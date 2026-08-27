#!/usr/bin/env python3
"""Патч debug-шаблона: все узлы подписки в видимых select-группах + селектор UDP.

include-proxies: false блокирует инъекцию Remnawave в # LEAVE THIS LINE!
include-all-proxies недостаточен — используем стандартный mihomo include-all: true.

Koala Clash рисует все proxies и proxy-groups (hidden: true не прячет карточки).
Поэтому в debug: includeHiddenHosts: false (нет gateway_*), страны-LB вырезаются,
⚡️ Автовыбор url-test'ит оставшиеся узлы.

📡 UDP в основной шаблон не кладём: inject_udp_selector вставляет группу и
поднимает Discord выше NETWORK,UDP только при сборке *-debug.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

INCLUDE_ALL = "    include-all: true"
KEEP_COUNTRIES_IN = "⚡️ Автовыбор"
# gateway_timeweb_101, gateway_timeweb-spb_105 — не ^gateway_[^_]+$
GATEWAY_EXCLUDE = r"(?i)^gateway_"
GATEWAY_COUNTRY_FILTER = re.compile(r"\^gateway_\[\^_\]\+_\d+\$")

UDP_NAME = "📡 UDP"
YOUTUBE_NAME = "📺 Youtube"

YOUTUBE_GROUP = re.compile(
    rf"(  - name: {re.escape(YOUTUBE_NAME)}\n"
    rf"    icon: [^\n]+\n"
    rf"    type: select\n"
    rf"(?:    description: [^\n]+\n)?"
    rf"(?:    include-all: true\n)?"
    rf"(?:    remnawave:\n      include-proxies: false\n)?"
    rf"    proxies:\n"
    rf"((?:      - [^\n]+\n)+))"
)

DISCORD_BLOCK = re.compile(
    r"\n  # --- Discord[^\n]*\n"
    r"  - AND,\(\(RULE-SET,cloudflare-ips\),\(NETWORK,udp\),\(DST-PORT,19200-19500\)\),[^\n]+\n"
    r"  - AND,\(\(RULE-SET,cloudflare-ips\),\(NETWORK,udp\),\(DST-PORT,50000-50100\)\),[^\n]+\n"
    r"  - AND,\(\(RULE-SET,discord_voiceips\),\(NETWORK,udp\),\(DST-PORT,50000-50100\)\),[^\n]+\n"
    r"  - RULE-SET,discord,[^\n]+\n"
    r"  - PROCESS-NAME-REGEX,discord,[^\n]+\n"
    r"  - PROCESS-NAME-REGEX,vesktop,[^\n]+\n"
)

VPN_CLIENTS = re.compile(r"  - RULE-SET,vpn-clients,DIRECT[^\n]*\n")

UDP_RULE = (
    "  - NETWORK,UDP,📡 UDP                             "
    "# весь UDP → селектор (выше Youtube/Google/игр/торрентов/MATCH)\n"
)

DISCORD_HDR = (
    "  # --- Discord (выше 📡 UDP и Google: голос по IP/порту"
    " + вложения на storage.googleapis.com) ---\n"
)


def visible_select_groups(text: str) -> list[str]:
    doc = yaml.safe_load(text)
    return [
        g["name"]
        for g in doc.get("proxy-groups", [])
        if not g.get("hidden") and g.get("type") == "select"
    ]


def country_lb_names(text: str) -> list[str]:
    doc = yaml.safe_load(text)
    return [
        g["name"]
        for g in doc.get("proxy-groups") or []
        if GATEWAY_COUNTRY_FILTER.search(str(g.get("filter") or ""))
    ]


def exclude_filter_line() -> str:
    return f'    exclude-filter: "{GATEWAY_EXCLUDE}"'


def disable_hidden_hosts(text: str) -> str:
    text, n = re.subn(
        r"(remnawave:\n  includeHiddenHosts: )true",
        r"\1false",
        text,
        count=1,
    )
    return text


def drop_country_lb_groups(text: str, country_names: list[str]) -> str:
    if not country_names:
        return text
    start = text.index("proxy-groups:\n")
    end = text.index("\nrule-providers:")
    head, body, tail = text[:start], text[start:end], text[end:]
    drop = set(country_names)
    chunks = re.split(r"(?=  - name: )", body)
    kept = []
    for chunk in chunks:
        m = re.match(r"  - name: (.+)\n", chunk)
        if m and m.group(1) in drop:
            continue
        kept.append(chunk)
    return head + "".join(kept) + tail


def _group_head(name: str) -> str:
    return (
        rf"(  - name: {re.escape(name)}\n"
        rf"(?:    icon: [^\n]+\n)?"
        rf"    type: select\n"
        rf"(?:    description: [^\n]+\n)?"
        rf")"
    )


def patch_autoselect(text: str, exclude_line: str) -> str | None:
    if f"  - name: {KEEP_COUNTRIES_IN}\n" not in text:
        return text
    pat = (
        rf"(  - name: {re.escape(KEEP_COUNTRIES_IN)}\n"
        rf"    type: url-test\n"
        rf"(?:    (?!proxies:)(?!remnawave:)(?!include-all)[^\n]+\n)*)"
        rf"(?:    remnawave:\n      include-proxies: false\n)?"
        rf"(?:    include-all-proxies: true\n)?"
        rf"(?:    include-all: true\n)?"
        rf"(?:    exclude-filter: [^\n]+\n)?"
        rf"(?:    remnawave:\n      include-proxies: false\n)?"
        rf"(?:    proxies:\n(?:      - [^\n]+\n)*|    proxies: \[\]\n)"
    )
    insert = rf"\1    include-all-proxies: true\n{exclude_line}\n    proxies: []\n"
    text, n = re.subn(pat, insert, text, count=1)
    if n != 1:
        print("patch-include-proxies: не найден ⚡️ Автовыбор", file=sys.stderr)
        return None
    return text


def patch_group(text: str, name: str, exclude_line: str) -> str | None:
    insert = f"{INCLUDE_ALL}\n{exclude_line}\n"
    pat = (
        _group_head(name)
        + r"(?:    remnawave:\n      include-proxies: false\n)?"
        + r"(?:    include-all-proxies: true\n)?"
        + r"(?:    include-all: true\n)?"
        + r"(?:    exclude-filter: [^\n]+\n)?"
        + r"(?:    remnawave:\n      include-proxies: false\n)?"
        + r"(?:    include-all-proxies: true\n)?"
        + r"(?:    include-all: true\n)?"
        + r"(?:    exclude-filter: [^\n]+\n)?"
    )
    text, n = re.subn(pat, rf"\1{insert}", text, count=1)
    if n != 1:
        print(f"patch-include-proxies: не найдена группа {name!r}", file=sys.stderr)
        return None
    return text


def strip_countries_from_selectors(text: str, country_names: list[str]) -> str:
    if not country_names:
        return text
    start = text.index("proxy-groups:\n")
    end = text.index("\nrule-providers:")
    head, body, tail = text[:start], text[start:end], text[end:]
    chunks = re.split(r"(?=  - name: )", body)
    out = []
    for chunk in chunks:
        for name in country_names:
            chunk = chunk.replace(f"      - {name}\n", "")
        out.append(chunk)
    return head + "".join(out) + tail


def insert_udp_group(text: str) -> str | None:
    if f"  - name: {UDP_NAME}\n" in text:
        return text
    m = YOUTUBE_GROUP.search(text)
    if not m:
        print("patch-include-proxies: нет группы Youtube — UDP не вставить", file=sys.stderr)
        return None
    block = (
        f"  - name: {UDP_NAME}\n"
        "    icon: https://cdn.jsdelivr.net/gh/Koolson/Qure@master/IconSet/Color/Rocket.png\n"
        "    type: select\n"
        '    description: "Весь UDP — выше Youtube, Google, игр и MATCH; Discord — свой селектор"\n'
        "    remnawave:\n"
        "      include-proxies: false\n"
        "    proxies:\n"
        f"{m.group(2)}"
    )
    return text[: m.start()] + block + text[m.start() :]


def move_discord_above_udp(text: str) -> str | None:
    if "NETWORK,UDP,📡 UDP" in text:
        return text
    dm = DISCORD_BLOCK.search(text)
    if not dm:
        print("patch-include-proxies: нет блока Discord — UDP-правило не вставить", file=sys.stderr)
        return None
    body = re.sub(r"^  # --- Discord[^\n]*\n", DISCORD_HDR, dm.group(0).lstrip("\n"), count=1)
    text = text[: dm.start()] + text[dm.end() :]
    vm = VPN_CLIENTS.search(text)
    if not vm:
        print("patch-include-proxies: нет vpn-clients — Discord/UDP некуда вставить", file=sys.stderr)
        return None
    return text[: vm.end()] + "\n" + body + UDP_RULE + "\n" + text[vm.end() :]


def inject_udp_selector(text: str) -> str | None:
    text = insert_udp_group(text)
    if text is None:
        return None
    return move_discord_above_udp(text)


def patch_wl_whitelist_filter(text: str) -> str:
    return re.sub(
        r"(  - name: 🇷🇺 Белые списки\n(?:.*\n)*?    include-all: true\n"
        r"(?:    exclude-filter: [^\n]+\n)?)"
        r"    filter: [^\n]+\n",
        r"\1",
        text,
        count=1,
    )


def patch_text(text: str, *, is_wl: bool = False) -> str | None:
    if not is_wl:
        text = inject_udp_selector(text)
        if text is None:
            return None

    countries = country_lb_names(text)
    exclude_line = exclude_filter_line()
    text = disable_hidden_hosts(text)
    text = drop_country_lb_groups(text, countries)
    text = strip_countries_from_selectors(text, countries)

    names = visible_select_groups(text)
    if not names:
        print("patch-include-proxies: нет видимых select-групп", file=sys.stderr)
        return None

    for name in names:
        text = patch_group(text, name, exclude_line)
        if text is None:
            return None

    text = patch_autoselect(text, exclude_line)
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
    extra = f", UDP={'да' if UDP_NAME in names else 'нет'}"
    print(f"patch-include-proxies: {len(names)} селекторов, include-all{extra} → {path}")
    return True


def self_check() -> None:
    root = Path(__file__).resolve().parents[1]
    src = (root / "MIHOMO/template_remnawave.yaml").read_text(encoding="utf-8")
    assert f"  - name: {UDP_NAME}\n" not in src, "UDP-селектор не должен быть в шаблоне"
    assert "NETWORK,UDP,📡 UDP" not in src

    out = patch_text(src, is_wl=False)
    assert out is not None
    doc = yaml.safe_load(out)
    names = [
        g["name"]
        for g in doc["proxy-groups"]
        if not g.get("hidden") and g.get("type") == "select"
    ]
    assert UDP_NAME in names
    udp = next(g for g in doc["proxy-groups"] if g["name"] == UDP_NAME)
    yt = next(g for g in doc["proxy-groups"] if g["name"] == YOUTUBE_NAME)
    countries_src = country_lb_names(src)
    assert countries_src, "в шаблоне должны быть country load-balance"
    assert "includeHiddenHosts: true" in src
    assert "includeHiddenHosts: false" in out
    assert country_lb_names(out) == []
    assert all(f"  - name: {c}\n" not in out for c in countries_src)
    assert udp.get("include-all") is True
    assert udp.get("exclude-filter") == GATEWAY_EXCLUDE
    assert yt.get("exclude-filter") == GATEWAY_EXCLUDE
    assert udp.get("proxies") == yt.get("proxies")
    assert names.index(UDP_NAME) < names.index(YOUTUBE_NAME)
    assert all(c not in (yt.get("proxies") or []) for c in countries_src)
    auto = next(g for g in doc["proxy-groups"] if g["name"] == KEEP_COUNTRIES_IN)
    assert auto.get("include-all-proxies") is True
    assert auto.get("exclude-filter") == GATEWAY_EXCLUDE
    assert auto.get("proxies") == []
    vpn = next(g for g in doc["proxy-groups"] if g["name"] == "🛡️ VPN")
    assert vpn.get("proxies") == ["⚡️ Автовыбор"]

    rules = [str(r) for r in doc["rules"]]
    assert sum("vesktop" in r for r in rules) == 1
    i_vpn = next(i for i, r in enumerate(rules) if "vpn-clients" in r)
    i_vesktop = next(i for i, r in enumerate(rules) if "vesktop" in r)
    i_udp = next(i for i, r in enumerate(rules) if "NETWORK" in r and "UDP" in r and "📡" in r)
    i_yt = next(i for i, r in enumerate(rules) if "youtube-meta" in r)
    assert i_vpn < i_vesktop < i_udp < i_yt

    again = patch_text(out, is_wl=False)
    assert again is not None
    assert sum(1 for g in yaml.safe_load(again)["proxy-groups"] if g["name"] == UDP_NAME) == 1

    wl = (root / "MIHOMO/wl.yaml").read_text(encoding="utf-8")
    wl_out = patch_text(wl, is_wl=True)
    assert wl_out is not None
    assert UDP_NAME not in wl_out
    wl_sel = next(g for g in yaml.safe_load(wl_out)["proxy-groups"] if g["name"] == "🇷🇺 Белые списки")
    assert wl_sel.get("include-all") is True
    assert wl_sel.get("exclude-filter") == GATEWAY_EXCLUDE
    assert "filter" not in wl_sel
    print("patch-include-proxies: self-check ok")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args == ["--self-check"]:
        self_check()
        return 0
    paths = [Path(p) for p in args]
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
