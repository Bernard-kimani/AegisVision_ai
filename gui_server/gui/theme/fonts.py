"""
AegisVision font scale.

Functions, not constants -- CTkFont is a stateful Tk resource and the codebase
convention (and CTk's own) is a fresh instance per widget. Centralizing the
size/weight choices here fixes the previously-scattered ad hoc CTkFont(...)
calls (e.g. section headers sized 14/15/16 inconsistently across tabs, and
three separate "Consolas" monospace call sites disagreeing on size 10 vs 11).
"""

import platform
import customtkinter as ctk

_MONO_FAMILY_BY_PLATFORM = {
    "Windows": "Consolas",
    "Darwin": "Menlo",
}
_MONO_FALLBACK = "DejaVu Sans Mono"


def heading() -> ctk.CTkFont:
    """Page-level title, e.g. the app header."""
    return ctk.CTkFont(size=20, weight="bold")


def section() -> ctk.CTkFont:
    """Section heading used by theme.layout.section()."""
    return ctk.CTkFont(size=15, weight="bold")


def body() -> ctk.CTkFont:
    """Default label / entry text. Matches the theme JSON's platform default
    size -- this wrapper exists so call sites are consistent and explicit."""
    return ctk.CTkFont(size=13)


def caption() -> ctk.CTkFont:
    """Hint / secondary / status text."""
    return ctk.CTkFont(size=11)


def mono(size: int = 11) -> ctk.CTkFont:
    """Monospace font for log/signal views, with a cross-platform family
    fallback (Tk does not auto-fallback a tuple of family names the way CSS
    does, so the family is resolved explicitly per OS)."""
    family = _MONO_FAMILY_BY_PLATFORM.get(platform.system(), _MONO_FALLBACK)
    return ctk.CTkFont(family=family, size=size)
