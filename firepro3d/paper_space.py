"""
paper_space.py
==============
Sprint 4B — Paper Space layout with title block and live model-space viewport.

Classes
-------
TitleBlockItem   — QGraphicsItem that draws a professional engineering title block
PaperViewport    — QGraphicsRectItem that live-renders Model_Space content
PaperScene       — QGraphicsScene representing one paper layout
PaperSpaceWidget — QWidget wrapping a view of PaperScene + paper-size/title controls
"""

from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem, QGraphicsObject,
    QGraphicsSceneContextMenuEvent, QComboBox, QPushButton, QLabel,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QGraphicsDropShadowEffect,
    QMenu,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF, QSize, pyqtSignal
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QFont, QFontMetricsF, QTransform, QPixmap,
    QPainterPath,
)
try:
    from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

# Base directory for default title block PDFs
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ─────────────────────────────────────────────────────────────────────────────
# Paper sizes (width × height in mm, portrait orientation)
# ─────────────────────────────────────────────────────────────────────────────

PAPER_SIZES: dict[str, tuple[float, float]] = {
    # ISO A-series (portrait: width × height in mm)
    "A4":     (210.0,  297.0),
    "A3":     (297.0,  420.0),
    "A2":     (420.0,  594.0),
    "A1":     (594.0,  841.0),
    "A0":     (841.0, 1189.0),
    # ANSI (landscape: width × height in mm)
    "ANSI B": (431.8,  279.4),   # 17" × 11" landscape
    "ANSI D": (863.6,  558.8),   # 34" × 22" landscape
    # Legacy
    "Letter": (215.9,  279.4),
    "D-size": (558.8,  863.6),
}

# Map paper size name → DXF title block file (preferred, vector)
TITLE_BLOCK_DXFS: dict[str, str] = {
    "ANSI B": os.path.join(_BASE_DIR, "default titleblocks", "CEL Titleblock (ANSI B) R0.dxf"),
    "ANSI D": os.path.join(_BASE_DIR, "default titleblocks", "CEL Titleblock (ANSI D) R0.dxf"),
}

# Map paper size name → PDF title block file (raster fallback)
TITLE_BLOCK_PDFS: dict[str, str] = {
    "ANSI B": os.path.join(_BASE_DIR, "default titleblocks", "CEL Titleblock (ANSI B) R0.pdf"),
    "ANSI D": os.path.join(_BASE_DIR, "default titleblocks", "CEL Titleblock (ANSI D) R0.pdf"),
}

# Margins (mm)
MARGIN        = 10.0    # outer border
INNER_MARGIN  = 5.0     # inside border to content
TITLE_H       = 65.0    # title block height


# ─────────────────────────────────────────────────────────────────────────────
# Scale helpers
# ─────────────────────────────────────────────────────────────────────────────

SCALE_PRESETS: list[tuple[str, float]] = [
    ("1:200", 1 / 200), ("1:100", 1 / 100), ("1:75", 1 / 75),
    ("1:50", 1 / 50), ("1:25", 1 / 25), ("1:20", 1 / 20),
    ("1:10", 1 / 10), ("1:5", 1 / 5), ("1:1", 1.0),
    ('1/8"=1\'-0"', 1 / 96), ('3/16"=1\'-0"', 3 / 192),
    ('1/4"=1\'-0"', 1 / 48), ('3/8"=1\'-0"', 3 / 96),
    ('1/2"=1\'-0"', 1 / 24), ('3/4"=1\'-0"', 3 / 36),
    ('1"=1\'-0"', 1 / 12), ('1-1/2"=1\'-0"', 1.5 / 12),
    ('3"=1\'-0"', 3 / 12),
]
_PRESET_MAP: dict[str, float] = {label: ratio for label, ratio in SCALE_PRESETS}
_RE_METRIC = re.compile(r"^1\s*:\s*(\d+(?:\.\d+)?)$")
_RE_IMPERIAL = re.compile(r'^(\d+(?:-\d+/\d+|\.\d+)?(?:/\d+)?)\s*"\s*=\s*1\'-0"$')


def _parse_imperial_inches(s: str) -> float:
    if "-" in s:
        whole, frac = s.split("-", 1)
        return float(whole) + _parse_imperial_inches(frac)
    if "/" in s:
        num, den = s.split("/", 1)
        return float(num) / float(den)
    return float(s)


def scale_to_float(s: str) -> float:
    """Parse a scale string and return the corresponding ratio (model/paper).

    Args:
        s: A scale string such as ``"1:100"``, ``'1/4"=1\\'-0"'``, or
           ``"1:125"`` (custom metric).

    Returns:
        The dimensionless scale ratio (e.g. 0.01 for 1:100).

    Raises:
        ValueError: If *s* cannot be recognised as a valid scale string.
    """
    s = s.strip()
    if s in _PRESET_MAP:
        return _PRESET_MAP[s]
    m = _RE_METRIC.match(s)
    if m:
        return 1.0 / float(m.group(1))
    m = _RE_IMPERIAL.match(s)
    if m:
        return _parse_imperial_inches(m.group(1)) / 12.0
    raise ValueError(f"Cannot parse scale string: {s!r}")


