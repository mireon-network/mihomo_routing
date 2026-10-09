#!/usr/bin/env python3
"""Вырезать из games.yaml процессы лаунчеров и слишком широкие имена.

games.yaml — зеркало апстрима; лаунчеры живут только в games-launchers.
После upstream-sync этот скрипт снова вычищает пересечения.
javaw.exe — любой Java GUI, не только Minecraft; домены Minecraft уже в games-domain-custom.
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
# Переживает перезапись зеркала. Minecraft Java остаётся на доменах.
DROP_KEYS = frozenset({("PROCESS-NAME", "javaw.exe")})


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


def should_strip(key: tuple[str, str], launcher_keys: set[tuple[str, str]]) -> bool:
    return key in launcher_keys or key in DROP_KEYS


def self_check() -> None:
    javaw = ("PROCESS-NAME", "javaw.exe")
    steam = ("PROCESS-NAME", "steam.exe")
    assert should_strip(javaw, set())
    assert not should_strip(("PROCESS-NAME", "cs2.exe"), set())
    assert should_strip(steam, {steam})
    print("strip-games-launchers: self-check ok")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args == ["--self-check"]:
        self_check()
        return 0

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
        if key and should_strip(key, launcher_keys):
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

    left = keys_in(GAMES)
    leftover = left & launcher_keys
    if leftover or DROP_KEYS & left:
        print(
            "остались пересечения:",
            sorted(v for _, v in (leftover | (DROP_KEYS & left))),
            file=sys.stderr,
        )
        return 1

    print(f"strip-games-launchers: убрано {len(removed)} ({', '.join(removed) or '—'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
