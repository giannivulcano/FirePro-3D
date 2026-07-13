"""
constants.py
=============
Shared named constants for FirePro 3D.

Centralises magic strings and numbers that were previously
hard-coded across multiple modules.
"""

# ── Default level / annotation group ──────────────────────────────────────────
DEFAULT_LEVEL = "Level 1"
# Annotation grouping label (the per-entity "layer" system was removed; this is
# now only a category for CAD annotations — see annotations.py).
DEFAULT_ANNOTATION_GROUP = "Default"

# ── Z-ordering ───────────────────────────────────────────────────────────────
# See docs/specs/view-relationships.md §7.3 for the spec source of truth.
#
# Static z-values (items outside or before elevation-based z-ordering):
Z_CROP_BOX       = -200   # SharedCropBox (below all geometry)
Z_BELOW_GEOMETRY = -100   # origin cross, items below all geometry
Z_UNDERLAY       = -79    # underlays/imports (initial; overridden at runtime)
Z_ROOF           = -75    # roof items (initial; overridden at runtime)
Z_CONSTRUCTION   = 1      # construction geometry (lines, rects, circles, arcs)
Z_DESIGN_AREA    = 2      # design area boundary
Z_PIPE           = 5      # pipes (initial; overridden at runtime)
Z_NODE           = 10     # nodes (initial; overridden at runtime)
Z_DETAIL_MARKER  = 45     # detail view markers
Z_WATER_SUPPLY   = 50     # water supply symbol
Z_SPRINKLER      = 100    # sprinkler symbols
Z_OVERLAY        = 200    # previews, view markers, room labels, badges
Z_GRIDLINE_BUBBLE = 500   # gridline bubbles, elevation bubbles
Z_DESIGN_AREA_CONFIRMED = 600  # confirmed design-area outline (above geometry + gridlines)
Z_PREVIEW        = 999    # ephemeral array/tool preview overlay
#
# Elevation-based Z-ordering (level_manager.apply_to_scene):
# z = elevation_mm * Z_ELEV_SCALE + category offset
Z_ELEV_SCALE     = 1.0 / 100.0  # mm → Z units (keeps values manageable)
Z_CAT_FLOOR      = 0.0    # FloorSlab
Z_CAT_UNDERLAY   = 0.05   # DXF/PDF imports
Z_CAT_ROOF       = 0.1    # RoofItem
Z_CAT_ROOM       = 0.2    # Room
Z_CAT_WALL       = 0.3    # WallSegment
Z_CAT_OPENING    = 0.35   # DoorOpening, WindowOpening
Z_CAT_PIPE       = 0.4    # Pipe
Z_CAT_NODE       = 0.5    # Node

# ── Default gridline geometry (in inches, converted to mm at 25.4 mm/in) ─────
DEFAULT_GRIDLINE_SPACING_IN = 7315.2   # 288 in / 24 ft
DEFAULT_GRIDLINE_LENGTH_IN  = 21945.6  # 864 in / 72 ft

# ── Underlay rendering ───────────────────────────────────────────────────────
# Cosmetic pen width (device pixels) for batched DXF/PDF underlay geometry, so
# lines stay a constant thickness regardless of zoom or import scale. Matches
# the gridline on-screen width (GRID_WIDTH in gridline.py).
UNDERLAY_LINE_WIDTH_PX = 1.5

# ── Default ceiling offset (mm below ceiling level) ──────────────────────────
DEFAULT_CEILING_OFFSET_MM = -50.8      # −2 inches (sprinkler deflector below ceiling)

# ── Design-area creation ─────────────────────────────────────────────────────
DESIGN_AREA_PICK_PX = 16       # sprinkler pick radius in design_area mode (screen px, zoom-aware)
DESIGN_AREA_HL_RADIUS_PX = 14  # highlight-ring radius for selected design sprinklers (px)
SQFT_TO_MM2 = 92_903.04        # 1 ft² in mm²

# ── Pipe geometry check tolerance ────────────────────────────────────────────
Z_COPLANAR_TOL = 1.0              # mm — pipes within this Z-difference are coplanar

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
# ── Wall join tolerances (mm) ────────────────────────────────────────────────
MITER_TOL = 1.0               # max gap to treat endpoints as coincident for miter
MAX_MITER_FACTOR = 4.0        # miter extension cap: half_thickness * this factor
AUTO_JOIN_TOLERANCE = 20.0    # snap radius for endpoint-to-endpoint wall joins
TEE_TOLERANCE = 40.0          # snap radius for tee (mid-wall) joins

# ── Pipe colour map ──────────────────────────────────────────────────────────
PIPE_COLORS: dict[str, str] = {
    "Red":   "#e62828",
    "Blue":  "#3366e6",
    "Black": "#1a1a1a",
    "White": "#f2f2f2",
    "Grey":  "#8c8c8c",
}

# ── Paper-space sheet text annotations ──────────────────────────────────────
DEFAULT_TEXT_HEIGHT_MM = 4.7625  # 3/16" — default sheet-note CAP height (paper mm)
TEXT_METRIC_REF_PX = 1000        # device-independent reference px size for QFont metrics
MIN_TEXT_WRAP_WIDTH_MM = 5.0     # smallest draggable wrap width
