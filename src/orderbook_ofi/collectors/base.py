"""Reconnect-capable synchronous WebSocket collector base class."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection, connect

from orderbook_ofi.models import NormalizedEvent

EventCallback = Callable[[NormalizedEvent], None]
RawCallback = Callable[[str, int], None]


@dataclass
class CollectorStats:
    messages: int = 0
    events: int = 0
    heartbeats: int = 0
    reconnects: int = 0
    parse_errors: int = 0
    started_ts_ns: int = 0
    ended_ts_ns: int = 0
    elapsed_seconds: float = 0.0

    @property
    def duration_seconds(self) -> float:
        if self.elapsed_seconds > 0:
            return self.elapsed_seconds
        if self.ended_ts_ns <= self.started_ts_ns:
            return 0.0
        return (self.ended_ts_ns - self.started_ts_ns) / 1_000_000_000


class WebSocketCollector:
    venue = "unknown"
    market = "unknown"

    def __init__(
        self,
        symbols: Iterable[str],
        *,
        max_reconnects: int = 5,
        reconnect_backoff_seconds: float = 1.0,
        strict_parsing: bool = True,
    ) -> None:
        normalized = tuple(dict.fromkeys(symbol.upper() for symbol in symbols))
        if not normalized:
            raise ValueError("At least one symbol is required")
        self.symbols = normalized
        self.max_reconnects = max_reconnects
        self.reconnect_backoff_seconds = reconnect_backoff_seconds
        self.strict_parsing = strict_parsing

    @property
    def websocket_url(self) -> str:
        raise NotImplementedError

    def on_connected(self, websocket: ClientConnection) -> Iterable[NormalizedEvent]:
        return ()

    def decode_message(self, message: str | bytes) -> str:
        return message.decode("utf-8") if isinstance(message, bytes) else message

    def handle_heartbeat(self, message: str, websocket: ClientConnection) -> bool:
        return False

    def parse_message(self, message: str, receive_ts_ns: int) -> list[NormalizedEvent]:
        raise NotImplementedError

    def collect(
        self,
        on_event: EventCallback,
        *,
        on_raw: Optional[RawCallback] = None,
        duration_seconds: Optional[float] = None,
        max_events: Optional[int] = None,
    ) -> CollectorStats:
        if duration_seconds is not None and duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if max_events is not None and max_events <= 0:
            raise ValueError("max_events must be positive")

        stats = CollectorStats(started_ts_ns=time.time_ns())
        started_monotonic = time.monotonic()

        def finish() -> CollectorStats:
            stats.ended_ts_ns = time.time_ns()
            stats.elapsed_seconds = max(0.0, time.monotonic() - started_monotonic)
            return stats

        deadline = time.monotonic() + duration_seconds if duration_seconds is not None else None
        reconnect_attempts = 0

        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            try:
                with connect(self.websocket_url) as websocket:
                    reconnect_attempts = 0
                    for bootstrap_event in self.on_connected(websocket):
                        stats.events += 1
                        on_event(bootstrap_event)
                        if max_events is not None and stats.events >= max_events:
                            return finish()

                    while True:
                        if deadline is not None:
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                return finish()
                            timeout = max(0.1, min(remaining, 1.0))
                        else:
                            timeout = 1.0

                        try:
                            raw_payload = websocket.recv(timeout=timeout)
                        except TimeoutError:
                            continue

                        receive_ts_ns = time.time_ns()
                        stats.messages += 1
                        text_message = self.decode_message(raw_payload)

                        if on_raw is not None:
                            on_raw(text_message, receive_ts_ns)

                        if self.handle_heartbeat(text_message, websocket):
                            stats.heartbeats += 1
                            continue

                        try:
                            events = self.parse_message(text_message, receive_ts_ns)
                        except Exception:
                            stats.parse_errors += 1
                            if self.strict_parsing:
                                raise
                            continue

                        for event in events:
                            stats.events += 1
                            on_event(event)
                            if max_events is not None and stats.events >= max_events:
                                return finish()

            except ConnectionClosed:
                reconnect_attempts += 1
                stats.reconnects += 1
                if reconnect_attempts > self.max_reconnects:
                    raise
                backoff = self.reconnect_backoff_seconds * (2 ** (reconnect_attempts - 1))
                time.sleep(backoff)

        return finish()
