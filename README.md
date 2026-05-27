# mihomo_routing

Форк конфигурации Mihomo (Remnawave) на базе [RoscomVPN routing](https://github.com/hydraponique/roscomvpn-routing) с локальными rule-sets и правилами для AI.

Файлы правятся **вручную** в этом репозитории; автосинхронизации нет.

## Содержимое

| Путь | Описание |
|------|----------|
| `MIHOMO/template_remnawave.yaml` | Шаблон для Remnawave |
| `rule-sets/other/torrent-clients.yaml` | Торрент-клиенты (форк [legiz-ru/mihomo-rule-sets](https://github.com/legiz-ru/mihomo-rule-sets/blob/main/other/torrent-clients.yaml)) |
| `rule-sets/mihomo/games.yaml` | Игры ([roscomvpn/custom-category](https://github.com/roscomvpn/custom-category)) + [GeForce NOW](https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json) (облако = сеть, `PROCESS-NAME` через [gamedatabase.json](https://gist.github.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161)) |
| `rule-sets/mihomo/ru-apps.yaml` | RU-приложения (тот же репозиторий) |
| `rule-sets/other/ai.yaml` | AI / LLM — только здесь, своими правками |
| `rule-sets/mrs/text/*.list` | Распакованные MRS-наборы (редактировать здесь) |
| `rule-sets/mrs/bin/*.mrs` | Бинарные rule-set для Mihomo (собираются из `text/`) |

В `template_remnawave.yaml` vendored rule-sets отдаются через **jsDelivr GitHub CDN** (не `github.com/.../blob/...`):

База: `https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/`

- `…/rule-sets/other/torrent-clients.yaml`
- `…/rule-sets/mihomo/games.yaml`
- `…/rule-sets/mihomo/ru-apps.yaml`
- `…/rule-sets/other/ai.yaml`
- `…/rule-sets/mrs/bin/<имя>.mrs`

После `git push` в `main` файлы доступны на CDN автоматически (кэш jsDelivr может обновляться с задержкой; при срочном обновлении — [purge](https://www.jsdelivr.com/tools/purge)).

## MRS rule-sets (geosite / geoip)

Наборы с `format: mrs` в шаблоне vendored в репозитории:

| Каталог | Назначение |
|---------|------------|
| `rule-sets/mrs/bin/` | Скачанные или собранные `.mrs` |
| `rule-sets/mrs/text/` | Текст после `mihomo convert-ruleset … mrs` (источник правок) |
| `rule-sets/mrs/manifest.yaml` | URL, `behavior`, имена файлов |

Первичная загрузка и обновление из manifest (URL в `manifest.yaml`):

```bash
./scripts/mrs-tool.sh sync
```

`sync` **не перезаписывает** локальные правки в `text/`: сравнивает upstream (staging), ваш `text/` и `.sync-baseline/` (снимок после последней успешной синхронизации). При конфликте — `SYNC-CONFLICTS.md` и `conflicts/<имя>/{baseline,local,remote}.list`. После ручного merge: `./scripts/mrs-tool.sh resolve [имя]`. Один раз после первого импорта без baseline: `./scripts/mrs-tool.sh baseline-init`. Принудительная перезапись: `download --force` и `unpack --force`.

Редактируйте `rule-sets/mrs/text/<имя>.list`, затем коммит — **pre-commit** сам вызовет `pack` и добавит обновлённые `rule-sets/mrs/bin/*.mrs` в индекс.

Установка хука (один раз после клонирования):

```bash
./scripts/mrs-tool.sh install-hooks
```

Отдельные команды: `download`, `unpack`, `pack`. Бинарник `mihomo` берётся из `PATH` или скачивается в `.tools/mihomo` (в `.gitignore`).

## Использование в Remnawave

Шаблон:

`https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/MIHOMO/template_remnawave.yaml`

## Как вручную подтянуть изменения из upstream

Источники:

| Что обновлять | Upstream |
|---------------|----------|
| Шаблон Mihomo | [hydraponique/roscomvpn-routing — `MIHOMO/template_remnawave.yaml`](https://github.com/hydraponique/roscomvpn-routing/blob/main/MIHOMO/template_remnawave.yaml) |
| Торрент-клиенты | [legiz-ru/mihomo-rule-sets — `other/torrent-clients.yaml`](https://github.com/legiz-ru/mihomo-rule-sets/blob/main/other/torrent-clients.yaml) |
| Игры (база, верх `games.yaml`) | [roscomvpn/custom-category](https://github.com/roscomvpn/custom-category) — не перезаписывать целиком |
| GeForce NOW → `PROCESS-NAME` | [NVIDIA `gfnpc-en-US.json`](https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json) + [gamedatabase.json](https://gist.github.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161) + [jsnli/steamappidlist](https://github.com/jsnli/steamappidlist) |
| RU-приложения | [roscomvpn/custom-category — `release/mihomo/ru-apps.yaml`](https://github.com/roscomvpn/custom-category/blob/release/mihomo/ru-apps.yaml) |

### 1. Скачать свежие файлы

Из корня репозитория:

```bash
curl -fsSL -o MIHOMO/template_remnawave.yaml \
  "https://raw.githubusercontent.com/hydraponique/roscomvpn-routing/main/MIHOMO/template_remnawave.yaml"

curl -fsSL -o rule-sets/other/torrent-clients.yaml \
  "https://raw.githubusercontent.com/legiz-ru/mihomo-rule-sets/main/other/torrent-clients.yaml"

curl -fsSL -o /tmp/gfnpc-en-US.json \
  "https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json"

curl -fsSL -o /tmp/gamedatabase.json \
  "https://gist.githubusercontent.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161/raw/gamedatabase.json"

curl -fsSL -o /tmp/games_appid.json \
  "https://raw.githubusercontent.com/jsnli/steamappidlist/master/data/games_appid.json"

# games.yaml — гибрид: база roscomvpn + блок GeForce NOW (`python3 scripts/generate-gfn-games-block.py`)

curl -fsSL -o rule-sets/mihomo/ru-apps.yaml \
  "https://raw.githubusercontent.com/roscomvpn/custom-category/release/mihomo/ru-apps.yaml"
```

`rule-sets/other/ai.yaml` из upstream **не качается** — это ваш локальный набор.

Блок **GeForce NOW** в `games.yaml` (после лаунчеров): только игры с **явным онлайном в жанрах** JSON (Multiplayer, MMO, F2P online, Battle Royale, Co-op/PvP и т.д.) — не весь каталог облака. Сопоставление exe:

1. точное имя GFN ↔ [gamedatabase.json](https://gist.github.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161);
2. для Steam-URL — имя из [jsnli/steamappidlist](https://github.com/jsnli/steamappidlist) `games_appid.json`, затем снова gamedatabase;
3. осторожное substring-совпадение имён (длинные строки).

Пересобрать блок:

```bash
python3 scripts/generate-gfn-games-block.py
```

Скрипт не трогает верх файла (roscomvpn + ваши правки). Офлайн-одиночки из GFN (Alan Wake, Cities: Skylines…) в блок **не** попадают.

Игры вне каталога GFN (например **R.E.P.O.** — онлайн co-op, но нет в `gfnpc-en-US.json`) — в секции «Добавленно вручную» внизу `games.yaml` и в `generate-gfn-games-block.py` (не перезаписываются при пересборке GFN).

### 2. Подставить URL на rule-sets из этого репо

В `MIHOMO/template_remnawave.yaml` в секции `rule-providers` заменить внешние ссылки на CDN **mihomo_routing** (если upstream снова указал legiz-ru / roscomvpn):

```text
legiz-ru/.../torrent-clients.yaml
  → https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/rule-sets/other/torrent-clients.yaml

roscomvpn/.../games.yaml
  → https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/rule-sets/mihomo/games.yaml

roscomvpn/.../ru-apps.yaml
  → https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/rule-sets/mihomo/ru-apps.yaml
```

Проверка:

```bash
grep -E "url:.*cdn\.jsdelivr\.net/gh/mireon-network/mihomo_routing@main" MIHOMO/template_remnawave.yaml
./scripts/cdn-url.sh rule-sets/mihomo/games.yaml
```

### 3. Вернуть локальные дополнения (AI)

После перезаписи шаблона из hydraponique снова нужны блоки для **🤖 ИИ** (если их нет в upstream):

1. **proxy-groups** — группа `🤖 ИИ` (как у `📺 Youtube`: `remnawave`, `include-all`, прокси `🛡️ VPN` / `🔓 Без VPN`).
2. **rule-providers** — провайдер `ai` на `rule-sets/other/ai.yaml` (classical yaml).
3. **rules** — `RULE-SET,ai,🤖 ИИ` **выше** `RULE-SET,google-play`, иначе Gemini/Google API уйдут в общий PROXY.

Ориентир по структуре — ваш прошлый форк или текущий коммит в `MIHOMO/template_remnawave.yaml` до обновления (`git show HEAD:MIHOMO/template_remnawave.yaml`).

Сравнить с upstream:

```bash
curl -fsSL /tmp/upstream-template.yaml \
  "https://raw.githubusercontent.com/hydraponique/roscomvpn-routing/main/MIHOMO/template_remnawave.yaml"
diff -u /tmp/upstream-template.yaml MIHOMO/template_remnawave.yaml
```

### 4. Закоммитить

```bash
git add MIHOMO/template_remnawave.yaml rule-sets/
git commit -m "chore: update from upstream RoscomVPN / rule-sets"
git push
```

## Благодарности

Основа правил — [hydraponique/roscomvpn-routing](https://github.com/hydraponique/roscomvpn-routing), rule-sets — [legiz-ru](https://github.com/legiz-ru/mihomo-rule-sets), [roscomvpn/custom-category](https://github.com/roscomvpn/custom-category).
