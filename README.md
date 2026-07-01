# Claude Science Local Model Lab

Experimental, unaffiliated lab for running a user-supplied Claude Science app
copy against a local or OpenAI-compatible model through an Anthropic-compatible
proxy.

This repo contains the proxy, profiles, tests, and docs. It does not include
Claude Science, Anthropic proprietary files, account state, app data, logs,
prompts, tool outputs, or artifacts.

## What This Is

- A small proxy from Claude Science's Anthropic-style `/v1/messages` traffic to
  OpenAI-compatible `/v1/chat/completions` backends.
- A repeatable local launch path that keeps the official Claude Science app on
  its normal port and runs an isolated copied app under `_local/`.
- A set of profiles for MTPLX/Qwen, Ollama, OpenRouter, and generic
  OpenAI-compatible servers.

## Why It Fits Claude Science

Most public proxies target Claude Code-style chat. This one is narrower: it
adapts the request shapes Claude Science actually emits.

- Implements the Claude Science surface we observed: `/v1/models`,
  `/v1/models/{id}`, `/v1/messages`, and `/v1/messages/count_tokens`.
- Brokers foreground, hidden-tool, tool-agent, and reviewer/harness requests
  instead of treating every call as one chat loop.
- Handles reviewer tools such as `submit_output` separately from user tools
  such as `python`, `bash`, and `search_skills`.
- Translates Anthropic `tool_use`/`tool_result` blocks to OpenAI-compatible
  tool messages and translates OpenAI `tool_calls` back.
- Repairs narrow local-model pseudo-tool-call text patterns observed from Qwen
  reviewer traffic.
- Validates returned tool calls against the exact schema Claude Science offered
  on that request before emitting executable `tool_use`.
- Advertises Claude-shaped model aliases with human display names so the app
  can show a local model in its picker.

For the longer comparison with Claude Code proxies, see
[`docs/why-this-proxy.md`](docs/why-this-proxy.md).

## Access And Boundaries

Using Claude Science as the client still requires official Claude Science beta
access and sign-in. The proxy does not bypass Claude Science entitlement or
login. Using the proxy by itself does not require an Anthropic account.

The lab keeps local state separate by default:

- Official Claude Science: `127.0.0.1:8765`, data under `~/.claude-science`.
- Isolated lab copy: `127.0.0.1:18765`, data under `_local/data`.
- Proxy: `127.0.0.1:18080`.
- `_local/` is gitignored and should contain app copies, cookies, logs,
  diagnostics, databases, and artifacts.

See [`docs/access.md`](docs/access.md) and
[`docs/architecture.md`](docs/architecture.md).

## Quick Start

Copy your installed Claude Science app into the ignored lab area:

```bash
mkdir -p _local
cp -R "/Applications/Claude Science.app" "_local/Claude Science.app"
```

Start a proxy profile:

```bash
PROXY_PROFILE=profiles/mtplx-qwen.env.example ./scripts/start-proxy-detached.sh
```

Or use another OpenAI-compatible provider:

```bash
OLLAMA_MODEL=qwen3:8b \
PROXY_PROFILE=profiles/ollama.env.example \
./scripts/start-proxy-detached.sh

OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=provider/model-slug \
PROXY_PROFILE=profiles/openrouter.env.example \
./scripts/start-proxy-detached.sh
```

Smoke test the proxy:

```bash
PROXY_PROFILE=profiles/mtplx-qwen.env.example ./scripts/doctor.sh
./scripts/smoke-proxy.sh
./scripts/test-streaming-proxy.sh
```

Provider-only smoke tests are available without launching Claude Science:

```bash
OPENROUTER_ENV_FILE=/path/to/ignored/.env ./scripts/smoke-openrouter.sh
OLLAMA_MODEL=qwen3:8b ./scripts/smoke-ollama.sh
```

Launch the isolated Claude Science copy:

```bash
./scripts/launch-claude-science-local.sh
./scripts/local-url.sh
```

Open the printed URL and ask for a deterministic reply:

```text
For this gateway test, reply with exactly LOCAL MODEL OK. Do not use tools.
```

If routing is local, `_local/proxy.log` will show `POST /v1/messages`.

MTPLX note: the Qwen profiles enable `PROXY_MTPLX_AVOID_BACKGROUND_BYPASS=1`.
This raises small Claude Science helper/reviewer calls above MTPLX's 48-token
background cutoff when their request shape would otherwise return an immediate
`session_busy` during foreground generation. The proxy log records
`mtplx_background_risk`, reasons, roles, and the adjusted upstream token count.

## Current Proof

The gateway path works with an isolated Claude Science app copy and an
MTPLX/Qwen backend. Verified paths include deterministic UI replies, short
analysis prompts, focused tool loops, reviewer `submit_output`, `python` plus
`save_artifacts` probes, and local model-picker labels.

The newer `2bc1ac85` Claude Science client was also tested in a temp copy. It
still honored `ANTHROPIC_BASE_URL` and called the proxy through `/v1/models` and
`/v1/messages`.

Known caveats: long buffered generations can starve the app of SSE events;
direct streaming needs more app-side proof; local models vary a lot in tool-call
quality.

For detailed checks and evidence, see
[`docs/verification-checklist.md`](docs/verification-checklist.md) and
[`docs/roadmap.md`](docs/roadmap.md).

## Repo Map

- `proxy/`: dependency-light Anthropic Messages to OpenAI-compatible proxy.
- `profiles/`: provider and experiment profiles.
- `scripts/`: launch, status, smoke-test, and app verification helpers.
- `tests/`: regression tests for streaming, tool filtering, and adapters.
- `docs/`: access notes, provider setup, architecture, verification, roadmap,
  comparison, and prior-art review.
- `AGENTS.md`: orientation for humans or agents cloning the repo.
- `_local/`: ignored local-only runtime area.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests
./scripts/test-streaming-proxy.sh
```

Credit and license notes are in [`NOTICE.md`](NOTICE.md) and
[`docs/prior-art-review.md`](docs/prior-art-review.md).
