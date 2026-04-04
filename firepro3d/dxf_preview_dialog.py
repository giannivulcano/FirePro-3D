"""
dxf_preview_dialog.py
=====================
Unified underlay import dialog for FirePro 3D.

Handles both **PDF** and **DXF** files from a single preview-first dialog.

Workflow
--------
1. User browses (or drags) a PDF or DXF file → entities load in a preview view.
2. User can:
   • Filter source layers via checkboxes
   • Rubber-band drag on the preview to select a spatial subset
   • Choose scale (dropdown, pick-2-pts, or auto-detected DXF units)
   • Pick a base point on the preview (default = origin 0,0)
   • Choose a destination Layer (colour/lineweight derived from it)
   • For multi-page PDFs: click a thumbnail to switch pages
3. On "Import →":
   • Dialog returns ImportParams with all settings
4. Caller (main.py) calls scene.begin_place_import(params)  or places at origin.
"""

from __future__ import annotations

import math
import os
import tempfile

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsItemGroup,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem,
    QLabel, QPushButton, QComboBox, QColorDialog,
    QListWidget, QListWidgetItem, QGroupBox,
    QFileDialog, QLineEdit, QDoubleSpinBox, QFormLayout,
    QDialogButtonBox, QProgressDialog, QApplication,
    QCheckBox, QWidget, QSizePolicy, QScrollArea,
    QMessageBox, QInputDialog, QAbstractItemView,
)
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QPainterPath, QFont, QCursor, QPainter,
    QPixmap, QIcon,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF, QSize, QSettings, pyqtSignal

try:
    import ezdxf
    _HAS_EZDXF = True
except ImportError:
    _HAS_EZDXF = False

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    fitz = None
    _HAS_FITZ = False

from dxf_import_worker import _sanitize_dxf
from snap_engine import SnapEngine, OsnapResult, SNAP_COLORS
from constants import DEFAULT_USER_LAYER


# ─────────────────────────────────────────────────────────────────────────────
# DXF $INSUNITS mapping
# ─────────────────────────────────────────────────────────────────────────────

_DXF_INSUNITS: dict[int, tuple[str, float]] = {
    # code: (display_name, scale_factor_to_inches)
    0: ("Unitless",  1.0),
    1: ("Inches",    1.0),
    2: ("Feet",      12.0),
    4: ("Millimeters", 1.0 / 25.4),
    5: ("Centimeters", 1.0 / 2.54),
    6: ("Meters",    1.0 / 0.0254),
}


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

class ImportParams:
    """Carries all parameters from the dialog to the scene."""
    def __init__(self):
        self.file_path: str = ""
        self.file_type: str = "dxf"       # "dxf" or "pdf"
        self.geom_list: list[dict] = []    # filtered geometry dicts
        self.scale: float = 1.0            # multiplier applied to all coordinates
        self.base_x: float = 0.0           # base point (subtracted before scaling)
        self.base_y: float = 0.0
        self.user_layer: str = DEFAULT_USER_LAYER   # destination layer (colour derived from it)
        self.selected_layers: list[str] | None = None  # None = all
        self.rotation: float = 0.0         # degrees (applied to final group)
        self.insert_at_origin: bool = True
        # PDF-specific
        self.pdf_page: int = 0
        self.pdf_dpi: int = 150
        self.has_vectors: bool = True      # False → raster fallback