def float_to_scale_str(ratio: float) -> str:
    """Return the human-readable scale label closest to *ratio*.

    Prefers a known preset label when the ratio is within 0.1 % of a preset;
    otherwise falls back to a ``"1:N"`` metric string.

    Args:
        ratio: Dimensionless scale ratio (model units / paper units).

    Returns:
        A scale string such as ``"1:100"`` or ``'1/4"=1\\'-0"'``.
    """
    for label, preset_ratio in SCALE_PRESETS:
        if abs(ratio - preset_ratio) < preset_ratio * 0.001:
            return label
    n = round(1.0 / ratio)
    return f"1:{n}"


def _compute_scale_field(sheet: "Sheet") -> str:
    """Return the scale label to display in the title block for *sheet*.

    Args:
        sheet: A ``Sheet`` instance whose ``sheet_views`` attribute holds the
            active viewports.

    Returns:
        A scale string (e.g. ``"1:100"``), ``"AS NOTED"`` when viewports use
        different scales, or an empty string when there are no viewports.
    """
    if not sheet.sheet_views:
        return ""
    scales = {sv.scale for sv in sheet.sheet_views}
    if len(scales) == 1:
        return float_to_scale_str(next(iter(scales)))
    return "AS NOTED"


# ─────────────────────────────────────────────────────────────────────────────
# Sheet data model
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TITLE_BLOCK_FIELDS: dict[str, str] = {
    "Company": "Celerity Engineering Limited",
    "Project": "",
    "Title": "Fire Suppression Layout",
    "Scale": "1:100",
    "Drawing No": "FP-001",
    "Rev": "A",
    "Date": datetime.date.today().strftime("%d %b %Y"),
    "Drawn By": "",
    "Checked By": "",
}


