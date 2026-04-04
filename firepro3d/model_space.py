import sys, json, math, shutil, logging

log = logging.getLogger("FirePro3D")
from PyQt6.QtWidgets import (QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
                              QGraphicsItem, QGraphicsItemGroup, QGraphicsPixmapItem,
                              QGraphicsTextItem, QGraphicsSimpleTextItem,
                              QGraphicsPathItem, QGraphicsRectItem,
                              QApplication, QProgressDialog, QMenu,
                              QDialog,
                              QHBoxLayout, QVBoxLayout, QLabel, QLineEdit)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import (QPen, QBrush, QColor, QPixmap, QPainterPath, QFont,
                          QCursor, QDoubleValidator, QImage, QPolygonF)
from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from .node import Node
from .pipe import Pipe
from .sprinkler import Sprinkler
from .sprinkler_system import SprinklerSystem
from .cad_math import CAD_Math
from .annotations import Annotation, DimensionAnnotation, NoteAnnotation, HatchItem
from .underlay import Underlay
from .scale_manager import ScaleManager
from .calibrate_dialog import CalibrateDialog
from .roof_dialog import RoofDialog
from .underlay_context_menu import UnderlayContextMenu
from .dxf_import_worker import DxfImportWorker
from .water_supply import WaterSupply
from .design_area import DesignArea
from .construction_geometry import (
    ConstructionLine, PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
)
from .snap_engine import SnapEngine, OsnapResult
from .display_manager import apply_category_defaults
from .gridline import GridlineItem, reset_grid_counters
from .view_marker import ViewMarkerArrow
from .constants import (Z_BELOW_GEOMETRY, DEFAULT_LEVEL, DEFAULT_USER_LAYER,
                       DEFAULT_CEILING_OFFSET_MM)
from .wall import WallSegment, compute_wall_quad, DEFAULT_THICKNESS_MM
from .floor_slab import FloorSlab
from .roof import RoofItem
from .room import Room
from .wall_opening import WallOpening, DoorOpening, WindowOpening
from .constraints import Constraint as ConstraintBase
from .user_layer_manager import lw_mm_to_cosmetic_px
from . import geometry_intersect as gi
import os


