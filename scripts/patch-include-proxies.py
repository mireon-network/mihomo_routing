#!/usr/bin/env python3
"""Патч debug-шаблона: все узлы подписки в видимых select-группах + селектор UDP.

include-all: true подтягивает узлы из общего proxies: (туда Remnawave пишет
по # LEAVE THIS LINE!). include-proxies: false не снимаем — иначе та же
инъекция ещё раз в группу и в клиенте дубли карточек.

На *-debug селектор — плоский список имён хостов. include-all без filter
возвращает в список сами группы стран, поэтому страны и «Автовыбор»
из debug-шаблона удаляются, а в видимый select попадают только имена gt_/bgt_.

📡 UDP в основной шаблон не кладём: inject_udp_selector вставляет группу и
поднимает Discord выше NETWORK,UDP только при сборке *-debug.
log-level на *-debug — debug (в шаблоне main остаётся warning).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

INCLUDE_ALL = "    include-all: true"

UDP_NAME = "📡 UDP"
YOUTUBE_NAME = "📺 Youtube"
# Эти пункты — группы, не хосты. В видимом select их нет, иначе список не плоский.
COUNTRY_NAMES = (
    "🇫🇮 Финляндия",
    "🇩🇪 Германия",
    "🇫🇷 Франция",
    "🇳🇱 Нидерланды",
    "🇵🇱 Польша",
    "🇺🇸 США",
)
AUTO_NAME = "⚡️ Автовыбор"
SELECT_ENTRIES_DROPPED = COUNTRY_NAMES + (AUTO_NAME,)
# include-all тянет и группы. В селектор — только имена нод.
HOST_FILTER = r"^(gt_[a-z]{2}-.+-[0-9]+|bgt_[^_]+_gt_[a-z]{2}-.+-[0-9]+)$"

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
    r"  - AND,\(\(RULE-SET,meta-geoip-cloudflare\),\(NETWORK,udp\),\(DST-PORT,19200-19500\)\),[^\n]+\n"
    r"  - AND,\(\(RULE-SET,meta-geoip-cloudflare\),\(NETWORK,udp\),\(DST-PORT,50000-50100\)\),[^\n]+\n"
    r"  - AND,\(\(RULE-SET,discord-voiceips\),\(NETWORK,udp\),\(DST-PORT,50000-50100\)\),[^\n]+\n"
    r"  - RULE-SET,meta-discord,[^\n]+\n"
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


def _group_head(name: str) -> str:
    return (
        rf"(  - name: {re.escape(name)}\n"
        rf"(?:    icon: [^\n]+\n)?"
        rf"    type: select\n"
        rf"(?:    description: [^\n]+\n)?"
        rf")"
    )


def _group_chunk(text: str, name: str) -> tuple[int, int] | None:
    marker = f"  - name: {name}\n"
    start = text.find(marker)
    if start < 0:
        return None
    rel = text[start + len(marker) :]
    m = re.search(r"\n  - name: |\nrule-providers:", rel)
    if not m:
        return None
    return start, start + len(marker) + m.start()


def patch_group(text: str, name: str) -> str | None:
    span = _group_chunk(text, name)
    if span is None:
        print(f"patch-include-proxies: не найдена группа {name!r}", file=sys.stderr)
        return None
    start, end = span
    chunk = text[start:end]
    if "    include-all: true\n" not in chunk:
        chunk, n = re.subn(_group_head(name), rf"\1{INCLUDE_ALL}\n", chunk, count=1)
        if n != 1:
            print(f"patch-include-proxies: не вставить include-all в {name!r}", file=sys.stderr)
            return None
    if "include-proxies: false" not in chunk:
        chunk, n = re.subn(
            rf"({INCLUDE_ALL}\n)",
            r"\1    remnawave:\n      include-proxies: false\n",
            chunk,
            count=1,
        )
        if n != 1:
            print(f"patch-include-proxies: не вернуть include-proxies в {name!r}", file=sys.stderr)
            return None
    return text[:start] + chunk + text[end:]


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


def restore_hidden_hosts(text: str) -> str:
    """Debug больше не выключает hidden hosts — вернуть true, если старый патч уже прогнался."""
    return re.sub(
        r"(remnawave:\n  includeHiddenHosts: )false",
        r"\1true",
        text,
        count=1,
    )


def drop_countries_from_visible_selects(text: str) -> str | None:
    for name in visible_select_groups(text):
        span = _group_chunk(text, name)
        if span is None:
            print(f"patch-include-proxies: не найдена группа {name!r}", file=sys.stderr)
            return None
        start, end = span
        chunk = text[start:end]
        for entry in SELECT_ENTRIES_DROPPED:
            # Последняя строка группы без \n на конце: срез чанка обрывается до следующего name.
            chunk = re.sub(rf"\n      - {re.escape(entry)}(?=\n|$)", "", chunk)
        text = text[:start] + chunk + text[end:]
    return text


def drop_country_groups(text: str) -> str | None:
    """Группы стран и «Автовыбор» не должны существовать: include-all иначе кладёт их в селектор."""
    start_marker = f"  - name: {COUNTRY_NAMES[0]}\n"
    end_marker = "  - name: ⚡️ Авто\n"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0:
        return text
    if end < 0 or end <= start:
        print("patch-include-proxies: не вырезать группы стран", file=sys.stderr)
        return None
    text = text[:start] + text[end:]
    old = "      - ⚡️ Автовыбор\n"
    new = "      - 🛡️ VPN\n"
    if old not in text:
        print("patch-include-proxies: нет ссылки «Автовыбор» у «Авто»", file=sys.stderr)
        return None
    return text.replace(old, new, 1)


def limit_visible_selects_to_hosts(text: str) -> str | None:
    line = f'    filter: "{HOST_FILTER}"\n'
    for name in visible_select_groups(text):
        span = _group_chunk(text, name)
        if span is None:
            print(f"patch-include-proxies: не найдена группа {name!r}", file=sys.stderr)
            return None
        start, end = span
        chunk = text[start:end]
        if line in chunk:
            continue
        marker = "\n    include-all: true\n"
        idx = chunk.find(marker)
        if idx < 0:
            print(f"patch-include-proxies: нет include-all в {name!r}", file=sys.stderr)
            return None
        insert_at = idx + len(marker)
        chunk = chunk[:insert_at] + line + chunk[insert_at:]
        text = text[:start] + chunk + text[end:]
    return text


def patch_wl_whitelist_filter(text: str) -> str:
    span = _group_chunk(text, "🇷🇺 Белые списки")
    if span is None:
        return text
    start, end = span
    chunk = text[start:end]
    chunk = re.sub(r"\n    exclude-filter: [^\n]+", "", chunk, count=1)
    chunk = re.sub(r"\n    filter: [^\n]+", "", chunk, count=1)
    return text[:start] + chunk + text[end:]


def patch_text(text: str, *, is_wl: bool = False) -> str | None:
    if not is_wl:
        text = inject_udp_selector(text)
        if text is None:
            return None

    names = visible_select_groups(text)
    if not names:
        print("patch-include-proxies: нет видимых select-групп", file=sys.stderr)
        return None

    text = restore_hidden_hosts(text)

    for name in names:
        text = patch_group(text, name)
        if text is None:
            return None

    if is_wl:
        text = patch_wl_whitelist_filter(text)
    else:
        text = drop_countries_from_visible_selects(text)
        if text is None:
            return None
        text = drop_country_groups(text)
        if text is None:
            return None
        text = limit_visible_selects_to_hosts(text)
        if text is None:
            return None

    text = re.sub(r"^log-level: \S+", "log-level: debug", text, count=1, flags=re.M)
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
    assert "mixed-port" not in yaml.safe_load(src)
    assert re.search(r"^log-level: warning$", src, re.M)
    assert f"  - name: {UDP_NAME}\n" not in src, "UDP-селектор не должен быть в шаблоне"
    assert "NETWORK,UDP,📡 UDP" not in src

    out = patch_text(src, is_wl=False)
    assert out is not None
    assert re.search(r"^log-level: debug$", out, re.M)
    doc = yaml.safe_load(out)
    names = [
        g["name"]
        for g in doc["proxy-groups"]
        if not g.get("hidden") and g.get("type") == "select"
    ]
    assert UDP_NAME in names
    udp = next(g for g in doc["proxy-groups"] if g["name"] == UDP_NAME)
    yt = next(g for g in doc["proxy-groups"] if g["name"] == YOUTUBE_NAME)
    assert udp.get("include-all") is True
    assert (udp.get("remnawave") or {}).get("include-proxies") is False
    assert udp.get("proxies") == yt.get("proxies")
    assert names.index(UDP_NAME) < names.index(YOUTUBE_NAME)
    assert "includeHiddenHosts: true" in src
    assert "includeHiddenHosts: false" not in out
    assert doc["remnawave"]["includeHiddenHosts"] is True
    for name in names:
        g = next(x for x in doc["proxy-groups"] if x["name"] == name)
        assert g.get("include-all") is True, name
        assert g.get("exclude-filter") is None, name
        assert (g.get("remnawave") or {}).get("include-proxies") is False, name
    vpn_raw = out[out.index("  - name: 🛡️ VPN\n") : out.index("  - name: 📡 UDP\n")]
    assert "include-all: true" in vpn_raw
    assert "include-proxies: false" in vpn_raw
    assert "# LEAVE THIS LINE!" in vpn_raw
    assert "exclude-filter" not in vpn_raw
    countries = (
        ("🇫🇮 Финляндия", "fi"),
        ("🇩🇪 Германия", "de"),
        ("🇫🇷 Франция", "fr"),
        ("🇳🇱 Нидерланды", "nl"),
        ("🇵🇱 Польша", "pl"),
        ("🇺🇸 США", "us"),
    )
    by_name = {g["name"]: g for g in doc["proxy-groups"]}
    src_doc = yaml.safe_load(src)
    src_by = {g["name"]: g for g in src_doc["proxy-groups"]}
    assert [name for name, _ in countries] == list(COUNTRY_NAMES)
    for group_name in (*COUNTRY_NAMES, AUTO_NAME):
        assert group_name not in by_name
    assert by_name["⚡️ Авто"].get("proxies") == ["🛡️ VPN"]
    assert not by_name["🛡️ VPN"].get("proxies")
    host_re = re.compile(HOST_FILTER)
    assert host_re.match("gt_pl-h2n-147")
    assert host_re.match("bgt_spb-tw-72_gt_fr-ovh-212")
    assert host_re.match("bgt_msk-tw-161_gt_pl-h2n-147")
    assert not host_re.match("🇫🇷 Франция")
    assert not host_re.match(AUTO_NAME)
    for sel in names:
        listed = by_name[sel].get("proxies") or []
        for entry in SELECT_ENTRIES_DROPPED:
            assert entry not in listed, sel
        assert by_name[sel].get("filter") == HOST_FILTER, sel
    src_vpn = src_by["🛡️ VPN"]
    assert "🇫🇷 Франция" in (src_vpn.get("proxies") or [])
    assert AUTO_NAME in (src_vpn.get("proxies") or [])
    assert src_by[AUTO_NAME].get("type") == "url-test"
    assert src_by[AUTO_NAME].get("lazy") is False
    assert src_by[AUTO_NAME].get("interval") == 600
    assert src_by[AUTO_NAME].get("proxies") == list(COUNTRY_NAMES)
    for name, code in countries:
        group = src_by[name]
        assert group.get("type") == "fallback"
        assert group.get("interval") == 30
        assert group.get("lazy") is False
        assert group.get("proxies") == [f"{name} · прямая", f"{name} · мосты"]
        direct = src_by[f"{name} · прямая"]
        bridge = src_by[f"{name} · мосты"]
        assert direct.get("filter") == rf"^gt_{code}-.+-[0-9]+$"
        assert bridge.get("filter") == rf"^bgt_[^_]+_gt_{code}-.+-[0-9]+$"
        assert direct.get("include-all") is True and direct.get("exclude-filter") is None
        assert bridge.get("include-all") is True and bridge.get("exclude-filter") is None
        assert direct.get("lazy") is True and bridge.get("lazy") is True
        assert direct.get("empty-fallback") == "REJECT"
        assert bridge.get("empty-fallback") == "REJECT"
        # без явных узлов/заглушек: пустой пул закрывает empty-fallback (mihomo >= v1.19.27)
        assert not direct.get("proxies"), direct.get("proxies")
        assert not bridge.get("proxies"), bridge.get("proxies")
        direct_re = re.compile(direct["filter"])
        bridge_re = re.compile(bridge["filter"])
        assert direct_re.match(f"gt_{code}-hz-102")
        assert direct_re.match(f"gt_{code}-h2n-147")
        assert direct_re.match(f"gt_{code}-hz-extra-102")
        assert not direct_re.match(f"gt-{code}-hz-102")
        assert not direct_re.match(f"gt_{code}_hz_102")
        assert not direct_re.match(f"bg_{code}-hz-102")
        assert not direct_re.match(f"bgt_spb-tw-161_gt_{code}-hz-102")
        assert bridge_re.search(f"bgt_spb-tw-161_gt_{code}-hz-102")
        assert not bridge_re.search(f"bgt_spb-tw-161_bg_{code}-hz-102")
        assert not bridge_re.search(f"bgt_spb_tw-161_gt_{code}-hz-102")
        assert not bridge_re.search(f"bg_{code}-hz-102")
        assert not bridge_re.search(f"foo_gt_{code}-hz-102")
        assert not bridge_re.search(f"gt_{code}-hz-102")
        assert not bridge_re.search(f"gt-{code}-hz-102")
        assert not bridge_re.search(f"gt_{code}_hz_102")

    rules = [str(r) for r in doc["rules"]]
    assert sum("vesktop" in r for r in rules) == 1
    i_vpn = next(i for i, r in enumerate(rules) if "vpn-clients" in r)
    i_vesktop = next(i for i, r in enumerate(rules) if "vesktop" in r)
    i_udp = next(i for i, r in enumerate(rules) if "NETWORK" in r and "UDP" in r and "📡" in r)
    i_yt = next(i for i, r in enumerate(rules) if "meta-youtube" in r)
    assert i_vpn < i_vesktop < i_udp < i_yt

    again = patch_text(out, is_wl=False)
    assert again is not None
    again_doc = yaml.safe_load(again)
    assert sum(1 for g in again_doc["proxy-groups"] if g["name"] == UDP_NAME) == 1
    again_by = {g["name"]: g for g in again_doc["proxy-groups"]}
    assert AUTO_NAME not in again_by
    assert again_by["⚡️ Авто"].get("proxies") == ["🛡️ VPN"]
    assert not again_by["🛡️ VPN"].get("proxies")
    again_names = [
        g["name"]
        for g in again_doc["proxy-groups"]
        if not g.get("hidden") and g.get("type") == "select"
    ]
    for sel in again_names:
        listed = again_by[sel].get("proxies") or []
        for entry in SELECT_ENTRIES_DROPPED:
            assert entry not in listed, sel
        assert again_by[sel].get("filter") == HOST_FILTER, sel
    assert again.count(f'filter: "{HOST_FILTER}"') == len(again_names)

    wl = (root / "MIHOMO/wl.yaml").read_text(encoding="utf-8")
    assert "mixed-port" not in yaml.safe_load(wl)
    assert re.search(r"^log-level: warning$", wl, re.M)
    wl_src = next(g for g in yaml.safe_load(wl)["proxy-groups"] if g["name"] == "🇷🇺 Белые списки")
    assert wl_src.get("filter") == r"(?i)^wlgt_[a-z]{2}-.+-[0-9]+$"
    wl_re = re.compile(wl_src["filter"])
    assert wl_re.match("wlgt_fi-hz-102")
    assert wl_re.match("wlgt_fi-h2n-147")
    assert wl_re.match("wlgt_de-hz-extra-102")
    assert not wl_re.match("gt_fi-hz-102")
    assert not wl_re.match("wlgt_fi_hz_102")
    assert not wl_re.match("bgt_spb-tw-161_wlgt_fi-hz-102")
    wl_out = patch_text(wl, is_wl=True)
    assert wl_out is not None
    assert re.search(r"^log-level: debug$", wl_out, re.M)
    assert UDP_NAME not in wl_out
    wl_sel = next(g for g in yaml.safe_load(wl_out)["proxy-groups"] if g["name"] == "🇷🇺 Белые списки")
    assert wl_sel.get("include-all") is True
    assert wl_sel.get("exclude-filter") is None
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
