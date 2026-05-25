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

В `template_remnawave.yaml` для vendored rule-sets используются **raw** URL этого репо (для `rule-providers` типа `http` нужен `raw.githubusercontent.com`, не ссылка `github.com/.../blob/...`):

- `https://raw.githubusercontent.com/mireon-network/mihomo_routing/main/rule-sets/other/torrent-clients.yaml`
- `https://raw.githubusercontent.com/mireon-network/mihomo_routing/main/rule-sets/mihomo/games.yaml`
- `https://raw.githubusercontent.com/mireon-network/mihomo_routing/main/rule-sets/mihomo/ru-apps.yaml`
- `https://raw.githubusercontent.com/mireon-network/mihomo_routing/main/rule-sets/other/ai.yaml`

## Использование в Remnawave

Шаблон:

`https://raw.githubusercontent.com/mireon-network/mihomo_routing/main/MIHOMO/template_remnawave.yaml`

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

В `MIHOMO/template_remnawave.yaml` в секции `rule-providers` заменить внешние ссылки на raw URL **mihomo_routing** (если upstream снова указал legiz-ru / roscomvpn):

```text
legiz-ru/.../torrent-clients.yaml
  → https://raw.githubusercontent.com/mireon-network/mihomo_routing/main/rule-sets/other/torrent-clients.yaml

roscomvpn/.../games.yaml
  → https://raw.githubusercontent.com/mireon-network/mihomo_routing/main/rule-sets/mihomo/games.yaml

roscomvpn/.../ru-apps.yaml
  → https://raw.githubusercontent.com/mireon-network/mihomo_routing/main/rule-sets/mihomo/ru-apps.yaml
```

Проверка:

```bash
grep -E "url:.*(torrent-clients|games|ru-apps|ai)\.yaml" MIHOMO/template_remnawave.yaml
```

Все четыре `url:` должны вести на `mireon-network/mihomo_routing`.

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
