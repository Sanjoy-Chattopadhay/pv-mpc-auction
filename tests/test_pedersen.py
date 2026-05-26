"""Unit tests for Pedersen commitments + Schnorr ZKPs."""

import pytest

from pv_mpc_auction import pedersen
from pv_mpc_auction.group import small_test_group


@pytest.fixture
def group():
    return small_test_group()


def test_commit_then_open(group):
    C, r = pedersen.commit(group, m=42)
    assert pedersen.verify_opening(C, 42, r)


def test_wrong_opening_fails(group):
    C, r = pedersen.commit(group, m=42)
    assert not pedersen.verify_opening(C, 43, r)
    assert not pedersen.verify_opening(C, 42, r + 1)


def test_hiding_property(group):
    """Same message under independent randomness yields distinct commitments."""
    samples = {pedersen.commit(group, 100)[0].value for _ in range(50)}
    assert len(samples) == 50


def test_homomorphic_add(group):
    C1, r1 = pedersen.commit(group, 7)
    C2, r2 = pedersen.commit(group, 13)
    summed = C1 * C2
    assert pedersen.verify_opening(summed, 20, (r1 + r2) % group.q)


def test_zkp_complete(group):
    C, r = pedersen.commit(group, 999)
    proof = pedersen.prove(C, 999, r)
    assert pedersen.verify(C, proof)


def test_zkp_sound(group):
    """A proof produced for the wrong witness must not verify."""
    C_real, r_real = pedersen.commit(group, 999)
    # Forge: build a proof against a different commitment's witness
    C_fake, r_fake = pedersen.commit(group, 1000)
    forged = pedersen.prove(C_fake, 1000, r_fake)
    assert not pedersen.verify(C_real, forged)


def test_zkp_tampered_proof_rejected(group):
    C, r = pedersen.commit(group, 42)
    proof = pedersen.prove(C, 42, r)
    tampered = pedersen.Proof(
        tau=proof.tau,
        s_m=(proof.s_m + 1) % group.q,
        s_r=proof.s_r,
    )
    assert not pedersen.verify(C, tampered)


def test_proof_serialisation_length(group):
    C, r = pedersen.commit(group, 1)
    proof = pedersen.prove(C, 1, r)
    assert len(proof.to_bytes()) == 256 + 256 + 256
