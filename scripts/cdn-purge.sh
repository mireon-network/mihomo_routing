#!/usr/bin/env bash
# Сброс кэша jsDelivr для файлов репозитория (purge API).
# Использование:
#   ./scripts/cdn-purge.sh rule-sets/yaml/ai.yaml
#   ./scripts/cdn-purge.sh --all    # все URL из MIHOMO/template_remnawave.yaml
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CDN_URL="$SCRIPT_DIR/cdn-url.sh"
TEMPLATE="$ROOT/MIHOMO/template_remnawave.yaml"
CDN_HOST="${CDN_HOST:-cdn.jsdelivr.net}"
PURGE_HOST="${PURGE_HOST:-purge.jsdelivr.net}"

die() { echo "cdn-purge: $*" >&2; exit 1; }

usage() {
  cat >&2 <<EOF
usage: $(basename "$0") <path-in-repo> …
       $(basename "$0") --all
       $(basename "$0") --url <cdn-url> …

Сбрасывает кэш jsDelivr. Пути — как в репозитории; --all — rule-providers из шаблона.
Переменные: CDN_BASE (как в cdn-url.sh), CDN_HOST, PURGE_HOST.
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

purge_path() {
  local rel="$1" cdn
  rel="${rel#./}"
  cdn="$("$CDN_URL" "$rel")"
  purge_cdn_url "$cdn"
}

collect_all_urls() {
  [[ -f "$TEMPLATE" ]] || die "нет файла: $TEMPLATE"
  grep -oE "https://${CDN_HOST}/gh/mireon-network/mihomo_routing@[^\"[:space:]]+" "$TEMPLATE" | sort -u
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