@dataclass
class SheetViewData:
    """Data for one viewport placed on a sheet."""
    source_view_type: str
    source_view_name: str
    title: str
    scale: float
    x: float
    y: float
    w: float
    h: float

    def to_dict(self) -> dict:
        return {
            "source_view_type": self.source_view_type,
            "source_view_name": self.source_view_name,
            "title": self.title,
            "scale": self.scale,
            "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SheetViewData":
        return cls(
            source_view_type=d["source_view_type"],
            source_view_name=d["source_view_name"],
            title=d["title"],
            scale=d["scale"],
            x=d["x"], y=d["y"],
            w=d["w"], h=d["h"],
        )


@dataclass
class Sheet:
    """Data model for one paper sheet."""
    number: str
    name: str
    paper_size: str
    title_block_fields: dict[str, str]
    sheet_views: list[SheetViewData]

    @classmethod
    def create_default(cls) -> "Sheet":
        return cls(
            number="FP-1.0",
            name="Fire Suppression Layout",
            paper_size="ANSI D",
            title_block_fields=dict(DEFAULT_TITLE_BLOCK_FIELDS),
            sheet_views=[],
        )

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "paper_size": self.paper_size,
            "title_block_fields": dict(self.title_block_fields),
            "sheet_views": [sv.to_dict() for sv in self.sheet_views],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Sheet":
        return cls(
            number=d["number"],
            name=d["name"],
            paper_size=d["paper_size"],
            title_block_fields=d.get("title_block_fields",
                                     dict(DEFAULT_TITLE_BLOCK_FIELDS)),
            sheet_views=[SheetViewData.from_dict(sv)
                         for sv in d.get("sheet_views", [])],
        )


# ─────────────────────────────────────────────────────────────────────────────
# ViewResolver — bridges source view managers to (scene, source_rect) pairs
# ─────────────────────────────────────────────────────────────────────────────

class ViewResolver:
    """Resolves source view type + name to (QGraphicsScene, QRectF).

    Single bridge object decoupling SheetViewport from individual view managers.
    """

    def __init__(self, model_scene, plan_view_manager,
                 detail_manager, elevation_manager):
        self._scene = model_scene
        self._pvm = plan_view_manager
        self._dm = detail_manager
        self._em = elevation_manager

    def resolve(self, view_type: str, view_name: str
                ) -> "tuple[QGraphicsScene, QRectF] | None":
        """Return (source_scene, source_rect) or None if not found."""
        if view_type == "plan":
            return self._resolve_plan(view_name)
        if view_type == "detail":
            return self._resolve_detail(view_name)
        if view_type == "elevation":
            return self._resolve_elevation(view_name)
        return None

    def _resolve_plan(self, name: str):
        pv = self._pvm.get(name) if hasattr(self._pvm, 'get') else self._pvm._views.get(name)
        if pv is None:
            return None
        rect = self._scene.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            rect = QRectF(0, 0, 1000, 1000)
        return (self._scene, rect)

    def _resolve_detail(self, name: str):
        marker = self._dm.get_marker(name)
        if marker is None:
            return None
        return (self._scene, marker.crop_rect)

    def _resolve_elevation(self, name: str):
        direction = name.lower()
        scene = self._em.get_scene(direction)
        if scene is None:
            return None
        rect = scene.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            rect = QRectF(0, 0, 1000, 1000)
        return (scene, rect)

    def available_views(self) -> dict[str, list[str]]:
        """Return available views grouped by type."""
        result: dict[str, list[str]] = {}
        plan_names = list(self._pvm._views.keys())
        if plan_names:
            result["Floor Plans"] = plan_names
        detail_names = self._dm.detail_names
        if detail_names:
            result["Details"] = detail_names
        directions = ["North", "South", "East", "West"]
        result["Elevations"] = directions
        return result


# ─────────────────────────────────────────────────────────────────────────────
# SheetViewport — live viewport on a paper sheet
# ─────────────────────────────────────────────────────────────────────────────

_GRIP_SIZE = 4.0
_MIN_VIEWPORT_SIZE = 20.0


class SheetViewport(QGraphicsObject):
    """A viewport on a paper sheet that renders a source view at scale."""

    navigate_requested = pyqtSignal(str, str)
    delete_requested = pyqtSignal(object)
    properties_requested = pyqtSignal(object)

    def __init__(self, data: SheetViewData, resolver: ViewResolver, parent=None):
        super().__init__(parent)
        self._data = data
        self._resolver = resolver
        self._dirty = True
        self._cache: QPixmap | None = None
        self._placeholder = False
        self._resizing = False
        self._resize_handle: int = -1
        self._resize_origin = QPointF()

        self.setPos(data.x, data.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(5)

        self._source_scene = None
        self._source_rect = QRectF()
        self._reconnect_source()

    @property
    def data(self) -> SheetViewData:
        return self._data

    def _reconnect_source(self):
        if self._source_scene is not None:
            try:
                self._source_scene.changed.disconnect(self._on_source_changed)
            except (TypeError, RuntimeError):
                pass
        result = self._resolver.resolve(self._data.source_view_type, self._data.source_view_name)
        if result is None:
            self._placeholder = True
            self._source_scene = None
            self._source_rect = QRectF()
            return
        self._placeholder = False
        self._source_scene, self._source_rect = result
        self._source_scene.changed.connect(self._on_source_changed)

    def _on_source_changed(self, rects=None):
        self.mark_dirty()

    def mark_dirty(self):
        self._dirty = True
        self._cache = None
        self.update()

    def sync_data_from_item(self):
        pos = self.pos()
        self._data.x = pos.x()
        self._data.y = pos.y()

    def boundingRect(self) -> QRectF:
        margin = _GRIP_SIZE if self.isSelected() else 0
        return QRectF(-margin, -margin, self._data.w + 2 * margin, self._data.h + 2 * margin)

    def paint(self, painter: QPainter, option, widget=None):
        w, h = self._data.w, self._data.h
        vp_rect = QRectF(0, 0, w, h)
        if self._placeholder:
            painter.fillRect(vp_rect, QColor("#e0e0e0"))
            painter.setPen(QPen(QColor("#888888"), 0.5))
            painter.drawRect(vp_rect)
            f = QFont("Arial", 3)
            painter.setFont(f)
            painter.setPen(Qt.GlobalColor.darkRed)
            painter.drawText(vp_rect, Qt.AlignmentFlag.AlignCenter,
                             f"View not found:\n{self._data.source_view_name}")
            return
        if self._dirty or self._cache is None:
            self._render_to_cache()
        if self._cache and not self._cache.isNull():
            painter.drawPixmap(vp_rect.toRect(), self._cache)
        else:
            painter.fillRect(vp_rect, Qt.GlobalColor.white)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.isSelected():
            painter.setPen(QPen(QColor("#0055ff"), 0.8, Qt.PenStyle.DashLine))
        else:
            painter.setPen(QPen(Qt.GlobalColor.black, 0.3))
        painter.drawRect(vp_rect)
        if self.isSelected():
            self._draw_grips(painter)

    def _render_to_cache(self):
        if self._source_scene is None:
            self._cache = None
            self._dirty = False
            return
        w, h = self._data.w, self._data.h
        dpr = 2
        px_w, px_h = int(w * dpr), int(h * dpr)
        if px_w <= 0 or px_h <= 0:
            self._cache = None
            self._dirty = False
            return
        pixmap = QPixmap(px_w, px_h)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.white)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = QRectF(0, 0, w, h)
        self._source_scene.render(p, target, self._source_rect)
        p.end()
        self._cache = pixmap
        self._dirty = False

    def _grip_rects(self) -> list[QRectF]:
        w, h = self._data.w, self._data.h
        g = _GRIP_SIZE
        hg = g / 2
        return [
            QRectF(-hg, -hg, g, g),
            QRectF(w / 2 - hg, -hg, g, g),
            QRectF(w - hg, -hg, g, g),
            QRectF(-hg, h / 2 - hg, g, g),
            QRectF(w - hg, h / 2 - hg, g, g),
            QRectF(-hg, h - hg, g, g),
            QRectF(w / 2 - hg, h - hg, g, g),
            QRectF(w - hg, h - hg, g, g),
        ]

    def _draw_grips(self, painter: QPainter):
        painter.setPen(QPen(QColor("#0055ff"), 0.3))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        for r in self._grip_rects():
            painter.drawRect(r)

    def _hit_grip(self, pos: QPointF) -> int:
        for i, r in enumerate(self._grip_rects()):
            if r.contains(pos):
                return i
        return -1

    def mousePressEvent(self, event):
        if self.isSelected() and event.button() == Qt.MouseButton.LeftButton:
            grip = self._hit_grip(event.pos())
            if grip >= 0:
                self._resizing = True
                self._resize_handle = grip
                self._resize_origin = event.pos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.pos() - self._resize_origin
            self._apply_grip_resize(self._resize_handle, delta)
            self._resize_origin = event.pos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_handle = -1
            self.sync_data_from_item()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_grip_resize(self, handle: int, delta: QPointF):
        dx, dy = delta.x(), delta.y()
        x, y = self._data.x, self._data.y
        w, h = self._data.w, self._data.h
        if handle in (0, 3, 5):
            new_w = max(w - dx, _MIN_VIEWPORT_SIZE)
            actual_dx = w - new_w
            self._data.x = x + actual_dx
            self._data.w = new_w
        if handle in (2, 4, 7):
            self._data.w = max(w + dx, _MIN_VIEWPORT_SIZE)
        if handle in (0, 1, 2):
            new_h = max(h - dy, _MIN_VIEWPORT_SIZE)
            actual_dy = h - new_h
            self._data.y = y + actual_dy
            self._data.h = new_h
        if handle in (5, 6, 7):
            self._data.h = max(h + dy, _MIN_VIEWPORT_SIZE)
        self.setPos(self._data.x, self._data.y)
        self.mark_dirty()
        self.prepareGeometryChange()

    def mouseDoubleClickEvent(self, event):
        self.navigate_requested.emit(self._data.source_view_type, self._data.source_view_name)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent):
        menu = QMenu()
        props_action = menu.addAction("Properties...")
        goto_action = menu.addAction("Go to View")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")
        action = menu.exec(event.screenPos())
        if action == props_action:
            self.properties_requested.emit(self)
        elif action == goto_action:
            self.navigate_requested.emit(self._data.source_view_type, self._data.source_view_name)
        elif action == delete_action:
            self.delete_requested.emit(self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.sync_data_from_item()
        return super().itemChange(change, value)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit(self)
        else:
            super().keyPressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# PDF-based title block background
# ─────────────────────────────────────────────────────────────────────────────

def _render_titleblock_pdf(pdf_path: str, paper_w_mm: float, paper_h_mm: float,
                            render_dpi: int = 150) -> "QPixmap | None":
    """
    Render page 0 of *pdf_path* to a QPixmap scaled to exactly
    paper_w_mm × paper_h_mm scene units (1 unit = 1 mm).

    Returns None if the PDF cannot be loaded or QPdf is unavailable.
    """
    if not _PDF_AVAILABLE:
        return None
    if not os.path.isfile(pdf_path):
        return None
    try:
        doc = QPdfDocument(None)
        status = doc.load(pdf_path)
        # PyQt6 versions differ: load() may return Error enum, Status enum, or int.
        # Accept 0, Error.NoError, or any "no error" variant; fall through to pageCount check.
        try:
            _no_err = getattr(QPdfDocument, "Error", QPdfDocument.Status).NoError
            if status != _no_err and status != 0:
                return None
        except (TypeError, AttributeError):
            pass  # fallback: just check pageCount below
        if doc.pageCount() == 0:
            return None
        # Native page size in points (1/72 inch)
        page_size_pt = doc.pagePointSize(0)
        if not page_size_pt.isValid() or page_size_pt.width() == 0:
            return None
        # Convert pts → inches → px at render_dpi
        w_px = int(page_size_pt.width()  / 72.0 * render_dpi)
        h_px = int(page_size_pt.height() / 72.0 * render_dpi)
        options = QPdfDocumentRenderOptions()
        image = doc.render(0, QSize(w_px, h_px), options)
        if image.isNull():
            return None
        pixmap = QPixmap.fromImage(image)
        return pixmap
    except Exception as e:
        pass  # render failed — caller checks for None
        return None


class TitleBlockPdfItem(QGraphicsPixmapItem):
    """
    Renders a PDF title block as a full-paper background pixmap.

    The pixmap is scaled (via QTransform) so it exactly covers the paper
    rectangle (0, 0, paper_w_mm, paper_h_mm) in scene coordinates.
    """

    def __init__(self, pdf_path: str, paper_w: float, paper_h: float, parent=None):
        super().__init__(parent)
        self._paper_w = paper_w
        self._paper_h = paper_h
        self.setZValue(0.5)   # above paper background, below viewport/title items
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        pixmap = _render_titleblock_pdf(pdf_path, paper_w, paper_h)
        if pixmap and not pixmap.isNull():
            self.setPixmap(pixmap)
            # Scale to paper dimensions
            sx = paper_w / pixmap.width()
            sy = paper_h / pixmap.height()
            self.setTransform(QTransform().scale(sx, sy))
            self.setPos(0, 0)
        else:
            pass  # pixmap failed to render — item will be blank


# ─────────────────────────────────────────────────────────────────────────────
# DXF-based title block (vector quality)
# ─────────────────────────────────────────────────────────────────────────────

class TitleBlockDxfItem(QGraphicsItem):
    """
    Renders a DXF title block as crisp vector geometry.

    The DXF is parsed once at construction; all SPLINE and LWPOLYLINE
    entities are converted to QPainterPaths and painted directly.
    DXF coordinates are in mm and Y-flipped to match the Qt scene.
    """

    def __init__(self, dxf_path: str, paper_w: float, paper_h: float, parent=None):
        super().__init__(parent)
        self._paper_w = paper_w
        self._paper_h = paper_h
        self._paths: list[QPainterPath] = []
        self._ok = False
        self.setZValue(0.5)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        try:
            self._parse_dxf(dxf_path)
            self._ok = True
        except Exception:
            pass  # leave _paths empty; caller checks is_valid()

    # ── public ────────────────────────────────────────────────────────────
    def is_valid(self) -> bool:
        return self._ok and len(self._paths) > 0

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._paper_w, self._paper_h)

    def paint(self, painter: QPainter, option, widget=None):
        pen = QPen(Qt.GlobalColor.black, 0)        # cosmetic (hairline)
        pen.setCosmetic(False)
        pen.setWidthF(0.25)                         # 0.25 mm line weight
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for path in self._paths:
            painter.drawPath(path)

    # ── DXF parsing ──────────────────────────────────────────────────────
    def _parse_dxf(self, dxf_path: str):
        import ezdxf

        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        paper_h = self._paper_h

        for entity in msp:
            etype = entity.dxftype()
            try:
                if etype == "LWPOLYLINE":
                    self._convert_lwpolyline(entity, paper_h)
                elif etype == "SPLINE":
                    self._convert_spline(entity, paper_h)
                elif etype == "LINE":
                    self._convert_line(entity, paper_h)
                elif etype == "CIRCLE":
                    self._convert_circle(entity, paper_h)
                elif etype == "ARC":
                    self._convert_arc(entity, paper_h)
            except Exception:
                pass  # skip unparseable entities

    def _convert_lwpolyline(self, entity, paper_h: float):
        points = list(entity.get_points(format="xyb"))
        if len(points) < 2:
            return
        path = QPainterPath()
        # First point
        x0, y0, _ = points[0]
        path.moveTo(x0, paper_h - y0)
        for i in range(1, len(points)):
            x, y, _ = points[i]
            path.lineTo(x, paper_h - y)
        if entity.closed:
            path.closeSubpath()
        self._paths.append(path)

    def _convert_spline(self, entity, paper_h: float):
        # Flatten spline to polyline points using ezdxf
        try:
            pts = list(entity.flattening(0.1))  # tolerance 0.1 mm
        except Exception:
            pts = list(entity.control_points)
        if len(pts) < 2:
            return
        path = QPainterPath()
        path.moveTo(pts[0].x, paper_h - pts[0].y)
        for pt in pts[1:]:
            path.lineTo(pt.x, paper_h - pt.y)
        self._paths.append(path)

    def _convert_line(self, entity, paper_h: float):
        s = entity.dxf.start
        e = entity.dxf.end
        path = QPainterPath()
        path.moveTo(s.x, paper_h - s.y)
        path.lineTo(e.x, paper_h - e.y)
        self._paths.append(path)

    def _convert_circle(self, entity, paper_h: float):
        c = entity.dxf.center
        r = entity.dxf.radius
        path = QPainterPath()
        path.addEllipse(QPointF(c.x, paper_h - c.y), r, r)
        self._paths.append(path)

    def _convert_arc(self, entity, paper_h: float):
        import math
        c = entity.dxf.center
        r = entity.dxf.radius
        # DXF angles are counter-clockwise from +X in degrees
        # Qt arcs: addArc expects a bounding rect and angles in 1/16th degree
        # But it's easier to flatten to points
        start_deg = entity.dxf.start_angle
        end_deg = entity.dxf.end_angle
        if end_deg < start_deg:
            end_deg += 360.0
        span = end_deg - start_deg
        n_seg = max(int(span / 5), 4)
        path = QPainterPath()
        for i in range(n_seg + 1):
            angle = math.radians(start_deg + span * i / n_seg)
            x = c.x + r * math.cos(angle)
            y = paper_h - (c.y + r * math.sin(angle))
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        self._paths.append(path)


