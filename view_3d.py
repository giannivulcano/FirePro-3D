"""
view_3d.py
==========
Interactive 3D visualization of the sprinkler / piping model using vispy.

Renders nodes, pipes, sprinklers, construction geometry, level floors,
and architectural entities (walls, floor slabs) in a 3D scene.
Supports click-to-select with bidirectional sync to the 2D Model Space.
"""

from __future__ import annotations

import math
import numpy as np

import vispy
vispy.use("pyqt6")

from vispy import scene
from vispy.scene import visuals
from vispy.geometry import create_cylinder

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import pyqtSignal, QTimer

from node import Node
from pipe import Pipe
from sprinkler import Sprinkler
from construction_geometry import (
    ConstructionLine, PolylineItem, LineItem, RectangleItem, CircleItem, ArcItem,
)
from gridline import GridlineItem
from water_supply import WaterSupply
from Annotations import DimensionAnnotation, NoteAnnotation
from wall import WallSegment
from floor_slab import FloorSlab


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

FT_TO_MM = 304.8
CIRCLE_SEGMENTS = 64
PICK_TOLERANCE_PX = 15

# Pipe nominal diameter → approximate OD in inches (for cylinder radius)
_NOMINAL_OD_IN = {
    '1"Ø': 1.315, '1-½"Ø': 1.900, '2"Ø': 2.375, '3"Ø': 3.500,
    '4"Ø': 4.500, '5"Ø': 5.563, '6"Ø': 6.625, '8"Ø': 8.625,
    # Legacy keys without Ø
    '1"': 1.315, '1-½"': 1.900, '2"': 2.375, '3"': 3.500,
    '4"': 4.500, '5"': 5.563, '6"': 6.625, '8"': 8.625,
}

# Colors
COL_NODE        = (0.55, 0.55, 0.55, 1.0)
COL_SPRINKLER   = (1.0, 0.2, 0.2, 1.0)
COL_WATER_SUPPLY = (0.0, 0.7, 0.86, 1.0)
COL_HIGHLIGHT   = (1.0, 1.0, 0.0, 0.85)
COL_CONSTR      = (0.4, 0.4, 0.4, 0.6)

# Pipe color name → RGBA
_PIPE_COLORS = {
    "Red":   (0.9, 0.15, 0.15, 1.0),
    "Blue":  (0.2, 0.4, 0.9, 1.0),
    "Black": (0.1, 0.1, 0.1, 1.0),
    "White": (0.95, 0.95, 0.95, 1.0),
    "Grey":  (0.55, 0.55, 0.55, 1.0),
}

