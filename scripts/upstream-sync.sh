#!/usr/bin/env bash
# Обновление файлов из upstream-репозиториев без перетирания локальных правок.
# MRS-наборы — через ./scripts/mrs-tool.sh sync (отдельный трёхсторонний merge).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MERGE="$ROOT/scripts/upstream-sync-merge.py"
MRS_TOOL="$ROOT/scripts/mrs-tool.sh"

die() { echo "upstream-sync: $*" >&2; exit 1; }

usage() {
  cat <<EOF
Использование: $(basename "$0") <команда>

  sync            — upstream YAML + MRS (без перетирания локальных правок)
  download        — только скачать upstream в .sync-upstream/staging/
  resolve [id …]  — принять local как baseline после ручного merge
  baseline-init   — один раз: скопировать текущие файлы → .sync-upstream/baseline/
  mrs-only        — только ./scripts/mrs-tool.sh sync

Источники: scripts/upstream-manifest.yaml
Конфликты:  .sync-upstream/SYNC-CONFLICTS.md и .sync-upstream/conflicts/<id>/

Первый запуск без baseline:
  $(basename "$0") baseline-init
  $(basename "$0") sync

Локальные-only (не синхронизируются): ai.yaml, *-custom.yaml
EOF
}

cmd_sync() {
  [[ -f "$MERGE" ]] || die "нет $MERGE"
  local merge_rc=0
  python3 "$MERGE" sync --root "$ROOT" || merge_rc=$?

  if [[ -x "$MRS_TOOL" ]]; then
    echo "upstream-sync: MRS rule-sets…"
    local mrs_rc=0
    "$MRS_TOOL" sync || mrs_rc=$?
    if [[ "$mrs_rc" -ne 0 ]]; then
      echo "upstream-sync: конфликты MRS — см. rule-sets/mrs/SYNC-CONFLICTS.md" >&2
      exit 1
    fi
  else
    echo "upstream-sync: пропуск MRS (нет $MRS_TOOL)" >&2
  fi

  if [[ "$merge_rc" -ne 0 ]]; then
    echo "upstream-sync: конфликты upstream — см. .sync-upstream/SYNC-CONFLICTS.md" >&2
    exit 1
  fi
  echo "upstream-sync: готово"
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    sync) cmd_sync ;;
    download) python3 "$MERGE" download --root "$ROOT" ;;
    resolve) python3 "$MERGE" resolve --root "$ROOT" "$@" ;;
    baseline-init) python3 "$MERGE" baseline-init --root "$ROOT" ;;
    mrs-only) "$MRS_TOOL" sync ;;
    -h|--help|"") usage ;;
    *) die "неизвестная команда: $cmd (см. --help)" ;;
  esac
}

main "$@"
