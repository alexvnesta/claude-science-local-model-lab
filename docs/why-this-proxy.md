# Why This Proxy Exists

This proxy is not "better" than every Claude Code proxy. Several reviewed
projects are more mature general-purpose gateways. This repo is better for one
specific job: running an isolated Claude Science app copy against a local or
OpenAI-compatible model while preserving Claude Science's foreground,
reviewer, and harness request shapes.

## What It Does Better For Claude Science

- Isolated Claude Science launch path that leaves the official app and account
  state alone.
- Claude Science's observed Anthropic surface: `/v1/models`,
  `/v1/models/{id}`, `/v1/messages`, and `/v1/messages/count_tokens`, including
  the `/v1/models?limit=1000` query the app sends before request submission.
- Claude Science-specific request classification: `plain`, `tools_hidden`,
  `tool_agent`, and `harness`.
- Separate harness-tool handling for reviewer calls such as `submit_output`, so
  reviewer structure is not lost when the foreground tool allowlist is narrow.
- Anthropic/OpenAI tool translation in both directions: Claude Science
  `tool_use` and `tool_result` blocks become OpenAI-compatible tool messages,
  while upstream OpenAI `tool_calls` become Claude Science-compatible
  Anthropic `tool_use` blocks.
- Claude Science compatibility details such as stable `toolu_...` IDs and
  `caller: {"type": "direct"}` on emitted tool-use blocks when the app expects
  that shape.
- Local-model text-tool adapters for observed reviewer/Qwen outputs:
  `<tool_call>[...]`, `::tool::+json::...`, fenced JSON, OpenAI-style function
  JSON, `submit_output(...)`, markdown-wrapped calls, and XML-ish
  `<function=...>` blocks.
- Schema validation against the exact tools Claude Science offered in that
  request before emitting executable Anthropic `tool_use` blocks.
- Metadata-only repair for known Claude Science/Qwen friction, without filling
  semantic fields like commands, code, paths, or artifact payloads.
- Hidden-tool honesty guard, so profiles that hide tools ask the local model to
  answer directly rather than fake searches, file reads, code execution, or
  artifact creation.
- Redacted tool-schema inventory logging for adapter development without
  publishing prompts, outputs, or proprietary app data.
- Regression tests for finite Anthropic SSE close, streamed OpenAI text,
  streamed tool-call deltas, invalid tool filtering, full-JSON fallback, and
  observed Qwen reviewer text-tool-call formats.
- Claude-shaped model aliases and display-name control so Claude Science's
  model picker can show a local backend label instead of an unavailable-looking
  cloud slug.
- Provider-neutral profiles for OpenAI-compatible backends, including Ollama
  and OpenRouter, not only the original MTPLX/Qwen proof.

## Where Other Projects Are Better

- Use UniClaudeProxy or similar universal adapters when you need broad Claude
  Code provider support, ReAct/XML fallbacks, image modes, or richer config.
- Use raine/claude-code-proxy-style designs as streaming-state-machine
  inspiration; they are stronger references for provider login and live
  streaming behavior.
- Use routatic/proxy as routing-policy prior art. Its scenario routing,
  fallback chains, and health handling are more advanced, but its AGPL-3.0
  license means this MIT repo treats it as design inspiration only unless the
  license decision changes.
- Use observability-focused proxies when request capture and dashboards matter
  more than Claude Science tool-loop compatibility.

## Design Position

This repo optimizes for:

- Public-safe reproducibility.
- Small dependency surface.
- Local-only app/runtime boundary.
- Honest beta/access caveats.
- Claude Science reviewer and tool-loop correctness.
- Clear credit to prior work.

It intentionally does not try to be:

- A subscription bypass.
- A redistributed Claude Science package.
- A universal Claude Code replacement.
- A mature provider router with billing, accounts, dashboards, or automatic
  fallback chains.

The right future direction is to keep the Claude Science broker behavior sharp
while gradually modularizing provider transport, streaming, and model-specific
tool adapters.
