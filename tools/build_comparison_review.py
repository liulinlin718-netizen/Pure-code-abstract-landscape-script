#!/usr/bin/env python3
"""Collect existing comparison composites and build review contact sheets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import shutil
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "tests" / "photo-deconstruct-svg" / "results"
DEFAULT_OUTPUT = ROOT / "tests" / "photo-deconstruct-svg" / "social-media-review"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
COMPARISON_TERMS = (
    "comparison",
    "before-after",
    "old-vs",
    "source-vs",
    "source-old-new",
    "contact-sheet",
)
GROUPS = (
    ("early-development", "Early development", "development-history"),
    ("testabstract-evolution", "Testabstract evolution", "testabstract-10"),
    ("minimal-landscape", "Minimal landscape", "minimal-landscape-10"),
    (
        "landscape-generalization",
        "Landscape generalization",
        "landscape-generalization-20",
    ),
)


@dataclass(frozen=True)
class ReviewImage:
    identifier: int
    group_slug: str
    group_label: str
    source: Path
    collected: Path
    modified_at: datetime
    width: int
    height: int
    byte_size: int
    content_sha256: str
    duplicate_of: int | None


def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf") if bold else Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if bold else Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def group_for(path: Path) -> tuple[int, str, str] | None:
    relative_parts = path.relative_to(RESULTS).parts
    if not relative_parts:
        return None
    area = relative_parts[0]
    for index, (slug, label, directory) in enumerate(GROUPS):
        if area == directory:
            return index, slug, label
    return None


def is_comparison(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
        return False
    lower_name = path.name.lower()
    return path.parent.name == "comparisons" or any(
        term in lower_name for term in COMPARISON_TERMS
    )


def candidate_sources() -> list[tuple[str, str, Path, datetime]]:
    candidates: list[tuple[int, str, str, Path, datetime]] = []
    for path in RESULTS.rglob("*"):
        group = group_for(path)
        if group is None or not is_comparison(path):
            continue
        group_index, group_slug, group_label = group
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        candidates.append((group_index, group_slug, group_label, path, modified_at))
    candidates.sort(key=lambda item: (item[0], item[4], item[3].as_posix()))
    return [(slug, label, path, modified) for _, slug, label, path, modified in candidates]


def safe_name(identifier: int, group_slug: str, source: Path) -> str:
    return f"{identifier:03d}-{group_slug}-{source.name}"


def collect(output: Path) -> list[ReviewImage]:
    collected_dir = output / "all-comparisons"
    collected_dir.mkdir(parents=True)
    items: list[ReviewImage] = []
    first_by_hash: dict[str, int] = {}
    for identifier, (group_slug, group_label, source, modified_at) in enumerate(
        candidate_sources(), start=1
    ):
        destination = collected_dir / safe_name(identifier, group_slug, source)
        shutil.copy2(source, destination)
        with Image.open(destination) as opened:
            width, height = opened.size
        content_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
        duplicate_of = first_by_hash.get(content_sha256)
        first_by_hash.setdefault(content_sha256, identifier)
        items.append(
            ReviewImage(
                identifier=identifier,
                group_slug=group_slug,
                group_label=group_label,
                source=source,
                collected=destination,
                modified_at=modified_at,
                width=width,
                height=height,
                byte_size=destination.stat().st_size,
                content_sha256=content_sha256,
                duplicate_of=duplicate_of,
            )
        )
    return items


def draw_tile(
    item: ReviewImage,
    *,
    width: int,
    height: int,
    label_font: ImageFont.ImageFont,
    detail_font: ImageFont.ImageFont,
) -> Image.Image:
    tile = Image.new("RGB", (width, height), "#171717")
    draw = ImageDraw.Draw(tile)
    padding = 18
    label_height = 106
    image_box = (width - padding * 2, height - label_height - padding * 2)
    with Image.open(item.collected) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail(image_box, Image.Resampling.LANCZOS)
    image_x = (width - image.width) // 2
    image_y = padding + (image_box[1] - image.height) // 2
    draw.rectangle(
        (
            image_x - 1,
            image_y - 1,
            image_x + image.width,
            image_y + image.height,
        ),
        outline="#383838",
        width=1,
    )
    tile.paste(image, (image_x, image_y))
    label_y = height - label_height + 10
    draw.text(
        (padding, label_y),
        (
            f"{item.identifier:03d}  {item.group_label}"
            if item.duplicate_of is None
            else f"{item.identifier:03d}  Duplicate of {item.duplicate_of:03d}"
        ),
        font=label_font,
        fill="#F2F2F2",
    )
    display_name = textwrap.shorten(item.source.name, width=62, placeholder="…")
    draw.text(
        (padding, label_y + 42),
        display_name,
        font=detail_font,
        fill="#AFAFAF",
    )
    return tile


def build_sheet(
    items: list[ReviewImage],
    output: Path,
    *,
    title: str,
    columns: int,
    tile_width: int,
    tile_height: int,
) -> None:
    if not items:
        return
    margin = 28
    header_height = 112
    rows = math.ceil(len(items) / columns)
    canvas_width = margin + columns * (tile_width + margin)
    canvas_height = header_height + rows * (tile_height + margin)
    canvas = Image.new("RGB", (canvas_width, canvas_height), "#0D0D0D")
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(38, bold=True)
    label_font = load_font(27, bold=True)
    detail_font = load_font(21)
    draw.text((margin, 28), title, font=title_font, fill="#F2F2F2")
    draw.text(
        (canvas_width - margin, 36),
        f"{len(items)} comparisons",
        font=detail_font,
        fill="#AFAFAF",
        anchor="ra",
    )
    for index, item in enumerate(items):
        row, column = divmod(index, columns)
        x = margin + column * (tile_width + margin)
        y = header_height + row * (tile_height + margin)
        tile = draw_tile(
            item,
            width=tile_width,
            height=tile_height,
            label_font=label_font,
            detail_font=detail_font,
        )
        canvas.paste(tile, (x, y))
    canvas.save(output, "JPEG", quality=91, optimize=True, progressive=True)


def write_manifest(items: list[ReviewImage], output: Path) -> None:
    manifest = output / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "id",
                "group",
                "modified_at",
                "source_path",
                "collected_file",
                "width",
                "height",
                "bytes",
                "sha256",
                "duplicate_of",
            )
        )
        for item in items:
            writer.writerow(
                (
                    f"{item.identifier:03d}",
                    item.group_slug,
                    item.modified_at.isoformat(timespec="seconds"),
                    item.source.relative_to(ROOT).as_posix(),
                    item.collected.relative_to(output).as_posix(),
                    item.width,
                    item.height,
                    item.byte_size,
                    item.content_sha256,
                    f"{item.duplicate_of:03d}" if item.duplicate_of else "",
                )
            )

    group_counts = {
        slug: sum(item.group_slug == slug for item in items) for slug, _, _ in GROUPS
    }
    unique_count = sum(item.duplicate_of is None for item in items)
    readme = output / "README.md"
    readme.write_text(
        "\n".join(
            (
                "# Social media comparison review",
                "",
                f"Collected {len(items)} existing comparison composites without modifying their originals.",
                f"There are {unique_count} byte-unique images; exact duplicate files remain in the full collection and are marked in the manifest.",
                "The numeric ID is stable across the copied image, contact sheets, and `manifest.csv`.",
                "",
                "## Groups",
                "",
                *(f"- `{slug}`: {group_counts[slug]} images" for slug, _, _ in GROUPS),
                "",
                "## Selection workflow",
                "",
                "Start with `contact-sheets/00-unique-comparisons.jpg`, then record the IDs you want in `shortlist/SELECTED-IDS.txt`.",
                "Use `contact-sheets/00-all-comparisons.jpg` when you need to audit every historical filename, including exact duplicates.",
                "The full-resolution copies are in `all-comparisons/`.",
                "",
            )
        ),
        encoding="utf-8",
    )
    shortlist = output / "shortlist"
    shortlist.mkdir()
    (shortlist / "SELECTED-IDS.txt").write_text(
        "# Add one selected three-digit ID per line, for example:\n# 003\n# 027\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing review directory: {output}")
    output.mkdir(parents=True)

    items = collect(output)
    if not items:
        raise SystemExit(f"No comparison images found under {RESULTS}")
    sheets = output / "contact-sheets"
    sheets.mkdir()
    build_sheet(
        items,
        sheets / "00-all-comparisons.jpg",
        title="Photo Deconstruct SVG — all comparisons",
        columns=3,
        tile_width=900,
        tile_height=620,
    )
    build_sheet(
        [item for item in items if item.duplicate_of is None],
        sheets / "00-unique-comparisons.jpg",
        title="Photo Deconstruct SVG — unique comparisons",
        columns=3,
        tile_width=900,
        tile_height=620,
    )
    for group_index, (group_slug, group_label, _) in enumerate(GROUPS, start=1):
        group_items = [item for item in items if item.group_slug == group_slug]
        build_sheet(
            group_items,
            sheets / f"{group_index:02d}-{group_slug}.jpg",
            title=group_label,
            columns=2,
            tile_width=1300,
            tile_height=820,
        )
    write_manifest(items, output)
    print(f"Collected {len(items)} comparison images into {output}")
    for sheet in sorted(sheets.glob("*.jpg")):
        print(sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
