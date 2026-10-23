"""Deterministic sequence-safe L2 replay and short-horizon price-impact analytics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from orderbook_ofi.book import LocalOrderBook, SequenceGapError
from orderbook_ofi.models import BookDelta, BookSnapshot
from orderbook_ofi.ofi import book_snapshot_features, compute_l1_ofi, compute_multilevel_ofi


@dataclass(frozen=True)
class L2ReplayStats:
    """Statistics tracking the integrity of an offline or online L2 replay."""
    deltas_seen: int
    deltas_applied: int
    stale_deltas: int
    sequence_gaps: int
    crossed_books: int


def replay_l2(
    snapshot: BookSnapshot,
    deltas: Iterable[BookDelta],
    depth: int = 20,
    include_multilevel_ofi: bool = False,
    multilevel_depth: int = 5,
) -> tuple[pd.DataFrame, L2ReplayStats]:
    """Replay incremental L2 updates against a bootstrap snapshot in strict sequence order.

    Extracts point-in-time order-book metrics and Cont's OFI at each applied state transition.

    Args:
        snapshot: Initial sequence-aware BookSnapshot.
        deltas: Stream or iterable of BookDelta objects.
        depth: Level depth to preserve in snapshots and feature calculations.
        include_multilevel_ofi: Whether to also calculate multi-level OFI per tick.
        multilevel_depth: Depth levels for multi-level OFI (default: 5).

    Returns:
        tuple[pd.DataFrame, L2ReplayStats]: Reconstructed feature timeseries and integrity stats.
    """
    if snapshot.sequence is None:
        raise ValueError("A sequence-aware snapshot with valid update ID is required")
    book = LocalOrderBook(snapshot.venue, snapshot.market, snapshot.symbol)
    book.load_snapshot(snapshot)
    previous = book.snapshot(snapshot.exchange_ts_ns, snapshot.receive_ts_ns, depth=depth)
    rows: list[dict[str, float | int]] = []
    seen = applied = stale = gaps = crossed = 0

    for delta in sorted(deltas, key=lambda event: (event.receive_ts_ns, event.last_update_id)):
        seen += 1
        try:
            changed = book.apply(delta)
        except SequenceGapError as exc:
            gaps += 1
            if "crossed" in str(exc).lower():
                crossed += 1
            break
        if not changed:
            stale += 1
            continue
        applied += 1
        current = book.snapshot(delta.exchange_ts_ns, delta.receive_ts_ns, depth=depth)
        features = book_snapshot_features(current, levels=depth)
        features.update({
            "exchange_ts_ns": int(delta.exchange_ts_ns),
            "receive_ts_ns": int(delta.receive_ts_ns),
            "sequence": int(delta.last_update_id),
            "l1_ofi": float(compute_l1_ofi(previous, current)),
            "latency_ms": (delta.receive_ts_ns - delta.exchange_ts_ns) / 1_000_000.0,
        })
        if include_multilevel_ofi:
            m_ofi = compute_multilevel_ofi(previous, current, levels=multilevel_depth)
            features.update(m_ofi)

        rows.append(features)
        previous = current

    return pd.DataFrame(rows), L2ReplayStats(
        deltas_seen=seen,
        deltas_applied=applied,
        stale_deltas=stale,
        sequence_gaps=gaps,
        crossed_books=crossed,
    )


def add_forward_mid_returns(
    frame: pd.DataFrame,
    horizons_seconds: tuple[int, ...] = (1, 5),
    timestamp_column: str = "exchange_ts_ns",
) -> pd.DataFrame:
    """Calculate causal forward mid-price percentage returns over specified second horizons.

    Uses searchsorted on sorted timestamps so only future events at or after the target horizon
    are matched, guaranteeing zero lookahead bias.
    """
    if frame.empty:
        return frame.copy()
    required = {timestamp_column, "mid"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Feature frame missing required columns: {sorted(missing)}")
    work = frame.sort_values(timestamp_column, kind="stable").reset_index(drop=True).copy()
    timestamps = work[timestamp_column].to_numpy(dtype="int64")
    mids = work["mid"].to_numpy(dtype=float)
    for seconds in horizons_seconds:
        targets = timestamps + seconds * 1_000_000_000
        indices = np.searchsorted(timestamps, targets, side="left")
        valid = indices < len(work)
        future = np.full(len(work), np.nan, dtype=float)
        future[valid] = mids[indices[valid]]
        work[f"forward_mid_return_{seconds}s"] = future / mids - 1.0
    return work


def correlation_or_none(left: pd.Series, right: pd.Series) -> float | None:
    """Compute Pearson correlation between two series or return None if insufficient variance."""
    aligned = pd.concat([left, right], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(aligned) < 3 or aligned.iloc[:, 0].std(ddof=1) == 0 or aligned.iloc[:, 1].std(ddof=1) == 0:
        return None
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))
