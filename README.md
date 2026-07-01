# Claude Science Local Model Lab

Experimental, unaffiliated lab for running a user-supplied Claude Science app
copy against a local OpenAI-compatible model server through an
Anthropic-compatible proxy.

This repository contains only lab code, profiles, tests, and documentation. It
does not include Claude Science itself, Anthropic proprietary files, account
state, local runtime data, logs, prompts, tool outputs, or artifacts.

The first working proof used MTPLX/Qwen, but the proxy is intentionally model
agnostic: MTPLX, Ollama, LM Studio, vLLM, llama.cpp server, or any similar
OpenAI-compatible `/v1/chat/completions` endpoint can be configured with a
profile file.

## Safety Boundary

This repo does not track the Claude Science app bundle, Claude account state,
task data, logs, or proxy PID files. Those live under `_local/`, which is
gitignored.

You must provide your own installed Claude Science application. The scripts
expect a local copy under `_local/Claude Science.app`, but that path is ignored
and should never be committed or redistributed.

The default launch script uses a separate Claude Science instance:

- Official app stays on `http://127.0.0.1:8765`.
- Local-model app copy runs on `http://127.0.0.1:18765`.
- Proxy listens on `http://127.0.0.1:18080`.
- Sandbox port is `18766`.

The macOS app bundle is mostly a launcher. The running official daemon normally
comes from `~/.claude-science/bin/claude-science`, while the isolated lab copy
uses `_local/Claude Science.app/Contents/Resources/bin/claude-science`. When
checking client updates, verify the managed binary and the copied app binary,
not just `/Applications/Claude Science.app/Contents/Info.plist`.

## Quick Start

Copy the installed app into the ignored lab directory:

```bash
mkdir -p _local
cp -R "/Applications/Claude Science.app" "_local/Claude Science.app"
```

Start the proxy in the background with the MTPLX/Qwen profile:

```bash
PROXY_PROFILE=profiles/mtplx-qwen.env.example ./scripts/start-proxy-detached.sh
```

For direct-analysis experiments inside Claude Science, use the Qwen analysis
profile. It drops Claude Science tool schemas before MTPLX and enables the
Qwen text-tool-call adapter used by the reviewer loop. In this mode, Claude
Science can get direct prose analysis from the local model, but it cannot
actually browse, run code, read files, or create artifacts through those hidden
tools:

```bash
PROXY_PROFILE=profiles/mtplx-qwen-analysis.env.example ./scripts/start-proxy-detached.sh
```

Smoke test the proxy:

```bash
./scripts/smoke-proxy.sh
./scripts/test-streaming-proxy.sh
```

Launch the isolated Claude Science copy:

```bash
./scripts/launch-claude-science-local.sh
```

Get the local app URL:

```bash
./scripts/local-url.sh
```

Then open the returned URL and ask for a deterministic response, for example:

```text
For this gateway test, reply with exactly LOCAL MODEL OK. Do not use tools.
```

If the proxy is being used, `_local/proxy.log` will show `POST /v1/messages`
requests from Claude Science and the UI will render the local model response.

For repeatable app-path probes without browser automation, use the local API
helper:

```bash
scripts/submit-local-request.py \
  --project-id <project-id> \
  "API path probe. Use search_skills once to search for figure-composer. After the tool result, answer with marker API_KIND_SEARCH_OK."
```

It uses the official `claude-science url` command for a short-lived login cookie
and prints the accepted frame id.

## Repository Layout

- `proxy/`: dependency-free Anthropic Messages to OpenAI-compatible proxy.
- `profiles/`: example profiles for MTPLX/Qwen and generic local backends.
- `scripts/`: launch, status, smoke-test, and local app verification helpers.
- `tests/`: regression tests for streaming, tool-call filtering, and adapters.
- `docs/`: architecture notes, verification checklist, and prior-art review.
- `_local/`: ignored local-only app/runtime/log/cookie/artifact area.

## Prior Art And Credit

