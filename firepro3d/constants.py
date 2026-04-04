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

# ── Default ceiling offset (mm below ceiling level) ──────────────────────────
DEFAULT_CEILING_OFFSET_MM = -50.8      # −2 inches (sprinkler deflector below ceiling)

# ── Hydraulic velocity thresholds (ft/s) ──────────────────────────────────────
VELOCITY_HIGH_FPS  = 20.0   # Red — exceeds NFPA limits
VELOCITY_WARN_FPS  = 12.0   # Orange — approaching limit
# Colours for velocity display
VELOCITY_COLOR_HIGH   = (220, 0, 0)      # red
VELOCITY_COLOR_WARN   = (220, 140, 0)    # orange
VELOCITY_COLOR_OK     = (0, 200, 80)     # green

# ── NFPA 13 coverage limits (sq ft per sprinkler) ────────────────────────────
HAZARD_CLASSES = [
    "Light Hazard",
    "Ordinary Hazard Group 1",
    "Ordinary Hazard Group 2",
    "Extra Hazard Group 1",
    "Extra Hazard Group 2",
    "Miscellaneous Storage",
    "High Piled Storage",
]

NFPA_MAX_COVERAGE_SQFT: dict[str, float] = {
    "Light Hazard":             225.0,
    "Ordinary Hazard Group 1":  130.0,
    "Ordinary Hazard Group 2":  130.0,
    "Extra Hazard Group 1":     100.0,
    "Extra Hazard Group 2":     100.0,
    "Miscellaneous Storage":    100.0,
    "High Piled Storage":       100.0,
}

# ── Pipe colour map ──────────────────────────────────────────────────────────
PIPE_COLORS: dict[str, str] = {
    "Red":   "#e62828",
    "Blue":  "#3366e6",
    "Black": "#1a1a1a",
    "White": "#f2f2f2",
    "Grey":  "#8c8c8c",
}
