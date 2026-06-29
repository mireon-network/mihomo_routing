#!/usr/bin/env python3
"""Сгенерировать tun.exclude-package в шаблоне из RU-app списков.

Механизм как у Davoyan/ultimate-mihomo-ru: российские приложения исключаются из
TUN по package-name. Davoyan берёт только ru-app-list.yaml; здесь — объединение
всех RU-наборов, которые роутятся в DIRECT, чтобы исключение из TUN и DIRECT-
маршрутизация совпадали (один источник правды для «RU-приложений»).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = (
    ROOT / "MIHOMO/template_remnawave.yaml",
    ROOT / "MIHOMO/wl.yaml",
)

SOURCES = (
    ROOT / "rule-sets/yaml/ru-app-list.yaml",   # legiz-ru (источник Davoyan)
    ROOT / "rule-sets/yaml/ru-apps-custom.yaml", # локальные дополнения (вне legiz)
)

# Android package-name: токены через точку, без пробелов/слешей; .exe — это десктоп.
PKG_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")


def collect_packages() -> list[str]:
    seen: dict[str, None] = {}  # dict сохраняет порядок и дедуплицирует
    for src in SOURCES:
        if not src.is_file():
            continue
        for m in re.finditer(r"PROCESS-NAME,([^\n#]+)", src.read_text(encoding="utf-8")):
            v = m.group(1).strip()
            if v.lower().endswith(".exe"):
                continue
            if PKG_RE.match(v):
                seen.setdefault(v, None)
    return list(seen)


def main() -> int:
    pkgs = collect_packages()
    if not pkgs:
        print("generate-tun-exclude-package: нет пакетов — прерываю", file=sys.stderr)
        return 1

    arr = "[" + ", ".join(json.dumps(p) for p in pkgs) + "]"
    line = f"  exclude-package: {arr}"

    rc = 0
    for tpl in TEMPLATES:
        text = tpl.read_text(encoding="utf-8")
        new, n = re.subn(r"^  exclude-package:.*$", lambda _: line, text, count=1, flags=re.M)
        if n == 0:
            print(
                f"generate-tun-exclude-package: в {tpl} нет строки 'exclude-package:'",
                file=sys.stderr,
            )
            rc = 1
            continue
        if new != text:
            tpl.write_text(new, encoding="utf-8")
        print(f"generate-tun-exclude-package: {len(pkgs)} пакетов → {tpl}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
