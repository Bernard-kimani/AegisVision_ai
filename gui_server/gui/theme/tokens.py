"""
AegisVision color tokens.

Every color is a (light_hex, dark_hex) tuple, matching the format CustomTkinter
widgets accept directly for fg_color / text_color / border_color / hover_color.
This is the single source of truth for color in the app -- tab files should
never hardcode a color string (e.g. fg_color="green"); named Tk color strings
do not react to ctk.set_appearance_mode(), tuples do.

Anchors given by design: antique gold #c6a75e, deep forest #0f1a14,
premium white #f3ede6. Everything else here is derived from those three to
fill out a full UI token set. Adjust freely -- this is the only place that
needs to change.
"""

# Ground / surfaces -----------------------------------------------------
# Dark mode uses a neutral charcoal (not the deep-forest green originally
# tried) -- the gold accent still carries the "forest/gold" identity, the
# ground itself stays a plain near-black so the gold and signal colors pop.
GROUND = ("#f3ede6", "#121212")          # window background -- "the ground"
SURFACE = ("#e9e1d4", "#1c1c1c")         # the only bg level a real card() uses
SURFACE_ALT = ("#e2d8c8", "#262626")     # hover / alt-row background inside a surface

# Borders / dividers ------------------------------------------------------
BORDER = ("#d8cdbb", "#333333")          # 1px input / card borders
DIVIDER = ("#000000", "#ffffff")         # section-separator hairline -- deliberately
                                          # high-contrast (black on light, white on dark)

# Text ---------------------------------------------------------------------
TEXT_PRIMARY = ("#0f1a14", "#f3ede6")
TEXT_SECONDARY = ("#55605a", "#b9b3a8")
TEXT_DISABLED = ("#9a978d", "#6b6b6b")

# Accent (gold) --------------------------------------------------------------
ACCENT = ("#c6a75e", "#c6a75e")
ACCENT_HOVER = ("#ad8f4e", "#d9bd7a")
ACCENT_PRESSED = ("#94793f", "#c6a75e")
TEXT_ON_ACCENT = ("#0f1a14", "#121212")  # gold is a bright midtone in both modes

# Semantic -------------------------------------------------------------------
SUCCESS = ("#2f8f56", "#59b37d")
ERROR = ("#c14a3a", "#e2584a")
WARNING = ("#b9812a", "#e0a53f")

# Trading signal chips (reuse semantic hues so the palette stays tight) ------
SIGNAL_BUY = SUCCESS
SIGNAL_SELL = ERROR
SIGNAL_WAIT = ("#8a8478", "#8a8478")
