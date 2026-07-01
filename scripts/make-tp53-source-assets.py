#!/usr/bin/env python3
"""Create the public TP53 notebook and README screenshots."""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


NOTEBOOK_PATH = Path("examples/tp53_brca_xena_analysis.ipynb")
SHOT_1 = Path("docs/assets/tp53-notebook-source-1.png")
SHOT_2 = Path("docs/assets/tp53-notebook-source-2.png")


TITLE_MD = """# TP53 expression in TCGA-BRCA

This notebook is a public, reproducible version of the Claude Science local
Qwen demo. It downloads the TCGA-BRCA Xena expression matrix, extracts TP53,
compares primary tumor and normal samples, and writes the same plot/summary
artifact shape used in the demo GIF.
"""


SETUP_CODE = """from pathlib import Path
import urllib.request

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

URL = "https://tcga.xenahubs.net/download/TCGA.BRCA.sampleMap/HiSeqV2.gz"
DATA = Path("TCGA.BRCA.HiSeqV2.gz")

if not DATA.exists():
    urllib.request.urlretrieve(URL, DATA)

print(f"Matrix ready: {DATA} ({DATA.stat().st_size:,} bytes)")"""


EXTRACT_CODE = """expr = pd.read_csv(DATA, sep="\\t", low_memory=False)
tp53_row = expr.loc[expr["sample"].eq("TP53")].iloc[0]

samples = pd.Index(expr.columns[1:], name="sample")
values = pd.to_numeric(tp53_row.iloc[1:], errors="coerce")
sample_type = samples.to_series().str.split("-").str[3].str[:2]

tp53 = pd.DataFrame({
    "sample": samples,
    "TP53_log2_TPM_plus_1": values.to_numpy(),
    "sample_type": sample_type.to_numpy(),
}).dropna()

normal = tp53.loc[tp53["sample_type"].eq("11"), "TP53_log2_TPM_plus_1"]
tumor = tp53.loc[tp53["sample_type"].eq("01"), "TP53_log2_TPM_plus_1"]
welch = stats.ttest_ind(tumor, normal, equal_var=False)

summary = pd.DataFrame({
    "group": ["Normal (-11)", "Primary tumor (-01)"],
    "n": [len(normal), len(tumor)],
    "mean": [normal.mean(), tumor.mean()],
    "median": [normal.median(), tumor.median()],
    "sd": [normal.std(), tumor.std()],
})

delta = tumor.mean() - normal.mean()
summary"""


PLOT_CODE = """rng = np.random.default_rng(42)
fig, ax = plt.subplots(figsize=(7, 5.5))

bp = ax.boxplot(
    [normal, tumor],
    widths=0.4,
    patch_artist=True,
    labels=[f"Normal (n={len(normal)})", f"Primary tumor (n={len(tumor)})"],
    medianprops={"color": "#e41a1c", "linewidth": 2},
    boxprops={"edgecolor": "#333"},
    whiskerprops={"color": "#333"},
    capprops={"color": "#333"},
)
bp["boxes"][0].set_facecolor("#d8e8d8")
bp["boxes"][1].set_facecolor("#e8d8d8")

def jitter(x, n, scale=0.08):
    return x + rng.uniform(-scale, scale, size=n)

ax.scatter(jitter(1, len(normal)), normal, s=10, alpha=0.35, color="#2b8c3e")
ax.scatter(jitter(2, len(tumor)), tumor, s=10, alpha=0.35, color="#b22222")
ax.set_title("TP53 differential expression in TCGA-BRCA", weight="bold")
ax.set_ylabel("TP53 expression (log2 TPM + 1)")
ax.text(1.5, max(tumor.max(), normal.max()) - 0.15, f"Delta = {delta:+.02f}", ha="center")
ax.grid(axis="y", alpha=0.25)

fig.tight_layout()
fig.savefig("tp53_expression_plot.png", dpi=200)

summary_md = f\"\"\"# TP53 differential expression in TCGA-BRCA

- Normal samples: n={len(normal)}, mean={normal.mean():.4f}, median={normal.median():.4f}
- Primary tumor samples: n={len(tumor)}, mean={tumor.mean():.4f}, median={tumor.median():.4f}
- Mean difference, tumor - normal: {delta:+.4f}
- Welch t-test: t={welch.statistic:.3f}, p={welch.pvalue:.3g}

Interpretation: TP53 mRNA abundance is very similar between TCGA-BRCA
primary tumors and normal adjacent samples in this matrix.
\"\"\"
Path("tp53_summary.md").write_text(summary_md)
print("Wrote tp53_expression_plot.png and tp53_summary.md")"""


