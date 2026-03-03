"""
dxf_preview_dialog.py
=====================
Preview-first DXF import dialog.

Workflow
--------
1. User browses to a DXF file → entities load in a preview view.
2. User can:
   • Filter layers via checkboxes
   • Rubber-band drag on the preview to select a spatial subset
   • Choose scale (dropdown or pick-2-pts-on-preview)
   • Pick a base point on the preview (default = DXF origin 0,0)
   • Set display colour and lineweight
3. On "Import →":
   • Dialog returns ImportParams with all settings
4. Caller (main.py) calls scene.begin_place_import(params)
5. A ghost bounding box follows the cursor on the model-space canvas.
6. User clicks the canvas → underlay group is placed at that point.
"""

from __future__ import annotations

import math
import os
import tempfile

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsTextItem,
    QLabel, QPushButton, QComboBox, QColorDialog,
    QListWidget, QListWidgetItem, QGroupBox,
    QFileDialog, QLineEdit, QDoubleSpinBox, QFormLayout,
    QDialogButtonBox, QProgressDialog, QApplication,
    QCheckBox, QWidget, QSizePolicy, QScrollArea,
    QMessageBox, QInputDialog,
)
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath, QFont, QCursor, QPainter
from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF, pyqtSignal

try:
    import ezdxf
    _HAS_EZDXF = True
except ImportError:
    _HAS_EZDXF = False

from dxf_import_dialog import _sanitize_dxf


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

class ImportParams:
    """Carries all parameters from the dialog to the scene."""
    def __init__(self):
        self.file_path: str = ""
        self.geom_list: list[dict] = []   # filtered geometry dicts
        self.scale: float = 1.0           # multiplier applied to all coordinates
        self.base_x: float = 0.0          # DXF-coord base point (subtracted before scaling)
        self.base_y: float = 0.0
        self.color: QColor = QColor("#ffffff")
        self.line_weight: float = 0.0
        self.selected_layers: list[str] | None = None  # None = all


# ─────────────────────────────────────────────────────────────────────────────
# Preview view
# ─────────────────────────────────────────────────────────────────────────────

