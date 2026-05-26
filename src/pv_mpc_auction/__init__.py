"""PV-MPC-Auction reference implementation.

A privacy-preserving sealed-bid auction protocol composing
Pedersen commitments, Shamir secret sharing, and Schnorr
zero-knowledge proofs, anchored to an Ethereum smart contract.

Companion code for the paper accepted at ICST 2026.
"""

__version__ = "1.0.0"
__all__ = [
    "group",
    "pedersen",
    "shamir",
    "secgt",
    "protocol",
    "chain_sim",
]
