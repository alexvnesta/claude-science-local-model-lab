# Prior Art Review

Reviewed on 2026-07-01 from shallow local clones plus GitHub metadata. The goal
was to confirm what existing Claude Code proxy projects already solve before
publishing this Claude Science local-model lab.

## Summary

The ecosystem already has strong Claude Code adapters. The reusable ideas are:
Anthropic Messages API translation, OpenAI-compatible backend routing,
Anthropic SSE event emission, tool-call ID/argument conversion, local-only
binding, request monitoring, provider auth, and token/request optimization.

The gap this repo addresses is narrower: Claude Science appears to exercise a
Claude-like Messages path, but it also emits distinct foreground, hidden-tool,
and reviewer/harness request shapes. The reviewer/harness path needs structural
tools such as `submit_output`, and live Qwen reviewer frames also needed
artifact-inspection tools. None of the reviewed projects directly targets this
Claude Science request-shape mix.

## Reviewed Projects

### UniClaudeProxy

Repo: [vibheksoni/UniClaudeProxy](https://github.com/vibheksoni/UniClaudeProxy)

License: MIT

Reviewed commit: `2f512a3626a25d24cee4e2387db5007802928d4c`

Relevant traits:

- FastAPI proxy for Claude Code.
- Converts Anthropic Messages to OpenAI Chat Completions, OpenAI Responses,
  Gemini, or Anthropic passthrough.
- Handles native tool calls, ReAct/XML fallback, image modes, reasoning blocks,
  system-prompt replacement, hot-reload config, local-only mode, and streaming.

Takeaway for this repo:

UniClaudeProxy is the closest "universal adapter" reference. Its ReAct fallback
and provider-specific conversion reinforce the need to keep model quirks behind
profiles. Our repo stays smaller and Claude-Science-specific instead of trying
to be universal.

### raine/claude-code-proxy

Repo: [raine/claude-code-proxy](https://github.com/raine/claude-code-proxy)

License: MIT

Reviewed commit: `d268aa55129c3d51db485a62a68c55e7cb524a6b`

Relevant traits:

- Rust proxy for routing Claude Code to ChatGPT/Codex, Kimi, or Cursor Agent.
- Implements provider login/token storage, model selection through
  `ANTHROPIC_MODEL`, stream reduction, Anthropic SSE emission, web-search
  compatibility, monitor UI, and tests.
- Always talks to upstream providers with streaming requests and recommends
  disabling Claude Code non-streaming fallback.
- Uses the Codex Responses endpoint, not generic OpenAI Chat Completions.
- Translates Claude Code's hosted `web_search_20250305` tool into Codex's
  native Responses `web_search` tool, including non-empty domain filters and
  forced `tool_choice` mapping.
- Translates Codex `web_search_call` output events back into Anthropic
  `server_tool_use` and `web_search_tool_result` content blocks, with
  `usage.server_tool_use.web_search_requests` accounting.
- Requests Codex reasoning summaries when reasoning effort is enabled and emits
  those summaries as Anthropic `thinking` blocks when Codex provides them.
- Has opt-in `previous_response_id` continuation for append-only Codex turns,
  with stale-state fallback to full-history requests.

Takeaway for this repo:

This is the strongest reference for a native OpenAI Responses bridge. The most
important lesson is that Anthropic hosted tools need a typed provider capability
boundary: a Responses-capable provider can map hosted search to native
`web_search`, while a generic Chat Completions provider such as local MTPLX
cannot honestly expose that capability unless the proxy executes search itself.
Our current MTPLX path therefore omits unsupported hosted server tools instead
of pretending they are ordinary OpenAI functions. Borrow the typed server-tool
model, event reducer, reasoning-summary mapping, cancellation discipline, and
continuation-state tests if this repo adds a Codex/Responses provider.

### routatic/proxy

Repo: [routatic/proxy](https://github.com/routatic/proxy)

License: AGPL-3.0

Reviewed commit: `9e294f9a2ec2ea5fa20b6c126800bac5847ced23`

Relevant traits:

- Go CLI proxy for Claude Code.
- Routes Anthropic-format requests through OpenCode Go, OpenCode Zen, or AWS
  Bedrock.
- Transforms between Anthropic Messages, OpenAI Chat Completions, OpenAI
  Responses, Gemini, and raw Anthropic wire formats depending on provider/model.
- Includes scenario routing for default, background, thinking, complex,
  long-context, and vision requests; streaming-specific routing; fallback
  chains; circuit-breaker style health handling; Anthropic-first failover; token
  counting; config hot reload; debug capture with redaction; daemon/autostart;
  and a macOS GUI.

Takeaway for this repo:

This is the strongest reference for routing policy as a first-class subsystem.
It reinforces that future Claude Science support should separate request-shape
classification from provider transport. Because it is AGPL-3.0, it is credited
as design prior art only; do not copy its implementation into this MIT repo
without an explicit license decision.

### seifghazi/claude-code-proxy

Repo: [seifghazi/claude-code-proxy](https://github.com/seifghazi/claude-code-proxy)

License: MIT

Reviewed commit: `02c9c766679eee75c861bbde11c6d8b5249d44a7`

Relevant traits:

- Transparent proxy and monitor for Claude Code.
- SQLite-backed request/conversation capture with a web dashboard.
- Optional routing of named Claude Code subagents to OpenAI models.
- Core Anthropic service mostly forwards to an Anthropic-compatible backend.

Takeaway for this repo:

This is most relevant for observability and routing-by-agent ideas, not for
local model translation. Claude Science does not expose reliable frame metadata
in the model HTTP payload, so our proxy classifies request kind from payload
shape instead.

### Rishurajgautam24/free-claude-code

Repo: [Rishurajgautam24/free-claude-code](https://github.com/Rishurajgautam24/free-claude-code)

License: MIT

Reviewed commit: `a599319dd6d56cf5ea1db7e52eeac0bc80fccb7c`

Relevant traits:

- Python proxy for Claude Code through NVIDIA NIM, OpenRouter, and LM Studio.
- Includes Anthropic-to-OpenAI message conversion, Anthropic SSE builder,
  thinking-token support, heuristic text-tool parser, request optimizations,
  rate limiting, and messaging integrations.
- The local `_local/free-claude-code` clone in this workspace points to this
  repo. It remains comparison material only and is not included in this public
  repo.

Takeaway for this repo:

This line is the practical "NVIDIA NIM proxy" prior art from the pasted search
overview. It overlaps with our need for OpenAI-compatible conversion and local
model quirks, but it is built around Claude Code ergonomics rather than Claude
Science reviewer/harness traffic.

### Alishahryar1/free-claude-code

Repo: [Alishahryar1/free-claude-code](https://github.com/Alishahryar1/free-claude-code)

License: MIT

Reviewed commit: `6a48811a9a648110c894738ee62dcb48b69cef96`

Relevant traits:

- Larger current Free Claude Code line with Claude Code and Codex support.
- Exposes many providers, Admin UI, generated model catalogs, local
  optimization intercepts, web-server tool handling, OpenAI Responses support,
  and a more extensive conversion/test surface.
- Its Anthropic-to-OpenAI conversion handles harder OpenAI chat edge cases such
  as assistant text after tool calls and native-only server-tool blocks.

Takeaway for this repo:

This is a more complete general gateway. The main reusable lesson is to keep
transport/provider support modular and tested. Our repo intentionally stays as
a small lab until Claude Science-specific behavior is better understood.

### llmtrim

Repo: [fkiene/llmtrim](https://github.com/fkiene/llmtrim)

License: MPL-2.0

Reviewed commit: `47375c77aff30e29899414038d79b4e1ab929ecd`

Relevant traits:

- Local HTTPS proxy, CLI, MCP server, and embeddable library for deterministic
  token compression.
- Intercepts selected LLM API hosts, compresses supported request bodies, and
  forwards responses unchanged.
- Uses token gates, quality gates, cache-zone discipline, and careful host/CA
  boundaries.

Takeaway for this repo:

llmtrim is not a Claude Code model adapter, so it should not be conflated with
the Claude Code proxy projects. It is useful prior art for future safe prompt,
tool-schema, or tool-output compression, but this repo does not include an
llmtrim-style compression layer.

### 1rgs/claude-code-proxy

Repo: [1rgs/claude-code-proxy](https://github.com/1rgs/claude-code-proxy)

License: no license detected by GitHub

Reviewed commit: `5e45ba683ded931c1832cfca6468a791c6855e45`

Relevant traits:

- FastAPI/LiteLLM proxy for Anthropic clients to OpenAI, Gemini, or Anthropic.
- Simple model mapping for Haiku/Sonnet-style requests.
- Supports streaming and non-streaming translation.

Takeaway for this repo:

This is earlier prior art for the basic gateway idea. Because no license was
detected, treat it as conceptual reference only unless the license situation is
clarified upstream.

### fuergaosi233/claude-code-proxy

Repo: [fuergaosi233/claude-code-proxy](https://github.com/fuergaosi233/claude-code-proxy)

License: MIT

Reviewed commit: `7ea4177a54a5ff7969a5f8ec76d9f80f2e0409e5`

Relevant traits:

- Python/FastAPI proxy for OpenAI-compatible APIs.
- Converts Claude messages, tool uses, tool results, images, model mappings,
  and custom headers.
- Implements streaming conversion, tool-call deltas, and cancellation-aware
  streaming.

Takeaway for this repo:

This is a compact reference for Claude-to-OpenAI conversion. Its streaming
tool-call handling reinforces the need for regression tests around partial JSON
argument deltas. Our proxy currently validates the completed streamed argument
object before emitting a Claude Science tool call; app-visible incremental tool
arguments remain future work.

## Our Adaptation Boundary

This repo's unique implementation work is the Claude Science local lab:

- Isolated copied app launch that leaves the official app path alone.
- Single-file, dependency-free Python Anthropic-to-OpenAI-compatible proxy.
- Configurable profiles for generic local backends and MTPLX/Qwen.
- Request classification as `plain`, `tools_hidden`, `tool_agent`, or
  `harness`.
- Separate harness tool list, defaulting to `submit_output`, for structural
  reviewer requests.
- Tool pass-through that preserves the request-specific tool surface Claude
  Science offered, without proxy-side task profiles or reviewer allowlists.
- Schema validation against the request's offered tool schemas.
- Narrow metadata-only repair for missing `human_description`.
- Python sanity filtering for observed malformed local-model execution calls.
- Hidden-tool guard that tells local models not to fake tool use when schemas
  are intentionally dropped.
- Qwen-oriented text-tool-call adapters for reviewer formats observed in live
  Claude Science runs.
- Redacted schema inventory logging and `/healthz` metrics for adapter
  development without prompts or tool payloads.
- Regression tests for streaming, heartbeat comments, request IDs, filtering,
  finite SSE close, health metrics, and the observed text-tool-call variants.

## Credit Checklist

- Keep `NOTICE.md` in the repository root.
- Keep this review updated when adding a new adapter based on prior art.
- Do not copy third-party source without carrying its license and attribution.
- Do not copy AGPL implementation code into this MIT repository without an
  explicit relicensing or licensing change.
- Keep `_local/` ignored and never commit Claude Science app bundles, runtime
  databases, account state, logs, cookies, prompts, tool results, or artifacts.
