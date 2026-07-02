#!/usr/bin/env python3
"""Патч debug-шаблона: все узлы подписки в видимых select-группах.

include-proxies: false блокирует инъекцию Remnawave в # LEAVE THIS LINE!
include-all-proxies недостаточен — используем стандартный mihomo include-all: true.
includeHiddenHosts: true не трогаем (gateway_* остаются в proxies:).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

INCLUDE_ALL = "    include-all: true"


def visible_select_groups(text: str) -> list[str]:
    doc = yaml.safe_load(text)
    return [
        g["name"]
        for g in doc.get("proxy-groups", [])
        if not g.get("hidden") and g.get("type") == "select"
    ]


def patch_group(text: str, name: str) -> str | None:
    pat = (
        rf"(  - name: {re.escape(name)}\n"
        rf"(?:    icon: [^\n]+\n)?"
        rf"    type: select\n)"
        rf"(?:    include-all-proxies: true\n)?"
        rf"(?:    include-all: true\n)?"
        rf"(?:    remnawave:\n      include-proxies: false\n)?"
        rf"(?!    include-all: true\n)"
    )
    text, n = re.subn(pat, rf"\1{INCLUDE_ALL}\n", text, count=1)
    if n != 1:
        if f"  - name: {name}\n" in text:
            # уже есть include-all, только снять remnawave/include-all-proxies
            text = re.sub(
                rf"(  - name: {re.escape(name)}\n(?:    icon: [^\n]+\n)?    type: select\n)"
                rf"(?:    include-all-proxies: true\n)?"
                rf"(?:    include-all: true\n)"
                rf"    remnawave:\n      include-proxies: false\n",
                rf"\1{INCLUDE_ALL}\n",
                text,
                count=1,
            )
            return text
        print(f"patch-include-proxies: не найдена группа {name!r}", file=sys.stderr)
        return None
    return text


def patch_wl_whitelist_filter(text: str) -> str:
    return re.sub(
        r"(  - name: 🇷🇺 Белые списки\n(?:.*\n)*?    include-all: true\n)"
        r"    filter: [^\n]+\n",
        r"\1",
        text,
        count=1,
    )


def patch_text(text: str, *, is_wl: bool = False) -> str | None:
    names = visible_select_groups(text)
    if not names:
        print("patch-include-proxies: нет видимых select-групп", file=sys.stderr)
        return None

    for name in names:
        text = patch_group(text, name)
        if text is None:
            return None

    if is_wl:
        text = patch_wl_whitelist_filter(text)

    return text


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    out = patch_text(text, is_wl=path.name == "wl.yaml")
    if out is None:
        return False
    if out != text:
        path.write_text(out, encoding="utf-8")
    names = visible_select_groups(out)
    print(f"patch-include-proxies: {len(names)} селекторов, include-all → {path}")
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
