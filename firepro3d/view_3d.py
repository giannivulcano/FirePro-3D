"""
view_3d.py
==========
Interactive 3D visualization of the sprinkler / piping model using PyVista.

Renders nodes, pipes, sprinklers, construction geometry, level floors,
and architectural entities (walls, floor slabs) in a 3D scene.
Supports click-to-select with bidirectional sync to the 2D Model Space.
"""

from __future__ import annotations

import math, logging
import numpy as np

log = logging.getLogger("FirePro3D.3D")

import pyvista as pv
from pyvistaqt import QtInteractor
import vtk

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMenu
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtCore import pyqtSignal, QTimer, Qt, QEvent

from .constants import DEFAULT_LEVEL
from .node import Node
from .pipe import Pipe
from .sprinkler import Sprinkler
from .construction_geometry import (
    ConstructionLine, PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
)
from .gridline import GridlineItem
from .water_supply import WaterSupply
from .annotations import DimensionAnnotation, NoteAnnotation
from .wall import WallSegment
from .floor_slab import FloorSlab
from .view_cube import ViewCube


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

FT_TO_MM = 304.8
CIRCLE_SEGMENTS = 64
PICK_TOLERANCE_PX = 15
MAX_CYLINDER_PIPES = 200   # above this count, fall back to line rendering

# Single source of truth for pipe OD table
from .pipe import Pipe as _PipeClass
_NOMINAL_OD_IN = _PipeClass.NOMINAL_OD_IN

# Colors (RGB tuples for PyVista)
COL_NODE        = (0.55, 0.55, 0.55)
COL_SPRINKLER   = (1.0, 0.2, 0.2)
COL_WATER_SUPPLY = (0.0, 0.7, 0.86)
COL_HIGHLIGHT   = (1.0, 1.0, 0.0)
COL_CONSTR      = (0.4, 0.4, 0.4)
COL_SEL_MESH    = (0.3, 0.6, 1.0)
COL_SEL_EDGE    = (0.2, 0.5, 1.0)

# Pipe color name → RGB
_PIPE_COLORS = {
    "Red":   (0.9, 0.15, 0.15),
    "Blue":  (0.2, 0.4, 0.9),
    "Black": (0.1, 0.1, 0.1),
    "White": (0.95, 0.95, 0.95),
    "Grey":  (0.55, 0.55, 0.55),
}

