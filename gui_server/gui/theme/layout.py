"""
AegisVision "grounded" layout primitives.

The window background is the ground -- content sits directly on it, and
sections are separated by a heading + thin divider line rather than by
nesting another bordered/rounded frame inside another. A bordered card()
is reserved for genuinely repeating, self-contained units (a template
image slot, a signal chip, a stat tile) -- never used just to group a
handful of form fields.

section() is the workhorse: it packs itself into `parent` (most usages are
a vertical stack inside one column), and returns a transparent content
frame for the caller to fill. divider() and card() are NOT auto-placed --
callers pack()/grid() them explicitly, since their placement context varies
(a vertical divider between two grid columns, a card in a repeating grid).
"""

import customtkinter as ctk

from . import tokens as colors
from . import fonts
from . import spacing


def section(parent, title: str, *, accent: bool = False,
            accent_divider: bool = False,
            pady=(0, spacing.LG)) -> ctk.CTkFrame:
    """Heading + hairline divider, packed into `parent`. Returns a fresh
    transparent content frame (packed fill='both', expand=True) for the
    caller to grid()/pack() real widgets into.

    accent=True colors the heading text gold instead of the primary text
    color -- use sparingly, for one visual anchor per page at most.
    accent_divider=True colors the hairline gold instead of the muted
    divider tone, for the same sparing "anchor" purpose.
    """
    outer = ctk.CTkFrame(parent, fg_color="transparent")
    outer.pack(fill="x", pady=pady)

    label_color = colors.ACCENT if accent else colors.TEXT_PRIMARY
    heading_label = ctk.CTkLabel(
        outer, text=title, font=fonts.section(),
        text_color=label_color, anchor="w",
    )
    heading_label.pack(fill="x", pady=(0, spacing.XS))

    line_color = colors.ACCENT if accent_divider else colors.DIVIDER
    line = ctk.CTkFrame(
        outer, height=spacing.DIVIDER_THICKNESS,
        fg_color=line_color, corner_radius=0,
    )
    line.pack(fill="x", pady=(0, spacing.SM))

    content = ctk.CTkFrame(outer, fg_color="transparent")
    content.pack(fill="both", expand=True)
    return content


def divider(parent, *, vertical: bool = False,
            accent: bool = False) -> ctk.CTkFrame:
    """Standalone hairline separator. Not auto-placed -- caller packs/grids
    it (e.g. a vertical divider between two side-by-side columns)."""
    color = colors.ACCENT if accent else colors.DIVIDER
    if vertical:
        return ctk.CTkFrame(
            parent, width=spacing.DIVIDER_THICKNESS,
            fg_color=color, corner_radius=0,
        )
    return ctk.CTkFrame(
        parent, height=spacing.DIVIDER_THICKNESS,
        fg_color=color, corner_radius=0,
    )


def card(parent, *, padding: int = spacing.MD) -> ctk.CTkFrame:
    """The only sanctioned bordered-container constructor left in the app.
    Reserved for genuinely repeating/self-contained units (template slots,
    signal chips, stat tiles) -- not for grouping ordinary form fields,
    which should use section() instead.

    `padding` is documented, not applied automatically: children should be
    packed/gridded with that much padding from this frame's edge.
    """
    return ctk.CTkFrame(
        parent,
        fg_color=colors.SURFACE,
        border_width=1,
        border_color=colors.BORDER,
        corner_radius=spacing.RADIUS_CARD,
    )
