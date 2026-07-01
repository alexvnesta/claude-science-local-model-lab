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
import hashlib
import json
import os
import re
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
DEFAULT_TOOL_ALLOWLIST = _env("PROXY_TOOL_ALLOWLIST", "")
DEFAULT_TOOL_VALIDATION = _env("PROXY_TOOL_VALIDATION", "schema")
DEFAULT_TOOL_REPAIR = _env("PROXY_TOOL_REPAIR", "metadata")
DEFAULT_FORCE_MENTIONED_TOOL = _env("PROXY_FORCE_MENTIONED_TOOL", "0")
DEFAULT_PARSE_TEXT_TOOL_CALLS = _env("PROXY_PARSE_TEXT_TOOL_CALLS", "0")
DEFAULT_SCHEMA_LOG_PATH = _env("PROXY_SCHEMA_LOG_PATH", "")
DEFAULT_HARNESS_TOOLS = _env("PROXY_HARNESS_TOOLS", "submit_output")
DEFAULT_CLAUDE_SCIENCE_COMPAT = _env("PROXY_CLAUDE_SCIENCE_COMPAT", "0")
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
        tool_allowlist: list[str],
        tool_validation: str,
        tool_repair: str,
        force_mentioned_tool: bool,
        parse_text_tool_calls: bool,
        schema_log_path: str,
        harness_tools: list[str],
        claude_science_compat: bool,
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
        self.tool_allowlist = tool_allowlist
        self.tool_validation = tool_validation
        self.tool_repair = tool_repair
        self.force_mentioned_tool = force_mentioned_tool
        self.parse_text_tool_calls = parse_text_tool_calls
        self.schema_log_path = schema_log_path
        self.harness_tools = harness_tools
        self.claude_science_compat = claude_science_compat
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
    [],
    "schema",
    "metadata",
    False,
    False,
    "",
    [],
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


def parse_tool_validation(value: str) -> str:
    mode = value.strip().lower()
    if mode not in ("off", "name", "schema"):
        raise ValueError("tool validation must be 'off', 'name', or 'schema'")
    return mode


def parse_tool_repair(value: str) -> str:
    mode = value.strip().lower()
    if mode not in ("off", "metadata"):
        raise ValueError("tool repair must be 'off' or 'metadata'")
    return mode


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ValueError("boolean value must be one of 1/0, true/false, yes/no, on/off")


CONFIG.advertised_models = parse_csv(DEFAULT_ADVERTISED_MODELS)
CONFIG.tool_allowlist = parse_csv(DEFAULT_TOOL_ALLOWLIST)
CONFIG.tool_validation = parse_tool_validation(DEFAULT_TOOL_VALIDATION)
CONFIG.tool_repair = parse_tool_repair(DEFAULT_TOOL_REPAIR)
CONFIG.force_mentioned_tool = parse_bool(DEFAULT_FORCE_MENTIONED_TOOL)
CONFIG.parse_text_tool_calls = parse_bool(DEFAULT_PARSE_TEXT_TOOL_CALLS)
CONFIG.schema_log_path = DEFAULT_SCHEMA_LOG_PATH
CONFIG.harness_tools = parse_csv(DEFAULT_HARNESS_TOOLS)
CONFIG.claude_science_compat = parse_bool(DEFAULT_CLAUDE_SCIENCE_COMPAT)


def log(message: str) -> None:
    print(f"[anthropic-mtplx-proxy] {message}", file=sys.stderr, flush=True)


def advertised_model_record(model: str) -> dict[str, Any]:
    return {
        "id": model,
        "type": "model",
        "display_name": model,
        "created_at": "2026-06-30T00:00:00Z",
    }


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


