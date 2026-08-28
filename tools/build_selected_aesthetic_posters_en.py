#!/usr/bin/env python3
"""Render an English edition of the finalized five-poster social set."""

from __future__ import annotations

import zipfile
from pathlib import Path

import build_selected_aesthetic_posters as zh


OUTPUT = (
    zh.base.ROOT
    / "tests"
    / "photo-deconstruct-svg"
    / "results"
    / "social-posters-merged-aesthetic-en-2026-08-28"
)

TRANSLATIONS = (
    ("全网很火的", "THE INTERNET'S"),
    ("风格化 Skill", "VIRAL STYLE SKILL"),
    ("被我写成了纯代码", "REBUILT IN PURE CODE"),
    ("不用 Token", "NO TOKEN"),
    ("也能一直做", "KEEP CREATING"),
    ("换照片", "NEW PHOTO"),
    ("继续跑", "RUN AGAIN"),
    ("把风格", "WRITE THE"),
    ("写进代码里", "STYLE INTO CODE"),
    ("不是 0 风格", "STILL HAS STYLE"),
    ("纯代码，", "PURE CODE"),
    ("也可以很有审美", "CAN HAVE GOOD TASTE"),
    ("纯代码做到这一步", "PURE CODE MADE IT THIS FAR"),
    ("你会给几分？", "HOW WOULD YOU RATE IT?"),
    ("原图", "BEFORE"),
    ("程序结果", "AFTER"),
)


def localize(document: str) -> str:
    localized = document.replace(
        '.latin { font-family: "Helvetica Neue", Arial, sans-serif; letter-spacing: 7px; }',
        '.latin { font-family: "Helvetica Neue", Arial, sans-serif; letter-spacing: 7px; }\n'
        '      .en { font-family: "Helvetica Neue", Arial, sans-serif; }',
    )
    localized = localized.replace('class="cn ', 'class="en ')
    for chinese, english in TRANSLATIONS:
        localized = localized.replace(chinese, english)
    localized = localized.replace(
        'font-size="182" fill="#DFFF45">STYLE INTO CODE',
        'font-size="160" fill="#DFFF45">STYLE INTO CODE',
    )
    return localized


def build_zip(pngs: list[Path], svgs: list[Path]) -> Path:
    destination = OUTPUT / "xiaohongshu-english-posters.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in [*pngs, *svgs, OUTPUT / "README.md", OUTPUT / "poster-set-preview.jpg"]:
            archive.write(path, path.name)
    return destination


def main() -> int:
    if not zh.RUN.is_dir():
        raise SystemExit(f"Missing source run: {zh.RUN}")
    if not zh.base.CHROME.is_file():
        raise SystemExit(f"Missing Chrome renderer: {zh.base.CHROME}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows = zh.entries()
    documents = tuple(
        localize(document)
        for document in (
            zh.page_one(rows),
            zh.page_two(rows),
            zh.page_three(rows),
            zh.page_four(rows),
            zh.page_five(rows),
        )
    )

    pngs: list[Path] = []
    svgs: list[Path] = []
    for index, document in enumerate(documents, start=1):
        svg = OUTPUT / f"poster-{index:02d}.svg"
        png = OUTPUT / f"poster-{index:02d}.png"
        svg.write_text(document, encoding="utf-8")
        zh.base.render(svg, png)
        svgs.append(svg)
        pngs.append(png)

    zh.base.contact_sheet(pngs, OUTPUT / "poster-set-preview.jpg")
    (OUTPUT / "README.md").write_text(
        "# English Xiaohongshu Poster Set\n\n"
        "Five posters, 3:4, 2400×3200. This edition mirrors the finalized Chinese set.\n\n"
        "All image selections, layouts, comparison pairs, and decorative elements are unchanged. "
        "Only the visible copy and comparison labels are localized into English.\n",
        encoding="utf-8",
    )
    archive = build_zip(pngs, svgs)
    print(OUTPUT / "poster-set-preview.jpg")
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
