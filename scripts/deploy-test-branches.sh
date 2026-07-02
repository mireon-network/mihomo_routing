#!/usr/bin/env bash
# Обновить throwaway-ветки <источник>-cdn и <источник>-debug от текущего HEAD.
#   ./scripts/deploy-test-branches.sh              # текущая ветка, remote origin
#   ./scripts/deploy-test-branches.sh origin       # текущая ветка, remote origin
#   ./scripts/deploy-test-branches.sh routing-v2   # явная исходная ветка
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

"$ROOT/scripts/deploy-cdn-test.sh" "${SRC}-cdn" "$REMOTE"
"$ROOT/scripts/deploy-debug.sh" "${SRC}-debug" "$REMOTE"
