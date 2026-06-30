#!/usr/bin/env python3
"""tools/_vault.py — Shared vault resolver for SpielOS tools.

Resolution order (matching bin/spiel):
  1. --vault CLI arg (if provided)
  2. $VAULT_DIR env var
  3. ~/.config/spielos/config  (global config set by installer)
  4. Walk up from cwd for .spiel-vault file
  5. Walk up from cwd for team/strategist.md
  6. Walk up from this file for team/strategist.md

Returns None if no vault found (caller falls back to cwd or errors).
"""

from __future__ import annotations

import os
from pathlib import Path


GLOBAL_CONFIG = Path.home() / ".config" / "spielos" / "config"


def _read_global_config() -> Path | None:
    """Read VAULT_DIR from ~/.config/spielos/config, validate team/strategist.md exists."""
    try:
        if not GLOBAL_CONFIG.is_file():
            return None
        text = GLOBAL_CONFIG.read_text(encoding="utf-8").strip()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip().upper() != "VAULT_DIR":
                continue
            p = Path(v.strip().strip("\"'")).expanduser().resolve()
            if (p / "team" / "strategist.md").is_file():
                return p
        return None
    except Exception:
        return None


def resolve_vault(cli_vault: str | None = None) -> Path | None:
    # 1. CLI arg
    if cli_vault:
        p = Path(cli_vault).expanduser().resolve()
        if (p / "team" / "strategist.md").is_file():
            return p

    # 2. $VAULT_DIR env var — per-command override (e.g. VAULT_DIR=/path spiel post)
    env_vault = os.environ.get("VAULT_DIR", "").strip()
    if env_vault:
        p = Path(env_vault).expanduser().resolve()
        if (p / "team" / "strategist.md").is_file():
            return p

    # 3. Global config (~/.config/spielos/config) — primary, set by installer / spiel set-vault
    global_cfg = _read_global_config()
    if global_cfg is not None:
        return global_cfg

    cwd = Path.cwd().resolve()

    # 4. Walk up for .spiel-vault
    for parent in [cwd] + list(cwd.parents):
        spiel_vault = parent / ".spiel-vault"
        if spiel_vault.is_file():
            try:
                text = spiel_vault.read_text(encoding="utf-8").strip()
                for line in text.splitlines():
                    if line.startswith("VAULT_DIR="):
                        override = line.split("=", 1)[1].strip().strip("\"'")
                        p = Path(override).expanduser().resolve()
                        if (p / "team" / "strategist.md").is_file():
                            return p
                        break
            except Exception:
                pass

    # 5. Walk up for team/strategist.md
    for parent in [cwd] + list(cwd.parents):
        if (parent / "team" / "strategist.md").is_file():
            return parent

    # 6. Bundled shim/tool tree fallback: <vault>/tools/_vault.py or <vault>/bin/spiel.
    for parent in [Path(__file__).resolve().parent] + list(Path(__file__).resolve().parents):
        if (parent / "team" / "strategist.md").is_file():
            return parent

    return None