# ─────────────────────────────────────────────────────────────────────────────
# Programmatic title block (fallback / ISO sizes)
# ─────────────────────────────────────────────────────────────────────────────

class TitleBlockItem(QGraphicsItem):
    """
    Engineering title block rendered at the bottom of the sheet.

    The block spans the full inner width (inside the drawing border) and is
    TITLE_H mm tall.  All sizes are in scene mm units.
    """

    def __init__(self, sheet_w: float, sheet_h: float, parent=None):
        super().__init__(parent)
        self._sheet_w = sheet_w
        self._sheet_h = sheet_h
        self.setZValue(10)

        self.fields: dict[str, str] = {
            "Company":      "Celerity Engineering Limited",
            "Project":      "",
            "Title":        "Fire Suppression Layout",
            "Scale":        "1:100",
            "Drawing No":   "FP-001",
            "Rev":          "A",
            "Date":         datetime.date.today().strftime("%d %b %Y"),
            "Drawn By":     "",
            "Checked By":   "",
        }

    # -- Geometry helpers

    def _inner_x(self) -> float:
        return MARGIN + INNER_MARGIN

    def _block_y(self) -> float:
        return self._sheet_h - MARGIN - INNER_MARGIN - TITLE_H

    def _block_w(self) -> float:
        return self._sheet_w - 2 * (MARGIN + INNER_MARGIN)

    def boundingRect(self) -> QRectF:
        return QRectF(
            self._inner_x(), self._block_y(),
            self._block_w(), TITLE_H,
        )

    # -- Paint

    def paint(self, painter: QPainter, option, widget=None):
        x  = self._inner_x()
        y  = self._block_y()
        w  = self._block_w()
        h  = TITLE_H

        pen_thick = QPen(Qt.GlobalColor.black, 0.5)
        pen_thin  = QPen(Qt.GlobalColor.black, 0.25)
        white     = QBrush(Qt.GlobalColor.white)

        painter.setBrush(white)
        painter.setPen(pen_thick)
        painter.drawRect(QRectF(x, y, w, h))

        # ── Column layout ────────────────────────────────────────────────────
        #  col0: Company  (30% width)
        #  col1: Project / Title  (40% width)
        #  col2: Scale / DRG No  (15% width)
        #  col3: Rev / Date  (15% width)

        c0 = x
        c1 = x + w * 0.30
        c2 = x + w * 0.70
        c3 = x + w * 0.85

        # Row dividers
        r0 = y
        r1 = y + h * 0.33
        r2 = y + h * 0.66
        r3 = y + h

        painter.setPen(pen_thin)

        # Vertical dividers
        for cx in (c1, c2, c3):
            painter.drawLine(QPointF(cx, r0), QPointF(cx, r3))

        # Horizontal dividers (col1+)
        for rx in (r1, r2):
            painter.drawLine(QPointF(c1, rx), QPointF(x + w, rx))

        # ── Text ─────────────────────────────────────────────────────────────

        def label(rect, text, bold=False, big=False):
            f = QFont("Arial")
            f.setPointSizeF(2.5 if big else 2.0)
            f.setBold(bold)
            painter.setFont(f)
            painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter |
                             Qt.TextFlag.TextWordWrap, text)

        def small_label(rect, caption, value):
            """Two-line cell: small caption + larger value."""
            cap_rect = QRectF(rect.x() + 1, rect.y() + 0.5,
                              rect.width() - 2, rect.height() * 0.40)
            val_rect = QRectF(rect.x() + 1,
                              rect.y() + rect.height() * 0.40,
                              rect.width() - 2, rect.height() * 0.55)
            f = QFont("Arial"); f.setPointSizeF(1.6)
            painter.setFont(f)
            painter.setPen(QPen(QColor("#666666"), 0.1))
            painter.drawText(cap_rect, Qt.AlignmentFlag.AlignLeft |
                             Qt.AlignmentFlag.AlignVCenter, caption)
            f2 = QFont("Arial"); f2.setPointSizeF(2.2); f2.setBold(True)
            painter.setFont(f2)
            painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
            painter.drawText(val_rect, Qt.AlignmentFlag.AlignLeft |
                             Qt.AlignmentFlag.AlignVCenter, " " + value)

        cell_h = (r3 - r1) / 2   # height of lower rows

        # Col 0 — company (full height)
        label(QRectF(c0 + 1, r0 + 1, c1 - c0 - 2, h - 2),
              self.fields["Company"], bold=True, big=True)

        # Col 1 rows
        small_label(QRectF(c1, r0, c2 - c1, r1 - r0),
                    "PROJECT", self.fields["Project"])
        small_label(QRectF(c1, r1, c2 - c1, r2 - r1),
                    "TITLE",   self.fields["Title"])
        f3 = QFont("Arial"); f3.setPointSizeF(1.8)
        painter.setFont(f3)
        painter.setPen(QPen(QColor("#666666"), 0.1))
        painter.drawText(QRectF(c1 + 1, r2 + 0.5, (c2 - c1) / 2 - 2, r3 - r2 - 1),
                         Qt.AlignmentFlag.AlignLeft, "DRAWN BY")
        painter.drawText(QRectF(c1 + (c2 - c1) / 2 + 1, r2 + 0.5,
                                (c2 - c1) / 2 - 2, r3 - r2 - 1),
                         Qt.AlignmentFlag.AlignLeft, "CHECKED BY")
        f4 = QFont("Arial"); f4.setPointSizeF(2.0); f4.setBold(True)
        painter.setFont(f4); painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
        painter.drawText(QRectF(c1 + 1, r2 + (r3 - r2) * 0.4,
                                (c2 - c1) / 2 - 2, r3 - r2 - (r3 - r2) * 0.4),
                         Qt.AlignmentFlag.AlignLeft,
                         " " + self.fields["Drawn By"])
        painter.drawText(QRectF(c1 + (c2 - c1) / 2 + 1, r2 + (r3 - r2) * 0.4,
                                (c2 - c1) / 2 - 2,
                                r3 - r2 - (r3 - r2) * 0.4),
                         Qt.AlignmentFlag.AlignLeft,
                         " " + self.fields["Checked By"])
        # Vertical divider inside col1 bottom row
        painter.setPen(pen_thin)
        painter.drawLine(QPointF(c1 + (c2 - c1) / 2, r2),
                         QPointF(c1 + (c2 - c1) / 2, r3))

        # Col 2 rows
        small_label(QRectF(c2, r0, c3 - c2, r1 - r0), "SCALE",      self.fields["Scale"])
        small_label(QRectF(c2, r1, c3 - c2, r2 - r1), "DRAWING NO", self.fields["Drawing No"])
        small_label(QRectF(c2, r2, c3 - c2, r3 - r2), "SHEET",      "1 of 1")

        # Col 3 rows
        small_label(QRectF(c3, r0, x + w - c3, r1 - r0), "REV",  self.fields["Rev"])
        small_label(QRectF(c3, r1, x + w - c3, r2 - r1), "DATE", self.fields["Date"])
        small_label(QRectF(c3, r2, x + w - c3, r3 - r2), "NFPA", "13")

        # Outer border (redraw thick on top to cover thin)
        painter.setPen(pen_thick)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, y, w, h))


