"""Five-phase PV-MPC-Auction orchestration.

This module wires together `pedersen`, `shamir`, `secgt`, and
`chain_sim` (or a real Ethereum backend) into the full protocol
described in the paper. The top-level entry point is
`run_auction(bids, ...)` which returns an `AuctionResult`.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import pedersen, secgt, shamir
from .chain_sim import Blockchain, sha256
from .group import Group, default_group
from .pedersen import Commitment, Proof
from .shamir import Share


# -----------------------------------------------------------------------------
# Per-bidder state
# -----------------------------------------------------------------------------
@dataclass
class BidderState:
    """All state held locally by one bidder during a run."""

    index: int                     # 1-based
    bid: int
    randomness: int = 0
    commitment: Optional[Commitment] = None
    proof: Optional[Proof] = None
    integer_share: Optional[List[Share]] = None
    bit_shares: Optional[List[List[Share]]] = None


# -----------------------------------------------------------------------------
# Result + per-phase timing
# -----------------------------------------------------------------------------
@dataclass
class PhaseTimings:
    registration: float = 0.0
    commitment: float = 0.0
    sharing: float = 0.0
    mpc: float = 0.0
    verification: float = 0.0

    @property
    def total(self) -> float:
        return (self.registration + self.commitment + self.sharing
                + self.mpc + self.verification)


@dataclass
class AuctionResult:
    winner_index: int             # 1-based
    winning_bid: int
    verified: bool
    timings: PhaseTimings
    chain: Blockchain
    n: int
    t: int
    bit_length: int


# -----------------------------------------------------------------------------
# Phase implementations
# -----------------------------------------------------------------------------
def _phase1_registration(chain: Blockchain, n: int, deposit: int = 1000):
    txs: List[Dict[str, Any]] = []
    for i in range(1, n + 1):
        txs.append({
            "type": "reg",
            "bidder": i,
            "pubkey_hash": sha256(f"P{i}".encode()).hex(),
            "deposit": deposit,
        })
    chain.mine(txs)


def _phase2_commit(chain: Blockchain, bidders: List[BidderState], group: Group):
    txs: List[Dict[str, Any]] = []
    for b in bidders:
        C, r = pedersen.commit(group, b.bid)
        b.commitment = C
        b.randomness = r
        b.proof = pedersen.prove(C, b.bid, r)
        txs.append({
            "type": "commit",
            "bidder": b.index,
            "C": C.value.to_bytes(256, "big"),
            "proof": b.proof.to_bytes(),
        })
    chain.mine(txs)


def _phase3_share(
    chain: Blockchain,
    bidders: List[BidderState],
    n: int,
    t: int,
    q: int,
    bit_length: int,
):
    txs: List[Dict[str, Any]] = []
    for b in bidders:
        b.integer_share = shamir.split(b.bid, n=n, t=t, q=q)
        bits = secgt.bit_decompose(b.bid, bit_length)
        b.bit_shares = [shamir.split(bk, n=n, t=t, q=q) for bk in bits]
        # Anchor the SHA-256 hash of every share on-chain (one tx per bidder)
        share_hashes = [
            sha256(str(s.value).encode()).hex()
            for s in b.integer_share
        ]
        for bs in b.bit_shares:
            share_hashes.extend(
                sha256(str(s.value).encode()).hex() for s in bs
            )
        txs.append({
            "type": "share",
            "bidder": b.index,
            "share_hashes": "|".join(share_hashes),
        })
    chain.mine(txs)


def _phase4_mpc(
    chain: Blockchain,
    bidders: List[BidderState],
    n: int,
    t: int,
    q: int,
    bit_length: int,
) -> tuple[int, int]:
    # Consistency check: integer share equals sum_k 2^k * bit-share
    for b in bidders:
        recombined = shamir.split(0, n=n, t=t, q=q)
        for k, bs in enumerate(b.bit_shares):  # type: ignore[arg-type]
            scaled = shamir.scalar_mul(1 << k, bs, q=q)
            recombined = shamir.add_shares(recombined, scaled, q=q)
        diff = shamir.add_shares(
            b.integer_share,  # type: ignore[arg-type]
            shamir.scalar_mul(-1, recombined, q=q),
            q=q,
        )
        delta = shamir.reconstruct(diff, q=q)
        assert delta == 0, f"bit/integer inconsistency for bidder {b.index}"

    # Tournament over the bidders
    bid_values = [b.bid for b in bidders]
    winner_idx, winning_bid = secgt.tournament_winner(
        bid_values, bit_length, n=n, t=t, q=q
    )
    # Phase-4 boundary: mine an MPC-completion marker block so each
    # protocol phase corresponds to exactly one mined block.
    chain.mine([{
        "type": "mpc_complete",
        "winner_index_pending_verification": winner_idx,
    }])
    return winner_idx, winning_bid


def _phase5_verify(
    chain: Blockchain,
    bidders: List[BidderState],
    winner_idx: int,
    winning_bid: int,
) -> bool:
    winner = bidders[winner_idx - 1]
    assert winner.commitment is not None
    # 1) Opening check
    ok_open = pedersen.verify_opening(winner.commitment, winner.bid, winner.randomness)
    # 2) Proof check
    assert winner.proof is not None
    ok_proof = pedersen.verify(winner.commitment, winner.proof)
    # 3) Chain integrity
    chain_ok, _ = chain.verify()
    chain.mine([{
        "type": "result",
        "winner": winner_idx,
        "bid": winning_bid,
        "valid": int(ok_open and ok_proof and chain_ok),
    }])
    return ok_open and ok_proof and chain_ok


# -----------------------------------------------------------------------------
# Top-level entry point
# -----------------------------------------------------------------------------
def run_auction(
    bids: List[int],
    *,
    group: Optional[Group] = None,
    threshold: Optional[int] = None,
    bit_length: int = 32,
    chain_difficulty: int = 1,
) -> AuctionResult:
    """Execute one full five-phase auction over the given bid list.

    Args:
        bids: bidder-indexed bid values; element 0 is bidder 1, etc.
        group: cryptographic group (defaults to RFC 3526 2048-bit).
        threshold: t; defaults to floor(n/2) + 1.
        bit_length: number of bits per bid.
        chain_difficulty: PoW difficulty in leading zero bytes.

    Returns:
        AuctionResult with timings, winner, and the mined chain.
    """
    if not bids:
        raise ValueError("need at least one bid")
    n = len(bids)
    t = threshold if threshold is not None else (n // 2 + 1)
    if not 1 <= t <= n:
        raise ValueError("threshold out of range")
    grp = group if group is not None else default_group()
    q = grp.q

    bidders = [BidderState(index=i + 1, bid=v) for i, v in enumerate(bids)]
    chain = Blockchain(difficulty=chain_difficulty)
    timings = PhaseTimings()

    # ---------------- Phase 1 ----------------
    t0 = time.perf_counter()
    _phase1_registration(chain, n)
    timings.registration = time.perf_counter() - t0

    # ---------------- Phase 2 ----------------
    t0 = time.perf_counter()
    _phase2_commit(chain, bidders, grp)
    timings.commitment = time.perf_counter() - t0

    # ---------------- Phase 3 ----------------
    t0 = time.perf_counter()
    _phase3_share(chain, bidders, n=n, t=t, q=q, bit_length=bit_length)
    timings.sharing = time.perf_counter() - t0

    # ---------------- Phase 4 ----------------
    t0 = time.perf_counter()
    winner_idx, winning_bid = _phase4_mpc(chain, bidders, n=n, t=t, q=q, bit_length=bit_length)
    timings.mpc = time.perf_counter() - t0

    # ---------------- Phase 5 ----------------
    t0 = time.perf_counter()
    verified = _phase5_verify(chain, bidders, winner_idx, winning_bid)
    timings.verification = time.perf_counter() - t0

    return AuctionResult(
        winner_index=winner_idx,
        winning_bid=winning_bid,
        verified=verified,
        timings=timings,
        chain=chain,
        n=n,
        t=t,
        bit_length=bit_length,
    )
