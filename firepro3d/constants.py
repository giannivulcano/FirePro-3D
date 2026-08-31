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

# Opening cross-wall alignment (§7.5)
OPENING_ALIGN_CENTER = "Centered"
OPENING_ALIGN_FRONT  = "Flush-front"
OPENING_ALIGN_BACK   = "Flush-back"
OPENING_ALIGNMENTS   = [OPENING_ALIGN_CENTER, OPENING_ALIGN_FRONT, OPENING_ALIGN_BACK]
OPENING_TYPES        = ["door", "window", "blank"]
Z_CAT_PIPE       = 0.4    # Pipe
Z_CAT_NODE       = 0.5    # Node
Z_CAT_CONSTRUCTION = Z_CAT_NODE + 0.1  # 2D draw geometry (above building geometry)

# ── Default gridline geometry ────────────────────────────────────────────────
DEFAULT_GRIDLINE_SPACING_MM = 7315.2   # 288 in / 24 ft
DEFAULT_GRIDLINE_LENGTH_MM  = 21945.6  # 864 in / 72 ft

GRIDLINE_BUBBLE_OFFSET_MM = 1000.0  # absolute along-axis bubble standoff (mm)

# ── Underlay rendering ───────────────────────────────────────────────────────
# Cosmetic pen width (device pixels) for batched DXF/PDF underlay geometry, so
# lines stay a constant thickness regardless of zoom or import scale.
# HARD PERF CONSTRAINT: must be <= 1.0. Qt's fast cosmetic stroker only
# handles widths <= 1.0px; wider cosmetic pens fall into the generic stroke
# pipeline — measured ~20x slower over a dense underlay (22ms vs 1ms for the
# same 94k-point drawing; the old 1.5 default made live repaints 500ms+).
UNDERLAY_LINE_WIDTH_PX = 1.0
# Screen hints at or below this round DOWN to 1.0 to stay on the fast path;
# heavier user-chosen weights keep their true hint width (and its cost).
UNDERLAY_FAST_PATH_SNAP_PX = 1.25

# Screen-hint conversion for named underlay line weights (§16.3):
# px = width_mm * UNDERLAY_MM_TO_PX_HINT. 6.0 makes Medium (0.25mm) ≈ 1.5px
# so the no-override look is pixel-identical to UNDERLAY_LINE_WIDTH_PX.
UNDERLAY_MM_TO_PX_HINT = 6.0

# ── Underlay import geometry (PDF bézier flattening) ─────────────────────────
# DEFAULT max chord deviation (PDF points; 1 pt = 1/72") when flattening cubic
# béziers from PDF vector imports — overridable live via Preferences > Import &
# Conversion (QSettings ``import/pdf_bezier_flatten_tol``, read by
# ``pdf_import_worker.current_pdf_flatten_tol``). Task-73 outcome: a visual gate
# on the Sleeman reference showed coarser values (2.0/1.5) facet noticeably when
# zoomed past plot scale, so the DEFAULT stays at the original fine 0.5 (no
# fidelity regression) and coarsening — for a smaller/faster underlay — is
# opt-in per user. The value is part of the PDF cache key, so a change
# re-extracts. Spinbox range 0.25–4.0.
PDF_BEZIER_FLATTEN_TOL = 0.5

# ── Underlay gesture freeze (freeze-blit, underlay-workflow spec §18) ────────
# Gesture is considered ended after this idle gap; the vector restore fires
# then. Must exceed a natural slow wheel-tick cadence (~0.3-1s between ticks
# measured live) or every tick pays a fresh capture + settle repaint (the
# thrash that made heavy underlays feel >1s per tick).
UNDERLAY_FREEZE_SETTLE_MS = 450
# Capture pad per side, as a fraction of the viewport (pan headroom during the
# gesture; panning past the pad shows blank margin until settle — accepted).
# 0.25 = 2.25x viewport pixels per capture (was 0.5 = 4x; capture cost scales
# with covered pixels and is paid synchronously at gesture start).
UNDERLAY_FREEZE_PAD_FRACTION = 0.25
# Per-axis pixel clamp on the capture pixmap (memory bound at any DPR/monitor;
# the pixmap-item transform corrects for any clamp, output just gets softer).
UNDERLAY_FREEZE_MAX_PX = 8192

