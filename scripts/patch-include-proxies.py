#!/usr/bin/env python3
"""Патч debug-шаблона: все узлы подписки в видимых select-группах.

Remnawave include-proxies: true подставляет только hidden gateway_*.
Вместо этого — mihomo include-all-proxies: true (все записи из proxies:).
include-proxies остаётся false; includeHiddenHosts: true не трогаем.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

INCLUDE_ALL_PROXIES = "    include-all-proxies: true"


def visible_select_groups(text: str) -> list[str]:
    doc = yaml.safe_load(text)
    return [
        g["name"]
        for g in doc.get("proxy-groups", [])
        if not g.get("hidden") and g.get("type") == "select"
    ]


def patch_group_include_all(text: str, name: str) -> str | None:
    pat = (
        rf"(  - name: {re.escape(name)}\n"
        rf"    icon: [^\n]+\n"
        rf"    type: select\n)"
        rf"(?!    include-all-proxies: true\n)"
    )
    text, n = re.subn(pat, rf"\1{INCLUDE_ALL_PROXIES}\n", text, count=1)
    if n != 1:
        print(
            f"patch-include-proxies: не найдена группа {name!r} (type: select)",
            file=sys.stderr,
        )
        return None
    return text


def patch_text(text: str) -> str | None:
    names = visible_select_groups(text)
    if not names:
        print("patch-include-proxies: нет видимых select-групп", file=sys.stderr)
        return None

    for name in names:
        text = patch_group_include_all(text, name)
        if text is None:
            return None
    return text


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    out = patch_text(text)
    if out is None:
        return False
    if out != text:
        path.write_text(out, encoding="utf-8")
    names = visible_select_groups(out)
    print(f"patch-include-proxies: {len(names)} селекторов, include-all-proxies → {path}")
    return True


def main(argv: list[str] | None = None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        print("patch-include-proxies: укажите файлы", file=sys.stderr)
        return 1
    rc = 0
    for path in paths:
        if not path.is_file():
            print(f"patch-include-proxies: нет {path}", file=sys.stderr)
            rc = 1
            continue
        if not patch_file(path):
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