Before publishing this lab, we reviewed the main public Claude Code proxy and
token-proxy projects named in the search overview and in our initial notes.
See `NOTICE.md` and `docs/prior-art-review.md` for links, licenses, reviewed
commits, and how this Claude Science-specific adapter differs.

## Model Profiles

Profiles are shell env files loaded before the proxy starts. The important
settings are:

- `MTPLX_OPENAI_BASE_URL`: upstream OpenAI-compatible base URL.
- `MTPLX_OPENAI_MODEL`: upstream model ID to send to `/v1/chat/completions`.
- `PROXY_ADVERTISED_MODELS`: model IDs exposed to Claude Science through
  `/v1/models`.
- `PROXY_MAX_TOKENS_CAP`: local cap applied to Claude Science's very large
  `max_tokens` requests.
- `PROXY_UPSTREAM_RETRIES` and `PROXY_UPSTREAM_RETRY_DELAY`: retries for
  transient local-backend load, including MTPLX `session_busy` responses.
- `PROXY_STREAM_MODE`: `direct` bridges upstream OpenAI SSE into Anthropic SSE;
  `buffered` waits for the full upstream response, then emits a finite
  Anthropic SSE response.
- `PROXY_TOOL_MODE`: `pass` forwards tool schemas, `drop` removes them before
  the local model.
- `PROXY_TOOL_ALLOWLIST`: optional comma-separated tool names to forward in
  `pass` mode. This keeps local models focused on a small task-relevant tool
  set while preserving schema validation.
- `PROXY_HARNESS_TOOLS`: structural Claude Science tools that bypass the normal
  agent allowlist. Defaults to `submit_output`, which reviewer frames use to
  return structured results. These are not user execution tools like `bash` or
  `python`.
- `PROXY_TOOL_VALIDATION`: `schema` validates returned tool calls against the
  tools Claude Science offered before emitting Anthropic `tool_use` blocks.
  `name` only checks the function name; `off` is for debugging.
- `PROXY_TOOL_REPAIR`: `metadata` fills safe missing Claude Science metadata
  fields such as `human_description` before schema validation. Semantic fields
  such as `command`, `code`, `environment`, and `file_path` are not repaired.
- `PROXY_FORCE_MENTIONED_TOOL`: when enabled, explicit prompts like "use the
  skill tool" are converted into a named upstream `tool_choice`. This is useful
  for Qwen, which can otherwise describe a requested tool action without
  actually calling the tool.
- `PROXY_PARSE_TEXT_TOOL_CALLS`: converts narrow Qwen-style textual tool-call
  forms back into Anthropic `tool_use` blocks.
- `PROXY_SCHEMA_LOG_PATH`: optional JSONL path for redacted offered-tool schema
  inventories. It records tool names, schema digests, required keys, and
  property names/types, not prompts or full tool descriptions.

The MTPLX proof profile is in `profiles/mtplx-qwen.env.example`. A generic
profile for Ollama/Gemma/vLLM/LM Studio is in
`profiles/openai-compatible.env.example`.

## Current Status

The gateway path works. The isolated Claude Science copy made real
`/v1/messages` calls to the local proxy, the proxy routed them to MTPLX, and
Claude Science rendered local model outputs in the UI, including deterministic
gateway tests and bounded MASLD-HCC analysis prompts.

