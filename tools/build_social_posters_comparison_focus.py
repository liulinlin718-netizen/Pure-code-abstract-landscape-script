#!/usr/bin/env python3
"""Build a comparison-first revision of the 3:4 Chinese social poster set."""

from __future__ import annotations

from pathlib import Path

import build_social_posters as base


OUTPUT = (
    base.ROOT
    / "tests"
    / "photo-deconstruct-svg"
    / "results"
    / "social-posters-comparison-focused-2026-08-27"
)


def comparison_pair(
    rows: dict[int, dict[str, str]],
    identifier: int,
    x: int,
    y: int,
    width: int,
    height: int,
    prefix: str,
    *,
    radius: int = 28,
    gap: int = 14,
    labels: bool = True,
) -> tuple[list[str], str]:
    half = (width - gap) // 2
    left_definition, left = base.image(
        base.asset(rows[identifier], "source"),
        x,
        y,
        half,
        height,
        prefix + "s",
        radius=radius,
    )
    right_x = x + half + gap
    right_definition, right = base.image(
        base.asset(rows[identifier], "preview"),
        right_x,
        y,
        half,
        height,
        prefix + "p",
        radius=radius,
    )
    label_markup = ""
    if labels:
        label_markup = f'''
          <rect x="{x + 28}" y="{y + 28}" width="150" height="66" rx="33" fill="#111417"/>
          <text x="{x + 103}" y="{y + 75}" text-anchor="middle" class="cn medium" font-size="34" fill="#FFFFFF">原图</text>
          <rect x="{right_x + 28}" y="{y + 28}" width="188" height="66" rx="33" fill="#DFFF32"/>
          <text x="{right_x + 122}" y="{y + 75}" text-anchor="middle" class="cn medium" font-size="34" fill="#111417">脚本结果</text>
        '''
    markup = f'''
      <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="#1B2024"/>
      {left}{right}{label_markup}
    '''
    return [left_definition, right_definition], markup


def page_one(rows: dict[int, dict[str, str]]) -> str:
    definitions, pair = comparison_pair(
        rows,
        4,
        0,
        0,
        2400,
        1990,
        "v2p1",
        radius=0,
        gap=10,
    )
    content = f'''
      {pair}
      <rect x="0" y="1230" width="2400" height="900" fill="url(#shade)"/>
      <circle cx="2090" cy="250" r="170" fill="#DFFF32"/>
      <text x="2090" y="270" text-anchor="middle" class="latin medium" font-size="46" fill="#111417">PURE</text>
      <text x="2090" y="334" text-anchor="middle" class="latin medium" font-size="46" fill="#111417">SCRIPT</text>
      <rect x="0" y="1900" width="2400" height="1300" fill="#111417"/>
      <text x="140" y="2110" class="cn medium" font-size="72" fill="#DFFF32">把最近很火的做图 Skill</text>
      <text x="130" y="2365" class="cn heavy" font-size="218" fill="#FFFFFF">提炼成</text>
      <rect x="120" y="2420" width="1570" height="286" rx="34" fill="#FF684D" transform="rotate(-2 120 2420)"/>
      <text x="190" y="2650" class="cn heavy" font-size="232" fill="#111417" transform="rotate(-2 190 2650)">一段脚本</text>
      <text x="140" y="2870" class="cn medium" font-size="68" fill="#FFFFFF">先看原图，再看它被重新组织。</text>
      <line x1="140" y1="2990" x2="2260" y2="2990" stroke="#4A5055" stroke-width="3"/>
      <text x="140" y="3110" class="latin medium" font-size="36" fill="#AEB7BE">SOURCE  /  PURE SCRIPT</text>
      <text x="2260" y="3110" text-anchor="end" class="cn medium" font-size="40" fill="#DFFF32">01 / 05</text>
    '''
    return base.svg_page(definitions, content, "#111417")


