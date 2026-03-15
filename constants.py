"""
constants.py
=============
Shared named constants for FirePro 3D.

Centralises magic strings and numbers that were previously
hard-coded across multiple modules.
"""

# ── Default level / layer names ───────────────────────────────────────────────
DEFAULT_LEVEL = "Level 1"
DEFAULT_USER_LAYER = "Default"

# ── Z-ordering ───────────────────────────────────────────────────────────────
Z_BELOW_GEOMETRY = -100  # Z-value for underlays, imports, PDF pages
Z_ROOF = -75             # Z-value for roof items (above underlays, below walls)

# ── Default gridline geometry (in inches, converted to mm at 25.4 mm/in) ─────
DEFAULT_GRIDLINE_SPACING_IN = 7315.2   # 288 in / 24 ft
DEFAULT_GRIDLINE_LENGTH_IN  = 21945.6  # 864 in / 72 ft
