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
  - `https://github.com/vibheksoni/UniClaudeProxy`
  - `https://github.com/raine/claude-code-proxy`
  - `https://github.com/routatic/proxy`
  - `https://github.com/seifghazi/claude-code-proxy`
  - `https://github.com/Rishurajgautam24/free-claude-code`
  - `https://github.com/Alishahryar1/free-claude-code`
  - `https://github.com/fkiene/llmtrim`
  - `https://github.com/1rgs/claude-code-proxy`
  - `https://github.com/fuergaosi233/claude-code-proxy`

See `docs/prior-art-review.md` and `NOTICE.md` for the reviewed commits,
licenses, and how this Claude Science-specific lab differs.

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
- `PROXY_TOOL_VALIDATION=off|name|schema` is configurable. The default
  `schema` mode emits Anthropic `tool_use` only for offered tool names with
  JSON-object arguments that satisfy the offered schema subset.
- `PROXY_TOOL_ALLOWLIST` is configurable. A fresh pass-mode probe with all 26
  tools forwarded hung against MTPLX/Qwen, so focused tool-loop tests should
  start with the allowlisted probe profile before broadening.
- `PROXY_HARNESS_TOOLS` is configurable and defaults to `submit_output`.
  Harness/reviewer tools bypass the foreground science-tool allowlist because
  reviewer frames need `submit_output` even when Qwen should see only a small
  task-relevant foreground tool set.
- `PROXY_TOOL_REPAIR=metadata` is configurable. A live pass-mode foreground
  probe showed Qwen selecting the correct `search_skills` tool but omitting the
  required `human_description` metadata field; metadata repair fills that
  non-semantic field while still rejecting missing semantic fields.
- `PROXY_FORCE_MENTIONED_TOOL=1` is enabled in the Qwen probe profile after a
  live `skill` probe showed Qwen claiming `figure-composer` was loaded without
  actually calling the `skill` tool.
- `PROXY_SCHEMA_LOG_PATH` can write redacted JSONL inventories of offered tool
  schemas for adapter development without logging prompts, outputs, full
  descriptions, or tool results.
- In `drop` mode, the proxy now injects a hidden-tool guard for non-reviewer
  tool sets. This prevents the local model from claiming searches, code
  execution, file reads, or artifact creation when Claude Science offered tools
  but the profile hid them upstream.
- `PROXY_PARSE_TEXT_TOOL_CALLS=1` enables Qwen-oriented adapters for observed
  reviewer pseudo-tool-call formats.
- Request logs now include `kind=harness`, `kind=tool_agent`,
  `kind=tools_hidden`, or `kind=plain` so reviewer, foreground tool, and
  analysis-only traffic are not conflated during debugging.
- `./scripts/test-streaming-proxy.sh` covers:
  - streamed text deltas;
  - streamed valid tool-call argument deltas;
  - filtering invalid streamed and non-streamed tool calls;
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
- In pass-through mode with all 26 Claude Science tools forwarded, MTPLX/Qwen
  selected the correct foreground `search_skills` tool but omitted required
  `human_description`; before metadata repair this was filtered, leaving an
  empty turn.
- With `profiles/mtplx-qwen-tool-probe.env.example`, the foreground
  `search_skills` probe completed: the proxy repaired missing
  `human_description`, Claude Science executed the real `search_skills` tool,
  returned a `tool_result`, and Qwen produced a final answer. The persisted
  frame was `365cf30d-cec0-4d6d-a38f-2e6efed7c00f`.
- A tool-heavy MASLD-HCC figure prompt exposed the failure mode that motivated
  the hidden-tool guard. Frame `977d476d-becf-41c7-8da1-287d43d721de`
  completed with a fake `<anonymous_function>()</anonymous_function>` and no
  real tool activity. The reviewer frame
  `7a330345-2e6e-40c2-8c30-d7ff07f50a32` correctly identified the claimed
  action as a failure, but emitted markdown-wrapped function text
  `[submit_output](submit_output(...))`; Claude Science recorded
  `inconclusive` with `no structured output`.
- After adding the hidden-tool guard, frame
  `e82fb0a0-a309-407a-81bf-6102afeb1a96` returned an honest limitation and
  draft figure-panel plan without fake tool tags. Its reviewer exposed another
  adapter shape: fenced reviewer JSON and fenced OpenAI-style function JSON with
  preamble text.
- After adding adapters for those JSON shapes, fresh frame
  `e3d8b42c-e4ab-4428-bfaf-e73d5471a781` completed with
  `REVIEWER_JSON_ADAPTER_OK`, no fake tool call, and reviewer frame
  `f10d4677-59da-4101-b340-04879ec18ca1` stored
  `structured_output: {"findings":[],"verdict":"pass"}` after real
  `submit_output` `tool_use` / `tool_result` messages.
