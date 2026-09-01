"""Shared SQLite plumbing; domain repositories own all queries."""

from .database import Database
from .migration import migrate_legacy_goals

__all__ = ["Database", "migrate_legacy_goals"]
