# Architecture

This lab keeps Claude Science itself intact and redirects only the model API
path for a copied, isolated instance.

```mermaid
flowchart LR
  official["Official Claude Science\n127.0.0.1:8765\nOpus path"]:::official
  copy["Copied Claude Science\n127.0.0.1:18765\nisolated _local/data"]:::local
  proxy["Anthropic-compatible proxy\n127.0.0.1:18080"]:::local
  backend["OpenAI-compatible backend\nMTPLX/Ollama/vLLM/LM Studio"]:::backend

  official --> cloud["Anthropic cloud"]
  copy -->|ANTHROPIC_BASE_URL| proxy
  proxy -->|/v1/chat/completions| backend

  classDef official fill:#fff7ed,stroke:#f97316,color:#111827
  classDef local fill:#eef2ff,stroke:#6366f1,color:#111827
  classDef backend fill:#ecfdf5,stroke:#10b981,color:#111827
```

## Proxy Surface

The proxy implements the small Anthropic surface Claude Science exercised in the
first proof:

- `GET /healthz`
- `GET /v1/models`
- `POST /v1/messages`
- `POST /v1/messages/count_tokens`

For `/v1/messages`, the proxy converts Anthropic Messages payloads into
OpenAI-compatible chat-completion payloads, forwards them to the configured
backend, then converts the response back into Anthropic Messages shape.

## Model Adaptation

Model-specific behavior belongs in profiles, not in Claude Science launch
logic. The MTPLX/Qwen profile is only the first known-good profile.

Useful profile dimensions:

- Model ID and base URL.
- Advertised Claude alias, usually `claude-opus-4-8`, plus the real local model.
- Request timeout.
- `max_tokens` cap.
- Future: provider-specific thinking/tool-call/JSON-mode hints.

## Main Technical Debt

The current proxy buffers streaming requests. Claude Science can consume the
synthetic Anthropic SSE response, but true incremental tool-call streaming will
be needed for reliability and speed on longer workflows.
