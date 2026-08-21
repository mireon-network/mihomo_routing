#!/usr/bin/env python3
"""Вырезать из games.yaml процессы, которые уже есть в games-launchers.yaml.

games.yaml — зеркало апстрима; лаунчеры живут только в games-launchers.
После upstream-sync этот скрипт снова вычищает пересечения.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAMES = ROOT / "rule-sets/yaml/games.yaml"
LAUNCHERS = ROOT / "rule-sets/yaml/games-launchers.yaml"

PAYLOAD = re.compile(r"^(\s*-\s*)(PROCESS-NAME(?:-REGEX)?),(.+)$")
SECTION_HDR = re.compile(r"^\s*# --- .+ ---\s*$")


def payload_key(line: str) -> tuple[str, str] | None:
    m = PAYLOAD.match(line.rstrip("\n"))
    if not m:
        return None
    kind, raw = m.group(2), m.group(3)
    val = raw.split("#", 1)[0].strip()
    val = val.removesuffix(",DIRECT").removesuffix(",PROXY").strip()
    if not val:
        return None
    return kind, val.lower()


def keys_in(path: Path) -> set[tuple[str, str]]:
    return {k for line in path.read_text(encoding="utf-8").splitlines() if (k := payload_key(line))}


def collapse_empty_sections(lines: list[str]) -> list[str]:
    """Убрать заголовки `# --- Foo ---`, после которых до следующего такого нет payload."""
    n = len(lines)
    drop: set[int] = set()
    i = 0
    while i < n:
        if SECTION_HDR.match(lines[i].rstrip("\n")):
            j = i + 1
            has_payload = False
            while j < n and not SECTION_HDR.match(lines[j].rstrip("\n")):
                if payload_key(lines[j]):
                    has_payload = True
                    break
                j += 1
            if not has_payload:
                drop.add(i)
                k = i + 1
                while k < j and not lines[k].strip():
                    drop.add(k)
                    k += 1
        i += 1
    return [ln for idx, ln in enumerate(lines) if idx not in drop]


def main() -> int:
    if not GAMES.is_file() or not LAUNCHERS.is_file():
        print("нет games.yaml или games-launchers.yaml", file=sys.stderr)
        return 1

    launcher_keys = keys_in(LAUNCHERS)
    src = GAMES.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    kept: list[str] = []
    removed: list[str] = []
    for line in lines:
        key = payload_key(line)
        if key and key in launcher_keys:
            removed.append(key[1])
            continue
        kept.append(line)

    kept = collapse_empty_sections(kept)
    spaced: list[str] = []
    for line in kept:
        if (
            SECTION_HDR.match(line.rstrip("\n"))
            and spaced
            and spaced[-1].strip()
            and not spaced[-1].lstrip().startswith("#")
        ):
            spaced.append("\n")
        spaced.append(line)
    kept = spaced
    # не копить пустые хвосты из вырезанных секций
    text = "".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text.endswith("\n"):
        text += "\n"

    GAMES.write_text(text, encoding="utf-8")

    leftover = keys_in(GAMES) & launcher_keys
    if leftover:
        print("остались пересечения:", sorted(v for _, v in leftover), file=sys.stderr)
        return 1

    print(f"strip-games-launchers: убрано {len(removed)} ({', '.join(removed) or '—'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
