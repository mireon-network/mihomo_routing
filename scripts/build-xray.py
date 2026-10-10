#!/usr/bin/env python3
"""Сборка XRAY/geosite.dat и XRAY/geoip.dat из MIHOMO/*.yaml и rule-sets/. MIHOMO не меняется.

Имя категории = id rule-set. JSON-шаблоны маршрутов не собираются.
"""
from __future__ import annotations

import ipaddress
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = ROOT / "rule-sets" / "mrs" / "text"
YAML = ROOT / "rule-sets" / "yaml"
OUT = ROOT / "XRAY"

PROFILES = (
    "MIHOMO/template_remnawave.yaml",
    "MIHOMO/wl.yaml",
)
# В шаблонах нет: только категория geosite.
EXTRA_GEOSITE = ("meta-reddit",)

PLAIN, REGEX, DOMAIN, FULL = 0, 1, 2, 3

GEOSITE: dict[str, list[tuple[int, str]]] = {}
GEOIP: dict[str, list[str]] = {}


def wildcard_regexp(body: str, suffix: bool) -> str:
    # mihomo: «*» — одна метка, «+.» — ещё и любой префикс слева.
    parts = [r"[^.]+" if label == "*" else re.escape(label) for label in body.split(".")]
    core = r"\.".join(parts)
    if suffix:
        return rf"(^|\.){core}$"
    return rf"^{core}$"


def parse_domain_line(line: str) -> tuple[int, str]:
    suffix = line.startswith("+.")
    body = line[2:] if suffix else line
    if "*" in body:
        return REGEX, wildcard_regexp(body, suffix)
    if suffix:
        return DOMAIN, body
    return FULL, body


def split_atoms(wrapped: str) -> list[str]:
    if not (wrapped.startswith("((") and wrapped.endswith("))")):
        raise SystemExit(f"не разобрал условие: {wrapped}")
    return wrapped[2:-2].split("),(")


def strip_comment(body: str) -> str:
    if " #" in body:
        return body.split(" #", 1)[0].rstrip()
    return body.rstrip()


def parse_template(text: str) -> tuple[dict[str, dict], list[str]]:
    providers: dict[str, dict] = {}
    rules: list[str] = []
    section = ""
    current: dict | None = None
    for line in text.splitlines():
        if line.startswith("rule-providers:"):
            section = "prov"
            continue
        if line.startswith("rules:"):
            if current:
                providers[current["name"]] = current
                current = None
            section = "rules"
            continue
        if section == "prov":
            if line.startswith("  ") and not line.startswith("   ") and ":" in line:
                if current:
                    providers[current["name"]] = current
                current = {"name": line.strip().split(":", 1)[0], "behavior": "", "payload": []}
            elif current and "behavior:" in line:
                current["behavior"] = line.split(":", 1)[1].strip()
            elif current and line.strip().startswith("- "):
                current["payload"].append(strip_comment(line.strip()[2:]))
        elif section == "rules" and line.startswith("  - "):
            rules.append(strip_comment(line[4:]))
    return providers, rules


def classify_classical(items: list[str]) -> tuple[list[tuple[int, str]], list[str], list[str], list[str]]:
    domains: list[tuple[int, str]] = []
    ips: list[str] = []
    ports: list[str] = []
    skipped: list[str] = []
    for item in items:
        kind, _, value = item.partition(",")
        if kind == "DOMAIN-SUFFIX":
            domains.append((DOMAIN, value))
        elif kind == "DOMAIN-KEYWORD":
            domains.append((PLAIN, value))
        elif kind == "DOMAIN-REGEX":
            domains.append((REGEX, value))
        elif kind == "DOMAIN":
            domains.append((FULL, value))
        elif kind in ("IP-CIDR", "IP-CIDR6"):
            ips.append(value)
        elif kind == "DST-PORT":
            ports.append(value)
        else:
            skipped.append(item)
    return domains, ips, ports, skipped


def list_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise SystemExit(f"нет {path}")
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            lines.append(s)
    return lines


def load_domain_list(name: str) -> list[tuple[int, str]]:
    domains = [parse_domain_line(s) for s in list_lines(TEXT / f"{name}.list")]
    if not domains:
        raise SystemExit(f"пустой {name}.list")
    return domains


def from_payload(behavior: str, payload: list[str]):
    if behavior == "domain":
        return [parse_domain_line(s) for s in payload], [], [], []
    if behavior == "ipcidr":
        return [], list(payload), [], []
    return classify_classical(payload)


