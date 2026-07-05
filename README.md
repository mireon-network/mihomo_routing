# mihomo_routing

Конфигурация Mihomo для Remnawave (mireon-network) с локальными rule-sets, MRS-наборами и правилами для AI.

Локальные правки — в `*-custom` и локальных MRS; зеркала upstream перезаписываются через `./scripts/upstream-sync.sh sync`.

## Содержимое

| Путь | Описание |
|------|----------|
| `MIHOMO/template_remnawave.yaml` | Шаблон для Remnawave (страны + gateway LB) |
| `MIHOMO/wl.yaml` | Режим «белые списки» |
| `rule-sets/yaml/torrent-clients.yaml` | Торрент-клиенты — **зеркало** [legiz-ru/mihomo-rule-sets](https://github.com/legiz-ru/mihomo-rule-sets/blob/main/other/torrent-clients.yaml) (без правок) |
| `rule-sets/yaml/torrent-clients-custom.yaml` | Локальные дополнения торрент-клиентов → DIRECT |
| `rule-sets/yaml/games.yaml` | Игры — **зеркало** [roscomvpn/custom-category](https://github.com/roscomvpn/custom-category) (без правок) |
| `rule-sets/yaml/games-custom.yaml` | Локальные дополнения игр: [GeForce NOW](https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json), нативные macOS/Linux, ручные — **только локально** |
| `rule-sets/yaml/games-launchers.yaml` | Игровые лаунчеры (Steam, Epic, VK Play…) — всегда DIRECT |
| `rule-sets/yaml/ru-app-list.yaml` | RU Android-пакеты — **зеркало** [legiz-ru/mihomo-rule-sets](https://github.com/legiz-ru/mihomo-rule-sets) (без правок) |
| `rule-sets/yaml/ru-apps-custom.yaml` | Локальные дополнения RU-приложений (вне legiz `ru-app-list`) → DIRECT |
| `rule-sets/yaml/wld-apps-custom.yaml` | Локальные дополнения для `wl.yaml` `tun.exclude-package` (домены из `wld.list`) |
| `rule-sets/yaml/ai.yaml` | AI / LLM — **только локально**, upstream не синхронизируется |
| `rule-sets/mrs/text/*.list` | Распакованные MRS-наборы (редактировать здесь) |
| `rule-sets/mrs/bin/*.mrs` | Бинарные rule-set для Mihomo (собираются из `text/`) |
| `scripts/upstream-sync.sh` | Обновление YAML из upstream-репозиториев |
| `scripts/mrs-tool.sh` | Обновление MRS rule-sets |
| `scripts/upstream-manifest.yaml` | Список upstream-источников для `upstream-sync.sh` |
| `scripts/generate-gfn-games-block.py` | Пересборка блока GeForce NOW в `games-custom.yaml` |
| `scripts/generate-tun-exclude-package.py` | Пересборка `tun.exclude-package` в обоих шаблонах |
| `scripts/test-config-local.sh` | Локальная проверка rule-providers без CDN (`mihomo -t` + convert-ruleset) |
| `scripts/deploy-test-branches.sh` | Обновить `<ветка>-cdn` и `<ветка>-debug` от текущего HEAD |
| `scripts/deploy-cdn-test.sh` | Throwaway-ветка `<ветка>-cdn`: CDN-URL rule-sets → своя ветка |
| `scripts/deploy-debug.sh` | Throwaway-ветка `<ветка>-debug`: CDN-URL + все узлы в селекторах |
| `scripts/patch-include-proxies.py` | Debug-патч: `include-all: true`, видимые хосты, без блокировки Remnawave |

> Мелкие наборы (`wine`, `games-proxy-rules`, `mail-ports`) — `type: inline` rule-providers в шаблоне (без отдельных загрузок). Локальные MRS без upstream: `private-domains-custom`, `category-ru-custom`, `private-ips-custom`, `torrent-domains-custom` — правишь `rule-sets/mrs/text/<имя>.list`, `mrs-tool.sh pack` собирает `bin/*.mrs` (sync их пропускает).

## CDN

В `template_remnawave.yaml` vendored rule-sets отдаются через **jsDelivr GitHub CDN** (не `github.com/.../blob/...`):

База: `https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/`

- `…/rule-sets/yaml/torrent-clients.yaml`
- `…/rule-sets/yaml/torrent-clients-custom.yaml`
- `…/rule-sets/yaml/games.yaml`
- `…/rule-sets/yaml/games-custom.yaml`
- `…/rule-sets/yaml/games-launchers.yaml`
- `…/rule-sets/yaml/ru-apps-custom.yaml`
- `…/rule-sets/yaml/ai.yaml`
- `…/rule-sets/mrs/bin/<имя>.mrs`

Проверка URL для файла:

```bash
./scripts/cdn-url.sh rule-sets/yaml/games.yaml
./scripts/cdn-purge.sh rule-sets/yaml/ai.yaml   # сброс кэша jsDelivr
./scripts/cdn-purge.sh --all                     # @main + @<ветка>-cdn/debug из MIHOMO/*.yaml
```

После `git push` в `main` файлы доступны на CDN автоматически (кэш jsDelivr может обновляться с задержкой; при срочном обновлении — `./scripts/cdn-purge.sh` или [purge](https://www.jsdelivr.com/tools/purge)).

Локальная проверка rule-sets без CDN:

```bash
./scripts/test-config-local.sh
./scripts/test-config-local.sh MIHOMO/wl.yaml
```

## Использование в Remnawave

Шаблоны (ветка `main`):

- Основной: `https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/MIHOMO/template_remnawave.yaml`
- Белые списки: `https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/MIHOMO/wl.yaml`

Live-тест — throwaway-ветки **`<ветка>-cdn`** и **`<ветка>-debug`** обновляются автоматически при push в любую ветку (кроме `*-cdn`/`*-debug`). Вручную: `./scripts/deploy-test-branches.sh`.

Пример для `routing-v2`:

- CDN: `https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@routing-v2-cdn/MIHOMO/template_remnawave.yaml`
- Debug: `https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@routing-v2-debug/MIHOMO/template_remnawave.yaml` — все узлы в селекторах (`include-all` + инъекция Remnawave)

## Обновление из upstream

Два контура синхронизации:

| Контур | Скрипт | Что обновляет |
|--------|--------|---------------|
| YAML-зеркала | `./scripts/upstream-sync.sh` | `torrent-clients`, `games`, `ru-app-list` |
| MRS (geosite / geoip) | `./scripts/mrs-tool.sh` | `rule-sets/mrs/text/` → `bin/` |

### Быстрый старт

```bash
./scripts/mrs-tool.sh install-hooks   # pre-commit: pack .mrs при коммите
./scripts/upstream-sync.sh sync       # YAML-зеркала + MRS
```

**Автоматически:** GitHub Actions [`.github/workflows/upstream-sync.yml`](.github/workflows/upstream-sync.yml) — каждый день **06:00 МСК** (`sync` + `test-config-local.sh`, коммит в `main` при изменениях). Ручной запуск: Actions → *Upstream sync* → *Run workflow*.

`upstream-sync.sh sync` последовательно:

1. скачивает upstream в `.sync-upstream/staging/`;
2. **перезаписывает** зеркала из manifest (конфликтов нет — правки только в `*-custom`);
3. post-hooks: GFN → `games-custom.yaml`, `tun.exclude-package` в обоих шаблонах, CDN URL в `template_remnawave.yaml`;
4. вызывает `./scripts/mrs-tool.sh sync`.

### Источники (`scripts/upstream-manifest.yaml`)

| id | Файл | Upstream |
|----|------|----------|
| `torrent_clients` | `rule-sets/yaml/torrent-clients.yaml` | [legiz-ru/mihomo-rule-sets](https://github.com/legiz-ru/mihomo-rule-sets) |
| `games` | `rule-sets/yaml/games.yaml` | [roscomvpn/custom-category](https://github.com/roscomvpn/custom-category) (post → GFN в `games-custom.yaml`) |
| `ru_app_list` | `rule-sets/yaml/ru-app-list.yaml` | [legiz-ru/mihomo-rule-sets](https://github.com/legiz-ru/mihomo-rule-sets) (post → `tun.exclude-package`) |

**Не синхронизируется (только локально):** `MIHOMO/template_remnawave.yaml`, `MIHOMO/wl.yaml`, `rule-sets/yaml/ai.yaml`, все `*-custom.yaml`, локальные MRS `*-custom` (`rule-sets/mrs/text/<имя>.list`).

Команды `upstream-sync.sh`:

```bash
./scripts/upstream-sync.sh sync       # YAML-зеркала + MRS
./scripts/upstream-sync.sh download # только staging
./scripts/upstream-sync.sh mrs-only # только MRS
```

### MRS rule-sets

| Каталог | Назначение |
|---------|------------|
| `rule-sets/mrs/bin/` | Скачанные или собранные `.mrs` |
| `rule-sets/mrs/text/` | Текст после `mihomo convert-ruleset … mrs` (источник правок) |
| `rule-sets/mrs/manifest.yaml` | URL, `behavior`, имена файлов |

```bash
./scripts/mrs-tool.sh sync
```

Upstream-наборы перезаписываются из CDN/MetaCubeX. Локальные правки — только в `*-custom` (`private-domains-custom`, `category-ru-custom`, `private-ips-custom`, `torrent-domains-custom`): правьте `text/*.list`, **pre-commit** вызовет `pack`.

Отдельные команды MRS: `download`, `unpack --force`, `pack`. Бинарник `mihomo` — из `PATH` или `.tools/mihomo` (в `.gitignore`).

Служебный каталог (в `.gitignore`): `rule-sets/mrs/.sync-staging/`.

## games.yaml и GeForce NOW

`games.yaml` — **зеркало апстрима без правок**. Все локальные дополнения вынесены в `games-custom.yaml`:

- блок GeForce NOW (пересобирается скриптом);
- нативные порты macOS/Linux;
- секция «Добавленно вручную» (R.E.P.O. и т.п.).

Правьте только часть `games-custom.yaml` **выше** маркера `# --- GeForce NOW` — всё ниже перезаписывает скрипт.

Лаунчеры, которые апстрим держит в `games.yaml`, в шаблоне перехватываются **раньше** правилом `games-launchers` (→ 🎮 Лаунчеры / DIRECT), поэтому отдельно вырезать их из зеркала не нужно.

Исключения с фиксированной политикой (не попадают в 🎮 Игры) — отдельные YAML, подключаются в шаблоне **до** `games`:

- `games-proxy-rules` — игровые домены и процессы → PROXY, инлайн rule-provider (**раньше** лаунчеров и MRS steam/epic)
- `games-launchers.yaml` — лаунчеры платформ → DIRECT (после proxy-rules; до MRS steam/epic)

После sync с апстримом скрипт автоматически пересобирает блок GFN в `games-custom.yaml` (`regenerate_gfn_block`), дедуплицируя против `games.yaml` и `games-launchers.yaml`. Вручную:

```bash
python3 scripts/generate-gfn-games-block.py
```

Источники GFN:

- [gfnpc-en-US.json](https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json)
- [gamedatabase.json](https://gist.github.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161)
- [jsnli/steamappidlist](https://github.com/jsnli/steamappidlist) — `games_appid.json`

В блок попадают только игры с **явным онлайном в жанрах** GFN (Multiplayer, MMO, F2P online, Battle Royale, Co-op/PvP…). Офлайн-одиночки не включаются.

Игры вне каталога GFN (например **R.E.P.O.**) — в секции «Добавленно вручную» внизу `games-custom.yaml` (генерируется из `generate-gfn-games-block.py`, не перезаписывается данными GFN).

## Локальные дополнения в шаблоне

`MIHOMO/template_remnawave.yaml` — **локальный** шаблон (не зеркало upstream). Локальные блоки:

### 🤖 ИИ

1. **proxy-groups** — группа `🤖 ИИ` (как у `📺 Youtube`: `remnawave.include-proxies: false`, прокси `🛡️ VPN` + переопределение стран).
2. **rule-providers** — провайдер `ai` → `rule-sets/yaml/ai.yaml`.
3. **rules** — `RULE-SET,ai,🤖 ИИ` и `RULE-SET,ai-meta,🤖 ИИ` **выше** финального `MATCH,PROXY` (иначе `*.googleapis.com` и пр. уходят в PROXY мимо группы ИИ).

### TUN exclude-package (RU-приложения мимо TUN)

`tun.exclude-package` — список Android-пакетов, которые не заворачиваются в TUN (механизм как у [Davoyan/ultimate-mihomo-ru](https://github.com/Davoyan/mihomo-rule-sets/blob/main/remnawave-templates/ultimate-mihomo-ru.yaml)):

| Шаблон | Источник пакетов |
|--------|------------------|
| `template_remnawave.yaml` | `ru-app-list.yaml` + `ru-apps-custom.yaml` (~530 пакетов) |
| `wl.yaml` | `wld.list` → `ru-app-list.yaml` + `wld-apps-custom.yaml` |

Пост-хук `regenerate_tun_exclude` срабатывает после sync `ru_app_list`. Вручную:

```bash
python3 scripts/generate-tun-exclude-package.py
```

### CDN URL в rule-providers

После каждого `upstream-sync.sh sync` в `template_remnawave.yaml` подставляются jsDelivr URL **mireon-network/mihomo_routing** вместо legiz-ru / roscomvpn. Проверка:

```bash
grep -E "url:.*cdn\.jsdelivr\.net/gh/mireon-network/mihomo_routing@main" MIHOMO/template_remnawave.yaml
```

Сравнить форк с upstream:

```bash
curl -fsSL -o /tmp/upstream-template.yaml \
  "https://raw.githubusercontent.com/hydraponique/roscomvpn-routing/main/MIHOMO/template_remnawave.yaml"
diff -u /tmp/upstream-template.yaml MIHOMO/template_remnawave.yaml
```

## Благодарности

- [legiz-ru/mihomo-rule-sets](https://github.com/legiz-ru/mihomo-rule-sets)
- [Davoyan/mihomo-rule-sets](https://github.com/Davoyan/mihomo-rule-sets)
- [RoscomVPN](https://github.com/roscomvpn)
- [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat)
