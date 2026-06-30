#!/usr/bin/env python3
"""Small Anthropic Messages API proxy for an OpenAI-compatible MTPLX endpoint.

This is intentionally dependency-free so the lab can run on a clean macOS
Python. It implements the minimum Anthropic surface needed to test Claude Code
and Claude Science gateway behavior:

- GET /healthz
- GET /v1/models
- POST /v1/messages
- POST /v1/messages/count_tokens

It converts Anthropic message/tool payloads into OpenAI chat-completions
payloads, forwards them to MTPLX, then converts the response back into
Anthropic's Messages shape. Streaming requests are bridged incrementally from
OpenAI-compatible SSE chunks into Anthropic SSE events.
"""

from __future__ import annotations

import argparse
import ast
import errno
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


DEFAULT_UPSTREAM_BASE = _env("MTPLX_OPENAI_BASE_URL", "http://127.0.0.1:8030/v1")
DEFAULT_UPSTREAM_MODEL = _env("MTPLX_OPENAI_MODEL", "mtplx-qwen36-27b-optimized-quality")
DEFAULT_TIMEOUT = float(_env("PROXY_REQUEST_TIMEOUT", "180"))
DEFAULT_MAX_TOKENS_CAP = int(_env("PROXY_MAX_TOKENS_CAP", "4096"))
DEFAULT_UPSTREAM_RETRIES = int(_env("PROXY_UPSTREAM_RETRIES", "2"))
DEFAULT_UPSTREAM_RETRY_DELAY = float(_env("PROXY_UPSTREAM_RETRY_DELAY", "2"))
DEFAULT_STREAM_MODE = _env("PROXY_STREAM_MODE", "direct")
DEFAULT_TOOL_MODE = _env("PROXY_TOOL_MODE", "pass")
DEFAULT_PARSE_TEXT_TOOL_CALLS = _env("PROXY_PARSE_TEXT_TOOL_CALLS", "0")
DEFAULT_ADVERTISED_MODELS = _env(
    "PROXY_ADVERTISED_MODELS",
    f"claude-opus-4-8,{DEFAULT_UPSTREAM_MODEL}",
)


class ProxyConfig:
    def __init__(
        self,
        upstream_base: str,
        upstream_model: str,
        timeout: float,
        max_tokens_cap: int,
        upstream_retries: int,
        upstream_retry_delay: float,
        stream_mode: str,
        tool_mode: str,
        parse_text_tool_calls: bool,
        advertised_models: list[str],
    ) -> None:
        self.upstream_base = upstream_base.rstrip("/")
        self.upstream_model = upstream_model
        self.timeout = timeout
        self.max_tokens_cap = max_tokens_cap
        self.upstream_retries = upstream_retries
        self.upstream_retry_delay = upstream_retry_delay
        self.stream_mode = stream_mode
        self.tool_mode = tool_mode
        self.parse_text_tool_calls = parse_text_tool_calls
        self.advertised_models = advertised_models


CONFIG = ProxyConfig(
    DEFAULT_UPSTREAM_BASE,
    DEFAULT_UPSTREAM_MODEL,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_TOKENS_CAP,
    DEFAULT_UPSTREAM_RETRIES,
    DEFAULT_UPSTREAM_RETRY_DELAY,
    DEFAULT_STREAM_MODE,
    DEFAULT_TOOL_MODE,
    False,
    [],
)


def parse_csv(value: str) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for raw in value.split(","):
        item = raw.strip()
        if item and item not in seen:
            seen.add(item)
            items.append(item)
    return items


def parse_stream_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in ("direct", "buffered"):
        raise ValueError("stream mode must be 'direct' or 'buffered'")
    return mode


def parse_tool_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in ("pass", "drop"):
        raise ValueError("tool mode must be 'pass' or 'drop'")
    return mode


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ValueError("boolean value must be one of 1/0, true/false, yes/no, on/off")


CONFIG.advertised_models = parse_csv(DEFAULT_ADVERTISED_MODELS)
CONFIG.parse_text_tool_calls = parse_bool(DEFAULT_PARSE_TEXT_TOOL_CALLS)


def log(message: str) -> None:
    print(f"[anthropic-mtplx-proxy] {message}", file=sys.stderr, flush=True)