# ── Default ceiling offset (mm below ceiling level) ──────────────────────────
DEFAULT_CEILING_OFFSET_MM = -50.8      # −2 inches (sprinkler deflector below ceiling)

# ── Floor slab elevation model (docs/specs/wall-room-floor-system.md §11) ────
MIN_FLOOR_THICKNESS_MM = 1.0        # anti-degeneracy floor, not architectural minimum
FLOOR_TOP_MODES = ("level", "absolute")
FLOOR_BOTTOM_MODES = ("level", "absolute", "thickness")

# ── Design-area creation ─────────────────────────────────────────────────────
# (DESIGN_AREA_PICK_PX retired 2026-08-25: design-area pick now routes through
#  SnapEngine.find at the shared SNAP_TOLERANCE_PX aperture.)

# ── ALIGN tracking paths (align_engine.py) ───────────────────────────────────
ALIGN_PATH_TOL_PX = 20.0       # screen-px cursor→path soft-snap aperture; wider than the
                               # 15px real-snap aperture but its OWN band (align-placement D7)

# ── ALIGN acquire machine (align_controller.py) ──────────────────────────────
ALIGN_DWELL_MS = 400           # hover-dwell to acquire a snap point (ms)
ALIGN_MAX_POINTS = 5           # acquired-point cap (evict oldest)
# Per-direction ray-kind gating defaults (SnappingPane toggles; controller flags).
ALIGN_DIR_HV_DEFAULT = True         # emit horizontal/vertical rays from point-acquires
ALIGN_DIR_EXTENSION_DEFAULT = True  # emit collinear extension rays from directional points
ALIGN_DIR_PARALLEL_DEFAULT = False  # direction-tracking parallel OFF by default:
#   the flaky direction-track parallel is superseded by the planned perpendicular
#   OFFSET-tracking feature (TODO P2); plumbing kept, surfaced only when re-enabled.
ALIGN_DIR_PERPENDICULAR_DEFAULT = True  # emit perpendicular rays (dir rotated 90°) from directional points

# ── ALIGN tracking-path overlay ───────────────────────────────────────────────
ALIGN_GUIDE_COLOR = "#00c8ff"          # cyan — alignment-guide line + glyph (theming.md)
ALIGN_GUIDE_DASH = [4.0, 4.0]          # cosmetic dash pattern (px)
ALIGN_GLYPH_PX = 7.0                   # reference-point glyph size (screen px)
ALIGN_ACQUIRE_COLOR = "#00ff88"        # green '+' acquired-point marker (distinct from snap glyphs)
DESIGN_AREA_HL_RADIUS_PX = 14  # highlight-ring radius for selected design sprinklers (px)

# ── Design-criteria badge (model-space mm; tuned at 2026-07-14 mockup gate) ──
DA_BADGE_WIDTH_MM   = 10000.0  # table width
DA_BADGE_TEXT_MM    = 200.0    # cell text cap height
DA_BADGE_TITLE_MM   = 300.0    # title row cap height
DA_BADGE_PAD_MM     = 120.0    # cell padding
DA_BADGE_CORNER_MM  = 300.0    # fillet radius of the outer border
DA_BADGE_LINE_MM    = 30.0     # border line thickness
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
    "Low-Piled Storage",
    "Miscellaneous Storage",
    "High Piled Storage",
]

