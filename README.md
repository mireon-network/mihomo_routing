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

### Мост + страна (по `vlessRoute`)

Ориентир — таблица в `Beget-MSK.json` / `Selectel-MSK.json` (поля `vlessRoute` → outbound).

В Remnawave: **один хост = один код маршрута**, remark например `gateway_selectel_1002` (Selectel + FI).  
Не отдельные «страны» без кода: маршрут задаётся числом `1001`–`1006`.

| vlessRoute | Имя в клиенте |
|------------|----------------|
| 1001 | 🇵🇱 Польша |
| 1002 | 🇫🇮 Финляндия |
| 1003 | 🇩🇪 Германия |
| 1004 | 🇫🇷 Франция |
| 1005 | 🇩🇪 Германия · NC |
| 1006 | 🇫🇮 Финляндия · 135 |
| 101 / 102 | 🇫🇮 / 🇩🇪 · авто (только Selectel) |

### Интерфейс клиента (две вкладки)

| Вкладка | Что выбираете |
|---------|----------------|
| **🌉 Мост** | **⚡️ Авто мост**, **🌍 Selectel**, **🌍 Beget** |
| **🛡️ VPN** | **VPN · 🇩🇪 Германия**, **VPN · 🇫🇷 Франция**, **VPN · 🇫🇮 Финляндия** (только страны, без `ROUTE-100x`) |

Префикс **`VPN ·`** в именах групп — чтобы не дублировать автогруппы Remnawave («Финляндия», «Германия» и т.д.).

Скрытые панели в Mihomo-клиенте: листья `VPN · … · Beget` / `VPN · … · Selectel`, агрегаторы **🌍 Beget** / **🌍 Selectel**, обёртки стран (`hidden: true`). В верхнем списке групп обычно видны **Мост** и **VPN** (зависит от клиента: Coala Clash, Clash Verge, FlClash и т.д.).

### Цепочка трафика

Один хост в подписке = мост MSK + `vlessRoute` в UUID (не двухшаговый relay в клиенте).

```text
Правила (PROXY, DNS #PROXY, Youtube, Discord, 🤖 ИИ)
  → 🌉 Мост                    ← вкладка «Мост»
  → 🌍 Selectel | 🌍 Beget     ← выбранный провайдер
  → VPN · 🇫🇮 … · Selectel|Beget   ← страна + мост (один gateway_*)
```

Группа **🛡️ VPN** во вкладке клиента задаёт **страну**; в цепочке `PROXY` она **не** стоит отдельным hop — трафик идёт через **🌉 Мост** → **🌍 …** → лист с нужным `gateway_*`.

**⚡️ Авто мост** — `url-test` между **🌍 Beget** и **🌍 Selectel** (в **🌍 …** только DE / FR / FI для автовыбора).

### Примеры (ручной режим)

| Мост | VPN | Активный лист (под **Мост → …**) | remark | MSK в панели |
|------|-----|----------------------------------|--------|----------------|
| **🌍 Selectel** | **VPN · 🇫🇮 Финляндия** | **VPN · 🇫🇮 Финляндия · Selectel** | `gateway_selectel_1002` | Selectel-MSK |
| **🌍 Beget** | **VPN · 🇫🇮 Финляндия** | **VPN · 🇫🇮 Финляндия · Beget** | `gateway_beget_1002` | Beget-MSK |
| **🌍 Selectel** | **VPN · 🇩🇪 Германия** | **VPN · 🇩🇪 Германия · Selectel** | `gateway_selectel_1003` | Selectel-MSK |
| **🌍 Beget** | **VPN · 🇩🇪 Германия** | **VPN · 🇩🇪 Германия · Beget** | `gateway_beget_1003` | Beget-MSK |

### Смена моста

Mihomo **не связывает** вкладки «Мост» и «VPN» автоматически — это ограничение движка, не одного клиента. В шаблоне **нет** `default: · Selectel` (иначе при **Beget** часто оставался бы Selectel-MSK).

После смены **Мост**:

1. Заново выберите страну во **🛡️ VPN**.
2. Раскройте **Мост → 🌍 Beget** (или **🌍 Selectel**) и выберите лист с тем же мостом, например **VPN · 🇫🇮 Финляндия · Beget**.
3. Проверьте remark в подписке / последнюю ноду в Remnawave.

Многие клиенты **не показывают** вложенный выбор «· Beget / · Selectel» внутри «VPN · Финляндия» (в т.ч. Coala Clash) — тогда ориентируйтесь на лист под **Мост**, а не только на подпись во вкладке VPN.

### Куда уходят правила

| Правила | Группа в шаблоне |
|---------|------------------|
| `MATCH`, Telegram, GitHub, Google Play, Twitch Ads | **PROXY** → **🌉 Мост** |
| AI (`rule-sets/other/ai.yaml`) | **🤖 ИИ** → **🌉 Мост** (или **🔓 Без VPN**) |
| Youtube, Discord | **📺 Youtube** / **💬 Discord.exe** → **🌉 Мост** |
| Игры (`games.yaml` и др.) | **🎮 Игры** → **🔓 Без VPN** или **🌉 Мост** |

В **Youtube / Discord / 🤖 ИИ** нет `include-all` — только **🌉 Мост** (и **Без VPN** у ИИ/игр).

### Только два хоста в подписке

Возможны **только** `gateway_beget` и `gateway_selectel` (без `1002`/`1003` в remark), если страна **не** переключается в клиенте — один `vlessRoute` на пользователя в Remnawave. Тогда в клиенте меняют только **Мост**.

Справочник по JSON в `temp/` (локально, в git не коммитится): см. `temp/README.md` при наличии копии у себя.

| vlessRoute | Выход |
|------------|--------|
| `1001` | PL |
| `1002` | FI HZ-95 |
| `1003` | DE DS |
| `1004` | FR DS |
| `1005` | DE NC |
| `1006` | FI HZ-135 |
| `101` / `102` | балансировщики FI / DE (только Selectel) |

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

1. **proxy-groups** — группа `🤖 ИИ` (как у `📺 Youtube`: `remnawave`, без `include-all`, прокси **🌉 Мост** / **🔓 Без VPN**); блок **🌉 Мост** / **🛡️ VPN** / мост+страна — см. раздел выше.
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
