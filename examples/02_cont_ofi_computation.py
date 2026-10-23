"""Example 2: Cont, Kukanov & Stoikov (2014) Order Flow Imbalance (OFI).

Demonstrates the mathematical mechanics of Level-1 OFI:
Reference:
    Cont, R., Kukanov, A., & Stoikov, S. (2014).
    The Price Impact of Order Book Events.
    Journal of Financial Econometrics, 12(1), 47-88.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orderbook_ofi.models import BookSnapshot
from orderbook_ofi.ofi import book_snapshot_features, compute_l1_ofi


def print_state(label: str, snapshot: BookSnapshot):
    feats = book_snapshot_features(snapshot, levels=2)
    bb, ba = snapshot.bids[0], snapshot.asks[0]
    print(f"\n--- {label} ---")
    print(f"  Best Bid: ${bb.price:.2f} x {bb.quantity:.2f} | Best Ask: ${ba.price:.2f} x {ba.quantity:.2f}")
    print(f"  Mid Price: ${feats['mid']:.2f} | Spread: ${feats['spread']:.2f} ({feats['spread_bps']:.1f} bps)")
    print(f"  Microprice: ${feats['microprice']:.4f} | Top Imbalance (OBI): {feats['top_imbalance']:+.3f}")


def main():
    print("=" * 70)
    print("Example 2: Cont's Order Flow Imbalance (OFI) Formulation & Scenarios")
    print("=" * 70)

    # Initial State (t = 0)
    t0 = BookSnapshot.from_levels(
        venue="binance", market="futures_um", symbol="ETHUSDT",
        exchange_ts=1_700_000_000_000, receive_ts_ns=1_700_000_000_000_000_000,
        bids=[[3000.0, 10.0], [2999.0, 20.0]],
        asks=[[3001.0, 8.0], [3002.0, 15.0]],
        sequence=1,
    )
    print_state("State 0 (Baseline)", t0)

    # Scenario A: New limit buy orders placed at existing best bid (+5 ETH)
    # Bid price unchanged ($3000), quantity increases from 10 -> 15.
    t1_add_bid = BookSnapshot.from_levels(
        venue="binance", market="futures_um", symbol="ETHUSDT",
        exchange_ts=1_700_000_000_100, receive_ts_ns=1_700_000_000_100_000_000,
        bids=[[3000.0, 15.0], [2999.0, 20.0]],
        asks=[[3001.0, 8.0], [3002.0, 15.0]],
        sequence=2,
    )
    ofi_a = compute_l1_ofi(t0, t1_add_bid)
    print_state("Scenario A: Limit Buy Add (+5 ETH at $3000)", t1_add_bid)
    print(f"  => OFI(t0 -> t1_A) = {ofi_a:+.2f} ETH (Positive: net buying pressure)")

    # Scenario B: Aggressive buyer steps in, best bid ticks UP ($3000.0 -> $3000.5 with 4 ETH)
    t1_bid_up = BookSnapshot.from_levels(
        venue="binance", market="futures_um", symbol="ETHUSDT",
        exchange_ts=1_700_000_000_200, receive_ts_ns=1_700_000_000_200_000_000,
        bids=[[3000.5, 4.0], [3000.0, 10.0]],
        asks=[[3001.0, 8.0], [3002.0, 15.0]],
        sequence=3,
    )
    ofi_b = compute_l1_ofi(t0, t1_bid_up)
    print_state("Scenario B: Bid Ticked Up ($3000 -> $3000.5, size=4 ETH)", t1_bid_up)
    print(f"  => OFI(t0 -> t1_B) = {ofi_b:+.2f} ETH (Entire new bid size counts as positive flow)")

    # Scenario C: Market buy executes through the best ask ($3001.0 consumed, new ask is $3002.0)
    t1_ask_lifted = BookSnapshot.from_levels(
        venue="binance", market="futures_um", symbol="ETHUSDT",
        exchange_ts=1_700_000_000_300, receive_ts_ns=1_700_000_000_300_000_000,
        bids=[[3000.0, 10.0], [2999.0, 20.0]],
        asks=[[3002.0, 15.0], [3003.0, 30.0]],
        sequence=4,
    )
    ofi_c = compute_l1_ofi(t0, t1_ask_lifted)
    print_state("Scenario C: Ask Lifted ($3001 consumed, new ask $3002)", t1_ask_lifted)
    print(f"  => OFI(t0 -> t1_C) = {ofi_c:+.2f} ETH (Old ask of 8 ETH cleared -> strong buy signal)")

    # Scenario D: Aggressive seller executes / cancels bid, best bid ticks DOWN ($3000 -> $2999)
    t1_bid_down = BookSnapshot.from_levels(
        venue="binance", market="futures_um", symbol="ETHUSDT",
        exchange_ts=1_700_000_000_400, receive_ts_ns=1_700_000_000_400_000_000,
        bids=[[2999.0, 20.0], [2998.0, 15.0]],
        asks=[[3001.0, 8.0], [3002.0, 15.0]],
        sequence=5,
    )
    ofi_d = compute_l1_ofi(t0, t1_bid_down)
    print_state("Scenario D: Bid Depleted/Ticked Down ($3000 -> $2999)", t1_bid_down)
    print(f"  => OFI(t0 -> t1_D) = {ofi_d:+.2f} ETH (Negative: strong selling pressure)")

    print("\n" + "=" * 70)
    print("Summary of Cont's OFI Logic:")
    print("  Bid Price UP   => +q_b(t)            | Ask Price UP   => +q_a(t-1)")
    print("  Bid Price SAME => q_b(t) - q_b(t-1)  | Ask Price SAME => q_a(t-1) - q_a(t)")
    print("  Bid Price DOWN => -q_b(t-1)          | Ask Price DOWN => -q_a(t)")
    print("  Net OFI = Bid Component + Ask Component")
    print("=" * 70)


if __name__ == "__main__":
    main()
