#!/usr/bin/env bash
# Throwaway-ветки <источник>-cdn и <источник>-debug от текущего HEAD (live-тест без merge в main).
#
#   ./scripts/deploy-test-branches.sh              # текущая ветка, remote origin
#   ./scripts/deploy-test-branches.sh origin       # текущая ветка, remote origin
#   ./scripts/deploy-test-branches.sh routing-v2   # явная исходная ветка
#
# *-cdn   — CDN-URL rule-sets → <owner>/<repo>@<ветка>-cdn
# *-debug — то же + include-all для Remnawave и селектор 📡 UDP (patch-include-proxies.py)
#
# При push в любую ветку (кроме *-cdn/*-debug) CI обновляет обе throwaway-ветки.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="origin"
SRC=""

if [[ $# -ge 1 && "$1" != origin && "$1" != fork ]]; then
  SRC="$1"
  REMOTE="${2:-origin}"
elif [[ $# -ge 1 ]]; then
  REMOTE="$1"
fi

if [[ -z "$SRC" ]]; then
  SRC="${GITHUB_REF_NAME:-$(git -C "$ROOT" branch --show-current)}"
fi
[[ -n "$SRC" ]] || { echo "deploy-test-branches: не удалось определить исходную ветку" >&2; exit 1; }

owner_repo_from_remote() {
  local url
  url="$(git -C "$ROOT" remote get-url --push "$REMOTE")"
  OWNER_REPO="$(printf '%s' "$url" | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')"
  [[ "$OWNER_REPO" == */* ]] || { echo "не распарсил owner/repo из '$url' (remote $REMOTE)" >&2; exit 1; }
  CDN="https://cdn.jsdelivr.net/gh/${OWNER_REPO}"
}

rewrite_cdn_urls_in_files() {
  local owner_repo="$1" br="$2"
  shift 2
  python3 - "$owner_repo" "$br" "$@" <<'PY'
import sys
owner_repo, br, *files = sys.argv[1], sys.argv[2], *sys.argv[3:]
src = "mireon-network/mihomo_routing@main/"
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
}

print_client_urls() {
  local br="$1"
  echo
  echo "Готово. Вставь в клиент/Remnawave (ветка @${br}):"
  echo "  ${CDN}@${br}/MIHOMO/template_remnawave.yaml"
  echo "  ${CDN}@${br}/MIHOMO/wl.yaml"
  echo
  echo "Репозиторий ${OWNER_REPO} должен быть ПУБЛИЧНЫМ (иначе jsDelivr не отдаст)."
  echo "Повторный деплой в ту же ветку кэшируется jsDelivr ~12h — сбрось кэш:"
  echo "  grep -oE 'https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main[^\" ]+' MIHOMO/template_remnawave.yaml \\"
  echo "    | sed 's#mireon-network/mihomo_routing@main#${OWNER_REPO}@${br}#' | sort -u | xargs ./scripts/cdn-purge.sh --url"
}

deploy_cdn_branch() {
  local br="$1" wt
  owner_repo_from_remote
  wt="$(mktemp -d)"
  trap 'git -C "$ROOT" worktree remove --force "$wt" 2>/dev/null || true; rm -rf "$wt"' EXIT

  git -C "$ROOT" worktree prune
  git -C "$ROOT" worktree add -f -B "$br" "$wt" HEAD >/dev/null

  rewrite_cdn_urls_in_files "$OWNER_REPO" "$br" "$wt"/MIHOMO/*.yaml

  git -C "$wt" add -A
  if ! git -C "$wt" diff --cached --quiet; then
    git -C "$wt" commit -q -m "test(cdn): internal URLs → ${OWNER_REPO}@${br} (throwaway, do NOT merge)"
  fi
  git -C "$wt" push -f "$REMOTE" "$br"
  print_client_urls "$br"
  git -C "$ROOT" worktree remove --force "$wt" 2>/dev/null || true
  rm -rf "$wt"
  trap - EXIT
}

deploy_debug_branch() {
  local br="$1" wt
  owner_repo_from_remote
  wt="$(mktemp -d)"
  trap 'git -C "$ROOT" worktree remove --force "$wt" 2>/dev/null || true; rm -rf "$wt"' EXIT

  git -C "$ROOT" worktree prune
  git -C "$ROOT" worktree add -f -B "$br" "$wt" HEAD >/dev/null

  local templates=(
    "$wt/MIHOMO/template_remnawave.yaml"
    "$wt/MIHOMO/wl.yaml"
  )
  rewrite_cdn_urls_in_files "$OWNER_REPO" "$br" "${templates[@]}"
  python3 "$ROOT/scripts/patch-include-proxies.py" "${templates[@]}"

  git -C "$wt" add -A
  if ! git -C "$wt" diff --cached --quiet; then
    git -C "$wt" commit -q -m "test(debug): CDN → ${OWNER_REPO}@${br}, include-all + UDP selector (throwaway, do NOT merge)"
  fi
  git -C "$wt" push -f "$REMOTE" "$br"
  print_client_urls "$br"
  git -C "$ROOT" worktree remove --force "$wt" 2>/dev/null || true
  rm -rf "$wt"
  trap - EXIT
}

deploy_cdn_branch "${SRC}-cdn"
deploy_debug_branch "${SRC}-debug"
