"""Example 5: Live Real-Time Binance USD-M Futures L2 Reconstruction & OFI.

Demonstrates:
1. Connecting to Binance USD-M Futures WebSocket public stream.
2. Bootstrapping with a REST order book snapshot.
3. Streaming incremental 100ms depth updates and trades.
4. Reconstructing the live LOB with LocalOrderBook in real-time.
5. Computing tick-by-tick Cont's Level-1 OFI and microprice.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orderbook_ofi.book import LocalOrderBook, SequenceGapError
from orderbook_ofi.collectors.binance import BinanceFuturesCollector
from orderbook_ofi.models import BookDelta, BookSnapshot, TradeEvent
from orderbook_ofi.ofi import book_snapshot_features, compute_l1_ofi


def main():
    print("=" * 70)
    print("Example 5: Live Real-Time Binance USD-M Futures LOB & OFI Stream")
    print("=" * 70)
    print("Connecting to wss://fstream.binance.com for BTCUSDT (100ms depth)...")
    print("Press Ctrl+C to stop.\n")

    book = LocalOrderBook(venue="binance", market="futures_um", symbol="BTCUSDT")
    collector = BinanceFuturesCollector(
        symbols=["BTCUSDT"],
        collect_trades=True,
        collect_depth=True,
        depth_limit=100,
    )

    previous_snapshot: BookSnapshot | None = None
    event_count = 0

    def on_event(event):
        nonlocal previous_snapshot, event_count

        if isinstance(event, BookSnapshot):
            book.load_snapshot(event)
            previous_snapshot = book.snapshot(event.exchange_ts_ns, event.receive_ts_ns, depth=5)
            bb, ba = book.best_bid, book.best_ask
            print(f"[SNAPSHOT] Initialized from REST | UpdateId={event.sequence} | "
                  f"Bid: {bb[0]:,.1f} ({bb[1]}) x Ask: {ba[0]:,.1f} ({ba[1]})")

        elif isinstance(event, BookDelta):
            if not book.initialized:
                return
            try:
                applied = book.apply(event)
            except SequenceGapError as exc:
                print(f"[SEQUENCE GAP] {exc} -> Re-initialization required.")
                return

            if not applied:
                return

            event_count += 1
            curr_snapshot = book.snapshot(event.exchange_ts_ns, event.receive_ts_ns, depth=5)
            if previous_snapshot is not None:
                ofi = compute_l1_ofi(previous_snapshot, curr_snapshot)
                feats = book_snapshot_features(curr_snapshot, levels=5)
                print(f"[{event_count:03d}] L1 OFI: {ofi:+8.3f} BTC | "
                      f"Mid: ${feats['mid']:>9,.2f} | "
                      f"Microprice: ${feats['microprice']:>9,.2f} | "
                      f"Spread: {feats['spread_bps']:>4.1f} bps | "
                      f"Top OBI: {feats['top_imbalance']:>+5.2f}")
            previous_snapshot = curr_snapshot

        elif isinstance(event, TradeEvent):
            pass

    try:
        # Collect for 10 seconds or 20 book updates for demonstration
        stats = collector.collect(on_event, duration_seconds=10.0, max_events=25)
        print("\n" + "=" * 70)
        print(f"Finished: {stats.messages} messages, {stats.events} events in {stats.duration_seconds:.2f}s")
        print("=" * 70)
    except KeyboardInterrupt:
        print("\n[!] Stopped by user.")


if __name__ == "__main__":
    main()
