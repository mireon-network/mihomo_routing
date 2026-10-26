#!/usr/bin/env bash
# Проверка шаблонов на матрице версий mihomo (сеть: GitHub API и скачивание ядер).
#   v1.19.27 — минимальная поддерживаемая (README): первая с empty-fallback;
#   вторая — последний стабильный релиз MetaCubeX/mihomo (releases/latest, не пререлиз).
# Локальный sha256 — у уже сверенных релизов. У более нового — digest ассета в GitHub API.
# Для каждой версии: test-config-local.sh (оба шаблона) + test-groups-fixture.py.
# Один раз: check-config-keys.py (опечатки/неизвестные ключи, ключи новее минимальной версии).
#
# Использование: scripts/test-config-matrix.sh
#   MIHOMO_TEST_VERSIONS="v1.19.27 v1.19.33" — не спрашивать latest, взять этот список.
#   Проверка ключей всегда против FLOOR, даже если список начинается с более новой версии.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLOOR=v1.19.27
TOOLS_DIR="$ROOT/.tools"
TEMPLATES=("$ROOT/MIHOMO/template_remnawave.yaml" "$ROOT/MIHOMO/wl.yaml")

gh_api() {  # $1 = путь после /repos/MetaCubeX/mihomo/
  local args=(-fsSL -H "Accept: application/vnd.github+json" -H "User-Agent: mihomo-routing")
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    args+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
  fi
  curl "${args[@]}" "https://api.github.com/repos/MetaCubeX/mihomo/$1"
}

latest_tag() {
  gh_api "releases/latest" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])'
}

if [[ -n "${MIHOMO_TEST_VERSIONS:-}" ]]; then
  VERSIONS="$MIHOMO_TEST_VERSIONS"
else
  LATEST="$(latest_tag)"
  if [[ "$LATEST" == "$FLOOR" ]]; then
    VERSIONS="$FLOOR"
  else
    VERSIONS="$FLOOR $LATEST"
  fi
fi
MIN_VERSION="$FLOOR"

release_sha256() {  # $1 = тег, $2 = имя .gz
  gh_api "releases/tags/$1" | python3 -c '
import json, sys
name = sys.argv[1]
for asset in json.load(sys.stdin).get("assets") or []:
    if asset.get("name") != name:
        continue
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:"):
        print(digest.split(":", 1)[1])
        raise SystemExit(0)
    sys.stderr.write(f"test-config-matrix: у {name} нет sha256 digest\n")
    raise SystemExit(1)
sys.stderr.write(f"test-config-matrix: нет ассета {name}\n")
raise SystemExit(1)
' "$2"
}

gz_sha256() {  # $1 = версия, $2 = os-arch; печатает sha256 .gz
  case "$1 $2" in
    "v1.19.27 linux-amd64") echo "fb3e34c55844f389ff54679e5a3aec331d5ec38006c20f8dcc476fb47768a58f" ;;
    "v1.19.27 linux-arm64") echo "87db0c6660a9557a901b5750f997967e71d8c0af07ea1d1dd4d04c28da7f7e6f" ;;
    "v1.19.33 linux-amd64") echo "132f6f3edf9a65e62f04853aed3358472e0b2b7666daa8419edfa2ddf5bb6323" ;;
    "v1.19.33 linux-arm64") echo "ba408b317080ee265c46cb923a50018c1b82cbd708551cdd46a1e3e307396187" ;;
    *) release_sha256 "$1" "mihomo-$2-$1.gz" ;;
  esac
}

fetch() {  # $1 = версия → путь к бинарю
  local v="$1" bin="$TOOLS_DIR/mihomo-$1" arch os sum url gz
  if [[ ! -x "$bin" ]]; then
    os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    case "$(uname -m)" in
      x86_64) arch=amd64 ;;
      aarch64|arm64) arch=arm64 ;;
      *) echo "test-config-matrix: неподдерживаемая архитектура" >&2; exit 1 ;;
    esac
    sum="$(gz_sha256 "$v" "$os-$arch")"
    mkdir -p "$TOOLS_DIR"
    url="https://github.com/MetaCubeX/mihomo/releases/download/$v/mihomo-${os}-${arch}-${v}.gz"
    gz="$bin.gz"
    curl -fsSL -o "$gz" "$url"
    echo "$sum  $gz" | sha256sum -c --status
    gunzip -c "$gz" >"$bin.tmp"
    rm -f "$gz"
    chmod +x "$bin.tmp" && mv "$bin.tmp" "$bin"
  fi
  echo "$bin"
}

echo "=== check-config-keys (min $MIN_VERSION)"
python3 "$ROOT/scripts/check-config-keys.py" --self-check
python3 "$ROOT/scripts/check-config-keys.py" --min-version "$MIN_VERSION" "${TEMPLATES[@]}"

for v in $VERSIONS; do
  bin="$(fetch "$v")"
  echo "=== mihomo $v"
  for tpl in "${TEMPLATES[@]}"; do
    MIHOMO_BIN="$bin" "$ROOT/scripts/test-config-local.sh" "$tpl"
  done
  MIHOMO_BIN="$bin" python3 "$ROOT/scripts/test-groups-fixture.py" "${TEMPLATES[@]}"
done
echo "✅ матрица: $VERSIONS"
