#!/usr/bin/env python3
"""Сборка summary .list из merge-from в manifest (дедуп upstream-зеркал)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MergeSet:
    set_id: str
    file: str
    sources: list[str]
    exclude: str
    exclude_from: str


def parse_manifest(path: Path) -> list[MergeSet]:
    sets: list[MergeSet] = []
    cur: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("- id:"):
            if cur and cur.get("merge-from"):
                sets.append(_merge_set(cur))
            cur = {"id": s.split(":", 1)[1].strip()}
        elif cur and ":" in s and not s.startswith("#"):
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            if k in ("id", "file", "merge-from", "exclude", "exclude-from"):
                cur[k] = v
    if cur and cur.get("merge-from"):
        sets.append(_merge_set(cur))
    return sets


def _merge_set(cur: dict[str, str]) -> MergeSet:
    return MergeSet(
        cur["id"],
        cur["file"],
        [x.strip() for x in cur["merge-from"].split(",") if x.strip()],
        cur.get("exclude", ""),
        cur.get("exclude-from", ""),
    )


def apply_exclude_from(path: Path, text_dir: Path, exclude_from: str) -> None:
    names = [x.strip() for x in exclude_from.split(",") if x.strip()]
    if not names:
        return
    banned: set[str] = set()
    for name in names:
        src = text_dir / f"{name}.list"
        if not src.is_file():
            print(f"mrs-build-merged-lists: нет {src.name} для exclude-from", file=sys.stderr)
            raise SystemExit(1)
        for line in src.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if item and not item.startswith("#"):
                banned.add(item)
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line.strip() not in banned]
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    print(
        f"mrs-build-merged-lists: exclude-from {path.name}: {len(lines)} → {len(kept)} ({exclude_from})",
        file=sys.stderr,
    )


def apply_exclude(path: Path, exclude: str) -> None:
    if not exclude:
        return
    items = [x.strip() for x in exclude.split(",") if x.strip()]
    if not items:
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    removed = {*items}
    kept = [line for line in lines if line.strip() not in removed]
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    print(
        f"mrs-build-merged-lists: exclude {path.name}: {len(lines)} → {len(kept)} (убрано: {exclude})",
        file=sys.stderr,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build merged MRS list files from manifest merge-from")
    ap.add_argument("--mrs-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()

    text_dir = args.mrs_dir / "text"
    merge_py = Path(__file__).resolve().parent / "mrs-merge-lists.py"

    for info in parse_manifest(args.manifest):
        inputs = [text_dir / f"{name}.list" for name in info.sources]
        exclude_names = [x.strip() for x in info.exclude_from.split(",") if x.strip()]
        exclude_paths = [text_dir / f"{name}.list" for name in exclude_names]
        missing = [p for p in inputs + exclude_paths if not p.is_file()]
        if missing:
            print(
                f"mrs-build-merged-lists: нет {[p.name for p in missing]} для {info.file}",
                file=sys.stderr,
            )
            return 1
        out = text_dir / f"{info.file}.list"
        print(f"mrs-build-merged-lists: {info.file}.list ← {', '.join(info.sources)}")
        subprocess.run(
            [sys.executable, str(merge_py), "-o", str(out), *[str(p) for p in inputs]],
            check=True,
        )
        apply_exclude_from(out, text_dir, info.exclude_from)
        apply_exclude(out, info.exclude)

    return 0


if __name__ == "__main__":
    sys.exit(main())