# ─────────────────────────────────────────────────────────────────────────────
# Viewport
# ─────────────────────────────────────────────────────────────────────────────

class PaperViewport(QGraphicsRectItem):
    """
    A rectangle in Paper Space that live-renders Model_Space content.

    The source area of the model scene can be overridden; if not set the
    entire scene rect is used.
    """

    def __init__(self, model_scene, x: float, y: float,
                 w: float, h: float, parent=None):
        super().__init__(x, y, w, h, parent)
        self._model_scene = model_scene
        self._source_rect: QRectF | None = None  # None = full scene rect

        pen = QPen(Qt.GlobalColor.black, 0.5)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.GlobalColor.white))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(5)

    @property
    def source_rect(self) -> QRectF | None:
        return self._source_rect

    @source_rect.setter
    def source_rect(self, rect: QRectF | None):
        self._source_rect = rect
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        r = self.rect()

        # White background
        painter.fillRect(r, Qt.GlobalColor.white)

        # Clip to viewport bounds
        painter.setClipRect(r)

        # Determine model-space source rect
        src = self._source_rect
        if src is None:
            src = self._model_scene.sceneRect()
        if not src.isNull() and not src.isEmpty():
            self._model_scene.render(painter, r, src)

        # Release clip before drawing border
        painter.setClipping(False)

        # Border
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.isSelected():
            painter.setPen(QPen(QColor("#0055ff"), 0.8, Qt.PenStyle.DashLine))
        else:
            painter.setPen(QPen(Qt.GlobalColor.black, 0.5))
        painter.drawRect(r)


