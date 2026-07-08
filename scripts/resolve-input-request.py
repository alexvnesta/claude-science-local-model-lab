#!/usr/bin/env python3
"""Resolve a pending Claude Science input request in the isolated app.

The web client routes approval cards through:

    POST /api/frames/{frame_id}/resolve-input

This helper uses the same short-lived local login path as submit-local-request.py
and can either take an explicit request/tool id pair or read the first pending
request from the isolated app database.
"""

from __future__ import annotations

import argparse
import glob
import http.cookiejar
import json
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame-id", required=True, help="Frame with a pending input request.")
    parser.add_argument("--request-id", help="Pending request id. Defaults to first pending request in DB.")
    parser.add_argument("--tool-id", help="Tool use id. Defaults to first pending request in DB.")
    parser.add_argument(
        "--app-port",
        default=os.environ.get("CLAUDE_SCIENCE_LOCAL_PORT", "18765"),
        help="Local Claude Science port.",
    )
    parser.add_argument(
        "--app-cli",
        default=str(ROOT / "_local/Claude Science.app/Contents/Resources/bin/claude-science"),
        help="Path to the copied claude-science CLI.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("CLAUDE_SCIENCE_LOCAL_DATA_DIR", str(ROOT / "_local/data")),
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("CLAUDE_SCIENCE_LOCAL_CONFIG", str(ROOT / "_local/config.toml")),
    )
    parser.add_argument("--db", help="Path to operon-cli.db. Defaults to first DB under data-dir/orgs.")
    parser.add_argument("--action", default="allow", choices=("allow", "deny", "cancel"))
    parser.add_argument(
        "--scope",
        choices=("once", "conversation", "project", "always"),
        default="conversation",
        help="Permission scope for approved requests. Use 'once' to omit a saved scope.",
    )
    parser.add_argument("--verifier-mode", choices=("on", "off"))
    parser.add_argument("--memory-mode", choices=("on", "off"))
    parser.add_argument("--plan-mode", action="store_true")
    parser.add_argument("--ultra-mode", action="store_true")
    parser.add_argument("--target-agent")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def login(
    opener: urllib.request.OpenerDirector,
    jar: http.cookiejar.MozillaCookieJar,
    args: argparse.Namespace,
) -> str:
    url_output = subprocess.check_output(
        [
            args.app_cli,
            "url",
            "--data-dir",
            args.data_dir,
            "--config",
            args.config,
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    login_url = url_output.splitlines()[0].strip()
    opener.open(login_url, timeout=10).read()
    for cookie in jar:
        if cookie.name == "operon_csrf":
            return str(cookie.value)
    raise RuntimeError("Claude Science login did not set operon_csrf")


def default_db(data_dir: str) -> Path:
    matches = glob.glob(str(Path(data_dir) / "orgs" / "*" / "operon-cli.db"))
    if not matches:
        raise RuntimeError(f"No operon-cli.db found under {data_dir}/orgs")
    matches.sort()
    return Path(matches[0])


def pending_request_from_db(db_path: Path, frame_id: str) -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    row = con.execute("select output_data from frames where id = ?", (frame_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"Frame not found in {db_path}: {frame_id}")
    output_data = json.loads(row[0] or "{}")
    pending = output_data.get("pending_input_requests")
    if not isinstance(pending, list) or not pending:
        raise RuntimeError(f"Frame has no pending_input_requests: {frame_id}")
    first = pending[0]
    if not isinstance(first, dict):
        raise RuntimeError(f"Malformed pending request on frame: {frame_id}")
    return first


def main() -> int:
    args = parse_args()
    pending: dict[str, Any] = {}
    if not args.request_id or not args.tool_id:
        pending = pending_request_from_db(Path(args.db) if args.db else default_db(args.data_dir), args.frame_id)

    request_id = args.request_id or pending.get("requestId")
    tool_id = args.tool_id or pending.get("tool_id") or request_id
    if not request_id or not tool_id:
        raise RuntimeError("Need both request id and tool id.")

    approved = args.action == "allow"
    response: dict[str, Any] = {
        "requestId": request_id,
        "tool_id": tool_id,
        "approved": approved,
        "action": args.action,
    }
    if args.scope and args.scope != "once":
        response["scope"] = args.scope

    body: dict[str, Any] = {"responses": [response]}
    if args.verifier_mode is not None:
        body["verifier_mode"] = args.verifier_mode
    if args.memory_mode is not None:
        body["memory_mode"] = args.memory_mode
    if args.plan_mode:
        body["plan_mode"] = True
    if args.ultra_mode:
        body["ultra_mode"] = True
    if args.target_agent:
        body["target_agent"] = args.target_agent

    if args.dry_run:
        print(json.dumps(body, indent=2))
        return 0

    jar = http.cookiejar.MozillaCookieJar(str(ROOT / "_local/app-api-cookie.jar"))
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    csrf = login(opener, jar, args)
    jar.save(ignore_discard=True, ignore_expires=True)

    url = f"http://localhost:{args.app_port}/api/frames/{args.frame_id}/resolve-input"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-operon-csrf": csrf,
            "origin": f"http://localhost:{args.app_port}",
            "referer": f"http://localhost:{args.app_port}/",
        },
        method="POST",
    )
    try:
        with opener.open(request, timeout=30) as response_handle:
            payload = response_handle.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(detail, file=sys.stderr)
        return 1

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
