"""Shared SQLite plumbing; domain repositories own all queries."""

from .database import Database

__all__ = ["Database"]
