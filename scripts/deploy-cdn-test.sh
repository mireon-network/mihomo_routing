#!/usr/bin/env bash
# Live-тест на КЛИЕНТЕ без пуша в main.
# Делает throwaway-ветку от текущего HEAD, переписывает внутренние CDN-URL шаблонов
# (mireon-network/mihomo_routing@main → <owner>/<repo>@<ветка>) и пушит её в указанный
# remote. Твой основной чекаут не трогается — всё в отдельном git worktree.
# Ветку НЕ мёржить в main (в ней подменены URL).
#
# Пушит в remote, КУДА У ТЕБЯ ЕСТЬ ДОСТУП (свой форк/личный репо). jsDelivr отдаёт
# любой ПУБЛИЧНЫЙ GitHub-репозиторий.
#
# Сначала закоммить правки в свою ветку (не в main!), затем:
#   ./scripts/deploy-cdn-test.sh                 # ветка cdn-test, remote origin
#   ./scripts/deploy-cdn-test.sh my-test fork    # ветка my-test, remote fork
#
# В конце печатает клиентский URL шаблона.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BR="${1:-cdn-test}"
REMOTE="${2:-origin}"

# owner/repo из push-URL выбранного remote (https или ssh)
URL="$(git -C "$ROOT" remote get-url --push "$REMOTE")"
OWNER_REPO="$(printf '%s' "$URL" | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')"
[[ "$OWNER_REPO" == */* ]] || { echo "не распарсил owner/repo из '$URL' (remote $REMOTE)"; exit 1; }
CDN="https://cdn.jsdelivr.net/gh/${OWNER_REPO}"

WT="$(mktemp -d)"
trap 'git -C "$ROOT" worktree remove --force "$WT" 2>/dev/null || true; rm -rf "$WT"' EXIT

git -C "$ROOT" worktree prune
git -C "$ROOT" worktree add -f -B "$BR" "$WT" HEAD >/dev/null

python3 - "$WT" "$OWNER_REPO" "$BR" <<'PY'
import sys, glob, os
wt, owner_repo, br = sys.argv[1], sys.argv[2], sys.argv[3]
src = "mireon-network/mihomo_routing@main/"
dst = f"{owner_repo}@{br}/"
n = 0
for f in glob.glob(os.path.join(wt, "MIHOMO", "*.yaml")):
    s = open(f, encoding="utf-8").read()
    n += s.count(src)
    r = s.replace(src, dst)
    if r != s:
        open(f, "w", encoding="utf-8").write(r)
print(f"переписано {n} внутренних URL → gh/{dst}")
PY

git -C "$WT" add -A
git -C "$WT" commit -q -m "test(cdn): internal URLs → ${OWNER_REPO}@${BR} (throwaway, do NOT merge)"
git -C "$WT" push -f "$REMOTE" "$BR"

echo
echo "Готово. Вставь в клиент/Remnawave (вместо @main):"
echo "  ${CDN}@${BR}/MIHOMO/template_remnawave.yaml"
echo "  ${CDN}@${BR}/MIHOMO/wl.yaml"
echo
echo "Репозиторий ${OWNER_REPO} должен быть ПУБЛИЧНЫМ (иначе jsDelivr не отдаст)."
echo "Повторный деплой в ту же ветку кэшируется jsDelivr ~12ч — сбрось кэш:"
echo "  grep -oE 'https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main[^\" ]+' MIHOMO/template_remnawave.yaml \\"
echo "    | sed 's#mireon-network/mihomo_routing@main#${OWNER_REPO}@${BR}#' | sort -u | xargs ./scripts/cdn-purge.sh --url"
