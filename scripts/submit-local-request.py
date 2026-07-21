#!/usr/bin/env python3
"""Submit a prompt to the isolated Claude Science app through its local API.

This uses the supported `claude-science url` command to obtain a short-lived
login cookie, then posts to `/api/projects/{project_id}/request` with the CSRF
header expected by the web client. It deliberately does not print cookies,
nonces, or bearer material.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="Prompt text to submit.")
    parser.add_argument("--project-id", required=True, help="Claude Science project id.")
    parser.add_argument("--app-port", default="18765", help="Local Claude Science port.")
    parser.add_argument(
        "--app-cli",
        default=str(ROOT / "_local/Claude Science.app/Contents/Resources/bin/claude-science"),
        help="Path to the copied claude-science CLI.",
    )
    parser.add_argument("--data-dir", default=str(ROOT / "_local/data"))
    parser.add_argument("--config", default=str(ROOT / "_local/config.toml"))
    parser.add_argument("--model", default="claude-opus-4-8")
    parser.add_argument("--effort", default="default")
    parser.add_argument("--verifier-mode", choices=("on", "off"), default="on")
    parser.add_argument("--memory-mode", choices=("on", "off"), default="off")
    parser.add_argument("--plan-mode", action="store_true")
    parser.add_argument("--ultra-mode", action="store_true")
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


def main() -> int:
    args = parse_args()
    jar = http.cookiejar.MozillaCookieJar(str(ROOT / "_local/app-api-cookie.jar"))
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    csrf = login(opener, jar, args)
    jar.save(ignore_discard=True, ignore_expires=True)

    body = {
        "input_data": {
            "request": args.prompt,
            "ultra_mode": bool(args.ultra_mode),
            "_intent_id": str(uuid.uuid4()),
        },
        "model": args.model,
        "effort": args.effort,
        "thinking": False,
        "plan_mode": bool(args.plan_mode),
        "ultra_mode": bool(args.ultra_mode),
        "verifier_mode": args.verifier_mode,
        "memory_mode": args.memory_mode,
    }
    url = f"http://localhost:{args.app_port}/api/projects/{args.project_id}/request"
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
        with opener.open(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        print(detail, file=sys.stderr)
        return 1

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
