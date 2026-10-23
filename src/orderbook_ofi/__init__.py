"""Order Book Reconstruction & Cont's Order Flow Imbalance (OFI) Package.

A high-performance, sequence-safe Level-2 Limit Order Book (LOB) engine,
Cont's Order Flow Imbalance (OFI) feature pipeline, and replay analytics.
"""
from orderbook_ofi.book import LocalOrderBook, SequenceGapError
from orderbook_ofi.models import (
    AggressorSide,
    BookDelta,
    BookLevel,
    BookSnapshot,
    NormalizedEvent,
    TradeEvent,
    event_to_record,
    timestamp_to_ns,
)
from orderbook_ofi.ofi import (
    book_snapshot_features,
    compute_l1_ofi,
    compute_multilevel_ofi,
)
from orderbook_ofi.replay import (
    L2ReplayStats,
    add_forward_mid_returns,
    correlation_or_none,
    replay_l2,
)
from orderbook_ofi.storage import (
    RawMessageWriter,
    atomic_json,
    sha256_file,
)

__version__ = "1.0.0"

__all__ = [
    # Core LOB Reconstruction
    "LocalOrderBook",
    "SequenceGapError",
    # Event Models
    "AggressorSide",
    "BookLevel",
    "BookSnapshot",
    "BookDelta",
    "TradeEvent",
    "NormalizedEvent",
    "event_to_record",
    "timestamp_to_ns",
    # Cont's OFI & Microstructure Features
    "compute_l1_ofi",
    "compute_multilevel_ofi",
    "book_snapshot_features",
    # Replay Engine & Analytics
    "L2ReplayStats",
    "replay_l2",
    "add_forward_mid_returns",
    "correlation_or_none",
    # Storage & Integrity
    "RawMessageWriter",
    "atomic_json",
    "sha256_file",
]