def is_client_disconnect(exc: BaseException) -> bool:
    if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
        return True
    if isinstance(exc, OSError) and exc.errno in (errno.EPIPE, errno.ECONNRESET):
        return True
    return False


class UpstreamHTTPError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def should_retry_upstream(status: int, detail: str) -> bool:
    retryable_status = status in (429, 500, 502, 503, 504)
    if not retryable_status:
        return False
    lowered = detail.lower()
    return status in (429, 502, 503, 504) or "session_busy" in lowered


def block_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            kind = block.get("type")
            if kind == "text":
                parts.append(str(block.get("text") or ""))
            elif kind == "image":
                parts.append("[image block omitted by local proxy]")
            elif kind == "document":
                parts.append("[document block omitted by local proxy]")
            elif kind == "tool_result":
                value = block.get("content")
                parts.append(block_text(value))
            elif kind == "thinking":
                continue
            else:
                parts.append(f"[{kind or 'unknown'} block omitted by local proxy]")
        return "\n".join(part for part in parts if part)
    return str(content)


def tool_result_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [
        block
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]


def user_text_without_tool_results(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, list):
        return block_text(content)
    kept = [
        block
        for block in content
        if not (isinstance(block, dict) and block.get("type") == "tool_result")
    ]
    return block_text(kept)


def assistant_message_from_blocks(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if not isinstance(content, list):
        return {"role": "assistant", "content": block_text(content)}

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            text_parts.append(str(block))
            continue
        if block.get("type") == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id") or f"toolu_{uuid.uuid4().hex}",
                    "type": "function",
                    "function": {
                        "name": block.get("name") or "unknown_tool",
                        "arguments": json.dumps(block.get("input") or {}),
                    },
                }
            )

    result: dict[str, Any] = {
        "role": "assistant",
        "content": "\n".join(part for part in text_parts if part) or None,
    }
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result


def anthropic_to_openai(payload: dict[str, Any], stream: bool = False) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []

    system = payload.get("system")
    system_text = block_text(system)
    if system_text:
        messages.append({"role": "system", "content": system_text})

    for message in payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "assistant":
            messages.append(assistant_message_from_blocks(message))
            continue
        if role != "user":
            messages.append({"role": str(role or "user"), "content": block_text(message.get("content"))})
            continue

        user_text = user_text_without_tool_results(message)
        if user_text:
            messages.append({"role": "user", "content": user_text})
        for block in tool_result_blocks(message):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id") or block.get("id") or "",
                    "content": block_text(block.get("content")),
                }
            )

    tools = []
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description") or "",
                    "parameters": tool.get("input_schema") or {"type": "object"},
                },
            }
        )

    requested_max_tokens = int(payload.get("max_tokens") or 1024)
    max_tokens = min(requested_max_tokens, CONFIG.max_tokens_cap)

    request: dict[str, Any] = {
        "model": CONFIG.upstream_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if "temperature" in payload:
        request["temperature"] = payload["temperature"]
    if "top_p" in payload:
        request["top_p"] = payload["top_p"]
    if tools and CONFIG.tool_mode == "pass":
        request["tools"] = tools

    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, dict) and CONFIG.tool_mode == "pass":
        choice_type = tool_choice.get("type")
        if choice_type in ("auto", "any"):
            request["tool_choice"] = "auto"
        elif choice_type == "tool" and tool_choice.get("name"):
            request["tool_choice"] = {
                "type": "function",
                "function": {"name": tool_choice["name"]},
            }

    return request


def single_tool_name(payload: dict[str, Any]) -> str | None:
    tools = payload.get("tools")
    if not isinstance(tools, list) or len(tools) != 1:
        return None
    tool = tools[0]
    if not isinstance(tool, dict):
        return None
    name = tool.get("name")
    return name if isinstance(name, str) and name else None


