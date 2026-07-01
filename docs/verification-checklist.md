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

Client update note from 2026-06-30: the official updater reported
`2e3e6f91 -> 2bc1ac85`, then showed
`UPDATE_SMOKE_FAIL: downloaded binary failed to launch - not replacing`, so the
active official and lab-copy binaries were not half-updated. A safe temp copy of
`~/.claude-science/bin/claude-science` was updated to
`0.1.0-dev.20260630.t212931.sha2bc1ac8` and launched against a temp copy of the
lab data with `ANTHROPIC_BASE_URL=http://127.0.0.1:18080`. That new binary still
called the proxy through `GET /v1/models?limit=1000` and `/v1/messages`; proxy
logs classified the model requests as `tools_hidden` and `tool_agent`.

## 2. Start Proxy

```bash
PROXY_PROFILE=profiles/mtplx-qwen.env.example ./scripts/start-proxy-detached.sh
```

For direct-analysis runs with MTPLX/Qwen, prefer:

```bash
PROXY_PROFILE=profiles/mtplx-qwen-analysis.env.example ./scripts/start-proxy-detached.sh
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
  `stream_heartbeat_seconds`, `tool_allowlist`, `tool_validation`,
  `tool_repair`, `force_mentioned_tool`, `parse_text_tool_calls`, and optional
  `schema_log_path` values.
- `/healthz` shows `harness_tools`, normally `["submit_output"]`.
- If the active profile sets them, `/healthz` also shows
  `harness_tool_allowlist` and `harness_force_submit_after_tool_results`.
- `/healthz.metrics` shows request counts by kind and stream mode, provider
  latency by kind, retry/error counts, and tool-filter reason counts. It should
  not include prompt text, tool arguments, tool results, account state, or
  artifact contents.
- `/v1/messages/count_tokens` returns an `input_tokens` value.
- `/v1/messages` returns a message containing `mtplx proxy ok`.
- `./scripts/test-streaming-proxy.sh` passes streamed text, direct-stream
  heartbeat comments, request ID response headers, buffered validation of
  upstream streamed tool-call deltas, invalid tool-call filtering, full-JSON
  fallback, finite SSE close, redacted health metrics, and Qwen text-tool-call
  adapter cases.

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
  "API path probe. Use search_skills once to search for figure-composer. After the tool result, answer with marker API_KIND_SEARCH_OK."
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

For public screenshots or GIFs, also confirm:

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
failure. See `docs/demo-capture.md`.

## 6. Bounded Analysis Proof

Use a fresh session when possible. Send a short, self-contained scientific
analysis prompt, for example:

```text
No tools, no files, no browsing. Answer directly in 5 bullets, max 350 words.

Analyze this mini MASLD-HCC signal: DKK1 +2.3, SOX4 +1.8, RELB +1.2, KRT19 +2.0, EPCAM +1.5, COL1A1 +1.3, TNFRSF12A +1.1, ALB -1.4, CYP3A4 -1.6. All are adjusted-significant. Caveat: summary table only, no raw counts, cohort metadata, survival, or validation.

