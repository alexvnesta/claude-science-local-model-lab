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
FONT_BIG = font(34, bold=True)
FONT_PATH = font(18)


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
    for x1, y1, x2, y2 in boxes:
        draw.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=8,
            outline=(100, 210, 255, 255),
            width=4,
        )

    return canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)


def make_contact(frames: list[Image.Image], output: Path) -> None:
    thumbs = [frame.convert("RGB").resize((320, 180), Image.Resampling.LANCZOS) for frame in frames]
    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 320, rows * 180), (22, 22, 22))
    draw = ImageDraw.Draw(sheet)
    for i, thumb in enumerate(thumbs):
        x = (i % cols) * 320
        y = (i // cols) * 180
        sheet.paste(thumb, (x, y))
        draw.text((x + 8, y + 8), f"frame {i + 1}", fill=(255, 255, 255), font=FONT_TAG)
    sheet.save(output)


def draw_source_frame() -> Image.Image:
    canvas = Image.new("RGB", OUT_SIZE, (18, 22, 27))
    draw = ImageDraw.Draw(canvas)

    screenshot_path = Path("docs/assets/tp53-notebook-source-1.png")
    if not screenshot_path.exists():
        raise SystemExit(f"Missing source screenshot: {screenshot_path}")

    source = Image.open(screenshot_path).convert("RGB")
    source_crop = source.crop((0, 0, source.width, min(source.height, 1040)))
    source_crop.thumbnail((565, 455), Image.Resampling.LANCZOS)
    source_x = 360
    source_y = 48
    draw.rounded_rectangle(
        (source_x - 10, source_y - 10, source_x + source_crop.width + 10, source_y + source_crop.height + 10),
        radius=12,
        fill=(255, 255, 255),
        outline=(100, 210, 255),
        width=4,
    )
    canvas.paste(source_crop, (source_x, source_y))

    draw.text((32, 62), "Source code", fill=(255, 255, 255), font=FONT_BIG)
    draw.text((32, 104), "available", fill=(255, 255, 255), font=FONT_BIG)

    body = (
        "The TP53 demo has a public Python notebook plus source screenshots "
        "checked into GitHub."
    )
    y = 172
    for line in textwrap.wrap(body, width=34):
        draw.text((34, y), line, fill=(218, 229, 236), font=FONT_BODY)
        y += 23

    draw.rounded_rectangle((32, 304, 318, 382), radius=10, fill=(5, 12, 18), outline=(100, 210, 255), width=2)
    draw.text((48, 323), "examples/", fill=(165, 205, 232), font=FONT_PATH)
    draw.text((48, 350), "tp53_brca_xena_analysis.ipynb", fill=(255, 255, 255), font=FONT_PATH)

    draw.rounded_rectangle((32, 414, 318, 492), radius=10, fill=(45, 70, 53), outline=(130, 210, 155), width=2)
    draw.text((48, 433), "Reproduce or inspect", fill=(245, 255, 248), font=FONT_PATH)
    draw.text((48, 460), "the analysis source", fill=(245, 255, 248), font=FONT_PATH)

    return canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)


def build(capture_dir: Path, output: Path, contact: Path | None) -> None:
    specs = [
        (
            "04_prompt_typed.png",
            "Local Qwen selected",
            "Claude Science is isolated on port 18765 and the model picker shows MTPLX Qwen 27B Local.",
            [(232, 378, 870, 523), (638, 486, 878, 523)],
        ),
        (
            "07_permission_card.png",
            "Python execution approval",
            "The app asks for local execution permission; the demo uses conversation-scoped approval.",
            [(178, 207, 862, 509), (188, 459, 314, 486)],
        ),
        (
            "09_after_download_wait.png",
            "Real TCGA data loaded",
            "Qwen downloads the Xena TCGA-BRCA matrix and extracts the TP53 row by barcode group.",
            [(182, 193, 858, 269)],
        ),
        (
            "current.png",
            "Reviewer catches the gap",
            "The reviewer flags missing deliverables, then Qwen self-corrects and starts the plotting step.",
            [(181, 234, 646, 267), (181, 287, 646, 319)],
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
            [(516, 129, 949, 470)],
        ),
    ]

    frames: list[Image.Image] = []
    for filename, title, body, boxes in specs:
        path = capture_dir / filename
        if not path.exists():
            raise SystemExit(f"Missing capture frame: {path}")
        frames.append(draw_callout(load_frame(path), title=title, body=body, boxes=boxes))
    frames.append(draw_source_frame())

    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=[1800, 1800, 1900, 2200, 2200, 3000, 3200],
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
