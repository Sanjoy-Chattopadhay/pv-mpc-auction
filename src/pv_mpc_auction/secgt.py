"""Bit-decomposed secure greater-than over Shamir shares.

Given the bit-shares of two L-bit integers a and b, return a shared
indicator [c] such that c = 1 iff a > b. Uses the standard
top-differing-bit construction of Damgard, Geisler, Kroigaard 2007.

This module exposes both a fully secure version (operating only on
shares) and a `tournament_winner` helper that composes SecGT into a
binary-tree tournament with log_2(n) depth.
"""

from __future__ import annotations

from typing import List, Sequence

from . import shamir
from .shamir import Share


# -----------------------------------------------------------------------------
# Bit decomposition (each bidder does this locally before sharing)
# -----------------------------------------------------------------------------
def bit_decompose(value: int, bit_length: int) -> List[int]:
    """Return the little-endian bit list of `value` with fixed length."""
    if value < 0 or value >= (1 << bit_length):
        raise ValueError(f"value out of range for {bit_length}-bit decomposition")
    return [(value >> k) & 1 for k in range(bit_length)]


# -----------------------------------------------------------------------------
# SecGT --- secure greater-than on Shamir-shared bit-vectors
# -----------------------------------------------------------------------------
def secgt(
    a_bits: Sequence[Sequence[Share]],
    b_bits: Sequence[Sequence[Share]],
    n: int,
    t: int,
    q: int,
) -> List[Share]:
    """Securely compute [c] where c = 1 iff a > b.

    Args:
        a_bits: a_bits[k] is the share-vector of the k-th bit of a
                (k = 0 is the least-significant bit). Length L.
        b_bits: analogously for b.
        n, t, q: Shamir parameters; n >= 2t - 1.

    Returns:
        The share-vector of the indicator c.
    """
    L = len(a_bits)
    assert len(b_bits) == L, "bit-vectors must have equal length"

    # Step 1: XOR  e_k = a_k + b_k - 2 * (a_k * b_k)
    e: List[List[Share]] = []
    for k in range(L):
        ab = shamir.simulated_mult(a_bits[k], b_bits[k], n=n, t=t, q=q)
        ab2 = shamir.scalar_mul(2, ab, q=q)
        added = shamir.add_shares(a_bits[k], b_bits[k], q=q)
        e_k = shamir.add_shares(
            added,
            shamir.scalar_mul(-1, ab2, q=q),
            q=q,
        )
        e.append(e_k)

    # Step 2: prefix-OR from the most-significant bit downward
    #         h_{L-1} = e_{L-1};  h_k = h_{k+1} + e_k - h_{k+1} * e_k
    h: List[List[Share]] = [None] * L  # type: ignore
    h[L - 1] = e[L - 1]
    for k in range(L - 2, -1, -1):
        he = shamir.simulated_mult(h[k + 1], e[k], n=n, t=t, q=q)
        h[k] = shamir.add_shares(
            shamir.add_shares(h[k + 1], e[k], q=q),
            shamir.scalar_mul(-1, he, q=q),
            q=q,
        )

    # Step 3: indicator of top-differing bit  f_k = h_k - h_{k+1}, h_L := 0
    f: List[List[Share]] = [None] * L  # type: ignore
    zero_vec = shamir.split(0, n=n, t=t, q=q)  # share-vector for h_L = 0
    for k in range(L):
        h_next = h[k + 1] if k + 1 < L else zero_vec
        f[k] = shamir.add_shares(
            h[k],
            shamir.scalar_mul(-1, h_next, q=q),
            q=q,
        )

    # Step 4: c = sum_k f_k * a_k
    c_share = shamir.split(0, n=n, t=t, q=q)
    for k in range(L):
        fa = shamir.simulated_mult(f[k], a_bits[k], n=n, t=t, q=q)
        c_share = shamir.add_shares(c_share, fa, q=q)
    return c_share


# -----------------------------------------------------------------------------
# Tournament composition --- winner determination over n bidders
# -----------------------------------------------------------------------------
def tournament_winner(
    bid_values: Sequence[int],
    bit_length: int,
    n: int,
    t: int,
    q: int,
) -> tuple[int, int]:
    """Determine the maximum bid via SecGT tournament.

    For clarity we keep this benchmark-oriented: we share each bid
    fresh, run SecGT comparisons, and reconstruct the result.
    Returns (winner_index_1_based, winning_bid).
    """
    if len(bid_values) != n:
        raise ValueError("bid_values length must equal n")

    # Each bidder shares its bid-bits
    bit_shares: list[list[list[Share]]] = []
    for v in bid_values:
        bits = bit_decompose(v, bit_length)
        bit_shares.append([shamir.split(b, n=n, t=t, q=q) for b in bits])

    # Carry the (index, bit-shares) through a balanced tree
    leaves: list[tuple[int, list[list[Share]]]] = list(
        enumerate(bit_shares, start=1)
    )

    while len(leaves) > 1:
        next_level: list[tuple[int, list[list[Share]]]] = []
        for i in range(0, len(leaves), 2):
            if i + 1 == len(leaves):
                next_level.append(leaves[i])  # odd one out advances
                continue
            (idx_a, bits_a), (idx_b, bits_b) = leaves[i], leaves[i + 1]
            c_share = secgt(bits_a, bits_b, n=n, t=t, q=q)
            c = shamir.reconstruct(c_share, q=q)
            winner_idx = idx_a if c == 1 else idx_b
            winner_bits = bits_a if c == 1 else bits_b
            next_level.append((winner_idx, winner_bits))
        leaves = next_level

    winner_idx_final, winner_bit_shares = leaves[0]
    # Reconstruct the winning bid from its bit-shares
    winning_bid = 0
    for k, bs in enumerate(winner_bit_shares):
        bit = shamir.reconstruct(bs, q=q)
        winning_bid += int(bit) << k
    return winner_idx_final, winning_bid
