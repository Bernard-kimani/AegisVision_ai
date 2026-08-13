"""
AegisVision spacing / sizing scale.

Named constants so tab files stop picking ad hoc padx/pady numbers per call
site. Values are pixels, used directly as CTk pack()/grid() padding kwargs.
"""

XS = 4
SM = 8
MD = 12
LG = 16
XL = 24

# Corner radius -- inputs/buttons/tabs are sharp-edged (0) by default via the
# theme JSON; card() is the one deliberately-soft exception. RADIUS_PILL is
# for the handful of explicitly pill-shaped buttons (server control actions).
RADIUS_CARD = 10
RADIUS_INPUT = 0
RADIUS_BUTTON = 0
RADIUS_PILL = 1000  # CTk clamps this to a true pill/capsule regardless of button size

# Divider hairline thickness, in pixels
DIVIDER_THICKNESS = 2
