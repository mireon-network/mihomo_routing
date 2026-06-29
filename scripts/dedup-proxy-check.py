#!/usr/bin/env python3
"""Проверка: безопасно ли удалить RULE-SET,...,PROXY, полагаясь на финальный MATCH,PROXY.

Удаление безопасно, только если домены списка НЕ перехватываются ни одним
правилом, стоящим НИЖЕ по порядку и ведущим в другой таргет (не PROXY).
Иначе такие домены сменят маршрут (PROXY → DIRECT/Игры/Youtube/...).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = ROOT / "rule-sets/mrs/text"
MANIFEST = ROOT / "rule-sets/mrs/manifest.yaml"
TEMPLATE = ROOT / "MIHOMO/template_remnawave.yaml"

CANDIDATES = ["google-play", "google-play-meta",
              "telegram", "games-proxy-rules"]


def id_to_file() -> dict[str, str]:
    m, cur = {}, None
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("- id:"):
            cur = s.split(":", 1)[1].strip()
        elif cur and s.startswith("file:"):
            m[cur] = s.split(":", 1)[1].strip()
    return m


def ordered_rules() -> list[tuple[str, str]]:
    out = []
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*-\s*RULE-SET,([^,]+),([^,#\n]+)", line)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def load_patterns(fid: str):
    p = TEXT / f"{fid}.list"
    if not p.is_file():
        return None
    pats = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("+."):
            pats.append(("incl", s[2:]))
        elif s.startswith("*."):
            pats.append(("wild", s[2:]))
        elif s.startswith("."):
            pats.append(("excl", s[1:]))
        elif s.startswith("full:"):
            pats.append(("exact", s[5:]))
        elif s.startswith("domain:"):
            pats.append(("incl", s[7:]))
        else:
            pats.append(("exact", s))
    return pats


def match(pat, d: str) -> bool:
    k, a = pat
    if k == "incl":
        return d == a or d.endswith("." + a)
    if k == "excl":
        return d != a and d.endswith("." + a)
    if k == "exact":
        return d == a
    if k == "wild":
        return d.endswith("." + a) and "." not in d[: -len(a) - 1]
    return False


def overlap(a_pats, b_pats) -> list[str]:
    hits = set()
    b_bases = [p[1] for p in b_pats]
    a_bases = [p[1] for p in a_pats]
    for base in a_bases:
        if any(match(pb, base) for pb in b_pats):
            hits.add(base)
    for base in b_bases:
        if any(match(pa, base) for pa in a_pats):
            hits.add(base)
    return sorted(hits)


def main() -> int:
    files = id_to_file()
    rules = ordered_rules()
    pos = {rid: i for i, (rid, _) in enumerate(rules)}

    for cand in CANDIDATES:
        cpats = load_patterns(files.get(cand, cand))
        if cpats is None:
            print(f"\n### {cand}: нет text/*.list (классический/процессный набор) — проверить вручную")
            continue
        i = pos.get(cand)
        if i is None:
            print(f"\n### {cand}: нет в правилах")
            continue
        later_non_proxy = [
            (rid, tgt) for rid, tgt in rules[i + 1:]
            if tgt != "PROXY"
        ]
        print(f"\n### {cand}  (паттернов: {len(cpats)})")
        any_hit = False
        for rid, tgt in later_non_proxy:
            lp = load_patterns(files.get(rid, rid))
            if lp is None:
                print(f"   · {rid} [{tgt}] — нет text/, вручную")
                continue
            h = overlap(cpats, lp)
            if h:
                any_hit = True
                shown = ", ".join(h[:8]) + (" …" if len(h) > 8 else "")
                print(f"   ⚠ ПЕРЕСЕЧЕНИЕ с {rid} [{tgt}]: {shown}")
        if not any_hit:
            print("   ✓ пересечений с mrs-списками ниже нет → можно удалить (упадёт в MATCH,PROXY)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
