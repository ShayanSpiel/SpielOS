from .registry import connection, connections

# Delivery adapters are loaded by the Agent through its declared Connection. Keeping
# the registry import-only lets a fresh harness start with no legacy packages.
__all__ = ["connection", "connections"]
