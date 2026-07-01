#!/usr/bin/env python3
"""Build an annotated TP53 Claude Science workflow GIF from captured frames."""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_SIZE = (960, 540)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_TITLE = font(24, bold=True)
FONT_BODY = font(15)
FONT_TAG = font(14, bold=True)


def load_frame(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    return image.resize(OUT_SIZE, Image.Resampling.LANCZOS)


def draw_callout(
    image: Image.Image,
    *,
    title: str,
    body: str,
    boxes: list[tuple[int, int, int, int]],
    label_xy: tuple[int, int] = (24, 24),
) -> Image.Image:
    canvas = image.convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # Header panel.
    x, y = label_xy
    wrapped = textwrap.wrap(body, width=56)
    header_h = 52 + (len(wrapped) * 18)
    draw.rounded_rectangle(
        (x, y, x + 520, y + header_h),
        radius=10,
        fill=(16, 18, 18, 230),
        outline=(100, 190, 255, 230),
        width=2,
    )
    draw.text((x + 16, y + 12), title, fill=(255, 255, 255, 255), font=FONT_TITLE)
    for i, line in enumerate(wrapped):
        draw.text((x + 16, y + 44 + i * 18), line, fill=(220, 230, 236, 255), font=FONT_BODY)

    # Highlight target regions.
    for idx, (x1, y1, x2, y2) in enumerate(boxes, start=1):
        draw.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=8,
            outline=(100, 210, 255, 255),
            width=4,
        )
        draw.rounded_rectangle((x1 + 6, y1 + 6, x1 + 32, y1 + 32), radius=8, fill=(100, 210, 255, 235))
        draw.text((x1 + 15, y1 + 9), str(idx), fill=(5, 20, 30, 255), font=FONT_TAG)

    return canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)


def make_contact(frames: list[Image.Image], output: Path) -> None:
    thumbs = [frame.convert("RGB").resize((320, 180), Image.Resampling.LANCZOS) for frame in frames]
    sheet = Image.new("RGB", (640, 540), (22, 22, 22))
    draw = ImageDraw.Draw(sheet)
    for i, thumb in enumerate(thumbs):
        x = (i % 2) * 320
        y = (i // 2) * 180
        sheet.paste(thumb, (x, y))
        draw.text((x + 8, y + 8), f"frame {i + 1}", fill=(255, 255, 255), font=FONT_TAG)
    sheet.save(output)


def build(capture_dir: Path, output: Path, contact: Path | None) -> None:
    specs = [
        (
            "04_prompt_typed.png",
            "Local Qwen selected",
            "Claude Science is isolated on port 18765 and the model picker shows MTPLX Qwen 27B Local.",
            [(388, 306, 915, 410), (660, 486, 875, 514)],
        ),
        (
            "07_permission_card.png",
            "Python execution approval",
            "The app asks for local execution permission; the demo uses conversation-scoped approval.",
            [(452, 224, 918, 507)],
        ),
        (
            "09_after_download_wait.png",
            "Real TCGA data loaded",
            "Qwen downloads the Xena TCGA-BRCA matrix and extracts the TP53 row by barcode group.",
            [(242, 126, 858, 205)],
        ),
        (
            "current.png",
            "Reviewer catches the gap",
            "The reviewer flags missing deliverables, then Qwen self-corrects and starts the plotting step.",
            [(240, 234, 860, 267), (240, 286, 860, 319)],
        ),
        (
            "10_final_review_state.png",
            "Artifacts saved",
            "Claude Science now has the PNG, markdown summary, and a clean final reviewer pass.",
            [(242, 160, 485, 323), (247, 380, 862, 410)],
        ),
        (
            "12_after_split_timeout_check.png",
            "Generated figure visible",
            "The saved TP53 figure opens in split view, showing tumor vs normal expression from TCGA-BRCA.",
            [(516, 44, 950, 530), (670, 486, 874, 514)],
        ),
    ]

    frames: list[Image.Image] = []
    for filename, title, body, boxes in specs:
        path = capture_dir / filename
        if not path.exists():
            raise SystemExit(f"Missing capture frame: {path}")
        frames.append(draw_callout(load_frame(path), title=title, body=body, boxes=boxes))

    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=[1800, 1800, 1900, 2200, 2200, 3000],
        loop=0,
        optimize=True,
        disposal=2,
    )
    if contact:
        make_contact(frames, contact)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-dir", type=Path, default=Path("/tmp/tp53-qwen-final-capture"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/assets/qwen-mtplx-tp53-workflow-demo.gif"),
    )
    parser.add_argument("--contact", type=Path)
    args = parser.parse_args()
    build(args.capture_dir, args.output, args.contact)


if __name__ == "__main__":
    main()
