# Roadmap And Cleanup Notes

## Current Assessment

This proxy is in a useful state for a public research lab, but live app claims
should still be backed by a fresh checklist run. The deterministic suite covers
the fragile proxy parts: streaming conversion, direct-stream idle heartbeats,
finite SSE close, request ID response headers, tool-call filtering, schema
validation, structural harness request classification, native/server-tool
non-forwarding, strict allowlist behavior, and redacted health metrics.

It is not yet a polished production gateway. The main risks are long-running
streaming behavior, the size of the single proxy file, and the fact that
provider support is still profile-based rather than a first-class provider
abstraction. The first
module split is underway (`request_shape.py` and `observability.py`), but the
translation/server state machine is still mostly in one file. Local Qwen 27B
can complete short direct answers, but full Claude Science tool loops remain
slower and less reliable than hosted Claude.

## Highest-Value Refinements

1. Harden direct streaming for live Claude Science app loops.

   The test suite now covers direct OpenAI SSE to Anthropic SSE conversion,
   idle heartbeat comments, request-ID headers, finite close, and buffered
   validation of upstream streamed tool-call argument deltas. The known-good
   MTPLX/Qwen app path is still buffered for short loops. Direct mode still
   needs app-side proof for long generations, safe app-visible incremental tool
   arguments, cancellation under real browser/app disconnects, and
   reviewer/harness traffic.

2. Split the proxy into modules.

   Started: `request_shape.py` owns request-kind classification, and
   `observability.py` owns redacted counters/logging/request IDs. A reasonable
   next split would be `server.py`, `config.py`, `anthropic.py`,
   `openai_compat.py`, `streaming.py`, `tools.py`, `profiles.py`, and
   `schema_validation.py`. Do this when tests can move with the code, not as a
   cosmetic shuffle.

3. Continue provider transport cleanup.

   OpenRouter and Ollama now have provider smoke scripts, `UPSTREAM_*` aliases,
   a small `doctor` command, explicit `PROXY_PROVIDER_NAME`, and profile
   defaults for direct-stream heartbeats. The next useful layer is a typed
   config file, more provider-specific defaults, and optional live-provider
   smoke coverage for additional OpenAI-compatible services.

4. Keep request-shape classification separate from provider transport.

   Claude Science request kinds (`plain`, `tools_hidden`, `tool_agent`,
   `harness`) currently label redacted metrics only. Provider selection, stream
   mode, and tool forwarding remain explicit profile/request settings. If future
   evidence justifies request-specific routing, add and test that policy rather
   than implying classification already changes behavior. Keep reviewer-specific
   inspection experiments outside proxy core until a trace proves a general
   transport requirement.

5. Improve observability without leaking data.

   Initial version done: `/v1/messages` responses include `X-Request-Id`, logs
   carry that ID, and `/healthz` exposes counters by request kind/stream mode,
   provider latency, retry counts, upstream error counts, and tool-call filter
   reasons. Keep prompts, tool arguments, tool results, account state, and
   artifacts out of public logs.

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

9. Measure reviewer budget needs before adding policy controls.

    Live reviewer probes showed reviewer quality can improve when artifact
    inspection tools are visible, but reviewers may then over-inspect and delay
    `submit_output`. Do not add proxy-side reviewer forcing without fresh
    evidence that it is a transport requirement rather than model behavior.

10. Add local process durability checks.

    Long Qwen/reviewer loops can leave the isolated app or upstream model
    server unavailable. Add a post-run health monitor that reports whether
    official Claude Science, isolated Claude Science, proxy, and upstream model
    ports are still listening, plus a clean recovery recipe.

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