# ─────────────────────────────────────────────────────────────────────────────
# Preview view (unchanged from DXF-only version)
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
        self.setMouseTracking(True)
        self._mode = "pan"
        self._pan_start = None
        self._rb_start: QPointF | None = None
        self._rb_item: QGraphicsRectItem | None = None

    def set_mode(self, mode: str):
        self._mode = mode
        if mode in ("rubber_band", "pick_point"):
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            dlg = self.parent()
            if dlg and hasattr(dlg, "_cursor_h"):
                dlg._cursor_h.setVisible(False)
                dlg._cursor_v.setVisible(False)
                dlg._snap_marker_h.setVisible(False)
                dlg._snap_marker_v.setVisible(False)

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
        elif self._mode == "pick_point":
            scene_pos = self.mapToScene(event.pos())
            dlg = self.parent()
            if dlg and hasattr(dlg, "_cursor_h"):
                vr = self.mapToScene(self.viewport().rect()).boundingRect()
                dlg._cursor_h.setLine(vr.left(), scene_pos.y(),
                                       vr.right(), scene_pos.y())
                dlg._cursor_v.setLine(scene_pos.x(), vr.top(),
                                       scene_pos.x(), vr.bottom())
                dlg._cursor_h.setVisible(True)
                dlg._cursor_v.setVisible(True)

                result = dlg._snap_engine.find(
                    scene_pos, self.scene(), self.transform())
                if result is not None:
                    s = 6
                    sp = result.point
                    dlg._snap_marker_h.setLine(
                        sp.x() - s, sp.y(), sp.x() + s, sp.y())
                    dlg._snap_marker_v.setLine(
                        sp.x(), sp.y() - s, sp.x(), sp.y() + s)
                    c = SNAP_COLORS.get(result.snap_type, "#ffff00")
                    pen = QPen(QColor(c), 2)
                    pen.setCosmetic(True)
                    dlg._snap_marker_h.setPen(pen)
                    dlg._snap_marker_v.setPen(pen)
                    dlg._snap_marker_h.setVisible(True)
                    dlg._snap_marker_v.setVisible(True)
                else:
                    dlg._snap_marker_h.setVisible(False)
                    dlg._snap_marker_v.setVisible(False)

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
# Unified import dialog
# ─────────────────────────────────────────────────────────────────────────────