def parse_json_object_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].strip() in ("```", "```json", "```JSON"):
            stripped = "\n".join(lines[1:]).strip()
            if stripped.endswith("```"):
                stripped = stripped[: -len("```")].strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_function_call_text(text: str, tool_name: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped.startswith(f"{tool_name}("):
        return None
    try:
        parsed = ast.parse(stripped, mode="eval")
    except SyntaxError:
        return None
    call = parsed.body
    if not isinstance(call, ast.Call):
        return None
    if not isinstance(call.func, ast.Name) or call.func.id != tool_name:
        return None

    arguments: dict[str, Any] = {}
    if len(call.args) == 1 and not call.keywords:
        try:
            value = ast.literal_eval(call.args[0])
        except (ValueError, SyntaxError):
            value = None
        if isinstance(value, dict):
            arguments.update(value)
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        try:
            arguments[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, SyntaxError):
            return None
    return arguments if arguments else None


def parse_text_tool_call(content: Any, tool_name_hint: str | None = None) -> dict[str, Any] | None:
    if not CONFIG.parse_text_tool_calls or not isinstance(content, str):
        return None
    stripped = content.strip()

    if tool_name_hint:
        arguments = parse_json_object_text(stripped)
        if arguments is None:
            arguments = parse_function_call_text(stripped, tool_name_hint)
        if arguments is not None:
            return {
                "type": "tool_use",
                "id": f"toolu_{uuid.uuid4().hex}",
                "name": tool_name_hint,
                "input": arguments,
            }

    parts = stripped.split("::", 3)
    if len(parts) == 4 and parts[0] == "" and parts[1] and parts[2] in ("+json", "json"):
        try:
            arguments = json.loads(parts[3].strip())
        except json.JSONDecodeError:
            arguments = None
        if isinstance(arguments, dict):
            return {
                "type": "tool_use",
                "id": f"toolu_{uuid.uuid4().hex}",
                "name": parts[1],
                "input": arguments,
            }

    marker = "<tool_call>"
    marker_at = stripped.find(marker)
    if marker_at < 0:
        return None

    raw = stripped[marker_at + len(marker) :].strip()
    start_positions = [pos for pos in (raw.find("["), raw.find("{")) if pos >= 0]
    if not start_positions:
        return None
    raw = raw[min(start_positions) :].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None

    name: str | None = None
    arguments: Any = {}
    if isinstance(parsed, list) and len(parsed) >= 2:
        name = parsed[0] if isinstance(parsed[0], str) else None
        arguments = parsed[1]
    elif isinstance(parsed, dict):
        name_value = parsed.get("name") or parsed.get("tool") or parsed.get("function")
        name = name_value if isinstance(name_value, str) else None
        arguments = parsed.get("arguments", parsed.get("input", {}))

    if not name:
        return None
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"_raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {"value": arguments}

    return {
        "type": "tool_use",
        "id": f"toolu_{uuid.uuid4().hex}",
        "name": name,
        "input": arguments,
    }


def openai_to_anthropic(
    data: dict[str, Any],
    requested_model: str | None = None,
    text_tool_name_hint: str | None = None,
) -> dict[str, Any]:
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content_blocks: list[dict[str, Any]] = []

    content = message.get("content")
    parsed_text_tool = parse_text_tool_call(content, tool_name_hint=text_tool_name_hint)
    if parsed_text_tool:
        content_blocks.append(parsed_text_tool)
    elif content:
        content_blocks.append({"type": "text", "text": str(content)})

    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        raw_args = fn.get("arguments") or "{}"
        try:
            parsed_args = json.loads(raw_args)
        except Exception:
            parsed_args = {"_raw": raw_args}
        content_blocks.append(
            {
                "type": "tool_use",
                "id": call.get("id") or f"toolu_{uuid.uuid4().hex}",
                "name": fn.get("name") or "unknown_tool",
                "input": parsed_args,
            }
        )

    finish_reason = choice.get("finish_reason")
    if any(block.get("type") == "tool_use" for block in content_blocks):
        stop_reason = "tool_use"
    elif finish_reason == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"

    usage = data.get("usage") or {}
    return {
        "id": f"msg_{uuid.uuid4().hex}",
        "type": "message",
        "role": "assistant",
        "model": requested_model or CONFIG.upstream_model,
        "content": content_blocks or [{"type": "text", "text": ""}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
        },
    }


def call_openai_chat(request: dict[str, Any]) -> dict[str, Any]:
    request = dict(request)
    request["stream"] = False
    url = f"{CONFIG.upstream_base}/chat/completions"
    body = json.dumps(request).encode("utf-8")
    started = time.monotonic()
    last_detail = ""
    for attempt in range(CONFIG.upstream_retries + 1):
        http_request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_env('MTPLX_API_KEY', 'local-mtplx')}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=CONFIG.timeout) as response:
                raw = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            last_detail = detail or str(exc)
            if attempt < CONFIG.upstream_retries and should_retry_upstream(exc.code, last_detail):
                delay = CONFIG.upstream_retry_delay * (attempt + 1)
                log(f"upstream HTTP {exc.code}; retrying in {delay:.1f}s")
                time.sleep(delay)
                continue
            raise UpstreamHTTPError(exc.code, last_detail) from exc
    else:
        raise UpstreamHTTPError(503, last_detail or "upstream retry limit exceeded")
    elapsed = time.monotonic() - started
    log(f"upstream completed in {elapsed:.1f}s")
    return json.loads(raw)


