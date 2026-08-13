"""
Secret/settings loader for AegisVision.

Owns only sensitive values (API keys). Tunable trading parameters (thresholds,
model name, provider choice, prompt text) remain GUI-editable via config_manager.py's
JSON file - this file is deliberately narrow in scope.
"""

import os
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

# gui_server/ so app_paths resolves (see its docstring re: frozen __file__ paths)
_GUI_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _GUI_SERVER_ROOT not in sys.path:
    sys.path.insert(0, _GUI_SERVER_ROOT)
from app_paths import get_app_root

# Dev mode: .env lives at the repo root (one level above gui_server/), matching
# where it's actually checked in for this project. Frozen: there's no "repo"
# anymore, so .env sits next to the .exe like everything else persistent.
if getattr(sys, "frozen", False):
    _ENV_DIR = get_app_root()
else:
    _ENV_DIR = os.path.dirname(get_app_root())
_ENV_FILE = os.path.join(_ENV_DIR, ".env")


class Settings(BaseSettings):
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Optional -- the Strategies tab's Supabase sync (storage/supabase_sync.py) is a
    # no-op when these are unset, so the app works fully offline until configured.
    supabase_url: str = ""
    supabase_key: str = ""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


_settings: Settings | None = None


def get_settings() -> Settings:
    """Load settings once (from .env / process environment) and cache them."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