def latest_user_text(payload: dict[str, Any]) -> str:
    for message in reversed(payload.get("messages") or []):
        if isinstance(message, dict) and message.get("role") == "user":
            return user_text_without_tool_results(message)
    return ""


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
    payload_tool_names = tool_names(payload)

    system = payload.get("system")
    system_text = block_text(system)
    if system_text:
        messages.append({"role": "system", "content": system_text})
    if CONFIG.tool_mode == "drop" and payload_tool_names and "submit_output" not in payload_tool_names:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Local proxy note: Claude Science offered tools for this turn, "
                    "but this profile intentionally hides tool schemas from the local model. "
                    "Do not emit tool-call markup, anonymous_function tags, XML tags, or function-call text. "
                    "Do not claim that you searched, browsed, read files, ran code, created artifacts, "
                    "or made a figure. If the user asks for live research, files, code execution, "
                    "or artifacts, say this local profile cannot execute those tools and provide only a "
                    "short direct draft, plan, or caveated analysis based on the visible prompt. "
                    "Keep the answer under 220 words so it can finish in one response."
                ),
            }
        )

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
    allowlist = set(CONFIG.tool_allowlist)
    harness_tools = set(CONFIG.harness_tools)
    for tool in payload.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if allowlist and name not in allowlist and name not in harness_tools:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
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
    forced_tool = forced_mentioned_tool(
        payload,
        [
            tool["function"]["name"]
            for tool in tools
            if isinstance(tool.get("function"), dict)
            and isinstance(tool["function"].get("name"), str)
        ],
    )
    if isinstance(tool_choice, dict) and CONFIG.tool_mode == "pass":
        choice_type = tool_choice.get("type")
        if choice_type == "auto":
            request["tool_choice"] = "auto"
        elif choice_type == "any":
            request["tool_choice"] = "required"
        elif choice_type == "tool" and tool_choice.get("name"):
            request["tool_choice"] = {
                "type": "function",
                "function": {"name": tool_choice["name"]},
            }
    elif forced_tool and CONFIG.tool_mode == "pass":
        request["tool_choice"] = {
            "type": "function",
            "function": {"name": forced_tool},
        }

    forwarded_names = [
        tool["function"]["name"]
        for tool in tools
        if isinstance(tool.get("function"), dict)
        and isinstance(tool["function"].get("name"), str)
    ]
    if (
        CONFIG.tool_mode == "pass"
        and len(forwarded_names) == 1
        and forwarded_names[0] in harness_tools
        and request.get("tool_choice") in (None, "auto", "required")
    ):
        request["tool_choice"] = {
            "type": "function",
            "function": {"name": forwarded_names[0]},
        }
        log(f"forcing harness tool_choice {forwarded_names[0]!r}")

    return request


