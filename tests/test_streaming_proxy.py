#!/usr/bin/env python3
"""Integration tests for the Anthropic-to-OpenAI streaming bridge."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import socket
import subprocess
import sys
import tempfile
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

    def _sse(
        self,
        chunks: list[dict[str, Any]],
        *,
        delay: float = 0.01,
        initial_delay: float = 0.0,
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if initial_delay:
            time.sleep(initial_delay)
        try:
            for chunk in chunks:
                self.wfile.write(b"data: ")
                self.wfile.write(json.dumps(chunk, separators=(",", ":")).encode("utf-8"))
                self.wfile.write(b"\n\n")
                self.wfile.flush()
                time.sleep(delay)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            if isinstance(exc, OSError) and exc.errno not in (errno.EPIPE, errno.ECONNRESET):
                raise

    def _sse_event(self, name: str, payload: dict[str, Any]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(f"event: {name}\n".encode("utf-8"))
        self.wfile.write(b"data: ")
        self.wfile.write(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        self.wfile.write(b"\n\n")
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
        if not payload.get("stream") and "check upstream api key alias" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": self.headers.get("Authorization", ""),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "check tool choice required" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "tool_choice": payload.get("tool_choice"),
                                        "tool_count": len(payload.get("tools") or []),
                                    }
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "check server tool skipped" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "tool_choice": payload.get("tool_choice"),
                                        "tool_count": len(payload.get("tools") or []),
                                        "tool_names": [
                                            item.get("function", {}).get("name")
                                            for item in payload.get("tools") or []
                                            if isinstance(item, dict)
                                        ],
                                    }
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "check harness tool choice" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "tool_choice": payload.get("tool_choice"),
                                        "tool_names": [
                                            item.get("function", {}).get("name")
                                            for item in payload.get("tools") or []
                                            if isinstance(item, dict)
                                        ],
                                    }
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "check completed harness followup" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "tool_choice": payload.get("tool_choice"),
                                        "tool_names": [
                                            item.get("function", {}).get("name")
                                            for item in payload.get("tools") or []
                                            if isinstance(item, dict)
                                        ],
                                    }
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "check harness allowlist" in prompt:
            names = [
                item.get("function", {}).get("name")
                for item in payload.get("tools") or []
                if isinstance(item, dict)
            ]
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "tool_choice": payload.get("tool_choice"),
                                        "tool_names": names,
                                    }
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "check tool allowlist" in prompt:
            names = [
                item.get("function", {}).get("name")
                for item in payload.get("tools") or []
                if isinstance(item, dict)
            ]
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps({"tool_names": names}),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "drop mode spoofed tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_drop_mode_spoof",
                                        "type": "function",
                                        "function": {
                                            "name": "bash",
                                            "arguments": json.dumps(
                                                {"command": "echo should-not-run"}
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "invalid native tool json" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_bad_json",
                                        "type": "function",
                                        "function": {
                                            "name": "bash",
                                            "arguments": "{\"command\":",
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "unknown native tool" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_unknown",
                                        "type": "function",
                                        "function": {
                                            "name": "delete_everything",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "schema invalid native tool" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_schema_bad",
                                        "type": "function",
                                        "function": {
                                            "name": "bash",
                                            "arguments": "{\"path\":\"pwd\"}",
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "valid python native tool" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_python_valid",
                                        "type": "function",
                                        "function": {
                                            "name": "python",
                                            "arguments": json.dumps(
                                                {
                                                    "code": "print('ok')",
                                                    "human_description": "Run a minimal check.",
                                                }
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "science compat native tool" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_science_compat",
                                        "type": "function",
                                        "function": {
                                            "name": "bash",
                                            "arguments": "{\"command\":\"pwd\"}",
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if "slow nonstream timeout" in prompt:
            time.sleep(0.5)
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "too late"},
                            "finish_reason": "stop",
                        }
                    ],
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

        if "long direct stream" in prompt:
            chunks = [{"choices": [{"delta": {"role": "assistant"}}]}]
            chunks.extend(
                {"choices": [{"delta": {"content": f"chunk-{idx:03d} "}}]}
                for idx in range(80)
            )
            chunks.append({"choices": [{"delta": {}, "finish_reason": "stop"}]})
            self._sse(chunks, delay=0.001)
            return

        if "stream upstream error event" in prompt:
            self._sse(
                [
                    {
                        "error": {
                            "type": "server_error",
                            "message": "synthetic upstream stream error",
                        }
                    }
                ],
                delay=0.001,
            )
            return

        if "stream upstream named error event" in prompt:
            self._sse_event(
                "error",
                {
                    "type": "error",
                    "message": "synthetic named upstream stream error",
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

        if "call split streamed tool" in prompt:
            self._sse(
                [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_split_1",
                                            "type": "function",
                                            "function": {
                                                "name": "bash",
                                                "arguments": "{\"com",
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
                                            "function": {"arguments": "mand\":\"p"},
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
                                            "function": {"arguments": "wd\"}"},
                                        }
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    },
                ],
                delay=0.001,
            )
            return

        if "call invalid streamed tool" in prompt:
            self._sse(
                [
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_stream_bad",
                                            "type": "function",
                                            "function": {
                                                "name": "bash",
                                                "arguments": "{\"command\":",
                                            },
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

        if "cancel direct stream" in prompt:
            chunks = [{"choices": [{"delta": {"role": "assistant"}}]}]
            chunks.extend(
                {"choices": [{"delta": {"content": f"cancel-{idx:03d} "}}]}
                for idx in range(200)
            )
            chunks.append({"choices": [{"delta": {}, "finish_reason": "stop"}]})
            self._sse(chunks, delay=0.02)
            return

        if "slow stream heartbeat" in prompt:
            self._sse(
                [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {"choices": [{"delta": {"content": "slow "}}]},
                    {
                        "choices": [
                            {"delta": {"content": "ok"}, "finish_reason": "stop"}
                        ]
                    },
                ],
                delay=0.12,
                initial_delay=0.12,
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


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"anthropic-version": "2023-06-01"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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


def stream_text(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(
        event["delta"]["text"]
        for name, event in events
        if name == "content_block_delta"
        and event.get("delta", {}).get("type") == "text_delta"
    )


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
    text = stream_text(events)
    assert text == "stream ok", text
    stop = [
        event["delta"]["stop_reason"]
        for name, event in events
        if name == "message_delta"
    ]
    assert stop == ["end_turn"], stop


def assert_long_text_stream(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": "long direct stream"}],
        },
    )
    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert names.count("message_start") == 1, names
    assert names[-2:] == ["message_delta", "message_stop"], names
    expected = "".join(f"chunk-{idx:03d} " for idx in range(80))
    assert stream_text(events) == expected, stream_text(events)[-80:]
    text_delta_count = sum(
        1
        for name, event in events
        if name == "content_block_delta"
        and event.get("delta", {}).get("type") == "text_delta"
    )
    assert text_delta_count == 80, text_delta_count


def assert_direct_stream_heartbeat(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "slow stream heartbeat"}],
        },
    )
    assert ": heartbeat\n\n" in raw, raw
    events = parse_sse(raw)
    assert stream_text(events) == "slow ok", stream_text(events)


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


def assert_split_streamed_tool_arguments(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "tools": [bash_tool()],
            "messages": [{"role": "user", "content": "call split streamed tool"}],
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


def bash_tool() -> dict[str, Any]:
    return {
        "name": "bash",
        "description": "run shell",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    }


def search_skills_tool() -> dict[str, Any]:
    return {
        "name": "search_skills",
        "description": "search skills",
        "input_schema": {
            "type": "object",
            "properties": {
                "human_description": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["human_description"],
        },
    }


def python_tool() -> dict[str, Any]:
    return {
        "name": "python",
        "description": "execute python",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "human_description": {"type": "string"},
            },
            "required": ["code"],
        },
    }


def repl_tool() -> dict[str, Any]:
    return {
        "name": "repl",
        "description": "run repl code",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "human_description": {"type": "string"},
            },
            "required": ["human_description", "code"],
        },
    }


def read_file_tool() -> dict[str, Any]:
    return {
        "name": "read_file",
        "description": "read artifact or file",
        "input_schema": {
            "type": "object",
            "properties": {
                "human_description": {"type": "string"},
                "version_id": {"type": "string"},
                "file_path": {"type": "string"},
            },
            "required": ["human_description"],
        },
    }


def submit_output_tool() -> dict[str, Any]:
    return {
        "name": "submit_output",
        "description": "submit structured review",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string"},
                "findings": {"type": "array", "items": {"type": "object"}},
                "human_description": {"type": "string"},
                "_completion_bullets": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["verdict", "findings"],
        },
    }


def server_web_search_tool() -> dict[str, Any]:
    return {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    }


def assert_invalid_native_tool_filtered(proxy_port: int, prompt: str) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [bash_tool()],
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "end_turn", payload
    assert all(block.get("type") != "tool_use" for block in payload["content"]), payload


def assert_valid_python_tool_allowed(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [python_tool()],
            "messages": [{"role": "user", "content": "valid python native tool"}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "tool_use", payload
    block = payload["content"][0]
    assert block["name"] == "python", payload
    assert block["input"]["code"] == "print('ok')", payload


def assert_claude_science_tool_compat(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [bash_tool()],
            "messages": [{"role": "user", "content": "science compat native tool"}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "tool_use", payload
    block = payload["content"][0]
    assert block["id"].startswith("toolu_"), payload
    assert block["id"] != "call_science_compat", payload
    assert block["caller"] == {"type": "direct"}, payload


def assert_invalid_streamed_tool_filtered(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "tools": [bash_tool()],
            "messages": [{"role": "user", "content": "call invalid streamed tool"}],
        },
    )
    events = parse_sse(raw)
    tool_starts = [
        event
        for name, event in events
        if name == "content_block_start"
        and event.get("content_block", {}).get("type") == "tool_use"
    ]
    assert tool_starts == [], events
    stop = [
        event["delta"]["stop_reason"]
        for name, event in events
        if name == "message_delta"
    ]
    assert stop == ["end_turn"], stop
    metrics = get_json(f"http://127.0.0.1:{proxy_port}/healthz")["metrics"]
    assert metrics["tool_filters_by_reason"].get("bad_arguments", 0) >= 1, metrics


def assert_tool_choice_required(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tool_choice": {"type": "any"},
            "tools": [bash_tool()],
            "messages": [{"role": "user", "content": "check tool choice required"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_choice"] == "required", upstream_seen
    assert upstream_seen["tool_count"] == 1, upstream_seen


def assert_server_tools_not_forwarded_as_functions(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tool_choice": {"type": "any"},
            "tools": [server_web_search_tool(), bash_tool()],
            "messages": [{"role": "user", "content": "check server tool skipped mixed"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == ["bash"], upstream_seen
    assert upstream_seen["tool_choice"] == "required", upstream_seen

    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tool_choice": {"type": "any"},
            "tools": [server_web_search_tool()],
            "messages": [{"role": "user", "content": "check server tool skipped only"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == [], upstream_seen
    assert upstream_seen["tool_count"] == 0, upstream_seen
    assert upstream_seen["tool_choice"] is None, upstream_seen

    metrics = get_json(f"http://127.0.0.1:{proxy_port}/healthz")["metrics"]
    assert metrics["messages_by_kind"].get("tools_hidden", 0) >= 1, metrics


def assert_tool_allowlist(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [bash_tool(), search_skills_tool()],
            "messages": [{"role": "user", "content": "check tool allowlist"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == ["search_skills"], upstream_seen


def assert_drop_mode_rejects_unforwarded_tool_calls(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [bash_tool()],
            "messages": [{"role": "user", "content": "drop mode spoofed tool call"}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "end_turn", payload
    assert [block["type"] for block in payload["content"]] == ["text"], payload
    metrics = get_json(f"http://127.0.0.1:{proxy_port}/healthz")["metrics"]
    assert metrics["tool_filters_by_reason"].get("no_tools_offered", 0) >= 1, metrics


def assert_harness_tools_do_not_extend_general_allowlist(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [bash_tool(), search_skills_tool(), submit_output_tool()],
            "messages": [{"role": "user", "content": "check harness allowlist"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == ["search_skills"], upstream_seen
    metrics = get_json(f"http://127.0.0.1:{proxy_port}/healthz")["metrics"]
    assert metrics["messages_by_kind"].get("harness", 0) >= 1, metrics


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
    assert stream_text(events) == "full json stream fallback ok", stream_text(events)


def assert_stream_error_event(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "stream upstream error event"}],
        },
    )
    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert names == ["error"], names
    error = events[0][1]["error"]
    assert error["type"] == "upstream_error", error
    assert error["message"] == "synthetic upstream stream error", error
    metrics = get_json(f"http://127.0.0.1:{proxy_port}/healthz")["metrics"]
    assert metrics["upstream_errors_by_status"].get("502", 0) >= 1, metrics


def assert_named_stream_error_event(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "stream upstream named error event"}],
        },
    )
    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert names == ["error"], names
    error = events[0][1]["error"]
    assert error["type"] == "upstream_error", error
    assert error["message"] == "synthetic named upstream stream error", error


def assert_nonstream_timeout_metric(proxy_port: int) -> None:
    try:
        post_json(
            f"http://127.0.0.1:{proxy_port}/v1/messages",
            {
                "model": "claude-opus-4-8",
                "stream": False,
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "slow nonstream timeout"}],
            },
        )
    except urllib.error.HTTPError as exc:
        assert exc.code == 500, exc
    else:
        raise AssertionError("expected proxy timeout response")
    metrics = get_json(f"http://127.0.0.1:{proxy_port}/healthz")["metrics"]
    reasons = metrics["upstream_transport_errors_by_reason"]
    assert reasons.get("timeout", 0) >= 1, metrics


def assert_stream_read_exception_becomes_error_event() -> None:
    from proxy.anthropic_mtplx_proxy import iter_openai_stream_events

    class ExplodingStream:
        def __iter__(self) -> Any:
            yield b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
            raise TimeoutError("synthetic upstream read timeout")

    events = list(
        iter_openai_stream_events(
            ExplodingStream(),
            heartbeat_seconds=0,
            request_id="test_stream_read_exception",
        )
    )
    assert events[0][0] == "chunk", events
    assert events[1][0] == "error", events
    assert isinstance(events[1][1], TimeoutError), events


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
        assert b"X-Request-Id: req_" in received, received.decode("utf-8", "replace")
        try:
            assert sock.recv(1) == b""
        except OSError as exc:
            assert exc.errno == errno.EBADF


def assert_client_cancellation_does_not_hang(proxy_port: int) -> None:
    body = json.dumps(
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": "cancel direct stream"}],
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
        while b"cancel-000" not in received:
            chunk = sock.recv(4096)
            assert chunk, received.decode("utf-8", "replace")
            received += chunk
    time.sleep(0.2)
    payload = get_json(f"http://127.0.0.1:{proxy_port}/healthz")
    assert payload["ok"] is True, payload


def assert_models_endpoint(proxy_port: int) -> None:
    payload = get_json(f"http://127.0.0.1:{proxy_port}/v1/models?limit=1000")
    ids = [item["id"] for item in payload["data"]]
    assert ids == ["claude-opus-4-8", "fake-model"], payload
    assert payload["data"][0]["display_name"] == "Claude Opus 4.8", payload
    assert payload["has_more"] is False, payload
    assert payload["first_id"] == "claude-opus-4-8", payload
    assert payload["last_id"] == "fake-model", payload

    model = get_json(f"http://127.0.0.1:{proxy_port}/v1/models/claude-opus-4-8")
    assert model["id"] == "claude-opus-4-8", model
    assert model["type"] == "model", model
    assert model["display_name"] == "Claude Opus 4.8", model


def assert_custom_model_display_names(proxy_port: int) -> None:
    payload = get_json(f"http://127.0.0.1:{proxy_port}/v1/models?limit=1000")
    names = {item["id"]: item["display_name"] for item in payload["data"]}
    assert names["claude-opus-4-8"] == "MTPLX Qwen 27B Local", payload
    assert names["fake-model"] == "Fake Model Direct", payload

    model = get_json(f"http://127.0.0.1:{proxy_port}/v1/models/claude-opus-4-8")
    assert model["display_name"] == "MTPLX Qwen 27B Local", model


def assert_bare_core_advertises_upstream_model_only(proxy_port: int) -> None:
    payload = get_json(f"http://127.0.0.1:{proxy_port}/v1/models?limit=1000")
    ids = [item["id"] for item in payload["data"]]
    assert ids == ["fake-model"], payload


def assert_upstream_env_aliases(proxy_port: int) -> None:
    payload = get_json(f"http://127.0.0.1:{proxy_port}/v1/models?limit=1000")
    ids = [item["id"] for item in payload["data"]]
    assert ids == ["fake-model"], payload

    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "fake-model",
            "max_tokens": 24,
            "messages": [{"role": "user", "content": "check upstream api key alias"}],
        },
    )
    message = json.loads(raw)
    assert message["content"][0]["text"] == "Bearer alias-test-key", message


def assert_health_metrics(proxy_port: int) -> None:
    payload = get_json(f"http://127.0.0.1:{proxy_port}/healthz")
    metrics = payload["metrics"]
    assert metrics["requests_total"] >= 1, metrics
    assert metrics["messages_by_kind"].get("plain", 0) >= 1, metrics
    assert metrics["messages_by_kind"].get("tools_hidden", 0) >= 1, metrics
    assert metrics["messages_by_stream_mode"].get("direct", 0) >= 1, metrics
    assert metrics["messages_by_stream_mode"].get("nonstream", 0) >= 1, metrics
    assert metrics["tool_filters_by_reason"].get("schema_invalid", 0) >= 1, metrics
    assert metrics["provider_latency_by_kind"].get("plain", {}).get("count", 0) >= 1, metrics
    assert payload["provider_name"] == "openai-compatible", payload
    assert payload["provider"]["name"] == "openai-compatible", payload
    assert payload["provider"]["base_url"].startswith("http://127.0.0.1:"), payload
    assert payload["provider"]["http_referer_header_set"] is False, payload
    assert payload["stream_heartbeat_seconds"] == 0.05, payload


def start_proxy_process(
    fake_port: int,
    proxy_port: int,
    tool_mode: str,
    extra_args: list[str] | None = None,
) -> subprocess.Popen[bytes]:
    args = [
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
        "--tool-mode",
        tool_mode,
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.Popen(
        args,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def start_proxy_env_alias_process(
    fake_port: int,
    proxy_port: int,
) -> subprocess.Popen[bytes]:
    args = [
        sys.executable,
        str(ROOT / "proxy" / "anthropic_mtplx_proxy.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(proxy_port),
        "--tool-mode",
        "drop",
    ]
    env = os.environ.copy()
    env.pop("MTPLX_OPENAI_BASE_URL", None)
    env.pop("MTPLX_OPENAI_MODEL", None)
    env.pop("MTPLX_API_KEY", None)
    env["UPSTREAM_OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake_port}/v1"
    env["UPSTREAM_OPENAI_MODEL"] = "fake-model"
    env["UPSTREAM_API_KEY"] = "alias-test-key"
    return subprocess.Popen(
        args,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def start_run_proxy_profile_override_process(
    fake_port: int,
    proxy_port: int,
) -> tuple[subprocess.Popen[bytes], Path]:
    local_dir = ROOT / "_local"
    local_dir.mkdir(exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=local_dir,
        prefix="test-profile-",
        suffix=".env",
        delete=False,
    )
    profile_path = Path(handle.name)
    with handle:
        handle.write(
            "\n".join(
                [
                    "PROXY_PROVIDER_NAME=openai-compatible",
                    "PROXY_STREAM_MODE=buffered",
                    "PROXY_TOOL_MODE=drop",
                    "PROXY_CLAUDE_SCIENCE_COMPAT=0",
                    "",
                ]
            )
        )
    env = os.environ.copy()
    env["PROXY_PROFILE"] = str(profile_path)
    env["UPSTREAM_OPENAI_BASE_URL"] = f"http://127.0.0.1:{fake_port}/v1"
    env["UPSTREAM_OPENAI_MODEL"] = "fake-model"
    env["UPSTREAM_API_KEY"] = "profile-override-key"
    env["PROXY_HOST"] = "127.0.0.1"
    env["PROXY_PORT"] = str(proxy_port)
    env["PROXY_CLAUDE_SCIENCE_COMPAT"] = "1"
    return (
        subprocess.Popen(
            [str(ROOT / "scripts" / "run-proxy.sh")],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ),
        profile_path,
    )


def main() -> int:
    fake_server, fake_port = start_fake_server()
    proxy_port = free_port()
    proc = start_proxy_process(
        fake_port,
        proxy_port,
        "drop",
        ["--stream-heartbeat-seconds", "0.05"],
    )
    try:
        wait_for_proxy(proxy_port, proc)
        assert_models_endpoint(proxy_port)
        assert_text_stream(proxy_port)
        assert_long_text_stream(proxy_port)
        assert_direct_stream_heartbeat(proxy_port)
        assert_full_json_stream_fallback(proxy_port)
        assert_stream_error_event(proxy_port)
        assert_named_stream_error_event(proxy_port)
        assert_stream_read_exception_becomes_error_event()
        assert_stream_connection_closes(proxy_port)
        assert_client_cancellation_does_not_hang(proxy_port)
        assert_nonstream(proxy_port)
        assert_drop_mode_rejects_unforwarded_tool_calls(proxy_port)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    alias_proxy_port = free_port()
    alias_proc = start_proxy_env_alias_process(fake_port, alias_proxy_port)
    try:
        wait_for_proxy(alias_proxy_port, alias_proc)
        assert_upstream_env_aliases(alias_proxy_port)
    finally:
        alias_proc.terminate()
        try:
            alias_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            alias_proc.kill()

    profile_override_proxy_port = free_port()
    profile_override_proc, profile_override_path = start_run_proxy_profile_override_process(
        fake_port,
        profile_override_proxy_port,
    )
    try:
        wait_for_proxy(profile_override_proxy_port, profile_override_proc)
        health = get_json(f"http://127.0.0.1:{profile_override_proxy_port}/healthz")
        assert health["claude_science_compat"] is True, health
        assert health["advertised_models"] == ["fake-model"], health
        assert health["stream_mode"] == "buffered", health
        assert health["tool_mode"] == "drop", health
        assert_bare_core_advertises_upstream_model_only(profile_override_proxy_port)
    finally:
        profile_override_proc.terminate()
        try:
            profile_override_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            profile_override_proc.kill()
        profile_override_path.unlink(missing_ok=True)

    display_proxy_port = free_port()
    display_proc = start_proxy_process(
        fake_port,
        display_proxy_port,
        "drop",
        [
            "--model-display-names",
            '{"claude-opus-4-8":"MTPLX Qwen 27B Local","fake-model":"Fake Model Direct"}',
        ],
    )
    try:
        wait_for_proxy(display_proxy_port, display_proc)
        assert_custom_model_display_names(display_proxy_port)
    finally:
        display_proc.terminate()
        try:
            display_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            display_proc.kill()

    timeout_proxy_port = free_port()
    timeout_proc = start_proxy_process(
        fake_port,
        timeout_proxy_port,
        "drop",
        ["--timeout", "0.1"],
    )
    try:
        wait_for_proxy(timeout_proxy_port, timeout_proc)
        assert_nonstream_timeout_metric(timeout_proxy_port)
    finally:
        timeout_proc.terminate()
        try:
            timeout_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            timeout_proc.kill()

    pass_proxy_port = free_port()
    pass_proc = start_proxy_process(
        fake_port,
        pass_proxy_port,
        "pass",
        ["--stream-heartbeat-seconds", "0.05"],
    )
    try:
        wait_for_proxy(pass_proxy_port, pass_proc)
        assert_text_stream(pass_proxy_port)
        assert_tool_stream(pass_proxy_port)
        assert_split_streamed_tool_arguments(pass_proxy_port)
        assert_invalid_streamed_tool_filtered(pass_proxy_port)
        assert_nonstream(pass_proxy_port)
        assert_invalid_native_tool_filtered(pass_proxy_port, "invalid native tool json")
        assert_invalid_native_tool_filtered(pass_proxy_port, "unknown native tool")
        assert_invalid_native_tool_filtered(pass_proxy_port, "schema invalid native tool")
        assert_valid_python_tool_allowed(pass_proxy_port)
        assert_tool_choice_required(pass_proxy_port)
        assert_server_tools_not_forwarded_as_functions(pass_proxy_port)
        assert_health_metrics(pass_proxy_port)
    finally:
        pass_proc.terminate()
        try:
            pass_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass_proc.kill()

    allowlist_proxy_port = free_port()
    allowlist_proc = start_proxy_process(
        fake_port,
        allowlist_proxy_port,
        "pass",
        ["--tool-allowlist", "search_skills", "--harness-tools", "submit_output"],
    )
    try:
        wait_for_proxy(allowlist_proxy_port, allowlist_proc)
        assert_tool_allowlist(allowlist_proxy_port)
        assert_harness_tools_do_not_extend_general_allowlist(allowlist_proxy_port)
    finally:
        allowlist_proc.terminate()
        try:
            allowlist_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            allowlist_proc.kill()

    compat_proxy_port = free_port()
    compat_proc = start_proxy_process(
        fake_port,
        compat_proxy_port,
        "pass",
        ["--claude-science-compat", "1"],
    )
    try:
        wait_for_proxy(compat_proxy_port, compat_proc)
        assert_claude_science_tool_compat(compat_proxy_port)
    finally:
        compat_proc.terminate()
        try:
            compat_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            compat_proc.kill()

    fake_server.shutdown()
    print("streaming proxy tests passed")
    return 0


def test_streaming_proxy_harness() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
