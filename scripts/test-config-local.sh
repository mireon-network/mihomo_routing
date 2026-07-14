#!/usr/bin/env bash
# Локальная проверка rule-providers/rules БЕЗ пуша в main и БЕЗ сети.
# Все провайдеры подменяются на type:file с локальными путями репозитория, затем:
#   1) mihomo -t — структура конфига + ссылки RULE-SET ↔ провайдеры;
#   2) convert-ruleset — каждый .mrs/.yaml реально парсится mihomo (ловит битый контент).
#
# Использование: scripts/test-config-local.sh [MIHOMO/template_remnawave.yaml]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TPL="${1:-$ROOT/MIHOMO/template_remnawave.yaml}"
MIHOMO_BIN="${MIHOMO_BIN:-$ROOT/.tools/mihomo}"
[[ -x "$MIHOMO_BIN" ]] || MIHOMO_BIN="$(command -v mihomo)" || { echo "нет mihomo"; exit 1; }

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# 1) Минимальный конфиг: провайдеры → type:file (локальные пути), заглушка-прокси.
python3 - "$TPL" "$ROOT" "$WORK" >"$WORK/config.yaml" <<'PY'
import sys, yaml
from pathlib import Path
tpl, root, work = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
doc = yaml.safe_load(open(tpl, encoding="utf-8"))
provs = doc.get("rule-providers", {}) or {}
out = {
    "mixed-port": 7890, "mode": "rule", "log-level": "warning",
    "proxies": [{"name": "DUMMY", "type": "socks5", "server": "127.0.0.1", "port": 1080}],
    "proxy-groups": [{"name": "G", "type": "select", "proxies": ["DUMMY", "DIRECT"]}],
    "rule-providers": {}, "rules": [],
}
missing = []
for name, p in provs.items():
    if p.get("type") == "inline":
        out["rule-providers"][name] = p
        out["rules"].append(f"RULE-SET,{name},G")
        continue
    url = p.get("url", "")
    sub = url.split("@main/", 1)[1] if "@main/" in url else None
    local = (root / sub) if sub else None
    if not local or not local.is_file():
        missing.append((name, sub)); continue
    out["rule-providers"][name] = {
        "type": "file", "behavior": p.get("behavior", "domain"),
        "format": p.get("format", "yaml"), "path": str(local),
    }
    out["rules"].append(f"RULE-SET,{name},G")
out["rules"].append("MATCH,G")
yaml.safe_dump(out, sys.stdout, allow_unicode=True, sort_keys=False)
if missing:
    print("MISSING_FILES:", missing, file=sys.stderr)
    sys.exit(2)
print(f"providers={len(out['rule-providers'])}", file=sys.stderr)
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
