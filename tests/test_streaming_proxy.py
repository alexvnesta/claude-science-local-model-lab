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
        if not payload.get("stream") and "check mtplx background guard" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "max_tokens": payload.get("max_tokens"),
                                        "roles": [
                                            message.get("role")
                                            for message in messages
                                            if isinstance(message, dict)
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
        if not payload.get("stream") and "check pass allowlist guard" in prompt:
            guard_present = any(
                message.get("role") == "system"
                and "this profile forwards only these Claude Science tools" in str(
                    message.get("content") or ""
                )
                and "hidden Claude Science tools inside Python" in str(
                    message.get("content") or ""
                )
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
        if not payload.get("stream") and "mtplx wrapper text" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "<mtplx_final_answer>wrapper stripped</mtplx_final_answer>",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                },
            )
            return
        if not payload.get("stream") and "strip thinking text" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "<think>private reasoning</think>\n\nvisible answer",
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
        if not payload.get("stream") and "check mentioned tool choice" in prompt:
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
        if not payload.get("stream") and "path-only python native tool" in prompt:
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
                                        "id": "call_python_path",
                                        "type": "function",
                                        "function": {
                                            "name": "python",
                                            "arguments": json.dumps(
                                                {
                                                    "code": "openrouter_free_probe.py",
                                                    "human_description": "Run generated file.",
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
        if not payload.get("stream") and "import-blob python native tool" in prompt:
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
                                        "id": "call_python_import_blob",
                                        "type": "function",
                                        "function": {
                                            "name": "python",
                                            "arguments": json.dumps(
                                                {
                                                    "code": (
                                                        "import "
                                                        + ", ".join(
                                                            f"pkg_{idx}" for idx in range(80)
                                                        )
                                                    ),
                                                    "human_description": "Start analysis.",
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
        if not payload.get("stream") and "tool-smuggled python native tool" in prompt:
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
                                        "id": "call_python_tool_smuggled",
                                        "type": "function",
                                        "function": {
                                            "name": "python",
                                            "arguments": json.dumps(
                                                {
                                                    "code": (
                                                        "# Load figure-style skill\n"
                                                        'skill({"skill": "figure-style"})'
                                                    ),
                                                    "human_description": "Load a skill.",
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
        if not payload.get("stream") and "assigned tool-smuggled python native tool" in prompt:
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
                                        "id": "call_python_assigned_tool_smuggled",
                                        "type": "function",
                                        "function": {
                                            "name": "python",
                                            "arguments": json.dumps(
                                                {
                                                    "code": (
                                                        "# Check available MCP servers\n"
                                                        'mcp_skills = search_skills({"prefix": "mcp-"})\n'
                                                        "print(mcp_skills)"
                                                    ),
                                                    "human_description": (
                                                        "Listing available MCP servers and compute"
                                                    ),
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
        if not payload.get("stream") and "kernel python native tool" in prompt:
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
                                        "id": "call_python_kernel",
                                        "type": "function",
                                        "function": {
                                            "name": "python",
                                            "arguments": json.dumps(
                                                {
                                                    "code": (
                                                        "import kernel\n"
                                                        'mcp_skills = kernel.search_skills({"prefix": "mcp-"})'
                                                    ),
                                                    "human_description": (
                                                        "Searching for cancer genomics MCP skills"
                                                    ),
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
        if not payload.get("stream") and "host skills python native tool" in prompt:
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
                                        "id": "call_python_host_skills",
                                        "type": "function",
                                        "function": {
                                            "name": "python",
                                            "arguments": json.dumps(
                                                {
                                                    "code": (
                                                        "mcp = host.skills.list()\n"
                                                        "print([s.get('name') for s in mcp])"
                                                    ),
                                                    "human_description": (
                                                        "Searching for cancer-related MCP servers"
                                                    ),
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
        if not payload.get("stream") and "metadata repair native tool" in prompt:
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
                                        "id": "call_metadata_repair",
                                        "type": "function",
                                        "function": {
                                            "name": "search_skills",
                                            "arguments": "{\"query\":\"figure visualization\"}",
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
        if not payload.get("stream") and "submit output bullet repair native tool" in prompt:
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
                                        "id": "call_submit_output_bullets",
                                        "type": "function",
                                        "function": {
                                            "name": "submit_output",
                                            "arguments": json.dumps(
                                                {
                                                    "verdict": "pass",
                                                    "human_description": "Submit review.",
                                                    "findings": [],
                                                    "_completion_bullets": "- Checked artifact IDs\n- Verified generated figure",
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
        if not payload.get("stream") and "xmlish unclosed arguments text tool call" in prompt:
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
                                    '<parameter=arguments>\n{"verdict":"pass","findings":[]}\n'
                                    "<parameter=name>\nsubmit_output\n"
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
        if not payload.get("stream") and "preamble xmlish unclosed text tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "I will call the reviewer tool now.\n"
                                    "<tool_call>\n"
                                    "<function=submit_output>\n"
                                    "<parameter=verdict>\npass\n"
                                    "<parameter=findings>\n[]\n"
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
        if not payload.get("stream") and "unavailable repl text tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "I'll use the repl tool for skill discovery.\n\n"
                                    "<tool_call>\n"
                                    "<function=repl>\n"
                                    "<parameter=human_description>Searching for cancer-related MCP servers\n"
                                    "<parameter=code>mcp = host.skills.list()\n"
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

        if "stream harness reviewer tools" in prompt:
            names = [
                item.get("function", {}).get("name")
                for item in payload.get("tools") or []
                if isinstance(item, dict)
            ]
            seen = json.dumps(
                {"tool_choice": payload.get("tool_choice"), "tool_names": names},
                sort_keys=True,
            )
            midpoint = len(seen) // 2
            self._sse(
                [
                    {"choices": [{"delta": {"role": "assistant"}}]},
                    {"choices": [{"delta": {"content": seen[:midpoint]}}]},
                    {
                        "choices": [
                            {
                                "delta": {"content": seen[midpoint:]},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                ],
                delay=0.001,
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


def assert_invalid_python_tool_filtered(proxy_port: int, prompt: str) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [python_tool()],
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "end_turn", payload
    assert all(block.get("type") != "tool_use" for block in payload["content"]), payload


def assert_unavailable_text_tool_markup_filtered(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [python_tool()],
            "messages": [{"role": "user", "content": "unavailable repl text tool call"}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "end_turn", payload
    text = payload["content"][0]["text"]
    assert "<tool_call>" not in text, payload
    assert "host.skills" not in text, payload
    assert "cannot call that tool from this local profile" in text, payload


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


def assert_metadata_tool_repaired(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [search_skills_tool()],
            "messages": [{"role": "user", "content": "metadata repair native tool"}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "tool_use", payload
    block = payload["content"][0]
    assert block["name"] == "search_skills", payload
    assert block["input"]["query"] == "figure visualization", payload
    assert block["input"]["human_description"].startswith("Local proxy repaired"), payload


def assert_submit_output_bullets_repaired(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [submit_output_tool()],
            "messages": [{"role": "user", "content": "submit output bullet repair native tool"}],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "tool_use", payload
    block = payload["content"][0]
    assert block["name"] == "submit_output", payload
    assert block["input"]["_completion_bullets"] == [
        "Checked artifact IDs",
        "Verified generated figure",
    ], payload


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


def assert_pass_allowlist_guard(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [bash_tool(), search_skills_tool()],
            "messages": [{"role": "user", "content": "check pass allowlist guard"}],
        },
    )
    payload = json.loads(raw)
    assert payload["content"][0]["text"] == "guard present", payload


def assert_harness_tool_allowlist_bypass(proxy_port: int) -> None:
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
    assert upstream_seen["tool_names"] == ["search_skills", "submit_output"], upstream_seen


def assert_harness_tool_specific_allowlist(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [
                bash_tool(),
                search_skills_tool(),
                repl_tool(),
                read_file_tool(),
                submit_output_tool(),
            ],
            "messages": [{"role": "user", "content": "check harness allowlist"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == [
        "repl",
        "read_file",
        "submit_output",
    ], upstream_seen


def assert_streamed_harness_uses_reviewer_allowlist(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "tool_choice": {"type": "any"},
            "tools": [
                bash_tool(),
                search_skills_tool(),
                repl_tool(),
                read_file_tool(),
                submit_output_tool(),
            ],
            "messages": [{"role": "user", "content": "stream harness reviewer tools"}],
        },
    )
    events = parse_sse(raw)
    upstream_seen = json.loads(stream_text(events))
    assert upstream_seen["tool_names"] == [
        "repl",
        "read_file",
        "submit_output",
    ], upstream_seen
    assert upstream_seen["tool_choice"] == "required", upstream_seen
    metrics = get_json(f"http://127.0.0.1:{proxy_port}/healthz")["metrics"]
    assert metrics["messages_by_kind"].get("harness", 0) >= 1, metrics
    assert metrics["messages_by_stream_mode"].get("direct", 0) >= 1, metrics


def assert_harness_closeout_forces_submit_only(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [
                search_skills_tool(),
                repl_tool(),
                read_file_tool(),
                submit_output_tool(),
            ],
            "messages": [
                {"role": "user", "content": "review output"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_repl_1",
                            "name": "repl",
                            "input": {"human_description": "Inspect TSV", "code": "print('ok')"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_repl_1",
                            "content": "ok",
                        }
                    ],
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_read_1",
                            "name": "read_file",
                            "input": {"human_description": "Inspect figure", "version_id": "v1"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_read_1",
                            "content": "ok",
                        },
                        {"type": "text", "text": "check harness allowlist"},
                    ],
                },
            ],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == ["submit_output"], upstream_seen
    assert upstream_seen["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_output"},
    }, upstream_seen


def assert_single_harness_tool_forced(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [submit_output_tool()],
            "messages": [{"role": "user", "content": "check harness tool choice"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == ["submit_output"], upstream_seen
    assert upstream_seen["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_output"},
    }, upstream_seen


def assert_completed_harness_tool_not_forced(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tool_choice": {"type": "any"},
            "tools": [submit_output_tool()],
            "messages": [
                {"role": "user", "content": "review this output"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_review_1",
                            "name": "submit_output",
                            "input": {"verdict": "pass", "findings": []},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_review_1",
                            "content": '{"ok":true}',
                        },
                        {"type": "text", "text": "check completed harness followup"},
                    ],
                },
            ],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == ["submit_output"], upstream_seen
    assert upstream_seen["tool_choice"] == "auto", upstream_seen


def assert_mentioned_tool_forced(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [search_skills_tool(), {
                "name": "skill",
                "description": "load skill",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "human_description": {"type": "string"},
                        "skill": {"type": "string"},
                    },
                    "required": ["human_description", "skill"],
                },
            }],
            "messages": [
                {
                    "role": "user",
                    "content": "check mentioned tool choice: use the skill tool once",
                }
            ],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_choice"] == {
        "type": "function",
        "function": {"name": "skill"},
    }, upstream_seen


def assert_natural_call_tool_forced(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [
                python_tool(),
                {
                    "name": "save_artifacts",
                    "description": "save files as artifacts",
                    "input_schema": {
                        "type": "object",
                        "properties": {"files": {"type": "array", "items": {"type": "string"}}},
                        "required": ["files"],
                    },
                },
                search_skills_tool(),
            ],
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "check mentioned tool choice: call python to create a figure, "
                        "then call save_artifacts after python succeeds"
                    ),
                }
            ],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_choice"] == {
        "type": "function",
        "function": {"name": "python"},
    }, upstream_seen


def assert_deferred_python_tool_forced(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [
                python_tool(),
                {
                    "name": "save_artifacts",
                    "description": "save files as artifacts",
                    "input_schema": {
                        "type": "object",
                        "properties": {"files": {"type": "array", "items": {"type": "string"}}},
                        "required": ["files"],
                    },
                },
            ],
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "check mentioned tool choice: make a plot with the python tool. "
                        "After python returns, call save_artifacts."
                    ),
                }
            ],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_choice"] == {
        "type": "function",
        "function": {"name": "python"},
    }, upstream_seen


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


def assert_wrapper_text_cleaned(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "mtplx wrapper text"}],
        },
    )
    payload = json.loads(raw)
    assert payload["content"][0]["text"] == "wrapper stripped", payload


def assert_thinking_text_stripped(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "strip thinking text"}],
        },
    )
    payload = json.loads(raw)
    assert payload["content"][0]["text"] == "visible answer", payload


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


def assert_mtplx_background_guard(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "system": "Tiny helper system prompt.",
            "max_tokens": 24,
            "messages": [{"role": "user", "content": "check mtplx background guard"}],
        },
    )
    payload = json.loads(raw)
    content = json.loads(payload["content"][0]["text"])
    assert content["max_tokens"] == 49, payload
    assert content["roles"] == ["system", "user"], payload


def assert_upstream_env_aliases(proxy_port: int) -> None:
    payload = get_json(f"http://127.0.0.1:{proxy_port}/v1/models?limit=1000")
    ids = [item["id"] for item in payload["data"]]
    assert ids == ["claude-opus-4-8", "fake-model"], payload

    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
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
    assert metrics["tool_filters_by_reason"].get("python_sanity", 0) >= 1, metrics
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
        "--parse-text-tool-calls",
        "1",
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
        "--parse-text-tool-calls",
        "1",
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
        assert_tool_stream(proxy_port)
        assert_split_streamed_tool_arguments(proxy_port)
        assert_invalid_streamed_tool_filtered(proxy_port)
        assert_full_json_stream_fallback(proxy_port)
        assert_stream_error_event(proxy_port)
        assert_stream_connection_closes(proxy_port)
        assert_client_cancellation_does_not_hang(proxy_port)
        assert_nonstream(proxy_port)
        assert_wrapper_text_cleaned(proxy_port)
        assert_invalid_native_tool_filtered(proxy_port, "invalid native tool json")
        assert_invalid_native_tool_filtered(proxy_port, "unknown native tool")
        assert_invalid_native_tool_filtered(proxy_port, "schema invalid native tool")
        assert_invalid_python_tool_filtered(proxy_port, "path-only python native tool")
        assert_invalid_python_tool_filtered(proxy_port, "import-blob python native tool")
        assert_invalid_python_tool_filtered(proxy_port, "tool-smuggled python native tool")
        assert_invalid_python_tool_filtered(proxy_port, "assigned tool-smuggled python native tool")
        assert_invalid_python_tool_filtered(proxy_port, "kernel python native tool")
        assert_invalid_python_tool_filtered(proxy_port, "host skills python native tool")
        assert_unavailable_text_tool_markup_filtered(proxy_port)
        assert_valid_python_tool_allowed(proxy_port)
        assert_metadata_tool_repaired(proxy_port)
        assert_submit_output_bullets_repaired(proxy_port)
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
        assert_text_tool_call_adapter(
            proxy_port,
            "xmlish unclosed arguments text tool call",
            include_extra_tools=True,
        )
        assert_text_tool_call_adapter(
            proxy_port,
            "preamble xmlish unclosed text tool call",
            include_extra_tools=True,
        )
        assert_health_metrics(proxy_port)
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

    mtplx_guard_proxy_port = free_port()
    mtplx_guard_proc = start_proxy_process(
        fake_port,
        mtplx_guard_proxy_port,
        "drop",
        ["--mtplx-avoid-background-bypass", "1"],
    )
    try:
        wait_for_proxy(mtplx_guard_proxy_port, mtplx_guard_proc)
        assert_mtplx_background_guard(mtplx_guard_proxy_port)
    finally:
        mtplx_guard_proc.terminate()
        try:
            mtplx_guard_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mtplx_guard_proc.kill()

    pass_proxy_port = free_port()
    pass_proc = start_proxy_process(fake_port, pass_proxy_port, "pass")
    try:
        wait_for_proxy(pass_proxy_port, pass_proc)
        assert_tool_choice_required(pass_proxy_port)
        assert_single_harness_tool_forced(pass_proxy_port)
        assert_completed_harness_tool_not_forced(pass_proxy_port)
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
        ["--tool-allowlist", "search_skills"],
    )
    try:
        wait_for_proxy(allowlist_proxy_port, allowlist_proc)
        assert_tool_allowlist(allowlist_proxy_port)
        assert_pass_allowlist_guard(allowlist_proxy_port)
        assert_harness_tool_allowlist_bypass(allowlist_proxy_port)
    finally:
        allowlist_proc.terminate()
        try:
            allowlist_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            allowlist_proc.kill()

    harness_allowlist_proxy_port = free_port()
    harness_allowlist_proc = start_proxy_process(
        fake_port,
        harness_allowlist_proxy_port,
        "pass",
        [
            "--tool-allowlist",
            "search_skills",
            "--harness-tool-allowlist",
            "repl,read_file,submit_output",
            "--harness-force-submit-after-tool-results",
            "2",
        ],
    )
    try:
        wait_for_proxy(harness_allowlist_proxy_port, harness_allowlist_proc)
        assert_harness_tool_specific_allowlist(harness_allowlist_proxy_port)
        assert_streamed_harness_uses_reviewer_allowlist(harness_allowlist_proxy_port)
        assert_harness_closeout_forces_submit_only(harness_allowlist_proxy_port)
    finally:
        harness_allowlist_proc.terminate()
        try:
            harness_allowlist_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            harness_allowlist_proc.kill()

    force_proxy_port = free_port()
    force_proc = start_proxy_process(
        fake_port,
        force_proxy_port,
        "pass",
        ["--force-mentioned-tool", "1"],
    )
    try:
        wait_for_proxy(force_proxy_port, force_proc)
        assert_mentioned_tool_forced(force_proxy_port)
        assert_natural_call_tool_forced(force_proxy_port)
        assert_deferred_python_tool_forced(force_proxy_port)
    finally:
        force_proc.terminate()
        try:
            force_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            force_proc.kill()

    compat_proxy_port = free_port()
    compat_proc = start_proxy_process(
        fake_port,
        compat_proxy_port,
        "drop",
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

    strip_proxy_port = free_port()
    strip_proc = start_proxy_process(
        fake_port,
        strip_proxy_port,
        "drop",
        ["--strip-thinking-text", "1"],
    )
    try:
        wait_for_proxy(strip_proxy_port, strip_proc)
        assert_thinking_text_stripped(strip_proxy_port)
    finally:
        strip_proc.terminate()
        try:
            strip_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            strip_proc.kill()
        fake_server.shutdown()
    print("streaming proxy tests passed")
    return 0


def test_streaming_proxy_harness() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