def page_two(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    cards: list[str] = []
    specs = (
        (10, 120, 710, "v2p2a", "山峦与色带"),
        (33, 120, 1490, "v2p2b", "主体与空间"),
        (17, 120, 2270, "v2p2c", "层次与远近"),
    )
    for identifier, x, y, prefix, caption in specs:
        pair_definitions, pair = comparison_pair(
            rows,
            identifier,
            x,
            y,
            2160,
            620,
            prefix,
            radius=30,
        )
        definitions.extend(pair_definitions)
        cards.append(
            pair
            + f'<text x="{x}" y="{y + 700}" class="cn medium" font-size="42" fill="#55524C">{caption}</text>'
        )
    content = f'''
      <rect x="0" y="0" width="2400" height="38" fill="#173BFF"/>
      <text x="120" y="220" class="latin medium" font-size="40" fill="#173BFF">COMPARE FIRST</text>
      <text x="110" y="480" class="cn heavy" font-size="184" fill="#111417">每一页，都先让原图说话。</text>
      <text x="120" y="610" class="cn medium" font-size="52" fill="#666158">对比不是附录，它就是这组海报的主角。</text>
      {''.join(cards)}
      <text x="2280" y="3100" text-anchor="end" class="cn medium" font-size="40" fill="#173BFF">02 / 05</text>
    '''
    return base.svg_page(definitions, content, "#F3EDDF")


def page_three(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    pair_a_definitions, pair_a = comparison_pair(
        rows, 15, 120, 960, 1020, 720, "v2p3a", radius=34
    )
    pair_b_definitions, pair_b = comparison_pair(
        rows, 23, 1260, 960, 1020, 720, "v2p3b", radius=34
    )
    pair_c_definitions, pair_c = comparison_pair(
        rows, 37, 420, 1900, 1560, 820, "v2p3c", radius=38
    )
    definitions.extend(pair_a_definitions + pair_b_definitions + pair_c_definitions)
    content = f'''
      <text x="130" y="230" class="latin medium" font-size="40" fill="#DFFF32">BEST BIG, OTHERS SMALL</text>
      <text x="120" y="520" class="cn heavy" font-size="184" fill="#FFFFFF">最像的，才值得放大。</text>
      <text x="120" y="730" class="cn heavy" font-size="150" fill="#FFFFFF">其他案例，缩小看稳定性。</text>
      <g transform="rotate(-2 630 1320)" filter="url(#shadow)">{pair_a}</g>
      <g transform="rotate(2 1770 1320)" filter="url(#shadow)">{pair_b}</g>
      <g transform="rotate(-1 1200 2310)" filter="url(#shadow)">{pair_c}</g>
      <circle cx="2100" cy="2160" r="168" fill="#FF684D"/>
      <text x="2100" y="2138" text-anchor="middle" class="cn heavy" font-size="68" fill="#111417">每张都要</text>
      <text x="2100" y="2230" text-anchor="middle" class="cn heavy" font-size="68" fill="#111417">经得起对比</text>
      <text x="120" y="3020" class="cn medium" font-size="58" fill="#DFFF32">相似度优先，画面感其次。</text>
      <text x="2280" y="3100" text-anchor="end" class="cn medium" font-size="40" fill="#FFFFFF">03 / 05</text>
    '''
    return base.svg_page(definitions, content, "#173BFF")


def page_four(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    cards: list[str] = []
    specs = (
        (6, 120, 820, "v2p4a"),
        (32, 1260, 820, "v2p4b"),
        (2, 120, 1710, "v2p4c"),
        (8, 1260, 1710, "v2p4d"),
    )
    for identifier, x, y, prefix in specs:
        pair_definitions, pair = comparison_pair(
            rows,
            identifier,
            x,
            y,
            1020,
            700,
            prefix,
            radius=30,
        )
        definitions.extend(pair_definitions)
        cards.append(pair)
    content = f'''
      <text x="120" y="220" class="latin medium" font-size="40" fill="#FF684D">SMALL CASES, SAME QUESTION</text>
      <text x="110" y="510" class="cn heavy" font-size="184" fill="#FFFFFF">不同照片，</text>
      <text x="110" y="710" class="cn heavy" font-size="184" fill="#FFFFFF">都放回原图旁边看。</text>
      {''.join(cards)}
      <line x1="120" y1="2570" x2="2280" y2="2570" stroke="#3A4148" stroke-width="4"/>
      <text x="120" y="2780" class="cn medium" font-size="62" fill="#FFFFFF">不靠单张“神图”，而是看它能不能连续成立。</text>
      <text x="120" y="2910" class="cn" font-size="46" fill="#AEB7BE">树、动物、云层、峡谷，都保留一张原图作为判断依据。</text>
      <text x="2280" y="3100" text-anchor="end" class="cn medium" font-size="40" fill="#DFFF32">04 / 05</text>
    '''
    return base.svg_page(definitions, content, "#111417")


def page_five(rows: dict[int, dict[str, str]]) -> str:
    definitions: list[str] = []
    cards: list[str] = []
    specs = (
        (4, 80, 80, "v2p5a"),
        (10, 1280, 80, "v2p5b"),
        (17, 80, 990, "v2p5c"),
        (33, 1280, 990, "v2p5d"),
        (23, 80, 2260, "v2p5e"),
        (37, 1280, 2260, "v2p5f"),
    )
    for identifier, x, y, prefix in specs:
        pair_definitions, pair = comparison_pair(
            rows,
            identifier,
            x,
            y,
            1040,
            650,
            prefix,
            radius=30,
            labels=False,
        )
        definitions.extend(pair_definitions)
        cards.append(pair)
    content = f'''
      {''.join(cards)}
      <rect x="420" y="700" width="1560" height="1760" rx="58" fill="#111417" filter="url(#shadow)"/>
      <text x="1200" y="970" text-anchor="middle" class="latin medium" font-size="42" fill="#DFFF32">40 PHOTOS LATER</text>
      <text x="1200" y="1250" text-anchor="middle" class="cn heavy" font-size="168" fill="#FFFFFF">跑完 40 张之后</text>
      <rect x="680" y="1380" width="1040" height="12" fill="#FF684D"/>
      <text x="1200" y="1670" text-anchor="middle" class="cn heavy" font-size="168" fill="#FFFFFF">每个结果旁边，</text>
      <text x="1200" y="1885" text-anchor="middle" class="cn heavy" font-size="168" fill="#DFFF32">都留着原图。</text>
      <text x="1200" y="2130" text-anchor="middle" class="cn heavy" font-size="202" fill="#FF684D">对比才有说服力</text>
      <text x="1200" y="2320" text-anchor="middle" class="cn medium" font-size="48" fill="#AEB7BE">好看是一部分，接近与稳定同样重要。</text>
      <text x="100" y="3070" class="latin medium" font-size="36" fill="#111417">SOURCE  /  PURE SCRIPT  /  REPEAT</text>
      <text x="2300" y="3070" text-anchor="end" class="cn medium" font-size="40" fill="#173BFF">05 / 05</text>
    '''
    return base.svg_page(definitions, content, "#F3EDDF")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = base.entries()
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
        base.render(svg, png)
        pngs.append(png)
    base.contact_sheet(pngs, OUTPUT / "poster-set-preview.jpg")
    (OUTPUT / "README.md").write_text(
        "# 对比优先版社媒海报\n\n"
        "5 页，3:4，2400×3200。封面保留旧版视觉体系，004 为唯一大幅案例；其余图片全部以中小尺寸原图/脚本对比卡展示。\n",
        encoding="utf-8",
    )
    print(OUTPUT / "poster-set-preview.jpg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
