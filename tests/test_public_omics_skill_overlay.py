"""Tests for the tracked public-omics-analysis skill overlay."""

from __future__ import annotations

import importlib.util
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skill-overlays" / "public-omics-analysis"


def load_kernel():
    path = SKILL_DIR / "kernel.py"
    spec = importlib.util.spec_from_file_location("public_omics_kernel", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_omics_kernel_helpers() -> None:
    module = load_kernel()

    references = module.public_omics_reference()
    assert "repetitive-elements.md" in references["available_references"]
    repeat_reference = module.public_omics_reference("te")
    assert repeat_reference["filename"] == "repetitive-elements.md"
    assert "processed TE matrix" in repeat_reference["content"]
    lowered_reference = " ".join(repeat_reference["content"].lower().split())
    assert (
        "recount the samples from the current files every time"
        in lowered_reference
    )

    assert module.tcga_sample_type("TCGA-AB-1234-01A-01R") == "01"
    assert module.tcga_short_barcode("TCGA-AB-1234-01A-01R") == "TCGA-AB-1234-01"
    assert module.tcga_participant_barcode("TCGA-AB-1234-01A-01R") == "TCGA-AB-1234"
    assert module.classify_repeat_feature("L1HS#LINE/L1") == {
        "name": "L1HS",
        "class": "LINE",
        "family": "L1",
    }
    assert module.summarize_join(["a", "b", "b"], ["b", "c"]) == {
        "left_total": 3,
        "right_total": 2,
        "left_unique": 2,
        "right_unique": 2,
        "overlap_unique": 1,
        "left_only_unique": 1,
        "right_only_unique": 1,
    }

    tcga_reference = module.public_omics_reference("tcga")
    assert tcga_reference["filename"] == "tcga-xena.md"


def test_public_omics_reference_helper_avoids_local_app_state_rescue() -> None:
    kernel_text = (SKILL_DIR / "kernel.py").read_text(encoding="utf-8")

    assert "PUBLIC_OMICS_REFERENCE_DIR" in kernel_text
    assert "CLAUDE_SCIENCE_LOCAL_DATA_DIR" not in kernel_text
    assert "OPERON_DATA_DIR" not in kernel_text
    assert "orgs/*/skills" not in kernel_text
    assert "CLAUDE_SKILL_ROOT" not in kernel_text
    assert "SKILL_ROOT" not in kernel_text


def test_public_omics_kernel_avoids_reserved_sidecar_names() -> None:
    tree = ast.parse((SKILL_DIR / "kernel.py").read_text(encoding="utf-8"))
    reserved = []
    for node in tree.body:
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        for name in names:
            if name.startswith("_") and not name.startswith("__"):
                reserved.append((name, node.lineno))

    assert reserved == []


def test_public_omics_openai_metadata_matches_skill() -> None:
    metadata = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert 'display_name: "Public Omics Analysis"' in metadata
    assert 'short_description: "Public processed omics analysis"' in metadata
    assert "Use $public-omics-analysis" in metadata
    assert "processed public omics data route" in metadata


def test_repetitive_element_reference_uses_recounted_route_pattern() -> None:
    text = (
        SKILL_DIR / "references" / "repetitive-elements.md"
    ).read_text(encoding="utf-8")

    lowered = " ".join(text.lower().split())
    assert "recount the samples from the current files every time" in lowered


def test_public_omics_guides_bioconductor_setup_without_local_env_plumbing() -> None:
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    repeat_text = (
        SKILL_DIR / "references" / "repetitive-elements.md"
    ).read_text(encoding="utf-8")
    combined = "\n".join([skill_text, repeat_text])
    lowered = " ".join(combined.lower().split())

    assert "Biobase" in combined
    assert "BiocGenerics" in combined
    assert "available R/Bioconductor packages" in combined
    assert "keep setup bounded" in lowered
    assert "record the environment change in provenance" in lowered
    assert "making a synthetic te plot" in lowered
    assert "manage_packages" not in combined
    assert "shared `r` environment" not in lowered
    assert "OPERON" not in combined


def test_public_omics_prefers_te_reference_over_local_artifact_search() -> None:
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    lowered = " ".join(skill_text.lower().split())

    assert 'public_omics_reference("repetitive-elements")' in lowered
    assert "before generic cancer-portal queries or local artifact search" in lowered
    assert "local artifact search" in lowered
    assert "use local artifact search only when the user asks to reuse existing artifacts" in lowered
    assert "print or summarize the returned artifact names" in lowered


def test_public_omics_helper_calling_convention_avoids_host_kernel_api() -> None:
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    lowered = " ".join(skill_text.lower().split())

    assert "ordinary names inside the python tool cell" in lowered
    assert "host.skills" in lowered
    assert "import kernel" in lowered


def test_public_omics_description_matches_paper_to_plot_gate() -> None:
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill_text.split("---", 2)[1].lower()

    assert "public processed data" in frontmatter
    assert "author-provided figure data" in frontmatter
    assert "reproducible plot from a paper" in frontmatter
    assert "te/repeat dysregulation across cancer types" in frontmatter
    assert "before generic pdf-only" in frontmatter
    assert "processed public matrix" in frontmatter


def test_public_omics_prefers_paper_data_routes_over_scraping_packages() -> None:
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    lowered = " ".join(skill_text.lower().split())

    assert "data availability" in lowered
    assert "code availability" in lowered
    assert "author package or repository archives" in lowered
    assert "before broad pdf scans" in lowered
    assert "generic web scraping" in lowered
    assert "do not install generic web-scraping packages" in lowered
    assert "requests" in lowered
    assert "beautifulsoup4" in lowered
    assert "blocked provenance" in lowered
