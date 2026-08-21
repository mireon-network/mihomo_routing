#!/usr/bin/env python3
"""Зеркалирование upstream YAML: remote → local. Локальные правки — только в *-custom."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

CDN_BASE = "https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main"
TEMPLATE = "MIHOMO/template_remnawave.yaml"

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
        re.compile(r"https://github\.com/legiz-ru/mihomo-rule-sets/[^ \n]+torrent-clients\.yaml"),
        f"{CDN_BASE}/rule-sets/yaml/torrent-clients.yaml",
    ),
    (
        re.compile(r"https://github\.com/roscomvpn/custom-category/[^ \n]+/games\.yaml"),
        f"{CDN_BASE}/rule-sets/yaml/games.yaml",
    ),
]


@dataclass
class SourceInfo:
    id: str
    url: str
    path: str
    post: list[str] = field(default_factory=list)


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
            cur = {"id": s.split(":", 1)[1].strip(), "post": []}
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


def apply_mirror(info: SourceInfo, root: Path, staging_dir: Path) -> str:
    local = root / info.path
    remote = staging_dir / info.path
    if not remote.is_file():
        return "skipped_no_remote"
    if local.is_file() and same_file(local, remote):
        return "unchanged"
    local.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(remote, local)
    return "applied"


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


def run_post_hooks(root: Path, info: SourceInfo) -> None:
    for hook in info.post:
        if hook == "strip_launchers":
            script = root / "scripts/strip-games-launchers.py"
            if not script.is_file():
                print(f"post {info.id}: нет {script}", file=sys.stderr)
                continue
            print(f"post {info.id}: strip_launchers…")
            subprocess.run([sys.executable, str(script)], cwd=root, check=True)
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
    stats: dict[str, int] = {}

    for info in sources:
        result = apply_mirror(info, root, staging)
        stats[result] = stats.get(result, 0) + 1
        print(f"{info.id} ({info.path}): {result}")
        if result in ("applied", "unchanged"):
            run_post_hooks(root, info)

    tpl = root / TEMPLATE
    if fix_template_cdn(tpl):
        print(f"post: fix_template_cdn — обновлены CDN URL в {TEMPLATE}")

    print(
        "upstream-sync:",
        ", ".join(f"{k}={v}" for k, v in sorted(stats.items())),
        file=sys.stderr,
    )
    return 0


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sync_dir = root / ".sync-upstream"
    manifest = root / "scripts/upstream-manifest.yaml"

    ap = argparse.ArgumentParser(description="Зеркалирование upstream YAML")
    ap.add_argument(
        "command",
        choices=("sync", "download"),
        help="sync — загрузить и записать зеркала; download — только staging",
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
    cmd_download(args.root, args.sync_dir, args.manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
