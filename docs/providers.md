# Provider Profiles

The proxy forwards requests to an OpenAI-compatible
`/v1/chat/completions` endpoint. MTPLX/Qwen was the first working proof, but it
is not required.

The preferred profile env names are:

- `UPSTREAM_OPENAI_BASE_URL`: upstream OpenAI-compatible base URL.
- `UPSTREAM_OPENAI_MODEL`: upstream model slug.
- `UPSTREAM_API_KEY`: upstream bearer token. Local servers often ignore it.
- `UPSTREAM_HTTP_REFERER`: optional OpenRouter attribution URL.
- `UPSTREAM_APP_TITLE`: optional OpenRouter app title.
- `PROXY_PROVIDER_NAME`: non-secret provider label shown in `/healthz` and
  proxy logs. Profiles set this to values such as `mtplx`, `ollama`, or
  `openrouter`; otherwise the proxy infers a conservative label from the final
  base URL.
- `PROXY_STREAM_HEARTBEAT_SECONDS`: direct-stream idle heartbeat interval. A
  value above zero emits SSE comments such as `: heartbeat` between upstream
  chunks without adding model text or tool events.

The older `MTPLX_OPENAI_BASE_URL`, `MTPLX_OPENAI_MODEL`, and `MTPLX_API_KEY`
names are still supported for compatibility.

## MTPLX / Local Qwen

The live local proof used MTPLX's OpenAI-compatible endpoint:

```text
UPSTREAM_OPENAI_BASE_URL=http://127.0.0.1:8030/v1
UPSTREAM_OPENAI_MODEL=mtplx-qwen36-27b-optimized-quality
```

MTPLX/Qwen is a companion local stack for the exact demo path; it is not
distributed in this repository. For another local Qwen stack to follow the same
path, expose an OpenAI-compatible server with:

```text
GET  /v1/models
POST /v1/chat/completions
```

Then set `UPSTREAM_OPENAI_BASE_URL` and `UPSTREAM_OPENAI_MODEL` in a local
profile. The model slug must match whatever the upstream server advertises.

Get MTPLX and the demo checkpoint:

- [MTPLX GitHub repo](https://github.com/youssofal/MTPLX)
- [MTPLX app and release downloads](https://mtplx.com/)
- [Youssofal/Qwen3.6-27B-MTPLX-Optimized-Quality](https://huggingface.co/Youssofal/Qwen3.6-27B-MTPLX-Optimized-Quality)

Follow the upstream MTPLX install/onboarding instructions, start an
OpenAI-compatible local server, then point this proxy at the server's base URL.
The public checkpoint ID and the model alias exposed by the local server do not
have to be identical; `UPSTREAM_OPENAI_MODEL` just needs to match the running
server.

Start with prose or narrow tool profiles before broadening tool exposure:

```bash
PROXY_PROFILE=profiles/mtplx-qwen-analysis.env.example ./scripts/start-proxy-detached.sh
PROXY_PROFILE=profiles/mtplx-qwen-tool-probe.env.example ./scripts/start-proxy-detached.sh
PROXY_PROFILE=profiles/mtplx-qwen-execution-probe.env.example ./scripts/start-proxy-detached.sh
```

Observed Qwen behavior:

- It can produce valid `python` and `save_artifacts` calls when the foreground
  tool surface is narrow and explicitly requested.
- It may split a requested artifact workflow across several Python calls even
  when asked to do it in one call.
- It may try to call Claude Science tools inside Python source, for example
  `skill({"skill":"figure-style"})`; the execution profile now filters that
  shape before local execution.
- Reviewer frames should not inherit the foreground allowlist. The execution
  profile uses `PROXY_HARNESS_TOOL_ALLOWLIST` so reviewers can inspect artifacts
  with `repl` and `read_file`.
- Reviewer frames may over-inspect instead of calling `submit_output`. The
  execution profile enables `PROXY_HARNESS_FORCE_SUBMIT_AFTER_TOOL_RESULTS=6`
  so a long reviewer inspection loop is closed by forwarding only
  `submit_output`.
- Local model loops are slow. The refined Qwen artifact run took multiple
  model turns for TSV, figure, Markdown, artifact save, final answer, and
  reviewer inspection. Treat this as a capability proof, not yet an ergonomic
  production default.
- MTPLX/Qwen profiles still default to `PROXY_STREAM_MODE=buffered` because
  that is the known-good app path for short tool loops. Direct mode now has
  proxy-level heartbeat coverage, but it still needs fresh Claude Science
  app-side proof before becoming the default for Qwen execution workflows.
- The analysis profile enables `PROXY_STRIP_THINKING_TEXT=1` so leading
  Qwen-style `<think>...</think>` blocks do not appear in clean no-tool Claude
  Science UI demos. Disable it when you need to debug raw model output.

## Ollama

Ollama documents OpenAI API compatibility at
`http://localhost:11434/v1/`, including `/v1/chat/completions`. Its examples
use an API key value of `ollama`, which is required by OpenAI SDK clients but
ignored by Ollama.

Start Ollama and pull a model:

```bash
# If the Ollama app/daemon is not already running, start `ollama serve`
# in a separate terminal first.
ollama pull qwen3:8b
```

Start this proxy with the Ollama profile:

```bash
OLLAMA_MODEL=qwen3:8b \
PROXY_PROFILE=profiles/ollama.env.example \
./scripts/start-proxy-detached.sh
```

Or run a provider-only smoke:

```bash
OLLAMA_MODEL=qwen3:8b ./scripts/smoke-ollama.sh
```

If the model does not reliably produce tool calls, switch to prose-only mode:

```bash
PROXY_TOOL_MODE=drop \
PROXY_PROFILE=profiles/ollama.env.example \
./scripts/start-proxy-detached.sh
```

Official reference:

- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)

## OpenRouter

OpenRouter documents a standard `/api/v1/chat/completions` endpoint and an
OpenAI SDK-compatible base URL of `https://openrouter.ai/api/v1`. It requires
an `Authorization: Bearer <OPENROUTER_API_KEY>` header. Optional app
attribution headers are useful for OpenRouter leaderboards, but they are not
required for this proxy profile.

Choose a model slug from the OpenRouter model catalog, then start the proxy:

```bash
OPENROUTER_API_KEY=... \
OPENROUTER_MODEL=your/provider-model-slug \
PROXY_PROFILE=profiles/openrouter.env.example \
./scripts/start-proxy-detached.sh
```

For a provider-only smoke, either set `OPENROUTER_MODEL` or let the script pick
a `:free` model from the OpenRouter catalog:

```bash
OPENROUTER_ENV_FILE=/path/to/ignored/.env ./scripts/smoke-openrouter.sh
```

Remote models vary widely in tool-call behavior. Start with short non-tool
prompts, then try a narrow `PROXY_TOOL_ALLOWLIST` before exposing the full
Claude Science tool inventory.

A provider-only smoke can pass while a full Claude Science foreground UI turn
still receives an upstream 429 from a `:free` model. Claude Science foreground
requests include a much larger system/tool context than the smoke script, and
free OpenRouter routes can be capacity-limited. For a public UI GIF, use MTPLX
or a paid/private-capacity OpenRouter route unless the free route is currently
healthy under the real app prompt.

Official references:

- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart)
- [OpenRouter model catalog](https://openrouter.ai/models)

See also [`demo-capture.md`](demo-capture.md).

## Other OpenAI-Compatible Backends

Use `profiles/openai-compatible.env.example` for vLLM, LM Studio, llama.cpp
server, Together, Fireworks, or any similar backend that implements
`POST /v1/chat/completions`.

Concrete local examples:

- LM Studio: start the local server in LM Studio and use
  `UPSTREAM_OPENAI_BASE_URL=http://127.0.0.1:1234/v1`; set
  `UPSTREAM_OPENAI_MODEL` to the exact loaded model ID shown by LM Studio.
- vLLM: start an OpenAI-compatible server such as
  `vllm serve <model> --api-key token-abc123`, then use the server's base URL
  ending before `/chat/completions`.
- llama.cpp server: use a build/server mode that exposes
  `POST /v1/chat/completions`; tool behavior depends on the model's chat
  template and function-calling support.

Provider checklist:

- Confirm the base URL should end before `/chat/completions`.
- Confirm the model slug exactly matches the upstream provider.
- Run `PROXY_PROFILE=... ./scripts/doctor.sh` before live app debugging.
- Keep `PROXY_MAX_TOKENS_CAP` modest until latency is understood.
- Use `PROXY_STREAM_MODE=direct` when upstream streaming is reliable.
- For direct mode, set `PROXY_STREAM_HEARTBEAT_SECONDS` to a modest interval
  such as `15` when the provider has long idle gaps between chunks.
- Use `PROXY_STREAM_MODE=buffered` only when direct streaming breaks the app
  path; long buffered generations can starve Claude Science of events.
- Use `PROXY_TOOL_MODE=drop` for prose-only model tests.
- Use `PROXY_TOOL_MODE=pass`, `PROXY_TOOL_VALIDATION=schema`, and a focused
  `PROXY_TOOL_ALLOWLIST` for live tool-loop experiments.

Official references:

- [LM Studio OpenAI compatibility](https://lmstudio.ai/docs/developer/openai-compat)
- [vLLM OpenAI-compatible server](https://docs.vllm.ai/en/stable/serving/online_serving/)
- [llama.cpp server OpenAI-compatible endpoint](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