# Level floor hues (RGBA — alpha used as opacity)
_FLOOR_COLORS = [
    (0.2, 0.4, 0.8, 0.35),
    (0.2, 0.8, 0.4, 0.35),
    (0.8, 0.4, 0.2, 0.35),
    (0.8, 0.2, 0.8, 0.35),
    (0.2, 0.8, 0.8, 0.35),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mesh_from_faces(verts: np.ndarray, faces: np.ndarray) -> "pv.PolyData":
    """Build a PolyData mesh from an Mx3 triangle face array (no manual padding)."""
    return pv.PolyData.from_regular_faces(verts, faces)


# ─────────────────────────────────────────────────────────────────────────────
# View3D widget
# ─────────────────────────────────────────────────────────────────────────────

class View3D(QWidget):
    """Interactive 3D visualization tab."""

    entitySelected = pyqtSignal(object)  # emits QGraphicsItem or None

    def __init__(self, model_space, level_manager, scale_manager, parent=None):
        super().__init__(parent)
        self._scene = model_space
        self._lm = level_manager
        self._sm = scale_manager

        # Dirty flag for lazy rebuild
        self._dirty = True
        self._first_build = True

        # Entity pick map: list index → QGraphicsItem
        self._node_refs: list[Node] = []
        self._pipe_refs: list[Pipe] = []
        self._node_positions_3d: np.ndarray | None = None
        self._pipe_midpoints_3d: np.ndarray | None = None

        # Wall / slab / roof pick maps
        self._wall_refs: list[WallSegment] = []
        self._slab_refs: list[FloorSlab] = []
        self._roof_refs: list = []
        self._wall_centroids_3d: np.ndarray | None = None
        self._slab_centroids_3d: np.ndarray | None = None
        self._roof_centroids_3d: np.ndarray | None = None
        self._original_wall_colors: list[tuple] = []
        self._original_slab_colors: list[tuple] = []
        self._original_roof_colors: list[tuple] = []

        # Actor management: category → list of VTK actors
        self._actors: dict[str, list] = {}
        # Reverse lookup: VTK actor → (entity_ref, entity_type)
        self._actor_to_entity: dict = {}

        # Mesh Z ranges for section cuts: actor → (min_z, max_z)
        self._actor_z_range: dict = {}

        # 3D-only selection tracking (for items where setSelected doesn't stick)
        self._3d_selected: list = []

        # Radiation heatmap state
        self._radiation_meshes: list = []
        self._radiation_entity_map: dict = {}
        self._radiation_orig_colors: dict = {}

        self._build_ui()
        self._connect_signals()

    # ── Actor management ────────────────────────────────────────────────

    def _clear_actors(self, category: str):
        """Remove all actors in a category from the plotter."""
        renderer = self._plotter.renderer
        for actor in self._actors.get(category, []):
            if actor is None:
                continue
            try:
                self._plotter.remove_actor(actor, render=False)
            except Exception:
                pass
            # Fallback: ensure VTK renderer also drops it
            try:
                if renderer.HasViewProp(actor):
                    renderer.RemoveActor(actor)
            except Exception:
                pass
            self._actor_to_entity.pop(actor, None)
            self._actor_z_range.pop(actor, None)
        self._actors[category] = []

    def _add_actor(self, category: str, actor, entity=None, entity_type: str = ""):
        """Track an actor under a category with optional entity mapping."""
        self._actors.setdefault(category, []).append(actor)
        if entity is not None:
            self._actor_to_entity[actor] = (entity, entity_type)

    def _add_edge_actor(self, mesh, category: str, *,
                        color=(0.0, 0.0, 0.0), opacity=1.0,
                        line_width=1.0, name=None):
        """Extract feature edges from *mesh* and add as a line actor."""
        edges = mesh.extract_feature_edges(
            boundary_edges=True, feature_edges=True,
            non_manifold_edges=False, manifold_edges=False,
            feature_angle=1.0,
        )
        if edges.n_cells > 0:
            kw = dict(color=color, opacity=opacity, line_width=line_width)
            if name is not None:
                kw["name"] = name
            actor = self._plotter.add_mesh(edges, **kw)
            self._add_actor(category, actor)
            return actor
        self._add_actor(category, None)
        return None

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar — compact wrapper widget with fixed height
        tb_widget = QWidget()
        tb_widget.setFixedHeight(28)
        tb_widget.setStyleSheet("background: #1e1e1e;")
        tb = QHBoxLayout(tb_widget)
        tb.setContentsMargins(4, 2, 4, 2)
        tb.setSpacing(4)

        _btn_style = "QPushButton { height: 20px; padding: 0 6px; font-size: 11px; }"

        self._fit_btn = QPushButton("Fit All")
        self._fit_btn.setStyleSheet(_btn_style)
        self._fit_btn.clicked.connect(self._fit_camera)
        tb.addWidget(self._fit_btn)

        self._proj_btn = QPushButton("Ortho")
        self._proj_btn.setStyleSheet(_btn_style)
        self._proj_btn.clicked.connect(self._toggle_projection)
        tb.addWidget(self._proj_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setStyleSheet(_btn_style)
        self._refresh_btn.clicked.connect(self.rebuild)
        tb.addWidget(self._refresh_btn)

        self._section_h_btn = QPushButton("H-Cut")
        self._section_h_btn.setStyleSheet(_btn_style)
        self._section_h_btn.setCheckable(True)
        self._section_h_btn.setToolTip("Horizontal section cut — hides geometry above cut height")
        self._section_h_btn.clicked.connect(self._toggle_horizontal_cut)
        tb.addWidget(self._section_h_btn)

        self._grid_btn = QPushButton("Grid")
        self._grid_btn.setStyleSheet(_btn_style)
        self._grid_btn.setCheckable(True)
        self._grid_btn.setChecked(False)
        self._grid_btn.setToolTip("Toggle ground grid")
        self._grid_btn.clicked.connect(self._toggle_3d_grid)
        tb.addWidget(self._grid_btn)

        self._floors_btn = QPushButton("Floors")
        self._floors_btn.setStyleSheet(_btn_style)
        self._floors_btn.setCheckable(True)
        self._floors_btn.setChecked(False)
        self._floors_btn.setToolTip("Toggle level floor planes")
        self._floors_btn.clicked.connect(self._toggle_level_floors)
        tb.addWidget(self._floors_btn)

        tb.addStretch()
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #aaa; font-size: 11px;")
        tb.addWidget(self._info_label)
        layout.addWidget(tb_widget)

        # PyVista plotter (replaces vispy SceneCanvas)
        self._plotter = QtInteractor(self)
        self._plotter.set_background(color=(0.12, 0.12, 0.14))
        self._plotter.enable_depth_peeling(10)  # correct transparency
        layout.addWidget(self._plotter)

        # The actual VTK render widget inside the plotter QFrame
        self._vtk_widget = self._plotter.interactor

        # Use VTK's default trackball camera style for navigation:
        #   Left-drag  = orbit (rotate)
        #   Middle-drag = pan
        #   Right-drag  = dolly zoom
        #   Scroll      = zoom
        # We intercept left-click (no drag) for picking and scroll for
        # zoom-to-cursor via event filter.
        self._vtk_widget.installEventFilter(self)
        self._click_pos = None  # track press pos to distinguish click vs drag
        self._orbit_center = np.array([0.0, 0.0, 0.0])  # centroid for orbit
        self._orbiting = False  # True while left-dragging (orbit)
        self._last_mouse = None  # last mouse pos during orbit

        # Observe camera changes to sync ViewCube
        self._vtk_widget.AddObserver(
            "InteractionEvent", lambda *_: self._sync_viewcube()
        )
        self._vtk_widget.AddObserver(
            "EndInteractionEvent", lambda *_: self._sync_viewcube()
        )

        # ViewCube overlay (top-right corner of the plotter)
        self._view_cube = ViewCube(self._plotter)
        self._view_cube.viewRequested.connect(self._on_viewcube_request)
        self._view_cube.raise_()
        self._position_viewcube()

        # Initial camera
        cam = self._plotter.camera
        cam.position = (10000, 10000, 10000)
        cam.focal_point = (0, 0, 0)
        cam.up = (0, 0, 1)
        cam.view_angle = 45

        # Ground grid and axis lines (static actors)
        self._grid_actor = None
        self._axis_actors: list = []
        self._create_axes()
        self._create_ground_grid(5000, 1000)

        # Visibility states
        self._3d_grid_visible = False
        self._level_floors_visible = False

        # Section cut state
        self._h_cut_enabled: bool = False
        self._h_cut_height_mm: float = 3000.0

        # Debounce timer
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(100)
        self._rebuild_timer.timeout.connect(self._do_rebuild)

    def _connect_signals(self):
        self._scene.sceneModified.connect(self._schedule_rebuild)
        self._scene.selectionChanged.connect(self._on_2d_selection_changed)

    # ── Coordinate mapping ─────────────────────────────────────────────────

    def _scene_to_3d(self, sx: float, sy: float, z_mm: float = 0.0):
        """Convert 2D scene coords + elevation (mm) to 3D world (mm)."""
        ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
        return np.array([sx / ppm, -sy / ppm, z_mm])

    def _node_to_3d(self, node: Node):
        if node is None:
            return np.array([0.0, 0.0, 0.0])
        return self._scene_to_3d(
            node.scenePos().x(), node.scenePos().y(), node.z_pos,
        )

    def _level_z_mm(self, level_name: str) -> float:
        lvl = self._lm.get(level_name)
        return lvl.elevation if lvl else 0.0

    # ── Camera ─────────────────────────────────────────────────────────────

    def _camera_to_angles(self):
        """Extract elevation/azimuth from current VTK camera position."""
        cam = self._plotter.camera
        pos = np.array(cam.position)
        fp = np.array(cam.focal_point)
        d = pos - fp
        dist = np.linalg.norm(d)
        if dist < 1e-10:
            return 30.0, 45.0
        d = d / dist
        elevation = math.degrees(math.asin(np.clip(d[2], -1, 1)))
        azimuth = math.degrees(math.atan2(d[0], d[1]))
        return elevation, azimuth

    def _set_camera_from_angles(self, elevation: float, azimuth: float,
                                center=None, distance=None):
        """Position VTK camera from elevation/azimuth/distance."""
        cam = self._plotter.camera
        if center is None:
            center = np.array(cam.focal_point)
        if distance is None:
            distance = np.linalg.norm(np.array(cam.position) - np.array(cam.focal_point))

        el = math.radians(elevation)
        az = math.radians(azimuth)
        x = distance * math.cos(el) * math.sin(az)
        y = distance * math.cos(el) * math.cos(az)
        z = distance * math.sin(el)

        cam.position = tuple(center + np.array([x, y, z]))
        cam.focal_point = tuple(center)
        cam.up = (0.0, 0.0, 1.0)

    def _compute_scene_bounds(self):
        """Compute bounding box center and span across ALL 3D geometry."""
        all_pts: list[np.ndarray] = []
        if self._node_positions_3d is not None and len(self._node_positions_3d) > 0:
            all_pts.append(self._node_positions_3d)
        if self._pipe_midpoints_3d is not None and len(self._pipe_midpoints_3d) > 0:
            all_pts.append(self._pipe_midpoints_3d)
        if self._wall_centroids_3d is not None and len(self._wall_centroids_3d) > 0:
            all_pts.append(self._wall_centroids_3d)
        if self._slab_centroids_3d is not None and len(self._slab_centroids_3d) > 0:
            all_pts.append(self._slab_centroids_3d)
        if self._roof_centroids_3d is not None and len(self._roof_centroids_3d) > 0:
            all_pts.append(self._roof_centroids_3d)
        if not all_pts:
            return None
        combined = np.vstack(all_pts)
        return combined.mean(axis=0), combined.max(axis=0) - combined.min(axis=0)

    def _fit_camera(self):
        """Auto-fit camera to encompass all geometry."""
        bounds = self._compute_scene_bounds()
        if bounds is not None:
            center, span = bounds
            self._orbit_center = center.copy()
            dist = max(max(span) * 1.8, 1000)
            elev, azim = self._camera_to_angles()
            self._set_camera_from_angles(elev, azim, center=center, distance=dist)
            self._plotter.render()
            self._sync_viewcube()

    def _toggle_projection(self):
        """Toggle between perspective and orthographic projection."""
        cam = self._plotter.camera
        if cam.parallel_projection:
            cam.parallel_projection = False
            self._proj_btn.setText("Ortho")
        else:
            cam.parallel_projection = True
            self._proj_btn.setText("Perspective")
        self._plotter.render()

    def _set_view_preset(self, elevation: float, azimuth: float):
        """Set camera to a standard engineering view preset."""
        if elevation == 90:
            self._plotter.camera.parallel_projection = True
            self._proj_btn.setText("Perspective")
        # Fit first, then snap angle (preserves center + distance)
        bounds = self._compute_scene_bounds()
        if bounds is not None:
            center, span = bounds
            self._orbit_center = center.copy()
            dist = max(max(span) * 1.8, 1000)
        else:
            center = np.array(self._plotter.camera.focal_point)
            dist = np.linalg.norm(np.array(self._plotter.camera.position) - center)
        self._set_camera_from_angles(elevation, azimuth, center=center, distance=dist)
        self._sync_viewcube()
        self._plotter.render()

    # ── Static geometry (axes, grid) ─────────────────────────────────────

    def _create_axes(self):
        """Create XYZ axis lines at world origin."""
        axis_len = 500.0  # mm
        for direction, color, label in [
            ([axis_len, 0, 0], (1.0, 0.0, 0.0), "X"),
            ([0, axis_len, 0], (0.0, 1.0, 0.0), "Y"),
            ([0, 0, axis_len], (0.0, 0.0, 1.0), "Z"),
        ]:
            line = pv.Line([0, 0, 0], direction)
            actor = self._plotter.add_mesh(
                line, color=color, line_width=2.5,
                render_lines_as_tubes=False, name=f"axis_{label}",
            )
            self._axis_actors.append(actor)
        # Axis labels
        label_pts = np.array([
            [axis_len + 60, 0, 0],
            [0, axis_len + 60, 0],
            [0, 0, axis_len + 60],
        ])
        self._plotter.add_point_labels(
            label_pts, ["X", "Y", "Z"],
            font_size=14, bold=True, text_color="white",
            shape=None, render_points_as_spheres=False,
            point_size=0, name="axis_labels",
        )

    def _create_ground_grid(self, extent: float, step: float):
        """Create a ground grid in the XY plane at Z=0."""
        pts = []
        lines = []
        idx = 0
        val = -extent
        while val <= extent:
            pts.extend([[val, -extent, 0], [val, extent, 0]])
            lines.extend([2, idx, idx + 1])
            idx += 2
            pts.extend([[-extent, val, 0], [extent, val, 0]])
            lines.extend([2, idx, idx + 1])
            idx += 2
            val += step

        grid_mesh = pv.PolyData(np.array(pts, dtype=np.float32))
        grid_mesh.lines = np.array(lines, dtype=np.int64)
        self._grid_actor = self._plotter.add_mesh(
            grid_mesh, color=(0.3, 0.3, 0.3), opacity=0.2,
            line_width=1.0, name="ground_grid",
        )
        self._grid_actor.SetVisibility(False)

    def _toggle_3d_grid(self):
        """Toggle ground grid visibility."""
        self._3d_grid_visible = not self._3d_grid_visible
        if self._grid_actor is not None:
            self._grid_actor.SetVisibility(self._3d_grid_visible)
        self._plotter.render()

    def _toggle_level_floors(self):
        """Toggle level floor planes visibility."""
        self._level_floors_visible = not self._level_floors_visible
        vis = self._level_floors_visible
        for actor in self._actors.get("floors", []):
            actor.SetVisibility(vis)
        for actor in self._actors.get("floor_edges", []):
            actor.SetVisibility(vis)
        for actor in self._actors.get("floor_labels", []):
            actor.SetVisibility(vis)
        self._plotter.render()

    # ── ViewCube ──────────────────────────────────────────────────────────

    def _position_viewcube(self):
        """Place the ViewCube in the top-right corner of the plotter."""
        try:
            cw = self._plotter.width()
        except Exception:
            return
        vc = self._view_cube
        margin = 4
        vc.move(cw - vc.width() - margin, margin)

    def _on_viewcube_request(self, elevation: float, azimuth: float):
        self._set_view_preset(elevation, azimuth)

    def _sync_viewcube(self):
        """Push current camera angles to the ViewCube so it rotates."""
        elev, azim = self._camera_to_angles()
        self._view_cube.set_camera_angles(elev, azim)

    def resizeEvent(self, event):
        """Reposition ViewCube when the widget is resized."""
        super().resizeEvent(event)
        self._position_viewcube()

    # ── Rebuild ────────────────────────────────────────────────────────────

    def _schedule_rebuild(self):
        self._dirty = True
        if self.isVisible():
            if not self._rebuild_timer.isActive():
                self._rebuild_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self._rebuild_timer.start()

    def _do_rebuild(self):
        if not self._dirty:
            return
        self.rebuild()

    @staticmethod
    def _is_visible(item) -> bool:
        """Check if an item is visible (not hidden via display overrides)."""
        overrides = getattr(item, "_display_overrides", None)
        if overrides and overrides.get("visible") is False:
            return False
        return True

    def rebuild(self):
        """Rebuild all 3D visuals from Model_Space data."""
        self._dirty = False

        # Suppress rendering during bulk updates
        self._plotter.suppress_rendering = True
        try:
            self._extract_nodes()
            self._extract_pipes()
            self._extract_sprinklers()
            self._extract_water_supply()
            self._extract_construction_geometry()
            self._extract_level_floors()
            self._extract_walls()
            self._extract_floor_slabs()
            self._extract_roofs()
            self._on_2d_selection_changed()
        finally:
            self._plotter.suppress_rendering = False

        # Keep rotation center at geometry bounding box centroid
        bounds = self._compute_scene_bounds()
        if bounds is not None:
            center, _ = bounds
            self._orbit_center = center.copy()
            cam = self._plotter.camera
            dist = np.linalg.norm(np.array(cam.position) - np.array(cam.focal_point))
            direction = np.array(cam.position) - np.array(cam.focal_point)
            if np.linalg.norm(direction) > 1e-10:
                direction = direction / np.linalg.norm(direction)
            else:
                direction = np.array([1.0, 1.0, 1.0]) / math.sqrt(3)
            cam.focal_point = tuple(center)
            cam.position = tuple(center + direction * dist)

        if self._first_build:
            self._fit_camera()
            self._first_build = False

        counts = (
            f"Nodes: {len(self._node_refs)}  "
            f"Pipes: {len(self._pipe_refs)}"
        )
        self._info_label.setText(counts)
        self._plotter.render()

    # ── Extract: Nodes ─────────────────────────────────────────────────────

    def _extract_nodes(self):
        self._clear_actors("nodes")
        nodes = [n for n in self._scene.sprinkler_system.nodes
                 if self._is_visible(n)]
        self._node_refs = nodes
        if not nodes:
            self._node_positions_3d = None
            return

        positions = np.array([self._node_to_3d(n) for n in nodes])
        self._node_positions_3d = positions
        # Positions kept for picking/bounds; no spheres rendered —
        # sprinklers get their own visuals in _extract_sprinklers.

    # ── Extract: Sprinklers ────────────────────────────────────────────────

    def _extract_sprinklers(self):
        self._clear_actors("sprinklers")
        nodes_with_spr = [n for n in self._scene.sprinkler_system.nodes
                          if n.has_sprinkler() and self._is_visible(n)]
        if not nodes_with_spr:
            return

        positions = np.array([self._node_to_3d(n) for n in nodes_with_spr],
                             dtype=np.float32)
        colors = []
        for n in nodes_with_spr:
            orient = n.sprinkler._properties.get("Orientation", {}).get("value", "Upright")
            if orient == "Pendent":
                colors.append([255, 50, 50])
            elif orient == "Sidewall":
                colors.append([50, 200, 50])
            else:
                colors.append([50, 100, 255])

        radius = 40.0  # world-space radius in mm
        sphere = pv.Sphere(radius=radius, theta_resolution=8, phi_resolution=8)
        pts = pv.PolyData(positions)
        pts["colors"] = np.array(colors, dtype=np.uint8)
        glyphs = pts.glyph(geom=sphere, scale=False, orient=False)
        glyphs["colors"] = np.repeat(pts["colors"], sphere.n_cells, axis=0)
        actor = self._plotter.add_mesh(
            glyphs, scalars="colors", rgb=True,
            name="sprinklers",
        )
        self._add_actor("sprinklers", actor)

    # ── Extract: Pipes ─────────────────────────────────────────────────────

    def _extract_pipes(self):
        self._clear_actors("pipes")
        pipes = [p for p in self._scene.sprinkler_system.pipes
                 if self._is_visible(p)]
        self._pipe_refs = pipes
        if not pipes:
            self._pipe_midpoints_3d = None
            return

        mids = []
        pipe_data = []  # (p1, p2, color_name, radius_mm)
        for p in pipes:
            if p.node1 is None or p.node2 is None:
                continue
            p1 = self._node_to_3d(p.node1)
            p2 = self._node_to_3d(p.node2)
            mids.append((p1 + p2) / 2.0)

            col_name = p._properties.get("Colour", {}).get("value", "Red")
            nom = p._properties.get("Diameter", {}).get("value", '2"Ø')
            od_in = _NOMINAL_OD_IN.get(nom, 2.375)
            radius_mm = od_in * 25.4 / 2.0
            pipe_data.append((p1, p2, col_name, radius_mm))

        if not mids:
            self._pipe_midpoints_3d = None
            return

        self._pipe_midpoints_3d = np.array(mids)

        use_cylinders = len(pipe_data) <= MAX_CYLINDER_PIPES

        if use_cylinders:
            # Group pipes by color, merge into one mesh per color
            color_groups: dict[str, list[pv.PolyData]] = {}
            for p1, p2, col_name, radius in pipe_data:
                length = float(np.linalg.norm(p2 - p1))
                if length < 1e-6:
                    continue
                direction = (p2 - p1) / length
                center = (p1 + p2) / 2.0
                cyl = pv.Cylinder(
                    center=center, direction=direction,
                    radius=radius, height=length, resolution=16,
                    capping=True,
                )
                color_groups.setdefault(col_name, []).append(cyl)

            for col_name, meshes in color_groups.items():
                if not meshes:
                    continue
                merged = meshes[0] if len(meshes) == 1 else pv.merge(meshes)
                color = _PIPE_COLORS.get(col_name, (0.9, 0.15, 0.15))
                actor = self._plotter.add_mesh(
                    merged, color=color, smooth_shading=True,
                    name=f"pipes_{col_name}",
                )
                self._add_actor("pipes", actor)
        else:
            # Fallback: line rendering for large pipe counts
            pts = []
            lines = []
            colors_arr = []
            idx = 0
            for p1, p2, col_name, _ in pipe_data:
                pts.extend([p1.tolist(), p2.tolist()])
                lines.extend([2, idx, idx + 1])
                c = _PIPE_COLORS.get(col_name, (0.9, 0.15, 0.15))
                colors_arr.extend([c, c])
                idx += 2

            line_mesh = pv.PolyData(np.array(pts, dtype=np.float32))
            line_mesh.lines = np.array(lines, dtype=np.int64)
            line_mesh["colors"] = (np.array(colors_arr) * 255).astype(np.uint8)
            nom = pipes[0]._properties.get("Diameter", {}).get("value", '2"Ø')
            od = _NOMINAL_OD_IN.get(nom, 2.375)
            width = max(2.0, od * 1.5)
            actor = self._plotter.add_mesh(
                line_mesh, scalars="colors", rgb=True,
                line_width=width, name="pipes_lines",
            )
            actor.GetProperty().SetVertexVisibility(False)
            actor.GetProperty().SetRenderPointsAsSpheres(False)
            actor.GetProperty().SetPointSize(0.001)
            self._add_actor("pipes", actor)

    # ── Extract: Water Supply ──────────────────────────────────────────────

    def _extract_water_supply(self):
        self._clear_actors("water_supply")
        ws = getattr(self._scene, "water_supply_node", None)
        if ws is None or not self._is_visible(ws):
            return
        pos = self._scene_to_3d(ws.scenePos().x(), ws.scenePos().y(), 0)
        sphere = pv.Sphere(radius=60.0, center=pos.tolist(),
                           theta_resolution=8, phi_resolution=8)
        actor = self._plotter.add_mesh(
            sphere, color=COL_WATER_SUPPLY, name="water_supply",
        )
        self._add_actor("water_supply", actor)

    # ── Extract: Construction Geometry ─────────────────────────────────────

    def _extract_construction_geometry(self):
        self._clear_actors("construction")
        lines_data = []

        # Lines
        for item in getattr(self._scene, "_draw_lines", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            p1 = item._pt1
            p2 = item._pt2
            lines_data.append([p1.x() / ppm, -p1.y() / ppm, z])
            lines_data.append([p2.x() / ppm, -p2.y() / ppm, z])

        # Construction lines
        for item in getattr(self._scene, "_construction_lines", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            p1 = item._pt1
            p2 = item._pt2
            lines_data.append([p1.x() / ppm, -p1.y() / ppm, z])
            lines_data.append([p2.x() / ppm, -p2.y() / ppm, z])

        # Rectangles (4 edges)
        for item in getattr(self._scene, "_draw_rects", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            r = item.rect()
            corners = [
                [r.left() / ppm, -r.top() / ppm, z],
                [r.right() / ppm, -r.top() / ppm, z],
                [r.right() / ppm, -r.bottom() / ppm, z],
                [r.left() / ppm, -r.bottom() / ppm, z],
            ]
            for i in range(4):
                lines_data.append(corners[i])
                lines_data.append(corners[(i + 1) % 4])

        # Circles (polygon approximation)
        for item in getattr(self._scene, "_draw_circles", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            cx = item._center.x() / ppm
            cy = -item._center.y() / ppm
            r = item._radius / ppm
            for i in range(CIRCLE_SEGMENTS):
                a1 = 2 * math.pi * i / CIRCLE_SEGMENTS
                a2 = 2 * math.pi * (i + 1) / CIRCLE_SEGMENTS
                lines_data.append([cx + r * math.cos(a1), cy + r * math.sin(a1), z])
                lines_data.append([cx + r * math.cos(a2), cy + r * math.sin(a2), z])

        # Arcs
        for item in getattr(self._scene, "_draw_arcs", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            cx = item._center.x() / ppm
            cy = -item._center.y() / ppm
            r = item._radius / ppm
            start = math.radians(item._start_deg)
            span = math.radians(item._span_deg)
            n_seg = max(8, int(abs(span) / (2 * math.pi) * CIRCLE_SEGMENTS))
            for i in range(n_seg):
                a1 = start + span * i / n_seg
                a2 = start + span * (i + 1) / n_seg
                lines_data.append([cx + r * math.cos(a1), cy + r * math.sin(a1), z])
                lines_data.append([cx + r * math.cos(a2), cy + r * math.sin(a2), z])

        # Polylines
        for item in getattr(self._scene, "_polylines", []):
            z = self._level_z_mm(getattr(item, "level", DEFAULT_LEVEL))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            pts = item._points
            for i in range(len(pts) - 1):
                lines_data.append([pts[i].x() / ppm, -pts[i].y() / ppm, z])
                lines_data.append([pts[i + 1].x() / ppm, -pts[i + 1].y() / ppm, z])

        if lines_data:
            points = np.array(lines_data, dtype=np.float32)
            n_segs = len(points) // 2
            line_cells = []
            for i in range(n_segs):
                line_cells.extend([2, i * 2, i * 2 + 1])
            mesh = pv.PolyData(points)
            mesh.lines = np.array(line_cells, dtype=np.int64)
            actor = self._plotter.add_mesh(
                mesh, color=COL_CONSTR, opacity=0.6,
                line_width=1.0, name="construction",
            )
            actor.GetProperty().SetVertexVisibility(False)
            actor.GetProperty().SetRenderPointsAsSpheres(False)
            actor.GetProperty().SetPointSize(0.001)
            self._add_actor("construction", actor)

    # ── Extract: Level Floors ──────────────────────────────────────────────

    def _extract_level_floors(self):
        self._clear_actors("floors")
        self._clear_actors("floor_edges")
        self._clear_actors("floor_labels")

        nodes = list(self._scene.sprinkler_system.nodes)
        if not nodes:
            return

        positions = self._node_positions_3d
        if positions is None or len(positions) == 0:
            return

        x_min, y_min = positions[:, 0].min(), positions[:, 1].min()
        x_max, y_max = positions[:, 0].max(), positions[:, 1].max()
        pad = max(abs(x_max - x_min), abs(y_max - y_min)) * 0.15 + 500
        x_min -= pad
        x_max += pad
        y_min -= pad
        y_max += pad

        for i, lvl in enumerate(self._lm.levels):
            z = lvl.elevation
            col = _FLOOR_COLORS[i % len(_FLOOR_COLORS)]

            verts = np.array([
                [x_min, y_min, z],
                [x_max, y_min, z],
                [x_max, y_max, z],
                [x_min, y_max, z],
            ], dtype=np.float32)
            faces = np.array([4, 0, 1, 2, 3], dtype=np.int64)  # single quad

            floor_mesh = pv.PolyData(verts, faces=faces)
            actor = self._plotter.add_mesh(
                floor_mesh, color=col[:3], opacity=0.35,
                name=f"floor_{i}",
            )
            actor.SetVisibility(self._level_floors_visible)
            self._add_actor("floors", actor)

            # Edge outline via VTK feature edges
            edge_actor = self._add_edge_actor(
                floor_mesh, "floor_edges",
                color=col[:3], opacity=0.6, name=f"floor_edge_{i}",
            )
            if edge_actor is not None:
                edge_actor.SetVisibility(self._level_floors_visible)

            # Level label
            label_pt = np.array([[x_min + 200, y_min + 200, z + 50]])
            label_actor = self._plotter.add_point_labels(
                label_pt, [lvl.name],
                font_size=12, bold=True, text_color="white",
                shape=None, point_size=0,
                name=f"floor_label_{i}",
            )
            if label_actor is not None:
                label_actor.SetVisibility(self._level_floors_visible)
                self._add_actor("floor_labels", label_actor)

    # ── Extract: Walls ────────────────────────────────────────────────────

    def _extract_walls(self):
        """Render wall entities as extruded 3D meshes with edge lines."""
        self._clear_actors("walls")
        self._clear_actors("wall_edges")
        self._wall_refs.clear()
        self._original_wall_colors.clear()

        scene_obj = self._scene
        if scene_obj is None:
            self._wall_centroids_3d = None
            return
        lm = self._lm
        centroids = []
        for wall in getattr(scene_obj, "_walls", []):
            if not self._is_visible(wall):
                continue
            mesh_data = wall.get_3d_mesh(level_manager=lm)
            if mesh_data is None:
                continue
            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)
            col = mesh_data.get("color", (0.8, 0.8, 0.8, 0.9))

            mesh = _mesh_from_faces(verts, faces)
            actor = self._plotter.add_mesh(
                mesh, color=col[:3], opacity=1.0,
            )
            self._add_actor("walls", actor, entity=wall, entity_type="wall")
            self._wall_refs.append(wall)
            self._original_wall_colors.append(col)
            centroids.append(verts.mean(axis=0))

            # Store Z range for section cuts
            self._actor_z_range[actor] = (float(verts[:, 2].min()), float(verts[:, 2].max()))

            # Edge wireframe via VTK feature edges
            self._add_edge_actor(mesh, "wall_edges")

        self._wall_centroids_3d = np.array(centroids) if centroids else None

    # ── Extract: Floor Slabs ──────────────────────────────────────────────

    def _extract_floor_slabs(self):
        """Render floor slab entities as solid 3D meshes with edge lines."""
        self._clear_actors("slabs")
        self._clear_actors("slab_edges")
        self._slab_refs.clear()
        self._original_slab_colors.clear()

        scene_obj = self._scene
        if scene_obj is None:
            self._slab_centroids_3d = None
            return
        lm = self._lm
        centroids = []
        for slab in getattr(scene_obj, "_floor_slabs", []):
            if not self._is_visible(slab):
                continue
            mesh_data = slab.get_3d_mesh(level_manager=lm)
            if mesh_data is None:
                continue
            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)
            col = mesh_data.get("color", (0.5, 0.5, 0.8, 1.0))

            mesh = _mesh_from_faces(verts, faces)
            # Full opacity, disable backface culling so slab is always visible
            actor = self._plotter.add_mesh(
                mesh, color=col[:3], opacity=1.0,
                show_edges=False,
            )
            actor.GetProperty().SetBackfaceCulling(False)
            actor.GetProperty().SetFrontfaceCulling(False)
            self._add_actor("slabs", actor, entity=slab, entity_type="slab")
            self._slab_refs.append(slab)
            self._original_slab_colors.append(col)
            centroids.append(verts.mean(axis=0))

            self._actor_z_range[actor] = (float(verts[:, 2].min()), float(verts[:, 2].max()))

            # Edge wireframe via VTK feature edges
            self._add_edge_actor(mesh, "slab_edges")

        self._slab_centroids_3d = np.array(centroids) if centroids else None

    def _extract_roofs(self):
        """Render roof entities as solid 3D meshes with edge lines."""
        self._clear_actors("roofs")
        self._clear_actors("roof_edges")
        self._roof_refs.clear()
        self._original_roof_colors.clear()

        scene_obj = self._scene
        if scene_obj is None:
            self._roof_centroids_3d = None
            return
        lm = self._lm
        centroids = []
        for roof in getattr(scene_obj, "_roofs", []):
            if not self._is_visible(roof):
                continue
            mesh_data = roof.get_3d_mesh(level_manager=lm)
            if mesh_data is None:
                continue
            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)
            col = mesh_data.get("color", (0.8, 0.7, 0.5, 0.5))

            mesh = _mesh_from_faces(verts, faces)
            actor = self._plotter.add_mesh(
                mesh, color=col[:3], opacity=col[3] if len(col) > 3 else 1.0,
            )
            self._add_actor("roofs", actor, entity=roof, entity_type="roof")
            self._roof_refs.append(roof)
            self._original_roof_colors.append(col)
            centroids.append(verts.mean(axis=0))

            self._actor_z_range[actor] = (float(verts[:, 2].min()), float(verts[:, 2].max()))

            # Edge wireframe via VTK feature edges
            self._add_edge_actor(mesh, "roof_edges")

        self._roof_centroids_3d = np.array(centroids) if centroids else None

    # ── Section Cuts ───────────────────────────────────────────────────────

    def _toggle_horizontal_cut(self):
        """Toggle horizontal section cut on/off."""
        self._h_cut_enabled = self._section_h_btn.isChecked()
        if self._h_cut_enabled:
            if self._lm is not None:
                levels = self._lm.levels
                if len(levels) >= 2:
                    self._h_cut_height_mm = levels[1].elevation
            self._apply_horizontal_cut()
        else:
            self._remove_horizontal_cut()
        self._plotter.render()

    def _apply_horizontal_cut(self):
        """Hide all meshes whose geometry is entirely above the cut plane."""
        cut_z = self._h_cut_height_mm

        # Hide mesh actors above cut
        for category in ("walls", "slabs", "roofs", "floors"):
            actors = self._actors.get(category, [])
            edge_cat = category.rstrip("s") + "_edges"  # walls→wall_edges
            if category == "floors":
                edge_cat = "floor_edges"
            edge_actors = self._actors.get(edge_cat, [])
            for i, actor in enumerate(actors):
                if actor is None:
                    continue
                z_range = self._actor_z_range.get(actor)
                if z_range is not None:
                    actor.SetVisibility(z_range[0] < cut_z)
                    if i < len(edge_actors) and edge_actors[i] is not None:
                        edge_actors[i].SetVisibility(z_range[0] < cut_z)

        # Node spheres removed — nothing to clip

    def _remove_horizontal_cut(self):
        """Restore all meshes to visible (respecting floors toggle)."""
        for category in ("walls", "slabs", "roofs"):
            for actor in self._actors.get(category, []):
                if actor is not None:
                    actor.SetVisibility(True)
        for category in ("wall_edges", "slab_edges", "roof_edges"):
            for actor in self._actors.get(category, []):
                if actor is not None:
                    actor.SetVisibility(True)

        # Restore floors based on toggle
        vis = self._level_floors_visible
        for actor in self._actors.get("floors", []):
            if actor is not None:
                actor.SetVisibility(vis)
        for actor in self._actors.get("floor_edges", []):
            if actor is not None:
                actor.SetVisibility(vis)
        for actor in self._actors.get("floor_labels", []):
            if actor is not None:
                actor.SetVisibility(vis)

        # Node spheres removed — nothing to restore

    # ── Mouse / Keyboard Event Filter ────────────────────────────────────

    _CLICK_THRESHOLD = 5  # pixels — less movement than this = click, not drag
    _ZOOM_FACTOR = 0.1    # fraction of distance to shift focal point per scroll tick

    def eventFilter(self, obj, event):
        """Intercept mouse events for orbit-around-centroid, picking,
        zoom-to-cursor, and keyboard shortcuts.

        Left-drag  = orbit around geometry centroid (handled here)
        Middle-drag = pan (VTK default)
        Right-drag  = dolly (VTK default)
        Left-click (no drag) = picking
        Scroll = zoom-to-cursor
        """
        etype = event.type()

        if etype == QEvent.Type.MouseButtonDblClick:
            if event.button() == Qt.MouseButton.LeftButton:
                # Treat double-click same as single click, reset state
                self._click_pos = None
                self._last_mouse = None
                self._orbiting = False
                return True  # consume — prevent stuck orbit

        if etype == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._vtk_widget.setFocus()  # ensure key events reach us
                self._click_pos = (event.position().x(), event.position().y())
                self._last_mouse = (event.position().x(), event.position().y())
                self._orbiting = False
                return True  # consume — we handle left-click/drag entirely

        if etype == QEvent.Type.MouseMove:
            if self._click_pos is not None and self._last_mouse is not None:
                buttons = event.buttons()
                if not (buttons & Qt.MouseButton.LeftButton):
                    # Left button no longer held — release was missed, reset
                    self._click_pos = None
                    self._last_mouse = None
                    self._orbiting = False
                    return False
                mx, my = event.position().x(), event.position().y()
                dx = mx - self._last_mouse[0]
                dy = my - self._last_mouse[1]
                # Check if we've moved enough to be a drag
                total_dx = abs(mx - self._click_pos[0])
                total_dy = abs(my - self._click_pos[1])
                if total_dx >= self._CLICK_THRESHOLD or total_dy >= self._CLICK_THRESHOLD:
                    self._orbiting = True
                if self._orbiting and (abs(dx) > 0.5 or abs(dy) > 0.5):
                    self._do_orbit(dx, dy)
                    self._last_mouse = (mx, my)
                    self._sync_viewcube()
                    return True  # consume — we handle orbit
            return False

        if etype == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if self._click_pos is not None and not self._orbiting:
                    dx = abs(event.position().x() - self._click_pos[0])
                    dy = abs(event.position().y() - self._click_pos[1])
                    if dx < self._CLICK_THRESHOLD and dy < self._CLICK_THRESHOLD:
                        self._on_mouse_press(event)
                self._click_pos = None
                self._last_mouse = None
                self._orbiting = False
                return True  # consume — we own the full left-button cycle

        # Safety: if mouse leaves widget mid-drag, reset orbit state
        if etype == QEvent.Type.Leave:
            self._click_pos = None
            self._last_mouse = None
            self._orbiting = False
            return False

        if etype == QEvent.Type.Wheel:
            self._on_scroll_zoom(event)
            return True

        if etype == QEvent.Type.KeyPress:
            handled = self._on_key_press(event)
            return handled or False

        if etype == QEvent.Type.ContextMenu:
            self._show_context_menu(event.globalPos())
            return True

        return super().eventFilter(obj, event)

    def _do_orbit(self, dx: float, dy: float):
        """Orbit the camera around self._orbit_center by mouse deltas."""
        sensitivity = 0.3  # degrees per pixel
        cam = self._plotter.camera
        pos = np.array(cam.position)
        center = self._orbit_center

        offset = pos - center
        dist = np.linalg.norm(offset)
        if dist < 1e-10:
            return

        # Current elevation / azimuth from orbit center
        norm = offset / dist
        elevation = math.degrees(math.asin(np.clip(norm[2], -1, 1)))
        azimuth = math.degrees(math.atan2(norm[0], norm[1]))

        # Apply mouse deltas
        azimuth += dx * sensitivity
        elevation += dy * sensitivity
        elevation = np.clip(elevation, -89.9, 89.9)

        # Rebuild camera position
        el = math.radians(elevation)
        az = math.radians(azimuth)
        new_offset = np.array([
            dist * math.cos(el) * math.sin(az),
            dist * math.cos(el) * math.cos(az),
            dist * math.sin(el),
        ])
        cam.position = tuple(center + new_offset)
        cam.focal_point = tuple(center)
        cam.up = (0.0, 0.0, 1.0)
        self._plotter.render()

    # ── Zoom-to-cursor ─────────────────────────────────────────────────────

    def _on_scroll_zoom(self, event):
        """Zoom toward / away from the 3D point under the cursor."""
        delta = event.angleDelta().y()
        if delta == 0:
            return

        factor = 0.85 if delta > 0 else 1.0 / 0.85

        cam = self._plotter.camera
        pos = np.array(cam.position)
        fp = np.array(cam.focal_point)

        # Ray-cast under cursor to get a real depth hit
        sx, sy = event.position().x(), event.position().y()
        renderer = self._plotter.renderer
        h = renderer.GetSize()[1]
        picker = vtk.vtkWorldPointPicker()
        picker.Pick(float(sx), float(h - sy), 0.0, renderer)
        picked = np.array(picker.GetPickPosition())

        # If the pick lands at the camera (no geometry hit), fall back to
        # projecting the cursor onto the focal plane instead.
        if np.linalg.norm(picked - pos) < 1e-6:
            # Cursor ray direction
            coord_near = vtk.vtkCoordinate()
            coord_near.SetCoordinateSystemToDisplay()
            coord_near.SetValue(float(sx), float(h - sy), 0.0)
            near = np.array(coord_near.GetComputedWorldValue(renderer))
            coord_far = vtk.vtkCoordinate()
            coord_far.SetCoordinateSystemToDisplay()
            coord_far.SetValue(float(sx), float(h - sy), 1.0)
            far = np.array(coord_far.GetComputedWorldValue(renderer))
            ray = far - near
            ray_len = np.linalg.norm(ray)
            if ray_len < 1e-10:
                return
            ray /= ray_len
            # Intersect ray with the focal plane
            view_dir = fp - pos
            denom = np.dot(ray, view_dir)
            if abs(denom) < 1e-10:
                return
            t = np.dot(fp - near, view_dir) / denom
            picked = near + ray * t

        # Move camera + focal point toward/away from the picked point
        cam.position = tuple(picked + (pos - picked) * factor)
        cam.focal_point = tuple(picked + (fp - picked) * factor)
        cam.up = (0.0, 0.0, 1.0)

        self._plotter.render()
        self._sync_viewcube()

    # ── Selection / Picking ────────────────────────────────────────────────

    def _on_mouse_press(self, event):
        """Handle left-click in 3D view for entity selection."""
        screen_x = event.position().x()
        screen_y = event.position().y()

        # Check for Ctrl modifier
        ctrl_held = event.modifiers() & Qt.KeyboardModifier.ControlModifier

        hit = self._pick_at(screen_x, screen_y)
        log.debug("click at (%.0f, %.0f), hit=%s", screen_x, screen_y, hit)

        if hit is not None:
            if ctrl_held:
                if hit in self._3d_selected:
                    self._3d_selected.remove(hit)
                    hit.setSelected(False)
                else:
                    hit.setSelected(True)
                    self._3d_selected.append(hit)
            else:
                self._scene.clearSelection()
                self._3d_selected = [hit]
                hit.setSelected(True)
            # Build combined selection: scene + our 3D tracking
            selected = list(self._scene.selectedItems())
            for item in self._3d_selected:
                if item not in selected:
                    selected.append(item)
            self.entitySelected.emit(hit)
            self._highlight_mesh_selection(selected)
        elif ctrl_held:
            pass  # preserve selection
        else:
            # Click on empty space — clear selection
            self._3d_selected.clear()
            self._clear_actors("highlight")
            self._clear_actors("sel_overlay")
            self._clear_actors("sel_overlay_edges")
            self._plotter.render()
            self._scene.clearSelection()

    def _nearest_point_entity(self, screen_x: float, screen_y: float):
        """Find the closest node or pipe midpoint within pick tolerance."""
        best_item = None
        best_dist = float("inf")

        for positions, refs in (
            (self._node_positions_3d, getattr(self, '_node_refs', None)),
            (self._pipe_midpoints_3d, getattr(self, '_pipe_refs', None)),
        ):
            if positions is None or refs is None:
                continue
            for i, pos3d in enumerate(positions):
                screen = self._project_to_screen(pos3d)
                if screen is None:
                    continue
                dist = math.sqrt((screen[0] - screen_x) ** 2 + (screen[1] - screen_y) ** 2)
                if dist < PICK_TOLERANCE_PX and dist < best_dist:
                    best_dist = dist
                    best_item = refs[i]

        return best_item, best_dist

    def _pick_at(self, screen_x: float, screen_y: float):
        """Find entity at screen position using VTK hardware picking."""
        renderer = self._plotter.renderer
        h = renderer.GetSize()[1]
        vtk_y = h - screen_y  # VTK uses bottom-left origin

        # Check nodes/pipes first (tight tolerance)
        point_item, point_dist = self._nearest_point_entity(screen_x, screen_y)
        if point_item is not None and point_dist < PICK_TOLERANCE_PX / 2:
            return point_item

        # Use VTK cell picker for mesh entities
        picker = vtk.vtkCellPicker()
        picker.SetTolerance(0.005)
        picker.Pick(int(screen_x), int(vtk_y), 0, renderer)

        actor = picker.GetActor()
        if actor is not None:
            if actor in self._actor_to_entity:
                entity, etype = self._actor_to_entity[actor]
                log.debug("picked actor → %s (%s)", type(entity).__name__, etype)
                return entity
            else:
                log.debug("picked actor not in entity map (category unknown)")
        else:
            log.debug("cell picker found no actor")

        # Fall back to any node/pipe within full tolerance
        return point_item

    def _project_to_screen(self, world_pos: np.ndarray):
        """Project a 3D world position to 2D screen coordinates."""
        try:
            renderer = self._plotter.renderer
            coord = vtk.vtkCoordinate()
            coord.SetCoordinateSystemToWorld()
            coord.SetValue(float(world_pos[0]), float(world_pos[1]), float(world_pos[2]))
            display = coord.GetComputedDisplayValue(renderer)
            h = renderer.GetSize()[1]
            # Convert VTK display (bottom-left origin) to Qt (top-left origin)
            return np.array([display[0], h - display[1]], dtype=float)
        except Exception:
            return None

    def _on_key_press(self, event):
        """Handle keyboard shortcuts in 3D view. Returns True if handled."""
        key = event.key()

        # Escape: cancel orbit, clear selection
        if key == Qt.Key.Key_Escape:
            # Break out of any stuck orbit state
            self._click_pos = None
            self._last_mouse = None
            self._orbiting = False
            # Clear ALL 3D highlights explicitly
            self._clear_actors("highlight")
            self._clear_actors("sel_overlay")
            self._clear_actors("sel_overlay_edges")
            self._plotter.render()
            # Clear 2D scene selection (also syncs model browser)
            self._scene.clearSelection()
            # Forward to radiation selection if active
            if getattr(self._scene, '_radiation_selecting', False):
                self._scene._radiation_selecting = False
                self._scene.radiationCancel.emit()
            return True

        # Radiation selection shortcuts
        if getattr(self._scene, '_radiation_selecting', False):
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self._scene.radiationConfirm.emit()
                return True
        return False

    def _on_escape(self):
        """Escape shortcut handler — clears orbit state and selection."""
        self._click_pos = None
        self._last_mouse = None
        self._orbiting = False
        self._3d_selected.clear()
        self._clear_actors("highlight")
        self._clear_actors("sel_overlay")
        self._clear_actors("sel_overlay_edges")
        self._plotter.render()
        self._scene.clearSelection()
        if getattr(self._scene, '_radiation_selecting', False):
            self._scene._radiation_selecting = False
            self._scene.radiationCancel.emit()

    def get_3d_selected(self):
        """Return items selected via 3D picking (may not be in scene selection)."""
        return list(self._3d_selected)

    def delete_selected(self):
        """Delete items selected in the 3D view."""
        items = list(self._3d_selected)
        if not items:
            return
        self._3d_selected.clear()
        self._clear_actors("highlight")
        self._clear_actors("sel_overlay")
        self._clear_actors("sel_overlay_edges")
        self._plotter.render()
        # Delete each item directly via scene methods
        from .roof import RoofItem
        from .wall import WallSegment
        from .floor_slab import FloorSlab
        for item in items:
            if isinstance(item, WallSegment):
                for op in list(item.openings):
                    if op.scene() is self._scene:
                        self._scene.removeItem(op)
                item.openings.clear()
                if item in self._scene._walls:
                    self._scene._walls.remove(item)
                self._scene.removeItem(item)
            elif isinstance(item, FloorSlab):
                if item in self._scene._floor_slabs:
                    self._scene._floor_slabs.remove(item)
                self._scene.removeItem(item)
            elif isinstance(item, RoofItem):
                if item in self._scene._roofs:
                    self._scene._roofs.remove(item)
                self._scene.removeItem(item)
            else:
                # Fallback: try setSelected + scene delete
                item.setSelected(True)
                self._scene.delete_selected_items()
        self._scene.push_undo_state()
        self.rebuild()

    def _show_context_menu(self, global_pos):
        """Show right-click context menu in the 3D view."""
        from .entity_context_menu import build_entity_context_menu

        selected = list(self._scene.selectedItems())
        # Include 3D-only selections
        for item in self._3d_selected:
            if item not in selected:
                selected.append(item)

        menu = build_entity_context_menu(
            selected,
            target=selected[0] if selected else None,
            scene=self._scene,
            on_hide=lambda: (self._scene._hide_items(selected), self.rebuild()),
            on_show_all=lambda: (self._scene._show_all_hidden(), self.rebuild()),
            on_delete=self.delete_selected,
            on_deselect=self._on_escape,
            on_fit=self._fit_camera,
            on_refresh=self.rebuild,
        )
        menu.exec(global_pos)

    def keyPressEvent(self, event):
        """Catch key events on the View3D widget itself (backup path)."""
        if self._on_key_press(event):
            event.accept()
        else:
            super().keyPressEvent(event)

    # ── Mesh Selection Highlight ─────────────────────────────────────────────

    def _highlight_mesh_selection(self, selected_items):
        """Highlight selected walls/slabs/roofs using overlay actors.

        Base actors are NEVER modified — instead we add a blue overlay mesh
        and bright edge wireframe on top of each selected entity.  This avoids
        VTK SetColor/SetOpacity issues that broke non-selected actor rendering.
        """
        # Remove previous selection overlays
        self._clear_actors("sel_overlay")
        self._clear_actors("sel_overlay_edges")

        if selected_items is None:
            selected_items = []

        # Reset radiation overlays to original
        if self._radiation_meshes:
            for entity, orig_fc in self._radiation_orig_colors.items():
                rad_mesh = self._radiation_entity_map.get(entity)
                if rad_mesh is not None:
                    try:
                        rad_mesh.GetMapper().GetInput().cell_data["colors"] = (orig_fc[:, :3] * 255).astype(np.uint8)
                        rad_mesh.GetMapper().GetInput().Modified()
                    except Exception:
                        pass

        if not selected_items:
            self._plotter.render()
            return

        # Highlight radiation overlays for selected entities
        if self._radiation_meshes:
            sel_set = set(id(s) for s in selected_items)
            for entity, rad_actor in self._radiation_entity_map.items():
                if id(entity) in sel_set:
                    orig_fc = self._radiation_orig_colors.get(entity)
                    if orig_fc is not None:
                        tinted = orig_fc.copy()
                        tinted[:, :3] = np.clip(tinted[:, :3] * 0.4 + 0.6, 0.0, 1.0)
                        try:
                            rad_actor.GetMapper().GetInput().cell_data["colors"] = (tinted[:, :3] * 255).astype(np.uint8)
                            rad_actor.GetMapper().GetInput().Modified()
                        except Exception:
                            pass

        # Find selected entities and add overlay meshes
        lm = self._lm
        for sel in selected_items:
            mesh_data = None
            log.debug("highlight: processing %s, has _roof_type=%s, has get_3d_mesh=%s",
                      type(sel).__name__, hasattr(sel, '_roof_type'), hasattr(sel, 'get_3d_mesh'))
            if isinstance(sel, WallSegment):
                mesh_data = sel.get_3d_mesh(level_manager=lm)
            elif isinstance(sel, FloorSlab):
                mesh_data = sel.get_3d_mesh(level_manager=lm)
            elif hasattr(sel, 'get_3d_mesh'):
                mesh_data = sel.get_3d_mesh(level_manager=lm)

            if mesh_data is None:
                log.debug("highlight: no mesh_data for %s", type(sel).__name__)
                continue

            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)

            overlay = _mesh_from_faces(verts, faces)
            actor = self._plotter.add_mesh(
                overlay, color=COL_SEL_MESH, opacity=1.0,
            )
            self._add_actor("sel_overlay", actor)

            # Bright edge wireframe via VTK feature edges
            self._add_edge_actor(
                overlay, "sel_overlay_edges",
                color=COL_SEL_EDGE, line_width=1.5,
            )

        self._plotter.render()

    # ── 2D → 3D Selection Sync ─────────────────────────────────────────────

    def _on_2d_selection_changed(self):
        """Highlight selected items in 3D."""
        self._clear_actors("highlight")
        try:
            selected = self._scene.selectedItems()
        except RuntimeError:
            return

        if not selected:
            self._highlight_mesh_selection(None)
            self._plotter.render()
            return

        node_positions = []
        pipe_cyls = []
        mesh_selected = []
        for item in selected:
            if isinstance(item, Node):
                node_positions.append(self._node_to_3d(item))
            elif isinstance(item, Pipe):
                if item.node1 is not None and item.node2 is not None:
                    p1 = self._node_to_3d(item.node1)
                    p2 = self._node_to_3d(item.node2)
                    nom = item._properties.get("Diameter", {}).get("value", '2"Ø')
                    od_in = _NOMINAL_OD_IN.get(nom, 2.375)
                    radius = od_in * 25.4 / 2.0 * 1.15
                    pipe_cyls.append((p1, p2, radius))
            elif isinstance(item, (WallSegment, FloorSlab)):
                mesh_selected.append(item)
            elif hasattr(item, '_roof_type'):
                mesh_selected.append(item)
        hl_idx = 0

        if node_positions:
            pts = pv.PolyData(np.array(node_positions, dtype=np.float32))
            sphere = pv.Sphere(radius=50.0, theta_resolution=8, phi_resolution=8)
            glyphs = pts.glyph(geom=sphere, scale=False, orient=False)
            actor = self._plotter.add_mesh(
                glyphs, color=COL_HIGHLIGHT, opacity=0.85,
                name=f"_hl_{hl_idx}",
            )
            self._add_actor("highlight", actor)
            hl_idx += 1

        if pipe_cyls:
            cyls = []
            for p1, p2, radius in pipe_cyls:
                length = float(np.linalg.norm(p2 - p1))
                if length < 1e-6:
                    continue
                direction = (p2 - p1) / length
                center = (p1 + p2) / 2.0
                cyl = pv.Cylinder(
                    center=center, direction=direction,
                    radius=radius, height=length, resolution=16,
                    capping=True,
                )
                cyls.append(cyl)
            if cyls:
                merged = cyls[0] if len(cyls) == 1 else pv.merge(cyls)
                # Solid overlay + edge wireframe (same pattern as wall highlight)
                actor = self._plotter.add_mesh(
                    merged, color=COL_SEL_MESH, opacity=1.0,
                    smooth_shading=True, name=f"_hl_{hl_idx}",
                )
                self._add_actor("highlight", actor)
                hl_idx += 1
                self._add_edge_actor(
                    merged, "highlight",
                    color=COL_SEL_EDGE, line_width=1.5,
                )
        self._highlight_mesh_selection(mesh_selected)
        self._plotter.render()

    # ------------------------------------------------------------------
    # Thermal radiation heatmap overlay
    # ------------------------------------------------------------------

    def show_radiation_heatmap(self, result):
        """Overlay colour-mapped meshes on receiver surfaces."""
        self.clear_radiation_heatmap()
        threshold = result.threshold

        for entity, flux in result.per_receiver_flux.items():
            sub = result.per_receiver_mesh.get(entity)
            if sub is None:
                continue
            verts = np.asarray(sub["vertices"], dtype=np.float64)
            faces = np.asarray(sub["faces"], dtype=np.int32)
            if len(faces) == 0:
                continue

            # Offset vertices along per-face normals to avoid z-fighting
            OFFSET_MM = 15.0
            v0 = verts[faces[:, 0]]
            v1 = verts[faces[:, 1]]
            v2 = verts[faces[:, 2]]
            normals = np.cross(v1 - v0, v2 - v0)
            norms = np.linalg.norm(normals, axis=1, keepdims=True)
            norms = np.where(norms > 1e-8, norms, 1.0)
            normals = normals / norms

            vert_normals = np.zeros_like(verts)
            vert_counts = np.zeros(len(verts))
            for col in range(3):
                np.add.at(vert_normals, faces[:, col], normals)
                np.add.at(vert_counts, faces[:, col], 1.0)
            vert_counts = np.where(vert_counts > 0, vert_counts, 1.0)
            vert_normals /= vert_counts[:, np.newaxis]
            vn_len = np.linalg.norm(vert_normals, axis=1, keepdims=True)
            vn_len = np.where(vn_len > 1e-8, vn_len, 1.0)
            vert_normals /= vn_len

            offset_verts = (verts + vert_normals * OFFSET_MM).astype(np.float32)

            face_colors = self._flux_to_colors(flux, threshold)

            # Ensure face_colors length matches faces
            if len(face_colors) < len(faces):
                pad = np.tile([0.0, 0.2, 0.8, 1.0],
                              (len(faces) - len(face_colors), 1)).astype(np.float32)
                face_colors = np.vstack([face_colors, pad])
            elif len(face_colors) > len(faces):
                face_colors = face_colors[:len(faces)]

            mesh = _mesh_from_faces(offset_verts, faces)
            # Store per-face colors as cell data (RGB uint8)
            mesh.cell_data["colors"] = (face_colors[:, :3] * 255).astype(np.uint8)

            actor = self._plotter.add_mesh(
                mesh, scalars="colors", rgb=True,
                show_scalar_bar=False,
            )
            self._radiation_meshes.append(actor)
            self._radiation_entity_map[entity] = actor
            self._radiation_orig_colors[entity] = face_colors.copy()

        self._plotter.render()

    def clear_radiation_heatmap(self):
        """Remove all radiation overlay meshes."""
        for actor in self._radiation_meshes:
            try:
                self._plotter.remove_actor(actor, render=False)
            except Exception:
                pass
        self._radiation_meshes.clear()
        self._radiation_entity_map.clear()
        self._radiation_orig_colors.clear()
        self._plotter.render()

    @staticmethod
    def _flux_to_colors(flux: np.ndarray, threshold: float) -> np.ndarray:
        """Map flux values to RGBA face colours using a 5-band scheme."""
        if threshold <= 0:
            threshold = 1.0
        ratio = np.asarray(flux, dtype=np.float64) / threshold
        n = len(ratio)
        colors = np.zeros((n, 4), dtype=np.float32)
        colors[:, 3] = 1.0

        m = ratio < 0.25
        colors[m] = [0.0, 0.2, 0.8, 1.0]

        m = (ratio >= 0.25) & (ratio < 0.50)
        colors[m] = [0.0, 0.7, 0.2, 1.0]

        m = (ratio >= 0.50) & (ratio < 0.75)
        colors[m] = [0.9, 0.9, 0.0, 1.0]

        m = (ratio >= 0.75) & (ratio < 1.00)
        colors[m] = [1.0, 0.5, 0.0, 1.0]

        m = ratio >= 1.00
        colors[m] = [1.0, 0.0, 0.0, 1.0]

        return colors
