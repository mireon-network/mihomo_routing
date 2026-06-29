#!/usr/bin/env bash
# Управление vendored .mrs: скачивание, распаковка (text), упаковка (bin).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MRS_DIR="$ROOT/rule-sets/mrs"
MANIFEST="$MRS_DIR/manifest.yaml"
BIN_DIR="$MRS_DIR/bin"
TEXT_DIR="$MRS_DIR/text"
STAGING_DIR="$MRS_DIR/.sync-staging"
BASELINE_DIR="$MRS_DIR/.sync-baseline"
CONFLICTS_REPORT="$MRS_DIR/SYNC-CONFLICTS.md"
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
        if k in ("id", "behavior", "file", "url", "src", "exclude"):
            cur[k] = v
if cur:
    sets.append(cur)
for item in sets:
    print("\t".join(item.get(k, "") for k in ("id", "behavior", "file", "url", "src", "exclude")))
PY
}

# $1 — исходный .txt (формат V2Ray: domain:/full:), $2 — выходной mihomo domain .list
v2ray_domain_to_list() {
  awk '
    { sub(/\r$/, ""); sub(/[[:space:]]+@.*$/, "") }   # CRLF и V2Ray-атрибуты (@...)
    /^[[:space:]]*$/ || /^[[:space:]]*#/ { next }
    /^domain:/  { sub(/^domain:/, "+."); print; next }
    /^full:/    { sub(/^full:/, "");     print; next }
    /^keyword:/ || /^regexp:/ { next }                # domain-behavior их не поддерживает
    { print }                                          # голый домен — как есть
  ' "$1" >"$2"
}

# $1 — .list файл; $2 — список исключаемых строк через запятую (точное совпадение строки)
# Убирает слишком широкие правила (например +.ru, +.su) из скачанного списка.
list_apply_exclude() {
  local out_list="$1" exclude="$2"
  [[ -z "$exclude" ]] && return 0
  local args=() e
  local oldifs="$IFS"; IFS=','
  for e in $exclude; do
    e="${e// /}"
    [[ -n "$e" ]] && args+=(-e "$e")
  done
  IFS="$oldifs"
  [[ ${#args[@]} -eq 0 ]] && return 0
  local before after tmp; tmp="$(mktemp)"
  before="$(grep -cve '^$' "$out_list")"
  grep -vxF "${args[@]}" "$out_list" >"$tmp" || true
  mv "$tmp" "$out_list"
  after="$(grep -cve '^$' "$out_list")"
  echo "   exclude: $before → $after строк (убрано: $exclude)"
}

# $1 — каталог bin; $2 — force (1 = перезаписать)
staging_download() {
  local dest="${1:-$BIN_DIR}"
  local force="${2:-0}"
  local text_dest; text_dest="$(dirname "$dest")/text"   # bin/ и text/ — соседи
  mkdir -p "$dest"
  while IFS=$'\t' read -r _ _ file url src exclude; do
    if [[ -n "$src" ]]; then
      # Текстовый источник: url → .txt → преобразуем сразу в text/*.list.
      # .mrs пакуется позже (cmd_pack). ponytail: только src=v2ray-domain.
      local out_list="$text_dest/${file}.list"
      mkdir -p "$text_dest"
      if [[ "$force" != "1" && -f "$out_list" ]]; then
        echo "→ $file.list (пропуск, уже есть; --force чтобы перезаписать)"
        continue
      fi
      echo "→ $file.list (src=$src)"
      local tmp; tmp="$(mktemp)"
      curl -fsSL -o "$tmp" "$url"
      case "$src" in
        v2ray-domain) v2ray_domain_to_list "$tmp" "$out_list" ;;
        mihomo-list)  sed 's/\r$//' "$tmp" >"$out_list" ;;   # уже формат mihomo, только CRLF→LF
        *) rm -f "$tmp"; die "неизвестный src=$src для $file" ;;
      esac
      rm -f "$tmp"
      list_apply_exclude "$out_list" "$exclude"
      continue
    fi
    local out="$dest/${file}.mrs"
    if [[ "$force" != "1" && -f "$out" ]]; then
      echo "→ $file.mrs (пропуск, уже есть; --force чтобы перезаписать)"
      continue
    fi
    echo "→ $file.mrs"
    curl -fsSL -o "$out" "$url"
  done < <(list_sets)
}

