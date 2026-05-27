#!/usr/bin/env bash
# Управление vendored .mrs: скачивание, распаковка (text), упаковка (bin).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MRS_DIR="$ROOT/rule-sets/mrs"
MANIFEST="$MRS_DIR/manifest.yaml"
BIN_DIR="$MRS_DIR/bin"
TEXT_DIR="$MRS_DIR/text"
TOOLS_DIR="$ROOT/.tools"
MIHOMO_BIN="${MIHOMO_BIN:-$TOOLS_DIR/mihomo}"
MIHOMO_VERSION="${MIHOMO_VERSION:-v1.19.25}"

die() { echo "mrs-tool: $*" >&2; exit 1; }

ensure_mihomo() {
  if command -v mihomo >/dev/null 2>&1; then
    MIHOMO_BIN="$(command -v mihomo)"
    return 0
  fi
  if [[ -x "$MIHOMO_BIN" ]]; then
    return 0
  fi

  local os arch asset url
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "$arch" in
    x86_64) arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) die "неподдерживаемая архитектура: $arch" ;;
  esac
  case "$os" in
    darwin) asset="mihomo-darwin-${arch}-${MIHOMO_VERSION}.gz" ;;
    linux) asset="mihomo-linux-${arch}-${MIHOMO_VERSION}.gz" ;;
    *) die "неподдерживаемая ОС: $os" ;;
  esac

  url="https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_VERSION}/${asset}"
  echo "mrs-tool: скачиваю mihomo ($asset)…"
  mkdir -p "$TOOLS_DIR"
  curl -fsSL "$url" | gunzip -c >"$MIHOMO_BIN"
  chmod +x "$MIHOMO_BIN"
}

# shellcheck disable=SC2034
parse_manifest() {
  [[ -f "$MANIFEST" ]] || die "нет $MANIFEST"
}

list_sets() {
  parse_manifest
  python3 - "$MANIFEST" <<'PY'
import sys

path = sys.argv[1]
sets = []
cur = None
for line in open(path, encoding="utf-8"):
    s = line.strip()
    if s.startswith("- id:"):
        if cur:
            sets.append(cur)
        cur = {"id": s.split(":", 1)[1].strip()}
    elif cur is not None and ":" in s and not s.startswith("#"):
        k, v = s.split(":", 1)
        k, v = k.strip(), v.strip()
        if k in ("id", "behavior", "file", "url"):
            cur[k] = v
if cur:
    sets.append(cur)
for item in sets:
    print("\t".join(item[k] for k in ("id", "behavior", "file", "url")))
PY
}

cmd_download() {
  mkdir -p "$BIN_DIR"
  while IFS=$'\t' read -r _ _ file url; do
    local out="$BIN_DIR/${file}.mrs"
    echo "→ $file.mrs"
    curl -fsSL -o "$out" "$url"
  done < <(list_sets)
}

cmd_unpack() {
  ensure_mihomo
  mkdir -p "$TEXT_DIR"
  while IFS=$'\t' read -r _ behavior file _; do
    local bin="$BIN_DIR/${file}.mrs"
    local txt="$TEXT_DIR/${file}.list"
    [[ -f "$bin" ]] || die "нет $bin (сначала: $0 download)"
    echo "→ $file.list"
    "$MIHOMO_BIN" convert-ruleset "$behavior" mrs "$bin" "$txt"
  done < <(list_sets)
}

cmd_pack() {
  ensure_mihomo
  mkdir -p "$BIN_DIR"
  local changed=0
  while IFS=$'\t' read -r _ behavior file _; do
    local txt="$TEXT_DIR/${file}.list"
    local bin="$BIN_DIR/${file}.mrs"
    [[ -f "$txt" ]] || continue
    if [[ ! -f "$bin" ]] || [[ "$txt" -nt "$bin" ]]; then
      echo "→ pack $file.mrs"
      "$MIHOMO_BIN" convert-ruleset "$behavior" text "$txt" "$bin"
      changed=1
    fi
  done < <(list_sets)
  if [[ "$changed" -eq 0 ]]; then
    echo "mrs-tool: упаковка не требуется"
  fi
}

cmd_sync() {
  cmd_download
  cmd_unpack
}

cmd_install_hooks() {
  local hook_src="$ROOT/scripts/git-hooks/pre-commit"
  local hook_dst="$ROOT/.git/hooks/pre-commit"
  [[ -f "$hook_src" ]] || die "нет $hook_src"
  cp "$hook_src" "$hook_dst"
  chmod +x "$hook_dst"
  echo "Установлен $hook_dst"
}

usage() {
  cat <<EOF
Использование: $(basename "$0") <команда>

  download       — скачать .mrs в rule-sets/mrs/bin/
  unpack         — bin/*.mrs → text/*.list (нужен mihomo)
  pack           — text/*.list → bin/*.mrs (нужен mihomo)
  sync           — download + unpack
  install-hooks  — установить git pre-commit

Переменные: MIHOMO_BIN, MIHOMO_VERSION
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    download) cmd_download ;;
    unpack) cmd_unpack ;;
    pack) cmd_pack ;;
    sync) cmd_sync ;;
    install-hooks) cmd_install_hooks ;;
    -h|--help|"") usage ;;
    *) die "неизвестная команда: $cmd (см. --help)" ;;
  esac
}

main "$@"
