#!/usr/bin/env bash
# Throwaway-ветка <источник>-debug от текущего HEAD:
#   • CDN-URL в template_remnawave.yaml и wl.yaml → <owner>/<repo>@<ветка>-debug
#   • remnawave.include-proxies: true в видимых select-группах (все узлы в селекторах)
#
#   ./scripts/deploy-debug.sh                  # <текущая>-debug
#   ./scripts/deploy-debug.sh routing-v2-debug # явное имя throwaway-ветки
# При push в любую ветку (кроме *-cdn/*-debug) — CI обновляет <ветка>-cdn и <ветка>-debug.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${1:-}" ]]; then
  BR="$1"
  REMOTE="${2:-origin}"
else
  SRC="${GITHUB_REF_NAME:-$(git -C "$ROOT" branch --show-current)}"
  [[ -n "$SRC" ]] || { echo "deploy-debug: укажите ветку или checkout исходной ветки" >&2; exit 1; }
  BR="${SRC}-debug"
  REMOTE="${2:-origin}"
fi

URL="$(git -C "$ROOT" remote get-url --push "$REMOTE")"
OWNER_REPO="$(printf '%s' "$URL" | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')"
[[ "$OWNER_REPO" == */* ]] || { echo "не распарсил owner/repo из '$URL' (remote $REMOTE)"; exit 1; }
CDN="https://cdn.jsdelivr.net/gh/${OWNER_REPO}"

WT="$(mktemp -d)"
trap 'git -C "$ROOT" worktree remove --force "$WT" 2>/dev/null || true; rm -rf "$WT"' EXIT

git -C "$ROOT" worktree prune
git -C "$ROOT" worktree add -f -B "$BR" "$WT" HEAD >/dev/null

TEMPLATES=(
  "$WT/MIHOMO/template_remnawave.yaml"
  "$WT/MIHOMO/wl.yaml"
)

python3 - "$OWNER_REPO" "$BR" "${TEMPLATES[@]}" <<'PY'
import sys
src = "mireon-network/mihomo_routing@main/"
owner_repo, br, *files = sys.argv[1], sys.argv[2], *sys.argv[3:]
dst = f"{owner_repo}@{br}/"
n = 0
for f in files:
    s = open(f, encoding="utf-8").read()
    n += s.count(src)
    r = s.replace(src, dst)
    if r != s:
        open(f, "w", encoding="utf-8").write(r)
print(f"переписано {n} внутренних URL → gh/{dst}")
PY

python3 "$ROOT/scripts/patch-include-proxies.py" "${TEMPLATES[@]}"

git -C "$WT" add -A
if ! git -C "$WT" diff --cached --quiet; then
  git -C "$WT" commit -q -m "test(debug): CDN → ${OWNER_REPO}@${BR}, include-proxies (throwaway, do NOT merge)"
fi
git -C "$WT" push -f "$REMOTE" "$BR"

echo
echo "Готово. Вставь в клиент/Remnawave (ветка @${BR}):"
echo "  ${CDN}@${BR}/MIHOMO/template_remnawave.yaml"
echo "  ${CDN}@${BR}/MIHOMO/wl.yaml"
echo
echo "Репозиторий ${OWNER_REPO} должен быть ПУБЛИЧНЫМ (иначе jsDelivr не отдаст)."
echo "Повторный деплой в ту же ветку кэшируется jsDelivr ~12ч — сбрось кэш:"
echo "  grep -oE 'https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main[^\" ]+' MIHOMO/template_remnawave.yaml \\"
echo "    | sed 's#mireon-network/mihomo_routing@main#${OWNER_REPO}@${BR}#' | sort -u | xargs ./scripts/cdn-purge.sh --url"
