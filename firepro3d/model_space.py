import sys, json, math, shutil, logging, time

log = logging.getLogger("FirePro3D")
from PyQt6.QtWidgets import (QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
                              QGraphicsItem, QGraphicsItemGroup, QGraphicsPixmapItem,
                              QGraphicsTextItem, QGraphicsSimpleTextItem,
                              QGraphicsPathItem, QGraphicsRectItem,
                              QApplication, QProgressDialog, QMenu,
                              QDialog)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import (QPen, QBrush, QColor, QPixmap, QPainterPath, QFont,
                          QImage, QPolygonF,
                          QTransform)
from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from .node import Node
from .pipe import Pipe
from .sprinkler import Sprinkler
from .sprinkler_system import SprinklerSystem
from .cad_math import CAD_Math
from .annotations import Annotation, DimensionAnnotation, NoteAnnotation
from .underlay import Underlay
from .underlay_freeze import UnderlayFreezeController, _UnderlayPathItem
from .scale_manager import ScaleManager
from .calibrate_dialog import CalibrateDialog
from .roof_dialog import RoofDialog
from .underlay_context_menu import UnderlayContextMenu
from .dxf_import_worker import DxfImportWorker
from .water_supply import WaterSupply
from .design_area import DesignArea, DesignAreaBadge
from .construction_geometry import (
    PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
    RegularPolygonItem,
)
from .snap_engine import SnapEngine, OsnapResult
from .display_manager import apply_category_defaults
from .gridline import (GridlineItem, reset_grid_counters,
                       sync_grid_counters, apply_duplicate_warnings, auto_label)
from .view_marker import ViewMarkerArrow
from .constants import (Z_BELOW_GEOMETRY, Z_UNDERLAY, DEFAULT_LEVEL,
                       DEFAULT_CEILING_OFFSET_MM, UNDERLAY_LINE_WIDTH_PX,
                       UNDERLAY_MM_TO_PX_HINT, UNDERLAY_FAST_PATH_SNAP_PX,
                       AUTO_JOIN_TOLERANCE, TEE_TOLERANCE, Z_COPLANAR_TOL,
                       DESIGN_AREA_HL_RADIUS_PX,
                       Z_OVERLAY, ALIGN_PATH_TOL_PX,
                       ALIGN_DWELL_MS, ALIGN_MAX_POINTS,
                       OPENING_ALIGN_CENTER, OPENING_ALIGNMENTS,
                       SELECTION_OUTLINE_COLOR, MIN_FLOOR_THICKNESS_MM)
from .fitting import Fitting
from .wall import WallSegment, compute_wall_quad, DEFAULT_THICKNESS_MM
from .floor_slab import FloorSlab
from .roof import RoofItem
from .room import Room
from .wall_opening import WallOpening, DoorOpening, WindowOpening
from .feature import DEFAULT_FEATURE_FOR_TYPE
from .constraints import Constraint as ConstraintBase
from .dynamic_input import SCHEMAS, effective_modifiers
from . import geometry_intersect as gi
import os


from .scene_io import SceneIOMixin
from .scene_tools import SceneTools
from .underlay_controller import UnderlayController
from .pipe_network_controller import PipeNetworkController
from .sprinkler_workflow_controller import SprinklerWorkflowController
from .network_codec import (
    serialize_node, serialize_pipe, serialize_dimension,
    serialize_note, serialize_water_supply, serialize_design_area,
)


def underlay_layer_pen(record: "Underlay", layer: str) -> QPen:
    """Cosmetic screen pen for one source layer of an underlay (spec §16.3).

    No effective weight -> exactly UNDERLAY_LINE_WIDTH_PX (today's look).
    Named weight -> width_mm * UNDERLAY_MM_TO_PX_HINT, still cosmetic.
    """
    colour = QColor(record.effective_layer_colour(layer))
    weight_name = record.effective_layer_weight(layer)
    if weight_name:
        from .paper_display import resolve_line_weight_mm
        width_px = resolve_line_weight_mm(weight_name) * UNDERLAY_MM_TO_PX_HINT
        # Near-1px hints snap to 1.0: Qt's fast cosmetic stroker only takes
        # widths <= 1.0 (see UNDERLAY_LINE_WIDTH_PX); ~1px hints are visually
        # identical but ~20x cheaper to stroke over a dense underlay.
        if width_px <= UNDERLAY_FAST_PATH_SNAP_PX:
            width_px = min(width_px, 1.0)
    else:
        width_px = UNDERLAY_LINE_WIDTH_PX
    pen = QPen(colour, width_px)
    pen.setCosmetic(True)
    return pen


def _pdf_width_to_px(pt_width: float) -> float:
    """PDF stroke width (points) -> cosmetic px, floored at the default width.

    Preserves the source line-width *hierarchy* while keeping thin lines at
    least as visible as today's flat ``UNDERLAY_LINE_WIDTH_PX``.
    """
    if pt_width <= 0.0:
        return UNDERLAY_LINE_WIDTH_PX
    width_mm = pt_width * 25.4 / 72.0
    width_px = max(UNDERLAY_LINE_WIDTH_PX, width_mm * UNDERLAY_MM_TO_PX_HINT)
    # Near-1px results snap to 1.0 for Qt's fast cosmetic-stroker path
    # (widths > 1.0 stroke ~20x slower; see UNDERLAY_LINE_WIDTH_PX).
    if width_px <= UNDERLAY_FAST_PATH_SNAP_PX:
        width_px = min(width_px, 1.0)
    return width_px


class _PlacementSentinel:
    """Marker object: ALIGN is active during placement, nothing to self-exclude.

    Set as ``_align_active_item`` for modes that place a *new* item (which has
    no scene identity yet), so the ALIGN tier is live without pointing at any
    real item to exclude.
    """


_GHOST_NODE_MARKER_MM = 120.0  # half-size of the move/paste ghost cross for nodes

# Arc placement variants (see ``_arc_variant``).  De-stringly-typed so a typo
# fails loudly at import instead of silently falling into centre-first.
_ARC_VARIANT_CENTER = "center"   # centre-first: click 1 is the arc centre
_ARC_VARIANT_START = "start"     # start-first: click 1 is the start point


def _record_levels(params, active: str) -> list[str]:
    """Levels for a new underlay record: the dialog's chosen levels, or
    ``[active_level]`` when the dialog authored none (redesign §10.3 reversal)."""
    chosen = list(getattr(params, "levels", None) or [])
    return chosen if chosen else [active]


class Model_Space(SceneIOMixin, QGraphicsScene):
    SNAP_RADIUS = 10
    SAVE_VERSION = 9  # v9: all dimensions stored in mm (was ft/in)
    UNDO_MAX = 50
    requestPropertyUpdate = pyqtSignal(object)
    cursorMoved = pyqtSignal(str)      # emits formatted "X: …  Y: …" string
    underlaysChanged = pyqtSignal()    # emitted when underlays list changes (for LayerManager)
    modeChanged = pyqtSignal(str)      # emits mode name for status bar instructions
    instructionChanged = pyqtSignal(str)  # emits step-by-step instruction text
    sceneModified = pyqtSignal()          # emitted on every push_undo_state
    radiationConfirm = pyqtSignal()       # Enter pressed during radiation selection
    radiationCancel = pyqtSignal()        # Escape pressed during radiation selection
    openViewRequested = pyqtSignal(str, str)  # (view_type, direction) — marker double-click
    # Dialog signals — UI shown by main.py, result fed back via callback
    numericInputRequested = pyqtSignal(str, str, str, float, float, float)  # mode, title, label, default, min, max
    warningIssued = pyqtSignal(str, str)                                    # title, message
    confirmRequested = pyqtSignal(str, str, str)                            # action_id, title, message
    snapToggled = pyqtSignal(bool)    # emitted whenever toggle_snap() runs
    alignToggled = pyqtSignal(bool)  # emitted whenever set_align_enabled() runs
    pipeNodeHighlight = pyqtSignal(str)  # pipe-mode node snap readout for status bar

    def __init__(self):
        super().__init__()
        self._tools = SceneTools(self)   # composed geometry-tool collaborator (decomposition slice B)
        self.setSceneRect(QRectF(-500000, -500000, 1000000, 1000000))
        # One-time repair: fix display/*/visible stored as bool instead of string
        self._repair_display_settings()
        # Disable BSP-tree indexing — cosmetic-pen items (gridlines) are
        # culled incorrectly by the spatial index at high zoom levels.
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.sprinkler_system = SprinklerSystem()
        self._pipe_ctl = PipeNetworkController(self)   # pipe/node concern (slice 5)
        self._spr_ctl = SprinklerWorkflowController(self)  # sprinkler/DA/hydraulic concern (slice 6)
        self.annotations = Annotation()
        self._sprinkler_db = None                              # shared DB, injected by MainWindow
        self._underlay_ctl = UnderlayController(self)  # underlay/import concern (slice)
        self._underlay_freeze = UnderlayFreezeController(self)  # spec §18
        self.scale_manager = ScaleManager()
        self.mode = None
        self.dimension_start = None
        self._dim_preview_line: "QGraphicsLineItem | None" = None
        self._dim_preview_label: "QGraphicsTextItem | None" = None
        self._dim_pending: "DimensionAnnotation | None" = None  # awaiting offset click (3-click mode)
        self._dim_line1: "LineItem | None" = None  # line hit on dim click 1 (for perpendicular detection)
        self._cal_point1 = None          # first point for "set_scale" mode
        self.node_start_pos = None
        self.node_end_pos = None
        self._pipe_node_was_new = False
        self._selected_items = None
        # The live on-canvas dynamic-input HUD, or None in cursor mode.  Its
        # presence *is* input mode — see is_input_mode.
        self.dynamic_input = None
        # Left-Shift tap tracking (cycle_placement_ambiguity). Armed on a clean
        # left-Shift press, broken by any other key or a click, consumed on the
        # matching release — so Shift-as-modifier never cycles.
        self._lshift_tap_armed = False
        self.water_supply_node: "WaterSupply | None" = None  # placed water supply
        self.hydraulic_result = None                          # last solver run (Sprint 2)
        self._radiation_selecting = False                      # True during radiation surface selection
        self.design_areas: list = []                          # list[DesignArea]
        self.active_design_area = None                        # DesignArea | None
        self.active_level: str = DEFAULT_LEVEL                     # floor level
        # Active view identity for per-view underlay visibility (§16.4).
        # Vocabulary: f"{source_view_type}:{view_name}" — e.g.
        # "plan:Plan: Level 1", "detail:Enlarged Riser".
        self.active_view_key: str = ""
        self._design_area_corner1: "QPointF | None" = None
        self._design_area_rect_item = None                    # QGraphicsRectItem preview
        self._da_highlights: list = []                        # pick-mode rings
        self._da_editing = None                               # DesignArea picks modify
        # Construction geometry (Sprint C)
        self._polylines: list[PolylineItem] = []
        self._polyline_active: "PolylineItem | None" = None   # in-progress polyline
        self._polyline_close_indicator: "QGraphicsEllipseItem | None" = None  # close-cue ring
        # Draw geometry (Sprint G)
        self._draw_lines: list[LineItem] = []
        self._draw_rects: list[RectangleItem] = []
        self._draw_circles: list[CircleItem] = []
        self._draw_dim_hint: "str | None" = None              # live dim overlay for Model_View
        self._draw_line_anchor: "QPointF | None" = None       # first click for line
        self._draw_rect_anchor: "QPointF | None" = None       # first click for rectangle
        self._draw_circle_center: "QPointF | None" = None     # first click for circle
        self._draw_rect_from_center: bool = False                # center vs corner rectangle
        self._draw_rect_preview: "QGraphicsRectItem | None" = None
        # Rectangle rotate step (Task 12).  Placement is 3-step: two clicks size
        # the axis-aligned rect, then a third rotates it.  ``_draw_rect_rotating``
        # is the step flag; the sized rect corners and the rotate pivot are
        # stashed while it is True (pivot = the first-click anchor — one of the
        # rect's corners — in corner mode, the centre in centre mode).  A 0°
        # rotate is the default axis-aligned end state.
        self._draw_rect_rotating: bool = False
        self._draw_rect_sized_pt1: "QPointF | None" = None
        self._draw_rect_sized_pt2: "QPointF | None" = None
        self._draw_rect_pivot: "QPointF | None" = None
        # Rotate-step reference guides: a 0° datum (horizontal) + the live sweep
        # line from the pivot, protractor-style (see _update_rect_ref_lines).
        self._draw_rect_ref_line0: "QGraphicsLineItem | None" = None
        self._draw_rect_ref_lineA: "QGraphicsLineItem | None" = None
        self._draw_circle_preview: "QGraphicsEllipseItem | None" = None
        # Polygon drawing (3-step: centre → radius → rotate)
        # _polygon_rotating: True during rotate step (after radius click)
        # _polygon_sized_radius: the fixed radius while rotating
        self._polygon_center: "QPointF | None" = None
        self._polygon_sides: int = 6
        self._polygon_inscribed: bool = True
        self._polygon_preview: "RegularPolygonItem | None" = None
        self._polygon_rotating: bool = False
        self._polygon_sized_radius: "float | None" = None
        self._polygon_ref_circle: "QGraphicsEllipseItem | None" = None
        self._polygon_ref_lineA: "QGraphicsLineItem | None" = None
        self._draw_polygons: list[RegularPolygonItem] = []
        self._last_scene_pos: "QPointF | None" = None  # last cursor position for Tab defaults
        self._resolved_point: "QPointF | None" = None  # constrained point published each frame
        # Arc drawing (3-click: centre, start point, end point)
        self._draw_arcs: list[ArcItem] = []
        # Holds the first click point.  In centre-first this is the arc centre
        # throughout.  In start-first (``_arc_variant == "start"``) it TRANSIENTLY
        # holds the START point until ``_commit_draw_arc_rim_at`` overwrites it
        # with the real centre at step 1→2 — don't trust the name mid-placement.
        self._draw_arc_center: "QPointF | None" = None
        self._draw_arc_radius: float = 0.0
        self._draw_arc_start_deg: float = 0.0
        self._draw_arc_step: int = 0  # 0=awaiting centre, 1=awaiting start, 2=awaiting end
        # "center" (centre-first, current) or "start" (start-first).  The
        # arrow-key CYCLE that flips this lands in a later task; the geometry is
        # already variant-aware so it can be driven by setting the flag.
        self._arc_variant: str = _ARC_VARIANT_CENTER
        self._draw_arc_radius_line: "QGraphicsLineItem | None" = None
        self._draw_arc_preview: "QGraphicsPathItem | None" = None
        # Arc span-step angle guides from the centre (protractor): a 0° datum
        # (horizontal) + the fixed start-angle radial + the live sweep radial
        # that tracks the cursor, so the sweep reads against both.
        self._draw_arc_ref_line0: "QGraphicsLineItem | None" = None
        self._draw_arc_ref_start: "QGraphicsLineItem | None" = None
        self._draw_arc_ref_sweep: "QGraphicsLineItem | None" = None
        # Placement-variant registry + session-sticky per-mode index (Task 13).
        self._init_placement_variants()
        # Text rubber-band (Sprint Q)
        self._text_anchor: "QPointF | None" = None
        self._text_preview: "QGraphicsRectItem | None" = None
        # Gridlines (Sprint U)
        self._gridlines: list[GridlineItem] = []
        # Gridline Array/Offset replication modes (Task 7)
        self._replicate_source = None           # GridlineItem being replicated
        self._replicate_kind: str = "array"     # "array" | "offset"
        self._replicate_count: int = 1
        self._replicate_spacing: float = 0.0
        self._replicate_ghost: list = []        # list[(QPointF origin, QPointF far)]
        self._move_ghost: list = []          # list[QPainterPath] in scene coords
        self._move_ghost_base: list = []      # base paths captured at first click
        # SNAP (Sprint H)
        self._snap_engine: SnapEngine = SnapEngine()
        self._snap_result: "OsnapResult | None" = None
        self._snap_enabled: bool = True
        self._snap_angle_deg: float = 45.0       # Ctrl-snap angle increment (degrees)
        # ALIGN acquire-and-track (align_controller.py + align_engine.py)
        from .align_controller import AlignController
        self._align_controller = AlignController(
            dwell_ms=ALIGN_DWELL_MS, max_points=ALIGN_MAX_POINTS)
        self._align_last_move_ns = None               # elapsed-ms clock between moves
        self._align_enabled: bool = True              # toggled via settings / F11
        # ALIGN path soft-snap aperture (px) — ALIGN's OWN grab band, separate
        # from the 15px real-snap aperture. Live-applied by the SnappingPane and
        # restored from QSettings; threaded into find(align_aperture_px=…).
        self._align_path_tol_px: float = float(ALIGN_PATH_TOL_PX)
        self._align_result = None                     # surfaced to drawForeground
        # On-path Navigate (Task 6 follow-up): the winning single-path Ray + the
        # cursor's signed distance along it, recovered in get_effective_position
        # while soft-snapped to one ``align_path``.  Drives the ``track`` schema
        # swap (active_schema) — None whenever the cursor is off a single path
        # (off ALIGN entirely, or on an ``align_intersection`` crossing, which
        # gets no distance field).  Survives ``clear_placement_state`` because it
        # is set before that call in the mouse-move path.
        self._align_track_ray = None                  # align_engine.Ray | None
        self._align_track_dist = 0.0                  # signed distance along it
        # Direction the auto-acquired active anchor extends along (spec D3): the
        # unit direction of the directional object the FIRST placement point
        # landed on, captured at the arming click (mousePressEvent).  ``None``
        # when the first point started in empty space / on a non-directional
        # point — then the anchor emits H/V only, no phantom extension.  Cleared
        # on every acquire-set reset so a prior element's direction never leaks.
        self._align_anchor_dir = None                 # (dx, dy) unit | None
        self._align_active_item = None                # item being placed/dragged (self-exclude)
        self._PLACEMENT_SENTINEL = _PlacementSentinel()  # shared sentinel for draw_gridline
        # Pipe-mode Tab cycling state now lives on self._pipe_ctl (controller)
        self._project_info: dict = {}            # project metadata (name, address, etc.)
        self._titleblock_template: dict | None = None  # embedded template dict (authoritative copy)
        self._level_manager = None                             # set by main.py
        self._plan_view_manager = None                         # set by main.py
        # Grip editing (Sprint I)
        self._grip_item = None                  # item currently being grip-dragged
        self._grip_index: int = -1              # grip handle index
        self._grip_dragging: bool = False
        # Gridline body drag (perpendicular constraint)
        self._dragging_gridline = None          # GridlineItem being body-dragged
        self._gridline_drag_start = None        # scene pos at drag start
        self._gridline_drag_original_pos = None # perpendicular position at drag start
        # Gridline spacing dimensions (on-selection)
        self._gridline_spacing_dims: list[dict] = []
        # Offset command (Sprint L)
        self._offset_source = None              # entity selected for offset
        self._offset_dist: float = 0.0          # distance entered by user
        self._offset_preview = None             # preview item shown during side-pick
        self._offset_manual: bool = False       # True when user typed distance via Tab
        self._offset_highlight = None           # highlight overlay for selected offset entity
        # Trim / Extend / Merge state (Sprint Y)
        self._trim_edge = None              # cutting edge item for trim
        self._trim_edge_highlight = None    # highlight overlay
        self._extend_boundary = None        # boundary edge item for extend
        self._extend_boundary_highlight = None
        self._merge_point1: tuple | None = None  # (item, grip_index, QPointF)
        self._merge_preview = None          # visual line connecting merge points
        # Constraint state (Sprint Y)
        self._constraints: list = []        # list of Constraint objects
        self._constraint_circle_a = None    # first circle for concentric constraint
        self._constraint_grip_a: tuple | None = None  # (item, grip_index) for dimensional
        # Align tool state
        self._align_reference = None
        self._align_highlight = None
        self._align_ghost = None
        self._align_padlocks: list = []
        # Interactive transforms (Rotate, Scale, Mirror)
        self._rotate_pivot: "QPointF | None" = None
        self._rotate_preview_line = None
        self._scale_base: "QPointF | None" = None
        self._scale_preview_line = None
        self._scale_factor: float = 1.0
        self._mirror_p1: "QPointF | None" = None
        self._mirror_preview_line = None
        # Break / Break at Point
        self._break_target = None
        self._break_highlight = None
        self._break_p1: "QPointF | None" = None
        self._break_at_target = None
        self._break_at_highlight = None
        # Fillet / Chamfer
        self._fillet_radius: float = 5.0
        self._fillet_item1 = None
        self._fillet_item2 = None
        self._fillet_highlight1 = None
        self._fillet_highlight2 = None
        self._fillet_preview = None
        self._chamfer_dist: float = 5.0
        self._chamfer_item1 = None
        self._chamfer_item2 = None
        self._chamfer_highlight1 = None
        self._chamfer_highlight2 = None
        self._chamfer_preview = None
        # Stretch
        self._stretch_vertices: list = []
        self._stretch_full_items: list = []
        self._stretch_base: "QPointF | None" = None
        self._stretch_preview_line = None
        # Place-import mode (Sprint L)
        # Modify "Pick new position" payloads (None for a fresh import):
        # management fields to re-apply on commit + the old underlay to remove
        # on commit (removal deferred so a cancelled pick is non-destructive).
        # (transient state now owned by self._underlay_ctl — slice C1)
        # Walls, Floors, Openings (Phase B/C/D)
        self._walls: list[WallSegment] = []
        self._floor_slabs: list[FloorSlab] = []
        self._next_wall_num: int = 1
        self._next_floor_num: int = 1
        self._wall_alignment: str = "Center"                  # alignment mode for new walls
        self._wall_primitive: str = "line"                    # variant for wall mode: "line"|"polyline"|"rect"
        self._wall_template: "WallSegment | None" = None      # pre-placement property template
        self._floor_template: "FloorSlab | None" = None       # pre-placement property template
        self._gridline_template: "GridlineItem | None" = None  # pre-placement property template
        self._roofs: list[RoofItem] = []
        self._rooms: list[Room] = []
        self._room_manual_active: "Room | None" = None     # in-progress manual room boundary
        self._next_roof_num: int = 1
        self._roof_template: "RoofItem | None" = None         # pre-placement property template
        self._roof_active: "RoofItem | None" = None           # in-progress roof boundary
        self._roof_rect_anchor: "QPointF | None" = None       # first click for rect roof
        self._roof_rect_preview: "QGraphicsRectItem | None" = None
        self._wall_anchor: "QPointF | None" = None          # first click for wall drawing
        self._wall_chain_start: "QPointF | None" = None    # very first anchor for wall-close
        self._wall_preview_rect: "QGraphicsPathItem | None" = None  # thickness preview
        self._wall_preview_line: "QGraphicsLineItem | None" = None
        self._wall_rect_anchor: "QPointF | None" = None   # first click for rect wall
        self._wall_rect_preview: "QGraphicsRectItem | None" = None
        self._wall_rect_thickness_preview: "QGraphicsPathItem | None" = None
        # Rect-wall rotate step (mirrors 2D-geo draw_rectangle rotate step)
        self._wall_rect_from_center: bool = False
        self._wall_rect_rotating: bool = False
        self._wall_rect_sized_pt1: "QPointF | None" = None
        self._wall_rect_sized_pt2: "QPointF | None" = None
        self._wall_rect_pivot: "QPointF | None" = None
        self._wall_rect_ref_line0: "QGraphicsLineItem | None" = None
        self._wall_rect_ref_lineA: "QGraphicsLineItem | None" = None
        self._floor_active: "FloorSlab | None" = None       # in-progress floor boundary
        self._floor_primitive: str = "rect"                 # variant for floor mode: "rect"|"polygon"
        self._floor_rect_from_center: bool = False          # corner vs centre rect
        self._floor_rect_anchor: "QPointF | None" = None   # first click for rect floor
        self._floor_rect_preview: "QGraphicsRectItem | None" = None
        # Rect-floor rotate step (mirrors the wall rect rotate step)
        self._floor_rect_sized_pt1: "QPointF | None" = None
        self._floor_rect_sized_pt2: "QPointF | None" = None
        self._floor_rect_rotating: bool = False
        self._floor_rect_pivot: "QPointF | None" = None
        self._floor_rect_ref_line0: "QGraphicsLineItem | None" = None
        self._floor_rect_ref_lineA: "QGraphicsLineItem | None" = None
        self._geometry_template = None                      # pre-placement template for geometry tools
        # Opening placement (§7.6): unified door/window/blank mode carrying a
        # Feature id + pre-commit cycle state (alignment / hinge / facing).
        self._opening_feature_id: str = DEFAULT_FEATURE_FOR_TYPE["door"]
        self._opening_alignment: str = OPENING_ALIGN_CENTER
        self._opening_mirror_hinge: bool = False
        self._opening_mirror_facing: bool = False
        self._opening_ghost: "WallOpening | None" = None    # live preview on hovered wall
        # Detail view placement
        self._detail_rect_anchor: "QPointF | None" = None
        self._detail_rect_preview: "QGraphicsRectItem | None" = None
        self._detail_markers: list = []
        self._detail_manager = None  # set by main.py
        self._sheets: list = []
        # Undo/redo
        self._undo_stack: list[dict] = []
        self._undo_pos: int = -1
        self._in_undo_restore: bool = False
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()
        self.push_undo_state()   # initial empty state
        self.selectionChanged.connect(self._on_selection_changed)
        # Scene-level selection manipulator (frame + rigid transforms) —
        # governing spec docs/specs/selection-manipulator.md.  One undo entry
        # per baked gesture via push_undo_state.
        self._manipulator = None
        self._create_manipulator()

    @property
    def underlays(self):
        """Back-compat read view of the underlay list (owned by the controller)."""
        return self._underlay_ctl.items

    # --- place_import transient state: forwarded so in-file references resolve (C1 bridge) ---
    @property
    def _place_import_params(self):
        return self._underlay_ctl._place_import_params

    @_place_import_params.setter
    def _place_import_params(self, v):
        self._underlay_ctl._place_import_params = v

    @property
    def _place_import_ghost(self):
        return self._underlay_ctl._place_import_ghost

    @_place_import_ghost.setter
    def _place_import_ghost(self, v):
        self._underlay_ctl._place_import_ghost = v

    @property
    def _place_import_bounds(self):
        return self._underlay_ctl._place_import_bounds

    @_place_import_bounds.setter
    def _place_import_bounds(self, v):
        self._underlay_ctl._place_import_bounds = v

    @property
    def _place_import_preserve_mgmt(self):
        return self._underlay_ctl._place_import_preserve_mgmt

    @_place_import_preserve_mgmt.setter
    def _place_import_preserve_mgmt(self, v):
        self._underlay_ctl._place_import_preserve_mgmt = v

    @property
    def _place_import_remove_old(self):
        return self._underlay_ctl._place_import_remove_old

    @_place_import_remove_old.setter
    def _place_import_remove_old(self, v):
        self._underlay_ctl._place_import_remove_old = v

    def _create_manipulator(self):
        """(Re)create the scene's selection manipulator and stash it."""
        from .selection_manipulator import SelectionManipulator
        self._manipulator = SelectionManipulator(
            self, commit_hook=lambda mode: self.push_undo_state())
        return self._manipulator

    def _live_manip(self):
        """Return the selection manipulator, recreating it if a scene rebuild
        deleted its underlying C++ object.

        The manipulator is a scene item, so paths that sweep the scene (undo
        ``_restore_network``, load, new file) can delete the C++ QGraphicsObject
        while this Python reference survives — touching it then raises
        ``wrapped C/C++ object ... has been deleted`` and, because it is read at
        the top of ``mousePressEvent``, would break *every* click (placement
        included). Self-heal so the press pipeline never crashes.
        """
        from PyQt6 import sip
        m = getattr(self, "_manipulator", None)
        if m is not None and not sip.isdeleted(m):
            return m
        return self._create_manipulator()

    # -------------------------------------------------------------------------
    # Selection change handler

    def _on_selection_changed(self):
        """Recompute gridline spacing dimensions when selection changes."""
        self._gridline_spacing_dims = self._compute_gridline_spacing()
        # Snapshot selected gridlines — only update when there IS a
        # selection.  The double-click press events fire deselection
        # before mouseDoubleClickEvent, so we must keep the last
        # non-empty snapshot intact.
        sel = [item for item in self.selectedItems()
               if isinstance(item, GridlineItem)]
        if sel:
            self._gridline_spacing_selected = sel
        for v in self.views():
            v.viewport().update()

    # -------------------------------------------------------------------------
    # Gridline spacing computation

    def _compute_gridline_spacing(self) -> list[dict]:
        """Compute spacing dimensions between adjacent gridlines.

        Single selection: dimensions to nearest parallel unselected
        neighbour on each side.

        Multi-selection: chain dimensions between adjacent selected
        gridlines, plus one dimension from each outer edge to the
        nearest unselected neighbour.
        """
        EPS_ANGLE = math.radians(0.5)

        selected_set = set(
            item for item in self.selectedItems()
            if isinstance(item, GridlineItem))
        if not selected_set:
            return []

        def _ang_mod_pi(gl):
            ln = gl.line()
            a = math.atan2(ln.p2().y() - ln.p1().y(),
                           ln.p2().x() - ln.p1().x())
            return a % math.pi

        # Cluster gridlines by direction angle (mod π): two lines share a
        # cluster only if they are TRULY parallel within EPS_ANGLE.  This
        # replaces the old binary dy>=dx bucket, which mis-paired lines of
        # different angles and flipped discontinuously near 45°.
        clusters: list[list[dict]] = []   # each: [{gl, a}]
        for gl in self._gridlines:
            a = _ang_mod_pi(gl)
            for cl in clusters:
                d = abs(a - cl[0]["a"])
                d = min(d, math.pi - d)
                if d <= EPS_ANGLE:
                    cl.append({"gl": gl, "a": a})
                    break
            else:
                clusters.append([{"gl": gl, "a": a}])

        results = []

        for cl in clusters:
            if not any(m["gl"] in selected_set for m in cl):
                continue

            # Cluster shared normal from the first member.  All members are
            # parallel within EPS_ANGLE, so their normals agree.
            px, py = cl[0]["gl"]._perpendicular_vector()

            # Along-direction unit vector + position from the first selected
            # member (for dimension-line placement).
            ref_gl = next(m["gl"] for m in cl if m["gl"] in selected_set)
            dir_x = ref_gl.line().p2().x() - ref_gl.line().p1().x()
            dir_y = ref_gl.line().p2().y() - ref_gl.line().p1().y()
            dir_len = math.hypot(dir_x, dir_y)
            ux = dir_x / dir_len if dir_len > 1e-12 else 0.0
            uy = dir_y / dir_len if dir_len > 1e-12 else 1.0
            along_pos = ref_gl.line().p1().x() * ux + ref_gl.line().p1().y() * uy

            def _make_dim(gl_a, perp_a, gl_b, perp_b, px=px, py=py,
                          along_pos=along_pos, ux=ux, uy=uy):
                from_pt = QPointF(perp_a * px + along_pos * ux,
                                  perp_a * py + along_pos * uy)
                to_pt = QPointF(perp_b * px + along_pos * ux,
                                perp_b * py + along_pos * uy)
                mid = QPointF((from_pt.x() + to_pt.x()) / 2,
                              (from_pt.y() + to_pt.y()) / 2)
                return {
                    "from_gl": gl_a, "to_gl": gl_b,
                    "distance": abs(perp_b - perp_a),
                    "from_pt": from_pt, "to_pt": to_pt,
                    "midpoint": mid, "perp_vector": (px, py),
                }

            # Project members onto the shared normal and sort.
            members = sorted(
                ((m["gl"],
                  m["gl"].line().p1().x() * px + m["gl"].line().p1().y() * py)
                 for m in cl),
                key=lambda t: t[1])

            # Walk the sorted list: emit a dim between every adjacent pair
            # where at least one side is selected (covers single + multi).
            for i in range(len(members) - 1):
                gl_a, perp_a = members[i]
                gl_b, perp_b = members[i + 1]
                if gl_a in selected_set or gl_b in selected_set:
                    results.append(_make_dim(gl_a, perp_a, gl_b, perp_b))

        return results

    def _apply_spacing_edit(self, dim: dict, new_distance: float,
                            selected: list | None = None):
        """Move gridlines so that the spacing matches *new_distance*.

        *selected* is the list of GridlineItems that were selected when
        the edit started.  All selected gridlines move as a rigid group;
        the unselected anchor stays put.
        """
        self.push_undo_state()
        from_gl, to_gl = dim["from_gl"], dim["to_gl"]
        delta = new_distance - dim["distance"]

        if selected is None:
            selected = [i for i in self.selectedItems()
                        if isinstance(i, GridlineItem)]

        if to_gl in selected and from_gl not in selected:
            for gl in selected:
                if not gl.locked:
                    gl.move_perpendicular(delta)
        elif from_gl in selected and to_gl not in selected:
            for gl in selected:
                if not gl.locked:
                    gl.move_perpendicular(-delta)
        else:
            if not to_gl.locked:
                to_gl.move_perpendicular(delta)

        self._gridline_spacing_dims = self._compute_gridline_spacing()
        self.update()

    # -------------------------------------------------------------------------
    # Preview items

    def init_preview_pipe(self):
        self.preview_pipe = QGraphicsLineItem()
        pen = QPen(Qt.GlobalColor.darkGray, 3, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.preview_pipe.setPen(pen)
        self.preview_pipe.setZValue(200)
        self.preview_pipe.setOpacity(0.7)
        self.addItem(self.preview_pipe)
        self.preview_pipe.hide()

        # Preview label (child of preview_pipe)
        self._preview_label = QGraphicsSimpleTextItem("", self.preview_pipe)
        self._preview_label.setBrush(QBrush(QColor("#ffffff")))
        self._preview_label.setZValue(201)
        self._preview_label.hide()

    def init_preview_node(self):
        self.preview_node = QGraphicsEllipseItem(-5, -5, 10, 10)
        self.preview_node.setBrush(QBrush(QColor(0, 0, 255, 100)))
        self.preview_node.setPen(QPen(Qt.GlobalColor.blue))
        self.preview_node.setZValue(200)
        self.preview_node.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.addItem(self.preview_node)
        self.preview_node.hide()

    # -------------------------------------------------------------------------
    # SAVE / LOAD  →  see scene_io.py (SceneIOMixin)
    # save_to_file(), load_from_file(), _clear_scene()
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # SCENE MANAGEMENT

    def _show_status(self, message: str, timeout: int = 5000):
        """Show a message on the main window's status bar."""
        views = self.views()
        if views:
            window = views[0].window()
            if window and hasattr(window, 'statusBar'):
                window.statusBar().showMessage(message, timeout)

    def draw_origin(self):
        """Draw a small white cross at the origin — constant screen size, non-selectable."""
        pen = QPen(QColor("#ffffff"))
        pen.setWidthF(1.5)
        pen.setCosmetic(True)
        size = 10  # ±10 device pixels → 20px cross on screen
        h_line = QGraphicsLineItem(-size, 0, size, 0)
        v_line = QGraphicsLineItem(0, -size, 0, size)
        h_line.setPen(pen)
        v_line.setPen(pen)
        # Non-interactive — purely decorative, constant screen size
        for item in (h_line, v_line):
            item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, False)
            item.setFlag(item.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(item.GraphicsItemFlag.ItemIgnoresTransformations, True)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setZValue(Z_BELOW_GEOMETRY)
            item.setData(0, "origin")  # tag so snap engine skips it
        self.addItem(h_line)
        self.addItem(v_line)

    def _remove_dim_preview(self):
        """Remove the temporary dimension placement preview items."""
        if self._dim_preview_line is not None:
            if self._dim_preview_line.scene() is self:
                self.removeItem(self._dim_preview_line)
            self._dim_preview_line = None
        if self._dim_preview_label is not None:
            if self._dim_preview_label.scene() is self:
                self.removeItem(self._dim_preview_label)
            self._dim_preview_label = None

    # -------------------------------------------------------------------------
    # DELETE

    def _remove_item_from_lists(self, item) -> bool:
        """Remove *item* from its tracking list and the scene.

        Returns True if the item was handled, False otherwise.
        """
        # Map each geometry type to the list that tracks it
        type_to_list = {
            DimensionAnnotation: self.annotations.dimensions,
            NoteAnnotation:      self.annotations.notes,
            PolylineItem:        self._polylines,
            LineItem:            self._draw_lines,
            RectangleItem:       self._draw_rects,
            CircleItem:          self._draw_circles,
            ArcItem:             self._draw_arcs,
            RegularPolygonItem:  self._draw_polygons,
            GridlineItem:        self._gridlines,
        }
        for cls, lst in type_to_list.items():
            if isinstance(item, cls):
                if item in lst:
                    lst.remove(item)
                self.removeItem(item)
                return True
        return False

    def _delete_single_item(self, item):
        """Remove a single geometry/annotation item from the scene and its tracking list."""
        self._remove_item_from_lists(item)

    def delete_selected_items(self):
        if not self.selectedItems():
            return
        selected = list(self.selectedItems())
        selected_set = set(selected)

        # Suppress scene updates during bulk deletion
        self.blockSignals(True)
        try:
            self._bulk_delete(selected, selected_set)
        finally:
            self.blockSignals(False)

        # Single scene refresh after all removals
        self.update()
        self._show_status(f"Deleted {len(selected)} item(s)")
        self.push_undo_state()

    def _bulk_delete(self, selected, selected_set):
        """Internal bulk-delete: removes items without per-item scene updates."""
        # Collect all pipes and nodes for batch removal from sprinkler_system
        pipes_to_remove = set()
        nodes_to_remove = set()
        sprinklers_to_remove = set()

        # ── Pass 1: Geometry / annotations / walls / floors / roofs ───────
        for item in selected:
            if isinstance(item, (Pipe, Node)):
                continue  # handled in passes 2-3
            if self._remove_item_from_lists(item):
                continue
            if isinstance(item, WaterSupply):
                self.removeItem(item)
                if self.water_supply_node is item:
                    self.water_supply_node = None
                    self.sprinkler_system.supply_node = None
            elif isinstance(item, DesignArea):
                if item in self.design_areas:
                    self.design_areas.remove(item)
                if self.active_design_area is item:
                    self.active_design_area = None
                if self._da_editing is item:
                    self._da_editing = None
                self.removeItem(item)
            elif isinstance(item, WallSegment):
                for op in list(item.openings):
                    if op.scene() is self:
                        self.removeItem(op)
                item.openings.clear()
                if item in self._walls:
                    self._walls.remove(item)
                self.removeItem(item)
            elif isinstance(item, FloorSlab):
                if item in self._floor_slabs:
                    self._floor_slabs.remove(item)
                self.removeItem(item)
            elif isinstance(item, RoofItem):
                if item in self._roofs:
                    self._roofs.remove(item)
                self.removeItem(item)
            elif isinstance(item, Room):
                if item in self._rooms:
                    self._rooms.remove(item)
                self.removeItem(item)
            elif isinstance(item, (DoorOpening, WindowOpening)):
                if item.wall is not None and item in item.wall.openings:
                    item.wall.openings.remove(item)
                self.removeItem(item)

        # ── Pass 2: Collect all pipes to delete (selected + orphaned) ─────
        for item in selected:
            if isinstance(item, Pipe):
                pipes_to_remove.add(item)
            elif isinstance(item, Node):
                # Collect pipes attached to selected nodes
                for pipe in list(item.pipes):
                    pipes_to_remove.add(pipe)
                if item.has_sprinkler():
                    sprinklers_to_remove.add(item.sprinkler)
                nodes_to_remove.add(item)

        # ── Pass 3: Detach and remove pipes in bulk ───────────────────────
        for pipe in pipes_to_remove:
            for node in (pipe.node1, pipe.node2):
                if node is not None and pipe in node.pipes:
                    node.pipes.remove(pipe)
                    # Queue orphaned nodes (no pipes, no sprinkler) for removal
                    if not node.pipes and not node.has_sprinkler():
                        nodes_to_remove.add(node)
            pipe.node1 = None
            pipe.node2 = None
            # Remove top-level label from scene
            if hasattr(pipe, "label") and pipe.label is not None:
                try:
                    self.removeItem(pipe.label)
                except (RuntimeError, ValueError):
                    pass
            # Remove top-level riser symbol from scene
            if hasattr(pipe, "_riser_symbol") and pipe._riser_symbol is not None:
                try:
                    self.removeItem(pipe._riser_symbol)
                except (RuntimeError, ValueError):
                    pass
            try:
                if pipe.scene() is self:
                    self.removeItem(pipe)
            except RuntimeError:
                pass

        # ── Pass 4: Remove sprinklers ─────────────────────────────────────
        for spr in sprinklers_to_remove:
            try:
                if spr.scene() is self:
                    self.removeItem(spr)
            except RuntimeError:
                pass
            if spr.node:
                spr.node.delete_sprinkler()

        # ── Pass 5: Remove nodes ──────────────────────────────────────────
        for node in nodes_to_remove:
            try:
                if node.scene() is self:
                    self.removeItem(node)
            except RuntimeError:
                pass

        # ── Batch cleanup of sprinkler_system lists ───────────────────────
        ss = self.sprinkler_system
        if pipes_to_remove:
            ss.pipes = [p for p in ss.pipes if p not in pipes_to_remove]
        if nodes_to_remove:
            ss.nodes = [n for n in ss.nodes if n not in nodes_to_remove]
        if sprinklers_to_remove:
            ss.sprinklers = [s for s in ss.sprinklers if s not in sprinklers_to_remove]

        # ── Constraints ───────────────────────────────────────────────────
        all_deleted = selected_set | pipes_to_remove | nodes_to_remove
        self._constraints = [c for c in self._constraints
                             if not any(c.involves(d) for d in all_deleted)]

        # Clean up padlocks for removed constraints
        surviving = set(self._constraints)
        stale_padlocks = [p for p in self._align_padlocks
                          if p._constraint is not None
                          and p._constraint not in surviving]
        for p in stale_padlocks:
            self._align_padlocks.remove(p)
            if p.scene() is self:
                self.removeItem(p)

        # Update fittings on surviving nodes that lost pipes
        for node in ss.nodes:
            if hasattr(node, "fitting") and node.fitting:
                node.fitting.update()

    # -------------------------------------------------------------------------
    # MODE MANAGEMENT

    def set_mode(self, mode, template=None):
        # Backward-compat alias: the ribbon calls set_mode("wall_rect") until
        # Task 6 updates it.  Fold into the unified "wall" mode with the rect
        # primitive pre-selected so all downstream logic sees mode == "wall".
        # Also pin the sticky variant index to the "rect" slot (index 2) so
        # _apply_current_variant() does not overwrite the selection.
        if mode == "wall_rect":
            self._wall_primitive = "rect"
            self._wall_rect_from_center = False
            if hasattr(self, "_variant_index"):
                self._variant_index["wall"] = 2  # "Wall (Corner Rectangle)" slot
            mode = "wall"
        # Backward-compat alias: the old ribbon menu calls set_mode("floor_rect").
        # Fold into unified "floor" mode with the corner-rect primitive selected
        # (index 0) so all downstream logic sees mode == "floor".
        if mode == "floor_rect":
            self._floor_primitive = "rect"
            self._floor_rect_from_center = False
            if hasattr(self, "_variant_index"):
                self._variant_index["floor"] = 0  # "Floor (Corner Rectangle)" slot
            mode = "floor"
        # A HUD outlives neither its schema nor its anchor: leaving one open
        # across a mode switch would strand a widget whose applier belongs to
        # the mode just left.  Closed before self.mode changes so the tear-down
        # still sees the mode the HUD was built for.
        #
        # Unconditional, *not* gated on ``is_input_mode()``: since decision S1
        # that answers "is a field focused", and the HUD spends most of a
        # placement unfocused.  Gating here would strand exactly the common case
        # — a passive readout for a mode the user has just left.
        # ``end_dynamic_input`` is a no-op when nothing is open.
        self.end_dynamic_input()
        # The resolved point and the readout derived from it belong to the
        # placement being torn down, not to the mode being entered; leaving
        # them set outlives every anchor cleared below and strands the live
        # readout on screen.
        self.clear_placement_state()
        self.mode = mode
        self._snap_result = None      # clear stale snap marker
        if hasattr(self, 'pipeNodeHighlight'):
            self.pipeNodeHighlight.emit("")
        # Reset grip editing state (prevents stale grip after Escape mid-drag)
        self._grip_item = None
        self._grip_index = -1
        self._grip_dragging = False
        # ALIGN active-item: arm the seam for EVERY point-asking placement mode
        # (spec 2026-08-26 universal client scope — see ``_ALIGN_PLACEMENT_MODES``).
        # New-item placement modes have no scene item to self-exclude, so they
        # take the shared ``_PLACEMENT_SENTINEL`` (as gridline/wall always did);
        # move/paste start on the sentinel too and the press path swaps in the
        # real moved item for self-exclusion, and a grip-drag sets the dragged
        # item directly (see mousePressEvent).
        # The acquire set never survives a mode boundary (design spec: Esc /
        # commit / mode-start/end clears all) — reset it and the dwell clock
        # here, the one place every mode change funnels through.
        self._align_controller.clear()
        self._align_last_move_ns = None
        self._align_anchor_dir = None
        if mode in self._ALIGN_PLACEMENT_MODES:
            self._align_active_item = self._PLACEMENT_SENTINEL
        else:
            self._align_active_item = None
            self._align_result = None
        # Clear the move/paste ghost when leaving those modes.
        if mode not in ("paste", "move"):
            self._move_ghost = []
            self._move_ghost_base = []
        # Reset gridline body drag state
        self._dragging_gridline = None
        self._gridline_drag_start = None
        self._gridline_drag_original_pos = None
        self.modeChanged.emit(mode)
        # Auto-deselect all geometry when entering a drawing/placement mode
        if mode not in ("select", "stretch", "move", "rotate", "scale",
                        "radiation_emitter", "radiation_receiver"):
            self.clearSelection()
        self.preview_node.hide()
        self.preview_pipe.hide()
        self._cal_point1 = None
        # (design_area mode suppresses snapping entirely in
        # get_effective_position — sprinkler centres only)
        self._snap_engine.skip_pipes = False
        # Design-area style + Z are mode-dependent (editing vs confirmed) —
        # resync on every mode change
        for _da in self.design_areas:
            _da.sync_z_for_mode(mode == "design_area")
            _da.update()
        # Clean up design_area preview if leaving that mode mid-draw
        if mode != "design_area":
            self._da_editing = None
            self._refresh_da_highlights()   # self-clearing outside the mode
            self._design_area_corner1 = None
            if self._design_area_rect_item is not None:
                if self._design_area_rect_item.scene() is self:
                    self.removeItem(self._design_area_rect_item)
                self._design_area_rect_item = None
        # Pipe placement teardown (orphan-delete + Tab-cycle reset) — owned by
        # the pipe controller (slice 5). Idempotent; safe on every mode change.
        self._pipe_ctl.clear()
        # Cancel in-progress construction geometry
        if mode != "polyline" and self._polyline_active is not None:
            # Cancel: always discard the in-progress polyline
            # (Enter commits via finalize() and sets _polyline_active=None
            #  before reaching here, so this path is only hit by Escape/mode-change)
            if self._polyline_active.scene() is self:
                self.removeItem(self._polyline_active)
            if self._polyline_active in self._polylines:
                self._polylines.remove(self._polyline_active)
            self._polyline_active = None
        self._hide_polyline_close_indicator()
        # Cancel in-progress draw geometry
        if mode not in ("draw_line", "draw_gridline"):
            self._draw_line_anchor = None
        if mode != "draw_rectangle":
            self._draw_rect_anchor = None
            self._draw_rect_rotating = False
            self._draw_rect_sized_pt1 = None
            self._draw_rect_sized_pt2 = None
            self._draw_rect_pivot = None
            self._clear_rect_ref_lines()
            if self._draw_rect_preview is not None:
                if self._draw_rect_preview.scene() is self:
                    self.removeItem(self._draw_rect_preview)
                self._draw_rect_preview = None
        if mode != "draw_circle":
            self._draw_circle_center = None
            if self._draw_circle_preview is not None:
                if self._draw_circle_preview.scene() is self:
                    self.removeItem(self._draw_circle_preview)
                self._draw_circle_preview = None
        if mode != "polygon":
            self._polygon_center = None
            self._polygon_rotating = False
            self._polygon_sized_radius = None
            if self._polygon_preview is not None:
                if self._polygon_preview.scene() is self:
                    self.removeItem(self._polygon_preview)
                self._polygon_preview = None
            self._clear_polygon_ref_items()
        if mode != "draw_arc":
            self._draw_arc_center = None
            self._draw_arc_radius = 0.0
            self._draw_arc_start_deg = 0.0
            self._draw_arc_step = 0
            if self._draw_arc_radius_line is not None:
                if self._draw_arc_radius_line.scene() is self:
                    self.removeItem(self._draw_arc_radius_line)
                self._draw_arc_radius_line = None
            if self._draw_arc_preview is not None:
                if self._draw_arc_preview.scene() is self:
                    self.removeItem(self._draw_arc_preview)
                self._draw_arc_preview = None
            self._clear_arc_ref_lines()
        if mode != "text":
            self._text_anchor = None
            if self._text_preview is not None:
                if self._text_preview.scene() is self:
                    self.removeItem(self._text_preview)
                self._text_preview = None
        if mode != "dimension":
            self.dimension_start = None
            self._dim_line1 = None
            self._remove_dim_preview()
            if self._dim_pending is not None:
                # Finalize at current offset
                self._dim_pending = None
                self.push_undo_state()
        if mode in ("sprinkler", "pipe", "set_scale"):
            self.current_template = template
            if template:
                template._scene_ref = self  # so template can access level_manager
                if mode == "pipe":
                    template._placement_phase = 0
                    # Sync per-node defaults — use existing per-node values or fall back to defaults
                    template.node1_ceiling_level = template.node1_ceiling_level or DEFAULT_LEVEL
                    template.node1_ceiling_offset = template.node1_ceiling_offset if template.node1_ceiling_offset is not None else DEFAULT_CEILING_OFFSET_MM
                    template.node2_ceiling_level = template.node2_ceiling_level or DEFAULT_LEVEL
                    template.node2_ceiling_offset = template.node2_ceiling_offset if template.node2_ceiling_offset is not None else DEFAULT_CEILING_OFFSET_MM
                self.requestPropertyUpdate.emit(template)
        else:
            self.current_template = None

        # Clean up offset preview whenever leaving offset modes
        if mode not in ("offset", "offset_side"):
            self._tools._clear_offset_preview()
            self._offset_source = None
            self._offset_manual = False
            if self._offset_highlight is not None:
                if self._offset_highlight.scene() is self:
                    self.removeItem(self._offset_highlight)
                self._offset_highlight = None

        # Clean up gridline replicate modes
        if mode not in ("gridline_array", "gridline_offset"):
            self._replicate_source = None
            self._replicate_ghost = []

        # Clean up trim state
        if mode not in ("trim", "trim_pick"):
            self._tools._clear_trim_state()

        # Clean up extend state
        if mode not in ("extend", "extend_pick"):
            self._tools._clear_extend_state()

        # Clean up merge state
        if mode != "merge_points":
            self._merge_point1 = None
            if self._merge_preview is not None:
                if self._merge_preview.scene() is self:
                    self.removeItem(self._merge_preview)
                self._merge_preview = None

        # Clean up constraint state
        if mode != "constraint_concentric":
            self._constraint_circle_a = None
        if mode != "constraint_dimensional":
            self._constraint_grip_a = None

        # Clean up align state
        if mode != "align":
            self._align_reference = None
            if self._align_highlight is not None:
                if self._align_highlight.scene() is self:
                    self.removeItem(self._align_highlight)
                self._align_highlight = None
            if hasattr(self, '_align_ghost') and self._align_ghost is not None:
                if self._align_ghost.scene() is self:
                    self.removeItem(self._align_ghost)
                self._align_ghost = None

        # Clean up wall drawing state
        if mode != "wall":
            self._wall_anchor = None
            self._wall_chain_start = None
            if self._wall_preview_line is not None:
                if self._wall_preview_line.scene() is self:
                    self.removeItem(self._wall_preview_line)
                self._wall_preview_line = None
            if self._wall_preview_rect is not None:
                if self._wall_preview_rect.scene() is self:
                    self.removeItem(self._wall_preview_rect)
                self._wall_preview_rect = None
        # Clean up floor drawing state (unified: polygon + rect share "floor")
        if mode != "floor":
            if self._floor_active is not None:
                if len(self._floor_active._points) < 3:
                    if self._floor_active.scene() is self:
                        self.removeItem(self._floor_active)
                    if self._floor_active in self._floor_slabs:
                        self._floor_slabs.remove(self._floor_active)
                self._floor_active = None
            # Rect-floor state (anchor / rotate step / previews / ref guides).
            self._floor_rect_anchor = None
            self._floor_rect_rotating = False
            self._floor_rect_sized_pt1 = None
            self._floor_rect_sized_pt2 = None
            self._floor_rect_pivot = None
            self._clear_floor_rect_ref_lines()
            if self._floor_rect_preview is not None:
                if self._floor_rect_preview.scene() is self:
                    self.removeItem(self._floor_rect_preview)
                self._floor_rect_preview = None
        if mode != "wall":
            self._wall_rect_anchor = None
            self._wall_rect_rotating = False
            self._wall_rect_sized_pt1 = None
            self._wall_rect_sized_pt2 = None
            self._wall_rect_pivot = None
            self._clear_wall_rect_ref_lines()
            if self._wall_rect_preview is not None:
                if self._wall_rect_preview.scene() is self:
                    self.removeItem(self._wall_rect_preview)
                self._wall_rect_preview = None
            if self._wall_rect_thickness_preview is not None:
                if self._wall_rect_thickness_preview.scene() is self:
                    self.removeItem(self._wall_rect_thickness_preview)
                self._wall_rect_thickness_preview = None
        # Clean up roof drawing state
        if mode != "roof":
            if self._roof_active is not None:
                if len(self._roof_active._points) < 3:
                    if self._roof_active.scene() is self:
                        self.removeItem(self._roof_active)
                    if self._roof_active in self._roofs:
                        self._roofs.remove(self._roof_active)
                self._roof_active = None
        if mode != "roof_rect":
            self._roof_rect_anchor = None
            if self._roof_rect_preview is not None:
                if self._roof_rect_preview.scene() is self:
                    self.removeItem(self._roof_rect_preview)
                self._roof_rect_preview = None

        # Clean up manual room drawing state
        if mode != "room_manual":
            if self._room_manual_active is not None:
                if len(self._room_manual_active._boundary) < 3:
                    if self._room_manual_active.scene() is self:
                        self.removeItem(self._room_manual_active)
                    if self._room_manual_active in self._rooms:
                        self._rooms.remove(self._room_manual_active)
                self._room_manual_active = None

        # ── Opening placement (§7.6) ─────────────────────────────────────────
        # Entering "opening" arms the placement template (Feature id + the
        # pre-commit cycle state) and clears any leftover ghost.  Leaving it
        # tears the ghost down so it never strands on the canvas.
        if mode == "opening":
            # Accept either a WallOpening TEMPLATE object (the pre-placement
            # property template — the new pattern) or a bare feature-id string
            # (legacy call sites / tests).  A string is adopted onto the
            # persistent template so there is always one source of truth.
            if isinstance(template, WallOpening):
                self.current_template = template
            else:
                feature_id = template or DEFAULT_FEATURE_FOR_TYPE["door"]
                self.current_template = WallOpening(feature_id=feature_id)
            tmpl = self.current_template
            tmpl._scene_ref = self
            # Mirror the template's placement state onto the scene fields the
            # cycle keys / ghost read (kept in sync both ways below).
            self._opening_feature_id = tmpl.feature_id
            self._opening_alignment = tmpl.alignment
            self._opening_mirror_hinge = tmpl.mirror_hinge
            self._opening_mirror_facing = tmpl.mirror_facing
            # Surface the template in the right-side property panel so the user
            # can edit Sill / size / orientation BEFORE placing.
            self.requestPropertyUpdate.emit(tmpl)
        if mode != "opening":
            self._clear_opening_ghost()

        # Clean up place_import transient state (owned by the controller).
        if mode != "place_import":
            self._underlay_ctl.clear()

        # Clean up interactive transforms
        def _remove_preview(attr):
            item = getattr(self, attr, None)
            if item is not None:
                if item.scene() is self:
                    self.removeItem(item)
                setattr(self, attr, None)

        if mode != "rotate":
            self._rotate_pivot = None
            _remove_preview("_rotate_preview_line")
        if mode != "scale":
            self._scale_base = None
            _remove_preview("_scale_preview_line")
        if mode != "mirror":
            self._mirror_p1 = None
            _remove_preview("_mirror_preview_line")
        if mode != "break":
            self._break_target = None
            self._break_p1 = None
            _remove_preview("_break_highlight")
        if mode != "break_at_point":
            self._break_at_target = None
            _remove_preview("_break_at_highlight")
        if mode != "fillet":
            self._fillet_item1 = None
            self._fillet_item2 = None
            _remove_preview("_fillet_highlight1")
            _remove_preview("_fillet_highlight2")
            _remove_preview("_fillet_preview")
        if mode != "chamfer":
            self._chamfer_item1 = None
            self._chamfer_item2 = None
            _remove_preview("_chamfer_highlight1")
            _remove_preview("_chamfer_highlight2")
            _remove_preview("_chamfer_preview")
        if mode != "stretch":
            self._stretch_vertices = []
            self._stretch_full_items = []
            self._stretch_base = None
            _remove_preview("_stretch_preview_line")
        if mode != "detail":
            self._detail_rect_anchor = None
            if self._detail_rect_preview is not None:
                if self._detail_rect_preview.scene() is self:
                    self.removeItem(self._detail_rect_preview)
                self._detail_rect_preview = None

        # Capture current selection when entering move/rotate/scale mode from ribbon
        if mode in ("move", "rotate", "scale") and not self._selected_items:
            self._selected_items = list(self.selectedItems())

        # Clear OSNAP snap trace whenever mode changes
        self._snap_result = None
        for v in self.views():
            v.viewport().update()

        # Emit initial step instruction for this mode
        _initial_steps = {
            "select":         "Select items to edit",
            "pipe":           "Pick start node",
            "sprinkler":      "Click a node or pipe to place sprinkler",
            "draw_line":      "Pick first point",
            "draw_rectangle": "Pick first corner",
            "draw_circle":    "Pick center point",
            "draw_arc":       "Pick center point",
            "polyline":       "Pick first point",
            "dimension":      "Pick first point",
            "text":           "Pick first corner",
            "set_scale":      "Pick first calibration point",
            "move":           "Pick base point",
            "offset":         "Click geometry to offset",
            "design_area":    "Click sprinklers to toggle. Shift+click for rectangle. Right-click to confirm; the next click starts a new area.",
            "water_supply":   "Click to place water supply",
            "paste":          "Click to place pasted items",
            "draw_gridline":  "Pick start point",
            "trim":           "Select cutting edge",
            "trim_pick":      "Click segment to trim (right-click to cancel)",
            "extend":         "Select boundary edge",
            "extend_pick":    "Click near endpoint to extend (right-click to cancel)",
            "merge_points":   "Click first endpoint",
            "constraint_concentric":   "Select first circle",
            "constraint_dimensional":  "Click first grip point",
            "align": "Click reference edge",
            "rotate":          "Pick pivot point",
            "scale":           "Pick base point (Tab = enter factor)",
            "mirror":          "Pick first axis point",
            "break":           "Select object to break",
            "break_at_point":  "Select object to split",
            "fillet":          "Click first object",
            "chamfer":         "Click first object",
            "stretch":         "Draw crossing window (right-to-left)",
            "wall":            "Pick wall start point",
            "floor":           "Pick first point",
            "room":            "Click inside a closed wall region",
            "room_manual":     "Pick first room boundary point",
            "opening":         "Click on a wall to place an opening",
            "door":            "Click on a wall to place door",
            "window":          "Click on a wall to place window",
            "detail":          "Pick first corner for detail view boundary",
            "polygon":         None,   # emitted with live readout below
        }
        instr = _initial_steps.get(mode, "")
        if mode == "wall":
            self.instructionChanged.emit(
                f"Pick wall start point [{self._wall_alignment}]")
        elif mode == "polygon":
            self.instructionChanged.emit(
                f"Pick centre point  |  {self._polygon_readout()}")
        elif instr:
            self.instructionChanged.emit(instr)

        # Multi-variant tools (arc, rectangle) re-apply their session-sticky
        # variant on entry and overwrite the plain instruction above with the
        # hinted step-0 readout ("<label> (←/→ to change): …").  Runs *after*
        # this mode's state reset (above) so the variant flag it sets is not
        # clobbered.  No-op for non-variant modes, so their plain instruction
        # stands.
        if mode in self._PLACEMENT_VARIANTS:
            self._apply_current_variant()

        # Populate the Properties dock with the gridline placement template so
        # the user can preset Bubble Offsets / Locked / visibility before
        # placing.  Mirrors how pipe/sprinkler modes emit their template at
        # set_mode time (line ~850 above).
        if mode == "draw_gridline":
            self.requestPropertyUpdate.emit(self._get_gridline_template())

        # Hand keyboard focus back to the canvas.  A tool is usually activated by
        # clicking its ribbon button, which leaves focus on the ribbon — so
        # step-0 keyboard input (←/→ variant cycle, and any pre-first-click key)
        # would be eaten by ribbon focus-navigation and never reach
        # ``keyPressEvent``.  Focus the *visible* view (not ``views()[0]``, which
        # is the never-shown orphan); a no-op headless, where nothing is visible.
        view = self._visible_view()
        if view is not None:
            view.setFocus(Qt.FocusReason.OtherFocusReason)

    @staticmethod
    def _repair_display_settings():
        """Fix display/*/visible values stored as bool instead of string.

        QSettings on Windows can round-trip bools inconsistently. This ensures
        all visibility flags are stored as ``"true"``/``"false"`` strings.
        """
        from .display_manager import _CATEGORIES
        from PyQt6.QtCore import QSettings
        settings = QSettings("GV", "FirePro3D")
        repaired = False
        for cat in _CATEGORIES:
            key = cat["key"]
            for prefix in ("", "default_"):
                skey = f"display/{key}/{prefix}visible"
                val = settings.value(skey)
                if val is None:
                    continue
                # Fix bools stored by older code — force to "true" string
                # (a bool False here is a bug, not an intentional hide)
                if isinstance(val, bool):
                    settings.setValue(skey, "true")
                    repaired = True
                elif isinstance(val, str) and val.lower() == "false":
                    # Check against the factory default — if the factory
                    # default is True, this False was likely a bug too.
                    factory_vis = cat.get("visible", True)
                    if factory_vis:
                        settings.setValue(skey, "true")
                        repaired = True
        if repaired:
            settings.sync()

    # -------------------------------------------------------------------------
    # NODE / PIPE / SPRINKLER MANAGEMENT

    def _get_active_view_range(self):
        """Return (view_depth, view_height) for the active level, or None."""
        pvm = self._plan_view_manager
        if pvm is None:
            return None
        pv = pvm.get(f"Plan: {self.active_level}")
        if pv is None:
            return None
        return (pv.view_depth, pv.view_height)

    def find_nearby_node(self, x, y, z_hint=None):
        return self._pipe_ctl.find_nearby_node(x, y, z_hint=z_hint)

    def find_nearby_candidates(self, x, y, z_hint=None):
        return self._pipe_ctl.find_nearby_candidates(x, y, z_hint=z_hint)

    def _update_pipe_tab_candidates(self, scene_pos, z_hint=None):
        return self._pipe_ctl._update_pipe_tab_candidates(scene_pos, z_hint=z_hint)

    def _emit_pipe_tab_readout(self):
        return self._pipe_ctl._emit_pipe_tab_readout()

    def find_or_create_node(self, x, y, z_hint=None):
        return self._pipe_ctl.find_or_create_node(x, y, z_hint=z_hint)

    def add_node(self, x, y, z_hint=None):
        return self._pipe_ctl.add_node(x, y, z_hint=z_hint)

    def remove_node(self, n):
        return self._pipe_ctl.remove_node(n)

    @staticmethod
    def _apply_fitting_dm_colors(fitting):
        return PipeNetworkController._apply_fitting_dm_colors(fitting)

    def add_pipe(self, n1, n2, template=None, _propagate_ceiling=True):
        return self._pipe_ctl.add_pipe(n1, n2, template=template,
                                       _propagate_ceiling=_propagate_ceiling)

    def _validate_4th_branch(self, node, new_pt: QPointF) -> str | None:
        return self._pipe_ctl._validate_4th_branch(node, new_pt)

    def _would_backtrack(self, start_node, end_node) -> bool:
        return self._pipe_ctl._would_backtrack(start_node, end_node)

    def _would_backtrack_at(self, start_node, target_pt: QPointF) -> bool:
        return self._pipe_ctl._would_backtrack_at(start_node, target_pt)

    def _try_extend_collinear(self, start_node, end_node, template) -> bool:
        return self._pipe_ctl._try_extend_collinear(start_node, end_node, template)

    def _convert_45_elbow_to_wye(self, junction_node, template):
        return self._pipe_ctl._convert_45_elbow_to_wye(junction_node, template)

    # ── Vertical pipe helpers ─────────────────────────────────────────────

    def _compute_template_z_pos(self, template, node_idx: int = 1) -> float | None:
        return self._pipe_ctl._compute_template_z_pos(template, node_idx)

    def _make_intermediate_node(self, existing_node, template):
        return self._pipe_ctl._make_intermediate_node(existing_node, template)

    def _make_intermediate_node_for_n2(self, existing_node, template):
        return self._pipe_ctl._make_intermediate_node_for_n2(existing_node, template)

    def _create_vertical_connection(self, start_node, existing_end_node, template):
        return self._pipe_ctl._create_vertical_connection(start_node, existing_end_node, template)

    def _find_or_split_vertical_at_z(self, xy_pos: QPointF,
                                      target_z: float,
                                      template) -> "Node | None":
        return self._pipe_ctl._find_or_split_vertical_at_z(xy_pos, target_z, template)

    def _split_vertical_pipe(self, pipe, target_z, template):
        return self._pipe_ctl._split_vertical_pipe(pipe, target_z, template)

    # ── End vertical pipe helpers ─────────────────────────────────────────

    def split_pipe(self, pipe, split_point):
        return self._pipe_ctl.split_pipe(pipe, split_point)

    def delete_pipe(self, pipe):
        return self._pipe_ctl.delete_pipe(pipe)

    def add_sprinkler(self, n, template=None):
        return self._spr_ctl.add_sprinkler(n, template=template)

    def remove_sprinkler(self, n):
        return self._spr_ctl.remove_sprinkler(n)

    # ── Auto-populate room with sprinklers ─────────────────────────────────

    def auto_populate_room(self, room, positions, sprinkler_record,
                           level, ceiling_level, sprinkler_offset,
                           design_density="0.10"):
        return self._spr_ctl.auto_populate_room(
            room, positions, sprinkler_record, level, ceiling_level,
            sprinkler_offset, design_density=design_density)

    # -------------------------------------------------------------------------
    # UNDERLAYS — IMPORT

    # ─────────────────────────────────────────────────────────────────────────
    # PREVIEW-FIRST IMPORT (place_import mode)
    # ─────────────────────────────────────────────────────────────────────────

    def begin_place_import(self, *args, **kwargs):
        return self._underlay_ctl.begin_place_import(*args, **kwargs)

    def _commit_place_import(self, *args, **kwargs):
        return self._underlay_ctl._commit_place_import(*args, **kwargs)

    def import_dxf(self, *args, **kwargs):
        return self._underlay_ctl.import_dxf(*args, **kwargs)

    def import_pdf(self, *args, **kwargs):
        return self._underlay_ctl.import_pdf(*args, **kwargs)

    def _build_batched_underlay_group(self, *args, **kwargs):
        return self._underlay_ctl._build_batched_underlay_group(*args, **kwargs)

    def _attach_snap_index(self, *args, **kwargs):
        return self._underlay_ctl._attach_snap_index(*args, **kwargs)

    def _import_pdf_vectors(self, *args, **kwargs):
        return self._underlay_ctl._import_pdf_vectors(*args, **kwargs)

    @staticmethod
    def _append_geom_to_path(path, g):
        # Static shell: the original was a @staticmethod called as
        # Model_Space._append_geom_to_path(path, g); delegate to the controller's.
        return UnderlayController._append_geom_to_path(path, g)

    # -------------------------------------------------------------------------
    # UNDERLAYS — MANAGEMENT (moved to UnderlayController C2b; thin shells)

    def _apply_underlay_display(self, *args, **kwargs):
        return self._underlay_ctl._apply_underlay_display(*args, **kwargs)

    def _apply_underlay_hidden_layers(self, *args, **kwargs):
        return self._underlay_ctl._apply_underlay_hidden_layers(*args, **kwargs)

    def _create_underlay_placeholder(self, *args, **kwargs):
        return self._underlay_ctl._create_underlay_placeholder(*args, **kwargs)

    def find_underlay_for_item(self, *args, **kwargs):
        return self._underlay_ctl.find_underlay_for_item(*args, **kwargs)

    def remove_underlay(self, *args, **kwargs):
        return self._underlay_ctl.remove_underlay(*args, **kwargs)

    def refresh_underlay(self, *args, **kwargs):
        return self._underlay_ctl.refresh_underlay(*args, **kwargs)

    def refresh_all_underlays(self, *args, **kwargs):
        return self._underlay_ctl.refresh_all_underlays(*args, **kwargs)

    def replace_underlay(self, *args, **kwargs):
        return self._underlay_ctl.replace_underlay(*args, **kwargs)

    def begin_replace_underlay_placement(self, *args, **kwargs):
        return self._underlay_ctl.begin_replace_underlay_placement(*args, **kwargs)

    def abort_underlay_freeze(self):
        """End any gesture freeze so vector underlay painting resumes now.

        Called defensively by every underlay mutation site, level passes,
        fit-to-screen and the paper render path (spec §18). No-op when no
        freeze is active.
        """
        self._underlay_freeze.abort()

    def repen_underlay(self, *args, **kwargs):
        return self._underlay_ctl.repen_underlay(*args, **kwargs)

    def set_underlay_layer_hidden(self, *args, **kwargs):
        return self._underlay_ctl.set_underlay_layer_hidden(*args, **kwargs)

    # -------------------------------------------------------------------------
    # UNDO / REDO

    def _capture_network(self) -> dict:
        """Serialize nodes/pipes/annotations to a dict (no underlays/scale)."""
        node_list = list(self.sprinkler_system.nodes)
        node_id = {n: i for i, n in enumerate(node_list)}
        nodes_data = [serialize_node(node, node_id) for node in node_list]
        pipes_data = []
        for pipe in self.sprinkler_system.pipes:
            if pipe.node1 is None or pipe.node2 is None:
                continue
            if pipe.node1 not in node_id or pipe.node2 not in node_id:
                continue
            pipes_data.append(serialize_pipe(pipe, node_id))
        annotations_data = []
        for dim in self.annotations.dimensions:
            annotations_data.append(serialize_dimension(dim))
        for note in self.annotations.notes:
            annotations_data.append(serialize_note(note))
        ws = self.water_supply_node
        ws_data = serialize_water_supply(ws) if ws is not None else None
        # Design areas
        da_data = [
            serialize_design_area(da, node_id, self.active_design_area)
            for da in self.design_areas
        ]
        return {
            "nodes":              nodes_data,
            "pipes":              pipes_data,
            "annotations":        annotations_data,
            "water_supply":       ws_data,
            "design_areas":       da_data,
            # ── Draw geometry ──────────────────────────────────────────────
            "polylines":          [pl.to_dict() for pl in self._polylines],
            "draw_lines":         [l.to_dict()  for l in self._draw_lines],
            "draw_rectangles":    [r.to_dict()  for r in self._draw_rects],
            "draw_circles":       [c.to_dict()  for c in self._draw_circles],
            "draw_arcs":          [a.to_dict()  for a in self._draw_arcs],
            "polygons":           [p.to_dict()  for p in self._draw_polygons],
            "gridlines":          [gl.to_dict() for gl in self._gridlines],
            # ── Walls & Floors ────────────────────────────────────────────
            "walls":              [w.to_dict()  for w in self._walls],
            "floor_slabs":        [fs.to_dict() for fs in self._floor_slabs],  # two-boundary schema via to_dict (parity w/ scene_io)
            "roofs":              [r.to_dict()  for r in self._roofs],
            "rooms":              [r.to_dict()  for r in self._rooms],
            "constraints":        self._capture_constraints(),
        }

    def _capture_constraints(self) -> list[dict]:
        """Serialize constraints for undo/save, using geometry-list index IDs."""
        all_geom = self._tools._all_geometry_items()
        geom_id = {item: i for i, item in enumerate(all_geom)}
        result = []
        for c in self._constraints:
            try:
                result.append(c.to_dict(geom_id))
            except (KeyError, AttributeError):
                pass
        return result

    def _restore_network(self, state: dict):
        """Restore nodes/pipes/annotations from a dict (keeps underlays and scale)."""
        self._in_undo_restore = True
        try:
            for pipe in list(self.sprinkler_system.pipes):
                # Remove top-level label from scene
                if hasattr(pipe, "label") and pipe.label is not None:
                    try:
                        self.removeItem(pipe.label)
                    except (RuntimeError, ValueError):
                        pass
                # Remove top-level riser symbol from scene
                if hasattr(pipe, "_riser_symbol") and pipe._riser_symbol is not None:
                    try:
                        self.removeItem(pipe._riser_symbol)
                    except (RuntimeError, ValueError):
                        pass
                if pipe.scene() is self:
                    self.removeItem(pipe)
            for node in list(self.sprinkler_system.nodes):
                if node.scene() is self:
                    self.removeItem(node)
            for dim in list(self.annotations.dimensions):
                if dim.scene() is self:
                    self.removeItem(dim)
            for note in list(self.annotations.notes):
                if note.scene() is self:
                    self.removeItem(note)
            # Remove old water supply if present
            if self.water_supply_node and self.water_supply_node.scene() is self:
                self.removeItem(self.water_supply_node)
            self.water_supply_node = None
            # Remove old design areas
            for da in self.design_areas:
                if da.scene() is self:
                    self.removeItem(da)
            self.design_areas = []
            self.active_design_area = None
            self.sprinkler_system = SprinklerSystem()
            self.annotations = Annotation()

            from .network_codec import deserialize_node
            id_to_node: dict[int, Node] = {}
            for entry in state.get("nodes", []):
                id_to_node[entry["id"]] = deserialize_node(self, entry)

            from .network_codec import deserialize_pipe
            for entry in state.get("pipes", []):
                deserialize_pipe(self, entry, id_to_node)

            for node in id_to_node.values():
                node.fitting.update()
                pending = getattr(node, "_fitting_display_overrides_pending", {})
                if pending:
                    node.fitting._display_overrides = pending
                    del node._fitting_display_overrides_pending
                # Apply DM colours without re-aligning (align was done by update)
                self._apply_fitting_dm_colors(node.fitting)

            from .network_codec import deserialize_dimension, deserialize_note
            for entry in state.get("annotations", []):
                ann_type = entry.get("type")
                if ann_type == "dimension":
                    deserialize_dimension(self, entry)
                elif ann_type == "note":
                    deserialize_note(self, entry)

            # Restore water supply
            ws_data = state.get("water_supply")
            if ws_data:
                from .network_codec import deserialize_water_supply
                deserialize_water_supply(self, ws_data)

            # Restore design areas
            from .network_codec import deserialize_design_area
            for da_entry in state.get("design_areas", []):
                da = deserialize_design_area(self, da_entry, id_to_node)
                apply_category_defaults(da)  # Class-A display tail (undo self-contained)
                # Tiles recomputed after walls & rooms restore below

            # ── Draw geometry ──────────────────────────────────────────────
            # Remove existing items from scene and lists
            for pl in list(self._polylines):
                if pl.scene() is self:
                    self.removeItem(pl)
            self._polylines.clear()

            for item in list(self._draw_lines):
                if item.scene() is self:
                    self.removeItem(item)
            self._draw_lines.clear()

            for item in list(self._draw_rects):
                if item.scene() is self:
                    self.removeItem(item)
            self._draw_rects.clear()

            for item in list(self._draw_circles):
                if item.scene() is self:
                    self.removeItem(item)
            self._draw_circles.clear()

            for item in list(self._draw_arcs):
                if item.scene() is self:
                    self.removeItem(item)
            self._draw_arcs.clear()

            for item in list(self._draw_polygons):
                if item.scene() is self:
                    self.removeItem(item)
            self._draw_polygons.clear()

            for gl in list(self._gridlines):
                if gl.scene() is self:
                    self.removeItem(gl)
            self._gridlines.clear()

            for w in list(self._walls):
                for op in w.openings:
                    if op.scene() is self:
                        self.removeItem(op)
                if w.scene() is self:
                    self.removeItem(w)
            self._walls.clear()

            for fs in list(self._floor_slabs):
                if fs.scene() is self:
                    self.removeItem(fs)
            self._floor_slabs.clear()

            for r in list(self._roofs):
                if r.scene() is self:
                    self.removeItem(r)
            self._roofs.clear()

            for rm in list(self._rooms):
                if rm.scene() is self:
                    self.removeItem(rm)
            self._rooms.clear()

            # Clear padlocks
            for p in self._align_padlocks:
                if p.scene() is self:
                    self.removeItem(p)
            self._align_padlocks.clear()

            self._constraints.clear()

            # Restore from snapshot
            for d in state.get("polylines", []):
                pl = PolylineItem.from_dict(d)
                self.addItem(pl)
                self._polylines.append(pl)

            for d in state.get("draw_lines", []):
                li = LineItem.from_dict(d)
                self.addItem(li)
                self._draw_lines.append(li)

            for d in state.get("draw_rectangles", []):
                ri = RectangleItem.from_dict(d)
                self.addItem(ri)
                self._draw_rects.append(ri)

            for d in state.get("draw_circles", []):
                ci = CircleItem.from_dict(d)
                self.addItem(ci)
                self._draw_circles.append(ci)

            for d in state.get("draw_arcs", []):
                ai = ArcItem.from_dict(d)
                self.addItem(ai)
                self._draw_arcs.append(ai)

            for d in state.get("polygons", []):
                pg = RegularPolygonItem.from_dict(d)
                self.addItem(pg)
                self._draw_polygons.append(pg)

            for d in state.get("gridlines", []):
                gl = GridlineItem.from_dict(d)
                self.addItem(gl)
                self._gridlines.append(gl)
            sync_grid_counters(self._gridlines)
            apply_duplicate_warnings(self._gridlines)

            # ── Walls & Floors ────────────────────────────────────────────
            for d in state.get("walls", []):
                wall = WallSegment.from_dict(d)
                self.addItem(wall)
                self._walls.append(wall)
                for op_data in d.get("openings", []):
                    op = WallOpening.from_dict(op_data, wall=wall)
                    wall.openings.append(op)
                    self.addItem(op)

            for d in state.get("floor_slabs", []):
                slab = FloorSlab.from_dict(d)
                self.addItem(slab)
                self._floor_slabs.append(slab)

            for d in state.get("roofs", []):
                roof = RoofItem.from_dict(d)
                self.addItem(roof)
                self._roofs.append(roof)

            for d in state.get("rooms", []):
                room = Room.from_dict(d)
                room._scale_manager_ref = self.scale_manager
                self.addItem(room)
                self._rooms.append(room)

            # Recompute auto-name counters (parity with load_from_file) so the
            # next auto-name doesn't skip a number after an undo.
            self._recalc_name_counters()

            # ── Design-area tiles (now that walls & rooms exist) ──────────
            for da in self.design_areas:
                da.compute_area(self.scale_manager)

            # ── Constraints ───────────────────────────────────────────────
            all_geom = self._tools._all_geometry_items()
            id_to_geom = {i: item for i, item in enumerate(all_geom)}
            for d in state.get("constraints", []):
                try:
                    c = ConstraintBase.from_dict(d, id_to_geom)
                    if c is not None:
                        self._constraints.append(c)
                except (ValueError, KeyError, TypeError):
                    pass  # skip malformed constraint data

            # Re-apply display settings (category defaults + per-item overrides)
            from .display_manager import apply_saved_display_settings
            apply_saved_display_settings(self)

            # Re-apply level visibility
            if self._level_manager:
                self._level_manager.apply_to_scene(self)

        finally:
            self._in_undo_restore = False

    def push_undo_state(self):
        """Snapshot current network state onto the undo stack."""
        if self._in_undo_restore:
            return
        state = self._capture_network()
        # Discard redo history beyond current position
        self._undo_stack = self._undo_stack[:self._undo_pos + 1]
        self._undo_stack.append(state)
        if len(self._undo_stack) > self.UNDO_MAX:
            self._undo_stack.pop(0)
        self._undo_pos = len(self._undo_stack) - 1
        # ALIGN acquisitions are per-placement tracking aids: reset them once a
        # placement commits.  push_undo_state is the single funnel every committed
        # placement passes through, so this clears the acquire set after each
        # element (matches AutoCAD OTRACK, which drops acquired points per picked
        # point) even in continuous modes that stay armed.  No-op when nothing is
        # acquired, so non-placement mutations are unaffected.
        ctrl = getattr(self, "_align_controller", None)
        if ctrl is not None and ctrl.acquired:
            ctrl.clear()
            self._align_last_move_ns = None
            self._align_anchor_dir = None
        self.sceneModified.emit()

    def undo(self):
        """Restore the previous network state."""
        self._underlay_freeze.abort()   # spec §18: never restore under a stale blit
        if self._undo_pos > 0:
            self._undo_pos -= 1
            self._restore_network(self._undo_stack[self._undo_pos])
            sync_grid_counters(self._gridlines)
            apply_duplicate_warnings(self._gridlines)
            # Refresh property panel and model browser — old references invalid
            self.requestPropertyUpdate.emit(None)
            self.sceneModified.emit()

    def redo(self):
        """Restore the next network state."""
        self._underlay_freeze.abort()   # spec §18: never restore under a stale blit
        if self._undo_pos < len(self._undo_stack) - 1:
            self._undo_pos += 1
            self._restore_network(self._undo_stack[self._undo_pos])
            sync_grid_counters(self._gridlines)
            apply_duplicate_warnings(self._gridlines)
            # Refresh property panel and model browser — old references invalid
            self.requestPropertyUpdate.emit(None)
            self.sceneModified.emit()

    # -------------------------------------------------------------------------
    # SCALE REFRESH

    def _refresh_all_scales(self):
        """Refresh visual sizes of all pipes, nodes, sprinklers, and fittings
        after a scale calibration change, then refresh all labels."""
        sm = self.scale_manager
        for pipe in self.sprinkler_system.pipes:
            pipe.update()       # triggers repaint with new scale-aware line weight
            pipe.update_label()
        for node in self.sprinkler_system.nodes:
            node.update()
            if node.has_sprinkler():
                node.sprinkler.rescale(sm)
            if node.has_fitting() and node.fitting.symbol is not None:
                node.fitting.rescale(sm)
                node.fitting.update()
        for dim in self.annotations.dimensions:
            dim.rescale(sm)
        if self.water_supply_node is not None:
            self.water_supply_node.rescale(sm)

    def _refresh_all_labels(self):
        """Refresh display text on all pipes and dimension annotations."""
        for pipe in self.sprinkler_system.pipes:
            pipe.update_label()
        for dim in self.annotations.dimensions:
            dim.update_label()

    def set_display_unit(self, unit):
        """Change the display unit and refresh all labels."""
        self.scale_manager.display_unit = unit
        self._refresh_all_labels()

    # -------------------------------------------------------------------------
    # Design area backward-compat property

    @property
    def design_area_sprinklers(self) -> list:
        """Return sprinklers from the active design area (backward compat)."""
        if self.active_design_area:
            return list(self.active_design_area.sprinklers)
        return []

    # -------------------------------------------------------------------------
    # HYDRAULICS

    def run_hydraulics(self, design_sprinklers=None):
        return self._spr_ctl.run_hydraulics(design_sprinklers=design_sprinklers)

    def clear_hydraulics(self):
        return self._spr_ctl.clear_hydraulics()

    def set_coverage_overlay(self, visible: bool):
        return self._spr_ctl.set_coverage_overlay(visible)

    # -------------------------------------------------------------------------
    # GEOMETRY HELPERS

    def get_snapped_position(self, x, y):
        grid = 1
        return QPointF(round(x / grid) * grid, round(y / grid) * grid)

    def get_effective_position(self, scene_pos: QPointF) -> QPointF:
        """Return best-fit cursor position: OSNAP > underlay snap > grid snap."""
        # Design-area picking snaps to sprinkler centres ONLY: general
        # OSNAP/underlay/grid snapping would drag clicks onto gridlines and
        # walls, but sprinkler node centres still snap (with a marker) so
        # picks have a visible target.
        if self.mode == "design_area":
            active = getattr(self, "active_level", DEFAULT_LEVEL)
            _view = self._snap_view()
            xform = _view.transform() if _view is not None else QTransform()
            sprinkler_nodes = {
                spr.node for spr in self.sprinkler_system.sprinklers
                if spr.node is not None
                and getattr(spr.node, "level", DEFAULT_LEVEL) == active
            }
            _was_enabled = self._snap_engine.enabled
            _was_center = self._snap_engine.snap_center
            self._snap_engine.enabled = True
            self._snap_engine.snap_center = True
            try:
                result = self._snap_engine.find(
                    scene_pos, self, xform,
                    only_types={"center"},
                    item_filter=lambda it: it in sprinkler_nodes,
                    held=self._snap_result)
            finally:
                self._snap_engine.enabled = _was_enabled
                self._snap_engine.snap_center = _was_center
            if result is not None:
                self._snap_result = result
                self._align_result = None
                return result.point
            self._snap_result = None
            self._align_result = None
            return QPointF(scene_pos)

        # SNAP takes highest priority (disabled when no mode or select mode,
        # but enabled during grip-drag even in select mode)
        if (self._snap_enabled
                and self.mode is not None
                and (self.mode != "select" or self._grip_dragging)):
            exclude = self._grip_item if self._grip_dragging else None
            _view = self._snap_view()
            if _view is not None:
                result = self._snap_engine.find(
                    scene_pos, self, _view.transform(), exclude=exclude,
                    held=self._snap_result)
                self._snap_result = result
                if result is not None:
                    self._align_result = None
                    return result.point
            else:
                self._snap_result = None
        else:
            self._snap_result = None

        # ── ALIGN acquire-and-track (weak snap, below real SNAP) ─────────
        # The controller holds the acquired set (fed on move by the dwell
        # machine); each frame it emits the transient tracking [Ray]s (acquired
        # H/V + extension + parallel, plus the auto-acquired active anchor).
        # Those rays enter the ONE picker via find(align_paths=…) at ALIGN
        # priority (below every real snap); a hit projects the cursor onto the
        # path / crossing.
        if self._align_enabled and self._align_active_item is not None:
            _view = self._snap_view()
            if _view is not None:
                self._align_controller.set_active_anchor(
                    self._align_anchor_point(), self._align_anchor_direction())
                # Parallel guide anchoring: once a placement FROM-point exists it
                # anchors THERE (fixed, so the cursor can snap onto it); before
                # the first point there is none, so it falls back to the cursor —
                # a moving preview that confirms the direction was acquired. Use
                # the raw per-mode anchor (not get_placement_anchor, which the
                # track schema masks with the ray origin).
                _anchor = self._mode_placement_anchor()
                parallel_origin = ((_anchor.x(), _anchor.y())
                                   if _anchor is not None
                                   else (scene_pos.x(), scene_pos.y()))
                rays = self._align_controller.build_rays(parallel_origin)
                if rays:
                    res = self._snap_engine.find(
                        scene_pos, self, _view.transform(),
                        align_paths=rays, held=self._align_result,
                        align_aperture_px=self._align_path_tol_px)
                    self._align_result = res
                    if (res is not None
                            and res.snap_type in ("align_intersection",
                                                  "align_path")):
                        # Navigate (D4): a single-path soft-snap arms the
                        # ``track`` schema so typing a Distance places along the
                        # path.  The picker returns the foot point but not the
                        # winning Ray, so recover it from ``rays`` (still held
                        # here) — the ray whose projection of the foot has ~0
                        # perpendicular error.  An ``align_intersection`` is a
                        # fixed crossing with no single direction, so it gets no
                        # distance field: clear the arm and leave the primitive
                        # schema live.
                        if res.snap_type == "align_path":
                            self._arm_align_track(rays, res.point)
                        else:
                            self._align_track_ray = None
                        return res.point
                    self._align_track_ray = None
                else:
                    self._align_result = None
                    self._align_track_ray = None
        else:
            self._align_result = None
            self._align_track_ray = None
        return self.get_snapped_position(scene_pos.x(), scene_pos.y())

    def _align_anchor_point(self):
        """The current placement FROM-point as an (x, y) tuple, or None.

        The active placement anchor auto-acquires an H/V pair (design spec D3):
        it is the point the user is drawing *from*, so lining up with it is
        always wanted.  Uses :meth:`_mode_placement_anchor` (the *raw* per-mode
        anchor), NOT :meth:`get_placement_anchor` — the latter is masked by the
        ``track`` schema to return the tracking ray's origin, which is non-None
        even before a first point is placed.  Feeding that to the auto-anchor
        would pin an H/V pair to the moving cursor (a parallel preview trivially
        self-snaps → track swap → ray origin = cursor), painting stray H/V lines
        anchored to nothing real.  The auto-anchor is the *real* from-point:
        None until the first click, then the clicked point.
        """
        a = self._mode_placement_anchor()
        return None if a is None else (a.x(), a.y())

    def _align_anchor_direction(self):
        """Direction the auto-acquired anchor extends along, or None (spec D3).

        The unit direction of the directional object the FIRST placement point
        landed on, captured at the arming click (``mousePressEvent``) in
        ``self._align_anchor_dir``.  When non-None, the controller's
        ``set_active_anchor(point, direction)`` gives the anchor an Extension
        ray so the user can extend end-to-end at the existing angle (continue a
        wall/line collinearly).  ``None`` when the first point started in empty
        space or on a non-directional point — the anchor then emits H/V only.
        """
        return self._align_anchor_dir

    def _arm_align_track(self, rays, foot) -> None:
        """Recover the winning single-path Ray and arm the Navigate track state.

        The ``align_path`` picker result carries the foot point but not the
        :class:`~firepro3d.align_engine.Ray` it projected onto, so recover it
        from *rays* (the transient set the seam just built): the winning ray is
        the one whose projection of *foot* lands back on *foot* — i.e. ~0
        perpendicular error.  That ray's origin/direction drive the ``track``
        schema (``resolve_track`` places ``origin + Distance·direction``), and
        the signed distance seeds the HUD's Distance field.

        Clears the arm when no ray matches (a defensive no-match rather than a
        stale ray leaking into the schema swap).

        Args:
            rays: The transient tracking rays the seam passed to ``find``.
            foot: The ``align_path`` foot point (``OsnapResult.point``).
        """
        from .align_engine import project_to_ray
        fp = (foot.x(), foot.y())
        best = None
        best_err = None
        for ray in rays:
            proj, dist = project_to_ray(fp, ray)
            err = math.hypot(proj[0] - fp[0], proj[1] - fp[1])
            if best_err is None or err < best_err:
                best_err, best, best_dist = err, ray, dist
        # A genuine on-path foot projects back onto itself; anything above a
        # hair is not the ray the picker chose (parallel rays never tie here
        # because only one passes through the foot).
        if best is not None and best_err <= 1e-6:
            self._align_track_ray = best
            self._align_track_dist = best_dist
        else:
            self._align_track_ray = None

    def _align_track_active(self) -> bool:
        """Whether the cursor is soft-snapped to a single ALIGN path right now.

        The gate for the ``track`` schema swap: true only while the live ALIGN
        result is a single ``align_path`` *and* its winning ray was recovered.
        Keyed on ``_align_result`` (not just the cached ray) so every real-snap
        path that clears the result to None — a stronger OSNAP winning, a mode
        with no ALIGN — drops the track schema without having to also reset the
        ray, and an ``align_intersection`` (a fixed crossing, no direction)
        never trips it.  Only meaningful for a placement mode whose normal
        schema resolves to a point; :meth:`_align_track_schema` enforces that.
        """
        res = self._align_result
        return (self._align_track_ray is not None
                and res is not None
                and getattr(res, "snap_type", None) == "align_path")

    def _align_track_schema(self):
        """Return the ``track`` Schema when the on-path swap should be live, else None.

        Scoped to placement modes whose normal (non-track) schema resolves to a
        point — line/circle/rectangle-sizing and friends.  A transform mode
        (move, the gridline replicate modes) or the rectangle/polygon rotate
        step has no meaningful "distance along a path", so the swap is refused
        there and the primitive schema stays live.  The mode must also be able
        to commit a typed point (``_APPLIER_FOR_MODE``), or an engaged track HUD
        would dead-end — the same honesty gate ``_hud_available`` applies.
        """
        if not self._align_track_active():
            return None
        if self.mode not in self._APPLIER_FOR_MODE:
            return None
        base = self._base_schema()
        if base is None or not base.is_placement:
            return None
        return SCHEMAS.get("track")

    def _base_schema(self):
        """The mode's normal (non-track) schema — the primitive readout.

        Split out of :meth:`active_schema` so the track-swap gate can consult
        the primitive schema without recursing through the swap itself.
        """
        if self.mode == "draw_arc":
            return self._arc_schema_for_step()
        if self.mode == "draw_rectangle":
            return self._rectangle_schema_for_step()
        if self.mode == "polygon":
            return self._polygon_schema_for_step()
        if self.mode == "wall":
            return self._wall_schema_for_primitive()
        if self.mode == "floor":
            return self._floor_schema_for_primitive()
        key = self._SCHEMA_FOR_MODE.get(self.mode)
        return SCHEMAS.get(key) if key else None

    def _align_snap_dict(self, res):
        """Map an ``OsnapResult`` → the dict the AlignController's dwell eats.

        Returns ``{"point", "snap_type", "source_id", "direction"}`` or None
        when there is no real snap under the cursor.  ``direction`` is the unit
        direction of the source object (line/wall/pipe/polyline) so an
        endpoint acquire can spawn an Extension ray and an edge (nearest) hit a
        Parallel ray; ``None`` for point-only sources.  ``source_id`` is a
        stable identity for the source item so re-hover-release and self-
        exclusion key off it (``id(source_item)`` when present, else the snap
        type — a scene-stable fallback for synthetic intersections).
        """
        if res is None:
            return None
        src = getattr(res, "source_item", None)
        source_id = id(src) if src is not None else hash(res.snap_type)
        return {
            "point": (res.point.x(), res.point.y()),
            "snap_type": res.snap_type,
            "source_id": source_id,
            "direction": self._source_item_direction(src),
        }

    @staticmethod
    def _source_item_direction(src):
        """Unit direction of a line-like source item, or None.

        Handles the directional entity types (line / wall / pipe / polyline);
        anything else (nodes, ellipses, points) has no direction.
        """
        if src is None:
            return None
        import math as _math
        p1 = p2 = None
        # WallSegment: true centerline endpoints.
        if isinstance(src, WallSegment):
            p1, p2 = src.centerline_pt1, src.centerline_pt2
        elif isinstance(src, GridlineItem):
            p1, p2 = QPointF(src._origin), src._far_point()
        elif isinstance(src, QGraphicsLineItem):
            ln = src.line()
            p1 = src.mapToScene(ln.p1())
            p2 = src.mapToScene(ln.p2())
        if p1 is None or p2 is None:
            return None
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        n = _math.hypot(dx, dy)
        if n < 1e-9:
            return None
        return (dx / n, dy / n)

    def toggle_snap(self, enabled: bool | None = None):
        """Toggle or explicitly set SNAP.  Called from F3 shortcut and
        the status bar SNAP indicator."""
        if enabled is None:
            self._snap_enabled = not self._snap_enabled
        else:
            self._snap_enabled = bool(enabled)
        self._snap_engine.enabled = self._snap_enabled
        self._snap_result = None
        # Refresh foreground overlay
        for v in self.views():
            v.viewport().update()
        self.snapToggled.emit(self._snap_enabled)

    def set_align_enabled(self, enabled: bool | None = None):
        """Toggle or set ALIGN. Mirrors toggle_snap()."""
        if enabled is None:
            self._align_enabled = not self._align_enabled
        else:
            self._align_enabled = bool(enabled)
        self._align_result = None
        for v in self.views():
            v.viewport().update()
        self.alignToggled.emit(self._align_enabled)

    def _constrain_angle(self, anchor: QPointF, raw: QPointF) -> QPointF:
        """
        Return *raw* projected onto the nearest angle increment ray from
        *anchor*.  Increment is self._snap_angle_deg (default 45°).
        Used when the user holds Ctrl while drawing or grip-dragging.
        """
        dx = raw.x() - anchor.x()
        dy = raw.y() - anchor.y()
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return anchor
        angle = math.atan2(dy, dx)
        step = math.radians(self._snap_angle_deg)
        snapped = round(angle / step) * step
        return QPointF(anchor.x() + dist * math.cos(snapped),
                       anchor.y() + dist * math.sin(snapped))

    def get_placement_anchor(self) -> "QPointF | None":
        """Return the active placement's anchor point in scene coordinates.

        One accessor for what were six per-mode anchor variables.

        ``None`` means no placement anchor exists. Placement schemas must not
        engage without one, and callers must not paper over ``None`` by
        substituting a fallback point — doing so defeats the gate. Transform
        schemas have no anchor by nature and are gated separately.

        The returned point is always a fresh copy, so callers are free to
        mutate it; it never aliases the scene's or an item's internal state.

        Returns:
            A copy of the anchor point, or None when no anchor exists.
        """
        # On-path Navigate: the ``track`` schema measures Distance from the
        # tracking path's ORIGIN (D4), not the mode's own placement anchor, so
        # while the track swap is live the anchor is the winning ray's origin.
        # ``resolve_track(origin, {Distance, __dir__})`` then lands
        # ``origin + Distance·direction``.
        if self._align_track_schema() is not None:
            ox, oy = self._align_track_ray.origin
            return QPointF(ox, oy)
        return self._mode_placement_anchor()

    def _mode_placement_anchor(self) -> "QPointF | None":
        """The mode's *own* placement anchor, ignoring any on-path track swap.

        Split out of :meth:`get_placement_anchor` so the commit path can ask
        "does the current mode already have a first-point anchor armed?" without
        the ``track`` schema substituting the tracking ray's origin (which is
        non-None even at the first-point step, and is exactly what would mask a
        first point as a second point — BUG A).  ``get_placement_anchor``
        returns the track-ray origin while the swap is live; this returns the
        real per-mode anchor (``None`` at the first-point step).
        """
        if self.mode in ("draw_line", "draw_gridline"):
            a = self._draw_line_anchor
            return QPointF(a) if a is not None else None
        if self.mode == "draw_rectangle":
            # Sizing step: the first-click anchor.  Rotate step: the pivot the
            # rotation turns about (the first-click anchor — one of the rect's
            # corners — in corner mode, the centre in centre mode).  Both
            # variants store it in ``_draw_rect_pivot``.
            if self._draw_rect_rotating:
                p = self._draw_rect_pivot
                return QPointF(p) if p is not None else None
            a = self._draw_rect_anchor
            return QPointF(a) if a is not None else None
        if self.mode == "draw_circle":
            a = self._draw_circle_center
            return QPointF(a) if a is not None else None
        if self.mode == "polygon":
            # Both sizing and rotate steps pivot about _polygon_center.
            a = self._polygon_center
            return QPointF(a) if a is not None else None
        if self.mode == "draw_arc":
            # The anchor is the FIRST click, stored in ``_draw_arc_center`` for
            # both variants (the centre in center-first, the start point in
            # start-first).  None at step 0, before that first click.
            a = self._draw_arc_center
            return QPointF(a) if (self._draw_arc_step in (1, 2)
                                  and a is not None) else None
        if self.mode == "wall":
            if self._wall_primitive == "rect":
                # Rotate step: pivot is the anchor.
                if self._wall_rect_rotating:
                    p = self._wall_rect_pivot
                    return QPointF(p) if p is not None else None
                a = self._wall_rect_anchor
                return QPointF(a) if a is not None else None
            a = self._wall_anchor
            return QPointF(a) if a is not None else None
        if self.mode == "floor":
            if self._floor_primitive == "rect":
                # Rotate step: pivot is the anchor.
                if self._floor_rect_rotating:
                    p = self._floor_rect_pivot
                    return QPointF(p) if p is not None else None
                a = self._floor_rect_anchor
                return QPointF(a) if a is not None else None
            # Polygon: anchor is the last placed vertex (rubber-band from it).
            fa = self._floor_active
            if fa is not None and fa._points:
                return QPointF(fa._points[-1])
            return None
        if self.mode == "polyline":
            pl = self._polyline_active
            if pl is not None and pl._points:
                return QPointF(pl._points[-1])
            return None
        if self.mode in ("pipe", "move"):
            # node_start_pos holds a Node in pipe mode but a raw QPointF in
            # move mode (set_mode's cleanup relies on the same distinction).
            nsp = self.node_start_pos
            if nsp is None:
                return None
            # scenePos() is already a fresh point; the raw QPointF is stored.
            return nsp.scenePos() if isinstance(nsp, Node) else QPointF(nsp)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Published placement state (dynamic input)
    # ─────────────────────────────────────────────────────────────────────────

    # Mode → schema key.  Transform modes map here too; their appliers
    # differ but the HUD contract is identical.
    _SCHEMA_FOR_MODE = {
        "draw_line": "line",
        "draw_gridline": "line",
        "polyline": "line",
        # wall is intentionally absent — active_schema special-cases it per
        # primitive (line/polyline → ``line``, rect → ``rectangle``), mirroring
        # the draw_rectangle / draw_arc pattern.
        "pipe": "line",
        # draw_rectangle is intentionally absent — active_schema special-cases
        # it per step (sizing → ``rectangle``, rotate → ``rotation``), the same
        # way draw_arc is.
        # polygon is also intentionally absent — active_schema special-cases it
        # per step (sizing → ``polygon``, rotate → ``rotation``).
        "draw_circle": "circle",
        "move": "displacement",
        "gridline_offset": "distance",
        "gridline_array": "spacing_count",
    }

    # Mode → name of the method that applies resolved geometry.  A mode is
    # only allowed to engage the HUD if it appears here: ``_SCHEMA_FOR_MODE``
    # describes the migration's end state, but a mode whose applier has not
    # landed would open a HUD whose Enter has nowhere to go.  Entries land
    # alongside their appliers, and the two tables converge.
    _APPLIER_FOR_MODE = {
        "draw_line": "_commit_draw_line_at",
        "draw_gridline": "_commit_draw_line_at",
        "polyline": "_commit_polyline_at",
        # draw_rectangle is step-aware (like draw_arc): active_schema special-
        # cases it, and this router dispatches to the sizing-advance or the
        # rotate commit.
        "draw_rectangle": "_apply_rectangle_dynamic_input",
        "draw_circle": "_commit_draw_circle_at",
        # polygon is step-aware (like draw_rectangle): active_schema special-
        # cases it, and this router dispatches to the sizing-advance or the
        # rotate commit.
        "polygon": "_apply_polygon_dynamic_input",
        "gridline_offset": "_apply_gridline_offset",
        "gridline_array": "_apply_gridline_array",
        "move": "_apply_move_displacement",
        # draw_arc is intentionally absent from _SCHEMA_FOR_MODE — active_schema
        # special-cases it per step; this router dispatches to the step applier.
        "draw_arc": "_apply_arc_dynamic_input",
        # wall is primitive-aware (like draw_rectangle): active_schema special-
        # cases it per primitive, and this router dispatches to the same press
        # handlers the mouse uses.
        "wall": "_apply_wall_dynamic_input",
        # floor mirrors wall: primitive-aware (rect step-aware / polygon), the
        # router dispatches to the same press handlers the mouse uses.
        "floor": "_apply_floor_dynamic_input",
    }

    # Mode -> ordered placement variants: (label, first-point instruction,
    # apply_fn(self)).  ←/→ cycles them at step 0 only; the chosen index is
    # session-sticky per mode.  Adding a multi-variant tool is one row here
    # plus a step-0 predicate branch in ``_at_placement_step_zero``.
    def _init_placement_variants(self):
        """Build the placement-variant registry + the sticky per-mode index.

        Called from ``__init__``.  Each variant is
        ``(label, first-point instruction, apply_fn(self))``; ``apply_fn`` sets
        the tool's variant flag so entry and ←/→ both drive geometry through the
        same state.
        """
        self._PLACEMENT_VARIANTS = {
            "draw_arc": [
                ("Center Point Arc", "Select center point to begin",
                 lambda s: setattr(s, "_arc_variant", _ARC_VARIANT_CENTER)),
                ("Start Point Arc", "Select start point to begin",
                 lambda s: setattr(s, "_arc_variant", _ARC_VARIANT_START)),
            ],
            "draw_rectangle": [
                ("Corner Rectangle", "Pick first corner",
                 lambda s: setattr(s, "_draw_rect_from_center", False)),
                ("Center Rectangle", "Pick center point",
                 lambda s: setattr(s, "_draw_rect_from_center", True)),
            ],
            "wall": [
                ("Wall (Line)", "Pick wall start point",
                 lambda s: s._set_wall_primitive("line")),
                ("Wall (Polyline)", "Pick wall start point",
                 lambda s: s._set_wall_primitive("polyline")),
                ("Wall (Corner Rectangle)", "Pick first corner",
                 lambda s: s._set_wall_primitive("rect", from_center=False)),
                ("Wall (Center Rectangle)", "Pick centre point",
                 lambda s: s._set_wall_primitive("rect", from_center=True)),
            ],
            "floor": [
                ("Floor (Corner Rectangle)", "Pick first corner",
                 lambda s: s._set_floor_primitive("rect", from_center=False)),
                ("Floor (Center Rectangle)", "Pick centre point",
                 lambda s: s._set_floor_primitive("rect", from_center=True)),
                ("Floor (Polygon)", "Pick first boundary point",
                 lambda s: s._set_floor_primitive("polygon")),
            ],
        }
        self._variant_index = {m: 0 for m in self._PLACEMENT_VARIANTS}

    def _at_placement_step_zero(self) -> bool:
        """True while the current tool has not placed its first point.

        Cycling the variant only makes sense before the first click; once a
        point is down the geometry is committed to a variant.
        """
        if self.mode == "draw_arc":
            return self._draw_arc_step == 0
        if self.mode == "draw_rectangle":
            return self._draw_rect_anchor is None and not self._draw_rect_rotating
        if self.mode == "wall":
            return (self._wall_anchor is None
                    and self._wall_rect_anchor is None
                    and not self._wall_rect_rotating)
        if self.mode == "floor":
            return (self._floor_active is None
                    and self._floor_rect_anchor is None
                    and not self._floor_rect_rotating)
        return False

    def _apply_current_variant(self) -> None:
        """Apply the sticky variant's state and emit the hinted step-0 readout.

        No-op for a mode with no variants.  Emits ``"<label> (←/→ to change):
        <instr>"`` so the readout advertises the cycle while it is still live.
        """
        variants = self._PLACEMENT_VARIANTS.get(self.mode)
        if not variants:
            return
        label, instr, apply_fn = variants[self._variant_index[self.mode]]
        apply_fn(self)
        self.instructionChanged.emit(f"{label} (←/→ to change): {instr}")

    def cycle_placement_variant(self, direction: int) -> bool:
        """←/→ cycle the placement variant; return False to fall through.

        Only cycles at step 0 of a multi-variant tool while no HUD field holds
        focus.  Returns False otherwise so the arrow key reaches the view's
        default scroll.

        Args:
            direction: +1 for the next variant, -1 for the previous.

        Returns:
            True when a variant was cycled (and the arrow key is consumed),
            False when cycling is not applicable.
        """
        if (self.mode not in self._PLACEMENT_VARIANTS
                or not self._at_placement_step_zero()
                or self.is_input_mode()):
            return False
        n = len(self._PLACEMENT_VARIANTS[self.mode])
        self._variant_index[self.mode] = (
            self._variant_index[self.mode] + direction) % n
        self._apply_current_variant()
        return True

    def active_schema(self):
        """Return the Schema for the current mode, or None.

        Warning:
            A non-None schema implies neither a published point nor an
            applier.  ``_SCHEMA_FOR_MODE`` is a forward declaration — it
            describes the migration's end state, while the
            ``publish_placement_state`` call sites and the appliers land one
            task at a time, so a mapped mode may still return a schema while
            ``get_resolved_point()`` stays None and no applier exists.  A
            caller that needs a seeded position must gate on
            ``get_resolved_point() is not None``, and a caller that intends to
            commit must gate on ``_APPLIER_FOR_MODE`` — never on this returning
            a schema, or it will open a HUD that can only dead-end.  Read the
            tables for the current state rather than trusting a count written
            here, which goes stale every time a mode is migrated.

        Returns:
            The registered ``Schema`` for ``self.mode``, or None when the mode
            has no dynamic-input schema.
        """
        # On-path Navigate (D4) overrides the primitive readout while the cursor
        # is soft-snapped to a single ALIGN path: the ``track`` schema replaces
        # the mode's Length/Angle (or X/Y, R, …) with one signed Distance field.
        # Refused for transform modes / rotate steps and for modes that cannot
        # commit a typed point — see ``_align_track_schema``.
        track = self._align_track_schema()
        if track is not None:
            return track
        return self._base_schema()

    def _rectangle_schema_for_step(self):
        """Return the rectangle schema for the current step.

        Rectangle placement is 3-step (Task 12): the two-click **sizing** step
        types the far corner (the ``rectangle`` X/Y schema), then the
        **rotate** step types the absolute orientation (the ``rotation``
        transform).  ``_draw_rect_rotating`` picks which one is live.  Unlike
        arc there is no anchorless step 0 — the sizing schema has an anchor from
        the first click, and before that first click the anchor gate keeps the
        HUD shut anyway.
        """
        if self._draw_rect_rotating:
            return SCHEMAS.get("rotation")
        return SCHEMAS.get("rectangle")

    def _polygon_schema_for_step(self):
        """Return the polygon schema for the current step.

        Polygon placement is 3-step: the sizing step types the radius (the
        ``polygon`` schema), then the rotate step types the orientation (the
        ``rotation`` schema).  ``_polygon_rotating`` picks which one is live.
        Step 0 has no anchor before the first click, so the anchor gate keeps
        the HUD shut then — exactly like draw_rectangle.
        """
        if self._polygon_rotating:
            return SCHEMAS.get("rotation")
        return SCHEMAS.get("polygon")

    def _arc_schema_for_step(self):
        """Return the arc schema for the current step, or None.

        Arc is the one mode whose schema changes mid-placement: step 1 types the
        radius + start angle (the ``line`` schema, Length=radius, Angle=start°),
        step 2 types the sweep (``arc_span``).  Step 0 has no HUD — there is no
        anchor before the first click, so nothing to read out or seed from.
        """
        if self._draw_arc_step == 1:
            return SCHEMAS.get("line")
        if self._draw_arc_step == 2:
            return SCHEMAS.get("arc_span")
        return None

    def _wall_schema_for_primitive(self):
        """HUD schema for the active wall primitive.

        Line/polyline → ``line`` schema.  Rect → step-aware: sizing step uses
        ``rectangle`` schema; rotate step uses ``rotation`` schema (mirrors
        ``_rectangle_schema_for_step``).
        """
        if self._wall_primitive == "rect":
            if self._wall_rect_rotating:
                return SCHEMAS.get("rotation")
            return SCHEMAS.get("rectangle")
        return SCHEMAS.get("line")

    def _floor_schema_for_primitive(self):
        """HUD schema for the active floor primitive.

        Rect → step-aware: sizing step uses ``rectangle`` schema, rotate step
        uses ``rotation`` schema.  Polygon → ``line`` schema (per-segment
        length/angle readout, same as the wall line/polyline).  Mirrors
        ``_wall_schema_for_primitive``.
        """
        if self._floor_primitive == "rect":
            if self._floor_rect_rotating:
                return SCHEMAS.get("rotation")
            return SCHEMAS.get("rectangle")
        return SCHEMAS.get("line")

    def get_resolved_point(self) -> "QPointF | None":
        """Return the last point published by ``publish_placement_state``.

        This is the *constrained* position actually shown on screen, which is
        what the HUD seeds from.  Distinct from ``_last_scene_pos``, which
        holds the raw cursor and so can disagree with the preview whenever a
        constraint (Ctrl, 45° snap, ALIGN) is active.

        This — not ``active_schema()`` — is the gate for "is there a live
        placement to seed from".  Most modes that ``active_schema()`` answers
        for do not publish yet (see its warning), so None here is the normal
        state in eight of the ten mapped modes.

        The returned point is always a fresh copy; callers may mutate it.

        Returns:
            A copy of the resolved point, or None when nothing is published.
        """
        p = self._resolved_point
        return QPointF(p) if p is not None else None

    def clear_placement_state(self) -> None:
        """Drop the published point and readout (placement finished/cancelled)."""
        self._resolved_point = None
        self._draw_dim_hint = None

    def publish_placement_state(self, anchor, point) -> None:
        """Record the resolved placement point and derive the HUD readout.

        Call once per frame per mode, at the point where the mode has finished
        constraining its position (OSNAP → ALIGN → Ctrl → 45° snap).  This
        is the single source for both the live read-only readout and the
        values the HUD seeds with, so the two cannot disagree.

        A schema-driven mode's readout is the ``DynamicInputHud`` widget itself
        (decision S1), which ``_sync_dynamic_input`` reseeds from the point
        recorded here.  There is no painted string to build — ``_draw_dim_hint``
        is only cleared, so a stale hint from a mode that hand-builds its own
        cannot survive into one that does not.  One HUD, not two, enforced at
        the single site that assigns the string rather than by a second test in
        ``Model_View.drawForeground``.

        Args:
            anchor: The placement anchor, or None when the mode has not
                established one yet.
            point: The fully constrained point under the cursor.
        """
        # No-op in input mode. The HUD seeded from the point published at
        # engage time, and the user is now editing those numbers; a late
        # publish would move the seed under them.
        if self.is_input_mode():
            return
        self._resolved_point = QPointF(point) if point is not None else None
        self._draw_dim_hint = None

    # ─────────────────────────────────────────────────────────────────────────
    # Dynamic input (on-canvas HUD)
    # ─────────────────────────────────────────────────────────────────────────
    #
    # Cursor mode and input mode are exclusive, but the HUD spans both
    # (decision S1).  One ``DynamicInputHud`` is built as soon as a placement
    # anchor is armed and lives until the placement ends; in cursor mode it is
    # a passive readout that follows the cursor, and in input mode it is the
    # editor.  ``dynamic_input is not None`` therefore means "there is a
    # placement being read out", while ``dynamic_input.is_engaged()`` — i.e.
    # ``is_input_mode()`` — means "the keyboard is in a field".  Everything
    # that makes the mouse inert keys off the latter, never the former.

    # Characters that open the HUD by being typed.  Only these engage: a
    # letter belongs to whatever shortcut owns it.
    ENGAGE_CHARS = "0123456789.-"

    def is_input_mode(self) -> bool:
        """Whether a HUD field has the keyboard and the cursor is therefore inert.

        Deliberately *not* "a HUD exists" (decision S1): the HUD is on screen
        for the whole placement, and for most of that time it is a read-only
        readout that must leave the mouse, Ctrl+Z and the click-commit path
        completely alone.

        Returns:
            True while a ``DynamicInputHud`` field holds focus.
        """
        hud = self.dynamic_input
        return hud is not None and hud.is_engaged()

    def _hud_available(self) -> bool:
        """Whether the current placement can carry a HUD at all.

        The same gate for the passive readout and for engaging it, so the HUD
        the user is looking at is always one they can type into.

        Refuses when there is nothing coherent to read out or edit: the mode has
        no schema, the mode has no applier, or an *anchored* schema has no
        anchor.  The anchor gate is keyed on ``schema.requires_anchor``, which
        covers every placement plus the one transform that has a real anchor
        (``move``, whose base point is measured from).  The genuinely
        anchorless transforms — ``distance``, ``spacing_count`` — leave it and
        so open as soon as their source is armed.

        The applier gate is what keeps the refusal honest for the anchorless
        transforms: skipping the anchor gate would otherwise let them open a HUD
        whose Enter reaches nothing, raising inside a Qt signal handler and
        stealing Enter from the mode's own working commit path.  Modes mapped
        in ``_SCHEMA_FOR_MODE`` but not yet in ``_APPLIER_FOR_MODE`` simply do
        not open a HUD.
        """
        if self.mode not in self._APPLIER_FOR_MODE:
            return False
        schema = self.active_schema()
        if schema is None:
            return False
        return not (schema.requires_anchor
                    and self.get_placement_anchor() is None)

    def _create_dynamic_input(self):
        """Build and show the HUD for the current mode as a passive readout.

        The HUD is parented to the first **visible** view, not ``views()[0]``.
        More than one view is attached to the plan scene — the main window
        keeps a vestigial view that is never parented into the tab widget and
        never shown — and index 0 is that orphan, so parenting there built a
        correct HUD inside an invisible widget tree: shown, but with no visible
        ancestor to carry it onto the screen.  Visibility is the right
        discriminator rather than focus because Tab arrives at the focused view
        but focus may be sitting on a ribbon widget, whereas exactly one plan
        view is visible at a time in the central tab stack.

        Returns:
            The live ``DynamicInputHud``, or None when it could not be shown —
            in which case nothing was left behind and the scene is unchanged.
        """
        view = self._visible_view()
        if view is None:
            return None
        schema = self.active_schema()

        from .dynamic_input import DynamicInputHud
        hud = DynamicInputHud(schema, self.scale_manager, view.viewport())
        hud.committed.connect(self._on_dynamic_input_committed)
        hud.cancelled.connect(self._on_dynamic_input_cancelled)
        hud.fieldCommitted.connect(self._on_dynamic_input_field_committed)
        self.dynamic_input = hud
        if hasattr(view, "place_dynamic_input"):
            # No scene latch while it is only a readout: passing None puts it
            # back on the cursor, which it now tracks frame by frame.  The latch
            # happens on engage, when the cursor goes inert and chasing it would
            # be meaningless.
            view.place_dynamic_input(hud, None)
        hud.show()
        hud.raise_()
        # Self-correcting: a HUD the user cannot see is worse than none at all —
        # engaging it would make the cursor inert with no visible way back.
        # Rather than trusting the parent choice above to be the only way that
        # can happen, confirm it really reached the screen and unwind if not.
        if not hud.isVisible():
            self.end_dynamic_input()
            return None
        return hud

    def _on_dynamic_input_field_committed(self) -> None:
        """Redraw the placement preview from the HUD's current field values.

        Fires on each Tab field-commit while a field is engaged (§4.5 keeps the
        mouse inert, so the ghost would otherwise sit frozen at its engage-time
        seed).  Reads values non-destructively — the invalid-flag machinery
        stays on the real Tab/Enter path — resolves them through the active
        schema, and drives the same preview helper the mouse uses.

        Placement schemas (``returns_point``) resolve to the ``QPointF`` the
        preview helpers consume and redraw directly.  The ``move`` transform
        redraws too: its ``{"offset": ...}`` is converted to the target point
        its ghost helper takes (base anchor + offset).  The gridline replicate
        transforms are deferred — they carry a signed side the typed value
        alone does not fix, so their preview-on-commit lands with their
        applier.  A no-op if the HUD closed between signal and slot.
        """
        hud = self.dynamic_input
        schema = self.active_schema()
        if hud is None or schema is None:
            return
        anchor = self.get_placement_anchor()
        if schema.requires_anchor and anchor is None:
            return
        resolved = schema.resolve(anchor, hud.current_values())
        if schema.returns_point:
            self._preview_from_resolved(resolved)
        elif schema.name == "rotation":
            # The rectangle and polygon rotate transforms' preview is an *angle*,
            # not a point, so it does not route through ``_transform_preview_point``
            # / ``_preview_from_resolved`` (which are point-based).  Dispatch to
            # the mode-appropriate helper.
            if self.mode == "polygon":
                self._preview_polygon_rotation(resolved["angle_deg"])
            else:
                self._preview_rectangle_rotation(resolved["angle_deg"])
        else:
            # A transform schema resolves to a scalar/offset dict, not a point,
            # but its preview helper takes the point the resolved value lands on.
            # Each anchored transform projects its dict onto that point so the
            # mouse path and this typed path stay identical.  The gridline
            # replicate transforms carry a signed side the typed value alone does
            # not fix, so their preview-on-commit is deferred and they fall
            # through to the no-op.
            point = self._transform_preview_point(resolved, anchor)
            if point is None:
                return
            self._preview_from_resolved(point)
        for v in self.views():
            v.viewport().update()

    def _transform_preview_point(self, resolved, anchor):
        """Project an anchored transform's resolved value onto its preview point.

        A transform schema does not resolve to a point, so the field-commit
        preview cannot feed ``_preview_from_resolved`` directly.  Each anchored
        transform re-derives the point its own preview helper consumes from the
        resolved dict and the scene's armed state:

        * ``move`` lands its base anchor at ``anchor + offset``;
        * ``draw_arc`` at step 2 sweeps to the endpoint the typed span implies on
          the stored radius circle (``_arc_end_point_for_span``).

        Returns:
            The ``QPointF`` the preview helper takes, or None for a transform
            whose preview-on-commit is deferred (the gridline replicate modes,
            which carry a signed side the typed value alone does not fix).
        """
        if self.mode == "move":
            offset = resolved["offset"]
            return QPointF(anchor.x() + offset.x(), anchor.y() + offset.y())
        if self.mode == "draw_arc" and self._draw_arc_step == 2:
            return self._arc_end_point_for_span(resolved["span_deg"])
        return None

    def _sync_dynamic_input(self) -> None:
        """Reconcile the HUD with the live placement state — create, reseed, close.

        The single owner of the HUD's existence during cursor mode.  Called once
        per mouse move and once per press, after the mode's own handler has run,
        so it sees the anchor and resolved point that handler just produced: a
        first click arms the anchor and the HUD appears, a second commits and it
        goes away, all without either press handler knowing the HUD exists.

        A no-op while engaged.  The user is typing; the mouse is inert by
        definition, so there is nothing new to reflect and reseeding would
        overwrite their entry.
        """
        if self.is_input_mode():
            return
        if not self._hud_available():
            if self.dynamic_input is not None:
                self.end_dynamic_input()
            return
        schema = self.active_schema()
        hud = self.dynamic_input
        if hud is not None and hud.schema is not schema:
            # Mode changed under a live HUD without passing through set_mode.
            # Its editors belong to the old schema, so it cannot be reused.
            self.end_dynamic_input()
            hud = None
        if hud is None:
            hud = self._create_dynamic_input()
            if hud is None:
                return
        hud.set_values(
            self._seed_values_for(schema, self.get_placement_anchor()))
        self._arm_arc_coupling(hud, schema)
        self._arm_track_direction(hud, schema)
        view = self._visible_view()
        if view is not None and hasattr(view, "place_dynamic_input"):
            # Re-placed every frame: an unengaged HUD follows the cursor.
            view.place_dynamic_input(hud)

    def begin_dynamic_input(self, seed: str = "") -> bool:
        """Engage input mode, opening the HUD first if one is not already up.

        Under decision S1 this no longer *creates* the HUD in the normal case —
        the placement already has one, showing the very numbers being engaged —
        it moves the keyboard into it.  The create path survives for the engage
        that arrives before any mouse move has synced one (Tab straight after
        the first click, with the pointer still stationary).

        Refuses, changing nothing, when input mode is already active or the
        placement cannot carry a HUD (see :meth:`_hud_available`).

        Args:
            seed: The keystroke that engaged the HUD, placed into the first
                field so typing continues naturally.  Empty for Tab, which
                engages without contributing a character.

        Returns:
            True when input mode was entered, False when the engage was
            refused.  Callers use this to decide whether to accept the key.
        """
        if self.is_input_mode():
            return False
        if not self._hud_available():
            return False
        schema = self.active_schema()
        hud = self.dynamic_input
        if hud is None or hud.schema is not schema:
            if hud is not None:
                self.end_dynamic_input()
            hud = self._create_dynamic_input()
            if hud is None:
                return False
        # Reseeded even when the HUD was already up: the sync runs on mouse
        # moves, and the anchor can have been armed by a click the pointer never
        # moved after, leaving the readout a frame behind what Enter would
        # commit.
        hud.set_values(
            self._seed_values_for(schema, self.get_placement_anchor()))
        self._arm_arc_coupling(hud, schema)
        self._arm_track_direction(hud, schema)
        view = self._visible_view()
        if view is not None and hasattr(view, "place_dynamic_input"):
            # Latch to the resolved placement point — the constrained position
            # actually on screen.  From here the cursor is inert, so the HUD
            # rides pan and zoom with the geometry it is editing instead of
            # chasing a pointer whose movement means nothing.
            view.place_dynamic_input(hud, self.get_resolved_point())
        hud.engage(seed)
        return True

    def _visible_view(self):
        """Return the attached view the user is actually looking at.

        The plan scene has more than one view attached and only one of them is
        on screen (see :meth:`begin_dynamic_input`), so anything that puts a
        widget in front of the user, or hands focus back to the canvas, has to
        pick by visibility instead of by index.

        Returns:
            The first visible ``QGraphicsView`` on this scene, or None when no
            attached view is visible.
        """
        return next((v for v in self.views() if v.isVisible()), None)

    def _snap_view(self):
        """The view whose zoom (``transform().m11()``) drives snap/scale reads.

        Prefers the on-screen plan view (:meth:`_visible_view`); falls back to
        the LAST-attached view so headless tests (which attach a view without
        ``show()``) still resolve a real transform. ``views()[0]`` is
        deliberately *not* the fallback: in the running app that is the
        vestigial, never-shown ``MainWindow.view`` frozen at ``m11 == 1.0`` —
        reading it made every zoom-dependent tolerance (snap aperture,
        design-area pick, ALIGN band, …) collapse to a fixed *scene*
        distance regardless of zoom.
        """
        v = self._visible_view()
        if v is not None:
            return v
        views = self.views()
        return views[-1] if views else None

    def _active_view_scale(self) -> float:
        """Current on-screen zoom (px per scene-unit) from the active plan view."""
        v = self._snap_view()
        return v.transform().m11() if v is not None else 1.0

    def _seed_values_for(self, schema, anchor) -> dict:
        """Return the values *schema*'s HUD should open with.

        WYSIWYG: a placement seeds from the **resolved** point — the
        constrained position actually drawn on screen — never from the raw
        cursor, so the numbers in the HUD are the ones the user is looking at.
        The anchor stands in when nothing has been published yet, which seeds a
        zero-length placement rather than an empty HUD.

        Args:
            schema: The active ``Schema``.
            anchor: The placement anchor, or None for a transform schema.

        Returns:
            Values keyed by field name, in schema (scene) units.
        """
        if schema.name == "track":
            # The track schema has no cursor-derived inverse (``seed`` is None):
            # its one Distance field is the signed distance-along-ray the seam
            # already measured when it recovered the winning ray.  Seeding it
            # keeps the readout showing how far along the path the cursor sits.
            return {"Distance": self._align_track_dist}
        if schema.is_placement:
            # Explicit None test, never truthiness: PyQt gives QPointF a
            # __bool__ that is False at the origin, so ``point or anchor`` would
            # silently discard a resolved point of exactly (0, 0) and read out a
            # zero-length placement.  Snapping to the origin is ordinary in CAD,
            # and the readout is now rebuilt every frame, so that would be
            # visible whenever the cursor crossed it.
            point = self.get_resolved_point()
            return schema.seed(anchor, anchor if point is None else point)
        return self._transform_seed_values(schema)

    def _transform_seed_values(self, schema) -> dict:
        """Return seed values for a transform schema, read from scene state.

        Transforms have no anchor and no cursor-derived inverse, so each reads
        the state its own commit path already uses — the replicate spacing and
        count for the gridline modes, the live displacement for a move.

        Args:
            schema: A transform ``Schema`` (``returns_point`` False).

        Returns:
            Values keyed by field name; empty for an unrecognised schema, which
            leaves the HUD's editors at their own defaults.
        """
        if schema.name == "displacement":
            anchor = self.get_placement_anchor()
            point = self.get_resolved_point()
            if anchor is None or point is None:
                return {"dX": 0.0, "dY": 0.0}
            # Y-up, matching resolve_displacement's negation.
            return {"dX": point.x() - anchor.x(),
                    "dY": -(point.y() - anchor.y())}
        if schema.name == "rotation":
            # Seed the live orientation: the pivot→resolved-point heading, the
            # same absolute angle the mouse and ``resolve_rotation`` use.  0°
            # (axis-aligned) before anything is published.  The pivot differs by
            # mode — the polygon rotate step pivots about its centre, the
            # rectangle about its stored pivot, the wall-rectangle about its
            # own stored pivot — so dispatch to the matching angle helper (all
            # share the same Y-up formula).
            point = self.get_resolved_point()
            if point is None:
                return {"Angle": 0.0}
            if self.mode == "polygon":
                return {"Angle": self._polygon_rotation_angle_to(point)}
            if self.mode == "wall":
                return {"Angle": self._wall_rect_rotation_angle_to(point)}
            if self.mode == "floor":
                return {"Angle": self._floor_rect_rotation_angle_to(point)}
            return {"Angle": self._rect_rotation_angle_to(point)}
        if schema.name == "arc_span":
            # Live span from the resolved point — the same sweep the third click
            # or a typed Span commits.  Without this the readout sits at 0 the
            # whole span step (a transform has no cursor-derived inverse).
            # ArcLength stays in scene units; ``set_values`` converts it to mm.
            point = self.get_resolved_point()
            if point is None or self._draw_arc_center is None:
                return {"Span": 0.0, "ArcLength": 0.0}
            cx, cy = self._draw_arc_center.x(), self._draw_arc_center.y()
            end_deg = math.degrees(math.atan2(-(point.y() - cy),
                                              point.x() - cx))
            span = end_deg - self._draw_arc_start_deg
            if span <= 0:
                span += 360.0
            return {"Span": span,
                    "ArcLength": math.radians(span) * self._draw_arc_radius}
        # ``_replicate_spacing`` is a *signed* perpendicular projection, so it
        # passes through 0.0 as the cursor crosses the source gridline — 0.0 is
        # not reliably "never set".  Treating it as unset is still correct
        # because the commit path rejects ``abs(dist) < 0.5`` anyway, so a
        # seeded zero could never be placed.  Explicit ``!= 0.0`` (matching the
        # comparison the modal path already uses) rather than truthiness, since
        # every other value here is a legitimate signed distance.
        #
        # Seeded as a **magnitude**: ``Distance`` and ``Spacing`` carry
        # ``minimum=0.0``, so the raw signed projection would seed text the
        # field itself rejects on the very next read.  The side stays with the
        # cursor and is reapplied by the appliers
        # (:meth:`_replicate_side_sign`) — offsetting by a typed magnitude onto
        # the side you are pointing at, rather than by a signed quantity whose
        # sign is invisible in the geometry.
        spacing = abs(self._replicate_spacing
                      if self._replicate_spacing != 0.0 else 1000.0)
        if schema.name == "distance":
            return {"Distance": spacing}
        if schema.name == "spacing_count":
            return {"Spacing": spacing,
                    "Count": max(1, int(self._replicate_count))}
        return {}

    def _arm_arc_coupling(self, hud, schema) -> None:
        """Arm the HUD's Span-to-ArcLength coupling for the ``arc_span`` schema.

        The coupling recomputes ``ArcLength = radius * radians(Span)`` as the
        user edits, so it needs the sweep radius in the millimetres the
        ``ArcLength`` DIMENSION editor stores.  The radius is fixed once step 2
        is reached, so arming it at seed time (before or at engage) is enough.

        ``_draw_arc_radius`` is in scene units; it is converted through the same
        DIMENSION scene->mm path the HUD's dimension editors use
        (``DynamicInputHud.scene_to_mm``, guarded on calibration: an
        uncalibrated scene treats one unit as one mm, a calibrated one routes
        through ``ScaleManager.scene_to_mm``), so the coupling and the editor
        agree.  A no-op for every other schema; ``set_coupling_radius`` is
        harmlessly ignored by non-arc HUDs, but the guard keeps intent clear.
        """
        if schema is None or schema.name != "arc_span":
            return
        hud.set_coupling_radius(hud.scene_to_mm(self._draw_arc_radius))

    def _arm_track_direction(self, hud, schema) -> None:
        """Inject the winning path's unit direction into a ``track`` HUD.

        ``resolve_track`` reads the direction from the values dict under the
        reserved ``"__dir__"`` key, injected by ``DynamicInputHud.values`` from
        whatever ``set_track_direction`` last armed.  The direction is fixed for
        as long as the cursor stays on one path, so arming it at seed time (each
        sync and at engage) keeps it current as the swap turns on and off.  A
        no-op for every other schema; other HUDs ignore the armed direction.
        """
        if schema is None or schema.name != "track":
            return
        direction = (self._align_track_ray.direction
                     if self._align_track_ray is not None else None)
        hud.set_track_direction(direction)

    def end_dynamic_input(self) -> None:
        """Close the HUD entirely — the placement it was reading out is over.

        Safe to call when no HUD is open, so every exit path (commit, mode
        switch, the anchor going away) can call it unconditionally.  Escape does
        *not* come here: it steps back to cursor mode and leaves the readout up
        (see :meth:`_on_dynamic_input_cancelled`).

        Focus goes back to the visible view — not to every attached view — or
        the canvas would keep receiving keys for a widget that is gone, and the
        last ``setFocus`` in the loop would have handed focus to the invisible
        orphan view the scene also carries (see :meth:`_create_dynamic_input`).
        It is claimed only when the HUD actually held it: a passive readout
        being retired must not yank focus away from whatever the user is really
        working in, such as the property panel.
        """
        hud = self.dynamic_input
        # Cleared first: the tear-down below can re-enter through focus and
        # paint events, which must already see cursor mode.
        self.dynamic_input = None
        if hud is None:
            return
        was_engaged = hud.is_engaged()
        hud.hide()
        # deleteLater only *schedules* deletion: until the deferred-delete pass
        # runs, the HUD is alive and would still be wired.  A stray signal in
        # that window would resolve one schema's values against an anchor the
        # scene has already moved past, so the connections go first.
        hud.committed.disconnect(self._on_dynamic_input_committed)
        hud.cancelled.disconnect(self._on_dynamic_input_cancelled)
        # Also out of the viewport's paint and focus chains for that window.
        hud.setParent(None)
        hud.deleteLater()
        if was_engaged:
            view = self._visible_view()
            if view is not None:
                view.setFocus(Qt.FocusReason.OtherFocusReason)
        # Every view still repaints: the HUD's departure has to clear from any
        # viewport that was painting it, visible or not.
        for v in self.views():
            v.viewport().update()

    def _on_dynamic_input_cancelled(self) -> None:
        """Escape rung 0: hand the placement back to the cursor.

        Only input mode is abandoned. The mode and its anchor survive, so
        Escape steps back to the cursor rather than throwing away a placement
        the user is midway through — a second Escape, handled elsewhere, is
        what cancels that.

        Under decision S1 the HUD itself survives too, reverting to the passive
        readout it is for the rest of the placement; closing it would leave the
        user with no numbers at all for a placement that is still live, and the
        next mouse move would only build it again.  Focus is pushed back to the
        view explicitly — the HUD is now transparent to the mouse but still
        holds the keyboard until someone takes it.
        """
        hud = self.dynamic_input
        if hud is None:
            return
        hud.disengage()
        view = self._visible_view()
        if view is not None:
            view.setFocus(Qt.FocusReason.OtherFocusReason)
        # The cursor is live again, so put the readout back under it rather than
        # leaving it latched where the placement was engaged.
        if view is not None and hasattr(view, "place_dynamic_input"):
            view.place_dynamic_input(hud, None)

    def _on_dynamic_input_committed(self, values: dict) -> None:
        """Resolve *values* into geometry and hand it to the click-commit path.

        Ordering is load-bearing: the schema resolves **before** the HUD is
        torn down and long before the applier runs, because appliers such as
        ``_commit_draw_line_at`` re-read the scene's anchor state and then call
        ``clear_placement_state()``.  Resolving afterwards would read an anchor
        the commit had already cleared.

        The HUD is torn down only once the applier reports success (decision
        D2).  A refusal — a length under the too-short floor, say — keeps it
        open with the offending field flagged, so the placement survives and
        the user can simply retype.  Closing first and applying afterwards is
        what made a typed ``0.3`` vanish into a status-bar message that
        appeared after the HUD had already gone.

        Args:
            values: Field values from the HUD, in schema units.
        """
        schema = self.active_schema()
        anchor = self.get_placement_anchor()
        if schema is None or (schema.requires_anchor and anchor is None):
            self.end_dynamic_input()
            return
        hud = self.dynamic_input
        geometry = schema.resolve(anchor, values)
        # On-path Navigate at the FIRST point (BUG A): the ``track`` schema is a
        # placement schema, so ``get_placement_anchor`` hands back the tracking
        # ray's ORIGIN even before the mode's own first click — non-None — which
        # satisfies the anchor gate above.  But the mode's commit-only appliers
        # (``_commit_draw_line_at`` / ``_commit_draw_circle_at``) refuse when no
        # per-mode anchor is armed, and a False verdict becomes a red field.  A
        # typed Distance on a path at the first point is really "click here to
        # arm the first point", so route the resolved point through the mode's
        # PRESS handler (the arm-or-commit entry a real first click takes),
        # exactly as ``_apply_wall_dynamic_input`` already does for walls.  With
        # a per-mode anchor armed (second point), this branch is skipped and the
        # segment commits through the normal applier as before.
        if (schema.name == "track"
                and self._mode_placement_anchor() is None
                and self._commit_track_first_point(geometry)):
            self.end_dynamic_input()
            return
        if self.apply_dynamic_input(geometry):
            # An applier may have torn the HUD down itself (e.g. by calling
            # set_mode); end_dynamic_input is a no-op in that case.
            self.end_dynamic_input()
        elif hud is not None and hud is self.dynamic_input:
            hud.reject_commit()

    def _commit_track_first_point(self, point) -> bool:
        """Arm the mode's first point at *point* via its press handler.

        The on-path Navigate first-point path (BUG A): a typed Distance on a
        tracking path at the first-point step must arm the mode's placement
        anchor the same way a real first click on the path does, not run the
        commit-only applier (which refuses without an anchor).  Dispatches a
        synthetic press — ``event=None`` (the arming branch of every placement
        press handler touches only ``snapped``; ``event.modifiers()`` is read
        only in the second-point/commit branch, which cannot run here because
        the anchor is None) — through ``_PRESS_DISPATCH`` for the current mode.

        Args:
            point: The resolved scene-space point (``origin + Distance·dir``).

        Returns:
            True when the mode has a press handler and the first point was
            armed; False when no handler exists (caller falls back to the
            normal applier / rejection path).
        """
        handler_name = self._PRESS_DISPATCH.get(self.mode)
        if handler_name is None:
            return False
        before = self._mode_placement_anchor()
        getattr(self, handler_name)(None, point, point, None, None, None)
        # Spec D3 parity for the typed-first-point path: this synthetic press
        # does NOT flow through mousePressEvent's arm wrapper, so mirror the
        # direction capture here.  A track first point is armed while soft-
        # snapped to a single ALIGN path, so the inherited direction is that
        # path's own direction (extension/parallel ray); fall back to the live
        # snap result's source object if no track ray is armed.
        if before is None and self._mode_placement_anchor() is not None:
            ray = self._align_track_ray
            if ray is not None:
                self._align_anchor_dir = ray.direction
            else:
                self._align_anchor_dir = self._source_item_direction(
                    getattr(self._snap_result, "source_item", None))
        return True

    def apply_dynamic_input(self, geometry):
        """Apply resolved *geometry* through the current mode's commit path.

        Dispatches through ``_APPLIER_FOR_MODE``, the same table
        ``begin_dynamic_input`` gates on, so a HUD can never open for a mode
        this cannot commit.  The raise is therefore unreachable from the UI and
        survives only as a programmer-error backstop for a direct call.

        Args:
            geometry: A ``QPointF`` for placement schemas, or the transform
                dict for the others.

        Returns:
            The applier's verdict: True when it committed, False when it
            refused (decision D2).  Forwarded verbatim so the one rule lives in
            the commit path and nothing mirrors its threshold.

        Raises:
            NotImplementedError: When the current mode has no applier.  Not
                reachable through the HUD — the engage gate refuses first.
        """
        applier = self._APPLIER_FOR_MODE.get(self.mode)
        if applier is None:
            raise NotImplementedError(
                f"no dynamic-input applier for {self.mode!r}")
        return bool(getattr(self, applier)(geometry))

    # ─────────────────────────────────────────────────────────────────────────
    # Tab exact-input handler
    # ─────────────────────────────────────────────────────────────────────────
    # Template getters (pre-placement property editing)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_wall_template(self) -> "WallSegment":
        """Return (lazily-created) wall template for pre-placement editing."""
        if self._wall_template is None:
            self._wall_template = WallSegment(QPointF(0, 0), QPointF(100, 0))
            self._wall_template.name = "(Template)"
            self._wall_template._alignment = self._wall_alignment
            self._wall_template._scale_manager_ref = self.scale_manager
        # Always sync levels with current active level
        self._wall_template.level = self.active_level
        self._wall_template._base_level = self.active_level
        if self._level_manager is not None:
            levels = self._level_manager.levels
            active_idx = next(
                (i for i, l in enumerate(levels)
                 if l.name == self.active_level), 0)
            if active_idx + 1 < len(levels):
                self._wall_template._top_level = levels[active_idx + 1].name
        return self._wall_template

    def _get_floor_template(self) -> "FloorSlab":
        """Return (lazily-created) floor slab template for pre-placement editing."""
        if self._floor_template is None:
            self._floor_template = FloorSlab(color="#8888cc")
            self._floor_template.name = "(Template)"
            self._floor_template._scale_manager_ref = self.scale_manager
        # Always sync level with current active level
        self._floor_template.level = self.active_level
        return self._floor_template

    # QSettings key for the persisted floor placement template (mirrors the
    # pipe/sprinkler/text template keys owned by MainWindow).
    FLOOR_TEMPLATE_SETTINGS_KEY = "template/floor"

    def save_floor_template_settings(self, settings) -> None:
        """Persist the floor placement template to *settings* (QSettings).

        Mirrors the pipe/sprinkler/text templates: writes raw internal values so
        they round-trip regardless of unit prefs.  Only the project-agnostic
        recipe is stored — modes, offsets and thickness.  Level NAMES and
        absolute-Z values are project-specific and are deliberately NOT
        persisted (they are re-seeded from the active level on load).
        """
        tmpl = self._get_floor_template()
        settings.setValue(self.FLOOR_TEMPLATE_SETTINGS_KEY, {
            "top_mode":         tmpl._top_mode,
            "top_offset_mm":    tmpl._top_offset_mm,
            "bottom_mode":      tmpl._bottom_mode,
            "bottom_offset_mm": tmpl._bottom_offset_mm,
            "thickness_mm":     tmpl._thickness_mm,
        })

    def load_floor_template_settings(self, settings) -> None:
        """Restore the floor placement template from *settings* (QSettings).

        Applies the persisted modes/offsets/thickness, then re-seeds the
        project-specific parts against the active level:

        * Level-mode boundaries → ``_top_level`` / ``_bottom_level`` resolve to
          the current active level.
        * Absolute-mode boundaries → ``_*_abs_z_mm`` seed from the active
          level's elevation, so an absolute default starts at a sane
          project-relative value.
        """
        if not settings.contains(self.FLOOR_TEMPLATE_SETTINGS_KEY):
            return
        blob = settings.value(self.FLOOR_TEMPLATE_SETTINGS_KEY, {})
        if not isinstance(blob, dict):
            return

        tmpl = self._get_floor_template()

        # Active level's elevation seeds absolute-mode boundaries.
        active_elev = 0.0
        if self._level_manager is not None:
            lvl = self._level_manager.get(self.active_level)
            if lvl is not None:
                active_elev = float(lvl.elevation)

        if "top_mode" in blob:
            mode = str(blob["top_mode"])
            if mode in {"level", "absolute"}:
                tmpl._top_mode = mode
        if "top_offset_mm" in blob:
            tmpl._top_offset_mm = float(blob["top_offset_mm"])
        if "bottom_mode" in blob:
            mode = str(blob["bottom_mode"])
            if mode in {"level", "absolute", "thickness"}:
                tmpl._bottom_mode = mode
        if "bottom_offset_mm" in blob:
            tmpl._bottom_offset_mm = float(blob["bottom_offset_mm"])
        if "thickness_mm" in blob:
            tmpl._thickness_mm = max(float(blob["thickness_mm"]),
                                     MIN_FLOOR_THICKNESS_MM)

        # Re-seed project-specific parts from the active level.
        tmpl._top_level = self.active_level
        tmpl._bottom_level = self.active_level
        if tmpl._top_mode == "absolute":
            tmpl._top_abs_z_mm = active_elev
        if tmpl._bottom_mode == "absolute":
            tmpl._bottom_abs_z_mm = active_elev

    def _get_roof_template(self) -> "RoofItem":
        """Return (lazily-created) roof template for pre-placement editing."""
        if self._roof_template is None:
            self._roof_template = RoofItem(color="#D2B48C")
            self._roof_template.name = "(Template)"
            self._roof_template._scale_manager_ref = self.scale_manager
        self._roof_template.level = self.active_level
        return self._roof_template

    def _get_gridline_template(self) -> "GridlineItem":
        """Return (lazily-created) gridline template for pre-placement editing.

        The template is NOT added to the scene and NOT appended to
        ``_gridlines``, so editing it via the property panel never triggers
        ``push_undo_state()`` (``GridlineItem.set_property`` guards the undo
        push with ``self.scene() is not None``).
        """
        if self._gridline_template is None:
            from .gridline import GridlineItem as _GLItem
            tmpl = _GLItem(QPointF(0, 0), QPointF(0, 1000))
            tmpl._label_text = "(Template)"
            tmpl._is_template = True
            self._gridline_template = tmpl
        return self._gridline_template

    def _get_geometry_template(self):
        """Return (lazily-created) geometry template for line/rect/circle/polyline."""
        from .construction_geometry import GeometryTemplate
        if self._geometry_template is None:
            self._geometry_template = GeometryTemplate()
        # Sync with active level
        self._geometry_template.level = self.active_level
        return self._geometry_template

    def _geom_color_lw(self):
        """Return (color, lineweight) for new geometry."""
        return "#ffffff", 2.0

    def _ensure_underlay_caches(self, *args, **kwargs):
        """Back-compat shell → :class:`UnderlayController`."""
        return self._underlay_ctl._ensure_underlay_caches(*args, **kwargs)

    def _load_underlay_from_cache(self, *args, **kwargs):
        """Back-compat shell → :class:`UnderlayController`."""
        return self._underlay_ctl._load_underlay_from_cache(*args, **kwargs)

    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_left_shift(event) -> bool:
        """Whether *event* is the **left** Shift key specifically.

        Qt reports both Shift keys as ``Key_Shift``; the left one is told apart
        by its native code so the right Shift stays a pure modifier.  On Windows
        left Shift carries scan code ``0x2A`` (42) / virtual key ``VK_LSHIFT``
        (``0xA0``); either match is accepted so a platform that fills only one
        of the two still works.
        """
        if event.key() != Qt.Key.Key_Shift:
            return False
        return event.nativeScanCode() == 42 or event.nativeVirtualKey() == 0xA0

    def cycle_placement_ambiguity(self) -> bool:
        """Left-Shift tap: cycle whatever is ambiguous about the placement.

        Select mode cycles similar elements, pipe mode cycles Z-stacked node
        candidates, wall mode cycles alignment.  These were Tab until Dynamic
        Input claimed Tab for the on-canvas HUD in every mode; a clean left-Shift
        tap now carries them (see :meth:`keyReleaseEvent`).

        Returns:
            True when something was cycled, False when the current mode has
            nothing ambiguous to cycle (so the caller can leave the key alone).
        """
        if self.mode in ("select", None, ""):
            return self._cycle_similar_selection()
        if self.mode == "pipe" and len(self._pipe_ctl._tab_candidates) > 1:
            self._pipe_ctl.cycle_tab()
            return True
        if self.mode == "opening":
            self._cycle_opening_alignment()
            return True
        return False

    def _cycle_opening_alignment(self) -> None:
        """Advance opening alignment through OPENING_ALIGNMENTS and refresh the
        live ghost (§7.6)."""
        aligns = list(OPENING_ALIGNMENTS)
        try:
            idx = aligns.index(self._opening_alignment)
        except ValueError:
            idx = -1
        self._opening_alignment = aligns[(idx + 1) % len(aligns)]
        self._sync_opening_state_to_template()
        self._refresh_opening_ghost()
        self.instructionChanged.emit(
            f"Opening [{self._opening_alignment}] · Space=align "
            f"←/→=hinge ↑/↓=facing")

    def _sync_opening_state_to_template(self) -> None:
        """Push the live cycle state onto the placement template and refresh the
        property panel so Spacebar/arrow changes are reflected there (§7.6)."""
        tmpl = getattr(self, "current_template", None)
        if isinstance(tmpl, WallOpening):
            tmpl.alignment = self._opening_alignment
            tmpl.mirror_hinge = self._opening_mirror_hinge
            tmpl.mirror_facing = self._opening_mirror_facing
            self.requestPropertyUpdate.emit(tmpl)

    def _cycle_similar_selection(self) -> bool:
        """Select the next element of the same type as the sole selection.

        Lifted verbatim from the retired ``_handle_tab_input`` select branch.

        Returns:
            True when the selection was advanced, False when there is not
            exactly one selected item of a cyclable type.
        """
        selected = self.selectedItems()
        if len(selected) == 1:
            item = selected[0]
            _type_map = {
                Pipe: lambda: list(self.sprinkler_system.pipes),
                WallSegment: lambda: list(self._walls),
                Node: lambda: [n for n in self.sprinkler_system.nodes
                               if n.has_sprinkler()],
                GridlineItem: lambda: list(self._gridlines),
                FloorSlab: lambda: list(self._floor_slabs),
                RoofItem: lambda: list(self._roofs),
            }
            collection = None
            for cls, getter in _type_map.items():
                if isinstance(item, cls):
                    collection = getter()
                    break
            if collection and item in collection:
                idx = collection.index(item)
                nxt = collection[(idx + 1) % len(collection)]
                self.clearSelection()
                nxt.setSelected(True)
                self.requestPropertyUpdate.emit(nxt)
                return True
        return False

    def _cycle_wall_alignment(self) -> None:
        """Advance wall alignment Center → Left → Right and refresh the preview.

        Triggered by Spacebar during wall placement (sole binding since Task 7).
        Previously bound to Left-Shift via ``cycle_placement_ambiguity``.
        """
        _cycle = {"Center": "Left", "Left": "Right", "Right": "Center"}
        self._wall_alignment = _cycle.get(self._wall_alignment, "Center")
        if self._wall_primitive == "rect":
            if self._wall_rect_anchor is None:
                self.instructionChanged.emit(
                    f"Pick first corner [{self._wall_alignment}]")
            else:
                self.instructionChanged.emit(
                    f"Pick opposite corner [{self._wall_alignment}]")
        elif self._wall_anchor is None:
            self.instructionChanged.emit(
                f"Pick wall start point [{self._wall_alignment}]  Space=align")
        else:
            self.instructionChanged.emit(
                f"Pick wall end point [{self._wall_alignment}]  Space=align")
        if self._wall_template is not None:
            self._wall_template._alignment = self._wall_alignment
            self.requestPropertyUpdate.emit(self._wall_template)
        # Force preview rect to update without requiring mouse movement
        if (self._wall_anchor is not None
                and self._last_scene_pos is not None
                and self._wall_preview_rect is not None):
            _wtmpl = self._get_wall_template()
            p1l, p1r, p2r, p2l = compute_wall_quad(
                self._wall_anchor, self._last_scene_pos,
                _wtmpl._thickness_mm, _wtmpl._alignment,
                self.scale_manager)
            _pp = QPainterPath()
            _pp.moveTo(p1l)
            _pp.lineTo(p2l)
            _pp.lineTo(p2r)
            _pp.lineTo(p1r)
            _pp.closeSubpath()
            self._wall_preview_rect.setPath(_pp)
            for v in self.views():
                v.viewport().update()

    # ─────────────────────────────────────────────────────────────────────────
    # Grid Lines
    # ─────────────────────────────────────────────────────────────────────────

    def place_grid_lines(self, params: dict):
        """Place gridlines from a batch spec (default-seed builder).

        *params* contains key ``"gridlines"`` — a list of dicts with
        keys: label, offset (scene px), length (scene px), angle_deg.

        Gridlines originate at p1 (the origin) and extend to p2.  Bubbles
        stand off from each endpoint via their own offset property
        (GRIDLINE_BUBBLE_OFFSET_MM), not a geometric overshoot.  Positive
        offset follows architectural convention (right for V, up for H).
        """
        specs = params.get("gridlines", [])
        if not specs:
            return

        self.push_undo_state()

        for spec in specs:
            label    = spec.get("label", "?")
            offset   = spec.get("offset", 0.0)
            length   = spec.get("length", 1000.0)
            angle    = spec.get("angle_deg", 90.0)

            rad = math.radians(angle)
            # Direction vector (along gridline)
            dx = math.cos(rad)
            dy = -math.sin(rad)   # Qt y-axis is inverted
            # Perpendicular vector (for offset)
            px = -dy
            py = dx

            # Positive offset: right for vertical, up for horizontal
            ox = offset * px
            oy = -offset * py

            # No geometric overshoot: bubbles stand off via their own offset
            # property (GRIDLINE_BUBBLE_OFFSET_MM).  p1 = origin, p2 = far end.
            p1 = QPointF(ox, oy)
            p2 = QPointF(ox + length * dx,
                         oy + length * dy)

            gl = GridlineItem(p1, p2, label=label)
            gl._locked = spec.get("locked", False)
            self.addItem(gl)
            apply_category_defaults(gl)
            self._gridlines.append(gl)

        self.sceneModified.emit()


    # ─────────────────────────────────────────────────────────────────────────
    # ── Align tool: dispatch-table getattr targets forward to the composed
    #    SceneTools collaborator (decomposition slice B) ─────────────────────
    def _press_align(self, event, pos, snapped, item_under, node_under, pipe_under):
        return self._tools._press_align(event, pos, snapped, item_under, node_under, pipe_under)

    def _move_align(self, event, snapped):
        return self._tools._move_align(event, snapped)

    def array_items(self, params):
        return self._tools.array_items(params)

    # OFFSET COMMAND helpers -> see scene_tools.py (SceneTools)
    # ─────────────────────────────────────────────────────────────────────────

    def project_point_onto_line(self, p1: QPointF, p2: QPointF, p: QPointF) -> QPointF:
        line_dx = p2.x() - p1.x()
        line_dy = p2.y() - p1.y()
        line_len2 = line_dx**2 + line_dy**2
        if line_len2 == 0:
            return p1
        t = ((p.x() - p1.x()) * line_dx + (p.y() - p1.y()) * line_dy) / line_len2
        t = max(0, min(1, t))
        return QPointF(p1.x() + t * line_dx, p1.y() + t * line_dy)

    def project_click_onto_pipe_segment(self, snapped, selection):
        line = selection.line()
        return self.project_point_onto_line(
            QPointF(line.x1(), line.y1()), QPointF(line.x2(), line.y2()), snapped
        )

    def update_preview_node(self, pos: QPointF):
        self.preview_node.setPos(pos)
        self.preview_node.show()

    # -------------------------------------------------------------------------
    # MOUSE EVENTS

    def _drag_grip_to(self, pos):
        """Apply the active grip drag to *pos* (scene coords), propagating to
        other selected gridlines. Endpoint grips (0/1) keep the opposite end
        fixed; bubble grips (2/3) slide the standoff. Lock-aware via apply_grip."""
        gi = self._grip_item
        if gi is None:
            return
        if isinstance(gi, GridlineItem):
            old_pt = gi.grip_points()[self._grip_index]
            gi.apply_grip(self._grip_index, pos)
            new_pt = gi.grip_points()[self._grip_index]
            delta = QPointF(new_pt.x() - old_pt.x(), new_pt.y() - old_pt.y())
            # Same scene-space delta re-projected onto each sibling's own axis:
            # exact for parallel (same-orientation) selections; non-parallel
            # members under-apply — consistent with endpoint-grip multi-select.
            for sel in self.selectedItems():
                if sel is gi or not isinstance(sel, GridlineItem):
                    continue
                sg = sel.grip_points()
                target = QPointF(sg[self._grip_index].x() + delta.x(),
                                 sg[self._grip_index].y() + delta.y())
                sel.apply_grip(self._grip_index, target)
        else:
            old_pt = None
            if (self._grip_index in (0, 1)
                    and isinstance(gi, WallSegment)
                    and hasattr(gi, "grip_points")):
                old_pt = gi.grip_points()[self._grip_index]
            gi.apply_grip(self._grip_index, pos)
            if old_pt is not None:
                new_pt = gi.grip_points()[self._grip_index]
                self._propagate_wall_endpoint(gi, old_pt, new_pt)
        self._tools._solve_constraints(gi)
        for v in self.views():
            v.viewport().update()

    def _propagate_wall_endpoint(self, moved, old_pt, new_pt) -> None:
        """Move every OTHER wall endpoint coincident with *old_pt* to *new_pt*.

        Polyline-drawn (or snapped-together) walls behave as joined: dragging a
        shared corner drags all its walls.  Proximity-based (no stored
        connectivity, no serialization change).  WallSegment endpoints only.

        Args:
            moved: The wall whose grip was directly dragged (excluded from scan).
            old_pt: The grip position before the drag move.
            new_pt: The grip position after the drag move.
        """
        eps = 0.5   # scene-unit anti-degeneracy tolerance (same family as snap)
        for w in self._walls:
            if w is moved:
                continue
            for idx in (0, 1):
                gp = w.grip_points()[idx]
                if (abs(gp.x() - old_pt.x()) <= eps
                        and abs(gp.y() - old_pt.y()) <= eps):
                    w.apply_grip(idx, QPointF(new_pt))

    def _format_cursor_readout(self, scene_pos) -> str:
        """Render *scene_pos* as the status-bar coordinate string.

        Args:
            scene_pos: The raw cursor position in scene coordinates.

        Returns:
            A string such as ``"X: 1000.000 mm  Y: 500.000 mm"``, Y negated
            into the Y-up convention the user reads.
        """
        sm = self.scale_manager
        return (f"X: {sm.scene_to_display(scene_pos.x())}  "
                f"Y: {sm.scene_to_display(-scene_pos.y())}")

    def mouseMoveEvent(self, event):
        # Input mode makes the cursor fully inert: nothing the mouse does may
        # move the seed out from under an open HUD.  Everything below the
        # guard — snap, previews, drags, publish — moves the geometry being
        # edited, so starving it is the point.
        #
        # The status-bar X/Y readout is the one exception: it is passive, and
        # freezing it makes the app look hung at exactly the moment the user is
        # typing.  ``_last_scene_pos`` deliberately stays frozen even so — it
        # feeds the geometry paths, and a stale raw cursor is the safer state.
        if self.is_input_mode():
            self.cursorMoved.emit(self._format_cursor_readout(event.scenePos()))
            return
        # ── Selection-manipulator drag owns the mouse ───────────────────
        # While a manipulator gesture is in flight, moves belong to the
        # grabber (held-transform preview); the placement machinery below
        # must not run.  The passive X/Y readout stays live.
        _manip = self._live_manip()
        if _manip is not None and _manip.is_dragging():
            self.cursorMoved.emit(self._format_cursor_readout(event.scenePos()))
            super().mouseMoveEvent(event)
            return
        scene_pos = event.scenePos()
        self._last_scene_pos = scene_pos
        self.cursorMoved.emit(self._format_cursor_readout(scene_pos))

        snapped = self.get_effective_position(scene_pos)
        # ── ALIGN dwell feed ────────────────────────────────────────────
        # Advance the acquire machine with the elapsed-ms since the last move
        # and the CURRENT real-snap under the cursor (get_effective_position
        # just populated ``_snap_result``).  Hover-resting long enough on one
        # snap source acquires it; the picker reads the acquired set next frame.
        now_ns = time.perf_counter_ns()
        elapsed_ms = (0.0 if self._align_last_move_ns is None
                      else (now_ns - self._align_last_move_ns) / 1e6)
        self._align_last_move_ns = now_ns
        if self._align_enabled and self._align_active_item is not None:
            self._align_controller.on_move(
                (scene_pos.x(), scene_pos.y()),
                self._align_snap_dict(self._snap_result), elapsed_ms)
        # Cleared each frame; draw modes republish below.  The resolved point
        # goes with the hint — leaving it set would let a mode that never
        # publishes hand the HUD the *previous* mode's stale point.
        self.clear_placement_state()

        # ── Grip drag (mode-independent, takes priority) ────────────────
        if self._grip_dragging and self._grip_item is not None:
            pos = snapped
            # Ctrl angle-snaps an endpoint-grip drag against the opposite
            # endpoint.  Only applied to 2-endpoint item types whose grip
            # indices map directly to the two ends:
            #   WallSegment / GridlineItem: grips[0]=pt1, grips[1]=pt2
            #   LineItem:                   grips[0]=pt1, grips[2]=pt2
            # Other item types (rect, arc, polygon, circle) use different
            # grip layouts and must NOT be affected by this block.
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                gi = self._grip_item
                idx = self._grip_index
                if isinstance(gi, (WallSegment, GridlineItem)):
                    if idx in (0, 1):
                        grips = gi.grip_points()
                        if len(grips) >= 2:
                            other = grips[1] if idx == 0 else grips[0]
                            pos = self._constrain_angle(other, snapped)
                elif isinstance(gi, LineItem):
                    if idx in (0, 2):
                        grips = gi.grip_points()
                        if len(grips) >= 3:
                            other = grips[2] if idx == 0 else grips[0]
                            pos = self._constrain_angle(other, snapped)
            self._drag_grip_to(pos)
            return

        # ── Gridline body drag (perpendicular constraint) ───────────────
        if self._dragging_gridline is not None:
            gl = self._dragging_gridline
            delta_x = snapped.x() - self._gridline_drag_start.x()
            delta_y = snapped.y() - self._gridline_drag_start.y()
            px, py = gl._perpendicular_vector()
            perp_offset = delta_x * px + delta_y * py
            gl.set_perpendicular_position(self._gridline_drag_original_pos + perp_offset)
            for v in self.views():
                v.viewport().update()
            return

        # ── Dispatch to per-mode handler ────────────────────────────────
        handler_name = self._MOVE_DISPATCH.get(self.mode)
        if handler_name is not None:
            getattr(self, handler_name)(event, snapped)
        else:
            # No mode matched — hide previews
            self.preview_node.hide()
            self.preview_pipe.hide()

        # After the handler, so it reads the point that handler just published.
        self._sync_dynamic_input()

        # Repaint foreground for snap indicator / grip overlay
        for v in self.views():
            v.viewport().update()

        super().mouseMoveEvent(event)

    # ── Dispatch table: mode string → move-handler method name ─────────
    _MOVE_DISPATCH = {
        "pipe":                     "_move_pipe",
        "set_scale":                "_move_set_scale",
        "design_area":              "_move_design_area",
        "polyline":                 "_move_polyline",
        "draw_line":                "_move_draw_line",
        "draw_gridline":            "_move_draw_line",
        "draw_rectangle":           "_move_draw_rectangle",
        "draw_circle":              "_move_draw_circle",
        "polygon":                  "_move_polygon",
        "draw_arc":                 "_move_draw_arc",
        "dimension":                "_move_dimension",
        "text":                     "_move_text",
        "place_import":             "_move_place_import",
        "offset":                   "_move_offset",
        "offset_side":              "_move_offset_side",
        "move":                     "_move_paste_move",
        "sprinkler":                "_move_preview_node",
        "paste":                    "_move_paste_move",
        "water_supply":             "_move_preview_node",
        "rotate":                   "_move_rotate",
        "mirror":                   "_move_mirror",
        "stretch":                  "_move_stretch",
        "wall":                     "_move_wall_router",
        "floor":                    "_move_floor_router",
        "roof":                     "_move_roof",
        "roof_rect":                "_move_roof_rect",
        "room_manual":              "_move_room_manual",
        "opening":                  "_move_opening",
        "door":                     "_move_door_window",
        "window":                   "_move_door_window",
        "detail":                   "_move_detail",
        "align":                    "_move_align",
        "gridline_array":           "_move_gridline_replicate",
        "gridline_offset":          "_move_gridline_replicate",
    }

    # Mode -> name of the method that redraws the placement preview from an
    # already-resolved point/transform.  Mouse-move calls it after constraining
    # the cursor; the Dynamic Input field-commit path calls it with the point a
    # typed value resolves to.  One preview code path, no divergence.
    _PREVIEW_DISPATCH = {
        "draw_line":       "_preview_from_line",
        "draw_gridline":   "_preview_from_line",
        "polyline":        "_preview_from_polyline",
        "draw_rectangle":  "_preview_from_rectangle",
        "draw_circle":     "_preview_from_circle",
        "polygon":         "_preview_from_polygon",
        "move":            "_preview_from_move",
        "gridline_offset": "_preview_from_gridline_replicate",
        "gridline_array":  "_preview_from_gridline_replicate",
        "draw_arc":        "_preview_from_arc",
    }

    def _preview_from_resolved(self, resolved) -> None:
        """Redraw the current mode's placement preview from ``resolved``.

        ``resolved`` is a ``QPointF``.  Placement helpers (line/rect/circle/
        polyline) use it directly as the second point; the two transform
        helpers (move, gridline replicate) derive their scalar — offset or
        spacing — from it internally, keeping that derivation in one place so
        the mouse path and any future typed path stay identical.  A no-op when
        the mode has no preview helper.
        """
        name = self._PREVIEW_DISPATCH.get(self.mode)
        if name is not None:
            getattr(self, name)(resolved)

    # ── Per-mode move handlers ──────────────────────────────────────────

    def _move_pipe(self, event, snapped):
        return self._pipe_ctl.move_pipe(event, snapped)

    def _move_set_scale(self, event, snapped):
        self.update_preview_node(snapped)
        if self._cal_point1 is not None:
            self.preview_pipe.setLine(
                self._cal_point1.x(), self._cal_point1.y(),
                snapped.x(), snapped.y()
            )
            self.preview_pipe.show()
        else:
            self.preview_pipe.hide()

    def _move_design_area(self, event, snapped):
        self.preview_node.hide()
        self.preview_pipe.hide()
        if self._design_area_corner1 is not None and self._design_area_rect_item is not None:
            c1 = self._design_area_corner1
            rect = QRectF(c1, snapped).normalized()
            self._design_area_rect_item.setRect(rect)

    def _preview_from_polyline(self, tip) -> None:
        """Extend the active polyline's rubber-band to ``tip``.

        ``tip`` is already constrained/resolved.  A no-op before the first
        vertex exists.  Polyline draws its preview through the item's own
        ``update_preview`` rather than ``preview_pipe``, so it does not share
        ``_preview_from_line``.
        """
        if self._polyline_active is None:
            return
        self._polyline_active.update_preview(tip)

    # ── Polyline close-indicator ring ────────────────────────────────────────

    _POLYLINE_CLOSE_RING_PX = 14  # half-side of the bounding square, screen px

    def _show_polyline_close_indicator(self, pt: QPointF) -> None:
        """Show (lazily-create) the hollow ring on *pt* signalling close-cue.

        The ring is a fixed screen-size QGraphicsEllipseItem with
        ItemIgnoresTransformations — it stays 14 px radius regardless of zoom,
        exactly like the design-area highlight rings in ``_refresh_da_highlights``.
        Coloured with ``SELECTION_OUTLINE_COLOR`` so it reads as a selection
        action, clearly distinct from the yellow/green snap dot.
        """
        r = self._POLYLINE_CLOSE_RING_PX
        if self._polyline_close_indicator is None:
            ring = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
            pen = QPen(QColor(SELECTION_OUTLINE_COLOR), 2)
            pen.setCosmetic(True)
            ring.setPen(pen)
            ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            ring.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            ring.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            ring.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            ring.setZValue(201)  # above Z_OVERLAY (200)
            self.addItem(ring)
            self._polyline_close_indicator = ring
        self._polyline_close_indicator.setPos(pt)
        self._polyline_close_indicator.show()

    def _hide_polyline_close_indicator(self) -> None:
        """Hide the close-cue ring (keeps the item alive for reuse)."""
        if self._polyline_close_indicator is not None:
            self._polyline_close_indicator.hide()

    def _move_polyline(self, event, snapped):
        if self._polyline_active is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._polyline_active is not None:
            pl = self._polyline_active
            pts = pl._points
            if len(pts) >= 3:
                scale = self._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                if math.hypot(snapped.x() - pts[0].x(), snapped.y() - pts[0].y()) <= tol:
                    self.update_preview_node(pts[0])
                    self._show_polyline_close_indicator(pts[0])
                    self._preview_from_polyline(pts[0])
                    # Keep the HUD readout live on the closing segment.
                    self.publish_placement_state(pts[-1], pts[0])
                    return
            self._hide_polyline_close_indicator()
            tip = snapped
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and len(self._polyline_active._points) >= 1):
                tip = self._constrain_angle(
                    self._polyline_active._points[-1], snapped
                )
            self._preview_from_polyline(tip)
            # Publishing here — after the Ctrl constraint — is what keeps the
            # readout and the HUD's seed from disagreeing with the preview.
            self.publish_placement_state(
                self._polyline_active._points[-1], tip)

    def _preview_from_line(self, tip) -> None:
        """Point the rubber-band line at ``tip`` (already constrained/resolved).

        Anchored at ``_draw_line_anchor`` — the ``draw_line``/``draw_gridline``
        first-click point.  A no-op before the anchor is armed.
        """
        anchor = self._draw_line_anchor
        if anchor is None:
            return
        self.preview_pipe.setLine(anchor.x(), anchor.y(), tip.x(), tip.y())
        self.preview_pipe.show()

    def _move_draw_line(self, event, snapped):
        _anchor = self._draw_line_anchor
        if _anchor is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        if _anchor is not None:
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._constrain_angle(_anchor, snapped)
            self._preview_from_line(tip)
            # Publishing here — after the Ctrl constraint — is what keeps
            # the readout and the HUD's seed from disagreeing.
            self.publish_placement_state(_anchor, tip)
        else:
            self.preview_pipe.hide()

    def _preview_from_rectangle(self, corner) -> None:
        """Redraw the rectangle preview to the resolved far ``corner``.

        Honours the from-centre branch (symmetric half-extents) and, in corner
        mode, the ``normalized()`` corner logic.  A no-op until both the anchor
        and the preview item exist.
        """
        if self._draw_rect_anchor is None or self._draw_rect_preview is None:
            return
        if self._draw_rect_from_center:
            # Center mode: anchor is center, rect extends symmetrically
            hw = abs(corner.x() - self._draw_rect_anchor.x())
            hh = abs(corner.y() - self._draw_rect_anchor.y())
            rect = QRectF(
                self._draw_rect_anchor.x() - hw,
                self._draw_rect_anchor.y() - hh,
                2 * hw, 2 * hh,
            )
        else:
            rect = QRectF(self._draw_rect_anchor, corner).normalized()
        self._draw_rect_preview.setRect(rect)

    def _preview_rectangle_rotation(self, angle_deg) -> None:
        """Spin the sized preview rect to ``angle_deg`` about the stored pivot.

        The rotate-step preview is **angle-driven**, not point-driven: the sized
        rect is fixed, only its orientation follows the cursor/typed angle.  Uses
        the same Qt transform ``RectangleItem.set_angle`` will — origin at the
        pivot, and the Y-up angle negated for Qt's CW-positive ``setRotation`` —
        so the ghost matches the committed item.  A no-op until the preview rect
        and the pivot both exist.
        """
        if self._draw_rect_preview is None or self._draw_rect_pivot is None:
            return
        self._draw_rect_preview.setTransformOriginPoint(self._draw_rect_pivot)
        self._draw_rect_preview.setRotation(-angle_deg)   # Y-up CCW → Qt CW negate
        self._update_rect_ref_lines(angle_deg)

    def _make_ref_line(self):
        """Create a dashed cosmetic angle-reference guide line, added to scene."""
        line = QGraphicsLineItem()
        pen = QPen(QColor(self._geom_color_lw()[0]), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        line.setPen(pen)
        line.setZValue(200)
        self.addItem(line)
        return line

    def _make_ref_circle(self):
        """Create a dashed cosmetic radius-reference circle, added to scene.

        Mirrors ``_make_ref_line``: dashed cosmetic pen, zValue 200, non-selectable.
        Callers position it via ``setRect``.  Stored as ``self._polygon_ref_circle``
        by the caller.
        """
        circle = QGraphicsEllipseItem()
        pen = QPen(QColor(self._geom_color_lw()[0]), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        circle.setPen(pen)
        circle.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        circle.setZValue(200)
        circle.setFlag(circle.GraphicsItemFlag.ItemIsSelectable, False)
        self.addItem(circle)
        return circle

    def _clear_polygon_ref_items(self) -> None:
        """Remove the polygon rotate-step reference circle and radial line."""
        for attr in ("_polygon_ref_circle", "_polygon_ref_lineA"):
            item = getattr(self, attr, None)
            if item is not None:
                if item.scene() is self:
                    self.removeItem(item)
                setattr(self, attr, None)

    def _set_arc_ref_lines(self) -> None:
        """Place the span-step arc guides: a 0° datum + the start-angle radial.

        Both are static through the span step (radius and start angle are fixed;
        only the sweep changes), so this runs once at the step-1→2 transition.
        The arc sweep runs from the start radial, so together they read as a
        protractor.  A no-op until the centre and both guides exist.
        """
        c = self._draw_arc_center
        if (c is None or self._draw_arc_ref_line0 is None
                or self._draw_arc_ref_start is None):
            return
        cx, cy, r = c.x(), c.y(), self._draw_arc_radius
        self._draw_arc_ref_line0.setLine(cx, cy, cx + r, cy)   # 0° datum
        sr = math.radians(self._draw_arc_start_deg)            # Y-up
        self._draw_arc_ref_start.setLine(
            cx, cy, cx + r * math.cos(sr), cy - r * math.sin(sr))

    def _update_arc_sweep_ref(self, cursor) -> None:
        """Point the live sweep radial from the centre to the arc endpoint.

        The endpoint sits on the radius circle at the cursor's bearing, so the
        radial ends exactly where the arc preview does.  A no-op until the sweep
        guide and centre exist.
        """
        c = self._draw_arc_center
        if c is None or self._draw_arc_ref_sweep is None:
            return
        cx, cy, r = c.x(), c.y(), self._draw_arc_radius
        end_deg = math.degrees(math.atan2(-(cursor.y() - cy), cursor.x() - cx))
        er = math.radians(end_deg)
        self._draw_arc_ref_sweep.setLine(
            cx, cy, cx + r * math.cos(er), cy - r * math.sin(er))

    def _clear_arc_ref_lines(self) -> None:
        """Remove the span-step arc guides from the scene."""
        for attr in ("_draw_arc_ref_line0", "_draw_arc_ref_start",
                     "_draw_arc_ref_sweep"):
            line = getattr(self, attr, None)
            if line is not None:
                if line.scene() is self:
                    self.removeItem(line)
                setattr(self, attr, None)

    def _update_rect_ref_lines(self, angle_deg) -> None:
        """Point the two rotate-step guides from the pivot (protractor).

        ``_draw_rect_ref_line0`` is the horizontal 0° datum; ``_draw_rect_ref_lineA``
        is the current sweep at ``angle_deg`` (Y-up).  Both run the sized rect's
        diagonal length so they frame the rectangle.  A no-op until both guides
        and the sized rect exist.
        """
        piv = self._draw_rect_pivot
        if (piv is None or self._draw_rect_ref_line0 is None
                or self._draw_rect_ref_lineA is None
                or self._draw_rect_sized_pt1 is None
                or self._draw_rect_sized_pt2 is None):
            return
        p1, p2 = self._draw_rect_sized_pt1, self._draw_rect_sized_pt2
        length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        rad = math.radians(angle_deg)
        self._draw_rect_ref_line0.setLine(piv.x(), piv.y(),
                                          piv.x() + length, piv.y())
        self._draw_rect_ref_lineA.setLine(
            piv.x(), piv.y(),
            piv.x() + length * math.cos(rad),
            piv.y() - length * math.sin(rad))   # Y-up: subtract sin

    def _clear_rect_ref_lines(self) -> None:
        """Remove both rotate-step guides from the scene."""
        for attr in ("_draw_rect_ref_line0", "_draw_rect_ref_lineA"):
            line = getattr(self, attr, None)
            if line is not None:
                if line.scene() is self:
                    self.removeItem(line)
                setattr(self, attr, None)

    def _clear_wall_rect_ref_lines(self) -> None:
        """Remove wall-rect rotate-step reference guides from the scene."""
        for attr in ("_wall_rect_ref_line0", "_wall_rect_ref_lineA"):
            line = getattr(self, attr, None)
            if line is not None:
                if line.scene() is self:
                    self.removeItem(line)
                setattr(self, attr, None)

    def _update_wall_rect_ref_lines(self, angle_deg) -> None:
        """Point the two wall-rect rotate-step guides from the pivot.

        Mirrors ``_update_rect_ref_lines``: a 0° datum + the live sweep line at
        ``angle_deg``, both diagonal-length so they frame the sized rectangle.
        A no-op until both guides and the sized rect exist.
        """
        piv = self._wall_rect_pivot
        if (piv is None or self._wall_rect_ref_line0 is None
                or self._wall_rect_ref_lineA is None
                or self._wall_rect_sized_pt1 is None
                or self._wall_rect_sized_pt2 is None):
            return
        p1, p2 = self._wall_rect_sized_pt1, self._wall_rect_sized_pt2
        length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        rad = math.radians(angle_deg)
        self._wall_rect_ref_line0.setLine(piv.x(), piv.y(),
                                          piv.x() + length, piv.y())
        self._wall_rect_ref_lineA.setLine(
            piv.x(), piv.y(),
            piv.x() + length * math.cos(rad),
            piv.y() - length * math.sin(rad))   # Y-up: subtract sin

    def _move_draw_rectangle(self, event, snapped):
        if self._draw_rect_rotating:
            # Rotate step: the sized rect is fixed; spin the ghost to the pivot→
            # cursor heading and publish so the HUD reads out the orientation.
            self.preview_node.hide()
            self.preview_pipe.hide()
            # Ctrl angle-snaps the rotation to ``_snap_angle_deg`` increments.
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._draw_rect_pivot is not None):
                snapped = self._constrain_angle(self._draw_rect_pivot, snapped)
            angle = self._rect_rotation_angle_to(snapped)
            self._preview_rectangle_rotation(angle)
            self.publish_placement_state(self._draw_rect_pivot, snapped)
            return
        if self._draw_rect_anchor is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._draw_rect_anchor is not None and self._draw_rect_preview is not None:
            self._preview_from_rectangle(snapped)
            # The HUD widget is the readout (S1).  Published unnormalised so the
            # signed extents reach the schema — normalising here would seed
            # from-centre-looking magnitudes and lose the dragged quadrant.
            self.publish_placement_state(self._draw_rect_anchor, snapped)

    def _preview_from_circle(self, rim) -> None:
        """Redraw the circle preview so ``rim`` lands on its circumference.

        The radius is the distance from ``_draw_circle_center`` to ``rim``.  A
        no-op until both the centre and the preview item exist.
        """
        if self._draw_circle_center is None or self._draw_circle_preview is None:
            return
        r = math.hypot(rim.x() - self._draw_circle_center.x(),
                       rim.y() - self._draw_circle_center.y())
        cx, cy = self._draw_circle_center.x(), self._draw_circle_center.y()
        self._draw_circle_preview.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def _move_draw_circle(self, event, snapped):
        if self._draw_circle_center is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._draw_circle_center is not None and self._draw_circle_preview is not None:
            self._preview_from_circle(snapped)
            # The HUD widget is the readout (S1); the rim point carries the
            # radius, since the commit takes the hypot.
            self.publish_placement_state(self._draw_circle_center, snapped)

    def _move_polygon(self, event, snapped):
        if self._polygon_rotating:
            # Rotate step: ghost is fixed-radius, only orientation changes.
            self.preview_node.hide()
            self.preview_pipe.hide()
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._polygon_center is not None):
                snapped = self._constrain_angle(self._polygon_center, snapped)
            angle = self._polygon_rotation_angle_to(snapped)
            self._preview_polygon_rotation(angle)
            self.publish_placement_state(self._polygon_center, snapped)
            return
        if self._polygon_center is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._polygon_center is not None:
            self._preview_from_polygon(snapped)
            self.publish_placement_state(self._polygon_center, snapped)

    def _preview_from_arc(self, resolved) -> None:
        """Redraw the arc preview from the resolved point ``resolved``.

        Step-aware, mirroring what ``_move_draw_arc`` draws so the mouse path and
        the Dynamic Input field-commit path share one preview updater:

        * step 1 points the radius line from the stored centre at ``resolved``;
        * step 2 rebuilds the arc sweep path from start deg to the bearing of
          ``resolved`` on the radius circle.

        A pure preview updater: no state mutation, no publish, and a no-op when
        the relevant preview item or the centre is None (before the first click,
        or between steps).
        """
        if self._draw_arc_center is None:
            return
        if self._draw_arc_step == 1:
            if self._draw_arc_radius_line is None:
                return
            cx = self._draw_arc_center.x()
            cy = self._draw_arc_center.y()
            self._draw_arc_radius_line.setLine(cx, cy,
                                               resolved.x(), resolved.y())
        elif self._draw_arc_step == 2:
            if self._draw_arc_preview is None:
                return
            cx = self._draw_arc_center.x()
            cy = self._draw_arc_center.y()
            r = self._draw_arc_radius
            end_deg = math.degrees(
                math.atan2(-(resolved.y() - cy), resolved.x() - cx)
            )
            span = end_deg - self._draw_arc_start_deg
            if span <= 0:
                span += 360.0
            path = QPainterPath()
            rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            path.arcMoveTo(rect, self._draw_arc_start_deg)
            path.arcTo(rect, self._draw_arc_start_deg, span)
            self._draw_arc_preview.setPath(path)

    def _move_draw_arc(self, event, snapped):
        self.preview_pipe.hide()
        if self._draw_arc_step == 0:
            # Before the first click there is no anchor, so no HUD; just track
            # the cursor.
            self.update_preview_node(snapped)
            return
        # Steps 1 and 2 draw through the shared preview updater and publish the
        # resolved point so the DynamicInputHud (decision S1) is the readout.
        # The painted ``_draw_dim_hint`` (block 4) is retired for arc: publish
        # clears it, so a mode that publishes state stops painting block 4.
        self.preview_node.hide()
        # Ctrl angle-snaps the centre→cursor ray (the radius/start bearing at
        # step 1, the sweep end at step 2) to ``_snap_angle_deg`` increments.
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and self._draw_arc_center is not None):
            snapped = self._constrain_angle(self._draw_arc_center, snapped)
        self._preview_from_arc(snapped)
        if self._draw_arc_step == 2:
            self._update_arc_sweep_ref(snapped)   # live sweep radial
        self.publish_placement_state(self._draw_arc_center, snapped)

    def _move_dimension(self, event, snapped):
        sm = self.scale_manager
        self.preview_pipe.hide()
        if self._dim_pending is not None:
            # Offset sub-mode: project cursor onto perpendicular of the base line
            dim = self._dim_pending
            p1 = dim._p1
            p2 = dim._p2
            mid_base = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            line_angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            perp = line_angle + math.pi / 2
            dx = snapped.x() - mid_base.x()
            dy = snapped.y() - mid_base.y()
            projected = dx * math.cos(perp) + dy * math.sin(perp)
            dim._offset_dist = projected
            dim.update_geometry()
            self.preview_node.hide()
        elif self.dimension_start is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
            # Show live preview line from first point to cursor
            p1 = self.dimension_start
            p2 = snapped
            if self._dim_preview_line is None:
                preview_pen = QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine)
                preview_pen.setCosmetic(True)
                self._dim_preview_line = QGraphicsLineItem()
                self._dim_preview_line.setPen(preview_pen)
                self._dim_preview_line.setZValue(200)
                self.addItem(self._dim_preview_line)
            self._dim_preview_line.setLine(p1.x(), p1.y(), p2.x(), p2.y())
            # Show live distance label
            dist = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            dist_text = (sm.scene_to_display(dist) if sm.is_calibrated
                         else f"{dist:.0f} mm")
            if self._dim_preview_label is None:
                self._dim_preview_label = QGraphicsTextItem()
                self._dim_preview_label.setDefaultTextColor(QColor("#ffffff"))
                f = QFont("Consolas", 10)
                self._dim_preview_label.setFont(f)
                self._dim_preview_label.setFlag(
                    self._dim_preview_label.GraphicsItemFlag.ItemIgnoresTransformations, True)
                self._dim_preview_label.setZValue(201)
                self.addItem(self._dim_preview_label)
            self._dim_preview_label.setPlainText(dist_text)
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            self._dim_preview_label.setPos(mid)

    def _move_text(self, event, snapped):
        sm = self.scale_manager
        self.preview_pipe.hide()
        if self._text_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
            if self._text_preview is not None:
                rect = QRectF(self._text_anchor, snapped).normalized()
                self._text_preview.setRect(rect)
                self._draw_dim_hint = (
                    f"W: {sm.scene_to_display(rect.width())}  "
                    f"H: {sm.scene_to_display(rect.height())}"
                    if sm.is_calibrated else
                    f"W: {rect.width():.0f}mm  H: {rect.height():.0f}mm"
                )

    def _move_place_import(self, event, snapped):
        self.preview_node.hide()
        self.preview_pipe.hide()
        self._underlay_ctl._update_place_import_ghost(snapped)

    def _move_offset(self, event, snapped):
        self.preview_node.hide()
        self.preview_pipe.hide()

    def _move_offset_side(self, event, snapped):
        self.preview_node.hide()
        self.preview_pipe.hide()
        if self._offset_source is not None:
            # Compute distance from cursor to source entity
            if not getattr(self, '_offset_manual', False):
                self._offset_dist = self._tools._perpendicular_distance(
                    self._offset_source, snapped)
            if self._offset_dist > 0:
                sd = self._tools._offset_signed_dist(
                    self._offset_source, self._offset_dist, snapped)
                self._tools._clear_offset_preview()
                preview = self._tools._make_offset_item(self._offset_source, sd)
                if preview is not None:
                    pen = preview.pen()
                    pen.setStyle(Qt.PenStyle.DashLine)
                    preview.setPen(pen)
                    preview.setZValue(200)
                    self.addItem(preview)
                    self._offset_preview = preview
                self._show_status(
                    f"Offset: {self._offset_dist:.1f} mm  "
                    f"(Tab = type distance, click to commit)", timeout=0)

    def _move_preview_node(self, event, snapped):
        self.update_preview_node(snapped)
        self.preview_pipe.hide()

    def _preview_from_move(self, target) -> None:
        """Slide the move/paste ghost silhouette so the base point lands on
        ``target``.

        Rebuilds ``_move_ghost`` (read by ``drawForeground`` block 8) as the
        base silhouette translated by ``target - node_start_pos`` and repaints.
        A no-op before the base point is set.
        """
        if self.node_start_pos is None:
            return
        offset = QPointF(target.x() - self.node_start_pos.x(),
                         target.y() - self.node_start_pos.y())
        self._move_ghost = [p.translated(offset.x(), offset.y())
                            for p in self._move_ghost_base]
        for v in self.views():
            v.viewport().update()

    def _move_paste_move(self, event, snapped):
        """Ghost preview for paste/move: silhouette rides the cursor after the
        base point is set. Before that, show the plain cursor marker."""
        if self.node_start_pos is None:
            self.update_preview_node(snapped)
            self.preview_pipe.hide()
            return
        self.preview_node.hide()
        self.preview_pipe.hide()
        offset = QPointF(snapped.x() - self.node_start_pos.x(),
                         snapped.y() - self.node_start_pos.y())
        self._preview_from_move(snapped)
        # Feed the dynamic-input HUD its live dX/dY seed (measured from the
        # base point in ``_transform_seed_values``).  The status-bar readout
        # below is a separate surface and stays: S1 retired the painted
        # on-canvas Dim HUD, which move never used, not the status line — and
        # it carries ``dist``, which the two-field HUD does not.  A no-op while
        # a field has focus, so a mid-edit reseed cannot land.  ``paste`` also
        # reaches here, harmlessly: it has no schema, so nothing seeds from it.
        self.publish_placement_state(self.node_start_pos, snapped)
        self._show_status(
            f"dx={offset.x():.1f}  dy={-offset.y():.1f}  "
            f"dist={math.hypot(offset.x(), offset.y()):.1f}", timeout=0)

    def _move_rotate(self, event, snapped):
        if self._rotate_pivot is None:
            return
        self.preview_node.hide()
        self.preview_pipe.hide()
        if self._rotate_preview_line is None:
            self._rotate_preview_line = QGraphicsLineItem()
            p = QPen(QColor("#00aaff"), 0); p.setCosmetic(True)
            p.setStyle(Qt.PenStyle.DashLine)
            self._rotate_preview_line.setPen(p)
            self._rotate_preview_line.setZValue(200)
            self.addItem(self._rotate_preview_line)
        self._rotate_preview_line.setLine(
            self._rotate_pivot.x(), self._rotate_pivot.y(),
            snapped.x(), snapped.y())
        self._rotate_preview_line.show()
        dx = snapped.x() - self._rotate_pivot.x()
        dy = snapped.y() - self._rotate_pivot.y()
        angle = math.degrees(math.atan2(-dy, dx))
        self._show_status(f"Rotate: {angle:.1f}°", timeout=0)

    def _move_mirror(self, event, snapped):
        if self._mirror_p1 is None:
            return
        self.preview_node.hide()
        self.preview_pipe.hide()
        if self._mirror_preview_line is None:
            self._mirror_preview_line = QGraphicsLineItem()
            p = QPen(QColor("#ff00ff"), 0); p.setCosmetic(True)
            p.setStyle(Qt.PenStyle.DashDotLine)
            self._mirror_preview_line.setPen(p)
            self._mirror_preview_line.setZValue(200)
            self.addItem(self._mirror_preview_line)
        self._mirror_preview_line.setLine(
            self._mirror_p1.x(), self._mirror_p1.y(),
            snapped.x(), snapped.y())
        self._mirror_preview_line.show()

    def _move_stretch(self, event, snapped):
        if self._stretch_base is None:
            return
        self.preview_node.hide()
        self.preview_pipe.hide()
        if self._stretch_preview_line is None:
            self._stretch_preview_line = QGraphicsLineItem()
            p = QPen(QColor("#00aaff"), 0); p.setCosmetic(True)
            p.setStyle(Qt.PenStyle.DashLine)
            self._stretch_preview_line.setPen(p)
            self._stretch_preview_line.setZValue(200)
            self.addItem(self._stretch_preview_line)
        self._stretch_preview_line.setLine(
            self._stretch_base.x(), self._stretch_base.y(),
            snapped.x(), snapped.y())
        self._stretch_preview_line.show()
        dx = snapped.x() - self._stretch_base.x()
        dy = snapped.y() - self._stretch_base.y()
        self._show_status(f"Stretch: dx={dx:.1f}  dy={dy:.1f}", timeout=0)

    def _move_wall(self, event, snapped):
        sm = self.scale_manager
        if self._wall_anchor is None:
            self.update_preview_node(snapped)
            if self._wall_preview_rect is not None:
                self._wall_preview_rect.hide()
        else:
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._constrain_angle(self._wall_anchor, snapped)
            self.preview_pipe.setLine(
                self._wall_anchor.x(), self._wall_anchor.y(),
                tip.x(), tip.y()
            )
            self.preview_pipe.show()
            self.preview_node.hide()
            _dx = tip.x() - self._wall_anchor.x()
            _dy = tip.y() - self._wall_anchor.y()
            _len = math.hypot(_dx, _dy)
            self._draw_dim_hint = (
                f"L: {sm.scene_to_display(_len)}"
                if sm.is_calibrated else
                f"L: {_len:.0f}mm"
            )
            self.publish_placement_state(self._wall_anchor, tip)
            # -- Wall thickness preview rectangle --
            if _len > 1.0:  # avoid degenerate preview
                if self._wall_preview_rect is None:
                    self._wall_preview_rect = QGraphicsPathItem()
                    _ppn = QPen(QColor("#aaaaaa"), 1, Qt.PenStyle.DashLine)
                    _ppn.setCosmetic(True)
                    self._wall_preview_rect.setPen(_ppn)
                    _fill = QColor("#cccccc")
                    _fill.setAlpha(30)
                    self._wall_preview_rect.setBrush(QBrush(_fill))
                    self._wall_preview_rect.setZValue(199)
                    self.addItem(self._wall_preview_rect)
                _wtmpl = self._get_wall_template()
                p1l, p1r, p2r, p2l = compute_wall_quad(
                    self._wall_anchor, tip, _wtmpl._thickness_mm,
                    _wtmpl._alignment, self.scale_manager)
                _pp = QPainterPath()
                _pp.moveTo(p1l)
                _pp.lineTo(p2l)
                _pp.lineTo(p2r)
                _pp.lineTo(p1r)
                _pp.closeSubpath()
                self._wall_preview_rect.setPath(_pp)
                self._wall_preview_rect.show()

    def _move_floor(self, event, snapped):
        if self._floor_active is None:
            self.update_preview_node(snapped)
            self.preview_pipe.hide()
        else:
            self.preview_node.hide()
            # Rubber-band line from last vertex to cursor
            last_pt = self._floor_active._points[-1]
            self.preview_pipe.setLine(
                last_pt.x(), last_pt.y(), snapped.x(), snapped.y())
            pen = QPen(QColor(self._floor_active._color), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self.preview_pipe.setPen(pen)
            self.preview_pipe.show()
            # Publish the resolved cursor every frame so the passive HUD seeds
            # a live per-segment Length/Angle from ``last_pt`` (the anchor
            # ``get_placement_anchor`` returns for a floor polygon).  Mirrors
            # ``_move_wall``; without it ``get_resolved_point()`` stays None and
            # the ``line`` schema seeds ``seed(anchor, anchor)`` — a frozen 0mm/0°
            # readout.  ``_draw_dim_hint`` is the legacy painted string and is
            # dead under the HUD design (``publish_placement_state`` clears it).
            self.publish_placement_state(last_pt, snapped)

    def _move_wall_rect(self, event, snapped):
        """Mouse-move preview for the wall rectangle primitive.

        Rotate step: spins the preview rect + updates ref guides (mirrors
        ``_move_draw_rectangle`` rotate branch).  Sizing step: updates the
        axis-aligned preview rect and wall-thickness overlay (existing logic,
        now also handles centre mode via ``rect_sizing_points``).
        """
        sm = self.scale_manager
        if self._wall_rect_rotating:
            # Rotate step: spin the sized preview rect about the pivot.
            self.preview_node.hide()
            self.preview_pipe.hide()
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._wall_rect_pivot is not None):
                snapped = self._constrain_angle(self._wall_rect_pivot, snapped)
            angle = self._wall_rect_rotation_angle_to(snapped)
            if self._wall_rect_preview is not None and self._wall_rect_pivot is not None:
                self._wall_rect_preview.setTransformOriginPoint(self._wall_rect_pivot)
                self._wall_rect_preview.setRotation(-angle)   # Y-up CCW → Qt CW negate
            self._update_wall_rect_ref_lines(angle)
            self.publish_placement_state(self._wall_rect_pivot, snapped)
            return
        if self._wall_rect_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._wall_rect_anchor is not None and self._wall_rect_preview is not None:
            from .construction_geometry import rect_sizing_points
            anc = self._wall_rect_anchor
            pt1, pt2 = rect_sizing_points(anc, snapped, self._wall_rect_from_center)
            rect = QRectF(pt1, pt2).normalized()
            self._wall_rect_preview.setRect(rect)
            self._draw_dim_hint = (
                f"W: {sm.scene_to_display(rect.width())}  "
                f"H: {sm.scene_to_display(rect.height())}"
            )
            self.publish_placement_state(anc, snapped)
            # -- Wall thickness preview (4 quads around rectangle) --
            if rect.width() > 1.0 and rect.height() > 1.0:
                if self._wall_rect_thickness_preview is None:
                    self._wall_rect_thickness_preview = QGraphicsPathItem()
                    _ppn = QPen(QColor("#aaaaaa"), 1, Qt.PenStyle.DashLine)
                    _ppn.setCosmetic(True)
                    self._wall_rect_thickness_preview.setPen(_ppn)
                    _fill = QColor("#cccccc")
                    _fill.setAlpha(30)
                    self._wall_rect_thickness_preview.setBrush(QBrush(_fill))
                    self._wall_rect_thickness_preview.setZValue(199)
                    self.addItem(self._wall_rect_thickness_preview)
                _wtmpl = self._get_wall_template()
                _ra = _wtmpl._alignment
                corners = [
                    QPointF(rect.x(), rect.y()),
                    QPointF(rect.x() + rect.width(), rect.y()),
                    QPointF(rect.x() + rect.width(), rect.y() + rect.height()),
                    QPointF(rect.x(), rect.y() + rect.height()),
                ]
                _pp = QPainterPath()
                for i in range(4):
                    p1 = corners[i]
                    p2 = corners[(i + 1) % 4]
                    q1l, q1r, q2r, q2l = compute_wall_quad(
                        p1, p2, _wtmpl._thickness_mm, _ra, sm)
                    _pp.moveTo(q1l)
                    _pp.lineTo(q2l)
                    _pp.lineTo(q2r)
                    _pp.lineTo(q1r)
                    _pp.closeSubpath()
                self._wall_rect_thickness_preview.setPath(_pp)
                self._wall_rect_thickness_preview.show()

    def _move_floor_rect(self, event, snapped):
        """Mouse-move preview for the floor rectangle primitive.

        Rotate step: spins the sized preview rect about the pivot + updates ref
        guides + publishes the orientation.  Sizing step: updates the
        axis-aligned preview rect (corner or centre) and publishes the far
        corner.  Mirrors ``_move_wall_rect`` (minus the wall thickness overlay).
        """
        sm = self.scale_manager
        if self._floor_rect_rotating:
            # Rotate step: spin the sized preview rect about the pivot.
            self.preview_node.hide()
            self.preview_pipe.hide()
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._floor_rect_pivot is not None):
                snapped = self._constrain_angle(self._floor_rect_pivot, snapped)
            angle = self._floor_rect_rotation_angle_to(snapped)
            if (self._floor_rect_preview is not None
                    and self._floor_rect_pivot is not None):
                self._floor_rect_preview.setTransformOriginPoint(self._floor_rect_pivot)
                self._floor_rect_preview.setRotation(-angle)   # Y-up CCW → Qt CW negate
            self._update_floor_rect_ref_lines(angle)
            self.publish_placement_state(self._floor_rect_pivot, snapped)
            return
        if self._floor_rect_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._floor_rect_anchor is not None and self._floor_rect_preview is not None:
            from .construction_geometry import rect_sizing_points
            anc = self._floor_rect_anchor
            pt1, pt2 = rect_sizing_points(anc, snapped, self._floor_rect_from_center)
            rect = QRectF(pt1, pt2).normalized()
            self._floor_rect_preview.setRect(rect)
            self._draw_dim_hint = (
                f"W: {sm.scene_to_display(rect.width())}  "
                f"H: {sm.scene_to_display(rect.height())}"
            )
            self.publish_placement_state(anc, snapped)

    def _move_roof(self, event, snapped):
        sm = self.scale_manager
        if self._roof_active is None:
            self.update_preview_node(snapped)
            self.preview_pipe.hide()
        else:
            self.preview_node.hide()
            last_pt = self._roof_active._points[-1]
            self.preview_pipe.setLine(
                last_pt.x(), last_pt.y(), snapped.x(), snapped.y())
            pen = QPen(QColor(self._roof_active._color), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self.preview_pipe.setPen(pen)
            self.preview_pipe.show()
            _dx = snapped.x() - last_pt.x()
            _dy = snapped.y() - last_pt.y()
            _len = math.hypot(_dx, _dy)
            _ang = math.degrees(math.atan2(-_dy, _dx))
            self._draw_dim_hint = f"L: {sm.scene_to_display(_len)}  A: {_ang:.1f}°"

    def _move_roof_rect(self, event, snapped):
        sm = self.scale_manager
        if self._roof_rect_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._roof_rect_anchor is not None and self._roof_rect_preview is not None:
            rect = QRectF(self._roof_rect_anchor, snapped).normalized()
            self._roof_rect_preview.setRect(rect)
            self._draw_dim_hint = (
                f"W: {sm.scene_to_display(rect.width())}  "
                f"H: {sm.scene_to_display(rect.height())}"
            )

    def _move_door_window(self, event, snapped):
        self.update_preview_node(snapped)

    # ── Gridline Array / Offset replication (Task 7) ────────────────────

    def _start_gridline_replicate(self, source, kind):
        """Enter array or offset replication mode for *source* gridline.

        Args:
            source: The :class:`GridlineItem` to replicate.
            kind: ``"array"`` for multiple evenly-spaced copies,
                  ``"offset"`` for a single copy at cursor distance.
        """
        self._replicate_source = source
        self._replicate_kind = kind
        self._replicate_count = 1
        self._replicate_spacing = 0.0
        self._replicate_ghost = []
        self.set_mode("gridline_offset" if kind == "offset" else "gridline_array")
        self.instructionChanged.emit(
            "Move to set spacing/side · type or Tab for exact · Enter=place · Esc=cancel"
        )

    def _build_replicate_ghost(self, spacing):
        """Compute ghost preview line segments for the current replicate state.

        Args:
            spacing: Signed perpendicular distance (mm) per step.

        Returns:
            List of ``(QPointF origin, QPointF far)`` tuples.
        """
        src = self._replicate_source
        if src is None:
            return []
        nx, ny = src._perpendicular_vector()
        th = math.radians(src._angle_deg)
        dxl = src._length * math.cos(th)
        dyl = -src._length * math.sin(th)   # Y-up → scene Y-down
        n = 1 if self._replicate_kind == "offset" else max(0, int(self._replicate_count))
        ghost = []
        for i in range(1, n + 1):
            ox = src._origin.x() + nx * spacing * i
            oy = src._origin.y() + ny * spacing * i
            ghost.append((QPointF(ox, oy), QPointF(ox + dxl, oy + dyl)))
        return ghost

    def _preview_from_gridline_replicate(self, cursor) -> None:
        """Rebuild the replicate ghost from a resolved ``cursor`` point.

        Projects ``cursor`` onto the source gridline's perpendicular to get the
        signed spacing, stores it in ``_replicate_spacing``, rebuilds
        ``_replicate_ghost`` (read by ``drawForeground`` block 7) and repaints.
        A no-op with no source.

        Unlike the placement helpers this takes the cursor **point** rather than
        the resolved scalar: the mouse-move path derives the spacing from the
        cursor here, so keeping that derivation in one place is what makes the
        preview identical to the mouse's.
        """
        src = self._replicate_source
        if src is None:
            return
        nx, ny = src._perpendicular_vector()
        o = src._origin
        # Signed perpendicular distance from source origin to cursor
        self._replicate_spacing = (
            (cursor.x() - o.x()) * nx + (cursor.y() - o.y()) * ny
        )
        self._replicate_ghost = self._build_replicate_ghost(self._replicate_spacing)
        for v in self.views():
            v.viewport().update()

    def _move_gridline_replicate(self, event, snapped):
        """Move handler for gridline_array / gridline_offset modes.

        Computes signed perpendicular distance from source to cursor and
        rebuilds the ghost preview overlay.
        """
        if self._replicate_source is None:
            return
        self._preview_from_gridline_replicate(snapped)
        # The readout is the ``DynamicInputHud`` widget, which seeds from
        # ``_replicate_spacing``/``_replicate_count`` directly (transform
        # schemas have no cursor-derived inverse).  Publishing here only clears
        # the painted hint, so this mode cannot leave a second readout on the
        # glass beside the widget (decision S1).  There is no anchor and no
        # resolved point to publish — the geometry is a signed scalar, not a
        # point.
        self.publish_placement_state(None, None)

    def _press_gridline_replicate(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Press handler for gridline_array / gridline_offset modes: commit."""
        self._commit_gridline_replicate()

    def _replicate_side_sign(self) -> float:
        """Return which side of the source the cursor put the ghost on.

        ``+1`` or ``-1``, matching the sign of the perpendicular projection.
        Zero — the cursor sitting on the source, or never having moved — reads
        as the positive side; nothing is placed at that spacing anyway, since
        the commit floor rejects it.
        """
        return -1.0 if self._replicate_spacing < 0.0 else 1.0

    def _apply_gridline_offset(self, params: dict) -> bool:
        """Place one copy at a typed distance (transform schema — dict, not point).

        The typed value is a **magnitude**; the side comes from where the
        cursor had the ghost when the HUD was engaged.  Enter places rather
        than merely redrawing the preview: the HUD is torn down on a successful
        commit and the next mouse move recomputes ``_replicate_spacing`` from
        the cursor, so a preview-only applier would silently discard the number
        the user typed.

        Args:
            params: ``resolve_distance``'s output — ``{"distance": float}``.

        Returns:
            The commit verdict (decision D2): False when the distance is under
            the too-close floor, which keeps the HUD open over a live
            placement.
        """
        return self._commit_gridline_replicate_at(
            params["distance"] * self._replicate_side_sign())

    def _apply_gridline_array(self, params: dict) -> bool:
        """Place *count* copies at a typed spacing.

        As :meth:`_apply_gridline_offset`, plus the count.  The count is
        accepted independently of the spacing: on a refusal the ghost is
        rebuilt with it, so what the user is left retyping against shows the
        number of copies they asked for rather than the previous one.

        Args:
            params: ``resolve_spacing_count``'s output — ``{"spacing": float,
                "count": int}``.

        Returns:
            The commit verdict (decision D2).
        """
        self._replicate_count = params["count"]
        placed = self._commit_gridline_replicate_at(
            params["spacing"] * self._replicate_side_sign())
        if not placed:
            self._replicate_ghost = self._build_replicate_ghost(
                self._replicate_spacing)
            for v in self.views():
                v.viewport().update()
        return placed

    def _commit_gridline_replicate(self) -> bool:
        """Place the copies at the cursor-derived spacing (click/Enter path)."""
        return self._commit_gridline_replicate_at(self._replicate_spacing)

    def _commit_gridline_replicate_at(self, dist: float) -> bool:
        """Place the replicated gridline copies as a single undo step.

        The commit half of :meth:`_press_gridline_replicate`, split out so
        Dynamic Input supplies a *distance* rather than duplicating the
        placement.  The too-close floor lives here and nowhere else — the
        schema deliberately does not mirror it (decision D2).

        Args:
            dist: Signed perpendicular distance per step, in scene units.

        Returns:
            True when copies were placed, False when the commit was refused.
            A refusal leaves the source armed and the ghost up so the distance
            can simply be retyped or re-picked; this path used to cancel
            replicate mode outright, which left a typed refusal with nothing to
            correct.
        """
        src = self._replicate_source
        if src is None:
            self._end_gridline_replicate()
            return False
        is_array = self._replicate_kind != "offset"
        if abs(dist) < 0.5:
            self._show_status(
                "Array spacing too small — skipped" if is_array
                else "Offset distance too small — skipped", timeout=2000)
            return False
        copies = (src.array_copies(dist, self._replicate_count) if is_array
                  else [src.offset_copy(dist)])
        if not copies:
            # A non-positive count — the factory's own refusal, not a distance
            # problem.  Reported the same way rather than silently, and it
            # leaves the placement live so the count can be retyped.
            self._show_status("Array count must be at least 1 — skipped",
                              timeout=2000)
            return False
        # Fresh sequential labels: sync counters past existing, then auto-label
        sync_grid_counters(self._gridlines)
        for cp in copies:
            gp = cp.grip_points()
            cp.grid_label = auto_label(gp[0], gp[1])
            self._register_gridline(cp)      # addItem + apply_category_defaults + append
        apply_duplicate_warnings(self._gridlines)
        self.push_undo_state()
        self._end_gridline_replicate()
        return True

    def _end_gridline_replicate(self):
        """Cancel or finish replication: clear state and return to select."""
        self._replicate_source = None
        self._replicate_ghost = []
        # Full clear, not just the readout: this returns to select mode, so a
        # bare hint reset would leave the cancelled placement's resolved point
        # readable until the next mouse-move republished or cleared it.
        self.clear_placement_state()
        self.set_mode("select")
        for v in self.views():
            v.viewport().update()

    # ── Dispatch table: mode string → press-handler method name ──────
    # Point-asking PLACEMENT modes — every command whose press picks a free
    # point in the scene to draw new geometry or drop a placed item.  This is
    # the authoritative "arm ALIGN" set (spec 2026-08-26: universal client
    # scope): both the ALIGN tier in ``get_effective_position`` and the dwell
    # feed gate on ``_align_active_item is not None``, so ALIGN is silently
    # inert in any placement mode omitted here.
    #
    # Defined POSITIVELY (membership) rather than as a hand-maintained literal
    # in ``set_mode``: it is the subset of ``_PRESS_DISPATCH`` whose handler
    # resolves a cursor point through ``get_effective_position`` and places
    # there.  Deliberately EXCLUDES:
    #   • ``select`` / ``None``            — no point placed
    #   • object-pick transforms/modifies  — rotate, scale, mirror, break,
    #     break_at_point, fillet, chamfer, stretch, trim(_pick), extend(_pick),
    #     merge_points, offset(_side), align, the two constraint pickers, room
    #     (click-inside-region), place_import (ghost drag, no snap point)
    # ``move``/``paste`` are placement (destination point) AND self-exclude the
    # moved item; they stay armed here and the press path swaps the sentinel for
    # the real self-exclude item.
    _ALIGN_PLACEMENT_MODES = frozenset({
        "draw_line", "draw_gridline", "draw_rectangle", "draw_circle",
        "draw_arc", "polyline", "polygon", "pipe", "sprinkler",
        "dimension", "text", "set_scale", "water_supply", "design_area",
        "wall", "floor", "roof", "roof_rect", "room_manual",
        "opening", "door", "window", "detail",
        "gridline_offset", "gridline_array",
        "move", "paste",
    })

    _PRESS_DISPATCH = {
        None:                       "_press_select_item",
        "select":                   "_press_select_item",
        "sprinkler":                "_press_sprinkler",
        "pipe":                     "_press_pipe",
        "set_scale":                "_press_set_scale",
        "dimension":                "_press_dimension",
        "text":                     "_press_text",
        "draw_arc":                 "_press_draw_arc",
        "draw_gridline":            "_press_draw_line",
        "water_supply":             "_press_water_supply",
        "design_area":              "_press_design_area",
        "room":                     "_press_room",
        "room_manual":              "_press_room_manual",
        "paste":                    "_press_paste_move",
        "move":                     "_press_paste_move",
        "place_import":             "_press_place_import",
        "offset":                   "_press_offset",
        "offset_side":              "_press_offset_side",
        "rotate":                   "_press_rotate",
        "scale":                    "_press_scale",
        "mirror":                   "_press_mirror",
        "break":                    "_press_break",
        "break_at_point":           "_press_break_at_point",
        "fillet":                   "_press_fillet",
        "chamfer":                  "_press_chamfer",
        "stretch":                  "_press_stretch",
        "trim":                     "_press_trim",
        "trim_pick":                "_press_trim",
        "extend":                   "_press_extend",
        "extend_pick":              "_press_extend",
        "merge_points":             "_press_merge_hatch",
        "constraint_concentric":    "_press_constraint",
        "constraint_dimensional":   "_press_constraint",
        "align":                    "_press_align",
        "polyline":                 "_press_polyline",
        "draw_line":                "_press_draw_line",
        "draw_rectangle":           "_press_draw_rectangle",
        "draw_circle":              "_press_draw_circle",
        "polygon":                  "_press_polygon",
        "wall":                     "_press_wall_router",
        "floor":                    "_press_floor_router",
        "roof":                     "_press_roof",
        "roof_rect":                "_press_roof_rect",
        "opening":                  "_press_opening",
        "door":                     "_press_door",
        "window":                   "_press_window",
        "detail":                   "_press_detail",
        "gridline_array":           "_press_gridline_replicate",
        "gridline_offset":          "_press_gridline_replicate",
    }

    # ------------------------------------------------------------------
    # Dialog callbacks — called by main.py after showing the dialog
    # ------------------------------------------------------------------

    def complete_numeric_input(self, mode: str, value: float, accepted: bool):
        """Handle result from a numeric input dialog shown by main.py."""
        if not accepted:
            return
        if mode == "offset_side":
            self._offset_dist = value
            self._offset_manual = True
            self._show_status(
                f"Offset: {value:.1f} mm (fixed)  "
                f"Click to pick side and commit.", timeout=0)
        elif mode == "rotate":
            if self._rotate_pivot is not None:
                self._tools._apply_rotate(self._rotate_pivot, value)
                self.push_undo_state()
                self._selected_items = []
                self.set_mode(None)
        elif mode == "scale":
            if self._scale_base is not None:
                self._tools._apply_scale(self._scale_base, value)
                self.push_undo_state()
                self._selected_items = []
                self.set_mode(None)
        elif mode == "fillet":
            self._fillet_radius = value
            if self._fillet_preview is not None:
                if self._fillet_preview.scene() is self:
                    self.removeItem(self._fillet_preview)
                self._fillet_preview = None
            data = self._tools._compute_fillet(self._fillet_item1, self._fillet_item2,
                                        self._fillet_radius)
            if data is not None:
                pp = QPainterPath()
                pp.addEllipse(data["center"], data["radius"], data["radius"])
                self._fillet_preview = self.addPath(
                    pp, QPen(QColor("#00ff00"), 1, Qt.PenStyle.DashLine))
            self._show_status(
                f"Fillet radius: {value:.1f}  Press Enter to commit", timeout=0)
        elif mode == "chamfer":
            self._chamfer_dist = value
            if self._chamfer_preview is not None:
                if self._chamfer_preview.scene() is self:
                    self.removeItem(self._chamfer_preview)
                self._chamfer_preview = None
            data = self._tools._compute_chamfer(self._chamfer_item1, self._chamfer_item2,
                                          self._chamfer_dist)
            if data is not None:
                self._chamfer_preview = QGraphicsLineItem(
                    data["cp1"].x(), data["cp1"].y(),
                    data["cp2"].x(), data["cp2"].y())
                p = QPen(QColor("#00ff00"), 1, Qt.PenStyle.DashLine)
                p.setCosmetic(True)
                self._chamfer_preview.setPen(p)
                self.addItem(self._chamfer_preview)
            self._show_status(
                f"Chamfer distance: {value:.1f}  Press Enter to commit", timeout=0)

    def complete_confirmation(self, action_id: str, result: str):
        """Handle result from a confirmation dialog shown by main.py.

        *result* is ``"accepted"``/``"rejected"`` for legacy Yes/No dialogs,
        or ``"riser"``/``"match"``/``"template"`` for elevation-mismatch dialogs.
        """
        if action_id == "mirror_delete" and result == "accepted":
            for item in list(self._selected_items or self.selectedItems()):
                self._delete_single_item(item)
            self.push_undo_state()

        elif action_id == "elev_mismatch_start":
            self._pipe_ctl.resume_elev_mismatch("start", result)
        elif action_id == "elev_mismatch_end":
            self._pipe_ctl.resume_elev_mismatch("end", result)

    def mousePressEvent(self, event):
        # A click ends any pending left-Shift tap: Shift+click is a modifier
        # use (multi-select), not a tap, so it must not cycle on release.
        self._lshift_tap_armed = False
        # Inert in input mode (see mouseMoveEvent): a click must not commit
        # geometry behind an open HUD.
        if self.is_input_mode():
            return
        if event.button() == Qt.MouseButton.RightButton:
            # Don't pass right-click to base — it deselects items.
            # contextMenuEvent handles right-click menus separately.
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        self._last_press_pos = event.scenePos()
        scene_pos = event.scenePos()
        snapped   = self.get_effective_position(scene_pos)

        items     = self.items(snapped)
        # Check for Sprinkler first (highest Z) and resolve to parent Node
        selection = next((i for i in items if isinstance(i, Sprinkler)), None)
        if selection is not None:
            selection = selection.node
        else:
            selection = next((i for i in items if isinstance(i, Node)), None)
        if selection is None:
            selection = next((i for i in items if isinstance(i, Pipe)), None)
        # Also check for walls, floors, roofs, view markers, design-area
        # badges (lower Z-order).
        if selection is None:
            for i in items:
                # A badge click resolves to its parent DesignArea (mirrors
                # the Sprinkler→Node resolve above); the ItemIsSelectable
                # check applies to the resolved parent.  Clicking the area's
                # interior must NOT steal room/wall selection — DesignArea
                # sits at Z=600 (above everything) with a filled tile-union
                # path, so a bare DesignArea hit is never a candidate (only
                # the badge is a click target); rubber-band selection still
                # selects the area itself.
                if isinstance(i, DesignAreaBadge):
                    parent = i.parentItem()
                    if (parent is not None and parent.flags()
                            & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                        selection = parent
                        break
                    continue
                if ((isinstance(i, (WallSegment, FloorSlab, RoofItem, Room,
                                    ViewMarkerArrow))
                        or type(i).__name__ == "DetailMarker")
                        and i.flags()
                        & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                    selection = i
                    break

        # Derive typed references for handler signature
        node_under = selection if isinstance(selection, Node) else None
        pipe_under = selection if isinstance(selection, Pipe) else None

        # ── Grip hit takes priority over mode handlers ──────────────────
        # Skip grip detection in drawing modes so clicks reach the draw handler
        _skip_grip_modes = ("wall", "floor", "pipe", "sprinkler",
                            "draw_line", "draw_rectangle",
                            "draw_circle", "draw_arc", "polyline", "draw_gridline",
                            "dimension", "text", "door", "window", "set_scale",
                            "detail", "align", "design_area")
        if (self.mode not in _skip_grip_modes
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            grip_hit = self._tools._find_grip_hit(snapped)
            if grip_hit is not None:
                if self.mode == "move" and self.node_start_pos is None:
                    # In move mode, use grip point as precise base point.  Build
                    # the ghost silhouette here too: this early return skips the
                    # ``_press_paste_move`` path that normally builds it, so
                    # without this the (common) base-click-on-the-moved-item case
                    # sets a base point but shows no ghost.
                    item, idx = grip_hit
                    self.node_start_pos = item.grip_points()[idx]
                    self._move_ghost_base = self._build_move_ghost_base(
                        is_paste=False)
                    self.instructionChanged.emit("Pick destination point")
                    return
                self._grip_item, self._grip_index = grip_hit
                self._grip_dragging = True
                # Enable ALIGN self-exclusion for gridline endpoint drags.
                if isinstance(self._grip_item, GridlineItem):
                    self._align_active_item = self._grip_item
                return  # consumed by grip system

        # ── Selection-manipulator interior press (select mode only) ─────
        # Grip hits above stay first (spec §event-routing: grip beats
        # interior-move).  Route the press through normal item dispatch so
        # the manipulator (z=1e6, shape = frame rect) receives it: drag =
        # group move, plain click = click-through picking.  Shift-presses
        # are excluded so Shift-click floor vertex editing keeps working
        # (mirrors the grip-check gate above).
        _manip = self._live_manip()
        if (_manip is not None and _manip.isVisible()
                and self.mode in (None, "select")
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                and _manip.hit_test(scene_pos)):
            super().mousePressEvent(event)
            return

        # ── Gridline body click → select (no body drag, use grips) ──
        if self.mode in (None, "select"):
            gl_hit = next(
                (i for i in items
                 if isinstance(i, GridlineItem)
                 or (hasattr(i, 'parentItem') and isinstance(i.parentItem(), GridlineItem))),
                None,
            )
            if gl_hit is not None:
                gl = gl_hit if isinstance(gl_hit, GridlineItem) else gl_hit.parentItem()
                ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
                if ctrl:
                    gl.setSelected(not gl.isSelected())
                else:
                    # Clear other selections and select this gridline
                    if not gl.isSelected():
                        self.clearSelection()
                        gl.setSelected(True)
                return

        # ── Dispatch to per-mode handler ────────────────────────────────
        handler_name = self._PRESS_DISPATCH.get(self.mode)
        if handler_name is not None:
            # Spec D3: when THIS press arms a first placement point, the
            # auto-acquired active anchor inherits the direction of the object
            # the point landed on, so an Extension ray extends end-to-end at the
            # existing angle (continue a wall/line collinearly).  Detect a
            # fresh arm by the raw per-mode anchor flipping None → not-None
            # across the handler (``_mode_placement_anchor`` is not masked by the
            # track-schema override, unlike ``get_placement_anchor``), then
            # capture the direction from the snap result the arming click landed
            # on (``None`` for empty space / a non-directional point — which also
            # correctly overwrites any stale inherited direction).
            anchor_before = self._mode_placement_anchor()
            getattr(self, handler_name)(event, scene_pos, snapped,
                                        selection, node_under, pipe_under)
            anchor_after = self._mode_placement_anchor()
            if anchor_before is None and anchor_after is not None:
                self._align_anchor_dir = self._source_item_direction(
                    getattr(self._snap_result, "source_item", None))
            # A press is what arms an anchor and what commits it, so the HUD's
            # existence is reconciled here as well as on move.  Without this a
            # committed placement would leave its readout hanging on screen
            # until the user happened to move the mouse.
            self._sync_dynamic_input()
            return

        # ── Shift-click floor vertex editing (select mode) ────────────────
        if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                and self.mode in (None, "select")):
            if self._press_select_shift_floor(event, scene_pos, snapped,
                                               selection, node_under, pipe_under):
                return

        # (Grip check was moved above the mode chain — always takes priority)

        super().mousePressEvent(event)

    # ── Per-mode press handlers ──────────────────────────────────────────

    def _press_select_item(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Explicit select-mode click: select the node or pipe under cursor."""
        # Shift-click floor vertex editing takes priority
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if self._press_select_shift_floor(event, pos, snapped,
                                               item_under, node_under, pipe_under):
                return
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if not ctrl:
            self.clearSelection()
        if item_under is not None:
            item_under.setSelected(not item_under.isSelected() if ctrl else True)

    def _press_sprinkler(self, event, pos, snapped, item_under, node_under, pipe_under):
        if isinstance(item_under, Pipe):
            node = self.split_pipe(item_under, self.project_click_onto_pipe_segment(snapped, item_under))
        elif isinstance(item_under, Node):
            node = item_under
            if node.has_sprinkler():
                return
        else:
            # Empty space or non-pipe/non-node item (Room, Wall, Floor, etc.)
            node = self.add_node(snapped.x(), snapped.y())
        self.add_sprinkler(node, getattr(self, "current_template", None))
        node.fitting.update()
        self.push_undo_state()

    def _press_pipe(self, event, pos, snapped, item_under, node_under, pipe_under):
        return self._pipe_ctl.press_pipe(
            event, pos, snapped, item_under, node_under, pipe_under)

    def cancel_pipe_placement(self) -> bool:
        return self._pipe_ctl.cancel_placement()

    def _press_set_scale(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._cal_point1 is None:
            self._cal_point1 = snapped
            self.instructionChanged.emit("Pick second calibration point")
        else:
            dialog = CalibrateDialog(self.views()[0] if self.views() else None)
            if dialog.exec():
                distance = dialog.get_distance()
                unit = dialog.get_unit_code()
                try:
                    self.scale_manager.calibrate(
                        self._cal_point1, snapped, distance, unit
                    )
                    self._show_status(f"Scale set: {self.scale_manager.pixels_per_mm:.4f} px/mm")
                    self._refresh_all_scales()
                except ValueError as e:
                    self._show_status(f"Calibration failed: {e}")
            self._cal_point1 = None
            self.set_mode(None)

    def _press_dimension(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._dim_pending is not None:
            # Click 3 — finalize offset
            self._dim_pending = None
            self.dimension_start = None
            self.push_undo_state()
            self.instructionChanged.emit("Pick first point")
            return
        elif self.dimension_start is None:
            # Click 1 — check if clicking on a circle or arc for radius dim
            hit_items = self.items(event.scenePos())
            _radius_target = None
            for hit in hit_items:
                if isinstance(hit, CircleItem):
                    _radius_target = (hit._center, snapped)
                    break
                elif isinstance(hit, ArcItem):
                    _radius_target = (hit._center, snapped)
                    break
            if _radius_target is not None:
                # Create radius dimension immediately (center → click point)
                center_pt, edge_pt = _radius_target
                self._remove_dim_preview()
                dim = DimensionAnnotation(center_pt, edge_pt)
                dim.is_radius = True
                self.addItem(dim)
                self.annotations.add_dimension(dim)
                self.requestPropertyUpdate.emit(dim)
                self._dim_pending = dim
                self.instructionChanged.emit("Click to set offset position")
                return
            # Normal Click 1 — set start point; detect if on a LineItem
            self.dimension_start = snapped
            self._dim_line1 = None
            for hit in hit_items:
                if isinstance(hit, LineItem):
                    self._dim_line1 = hit
                    break
            self.instructionChanged.emit("Pick second point")
        else:
            # Click 2 — check for parallel lines, then create dimension
            p1 = self.dimension_start
            p2 = snapped

            # Detect if click 2 is on a LineItem and lines are parallel
            hit2_items = self.items(event.scenePos())
            _line2 = None
            for hit in hit2_items:
                if isinstance(hit, LineItem) and hit is not self._dim_line1:
                    _line2 = hit
                    break

            if self._dim_line1 is not None and _line2 is not None:
                # Both clicks on lines — check parallelism
                l1 = self._dim_line1.line()
                l2 = _line2.line()
                a1 = math.atan2(l1.dy(), l1.dx())
                a2 = math.atan2(l2.dy(), l2.dx())
                angle_diff = abs(a1 - a2) % math.pi
                if angle_diff < math.radians(5) or angle_diff > math.radians(175):
                    # Parallel — compute perpendicular foot points
                    # Project p2 onto the perpendicular from p1
                    perp_angle = a1 + math.pi / 2
                    nx, ny = math.cos(perp_angle), math.sin(perp_angle)
                    # p2_foot = p1 + t * n where t = (p2 - p1) · n
                    dx = p2.x() - p1.x()
                    dy = p2.y() - p1.y()
                    t = dx * nx + dy * ny
                    p2 = QPointF(p1.x() + t * nx, p1.y() + t * ny)

            self._dim_line1 = None  # reset
            self._remove_dim_preview()
            dim = DimensionAnnotation(p1, p2)
            self.addItem(dim)
            self.annotations.add_dimension(dim)
            self.requestPropertyUpdate.emit(dim)
            self._dim_pending = dim
            self.instructionChanged.emit("Click to set offset position")

    def _press_text(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._text_anchor is None:
            # First click — set anchor, create dashed preview rectangle
            self._text_anchor = snapped
            self.update_preview_node(snapped)
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            _prev_pen = QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine)
            _prev_pen.setCosmetic(True)
            preview.setPen(_prev_pen)
            preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            preview.setZValue(200)
            self.addItem(preview)
            self._text_preview = preview
        else:
            # Second click — commit text box
            rect = QRectF(self._text_anchor, snapped).normalized()
            text_width = max(rect.width(), 20)  # minimum 20px width
            note = NoteAnnotation(
                text="Text", x=rect.x(), y=rect.y(),
                text_width=text_width)
            note.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextEditorInteraction)
            self.addItem(note)
            self.annotations.notes.append(note)
            self.requestPropertyUpdate.emit(note)
            # Remove preview
            if self._text_preview is not None:
                self.removeItem(self._text_preview)
                self._text_preview = None
            self._text_anchor = None
            self.push_undo_state()

    def _press_draw_arc(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._draw_arc_step == 0:
            # Click 1 — set centre
            self._draw_arc_center = snapped
            self._draw_arc_step = 1
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick start angle point")
            # Create radius preview line (centre → cursor)
            line = QGraphicsLineItem(snapped.x(), snapped.y(),
                                     snapped.x(), snapped.y())
            _prev_pen = QPen(QColor(self._geom_color_lw()[0]), 2, Qt.PenStyle.DashLine)
            _prev_pen.setCosmetic(True)
            line.setPen(_prev_pen)
            line.setZValue(200)
            self.addItem(line)
            self._draw_arc_radius_line = line
        elif self._draw_arc_step == 1:
            # Click 2 — set start point (defines radius + start angle).  Shared
            # with the Dynamic Input rim applier via ``_commit_draw_arc_rim_at``.
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                snapped = self._constrain_angle(self._draw_arc_center, snapped)
            self._commit_draw_arc_rim_at(snapped)
        elif self._draw_arc_step == 2:
            # Click 3 — set end point → commit arc
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                snapped = self._constrain_angle(self._draw_arc_center, snapped)
            self._commit_draw_arc_at(snapped)

    def _advance_arc_to_span_step(self) -> None:
        """Advance an armed arc from step 1 to step 2 (radius → span).

        Removes the radius preview line, creates the arc preview path item, sets
        ``_draw_arc_step = 2`` and emits the "pick end" instruction.  Shared
        verbatim by the mouse step-1 click and the Dynamic Input rim applier so
        both hand off to the span step identically.
        """
        self._draw_arc_step = 2
        self.instructionChanged.emit("Pick end angle point")
        # Remove radius line, create arc preview path
        if self._draw_arc_radius_line is not None:
            self.removeItem(self._draw_arc_radius_line)
            self._draw_arc_radius_line = None
        preview = QGraphicsPathItem()
        _prev_pen = QPen(QColor(self._geom_color_lw()[0]), 2, Qt.PenStyle.DashLine)
        _prev_pen.setCosmetic(True)
        preview.setPen(_prev_pen)
        preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        preview.setZValue(200)
        self.addItem(preview)
        self._draw_arc_preview = preview
        # Span-step angle guides: 0° datum + start radial (static) + a live sweep
        # radial that tracks the cursor.
        self._clear_arc_ref_lines()
        self._draw_arc_ref_line0 = self._make_ref_line()
        self._draw_arc_ref_start = self._make_ref_line()
        self._draw_arc_ref_sweep = self._make_ref_line()
        self._set_arc_ref_lines()

    def _commit_draw_arc_rim_at(self, point) -> bool:
        """Step-1 applier: fix radius + start angle, then advance to the span step.

        Variant-aware.  In center-first, ``point`` is the rim: radius and start°
        are measured from the stored centre.  In start-first, ``point`` is the
        CENTRE and the first click (``_draw_arc_center``) is the START, so the
        radius/start° are measured from ``point`` to that start, then ``point``
        is stored as the real centre for the span math.

        Shared by the mouse step-1 click (center-first, parity-preserving) and
        the Dynamic Input ``line`` schema, which resolves Length=radius +
        Angle=start° into this rim point.

        Args:
            point: The rim (center-first) or the centre (start-first).

        Returns:
            True when the arc advanced to step 2, False when the radius is under
            the too-small floor (a degenerate rim).
        """
        if self._arc_variant == _ARC_VARIANT_START:
            # ``point`` is the centre; the first click is the start point.
            cx, cy = point.x(), point.y()
            start = self._draw_arc_center
            r = math.hypot(start.x() - cx, start.y() - cy)
            if r < 0.01:
                return False
            self._draw_arc_radius = r
            self._draw_arc_start_deg = math.degrees(
                math.atan2(-(start.y() - cy), start.x() - cx)
            )
            # Store the real centre for the span derivation.
            self._draw_arc_center = QPointF(point)
        else:
            # center-first: ``point`` is the rim, measured from the stored centre.
            cx, cy = self._draw_arc_center.x(), self._draw_arc_center.y()
            r = math.hypot(point.x() - cx, point.y() - cy)
            if r < 0.01:
                return False
            self._draw_arc_radius = r
            self._draw_arc_start_deg = math.degrees(
                math.atan2(-(point.y() - cy), point.x() - cx)
            )
        self._advance_arc_to_span_step()
        return True

    def _arc_end_point_for_span(self, span_deg) -> "QPointF":
        """Return the sweep endpoint on the radius circle for ``span_deg``.

        The stored centre/radius/start° plus the typed span give a bearing
        ``start° + span`` (Y-up), projected onto the radius circle.  Feeds
        ``_commit_draw_arc_at``, which re-derives the span from this point, so
        the Dynamic Input span and the mouse third click share one commit.
        """
        cx, cy = self._draw_arc_center.x(), self._draw_arc_center.y()
        r = self._draw_arc_radius
        end_deg = self._draw_arc_start_deg + span_deg
        return QPointF(cx + r * math.cos(math.radians(end_deg)),
                       cy - r * math.sin(math.radians(end_deg)))

    def _apply_arc_dynamic_input(self, geometry) -> bool:
        """Route a resolved arc value to the right step's applier.

        Arc's schema is step-dependent, so its applier is too: at step 1 the
        ``line`` schema resolves to a rim QPointF, at step 2 the ``arc_span``
        schema resolves to a ``{"span_deg": …}`` dict.

        Returns:
            The step applier's verdict, or False outside steps 1/2.
        """
        if self._draw_arc_step == 1:
            return self._commit_draw_arc_rim_at(geometry)          # QPointF
        if self._draw_arc_step == 2:
            return self._commit_draw_arc_at(
                self._arc_end_point_for_span(geometry["span_deg"]))  # dict
        return False

    def _commit_draw_arc_at(self, end_point) -> bool:
        """Commit the in-progress arc, sweeping to ``end_point``.

        Shared commit path for both the third mouse click and (later) the
        Dynamic Input span value.  Reads the stored centre/radius/start angle,
        derives the span by projecting ``end_point`` onto the radius circle, and
        rejects a degenerate sweep (near 0 or near 360).

        Args:
            end_point: The sweep endpoint; only its bearing from the centre is
                used (the span is projected onto the stored radius circle).

        Returns:
            True when an ``ArcItem`` was committed, False when the arc is
            unarmed (no centre) or the span is under the too-small floor.
        """
        if self._draw_arc_center is None:
            return False
        cx, cy = self._draw_arc_center.x(), self._draw_arc_center.y()
        end_deg = math.degrees(
            math.atan2(-(end_point.y() - cy), end_point.x() - cx)
        )
        span = end_deg - self._draw_arc_start_deg
        # Normalise span to positive CCW direction
        if span <= 0:
            span += 360.0
        # Reject near-zero arcs
        if abs(span) < 0.5 or abs(span - 360.0) < 0.5:
            self._show_status("Arc span too small — skipped", timeout=2000)
            return False
        tmpl = self._get_geometry_template()
        _c, _lw = self._geom_color_lw()
        item = ArcItem(self._draw_arc_center, self._draw_arc_radius,
                       self._draw_arc_start_deg, span, _c, _lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        self.addItem(item)
        self._draw_arcs.append(item)
        item.setSelected(True)
        for v in self.views(): v.viewport().update()
        # Clean up previews
        if self._draw_arc_preview is not None:
            self.removeItem(self._draw_arc_preview)
            self._draw_arc_preview = None
        self._clear_arc_ref_lines()
        self._draw_arc_center = None
        self._draw_arc_radius = 0.0
        self._draw_arc_start_deg = 0.0
        self._draw_arc_step = 0
        self.push_undo_state()
        self.instructionChanged.emit("Pick center point")
        return True

    def _press_water_supply(self, event, pos, snapped, item_under, node_under, pipe_under):
        # Require direct click on a node or pipe (no proximity fallback)
        if isinstance(item_under, Node):
            target_node = item_under
        elif isinstance(item_under, Pipe):
            target_node = self.split_pipe(
                item_under,
                self.project_click_onto_pipe_segment(snapped, item_under),
            )
        else:
            self._show_status("Click on a node or pipe to place water supply")
            return

        if target_node is None:
            self._show_status("Click on a node or pipe to place water supply")
            return

        if self.water_supply_node is not None:
            self.removeItem(self.water_supply_node)
        ws = WaterSupply(target_node.scenePos().x(), target_node.scenePos().y())
        self.addItem(ws)
        self.water_supply_node = ws
        self.sprinkler_system.supply_node = ws
        self.requestPropertyUpdate.emit(ws)
        self.push_undo_state()
        self.set_mode(None)

    def _refresh_da_highlights(self):
        """Rebuild the per-sprinkler highlight rings for design_area mode.

        One fixed-screen-size ring per selected sprinkler of the active
        design area.  Self-clearing: outside design_area mode (or with no
        active area) it just removes existing rings.
        """
        for it in self._da_highlights:
            if it.scene() is self:
                self.removeItem(it)
        self._da_highlights.clear()

        if self.mode != "design_area" or not self._da_editing:
            return

        r = DESIGN_AREA_HL_RADIUS_PX
        for spr in self._da_editing.sprinklers:
            if not spr.node:
                continue
            ring = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
            ring.setPos(spr.node.scenePos())
            pen = QPen(QColor(255, 140, 0), 2)
            pen.setCosmetic(True)
            ring.setPen(pen)
            ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            ring.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            ring.setZValue(Z_OVERLAY)
            ring.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.addItem(ring)
            self._da_highlights.append(ring)

    def _ensure_editing_da(self, resume_spr=None):
        """Return the design area picks modify, creating or resuming one.

        With no working area: if *resume_spr* already belongs to a design
        area, editing resumes on that one; otherwise a new area starts.
        Confirming (right-click) clears the working area so the next pick
        starts a fresh one — this is how multiple design areas are made.
        """
        if self._da_editing is not None:
            return self._da_editing
        da = None
        if resume_spr is not None:
            da = next((d for d in self.design_areas
                       if resume_spr in d.sprinklers), None)
        if da is None:
            da = DesignArea()
            da.level = getattr(self, "active_level", DEFAULT_LEVEL)
            self.addItem(da)
            apply_category_defaults(da)
            da.sync_z_for_mode(editing=True)
            self.design_areas.append(da)
        self._da_editing = da
        self.active_design_area = da
        return da

    def _da_change_committed(self, da, confirmed=False):
        """Shared tail for every design-area mutation: recompute, refresh
        rings, live property panel, browser/dirty signal, status tally."""
        da.compute_area(self.scale_manager)
        self._refresh_da_highlights()
        self.requestPropertyUpdate.emit(da)
        self.sceneModified.emit()
        count = len(da.sprinklers)
        area = da._properties.get("Area", {}).get("value", "0")
        if confirmed:
            self._show_status(
                f"Design area confirmed: {count} sprinkler(s), {area}. "
                f"Click a sprinkler to start a new design area.")
        else:
            self._show_status(
                f"Design area: {count} sprinkler(s), {area}. "
                f"Click more or right-click to confirm.")

    def _press_design_area(self, event, pos, snapped, item_under, node_under, pipe_under):
        modifiers = event.modifiers() if hasattr(event, 'modifiers') else Qt.KeyboardModifier.NoModifier
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if shift:
            # Shift+click: rectangle selection mode
            if self._design_area_corner1 is None:
                self._design_area_corner1 = snapped
                rect_item = QGraphicsRectItem(QRectF(snapped, snapped))
                rect_item.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine))
                rect_item.setBrush(QBrush(QColor(255, 200, 0, 40)))
                rect_item.setZValue(2)
                self.addItem(rect_item)
                self._design_area_rect_item = rect_item
                self._show_status("Shift+click second corner to complete rectangle.")
            else:
                c1 = self._design_area_corner1
                selection_rect = QRectF(c1, snapped).normalized()
                active = getattr(self, "active_level", DEFAULT_LEVEL)
                selected_sprs = [
                    s for s in self.sprinkler_system.sprinklers
                    if s.node and selection_rect.contains(s.node.scenePos())
                    and getattr(s.node, "level", DEFAULT_LEVEL) == active
                ]
                # Remove the temporary preview rect
                if self._design_area_rect_item and self._design_area_rect_item.scene() is self:
                    self.removeItem(self._design_area_rect_item)
                self._design_area_rect_item = None
                self._design_area_corner1 = None
                # Add to the working design area (create/resume as needed)
                da = self._ensure_editing_da()
                for s in selected_sprs:
                    da.add_sprinkler(s)
                self._da_change_committed(da)
        else:
            # Normal click: toggle the nearest sprinkler on the active level.
            # Routes through SnapEngine (center-only whitelist, sprinkler nodes
            # only) so the pick aperture stays zoom-invariant and consistent
            # with the rest of the snap system.  OSNAP toggle is overridden so
            # design-area picking always works regardless of the F3 setting.
            active = getattr(self, "active_level", DEFAULT_LEVEL)
            _view = self._snap_view()
            xform = _view.transform() if _view is not None else QTransform()
            node_to_spr = {spr.node: spr for spr in self.sprinkler_system.sprinklers
                           if spr.node is not None
                           and getattr(spr.node, "level", DEFAULT_LEVEL) == active}
            target_spr = None
            _was_enabled = self._snap_engine.enabled
            _was_center = self._snap_engine.snap_center
            self._snap_engine.enabled = True
            self._snap_engine.snap_center = True
            try:
                result = self._snap_engine.find(
                    pos, self, xform,
                    only_types={"center"},
                    item_filter=lambda it: it in node_to_spr)
            finally:
                self._snap_engine.enabled = _was_enabled
                self._snap_engine.snap_center = _was_center
            if result is not None:
                target_spr = node_to_spr.get(result.source_item)
            if target_spr:
                da = self._ensure_editing_da(resume_spr=target_spr)
                da.toggle_sprinkler(target_spr)
                self._da_change_committed(da)
            else:
                self._show_status("No sprinkler found. Click on a sprinkler to add/remove it.")

    # ── Room boundary detection ────────────────────────────────────────

    def _wall_spans_level(self, wall, level_name: str) -> bool:
        """Return True if wall's Z-range includes the given level elevation."""
        zr = wall.z_range_mm()
        if zr is None:
            return False
        lm = self._level_manager
        if lm is None:
            return False
        lvl = lm.get(level_name)
        if lvl is None:
            return False
        return zr[0] <= lvl.elevation <= zr[1]

    def _detect_room_boundary(self, click_pt: QPointF) -> list[QPointF] | None:
        """Detect a closed wall boundary enclosing *click_pt*.

        Builds a graph from wall endpoints on the active level (including
        T-junction face points), then walks the boundary choosing the
        tightest clockwise turn.  Returns interior face polygon vertices.
        """
        import math as _m
        from collections import defaultdict

        TOL = 2.0
        level = self.active_level
        # Include walls visible on this plan — not just walls whose base
        # level matches, but also multi-level walls that span through it.
        walls = [w for w in self._walls
                 if w.isVisible() and (
                     w.level == level
                     or getattr(w, "_base_level", "") == level
                     or self._wall_spans_level(w, level))]
        if not walls:
            return None

        # ── Collect graph nodes: endpoints + T-junction face points ────
        raw_pts: list[QPointF] = []
        pt_sources: list = []  # track which wall/endpoint for each raw_pt

        for w in walls:
            raw_pts.append(w.pt1)
            pt_sources.append((w, 0))
            raw_pts.append(w.pt2)
            pt_sources.append((w, 1))

        # Add T-junction points: where a wall endpoint meets the face of
        # another wall (not at its endpoints)
        for w in walls:
            for ep in (w.pt1, w.pt2):
                for other in walls:
                    if other is w:
                        continue
                    # Check if ep is near other's centerline but NOT near endpoints
                    if (other.endpoint_near(ep, TOL) is not None):
                        continue  # already at an endpoint — handled above
                    fp = other.nearest_face_point(ep, TOL * 3,
                                                   self.scale_manager, ep)
                    if fp is not None:
                        raw_pts.append(ep)
                        pt_sources.append((other, "tee"))

        # Merge close points into unique node indices
        node_coords: list[QPointF] = []
        pt_to_node: dict[int, int] = {}

        for i, pt in enumerate(raw_pts):
            found = -1
            for ni, nc in enumerate(node_coords):
                if _m.hypot(pt.x() - nc.x(), pt.y() - nc.y()) <= TOL:
                    found = ni
                    break
            if found >= 0:
                pt_to_node[i] = found
            else:
                pt_to_node[i] = len(node_coords)
                node_coords.append(QPointF(pt))

        # ── Build directed edges ──────────────────────────────────────
        # Each entry: (neighbor_node, angle, wall_ref)
        adj: dict[int, list[tuple[int, float, "WallSegment"]]] = defaultdict(list)

        for wi, w in enumerate(walls):
            n1 = pt_to_node[wi * 2]
            n2 = pt_to_node[wi * 2 + 1]
            if n1 == n2:
                continue

            # Check for T-junction nodes along this wall's centerline
            # and split the wall edge into segments
            wall_nodes = [n1]
            for i in range(len(walls) * 2, len(raw_pts)):
                ni = pt_to_node[i]
                if ni == n1 or ni == n2:
                    continue
                src_wall, src_type = pt_sources[i]
                if src_wall is w or src_type != "tee":
                    continue
                # Check if this tee point is on wall w's centerline
                nc = node_coords[ni]
                ax, ay = w.pt1.x(), w.pt1.y()
                bx, by = w.pt2.x(), w.pt2.y()
                dx, dy = bx - ax, by - ay
                lsq = dx * dx + dy * dy
                if lsq < 1e-12:
                    continue
                t = ((nc.x() - ax) * dx + (nc.y() - ay) * dy) / lsq
                if 0.05 < t < 0.95:
                    wall_nodes.append(ni)
            wall_nodes.append(n2)

            # Sort by parameter t along the wall
            p1 = node_coords[n1]
            dx_w = node_coords[n2].x() - p1.x()
            dy_w = node_coords[n2].y() - p1.y()
            lsq_w = dx_w * dx_w + dy_w * dy_w
            if lsq_w > 1e-12:
                wall_nodes.sort(key=lambda ni: (
                    (node_coords[ni].x() - p1.x()) * dx_w +
                    (node_coords[ni].y() - p1.y()) * dy_w
                ) / lsq_w)

            # Add edges between consecutive nodes along this wall
            for j in range(len(wall_nodes) - 1):
                na, nb = wall_nodes[j], wall_nodes[j + 1]
                if na == nb:
                    continue
                pa, pb = node_coords[na], node_coords[nb]
                a_ab = _m.atan2(pb.y() - pa.y(), pb.x() - pa.x())
                a_ba = _m.atan2(pa.y() - pb.y(), pa.x() - pb.x())
                adj[na].append((nb, a_ab, w))
                adj[nb].append((na, a_ba, w))

        # ── Find nearest wall edge to click point ─────────────────────
        best_wall = None
        best_dist = float("inf")
        for w in walls:
            ax, ay = w.pt1.x(), w.pt1.y()
            bx, by = w.pt2.x(), w.pt2.y()
            dx, dy = bx - ax, by - ay
            lsq = dx * dx + dy * dy
            if lsq < 1e-12:
                continue
            t = max(0, min(1, ((click_pt.x() - ax) * dx + (click_pt.y() - ay) * dy) / lsq))
            d = _m.hypot(click_pt.x() - (ax + t * dx), click_pt.y() - (ay + t * dy))
            if d < best_dist:
                best_dist = d
                best_wall = w

        if best_wall is None:
            return None

        start_n1 = pt_to_node[walls.index(best_wall) * 2]
        start_n2 = pt_to_node[walls.index(best_wall) * 2 + 1]

        # Which side of the wall is the click on?
        wx = best_wall.pt2.x() - best_wall.pt1.x()
        wy = best_wall.pt2.y() - best_wall.pt1.y()
        cross = wx * (click_pt.y() - best_wall.pt1.y()) - wy * (click_pt.x() - best_wall.pt1.x())

        if cross >= 0:
            curr = start_n1
            prev_angle = _m.atan2(
                node_coords[start_n1].y() - node_coords[start_n2].y(),
                node_coords[start_n1].x() - node_coords[start_n2].x())
        else:
            curr = start_n2
            prev_angle = _m.atan2(
                node_coords[start_n2].y() - node_coords[start_n1].y(),
                node_coords[start_n2].x() - node_coords[start_n1].x())
        start = curr

        # ── Walk boundary (tightest CW turn) ──────────────────────────
        boundary = [node_coords[curr]]
        visited_edges: set[tuple[int, int]] = set()
        boundary_walls: list = []  # walls actually forming this room boundary

        for _ in range(len(node_coords) * 2 + 10):
            neighbors = adj.get(curr, [])
            if not neighbors:
                return None

            incoming = prev_angle + _m.pi
            best_next = None
            best_turn = float("inf")
            for nb, edge_angle, wall_ref in neighbors:
                if (curr, nb) in visited_edges:
                    continue
                turn = (incoming - edge_angle) % (2 * _m.pi)
                if turn < 1e-10:
                    turn = 2 * _m.pi
                if turn < best_turn:
                    best_turn = turn
                    best_next = (nb, edge_angle, wall_ref)

            if best_next is None:
                return None

            nb, edge_angle, wall_ref = best_next
            visited_edges.add((curr, nb))
            prev_angle = edge_angle
            curr = nb
            if wall_ref not in boundary_walls:
                boundary_walls.append(wall_ref)

            if curr == start and len(boundary) >= 3:
                break
            boundary.append(node_coords[curr])
        else:
            return None

        if len(boundary) < 3:
            return None

        # Use only the walls that form this room's boundary
        walls = boundary_walls

        # The boundary walk traces wall centerlines/axes. For non-center
        # alignments we may need to inset to reach the interior face:
        #   Center → axis at wall center → inset by half thickness
        #   Right  → axis IS the right face → no inset needed
        #   Left   → axis at left face → inset by full wall thickness
        align_counts = {"Center": 0, "Left": 0, "Right": 0}
        total_ht = 0.0
        for w in walls:
            align_counts[w._alignment] = align_counts.get(w._alignment, 0) + 1
            total_ht += w.half_thickness_scene()
        avg_ht = total_ht / len(walls) if walls else 0.0

        dominant = max(align_counts, key=align_counts.get)
        # Determine inset needed to reach interior face from the boundary walk
        # (which traces wall centerlines/axes):
        #   Center → axis at wall center → inset by half thickness (shrink)
        #   Right  → axis IS the right face → no inset needed
        #   Left   → axis at left face → inset by full thickness (shrink)
        if dominant == "Right":
            inset_dist = 0.0
        elif dominant == "Left":
            inset_dist = avg_ht * 2  # full wall thickness
        else:  # Center
            inset_dist = avg_ht  # half wall thickness
        want_larger = False  # always shrink toward room interior

        if inset_dist > 0.01:
            orig_area = abs(sum(
                boundary[i].x() * boundary[(i+1) % len(boundary)].y() -
                boundary[(i+1) % len(boundary)].x() * boundary[i].y()
                for i in range(len(boundary))) / 2.0)
            for sign in (1.0, -1.0):
                candidate = self._inset_polygon(boundary, inset_dist * sign)
                if candidate and len(candidate) >= 3:
                    cand_area = abs(sum(
                        candidate[i].x() * candidate[(i+1) % len(candidate)].y() -
                        candidate[(i+1) % len(candidate)].x() * candidate[i].y()
                        for i in range(len(candidate))) / 2.0)
                    area_ok = (cand_area > orig_area) if want_larger else (cand_area < orig_area)
                    if area_ok:
                        test_path = QPainterPath()
                        test_path.addPolygon(QPolygonF(candidate))
                        test_path.closeSubpath()
                        if test_path.contains(click_pt):
                            boundary = candidate
                            break

        # Validate
        path = QPainterPath()
        path.addPolygon(QPolygonF(boundary))
        path.closeSubpath()
        if not path.contains(click_pt):
            boundary.reverse()
            path = QPainterPath()
            path.addPolygon(QPolygonF(boundary))
            path.closeSubpath()
            if not path.contains(click_pt):
                return None

        return boundary

    @staticmethod
    def _inset_polygon(pts: list[QPointF], dist: float) -> list[QPointF] | None:
        """Offset a polygon inward by *dist* using edge normals."""
        import math as _m
        n = len(pts)
        if n < 3:
            return None

        # Compute inward normals for each edge
        normals = []
        for i in range(n):
            j = (i + 1) % n
            dx = pts[j].x() - pts[i].x()
            dy = pts[j].y() - pts[i].y()
            length = _m.hypot(dx, dy)
            if length < 1e-12:
                normals.append((0.0, 0.0))
                continue
            # Inward normal (assuming CW winding for scene Y-down)
            nx = dy / length
            ny = -dx / length
            normals.append((nx, ny))

        # Check winding: if polygon area is positive (CCW), flip normals
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += pts[i].x() * pts[j].y() - pts[j].x() * pts[i].y()
        if area > 0:  # CCW winding
            normals = [(-nx, -ny) for nx, ny in normals]

        # Offset each edge inward and intersect consecutive offset edges
        result = []
        for i in range(n):
            prev = (i - 1) % n
            # Previous edge offset line
            p1 = QPointF(pts[prev].x() + normals[prev][0] * dist,
                         pts[prev].y() + normals[prev][1] * dist)
            p2 = QPointF(pts[i].x() + normals[prev][0] * dist,
                         pts[i].y() + normals[prev][1] * dist)
            # Current edge offset line
            p3 = QPointF(pts[i].x() + normals[i][0] * dist,
                         pts[i].y() + normals[i][1] * dist)
            p4 = QPointF(pts[(i + 1) % n].x() + normals[i][0] * dist,
                         pts[(i + 1) % n].y() + normals[i][1] * dist)
            # Intersect
            dx1 = p2.x() - p1.x()
            dy1 = p2.y() - p1.y()
            dx2 = p4.x() - p3.x()
            dy2 = p4.y() - p3.y()
            denom = dx1 * dy2 - dy1 * dx2
            if abs(denom) < 1e-10:
                result.append(QPointF(pts[i].x() + normals[i][0] * dist,
                                      pts[i].y() + normals[i][1] * dist))
            else:
                t = ((p3.x() - p1.x()) * dy2 - (p3.y() - p1.y()) * dx2) / denom
                result.append(QPointF(p1.x() + t * dx1, p1.y() + t * dy1))

        return result

    def _press_room(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Room mode: click inside a closed wall region to create a room."""
        boundary = self._detect_room_boundary(snapped)
        if boundary is None:
            self._show_status("No closed wall boundary found at click point", 3000)
            return

        # Check if a room already exists at this location
        click_path = QPainterPath()
        click_path.addPolygon(QPolygonF(boundary))
        for existing in self._rooms:
            if existing.level == self.active_level:
                ep = QPainterPath()
                ep.addPolygon(QPolygonF(existing.boundary))
                if ep.contains(snapped) and click_path.contains(
                    QPointF(
                        sum(p.x() for p in existing.boundary) / len(existing.boundary),
                        sum(p.y() for p in existing.boundary) / len(existing.boundary),
                    )
                ):
                    self._show_status("Room already exists here", 2000)
                    return

        room = Room(boundary=boundary)
        room.level = self.active_level
        # Auto-assign ceiling level (next level up)
        if self._level_manager:
            levels = self._level_manager.levels
            active_idx = next(
                (i for i, lv in enumerate(levels) if lv.name == self.active_level), -1
            )
            if active_idx >= 0 and active_idx + 1 < len(levels):
                room._ceiling_level = levels[active_idx + 1].name
        room.name = f"Room {len(self._rooms) + 1}"
        room._tag = room.name
        room._update_label()  # rebuild label now that name/tag are set

        self.addItem(room)
        self._rooms.append(room)
        apply_category_defaults(room)
        self.clearSelection()
        room.setSelected(True)
        self.requestPropertyUpdate.emit(room)
        self.push_undo_state()
        self._show_status(f"Created {room.name}", 2000)

    # ── Room manual (polygon click-to-place) ──────────────────────────

    def _move_room_manual(self, event, snapped):
        if self._room_manual_active is None:
            self.update_preview_node(snapped)
            self.preview_pipe.hide()
        else:
            self.preview_node.hide()
            last_pt = self._room_manual_active._boundary[-1]
            self.preview_pipe.setLine(
                last_pt.x(), last_pt.y(), snapped.x(), snapped.y())
            pen = QPen(QColor(self._room_manual_active._color), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self.preview_pipe.setPen(pen)
            self.preview_pipe.show()

    def _press_room_manual(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Manual room mode: click to place boundary points, close near first."""
        if self._room_manual_active is None:
            room = Room(boundary=[snapped])
            room.level = self.active_level
            if self._level_manager:
                levels = self._level_manager.levels
                active_idx = next(
                    (i for i, lv in enumerate(levels) if lv.name == self.active_level), -1)
                if active_idx >= 0 and active_idx + 1 < len(levels):
                    room._ceiling_level = levels[active_idx + 1].name
            room.name = f"Room {len(self._rooms) + 1}"
            room._tag = room.name
            self.addItem(room)
            self._rooms.append(room)
            self._room_manual_active = room
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick next point (click near first or Enter to close)")
        else:
            pts = self._room_manual_active._boundary
            # Close polygon: click near first point with ≥3 points
            if len(pts) >= 3:
                scale = self._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                d0 = math.hypot(snapped.x() - pts[0].x(), snapped.y() - pts[0].y())
                if d0 <= tol:
                    self._room_manual_active._rebuild()
                    self._room_manual_active._update_label()
                    apply_category_defaults(self._room_manual_active)
                    self.clearSelection()
                    self._room_manual_active.setSelected(True)
                    self.requestPropertyUpdate.emit(self._room_manual_active)
                    self._show_status(f"Created {self._room_manual_active.name}", 2000)
                    self._room_manual_active = None
                    self.preview_pipe.hide()
                    for v in self.views(): v.viewport().update()
                    self.push_undo_state()
                    self.instructionChanged.emit("Pick first room boundary point")
                    return
            # Click-to-delete vertex
            if len(pts) >= 2:
                scale = self._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                for vi in range(len(pts)):
                    dv = math.hypot(snapped.x() - pts[vi].x(), snapped.y() - pts[vi].y())
                    if dv <= tol:
                        pts.pop(vi)
                        self._room_manual_active._rebuild()
                        for v in self.views(): v.viewport().update()
                        return
            # Add new point
            pts.append(snapped)
            self._room_manual_active._rebuild()

    def _press_paste_move(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self.node_start_pos is None:
            self.node_start_pos = snapped
            self._move_ghost_base = self._build_move_ghost_base(is_paste=(self.mode == "paste"))
        else:
            offset = CAD_Math.get_vector(self.node_start_pos, snapped)
            if self.mode == "paste":
                self.paste_items(offset)
            elif self.mode == "move":
                self.move_items(offset)
            self.push_undo_state()
            self.node_start_pos = None
            self._move_ghost = []
            self._move_ghost_base = []
            self.set_mode(None)

    def _apply_move_displacement(self, params: dict) -> bool:
        """Apply a typed dX/dY displacement (transform schema — dict, not point).

        The commit half of the ``move`` branch of :meth:`_press_paste_move`,
        so a typed displacement and a dragged one share ``move_items`` and one
        undo push.  Only ``move`` routes here — ``paste`` is deliberately kept
        out of the schema and anchor tables (F2), because it commits through
        ``paste_items`` and would otherwise be applied as a move of the current
        selection.

        Every displacement commits: unlike the length/radius/spacing schemas
        there is no magnitude floor, so this always reports success (decision
        D2's verdict is still returned for the dispatcher's sake).

        Args:
            params: ``resolve_displacement``'s output — ``{"offset": QPointF}``,
                already Y-flipped into scene coordinates.

        Returns:
            True — the move is unconditional.
        """
        self.move_items(params["offset"])
        self.push_undo_state()
        self.node_start_pos = None
        self._move_ghost = []
        self._move_ghost_base = []
        self.clear_placement_state()
        self.set_mode(None)
        return True

    def _press_place_import(self, event, pos, snapped, item_under, node_under, pipe_under):
        self._underlay_ctl._commit_place_import(snapped)

    def _press_offset(self, event, pos, snapped, item_under, node_under, pipe_under):
        # Select entity to offset — go straight to live preview (no dialog)
        hit = [i for i in self.items(pos)
               if isinstance(i, (LineItem, PolylineItem, CircleItem, RectangleItem, ArcItem))]
        if not hit:
            return
        self._offset_source = hit[0]
        self._offset_highlight = self._tools._highlight_item(hit[0])
        self._offset_dist = 0  # will be computed from cursor distance
        self._offset_manual = False  # cursor-driven distance
        self.set_mode("offset_side")
        self._show_status(
            "Move cursor to set offset distance and side, "
            "click to commit. Tab = type distance.")

    def _press_offset_side(self, event, pos, snapped, item_under, node_under, pipe_under):
        # Click determines which side — commit the offset
        if self._offset_source is not None and self._offset_dist > 0:
            sd = self._tools._offset_signed_dist(self._offset_source, self._offset_dist, snapped)
            self._tools._clear_offset_preview()
            new_item = self._tools._make_offset_item(self._offset_source, sd)
            if new_item is not None:
                if isinstance(new_item, LineItem):
                    self.addItem(new_item)
                    self._draw_lines.append(new_item)
                elif isinstance(new_item, PolylineItem):
                    self.addItem(new_item)
                    self._polylines.append(new_item)
                elif isinstance(new_item, CircleItem):
                    self.addItem(new_item)
                    self._draw_circles.append(new_item)
                elif isinstance(new_item, RectangleItem):
                    self.addItem(new_item)
                    self._draw_rects.append(new_item)
                elif isinstance(new_item, ArcItem):
                    self.addItem(new_item)
                    self._draw_arcs.append(new_item)
                self.push_undo_state()
        # Stay in offset mode ready for next entity
        self._offset_source = None
        if self._offset_highlight is not None:
            if self._offset_highlight.scene() is self:
                self.removeItem(self._offset_highlight)
            self._offset_highlight = None
        self.set_mode("offset")

    # ── Interactive Rotate ────────────────────────────────────────────
    def _press_rotate(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._rotate_pivot is None:
            self._rotate_pivot = snapped
            self.instructionChanged.emit("Click to set angle, or Tab for exact angle")
        else:
            dx = snapped.x() - self._rotate_pivot.x()
            dy = snapped.y() - self._rotate_pivot.y()
            angle = math.degrees(math.atan2(-dy, dx))
            self._tools._apply_rotate(self._rotate_pivot, angle)
            self.push_undo_state()
            self._selected_items = []
            self.set_mode(None)

    # ── Interactive Scale ─────────────────────────────────────────────
    def _press_scale(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._scale_base is None:
            self._scale_base = snapped
            self.instructionChanged.emit("Tab = enter scale factor")

    # ── Mirror ────────────────────────────────────────────────────────
    def _press_mirror(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._mirror_p1 is None:
            self._mirror_p1 = snapped
            self.instructionChanged.emit("Pick second axis point")
        else:
            self._tools._apply_mirror(self._mirror_p1, snapped)
            self.confirmRequested.emit(
                "mirror_delete", "Mirror", "Delete original objects?")
            # If user accepts, complete_confirmation() deletes originals
            # Push undo regardless — mirror already applied
            self.push_undo_state()
            self._selected_items = []
            self.set_mode(None)

    # ── Break (2-point) ──────────────────────────────────────────────
    def _press_break(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._break_target is None:
            hit = self._tools._find_geometry_at(pos)
            if hit is not None:
                self._break_target = hit
                self._break_highlight = self._tools._highlight_item(hit)
                self.instructionChanged.emit("Pick first break point on object")
        elif self._break_p1 is None:
            self._break_p1 = snapped
            self.instructionChanged.emit("Pick second break point")
        else:
            self._tools._break_item(self._break_target, self._break_p1, snapped)
            self.push_undo_state()
            self.set_mode("break")

    # ── Break at Point ───────────────────────────────────────────────
    def _press_break_at_point(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._break_at_target is None:
            hit = self._tools._find_geometry_at(pos)
            if hit is not None:
                self._break_at_target = hit
                self._break_at_highlight = self._tools._highlight_item(hit)
                self.instructionChanged.emit("Pick break point on object")
        else:
            self._tools._break_at_point(self._break_at_target, snapped)
            self.push_undo_state()
            self.set_mode("break_at_point")

    # ── Fillet ───────────────────────────────────────────────────────
    def _press_fillet(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._fillet_item1 is None:
            hit = self._tools._find_geometry_at(pos)
            if hit is not None and isinstance(hit, LineItem):
                self._fillet_item1 = hit
                self._fillet_highlight1 = self._tools._highlight_item(hit)
                self.instructionChanged.emit("Click second line (Tab = set radius)")
        elif self._fillet_item2 is None:
            hit = self._tools._find_geometry_at(pos)
            if hit is not None and isinstance(hit, LineItem) and hit is not self._fillet_item1:
                self._fillet_item2 = hit
                self._fillet_highlight2 = self._tools._highlight_item(hit)
                data = self._tools._compute_fillet(self._fillet_item1, self._fillet_item2,
                                           self._fillet_radius)
                if data is None:
                    self._show_status("Cannot fillet these lines (parallel?)")
                    self.set_mode("fillet")
                else:
                    # Show preview
                    pp = QPainterPath()
                    r = data["radius"]
                    c = data["center"]
                    pp.addEllipse(c, r, r)
                    self._fillet_preview = self.addPath(
                        pp, QPen(QColor("#00ff00"), 1, Qt.PenStyle.DashLine))
                    self._fillet_preview.setPen(
                        QPen(QColor("#00ff00"), 1, Qt.PenStyle.DashLine))
                    self._fillet_preview.pen().setCosmetic(True)
                    self.instructionChanged.emit(
                        f"Radius: {self._fillet_radius:.1f}  Press Enter to commit, Tab to change")

    # ── Chamfer ──────────────────────────────────────────────────────
    def _press_chamfer(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._chamfer_item1 is None:
            hit = self._tools._find_geometry_at(pos)
            if hit is not None and isinstance(hit, LineItem):
                self._chamfer_item1 = hit
                self._chamfer_highlight1 = self._tools._highlight_item(hit)
                self.instructionChanged.emit("Click second line (Tab = set distance)")
        elif self._chamfer_item2 is None:
            hit = self._tools._find_geometry_at(pos)
            if hit is not None and isinstance(hit, LineItem) and hit is not self._chamfer_item1:
                self._chamfer_item2 = hit
                self._chamfer_highlight2 = self._tools._highlight_item(hit)
                data = self._tools._compute_chamfer(self._chamfer_item1, self._chamfer_item2,
                                             self._chamfer_dist)
                if data is None:
                    self._show_status("Cannot chamfer these lines (parallel?)")
                    self.set_mode("chamfer")
                else:
                    self._chamfer_preview = QGraphicsLineItem(
                        data["cp1"].x(), data["cp1"].y(),
                        data["cp2"].x(), data["cp2"].y())
                    p = QPen(QColor("#00ff00"), 1, Qt.PenStyle.DashLine)
                    p.setCosmetic(True)
                    self._chamfer_preview.setPen(p)
                    self.addItem(self._chamfer_preview)
                    self.instructionChanged.emit(
                        f"Distance: {self._chamfer_dist:.1f}  Press Enter to commit, Tab to change")

    # ── Stretch (base/destination pick after crossing window) ────────
    def _press_stretch(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._stretch_vertices or self._stretch_full_items:
            if self._stretch_base is None:
                self._stretch_base = snapped
                self.instructionChanged.emit("Pick destination point")
            else:
                delta = QPointF(snapped.x() - self._stretch_base.x(),
                                snapped.y() - self._stretch_base.y())
                self._tools._commit_stretch(delta)
                self.push_undo_state()
                self.set_mode(None)

    # ── Trim / Extend (Sprint Y) ─────────────────────────────────────
    def _press_trim(self, event, pos, snapped, item_under, node_under, pipe_under):
        self._tools._handle_trim_click(snapped)

    def _press_extend(self, event, pos, snapped, item_under, node_under, pipe_under):
        self._tools._handle_extend_click(snapped)

    # ── Merge / Hatch ────────────────────────────────────────────────
    def _press_merge_hatch(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self.mode == "merge_points":
            self._tools._handle_merge_click(snapped)

    # ── Constraints ──────────────────────────────────────────────────
    def _press_constraint(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self.mode == "constraint_concentric":
            self._tools._handle_constraint_concentric_click(snapped)
        elif self.mode == "constraint_dimensional":
            self._tools._handle_constraint_dimensional_click(snapped)

    def _press_polyline(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._polyline_active is None:
            # First click — create the polyline item
            tmpl = self._get_geometry_template()
            _c, _lw = self._geom_color_lw()
            pl = PolylineItem(snapped, _c, _lw)
            pl.level = tmpl.level
            pl._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
            self.addItem(pl)
            self._polylines.append(pl)
            self._polyline_active = pl
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick next point (Enter to finish)")
        else:
            pts = self._polyline_active._points
            # Close-on-start: ≥3 vertices and click within tolerance of pts[0].
            if len(pts) >= 3:
                scale = self._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                d0 = math.hypot(snapped.x() - pts[0].x(), snapped.y() - pts[0].y())
                if d0 <= tol:
                    pl = self._polyline_active
                    pl.close()
                    pl.finalize()
                    self._polyline_active = None
                    self._hide_polyline_close_indicator()
                    pl.setSelected(True)
                    self.preview_pipe.hide()
                    for v in self.views(): v.viewport().update()
                    self.push_undo_state()
                    self.instructionChanged.emit("Pick first point")
                    return
            # Subsequent clicks — append vertex (apply Ctrl constraint if held)
            tip = snapped
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and len(self._polyline_active._points) >= 1):
                tip = self._constrain_angle(
                    self._polyline_active._points[-1], snapped
                )
            self._commit_polyline_at(tip)
        # don't let super() deselect items mid-draw

    def _commit_polyline_at(self, tip):
        """Append one vertex to the active polyline at ``tip``.

        The commit half of :meth:`_press_polyline`, split out so that Dynamic
        Input is an alternative *point source* rather than an alternative
        *commit path*: a typed exact point and a mouse click land here, so they
        cannot drift apart.

        ``tip`` is expected to arrive fully constrained (OSNAP, ALIGN,
        Ctrl) — this method applies no further constraint.

        Deliberately does **not** push an undo state.  Polyline undo is pushed
        once when the chain is finalized, not per vertex, so pushing here would
        put half-drawn polylines on the stack and make a typed vertex behave
        differently from a clicked one.  The retired modal ``_DynInput``
        polyline branch did push per vertex; that is the drift being removed.

        Unlike the line commit the placement stays live afterwards: the new
        vertex becomes the next anchor, so ``get_placement_anchor()`` keeps
        answering and the HUD is reseeded for the following segment.

        Args:
            tip: The scene-space position of the new vertex.  No-op when no
                polyline is being drawn.

        Returns:
            True when a vertex was appended, False when no polyline is active.
            Polyline has no magnitude floor of its own, so False here only ever
            means "nothing to append to" (decision D2).
        """
        pl = self._polyline_active
        if pl is None:
            return False
        pl.append_point(tip)
        # The published point described the segment just committed; the next
        # frame republishes from the new anchor.
        self.clear_placement_state()
        return True

    def _delete_or_pop_polyline_vertex(self) -> bool:
        """Delete key during polyline placement pops the last vertex.

        At one remaining vertex the in-progress polyline is discarded and the
        tool re-arms.  Returns True when it handled the key (placement active).
        """
        # Floor polygon placement: pop the last boundary vertex (discard the
        # in-progress slab at one vertex).  Shares the Delete-pop UX with the
        # polyline tool.
        if self.mode == "floor" and self._floor_active is not None:
            fa = self._floor_active
            if len(fa._points) <= 1:
                if fa.scene() is self:
                    self.removeItem(fa)
                if fa in self._floor_slabs:
                    self._floor_slabs.remove(fa)
                self._floor_active = None
                self.preview_pipe.hide()
                self.instructionChanged.emit("Pick first boundary point")
            else:
                fa._points.pop()
                fa._rebuild_path()
            for v in self.views(): v.viewport().update()
            return True
        pl = self._polyline_active
        if self.mode != "polyline" or pl is None:
            return False
        if len(pl._points) <= 1:
            if pl.scene() is self:
                self.removeItem(pl)
            if pl in self._polylines:
                self._polylines.remove(pl)
            self._polyline_active = None
            self._hide_polyline_close_indicator()
            self.instructionChanged.emit("Pick first point")
        else:
            pl._points.pop()
            pl._rebuild_path()
            self._hide_polyline_close_indicator()
        for v in self.views(): v.viewport().update()
        return True

    def _register_gridline(self, gl):
        """Add a gridline to the scene and the ``_gridlines`` collection with
        canonical defaults applied.

        This is the per-item nucleus shared by ``_make_line_like`` (single
        placement) and ``_commit_gridline_replicate`` (batch placement).
        Counter-sync, auto-labelling, selection, and duplicate-warning are
        intentionally left at each call site because their ordering differs.
        """
        self.addItem(gl)
        apply_category_defaults(gl)
        self._gridlines.append(gl)

    def _make_line_like(self, anchor, tip):
        """Factory: build the item for the active line-like draw mode.

        Mode ``"draw_gridline"`` builds a :class:`GridlineItem` (adopting the
        current Grid Line display defaults); every other line-like mode builds
        a :class:`LineItem` with the active geometry template's level and
        colour/line-weight.  Both paths add the item, register it in the right
        collection, and select it.
        """
        if self.mode == "draw_gridline":
            # Sync the auto-number counters to the EXISTING gridlines BEFORE
            # constructing (GridlineItem.__init__ auto-labels at construction),
            # so a freshly placed gridline continues the sequence (e.g. "4"
            # after a 1/2/3 seed) instead of restarting at "1"/"A".
            sync_grid_counters(self._gridlines)
            gl = GridlineItem(anchor, tip)
            # Apply category display defaults first, then overlay the placement
            # template so user-preset values win over category defaults.
            self._register_gridline(gl)      # addItem + apply_category_defaults + append
            # Copy non-geometric template values onto the placed gridline.
            _tmpl = self._get_gridline_template()
            gl._bubble1_offset = _tmpl._bubble1_offset
            gl._bubble2_offset = _tmpl._bubble2_offset
            gl.bubble1.setVisible(_tmpl.bubble1.isVisible())
            gl.bubble2.setVisible(_tmpl.bubble2.isVisible())
            gl._locked = _tmpl._locked
            if _tmpl._display_overrides:
                gl._display_overrides = dict(_tmpl._display_overrides)
            gl._rebuild_geometry()
            gl.setSelected(True)
            self.requestPropertyUpdate.emit(gl)
            sync_grid_counters(self._gridlines)
            apply_duplicate_warnings(self._gridlines)
            return gl
        tmpl = self._get_geometry_template()
        _c, _lw = self._geom_color_lw()
        item = LineItem(anchor, tip, _c, _lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        self.addItem(item)
        self._draw_lines.append(item)
        item.setSelected(True)
        return item

    def _press_draw_line(self, event, pos, snapped, item_under, node_under, pipe_under):
        _is_grid = self.mode == "draw_gridline"
        if self._draw_line_anchor is None:
            self._draw_line_anchor = snapped
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick end point" if _is_grid else "Pick second point")
        else:
            # Place the item (apply Ctrl constraint if held)
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._constrain_angle(self._draw_line_anchor, snapped)
            self._commit_draw_line_at(tip)

    def _commit_draw_line_at(self, tip):
        """Commit the armed line-like placement, ending at ``tip``.

        This is the commit half of :meth:`_press_draw_line`, split out so that
        Dynamic Input is an alternative *point source* rather than an
        alternative *commit path*: a typed exact point and a mouse click land
        in this one method, so they cannot drift apart.

        ``tip`` is expected to be fully constrained already (OSNAP, ALIGN,
        Ctrl) — this method applies no further constraint. A too-short line is
        rejected and leaves the anchor armed so the user can re-pick.

        Args:
            tip: The scene-space end point of the line. No-op when no anchor
                is armed.

        Returns:
            True when a line was committed, False when it was refused (no
            anchor, or under the too-short floor).  Decision D2: the caller
            turns a False into a flagged HUD field rather than the placement
            silently evaporating into a status-bar message the user never sees.
        """
        anchor = self._draw_line_anchor
        if anchor is None:
            return False
        _is_grid = self.mode == "draw_gridline"
        # Reject zero-length lines
        if math.hypot(tip.x() - anchor.x(),
                      tip.y() - anchor.y()) < 0.5:
            self._show_status(
                "Gridline too short — skipped" if _is_grid else "Line too short — skipped",
                timeout=2000)
            return False
        self._make_line_like(anchor, tip)
        for v in self.views(): v.viewport().update()
        self._draw_line_anchor = None
        self.clear_placement_state()
        self.preview_pipe.hide()
        self.push_undo_state()
        self.instructionChanged.emit("Pick start point" if _is_grid else "Pick first point")
        return True

    def _press_draw_rectangle(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._draw_rect_rotating:
            # Third click: commit at the orientation from the pivot to the click.
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._draw_rect_pivot is not None):
                snapped = self._constrain_angle(self._draw_rect_pivot, snapped)
            self._commit_rectangle_rotated(
                self._rect_rotation_angle_to(snapped))
        elif self._draw_rect_anchor is None:
            self._draw_rect_anchor = snapped
            self.update_preview_node(snapped)
            _instr = "Pick opposite corner" if not self._draw_rect_from_center else "Pick corner (from center)"
            self.instructionChanged.emit(_instr)
            # Create preview rect
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            _prev_pen = QPen(QColor(self._geom_color_lw()[0]), 2, Qt.PenStyle.DashLine)
            _prev_pen.setCosmetic(True)
            preview.setPen(_prev_pen)
            preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            preview.setZValue(200)
            self.addItem(preview)
            self._draw_rect_preview = preview
        else:
            # Second click: size the axis-aligned rect and enter the rotate step
            # (no longer commits — the third click/typed angle does).
            self._advance_rectangle_to_rotate_step(snapped)

    def _rect_rotation_angle_to(self, cursor) -> float:
        """Return the absolute orientation (Y-up degrees from +x) pivot→``cursor``.

        0° when the cursor is due-east of the pivot, i.e. axis-aligned.  Shared
        by the third mouse click and the rotate preview so both read the same
        heading.  Falls back to 0° when the pivot is unset (a guard; the rotate
        step always has one).
        """
        piv = self._draw_rect_pivot
        if piv is None:
            return 0.0
        return math.degrees(math.atan2(-(cursor.y() - piv.y()),
                                       cursor.x() - piv.x()))

    def _rect_sizing_points(self, corner):
        """Return the axis-aligned ``(pt1, pt2)`` the sizing step produces.

        Delegates to ``rect_sizing_points`` (shared with wall-rect placement) so
        the 2D-geo rect and wall rect use identical sizing math.  Returns
        ``(None, None)`` when unarmed.
        """
        from .construction_geometry import rect_sizing_points
        anc = self._draw_rect_anchor
        if anc is None:
            return None, None
        return rect_sizing_points(anc, corner, self._draw_rect_from_center)

    def _advance_rectangle_to_rotate_step(self, corner) -> bool:
        """Advance an armed rectangle from the sizing step to the rotate step.

        Stores the sized axis-aligned rect (``_draw_rect_sized_pt1/_pt2``) and
        its pivot (the first-click anchor — one of the rect's corners — in
        corner mode, the rect centre, which equals the anchor, in centre mode),
        sets
        ``_draw_rect_rotating``, and re-fits the preview rect to the sized
        extents.  Shared verbatim by the mouse second click and the sizing
        Dynamic Input applier, so both hand off to the rotate step identically.

        Args:
            corner: The second point, fully constrained already.

        Returns:
            True when the rect advanced to the rotate step, False when it was
            refused (no anchor, or an extent under the too-small floor).
        """
        pt1, pt2 = self._rect_sizing_points(corner)
        if pt1 is None:
            return False
        # Reject zero-size rectangles (decision D2 — the floor lives here, the
        # same threshold the old 2-click commit used).
        if abs(pt2.x() - pt1.x()) < 0.5 or abs(pt2.y() - pt1.y()) < 0.5:
            self._show_status("Rectangle too small — skipped", timeout=2000)
            return False
        self._draw_rect_sized_pt1 = pt1
        self._draw_rect_sized_pt2 = pt2
        # Pivot: corner mode turns about the first-click anchor (one of the
        # rect's corners); centre mode turns about the rect centre = the anchor.
        self._draw_rect_pivot = QPointF(self._draw_rect_anchor)
        self._draw_rect_rotating = True
        # Snap the preview to the final sized rect; the rotate preview spins it.
        if self._draw_rect_preview is not None:
            self._draw_rect_preview.setRect(QRectF(pt1, pt2).normalized())
        # Rotation reference guides (0° datum + live sweep), drawn from the pivot.
        self._clear_rect_ref_lines()
        self._draw_rect_ref_line0 = self._make_ref_line()
        self._draw_rect_ref_lineA = self._make_ref_line()
        self._update_rect_ref_lines(0.0)
        self.clear_placement_state()
        self.instructionChanged.emit("Pick rotation / type angle")
        return True

    def _apply_rectangle_dynamic_input(self, geometry) -> bool:
        """Route a resolved rectangle value to the right step's applier.

        Rectangle's schema is step-dependent, so its applier is too: at the
        sizing step the ``rectangle`` schema resolves to a far-corner QPointF
        (advance to the rotate step), at the rotate step the ``rotation`` schema
        resolves to a ``{"angle_deg": …}`` dict (commit).

        Returns:
            The step applier's verdict.
        """
        if self._draw_rect_rotating:
            return self._apply_rectangle_rotation(geometry)         # dict
        return self._advance_rectangle_to_rotate_step(geometry)      # QPointF

    def _apply_rectangle_rotation(self, geometry) -> bool:
        """Rotate-step applier: commit the sized rect at the typed angle."""
        return self._commit_rectangle_rotated(geometry["angle_deg"])

    def _commit_rectangle_rotated(self, angle_deg) -> bool:
        """Commit the sized rectangle rotated to ``angle_deg`` about its pivot.

        The real commit for the 3-step placement (Task 12).  The 2-click sizing
        already produced ``_draw_rect_sized_pt1/_pt2`` (axis-aligned) and the
        ``_draw_rect_pivot`` the rotation turns about (the first-click anchor —
        one of the rect's corners — in corner mode, the centre in centre mode).
        This builds the ``RectangleItem`` from those
        corners and applies ``set_angle(angle_deg, pivot)`` — a 0° rotate leaves
        it exactly axis-aligned, the old 2-click end state.

        Shared by the third mouse click and the ``rotation`` Dynamic Input value
        (both route in through ``_apply_rectangle_rotation``).

        Args:
            angle_deg: Absolute orientation, Y-up degrees from +x.

        Returns:
            True when a ``RectangleItem`` was committed, False when the sizing
            state is missing or the sized rect is degenerate (a guard — the
            floor already gated at the sizing step).
        """
        pt1 = self._draw_rect_sized_pt1
        pt2 = self._draw_rect_sized_pt2
        if pt1 is None or pt2 is None:
            return False
        # Guard: the sizing step already rejected sub-floor extents, but keep it
        # so a direct call can never build a degenerate item.
        if abs(pt2.x() - pt1.x()) < 0.5 or abs(pt2.y() - pt1.y()) < 0.5:
            return False
        tmpl = self._get_geometry_template()
        _c, _lw = self._geom_color_lw()
        item = RectangleItem(pt1, pt2, _c, _lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        item.set_angle(angle_deg, self._draw_rect_pivot)
        self.addItem(item)
        self._draw_rects.append(item)
        item.setSelected(True)
        for v in self.views(): v.viewport().update()
        # Remove preview
        if self._draw_rect_preview is not None:
            self.removeItem(self._draw_rect_preview)
            self._draw_rect_preview = None
        _from_centre = self._draw_rect_from_center
        # Reset the full rect state (anchor + rotate step + sized rect + pivot).
        self._draw_rect_anchor = None
        self._draw_rect_rotating = False
        self._draw_rect_sized_pt1 = None
        self._draw_rect_sized_pt2 = None
        self._draw_rect_pivot = None
        self._clear_rect_ref_lines()
        self.clear_placement_state()
        self.push_undo_state()
        self.instructionChanged.emit(
            "Pick center point" if _from_centre else "Pick first corner")
        return True

    def _press_draw_circle(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._draw_circle_center is None:
            self._draw_circle_center = snapped
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick radius point")
            # Create preview circle
            preview = QGraphicsEllipseItem(snapped.x(), snapped.y(), 0, 0)
            _prev_pen = QPen(QColor(self._geom_color_lw()[0]), 2, Qt.PenStyle.DashLine)
            _prev_pen.setCosmetic(True)
            preview.setPen(_prev_pen)
            preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            preview.setZValue(200)
            self.addItem(preview)
            self._draw_circle_preview = preview
        else:
            self._commit_draw_circle_at(snapped)

    def _commit_draw_circle_at(self, rim):
        """Commit the armed circle with ``rim`` on its circumference.

        The commit half of :meth:`_press_draw_circle`, split out so Dynamic
        Input is an alternative *point source* rather than an alternative
        *commit path*.

        Only the distance from the centre matters — the radius is a ``hypot``
        — which is what lets ``resolve_circle`` return a bare ``+X`` point for
        a typed radius without encoding a meaningless direction.

        Args:
            rim: A scene-space point on the circumference, fully constrained.

        Returns:
            True when a circle was committed, False when it was refused (no
            centre, or a radius under the too-small floor).

        A refusal now leaves the centre armed and the preview up, matching the
        line and rectangle commits; this path used to tear the placement down
        and push an undo state even for a circle it never created.
        """
        centre = self._draw_circle_center
        if centre is None:
            return False
        r = math.hypot(rim.x() - centre.x(), rim.y() - centre.y())
        if r < 0.5:
            self._show_status("Circle radius too small — skipped", timeout=2000)
            return False
        tmpl = self._get_geometry_template()
        _c, _lw = self._geom_color_lw()
        item = CircleItem(centre, r, _c, _lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        self.addItem(item)
        self._draw_circles.append(item)
        item.setSelected(True)
        for v in self.views(): v.viewport().update()
        # Remove preview
        if self._draw_circle_preview is not None:
            self.removeItem(self._draw_circle_preview)
            self._draw_circle_preview = None
        self._draw_circle_center = None
        self.clear_placement_state()
        self.push_undo_state()
        self.instructionChanged.emit("Pick center point")
        return True

    # ── Polygon drawing ───────────────────────────────────────────────

    def _polygon_readout(self) -> str:
        """Return the live-state suffix shown in every polygon instruction line.

        Format: ``"{n} sides (↑/↓)  ·  {shape} (←/→)"``.  Called by
        ``_press_polygon``, ``_cycle_polygon_sides``, and
        ``_toggle_polygon_inscribed`` so the full hint always includes the
        current step prompt.
        """
        shape = "inscribed" if self._polygon_inscribed else "circumscribed"
        return f"{self._polygon_sides} sides (↑/↓)  ·  {shape} (←/→)"

    def _press_polygon(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._polygon_rotating:
            # Step 2: commit at the pivot→click orientation.
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._polygon_center is not None):
                snapped = self._constrain_angle(self._polygon_center, snapped)
            self._commit_polygon_rotated(self._polygon_rotation_angle_to(snapped))
        elif self._polygon_center is None:
            # Step 0: arm the centre.
            self._polygon_center = snapped
            self.update_preview_node(snapped)
            self.instructionChanged.emit(
                f"Pick radius  |  {self._polygon_readout()}")
        else:
            # Step 1: set the radius and advance to the rotate step.
            self._advance_polygon_to_rotate_step(snapped)

    def _polygon_rotation_angle_to(self, cursor) -> float:
        """Return absolute Y-up orientation (degrees from +x) centre→``cursor``.

        0° when the cursor is due-east of the centre (axis-aligned first vertex).
        Falls back to 0° when the centre is unset (guard — rotate step always has
        one).
        """
        c = self._polygon_center
        if c is None:
            return 0.0
        return math.degrees(math.atan2(-(cursor.y() - c.y()),
                                       cursor.x() - c.x()))

    def _advance_polygon_to_rotate_step(self, rim) -> bool:
        """Advance an armed polygon from the sizing step to the rotate step.

        Stores the sized radius (``_polygon_sized_radius``), sets
        ``_polygon_rotating = True``, rebuilds the ghost at rotation 0
        (axis-aligned), and shows the reference circle + a 0° datum line.
        Shared by the mouse second click and the sizing Dynamic Input applier.

        Args:
            rim: The radius-pick point (fully constrained).

        Returns:
            True when advanced; False when rejected (no centre, or radius < 0.5).
        """
        c = self._polygon_center
        if c is None:
            return False
        r = math.hypot(rim.x() - c.x(), rim.y() - c.y())
        if r < 0.5:
            self._show_status("Polygon radius too small — skipped", timeout=2000)
            return False
        self._polygon_sized_radius = r
        self._polygon_rotating = True
        # Rebuild ghost axis-aligned (rotation 0) at the fixed radius.
        if self._polygon_preview is not None and self._polygon_preview.scene() is self:
            self.removeItem(self._polygon_preview)
            self._polygon_preview = None
        self._polygon_preview = self._build_polygon_ghost(c, r, 0.0)
        # Reference circle centred on the centre at the sized radius.
        self._clear_polygon_ref_items()
        self._polygon_ref_circle = self._make_ref_circle()
        self._polygon_ref_circle.setRect(
            c.x() - r, c.y() - r, 2 * r, 2 * r)
        # Radial reference line (0° datum) from centre eastwards.
        self._polygon_ref_lineA = self._make_ref_line()
        self._polygon_ref_lineA.setLine(c.x(), c.y(), c.x() + r, c.y())
        self.clear_placement_state()
        self.instructionChanged.emit(
            f"Pick rotation angle  |  {self._polygon_readout()}")
        return True

    def _apply_polygon_dynamic_input(self, geometry) -> bool:
        """Route a resolved polygon value to the right step's applier.

        At the sizing step the ``polygon`` schema resolves to a radius QPointF
        (advance to the rotate step); at the rotate step the ``rotation`` schema
        resolves to a ``{"angle_deg": …}`` dict (commit).  Mirrors
        ``_apply_rectangle_dynamic_input``.
        """
        if self._polygon_rotating:
            return self._commit_polygon_rotated(geometry["angle_deg"])   # dict
        return self._advance_polygon_to_rotate_step(geometry)             # QPointF

    def _commit_polygon_rotated(self, angle_deg) -> bool:
        """Commit the sized polygon at ``angle_deg`` orientation (Y-up, degrees).

        Builds ``RegularPolygonItem`` from the stored centre and sized radius,
        clears all placement state, and pushes undo.  Shared by the third mouse
        click and the ``rotation`` Dynamic Input value.

        Args:
            angle_deg: Absolute orientation, Y-up degrees from +x.

        Returns:
            True when committed; False when sizing state is missing.
        """
        c = self._polygon_center
        r = self._polygon_sized_radius
        if c is None or r is None:
            return False
        tmpl = self._get_geometry_template()
        _c, _lw = self._geom_color_lw()
        item = RegularPolygonItem(c, sides=self._polygon_sides, radius_mm=r,
                                  rotation_deg=angle_deg,
                                  inscribed=self._polygon_inscribed,
                                  color=_c, lineweight=_lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        self.addItem(item)
        self._draw_polygons.append(item)
        item.setSelected(True)
        # Remove preview ghost.
        if self._polygon_preview is not None:
            if self._polygon_preview.scene() is self:
                self.removeItem(self._polygon_preview)
            self._polygon_preview = None
        # Clear all placement state.
        self._polygon_center = None
        self._polygon_rotating = False
        self._polygon_sized_radius = None
        self._clear_polygon_ref_items()
        self.clear_placement_state()
        for v in self.views(): v.viewport().update()
        self.push_undo_state()
        self.instructionChanged.emit(
            f"Pick centre point  |  {self._polygon_readout()}")
        return True

    def _commit_polygon_at(self, rim):
        """Legacy 2-step commit: radius-pick point carries both radius and rotation.

        Kept for backward compatibility with the HUD ``polygon`` schema resolver
        which returns a QPointF on the rim circle.  In 3-step placement this is
        only reached via ``_apply_polygon_dynamic_input`` at the sizing step,
        which calls ``_advance_polygon_to_rotate_step`` instead — so this method
        is no longer the commit path.  It is preserved so external callers (e.g.
        tests that pre-date the 3-step change) can still advance the sizing step
        by passing a point.
        """
        return self._advance_polygon_to_rotate_step(rim)

    def _build_polygon_ghost(self, center, radius, rotation_deg) -> "RegularPolygonItem":
        """Create and return a dashed ghost RegularPolygonItem added to the scene."""
        _c, _lw = self._geom_color_lw()
        ghost = RegularPolygonItem(center, sides=self._polygon_sides, radius_mm=radius,
                                   rotation_deg=rotation_deg,
                                   inscribed=self._polygon_inscribed,
                                   color=_c, lineweight=_lw)
        pen = QPen(QColor(_c), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        ghost.setPen(pen)
        ghost.setZValue(200)
        ghost.setFlag(ghost.GraphicsItemFlag.ItemIsSelectable, False)
        self.addItem(ghost)
        return ghost

    def _preview_from_polygon(self, tip):
        """Live ghost of the polygon during the sizing step (centre→tip).

        During the sizing step, tip sets both radius and rotation; the ghost
        tracks both live.  During the rotate step, use ``_preview_polygon_rotation``
        instead (which keeps a fixed radius and only spins the ghost).
        """
        if self._polygon_center is None:
            return
        c = self._polygon_center
        dx, dy = tip.x() - c.x(), tip.y() - c.y()
        r = math.hypot(dx, dy)
        if r < 0.5:
            return
        # During sizing step, rotation tracks the cursor bearing.
        rot = 0.0  # axis-aligned during sizing step (rotation added at step 2)
        if self._polygon_preview is not None and self._polygon_preview.scene() is self:
            self.removeItem(self._polygon_preview)
        self._polygon_preview = self._build_polygon_ghost(c, r, rot)
        # Also update / create the reference circle (shows bounding circle).
        if self._polygon_ref_circle is None:
            self._polygon_ref_circle = self._make_ref_circle()
        self._polygon_ref_circle.setRect(c.x() - r, c.y() - r, 2 * r, 2 * r)

    def _preview_polygon_rotation(self, angle_deg) -> None:
        """Spin the sized-radius polygon ghost to ``angle_deg`` during rotate step.

        Mirrors ``_preview_rectangle_rotation``: only the ghost's orientation
        changes, the radius is fixed at ``_polygon_sized_radius``.  Also updates
        the radial reference line.  A no-op until the ghost and centre exist.
        """
        c = self._polygon_center
        r = self._polygon_sized_radius
        if c is None or r is None:
            return
        # Rebuild ghost at the fixed radius and new rotation.
        if self._polygon_preview is not None and self._polygon_preview.scene() is self:
            self.removeItem(self._polygon_preview)
        self._polygon_preview = self._build_polygon_ghost(c, r, angle_deg)
        # Update the radial reference line to follow the cursor heading.
        if self._polygon_ref_lineA is not None:
            rad = math.radians(angle_deg)
            self._polygon_ref_lineA.setLine(
                c.x(), c.y(),
                c.x() + r * math.cos(rad),
                c.y() - r * math.sin(rad))  # Y-up: subtract sin

    def _cycle_polygon_sides(self, direction: int):
        self._polygon_sides = max(3, min(120, self._polygon_sides + direction))
        if self._last_scene_pos is not None:
            if self._polygon_rotating:
                angle = self._polygon_rotation_angle_to(self._last_scene_pos)
                self._preview_polygon_rotation(angle)
            else:
                self._preview_from_polygon(self._last_scene_pos)
        if self._polygon_rotating:
            self.instructionChanged.emit(
                f"Pick rotation angle  |  {self._polygon_readout()}")
        elif self._polygon_center is not None:
            self.instructionChanged.emit(
                f"Pick radius  |  {self._polygon_readout()}")
        else:
            self.instructionChanged.emit(
                f"Pick centre point  |  {self._polygon_readout()}")

    def _toggle_polygon_inscribed(self):
        self._polygon_inscribed = not self._polygon_inscribed
        if self._last_scene_pos is not None:
            if self._polygon_rotating:
                angle = self._polygon_rotation_angle_to(self._last_scene_pos)
                self._preview_polygon_rotation(angle)
            else:
                self._preview_from_polygon(self._last_scene_pos)
        if self._polygon_rotating:
            self.instructionChanged.emit(
                f"Pick rotation angle  |  {self._polygon_readout()}")
        elif self._polygon_center is not None:
            self.instructionChanged.emit(
                f"Pick radius  |  {self._polygon_readout()}")
        else:
            self.instructionChanged.emit(
                f"Pick centre point  |  {self._polygon_readout()}")

    # ── Wall primitive routers (variant dispatch) ─────────────────────
    def _set_wall_primitive(self, prim, from_center=False):
        """Apply the wall primitive variant (called by _PLACEMENT_VARIANTS apply_fn).

        Sets ``_wall_primitive`` and, for the rect primitives, also sets
        ``_wall_rect_from_center`` so corner and center variants are distinct.
        """
        self._wall_primitive = prim
        if prim == "rect":
            self._wall_rect_from_center = from_center

    def _press_wall_router(self, *args):
        """Dispatch a wall click to the active primitive's builder."""
        if self._wall_primitive == "rect":
            return self._press_wall_rect(*args)
        return self._press_wall(*args)

    def _move_wall_router(self, *args):
        """Dispatch a wall mouse-move to the active primitive's preview builder."""
        if self._wall_primitive == "rect":
            return self._move_wall_rect(*args)
        return self._move_wall(*args)

    def _apply_wall_dynamic_input(self, geometry) -> bool:
        """Commit a typed wall placement via the same builders the mouse uses.

        ``geometry`` is the resolved QPointF (the line/rectangle placement
        schemas resolve to the point a click would produce), routed through the
        primitive's press handler for structural commit parity.

        Args:
            geometry: The scene-space target point resolved by the active schema.

        Returns:
            True always (the press handlers do not return a refusal; a too-short
            wall emits a status message and the anchor remains armed, matching
            mouse behaviour).
        """
        if self._wall_primitive == "rect":
            if self._wall_rect_rotating:
                # Rotate step: geometry is a dict {"angle_deg": …}
                return self._commit_wall_rect_rotated(geometry["angle_deg"])
            # Sizing step: geometry is a QPointF (the far corner / second point)
            return self._advance_wall_rect_to_rotate_step(geometry)
        else:
            self._press_wall(None, geometry, geometry, None, None, None)
        return True

    # ── Wall drawing ──────────────────────────────────────────────────
    def _press_wall(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._wall_anchor is None:
            self._wall_anchor = snapped
            self._wall_chain_start = QPointF(snapped)
            self.update_preview_node(snapped)
            self.instructionChanged.emit(f"Pick wall end point [{self._wall_alignment}]  Space=align")
        else:
            tip = snapped
            if event is not None and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                tip = self._constrain_angle(self._wall_anchor, snapped)
            # Close wall loop: if clicking near chain start → snap tip to start
            _close_loop = False
            if self._wall_chain_start is not None:
                scale = self._active_view_scale()
                tol = 15.0 / max(scale, 1e-6)
                d_start = math.hypot(tip.x() - self._wall_chain_start.x(),
                                     tip.y() - self._wall_chain_start.y())
                if d_start <= tol:
                    tip = QPointF(self._wall_chain_start)
                    _close_loop = True
            _tmpl = self._get_wall_template()
            wall = WallSegment(self._wall_anchor, tip,
                               thickness_mm=_tmpl._thickness_mm,
                               color=_tmpl._color.name())
            wall.name = f"Wall {self._next_wall_num}"
            self._next_wall_num += 1
            wall._alignment = _tmpl._alignment
            wall._fill_mode = _tmpl._fill_mode
            wall.level = _tmpl.level if _tmpl.level else self.active_level
            wall._base_level = _tmpl._base_level if _tmpl._base_level else self.active_level
            wall._top_level = getattr(_tmpl, "_top_level", "")
            wall._height_mm = getattr(_tmpl, "_height_mm", 3048.0)
            # Keep scene alignment in sync with template
            self._wall_alignment = _tmpl._alignment
            self.addItem(wall)
            self._walls.append(wall)
            apply_category_defaults(wall)
            # Auto-join: snap endpoints to nearby walls
            self._auto_join_wall(wall)
            wall.setSelected(True)
            for v in self.views(): v.viewport().update()
            self.preview_pipe.hide()
            if self._wall_preview_rect is not None:
                self._wall_preview_rect.hide()
            self.push_undo_state()
            if _close_loop or self._wall_primitive == "line":
                # Line variant: one segment then re-arm fresh.
                # Polyline: an explicit loop-close also stops the chain.
                self._wall_anchor = None
                self._wall_chain_start = None
                self.instructionChanged.emit(
                    f"Pick wall start point [{self._wall_alignment}]")
            else:
                # Polyline: end of this wall becomes start of next.
                self._wall_anchor = QPointF(tip)
                self.instructionChanged.emit(
                    f"Pick next wall end [{self._wall_alignment}]  Space=align  Esc=stop")

    # ── Wall rectangle drawing ──────────────────────────────────────────
    def _press_wall_rect(self, event, pos, snapped, item_under, node_under, pipe_under):
        """3-step wall-rectangle placement, mirroring ``_press_draw_rectangle``.

        Step 1 (no anchor): set anchor, create dashed preview.
        Step 2 (anchor set, not rotating): advance to rotate step via
            ``_advance_wall_rect_to_rotate_step``.
        Step 3 (rotating): commit 4 WallSegments at the rotation angle.
        """
        if self._wall_rect_rotating:
            # Third click: commit at the pivot→cursor heading.
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._wall_rect_pivot is not None):
                snapped = self._constrain_angle(self._wall_rect_pivot, snapped)
            self._commit_wall_rect_rotated(
                self._wall_rect_rotation_angle_to(snapped))
        elif self._wall_rect_anchor is None:
            # First click: store anchor, show dashed preview rect.
            self._wall_rect_anchor = snapped
            self.update_preview_node(snapped)
            _instr = ("Pick corner (from centre)" if self._wall_rect_from_center
                      else "Pick opposite corner for rectangular wall")
            self.instructionChanged.emit(_instr)
            _tmpl = self._get_wall_template()
            _wc = QColor(_tmpl._color)
            pen = QPen(_wc, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            preview.setPen(pen)
            _wc.setAlpha(30)
            preview.setBrush(QBrush(_wc))
            preview.setZValue(200)
            self.addItem(preview)
            self._wall_rect_preview = preview
        else:
            # Second click: size the axis-aligned rect and enter rotate step.
            self._advance_wall_rect_to_rotate_step(snapped)

    def _wall_rect_rotation_angle_to(self, cursor) -> float:
        """Return Y-up degrees from +x (pivot → cursor).  Falls back to 0°."""
        piv = self._wall_rect_pivot
        if piv is None:
            return 0.0
        return math.degrees(math.atan2(-(cursor.y() - piv.y()),
                                       cursor.x() - piv.x()))

    def _advance_wall_rect_to_rotate_step(self, corner) -> bool:
        """Advance armed wall rect from sizing to rotate step.

        Mirrors ``_advance_rectangle_to_rotate_step``.  Computes the
        axis-aligned pt1/pt2 via ``rect_sizing_points``, rejects extents <0.5,
        stores state, snaps the preview rect, creates ref guides, emits
        instruction.

        Args:
            corner: The second placement point (fully snapped QPointF).

        Returns:
            True when the step advanced, False when refused (no anchor / too-small).
        """
        from .construction_geometry import rect_sizing_points
        anc = self._wall_rect_anchor
        if anc is None:
            return False
        pt1, pt2 = rect_sizing_points(anc, corner, self._wall_rect_from_center)
        if abs(pt2.x() - pt1.x()) < 0.5 or abs(pt2.y() - pt1.y()) < 0.5:
            self._show_status("Wall rectangle too small — skipped", timeout=2000)
            return False
        self._wall_rect_sized_pt1 = pt1
        self._wall_rect_sized_pt2 = pt2
        self._wall_rect_pivot = QPointF(anc)
        self._wall_rect_rotating = True
        # Snap the preview to the sized rect.
        if self._wall_rect_preview is not None:
            self._wall_rect_preview.setRect(QRectF(pt1, pt2).normalized())
        # Clear thickness preview — it no longer applies during rotate step.
        if self._wall_rect_thickness_preview is not None:
            if self._wall_rect_thickness_preview.scene() is self:
                self.removeItem(self._wall_rect_thickness_preview)
            self._wall_rect_thickness_preview = None
        # Create rotation reference guides.
        self._clear_wall_rect_ref_lines()
        self._wall_rect_ref_line0 = self._make_ref_line()
        self._wall_rect_ref_lineA = self._make_ref_line()
        self._update_wall_rect_ref_lines(0.0)
        self.clear_placement_state()
        self.instructionChanged.emit("Pick rotation / type angle")
        return True

    def _commit_wall_rect_rotated(self, angle_deg) -> bool:
        """Commit the sized wall rectangle rotated to ``angle_deg`` about its pivot.

        Uses ``rotated_rect_corners`` to compute the 4 scene-space corners, then
        creates 4 ``WallSegment``s between consecutive corners (same template and
        auto-join loop as the old 2-click commit).  Clears all rect state and
        re-arms continuous placement.

        Args:
            angle_deg: Y-up CCW degrees from +x (the same convention as the
                2D-geo rect ``set_angle``).

        Returns:
            True when 4 walls were committed; False when sizing state is missing.
        """
        from .construction_geometry import rotated_rect_corners
        pt1 = self._wall_rect_sized_pt1
        pt2 = self._wall_rect_sized_pt2
        pivot = self._wall_rect_pivot
        if pt1 is None or pt2 is None or pivot is None:
            return False
        corners = rotated_rect_corners(pt1, pt2, angle_deg, pivot)
        _tmpl = self._get_wall_template()
        _rect_align = _tmpl._alignment
        walls_created = []
        for i in range(4):
            p1 = corners[i]
            p2 = corners[(i + 1) % 4]
            wall = WallSegment(p1, p2,
                               thickness_mm=_tmpl._thickness_mm,
                               color=_tmpl._color.name())
            wall.name = f"Wall {self._next_wall_num}"
            self._next_wall_num += 1
            wall._alignment = _rect_align
            wall._fill_mode = _tmpl._fill_mode
            wall.level = _tmpl.level if _tmpl.level else self.active_level
            wall._base_level = _tmpl._base_level if _tmpl._base_level else self.active_level
            wall._top_level = getattr(_tmpl, "_top_level", "")
            wall._height_mm = getattr(_tmpl, "_height_mm", 3048.0)
            self._wall_alignment = _tmpl._alignment
            self.addItem(wall)
            self._walls.append(wall)
            apply_category_defaults(wall)
            walls_created.append(wall)
        for wall in walls_created:
            self._auto_join_wall(wall)
            wall.setSelected(True)
        for v in self.views():
            v.viewport().update()
        # Clean up preview + ref guides
        if self._wall_rect_preview is not None:
            if self._wall_rect_preview.scene() is self:
                self.removeItem(self._wall_rect_preview)
            self._wall_rect_preview = None
        if self._wall_rect_thickness_preview is not None:
            if self._wall_rect_thickness_preview.scene() is self:
                self.removeItem(self._wall_rect_thickness_preview)
            self._wall_rect_thickness_preview = None
        self._clear_wall_rect_ref_lines()
        # Reset all rect state (re-arm continuous placement)
        _from_centre = self._wall_rect_from_center
        self._wall_rect_anchor = None
        self._wall_rect_rotating = False
        self._wall_rect_sized_pt1 = None
        self._wall_rect_sized_pt2 = None
        self._wall_rect_pivot = None
        self.clear_placement_state()
        self.push_undo_state()
        self.instructionChanged.emit(
            "Pick centre point" if _from_centre else "Pick first corner")
        return True

    # ── Floor placement (unified dispatch — mirrors the wall pattern) ─────────
    def _set_floor_primitive(self, primitive, from_center=False):
        """Apply the floor primitive variant (called by _PLACEMENT_VARIANTS apply_fn).

        Sets ``_floor_primitive`` and, for the rect primitives, also sets
        ``_floor_rect_from_center`` so corner and centre variants are distinct.
        Mirrors ``_set_wall_primitive``.
        """
        self._floor_primitive = primitive
        if primitive == "rect":
            self._floor_rect_from_center = from_center

    def _press_floor_router(self, *args):
        """Dispatch a floor click to the active primitive's builder."""
        if self._floor_primitive == "rect":
            return self._press_floor_rect(*args)
        return self._press_floor(*args)   # polygon

    def _move_floor_router(self, *args):
        """Dispatch a floor mouse-move to the active primitive's preview builder."""
        if self._floor_primitive == "rect":
            return self._move_floor_rect(*args)
        return self._move_floor(*args)    # polygon

    def _apply_floor_dynamic_input(self, geometry) -> bool:
        """Commit a typed floor placement via the same builders the mouse uses.

        Rect: sizing step advances to the rotate step; rotate step commits the
        4 rotated corners.  Polygon: routes the resolved point through the
        vertex press handler.  Mirrors ``_apply_wall_dynamic_input``.
        """
        if self._floor_primitive == "rect":
            if self._floor_rect_rotating:
                return self._commit_floor_rect_rotated(geometry["angle_deg"])
            return self._advance_floor_rect_to_rotate_step(geometry)
        else:
            self._press_floor(None, geometry, geometry, None, None, None)
        return True

    def _floor_base_name(self) -> str:
        """Base name for a placed floor: the user-authored template name or "Floor".

        The template name defaults to the literal ``"(Template)"`` (set in
        ``_get_floor_template``); that placeholder and a blank name both fall
        back to ``"Floor"``.  A user-authored name is used verbatim (trimmed).
        """
        tmpl = self._get_floor_template()
        nm = (getattr(tmpl, "name", "") or "").strip()
        return nm if (nm and nm != "(Template)") else "Floor"

    def _unique_floor_name(self, base: str) -> str:
        """Return *base* uniquified against existing floor names.

        If *base* is unused among ``self._floor_slabs`` it is returned as-is;
        otherwise the smallest ``f"{base} {N}"`` with N >= 1 that is free
        (so a "Slab" collision yields "Slab 1", "Slab 2", ...).
        The caller must name the slab BEFORE appending it (or the new slab must
        not yet be in ``_floor_slabs``) so it does not collide with itself.
        """
        existing = {s.name for s in self._floor_slabs if s is not None}
        if base not in existing:
            return base
        n = 1
        while f"{base} {n}" in existing:
            n += 1
        return f"{base} {n}"

    def _apply_floor_template_fields(self, slab) -> None:
        """Copy the floor template's model fields onto a freshly-built slab.

        Applies the two-boundary elevation model (top/bottom mode/level/offset/
        abs-z) and thickness so a placed slab inherits the template the user
        edited pre-placement — the parity gap the old thickness-only copy left
        open. The owning ``.level`` is deliberately NOT copied (retired for
        floor geometry; see note below).
        """
        tmpl = self._get_floor_template()
        slab._thickness_mm = tmpl._thickness_mm
        slab._top_mode = tmpl._top_mode
        slab._top_level = tmpl._top_level if tmpl._top_level else self.active_level
        slab._top_offset_mm = tmpl._top_offset_mm
        slab._top_abs_z_mm = tmpl._top_abs_z_mm
        slab._bottom_mode = tmpl._bottom_mode
        slab._bottom_level = tmpl._bottom_level if tmpl._bottom_level else self.active_level
        slab._bottom_offset_mm = tmpl._bottom_offset_mm
        slab._bottom_abs_z_mm = tmpl._bottom_abs_z_mm
        # NOTE: no owning `.level` write — a floor's `.level` is retired for
        # geometry (visibility is pure z-range) and is NOT serialized, so it
        # would silently revert to the mixin default on reload/undo. The two
        # boundary refs above (_top_level/_bottom_level) carry the elevation.

    # ── Floor polygon (click-vertex) ──────────────────────────────────────────
    def _press_floor(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._floor_active is None:
            _ftmpl = self._get_floor_template()
            slab = FloorSlab(color=_ftmpl._color.name())
            # Name from the template (uniquified) BEFORE appending to _floor_slabs
            # so the new slab is not counted against itself.
            slab.name = self._unique_floor_name(self._floor_base_name())
            self._apply_floor_template_fields(slab)
            slab.add_point(snapped)
            self.addItem(slab)
            self._floor_slabs.append(slab)
            self._floor_active = slab
            self.update_preview_node(snapped)
            self.instructionChanged.emit(
                "Pick next boundary point (click near first / Enter / double-click to close, Del pops)")
        else:
            pts = self._floor_active._points
            # Close-near-first: ≥3 points and click within snap tolerance of first vertex.
            if len(pts) >= 3:
                scale = self._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                d0 = math.hypot(snapped.x() - pts[0].x(), snapped.y() - pts[0].y())
                if d0 <= tol:
                    self._floor_active.close_polygon()
                    apply_category_defaults(self._floor_active)
                    self._floor_active.setSelected(True)
                    self._floor_active = None
                    self.preview_pipe.hide()
                    for v in self.views(): v.viewport().update()
                    self.push_undo_state()
                    self.instructionChanged.emit("Pick first boundary point (←/→ to change)")
                    return
            self._floor_active.add_point(snapped)

    # ── Floor rectangle (3-step: anchor → size → rotate) ──────────────────────
    def _press_floor_rect(self, event, pos, snapped, item_under, node_under, pipe_under):
        """3-step floor-rectangle placement, mirroring ``_press_wall_rect``.

        Step 1 (no anchor): store anchor, create dashed preview.
        Step 2 (anchor set, not rotating): advance to rotate step.
        Step 3 (rotating): commit ONE 4-corner FloorSlab at the rotation angle.
        """
        if self._floor_rect_rotating:
            # Third click: commit at the pivot→cursor heading.
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._floor_rect_pivot is not None):
                snapped = self._constrain_angle(self._floor_rect_pivot, snapped)
            self._commit_floor_rect_rotated(
                self._floor_rect_rotation_angle_to(snapped))
        elif self._floor_rect_anchor is None:
            # First click: store anchor, show dashed preview rect.
            self._floor_rect_anchor = snapped
            self.update_preview_node(snapped)
            _instr = ("Pick corner (from centre)" if self._floor_rect_from_center
                      else "Pick opposite corner for rectangular floor")
            self.instructionChanged.emit(_instr)
            _ftmpl = self._get_floor_template()
            _fc = QColor(_ftmpl._color)
            pen = QPen(_fc, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            preview.setPen(pen)
            _fc.setAlpha(30)
            preview.setBrush(QBrush(_fc))
            preview.setZValue(200)
            self.addItem(preview)
            self._floor_rect_preview = preview
        else:
            # Second click: size the axis-aligned rect and enter rotate step.
            self._advance_floor_rect_to_rotate_step(snapped)

    def _floor_rect_rotation_angle_to(self, cursor) -> float:
        """Return Y-up degrees from +x (pivot → cursor).  Falls back to 0°."""
        piv = self._floor_rect_pivot
        if piv is None:
            return 0.0
        return math.degrees(math.atan2(-(cursor.y() - piv.y()),
                                       cursor.x() - piv.x()))

    def _advance_floor_rect_to_rotate_step(self, corner) -> bool:
        """Advance the armed floor rect from sizing to rotate step.

        Mirrors ``_advance_wall_rect_to_rotate_step``.  Computes the axis-aligned
        pt1/pt2 via ``rect_sizing_points``, rejects extents <0.5, stores state,
        snaps the preview rect, creates ref guides, emits instruction.
        """
        from .construction_geometry import rect_sizing_points
        anc = self._floor_rect_anchor
        if anc is None:
            return False
        pt1, pt2 = rect_sizing_points(anc, corner, self._floor_rect_from_center)
        if abs(pt2.x() - pt1.x()) < 0.5 or abs(pt2.y() - pt1.y()) < 0.5:
            self._show_status("Floor rectangle too small — skipped", timeout=2000)
            return False
        self._floor_rect_sized_pt1 = pt1
        self._floor_rect_sized_pt2 = pt2
        self._floor_rect_pivot = QPointF(anc)
        self._floor_rect_rotating = True
        if self._floor_rect_preview is not None:
            self._floor_rect_preview.setRect(QRectF(pt1, pt2).normalized())
        self._clear_floor_rect_ref_lines()
        self._floor_rect_ref_line0 = self._make_ref_line()
        self._floor_rect_ref_lineA = self._make_ref_line()
        self._update_floor_rect_ref_lines(0.0)
        self.clear_placement_state()
        self.instructionChanged.emit("Pick rotation / type angle")
        return True

    def _commit_floor_rect_rotated(self, angle_deg) -> bool:
        """Commit the sized floor rectangle rotated to ``angle_deg`` about its pivot.

        Uses ``rotated_rect_corners`` to compute the 4 scene-space corners, then
        builds ONE ``FloorSlab`` from them (mirrors ``_commit_wall_rect_rotated``,
        which builds 4 walls — a floor is a single closed polygon).  Clears all
        rect state and re-arms continuous placement.
        """
        from .construction_geometry import rotated_rect_corners
        pt1 = self._floor_rect_sized_pt1
        pt2 = self._floor_rect_sized_pt2
        pivot = self._floor_rect_pivot
        if pt1 is None or pt2 is None or pivot is None:
            return False
        corners = rotated_rect_corners(pt1, pt2, angle_deg, pivot)
        _ftmpl = self._get_floor_template()
        slab = FloorSlab(points=list(corners), color=_ftmpl._color.name())
        # Name from the template (uniquified) BEFORE appending to _floor_slabs.
        slab.name = self._unique_floor_name(self._floor_base_name())
        self._apply_floor_template_fields(slab)
        self.addItem(slab)
        self._floor_slabs.append(slab)
        apply_category_defaults(slab)
        slab.setSelected(True)
        for v in self.views():
            v.viewport().update()
        # Clean up preview + ref guides.
        if self._floor_rect_preview is not None:
            if self._floor_rect_preview.scene() is self:
                self.removeItem(self._floor_rect_preview)
            self._floor_rect_preview = None
        self._clear_floor_rect_ref_lines()
        # Reset all rect state (re-arm continuous placement).
        _from_centre = self._floor_rect_from_center
        self._floor_rect_anchor = None
        self._floor_rect_rotating = False
        self._floor_rect_sized_pt1 = None
        self._floor_rect_sized_pt2 = None
        self._floor_rect_pivot = None
        self.clear_placement_state()
        self.push_undo_state()
        self.instructionChanged.emit(
            "Pick centre point" if _from_centre else "Pick first corner")
        return True

    def _clear_floor_rect_ref_lines(self) -> None:
        """Remove floor-rect rotate-step reference guides from the scene."""
        for attr in ("_floor_rect_ref_line0", "_floor_rect_ref_lineA"):
            line = getattr(self, attr, None)
            if line is not None:
                if line.scene() is self:
                    self.removeItem(line)
                setattr(self, attr, None)

    def _update_floor_rect_ref_lines(self, angle_deg) -> None:
        """Point the two floor-rect rotate-step guides from the pivot.

        Mirrors ``_update_wall_rect_ref_lines``: a 0° datum + the live sweep line
        at ``angle_deg``, both diagonal-length so they frame the sized rectangle.
        A no-op until both guides and the sized rect exist.
        """
        piv = self._floor_rect_pivot
        if (piv is None or self._floor_rect_ref_line0 is None
                or self._floor_rect_ref_lineA is None
                or self._floor_rect_sized_pt1 is None
                or self._floor_rect_sized_pt2 is None):
            return
        p1, p2 = self._floor_rect_sized_pt1, self._floor_rect_sized_pt2
        length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        rad = math.radians(angle_deg)
        self._floor_rect_ref_line0.setLine(piv.x(), piv.y(),
                                           piv.x() + length, piv.y())
        self._floor_rect_ref_lineA.setLine(
            piv.x(), piv.y(),
            piv.x() + length * math.cos(rad),
            piv.y() - length * math.sin(rad))   # Y-up: subtract sin

    # ── Detail view placement ──────────────────────────────────────────

    def _press_detail(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._detail_rect_anchor is None:
            self._detail_rect_anchor = snapped
            self.instructionChanged.emit("Pick opposite corner for detail view boundary")
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            pen = QPen(QColor("#4488cc"), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview.setPen(pen)
            fill = QColor("#4488cc")
            fill.setAlpha(20)
            preview.setBrush(QBrush(fill))
            preview.setZValue(200)
            self.addItem(preview)
            self._detail_rect_preview = preview
        else:
            rect = QRectF(self._detail_rect_anchor, snapped).normalized()
            # Clean up preview
            if self._detail_rect_preview is not None:
                self.removeItem(self._detail_rect_preview)
                self._detail_rect_preview = None
            self._detail_rect_anchor = None

            # Create detail via manager
            if self._detail_manager is not None:
                name = self._detail_manager.next_name()
                self._detail_manager.create_detail(
                    name, rect, self.active_level)
                self._detail_manager.open_detail(name)
                # Notify project browser
                if hasattr(self, "_on_detail_created"):
                    self._on_detail_created()

            self.push_undo_state()
            self.set_mode("select")

    def _move_detail(self, event, snapped):
        sm = self.scale_manager
        if self._detail_rect_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._detail_rect_anchor is not None and self._detail_rect_preview is not None:
            rect = QRectF(self._detail_rect_anchor, snapped).normalized()
            self._detail_rect_preview.setRect(rect)
            self._draw_dim_hint = (
                f"W: {sm.scene_to_display(rect.width())}  "
                f"H: {sm.scene_to_display(rect.height())}"
            )

    # ── Roof placement ────────────────────────────────────────────────

    def _press_roof(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._roof_active is None:
            _rtmpl = self._get_roof_template()
            roof = RoofItem(color=_rtmpl._color.name())
            roof.name = f"Roof {self._next_roof_num}"
            self._next_roof_num += 1
            roof._thickness_mm = _rtmpl._thickness_mm
            roof._roof_type = _rtmpl._roof_type
            roof._pitch_deg = _rtmpl._pitch_deg
            roof._eave_height_mm = _rtmpl._eave_height_mm
            roof._overhang_mm = _rtmpl._overhang_mm
            roof.level = _rtmpl.level if _rtmpl.level else self.active_level
            roof.add_point(snapped)
            self.addItem(roof)
            self._roofs.append(roof)
            self._roof_active = roof
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick next point (click near first or Enter to close)")
        else:
            pts = self._roof_active._points
            if len(pts) >= 3:
                scale = self._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                d0 = math.hypot(snapped.x() - pts[0].x(), snapped.y() - pts[0].y())
                if d0 <= tol:
                    self._roof_active.close_polygon()
                    self.preview_pipe.hide()

                    # Show roof-properties dialog
                    roof = self._roof_active
                    self._roof_active = None
                    roof._scale_manager_ref = self.scale_manager
                    dlg = RoofDialog(
                        self.views()[0] if self.views() else None,
                        defaults={
                            "name":            roof.name,
                            "roof_type":       roof._roof_type,
                            "pitch_deg":       roof._pitch_deg,
                            "eave_height_mm":  roof._eave_height_mm,
                            "level":           roof.level,
                            "overhang_mm":     roof._overhang_mm,
                            "color":           roof._color.name(),
                            "ridge_direction": roof._ridge_direction,
                            "half_span_mm":    roof.half_span_mm(),
                        },
                        level_manager=self._level_manager,
                        scale_manager=self.scale_manager,
                    )
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        p = dlg.get_params()
                        roof.name            = p["name"] or roof.name
                        roof._roof_type      = p["roof_type"]
                        roof._pitch_deg      = p["pitch_deg"]
                        roof._eave_height_mm = p["eave_height_mm"]
                        roof._overhang_mm    = p["overhang_mm"]
                        roof._ridge_direction = p.get("ridge_direction", "auto")
                        roof._color          = QColor(p["color"])
                        if p.get("eave_level"):
                            roof.level = p["eave_level"]
                        roof._rebuild_path()
                        roof.update()
                        apply_category_defaults(roof)
                    else:
                        # User cancelled — remove the roof
                        self.removeItem(roof)
                        self._roofs.remove(roof)

                    roof.setSelected(True)
                    for v in self.views(): v.viewport().update()
                    self.push_undo_state()
                    self.instructionChanged.emit("Pick first boundary point (click near first to close)")
                    return
            if len(pts) >= 2:
                scale = self._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                for vi in range(len(pts)):
                    dv = math.hypot(snapped.x() - pts[vi].x(), snapped.y() - pts[vi].y())
                    if dv <= tol:
                        pts.pop(vi)
                        self._roof_active._rebuild_path()
                        for v in self.views(): v.viewport().update()
                        return
            self._roof_active.add_point(snapped)

    def _press_roof_rect(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._roof_rect_anchor is None:
            self._roof_rect_anchor = snapped
            self.instructionChanged.emit("Pick opposite corner for rectangular roof")
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            _rtmpl = self._get_roof_template()
            _rc = QColor(_rtmpl._color)
            pen = QPen(_rc, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview.setPen(pen)
            _rc.setAlpha(30)
            preview.setBrush(QBrush(_rc))
            preview.setZValue(200)
            self.addItem(preview)
            self._roof_rect_preview = preview
        else:
            rect = QRectF(self._roof_rect_anchor, snapped).normalized()
            corners = [
                QPointF(rect.x(), rect.y()),
                QPointF(rect.x() + rect.width(), rect.y()),
                QPointF(rect.x() + rect.width(), rect.y() + rect.height()),
                QPointF(rect.x(), rect.y() + rect.height()),
            ]
            _rtmpl = self._get_roof_template()
            roof = RoofItem(points=corners, color=_rtmpl._color.name())
            roof.name = f"Roof {self._next_roof_num}"
            self._next_roof_num += 1
            roof._thickness_mm = _rtmpl._thickness_mm
            roof._roof_type = _rtmpl._roof_type
            roof._pitch_deg = _rtmpl._pitch_deg
            roof._eave_height_mm = _rtmpl._eave_height_mm
            roof._overhang_mm = _rtmpl._overhang_mm
            roof.level = _rtmpl.level if _rtmpl.level else self.active_level
            self.addItem(roof)
            self._roofs.append(roof)

            # Clean up preview
            if self._roof_rect_preview is not None:
                self.removeItem(self._roof_rect_preview)
                self._roof_rect_preview = None
            self._roof_rect_anchor = None

            # Show roof-properties dialog
            dlg = RoofDialog(
                self.views()[0] if self.views() else None,
                defaults={
                    "name":           roof.name,
                    "roof_type":      roof._roof_type,
                    "pitch_deg":      roof._pitch_deg,
                    "eave_height_mm": roof._eave_height_mm,
                    "level":          roof.level,
                    "overhang_mm":    roof._overhang_mm,
                    "color":          roof._color.name(),
                },
                level_manager=self._level_manager,
                scale_manager=self.scale_manager,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                p = dlg.get_params()
                roof.name           = p["name"] or roof.name
                roof._roof_type     = p["roof_type"]
                roof._pitch_deg     = p["pitch_deg"]
                roof._eave_height_mm = p["eave_height_mm"]
                roof._overhang_mm   = p["overhang_mm"]
                roof._color         = QColor(p["color"])
                if p.get("eave_level"):
                    roof.level = p["eave_level"]
                roof._rebuild_path()
                roof.update()
                apply_category_defaults(roof)
            else:
                # User cancelled — remove the roof
                self.removeItem(roof)
                self._roofs.remove(roof)

            roof.setSelected(True)
            for v in self.views(): v.viewport().update()
            self.push_undo_state()
            self.instructionChanged.emit("Pick first corner for rectangular roof")

    # ── Door placement ────────────────────────────────────────────────
    def _press_opening(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Commit-click for the unified opening placement mode (§7.6).

        Requires a wall under the cursor: empty-space clicks are rejected with a
        status prompt (§7.10).  The placed opening inherits the pre-commit cycle
        state (alignment / hinge / facing) currently armed on the scene.
        """
        wall = self._find_wall_at(snapped)
        if wall is None:
            self._show_status("Click on a wall to place an opening", timeout=2000)
            self.instructionChanged.emit("Click on a wall to place an opening")
            return
        # The placement TEMPLATE (a WallOpening) is the single source of truth
        # for feature + size + sill; the scene mirrors below carry only the
        # live cycle state (alignment / hinge / facing) which is kept synced
        # onto the template by the cycle keys.
        tmpl = getattr(self, "current_template", None)
        if isinstance(tmpl, WallOpening):
            op = WallOpening(
                wall=wall, feature_id=tmpl.feature_id,
                offset_along=self._offset_along_wall(wall, snapped),
                width_mm=tmpl.width_mm, height_mm=tmpl.height_mm,
                sill_mm=tmpl.sill_mm,
            )
            op.alignment = tmpl.alignment
            op.mirror_hinge = tmpl.mirror_hinge
            op.mirror_facing = tmpl.mirror_facing
        else:
            op = WallOpening(wall=wall, feature_id=self._opening_feature_id,
                             offset_along=self._offset_along_wall(wall, snapped))
            op.alignment = self._opening_alignment
            op.mirror_hinge = self._opening_mirror_hinge
            op.mirror_facing = self._opening_mirror_facing
        op.level = wall.level
        op._reposition()
        wall.openings.append(op)
        self.addItem(op)
        self.push_undo_state()
        self.instructionChanged.emit("Click on a wall to place an opening")

    def _press_door(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Legacy door dispatch — retarget onto the unified opening path so the
        pre-Task-7 ribbon buttons keep working (§7.6)."""
        self._opening_feature_id = DEFAULT_FEATURE_FOR_TYPE["door"]
        self._press_opening(event, pos, snapped, item_under, node_under, pipe_under)

    # ── Window placement (legacy shim) ────────────────────────────────
    def _press_window(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Legacy window dispatch — retarget onto the unified opening path."""
        self._opening_feature_id = DEFAULT_FEATURE_FOR_TYPE["window"]
        self._press_opening(event, pos, snapped, item_under, node_under, pipe_under)

    # ── Opening live preview (§7.6) ───────────────────────────────────
    def _move_opening(self, event, snapped):
        """Redraw the live opening ghost on the hovered wall.

        Hidden (and removed) when the cursor is not over a wall, so the ghost
        never floats in empty space.
        """
        wall = self._find_wall_at(snapped)
        if wall is None:
            self._clear_opening_ghost()
            return
        offset = self._offset_along_wall(wall, snapped)
        ghost = self._opening_ghost
        # Rebuild the ghost from scratch if it is missing or its Feature changed
        # (feature_id is immutable on a WallOpening, so swap on mismatch).
        if ghost is None or ghost.feature_id != self._opening_feature_id:
            self._clear_opening_ghost()
            ghost = WallOpening(feature_id=self._opening_feature_id)
            ghost.setOpacity(0.5)
            ghost.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            ghost._exclude_from_bulk_select = True
            self.addItem(ghost)
            self._opening_ghost = ghost
        ghost.wall = wall
        ghost._offset_along = offset
        tmpl = getattr(self, "current_template", None)
        if isinstance(tmpl, WallOpening):
            ghost.width_mm = tmpl.width_mm
            ghost.height_mm = tmpl.height_mm
            ghost.sill_mm = tmpl.sill_mm
        ghost.alignment = self._opening_alignment
        ghost.mirror_hinge = self._opening_mirror_hinge
        ghost.mirror_facing = self._opening_mirror_facing
        ghost._reposition()

    def _refresh_opening_ghost(self):
        """Re-apply the current cycle state to the live ghost (post-cycle)."""
        ghost = self._opening_ghost
        if ghost is None:
            return
        ghost.alignment = self._opening_alignment
        ghost.mirror_hinge = self._opening_mirror_hinge
        ghost.mirror_facing = self._opening_mirror_facing
        ghost._reposition()
        for v in self.views():
            v.viewport().update()

    def _clear_opening_ghost(self):
        """Remove the live opening ghost if present."""
        ghost = getattr(self, "_opening_ghost", None)
        if ghost is not None:
            if ghost.scene() is self:
                self.removeItem(ghost)
            self._opening_ghost = None

    # ── Shift-click floor vertex editing (select mode) ────────────────
    def _press_select_shift_floor(self, event, pos, snapped, item_under, node_under, pipe_under):
        """Handle shift-click vertex editing on FloorSlabs. Returns True if consumed."""
        # Find FloorSlab under cursor
        for it in self.items(snapped):
            if isinstance(it, FloorSlab) and len(it._points) >= 3:
                scale = self._active_view_scale()
                vtx_tol = 8.0 / max(scale, 1e-6)
                # Check if near an existing vertex → delete it (min 3)
                for vi, vpt in enumerate(it._points):
                    dv = math.hypot(snapped.x() - vpt.x(), snapped.y() - vpt.y())
                    if dv <= vtx_tol:
                        it.remove_point(vi)
                        it.setSelected(True)
                        it.update()
                        for v in self.views(): v.viewport().update()
                        self.push_undo_state()
                        return True
                # Check if near an edge → insert vertex at projection
                edge_idx, edge_dist, proj_pt = it.nearest_edge(snapped)
                edge_tol = 12.0 / max(scale, 1e-6)
                if edge_dist <= edge_tol:
                    it.insert_point(edge_idx + 1, proj_pt)
                    it.setSelected(True)
                    it.update()
                    for v in self.views(): v.viewport().update()
                    self.push_undo_state()
                    return True
                break  # only edit the topmost floor
        return False

    def mouseReleaseEvent(self, event):
        # Inert in input mode (see mouseMoveEvent).  Without this, a drag that
        # was in progress when the HUD engaged would still *finish* here —
        # pushing an undo entry for a gesture the user abandoned by typing —
        # and the drag-vs-click test below would compare a stale
        # ``_last_press_pos`` (its press was swallowed) against a fresh release.
        if self.is_input_mode():
            return
        # ── Selection-manipulator drag release ──────────────────────────
        # Deliver straight to the grabber: bake + commit happen in
        # SelectionManipulator._finish; the marker-deselect logic below is
        # for rubber-band drags and must not run on a manipulator gesture.
        _manip = self._live_manip()
        if (event.button() == Qt.MouseButton.LeftButton
                and _manip is not None and _manip.is_dragging()):
            super().mouseReleaseEvent(event)
            return
        # ── Gridline body drag release ──────────────────────────────────
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_gridline is not None:
            self.push_undo_state()
            self._dragging_gridline = None
            self._gridline_drag_start = None
            self._gridline_drag_original_pos = None
            return
        if event.button() == Qt.MouseButton.LeftButton and self._grip_dragging:
            self._tools._solve_constraints(self._grip_item)  # enforce constraints
            self._grip_dragging = False
            self._grip_item     = None
            self._grip_index    = -1
            # Clear ALIGN active item now that the drag gesture is complete.
            self._align_active_item = None
            self._align_result = None
            self._align_controller.clear()
            self._align_last_move_ns = None
            self._align_anchor_dir = None
            self.push_undo_state()
            for v in self.views():
                v.viewport().update()
            return
        super().mouseReleaseEvent(event)
        # Deselect markers that got caught in a rubber-band drag.
        # Only do this for drag selections — not direct clicks on the marker.
        press = getattr(self, "_last_press_pos", None)
        release = event.scenePos()
        is_drag = (press is not None
                   and (press - release).manhattanLength() > 4.0)
        if is_drag:
            for item in self.selectedItems():
                if getattr(item, "_exclude_from_bulk_select", False):
                    item.setSelected(False)

    def mouseDoubleClickEvent(self, event):
        # Inert in input mode (see mouseMoveEvent).  Presses are swallowed
        # while the HUD is open, so the press/release/double-click chain
        # arrives incomplete; acting on the tail of it would end a pipe or
        # polyline chain the user never finished.
        if self.is_input_mode():
            return
        # ── Pipe: double-click finishes the polyline chain ─────────────
        if (event.button() == Qt.MouseButton.LeftButton
                and self.mode == "pipe"
                and self.node_start_pos is not None):
            # Double-click fires a press first which placed one more pipe.
            # Just end the chain — keep mode active for a new chain.
            self.node_start_pos = None
            self._pipe_node_was_new = False
            self.preview_pipe.hide()
            self.preview_node.hide()
            self.push_undo_state()
            self.instructionChanged.emit("Pick start node")
            event.accept()
            return

        if (event.button() == Qt.MouseButton.LeftButton
                and self.mode == "polyline"
                and self._polyline_active is not None):
            # Qt delivers Press → Release → DblClick → Release, so a double
            # click contributes exactly *one* extra press — the same thing the
            # pipe branch above says.  That press already appended a vertex at
            # the ghost's tip, which the user does not want; drop it so the
            # polyline finishes at the last single-clicked vertex.
            #
            # This popped twice, which also discarded a genuinely placed
            # vertex: the segment under the ghost *and* the last committed
            # segment both disappeared on finish.
            pts = self._polyline_active._points
            if len(pts) > 2:
                pts.pop()
            if len(pts) >= 2:
                pl = self._polyline_active
                pl.finalize()
                self._polyline_active = None
                self._hide_polyline_close_indicator()
                pl.setSelected(True)
                for v in self.views(): v.viewport().update()
                self.push_undo_state()
                self.instructionChanged.emit("Pick first point")
            event.accept()
            return

        # ── Floor: double-click closes the polygon ───────────────────────
        if (event.button() == Qt.MouseButton.LeftButton
                and self.mode == "floor"
                and self._floor_active is not None):
            pts = self._floor_active._points
            # Double-click adds an extra point via mousePressEvent — remove it
            if len(pts) > 3:
                pts.pop()
            if len(pts) >= 3:
                self._floor_active.close_polygon()
                apply_category_defaults(self._floor_active)
                self._floor_active.setSelected(True)
                self._floor_active = None
                for v in self.views(): v.viewport().update()
                self.push_undo_state()
                self.instructionChanged.emit("Pick first boundary point (double-click to close)")
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu on right-click for underlays or scene entities."""
        # Right-click confirms design area selection
        if self.mode == "design_area":
            da = self._da_editing or self.active_design_area
            if da and da.sprinklers:
                self.active_design_area = da
                self._da_editing = None      # next pick starts a NEW area
                self._da_change_committed(da, confirmed=True)
            # Stay in design_area mode so more areas can be defined;
            # Esc or a tool switch leaves the mode.
            event.accept()
            return
        hit_items = self.items(event.scenePos())

        # 1. Check underlays first
        for item in hit_items:
            candidate = item
            while candidate is not None:
                result = self.find_underlay_for_item(candidate)
                if result is not None:
                    data, scene_item = result
                    UnderlayContextMenu.show(
                        self, data, scene_item,
                        event.screenPos()
                    )
                    return
                candidate = candidate.parentItem()

        # 2. Check for scene entities
        target = self._find_entity_at(event.scenePos())
        if target is not None:
            # If target is not selected, select it alone
            if not target.isSelected():
                self.clearSelection()
                target.setSelected(True)
            self._show_entity_context_menu(target, event.screenPos())
            return

        super().contextMenuEvent(event)

    # ── Entity context menu helpers ────────────────────────────────────────

    def _find_entity_at(self, pos):
        """Find the first selectable scene entity at the given position."""
        ENTITY_TYPES = (
            Node, Pipe, DimensionAnnotation, NoteAnnotation,
            PolylineItem, LineItem, RectangleItem,
            CircleItem, ArcItem, RegularPolygonItem, GridlineItem, WaterSupply,
            WallSegment, FloorSlab, DoorOpening, WindowOpening, Room,
        )
        for item in self.items(pos):
            # Sprinklers are children of Nodes — resolve to parent
            if isinstance(item, Sprinkler):
                item = item.parentItem()
            if isinstance(item, ENTITY_TYPES):
                return item
            # DetailMarker (avoid import — check by class name)
            if type(item).__name__ == "DetailMarker":
                return item
        return None

    def _show_entity_context_menu(self, target, screen_pos):
        """Build and show the right-click context menu for scene entities."""
        from .entity_context_menu import build_entity_context_menu
        from .room import Room

        selected = self.selectedItems()
        menu = build_entity_context_menu(
            selected,
            target,
            scene=self,
            on_copy=self.copy_selected_items,
            on_hide=lambda: self._hide_items(
                [target] + [i for i in selected if i is not target]
            ),
            on_hide_all_type=lambda t=type(target): self._hide_all_of_type(t),
            on_show_all=self._show_all_hidden,
            on_delete=self.delete_selected_items,
            on_properties=lambda: self.requestPropertyUpdate.emit(target),
            on_auto_populate_room=(
                (lambda: self._auto_populate_room_dialog(target))
                if isinstance(target, Room) else None
            ),
            on_array_gridline=(
                (lambda: self._start_gridline_replicate(target, "array"))
                if isinstance(target, GridlineItem) else None
            ),
            on_offset_gridline=(
                (lambda: self._start_gridline_replicate(target, "offset"))
                if isinstance(target, GridlineItem) else None
            ),
        )
        menu.exec(screen_pos)

    def set_sprinkler_db(self, db):
        """Inject the shared SprinklerDatabase (called by MainWindow)."""
        self._sprinkler_db = db

    def _auto_populate_room_dialog(self, room):
        """Open the auto-populate dialog for a room and place sprinklers."""
        from .auto_populate_dialog import AutoPopulateDialog
        from .sprinkler_db import SprinklerDatabase

        db = self._sprinkler_db or SprinklerDatabase()
        dlg = AutoPopulateDialog(
            room, db,
            level_manager=self._level_manager,
            scale_manager=self.scale_manager,
            parent=self.views()[0] if self.views() else None,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            results = dlg.get_results()
            self.auto_populate_room(
                room,
                results["positions"],
                results["record"],
                results["level"],
                results["ceiling_level"],
                results["ceiling_offset"],
                results.get("design_density", "0.10"),
            )

    def _hide_items(self, items):
        """Hide the given items via display overrides (persists through refresh)."""
        for item in items:
            if hasattr(item, "_display_overrides"):
                item._display_overrides["visible"] = False
            # Fitting is not a QGraphicsItem — hide its symbol directly
            if isinstance(item, Fitting):
                if item.symbol is not None:
                    item.symbol.setVisible(False)
            else:
                item.setVisible(False)

    def _show_items(self, items):
        """Show the given items via display overrides."""
        for item in items:
            if hasattr(item, "_display_overrides"):
                item._display_overrides.pop("visible", None)
            # Fitting is not a QGraphicsItem — re-evaluate via update()
            if isinstance(item, Fitting):
                item.update()
            else:
                item.setVisible(True)

    def _show_all_hidden(self):
        """Restore visibility for all manually hidden items."""
        for item in self.items():
            if hasattr(item, "_display_overrides"):
                if item._display_overrides.get("visible") is False:
                    item._display_overrides.pop("visible", None)
                    item.setVisible(True)
        # Also clear fitting overrides (Fitting is not a QGraphicsItem)
        ss = getattr(self, "sprinkler_system", None)
        if ss:
            for node in ss.nodes:
                if node.fitting and node.fitting._display_overrides.get("visible") is False:
                    node.fitting._display_overrides.pop("visible", None)
                    node.fitting.update()
        # Re-apply level filtering so items outside the active view range
        # don't remain visible after being un-hidden.
        if hasattr(self, "_level_manager"):
            self._level_manager.apply_to_scene(self)

    def _hide_all_of_type(self, item_type):
        """Hide all scene items that are instances of *item_type*."""
        for item in self.items():
            if type(item) is item_type:
                if hasattr(item, "_display_overrides"):
                    item._display_overrides["visible"] = False
                item.setVisible(False)

    def _move_selection_to_level(self, target_level: str):
        """Move all selected items to the target level, updating elevations."""
        self.push_undo_state()
        items = list(self.selectedItems())
        moved_nodes = set()
        for item in items:
            if hasattr(item, "level"):
                item.level = target_level
                if isinstance(item, Node):
                    moved_nodes.add(item)
                    item.ceiling_level = target_level
                    item._properties["Ceiling Level"]["value"] = target_level
                    if self._level_manager:
                        lvl = self._level_manager.get(target_level)
                        if lvl:
                            item.z_pos = lvl.elevation + item.ceiling_offset

        # Move pipes whose both endpoints moved
        for item in items:
            if isinstance(item, Pipe):
                if item.node1 in moved_nodes and item.node2 in moved_nodes:
                    item.level = target_level

        if self._level_manager:
            self._level_manager.apply_to_scene(self)
        self.sceneModified.emit()

    def _select_same_level(self, level_name: str):
        """Select all visible entities on the given level."""
        self.clearSelection()
        for item in self._items_on_level(level_name):
            if item.isVisible() and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                item.setSelected(True)

    def _items_on_level(self, level_name: str) -> list:
        """Return all scene items assigned to the given level."""
        result = []
        for node in self.sprinkler_system.nodes:
            if getattr(node, "level", None) == level_name:
                result.append(node)
        for pipe in self.sprinkler_system.pipes:
            if getattr(pipe, "level", None) == level_name:
                result.append(pipe)
        for lst in [self._polylines, self._draw_lines,
                    self._draw_rects, self._draw_circles, self._draw_arcs,
                    self._draw_polygons,
                    self._gridlines,
                    self._walls, self._floor_slabs, self._roofs]:
            for item in lst:
                if getattr(item, "level", None) == level_name:
                    result.append(item)
        ann = getattr(self, "annotations", None)
        if ann:
            for dim in getattr(ann, "dimensions", []):
                if getattr(dim, "level", None) == level_name:
                    result.append(dim)
            for note in getattr(ann, "notes", []):
                if getattr(note, "level", None) == level_name:
                    result.append(note)
        ws = getattr(self, "water_supply_node", None)
        if ws is not None and getattr(ws, "level", None) == level_name:
            result.append(ws)
        return result

    # ── Wall / Floor helpers ─────────────────────────────────────────────

    def _recalc_name_counters(self):
        """Recalculate auto-name counters from existing entity names."""
        wall_nums = []
        for w in self._walls:
            if w.name.startswith("Wall "):
                try:
                    wall_nums.append(int(w.name.split(" ", 1)[1]))
                except (ValueError, IndexError):
                    pass
        self._next_wall_num = (max(wall_nums) + 1) if wall_nums else 1

        floor_nums = []
        for fs in self._floor_slabs:
            if fs.name.startswith("Floor "):
                try:
                    floor_nums.append(int(fs.name.split(" ", 1)[1]))
                except (ValueError, IndexError):
                    pass
        self._next_floor_num = (max(floor_nums) + 1) if floor_nums else 1

        roof_nums = []
        for r in self._roofs:
            if r.name.startswith("Roof "):
                try:
                    roof_nums.append(int(r.name.split(" ", 1)[1]))
                except (ValueError, IndexError):
                    pass
        self._next_roof_num = (max(roof_nums) + 1) if roof_nums else 1

    def _auto_join_wall(self, wall: WallSegment,
                        tolerance: float = AUTO_JOIN_TOLERANCE):
        """Snap wall endpoints to nearby existing wall endpoints (miter join)
        and to mid-wall faces (tee join)."""

        # Track which endpoints have already been snapped (0=pt1, 1=pt2)
        snapped = set()

        # Pass 1: endpoint-to-endpoint (miter / corner join)
        for other in self._walls:
            if other is wall:
                continue
            for my_idx in (0, 1):
                if my_idx in snapped:
                    continue
                my_pt = wall.pt1 if my_idx == 0 else wall.pt2
                hit = other.endpoint_near(my_pt, tolerance)
                if hit is not None:
                    target = other.pt1 if hit == 0 else other.pt2
                    wall.snap_endpoint_to(my_idx, target)
                    snapped.add(my_idx)
                    # Rebuild connected wall so its miter updates too
                    other._rebuild_path()
                    other.update()

        # Pass 2: tee join — snap unsnapped endpoints onto the host
        # wall's CENTERLINE (the point the user picked stays put; the
        # drawn body is coped back to the host face at render time by
        # WallSegment._tee_cope_corners).  The old face snap made the
        # picked point visibly "jump" off the centerline.
        for other in self._walls:
            if other is wall:
                continue
            for my_idx in (0, 1):
                if my_idx in snapped:
                    continue
                my_pt = wall.pt1 if my_idx == 0 else wall.pt2
                cl_pt = other.nearest_centerline_point(my_pt, TEE_TOLERANCE)
                if cl_pt is not None:
                    wall.snap_endpoint_to(my_idx, cl_pt)
                    snapped.add(my_idx)

    def _find_wall_at(self, pos: QPointF) -> "WallSegment | None":
        """Return the first wall whose shape contains pos."""
        for wall in self._walls:
            if wall.shape().contains(pos):
                return wall
        return None

    def _offset_along_wall(self, wall: WallSegment, pos: QPointF) -> float:
        """Project pos onto the wall centerline and return distance from pt1."""
        a = wall.centerline_angle_rad()
        dx = pos.x() - wall.pt1.x()
        dy = pos.y() - wall.pt1.y()
        return dx * math.cos(a) + dy * math.sin(a)

    def copy_items_to_level(self, items: list, target_level: str):
        """Duplicate items and assign copies to target_level."""
        if not items:
            return
        self.push_undo_state()

        # Serialize selected items via copy mechanism
        old_selection = list(self.selectedItems())
        self.clearSelection()
        for item in items:
            if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                item.setSelected(True)

        old_clip = QApplication.clipboard().text()
        self.copy_selected_items()

        # Temporarily set active level so paste assigns the target level
        saved_level = self.active_level
        self.active_level = target_level
        self.paste_items(QPointF(0, 0))
        self.active_level = saved_level

        QApplication.clipboard().setText(old_clip)

        # Restore original selection
        self.clearSelection()
        for item in old_selection:
            if item.scene() == self:
                item.setSelected(True)

        if self._level_manager:
            self._level_manager.apply_to_scene(self)
        self.sceneModified.emit()

    def duplicate_level_entities(self, source_level: str, target_level: str):
        """Copy all entities on source_level to target_level."""
        items = self._items_on_level(source_level)
        if items:
            self.copy_items_to_level(items, target_level)

    # -------------------------------------------------------------------------
    # KEY EVENTS

    def keyPressEvent(self, event):
        # Left-Shift tap tracking: a clean left-Shift press arms the cycle;
        # any other key breaks it, so Shift held as a modifier never cycles.
        # Autorepeat (a held key) is neither an arm nor a break.
        if not event.isAutoRepeat():
            self._lshift_tap_armed = self._is_left_shift(event)
        # ←/→ cycle the placement variant at step 0 (arc, rectangle, …).
        # Consume only when a variant actually cycles; otherwise fall through
        # so the view's default arrow-scroll still works.
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            direction = -1 if event.key() == Qt.Key.Key_Left else +1
            if self.cycle_placement_variant(direction):
                event.accept()
                return
            # else fall through to default view scroll
        # ── Polygon placement cycle keys ─────────────────────────────────────
        if self.mode == "polygon" and not self.is_input_mode():
            if event.key() == Qt.Key.Key_Up:
                self._cycle_polygon_sides(+1); event.accept(); return
            if event.key() == Qt.Key.Key_Down:
                self._cycle_polygon_sides(-1); event.accept(); return
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                self._toggle_polygon_inscribed(); event.accept(); return
        # ── Wall placement: Spacebar cycles alignment ─────────────────────────
        if (event.key() == Qt.Key.Key_Space
                and self.mode == "wall"
                and not self.is_input_mode()):
            self._cycle_wall_alignment()
            event.accept()
            return
        # ── Opening placement cycle keys (§7.6) ──────────────────────────────
        # Spacebar cycles alignment; ←/→ toggle the hinge mirror; ↑/↓ toggle the
        # facing mirror.  All gated on not-input-mode so a focused HUD field
        # keeps these keys for typing.
        if self.mode == "opening" and not self.is_input_mode():
            if event.key() == Qt.Key.Key_Space:
                self.cycle_placement_ambiguity()
                event.accept()
                return
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                self._opening_mirror_hinge = not self._opening_mirror_hinge
                self._sync_opening_state_to_template()
                self._refresh_opening_ghost()
                event.accept()
                return
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._opening_mirror_facing = not self._opening_mirror_facing
                self._sync_opening_state_to_template()
                self._refresh_opening_ghost()
                event.accept()
                return
        # Esc mid-manipulator-drag cancels the gesture (restore pre-drag
        # state, no commit) before any other Escape handling runs.
        if event.key() == Qt.Key.Key_Escape:
            _manip = self._live_manip()
            if _manip is not None and _manip.is_dragging():
                _manip.cancel_drag()
                event.accept()
                return
        # Radiation selection flow — intercept Enter/Escape first
        if self._radiation_selecting:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.radiationConfirm.emit()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._radiation_selecting = False
                self.radiationCancel.emit()
                return
        if event.key() == Qt.Key.Key_Escape:
            # Gridline replicate: Esc cancels without committing
            if self.mode in ("gridline_array", "gridline_offset"):
                self._end_gridline_replicate()
                return
            # Pipe polyline: first Escape ends the chain, second exits mode
            if self.mode == "pipe" and self.node_start_pos is not None:
                self.node_start_pos = None
                self._pipe_node_was_new = False
                self.preview_pipe.hide()
                self.preview_node.hide()
                self.instructionChanged.emit("Pick start node")
                return
            # Align: first Escape clears reference, second exits mode
            if self.mode == "align" and self._align_reference is not None:
                self._align_reference = None
                if self._align_highlight is not None:
                    if self._align_highlight.scene() is self:
                        self.removeItem(self._align_highlight)
                    self._align_highlight = None
                if hasattr(self, '_align_ghost') and self._align_ghost is not None:
                    if self._align_ghost.scene() is self:
                        self.removeItem(self._align_ghost)
                    self._align_ghost = None
                self._show_status("Click reference edge")
                return
            if self.mode and self.mode not in (None, "select"):
                self._show_status("Mode cancelled", 2000)
            self.set_mode(None)
        elif event.key() == Qt.Key.Key_Delete:
            if not self._delete_or_pop_polyline_vertex():
                self.delete_selected_items()
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+A is handled by QShortcut → Model_View._select_all_items()
            # This fallback is kept for completeness.
            self.blockSignals(True)
            for item in self.items():
                if isinstance(item, GridlineItem):
                    continue
                if getattr(item, "_exclude_from_bulk_select", False):
                    continue
                if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                    item.setSelected(True)
            self.blockSignals(False)
            self.selectionChanged.emit()
            for v in self.views():
                v.viewport().update()
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
        elif event.key() == Qt.Key.Key_Y and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.redo()
        elif (event.key() == Qt.Key.Key_Z
              and event.modifiers() == (Qt.KeyboardModifier.ControlModifier
                                        | Qt.KeyboardModifier.ShiftModifier)):
            self.redo()
        elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selected_items()
        elif event.key() == Qt.Key.Key_M and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.selectedItems():
                self._selected_items = self.selectedItems()
                self.set_mode("move")
        elif event.key() == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.duplicate_selected()
        elif event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.clipboard_data():
                self.set_mode("paste")
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Commit gridline replicate on Enter
            if self.mode in ("gridline_array", "gridline_offset"):
                self._commit_gridline_replicate()
                return
            # Commit offset on Enter (same logic as click)
            if self.mode == "offset_side" and self._offset_source is not None and self._offset_dist > 0:
                cursor_pos = self._last_scene_pos
                if cursor_pos is not None:
                    sd = self._tools._offset_signed_dist(self._offset_source, self._offset_dist, cursor_pos)
                    self._tools._clear_offset_preview()
                    new_item = self._tools._make_offset_item(self._offset_source, sd)
                    if new_item is not None:
                        if isinstance(new_item, LineItem):
                            self.addItem(new_item)
                            self._draw_lines.append(new_item)
                        elif isinstance(new_item, PolylineItem):
                            self.addItem(new_item)
                            self._polylines.append(new_item)
                        elif isinstance(new_item, CircleItem):
                            self.addItem(new_item)
                            self._draw_circles.append(new_item)
                        elif isinstance(new_item, RectangleItem):
                            self.addItem(new_item)
                            self._draw_rects.append(new_item)
                        elif isinstance(new_item, ArcItem):
                            self.addItem(new_item)
                            self._draw_arcs.append(new_item)
                        self.push_undo_state()
                    self._offset_source = None
                    if self._offset_highlight is not None:
                        if self._offset_highlight.scene() is self:
                            self.removeItem(self._offset_highlight)
                        self._offset_highlight = None
                    self.set_mode("offset")
                return
            # Finish an in-progress polyline
            if self.mode == "polyline" and self._polyline_active is not None:
                if len(self._polyline_active._points) >= 2:
                    pl = self._polyline_active
                    pl.finalize()
                    self._polyline_active = None
                    self._hide_polyline_close_indicator()
                    pl.setSelected(True)
                    self.push_undo_state()
                    self.instructionChanged.emit("Pick first point")
                    # Stay in polyline mode so user can draw another
            # Close an in-progress floor slab
            elif self.mode == "floor" and self._floor_active is not None:
                if len(self._floor_active._points) >= 3:
                    self._floor_active.close_polygon()
                    apply_category_defaults(self._floor_active)
                    self._floor_active.setSelected(True)
                    self._floor_active = None
                    for v in self.views(): v.viewport().update()
                    self.push_undo_state()
                    self.instructionChanged.emit("Pick first boundary point (double-click or Enter to close)")
            # Close an in-progress roof polygon
            elif self.mode == "roof" and self._roof_active is not None:
                if len(self._roof_active._points) >= 3:
                    self._roof_active.close_polygon()
                    self.preview_pipe.hide()

                    # Show roof-properties dialog
                    roof = self._roof_active
                    self._roof_active = None
                    roof._scale_manager_ref = self.scale_manager
                    dlg = RoofDialog(
                        self.views()[0] if self.views() else None,
                        defaults={
                            "name":            roof.name,
                            "roof_type":       roof._roof_type,
                            "pitch_deg":       roof._pitch_deg,
                            "eave_height_mm":  roof._eave_height_mm,
                            "level":           roof.level,
                            "overhang_mm":     roof._overhang_mm,
                            "color":           roof._color.name(),
                            "ridge_direction": roof._ridge_direction,
                            "half_span_mm":    roof.half_span_mm(),
                        },
                        level_manager=self._level_manager,
                        scale_manager=self.scale_manager,
                    )
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        p = dlg.get_params()
                        roof.name            = p["name"] or roof.name
                        roof._roof_type      = p["roof_type"]
                        roof._pitch_deg      = p["pitch_deg"]
                        roof._eave_height_mm = p["eave_height_mm"]
                        roof._overhang_mm    = p["overhang_mm"]
                        roof._ridge_direction = p.get("ridge_direction", "auto")
                        roof._color          = QColor(p["color"])
                        if p.get("eave_level"):
                            roof.level = p["eave_level"]
                        roof._rebuild_path()
                        roof.update()
                    else:
                        self.removeItem(roof)
                        self._roofs.remove(roof)

                    roof.setSelected(True)
                    for v in self.views(): v.viewport().update()
                    self.push_undo_state()
                    self.instructionChanged.emit("Pick first boundary point (click near first to close)")
            # Close an in-progress manual room polygon
            elif self.mode == "room_manual" and self._room_manual_active is not None:
                if len(self._room_manual_active._boundary) >= 3:
                    self._room_manual_active._rebuild()
                    self._room_manual_active._update_label()
                    apply_category_defaults(self._room_manual_active)
                    self.clearSelection()
                    self._room_manual_active.setSelected(True)
                    self.requestPropertyUpdate.emit(self._room_manual_active)
                    self._show_status(f"Created {self._room_manual_active.name}", 2000)
                    self._room_manual_active = None
                    self.preview_pipe.hide()
                    for v in self.views(): v.viewport().update()
                    self.push_undo_state()
                    self.instructionChanged.emit("Pick first room boundary point")
            # Commit fillet
            elif self.mode == "fillet" and self._fillet_item1 is not None and self._fillet_item2 is not None:
                data = self._tools._compute_fillet(self._fillet_item1, self._fillet_item2,
                                            self._fillet_radius)
                if data is not None:
                    self._tools._commit_fillet(data)
                    self.push_undo_state()
                else:
                    self._show_status("Cannot compute fillet for these objects", timeout=3000)
                self.set_mode(None)
                return
            # Commit chamfer
            elif self.mode == "chamfer" and self._chamfer_item1 is not None and self._chamfer_item2 is not None:
                data = self._tools._compute_chamfer(self._chamfer_item1, self._chamfer_item2,
                                              self._chamfer_dist)
                if data is not None:
                    self._tools._commit_chamfer(data)
                    self.push_undo_state()
                else:
                    self._show_status("Cannot compute chamfer for these objects", timeout=3000)
                self.set_mode(None)
                return
        # ── Type-to-engage: a digit/./- opens the on-canvas HUD ─────────────
        # ``event.text()`` is "" for every non-text key (F5, a bare modifier),
        # and `"" in ENGAGE_CHARS` is True in Python, so the empty case must be
        # excluded explicitly or every such key would try to engage.
        # begin_dynamic_input applies the real gates (schema, anchor) and its
        # return value decides whether the key is consumed here.
        #
        # ``effective_modifiers`` masks off KeypadModifier, which every numpad
        # keystroke carries.  Sharing the helper with ``DynamicInputHud`` makes
        # engage and commit agree by construction: whatever the numpad can open
        # here, the HUD's keys can also close.
        elif (event.text()
              and event.text() in self.ENGAGE_CHARS
              and effective_modifiers(event) == Qt.KeyboardModifier.NoModifier
              and not self.is_input_mode()
              and self.begin_dynamic_input(seed=event.text())):
            return
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Fire the placement-cycle on a clean left-Shift tap.

        The tap stays armed only if nothing happened between the left-Shift
        press and this release (see ``keyPressEvent`` and ``mousePressEvent``),
        so Shift+click, Shift+drag and Shift+key never cycle.  A HUD field
        having focus suppresses it too — Shift is an ordinary modifier there.
        """
        if (self._is_left_shift(event) and self._lshift_tap_armed
                and not event.isAutoRepeat()):
            self._lshift_tap_armed = False
            if not self.is_input_mode() and self.cycle_placement_ambiguity():
                event.accept()
                return
        super().keyReleaseEvent(event)

    # -------------------------------------------------------------------------
    # COPY / PASTE / MOVE

    def copy_selected_items(self):
        data = []
        for item in self.selectedItems():
            if isinstance(item, Node):
                sprinkler = item.sprinkler.get_properties() if item.has_sprinkler() else None
                pipes = []
                for p in item.pipes:
                    other = p.node1 if p.node2 == item else p.node2
                    pipes.append({"x": other.pos().x(), "y": other.pos().y()})
                data.append({
                    "type": "node",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "elevation": item.z_pos,
                    "ceiling_level": getattr(item, "ceiling_level", DEFAULT_LEVEL),
                    "ceiling_offset_mm": getattr(item, "ceiling_offset", DEFAULT_CEILING_OFFSET_MM),
                    "level": getattr(item, "level", DEFAULT_LEVEL),
                    "sprinkler": sprinkler,
                    "pipes": pipes,
                })
            elif hasattr(item, "to_dict"):
                data.append(item.to_dict())
        QApplication.clipboard().setText(json.dumps(data))
        self._show_status(f"Copied {len(data)} item(s)")

    def paste_items(self, offset):
        data = self.clipboard_data()
        for obj in data:
            obj_type = obj.get("type", "")
            if obj_type == "node":
                new_x = obj["x"] + offset.x()
                new_y = obj["y"] + offset.y()
                # Compute z_hint from clipboard elevation data
                paste_z = obj.get("elevation")
                if paste_z is None and "ceiling_level" in obj:
                    if self._level_manager:
                        _lvl = self._level_manager.get(obj["ceiling_level"])
                        if _lvl:
                            _off = obj.get("ceiling_offset_mm",
                                           DEFAULT_CEILING_OFFSET_MM)
                            paste_z = _lvl.elevation + _off
                existing = self.find_nearby_node(new_x, new_y, z_hint=paste_z)
                node1 = existing if existing else self.add_node(
                    new_x, new_y, z_hint=paste_z)

                # Restore ceiling and layer from copied data
                if "ceiling_level" in obj:
                    node1.ceiling_level = obj["ceiling_level"]
                    node1._properties["Ceiling Level"]["value"] = obj["ceiling_level"]
                if "ceiling_offset_mm" in obj:
                    node1.ceiling_offset = obj["ceiling_offset_mm"]
                    node1._properties["Ceiling Offset"]["value"] = str(obj["ceiling_offset_mm"])
                elif "z_offset" in obj:
                    # Old clipboard data: z_offset was raw elevation offset
                    node1.ceiling_offset = obj["z_offset"]
                    node1._properties["Ceiling Offset"]["value"] = str(obj["z_offset"])
                if "level" in obj:
                    node1.level = obj["level"]
                # Recompute z_pos from ceiling level + offset
                if self._level_manager:
                    lvl = self._level_manager.get(node1.ceiling_level)
                    if lvl:
                        node1.z_pos = lvl.elevation + node1.ceiling_offset
                    elif "elevation" in obj:
                        node1.z_pos = obj["elevation"]

                if obj.get("sprinkler"):
                    template = Sprinkler(None)
                    for key, meta in obj["sprinkler"].items():
                        template.set_property(key, meta["value"])
                    self.add_sprinkler(node1, template)

                for p in obj.get("pipes", []):
                    px = p["x"] + offset.x()
                    py = p["y"] + offset.y()
                    existing_p = self.find_nearby_node(
                        px, py, z_hint=paste_z)
                    node2 = existing_p if existing_p else self.add_node(
                        px, py, z_hint=paste_z)
                    if not any(
                        (pipe.node1 == node1 and pipe.node2 == node2) or
                        (pipe.node1 == node2 and pipe.node2 == node1)
                        for pipe in self.sprinkler_system.pipes
                    ):
                        self.add_pipe(node1, node2)
                node1.fitting.update()

            elif obj_type == "draw_line":
                item = LineItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.level = self.active_level
                self.addItem(item)
                self._draw_lines.append(item)

            elif obj_type == "draw_rectangle":
                item = RectangleItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.level = self.active_level
                self.addItem(item)
                self._draw_rects.append(item)

            elif obj_type == "draw_circle":
                item = CircleItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.level = self.active_level
                self.addItem(item)
                self._draw_circles.append(item)

            elif obj_type == "arc":
                item = ArcItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.level = self.active_level
                self.addItem(item)
                self._draw_arcs.append(item)

            elif obj_type == "polyline":
                item = PolylineItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.level = self.active_level
                self.addItem(item)
                self._polylines.append(item)

            elif obj_type == "polygon":
                item = RegularPolygonItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.level = self.active_level
                self.addItem(item)
                self._draw_polygons.append(item)

            elif obj_type == "block_item":
                from .block_item import BlockItem
                def _item_factory(d):
                    t = d.get("type", "")
                    if t == "draw_line":
                        return LineItem.from_dict(d)
                    elif t == "draw_rectangle":
                        return RectangleItem.from_dict(d)
                    elif t == "draw_circle":
                        return CircleItem.from_dict(d)
                    elif t == "polyline":
                        return PolylineItem.from_dict(d)
                    elif t == "arc":
                        return ArcItem.from_dict(d)
                    elif t == "polygon":
                        return RegularPolygonItem.from_dict(d)
                    elif t == "block_item":
                        return BlockItem.from_dict(d, _item_factory)
                    return None
                item = BlockItem.from_dict(obj, _item_factory)
                item.translate(offset.x(), offset.y())
                self.addItem(item)
                # BlockItems live in the scene but aren't tracked in a dedicated list

            elif "origin" in obj and "angle" in obj and not obj_type:
                # Gridline — to_dict() emits no "type" key; detect by parametric keys.
                gl = GridlineItem.from_dict(obj)
                gl._origin = QPointF(
                    gl._origin.x() + offset.x(),
                    gl._origin.y() + offset.y(),
                )
                gl._rebuild_geometry()
                sync_grid_counters(self._gridlines)
                gl.grid_label = auto_label(gl.grip_points()[0], gl.grip_points()[1])
                self._register_gridline(gl)
                apply_duplicate_warnings(self._gridlines)

        self._show_status(f"Pasted {len(data)} item(s)")

    def _shape_paths_for_move(self, items):
        """Scene-coord QPainterPath silhouettes for live scene *items*.
        Nodes have no useful shape() — emit a small cross marker."""
        from .node import Node
        from .sprinkler import Sprinkler
        paths = []
        for item in items:
            if isinstance(item, Sprinkler) and item.node is not None:
                item = item.node
            if isinstance(item, Node):
                c = item.scenePos()
                r = _GHOST_NODE_MARKER_MM
                p = QPainterPath()
                p.moveTo(c.x() - r, c.y()); p.lineTo(c.x() + r, c.y())
                p.moveTo(c.x(), c.y() - r); p.lineTo(c.x(), c.y() + r)
                paths.append(p)
                continue
            if isinstance(item, GridlineItem):
                # Ghost the centerline (grip endpoints), not the fat hit-strip
                # + bubbles that shape() returns.
                pts = item.grip_points()
                p = QPainterPath()
                p.moveTo(pts[0]); p.lineTo(pts[1])
                paths.append(p)
                continue
            if hasattr(item, "shape"):
                try:
                    paths.append(item.mapToScene(item.shape()))
                    continue
                except Exception:
                    pass
            if hasattr(item, "sceneBoundingRect"):
                p = QPainterPath(); p.addRect(item.sceneBoundingRect())
                paths.append(p)
        return paths

    def _clipboard_ghost_paths(self, data):
        """Scene-coord silhouettes reconstructed from clipboard *data* dicts,
        without adding anything to the scene. Covers the copyable types."""
        from .construction_geometry import (
            LineItem, RectangleItem, CircleItem, ArcItem, PolylineItem,
            RegularPolygonItem as _RegularPolygonItem,
        )
        paths = []
        if not data:
            return paths
        geom_ctors = {
            "draw_line": LineItem, "draw_rectangle": RectangleItem,
            "draw_circle": CircleItem, "draw_arc": ArcItem, "polyline": PolylineItem,
            "polygon": _RegularPolygonItem,
        }
        for obj in data:
            t = obj.get("type", "")
            if t == "gridline":
                ox, oy = obj.get("origin", [0.0, 0.0])
                length = float(obj.get("length", 0.0))
                th = math.radians(float(obj.get("angle", 0.0)))
                p = QPainterPath(); p.moveTo(ox, oy)
                p.lineTo(ox + length * math.cos(th), oy - length * math.sin(th))
                paths.append(p)
            elif t == "node":
                c = QPointF(obj.get("x", 0.0), obj.get("y", 0.0))
                r = _GHOST_NODE_MARKER_MM
                p = QPainterPath()
                p.moveTo(c.x() - r, c.y()); p.lineTo(c.x() + r, c.y())
                p.moveTo(c.x(), c.y() - r); p.lineTo(c.x(), c.y() + r)
                for seg in obj.get("pipes", []):
                    p.moveTo(c.x(), c.y()); p.lineTo(seg.get("x", 0.0), seg.get("y", 0.0))
                paths.append(p)
            elif t in geom_ctors:
                try:
                    item = geom_ctors[t].from_dict(obj)
                    paths.append(item.mapToScene(item.shape()))
                except Exception:
                    pass
        return paths

    def _build_move_ghost_base(self, is_paste: bool):
        """Base silhouettes (offset 0). Paste → clipboard; move → live selection."""
        if is_paste:
            return self._clipboard_ghost_paths(self.clipboard_data())
        return self._shape_paths_for_move(self._selected_items or self.selectedItems())

    def move_items(self, offset):
        if not self._selected_items:
            return
        # Resolve any Sprinkler items to their parent Node
        resolved = []
        seen = set()
        for item in self._selected_items:
            if isinstance(item, Sprinkler) and item.node is not None:
                item = item.node
            if id(item) not in seen:
                seen.add(id(item))
                resolved.append(item)
        for item in resolved:
            if isinstance(item, Node):
                item.moveBy(offset.x(), offset.y())
                item.setSelected(True)
                item.fitting.update()
            elif hasattr(item, "translate"):
                item.translate(offset.x(), offset.y())
                item.setSelected(True)
        self._tools._solve_constraints()  # enforce constraints after move
        self._selected_items = None   # clear after use

    def clipboard_data(self):
        text = QApplication.clipboard().text()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    # -------------------------------------------------------------------------
    # DUPLICATE (Sprint I)

    def duplicate_selected(self):
        """Copy selected items and immediately paste them at +10,+10 offset."""
        items = self.selectedItems()
        if not items:
            return

        data = []
        for item in items:
            if isinstance(item, Node):
                sprinkler = item.sprinkler.get_properties() if item.has_sprinkler() else None
                pipes_d = []
                for p in item.pipes:
                    other = p.node1 if p.node2 == item else p.node2
                    pipes_d.append({"x": other.pos().x(), "y": other.pos().y()})
                data.append({
                    "type": "node",
                    "x": item.pos().x(), "y": item.pos().y(),
                    "sprinkler": sprinkler, "pipes": pipes_d,
                })
            elif hasattr(item, "to_dict"):
                data.append(item.to_dict())

        if not data:
            return

        # Temporarily swap clipboard → paste → restore
        old = QApplication.clipboard().text()
        QApplication.clipboard().setText(json.dumps(data))
        self.paste_items(QPointF(10, 10))
        QApplication.clipboard().setText(old)
        self._show_status(f"Duplicated {len(data)} item(s)")
        self.push_undo_state()


    # -------------------------------------------------------------------------
    # GEOMETRY TOOLS -> see scene_tools.py (SceneTools)
    # array, rotate, scale, mirror, join, explode, break, fillet, chamfer,
    # stretch, trim, extend, merge, hatch, constraints, geometry helpers
    # -------------------------------------------------------------------------
