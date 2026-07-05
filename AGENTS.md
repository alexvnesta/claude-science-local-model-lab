# Agent Orientation

This repository is a public, unaffiliated lab for routing a user-supplied
Claude Science app copy through a local Anthropic-compatible proxy. Keep the
repo cloneable, safe, and boring to audit.

## Non-Negotiable Boundaries

- Do not commit `_local/`, app bundles, Claude account state, login cookies,
  SQLite databases, logs, prompts, tool outputs, artifacts, or diagnostic ZIPs.
- Do not add instructions that bypass Claude Science beta access, Anthropic
  account login, organization enablement, or Anthropic terms.
- Do not vendor or copy proprietary Claude Science files.
- Do not copy source from third-party proxy repos unless the license decision is
  explicit and the attribution is updated.
- Treat prior-art projects in `NOTICE.md` and `docs/prior-art-review.md` as
  credited references.

## Current Shape

- `proxy/anthropic_mtplx_proxy.py` is the dependency-free Anthropic Messages to
  OpenAI-compatible proxy.
- `scripts/` launches and verifies the isolated local Claude Science copy.
- `profiles/` contains shell env profiles for MTPLX/Qwen, generic local
  OpenAI-compatible backends, Ollama, and OpenRouter.
- `tests/test_streaming_proxy.py` is the main regression suite for streaming,
  tool-call filtering, schema validation, finite SSE close, request IDs, and
  health metrics.
- `docs/architecture.md` explains the request-shape broker model.
- `docs/why-this-proxy.md` explains the Claude Science-specific value compared
  with Claude Code proxy prior art.

The preferred env names are `UPSTREAM_OPENAI_BASE_URL`,
`UPSTREAM_OPENAI_MODEL`, and `UPSTREAM_API_KEY`. The older
`MTPLX_OPENAI_BASE_URL`, `MTPLX_OPENAI_MODEL`, and `MTPLX_API_KEY` names are
still supported for compatibility. Profiles may point the upstream values at
Ollama, OpenRouter, vLLM, LM Studio, llama.cpp server, or another compatible
backend.

## How To Work Here

1. Start by reading `README.md`, this file, `docs/README.md`, and the relevant
   profile under `profiles/`. Use `docs/architecture.md` when changing proxy
   behavior.
2. Keep changes small and public-safe. If a run needs app state, inspect it only
   locally and summarize protocol shape, never raw user data.
3. Prefer adding provider behavior behind profiles or small conversion helpers
   instead of hard-coding a model-specific branch in launch scripts.
4. When changing tool handling, update tests for both valid and invalid tool
   calls. Claude Science should execute only schema-valid offered tools.
5. When changing docs about access, verify against official Anthropic docs.
6. When adding provider docs, link official provider docs and keep secrets out
   of tracked profiles.

## Verification

For proxy or profile changes, run:

```bash
python3 -m pytest tests
./scripts/test-streaming-proxy.sh
git diff --check
```

For provider checks, use `./scripts/doctor.sh`,
`./scripts/smoke-openrouter.sh`, or `./scripts/smoke-ollama.sh`. Those scripts
may source ignored env files, but they must not print secret values.

For a live Claude Science run, follow `docs/verification-checklist.md`. Keep raw
logs, app databases, prompts, tool outputs, and screenshots under `_local/`.

## Known Technical Debt

- Direct streaming is covered by tests but still needs more app-side hardening
  for long Claude Science tool loops.
- The proxy is still one large Python file. Split it only when the split reduces
  real complexity and keeps tests clear.
- OpenRouter and Ollama support use the generic OpenAI-compatible surface. Model
  tool quality will vary; use `PROXY_TOOL_MODE=drop` for prose-only models and
  focused allowlists for tool-capable models.
