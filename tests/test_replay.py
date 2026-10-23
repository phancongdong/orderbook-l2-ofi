"""Unit tests for deterministic L2 replay and forward returns."""
from __future__ import annotations

import pandas as pd

from orderbook_ofi.models import BookDelta, BookSnapshot
from orderbook_ofi.replay import add_forward_mid_returns, correlation_or_none, replay_l2


def _snapshot() -> BookSnapshot:
    return BookSnapshot.from_levels(
        venue="test",
        market="perp",
        symbol="ETHUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_000_010_000_000,
        bids=[[100.0, 10.0], [99.0, 5.0]],
        asks=[[101.0, 8.0], [102.0, 4.0]],
        sequence=100,
        source="bootstrap",
    )


def test_replay_ignores_stale_and_applies_sequence_chain():
    stale = BookDelta.from_levels(
        venue="test",
        market="perp",
        symbol="ETHUSDT",
        exchange_ts=1_700_000_000_020,
        receive_ts_ns=1_700_000_000_020_000_000,
        first_update_id=99,
        last_update_id=100,
        previous_update_id=99,
        bids=[],
        asks=[],
    )
    update = BookDelta.from_levels(
        venue="test",
        market="perp",
        symbol="ETHUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_000_110_000_000,
        first_update_id=101,
        last_update_id=101,
        previous_update_id=100,
        bids=[[100.0, 12.0]],
        asks=[[101.0, 6.0]],
    )

    features, stats = replay_l2(_snapshot(), [stale, update], include_multilevel_ofi=True)

    assert stats.stale_deltas == 1
    assert stats.deltas_applied == 1
    assert stats.sequence_gaps == 0
    assert features.iloc[0]["top_imbalance"] > 0
    assert features.iloc[0]["l1_ofi"] == 4.0
    assert "integrated_ofi" in features.columns


def test_forward_return_uses_first_state_at_or_after_horizon():
    frame = pd.DataFrame({
        "exchange_ts_ns": [0, 500_000_000, 1_100_000_000, 2_000_000_000],
        "mid": [100.0, 100.1, 100.2, 100.4],
    })

    result = add_forward_mid_returns(frame, horizons_seconds=(1,))

    assert result.iloc[0]["forward_mid_return_1s"] == 100.2 / 100.0 - 1.0
    assert pd.isna(result.iloc[-1]["forward_mid_return_1s"])


def test_forward_return_can_use_receive_time_for_causal_alignment():
    frame = pd.DataFrame({
        "exchange_ts_ns": [0, 1, 2],
        "receive_ts_ns": [0, 900_000_000, 1_100_000_000],
        "mid": [100.0, 100.1, 100.3],
    })

    result = add_forward_mid_returns(
        frame,
        horizons_seconds=(1,),
        timestamp_column="receive_ts_ns",
    )

    assert result.iloc[0]["forward_mid_return_1s"] == 100.3 / 100.0 - 1.0


def test_correlation_or_none():
    s1 = pd.Series([1.0, 2.0, 3.0, 4.0])
    s2 = pd.Series([2.0, 4.0, 6.0, 8.0])
    assert correlation_or_none(s1, s2) == 1.0

    constant = pd.Series([1.0, 1.0, 1.0, 1.0])
    assert correlation_or_none(s1, constant) is None