class _PreviewView(QGraphicsView):
    """
    QGraphicsView with:
    - Middle-drag pan / scroll-wheel zoom
    - Modes: "pan" | "rubber_band" | "pick_point"
    - Signals: rubber_band_rect(QRectF), point_picked(QPointF)
    """
    rubber_band_rect = pyqtSignal(QRectF)
    point_picked = pyqtSignal(QPointF)

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setInteractive(False)
        self._mode = "pan"          # "pan" | "rubber_band" | "pick_point"
        self._pan_start = None
        self._rb_start: QPointF | None = None
        self._rb_item: QGraphicsRectItem | None = None

    def set_mode(self, mode: str):
        self._mode = mode
        if mode == "rubber_band":
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif mode == "pick_point":
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        old = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new = self.mapToScene(event.position().toPoint())
        d = new - old
        self.translate(d.x(), d.y())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (
                self._mode == "pan" and event.button() == Qt.MouseButton.LeftButton):
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            if self._mode == "rubber_band":
                self._rb_start = scene_pos
                self._rb_item = QGraphicsRectItem()
                pen = QPen(QColor("#00aaff"), 1, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self._rb_item.setPen(pen)
                self._rb_item.setBrush(QBrush(QColor(0, 170, 255, 30)))
                self._rb_item.setZValue(1000)
                self.scene().addItem(self._rb_item)
            elif self._mode == "pick_point":
                self.point_picked.emit(scene_pos)
                # Don't auto-switch to "pan" here — let the signal handler
                # decide (it may re-enter pick_point for multi-pick flows).

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
        elif self._mode == "rubber_band" and self._rb_start is not None:
            scene_pos = self.mapToScene(event.pos())
            rect = QRectF(self._rb_start, scene_pos).normalized()
            if self._rb_item:
                self._rb_item.setRect(rect)

    def mouseReleaseEvent(self, event):
        if self._pan_start is not None:
            self._pan_start = None
            if self._mode == "pan":
                self.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
        elif (event.button() == Qt.MouseButton.LeftButton
              and self._mode == "rubber_band"
              and self._rb_start is not None):
            scene_pos = self.mapToScene(event.pos())
            rect = QRectF(self._rb_start, scene_pos).normalized()
            if self._rb_item:
                self.scene().removeItem(self._rb_item)
                self._rb_item = None
            self._rb_start = None
            if rect.width() > 2 or rect.height() > 2:
                self.rubber_band_rect.emit(rect)
            self.set_mode("pan")


# ─────────────────────────────────────────────────────────────────────────────
# Main dialog
# ─────────────────────────────────────────────────────────────────────────────

class DxfPreviewDialog(QDialog):
    """Preview-first DXF import dialog."""

    _SCALE_OPTIONS = [
        ("1:1   (full size)",  1.0),
        ("1:2",               0.5),
        ("1:5",               0.2),
        ("1:10",              0.1),
        ("1:20",              0.05),
        ("1:50",              0.02),
        ("1:100",             0.01),
        ("1:200",             0.005),
        ("1:500",             0.002),
        ("1:1000",            0.001),
        ("Custom…",           None),
    ]

    _LW_OPTIONS = [
        ("Hairline (0)",          0.0),
        ("Very Light (0.18 mm)",  0.18),
        ("Light (0.25 mm)",       0.25),
        ("Medium (0.35 mm)",      0.35),
        ("Heavy (0.50 mm)",       0.50),
        ("Very Heavy (0.70 mm)",  0.70),
    ]

    def __init__(self, parent=None, file_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Import DXF — Preview")
        self.resize(1100, 700)

        self._colour = QColor("#ffffff")
        self._all_geoms: list[dict] = []      # all parsed geometry dicts
        self._layers: list[str] = []
        self._selected_indices: set[int] | None = None  # None = all
        self._base_x = 0.0
        self._base_y = 0.0
        self._pick_pts: list[QPointF] = []    # for 2-point scale pick
        self._base_marker: QGraphicsEllipseItem | None = None
        self._pick_markers: list[QGraphicsItem] = []

        self._pick_mode: str | None = None   # "base", "scale_pt1", "scale_pt2"

        self._preview_scene = QGraphicsScene()
        self._preview_view = _PreviewView(self._preview_scene)
        self._preview_view.rubber_band_rect.connect(self._on_rubber_band)
        self._preview_view.point_picked.connect(self._on_any_point_picked)

        self._build_ui()

        if file_path:
            self._file_edit.setText(file_path)
            self._load_file()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # File bar
        file_bar = QHBoxLayout()
        file_bar.addWidget(QLabel("DXF File:"))
        self._file_edit = QLineEdit()
        file_bar.addWidget(self._file_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_file)
        file_bar.addWidget(browse_btn)
        reload_btn = QPushButton("↺ Reload")
        reload_btn.clicked.connect(self._load_file)
        file_bar.addWidget(reload_btn)
        outer.addLayout(file_bar)

        # Preview + controls splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: preview
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(2)

        mode_bar = QHBoxLayout()
        self._pan_btn = QPushButton("Pan / Zoom")
        self._pan_btn.setCheckable(True)
        self._pan_btn.setChecked(True)
        self._pan_btn.clicked.connect(lambda: self._set_view_mode("pan"))
        self._rb_btn = QPushButton("✂ Select Area")
        self._rb_btn.setCheckable(True)
        self._rb_btn.setToolTip(
            "Drag a rectangle on the preview to import only entities within that area."
            "\nDrag outside or click 'Clear Selection' to reset."
        )
        self._rb_btn.clicked.connect(lambda: self._set_view_mode("rubber_band"))
        self._clear_sel_btn = QPushButton("Clear Selection")
        self._clear_sel_btn.clicked.connect(self._clear_selection)
        mode_bar.addWidget(self._pan_btn)
        mode_bar.addWidget(self._rb_btn)
        mode_bar.addWidget(self._clear_sel_btn)
        mode_bar.addStretch()
        left_lay.addLayout(mode_bar)

        left_lay.addWidget(self._preview_view, 1)

        self._info_lbl = QLabel("Load a DXF file to see a preview.")
        self._info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_lay.addWidget(self._info_lbl)
        splitter.addWidget(left)

        # Right: controls
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMinimumWidth(240)
        right_scroll.setMaximumWidth(320)
        right_w = QWidget()
        right_lay = QVBoxLayout(right_w)
        right_lay.setContentsMargins(4, 4, 4, 4)
        right_lay.setSpacing(6)

        # Layers
        layer_grp = QGroupBox("Layers")
        layer_vlay = QVBoxLayout(layer_grp)
        la_btn_row = QHBoxLayout()
        all_btn = QPushButton("All")
        all_btn.clicked.connect(self._select_all_layers)
        none_btn = QPushButton("None")
        none_btn.clicked.connect(self._deselect_all_layers)
        la_btn_row.addWidget(all_btn)
        la_btn_row.addWidget(none_btn)
        la_btn_row.addStretch()
        layer_vlay.addLayout(la_btn_row)
        self._layer_list = QListWidget()
        self._layer_list.setMaximumHeight(180)
        self._layer_list.itemChanged.connect(self._on_layer_changed)
        layer_vlay.addWidget(self._layer_list)
        right_lay.addWidget(layer_grp)

        # Scale
        scale_grp = QGroupBox("Scale")
        scale_vlay = QVBoxLayout(scale_grp)
        self._scale_combo = QComboBox()
        for label, _ in self._SCALE_OPTIONS:
            self._scale_combo.addItem(label)
        self._scale_combo.currentIndexChanged.connect(self._on_scale_combo_changed)
        scale_vlay.addWidget(self._scale_combo)
        self._custom_scale_spin = QDoubleSpinBox()
        self._custom_scale_spin.setRange(0.0001, 1000.0)
        self._custom_scale_spin.setDecimals(5)
        self._custom_scale_spin.setValue(1.0)
        self._custom_scale_spin.setSuffix("  ×")
        self._custom_scale_spin.setVisible(False)
        scale_vlay.addWidget(self._custom_scale_spin)
        pick2_btn = QPushButton("📐 Pick 2 pts on preview")
        pick2_btn.setToolTip(
            "Click two points on the preview, then enter the real distance between them."
        )
        pick2_btn.clicked.connect(self._start_pick2)
        scale_vlay.addWidget(pick2_btn)
        right_lay.addWidget(scale_grp)

        # Base point
        base_grp = QGroupBox("Base / Insertion Point (DXF coords)")
        base_form = QFormLayout(base_grp)
        self._base_x_spin = QDoubleSpinBox()
        self._base_x_spin.setRange(-1e9, 1e9)
        self._base_x_spin.setDecimals(3)
        self._base_x_spin.setValue(0.0)
        self._base_x_spin.valueChanged.connect(self._on_base_changed)
        self._base_y_spin = QDoubleSpinBox()
        self._base_y_spin.setRange(-1e9, 1e9)
        self._base_y_spin.setDecimals(3)
        self._base_y_spin.setValue(0.0)
        self._base_y_spin.valueChanged.connect(self._on_base_changed)
        base_form.addRow("X:", self._base_x_spin)
        base_form.addRow("Y:", self._base_y_spin)
        pick_base_btn = QPushButton("📍 Pick on preview")
        pick_base_btn.clicked.connect(self._start_pick_base)
        base_form.addRow(pick_base_btn)
        right_lay.addWidget(base_grp)

        # Display
        disp_grp = QGroupBox("Display")
        disp_lay = QFormLayout(disp_grp)
        colour_row = QHBoxLayout()
        self._colour_btn = QPushButton()
        self._colour_btn.setFixedSize(60, 24)
        self._update_colour_btn()
        self._colour_btn.clicked.connect(self._pick_colour)
        colour_row.addWidget(self._colour_btn)
        colour_row.addStretch()
        disp_lay.addRow("Colour:", colour_row)
        self._lw_combo = QComboBox()
        for label, _ in self._LW_OPTIONS:
            self._lw_combo.addItem(label)
        self._lw_combo.setCurrentIndex(1)
        disp_lay.addRow("Line weight:", self._lw_combo)
        right_lay.addWidget(disp_grp)

        right_lay.addStretch()
        right_scroll.setWidget(right_w)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, 1)

        # Bottom bar
        bot = QHBoxLayout()
        self._status_lbl = QLabel("")
        bot.addWidget(self._status_lbl, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import →")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        bot.addWidget(buttons)
        outer.addLayout(bot)

    # ── File loading ──────────────────────────────────────────────────────────

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DXF File", "", "DXF Files (*.dxf)"
        )
        if path:
            self._file_edit.setText(path)
            self._load_file()

    def _load_file(self):
        path = self._file_edit.text().strip()
        if not path or not os.path.exists(path):
            return
        if not _HAS_EZDXF:
            QMessageBox.warning(self, "Missing dependency",
                                "ezdxf is required for DXF import.\n"
                                "Install it with: pip install ezdxf")
            return

        self._info_lbl.setText("Loading…")
        QApplication.processEvents()

        # Parse DXF
        clean = _sanitize_dxf(path)
        try:
            doc = ezdxf.readfile(clean)
        except Exception as e:
            self._info_lbl.setText(f"Error: {e}")
            return
        finally:
            if clean != path and os.path.exists(clean):
                os.remove(clean)

        msp = doc.modelspace()
        layers_set: set[str] = {"0"}
        for layer in doc.layers:
            layers_set.add(layer.dxf.name)
        for entity in msp:
            layers_set.add(entity.dxf.get("layer", "0") if hasattr(entity.dxf, "get") else "0")

        self._layers = sorted(layers_set)
        self._populate_layer_list()

        # Extract geometry
        from dxf_import_worker import DxfImportWorker
        # Run synchronously for preview (small files are fine; large files show a dialog)
        geoms = []
        all_ents = list(msp)
        prog = QProgressDialog("Loading preview…", "Cancel", 0, len(all_ents), self)
        prog.setMinimumDuration(500)
        worker_ref = DxfImportWorker.__new__(DxfImportWorker)
        worker_ref._cancelled = False
        for i, ent in enumerate(all_ents):
            if prog.wasCanceled():
                break
            if i % 200 == 0:
                prog.setValue(i)
                QApplication.processEvents()
            try:
                g = worker_ref._extract_geometry(ent)
                if g is not None:
                    geoms.append(g)
            except Exception:
                pass
        prog.close()
        self._all_geoms = geoms
        self._selected_indices = None  # all selected
        self._rebuild_preview()
        n = len(self._all_geoms)
        self._info_lbl.setText(f"{n} entities loaded from {os.path.basename(path)}")
        self._update_status()

    def _populate_layer_list(self):
        self._layer_list.blockSignals(True)
        self._layer_list.clear()
        for name in self._layers:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._layer_list.addItem(item)
        self._layer_list.blockSignals(False)

    # ── Preview rendering ─────────────────────────────────────────────────────

    def _rebuild_preview(self):
        self._preview_scene.clear()
        self._base_marker = None
        self._pick_markers = []

        pen_normal = QPen(QColor("#c0c0c0"), 0)
        pen_normal.setCosmetic(True)
        pen_sel = QPen(QColor("#4fa3e0"), 0)
        pen_sel.setCosmetic(True)
        pen_dim = QPen(QColor("#444444"), 0)
        pen_dim.setCosmetic(True)

        active_layers = self._active_layers()
        for idx, g in enumerate(self._all_geoms):
            is_active_layer = (active_layers is None or g.get("layer", "0") in active_layers)
            is_selected = (self._selected_indices is None or idx in self._selected_indices)
            if is_active_layer and is_selected:
                pen = pen_sel
            elif is_active_layer:
                pen = pen_normal
            else:
                pen = pen_dim
            self._add_preview_geom(g, pen)

        self._draw_base_marker()
        if self._all_geoms:
            self._preview_view.fitInView(
                self._preview_scene.itemsBoundingRect().adjusted(-10, -10, 10, 10),
                Qt.AspectRatioMode.KeepAspectRatio
            )

    def _add_preview_geom(self, g: dict, pen: QPen):
        kind = g.get("kind")
        if kind == "line":
            item = QGraphicsLineItem(g["x1"], g["y1"], g["x2"], g["y2"])
            item.setPen(pen)
            self._preview_scene.addItem(item)
        elif kind == "circle":
            item = QGraphicsEllipseItem(g["x"], g["y"], g["w"], g["h"])
            item.setPen(pen)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._preview_scene.addItem(item)
        elif kind == "arc":
            item = QGraphicsEllipseItem(g["rx"], g["ry"], g["rw"], g["rh"])
            item.setPen(pen)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            item.setStartAngle(int(g["start"] * 16))
            item.setSpanAngle(int(g["span"] * 16))
            self._preview_scene.addItem(item)
        elif kind in ("path_points", "ellipse_full"):
            if kind == "ellipse_full":
                pts_raw = g
                item = QGraphicsEllipseItem(
                    g["pos_cx"] + g["x"], g["pos_cy"] + g["y"], g["w"], g["h"]
                )
                item.setPen(pen)
                item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                self._preview_scene.addItem(item)
                return
            pts = [QPointF(p[0], p[1]) for p in g["points"]]
            if len(pts) < 2:
                return
            path = QPainterPath(pts[0])
            for p in pts[1:]:
                path.lineTo(p)
            if g.get("closed") and len(pts) >= 3:
                path.closeSubpath()
            item = QGraphicsPathItem(path)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._preview_scene.addItem(item)
        elif kind == "text":
            item = QGraphicsTextItem(g.get("text", ""))
            item.setDefaultTextColor(pen.color())
            f = QFont()
            f.setPointSizeF(6)
            item.setFont(f)
            item.setPos(g["x"], g["y"])
            self._preview_scene.addItem(item)

    def _draw_base_marker(self):
        if self._base_marker is not None:
            if self._base_marker.scene() is self._preview_scene:
                self._preview_scene.removeItem(self._base_marker)
            self._base_marker = None
        # Draw a cross at base point
        bx = self._base_x_spin.value()
        by = self._base_y_spin.value()  # already in preview coords (y-flipped by worker)
        s = 15
        pen = QPen(QColor("#ff4400"), 2)
        pen.setCosmetic(True)
        h = QGraphicsLineItem(bx - s, by, bx + s, by)
        h.setPen(pen)
        h.setZValue(500)
        v = QGraphicsLineItem(bx, by - s, bx, by + s)
        v.setPen(pen)
        v.setZValue(500)
        self._preview_scene.addItem(h)
        self._preview_scene.addItem(v)
        self._base_marker = h  # store one for cleanup

    # ── Layer controls ────────────────────────────────────────────────────────

    def _active_layers(self) -> set[str] | None:
        if self._layer_list.count() == 0:
            return None
        checked = set()
        all_checked = True
        for i in range(self._layer_list.count()):
            it = self._layer_list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                checked.add(it.text())
            else:
                all_checked = False
        return None if all_checked else checked

    def _select_all_layers(self):
        self._layer_list.blockSignals(True)
        for i in range(self._layer_list.count()):
            self._layer_list.item(i).setCheckState(Qt.CheckState.Checked)
        self._layer_list.blockSignals(False)
        self._on_layer_changed()

    def _deselect_all_layers(self):
        self._layer_list.blockSignals(True)
        for i in range(self._layer_list.count()):
            self._layer_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._layer_list.blockSignals(False)
        self._on_layer_changed()

    def _on_layer_changed(self, *_):
        self._rebuild_preview()
        self._update_status()

    # ── Rubber-band selection ────────────────────────────────────────────────

    def _set_view_mode(self, mode: str):
        self._pan_btn.setChecked(mode == "pan")
        self._rb_btn.setChecked(mode == "rubber_band")
        self._preview_view.set_mode(mode)

    def _on_rubber_band(self, rect: QRectF):
        """Select geometry items that fall within the rubber-band rect."""
        selected = set()
        for idx, g in enumerate(self._all_geoms):
            if self._geom_in_rect(g, rect):
                selected.add(idx)
        if selected:
            if self._selected_indices is None:
                self._selected_indices = selected
            else:
                self._selected_indices &= selected
        self._rebuild_preview()
        self._update_status()
        self._set_view_mode("pan")

    def _geom_in_rect(self, g: dict, rect: QRectF) -> bool:
        kind = g.get("kind")
        if kind == "line":
            return (rect.contains(QPointF(g["x1"], g["y1"])) or
                    rect.contains(QPointF(g["x2"], g["y2"])))
        elif kind in ("circle", "arc"):
            cx = g.get("x", g.get("rx", 0)) + g.get("w", g.get("rw", 0)) / 2
            cy = g.get("y", g.get("ry", 0)) + g.get("h", g.get("rh", 0)) / 2
            return rect.contains(QPointF(cx, cy))
        elif kind == "path_points":
            pts = g.get("points", [])
            return any(rect.contains(QPointF(p[0], p[1])) for p in pts)
        elif kind == "text":
            return rect.contains(QPointF(g.get("x", 0), g.get("y", 0)))
        return rect.contains(QPointF(0, 0))

    def _clear_selection(self):
        self._selected_indices = None
        self._rebuild_preview()
        self._update_status()

    # ── Scale ─────────────────────────────────────────────────────────────────

    def _on_scale_combo_changed(self, idx: int):
        _, val = self._SCALE_OPTIONS[idx]
        self._custom_scale_spin.setVisible(val is None)

    def _current_scale(self) -> float:
        idx = self._scale_combo.currentIndex()
        _, val = self._SCALE_OPTIONS[idx]
        if val is None:
            return self._custom_scale_spin.value()
        return val

    def _start_pick2(self):
        """Enter 2-point scale pick mode."""
        self._pick_pts = []
        # Remove old markers
        for m in self._pick_markers:
            if m.scene() is self._preview_scene:
                self._preview_scene.removeItem(m)
        self._pick_markers = []
        self._pick_mode = "scale_pt1"
        self._preview_view.set_mode("pick_point")
        self._status_lbl.setText("Click the FIRST point on the preview\u2026")

    def _on_any_point_picked(self, raw_pt: QPointF):
        """Single dispatcher for all point-pick modes — avoids fragile disconnect/connect."""
        pt = self._snap_to_nearest(raw_pt)
        if self._pick_mode in ("scale_pt1", "scale_pt2"):
            self._on_pick2_pt(pt)
        elif self._pick_mode == "base":
            self._on_point_picked(pt)

    def _on_pick2_pt(self, pt: QPointF):
        """Handle a point picked during 2-point scale mode (already snapped)."""
        pen = QPen(QColor("#ff0000"), 2)
        pen.setCosmetic(True)
        s = 8
        h = QGraphicsLineItem(pt.x() - s, pt.y(), pt.x() + s, pt.y())
        h.setPen(pen); h.setZValue(600)
        v = QGraphicsLineItem(pt.x(), pt.y() - s, pt.x(), pt.y() + s)
        v.setPen(pen); v.setZValue(600)
        self._preview_scene.addItem(h)
        self._preview_scene.addItem(v)
        self._pick_markers.extend([h, v])
        self._pick_pts.append(pt)

        if len(self._pick_pts) == 1:
            self._pick_mode = "scale_pt2"
            self._status_lbl.setText("Click the SECOND point on the preview\u2026")
            self._preview_view.set_mode("pick_point")
        elif len(self._pick_pts) == 2:
            # Draw line between the two points
            line = QGraphicsLineItem(
                self._pick_pts[0].x(), self._pick_pts[0].y(),
                self._pick_pts[1].x(), self._pick_pts[1].y()
            )
            line.setPen(QPen(QColor("#ff0000"), 1))
            line.setZValue(600)
            self._preview_scene.addItem(line)
            self._pick_markers.append(line)

            px_dist = math.hypot(
                self._pick_pts[1].x() - self._pick_pts[0].x(),
                self._pick_pts[1].y() - self._pick_pts[0].y()
            )
            # Return to pan mode
            self._pick_mode = None
            self._preview_view.set_mode("pan")

            if px_dist < 1.0:
                self._status_lbl.setText("Points too close \u2014 try again.")
                return

            real_dist, ok = QInputDialog.getDouble(
                self, "Real Distance",
                f"The two points are {px_dist:.1f} preview units apart.\n"
                "Enter the REAL distance between them:",
                decimals=3, min=0.001, max=1e9
            )
            if ok and real_dist > 0:
                factor = real_dist / px_dist
                # Set custom scale
                custom_idx = len(self._SCALE_OPTIONS) - 1
                self._scale_combo.setCurrentIndex(custom_idx)
                self._custom_scale_spin.setValue(factor)
                self._status_lbl.setText(
                    f"Scale set: {px_dist:.1f} preview units = {real_dist} real \u2192 \u00d7{factor:.5f}"
                )
            else:
                self._status_lbl.setText("Scale pick cancelled.")

    # ── Snap to nearest geometry vertex ──────────────────────────────────────

    def _snap_to_nearest(self, pt: QPointF, tolerance: float = 0.0) -> QPointF:
        """Snap *pt* to the nearest geometry vertex within tolerance.

        If tolerance is 0, it auto-calculates from the current zoom level.
        Returns the snapped point, or the original if nothing is close enough.
        """
        if tolerance <= 0:
            # ~15 pixels in scene coordinates
            vp = self._preview_view
            p0 = vp.mapToScene(0, 0)
            p1 = vp.mapToScene(15, 0)
            tolerance = abs(p1.x() - p0.x())
            if tolerance < 1e-6:
                tolerance = 20.0

        best_dist = tolerance
        best_pt = pt

        for g in self._all_geoms:
            candidates: list[tuple[float, float]] = []
            kind = g.get("kind")
            if kind == "line":
                candidates.append((g["x1"], g["y1"]))
                candidates.append((g["x2"], g["y2"]))
            elif kind in ("circle", "arc"):
                cx = g.get("x", g.get("rx", 0)) + g.get("w", g.get("rw", 0)) / 2
                cy = g.get("y", g.get("ry", 0)) + g.get("h", g.get("rh", 0)) / 2
                candidates.append((cx, cy))
            elif kind == "path_points":
                for p in g.get("points", []):
                    if len(p) >= 2:
                        candidates.append((p[0], p[1]))
            elif kind == "text":
                candidates.append((g.get("x", 0), g.get("y", 0)))

            for cx, cy in candidates:
                d = math.hypot(cx - pt.x(), cy - pt.y())
                if d < best_dist:
                    best_dist = d
                    best_pt = QPointF(cx, cy)

        return best_pt

    # ── Base point ────────────────────────────────────────────────────────────

    def _start_pick_base(self):
        self._pick_mode = "base"
        self._preview_view.set_mode("pick_point")
        self._status_lbl.setText("Click the base / insertion point on the preview\u2026")

    def _on_point_picked(self, pt: QPointF):
        """Store the picked point as the DXF base point (already snapped)."""
        # The preview is in the same coordinate space as the raw DXF geometry
        self._base_x_spin.blockSignals(True)
        self._base_y_spin.blockSignals(True)
        self._base_x_spin.setValue(pt.x())
        self._base_y_spin.setValue(pt.y())
        self._base_x_spin.blockSignals(False)
        self._base_y_spin.blockSignals(False)
        self._draw_base_marker()
        self._pick_mode = None
        self._status_lbl.setText(
            f"Base point set to ({pt.x():.3f}, {pt.y():.3f}) in DXF coordinates."
        )
        self._preview_view.set_mode("pan")

    def _on_base_changed(self):
        self._draw_base_marker()

    # ── Colour ────────────────────────────────────────────────────────────────

    def _pick_colour(self):
        c = QColorDialog.getColor(self._colour, self, "Line Colour")
        if c.isValid():
            self._colour = c
            self._update_colour_btn()

    def _update_colour_btn(self):
        self._colour_btn.setStyleSheet(
            f"background-color: {self._colour.name()}; border: 1px solid #888;"
        )

    # ── Status ────────────────────────────────────────────────────────────────

    def _update_status(self):
        total = len(self._all_geoms)
        active_layers = self._active_layers()
        layer_filtered = [
            g for g in self._all_geoms
            if active_layers is None or g.get("layer", "0") in active_layers
        ]
        if self._selected_indices is None:
            selected_n = len(layer_filtered)
        else:
            selected_n = len([
                g for idx, g in enumerate(self._all_geoms)
                if idx in self._selected_indices
                and (active_layers is None or g.get("layer", "0") in active_layers)
            ])
        self._status_lbl.setText(
            f"{selected_n} of {total} entities selected for import."
        )

    # ── Accept / result ───────────────────────────────────────────────────────

    def _on_accept(self):
        if not self._all_geoms:
            QMessageBox.warning(self, "Nothing to import",
                                "Load a DXF file before importing.")
            return
        self.accept()

    def get_import_params(self) -> ImportParams:
        """Call after dialog.exec() == Accepted."""
        p = ImportParams()
        p.file_path = self._file_edit.text().strip()
        p.scale = self._current_scale()
        p.base_x = self._base_x_spin.value()
        p.base_y = self._base_y_spin.value()
        p.color = QColor(self._colour)
        p.line_weight = self._LW_OPTIONS[self._lw_combo.currentIndex()][1]
        p.selected_layers = (
            list(self._active_layers())
            if self._active_layers() is not None
            else None
        )

        active_layers = self._active_layers()
        geoms = []
        for idx, g in enumerate(self._all_geoms):
            if active_layers is not None and g.get("layer", "0") not in active_layers:
                continue
            if self._selected_indices is not None and idx not in self._selected_indices:
                continue
            geoms.append(g)
        p.geom_list = geoms
        return p
