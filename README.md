# mihomo_routing

Форк конфигурации Mihomo (Remnawave) на базе [RoscomVPN routing](https://github.com/hydraponique/roscomvpn-routing) с локальными rule-sets и правилами для AI.

Локальные правки сохраняются: обновление из upstream — через скрипты с **трёхсторонним merge** (baseline / local / remote), без слепой перезаписи.

## Содержимое

| Путь | Описание |
|------|----------|
| `MIHOMO/template_remnawave.yaml` | Шаблон для Remnawave |
| `rule-sets/yaml/torrent-clients.yaml` | Торрент-клиенты (форк [legiz-ru/mihomo-rule-sets](https://github.com/legiz-ru/mihomo-rule-sets/blob/main/other/torrent-clients.yaml)) |
| `rule-sets/yaml/games.yaml` | Игры ([roscomvpn/custom-category](https://github.com/roscomvpn/custom-category)) + [GeForce NOW](https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json) |
| `rule-sets/yaml/ru-apps.yaml` | RU-приложения (тот же репозиторий) |
| `rule-sets/yaml/ai.yaml` | AI / LLM — **только локально**, upstream не синхронизируется |
| `rule-sets/mrs/text/*.list` | Распакованные MRS-наборы (редактировать здесь) |
| `rule-sets/mrs/bin/*.mrs` | Бинарные rule-set для Mihomo (собираются из `text/`) |
| `scripts/upstream-sync.sh` | Обновление YAML из upstream-репозиториев |
| `scripts/mrs-tool.sh` | Обновление MRS rule-sets |
| `scripts/upstream-manifest.yaml` | Список upstream-источников для `upstream-sync.sh` |
| `scripts/generate-gfn-games-block.py` | Пересборка блока GeForce NOW в `games.yaml` |

## CDN

В `template_remnawave.yaml` vendored rule-sets отдаются через **jsDelivr GitHub CDN** (не `github.com/.../blob/...`):

База: `https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/`

- `…/rule-sets/yaml/torrent-clients.yaml`
- `…/rule-sets/yaml/games.yaml`
- `…/rule-sets/yaml/ru-apps.yaml`
- `…/rule-sets/yaml/ai.yaml`
- `…/rule-sets/mrs/bin/<имя>.mrs`

Проверка URL для файла:

```bash
./scripts/cdn-url.sh rule-sets/yaml/games.yaml
./scripts/cdn-purge.sh rule-sets/yaml/ai.yaml   # сброс кэша jsDelivr
./scripts/cdn-purge.sh --all                     # все rule-providers из шаблона
```

После `git push` в `main` файлы доступны на CDN автоматически (кэш jsDelivr может обновляться с задержкой; при срочном обновлении — `./scripts/cdn-purge.sh` или [purge](https://www.jsdelivr.com/tools/purge)).

## Использование в Remnawave

Шаблон:

`https://cdn.jsdelivr.net/gh/mireon-network/mihomo_routing@main/MIHOMO/template_remnawave.yaml`

## Обновление из upstream

Два независимых контура синхронизации:

| Контур | Скрипт | Что обновляет |
|--------|--------|---------------|
| YAML rule-sets, шаблон | `./scripts/upstream-sync.sh` | `MIHOMO/`, `rule-sets/yaml/` |
| MRS (geosite / geoip) | `./scripts/mrs-tool.sh` | `rule-sets/mrs/text/` → `bin/` |

### Быстрый старт

```bash
# один раз после клонирования или перед первым sync
./scripts/upstream-sync.sh baseline-init
./scripts/mrs-tool.sh baseline-init   # если ещё не делали для MRS
./scripts/mrs-tool.sh install-hooks   # pre-commit: pack .mrs при коммите

# обновить всё
./scripts/upstream-sync.sh sync
```

`upstream-sync.sh sync` последовательно:

1. скачивает upstream в `.sync-upstream/staging/`;
2. сливает с локальными файлами (см. логику ниже);
3. запускает post-hooks (CDN URL в шаблоне, блок GFN в `games.yaml`);
4. вызывает `./scripts/mrs-tool.sh sync`.

### Источники (`scripts/upstream-manifest.yaml`)

| id | Файл | Upstream | auto_apply |
|----|------|----------|------------|
| `template_remnawave` | `MIHOMO/template_remnawave.yaml` | [hydraponique/roscomvpn-routing](https://github.com/hydraponique/roscomvpn-routing) | **false** (форк) |
| `torrent_clients` | `rule-sets/yaml/torrent-clients.yaml` | [legiz-ru/mihomo-rule-sets](https://github.com/legiz-ru/mihomo-rule-sets) | true |
| `games` | `rule-sets/yaml/games.yaml` | [roscomvpn/custom-category](https://github.com/roscomvpn/custom-category) | **false** (форк + GFN) |
| `ru_apps` | `rule-sets/yaml/ru-apps.yaml` | roscomvpn/custom-category | true |

**Не синхронизируется:** `rule-sets/yaml/ai.yaml` — локальный набор.

Добавить новый источник — запись в `scripts/upstream-manifest.yaml`.

### Логика merge (без перетирания правок)

Для каждого файла хранится **baseline** в `.sync-upstream/baseline/` (снимок после последней успешной синхронизации).

| Ситуация | Результат |
|----------|-----------|
| local = baseline, upstream изменился, `auto_apply: true` | подтянуть upstream (`applied`) |
| local = baseline, upstream изменился, `auto_apply: false` | **конфликт** — нужен ручной merge |
| local изменён, upstream нет | оставить local (`kept_local`) |
| local и upstream изменились по-разному | **конфликт** |

При конфликте:

- отчёт: `.sync-upstream/SYNC-CONFLICTS.md`;
- файлы: `.sync-upstream/conflicts/<id>/{baseline,local,remote}`.

Разрешение:

```bash
# вручную собрать итог в рабочем файле, затем:
./scripts/upstream-sync.sh resolve template_remnawave
./scripts/upstream-sync.sh sync
```

Команды `upstream-sync.sh`:

```bash
./scripts/upstream-sync.sh sync            # YAML + MRS
./scripts/upstream-sync.sh download        # только скачать в staging
./scripts/upstream-sync.sh baseline-init   # зафиксировать текущие файлы как baseline
./scripts/upstream-sync.sh resolve [id]    # принять local как baseline
./scripts/upstream-sync.sh mrs-only        # только MRS
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

При конфликте — `rule-sets/mrs/SYNC-CONFLICTS.md` и `rule-sets/mrs/conflicts/<имя>/`. После ручного merge: `./scripts/mrs-tool.sh resolve [имя]`.

Редактируйте `rule-sets/mrs/text/<имя>.list`, затем коммит — **pre-commit** вызовет `pack` и добавит обновлённые `rule-sets/mrs/bin/*.mrs` в индекс.

Отдельные команды MRS: `download`, `unpack`, `pack`. Бинарник `mihomo` — из `PATH` или `.tools/mihomo` (в `.gitignore`).

Служебные каталоги (в `.gitignore`): `.sync-upstream/`, `rule-sets/mrs/.sync-staging/`, `rule-sets/mrs/.sync-baseline/`, `rule-sets/mrs/conflicts/`.

## games.yaml и GeForce NOW

`games.yaml` — гибрид: база roscomvpn + блок GeForce NOW + секция «Добавленно вручную».

Исключения с фиксированной политикой (не попадают в 🎮 Игры) — отдельные YAML, подключаются в шаблоне **до** `games`:

- `games-proxy-domains.yaml` — игровые домены → PROXY (в шаблоне **раньше** лаунчеров и MRS steam/epic)
- `games-launchers-direct.yaml` — лаунчеры платформ → DIRECT (после proxy-domains; до MRS steam/epic)

После sync с upstream roscomvpn скрипт автоматически пересобирает блок GFN (`regenerate_gfn_block`). Вручную:

```bash
python3 scripts/generate-gfn-games-block.py
```

Источники GFN:

- [gfnpc-en-US.json](https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json)
- [gamedatabase.json](https://gist.github.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161)
- [jsnli/steamappidlist](https://github.com/jsnli/steamappidlist) — `games_appid.json`

В блок попадают только игры с **явным онлайном в жанрах** GFN (Multiplayer, MMO, F2P online, Battle Royale, Co-op/PvP…). Офлайн-одиночки не включаются.

Игры вне каталога GFN (например **R.E.P.O.**) — в секции «Добавленно вручную» внизу `games.yaml` и в `generate-gfn-games-block.py` (не перезаписываются при пересборке GFN).

## Локальные дополнения в шаблоне

После merge upstream-шаблона из hydraponique проверьте, что сохранены локальные блоки:

### 🤖 ИИ

1. **proxy-groups** — группа `🤖 ИИ` (как у `📺 Youtube`: `remnawave.include-proxies: false`, прокси `🛡️ VPN` + переопределение стран).
2. **rule-providers** — провайдер `ai` → `rule-sets/yaml/ai.yaml`.
3. **rules** — `RULE-SET,ai,🤖 ИИ` **выше** `RULE-SET,google-play`.

### CDN URL в rule-providers

Post-hook `fix_template_cdn` подставляет jsDelivr **mireon-network/mihomo_routing** вместо legiz-ru / roscomvpn. Проверка:

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

Основа правил — [hydraponique/roscomvpn-routing](https://github.com/hydraponique/roscomvpn-routing), rule-sets — [legiz-ru](https://github.com/legiz-ru/mihomo-rule-sets), [roscomvpn/custom-category](https://github.com/roscomvpn/custom-category).
