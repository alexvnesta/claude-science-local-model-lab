#!/usr/bin/env python3
"""Integration tests for the Anthropic-to-OpenAI streaming bridge."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_PRUNED_FOREGROUND_TOOL_NAMES = [
    "web_search",
    "bash",
    "python",
    "r",
    "repl",
    "save_artifacts",
    "read_file",
    "edit_file",
    "manage_environments",
    "manage_packages",
    "fetch_article_fulltext",
    "list_compute",
    "compute_details",
    "ask_about_compute",
    "skill",
    "ask_user",
    "search_skills",
    "summary_query",
    "boundary",
    "request_network_access",
    "list_host_grants",
    "request_host_access",
    "delete_host_files",
    "update_step_status",
    "wait_for_notification",
    "generate_plan",
]


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    server_version = "FakeOpenAI/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _count_request(self, key: str) -> None:
        lock = getattr(self.server, "request_counts_lock", None)
        counts = getattr(self.server, "request_counts", None)
        if lock is None or counts is None:
            return
        with lock:
            counts[key] = counts.get(key, 0) + 1

    def _remember_payload(self, key: str, payload: dict[str, Any]) -> None:
        lock = getattr(self.server, "request_payloads_lock", None)
        payloads = getattr(self.server, "request_payloads", None)
        if lock is None or payloads is None:
            return
        with lock:
            payloads[key] = payload

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
        if self.path == "/search":
            self._remember_payload("tavily_search", payload)
            self._json(
                200,
                {
                    "results": [
                        {
                            "title": "Example Source",
                            "url": "https://example.com/result",
                            "content": "Example Source says the proxy-owned web search bridge works.",
                            "score": 0.98,
                            "published_date": "July 1, 2026",
                        }
                    ]
                },
            )
            return
        if self.path == "/v2/search":
            self._remember_payload("firecrawl_search", payload)
            self._json(
                200,
                {
                    "success": True,
                    "data": {
                        "web": [
                            {
                                "title": "Example Firecrawl Source",
                                "url": "https://example.com/firecrawl-result",
                                "description": "Firecrawl says the proxy-owned web search bridge works.",
                            }
                        ]
                    },
                    "creditsUsed": 2,
                },
            )
            return
        messages = payload.get("messages") or []
        prompt = json.dumps(messages)
        if not payload.get("stream") and "coalesce proxy owned server web search" in prompt:
            self._count_request("coalesce_proxy_owned_upstream")
        if not payload.get("stream") and "proxy owned server web search" in prompt:
            if (
                "slow proxy owned server web search" in prompt
                or "coalesce proxy owned server web search" in prompt
            ) and not any(
                isinstance(message, dict) and message.get("role") == "tool"
                for message in messages
            ):
                time.sleep(0.15)
            if any(
                message.get("role") == "tool"
                and (
                    "Example Source" in str(message.get("content") or "")
                    or "Example Firecrawl Source" in str(message.get("content") or "")
                )
                for message in messages
                if isinstance(message, dict)
            ):
                self._json(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "Example Source confirms the bridge works: https://example.com/result",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                    },
                )
                return
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
                                        "id": "call_proxy_web_search",
                                        "type": "function",
                                        "function": {
                                            "name": "web_search",
                                            "arguments": json.dumps(
                                                {"query": "proxy owned server web search"}
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 4},
                },
            )
            return
        if not payload.get("stream") and "proxy owned raw web search" in prompt:
            if any(
                message.get("role") == "tool"
                and (
                    "Example Source" in str(message.get("content") or "")
                    or "Example Firecrawl Source" in str(message.get("content") or "")
                )
                for message in messages
                if isinstance(message, dict)
            ):
                self._json(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": (
                                        "Raw web search bridge works: "
                                        "https://example.com/result"
                                    ),
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                    },
                )
                return
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "<call_tool name=\"web_search\">\n"
                                    "<parameter=query>proxy owned raw web search</parameter>\n"
                                    "</call_tool>"
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 4},
                },
            )
            return
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
        if not payload.get("stream") and "check exact tool definitions" in prompt:
            forwarded = [
                item.get("function", {})
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
                                "content": json.dumps({"tools": forwarded}),
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
        if not payload.get("stream") and "check harness pass through" in prompt:
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
        if not payload.get("stream") and "check app-pruned tool pass through" in prompt:
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
        if not payload.get("stream") and "check server tool omission" in prompt:
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
        if not payload.get("stream") and "generate plan approve repair native tool" in prompt:
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
                                        "id": "call_generate_plan_repair",
                                        "type": "function",
                                        "function": {
                                            "name": "generate_plan",
                                            "arguments": json.dumps(
                                                {
                                                    "approve": True,
                                                    "human_description": (
                                                        "Generating plan for TE expression"
                                                    ),
                                                    "task_summary": (
                                                        "Plan a public TE expression "
                                                        "analysis in breast cancer."
                                                    ),
                                                    "steps": [
                                                        {
                                                            "title": "Inventory datasets",
                                                            "description": (
                                                                "Find usable processed TE "
                                                                "expression resources."
                                                            ),
                                                        }
                                                    ],
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
        if not payload.get("stream") and "server loop raw skill text tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "<tool_call>\n"
                                    "<function=skill>\n"
                                    "<parameter=skill>\n"
                                    "mcp-cellguide\n"
                                    "</parameter>\n"
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
        if not payload.get("stream") and "server loop call_tool search_skills text tool call" in prompt:
            self._json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "<call_tool name=\"search_skills\">\n"
                                    "<parameter=query> transposon TE retrotransposon expression analysis\n"
                                    "</parameter>\n"
                                    "</call_tool>"
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
    server.request_counts = {}
    server.request_counts_lock = threading.Lock()
    server.request_payloads = {}
    server.request_payloads_lock = threading.Lock()
    port = int(server.server_address[1])
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
    assert "event: ping\ndata: {\"type\":\"ping\"}\n\n" in raw, raw
    events = parse_sse(raw)
    assert any(name == "ping" and event.get("type") == "ping" for name, event in events), events
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


def skill_tool() -> dict[str, Any]:
    return {
        "name": "skill",
        "description": "load skill",
        "input_schema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string"},
                "human_description": {"type": "string"},
                "skill": {"type": "string"},
            },
            "required": ["human_description", "skill"],
        },
    }


def exact_definition_probe_tool() -> dict[str, Any]:
    return {
        "name": "definition_probe",
        "description": (
            "Preserve this active tool description exactly; do not trim, summarize, "
            "or rewrite it before sending the request upstream. "
            "It includes operational guidance that the model must see."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Exact user-facing lookup request.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["quick", "deep"],
                    "description": "Controls whether the tool should do a quick or deep lookup.",
                },
                "limits": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "max_rows": {"type": "integer", "minimum": 1},
                        "include_private": {"type": "boolean"},
                    },
                    "required": ["max_rows"],
                },
            },
            "required": ["query", "mode"],
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


def generate_plan_tool() -> dict[str, Any]:
    return {
        "name": "generate_plan",
        "description": (
            "Create or revise an execution plan. Use approve=true alone only to approve "
            "the current plan."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "approve": {"type": "boolean"},
                "human_description": {"type": "string"},
                "task_summary": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "object"}},
                "desired_outputs": {"type": "array", "items": {"type": "string"}},
                "feasibility": {"type": "object"},
            },
            "required": ["human_description"],
        },
    }


def generic_tool(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"{name} tool",
        "input_schema": {"type": "object"},
    }


def anthropic_server_web_search_tool() -> dict[str, Any]:
    return {"type": "web_search_20250305", "name": "web_search"}


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


def assert_generate_plan_approve_content_repaired(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [generate_plan_tool()],
            "messages": [
                {"role": "user", "content": "generate plan approve repair native tool"}
            ],
        },
    )
    payload = json.loads(raw)
    assert payload["stop_reason"] == "tool_use", payload
    block = payload["content"][0]
    assert block["name"] == "generate_plan", payload
    assert block["input"]["task_summary"].startswith("Plan a public TE expression"), payload
    assert block["input"]["steps"][0]["title"] == "Inventory datasets", payload
    assert "approve" not in block["input"], payload


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


def assert_active_tool_definitions_are_lossless(proxy_port: int) -> None:
    tool = exact_definition_probe_tool()
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [tool],
            "messages": [{"role": "user", "content": "check exact tool definitions"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tools"] == [
        {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        }
    ], upstream_seen


def assert_app_pruned_foreground_tools_pass_through(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tools": [
                generic_tool(name)
                for name in APP_PRUNED_FOREGROUND_TOOL_NAMES
            ],
            "messages": [{"role": "user", "content": "check app-pruned tool pass through"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == APP_PRUNED_FOREGROUND_TOOL_NAMES, upstream_seen


def assert_anthropic_server_tools_are_not_forwarded(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "max_tokens": 64,
            "tool_choice": {"type": "tool", "name": "web_search"},
            "tools": [
                anthropic_server_web_search_tool(),
                bash_tool(),
            ],
            "messages": [{"role": "user", "content": "check server tool omission"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == ["bash"], upstream_seen
    assert upstream_seen["tool_choice"] is None, upstream_seen


def assert_proxy_owned_server_web_search(
    proxy_port: int, fake_server: ThreadingHTTPServer
) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 128,
            "tool_choice": {"type": "tool", "name": "web_search"},
            "tools": [
                {
                    **anthropic_server_web_search_tool(),
                    "max_uses": 2,
                    "allowed_domains": ["example.com"],
                    "blocked_domains": ["blocked.example"],
                }
            ],
            "messages": [{"role": "user", "content": "proxy owned server web search"}],
        },
    )
    events = parse_sse(raw)
    starts = [
        event.get("content_block", {})
        for name, event in events
        if name == "content_block_start"
    ]
    assert any(block.get("type") == "server_tool_use" for block in starts), events
    results = [
        block
        for block in starts
        if block.get("type") == "web_search_tool_result"
    ]
    assert results, events
    assert results[0]["content"][0]["url"] == "https://example.com/result", results
    assert "Example Source confirms" in stream_text(events), stream_text(events)
    tavily_payload = fake_request_payload(fake_server, "tavily_search")
    assert tavily_payload["include_domains"] == ["example.com"], tavily_payload
    assert "exclude_domains" not in tavily_payload, tavily_payload
    assert not any(block.get("type") == "tool_use" for block in starts), events
    usage_events = [
        event
        for name, event in events
        if name == "message_delta"
    ]
    assert usage_events[-1]["usage"]["server_tool_use"]["web_search_requests"] == 1, usage_events

    health = get_json(f"http://127.0.0.1:{proxy_port}/healthz")
    assert health["server_web_search"]["mode"] == "tavily", health
    assert health["server_web_search"]["tavily_key_set"] is True, health
    assert health["metrics"]["messages_by_stream_mode"].get("server_tool_loop", 0) >= 1, health


def assert_proxy_owned_raw_server_web_search(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 128,
            "tool_choice": {"type": "tool", "name": "web_search"},
            "tools": [
                {
                    **anthropic_server_web_search_tool(),
                    "max_uses": 2,
                    "allowed_domains": ["example.com"],
                }
            ],
            "messages": [{"role": "user", "content": "proxy owned raw web search"}],
        },
    )
    events = parse_sse(raw)
    starts = [
        event.get("content_block", {})
        for name, event in events
        if name == "content_block_start"
    ]
    server_uses = [block for block in starts if block.get("type") == "server_tool_use"]
    assert server_uses, events
    assert server_uses[0]["name"] == "web_search", server_uses
    results = [
        block
        for block in starts
        if block.get("type") == "web_search_tool_result"
    ]
    assert results, events
    assert results[0]["content"][0]["url"] == "https://example.com/result", results
    assert "Raw web search bridge works" in stream_text(events), stream_text(events)
    assert "cannot call that tool from this local profile" not in stream_text(events), events
    health = get_json(f"http://127.0.0.1:{proxy_port}/healthz")
    assert health["metrics"]["messages_by_stream_mode"].get("server_tool_loop", 0) >= 1, health


def assert_proxy_owned_server_web_search_stream_heartbeat(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 128,
            "tool_choice": {"type": "tool", "name": "web_search"},
            "tools": [
                {
                    **anthropic_server_web_search_tool(),
                    "max_uses": 2,
                    "allowed_domains": ["example.com"],
                }
            ],
            "messages": [{"role": "user", "content": "slow proxy owned server web search"}],
        },
    )
    assert ": heartbeat\n\n" in raw, raw
    assert "event: ping\ndata: {\"type\":\"ping\"}\n\n" in raw, raw
    assert raw.index("event: message_start") < raw.index(": heartbeat"), raw
    assert raw.index(": heartbeat") < raw.index("event: content_block_start"), raw
    assert raw.index("event: ping") < raw.index("event: content_block_start"), raw
    events = parse_sse(raw)
    names = [name for name, _ in events]
    assert names.count("message_start") == 1, names
    starts = [
        event.get("content_block", {})
        for name, event in events
        if name == "content_block_start"
    ]
    assert any(block.get("type") == "server_tool_use" for block in starts), events
    assert "Example Source confirms" in stream_text(events), stream_text(events)


def fake_request_count(server: ThreadingHTTPServer, key: str) -> int:
    lock = getattr(server, "request_counts_lock")
    counts = getattr(server, "request_counts")
    with lock:
        return int(counts.get(key, 0))


def fake_request_payload(server: ThreadingHTTPServer, key: str) -> dict[str, Any]:
    lock = getattr(server, "request_payloads_lock")
    payloads = getattr(server, "request_payloads")
    with lock:
        payload = payloads.get(key)
    assert isinstance(payload, dict), (key, payloads)
    return payload


def proxy_owned_web_search_payload(prompt: str) -> dict[str, Any]:
    return {
        "model": "claude-opus-4-8",
        "stream": True,
        "max_tokens": 128,
        "tool_choice": {"type": "tool", "name": "web_search"},
        "tools": [
            {
                **anthropic_server_web_search_tool(),
                "max_uses": 2,
                "allowed_domains": ["example.com"],
            }
        ],
        "messages": [{"role": "user", "content": prompt}],
    }


def assert_server_tool_loop_retry_reuses_finished_job(
    proxy_port: int, fake_server: ThreadingHTTPServer
) -> None:
    payload = proxy_owned_web_search_payload("coalesce proxy owned server web search")
    request = urllib.request.Request(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    response = urllib.request.urlopen(request, timeout=10)
    seen = ""
    deadline = time.monotonic() + 5
    try:
        while "event: ping" not in seen and time.monotonic() < deadline:
            line = response.readline().decode("utf-8", "replace")
            if not line:
                break
            seen += line
    finally:
        response.close()
    assert "event: ping" in seen, seen

    time.sleep(0.35)
    assert fake_request_count(fake_server, "coalesce_proxy_owned_upstream") == 2

    raw = post_json(f"http://127.0.0.1:{proxy_port}/v1/messages", payload)
    events = parse_sse(raw)
    assert "Example Source confirms" in stream_text(events), stream_text(events)
    assert fake_request_count(fake_server, "coalesce_proxy_owned_upstream") == 2


def assert_proxy_owned_server_web_search_firecrawl(
    proxy_port: int, fake_server: ThreadingHTTPServer
) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 128,
            "tool_choice": {"type": "tool", "name": "web_search"},
            "tools": [
                {
                    **anthropic_server_web_search_tool(),
                    "max_uses": 2,
                    "allowed_domains": ["example.com"],
                    "blocked_domains": ["blocked.example"],
                }
            ],
            "messages": [{"role": "user", "content": "proxy owned server web search"}],
        },
    )
    events = parse_sse(raw)
    starts = [
        event.get("content_block", {})
        for name, event in events
        if name == "content_block_start"
    ]
    results = [
        block
        for block in starts
        if block.get("type") == "web_search_tool_result"
    ]
    assert results, events
    assert results[0]["content"][0]["url"] == "https://example.com/firecrawl-result", results
    assert "Example Source confirms" in stream_text(events), stream_text(events)
    firecrawl_payload = fake_request_payload(fake_server, "firecrawl_search")
    assert firecrawl_payload["includeDomains"] == ["example.com"], firecrawl_payload
    assert "excludeDomains" not in firecrawl_payload, firecrawl_payload
    health = get_json(f"http://127.0.0.1:{proxy_port}/healthz")
    assert health["server_web_search"]["mode"] == "firecrawl", health
    assert health["server_web_search"]["firecrawl_key_set"] is True, health


def assert_harness_tools_pass_through(proxy_port: int) -> None:
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
            "messages": [{"role": "user", "content": "check harness pass through"}],
        },
    )
    payload = json.loads(raw)
    upstream_seen = json.loads(payload["content"][0]["text"])
    assert upstream_seen["tool_names"] == [
        "bash",
        "search_skills",
        "repl",
        "read_file",
        "submit_output",
    ], upstream_seen


def assert_streamed_harness_tools_pass_through(proxy_port: int) -> None:
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
        "bash",
        "search_skills",
        "repl",
        "read_file",
        "submit_output",
    ], upstream_seen
    assert upstream_seen["tool_choice"] == "required", upstream_seen
    metrics = get_json(f"http://127.0.0.1:{proxy_port}/healthz")["metrics"]
    assert metrics["messages_by_kind"].get("harness", 0) >= 1, metrics
    assert metrics["messages_by_stream_mode"].get("direct", 0) >= 1, metrics


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


def assert_server_loop_raw_skill_text_tool_repaired(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "tools": [
                {**anthropic_server_web_search_tool(), "max_uses": 1},
                skill_tool(),
                search_skills_tool(),
            ],
            "messages": [
                {"role": "user", "content": "server loop raw skill text tool call"}
            ],
        },
    )
    events = parse_sse(raw)
    tool_starts = [
        event.get("content_block", {})
        for name, event in events
        if name == "content_block_start"
        and event.get("content_block", {}).get("type") == "tool_use"
    ]
    assert len(tool_starts) == 1, events
    assert tool_starts[0]["name"] == "skill", events
    input_deltas = [
        event["delta"]["partial_json"]
        for name, event in events
        if name == "content_block_delta"
        and event.get("delta", {}).get("type") == "input_json_delta"
    ]
    assert input_deltas, events
    tool_input = json.loads(input_deltas[0])
    assert tool_input["skill"] == "mcp-cellguide", tool_input
    assert tool_input["human_description"].startswith("Local proxy repaired"), tool_input
    assert "cannot call that tool from this local profile" not in stream_text(events), events
    stop = [
        event["delta"]["stop_reason"]
        for name, event in events
        if name == "message_delta"
    ]
    assert stop == ["tool_use"], events


def assert_server_loop_call_tool_text_tool_repaired(proxy_port: int) -> None:
    raw = post_json(
        f"http://127.0.0.1:{proxy_port}/v1/messages",
        {
            "model": "claude-opus-4-8",
            "stream": True,
            "max_tokens": 64,
            "tools": [
                {**anthropic_server_web_search_tool(), "max_uses": 1},
                skill_tool(),
                search_skills_tool(),
            ],
            "messages": [
                {
                    "role": "user",
                    "content": "server loop call_tool search_skills text tool call",
                }
            ],
        },
    )
    events = parse_sse(raw)
    tool_starts = [
        event.get("content_block", {})
        for name, event in events
        if name == "content_block_start"
        and event.get("content_block", {}).get("type") == "tool_use"
    ]
    assert len(tool_starts) == 1, events
    assert tool_starts[0]["name"] == "search_skills", events
    input_deltas = [
        event["delta"]["partial_json"]
        for name, event in events
        if name == "content_block_delta"
        and event.get("delta", {}).get("type") == "input_json_delta"
    ]
    assert input_deltas, events
    tool_input = json.loads(input_deltas[0])
    assert tool_input["query"] == "transposon TE retrotransposon expression analysis", tool_input
    assert tool_input["human_description"].startswith("Local proxy repaired"), tool_input
    assert "cannot call that tool from this local profile" not in stream_text(events), events
    stop = [
        event["delta"]["stop_reason"]
        for name, event in events
        if name == "message_delta"
    ]
    assert stop == ["tool_use"], events


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


def assert_request_debug_capture(fake_port: int) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        shape_path = temp / "request-shape.jsonl"
        raw_dir = temp / "raw-captures"
        proxy_port = free_port()
        proc = start_proxy_process(
            fake_port,
            proxy_port,
            "pass",
            [
                "--request-shape-log-path",
                str(shape_path),
                "--raw-request-capture-dir",
                str(raw_dir),
            ],
        )
        try:
            wait_for_proxy(proxy_port, proc)
            health = get_json(f"http://127.0.0.1:{proxy_port}/healthz")
            assert health["request_shape_log_path"] == "<enabled:request-shape.jsonl>", health
            assert health["raw_request_capture_dir"] == "<enabled:raw-captures>", health
            assert str(temp) not in json.dumps(health), health
            assert proc.stderr is not None
            ready, _, _ = select.select([proc.stderr], [], [], 0)
            if ready:
                startup_log = os.read(proc.stderr.fileno(), 8192).decode("utf-8", "replace")
                assert str(temp) not in startup_log, startup_log
                assert "<enabled:request-shape.jsonl>" in startup_log, startup_log

            raw = post_json(
                f"http://127.0.0.1:{proxy_port}/v1/messages",
                {
                    "model": "claude-opus-4-8",
                    "system": [{"type": "text", "text": "private system text"}],
                    "max_tokens": 64,
                    "tools": [search_skills_tool()],
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "private user text"},
                            ],
                        }
                    ],
                },
            )
            payload = json.loads(raw)
            assert payload["content"][0]["text"] == "nonstream ok", payload

            lines = shape_path.read_text(encoding="utf-8").splitlines()
            assert len(lines) == 1, lines
            record = json.loads(lines[0])
            rendered_record = json.dumps(record)
            assert "private system text" not in rendered_record, record
            assert "private user text" not in rendered_record, record
            assert record["request_id"].startswith("req_"), record
            assert record["kind"] == "tool_agent", record
            assert record["anthropic"]["system"]["text_chars"] == len("private system text")
            assert record["anthropic"]["messages"][0]["content"]["text_chars"] == len("private user text")
            assert record["anthropic"]["tools"]["tool_count"] == 1
            assert record["anthropic"]["tools"]["description_chars"] > 0
            assert record["anthropic"]["tools"]["schema_json_chars"] > 0
            assert record["anthropic"]["tools"]["definition_json_chars"] > (
                record["anthropic"]["tools"]["description_chars"]
                + record["anthropic"]["tools"]["schema_json_chars"]
            )
            assert record["anthropic"]["tools"]["tools"][0]["definition_json_chars"] > (
                record["anthropic"]["tools"]["tools"][0]["description_chars"]
                + record["anthropic"]["tools"]["tools"][0]["schema_json_chars"]
            )
            assert record["openai"]["message_text_chars"] == (
                len("private system text") + len("private user text")
            )
            cache_candidate = record["openai"]["cache_candidate"]
            assert cache_candidate["version"] == 1, cache_candidate
            assert cache_candidate["split_strategy"] == "before_last_user_message", cache_candidate
            assert cache_candidate["prefix_message_count"] == 1, cache_candidate
            assert cache_candidate["tail_message_count"] == 1, cache_candidate
            assert cache_candidate["prefix_roles"] == ["system"], cache_candidate
            assert cache_candidate["tail_roles"] == ["user"], cache_candidate
            assert cache_candidate["prefix_json_chars"] > 0, cache_candidate
            assert cache_candidate["tail_json_chars"] > 0, cache_candidate
            assert cache_candidate["estimated_prefix_tokens"] > 0, cache_candidate
            assert cache_candidate["estimated_tail_tokens"] > 0, cache_candidate
            assert cache_candidate["estimated_full_prompt_tokens"] > 0, cache_candidate
            assert cache_candidate["context_pressure"] == "ok", cache_candidate
            assert len(cache_candidate["prefix_hash"]) == 24, cache_candidate
            assert len(cache_candidate["tail_hash"]) == 24, cache_candidate
            assert len(cache_candidate["tools_hash"]) == 24, cache_candidate

            raw_files = sorted(raw_dir.glob("*.json"))
            assert [path.name.rsplit(".", 2)[-2:] for path in raw_files] == [
                ["anthropic", "json"],
                ["openai", "json"],
            ], raw_files
            assert raw_dir.stat().st_mode & 0o777 == 0o700
            assert all((path.stat().st_mode & 0o777) == 0o600 for path in raw_files)
            raw_text = "\n".join(path.read_text(encoding="utf-8") for path in raw_files)
            assert "private system text" in raw_text
            assert "private user text" in raw_text
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def start_proxy_process(
    fake_port: int,
    proxy_port: int,
    tool_mode: str,
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
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
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.Popen(
        args,
        cwd=ROOT,
        env=env,
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
        assert_generate_plan_approve_content_repaired(proxy_port)
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

    assert_request_debug_capture(fake_port)

    pass_proxy_port = free_port()
    pass_proc = start_proxy_process(fake_port, pass_proxy_port, "pass")
    try:
        wait_for_proxy(pass_proxy_port, pass_proc)
        assert_active_tool_definitions_are_lossless(pass_proxy_port)
        assert_app_pruned_foreground_tools_pass_through(pass_proxy_port)
        assert_anthropic_server_tools_are_not_forwarded(pass_proxy_port)
        assert_tool_choice_required(pass_proxy_port)
        assert_single_harness_tool_forced(pass_proxy_port)
        assert_completed_harness_tool_not_forced(pass_proxy_port)
    finally:
        pass_proc.terminate()
        try:
            pass_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass_proc.kill()

    web_search_proxy_port = free_port()
    web_search_proc = start_proxy_process(
        fake_port,
        web_search_proxy_port,
        "pass",
        [
            "--server-web-search",
            "tavily",
            "--server-web-search-max-results",
            "3",
            "--server-web-search-max-uses",
            "2",
            "--tavily-base-url",
            f"http://127.0.0.1:{fake_port}",
            "--stream-heartbeat-seconds",
            "0.05",
        ],
        {"TAVILY_API_KEY": "test-tavily-key"},
    )
    try:
        wait_for_proxy(web_search_proxy_port, web_search_proc)
        assert_proxy_owned_server_web_search(web_search_proxy_port, fake_server)
        assert_proxy_owned_raw_server_web_search(web_search_proxy_port)
        assert_proxy_owned_server_web_search_stream_heartbeat(web_search_proxy_port)
        assert_server_tool_loop_retry_reuses_finished_job(web_search_proxy_port, fake_server)
        assert_server_loop_raw_skill_text_tool_repaired(web_search_proxy_port)
        assert_server_loop_call_tool_text_tool_repaired(web_search_proxy_port)
    finally:
        web_search_proc.terminate()
        try:
            web_search_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web_search_proc.kill()

    firecrawl_proxy_port = free_port()
    firecrawl_proc = start_proxy_process(
        fake_port,
        firecrawl_proxy_port,
        "pass",
        [
            "--server-web-search",
            "firecrawl",
            "--server-web-search-max-results",
            "3",
            "--server-web-search-max-uses",
            "2",
            "--firecrawl-base-url",
            f"http://127.0.0.1:{fake_port}",
        ],
        {"FIRECRAWL_API_KEY": "test-firecrawl-key"},
    )
    try:
        wait_for_proxy(firecrawl_proxy_port, firecrawl_proc)
        assert_proxy_owned_server_web_search_firecrawl(firecrawl_proxy_port, fake_server)
    finally:
        firecrawl_proc.terminate()
        try:
            firecrawl_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            firecrawl_proc.kill()

    web_search_no_text_parse_proxy_port = free_port()
    web_search_no_text_parse_proc = start_proxy_process(
        fake_port,
        web_search_no_text_parse_proxy_port,
        "pass",
        [
            "--parse-text-tool-calls",
            "0",
            "--server-web-search",
            "tavily",
            "--server-web-search-max-results",
            "3",
            "--server-web-search-max-uses",
            "2",
            "--tavily-base-url",
            f"http://127.0.0.1:{fake_port}",
        ],
        {"TAVILY_API_KEY": "test-tavily-key"},
    )
    try:
        wait_for_proxy(web_search_no_text_parse_proxy_port, web_search_no_text_parse_proc)
        assert_proxy_owned_raw_server_web_search(web_search_no_text_parse_proxy_port)
    finally:
        web_search_no_text_parse_proc.terminate()
        try:
            web_search_no_text_parse_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web_search_no_text_parse_proc.kill()

    harness_proxy_port = free_port()
    harness_proc = start_proxy_process(fake_port, harness_proxy_port, "pass")
    try:
        wait_for_proxy(harness_proxy_port, harness_proc)
        assert_harness_tools_pass_through(harness_proxy_port)
        assert_streamed_harness_tools_pass_through(harness_proxy_port)
    finally:
        harness_proc.terminate()
        try:
            harness_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            harness_proc.kill()

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
