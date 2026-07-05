#!/usr/bin/env bash
# Зеркалирование upstream YAML (remote → local). Локальные правки — в *-custom.
# MRS-наборы — через ./scripts/mrs-tool.sh sync.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MERGE="$ROOT/scripts/upstream-sync-merge.py"
MRS_TOOL="$ROOT/scripts/mrs-tool.sh"

die() { echo "upstream-sync: $*" >&2; exit 1; }

usage() {
  cat <<EOF
Использование: $(basename "$0") <команда>

  sync       — upstream YAML (зеркала) + MRS
  download   — только скачать upstream в .sync-upstream/staging/
  mrs-only   — только ./scripts/mrs-tool.sh sync

Источники: scripts/upstream-manifest.yaml
Staging:    .sync-upstream/staging/

  $(basename "$0") sync

Зеркала (перезаписываются из upstream): torrent-clients, games, ru-app-list.
Локальные-only (не синхронизируются): ai.yaml, *-custom.yaml, MIHOMO/template_remnawave.yaml.
EOF
}

cmd_sync() {
  [[ -f "$MERGE" ]] || die "нет $MERGE"
  python3 "$MERGE" sync --root "$ROOT"

  if [[ -x "$MRS_TOOL" ]]; then
    echo "upstream-sync: MRS rule-sets…"
    "$MRS_TOOL" sync
  else
    echo "upstream-sync: пропуск MRS (нет $MRS_TOOL)" >&2
  fi

  echo "upstream-sync: готово"
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    sync) cmd_sync ;;
    download) python3 "$MERGE" download --root "$ROOT" ;;
    mrs-only) "$MRS_TOOL" sync ;;
    -h|--help|"") usage ;;
    *) die "неизвестная команда: $cmd (см. --help)" ;;
  esac
}

main "$@"
