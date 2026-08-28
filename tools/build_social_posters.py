#!/usr/bin/env python3
"""Build a five-page 3:4 Chinese social-poster set from selected comparisons."""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
RUN = (
    ROOT
    / "tests"
    / "photo-deconstruct-svg"
    / "results"
    / "full-rerun-internal-geometry-fix-2026-08-26"
)
OUTPUT = (
    ROOT
    / "tests"
    / "photo-deconstruct-svg"
    / "results"
    / "social-posters-2026-08-26"
)
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
WIDTH = 2400
HEIGHT = 3200


def entries() -> dict[int, dict[str, str]]:
    with (RUN / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        return {int(row["id"]): row for row in csv.DictReader(handle)}


def file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def asset(row: dict[str, str], kind: str) -> Path:
    return (ROOT / row[kind]) if kind == "source" else (RUN / row[kind])


def image(
    path: Path,
    x: int,
    y: int,
    width: int,
    height: int,
    clip_id: str,
    *,
    radius: int = 0,
    opacity: float = 1.0,
) -> tuple[str, str]:
    definition = (
        f'<clipPath id="{clip_id}"><rect x="{x}" y="{y}" width="{width}" '
        f'height="{height}" rx="{radius}"/></clipPath>'
    )
    markup = (
        f'<image href="{escape(file_uri(path))}" x="{x}" y="{y}" width="{width}" '
        f'height="{height}" preserveAspectRatio="xMidYMid slice" '
        f'clip-path="url(#{clip_id})" opacity="{opacity:.3f}"/>'
    )
    return definition, markup


def svg_page(definitions: list[str], content: str, background: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
  <defs>
    <style>
      .cn {{ font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; }}
      .latin {{ font-family: "Helvetica Neue", Arial, sans-serif; letter-spacing: 7px; }}
      .heavy {{ font-weight: 700; }}
      .medium {{ font-weight: 500; }}
    </style>
    <linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#111417" stop-opacity="0"/>
      <stop offset="0.64" stop-color="#111417" stop-opacity="0.10"/>
      <stop offset="1" stop-color="#111417" stop-opacity="0.96"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%">
      <feDropShadow dx="0" dy="28" stdDeviation="28" flood-color="#000000" flood-opacity="0.24"/>
    </filter>
    {''.join(definitions)}
  </defs>
  <rect width="2400" height="3200" fill="{background}"/>
  {content}
</svg>
'''


def page_one(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    clip, hero = image(asset(rows[4], "preview"), 0, 0, 2400, 2460, "p1hero")
    definitions.append(clip)
    content = f'''
      {hero}
      <rect x="0" y="0" width="2400" height="2520" fill="url(#shade)"/>
      <circle cx="2090" cy="330" r="170" fill="#DFFF32"/>
      <text x="2090" y="350" text-anchor="middle" class="latin medium" font-size="46" fill="#111417">PURE</text>
      <text x="2090" y="414" text-anchor="middle" class="latin medium" font-size="46" fill="#111417">SCRIPT</text>
      <text x="140" y="1860" class="cn medium" font-size="74" fill="#DFFF32">把最近很火的做图 Skill</text>
      <text x="130" y="2095" class="cn heavy" font-size="220" fill="#FFFFFF">提炼成</text>
      <rect x="120" y="2160" width="1570" height="290" rx="34" fill="#FF684D" transform="rotate(-2 120 2160)"/>
      <text x="190" y="2392" class="cn heavy" font-size="236" fill="#111417" transform="rotate(-2 190 2392)">一段脚本</text>
      <rect x="0" y="2460" width="2400" height="740" fill="#111417"/>
      <text x="140" y="2720" class="cn medium" font-size="86" fill="#FFFFFF">然后，效果比想象中更完整。</text>
      <line x1="140" y1="2865" x2="2260" y2="2865" stroke="#4A5055" stroke-width="3"/>
      <text x="140" y="3040" class="latin medium" font-size="40" fill="#AEB7BE">PHOTO  →  SCRIPT  →  VISUAL LANGUAGE</text>
      <text x="2260" y="3040" text-anchor="end" class="cn medium" font-size="40" fill="#DFFF32">01 / 05</text>
    '''
    return svg_page(definitions, content, "#111417")


def page_two(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    source_clip, source = image(asset(rows[33], "source"), 120, 970, 1050, 1470, "p2source", radius=34)
    program_clip, program = image(asset(rows[33], "preview"), 1230, 970, 1050, 1470, "p2program", radius=34)
    definitions.extend((source_clip, program_clip))
    content = f'''
      <rect x="0" y="0" width="2400" height="38" fill="#173BFF"/>
      <text x="120" y="270" class="latin medium" font-size="42" fill="#173BFF">ONE PHOTO, TWO ORDERS</text>
      <text x="110" y="570" class="cn heavy" font-size="210" fill="#111417">不是生图。</text>
      <text x="110" y="805" class="cn heavy" font-size="190" fill="#111417">是把风格写进脚本。</text>
      <rect x="1940" y="150" width="250" height="250" rx="125" fill="#FF684D"/>
      <text x="2065" y="305" text-anchor="middle" class="cn heavy" font-size="90" fill="#111417">对比</text>
      {source}
      {program}
      <rect x="150" y="1010" width="174" height="76" rx="38" fill="#111417"/>
      <text x="237" y="1064" text-anchor="middle" class="cn medium" font-size="38" fill="#FFFFFF">原图</text>
      <rect x="1260" y="1010" width="212" height="76" rx="38" fill="#DFFF32"/>
      <text x="1366" y="1064" text-anchor="middle" class="cn medium" font-size="38" fill="#111417">纯脚本</text>
      <path d="M 1185 1090 L 1215 1090 M 1200 1075 L 1200 1105" stroke="#173BFF" stroke-width="7"/>
      <text x="120" y="2665" class="cn medium" font-size="90" fill="#111417">同一画面，另一种组织方式。</text>
      <text x="120" y="2815" class="cn" font-size="50" fill="#55524C">照片还在，颜色和轮廓被重新安排。</text>
      <rect x="120" y="2990" width="1900" height="6" fill="#111417"/>
      <text x="2280" y="3020" text-anchor="end" class="cn medium" font-size="40" fill="#173BFF">02 / 05</text>
    '''
    return svg_page(definitions, content, "#F3EDDF")


def page_three(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    a_clip, a = image(asset(rows[8], "preview"), 170, 980, 1320, 910, "p3a", radius=40)
    b_clip, b = image(asset(rows[17], "preview"), 1060, 1700, 1150, 780, "p3b", radius=40)
    c_clip, c = image(asset(rows[15], "preview"), 170, 2080, 780, 900, "p3c", radius=40)
    definitions.extend((a_clip, b_clip, c_clip))
    content = f'''
      <text x="150" y="250" class="latin medium" font-size="42" fill="#DFFF32">A VISUAL LANGUAGE EMERGES</text>
      <text x="140" y="570" class="cn heavy" font-size="205" fill="#FFFFFF">一套脚本</text>
      <text x="140" y="800" class="cn heavy" font-size="174" fill="#FFFFFF">开始长出自己的视觉语言</text>
      <g transform="rotate(-3 830 1435)" filter="url(#shadow)">{a}</g>
      <g transform="rotate(4 1635 2090)" filter="url(#shadow)">{b}</g>
      <g transform="rotate(-4 560 2530)" filter="url(#shadow)">{c}</g>
      <circle cx="1930" cy="1110" r="250" fill="#FF684D"/>
      <text x="1930" y="1090" text-anchor="middle" class="cn heavy" font-size="96" fill="#111417">风格不是</text>
      <text x="1930" y="1210" text-anchor="middle" class="cn heavy" font-size="96" fill="#111417">贴上去的</text>
      <text x="130" y="3090" class="cn heavy" font-size="74" fill="#DFFF32">平滑</text>
      <text x="505" y="3090" class="cn heavy" font-size="74" fill="#FFFFFF">/</text>
      <text x="640" y="3090" class="cn heavy" font-size="74" fill="#DFFF32">克制</text>
      <text x="1015" y="3090" class="cn heavy" font-size="74" fill="#FFFFFF">/</text>
      <text x="1150" y="3090" class="cn heavy" font-size="74" fill="#DFFF32">有纸感</text>
      <text x="2260" y="3090" text-anchor="end" class="cn medium" font-size="40" fill="#FFFFFF">03 / 05</text>
    '''
    return svg_page(definitions, content, "#173BFF")


def page_four(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    placements = (
        (10, 770, "p4a"),
        (6, 1990, "p4b"),
    )
    panels: list[str] = []
    for identifier, y, prefix in placements:
        left_def, left = image(asset(rows[identifier], "source"), 120, y, 1030, 880, prefix + "s", radius=28)
        right_def, right = image(asset(rows[identifier], "preview"), 1250, y, 1030, 880, prefix + "p", radius=28)
        definitions.extend((left_def, right_def))
        panels.append(
            f'''{left}{right}
            <text x="155" y="{y + 78}" class="cn medium" font-size="36" fill="#FFFFFF">原图</text>
            <text x="1285" y="{y + 78}" class="cn medium" font-size="36" fill="#DFFF32">脚本结果</text>'''
        )
    content = f'''
      <text x="120" y="210" class="latin medium" font-size="42" fill="#FF684D">SAME SCRIPT, DIFFERENT SCENES</text>
      <text x="110" y="490" class="cn heavy" font-size="190" fill="#FFFFFF">换一张照片，</text>
      <text x="110" y="700" class="cn heavy" font-size="190" fill="#FFFFFF">它继续成立。</text>
      {''.join(panels)}
      <line x1="120" y1="1830" x2="2280" y2="1830" stroke="#3A4148" stroke-width="4"/>
      <circle cx="1200" cy="1830" r="70" fill="#FF684D"/>
      <path d="M1164 1830 H1236 M1200 1794 V1866" stroke="#111417" stroke-width="10"/>
      <text x="120" y="3010" class="cn medium" font-size="54" fill="#ABB5BC">山峦、树、天空、色块，都用同一套规则重新排布。</text>
      <text x="2280" y="3110" text-anchor="end" class="cn medium" font-size="40" fill="#DFFF32">04 / 05</text>
    '''
    return svg_page(definitions, content, "#111417")


def page_five(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    specs = (
        (2, 80, 100, 1040, 850, "p5a"),
        (4, 1280, 100, 1040, 850, "p5b"),
        (23, 80, 1040, 1040, 850, "p5c"),
        (37, 1280, 1040, 1040, 850, "p5d"),
        (10, 80, 1980, 1040, 850, "p5e"),
        (32, 1280, 1980, 1040, 850, "p5f"),
    )
    images: list[str] = []
    for identifier, x, y, width, height, clip_id in specs:
        definition, markup = image(
            asset(rows[identifier], "preview"),
            x,
            y,
            width,
            height,
            clip_id,
            radius=34,
        )
        definitions.append(definition)
        images.append(markup)
    content = f'''
      {''.join(images)}
      <rect x="450" y="730" width="1500" height="1760" rx="56" fill="#111417" filter="url(#shadow)"/>
      <text x="1200" y="980" text-anchor="middle" class="latin medium" font-size="42" fill="#DFFF32">40 PHOTOS LATER</text>
      <text x="1200" y="1250" text-anchor="middle" class="cn heavy" font-size="168" fill="#FFFFFF">跑完 40 张之后</text>
      <rect x="680" y="1390" width="1040" height="12" fill="#FF684D"/>
      <text x="1200" y="1680" text-anchor="middle" class="cn heavy" font-size="174" fill="#FFFFFF">它不只像滤镜。</text>
      <text x="1200" y="1900" text-anchor="middle" class="cn heavy" font-size="168" fill="#DFFF32">更像一套新的</text>
      <text x="1200" y="2115" text-anchor="middle" class="cn heavy" font-size="220" fill="#FF684D">视觉语法</text>
      <text x="1200" y="2310" text-anchor="middle" class="cn medium" font-size="50" fill="#AEB7BE">同一套脚本 · 不同的画面 · 连续成立</text>
      <text x="100" y="3040" class="latin medium" font-size="38" fill="#111417">PHOTO → PURE SCRIPT → POST</text>
      <text x="2300" y="3040" text-anchor="end" class="cn medium" font-size="40" fill="#173BFF">05 / 05</text>
    '''
    return svg_page(definitions, content, "#F3EDDF")


def render(svg: Path, png: Path) -> None:
    process = subprocess.run(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={WIDTH},{HEIGHT}",
            f"--screenshot={png}",
            svg.as_uri(),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if process.returncode != 0 or not png.is_file():
        raise RuntimeError(process.stdout + process.stderr)


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def contact_sheet(pages: list[Path], destination: Path) -> None:
    thumb_width = 600
    thumb_height = 800
    margin = 46
    header = 150
    canvas = Image.new("RGB", (thumb_width * 3 + margin * 4, thumb_height * 2 + margin * 3 + header), "#111417")
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 42), "社媒海报预览 · 3:4 · 2400×3200", font=load_font(46), fill="#FFFFFF")
    for index, page in enumerate(pages):
        with Image.open(page) as opened:
            thumb = opened.convert("RGB").resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        row, column = divmod(index, 3)
        x = margin + column * (thumb_width + margin)
        y = header + margin + row * (thumb_height + margin)
        canvas.paste(thumb, (x, y))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "JPEG", quality=94, optimize=True, progressive=True)


def main() -> int:
    if not RUN.is_dir():
        raise SystemExit(f"Missing full rerun: {RUN}")
    if not CHROME.is_file():
        raise SystemExit(f"Missing Chrome: {CHROME}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = entries()
    documents = (
        page_one(rows),
        page_two(rows),
        page_three(rows),
        page_four(rows),
        page_five(rows),
    )
    pngs: list[Path] = []
    for index, document in enumerate(documents, start=1):
        svg = OUTPUT / f"poster-{index:02d}.svg"
        png = OUTPUT / f"poster-{index:02d}.png"
        svg.write_text(document, encoding="utf-8")
        render(svg, png)
        pngs.append(png)
    contact_sheet(pngs, OUTPUT / "poster-set-preview.jpg")
    (OUTPUT / "README.md").write_text(
        "# 社媒海报组\n\n"
        "5 页，3:4，2400×3200，中文。PNG 可直接发社媒，SVG 可继续编辑。\n\n"
        "建议发布顺序：封面 → 原图/脚本对比 → 视觉语言 → 泛化对比 → 40 张总结。\n",
        encoding="utf-8",
    )
    print(OUTPUT / "poster-set-preview.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
