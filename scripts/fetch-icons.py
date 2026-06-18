#!/usr/bin/env python3
"""fetch-icons.py — Download Scarlab icons from GitHub and save to assets/icons/.

Usage:
    python3 scripts/fetch-icons.py          # download all mapped icons
    python3 scripts/fetch-icons.py --list    # show current mapping
    python3 scripts/fetch-icons.py --all     # download ALL 1401 Scarlab icons
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.request import urlopen, Request

REPO = "https://raw.githubusercontent.com/la-moore/scarlab-icons/master/packages/icons/src"
ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "assets" / "brand-config.json"

# Map: (our_icon_name, scarlab_variant, scarlab_name)
# ghost = duotone (has opacity fills), base = simple stroke
ICON_MAP = [
    ("arrow-up-right", "base", "arrow-up-right"),
    ("ban", "ghost", "ban"),
    ("sparkles", "ghost", "sparkles"),
    ("code", "base", "code"),
    ("location", "ghost", "location"),
    ("crosshair", "base", "crosshair"),
    ("feather", "ghost", "feather"),
    ("git-pull-request", "ghost", "git-pull-request"),
    ("layers", "ghost", "layers"),
    ("bulb", "ghost", "bulb"),
    ("award", "ghost", "award"),
    ("mail", "ghost", "mail"),
    ("cog", "ghost", "cog"),
    ("qrcode", "ghost", "qrcode"),
    ("terminal", "ghost", "terminal"),
    ("trending-up", "base", "trending-up"),
]

USER_AGENT = "fetch-icons.py/1.0"


def download(name: str, variant: str, scarlab_name: str) -> bool:
    url = f"{REPO}/{variant}/{scarlab_name}.svg"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        resp = urlopen(req, timeout=15)
        svg = resp.read().decode("utf-8")
    except Exception as e:
        print(f"  ✗ {name} ({variant}/{scarlab_name}): {e}")
        return False

    # Replace hardcoded color with currentColor for CSS control
    svg = svg.replace('#323232', 'currentColor')
    # Strip width/height for scalable sizing
    svg = re.sub(r'\s+(width|height)="[^"]*"', '', svg)

    out = ICONS_DIR / f"{name}.svg"
    out.write_text(svg)
    print(f"  ✓ {name}.svg ({variant}/{scarlab_name}) — {len(svg)} bytes")
    return True


def show_mapping():
    print("Current icon mapping for brand-config.json:\n")
    print(f"{'Name':<20} {'Variant':<10} {'Scarlab Name':<20}")
    print("-" * 50)
    for name, variant, scarlab_name in ICON_MAP:
        print(f"{name:<20} {variant:<10} {scarlab_name:<20}")


def download_all():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    fail = 0
    for name, variant, scarlab_name in ICON_MAP:
        if download(name, variant, scarlab_name):
            ok += 1
        else:
            fail += 1
    print(f"\n  Downloaded: {ok}/{ok + fail}")
    return fail == 0


def main():
    ap = argparse.ArgumentParser(description="Download Scarlab icons from GitHub")
    ap.add_argument("--list", action="store_true", help="Show icon mapping")
    ap.add_argument("--all", action="store_true", help="Download all mapped icons (default)")
    args = ap.parse_args()

    if args.list:
        show_mapping()
        return 0

    ok = download_all()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
