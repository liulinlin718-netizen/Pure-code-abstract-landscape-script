#!/usr/bin/env python3
"""Build the Python distributions and the standalone Agent Skill ZIP."""

from __future__ import annotations

import argparse
import configparser
import hashlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "photo-deconstruct-svg"
DIST_DIR = ROOT / "dist"
BUILD_FILES = (
    "README.md",
    "requirements.txt",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "MANIFEST.in",
)


def package_version() -> str:
    config = configparser.ConfigParser()
    config.read(ROOT / "setup.cfg", encoding="utf-8")
    return config["metadata"]["version"]


def copy_skill_bundle(destination: Path) -> Path:
    bundle = destination / "photo-deconstruct-svg"
    shutil.copytree(
        SKILL_DIR,
        bundle,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    shutil.copy2(ROOT / "requirements.txt", bundle / "requirements.txt")
    return bundle


def write_deterministic_zip(source: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source.parent).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def copy_build_tree(destination: Path) -> None:
    for filename in BUILD_FILES:
        shutil.copy2(ROOT / filename, destination / filename)
    shutil.copytree(
        SKILL_DIR,
        destination / SKILL_DIR.name,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def matching_artifacts(version: str) -> list[Path]:
    patterns = (
        f"photo-deconstruct-svg-{version}.zip",
        f"photo-deconstruct-svg-{version}.tar.gz",
        f"photo_deconstruct_svg-{version}-*.whl",
        "SHA256SUMS.txt",
    )
    return sorted({path for pattern in patterns for path in DIST_DIR.glob(pattern)})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace artifacts for the current package version",
    )
    args = parser.parse_args()

    version = package_version()
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    existing = matching_artifacts(version)
    if existing and not args.force:
        names = ", ".join(path.name for path in existing)
        raise SystemExit(f"Refusing to overwrite existing release artifacts: {names}")
    for path in existing:
        path.unlink()

    with tempfile.TemporaryDirectory(prefix="photo-deconstruct-release-") as temp_name:
        temporary = Path(temp_name)
        bundle = copy_skill_bundle(temporary / "bundle")
        zip_path = DIST_DIR / f"photo-deconstruct-svg-{version}.zip"
        write_deterministic_zip(bundle, zip_path)

        build_tree = temporary / "python-package"
        build_tree.mkdir()
        copy_build_tree(build_tree)
        subprocess.run(
            [
                sys.executable,
                "setup.py",
                "sdist",
                "--dist-dir",
                str(DIST_DIR),
                "bdist_wheel",
                "--dist-dir",
                str(DIST_DIR),
            ],
            cwd=build_tree,
            check=True,
        )

    artifacts = [
        path
        for path in matching_artifacts(version)
        if path.name != "SHA256SUMS.txt"
    ]
    checksum_path = DIST_DIR / "SHA256SUMS.txt"
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )
    for path in artifacts:
        print(path)
    print(checksum_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