Client update probe, 2026-06-30: the official updater reported
`2e3e6f91 -> 2bc1ac85`. The visible app install stayed on
`0.1.0-dev.20260630.t160235.sha2e3e6f9` after an
`UPDATE_SMOKE_FAIL: downloaded binary failed to launch - not replacing` event,
so the active official and lab-copy binaries were not half-updated. A safe temp
copy of `~/.claude-science/bin/claude-science` was updated to
`0.1.0-dev.20260630.t212931.sha2bc1ac8` and launched with
`ANTHROPIC_BASE_URL=http://127.0.0.1:18080` against a temp copy of the lab data.
That new binary still honored local routing: the proxy saw
`GET /v1/models?limit=1000`, then `/v1/messages` requests classified as
`tools_hidden` and `tool_agent`. Exact string checks also found
`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `/v1/messages`,
`/v1/messages/count_tokens`, `/v1/models`, and `claude-opus-4-8` in both old
and new binaries. The only obvious model-token delta was that `2bc1ac85` added
`claude-sonnet-5` and dropped the bare `claude-haiku-4-5` alias while retaining
`claude-haiku-4-5-20251001`.

Claude Science creates separate foreground and reviewer frames. The proxy uses
one local model backend for all frames in the current profiles, but it no longer
treats every request as the same agent shape: request logs label `kind=harness`,
`kind=tool_agent`, `kind=tools_hidden`, or `kind=plain`, and harness tools such
as `submit_output` are handled separately from the science-agent allowlist.

Known limitations:

- The proxy supports direct OpenAI-SSE-to-Anthropic-SSE bridging, but the MTPLX
  Qwen endpoint hung in direct streaming during testing. The MTPLX profiles
  therefore use `PROXY_STREAM_MODE=buffered`.
- Buffered SSE responses now close the connection after `message_stop`; this
  fixed app-side idle-watchdog symptoms seen during early UI runs.
- Tool calls are forwarded in `pass` mode, then gated before execution. The
  proxy rejects unknown tools, malformed/non-object arguments, and schema-invalid
  inputs. Observed Qwen reviewer pseudo-tool-call formats can still be repaired
  when `PROXY_PARSE_TEXT_TOOL_CALLS=1`; missing `human_description` metadata can
  be filled by `PROXY_TOOL_REPAIR=metadata`.
- Full 26-tool forwarding can be slow or hang on local Qwen. Use
  `profiles/mtplx-qwen-tool-probe.env.example` for focused live tool-loop
  experiments. That profile completed a real foreground `search_skills`
  tool-use/tool-result loop in the local Claude Science UI.
- For execution-tool experiments, use
  `profiles/mtplx-qwen-execution-probe.env.example`. Direct isolated probes
  showed Qwen 27B can emit schema-valid `python` and `save_artifacts` calls
  when those are the only forwarded science tools and the requested tool is
  forced. App-side execution also requires approving the Claude Science local
  execution permission with conversation scope. In the UI this is
  "Permissions -> Allow -> for this conversation"; scripted checks use
  `scripts/resolve-input-request.py --scope conversation`.
- The strongest verified execution/artifact proof so far is frame
  `b1ff2cd4-dac4-4417-96f1-6cd39c491dbc`: Qwen emitted compat `python` and
  `save_artifacts` tool calls, Claude Science executed Python, saved a PNG and
  text artifact, and the reviewer child completed with empty findings.
- Long figure-producing prompts are still limited by streaming/runtime
  behavior. Buffered mode is the known-good short-loop app path, but long Qwen
  generations can leave Claude Science without SSE events long enough for the
  app to disconnect. Direct streaming needs further compatibility work before
  it is the default live-app path.
- Reviewer frames need `submit_output` even when the foreground agent allowlist
  is narrow. The proxy therefore forwards configured harness tools and forces a
  named upstream `tool_choice` when `submit_output` is the only offered tool.
- The Qwen analysis profile adds an honesty guard when tool schemas are hidden,
  so tool-heavy prompts should return a limitation or draft plan rather than
  fake tool markup such as `<anonymous_function>()`.
- Claude Science asks for large `max_tokens` values, so local profiles should
  keep a sane cap.
- MTPLX can serialize concurrent foreground/background generations. The proxy
  retries transient `session_busy` responses, but serious runs should still keep
  background-review traffic in mind.
- Long follow-up chains grow expensive quickly. Prefer fresh sessions for clean
  verification and benchmark runs.
- Some UI metadata can still say the Claude alias is unavailable even while
  request routing is local.

See `docs/verification-checklist.md` for the exact proof checklist and
`docs/github-post.md` for a publishable write-up draft.

## Development

Run the Python regression suite:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests
```
