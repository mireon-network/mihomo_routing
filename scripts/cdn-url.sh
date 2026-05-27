#!/usr/bin/env bash
# Публичный CDN для файлов репозитория (jsDelivr GitHub).
# Использование: ./scripts/cdn-url.sh rule-sets/yaml/games.yaml
set -euo pipefail

CDN_BASE="${CDN_BASE:-https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main}"

if [[ $# -lt 1 ]]; then
  echo "$CDN_BASE" >&2
  echo "usage: $(basename "$0") <path-in-repo> …" >&2
  exit 1
fi

for rel in "$@"; do
  rel="${rel#./}"
  printf '%s/%s\n' "$CDN_BASE" "$rel"
done
