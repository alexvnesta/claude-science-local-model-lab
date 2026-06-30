#!/usr/bin/env python3
"""Integration tests for the Anthropic-to-OpenAI streaming bridge."""

from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    server_version = "FakeOpenAI/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, chunks: list[dict[str, Any]]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(b"data: ")
            self.wfile.write(json.dumps(chunk, separators=(",", ":")).encode("utf-8"))
            self.wfile.write(b"\n\n")
            self.wfile.flush()
            time.sleep(0.01)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/models":
            self._json(200, {"data": [{"id": "fake-model"}]})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or "0")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        messages = payload.get("messages") or []
        prompt = json.dumps(messages)
        if not payload.get("stream") and "text json tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": '::submit_output::+json::{"verdict":"pass","finding_count":0,"findings":[]}',
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream") and "check dropped tool guard" in prompt:
            guard_present = any(
                message.get("role") == "system"
                and "Local proxy note: Claude Science offered tools" in str(message.get("content") or "")
                for message in messages
                if isinstance(message, dict)
            )
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "guard present" if guard_present else "guard missing",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "fenced json tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": '```json\n{"verdict":"pass","finding_count":0,"findings":[]}\n```',
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream") and "preamble fenced reviewer json tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "I need to call the submit_output tool.\n\n"
                                    "```json\n"
                                    '{"verdict":"pass","findings":[],"note":"ok"}\n'
                                    "```"
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream") and "openai function json tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "I need to actually call the submit_output tool.\n\n"
                                    "```json\n"
                                    "{\n"
                                    '  "type": "function",\n'
                                    '  "name": "submit_output",\n'
                                    '  "arguments": {"verdict":"pass","findings":[],"note":"ok"}\n'
                                    "}\n"
                                    "```"
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream") and "markdown function text tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "[submit_output](submit_output("
                                    "verdict='fail', "
                                    "findings=[{'msg_idx': 2, 'finding_type': 'fail'}]"
                                    "))"
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream") and "function text tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": 'submit_output(verdict="pass", findings=[], artifact_version_id=None, msg_idx=None)',
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream") and "xmlish text tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "<tool_call>\n"
                                    "<function=submit_output>\n"
                                    "<parameter=agent_output_is_complete>\ntrue\n</parameter>\n"
                                    "<parameter=findings>\n[]\n</parameter>\n"
                                    "<parameter=verdict>\npass\n</parameter>\n"
                                    "</function>\n"
                                    "</tool_call>"
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream") and "text tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": '<tool_call>["submit_output","{\\"verdict\\":\\"pass\\",\\"finding_count\\":0,\\"findings\\":[]}"]',
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream"):
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "nonstream ok"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                },
            )
            return

        if "full json fallback" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "full json stream fallback ok",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6},
                },
            )
            return

        if "call a tool" in prompt:
            self._sse(
                [
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_fake_1",
                                            "type": "function",
                                            "function": {
                                                "name": "bash",
                                                "arguments": "{\"command\":\"",
                                            },
                                        }
                                    ]
                                }
                            }
                        ]
                    },
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "function": {"arguments": "pwd\"}"},
                                        }
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                ]
            )
            return

        self._sse(
            [
                {"choices": [{"delta": {"role": "assistant"}}]},
                {"choices": [{"delta": {"content": "stream "}}]},
                {
                    "choices": [
                        {"delta": {"content": "ok"}, "finish_reason": "stop"}
                    ]
                },
            ]
        )


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_fake_server() -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
    port = int(server.server_address[1])
    import threading

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def wait_for_proxy(port: int, proc: subprocess.Popen[bytes]) -> None:
    url = f"http://127.0.0.1:{port}/healthz"
    for _ in range(50):
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            raise AssertionError(f"proxy exited early\n{stderr}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise AssertionError("proxy did not become ready")


def post_json(url: str, payload: dict[str, Any]) -> str:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "anthropic-version": "2023-06-01"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if payload.get("stream"):
            lines: list[str] = []
            saw_message_stop = False
            while True:
                raw_line = response.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8")
                lines.append(line)
                if line.startswith("event: message_stop"):
                    saw_message_stop = True
                elif saw_message_stop and line.strip() == "":
                    break
            return "".join(lines)
        return response.read().decode("utf-8")


def parse_sse(raw: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in raw.strip().split("\n\n"):
        name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if name and data:
            events.append((name, json.loads(data)))
    return events


def assert_text_stream(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "say stream ok"}],
        },
    )
    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert names[:2] == ["message_start", "content_block_start"], names
    text = "".join(
        event["delta"]["text"]
        for name, event in events
        if name == "content_block_delta"
        and event.get("delta", {}).get("type") == "text_delta"
    )
    assert text == "stream ok", text
    stop = [
        event["delta"]["stop_reason"]
        for name, event in events
        if name == "message_delta"
    ]
    assert stop == ["end_turn"], stop


