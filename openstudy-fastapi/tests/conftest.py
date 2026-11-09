"""Pytest bootstrap: make the backend package importable from the repo root."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# These two files are script-style integration checks (custom Checker / direct
# asyncio.run), not pytest test modules. They remain runnable via
# `python tests/<file>.py`; exclude them from pytest collection so the default
# `pytest` command stays deterministic.
collect_ignore = [
    "test_agent_rag_tools.py",
    "test_context_memory.py",
]
