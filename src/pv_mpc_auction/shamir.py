"""Shamir (t, n) secret sharing over Z_q.

A dealer chooses a random polynomial f(x) of degree (t-1) with
constant term equal to the secret. Each share s_i = f(i) for i = 1..n.
Any t shares reconstruct the secret via Lagrange interpolation; any
(t-1) shares reveal nothing (information-theoretic privacy).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class Share:
    """A single share (i, s_i) over Z_q."""

    i: int     # share index (1-based)
    value: int # the share value s_i = f(i) mod q


def _eval_poly(coeffs: Sequence[int], x: int, q: int) -> int:
    """Horner-rule polynomial evaluation mod q."""
    result = 0
    for c in reversed(coeffs):
        result = (result * x + c) % q
    return result


def split(secret: int, n: int, t: int, q: int) -> List[Share]:
    """Split `secret` into n Shamir shares with threshold t over Z_q.

    Args:
        secret: the value to share, must lie in [0, q).
        n:      total number of shares.
        t:      reconstruction threshold; 1 <= t <= n.
        q:      modulus (typically the subgroup order).

    Returns:
        A list of n Share objects.
    """
    if not 0 <= secret < q:
        raise ValueError("secret must lie in [0, q)")
    if not 1 <= t <= n:
        raise ValueError("require 1 <= t <= n")
    coeffs = [secret] + [secrets.randbelow(q) for _ in range(t - 1)]
    return [Share(i=i, value=_eval_poly(coeffs, i, q)) for i in range(1, n + 1)]


def _lagrange_coefficient(i: int, others: Iterable[int], q: int) -> int:
    """Compute the Lagrange coefficient for share index i at x=0."""
    num, den = 1, 1
    for j in others:
        if j == i:
            continue
        num = (num * (-j)) % q
        den = (den * (i - j)) % q
    return (num * pow(den, -1, q)) % q


def reconstruct(shares: Sequence[Share], q: int) -> int:
    """Reconstruct the secret from at least t shares via Lagrange interpolation."""
    if len(shares) == 0:
        raise ValueError("need at least one share")
    indices = [s.i for s in shares]
    if len(set(indices)) != len(indices):
        raise ValueError("share indices must be distinct")
    total = 0
    for s in shares:
        coeff = _lagrange_coefficient(s.i, indices, q)
        total = (total + coeff * s.value) % q
    return total


# -----------------------------------------------------------------------------
# Linear operations on shares (local, no interaction)
# -----------------------------------------------------------------------------
def add_shares(a: Sequence[Share], b: Sequence[Share], q: int) -> List[Share]:
    """Compute [a] + [b] = [a + b] pointwise."""
    if [s.i for s in a] != [s.i for s in b]:
        raise ValueError("share index sets must match")
    return [Share(i=s.i, value=(s.value + t.value) % q) for s, t in zip(a, b)]


def scalar_mul(c: int, a: Sequence[Share], q: int) -> List[Share]:
    """Compute c * [a] = [c * a] pointwise (c public)."""
    return [Share(i=s.i, value=(c * s.value) % q) for s in a]


def add_constant(k: int, a: Sequence[Share], q: int) -> List[Share]:
    """Compute [a] + k pointwise (k public)."""
    return [Share(i=s.i, value=(s.value + k) % q) for s in a]


# -----------------------------------------------------------------------------
# Simulated BGW multiplication (single party orchestrates honestly)
# -----------------------------------------------------------------------------
def simulated_mult(a: Sequence[Share], b: Sequence[Share], n: int, t: int, q: int) -> List[Share]:
    """Simulate BGW-style secure multiplication on Shamir shares.

    In a real distributed deployment each party would locally multiply
    its shares, then re-share the product to bring the polynomial
    degree from 2(t-1) back down to (t-1). Here we collapse that
    interaction into a single function call that:
      1. reconstructs a and b (only the simulator sees the cleartexts;
         no party would in reality),
      2. re-shares the product.
    This is purely for benchmarking the cost model on a single host;
    the public API mirrors what each party would compute.
    """
    ra = reconstruct(a, q)
    rb = reconstruct(b, q)
    return split((ra * rb) % q, n=n, t=t, q=q)
