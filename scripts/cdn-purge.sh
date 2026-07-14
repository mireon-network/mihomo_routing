#!/usr/bin/env bash
# Сброс кэша jsDelivr для файлов репозитория (purge API).
# Использование:
#   ./scripts/cdn-purge.sh rule-sets/yaml/ai.yaml
#   ./scripts/cdn-purge.sh --all    # @main + @<ветка>-cdn/debug rule-providers
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CDN_URL="$SCRIPT_DIR/cdn-url.sh"
TEMPLATE="$ROOT/MIHOMO/template_remnawave.yaml"
WL_TEMPLATE="$ROOT/MIHOMO/wl.yaml"
CDN_HOST="${CDN_HOST:-cdn.jsdelivr.net}"
PURGE_HOST="${PURGE_HOST:-purge.jsdelivr.net}"
CDN_REMOTE="${CDN_REMOTE:-origin}"

die() { echo "cdn-purge: $*" >&2; exit 1; }

usage() {
  cat >&2 <<EOF
usage: $(basename "$0") <path-in-repo> …
       $(basename "$0") --all
       $(basename "$0") --url <cdn-url> …

Сбрасывает кэш jsDelivr. Пути — как в репозитории (@main).
--all — rule-providers нашего репо из MIHOMO/*.yaml (@main) и @<ветка>-cdn/debug.
        Чужие CDN (иконки Qure и т.п.) не трогаем.

Переменные: CDN_BASE, CDN_HOST, PURGE_HOST, CDN_REMOTE, CDN_PURGE_BRANCH.
EOF
}

cdn_to_purge() {
  local cdn="$1"
  case "$cdn" in
    "https://${CDN_HOST}/"*) printf 'https://%s/%s\n' "$PURGE_HOST" "${cdn#https://${CDN_HOST}/}" ;;
    *) die "не CDN URL jsDelivr: $cdn" ;;
  esac
}

purge_cdn_url() {
  local cdn="$1" purge code
  purge="$(cdn_to_purge "$cdn")"
  code="$(curl -fsS -o /dev/null -w '%{http_code}' "$purge" || true)"
  if [[ "$code" == "200" ]]; then
    printf 'ok  %s\n' "$cdn"
    return 0
  fi
  printf 'FAIL http=%s  %s\n' "$code" "$cdn" >&2
  printf '     %s\n' "$purge" >&2
  return 1
}

owner_repo() {
  local url
  url="$(git -C "$ROOT" remote get-url --push "$CDN_REMOTE" 2>/dev/null)" || return 1
  printf '%s' "$url" | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##'
}

source_branch() {
  local src="${CDN_PURGE_BRANCH:-${GITHUB_REF_NAME:-$(git -C "$ROOT" branch --show-current 2>/dev/null || true)}}"
  src="${src%-cdn}"
  src="${src%-debug}"
  printf '%s' "$src"
}

# Для @main URL добавляет @<ветка>-cdn и @<ветка>-debug (если ветка не main).
branch_variant_urls() {
  local main_cdn="$1" repo src path
  [[ "$main_cdn" == *"@main/"* ]] || return 0
  src="$(source_branch)"
  [[ -n "$src" && "$src" != "main" ]] || return 0
  repo="$(owner_repo)" || repo="mireon-network/mihomo_routing"
  path="${main_cdn#*@main/}"
  printf 'https://%s/gh/%s@%s-cdn/%s\n' "$CDN_HOST" "$repo" "$src" "$path"
  printf 'https://%s/gh/%s@%s-debug/%s\n' "$CDN_HOST" "$repo" "$src" "$path"
}


collect_main_urls() {
  local f repo prefix
  repo="$(owner_repo)" || repo="mireon-network/mihomo_routing"
  prefix="https://${CDN_HOST}/gh/${repo}@"
  for f in "$TEMPLATE" "$WL_TEMPLATE"; do
    [[ -f "$f" ]] || die "нет файла: $f"
    grep -oE "https://${CDN_HOST}/gh/[^\"[:space:]]+" "$f" | grep -F "$prefix" || true
  done | sort -u
}

collect_all_urls() {
  local url extra
  while IFS= read -r url; do
    [[ -n "$url" ]] || continue
    printf '%s\n' "$url"
    branch_variant_urls "$url"
  done < <(collect_main_urls) | sort -u
}

purge_path() {
  local rel="$1" cdn extra rc=0
  rel="${rel#./}"
  cdn="$("$CDN_URL" "$rel")"
  purge_cdn_url "$cdn" || rc=1
  while IFS= read -r extra; do
    [[ -n "$extra" ]] || continue
    purge_cdn_url "$extra" || rc=1
  done < <(branch_variant_urls "$cdn")
  return "$rc"
}

failed=0

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  '')
    usage
    exit 1
    ;;
  --all|all)
    while IFS= read -r url; do
      purge_cdn_url "$url" || ((failed+=1)) || true
    done < <(collect_all_urls)
    ;;
  --url)
    shift
    [[ $# -ge 1 ]] || die "нужен хотя бы один CDN URL после --url"
    for url in "$@"; do
      purge_cdn_url "$url" || ((failed+=1)) || true
    done
    ;;
  *)
    for rel in "$@"; do
      purge_path "$rel" || ((failed+=1)) || true
    done
    ;;
esac

exit "$failed"
