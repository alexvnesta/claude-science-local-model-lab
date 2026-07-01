# Draft GitHub Post

## Title

Running Claude Science Against a Local Model: First Working Proxy Proof

## Summary

We tested whether Claude Science can be run against a local model server by
launching a copied, isolated Claude Science app with Anthropic-style gateway
environment variables and routing its model calls through a local proxy.

Result: yes. The isolated Claude Science copy made real `/v1/messages` requests
to our local proxy, the proxy translated those requests to an OpenAI-compatible
MTPLX/Qwen backend, and Claude Science rendered the local model response in the
UI.

## Access Caveat

This is not a Claude Science access bypass. Anthropic's docs currently describe
Claude Science as beta software: Pro and Max have access on by default; Team
and Enterprise organizations need an Owner or Primary Owner to enable Claude
Science in Organization settings; Free users do not have access; and entitled
users download the app and sign in with their `claude.ai` account.

So the real setup friction starts before the proxy: you need official beta
access, the installed app, and an initial Claude account login. This repo keeps
that boundary intact and does not redistribute the app or account state.

## Setup

- Official Claude Science remained untouched on `127.0.0.1:8765`.
- Copied Claude Science app ran on `127.0.0.1:18765`.
- Local proxy ran on `127.0.0.1:18080`.
- MTPLX exposed an OpenAI-compatible endpoint at `127.0.0.1:8030/v1`.
- The first proof used `mtplx-qwen36-27b-optimized-quality`.
- Portable profiles are included for Ollama and OpenRouter, plus a generic
  OpenAI-compatible profile for vLLM, LM Studio, llama.cpp server, and similar
  backends.

## Why a Proxy

Claude Science speaks an Anthropic Messages-style API. Most local model servers
expose OpenAI-compatible chat completions. The proxy does the translation:

- Anthropic messages to OpenAI chat messages.
- Anthropic tools to OpenAI function tools.
- OpenAI chat responses back to Anthropic message blocks.
- Claude Science's large `max_tokens` requests to a configurable local cap.

## What Worked

- Claude Science called `GET /v1/models?limit=1000` on the local proxy.
- Onboarding task generation called `POST /v1/messages` through the proxy.
- A live UI prompt asking for exactly `LOCAL MODEL OK` was answered by the local
  model and rendered in Claude Science.
- Bounded biomedical-analysis prompts completed in the UI through the local
  MTPLX/Qwen path.
- The proxy test suite covers Anthropic SSE output, OpenAI streaming text,
  OpenAI streaming tool-call deltas, full-JSON fallback, socket close after
  `message_stop`, and observed Qwen text-tool-call formats.
- Claude Science foreground and reviewer frames are separate app requests. The
  proxy now logs request kind (`harness`, `tool_agent`, `tools_hidden`, or
  `plain`) and treats structural reviewer tools like `submit_output` separately
  from ordinary science/execution tools.
- In an isolated execution-tool probe, Qwen 27B emitted schema-valid `python`
  and `save_artifacts` calls when only those tools were exposed. That is a tool
  formatting proof; full app-side execution still needs persisted
  `tool_result` and artifact evidence.
- A fresh authenticated app-API probe completed the full foreground/reviewer
  loop: foreground `search_skills` tool use and tool result, then reviewer
  `submit_output` tool use and success result. This is the strongest current
  evidence that the broker can keep main-agent and reviewer traffic distinct.

## What Is Rough

- Streaming is configurable. The proxy can bridge true OpenAI SSE into
  Anthropic SSE, but MTPLX/Qwen direct streaming hung during live testing, so the
  MTPLX profiles currently use buffered mode.
- Tool calls still need live workflow stress testing, but the proxy now forwards
  tools through a validation boundary: unknown tools, malformed JSON args, and
  schema-invalid inputs are filtered before Anthropic `tool_use` is emitted.
  The Qwen analysis profile can also repair observed reviewer pseudo-tool-call
  formats when explicitly enabled.
- Do not use one universal allowlist for every request shape. Reviewer/harness
  calls need `submit_output`, while foreground science-agent calls may need a
  much smaller tool subset than the full Claude Science inventory.
- Local model latency matters. Tiny prompts worked; longer Claude Science loops
  need careful model and token-cap tuning.
- Local backends may serialize concurrent requests. MTPLX can return
  `session_busy` when Claude Science sends foreground and background-review
  calls at the same time, so the proxy includes configurable retries.
- The model picker needs a Claude-shaped compatibility ID plus a human display
  name. Claude Science filters non-`claude-` IDs and slug-like display names
  from `/api/models`, so set `PROXY_MODEL_DISPLAY_NAMES` for local backends.

## How to Try Another Model

Use a provider profile:

```bash
cp profiles/openai-compatible.env.example profiles/local.env
```

Edit:

```bash
UPSTREAM_OPENAI_BASE_URL=http://127.0.0.1:11434/v1
UPSTREAM_OPENAI_MODEL=gemma-or-qwen-or-your-model
UPSTREAM_API_KEY=local-placeholder
PROXY_ADVERTISED_MODELS=claude-opus-4-8,gemma-or-qwen-or-your-model
PROXY_MODEL_DISPLAY_NAMES='{"claude-opus-4-8":"Gemma Local"}'
PROXY_MAX_TOKENS_CAP=4096
PROXY_STREAM_MODE=direct
PROXY_TOOL_MODE=pass
PROXY_TOOL_ALLOWLIST=
PROXY_TOOL_VALIDATION=schema
PROXY_TOOL_REPAIR=metadata
PROXY_HARNESS_TOOLS=submit_output
PROXY_PARSE_TEXT_TOOL_CALLS=0
# Optional diagnostics only:
# PROXY_SCHEMA_LOG_PATH=_local/tool-schema-capture.jsonl
```

For Ollama:

```bash
OLLAMA_MODEL=qwen3:8b \
PROXY_PROFILE=profiles/ollama.env.example \
./scripts/start-proxy-detached.sh
```

For OpenRouter:

```bash
OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=provider/model-slug \
PROXY_PROFILE=profiles/openrouter.env.example \
./scripts/start-proxy-detached.sh
```

For local Qwen-style models, start with the focused probe profile:

```bash
PROXY_PROFILE=profiles/mtplx-qwen-tool-probe.env.example ./scripts/start-proxy-detached.sh
```

For execution-tool probes after that:

```bash
PROXY_PROFILE=profiles/mtplx-qwen-execution-probe.env.example ./scripts/start-proxy-detached.sh
```

Then run:

```bash
PROXY_PROFILE=profiles/local.env ./scripts/start-proxy-detached.sh
./scripts/smoke-proxy.sh
./scripts/test-streaming-proxy.sh
./scripts/launch-claude-science-local.sh
scripts/submit-local-request.py --project-id <project-id> "For this gateway test, reply with exactly LOCAL MODEL OK. Do not use tools."
```

## Safety Notes

Do not commit the copied app bundle, Claude Science data directory, account
state, task outputs, logs with secrets, or local PID files. This repo keeps all
of that under `_local/`, which is gitignored.
