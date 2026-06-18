#!/usr/bin/env python3
"""setup_buffer_channels.py — One-time helper to enumerate Buffer channels and write IDs to .env.

Lists all channels (across all orgs) accessible to your BUFFER_ACCESS_TOKEN.
With --pick, interactively selects channels and writes the chosen IDs to
~/.config/opencode/.env as BUFFER_CHANNEL_IDS.

Usage:
    python3 scripts/setup_buffer_channels.py           # list only
    python3 scripts/setup_buffer_channels.py --pick    # interactive picker
    python3 scripts/setup_buffer_channels.py --pick 3  # auto-pick first 3 (free tier cap)
"""

import argparse
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from engine_state import ENV_FILE

BUFFER_API_URL = "https://api.bufferapp.com/graphql"

LIST_CHANNELS_QUERY = """
query {
  account {
    organizations {
      id
      name
      channels { id service name }
    }
  }
}
"""


def load_env_file() -> dict:
    env = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def write_env_var(key: str, value: str) -> None:
    """Set or update a single key in ~/.config/opencode/.env. Preserves all other lines."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(existing):
        new = pattern.sub(f"{key}={value}", existing)
    else:
        sep = "" if not existing or existing.endswith("\n") else "\n"
        new = f"{existing}{sep}{key}={value}\n"
    ENV_FILE.write_text(new)
    os.chmod(ENV_FILE, 0o600)


def fetch_channels(token: str) -> list[dict]:
    payload = f'{{"query": {repr(LIST_CHANNELS_QUERY)}}}'
    req = urllib.request.Request(
        BUFFER_API_URL,
        data=payload.encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: Buffer API HTTP {e.code}: {err[:300]}")
        sys.exit(1)
    import json
    parsed = json.loads(data)
    if parsed.get("errors"):
        print(f"ERROR: Buffer returned errors: {parsed['errors']}")
        sys.exit(1)
    orgs = (parsed.get("data") or {}).get("account", {}).get("organizations", []) or []
    out = []
    for org in orgs:
        for ch in org.get("channels", []) or []:
            out.append({
                "id": ch.get("id"),
                "service": ch.get("service"),
                "name": ch.get("name"),
                "org": org.get("name"),
            })
    return out


def main():
    parser = argparse.ArgumentParser(description="List Buffer channels and write IDs to .env.")
    parser.add_argument("--pick", nargs="?", const="interactive", default=None, metavar="N_OR_INTERACTIVE",
                        help="Pick channels. Value: integer (auto-pick first N) or omit for interactive prompt.")
    args = parser.parse_args()

    env = load_env_file()
    token = env.get("BUFFER_ACCESS_TOKEN") or os.environ.get("BUFFER_ACCESS_TOKEN")
    if not token:
        print("ERROR: BUFFER_ACCESS_TOKEN not set.")
        print(f"  Add it to {ENV_FILE} first, or export it.")
        print("  Get a token at https://publish.buffer.com/settings/api")
        sys.exit(1)

    print("═══ Buffer Channels ═══")
    try:
        channels = fetch_channels(token)
    except Exception as e:
        print(f"ERROR: failed to fetch channels: {e}")
        sys.exit(1)

    if not channels:
        print("  (no channels found — connect social accounts at publish.buffer.com first)")
        return 1

    print(f"  Found {len(channels)} channel(s):\n")
    for i, ch in enumerate(channels, 1):
        print(f"  [{i:2d}] {ch['service']:14s}  {ch['name']:40s}  id={ch['id']}  ({ch['org']})")
    print()

    if args.pick is None:
        # List only mode
        print("Run with --pick to write chosen IDs to .env.")
        print("Run with --pick 3 to auto-pick the first 3 (free tier cap).")
        return 0

    # Pick mode
    chosen = []
    if args.pick.isdigit():
        n = int(args.pick)
        if n < 1 or n > len(channels):
            print(f"ERROR: --pick {n} out of range (1-{len(channels)})")
            sys.exit(1)
        chosen = channels[:n]
        print(f"Auto-picking first {n}:")
    else:
        print("Enter channel numbers to include (comma-separated), or 'all':")
        raw = input("> ").strip()
        if raw.lower() == "all":
            chosen = channels
        else:
            try:
                idxs = [int(x.strip()) for x in raw.split(",") if x.strip()]
            except ValueError:
                print("ERROR: invalid input")
                sys.exit(1)
            for i in idxs:
                if i < 1 or i > len(channels):
                    print(f"ERROR: index {i} out of range")
                    sys.exit(1)
                chosen.append(channels[i - 1])

    if len(chosen) > 3:
        print(f"WARN: Buffer free tier caps at 3 channels. You picked {len(chosen)}.")
        print("      Channels 4+ may be locked or fail at the API level.")
        ans = input("      Continue? (y/N): ").strip().lower()
        if ans not in ("y", "yes"):
            print("Cancelled.")
            return 0

    ids = ",".join(ch["id"] for ch in chosen)
    write_env_var("BUFFER_CHANNEL_IDS", ids)
    selected = ", ".join("{0}:{1}".format(ch["service"], ch["name"]) for ch in chosen)
    print(f"\n✓ Wrote BUFFER_CHANNEL_IDS={ids} to {ENV_FILE}")
    print(f"  Selected: {selected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
