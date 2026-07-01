# Roadmap And Cleanup Notes

## Current Assessment

This proxy is in a good state for a public research lab. It proves that an
isolated Claude Science app copy can route Anthropic-style model calls through
a local proxy into an OpenAI-compatible backend, and it has real tests around
the fragile parts: streaming conversion, finite SSE close, tool-call filtering,
schema validation, and Qwen-style reviewer tool-call text.

It is not yet a polished production gateway. The main risks are long-running
streaming behavior, the size of the single proxy file, model-specific adapters
living near generic conversion code, and the fact that provider support is
still profile-based rather than a first-class provider abstraction.

## Highest-Value Refinements

1. Harden direct streaming for live Claude Science app loops.

   The test suite covers direct OpenAI SSE to Anthropic SSE conversion, but the
   known-good MTPLX/Qwen app path is still buffered for short loops. Direct
   mode needs app-side proof for long generations, incremental tool arguments,
   cancellation, idle heartbeats, and reviewer/harness traffic.

2. Split the proxy into modules.

   A reasonable split would be `server.py`, `config.py`, `anthropic.py`,
   `openai_compat.py`, `streaming.py`, `tools.py`, `profiles.py`,
   `schema_validation.py`, and `adapters/qwen.py`. Do this when tests can move
   with the code, not as a cosmetic shuffle.

3. Continue provider transport cleanup.

   OpenRouter and Ollama now have provider smoke scripts, `UPSTREAM_*` aliases,
   and a small `doctor` command. The next useful layer is a typed config file,
   more provider-specific defaults, and optional live-provider smoke coverage
   for additional OpenAI-compatible services.

4. Keep request-shape routing separate from provider transport.

   Claude Science request kinds (`plain`, `tools_hidden`, `tool_agent`,
   `harness`) should remain the broker's core abstraction. Provider selection,
   stream mode, and tool adapter choices should hang off that classification
   rather than being mixed into app launch scripts.

5. Improve observability without leaking data.

   Add structured, redacted request IDs, counters by request kind, provider
   latency, retry counts, and tool-call filter reasons. Keep prompts, tool
   arguments, tool results, account state, and artifacts out of public logs.

6. Package the project.

   Add `pyproject.toml`, an installable console entrypoint, and a typed config
   file format while preserving the simple shell profile path for quick tests.

7. Separate evidence logs from quick-start docs.

   The README should stay cloneable and short. Long frame IDs, app-path proof,
   and version archaeology should live in evidence docs or release notes.

8. Broaden provider smoke tests beyond Ollama and OpenRouter.

   Keep CI deterministic by defaulting to fake upstreams, but add optional live
   smoke paths for vLLM, LM Studio, llama.cpp server, and other providers when
   their local endpoints or API keys are present.

## Cleanup Principles

- Keep `_local/` as the only place for app copies, logs, cookies, databases,
  and artifacts.
- Prefer profiles over code branches until a provider quirk is proven and
  tested.
- Treat hidden tools honestly: if a profile hides tools from the local model,
  it should not claim to have browsed, executed code, read files, or saved
  artifacts.
- Treat reviewer/harness tools as structural app protocol, not general user
  capabilities.
- Keep comparisons with prior art specific and credited.
