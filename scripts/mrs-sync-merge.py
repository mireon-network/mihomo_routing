#!/usr/bin/env python3
"""Зеркалирование upstream MRS: staging → text/. bin/ собирает mrs-tool pack.

Чужой .mrs не копируем: те же строки, другие байты, и check роняет весь sync.
Локальные правки — *-custom без url.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SetInfo:
    set_id: str
    behavior: str
    file: str
    has_upstream: bool


def parse_manifest(path: Path) -> list[SetInfo]:
    sets: list[SetInfo] = []
    cur: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("- id:"):
            if cur:
                sets.append(
                    SetInfo(
                        cur["id"],
                        cur["behavior"],
                        cur["file"],
                        bool(cur.get("url") or cur.get("src")),
                    )
                )
            cur = {"id": s.split(":", 1)[1].strip()}
        elif cur and ":" in s and not s.startswith("#"):
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            if k in ("id", "behavior", "file", "url", "src"):
                cur[k] = v
    if cur:
        sets.append(
            SetInfo(
                cur["id"],
                cur["behavior"],
                cur["file"],
                bool(cur.get("url") or cur.get("src")),
            )
        )
    return sets


def same_file(a: Path, b: Path) -> bool:
    if not a.is_file() or not b.is_file():
        return False
    return a.read_bytes() == b.read_bytes()


def apply_mirror(info: SetInfo, text_dir: Path, staging_text: Path) -> str:
    remote_list = staging_text / f"{info.file}.list"
    local_list = text_dir / f"{info.file}.list"
    if not remote_list.is_file():
        return "skipped_no_remote"
    if local_list.is_file() and same_file(local_list, remote_list):
        return "unchanged"
    local_list.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(remote_list, local_list)
    return "applied"


def main() -> int:
    ap = argparse.ArgumentParser(description="Зеркалирование upstream MRS из staging")
    ap.add_argument("--mrs-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    args = ap.parse_args()

    mrs_dir = args.mrs_dir.resolve()
    text_dir = mrs_dir / "text"
    staging_text = mrs_dir / ".sync-staging" / "text"

    text_dir.mkdir(parents=True, exist_ok=True)

    stats: dict[str, int] = {}
    for info in parse_manifest(args.manifest):
        if not info.has_upstream:
            stats["skipped_local"] = stats.get("skipped_local", 0) + 1
            print(f"{info.file}: skipped_local")
            continue
        result = apply_mirror(info, text_dir, staging_text)
        stats[result] = stats.get(result, 0) + 1
        print(f"{info.file}: {result}")

    print(
        "mrs-sync-merge:",
        ", ".join(f"{k}={v}" for k, v in sorted(stats.items())),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
