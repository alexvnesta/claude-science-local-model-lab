# Notice And Prior Art

This repository contains an independently implemented local-model lab for
Claude Science. It does not vendor or redistribute Claude Science, Claude
account state, runtime data, logs, prompts, or task outputs.

The proxy work was reviewed against the public projects below on 2026-07-01.
They deserve credit for proving and hardening adjacent Claude Code proxy
patterns. This repo does not include copied source from those projects; the
overlap is architectural prior art around Anthropic-compatible gateways,
OpenAI-compatible backends, streaming, tool-call conversion, and local safety
boundaries.

| Project | License | Reviewed commit | What it contributed as prior art |
| --- | --- | --- | --- |
| [vibheksoni/UniClaudeProxy](https://github.com/vibheksoni/UniClaudeProxy) | MIT | `2f512a3626a25d24cee4e2387db5007802928d4c` | Multi-provider Anthropic-to-OpenAI/Gemini/Anthropic translation, ReAct XML fallback, local-only binding, streaming/tool-call conversion. |
| [raine/claude-code-proxy](https://github.com/raine/claude-code-proxy) | MIT | `24cf55825cb40a72345dc59a88b040e8cdb54f84` | Rust implementation of Claude Code to Codex/Kimi/Cursor subscription backends, robust stream reduction, auth/token flows, and monitor UI. |
| [routatic/proxy](https://github.com/routatic/proxy) | AGPL-3.0 | `9e294f9a2ec2ea5fa20b6c126800bac5847ced23` | Go CLI proxy for Claude Code with OpenCode Go/Zen and AWS Bedrock routing, Anthropic/OpenAI/Responses/Gemini transformations, scenario routing, fallback chains, Anthropic-first failover, and debug redaction. |
| [seifghazi/claude-code-proxy](https://github.com/seifghazi/claude-code-proxy) | MIT | `02c9c766679eee75c861bbde11c6d8b5249d44a7` | Transparent request capture, SQLite conversation visualization, and optional agent routing. |
| [Rishurajgautam24/free-claude-code](https://github.com/Rishurajgautam24/free-claude-code) | MIT | `a599319dd6d56cf5ea1db7e52eeac0bc80fccb7c` | NVIDIA NIM/OpenRouter/LM Studio routing for Claude Code, heuristic text-tool parsing, request optimization, rate limiting. This was also the origin of the local `_local/free-claude-code` clone used for comparison only. |
| [Alishahryar1/free-claude-code](https://github.com/Alishahryar1/free-claude-code) | MIT | `6a48811a9a648110c894738ee62dcb48b69cef96` | Larger current Free Claude Code line with Admin UI, Claude Code and Codex support, broad provider catalog, strict conversion tests, local web-tool handling, and model picker support. |
| [fkiene/llmtrim](https://github.com/fkiene/llmtrim) | MPL-2.0 | `47375c77aff30e29899414038d79b4e1ab929ecd` | Token-compression proxy and library. This is not a model-adapter proxy, but it is relevant prior art for safe request rewriting, token gates, tool-schema trimming, and local interception boundaries. |
| [1rgs/claude-code-proxy](https://github.com/1rgs/claude-code-proxy) | No license detected by GitHub | `5e45ba683ded931c1832cfca6468a791c6855e45` | Early LiteLLM-based Anthropic client proxy for OpenAI/Gemini/Anthropic with model mapping and streaming support. |
| [fuergaosi233/claude-code-proxy](https://github.com/fuergaosi233/claude-code-proxy) | MIT | `7ea4177a54a5ff7969a5f8ec76d9f80f2e0409e5` | FastAPI/OpenAI-compatible proxy with tool conversion, streaming, cancellation handling, custom headers, Azure/OpenAI/Ollama examples. |

NVIDIA NIM is treated here as an upstream provider path rather than a single
proxy repository. The reviewed NIM-specific proxy line is the Free Claude Code
family above, alongside NVIDIA's public Claude Code integration documentation.

## How This Repo Differs

- It targets Claude Science, not Claude Code.
- It keeps a copied Claude Science app and all runtime data under ignored
  `_local/` paths supplied by the user.
- It focuses on the Claude Science request shapes observed in local runs:
  foreground science-agent turns, hidden-tool analysis turns, and reviewer or
  harness turns such as `submit_output`.
- It validates returned tool calls against the tool schemas Claude Science
  offered for that specific request, without repairing model mistakes into
  executable tool calls.
- It includes regression tests for streaming, filtered tool calls, finite SSE
  close, request IDs, health metrics, and schema/name validation.

## Attribution Policy

If this project later copies code from any prior-art project, keep that code's
license terms intact and add a file-level attribution note. Do not copy
AGPL-licensed implementation code into this MIT-licensed repository without
making a deliberate licensing decision. For now, attribution is handled through
this notice and the prior-art review in `docs/prior-art-review.md`.