Say: (1) likely biology, (2) strongest caveat/stop signal, (3) what Claude Science handles well, (4) what Insight still defensibly owns, (5) one next experiment with pass/fail criteria.
```

Expected:

- The UI renders a substantive answer, not just a gateway echo.
- The frame eventually reaches `completed` in the isolated SQLite database.
- For the Qwen analysis profile, `_local/proxy.log` should show Claude Science
  tool schemas dropped before upstream, e.g. `tools=26 upstream_tools=0`.
- In `PROXY_TOOL_MODE=drop`, tool-heavy prompts should produce an honest
  limitation or draft plan. They should not contain `<anonymous_function>`,
  `<tool_call>`, XML function tags, or claims that searches/files/code/artifacts
  were actually executed.
- In `PROXY_TOOL_MODE=pass` with `PROXY_TOOL_VALIDATION=schema`, tool-heavy
  prompts should forward Claude Science tool schemas upstream, but returned tool
  calls should be emitted only when they use an offered tool name and JSON-object
  arguments that satisfy the offered schema. Unknown tools, malformed JSON args,
  and missing required fields should be filtered rather than wrapped as
  executable `tool_use`.
- With `PROXY_TOOL_REPAIR=metadata`, missing `human_description` may be filled
  for Qwen-generated calls. Missing semantic fields such as `command`, `code`,
  or `file_path` should still be filtered.
- If full-tool forwarding stalls, restart with
  `profiles/mtplx-qwen-tool-probe.env.example` and verify a single allowlisted
  tool loop before broadening the allowlist.
- For execution-tool probes, restart with
  `profiles/mtplx-qwen-execution-probe.env.example` and begin with explicit,
  single-tool prompts for `python` or `save_artifacts`. Direct proxy success
  means Qwen formatted the tool call; app-side success additionally requires a
  persisted Claude Science `tool_result` and, for artifacts, a saved artifact
  version.
- New app-side execution proofs should use the compatibility profile so tool
  ids are normalized to `toolu_...` and emitted tool-use blocks include
  `caller: {"type":"direct"}`. Older pre-compat frames with OpenAI-style
  `call_...` ids can still clear the permission card and run Python, but they
  are poor recovery targets for artifact-loop verification.
- With `PROXY_FORCE_MENTIONED_TOOL=1`, explicit user text such as "use the
  skill tool" or "call python to create..." should show a named upstream
  `tool_choice` in direct probes and a real `tool_use` in the persisted Claude
  Science frame. If multiple tools are mentioned, the proxy chooses the earliest
  explicit tool mention, not the longest tool name.
- Reviewer/harness calls should log `kind=harness`, forward `submit_output`
  even if it is absent from `PROXY_TOOL_ALLOWLIST`, and force a named upstream
  `tool_choice` when `submit_output` is the only forwarded tool. After a
  completed `submit_output` tool result is present in the conversation, the
  proxy should log `not forcing completed harness tool_choice 'submit_output'`
  and allow the reviewer follow-up to end normally instead of looping.
- Reviewer/harness calls may need their own tool set. For Qwen execution
  probes, `/healthz` should show
  `harness_tool_allowlist: ["repl","read_file","boundary","summary_query","query_target_history","submit_output"]`.
  In reviewer logs, `kind=harness` with `upstream_tools=6` means the reviewer
  can inspect artifacts instead of being forced to submit blindly.
- For local models that keep inspecting, `/healthz` may show
  `harness_force_submit_after_tool_results`. When this is nonzero and a
  reviewer has already completed that many non-harness tool results, the proxy
  should log `forcing harness closeout 'submit_output'` and forward only the
  harness submit tool on that turn.
- When `PROXY_SCHEMA_LOG_PATH` is set, `_local/tool-schema-capture.jsonl` should
  receive one redacted inventory per tool-offering request. Keep this file out
  of git and use it to tune provider-specific tool adapters.
- Python tool calls should be inline executable code, not filenames or
  generated artifact paths. The proxy filters observed malformed local-model
  shapes such as `code: "openrouter_free_probe.py"` and giant single-line
  import blobs while preserving normal multi-line analysis scripts. It also
  filters Claude Science app-tool invocations smuggled inside Python source,
  such as `skill({"skill": "figure-style"})`.
- Reviewer status may still be model-specific. If it is inconclusive, inspect
  the reviewer message shape and add a narrow adapter plus a regression test.
  Observed Qwen reviewer shapes include markdown-wrapped function text, fenced
  reviewer JSON, fenced OpenAI-style function JSON, XML-ish function blocks,
  and `::tool::+json::...`.
- A successful reviewer-adapter pass should show assistant `tool_use`, user
  `tool_result`, and reviewer-frame `structured_output` in the isolated
  SQLite database. A clean pass may not create a row in `verification_checks`;
  the reviewer frame's `output_data.structured_output` is the durable evidence.
- Strong app-path proof should show both the foreground frame and reviewer child
  completing. Example known-good frame:
  `a160c85e-4258-40cc-9196-dd43a9e9d565` called `search_skills`, received a
  real `tool_result`, answered `API_KIND_SEARCH_OK`, and reviewer child
  `33efd0d8-5f9b-4ae0-810b-4db8dd5b96cf` called `submit_output` successfully.
- Known-good execution/artifact frame:
  `b1ff2cd4-dac4-4417-96f1-6cd39c491dbc` emitted compat `python` and
  `save_artifacts` tool uses, Python wrote `qwen_probe_compat.png` and
  `qwen_probe_compat.txt`, Claude Science saved both as artifacts, and reviewer
  child `831a0f6c-d2ed-4438-94cd-6ed6f3c8f5bf` completed with
  `structured_output: {"findings":[]}`.
- Permission-scope proof:
  `6b100da8-0737-4232-b106-c15b347273cb` originally paused with a local
  `python` permission card. Resolving it with `scope: "conversation"` cleared
  `pending_input_requests` and created an `execution_log` row writing
  `qwen_probe.png` and `qwen_probe.txt`.
- OpenRouter/Gemma proof:
  `d18147f0-825d-4930-857b-55406366cb09` ran against
  `google/gemma-4-31b-it:free` through `profiles/openrouter.env.example` with
  `PROXY_STREAM_MODE=direct`, `PROXY_TOOL_MODE=pass`,
  `PROXY_TOOL_ALLOWLIST=python,save_artifacts`, forced mentioned tools, and
  Claude Science compatibility enabled. The frame required one Python retry
  after `pandas.to_markdown()` failed without `tabulate`, then saved
  `gemma_clean_scores.tsv`, `gemma_clean_analysis.md`, and
  `gemma_clean_figure.png`. Saved artifact versions were
  `84137fc9-e320-43f5-b89e-0da5e29a67fc` (TSV),
  `09db178b-a54c-409d-ae99-4f21dc2f31c7` (Markdown), and
  `3ba6322e-e2b9-494a-a9bd-1e37b923c21b` (PNG). The reviewer first caught a
  hallucinated artifact-version reference, then reviewer child
  `b58aa2ca-fac0-4aa1-a94e-8be876ee13a7` completed with `findings: []` and a
  resolved prior disposition after correction. Proxy logs showed
  `not forcing completed harness tool_choice 'submit_output'` on reviewer
  follow-ups. Caveat: OpenRouter intermittently returned upstream 429s for the
  free Gemma endpoint, and the generated mechanism text in the PNG was clipped;
  this proves the loop, not publication-quality figure layout.
- Local Qwen refined artifact proof:
  `55f1c397-47ea-4d9a-adda-48cf357fc4c4` ran against
  `mtplx-qwen36-27b-optimized-quality` through
  `profiles/mtplx-qwen-execution-probe.env.example`. The foreground frame
  produced `QWEN_REFINED_DONE` and saved all requested artifacts:
  `f2193067-2ac6-4497-a51b-1beeea0540fd` (`qwen_refined_scores.tsv`,
  checksum `ce0867bc037b7bc3caba31688c890317860bc1a2cc64249de7182a9a7590fa57`),
  `3464db49-f767-4692-9fee-46ebac3f8452` (`qwen_refined_analysis.md`,
  checksum `d996e7ffed2f97a1426dde8b48cd0cb1b32123eddf7ab8d73dbbcd2f2ab363a8`),
  and `6032a393-888d-405d-9b9a-b3868a0dcb62` (`qwen_refined_figure.png`,
  checksum `82c8971f45f6b6029cb4655e2b94ec108c019ad9aeb6b86ae95581c78a5dfe6c`).
  The run avoided the earlier `skill()`-inside-Python failure and used real
  `python` plus `save_artifacts` calls. Caveats: Qwen split the work across
  several tool turns despite being asked for one Python call; the PNG was
  readable but Panel B was a component breakdown, not the requested simple
  mechanism schematic; and the reviewer child
  `15ee6b53-3a23-4521-9228-8b06187d5da7` used real `repl`/`read_file`
  inspection tools but remained slow and loop-prone before the closeout guard
  was added.

## 6.1 Streaming Caveat For Long Tool Calls

`PROXY_STREAM_MODE=buffered` is the known-good mode for short MTPLX/Qwen tool
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
- Disable verifier for long foreground experiments when isolating main-agent
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