def assert_tool_stream(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "tools": [
                {
                    "name": "bash",
                    "description": "run shell",
                    "input_schema": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                }
            ],
            "messages": [{"role": "user", "content": "call a tool"}],
        },
    )
    events = parse_sse(raw)
    tool_starts = [
        event
        for name, event in events
        if name == "content_block_start"
        and event.get("content_block", {}).get("type") == "tool_use"
    ]
    assert len(tool_starts) == 1, events
    assert tool_starts[0]["content_block"]["name"] == "bash", tool_starts
    partial_json = "".join(
        event["delta"]["partial_json"]
        for name, event in events
        if name == "content_block_delta"
        and event.get("delta", {}).get("type") == "input_json_delta"
    )
    assert json.loads(partial_json) == {"command": "pwd"}, partial_json
    stop = [
        event["delta"]["stop_reason"]
        for name, event in events
        if name == "message_delta"
    ]
    assert stop == ["tool_use"], stop


def assert_nonstream(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "nonstream"}],
        },
    )
    payload = json.loads(raw)
    assert payload["content"][0]["text"] == "nonstream ok", payload


def assert_text_tool_call_adapter(
    proxy_port: int,
    prompt: str,
    include_extra_tools: bool = False,
) -> None:
    tools = [
        {
            "name": "submit_output",
            "description": "submit review",
            "input_schema": {
                "type": "object",
                "properties": {"verdict": {"type": "string"}},
                "required": ["verdict"],
            },
        }
    ]
    if include_extra_tools:
        tools.extend(
            [
                {
                    "name": "read_file",
                    "description": "read file",
                    "input_schema": {"type": "object"},
                },
                {
                    "name": "python",
                    "description": "run python",
                    "input_schema": {"type": "object"},
                },
            ]
        )
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": tools,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "tool_use", payload
    block = payload["content"][0]
    assert block["type"] == "tool_use", payload
    assert block["name"] == "submit_output", payload
    expected_verdict = "fail" if prompt == "markdown function text tool call" else "pass"
    assert block["input"]["verdict"] == expected_verdict, payload


def assert_dropped_tool_guard(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [
                {
                    "name": "search_skills",
                    "description": "search skills",
                    "input_schema": {"type": "object"},
                }
            ],
            "messages": [{"role": "user", "content": "check dropped tool guard"}],
        },
    )
    payload = json.loads(raw)
    assert payload["content"][0]["text"] == "guard present", payload


def assert_full_json_stream_fallback(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "full json fallback"}],
        },
    )
    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert names.count("message_start") == 1, names
    text = "".join(
        event["delta"]["text"]
        for name, event in events
        if name == "content_block_delta"
        and event.get("delta", {}).get("type") == "text_delta"
    )
    assert text == "full json stream fallback ok", text


def assert_stream_connection_closes(proxy_port: int) -> None:
    body = json.dumps(
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "say stream ok"}],
        }
    ).encode("utf-8")
    request = (
        b"POST /v1/messages HTTP/1.1\r\n"
        b"Host: 127.0.0.1:%d\r\n"
        b"Content-Type: application/json\r\n"
        b"anthropic-version: 2023-06-01\r\n"
        b"Connection: keep-alive\r\n"
        b"Content-Length: %d\r\n"
        b"\r\n"
    ) % (proxy_port, len(body))
    with socket.create_connection(("127.0.0.1", proxy_port), timeout=2) as sock:
        sock.settimeout(2)
        sock.sendall(request + body)
        received = b""
        while b"event: message_stop" not in received:
            chunk = sock.recv(4096)
            if not chunk:
                break
            received += chunk
        assert b"event: message_stop" in received, received.decode("utf-8", "replace")
        assert sock.recv(1) == b""


def main() -> int:
    fake_server, fake_port = start_fake_server()
    proxy_port = free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            str(ROOT / "proxy" / "anthropic_mtplx_proxy.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(proxy_port),
            "--upstream-base",
            f"http://127.0.0.1:{fake_port}/v1",
            "--upstream-model",
            "fake-model",
            "--advertised-models",
            "claude-opus-4-8,fake-model",
            "--parse-text-tool-calls",
            "1",
            "--tool-mode",
            "drop",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_for_proxy(proxy_port, proc)
        assert_text_stream(proxy_port)
        assert_tool_stream(proxy_port)
        assert_full_json_stream_fallback(proxy_port)
        assert_stream_connection_closes(proxy_port)
        assert_nonstream(proxy_port)
        assert_dropped_tool_guard(proxy_port)
        assert_text_tool_call_adapter(proxy_port, "text tool call")
        assert_text_tool_call_adapter(proxy_port, "text json tool call")
        assert_text_tool_call_adapter(proxy_port, "fenced json tool call")
        assert_text_tool_call_adapter(
            proxy_port,
            "preamble fenced reviewer json tool call",
            include_extra_tools=True,
        )
        assert_text_tool_call_adapter(
            proxy_port,
            "openai function json tool call",
            include_extra_tools=True,
        )
        assert_text_tool_call_adapter(
            proxy_port,
            "function text tool call",
            include_extra_tools=True,
        )
        assert_text_tool_call_adapter(
            proxy_port,
            "markdown function text tool call",
            include_extra_tools=True,
        )
        assert_text_tool_call_adapter(
            proxy_port,
            "xmlish text tool call",
            include_extra_tools=True,
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        fake_server.shutdown()
    print("streaming proxy tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
