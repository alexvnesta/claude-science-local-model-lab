#!/usr/bin/env python3
"""Validate slim REdiscoverTE eval prompt contracts and evidence classes."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "eval-prompts" / "recoverte" / "manifest.json"

COMMON_ROUTE_LEAK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b[A-Za-z][A-Za-z0-9_-]*(?:data|paper)[_-]?"
            r"\d+\.\d+\.\d+(?:\.(?:tar\.gz|tgz|zip))?\b",
            re.I,
        ),
        "versioned data package filename",
    ),
    (re.compile(r"https?://[^\s<>)\]]+", re.I), "direct URL"),
    (re.compile(r"https?://\S+/(?:data|download|releases?)/\S+", re.I), "direct data URL"),
    (re.compile(r"\b(?:handoff|staged|inputs?)/[^\s]+", re.I), "staged input path"),
    (
        re.compile(
            r"(?:/Users/|/tmp/|/var/folders/|~/|(?:^|\s)_local/|(?:^|\s)\.cache/)[^\s]*",
            re.I,
        ),
        "local or cache path",
    ),
    (re.compile(r"\bFig(?:ure)?[0-9A-Za-z_-]*(?:_data|[-_/]data)/", re.I), "figure data directory"),
    (re.compile(r"\bFigure[_-]?[0-9A-Za-z]+\.Rmd\b", re.I), "figure script member"),
    (re.compile(r"\.(?:RDS|RData|rda)\b", re.I), "R-native data object hint"),
    (re.compile(r"\b[a-z][A-Za-z0-9]*_[A-Za-z0-9_]*\s*\(", re.I), "snake-case helper call"),
    (re.compile(r"\b(?:use|load)\s+(?:the\s+)?skill\s+\$?[A-Za-z0-9_-]+", re.I), "exact skill instruction"),
    (re.compile(r"\$[a-z][a-z0-9-]+\b", re.I), "explicit skill mention"),
    (re.compile(r"\bscore-[a-z0-9_-]+\.py\b", re.I), "scorer script name"),
    (re.compile(r"\b[a-z0-9]+_fig[0-9][a-z0-9_]*\b", re.I), "exact figure artifact prefix"),
)

NATURAL_EXTRA_LEAK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[A-Z][A-Za-z-]+\s+et\s+al\.?", re.I), "paper author cue"),
    (re.compile(r"\b10\.\d{4,9}/\S+", re.I), "paper DOI"),
    (re.compile(r"\b(?:paper|study|article)\s+(?:title|doi|authors?)\b", re.I), "paper identity cue"),
)

VALID_TASKS = {"paper_key_figure", "brca_subtype"}
VALID_LEAK_POLICIES = {"paper_natural", "natural"}
VALID_TIERS = {"paper-to-figure", "hypothesis-to-plot"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def prompt_text(entry: dict[str, Any], *, root: Path = ROOT) -> str:
    raw_file = entry.get("file")
    if not isinstance(raw_file, str) or not raw_file:
        raise ValueError(f"prompt {entry.get('id')!r} has no file")
    path = root / raw_file
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def leak_patterns_for(entry: dict[str, Any]) -> tuple[tuple[re.Pattern[str], str], ...]:
    leak_policy = entry.get("leak_policy")
    if leak_policy == "natural":
        return COMMON_ROUTE_LEAK_PATTERNS + NATURAL_EXTRA_LEAK_PATTERNS
    return COMMON_ROUTE_LEAK_PATTERNS


def lint_prompt(entry: dict[str, Any], text: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for pattern, label in leak_patterns_for(entry):
        for match in pattern.finditer(text):
            failures.append(
                {
                    "prompt_id": entry.get("id"),
                    "label": label,
                    "match": match.group(0),
                    "line": text.count("\n", 0, match.start()) + 1,
                }
            )
    return failures


def validate_entry(entry: dict[str, Any], *, root: Path = ROOT) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    prompt_id = entry.get("id")
    if not isinstance(prompt_id, str) or not prompt_id:
        failures.append({"prompt_id": prompt_id, "label": "missing prompt id"})
    if entry.get("task") not in VALID_TASKS:
        failures.append({"prompt_id": prompt_id, "label": "invalid task", "value": entry.get("task")})
    if entry.get("autonomy_tier") not in VALID_TIERS:
        failures.append(
            {"prompt_id": prompt_id, "label": "invalid autonomy tier", "value": entry.get("autonomy_tier")}
        )
    if entry.get("leak_policy") not in VALID_LEAK_POLICIES:
        failures.append(
            {"prompt_id": prompt_id, "label": "invalid leak policy", "value": entry.get("leak_policy")}
        )
    if entry.get("route_supplied_by") != "model":
        failures.append(
            {"prompt_id": prompt_id, "label": "route is not model supplied", "value": entry.get("route_supplied_by")}
        )
    if entry.get("eligible_for_model_capability_if_clean") is not True:
        failures.append({"prompt_id": prompt_id, "label": "prompt is not capability-eligible when clean"})
    artifacts = entry.get("required_artifacts")
    if not isinstance(artifacts, list) or not artifacts or any(not isinstance(item, str) for item in artifacts):
        failures.append({"prompt_id": prompt_id, "label": "required artifacts missing or invalid"})
    elif len(set(artifacts)) != len(artifacts):
        failures.append({"prompt_id": prompt_id, "label": "duplicate required artifact names"})
    strict = entry.get("strict_proxy_requirements")
    if not isinstance(strict, dict):
        failures.append({"prompt_id": prompt_id, "label": "strict proxy requirements missing"})
    else:
        if strict.get("server_web_search") != "off":
            failures.append({"prompt_id": prompt_id, "label": "server web search not disabled"})
        if strict.get("proxy_assisted_tool_calls") != "fail":
            failures.append({"prompt_id": prompt_id, "label": "proxy-assisted tool calls not fail-closed"})
        if strict.get("tool_repair_or_filter_deltas") != "fail":
            failures.append({"prompt_id": prompt_id, "label": "tool repair/filter deltas not fail-closed"})
    try:
        text = prompt_text(entry, root=root)
    except (OSError, ValueError) as exc:
        failures.append({"prompt_id": prompt_id, "label": "prompt file error", "error": str(exc)})
    else:
        failures.extend(lint_prompt(entry, text))
        for artifact in artifacts or []:
            if isinstance(artifact, str) and artifact not in text:
                failures.append(
                    {"prompt_id": prompt_id, "label": "required artifact not named in prompt", "artifact": artifact}
                )
    return failures


def validate_manifest(path: Path = DEFAULT_MANIFEST, *, root: Path = ROOT) -> dict[str, Any]:
    manifest = read_json(path)
    entries = manifest.get("prompts")
    failures: list[dict[str, Any]] = []
    if not isinstance(entries, list) or not entries:
        failures.append({"label": "manifest has no prompts"})
        entries = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append({"label": "prompt entry is not an object"})
            continue
        prompt_id = str(entry.get("id") or "")
        if prompt_id in seen:
            failures.append({"prompt_id": prompt_id, "label": "duplicate prompt id"})
        seen.add(prompt_id)
        failures.extend(validate_entry(entry, root=root))
    return {
        "passed": not failures,
        "manifest": str(path),
        "prompt_count": len(entries),
        "failures": failures,
    }


def classify_evidence(
    entry: dict[str, Any],
    *,
    artifact_gate_passed: bool,
    positive_evidence_complete: bool,
    proxy_assisted: bool = False,
    reviewer_assisted: bool = False,
    route_supplied_by_prompt: bool = False,
) -> dict[str, Any]:
    contaminated = proxy_assisted or reviewer_assisted or route_supplied_by_prompt
    prompt_capability = entry.get("eligible_for_model_capability_if_clean") is True
    clean_model_capability = bool(
        artifact_gate_passed
        and positive_evidence_complete
        and not contaminated
        and prompt_capability
        and entry.get("route_supplied_by") == "model"
    )
    if route_supplied_by_prompt:
        evidence_class = "known_route_or_prompt_supplied"
    elif reviewer_assisted:
        evidence_class = "reviewer_assisted_repair"
    elif proxy_assisted:
        evidence_class = "proxy_assisted_repair"
    elif not artifact_gate_passed:
        evidence_class = "artifact_gate_failed"
    elif not positive_evidence_complete:
        evidence_class = "incomplete_positive_evidence"
    else:
        evidence_class = str(entry.get("autonomy_tier"))
    return {
        "prompt_id": entry.get("id"),
        "evidence_class": evidence_class,
        "counts_as_clean_model_capability": clean_model_capability,
        "counts_as_clean_model_figure_reproduction": clean_model_capability
        and entry.get("task") == "paper_key_figure",
        "counts_as_clean_brca_subtype_plot": clean_model_capability
        and entry.get("task") == "brca_subtype",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_manifest(args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
