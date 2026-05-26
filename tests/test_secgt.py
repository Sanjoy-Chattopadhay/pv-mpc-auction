"""Unit tests for the bit-decomposed secure greater-than primitive."""

import secrets

import pytest

from pv_mpc_auction import secgt, shamir
from pv_mpc_auction.group import small_test_group


@pytest.fixture(scope="module")
def q():
    return small_test_group().q


@pytest.mark.parametrize("a,b,expected", [
    (5,  3, 1),
    (3,  5, 0),
    (10, 10, 0),
    (0,  1, 0),
    (1,  0, 1),
    (255, 254, 1),
    (255, 255, 0),
])
def test_secgt_simple(q, a, b, expected):
    L = 8
    a_bits = [shamir.split(b_, n=5, t=3, q=q) for b_ in secgt.bit_decompose(a, L)]
    b_bits = [shamir.split(b_, n=5, t=3, q=q) for b_ in secgt.bit_decompose(b, L)]
    c_share = secgt.secgt(a_bits, b_bits, n=5, t=3, q=q)
    c = shamir.reconstruct(c_share, q=q)
    assert c == expected, f"SecGT({a},{b}) = {c}, expected {expected}"


def test_tournament_finds_max(q):
    rng = secrets.SystemRandom()
    bids = [rng.randrange(0, 1 << 12) for _ in range(8)]
    expected_winner = bids.index(max(bids)) + 1   # 1-based
    expected_value  = max(bids)
    winner_idx, winning_bid = secgt.tournament_winner(
        bids, bit_length=12, n=8, t=5, q=q
    )
    assert winner_idx == expected_winner
    assert winning_bid == expected_value


def test_tournament_odd_count(q):
    bids = [10, 30, 20, 50, 40]
    winner_idx, winning_bid = secgt.tournament_winner(
        bids, bit_length=8, n=5, t=3, q=q
    )
    assert winner_idx == 4
    assert winning_bid == 50


def test_bit_decompose_range_error():
    with pytest.raises(ValueError):
        secgt.bit_decompose(-1, bit_length=4)
    with pytest.raises(ValueError):
        secgt.bit_decompose(16, bit_length=4)  # 2^4 = 16 out of range
