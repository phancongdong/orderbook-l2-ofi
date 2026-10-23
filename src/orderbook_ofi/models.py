"""Normalized, venue-aware limit order book and trade event models."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence


class AggressorSide(str, Enum):
    """Normalized aggressor (taker) order side."""
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


def timestamp_to_ns(value: int | float | str) -> int:
    """Normalize second, millisecond, microsecond, or nanosecond epochs to nanoseconds."""
    timestamp = int(value)
    magnitude = abs(timestamp)
    if magnitude < 100_000_000_000:
        return timestamp * 1_000_000_000
    if magnitude < 100_000_000_000_000:
        return timestamp * 1_000_000
    if magnitude < 100_000_000_000_000_000:
        return timestamp * 1_000
    return timestamp


def _positive_finite(value: float, field_name: str, allow_zero: bool = False) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    if allow_zero:
        if value < 0:
            raise ValueError(f"{field_name} must be non-negative")
    elif value <= 0:
        raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True)
class BookLevel:
    """A single price and resting depth level in an order book."""
    price: float
    quantity: float

    def __post_init__(self) -> None:
        _positive_finite(float(self.price), "price")
        _positive_finite(float(self.quantity), "quantity", allow_zero=True)

    @classmethod
    def from_value(cls, value: Sequence[Any] | Mapping[str, Any]) -> "BookLevel":
        if isinstance(value, Mapping):
            price = value.get("price", value.get("p"))
            quantity = value.get("quantity", value.get("qty", value.get("v")))
        else:
            price, quantity = value[0], value[1]
        return cls(price=float(price), quantity=float(quantity))

    def as_pair(self) -> list[float]:
        return [self.price, self.quantity]


@dataclass(frozen=True)
class TradeEvent:
    """Normalized public market trade."""
    venue: str
    market: str
    symbol: str
    exchange_ts_ns: int
    receive_ts_ns: int
    trade_id: str
    price: float
    quantity: float
    quote_quantity: float
    aggressor_side: AggressorSide
    buyer_is_maker: Optional[bool] = None
    sequence: Optional[int] = None
    source: str = "websocket"
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False)

    event_type: str = field(default="trade", init=False)

    def __post_init__(self) -> None:
        _positive_finite(float(self.price), "price")
        _positive_finite(float(self.quantity), "quantity")
        _positive_finite(float(self.quote_quantity), "quote_quantity", allow_zero=True)
        if self.exchange_ts_ns <= 0 or self.receive_ts_ns <= 0:
            raise ValueError("timestamps must be positive")

    @classmethod
    def from_maker_flag(
        cls,
        *,
        venue: str,
        market: str,
        symbol: str,
        exchange_ts: int | float | str,
        receive_ts_ns: int,
        trade_id: str | int,
        price: float | str,
        quantity: float | str,
        buyer_is_maker: bool,
        quote_quantity: Optional[float | str] = None,
        sequence: Optional[int] = None,
        source: str = "websocket",
        raw: Optional[Mapping[str, Any]] = None,
    ) -> "TradeEvent":
        price_f = float(price)
        qty_f = float(quantity)
        quote_f = float(quote_quantity) if quote_quantity is not None else price_f * qty_f
        aggressor = AggressorSide.SELL if buyer_is_maker else AggressorSide.BUY
        return cls(
            venue=venue,
            market=market,
            symbol=symbol.upper(),
            exchange_ts_ns=timestamp_to_ns(exchange_ts),
            receive_ts_ns=receive_ts_ns,
            trade_id=str(trade_id),
            price=price_f,
            quantity=qty_f,
            quote_quantity=quote_f,
            aggressor_side=aggressor,
            buyer_is_maker=buyer_is_maker,
            sequence=sequence,
            source=source,
            raw=raw or {},
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "venue": self.venue,
            "market": self.market,
            "symbol": self.symbol,
            "exchange_ts_ns": self.exchange_ts_ns,
            "receive_ts_ns": self.receive_ts_ns,
            "trade_id": self.trade_id,
            "price": self.price,
            "quantity": self.quantity,
            "quote_quantity": self.quote_quantity,
            "aggressor_side": self.aggressor_side.value,
            "buyer_is_maker": self.buyer_is_maker,
            "sequence": self.sequence,
            "source": self.source,
            "raw_json": json.dumps(self.raw, separators=(",", ":"), sort_keys=True),
        }


@dataclass(frozen=True)
class BookSnapshot:
    """Full or sampled Level-2 book snapshot sorted canonically."""
    venue: str
    market: str
    symbol: str
    exchange_ts_ns: int
    receive_ts_ns: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    sequence: Optional[int] = None
    source: str = "sampled_snapshot"
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False)

    event_type: str = field(default="book_snapshot", init=False)

    def __post_init__(self) -> None:
        if self.exchange_ts_ns <= 0 or self.receive_ts_ns <= 0:
            raise ValueError("timestamps must be positive")
        if any(self.bids[i].price < self.bids[i + 1].price for i in range(len(self.bids) - 1)):
            raise ValueError("bids must be sorted descending")
        if any(self.asks[i].price > self.asks[i + 1].price for i in range(len(self.asks) - 1)):
            raise ValueError("asks must be sorted ascending")
        if self.bids and self.asks and self.bids[0].price >= self.asks[0].price:
            raise ValueError("book snapshot is crossed")

    @classmethod
    def from_levels(
        cls,
        *,
        venue: str,
        market: str,
        symbol: str,
        exchange_ts: int | float | str,
        receive_ts_ns: int,
        bids: Iterable[Sequence[Any] | Mapping[str, Any]],
        asks: Iterable[Sequence[Any] | Mapping[str, Any]],
        sequence: Optional[int] = None,
        source: str = "sampled_snapshot",
        raw: Optional[Mapping[str, Any]] = None,
    ) -> "BookSnapshot":
        bid_levels = tuple(sorted((BookLevel.from_value(value) for value in bids), key=lambda x: x.price, reverse=True))
        ask_levels = tuple(sorted((BookLevel.from_value(value) for value in asks), key=lambda x: x.price))
        return cls(
            venue=venue,
            market=market,
            symbol=symbol.upper(),
            exchange_ts_ns=timestamp_to_ns(exchange_ts),
            receive_ts_ns=receive_ts_ns,
            bids=bid_levels,
            asks=ask_levels,
            sequence=sequence,
            source=source,
            raw=raw or {},
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "venue": self.venue,
            "market": self.market,
            "symbol": self.symbol,
            "exchange_ts_ns": self.exchange_ts_ns,
            "receive_ts_ns": self.receive_ts_ns,
            "sequence": self.sequence,
            "source": self.source,
            "depth": min(len(self.bids), len(self.asks)),
            "bids_json": json.dumps([level.as_pair() for level in self.bids], separators=(",", ":")),
            "asks_json": json.dumps([level.as_pair() for level in self.asks], separators=(",", ":")),
            "raw_json": json.dumps(self.raw, separators=(",", ":"), sort_keys=True),
        }


@dataclass(frozen=True)
class BookDelta:
    """Incremental Level-2 limit order book update containing changed price levels."""
    venue: str
    market: str
    symbol: str
    exchange_ts_ns: int
    receive_ts_ns: int
    first_update_id: int
    last_update_id: int
    previous_update_id: Optional[int]
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    source: str = "incremental_l2"
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False)

    event_type: str = field(default="book_delta", init=False)

    def __post_init__(self) -> None:
        if self.first_update_id > self.last_update_id:
            raise ValueError("first_update_id cannot exceed last_update_id")
        if self.exchange_ts_ns <= 0 or self.receive_ts_ns <= 0:
            raise ValueError("timestamps must be positive")

    @classmethod
    def from_levels(
        cls,
        *,
        venue: str,
        market: str,
        symbol: str,
        exchange_ts: int | float | str,
        receive_ts_ns: int,
        first_update_id: int,
        last_update_id: int,
        previous_update_id: Optional[int],
        bids: Iterable[Sequence[Any] | Mapping[str, Any]],
        asks: Iterable[Sequence[Any] | Mapping[str, Any]],
        raw: Optional[Mapping[str, Any]] = None,
    ) -> "BookDelta":
        return cls(
            venue=venue,
            market=market,
            symbol=symbol.upper(),
            exchange_ts_ns=timestamp_to_ns(exchange_ts),
            receive_ts_ns=receive_ts_ns,
            first_update_id=int(first_update_id),
            last_update_id=int(last_update_id),
            previous_update_id=int(previous_update_id) if previous_update_id is not None else None,
            bids=tuple(BookLevel.from_value(value) for value in bids),
            asks=tuple(BookLevel.from_value(value) for value in asks),
            raw=raw or {},
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "venue": self.venue,
            "market": self.market,
            "symbol": self.symbol,
            "exchange_ts_ns": self.exchange_ts_ns,
            "receive_ts_ns": self.receive_ts_ns,
            "first_update_id": self.first_update_id,
            "last_update_id": self.last_update_id,
            "previous_update_id": self.previous_update_id,
            "source": self.source,
            "bids_json": json.dumps([level.as_pair() for level in self.bids], separators=(",", ":")),
            "asks_json": json.dumps([level.as_pair() for level in self.asks], separators=(",", ":")),
            "raw_json": json.dumps(self.raw, separators=(",", ":"), sort_keys=True),
        }


NormalizedEvent = TradeEvent | BookSnapshot | BookDelta


def event_to_record(event: NormalizedEvent | Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(event, "to_record"):
        return event.to_record()
    return dict(event)
