# Public Evidence Bundle

This page collects the shareable proof points behind the README demo without
including Claude Science account state, app databases, cookies, prompts, tool
arguments, tool results, or private artifacts.

## What The Demo Proves

- An isolated copied Claude Science app can route Anthropic-shaped traffic to a
  local proxy instead of the official Anthropic model endpoint.
- The proxy can advertise Claude-shaped model IDs with a visible local-provider
  display name, for example `MTPLX Qwen 27B Local`.
- Foreground agent, reviewer/harness, and tool-agent traffic are classified and
  adapted separately.
- The TP53 TCGA-BRCA workflow completed through local MTPLX/Qwen with Python
  execution, artifact saving, a reviewer finding, corrective artifact creation,
  and a final clean reviewer result.

The exact TP53 capture details, frame IDs, artifact checksums, and network
allowlist are in [`demo-capture.md`](demo-capture.md).

## Public Data Source

The demo uses public UCSC Xena TCGA-BRCA expression data:

- Dataset URL:
  `https://tcga.xenahubs.net/download/TCGA.BRCA.sampleMap/HiSeqV2.gz`
- TCGA Xena hub: <https://tcga.xenahubs.net/>
- TCGA Breast Cancer cohort page:
  <https://xenabrowser.net/datapages/?cohort=TCGA+Breast+Cancer+%28BRCA%29>

The demo prompt pinned the dataset URL so the GIF tests local model execution,
artifact creation, and reviewer recovery rather than data-discovery ability.

## Redacted Health Check Shape

`GET /healthz` is intended to be safe for issue reports. A representative shape
looks like this:

```json
{
  "ok": true,
  "provider": {
    "name": "mtplx",
    "base_url": "http://127.0.0.1:8030/v1",
    "model": "mtplx-qwen36-27b-optimized-quality",
    "http_referer_header_set": false,
    "app_title_header_set": false
  },
  "stream_mode": "buffered",
  "tool_mode": "pass",
  "request_shape_log_path": "<enabled:request-shape-capture.jsonl>",
  "raw_request_capture_dir": "",
  "harness_tools": ["submit_output"],
  "metrics": {
    "requests_total": 3,
    "messages_by_kind": {
      "plain": 1,
      "tool_agent": 1,
      "harness": 1
    },
    "messages_by_stream_mode": {
      "buffered": 3
    },
    "provider_latency_by_kind": {
      "plain": {
        "count": 1,
        "avg_ms": 1200.0,
        "last_ms": 1200.0,
        "max_ms": 1200.0
      }
    },
    "upstream_retries_by_status": {},
    "upstream_errors_by_status": {},
    "tool_filters_by_reason": {}
  }
}
```

The actual values will differ by provider, profile, and run. The important
property is that the metrics are operational counters and timings only.

## What It Does Not Prove

- This repo does not distribute Claude Science or bypass Claude Science beta
  access, sign-in, account entitlement, or organization settings.
- MTPLX/Qwen is a companion local setup, not bundled here. Public users can
  get MTPLX from <https://github.com/youssofal/MTPLX> or
  <https://mtplx.com/> and can reproduce the proxy path with Ollama or another
  OpenAI-compatible backend. The exact GIF path requires an equivalent local
  Qwen server and a model such as
  <https://huggingface.co/Youssofal/Qwen3.6-27B-MTPLX-Optimized-Quality>.
- A provider-only smoke test does not guarantee a full Claude Science workflow.
  The full app prompt is much larger and includes reviewer/harness traffic.
