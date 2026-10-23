"""Example 3: Multi-Level Order Flow Imbalance (M-OFI).

Demonstrates computing OFI across multiple price levels (L1, L2, L3, ...)
and synthesizing an integrated multi-level OFI signal.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orderbook_ofi.models import BookSnapshot
from orderbook_ofi.ofi import compute_l1_ofi, compute_multilevel_ofi


def main():
    print("=" * 70)
    print("Example 3: Multi-Level Order Flow Imbalance (M-OFI)")
    print("=" * 70)

    # Initial snapshot with 5 levels of depth
    t0 = BookSnapshot.from_levels(
        venue="binance", market="futures_um", symbol="SOLUSDT",
        exchange_ts=1_700_000_000_000, receive_ts_ns=1_700_000_000_000_000_000,
        bids=[
            [150.0, 100.0],
            [149.9, 200.0],
            [149.8, 300.0],
            [149.7, 400.0],
            [149.6, 500.0],
        ],
        asks=[
            [150.1, 120.0],
            [150.2, 250.0],
            [150.3, 350.0],
            [150.4, 450.0],
            [150.5, 600.0],
        ],
        sequence=1,
    )

    # State at t1:
    # Level 1: Bid size increases (100 -> 150), Ask size unchanged (120)
    # Level 2: Bid size increases (200 -> 280), Ask size decreases (250 -> 180)
    # Level 3: Bid price ticks up to 149.85 with 320 size
    t1 = BookSnapshot.from_levels(
        venue="binance", market="futures_um", symbol="SOLUSDT",
        exchange_ts=1_700_000_000_100, receive_ts_ns=1_700_000_000_100_000_000,
        bids=[
            [150.0, 150.0],
            [149.9, 280.0],
            [149.85, 320.0],
            [149.7, 400.0],
            [149.6, 500.0],
        ],
        asks=[
            [150.1, 120.0],
            [150.2, 180.0],
            [150.3, 350.0],
            [150.4, 450.0],
            [150.5, 600.0],
        ],
        sequence=2,
    )

    # 1. Level-1 OFI (Best quotes only)
    l1 = compute_l1_ofi(t0, t1)
    print(f"\n[+] Level-1 OFI (Cont 2014): {l1:+.2f}")
    print("    Captures only top of book: Delta Bid L1 (+50) + Delta Ask L1 (0) = +50.0")

    # 2. Multi-Level OFI (Top 5 levels)
    m_ofi = compute_multilevel_ofi(t0, t1, levels=5)
    print("\n[+] Multi-Level OFI Breakdown:")
    for k in range(1, 6):
        key = f"l{k}_ofi"
        print(f"    Level {k} OFI: {m_ofi[key]:+8.2f}")

    print(f"\n[+] Integrated OFI (Harmonic 1/k Weighted): {m_ofi['integrated_ofi']:+.2f}")
    print("\nWhy Multi-Level OFI matters:")
    print("  Large algorithmic participants often stage liquidity at deeper levels")
    print("  (L2 - L5). While L1 OFI captures immediate tick impact, Multi-Level OFI")
    print("  detects book replenishment, layering, and deeper queue cancellations.")
    print("=" * 70)


if __name__ == "__main__":
    main()
