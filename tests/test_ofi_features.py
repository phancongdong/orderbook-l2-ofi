"""Unit tests for Order Flow Imbalance (OFI) and order-book features."""
from __future__ import annotations

from orderbook_ofi.models import BookSnapshot
from orderbook_ofi.ofi import (
    book_snapshot_features,
    compute_l1_ofi,
    compute_multilevel_ofi,
)


def test_book_features_and_l1_ofi_directional_cases():
    previous = BookSnapshot.from_levels(
        venue="test",
        market="spot",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_000_000_000_001,
        bids=[[100.0, 10.0], [99.0, 5.0]],
        asks=[[101.0, 8.0], [102.0, 4.0]],
    )

    # Case 1: Same prices, bid size +2, ask size -3 -> OFI = +2 - (-3) = +5
    current_size_change = BookSnapshot.from_levels(
        venue="test",
        market="spot",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_010_000_000_001,
        bids=[[100.0, 12.0], [99.0, 5.0]],
        asks=[[101.0, 5.0], [102.0, 4.0]],
    )
    features = book_snapshot_features(current_size_change, levels=2)
    assert features["mid"] == 100.5
    assert features["spread"] == 1.0
    assert features["top_imbalance"] > 0
    assert features["microprice"] > features["mid"]
    assert compute_l1_ofi(previous, current_size_change) == 5.0

    # Case 2: Bid price up (+100.5 with size 6), Ask price same -> OFI = +6 + 0 = +6
    current_bid_up = BookSnapshot.from_levels(
        venue="test",
        market="spot",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_010_000_000_001,
        bids=[[100.5, 6.0], [100.0, 10.0]],
        asks=[[101.0, 8.0], [102.0, 4.0]],
    )
    assert compute_l1_ofi(previous, current_bid_up) == 6.0

    # Case 3: Ask lifted (Ask price up 101 -> 102), Bid same -> OFI = 0 + 8 = +8
    current_ask_lifted = BookSnapshot.from_levels(
        venue="test",
        market="spot",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_010_000_000_001,
        bids=[[100.0, 10.0], [99.0, 5.0]],
        asks=[[102.0, 4.0], [103.0, 10.0]],
    )
    assert compute_l1_ofi(previous, current_ask_lifted) == 8.0

    # Case 4: Bid price down (100 -> 99), Ask same -> OFI = -10 + 0 = -10
    current_bid_down = BookSnapshot.from_levels(
        venue="test",
        market="spot",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_010_000_000_001,
        bids=[[99.0, 5.0]],
        asks=[[101.0, 8.0], [102.0, 4.0]],
    )
    assert compute_l1_ofi(previous, current_bid_down) == -10.0


def test_compute_multilevel_ofi():
    prev = BookSnapshot.from_levels(
        venue="test", market="spot", symbol="BTCUSDT",
        exchange_ts=1_000, receive_ts_ns=1_000_000,
        bids=[[100.0, 10.0], [99.0, 20.0]],
        asks=[[101.0, 8.0], [102.0, 15.0]],
    )
    curr = BookSnapshot.from_levels(
        venue="test", market="spot", symbol="BTCUSDT",
        exchange_ts=1_100, receive_ts_ns=1_100_000,
        bids=[[100.0, 15.0], [99.0, 25.0]],
        asks=[[101.0, 6.0], [102.0, 10.0]],
    )
    m_ofi = compute_multilevel_ofi(prev, curr, levels=2)
    # L1: (15 - 10) + (8 - 6) = 5 + 2 = 7.0
    # L2: (25 - 20) + (15 - 10) = 5 + 5 = 10.0
    assert m_ofi["l1_ofi"] == 7.0
    assert m_ofi["l2_ofi"] == 10.0
    assert "integrated_ofi" in m_ofi
