# Initial Findings

## Confirmed

- Claude Code has a documented LLM gateway seam via `ANTHROPIC_BASE_URL`.
- Ollama documents a Claude Code local-model launch using:
  - `ANTHROPIC_AUTH_TOKEN=ollama`
  - `ANTHROPIC_API_KEY=""`
  - `ANTHROPIC_BASE_URL=http://localhost:11434`
- Community proxies exist that translate Anthropic Messages API traffic to
  OpenAI-compatible backends and highlight tool-call streaming as the hard part.
- MTPLX is currently exposed locally as an OpenAI-compatible API:
  - `http://127.0.0.1:8030/v1`
  - `mtplx-qwen36-27b-optimized-quality`
  - reported context length: `262144`

## Public References

- Claude Science overview:
  `https://claude.com/docs/claude-science/overview`
- Ollama Claude Code integration:
  `https://docs.ollama.com/integrations/claude-code`
- Ollama Anthropic compatibility API:
  `https://docs.ollama.com/api/anthropic-compatibility`
- Existing proxy prior art:
  - `https://github.com/1rgs/claude-code-proxy`
  - `https://github.com/fuergaosi233/claude-code-proxy`

## Unknown

- Whether Claude Science honors the same `ANTHROPIC_BASE_URL` seam as Claude
  Code.
- Whether Claude Science requires Claude-account OAuth features that a local
  proxy cannot emulate.
- Whether its reviewer/orchestrator model selection can be pointed at a local
  model without server-managed settings or a Claude Apps Gateway.

## First Experiment

Run the local proxy, then launch the copied Claude Science app with an isolated
data directory and `ANTHROPIC_BASE_URL=http://127.0.0.1:18080`. If proxy logs
show `/v1/messages` traffic from Claude Science, the seam exists. If not, the
next path is Claude Apps Gateway research or registering MTPLX as a managed
model endpoint/tool rather than replacing the coordinator model.

## 2026-06-30 Result

The gateway seam exists.

Setup:

- Official Claude Science remained on `127.0.0.1:8765`.
- Isolated copied app ran on `127.0.0.1:18765`.
- Local proxy ran on `127.0.0.1:18080`.
- MTPLX upstream ran on `127.0.0.1:8030/v1`.

Evidence:

- The isolated Claude Science startup called the proxy's `GET /v1/models?limit=1000`.
- Onboarding generated starter tasks through `POST /v1/messages` with
  `stream=true`, `messages=3`, `tools=13`, and `max_tokens=128000`; MTPLX
  completed the upstream request and the UI accepted the result.
- A first-session prompt, "reply with exactly LOCAL MODEL OK", triggered:
  - one non-streaming `/v1/messages` call with `messages=1`, `tools=1`;
  - one streaming `/v1/messages` agent call with `messages=2`, `tools=25`;
  - the Claude Science UI rendered `LOCAL MODEL OK`.
- After hardening and advertising both `claude-opus-4-8` and the real MTPLX
  model, a second interactive prompt rendered `SECOND LOCAL OK` in the Claude
  Science UI. The proxy log showed:
  - a non-streaming `/v1/messages` call with `messages=1`, `tools=1`;
  - a streaming `/v1/messages` call with `messages=4`, `tools=25`;
  - a follow-up review call with `messages=5`, `tools=13`.
- The daemonized proxy launcher survived after its parent shell exited and
  passed `./scripts/smoke-proxy.sh`.

Known rough edges:

- The UI still displays `Model: claude-opus-4-8 (unavailable)`, even though
  the request path is local and `/v1/models` advertises that alias. This is
  likely model metadata / UI state rather than a routing failure.
- Claude Science requests very large `max_tokens` values. The proxy now caps
  upstream `max_tokens` with `PROXY_MAX_TOKENS_CAP` to keep local runs sane.
- The proxy supports true stream bridging in tests, including text deltas and
  tool-call argument deltas. MTPLX/Qwen direct streaming hung after
  `message_start` in live testing, so MTPLX profiles use buffered mode.
- MTPLX latency is workable for tiny prompts but too slow for full scientific
  loops without careful model/profile tuning.
- MTPLX can return `session_busy` when Claude Science sends background-review
  calls while another local generation is active. The proxy retries transient
  upstream load responses, but persistent saturation still needs operator
  attention.

## 2026-06-30 Proxy Refinement Result

Additional hardening:

- Buffered Anthropic SSE responses now send `Connection: close` and close after
  `message_stop`. This removed the observed app-side idle-watchdog mismatch
  where the proxy returned `200` but Claude Science kept waiting.
- `PROXY_STREAM_MODE=direct|buffered` is configurable.
- `PROXY_TOOL_MODE=pass|drop` is configurable.
- `PROXY_PARSE_TEXT_TOOL_CALLS=1` enables Qwen-oriented adapters for observed
  reviewer pseudo-tool-call formats.
- `./scripts/test-streaming-proxy.sh` covers:
  - streamed text deltas;
  - streamed tool-call argument deltas;
  - full JSON response fallback on a streamed request;
  - socket close after `message_stop`;
  - non-streaming responses;
  - observed Qwen text-tool-call formats.

Live UI evidence:

- With `profiles/mtplx-qwen-analysis.env.example`, Claude Science sent a
  MASLD-HCC analysis request with `tools=26` and `upstream_tools=0`; the proxy
  routed it to MTPLX and Claude Science rendered a real analysis in the UI.
- The persisted frame `60449c6c-b5db-4f9b-970b-656a23abf2ee` completed with a
  bounded MASLD-HCC response on tumor-intrinsic dedifferentiation vs
  stromal/sampling contamination.
- A final tiny UI prompt completed with:
  `Local proxy analysis path works, but review/tool adaptation remains model-specific.`
- A fresh-session verifier completed with:
  `FRESH_XML_ADAPTER_OK. Local-model reviewer tool calls need provider-specific adapters and regression fixtures.`
- In that fresh verifier, the reviewer produced real Anthropic `tool_use` and
  `tool_result` blocks and the reviewer frame stored `structured_output` with
  `verdict: pass`.

Remaining caveat:

- The main analysis path is working. Reviewer/tool adaptation is still
  model-specific, but the test suite now covers all Qwen reviewer formats
  observed in this session and the latest fresh-session verifier produced
  structured reviewer output.
