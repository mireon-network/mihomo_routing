#!/usr/bin/env python3
"""Анализ покрытия доменных rule-set'ов для дедупликации.

Находит списки, полностью покрытые более приоритетным набором с тем же
таргетом маршрутизации. Приоритет: MetaCubeX > roscomvpn > legiz/davoyan > custom.
Только анализ — ничего не удаляет.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MRS = ROOT / "rule-sets/mrs"
MANIFEST = MRS / "manifest.yaml"
TEXT = MRS / "text"
TEMPLATE = ROOT / "MIHOMO/template_remnawave.yaml"


def parse_manifest() -> list[dict]:
    sets, cur = [], None
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("- id:"):
            if cur:
                sets.append(cur)
            cur = {"id": s.split(":", 1)[1].strip()}
        elif cur is not None and ":" in s and not s.startswith("#"):
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            if k in ("id", "behavior", "file", "url", "src"):
                cur[k] = v
    if cur:
        sets.append(cur)
    return sets


def priority(url: str) -> int:
    if "MetaCubeX" in url:
        return 4
    if "hydraponique" in url:
        return 3
    if "legiz-ru" in url or "Davoyan" in url or "based_by_davoyan" in url:
        return 2
    return 1


def parse_targets() -> dict[str, str]:
    tgt = {}
    for m in re.finditer(r"-\s*RULE-SET,([^,]+),([^,#\n]+)", TEMPLATE.read_text(encoding="utf-8")):
        tgt[m.group(1).strip()] = m.group(2).strip()
    return tgt


def load_patterns(path: Path) -> list[tuple[str, str]]:
    pats = []
    for raw in path.read_text(encoding="utf-8").splitlines():
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


def under(d: str, base: str) -> bool:
    """d == base или d — поддомен base."""
    return d == base or d.endswith("." + base)


def covers(a: tuple[str, str], b: tuple[str, str]) -> bool:
    ka, da = a
    kb, db = b
    if ka == "incl":  # +.da покрывает da и все его поддомены — любой kind B
        return under(db, da)
    if ka == "excl":  # .da покрывает строгие поддомены da
        if kb == "exact":
            return db.endswith("." + da)
        if kb in ("incl", "excl", "wild"):
            return db == da or db.endswith("." + da)
    if ka == "exact":
        return kb == "exact" and da == db
    if ka == "wild":
        return kb == "wild" and da == db
    return False


def covered_by_union(b_pats, a_pats) -> bool:
    return all(any(covers(a, b) for a in a_pats) for b in b_pats)


def covers_list(a_pats, b_pats) -> bool:
    return covered_by_union(b_pats, a_pats)


def main() -> int:
    sets = parse_manifest()
    targets = parse_targets()
    # только domain-наборы, у которых есть text/*.list
    domain_sets = []
    for s in sets:
        if s.get("behavior") != "domain":
            continue
        p = TEXT / f"{s['file']}.list"
        if not p.is_file():
            continue
        domain_sets.append(
            {
                "id": s["id"],
                "file": s["file"],
                "prio": priority(s["url"]),
                "target": targets.get(s["id"], "?"),
                "pats": load_patterns(p),
            }
        )

    print(f"Доменных наборов с text/: {len(domain_sets)}\n")
    orphan = [b for b in domain_sets if b["target"] == "?"]
    domain_sets = [b for b in domain_sets if b["target"] != "?"]
    redundant = []
    for b in domain_sets:
        # кандидаты-покрыватели с тем же таргетом:
        #  - строго выше по приоритету; ИЛИ
        #  - равный приоритет, но строгое надмножество (тай-брейк: больше паттернов,
        #    при равенстве — лексикографически меньший id остаётся)
        cand = []
        for a in domain_sets:
            if a["id"] == b["id"] or a["target"] != b["target"]:
                continue
            if a["prio"] > b["prio"]:
                cand.append(a)
            elif a["prio"] == b["prio"] and covers_list(a["pats"], b["pats"]):
                if not covers_list(b["pats"], a["pats"]):
                    cand.append(a)  # a строго больше
                elif (len(a["pats"]), b["id"]) > (len(b["pats"]), a["id"]):
                    cand.append(a)  # эквивалентны — оставляем по тай-брейку
        if not cand:
            continue
        union = [p for a in cand for p in a["pats"]]
        if covered_by_union(b["pats"], union):
            who = ", ".join(
                a["id"] for a in cand if covered_by_union(b["pats"], a["pats"])
            ) or "(union)"
            redundant.append((b, who))

    # Проверка: каждый удаляемый должен быть покрыт ОСТАЮЩИМИСЯ (не другим удаляемым).
    remove_ids = {b["id"] for b, _ in redundant}
    changed = True
    while changed:
        changed = False
        for b, _ in list(redundant):
            survivors = [
                a for a in domain_sets
                if a["id"] not in remove_ids and a["target"] == b["target"]
            ]
            if not covered_by_union(b["pats"], [p for a in survivors for p in a["pats"]]):
                remove_ids.discard(b["id"])
                redundant = [(x, w) for x, w in redundant if x["id"] != b["id"]]
                changed = True

    if not redundant:
        print("Полностью покрытых списков не найдено.")
    else:
        print("ИЗБЫТОЧНЫЕ (полностью покрыты остающимся набором с тем же таргетом):\n")
        for b, who in redundant:
            survivors = [
                a["id"] for a in domain_sets
                if a["id"] not in remove_ids and a["target"] == b["target"]
                and covered_by_union(b["pats"], a["pats"])
            ]
            print(f"  ✗ {b['id']:24s} target={b['target']:12s} prio={b['prio']}  ⊆ {', '.join(survivors)}")

    if orphan:
        print("\nОСИРОТЕВШИЕ (нет в правилах, target=?) — не трогаю автоматически:")
        for b in orphan:
            print(f"  ? {b['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
