"""Binance USD-M futures trade and incremental L2 collector."""
from __future__ import annotations

import json
import time
from typing import Iterable

import requests
from websockets.sync.client import ClientConnection

from orderbook_ofi.collectors.base import WebSocketCollector
from orderbook_ofi.models import BookDelta, BookSnapshot, NormalizedEvent, TradeEvent


class BinanceFuturesCollector(WebSocketCollector):
    venue = "binance"
    market = "futures_um"

    def __init__(
        self,
        symbols: Iterable[str],
        *,
        collect_trades: bool = True,
        collect_depth: bool = True,
        trade_stream: str = "trade",
        depth_limit: int = 1000,
        rest_base_url: str = "https://fapi.binance.com",
        websocket_base_url: str = "wss://fstream.binance.com/stream",
        **kwargs,
    ) -> None:
        super().__init__(symbols, **kwargs)
        if not collect_trades and not collect_depth:
            raise ValueError("Enable trades, depth, or both")
        if trade_stream not in {"trade", "aggTrade"}:
            raise ValueError("Binance trade_stream must be 'trade' or 'aggTrade'")
        if depth_limit not in {5, 10, 20, 50, 100, 500, 1000}:
            raise ValueError("Unsupported Binance depth_limit")
        self.collect_trades = collect_trades
        self.collect_depth = collect_depth
        self.trade_stream = trade_stream
        self.depth_limit = depth_limit
        self.rest_base_url = rest_base_url.rstrip("/")
        self.websocket_base_url = websocket_base_url.rstrip("/")
        self.session = requests.Session()

    @property
    def websocket_url(self) -> str:
        streams: list[str] = []
        for symbol in self.symbols:
            stream_symbol = symbol.lower()
            if self.collect_trades:
                streams.append(f"{stream_symbol}@{self.trade_stream}")
            if self.collect_depth:
                streams.append(f"{stream_symbol}@depth@100ms")
        return f"{self.websocket_base_url}?streams={'/'.join(streams)}"

    def on_connected(self, websocket: ClientConnection) -> Iterable[NormalizedEvent]:
        if not self.collect_depth:
            return ()
        snapshots: list[BookSnapshot] = []
        for symbol in self.symbols:
            response = self.session.get(
                f"{self.rest_base_url}/fapi/v1/depth",
                params={"symbol": symbol, "limit": self.depth_limit},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            receive_ts_ns = time.time_ns()
            exchange_ts = payload.get("T", payload.get("E", receive_ts_ns))
            snapshots.append(BookSnapshot.from_levels(
                venue=self.venue,
                market=self.market,
                symbol=symbol,
                exchange_ts=exchange_ts,
                receive_ts_ns=receive_ts_ns,
                bids=payload.get("bids", []),
                asks=payload.get("asks", []),
                sequence=int(payload["lastUpdateId"]),
                source="rest_bootstrap_snapshot",
                raw=payload,
            ))
        return snapshots

    def parse_message(self, message: str, receive_ts_ns: int) -> list[NormalizedEvent]:
        payload = json.loads(message)
        data = payload.get("data", payload)
        event_type = data.get("e")

        if event_type in {"trade", "aggTrade"}:
            buyer_is_maker = bool(data.get("m"))
            return [TradeEvent.from_maker_flag(
                venue=self.venue,
                market=self.market,
                symbol=str(data["s"]),
                exchange_ts=data.get("T", data.get("E", receive_ts_ns)),
                receive_ts_ns=receive_ts_ns,
                trade_id=data.get("t", data.get("a", f"{receive_ts_ns}")),
                price=data["p"],
                quantity=data["q"],
                quote_quantity=data.get("q_quote"),
                buyer_is_maker=buyer_is_maker,
                sequence=data.get("t", data.get("a")),
                raw=data,
            )]

        if event_type == "depthUpdate":
            return [BookDelta.from_levels(
                venue=self.venue,
                market=self.market,
                symbol=str(data["s"]),
                exchange_ts=data.get("T", data.get("E", receive_ts_ns)),
                receive_ts_ns=receive_ts_ns,
                first_update_id=int(data["U"]),
                last_update_id=int(data["u"]),
                previous_update_id=int(data["pu"]) if "pu" in data else None,
                bids=data.get("b", []),
                asks=data.get("a", []),
                raw=data,
            )]

        return []
