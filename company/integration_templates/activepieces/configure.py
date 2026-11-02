#!/usr/bin/env python3
"""Prepare a plugin for an explicit official MCP URL; never connect or install."""
import argparse
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit


def prepare(url, output):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not parsed.path.rstrip("/").endswith("/mcp")
            or "YOUR-" in parsed.hostname.upper()):
        raise ValueError("Supply the exact HTTPS server URL copied from Activepieces Settings > MCP Server")
    output = Path(output)
    if output.exists():
        raise ValueError("Output must be a new directory")
    source = Path(__file__).resolve().parent
    output.mkdir(parents=True)
    shutil.copyfile(source / "plugin.json", output / "plugin.json")
    shutil.copytree(source / "skills", output / "skills")
    template = json.loads((source / "mcp.json.example").read_text())
    template["mcpServers"]["activepieces"]["url"] = url.rstrip("/")
    (output / "mcp.json").write_text(json.dumps(template, indent=2) + "\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(prepare(args.url, args.output))
