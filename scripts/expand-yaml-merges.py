#!/usr/bin/env python3
"""Развернуть <<: *rp_* в Mihomo-шаблонах (Remnawave/node-yaml падает на alias flood)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BLOCKS = {
    "rp_domain": """\
    type: http
    proxy: {proxy}
    interval: {interval}
    behavior: domain
    format: mrs""",
    "rp_ipcidr": """\
    type: http
    proxy: {proxy}
    interval: {interval}
    behavior: ipcidr
    format: mrs""",
    "rp_domain_yaml": """\
    type: http
    proxy: {proxy}
    interval: {interval}
    behavior: domain
    format: yaml""",
    "rp_ipcidr_yaml": """\
    type: http
    proxy: {proxy}
    interval: {interval}
    behavior: ipcidr
    format: yaml""",
    "rp_classical": """\
    type: http
    proxy: {proxy}
    interval: {interval}
    behavior: classical
    format: yaml""",
}

ANCHOR_TAIL = """\
  rp_base: &rp_base
    type: http
    proxy: {proxy}
    interval: 86400
  rp_domain: &rp_domain
    <<: *rp_base
    behavior: domain
    format: mrs
  rp_ipcidr: &rp_ipcidr
    <<: *rp_base
    behavior: ipcidr
    format: mrs
  rp_domain_yaml: &rp_domain_yaml
    <<: *rp_base
    behavior: domain
    format: yaml
  rp_ipcidr_yaml: &rp_ipcidr_yaml
    <<: *rp_base
    behavior: ipcidr
    format: yaml
  rp_classical: &rp_classical
    <<: *rp_base
    behavior: classical
    format: yaml"""


def proxy_for(path: Path) -> str:
    return "PROXY" if path.name == "wl.yaml" else "⚡️ Авто"


def expand_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    proxy = proxy_for(path)
    out = text

    if ANCHOR_TAIL.format(proxy=proxy) in out:
        out = out.replace(
            ANCHOR_TAIL.format(proxy=proxy) + "\n",
            f"  # rp_* шаблоны развёрнуты в rule-providers (Remnawave/node-yaml alias limit)\n",
        )

    for name, tmpl in BLOCKS.items():
        default = tmpl.format(proxy=proxy, interval=86400)
        out = out.replace(f"    <<: *{name}\n", default + "\n")

    # interval: 86400 из шаблона + interval: 2592000 в провайдере → дубликат ключа
    out = re.sub(
        r"    interval: 86400\n"
        r"(    behavior: [^\n]+\n    format: [^\n]+\n"
        r"    url: [^\n]+\n    path: [^\n]+\n)"
        r"    interval: (\d+)\n",
        r"\1    interval: \2\n",
        out,
    )

    if out == text:
        return False
    path.write_text(out, encoding="utf-8")
    return True


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] or list((ROOT / "MIHOMO").glob("*.yaml"))
    for path in paths:
        if expand_file(path):
            print(f"expanded: {path}")
        else:
            print(f"unchanged: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
