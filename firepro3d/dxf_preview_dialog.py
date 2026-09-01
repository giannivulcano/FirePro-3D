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
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QStackedWidget,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsItemGroup,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem,
    QLabel, QPushButton, QComboBox, QColorDialog,
    QListWidget, QListWidgetItem, QGroupBox,
    QFileDialog, QLineEdit, QFormLayout,
    QDialogButtonBox, QApplication,
    QCheckBox, QWidget, QSizePolicy, QScrollArea,
    QMessageBox, QInputDialog, QAbstractItemView, QFrame,
)
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QPainterPath, QFont, QFontMetricsF,
    QCursor, QPainter, QPixmap, QIcon, QTransform,
)
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QLineF, QSizeF, QSize, QSettings, QThread,
    pyqtSignal,
)

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
from .loading_bar import LoadingBar
from .theme import detect, build_app_qss
from .icons import themed_icon
from .constants import DEFAULT_LEVEL
from .underlay_mru import RecentSources
from .snap_engine import SnapEngine, OsnapResult, SNAP_COLORS, SNAP_MARKERS
from .underlay_snap_index import UnderlaySnapIndex
from .scale_manager import ScaleManager
from .dimension_edit import DimensionEdit
from .assets import asset_path


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
# PDF architectural / engineering scale ratios
# ─────────────────────────────────────────────────────────────────────────────

_MM_PER_POINT = 25.4 / 72.0   # a PDF point is 1/72 inch


def pdf_scale_from_ratio(paper_mm: float, real_mm: float) -> float:
    """import_scale (PDF points -> scene mm) for a paper:real drawing ratio.

    Derived from the calibration ground truth ``scale = real_mm / source_units``
    (source unit = point): a paper distance ``paper_mm`` occupies
    ``paper_mm / _MM_PER_POINT`` points, so ``scale = real_mm / that``.
    """
    if paper_mm <= 0:
        return 1.0
    return (real_mm / paper_mm) * _MM_PER_POINT


def _arch(label: str, paper_in: float, real_ft: float) -> tuple[str, float]:
    return (label, pdf_scale_from_ratio(paper_in * 25.4, real_ft * 304.8))


# Imperial architectural scales (paper inches : 1 foot).
_ARCH_SCALES: list[tuple[str, float]] = [
    _arch('1/8" = 1\'-0"', 0.125, 1.0),
    _arch('3/16" = 1\'-0"', 0.1875, 1.0),
    _arch('1/4" = 1\'-0"', 0.25, 1.0),
    _arch('3/8" = 1\'-0"', 0.375, 1.0),
    _arch('1/2" = 1\'-0"', 0.5, 1.0),
    _arch('3/4" = 1\'-0"', 0.75, 1.0),
    _arch('1" = 1\'-0"', 1.0, 1.0),
    _arch('1-1/2" = 1\'-0"', 1.5, 1.0),
    _arch('3" = 1\'-0"', 3.0, 1.0),
]

# Engineering scales (1 inch : N feet).
_ENG_SCALES: list[tuple[str, float]] = [
    _arch('1" = 10\'', 1.0, 10.0),
    _arch('1" = 20\'', 1.0, 20.0),
    _arch('1" = 30\'', 1.0, 30.0),
    _arch('1" = 40\'', 1.0, 40.0),
    _arch('1" = 50\'', 1.0, 50.0),
    _arch('1" = 100\'', 1.0, 100.0),
]


def pdf_scale_ratio_text(factor: float) -> str:
    """Human-readable ratio for a PDF import_scale factor (mm per point).

    ``factor`` = real-mm per PDF point. The drawing ratio is ``1 : M`` where
    ``M = real/paper`` magnification. If the factor matches a standard named
    scale (within 2%), that name is shown too.
    """
    if factor <= 0:
        return ""
    M = factor * 72.0 / 25.4          # real per paper -> drawing is 1 : M
    for label, sc in _ARCH_SCALES + _ENG_SCALES:
        if abs(sc - factor) <= 0.02 * factor:
            return f"{label}  (1:{M:.4g})"
    return f"1 : {M:.4g}"


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
        self.import_bounds: list[float] | None = None  # area selection bounds
        self.levels: list[str] = []            # authored by the Placement multi-select
        self.scale_verified: bool = False      # calibrate / "Looks right"


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
    zoomChanged = pyqtSignal(float)          # emits the ratio vs fit (1.0 == fit)

    _ZOOM_MIN = 0.25                          # 25% of fit
    _ZOOM_MAX = 12.0                          # 1200% of fit

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self._fit_scale = 1.0                 # view m11 at the last fitInView
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        # Hide the scrollbars — panning is driven programmatically via
        # the (still-functional) scrollbar values, so they're just clutter.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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

    def fitInView(self, *args, **kwargs):
        super().fitInView(*args, **kwargs)
        self._fit_scale = self.transform().m11() or 1.0
        self.zoomChanged.emit(self._zoom_ratio())

    def _zoom_ratio(self) -> float:
        return self.transform().m11() / (self._fit_scale or 1.0)

    def _clamped_factor(self, factor: float) -> float:
        """Clamp *factor* so the resulting zoom stays in [25%, 1200%] of fit."""
        cur = self.transform().m11()
        if cur <= 0:
            return factor
        lo, hi = self._ZOOM_MIN * self._fit_scale, self._ZOOM_MAX * self._fit_scale
        target = max(lo, min(hi, cur * factor))
        return target / cur

    def _apply_zoom(self, factor: float):
        """Zoom about the view centre with clamping (used by tests/buttons)."""
        real = self._clamped_factor(factor)
        self.scale(real, real)
        self.zoomChanged.emit(self._zoom_ratio())

    def wheelEvent(self, event):
        factor = self._clamped_factor(
            1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15)
        old = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new = self.mapToScene(event.position().toPoint())
        d = new - old
        self.translate(d.x(), d.y())
        self.zoomChanged.emit(self._zoom_ratio())

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
        elif marker == "diamond":
            from PyQt6.QtGui import QPolygon
            from PyQt6.QtCore import QPoint
            poly = QPolygon([
                QPoint(int(x),     int(y) - s),
                QPoint(int(x) + s, int(y)),
                QPoint(int(x),     int(y) + s),
                QPoint(int(x) - s, int(y)),
            ])
            painter.drawPolygon(poly)
        elif marker == "cross":
            painter.drawLine(int(x) - s, int(y) - s, int(x) + s, int(y) + s)
            painter.drawLine(int(x) + s, int(y) - s, int(x) - s, int(y) + s)
        elif marker == "right_angle":
            painter.drawLine(int(x) - s, int(y), int(x), int(y))
            painter.drawLine(int(x), int(y), int(x), int(y) - s)
            painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)
        elif marker == "tangent_circle":
            painter.drawEllipse(int(x) - s, int(y) - s, 2 * s, 2 * s)
            painter.drawLine(int(x) - s - 2, int(y) + s,
                             int(x) + s + 2, int(y) + s)
        elif marker == "x_cross":
            painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)
            painter.drawLine(int(x) - s, int(y) - s, int(x) + s, int(y) + s)
            painter.drawLine(int(x) + s, int(y) - s, int(x) - s, int(y) + s)
        painter.restore()


# ─────────────────────────────────────────────────────────────────────────────
# Unified import dialog
# ─────────────────────────────────────────────────────────────────────────────

# ── Background workers ────────────────────────────────────────────────────────

# Strong refs to unparented worker threads.  Workers must not be parented
# to the dialog (deleteLater() would destroy a running QThread), so they
# are kept alive here until their run() exits.
_LIVE_WORKERS: set = set()


def _keepalive(worker: QThread):
    _LIVE_WORKERS.add(worker)
    worker.finished.connect(lambda: _LIVE_WORKERS.discard(worker))


class _DialogReadWorker(QThread):
    """Sanitize + parse a DXF file off the GUI thread."""

    finished_doc = pyqtSignal(object)  # ezdxf document
    status = pyqtSignal(str)            # phase description for the bar
    error = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self):
        try:
            size_mb = 0.0
            try:
                size_mb = os.path.getsize(self._path) / (1024 * 1024)
            except OSError:
                pass
            size_note = f" ({size_mb:,.0f} MB)" if size_mb >= 1 else ""
            self.status.emit(f"Checking DXF formatting{size_note}…")
            clean = _sanitize_dxf(self._path)
            try:
                self.status.emit(f"Parsing DXF{size_note} — this can take a while…")
                doc = ezdxf.readfile(clean)
            finally:
                if clean != self._path and os.path.exists(clean):
                    os.remove(clean)
        except Exception as e:
            self.error.emit(str(e))
            return
        self.finished_doc.emit(doc)


