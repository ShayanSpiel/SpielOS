#!/usr/bin/env python3
"""engine_config.py — Single source of truth for rules.yaml access.

All mechanical configuration lives in rules.yaml. This module provides
typed accessors. No script should import rules.yaml directly.
"""

from pathlib import Path

import yaml

from engine_state import RULES_FILE


class Config:
    def __init__(self) -> None:
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is not None:
            return self._data
        if not RULES_FILE.exists():
            msg = f"rules.yaml not found: {RULES_FILE}"
            raise FileNotFoundError(msg)
        with RULES_FILE.open() as f:
            self._data = yaml.safe_load(f) or {}
        return self._data

    def reload(self) -> None:
        self._data = None
        self._load()

    def get(self, *keys: str, default=None):
        data = self._load()
        for k in keys:
            if isinstance(data, dict):
                data = data.get(k, {})
            else:
                return default
        return data if data is not None else default

    @property
    def posting_mode(self) -> str:
        return self.get("posting", "mode", default="manual")

    @property
    def quality_threshold(self) -> float:
        return float(self.get("posting", "quality_threshold", default=0.85))

    @property
    def max_auto_day(self) -> int:
        return int(self.get("posting", "max_auto_day", default=3))

    @property
    def require_confirm(self) -> list:
        return self.get("posting", "require_confirm", default=["blog", "linkedin"])

    @property
    def char_limits(self) -> dict:
        return self.get("char_limits", default={})

    @property
    def gates_enabled(self) -> dict:
        return self.get("gates", default={})

    @property
    def gate_params(self) -> dict:
        return self.get("gate_params", default={})

    @property
    def safe_openers(self) -> list[str]:
        return self.get("safe_openers", default=[])

    @property
    def banned_openers(self) -> list[str]:
        return self.get("banned_openers", default=[])

    @property
    def lesson_triggers(self) -> list[str]:
        return self.get("lesson_triggers", default=[])

    @property
    def audience_triggers(self) -> list[str]:
        return self.get("audience_triggers", default=[])

    @property
    def architecture_leaks(self) -> list[str]:
        return self.get("architecture_leaks", default=[])

    @property
    def generic_statements(self) -> list[str]:
        return self.get("generic_statements", default=[])

    @property
    def common_words(self) -> list[str]:
        return self.get("common_words", default=[])

    @property
    def known_names(self) -> list[str]:
        return self.get("known_names", default=[])

    @property
    def engagement_bank(self) -> list[str]:
        return self.get("engagement_bank", default=[])

    @property
    def archetypes(self) -> dict:
        return self.get("strategy", "archetypes", default={})

    @property
    def verticals(self) -> dict:
        return self.get("strategy", "verticals", default={})

    @property
    def funnel_stages(self) -> dict:
        return self.get("strategy", "funnel_stages", default={})

    @property
    def icp_layers(self) -> dict:
        return self.get("strategy", "icp_layers", default={})

    @property
    def strategy_pages(self) -> list[str]:
        return self.get("strategy", "pages", default=[
            "icp-offer", "funnel-and-matrix", "voice-and-gates",
            "session-as-content", "voice-corpus",
        ])

    @property
    def template_weights(self) -> dict:
        return self.get("template_selector", "weights", default={})

    @property
    def template_top_n(self) -> dict:
        return self.get("template_selector", "top_n", default={})

    @property
    def category_priors(self) -> dict:
        return self.get("template_selector", "category_priors", default={})

    @property
    def compiler_meaning_axes(self) -> list[str]:
        return self.get("compiler", "meaning_axes", default=[
            "systemic", "behavioral", "philosophical", "contrarian", "leverage", "human",
        ])

    @property
    def creds_required(self) -> dict:
        return self.get("creds_required", default={})

    @property
    def cadence(self) -> dict:
        return self.get("cadence", default={})

    @property
    def buffer_config(self) -> dict:
        return self.get("buffer", default={})

    @property
    def primary_offer(self) -> str:
        return self.get("strategy", "primary_offer", default="spiel-engine-dfy")

    @property
    def icp_profile(self) -> str:
        return self.get("strategy", "icp_profile", default="technical-founder")


config = Config()
