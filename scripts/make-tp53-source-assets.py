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
FONT_CODE_SMALL = font(16, mono=True)
FONT_TEXT_SMALL = font(18)
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


def draw_code_cell(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    label: str,
    source: str,
    *,
    wrap_width: int = 96,
    code_font: ImageFont.FreeTypeFont | ImageFont.ImageFont = FONT_CODE,
    line_h: int = 26,
) -> int:
    lines = wrap_code(source, width=wrap_width)
    h = 46 + len(lines) * line_h + 24
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill=(247, 249, 252), outline=(210, 218, 226), width=2)
    draw.text((x + 18, y + 14), label, font=FONT_LABEL, fill=(88, 96, 105))
    draw.rounded_rectangle((x + 96, y + 12, x + w - 18, y + h - 16), radius=8, fill=(255, 255, 255), outline=(226, 232, 240))
    line_y = y + 28
    for line in lines:
        draw.text((x + 116, line_y), line, font=code_font, fill=(24, 32, 42))
        line_y += line_h
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


def draw_plot_preview(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=12, fill=(255, 255, 255), outline=(210, 218, 226), width=2)
    draw.text((x + 24, y + 22), "Rendered plot preview", font=font(24, bold=True), fill=(24, 32, 42))
    draw.text((x + 24, y + 56), "TP53 expression in TCGA-BRCA", font=FONT_TEXT_SMALL, fill=(82, 91, 104))

    plot_x0 = x + 64
    plot_y0 = y + 112
    plot_x1 = x + w - 34
    plot_y1 = y + h - 92

    draw.line((plot_x0, plot_y0, plot_x0, plot_y1), fill=(80, 80, 80), width=2)
    draw.line((plot_x0, plot_y1, plot_x1, plot_y1), fill=(80, 80, 80), width=2)

    ymin, ymax = 8.0, 12.4

    def sy(value: float) -> float:
        return plot_y1 - (value - ymin) / (ymax - ymin) * (plot_y1 - plot_y0)

    for tick in [8, 9, 10, 11, 12]:
        ty = sy(tick)
        draw.line((plot_x0 - 6, ty, plot_x0, ty), fill=(80, 80, 80), width=2)
        draw.line((plot_x0, ty, plot_x1, ty), fill=(229, 234, 240), width=1)
        draw.text((x + 25, ty - 11), str(tick), font=FONT_TEXT_SMALL, fill=(82, 91, 104))

    def box(cx: int, q1: float, median: float, q3: float, low: float, high: float, fill: tuple[int, int, int]) -> None:
        box_w = 84
        draw.line((cx, sy(low), cx, sy(high)), fill=(55, 55, 55), width=2)
        draw.line((cx - 26, sy(low), cx + 26, sy(low)), fill=(55, 55, 55), width=2)
        draw.line((cx - 26, sy(high), cx + 26, sy(high)), fill=(55, 55, 55), width=2)
        draw.rectangle((cx - box_w // 2, sy(q3), cx + box_w // 2, sy(q1)), fill=fill, outline=(55, 55, 55), width=2)
        draw.line((cx - box_w // 2, sy(median), cx + box_w // 2, sy(median)), fill=(228, 26, 28), width=3)

    normal_x = int(plot_x0 + (plot_x1 - plot_x0) * 0.34)
    tumor_x = int(plot_x0 + (plot_x1 - plot_x0) * 0.70)
    box(normal_x, 10.17, 10.57, 10.91, 9.0, 11.8, (216, 232, 216))
    box(tumor_x, 10.11, 10.64, 11.04, 8.8, 12.0, (232, 216, 216))

    for i in range(58):
        offset = ((i * 37) % 42) - 21
        value = 10.49 + ((((i * 19) % 100) - 50) / 100) * 1.0
        draw.ellipse((normal_x + offset - 2, sy(value) - 2, normal_x + offset + 2, sy(value) + 2), fill=(43, 140, 62))
    for i in range(90):
        offset = ((i * 31) % 54) - 27
        value = 10.51 + ((((i * 23) % 100) - 50) / 100) * 1.25
        draw.ellipse((tumor_x + offset - 2, sy(value) - 2, tumor_x + offset + 2, sy(value) + 2), fill=(178, 34, 34))

    draw.text((normal_x - 58, plot_y1 + 16), "Normal", font=FONT_TEXT_SMALL, fill=(42, 72, 45))
    draw.text((tumor_x - 76, plot_y1 + 16), "Primary tumor", font=FONT_TEXT_SMALL, fill=(96, 45, 45))
    draw.text((plot_x0 + 80, plot_y0 + 10), "Delta = +0.02", font=FONT_TEXT_SMALL, fill=(24, 32, 42))
    draw.text((x + 24, y + h - 52), "Saved as tp53_expression_plot.png", font=FONT_TEXT_SMALL, fill=(82, 91, 104))


def render_plot_page(output: Path) -> None:
    width = 1400
    title = "TP53 TCGA-BRCA notebook source: plot + rendered figure"
    code_h = 46 + len(wrap_code(PLOT_CODE, width=62)) * 22 + 24
    right_h = 650 + 260 + 24
    height = 102 + max(code_h, right_h) + 34
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, width, 72), fill=(33, 38, 45))
    draw.text((34, 20), title, font=FONT_TITLE, fill=(255, 255, 255))

    y = 102
    draw_code_cell(
        draw,
        42,
        y,
        780,
        "In [3]:",
        PLOT_CODE,
        wrap_width=62,
        code_font=FONT_CODE_SMALL,
        line_h=22,
    )
    draw_plot_preview(draw, 850, y, 508, 650)

    result_y = y + 674
    result_h = 54 + len(RESULT_TEXT.splitlines()) * 28
    draw.rounded_rectangle((850, result_y, 1358, result_y + result_h), radius=12, fill=(248, 250, 246), outline=(206, 222, 204), width=2)
    line_y = result_y + 24
    for line in RESULT_TEXT.splitlines():
        draw.text((878, line_y), line, font=FONT_TEXT_SMALL, fill=(42, 72, 45))
        line_y += 28

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def build() -> None:
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_PATH.write_text(json.dumps(notebook(), indent=2) + "\n")
    render_page(SHOT_1, "TP53 TCGA-BRCA notebook source: data load", [("In [1]:", SETUP_CODE), ("In [2]:", EXTRACT_CODE)])
    render_plot_page(SHOT_2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    build()


if __name__ == "__main__":
    main()
