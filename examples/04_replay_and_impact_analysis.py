"""Example 4: Offline L2 Replay and Empirical Price Impact Analysis.

Demonstrates:
1. Replaying a sequence of L2 deltas against a bootstrap snapshot.
2. Generating point-in-time features (L1 OFI, Microprice, Spread, OBI).
3. Calculating causal forward mid-price returns at 1-second and 5-second horizons.
4. Testing Cont's empirical hypothesis: contemporaneous and predictive price impact of OFI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orderbook_ofi.models import BookDelta, BookSnapshot
from orderbook_ofi.replay import add_forward_mid_returns, correlation_or_none, replay_l2


def generate_synthetic_l2_stream():
    """Generate a 50-tick sequence of L2 order book events."""
    base_price = 100.0
    snapshot = BookSnapshot.from_levels(
        venue="binance", market="futures_um", symbol="BTCUSDT",
        exchange_ts=1_000_000_000, receive_ts_ns=1_000_050_000,
        bids=[[base_price - 0.1, 10.0], [base_price - 0.2, 20.0]],
        asks=[[base_price + 0.1, 10.0], [base_price + 0.2, 20.0]],
        sequence=100,
    )

    deltas = []
    current_bid = base_price - 0.1
    current_ask = base_price + 0.1
    rng = np.random.default_rng(42)

    for i in range(1, 51):
        # Every 100ms
        ts = 1_000_000_000 + i * 100_000_000
        # Flow shock: drift up or down
        direction = 1 if (i % 10 < 6) else -1
        qty_bid = float(np.round(10.0 + direction * rng.uniform(1.0, 5.0), 2))
        qty_ask = float(np.round(10.0 - direction * rng.uniform(1.0, 5.0), 2))

        # Occasionally shift price
        if i % 7 == 0:
            current_bid += direction * 0.05
            current_ask += direction * 0.05

        deltas.append(BookDelta.from_levels(
            venue="binance", market="futures_um", symbol="BTCUSDT",
            exchange_ts=ts,
            receive_ts_ns=ts + 5_000_000,  # 5ms network latency
            first_update_id=100 + i,
            last_update_id=100 + i,
            previous_update_id=100 + i - 1,
            bids=[[current_bid, max(1.0, qty_bid)]],
            asks=[[current_ask, max(1.0, qty_ask)]],
        ))

    return snapshot, deltas


def main():
    print("=" * 70)
    print("Example 4: Deterministic L2 Replay & Price Impact Regression")
    print("=" * 70)

    snapshot, deltas = generate_synthetic_l2_stream()
    print(f"[+] Loaded 1 bootstrap snapshot and {len(deltas)} incremental deltas.")

    # 1. Execute replay
    features, stats = replay_l2(snapshot, deltas, depth=10)
    print("\n[+] Replay Statistics:")
    print(f"    Deltas Seen:     {stats.deltas_seen}")
    print(f"    Deltas Applied:  {stats.deltas_applied}")
    print(f"    Stale Deltas:    {stats.stale_deltas}")
    print(f"    Sequence Gaps:   {stats.sequence_gaps}")
    print(f"    Crossed Books:   {stats.crossed_books}")

    # 2. Add causal forward mid returns at 1-second and 2-second horizons
    features = add_forward_mid_returns(features, horizons_seconds=(1, 2))

    # 3. Inspect sample rows
    print("\n[+] Reconstructed Event Sample (first 5 ticks):")
    cols = ["sequence", "mid", "spread_bps", "top_imbalance", "l1_ofi", "forward_mid_return_1s"]
    sample = features[cols].head(5)
    print(sample.to_string(index=False))

    # 4. Measure correlations with forward price moves
    corr_ofi_fwd1s = correlation_or_none(features["l1_ofi"], features["forward_mid_return_1s"])
    corr_obi_fwd1s = correlation_or_none(features["top_imbalance"], features["forward_mid_return_1s"])

    print("\n[+] Empirical Impact Correlations with Forward 1s Return:")
    print(f"    Corr(L1 OFI, Forward 1s Mid Return):        {corr_ofi_fwd1s:+.4f}" if corr_ofi_fwd1s is not None else "    N/A")
    print(f"    Corr(Top Imbalance, Forward 1s Mid Return): {corr_obi_fwd1s:+.4f}" if corr_obi_fwd1s is not None else "    N/A")

    print("\nKey Insight from Rama Cont et al. (2014):")
    print("  While static Order Book Imbalance (OBI) reflects currently resting depth,")
    print("  Order Flow Imbalance (OFI) accounts for the dynamic arrival, amendment,")
    print("  and cancellation of orders, exhibiting a significantly stronger contemporaneous")
    print("  linear relationship with mid-price changes.")
    print("=" * 70)


if __name__ == "__main__":
    main()