class _DialogExtractWorker(QThread):
    """Per-entity geometry extraction off the GUI thread.

    Holds the in-memory ezdxf document and never re-reads the file, so
    DWG temp-file cleanup while extraction runs is safe.  The GUI must
    not touch the document while this runs (dialog controls are
    disabled for the duration).
    """

    progress = pyqtSignal(int, int)          # (current, total)
    status = pyqtSignal(str)                  # phase description for the bar
    finished_geoms = pyqtSignal(list, list)  # (geom dicts, layer names)
    aborted = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, doc, layout_name: str, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._layout = layout_name
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self._run_inner()
        except Exception as e:
            self.error.emit(str(e))

    def _run_inner(self):
        doc = self._doc
        layout_name = self._layout
        scope = "Model space" if layout_name == "Model" else f"layout “{layout_name}”"

        # ── Viewport bounds (paper layouts only) ─────────────────────────
        vp_bounds = None
        if layout_name != "Model":
            self.status.emit(f"Reading viewports for {scope}…")
            from .dwg_converter import get_viewport_bounds
            vp_bounds = get_viewport_bounds(
                layout_name=layout_name, doc=doc)

        # ── Extract model-space geometry ─────────────────────────────────
        from .dxf_import_worker import (
            DxfImportWorker, _build_layer_colors, _entity_in_viewport,
        )
        self.status.emit("Scanning drawing entities…")
        msp = doc.modelspace()
        all_ents = list(msp)

        # Collect layer names from doc + entity attributes (reuse the
        # entity list — re-walking the ezdxf entity DB doubles the pass)
        layers_set: set[str] = {"0"}
        for layer in doc.layers:
            layers_set.add(layer.dxf.name)
        for entity in all_ents:
            layers_set.add(
                entity.dxf.get("layer", "0")
                if hasattr(entity.dxf, "get") else "0"
            )

        worker_ref = DxfImportWorker.__new__(DxfImportWorker)
        worker_ref._cancelled = False
        worker_ref._layer_colors = _build_layer_colors(doc)

        total = len(all_ents)
        self.status.emit(f"Extracting geometry from {total:,} entities…")
        self.progress.emit(0, total)
        geoms: list[dict] = []
        for i, ent in enumerate(all_ents):
            if self._cancelled:
                self.aborted.emit()
                return
            if i % 100 == 0:
                self.progress.emit(i, total)
                # Briefly yield the GIL so the GUI thread is scheduled to
                # repaint the bar between chunks; without this the worker
                # races ahead and the main thread drains many queued progress
                # signals in one slice, so the bar appears to jump.
                self.usleep(300)
            # Pre-filter by viewport bounds at entity level
            if vp_bounds and not _entity_in_viewport(ent, vp_bounds):
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

        # ── Post-extraction viewport filter (catches INSERT/HATCH) ───────
        if vp_bounds:
            self.status.emit("Clipping geometry to the layout viewport…")
            from .dwg_converter import filter_geoms_by_bounds
            geoms = filter_geoms_by_bounds(geoms, vp_bounds)

        # ── Paper layout annotations ─────────────────────────────────────
        if layout_name != "Model":
            self.status.emit("Reading sheet annotations…")
            from .dwg_converter import extract_layout_entities
            layout_geoms = extract_layout_entities(
                layout_name=layout_name, doc=doc)
            if layout_geoms:
                geoms.extend(layout_geoms)

        if self._cancelled:
            self.aborted.emit()
            return
        geom_layers = {g.get("layer", "0") for g in geoms}
        self.finished_geoms.emit(geoms, sorted(layers_set | geom_layers))


# ─────────────────────────────────────────────────────────────────────────────
# Shell primitives — step-rail / levels picker / commit-sentence
# (used by the redesigned import shell; do not depend on UnderlayImportDialog)
# ─────────────────────────────────────────────────────────────────────────────

class _StepRail(QFrame):
    """Vertical step-rail widget with three clickable rows: source / content / place.

    Each row is a flat QPushButton. Clicking emits ``stepClicked(key)``.
    Rows carry a ``state`` dynamic property ("done" | "active" | "warn") that
    QSS can use for colouring; the shell layer adds the stylesheet.
    """

    stepClicked = pyqtSignal(str)

    _KEYS = ("source", "content", "place")
    _LABELS = {"source": "Source", "content": "Content", "place": "Placement"}

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self._rows: dict[str, QPushButton] = {}
        self._states: dict[str, str] = {}

        for key in self._KEYS:
            btn = QPushButton(self._LABELS[key])
            btn.setFlat(True)
            btn.setFixedWidth(160)
            # Emit the key when clicked — capture key in default arg
            btn.clicked.connect(lambda _checked, k=key: self.stepClicked.emit(k))
            lay.addWidget(btn)
            self._rows[key] = btn
            self._states[key] = "active"

    # ------------------------------------------------------------------
    def set_step(self, key: str, status: str, state: str) -> None:
        """Update a step row's status text and state badge."""
        btn = self._rows[key]
        self._states[key] = state

        # Elide the status to ~150px using the button's current font
        fm = QFontMetricsF(btn.font())
        elided = fm.elidedText(status, Qt.TextElideMode.ElideRight, 150)
        btn.setText(f"{self._LABELS[key]}\n{elided}")
        btn.setToolTip(status)

        btn.setProperty("state", state)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def row(self, key: str) -> QPushButton:
        """Return the QPushButton for *key*."""
        return self._rows[key]

    def state(self, key: str) -> str:
        """Return the stored state string for *key*."""
        return self._states[key]


