#!/usr/bin/env python3
"""Run every local test photograph through the current deterministic pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "tests" / "photo-deconstruct-svg" / "datasets"
DEFAULT_OUTPUT = (
    ROOT
    / "tests"
    / "photo-deconstruct-svg"
    / "results"
    / "full-rerun-2026-08-26"
)
DECONSTRUCT = ROOT / "photo-deconstruct-svg" / "scripts" / "deconstruct_photo.py"
VALIDATE = ROOT / "photo-deconstruct-svg" / "scripts" / "validate_svg.py"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
GROUPS = (
    ("testabstract-10", "Testabstract 10"),
    ("minimal-landscape-10", "Minimal landscape 10"),
    ("landscape-generalization-20", "Landscape generalization 20"),
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
PIPELINE_ARGS = (
    "--detail",
    "0.35",
    "--paper",
    "0.50",
    "--paper-style",
    "rough",
    "--paper-density",
    "1.00",
    "--grain-overlay",
    "0.34",
    "--gradient-strength",
    "0.30",
    "--color-mode",
    "source",
    "--curve-smoothing",
    "0.82",
    "--min-negative-gap",
    "0.018",
    "--palette-size",
    "6",
    "--max-shapes",
    "10",
    "--seed",
    "17",
)


@dataclass(frozen=True)
class RunItem:
    identifier: int
    group_slug: str
    group_label: str
    source: Path
    svg: Path
    analysis: Path
    preview: Path
    comparison: Path
    validation: str
    validation_failed_checks: tuple[str, ...]
    archetype: str
    shape_count: int
    elapsed_seconds: float


def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
        if bold
        else Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        if bold
        else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def source_images() -> list[tuple[str, str, Path]]:
    images: list[tuple[str, str, Path]] = []
    for group_slug, group_label in GROUPS:
        image_dir = DATASETS / group_slug / "images"
        group_images = sorted(
            path
            for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        images.extend((group_slug, group_label, path) for path in group_images)
    return images


def contain_on_surface(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    surface = Image.new("RGB", size, "#101010")
    contained = ImageOps.contain(image.convert("RGB"), size, Image.Resampling.LANCZOS)
    x = (size[0] - contained.width) // 2
    y = (size[1] - contained.height) // 2
    surface.paste(contained, (x, y))
    return surface


def make_comparison(
    source_path: Path,
    preview_path: Path,
    destination: Path,
    *,
    identifier: int,
    group_label: str,
) -> None:
    width = 2440
    height = 1010
    margin = 30
    title_height = 82
    footer_height = 70
    gap = 28
    panel_width = (width - margin * 2 - gap) // 2
    panel_height = height - title_height - footer_height - margin * 2
    canvas = Image.new("RGB", (width, height), "#0C0C0C")
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(32, bold=True)
    label_font = load_font(25, bold=True)
    detail_font = load_font(22)
    draw.text(
        (margin, 25),
        f"{identifier:03d}  {group_label}",
        font=title_font,
        fill="#F1F1F1",
    )
    draw.text(
        (width - margin, 30),
        source_path.name,
        font=detail_font,
        fill="#AFAFAF",
        anchor="ra",
    )
    with Image.open(source_path) as opened:
        source = contain_on_surface(
            ImageOps.exif_transpose(opened), (panel_width, panel_height)
        )
    with Image.open(preview_path) as opened:
        program = contain_on_surface(opened, (panel_width, panel_height))
    left_x = margin
    right_x = margin + panel_width + gap
    image_y = title_height
    canvas.paste(source, (left_x, image_y))
    canvas.paste(program, (right_x, image_y))
    draw.text(
        (left_x, height - footer_height + 18),
        "SOURCE",
        font=label_font,
        fill="#F1F1F1",
    )
    draw.text(
        (right_x, height - footer_height + 18),
        "PROGRAM — CURRENT PURE SCRIPT",
        font=label_font,
        fill="#F1F1F1",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "JPEG", quality=93, optimize=True, progressive=True)


def render_svg(svg: Path, preview: Path, dimensions: tuple[int, int]) -> None:
    if not CHROME.is_file():
        raise RuntimeError(f"Headless Chrome renderer not found: {CHROME}")
    width, height = dimensions
    rendering = subprocess.run(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={width},{height}",
            f"--screenshot={preview}",
            svg.as_uri(),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if rendering.returncode != 0 or not preview.is_file():
        raise RuntimeError(
            f"SVG preview rendering failed for {svg}:\n"
            f"{rendering.stdout}\n{rendering.stderr}"
        )


def make_contact_sheet(
    items: list[RunItem],
    destination: Path,
    *,
    title: str,
    columns: int = 2,
) -> None:
    tile_width = 1420
    tile_height = 640
    margin = 30
    header_height = 112
    rows = math.ceil(len(items) / columns)
    width = margin + columns * (tile_width + margin)
    height = header_height + rows * (tile_height + margin)
    canvas = Image.new("RGB", (width, height), "#0B0B0B")
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(38, bold=True)
    detail_font = load_font(22)
    draw.text((margin, 30), title, font=title_font, fill="#F1F1F1")
    draw.text(
        (width - margin, 38),
        f"{len(items)} source / program pairs",
        font=detail_font,
        fill="#AFAFAF",
        anchor="ra",
    )
    for index, item in enumerate(items):
        row, column = divmod(index, columns)
        x = margin + column * (tile_width + margin)
        y = header_height + row * (tile_height + margin)
        with Image.open(item.comparison) as opened:
            tile = ImageOps.contain(
                opened.convert("RGB"),
                (tile_width, tile_height),
                Image.Resampling.LANCZOS,
            )
        tile_surface = Image.new("RGB", (tile_width, tile_height), "#151515")
        tile_surface.paste(
            tile,
            ((tile_width - tile.width) // 2, (tile_height - tile.height) // 2),
        )
        canvas.paste(tile_surface, (x, y))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "JPEG", quality=91, optimize=True, progressive=True)


def run_one(
    output: Path,
    *,
    identifier: int,
    group_slug: str,
    group_label: str,
    source: Path,
) -> RunItem:
    stem = f"{identifier:03d}-{source.stem}"
    group_output = output / "outputs" / group_slug
    group_output.mkdir(parents=True, exist_ok=True)
    svg = group_output / f"{stem}.svg"
    analysis = group_output / f"{stem}.json"
    preview = group_output / f"{stem}.png"
    comparison = output / "comparisons" / f"{stem}-source-vs-program.jpg"

    started = time.monotonic()
    generation = subprocess.run(
        [
            sys.executable,
            str(DECONSTRUCT),
            str(source),
            str(svg),
            "--analysis-json",
            str(analysis),
            *PIPELINE_ARGS,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if generation.returncode != 0:
        raise RuntimeError(
            f"Generation failed for {source}:\n{generation.stdout}\n{generation.stderr}"
        )
    plan = json.loads(analysis.read_text(encoding="utf-8"))
    output_dimensions = tuple(int(value) for value in plan["output_dimensions"])
    render_svg(svg, preview, output_dimensions)
    validation_process = subprocess.run(
        [sys.executable, str(VALIDATE), str(svg), "--analysis", str(analysis)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    validation_report = json.loads(validation_process.stdout)
    failed_checks = tuple(
        key for key, passed in validation_report["checks"].items() if not passed
    )
    make_comparison(
        source,
        preview,
        comparison,
        identifier=identifier,
        group_label=group_label,
    )
    return RunItem(
        identifier=identifier,
        group_slug=group_slug,
        group_label=group_label,
        source=source,
        svg=svg,
        analysis=analysis,
        preview=preview,
        comparison=comparison,
        validation=validation_report["result"],
        validation_failed_checks=failed_checks,
        archetype=str(plan.get("archetype", "unknown")),
        shape_count=int(plan.get("large_shape_count", 0)),
        elapsed_seconds=time.monotonic() - started,
    )


def write_manifest(items: list[RunItem], output: Path) -> None:
    with (output / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "id",
                "dataset",
                "source",
                "svg",
                "analysis",
                "preview",
                "comparison",
                "validation",
                "failed_checks",
                "archetype",
                "shape_count",
                "elapsed_seconds",
            )
        )
        for item in items:
            writer.writerow(
                (
                    f"{item.identifier:03d}",
                    item.group_slug,
                    item.source.relative_to(ROOT).as_posix(),
                    item.svg.relative_to(output).as_posix(),
                    item.analysis.relative_to(output).as_posix(),
                    item.preview.relative_to(output).as_posix(),
                    item.comparison.relative_to(output).as_posix(),
                    item.validation,
                    ";".join(item.validation_failed_checks),
                    item.archetype,
                    item.shape_count,
                    f"{item.elapsed_seconds:.3f}",
                )
            )
    pass_count = sum(item.validation == "PASS" for item in items)
    (output / "README.md").write_text(
        "\n".join(
            (
                "# Full 40-image current-script rerun",
                "",
                f"Generated {len(items)} source/program pairs with one fixed parameter set; {pass_count}/{len(items)} SVG validations passed.",
                "No image-generation model, style transfer, manual tracing, or per-image tuning was used.",
                "",
                "## Parameters",
                "",
                "```text",
                " ".join(PIPELINE_ARGS),
                "```",
                "",
                "The complete comparison is `contact-sheets/00-all-40-source-vs-program.jpg`.",
                "Individual full-resolution pairs are in `comparisons/`.",
                "",
            )
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing run: {output}")
    output.mkdir(parents=True)

    sources = source_images()
    print(f"Running {len(sources)} source images with the current pure script", flush=True)
    items: list[RunItem] = []
    for identifier, (group_slug, group_label, source) in enumerate(sources, start=1):
        print(
            f"[{identifier:02d}/{len(sources)}] {group_slug}/{source.name}",
            flush=True,
        )
        items.append(
            run_one(
                output,
                identifier=identifier,
                group_slug=group_slug,
                group_label=group_label,
                source=source,
            )
        )

    contacts = output / "contact-sheets"
    make_contact_sheet(
        items,
        contacts / "00-all-40-source-vs-program.jpg",
        title="Photo Deconstruct SVG — all 40 current-script results",
    )
    for group_index, (group_slug, group_label) in enumerate(GROUPS, start=1):
        group_items = [item for item in items if item.group_slug == group_slug]
        make_contact_sheet(
            group_items,
            contacts / f"{group_index:02d}-{group_slug}-source-vs-program.jpg",
            title=group_label,
        )
    write_manifest(items, output)
    print(f"Complete comparison: {contacts / '00-all-40-source-vs-program.jpg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
