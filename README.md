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
reviewer/harness requests. This proxy preserves those request shapes, forwards
the tool surface Claude Science offered for the current request, validates
returned tool calls against the exact schemas Claude Science offered, and runs
against a copied local app so the official Claude Science install stays
untouched.

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
- Forwards the tools Claude Science offered on the current request instead of
  inventing proxy-side task profiles.
- Omits unsupported Anthropic server-side tools such as dated `web_fetch` by
  default. Dated `web_search` can be enabled as proxy-owned Tavily or Firecrawl
  search for local Chat Completions backends, or mapped natively by a future
  Responses provider.
- Translates Anthropic tool blocks to OpenAI-compatible tool messages and
  translates OpenAI tool calls back.
- Validates returned tool calls against the exact schemas Claude Science
  offered on that request.
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
counts, tool-filter reason counts, and redacted debug-capture enablement, but
not prompts, full local paths, tool arguments, tool results, account state, or
artifacts. For prompt size investigations, enable
`PROXY_REQUEST_SHAPE_LOG_PATH` to write redacted request-size breakdowns under
`_local/`, including per-tool description, schema, and full definition JSON
character counts. The default pass mode preserves active tool definitions
exactly; prompt reduction should come from changing which tools Claude Science
offers, not by silently trimming the tools still sent upstream. Keep
`PROXY_RAW_REQUEST_CAPTURE_DIR` off unless you explicitly need private raw
request bodies for local debugging.

Expected first-run signals are listed in
[`docs/verification-checklist.md`](docs/verification-checklist.md).

Provider-only smoke tests are available without launching Claude Science:

```bash
OPENROUTER_ENV_FILE=/path/to/ignored/.env ./scripts/smoke-openrouter.sh
```

To let Chat Completions backends use Claude Science's hosted `web_search`
server tool, opt in to a proxy-owned search bridge and keep secrets in ignored
local env files:

```bash
cat > _local/proxy.env <<'EOF'
FIRECRAWL_API_KEY=...
PROXY_SERVER_WEB_SEARCH=firecrawl
PROXY_SERVER_WEB_SEARCH_MAX_USES=3
PROXY_SERVER_WEB_SEARCH_CONVERSATION_MAX_USES=3
EOF
```

Set `PROXY_SERVER_WEB_SEARCH_CONVERSATION_MAX_USES=0` only for manual debugging
where repeated search loops are intentional.

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

## Current Proof

The gateway path works with an isolated Claude Science app copy and MTPLX/Qwen
or OpenRouter backends. Verified paths include deterministic UI replies, short
analysis prompts, focused tool loops, reviewer `submit_output`, `python` plus
`save_artifacts` probes, OpenRouter/Gemma artifact runs, local Qwen artifact
runs, reviewer inspection-tool routing, and local/provider model-picker labels.

For a public-safe evidence summary, see
[`docs/evidence-bundle.md`](docs/evidence-bundle.md).

Primary Qwen/MTPLX workflow GIF:

![Claude Science running a TP53 TCGA-BRCA analysis through local MTPLX Qwen 27B](docs/assets/qwen-mtplx-tp53-workflow-demo.gif)

The GIF shows the isolated app using the `MTPLX Qwen 27B Local` model label,
conversation-scoped Python permission, a reviewer finding, corrective artifact
creation, a final reviewer pass, and the generated TP53 TCGA-BRCA plot opened
in split view.

Public source notebook for the TP53 analysis:
[`examples/tp53_brca_xena_analysis.ipynb`](examples/tp53_brca_xena_analysis.ipynb).
The demo uses the public UCSC Xena TCGA-BRCA `HiSeqV2` expression matrix:
[`TCGA.BRCA.sampleMap/HiSeqV2.gz`](https://tcga.xenahubs.net/download/TCGA.BRCA.sampleMap/HiSeqV2.gz).

<img src="docs/assets/tp53-notebook-source-1.png" alt="Notebook source for loading TCGA-BRCA TP53 expression data" width="900">

<img src="docs/assets/tp53-notebook-source-2.png" alt="Notebook source for plotting TP53 expression and writing artifacts" width="900">

For detailed evidence, caveats, and capture notes, see
[`docs/evidence-bundle.md`](docs/evidence-bundle.md),
[`docs/demo-capture.md`](docs/demo-capture.md), and
[`docs/verification-checklist.md`](docs/verification-checklist.md).

## Repo Map

- `proxy/`: dependency-light Anthropic Messages to OpenAI-compatible proxy.
  `observability.py` and `request_shape.py` are the first extracted modules;
  the conversion/server code is still being split out incrementally.
- `profiles/`: provider/backend profiles.
- `scripts/`: launch, status, smoke-test, and app verification helpers.
  `scripts/report-prefix-cache.py` summarizes ignored request-shape JSONL logs
  when `PROXY_REQUEST_SHAPE_LOG_PATH` is enabled.
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
