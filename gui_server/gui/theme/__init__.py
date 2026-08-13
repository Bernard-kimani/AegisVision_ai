"""
AegisVision theme package.

Usage in tab files:

    from gui.theme import colors, fonts, spacing
    from gui.theme.layout import section, divider, card

`colors` is the tokens module aliased for readability at call sites
(colors.ACCENT, colors.SUCCESS, ...).
"""

from . import tokens as colors
from . import fonts
from . import spacing
from . import layout
from . import icons
from .layout import section, divider, card

__all__ = ["colors", "fonts", "spacing", "layout", "icons", "section", "divider", "card"]