NFPA_MAX_COVERAGE_SQFT: dict[str, float] = {
    "Light Hazard":             225.0,
    "Ordinary Hazard Group 1":  130.0,
    "Ordinary Hazard Group 2":  130.0,
    "Extra Hazard Group 1":     100.0,
    "Extra Hazard Group 2":     100.0,
    "Low-Piled Storage":        130.0,   # OH-type criteria (NFPA 13 low-piled)
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
GRIDLINE_BUBBLE_LABEL_EM_FRAC = 0.9  # bubble label em height = 0.9 × head radius (historic screen ratio)
MIN_TEXT_WRAP_WIDTH_MM = 5.0     # smallest draggable wrap width

# ── App-wide selection / grip style (owned by docs/architecture/theming.md) ──
# Used by SheetViewport and TextAnnotationItem to draw consistent selected-item
# dashed boundaries and 8-handle resize grips on all paper-space items.
SELECTION_OUTLINE_COLOR = "#0055ff"         # selected-item dashed boundary + grip outline
SELECTION_OUTLINE_WIDTH_MM = 0.8           # dashed boundary pen width (paper mm)
SELECTION_GRIP_OUTLINE_WIDTH_MM = 0.3      # grip square outline pen width (paper mm)
SELECTION_GRIP_SIZE_MM = 4.0               # grip square side length (paper mm)

# ── Selection-manipulator handle/knob style (docs/specs/selection-manipulator.md) ──
# Mockup-approved 2026-08-30 (style A): dark-filled square handles with a
# theme-``selection`` border and a hollow rotate knob. The FILL is a function of
# the theme — near-black on a dark canvas, white on a light canvas — so handles
# read against the canvas either way while the green border does the defining.
MANIP_HANDLE_SIZE_PX = 9.0                  # resize-handle square side (device px)
MANIP_HANDLE_BORDER_PX = 1.2               # handle + knob outline width (device px)
MANIP_KNOB_RADIUS_PX = 5.5                 # rotate-knob radius (device px)
MANIP_STEM_LEN_PX = 28.0                   # top-mid → rotate-knob stem length (px)
MANIP_HANDLE_FILL_DARK = "#101613"          # fill on a dark canvas (prototype value)
MANIP_HANDLE_FILL_LIGHT = "#ffffff"         # fill on a light canvas

TEXT_BOX_MARGIN_MM = 1.0  # inner padding between sheet-text content and its box edge

# Word-standard font size ladder (pt) — shared by the ribbon Font group's
# size dropdown and its grow/shrink stepping (units-and-formatting.md).
FONT_SIZE_LADDER_PT = (8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)

# ── Title block template system (docs/specs/titleblock-template-system.md) ──
TB_MARGIN_EDGE_DEFAULT_MM = 10.0    # paper edge → drawing area
TB_MARGIN_STRIP_DEFAULT_MM = 5.0    # drawing area → info strip
TB_STRIP_DEFAULT_MM = 90.0          # default info-strip width
TB_DEFAULT_FILLET_MM = 10.0         # default frame fillet radius
TB_STRIP_MIN_MM = 20.0              # validation floor: strip width
TB_AREA_MIN_MM = 100.0              # validation floor: drawing area per dimension
TB_LABEL_CAP_FRAC = 0.45            # label cap height as fraction of value cap height
TB_CELL_PAD_MM = 1.5                # inner cell padding (solver + T7 renderer share this)
TB_LABEL_ROW_MM = 3.0               # label row height when a label is present
TB_REV_ROW_MM = 5.0                 # height per revision table data row (header + each row)
TB_REV_CAP_MM = 2.0                 # revision row text cap height (header + data rows)
TB_LABEL_CAP_MIN_MM = 1.2           # floor for computed label cap height
TB_REV_PEN_MM = 0.2                 # revision table divider pen width (mm)
TB_PREVIEW_MIN_MM = 20.0            # Fields-tab single-field preview: nominal slot min-height for unplaced fields
TB_INSERT_BAND_PX = 6               # Arrangements canvas: hit-band (px) around row boundaries for insert zones
TB_POOL_CARD_W = 150                # Arrangements tab: pool card list width (px); consumed by Task 10
