#!/usr/bin/env python3
"""Фикстурный тест групп: шаблон + реалистичные (обезличенные) имена узлов → живой mihomo.

Эмулирует отдачу Remnawave (remnawave-ключи вырезаны, узлы — в общий proxies:),
запускает mihomo без TUN/DNS/rule-providers и через external-controller проверяет:
  full  — у каждого пула с filter есть свои узлы, чужие/устаревшие имена не попали;
          запросы через каждую страну/Автовыбор/WL проходят (REJECT-заглушка не выбрана);
  empty — узлов нужной схемы нет → empty-fallback подставляет REJECT (не COMPATIBLE/DIRECT),
          запросы через страны/WL не проходят (fail-closed). Требует mihomo >= v1.19.27.
  failover — после успешной проверки прямые (gt_) гаснут. За 45с страна сама уходит на мосты.
          45с длиннее interval 30 и короче 180: lazy true или interval 180 тест не проходит.
Узлы — type: direct, кроме gt_ в failover (локальный HTTP CONNECT). Цель — локальный HTTP 204.

Использование: MIHOMO_BIN=... scripts/test-groups-fixture.py [MIHOMO/template_remnawave.yaml ...]
"""
from __future__ import annotations

import http.server
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COUNTRIES = ("fi", "de", "fr", "nl", "pl", "us")
BUILTIN = {"DIRECT", "REJECT", "REJECT-DROP", "COMPATIBLE", "PASS"}
# Дольше interval fallback (30с), короче прежнего 180с.
FAILOVER_WAIT_S = 45
# Дольше timeout проверки (3с): стартовый health-check уже закончился до обрыва прямых.
FAILOVER_SETTLE_S = 4

# Схема имён (см. шапку шаблона): прямая gt_<cc>-<хостер>-<октет>, мост bgt_<локация-хостер-октет>_gt_<cc>-…
def full_nodes() -> list[str]:
    nodes = []
    for i, cc in enumerate(COUNTRIES):
        nodes += [
            f"gt_{cc}-hz-{101 + i}",
            f"gt_{cc}-aeza-extra-{111 + i}",           # хостер с «-»
            f"bgt_spb-tw-{161 + i}_gt_{cc}-hz-{121 + i}",
        ]
    nodes += ["wlgt_fi-hz-131", "wlgt_DE-h2n-132"]   # WL-фильтр с (?i)
    return nodes + DECOYS


DECOYS = [
    "bg_fi-hz-141",                     # старая схема мостов — не должна попадать никуда
    "gt-fi-hz-142",                     # опечатка в разделителе
    "bgt_spb-tw-161_bg_de-hz-143",      # мост на старый выход
    "ℹ️ Подписка до 01.12.2026",        # инфо-хост Remnawave
]


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # mihomo шлёт два HEAD подряд по одному соединению

    def do_GET(self):  # noqa: N802
        self.send_response(204)
        self.end_headers()

    do_HEAD = do_GET

    def log_message(self, *a):
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def remnawave_render(tpl: dict, nodes: list[str]) -> dict:
    """Как renderConfig в remnawave/backend: remnawave-ключи вырезаны, proxies групп = list|[]."""
    doc = {k: v for k, v in tpl.items() if k != "remnawave"}
    doc["proxies"] = [*(tpl.get("proxies") or []), *({"name": n, "type": "direct"} for n in nodes)]
    groups = []
    for g in tpl.get("proxy-groups") or []:
        g = {k: v for k, v in g.items() if k != "remnawave"}
        g["proxies"] = list(g.get("proxies") or [])
        groups.append(g)
    doc["proxy-groups"] = groups
    return doc