def load_set(providers: dict[str, dict], name: str):
    prov = providers.get(name)
    if not prov:
        raise SystemExit(f"нет rule-provider {name}")
    if prov["payload"]:
        return from_payload(prov["behavior"], prov["payload"])
    behavior = prov["behavior"]
    if behavior == "classical":
        path = YAML / f"{name}.yaml"
        if not path.is_file():
            raise SystemExit(f"нет {path}")
        items = [
            strip_comment(line.strip()[2:])
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- ")
        ]
        return classify_classical(items)
    if behavior == "ipcidr":
        return [], list_lines(TEXT / f"{name}.list"), [], []
    return load_domain_list(name), [], [], []


def policy_of(rest: str) -> tuple[str, str]:
    end = rest.rfind("))")
    if end < 0:
        raise SystemExit(f"нет условия: {rest}")
    wrapped = rest[: end + 2]
    return wrapped, rest[end + 2 :].lstrip(",").strip()


def record_set(providers: dict[str, dict], name: str) -> None:
    domains, ips, _ports, _skipped = load_set(providers, name)
    if domains:
        GEOSITE[name] = domains
    if ips:
        GEOIP[name] = ips


def collect_categories(providers: dict[str, dict], src_rules: list[str]) -> None:
    for raw in src_rules:
        if raw.startswith("RULE-SET,"):
            record_set(providers, raw.split(",")[1])
        elif raw.startswith(("AND,", "OR,")):
            wrapped, _outbound = policy_of(raw.split(",", 1)[1])
            for atom in split_atoms(wrapped):
                if atom.startswith("RULE-SET,"):
                    record_set(providers, atom.split(",", 1)[1])


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def proto_len(field: int, payload: bytes) -> bytes:
    return bytes([(field << 3) | 2]) + varint(len(payload)) + payload


def proto_var(field: int, n: int) -> bytes:
    return bytes([field << 3]) + varint(n)


def domain_msg(typ: int, value: str) -> bytes:
    return proto_var(1, typ) + proto_len(2, value.encode())


def cidr_msg(cidr: str) -> bytes:
    network = ipaddress.ip_network(cidr, strict=False)
    return proto_len(1, network.network_address.packed) + proto_var(2, network.prefixlen)


def dat_code(code: str) -> bytes:
    # Xray делает strings.ToUpper и сравнивает байты кода в .dat
    return code.upper().encode()


def geosite_dat(categories: dict[str, list[tuple[int, str]]]) -> bytes:
    out = b""
    for code, domains in categories.items():
        body = proto_len(1, dat_code(code))
        for typ, value in domains:
            body += proto_len(2, domain_msg(typ, value))
        out += proto_len(1, body)
    return out


def geoip_dat(categories: dict[str, list[str]]) -> bytes:
    out = b""
    for code, cidrs in categories.items():
        body = proto_len(1, dat_code(code))
        for cidr in cidrs:
            body += proto_len(2, cidr_msg(cidr))
        out += proto_len(1, body)
    return out


def read_varint(buf: bytes, i: int) -> tuple[int, int]:
    n = shift = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7


def parse_fields(buf: bytes) -> list[tuple[int, int, object]]:
    fields: list[tuple[int, int, object]] = []
    i = 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            val, i = read_varint(buf, i)
        elif wire == 2:
            ln, i = read_varint(buf, i)
            val = buf[i : i + ln]
            i += ln
        else:
            raise SystemExit(f"wire {wire}")
        fields.append((field, wire, val))
    return fields


def decode_geosite(buf: bytes) -> dict[str, list[tuple[int, str]]]:
    found: dict[str, list[tuple[int, str]]] = {}
    for field, _, entry in parse_fields(buf):
        if field != 1:
            continue
        code = ""
        domains: list[tuple[int, str]] = []
        for f, _, val in parse_fields(entry):  # type: ignore[arg-type]
            if f == 1:
                code = val.decode()  # type: ignore[union-attr]
            elif f == 2:
                typ, value = 0, ""
                for df, _, dv in parse_fields(val):  # type: ignore[arg-type]
                    if df == 1:
                        typ = dv  # type: ignore[assignment]
                    elif df == 2:
                        value = dv.decode()  # type: ignore[union-attr]
                domains.append((typ, value))
        found[code] = domains
    return found


