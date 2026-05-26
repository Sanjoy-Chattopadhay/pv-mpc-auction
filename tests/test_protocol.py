"""End-to-end test of the five-phase protocol against the simulated chain."""

import pytest

from pv_mpc_auction.group import small_test_group
from pv_mpc_auction.protocol import run_auction


@pytest.fixture(scope="module")
def group():
    return small_test_group()


def test_protocol_picks_max(group):
    bids = [10, 50, 30, 90, 20]   # bidder 4 should win
    result = run_auction(bids, group=group, bit_length=8, chain_difficulty=0)
    assert result.winner_index == 4
    assert result.winning_bid == 90
    assert result.verified is True


def test_protocol_smallest_n(group):
    """The protocol must also work with the smallest meaningful n=3."""
    bids = [7, 13, 11]
    result = run_auction(bids, group=group, bit_length=8, chain_difficulty=0)
    assert result.winner_index == 2
    assert result.winning_bid == 13


def test_protocol_consistent_chain(group):
    bids = [11, 22, 33, 44]
    result = run_auction(bids, group=group, bit_length=8, chain_difficulty=0)
    ok, reason = result.chain.verify()
    assert ok, reason


def test_protocol_phase_count(group):
    bids = [1, 2, 3]
    result = run_auction(bids, group=group, bit_length=8, chain_difficulty=0)
    # Genesis + 5 phase blocks
    assert len(result.chain.blocks) == 6


def test_protocol_timings_nonzero(group):
    bids = [5, 15, 25]
    result = run_auction(bids, group=group, bit_length=8, chain_difficulty=0)
    t = result.timings
    assert t.commitment > 0
    assert t.sharing > 0
    assert t.mpc > 0
    assert t.total > 0
