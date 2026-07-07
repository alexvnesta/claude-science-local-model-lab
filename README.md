# Claude Science Local Model Lab

Experimental, unaffiliated lab for running a user-supplied Claude Science app
copy against a local or OpenAI-compatible model through an Anthropic-compatible
proxy.

This repo contains the proxy, profiles, tests, and docs. It does not include
Claude Science, Anthropic proprietary files, account state, app data, logs,
prompts, tool outputs, or artifacts.

## TL;DR

Traditional Claude Code proxies mostly translate one chat/tool loop from an
Anthropic-shaped client to another provider. Claude Science is different: in
observed runs it sends separate foreground-agent, hidden-tool, tool-agent, and
reviewer/harness requests. This proxy preserves those request kinds, keeps
structural reviewer tools such as `submit_output` explicit, validates returned
tool calls against the forwarded client-tool schemas Claude Science offered,
and runs against a copied local app so the official Claude Science install
stays untouched.

If you only want the architecture distinction, read
[`docs/why-this-proxy.md`](docs/why-this-proxy.md).

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

- Brokers foreground, hidden-tool, tool-agent, and reviewer/harness requests.
- Keeps structural reviewer tools such as `submit_output` explicit without
  adding reviewer-only rescue policy.
- Translates Anthropic tool blocks to OpenAI-compatible tool messages and
  translates OpenAI tool calls back.
- Validates returned tool calls against the effective forwarded client-tool
  schemas for that request.
- Supports local/provider profiles, model-picker labels, redacted observability,
  and regression tests.

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

Prerequisites:

- macOS with official Claude Science beta access and the app installed.
- Python 3.10+ and `curl`.
- One OpenAI-compatible upstream backend with `GET /v1/models` and
  `POST /v1/chat/completions`. OpenRouter is the simplest hosted example;
  MTPLX/Qwen, Ollama, vLLM, LM Studio, and llama.cpp are covered in
  [`docs/providers.md`](docs/providers.md).

Copy your installed Claude Science app into the ignored lab area:

```bash
mkdir -p _local
cp -R "/Applications/Claude Science.app" "_local/Claude Science.app"
```

Install test dependencies:

```bash
python3 -m pip install -r requirements-dev.txt
```

Start a hosted OpenRouter example:

```bash
OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=provider/model-slug \
PROXY_PROFILE=profiles/openrouter.env.example \
./scripts/start-proxy-detached.sh
```

Use a paid/private-capacity route for full Claude Science UI demos when
possible. Free OpenRouter routes are useful for smoke tests but can fail large
Claude Science foreground prompts with upstream capacity errors.

Or point at any OpenAI-compatible backend:

```bash
cp profiles/openai-compatible.env.example profiles/local.env
# edit profiles/local.env for your base URL, model, and key
PROXY_PROFILE=profiles/local.env ./scripts/start-proxy-detached.sh
```

Smoke test the proxy after it starts:

```bash
PROXY_PROFILE=<the same profile you started> ./scripts/doctor.sh
./scripts/smoke-proxy.sh
./scripts/test-streaming-proxy.sh
```

`/healthz` is intentionally safe to share in bug reports. It includes provider
identity, stream mode, request-kind counters, provider latency summaries, retry
counts, and tool-filter reason counts, but not prompts, tool arguments, tool
results, account state, or artifacts.

Expected first-run signals are listed in
[`docs/verification-checklist.md`](docs/verification-checklist.md).

Provider-only smoke tests are available without launching Claude Science:

```bash
OPENROUTER_ENV_FILE=/path/to/ignored/.env ./scripts/smoke-openrouter.sh
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

For MTPLX/Qwen, Ollama, and other provider-specific notes, see
[`docs/providers.md`](docs/providers.md).

## Current Proxy Evidence

The gateway path is intended for an isolated Claude Science app copy and
OpenAI-compatible backends such as MTPLX/Qwen or OpenRouter. Current
deterministic proxy evidence covers provider smoke tests, request-kind routing,
schema validation, explicit allowlists, reviewer `submit_output` handling, and
local/provider model-picker labels. Treat model scientific performance as
separate eval evidence, not as a proxy claim.

For detailed transport checks, caveats, and expected live-run signals, see
[`docs/verification-checklist.md`](docs/verification-checklist.md).

## Repo Map

- `proxy/`: dependency-light Anthropic Messages to OpenAI-compatible proxy.
  `observability.py` and `request_shape.py` are the first extracted modules;
  the conversion/server code is still being split out incrementally.
- `profiles/`: provider/backend profiles.
- `scripts/`: launch, status, smoke-test, and app verification helpers.
- `tests/`: regression tests for streaming, tool filtering, and adapters.
- `docs/`: start with the [`docs/README.md`](docs/README.md) index for setup,
  architecture, evidence, verification, roadmap, and archived lab notes.
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
