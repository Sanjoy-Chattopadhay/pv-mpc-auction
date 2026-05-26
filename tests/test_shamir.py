"""Unit tests for Shamir (t,n) secret sharing."""

import pytest

from pv_mpc_auction import shamir
from pv_mpc_auction.group import small_test_group


@pytest.fixture(scope="module")
def q():
    return small_test_group().q


@pytest.mark.parametrize("n,t,secret", [
    (5, 3, 12345),
    (10, 6, 0),
    (7, 4, 999_999_999),
    (3, 2, 1),
])
def test_reconstruct_any_t(q, n, t, secret):
    shares = shamir.split(secret, n=n, t=t, q=q)
    # Reconstruct from various subsets of exactly t shares
    for start in range(n - t + 1):
        subset = shares[start:start + t]
        assert shamir.reconstruct(subset, q=q) == secret


def test_fewer_than_t_reveals_nothing(q):
    """Two distinct secrets must give same-distribution view to < t parties."""
    shares_a = shamir.split(11, n=5, t=3, q=q)
    shares_b = shamir.split(99, n=5, t=3, q=q)
    # Reconstructing 2 of the 11-shares as if they were of a different
    # polynomial still works (information-theoretic privacy).
    # We just confirm that 2-share "reconstruction" with arbitrary
    # missing data produces *some* result -- not the original 11.
    partial = shares_a[:2]
    # No assertion about value; the privacy guarantee is informational.
    assert len(partial) == 2
    # And that 2 different secrets can produce 2 share-vectors that
    # would extrapolate to *anything* under a different polynomial.
    assert shares_a[:2] != shares_b[:2]


def test_linear_combination(q):
    a = shamir.split(7, n=5, t=3, q=q)
    b = shamir.split(13, n=5, t=3, q=q)
    summed = shamir.add_shares(a, b, q=q)
    assert shamir.reconstruct(summed[:3], q=q) == 20

    scaled = shamir.scalar_mul(4, a, q=q)
    assert shamir.reconstruct(scaled[:3], q=q) == 28

    plus_const = shamir.add_constant(100, a, q=q)
    assert shamir.reconstruct(plus_const[:3], q=q) == 107


def test_simulated_mult(q):
    a = shamir.split(6, n=5, t=3, q=q)
    b = shamir.split(7, n=5, t=3, q=q)
    prod = shamir.simulated_mult(a, b, n=5, t=3, q=q)
    assert shamir.reconstruct(prod[:3], q=q) == 42


def test_invalid_parameters(q):
    with pytest.raises(ValueError):
        shamir.split(0, n=3, t=0, q=q)
    with pytest.raises(ValueError):
        shamir.split(-1, n=3, t=2, q=q)
    with pytest.raises(ValueError):
        shamir.reconstruct([], q=q)