class UnderlayImportDialog(QDialog):
    """Unified preview-first import dialog for PDF and DXF underlays."""

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

    def __init__(self, parent=None, file_path: str = "",
                 user_layer_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Import Underlay — Preview")
        self.resize(1100, 700)

        self._user_layer_manager = user_layer_manager
        self._file_type: str = ""          # "dxf" or "pdf"
        self._all_geoms: list[dict] = []
        self._layers: list[str] = []
        self._selected_indices: set[int] | None = None
        self._base_x = 0.0
        self._base_y = 0.0
        self._pick_pts: list[QPointF] = []
        self._base_marker: QGraphicsEllipseItem | None = None
        self._pick_markers: list[QGraphicsItem] = []
        self._pick_mode: str | None = None
        self._has_vectors: bool = True
        self._pdf_page: int = 0
        self._pdf_page_count: int = 0

        self._preview_scene = QGraphicsScene()
        self._preview_view = _PreviewView(self._preview_scene, parent=self)
        self._preview_view.rubber_band_rect.connect(self._on_rubber_band)
        self._preview_view.point_picked.connect(self._on_any_point_picked)

        self._snap_engine = SnapEngine()
        self._create_overlay_items()
        self._build_ui()
        self._restore_saved_settings()

        if file_path:
            self._file_edit.setText(file_path)
            self._load_file()

    # ── Overlay items ─────────────────────────────────────────────────────────

    def _create_overlay_items(self):
        snap_pen = QPen(QColor("#ffff00"), 2)
        snap_pen.setCosmetic(True)
        self._snap_marker_h = QGraphicsLineItem()
        self._snap_marker_v = QGraphicsLineItem()
        for m in (self._snap_marker_h, self._snap_marker_v):
            m.setPen(snap_pen)
            m.setZValue(998)
            m.setVisible(False)
            self._preview_scene.addItem(m)

        cursor_pen = QPen(QColor("#ff8800"), 1, Qt.PenStyle.DashDotLine)
        cursor_pen.setCosmetic(True)
        self._cursor_h = QGraphicsLineItem()
        self._cursor_v = QGraphicsLineItem()
        for ch in (self._cursor_h, self._cursor_v):
            ch.setPen(cursor_pen)
            ch.setZValue(997)
            ch.setVisible(False)
            self._preview_scene.addItem(ch)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # File bar
        file_bar = QHBoxLayout()
        file_bar.addWidget(QLabel("File:"))
        self._file_edit = QLineEdit()
        file_bar.addWidget(self._file_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_file)
        file_bar.addWidget(browse_btn)
        reload_btn = QPushButton("↺ Reload")
        reload_btn.clicked.connect(self._load_file)
        file_bar.addWidget(reload_btn)
        outer.addLayout(file_bar)

        # PDF page thumbnail strip (hidden by default)
        self._thumb_list = QListWidget()
        self._thumb_list.setFlow(QListWidget.Flow.LeftToRight)
        self._thumb_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._thumb_list.setIconSize(QSize(80, 100))
        self._thumb_list.setFixedHeight(120)
        self._thumb_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._thumb_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._thumb_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self._thumb_list.currentRowChanged.connect(self._on_page_thumb_clicked)
        self._thumb_list.setVisible(False)
        outer.addWidget(self._thumb_list)

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

        self._info_lbl = QLabel("Load a PDF or DXF file to see a preview.")
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

        # Source layers
        layer_grp = QGroupBox("Source Layers")
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
        self._units_info_lbl = QLabel("")
        self._units_info_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        self._units_info_lbl.setVisible(False)
        scale_vlay.addWidget(self._units_info_lbl)
        pick2_btn = QPushButton("📐 Pick 2 pts on preview")
        pick2_btn.setToolTip(
            "Click two points on the preview, then enter the real distance between them."
        )
        pick2_btn.clicked.connect(self._start_pick2)
        scale_vlay.addWidget(pick2_btn)
        right_lay.addWidget(scale_grp)

        # Rotation
        rot_grp = QGroupBox("Rotation")
        rot_vlay = QVBoxLayout(rot_grp)
        rot_form = QFormLayout()
        self._rotation_spin = QDoubleSpinBox()
        self._rotation_spin.setRange(-360.0, 360.0)
        self._rotation_spin.setDecimals(1)
        self._rotation_spin.setSingleStep(1.0)
        self._rotation_spin.setValue(0.0)
        self._rotation_spin.setSuffix(" °")
        self._rotation_spin.valueChanged.connect(self._on_rotation_changed)
        rot_form.addRow("Angle:", self._rotation_spin)
        rot_vlay.addLayout(rot_form)
        rot_btn_lay = QHBoxLayout()
        btn_ccw = QPushButton("⟲ −90°")
        btn_ccw.clicked.connect(lambda: self._rotation_spin.setValue(
            self._rotation_spin.value() - 90.0))
        btn_cw = QPushButton("⟳ +90°")
        btn_cw.clicked.connect(lambda: self._rotation_spin.setValue(
            self._rotation_spin.value() + 90.0))
        btn_180 = QPushButton("180°")
        btn_180.clicked.connect(lambda: self._rotation_spin.setValue(
            self._rotation_spin.value() + 180.0))
        rot_btn_lay.addWidget(btn_ccw)
        rot_btn_lay.addWidget(btn_cw)
        rot_btn_lay.addWidget(btn_180)
        rot_vlay.addLayout(rot_btn_lay)
        right_lay.addWidget(rot_grp)

        # Base point
        base_grp = QGroupBox("Base / Insertion Point")
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

        # Destination layer (replaces old colour picker)
        dest_grp = QGroupBox("Destination Layer")
        dest_lay = QVBoxLayout(dest_grp)
        self._dest_layer_combo = QComboBox()
        if self._user_layer_manager is not None:
            for lyr in self._user_layer_manager.layers:
                self._dest_layer_combo.addItem(lyr.name)
        else:
            self._dest_layer_combo.addItem(DEFAULT_USER_LAYER)
        dest_lay.addWidget(self._dest_layer_combo)
        self._layer_colour_lbl = QLabel("")
        self._layer_colour_lbl.setStyleSheet("font-size: 11px; color: #aaa;")
        dest_lay.addWidget(self._layer_colour_lbl)
        self._dest_layer_combo.currentTextChanged.connect(self._on_dest_layer_changed)
        self._on_dest_layer_changed()
        right_lay.addWidget(dest_grp)

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
        self._origin_cb = QCheckBox("Insert at origin")
        self._origin_cb.setChecked(True)
        bot.addWidget(self._origin_cb)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import →")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        bot.addWidget(buttons)
        outer.addLayout(bot)

    # ── Destination layer ────────────────────────────────────────────────────

    def _on_dest_layer_changed(self):
        name = self._dest_layer_combo.currentText()
        if self._user_layer_manager:
            ldef = self._user_layer_manager.get(name)
            if ldef:
                self._layer_colour_lbl.setText(
                    f"Colour: {ldef.color}  •  Lineweight: {ldef.lineweight} mm")
                return
        self._layer_colour_lbl.setText("")

    # ── Persist settings between sessions ──────────────────────────────────

    _SETTINGS_KEY = "UnderlayImport"

    def _restore_saved_settings(self):
        """Restore last-used import settings from QSettings."""
        pfx = f"{self._SETTINGS_KEY}/"
        s = QSettings("GV", "FirePro3D")
        # Scale combo
        scale_idx = s.value(f"{pfx}scale_idx", 0, type=int)
        if 0 <= scale_idx < self._scale_combo.count():
            self._scale_combo.blockSignals(True)
            self._scale_combo.setCurrentIndex(scale_idx)
            self._scale_combo.blockSignals(False)
            self._on_scale_combo_changed(scale_idx)
        custom_scale = s.value(f"{pfx}custom_scale", 1.0, type=float)
        self._custom_scale_spin.blockSignals(True)
        self._custom_scale_spin.setValue(custom_scale)
        self._custom_scale_spin.blockSignals(False)
        # Rotation
        rotation = s.value(f"{pfx}rotation", 0.0, type=float)
        self._rotation_spin.blockSignals(True)
        self._rotation_spin.setValue(rotation)
        self._rotation_spin.blockSignals(False)
        # Destination layer
        layer = s.value(f"{pfx}dest_layer", "", type=str)
        if layer:
            idx = self._dest_layer_combo.findText(layer)
            if idx >= 0:
                self._dest_layer_combo.blockSignals(True)
                self._dest_layer_combo.setCurrentIndex(idx)
                self._dest_layer_combo.blockSignals(False)
                self._on_dest_layer_changed()
        # Insert at origin
        origin = s.value(f"{pfx}insert_at_origin", True, type=bool)
        self._origin_cb.setChecked(origin)

    def _save_settings(self):
        """Save current import settings to QSettings."""
        pfx = f"{self._SETTINGS_KEY}/"
        s = QSettings("GV", "FirePro3D")
        s.setValue(f"{pfx}scale_idx", self._scale_combo.currentIndex())
        s.setValue(f"{pfx}custom_scale", self._custom_scale_spin.value())
        s.setValue(f"{pfx}rotation", self._rotation_spin.value())
        s.setValue(f"{pfx}dest_layer", self._dest_layer_combo.currentText())
        s.setValue(f"{pfx}insert_at_origin", self._origin_cb.isChecked())

    # ── File loading ──────────────────────────────────────────────────────────

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Underlay File", "",
            "All Supported (*.dxf *.pdf);;DXF Files (*.dxf);;PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            self._file_edit.setText(path)
            self._load_file()

    def _load_file(self):
        path = self._file_edit.text().strip()
        if not path or not os.path.exists(path):
            return

        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            self._load_pdf(path)
        elif ext == ".dxf":
            self._load_dxf(path)
        else:
            QMessageBox.warning(self, "Unsupported file",
                                f"File type '{ext}' is not supported.\n"
                                "Please select a PDF or DXF file.")

    # ── DXF loading ──────────────────────────────────────────────────────────

    def _load_dxf(self, path: str):
        self._file_type = "dxf"
        self._thumb_list.setVisible(False)
        self._has_vectors = True

        if not _HAS_EZDXF:
            QMessageBox.warning(self, "Missing dependency",
                                "ezdxf is required for DXF import.\n"
                                "Install it with: pip install ezdxf")
            return

        self._info_lbl.setText("Loading DXF…")
        QApplication.processEvents()

        clean = _sanitize_dxf(path)
        try:
            doc = ezdxf.readfile(clean)
        except Exception as e:
            self._info_lbl.setText(f"Error: {e}")
            return
        finally:
            if clean != path and os.path.exists(clean):
                os.remove(clean)

        # Auto-detect DXF units ($INSUNITS)
        self._detect_dxf_units(doc)

        msp = doc.modelspace()
        layers_set: set[str] = {"0"}
        for layer in doc.layers:
            layers_set.add(layer.dxf.name)
        for entity in msp:
            layers_set.add(
                entity.dxf.get("layer", "0")
                if hasattr(entity.dxf, "get") else "0"
            )

        self._layers = sorted(layers_set)
        self._populate_layer_list()

        # Extract geometry synchronously
        from dxf_import_worker import DxfImportWorker
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
        self._selected_indices = None
        self._rebuild_preview()
        n = len(self._all_geoms)
        self._info_lbl.setText(f"{n} entities loaded from {os.path.basename(path)}")
        self._update_status()

    def _detect_dxf_units(self, doc):
        """Read $INSUNITS from DXF header and pre-fill scale if known."""
        try:
            code = doc.header.get("$INSUNITS", 0)
            if not isinstance(code, int):
                code = int(code)
        except Exception:
            code = 0

        if code in _DXF_INSUNITS and code != 0:
            name, factor = _DXF_INSUNITS[code]
            self._units_info_lbl.setText(f"Detected units: {name}")
            self._units_info_lbl.setVisible(True)
            # Auto-set custom scale
            custom_idx = len(self._SCALE_OPTIONS) - 1
            self._scale_combo.setCurrentIndex(custom_idx)
            self._custom_scale_spin.setValue(factor)
        else:
            self._units_info_lbl.setVisible(False)

    # ── PDF loading ──────────────────────────────────────────────────────────

    def _load_pdf(self, path: str):
        self._file_type = "pdf"

        if not _HAS_FITZ:
            QMessageBox.warning(self, "Missing dependency",
                                "PyMuPDF (fitz) is required for PDF vector import.\n"
                                "Install it with: pip install PyMuPDF")
            return

        self._info_lbl.setText("Loading PDF…")
        QApplication.processEvents()

        try:
            doc = fitz.open(path)
        except Exception as e:
            self._info_lbl.setText(f"Error opening PDF: {e}")
            return
        try:
            self._pdf_page_count = len(doc)
        finally:
            doc.close()

        # Generate thumbnails
        self._thumb_list.clear()
        if self._pdf_page_count > 1:
            from pdf_import_worker import generate_pdf_thumbnails
            thumbs = generate_pdf_thumbnails(path, width=80)
            for page_idx, pixmap in thumbs:
                item = QListWidgetItem(QIcon(pixmap), f"Page {page_idx + 1}")
                self._thumb_list.addItem(item)
            self._thumb_list.setVisible(True)
            if self._thumb_list.count() > 0:
                self._thumb_list.setCurrentRow(0)
        else:
            self._thumb_list.setVisible(False)

        self._pdf_page = 0
        self._load_pdf_page(path, 0)

    def _load_pdf_page(self, path: str, page: int):
        """Load vectors from a specific PDF page."""
        from pdf_import_worker import extract_pdf_vectors_sync

        self._pdf_page = page
        self._info_lbl.setText(f"Extracting vectors from page {page + 1}…")
        QApplication.processEvents()

        geoms, layers = extract_pdf_vectors_sync(path, page)

        if geoms:
            self._has_vectors = True
            self._all_geoms = geoms
            self._layers = layers
            self._populate_layer_list()
            self._selected_indices = None

            # Default base point for PDFs: bottom-left corner of bounding box.
            # PDF coords have origin at top-left (Y-down), so bottom-left is
            # (min_x, max_y).  This ensures "Insert at origin" places the
            # visual bottom-left at the scene origin.
            xs, ys = [], []
            for g in geoms:
                kind = g.get("kind")
                if kind == "line":
                    xs += [g["x1"], g["x2"]]
                    ys += [g["y1"], g["y2"]]
                elif kind == "path_points":
                    for pt in g.get("points", []):
                        xs.append(pt[0]); ys.append(pt[1])
                elif kind in ("circle", "arc"):
                    x0 = g.get("x", g.get("rx", 0))
                    y0 = g.get("y", g.get("ry", 0))
                    xs += [x0, x0 + g.get("w", g.get("rw", 0))]
                    ys += [y0, y0 + g.get("h", g.get("rh", 0))]
                elif kind == "text":
                    xs.append(g["x"]); ys.append(g["y"])
            if xs and ys:
                self._base_x_spin.blockSignals(True)
                self._base_y_spin.blockSignals(True)
                self._base_x_spin.setValue(min(xs))
                self._base_y_spin.setValue(max(ys))
                self._base_x_spin.blockSignals(False)
                self._base_y_spin.blockSignals(False)

            self._rebuild_preview()
            n = len(geoms)
            self._info_lbl.setText(
                f"{n} vector entities from page {page + 1} of "
                f"{os.path.basename(path)}"
            )
        else:
            # No vectors — show raster preview
            self._has_vectors = False
            self._all_geoms = []
            self._layers = []
            self._populate_layer_list()
            self._selected_indices = None
            self._show_raster_preview(path, page)
            self._info_lbl.setText(
                f"No vector geometry found on page {page + 1} — "
                f"will import as raster image."
            )

        self._units_info_lbl.setVisible(False)
        self._update_status()

    def _show_raster_preview(self, path: str, page: int):
        """Show a raster rendering of the PDF page as a fallback preview."""
        self._preview_scene.clear()
        self._base_marker = None
        self._pick_markers = []
        self._create_overlay_items()

        doc = None
        try:
            doc = fitz.open(path)
            pg = doc[page]
            # Render at 72 DPI for preview
            pix = pg.get_pixmap(alpha=False)
            from PyQt6.QtGui import QImage
            qimg = QImage(pix.samples, pix.width, pix.height,
                          pix.stride, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            item = QGraphicsPixmapItem(pixmap)
            item.setZValue(-200)
            self._preview_scene.addItem(item)
            self._preview_view.fitInView(
                self._preview_scene.itemsBoundingRect().adjusted(-10, -10, 10, 10),
                Qt.AspectRatioMode.KeepAspectRatio
            )
        except Exception:
            pass
        finally:
            if doc is not None:
                doc.close()

    def _on_page_thumb_clicked(self, row: int):
        if row < 0:
            return
        path = self._file_edit.text().strip()
        if path and os.path.exists(path):
            self._load_pdf_page(path, row)

    # ── Common helpers ───────────────────────────────────────────────────────

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
        self._preview_geom_group = None
        self._pick_markers = []
        self._create_overlay_items()

        pen_normal = QPen(QColor("#c0c0c0"), 0)
        pen_normal.setCosmetic(True)
        pen_sel = QPen(QColor("#4fa3e0"), 0)
        pen_sel.setCosmetic(True)
        pen_dim = QPen(QColor("#444444"), 0)
        pen_dim.setCosmetic(True)

        geom_items: list[QGraphicsItem] = []
        active_layers = self._active_layers()
        for idx, g in enumerate(self._all_geoms):
            layer_key = g.get("layer", "0")
            is_active_layer = (active_layers is None or layer_key in active_layers)
            is_selected = (self._selected_indices is None or idx in self._selected_indices)
            if is_active_layer and is_selected:
                pen = pen_sel
            elif is_active_layer:
                pen = pen_normal
            else:
                pen = pen_dim
            item = self._add_preview_geom(g, pen)
            if item is not None:
                geom_items.append(item)

        # Group geometry items and apply rotation around the base point
        rotation = self._rotation_spin.value() if hasattr(self, "_rotation_spin") else 0.0
        if geom_items and rotation != 0.0:
            group = self._preview_scene.createItemGroup(geom_items)
            bx = self._base_x_spin.value() if hasattr(self, "_base_x_spin") else 0.0
            by = self._base_y_spin.value() if hasattr(self, "_base_y_spin") else 0.0
            group.setTransformOriginPoint(bx, by)
            group.setRotation(rotation)
            self._preview_geom_group = group

        self._draw_base_marker()
        if self._all_geoms:
            self._preview_view.fitInView(
                self._preview_scene.itemsBoundingRect().adjusted(-10, -10, 10, 10),
                Qt.AspectRatioMode.KeepAspectRatio
            )

    def _add_preview_geom(self, g: dict, pen: QPen) -> QGraphicsItem | None:
        kind = g.get("kind")
        item: QGraphicsItem | None = None
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
                item = QGraphicsEllipseItem(
                    g["pos_cx"] + g["x"], g["pos_cy"] + g["y"], g["w"], g["h"]
                )
                item.setPen(pen)
                item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                self._preview_scene.addItem(item)
                return item
            pts = [QPointF(p[0], p[1]) for p in g["points"]]
            if len(pts) < 2:
                return None
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
            f.setPointSizeF(g.get("size", 6))
            item.setFont(f)
            item.setPos(g["x"], g["y"])
            self._preview_scene.addItem(item)
        return item

    def _draw_base_marker(self):
        if self._base_marker is not None:
            if self._base_marker.scene() is self._preview_scene:
                self._preview_scene.removeItem(self._base_marker)
            self._base_marker = None
        bx = self._base_x_spin.value()
        by = self._base_y_spin.value()
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
        self._base_marker = h

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
        self._pick_pts = []
        for m in self._pick_markers:
            if m.scene() is self._preview_scene:
                self._preview_scene.removeItem(m)
        self._pick_markers = []
        self._pick_mode = "scale_pt1"
        self._preview_view.set_mode("pick_point")
        self._status_lbl.setText("Click the FIRST point on the preview…")

    def _on_any_point_picked(self, raw_pt: QPointF):
        pt = self._snap_to_nearest(raw_pt)
        if self._pick_mode in ("scale_pt1", "scale_pt2"):
            self._on_pick2_pt(pt)
        elif self._pick_mode == "base":
            self._on_point_picked(pt)

    def _on_pick2_pt(self, pt: QPointF):
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
            self._status_lbl.setText("Click the SECOND point on the preview…")
            self._preview_view.set_mode("pick_point")
        elif len(self._pick_pts) == 2:
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
            self._pick_mode = None
            self._preview_view.set_mode("pan")

            if px_dist < 1.0:
                self._status_lbl.setText("Points too close — try again.")
                return

            real_dist, ok = QInputDialog.getDouble(
                self, "Real Distance",
                f"The two points are {px_dist:.1f} preview units apart.\n"
                "Enter the REAL distance between them:",
                decimals=3, min=0.001, max=1e9
            )
            if ok and real_dist > 0:
                factor = real_dist / px_dist
                custom_idx = len(self._SCALE_OPTIONS) - 1
                self._scale_combo.setCurrentIndex(custom_idx)
                self._custom_scale_spin.setValue(factor)
                self._status_lbl.setText(
                    f"Scale set: {px_dist:.1f} preview units = {real_dist} real → ×{factor:.5f}"
                )
            else:
                self._status_lbl.setText("Scale pick cancelled.")

    # ── Snap ──────────────────────────────────────────────────────────────────

    def _snap_to_nearest(self, pt: QPointF, tolerance: float = 0.0) -> QPointF:
        result = self._snap_engine.find(
            pt, self._preview_scene, self._preview_view.transform()
        )
        if result is not None:
            return result.point
        return pt

    # ── Base point ────────────────────────────────────────────────────────────

    def _start_pick_base(self):
        self._pick_mode = "base"
        self._preview_view.set_mode("pick_point")
        self._status_lbl.setText("Click the base / insertion point on the preview…")

    def _on_point_picked(self, pt: QPointF):
        self._base_x_spin.blockSignals(True)
        self._base_y_spin.blockSignals(True)
        self._base_x_spin.setValue(pt.x())
        self._base_y_spin.setValue(pt.y())
        self._base_x_spin.blockSignals(False)
        self._base_y_spin.blockSignals(False)
        self._draw_base_marker()
        self._pick_mode = None
        self._status_lbl.setText(
            f"Base point set to ({pt.x():.3f}, {pt.y():.3f})."
        )
        self._preview_view.set_mode("pan")

    def _on_rotation_changed(self):
        """Rebuild preview to reflect the new rotation angle."""
        self._rebuild_preview()

    def _on_base_changed(self):
        self._draw_base_marker()

    # ── Status ────────────────────────────────────────────────────────────────

    def _update_status(self):
        total = len(self._all_geoms)
        if total == 0 and not self._has_vectors:
            self._status_lbl.setText("Raster import — no vector entities.")
            return
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
        if not self._all_geoms and self._has_vectors:
            QMessageBox.warning(self, "Nothing to import",
                                "Load a file before importing.")
            return
        self.accept()

    def get_import_params(self) -> ImportParams:
        """Call after dialog.exec() == Accepted."""
        p = ImportParams()
        p.file_path = self._file_edit.text().strip()
        p.file_type = self._file_type
        p.scale = self._current_scale()
        p.base_x = self._base_x_spin.value()
        p.base_y = self._base_y_spin.value()
        p.rotation = self._rotation_spin.value()
        p.user_layer = self._dest_layer_combo.currentText()
        p.selected_layers = (
            list(self._active_layers())
            if self._active_layers() is not None
            else None
        )
        p.has_vectors = self._has_vectors
        p.pdf_page = self._pdf_page
        p.pdf_dpi = 150
        p.insert_at_origin = self._origin_cb.isChecked()

        active_layers = self._active_layers()
        geoms = []
        for idx, g in enumerate(self._all_geoms):
            if active_layers is not None and g.get("layer", "0") not in active_layers:
                continue
            if self._selected_indices is not None and idx not in self._selected_indices:
                continue
            geoms.append(g)
        p.geom_list = geoms
        self._save_settings()
        return p


# ── Backwards compat alias ───────────────────────────────────────────────────
DxfPreviewDialog = UnderlayImportDialog
