"""Append-only raw capture and atomic file persistence utilities."""
from __future__ import annotations

import gzip
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


def sha256_file(path: Path) -> str:
    """Calculate cryptographic SHA-256 hash of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically write JSON payload with directory creation and rename semantics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


class RawMessageWriter:
    """High-throughput compressed .ndjson.gz append-only raw message logger."""
    def __init__(
        self,
        root: Path | str,
        venue: str,
        market: str,
        session_id: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.session_id = session_id or f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        self.path = Path(root) / "raw_live" / venue / market / f"{self.session_id}.ndjson.gz"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = gzip.open(self.path, "wt", encoding="utf-8", newline="\n")
        self.count = 0
        self.first_receive_ts_ns: Optional[int] = None
        self.last_receive_ts_ns: Optional[int] = None

    def write(self, raw_message: str, receive_ts_ns: int) -> None:
        """Write raw serialized payload with receive timestamp."""
        if self.first_receive_ts_ns is None:
            self.first_receive_ts_ns = receive_ts_ns
        self.last_receive_ts_ns = receive_ts_ns
        self._handle.write(json.dumps({
            "receive_ts_ns": receive_ts_ns,
            "raw": raw_message,
        }, separators=(",", ":")) + "\n")
        self.count += 1

    def close(self) -> Path:
        """Flush and close underlying gzip stream."""
        if not self._handle.closed:
            self._handle.close()
        return self.path

    def __enter__(self) -> "RawMessageWriter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
