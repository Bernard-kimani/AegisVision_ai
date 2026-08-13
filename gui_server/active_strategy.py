"""
Tracks which "strategy" (see gui/strategies_tab.py) is currently active for
the live trading pipeline -- a strategy bundles its own 3 template slots
(bullish_ideal/bearish_ideal/fail_trap) + Agent 2 prompt under
strategies_store/{strategy_id}/.

This is a tiny, app-root-tier module (alongside app_paths.py) rather than
living inside gui/ or storage/, because both the GUI process (which writes
it, on strategy creation/switch) and the Flask server process (which reads
it, via storage/active_strategy_store.py) need it, and neither should import
from the other's package.

Fails safe: a missing/unparseable pointer file means "no strategy active",
never an exception -- the live pipeline falls back to the pre-Strategies-tab
global template/prompt paths in that case (see active_strategy_store.py).
"""

import json
import logging
import os
from typing import Optional, Tuple

from app_paths import get_app_root

logger = logging.getLogger(__name__)

STRATEGIES_STORE_DIR = os.path.join(get_app_root(), "strategies_store")
_ACTIVE_STRATEGY_FILE = os.path.join(STRATEGIES_STORE_DIR, "active_strategy.json")


def get_active_strategy_id() -> Optional[str]:
    """The currently active strategy's id, or None if no strategy is active
    (fresh install, or the user hasn't created/selected one yet)."""
    if not os.path.exists(_ACTIVE_STRATEGY_FILE):
        return None
    try:
        with open(_ACTIVE_STRATEGY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("strategy_id") or None
    except Exception as e:
        logger.warning(f"Could not read active_strategy.json, treating as no active strategy: {e}")
        return None


def set_active_strategy_id(strategy_id: str, strategy_name: str) -> None:
    """GUI-only: called on strategy creation and on dropdown switch."""
    os.makedirs(STRATEGIES_STORE_DIR, exist_ok=True)
    with open(_ACTIVE_STRATEGY_FILE, "w", encoding="utf-8") as f:
        json.dump({"strategy_id": strategy_id, "strategy_name": strategy_name}, f, indent=2)


def get_strategy_dir(strategy_id: str) -> str:
    return os.path.join(STRATEGIES_STORE_DIR, strategy_id)


def get_active_strategy_dirs() -> Optional[Tuple[str, str]]:
    """(templates_dir, prompts_dir) for the currently active strategy, or
    None if no strategy is active."""
    strategy_id = get_active_strategy_id()
    if strategy_id is None:
        return None
    base = get_strategy_dir(strategy_id)
    return os.path.join(base, "templates"), os.path.join(base, "prompts")
