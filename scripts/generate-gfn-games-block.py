#!/usr/bin/env python3
"""Собрать блок GeForce NOW для rule-sets/yaml/games-process-custom.yaml.

games.yaml — зеркало апстрима (roscomvpn). Лаунчеры вырезает strip-games-launchers.py
в games-launchers.yaml. Наши добавления (GFN, ручные игры) живут в
games-process-custom.yaml; апстримные процессы и лаунчеры исключаются из блока,
чтобы не плодить дубли между наборами.

Источники:
  - https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json
  - https://gist.github.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161 (gamedatabase.json)
  - https://github.com/jsnli/steamappidlist — data/games_appid.json (appid → имя Steam)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAMES_CUSTOM_YAML = ROOT / "rule-sets/yaml/games-process-custom.yaml"
# Зеркала апстрима / соседние наборы — для дедупликации (их процессы не дублируем).
DEDUP_SOURCES = (
    ROOT / "rule-sets/yaml/games.yaml",
    ROOT / "rule-sets/yaml/games-launchers.yaml",
)

GFN_URL = "https://static.nvidiagrid.net/supported-public-game-list/locales/gfnpc-en-US.json"
GDB_URL = "https://gist.githubusercontent.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161/raw/gamedatabase.json"
STEAM_URL = "https://raw.githubusercontent.com/jsnli/steamappidlist/master/data/games_appid.json"

GFN_MARKER = "  # --- GeForce NOW"
MANUAL_MARKER = "  # --- Добавленно вручную"
DEFAULT_MANUAL = (
    "\n  # --- Добавленно вручную (нет в GFN / не попали в фильтр жанров) ---\n"
    "  # R.E.P.O. — co-op онлайн, Steam 3241660; в gfnpc-en-US.json отсутствует\n"
    "  # (REPO/Overwolf — только Windows; на Linux Proton видит REPO.exe)\n"
    "  # Raft.exe / Tanki.exe уже есть в апстримном games.yaml — не дублируем.\n"
    "  - PROCESS-NAME,REPO.exe\n"
    "  - PROCESS-NAME,REPO-Win64-Shipping.exe\n"
    "  - PROCESS-NAME,Raft                  # Raft — нативный macOS\n"
    "  - PROCESS-NAME,Overwolf.exe\n"
)

# Не попадают в games.yaml — см. rule-sets/yaml/games-launchers.yaml
LAUNCHER_PROCESS_EXACT = frozenset(
    {
        "battalionlauncher.exe",
        "steamlauncher.exe",
        "launcher.exe",
        "slauncher.exe",
        "dundeflauncher.exe",
        "wowslauncher.exe",
        "mycomgames.exe",
    }
)


def usable_process(proc: str) -> bool:
    return bool(proc) and not any(ch in proc for ch in "\n\r#,:" )


def is_launcher_process(proc: str) -> bool:
    pl = proc.lower()
    if pl in LAUNCHER_PROCESS_EXACT:
        return True
    return pl.endswith("launcher.exe")

# Жанры GFN, где в метаданных явно указан сетевой/мультиплеерный геймплей.
ONLINE_GENRE_KEYWORDS = (
    "multiplayer",
    "massively multiplayer",
    "massively multiplayer online",
    "free to play",
    "free-to-play",
    "battle royale",
    "mmo",
    "online co-op",
    "online co op",
    " co-op",
    "co-op",
    "pvp",
    "competitive",
    "esports",
    "cross-platform multiplayer",
    "cross platform multiplayer",
)


def needs_online_gameplay(g: dict) -> bool:
    genres = " | ".join(x.lower() for x in (g.get("genres") or []))
    return any(k in genres for k in ONLINE_GENRE_KEYWORDS)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "mihomo-routing/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[™®©]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def split_owned(text: str) -> tuple[str, str]:
    """Голова до маркера GFN и ручной хвост. Хвост пустой, если секции ещё нет."""
    gfn_at = text.find(GFN_MARKER)
    if gfn_at < 0:
        return text.rstrip() + "\n", ""
    manual_at = text.find(MANUAL_MARKER, gfn_at)
    head = text[:gfn_at].rstrip() + "\n"
    if manual_at < 0:
        return head, ""
    return head, text[manual_at:]


def splice_gfn(text: str, gfn_lines: list[str]) -> str:
    head, manual_tail = split_owned(text)
    block = "\n".join(gfn_lines)
    if not block.endswith("\n"):
        block += "\n"
    if manual_tail:
        return head + block + "\n" + manual_tail
    return head + block + DEFAULT_MANUAL


def self_check() -> None:
    src = (
        "head\n"
        "  # --- GeForce NOW old\n"
        "  - PROCESS-NAME,old.exe\n"
        "\n"
        "  # --- Добавленно вручную (нет в GFN / не попали в фильтр жанров) ---\n"
        "  - PROCESS-NAME,KEEP.exe\n"
    )
    out = splice_gfn(src, ["  # --- GeForce NOW new", "  - PROCESS-NAME,new.exe", ""])
    assert "old.exe" not in out
    assert "new.exe" in out and "KEEP.exe" in out
    assert out.index("new.exe") < out.index("KEEP.exe")
    assert not usable_process("000: Dawn of War III")
    assert usable_process("Among Us.exe")
    print("generate-gfn-games-block: self-check ok")


def main() -> int:
    if sys.argv[1:2] == ["--self-check"]:
        self_check()
        return 0
    gfn = json.loads(fetch(GFN_URL))
    gdb = json.loads(fetch(GDB_URL))
    steam = json.loads(fetch(STEAM_URL))
    appid_name = {str(x["appid"]): x["name"] for x in steam}

    name_to_proc: dict[str, str] = {}
    norm_to_proc: dict[str, str] = {}
    for e in gdb:
        n = (e.get("Name") or "").strip()
        p = (e.get("processName") or "").strip()
        if n and p:
            name_to_proc[n.lower()] = p
            norm_to_proc[norm(n)] = p

    def match_exact(title: str | None) -> str | None:
        if not title:
            return None
        return name_to_proc.get(title.lower()) or norm_to_proc.get(norm(title))

    def steam_appid(g: dict) -> str | None:
        m = re.search(r"/app/(\d+)", g.get("steamUrl") or "")
        return m.group(1) if m else None

    def resolve(g: dict) -> tuple[str | None, str]:
        proc = match_exact(g["title"])
        if proc:
            return proc, "gfn_title"
        aid = steam_appid(g)
        if aid:
            proc = match_exact(appid_name.get(aid))
            if proc:
                return proc, "steam_name"
        return None, "none"

    def process_names(text: str) -> set[str]:
        names: set[str] = set()
        for m in re.finditer(r"PROCESS-NAME,([^\n]+)", text):
            v = m.group(1).split("#", 1)[0].strip()  # отсечь инлайн-комментарий
            v = v.removesuffix(",DIRECT").removesuffix(",PROXY").strip()
            if v and not v.startswith("(?"):
                names.add(v.lower())
        return names

    current = GAMES_CUSTOM_YAML.read_text(encoding="utf-8")
    head, manual_tail = split_owned(current)
    existing: set[str] = process_names(head)
    existing |= process_names(manual_tail or DEFAULT_MANUAL)
    for src in DEDUP_SOURCES:
        if src.is_file():
            existing |= process_names(src.read_text(encoding="utf-8"))

    entries: list[tuple[str, str, str, str, list]] = []
    stats: dict[str, int] = {}
    for g in sorted(
        (x for x in gfn if x.get("status") == "AVAILABLE"),
        key=lambda x: x["title"].lower(),
    ):
        if not needs_online_gameplay(g):
            stats["skipped_offline"] = stats.get("skipped_offline", 0) + 1
            continue
        proc, via = resolve(g)
        if not proc:
            stats["skipped_no_exe"] = stats.get("skipped_no_exe", 0) + 1
            continue
        if not usable_process(proc):
            stats["skipped_bad_name"] = stats.get("skipped_bad_name", 0) + 1
            continue
        if is_launcher_process(proc):
            stats["skipped_launcher"] = stats.get("skipped_launcher", 0) + 1
            continue
        stats[via] = stats.get(via, 0) + 1
        pl = proc.lower()
        if pl in existing:
            continue
        existing.add(pl)
        entries.append(
            (g["title"], proc, via, g.get("store", ""), g.get("genres") or [])
        )

    lines = [
        GFN_MARKER + " (только онлайн/MP по жанрам GFN) ---",
        "  # JSON: " + GFN_URL,
        "  # exe:  " + "https://gist.github.com/Gr3gorywolf/1757c79ce1152966bf77bf8c6d069161",
        "  # Steam appid→name: https://github.com/jsnli/steamappidlist (games_appid.json)",
        f"  # добавлено {len(entries)} PROCESS-NAME",
        f"  # пропущено офлайн (нет MP/MMO/F2P online в жанрах): {stats.get('skipped_offline', 0)}",
        f"  # пропущено без exe в gamedatabase: {stats.get('skipped_no_exe', 0)}",
        "",
    ]
    for title, proc, via, store, genres in entries:
        g = ", ".join(genres[:3]) if genres else ""
        meta = f"{store} | {g}" if g else store
        lines.append(f"  # {title} ({meta}; match={via})")
        lines.append(f"  - PROCESS-NAME,{proc}")
        lines.append("")

    out = splice_gfn(current, lines)
    if out == current:
        print(
            f"generate-gfn-games-block: без изменений "
            f"({len(entries)} GFN PROCESS-NAME, stats={stats})"
        )
        return 0
    GAMES_CUSTOM_YAML.write_text(out, encoding="utf-8")
    print(
        f"generate-gfn-games-block: обновлён {GAMES_CUSTOM_YAML} "
        f"({len(entries)} GFN PROCESS-NAME, stats={stats})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
