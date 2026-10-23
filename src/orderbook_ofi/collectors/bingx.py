"""BingX perpetual swap trade and sampled/incremental depth WebSocket collector."""
from __future__ import annotations

import gzip
import json
import uuid
from typing import Any, Iterable, Mapping

from websockets.sync.client import ClientConnection

from orderbook_ofi.collectors.base import WebSocketCollector
from orderbook_ofi.models import BookDelta, BookSnapshot, NormalizedEvent, TradeEvent


class BingXCollector(WebSocketCollector):
    venue = "bingx"
    market = "perpetual"

    def __init__(
        self,
        symbols: Iterable[str],
        *,
        collect_trades: bool = True,
        collect_depth: bool = True,
        depth_mode: str = "incremental",
        depth_level: int = 20,
        depth_interval_ms: int = 200,
        websocket_url: str = "wss://open-api-swap.bingx.com/swap-market",
        **kwargs,
    ) -> None:
        super().__init__(symbols, **kwargs)
        if not collect_trades and not collect_depth:
            raise ValueError("Enable trades, depth, or both")
        if depth_mode not in {"incremental", "snapshot"}:
            raise ValueError("BingX depth_mode must be 'incremental' or 'snapshot'")
        if depth_level not in {5, 10, 20, 50, 100}:
            raise ValueError("BingX depth_level must be 5, 10, 20, 50, or 100")
        if depth_interval_ms not in {200, 500}:
            raise ValueError("BingX depth interval must be 200 or 500 ms")
        self.collect_trades = collect_trades
        self.collect_depth = collect_depth
        self.depth_mode = depth_mode
        self.depth_level = depth_level
        self.depth_interval_ms = depth_interval_ms
        self._websocket_url = websocket_url

    @property
    def websocket_url(self) -> str:
        return self._websocket_url

    def on_connected(self, websocket: ClientConnection) -> Iterable[NormalizedEvent]:
        for symbol in self.symbols:
            if self.collect_trades:
                websocket.send(json.dumps({
                    "id": str(uuid.uuid4()),
                    "reqType": "sub",
                    "dataType": f"{symbol}@trade",
                }))
            if self.collect_depth:
                data_type = (
                    f"{symbol}@incrDepth"
                    if self.depth_mode == "incremental"
                    else f"{symbol}@depth{self.depth_level}@{self.depth_interval_ms}ms"
                )
                websocket.send(json.dumps({
                    "id": str(uuid.uuid4()),
                    "reqType": "sub",
                    "dataType": data_type,
                }))
        return ()

    def decode_message(self, message: str | bytes) -> str:
        if isinstance(message, str):
            return message
        try:
            return gzip.decompress(message).decode("utf-8")
        except (OSError, EOFError):
            return message.decode("utf-8")

    def handle_heartbeat(self, message: str, websocket: ClientConnection) -> bool:
        if message == "Ping":
            websocket.send("Pong")
            return True
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return False
        if isinstance(payload, Mapping) and "ping" in payload:
            websocket.send(json.dumps({"pong": payload["ping"]}))
            return True
        return False

    @staticmethod
    def _symbol_from_type(data_type: str) -> str:
        return data_type.split("@", 1)[0].upper()

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1"}:
                return True
            if normalized in {"false", "0"}:
                return False
        return bool(value)

    def parse_message(self, message: str, receive_ts_ns: int) -> list[NormalizedEvent]:
        payload = json.loads(message)
        if not isinstance(payload, Mapping) or payload.get("code", 0) not in {0, None}:
            return []
        data_type = str(payload.get("dataType", ""))
        data = payload.get("data")
        if data is None:
            return []
        rows = data if isinstance(data, list) else [data]
        symbol_from_type = self._symbol_from_type(data_type) if data_type else ""
        events: list[NormalizedEvent] = []

        if "@trade" in data_type:
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                buyer_is_maker = self._as_bool(row.get("m", row.get("isBuyerMaker")))
                events.append(TradeEvent.from_maker_flag(
                    venue=self.venue,
                    market=self.market,
                    symbol=str(row.get("s", symbol_from_type)),
                    exchange_ts=row.get("T", row.get("time", row.get("E", receive_ts_ns))),
                    receive_ts_ns=receive_ts_ns,
                    trade_id=row.get(
                        "id",
                        row.get("tradeId", row.get("t", f"{receive_ts_ns}-{len(events)}")),
                    ),
                    price=row.get("p", row.get("price")),
                    quantity=row.get("v", row.get("q", row.get("qty"))),
                    quote_quantity=row.get("quoteQty"),
                    buyer_is_maker=buyer_is_maker,
                    raw=row,
                ))
            return events

        if "@depth" in data_type:
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                bids = row.get("bids", row.get("b", []))
                asks = row.get("asks", row.get("a", []))
                events.append(BookSnapshot.from_levels(
                    venue=self.venue,
                    market=self.market,
                    symbol=str(row.get("s", symbol_from_type)),
                    exchange_ts=row.get("T", row.get("ts", payload.get("ts", receive_ts_ns))),
                    receive_ts_ns=receive_ts_ns,
                    bids=bids,
                    asks=asks,
                    sequence=None,
                    source="sampled_snapshot",
                    raw=row,
                ))
            return events

        if "@incrDepth" in data_type:
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                last_update_id = int(row["lastUpdateId"])
                bids = row.get("bids", row.get("b", []))
                asks = row.get("asks", row.get("a", []))
                exchange_ts = row.get(
                    "T",
                    row.get("time", row.get("ts", payload.get("timestamp", receive_ts_ns))),
                )
                if row.get("action") == "all":
                    events.append(BookSnapshot.from_levels(
                        venue=self.venue,
                        market=self.market,
                        symbol=str(row.get("s", symbol_from_type)),
                        exchange_ts=exchange_ts,
                        receive_ts_ns=receive_ts_ns,
                        bids=bids,
                        asks=asks,
                        sequence=last_update_id,
                        source="incremental_bootstrap_snapshot",
                        raw=row,
                    ))
                elif row.get("action") == "update":
                    events.append(BookDelta.from_levels(
                        venue=self.venue,
                        market=self.market,
                        symbol=str(row.get("s", symbol_from_type)),
                        exchange_ts=exchange_ts,
                        receive_ts_ns=receive_ts_ns,
                        first_update_id=last_update_id,
                        last_update_id=last_update_id,
                        previous_update_id=last_update_id - 1,
                        bids=bids,
                        asks=asks,
                        raw=row,
                    ))
        return events
