"""
Decorator TemplateImageStore/PromptStore implementations that resolve to
whichever strategy is currently active (see active_strategy.py), falling
back to the pre-Strategies-tab global paths when no strategy is active --
this makes the Strategies feature 100% backward-compatible for existing
installs with no strategy created yet, no migration script needed.

Resolution happens fresh on every call (not cached at construction time), so
switching strategies from the GUI dropdown takes effect on the very next
/analyze call with no server restart. trading_server.py's create_app() is
the only caller that matters here -- swap its two direct LocalFile*Store(...)
constructions for these, and nothing else in the live pipeline changes.
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

_APP_ROOT = os.path.dirname(os.path.abspath(__file__))
_GUI_SERVER_ROOT = os.path.dirname(_APP_ROOT)
if _GUI_SERVER_ROOT not in sys.path:
    sys.path.insert(0, _GUI_SERVER_ROOT)

from app_paths import get_app_root
from active_strategy import get_active_strategy_dirs
from storage.template_image_store import (
    TemplateImageStore, TemplateRecord, TemplateSourceImage, LocalFileTemplateImageStore,
)
from storage.prompt_store import PromptStore, PromptVersion, LocalFilePromptStore

_LEGACY_TEMPLATES_DIR = os.path.join(get_app_root(), "templates_store")
_LEGACY_PROMPTS_DIR = os.path.join(get_app_root(), "storage_data", "prompts")


class ActiveStrategyTemplateStore(TemplateImageStore):
    """Delegates every call to whichever strategy is currently active, or
    the legacy global template store if none is active."""

    def _delegate(self) -> LocalFileTemplateImageStore:
        dirs = get_active_strategy_dirs()
        templates_dir = dirs[0] if dirs else _LEGACY_TEMPLATES_DIR
        return LocalFileTemplateImageStore(templates_dir)

    def save_template(self, slot: str, source_image_path: str, caption: str) -> TemplateRecord:
        return self._delegate().save_template(slot, source_image_path, caption)

    def save_template_source(
        self, slot: str, position: int, source_image_path: str,
        crop_box: Tuple[float, float, float, float], caption: Optional[str] = None,
    ) -> TemplateRecord:
        return self._delegate().save_template_source(slot, position, source_image_path, crop_box, caption)

    def get_template_sources(self, slot: str) -> List[TemplateSourceImage]:
        return self._delegate().get_template_sources(slot)

    def remove_template_source(self, slot: str, position: int) -> Optional[TemplateRecord]:
        return self._delegate().remove_template_source(slot, position)

    def get_template(self, slot: str) -> Optional[TemplateRecord]:
        return self._delegate().get_template(slot)

    def get_template_base64(self, slot: str) -> Optional[str]:
        return self._delegate().get_template_base64(slot)

    def list_templates(self) -> Dict[str, TemplateRecord]:
        return self._delegate().list_templates()

    def update_caption(self, slot: str, caption: str) -> Optional[TemplateRecord]:
        return self._delegate().update_caption(slot, caption)


class ActiveStrategyPromptStore(PromptStore):
    """Delegates every call to whichever strategy is currently active, or
    the legacy global prompt store if none is active."""

    def _delegate(self) -> LocalFilePromptStore:
        dirs = get_active_strategy_dirs()
        prompts_dir = dirs[1] if dirs else _LEGACY_PROMPTS_DIR
        return LocalFilePromptStore(prompts_dir)

    def save_prompt(self, strategy_name: str, text: str, notes: str = "") -> PromptVersion:
        return self._delegate().save_prompt(strategy_name, text, notes)

    def get_latest(self, strategy_name: str) -> Optional[PromptVersion]:
        return self._delegate().get_latest(strategy_name)

    def get_version(self, strategy_name: str, version: int) -> Optional[PromptVersion]:
        return self._delegate().get_version(strategy_name, version)

    def list_versions(self, strategy_name: str) -> List[PromptVersion]:
        return self._delegate().list_versions(strategy_name)

    def list_strategies(self) -> List[str]:
        return self._delegate().list_strategies()
