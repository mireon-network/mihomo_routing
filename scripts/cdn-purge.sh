#!/usr/bin/env bash
# Сброс кэша jsDelivr для файлов репозитория (purge API).
# Использование:
#   ./scripts/cdn-purge.sh rule-sets/yaml/ai.yaml
#   ./scripts/cdn-purge.sh --koala           # только MIHOMO/koala.css
#   ./scripts/cdn-purge.sh --mihomo-routing  # .mrs из шаблонов
#   ./scripts/cdn-purge.sh --xray-routing    # XRAY/*
#   ./scripts/cdn-purge.sh --all             # всё: тема, mrs, XRAY, шаблоны, yaml rule-providers
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
       $(basename "$0") --koala
       $(basename "$0") --mihomo-routing
       $(basename "$0") --xray-routing
       $(basename "$0") --all
       $(basename "$0") --url <cdn-url> …

Сбрасывает кэш jsDelivr на @main и @<ветка>-cdn/debug.
--koala — только MIHOMO/koala.css.
--mihomo-routing — .mrs из шаблонов MIHOMO.
--xray-routing — файлы XRAY/*.
--all — тема, mrs, XRAY, сами шаблоны и yaml rule-providers.
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

# Для @main URL добавляет @<ветка>-cdn и @<ветка>-debug (для main — main-cdn/main-debug).
branch_variant_urls() {
  local main_cdn="$1" repo src path
  [[ "$main_cdn" == *"@main/"* ]] || return 0
  src="$(source_branch)"
  [[ -n "$src" ]] || return 0
  repo="$(owner_repo)" || repo="mireon-network/mihomo_routing"
  path="${main_cdn#*@main/}"
  printf 'https://%s/gh/%s@%s-cdn/%s\n' "$CDN_HOST" "$repo" "$src" "$path"
  printf 'https://%s/gh/%s@%s-debug/%s\n' "$CDN_HOST" "$repo" "$src" "$path"
}


repo_cdn_prefix() {
  local repo
  repo="$(owner_repo)" || repo="mireon-network/mihomo_routing"
  printf 'https://%s/gh/%s@' "$CDN_HOST" "$repo"
}

# CDN URL нашего репозитория, прописанные в шаблонах.
template_repo_urls() {
  local f prefix
  prefix="$(repo_cdn_prefix)"
  for f in "$TEMPLATE" "$WL_TEMPLATE"; do
    [[ -f "$f" ]] || die "нет файла: $f"
    grep -oE "https://${CDN_HOST}/gh/[^\"[:space:]]+" "$f" | grep -F "$prefix" || true
  done
}

# К @main URL добавляет @<ветка>-cdn и @<ветка>-debug.
expand_refs() {
  local url
  while IFS= read -r url; do
    [[ -n "$url" ]] || continue
    printf '%s\n' "$url"
    branch_variant_urls "$url"
  done | sort -u
}

collect_koala_urls() {
  [[ -f "$ROOT/MIHOMO/koala.css" ]] || die "нет файла: $ROOT/MIHOMO/koala.css"
  "$CDN_URL" MIHOMO/koala.css | expand_refs
}

collect_mrs_urls() {
  local urls
  urls="$(template_repo_urls | grep '\.mrs$' || true)"
  [[ -n "$urls" ]] || die "в шаблонах нет URL на .mrs"
  printf '%s\n' "$urls" | expand_refs
}

collect_xray_urls() {
  local path rel found=0
  for path in "$ROOT"/XRAY/*; do
    [[ -f "$path" ]] || continue
    found=1
    rel="${path#"$ROOT"/}"
    "$CDN_URL" "$rel"
  done
  [[ "$found" -eq 1 ]] || die "нет файлов в XRAY/"
}

collect_all_urls() {
  [[ -f "$ROOT/MIHOMO/koala.css" ]] || die "нет файла: $ROOT/MIHOMO/koala.css"
  {
    "$CDN_URL" MIHOMO/koala.css
    "$CDN_URL" "${TEMPLATE#"$ROOT"/}"
    "$CDN_URL" "${WL_TEMPLATE#"$ROOT"/}"
    template_repo_urls
    collect_xray_urls
  } | expand_refs
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

purge_listed() {
  local url
  while IFS= read -r url; do
    [[ -n "$url" ]] || continue
    purge_cdn_url "$url" || ((failed+=1)) || true
  done
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
  --koala)
    urls="$(collect_koala_urls)"
    printf '%s\n' "$urls" | purge_listed
    ;;
  --mihomo-routing)
    urls="$(collect_mrs_urls)"
    printf '%s\n' "$urls" | purge_listed
    ;;
  --xray-routing)
    urls="$(collect_xray_urls | expand_refs)"
    printf '%s\n' "$urls" | purge_listed
    ;;
  --all|all)
    urls="$(collect_all_urls)"
    printf '%s\n' "$urls" | purge_listed
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
