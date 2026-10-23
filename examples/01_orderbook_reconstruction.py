"""Example 1: Sequence-Aware Level-2 Limit Order Book (LOB) Reconstruction.

This example illustrates:
1. Creating a LocalOrderBook for BTCUSDT.
2. Initializing from a REST snapshot.
3. Applying incremental deltas (order placement, amendment, cancellation).
4. Pruning empty (0 quantity) price levels.
5. Detecting sequence gaps and preventing crossed books.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to python path for standalone execution
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orderbook_ofi.book import LocalOrderBook, SequenceGapError
from orderbook_ofi.models import BookDelta, BookSnapshot


def main():
    print("=" * 70)
    print("Example 1: Sequence-Aware Level-2 Order Book Reconstruction")
    print("=" * 70)

    # 1. Initialize empty order book for Binance BTCUSDT
    book = LocalOrderBook(venue="binance", market="futures_um", symbol="BTCUSDT")
    print(f"Initialized book: venue={book.venue}, symbol={book.symbol}, ready={book.initialized}")

    # 2. Load initial REST snapshot (sequence = 1000)
    snapshot = BookSnapshot.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_000,
        receive_ts_ns=1_700_000_000_050_000_000,
        bids=[
            [65000.0, 1.5],
            [64990.0, 3.2],
            [64980.0, 5.0],
        ],
        asks=[
            [65010.0, 1.2],
            [65020.0, 2.8],
            [65030.0, 4.5],
        ],
        sequence=1000,
        source="rest_bootstrap",
    )
    book.load_snapshot(snapshot)
    print("\n[+] Loaded snapshot (update_id=1000):")
    print(f"    Best Bid: ${book.best_bid[0]:,.2f} (qty: {book.best_bid[1]})")
    print(f"    Best Ask: ${book.best_ask[0]:,.2f} (qty: {book.best_ask[1]})")
    print(f"    Mid Price: ${book.mid_price:,.2f} | Spread: ${book.spread:,.2f}")

    # 3. Apply first incremental delta that bridges snapshot (first_update_id=995, last_update_id=1002)
    #    - Update 65000.0 bid size to 2.5 (addition of limit orders)
    #    - Add new best ask at 65005.0 with size 0.8 (aggressive ask tightens spread)
    delta1 = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_100,
        receive_ts_ns=1_700_000_000_150_000_000,
        first_update_id=995,
        last_update_id=1002,
        previous_update_id=994,
        bids=[[65000.0, 2.5]],
        asks=[[65005.0, 0.8]],
    )
    applied = book.apply(delta1)
    print(f"\n[+] Applied Delta 1 (u=1002, bridged snapshot): {applied}")
    print(f"    Best Bid: ${book.best_bid[0]:,.2f} (qty: {book.best_bid[1]})")
    print(f"    Best Ask: ${book.best_ask[0]:,.2f} (qty: {book.best_ask[1]})")
    print(f"    New Mid:  ${book.mid_price:,.2f} | New Spread: ${book.spread:,.2f}")

    # 4. Apply second delta (u=1005, pu=1002):
    #    - Cancel 65005.0 ask (quantity = 0.0 -> removed from book)
    delta2 = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_200,
        receive_ts_ns=1_700_000_000_250_000_000,
        first_update_id=1003,
        last_update_id=1005,
        previous_update_id=1002,
        bids=[],
        asks=[[65005.0, 0.0]],  # Cancel level
    )
    book.apply(delta2)
    print("\n[+] Applied Delta 2 (Ask at 65005.0 cancelled with qty=0.0):")
    print(f"    Best Ask reverted to: ${book.best_ask[0]:,.2f} (qty: {book.best_ask[1]})")

    # 5. Stale delta detection (last_update_id <= book.last_update_id)
    stale_delta = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_050,
        receive_ts_ns=1_700_000_000_060_000_000,
        first_update_id=1000,
        last_update_id=1004,
        previous_update_id=999,
        bids=[[65000.0, 10.0]],
        asks=[],
    )
    result = book.apply(stale_delta)
    print(f"\n[+] Stale Delta (u=1004 <= current 1005): correctly dropped -> applied={result}")

    # 6. Sequence gap detection (expected 1006, got 1010)
    gap_delta = BookDelta.from_levels(
        venue="binance",
        market="futures_um",
        symbol="BTCUSDT",
        exchange_ts=1_700_000_000_400,
        receive_ts_ns=1_700_000_000_450_000_000,
        first_update_id=1009,
        last_update_id=1010,
        previous_update_id=1008,
        bids=[[65002.0, 1.0]],
        asks=[],
    )
    try:
        book.apply(gap_delta)
    except SequenceGapError as exc:
        print(f"\n[+] Sequence Gap caught successfully:")
        print(f"    {exc}")

    # 7. Export canonical snapshot
    exported = book.snapshot(exchange_ts_ns=1_700_000_000_300, receive_ts_ns=1_700_000_000_350_000_000, depth=5)
    print(f"\n[+] Exported Snapshot depth={exported.to_record()['depth']}, seq={exported.sequence}")
    print("=" * 70)


if __name__ == "__main__":
    main()