# ─────────────────────────────────────────────────────────────────────────────
# Paper scene
# ─────────────────────────────────────────────────────────────────────────────

class PaperScene(QGraphicsScene):
    """
    QGraphicsScene representing one paper layout.

    Coordinate system: 1 scene unit = 1 mm.
    The paper sits at (0, 0) with width × height in mm.
    """

    def __init__(self, model_scene, paper_size: str = "ANSI D"):
        super().__init__()
        self._model_scene  = model_scene
        self._paper_size   = paper_size
        self._bg_item      = None
        self._border_item  = None
        self._title        = None
        self._title_tb     = None   # DXF or PDF title block item
        self._viewport     = None
        self._setup()

    def _setup(self):
        """Build/rebuild all paper scene items."""
        self.clear()
        self._title_tb = None

        w, h = PAPER_SIZES[self._paper_size]

        # White paper background
        self._bg_item = self.addRect(
            0, 0, w, h,
            QPen(Qt.GlobalColor.black, 0.3),
            QBrush(Qt.GlobalColor.white),
        )
        self._bg_item.setZValue(0)

        # Title block: try DXF (vector) → PDF (raster) → programmatic
        use_external_title = False

        # 1) DXF title block (preferred — crisp vector at any zoom)
        dxf_path = TITLE_BLOCK_DXFS.get(self._paper_size)
        if dxf_path and os.path.isfile(dxf_path):
            tb_dxf = TitleBlockDxfItem(dxf_path, w, h)
            if tb_dxf.is_valid():
                self.addItem(tb_dxf)
                self._title_tb = tb_dxf
                use_external_title = True

        # 2) PDF title block (fallback — rasterized)
        if not use_external_title:
            pdf_path = TITLE_BLOCK_PDFS.get(self._paper_size)
            if pdf_path:
                tb_pdf = TitleBlockPdfItem(pdf_path, w, h)
                if tb_pdf.pixmap() is not None and not tb_pdf.pixmap().isNull():
                    self.addItem(tb_pdf)
                    self._title_tb = tb_pdf
                    use_external_title = True

        # Drawing border (inner margin) — always shown
        bx = MARGIN; by = MARGIN
        bw = w - 2 * MARGIN; bh = h - 2 * MARGIN
        border = self.addRect(
            bx, by, bw, bh,
            QPen(Qt.GlobalColor.black, 0.5),
            QBrush(Qt.BrushStyle.NoBrush),
        )
        border.setZValue(2)

        # Programmatic title block — shown only when no DXF/PDF loaded
        self._title = TitleBlockItem(w, h)
        self.addItem(self._title)
        if use_external_title:
            self._title.hide()   # DXF/PDF title block takes precedence

        # Viewport — fills the area above the title block (inside border)
        vp_x = bx + INNER_MARGIN
        vp_y = by + INNER_MARGIN
        vp_w = bw - 2 * INNER_MARGIN
        vp_h = bh - 2 * INNER_MARGIN - TITLE_H - 2
        self._viewport = PaperViewport(self._model_scene,
                                       vp_x, vp_y, vp_w, vp_h)
        self.addItem(self._viewport)

        self.setSceneRect(-20, -20, w + 40, h + 40)

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def paper_size(self) -> str:
        return self._paper_size

    @paper_size.setter
    def paper_size(self, size: str):
        if size in PAPER_SIZES:
            self._paper_size = size
            self._setup()

    @property
    def title_block(self) -> TitleBlockItem:
        return self._title

    def refresh_viewport(self):
        """Force the viewport to repaint (call after model changes)."""
        if self._viewport:
            self._viewport.update()


