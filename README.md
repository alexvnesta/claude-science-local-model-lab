# Claude Science Local Model Lab

Experimental lab for running a copied Claude Science instance against a local
OpenAI-compatible model server through an Anthropic-compatible proxy.

The first working proof used MTPLX/Qwen, but the proxy is intentionally model
agnostic: MTPLX, Ollama, LM Studio, vLLM, llama.cpp server, or any similar
OpenAI-compatible `/v1/chat/completions` endpoint can be configured with a
profile file.

## Safety Boundary

This repo does not track the Claude Science app bundle, Claude account state,
task data, logs, or proxy PID files. Those live under `_local/`, which is
gitignored.

The default launch script uses a separate Claude Science instance:

- Official app stays on `http://127.0.0.1:8765`.
- Local-model app copy runs on `http://127.0.0.1:18765`.
- Proxy listens on `http://127.0.0.1:18080`.
- Sandbox port is `18766`.

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

Smoke test the proxy:

```bash
./scripts/smoke-proxy.sh
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

The MTPLX proof profile is in `profiles/mtplx-qwen.env.example`. A generic
profile for Ollama/Gemma/vLLM/LM Studio is in
`profiles/openai-compatible.env.example`.

## Current Status

The gateway path works: the isolated Claude Science copy made real
`/v1/messages` calls to the local proxy, the proxy routed them to MTPLX, and
Claude Science rendered `LOCAL MODEL OK` in the UI.

Known limitations:

- Streaming is currently buffered: the proxy waits for a full upstream response,
  then emits Anthropic SSE events.
- Tool-call translation is sufficient for the first proof, but needs more stress
  testing before serious agentic scientific workflows.
- Claude Science asks for large `max_tokens` values, so local profiles should
  keep a sane cap.
- MTPLX can serialize concurrent foreground/background generations. The proxy
  retries transient `session_busy` responses, but serious runs should still keep
  background-review traffic in mind.
- Some UI metadata can still say the Claude alias is unavailable even while
  request routing is local.

See `docs/verification-checklist.md` for the exact proof checklist and
`docs/github-post.md` for a publishable write-up draft.