def open_openai_stream(request: dict[str, Any]) -> Any:
    request = dict(request)
    request["stream"] = True
    url = f"{CONFIG.upstream_base}/chat/completions"
    body = json.dumps(request).encode("utf-8")
    last_detail = ""
    for attempt in range(CONFIG.upstream_retries + 1):
        http_request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Authorization": f"Bearer {_env('MTPLX_API_KEY', 'local-mtplx')}",
            },
            method="POST",
        )
        try:
            return urllib.request.urlopen(http_request, timeout=CONFIG.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            last_detail = detail or str(exc)
            if attempt < CONFIG.upstream_retries and should_retry_upstream(exc.code, last_detail):
                delay = CONFIG.upstream_retry_delay * (attempt + 1)
                log(f"upstream stream HTTP {exc.code}; retrying in {delay:.1f}s")
                time.sleep(delay)
                continue
            raise UpstreamHTTPError(exc.code, last_detail) from exc
    raise UpstreamHTTPError(503, last_detail or "upstream stream retry limit exceeded")


def iter_openai_stream(response: Any) -> Any:
    for raw_line in response:
        line = raw_line.decode("utf-8", "replace").strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            break
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            log(f"skipping non-json stream line: {line[:200]}")


def estimate_tokens(payload: Any) -> int:
    text = json.dumps(payload, ensure_ascii=False)
    return max(1, len(text) // 4)


def sse_event(name: str, data: dict[str, Any]) -> bytes:
    encoded = json.dumps(data, separators=(",", ":"))
    return f"event: {name}\ndata: {encoded}\n\n".encode("utf-8")


def send_sse_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("X-Accel-Buffering", "no")
    handler.send_header("Connection", "close")
    handler.end_headers()


def write_sse(handler: BaseHTTPRequestHandler, name: str, data: dict[str, Any]) -> None:
    handler.wfile.write(sse_event(name, data))


def finish_sse(handler: BaseHTTPRequestHandler) -> None:
    handler.wfile.flush()
    handler.close_connection = True


def emit_anthropic_message_events(handler: BaseHTTPRequestHandler, message: dict[str, Any]) -> None:
    start_message = dict(message)
    start_message["content"] = []
    write_sse(handler, "message_start", {"type": "message_start", "message": start_message})
    handler.wfile.flush()

    for index, block in enumerate(message.get("content") or []):
        block_type = block.get("type")
        if block_type == "text":
            write_sse(
                handler,
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "text", "text": ""},
                },
            )
            write_sse(
                handler,
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": block.get("text") or ""},
                },
            )
        elif block_type == "tool_use":
            write_sse(
                handler,
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": {},
                    },
                },
            )
            write_sse(
                handler,
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": json.dumps(block.get("input") or {}),
                    },
                },
            )
        write_sse(handler, "content_block_stop", {"type": "content_block_stop", "index": index})
        handler.wfile.flush()

    write_sse(
        handler,
        "message_delta",
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": message.get("stop_reason"),
                "stop_sequence": message.get("stop_sequence"),
            },
            "usage": {"output_tokens": message.get("usage", {}).get("output_tokens", 0)},
        },
    )
    write_sse(handler, "message_stop", {"type": "message_stop"})
    finish_sse(handler)