def forced_mentioned_tool(payload: dict[str, Any], forwarded_tool_names: list[str]) -> str | None:
    if not CONFIG.force_mentioned_tool or not forwarded_tool_names:
        return None
    text = latest_user_text(payload).lower()
    if not text:
        return None
    best: tuple[int, int, str] | None = None
    for name in forwarded_tool_names:
        escaped = re.escape(name.lower())
        patterns = [
            rf"\buse\s+(?:the\s+)?`?{escaped}`?\s+tool\b",
            rf"\bcall\s+(?:the\s+)?`?{escaped}`?\s+tool\b",
            rf"\bcall\s+(?:the\s+)?`?{escaped}`?\b",
            rf"\bload\s+(?:the\s+)?`?{escaped}`?\s+tool\b",
            rf"\bmust\s+call\s+(?:the\s+)?`?{escaped}`?\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            candidate = (match.start(), -len(name), name)
            if best is None or candidate < best:
                best = candidate
    return best[2] if best else None


def tool_names(payload: dict[str, Any]) -> list[str]:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return []
    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return names


def tool_schema_map(
    payload: dict[str, Any],
    allowlist: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return {}
    allowed = set(allowlist or [])
    harness_tools = set(CONFIG.harness_tools)
    schemas: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if allowed and name not in allowed and name not in harness_tools:
            continue
        schema = tool.get("input_schema")
        if isinstance(name, str) and name and isinstance(schema, dict):
            schemas[name] = schema
        elif isinstance(name, str) and name:
            schemas[name] = {"type": "object"}
    return schemas


def classify_request_kind(
    payload: dict[str, Any],
    request: dict[str, Any],
) -> str:
    offered = set(tool_names(payload))
    forwarded = {
        item.get("function", {}).get("name")
        for item in request.get("tools") or []
        if isinstance(item, dict)
    }
    forwarded = {name for name in forwarded if isinstance(name, str)}
    harness = set(CONFIG.harness_tools)

    if offered & harness or forwarded & harness:
        return "harness"
    if forwarded:
        return "tool_agent"
    if offered:
        return "tools_hidden"
    return "plain"


def schema_digest(schema: Any) -> str:
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def summarize_tool_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"schema_type": type(schema).__name__}

    summary: dict[str, Any] = {
        "digest": schema_digest(schema),
        "type": schema.get("type"),
        "required": schema.get("required") if isinstance(schema.get("required"), list) else [],
        "additionalProperties": schema.get("additionalProperties"),
    }
    properties = schema.get("properties")
    if isinstance(properties, dict):
        summary["properties"] = sorted(str(key) for key in properties)
        summary["property_types"] = {
            str(key): value.get("type")
            for key, value in properties.items()
            if isinstance(value, dict) and "type" in value
        }
    else:
        summary["properties"] = []
    return summary


def log_tool_schema_inventory(payload: dict[str, Any]) -> None:
    if not CONFIG.schema_log_path:
        return
    tools = payload.get("tools")
    if not isinstance(tools, list) or not tools:
        return

    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stream": bool(payload.get("stream")),
        "model": payload.get("model"),
        "max_tokens": payload.get("max_tokens"),
        "tool_choice": payload.get("tool_choice"),
        "tool_count": len(tools),
        "tools": [],
    }
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        schema = tool.get("input_schema")
        record["tools"].append(
            {
                "name": name if isinstance(name, str) else None,
                "description_len": len(str(tool.get("description") or "")),
                "schema": summarize_tool_schema(schema),
            }
        )

    try:
        directory = os.path.dirname(CONFIG.schema_log_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(CONFIG.schema_log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        log(f"could not write schema inventory to {CONFIG.schema_log_path}: {exc}")


def single_tool_name(names: list[str]) -> str | None:
    if len(names) != 1:
        return None
    return names[0]


def schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_json_schema(value: Any, schema: Any, path: str = "$") -> list[str]:
    """Small JSON Schema subset validator for tool-call safety checks.

    It intentionally covers the schema keywords Claude Science tools commonly
    use while staying dependency-free for fresh macOS installs.
    """

    if schema is True or schema is None:
        return []
    if schema is False:
        return [f"{path}: value is not allowed"]
    if not isinstance(schema, dict):
        return []

    if value is None and schema.get("nullable") is True:
        return []

    errors: list[str] = []

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and isinstance(schema["enum"], list) and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} is not in enum")

    expected_type = schema.get("type")
    if isinstance(expected_type, str):
        if not schema_type_matches(value, expected_type):
            errors.append(f"{path}: expected {expected_type}")
            return errors
    elif isinstance(expected_type, list):
        if not any(isinstance(item, str) and schema_type_matches(value, item) for item in expected_type):
            errors.append(f"{path}: expected one of {expected_type}")
            return errors

    if "anyOf" in schema and isinstance(schema["anyOf"], list):
        if not any(not validate_json_schema(value, option, path) for option in schema["anyOf"]):
            errors.append(f"{path}: did not match anyOf")
    if "oneOf" in schema and isinstance(schema["oneOf"], list):
        matches = sum(1 for option in schema["oneOf"] if not validate_json_schema(value, option, path))
        if matches != 1:
            errors.append(f"{path}: matched {matches} oneOf options")
    if "allOf" in schema and isinstance(schema["allOf"], list):
        for option in schema["allOf"]:
            errors.extend(validate_json_schema(value, option, path))

    if isinstance(value, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{path}: missing required key {key!r}")

        properties = schema.get("properties")
        property_names: set[str] = set()
        if isinstance(properties, dict):
            for key, subschema in properties.items():
                if not isinstance(key, str):
                    continue
                property_names.add(key)
                if key in value:
                    errors.extend(validate_json_schema(value[key], subschema, f"{path}.{key}"))

        additional = schema.get("additionalProperties")
        if additional is False:
            for key in value:
                if key not in property_names:
                    errors.append(f"{path}: unexpected key {key!r}")
        elif isinstance(additional, dict):
            for key, item in value.items():
                if key not in property_names:
                    errors.extend(validate_json_schema(item, additional, f"{path}.{key}"))

    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict) or isinstance(items, bool):
            for index, item in enumerate(value):
                errors.extend(validate_json_schema(item, items, f"{path}[{index}]"))

    return errors


def coerce_tool_arguments(arguments: Any) -> dict[str, Any] | None:
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    if isinstance(arguments, dict):
        return arguments
    return None


def repair_metadata_arguments(
    name: str,
    arguments: dict[str, Any],
    schema: dict[str, Any] | None,
) -> dict[str, Any]:
    if CONFIG.tool_repair != "metadata" or not schema:
        return arguments
    required = schema.get("required")
    properties = schema.get("properties")
    if not isinstance(required, list) or "human_description" not in required:
        return arguments
    if not isinstance(properties, dict):
        return arguments
    human_description_schema = properties.get("human_description")
    if not isinstance(human_description_schema, dict):
        return arguments
    if human_description_schema.get("type") not in (None, "string"):
        return arguments
    if "human_description" in arguments:
        return arguments

    repaired = dict(arguments)
    repaired["human_description"] = f"Local proxy repaired missing human_description for {name}."
    log(f"repaired missing human_description for tool call {name!r}")
    return repaired


def validate_tool_use_block(
    block: dict[str, Any] | None,
    tool_schemas: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if block is None:
        return None

    name = block.get("name")
    if not isinstance(name, str) or not name:
        log("dropping malformed tool call without a function name")
        return None

    if CONFIG.tool_validation in ("name", "schema"):
        if not tool_schemas:
            log(f"dropping tool call {name!r}; request did not offer tools")
            return None
        if name not in tool_schemas:
            log(f"dropping unknown tool call {name!r}")
            return None

    arguments = coerce_tool_arguments(block.get("input"))
    if arguments is None:
        log(f"dropping tool call {name!r}; arguments are not a JSON object")
        return None

    schema = tool_schemas.get(name)
    arguments = repair_metadata_arguments(name, arguments, schema)
    block["input"] = arguments

    if CONFIG.tool_validation == "schema":
        if schema:
            errors = validate_json_schema(arguments, schema)
            if errors:
                log(f"dropping invalid tool call {name!r}: {'; '.join(errors[:3])}")
                return None

    return block


def parse_json_object_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].strip() in ("```", "```json", "```JSON"):
            stripped = "\n".join(lines[1:]).strip()
            if stripped.endswith("```"):
                stripped = stripped[: -len("```")].strip()
    elif "```" in stripped:
        match = re.search(r"```(?:json|JSON)?\s*(.*?)```", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def clean_model_text(text: str) -> str:
    cleaned = text.strip()
    for tag in ("mtplx_final_answer", "final_answer"):
        open_tag = f"<{tag}>"
        close_tag = f"</{tag}>"
        if cleaned.startswith(open_tag):
            cleaned = cleaned[len(open_tag) :].lstrip()
        if cleaned.endswith(close_tag):
            cleaned = cleaned[: -len(close_tag)].rstrip()
    return cleaned


def claude_science_tool_id(tool_id: str | None) -> str:
    if not CONFIG.claude_science_compat:
        return tool_id or f"toolu_{uuid.uuid4().hex}"
    if isinstance(tool_id, str) and tool_id.startswith("toolu_"):
        return tool_id
    seed = tool_id or uuid.uuid4().hex
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()[:24]
    return f"toolu_{digest}"


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


def parse_markdown_function_call_text(text: str, tool_name: str) -> dict[str, Any] | None:
    stripped = text.strip()
    prefix = f"[{tool_name}]("
    if not stripped.startswith(prefix) or not stripped.endswith(")"):
        return None
    target = stripped[len(prefix) : -1].strip()
    return parse_function_call_text(target, tool_name)


def tool_use_block(
    name: str,
    arguments: Any,
    tool_id: str | None = None,
) -> dict[str, Any] | None:
    parsed_arguments = coerce_tool_arguments(arguments)
    if parsed_arguments is None:
        return None
    return {
        "type": "tool_use",
        "id": claude_science_tool_id(tool_id),
        "name": name,
        "input": parsed_arguments,
        **({"caller": {"type": "direct"}} if CONFIG.claude_science_compat else {}),
    }


def parse_json_tool_call_text(
    text: str,
    tool_name_hint: str | None = None,
    allowed_tool_names: list[str] | None = None,
) -> dict[str, Any] | None:
    parsed = parse_json_object_text(text)
    if parsed is None:
        return None

    allowed_names = set(allowed_tool_names or [])

    def allowed(name: str) -> bool:
        return not allowed_names or name in allowed_names

    function = parsed.get("function")
    if isinstance(function, dict):
        name_value = function.get("name") or parsed.get("name")
        if isinstance(name_value, str) and allowed(name_value):
            return tool_use_block(
                name_value,
                function.get("arguments", parsed.get("arguments", parsed.get("input", {}))),
            )

    name_value = parsed.get("name") or parsed.get("tool") or parsed.get("function")
    if isinstance(name_value, str) and allowed(name_value):
        return tool_use_block(name_value, parsed.get("arguments", parsed.get("input", {})))

    if tool_name_hint == "submit_output":
        return tool_use_block(tool_name_hint, parsed)

    if "submit_output" in allowed_names and ("verdict" in parsed or "findings" in parsed):
        return tool_use_block("submit_output", parsed)

    return None


def parse_loose_value(text: str) -> Any:
    value = text.strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def parse_xmlish_tool_call_text(
    text: str,
    allowed_tool_names: list[str] | None = None,
) -> tuple[str, dict[str, Any]] | None:
    stripped = text.strip()
    if not stripped.startswith("<tool_call>"):
        return None
    match = re.search(r"<function=([A-Za-z_][A-Za-z0-9_.-]*)>", stripped)
    if not match:
        return None
    name = match.group(1)
    allowed_names = set(allowed_tool_names or [])
    if allowed_names and name not in allowed_names:
        return None

    arguments: dict[str, Any] = {}
    for parameter, raw_value in re.findall(
        r"<parameter=([A-Za-z_][A-Za-z0-9_.-]*)>(.*?)</parameter>",
        stripped,
        flags=re.DOTALL,
    ):
        arguments[parameter] = parse_loose_value(raw_value)
    return (name, arguments) if arguments else None


def parse_text_tool_call(
    content: Any,
    tool_name_hint: str | None = None,
    allowed_tool_names: list[str] | None = None,
) -> dict[str, Any] | None:
    if not CONFIG.parse_text_tool_calls or not isinstance(content, str):
        return None
    stripped = content.strip()
    allowed_names = set(allowed_tool_names or [])

    if tool_name_hint:
        json_tool = parse_json_tool_call_text(
            stripped,
            tool_name_hint=tool_name_hint,
            allowed_tool_names=allowed_tool_names,
        )
        if json_tool is not None:
            return json_tool
        arguments = parse_function_call_text(stripped, tool_name_hint)
        if arguments is not None:
            return tool_use_block(tool_name_hint, arguments)

    json_tool = parse_json_tool_call_text(stripped, allowed_tool_names=allowed_tool_names)
    if json_tool is not None:
        return json_tool

    for name in sorted(allowed_names, key=len, reverse=True):
        arguments = (
            parse_function_call_text(stripped, name)
            or parse_markdown_function_call_text(stripped, name)
        )
        if arguments is not None:
            return tool_use_block(name, arguments)

    xmlish = parse_xmlish_tool_call_text(stripped, allowed_tool_names=allowed_tool_names)
    if xmlish is not None:
        name, arguments = xmlish
        return tool_use_block(name, arguments)

    parts = stripped.split("::", 3)
    if len(parts) == 4 and parts[0] == "" and parts[1] and parts[2] in ("+json", "json"):
        try:
            arguments = json.loads(parts[3].strip())
        except json.JSONDecodeError:
            arguments = None
        if isinstance(arguments, dict) and (not allowed_names or parts[1] in allowed_names):
            return tool_use_block(parts[1], arguments)

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
    if allowed_names and name not in allowed_names:
        return None
    return tool_use_block(name, arguments)


def openai_to_anthropic(
    data: dict[str, Any],
    requested_model: str | None = None,
    tool_schemas: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content_blocks: list[dict[str, Any]] = []
    schemas = tool_schemas or {}
    offered_tool_names = list(schemas)

    content = message.get("content")
    text_tool_name_hint = single_tool_name(offered_tool_names)
    parsed_text_tool = parse_text_tool_call(
        content,
        tool_name_hint=text_tool_name_hint,
        allowed_tool_names=offered_tool_names,
    )
    parsed_text_tool = validate_tool_use_block(parsed_text_tool, schemas)
    if parsed_text_tool:
        content_blocks.append(parsed_text_tool)
    elif content:
        content_blocks.append({"type": "text", "text": clean_model_text(str(content))})

    for call in message.get("tool_calls") or []:
        fn = call.get("function") or {}
        raw_args = fn.get("arguments") or "{}"
        candidate = tool_use_block(
            str(fn.get("name") or ""),
            raw_args,
            tool_id=call.get("id") or f"toolu_{uuid.uuid4().hex}",
        )
        candidate = validate_tool_use_block(candidate, schemas)
        if candidate:
            content_blocks.append(candidate)

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
            content_block = {
                "type": "tool_use",
                "id": block.get("id"),
                "name": block.get("name"),
                "input": {},
            }
            if CONFIG.claude_science_compat and isinstance(block.get("caller"), dict):
                content_block["caller"] = block["caller"]
            write_sse(
                handler,
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": content_block,
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
    if saw_tool_use:
        return "tool_use"
    if finish_reason == "length":
        return "max_tokens"
    return "end_turn"


def stream_openai_to_anthropic(
    handler: BaseHTTPRequestHandler,
    request: dict[str, Any],
    requested_model: str,
    tool_schemas: dict[str, dict[str, Any]] | None = None,
) -> None:
    started = time.monotonic()
    response = open_openai_stream(request)
    send_sse_headers(handler)
    schemas = tool_schemas or {}

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

    def emit_tool_block(block: dict[str, Any]) -> None:
        nonlocal next_block_index, saw_any_content, saw_tool_use
        stop_text_block()
        start_message_once()
        anthropic_index = next_block_index
        next_block_index += 1
        content_block = {
            "type": "tool_use",
            "id": block["id"],
            "name": block["name"],
            "input": {},
        }
        if CONFIG.claude_science_compat and isinstance(block.get("caller"), dict):
            content_block["caller"] = block["caller"]
        write_sse(
            handler,
            "content_block_start",
            {
                "type": "content_block_start",
                "index": anthropic_index,
                "content_block": content_block,
            },
        )
        write_sse(
            handler,
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": anthropic_index,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps(block.get("input") or {}),
                },
            },
        )
        write_sse(
            handler,
            "content_block_stop",
            {"type": "content_block_stop", "index": anthropic_index},
        )
        saw_any_content = True
        saw_tool_use = True
        handler.wfile.flush()

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
                    tool_schemas=schemas,
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
                block = tool_blocks.setdefault(
                    openai_index,
                    {"id": None, "name": None, "arguments": ""},
                )
                if call.get("id"):
                    block["id"] = call["id"]
                if fn.get("name"):
                    block["name"] = fn["name"]
                if args_delta:
                    output_chars += len(args_delta)
                    block["arguments"] = str(block.get("arguments") or "") + args_delta
    finally:
        response.close()

    stop_text_block()
    for _openai_index, block in sorted(tool_blocks.items()):
        candidate = tool_use_block(
            str(block.get("name") or ""),
            block.get("arguments") or "{}",
            tool_id=str(block.get("id") or f"toolu_{uuid.uuid4().hex}"),
        )
        candidate = validate_tool_use_block(candidate, schemas)
        if candidate:
            emit_tool_block(candidate)

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
                    "tool_allowlist": CONFIG.tool_allowlist,
                    "tool_validation": CONFIG.tool_validation,
                    "tool_repair": CONFIG.tool_repair,
                    "force_mentioned_tool": CONFIG.force_mentioned_tool,
                    "parse_text_tool_calls": CONFIG.parse_text_tool_calls,
                    "schema_log_path": CONFIG.schema_log_path,
                    "harness_tools": CONFIG.harness_tools,
                    "claude_science_compat": CONFIG.claude_science_compat,
                },
            )
            return
        if path == "/v1/models":
            models = [advertised_model_record(model) for model in CONFIG.advertised_models]
            self._json(
                200,
                {
                    "data": models,
                    "has_more": False,
                    "first_id": models[0]["id"] if models else None,
                    "last_id": models[-1]["id"] if models else None,
                },
            )
            return
        if path.startswith("/v1/models/"):
            model = urllib.parse.unquote(path.removeprefix("/v1/models/"))
            if model in CONFIG.advertised_models:
                self._json(200, advertised_model_record(model))
                return
            self._json(
                404,
                {
                    "error": {
                        "type": "not_found_error",
                        "message": f"model {model!r} is not advertised by this proxy",
                    }
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
            log_tool_schema_inventory(payload)
            request = anthropic_to_openai(payload, stream=stream_requested)
            schemas = tool_schema_map(payload, allowlist=CONFIG.tool_allowlist)
            requested_max_tokens = payload.get("max_tokens")
            request_kind = classify_request_kind(payload, request)
            log(
                "request "
                f"kind={request_kind} "
                f"stream={stream_requested} "
                f"messages={len(payload.get('messages') or [])} "
                f"tools={len(payload.get('tools') or [])} "
                f"upstream_tools={len(request.get('tools') or [])} "
                f"tool_choice={request.get('tool_choice')} "
                f"requested_max_tokens={requested_max_tokens} "
                f"upstream_max_tokens={request.get('max_tokens')}"
            )
            if stream_requested and CONFIG.stream_mode == "direct":
                stream_openai_to_anthropic(
                    self,
                    request,
                    requested_model=requested_model,
                    tool_schemas=schemas,
                )
            else:
                upstream = call_openai_chat(request)
                message = openai_to_anthropic(
                    upstream,
                    requested_model=requested_model,
                    tool_schemas=schemas,
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
        "--tool-allowlist",
        default=",".join(CONFIG.tool_allowlist),
        help="Optional comma-separated tool names to forward upstream in pass mode.",
    )
    parser.add_argument(
        "--tool-validation",
        default=CONFIG.tool_validation,
        choices=("off", "name", "schema"),
        help="Validate returned tool calls before emitting Anthropic tool_use blocks.",
    )
    parser.add_argument(
        "--tool-repair",
        default=CONFIG.tool_repair,
        choices=("off", "metadata"),
        help="Repair safe missing tool-call metadata fields before schema validation.",
    )
    parser.add_argument(
        "--force-mentioned-tool",
        default="1" if CONFIG.force_mentioned_tool else "0",
        help="When enabled, force named tool_choice if latest user text explicitly says to use/call/load that tool.",
    )
    parser.add_argument(
        "--parse-text-tool-calls",
        default="1" if CONFIG.parse_text_tool_calls else "0",
        help="Convert narrow textual <tool_call>[...] responses into Anthropic tool_use blocks.",
    )
    parser.add_argument(
        "--schema-log-path",
        default=CONFIG.schema_log_path,
        help="Optional JSONL path for redacted offered-tool schema inventories.",
    )
    parser.add_argument(
        "--harness-tools",
        default=",".join(CONFIG.harness_tools),
        help="Comma-separated structural harness tools that bypass the agent allowlist.",
    )
    parser.add_argument(
        "--claude-science-compat",
        default="1" if CONFIG.claude_science_compat else "0",
        help="Emit Claude Science execution-compatible tool_use metadata.",
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
    CONFIG.tool_allowlist = parse_csv(args.tool_allowlist)
    CONFIG.tool_validation = parse_tool_validation(args.tool_validation)
    CONFIG.tool_repair = parse_tool_repair(args.tool_repair)
    CONFIG.force_mentioned_tool = parse_bool(args.force_mentioned_tool)
    CONFIG.parse_text_tool_calls = parse_bool(args.parse_text_tool_calls)
    CONFIG.schema_log_path = args.schema_log_path
    CONFIG.harness_tools = parse_csv(args.harness_tools)
    CONFIG.claude_science_compat = parse_bool(args.claude_science_compat)
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
        f"tool_allowlist={CONFIG.tool_allowlist or '<all>'}; "
        f"tool_validation={CONFIG.tool_validation}; "
        f"tool_repair={CONFIG.tool_repair}; "
        f"force_mentioned_tool={CONFIG.force_mentioned_tool}; "
        f"parse_text_tool_calls={CONFIG.parse_text_tool_calls}; "
        f"schema_log_path={CONFIG.schema_log_path or '<disabled>'}; "
        f"harness_tools={CONFIG.harness_tools}; "
        f"claude_science_compat={CONFIG.claude_science_compat}; "
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
