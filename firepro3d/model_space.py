import sys, json, math, shutil, logging

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
                          QFontMetricsF)
from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from .node import Node
from .pipe import Pipe
from .sprinkler import Sprinkler
from .sprinkler_system import SprinklerSystem
from .cad_math import CAD_Math
from .annotations import Annotation, DimensionAnnotation, NoteAnnotation
from .underlay import Underlay
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
                       UNDERLAY_MM_TO_PX_HINT,
                       AUTO_JOIN_TOLERANCE, TEE_TOLERANCE, Z_COPLANAR_TOL,
                       DESIGN_AREA_PICK_PX, DESIGN_AREA_HL_RADIUS_PX,
                       Z_OVERLAY, INFERENCE_TOL_PX,
                       OPENING_ALIGN_CENTER, OPENING_ALIGNMENTS,
                       SELECTION_OUTLINE_COLOR)
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
from .scene_tools import SceneToolsMixin


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
    else:
        width_px = UNDERLAY_LINE_WIDTH_PX
    pen = QPen(colour, width_px)
    pen.setCosmetic(True)
    return pen


class _PlacementSentinel:
    """Marker object: inference is active during placement, nothing to self-exclude.

    Must NOT implement alignment_reference_points() so that the engine
    excludes nothing — all existing gridlines remain valid candidates.
    """


_GHOST_NODE_MARKER_MM = 120.0  # half-size of the move/paste ghost cross for nodes

# Arc placement variants (see ``_arc_variant``).  De-stringly-typed so a typo
# fails loudly at import instead of silently falling into centre-first.
_ARC_VARIANT_CENTER = "center"   # centre-first: click 1 is the arc centre
_ARC_VARIANT_START = "start"     # start-first: click 1 is the start point


