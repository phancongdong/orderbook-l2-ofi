"""Sequence-aware local limit-order-book reconstruction engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from orderbook_ofi.models import BookDelta, BookLevel, BookSnapshot


class SequenceGapError(RuntimeError):
    """Raised when an incremental feed cannot be applied without a sequence gap."""


@dataclass
class LocalOrderBook:
    """Deterministic, sequence-aware local Limit Order Book (LOB).

    Reconstructs the full Level-2 order book by maintaining bid and ask price ladders,
    applying sequence checks for market data feeds (e.g., Binance USD-M futures diff depth,
    BingX incremental depth), dropping stale updates, pruning 0-quantity price levels,
    and verifying crossed-book integrity.
    """
    venue: str
    market: str
    symbol: str
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    last_update_id: Optional[int] = None
    initialized: bool = False

    def load_snapshot(self, snapshot: BookSnapshot) -> None:
        """Initialize the local order book from a sequence-aware REST or WebSocket snapshot."""
        if snapshot.symbol.upper() != self.symbol.upper():
            raise ValueError(f"Snapshot symbol '{snapshot.symbol}' does not match local book '{self.symbol}'")
        if snapshot.sequence is None:
            raise ValueError("A sequence-aware snapshot with valid update ID is required")
        self.bids = {level.price: level.quantity for level in snapshot.bids if level.quantity > 0}
        self.asks = {level.price: level.quantity for level in snapshot.asks if level.quantity > 0}
        self.last_update_id = snapshot.sequence
        self.initialized = True
        self._validate_not_crossed()

    def apply(self, delta: BookDelta) -> bool:
        """Apply an incremental L2 delta update.

        Returns:
            bool: True if the delta was applied; False if the delta was stale (last_update_id <= current).

        Raises:
            RuntimeError: If called before initializing with a snapshot.
            ValueError: If the delta symbol doesn't match.
            SequenceGapError: If a sequence gap or crossed book is detected.
        """
        if not self.initialized or self.last_update_id is None:
            raise RuntimeError("Must load a snapshot before applying deltas")
        if delta.symbol.upper() != self.symbol.upper():
            raise ValueError(f"Delta symbol '{delta.symbol}' does not match local book '{self.symbol}'")
        if delta.last_update_id <= self.last_update_id:
            # Stale update already superseded by current book state
            return False

        expected = self.last_update_id + 1
        previous_matches = delta.previous_update_id == self.last_update_id
        range_bridges_snapshot = delta.first_update_id <= expected <= delta.last_update_id
        if not previous_matches and not range_bridges_snapshot:
            previous_detail = (
                f"pu={delta.previous_update_id}"
                if delta.previous_update_id is not None
                else "pu=missing"
            )
            raise SequenceGapError(
                f"{self.symbol}: expected pu={self.last_update_id} or an update range "
                f"containing {expected}, got {previous_detail}, "
                f"range=[{delta.first_update_id}, {delta.last_update_id}]"
            )

        self._apply_levels(self.bids, delta.bids)
        self._apply_levels(self.asks, delta.asks)
        self.last_update_id = delta.last_update_id
        self._validate_not_crossed()
        return True

    @staticmethod
    def _apply_levels(book: dict[float, float], levels: tuple[BookLevel, ...]) -> None:
        for level in levels:
            if level.quantity == 0:
                book.pop(level.price, None)
            else:
                book[level.price] = level.quantity

    def _validate_not_crossed(self) -> None:
        if self.bids and self.asks and max(self.bids) >= min(self.asks):
            best_bid = max(self.bids)
            best_ask = min(self.asks)
            raise SequenceGapError(
                f"{self.symbol}: reconstructed book is crossed (best_bid={best_bid} >= best_ask={best_ask})"
            )

    @property
    def best_bid(self) -> Optional[tuple[float, float]]:
        """Return (price, size) of best bid or None if book empty."""
        if not self.bids:
            return None
        price = max(self.bids)
        return price, self.bids[price]

    @property
    def best_ask(self) -> Optional[tuple[float, float]]:
        """Return (price, size) of best ask or None if book empty."""
        if not self.asks:
            return None
        price = min(self.asks)
        return price, self.asks[price]

    @property
    def mid_price(self) -> Optional[float]:
        """Current mid price (best_bid + best_ask) / 2."""
        bb = self.best_bid
        ba = self.best_ask
        if bb is None or ba is None:
            return None
        return (bb[0] + ba[0]) / 2.0

    @property
    def spread(self) -> Optional[float]:
        """Current top spread (best_ask - best_bid)."""
        bb = self.best_bid
        ba = self.best_ask
        if bb is None or ba is None:
            return None
        return ba[0] - bb[0]

    def snapshot(self, exchange_ts_ns: int, receive_ts_ns: int, depth: int = 20) -> BookSnapshot:
        """Export a canonical BookSnapshot containing the top N bid and ask levels."""
        if not self.initialized or self.last_update_id is None:
            raise RuntimeError("Local order book is not initialized")
        bids = tuple(
            BookLevel(price, quantity)
            for price, quantity in sorted(self.bids.items(), reverse=True)[:depth]
        )
        asks = tuple(
            BookLevel(price, quantity)
            for price, quantity in sorted(self.asks.items())[:depth]
        )
        return BookSnapshot(
            venue=self.venue,
            market=self.market,
            symbol=self.symbol,
            exchange_ts_ns=exchange_ts_ns,
            receive_ts_ns=receive_ts_ns,
            bids=bids,
            asks=asks,
            sequence=self.last_update_id,
            source="incremental_rebuild",
        )