- A later focused profile exposed an agent-shape mistake: the same global
  allowlist was being applied to foreground and reviewer requests. Reviewer
  frame `6cd7c709-26e5-45de-9410-afd0aae7a07f` was asked to call
  `submit_output` while the focused foreground allowlist hid that tool from the
  upstream request. The proxy now treats configured harness tools separately
  and direct probes show `kind=harness` with forced `submit_output`, and
  `kind=tool_agent` with forced `skill`.
- A temporary execution-only proxy on `127.0.0.1:18081` exposed only `python`
  and `save_artifacts`. Direct Qwen probes produced schema-valid `tool_use`
  blocks for both tools:
  - `python`: `code: print("QWEN_PYTHON_OK")`, `environment: python`.
  - `save_artifacts`: `files: ["qwen_probe.txt"]`, `language: text`.
  These are formatting proofs only; app-side execution still needs a live
  Claude Science `tool_result`/artifact-version proof.
- A fresh authenticated app-API proof used `scripts/submit-local-request.py` to
  create frame `a160c85e-4258-40cc-9196-dd43a9e9d565`. The foreground frame
  emitted a real `search_skills` `tool_use`, received a real `tool_result`, and
  answered `API_KIND_SEARCH_OK`. Reviewer child
  `33efd0d8-5f9b-4ae0-810b-4db8dd5b96cf` then emitted a real `submit_output`
  `tool_use`, received a success `tool_result`, and completed with
  `structured_output: {"findings":[]}`. The proxy log classified the foreground
  request as `kind=tool_agent` and the reviewer request as `kind=harness`.

Remaining caveat:

- The main analysis path is working. Reviewer/tool adaptation is still
  model-specific, but the test suite now covers all Qwen reviewer formats
  observed in this session and the latest fresh-session verifier produced
  structured reviewer output. Foreground agents, reviewers, and future
  subagents should be debugged as separate request shapes. A clean reviewer
  pass may be represented only on the reviewer frame's `structured_output`; the
  `verification_checks` table is mainly useful when a check is opened or
  inconclusive.

## 2026-07-01 Execution/Permission Result

Additional app-side execution evidence:

- The execution profile now enables `PROXY_CLAUDE_SCIENCE_COMPAT=1`, which
  normalizes OpenAI-style tool ids to Anthropic-looking `toolu_...` ids and
  adds `caller: {"type":"direct"}` to emitted tool-use blocks.
- Frame `b1ff2cd4-dac4-4417-96f1-6cd39c491dbc` is the strongest verified
  foreground execution proof so far:
  - Qwen emitted a compat `python` tool call.
  - Claude Science queued a local execution permission request.
  - After approval, Python created `qwen_probe_compat.png` and
    `qwen_probe_compat.txt`.
  - Qwen emitted `save_artifacts`.
  - Claude Science saved both files as artifacts:
    `7596667b-9170-4efd-94f0-1dca19caf8cf` and
    `61d400d7-0252-4fa5-98c5-22866f425bfc`.
  - Reviewer child `831a0f6c-d2ed-4438-94cd-6ed6f3c8f5bf` completed with
    `structured_output: {"findings":[]}`.
- The local execution permission card should be resolved with conversation
  scope, matching the UI path "Permissions -> Allow -> for this conversation".
  The scripted equivalent is now:
  `scripts/resolve-input-request.py --frame-id <frame> --scope conversation`.
- Frame `6b100da8-0737-4232-b106-c15b347273cb` demonstrated the scoped
  permission point on an older pre-compat tool id. Approving with
  `scope: "conversation"` cleared `pending_input_requests` and produced an
  `execution_log` row writing `qwen_probe.png` and `qwen_probe.txt`. Because
  that frame used pre-compat `call_...` ids and later hit slow post-tool
  generation, it is evidence for permission/execution, not the preferred
  artifact-loop proof.
- A natural MASLD-HCC figure prompt exposed a Qwen behavior failure: the model
  promised to create artifacts and/or load figure skills but did not call a
  tool. Reviewer frames correctly flagged this as high-severity failed work.
- `PROXY_FORCE_MENTIONED_TOOL=1` was refined after a strict prompt mentioned
  both `python` and `save_artifacts`. The proxy now chooses the earliest
  explicit tool mention so "call python ... after python succeeds, call
  save_artifacts" forces `python`, not the later/longer tool name.
- Long figure-producing Qwen runs exposed the buffered streaming ceiling. In
  `PROXY_STREAM_MODE=buffered`, the app accepts short tool-loop responses, but
  a long upstream generation can starve Claude Science of SSE events until the
  client disconnects. A quick `PROXY_STREAM_MODE=direct` live-app trial did not
  produce a persisted tool-loop frame, so direct streaming remains future work.

Practical current ceiling:

- Qwen 27B can drive a short Claude Science execution/artifact/reviewer loop
  when tools are focused, ids are compatibility-normalized, local execution is
  approved for the conversation, and the generation completes quickly.
- It is not yet reliable for full figure-producing analyses with reviewers in
  one live app run. The next engineering target is robust direct Anthropic SSE
  emission/heartbeats for long OpenAI-compatible tool-call streams, plus fresh
  model-specific profiles for Gemma/Qwen variants.
