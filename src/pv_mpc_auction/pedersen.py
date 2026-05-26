"""Pedersen commitment + non-interactive Schnorr opening proof.

The commitment is:
    C = g^m * h^r  mod p

It is perfectly hiding (over m) and computationally binding (under DLog).

The opening proof shows knowledge of (m, r) such that C = g^m h^r,
without revealing them. We use the standard sigma protocol made
non-interactive via the Fiat-Shamir heuristic with SHA-256.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Tuple

from .group import Group


# -----------------------------------------------------------------------------
# Commitments
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Commitment:
    """A Pedersen commitment C = g^m h^r in the subgroup of Z_p*."""

    value: int  # the group element C
    group: Group

    def __post_init__(self) -> None:
        if not self.group.in_subgroup(self.value):
            raise ValueError("Commitment is not in the order-q subgroup")

    def __mul__(self, other: "Commitment") -> "Commitment":
        """Homomorphic addition: C1 * C2 = Commit(m1+m2, r1+r2)."""
        if self.group != other.group:
            raise ValueError("Cannot combine commitments from different groups")
        return Commitment(
            value=(self.value * other.value) % self.group.p,
            group=self.group,
        )


def commit(group: Group, m: int, r: int | None = None) -> Tuple[Commitment, int]:
    """Compute a Pedersen commitment C = g^m h^r.

    If `r` is None, a uniformly random `r in Z_q` is sampled.
    Returns (C, r) so the caller can store r for later opening.
    """
    if not 0 <= m < group.q:
        raise ValueError(f"Message m must lie in [0, q); got bit-length {m.bit_length()}")
    if r is None:
        r = secrets.randbelow(group.q - 1) + 1
    if not 0 <= r < group.q:
        raise ValueError("Randomness r must lie in [0, q)")
    C = (pow(group.g, m, group.p) * pow(group.h, r, group.p)) % group.p
    return Commitment(value=C, group=group), r


def verify_opening(C: Commitment, m: int, r: int) -> bool:
    """Check that (m, r) opens the commitment C correctly."""
    expected, _ = commit(C.group, m, r)
    return expected.value == C.value


# -----------------------------------------------------------------------------
# Non-interactive Schnorr ZKP of knowledge of (m, r) such that C = g^m h^r
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Proof:
    """A Schnorr proof of knowledge for a Pedersen commitment opening."""

    tau: int  # the first message (commitment to k_m, k_r)
    s_m: int  # response on the message exponent
    s_r: int  # response on the randomness exponent

    def to_bytes(self) -> bytes:
        # Fixed-size big-endian encodings, concatenated.
        # We use 256-byte fields throughout so the same serialiser
        # works for any group up to 2048 bits (RFC 3526 Group 14).
        return (
            self.tau.to_bytes(256, "big")
            + self.s_m.to_bytes(256, "big")
            + self.s_r.to_bytes(256, "big")
        )


def _fiat_shamir_challenge(group: Group, C: Commitment, tau: int) -> int:
    """Compute the Fiat-Shamir challenge c = H(g, h, C, tau) mod q."""
    blob = (
        group.g.to_bytes(256, "big")
        + group.h.to_bytes(256, "big")
        + C.value.to_bytes(256, "big")
        + tau.to_bytes(256, "big")
    )
    digest = hashlib.sha256(blob).digest()
    return int.from_bytes(digest, "big") % group.q


def prove(C: Commitment, m: int, r: int) -> Proof:
    """Produce a non-interactive Schnorr proof of knowledge for (m, r)."""
    group = C.group
    k_m = secrets.randbelow(group.q - 1) + 1
    k_r = secrets.randbelow(group.q - 1) + 1
    tau = (pow(group.g, k_m, group.p) * pow(group.h, k_r, group.p)) % group.p
    c = _fiat_shamir_challenge(group, C, tau)
    s_m = (k_m - c * m) % group.q
    s_r = (k_r - c * r) % group.q
    return Proof(tau=tau, s_m=s_m, s_r=s_r)


def verify(C: Commitment, proof: Proof) -> bool:
    """Verify a Schnorr proof of knowledge for the commitment opening."""
    group = C.group
    if not group.in_subgroup(proof.tau):
        return False
    c = _fiat_shamir_challenge(group, C, proof.tau)
    lhs = (
        pow(group.g, proof.s_m, group.p)
        * pow(group.h, proof.s_r, group.p)
        * pow(C.value, c, group.p)
    ) % group.p
    return lhs == proof.tau
