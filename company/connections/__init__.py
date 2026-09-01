from .registry import connection, connections
from .core import Connection

# Delivery adapters are loaded by the Agent through its declared Connection. Keeping
# the registry import-only lets a fresh harness start with no legacy packages.
__all__ = ["Connection", "connection", "connections"]
