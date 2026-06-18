#!/usr/bin/env python3
"""parse-frontmatter.py — Extract frontmatter from a markdown file and emit shell
exports. Used by publish-blog.sh to load frontmatter into the shell.

Usage:
    python3 parse-frontmatter.py <file.md>          # all fields
    python3 parse-frontmatter.py <file.md> KEY      # single field value (raw)

Outputs `export KEY="value"` lines on stdout for top-level scalar fields.
Lists are joined with ", " into a single string. Values are shell-escaped.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path


def parse_fm(text: str) -> dict:
    fields: dict = {}
    current_key: str | None = None
    in_list = False
    list_items: list[str] = []

    def flush_list():
        nonlocal list_items, current_key
        if current_key and list_items:
            fields[current_key] = list_items
        list_items = []
        current_key = None

    for line in text.split("\n"):
        if not line.strip():
            flush_list()
            in_list = False
            continue
        m_kv = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        m_li = re.match(r"^\s*-\s+(.*)$", line)
        if m_kv and not line.startswith(" ") and not line.startswith("\t"):
            flush_list()
            key, val = m_kv.group(1), m_kv.group(2).strip()
            if val == "":
                current_key = key
                in_list = True
                list_items = []
            elif val.startswith("[") and val.endswith("]"):
                inner = val[1:-1].strip()
                fields[key] = [
                    s.strip().strip('"').strip("'")
                    for s in inner.split(",")
                    if s.strip()
                ]
                current_key = None
                in_list = False
            else:
                fields[key] = val.strip('"').strip("'")
                current_key = None
                in_list = False
        elif m_li and in_list:
            list_items.append(m_li.group(1).strip().strip('"').strip("'"))
        else:
            flush_list()
            in_list = False
    flush_list()
    return fields


def shell_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")


def emit_exports(fields: dict) -> str:
    out = []
    for k, v in fields.items():
        key = k.upper().replace("-", "_")
        if isinstance(v, list):
            val = ", ".join(v)
        else:
            val = str(v)
        out.append(f'export {key}="{shell_escape(val)}"')
    aliases = {
        "standalone_test": "STANDALONE",
    }
    for src, alias in aliases.items():
        if src in fields:
            val = fields[src]
            if isinstance(val, list):
                val = ", ".join(val)
            out.append(f'export {alias}="{shell_escape(str(val))}"')
    return "\n".join(out) + "\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: parse-frontmatter.py <file> [KEY]", file=sys.stderr)
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        print("No frontmatter found", file=sys.stderr)
        sys.exit(1)
    fm = parse_fm(m.group(1))
    if len(sys.argv) >= 3:
        key = sys.argv[2]
        val = fm.get(key, "")
        if isinstance(val, list):
            print(", ".join(val))
        else:
            print(val)
    else:
        sys.stdout.write(emit_exports(fm))


if __name__ == "__main__":
    main()
