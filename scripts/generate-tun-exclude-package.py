#!/usr/bin/env python3
"""Сгенерировать tun.exclude-package в шаблонах Mihomo.

template_remnawave.yaml — все RU-приложения из ru-app-list + ru-apps-custom (DIRECT-маршрутизация).
wl.yaml — пакеты из ru-app-list, отфильтрованные по wld.list (+ aliases), плюс wld-apps-custom.
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
# sber/dgis — 4 символа. Короче (ya, t2) совпадение по началу сегмента не берём.
PREFIX_MIN = 4
WLD_FILTER_SOURCES = (ROOT / "rule-sets/yaml/ru-app-list.yaml",)
WLD_CUSTOM_SOURCES = (ROOT / "rule-sets/yaml/wld-apps-custom.yaml",)


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


def require_sources(sources: tuple[Path, ...]) -> None:
    missing = [src for src in sources if not src.is_file()]
    if missing:
        raise SystemExit(
            "generate-tun-exclude-package: нет " + ", ".join(str(p) for p in missing)
        )


def collect_packages(sources: tuple[Path, ...]) -> list[str]:
    require_sources(sources)
    seen: dict[str, None] = {}
    for src in sources:
        for m in re.finditer(r"PROCESS-NAME,([^\n#]+)", src.read_text(encoding="utf-8")):
            v = m.group(1).strip()
            if v.lower().endswith(".exe"):
                continue
            if PKG_RE.match(v):
                seen.setdefault(v, None)
    return list(seen)


def package_matches_wld(pkg: str, tokens: frozenset[str]) -> bool:
    # ru.sberbankmobile и pro.sber_zvuk: метка короче сегмента или склеена через _
    segs: list[str] = []
    for part in pkg.lower().split("."):
        segs.append(part)
        if "_" in part:
            segs.extend(piece for piece in part.split("_") if piece)
    if any(token in segs for token in tokens):
        return True
    return any(
        len(token) >= PREFIX_MIN and any(seg.startswith(token) and seg != token for seg in segs)
        for token in tokens
    )


def collect_wld_packages() -> list[str]:
    tokens = wld_match_tokens()
    if not tokens:
        print("generate-tun-exclude-package: wld.list пуст или не найден", file=sys.stderr)
        return []
    seen: dict[str, None] = {}
    for pkg in collect_packages(WLD_FILTER_SOURCES):
        if package_matches_wld(pkg, tokens):
            seen.setdefault(pkg, None)
    for pkg in collect_packages(WLD_CUSTOM_SOURCES):
        seen.setdefault(pkg, None)
    return list(seen)


def self_check() -> None:
    try:
        require_sources((Path("/no/such/ru-apps-custom.yaml"),))
    except SystemExit as exc:
        assert "ru-apps-custom.yaml" in str(exc)
    else:
        raise AssertionError("пропавший yaml не остановил сборку")
    tokens = frozenset({"sber", "sberbank", "dgis", "gosuslugi", "yandex", "ya", "mail"})
    assert package_matches_wld("ru.sberbankmobile", tokens)
    assert package_matches_wld("ru.sberbank_sbbol", tokens)
    assert package_matches_wld("pro.sber_zvuk", tokens)
    assert package_matches_wld("ru.dublgis.dgismobile", tokens)
    assert package_matches_wld("com.uip.gosuslugi2", tokens)
    assert package_matches_wld("ru.yandex_team.calendar_app", tokens)
    assert package_matches_wld("ru.mail.cloud", tokens)
    assert not package_matches_wld("com.yappy.android", tokens)
    print("generate-tun-exclude-package: self-check ok")


def main() -> int:
    if sys.argv[1:2] == ["--self-check"]:
        self_check()
        return 0
    # оба шаблона читают эти файлы; проверяем до первой записи
    require_sources(
        TEMPLATES[ROOT / "MIHOMO/template_remnawave.yaml"]
        + WLD_FILTER_SOURCES
        + WLD_CUSTOM_SOURCES
    )
    rc = 0
    for tpl, sources in TEMPLATES.items():
        if tpl.name == "wl.yaml":
            pkgs = collect_wld_packages()
            src_desc = "wld.list → ru-app-list + wld-apps-custom"
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
