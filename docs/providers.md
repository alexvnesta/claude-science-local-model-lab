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

The older `MTPLX_OPENAI_BASE_URL`, `MTPLX_OPENAI_MODEL`, and `MTPLX_API_KEY`
names are still supported for compatibility.

## Ollama

Ollama documents OpenAI API compatibility at
`http://localhost:11434/v1/`, including `/v1/chat/completions`. Its examples
use an API key value of `ollama`, which is required by OpenAI SDK clients but
ignored by Ollama.

Start Ollama and pull a model:

```bash
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

Official references:

- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart)
- [OpenRouter model catalog](https://openrouter.ai/models)

## Other OpenAI-Compatible Backends

Use `profiles/openai-compatible.env.example` for vLLM, LM Studio, llama.cpp
server, Together, Fireworks, or any similar backend that implements
`POST /v1/chat/completions`.

Provider checklist:

- Confirm the base URL should end before `/chat/completions`.
- Confirm the model slug exactly matches the upstream provider.
- Run `PROXY_PROFILE=... ./scripts/doctor.sh` before live app debugging.
- Keep `PROXY_MAX_TOKENS_CAP` modest until latency is understood.
- Use `PROXY_STREAM_MODE=direct` when upstream streaming is reliable.
- Use `PROXY_STREAM_MODE=buffered` only when direct streaming breaks the app
  path; long buffered generations can starve Claude Science of events.
- Use `PROXY_TOOL_MODE=drop` for prose-only model tests.
- Use `PROXY_TOOL_MODE=pass`, `PROXY_TOOL_VALIDATION=schema`, and a focused
  `PROXY_TOOL_ALLOWLIST` for live tool-loop experiments.
