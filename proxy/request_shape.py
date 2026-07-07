"""Claude Science request-shape classification.

The local proxy treats Claude Science traffic as brokered request kinds first.
Provider transport, streaming mode, and profile settings should hang off this
classification instead of deciding behavior from launch scripts alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequestShape:
    kind: str
    offered_tools: tuple[str, ...]
    forwarded_tools: tuple[str, ...]
    harness_tools: tuple[str, ...]
    stream_requested: bool
    stream_mode: str
    requested_model: str
    requested_max_tokens: Any
    upstream_max_tokens: Any
    message_count: int
    tool_choice: Any

    def redacted_summary(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "stream_requested": self.stream_requested,
            "stream_mode": self.stream_mode,
            "messages": self.message_count,
            "tools": len(self.offered_tools),
            "upstream_tools": len(self.forwarded_tools),
            "tool_choice": self.tool_choice,
            "requested_max_tokens": self.requested_max_tokens,
            "upstream_max_tokens": self.upstream_max_tokens,
        }


def offered_tool_names(payload: dict[str, Any]) -> tuple[str, ...]:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return ()
    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return tuple(names)


def forwarded_tool_names(request: dict[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for item in request.get("tools") or []:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return tuple(names)


def classify_request_kind(
    *,
    offered_tools: tuple[str, ...],
    forwarded_tools: tuple[str, ...],
    harness_tools: tuple[str, ...],
) -> str:
    offered = set(offered_tools)
    forwarded = set(forwarded_tools)
    harness = set(harness_tools)
    if offered & harness or forwarded & harness:
        return "harness"
    if forwarded:
        return "tool_agent"
    if offered:
        return "tools_hidden"
    return "plain"


def build_request_shape(
    payload: dict[str, Any],
    request: dict[str, Any],
    *,
    harness_tools: list[str],
    stream_mode: str,
    requested_model: str,
    stream_requested: bool,
) -> RequestShape:
    offered = offered_tool_names(payload)
    forwarded = forwarded_tool_names(request)
    harness = tuple(harness_tools)
    kind = classify_request_kind(
        offered_tools=offered,
        forwarded_tools=forwarded,
        harness_tools=harness,
    )
    return RequestShape(
        kind=kind,
        offered_tools=offered,
        forwarded_tools=forwarded,
        harness_tools=harness,
        stream_requested=stream_requested,
        stream_mode=stream_mode,
        requested_model=requested_model,
        requested_max_tokens=payload.get("max_tokens"),
        upstream_max_tokens=request.get("max_tokens"),
        message_count=len(payload.get("messages") or []),
        tool_choice=request.get("tool_choice"),
    )