class Model_Space(SceneToolsMixin, SceneIOMixin, QGraphicsScene):
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
    osnapToggled = pyqtSignal(bool)    # emitted whenever toggle_osnap() runs
    inferenceToggled = pyqtSignal(bool)  # emitted whenever set_inference_enabled() runs
    pipeNodeHighlight = pyqtSignal(str)  # pipe-mode node snap readout for status bar

    def __init__(self):
        super().__init__()
        self.setSceneRect(QRectF(-500000, -500000, 1000000, 1000000))
        # One-time repair: fix display/*/visible stored as bool instead of string
        self._repair_display_settings()
        # Disable BSP-tree indexing — cosmetic-pen items (gridlines) are
        # culled incorrectly by the spatial index at high zoom levels.
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.sprinkler_system = SprinklerSystem()
        self.annotations = Annotation()
        self._sprinkler_db = None                              # shared DB, injected by MainWindow
        self.underlays: list[tuple[Underlay, QGraphicsItem]] = []  # (data, scene_item)
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
        self._snap_to_underlay: bool = False
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
        self._inference_exclude_ids: set = set()  # ids self-excluded from inference (move)
        # OSNAP (Sprint H)
        self._snap_engine: SnapEngine = SnapEngine()
        self._snap_result: "OsnapResult | None" = None
        self._osnap_enabled: bool = True
        self._snap_angle_deg: float = 45.0       # Ctrl-snap angle increment (degrees)
        # Inferred alignment guides (inference_engine.py)
        from .inference_engine import InferenceEngine
        self._inference_engine: InferenceEngine = InferenceEngine()
        self._inference_enabled: bool = True          # toggled via settings (Task 4)
        self._inference_result = None                 # surfaced to drawForeground (Task 3)
        self._inference_active_item = None            # item being placed/dragged (self-exclude)
        self._PLACEMENT_SENTINEL = _PlacementSentinel()  # shared sentinel for draw_gridline
        # Pipe-mode Tab cycling through Z-stacked node candidates
        self._pipe_tab_candidates: list = []
        self._pipe_tab_index: int = 0
        self._pipe_tab_pos: QPointF | None = None
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
        self._place_import_params = None
        self._place_import_ghost = None
        self._place_import_bounds = QRectF(-50, -50, 100, 100)
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
        self._floor_rect_anchor: "QPointF | None" = None   # first click for rect floor
        self._floor_rect_preview: "QGraphicsRectItem | None" = None
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
        self._pipe_tab_candidates = []
        self._pipe_tab_index = 0
        self._pipe_tab_pos = None
        if hasattr(self, 'pipeNodeHighlight'):
            self.pipeNodeHighlight.emit("")
        # Reset grip editing state (prevents stale grip after Escape mid-drag)
        self._grip_item = None
        self._grip_index = -1
        self._grip_dragging = False
        # Inference active-item: sentinel for draw_gridline + paste/move.
        if mode in ("draw_gridline", "paste", "move", "wall"):
            self._inference_active_item = self._PLACEMENT_SENTINEL
        else:
            self._inference_active_item = None
            self._inference_result = None
        # Move self-excludes the moving gridlines from the reference set.
        if mode == "move":
            self._inference_exclude_ids = {
                id(i) for i in (self.selectedItems() or [])
                if isinstance(i, GridlineItem)
            } | {
                id(i) for i in (self._selected_items or [])
                if isinstance(i, GridlineItem)
            }
        else:
            self._inference_exclude_ids = set()
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
        # Only remove node if we created it during pipe first-click and it's orphaned.
        # Pre-existing nodes must survive escape. In paste/move mode node_start_pos
        # is a QPointF — never call remove_node on it.
        if self.node_start_pos is not None:
            if isinstance(self.node_start_pos, Node) and self._pipe_node_was_new:
                self.remove_node(self.node_start_pos)
            self.node_start_pos = None
        self._pipe_node_was_new = False
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
            self._clear_offset_preview()
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
            self._clear_trim_state()

        # Clean up extend state
        if mode not in ("extend", "extend_pick"):
            self._clear_extend_state()

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
        # Clean up floor drawing state
        if mode != "floor":
            if self._floor_active is not None:
                if len(self._floor_active._points) < 3:
                    if self._floor_active.scene() is self:
                        self.removeItem(self._floor_active)
                    if self._floor_active in self._floor_slabs:
                        self._floor_slabs.remove(self._floor_active)
                self._floor_active = None
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
        if mode != "floor_rect":
            self._floor_rect_anchor = None
            if self._floor_rect_preview is not None:
                if self._floor_rect_preview.scene() is self:
                    self.removeItem(self._floor_rect_preview)
                self._floor_rect_preview = None
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

        # Clean up place_import ghost and params
        if mode != "place_import":
            if self._place_import_ghost is not None:
                if self._place_import_ghost.scene() is self:
                    self.removeItem(self._place_import_ghost)
                self._place_import_ghost = None
            self._place_import_params = None
            self._place_import_bounds = QRectF(-50, -50, 100, 100)

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
            "floor":           "Pick first boundary point (click near first to close)",
            "floor_rect":      "Pick first corner for rectangular floor",
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
        pt = QPointF(x, y)

        view_range = self._get_active_view_range()

        def _in_view_range(node):
            if view_range is None:
                return True
            return view_range[0] <= node.z_pos <= view_range[1]

        # Collect all XY candidates (both priority tiers), filtered by view range
        bbox_candidates = []
        dist_candidates = []
        for node in self.sprinkler_system.nodes:
            if not _in_view_range(node):
                continue
            if node.has_sprinkler():
                spr = node.sprinkler
                if spr.mapToScene(spr.boundingRect()).boundingRect().contains(pt):
                    bbox_candidates.append(node)
                    continue
            if node.distance_to(x, y) <= self.SNAP_RADIUS:
                dist_candidates.append(node)

        # Merge: bbox hits first, then distance hits
        candidates = bbox_candidates + dist_candidates
        if not candidates:
            return None
        if z_hint is None or len(candidates) == 1:
            return candidates[0]
        return min(candidates, key=lambda n: abs(n.z_pos - z_hint))

    def find_nearby_candidates(self, x, y, z_hint=None):
        """Return all nodes within SNAP_RADIUS, filtered by view range.

        If *z_hint* is provided, results are sorted by ascending distance
        to *z_hint*.  Otherwise sorted by insertion order.
        """
        pt = QPointF(x, y)
        view_range = self._get_active_view_range()

        def _in_view_range(node):
            if view_range is None:
                return True
            return view_range[0] <= node.z_pos <= view_range[1]

        candidates = []
        for node in self.sprinkler_system.nodes:
            if not _in_view_range(node):
                continue
            if node.has_sprinkler():
                spr = node.sprinkler
                if spr.mapToScene(spr.boundingRect()).boundingRect().contains(pt):
                    candidates.append(node)
                    continue
            if node.distance_to(x, y) <= self.SNAP_RADIUS:
                candidates.append(node)

        if z_hint is not None and len(candidates) > 1:
            candidates.sort(key=lambda n: abs(n.z_pos - z_hint))
        return candidates

    def _update_pipe_tab_candidates(self, scene_pos, z_hint=None):
        """Rebuild pipe-mode Tab candidate list at the given cursor position.

        Resets Tab index to 0.  Called on every cursor move in pipe mode.
        """
        self._pipe_tab_candidates = self.find_nearby_candidates(
            scene_pos.x(), scene_pos.y(), z_hint=z_hint)
        self._pipe_tab_index = 0
        self._pipe_tab_pos = QPointF(scene_pos.x(), scene_pos.y())
        self._emit_pipe_tab_readout()

    def _emit_pipe_tab_readout(self):
        """Emit signal with current Tab-cycle candidate info for status bar."""
        candidates = self._pipe_tab_candidates
        if not candidates:
            self.pipeNodeHighlight.emit("")
            return
        idx = self._pipe_tab_index
        node = candidates[idx]
        sm = self.scale_manager
        elev_str = sm.format_length(node.z_pos) if sm else f"{node.z_pos:.1f} mm"
        level_str = getattr(node, "ceiling_level", "?")
        total = len(candidates)
        if total > 1:
            text = f"Node @ {elev_str} ({level_str}) [{idx + 1}/{total}]"
        else:
            text = f"Node @ {elev_str} ({level_str})"
        self.pipeNodeHighlight.emit(text)

    def find_or_create_node(self, x, y, z_hint=None):
        existing = self.find_nearby_node(x, y, z_hint=z_hint)
        if existing:
            return existing
        return self.add_node(x, y, z_hint=z_hint)

    def add_node(self, x, y, z_hint=None):
        node = self.find_nearby_node(x, y, z_hint=z_hint)
        if not node:
            node = Node(x, y)
            node.level = self.active_level
            node.ceiling_level = self.active_level

            node._properties["Ceiling Level"]["value"] = self.active_level
            # Compute z_pos from ceiling level elevation + offset
            if self._level_manager:
                lvl = self._level_manager.get(self.active_level)
                if lvl:
                    node.z_pos = lvl.elevation + node.ceiling_offset
            self.addItem(node)
            apply_category_defaults(node)
            node.setVisible(True)
            self.sprinkler_system.add_node(node)
        return node

    def remove_node(self, n):
        try:
            self.sprinkler_system.remove_node(n)
        except ValueError:
            pass
        if n.scene() is self:
            self.removeItem(n)
        n = None
        self.node_start_pos = None

    @staticmethod
    def _apply_fitting_dm_colors(fitting):
        """Apply Display Manager colour/opacity to a fitting without re-aligning.

        This avoids the full apply_category_defaults → _apply_fitting → align_fitting
        chain which can displace the symbol if called at the wrong time.
        """
        from .display_manager import _set_svg_tint, _CATEGORIES
        from PyQt6.QtCore import QSettings
        cat_def = next((c for c in _CATEGORIES if c["key"] == "Fitting"), None)
        if cat_def is None or fitting.symbol is None:
            return
        settings = QSettings("GV", "FirePro3D")
        if not settings.contains("display/Fitting/color"):
            return  # no user-saved settings — keep SVG natural colours
        color = settings.value("display/Fitting/color", cat_def["color"])
        fill = settings.value("display/Fitting/fill", cat_def.get("fill"))
        opacity = int(float(settings.value("display/Fitting/opacity", cat_def["opacity"])))
        fitting._display_color = color
        fitting._display_fill_color = fill
        fitting._display_opacity = opacity
        _set_svg_tint(fitting.symbol, color, fill)
        fitting.symbol.setOpacity(opacity / 100.0 if opacity > 1 else opacity)

    def add_pipe(self, n1, n2, template=None, _propagate_ceiling=True):
        pipe = Pipe(n1, n2)
        # Apply template first so non-level properties are copied
        if template:
            pipe.set_properties(template)
        # Only override the visibility level (Level) with the active level.
        # Ceiling Level comes from the template — it controls 3D elevation.
        pipe.level = self.active_level
        self.sprinkler_system.add_pipe(pipe)
        self.addItem(pipe)
        apply_category_defaults(pipe)
        pipe.update_label()   # re-run now that pipe.scene() is valid
        pipe.update_geometry()
        # Ensure visibility — level filtering may not have run yet
        pipe.setVisible(True)
        pipe.setOpacity(1.0)
        pipe.update()
        # Update fittings at both endpoints immediately so they reflect
        # the new connection angle before anything else renders.
        # Collect all affected nodes first, then update + apply colours.
        affected_nodes = {n1, n2}
        for p in n1.pipes:
            affected_nodes.add(p.node2 if p.node1 is n1 else p.node1)
        for p in n2.pipes:
            affected_nodes.add(p.node2 if p.node1 is n2 else p.node1)
        for node in affected_nodes:
            node.fitting.update()
            self._apply_fitting_dm_colors(node.fitting)
        for v in self.views():
            v.viewport().update()

        # Propagate the pipe's ceiling properties to both endpoint nodes
        # so their 3D elevation matches what the user set on the template.
        # Skip during load — nodes already have authoritative ceiling data.
        if _propagate_ceiling and template is not None:
            # Use per-node ceiling values from template; fall back to defaults
            for node, lvl_attr, off_attr in (
                (n1, "node1_ceiling_level", "node1_ceiling_offset"),
                (n2, "node2_ceiling_level", "node2_ceiling_offset"),
            ):
                if node is None:
                    continue
                c_lvl = getattr(template, lvl_attr, None)
                c_off = getattr(template, off_attr, None)
                if c_lvl is None:
                    c_lvl = DEFAULT_LEVEL
                if c_off is None:
                    c_off = DEFAULT_CEILING_OFFSET_MM
                node.ceiling_level = c_lvl
                node._properties["Ceiling Level"]["value"] = c_lvl
                node.ceiling_offset = c_off
                node._properties["Ceiling Offset"]["value"] = str(c_off)
                node._recompute_z_pos()
        elif _propagate_ceiling:
            # No template — apply defaults to both endpoint nodes
            for node in (n1, n2):
                if node is not None:
                    node.ceiling_level = DEFAULT_LEVEL
                    node._properties["Ceiling Level"]["value"] = DEFAULT_LEVEL
                    node.ceiling_offset = DEFAULT_CEILING_OFFSET_MM
                    node._properties["Ceiling Offset"]["value"] = str(DEFAULT_CEILING_OFFSET_MM)
                    node._recompute_z_pos()

        return pipe

    def _validate_4th_branch(self, node, new_pt: QPointF) -> str | None:
        """Check whether adding a 4th coplanar branch at *node* toward *new_pt* is valid.

        A 4th coplanar pipe is only allowed if:
        - The existing coplanar fitting is a tee (3 pipes with a through-run pair)
        - The new pipe is perpendicular (~90°) to the through-run

        Only considers coplanar pipes (other endpoint within
        ``Z_COPLANAR_TOL`` of *node*).

        Returns an error message string, or None if the connection is valid.
        """
        from .fitting import Fitting
        nz = node.z_pos
        coplanar_pipes = [p for p in node.pipes
                          if abs((p.node2 if p.node1 is node else p.node1).z_pos
                                 - nz) <= Z_COPLANAR_TOL]
        if len(coplanar_pipes) != 3:
            return "A 4th branch can only be added to a tee fitting."
        # Check that the current coplanar fitting is actually a tee
        ft_type = node.fitting.determine_type(coplanar_pipes)
        if ft_type != "tee":
            return (f"A 4th branch can only be added to a tee fitting "
                    f"(current fitting: {ft_type}).")
        # Find the through-run direction (the collinear pair in the tee)
        np_ = node.scenePos()
        vectors = []
        for p in coplanar_pipes:
            other = p.node2 if p.node1 is node else p.node1
            op = other.scenePos()
            dx, dy = op.x() - np_.x(), op.y() - np_.y()
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            vectors.append((dx / length, dy / length))
        if len(vectors) != 3:
            return "Cannot determine pipe directions at this node."
        # Find the collinear pair (angle ≈ 180°)
        through_dir = None
        for i in range(3):
            for j in range(i + 1, 3):
                dot = vectors[i][0] * vectors[j][0] + vectors[i][1] * vectors[j][1]
                if dot < -0.95:  # ~180° ± ~18°
                    through_dir = vectors[i]
                    break
            if through_dir:
                break
        if through_dir is None:
            return "Cannot find through-run direction on this tee."
        # Check new pipe direction is perpendicular to through-run
        dx_new = new_pt.x() - np_.x()
        dy_new = new_pt.y() - np_.y()
        len_new = math.hypot(dx_new, dy_new)
        if len_new < 1e-6:
            return "New pipe has zero length."
        ux_new, uy_new = dx_new / len_new, dy_new / len_new
        dot_new = through_dir[0] * ux_new + through_dir[1] * uy_new
        if abs(dot_new) > 0.17:  # cos(80°) ≈ 0.17 — must be within ~10° of 90°
            return ("A 4th branch must be perpendicular to the through-run "
                    "to form a cross fitting.")
        return None

    def _would_backtrack(self, start_node, end_node) -> bool:
        """Return True if placing a pipe from *start_node* to *end_node*
        would overlap an existing pipe (backtracking).

        Checks:
        1. Direct duplicate — a pipe already connects the same two nodes.
        2. End lands on an existing pipe connected to start — the new end
           point lies between the endpoints of a pipe already attached to
           start_node.

        Only considers coplanar pipes (other endpoint within
        ``Z_COPLANAR_TOL`` of *start_node*).
        """
        ep = end_node.scenePos()
        sz = start_node.z_pos
        for pipe in start_node.pipes:
            other = pipe.node2 if pipe.node1 is start_node else pipe.node1
            # Direct duplicate — always block regardless of Z
            if other is end_node:
                return True
            # Skip non-coplanar pipes (risers / cross-level)
            if abs(other.z_pos - sz) > Z_COPLANAR_TOL:
                continue
            # End point lies on an existing pipe segment
            op = other.scenePos()
            sp = start_node.scenePos()
            dx, dy = op.x() - sp.x(), op.y() - sp.y()
            length_sq = dx * dx + dy * dy
            if length_sq < 1e-6:
                continue
            t = ((ep.x() - sp.x()) * dx + (ep.y() - sp.y()) * dy) / length_sq
            if 0.01 < t < 0.99:
                proj_x = sp.x() + t * dx
                proj_y = sp.y() + t * dy
                dist = math.hypot(ep.x() - proj_x, ep.y() - proj_y)
                if dist < 10.0:
                    return True
        return False

    def _would_backtrack_at(self, start_node, target_pt: QPointF) -> bool:
        """Like _would_backtrack but takes a point instead of a node.

        Used to check for backtracking *before* creating a node.
        Only considers coplanar pipes (other endpoint within
        ``Z_COPLANAR_TOL`` of *start_node*).
        """
        sp = start_node.scenePos()
        sz = start_node.z_pos
        for pipe in start_node.pipes:
            other = pipe.node2 if pipe.node1 is start_node else pipe.node1
            # Skip non-coplanar pipes (risers / cross-level)
            if abs(other.z_pos - sz) > Z_COPLANAR_TOL:
                continue
            op = other.scenePos()
            # Check if target_pt is the same as other node
            if math.hypot(target_pt.x() - op.x(), target_pt.y() - op.y()) < 5.0:
                return True
            # Check if target_pt lies on existing pipe segment
            dx, dy = op.x() - sp.x(), op.y() - sp.y()
            length_sq = dx * dx + dy * dy
            if length_sq < 1e-6:
                continue
            t = ((target_pt.x() - sp.x()) * dx + (target_pt.y() - sp.y()) * dy) / length_sq
            if 0.01 < t < 0.99:
                proj_x = sp.x() + t * dx
                proj_y = sp.y() + t * dy
                dist = math.hypot(target_pt.x() - proj_x, target_pt.y() - proj_y)
                if dist < 10.0:
                    return True
        return False

    def _try_extend_collinear(self, start_node, end_node, template) -> bool:
        """If start_node has exactly one other pipe and the new direction is
        collinear, extend that pipe to *end_node* and remove start_node.

        Returns True if extension happened, False otherwise.
        """
        # Don't merge if the node has a sprinkler
        if start_node.has_sprinkler():
            return False

        other_pipes = [p for p in start_node.pipes]
        if len(other_pipes) != 1:
            return False  # junction or isolated — don't merge

        existing = other_pipes[0]
        far_node = existing.node2 if existing.node1 is start_node else existing.node1

        # Direction of existing pipe (far_node → start_node)
        sp = start_node.scenePos()
        fp = far_node.scenePos()
        ep = end_node.scenePos()

        dx_old = sp.x() - fp.x()
        dy_old = sp.y() - fp.y()
        dx_new = ep.x() - sp.x()
        dy_new = ep.y() - sp.y()

        len_old = math.hypot(dx_old, dy_old)
        len_new = math.hypot(dx_new, dy_new)
        if len_old < 1e-6 or len_new < 1e-6:
            return False

        # Normalise
        ux_old, uy_old = dx_old / len_old, dy_old / len_old
        ux_new, uy_new = dx_new / len_new, dy_new / len_new

        # Dot product: collinear if ≈ 1.0 (same direction continuation)
        dot = ux_old * ux_new + uy_old * uy_new
        if abs(dot - 1.0) > 0.05:  # ~5° tolerance
            return False

        # Extend: reconnect existing pipe — replace start_node with end_node
        # Only remove from the node being replaced (start_node), keep far_node
        if existing in start_node.pipes:
            start_node.pipes.remove(existing)

        # Reconnect the pipe endpoint
        if existing.node1 is start_node:
            existing.node1 = end_node
        else:
            existing.node2 = end_node
        end_node.pipes.append(existing)
        existing.update_geometry()
        existing.set_pipe_display()
        existing.update_label()
        existing.update()

        # Remove orphaned start_node
        if len(start_node.pipes) == 0:
            self.sprinkler_system.remove_node(start_node)
            self.removeItem(start_node)

        # Update fittings at both endpoints + apply DM colours
        far_node.fitting.update()
        self._apply_fitting_dm_colors(far_node.fitting)
        end_node.fitting.update()
        self._apply_fitting_dm_colors(end_node.fitting)
        self.update()
        return True

    def _convert_45_elbow_to_wye(self, junction_node, template):
        """If the junction has a sharp 45° angle between pipe vectors,
        add a 1-ft capped stub on the through branch to create a wye.

        A 135° angle between vectors is a normal 45° elbow (keep it).
        A 45° angle between vectors is too sharp for a real fitting —
        add a stub continuing the *first* (through) pipe direction so
        the node becomes a 3-pipe wye.
        """
        if junction_node.fitting.type != "45elbow":
            return

        pipes = list(junction_node.pipes)
        if len(pipes) != 2:
            return

        jp = junction_node.scenePos()

        v = []
        for p in pipes:
            far = p.node2 if p.node1 is junction_node else p.node1
            fp = far.scenePos()
            dx, dy = fp.x() - jp.x(), fp.y() - jp.y()
            length = math.hypot(dx, dy)
            if length < 1e-6:
                return
            v.append((dx / length, dy / length, p))

        angle = abs(CAD_Math.get_angle_between_vectors(
            QPointF(v[0][0], v[0][1]), QPointF(v[1][0], v[1][1]),
            signed=False))

        # 135° between vectors → normal 45° elbow (body angle), leave it
        if math.isclose(angle, 135, abs_tol=10):
            return

        # ~45° angle: too sharp — add a stub on the through branch.
        # The through pipe is the one placed FIRST (earlier in the list).
        # The new pipe (branch) was just appended, so it's last.
        through_dir = (v[0][0], v[0][1])

        # Stub continues opposite the through direction (away from the first pipe)
        STUB_LENGTH = 304.8  # 1 ft in mm
        stub_x = jp.x() - through_dir[0] * STUB_LENGTH
        stub_y = jp.y() - through_dir[1] * STUB_LENGTH
        stub_node = self.add_node(stub_x, stub_y)

        # Add stub pipe
        self.add_pipe(junction_node, stub_node, template)

        # Let the existing fitting logic determine type (3 pipes → wye)
        junction_node.fitting.update()
        stub_node.fitting.update()

    # ── Vertical pipe helpers ─────────────────────────────────────────────

    def _compute_template_z_pos(self, template, node_idx: int = 1) -> float | None:
        """Compute the z_pos (mm) that a template pipe would impose.

        *node_idx* selects which endpoint: 1 for start node, 2 for end node.
        Uses per-node ceiling attributes when available, falling back to the
        pipe-level Ceiling Level / Ceiling Offset properties.
        """
        if node_idx == 1:
            ceiling_lvl_name = getattr(template, "node1_ceiling_level", None)
            offset = getattr(template, "node1_ceiling_offset", None)
        else:
            ceiling_lvl_name = getattr(template, "node2_ceiling_level", None)
            offset = getattr(template, "node2_ceiling_offset", None)
        # Fallback to defaults (pipe-level ceiling attrs were removed)
        if not ceiling_lvl_name:
            ceiling_lvl_name = DEFAULT_LEVEL
        if offset is None:
            offset = DEFAULT_CEILING_OFFSET_MM
        if not ceiling_lvl_name or not self._level_manager:
            return None
        lvl = self._level_manager.get(ceiling_lvl_name)
        if lvl is None:
            return None
        return lvl.elevation + offset

    def _make_intermediate_node(self, existing_node, template):
        """Create a node at *existing_node*'s XY but at the template's ceiling level.

        Bypasses ``add_node()`` because ``find_nearby_node()`` would return
        *existing_node* (same XY within SNAP_RADIUS).  Returns the new node.
        """
        ex = existing_node.scenePos().x()
        ey = existing_node.scenePos().y()

        intermediate = Node(ex, ey)
        intermediate.level = self.active_level

        ceiling_lvl = getattr(template, "node1_ceiling_level", None) or DEFAULT_LEVEL
        ceiling_off = getattr(template, "node1_ceiling_offset", None)
        if ceiling_off is None:
            ceiling_off = DEFAULT_CEILING_OFFSET_MM
        intermediate.ceiling_level = ceiling_lvl
        intermediate._properties["Ceiling Level"]["value"] = ceiling_lvl
        intermediate.ceiling_offset = ceiling_off
        intermediate._properties["Ceiling Offset"]["value"] = str(ceiling_off)
        if self._level_manager:
            lvl = self._level_manager.get(ceiling_lvl)
            if lvl:
                intermediate.z_pos = lvl.elevation + ceiling_off

        self.addItem(intermediate)
        self.sprinkler_system.add_node(intermediate)
        return intermediate

    def _make_intermediate_node_for_n2(self, existing_node, template):
        """Create a node at *existing_node*'s XY using template's Node 2 ceiling.

        Same as ``_make_intermediate_node`` but reads from the per-node
        ``node2_ceiling_level`` / ``node2_ceiling_offset`` attributes.
        """
        ex = existing_node.scenePos().x()
        ey = existing_node.scenePos().y()

        node = Node(ex, ey)
        node.level = self.active_level

        ceiling_lvl = getattr(template, "node2_ceiling_level", None) or DEFAULT_LEVEL
        ceiling_off = getattr(template, "node2_ceiling_offset", None)
        if ceiling_off is None:
            ceiling_off = DEFAULT_CEILING_OFFSET_MM
        node.ceiling_level = ceiling_lvl
        node._properties["Ceiling Level"]["value"] = ceiling_lvl
        node.ceiling_offset = ceiling_off
        node._properties["Ceiling Offset"]["value"] = str(ceiling_off)
        if self._level_manager:
            lvl = self._level_manager.get(ceiling_lvl)
            if lvl:
                node.z_pos = lvl.elevation + ceiling_off

        self.addItem(node)
        self.sprinkler_system.add_node(node)
        return node

    def _create_vertical_connection(self, start_node, existing_end_node, template):
        """Insert an intermediate node + vertical pipe + horizontal pipe.

        * intermediate_node — same XY as *existing_end_node* but at the
          template's Ceiling Level / Offset.
        * vertical pipe — between *existing_end_node* and *intermediate_node*.
        * horizontal pipe — between *start_node* and *intermediate_node*
          (carries the full template).
        """
        intermediate = self._make_intermediate_node(existing_end_node, template)

        # Vertical pipe (existing_end_node <-> intermediate) — same XY, different z
        self.add_pipe(existing_end_node, intermediate, template,
                      _propagate_ceiling=False)

        # Horizontal pipe (start_node <-> intermediate) with full template
        self.add_pipe(start_node, intermediate, template)

    def _find_or_split_vertical_at_z(self, xy_pos: QPointF,
                                      target_z: float,
                                      template) -> "Node | None":
        """Find an existing node or split a vertical pipe at *target_z* near *xy_pos*.

        Search order:
        1. Existing node at this XY whose z_pos matches *target_z*.
        2. Vertical pipe at this XY whose Z range spans *target_z* — split it.

        Returns the node at *target_z*, or ``None`` if nothing suitable exists.
        """
        if target_z is None:
            return None
        snap_r = self.SNAP_RADIUS
        # 1. Existing node at matching XY and Z
        for node in self.sprinkler_system.nodes:
            if node.distance_to(xy_pos.x(), xy_pos.y()) <= snap_r:
                if abs(node.z_pos - target_z) < 0.5:
                    return node
        # 2. Vertical pipe spanning target_z
        for pipe in self.sprinkler_system.pipes:
            if not pipe.node1 or not pipe.node2:
                continue
            if not pipe._is_vertical():
                continue
            pipe_xy = pipe.node1.scenePos()
            dx = pipe_xy.x() - xy_pos.x()
            dy = pipe_xy.y() - xy_pos.y()
            if (dx * dx + dy * dy) > snap_r * snap_r:
                continue
            z_lo = min(pipe.node1.z_pos, pipe.node2.z_pos)
            z_hi = max(pipe.node1.z_pos, pipe.node2.z_pos)
            if z_lo + 0.5 < target_z < z_hi - 0.5:
                return self._split_vertical_pipe(pipe, target_z, template)
        return None

    def _split_vertical_pipe(self, pipe, target_z: float, template) -> "Node":
        """Split a vertical pipe at *target_z*, returning the new mid-node.

        Creates a new node at the pipe's XY with the template's ceiling
        properties (so z_pos == target_z), then replaces the original pipe
        with two shorter vertical pipes.
        """
        xy = pipe.node1.scenePos()
        mid = Node(xy.x(), xy.y())
        mid.level = self.active_level

        ceiling_lvl = getattr(template, "node1_ceiling_level", None) or DEFAULT_LEVEL
        ceiling_off = getattr(template, "node1_ceiling_offset", None)
        if ceiling_off is None:
            ceiling_off = DEFAULT_CEILING_OFFSET_MM
        mid.ceiling_level = ceiling_lvl
        mid._properties["Ceiling Level"]["value"] = ceiling_lvl
        mid.ceiling_offset = ceiling_off
        mid._properties["Ceiling Offset"]["value"] = str(ceiling_off)
        mid.z_pos = target_z

        self.addItem(mid)
        self.sprinkler_system.add_node(mid)

        # Create two replacement vertical pipes preserving the original's properties
        node_a = pipe.node1
        node_b = pipe.node2
        for (na, nb) in ((node_a, mid), (mid, node_b)):
            seg = Pipe(na, nb)
            seg.level = pipe.level
            for key in ("Diameter", "Schedule", "C-Factor",
                        "Material", "Colour", "Phase", "Line Type"):
                seg._properties[key]["value"] = pipe._properties[key]["value"]
            self.sprinkler_system.add_pipe(seg)
            self.addItem(seg)
            seg.set_pipe_display()

        self.delete_pipe(pipe)
        mid.fitting.update()
        node_a.fitting.update()
        node_b.fitting.update()
        return mid

    # ── End vertical pipe helpers ─────────────────────────────────────────

    def split_pipe(self, pipe, split_point: QPointF):
        # If split point is near an existing endpoint, return that node
        # instead of creating a tiny degenerate split.
        for end_node in (pipe.node1, pipe.node2):
            if end_node is not None:
                dx = end_node.scenePos().x() - split_point.x()
                dy = end_node.scenePos().y() - split_point.y()
                if (dx * dx + dy * dy) < self.SNAP_RADIUS * self.SNAP_RADIUS:
                    return end_node
        new_node = self.add_node(split_point.x(), split_point.y())
        node_a = pipe.node1
        node_b = pipe.node2
        # Use _propagate_ceiling=False — pipe attributes can be stale.
        # Copy ceiling from the authoritative source (endpoint nodes).
        self.add_pipe(node_a, new_node, pipe, _propagate_ceiling=False)
        self.add_pipe(new_node, node_b, pipe, _propagate_ceiling=False)
        self.delete_pipe(pipe)
        # Set new_node's ceiling from node_a (authoritative endpoint)
        new_node.ceiling_level = node_a.ceiling_level
        new_node._properties["Ceiling Level"]["value"] = node_a.ceiling_level
        new_node.ceiling_offset = node_a.ceiling_offset
        new_node._properties["Ceiling Offset"]["value"] = str(node_a.ceiling_offset)
        new_node._recompute_z_pos()
        new_node.fitting.update()
        node_a.fitting.update()
        node_b.fitting.update()
        return new_node

    def delete_pipe(self, pipe):
        for node in (pipe.node1, pipe.node2):
            if node is not None:
                node.remove_pipe(pipe)
                if not node.has_sprinkler() and not node.pipes:
                    self.remove_node(node)
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
            self.removeItem(pipe)
        except (RuntimeError, ValueError):
            pass  # item may already be removed from scene
        if pipe in self.sprinkler_system.pipes:
            self.sprinkler_system.remove_pipe(pipe)

    def add_sprinkler(self, n, template=None):
        if n.has_sprinkler():
            return
        n.add_sprinkler()
        sprinkler = n.sprinkler
        self.sprinkler_system.add_sprinkler(sprinkler)
        if template:
            sprinkler.set_properties(template)
        apply_category_defaults(sprinkler)
        sprinkler.setVisible(True)
        sprinkler.update()
        if n.has_fitting():
            n.fitting.update()
        for v in self.views():
            v.viewport().update()
        return sprinkler

    def remove_sprinkler(self, n):
        sprinkler = n.sprinkler
        self.removeItem(sprinkler)
        self.sprinkler_system.remove_sprinkler(sprinkler)
        n.delete_sprinkler()

    # ── Auto-populate room with sprinklers ─────────────────────────────────

    def auto_populate_room(self, room, positions, sprinkler_record,
                           level, ceiling_level, sprinkler_offset,
                           design_density="0.10"):
        """Place sprinkler nodes at computed positions inside a room.

        Parameters
        ----------
        room : Room
            The target room.
        positions : list[QPointF]
            Scene-unit positions for each sprinkler.
        sprinkler_record : SprinklerRecord
            Database record to apply as template properties.
        level, ceiling_level : str
            Level names for the nodes.
        sprinkler_offset : float
            Offset from ceiling surface in mm (negative = below).
        design_density : str
            Design density string (gpm/ft²).
        """
        if not positions:
            return

        self.push_undo_state()

        # Remove existing sprinklers in this room before placing new ones
        existing = room._detect_sprinklers()
        for spr in existing:
            node = spr.node
            if node is not None:
                # Remove the sprinkler from the node
                if node.sprinkler is spr:
                    node.delete_sprinkler()
                # If the node has no pipes, remove it entirely
                if not node.pipes:
                    self.sprinkler_system.remove_node(node)
                    if node.scene() is self:
                        self.removeItem(node)

        # Compute the node ceiling_offset so the sprinkler ends up at
        # the correct absolute Z:
        #   ceiling_offset = sprinkler_offset - (ceil_level_elev - room_ceiling_elev)
        # This accounts for dropped ceilings where the room ceiling is
        # lower than the ceiling level.
        ceiling_offset = sprinkler_offset
        lm = self._level_manager
        if lm is not None:
            ceil_lvl = lm.get(ceiling_level)
            if ceil_lvl is not None:
                ceil_level_elev = ceil_lvl.elevation
                zr = room.z_range_mm()
                if zr is not None:
                    room_ceiling_elev = max(zr)
                    ceiling_offset = sprinkler_offset - (ceil_level_elev - room_ceiling_elev)

        # Build a temporary Sprinkler as template for set_properties
        from .sprinkler import Sprinkler
        temp_spr = Sprinkler(None)
        temp_spr._properties["Manufacturer"]["value"] = sprinkler_record.manufacturer
        temp_spr._properties["Model"]["value"] = sprinkler_record.model
        temp_spr._properties["Orientation"]["value"] = sprinkler_record.type
        temp_spr._properties["K-Factor"]["value"] = str(sprinkler_record.k_factor)
        temp_spr._properties["Coverage Area"]["value"] = str(sprinkler_record.coverage_area)
        temp_spr._properties["Min Pressure"]["value"] = str(sprinkler_record.min_pressure)
        temp_spr._properties["Temperature"]["value"] = f"{sprinkler_record.temp_rating}\u00b0F"
        temp_spr._properties["Design Density"]["value"] = design_density
        # Level is a Node property, not a Sprinkler property — set on node below
        temp_spr._properties["Ceiling Level"]["value"] = ceiling_level
        temp_spr._properties["Ceiling Offset"]["value"] = str(ceiling_offset)

        count = 0
        for pt in positions:
            # Always create a NEW node — don't reuse existing nodes at
            # the same XY.  Stacked rooms need separate nodes at
            # different Z positions for the same XY location.
            node = Node(pt.x(), pt.y())
            self.addItem(node)
            self.sprinkler_system.add_node(node)
            # Set level, ceiling, and room assignment
            node.level = level
            node._room_name = room.name
            node.ceiling_level = ceiling_level
            node._properties["Ceiling Level"]["value"] = ceiling_level
            node.ceiling_offset = ceiling_offset
            node._properties["Ceiling Offset"]["value"] = str(ceiling_offset)
            node._recompute_z_pos()
            self.add_sprinkler(node, temp_spr)
            count += 1

        room_name = room.name or room._tag or "room"
        self._show_status(f"Placed {count} sprinkler(s) in {room_name}.")

    # -------------------------------------------------------------------------
    # UNDERLAYS — IMPORT

    # ─────────────────────────────────────────────────────────────────────────
    # PREVIEW-FIRST IMPORT (place_import mode)
    # ─────────────────────────────────────────────────────────────────────────

    def begin_place_import(self, params):
        """
        Start the interactive placement of a DXF block after the preview dialog.

        The scene enters 'place_import' mode.  A ghost bounding-box preview
        follows the cursor.  Clicking commits the placement.

        Parameters
        ----------
        params : ImportParams
            Result from DxfPreviewDialog.get_import_params()
        """
        self._place_import_params = params
        self._place_import_ghost = None

        # Build a bounding rect for the (scaled, base-point-adjusted) geometry
        if params.geom_list:
            xs, ys = [], []
            s = params.scale
            bx, by = params.base_x, params.base_y
            for g in params.geom_list:
                kind = g.get("kind")
                if kind == "line":
                    xs += [(g["x1"] - bx) * s, (g["x2"] - bx) * s]
                    ys += [(g["y1"] - by) * s, (g["y2"] - by) * s]
                elif kind in ("circle", "arc"):
                    x0 = (g.get("x", g.get("rx", 0)) - bx) * s
                    y0 = (g.get("y", g.get("ry", 0)) - by) * s
                    xs += [x0, x0 + g.get("w", g.get("rw", 0)) * s]
                    ys += [y0, y0 + g.get("h", g.get("rh", 0)) * s]
                elif kind == "path_points":
                    for pt in g.get("points", []):
                        xs.append((pt[0] - bx) * s)
                        ys.append((pt[1] - by) * s)
                elif kind == "text":
                    xs.append((g["x"] - bx) * s)
                    ys.append((g["y"] - by) * s)
            if xs and ys:
                self._place_import_bounds = QRectF(
                    min(xs), min(ys),
                    max(xs) - min(xs), max(ys) - min(ys)
                )
            else:
                self._place_import_bounds = QRectF(-50, -50, 100, 100)
        else:
            self._place_import_bounds = QRectF(-50, -50, 100, 100)

        self.set_mode("place_import")

    def _update_place_import_ghost(self, pos: QPointF):
        """Reposition the ghost bounding rect at cursor position."""
        if self._place_import_ghost is not None:
            if self._place_import_ghost.scene() is self:
                self.removeItem(self._place_import_ghost)
            self._place_import_ghost = None

        r = self._place_import_bounds
        ghost = QGraphicsRectItem(r)  # local coords
        pen = QPen(QColor("#4fa3e0"), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        ghost.setPen(pen)
        ghost.setBrush(QBrush(QColor(79, 163, 224, 20)))
        ghost.setZValue(200)
        ghost.setPos(pos)
        # Show rotation from import params
        rotation = getattr(self._place_import_params, "rotation", 0.0)
        if rotation != 0.0:
            ghost.setRotation(rotation)
        self.addItem(ghost)
        self._place_import_ghost = ghost

    def _commit_place_import(self, insert_pt: QPointF):
        """Finalize placement: create the underlay group at insert_pt."""
        if self._place_import_ghost is not None:
            if self._place_import_ghost.scene() is self:
                self.removeItem(self._place_import_ghost)
            self._place_import_ghost = None

        params = self._place_import_params
        if not params or not params.geom_list:
            self.set_mode(None)
            return

        # Write geometry cache (raw, pre-transform)
        _cache_written = self._write_underlay_cache(
            params.file_path, params.geom_list,
            page=getattr(params, "pdf_page", 0),
            selected_layers=getattr(params, "selected_layers", None),
            layout=getattr(params, "layout", ""),
            import_bounds=getattr(params, "import_bounds", None))

        s = params.scale
        bx, by = params.base_x, params.base_y

        # Transform geometry: shift by base point and apply scale
        transformed = []
        for g in params.geom_list:
            kind = g.get("kind")
            t = dict(g)
            if kind == "line":
                t["x1"] = (g["x1"] - bx) * s
                t["y1"] = (g["y1"] - by) * s
                t["x2"] = (g["x2"] - bx) * s
                t["y2"] = (g["y2"] - by) * s
            elif kind in ("circle", "arc"):
                xk = "x" if kind == "circle" else "rx"
                yk = "y" if kind == "circle" else "ry"
                wk = "w" if kind == "circle" else "rw"
                hk = "h" if kind == "circle" else "rh"
                t[xk] = (g[xk] - bx) * s
                t[yk] = (g[yk] - by) * s
                t[wk] = g[wk] * s
                t[hk] = g[hk] * s
            elif kind == "ellipse_full":
                t["pos_cx"] = (g["pos_cx"] - bx) * s
                t["pos_cy"] = (g["pos_cy"] - by) * s
                t["x"] = g["x"] * s; t["y"] = g["y"] * s
                t["w"] = g["w"] * s; t["h"] = g["h"] * s
            elif kind == "path_points":
                t["points"] = [((p[0] - bx) * s, (p[1] - by) * s)
                               for p in g["points"]]
            elif kind == "text":
                t["x"] = (g["x"] - bx) * s
                t["y"] = (g["y"] - by) * s
                if "size" in g:
                    t["size"] = g["size"] * s
            transformed.append(t)

        file_type = getattr(params, "file_type", "dxf")
        rotation = getattr(params, "rotation", 0.0)
        record = Underlay(
            type=file_type, path=params.file_path,
            x=insert_pt.x(), y=insert_pt.y(),
            rotation=rotation,
            colour="#c0c0c0",
            line_weight=UNDERLAY_LINE_WIDTH_PX,
            import_scale=s,
            import_base_x=bx,
            import_base_y=by,
            selected_layers=getattr(params, "selected_layers", None),
            level=self.active_level,
            import_mode=getattr(params, "import_mode", "auto"),
            layout=getattr(params, "layout", ""),
            import_bounds=getattr(params, "import_bounds", None),
        )

        result = self._build_batched_underlay_group(transformed, record)
        if result is None:
            self.set_mode(None)
            return

        group, all_layers = result
        group.setPos(insert_pt)
        _TYPE_LABELS = {"pdf": "PDF Underlay", "dxf": "DXF Underlay", "dwg": "DWG Underlay"}
        group.setData(0, _TYPE_LABELS.get(file_type, "DXF Underlay"))
        group.setData(2, all_layers)
        group.setData(5, params.geom_list)  # raw pre-transform geom for cache
        group.setData(6, not _cache_written)  # dirty until cached on save

        self._apply_underlay_display(group, record)
        self._apply_underlay_hidden_layers(group, record)
        self._attach_snap_index(group, transformed, record)
        self.underlays.append((record, group))
        self.underlaysChanged.emit()
        self.push_undo_state()

        self.set_mode(None)

    def import_dxf(self, file_path, color=QColor("white"), line_weight=0,
                   x=0.0, y=0.0, layers=None, _record: Underlay = None,
                   layout: str = "", skip_sanitize: bool = False):
        """
        Import a DXF file as an underlay using a background thread.

        Supported entities: LINE, CIRCLE, ARC, ELLIPSE, LWPOLYLINE, POLYLINE,
        SPLINE, TEXT, MTEXT.

        Parameters
        ----------
        layers : list[str] | None
            If given, only import entities on these layers. None = all layers.
        """
        parent_widget = self.views()[0] if self.views() else None

        # Create progress dialog
        progress = QProgressDialog("Importing DXF…", "Cancel", 0, 100, parent_widget)
        progress.setWindowTitle("DXF Import")
        progress.setMinimumDuration(0)   # show immediately
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setValue(0)

        # Create and configure worker (no Qt objects passed — created on main thread later)
        worker = DxfImportWorker(file_path, layers, layout=layout,
                                 skip_sanitize=skip_sanitize)

        # Store references so they don't get garbage-collected
        self._dxf_worker = worker
        self._dxf_progress = progress
        self._dxf_import_params = {
            "file_path": file_path, "color": color, "line_weight": line_weight,
            "x": x, "y": y, "layers": layers, "_record": _record,
            "layout": layout,
        }

        # Wire signals
        worker.progress.connect(lambda cur, tot: self._on_dxf_progress(progress, cur, tot))
        worker.status.connect(lambda msg: progress.setLabelText(msg))
        worker.finished_data.connect(lambda geom_list: self._on_dxf_finished(geom_list, progress))
        worker.error.connect(lambda msg: self._on_dxf_error(msg, progress))
        progress.canceled.connect(worker.cancel)

        worker.start()

    def _on_dxf_progress(self, progress: QProgressDialog, current: int, total: int):
        if total > 0:
            progress.setMaximum(total)
            progress.setValue(current)

    def _on_dxf_finished(self, geom_list: list, progress: QProgressDialog):
        """Receives raw geometry dicts from the worker and creates QGraphicsItems
        on the main thread (required by Qt)."""
        params = self._dxf_import_params

        if not geom_list:
            progress.close()
            self._cleanup_dxf_worker()
            return

        color = params.get("color", QColor("#c0c0c0"))

        # Apply spatial bounds filter (area selection at import time)
        record = params.get("_record")
        if record is not None and record.import_bounds is not None:
            from .dwg_converter import filter_geoms_by_bounds
            geom_list = filter_geoms_by_bounds(
                geom_list, [tuple(record.import_bounds)])

        # Write geometry cache (filtered, pre-transform)
        cache_source = params.get("_dwg_source_path", params["file_path"])
        _cache_written = self._write_underlay_cache(
            cache_source, geom_list,
            page=0,
            selected_layers=params.get("layers"),
            layout=params.get("layout", ""),
            import_bounds=(record.import_bounds
                           if record is not None else None))

        # Snapshot raw geom for cache-on-save (before transform mutates)
        _raw_geom = geom_list

        # Apply import transform if reloading from a record with baked params
        if record is not None and (record.import_scale != 1.0
                                    or record.import_base_x != 0.0
                                    or record.import_base_y != 0.0):
            s = record.import_scale
            bx, by = record.import_base_x, record.import_base_y
            transformed = []
            for g in geom_list:
                kind = g.get("kind")
                t = dict(g)
                if kind == "line":
                    t["x1"] = (g["x1"] - bx) * s
                    t["y1"] = (g["y1"] - by) * s
                    t["x2"] = (g["x2"] - bx) * s
                    t["y2"] = (g["y2"] - by) * s
                elif kind in ("circle", "arc"):
                    xk = "x" if kind == "circle" else "rx"
                    yk = "y" if kind == "circle" else "ry"
                    wk = "w" if kind == "circle" else "rw"
                    hk = "h" if kind == "circle" else "rh"
                    t[xk] = (g[xk] - bx) * s
                    t[yk] = (g[yk] - by) * s
                    t[wk] = g[wk] * s
                    t[hk] = g[hk] * s
                elif kind == "ellipse_full":
                    t["pos_cx"] = (g["pos_cx"] - bx) * s
                    t["pos_cy"] = (g["pos_cy"] - by) * s
                    t["x"] = g["x"] * s; t["y"] = g["y"] * s
                    t["w"] = g["w"] * s; t["h"] = g["h"] * s
                elif kind == "path_points":
                    t["points"] = [((p[0] - bx) * s, (p[1] - by) * s)
                                   for p in g["points"]]
                elif kind == "text":
                    t["x"] = (g["x"] - bx) * s
                    t["y"] = (g["y"] - by) * s
                    if "size" in g:
                        t["size"] = g["size"] * s
                transformed.append(t)
            geom_list = transformed

        record = params["_record"] or Underlay(
            type=params.get("file_type", "dxf"), path=params["file_path"],
            x=params["x"], y=params["y"],
            colour=color.name(),
            line_weight=params.get("line_weight", UNDERLAY_LINE_WIDTH_PX),
            level=self.active_level,
            layout=params.get("layout", ""),
        )

        result = self._build_batched_underlay_group(geom_list, record)

        if result is None:
            progress.close()
            self._cleanup_dxf_worker()
            return

        group, all_layers = result
        group.setPos(params["x"], params["y"])

        _TYPE_LABELS = {"pdf": "PDF Underlay", "dxf": "DXF Underlay", "dwg": "DWG Underlay"}
        group.setData(0, _TYPE_LABELS.get(record.type, "DXF Underlay"))
        group.setData(5, _raw_geom)  # raw pre-transform geom for cache
        group.setData(6, not _cache_written)  # dirty until cached on save

        self._apply_underlay_display(group, record)
        self._apply_underlay_hidden_layers(group, record)
        self._attach_snap_index(group, geom_list, record)
        group.setData(2, all_layers)

        self.underlays.append((record, group))

        progress.close()
        self._cleanup_dxf_worker()

        # Clean up temp DWG->DXF conversion output (async-safe)
        dwg_cleanup = params.get("_dwg_cleanup_path")
        if dwg_cleanup:
            from .dwg_converter import cleanup_converted_dxf
            cleanup_converted_dxf(dwg_cleanup)

        self.underlaysChanged.emit()
        self.push_undo_state()

        self._show_status(f"Imported DXF: {params['file_path']}")

    @staticmethod
    def _build_pen_cache(geom_list: list[dict], line_width: float) -> dict:
        """Build a ``{hex_color: (QPen, QColor)}`` cache from geometry dicts."""
        cache: dict[str, tuple] = {}
        for g in geom_list:
            c = g.get("color")
            if c and c not in cache:
                qc = QColor(c)
                p = QPen(qc, line_width)
                p.setCosmetic(True)
                cache[c] = (p, qc)
        return cache

    @staticmethod
    def _append_geom_to_path(path: QPainterPath, g: dict):
        """Append a single geometry dict to a batched QPainterPath.

        Mirrors UnderlayImportDialog._append_geom_to_path — used for
        batched underlay rendering where one QPainterPath per layer
        replaces one QGraphicsItem per geometry.
        """
        kind = g.get("kind")
        if kind == "line":
            path.moveTo(g["x1"], g["y1"])
            path.lineTo(g["x2"], g["y2"])
        elif kind == "circle":
            path.addEllipse(g["x"], g["y"], g["w"], g["h"])
        elif kind == "arc":
            rect = QRectF(g["rx"], g["ry"], g["rw"], g["rh"])
            path.arcMoveTo(rect, g["start"])
            path.arcTo(rect, g["start"], g["span"])
        elif kind == "ellipse_full":
            path.addEllipse(
                g["pos_cx"] + g["x"], g["pos_cy"] + g["y"],
                g["w"], g["h"])
        elif kind == "path_points":
            pts = g["points"]
            if len(pts) < 2:
                return
            path.moveTo(pts[0][0], pts[0][1])
            for p in pts[1:]:
                path.lineTo(p[0], p[1])
            if g.get("closed") and len(pts) >= 3:
                path.closeSubpath()
        elif kind == "text":
            txt = g.get("text", "")
            if txt:
                f = QFont("Arial")
                f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                f.setPointSizeF(max(0.5, g.get("size", 6)))
                tx, ty = g["x"], g["y"]
                ha = g.get("halign", 0)
                va = g.get("valign", 3)
                lines = txt.split("\n")
                fm = QFontMetricsF(f)
                line_h = fm.height()
                total_h = line_h * len(lines)
                if va == 0:       # top
                    base_y = ty + fm.ascent()
                elif va == 1:     # middle
                    base_y = ty + fm.ascent() - total_h / 2
                elif va == 2:     # bottom
                    base_y = ty + fm.ascent() - total_h
                else:             # baseline (single-line default)
                    base_y = ty
                for i, line in enumerate(lines):
                    if not line.strip():
                        continue
                    lx = tx
                    if ha == 1:   # center
                        lx -= fm.horizontalAdvance(line) / 2
                    elif ha == 2: # right
                        lx -= fm.horizontalAdvance(line)
                    path.addText(lx, base_y + i * line_h, f, line)

    def _build_batched_underlay_group(
        self,
        geom_list: list[dict],
        record: Underlay,
    ) -> tuple[QGraphicsItemGroup, list[str]] | None:
        """Build a batched underlay group from geometry dicts.

        Instead of one QGraphicsItem per geometry (which freezes on large
        files), batches all geometry into one QPainterPath per DXF layer.
        Each layer gets up to two path items: one for stroked geometry
        (lines, arcs, circles, polylines) and one for filled text.

        Pens are per-layer and record-driven (spec §16.3): each layer's
        stroke item gets ``underlay_layer_pen(record, layer)`` (always
        cosmetic — constant on-screen width regardless of zoom or import
        scale); text items are NoPen with a brush in the layer's
        effective colour.

        Returns ``(group, sorted_layer_list)`` or ``None`` if no items.
        """
        # Group geometry by layer
        by_layer: dict[str, list[dict]] = {}
        for g in geom_list:
            layer = g.get("layer", "0")
            by_layer.setdefault(layer, []).append(g)

        items: list[QGraphicsItem] = []

        for layer, geoms in by_layer.items():
            geom_path = QPainterPath()
            text_path = QPainterPath()

            for g in geoms:
                if g.get("kind") == "text":
                    self._append_geom_to_path(text_path, g)
                else:
                    self._append_geom_to_path(geom_path, g)

            if not geom_path.isEmpty():
                item = QGraphicsPathItem(geom_path)
                item.setPen(underlay_layer_pen(record, layer))
                item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                item.setZValue(Z_UNDERLAY)
                item.setData(1, layer)  # layer tag for visibility toggling
                items.append(item)

            if not text_path.isEmpty():
                item = QGraphicsPathItem(text_path)
                item.setPen(QPen(Qt.PenStyle.NoPen))
                item.setBrush(QBrush(QColor(
                    record.effective_layer_colour(layer))))
                item.setZValue(Z_UNDERLAY)
                item.setData(1, layer)
                items.append(item)

        if not items:
            return None

        old_method = self.itemIndexMethod()
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        for item in items:
            self.addItem(item)
        group = self.createItemGroup(items)
        group.setZValue(Z_UNDERLAY)
        self.setItemIndexMethod(old_method)

        all_layers = sorted(by_layer.keys())
        return group, all_layers

    def _attach_snap_index(self, group: QGraphicsItemGroup,
                           geom_list: list[dict], record: Underlay):
        """Build a spatial snap index and attach it to the underlay group.

        The index stores geometry dicts for lazy snap queries by the snap
        engine, replacing invisible QGraphicsItems in the scene BSP.
        """
        from .underlay_snap_index import UnderlaySnapIndex
        index = UnderlaySnapIndex(geom_list, record.hidden_layers)
        group.setData(4, index)

    def _on_dxf_error(self, msg: str, progress: QProgressDialog):
        progress.close()
        self._show_status(f"DXF error: {msg}")
        self._cleanup_dxf_worker()

    def _cleanup_dxf_worker(self):
        if hasattr(self, "_dxf_worker") and self._dxf_worker is not None:
            self._dxf_worker.quit()
            self._dxf_worker.wait()
        self._dxf_worker = None
        self._dxf_progress = None
        self._dxf_import_params = None

    def import_pdf(self, file_path, dpi=150, page=0, x=0.0, y=0.0,
                   _record: Underlay = None, import_mode: str = "auto"):
        """Import a PDF page as an underlay.

        When *_record* is provided (reload / refresh-from-disk) and the
        original import used vector extraction (``import_mode`` is
        ``"vectors"`` or ``"auto"``), vectors are re-extracted from the
        PDF and rendered as QGraphicsItems — matching the quality of
        the original import-dialog placement.

        Falls back to raster rendering when vector extraction is
        unavailable or ``import_mode`` is ``"raster"``.
        """
        import os
        if not os.path.isfile(file_path):
            self._show_status(f"PDF not found: {file_path}")
            log.warning("PDF not found: %s", file_path)
            return

        # -----------------------------------------------------------------
        # Vector path — re-extract from PDF when reloading a vector import
        # -----------------------------------------------------------------
        effective_mode = _record.import_mode if _record else import_mode
        if effective_mode in ("vectors", "auto"):
            try:
                from .pdf_import_worker import extract_pdf_vectors_sync
                p = _record.page if _record else page
                geom_list, _layers = extract_pdf_vectors_sync(file_path, page=p)
            except Exception as exc:
                log.warning("PDF vector extraction failed, falling back to raster: %s", exc)
                geom_list = []

            if geom_list:
                self._import_pdf_vectors(
                    file_path, geom_list, x=x, y=y,
                    _record=_record, import_mode=effective_mode,
                    dpi=dpi, page=_record.page if _record else page,
                )
                return

        # -----------------------------------------------------------------
        # Raster fallback
        # -----------------------------------------------------------------
        pixmap = None

        # --- Strategy 1: PyMuPDF (fitz) — fast, synchronous, reliable ----
        try:
            import fitz
            doc = fitz.open(file_path)
            if page < 0 or page >= len(doc):
                doc.close()
                self._show_status(
                    f"Page {page} out of range (0–{len(doc)-1})")
                return
            pg = doc[page]
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = pg.get_pixmap(matrix=mat, alpha=False)
            qimg = QImage(pix.samples, pix.width, pix.height,
                          pix.stride, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg.copy())   # .copy() detaches from fitz buffer
            doc.close()
        except ImportError:
            pass  # fitz not installed — fall through to QPdfDocument
        except Exception as e:
            log.warning("fitz PDF render failed: %s", e)

        # --- Strategy 2: QPdfDocument (Qt built-in) ----------------------
        if pixmap is None:
            try:
                doc = QPdfDocument(self)
                err = doc.load(file_path)
                # Give Qt a chance to finish async loading if needed
                if doc.pageCount() == 0:
                    QApplication.processEvents()
                page_count = doc.pageCount()
                if page_count == 0:
                    raise RuntimeError(
                        f"QPdfDocument loaded 0 pages (load error: {err})")
                if page < 0 or page >= page_count:
                    raise IndexError(
                        f"Page {page} out of range (0–{page_count-1})")

                page_size = doc.pagePointSize(page)
                if not page_size.isValid():
                    raise RuntimeError("Invalid page size from PDF")

                width_px = int(page_size.width() * dpi / 72.0)
                height_px = int(page_size.height() * dpi / 72.0)

                options = QPdfDocumentRenderOptions()
                image = doc.render(page, QSize(width_px, height_px), options)
                if image.isNull():
                    raise RuntimeError("QPdfDocument.render() returned null")

                pixmap = QPixmap.fromImage(image)
            except Exception as e:
                self._show_status(f"Error importing PDF: {e}")
                log.warning("QPdfDocument PDF render failed: %s", e)
                return

        if pixmap is None or pixmap.isNull():
            self._show_status("Failed to render PDF page")
            return

        item = QGraphicsPixmapItem(pixmap)
        item.setZValue(Z_UNDERLAY)
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        # When reloading from a saved project (_record provided), always use
        # the stored position exactly.  For a fresh import with no explicit
        # position, centre the pixmap on the scene origin.
        if _record is not None:
            item.setPos(x, y)
        elif x != 0.0 or y != 0.0:
            item.setPos(x, y)
        else:
            item.setPos(-pixmap.width() / 2, -pixmap.height() / 2)
        item.setData(0, "PDF Underlay")
        self.addItem(item)

        record = _record or Underlay(
            type="pdf", path=file_path,
            x=item.pos().x(), y=item.pos().y(),
            dpi=dpi, page=page,
            level=self.active_level,
            import_mode=import_mode,
        )

        # Apply saved display settings
        self._apply_underlay_display(item, record)

        self.underlays.append((record, item))
        self.underlaysChanged.emit()
        self.push_undo_state()
        self._show_status(f"Imported PDF '{file_path}' page {page} at {dpi} DPI")

    def _import_pdf_vectors(self, file_path: str, geom_list: list[dict],
                            x: float = 0.0, y: float = 0.0,
                            _record: Underlay = None,
                            import_mode: str = "auto",
                            dpi: int = 150, page: int = 0):
        """Build vector QGraphicsItems from PDF geometry dicts.

        Mirrors the DXF reload path: apply stored import transform
        (scale + base-point shift), convert to QGraphicsItems via
        ``_build_batched_underlay_group()``, and register the underlay.
        """
        # Write geometry cache (raw, pre-transform)
        _cache_written = self._write_underlay_cache(
            file_path, geom_list, page=page,
            selected_layers=None,
            import_bounds=(_record.import_bounds
                           if _record is not None else None))

        # Snapshot raw geom for cache-on-save (before transform mutates)
        _raw_geom = geom_list

        # Apply import transform if reloading from a record with baked params
        if _record is not None and (_record.import_scale != 1.0
                                     or _record.import_base_x != 0.0
                                     or _record.import_base_y != 0.0):
            s = _record.import_scale
            bx, by = _record.import_base_x, _record.import_base_y
            transformed = []
            for g in geom_list:
                kind = g.get("kind")
                t = dict(g)
                if kind == "line":
                    t["x1"] = (g["x1"] - bx) * s
                    t["y1"] = (g["y1"] - by) * s
                    t["x2"] = (g["x2"] - bx) * s
                    t["y2"] = (g["y2"] - by) * s
                elif kind in ("circle", "arc"):
                    xk = "x" if kind == "circle" else "rx"
                    yk = "y" if kind == "circle" else "ry"
                    wk = "w" if kind == "circle" else "rw"
                    hk = "h" if kind == "circle" else "rh"
                    t[xk] = (g[xk] - bx) * s
                    t[yk] = (g[yk] - by) * s
                    t[wk] = g[wk] * s
                    t[hk] = g[hk] * s
                elif kind == "ellipse_full":
                    t["pos_cx"] = (g["pos_cx"] - bx) * s
                    t["pos_cy"] = (g["pos_cy"] - by) * s
                    t["x"] = g["x"] * s; t["y"] = g["y"] * s
                    t["w"] = g["w"] * s; t["h"] = g["h"] * s
                elif kind == "path_points":
                    t["points"] = [((p[0] - bx) * s, (p[1] - by) * s)
                                   for p in g["points"]]
                elif kind == "text":
                    t["x"] = (g["x"] - bx) * s
                    t["y"] = (g["y"] - by) * s
                    if "size" in g:
                        t["size"] = g["size"] * s
                transformed.append(t)
            geom_list = transformed

        record = _record or Underlay(
            type="pdf", path=file_path,
            x=x, y=y,
            dpi=dpi, page=page,
            level=self.active_level,
            import_mode=import_mode,
        )

        result = self._build_batched_underlay_group(geom_list, record)

        if result is None:
            log.warning("PDF vector extraction yielded 0 items for %s", file_path)
            return

        group, all_layers = result
        group.setPos(x, y)
        group.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        group.setData(0, "PDF Underlay")
        group.setData(5, _raw_geom)  # raw pre-transform geom for cache
        group.setData(6, not _cache_written)  # dirty until cached on save

        self._apply_underlay_display(group, record)
        self._apply_underlay_hidden_layers(group, record)
        self._attach_snap_index(group, geom_list, record)
        group.setData(2, all_layers)

        self.underlays.append((record, group))
        self.underlaysChanged.emit()
        self.push_undo_state()

        self._show_status(
            f"Imported PDF '{file_path}' page {page} as vectors")

    # -------------------------------------------------------------------------
    # UNDERLAYS — MANAGEMENT

    def _apply_underlay_display(self, item: QGraphicsItem, record: Underlay):
        """Apply transform origin, scale, rotation, opacity, visibility, and lock state."""
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setScale(record.scale)
        item.setRotation(record.rotation)
        item.setOpacity(record.opacity)
        if not record.visible:
            item.setVisible(False)
        if record.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def _apply_underlay_hidden_layers(self, item: QGraphicsItem,
                                       data: Underlay):
        """Hide child items whose source layer is in data.hidden_layers.

        Stale layer names (no longer in the file) are silently dropped.
        """
        if not data.hidden_layers or not hasattr(item, "childItems"):
            return
        actual_layers = set()
        for child in item.childItems():
            layer_name = child.data(1)
            if layer_name is not None:
                actual_layers.add(layer_name)
        data.hidden_layers = [
            ln for ln in data.hidden_layers if ln in actual_layers
        ]
        hidden_set = set(data.hidden_layers)
        for child in item.childItems():
            layer_name = child.data(1)
            if layer_name in hidden_set:
                child.setVisible(False)

    def _create_underlay_placeholder(self, data: Underlay) -> QGraphicsItem:
        """Create a placeholder rect for a missing underlay file."""
        rect = QGraphicsRectItem(0, 0, 200, 150)
        pen = QPen(QColor("#ff0000"), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        rect.setPen(pen)
        rect.setBrush(QBrush(QColor(255, 0, 0, 30)))
        rect.setPos(data.x, data.y)
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        rect.setData(0, "missing_underlay")

        filename = os.path.basename(data.path)
        label = QGraphicsSimpleTextItem(
            f"{filename}\nMissing \u2014 right-click to relink", rect)
        font = QFont()
        font.setPointSize(8)
        label.setFont(font)
        label.setBrush(QBrush(QColor("#ff0000")))

        self.addItem(rect)
        self.underlays.append((data, rect))
        self.underlaysChanged.emit()
        return rect

    def find_underlay_for_item(self, item: QGraphicsItem):
        """Return the (Underlay, QGraphicsItem) tuple for a scene item, or None."""
        for data, scene_item in self.underlays:
            if scene_item is item:
                return data, scene_item
        return None

    def remove_underlay(self, data: Underlay, item: QGraphicsItem):
        """Remove an underlay from the scene and the tracking list."""
        pair = (data, item)
        if pair in self.underlays:
            self.underlays.remove(pair)
        if item.scene() is self:
            if isinstance(item, QGraphicsItemGroup):
                # destroyItemGroup re-parents children back to the scene rather
                # than deleting them, so we must remove each child first.
                for child in item.childItems():
                    self.removeItem(child)
                self.destroyItemGroup(item)
            else:
                self.removeItem(item)
        self.underlaysChanged.emit()
        self._show_status(f"Removed underlay: {data.path}")

    def refresh_underlay(self, data: Underlay, item: QGraphicsItem):
        """Re-import an underlay from disk, preserving position/scale/rotation/opacity."""
        # Sync current transform state back to record
        data.x = item.scenePos().x()
        data.y = item.scenePos().y()
        data.scale = item.scale()
        data.rotation = item.rotation()
        data.opacity = item.opacity()

        # Check file exists before re-import
        if not os.path.exists(data.path):
            # Replace with placeholder
            if item.scene() is self:
                self.removeItem(item)
            # Remove old entry from underlays list
            old_entries = [(i, d) for i, (d, it) in enumerate(self.underlays) if d is data]
            for i, _ in reversed(old_entries):
                self.underlays.pop(i)
            self._create_underlay_placeholder(data)
            self._show_status(f"Missing underlay: {data.path}")
            return

        # Remove old entry from underlays list BEFORE re-import.
        # DXF import is async (worker thread) — if we clean up after,
        # the duplicate check races with _on_dxf_finished appending.
        self.underlays = [(d, it) for d, it in self.underlays if d is not data]
        if item.scene() is self:
            self.removeItem(item)

        # Re-import (appends a fresh entry to self.underlays)
        if data.type == "pdf":
            self.import_pdf(
                data.path, dpi=data.dpi, page=data.page,
                x=data.x, y=data.y, _record=data,
                import_mode=data.import_mode,
            )
        elif data.type in ("dxf", "dwg"):
            dxf_path = data.path
            if data.type == "dwg":
                from .dwg_converter import (
                    find_oda_converter, convert_dwg_to_dxf,
                )
                oda = find_oda_converter()
                if oda is None:
                    self._create_underlay_placeholder(data)
                    self._show_status("DWG refresh failed: ODA File Converter not found")
                    return
                proj = getattr(self, "_project_path", None)
                proj_dir = os.path.dirname(proj) if proj else None
                converted = convert_dwg_to_dxf(oda, data.path, project_dir=proj_dir)
                if converted is None:
                    self._create_underlay_placeholder(data)
                    self._show_status(f"DWG refresh failed: conversion error for {data.path}")
                    return
                dxf_path = converted

            self.import_dxf(
                dxf_path, color=QColor(data.colour),
                line_weight=data.line_weight,
                x=data.x, y=data.y, layers=data.selected_layers,
                _record=data,
                layout=data.layout,
                skip_sanitize=(data.type == "dwg"),  # ODA output is clean
            )

            # Store DWG metadata on import params for async cleanup
            if data.type == "dwg" and hasattr(self, '_dxf_import_params') and self._dxf_import_params:
                self._dxf_import_params["_dwg_source_path"] = data.path
                self._dxf_import_params["_dwg_cleanup_path"] = dxf_path
                self._dxf_import_params["layout"] = data.layout

        self._show_status(f"Refreshed underlay: {data.path}")

    def refresh_all_underlays(self):
        """Re-import every underlay from disk."""
        # Take a snapshot since refresh modifies the list
        snapshot = list(self.underlays)
        for data, item in snapshot:
            self.refresh_underlay(data, item)

    def repen_underlay(self, record: Underlay):
        """Re-apply effective per-layer pens/brushes + opacity in place (§16.3).

        Never rebuilds the group (callable from any context, incl. DM live
        preview). Guards deleted C++ objects like the §7.2 pass.
        """
        for data, group in getattr(self, "underlays", []):
            if data is not record or group is None:
                continue
            try:
                children = group.childItems()
            except RuntimeError:
                return
            for child in children:
                layer = child.data(1)
                if layer is None or not isinstance(child, QGraphicsPathItem):
                    continue
                if child.pen().style() == Qt.PenStyle.NoPen:
                    # text batch: colour rides the brush fill
                    child.setBrush(QBrush(QColor(
                        record.effective_layer_colour(layer))))
                else:
                    child.setPen(underlay_layer_pen(record, layer))
            group.setOpacity(record.opacity)
            return

    def set_underlay_layer_hidden(self, record: Underlay, group,
                                  layer_name: str, hidden: bool):
        """Single choke point for hidden_layers edits (§16.6 — one state,
        two surfaces: browser tree and DM tab both route through here).
        No push_undo_state here — callers decide (browser pushes, DM never)."""
        if hidden and layer_name not in record.hidden_layers:
            record.hidden_layers.append(layer_name)
        elif not hidden and layer_name in record.hidden_layers:
            record.hidden_layers.remove(layer_name)
        else:
            return
        try:
            for child in group.childItems():
                if child.data(1) == layer_name:
                    child.setVisible(not hidden)
        except RuntimeError:
            return
        self.underlaysChanged.emit()

    # -------------------------------------------------------------------------
    # UNDO / REDO

    def _capture_network(self) -> dict:
        """Serialize nodes/pipes/annotations to a dict (no underlays/scale)."""
        node_list = list(self.sprinkler_system.nodes)
        node_id = {n: i for i, n in enumerate(node_list)}
        nodes_data = []
        for node in node_list:
            undo_node = {
                "id":             node_id[node],
                "x":              node.scenePos().x(),
                "y":              node.scenePos().y(),
                "elevation":      node.z_pos,
                "sprinkler":      node.sprinkler.get_properties() if node.has_sprinkler() else None,
                "level":          getattr(node, "level", DEFAULT_LEVEL),
                "ceiling_level":  getattr(node, "ceiling_level", DEFAULT_LEVEL),
                "ceiling_offset_mm": getattr(node, "ceiling_offset", DEFAULT_CEILING_OFFSET_MM),
                "room_name":     getattr(node, "_room_name", ""),
            }
            node_ovr = getattr(node, "_display_overrides", {})
            if node_ovr:
                undo_node["display_overrides"] = node_ovr
            if node.has_sprinkler():
                spr_ovr = getattr(node.sprinkler, "_display_overrides", {})
                if spr_ovr:
                    undo_node["sprinkler_display_overrides"] = spr_ovr
            fit_ovr = getattr(node.fitting, "_display_overrides", {}) if node.has_fitting() else {}
            if fit_ovr:
                undo_node["fitting_display_overrides"] = fit_ovr
            nodes_data.append(undo_node)
        pipes_data = []
        for pipe in self.sprinkler_system.pipes:
            if pipe.node1 is None or pipe.node2 is None:
                continue
            if pipe.node1 not in node_id or pipe.node2 not in node_id:
                continue
            undo_pipe = {
                "node1_id":   node_id[pipe.node1],
                "node2_id":   node_id[pipe.node2],
                "properties": {k: v["value"] for k, v in pipe.get_properties().items()},
                "level":     getattr(pipe, "level", DEFAULT_LEVEL),
            }
            pipe_ovr = getattr(pipe, "_display_overrides", {})
            if pipe_ovr:
                undo_pipe["display_overrides"] = pipe_ovr
            pipes_data.append(undo_pipe)
        annotations_data = []
        for dim in self.annotations.dimensions:
            annotations_data.append({
                "type": "dimension",
                "p1":   [dim._p1.x(), dim._p1.y()],
                "p2":   [dim._p2.x(), dim._p2.y()],
                "offset_dist": getattr(dim, "_offset_dist", 10),
                "witness_ext_override": getattr(dim, "_witness_ext_override", None),
                "properties": {k: v["value"] for k, v in dim.get_properties().items()},
                "level":     getattr(dim, "level", DEFAULT_LEVEL),
            })
        for note in self.annotations.notes:
            annotations_data.append({
                "type": "note",
                "x":    note.scenePos().x(),
                "y":    note.scenePos().y(),
                "text_width": note.textWidth(),
                "properties": {k: v["value"] for k, v in note.get_properties().items()},
                "level":     getattr(note, "level", DEFAULT_LEVEL),
            })
        ws = self.water_supply_node
        ws_data = None
        if ws is not None:
            ws_data = {
                "x":          ws.pos().x(),
                "y":          ws.pos().y(),
                "properties": {k: v["value"] for k, v in ws.get_properties().items()},
            }
            ws_ovr = getattr(ws, "_display_overrides", {})
            if ws_ovr:
                ws_data["display_overrides"] = ws_ovr
        # Design areas
        da_data = []
        for da in self.design_areas:
            spr_nids = [node_id[s.node] for s in da.sprinklers
                        if s.node and s.node in node_id]
            da_data.append({
                "sprinkler_node_ids": spr_nids,
                # raw stored props — get_properties() adds synthesized display rows
                "properties": {k: v["value"] for k, v in da._properties.items()},
                "is_active": da is self.active_design_area,
                "level": da.level,
                "badge_offset": (list(da.badge_offset())
                                 if da._badge_user_moved else None),
            })
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
            "floor_slabs":        [fs.to_dict() for fs in self._floor_slabs],
            "roofs":              [r.to_dict()  for r in self._roofs],
            "rooms":              [r.to_dict()  for r in self._rooms],
            "constraints":        self._capture_constraints(),
        }

    def _capture_constraints(self) -> list[dict]:
        """Serialize constraints for undo/save, using geometry-list index IDs."""
        all_geom = self._all_geometry_items()
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

            id_to_node: dict[int, Node] = {}
            for entry in state.get("nodes", []):
                node = Node(entry["x"], entry["y"])
                self.addItem(node)
                self.sprinkler_system.add_node(node)
                id_to_node[entry["id"]] = node
                node._display_overrides = entry.get("display_overrides", {})
                if entry.get("sprinkler"):
                    template = Sprinkler(None)
                    for key, value in entry["sprinkler"].items():
                        if isinstance(value, dict):
                            template.set_property(key, value["value"])
                        else:
                            template.set_property(key, value)
                    self.add_sprinkler(node, template)
                    node.sprinkler._display_overrides = entry.get(
                        "sprinkler_display_overrides", {})
                node._fitting_display_overrides_pending = entry.get(
                    "fitting_display_overrides", {})
                node.level = entry.get("level", DEFAULT_LEVEL)
                node._room_name = entry.get("room_name", "")
                node.ceiling_level = entry.get("ceiling_level", node.level)
                if "ceiling_offset_mm" in entry:
                    node.ceiling_offset = entry["ceiling_offset_mm"]
                else:
                    node.ceiling_offset = entry.get("ceiling_offset", -2.0) * 25.4  # old inches → mm
                node._properties["Ceiling Level"]["value"] = node.ceiling_level
                node._properties["Ceiling Offset"]["value"] = str(node.ceiling_offset)
                if self._level_manager:
                    lvl = self._level_manager.get(node.ceiling_level)
                    if lvl:
                        node.z_pos = lvl.elevation + node.ceiling_offset
                    else:
                        node.z_pos = entry.get("elevation", 0)
                else:
                    node.z_pos = entry.get("elevation", 0)

            for entry in state.get("pipes", []):
                n1 = id_to_node.get(entry["node1_id"])
                n2 = id_to_node.get(entry["node2_id"])
                if n1 and n2:
                    pipe = Pipe(n1, n2)
                    self.sprinkler_system.add_pipe(pipe)
                    self.addItem(pipe)
                    pipe.update_label()
                    for key, value in entry.get("properties", {}).items():
                        pipe.set_property(key, value)
                    # Old files without Line Type: auto-assign based on diameter
                    props = entry.get("properties", {})
                    if "Line Type" not in props:
                        dia = props.get("Diameter", "1\"Ø")
                        pipe._properties["Line Type"]["value"] = (
                            "Main" if dia in Pipe._MAIN_DIAMETERS else "Branch"
                        )
                        pipe.set_pipe_display()
                    pipe.level = entry.get("level", DEFAULT_LEVEL)
                    pipe._display_overrides = entry.get("display_overrides", {})
                    apply_category_defaults(pipe)

            for node in id_to_node.values():
                node.fitting.update()
                pending = getattr(node, "_fitting_display_overrides_pending", {})
                if pending:
                    node.fitting._display_overrides = pending
                    del node._fitting_display_overrides_pending
                # Apply DM colours without re-aligning (align was done by update)
                self._apply_fitting_dm_colors(node.fitting)

            for entry in state.get("annotations", []):
                ann_type = entry.get("type")
                if ann_type == "dimension":
                    p1 = QPointF(entry["p1"][0], entry["p1"][1])
                    p2 = QPointF(entry["p2"][0], entry["p2"][1])
                    dim = DimensionAnnotation(p1, p2)
                    dim._offset_dist = entry.get("offset_dist", 10)
                    dim._witness_ext_override = entry.get("witness_ext_override", None)
                    self.addItem(dim)
                    self.annotations.add_dimension(dim)
                    for key, value in entry.get("properties", {}).items():
                        dim.set_property(key, value)
                    dim.update_geometry()
                    dim.level = entry.get("level", DEFAULT_LEVEL)
                elif ann_type == "note":
                    note = NoteAnnotation(x=entry["x"], y=entry["y"])
                    self.addItem(note)
                    self.annotations.add_note(note)
                    for key, value in entry.get("properties", {}).items():
                        note.set_property(key, value)
                    note.level = entry.get("level", DEFAULT_LEVEL)

            # Restore water supply
            ws_data = state.get("water_supply")
            if ws_data:
                ws = WaterSupply(ws_data["x"], ws_data["y"])
                self.addItem(ws)
                self.water_supply_node = ws
                self.sprinkler_system.supply_node = ws
                for key, value in ws_data.get("properties", {}).items():
                    ws.set_property(key, value)
                ws._display_overrides = ws_data.get("display_overrides", {})

            # Restore design areas
            for da_entry in state.get("design_areas", []):
                spr_nids = da_entry.get("sprinkler_node_ids", [])
                sprs = [id_to_node[nid].sprinkler for nid in spr_nids
                        if nid in id_to_node and id_to_node[nid].has_sprinkler()]
                da = DesignArea(sprs)
                lvl = da_entry.get("level")
                if not lvl:
                    # Pre-2026-07 save: backfill from member sprinklers
                    lvl = next((s.node.level for s in sprs if s.node),
                               DEFAULT_LEVEL)
                da.level = lvl
                for key, value in da_entry.get("properties", {}).items():
                    da.set_property(key, value)
                self.addItem(da)
                apply_category_defaults(da)
                self.design_areas.append(da)
                if da_entry.get("is_active", False):
                    self.active_design_area = da
                bo = da_entry.get("badge_offset")
                if bo is not None:
                    da.set_badge_offset(QPointF(bo[0], bo[1]))
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

            # ── Design-area tiles (now that walls & rooms exist) ──────────
            for da in self.design_areas:
                da.compute_area(self.scale_manager)

            # ── Constraints ───────────────────────────────────────────────
            all_geom = self._all_geometry_items()
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
        self.sceneModified.emit()

    def undo(self):
        """Restore the previous network state."""
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
        """Run the Hazen-Williams solver and store results for overlay display."""
        from .hydraulic_solver import HydraulicSolver
        solver = HydraulicSolver(self.sprinkler_system, self.scale_manager)
        result = solver.solve(design_sprinklers=design_sprinklers)
        # Prepend design-area spacing violations — the report renders
        # messages at the top, so listing violations lead the output.
        da = self.active_design_area
        if da is not None and getattr(da, "spacing_warnings", None):
            result.messages[:0] = da.spacing_warnings
        if da is not None:
            crit = da.effective_criteria()
            if crit.warnings:
                result.messages[:0] = crit.warnings
            remote_psi = min(
                (result.required_node_pressures.get(s.node, 0.0)
                 for s in da.sprinklers if s.node), default=0.0)
            da.set_hydraulic_snapshot({
                "total_demand_gpm": result.total_demand,
                "demand_psi": result.required_pressure,
                "remote_head_psi": remote_psi,
                "sprinklers_calculated": len(design_sprinklers or []),
                "hose_gpm": getattr(result, "hose_stream_gpm", 0.0),
            } if (result.passed or result.node_pressures) else None)
        self.hydraulic_result = result
        self._supply_network_node = getattr(solver, '_supply_node', None)
        # Refresh all pipe labels and node badges
        for pipe in self.sprinkler_system.pipes:
            pipe.update_label()
            pipe.update()
        from .hydraulic_node_badge import best_position_for_node

        # Group major nodes by 2D scene position to detect overlaps (vertical drops)
        pos_groups: dict[tuple, list] = {}
        for node in self.sprinkler_system.nodes:
            node.remove_hydraulic_badge()
            label = result.node_labels.get(node) if hasattr(result, 'node_labels') else None
            # Only create badges for major nodes (purely numeric labels)
            if label is not None and label.isdigit():
                sp = node.scenePos()
                key = (round(sp.x(), 0), round(sp.y(), 0))
                pos_groups.setdefault(key, []).append(node)

        for nodes_at_pos in pos_groups.values():
            # All nodes at this 2D position share auto-position, stack vertically
            pos_label = best_position_for_node(nodes_at_pos[0])
            for stack_idx, node in enumerate(nodes_at_pos):
                nn = result.node_numbers[node]
                p_actual = result.node_pressures.get(node, 0.0)
                p_required = result.required_node_pressures.get(node, 0.0)
                q_out = 0.0
                if node.has_sprinkler():
                    try:
                        k = float(node.sprinkler._properties.get(
                            "K-Factor", {}).get("value", 5.6))
                    except (ValueError, TypeError):
                        k = 5.6
                    q_out = k * math.sqrt(max(p_actual, 0.0))
                q_total = 0.0
                for pipe in node.pipes:
                    pf = abs(result.pipe_flows.get(pipe, 0.0))
                    if pf > q_total:
                        q_total = pf
                label = result.node_labels.get(node, str(nn)) if hasattr(result, 'node_labels') else str(nn)
                node.create_hydraulic_badge(nn, p_actual, p_required,
                                            q_out, q_total,
                                            position=pos_label,
                                            stack_index=stack_idx,
                                            stack_total=len(nodes_at_pos),
                                            node_label=label)

        for node in self.sprinkler_system.nodes:
            node.update()
        return result

    def clear_hydraulics(self):
        """Remove the hydraulic results overlay."""
        self.hydraulic_result = None
        for pipe in self.sprinkler_system.pipes:
            pipe.update_label()
            pipe.update()
        for node in self.sprinkler_system.nodes:
            node.remove_hydraulic_badge()
            node.update()

    def set_coverage_overlay(self, visible: bool):
        """Show or hide translucent coverage circles on all sprinkler nodes."""
        Node._coverage_visible = visible
        for node in self.sprinkler_system.nodes:
            node.prepareGeometryChange()
            node.update()

    # -------------------------------------------------------------------------
    # GEOMETRY HELPERS

    def get_snapped_position(self, x, y):
        grid = 1
        return QPointF(round(x / grid) * grid, round(y / grid) * grid)

    def _collect_alignment_refs(self, cursor=None, tol=None):
        """Collect alignment reference features from the scene's alignment
        providers (gridlines + walls). The InferenceEngine stays generic;
        Model_Space supplies candidates from its own entity collections.

        Args:
            cursor: Optional QPointF scene position of the current cursor.
                When provided together with *tol*, walls are spatially filtered
                to those whose bounding box intersects a (2*tol x 2*tol) rect
                centred on *cursor*, using the scene BSP index.
            tol: Optional float tolerance radius (scene units). Required when
                *cursor* is provided to enable the spatial filter.

        Future providers are added by iterating their own collections here,
        NOT by changing the inference engine.  Self-exclusion is applied via
        source_id so the active item does not snap to itself.
        """
        refs = []
        exclude_id = (id(self._inference_active_item)
                      if self._inference_active_item is not None else None)
        exclude_ids = self._inference_exclude_ids
        for gl in self._gridlines:                       # small list — direct
            for f in gl.alignment_reference_points():
                if f.source_id != exclude_id and f.source_id not in exclude_ids:
                    refs.append(f)
        # Walls can be numerous (imports) — spatial-filter to the cursor rect
        # via the scene BSP index (NOT sceneBoundingRect, NOT a full self._walls scan).
        if cursor is not None and tol:
            rect = QRectF(cursor.x() - tol, cursor.y() - tol, 2 * tol, 2 * tol)
            for it in self.items(rect):
                if isinstance(it, WallSegment):
                    for f in it.alignment_reference_points():
                        if f.source_id != exclude_id and f.source_id not in exclude_ids:
                            refs.append(f)
        return refs

    def get_effective_position(self, scene_pos: QPointF) -> QPointF:
        """Return best-fit cursor position: OSNAP > underlay snap > grid snap."""
        # Design-area picking snaps to sprinkler centres ONLY: general
        # OSNAP/underlay/grid snapping would drag clicks onto gridlines and
        # walls, but sprinkler node centres still snap (with a marker) so
        # picks have a visible target.
        if self.mode == "design_area":
            active = getattr(self, "active_level", DEFAULT_LEVEL)
            view_scale = (self.views()[0].transform().m11()
                          if self.views() else 1.0)
            tol = DESIGN_AREA_PICK_PX / max(view_scale, 1e-9)
            best_node = None
            best_d = tol
            for spr in self.sprinkler_system.sprinklers:
                if not spr.node:
                    continue
                if getattr(spr.node, "level", DEFAULT_LEVEL) != active:
                    continue
                d = spr.node.distance_to(scene_pos.x(), scene_pos.y())
                if d < best_d:
                    best_d = d
                    best_node = spr.node
            if best_node is not None:
                pt = QPointF(best_node.scenePos())
                self._snap_result = OsnapResult(point=pt, snap_type="center")
                self._inference_result = None
                return pt
            self._snap_result = None
            self._inference_result = None
            return QPointF(scene_pos)

        # OSNAP takes highest priority (disabled when no mode or select mode,
        # but enabled during grip-drag even in select mode)
        if (self._osnap_enabled
                and self.mode is not None
                and (self.mode != "select" or self._grip_dragging)):
            exclude = self._grip_item if self._grip_dragging else None
            views = self.views()
            if views:
                result = self._snap_engine.find(
                    scene_pos, self, views[0].transform(), exclude=exclude)
                self._snap_result = result
                if result is not None:
                    self._inference_result = None
                    return result.point
            else:
                self._snap_result = None
        else:
            self._snap_result = None

        # Underlay snap
        if self._snap_to_underlay:
            snap_pt = self.find_snap_point(scene_pos)
            if snap_pt is not None:
                self._inference_result = None
                return snap_pt

        # ── Inferred alignment guides (weak snap, below OSNAP) ────────────
        if self._inference_enabled and self._inference_active_item is not None:
            views = self.views()
            if views:
                view = views[0]
                scale = max(abs(view.transform().m11()), 1e-9)
                tol = INFERENCE_TOL_PX / scale
                refs = self._collect_alignment_refs(scene_pos, tol)
                res = self._inference_engine.resolve(
                    (scene_pos.x(), scene_pos.y()), refs, tol)
                self._inference_result = res  # stored even when "free" (Task 3 reads it)
                if res.priority != "free":
                    return QPointF(res.snapped[0], res.snapped[1])
                # "free" — fall through to grid snap (no position change)
        else:
            self._inference_result = None
        return self.get_snapped_position(scene_pos.x(), scene_pos.y())

    def toggle_osnap(self, enabled: bool | None = None):
        """Toggle or explicitly set OSNAP.  Called from F3 shortcut and
        the status bar OSNAP indicator."""
        if enabled is None:
            self._osnap_enabled = not self._osnap_enabled
        else:
            self._osnap_enabled = bool(enabled)
        self._snap_engine.enabled = self._osnap_enabled
        self._snap_result = None
        # Refresh foreground overlay
        for v in self.views():
            v.viewport().update()
        self.osnapToggled.emit(self._osnap_enabled)

    def set_inference_enabled(self, enabled: bool | None = None):
        """Toggle or set alignment inference. Mirrors toggle_osnap()."""
        if enabled is None:
            self._inference_enabled = not self._inference_enabled
        else:
            self._inference_enabled = bool(enabled)
        self._inference_result = None
        for v in self.views():
            v.viewport().update()
        self.inferenceToggled.emit(self._inference_enabled)

    def find_snap_point(self, pos: QPointF) -> QPointF | None:
        """Find the nearest DXF underlay snap point within tolerance."""
        sm = self.scale_manager
        tolerance = sm.paper_to_scene(2.0) if sm.is_calibrated else 15.0
        search_rect = QRectF(pos.x() - tolerance, pos.y() - tolerance,
                             tolerance * 2, tolerance * 2)
        best_dist = tolerance
        best_pt = None
        for item in self.items(search_rect):
            parent = item.parentItem()
            if parent is None or not isinstance(parent, QGraphicsItemGroup):
                continue
            for pt in self._item_snap_points(item):
                d = math.hypot(pos.x() - pt.x(), pos.y() - pt.y())
                if d < best_dist:
                    best_dist = d
                    best_pt = pt
        return best_pt

    def _item_snap_points(self, item) -> list:
        """Return scene-coordinate snap points for a QGraphicsItem."""
        pts = []
        if isinstance(item, QGraphicsLineItem):
            line = item.line()
            pts.append(item.mapToScene(line.p1()))
            pts.append(item.mapToScene(line.p2()))
            pts.append(item.mapToScene(
                QPointF((line.x1() + line.x2()) / 2, (line.y1() + line.y2()) / 2)
            ))
        elif isinstance(item, QGraphicsEllipseItem):
            pts.append(item.mapToScene(item.boundingRect().center()))
        elif isinstance(item, QGraphicsPathItem):
            path = item.path()
            for i in range(min(path.elementCount(), 256)):   # cap to avoid spam on splines
                elem = path.elementAt(i)
                pts.append(item.mapToScene(QPointF(elem.x, elem.y)))
        return pts

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
        if self.mode == "draw_arc":
            return self._arc_schema_for_step()
        if self.mode == "draw_rectangle":
            return self._rectangle_schema_for_step()
        if self.mode == "polygon":
            return self._polygon_schema_for_step()
        if self.mode == "wall":
            return self._wall_schema_for_primitive()
        key = self._SCHEMA_FOR_MODE.get(self.mode)
        return SCHEMAS.get(key) if key else None

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

    def get_resolved_point(self) -> "QPointF | None":
        """Return the last point published by ``publish_placement_state``.

        This is the *constrained* position actually shown on screen, which is
        what the HUD seeds from.  Distinct from ``_last_scene_pos``, which
        holds the raw cursor and so can disagree with the preview whenever a
        constraint (Ctrl, 45° snap, inference) is active.

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
        constraining its position (OSNAP → inference → Ctrl → 45° snap).  This
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
            # rectangle about its stored pivot — so dispatch to the matching
            # angle helper (both share the same Y-up formula).
            point = self.get_resolved_point()
            if point is None:
                return {"Angle": 0.0}
            if self.mode == "polygon":
                return {"Angle": self._polygon_rotation_angle_to(point)}
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
        if self.apply_dynamic_input(geometry):
            # An applier may have torn the HUD down itself (e.g. by calling
            # set_mode); end_dynamic_input is a no-op in that case.
            self.end_dynamic_input()
        elif hud is not None and hud is self.dynamic_input:
            hud.reject_commit()

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

    def _ensure_underlay_caches(self, project_path: str):
        """Ensure every underlay has a cache entry.

        Called on save.  Reads the raw geometry stored on each group's
        ``data(5)`` — this is the exact geometry that was imported
        (including area selection filtering), avoiding expensive
        re-extraction from the source file.

        The JSON write is skipped when the geometry is unchanged since
        the last write (``data(6)`` dirty flag is falsy) AND the cache
        file already exists — serialising hundreds of thousands of geoms
        on every Ctrl+S froze the UI for seconds.  The existence check
        keeps Save-As (new cache directory) and externally-deleted cache
        files self-healing.
        """
        from .underlay_cache import cache_dir_for_project, write_cache
        cache_dir = cache_dir_for_project(project_path)
        for record, item in self.underlays:
            if item is None or not os.path.isfile(record.path):
                continue
            key = record.cache_key()
            if (not item.data(6)
                    and os.path.isfile(os.path.join(cache_dir, key))):
                continue
            geom_list = item.data(5)
            if not geom_list:
                continue
            try:
                source_mtime = os.path.getmtime(record.path)
                write_cache(cache_dir, key, geom_list,
                            source_mtime=source_mtime)
            except OSError:
                continue  # non-fatal — cache is an optimisation
            item.setData(6, False)

    def _load_underlay_from_cache(self, record, source_mtime):
        """Try to load an underlay from the geometry cache.

        Returns True if the underlay was loaded from a fresh cache entry,
        False if the caller should fall back to async parsing (cache
        stale, missing, or project never saved).
        """
        project_path = getattr(self, "_project_path", None)
        if not project_path:
            return False

        from .underlay_cache import cache_dir_for_project, read_cache
        cache_dir = cache_dir_for_project(project_path)
        key = record.cache_key()

        geom_list = read_cache(cache_dir, key, source_mtime=source_mtime)
        if geom_list is None:
            # Cache stale or missing — fall back to the async import path
            # (scene_io load) rather than re-extracting synchronously on
            # the GUI thread.  The async path handles _record / layout /
            # import_bounds and rewrites the cache when it finishes.
            return False

        # Snapshot raw geom for cache-on-save
        _raw_geom = geom_list

        # Apply import transform (same logic as _on_dxf_finished reload path)
        if (record.import_scale != 1.0
                or record.import_base_x != 0.0
                or record.import_base_y != 0.0):
            s = record.import_scale
            bx, by = record.import_base_x, record.import_base_y
            transformed = []
            for g in geom_list:
                kind = g.get("kind")
                t = dict(g)
                if kind == "line":
                    t["x1"] = (g["x1"] - bx) * s
                    t["y1"] = (g["y1"] - by) * s
                    t["x2"] = (g["x2"] - bx) * s
                    t["y2"] = (g["y2"] - by) * s
                elif kind in ("circle", "arc"):
                    xk = "x" if kind == "circle" else "rx"
                    yk = "y" if kind == "circle" else "ry"
                    wk = "w" if kind == "circle" else "rw"
                    hk = "h" if kind == "circle" else "rh"
                    t[xk] = (g[xk] - bx) * s
                    t[yk] = (g[yk] - by) * s
                    t[wk] = g[wk] * s
                    t[hk] = g[hk] * s
                elif kind == "ellipse_full":
                    t["pos_cx"] = (g["pos_cx"] - bx) * s
                    t["pos_cy"] = (g["pos_cy"] - by) * s
                    t["x"] = g["x"] * s
                    t["y"] = g["y"] * s
                    t["w"] = g["w"] * s
                    t["h"] = g["h"] * s
                elif kind == "path_points":
                    t["points"] = [((p[0] - bx) * s, (p[1] - by) * s)
                                   for p in g["points"]]
                elif kind == "text":
                    t["x"] = (g["x"] - bx) * s
                    t["y"] = (g["y"] - by) * s
                    if "size" in g:
                        t["size"] = g["size"] * s
                transformed.append(t)
            geom_list = transformed

        # Build batched render items (same as _commit_place_import)
        result = self._build_batched_underlay_group(geom_list, record)
        if result is None:
            return False

        group, all_layers = result
        group.setPos(record.x, record.y)
        _TYPE_LABELS = {"pdf": "PDF Underlay", "dxf": "DXF Underlay", "dwg": "DWG Underlay"}
        group.setData(0, _TYPE_LABELS.get(record.type, "DXF Underlay"))
        group.setData(2, all_layers)
        group.setData(5, _raw_geom)  # raw pre-transform geom for cache
        group.setData(6, False)  # geometry came straight from the cache
        if source_mtime is None:
            group.setData(3, "source_missing")

        self._apply_underlay_display(group, record)
        self._apply_underlay_hidden_layers(group, record)
        self._attach_snap_index(group, geom_list, record)
        self.underlays.append((record, group))

        return True

    def _write_underlay_cache(self, source_path: str, geom_list: list[dict],
                              page: int = 0,
                              selected_layers: list[str] | None = None,
                              layout: str = "",
                              import_bounds: list[float] | None = None,
                              ) -> bool:
        """Write geometry dicts to the project cache directory.

        No-op if the project has not been saved yet (no project path).

        Returns:
            True if the cache entry was written — callers use this to
            decide whether the group's dirty flag (``data(6)``) is set.
        """
        project_path = getattr(self, "_project_path", None)
        if not project_path:
            return False
        try:
            source_mtime = os.path.getmtime(source_path)
        except OSError:
            return False
        from .underlay_cache import cache_dir_for_project, compute_cache_key, write_cache
        cache_dir = cache_dir_for_project(project_path)
        key = compute_cache_key(source_path, page=page,
                                selected_layers=selected_layers,
                                layout=layout,
                                import_bounds=import_bounds)
        try:
            write_cache(cache_dir, key, geom_list, source_mtime=source_mtime)
        except OSError:
            return False  # non-fatal — cache is an optimisation
        return True

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
        if self.mode == "pipe" and len(self._pipe_tab_candidates) > 1:
            self._pipe_tab_index = (
                (self._pipe_tab_index + 1) % len(self._pipe_tab_candidates))
            self._emit_pipe_tab_readout()
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
    # OFFSET COMMAND helpers -> see scene_tools.py (SceneToolsMixin)
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
        self._solve_constraints(gi)
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
        scene_pos = event.scenePos()
        self._last_scene_pos = scene_pos
        self.cursorMoved.emit(self._format_cursor_readout(scene_pos))

        snapped = self.get_effective_position(scene_pos)
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
        "floor":                    "_move_floor",
        "floor_rect":               "_move_floor_rect",
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
        if self.node_start_pos:
            start = self.node_start_pos.scenePos()
            snapped_end = self.node_start_pos.snap_point_45(start, snapped)

            # Update Tab cycling candidates at cursor position
            template = getattr(self, "current_template", None)
            template_z2 = (self._compute_template_z_pos(template, node_idx=2)
                           if template is not None else None)
            self._update_pipe_tab_candidates(snapped_end, z_hint=template_z2)

            self.update_preview_node(snapped_end)
            self.preview_pipe.setLine(start.x(), start.y(), snapped_end.x(), snapped_end.y())

            # Style preview from current template
            if template:
                from .pipe import Pipe
                from .constants import PIPE_COLORS
                col_name = template._properties.get("Colour", {}).get("value", "Red")
                color = QColor(PIPE_COLORS.get(col_name, "#e62828"))
                width = Pipe.display_width_mm(template)
                pen = QPen(color, width)
                self.preview_pipe.setPen(pen)

                # Preview label — diameter on top, length below
                dx = snapped_end.x() - start.x()
                dy = snapped_end.y() - start.y()
                length_mm = math.hypot(dx, dy)
                sm = self.scale_manager
                dia_str = template._properties.get("Diameter", {}).get("value", "")
                if sm and dia_str:
                    try:
                        dia_str = sm.format_length(float(dia_str))
                    except (ValueError, TypeError):
                        pass
                len_str = sm.format_length(length_mm) if sm else f"{length_mm:.0f} mm"
                lbl = f"{dia_str}\n{len_str}" if dia_str else len_str
                self._preview_label.setText(lbl)
                # Font size from template label size (inches → mm scene units)
                label_size = 12
                try:
                    label_size = int(template._properties.get(
                        "Label Size", {}).get("value", 12))
                except (ValueError, TypeError):
                    pass
                font = QFont("Consolas")
                font.setPixelSize(max(1, int(label_size * 25.4)))
                self._preview_label.setFont(font)
                mid_x = (start.x() + snapped_end.x()) / 2
                mid_y = (start.y() + snapped_end.y()) / 2
                br = self._preview_label.boundingRect()
                self._preview_label.setPos(mid_x - br.width() / 2, mid_y - br.height() - 50)
                self._preview_label.show()
            else:
                pen = QPen(Qt.GlobalColor.darkGray, 3, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self.preview_pipe.setPen(pen)
                self._preview_label.hide()

            self.preview_pipe.show()
        else:
            # Before first click — track candidates at cursor for Tab cycling
            self.update_preview_node(snapped)
            template = getattr(self, "current_template", None)
            template_z1 = (self._compute_template_z_pos(template, node_idx=1)
                           if template is not None else None)
            self._update_pipe_tab_candidates(snapped, z_hint=template_z1)
            self.preview_pipe.hide()
            self._preview_label.hide()

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
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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
        self._update_place_import_ghost(snapped)

    def _move_offset(self, event, snapped):
        self.preview_node.hide()
        self.preview_pipe.hide()

    def _move_offset_side(self, event, snapped):
        self.preview_node.hide()
        self.preview_pipe.hide()
        if self._offset_source is not None:
            # Compute distance from cursor to source entity
            if not getattr(self, '_offset_manual', False):
                self._offset_dist = self._perpendicular_distance(
                    self._offset_source, snapped)
            if self._offset_dist > 0:
                sd = self._offset_signed_dist(
                    self._offset_source, self._offset_dist, snapped)
                self._clear_offset_preview()
                preview = self._make_offset_item(self._offset_source, sd)
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
        sm = self.scale_manager
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
            _dx = snapped.x() - last_pt.x()
            _dy = snapped.y() - last_pt.y()
            _len = math.hypot(_dx, _dy)
            _ang = math.degrees(math.atan2(-_dy, _dx))
            self._draw_dim_hint = f"L: {sm.scene_to_display(_len)}  A: {_ang:.1f}°"

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
        sm = self.scale_manager
        if self._floor_rect_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._floor_rect_anchor is not None and self._floor_rect_preview is not None:
            rect = QRectF(self._floor_rect_anchor, snapped).normalized()
            self._floor_rect_preview.setRect(rect)
            self._draw_dim_hint = (
                f"W: {sm.scene_to_display(rect.width())}  "
                f"H: {sm.scene_to_display(rect.height())}"
            )

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
        "floor":                    "_press_floor",
        "floor_rect":               "_press_floor_rect",
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
                self._apply_rotate(self._rotate_pivot, value)
                self.push_undo_state()
                self._selected_items = []
                self.set_mode(None)
        elif mode == "scale":
            if self._scale_base is not None:
                self._apply_scale(self._scale_base, value)
                self.push_undo_state()
                self._selected_items = []
                self.set_mode(None)
        elif mode == "fillet":
            self._fillet_radius = value
            if self._fillet_preview is not None:
                if self._fillet_preview.scene() is self:
                    self.removeItem(self._fillet_preview)
                self._fillet_preview = None
            data = self._compute_fillet(self._fillet_item1, self._fillet_item2,
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
            data = self._compute_chamfer(self._chamfer_item1, self._chamfer_item2,
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
            self._pending_confirm_data = getattr(self, "_pending_confirm_data", {})
            data = self._pending_confirm_data.pop("elev_start", None)
            if not data:
                return
            start_node = data["start_node"]
            template = data["template"]

            if result == "riser":
                # Create vertical riser, checking for overlap first
                xy = start_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=1)
                split_node = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if split_node is not None:
                    # Reuse existing / split node — no new vertical pipe needed
                    self.node_start_pos = split_node
                else:
                    intermediate = self._make_intermediate_node(start_node, template)
                    self.add_pipe(start_node, intermediate, template,
                                  _propagate_ceiling=False)
                    self.node_start_pos = intermediate
                self.instructionChanged.emit("Pick end node")

            elif result == "match":
                # Place pipe at existing node's elevation — adopt node's
                # ceiling into template (mirrors normal existing-node flow)
                template.node1_ceiling_level = start_node.ceiling_level
                template.node1_ceiling_offset = start_node.ceiling_offset
                template.node2_ceiling_level = start_node.ceiling_level
                template.node2_ceiling_offset = start_node.ceiling_offset
                self.node_start_pos = start_node
                self.instructionChanged.emit("Pick end node")

            elif result == "template":
                # Keep template elevation; find/split existing geometry at that Z
                xy = start_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=1)
                target = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if target is not None:
                    self.node_start_pos = target
                else:
                    # No existing geometry — create standalone node at template Z
                    self.node_start_pos = self._make_intermediate_node(
                        start_node, template)
                self.instructionChanged.emit("Pick end node")

            # Transition to phase 1: N1 locked, N2 editable
            template._placement_phase = 1
            self.requestPropertyUpdate.emit(template)

        elif action_id == "elev_mismatch_end":
            self._pending_confirm_data = getattr(self, "_pending_confirm_data", {})
            data = self._pending_confirm_data.pop("elev_end", None)
            if not data:
                return
            start_node = data["start_node"]
            end_node = data["end_node"]
            template = data["template"]

            if result == "riser":
                # Create vertical riser, checking for overlap first
                xy = end_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=2)
                split_node = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if split_node is not None:
                    # Reuse existing / split node — connect horizontal pipe to it
                    intermediate = split_node
                else:
                    intermediate = self._make_intermediate_node(end_node, template)
                    self.add_pipe(intermediate, end_node, template,
                                  _propagate_ceiling=False)
                # Place the horizontal pipe to the intermediate node
                extended = self._try_extend_collinear(
                    start_node, intermediate, template)
                if not extended:
                    self.add_pipe(start_node, intermediate, template)
                    start_node.fitting.update()
                    intermediate.fitting.update()
                    self._convert_45_elbow_to_wye(start_node, template)
                self.node_start_pos = intermediate
                self._pipe_node_was_new = False
                self.push_undo_state()
                self.instructionChanged.emit(
                    "Pick next node (Esc/double-click to finish)")

            elif result == "match":
                # Place pipe at existing node's elevation — adopt node's
                # ceiling into template (mirrors normal existing-node flow)
                template.node2_ceiling_level = end_node.ceiling_level
                template.node2_ceiling_offset = end_node.ceiling_offset
                self.requestPropertyUpdate.emit(template)
                extended = self._try_extend_collinear(
                    start_node, end_node, template)
                if not extended:
                    self.add_pipe(start_node, end_node, template)
                    start_node.fitting.update()
                    end_node.fitting.update()
                    self._convert_45_elbow_to_wye(start_node, template)
                self.node_start_pos = end_node
                self._pipe_node_was_new = False
                self.push_undo_state()
                self.instructionChanged.emit(
                    "Pick next node (Esc/double-click to finish)")

            elif result == "template":
                # Keep template elevation; find/split existing geometry at that Z
                xy = end_node.scenePos()
                template_z = self._compute_template_z_pos(template, node_idx=2)
                target = self._find_or_split_vertical_at_z(
                    xy, template_z, template) if template_z is not None else None
                if target is None:
                    target = self._make_intermediate_node(end_node, template)
                # Place horizontal pipe to the target node
                extended = self._try_extend_collinear(
                    start_node, target, template)
                if not extended:
                    self.add_pipe(start_node, target, template)
                    start_node.fitting.update()
                    target.fitting.update()
                    self._convert_45_elbow_to_wye(start_node, template)
                self.node_start_pos = target
                self._pipe_node_was_new = False
                self.push_undo_state()
                self.instructionChanged.emit(
                    "Pick next node (Esc/double-click to finish)")

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
        _skip_grip_modes = ("wall", "floor", "floor_rect", "pipe", "sprinkler",
                            "draw_line", "draw_rectangle",
                            "draw_circle", "draw_arc", "polyline", "draw_gridline",
                            "dimension", "text", "door", "window", "set_scale",
                            "detail", "align", "design_area")
        if (self.mode not in _skip_grip_modes
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            grip_hit = self._find_grip_hit(snapped)
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
                # Enable inference self-exclusion for gridline endpoint drags.
                if isinstance(self._grip_item, GridlineItem):
                    self._inference_active_item = self._grip_item
                return  # consumed by grip system

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
            getattr(self, handler_name)(event, scene_pos, snapped,
                                        selection, node_under, pipe_under)
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
        if self.node_start_pos is None:
            template = getattr(self, "current_template", None)

            # Use Tab-selected candidate if available
            tab_node = None
            if (self._pipe_tab_candidates
                    and self._pipe_tab_index < len(self._pipe_tab_candidates)):
                tab_node = self._pipe_tab_candidates[self._pipe_tab_index]

            # Check for existing node BEFORE find_or_create_node
            template_z1 = (self._compute_template_z_pos(template, node_idx=1)
                           if template is not None else None)
            existing_start = (tab_node if tab_node is not None
                              else self.find_nearby_node(
                                  snapped.x(), snapped.y(), z_hint=template_z1))

            # Block starting a pipe from a node that's already full (4 = cross)
            if existing_start is not None and len(existing_start.pipes) >= 4:
                self.warningIssued.emit(
                    "Connection Limit",
                    f"This node already has {len(existing_start.pipes)} connections (max 4).")
                return
            # Starting from a tee node is allowed — the second-click check
            # will validate the angle for the cross.

            if isinstance(item_under, Pipe):
                start_node = self.split_pipe(item_under, self.project_click_onto_pipe_segment(snapped, item_under))
                self._pipe_node_was_new = True  # split created new node
                _check_elevation = True  # split node inherits pipe's Z — may differ from template
            else:
                start_node = (tab_node if tab_node is not None
                              else self.find_or_create_node(
                                  snapped.x(), snapped.y(), z_hint=template_z1))
                self._pipe_node_was_new = (existing_start is None)
                _check_elevation = (existing_start is not None and existing_start is start_node)

            # Check elevation mismatch on pre-existing or pipe-split nodes
            if _check_elevation and template is not None:
                template_z = self._compute_template_z_pos(template, node_idx=1)
                if template_z is not None and abs(start_node.z_pos - template_z) > 0.01:
                    if not hasattr(self, "_pending_confirm_data"):
                        self._pending_confirm_data = {}
                    self._pending_confirm_data["elev_start"] = {
                        "start_node": start_node, "template": template}
                    sm = self.scale_manager
                    _fz = sm.format_length if sm else (lambda v: f"{v:.1f} mm")
                    self.confirmRequested.emit(
                        "elev_mismatch_start",
                        "Elevation Mismatch",
                        f"Start node is at elevation {_fz(start_node.z_pos)} "
                        f"but the template targets {_fz(template_z)}.")
                    # Result handled by complete_confirmation(); flow resumes
                    # with start_node potentially replaced by intermediate
                    return

            self.node_start_pos = start_node
            # Reset Tab cycling after committing start node
            self._pipe_tab_candidates = []
            self._pipe_tab_index = 0
            # Transition to phase 1: lock Node 1, allow Node 2 editing
            if template is not None:
                if self._pipe_node_was_new:
                    # New node — apply template elevation TO the node
                    start_node.ceiling_level = template.node1_ceiling_level
                    start_node.ceiling_offset = template.node1_ceiling_offset
                else:
                    # Existing node — adopt its elevation for Node 1
                    template.node1_ceiling_level = start_node.ceiling_level
                    template.node1_ceiling_offset = start_node.ceiling_offset
                # Default Node 2 to match Node 1 (horizontal pipe default)
                template.node2_ceiling_level = template.node1_ceiling_level
                template.node2_ceiling_offset = template.node1_ceiling_offset
                template._placement_phase = 1
                self.requestPropertyUpdate.emit(template)
            self.instructionChanged.emit("Pick end node")
        else:
            start_pos   = self.node_start_pos.scenePos()
            snapped_end = self.node_start_pos.snap_point_45(start_pos, snapped)
            template = getattr(self, "current_template", None)

            # ── Backtrack check (before creating/splitting nodes) ─────
            if self._would_backtrack_at(self.node_start_pos, snapped_end):
                self.warningIssued.emit(
                    "Pipe Overlap",
                    "Cannot place a pipe back over an existing pipe segment.")
                return

            # ── Node connection-limit & angle validation ─────────────
            # Only count coplanar pipes — risers don't consume branch slots
            _sz = self.node_start_pos.z_pos
            start_pipes = sum(1 for p in self.node_start_pos.pipes
                              if abs((p.node2 if p.node1 is self.node_start_pos
                                      else p.node1).z_pos - _sz) <= Z_COPLANAR_TOL)
            if start_pipes >= 4:
                self.warningIssued.emit(
                    "Connection Limit",
                    f"Start node already has {start_pipes} coplanar connections (max 4).")
                return
            # Adding a 4th branch is only valid to turn a tee into a cross
            if start_pipes == 3:
                err = self._validate_4th_branch(self.node_start_pos, snapped_end)
                if err:
                    self.warningIssued.emit("Invalid Connection", err)
                    return
            # Use Tab-selected candidate if available
            tab_node = None
            if (self._pipe_tab_candidates
                    and self._pipe_tab_index < len(self._pipe_tab_candidates)):
                tab_node = self._pipe_tab_candidates[self._pipe_tab_index]

            template_z2 = (self._compute_template_z_pos(template, node_idx=2)
                           if template is not None else None)
            existing_end_check = (tab_node if tab_node is not None
                                  else self.find_nearby_node(
                                      snapped_end.x(), snapped_end.y(), z_hint=template_z2))
            if existing_end_check is not None:
                _ez = existing_end_check.z_pos
                end_pipes = sum(1 for p in existing_end_check.pipes
                                if abs((p.node2 if p.node1 is existing_end_check
                                        else p.node1).z_pos - _ez) <= Z_COPLANAR_TOL)
                if end_pipes >= 4:
                    self.warningIssued.emit(
                        "Connection Limit",
                        f"Target node already has {end_pipes} coplanar connections (max 4).")
                    return
                if end_pipes == 3:
                    err = self._validate_4th_branch(
                        existing_end_check,
                        self.node_start_pos.scenePos())
                    if err:
                        self.warningIssued.emit("Invalid Connection", err)
                        return

            # Check for existing node BEFORE find_or_create_node
            existing_end = (tab_node if tab_node is not None
                            else self.find_nearby_node(
                                snapped_end.x(), snapped_end.y(), z_hint=template_z2))

            if isinstance(item_under, Pipe):
                end_node = self.split_pipe(item_under, self.project_click_onto_pipe_segment(snapped_end, item_under))
                _check_end_elev = True  # split node inherits pipe's Z
            else:
                end_node = (tab_node if tab_node is not None
                            else self.find_or_create_node(
                                snapped_end.x(), snapped_end.y(), z_hint=template_z2))
                _check_end_elev = (existing_end is not None)

            # Block zero-length same-node pipe — unless template specifies
            # a different elevation for Node 2 (vertical pipe placement)
            if end_node is self.node_start_pos:
                if template is not None:
                    z1 = self._compute_template_z_pos(template, node_idx=1)
                    z2 = self._compute_template_z_pos(template, node_idx=2)
                    if z1 is not None and z2 is not None and abs(z1 - z2) > 0.5:
                        # Create a new node at same XY with Node 2's elevation
                        end_node = self._make_intermediate_node_for_n2(
                            self.node_start_pos, template)
                    else:
                        return  # truly same position — wait for valid click
                else:
                    return

            # Detect elevation mismatch on an existing or pipe-split end node
            if _check_end_elev and template is not None:
                template_z = self._compute_template_z_pos(template, node_idx=2)
                if template_z is not None and abs(end_node.z_pos - template_z) > 0.01:
                    if not hasattr(self, "_pending_confirm_data"):
                        self._pending_confirm_data = {}
                    self._pending_confirm_data["elev_end"] = {
                        "start_node": self.node_start_pos,
                        "end_node": end_node, "template": template}
                    sm = self.scale_manager
                    _fz = sm.format_length if sm else (lambda v: f"{v:.1f} mm")
                    self.confirmRequested.emit(
                        "elev_mismatch_end",
                        "Elevation Mismatch",
                        f"The target node is at elevation {_fz(end_node.z_pos)} "
                        f"but the template targets {_fz(template_z)}.")
                    return

            # ── Collinear extension check ─────────────────────────────
            extended = self._try_extend_collinear(
                self.node_start_pos, end_node, template)

            if not extended:
                new_pipe = self.add_pipe(
                    self.node_start_pos, end_node, template)
                self.node_start_pos.fitting.update()
                end_node.fitting.update()
                # ── 45° elbow → wye + stub ────────────────────────────
                self._convert_45_elbow_to_wye(
                    self.node_start_pos, template)

            # Continuous polyline: end node becomes the next start node
            self.node_start_pos = end_node
            self._pipe_node_was_new = False
            # Reset Tab cycling after committing end node
            self._pipe_tab_candidates = []
            self._pipe_tab_index = 0
            self.push_undo_state()
            # Update template: Node 1 adopts end node's elevation for next segment
            if template is not None:
                template.node1_ceiling_level = end_node.ceiling_level
                template.node1_ceiling_offset = end_node.ceiling_offset
                # Default Node 2 to match for horizontal continuation
                template.node2_ceiling_level = end_node.ceiling_level
                template.node2_ceiling_offset = end_node.ceiling_offset
                template._placement_phase = 1
                self.requestPropertyUpdate.emit(template)
            self.instructionChanged.emit("Pick next node (Esc/double-click to finish)")

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
            # Uses the RAW click position (not snapped) so OSNAP hits on
            # gridlines/underlay geometry cannot drag the pick away, and a
            # zoom-aware pixel radius so sprinklers are hittable at any zoom.
            active = getattr(self, "active_level", DEFAULT_LEVEL)
            view_scale = (self.views()[0].transform().m11()
                          if self.views() else 1.0)
            tol = DESIGN_AREA_PICK_PX / max(view_scale, 1e-9)
            target_spr = None
            best_d = tol
            for spr in self.sprinkler_system.sprinklers:
                if not spr.node:
                    continue
                if getattr(spr.node, "level", DEFAULT_LEVEL) != active:
                    continue
                d = spr.node.distance_to(pos.x(), pos.y())
                if d < best_d:
                    best_d = d
                    target_spr = spr
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
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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
        self._commit_place_import(snapped)

    def _press_offset(self, event, pos, snapped, item_under, node_under, pipe_under):
        # Select entity to offset — go straight to live preview (no dialog)
        hit = [i for i in self.items(pos)
               if isinstance(i, (LineItem, PolylineItem, CircleItem, RectangleItem, ArcItem))]
        if not hit:
            return
        self._offset_source = hit[0]
        self._offset_highlight = self._highlight_item(hit[0])
        self._offset_dist = 0  # will be computed from cursor distance
        self._offset_manual = False  # cursor-driven distance
        self.set_mode("offset_side")
        self._show_status(
            "Move cursor to set offset distance and side, "
            "click to commit. Tab = type distance.")

    def _press_offset_side(self, event, pos, snapped, item_under, node_under, pipe_under):
        # Click determines which side — commit the offset
        if self._offset_source is not None and self._offset_dist > 0:
            sd = self._offset_signed_dist(self._offset_source, self._offset_dist, snapped)
            self._clear_offset_preview()
            new_item = self._make_offset_item(self._offset_source, sd)
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
            self._apply_rotate(self._rotate_pivot, angle)
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
            self._apply_mirror(self._mirror_p1, snapped)
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
            hit = self._find_geometry_at(pos)
            if hit is not None:
                self._break_target = hit
                self._break_highlight = self._highlight_item(hit)
                self.instructionChanged.emit("Pick first break point on object")
        elif self._break_p1 is None:
            self._break_p1 = snapped
            self.instructionChanged.emit("Pick second break point")
        else:
            self._break_item(self._break_target, self._break_p1, snapped)
            self.push_undo_state()
            self.set_mode("break")

    # ── Break at Point ───────────────────────────────────────────────
    def _press_break_at_point(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._break_at_target is None:
            hit = self._find_geometry_at(pos)
            if hit is not None:
                self._break_at_target = hit
                self._break_at_highlight = self._highlight_item(hit)
                self.instructionChanged.emit("Pick break point on object")
        else:
            self._break_at_point(self._break_at_target, snapped)
            self.push_undo_state()
            self.set_mode("break_at_point")

    # ── Fillet ───────────────────────────────────────────────────────
    def _press_fillet(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._fillet_item1 is None:
            hit = self._find_geometry_at(pos)
            if hit is not None and isinstance(hit, LineItem):
                self._fillet_item1 = hit
                self._fillet_highlight1 = self._highlight_item(hit)
                self.instructionChanged.emit("Click second line (Tab = set radius)")
        elif self._fillet_item2 is None:
            hit = self._find_geometry_at(pos)
            if hit is not None and isinstance(hit, LineItem) and hit is not self._fillet_item1:
                self._fillet_item2 = hit
                self._fillet_highlight2 = self._highlight_item(hit)
                data = self._compute_fillet(self._fillet_item1, self._fillet_item2,
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
            hit = self._find_geometry_at(pos)
            if hit is not None and isinstance(hit, LineItem):
                self._chamfer_item1 = hit
                self._chamfer_highlight1 = self._highlight_item(hit)
                self.instructionChanged.emit("Click second line (Tab = set distance)")
        elif self._chamfer_item2 is None:
            hit = self._find_geometry_at(pos)
            if hit is not None and isinstance(hit, LineItem) and hit is not self._chamfer_item1:
                self._chamfer_item2 = hit
                self._chamfer_highlight2 = self._highlight_item(hit)
                data = self._compute_chamfer(self._chamfer_item1, self._chamfer_item2,
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
                self._commit_stretch(delta)
                self.push_undo_state()
                self.set_mode(None)

    # ── Trim / Extend (Sprint Y) ─────────────────────────────────────
    def _press_trim(self, event, pos, snapped, item_under, node_under, pipe_under):
        self._handle_trim_click(snapped)

    def _press_extend(self, event, pos, snapped, item_under, node_under, pipe_under):
        self._handle_extend_click(snapped)

    # ── Merge / Hatch ────────────────────────────────────────────────
    def _press_merge_hatch(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self.mode == "merge_points":
            self._handle_merge_click(snapped)

    # ── Constraints ──────────────────────────────────────────────────
    def _press_constraint(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self.mode == "constraint_concentric":
            self._handle_constraint_concentric_click(snapped)
        elif self.mode == "constraint_dimensional":
            self._handle_constraint_dimensional_click(snapped)

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
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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

        ``tip`` is expected to arrive fully constrained (OSNAP, inference,
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

        ``tip`` is expected to be fully constrained already (OSNAP, inference,
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
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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

    # ── Floor drawing ─────────────────────────────────────────────────
    def _press_floor(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._floor_active is None:
            _ftmpl = self._get_floor_template()
            slab = FloorSlab(color=_ftmpl._color.name())
            slab.name = f"Floor {self._next_floor_num}"
            self._next_floor_num += 1
            slab._thickness_mm = _ftmpl._thickness_mm
            slab.level = _ftmpl.level if _ftmpl.level else self.active_level
            slab.add_point(snapped)
            self.addItem(slab)
            self._floor_slabs.append(slab)
            self._floor_active = slab
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick next point (click near first or Enter to close)")
        else:
            pts = self._floor_active._points
            # Close-near-first: if ≥3 points and click is within snap tolerance of first vertex
            if len(pts) >= 3:
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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
                    self.instructionChanged.emit("Pick first boundary point (click near first to close)")
                    return
            # Click-to-delete vertex: if click is near an existing vertex (8px) → remove it
            if len(pts) >= 2:
                scale = self.views()[0].transform().m11() if self.views() else 1.0
                tol = 8.0 / max(scale, 1e-6)
                for vi in range(len(pts)):
                    dv = math.hypot(snapped.x() - pts[vi].x(), snapped.y() - pts[vi].y())
                    if dv <= tol:
                        pts.pop(vi)
                        self._floor_active._rebuild_path()
                        for v in self.views(): v.viewport().update()
                        return
            self._floor_active.add_point(snapped)

    # ── Floor rectangle (2-click) ─────────────────────────────────────
    def _press_floor_rect(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._floor_rect_anchor is None:
            self._floor_rect_anchor = snapped
            self.instructionChanged.emit("Pick opposite corner for rectangular floor")
            # Create preview rect
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            _ftmpl = self._get_floor_template()
            _fc = QColor(_ftmpl._color)
            pen = QPen(_fc, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            preview.setPen(pen)
            _fc.setAlpha(30)
            preview.setBrush(QBrush(_fc))
            preview.setZValue(200)
            self.addItem(preview)
            self._floor_rect_preview = preview
        else:
            # Commit rectangular floor
            rect = QRectF(self._floor_rect_anchor, snapped).normalized()
            corners = [
                QPointF(rect.x(), rect.y()),
                QPointF(rect.x() + rect.width(), rect.y()),
                QPointF(rect.x() + rect.width(), rect.y() + rect.height()),
                QPointF(rect.x(), rect.y() + rect.height()),
            ]
            _ftmpl = self._get_floor_template()
            slab = FloorSlab(points=corners, color=_ftmpl._color.name())
            slab.name = f"Floor {self._next_floor_num}"
            self._next_floor_num += 1
            slab._thickness_mm = _ftmpl._thickness_mm
            slab.level = _ftmpl.level if _ftmpl.level else self.active_level
            self.addItem(slab)
            self._floor_slabs.append(slab)
            apply_category_defaults(slab)
            slab.setSelected(True)
            for v in self.views(): v.viewport().update()
            # Clean up preview
            if self._floor_rect_preview is not None:
                self.removeItem(self._floor_rect_preview)
                self._floor_rect_preview = None
            self._floor_rect_anchor = None
            self.push_undo_state()
            self.instructionChanged.emit("Pick first corner for rectangular floor")

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
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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
                scale = self.views()[0].transform().m11() if self.views() else 1.0
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
        # ── Gridline body drag release ──────────────────────────────────
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_gridline is not None:
            self.push_undo_state()
            self._dragging_gridline = None
            self._gridline_drag_start = None
            self._gridline_drag_original_pos = None
            return
        if event.button() == Qt.MouseButton.LeftButton and self._grip_dragging:
            self._solve_constraints(self._grip_item)  # enforce constraints
            self._grip_dragging = False
            self._grip_item     = None
            self._grip_index    = -1
            # Clear inference active item now that the drag gesture is complete.
            self._inference_active_item = None
            self._inference_result = None
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
                    sd = self._offset_signed_dist(self._offset_source, self._offset_dist, cursor_pos)
                    self._clear_offset_preview()
                    new_item = self._make_offset_item(self._offset_source, sd)
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
                data = self._compute_fillet(self._fillet_item1, self._fillet_item2,
                                            self._fillet_radius)
                if data is not None:
                    self._commit_fillet(data)
                    self.push_undo_state()
                else:
                    self._show_status("Cannot compute fillet for these objects", timeout=3000)
                self.set_mode(None)
                return
            # Commit chamfer
            elif self.mode == "chamfer" and self._chamfer_item1 is not None and self._chamfer_item2 is not None:
                data = self._compute_chamfer(self._chamfer_item1, self._chamfer_item2,
                                              self._chamfer_dist)
                if data is not None:
                    self._commit_chamfer(data)
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
        self._solve_constraints()  # enforce constraints after move
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
    # GEOMETRY TOOLS -> see scene_tools.py (SceneToolsMixin)
    # array, rotate, scale, mirror, join, explode, break, fillet, chamfer,
    # stretch, trim, extend, merge, hatch, constraints, geometry helpers
    # -------------------------------------------------------------------------
