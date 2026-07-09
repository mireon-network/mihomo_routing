#!/usr/bin/env python3
"""Слияние mihomo .list: уникальные непустые строки, сортировка по CIDR."""
from __future__ import annotations

import argparse
import ipaddress
import sys
from pathlib import Path


def sort_key(line: str) -> tuple:
    if "/" in line:
        try:
            net = ipaddress.ip_network(line, strict=False)
            return (0, net.version, int(net.network_address), net.prefixlen, line)
        except ValueError:
            pass
    key = line[2:] if line.startswith("+.") else line[1:] if line.startswith("+") else line
    return (1, key)


def read_cidr_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip().replace("\r", "")
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def verify_no_loss(inputs: list[Path], output: Path) -> None:
    """Каждая CIDR-строка из источников должна быть в итоге (дедуп только exact match)."""
    out_set = set(read_cidr_lines(output))
    union: set[str] = set()
    for path in inputs:
        for line in read_cidr_lines(path):
            union.add(line)
            if line not in out_set:
                raise ValueError(f"CIDR потерян при merge: {line!r} (из {path.name})")
    if out_set != union:
        extra = out_set - union
        raise ValueError(f"summary содержит лишние CIDR ({len(extra)}), пример: {next(iter(extra))!r}")
    print(
        f"mrs-merge-lists: verify OK — {len(union)} уникальных записей, потерь нет",
        file=sys.stderr,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge mihomo list files (unique lines)")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("inputs", nargs="+", type=Path)
    args = ap.parse_args()

    seen: set[str] = set()
    lines: list[str] = []
    for path in args.inputs:
        for raw in path.read_text(encoding="utf-8").splitlines():
            s = raw.strip().replace("\r", "")
            if not s or s.startswith("#"):
                continue
            if s not in seen:
                seen.add(s)
                lines.append(s)

    lines.sort(key=sort_key)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"mrs-merge-lists: {len(lines)} unique lines → {args.output}", file=sys.stderr)
    verify_no_loss(args.inputs, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