# $1 — bin dir; $2 — text dir
staging_unpack() {
  local bin_d="${1:-$BIN_DIR}"
  local text_d="${2:-$TEXT_DIR}"
  ensure_mihomo
  mkdir -p "$text_d"
  while IFS=$'\t' read -r _ behavior file _ src _; do
    [[ -n "$src" ]] && continue   # текстовый источник: list уже готов в staging_download
    local bin="$bin_d/${file}.mrs"
    local txt="$text_d/${file}.list"
    [[ -f "$bin" ]] || die "нет $bin"
    echo "→ $txt"
    "$MIHOMO_BIN" convert-ruleset "$behavior" mrs "$bin" "$txt"
  done < <(list_sets)
}

cmd_download() {
  local force=0
  if [[ "${1:-}" == "--force" ]]; then
    force=1
  fi
  staging_download "$BIN_DIR" "$force"
}

cmd_unpack() {
  if [[ "${1:-}" == "--force" ]]; then
    staging_unpack "$BIN_DIR" "$TEXT_DIR"
    return
  fi
  die "unpack перезаписывает text/; для безопасного обновления используйте: $0 sync"
}

cmd_pack() {
  ensure_mihomo
  mkdir -p "$BIN_DIR"
  local changed=0
  while IFS=$'\t' read -r _ behavior file _ _ _; do
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
  ensure_mihomo
  rm -rf "$STAGING_DIR"
  mkdir -p "$STAGING_DIR/bin" "$STAGING_DIR/text"

  echo "mrs-tool: загрузка upstream в staging…"
  staging_download "$STAGING_DIR/bin" 1
  staging_unpack "$STAGING_DIR/bin" "$STAGING_DIR/text"

  echo "mrs-tool: слияние с локальным text/…"
  local merge_rc=0
  python3 "$ROOT/scripts/mrs-sync-merge.py" \
    --mrs-dir "$MRS_DIR" \
    --manifest "$MANIFEST" || merge_rc=$?

  echo "mrs-tool: упаковка локальных правок в bin/…"
  cmd_pack

  if [[ "$merge_rc" -ne 0 ]]; then
    echo "mrs-tool: есть конфликты — см. $CONFLICTS_REPORT" >&2
    exit 1
  fi
  echo "mrs-tool: sync завершён без конфликтов"
}

cmd_resolve() {
  parse_manifest
  python3 "$ROOT/scripts/mrs-sync-merge.py" \
    --mrs-dir "$MRS_DIR" \
    --manifest "$MANIFEST" \
    --resolve "$@"
  cmd_pack
}

cmd_baseline_init() {
  mkdir -p "$BASELINE_DIR"
  local n=0
  for f in "$TEXT_DIR"/*.list; do
    [[ -f "$f" ]] || continue
    local base
    base="$(basename "$f")"
    cp "$f" "$BASELINE_DIR/$base"
    n=$((n + 1))
  done
  echo "mrs-tool: baseline инициализирован ($n файлов) в .sync-baseline/"
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

  download [--force]  — скачать .mrs в rule-sets/mrs/bin/
  unpack --force        — bin/*.mrs → text/*.list (перезаписывает text/)
  pack                  — text/*.list → bin/*.mrs
  sync                  — upstream → staging, слияние без перетирания локальных правок
  resolve [имя …]       — после ручного merge: local → baseline, убрать conflict
  baseline-init         — один раз: скопировать text/ → .sync-baseline/
  install-hooks         — git pre-commit

  sync при конфликте создаёт $CONFLICTS_REPORT и каталоги conflicts/<имя>/.
  Переменные: MIHOMO_BIN, MIHOMO_VERSION
EOF
}

main() {
  local cmd="${1:-}"
  shift || true
  case "$cmd" in
    download) cmd_download "$@" ;;
    unpack) cmd_unpack "$@" ;;
    pack) cmd_pack ;;
    sync) cmd_sync ;;
    resolve) cmd_resolve "$@" ;;
    baseline-init) cmd_baseline_init ;;
    install-hooks) cmd_install_hooks ;;
    -h|--help|"") usage ;;
    *) die "неизвестная команда: $cmd (см. --help)" ;;
  esac
}

main "$@"
