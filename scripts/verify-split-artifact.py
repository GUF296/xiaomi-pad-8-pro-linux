#!/usr/bin/env python3
"""Verify available files from a checksum list shared across split artifacts.

A source run may publish one SHA256SUMS for the combined build tree and then
split that tree into separate Actions artifacts. Absent entries belong to the
other artifact; every present match is checked, and required inputs must be
covered by matching checksums.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path, PurePosixPath

LINE = re.compile(r"^([0-9a-fA-F]{64})[ \t]+\*?(.+)$")


def parts(name: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe checksum path: {name!r}")
    return tuple(p for p in path.parts if p != ".")


def suffix_match(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    n = min(len(a), len(b))
    return a[-n:] == b[-n:]


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="downloaded artifact directory")
    ap.add_argument("checksum_file", type=Path)
    ap.add_argument("required", nargs="+", type=Path)
    args = ap.parse_args()
    root = args.root.resolve(strict=True)
    manifest = args.checksum_file.resolve(strict=True)
    if not root.is_dir():
        raise SystemExit(f"artifact root is not a directory: {root}")
    files: dict[Path, tuple[str, ...]] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise SystemExit(f"artifact contains a symlink: {path}")
        if path.is_file() and path != manifest:
            files[path] = tuple(path.relative_to(root).parts)
    if not files:
        raise SystemExit(f"artifact is empty: {root}")
    required: set[Path] = set()
    for original in args.required:
        path = original.resolve()
        if path not in files:
            raise SystemExit(f"required file is outside artifact or missing: {original}")
        required.add(path)
    verified: set[Path] = set()
    skipped = 0
    entries = 0
    for line_no, line in enumerate(manifest.read_text().splitlines(), 1):
        if not line:
            continue
        match = LINE.fullmatch(line)
        if not match:
            raise SystemExit(f"malformed {manifest}:{line_no}")
        expected = match.group(1).lower()
        try:
            manifest_parts = parts(match.group(2))
        except ValueError as exc:
            raise SystemExit(f"{manifest}:{line_no}: {exc}") from exc
        entries += 1
        candidates = [path for path, rel in files.items()
                      if suffix_match(rel, manifest_parts)]
        if not candidates:
            skipped += 1
            continue
        if len(candidates) > 1:
            raise SystemExit(
                f"ambiguous checksum entry {match.group(2)!r}: "
                + ", ".join(map(str, candidates)))
        path = candidates[0]
        actual = digest(path)
        if actual != expected:
            raise SystemExit(f"SHA256 mismatch for {path}: {actual} != {expected}")
        verified.add(path)
        print(f"{path.relative_to(root)}: OK")
    if entries == 0:
        raise SystemExit(f"checksum file has no entries: {manifest}")
    missing = required - verified
    if missing:
        raise SystemExit("required files lack checksum coverage: "
                         + ", ".join(str(x.relative_to(root)) for x in sorted(missing)))
    print(f"verified {len(verified)} file(s); ignored {skipped} "
          "entry/entries absent from this split artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
