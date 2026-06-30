# Official Claude Science Observability

This lab can learn a lot from official Claude Science without intercepting
encrypted Anthropic traffic or printing credentials.

## Safe Places

Diagnostic archives and extracted logs belong under `_local/diagnostics/`.
That directory is ignored by git through the top-level `_local/` rule.

The first preserved bundle:

- Source: `/Users/alex/Downloads/operon-diagnostics-20260630T195142.zip`
- Safe copy:
  `_local/diagnostics/operon-diagnostics-20260630T195142.zip`
- SHA-256:
  `a6131bf57d8c17d3d96471daea461b8ffd7bcc1e54859084eb6301d667a1890d`

## Diagnostic Bundle Contents

The 2026-06-30 diagnostics archive contains:

- `logs/spawn.log`
- `logs/server-20260630.log`
- `logs/app.log`
- `operon.lock.json`
- `system-info.json`
- `ssh/providers.json`
- `ssh/diagnostics.json`

It does not include the SQLite conversation database.

## What The Logs Show

Useful high-level signals from the preserved bundle:

- Official build:
  `0.1.0-dev.20260630.t160235.sha2e3e6f9`
- Official daemon PID: `10002`
- Official UI port: `127.0.0.1:8765`
- Sandbox origin: `http://localhost:8766/mcp_apps`
- Platform: macOS arm64, Node `v24.3.0`, Bun `1.3.13`
- Memory: 64 GiB
- Built-in MCP warmup attempts: 24 connectors
- MCP package set includes `mcp==1.27.1`, `requests==2.33.1`,
  `pandas==2.3.3`
- No SSH providers were configured in the bundle.

Operational counts from the extracted logs:

- `12` LLM perf lines
- `490` tool-pruning lines
- `48` MCP connector acquire-timeout lines
- `8` persisted large tool-result lines
- `26` verifier lines

The perf lines show primary `claude-opus-4-8` calls and at least one
`claude-sonnet-4-6` auxiliary/review-style call.

## SQLite State Sniffing

Use the redacted inspector:

```bash
./scripts/sniff-official-state.py --recent 20 --frames 8
```

It opens the official `operon-cli.db` read-only, skips credential tables, and
prints only protocol shape:

- Recent frame IDs, agent names, status, model, and token counters.
- Tool-use inventory by tool name and caller type.
- Recent tool-use rows with input keys and short `human_description` values.
- Tool-result count and size range.
- Host helper-call counts and error counts.

The first redacted run parsed:

- `1144` messages
- `580` `tool_use` blocks
- `579` `tool_result` blocks
- Tool-result length range: `16` to `48934`

Top tool-use names:

- `python`
- `bash`
- `update_step_status`
- `repl`
- `save_artifacts`
- `read_file`
- `edit_file`
- `submit_output`
- `manage_environments`
- `skill`
- `search_skills`
- `generate_plan`

This confirms that official Claude Science stores model-facing messages in an
Anthropic-compatible shape with assistant `tool_use` blocks and user
`tool_result` blocks. That is directly useful for proxy compatibility testing.

## Boundary

Do not publish or commit:

- Diagnostic ZIPs
- Extracted logs
- SQLite databases
- Claude account state
- Credential tables
- Raw prompts, tool arguments, or tool results

Publish only redacted inventories, counts, protocol shapes, and reproducible
inspection scripts.
