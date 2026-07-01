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

Primary MTPLX/Qwen workflow demo GIF:
[`assets/qwen-mtplx-tp53-workflow-demo.gif`](assets/qwen-mtplx-tp53-workflow-demo.gif).
It is an annotated presentation layer built from a real Claude Science run that
produced a TCGA-BRCA TP53 expression plot and a markdown summary.

The TP53 capture was recorded on 2026-07-01 with:

- MTPLX serving `mtplx-qwen36-27b-optimized-quality` on
  `127.0.0.1:8030/v1`.
- Proxy on `127.0.0.1:18081` using
  `profiles/mtplx-qwen-execution-probe.env.example`.
- Isolated Claude Science on `127.0.0.1:18765`.
- Visible model label: `MTPLX Qwen 27B Local`.
- Prompt: a constrained TP53 task that pinned the Xena matrix URL:
  `https://tcga.xenahubs.net/download/TCGA.BRCA.sampleMap/HiSeqV2.gz`.

Evidence from the run:

- Foreground frame `0b03da82-efe5-4440-be56-651d7053d1fb` completed.
- First reviewer child `be081ac7-04c1-4d5a-9151-8caf627797c8` correctly failed
  the run because the PNG and markdown had not yet been saved.
- Qwen self-corrected, generated `tp53_expression_plot.png`, and saved
  `tp53_summary.md`.
- Final reviewer child `063795d2-56a4-4776-84e6-afdd3970f05b` completed with
  `findings: []` and resolved the prior failure.
- Saved artifacts:
  - `tp53_expression_plot.png`, artifact
    `ae4d414a-38de-4334-bcae-6aa3f3fdbda9`, checksum
    `c8390dc423e6d334f856ec277371bb97de98ea224760261cd6baa3c416fdb5cc`.
  - `tp53_summary.md`, artifact `830784fd-ff66-4761-b0c2-7b328e5cb8cf`,
    checksum
    `45f31d6d9c2070cf21425ba310e3e2377b251d30e83fe21062ec544815bad891`.

Network note: Claude Science's network allowlist must include both the Xena hub
and its redirected S3 host for this demo:

- `tcga.xenahubs.net`
- `tcga-xena-hub.s3.dualstack.us-east-1.amazonaws.com`

This is a workflow proof, not a data-discovery proof. The Xena matrix URL was
pinned so the GIF tests local model execution, artifact creation, and reviewer
recovery rather than whether Qwen can discover the correct public dataset.

Regenerate the annotated GIF from captured screenshots:

```bash
python3 scripts/make-tp53-demo-gif.py \
  --capture-dir /tmp/tp53-qwen-final-capture \
  --output docs/assets/qwen-mtplx-tp53-workflow-demo.gif \
  --contact /tmp/tp53-qwen-demo-contact.png
```

Older exact-reply MTPLX/Qwen demo GIF:
[`assets/qwen-mtplx-annotated-demo.gif`](assets/qwen-mtplx-annotated-demo.gif).
It is an annotated presentation layer built from the raw capture at
[`assets/qwen-mtplx-clean-demo.gif`](assets/qwen-mtplx-clean-demo.gif). The
raw capture was recorded on 2026-07-01 with:

- MTPLX serving `mtplx-qwen36-27b-optimized-quality` on
  `127.0.0.1:8030/v1`.
- Proxy on `127.0.0.1:18081` using
  `profiles/mtplx-qwen-analysis.env.example`.
- Isolated Claude Science on `127.0.0.1:18765`.
- Prompt: `No tools, no files, no browsing. Reply with exactly: QWEN MTPLX CLEAN OK`.

The older exact-reply capture intentionally ends on the successful visible
answer. In the same run, the reviewer later ended `Inconclusive` with no
structured output, which is still a current Qwen/harness caveat for this
no-tool demo path.

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
- For workflow demos, the generated artifact or figure opened visibly in the
  app, plus the final reviewer status.
- Optionally, a terminal tail with redacted proxy lines showing
  `POST /v1/messages`, request kind, provider name, and request ID.

Do not show account state, cookies, prompt logs, tool arguments, tool results,
artifacts containing private data, or API keys.

## Thinking Text

Qwen may emit visible `<think>...</think>` text when Claude Science's larger
foreground prompt triggers reasoning behavior, even when the upstream server is
configured for terse answers. The MTPLX/Qwen analysis profile enables:

```bash
PROXY_STRIP_THINKING_TEXT=1
```

This strips leading local-model thinking blocks from buffered assistant text
before the proxy emits Anthropic text. It is meant for clean prose/demo runs.
Leave it off when debugging raw provider behavior or testing direct streaming.