def decode_geoip(buf: bytes) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for field, _, entry in parse_fields(buf):
        if field != 1:
            continue
        code = ""
        cidrs: list[str] = []
        for f, _, val in parse_fields(entry):  # type: ignore[arg-type]
            if f == 1:
                code = val.decode()  # type: ignore[union-attr]
            elif f == 2:
                raw, prefix = b"", 0
                for cf, _, cv in parse_fields(val):  # type: ignore[arg-type]
                    if cf == 1:
                        raw = cv  # type: ignore[assignment]
                    elif cf == 2:
                        prefix = cv  # type: ignore[assignment]
                cidrs.append(f"{ipaddress.ip_address(raw)}/{prefix}")
        found[code] = cidrs
    return found


def collect_profile(src: str) -> None:
    text = (ROOT / src).read_text(encoding="utf-8")
    providers, src_rules = parse_template(text)
    collect_categories(providers, src_rules)


def self_check() -> None:
    domains, ips, ports, skipped = classify_classical(
        [
            "DOMAIN-SUFFIX,easebar.com",
            "IP-CIDR,172.232.25.131/32",
            "PROCESS-NAME,cs2.exe",
            "DST-PORT,25",
        ]
    )
    assert domains == [(DOMAIN, "easebar.com")]
    assert ips == ["172.232.25.131/32"]
    d, i, _, s = from_payload("domain", ["+.easebar.com", "+.deadorbit.net"])
    assert d == [(DOMAIN, "easebar.com"), (DOMAIN, "deadorbit.net")] and not i and not s
    _, i, _, s = from_payload("ipcidr", ["172.232.25.131/32"])
    assert i == ["172.232.25.131/32"] and not s
    assert ports == ["25"] and skipped == ["PROCESS-NAME,cs2.exe"]
    GEOSITE.clear()
    GEOIP.clear()
    collect_categories(
        {
            "only-proc": {"behavior": "classical", "payload": ["PROCESS-NAME,cs2.exe"]},
            "priv": {"behavior": "ipcidr", "payload": ["10.0.0.0/8"]},
        },
        [
            "PROCESS-NAME,cs2.exe,games",
            "RULE-SET,only-proc,🎮 Игры",
            "AND,((RULE-SET,priv),(NETWORK,tcp)),DIRECT",
            "MATCH,PROXY",
        ],
    )
    assert "only-proc" not in GEOSITE and "only-proc" not in GEOIP
    assert GEOIP["priv"] == ["10.0.0.0/8"] and "priv" not in GEOSITE
    assert parse_domain_line("+.reddit.com") == (DOMAIN, "reddit.com")
    assert parse_domain_line("router.asus.com") == (FULL, "router.asus.com")
    assert parse_domain_line("+.tinkoff.*") == (REGEX, r"(^|\.)tinkoff\.[^.]+$")
    assert classify_classical(["DOMAIN,example.com", "DOMAIN-KEYWORD,mtalk"])[0] == [
        (FULL, "example.com"),
        (PLAIN, "mtalk"),
    ]
    site = geosite_dat({"reddit": [(DOMAIN, "reddit.com"), (FULL, "www.reddit.com")]})
    assert decode_geosite(site)["REDDIT"] == [(DOMAIN, "reddit.com"), (FULL, "www.reddit.com")]
    ipdat = geoip_dat({"private": ["10.0.0.0/8", "::/127"]})
    assert decode_geoip(ipdat)["PRIVATE"] == ["10.0.0.0/8", "::/127"]


def main() -> None:
    self_check()
    GEOSITE.clear()
    GEOIP.clear()
    for src in PROFILES:
        collect_profile(src)
    for name in EXTRA_GEOSITE:
        GEOSITE[name] = load_domain_list(name)
    site = geosite_dat(GEOSITE)
    ipdat = geoip_dat(GEOIP)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "geosite.dat").write_bytes(site)
    (OUT / "geoip.dat").write_bytes(ipdat)
    decoded_site = decode_geosite(site)
    decoded_ip = decode_geoip(ipdat)
    assert (DOMAIN, "reddit.com") in decoded_site["META-REDDIT"]
    assert decoded_site["META-YOUTUBE"]
    assert "10.0.0.0/8" in decoded_ip["META-GEOIP-PRIVATE"]
    assert (REGEX, r"(^|\.)tinkoff\.[^.]+$") in decoded_site["SUMMARY-CATEGORY-RU"]
    print(
        f"geosite: {len(GEOSITE)} категорий, {len(site)} байт; geoip: {len(GEOIP)} категорий, {len(ipdat)} байт",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
