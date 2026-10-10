#!/usr/bin/env bash
# Локальная проверка шаблона БЕЗ пуша в main и БЕЗ сети.
# В mihomo -t уходит шаблон целиком. Подменяются только proxies (узлы ставит
# Remnawave) и URL провайдеров → type:file с локальными путями.
#   1) mihomo -t — dns, sniffer, группы, tun, find-process-mode и rules;
#   2) convert-ruleset — каждый .mrs/.yaml реально парсится mihomo (ловит битый контент).
#
# Использование: scripts/test-config-local.sh [MIHOMO/template_remnawave.yaml]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TPL="${1:-$ROOT/MIHOMO/template_remnawave.yaml}"
MIHOMO_BIN="${MIHOMO_BIN:-$ROOT/.tools/mihomo}"
[[ -x "$MIHOMO_BIN" ]] || MIHOMO_BIN="$(command -v mihomo)" || { echo "нет mihomo"; exit 1; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# 1) Шаблон целиком. Заглушка только у proxies, провайдеры → type:file.
python3 - "$TPL" "$ROOT" "$WORK" >"$WORK/config.yaml" <<'PY'
import re, sys, yaml
from pathlib import Path
tpl, root, work = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
doc = yaml.safe_load(open(tpl, encoding="utf-8"))
provs = doc.get("rule-providers", {}) or {}
def iter_str(obj: object):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str):
                yield key
            yield from iter_str(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_str(item)

def rule_sets_in(text: str) -> set[str]:
    found = set()
    for chunk in re.findall(r"rule-set:([^'\"\s#]+)", text):
        found.update(part for part in chunk.split(",") if part)
    for name in re.findall(r"RULE-SET,([^,)\s]+)", text):
        found.add(name)
    return found

def policy_of(rule: str) -> str:
    rule = rule.split(" #", 1)[0].strip()
    if rule.startswith(("AND,", "OR,")):
        end = rule.rfind("))")
        if end < 0:
            return ""
        pol = rule[end + 2 :].lstrip(",").strip()
    else:
        parts = [part.strip() for part in rule.split(",")]
        if parts and parts[-1] == "no-resolve":
            parts = parts[:-1]
        pol = parts[-1] if len(parts) >= 2 else ""
    return pol.removesuffix(",no-resolve").strip()

builtins = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE"}
groups = {g.get("name") for g in (doc.get("proxy-groups") or []) if g.get("name")}
bad_rules = sorted(rule_sets_in("\n".join(iter_str(doc.get("dns") or {}))) - set(provs))
bad_rules += sorted(
    name for rule in (doc.get("rules") or []) for name in re.findall(r"RULE-SET,([^,)\s]+)", str(rule))
    if name not in provs
)
if bad_rules:
    print("MISSING_RULE_SETS:", sorted(set(bad_rules)), file=sys.stderr)
    sys.exit(2)
bad_policies = sorted({
    pol
    for rule in (doc.get("rules") or [])
    if (pol := policy_of(str(rule))) and pol not in builtins and pol not in groups
})
if bad_policies:
    print("MISSING_POLICIES:", bad_policies, file=sys.stderr)
    sys.exit(2)
broken = [
    str(rule)
    for rule in (doc.get("rules") or [])
    if str(rule).startswith(("AND,", "OR,")) and not policy_of(str(rule))
]
if broken:
    print("BROKEN_RULES:", broken, file=sys.stderr)
    sys.exit(2)

doc["proxies"] = [{"name": "DUMMY", "type": "socks5", "server": "127.0.0.1", "port": 1080}]
local_provs = {}
missing = []
for name, p in provs.items():
    if p.get("type") == "inline":
        local_provs[name] = p
        continue
    url = p.get("url", "")
    sub = url.split("@main/", 1)[1] if "@main/" in url else None
    local = (root / sub) if sub else None
    if not local or not local.is_file():
        missing.append((name, sub)); continue
    local_provs[name] = {
        "type": "file", "behavior": p.get("behavior", "domain"),
        "format": p.get("format", "yaml"), "path": str(local),
    }
doc["rule-providers"] = local_provs
yaml.safe_dump(doc, sys.stdout, allow_unicode=True, sort_keys=False)
if missing:
    print("MISSING_FILES:", missing, file=sys.stderr)
    sys.exit(2)
print(f"providers={len(local_provs)}", file=sys.stderr)
PY

echo "→ [1/2] mihomo -t (структура + ссылки)"
SAFE_PATHS="$ROOT" "$MIHOMO_BIN" -t -d "$WORK" -f "$WORK/config.yaml"

echo "→ [2/2] парсинг содержимого каждого файла (convert-ruleset)"
rc=0
python3 - "$TPL" "$ROOT" <<'PY' >"$WORK/files.tsv"
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1], encoding="utf-8")); root = sys.argv[2]
for name, p in (doc.get("rule-providers") or {}).items():
    if p.get("type") == "inline":
        print(f"{name}\tinline\t-\t-")
        continue
    url = p.get("url", "")
    if "@main/" not in url: continue
    print(f"{name}\t{p.get('behavior','domain')}\t{p.get('format','yaml')}\t{root}/{url.split('@main/',1)[1]}")
PY
while IFS=$'\t' read -r name behavior format path; do
  if [[ "$behavior" == "inline" ]]; then
    printf "   %-28s %-9s %-6s %s\n" "$name" "inline" "-" "ok(inline)"
    continue
  fi
  # classical mrs не поддерживается — classical валидируем как yaml-парс (mihomo читает),
  # domain/ipcidr конвертируем в mrs (полноценный парс контента).
  if [[ "$behavior" == "classical" ]]; then
    python3 -c "import yaml,sys; d=yaml.safe_load(open('$path')); assert isinstance(d.get('payload'),list)" \
      && st="ok(classical-yaml)" || { st="FAIL"; rc=1; }
  else
    "$MIHOMO_BIN" convert-ruleset "$behavior" "$format" "$path" "$WORK/_o.mrs" >/dev/null 2>&1 \
      && st="ok" || { st="FAIL"; rc=1; }
  fi
  printf "   %-28s %-9s %-6s %s\n" "$name" "$behavior" "$format" "$st"
  [[ "$st" == FAIL* ]] && echo "      !! битый: $path"
done <"$WORK/files.tsv"

[[ $rc -eq 0 ]] && echo "✅ всё валидно" || echo "❌ есть ошибки"
exit $rc
