"""Unit tests for order book and trade event models."""
from __future__ import annotations

import json
import pytest

from orderbook_ofi.models import (
    AggressorSide,
    BookDelta,
    BookLevel,
    BookSnapshot,
    TradeEvent,
    timestamp_to_ns,
)


def test_timestamp_to_ns_normalization():
    # Seconds
    assert timestamp_to_ns(1_700_000_000) == 1_700_000_000_000_000_000
    # Milliseconds
    assert timestamp_to_ns(1_700_000_000_000) == 1_700_000_000_000_000_000
    # Microseconds
    assert timestamp_to_ns(1_700_000_000_000_000) == 1_700_000_000_000_000_000
    # Nanoseconds
    assert timestamp_to_ns(1_700_000_000_000_000_000) == 1_700_000_000_000_000_000


def test_book_level_validation():
    lvl = BookLevel(100.5, 2.0)
    assert lvl.price == 100.5
    assert lvl.quantity == 2.0
    assert lvl.as_pair() == [100.5, 2.0]

    with pytest.raises(ValueError, match="price must be positive"):
        BookLevel(-1.0, 10.0)

    with pytest.raises(ValueError, match="quantity must be non-negative"):
        BookLevel(100.0, -0.5)


def test_trade_event_from_maker_flag():
    # buyer_is_maker=True -> Aggressive SELL
    sell_trade = TradeEvent.from_maker_flag(
        venue="binance",
        market="futures_um",
        symbol="btcusdt",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_000_000_100_000,
        trade_id="12345",
        price=50000.0,
        quantity=0.5,
        buyer_is_maker=True,
    )
    assert sell_trade.aggressor_side == AggressorSide.SELL
    assert sell_trade.symbol == "BTCUSDT"
    assert sell_trade.quote_quantity == 25000.0

    record = sell_trade.to_record()
    assert record["aggressor_side"] == "SELL"
    assert json.loads(record["raw_json"]) == {}

    # buyer_is_maker=False -> Aggressive BUY
    buy_trade = TradeEvent.from_maker_flag(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_000_000_100_000,
        trade_id="12346",
        price=50000.0,
        quantity=1.0,
        buyer_is_maker=False,
    )
    assert buy_trade.aggressor_side == AggressorSide.BUY


def test_book_snapshot_sorting_and_validation():
    snap = BookSnapshot.from_levels(
        venue="binance",
        market="futures_um",
        symbol="ETHUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_000_000_000_000,
        bids=[[2990.0, 1.0], [3000.0, 5.0]],  # Out of order
        asks=[[3020.0, 2.0], [3010.0, 4.0]],  # Out of order
        sequence=42,
    )
    # Bids sorted descending
    assert snap.bids[0].price == 3000.0
    assert snap.bids[1].price == 2990.0
    # Asks sorted ascending
    assert snap.asks[0].price == 3010.0
    assert snap.asks[1].price == 3020.0


def test_crossed_book_snapshot_rejected():
    with pytest.raises(ValueError, match="book snapshot is crossed"):
        BookSnapshot.from_levels(
            venue="binance",
            market="futures_um",
            symbol="ETHUSDT",
            exchange_ts=1_700_000_000_000,
            receive_ts_ns=1_700_000_000_000_000_000,
            bids=[[3010.0, 1.0]],  # Best bid >= Best ask
            asks=[[3000.0, 1.0]],
        )


def test_book_delta_validation():
    delta = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_000_000_000_000,
        first_update_id=10,
        last_update_id=15,
        previous_update_id=9,
        bids=[[50000.0, 1.0]],
        asks=[[50001.0, 0.0]],
    )
    assert delta.first_update_id == 10
    assert delta.last_update_id == 15
    assert delta.previous_update_id == 9

    with pytest.raises(ValueError, match="first_update_id cannot exceed last_update_id"):
        BookDelta.from_levels(
            venue="binance",
            market="futures_um",
            symbol="BTCUSDT",
            exchange_ts=1_700_000_000_000,
            receive_ts_ns=1_700_000_000_000_000_000,
            first_update_id=20,
            last_update_id=10,
            previous_update_id=None,
            bids=[],
            asks=[],
        )
