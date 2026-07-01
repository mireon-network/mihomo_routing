#!/usr/bin/env python3
"""Слияние upstream MRS (staging) с локальным text/ без перетирания правок."""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
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


def write_conflict_bundle(
    conflicts_dir: Path,
    name: str,
    local: Path | None,
    remote: Path,
    baseline: Path | None,
) -> None:
    bundle = conflicts_dir / name
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    if baseline and baseline.is_file():
        shutil.copy2(baseline, bundle / "baseline.list")
    if local and local.is_file():
        shutil.copy2(local, bundle / "local.list")
    shutil.copy2(remote, bundle / "remote.list")


def merge_one(
    info: SetInfo,
    text_dir: Path,
    baseline_dir: Path,
    staging_text: Path,
    staging_bin: Path,
    bin_dir: Path,
    conflicts_dir: Path,
) -> str:
    """Возвращает: applied | kept_local | unchanged | conflict | skipped_no_remote"""
    local = text_dir / f"{info.file}.list"
    remote = staging_text / f"{info.file}.list"
    base = baseline_dir / f"{info.file}.list"
    out_bin = bin_dir / f"{info.file}.mrs"
    st_bin = staging_bin / f"{info.file}.mrs"

    if not remote.is_file():
        return "skipped_no_remote"

    has_local = local.is_file()
    has_base = base.is_file()

    if not has_local:
        shutil.copy2(remote, local)
        shutil.copy2(remote, base)
        if st_bin.is_file():
            shutil.copy2(st_bin, out_bin)
        return "applied"

    if not has_base:
        if same_file(local, remote):
            shutil.copy2(remote, base)
            if st_bin.is_file():
                shutil.copy2(st_bin, out_bin)
            return "unchanged"
        write_conflict_bundle(conflicts_dir, info.file, local, remote, None)
        return "conflict"

    loc_eq_rem = same_file(local, remote)
    loc_eq_base = same_file(local, base)
    rem_eq_base = same_file(remote, base)

    if loc_eq_rem:
        shutil.copy2(remote, base)
        if st_bin.is_file():
            shutil.copy2(st_bin, out_bin)
        return "unchanged"

    if loc_eq_base and not rem_eq_base:
        shutil.copy2(remote, local)
        shutil.copy2(remote, base)
        if st_bin.is_file():
            shutil.copy2(st_bin, out_bin)
        return "applied"

    if not loc_eq_base and rem_eq_base:
        return "kept_local"

    write_conflict_bundle(conflicts_dir, info.file, local, remote, base)
    return "conflict"


def write_conflicts_report(
    report: Path,
    conflicts: list[SetInfo],
    mrs_dir: Path,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Конфликты синхронизации MRS",
        "",
        f"Обновлено: {ts}",
        "",
        "Команда `./scripts/mrs-tool.sh sync` **не перезаписала** локальные файлы "
        "в `text/`, потому что и upstream, и ваши правки изменили один и тот же набор.",
        "",
        "## Что сделать",
        "",
        "1. Для каждого набора ниже откройте каталог в `conflicts/<имя>/`:",
        "   - `baseline.list` — состояние при последней успешной синхронизации;",
        "   - `local.list` — ваш текущий `text/<имя>.list`;",
        "   - `remote.list` — новая версия с CDN/upstream.",
        "2. Вручную соберите итог в `text/<имя>.list`.",
        "3. Удалите каталог этого набора из `conflicts/`.",
        "4. Запустите `./scripts/mrs-tool.sh pack` (или сделайте коммит — pre-commit упакует).",
        "5. Повторите `./scripts/mrs-tool.sh sync` — после разрешения обновится `/.sync-baseline/`.",
        "",
        "Когда все конфликты сняты, удалите этот файл.",
        "",
        "## Наборы с конфликтами",
        "",
    ]
    for s in conflicts:
        lines.append(f"- `{s.file}` (`{s.set_id}`) → `{mrs_dir / 'conflicts' / s.file}/`")
    lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")


def cmd_resolve(mrs_dir: Path, manifest: Path, names: list[str]) -> int:
    text_dir = mrs_dir / "text"
    baseline_dir = mrs_dir / ".sync-baseline"
    conflicts_dir = mrs_dir / "conflicts"
    report = mrs_dir / "SYNC-CONFLICTS.md"
    if names:
        targets = names
    elif conflicts_dir.is_dir():
        targets = sorted(p.name for p in conflicts_dir.iterdir() if p.is_dir())
    else:
        print("mrs-sync-merge: нет каталогов conflicts/", file=sys.stderr)
        return 0

    for name in targets:
        local = text_dir / f"{name}.list"
        if not local.is_file():
            print(f"resolve: нет {local}", file=sys.stderr)
            continue
        baseline_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, baseline_dir / f"{name}.list")
        bundle = conflicts_dir / name
        if bundle.is_dir():
            shutil.rmtree(bundle)
        print(f"resolve: {name} — baseline обновлён из local")

    if conflicts_dir.is_dir() and not any(conflicts_dir.iterdir()):
        conflicts_dir.rmdir()
    if report.is_file() and (
        not conflicts_dir.is_dir() or not any(conflicts_dir.iterdir())
    ):
        report.unlink()
        print("resolve: удалён SYNC-CONFLICTS.md")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mrs-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument(
        "--resolve",
        nargs="*",
        metavar="FILE",
        help="принять local.list как baseline (без имени — все conflicts/)",
    )
    args = ap.parse_args()

    if args.resolve is not None:
        return cmd_resolve(args.mrs_dir.resolve(), args.manifest, args.resolve)

    mrs_dir = args.mrs_dir.resolve()
    text_dir = mrs_dir / "text"
    bin_dir = mrs_dir / "bin"
    baseline_dir = mrs_dir / ".sync-baseline"
    staging_dir = mrs_dir / ".sync-staging"
    staging_text = staging_dir / "text"
    staging_bin = staging_dir / "bin"
    conflicts_dir = mrs_dir / "conflicts"
    report = mrs_dir / "SYNC-CONFLICTS.md"

    text_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    baseline_dir.mkdir(parents=True, exist_ok=True)

    sets = parse_manifest(args.manifest)
    stats: dict[str, int] = {}
    conflict_sets: list[SetInfo] = []

    for info in sets:
        if not info.has_upstream:
            stats["skipped_local"] = stats.get("skipped_local", 0) + 1
            print(f"{info.file}: skipped_local")
            continue
        result = merge_one(
            info,
            text_dir,
            baseline_dir,
            staging_text,
            staging_bin,
            bin_dir,
            conflicts_dir,
        )
        stats[result] = stats.get(result, 0) + 1
        if result == "conflict":
            conflict_sets.append(info)
        print(f"{info.file}: {result}")

    if conflict_sets:
        write_conflicts_report(report, conflict_sets, mrs_dir)
    elif report.is_file():
        report.unlink()

    if conflicts_dir.is_dir() and not any(conflicts_dir.iterdir()):
        conflicts_dir.rmdir()

    print(
        "mrs-sync-merge:",
        ", ".join(f"{k}={v}" for k, v in sorted(stats.items())),
        file=sys.stderr,
    )
    return 1 if conflict_sets else 0


if __name__ == "__main__":
    sys.exit(main())
