#!/usr/bin/env python3
"""Summarize proxy prefix-cache candidates from request-shape JSONL logs."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if isinstance(record, dict):
                records.append(record)
    return records


def cache_candidate(record: dict[str, Any]) -> dict[str, Any] | None:
    openai = record.get("openai")
    if not isinstance(openai, dict):
        return None
    candidate = openai.get("cache_candidate")
    return candidate if isinstance(candidate, dict) else None


def avg(values: list[int]) -> float:
    return statistics.mean(values) if values else 0.0


def rough_tokens(candidate: dict[str, Any]) -> int:
    value = candidate.get("estimated_full_prompt_tokens")
    if isinstance(value, int) and value > 0:
        return value
    try:
        chars = int(candidate.get("full_prompt_json_chars") or 0)
    except (TypeError, ValueError):
        chars = 0
    return max(1, chars // 4) if chars else 0


def context_pressure(tokens: int) -> str:
    if tokens >= 192_000:
        return "critical"
    if tokens >= 128_000:
        return "high"
    if tokens >= 96_000:
        return "watch"
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default="_local/request-shape-capture.jsonl",
        help="Request-shape JSONL log path.",
    )
    parser.add_argument("--limit", type=int, default=12, help="Rows to print.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    records = iter_jsonl(Path(args.path))
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    skipped = 0
    for record in records:
        candidate = cache_candidate(record)
        if not candidate:
            skipped += 1
            continue
        key = (
            str(candidate.get("model") or record.get("openai", {}).get("model") or ""),
            str(candidate.get("prefix_hash") or ""),
            str(candidate.get("tools_hash") or ""),
        )
        groups[key].append(record)

    rows: list[dict[str, Any]] = []
    for (model, prefix_hash, tools_hash), members in groups.items():
        candidates = [cache_candidate(member) or {} for member in members]
        prefix_sizes = [
            int(candidate.get("prefix_json_chars") or 0)
            for candidate in candidates
        ]
        tail_sizes = [
            int(candidate.get("tail_json_chars") or 0)
            for candidate in candidates
        ]
        full_sizes = [
            int(candidate.get("full_prompt_json_chars") or 0)
            for candidate in candidates
        ]
        estimated_tokens = [
            rough_tokens(candidate)
            for candidate in candidates
        ]
        pressure = Counter(
            str(candidate.get("context_pressure") or context_pressure(rough_tokens(candidate)))
            for candidate in candidates
        )
        kinds = Counter(str(member.get("kind") or "") for member in members)
        stream_modes = Counter(
            str((member.get("shape") or {}).get("stream_mode") or "")
            for member in members
            if isinstance(member.get("shape"), dict)
        )
        rows.append(
            {
                "model": model,
                "prefix_hash": prefix_hash,
                "tools_hash": tools_hash,
                "count": len(members),
                "potential_hits": max(0, len(members) - 1),
                "avg_prefix_json_chars": round(avg(prefix_sizes), 1),
                "avg_tail_json_chars": round(avg(tail_sizes), 1),
                "avg_full_prompt_json_chars": round(avg(full_sizes), 1),
                "avg_estimated_full_prompt_tokens": round(avg(estimated_tokens), 1),
                "context_pressure": dict(pressure),
                "kinds": dict(kinds),
                "stream_modes": dict(stream_modes),
                "first_ts": min(str(member.get("ts") or "") for member in members),
                "last_ts": max(str(member.get("ts") or "") for member in members),
                "sample_request_ids": [
                    str(member.get("request_id") or "")
                    for member in members[:5]
                ],
            }
        )

    rows.sort(
        key=lambda row: (
            int(row["potential_hits"]),
            int(row["count"]),
            float(row["avg_prefix_json_chars"]),
        ),
        reverse=True,
    )

    summary = {
        "path": str(args.path),
        "records": len(records),
        "records_with_cache_candidate": len(records) - skipped,
        "unique_prefix_groups": len(groups),
        "potential_hits": sum(int(row["potential_hits"]) for row in rows),
        "rows": rows[: args.limit],
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    print(f"path: {summary['path']}")
    print(f"records: {summary['records']}")
    print(f"records_with_cache_candidate: {summary['records_with_cache_candidate']}")
    print(f"unique_prefix_groups: {summary['unique_prefix_groups']}")
    print(f"potential_hits: {summary['potential_hits']}")
    if not rows:
        print("No cache candidates found. Enable PROXY_REQUEST_SHAPE_LOG_PATH and run traffic.")
        return 0

    print()
    header = (
        "count hits est_tokens pressure prefix_chars tail_chars model prefix_hash tools_hash "
        "stream_modes sample_request_ids"
    )
    print(header)
    print("-" * len(header))
    for row in rows[: args.limit]:
        print(
            f"{row['count']:>5} "
            f"{row['potential_hits']:>4} "
            f"{row['avg_estimated_full_prompt_tokens']:>10.1f} "
            f"{row['context_pressure']} "
            f"{row['avg_prefix_json_chars']:>12.1f} "
            f"{row['avg_tail_json_chars']:>10.1f} "
            f"{row['model']} "
            f"{row['prefix_hash']} "
            f"{row['tools_hash']} "
            f"{row['stream_modes']} "
            f"{','.join(row['sample_request_ids'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
