#!/usr/bin/env python3
"""include-proxies: true в видимых select-группах YAML-шаблона (in-place)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


def visible_select_groups(text: str) -> list[str]:
    doc = yaml.safe_load(text)
    return [
        g["name"]
        for g in doc.get("proxy-groups", [])
        if not g.get("hidden") and g.get("type") == "select"
    ]


def patch_text(text: str) -> str | None:
    names = visible_select_groups(text)
    if not names:
        return None
    for name in names:
        pat = rf"(  - name: {re.escape(name)}\n(?:.*\n)*?    remnawave:\n      include-proxies:) false"
        text, n = re.subn(pat, r"\1 true", text, count=1)
        if n != 1:
            print(
                f"patch-include-proxies: не найдена группа {name!r} (include-proxies: false)",
                file=sys.stderr,
            )
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
    print(f"patch-include-proxies: {len(names)} селекторов → {path}")
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