# ─────────────────────────────────────────────────────────────────────────────
# Title-block editor dialog
# ─────────────────────────────────────────────────────────────────────────────

class TitleBlockDialog(QDialog):
    def __init__(self, title_block: TitleBlockItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Title Block")
        self._tb = title_block

        layout = QFormLayout(self)
        self._edits: dict[str, QLineEdit] = {}

        for key, value in title_block.fields.items():
            edit = QLineEdit(value)
            self._edits[key] = edit
            layout.addRow(key + ":", edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _save(self):
        for key, edit in self._edits.items():
            self._tb.fields[key] = edit.text()
        self._tb.update()
        self.accept()


# ─────────────────────────────────────────────────────────────────────────────
# PaperSpaceWidget — the full dock/tab widget
# ─────────────────────────────────────────────────────────────────────────────

class PaperSpaceWidget(QWidget):
    """
    Complete Paper Space panel: toolbar + QGraphicsView of PaperScene.

    Parameters
    ----------
    model_scene : Model_Space
        The drawing scene whose content will be rendered in the viewport.
    """

    def __init__(self, model_scene, parent=None):
        super().__init__(parent)
        self._model_scene = model_scene

        self.paper_scene = PaperScene(model_scene, "ANSI D")

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # ── Toolbar ────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 2)

        toolbar.addWidget(QLabel("Paper:"))
        self._size_combo = QComboBox()
        self._size_combo.addItems(list(PAPER_SIZES.keys()))
        self._size_combo.setCurrentText("ANSI D")
        self._size_combo.currentTextChanged.connect(self._change_paper)
        toolbar.addWidget(self._size_combo)

        toolbar.addSpacing(12)

        edit_title_btn = QPushButton("Edit Title Block…")
        edit_title_btn.clicked.connect(self._edit_title)
        toolbar.addWidget(edit_title_btn)

        refresh_btn = QPushButton("⟳ Refresh Viewport")
        refresh_btn.setToolTip("Repaint the model-space preview")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

        fit_btn = QPushButton("Fit Sheet")
        fit_btn.clicked.connect(self._fit)
        toolbar.addWidget(fit_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── View ─────────────────────────────────────────────────────────────
        self.view = QGraphicsView(self.paper_scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor("#c0c0c0")))
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        layout.addWidget(self.view)

        # Fit to sheet on first show
        self._fit()

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _change_paper(self, size: str):
        self.paper_scene.paper_size = size
        self._fit()

    def change_paper(self, size: str):
        """Public: change paper size and fit the view."""
        self._size_combo.setCurrentText(size)  # keeps combo in sync

    def _edit_title(self):
        dlg = TitleBlockDialog(self.paper_scene.title_block, self)
        dlg.exec()
        self.paper_scene.refresh_viewport()

    def edit_title_block(self):
        """Public: open the title block editor dialog."""
        self._edit_title()

    def _refresh(self):
        self.paper_scene.refresh_viewport()

    def _fit(self):
        self.view.fitInView(self.paper_scene.sceneRect(),
                            Qt.AspectRatioMode.KeepAspectRatio)

    # ── Zoom wheel ────────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.view.scale(factor, factor)
