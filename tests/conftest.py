"""tests/conftest.py — Path setup so tests can find the vault."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
