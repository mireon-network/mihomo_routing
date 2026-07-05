#!/usr/bin/env python3
"""Сгенерировать tun.exclude-package в шаблонах Mihomo.

template_remnawave.yaml — все RU-приложения из ru-app-list + ru-apps-custom (DIRECT-маршрутизация).
wl.yaml — только пакеты, соответствующие доменам rule-set wld (RULE-SET,wld,DIRECT), плюс wld-apps-custom.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WLD_LIST = ROOT / "rule-sets/mrs/text/wld.list"

TEMPLATES: dict[Path, tuple[Path, ...]] = {
    ROOT / "MIHOMO/template_remnawave.yaml": (
        ROOT / "rule-sets/yaml/ru-app-list.yaml",
        ROOT / "rule-sets/yaml/ru-apps-custom.yaml",
    ),
    ROOT / "MIHOMO/wl.yaml": (),  # заполняется collect_wld_packages()
}

# Метка домена wld.list → сегменты Android package-name
WLD_ALIASES: dict[str, frozenset[str]] = {
    "wb": frozenset({"wildberries", "wb"}),
    "ya": frozenset({"yandex"}),
    "t2": frozenset({"tele2", "t2", "mytele2", "troika"}),
    "tbank": frozenset({"tbank", "tinkoff"}),
    "cdn-tinkoff": frozenset({"tinkoff", "tbank"}),
    "sber": frozenset({"sber", "sberbank", "sbrf", "sberauto", "sbermegamarket"}),
    "sberbank": frozenset({"sber", "sberbank", "sbrf", "sberauto", "sbermegamarket"}),
    "vk": frozenset({"vk", "vkontakte", "vkplay", "vkpm", "vkmusic"}),
    "cdn-vk": frozenset({"vk", "vkontakte", "vkplay", "vkpm", "vkmusic"}),
    "mail": frozenset({"mail"}),
    "ozon": frozenset({"ozon"}),
    "avito": frozenset({"avito", "youla", "beru"}),
    "vtb": frozenset({"vtb"}),
    "alfabank": frozenset({"alfabank", "alfadirect", "alfastrah"}),
    "gosuslugi": frozenset({"gosuslugi"}),
    "kinopoisk": frozenset({"kinopoisk"}),
    "rutube": frozenset({"rutube"}),
    "pochta": frozenset({"russianpost", "pechkin"}),
    "rzd": frozenset({"rzd"}),
    "2gis": frozenset({"dgis", "2gis"}),
    "dzen": frozenset({"zen"}),
    "oneme": frozenset({"oneme"}),
    "max": frozenset({"oneme"}),
    "tutu": frozenset({"tutu"}),
    "lenta": frozenset({"lenta", "lentochka"}),
    "rambler": frozenset({"rambler"}),
    "auto": frozenset({"auto"}),
    "taximaxim": frozenset({"taximaxim", "taxsee"}),
    "userapi": frozenset({"vk", "vkontakte"}),
}

PKG_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
WLD_PKG_SOURCES = (
    ROOT / "rule-sets/yaml/ru-app-list.yaml",
    ROOT / "rule-sets/yaml/ru-apps-custom.yaml",
    ROOT / "rule-sets/yaml/wld-apps-custom.yaml",
)


def _primary_label(domain: str) -> str:
    parts = domain.split(".")
    return parts[-2] if len(parts) >= 2 else parts[0]


def wld_match_tokens() -> frozenset[str]:
    tokens: set[str] = set()
    if not WLD_LIST.is_file():
        return frozenset()
    for raw in WLD_LIST.read_text(encoding="utf-8").splitlines():
        domain = raw.strip().lstrip("+.").lower()
        if not domain or domain.startswith("#"):
            continue
        label = _primary_label(domain)
        tokens.add(label)
        tokens |= set(WLD_ALIASES.get(label, ()))
    return frozenset(tokens)


def collect_packages(sources: tuple[Path, ...]) -> list[str]:
    seen: dict[str, None] = {}
    for src in sources:
        if not src.is_file():
            continue
        for m in re.finditer(r"PROCESS-NAME,([^\n#]+)", src.read_text(encoding="utf-8")):
            v = m.group(1).strip()
            if v.lower().endswith(".exe"):
                continue
            if PKG_RE.match(v):
                seen.setdefault(v, None)
    return list(seen)


def package_matches_wld(pkg: str, tokens: frozenset[str]) -> bool:
    segs = pkg.lower().split(".")
    return any(t in segs for t in tokens)


def collect_wld_packages() -> list[str]:
    tokens = wld_match_tokens()
    if not tokens:
        print("generate-tun-exclude-package: wld.list пуст или не найден", file=sys.stderr)
        return []
    all_pkgs = collect_packages(WLD_PKG_SOURCES)
    return [p for p in all_pkgs if package_matches_wld(p, tokens)]


def main() -> int:
    rc = 0
    for tpl, sources in TEMPLATES.items():
        if tpl.name == "wl.yaml":
            pkgs = collect_wld_packages()
            src_desc = "wld.list + ru-app-list/ru-apps-custom/wld-apps-custom"
        else:
            pkgs = collect_packages(sources)
            src_desc = " + ".join(s.name for s in sources)

        if not pkgs:
            print(f"generate-tun-exclude-package: нет пакетов для {tpl.name} — прерываю", file=sys.stderr)
            rc = 1
            continue

        arr = "[" + ", ".join(json.dumps(p) for p in pkgs) + "]"
        line = f"  exclude-package: {arr}"
        text = tpl.read_text(encoding="utf-8")
        new, n = re.subn(r"^  exclude-package:.*$", lambda _: line, text, count=1, flags=re.M)
        if n == 0:
            print(f"generate-tun-exclude-package: в {tpl} нет строки 'exclude-package:'", file=sys.stderr)
            rc = 1
            continue
        if new != text:
            tpl.write_text(new, encoding="utf-8")
        print(f"generate-tun-exclude-package: {len(pkgs)} пакетов ({src_desc}) → {tpl.name}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
