"""Small helpers for public omics quick-look analyses."""


PUBLIC_OMICS_REFERENCE_DIR = ""


def public_omics_reference(name=None):
    """Return a bundled public-omics reference by short name.

    This gives Claude Science agents an executable way to load the same
    reference files named in SKILL.md when only the top-level skill text was
    injected into the conversation.
    """

    import os
    from pathlib import Path

    aliases = {
        "repetitive-elements": "repetitive-elements.md",
        "repeat": "repetitive-elements.md",
        "repeats": "repetitive-elements.md",
        "te": "repetitive-elements.md",
        "transposable-elements": "repetitive-elements.md",
        "tcga-xena": "tcga-xena.md",
        "tcga": "tcga-xena.md",
        "xena": "tcga-xena.md",
        "source-patterns": "source-patterns.md",
        "sources": "source-patterns.md",
    }
    if name is None:
        return {
            "available_references": sorted(set(aliases.values())),
            "aliases": sorted(aliases),
        }

    key = str(name).strip().lower().replace("_", "-")
    key = key.removesuffix(".md")
    filename = aliases.get(key, f"{key}.md")

    candidates = []
    installed_reference_dir = str(PUBLIC_OMICS_REFERENCE_DIR).strip()
    if installed_reference_dir and not installed_reference_dir.startswith("__"):
        candidates.append(Path(installed_reference_dir) / filename)

    file_value = globals().get("__file__")
    if file_value:
        candidates.append(Path(file_value).resolve().parent / "references" / filename)

    env_name = "PUBLIC_OMICS_REFERENCE_DIR"
    env_value = os.environ.get(env_name)
    if env_value:
        candidates.append(Path(env_value) / filename)

    seen = set()
    checked = []
    for candidate in candidates:
        text_path = str(candidate)
        if text_path in seen:
            continue
        seen.add(text_path)
        checked.append(text_path)
        if candidate.is_file():
            return {
                "name": key,
                "filename": filename,
                "path": text_path,
                "content": candidate.read_text(encoding="utf-8"),
            }

    return {
        "name": key,
        "filename": filename,
        "content": "",
        "error": "reference file not found",
        "checked_paths": checked[:20],
    }


def tcga_short_barcode(barcode, length=15):
    """Return a TCGA barcode prefix suitable for common sample-level joins."""
    if barcode is None:
        return None
    text = str(barcode).strip()
    if not text:
        return None
    return text[:length]


def tcga_participant_barcode(barcode):
    """Return the 12-character TCGA participant barcode."""
    return tcga_short_barcode(barcode, 12)


def tcga_sample_type(barcode):
    """Return the two-digit TCGA sample type code, such as 01 or 11."""
    if barcode is None:
        return None
    parts = str(barcode).strip().split("-")
    if len(parts) < 4 or len(parts[3]) < 2:
        return None
    return parts[3][:2]


def classify_repeat_feature(value):
    """Extract a repeat class/family hint from common repeat feature strings."""
    if value is None:
        return {"name": None, "class": None, "family": None}
    text = str(value).strip()
    if not text:
        return {"name": None, "class": None, "family": None}
    name = text
    rep_class = None
    rep_family = None
    if "#" in text:
        name, rest = text.split("#", 1)
        if "/" in rest:
            rep_class, rep_family = rest.split("/", 1)
        else:
            rep_class = rest
    elif "|" in text:
        parts = [part.strip() for part in text.split("|")]
        name = parts[0] if parts else text
        if len(parts) > 1:
            rep_class = parts[1]
        if len(parts) > 2:
            rep_family = parts[2]
    elif "/" in text:
        rep_class, rep_family = text.split("/", 1)
    return {
        "name": name.strip() if name is not None else None,
        "class": rep_class.strip().rstrip("?") if rep_class else None,
        "family": rep_family.strip().rstrip("?") if rep_family else None,
    }


def summarize_join(left_ids, right_ids):
    """Summarize overlap between two identifier collections before merging."""
    left = [str(item) for item in left_ids if item is not None and str(item) != ""]
    right = [str(item) for item in right_ids if item is not None and str(item) != ""]
    left_set = set(left)
    right_set = set(right)
    overlap = left_set & right_set
    return {
        "left_total": len(left),
        "right_total": len(right),
        "left_unique": len(left_set),
        "right_unique": len(right_set),
        "overlap_unique": len(overlap),
        "left_only_unique": len(left_set - right_set),
        "right_only_unique": len(right_set - left_set),
    }