class _LevelsPicker(QWidget):
    """Multi-select list of project levels (checkable QListWidget).

    The *current* level starts checked; all others unchecked.
    ``changed`` emits whenever any item's check state changes.
    """

    changed = pyqtSignal()

    def __init__(self, levels: list[str], current: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._list = QListWidget()
        self._levels = list(levels)

        for name in levels:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            state = Qt.CheckState.Checked if name == current else Qt.CheckState.Unchecked
            item.setCheckState(state)
            self._list.addItem(item)

        self._list.itemChanged.connect(lambda _item: self.changed.emit())
        lay.addWidget(self._list)

    # ------------------------------------------------------------------
    def selected(self) -> list[str]:
        """Return the names of all currently checked levels, in list order."""
        result = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.append(item.text())
        return result

    def set_selected(self, names: list[str]) -> None:
        """Set checked items to exactly *names*; others become unchecked."""
        name_set = set(names)
        for i in range(self._list.count()):
            item = self._list.item(i)
            new_state = (Qt.CheckState.Checked
                         if item.text() in name_set
                         else Qt.CheckState.Unchecked)
            item.setCheckState(new_state)


def build_commit_sentence(
    *,
    name: str,
    page: int,
    pages: int,
    layers_hidden: int,
    cropped: bool,
    scale: str,
    verified: bool,
    rotation: int | float,
    levels: list[str],
    position: str,
    warn_hex: str | None = None,
    ok_hex: str | None = None,
) -> str:
    """Return an HTML rich-text summary sentence describing the pending import.

    Clauses are omitted when they carry no information (e.g. page clause when
    pages <= 1, layers-hidden clause when 0, rotation clause when 0).
    """
    theme = detect()
    if warn_hex is None:
        warn_hex = theme.warn
    if ok_hex is None:
        ok_hex = theme.ok

    parts: list[str] = []

    # Name — always bold
    parts.append(f"Import <b>{name}</b>")

    # Page clause — only for multi-page sources
    if pages > 1:
        parts.append(f"· page {page} of {pages}")

    # Layers hidden
    if layers_hidden > 0:
        parts.append(f"· {layers_hidden} layers hidden")

    # Crop
    if cropped:
        parts.append("· cropped")
    else:
        parts.append("· whole sheet")

    # Scale + verification
    verified_word = "verified" if verified else "unverified"
    color_hex = ok_hex if verified else warn_hex
    parts.append(
        f"· at <b>{scale}</b> "
        f"(<span style='color:{color_hex}'>{verified_word}</span>)"
    )

    # Rotation — only when non-zero
    if rotation != 0:
        parts.append(f"· rotated {rotation}°")

    # Levels — always
    levels_str = " + ".join(levels)
    parts.append(f"· onto <b>{levels_str}</b>")

    sentence = " ".join(parts)

    # Position tail
    if position == "pick":
        sentence += " — then pick the insertion point."
    elif position == "origin":
        sentence += " — placed at the origin."

    return sentence


class UnderlayImportDialog(QDialog):
    """Unified preview-first import dialog for PDF and DXF underlays."""

    _SCALE_OPTIONS = [
        ("1:1",               1.0),
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
                 scale_manager=None, default_dir: str = "",
                 levels: list[str] | None = None, current_level: str = "",
                 modify_record=None):
        super().__init__(parent)
        self.setWindowTitle("Import Underlay — Preview")
        # Frameless: the shell draws its own single header (no OS title bar on
        # top of ours). Draggable via the header; Cancel/✕ close it.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.resize(1220, 680)
        proj = getattr(parent, "_current_file", None)
        self._project_name = (os.path.splitext(os.path.basename(proj))[0]
                              if proj else "Untitled")
        self._drag_pos = None

        self._sm = scale_manager
        self._default_dir = default_dir
        self._import_levels = list(levels) if levels else []
        self._current_level = current_level
        self._modify_record = modify_record
        self._mru = RecentSources()
        self._scale_verified = False
        self._scale_provenance = ""
        self._crop_scrim = None
        self._active_step = "source"
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
        self._pdf_page_names: list[str] = []
        self._doc = None          # ezdxf document (DXF/DWG only)
        self._extracting = False  # re-entrancy guard for extraction
        self._extract_worker: _DialogExtractWorker | None = None
        self._read_worker: _DialogReadWorker | None = None
        self._extract_total: int | None = None
        self._pending_read_path: str = ""
        self._preview_geom_group = None
        self._snap_index: UnderlaySnapIndex | None = None
        self._snap_index_src: list | None = None  # identity of indexed geoms
        # Per-layout extraction memo: layout name -> (geoms, layers).
        # Revisiting Model→Layout1→Model previously re-extracted thrice.
        self._layout_cache: dict[str, tuple[list[dict], list[str]]] = {}

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

        if modify_record is not None:
            self._apply_modify_prefill(modify_record)

    def _apply_modify_prefill(self, record):
        """Pre-load the dialog from an existing underlay record (Modify flow).

        Sets the file, then the scale/rotation/page/dpi/mode/base widgets from
        the record so re-placement starts from the record's current state.
        Layer selection is left to the freshly loaded file (the record's
        selected_layers still round-trips via the layer tree once geometry is
        available); management fields (colour, levels, overrides…) are NOT
        surfaced here — they are preserved by replace_underlay, not re-edited.
        """
        _name = os.path.basename(record.path) or "underlay"
        self.setWindowTitle(f"Modify Underlay — {_name}")
        if hasattr(self, "_title_lbl"):
            self._title_lbl.setText(f"Modify Underlay — {_name}")
        _ok = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if _ok is not None:
            _ok.setText("Save changes")

        # Load the file first (sync for PDF, async for DXF).
        self._file_edit.setText(record.path)
        self._load_file()

        # PDF page — set the target page and (re)render it.
        if record.type == "pdf" and record.page:
            self._pdf_page = record.page
            try:
                self._load_pdf_page(record.path, record.page)
            except Exception:
                pass

        # DPI / import mode combos (PDF).
        self._dpi_combo.blockSignals(True)
        self._dpi_combo.setCurrentText(str(record.dpi))
        self._dpi_combo.blockSignals(False)
        self._mode_combo.blockSignals(True)
        self._mode_combo.setCurrentText(record.import_mode.capitalize())
        self._mode_combo.blockSignals(False)

        # Scale — the record stores the baked import multiplier as import_scale.
        # Route it through the "Custom…" option so get_import_params().scale
        # reproduces it exactly.
        custom_idx = len(self._SCALE_OPTIONS) - 1
        self._scale_combo.blockSignals(True)
        self._scale_combo.setCurrentIndex(custom_idx)
        self._scale_combo.blockSignals(False)
        self._custom_scale_edit.blockSignals(True)
        self._custom_scale_edit.setText(f"{record.import_scale:.6g}")
        self._custom_scale_edit.blockSignals(False)

        # Rotation (display transform).
        self._set_rotation(record.rotation)

        # Base point (subtracted before scaling at import time).
        try:
            self._base_x_edit.set_value_mm(record.import_base_x)
            self._base_y_edit.set_value_mm(record.import_base_y)
            self._base_x = record.import_base_x
            self._base_y = record.import_base_y
        except Exception:
            pass

        # Levels + scale-provenance (redesign): the dialog authors these now.
        # A verified scale must stay verified — set AFTER the (signal-blocked)
        # scale restore above so the factor-change reset doesn't clear it.
        self._levels_picker.set_selected(list(record.levels))
        self._scale_verified = bool(getattr(record, "scale_verified", False))
        self._scale_provenance = "Restored from the saved underlay."
        self._update_all()

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
        """Assemble the redesigned shell: title bar · [step rail | preview |
        contextual panel] · commit-sentence footer. All the heavy controls are
        the same widgets as before — only re-homed into the new containers."""
        t = detect()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Object-scoped chrome for the shell (rail rows, cards, footer, pills).
        self.setObjectName("ImportUnderlayDialog")
        self.setStyleSheet(build_app_qss(t) + f"""
        #ImportUnderlayDialog {{ background:{t.ground}; }}
        #importTitleBar {{ background:{t.surface}; border-bottom:1px solid {t.line}; }}
        #importFooter {{ background:{t.raised}; border-top:1px solid {t.line}; }}
        #importRail {{ background:{t.surface}; border-right:1px solid {t.line}; }}
        #importRail QPushButton {{ text-align:left; padding:7px 10px; border:none;
            border-left:3px solid transparent; background:transparent; color:{t.ink};
            border-radius:0; }}
        #importRail QPushButton[state="active"],
        #importRail QPushButton[state="warn"] {{ border-left:3px solid {t.accent}; }}
        #importPanel {{ background:{t.surface}; border-left:1px solid {t.line}; }}
        """)

        # ── Title bar (single header — the window is frameless) ──────────────
        self._titlebar = QFrame(objectName="importTitleBar")
        self._titlebar.setFixedHeight(40)
        tbl = QHBoxLayout(self._titlebar)
        tbl.setContentsMargins(14, 8, 12, 8)
        glyph = QLabel()
        try:
            glyph.setPixmap(themed_icon(
                "underlay_import_icon.svg",
                "light" if t.name == "light" else "dark").pixmap(20, 20))
        except Exception:
            pass
        self._title_lbl = QLabel(f"Import Underlay  —  {self._project_name}")
        self._title_lbl.setStyleSheet(
            f"color:{t.ink}; font-size:13px; font-weight:600; background:transparent;")
        tbl.addWidget(glyph)
        tbl.addSpacing(8)
        tbl.addWidget(self._title_lbl)
        tbl.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 24)
        close_btn.setStyleSheet(
            f"QPushButton{{border:none; background:transparent; color:{t.muted};"
            f" font-size:14px; border-radius:5px;}}"
            f"QPushButton:hover{{background:{t.danger}; color:#fff;}}")
        close_btn.clicked.connect(self.reject)
        tbl.addWidget(close_btn)
        outer.addWidget(self._titlebar)

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

        # Compact "pill" button factory (rounded segmented-control style).
        def _pill(text, slot, tip="", icon=None, checkable=False, expanding=False):
            b = QPushButton(icon, text) if icon is not None else QPushButton(text)
            b.setStyleSheet(
                "QPushButton { padding: 3px 10px; border-radius: 11px; }")
            b.setSizePolicy(
                QSizePolicy.Policy.Expanding if expanding
                else QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Fixed)
            if checkable:
                b.setCheckable(True)
            if slot is not None:
                b.clicked.connect(slot)
            if tip:
                b.setToolTip(tip)
            return b

        def _sep():
            line = QWidget()
            line.setFixedHeight(1)
            line.setStyleSheet(f"background: {t.border_subtle};")
            return line

        # ── Body: step rail | preview workspace | contextual panel ──────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Step rail
        rail_wrap = QFrame(objectName="importRail")
        rail_wrap.setFixedWidth(188)
        rw = QVBoxLayout(rail_wrap)
        rw.setContentsMargins(6, 12, 6, 12)
        self._rail = _StepRail()
        self._rail.stepClicked.connect(self._on_rail_clicked)
        rw.addWidget(self._rail)
        rw.addStretch(1)
        body.addWidget(rail_wrap)

        # Preview workspace column: toolbar (mode pills + Fit readout) · view · chip
        prev_wrap = QWidget()
        prev_lay = QVBoxLayout(prev_wrap)
        prev_lay.setContentsMargins(10, 10, 10, 8)
        prev_lay.setSpacing(6)
        ptool = QHBoxLayout()
        self._preview_hint = QLabel(
            "Drop a source to begin — everything happens on this preview.")
        self._preview_hint.setStyleSheet(
            f"color:{t.muted}; font-size:11px; background:transparent;")
        ptool.addWidget(self._preview_hint)
        ptool.addStretch(1)
        self._fit_readout = QLabel("Fit · 100%")
        self._fit_readout.setStyleSheet(
            f"color:{t.muted}; font-size:11px; background:transparent;")
        self._preview_view.zoomChanged.connect(self._on_preview_zoom)
        ptool.addWidget(self._fit_readout)
        prev_lay.addLayout(ptool)
        prev_lay.addWidget(self._preview_view, 1)
        self._instruction_chip = QLabel("")
        self._instruction_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._instruction_chip.setStyleSheet(
            f"background:{t.raised}; color:{t.muted}; border:1px solid {t.line};"
            f" border-radius:9px; padding:3px; font-size:10.5px;")
        self._instruction_chip.setVisible(False)
        prev_lay.addWidget(self._instruction_chip)
        self._info_lbl = QLabel("Drop a PDF, DWG or DXF here — or use Browse.")
        self._info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_lbl.setStyleSheet(f"color:{t.faint};")
        prev_lay.addWidget(self._info_lbl)
        # Pan is the default view mode; kept hidden so _set_view_mode has a
        # toggle target (Draw-crop lives in the Content panel).
        self._pan_btn = QPushButton()
        self._pan_btn.setCheckable(True)
        self._pan_btn.setChecked(True)
        self._pan_btn.setVisible(False)
        body.addWidget(prev_wrap, 1)

        # ── Contextual panel: a QStackedWidget, ONE page per step ────────────
        self._panel_stack = QStackedWidget(objectName="importPanel")
        self._panel_stack.setFixedWidth(324)
        self._controls_panel = self._panel_stack
        self._panel_pages = {"source": 0, "content": 1, "place": 2}

        def _page():
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(14, 14, 14, 14)
            v.setSpacing(9)
            return w, v

        def _hdr(txt):
            l = QLabel(txt.upper())
            l.setStyleSheet(
                f"color:{t.ink}; font-size:12px; font-weight:700;"
                f" letter-spacing:1px; background:transparent;")
            return l

        # -- Page 0: SOURCE (file + recent) --
        src_pg, src_v = _page()
        src_v.addWidget(_hdr("Source"))
        self._file_edit = QLineEdit()
        src_v.addWidget(self._file_edit)
        frow = QHBoxLayout()
        frow.addWidget(_pill("Browse", self._browse_file))
        frow.addWidget(_pill("Reload", self._load_file))
        frow.addStretch()
        src_v.addLayout(frow)
        rlbl = QLabel("Recent")
        rlbl.setStyleSheet(f"color:{t.faint}; font-size:10px;")
        src_v.addWidget(rlbl)
        self._recent_list = QListWidget()
        self._recent_list.setMaximumHeight(140)
        self._recent_list.itemClicked.connect(self._on_recent_clicked)
        src_v.addWidget(self._recent_list)
        src_v.addStretch(1)
        self._panel_stack.addWidget(src_pg)
        self._refresh_recent_list()

        # -- Page 1: CONTENT (layout · layers · region · PDF options) --
        con_pg, con_v = _page()
        con_v.addWidget(_hdr("Content"))
        self._layout_label = QLabel("Layout:")
        self._layout_label.setVisible(False)
        con_v.addWidget(self._layout_label)
        self._layout_combo = QComboBox()
        self._layout_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        self._layout_combo.setVisible(False)
        con_v.addWidget(self._layout_combo)
        layer_grp = QGroupBox("Source layers")
        layer_vlay = QVBoxLayout(layer_grp)
        la_btn_row = QHBoxLayout()
        la_btn_row.addWidget(_pill("All", self._select_all_layers))
        la_btn_row.addWidget(_pill("None", self._deselect_all_layers))
        la_btn_row.addStretch()
        layer_vlay.addLayout(la_btn_row)
        self._layer_list = QListWidget()
        self._layer_list.setMaximumHeight(180)
        self._layer_list.itemChanged.connect(self._on_layer_changed)
        layer_vlay.addWidget(self._layer_list)
        con_v.addWidget(layer_grp)
        # Region (crop) — Draw crop / Clear live here (armed on the preview).
        region_grp = QGroupBox("Region")
        region_v = QVBoxLayout(region_grp)
        self._region_lbl = QLabel(
            "Whole sheet imports. Draw a crop on the preview to bring in just "
            "one area.")
        self._region_lbl.setWordWrap(True)
        self._region_lbl.setStyleSheet(f"color:{t.muted}; font-size:11px;")
        region_v.addWidget(self._region_lbl)
        crop_row = QHBoxLayout()
        self._rb_btn = _pill(
            "Draw crop", lambda: self._set_view_mode("rubber_band"),
            icon=QIcon(asset_path("Ribbon", "cut_icon.svg")), checkable=True)
        self._clear_sel_btn = _pill("Clear", self._clear_selection)
        crop_row.addWidget(self._rb_btn)
        crop_row.addWidget(self._clear_sel_btn)
        crop_row.addStretch()
        region_v.addLayout(crop_row)
        con_v.addWidget(region_grp)
        self._pdf_opts_grp = QGroupBox("PDF Options")
        pdf_form = QFormLayout(self._pdf_opts_grp)
        self._dpi_combo = QComboBox()
        self._dpi_combo.addItems(["72", "150", "300"])
        self._dpi_combo.setCurrentIndex(1)
        self._dpi_combo.currentIndexChanged.connect(self._on_pdf_option_changed)
        pdf_form.addRow("DPI:", self._dpi_combo)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Auto", "Vectors", "Raster"])
        self._mode_combo.setCurrentIndex(0)
        self._mode_combo.currentIndexChanged.connect(self._on_pdf_option_changed)
        pdf_form.addRow("Mode:", self._mode_combo)
        self._pdf_opts_grp.setVisible(False)
        con_v.addWidget(self._pdf_opts_grp)
        con_v.addStretch(1)
        self._panel_stack.addWidget(con_pg)

        # -- Page 2: PLACEMENT (levels · scale evidence · rotation · base · pos) --
        pl_pg, pl_v = _page()
        pl_v.addWidget(_hdr("Placement"))
        pl_v.addWidget(QLabel("Levels — where it shows"))
        self._levels_picker = _LevelsPicker(
            self._import_levels or [self._current_level or DEFAULT_LEVEL],
            current=self._current_level or DEFAULT_LEVEL)
        self._levels_picker.setMaximumHeight(96)
        self._levels_picker.changed.connect(self._update_all)
        self._selected_levels = self._levels_picker.selected  # get_import_params hook
        pl_v.addWidget(self._levels_picker)
        pl_v.addWidget(_sep())

        scale_head = QHBoxLayout()
        scale_head.addWidget(QLabel("Scale:"))
        self._scale_combo = QComboBox()
        self._populate_scale_combo(is_pdf=False)
        self._scale_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._scale_combo.currentIndexChanged.connect(self._on_scale_combo_changed)
        scale_head.addWidget(self._scale_combo)
        self._custom_scale_edit = QLineEdit()
        self._custom_scale_edit.setPlaceholderText("factor")
        self._custom_scale_edit.setText("1.0")
        self._custom_scale_edit.setFixedWidth(80)
        self._custom_scale_edit.setVisible(False)
        self._custom_scale_edit.textChanged.connect(self._on_custom_scale_edited)
        scale_head.addWidget(self._custom_scale_edit)
        scale_head.addStretch()
        self._scale_pill = QLabel(" unverified ")
        scale_head.addWidget(self._scale_pill)
        pl_v.addLayout(scale_head)
        acts_row = QHBoxLayout()
        self._calibrate_btn = _pill(
            "Calibrate", self._start_pick2,
            tip=("Click two points on the preview, then enter the real distance "
                 "between them."),
            icon=QIcon(asset_path("Ribbon", "dimension_icon.svg")))
        acts_row.addWidget(self._calibrate_btn)
        acts_row.addWidget(_pill(
            "Looks right", lambda: self._mark_scale_verified("Confirmed by eye.")))
        acts_row.addStretch()
        pl_v.addLayout(acts_row)
        self._units_info_lbl = QLabel("")
        self._units_info_lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        self._units_info_lbl.setVisible(False)
        pl_v.addWidget(self._units_info_lbl)
        self._calibration_lbl = QLabel("")
        self._calibration_lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        self._calibration_lbl.setVisible(False)
        pl_v.addWidget(self._calibration_lbl)
        self._scale_readout_lbl = QLabel("")
        self._scale_readout_lbl.setStyleSheet(f"color: {t.accent}; font-size: 11px;")
        self._scale_readout_lbl.setVisible(False)
        pl_v.addWidget(self._scale_readout_lbl)
        self._scale_ratio_lbl = QLabel("")
        self._scale_ratio_lbl.setStyleSheet(f"color: {t.text_secondary}; font-size: 11px;")
        self._scale_ratio_lbl.setVisible(False)
        pl_v.addWidget(self._scale_ratio_lbl)
        pl_v.addWidget(_sep())

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Angle:"))
        self._rotation_edit = QLineEdit()
        self._rotation_edit.setText("0.0°")
        self._rotation_edit.setFixedWidth(58)
        self._rotation_edit.editingFinished.connect(self._on_rotation_changed)
        rot_row.addWidget(self._rotation_edit)
        rot_row.addStretch()
        rot_row.addWidget(_pill(
            "−90°", lambda: self._set_rotation(self._get_rotation() - 90.0)))
        rot_row.addWidget(_pill(
            "+90°", lambda: self._set_rotation(self._get_rotation() + 90.0)))
        rot_row.addWidget(_pill(
            "180°", lambda: self._set_rotation(self._get_rotation() + 180.0)))
        pl_v.addLayout(rot_row)
        pl_v.addWidget(_sep())

        base_row = QHBoxLayout()
        base_x_lbl = QLabel("X:")
        base_row.addWidget(base_x_lbl)
        self._base_x_edit = DimensionEdit(self._sm, initial_mm=0.0)
        self._base_x_edit.setFixedWidth(68)
        self._base_x_edit.valueChanged.connect(self._on_base_changed)
        base_row.addWidget(self._base_x_edit)
        base_y_lbl = QLabel("Y:")
        base_row.addWidget(base_y_lbl)
        self._base_y_edit = DimensionEdit(self._sm, initial_mm=0.0)
        self._base_y_edit.setFixedWidth(68)
        self._base_y_edit.valueChanged.connect(self._on_base_changed)
        base_row.addWidget(self._base_y_edit)
        base_row.addStretch()
        self._pick_base_btn = _pill(
            "Pick", self._start_pick_base, tip="Pick base point on preview")
        base_row.addWidget(self._pick_base_btn)
        pl_v.addLayout(base_row)
        self._base_inputs = [base_x_lbl, self._base_x_edit,
                             base_y_lbl, self._base_y_edit, self._pick_base_btn]

        pl_v.addWidget(_sep())
        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("Position:"))
        self._origin_cb = QCheckBox("Insert at origin")
        self._origin_cb.setChecked(True)
        self._origin_cb.toggled.connect(self._update_base_enabled)
        pos_row.addWidget(self._origin_cb)
        pos_row.addStretch()
        pl_v.addLayout(pos_row)
        pl_v.addStretch(1)
        self._panel_stack.addWidget(pl_pg)

        body.addWidget(self._panel_stack)
        outer.addLayout(body, 1)
        self._switch_step("source")

        # Progress bar (hidden by default)
        self._loading_bar = LoadingBar(self, cancel=True)
        outer.addWidget(self._loading_bar)

        # ── Commit footer: sentence + Cancel / Import ───────────────────────
        footer = QFrame(objectName="importFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(14, 9, 14, 9)
        self._status_lbl = QLabel("")          # retained (some code sets it)
        self._status_lbl.setVisible(False)
        self._commit_label = QLabel("")
        self._commit_label.setTextFormat(Qt.TextFormat.RichText)
        self._commit_label.setWordWrap(True)
        self._commit_label.setStyleSheet(
            f"color:{t.muted}; font-size:11.5px; background:transparent;")
        fl.addWidget(self._commit_label, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import →")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self._button_box = buttons
        fl.addWidget(buttons)
        outer.addWidget(footer)

        # Scale edits invalidate a verified scale (calibration excepted).
        self._scale_combo.currentIndexChanged.connect(
            lambda *_: self._on_scale_factor_changed())
        self._custom_scale_edit.textChanged.connect(
            lambda *_: self._on_scale_factor_changed())
        self._rotation_edit.editingFinished.connect(self._update_all)
        self._origin_cb.toggled.connect(lambda *_: self._update_all())
        self._layer_list.itemChanged.connect(lambda *_: self._update_all())
        self._file_edit.textChanged.connect(lambda *_: self._update_all())

        self._update_base_enabled()  # base point starts disabled (origin on)
        self._update_all()

        # Accept drops of underlay files anywhere on the dialog.
        self.setAcceptDrops(True)

    # ── Shell wiring (redesign) ────────────────────────────────────────────

    def _on_rail_clicked(self, key: str) -> None:
        """Rail rows switch the contextual panel to that step's section."""
        self._switch_step(key)

    def _switch_step(self, key: str) -> None:
        """Show the panel page for *key* and mark that rail row active."""
        idx = self._panel_pages.get(key)
        if idx is None:
            return
        self._panel_stack.setCurrentIndex(idx)
        self._active_step = key
        self._update_all()

    # Frameless-window drag: the header moves the dialog.
    def mousePressEvent(self, event):
        tb = getattr(self, "_titlebar", None)
        if (tb is not None and event.button() == Qt.MouseButton.LeftButton
                and tb.geometry().contains(event.position().toPoint())):
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _on_preview_zoom(self, ratio: float) -> None:
        self._fit_readout.setText(f"Fit · {int(round(ratio * 100))}%")

    def _refresh_recent_list(self) -> None:
        self._recent_list.clear()
        for p in self._mru.list():
            self._recent_list.addItem(os.path.basename(p))
            self._recent_list.item(self._recent_list.count() - 1).setToolTip(p)

    def _on_recent_clicked(self, item) -> None:
        path = item.toolTip()
        if path:
            self._file_edit.setText(path)
            self._load_file()

    def _note_recent_source(self, path: str) -> None:
        if path:
            self._mru.add(path)
            self._refresh_recent_list()

    @staticmethod
    def _accepts_drop(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in (".pdf", ".dwg", ".dxf")

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            urls = md.urls()
            if len(urls) == 1 and self._accepts_drop(urls[0].toLocalFile()):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if self._accepts_drop(path):
                self._file_edit.setText(path)
                self._load_file()
                event.acceptProposedAction()
                return
        event.ignore()

    def _mark_scale_verified(self, provenance: str) -> None:
        self._scale_verified = True
        self._scale_provenance = provenance
        self._update_all()

    def _on_scale_factor_changed(self) -> None:
        self._scale_verified = False
        self._update_all()

    def _update_all(self) -> None:
        """Rebuild the scale pill, step-rail statuses, and commit sentence from
        the current dialog state. Safe to call before the shell is fully built."""
        if not hasattr(self, "_commit_label"):
            return
        t = detect()
        verified = self._scale_verified
        col = t.ok if verified else t.warn
        self._scale_pill.setText(" verified " if verified else " unverified ")
        self._scale_pill.setStyleSheet(
            f"background:transparent; color:{col}; border:1px solid {col};"
            f" border-radius:8px; padding:1px 8px; font-size:10px; font-weight:700;")

        path = self._file_edit.text().strip()
        name = os.path.splitext(os.path.basename(path))[0] if path else "(no file)"
        pages = getattr(self, "_pdf_page_count", 0) or 1
        page = (getattr(self, "_pdf_page", 0) or 0) + 1
        layers_hidden = sum(
            1 for i in range(self._layer_list.count())
            if self._layer_list.item(i).checkState() != Qt.CheckState.Checked)
        cropped = self._selected_indices is not None
        if self._custom_scale_edit.isVisible():
            scale_str = self._custom_scale_edit.text() or "1.0"
        else:
            scale_str = self._scale_combo.currentText() or "1:1"
        rotation = int(round(self._get_rotation()))
        levels = self._levels_picker.selected()
        position = "origin" if self._origin_cb.isChecked() else "pick"

        self._commit_label.setText(build_commit_sentence(
            name=name, page=page, pages=pages, layers_hidden=layers_hidden,
            cropped=cropped, scale=scale_str, verified=verified,
            rotation=rotation, levels=levels, position=position))

        active = getattr(self, "_active_step", "source")
        states = {
            "source": ("done" if path else "warn"),
            "content": ("done" if path else "warn"),
            "place": ("done" if (verified and levels) else "warn"),
        }
        # The active row is highlighted unless it already warns.
        for k in states:
            if k == active and states[k] != "warn":
                states[k] = "active"
        self._rail.set_step(
            "source", (os.path.basename(path) or "Drop a file or Browse"),
            states["source"])
        self._rail.set_step(
            "content", ("cropped" if cropped else "whole sheet"),
            states["content"])
        self._rail.set_step(
            "place",
            f"{len(levels)} level{'s' if len(levels) != 1 else ''} · "
            f"{'verified' if verified else 'unverified'}",
            states["place"])

        ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setEnabled(bool(levels))

    # ── Loading state ─────────────────────────────────────────────────────

    def _set_controls_enabled(self, enabled: bool):
        """Enable/disable the preview, controls panel, and bottom buttons.

        Disabled during loading AND extraction — the progress bar pumps
        processEvents, so enabled controls would let layer toggles or
        Import clicks land on a half-built ``_all_geoms``.
        """
        self._preview_view.setEnabled(enabled)
        panel = getattr(self, "_controls_panel", None)
        if panel is not None:
            panel.setEnabled(enabled)
        btns = getattr(self, "_button_box", None) or self.findChild(QDialogButtonBox)
        if btns:
            btns.setEnabled(enabled)

    def _set_loading(self, message: str):
        """Disable controls and show a loading message with indeterminate progress."""
        self._loading_bar.start(message)
        self._set_controls_enabled(False)

    def _set_extracting(self, total: int):
        """Switch progress bar to determinate mode for entity extraction."""
        self._loading_bar.start_determinate(total, "Extracting entities…")
        self._set_controls_enabled(False)

    def _update_progress(self, current: int, total: int, message: str = ""):
        """Update progress bar value and optional message."""
        self._loading_bar.update(current, message)

    def _clear_loading(self):
        """Re-enable controls and hide progress bar."""
        self._loading_bar.finish()
        self._set_controls_enabled(True)

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
        if self._extracting or self._read_worker is not None:
            return  # a load is already in flight
        path = self._file_edit.text().strip()
        if not path or not os.path.exists(path):
            return

        ext = os.path.splitext(path)[1].lower()
        if ext in (".pdf", ".dxf", ".dwg"):
            self._note_recent_source(path)
            self._switch_step("content")   # loading a source auto-advances
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

    def _load_dxf(self, path: str, _doc=None):
        """Load a DXF file with layout detection and deferred extraction.

        Args:
            path: Path to the DXF file.
            _doc: Pre-read ezdxf document (skips sanitization/read).
                  Used by _load_dwg() to pass ODA-converted docs that
                  must not go through _sanitize_dxf().
        """
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
            self._on_dxf_read(path, _doc)
            return

        # Read + parse off the GUI thread \u2014 readfile blocks for tens
        # of seconds on large files.  Continues in _on_read_finished.
        self._set_loading("Reading DXF file\u2026")
        self._pending_read_path = path
        w = _DialogReadWorker(path)
        self._read_worker = w
        w.finished_doc.connect(self._on_read_finished)
        w.status.connect(self._on_read_status)
        w.error.connect(self._on_read_error)
        _keepalive(w)
        w.start()

    def _on_read_status(self, message: str):
        if self._read_worker is None:
            return
        self._loading_bar.busy(message)

    def _on_read_finished(self, doc):
        if self._read_worker is None:
            return  # dialog closed while reading \u2014 discard
        self._read_worker = None
        self._on_dxf_read(self._pending_read_path, doc)

    def _on_read_error(self, msg: str):
        if self._read_worker is None:
            return
        self._read_worker = None
        self._clear_loading()
        self._info_lbl.setText(f"Error: {msg}")

    def _on_dxf_read(self, path: str, doc):
        """Continue the DXF load once the document is available."""
        self._doc = doc
        self._layout_cache.clear()  # new document — memo entries are stale

        # Auto-detect DXF units ($INSUNITS)
        self._populate_scale_combo(is_pdf=False)  # clear any prior PDF arch scales
        self._detect_dxf_units(doc)

        # Detect layouts
        from .dwg_converter import list_layouts
        layouts = list_layouts(doc=doc)

        if len(layouts) <= 1:
            # Single layout — hide combo, extract immediately
            self._layout_combo.blockSignals(True)
            self._layout_combo.clear()
            self._layout_combo.blockSignals(False)
            self._layout_combo.setVisible(False)
            self._layout_label.setVisible(False)
            self._clear_loading()
            self._extract_for_layout("Model")
        else:
            # Multiple layouts — show combo, defer extraction
            self._layout_combo.blockSignals(True)
            self._layout_combo.clear()
            for name in layouts:
                self._layout_combo.addItem(name)
            self._layout_combo.setCurrentIndex(-1)  # no selection
            self._layout_combo.blockSignals(False)
            self._layout_combo.setVisible(True)
            self._layout_label.setVisible(True)
            self._clear_loading()
            self._info_lbl.setText("Select a layout to preview.")
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

    def _on_layout_changed(self, index: int):
        """Handle layout combo selection — extract geometry for the chosen layout."""
        if index < 0 or not hasattr(self, "_doc") or self._doc is None:
            return
        layout_name = self._layout_combo.currentText()
        self._extract_for_layout(layout_name)

    def _extract_for_layout(self, layout_name: str):
        """Extract geometry for a layout and rebuild the preview.

        Memoized layouts restore synchronously; otherwise extraction
        runs on a _DialogExtractWorker thread and continues in
        _on_extract_finished — the GUI stays responsive and Cancel
        genuinely aborts instead of committing a partial result.
        """
        if self._extracting:
            return
        self._selected_layout = layout_name

        # ── Memoized layout — skip re-extraction entirely ────────────────
        cached = self._layout_cache.get(layout_name)
        if cached is not None:
            self._all_geoms, layers = cached
            self._layers = list(layers)
            self._populate_layer_list()
            self._selected_indices = None
            self._set_loading("Building preview…")
            self._rebuild_preview()
            self._clear_loading()
            self._show_extract_summary(layout_name)
            return

        if self._doc is None:
            return

        self._extracting = True
        self._extract_total = None
        self._set_loading("Preparing extraction…")
        w = _DialogExtractWorker(self._doc, layout_name)
        self._extract_worker = w
        w.progress.connect(self._on_extract_progress)
        w.status.connect(self._on_extract_status)
        w.finished_geoms.connect(self._on_extract_finished)
        w.aborted.connect(self._on_extract_aborted)
        w.error.connect(self._on_extract_error)
        _keepalive(w)
        w.start()

    def _show_extract_summary(self, layout_name: str):
        path = self._file_edit.text().strip()
        n = len(self._all_geoms)
        layout_label = (f" (layout: {layout_name})"
                        if layout_name != "Model" else "")
        self._info_lbl.setText(
            f"{n:,} entities loaded from "
            f"{os.path.basename(path)}{layout_label}")
        self._update_status()

    def _on_extract_progress(self, current: int, total: int):
        if self._extract_worker is None:
            return
        if self._loading_bar.cancelled:
            self._extract_worker.cancel()
            return
        if total != self._extract_total:
            self._extract_total = total
            self._set_extracting(total)  # determinate bar + controls off
        pct = f"  {current:,} / {total:,}" if total else ""
        self._update_progress(current, total, f"Extracting geometry…{pct}")

    def _on_extract_status(self, message: str):
        """Show a descriptive phase label for the un-counted extraction
        phases (scan, viewport clip, sheet annotations) as an indeterminate
        pulse so the bar never sits frozen at 100 %."""
        if self._extract_worker is None:
            return
        if self._loading_bar.cancelled:
            self._extract_worker.cancel()
            return
        self._loading_bar.busy(message)

    def _on_extract_finished(self, geoms: list, layers: list):
        if self._extract_worker is None:
            return  # dialog closed mid-extraction — discard the result
        self._extract_worker = None
        self._extracting = False
        layout_name = self._selected_layout
        self._all_geoms = geoms

        # ── Entity type dialog (DWG files only, first extraction) ────────
        if getattr(self, "_show_entity_type_filter", False):
            self._show_entity_type_filter = False
            self._clear_loading()
            excluded = self._show_geom_type_dialog()
            if excluded is None:
                # User cancelled — clean up and bail
                from .dwg_converter import cleanup_converted_dxf
                cleanup_converted_dxf(
                    getattr(self, "_converted_dxf_path", ""))
                self._all_geoms = []
                self._rebuild_preview()
                self._info_lbl.setText("Import cancelled.")
                return
            if excluded:
                self._all_geoms = [
                    g for g in self._all_geoms
                    if g.get("kind") not in excluded
                ]

        self._layers = list(layers)
        self._populate_layer_list()
        self._selected_indices = None

        # Memoize — only complete (non-aborted) extractions reach here
        self._layout_cache[layout_name] = (
            self._all_geoms, list(self._layers))

        self._set_loading("Building preview…")
        self._rebuild_preview()
        self._clear_loading()
        self._show_extract_summary(layout_name)

    def _on_extract_aborted(self):
        self._extract_worker = None
        self._extracting = False
        self._clear_loading()
        self._info_lbl.setText("Extraction cancelled.")
        self._update_status()

    def _on_extract_error(self, msg: str):
        if self._extract_worker is None:
            return
        self._extract_worker = None
        self._extracting = False
        self._clear_loading()
        self._info_lbl.setText(f"Error: {msg}")

    # ── DWG loading ──────────────────────────────────────────────────────────

    def _load_dwg(self, path: str):
        """Load a DWG file by converting to DXF via ODA File Converter."""
        from .dwg_converter import (
            find_oda_converter, convert_dwg_to_dxf,
            cleanup_converted_dxf, read_dxf, ODA_DOWNLOAD_URL,
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

        # ── Stage 2: Read converted DXF (bypasses _sanitize_dxf) ────────
        self._set_loading("Reading DXF\u2026")
        doc = read_dxf(dxf_path)
        if doc is None:
            self._clear_loading()
            QMessageBox.warning(self, "Read Error",
                                f"Could not read converted DXF:\n{dxf_path}")
            return
        self._clear_loading()

        # ── Stage 3: Hand off to unified DXF path ───────────────────────
        self._dwg_source_path = path
        self._converted_dxf_path = dxf_path
        self._show_entity_type_filter = True
        self._load_dxf(dxf_path, _doc=doc)
        self._file_type = "dwg"

        # Clean up temp DXFs (UNDERLAY_REF DXFs are preserved).
        # Safe because the ezdxf doc is in memory as self._doc.
        cleanup_converted_dxf(dxf_path)

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

        layout_note = getattr(self, "_selected_layout", "Model")
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

    # ── PDF loading ──────────────────────────────────────────────────────────

    def _seed_pdf_options_from_prefs(self):
        """Seed the PDF Options combos from the Preferences defaults (one-off)."""
        from PyQt6.QtCore import QSettings
        from .preferences_dialog import _QSETTINGS_ORG, _QSETTINGS_APP
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        dpi = s.value("import/pdf_dpi", 150, type=int)
        mode = s.value("import/pdf_import_mode", "auto", type=str)
        self._dpi_combo.blockSignals(True)
        self._mode_combo.blockSignals(True)
        self._dpi_combo.setCurrentText(str(dpi))
        self._mode_combo.setCurrentText(mode.capitalize())
        self._dpi_combo.blockSignals(False)
        self._mode_combo.blockSignals(False)

    def _load_pdf(self, path: str):
        self._file_type = "pdf"
        self._pdf_opts_grp.setVisible(True)
        self._seed_pdf_options_from_prefs()
        self._populate_scale_combo(is_pdf=True)   # offer architectural ratios

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
        from .pdf_import_worker import pdf_page_names
        self._pdf_page_names = pdf_page_names(path)
        if self._pdf_page_count > 1:
            from .pdf_import_worker import generate_pdf_thumbnails
            thumbs = generate_pdf_thumbnails(path, width=80)
            for page_idx, pixmap in thumbs:
                name = (self._pdf_page_names[page_idx]
                        if page_idx < len(self._pdf_page_names)
                        else f"Page {page_idx + 1}")
                item = QListWidgetItem(QIcon(pixmap), name)
                self._thumb_list.addItem(item)
            self._thumb_list.setVisible(True)
            if self._thumb_list.count() > 0:
                self._thumb_list.setCurrentRow(0)
        else:
            self._thumb_list.setVisible(False)

        self._pdf_page = 0
        self._load_pdf_page(path, 0)

    def _page_name(self, page: int) -> str:
        """Display name for a PDF page (label else 'Page N')."""
        names = getattr(self, "_pdf_page_names", [])
        return names[page] if 0 <= page < len(names) else f"Page {page + 1}"

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
                f"{self._page_name(page)} — raster at {dpi} DPI.")
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
                    f"{self._page_name(page)} — {n} vector entities from "
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
        self._update_scale_readout()
        self._update_status()

    def _show_raster_preview(self, path: str, page: int, dpi: int = 150):
        """Show a raster rendering of the PDF page as a fallback preview."""
        self._preview_scene.clear()
        self._base_marker = None
        self._preview_geom_group = None  # destroyed by clear()
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
                item.setCacheMode(
                    QGraphicsItem.CacheMode.DeviceCoordinateCache)
                self._preview_scene.addItem(item)
                geom_items.append(item)
            # Text: filled, no outline
            tp = text_paths[pid]
            if not tp.isEmpty():
                item = QGraphicsPathItem(tp)
                item.setPen(QPen(Qt.PenStyle.NoPen))
                item.setBrush(QBrush(pen.color()))
                item.setCacheMode(
                    QGraphicsItem.CacheMode.DeviceCoordinateCache)
                self._preview_scene.addItem(item)
                geom_items.append(item)

        # Group geometry items and apply rotation around the base point
        rotation = self._get_rotation()
        if geom_items:
            group = self._preview_scene.createItemGroup(geom_items)
            group.setData(0, "DXF Underlay")  # snap engine recognises tagged groups
            bx = self._base_x_edit.value_mm() if hasattr(self, "_base_x_edit") else 0.0
            by = self._base_y_edit.value_mm() if hasattr(self, "_base_y_edit") else 0.0
            group.setTransformOriginPoint(bx, by)
            group.setRotation(rotation)
            # Lazy snap index instead of one invisible QGraphicsItem per
            # geometry (~293K items on large drawings, rebuilt on every
            # layer toggle).  Geometry dicts are in group-local coords;
            # the engine maps queries through the group's sceneTransform,
            # so rotation needs no index rebuild.  Empty hidden-layers
            # list = snap on all layers, matching the old invisible-item
            # behaviour.  Rebuilt only when _all_geoms is a new list.
            if (self._snap_index is None
                    or self._snap_index_src is not self._all_geoms):
                self._snap_index = UnderlaySnapIndex(self._all_geoms, [])
                self._snap_index_src = self._all_geoms
            group.setData(4, self._snap_index)
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
                # DPI-independent + fractional-exact size: render at a fixed
                # pixel em, then scale by size/BASE. (Point size would inflate by
                # 96/72 + HiDPI; rounding a pixel size loses sub-point accuracy.)
                size = max(0.5, float(g.get("size", 6)))
                _BASE = 100.0
                f = QFont("Arial")
                f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                f.setPixelSize(int(_BASE))
                sc = size / _BASE
                tx, ty = g["x"], g["y"]
                ha = g.get("halign", 0)
                va = g.get("valign", 3)
                twidth = g.get("twidth")
                lines = txt.split("\n")
                single = len(lines) == 1
                fm = QFontMetricsF(f)
                line_h = fm.height() * sc
                total_h = line_h * len(lines)
                # Vertical anchor for the text block
                if va == 0:       # top
                    base_y = ty + fm.ascent() * sc
                elif va == 1:     # middle
                    base_y = ty + fm.ascent() * sc - total_h / 2
                elif va == 2:     # bottom
                    base_y = ty + fm.ascent() * sc - total_h
                else:             # baseline (PDF spans: y == span origin)
                    base_y = ty
                for i, line in enumerate(lines):
                    if not line.strip():
                        continue
                    nat_w = fm.horizontalAdvance(line)   # at BASE px
                    # fit x to the source span width when known, else scale = size
                    sx = (twidth / nat_w) if (twidth and nat_w > 0 and single) else sc
                    final_w = nat_w * sx
                    lx = tx
                    if ha == 1:   # center
                        lx -= final_w / 2
                    elif ha == 2: # right
                        lx -= final_w
                    tmp = QPainterPath()
                    tmp.addText(0.0, 0.0, f, line)
                    tr = QTransform()
                    tr.translate(lx, base_y + i * line_h)
                    tr.scale(sx, sc)
                    path.addPath(tr.map(tmp))

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

    def _populate_scale_combo(self, is_pdf: bool):
        """(Re)fill the scale combo, storing each preset's scale in itemData.

        Architectural/engineering ratios are **PDF-only** — their points->mm
        math is verified; DXF/DWG unit support is a follow-up.
        """
        combo = self._scale_combo
        combo.blockSignals(True)
        combo.clear()
        for label, val in self._SCALE_OPTIONS:
            combo.addItem(label, val)          # val=None for "Custom…"
        if is_pdf:
            combo.insertSeparator(combo.count())
            for label, val in _ARCH_SCALES:
                combo.addItem(label, val)
            combo.insertSeparator(combo.count())
            for label, val in _ENG_SCALES:
                combo.addItem(label, val)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _on_scale_combo_changed(self, idx: int):
        is_custom = self._scale_combo.currentData() is None   # "Custom…"
        self._custom_scale_edit.setVisible(is_custom)
        self._calibration_lbl.setVisible(
            is_custom and bool(self._calibration_lbl.text()))
        self._update_scale_readout()
        self._update_scale_ratio_label()

    def _on_custom_scale_edited(self, *_):
        self._update_scale_ratio_label()
        self._update_scale_readout()

    def _update_scale_ratio_label(self):
        """For a PDF Custom/calibrated factor, show the equivalent drawing ratio."""
        lbl = getattr(self, "_scale_ratio_lbl", None)
        if lbl is None:
            return
        is_pdf = getattr(self, "_file_type", "") == "pdf"
        # Named presets already read as a ratio in the combo; annotate Custom only.
        if not is_pdf or self._scale_combo.currentData() is not None:
            lbl.setVisible(False)
            return
        txt = pdf_scale_ratio_text(self._current_scale())
        if txt:
            lbl.setText(f"=  {txt}")
            lbl.setVisible(True)
        else:
            lbl.setVisible(False)

    def _get_custom_scale(self) -> float:
        try:
            return float(self._custom_scale_edit.text())
        except (ValueError, AttributeError):
            return 1.0

    def _current_scale(self) -> float:
        data = self._scale_combo.currentData()
        if data is not None:
            return float(data)
        return self._get_custom_scale()   # "Custom…"

    def _update_scale_readout(self):
        """Show the real-world size of the loaded geometry at the current scale."""
        lbl = getattr(self, "_scale_readout_lbl", None)
        if lbl is None:
            return
        geoms = getattr(self, "_all_geoms", None)
        if not geoms or self._scale_combo.currentData() is None:
            lbl.setVisible(False)
            return
        xs, ys = [], []
        for g in geoms:
            k = g.get("kind")
            if k == "line":
                xs += [g["x1"], g["x2"]]; ys += [g["y1"], g["y2"]]
            elif k == "path_points":
                for p in g["points"]:
                    xs.append(p[0]); ys.append(p[1])
            elif k == "circle":
                xs += [g["x"], g["x"] + g["w"]]; ys += [g["y"], g["y"] + g["h"]]
        if not xs or not ys:
            lbl.setVisible(False)
            return
        s = self._current_scale()
        w_mm = (max(xs) - min(xs)) * s
        h_mm = (max(ys) - min(ys)) * s
        sm = getattr(self, "_sm", None)
        if sm is not None:
            lbl.setText(f"≈ {sm.format_length(w_mm)} × {sm.format_length(h_mm)} real")
        else:
            lbl.setText(f"≈ {w_mm:.0f} × {h_mm:.0f} mm real")
        lbl.setVisible(True)

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
        # Constant-size filled dot marking the diamond's exact centre, so the
        # picked point is unambiguous regardless of zoom.
        dot = QGraphicsEllipseItem(-3, -3, 6, 6)
        dot.setPos(pt)
        dot.setBrush(QBrush(QColor("#00cc44")))
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        dot.setZValue(601)
        self._preview_scene.addItem(dot)
        self._pick_markers.append(dot)
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
                    if self._file_type == "pdf":
                        ratio = pdf_scale_ratio_text(factor)
                        self._calibration_lbl.setText(
                            f"{px_dist:.1f} pt = {display}   ({ratio})")
                    else:
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
        """Apply rotation to the existing preview group — no rebuild.

        Rotation is a group transform; the batched paths and the snap
        index both live in group-local coordinates, so neither needs
        rebuilding (a full rebuild froze the dialog for seconds on
        large drawings).
        """
        group = self._preview_geom_group
        if group is None:
            return
        try:
            bx = self._base_x_edit.value_mm()
            by = self._base_y_edit.value_mm()
            group.setTransformOriginPoint(bx, by)
            group.setRotation(self._get_rotation())
        except RuntimeError:
            # C++ object deleted (scene was cleared) — rebuild from data
            self._preview_geom_group = None
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

    def _update_base_enabled(self, *_):
        """Grey out the base-point inputs while 'Insert at origin' is active —
        the X/Y base point is ignored in that mode, so editable fields would
        be misleading."""
        at_origin = self._origin_cb.isChecked()
        for w in getattr(self, "_base_inputs", []):
            w.setEnabled(not at_origin)

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
        if self._extracting:
            return  # half-built _all_geoms — ignore queued Import clicks
        if not self._all_geoms and self._has_vectors:
            QMessageBox.warning(self, "Nothing to import",
                                "Load a file before importing.")
            return
        self.accept()

    def done(self, result: int):
        """Release heavy references when the dialog closes.

        The dialog is parented to the main window, so it outlives close
        until deleteLater(); dropping the ezdxf document and preview
        scene items (~293K invisible snap items on large drawings) here
        frees the bulk of the memory immediately.  ``get_import_params()``
        — called after ``exec()`` returns — reads only widgets and
        ``_all_geoms``, both of which stay valid.
        """
        # Detach in-flight workers: cancel extraction, orphan the read
        # (readfile is not interruptible).  Slots guard on the worker
        # attributes being None, so late signals are discarded; the
        # _LIVE_WORKERS keepalive lets the threads finish safely.
        w = self._extract_worker
        if w is not None:
            self._extract_worker = None
            if hasattr(w, "cancel"):
                w.cancel()
        self._read_worker = None
        self._extracting = False

        self._doc = None
        self._snap_index = None
        self._snap_index_src = None
        self._layout_cache.clear()
        self._preview_geom_group = None
        self._preview_scene.clear()
        super().done(result)

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

        # Compute import bounds when area selection was used
        if self._selected_indices is not None and geoms:
            from .dwg_converter import compute_geom_bounds
            p.import_bounds = compute_geom_bounds(geoms)

        # Preserve original .dwg path for DWG files
        if self._file_type == "dwg":
            p.file_path = getattr(self, "_dwg_source_path", p.file_path)

        # Include selected layout for any file type (empty string = Model)
        selected = getattr(self, "_selected_layout", "")
        p.layout = "" if selected == "Model" else selected

        # Placement levels + scale provenance (defensive: the Placement
        # multi-select / verified-state land in later redesign tasks).
        levels_getter = getattr(self, "_selected_levels", None)
        p.levels = list(levels_getter()) if callable(levels_getter) else []
        p.scale_verified = bool(getattr(self, "_scale_verified", False))

        self._save_settings()
        return p


# ── Backwards compat alias ───────────────────────────────────────────────────
DxfPreviewDialog = UnderlayImportDialog
