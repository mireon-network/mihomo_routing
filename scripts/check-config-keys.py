#!/usr/bin/env python3
"""Статическая проверка ключей шаблонов против схемы конфига mihomo.

mihomo молча игнорирует неизвестные ключи (`mihomo -t` их не ловит), поэтому
опечатка вроде `emtpy-fallback` или ключ, которого нет в минимальной
поддерживаемой версии ядра, тихо меняет поведение у клиентов.

Схема снята с исходников mihomo v1.19.32 (yaml/group/provider-теги в
config/config.go, adapter/outboundgroup/*.go, rules/provider/parse.go).
При обновлении ядра — дополнить множества ниже.

Использование:
  scripts/check-config-keys.py [--min-version v1.19.27] FILE...
  scripts/check-config-keys.py --self-check
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

TOP = {
    "port", "socks-port", "redir-port", "tproxy-port", "mixed-port", "ss-config", "vmess-config",
    "inbound-tfo", "inbound-mptcp", "authentication", "skip-auth-prefixes", "lan-allowed-ips",
    "lan-disallowed-ips", "allow-lan", "bind-address", "mode", "unified-delay", "log-level", "ipv6",
    "external-controller", "external-controller-routing-mark", "external-controller-pipe",
    "external-controller-unix", "external-controller-tls", "external-controller-cors", "external-ui",
    "external-ui-url", "external-ui-name", "external-doh-server", "secret", "interface-name",
    "routing-mark", "tunnels", "geo-auto-update", "geo-update-interval", "geodata-mode",
    "geodata-loader", "geosite-matcher", "tcp-concurrent", "find-process-mode",
    "global-client-fingerprint", "global-ua", "etag-support", "keep-alive-idle",
    "keep-alive-interval", "disable-keep-alive", "proxy-providers", "rule-providers", "proxies",
    "proxy-groups", "rules", "sub-rules", "listeners", "hosts", "dns", "ntp", "tun", "tuic-server",
    "iptables", "experimental", "profile", "geox-url", "sniffer", "tls", "clash-for-android",
}

SECTIONS: dict[str, set[str]] = {
    "dns": {
        "enable", "prefer-h3", "ipv6", "ipv6-timeout", "use-hosts", "use-system-hosts",
        "respect-rules", "nameserver", "fallback", "fallback-filter", "fallback-lazy-query",
        "listen", "listen-routing-mark", "enhanced-mode", "fake-ip-range", "fake-ip-range6",
        "fake-ip-filter", "fake-ip-filter-mode", "fake-ip-ttl", "default-nameserver",
        "cache-algorithm", "cache-max-size", "proxy-server-nameserver", "direct-nameserver",
        "direct-nameserver-follow-policy", "nameserver-policy",
    },
    "dns.fallback-filter": {"geoip", "geoip-code", "ipcidr", "domain", "geosite"},
    "tun": {
        "enable", "device", "stack", "dns-hijack", "auto-route", "auto-detect-interface", "mtu",
        "gso", "gso-max-size", "inet6-address", "iproute2-table-index", "iproute2-rule-index",
        "auto-redirect", "auto-redirect-input-mark", "auto-redirect-output-mark",
        "auto-redirect-iproute2-fallback-rule-index", "loopback-address", "strict-route",
        "route-address", "route-address-set", "route-exclude-address", "route-exclude-address-set",
        "include-interface", "exclude-interface", "include-uid", "include-uid-range", "exclude-uid",
        "exclude-uid-range", "exclude-src-port", "exclude-src-port-range", "exclude-dst-port",
        "exclude-dst-port-range", "include-android-user", "include-package", "exclude-package",
        "include-mac-address", "exclude-mac-address", "endpoint-independent-nat", "udp-timeout",
        "icmp-timeout", "disable-icmp-forwarding", "congestion-controller", "file-descriptor",
        "inet4-route-address", "inet6-route-address", "inet4-route-exclude-address",
        "inet6-route-exclude-address", "recvmsgx", "sendmsgx", "processors-per-channel",
    },
    "sniffer": {
        "enable", "override-destination", "sniffing", "force-domain", "skip-src-address",
        "skip-dst-address", "skip-domain", "port-whitelist", "force-dns-mapping", "parse-pure-ip",
        "sniff",
    },
    "sniffer.sniff.*": {"ports", "override-destination"},
    "profile": {"store-selected", "store-fake-ip"},
    "experimental": {"fingerprints", "quic-go-disable-gso", "quic-go-disable-ecn", "dialer-ip4p-convert"},
    "ntp": {"enable", "server", "port", "interval", "dialer-proxy", "write-to-system"},
    "geox-url": {"geoip", "mmdb", "asn", "geosite"},
    "external-controller-cors": {"allow-origins", "allow-private-network"},
    "clash-for-android": {"append-system-dns", "ui-subtitle-pattern"},
}

GROUP = {
    "name", "type", "proxies", "use", "url", "interval", "timeout", "max-failed-times",
    "empty-fallback", "lazy", "disable-udp", "filter", "exclude-filter", "exclude-type",
    "expected-status", "include-all", "include-all-proxies", "include-all-providers", "hidden",
    "icon", "tolerance", "strategy", "hash-key", "default-selected",
    # не ядро: Remnawave вырезает до отдачи клиенту; mihomo-клиенты тоже не валидируют
    "remnawave", "description",
}
GROUP_REMNAWAVE = {"include-proxies", "select-random-proxy", "shuffle-proxies-order"}
ROOT_REMNAWAVE = {"includeHiddenHosts"}
RULE_PROVIDER = {
    "type", "behavior", "format", "url", "path", "interval", "proxy", "header", "size-limit",
    "payload", "path-in-bundle",
}

# Ключи новее минимальной версии ядра: старое ядро их молча проигнорирует.
SINCE = {
    ("proxy-groups", "empty-fallback"): (1, 19, 27),
    ("rule-providers", "path-in-bundle"): (1, 19, 27),
    ("<root>", "external-controller-routing-mark"): (1, 19, 28),
    ("dns", "listen-routing-mark"): (1, 19, 28),
    ("tun", "icmp-timeout"): (1, 19, 28),
    ("proxy-groups", "default-selected"): (1, 19, 28),
    ("dns", "fallback-lazy-query"): (1, 19, 28),
    ("tun", "processors-per-channel"): (1, 19, 31),
    ("proxy-groups", "hash-key"): (1, 19, 32),
}

DEFAULT_MIN = "v1.19.27"


def parse_ver(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.lstrip("v").split("."))


def check_doc(doc: dict, min_ver: tuple[int, ...]) -> list[str]:
    errs: list[str] = []

    def unknown(where: str, keys, allowed: set[str]) -> None:
        for k in keys:
            if k not in allowed:
                errs.append(f"{where}: неизвестный ключ {k!r}")

    def since(section: str, key: str, where: str) -> None:
        need = SINCE.get((section, key))
        if need and need > min_ver:
            v = ".".join(map(str, need))
            errs.append(f"{where}: {key!r} появился в v{v} — минимальное ядро его молча проигнорирует")

    for k in doc:
        if k.startswith("x-"):  # x-* — только YAML-якоря
            continue
        if k == "remnawave":
            unknown("remnawave", doc[k] or {}, ROOT_REMNAWAVE)
            continue
        if k not in TOP:
            errs.append(f"<root>: неизвестный ключ {k!r}")
            continue
        since("<root>", k, "<root>")

    for sec, allowed in SECTIONS.items():
        parts = sec.split(".")
        node = doc
        if parts[-1] == "*":
            for p in parts[:-1]:
                node = (node or {}).get(p) if isinstance(node, dict) else None
            for name, sub in (node or {}).items():
                unknown(f"{'.'.join(parts[:-1])}.{name}", sub or {}, allowed)
            continue
        for p in parts:
            node = node.get(p) if isinstance(node, dict) else None
        if isinstance(node, dict):
            unknown(sec, node, allowed)
            for k in node:
                since(sec, k, sec)

    for g in doc.get("proxy-groups") or []:
        where = f"proxy-groups[{g.get('name')}]"
        unknown(where, g, GROUP)
        unknown(f"{where}.remnawave", g.get("remnawave") or {}, GROUP_REMNAWAVE)
        for k in g:
            since("proxy-groups", k, where)

    for name, p in (doc.get("rule-providers") or {}).items():
        where = f"rule-providers[{name}]"
        unknown(where, p or {}, RULE_PROVIDER)
        for k in p or {}:
            since("rule-providers", k, where)
    return errs


def check_file(path: Path, min_ver: tuple[int, ...]) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return check_doc(doc, min_ver)


def self_check() -> None:
    root = Path(__file__).resolve().parents[1]
    mv = parse_ver(DEFAULT_MIN)
    for f in ("MIHOMO/template_remnawave.yaml", "MIHOMO/wl.yaml"):
        assert check_file(root / f, mv) == [], f
    bad = {
        "mixd-port": 1,
        "external-controller-routing-mark": 1,
        "dns": {"enable": True, "nameserver-polcy": {}, "listen-routing-mark": 1},
        "tun": {"exclude-pakage": [], "icmp-timeout": 1, "processors-per-channel": 1},
        "sniffer": {"sniff": {"TLS": {"port": [443]}}},
        "proxy-groups": [
            {"name": "a", "type": "fallback", "emtpy-fallback": "REJECT", "proxies": ["REJECT"]},
            {"name": "b", "type": "select", "default-selected": "x", "proxies": ["REJECT"],
             "remnawave": {"include-proxy": False}},
        ],
        "rule-providers": {"p": {"type": "http", "behaviour": "domain"}},
    }
    errs = check_doc(bad, mv)
    for needle in ("mixd-port", "nameserver-polcy", "exclude-pakage", "'port'", "emtpy-fallback",
                   "default-selected", "include-proxy", "behaviour", "external-controller-routing-mark",
                   "listen-routing-mark", "icmp-timeout", "processors-per-channel"):
        assert any(needle in e for e in errs), (needle, errs)
    at_28 = check_doc(bad, parse_ver("v1.19.28"))
    for gone in ("default-selected", "external-controller-routing-mark", "listen-routing-mark", "icmp-timeout"):
        assert not any(gone in e for e in at_28), (gone, at_28)
    assert any("processors-per-channel" in e for e in at_28), at_28
    assert not any("processors-per-channel" in e for e in check_doc(bad, parse_ver("v1.19.31")))
    print("check-config-keys: self-check ok")


def main(argv: list[str]) -> int:
    if argv == ["--self-check"]:
        self_check()
        return 0
    min_v = os.environ.get("MIHOMO_MIN_VERSION", DEFAULT_MIN)
    if len(argv) >= 2 and argv[0] == "--min-version":
        min_v, argv = argv[1], argv[2:]
    files = [Path(a) for a in argv] or [
        Path(__file__).resolve().parents[1] / "MIHOMO/template_remnawave.yaml",
        Path(__file__).resolve().parents[1] / "MIHOMO/wl.yaml",
    ]
    rc = 0
    for f in files:
        errs = check_file(f, parse_ver(min_v))
        for e in errs:
            print(f"❌ {f.name}: {e}", file=sys.stderr)
        if errs:
            rc = 1
        else:
            print(f"check-config-keys: {f.name} ok (min {min_v})")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
