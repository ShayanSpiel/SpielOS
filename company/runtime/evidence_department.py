"""Backward-compatible alias for the declarative Department interpreter."""

from ..runtime.interpreter import InterpretedDepartment, compare

# Historical name used by growth departments and tests.
EvidenceDepartment = InterpretedDepartment

__all__ = ["EvidenceDepartment", "InterpretedDepartment", "compare"]
