#!/usr/bin/env python3
"""Build six lively Xiaohongshu posters with unique source/result comparisons."""

from __future__ import annotations

import csv
import math
import zipfile
from pathlib import Path

import build_social_posters as base


RUN = (
    base.ROOT
    / "tests"
    / "photo-deconstruct-svg"
    / "results"
    / "full-rerun-micro-contour-2026-08-27"
)
OUTPUT = (
    base.ROOT
    / "tests"
    / "photo-deconstruct-svg"
    / "results"
    / "social-posters-merged-aesthetic-2026-08-27"
)
SELECTED = (4, 6, 8, 10, 15, 31, 33, 37)
PAGE_ASSIGNMENTS = ((4, 8), (6, 15), (10, 31), (33,), (37,))
base.RUN = RUN


def entries() -> dict[int, dict[str, str]]:
    with (RUN / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        rows = {int(row["id"]): row for row in csv.DictReader(handle)}
    missing = sorted(set(SELECTED) - set(rows))
    if missing:
        raise RuntimeError(f"Selected IDs are missing from the current run: {missing}")
    flattened = tuple(identifier for page in PAGE_ASSIGNMENTS for identifier in page)
    if len(flattened) != len(set(flattened)) or set(flattened) != set(SELECTED):
        raise RuntimeError("Every selected photo must appear on exactly one poster")
    return rows


def star(cx: float, cy: float, outer: float, inner: float, color: str) -> str:
    points: list[str] = []
    for index in range(16):
        angle = -math.pi / 2.0 + index * math.pi / 8.0
        radius = outer if index % 2 == 0 else inner
        points.append(f"{cx + math.cos(angle) * radius:.1f},{cy + math.sin(angle) * radius:.1f}")
    return f'<polygon points="{" ".join(points)}" fill="{color}"/>'


def pill(x: int, y: int, width: int, text: str, fill: str, color: str) -> str:
    return f'''
      <rect x="{x}" y="{y}" width="{width}" height="76" rx="38" fill="{fill}"/>
      <text x="{x + width / 2:.1f}" y="{y + 54}" text-anchor="middle" class="cn medium" font-size="38" fill="{color}">{text}</text>
    '''


def comparison_row(
    rows: dict[int, dict[str, str]],
    identifier: int,
    x: int,
    y: int,
    width: int,
    height: int,
    prefix: str,
    *,
    gap: int = 34,
    radius: int = 30,
    frame: str = "#F8F4EA",
    border: str = "#111417",
    result_label: str = "程序结果",
    source_angle: float = 0.0,
    result_angle: float = 0.0,
    source_dx: int = 0,
    source_dy: int = 0,
    result_dx: int = 0,
    result_dy: int = 0,
) -> tuple[list[str], str]:
    panel_width = (width - gap) // 2
    source_x = x + source_dx
    source_y = y + source_dy
    right_x = x + panel_width + gap + result_dx
    right_y = y + result_dy
    source_def, source = base.image(
        base.asset(rows[identifier], "source"), source_x, source_y, panel_width, height, prefix + "-source", radius=radius
    )
    result_def, result = base.image(
        base.asset(rows[identifier], "preview"), right_x, right_y, panel_width, height, prefix + "-result", radius=radius
    )
    source_cx = source_x + panel_width / 2
    source_cy = source_y + height / 2
    result_cx = right_x + panel_width / 2
    result_cy = right_y + height / 2
    markup = f'''
      <g transform="rotate({source_angle:.2f} {source_cx:.1f} {source_cy:.1f})">
        <rect x="{source_x - 14}" y="{source_y - 14}" width="{panel_width + 28}" height="{height + 28}" rx="{radius + 10}" fill="{frame}" filter="url(#shadow)"/>
        {source}
        <rect x="{source_x}" y="{source_y}" width="{panel_width}" height="{height}" rx="{radius}" fill="none" stroke="{border}" stroke-width="4"/>
        {pill(source_x + 24, source_y + 24, 150, "原图", "#111417", "#FFFFFF")}
      </g>
      <g transform="rotate({result_angle:.2f} {result_cx:.1f} {result_cy:.1f})">
        <rect x="{right_x - 14}" y="{right_y - 14}" width="{panel_width + 28}" height="{height + 28}" rx="{radius + 10}" fill="{frame}" filter="url(#shadow)"/>
        {result}
        <rect x="{right_x}" y="{right_y}" width="{panel_width}" height="{height}" rx="{radius}" fill="none" stroke="{border}" stroke-width="4"/>
        {pill(right_x + 24, right_y + 24, 220, result_label, "#DFFF45", "#111417")}
      </g>
    '''
    return [source_def, result_def], markup


def comparison_stack(
    rows: dict[int, dict[str, str]],
    identifier: int,
    x: int,
    y: int,
    width: int,
    image_height: int,
    prefix: str,
    *,
    gap: int = 58,
    radius: int = 28,
    frame: str = "#F8F4EA",
    border: str = "#111417",
    source_angle: float = 0.0,
    result_angle: float = 0.0,
    source_dx: int = 0,
    source_dy: int = 0,
    result_dx: int = 0,
    result_dy: int = 0,
) -> tuple[list[str], str]:
    source_x = x + source_dx
    source_y = y + source_dy
    result_x = x + result_dx
    result_y = y + image_height + gap + result_dy
    source_def, source = base.image(
        base.asset(rows[identifier], "source"), source_x, source_y, width, image_height, prefix + "-source", radius=radius
    )
    result_def, result = base.image(
        base.asset(rows[identifier], "preview"), result_x, result_y, width, image_height, prefix + "-result", radius=radius
    )
    source_cx = source_x + width / 2
    source_cy = source_y + image_height / 2
    result_cx = result_x + width / 2
    result_cy = result_y + image_height / 2
    markup = f'''
      <g transform="rotate({source_angle:.2f} {source_cx:.1f} {source_cy:.1f})">
        <rect x="{source_x - 14}" y="{source_y - 14}" width="{width + 28}" height="{image_height + 28}" rx="{radius + 10}" fill="{frame}" filter="url(#shadow)"/>
        {source}
        <rect x="{source_x}" y="{source_y}" width="{width}" height="{image_height}" rx="{radius}" fill="none" stroke="{border}" stroke-width="4"/>
        {pill(source_x + 22, source_y + 22, 150, "原图", "#111417", "#FFFFFF")}
      </g>
      <g transform="rotate({result_angle:.2f} {result_cx:.1f} {result_cy:.1f})">
        <rect x="{result_x - 14}" y="{result_y - 14}" width="{width + 28}" height="{image_height + 28}" rx="{radius + 10}" fill="{frame}" filter="url(#shadow)"/>
        {result}
        <rect x="{result_x}" y="{result_y}" width="{width}" height="{image_height}" rx="{radius}" fill="none" stroke="{border}" stroke-width="4"/>
        {pill(result_x + 22, result_y + 22, 220, "程序结果", "#DFFF45", "#111417")}
      </g>
    '''
    return [source_def, result_def], markup


def image_card(
    rows: dict[int, dict[str, str]],
    identifier: int,
    kind: str,
    x: int,
    y: int,
    width: int,
    height: int,
    prefix: str,
    *,
    angle: float,
    label: str,
    label_fill: str,
    label_color: str,
    frame: str = "#F8F4EA",
    border: str = "#111417",
    radius: int = 34,
) -> tuple[list[str], str]:
    definition, artwork = base.image(
        base.asset(rows[identifier], kind), x, y, width, height, prefix, radius=radius
    )
    cx = x + width / 2
    cy = y + height / 2
    markup = f'''
      <g transform="rotate({angle:.2f} {cx:.1f} {cy:.1f})">
        <rect x="{x - 16}" y="{y - 16}" width="{width + 32}" height="{height + 32}" rx="{radius + 10}" fill="{frame}" filter="url(#shadow)"/>
        {artwork}
        <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="none" stroke="{border}" stroke-width="5"/>
        {pill(x + 26, y + 26, 150 if kind == "source" else 220, label, label_fill, label_color)}
      </g>
    '''
    return [definition], markup


def split_comparison(
    rows: dict[int, dict[str, str]],
    identifier: int,
    x: int,
    y: int,
    width: int,
    height: int,
    prefix: str,
    *,
    radius: int = 42,
    border: str = "#9DEEFF",
) -> tuple[list[str], str]:
    source_def, source = base.image(
        base.asset(rows[identifier], "source"), x, y, width, height, prefix + "-source-image", radius=radius
    )
    result_def, result = base.image(
        base.asset(rows[identifier], "preview"), x, y, width, height, prefix + "-result-image", radius=radius
    )
    top_cut = x + width * 0.62
    bottom_cut = x + width * 0.38
    definitions = [
        source_def,
        result_def,
        f'<clipPath id="{prefix}-source-slice"><polygon points="{x},{y} {top_cut:.1f},{y} {bottom_cut:.1f},{y + height} {x},{y + height}"/></clipPath>',
        f'<clipPath id="{prefix}-result-slice"><polygon points="{top_cut:.1f},{y} {x + width},{y} {x + width},{y + height} {bottom_cut:.1f},{y + height}"/></clipPath>',
    ]
    markup = f'''
      <rect x="{x - 18}" y="{y - 18}" width="{width + 36}" height="{height + 36}" rx="{radius + 12}" fill="#F4EFE5" filter="url(#shadow)"/>
      <g clip-path="url(#{prefix}-source-slice)">{source}</g>
      <g clip-path="url(#{prefix}-result-slice)">{result}</g>
      <line x1="{top_cut:.1f}" y1="{y}" x2="{bottom_cut:.1f}" y2="{y + height}" stroke="#DFFF45" stroke-width="18"/>
      <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="none" stroke="{border}" stroke-width="6"/>
      {pill(x + 30, y + 30, 150, "原图", "#111417", "#FFFFFF")}
      {pill(x + width - 250, y + height - 106, 220, "程序结果", "#DFFF45", "#111417")}
    '''
    return definitions, markup


def page_one(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    d1, pair_one = comparison_row(
        rows,
        4,
        120,
        1050,
        2160,
        760,
        "p1-a",
        border="#111417",
        source_angle=-3.8,
        result_angle=4.0,
        source_dx=20,
        source_dy=35,
        result_dx=-20,
    )
    d2, pair_two = comparison_row(
        rows,
        8,
        120,
        2070,
        2160,
        760,
        "p1-b",
        border="#173BFF",
        source_angle=4.2,
        result_angle=-3.6,
        source_dx=-5,
        result_dx=-15,
        result_dy=30,
    )
    definitions.extend(d1 + d2)
    content = f'''
      <text x="120" y="150" class="latin medium" font-size="40" fill="#173BFF">TRENDING STYLE → REPEATABLE CODE</text>
      <text x="110" y="410" class="cn heavy" font-size="174" fill="#111417">全网很火的</text>
      <text x="110" y="610" class="cn heavy" font-size="174" fill="#111417">风格化 Skill</text>
      <text x="110" y="830" class="cn heavy" font-size="166" fill="#FF6B55">被我写成了纯代码</text>
      <circle cx="2090" cy="280" r="154" fill="#DFFF45"/>
      <text x="2090" y="270" text-anchor="middle" class="latin heavy" font-size="58" fill="#111417">0</text>
      <text x="2090" y="340" text-anchor="middle" class="latin heavy" font-size="46" fill="#111417">TOKEN</text>
      {pair_one}{pair_two}
      <path d="M 720 1940 C 940 1840, 1120 2025, 1360 1910 C 1530 1830, 1710 1870, 1840 1940" fill="none" stroke="#FF6B55" stroke-width="18" stroke-linecap="round"/>
      <circle cx="150" cy="3055" r="30" fill="#FF6B55"/>
      <circle cx="230" cy="3055" r="30" fill="#DFFF45"/>
      <circle cx="310" cy="3055" r="30" fill="#173BFF"/>
      <path d="M 470 3060 C 650 2950, 820 3160, 1010 3040 C 1150 2960, 1290 2990, 1410 3060" fill="none" stroke="#FF6B55" stroke-width="18" stroke-linecap="round"/>
    '''
    return base.svg_page(definitions, content, "#F4EFE5")


def page_two(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    d1, left = comparison_stack(
        rows,
        6,
        110,
        880,
        980,
        780,
        "p2-a",
        gap=78,
        border="#173BFF",
        source_angle=-4.5,
        result_angle=3.2,
        result_dx=60,
        result_dy=35,
    )
    d2, right = comparison_stack(
        rows,
        15,
        1310,
        880,
        980,
        780,
        "p2-b",
        gap=78,
        border="#173BFF",
        source_angle=4.0,
        result_angle=-3.8,
        source_dx=-20,
        source_dy=130,
        result_dx=-70,
        result_dy=-30,
    )
    definitions.extend(d1 + d2)
    content = f'''
      <text x="120" y="150" class="latin medium" font-size="40" fill="#111417">LOCAL SCRIPT · NO TOKEN PER RUN</text>
      <text x="110" y="430" class="cn heavy" font-size="178" fill="#111417">不用 Token</text>
      <text x="110" y="640" class="cn heavy" font-size="194" fill="#DFFF45">也能一直做</text>
      <circle cx="2080" cy="390" r="168" fill="#173BFF"/>
      <text x="2080" y="380" text-anchor="middle" class="cn heavy" font-size="60" fill="#FFFFFF">换照片</text>
      <text x="2080" y="460" text-anchor="middle" class="cn heavy" font-size="60" fill="#FFFFFF">继续跑</text>
      {left}{right}
      <path d="M 120 3060 C 310 2950, 500 3160, 700 3040 C 850 2950, 1020 2980, 1160 3060" fill="none" stroke="#173BFF" stroke-width="18" stroke-linecap="round"/>
      <circle cx="1280" cy="3050" r="28" fill="#111417"/>
      <circle cx="1360" cy="3050" r="28" fill="#DFFF45"/>
      {star(2180, 3010, 90, 32, "#DFFF45")}
    '''
    return base.svg_page(definitions, content, "#FF6B55")


def page_three(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    d1, pair_one = comparison_row(
        rows,
        10,
        120,
        830,
        2160,
        820,
        "p3-a",
        border="#9DEEFF",
        source_angle=-4.2,
        result_angle=2.8,
        source_dy=45,
        result_dx=-15,
        result_dy=-20,
    )
    d2, pair_two = comparison_row(
        rows,
        31,
        120,
        1980,
        2160,
        820,
        "p3-b",
        border="#9DEEFF",
        source_angle=3.3,
        result_angle=-4.4,
        source_dx=15,
        source_dy=-30,
        result_dx=-25,
        result_dy=30,
    )
    definitions.extend(d1 + d2)
    content = f'''
      <text x="120" y="145" class="latin medium" font-size="40" fill="#9DEEFF">STYLE RULES, WRITTEN ONCE</text>
      <text x="110" y="410" class="cn heavy" font-size="182" fill="#FFFFFF">把风格</text>
      <text x="110" y="625" class="cn heavy" font-size="182" fill="#DFFF45">写进代码里</text>
      <path d="M 1380 520 C 1570 410, 1770 650, 1970 520 C 2100 440, 2200 470, 2280 530" fill="none" stroke="#FF6B55" stroke-width="18" stroke-linecap="round"/>
      {pair_one}{pair_two}
      <circle cx="120" cy="3020" r="28" fill="#FF6B55"/>
      <circle cx="195" cy="3020" r="28" fill="#DFFF45"/>
      <circle cx="270" cy="3020" r="28" fill="#9DEEFF"/>
      <path d="M 1500 3030 C 1690 2920, 1840 3130, 2020 3020 C 2140 2950, 2220 2980, 2280 3030" fill="none" stroke="#FF6B55" stroke-width="18" stroke-linecap="round"/>
    '''
    return base.svg_page(definitions, content, "#062E38")


def page_four(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    d1, source = image_card(
        rows, 33, "source", 80, 900, 1290, 1660, "p5-source", angle=-5.2,
        label="原图", label_fill="#111417", label_color="#FFFFFF", border="#54234A"
    )
    d2, result = image_card(
        rows, 33, "preview", 1030, 1060, 1290, 1660, "p5-result", angle=5.0,
        label="程序结果", label_fill="#DFFF45", label_color="#111417", border="#54234A"
    )
    definitions.extend(d1 + d2)
    content = f'''
      <text x="120" y="145" class="latin medium" font-size="40" fill="#54234A">ZERO TOKEN, FULL VISUAL LANGUAGE</text>
      <text x="110" y="420" class="cn heavy" font-size="188" fill="#54234A">0 Token</text>
      <text x="110" y="635" class="cn heavy" font-size="180" fill="#F6F0E5">不是 0 风格</text>
      <circle cx="2080" cy="350" r="150" fill="#DFFF45"/>
      {star(2080, 350, 100, 36, "#FF6B55")}
      {source}{result}
      <path d="M 210 2700 C 540 2540, 770 2840, 1090 2680 C 1440 2500, 1790 2840, 2200 2640" fill="none" stroke="#54234A" stroke-width="18" stroke-linecap="round"/>
      <circle cx="950" cy="3020" r="28" fill="#54234A"/>
      <circle cx="1200" cy="3020" r="28" fill="#DFFF45"/>
      <circle cx="1450" cy="3020" r="28" fill="#FF6B55"/>
    '''
    return base.svg_page(definitions, content, "#F2A6C4")


def page_five(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    d1, comparison = comparison_row(
        rows,
        37,
        100,
        940,
        2200,
        720,
        "p5-merged-full",
        gap=40,
        radius=34,
        border="#9DEEFF",
        source_angle=-3.0,
        result_angle=3.0,
        source_dy=25,
        result_dy=-20,
    )
    definitions.extend(d1)
    content = f'''
      <text x="120" y="145" class="latin medium" font-size="40" fill="#9DEEFF">PURE CODE CAN STILL LOOK GOOD</text>
      <text x="110" y="430" class="cn heavy" font-size="170" fill="#FFFFFF">纯代码，</text>
      <text x="110" y="630" class="cn heavy" font-size="164" fill="#DFFF45">也可以很有审美</text>
      {comparison}
      <path d="M 580 1810 C 790 1690, 980 1900, 1190 1780 C 1390 1670, 1580 1870, 1810 1750" fill="none" stroke="#173BFF" stroke-width="18" stroke-linecap="round"/>
      <circle cx="1960" cy="1770" r="28" fill="#FF6B55"/>
      <circle cx="2040" cy="1770" r="28" fill="#DFFF45"/>
      <circle cx="2120" cy="1770" r="28" fill="#9DEEFF"/>
      <rect x="220" y="1980" width="1960" height="500" rx="70" fill="#F4EFE5"/>
      <text x="1200" y="2195" text-anchor="middle" class="cn heavy" font-size="104" fill="#111417">纯代码做到这一步</text>
      <text x="1200" y="2355" text-anchor="middle" class="cn heavy" font-size="112" fill="#FF6B55">你会给几分？</text>
      <path d="M 500 2700 C 760 2540, 980 2820, 1230 2670 C 1460 2530, 1690 2780, 1930 2640" fill="none" stroke="#173BFF" stroke-width="20" stroke-linecap="round"/>
      {star(2050, 2880, 118, 42, "#DFFF45")}
    '''
    return base.svg_page(definitions, content, "#111417")


def build_zip(pngs: list[Path], svgs: list[Path]) -> Path:
    destination = OUTPUT / "xiaohongshu-merged-comparison-posters.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [*pngs, *svgs, OUTPUT / "README.md", OUTPUT / "poster-set-preview.jpg"]:
            archive.write(path, path.name)
    return destination


def main() -> int:
    if not RUN.is_dir():
        raise SystemExit(f"Missing current full run: {RUN}")
    if not base.CHROME.is_file():
        raise SystemExit(f"Missing Chrome renderer: {base.CHROME}")
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
    svgs: list[Path] = []
    for index, document in enumerate(documents, start=1):
        svg = OUTPUT / f"poster-{index:02d}.svg"
        png = OUTPUT / f"poster-{index:02d}.png"
        svg.write_text(document, encoding="utf-8")
        base.render(svg, png)
        svgs.append(svg)
        pngs.append(png)
    base.contact_sheet(pngs, OUTPUT / "poster-set-preview.jpg")
    (OUTPUT / "README.md").write_text(
        "# 小红书前后对比海报组\n\n"
        "5 张，3:4，2400×3200。八个入选样本各出现一次，每个样本同时展示原图和程序结果。\n\n"
        "海报上不显示测试 ID 或页码，不重复使用任何样本。\n"
        "底部说明小字已全部改为抽象装饰；收尾页使用原最后一张山景。\n"
        "传播主线：热门风格化 Skill → 纯代码实现 → 0 Token 也能重复运行。\n",
        encoding="utf-8",
    )
    archive = build_zip(pngs, svgs)
    print(OUTPUT / "poster-set-preview.jpg")
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
