# Demo Capture Notes

This repo can show two different things, and they should not be conflated:

- Routing proof: the proxy can reach a provider, Claude Science can discover
  the advertised Claude-shaped model, and the proxy can translate a simple
  `/v1/messages` request.
- Workflow proof: the full Claude Science UI can complete a foreground turn,
  tool loops, artifact creation, and reviewer/harness checks through that
  provider.

The current MTPLX/Qwen evidence includes workflow proof. The current
OpenRouter-free evidence includes provider smoke proof and model-picker routing
proof, but the free-tier UI capture is not stable enough to publish as a
working demo GIF.

## Model Picker Labels

Claude Science expects Claude-shaped model IDs. For local or remote non-Claude
providers, keep the advertised model ID compatible and change the visible label:

```bash
PROXY_ADVERTISED_MODELS=claude-opus-4-8
PROXY_MODEL_DISPLAY_NAMES='{"claude-opus-4-8":"OpenRouter openai/gpt-oss-20b:free"}'
```

The app may still show `unavailable` when its account or project-level state
marks the original Claude model unavailable. The proxy can control the model
list response and display name, but it cannot change Claude Science account
entitlements or every client-side availability rule.

## OpenRouter Free Capture Caveat

On 2026-07-01, provider-only OpenRouter smoke tests passed through this proxy,
including automatic selection of a `:free` catalog model. Full Claude Science
foreground UI requests to `google/gemma-4-26b-a4b-it:free` and
`openai/gpt-oss-20b:free` then hit upstream OpenRouter 429 capacity responses.

That failure is useful information:

- The OpenRouter profile and authentication path were working.
- Claude Science foreground prompts are much larger than provider-only smoke
  prompts; one observed foreground prompt was about 66k characters before the
  user text.
- Free models can be capacity-limited at exactly the moment a polished demo
  needs them.

For a clean public GIF, prefer one of these setups:

- Local MTPLX/Qwen on `127.0.0.1:8030/v1`, because it avoids remote free-tier
  capacity.
- OpenRouter with a paid or private-capacity model route.
- A separate provider with predictable streaming and enough context for the
  full Claude Science foreground prompt.

## Suggested Capture Script

Use isolated ports so the official Claude Science app remains untouched:

```bash
PROXY_PORT=18081 \
PROXY_PROFILE=profiles/openrouter.env.example \
OPENROUTER_MODEL=openai/gpt-oss-20b:free \
PROXY_TOOL_MODE=drop \
PROXY_STREAM_MODE=buffered \
./scripts/start-proxy-detached.sh

CLAUDE_SCIENCE_PORT=18765 \
ANTHROPIC_BASE_URL=http://127.0.0.1:18081 \
./scripts/launch-claude-science-local.sh
```

Then verify the provider path first:

```bash
OPENROUTER_ENV_FILE=/path/to/ignored/.env ./scripts/smoke-openrouter.sh
curl -s http://127.0.0.1:18081/healthz
```

For the UI capture, use a short no-tool prompt:

```text
No tools, no files, no browsing. Reply with exactly: LOCAL PROXY DEMO OK
```

If the UI shows a provider-capacity retry or the proxy logs an upstream 429,
do not publish that as a working demo. Keep the note as a provider-capacity
finding and retry with MTPLX or a non-free OpenRouter route.

## What To Show In A GIF

A useful short GIF should show:

- The isolated local URL, normally `http://127.0.0.1:18765/...`.
- The model picker label, for example `OpenRouter openai/gpt-oss-20b:free` or
  `MTPLX Qwen 27B`.
- A short deterministic prompt.
- The rendered response.
- Optionally, a terminal tail with redacted proxy lines showing
  `POST /v1/messages`, request kind, provider name, and request ID.

Do not show account state, cookies, prompt logs, tool arguments, tool results,
artifacts containing private data, or API keys.
