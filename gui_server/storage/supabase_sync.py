"""
Background Supabase sync for the Strategies tab.

The live trading pipeline NEVER imports this module -- it only ever reads
local disk (see active_strategy_store.py). This is purely a GUI-side
durability/multi-machine backstop: every local save pushes here in the
background (best-effort, never blocking), and switching the active strategy
pulls from here before caching locally.

v1 (this module, right now): a no-op stub. `SupabaseSyncClient` is always
constructed, but every method silently returns immediately unless
settings.supabase_url/supabase_key are both set AND the `supabase` package
is installed -- so the Strategies tab works fully offline today with zero
config, and turning on real sync later (once a Supabase project exists) is
just filling in the bodies of the methods below, not touching any call site
in strategies_tab.py.
"""

import logging
import queue
import threading
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class SupabaseSyncClient:
    def __init__(self):
        self.enabled = False
        self._client = None
        self._queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None

        try:
            from settings import get_settings
            settings = get_settings()
        except Exception as e:
            logger.debug(f"Supabase sync disabled: could not load settings ({e})")
            return

        if not settings.supabase_url or not settings.supabase_key:
            logger.info("Supabase sync disabled: supabase_url/supabase_key not configured (running local-only)")
            return

        try:
            from supabase import create_client
        except ImportError:
            logger.info("Supabase sync disabled: 'supabase' package not installed (running local-only)")
            return

        try:
            self._client = create_client(settings.supabase_url, settings.supabase_key)
            self.enabled = True
            self._worker = threading.Thread(target=self._run_queue, daemon=True)
            self._worker.start()
            logger.info("Supabase sync enabled")
        except Exception as e:
            logger.warning(f"Supabase sync disabled: failed to connect ({e})")

    def _run_queue(self):
        while True:
            job = self._queue.get()
            try:
                job()
            except Exception as e:
                logger.warning(f"Supabase sync job failed (will not retry): {e}")

    def _enqueue(self, job: Callable[[], None]) -> None:
        if not self.enabled:
            return
        self._queue.put(job)

    # -- push methods (fire-and-forget, background) -----------------------
    # TODO(step 6): implement against the schema in the approved plan
    # (strategies / app_state / template_slots / template_slot_images /
    # prompts tables + the strategy-assets Storage bucket) once a Supabase
    # project exists. Each currently just no-ops via _enqueue's enabled check.

    def push_strategy_create(self, strategy_id: str, name: str, category: str) -> None:
        self._enqueue(lambda: None)

    def push_template_slot(self, strategy_id: str, slot: str, caption: str) -> None:
        self._enqueue(lambda: None)

    def push_template_source(
        self, strategy_id: str, slot: str, position: int,
        source_image_path: str, crop_box: tuple, source_dims: tuple,
    ) -> None:
        self._enqueue(lambda: None)

    def push_template_composite(self, strategy_id: str, slot: str, composite_image_path: str) -> None:
        self._enqueue(lambda: None)

    def push_prompt_version(self, strategy_id: str, version: int, text: str, notes: str) -> None:
        self._enqueue(lambda: None)

    def push_active_strategy(self, strategy_id: str) -> None:
        self._enqueue(lambda: None)

    # -- pull methods (synchronous, caller waits) --------------------------

    def pull_strategy(self, strategy_id: str) -> bool:
        """Downloads everything for one strategy into the local cache.
        Returns False (not yet implemented / not enabled) so callers know to
        fall back to whatever's already cached locally."""
        if not self.enabled:
            return False
        logger.debug("pull_strategy: Supabase sync not yet implemented (step 6)")
        return False

    def list_remote_strategies(self) -> List[dict]:
        if not self.enabled:
            return []
        return []