def stream_anthropic(handler: BaseHTTPRequestHandler, message: dict[str, Any]) -> None:
    send_sse_headers(handler)
    emit_anthropic_message_events(handler, message)


def openai_finish_to_anthropic(finish_reason: str | None, saw_tool_use: bool) -> str:
    if saw_tool_use or finish_reason == "tool_calls":
        return "tool_use"
    if finish_reason == "length":
        return "max_tokens"
    return "end_turn"


def stream_openai_to_anthropic(
    handler: BaseHTTPRequestHandler,
    request: dict[str, Any],
    requested_model: str,
    text_tool_name_hint: str | None = None,
) -> None:
    started = time.monotonic()
    response = open_openai_stream(request)
    send_sse_headers(handler)

    message_id = f"msg_{uuid.uuid4().hex}"
    start_message = {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": requested_model,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }

    next_block_index = 0
    text_block_index: int | None = None
    text_block_open = False
    tool_blocks: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None
    output_chars = 0
    saw_any_content = False
    saw_tool_use = False
    message_started = False

    def start_message_once() -> None:
        nonlocal message_started
        if message_started:
            return
        write_sse(handler, "message_start", {"type": "message_start", "message": start_message})
        handler.wfile.flush()
        message_started = True

    def stop_text_block() -> None:
        nonlocal text_block_open
        if text_block_open and text_block_index is not None:
            write_sse(
                handler,
                "content_block_stop",
                {"type": "content_block_stop", "index": text_block_index},
            )
            handler.wfile.flush()
            text_block_open = False

    def ensure_text_block() -> int:
        nonlocal next_block_index, text_block_index, text_block_open, saw_any_content
        start_message_once()
        if text_block_index is None:
            text_block_index = next_block_index
            next_block_index += 1
            write_sse(
                handler,
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": text_block_index,
                    "content_block": {"type": "text", "text": ""},
                },
            )
            text_block_open = True
            saw_any_content = True
        elif not text_block_open:
            text_block_open = True
        return text_block_index

    def ensure_tool_block(openai_index: int, call: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal next_block_index, saw_any_content, saw_tool_use
        block = tool_blocks.setdefault(
            openai_index,
            {
                "anthropic_index": None,
                "id": None,
                "name": None,
                "pending_args": "",
                "open": False,
            },
        )
        if call.get("id"):
            block["id"] = call["id"]
        fn = call.get("function") if isinstance(call.get("function"), dict) else {}
        if fn.get("name"):
            block["name"] = fn["name"]
        if block["open"]:
            return block
        if not block.get("name"):
            return None

        stop_text_block()
        start_message_once()
        block["anthropic_index"] = next_block_index
        next_block_index += 1
        block["id"] = block.get("id") or f"toolu_{uuid.uuid4().hex}"
        write_sse(
            handler,
            "content_block_start",
            {
                "type": "content_block_start",
                "index": block["anthropic_index"],
                "content_block": {
                    "type": "tool_use",
                    "id": block["id"],
                    "name": block["name"],
                    "input": {},
                },
            },
        )
        block["open"] = True
        saw_any_content = True
        saw_tool_use = True
        pending_args = block.get("pending_args") or ""
        if pending_args:
            write_sse(
                handler,
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": block["anthropic_index"],
                    "delta": {"type": "input_json_delta", "partial_json": pending_args},
                },
            )
            block["pending_args"] = ""
        handler.wfile.flush()
        return block

    try:
        for chunk in iter_openai_stream(response):
            choices = chunk.get("choices") or []
            if chunk.get("usage"):
                usage = chunk["usage"]
                output_chars = max(output_chars, int(usage.get("completion_tokens") or 0) * 4)
            if not choices:
                continue
            choice = choices[0]
            if "message" in choice:
                message = openai_to_anthropic(
                    chunk,
                    requested_model=requested_model,
                    text_tool_name_hint=text_tool_name_hint,
                )
                if message_started or saw_any_content:
                    log("ignoring full-message stream fallback after partial stream output")
                    finish_reason = choice.get("finish_reason") or finish_reason
                    continue
                emit_anthropic_message_events(handler, message)
                log(f"upstream stream completed in {time.monotonic() - started:.1f}s")
                return

            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}
            content_delta = delta.get("content")
            if content_delta:
                index = ensure_text_block()
                text = str(content_delta)
                output_chars += len(text)
                write_sse(
                    handler,
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": index,
                        "delta": {"type": "text_delta", "text": text},
                    },
                )
                handler.wfile.flush()

            for call in delta.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                openai_index = int(call.get("index") or 0)
                fn = call.get("function") if isinstance(call.get("function"), dict) else {}
                args_delta = str(fn.get("arguments") or "")
                block = ensure_tool_block(openai_index, call)
                if block is None:
                    if args_delta:
                        pending = tool_blocks[openai_index].get("pending_args") or ""
                        tool_blocks[openai_index]["pending_args"] = pending + args_delta
                        output_chars += len(args_delta)
                    continue
                if args_delta:
                    output_chars += len(args_delta)
                    write_sse(
                        handler,
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": block["anthropic_index"],
                            "delta": {"type": "input_json_delta", "partial_json": args_delta},
                        },
                    )
                    handler.wfile.flush()
    finally:
        response.close()

    stop_text_block()
    for block in sorted(tool_blocks.values(), key=lambda item: item.get("anthropic_index") or 0):
        if block.get("open"):
            write_sse(
                handler,
                "content_block_stop",
                {"type": "content_block_stop", "index": block["anthropic_index"]},
            )
            block["open"] = False

    if not saw_any_content:
        index = ensure_text_block()
        write_sse(
            handler,
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": "text_delta", "text": ""},
            },
        )
        stop_text_block()

    stop_reason = openai_finish_to_anthropic(finish_reason, saw_tool_use)
    write_sse(
        handler,
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": max(1, output_chars // 4)},
        },
    )
    write_sse(handler, "message_stop", {"type": "message_stop"})
    finish_sse(handler)
    log(f"upstream stream completed in {time.monotonic() - started:.1f}s")


