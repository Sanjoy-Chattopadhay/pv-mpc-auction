"""In-memory PoW blockchain simulator.

Used for offline experiments that do not require Sepolia connectivity.
Provides a hash-linked chain with a Merkle root over the transaction
list and a SHA-256 proof-of-work at adjustable difficulty.

The on-chain leg of the real protocol is realised by `MPCAuction.sol`;
this module exists to make the paper's benchmarks self-contained and
reproducible without network access.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _serialize_tx(tx: Dict[str, Any]) -> bytes:
    # Deterministic serialisation: sort keys and encode strings UTF-8.
    items = sorted(tx.items())
    parts: list[bytes] = []
    for k, v in items:
        parts.append(k.encode("utf-8"))
        if isinstance(v, int):
            parts.append(v.to_bytes(64, "big", signed=False)[-32:])
        elif isinstance(v, bytes):
            parts.append(v)
        else:
            parts.append(str(v).encode("utf-8"))
    return b"||".join(parts)


def merkle_root(txs: List[Dict[str, Any]]) -> bytes:
    """Compute a binary Merkle root over the transaction list.

    Single-tx blocks have root = H(tx). Empty blocks have root = H("").
    Odd-out leaves are paired with themselves at each level.
    """
    if not txs:
        return sha256(b"")
    layer = [sha256(_serialize_tx(tx)) for tx in txs]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


@dataclass
class Block:
    index: int
    prev_hash: bytes
    root: bytes
    nonce: int
    timestamp: float
    txs: List[Dict[str, Any]] = field(default_factory=list)

    def header_hash(self) -> bytes:
        return sha256(
            self.index.to_bytes(8, "big")
            + self.prev_hash
            + self.root
            + self.nonce.to_bytes(8, "big")
            + int(self.timestamp).to_bytes(8, "big")
        )


@dataclass
class Blockchain:
    """A toy PoW chain. `difficulty` is the number of leading zero bytes."""

    difficulty: int = 1
    blocks: List[Block] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.blocks:
            genesis = Block(
                index=0,
                prev_hash=b"\x00" * 32,
                root=sha256(b"genesis"),
                nonce=0,
                timestamp=time.time(),
                txs=[],
            )
            self.blocks.append(genesis)

    def tip(self) -> Block:
        return self.blocks[-1]

    def mine(self, txs: List[Dict[str, Any]]) -> Block:
        prev = self.tip()
        root = merkle_root(txs)
        nonce = 0
        target_prefix = b"\x00" * self.difficulty
        while True:
            candidate = Block(
                index=prev.index + 1,
                prev_hash=prev.header_hash(),
                root=root,
                nonce=nonce,
                timestamp=time.time(),
                txs=txs,
            )
            if candidate.header_hash().startswith(target_prefix):
                self.blocks.append(candidate)
                return candidate
            nonce += 1

    def verify(self) -> Tuple[bool, str]:
        """Verify chain integrity. Returns (ok, reason)."""
        for k in range(1, len(self.blocks)):
            cur = self.blocks[k]
            prev = self.blocks[k - 1]
            if cur.prev_hash != prev.header_hash():
                return False, f"hash chain broken at block {k}"
            if cur.root != merkle_root(cur.txs):
                return False, f"merkle root mismatch at block {k}"
            target = b"\x00" * self.difficulty
            if not cur.header_hash().startswith(target):
                return False, f"PoW invalid at block {k}"
        return True, "ok"
