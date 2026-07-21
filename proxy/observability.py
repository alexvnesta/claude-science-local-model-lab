"""Redacted runtime observability for the local Claude Science proxy.

This module intentionally stores only request-shape and transport metadata.
It must not receive prompts, tool arguments, tool results, account state, or
artifact contents.
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from collections import Counter
from typing import Any


class ProxyMetrics:
    def __init__(self) -> None:
        self.started_monotonic = time.monotonic()
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._lock = threading.Lock()
        self.requests_total = 0
        self.messages_by_kind: Counter[str] = Counter()
        self.messages_by_stream_mode: Counter[str] = Counter()
        self.upstream_errors_by_status: Counter[str] = Counter()
        self.upstream_retries_by_status: Counter[str] = Counter()
        self.upstream_transport_errors_by_reason: Counter[str] = Counter()
        self.tool_filters_by_reason: Counter[str] = Counter()
        self.provider_latency_by_kind: dict[str, dict[str, float | int]] = {}

    def next_request_id(self) -> str:
        return f"req_{uuid.uuid4().hex[:12]}"

    def record_message(self, *, kind: str, stream_mode: str) -> None:
        with self._lock:
            self.requests_total += 1
            self.messages_by_kind[kind] += 1
            self.messages_by_stream_mode[stream_mode] += 1

    def record_upstream_retry(self, *, status: int) -> None:
        with self._lock:
            self.upstream_retries_by_status[str(status)] += 1

    def record_upstream_error(self, *, status: int) -> None:
        with self._lock:
            self.upstream_errors_by_status[str(status)] += 1

    def record_upstream_transport_error(self, *, reason: str) -> None:
        with self._lock:
            self.upstream_transport_errors_by_reason[reason] += 1

    def record_tool_filter(self, *, reason: str) -> None:
        with self._lock:
            self.tool_filters_by_reason[reason] += 1

    def record_provider_latency(self, *, kind: str, elapsed_seconds: float) -> None:
        elapsed_ms = max(0.0, elapsed_seconds * 1000)
        with self._lock:
            current = self.provider_latency_by_kind.setdefault(
                kind,
                {
                    "count": 0,
                    "total_ms": 0.0,
                    "last_ms": 0.0,
                    "max_ms": 0.0,
                },
            )
            current["count"] = int(current["count"]) + 1
            current["total_ms"] = float(current["total_ms"]) + elapsed_ms
            current["last_ms"] = elapsed_ms
            current["max_ms"] = max(float(current["max_ms"]), elapsed_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latency: dict[str, dict[str, float | int]] = {}
            for kind, values in self.provider_latency_by_kind.items():
                count = int(values["count"])
                total_ms = float(values["total_ms"])
                latency[kind] = {
                    "count": count,
                    "avg_ms": round(total_ms / count, 1) if count else 0.0,
                    "last_ms": round(float(values["last_ms"]), 1),
                    "max_ms": round(float(values["max_ms"]), 1),
                }
            return {
                "started_at": self.started_at,
                "uptime_seconds": round(time.monotonic() - self.started_monotonic, 1),
                "requests_total": self.requests_total,
                "messages_by_kind": dict(sorted(self.messages_by_kind.items())),
                "messages_by_stream_mode": dict(sorted(self.messages_by_stream_mode.items())),
                "upstream_errors_by_status": dict(sorted(self.upstream_errors_by_status.items())),
                "upstream_retries_by_status": dict(sorted(self.upstream_retries_by_status.items())),
                "upstream_transport_errors_by_reason": dict(
                    sorted(self.upstream_transport_errors_by_reason.items())
                ),
                "tool_filters_by_reason": dict(sorted(self.tool_filters_by_reason.items())),
                "provider_latency_by_kind": latency,
            }


METRICS = ProxyMetrics()


def log_event(message: str, *, request_id: str | None = None) -> None:
    prefix = "[anthropic-mtplx-proxy]"
    if request_id:
        prefix = f"{prefix} [{request_id}]"
    print(f"{prefix} {message}", file=sys.stderr, flush=True)
