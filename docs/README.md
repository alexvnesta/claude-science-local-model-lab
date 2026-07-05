# Documentation Index

Start with the README for the public overview and Quick Start. Use this page
when you need a more specific reference.

## Core Docs

- [`why-this-proxy.md`](why-this-proxy.md): short rationale, diagram, and how
  this differs from a traditional Claude Code proxy.
- [`providers.md`](providers.md): OpenRouter, MTPLX/Qwen, Ollama, and generic
  OpenAI-compatible backend setup notes.
- [`architecture.md`](architecture.md): request-shape broker model, tool
  routing, schema validation, streaming, and observability design.
- [`verification-checklist.md`](verification-checklist.md): checklist for
  proving proxy routing, smoke testing, permissions, and reviewer/tool loops.

## Reference Docs

- [`access.md`](access.md): Claude Science beta access and entitlement notes
  with official Anthropic references.
- [`prior-art-review.md`](prior-art-review.md): reviewed Claude Code proxy
  projects and what this repo borrows or deliberately does differently.
- [`official-observability.md`](official-observability.md): what can be learned
  from local Claude Science diagnostics without publishing private data.
- [`roadmap.md`](roadmap.md): next engineering work and known technical debt.

## Archive

Archived files are historical lab notes. They may mention experiments, profiles,
or model-rescue behavior that has since been removed; use the core docs above
for the current proxy contract.

- [`archive/initial-findings.md`](archive/initial-findings.md): chronological
  lab notes from early protocol discovery.
- [`archive/github-post.md`](archive/github-post.md): older long-form draft
  writeup, kept for historical context.
