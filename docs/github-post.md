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

## Setup

- Official Claude Science remained untouched on `127.0.0.1:8765`.
- Copied Claude Science app ran on `127.0.0.1:18765`.
- Local proxy ran on `127.0.0.1:18080`.
- MTPLX exposed an OpenAI-compatible endpoint at `127.0.0.1:8030/v1`.
- The first proof used `mtplx-qwen36-27b-optimized-quality`.

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

## What Is Rough

- Streaming is buffered. The proxy waits for the local backend to finish, then
  emits Anthropic SSE events.
- Tool calls need more stress testing. The basic format translation exists, but
  full scientific-agent workflows will expose more edge cases.
- Local model latency matters. Tiny prompts worked; longer Claude Science loops
  need careful model and token-cap tuning.
- Local backends may serialize concurrent requests. MTPLX can return
  `session_busy` when Claude Science sends foreground and background-review
  calls at the same time, so the proxy includes configurable retries.
- UI metadata may still show a Claude alias as unavailable even when the request
  path is local.

## How to Try Another Model

Create a profile:

```bash
cp profiles/openai-compatible.env.example profiles/local.env
```

Edit:

```bash
MTPLX_OPENAI_BASE_URL=http://127.0.0.1:11434/v1
MTPLX_OPENAI_MODEL=gemma-or-qwen-or-your-model
PROXY_ADVERTISED_MODELS=claude-opus-4-8,gemma-or-qwen-or-your-model
PROXY_MAX_TOKENS_CAP=4096
```

Then run:

```bash
PROXY_PROFILE=profiles/local.env ./scripts/start-proxy-detached.sh
./scripts/smoke-proxy.sh
./scripts/launch-claude-science-local.sh
```

## Safety Notes

Do not commit the copied app bundle, Claude Science data directory, account
state, task outputs, logs with secrets, or local PID files. This repo keeps all
of that under `_local/`, which is gitignored.
