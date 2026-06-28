#!/usr/bin/env python3
"""Слияние upstream YAML с локальными файлами без перетирания правок."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CDN_BASE = "https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main"

CDN_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"https://raw\.githubusercontent\.com/legiz-ru/mihomo-rule-sets/[^/]+/other/torrent-clients\.yaml"
        ),
        f"{CDN_BASE}/rule-sets/yaml/torrent-clients.yaml",
    ),
    (
        re.compile(
            r"https://raw\.githubusercontent\.com/roscomvpn/custom-category/[^/]+/mihomo/games\.yaml"
        ),
        f"{CDN_BASE}/rule-sets/yaml/games.yaml",
    ),
    (
        re.compile(
            r"https://raw\.githubusercontent\.com/roscomvpn/custom-category/[^/]+/mihomo/ru-apps\.yaml"
        ),
        f"{CDN_BASE}/rule-sets/yaml/ru-apps.yaml",
    ),
    (
        re.compile(r"https://github\.com/legiz-ru/mihomo-rule-sets/[^ \n]+torrent-clients\.yaml"),
        f"{CDN_BASE}/rule-sets/yaml/torrent-clients.yaml",
    ),
    (
        re.compile(r"https://github\.com/roscomvpn/custom-category/[^ \n]+/games\.yaml"),
        f"{CDN_BASE}/rule-sets/yaml/games.yaml",
    ),
    (
        re.compile(r"https://github\.com/roscomvpn/custom-category/[^ \n]+/ru-apps\.yaml"),
        f"{CDN_BASE}/rule-sets/yaml/ru-apps.yaml",
    ),
]


@dataclass
class SourceInfo:
    id: str
    url: str
    path: str
    post: list[str] = field(default_factory=list)
    auto_apply: bool = True


def parse_manifest(path: Path) -> list[SourceInfo]:
    sources: list[SourceInfo] = []
    cur: dict[str, object] | None = None
    in_post = False

    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- id:"):
            if cur:
                sources.append(_source_from_dict(cur))
            cur = {"id": s.split(":", 1)[1].strip(), "post": [], "auto_apply": True}
            in_post = False
            continue
        if cur is None:
            continue
        if s == "post:":
            in_post = True
            continue
        if in_post and s.startswith("- "):
            cur["post"].append(s[2:].strip())
            continue
        if s.startswith("auto_apply:"):
            in_post = False
            cur["auto_apply"] = s.split(":", 1)[1].strip().lower() not in ("false", "0", "no")
            continue
        if ":" in s and not s.startswith("-"):
            in_post = False
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            if k in ("id", "url", "path"):
                cur[k] = v

    if cur:
        sources.append(_source_from_dict(cur))
    return sources


def _source_from_dict(cur: dict[str, object]) -> SourceInfo:
    return SourceInfo(
        id=str(cur["id"]),
        url=str(cur["url"]),
        path=str(cur["path"]),
        post=list(cur.get("post") or []),
        auto_apply=bool(cur.get("auto_apply", True)),
    )


def same_file(a: Path, b: Path) -> bool:
    if not a.is_file() or not b.is_file():
        return False
    return a.read_bytes() == b.read_bytes()


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "mihomo-routing-upstream-sync/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def write_conflict_bundle(
    conflicts_dir: Path,
    source_id: str,
    local: Path | None,
    remote: Path,
    baseline: Path | None,
) -> None:
    bundle = conflicts_dir / source_id
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    if baseline and baseline.is_file():
        shutil.copy2(baseline, bundle / "baseline")
    if local and local.is_file():
        shutil.copy2(local, bundle / "local")
    shutil.copy2(remote, bundle / "remote")


def merge_one(
    info: SourceInfo,
    root: Path,
    staging_dir: Path,
    baseline_dir: Path,
    conflicts_dir: Path,
) -> str:
    local = root / info.path
    remote = staging_dir / info.path
    base = baseline_dir / info.path

    if not remote.is_file():
        return "skipped_no_remote"

    has_local = local.is_file()
    has_base = base.is_file()

    if not has_local:
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(remote, local)
        shutil.copy2(remote, base)
        return "applied"

    if not has_base:
        if same_file(local, remote):
            shutil.copy2(remote, base)
            return "unchanged"
        write_conflict_bundle(conflicts_dir, info.id, local, remote, None)
        return "conflict"

    loc_eq_rem = same_file(local, remote)
    loc_eq_base = same_file(local, base)
    rem_eq_base = same_file(remote, base)

    if loc_eq_rem:
        shutil.copy2(remote, base)
        return "unchanged"

    if loc_eq_base and not rem_eq_base:
        if info.auto_apply:
            shutil.copy2(remote, local)
            shutil.copy2(remote, base)
            return "applied"
        write_conflict_bundle(conflicts_dir, info.id, local, remote, base)
        return "conflict"

    if not loc_eq_base and rem_eq_base:
        return "kept_local"

    write_conflict_bundle(conflicts_dir, info.id, local, remote, base)
    return "conflict"


def fix_template_cdn(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    updated = text
    for pattern, repl in CDN_REPLACEMENTS:
        updated = pattern.sub(repl, updated)
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def run_post_hooks(root: Path, info: SourceInfo, result: str) -> None:
    if result == "conflict":
        return
    for hook in info.post:
        if hook == "fix_template_cdn":
            target = root / info.path
            if fix_template_cdn(target):
                print(f"post {info.id}: fix_template_cdn — обновлены CDN URL")
        elif hook == "regenerate_gfn_block":
            script = root / "scripts/generate-gfn-games-block.py"
            if not script.is_file():
                print(f"post {info.id}: нет {script}", file=sys.stderr)
                continue
            print(f"post {info.id}: regenerate_gfn_block…")
            subprocess.run([sys.executable, str(script)], cwd=root, check=True)
        elif hook == "regenerate_tun_exclude":
            script = root / "scripts/generate-tun-exclude-package.py"
            if not script.is_file():
                print(f"post {info.id}: нет {script}", file=sys.stderr)
                continue
            print(f"post {info.id}: regenerate_tun_exclude…")
            subprocess.run([sys.executable, str(script)], cwd=root, check=True)
        else:
            print(f"post {info.id}: неизвестный hook {hook!r}", file=sys.stderr)


def write_conflicts_report(report: Path, conflicts: list[SourceInfo], sync_dir: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Конфликты синхронизации upstream",
        "",
        f"Обновлено: {ts}",
        "",
        "Команда `./scripts/upstream-sync.sh sync` **не перезаписала** локальные файлы,",
        "потому что и upstream, и ваши правки изменили один и тот же файл.",
        "",
        "## Что сделать",
        "",
        "1. Для каждого источника откройте `.sync-upstream/conflicts/<id>/`:",
        "   - `baseline` — состояние при последней успешной синхронизации;",
        "   - `local` — ваш текущий файл;",
        "   - `remote` — новая версия upstream.",
        "2. Соберите итог вручную в рабочем файле (см. `path` в manifest).",
        "3. Удалите каталог этого источника из `conflicts/`.",
        "4. Запустите `./scripts/upstream-sync.sh resolve <id>` или `resolve` без аргументов.",
        "5. Повторите `./scripts/upstream-sync.sh sync`.",
        "",
        "Когда все конфликты сняты, удалите этот файл.",
        "",
        "## Источники с конфликтами",
        "",
    ]
    for s in conflicts:
        lines.append(f"- `{s.id}` → `{s.path}` → `{sync_dir / 'conflicts' / s.id}/`")
    lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")


def cmd_download(root: Path, sync_dir: Path, manifest: Path) -> list[SourceInfo]:
    sources = parse_manifest(manifest)
    staging = sync_dir / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    for info in sources:
        dest = staging / info.path
        print(f"fetch {info.id}: {info.url}")
        try:
            fetch(info.url, dest)
        except OSError as exc:
            print(f"fetch {info.id}: ошибка — {exc}", file=sys.stderr)
    return sources


def cmd_sync(root: Path, sync_dir: Path, manifest: Path) -> int:
    sources = cmd_download(root, sync_dir, manifest)
    staging = sync_dir / "staging"
    baseline_dir = sync_dir / "baseline"
    conflicts_dir = sync_dir / "conflicts"
    report = sync_dir / "SYNC-CONFLICTS.md"

    baseline_dir.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {}
    conflict_sources: list[SourceInfo] = []
    results: dict[str, str] = {}

    for info in sources:
        result = merge_one(info, root, staging, baseline_dir, conflicts_dir)
        stats[result] = stats.get(result, 0) + 1
        results[info.id] = result
        print(f"{info.id} ({info.path}): {result}")
        if result == "conflict":
            conflict_sources.append(info)

    for info in sources:
        run_post_hooks(root, info, results[info.id])

    if conflict_sources:
        write_conflicts_report(report, conflict_sources, sync_dir)
    elif report.is_file():
        report.unlink()

    if conflicts_dir.is_dir() and not any(conflicts_dir.iterdir()):
        conflicts_dir.rmdir()

    print(
        "upstream-sync:",
        ", ".join(f"{k}={v}" for k, v in sorted(stats.items())),
        file=sys.stderr,
    )
    return 1 if conflict_sources else 0


def cmd_resolve(root: Path, sync_dir: Path, manifest: Path, ids: list[str]) -> int:
    sources = {s.id: s for s in parse_manifest(manifest)}
    baseline_dir = sync_dir / "baseline"
    conflicts_dir = sync_dir / "conflicts"
    report = sync_dir / "SYNC-CONFLICTS.md"

    if ids:
        targets = ids
    elif conflicts_dir.is_dir():
        targets = sorted(p.name for p in conflicts_dir.iterdir() if p.is_dir())
    else:
        print("upstream-sync: нет каталогов conflicts/")
        return 0

    for source_id in targets:
        info = sources.get(source_id)
        if not info:
            print(f"resolve: неизвестный id {source_id!r}", file=sys.stderr)
            continue
        local = root / info.path
        if not local.is_file():
            print(f"resolve: нет {local}", file=sys.stderr)
            continue
        baseline_dir.mkdir(parents=True, exist_ok=True)
        dest_base = baseline_dir / info.path
        dest_base.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dest_base)
        bundle = conflicts_dir / source_id
        if bundle.is_dir():
            shutil.rmtree(bundle)
        print(f"resolve: {source_id} — baseline обновлён из local")

    if conflicts_dir.is_dir() and not any(conflicts_dir.iterdir()):
        conflicts_dir.rmdir()
    if report.is_file() and (not conflicts_dir.is_dir() or not any(conflicts_dir.iterdir())):
        report.unlink()
        print("resolve: удалён SYNC-CONFLICTS.md")
    return 0


def cmd_baseline_init(root: Path, sync_dir: Path, manifest: Path) -> int:
    baseline_dir = sync_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for info in parse_manifest(manifest):
        local = root / info.path
        if not local.is_file():
            print(f"baseline-init: пропуск {info.path} (нет файла)", file=sys.stderr)
            continue
        dest = baseline_dir / info.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dest)
        n += 1
    print(f"baseline-init: {n} файлов → {baseline_dir}/")
    return 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sync_dir = root / ".sync-upstream"
    manifest = root / "scripts/upstream-manifest.yaml"

    ap = argparse.ArgumentParser(description="Слияние upstream без перетирания локальных правок")
    ap.add_argument(
        "command",
        choices=("sync", "resolve", "baseline-init", "download"),
        help="sync — загрузить и слить; resolve — принять local как baseline",
    )
    ap.add_argument(
        "ids",
        nargs="*",
        help="id источников для resolve (по умолчанию — все conflicts/)",
    )
    ap.add_argument("--root", type=Path, default=root)
    ap.add_argument("--sync-dir", type=Path, default=sync_dir)
    ap.add_argument("--manifest", type=Path, default=manifest)
    args = ap.parse_args()

    args.root = args.root.resolve()
    args.sync_dir = args.sync_dir.resolve()
    args.manifest = args.manifest.resolve()

    if args.command == "sync":
        return cmd_sync(args.root, args.sync_dir, args.manifest)
    if args.command == "download":
        cmd_download(args.root, args.sync_dir, args.manifest)
        return 0
    if args.command == "resolve":
        return cmd_resolve(args.root, args.sync_dir, args.manifest, args.ids)
    if args.command == "baseline-init":
        return cmd_baseline_init(args.root, args.sync_dir, args.manifest)
    return 1


if __name__ == "__main__":
    sys.exit(main())