from .scene_io import SceneIOMixin
from .scene_tools import SceneToolsMixin


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
        self._snap_to_underlay: bool = False
        self.water_supply_node: "WaterSupply | None" = None  # placed water supply
        self.hydraulic_result = None                          # last solver run (Sprint 2)
        self._radiation_selecting = False                      # True during radiation surface selection
        self.design_areas: list = []                          # list[DesignArea]
        self.active_design_area = None                        # DesignArea | None
        self.active_user_layer: str = DEFAULT_USER_LAYER                  # Sprint 4A active layer
        self.active_level: str = DEFAULT_LEVEL                     # floor level
        self._design_area_corner1: "QPointF | None" = None
        self._design_area_rect_item = None                    # QGraphicsRectItem preview
        # Construction geometry (Sprint C)
        self._construction_lines: list[ConstructionLine] = []
        self._polylines: list[PolylineItem] = []
        self._cline_anchor: "QPointF | None" = None           # first click for construction line
        self._polyline_active: "PolylineItem | None" = None   # in-progress polyline
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
        self._draw_circle_preview: "QGraphicsEllipseItem | None" = None
        # Draw colour/lineweight now derived from active layer (see _get_draw_color/_get_draw_lineweight)
        self._last_scene_pos: "QPointF | None" = None  # last cursor position for Tab defaults
        # Arc drawing (3-click: centre, start point, end point)
        self._draw_arcs: list[ArcItem] = []
        self._draw_arc_center: "QPointF | None" = None
        self._draw_arc_radius: float = 0.0
        self._draw_arc_start_deg: float = 0.0
        self._draw_arc_step: int = 0  # 0=awaiting centre, 1=awaiting start, 2=awaiting end
        self._draw_arc_radius_line: "QGraphicsLineItem | None" = None
        self._draw_arc_preview: "QGraphicsPathItem | None" = None
        # Text rubber-band (Sprint Q)
        self._text_anchor: "QPointF | None" = None
        self._text_preview: "QGraphicsRectItem | None" = None
        # Gridlines (Sprint U)
        self._gridlines: list[GridlineItem] = []
        self._gridline_anchor: "QPointF | None" = None  # first click for gridline placement
        # OSNAP (Sprint H)
        self._snap_engine: SnapEngine = SnapEngine()
        self._snap_result: "OsnapResult | None" = None
        self._osnap_enabled: bool = True
        self._snap_angle_deg: float = 45.0       # Ctrl-snap angle increment (degrees)
        self._project_info: dict = {}            # project metadata (name, address, etc.)
        self._level_manager = None                             # set by main.py
        self._plan_view_manager = None                         # set by main.py
        # Grip editing (Sprint I)
        self._grip_item = None                  # item currently being grip-dragged
        self._grip_index: int = -1              # grip handle index
        self._grip_dragging: bool = False
        # Offset command (Sprint L)
        self._offset_source = None              # entity selected for offset
        self._offset_dist: float = 0.0          # distance entered by user
        self._offset_preview = None             # preview item shown during side-pick
        self._offset_manual: bool = False       # True when user typed distance via Tab
        self._offset_highlight = None           # highlight overlay for selected offset entity
        # Move preview (Sprint Z)
        self._move_preview_line = None          # rubber-band line from base point to cursor
        # Single place mode (Sprint Y) — return to select after placing one item
        self.single_place_mode: bool = False
        # Trim / Extend / Merge state (Sprint Y)
        self._trim_edge = None              # cutting edge item for trim
        self._trim_edge_highlight = None    # highlight overlay
        self._extend_boundary = None        # boundary edge item for extend
        self._extend_boundary_highlight = None
        self._merge_point1: tuple | None = None  # (item, grip_index, QPointF)
        self._merge_preview = None          # visual line connecting merge points
        # Hatching state (Sprint Y)
        self._hatch_items: list = []        # list of HatchItem
        # Constraint state (Sprint Y)
        self._constraints: list = []        # list of Constraint objects
        self._constraint_circle_a = None    # first circle for concentric constraint
        self._constraint_grip_a: tuple | None = None  # (item, grip_index) for dimensional
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
        self._wall_template: "WallSegment | None" = None      # pre-placement property template
        self._floor_template: "FloorSlab | None" = None       # pre-placement property template
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
        self._floor_active: "FloorSlab | None" = None       # in-progress floor boundary
        self._floor_rect_anchor: "QPointF | None" = None   # first click for rect floor
        self._floor_rect_preview: "QGraphicsRectItem | None" = None
        self._geometry_template = None                      # pre-placement template for geometry tools
        # Detail view placement
        self._detail_rect_anchor: "QPointF | None" = None
        self._detail_rect_preview: "QGraphicsRectItem | None" = None
        self._detail_markers: list = []
        self._detail_manager = None  # set by main.py
        # Undo/redo
        self._undo_stack: list[dict] = []
        self._undo_pos: int = -1
        self._in_undo_restore: bool = False
        self.init_preview_node()
        self.init_preview_pipe()
        self.draw_origin()
        self.push_undo_state()   # initial empty state

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
            ConstructionLine:    self._construction_lines,
            PolylineItem:        self._polylines,
            LineItem:            self._draw_lines,
            RectangleItem:       self._draw_rects,
            CircleItem:          self._draw_circles,
            ArcItem:             self._draw_arcs,
            GridlineItem:        self._gridlines,
            HatchItem:           self._hatch_items,
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

        # Update fittings on surviving nodes that lost pipes
        for node in ss.nodes:
            if hasattr(node, "fitting") and node.fitting:
                node.fitting.update()

    # -------------------------------------------------------------------------
    # MODE MANAGEMENT

    def set_mode(self, mode, template=None):
        self.mode = mode
        self._snap_result = None      # clear stale snap marker
        # Reset grip editing state (prevents stale grip after Escape mid-drag)
        self._grip_item = None
        self._grip_index = -1
        self._grip_dragging = False
        self.modeChanged.emit(mode)
        # Auto-deselect all geometry when entering a drawing/placement mode
        if mode not in ("select", "stretch", "move", "rotate", "scale",
                        "radiation_emitter", "radiation_receiver"):
            self.clearSelection()
        self.preview_node.hide()
        self.preview_pipe.hide()
        self._cal_point1 = None
        # In design_area mode, OSNAP stays on but filters out pipes
        if mode == "design_area":
            self._snap_engine.skip_pipes = True
        else:
            self._snap_engine.skip_pipes = False
        # Clean up design_area preview if leaving that mode mid-draw
        if mode != "design_area":
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
        if mode != "construction_line":
            self._cline_anchor = None
        if mode != "polyline" and self._polyline_active is not None:
            # Cancel: always discard the in-progress polyline
            # (Enter commits via finalize() and sets _polyline_active=None
            #  before reaching here, so this path is only hit by Escape/mode-change)
            if self._polyline_active.scene() is self:
                self.removeItem(self._polyline_active)
            if self._polyline_active in self._polylines:
                self._polylines.remove(self._polyline_active)
            self._polyline_active = None
        # Cancel in-progress draw geometry
        if mode != "draw_line":
            self._draw_line_anchor = None
        if mode != "draw_rectangle":
            self._draw_rect_anchor = None
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
        if mode != "text":
            self._text_anchor = None
            if self._text_preview is not None:
                if self._text_preview.scene() is self:
                    self.removeItem(self._text_preview)
                self._text_preview = None
        if mode != "gridline":
            self._gridline_anchor = None
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
                    # Sync per-node defaults from pipe's ceiling properties
                    template.node1_ceiling_level = template.ceiling_level
                    template.node1_ceiling_offset = template.ceiling_offset
                    template.node2_ceiling_level = template.ceiling_level
                    template.node2_ceiling_offset = template.ceiling_offset
                self.requestPropertyUpdate.emit(template)
        else:
            self.current_template = None

        # Clean up move preview line
        if mode != "move":
            if self._move_preview_line is not None:
                if self._move_preview_line.scene() is self:
                    self.removeItem(self._move_preview_line)
                self._move_preview_line = None

        # Clean up offset preview whenever leaving offset modes
        if mode not in ("offset", "offset_side"):
            self._clear_offset_preview()
            self._offset_source = None
            self._offset_manual = False
            if self._offset_highlight is not None:
                if self._offset_highlight.scene() is self:
                    self.removeItem(self._offset_highlight)
                self._offset_highlight = None

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
        if mode != "wall_rect":
            self._wall_rect_anchor = None
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
            "design_area":    "Click sprinklers to toggle. Shift+click for rectangle. Right-click to confirm.",
            "water_supply":   "Click to place water supply",
            "paste":          "Click to place pasted items",
            "construction_line": "Pick first point",
            "gridline":       "Pick start point",
            "trim":           "Select cutting edge",
            "trim_pick":      "Click segment to trim (right-click to cancel)",
            "extend":         "Select boundary edge",
            "extend_pick":    "Click near endpoint to extend (right-click to cancel)",
            "merge_points":   "Click first endpoint",
            "hatch":          "Click a closed object to apply hatching",
            "constraint_concentric":   "Select first circle",
            "constraint_dimensional":  "Click first grip point",
            "rotate":          "Pick pivot point",
            "scale":           "Pick base point (Tab = enter factor)",
            "mirror":          "Pick first axis point",
            "break":           "Select object to break",
            "break_at_point":  "Select object to split",
            "fillet":          "Click first object",
            "chamfer":         "Click first object",
            "stretch":         "Draw crossing window (right-to-left)",
            "wall":            "Pick wall start point",
            "wall_rect":       "Pick first corner for rectangular wall",
            "floor":           "Pick first boundary point (click near first to close)",
            "floor_rect":      "Pick first corner for rectangular floor",
            "room":            "Click inside a closed wall region",
            "room_manual":     "Pick first room boundary point",
            "door":            "Click on a wall to place door",
            "window":          "Click on a wall to place window",
            "detail":          "Pick first corner for detail view boundary",
        }
        instr = _initial_steps.get(mode, "")
        if mode == "wall":
            self.instructionChanged.emit(
                f"Pick wall start point [{self._wall_alignment}]")
        elif instr:
            self.instructionChanged.emit(instr)

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

    def find_nearby_node(self, x, y):
        pt = QPointF(x, y)
        # Priority 1: cursor inside any sprinkler's bounding box → snap to node
        for node in self.sprinkler_system.nodes:
            if node.has_sprinkler():
                spr = node.sprinkler
                if spr.mapToScene(spr.boundingRect()).boundingRect().contains(pt):
                    return node
        # Priority 2: distance-based snap
        for node in self.sprinkler_system.nodes:
            if node.distance_to(x, y) <= self.SNAP_RADIUS:
                return node
        return None

    def find_or_create_node(self, x, y):
        existing = self.find_nearby_node(x, y)
        if existing:
            return existing
        return self.add_node(x, y)

    def add_node(self, x, y):
        node = self.find_nearby_node(x, y)
        if not node:
            node = Node(x, y)
            node.user_layer = self.active_user_layer
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
        pipe.user_layer = self.active_user_layer
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
            # Use per-node ceiling values if available (template placement)
            for node, lvl_attr, off_attr in (
                (n1, "node1_ceiling_level", "node1_ceiling_offset"),
                (n2, "node2_ceiling_level", "node2_ceiling_offset"),
            ):
                if node is None:
                    continue
                c_lvl = getattr(template, lvl_attr, None)
                c_off = getattr(template, off_attr, None)
                if c_lvl is None:
                    c_lvl = pipe._properties["Ceiling Level"]["value"]
                if c_off is None:
                    try:
                        c_off = float(pipe._properties["Ceiling Offset"]["value"])
                    except (ValueError, TypeError):
                        c_off = -2.0
                node.ceiling_level = c_lvl
                node._properties["Ceiling Level"]["value"] = c_lvl
                node.ceiling_offset = c_off
                node._properties["Ceiling Offset"]["value"] = str(c_off)
                node._recompute_z_pos()
        elif _propagate_ceiling:
            # No template — fallback to pipe's single ceiling values
            ceiling_lvl = pipe._properties["Ceiling Level"]["value"]
            try:
                ceiling_off = float(pipe._properties["Ceiling Offset"]["value"])
            except (ValueError, TypeError):
                ceiling_off = -2.0
            for node in (n1, n2):
                if node is not None:
                    node.ceiling_level = ceiling_lvl
                    node._properties["Ceiling Level"]["value"] = ceiling_lvl
                    node.ceiling_offset = ceiling_off
                    node._properties["Ceiling Offset"]["value"] = str(ceiling_off)
                    node._recompute_z_pos()

        return pipe

    def _validate_4th_branch(self, node, new_pt: QPointF) -> str | None:
        """Check whether adding a 4th branch at *node* toward *new_pt* is valid.

        A 4th pipe is only allowed if:
        - The existing fitting is a tee (3 pipes with a through-run pair)
        - The new pipe is perpendicular (~90°) to the through-run

        Returns an error message string, or None if the connection is valid.
        """
        from .fitting import Fitting
        pipes = node.pipes
        if len(pipes) != 3:
            return "A 4th branch can only be added to a tee fitting."
        # Check that the current fitting is actually a tee
        ft_type = node.fitting.determine_type(pipes)
        if ft_type != "tee":
            return (f"A 4th branch can only be added to a tee fitting "
                    f"(current fitting: {ft_type}).")
        # Find the through-run direction (the collinear pair in the tee)
        np_ = node.scenePos()
        vectors = []
        for p in pipes:
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
        """
        ep = end_node.scenePos()
        for pipe in start_node.pipes:
            other = pipe.node2 if pipe.node1 is start_node else pipe.node1
            # Direct duplicate
            if other is end_node:
                return True
            # End point lies on an existing pipe segment
            op = other.scenePos()
            sp = start_node.scenePos()
            dx, dy = op.x() - sp.x(), op.y() - sp.y()
            length_sq = dx * dx + dy * dy
            if length_sq < 1e-6:
                continue
            t = ((ep.x() - sp.x()) * dx + (ep.y() - sp.y()) * dy) / length_sq
            if 0.01 < t < 0.99:
                # Project and check perpendicular distance
                proj_x = sp.x() + t * dx
                proj_y = sp.y() + t * dy
                dist = math.hypot(ep.x() - proj_x, ep.y() - proj_y)
                if dist < 10.0:  # within snap tolerance
                    return True
        return False

    def _would_backtrack_at(self, start_node, target_pt: QPointF) -> bool:
        """Like _would_backtrack but takes a point instead of a node.

        Used to check for backtracking *before* creating a node.
        """
        sp = start_node.scenePos()
        for pipe in start_node.pipes:
            other = pipe.node2 if pipe.node1 is start_node else pipe.node1
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
        # Fallback to pipe-level properties
        if not ceiling_lvl_name:
            ceiling_lvl_name = template._properties.get(
                "Ceiling Level", {}).get("value")
        if offset is None:
            try:
                offset = float(template._properties.get(
                    "Ceiling Offset", {}).get("value", DEFAULT_CEILING_OFFSET_MM))
            except (ValueError, TypeError):
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
        intermediate.user_layer = self.active_user_layer
        intermediate.level = self.active_level

        ceiling_lvl = template._properties["Ceiling Level"]["value"]
        try:
            ceiling_off = float(template._properties["Ceiling Offset"]["value"])
        except (ValueError, TypeError):
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
        node.user_layer = self.active_user_layer
        node.level = self.active_level

        ceiling_lvl = getattr(template, "node2_ceiling_level",
                              template._properties["Ceiling Level"]["value"])
        ceiling_off = getattr(template, "node2_ceiling_offset",
                              template.ceiling_offset)
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
        vertical_pipe = Pipe(existing_end_node, intermediate)
        vertical_pipe.user_layer = self.active_user_layer
        vertical_pipe.level = self.active_level
        # Copy physical properties (not ceiling props — endpoints already set)
        for key in ("Diameter", "Schedule", "C-Factor", "Material", "Colour", "Phase"):
            if key in template._properties:
                vertical_pipe.set_property(key, template._properties[key]["value"])
        self.sprinkler_system.add_pipe(vertical_pipe)
        self.addItem(vertical_pipe)
        apply_category_defaults(vertical_pipe)
        vertical_pipe.update_label()

        # Horizontal pipe (start_node <-> intermediate) with full template
        self.add_pipe(start_node, intermediate, template)

        # Refresh fittings on all affected nodes
        start_node.fitting.update()
        existing_end_node.fitting.update()
        intermediate.fitting.update()

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
        mid.user_layer = self.active_user_layer
        mid.level = self.active_level

        ceiling_lvl = template._properties["Ceiling Level"]["value"]
        mid.ceiling_level = ceiling_lvl
        mid._properties["Ceiling Level"]["value"] = ceiling_lvl
        mid.ceiling_offset = template.ceiling_offset
        mid._properties["Ceiling Offset"]["value"] = str(template.ceiling_offset)
        mid.z_pos = target_z

        self.addItem(mid)
        self.sprinkler_system.add_node(mid)

        # Create two replacement vertical pipes preserving the original's properties
        node_a = pipe.node1
        node_b = pipe.node2
        for (na, nb) in ((node_a, mid), (mid, node_b)):
            seg = Pipe(na, nb)
            seg.user_layer = pipe.user_layer
            seg.level = pipe.level
            for key in ("Diameter", "Schedule", "C-Factor",
                        "Material", "Colour", "Phase", "Line Type"):
                seg._properties[key]["value"] = pipe._properties[key]["value"]
            seg.ceiling_level = pipe.ceiling_level
            seg.ceiling_offset = pipe.ceiling_offset
            seg._properties["Ceiling Level"]["value"] = pipe.ceiling_level
            seg._properties["Ceiling Offset"]["value"] = str(pipe.ceiling_offset)
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
        template = pipe
        node_a = pipe.node1
        node_b = pipe.node2
        self.add_pipe(node_a, new_node, template)
        self.add_pipe(new_node, node_b, template)
        self.delete_pipe(pipe)
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
            node.user_layer = self.active_user_layer
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
            transformed.append(t)

        # Derive colour/lineweight from user_layer
        color, lw = self._underlay_color_lw(
            getattr(params, "user_layer", DEFAULT_USER_LAYER))
        pen = QPen(color, lw)
        pen.setCosmetic(True)

        items = []
        for geom in transformed:
            item = self._geom_to_item(geom, pen, color)
            if item is not None:
                items.append(item)

        if not items:
            self.set_mode(None)
            return

        old_method = self.itemIndexMethod()
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        for item in items:
            self.addItem(item)
        group = self.createItemGroup(items)
        group.setZValue(Z_BELOW_GEOMETRY)
        group.setPos(insert_pt)
        group.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        file_type = getattr(params, "file_type", "dxf")
        label = "PDF Underlay" if file_type == "pdf" else "DXF Underlay"
        group.setData(0, label)
        all_layers = sorted({g.get("layer", "0") for g in transformed})
        group.setData(2, all_layers)
        self.setItemIndexMethod(old_method)

        user_layer = getattr(params, "user_layer", DEFAULT_USER_LAYER)
        rotation = getattr(params, "rotation", 0.0)
        record = Underlay(
            type=file_type, path=params.file_path,
            x=insert_pt.x(), y=insert_pt.y(),
            rotation=rotation,
            colour=color.name(),
            line_weight=lw,
            user_layer=user_layer,
        )
        self._apply_underlay_display(group, record)
        self.underlays.append((record, group))
        self.underlaysChanged.emit()
        self.push_undo_state()
        self.set_mode(None)

    def import_dxf(self, file_path, color=QColor("white"), line_weight=0,
                   x=0.0, y=0.0, layers=None, _record: Underlay = None,
                   user_layer: str = DEFAULT_USER_LAYER):
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
        worker = DxfImportWorker(file_path, layers)

        # Store references so they don't get garbage-collected
        self._dxf_worker = worker
        self._dxf_progress = progress
        self._dxf_import_params = {
            "file_path": file_path, "color": color, "line_weight": line_weight,
            "x": x, "y": y, "layers": layers, "_record": _record,
            "user_layer": user_layer,
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
        progress.setLabelText(f"Building {len(geom_list)} items…")
        QApplication.processEvents()

        if not geom_list:
            progress.close()
            self._cleanup_dxf_worker()
            return

        # Derive colour from user_layer if available, otherwise use params["color"]
        ul = params.get("user_layer", DEFAULT_USER_LAYER)
        color, lw = self._underlay_color_lw(ul)
        # Fall back to explicit color if the layer lookup returned default white
        if params.get("color") and ul == DEFAULT_USER_LAYER:
            color = params["color"]
            lw = 1.5
        pen = QPen(color, lw)
        pen.setCosmetic(True)

        items = []
        for geom in geom_list:
            item = self._geom_to_item(geom, pen, color)
            if item is not None:
                items.append(item)

        if not items:
            progress.close()
            self._cleanup_dxf_worker()
            return

        progress.setLabelText(f"Adding {len(items)} items to scene…")
        QApplication.processEvents()

        # Temporarily disable BSP indexing for bulk insertion
        old_method = self.itemIndexMethod()
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

        for item in items:
            self.addItem(item)
        group = self.createItemGroup(items)
        group.setZValue(Z_BELOW_GEOMETRY)
        group.setPos(params["x"], params["y"])
        group.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )
        group.setData(0, "DXF Underlay")

        record = params["_record"] or Underlay(
            type="dxf", path=params["file_path"],
            x=params["x"], y=params["y"],
            colour=color.name(),
            line_weight=params.get("line_weight", lw),
            user_layer=ul,
        )

        # Apply saved display settings
        self._apply_underlay_display(group, record)
        # Store sorted layer list on the group for the LayerManager
        all_layers = sorted({geom.get("layer", "0") for geom in geom_list})
        group.setData(2, all_layers)

        self.underlays.append((record, group))

        # Restore indexing
        self.setItemIndexMethod(old_method)

        progress.close()
        self._cleanup_dxf_worker()
        self.underlaysChanged.emit()
        self._show_status(f"Imported DXF: {params['file_path']} ({len(items)} items)")

    def _geom_to_item(self, geom: dict, pen: QPen, color: QColor):
        """Convert a geometry dict (from DxfImportWorker) into a QGraphicsItem.
        Must be called on the main thread."""
        kind = geom["kind"]
        layer = geom.get("layer", "0")

        if kind == "line":
            item = QGraphicsLineItem(geom["x1"], geom["y1"], geom["x2"], geom["y2"])
            item.setPen(pen)
            item.setZValue(Z_BELOW_GEOMETRY)

        elif kind == "circle":
            item = QGraphicsEllipseItem(geom["x"], geom["y"], geom["w"], geom["h"])
            item.setPen(pen)
            item.setZValue(Z_BELOW_GEOMETRY)

        elif kind == "arc":
            path = QPainterPath()
            rect = QRectF(geom["rx"], geom["ry"], geom["rw"], geom["rh"])
            path.arcMoveTo(rect, geom["start"])
            path.arcTo(rect, geom["start"], geom["span"])
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            item.setZValue(Z_BELOW_GEOMETRY)

        elif kind == "ellipse_full":
            item = QGraphicsEllipseItem(geom["x"], geom["y"], geom["w"], geom["h"])
            item.setPen(pen)
            item.setZValue(Z_BELOW_GEOMETRY)
            item.setPos(geom["pos_cx"], geom["pos_cy"])
            item.setRotation(geom["rotation"])

        elif kind == "path_points":
            points = geom["points"]
            if len(points) < 2:
                return None
            path = QPainterPath()
            path.moveTo(points[0][0], points[0][1])
            for pt in points[1:]:
                path.lineTo(pt[0], pt[1])
            if geom.get("closed"):
                path.closeSubpath()
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            item.setZValue(Z_BELOW_GEOMETRY)

        elif kind == "text":
            item = QGraphicsTextItem(geom["text"])
            item.setPos(geom["x"], geom["y"])
            item.setDefaultTextColor(color)
            if "size" in geom:
                f = QFont()
                f.setPointSizeF(geom["size"])
                item.setFont(f)
            item.setZValue(Z_BELOW_GEOMETRY)

        else:
            return None

        # Tag each item with its DXF layer so LayerManager can toggle visibility
        item.setData(1, layer)
        return item

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
                   _record: Underlay = None):
        import os
        if not os.path.isfile(file_path):
            self._show_status(f"PDF not found: {file_path}")
            log.warning("PDF not found: %s", file_path)
            return

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
        item.setZValue(Z_BELOW_GEOMETRY)
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
            dpi=dpi, page=page
        )

        # Apply saved display settings
        self._apply_underlay_display(item, record)

        self.underlays.append((record, item))
        self.underlaysChanged.emit()
        self._show_status(f"Imported PDF '{file_path}' page {page} at {dpi} DPI")

    # -------------------------------------------------------------------------
    # UNDERLAYS — MANAGEMENT

    def _apply_underlay_display(self, item: QGraphicsItem, record: Underlay):
        """Apply scale, rotation, opacity, and lock state from the record."""
        item.setScale(record.scale)
        item.setRotation(record.rotation)
        item.setOpacity(record.opacity)
        if record.locked:
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

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

        # Remove old item from scene
        idx = None
        for i, (d, it) in enumerate(self.underlays):
            if d is data:
                idx = i
                break
        if item.scene() is self:
            self.removeItem(item)

        # Re-import
        if data.type == "pdf":
            self.import_pdf(
                data.path, dpi=data.dpi, page=data.page,
                x=data.x, y=data.y, _record=data
            )
        elif data.type == "dxf":
            self.import_dxf(
                data.path, color=QColor(data.colour),
                line_weight=data.line_weight,
                x=data.x, y=data.y, _record=data,
                user_layer=data.user_layer,
            )

        # The import functions append a new entry — remove the duplicate old slot if needed
        if idx is not None and idx < len(self.underlays):
            # Find and remove the entry pointing to the old (now removed) item
            # The fresh entry is at the end
            old_entries = [(i, d) for i, (d, it) in enumerate(self.underlays) if d is data]
            if len(old_entries) > 1:
                # Remove the first (stale) one
                self.underlays.pop(old_entries[0][0])

        self._show_status(f"Refreshed underlay: {data.path}")

    def refresh_all_underlays(self):
        """Re-import every underlay from disk."""
        # Take a snapshot since refresh modifies the list
        snapshot = list(self.underlays)
        for data, item in snapshot:
            self.refresh_underlay(data, item)

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
                "z_offset":       getattr(node, "z_offset", node.z_pos),
                "sprinkler":      node.sprinkler.get_properties() if node.has_sprinkler() else None,
                "user_layer":     getattr(node, "user_layer", "0"),
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
                "user_layer": getattr(pipe, "user_layer", "0"),
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
                "user_layer": getattr(dim, "user_layer", DEFAULT_USER_LAYER),
                "level":     getattr(dim, "level", DEFAULT_LEVEL),
            })
        for note in self.annotations.notes:
            annotations_data.append({
                "type": "note",
                "x":    note.scenePos().x(),
                "y":    note.scenePos().y(),
                "text_width": note.textWidth(),
                "properties": {k: v["value"] for k, v in note.get_properties().items()},
                "user_layer": getattr(note, "user_layer", DEFAULT_USER_LAYER),
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
                "properties": {k: v["value"] for k, v in da.get_properties().items()},
                "is_active": da is self.active_design_area,
            })
        return {
            "nodes":              nodes_data,
            "pipes":              pipes_data,
            "annotations":        annotations_data,
            "water_supply":       ws_data,
            "design_areas":       da_data,
            # ── Draw geometry ──────────────────────────────────────────────
            "construction_lines": [cl.to_dict() for cl in self._construction_lines],
            "polylines":          [pl.to_dict() for pl in self._polylines],
            "draw_lines":         [l.to_dict()  for l in self._draw_lines],
            "draw_rectangles":    [r.to_dict()  for r in self._draw_rects],
            "draw_circles":       [c.to_dict()  for c in self._draw_circles],
            "draw_arcs":          [a.to_dict()  for a in self._draw_arcs],
            "gridlines":          [gl.to_dict() for gl in self._gridlines],
            # ── Walls & Floors ────────────────────────────────────────────
            "walls":              [w.to_dict()  for w in self._walls],
            "floor_slabs":        [fs.to_dict() for fs in self._floor_slabs],
            "roofs":              [r.to_dict()  for r in self._roofs],
            "rooms":              [r.to_dict()  for r in self._rooms],
            # ── Hatches & Constraints ─────────────────────────────────────
            "hatches":            [h.to_dict() for h in self._hatch_items
                                  if hasattr(h, 'to_dict')],
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
                node.z_offset = entry.get("z_offset", entry.get("elevation", 0))
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
                node.user_layer = entry.get("user_layer", "0")
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
                    pipe.user_layer = entry.get("user_layer", "0")
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
                    dim.user_layer = entry.get("user_layer", DEFAULT_USER_LAYER)
                    dim.level = entry.get("level", DEFAULT_LEVEL)
                elif ann_type == "note":
                    note = NoteAnnotation(x=entry["x"], y=entry["y"])
                    self.addItem(note)
                    self.annotations.add_note(note)
                    for key, value in entry.get("properties", {}).items():
                        note.set_property(key, value)
                    note.user_layer = entry.get("user_layer", DEFAULT_USER_LAYER)
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
                for key, value in da_entry.get("properties", {}).items():
                    da.set_property(key, value)
                self.addItem(da)
                self.design_areas.append(da)
                if da_entry.get("is_active", False):
                    self.active_design_area = da
                da.compute_area(self.scale_manager)

            # ── Draw geometry ──────────────────────────────────────────────
            # Remove existing items from scene and lists
            for cl in list(self._construction_lines):
                if cl.scene() is self:
                    self.removeItem(cl)
            self._construction_lines.clear()

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

            for h in list(self._hatch_items):
                if h.scene() is self:
                    self.removeItem(h)
            self._hatch_items.clear()

            self._constraints.clear()

            # Restore from snapshot
            for d in state.get("construction_lines", []):
                cl = ConstructionLine.from_dict(d)
                self.addItem(cl)
                self._construction_lines.append(cl)

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

            for d in state.get("gridlines", []):
                gl = GridlineItem.from_dict(d)
                self.addItem(gl)
                self._gridlines.append(gl)

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

            # ── Hatches ───────────────────────────────────────────────────
            for d in state.get("hatches", []):
                try:
                    h = HatchItem.from_dict(d)
                    self.addItem(h)
                    self._hatch_items.append(h)
                except (ValueError, KeyError, TypeError):
                    pass  # skip malformed hatch data

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
            # Refresh property panel and model browser — old references invalid
            self.requestPropertyUpdate.emit(None)
            self.sceneModified.emit()

    def redo(self):
        """Restore the next network state."""
        if self._undo_pos < len(self._undo_stack) - 1:
            self._undo_pos += 1
            self._restore_network(self._undo_stack[self._undo_pos])
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
        self.hydraulic_result = result
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
                p = result.node_pressures.get(node, 0.0)
                q_out = 0.0
                if node.has_sprinkler():
                    try:
                        k = float(node.sprinkler._properties.get(
                            "K-Factor", {}).get("value", 5.6))
                    except (ValueError, TypeError):
                        k = 5.6
                    q_out = k * math.sqrt(max(p, 0.0))
                q_total = 0.0
                for pipe in node.pipes:
                    pf = abs(result.pipe_flows.get(pipe, 0.0))
                    if pf > q_total:
                        q_total = pf
                label = result.node_labels.get(node, str(nn)) if hasattr(result, 'node_labels') else str(nn)
                node.create_hydraulic_badge(nn, p, q_out, q_total,
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

    def _get_draw_color(self) -> str:
        """Return the active layer's colour for new geometry."""
        if hasattr(self, "_user_layer_manager") and self._user_layer_manager:
            ldef = self._user_layer_manager.get(self.active_user_layer)
            if ldef:
                return ldef.color
        return "#ffffff"

    def _get_draw_lineweight(self) -> float:
        """Return the active layer's lineweight as cosmetic screen px."""
        if hasattr(self, "_user_layer_manager") and self._user_layer_manager:
            ldef = self._user_layer_manager.get(self.active_user_layer)
            if ldef:
                return lw_mm_to_cosmetic_px(ldef.lineweight)
        return 2.0

    # -------------------------------------------------------------------------
    # GEOMETRY HELPERS

    def get_snapped_position(self, x, y):
        grid = 1
        return QPointF(round(x / grid) * grid, round(y / grid) * grid)

    def get_effective_position(self, scene_pos: QPointF) -> QPointF:
        """Return best-fit cursor position: OSNAP > underlay snap > grid snap."""
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
                    return result.point
            else:
                self._snap_result = None
        else:
            self._snap_result = None

        # Underlay snap
        if self._snap_to_underlay:
            snap_pt = self.find_snap_point(scene_pos)
            if snap_pt is not None:
                return snap_pt
        return self.get_snapped_position(scene_pos.x(), scene_pos.y())

    def toggle_osnap(self, enabled: bool | None = None):
        """Toggle or explicitly set OSNAP.  Called from ribbon button / F3."""
        if enabled is None:
            self._osnap_enabled = not self._osnap_enabled
        else:
            self._osnap_enabled = bool(enabled)
        self._snap_engine.enabled = self._osnap_enabled
        self._snap_result = None
        # Refresh foreground overlay
        for v in self.views():
            v.viewport().update()

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

    def _get_geometry_template(self):
        """Return (lazily-created) geometry template for line/rect/circle/polyline."""
        from .construction_geometry import GeometryTemplate
        if self._geometry_template is None:
            self._geometry_template = GeometryTemplate()
            self._geometry_template.user_layer = self.active_user_layer
        # Sync with active level
        self._geometry_template.level = self.active_level
        return self._geometry_template

    def _geom_color_lw(self):
        """Return (color, lineweight) derived from the geometry template's layer."""
        tmpl = self._get_geometry_template()
        if hasattr(self, "_user_layer_manager") and self._user_layer_manager:
            ldef = self._user_layer_manager.get(tmpl.user_layer)
            if ldef:
                return ldef.color, lw_mm_to_cosmetic_px(ldef.lineweight)
        return "#ffffff", 2.0

    def _underlay_color_lw(self, user_layer: str = DEFAULT_USER_LAYER):
        """Return (QColor, lineweight_px) derived from a user layer name."""
        if hasattr(self, "_user_layer_manager") and self._user_layer_manager:
            ldef = self._user_layer_manager.get(user_layer)
            if ldef:
                return QColor(ldef.color), lw_mm_to_cosmetic_px(ldef.lineweight)
        return QColor("#ffffff"), 1.5

    # ─────────────────────────────────────────────────────────────────────────

    def _handle_tab_input(self):
        """
        Open a lightweight inline popup to let the user type exact dimensions
        for the current drawing operation (line length+angle, rect W+H,
        circle radius).  Called by Model_View.keyPressEvent when Tab is
        pressed.

        In wall mode, Tab cycles alignment (Center → Interior → Exterior)
        instead of opening the exact-input popup.

        Defaults are computed from the current cursor position relative to
        the anchor point.  Values are always in mm (1 scene unit = 1 mm
        when uncalibrated).  Angles follow Y-up convention (0°=right, 90°=up).
        """
        # ── Select mode: cycle through similar elements ──
        if self.mode in ("select", None, ""):
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
                    return
            return  # in select mode but nothing to cycle — do nothing

        # ── Wall mode: cycle alignment instead of opening dialog ──
        if self.mode in ("wall", "wall_rect"):
            _cycle = {"Center": "Interior", "Interior": "Exterior", "Exterior": "Center"}
            self._wall_alignment = _cycle.get(self._wall_alignment, "Center")
            if self.mode == "wall_rect":
                if self._wall_rect_anchor is None:
                    self.instructionChanged.emit(f"Pick first corner for rectangular wall [{self._wall_alignment}]")
                else:
                    self.instructionChanged.emit(f"Pick opposite corner [{self._wall_alignment}]")
            elif self._wall_anchor is None:
                self.instructionChanged.emit(f"Pick wall start point [{self._wall_alignment}]")
            else:
                self.instructionChanged.emit(f"Pick wall end point [{self._wall_alignment}]")
            # Sync template alignment and update Properties dock live
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
            return

        # ── Offset / Rotate / Scale / Fillet / Chamfer: Tab opens value input ──
        # Dialogs are shown by main.py; results arrive via complete_numeric_input()
        if self.mode == "offset_side":
            default = self._offset_dist if self._offset_dist > 0 else 10.0
            self.numericInputRequested.emit(
                "offset_side", "Offset Distance", "Distance:", default, 0.01, 1_000_000)
            return
        if self.mode == "rotate" and self._rotate_pivot is not None:
            self.numericInputRequested.emit(
                "rotate", "Rotate Angle", "Angle (degrees):", 90.0, -360.0, 360.0)
            return
        if self.mode == "scale" and self._scale_base is not None:
            self.numericInputRequested.emit(
                "scale", "Scale Factor", "Factor:", 2.0, 0.001, 10000.0)
            return
        if self.mode == "fillet" and self._fillet_item2 is not None:
            self.numericInputRequested.emit(
                "fillet", "Fillet Radius", "Radius:", self._fillet_radius, 0.01, 1_000_000)
            return
        if self.mode == "chamfer" and self._chamfer_item2 is not None:
            self.numericInputRequested.emit(
                "chamfer", "Chamfer Distance", "Distance:", self._chamfer_dist, 0.01, 1_000_000)
            return

        cursor = self._last_scene_pos   # may be None on startup

        def _defaults_from(anchor):
            """Return (length_mm, angle_deg) from anchor to cursor."""
            if cursor is None:
                return 100.0, 0.0
            dx = cursor.x() - anchor.x()
            dy = cursor.y() - anchor.y()
            length = math.hypot(dx, dy)
            angle = math.degrees(math.atan2(-dy, dx))   # Y-up convention
            return max(length, 0.01), angle

        # ScaleManager for unit formatting/parsing in Tab input dialogs
        _sm = self.scale_manager

        # ── Inline frameless popup for Dynamic Input ──────────────────────
        class _DynInput(QDialog):
            """Frameless side-by-side input popup (no spinner, no header,
            no OK/Cancel).  Enter accepts, Escape cancels, Tab cycles fields.

            Dimension fields show the formatted value with units inside the
            text box (e.g. ``-0' 2"``).  Angle fields (suffix ``"°"``) keep
            a plain numeric display with the ``°`` suffix label.
            """

            def __init__(self, fields, sm=None, parent=None):
                """*fields*: list of (name, default_mm, suffix, decimals)
                *sm*: ScaleManager for unit formatting/parsing (optional)."""
                super().__init__(parent)
                self._sm = sm
                self.setWindowFlags(
                    Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                )
                self.setStyleSheet(
                    "QDialog   { background: #2d2d2d; border: 1px solid #555;"
                    "            border-radius: 4px; }"
                    "QLabel    { color: #aaaaaa; font: 8pt 'Segoe UI';"
                    "            padding: 0 1px; }"
                    "QLineEdit { background: #1a1a1a; color: #ffffff;"
                    "            border: 1px solid #555; border-radius: 3px;"
                    "            padding: 2px 4px; font: 8pt 'Consolas';"
                    "            min-width: 70px; max-width: 110px; }"
                    "QLineEdit:focus { border-color: #4fa3e0; }"
                )
                lay = QHBoxLayout(self)
                lay.setContentsMargins(6, 4, 6, 4)
                lay.setSpacing(3)
                self._edits = {}
                self._is_dim = {}     # True for dimension fields, False for angle
                self._order = []
                first = None
                for name, default_val, suffix, decimals in fields:
                    is_angle = (suffix == "°")
                    self._is_dim[name] = not is_angle
                    lay.addWidget(QLabel(f"{name}:"))
                    if is_angle:
                        # Angle: plain number + ° suffix label
                        edit = QLineEdit(f"{default_val:.{decimals}f}")
                        edit.setAlignment(Qt.AlignmentFlag.AlignRight)
                        v = QDoubleValidator()
                        v.setDecimals(decimals)
                        edit.setValidator(v)
                        lay.addWidget(edit)
                        lay.addWidget(QLabel("°"))
                    else:
                        # Dimension: formatted value with units inside text box
                        if sm:
                            display_text = sm.format_length(default_val)
                        else:
                            display_text = f"{default_val:.{decimals}f} mm"
                        edit = QLineEdit(display_text)
                        edit.setAlignment(Qt.AlignmentFlag.AlignRight)
                        # No QDoubleValidator — we accept free-form dimension text
                        lay.addWidget(edit)
                    self._edits[name] = edit
                    self._order.append(edit)
                    if first is None:
                        first = edit
                # Position near mouse cursor
                gpos = QCursor.pos()
                self.adjustSize()
                self.move(gpos.x() + 16, gpos.y() + 16)
                if first:
                    first.selectAll()
                    first.setFocus()

            def keyPressEvent(self, event):
                key = event.key()
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.accept()
                elif key == Qt.Key.Key_Escape:
                    self.reject()
                elif key == Qt.Key.Key_Tab:
                    cur = self.focusWidget()
                    if cur in self._order:
                        idx = self._order.index(cur)
                        nxt = self._order[(idx + 1) % len(self._order)]
                        nxt.selectAll()
                        nxt.setFocus()
                    event.accept()
                else:
                    super().keyPressEvent(event)

            def value(self, name):
                """Return value in scene units (mm for dimensions, degrees for angles)."""
                text = self._edits[name].text().strip()
                if self._is_dim.get(name, False) and self._sm:
                    fallback = self._sm.bare_number_unit()
                    parsed = ScaleManager.parse_dimension(text, fallback)
                    if parsed is not None:
                        return parsed
                # Angle or fallback: plain float
                try:
                    return float(text)
                except ValueError:
                    return 0.0

        # ── Move mode: Tab opens dX/dY input after base point is set ──
        if self.mode == "move" and self.node_start_pos is not None:
            dx_mm = 0.0
            dy_mm = 0.0
            if cursor is not None:
                dx_mm = cursor.x() - self.node_start_pos.x()
                dy_mm = -(cursor.y() - self.node_start_pos.y())  # Y-up
            dlg = _DynInput([
                ("dX", dx_mm, "", 2),
                ("dY", dy_mm, "", 2),
            ], sm=_sm)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                offset = QPointF(dlg.value("dX"),
                                 -dlg.value("dY"))  # Y-down
                self.move_items(offset)
                self.push_undo_state()
                self.node_start_pos = None
                self.set_mode(None)
            return

        # ── Line ──────────────────────────────────────────────────────────
        if self.mode == "draw_line" and self._draw_line_anchor is not None:
            anchor = self._draw_line_anchor
            def_len, def_ang = _defaults_from(anchor)

            dlg = _DynInput([
                ("Length", def_len, "", 2),
                ("Angle",  def_ang, "°",  2),
            ], sm=_sm)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            length = dlg.value("Length")
            angle_rad = math.radians(dlg.value("Angle"))
            tip = QPointF(
                anchor.x() + length * math.cos(angle_rad),
                anchor.y() - length * math.sin(angle_rad),  # Y-up → scene Y-down
            )
            tmpl = self._get_geometry_template()
            _c, _lw = self._geom_color_lw()
            item = LineItem(anchor, tip, _c, _lw)
            item.user_layer = tmpl.user_layer
            item.level = tmpl.level
            self.addItem(item)
            self._draw_lines.append(item)
            item.setSelected(True)
            self._draw_line_anchor = None
            self.preview_pipe.hide()
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")

        # ── Construction Line ─────────────────────────────────────────────
        elif self.mode == "construction_line" and self._cline_anchor is not None:
            anchor = self._cline_anchor
            def_len, def_ang = _defaults_from(anchor)

            dlg = _DynInput([
                ("Length", def_len, "", 2),
                ("Angle",  def_ang, "°",  2),
            ], sm=_sm)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            length = dlg.value("Length")
            angle_rad = math.radians(dlg.value("Angle"))
            tip = QPointF(
                anchor.x() + length * math.cos(angle_rad),
                anchor.y() - length * math.sin(angle_rad),
            )
            item = ConstructionLine(anchor, tip)
            item.level = self.active_level
            self.addItem(item)
            self._construction_lines.append(item)
            item.setSelected(True)
            self._cline_anchor = None
            self.preview_pipe.hide()
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")

        # ── Rectangle ────────────────────────────────────────────────────
        elif self.mode == "draw_rectangle" and self._draw_rect_anchor is not None:
            anc = self._draw_rect_anchor
            def_w = abs(cursor.x() - anc.x()) if cursor else 100.0
            def_h = abs(cursor.y() - anc.y()) if cursor else 100.0
            def_w = max(def_w, 0.01)
            def_h = max(def_h, 0.01)

            dlg = _DynInput([
                ("X", def_w, "", 2),
                ("Y", def_h, "", 2),
            ], sm=_sm)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            if self._draw_rect_from_center:
                # Center mode: anchor is center, X/Y are half-extents
                hw = dlg.value("X")
                hh = dlg.value("Y")
                pt1 = QPointF(self._draw_rect_anchor.x() - hw,
                              self._draw_rect_anchor.y() + hh)  # Y-up → scene Y-down
                pt2 = QPointF(self._draw_rect_anchor.x() + hw,
                              self._draw_rect_anchor.y() - hh)
            else:
                pt1 = QPointF(self._draw_rect_anchor.x(),
                              self._draw_rect_anchor.y())
                pt2 = QPointF(
                    self._draw_rect_anchor.x() + dlg.value("X"),
                    self._draw_rect_anchor.y() - dlg.value("Y"),
                )
            tmpl = self._get_geometry_template()
            _c, _lw = self._geom_color_lw()
            item = RectangleItem(pt1, pt2, _c, _lw)
            item.user_layer = tmpl.user_layer
            item.level = tmpl.level
            self.addItem(item)
            self._draw_rects.append(item)
            item.setSelected(True)
            if self._draw_rect_preview is not None:
                self.removeItem(self._draw_rect_preview)
                self._draw_rect_preview = None
            self._draw_rect_anchor = None
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")

        # ── Polyline ─────────────────────────────────────────────────────
        elif self.mode == "polyline" and self._polyline_active is not None:
            anchor = self._polyline_active._points[-1]
            def_len, def_ang = _defaults_from(anchor)

            dlg = _DynInput([
                ("Length", def_len, "", 2),
                ("Angle",  def_ang, "°",  2),
            ], sm=_sm)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            length = dlg.value("Length")
            angle_rad = math.radians(dlg.value("Angle"))
            tip = QPointF(
                anchor.x() + length * math.cos(angle_rad),
                anchor.y() - length * math.sin(angle_rad),  # Y-up → scene Y-down
            )
            self._polyline_active.append_point(tip)
            self.push_undo_state()

        # ── Circle ───────────────────────────────────────────────────────
        elif self.mode == "draw_circle" and self._draw_circle_center is not None:
            center = self._draw_circle_center
            def_r = 50.0
            if cursor is not None:
                def_r = max(math.hypot(cursor.x() - center.x(),
                                       cursor.y() - center.y()), 0.01)

            dlg = _DynInput([
                ("Radius", def_r, "", 2),
            ], sm=_sm)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            r = dlg.value("Radius")
            tmpl = self._get_geometry_template()
            _c, _lw = self._geom_color_lw()
            item = CircleItem(self._draw_circle_center, r, _c, _lw)
            item.user_layer = tmpl.user_layer
            item.level = tmpl.level
            self.addItem(item)
            self._draw_circles.append(item)
            item.setSelected(True)
            if self._draw_circle_preview is not None:
                self.removeItem(self._draw_circle_preview)
                self._draw_circle_preview = None
            self._draw_circle_center = None
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")

    # ─────────────────────────────────────────────────────────────────────────
    # Grid Lines
    # ─────────────────────────────────────────────────────────────────────────

    def place_grid_lines(self, params: dict):
        """Place gridlines from the GridLinesDialog.

        *params* contains key ``"gridlines"`` — a list of dicts with
        keys: label, offset (scene px), length (scene px), angle_deg.

        Gridlines originate at p1 (the bubble end) and extend to p2.
        The bubble overshoot is a fixed 2% of the gridline length so
        it is consistent regardless of zoom level.  Positive offset
        follows architectural convention (right for V, up for H).
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

            # Zoom-independent bubble overshoot: 6% of gridline length
            bubble_overshoot = length * 0.06

            # p1 = bubble end (slightly past origin), p2 = far end
            p1 = QPointF(ox - bubble_overshoot * dx,
                         oy - bubble_overshoot * dy)
            p2 = QPointF(ox + length * dx,
                         oy + length * dy)

            gl = GridlineItem(p1, p2, label=label)
            gl.level = self.active_level
            gl.user_layer = self.active_user_layer
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

    def mouseMoveEvent(self, event):
        scene_pos = event.scenePos()
        self._last_scene_pos = scene_pos
        sm = self.scale_manager
        coord_str = (f"X: {sm.scene_to_display(scene_pos.x())}  "
                     f"Y: {sm.scene_to_display(-scene_pos.y())}")
        self.cursorMoved.emit(coord_str)

        snapped = self.get_effective_position(scene_pos)
        self._draw_dim_hint = None   # cleared each frame; draw modes set it below

        # ── Grip drag (mode-independent, takes priority) ────────────────
        if self._grip_dragging and self._grip_item is not None:
            pos = snapped
            # Ctrl constrains to angle increments from the opposite grip
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and hasattr(self._grip_item, "grip_points")):
                grips = self._grip_item.grip_points()
                if len(grips) >= 2 and self._grip_index != 1:
                    opp = 0 if self._grip_index == len(grips) - 1 else len(grips) - 1
                    pos = self._constrain_angle(grips[opp], snapped)
            # For gridlines: move the same grip on all selected gridlines
            # while keeping the opposite end fixed (length adjusts).
            if isinstance(self._grip_item, GridlineItem):
                old_grips = self._grip_item.grip_points()
                old_pt = old_grips[self._grip_index]
                self._grip_item.apply_grip(self._grip_index, pos)
                new_grips = self._grip_item.grip_points()
                new_pt = new_grips[self._grip_index]
                delta = QPointF(new_pt.x() - old_pt.x(),
                                new_pt.y() - old_pt.y())
                # Apply same grip-index movement to other selected gridlines
                for sel in self.selectedItems():
                    if sel is self._grip_item or not isinstance(sel, GridlineItem):
                        continue
                    sg = sel.grip_points()
                    target = QPointF(sg[self._grip_index].x() + delta.x(),
                                     sg[self._grip_index].y() + delta.y())
                    sel.apply_grip(self._grip_index, target)
            else:
                self._grip_item.apply_grip(self._grip_index, pos)
            self._solve_constraints(self._grip_item)
            # Real-time hatch rebuild during grip drag
            for h in self._hatch_items:
                if getattr(h, '_source_item', None) is self._grip_item:
                    h.rebuild_from_source()
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
        "construction_line":        "_move_draw_line",
        "draw_rectangle":           "_move_draw_rectangle",
        "draw_circle":              "_move_draw_circle",
        "draw_arc":                 "_move_draw_arc",
        "dimension":                "_move_dimension",
        "text":                     "_move_text",
        "gridline":                 "_move_gridline",
        "place_import":             "_move_place_import",
        "offset":                   "_move_offset",
        "offset_side":              "_move_offset_side",
        "move":                     "_move_move",
        "sprinkler":                "_move_preview_node",
        "paste":                    "_move_preview_node",
        "water_supply":             "_move_preview_node",
        "rotate":                   "_move_rotate",
        "mirror":                   "_move_mirror",
        "stretch":                  "_move_stretch",
        "wall":                     "_move_wall",
        "wall_rect":                "_move_wall_rect",
        "floor":                    "_move_floor",
        "floor_rect":               "_move_floor_rect",
        "roof":                     "_move_roof",
        "roof_rect":                "_move_roof_rect",
        "room_manual":              "_move_room_manual",
        "door":                     "_move_door_window",
        "window":                   "_move_door_window",
        "detail":                   "_move_detail",
    }

    # ── Per-mode move handlers ──────────────────────────────────────────

    def _move_pipe(self, event, snapped):
        if self.node_start_pos:
            start = self.node_start_pos.scenePos()
            snapped_end = self.node_start_pos.snap_point_45(start, snapped)
            self.update_preview_node(snapped_end)
            self.preview_pipe.setLine(start.x(), start.y(), snapped_end.x(), snapped_end.y())

            # Style preview from current template
            template = getattr(self, "current_template", None)
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
            self.update_preview_node(snapped)
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

    def _move_polyline(self, event, snapped):
        sm = self.scale_manager
        if self._polyline_active is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._polyline_active is not None:
            tip = snapped
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and len(self._polyline_active._points) >= 1):
                tip = self._constrain_angle(
                    self._polyline_active._points[-1], snapped
                )
            self._polyline_active.update_preview(tip)
            _last = self._polyline_active._points[-1]
            _dx = tip.x() - _last.x()
            _dy = tip.y() - _last.y()
            _len = math.hypot(_dx, _dy)
            _ang = math.degrees(math.atan2(-_dy, _dx))
            self._draw_dim_hint = (
                f"L: {sm.scene_to_display(_len)}  A: {_ang:.1f}°"
                if sm.is_calibrated else
                f"L: {_len:.0f}mm  A: {_ang:.1f}°"
            )

    def _move_draw_line(self, event, snapped):
        sm = self.scale_manager
        _anchor = self._draw_line_anchor if self.mode == "draw_line" else self._cline_anchor
        if _anchor is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        if _anchor is not None:
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._constrain_angle(_anchor, snapped)
            self.preview_pipe.setLine(
                _anchor.x(), _anchor.y(),
                tip.x(), tip.y()
            )
            self.preview_pipe.show()
            _dx = tip.x() - _anchor.x()
            _dy = tip.y() - _anchor.y()
            _len = math.hypot(_dx, _dy)
            _ang = math.degrees(math.atan2(-_dy, _dx))
            self._draw_dim_hint = (
                f"L: {sm.scene_to_display(_len)}  A: {_ang:.1f}°"
                if sm.is_calibrated else
                f"L: {_len:.0f}mm  A: {_ang:.1f}°"
            )
        else:
            self.preview_pipe.hide()

    def _move_draw_rectangle(self, event, snapped):
        sm = self.scale_manager
        if self._draw_rect_anchor is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._draw_rect_anchor is not None and self._draw_rect_preview is not None:
            if self._draw_rect_from_center:
                # Center mode: anchor is center, rect extends symmetrically
                hw = abs(snapped.x() - self._draw_rect_anchor.x())
                hh = abs(snapped.y() - self._draw_rect_anchor.y())
                rect = QRectF(
                    self._draw_rect_anchor.x() - hw,
                    self._draw_rect_anchor.y() - hh,
                    2 * hw, 2 * hh,
                )
            else:
                rect = QRectF(self._draw_rect_anchor, snapped).normalized()
            self._draw_rect_preview.setRect(rect)
            self._draw_dim_hint = (
                f"W: {sm.scene_to_display(rect.width())}  H: {sm.scene_to_display(rect.height())}"
                if sm.is_calibrated else
                f"W: {rect.width():.0f}mm  H: {rect.height():.0f}mm"
            )

    def _move_draw_circle(self, event, snapped):
        sm = self.scale_manager
        if self._draw_circle_center is None:
            self.update_preview_node(snapped)   # cursor preview before first click
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._draw_circle_center is not None and self._draw_circle_preview is not None:
            r = math.hypot(snapped.x() - self._draw_circle_center.x(),
                           snapped.y() - self._draw_circle_center.y())
            cx, cy = self._draw_circle_center.x(), self._draw_circle_center.y()
            self._draw_circle_preview.setRect(cx - r, cy - r, 2 * r, 2 * r)
            self._draw_dim_hint = (
                f"R: {sm.scene_to_display(r)}"
                if sm.is_calibrated else
                f"R: {r:.0f}mm"
            )

    def _move_draw_arc(self, event, snapped):
        sm = self.scale_manager
        self.preview_pipe.hide()
        if self._draw_arc_step == 0:
            # Before first click — show cursor preview
            self.update_preview_node(snapped)
        elif self._draw_arc_step == 1:
            # After centre click — update radius line to cursor
            self.preview_node.hide()
            if self._draw_arc_radius_line is not None:
                cx = self._draw_arc_center.x()
                cy = self._draw_arc_center.y()
                self._draw_arc_radius_line.setLine(cx, cy,
                                                    snapped.x(), snapped.y())
                r = math.hypot(snapped.x() - cx, snapped.y() - cy)
                self._draw_dim_hint = (
                    f"R: {sm.scene_to_display(r)}"
                    if sm.is_calibrated else
                    f"R: {r:.0f}mm"
                )
        elif self._draw_arc_step == 2:
            # After start click — update arc preview to cursor angle
            self.preview_node.hide()
            if self._draw_arc_preview is not None:
                cx = self._draw_arc_center.x()
                cy = self._draw_arc_center.y()
                r = self._draw_arc_radius
                end_deg = math.degrees(
                    math.atan2(-(snapped.y() - cy), snapped.x() - cx)
                )
                span = end_deg - self._draw_arc_start_deg
                if span <= 0:
                    span += 360.0
                path = QPainterPath()
                rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
                path.arcMoveTo(rect, self._draw_arc_start_deg)
                path.arcTo(rect, self._draw_arc_start_deg, span)
                self._draw_arc_preview.setPath(path)
                self._draw_dim_hint = f"Span: {span:.1f}\u00b0"

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

    def _move_gridline(self, event, snapped):
        if self._gridline_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
            self.preview_pipe.setLine(
                self._gridline_anchor.x(), self._gridline_anchor.y(),
                snapped.x(), snapped.y()
            )
            self.preview_pipe.show()

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

    def _move_move(self, event, snapped):
        self.update_preview_node(snapped)
        self.preview_pipe.hide()
        if self.node_start_pos is not None:
            # Show rubber-band line from base point to cursor
            if self._move_preview_line is None:
                self._move_preview_line = QGraphicsLineItem()
                pen = QPen(QColor("#00aaff"), 0)
                pen.setCosmetic(True)
                pen.setStyle(Qt.PenStyle.DashLine)
                self._move_preview_line.setPen(pen)
                self._move_preview_line.setZValue(200)
                self.addItem(self._move_preview_line)
            self._move_preview_line.setLine(
                self.node_start_pos.x(), self.node_start_pos.y(),
                snapped.x(), snapped.y())
            self._move_preview_line.show()
            # Show displacement in status bar
            dx = snapped.x() - self.node_start_pos.x()
            dy = snapped.y() - self.node_start_pos.y()
            self._show_status(
                f"Move: dx={dx:.1f}  dy={dy:.1f}  "
                f"dist={math.hypot(dx, dy):.1f}", timeout=0)

    def _move_preview_node(self, event, snapped):
        self.update_preview_node(snapped)
        self.preview_pipe.hide()

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
        sm = self.scale_manager
        if self._wall_rect_anchor is None:
            self.update_preview_node(snapped)
        else:
            self.preview_node.hide()
        self.preview_pipe.hide()
        if self._wall_rect_anchor is not None and self._wall_rect_preview is not None:
            rect = QRectF(self._wall_rect_anchor, snapped).normalized()
            self._wall_rect_preview.setRect(rect)
            self._draw_dim_hint = (
                f"W: {sm.scene_to_display(rect.width())}  "
                f"H: {sm.scene_to_display(rect.height())}"
            )
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
        "gridline":                 "_press_gridline",
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
        "hatch":                    "_press_merge_hatch",
        "constraint_concentric":    "_press_constraint",
        "constraint_dimensional":   "_press_constraint",
        "polyline":                 "_press_polyline",
        "draw_line":                "_press_draw_line",
        "construction_line":        "_press_construction_line",
        "draw_rectangle":           "_press_draw_rectangle",
        "draw_circle":              "_press_draw_circle",
        "wall":                     "_press_wall",
        "wall_rect":                "_press_wall_rect",
        "floor":                    "_press_floor",
        "floor_rect":               "_press_floor_rect",
        "roof":                     "_press_roof",
        "roof_rect":                "_press_roof_rect",
        "door":                     "_press_door",
        "window":                   "_press_window",
        "detail":                   "_press_detail",
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
                    vert = Pipe(start_node, intermediate)
                    vert.user_layer = self.active_user_layer
                    vert.level = self.active_level
                    for key in ("Diameter", "Schedule", "C-Factor",
                                "Material", "Colour", "Phase"):
                        vert._properties[key]["value"] = template._properties[key]["value"]
                    self.sprinkler_system.add_pipe(vert)
                    self.addItem(vert)
                    vert.set_pipe_display()
                    self.node_start_pos = intermediate
                self.instructionChanged.emit("Pick end node")

            elif result == "match":
                # Place pipe at existing node's elevation
                template.set_property("Ceiling Level", start_node.ceiling_level)
                template.set_property("Ceiling Offset", start_node.ceiling_offset)
                self.requestPropertyUpdate.emit(template)
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
                    vert = Pipe(intermediate, end_node)
                    vert.user_layer = self.active_user_layer
                    vert.level = self.active_level
                    for key in ("Diameter", "Schedule", "C-Factor",
                                "Material", "Colour", "Phase"):
                        vert._properties[key]["value"] = template._properties[key]["value"]
                    self.sprinkler_system.add_pipe(vert)
                    self.addItem(vert)
                    vert.set_pipe_display()
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
                # Place pipe at existing node's elevation
                template.set_property("Ceiling Level", end_node.ceiling_level)
                template.set_property("Ceiling Offset", end_node.ceiling_offset)
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
        # Also check for walls, floors, roofs, view markers (lower Z-order)
        if selection is None:
            selection = next(
                (i for i in items
                 if (isinstance(i, (WallSegment, FloorSlab, RoofItem, Room,
                                    ViewMarkerArrow))
                     or type(i).__name__ == "DetailMarker")
                 and i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable),
                None,
            )

        # Derive typed references for handler signature
        node_under = selection if isinstance(selection, Node) else None
        pipe_under = selection if isinstance(selection, Pipe) else None

        # ── Grip hit takes priority over mode handlers ──────────────────
        # Skip grip detection in drawing modes so clicks reach the draw handler
        _skip_grip_modes = ("wall", "wall_rect", "floor", "floor_rect", "pipe", "sprinkler",
                            "draw_line", "construction_line", "draw_rectangle",
                            "draw_circle", "draw_arc", "polyline", "gridline",
                            "dimension", "text", "door", "window", "set_scale",
                            "detail")
        if (self.mode not in _skip_grip_modes
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            grip_hit = self._find_grip_hit(snapped)
            if grip_hit is not None:
                if self.mode == "move" and self.node_start_pos is None:
                    # In move mode, use grip point as precise base point
                    item, idx = grip_hit
                    self.node_start_pos = item.grip_points()[idx]
                    self.instructionChanged.emit("Pick destination point")
                    return
                self._grip_item, self._grip_index = grip_hit
                self._grip_dragging = True
                return  # consumed by grip system

        # ── Dispatch to per-mode handler ────────────────────────────────
        handler_name = self._PRESS_DISPATCH.get(self.mode)
        if handler_name is not None:
            getattr(self, handler_name)(event, scene_pos, snapped,
                                        selection, node_under, pipe_under)
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

            # Check for existing node BEFORE find_or_create_node
            existing_start = self.find_nearby_node(snapped.x(), snapped.y())

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
                start_node = self.find_or_create_node(snapped.x(), snapped.y())
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
            start_pipes = len(self.node_start_pos.pipes)
            if start_pipes >= 4:
                self.warningIssued.emit(
                    "Connection Limit",
                    f"Start node already has {start_pipes} connections (max 4).")
                return
            # Adding a 4th branch is only valid to turn a tee into a cross
            if start_pipes == 3:
                err = self._validate_4th_branch(self.node_start_pos, snapped_end)
                if err:
                    self.warningIssued.emit("Invalid Connection", err)
                    return
            existing_end_check = self.find_nearby_node(snapped_end.x(), snapped_end.y())
            if existing_end_check is not None:
                end_pipes = len(existing_end_check.pipes)
                if end_pipes >= 4:
                    self.warningIssued.emit(
                        "Connection Limit",
                        f"Target node already has {end_pipes} connections (max 4).")
                    return
                if end_pipes == 3:
                    err = self._validate_4th_branch(
                        existing_end_check,
                        self.node_start_pos.scenePos())
                    if err:
                        self.warningIssued.emit("Invalid Connection", err)
                        return

            # Check for existing node BEFORE find_or_create_node
            existing_end = self.find_nearby_node(snapped_end.x(), snapped_end.y())

            if isinstance(item_under, Pipe):
                end_node = self.split_pipe(item_under, self.project_click_onto_pipe_segment(snapped_end, item_under))
                _check_end_elev = True  # split node inherits pipe's Z
            else:
                end_node = self.find_or_create_node(snapped_end.x(), snapped_end.y())
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
                dim.user_layer = "Annotations"
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
            dim.user_layer = "Annotations"
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
            note.user_layer = "Annotations"
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
            # Click 2 — set start point (defines radius + start angle)
            cx, cy = self._draw_arc_center.x(), self._draw_arc_center.y()
            r = math.hypot(snapped.x() - cx, snapped.y() - cy)
            if r < 0.01:
                return
            self._draw_arc_radius = r
            self._draw_arc_start_deg = math.degrees(
                math.atan2(-(snapped.y() - cy), snapped.x() - cx)
            )
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
        elif self._draw_arc_step == 2:
            # Click 3 — set end point → commit arc
            cx, cy = self._draw_arc_center.x(), self._draw_arc_center.y()
            end_deg = math.degrees(
                math.atan2(-(snapped.y() - cy), snapped.x() - cx)
            )
            span = end_deg - self._draw_arc_start_deg
            # Normalise span to positive CCW direction
            if span <= 0:
                span += 360.0
            # Reject near-zero arcs
            if abs(span) < 0.5 or abs(span - 360.0) < 0.5:
                self._show_status("Arc span too small — skipped", timeout=2000)
                return
            tmpl = self._get_geometry_template()
            _c, _lw = self._geom_color_lw()
            item = ArcItem(self._draw_arc_center, self._draw_arc_radius,
                           self._draw_arc_start_deg, span, _c, _lw)
            item.user_layer = tmpl.user_layer
            item.level = tmpl.level
            self.addItem(item)
            self._draw_arcs.append(item)
            item.setSelected(True)
            for v in self.views(): v.viewport().update()
            # Clean up previews
            if self._draw_arc_preview is not None:
                self.removeItem(self._draw_arc_preview)
                self._draw_arc_preview = None
            self._draw_arc_center = None
            self._draw_arc_radius = 0.0
            self._draw_arc_start_deg = 0.0
            self._draw_arc_step = 0
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")
            else:
                self.instructionChanged.emit("Pick center point")

    def _press_gridline(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._gridline_anchor is None:
            self._gridline_anchor = snapped
            self.instructionChanged.emit("Pick end point")
        else:
            # Create gridline from anchor to snapped
            gl = GridlineItem(self._gridline_anchor, snapped)
            gl.user_layer = self.active_user_layer
            gl.level = self.active_level
            self.addItem(gl)
            apply_category_defaults(gl)
            self._gridlines.append(gl)
            self.requestPropertyUpdate.emit(gl)
            gl.setSelected(True)
            for v in self.views(): v.viewport().update()
            self._gridline_anchor = None
            self.preview_pipe.hide()
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")
            else:
                self.instructionChanged.emit("Pick start point")

    def _press_water_supply(self, event, pos, snapped, item_under, node_under, pipe_under):
        # Require placement on a node or pipe (split to create node)
        if isinstance(item_under, Node):
            target_node = item_under
        elif isinstance(item_under, Pipe):
            target_node = self.split_pipe(
                item_under,
                self.project_click_onto_pipe_segment(snapped, item_under),
            )
        else:
            target_node = self.find_nearby_node(snapped.x(), snapped.y())

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
                selected_sprs = [
                    s for s in self.sprinkler_system.sprinklers
                    if s.node and selection_rect.contains(s.node.scenePos())
                ]
                # Remove the temporary preview rect
                if self._design_area_rect_item and self._design_area_rect_item.scene() is self:
                    self.removeItem(self._design_area_rect_item)
                self._design_area_rect_item = None
                self._design_area_corner1 = None
                # Create/update design area with selected sprinklers
                if not self.active_design_area:
                    da = DesignArea(selected_sprs)
                    self.addItem(da)
                    self.design_areas.append(da)
                    self.active_design_area = da
                else:
                    for s in selected_sprs:
                        self.active_design_area.add_sprinkler(s)
                if self.active_design_area:
                    self.active_design_area.compute_area(self.scale_manager)
                count = len(self.active_design_area.sprinklers) if self.active_design_area else 0
                self._show_status(f"Design area: {count} sprinkler(s). Click more or right-click to confirm.")
        else:
            # Normal click: toggle individual sprinkler
            # Find sprinkler node near click
            target_spr = None
            for spr in self.sprinkler_system.sprinklers:
                if spr.node and spr.node.distance_to(snapped.x(), snapped.y()) < 40:
                    target_spr = spr
                    break
            if target_spr:
                if not self.active_design_area:
                    da = DesignArea()
                    self.addItem(da)
                    self.design_areas.append(da)
                    self.active_design_area = da
                self.active_design_area.toggle_sprinkler(target_spr)
                self.active_design_area.compute_area(self.scale_manager)
                count = len(self.active_design_area.sprinklers)
                self._show_status(f"Design area: {count} sprinkler(s). Click more or right-click to confirm.")
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

        # The boundary walk traces wall centerlines. For non-center alignments
        # we need a half-wall-width inset to reach the interior face:
        #   Center   → no adjustment (centerline = wall center, already correct)
        #   Interior → inset by half thickness (centerline is at interior face,
        #              room face is half-thickness inward)
        #   Exterior → inset by half thickness (centerline is at exterior face,
        #              room face is half-thickness inward)
        align_counts = {"Center": 0, "Interior": 0, "Exterior": 0}
        total_ht = 0.0
        for w in walls:
            align_counts[w._alignment] = align_counts.get(w._alignment, 0) + 1
            total_ht += w.half_thickness_scene()
        avg_ht = total_ht / len(walls) if walls else 0.0

        dominant = max(align_counts, key=align_counts.get)
        # All alignments need inset to reach the inner wall face:
        #   Center   → centerline is at wall center → inset by half thickness (shrink)
        #   Interior → centerline is at interior face → inset by half thickness (shrink)
        #   Exterior → centerline is at exterior face → inset by half thickness (expand)
        # Determine inset needed to reach interior face from the boundary walk
        # (which traces wall centerlines/axes):
        #   Center   → axis at wall center → inset by half thickness (shrink)
        #   Interior → axis IS the interior face → no inset needed
        #   Exterior → axis at exterior face → inset by full thickness (shrink)
        if dominant == "Exterior":
            inset_dist = 0.0
        elif dominant == "Interior":
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
            room.user_layer = self.active_user_layer
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
                    if self.single_place_mode:
                        self.set_mode("select")
                    else:
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
        else:
            offset = CAD_Math.get_vector(self.node_start_pos, snapped)
            if self.mode == "paste":
                self.paste_items(offset)
            elif self.mode == "move":
                self.move_items(offset)
            self.push_undo_state()
            self.node_start_pos = None
            self.set_mode(None)

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
        elif self.mode == "hatch":
            self._handle_hatch_click(snapped)

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
            pl.user_layer = tmpl.user_layer
            pl.level = tmpl.level
            self.addItem(pl)
            self._polylines.append(pl)
            self._polyline_active = pl
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick next point (Enter to finish)")
        else:
            # Subsequent clicks — append vertex (apply Ctrl constraint if held)
            tip = snapped
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and len(self._polyline_active._points) >= 1):
                tip = self._constrain_angle(
                    self._polyline_active._points[-1], snapped
                )
            self._polyline_active.append_point(tip)
        # don't let super() deselect items mid-draw

    def _press_draw_line(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._draw_line_anchor is None:
            self._draw_line_anchor = snapped
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick second point")
        else:
            # Place the line (apply Ctrl constraint if held)
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._constrain_angle(self._draw_line_anchor, snapped)
            # Reject zero-length lines
            if math.hypot(tip.x() - self._draw_line_anchor.x(),
                          tip.y() - self._draw_line_anchor.y()) < 0.5:
                self._show_status("Line too short — skipped", timeout=2000)
                return
            tmpl = self._get_geometry_template()
            _c, _lw = self._geom_color_lw()
            item = LineItem(self._draw_line_anchor, tip, _c, _lw)
            item.user_layer = tmpl.user_layer
            item.level = tmpl.level
            self.addItem(item)
            self._draw_lines.append(item)
            item.setSelected(True)
            for v in self.views(): v.viewport().update()
            self._draw_line_anchor = None
            self.preview_pipe.hide()
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")
            else:
                self.instructionChanged.emit("Pick first point")

    def _press_construction_line(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._cline_anchor is None:
            self._cline_anchor = snapped
            self.update_preview_node(snapped)
            self.instructionChanged.emit("Pick second point")
        else:
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._constrain_angle(self._cline_anchor, snapped)
            if math.hypot(tip.x() - self._cline_anchor.x(),
                          tip.y() - self._cline_anchor.y()) < 0.5:
                self._show_status("Construction line too short — skipped", timeout=2000)
                return
            item = ConstructionLine(self._cline_anchor, tip)
            item.level = self.active_level
            self.addItem(item)
            self._construction_lines.append(item)
            item.setSelected(True)
            for v in self.views(): v.viewport().update()
            self._cline_anchor = None
            self.preview_pipe.hide()
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")
            else:
                self.instructionChanged.emit("Pick first point")

    def _press_draw_rectangle(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._draw_rect_anchor is None:
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
            # Commit rectangle
            if self._draw_rect_from_center:
                hw = abs(snapped.x() - self._draw_rect_anchor.x())
                hh = abs(snapped.y() - self._draw_rect_anchor.y())
                pt1 = QPointF(self._draw_rect_anchor.x() - hw, self._draw_rect_anchor.y() - hh)
                pt2 = QPointF(self._draw_rect_anchor.x() + hw, self._draw_rect_anchor.y() + hh)
            else:
                rect = QRectF(self._draw_rect_anchor, snapped).normalized()
                pt1 = QPointF(rect.x(), rect.y())
                pt2 = QPointF(rect.x() + rect.width(), rect.y() + rect.height())
            # Reject zero-size rectangles
            if abs(pt2.x() - pt1.x()) < 0.5 or abs(pt2.y() - pt1.y()) < 0.5:
                self._show_status("Rectangle too small — skipped", timeout=2000)
                return
            tmpl = self._get_geometry_template()
            _c, _lw = self._geom_color_lw()
            item = RectangleItem(pt1, pt2, _c, _lw)
            item.user_layer = tmpl.user_layer
            item.level = tmpl.level
            self.addItem(item)
            self._draw_rects.append(item)
            item.setSelected(True)
            for v in self.views(): v.viewport().update()
            # Remove preview
            if self._draw_rect_preview is not None:
                self.removeItem(self._draw_rect_preview)
                self._draw_rect_preview = None
            self._draw_rect_anchor = None
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")
            else:
                _instr = "Pick center point" if self._draw_rect_from_center else "Pick first corner"
                self.instructionChanged.emit(_instr)

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
            # Commit circle
            r = math.hypot(snapped.x() - self._draw_circle_center.x(),
                           snapped.y() - self._draw_circle_center.y())
            if r < 0.5:
                self._show_status("Circle radius too small — skipped", timeout=2000)
            if r >= 0.5:
                tmpl = self._get_geometry_template()
                _c, _lw = self._geom_color_lw()
                item = CircleItem(self._draw_circle_center, r, _c, _lw)
                item.user_layer = tmpl.user_layer
                item.level = tmpl.level
                self.addItem(item)
                self._draw_circles.append(item)
                item.setSelected(True)
                for v in self.views(): v.viewport().update()
            # Remove preview
            if self._draw_circle_preview is not None:
                self.removeItem(self._draw_circle_preview)
                self._draw_circle_preview = None
            self._draw_circle_center = None
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")
            else:
                self.instructionChanged.emit("Pick center point")

    # ── Wall drawing ──────────────────────────────────────────────────
    def _press_wall(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._wall_anchor is None:
            self._wall_anchor = snapped
            self._wall_chain_start = QPointF(snapped)
            self.update_preview_node(snapped)
            self.instructionChanged.emit(f"Pick wall end point [{self._wall_alignment}]  Tab=cycle")
        else:
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
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
            wall.user_layer = self.active_user_layer
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
            if _close_loop:
                # Loop closed — stop wall chain
                self._wall_anchor = None
                self._wall_chain_start = None
                if self.single_place_mode:
                    self.set_mode("select")
                else:
                    self.instructionChanged.emit(
                        f"Pick wall start point [{self._wall_alignment}]")
            else:
                # Chain: end of this wall becomes start of next
                self._wall_anchor = QPointF(tip)
                self.instructionChanged.emit(
                    f"Pick next wall end [{self._wall_alignment}]  Tab=cycle  Esc=stop")

    # ── Wall rectangle drawing ──────────────────────────────────────────
    def _press_wall_rect(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._wall_rect_anchor is None:
            self._wall_rect_anchor = snapped
            self.instructionChanged.emit("Pick opposite corner for rectangular wall")
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
            # Commit rectangular wall — create 4 wall segments
            rect = QRectF(self._wall_rect_anchor, snapped).normalized()
            corners = [
                QPointF(rect.x(), rect.y()),                          # top-left
                QPointF(rect.x() + rect.width(), rect.y()),           # top-right
                QPointF(rect.x() + rect.width(), rect.y() + rect.height()),  # bottom-right
                QPointF(rect.x(), rect.y() + rect.height()),          # bottom-left
            ]
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
                wall.user_layer = self.active_user_layer
                self._wall_alignment = _tmpl._alignment
                self.addItem(wall)
                self._walls.append(wall)
                apply_category_defaults(wall)
                walls_created.append(wall)
            # Auto-join all walls
            for wall in walls_created:
                self._auto_join_wall(wall)
                wall.setSelected(True)
            for v in self.views():
                v.viewport().update()
            # Clean up preview
            if self._wall_rect_preview is not None:
                self.removeItem(self._wall_rect_preview)
                self._wall_rect_preview = None
            if self._wall_rect_thickness_preview is not None:
                if self._wall_rect_thickness_preview.scene() is self:
                    self.removeItem(self._wall_rect_thickness_preview)
                self._wall_rect_thickness_preview = None
            self._wall_rect_anchor = None
            self.push_undo_state()
            if self.single_place_mode:
                self.set_mode("select")
            else:
                self.instructionChanged.emit("Pick first corner for rectangular wall")

    # ── Floor drawing ─────────────────────────────────────────────────
    def _press_floor(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._floor_active is None:
            _ftmpl = self._get_floor_template()
            slab = FloorSlab(color=_ftmpl._color.name())
            slab.name = f"Floor {self._next_floor_num}"
            self._next_floor_num += 1
            slab._thickness_mm = _ftmpl._thickness_mm
            slab.level = _ftmpl.level if _ftmpl.level else self.active_level
            slab.user_layer = self.active_user_layer
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
                    if self.single_place_mode:
                        self.set_mode("select")
                    else:
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
            slab.user_layer = self.active_user_layer
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
            if self.single_place_mode:
                self.set_mode("select")
            else:
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
            roof.user_layer = self.active_user_layer
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
                    if self.single_place_mode:
                        self.set_mode("select")
                    else:
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
            roof.user_layer = self.active_user_layer
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
            if self.single_place_mode:
                self.set_mode("select")
            else:
                self.instructionChanged.emit("Pick first corner for rectangular roof")

    # ── Door placement ────────────────────────────────────────────────
    def _press_door(self, event, pos, snapped, item_under, node_under, pipe_under):
        wall = self._find_wall_at(snapped)
        if wall is not None:
            offset = self._offset_along_wall(wall, snapped)
            door = DoorOpening(wall=wall, offset_along=offset)
            door.level = wall.level
            door.user_layer = wall.user_layer
            wall.openings.append(door)
            self.addItem(door)
            self.push_undo_state()
            self.instructionChanged.emit("Click on a wall to place another door")

    # ── Window placement ──────────────────────────────────────────────
    def _press_window(self, event, pos, snapped, item_under, node_under, pipe_under):
        wall = self._find_wall_at(snapped)
        if wall is not None:
            offset = self._offset_along_wall(wall, snapped)
            win = WindowOpening(wall=wall, offset_along=offset)
            win.level = wall.level
            win.user_layer = wall.user_layer
            wall.openings.append(win)
            self.addItem(win)
            self.push_undo_state()
            self.instructionChanged.emit("Click on a wall to place another window")

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
        if event.button() == Qt.MouseButton.LeftButton and self._grip_dragging:
            self._solve_constraints(self._grip_item)  # enforce constraints
            # Rebuild any hatches whose source was the dragged item
            for h in self._hatch_items:
                if getattr(h, '_source_item', None) is self._grip_item:
                    h.rebuild_from_source()
            self._grip_dragging = False
            self._grip_item     = None
            self._grip_index    = -1
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
            # Double-click fires two mousePressEvents first, adding an extra
            # vertex.  Remove that extra point before finalizing.
            pts = self._polyline_active._points
            # Double-click fires two mousePressEvents, each adding a point
            if len(pts) > 2:
                pts.pop()
            if len(pts) > 2:
                pts.pop()
            if len(pts) >= 2:
                pl = self._polyline_active
                pl.finalize()
                self._polyline_active = None
                pl.setSelected(True)
                for v in self.views(): v.viewport().update()
                self.push_undo_state()
                if self.single_place_mode:
                    self.set_mode("select")
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
                if self.single_place_mode:
                    self.set_mode("select")
                else:
                    self.instructionChanged.emit("Pick first boundary point (double-click to close)")
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Show context menu on right-click for underlays or scene entities."""
        # Right-click confirms design area selection
        if self.mode == "design_area":
            if self.active_design_area and self.active_design_area.sprinklers:
                self.active_design_area.compute_area(self.scale_manager)
                count = len(self.active_design_area.sprinklers)
                self._show_status(f"Design area confirmed: {count} sprinkler(s).")
                self.requestPropertyUpdate.emit(self.active_design_area)
            self.set_mode(None)
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
            ConstructionLine, PolylineItem, LineItem, RectangleItem,
            CircleItem, ArcItem, GridlineItem, HatchItem, WaterSupply,
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
        )
        menu.exec(screen_pos)

    def _auto_populate_room_dialog(self, room):
        """Open the auto-populate dialog for a room and place sprinklers."""
        from .auto_populate_dialog import AutoPopulateDialog
        from .sprinkler_db import SprinklerDatabase

        db = SprinklerDatabase()
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
            item.setVisible(False)

    def _show_items(self, items):
        """Show the given items via display overrides."""
        for item in items:
            if hasattr(item, "_display_overrides"):
                item._display_overrides.pop("visible", None)
            item.setVisible(True)

    def _show_all_hidden(self):
        """Restore visibility for all manually hidden items."""
        from .floor_slab import FloorSlab
        from .room import Room
        for item in self.items():
            if hasattr(item, "_display_overrides"):
                if item._display_overrides.get("visible") is False:
                    item._display_overrides.pop("visible", None)
                    item.setVisible(True)

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
                    if self._level_manager:
                        lvl = self._level_manager.get(target_level)
                        if lvl:
                            item.z_pos = lvl.elevation + item.z_offset  # z_offset is legacy (may be ft from old saves)

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
        for lst in [self._construction_lines, self._polylines, self._draw_lines,
                    self._draw_rects, self._draw_circles, self._draw_arcs,
                    self._gridlines, self._hatch_items,
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

    def _auto_join_wall(self, wall: WallSegment, tolerance: float = 20.0):
        """Snap wall endpoints to nearby existing wall endpoints (miter join)
        and to mid-wall faces (tee join)."""
        TEE_TOLERANCE = 40.0  # larger search radius for tee intersections

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

        # Pass 2: tee join — snap unsnapped endpoints to mid-wall faces.
        # The reference_point is the wall's OTHER endpoint so the new wall
        # terminates on the face of the existing wall that is nearest to
        # the start (or end) of the new wall.
        for other in self._walls:
            if other is wall:
                continue
            for my_idx in (0, 1):
                if my_idx in snapped:
                    continue
                my_pt = wall.pt1 if my_idx == 0 else wall.pt2
                # Reference = the other end of the new wall
                ref_pt = wall.pt2 if my_idx == 0 else wall.pt1
                face_pt = other.nearest_face_point(
                    my_pt, TEE_TOLERANCE, self.scale_manager,
                    reference_point=ref_pt)
                if face_pt is not None:
                    wall.snap_endpoint_to(my_idx, face_pt)
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
            # Pipe polyline: first Escape ends the chain, second exits mode
            if self.mode == "pipe" and self.node_start_pos is not None:
                self.node_start_pos = None
                self._pipe_node_was_new = False
                self.preview_pipe.hide()
                self.preview_node.hide()
                self.instructionChanged.emit("Pick start node")
                return
            if self.mode and self.mode not in (None, "select"):
                self._show_status("Mode cancelled", 2000)
            self.set_mode(None)
        elif event.key() == Qt.Key.Key_Delete:
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
                    pl.setSelected(True)
                    self.push_undo_state()
                    if self.single_place_mode:
                        self.set_mode("select")
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
                    if self.single_place_mode:
                        self.set_mode("select")
                    else:
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
                    if self.single_place_mode:
                        self.set_mode("select")
                    else:
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
                    if self.single_place_mode:
                        self.set_mode("select")
                    else:
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
        else:
            super().keyPressEvent(event)

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
                    "z_offset": getattr(item, "z_offset", item.z_pos),
                    "level": getattr(item, "level", DEFAULT_LEVEL),
                    "user_layer": getattr(item, "user_layer", DEFAULT_USER_LAYER),
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
                existing = self.find_nearby_node(new_x, new_y)
                node1 = existing if existing else self.add_node(new_x, new_y)

                # Restore elevation offset and layer from copied data
                if "z_offset" in obj:
                    node1.z_offset = obj["z_offset"]
                elif "elevation" in obj:
                    node1.z_offset = obj["elevation"]
                node1.set_property("Elevation Offset", str(node1.z_offset))
                if "level" in obj:
                    node1.level = obj["level"]
                if "user_layer" in obj:
                    node1.user_layer = obj["user_layer"]
                # Recompute z_pos from level
                if self._level_manager:
                    lvl = self._level_manager.get(node1.level)
                    if lvl:
                        node1.z_pos = lvl.elevation + node1.z_offset  # z_offset is legacy (may be ft from old saves)

                if obj.get("sprinkler"):
                    template = Sprinkler(None)
                    for key, meta in obj["sprinkler"].items():
                        template.set_property(key, meta["value"])
                    self.add_sprinkler(node1, template)

                for p in obj.get("pipes", []):
                    px = p["x"] + offset.x()
                    py = p["y"] + offset.y()
                    existing_p = self.find_nearby_node(px, py)
                    node2 = existing_p if existing_p else self.add_node(px, py)
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
                item.user_layer = self.active_user_layer
                item.level = self.active_level
                self.addItem(item)
                self._draw_lines.append(item)

            elif obj_type == "draw_rectangle":
                item = RectangleItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.user_layer = self.active_user_layer
                item.level = self.active_level
                self.addItem(item)
                self._draw_rects.append(item)

            elif obj_type == "draw_circle":
                item = CircleItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.user_layer = self.active_user_layer
                item.level = self.active_level
                self.addItem(item)
                self._draw_circles.append(item)

            elif obj_type == "arc":
                item = ArcItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.user_layer = self.active_user_layer
                item.level = self.active_level
                self.addItem(item)
                self._draw_arcs.append(item)

            elif obj_type == "polyline":
                item = PolylineItem.from_dict(obj)
                item.translate(offset.x(), offset.y())
                item.user_layer = self.active_user_layer
                item.level = self.active_level
                self.addItem(item)
                self._polylines.append(item)

            elif obj_type == "construction_line":
                item = ConstructionLine.from_dict(obj)
                item.translate(offset.x(), offset.y())
                self.addItem(item)
                self._construction_lines.append(item)

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
                    elif t == "construction_line":
                        return ConstructionLine.from_dict(d)
                    elif t == "block_item":
                        return BlockItem.from_dict(d, _item_factory)
                    return None
                item = BlockItem.from_dict(obj, _item_factory)
                item.translate(offset.x(), offset.y())
                self.addItem(item)
                # BlockItems live in the scene but aren't tracked in a dedicated list
        self._show_status(f"Pasted {len(data)} item(s)")

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