def build_config(tpl: dict, nodes: list[str], http_port: int, api: int, mixed: int):
    doc = remnawave_render(tpl, nodes)
    for k in ("tun", "dns", "sniffer", "rule-providers", "hosts", "profile"):
        doc.pop(k, None)
    test_url = f"http://127.0.0.1:{http_port}/generate_204"
    routes = {}
    for g in doc["proxy-groups"]:
        if "url" in g:
            g["url"] = test_url
        if g.get("type") == "fallback" or g["name"] in ("⚡️ Автовыбор", "🇷🇺 Белые списки"):
            routes[g["name"]] = free_port()
    doc.update({
        "mixed-port": mixed,                 # только в тесте: через него шлём запросы
        "external-controller": f"127.0.0.1:{api}",
        "log-level": "error",  # HTTP health-check URL даёт warning-спам
        "rules": [f"DST-PORT,{p},{name}" for name, p in routes.items()] + ["MATCH,REJECT"],
    })
    return doc, routes


def api_get(api: int, path: str):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        f"http://127.0.0.1:{api}{path}", timeout=3
    ) as r:
        return json.load(r)


def via_proxy(mixed: int, port: int) -> int | None:
    """HTTP-запрос через mixed-port mihomo к 127.0.0.1:port; код ответа или None."""
    try:
        with socket.create_connection(("127.0.0.1", mixed), timeout=4) as s:
            s.sendall(f"GET http://127.0.0.1:{port}/ HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                      "Connection: close\r\n\r\n".encode())
            data = s.recv(64)
        m = re.match(rb"HTTP/1\.[01] (\d{3})", data)
        return int(m.group(1)) if m else None
    except OSError:
        return None


def run(mihomo: str, tpl_path: Path, scenario: str) -> list[str]:
    tpl = yaml.safe_load(tpl_path.read_text(encoding="utf-8"))
    nodes = full_nodes() if scenario == "full" else DECOYS
    errs: list[str] = []

    servers = []
    http_port = free_port()
    api, mixed = free_port(), free_port()
    doc, routes = build_config(tpl, nodes, http_port, api, mixed)
    for p in [http_port, *routes.values()]:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)

    with tempfile.TemporaryDirectory() as work:
        cfg = Path(work) / "config.yaml"
        cfg.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        proc = subprocess.Popen([mihomo, "-d", work, "-f", str(cfg)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                try:
                    api_get(api, "/version")
                    break
                except OSError:
                    if proc.poll() is not None:
                        return [f"mihomo упал: {proc.stdout.read().decode(errors='replace')[-2000:]}"]
                    time.sleep(0.1)
            else:
                return ["mihomo не поднял external-controller"]
            time.sleep(3)  # первичный health-check (выполняется сразу, независимо от lazy)
            proxies = api_get(api, "/proxies")["proxies"]

            for g in tpl.get("proxy-groups") or []:
                if not g.get("filter"):
                    continue
                name = g["name"]
                members = proxies[name]["all"]
                real = [m for m in members if m not in BUILTIN]
                rx = re.compile(g["filter"].replace("(?i)", ""), re.I if "(?i)" in g["filter"] else 0)
                expected = [n for n in nodes if rx.search(n)]
                if sorted(real) != sorted(expected):
                    errs.append(f"{name}: узлы {real} ≠ ожидаемые {expected}")
                if any(m in ("DIRECT", "COMPATIBLE") for m in members):
                    errs.append(f"{name}: в группе {members} — утечка в DIRECT")
                if scenario == "full" and not real:
                    errs.append(f"{name}: пул пуст")
                if scenario == "empty" and members != ["REJECT"]:
                    errs.append(f"{name}: пустой пул = {members}, ожидали ['REJECT']")
                if g.get("empty-fallback") != "REJECT":
                    errs.append(f"{name}: нет empty-fallback: REJECT — пустой пул станет DIRECT")
                if "REJECT" in (g.get("proxies") or []) and scenario == "full":
                    errs.append(f"{name}: явная REJECT-заглушка в proxies (при ложном падении health-check блокирует трафик)")
                if any(d in members for d in DECOYS):
                    errs.append(f"{name}: попал узел вне схемы имён: {members}")

            for name, port in routes.items():
                if name not in proxies:
                    continue
                codes = [via_proxy(mixed, port) for _ in range(12)]
                ok = sum(c == 204 for c in codes)
                if scenario == "full" and ok != len(codes):
                    errs.append(f"{name}: прошло {ok}/{len(codes)} запросов (REJECT-заглушка выбрана?)")
                if scenario == "empty" and ok:
                    errs.append(f"{name}: при пустых пулах прошло {ok} запросов — утечка")
        finally:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
            for s in servers:
                s.shutdown()
    return errs


def country_fallback_name(tpl: dict) -> str | None:
    for g in tpl.get("proxy-groups") or []:
        proxies = g.get("proxies") or []
        if g.get("type") == "fallback" and proxies == [f"{g['name']} · прямая", f"{g['name']} · мосты"]:
            return g["name"]
    return None


def _node_alive(proxy: dict) -> bool:
    if proxy.get("alive") is True:
        return True
    hist = proxy.get("history") or []
    return bool(hist) and (hist[-1].get("delay") or 0) > 0


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            chunk = src.recv(65536)
            if not chunk:
                break
            dst.sendall(chunk)
    except OSError:
        pass


def _tunnel(conn: socket.socket) -> None:
    """HTTP CONNECT → TCP к цели. Пока слушатель жив, gt_* проходят health-check."""
    upstream = None
    try:
        data = b""
        conn.settimeout(5)
        while b"\r\n\r\n" not in data and len(data) < 65536:
            chunk = conn.recv(4096)
            if not chunk:
                return
            data += chunk
        parts = data.split(b"\r\n", 1)[0].decode("ascii", "replace").split()
        if len(parts) < 2 or parts[0].upper() != "CONNECT":
            conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n")
            return
        host, sep, port_s = parts[1].rpartition(":")
        if not sep:
            return
        upstream = socket.create_connection((host.strip("[]"), int(port_s)), timeout=3)
        conn.sendall(b"HTTP/1.1 200 Connection Established\r\nContent-Length: 0\r\n\r\n")
        rest = data.split(b"\r\n\r\n", 1)[1]
        if rest:
            upstream.sendall(rest)
        conn.settimeout(None)
        upstream.settimeout(None)
        threading.Thread(target=_pipe, args=(conn, upstream), daemon=True).start()
        _pipe(upstream, conn)
    except OSError:
        pass
    finally:
        for sock in (conn, upstream):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass


def start_connect_proxy(port: int, stop: threading.Event) -> socket.socket:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen()
    listener.settimeout(0.2)

    def accept_loop() -> None:
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(target=_tunnel, args=(conn,), daemon=True).start()

    threading.Thread(target=accept_loop, daemon=True).start()
    return listener


def _poll_proxies(api: int, proc: subprocess.Popen, seconds: float, pred):
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        if proc.poll() is not None:
            return None
        try:
            last = api_get(api, "/proxies")["proxies"]
        except (OSError, KeyError, ValueError):
            time.sleep(0.2)
            continue
        if pred(last):
            return last
        time.sleep(0.4)
    return None


def run_failover(mihomo: str, tpl_path: Path) -> list[str]:
    """Прямые живы на старте, потом гаснут. Периодическая проверка (не пачка ошибок) уводит на мосты."""
    tpl = yaml.safe_load(tpl_path.read_text(encoding="utf-8"))
    country = country_fallback_name(tpl)
    if country is None:
        return []
    direct_name = f"{country} · прямая"
    bridge_name = f"{country} · мосты"
    fb = next(g for g in tpl["proxy-groups"] if g["name"] == country)
    if fb.get("lazy") is not False or fb.get("interval") != 30:
        return [f"{country}: нужен lazy: false и interval: 30, сейчас lazy={fb.get('lazy')!r} interval={fb.get('interval')!r}"]
    child = next(g for g in tpl["proxy-groups"] if g["name"] == direct_name)
    rx = re.compile(child["filter"])
    direct_nodes = [n for n in full_nodes() if rx.search(n)]
    if not direct_nodes:
        return [f"{direct_name}: фикстура не собрала прямые узлы"]

    errs: list[str] = []
    http_port = free_port()
    proxy_port = free_port()
    api, mixed = free_port(), free_port()
    doc, routes = build_config(tpl, full_nodes(), http_port, api, mixed)
    for p in doc["proxies"]:
        if str(p.get("name", "")).startswith("gt_"):
            name = p["name"]
            p.clear()
            p.update({"name": name, "type": "http", "server": "127.0.0.1", "port": proxy_port})

    stop = threading.Event()
    listener = start_connect_proxy(proxy_port, stop)
    servers = []
    for p in [http_port, *routes.values()]:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)

    def close_proxy() -> None:
        stop.set()
        try:
            listener.close()
        except OSError:
            pass

    with tempfile.TemporaryDirectory() as work:
        cfg = Path(work) / "config.yaml"
        cfg.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        proc = subprocess.Popen(
            [mihomo, "-d", work, "-f", str(cfg)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        log_chunks: list[bytes] = []

        def drain() -> None:
            if proc.stdout is None:
                return
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                log_chunks.append(chunk)

        threading.Thread(target=drain, daemon=True).start()

        def crash_tail() -> str:
            return b"".join(log_chunks).decode(errors="replace")[-2000:]

        try:
            up = False
            for _ in range(100):
                try:
                    api_get(api, "/version")
                    up = True
                    break
                except OSError:
                    if proc.poll() is not None:
                        time.sleep(0.2)
                        return [f"mihomo упал: {crash_tail()}"]
                    time.sleep(0.1)
            if not up:
                return [f"mihomo не поднял external-controller: {crash_tail()}"]

            alive = _poll_proxies(
                api, proc, 15,
                lambda ps: ps.get(country, {}).get("now") == direct_name
                and all(_node_alive(ps.get(n, {})) for n in direct_nodes),
            )
            if alive is None:
                return [f"{country}: прямые не стали живыми за 15с, узлы {direct_nodes}. {crash_tail()}"]
            time.sleep(FAILOVER_SETTLE_S)
            if api_get(api, "/proxies")["proxies"].get(country, {}).get("now") != direct_name:
                return [f"{country}: прямая слетела до обрыва прокси"]
            close_proxy()
            switched = _poll_proxies(
                api, proc, FAILOVER_WAIT_S,
                lambda ps: ps.get(country, {}).get("now") == bridge_name,
            )
            if switched is None:
                now = None
                try:
                    now = api_get(api, "/proxies")["proxies"].get(country, {}).get("now")
                except (OSError, KeyError, ValueError):
                    pass
                return [f"{country}: за {FAILOVER_WAIT_S}с now={now!r}, ждали {bridge_name!r}"]
            code = via_proxy(mixed, routes[country])
            if code != 204:
                errs.append(f"{country}: после перехода на мост ответ {code}")
        finally:
            close_proxy()
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
            for s in servers:
                s.shutdown()
    return errs


def main(argv: list[str]) -> int:
    mihomo = os.environ.get("MIHOMO_BIN") or str(ROOT / ".tools/mihomo")
    ver = subprocess.run([mihomo, "-v"], capture_output=True, text=True).stdout.split("\n")[0]
    files = [Path(a) for a in argv] or [ROOT / "MIHOMO/template_remnawave.yaml", ROOT / "MIHOMO/wl.yaml"]
    rc = 0
    for f in files:
        for scenario in ("full", "empty"):
            errs = run(mihomo, f, scenario)
            tag = f"{f.name} [{scenario}]"
            if errs:
                rc = 1
                print(f"❌ {tag}", file=sys.stderr)
                for e in errs:
                    print(f"   {e}", file=sys.stderr)
            else:
                print(f"✅ {tag}")
        if country_fallback_name(yaml.safe_load(f.read_text(encoding="utf-8"))):
            errs = run_failover(mihomo, f)
            tag = f"{f.name} [failover]"
            if errs:
                rc = 1
                print(f"❌ {tag}", file=sys.stderr)
                for e in errs:
                    print(f"   {e}", file=sys.stderr)
            else:
                print(f"✅ {tag}")
    print(f"test-groups-fixture: {ver}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