class Handler(BaseHTTPRequestHandler):
    server_version = "AnthropicMTPLXProxy/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        log(f"{self.address_string()} {fmt % args}")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            self._json(
                200,
                {
                    "ok": True,
                    "upstream_base": CONFIG.upstream_base,
                    "upstream_model": CONFIG.upstream_model,
                    "advertised_models": CONFIG.advertised_models,
                    "max_tokens_cap": CONFIG.max_tokens_cap,
                    "upstream_retries": CONFIG.upstream_retries,
                    "upstream_retry_delay": CONFIG.upstream_retry_delay,
                    "stream_mode": CONFIG.stream_mode,
                    "tool_mode": CONFIG.tool_mode,
                    "parse_text_tool_calls": CONFIG.parse_text_tool_calls,
                },
            )
            return
        if path == "/v1/models":
            self._json(
                200,
                {
                    "data": [
                        {
                            "id": model,
                            "type": "model",
                            "display_name": model,
                            "created_at": "2026-06-30T00:00:00Z",
                        }
                        for model in CONFIG.advertised_models
                    ]
                },
            )
            return
        self._json(404, {"error": {"type": "not_found_error", "message": path}})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/v1/messages/count_tokens":
                self._json(200, {"input_tokens": estimate_tokens(payload)})
                return
            if path != "/v1/messages":
                self._json(404, {"error": {"type": "not_found_error", "message": path}})
                return

            requested_model = str(payload.get("model") or CONFIG.upstream_model)
            stream_requested = bool(payload.get("stream"))
            request = anthropic_to_openai(payload, stream=stream_requested)
            text_tool_name_hint = single_tool_name(payload)
            requested_max_tokens = payload.get("max_tokens")
            log(
                "request "
                f"stream={stream_requested} "
                f"messages={len(payload.get('messages') or [])} "
                f"tools={len(payload.get('tools') or [])} "
                f"upstream_tools={len(request.get('tools') or [])} "
                f"requested_max_tokens={requested_max_tokens} "
                f"upstream_max_tokens={request.get('max_tokens')}"
            )
            if stream_requested and CONFIG.stream_mode == "direct":
                stream_openai_to_anthropic(
                    self,
                    request,
                    requested_model=requested_model,
                    text_tool_name_hint=text_tool_name_hint,
                )
            else:
                upstream = call_openai_chat(request)
                message = openai_to_anthropic(
                    upstream,
                    requested_model=requested_model,
                    text_tool_name_hint=text_tool_name_hint,
                )
                if stream_requested:
                    stream_anthropic(self, message)
                else:
                    self._json(200, message)
        except UpstreamHTTPError as exc:
            detail = exc.detail
            log(f"upstream HTTP error {exc.status}: {detail[:500]}")
            self._json(
                exc.status,
                {"error": {"type": "upstream_error", "message": detail or str(exc)}},
            )
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            if is_client_disconnect(exc):
                log("client disconnected before response completed")
                return
            log(f"os error: {exc}\n{traceback.format_exc()}")
            self._json(500, {"error": {"type": "proxy_error", "message": str(exc)}})
        except Exception as exc:
            log(f"error: {exc}\n{traceback.format_exc()}")
            self._json(500, {"error": {"type": "proxy_error", "message": str(exc)}})


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exc_info()[1]
        if exc is not None and is_client_disconnect(exc):
            log(f"client disconnected: {client_address}")
            return
        super().handle_error(request, client_address)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=_env("PROXY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(_env("PROXY_PORT", "18080")))
    parser.add_argument("--upstream-base", default=CONFIG.upstream_base)
    parser.add_argument("--upstream-model", default=CONFIG.upstream_model)
    parser.add_argument("--timeout", type=float, default=CONFIG.timeout)
    parser.add_argument("--max-tokens-cap", type=int, default=CONFIG.max_tokens_cap)
    parser.add_argument("--upstream-retries", type=int, default=CONFIG.upstream_retries)
    parser.add_argument(
        "--upstream-retry-delay",
        type=float,
        default=CONFIG.upstream_retry_delay,
    )
    parser.add_argument(
        "--stream-mode",
        default=CONFIG.stream_mode,
        choices=("direct", "buffered"),
        help="direct streams upstream SSE; buffered asks upstream for a full response then emits Anthropic SSE.",
    )
    parser.add_argument(
        "--tool-mode",
        default=CONFIG.tool_mode,
        choices=("pass", "drop"),
        help="pass forwards Claude Science tools upstream; drop omits tool schemas for direct-analysis local models.",
    )
    parser.add_argument(
        "--parse-text-tool-calls",
        default="1" if CONFIG.parse_text_tool_calls else "0",
        help="Convert narrow textual <tool_call>[...] responses into Anthropic tool_use blocks.",
    )
    parser.add_argument(
        "--advertised-models",
        default=",".join(CONFIG.advertised_models),
        help="Comma-separated model ids to expose via /v1/models.",
    )
    args = parser.parse_args()

    CONFIG.upstream_base = args.upstream_base.rstrip("/")
    CONFIG.upstream_model = args.upstream_model
    CONFIG.timeout = args.timeout
    CONFIG.max_tokens_cap = args.max_tokens_cap
    CONFIG.upstream_retries = args.upstream_retries
    CONFIG.upstream_retry_delay = args.upstream_retry_delay
    CONFIG.stream_mode = parse_stream_mode(args.stream_mode)
    CONFIG.tool_mode = parse_tool_mode(args.tool_mode)
    CONFIG.parse_text_tool_calls = parse_bool(args.parse_text_tool_calls)
    CONFIG.advertised_models = parse_csv(args.advertised_models)
    if CONFIG.upstream_model not in CONFIG.advertised_models:
        CONFIG.advertised_models.append(CONFIG.upstream_model)

    server = ProxyServer((args.host, args.port), Handler)
    log(
        f"listening on http://{args.host}:{args.port}; "
        f"upstream={CONFIG.upstream_base}; model={CONFIG.upstream_model}; "
        f"max_tokens_cap={CONFIG.max_tokens_cap}; "
        f"retries={CONFIG.upstream_retries}; "
        f"stream_mode={CONFIG.stream_mode}; "
        f"tool_mode={CONFIG.tool_mode}; "
        f"parse_text_tool_calls={CONFIG.parse_text_tool_calls}; "
        f"advertised_models={CONFIG.advertised_models}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("stopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
