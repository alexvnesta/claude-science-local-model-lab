"""Tests for the slim REdiscoverTE evaluation prompt contract."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "eval-prompts" / "recoverte" / "manifest.json"
CONTRACT = ROOT / "scripts" / "recoverte_eval_contract.py"


def load_contract():
    spec = importlib.util.spec_from_file_location("recoverte_eval_contract", CONTRACT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest_payload() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def prompt_by_id(prompt_id: str) -> dict:
    matches = [
        item for item in manifest_payload()["prompts"] if item.get("id") == prompt_id
    ]
    assert len(matches) == 1
    return matches[0]


def test_recoverte_manifest_validates_cleanly() -> None:
    result = subprocess.run(
        [sys.executable, str(CONTRACT)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["prompt_count"] == 2
    assert payload["failures"] == []


def test_prompt0_entries_are_model_supplied_capability_eligible_gates() -> None:
    prompts = manifest_payload()["prompts"]

    assert {item["id"] for item in prompts} == {
        "prompt0-paper-to-figure",
        "prompt0-natural-hypothesis-to-plot",
    }
    for item in prompts:
        assert item["route_supplied_by"] == "model"
        assert item["eligible_for_model_capability_if_clean"] is True
        assert item["strict_proxy_requirements"] == {
            "server_web_search": "off",
            "proxy_assisted_tool_calls": "fail",
            "tool_repair_or_filter_deltas": "fail",
        }


def test_natural_prompt_has_no_paper_or_route_leakage() -> None:
    contract = load_contract()
    entry = prompt_by_id("prompt0-natural-hypothesis-to-plot")
    text = contract.prompt_text(entry)

    assert "transposable element expression in breast cancer" in text
    assert contract.lint_prompt(entry, text) == []


def test_paper_prompt_names_study_but_not_exact_route() -> None:
    contract = load_contract()
    entry = prompt_by_id("prompt0-paper-to-figure")
    text = contract.prompt_text(entry)

    assert "Kong et al. 2019 Nature Communications" in text
    assert "10.1038/s41467-019-13035-2" in text
    assert contract.lint_prompt(entry, text) == []


def test_linter_rejects_route_leak_categories_without_private_answer_key() -> None:
    contract = load_contract()
    entry = prompt_by_id("prompt0-paper-to-figure")
    leaked_text = "\n".join(
        [
            "Download ExampleData_1.2.3.tar.gz from https://example.org/data/archive.tgz.",
            "Use staged/ExampleData_1.2.3.tar.gz and Fig2_data/table.RDS.",
            "Load the skill exact-route-helper and call archive_route_helper().",
            "Run score-example-route.py and save example_fig2_plot.png.",
        ]
    )

    labels = {failure["label"] for failure in contract.lint_prompt(entry, leaked_text)}

    assert "versioned data package filename" in labels
    assert "direct data URL" in labels
    assert "staged input path" in labels
    assert "figure data directory" in labels
    assert "R-native data object hint" in labels
    assert "exact skill instruction" in labels
    assert "snake-case helper call" in labels
    assert "scorer script name" in labels
    assert "exact figure artifact prefix" in labels


def test_natural_linter_rejects_paper_identity_categories() -> None:
    contract = load_contract()
    entry = prompt_by_id("prompt0-natural-hypothesis-to-plot")
    leaked_text = "Use Smith et al. and DOI 10.1234/example for this paper title."

    labels = {failure["label"] for failure in contract.lint_prompt(entry, leaked_text)}

    assert "paper author cue" in labels
    assert "paper DOI" in labels
    assert "paper identity cue" in labels


def test_prompt_artifact_contracts_are_named_in_prompt_text() -> None:
    contract = load_contract()
    for entry in manifest_payload()["prompts"]:
        text = contract.prompt_text(entry)
        for artifact in entry["required_artifacts"]:
            assert artifact in text


def test_classifier_downgrades_contaminated_or_incomplete_runs() -> None:
    contract = load_contract()
    paper_entry = prompt_by_id("prompt0-paper-to-figure")
    natural_entry = prompt_by_id("prompt0-natural-hypothesis-to-plot")

    assert contract.classify_evidence(
        paper_entry,
        artifact_gate_passed=True,
        positive_evidence_complete=True,
    ) == {
        "prompt_id": "prompt0-paper-to-figure",
        "evidence_class": "paper-to-figure",
        "counts_as_clean_model_capability": True,
        "counts_as_clean_model_figure_reproduction": True,
        "counts_as_clean_brca_subtype_plot": False,
    }
    assert contract.classify_evidence(
        natural_entry,
        artifact_gate_passed=True,
        positive_evidence_complete=True,
    )["counts_as_clean_brca_subtype_plot"] is True
    assert contract.classify_evidence(
        paper_entry,
        artifact_gate_passed=True,
        positive_evidence_complete=True,
        route_supplied_by_prompt=True,
    )["counts_as_clean_model_capability"] is False
    assert contract.classify_evidence(
        paper_entry,
        artifact_gate_passed=False,
        positive_evidence_complete=True,
    )["evidence_class"] == "artifact_gate_failed"
    assert contract.classify_evidence(
        paper_entry,
        artifact_gate_passed=True,
        positive_evidence_complete=False,
    )["evidence_class"] == "incomplete_positive_evidence"