RESULT_TEXT = """Expected result from the demo run

Normal (-11): n=114, mean=10.4900, median=10.5713
Primary tumor (-01): n=1097, mean=10.5096, median=10.6358
Mean difference, tumor - normal: +0.0196
Welch t-test: t=0.323, p=0.747"""


def font(size: int, *, mono: bool = False, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if mono:
        candidates.extend(
            [
                "/System/Library/Fonts/Menlo.ttc",
                "/System/Library/Fonts/Supplemental/Courier New.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
        )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_TITLE = font(34, bold=True)
FONT_TEXT = font(22)
FONT_CODE = font(19, mono=True)
FONT_LABEL = font(18, bold=True)


def notebook() -> dict:
    cells = [
        {"cell_type": "markdown", "metadata": {}, "source": TITLE_MD.splitlines(keepends=True)},
        {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": SETUP_CODE.splitlines(keepends=True)},
        {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": EXTRACT_CODE.splitlines(keepends=True)},
        {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": PLOT_CODE.splitlines(keepends=True)},
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def wrap_code(source: str, width: int = 96) -> list[str]:
    wrapped: list[str] = []
    for line in source.splitlines():
        if not line:
            wrapped.append("")
            continue
        indent = len(line) - len(line.lstrip())
        prefix = " " * indent
        wrapped.extend(textwrap.wrap(line, width=width, subsequent_indent=prefix + "    ") or [""])
    return wrapped


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    lines: Iterable[str],
    x: int,
    y: int,
    *,
    code: bool = False,
    fill: tuple[int, int, int] = (30, 35, 40),
) -> int:
    active_font = FONT_CODE if code else FONT_TEXT
    line_h = 26 if code else 30
    for line in lines:
        draw.text((x, y), line, font=active_font, fill=fill)
        y += line_h
    return y


def draw_code_cell(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, label: str, source: str) -> int:
    lines = wrap_code(source)
    h = 46 + len(lines) * 26 + 24
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill=(247, 249, 252), outline=(210, 218, 226), width=2)
    draw.text((x + 18, y + 14), label, font=FONT_LABEL, fill=(88, 96, 105))
    draw.rounded_rectangle((x + 96, y + 12, x + w - 18, y + h - 16), radius=8, fill=(255, 255, 255), outline=(226, 232, 240))
    draw_text_block(draw, lines, x + 116, y + 28, code=True, fill=(24, 32, 42))
    return y + h + 24


def render_page(output: Path, title: str, cells: list[tuple[str, str]], result_text: str | None = None) -> None:
    width = 1400
    height = 126
    for _, source in cells:
        height += 46 + len(wrap_code(source)) * 26 + 24 + 24
    if result_text:
        height += 54 + len(result_text.splitlines()) * 30 + 24
    height += 34
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, width, 72), fill=(33, 38, 45))
    draw.text((34, 20), title, font=FONT_TITLE, fill=(255, 255, 255))
    y = 102

    for label, source in cells:
        y = draw_code_cell(draw, 42, y, 1316, label, source)

    if result_text:
        result_h = 54 + len(result_text.splitlines()) * 30
        draw.rounded_rectangle((42, y, 1358, y + result_h), radius=12, fill=(248, 250, 246), outline=(206, 222, 204), width=2)
        draw_text_block(draw, result_text.splitlines(), 70, y + 24, fill=(42, 72, 45))

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def build() -> None:
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_PATH.write_text(json.dumps(notebook(), indent=2) + "\n")
    render_page(SHOT_1, "TP53 TCGA-BRCA notebook source: data load", [("In [1]:", SETUP_CODE), ("In [2]:", EXTRACT_CODE)])
    render_page(SHOT_2, "TP53 TCGA-BRCA notebook source: plot + artifacts", [("In [3]:", PLOT_CODE)], RESULT_TEXT)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    build()


if __name__ == "__main__":
    main()