# Level floor hues (cycled)
_FLOOR_COLORS = [
    (0.2, 0.4, 0.8, 0.12),
    (0.2, 0.8, 0.4, 0.12),
    (0.8, 0.4, 0.2, 0.12),
    (0.8, 0.2, 0.8, 0.12),
    (0.2, 0.8, 0.8, 0.12),
]


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

        # Ortho / perspective state
        self._perspective = True

        self._build_ui()
        self._connect_signals()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        tb = QHBoxLayout()
        tb.setContentsMargins(4, 2, 4, 2)

        self._fit_btn = QPushButton("Fit All")
        self._fit_btn.setFixedHeight(24)
        self._fit_btn.clicked.connect(self._fit_camera)
        tb.addWidget(self._fit_btn)

        self._proj_btn = QPushButton("Ortho")
        self._proj_btn.setFixedHeight(24)
        self._proj_btn.clicked.connect(self._toggle_projection)
        tb.addWidget(self._proj_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedHeight(24)
        self._refresh_btn.clicked.connect(self.rebuild)
        tb.addWidget(self._refresh_btn)

        self._section_h_btn = QPushButton("H-Cut")
        self._section_h_btn.setFixedHeight(24)
        self._section_h_btn.setCheckable(True)
        self._section_h_btn.setToolTip("Horizontal section cut — hides geometry above cut height")
        self._section_h_btn.clicked.connect(self._toggle_horizontal_cut)
        tb.addWidget(self._section_h_btn)

        tb.addStretch()
        self._info_label = QLabel("")
        tb.addWidget(self._info_label)
        layout.addLayout(tb)

        # vispy canvas
        self._canvas = scene.SceneCanvas(keys="interactive", show=False)
        self._canvas.bgcolor = (0.12, 0.12, 0.14, 1.0)
        self._view = self._canvas.central_widget.add_view()
        self._view.camera = scene.TurntableCamera(
            fov=45, distance=10000, elevation=30, azimuth=45,
        )

        layout.addWidget(self._canvas.native)

        # Visuals (created once, data updated on rebuild)
        self._node_markers = visuals.Markers(parent=self._view.scene)
        self._sprinkler_markers = visuals.Markers(parent=self._view.scene)
        self._pipe_lines = visuals.Line(parent=self._view.scene, antialias=True)
        self._constr_lines = visuals.Line(
            parent=self._view.scene, antialias=True, color=COL_CONSTR,
        )
        self._ws_marker = visuals.Markers(parent=self._view.scene)
        self._highlight_markers = visuals.Markers(parent=self._view.scene)
        self._highlight_markers.visible = False

        # Level floor meshes (dynamic, recreated on rebuild)
        self._floor_meshes: list[visuals.Mesh] = []
        # Wall and slab meshes (dynamic, recreated on rebuild)
        self._wall_meshes: list[visuals.Mesh] = []
        self._slab_meshes: list[visuals.Mesh] = []

        # Section cut state
        self._h_cut_enabled: bool = False
        self._h_cut_height_mm: float = 3000.0     # default ~10 ft

        # Debounce timer
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(100)
        self._rebuild_timer.timeout.connect(self._do_rebuild)

        # Mouse picking
        self._canvas.events.mouse_press.connect(self._on_mouse_press)

    def _connect_signals(self):
        self._scene.sceneModified.connect(self._schedule_rebuild)
        self._scene.selectionChanged.connect(self._on_2d_selection_changed)

    # ── Coordinate mapping ─────────────────────────────────────────────────

    def _scene_to_3d(self, sx: float, sy: float, z_ft: float = 0.0):
        """Convert 2D scene coords + elevation (ft) to 3D world (mm)."""
        ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
        return np.array([sx / ppm, -sy / ppm, z_ft * FT_TO_MM])

    def _node_to_3d(self, node: Node):
        return self._scene_to_3d(
            node.scenePos().x(), node.scenePos().y(), node.z_pos,
        )

    def _level_z_mm(self, level_name: str) -> float:
        lvl = self._lm.get(level_name)
        return (lvl.elevation if lvl else 0.0) * FT_TO_MM

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

    def rebuild(self):
        """Rebuild all 3D visuals from Model_Space data."""
        self._dirty = False

        self._extract_nodes()
        self._extract_pipes()
        self._extract_sprinklers()
        self._extract_water_supply()
        self._extract_construction_geometry()
        self._extract_level_floors()
        self._extract_walls()
        self._extract_floor_slabs()
        self._on_2d_selection_changed()

        if self._first_build:
            self._fit_camera()
            self._first_build = False

        counts = (
            f"Nodes: {len(self._node_refs)}  "
            f"Pipes: {len(self._pipe_refs)}"
        )
        self._info_label.setText(counts)
        self._canvas.update()

    # ── Extract: Nodes ─────────────────────────────────────────────────────

    def _extract_nodes(self):
        nodes = list(self._scene.sprinkler_system.nodes)
        self._node_refs = nodes
        if not nodes:
            self._node_markers.visible = False
            self._node_positions_3d = None
            return

        positions = np.array([self._node_to_3d(n) for n in nodes])
        self._node_positions_3d = positions

        colors = np.array([
            COL_NODE if not n.has_sprinkler() else (0.3, 0.3, 0.3, 0.5)
            for n in nodes
        ])
        self._node_markers.set_data(
            pos=positions, face_color=colors, size=6, edge_width=0,
        )
        self._node_markers.visible = True

    # ── Extract: Sprinklers ────────────────────────────────────────────────

    def _extract_sprinklers(self):
        nodes_with_spr = [n for n in self._scene.sprinkler_system.nodes
                          if n.has_sprinkler()]
        if not nodes_with_spr:
            self._sprinkler_markers.visible = False
            return

        positions = np.array([self._node_to_3d(n) for n in nodes_with_spr])
        colors = []
        for n in nodes_with_spr:
            orient = n.sprinkler._properties.get("Orientation", {}).get("value", "Upright")
            if orient == "Pendent":
                colors.append((1.0, 0.2, 0.2, 1.0))
            elif orient == "Sidewall":
                colors.append((0.2, 0.8, 0.2, 1.0))
            else:
                colors.append((0.2, 0.4, 1.0, 1.0))
        colors = np.array(colors)

        self._sprinkler_markers.set_data(
            pos=positions, face_color=colors, size=10,
            edge_width=1, edge_color=(1, 1, 1, 0.8),
            symbol="disc",
        )
        self._sprinkler_markers.visible = True

    # ── Extract: Pipes ─────────────────────────────────────────────────────

    def _extract_pipes(self):
        pipes = list(self._scene.sprinkler_system.pipes)
        self._pipe_refs = pipes
        if not pipes:
            self._pipe_lines.visible = False
            self._pipe_midpoints_3d = None
            return

        # Build line segment pairs
        positions = []
        colors = []
        mids = []
        for p in pipes:
            p1 = self._node_to_3d(p.node1)
            p2 = self._node_to_3d(p.node2)
            positions.append(p1)
            positions.append(p2)
            mids.append((p1 + p2) / 2.0)

            col_name = p._properties.get("Colour", {}).get("value", "Red")
            c = _PIPE_COLORS.get(col_name, (0.9, 0.15, 0.15, 1.0))
            colors.append(c)
            colors.append(c)

        self._pipe_midpoints_3d = np.array(mids)

        # Line width from average nominal diameter
        nom = pipes[0]._properties.get("Diameter", {}).get("value", '2"Ø')
        od = _NOMINAL_OD_IN.get(nom, 2.375)
        width = max(2.0, od * 1.5)

        self._pipe_lines.set_data(
            pos=np.array(positions),
            color=np.array(colors),
            width=width,
            connect="segments",
        )
        self._pipe_lines.visible = True

    # ── Extract: Water Supply ──────────────────────────────────────────────

    def _extract_water_supply(self):
        ws = getattr(self._scene, "water_supply_node", None)
        if ws is None:
            self._ws_marker.visible = False
            return
        pos = self._scene_to_3d(ws.scenePos().x(), ws.scenePos().y(), 0)
        self._ws_marker.set_data(
            pos=np.array([pos]), face_color=[COL_WATER_SUPPLY],
            size=14, edge_width=2, edge_color=(1, 1, 1, 1),
            symbol="diamond",
        )
        self._ws_marker.visible = True

    # ── Extract: Construction Geometry ─────────────────────────────────────

    def _extract_construction_geometry(self):
        lines_data = []  # pairs of 3D points

        def _pen_rgba(item):
            c = item.pen().color()
            return (c.redF(), c.greenF(), c.blueF(), c.alphaF())

        # Lines
        for item in getattr(self._scene, "_draw_lines", []):
            z = self._level_z_mm(getattr(item, "level", "Level 1"))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            p1 = item._pt1
            p2 = item._pt2
            lines_data.append(np.array([p1.x() / ppm, -p1.y() / ppm, z]))
            lines_data.append(np.array([p2.x() / ppm, -p2.y() / ppm, z]))

        # Construction lines
        for item in getattr(self._scene, "_construction_lines", []):
            z = self._level_z_mm(getattr(item, "level", "Level 1"))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            p1 = item._pt1
            p2 = item._pt2
            lines_data.append(np.array([p1.x() / ppm, -p1.y() / ppm, z]))
            lines_data.append(np.array([p2.x() / ppm, -p2.y() / ppm, z]))

        # Rectangles (4 edges)
        for item in getattr(self._scene, "_draw_rects", []):
            z = self._level_z_mm(getattr(item, "level", "Level 1"))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            r = item.rect()
            corners = [
                np.array([r.left() / ppm, -r.top() / ppm, z]),
                np.array([r.right() / ppm, -r.top() / ppm, z]),
                np.array([r.right() / ppm, -r.bottom() / ppm, z]),
                np.array([r.left() / ppm, -r.bottom() / ppm, z]),
            ]
            for i in range(4):
                lines_data.append(corners[i])
                lines_data.append(corners[(i + 1) % 4])

        # Circles (polygon approximation)
        for item in getattr(self._scene, "_draw_circles", []):
            z = self._level_z_mm(getattr(item, "level", "Level 1"))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            cx = item._center.x() / ppm
            cy = -item._center.y() / ppm
            r = item._radius / ppm
            for i in range(CIRCLE_SEGMENTS):
                a1 = 2 * math.pi * i / CIRCLE_SEGMENTS
                a2 = 2 * math.pi * (i + 1) / CIRCLE_SEGMENTS
                lines_data.append(np.array([cx + r * math.cos(a1), cy + r * math.sin(a1), z]))
                lines_data.append(np.array([cx + r * math.cos(a2), cy + r * math.sin(a2), z]))

        # Arcs
        for item in getattr(self._scene, "_draw_arcs", []):
            z = self._level_z_mm(getattr(item, "level", "Level 1"))
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
                lines_data.append(np.array([cx + r * math.cos(a1), cy + r * math.sin(a1), z]))
                lines_data.append(np.array([cx + r * math.cos(a2), cy + r * math.sin(a2), z]))

        # Polylines
        for item in getattr(self._scene, "_polylines", []):
            z = self._level_z_mm(getattr(item, "level", "Level 1"))
            ppm = self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0
            pts = item._points
            for i in range(len(pts) - 1):
                lines_data.append(np.array([pts[i].x() / ppm, -pts[i].y() / ppm, z]))
                lines_data.append(np.array([pts[i + 1].x() / ppm, -pts[i + 1].y() / ppm, z]))

        if lines_data:
            self._constr_lines.set_data(
                pos=np.array(lines_data), connect="segments",
            )
            self._constr_lines.visible = True
        else:
            self._constr_lines.visible = False

    # ── Extract: Level Floors ──────────────────────────────────────────────

    def _extract_level_floors(self):
        # Remove old floor meshes
        for m in self._floor_meshes:
            m.parent = None
        self._floor_meshes.clear()

        # Compute overall XY bounds from all nodes
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
            z = lvl.elevation * FT_TO_MM
            col = _FLOOR_COLORS[i % len(_FLOOR_COLORS)]

            verts = np.array([
                [x_min, y_min, z],
                [x_max, y_min, z],
                [x_max, y_max, z],
                [x_min, y_max, z],
            ], dtype=np.float32)
            faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32)

            mesh = visuals.Mesh(
                vertices=verts, faces=faces,
                color=col,
                parent=self._view.scene,
            )
            self._floor_meshes.append(mesh)

    # ── Extract: Walls (stub — filled in Phase B) ─────────────────────────

    def _extract_walls(self):
        """Render wall entities as extruded 3D meshes."""
        # Remove old meshes
        for m in self._wall_meshes:
            m.parent = None
        self._wall_meshes.clear()

        scene_obj = self._scene
        if scene_obj is None:
            return
        lm = self._level_manager
        for wall in getattr(scene_obj, "_walls", []):
            mesh_data = wall.get_3d_mesh(level_manager=lm)
            if mesh_data is None:
                continue
            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)
            col = mesh_data.get("color", (0.8, 0.8, 0.8, 0.9))
            mesh = visuals.Mesh(
                vertices=verts, faces=faces,
                color=col,
                parent=self._view.scene,
            )
            self._wall_meshes.append(mesh)

    # ── Extract: Floor Slabs ──────────────────────────────────────────────

    def _extract_floor_slabs(self):
        """Render floor slab entities as solid 3D meshes."""
        # Remove old meshes
        for m in self._slab_meshes:
            m.parent = None
        self._slab_meshes.clear()

        scene_obj = self._scene
        if scene_obj is None:
            return
        lm = self._level_manager
        for slab in getattr(scene_obj, "_floor_slabs", []):
            mesh_data = slab.get_3d_mesh(level_manager=lm)
            if mesh_data is None:
                continue
            verts = np.array(mesh_data["vertices"], dtype=np.float32)
            faces = np.array(mesh_data["faces"], dtype=np.uint32)
            col = mesh_data.get("color", (0.5, 0.5, 0.8, 0.5))
            mesh = visuals.Mesh(
                vertices=verts, faces=faces,
                color=col,
                parent=self._view.scene,
            )
            self._slab_meshes.append(mesh)

    # ── Camera ─────────────────────────────────────────────────────────────

    def _fit_camera(self):
        """Auto-fit camera to encompass all geometry."""
        if self._node_positions_3d is not None and len(self._node_positions_3d) > 0:
            center = self._node_positions_3d.mean(axis=0)
            span = self._node_positions_3d.ptp(axis=0)  # range per axis
            dist = max(span) * 1.8
            self._view.camera.center = tuple(center)
            self._view.camera.distance = max(dist, 1000)

    def _toggle_projection(self):
        """Toggle between perspective and orthographic projection."""
        self._perspective = not self._perspective
        if self._perspective:
            self._view.camera.fov = 45
            self._proj_btn.setText("Ortho")
        else:
            self._view.camera.fov = 0
            self._proj_btn.setText("Perspective")

    # ── Section Cuts ───────────────────────────────────────────────────────

    def _toggle_horizontal_cut(self):
        """Toggle horizontal section cut on/off."""
        self._h_cut_enabled = self._section_h_btn.isChecked()
        if self._h_cut_enabled:
            # Use mid-level height as default cut if levels exist
            if self._level_manager is not None:
                levels = self._level_manager.levels
                if len(levels) >= 2:
                    self._h_cut_height_mm = levels[1].elevation * FT_TO_MM
            self._apply_horizontal_cut()
        else:
            self._remove_horizontal_cut()
        self._canvas.update()

    def _apply_horizontal_cut(self):
        """Hide all meshes whose geometry is entirely above the cut plane."""
        cut_z = self._h_cut_height_mm
        for mesh_list in (self._wall_meshes, self._slab_meshes, self._floor_meshes):
            for m in mesh_list:
                md = getattr(m, '_meshdata', None)
                if md is not None:
                    verts = md.get_vertices()
                    if verts is not None and len(verts) > 0:
                        min_z = verts[:, 2].min()
                        m.visible = min_z < cut_z
                    else:
                        m.visible = True
                else:
                    m.visible = True

        # Clip nodes/sprinklers above cut
        if self._node_positions_3d is not None and len(self._node_positions_3d) > 0:
            below = self._node_positions_3d[:, 2] < cut_z
            pos_vis = self._node_positions_3d[below]
            if len(pos_vis) > 0:
                self._node_markers.set_data(
                    pos=pos_vis,
                    face_color=COL_NODE, edge_color=COL_NODE,
                    size=6,
                )
            else:
                self._node_markers.set_data(pos=np.zeros((0, 3), dtype=np.float32))

    def _remove_horizontal_cut(self):
        """Restore all meshes to visible."""
        for mesh_list in (self._wall_meshes, self._slab_meshes, self._floor_meshes):
            for m in mesh_list:
                m.visible = True
        # Restore node markers
        if self._node_positions_3d is not None and len(self._node_positions_3d) > 0:
            self._node_markers.set_data(
                pos=self._node_positions_3d,
                face_color=COL_NODE, edge_color=COL_NODE,
                size=6,
            )

    # ── Selection / Picking ────────────────────────────────────────────────

    def _on_mouse_press(self, event):
        """Handle click in 3D view for entity selection."""
        if event.button != 1:  # left click only
            return

        screen_pos = np.array(event.pos[:2], dtype=float)
        hit = self._pick_nearest(screen_pos)

        if hit is not None:
            self._scene.clearSelection()
            hit.setSelected(True)
            self.entitySelected.emit(hit)
        else:
            self._scene.clearSelection()
            self.entitySelected.emit(None)

    def _pick_nearest(self, screen_pos: np.ndarray):
        """Find nearest entity to a screen-space click position."""
        tr = self._view.camera.transform
        best_item = None
        best_dist = float("inf")

        # Check nodes
        if self._node_positions_3d is not None:
            for i, pos3d in enumerate(self._node_positions_3d):
                screen = self._project_to_screen(pos3d)
                if screen is None:
                    continue
                dist = np.linalg.norm(screen - screen_pos)
                if dist < PICK_TOLERANCE_PX and dist < best_dist:
                    best_dist = dist
                    best_item = self._node_refs[i]

        # Check pipe midpoints
        if self._pipe_midpoints_3d is not None:
            for i, pos3d in enumerate(self._pipe_midpoints_3d):
                screen = self._project_to_screen(pos3d)
                if screen is None:
                    continue
                dist = np.linalg.norm(screen - screen_pos)
                if dist < PICK_TOLERANCE_PX and dist < best_dist:
                    best_dist = dist
                    best_item = self._pipe_refs[i]

        return best_item

    def _project_to_screen(self, world_pos: np.ndarray):
        """Project a 3D world position to 2D screen coordinates."""
        try:
            tr = self._view.scene.transform
            mapped = tr.map(world_pos)
            return np.array(mapped[:2])
        except Exception:
            return None

    # ── 2D → 3D Selection Sync ─────────────────────────────────────────────

    def _on_2d_selection_changed(self):
        """Highlight selected items in 3D."""
        selected = self._scene.selectedItems()
        if not selected:
            self._highlight_markers.visible = False
            return

        positions = []
        for item in selected:
            if isinstance(item, Node):
                positions.append(self._node_to_3d(item))
            elif isinstance(item, Pipe):
                mid = (self._node_to_3d(item.node1) + self._node_to_3d(item.node2)) / 2
                positions.append(mid)

        if positions:
            self._highlight_markers.set_data(
                pos=np.array(positions),
                face_color=COL_HIGHLIGHT,
                size=16, edge_width=2, edge_color=(1, 1, 1, 1),
                symbol="ring",
            )
            self._highlight_markers.visible = True
        else:
            self._highlight_markers.visible = False
