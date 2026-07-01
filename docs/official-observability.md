# Claude Science Observability Boundary

This lab can learn useful protocol shape from a locally installed Claude
Science app without publishing Anthropic proprietary files, account state,
prompts, tool results, logs, or credentials.

## Safe Local-Only Places

Diagnostic archives, extracted logs, local SQLite databases, and local app data
belong under `_local/`. That directory is ignored by git and should remain
local to each user.

## Diagnostic Bundle Contents

Claude Science diagnostic archives may contain files such as:

- `logs/spawn.log`
- `logs/server-*.log`
- `logs/app.log`
- `operon.lock.json`
- `system-info.json`
- `ssh/providers.json`
- `ssh/diagnostics.json`

Keep those files out of git. If a future public report needs evidence from a
bundle, publish only redacted counts or protocol-shape observations, not the
bundle itself.

## SQLite State Sniffing

For a local-only protocol inventory, use the redacted inspector:

```bash
./scripts/sniff-official-state.py --recent 20 --frames 8
```

It opens the local `operon-cli.db` read-only, skips credential tables, and
prints only protocol shape:

- Recent frame IDs, agent names, status, model, and token counters.
- Tool-use inventory by tool name and caller type.
- Recent tool-use rows with input keys and short `human_description` values.
- Tool-result count and size range.
- Host helper-call counts and error counts.

Useful tool-use names observed during local testing included:

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

That shape is directly useful for proxy compatibility testing: assistant
`tool_use` blocks and user `tool_result` blocks can be verified without
publishing raw conversations or tool outputs.

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
