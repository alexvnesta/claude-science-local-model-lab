# Verification Checklist

Use this checklist before publishing a run result or changing the proxy.

## 0. Confirm Access

Before debugging the proxy, confirm the user has official Claude Science beta
access and can sign in to the installed app. Verified Anthropic docs currently
say Claude Science is beta; Pro and Max have app access on by default; Team and
Enterprise organizations must enable it in Organization settings; Free users do
not have access; and entitled members download the app and sign in with their
`claude.ai` account.

See `docs/access.md` for source links and notes.

Expected:

- Claude Science is installed locally by the user.
- The user can launch the official app and sign in normally.
- On Team or Enterprise, organization capability enablement and role
  entitlement have been checked.
- No copied app bundle, account state, logs, or runtime data are committed.

## 1. Confirm Separation

```bash
./scripts/status.sh
```

Expected:

- Official Claude Science is still on `127.0.0.1:8765`.
- Local Claude Science uses `127.0.0.1:18765`.
- Proxy uses `127.0.0.1:18080`.
- MTPLX or another OpenAI-compatible backend is reachable.

## 2. Start Proxy

```bash
PROXY_PROFILE=profiles/mtplx-qwen.env.example ./scripts/start-proxy-detached.sh
```

For another local backend, copy and edit the generic profile:

```bash
cp profiles/openai-compatible.env.example profiles/local.env
PROXY_PROFILE=profiles/local.env ./scripts/start-proxy-detached.sh
```

## 3. Smoke Proxy

```bash
./scripts/smoke-proxy.sh
./scripts/test-streaming-proxy.sh
```

Expected:

- `/healthz` returns the configured upstream, provider name, advertised model
  list, and redacted provider summary.
- `/healthz` shows the intended `stream_mode`, `tool_mode`,
  `stream_heartbeat_seconds`, `tool_allowlist`, `tool_validation`, and optional
  `schema_log_path` values.
- `/healthz` shows `harness_tools`, normally `["submit_output"]`.
- If the active profile sets them, `/healthz` also shows
  `harness_tool_allowlist`.
- `/healthz.metrics` shows request counts by kind and stream mode, provider
  latency by kind, retry/error counts, and tool-filter reason counts. It should
  not include prompt text, tool arguments, tool results, account state, or
  artifact contents.
- `/v1/messages/count_tokens` returns an `input_tokens` value.
- `/v1/messages` returns a message containing `mtplx proxy ok`.
- `./scripts/test-streaming-proxy.sh` passes streamed text, direct-stream
  heartbeat comments, request ID response headers, buffered validation of
  upstream streamed tool-call deltas, invalid tool-call filtering, full-JSON
  fallback, finite SSE close, and redacted health metrics.

## 4. Launch Isolated Claude Science

```bash
./scripts/launch-claude-science-local.sh
```

In another terminal:

```bash
./scripts/local-url.sh
```

Open the returned URL.

For scripted local-app verification without browser automation, submit a
request through the authenticated app API:

```bash
scripts/submit-local-request.py \
  --project-id <project-id> \
  "API path probe. Use search_skills once to search for proxy routing. After the tool result, answer with marker API_KIND_SEARCH_OK."
```

The helper obtains a short-lived login cookie through `claude-science url`,
posts to `/api/projects/{project_id}/request`, and prints the accepted
`root_frame_id`.

When Claude Science pauses on a local execution permission card, approve it
with conversation scope, matching the UI path "Permissions -> Allow -> for this
conversation":

```bash
scripts/resolve-input-request.py \
  --frame-id <root_frame_id> \
  --scope conversation
```

The helper defaults to `--scope conversation`. Use `--scope once` only when you
want to mimic a single-use approval. A correct approval should clear
`output_data.pending_input_requests` and create an `execution_log` row for
`python`/local execution.

## 5. Interactive UI Proof

Send:

```text
For this gateway test, reply with exactly LOCAL MODEL OK. Do not use tools.
```

Expected:

- The Claude Science UI renders `LOCAL MODEL OK`.
- `_local/proxy.log` shows `POST /v1/messages` for the same interaction.
- The proxy log shows the upstream model, requested token count, capped token
  count, request `kind`, request ID, stream mode, MTPLX background-risk fields,
  and upstream completion time.
- For MTPLX, `session_busy` means MTPLX classified a small helper/reviewer-style
  call as background while foreground generation was active or queued. With
  `PROXY_MTPLX_AVOID_BACKGROUND_BYPASS=1`, risk-shaped calls are raised above
  MTPLX's 48-token background cutoff so they queue instead of returning an
  immediate 503. Persistent `session_busy` after that points to a non-guarded
  background source or a saturated backend.

For screenshots or local debugging captures, also confirm:

- The visible model label comes from `PROXY_MODEL_DISPLAY_NAMES` and matches
  the provider being demonstrated.
- The app does not show an upstream-capacity retry, `unavailable` state, or an
  old failed frame.
- The proxy log for the captured turn shows the same provider and request ID.
- No account state, cookies, API keys, private prompts, tool arguments, tool
  results, or private artifacts are visible.

OpenRouter-free note from 2026-07-01: provider-only smoke passed, but full
Claude Science UI prompts to two `:free` models hit upstream 429 capacity
responses. Treat that as a provider-capacity caveat, not as a proxy routing
failure.

## 6. Optional Tool-Loop Proof

Use a fresh session when possible. Keep the prompt short and focused on
transport shape, not scientific ability. For example:

```text
For this proxy tool-loop test, use search_skills once to search for proxy
routing. After the tool result, answer with marker API_KIND_SEARCH_OK.
```

Expected:

- The UI renders a substantive answer, not just a gateway echo.
- The frame eventually reaches `completed` in the isolated SQLite database.
- With `PROXY_TOOL_MODE=drop`, `_local/proxy.log` should show Claude Science
  tool schemas dropped before upstream, e.g. `tools=26 upstream_tools=0`.
- In `PROXY_TOOL_MODE=drop`, tool-heavy prompts may still fail by claiming fake
  tool use. Document that as a model failure; the proxy should not repair it.
- In `PROXY_TOOL_MODE=pass` with `PROXY_TOOL_VALIDATION=schema`, tool-heavy
  prompts should forward Claude Science tool schemas upstream, but returned tool
  calls should be emitted only when they use an offered tool name and JSON-object
  arguments that satisfy the offered schema. Unknown tools, malformed JSON args,
  and missing required fields should be filtered rather than wrapped as
  executable `tool_use`.
- Missing `human_description`, malformed JSON args, and missing semantic fields
  such as `command`, `code`, or `file_path` should be filtered rather than
  repaired by the proxy.
- If full-tool forwarding stalls, use a temporary `PROXY_TOOL_ALLOWLIST=...`
  override and verify a single allowlisted tool loop before broadening.
- For execution-tool probes, use explicit overrides such as
  `PROXY_TOOL_ALLOWLIST=python,save_artifacts` and begin with single-tool prompts
  for `python` or `save_artifacts`. Direct proxy success means the model
  formatted the tool call; app-side success additionally requires a persisted
  Claude Science `tool_result` and, for artifacts, a saved artifact version.
- New app-side execution proofs can set `PROXY_CLAUDE_SCIENCE_COMPAT=1` when
  the app requires `toolu_...` ids and `caller: {"type":"direct"}` metadata.
  Older pre-compat frames with OpenAI-style `call_...` ids can still clear the
  permission card and run Python, but they are poor recovery targets for
  artifact-loop verification.
- Reviewer/harness calls should log `kind=harness`, forward `submit_output`
  even if it is absent from `PROXY_TOOL_ALLOWLIST`. The proxy should translate
  explicit Claude Science `tool_choice` values, but it should not add a
  harness-specific `tool_choice` when the app did not request one.
- Reviewer/harness calls may need their own tool set. When a focused probe uses
  `PROXY_HARNESS_TOOL_ALLOWLIST`, `/healthz` should show only the explicit
  reviewer tools for that run plus `submit_output`. In reviewer logs,
  `kind=harness` should show the corresponding forwarded tool count. This is a
  profile override for inspection, not a model-specific rescue path.
- When `PROXY_SCHEMA_LOG_PATH` is set, `_local/tool-schema-capture.jsonl` should
  receive one redacted inventory per tool-offering request. Keep this file out
  of git and use it to debug offered-tool and schema mismatches.
- Python tool calls should be inline executable code, not filenames or
  generated artifact paths. If a conceptually bad call satisfies the offered
  tool schema, treat that as model behavior to document, not as a proxy
  translation problem.
- Reviewer status may still be model-specific. If it is inconclusive, document
  the model failure first. Change the proxy only when current traces prove a
  generalizable transport/format issue and the change has a regression test.
  Reviewer pseudo-tool text is treated as model output, not as an executable
  proxy repair.
- A successful reviewer pass should show assistant `tool_use`, user
  `tool_result`, and reviewer-frame `structured_output` in the isolated
  SQLite database. A clean pass may not create a row in `verification_checks`;
  the reviewer frame's `output_data.structured_output` is the durable evidence.
- Strong app-path proof should show both the foreground frame and reviewer child
  completing. For tool execution, the isolated app database should show matching
  `frame_messages`, `tool_result`, `execution_log`, and artifact rows when
  artifacts were requested.
- If a local execution tool pauses on a permission card, resolving it with
  conversation scope should clear `pending_input_requests` and create a matching
  `execution_log` row. Keep permission evidence local and do not commit it.

## 6.1 Streaming Caveat For Long Tool Calls

`PROXY_STREAM_MODE=buffered` is the default mode for short MTPLX/Qwen tool
loops because Claude Science accepts the final Anthropic SSE shape. However, it
does not emit incremental events while waiting for the upstream response. Long
Qwen generations around one to two minutes can cause Claude Science to
disconnect before the proxy returns the completed response.

`PROXY_STREAM_MODE=direct` now has deterministic proxy tests for OpenAI SSE to
Anthropic SSE conversion, idle heartbeat comments, request ID headers, finite
close, and buffered validation of streamed upstream tool-call argument deltas.
It still does not provide a verified app-side persisted tool loop for
MTPLX/Qwen. It needs more work before it replaces buffered mode. Until then:

- Keep execution probes short and focused.
- Disable verifier for long foreground probes when isolating main-agent
  behavior.
- Avoid running old processing frames concurrently with fresh probes.
- If `session_busy` appears, inspect `_local/proxy.log` for
  `mtplx_background_risk=True`, `mtplx_background_reasons`, and
  `upstream_max_tokens=49`. A risky call still going upstream at `<=48` means the
  guard is not enabled for that proxy process.
- Treat successful direct proxy calls as formatting evidence only unless the
  isolated app database shows persisted `frame_messages`, `execution_log`, and
  artifact rows.
- Treat heartbeat success as transport liveness evidence, not as proof that
  Qwen can complete long app-side execution/reviewer workflows in direct mode.

## 7. Record Evidence

Capture:

- Port status from `./scripts/status.sh`.
- Last 80 lines of `_local/proxy.log`.
- The UI response text.
- Any UI model metadata warnings.
- Frame status and short output preview from the isolated
  `_local/data/.../operon-cli.db` database.

Do not publish `_local/`, app bundles, account state, logs with secrets, or task
data.
