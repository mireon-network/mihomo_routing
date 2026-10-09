#!/usr/bin/env python3
"""Сборка XRAY/ из правил MIHOMO/*.yaml и rule-sets/. MIHOMO не меняется.

Домены и IP наборов — категории geosite.dat / geoip.dat.
В JSON только geosite:<имя> и geoip:<имя>. Имя категории = id rule-set.
Одиночные домены внутри OR/AND остаются как есть. Процессы — в *.skipped.txt.
"""
from __future__ import annotations

import ipaddress
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = ROOT / "rule-sets" / "mrs" / "text"
YAML = ROOT / "rule-sets" / "yaml"
OUT = ROOT / "XRAY"

PROFILES = (
    ("MIHOMO/template_remnawave.yaml", "template_remnawave"),
    ("MIHOMO/wl.yaml", "wl"),
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


def skip_note(prefix: str, skipped: list[str]) -> str:
    procs = [s for s in skipped if s.startswith("PROCESS")]
    other = [s for s in skipped if not s.startswith("PROCESS")]
    bits = []
    if procs:
        bits.append(f"пропущено процессов {len(procs)}")
    if other:
        bits.append("не перенесено: " + ", ".join(other))
    return f"{prefix}: " + "; ".join(bits)


def field(outbound: str, **parts: object) -> dict:
    rule: dict = {"type": "field", "outboundTag": outbound}
    rule.update(parts)
    return rule


def emit_parts(name: str, outbound: str, domains, ips, ports) -> list[dict]:
    rules: list[dict] = []
    if domains:
        GEOSITE[name] = domains
        rules.append(field(outbound, domain=[f"geosite:{name}"]))
    if ips:
        GEOIP[name] = ips
        rules.append(field(outbound, ip=[f"geoip:{name}"]))
    if ports:
        rules.append(field(outbound, port=",".join(ports)))
    return rules


def atom_rule(providers: dict[str, dict], atom: str, outbound: str) -> tuple[dict | None, str | None]:
    kind, _, value = atom.partition(",")
    if kind == "NETWORK":
        return field(outbound, network=value.lower()), None
    if kind == "DST-PORT":
        return field(outbound, port=value), None
    if kind == "DOMAIN-SUFFIX":
        return field(outbound, domain=["domain:" + value]), None
    if kind == "DOMAIN-KEYWORD":
        return field(outbound, domain=["keyword:" + value]), None
    if kind == "DOMAIN":
        return field(outbound, domain=["full:" + value]), None
    if kind == "RULE-SET":
        domains, ips, ports, skipped = load_set(providers, value)
        if skipped and not (domains or ips or ports):
            return None, skip_note(f"{atom} → {outbound}", skipped)
        rules = emit_parts(value, outbound, domains, ips, ports)
        if len(rules) != 1:
            raise SystemExit(f"AND/OR RULE-SET {value} дал {len(rules)} правил, нужно одно")
        note = skip_note(atom, skipped) if skipped else None
        return rules[0], note
    return None, f"не перенесено: {atom} → {outbound}"


def logic_rule(providers: dict[str, dict], wrapped: str, outbound: str, op: str) -> tuple[list[dict], list[str]]:
    atoms = split_atoms(wrapped)
    if op == "OR":
        rules: list[dict] = []
        notes: list[str] = []
        for atom in atoms:
            rule, note = atom_rule(providers, atom, outbound)
            if rule:
                rules.append(rule)
            if note:
                notes.append(note)
        return rules, notes
    merged: dict = {"type": "field", "outboundTag": outbound}
    notes: list[str] = []
    for atom in atoms:
        rule, note = atom_rule(providers, atom, outbound)
        if note:
            notes.append(note)
        if not rule:
            continue
        for key, val in rule.items():
            if key in ("type", "outboundTag"):
                continue
            merged[key] = val
    if len(merged) == 2:
        return [], notes or [f"AND → {outbound}: нечего переносить"]
    if "ip" in merged and "port" not in merged:
        names = [atom.split(",", 1)[1] for atom in atoms if atom.startswith("RULE-SET,")]
        if names:
            notes.append(f"{names[0]}: geoip без no-resolve — только уже известный IP")
    return [merged], notes


def policy_of(rest: str) -> tuple[str, str]:
    end = rest.rfind("))")
    if end < 0:
        raise SystemExit(f"нет условия: {rest}")
    wrapped = rest[: end + 2]
    return wrapped, rest[end + 2 :].lstrip(",").strip()


def build(providers: dict[str, dict], src_rules: list[str]) -> tuple[list[dict], list[str]]:
    rules: list[dict] = []
    notes: list[str] = []
    for raw in src_rules:
        if raw.startswith("RULE-SET,"):
            parts = raw.split(",")
            name, outbound = parts[1], parts[2]
            no_resolve = "no-resolve" in parts[3:]
            domains, ips, ports, skipped = load_set(providers, name)
            if skipped:
                notes.append(skip_note(f"RULE-SET,{name} → {outbound}", skipped))
            made = emit_parts(name, outbound, domains, ips, ports)
            if any("ip" in rule and "port" not in rule for rule in made) and not no_resolve:
                notes.append(f"{name}: geoip без no-resolve — только уже известный IP")
            if not made and not skipped:
                notes.append(f"RULE-SET,{name} → {outbound}: в xray пусто")
            rules.extend(made)
        elif raw.startswith("IP-CIDR,") or raw.startswith("IP-CIDR6,"):
            parts = raw.split(",")
            rules.append(field(parts[2], ip=[parts[1]]))
        elif raw.startswith("AND,") or raw.startswith("OR,"):
            op, rest = raw.split(",", 1)
            wrapped, outbound = policy_of(rest)
            made, extra = logic_rule(providers, wrapped, outbound, op)
            rules.extend(made)
            notes.extend(extra)
        elif raw.startswith("MATCH,"):
            outbound = raw.split(",", 1)[1]
            # пустой field xray-core отвергает: "this rule has no effective fields"
            rules.append(field(outbound, network="tcp,udp"))
        elif raw.startswith("PROCESS-"):
            notes.append(raw)
        else:
            notes.append(f"не перенесено: {raw}")
    return rules, notes


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


def geosite_dat(categories: dict[str, list[tuple[int, str]]]) -> bytes:
    out = b""
    for code, domains in categories.items():
        body = proto_len(1, code.encode())
        for typ, value in domains:
            body += proto_len(2, domain_msg(typ, value))
        out += proto_len(1, body)
    return out


def geoip_dat(categories: dict[str, list[str]]) -> bytes:
    out = b""
    for code, cidrs in categories.items():
        body = proto_len(1, code.encode())
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


def write_profile(src: str, name: str) -> None:
    text = (ROOT / src).read_text(encoding="utf-8")
    providers, src_rules = parse_template(text)
    rules, notes = build(providers, src_rules)
    doc = {"routing": {"domainStrategy": "AsIs", "rules": rules}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / f"{name}.skipped.txt").write_text(
        "\n".join(notes) + ("\n" if notes else ""),
        encoding="utf-8",
    )
    print(f"{name}: rules={len(rules)} skipped={len(notes)}", file=sys.stderr)


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
    assert parse_domain_line("+.reddit.com") == (DOMAIN, "reddit.com")
    assert parse_domain_line("router.asus.com") == (FULL, "router.asus.com")
    assert parse_domain_line("+.tinkoff.*") == (REGEX, r"(^|\.)tinkoff\.[^.]+$")
    assert classify_classical(["DOMAIN,example.com", "DOMAIN-KEYWORD,mtalk"])[0] == [
        (FULL, "example.com"),
        (PLAIN, "mtalk"),
    ]
    site = geosite_dat({"reddit": [(DOMAIN, "reddit.com"), (FULL, "www.reddit.com")]})
    assert decode_geosite(site)["reddit"] == [(DOMAIN, "reddit.com"), (FULL, "www.reddit.com")]
    ipdat = geoip_dat({"private": ["10.0.0.0/8", "::/127"]})
    assert decode_geoip(ipdat)["private"] == ["10.0.0.0/8", "::/127"]


def main() -> None:
    self_check()
    GEOSITE.clear()
    GEOIP.clear()
    for src, name in PROFILES:
        write_profile(src, name)
    for name in EXTRA_GEOSITE:
        GEOSITE[name] = load_domain_list(name)
    site = geosite_dat(GEOSITE)
    ipdat = geoip_dat(GEOIP)
    (OUT / "geosite.dat").write_bytes(site)
    (OUT / "geoip.dat").write_bytes(ipdat)
    decoded_site = decode_geosite(site)
    decoded_ip = decode_geoip(ipdat)
    assert (DOMAIN, "reddit.com") in decoded_site["meta-reddit"]
    assert decoded_site["meta-youtube"]
    assert "10.0.0.0/8" in decoded_ip["meta-geoip-private"]
    youtube = json.loads((OUT / "template_remnawave.json").read_text(encoding="utf-8"))
    rules = youtube["routing"]["rules"]
    assert any(r.get("domain") == ["geosite:meta-youtube"] for r in rules)
    assert not any(r.get("domain") == ["geosite:meta-reddit"] for r in rules)
    assert all(len(r.get("domain", [])) < 8 for r in rules)
    assert rules[-1] == {"type": "field", "outboundTag": "PROXY", "network": "tcp,udp"}
    assert (REGEX, r"(^|\.)tinkoff\.[^.]+$") in decoded_site["summary-category-ru"]
    print(
        f"geosite: {len(GEOSITE)} категорий, {len(site)} байт; geoip: {len(GEOIP)} категорий, {len(ipdat)} байт",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
