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
    QFileDialog, QLineEdit, QFormLayout,
    QDialogButtonBox, QProgressDialog, QProgressBar, QApplication,
    QCheckBox, QWidget, QSizePolicy, QScrollArea,
    QMessageBox, QInputDialog, QAbstractItemView,
)
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QPainterPath, QFont, QCursor, QPainter,
    QPixmap, QIcon,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF, QSizeF, QSize, QSettings, pyqtSignal

try:
    import ezdxf
    import logging as _logging
    _logging.getLogger("ezdxf").setLevel(_logging.ERROR)
    _HAS_EZDXF = True
except ImportError:
    _HAS_EZDXF = False

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    fitz = None
    _HAS_FITZ = False

from .dxf_import_worker import _sanitize_dxf
from .snap_engine import SnapEngine, OsnapResult, SNAP_COLORS, SNAP_MARKERS
from .scale_manager import ScaleManager
from .dimension_edit import DimensionEdit


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
        self.selected_layers: list[str] | None = None  # None = all
        self.rotation: float = 0.0         # degrees (applied to final group)
        self.insert_at_origin: bool = True
        # PDF-specific
        self.pdf_page: int = 0
        self.pdf_dpi: int = 150
        self.has_vectors: bool = True      # False → raster fallback
        self.import_mode: str = "auto"    # "auto" | "vectors" | "raster"
        self.layout: str = ""            # DWG layout name (empty = Model)


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
            dlg = getattr(self, "_dialog", None)
            if dlg and hasattr(dlg, "_cursor_h"):
                dlg._cursor_h.setVisible(False)
                dlg._cursor_v.setVisible(False)
                dlg._snap_result = None
                self.viewport().update()

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
                # Use snapped point if available
                dlg = getattr(self, "_dialog", None)
                snap = getattr(dlg, "_snap_result", None) if dlg else None
                pt = snap.point if snap else scene_pos
                self.point_picked.emit(pt)

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
            dlg = getattr(self, "_dialog", None)
            if dlg and hasattr(dlg, "_cursor_h"):
                result = dlg._snap_engine.find(
                    scene_pos, self.scene(), self.transform())
                dlg._snap_result = result

                # Crosshairs jump to snap point when available
                cp = result.point if result else scene_pos
                vr = self.mapToScene(self.viewport().rect()).boundingRect()
                dlg._cursor_h.setLine(vr.left(), cp.y(),
                                       vr.right(), cp.y())
                dlg._cursor_v.setLine(cp.x(), vr.top(),
                                       cp.x(), vr.bottom())
                dlg._cursor_h.setVisible(True)
                dlg._cursor_v.setVisible(True)
                self.viewport().update()

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

    def drawForeground(self, painter: QPainter, rect):
        """Draw snap glyph and source-item trace over the preview."""
        if not painter.isActive():
            return
        super().drawForeground(painter, rect)
        dlg = getattr(self, "_dialog", None)
        if dlg is None:
            return
        snap = getattr(dlg, "_snap_result", None)
        if snap is None:
            return

        # ── Source-item trace (scene coords) ──────────────────────────
        src = snap.source_item
        if src is not None:
            color = QColor(SNAP_COLORS.get(snap.snap_type, "#aaaaaa"))
            trace_pen = QPen(color, 1, Qt.PenStyle.DashLine)
            trace_pen.setCosmetic(True)
            painter.save()
            painter.setPen(trace_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if isinstance(src, QGraphicsLineItem):
                ln = src.line()
                painter.drawLine(QLineF(src.mapToScene(ln.p1()),
                                        src.mapToScene(ln.p2())))
            elif isinstance(src, QGraphicsEllipseItem):
                painter.drawEllipse(src.mapRectToScene(src.rect()))
            elif isinstance(src, QGraphicsPathItem):
                painter.drawPath(src.mapToScene(src.path()))
            painter.restore()

        # ── Snap glyph (viewport coords) ─────────────────────────────
        color = QColor(SNAP_COLORS.get(snap.snap_type, "#ffffff"))
        marker = SNAP_MARKERS.get(snap.snap_type, "square")
        vp = self.mapFromScene(snap.point)
        x, y = vp.x(), vp.y()
        s = 6

        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(color, 2)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if marker == "square":
            painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)
        elif marker == "circle":
            painter.drawEllipse(int(x) - s, int(y) - s, 2 * s, 2 * s)
        elif marker == "triangle":
            from PyQt6.QtGui import QPolygon
            from PyQt6.QtCore import QPoint
            poly = QPolygon([
                QPoint(int(x), int(y) - s),
                QPoint(int(x) + s, int(y) + s),
                QPoint(int(x) - s, int(y) + s),
            ])
            painter.drawPolygon(poly)
        elif marker == "x_cross":
            painter.drawLine(int(x) - s, int(y) - s, int(x) + s, int(y) + s)
            painter.drawLine(int(x) - s, int(y) + s, int(x) + s, int(y) - s)
        else:
            # Fallback: crosshair
            painter.drawLine(int(x) - s, int(y), int(x) + s, int(y))
            painter.drawLine(int(x), int(y) - s, int(x), int(y) + s)
        painter.restore()


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
                 scale_manager=None, default_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Import Underlay — Preview")
        self.resize(1100, 700)
        self.setWindowState(Qt.WindowState.WindowMaximized)

        self._sm = scale_manager
        self._default_dir = default_dir
        self._file_type: str = ""          # "dxf" or "pdf"
        self._all_geoms: list[dict] = []
        self._layers: list[str] = []
        self._selected_indices: set[int] | None = None
        self._base_x = 0.0
        self._base_y = 0.0
        self._pick_pts: list[QPointF] = []
        self._base_markers: list[QGraphicsItem] = []
        self._pick_markers: list[QGraphicsItem] = []
        self._pick_mode: str | None = None
        self._has_vectors: bool = True
        self._snap_result: OsnapResult | None = None
        self._pdf_page: int = 0
        self._pdf_page_count: int = 0
        self._load_cancelled = False

        self._preview_scene = QGraphicsScene()
        self._preview_view = _PreviewView(self._preview_scene, parent=self)
        self._preview_view._dialog = self  # direct ref — parent() changes after layout
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

        self._info_lbl = QLabel("Load a PDF, DXF, or DWG file to see a preview.")
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
        self._custom_scale_edit = QLineEdit()
        self._custom_scale_edit.setPlaceholderText("scale factor")
        self._custom_scale_edit.setText("1.0")
        self._custom_scale_edit.setVisible(False)
        scale_vlay.addWidget(self._custom_scale_edit)
        self._units_info_lbl = QLabel("")
        self._units_info_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        self._units_info_lbl.setVisible(False)
        scale_vlay.addWidget(self._units_info_lbl)
        self._calibration_lbl = QLabel("")
        self._calibration_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        self._calibration_lbl.setVisible(False)
        scale_vlay.addWidget(self._calibration_lbl)
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
        self._rotation_edit = QLineEdit()
        self._rotation_edit.setText("0.0°")
        self._rotation_edit.editingFinished.connect(self._on_rotation_changed)
        rot_form.addRow("Angle:", self._rotation_edit)
        rot_vlay.addLayout(rot_form)
        rot_btn_lay = QHBoxLayout()
        btn_ccw = QPushButton("⟲ −90°")
        btn_ccw.clicked.connect(lambda: self._set_rotation(self._get_rotation() - 90.0))
        btn_cw = QPushButton("⟳ +90°")
        btn_cw.clicked.connect(lambda: self._set_rotation(self._get_rotation() + 90.0))
        btn_180 = QPushButton("180°")
        btn_180.clicked.connect(lambda: self._set_rotation(self._get_rotation() + 180.0))
        rot_btn_lay.addWidget(btn_ccw)
        rot_btn_lay.addWidget(btn_cw)
        rot_btn_lay.addWidget(btn_180)
        rot_vlay.addLayout(rot_btn_lay)
        right_lay.addWidget(rot_grp)

        # Base point
        base_grp = QGroupBox("Base / Insertion Point")
        base_form = QFormLayout(base_grp)
        self._base_x_edit = DimensionEdit(self._sm, initial_mm=0.0)
        self._base_x_edit.valueChanged.connect(self._on_base_changed)
        self._base_y_edit = DimensionEdit(self._sm, initial_mm=0.0)
        self._base_y_edit.valueChanged.connect(self._on_base_changed)
        base_form.addRow("X:", self._base_x_edit)
        base_form.addRow("Y:", self._base_y_edit)
        pick_base_btn = QPushButton("📍 Pick on preview")
        pick_base_btn.clicked.connect(self._start_pick_base)
        base_form.addRow(pick_base_btn)
        right_lay.addWidget(base_grp)

        # PDF options (DPI + import mode)
        self._pdf_opts_grp = QGroupBox("PDF Options")
        pdf_form = QFormLayout(self._pdf_opts_grp)
        self._dpi_combo = QComboBox()
        self._dpi_combo.addItems(["72", "150", "300"])
        self._dpi_combo.setCurrentIndex(1)  # default 150
        self._dpi_combo.currentIndexChanged.connect(self._on_pdf_option_changed)
        pdf_form.addRow("DPI:", self._dpi_combo)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Auto", "Vectors", "Raster"])
        self._mode_combo.setCurrentIndex(0)  # default Auto
        self._mode_combo.currentIndexChanged.connect(self._on_pdf_option_changed)
        pdf_form.addRow("Mode:", self._mode_combo)
        self._pdf_opts_grp.setVisible(False)  # shown only for PDFs
        right_lay.addWidget(self._pdf_opts_grp)

        right_lay.addStretch()
        right_scroll.setWidget(right_w)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        outer.addWidget(splitter, 1)

        # Progress bar (hidden by default)
        self._progress_row = QWidget()
        prog_lay = QHBoxLayout(self._progress_row)
        prog_lay.setContentsMargins(0, 0, 0, 0)
        prog_lay.setSpacing(6)
        self._progress_lbl = QLabel("")
        prog_lay.addWidget(self._progress_lbl)
        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(True)
        prog_lay.addWidget(self._progress_bar, 1)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel_load)
        prog_lay.addWidget(self._cancel_btn)
        self._progress_row.setVisible(False)
        outer.addWidget(self._progress_row)

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

    # ── Loading state ─────────────────────────────────────────────────────

    def _set_loading(self, message: str):
        """Disable controls and show a loading message with indeterminate progress."""
        self._load_cancelled = False
        self._progress_lbl.setText(message)
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._progress_row.setVisible(True)
        self._cancel_btn.setEnabled(False)  # only enabled during extraction
        self._preview_view.setEnabled(False)
        # Disable the right-side controls panel
        splitter = self.findChild(QSplitter)
        if splitter and splitter.count() > 1:
            splitter.widget(1).setEnabled(False)
        # Disable bottom bar buttons
        btns = self.findChild(QDialogButtonBox)
        if btns:
            btns.setEnabled(False)
        QApplication.processEvents()

    def _set_extracting(self, total: int):
        """Switch progress bar to determinate mode for entity extraction."""
        self._load_cancelled = False
        self._progress_bar.setRange(0, total)
        self._progress_bar.setValue(0)
        self._cancel_btn.setEnabled(True)

    def _update_progress(self, current: int, total: int, message: str = ""):
        """Update progress bar value and optional message."""
        self._progress_bar.setValue(current)
        if message:
            self._progress_lbl.setText(message)
        QApplication.processEvents()

    def _clear_loading(self):
        """Re-enable controls and hide progress bar."""
        self._progress_row.setVisible(False)
        self._preview_view.setEnabled(True)
        splitter = self.findChild(QSplitter)
        if splitter and splitter.count() > 1:
            splitter.widget(1).setEnabled(True)
        btns = self.findChild(QDialogButtonBox)
        if btns:
            btns.setEnabled(True)

    def _on_cancel_load(self):
        """Set the cancel flag so the extraction loop stops."""
        self._load_cancelled = True

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
        self._custom_scale_edit.blockSignals(True)
        self._custom_scale_edit.setText(f"{custom_scale:.5g}")
        self._custom_scale_edit.blockSignals(False)
        # Rotation
        rotation = s.value(f"{pfx}rotation", 0.0, type=float) % 360.0
        self._rotation_edit.blockSignals(True)
        self._rotation_edit.setText(f"{rotation:.1f}°")
        self._rotation_edit.blockSignals(False)
        # Insert at origin
        origin = s.value(f"{pfx}insert_at_origin", True, type=bool)
        self._origin_cb.setChecked(origin)

    def _save_settings(self):
        """Save current import settings to QSettings."""
        pfx = f"{self._SETTINGS_KEY}/"
        s = QSettings("GV", "FirePro3D")
        s.setValue(f"{pfx}scale_idx", self._scale_combo.currentIndex())
        s.setValue(f"{pfx}custom_scale", self._get_custom_scale())
        s.setValue(f"{pfx}rotation", self._get_rotation())
        s.setValue(f"{pfx}insert_at_origin", self._origin_cb.isChecked())

    # ── File loading ──────────────────────────────────────────────────────────

    def _browse_file(self):
        start_dir = self._default_dir or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Underlay File", start_dir,
            "All Supported (*.dxf *.dwg *.pdf);;DWG Files (*.dwg);;DXF Files (*.dxf);;PDF Files (*.pdf);;All Files (*)"
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
        elif ext == ".dwg":
            self._load_dwg(path)
        else:
            QMessageBox.warning(self, "Unsupported file",
                                f"File type '{ext}' is not supported.\n"
                                "Please select a PDF, DXF, or DWG file.")

    # ── DXF loading ──────────────────────────────────────────────────────────

    @staticmethod
    def _entity_in_viewport(ent, bounds) -> bool:
        """Check if a DXF entity falls within viewport bounds.

        Checks ALL coordinates (not sampled) for accurate pre-filtering.
        INSERT/HATCH/DIMENSION always pass since their explosion produces
        geometry at unpredictable locations.
        """
        etype = ent.dxftype()

        # Types that explode — can't pre-filter
        if etype in ("INSERT", "HATCH", "DIMENSION"):
            return True

        try:
            if etype == "LINE":
                pts = [(ent.dxf.start[0], -ent.dxf.start[1]),
                       (ent.dxf.end[0], -ent.dxf.end[1])]
            elif etype in ("CIRCLE", "ARC"):
                c = ent.dxf.center
                pts = [(c.x, -c.y)]
            elif etype == "ELLIPSE":
                c = ent.dxf.center
                pts = [(c.x, -c.y)]
            elif etype in ("LWPOLYLINE", "POLYLINE"):
                pts = [(p[0], -p[1]) for p in ent.get_points()]
            elif etype == "SPLINE":
                pts = [(cp[0], -cp[1]) for cp in ent.control_points]
            elif etype in ("TEXT", "MTEXT"):
                ins = ent.dxf.insert
                pts = [(ins[0], -ins[1])]
            else:
                return True  # unknown — include
        except (AttributeError, IndexError, TypeError):
            return True

        if not pts:
            return True

        for bx0, by0, bx1, by1 in bounds:
            if by0 > by1:
                by0, by1 = by1, by0
            for px, py in pts:
                if bx0 <= px <= bx1 and by0 <= py <= by1:
                    return True
        return False

    def _load_dxf(self, path: str, _skip_rebuild: bool = False,
                  _vp_bounds=None, _doc=None):
        self._file_type = "dxf"
        self._pdf_opts_grp.setVisible(False)
        self._thumb_list.setVisible(False)
        self._has_vectors = True

        if not _HAS_EZDXF:
            QMessageBox.warning(self, "Missing dependency",
                                "ezdxf is required for DXF import.\n"
                                "Install it with: pip install ezdxf")
            return

        if _doc is not None:
            doc = _doc
        else:
            self._set_loading("Reading DXF file\u2026")

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
        from .dxf_import_worker import DxfImportWorker, _build_layer_colors
        geoms = []
        all_ents = list(msp)
        self._set_extracting(len(all_ents))
        self._progress_lbl.setText("Extracting entities\u2026")
        worker_ref = DxfImportWorker.__new__(DxfImportWorker)
        worker_ref._cancelled = False
        worker_ref._layer_colors = _build_layer_colors(doc)
        for i, ent in enumerate(all_ents):
            if self._load_cancelled:
                break
            if i % 200 == 0:
                self._update_progress(i, len(all_ents))
            if _vp_bounds and not self._entity_in_viewport(ent, _vp_bounds):
                continue
            try:
                g = worker_ref._extract_geometry(ent)
                if g is not None:
                    if isinstance(g, list):
                        geoms.extend(g)
                    else:
                        geoms.append(g)
            except Exception:
                pass

        self._all_geoms = geoms
        self._selected_indices = None
        if not _skip_rebuild:
            self._set_loading("Building preview\u2026")
            self._rebuild_preview()
            self._clear_loading()
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
            self._custom_scale_edit.setText(f"{factor:.5g}")
        else:
            self._units_info_lbl.setVisible(False)

    # ── DWG loading ──────────────────────────────────────────────────────────

    def _load_dwg(self, path: str):
        """Load a DWG file by converting to DXF via ODA File Converter."""
        from .dwg_converter import (
            find_oda_converter, convert_dwg_to_dxf,
            list_dwg_layouts, cleanup_converted_dxf, ODA_DOWNLOAD_URL,
        )

        oda_path = find_oda_converter()
        if oda_path is None:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("ODA File Converter Required")
            msg.setText(
                "DWG import requires ODA File Converter (free download).\n\n"
                f"Download from:\n{ODA_DOWNLOAD_URL}")
            msg.addButton(QMessageBox.StandardButton.Cancel)
            locate_btn = msg.addButton("Locate ODA\u2026",
                                       QMessageBox.ButtonRole.ActionRole)
            msg.exec()
            if msg.clickedButton() == locate_btn:
                oda_path = self._browse_for_oda()
            if oda_path is None:
                return

        import time as _time
        _t0 = _time.perf_counter()

        # ── Stage 1: ODA conversion ──────────────────────────────────────
        self._set_loading("Converting DWG \u2192 DXF\u2026")
        dxf_path = convert_dwg_to_dxf(oda_path, path,
                                       project_dir=self._default_dir or None)
        while dxf_path is None:
            self._clear_loading()
            from .dwg_converter import get_last_error
            diag = get_last_error()
            detail = f"\n\nDiagnostics:\n{diag}" if diag else ""
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Conversion Failed")
            msg.setText(
                f"ODA File Converter could not convert this DWG file.\n"
                f"ODA path: {oda_path}{detail}")
            msg.addButton(QMessageBox.StandardButton.Cancel)
            change_btn = msg.addButton("Change ODA Path\u2026",
                                       QMessageBox.ButtonRole.ActionRole)
            msg.exec()
            if msg.clickedButton() != change_btn:
                return
            new_path = self._browse_for_oda()
            if new_path is None:
                return
            oda_path = new_path
            self._set_loading("Converting DWG \u2192 DXF\u2026")
            dxf_path = convert_dwg_to_dxf(oda_path, path,
                                           project_dir=self._default_dir or None)

        _t1 = _time.perf_counter()
        print(f"[DWG perf] ODA conversion: {_t1-_t0:.2f}s")

        # ── Stage 2: Read DXF once ───────────────────────────────────────
        self._set_loading("Reading DXF\u2026")
        from .dwg_converter import (
            read_dxf, list_dwg_layouts as _list_layouts,
            get_viewport_bounds, filter_geoms_by_bounds,
            extract_layout_entities,
        )
        doc = read_dxf(dxf_path)
        if doc is None:
            self._clear_loading()
            QMessageBox.warning(self, "Read Error",
                                f"Could not read converted DXF:\n{dxf_path}")
            return
        _t2 = _time.perf_counter()
        print(f"[DWG perf] DXF read: {_t2-_t1:.2f}s")

        # ── Stage 3: Layout listing + selection ──────────────────────────
        self._clear_loading()
        layouts = _list_layouts(doc=doc)
        _t3 = _time.perf_counter()
        print(f"[DWG perf] Layout listing: {_t3-_t2:.2f}s ({len(layouts)} layouts)")

        selected_layout = "Model"
        if len(layouts) > 1:
            from PyQt6.QtWidgets import QInputDialog
            choice, ok = QInputDialog.getItem(
                self, "Select Layout",
                "Select which layout to import:\n\n"
                "\u2022 'Model' imports all model-space geometry.\n"
                "\u2022 Paper layouts import only the geometry\n"
                "  visible through that layout's viewports.",
                layouts, 0, False)
            if not ok:
                cleanup_converted_dxf(dxf_path)
                return
            selected_layout = choice

        _t3 = _time.perf_counter()  # reset after user dialog
        self._dwg_layout = selected_layout
        self._dwg_source_path = path

        # ── Stage 4: Viewport bounds ─────────────────────────────────────
        vp_bounds = None
        if selected_layout != "Model":
            vp_bounds = get_viewport_bounds(
                layout_name=selected_layout, doc=doc)
        _t4 = _time.perf_counter()
        print(f"[DWG perf] Viewport bounds: {_t4-_t3:.2f}s"
              f" (bounds={'yes' if vp_bounds else 'none'})")

        # ── Stage 5: Geometry extraction ─────────────────────────────────
        self._set_loading("Extracting geometry\u2026")
        self._load_dxf(dxf_path, _skip_rebuild=True,
                        _vp_bounds=vp_bounds, _doc=doc)
        _t5 = _time.perf_counter()
        print(f"[DWG perf] Extraction: {_t5-_t4:.2f}s"
              f" ({len(self._all_geoms)} geoms)")

        # ── Stage 6: Post-extraction viewport filter ─────────────────────
        if selected_layout != "Model" and vp_bounds:
            before = len(self._all_geoms)
            self._all_geoms = filter_geoms_by_bounds(
                self._all_geoms, vp_bounds)
            self._selected_indices = None
            _t6 = _time.perf_counter()
            print(f"[DWG perf] Viewport filter: {_t6-_t5:.2f}s"
                  f" ({before} -> {len(self._all_geoms)} geoms)")
        else:
            _t6 = _t5

        # ── Stage 7: Paper layout entities ───────────────────────────────
        if selected_layout != "Model":
            layout_geoms = extract_layout_entities(
                layout_name=selected_layout, doc=doc)
            if layout_geoms:
                self._all_geoms.extend(layout_geoms)
            _t7 = _time.perf_counter()
            print(f"[DWG perf] Layout entities: {_t7-_t6:.2f}s"
                  f" (+{len(layout_geoms) if layout_geoms else 0})")
        else:
            _t7 = _t6

        self._clear_loading()

        # ── Stage 8: Entity type dialog ──────────────────────────────────
        excluded_kinds = self._show_geom_type_dialog()
        if excluded_kinds is None:
            cleanup_converted_dxf(dxf_path)
            return
        if excluded_kinds:
            self._all_geoms = [g for g in self._all_geoms
                               if g.get("kind") not in excluded_kinds]
        _t8 = _time.perf_counter()

        # ── Stage 9: Preview rebuild ─────────────────────────────────────
        self._set_loading(f"Building preview ({len(self._all_geoms)} entities)\u2026")
        self._rebuild_preview()
        self._clear_loading()
        _t9 = _time.perf_counter()
        print(f"[DWG perf] Preview rebuild: {_t9-_t8:.2f}s"
              f" ({len(self._all_geoms)} items)")
        print(f"[DWG perf] TOTAL (excl. dialogs): {_t9-_t0:.2f}s")

        # Don't clean up UNDERLAY_REF DXFs (they persist for reuse)
        cleanup_converted_dxf(dxf_path)

        self._file_type = "dwg"
        n = len(self._all_geoms)
        layout_label = f" (layout: {selected_layout})" if selected_layout != "Model" else ""
        self._info_lbl.setText(
            f"{n:,} entities from {os.path.basename(path)}{layout_label}")

    def _browse_for_oda(self) -> str | None:
        """Let the user manually locate ODAFileConverter.exe and save to QSettings."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate ODA File Converter",
            os.environ.get("ProgramFiles", ""),
            "Executables (*.exe);;All Files (*)")
        if path and os.path.isfile(path):
            from PyQt6.QtCore import QSettings
            s = QSettings("GV", "FirePro3D")
            s.setValue("dwg/oda_converter_path", path)
            return path
        return None

    def _show_geom_type_dialog(self) -> set[str] | None:
        """Show geometry type counts from ``_all_geoms`` and let user deselect.

        Called AFTER extraction and viewport filtering so counts reflect
        what will actually be imported.

        Returns a set of geometry ``kind`` values to EXCLUDE, an empty
        set to keep everything, or ``None`` if cancelled.
        """
        if not self._all_geoms:
            return set()

        counts: dict[str, int] = {}
        for g in self._all_geoms:
            kind = g.get("kind", "unknown")
            counts[kind] = counts.get(kind, 0) + 1

        total = sum(counts.values())

        layout_note = getattr(self, "_dwg_layout", "Model")
        dlg = QDialog(self)
        dlg.setWindowTitle("Import Entity Types")
        dlg.resize(400, 320)
        lay = QVBoxLayout(dlg)

        scope = (f"'{layout_note}' viewport" if layout_note != "Model"
                 else "Model space")
        lay.addWidget(QLabel(
            f"{total:,} geometry items in {scope}.\n"
            "Deselect types you don't need."))

        _KIND_LABELS = {
            "line": "Lines",
            "path_points": "Polylines / Splines",
            "circle": "Circles",
            "arc": "Arcs",
            "ellipse_full": "Ellipses",
            "text": "Text",
        }
        _DISPLAY_ORDER = ["line", "path_points", "circle", "arc",
                          "ellipse_full", "text"]

        from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
        tree = QTreeWidget()
        tree.setHeaderLabels(["Type", "Count"])
        tree.setColumnWidth(0, 200)
        tree.setRootIsDecorated(False)

        items_map: dict[str, QTreeWidgetItem] = {}
        remaining = dict(counts)
        for kind in _DISPLAY_ORDER:
            if kind not in remaining:
                continue
            c = remaining.pop(kind)
            label = _KIND_LABELS.get(kind, kind)
            item = QTreeWidgetItem([label, f"{c:,}"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            tree.addTopLevelItem(item)
            items_map[kind] = item
        for kind in sorted(remaining.keys()):
            c = remaining[kind]
            item = QTreeWidgetItem([kind, f"{c:,}"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            tree.addTopLevelItem(item)
            items_map[kind] = item

        lay.addWidget(tree, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Import Selected")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        excluded = set()
        for kind, item in items_map.items():
            if item.checkState(0) != Qt.CheckState.Checked:
                excluded.add(kind)
        return excluded

    def _load_dxf_with_layout(self, dxf_path: str, layout_name: str):
        """Load entities from a specific layout of a DXF file.

        For ``"Model"`` layout, delegates to the standard ``_load_dxf()``
        pipeline.  For paper-space layouts, reads entities from the
        named layout instead of modelspace.
        """
        if layout_name == "Model":
            self._load_dxf(dxf_path)
            return

        # Paper-space layout — same logic as _load_dxf but from named layout
        self._file_type = "dwg"
        self._pdf_opts_grp.setVisible(False)
        self._thumb_list.setVisible(False)
        self._has_vectors = True

        if not _HAS_EZDXF:
            QMessageBox.warning(self, "Missing dependency",
                                "ezdxf is required for DWG import.\n"
                                "Install it with: pip install ezdxf")
            return

        self._info_lbl.setText(f"Loading layout '{layout_name}'\u2026")
        QApplication.processEvents()

        clean = _sanitize_dxf(dxf_path)
        try:
            doc = ezdxf.readfile(clean)
        except Exception as e:
            self._info_lbl.setText(f"Error: {e}")
            return
        finally:
            if clean != dxf_path and os.path.exists(clean):
                os.remove(clean)

        try:
            layout = doc.layouts.get(layout_name)
        except KeyError:
            self._info_lbl.setText(f"Layout '{layout_name}' not found")
            return

        layers_set: set[str] = {"0"}
        for layer in doc.layers:
            layers_set.add(layer.dxf.name)
        for entity in layout:
            layers_set.add(
                entity.dxf.get("layer", "0")
                if hasattr(entity.dxf, "get") else "0"
            )

        self._layers = sorted(layers_set)
        self._populate_layer_list()

        # Extract geometry synchronously
        from .dxf_import_worker import DxfImportWorker, _build_layer_colors
        geoms = []
        all_ents = list(layout)
        prog = QProgressDialog("Loading preview\u2026", "Cancel", 0, len(all_ents), self)
        prog.setMinimumDuration(500)
        worker_ref = DxfImportWorker.__new__(DxfImportWorker)
        worker_ref._cancelled = False
        worker_ref._layer_colors = _build_layer_colors(doc)
        for i, ent in enumerate(all_ents):
            if prog.wasCanceled():
                break
            if i % 200 == 0:
                prog.setValue(i)
                QApplication.processEvents()
            try:
                g = worker_ref._extract_geometry(ent)
                if g is not None:
                    if isinstance(g, list):
                        geoms.extend(g)
                    else:
                        geoms.append(g)
            except Exception:
                pass
        prog.close()

        self._all_geoms = geoms
        self._selected_indices = None
        self._rebuild_preview()
        self._update_status()

    # ── PDF loading ──────────────────────────────────────────────────────────

    def _load_pdf(self, path: str):
        self._file_type = "pdf"
        self._pdf_opts_grp.setVisible(True)

        if not _HAS_FITZ:
            QMessageBox.warning(self, "Missing dependency",
                                "PyMuPDF (fitz) is required for PDF vector import.\n"
                                "Install it with: pip install PyMuPDF")
            return

        self._set_loading("Reading PDF file…")

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
            from .pdf_import_worker import generate_pdf_thumbnails
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

    def _load_pdf_page(self, path: str, page: int, dpi: int | None = None):
        """Load vectors from a specific PDF page."""
        if dpi is None:
            dpi = int(self._dpi_combo.currentText())

        self._pdf_page = page
        mode = self._mode_combo.currentText().lower()  # "auto", "vectors", "raster"

        if mode == "raster":
            self._has_vectors = False
            self._all_geoms = []
            self._layers = []
            self._populate_layer_list()
            self._selected_indices = None
            self._show_raster_preview(path, page, dpi)
            self._clear_loading()
            self._info_lbl.setText(
                f"Raster import of page {page + 1} at {dpi} DPI.")
        else:
            from .pdf_import_worker import extract_pdf_vectors_sync
            self._set_loading(f"Extracting vectors from page {page + 1}…")
            geoms, layers = extract_pdf_vectors_sync(path, page)

            if geoms:
                self._has_vectors = True
                self._all_geoms = geoms
                self._layers = layers
                self._populate_layer_list()
                self._selected_indices = None

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
                    self._base_x_edit.blockSignals(True)
                    self._base_y_edit.blockSignals(True)
                    self._base_x_edit.set_value_mm(min(xs))
                    self._base_y_edit.set_value_mm(max(ys))
                    self._base_x_edit.blockSignals(False)
                    self._base_y_edit.blockSignals(False)

                self._set_loading("Building preview…")
                self._rebuild_preview()
                self._clear_loading()
                n = len(geoms)
                self._info_lbl.setText(
                    f"{n} vector entities from page {page + 1} of "
                    f"{os.path.basename(path)}")
            elif mode == "vectors":
                self._has_vectors = False
                self._all_geoms = []
                self._layers = []
                self._populate_layer_list()
                self._selected_indices = None
                self._preview_scene.clear()
                self._base_markers = []
                self._pick_markers = []
                self._create_overlay_items()
                self._clear_loading()
                self._info_lbl.setText(
                    f"No vector geometry found on page {page + 1}.")
                self._status_lbl.setText(
                    "No vectors found — switch to Auto or Raster.")
            else:
                self._has_vectors = False
                self._all_geoms = []
                self._layers = []
                self._populate_layer_list()
                self._selected_indices = None
                self._show_raster_preview(path, page, dpi)
                self._clear_loading()
                self._info_lbl.setText(
                    f"No vector geometry found on page {page + 1} — "
                    f"will import as raster image.")

        self._units_info_lbl.setVisible(False)
        self._update_status()

    def _show_raster_preview(self, path: str, page: int, dpi: int = 150):
        """Show a raster rendering of the PDF page as a fallback preview."""
        self._preview_scene.clear()
        self._base_marker = None
        self._pick_markers = []
        self._create_overlay_items()

        doc = None
        try:
            doc = fitz.open(path)
            pg = doc[page]
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = pg.get_pixmap(matrix=mat, alpha=False)
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

        # Batch all geometry into one QPainterPath per pen style
        # instead of one QGraphicsItem per geometry (293K → ~6 items).
        # Text needs separate paths (filled, no outline) from geometry
        # (outlined, no fill).
        pens = (pen_sel, pen_normal, pen_dim)
        geom_paths = {id(p): QPainterPath() for p in pens}
        text_paths = {id(p): QPainterPath() for p in pens}
        pen_map = {id(p): p for p in pens}

        active_layers = self._active_layers()
        for idx, g in enumerate(self._all_geoms):
            layer_key = g.get("layer", "0")
            is_active = active_layers is None or layer_key in active_layers
            is_sel = self._selected_indices is None or idx in self._selected_indices
            if is_active and is_sel:
                pen = pen_sel
            elif is_active:
                pen = pen_normal
            else:
                pen = pen_dim
            pid = id(pen)
            if g.get("kind") == "text":
                self._append_geom_to_path(text_paths[pid], g)
            else:
                self._append_geom_to_path(geom_paths[pid], g)

        geom_items: list[QGraphicsItem] = []
        for pid in [id(p) for p in pens]:
            pen = pen_map[pid]
            # Geometry: stroked outline, no fill
            gp = geom_paths[pid]
            if not gp.isEmpty():
                item = QGraphicsPathItem(gp)
                item.setPen(pen)
                item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                self._preview_scene.addItem(item)
                geom_items.append(item)
            # Text: filled, no outline
            tp = text_paths[pid]
            if not tp.isEmpty():
                item = QGraphicsPathItem(tp)
                item.setPen(QPen(Qt.PenStyle.NoPen))
                item.setBrush(QBrush(pen.color()))
                self._preview_scene.addItem(item)
                geom_items.append(item)

        # Group geometry items and apply rotation around the base point
        rotation = self._get_rotation()
        if geom_items:
            group = self._preview_scene.createItemGroup(geom_items)
            group.setData(0, "DXF Underlay")  # snap engine descends into tagged groups
            bx = self._base_x_edit.value_mm() if hasattr(self, "_base_x_edit") else 0.0
            by = self._base_y_edit.value_mm() if hasattr(self, "_base_y_edit") else 0.0
            group.setTransformOriginPoint(bx, by)
            group.setRotation(rotation)
            self._preview_geom_group = group

        self._draw_base_marker()
        if self._all_geoms:
            self._preview_view.fitInView(
                self._preview_scene.itemsBoundingRect().adjusted(-10, -10, 10, 10),
                Qt.AspectRatioMode.KeepAspectRatio
            )

    @staticmethod
    def _append_geom_to_path(path: QPainterPath, g: dict):
        """Append a single geometry dict to a batched QPainterPath."""
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
                path.addText(g["x"], g["y"], f, txt)

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
            txt = g.get("text", "")
            if txt:
                f = QFont("Arial")
                f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                f.setPointSizeF(max(0.5, g.get("size", 6)))
                path = QPainterPath()
                path.addText(0, 0, f, txt)
                item = QGraphicsPathItem(path)
                item.setBrush(QBrush(pen.color()))
                item.setPen(QPen(Qt.PenStyle.NoPen))
                item.setPos(g["x"], g["y"])
                self._preview_scene.addItem(item)
        return item

    def _draw_base_marker(self):
        # Remove previous base marker items (guard against deleted C++ objects)
        for m in self._base_markers:
            try:
                if m.scene() is self._preview_scene:
                    self._preview_scene.removeItem(m)
            except RuntimeError:
                pass  # already deleted by scene.clear()
        self._base_markers.clear()

        bx = self._base_x_edit.value_mm()
        by = self._base_y_edit.value_mm()
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
        self._base_markers = [h, v]

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
        self._custom_scale_edit.setVisible(val is None)
        self._calibration_lbl.setVisible(val is None and bool(self._calibration_lbl.text()))

    def _get_custom_scale(self) -> float:
        try:
            return float(self._custom_scale_edit.text())
        except (ValueError, AttributeError):
            return 1.0

    def _current_scale(self) -> float:
        idx = self._scale_combo.currentIndex()
        _, val = self._SCALE_OPTIONS[idx]
        if val is None:
            return self._get_custom_scale()
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
        pen = QPen(QColor("#00cc44"), 2)
        pen.setCosmetic(True)
        s = 8
        # Diamond marker for scale pick points
        path = QPainterPath()
        path.moveTo(pt.x(), pt.y() - s)
        path.lineTo(pt.x() + s, pt.y())
        path.lineTo(pt.x(), pt.y() + s)
        path.lineTo(pt.x() - s, pt.y())
        path.closeSubpath()
        diamond = QGraphicsPathItem(path)
        diamond.setPen(pen)
        diamond.setZValue(600)
        self._preview_scene.addItem(diamond)
        self._pick_markers.append(diamond)
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
            line.setPen(QPen(QColor("#00cc44"), 1, Qt.PenStyle.DashLine))
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

            # Build a unit hint for the prompt
            if self._sm:
                hint = self._sm.format_length(1000.0)  # e.g. "3' 3 3/8\"" or "1000.000 mm"
                unit_hint = f" (e.g. {hint})"
            else:
                unit_hint = ""

            text, ok = QInputDialog.getText(
                self, "Real Distance",
                f"The two points are {px_dist:.1f} preview units apart.\n"
                f"Enter the REAL distance between them{unit_hint}:"
            )
            if ok and text.strip():
                fallback = self._sm.bare_number_unit() if self._sm else "mm"
                parsed_mm = ScaleManager.parse_dimension(text.strip(), fallback)
                if parsed_mm is not None and parsed_mm > 0:
                    factor = parsed_mm / px_dist
                    custom_idx = len(self._SCALE_OPTIONS) - 1
                    self._scale_combo.setCurrentIndex(custom_idx)
                    self._custom_scale_edit.setText(f"{factor:.5g}")
                    display = self._sm.format_length(parsed_mm) if self._sm else f"{parsed_mm:.1f} mm"
                    self._calibration_lbl.setText(
                        f"{px_dist:.1f} px = {display}")
                    self._calibration_lbl.setVisible(True)
                    self._status_lbl.setText(f"Scale calibrated: {display}")
                else:
                    self._status_lbl.setText("Could not parse distance — try again.")
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
        self._base_x_edit.blockSignals(True)
        self._base_y_edit.blockSignals(True)
        self._base_x_edit.set_value_mm(pt.x())
        self._base_y_edit.set_value_mm(pt.y())
        self._base_x_edit.blockSignals(False)
        self._base_y_edit.blockSignals(False)
        self._draw_base_marker()
        self._pick_mode = None
        self._status_lbl.setText(
            f"Base point set to ({pt.x():.3f}, {pt.y():.3f})."
        )
        self._preview_view.set_mode("pan")

    def _on_pdf_option_changed(self):
        """Re-render PDF preview when DPI or import mode changes."""
        if self._file_type != "pdf":
            return
        path = self._file_edit.text().strip()
        if not path:
            return
        self._load_pdf_page(path, self._pdf_page)

    def _on_rotation_changed(self):
        """Rebuild preview to reflect the new rotation angle."""
        self._rebuild_preview()

    def _get_rotation(self) -> float:
        text = self._rotation_edit.text().strip().rstrip("°").strip()
        try:
            return float(text) % 360.0
        except (ValueError, AttributeError):
            return 0.0

    def _set_rotation(self, deg: float):
        deg = deg % 360.0
        self._rotation_edit.setText(f"{deg:.1f}°")
        self._on_rotation_changed()

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
        p.base_x = self._base_x_edit.value_mm()
        p.base_y = self._base_y_edit.value_mm()
        p.rotation = self._get_rotation()
        p.selected_layers = (
            list(self._active_layers())
            if self._active_layers() is not None
            else None
        )
        p.has_vectors = self._has_vectors
        p.pdf_page = self._pdf_page
        p.pdf_dpi = int(self._dpi_combo.currentText())
        p.import_mode = self._mode_combo.currentText().lower()
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

        # DWG-specific: preserve original .dwg path and layout
        if self._file_type == "dwg":
            p.file_path = getattr(self, "_dwg_source_path", p.file_path)
            p.layout = getattr(self, "_dwg_layout", "")

        self._save_settings()
        return p


# ── Backwards compat alias ───────────────────────────────────────────────────
DxfPreviewDialog = UnderlayImportDialog
