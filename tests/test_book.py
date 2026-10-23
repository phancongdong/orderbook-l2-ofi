"""Unit tests for sequence-aware local limit-order-book reconstruction."""
from __future__ import annotations

import pytest

from orderbook_ofi.book import LocalOrderBook, SequenceGapError
from orderbook_ofi.models import BookDelta, BookSnapshot


def test_local_book_load_snapshot_and_properties():
    book = LocalOrderBook("binance", "futures_um", "BTCUSDT")
    assert not book.initialized

    snapshot = BookSnapshot.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_001_000_000_000,
        bids=[[100.0, 10.0], [99.0, 5.0]],
        asks=[[101.0, 8.0], [102.0, 4.0]],
        sequence=100,
        source="rest_bootstrap",
    )
    book.load_snapshot(snapshot)

    assert book.initialized
    assert book.last_update_id == 100
    assert book.best_bid == (100.0, 10.0)
    assert book.best_ask == (101.0, 8.0)
    assert book.mid_price == 100.5
    assert book.spread == 1.0


def test_local_book_applies_delta_and_prunes_zero():
    book = LocalOrderBook("binance", "futures_um", "BTCUSDT")
    snapshot = BookSnapshot.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_001_000_000_000,
        bids=[[100.0, 10.0], [99.0, 5.0]],
        asks=[[101.0, 8.0], [102.0, 4.0]],
        sequence=100,
    )
    book.load_snapshot(snapshot)

    delta = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_001_100_000_000,
        first_update_id=101,
        last_update_id=102,
        previous_update_id=100,
        bids=[[100.0, 12.0], [99.0, 0.0]],  # 99.0 pruned
        asks=[[101.0, 5.0]],
    )
    assert book.apply(delta)
    rebuilt = book.snapshot(delta.exchange_ts_ns, delta.receive_ts_ns)
    assert rebuilt.sequence == 102
    assert rebuilt.bids[0].quantity == 12.0
    assert all(level.price != 99.0 for level in rebuilt.bids)


def test_local_book_rejects_sequence_gap():
    book = LocalOrderBook("binance", "futures_um", "BTCUSDT")
    snapshot = BookSnapshot.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_001_000_000_000,
        bids=[[100.0, 10.0]],
        asks=[[101.0, 8.0]],
        sequence=100,
    )
    book.load_snapshot(snapshot)

    broken = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_200,
        receive_ts_ns=1_700_000_001_200_000_000,
        first_update_id=104,
        last_update_id=104,
        previous_update_id=103,  # Expected 100
        bids=[],
        asks=[],
    )
    with pytest.raises(SequenceGapError):
        book.apply(broken)


def test_local_book_accepts_first_delta_that_bridges_snapshot_sequence():
    book = LocalOrderBook("binance", "futures_um", "ETHUSDT")
    snapshot = BookSnapshot.from_levels(
        venue="binance",
        market="futures_um",
        symbol="ETHUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_001_000_000_000,
        bids=[[100.0, 10.0]],
        asks=[[101.0, 8.0]],
        sequence=100,
    )
    delta = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="ETHUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_001_100_000_000,
        first_update_id=95,
        last_update_id=105,
        previous_update_id=94,
        bids=[[100.0, 12.0]],
        asks=[[101.0, 7.0]],
    )
    book.load_snapshot(snapshot)
    assert book.apply(delta)
    assert book.last_update_id == 105


def test_local_book_detects_crossed_book():
    book = LocalOrderBook("binance", "futures_um", "BTCUSDT")
    snapshot = BookSnapshot.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_001_000_000_000,
        bids=[[100.0, 10.0]],
        asks=[[101.0, 8.0]],
        sequence=100,
    )
    book.load_snapshot(snapshot)

    # Cross book: bid price 102.0 >= ask price 101.0
    crossed = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_001_100_000_000,
        first_update_id=101,
        last_update_id=101,
        previous_update_id=100,
        bids=[[102.0, 5.0]],
        asks=[],
    )
    with pytest.raises(SequenceGapError, match="crossed"):
        book.apply(crossed)
