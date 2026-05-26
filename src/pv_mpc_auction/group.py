"""Cryptographic group parameters.

Uses the 2048-bit MODP Group 14 from RFC 3526 as the underlying
prime-order subgroup. The generator g is fixed at 2 (the RFC value),
and a second generator h is derived deterministically by hashing a
public seed and squaring into the subgroup of order q -- a
nothing-up-my-sleeve construction so that log_g(h) is unknown.

A `SmallGroup` is provided for fast unit tests; production code
should always use `default_group()` which returns the RFC-3526 group.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache


# -----------------------------------------------------------------------------
# RFC 3526 Group 14 (2048-bit MODP)
# https://www.rfc-editor.org/rfc/rfc3526#section-3
# p is a safe prime: q = (p-1)/2 is also prime
# -----------------------------------------------------------------------------
_RFC3526_GROUP14_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E08"
    "8A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B"
    "302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9"
    "A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE6"
    "49286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8"
    "FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C"
    "180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF695581718"
    "3995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFF"
    "FFFFFFFF"
)

_P_RFC3526 = int(_RFC3526_GROUP14_HEX, 16)
_Q_RFC3526 = (_P_RFC3526 - 1) // 2
_G_RFC3526 = 2  # standard RFC generator


@dataclass(frozen=True)
class Group:
    """A safe-prime group of order q = (p-1)/2 with two generators g, h."""

    p: int  # safe prime
    q: int  # subgroup order, q = (p-1)/2
    g: int  # generator of the order-q subgroup
    h: int  # second generator, log_g(h) unknown

    @property
    def name(self) -> str:
        return f"SafePrimeGroup({self.p.bit_length()}-bit)"

    def random_exponent(self, rng) -> int:
        """Sample uniformly from Z_q."""
        # rng must have a `randbelow(n)` method like `secrets.SystemRandom`
        return rng.randbelow(self.q - 1) + 1

    def in_subgroup(self, x: int) -> bool:
        """Test whether x lies in the order-q subgroup of Z_p*."""
        return 1 <= x < self.p and pow(x, self.q, self.p) == 1


def _hash_to_subgroup(seed: bytes, p: int, q: int) -> int:
    """Derive an element of the order-q subgroup deterministically from `seed`.

    We compute SHA-256(seed)^2 mod p, then keep hashing-and-squaring until
    we land on a non-trivial subgroup element. Squaring guarantees the
    result is a quadratic residue, which for a safe prime is exactly the
    order-q subgroup.
    """
    counter = 0
    while True:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        candidate = int.from_bytes(digest, "big") % p
        squared = pow(candidate, 2, p)
        if squared != 1 and pow(squared, q, p) == 1:
            return squared
        counter += 1


@lru_cache(maxsize=1)
def default_group() -> Group:
    """Return the production 2048-bit RFC 3526 Group 14 with derived h.

    The RFC's generator g=2 is a generator of Z_p*; for the Pedersen
    commitment we require generators of the order-q subgroup of quadratic
    residues. We therefore use g' = 2^2 = 4 mod p, which is a QR and
    generates the order-q subgroup.
    """
    p, q = _P_RFC3526, _Q_RFC3526
    g = pow(_G_RFC3526, 2, p)  # g' = g^2 lands in the order-q QR subgroup
    # h is derived from a fixed public seed so it is reproducible across runs
    # and verifiable as a nothing-up-my-sleeve value.
    h = _hash_to_subgroup(b"PV-MPC-Auction/RFC3526-Group14/h-seed/v1", p, q)
    return Group(p=p, q=q, g=g, h=h)


# RFC 5054 (SRP) Group 1 --- 1024-bit verified safe prime. Used by
# `small_test_group()` for fast unit tests. We deliberately do NOT use
# this group in production --- 1024 bits is below current best practice
# for new deployments. `default_group()` returns the 2048-bit RFC 3526
# Group 14 which is the production-grade choice.
_RFC5054_1024_HEX = (
    "EEAF0AB9ADB38DD69C33F80AFA8FC5E860726187"
    "75FF3C0B9EA2314C9C256576D674DF7496EA81D3"
    "383B4813D692C6E0E0D5D8E250B98BE48E495C1D"
    "6089DAD15DC7D7B46154D6B6CE8EF4AD69B15D49"
    "82559B297BCF1885C529F566660E57EC68EDBC3C"
    "05726CC02FD4CBF4976EAA9AFD5138FE8376435B"
    "9FC61D2FC0EB06E3"
)
_P_RFC5054_1024 = int(_RFC5054_1024_HEX, 16)
_Q_RFC5054_1024 = (_P_RFC5054_1024 - 1) // 2
_G_RFC5054_1024 = 2


@lru_cache(maxsize=1)
def small_test_group() -> Group:
    """A 1024-bit RFC 5054 safe-prime group for fast unit tests.

    DO NOT use in production --- 1024 bits is below current best practice
    for new deployments. Production code should call `default_group()`,
    which returns the 2048-bit RFC 3526 Group 14.
    """
    p, q = _P_RFC5054_1024, _Q_RFC5054_1024
    g = pow(_G_RFC5054_1024, 2, p)  # in QR subgroup
    h = _hash_to_subgroup(b"PV-MPC-Auction/RFC5054-G1/h-seed/v1", p, q)
    return Group(p=p, q=q, g=g, h=h)
