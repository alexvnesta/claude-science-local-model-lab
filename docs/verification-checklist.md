# Verification Checklist

Use this checklist before publishing a run result or changing the proxy.

## 1. Confirm Separation

```bash
./scripts/status.sh
```

Expected:

- Official Claude Science is still on `127.0.0.1:8765`.
- Local Claude Science uses `127.0.0.1:18765`.
- Proxy uses `127.0.0.1:18080`.
- MTPLX or another OpenAI-compatible backend is reachable.

## 2. Start Proxy

```bash
PROXY_PROFILE=profiles/mtplx-qwen.env.example ./scripts/start-proxy-detached.sh
```

For direct-analysis runs with MTPLX/Qwen, prefer:

```bash
PROXY_PROFILE=profiles/mtplx-qwen-analysis.env.example ./scripts/start-proxy-detached.sh
```

For another local backend, copy and edit the generic profile:

```bash
cp profiles/openai-compatible.env.example profiles/local.env
PROXY_PROFILE=profiles/local.env ./scripts/start-proxy-detached.sh
```

## 3. Smoke Proxy

```bash
./scripts/smoke-proxy.sh
./scripts/test-streaming-proxy.sh
```

Expected:

- `/healthz` returns the configured upstream and advertised model list.
- `/healthz` shows the intended `stream_mode`, `tool_mode`, and
  `parse_text_tool_calls` values.
- `/v1/messages/count_tokens` returns an `input_tokens` value.
- `/v1/messages` returns a message containing `mtplx proxy ok`.
- `./scripts/test-streaming-proxy.sh` passes streamed text, streamed tool-call
  deltas, full-JSON fallback, finite SSE close, and Qwen text-tool-call adapter
  cases.

## 4. Launch Isolated Claude Science

```bash
./scripts/launch-claude-science-local.sh
```

In another terminal:

```bash
./scripts/local-url.sh
```

Open the returned URL.

## 5. Interactive UI Proof

Send:

```text
For this gateway test, reply with exactly LOCAL MODEL OK. Do not use tools.
```

Expected:

- The Claude Science UI renders `LOCAL MODEL OK`.
- `_local/proxy.log` shows `POST /v1/messages` for the same interaction.
- The proxy log shows the upstream model, requested token count, capped token
  count, and upstream completion time.
- For MTPLX, transient `session_busy` log lines are acceptable if they retry and
  later complete. Persistent `session_busy` means the local backend is saturated.

## 6. Bounded Analysis Proof

Use a fresh session when possible. Send a short, self-contained scientific
analysis prompt, for example:

```text
No tools, no files, no browsing. Answer directly in 5 bullets, max 350 words.

Analyze this mini MASLD-HCC signal: DKK1 +2.3, SOX4 +1.8, RELB +1.2, KRT19 +2.0, EPCAM +1.5, COL1A1 +1.3, TNFRSF12A +1.1, ALB -1.4, CYP3A4 -1.6. All are adjusted-significant. Caveat: summary table only, no raw counts, cohort metadata, survival, or validation.

Say: (1) likely biology, (2) strongest caveat/stop signal, (3) what Claude Science handles well, (4) what Insight still defensibly owns, (5) one next experiment with pass/fail criteria.
```

Expected:

- The UI renders a substantive answer, not just a gateway echo.
- The frame eventually reaches `completed` in the isolated SQLite database.
- For the Qwen analysis profile, `_local/proxy.log` should show Claude Science
  tool schemas dropped before upstream, e.g. `tools=26 upstream_tools=0`.
- Reviewer status may still be model-specific. If it is inconclusive, inspect
  the reviewer message shape and add a narrow adapter plus a regression test.

## 7. Record Evidence

Capture:

- Port status from `./scripts/status.sh`.
- Last 80 lines of `_local/proxy.log`.
- The UI response text.
- Any UI model metadata warnings.
- Frame status and short output preview from the isolated
  `_local/data/.../operon-cli.db` database.

Do not publish `_local/`, app bundles, account state, logs with secrets, or task
data.
