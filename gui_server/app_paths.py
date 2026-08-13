"""
Shared "where does persistent data live" helper.

Any module computing a path from __file__ to find storage_data/, templates_store/,
or .env breaks once PyInstaller bundles the app: frozen modules resolve __file__
to PyInstaller's ephemeral temp extraction folder (_MEIPASS), which is wiped after
the process exits - so audit logs, saved prompts, and template images would
silently vanish between runs of a packaged .exe. Everything that needs a stable,
persistent root should call get_app_root() instead of deriving it from __file__.
"""

import os
import sys


def get_app_root() -> str:
    """The directory the app's persistent data lives next to: the .exe's own
    directory when frozen, or gui_server/ (the repo's app root) in dev mode."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
