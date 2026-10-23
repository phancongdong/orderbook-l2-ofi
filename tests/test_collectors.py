"""Unit tests for WebSocket collectors."""
from __future__ import annotations

import gzip
import json
from unittest.mock import MagicMock

from orderbook_ofi.collectors.binance import BinanceFuturesCollector
from orderbook_ofi.collectors.bingx import BingXCollector
from orderbook_ofi.models import BookDelta, TradeEvent


def test_binance_collector_url_and_message_parsing():
    collector = BinanceFuturesCollector(
        symbols=["BTCUSDT", "ETHUSDT"],
        collect_trades=True,
        collect_depth=True,
    )
    url = collector.websocket_url
    assert "btcusdt@trade" in url
    assert "btcusdt@depth@100ms" in url
    assert "ethusdt@trade" in url

    # Test trade parsing
    trade_raw = json.dumps({
        "e": "trade",
        "E": 1700000000100,
        "T": 1700000000050,
        "s": "BTCUSDT",
        "t": 98765,
        "p": "65000.5",
        "q": "0.1",
        "m": True,
    })
    events = collector.parse_message(trade_raw, receive_ts_ns=1700000000120000000)
    assert len(events) == 1
    assert isinstance(events[0], TradeEvent)
    assert events[0].price == 65000.5
    assert events[0].aggressor_side.value == "SELL"

    # Test depthUpdate parsing
    depth_raw = json.dumps({
        "e": "depthUpdate",
        "E": 1700000000200,
        "T": 1700000000150,
        "s": "BTCUSDT",
        "U": 100,
        "u": 105,
        "pu": 99,
        "b": [["65000.0", "1.5"]],
        "a": [["65010.0", "2.0"]],
    })
    depth_events = collector.parse_message(depth_raw, receive_ts_ns=1700000000220000000)
    assert len(depth_events) == 1
    assert isinstance(depth_events[0], BookDelta)
    assert depth_events[0].first_update_id == 100
    assert depth_events[0].last_update_id == 105
    assert depth_events[0].previous_update_id == 99


def test_bingx_collector_gzip_and_heartbeat():
    collector = BingXCollector(symbols=["BTC-USDT"])

    # Test heartbeat Ping -> Pong
    ws_mock = MagicMock()
    assert collector.handle_heartbeat("Ping", ws_mock)
    ws_mock.send.assert_called_with("Pong")

    # Test json ping -> pong
    assert collector.handle_heartbeat(json.dumps({"ping": "abc123"}), ws_mock)
    ws_mock.send.assert_called_with(json.dumps({"pong": "abc123"}))

    # Test gzip decompression
    payload_str = json.dumps({"code": 0, "dataType": "BTC-USDT@trade", "data": []})
    compressed = gzip.compress(payload_str.encode("utf-8"))
    decompressed = collector.decode_message(compressed)
    assert decompressed == payload_str
