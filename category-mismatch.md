# Несовпадения категорий

`+.windsurf.com` в русских категориях уже нет. Он остался только в `meta-ai`.

Ниже список строк, которые не относятся к своей категории. Каждая сверена с файлом. Всё из `category-ru-davoyan` дополнительно лежит в `summary-category-ru`, потому что это склейка.

## Убрать из русских списков

| Строка | Почему | Где ещё |
|---|---|---|
| `+.by` | весь домен Беларуси | только `category-ru-davoyan` |
| `+.ubs.com` | банк UBS, Швейцария | `meta-category-ru`, `meta-category-bank-ru` |
| `+.autobahn.db.com` | Deutsche Bank Autobahn, Германия. Сайт открывается как Autobahn | только `category-ru-davoyan` |
| `+.bk.mufg.jp` | банк MUFG, Япония | только `category-ru-davoyan` |
| `+.mizuhogroup.com` | Mizuho, Япония | только `category-ru-davoyan` |
| `+.altynbank.com` | Altyn Bank, Казахстан | только `category-ru-davoyan` |
| `+.checkip.amazonaws.com` | проверка IP у Amazon | только `category-ru-davoyan` |
| `+.ifconfig.me` | чужой сервис «покажи мой IP» | только `category-ru-davoyan` |
| `+.ip.sb` | то же | только `category-ru-davoyan` |
| `+.ipapi.is` | то же | только `category-ru-davoyan` |
| `+.ipify.org` | то же | только `category-ru-davoyan` |
| `+.iplocate.io` | то же | только `category-ru-davoyan` |
| `+.showip.net` | то же | только `category-ru-davoyan` |
| `+.ru.com` | суффикс CentralNic, ловит любое имя под `ru.com` | `meta-category-ru` |
| `+.ru.net` | то же | `meta-category-ru` |
| `+.asiangooglenetwork.com` | рекламная сеть Google | `meta-category-ru`, `meta-category-media-ru` |
| `+.psk` | не домен и не зона, строка ничего не ловит | только `category-ru-davoyan` |
| `+.coloradogrowers.com` | американское имя, русского оператора нет | только `category-ru-davoyan` |
| `+.doktor.kr` | корейская зона `.kr`, адрес не резолвится | только `category-ru-davoyan` |
| `+.medtrum.eu` | Medtrum, Китай/ЕС | только `category-ru-davoyan` |
| `+.ewisdom.us.kg` | бесплатный поддомен, магазин не подтверждён | `meta-category-ru`, `meta-category-ecommerce-ru` |

## Посмотреть, но не факт

| Строка | Где | Почему под вопросом |
|---|---|---|
| `+.justveryok.com` | `meta-mailru-group`, `meta-category-ru`, Davoyan | похоже на случайный домен Mail.ru, не продукт. Сайт не открылся |
| `+.keyboardmen.com` | те же | то же |
| `+.rabbitcounter.com` | те же | то же |
| `+.sayeasy.eu` | те же | то же |
| `+.themeforest.net` | `meta-ai` | магазин тем Envato, не ИИ. Сайт это подтвердил |
| `+.envato.com` | `meta-ai` | то же |
| `+.envato-static.com` | `meta-ai` | то же |
| `+.envatousercontent.com` | `meta-ai` | то же |

## Не русские, но в других категориях

| Строка | Категория | Почему |
|---|---|---|
| `+.in.th` | `meta-category-games` | весь тайский суффикс `*.in.th` уезжает в игры |
| `+.gamebanana.com` | `meta-category-games` | сайт модов. Вики и моды этот набор выкидывает |
| `+.loverslab.com` | `meta-category-games` | то же |
| `+.thunderstore.io` | `meta-category-games` | то же |
| `+.thunderstore.org` | `meta-category-games` | то же |
| `+.r2modman.com` | `meta-category-games` | то же |
| `25.0.0.0/8` | `private-ips-custom` | сеть минобороны Великобритании |
| `26.0.0.0/8` | `private-ips-custom` | сеть минобороны США |

## IP

В `summary-ru-ips` целиком внутри Cloudflare лежит **2539** префиксов: 422 из `meta-geoip-ru` и 2527 из `ips-for-ru`. Внутри Google — **758**: 95 и 753. С голосовыми адресами Discord и с частными сетями пересечений нет. `8.8.8.8` и `1.1.1.1` в русский набор не входят.

## Оставить

| Строка | Почему оставить |
|---|---|
| `+.windsurf.com` | уже убран из русских списков, лежит в `meta-ai` |
| `+.unidraw.io` | русская онлайн-доска, сайт на русском |
| `noda.finance` | открывается как `nodabank.ru` |
| `tehnodom.com` | открывается как Selectel Chipcore |
| `cloudru.cn` | Cloud.ru |
| `hayya.ae` | такси в Дубае, список Яндекса |
| `+.xsolla.com`, `+.xsolla.net` | в шаблоне оставлены специально |
| `+.rnd.ru` | `category-ban-ru` специально стоит выше русского catch-all |
