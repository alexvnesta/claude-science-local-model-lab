#!/usr/bin/env python3
"""Redacted inspector for official Claude Science local state.

This does not MITM Anthropic TLS traffic. It reads the local Claude Science
SQLite state in read-only mode and reports model-facing tool_use/tool_result
shapes plus host helper calls. It intentionally avoids credential tables and
redacts tool inputs.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


SECRET_MARKERS = (
    "api",
    "auth",
    "bearer",
    "credential",
    "key",
    "oauth",
    "password",
    "refresh",
    "secret",
    "token",
)


def default_db() -> Path:
    candidates = [
        Path(path)
        for path in glob.glob(
            str(Path.home() / ".claude-science" / "orgs" / "*" / "operon-cli.db")
        )
    ]
    if not candidates:
        raise SystemExit("No ~/.claude-science/orgs/*/operon-cli.db found")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def short(value: Any, limit: int = 96) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    if any(marker in text.lower() for marker in SECRET_MARKERS):
        return "[redacted]"
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def input_keys(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return ", ".join(sorted(str(key) for key in value.keys()))


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type='table' and name=?", (name,)
    ).fetchone()
    return row is not None


def iter_messages(
    conn: sqlite3.Connection, frame_id: str | None
) -> tuple[list[tuple[str, int, dict[str, Any]]], int]:
    sql = "select frame_id, idx, msg_json from frame_messages"
    params: tuple[Any, ...] = ()
    if frame_id:
        sql += " where frame_id=?"
        params = (frame_id,)
    sql += " order by frame_id, idx"

    rows: list[tuple[str, int, dict[str, Any]]] = []
    malformed = 0
    for raw_frame_id, idx, raw_json in conn.execute(sql, params):
        try:
            rows.append((raw_frame_id, idx, json.loads(raw_json)))
        except Exception:
            malformed += 1
    return rows, malformed


def recent_frames(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        select id, name, agent_name, status, model, input_tokens, output_tokens,
               cache_read_tokens, updated_at
        from frames
        order by updated_at desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    conn.row_factory = None
    return rows


def summarize_messages(
    messages: list[tuple[str, int, dict[str, Any]]], recent_limit: int
) -> tuple[
    collections.Counter[tuple[str, str]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    recent_tool_uses: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []

    for frame_id, idx, msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "tool_use":
                name = str(block.get("name") or "<unnamed>")
                caller = ""
                caller_block = block.get("caller")
                if isinstance(caller_block, dict):
                    caller = str(caller_block.get("type") or "")
                counts[(name, caller)] += 1
                tool_input = block.get("input")
                human_description = ""
                if isinstance(tool_input, dict):
                    human_description = short(tool_input.get("human_description"))
                recent_tool_uses.append(
                    {
                        "frame_id": frame_id,
                        "idx": idx,
                        "name": name,
                        "caller": caller,
                        "input_keys": input_keys(tool_input),
                        "human_description": human_description,
                    }
                )
            elif block_type == "tool_result":
                content_value = block.get("content")
                if isinstance(content_value, str):
                    result_len = len(content_value)
                else:
                    result_len = len(json.dumps(content_value, ensure_ascii=False))
                tool_results.append(
                    {
                        "frame_id": frame_id,
                        "idx": idx,
                        "tool_use_id": short(block.get("tool_use_id"), 40),
                        "content_len": result_len,
                    }
                )

    recent_tool_uses.sort(key=lambda item: (item["frame_id"], item["idx"]), reverse=True)
    return counts, recent_tool_uses[:recent_limit], tool_results


def print_markdown(args: argparse.Namespace) -> None:
    db_path = Path(args.db).expanduser() if args.db else default_db()
    conn = connect_readonly(db_path)

    print("# Official Claude Science Local-State Sniff")
    print()
    print(f"- DB: `{db_path}`")
    print("- Mode: read-only SQLite inspection")
    print("- Redaction: tool input values are omitted except short human descriptions")
    print()

    if table_exists(conn, "frames"):
        print("## Recent Frames")
        print()
        print("| frame | agent | status | model | input | output | cache_read | name |")
        print("| --- | --- | --- | --- | ---: | ---: | ---: | --- |")
        for row in recent_frames(conn, args.frames):
            print(
                "| "
                + " | ".join(
                    [
                        f"`{short(row['id'], 8)}`",
                        short(row["agent_name"], 24),
                        short(row["status"], 24),
                        short(row["model"], 32),
                        str(row["input_tokens"] or 0),
                        str(row["output_tokens"] or 0),
                        str(row["cache_read_tokens"] or 0),
                        short(row["name"], 64),
                    ]
                )
                + " |"
            )
        print()

    messages, malformed = iter_messages(conn, args.frame_id)
    counts, recent_tool_uses, tool_results = summarize_messages(messages, args.recent)

    print("## Tool Use Inventory")
    print()
    print(f"- Parsed messages: {len(messages)}")
    print(f"- Malformed/skipped messages: {malformed}")
    print(f"- Tool use blocks: {sum(counts.values())}")
    print(f"- Tool result blocks: {len(tool_results)}")
    if tool_results:
        lengths = [int(row["content_len"]) for row in tool_results]
        print(f"- Tool result bytes/chars: min={min(lengths)} max={max(lengths)}")
    print()
    print("| tool | caller | count |")
    print("| --- | --- | ---: |")
    for (name, caller), count in counts.most_common():
        print(f"| `{short(name, 80)}` | `{short(caller or '-', 32)}` | {count} |")
    print()

    print("## Recent Tool Uses")
    print()
    print("| frame | idx | tool | input keys | human description |")
    print("| --- | ---: | --- | --- | --- |")
    for item in recent_tool_uses:
        print(
            "| "
            + " | ".join(
                [
                    f"`{short(item['frame_id'], 8)}`",
                    str(item["idx"]),
                    f"`{short(item['name'], 80)}`",
                    short(item["input_keys"], 120),
                    short(item["human_description"], 120),
                ]
            )
            + " |"
        )
    print()

    if table_exists(conn, "host_call_log"):
        print("## Host Helper Calls")
        print()
        print("| method | count | total bytes | max bytes | errors |")
        print("| --- | ---: | ---: | ---: | ---: |")
        for method, count, total_bytes, max_bytes, errors in conn.execute(
            """
            select method,
                   count(*) as n,
                   sum(bytes) as total_bytes,
                   max(bytes) as max_bytes,
                   sum(case when error is not null and error <> '' then 1 else 0 end) as errors
            from host_call_log
            group by method
            order by n desc
            """
        ):
            print(
                f"| `{short(method, 80)}` | {count} | {total_bytes or 0} | "
                f"{max_bytes or 0} | {errors or 0} |"
            )
        print()

    if table_exists(conn, "custom_mcp_servers"):
        print("## MCP Servers")
        print()
        print("| name | transport | source |")
        print("| --- | --- | --- |")
        for name, transport, source in conn.execute(
            "select name, transport, source from custom_mcp_servers order by name"
        ):
            print(f"| `{short(name, 80)}` | `{short(transport, 32)}` | `{short(source, 32)}` |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="Path to operon-cli.db. Defaults to latest official DB.")
    parser.add_argument("--frame-id", help="Restrict message parsing to one frame.")
    parser.add_argument("--recent", type=int, default=24, help="Recent tool_use rows to print.")
    parser.add_argument("--frames", type=int, default=8, help="Recent frames to print.")
    args = parser.parse_args()
    print_markdown(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
