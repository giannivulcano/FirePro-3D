"""
paper_space.py
==============
Sprint 4B — Paper Space layout with title block and live model-space viewport.

Classes
-------
TitleBlockItem   — QGraphicsItem that draws a professional engineering title block
SheetViewport    — QGraphicsObject viewport placed on a paper sheet (replaces PaperViewport)
PaperScene       — QGraphicsScene representing one paper layout
PaperSpaceWidget — QWidget wrapping a view of PaperScene + paper-size/title controls
"""

from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import dataclass, field
from .constants import DEFAULT_TEXT_HEIGHT_MM, TEXT_METRIC_REF_PX, MIN_TEXT_WRAP_WIDTH_MM
from .scale_manager import ScaleManager
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QGraphicsPixmapItem, QGraphicsObject, QGraphicsTextItem,
    QGraphicsSceneContextMenuEvent, QComboBox, QPushButton, QLabel,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QGraphicsDropShadowEffect,
    QMenu, QCheckBox, QColorDialog, QFontComboBox, QPlainTextEdit,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF, QSize, pyqtSignal
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QFont, QFontMetricsF, QTransform, QPixmap,
    QPainterPath, QImage,
)
try:
    from PyQt6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

# Base directory for default title block PDFs
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

MIME_VIEW = "application/x-firepro3d-view"


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
    otherwise falls back to a ``"1:N"`` metric string.  A ratio of ``0.0``
    returns ``"NTS"`` (Not To Scale).

    Args:
        ratio: Dimensionless scale ratio (model units / paper units).

    Returns:
        A scale string such as ``"1:100"`` or ``'1/4"=1\\'-0"'``.
    """
    if ratio == 0.0:
        return "NTS"
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
        different scales, ``"NTS"`` when all viewports are Not To Scale,
        or an empty string when there are no viewports.
    """
    if not sheet.sheet_views:
        return ""
    scales = {sv.scale for sv in sheet.sheet_views if sv.scale != 0.0}
    if not scales:
        return "NTS"
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
    show_border: bool = True
    view_number: str = ""

    def to_dict(self) -> dict:
        return {
            "source_view_type": self.source_view_type,
            "source_view_name": self.source_view_name,
            "title": self.title,
            "scale": self.scale,
            "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
            "show_border": self.show_border,
            "view_number": self.view_number,
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
            show_border=d.get("show_border", True),
            view_number=d.get("view_number", ""),
        )


@dataclass
class TextAnnotationData:
    """Serializable data for one sheet text annotation. All lengths in paper mm.

    Shared by reference with its TextAnnotationItem (never copied), exactly like
    SheetViewData <-> SheetViewport.
    """
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    height_mm: float = DEFAULT_TEXT_HEIGHT_MM   # CAP height
    wrap_width_mm: float = 0.0                   # 0 = auto-width; >0 = word-wrap width
    font_family: str = ""                        # "" => Arial default
    bold: bool = False
    italic: bool = False
    color: str = "#000000"                       # authored hex, default black
    align: str = "L"                             # 'L' | 'C' | 'R'
    opaque_bg: bool = False
    type: str = "text"                           # discriminator for future annotation types

    def to_dict(self) -> dict:
        return {
            "type": self.type, "text": self.text,
            "x": self.x, "y": self.y,
            "height_mm": self.height_mm, "wrap_width_mm": self.wrap_width_mm,
            "font_family": self.font_family,
            "bold": self.bold, "italic": self.italic,
            "color": self.color, "align": self.align,
            "opaque_bg": self.opaque_bg,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TextAnnotationData":
        return cls(
            text=d.get("text", ""),
            x=d.get("x", 0.0), y=d.get("y", 0.0),
            height_mm=d.get("height_mm", DEFAULT_TEXT_HEIGHT_MM),
            wrap_width_mm=d.get("wrap_width_mm", 0.0),
            font_family=d.get("font_family", ""),
            bold=d.get("bold", False), italic=d.get("italic", False),
            color=d.get("color", "#000000"), align=d.get("align", "L"),
            opaque_bg=d.get("opaque_bg", False),
            type=d.get("type", "text"),
        )


@dataclass
class Sheet:
    """Data model for one paper sheet."""
    number: str
    name: str
    paper_size: str
    title_block_fields: dict[str, str]
    sheet_views: list[SheetViewData]
    annotations: list[TextAnnotationData] = field(default_factory=list)

    @classmethod
    def create_default(cls) -> "Sheet":
        return cls(
            number="FP-1.0",
            name="Fire Suppression Layout",
            paper_size="ANSI D",
            title_block_fields=dict(DEFAULT_TITLE_BLOCK_FIELDS),
            sheet_views=[],
            annotations=[],
        )

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "paper_size": self.paper_size,
            "title_block_fields": dict(self.title_block_fields),
            "sheet_views": [sv.to_dict() for sv in self.sheet_views],
            "annotations": [a.to_dict() for a in self.annotations],
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
            annotations=[TextAnnotationData.from_dict(a)
                         for a in d.get("annotations", [])],
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
_VIEW_TITLE_H = 8.0  # mm height for view title below viewport


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
        self._placeholder = False
        self._resizing = False
        self._resize_handle: int = -1
        self._resize_origin = QPointF()

        self.setPos(data.x, data.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
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

    def disconnect_source(self):
        """Drop the source-scene ``changed`` connection (call before discard).

        Required when a transient :class:`PaperScene` is built for off-screen
        export/print and then discarded — otherwise the live model/elevation
        scene keeps a reference to this viewport's slot and fires it forever.
        """
        if self._source_scene is not None:
            try:
                self._source_scene.changed.disconnect(self._on_source_changed)
            except (TypeError, RuntimeError):
                pass
            self._source_scene = None

    def mark_dirty(self):
        self.update()

    def sync_data_from_item(self):
        pos = self.pos()
        self._data.x = pos.x()
        self._data.y = pos.y()

    def boundingRect(self) -> QRectF:
        margin = _GRIP_SIZE if self.isSelected() else 0
        return QRectF(-margin, -margin,
                      self._data.w + 2 * margin,
                      self._data.h + _VIEW_TITLE_H + 2 * margin)

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

        # White background
        painter.fillRect(vp_rect, Qt.GlobalColor.white)

        # Clip to viewport bounds
        painter.setClipRect(vp_rect)

        # Render source scene with paper-space display overrides
        if self._source_scene is not None and not self._source_rect.isNull() and not self._source_rect.isEmpty():
            from .paper_display import apply_paper_overrides, restore_model_display
            saved = apply_paper_overrides(self._source_scene, self._source_rect)
            try:
                self._source_scene.render(painter, vp_rect, self._source_rect)
            finally:
                restore_model_display(saved)

        # Release clip
        painter.setClipping(False)

        # Border (only when enabled)
        if self._data.show_border:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if self.isSelected():
                painter.setPen(QPen(QColor("#0055ff"), 0.8, Qt.PenStyle.DashLine))
            else:
                painter.setPen(QPen(Qt.GlobalColor.black, 0.3))
            painter.drawRect(vp_rect)
        elif self.isSelected():
            # Still show selection indicator even without border
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#0055ff"), 0.8, Qt.PenStyle.DashLine))
            painter.drawRect(vp_rect)

        # View title below viewport (Revit-style)
        title_y = h + 0.5

        # Bubble
        bubble_r = 3.0
        bubble_cx = bubble_r + 1.0
        bubble_cy = title_y + bubble_r + 1.0
        painter.setPen(QPen(Qt.GlobalColor.black, 0.25))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        painter.drawEllipse(QPointF(bubble_cx, bubble_cy), bubble_r, bubble_r)
        # Number in bubble
        f_num = QFont("Arial")
        f_num.setPointSizeF(2.0)
        f_num.setBold(True)
        painter.setFont(f_num)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(QRectF(bubble_cx - bubble_r, bubble_cy - bubble_r,
                                bubble_r * 2, bubble_r * 2),
                         Qt.AlignmentFlag.AlignCenter,
                         self._data.view_number or "1")

        # Horizontal line from bubble right perimeter to viewport edge
        line_x_start = bubble_cx + bubble_r
        painter.setPen(QPen(Qt.GlobalColor.black, 0.3))
        painter.drawLine(QPointF(line_x_start, bubble_cy),
                         QPointF(w, bubble_cy))

        # Title text — ALL CAPS, bold, ABOVE the line
        text_x = line_x_start + 1.5
        f_title = QFont("Arial")
        f_title.setPointSizeF(2.2)
        f_title.setBold(True)
        painter.setFont(f_title)
        painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
        title_rect_above = QRectF(text_x, title_y, w - text_x, bubble_cy - title_y - 0.3)
        painter.drawText(title_rect_above,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                         self._data.title.upper())

        # Scale text below the line
        if self._data.scale == 0.0:
            scale_text = "NTS"
        else:
            scale_text = float_to_scale_str(self._data.scale)
        f_scale = QFont("Arial")
        f_scale.setPointSizeF(1.6)
        painter.setFont(f_scale)
        painter.setPen(QPen(QColor("#444444"), 0.1))
        title_rect_below = QRectF(text_x, bubble_cy + 0.3, w - text_x, bubble_r + 0.5)
        painter.drawText(title_rect_below,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         scale_text)

        # Resize grips when selected
        if self.isSelected():
            self._draw_grips(painter)

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
# TextAnnotationItem — free-placed, paper-fixed text block
# ─────────────────────────────────────────────────────────────────────────────

class TextAnnotationItem(QGraphicsTextItem):
    """A free-placed, paper-fixed text block on a PaperScene.

    Purpose-built (NOT a reused model-space NoteAnnotation — spec §4.11). Holds
    its TextAnnotationData by shared reference. Sizes via a device-independent
    pixel-size font + geometric setScale on cap height, so a paper-mm height
    renders identically on the 96-dpi screen and the 300-dpi PDF.

    Sizing invariant (§9.4): font.setPixelSize(TEXT_METRIC_REF_PX) gives a
    large, high-precision reference size; setScale then maps cap-height units
    to paper-mm units. NEVER setPointSizeF (DPI-dependent), NEVER
    ItemIgnoresTransformations (pins to device px, breaks zoom + export).
    """

    delete_requested = pyqtSignal(object)
    properties_requested = pyqtSignal(object)

    _ALIGN = {
        "L": Qt.AlignmentFlag.AlignLeft,
        "C": Qt.AlignmentFlag.AlignCenter,
        "R": Qt.AlignmentFlag.AlignRight,
    }
    _GRIP_MM = 2.5   # paper-mm size of the right-edge wrap-resize handle

    def __init__(self, data: "TextAnnotationData", parent=None):
        super().__init__(data.text, parent)
        self._data = data
        self._editing = False
        self._text_before_edit = data.text
        self._pos_at_press = None
        self._wrap_at_press = None
        self._resizing = False
        self.setZValue(15)
        self.setTransformOriginPoint(0, 0)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setPos(data.x, data.y)
        self._apply_format()

    @property
    def data(self) -> "TextAnnotationData":
        """Shared-reference access to the underlying TextAnnotationData."""
        return self._data

    def _apply_format(self) -> None:
        """Rebuild font, colour, alignment, scale, and wrap from self._data.

        Recompute all display properties from the data object. Call whenever
        any formatting attribute on the data changes.
        """
        d = self._data
        f = QFont(d.font_family) if d.font_family else QFont("Arial")
        f.setBold(d.bold)
        f.setItalic(d.italic)
        f.setPixelSize(TEXT_METRIC_REF_PX)
        self.setFont(f)
        self.setDefaultTextColor(QColor(d.color))
        opt = self.document().defaultTextOption()
        opt.setAlignment(self._ALIGN.get(d.align, Qt.AlignmentFlag.AlignLeft))
        self.document().setDefaultTextOption(opt)
        cap = QFontMetricsF(f).capHeight()
        scale = d.height_mm / cap if cap > 0 else 1.0
        self.setScale(scale)
        if d.wrap_width_mm > 0:
            self.setTextWidth(d.wrap_width_mm / scale)
        else:
            self.setTextWidth(-1)
            self.setTextWidth(self.document().idealWidth())

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """Paint the text block with opaque fill, edit frame, and resize grip.

        Renders in order: (1) solid-white knockout when opaque_bg is set,
        (2) the text via super(), (3) dashed #88aaff cosmetic border while
        inline-editing, (4) solid #88aaff grip square on the right edge while
        selected but not editing. Grip is drawn in item-local unscaled coords
        at size _GRIP_MM / scale so it appears _GRIP_MM paper-mm on screen.

        Args:
            painter: Active QPainter for the scene.
            option: Style option (passed through to super).
            widget: Optional target widget (passed through to super).
        """
        if self._data.opaque_bg:
            painter.fillRect(self.boundingRect(), QColor("#ffffff"))
        super().paint(painter, option, widget)
        if self._editing:
            pen = QPen(QColor("#88aaff"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
        elif self.isSelected():
            s = self.scale() or 1.0
            gs = self._GRIP_MM / s
            br = self.boundingRect()
            grip = QRectF(br.right() - gs, br.center().y() - gs / 2, gs, gs)
            painter.fillRect(grip, QColor("#88aaff"))

    # ── A. Edit lifecycle ──────────────────────────────────────────────────

    def is_effectively_empty(self) -> bool:
        """Return True when the block contains only whitespace.

        Returns:
            True when toPlainText().strip() is an empty string.
        """
        return self.toPlainText().strip() == ""

    def begin_edit(self) -> None:
        """Enter inline-edit mode: enable text interaction and take keyboard focus.

        Saves the current text so that cancel_edit() can revert to it.
        """
        self._editing = True
        self._text_before_edit = self._data.text
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def commit_edit(self) -> str:
        """Commit the edited text into data and exit edit mode.

        Returns:
            The committed plain-text string (may be empty/whitespace).
        """
        self._editing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        new_text = self.toPlainText()
        self._data.text = new_text
        self._apply_format()
        return new_text

    def cancel_edit(self) -> None:
        """Revert to the pre-edit text and exit edit mode without committing.

        For a pending placement item (scene._pending_text is self), also
        discards the transient item so that Esc during place-mode leaves
        nothing on the scene and nothing tracked. The reverted text is always
        empty for a fresh placement, so commit_place_text() will auto-discard.
        """
        self._editing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setPlainText(self._text_before_edit)
        self._data.text = self._text_before_edit
        self._apply_format()
        # Esc during place-mode: route through commit_place_text so the
        # transient item is removed and nothing is left tracked.
        scene = self.scene()
        if scene is not None and getattr(scene, "_pending_text", None) is self:
            scene.commit_place_text(self)

    def mouseDoubleClickEvent(self, event) -> None:
        """Enter inline-edit mode on a double-click while not already editing."""
        if not self._editing:
            self.begin_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event) -> None:
        """Auto-commit the edit when the item loses keyboard focus."""
        if self._editing:
            self._on_edit_finished()
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        """Route key events to the editor or to item-level commands.

        While editing: Esc cancels; all other keys (Enter for newline, Delete
        for character) pass through to the text editor.
        While not editing: Delete emits delete_requested; other keys delegate
        to super().
        """
        if self._editing:
            if event.key() == Qt.Key.Key_Escape:
                self.cancel_edit()
                event.accept()
                return
            super().keyPressEvent(event)   # Enter=newline, Delete=char
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_requested.emit(self)
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_edit_finished(self) -> None:
        """Called when inline editing ends (focus-out path).

        For a pending placement item (scene._pending_text is self), routes to
        commit_place_text() which discards the transient item when empty and
        creates a tracked annotation otherwise. For an existing tracked
        annotation, commits the edit directly. Task 7 will swap the tracked
        path for an undo command.
        """
        scene = self.scene()
        if scene is not None and getattr(scene, "_pending_text", None) is self:
            scene.commit_place_text(self)
        else:
            self.commit_edit()

    def sync_data_from_item(self) -> None:
        """Write the current scene position back into the data object (paper mm)."""
        self._data.x = self.pos().x()
        self._data.y = self.pos().y()

    def contextMenuEvent(self, event) -> None:
        """Show Properties / Delete context menu on right-click.

        While inline-editing, delegates to super() so the native copy/paste
        editor menu is shown instead of the Properties/Delete menu.
        """
        if self._editing:
            super().contextMenuEvent(event)
            return
        menu = QMenu()
        props = menu.addAction("Properties...")
        menu.addSeparator()
        delete = menu.addAction("Delete")
        action = menu.exec(event.screenPos())
        if action == props:
            self.properties_requested.emit(self)
        elif action == delete:
            self.delete_requested.emit(self)

    # ── B. itemChange: anchor clamp + live data sync ─────────────────────────

    def itemChange(self, change, value):
        """Clamp position to the paper rect and live-sync data on every move.

        ItemPositionChange: clamps the proposed QPointF to [0, paper_width] ×
        [0, paper_height] using PAPER_SIZES[scene.sheet.paper_size].
        ItemPositionHasChanged: calls sync_data_from_item() so _data.x/y stays
        current for export/print without a separate save step.

        Args:
            change: GraphicsItemChange enum value.
            value: Proposed value (QPointF for position changes).

        Returns:
            The (possibly clamped) value for position changes; super()'s return
            for all other changes.
        """
        Change = QGraphicsItem.GraphicsItemChange
        if change == Change.ItemPositionChange and self.scene() is not None:
            pw, ph = PAPER_SIZES[self.scene().sheet.paper_size]
            return QPointF(max(0.0, min(value.x(), pw)),
                           max(0.0, min(value.y(), ph)))
        if change == Change.ItemPositionHasChanged:
            self.sync_data_from_item()
        return super().itemChange(change, value)

    # ── C. Wrap-resize grip ───────────────────────────────────────────────────

    def _grip_scene_rect(self) -> QRectF:
        """Return the resize-grip hit rectangle in scene (paper-mm) coordinates.

        The grip is a _GRIP_MM × _GRIP_MM square centred on the right edge of
        sceneBoundingRect. Used by mousePressEvent for hit-testing.

        Returns:
            QRectF in scene coordinates.
        """
        br = self.sceneBoundingRect()
        g = self._GRIP_MM
        return QRectF(br.right() - g, br.center().y() - g / 2, g, g)

    def mousePressEvent(self, event) -> None:
        """Start a wrap-resize drag when the grip is pressed; otherwise begin move."""
        if self.isSelected() and self._grip_scene_rect().contains(event.scenePos()):
            self._resizing = True
            self._wrap_at_press = self._data.wrap_width_mm
            event.accept()
            return
        self._pos_at_press = (self._data.x, self._data.y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Expand or shrink wrap_width_mm while dragging the right-edge grip."""
        if self._resizing:
            new_w = max(MIN_TEXT_WRAP_WIDTH_MM,
                        event.scenePos().x() - self.pos().x())
            self._data.wrap_width_mm = new_w
            self.prepareGeometryChange()
            self._apply_format()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Finish a resize or move drag and notify the undo hook."""
        if self._resizing:
            self._resizing = False
            self._on_wrap_resized(self._wrap_at_press, self._data.wrap_width_mm)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._pos_at_press is not None:
            old = self._pos_at_press
            self._pos_at_press = None
            if old != (self._data.x, self._data.y):
                self._on_moved(old, (self._data.x, self._data.y))

    def _on_moved(self, old_xy: tuple, new_xy: tuple) -> None:
        """Hook called after a completed free-drag move.

        Scene overrides this in Task 7 to push a MoveTextAnnotationCommand.
        Default: no-op (data already updated live by itemChange).

        Args:
            old_xy: (x, y) paper-mm position before the drag.
            new_xy: (x, y) paper-mm position after the drag.
        """

    def _on_wrap_resized(self, old_w: float, new_w: float) -> None:
        """Hook called after a completed wrap-resize drag.

        Scene overrides this in Task 7 to push a WrapResizeTextCommand.
        Default: no-op (wrap_width_mm already updated live by mouseMoveEvent).

        Args:
            old_w: wrap_width_mm in paper mm before the resize.
            new_w: wrap_width_mm in paper mm after the resize.
        """


# ─────────────────────────────────────────────────────────────────────────────
# SheetViewPropertiesDialog
# ─────────────────────────────────────────────────────────────────────────────

class SheetViewPropertiesDialog(QDialog):
    """Properties dialog for a sheet viewport.

    Used both pre-placement (title + scale) and post-placement
    (adds position and size fields).
    """

    def __init__(self, source_view_name: str, data: SheetViewData | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sheet View Properties")
        self._data = data

        layout = QFormLayout(self)

        self._title_edit = QLineEdit(data.title if data else source_view_name)
        layout.addRow("Title:", self._title_edit)

        self._scale_combo = QComboBox()
        self._scale_combo.setEditable(True)
        self._scale_combo.addItem("NTS")
        for label, _ in SCALE_PRESETS:
            self._scale_combo.addItem(label)
        if data:
            self._scale_combo.setCurrentText(float_to_scale_str(data.scale))
        else:
            self._scale_combo.setCurrentText("1:100")
        layout.addRow("Scale:", self._scale_combo)

        self._border_check = QCheckBox("Show Border")
        self._border_check.setChecked(data.show_border if data else True)
        layout.addRow("", self._border_check)

        if data:
            self._x_edit = QLineEdit(f"{data.x:.1f}")
            self._y_edit = QLineEdit(f"{data.y:.1f}")
            self._w_edit = QLineEdit(f"{data.w:.1f}")
            self._h_edit = QLineEdit(f"{data.h:.1f}")
            layout.addRow("Position X:", self._x_edit)
            layout.addRow("Position Y:", self._y_edit)
            layout.addRow("Width:", self._w_edit)
            layout.addRow("Height:", self._h_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_title(self) -> str:
        return self._title_edit.text()

    def get_show_border(self) -> bool:
        return self._border_check.isChecked()

    def get_scale(self) -> float:
        text = self._scale_combo.currentText()
        if text.upper() == "NTS":
            return 0.0  # sentinel for Not To Scale
        return scale_to_float(text)

    def get_position(self) -> "tuple[float, float] | None":
        if self._data is None:
            return None
        try:
            x = float(self._x_edit.text())
            y = float(self._y_edit.text())
        except ValueError:
            return (self._data.x, self._data.y)
        return (x, y)

    def get_size(self) -> "tuple[float, float] | None":
        if self._data is None:
            return None
        try:
            w = float(self._w_edit.text())
            h = float(self._h_edit.text())
        except ValueError:
            return (self._data.w, self._data.h)
        return (max(w, _MIN_VIEWPORT_SIZE), max(h, _MIN_VIEWPORT_SIZE))


# ─────────────────────────────────────────────────────────────────────────────
# TextAnnotationPropertiesDialog helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_text_height_mm(text: str) -> float | None:
    """Parse a paper text height string to mm.

    Delegates to ``ScaleManager.parse_dimension`` after pre-processing a bare
    leading fraction such as ``1/8"`` (which parse_dimension rejects) by
    inserting a ``0 `` prefix to produce ``0 1/8"``.

    Args:
        text: A dimension string, e.g. ``'1/8"'``, ``'3mm'``, ``'3.175 mm'``.

    Returns:
        The equivalent value in millimetres, or ``None`` if unparseable.
    """
    import re as _re
    t = text.strip()
    # Pre-process a bare leading fraction like "1/8"" → "0 1/8""
    if _re.match(r'^\d+\s*/\s*\d+\s*"?$', t):
        t = "0 " + t
    return ScaleManager.parse_dimension(t, fallback_unit="mm")


# ─────────────────────────────────────────────────────────────────────────────
# TextAnnotationPropertiesDialog
# ─────────────────────────────────────────────────────────────────────────────

class TextAnnotationPropertiesDialog(QDialog):
    """Properties dialog for a sheet text annotation.

    Mirrors ``SheetViewPropertiesDialog``: ``QFormLayout``, one row per field,
    ``QDialogButtonBox(Ok|Cancel)``.  The caller reads values via ``get_*``
    accessors and applies them through an undo command — **this dialog never
    mutates the annotation directly** (§9.6).

    Args:
        data: The ``TextAnnotationData`` to pre-populate fields from.
        sm: A ``ScaleManager`` instance used to format the height seed value.
        parent: Optional parent widget.
    """

    def __init__(self, data: TextAnnotationData, sm: ScaleManager,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text Annotation Properties")
        self._height_fallback = data.height_mm

        layout = QFormLayout(self)

        # ── Text ─────────────────────────────────────────────────────────────
        self._text_edit = QPlainTextEdit(data.text)
        self._text_edit.setMinimumHeight(80)
        layout.addRow("Text:", self._text_edit)

        # ── Font family ───────────────────────────────────────────────────────
        self._font_combo = QFontComboBox()
        if data.font_family:
            self._font_combo.setCurrentFont(QFont(data.font_family))
        layout.addRow("Font:", self._font_combo)

        # ── Height ────────────────────────────────────────────────────────────
        self._height_edit = QLineEdit(sm.format_length(data.height_mm))
        self._height_edit.setPlaceholderText('e.g. 0 1/8" or 3.18mm')
        layout.addRow("Height:", self._height_edit)

        # ── Bold / Italic ─────────────────────────────────────────────────────
        self._bold_check = QCheckBox("Bold")
        self._bold_check.setChecked(data.bold)
        layout.addRow("", self._bold_check)

        self._italic_check = QCheckBox("Italic")
        self._italic_check.setChecked(data.italic)
        layout.addRow("", self._italic_check)

        # ── Color swatch ──────────────────────────────────────────────────────
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(24, 24)
        initial_color = data.color if data.color else "#000000"
        self._color_btn.setProperty("_color_value", initial_color)
        c = QColor(initial_color)
        self._color_btn.setStyleSheet(
            f"background: {c.name()}; border: 1px solid #888; border-radius: 2px;"
        )
        self._color_btn.clicked.connect(self._pick_color_slot)
        layout.addRow("Color:", self._color_btn)

        # ── Alignment ─────────────────────────────────────────────────────────
        self._align_combo = QComboBox()
        self._align_combo.addItems(["Left", "Center", "Right"])
        _align_idx = {"L": 0, "C": 1, "R": 2}
        self._align_combo.setCurrentIndex(_align_idx.get(data.align, 0))
        layout.addRow("Alignment:", self._align_combo)

        # ── Opaque background ─────────────────────────────────────────────────
        self._opaque_check = QCheckBox("Opaque background")
        self._opaque_check.setChecked(data.opaque_bg)
        layout.addRow("", self._opaque_check)

        # ── Buttons ───────────────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    # ── Color picker slot ─────────────────────────────────────────────────────

    def _pick_color_slot(self):
        """Open a colour dialog and update the swatch button."""
        stored = self._color_btn.property("_color_value")
        current = QColor(stored) if stored else QColor("#000000")
        color = QColorDialog.getColor(current, self, "Pick a colour")
        if color.isValid():
            self._color_btn.setProperty("_color_value", color.name())
            self._color_btn.setStyleSheet(
                f"background: {color.name()}; "
                f"border: 1px solid #888; border-radius: 2px;"
            )

    # ── Accessors (caller reads these; never mutates the annotation) ──────────

    def get_text(self) -> str:
        """Return the plain text content."""
        return self._text_edit.toPlainText()

    def get_font_family(self) -> str:
        """Return the selected font family name."""
        return self._font_combo.currentFont().family()

    def get_height_mm(self) -> float:
        """Parse the height field and return mm; on unrecognisable input returns original.

        Returns:
            Height in millimetres from the height field, or the original
            ``data.height_mm`` when the field text cannot be parsed.
        """
        result = _parse_text_height_mm(self._height_edit.text())
        return result if result is not None else self._height_fallback

    def get_bold(self) -> bool:
        """Return whether bold is checked."""
        return self._bold_check.isChecked()

    def get_italic(self) -> bool:
        """Return whether italic is checked."""
        return self._italic_check.isChecked()

    def get_color(self) -> str:
        """Return the selected colour as a hex string (e.g. ``'#ff0000'``)."""
        return self._color_btn.property("_color_value") or "#000000"

    def get_alignment(self) -> str:
        """Return the alignment code: ``'L'``, ``'C'``, or ``'R'``."""
        return ["L", "C", "R"][self._align_combo.currentIndex()]

    def get_opaque_bg(self) -> bool:
        """Return whether the opaque-background option is checked."""
        return self._opaque_check.isChecked()


# ─────────────────────────────────────────────────────────────────────────────
# TitleBlockFieldOverlay — field values painted over DXF/PDF artwork
# ─────────────────────────────────────────────────────────────────────────────

class TitleBlockFieldOverlay(QGraphicsItem):
    """Draws title block field values on top of DXF/PDF artwork.

    Only used when an external (DXF/PDF) title block is active.
    """

    def __init__(self, paper_w: float, paper_h: float,
                 fields: dict[str, str], parent=None):
        super().__init__(parent)
        self._paper_w = paper_w
        self._paper_h = paper_h
        self._fields = fields
        self.setZValue(1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._paper_w, self._paper_h)

    def paint(self, painter: QPainter, option, widget=None):
        layout = _get_field_layout(self._paper_w, self._paper_h)
        if layout is None:
            return
        for field_name, (x, y, w, h, font_size) in layout.items():
            value = self._fields.get(field_name, "")
            if not value:
                continue
            f = QFont("Arial")
            f.setPointSizeF(font_size)
            f.setBold(True)
            painter.setFont(f)
            painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
            painter.drawText(
                QRectF(x + 1, y + h * 0.3, w - 2, h * 0.65),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                value,
            )


def _get_field_layout(paper_w: float, paper_h: float
                      ) -> "dict[str, tuple[float, float, float, float, float]] | None":
    """Return field layout for the given paper size.

    Returns {field_name: (x, y, w, h, font_size_pt)} in mm.
    """
    bx = MARGIN + INNER_MARGIN
    by = paper_h - MARGIN - INNER_MARGIN - TITLE_H
    bw = paper_w - 2 * (MARGIN + INNER_MARGIN)
    bh = TITLE_H

    c0 = bx
    c1 = bx + bw * 0.30
    c2 = bx + bw * 0.70
    c3 = bx + bw * 0.85

    r0 = by
    r1 = by + bh * 0.33
    r2 = by + bh * 0.66
    r3 = by + bh

    row_h = (r3 - r0) / 3.0
    half_col1 = (c2 - c1) / 2.0

    return {
        "Company":    (c0, r0, c1 - c0, bh, 2.5),
        "Project":    (c1, r0, c2 - c1, row_h, 2.2),
        "Title":      (c1, r1, c2 - c1, row_h, 2.2),
        "Drawn By":   (c1, r2, half_col1, row_h, 2.0),
        "Checked By": (c1 + half_col1, r2, half_col1, row_h, 2.0),
        "Scale":      (c2, r0, c3 - c2, row_h, 2.2),
        "Drawing No": (c2, r1, c3 - c2, row_h, 2.2),
        "Rev":        (c3, r0, bx + bw - c3, row_h, 2.2),
        "Date":       (c3, r1, bx + bw - c3, row_h, 2.2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PaperGraphicsView — drop-aware view for placing sheet viewports
# ─────────────────────────────────────────────────────────────────────────────

class PaperGraphicsView(QGraphicsView):
    """QGraphicsView for PaperScene with drop support and model-view-style navigation."""

    def __init__(self, scene: "PaperScene", parent=None):
        super().__init__(scene, parent)
        self.setAcceptDrops(True)
        self._paper_scene = scene
        self._panning = False
        self._pan_start = QPointF()
        self._add_text_mode = False
        self._add_text_btn = None

        # Match Model_View navigation style
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#c0c0c0")))

    # ── Add-Text tool ──────────────────────────────────────────────────

    def set_add_text_mode(self, on: bool) -> None:
        """Enable or disable Add-Text place-mode.

        When *on* is True the cursor changes to a cross-hair and the next
        left-click places a new text annotation at that scene position. The
        mode is automatically cleared after one placement.

        Args:
            on: True to enter Add-Text place-mode; False to exit.
        """
        self._add_text_mode = bool(on)
        self.setCursor(
            Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor
        )

    # ── Delete key handling ────────────────────────────────────────────

    def event(self, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.ShortcutOverride:
            if event.key() == Qt.Key.Key_Delete:
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            scene = self._paper_scene
            selected = [item for item in scene.selectedItems()
                        if isinstance(item, SheetViewport)]
            for vp in selected:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda v=vp: scene.remove_viewport(v))
            ann_selected = [
                item for item in scene.selectedItems()
                if isinstance(item, TextAnnotationItem)
                and not getattr(item, "_editing", False)
            ]
            for it in ann_selected:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda a=it: scene.remove_annotation(a))
            if selected or ann_selected:
                event.accept()
                return
        super().keyPressEvent(event)

    # ── Drag-and-drop (existing) ─────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_VIEW):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_VIEW):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_VIEW):
            event.ignore()
            return
        raw = bytes(event.mimeData().data(MIME_VIEW)).decode("utf-8")
        payload = json.loads(raw)
        view_type = payload["view_type"]
        view_name = payload["view_name"]

        drop_pos = self.mapToScene(event.position().toPoint())

        dlg = SheetViewPropertiesDialog(view_name, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            event.ignore()
            return

        title = dlg.get_title()
        scale = dlg.get_scale()

        result = self._paper_scene._resolver.resolve(view_type, view_name)
        if result is None:
            event.ignore()
            return
        _, src_rect = result

        pw, ph = PAPER_SIZES[self._paper_scene.sheet.paper_size]
        max_w = pw - 2 * (MARGIN + INNER_MARGIN)
        max_h = ph - 2 * (MARGIN + INNER_MARGIN) - TITLE_H

        if scale == 0.0:
            # NTS: fit to a reasonable default viewport size
            target_w = max_w * 0.6
            target_h = max_h * 0.6
            sx = target_w / src_rect.width() if src_rect.width() > 0 else 0.01
            sy = target_h / src_rect.height() if src_rect.height() > 0 else 0.01
            fit_scale = min(sx, sy)
            vp_w = src_rect.width() * fit_scale
            vp_h = src_rect.height() * fit_scale
        else:
            vp_w = src_rect.width() * scale
            vp_h = src_rect.height() * scale

        if vp_w > max_w or vp_h > max_h:
            clamp = min(max_w / vp_w, max_h / vp_h)
            vp_w *= clamp
            vp_h *= clamp

        x = drop_pos.x() - vp_w / 2
        y = drop_pos.y() - vp_h / 2

        x = max(MARGIN + INNER_MARGIN, min(x, pw - MARGIN - INNER_MARGIN - vp_w))
        y = max(MARGIN + INNER_MARGIN, min(y, ph - MARGIN - INNER_MARGIN - TITLE_H - vp_h))

        data = SheetViewData(view_type, view_name, title, scale, x, y, vp_w, vp_h)
        self._paper_scene.add_viewport(data)
        event.acceptProposedAction()

    # ── Navigation (middle-button pan + scroll zoom) ─────────────────

    def wheelEvent(self, event):
        """Zoom under cursor, matching Model_View behavior."""
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        # Anchor zoom to cursor position
        cursor_scene = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new_cursor_scene = self.mapToScene(event.position().toPoint())
        delta = new_cursor_scene - cursor_scene
        self.translate(delta.x(), delta.y())

    def mousePressEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if self._add_text_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.position().toPoint())
            self._paper_scene.begin_place_text(pos)
            self.set_add_text_mode(False)
            if self._add_text_btn is not None:
                self._add_text_btn.setChecked(False)
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


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
        pen = QPen(Qt.GlobalColor.black, 0)
        pen.setCosmetic(False)
        pen.setWidthF(0.25)
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
# Paper scene
# ─────────────────────────────────────────────────────────────────────────────

class PaperScene(QGraphicsScene):
    """QGraphicsScene representing one paper layout.

    Coordinate system: 1 scene unit = 1 mm.
    """

    navigate_to_view = pyqtSignal(str, str)

    def __init__(self, sheet: Sheet, resolver: ViewResolver):
        super().__init__()
        self._sheet = sheet
        self._resolver = resolver
        self._bg_item = None
        self._border_item = None
        self._title = None
        self._title_tb = None
        self._field_overlay = None
        self._viewports: list[SheetViewport] = []
        self._annotations: list[TextAnnotationItem] = []
        self._pending_text: "TextAnnotationItem | None" = None
        self._setup()

    def _setup(self):
        """Build/rebuild all paper scene items."""
        self.clear()
        self._title_tb = None
        self._field_overlay = None
        self._viewports = []
        self._annotations = []
        self._pending_text = None  # any in-progress placement is voided by a rebuild

        w, h = PAPER_SIZES[self._sheet.paper_size]

        # White paper background
        self._bg_item = self.addRect(
            0, 0, w, h,
            QPen(Qt.GlobalColor.black, 0.3),
            QBrush(Qt.GlobalColor.white),
        )
        self._bg_item.setZValue(0)

        # Title block: try DXF (vector) → PDF (raster) → programmatic
        use_external_title = False

        dxf_path = TITLE_BLOCK_DXFS.get(self._sheet.paper_size)
        if dxf_path and os.path.isfile(dxf_path):
            tb_dxf = TitleBlockDxfItem(dxf_path, w, h)
            if tb_dxf.is_valid():
                self.addItem(tb_dxf)
                self._title_tb = tb_dxf
                use_external_title = True

        if not use_external_title:
            pdf_path = TITLE_BLOCK_PDFS.get(self._sheet.paper_size)
            if pdf_path:
                tb_pdf = TitleBlockPdfItem(pdf_path, w, h)
                if tb_pdf.pixmap() is not None and not tb_pdf.pixmap().isNull():
                    self.addItem(tb_pdf)
                    self._title_tb = tb_pdf
                    use_external_title = True

        # Drawing border (skip when external DXF/PDF artwork provides its own)
        bx, by = MARGIN, MARGIN
        bw, bh = w - 2 * MARGIN, h - 2 * MARGIN
        if not use_external_title:
            border = self.addRect(
                bx, by, bw, bh,
                QPen(Qt.GlobalColor.black, 0.5),
                QBrush(Qt.BrushStyle.NoBrush),
            )
            border.setZValue(2)

        # Programmatic title block (fallback)
        self._title = TitleBlockItem(w, h)
        self._title.fields = self._sheet.title_block_fields
        self.addItem(self._title)
        if use_external_title:
            self._title.hide()

        # Field overlay removed — DXF artwork already contains placeholder text
        # as geometry; the programmatic overlay produced misaligned duplicates.

        self.setSceneRect(-20, -20, w + 40, h + 40)

        # Rebuild viewports from sheet data
        for sv_data in self._sheet.sheet_views:
            self._create_viewport(sv_data)

        # Rebuild annotations from sheet data
        for ann_data in self._sheet.annotations:
            self._create_annotation(ann_data)

    # ── Viewport management ──────────────────────────────────────────────

    def _create_viewport(self, data: SheetViewData) -> SheetViewport:
        vp = SheetViewport(data, self._resolver)
        vp.navigate_requested.connect(self._on_navigate)
        vp.delete_requested.connect(self._on_delete_viewport)
        vp.properties_requested.connect(self._on_viewport_properties)
        self.addItem(vp)
        self._viewports.append(vp)
        return vp

    def add_viewport(self, data: SheetViewData) -> SheetViewport:
        if not data.view_number:
            data.view_number = str(len(self._sheet.sheet_views) + 1)
        self._sheet.sheet_views.append(data)
        vp = self._create_viewport(data)
        self._update_scale_field()
        return vp

    def remove_viewport(self, viewport: SheetViewport):
        if viewport in self._viewports:
            self._viewports.remove(viewport)
        if viewport.data in self._sheet.sheet_views:
            self._sheet.sheet_views.remove(viewport.data)
        self.removeItem(viewport)
        self._update_scale_field()

    def get_viewports(self) -> list[SheetViewport]:
        return list(self._viewports)

    def update_from_sheet(self, sheet: Sheet):
        self._sheet = sheet
        self._setup()

    def _update_scale_field(self):
        self._sheet.title_block_fields["Scale"] = _compute_scale_field(self._sheet)
        if self._title:
            self._title.update()
        if self._field_overlay:
            self._field_overlay.update()

    def _on_navigate(self, view_type: str, view_name: str):
        self.navigate_to_view.emit(view_type, view_name)

    def _on_delete_viewport(self, viewport):
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda vp=viewport: self.remove_viewport(vp))

    def _on_viewport_properties(self, viewport):
        dlg = SheetViewPropertiesDialog(
            viewport.data.source_view_name, viewport.data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            viewport.data.title = dlg.get_title()
            viewport.data.show_border = dlg.get_show_border()
            new_scale = dlg.get_scale()
            if new_scale != viewport.data.scale:
                viewport.data.scale = new_scale
                if new_scale != 0.0:
                    result = self._resolver.resolve(
                        viewport.data.source_view_type, viewport.data.source_view_name)
                    if result:
                        _, src_rect = result
                        viewport.data.w = src_rect.width() * new_scale
                        viewport.data.h = src_rect.height() * new_scale
            pos = dlg.get_position()
            if pos:
                viewport.data.x, viewport.data.y = pos
            size = dlg.get_size()
            if size:
                viewport.data.w, viewport.data.h = size
            viewport.setPos(viewport.data.x, viewport.data.y)
            viewport.mark_dirty()
            viewport.prepareGeometryChange()
            self._update_scale_field()

    # ── Annotation management ────────────────────────────────────────────

    def _create_annotation(self, data: TextAnnotationData) -> TextAnnotationItem:
        """Build a TextAnnotationItem from existing data.

        Does NOT touch sheet.annotations — called from _setup() over an
        already-populated list, so appending here would double the data.

        Args:
            data: The TextAnnotationData that the new item will share by
                reference (same pattern as _create_viewport / SheetViewData).

        Returns:
            The newly created and added TextAnnotationItem.
        """
        item = TextAnnotationItem(data)
        item.delete_requested.connect(self._on_delete_annotation)
        item.properties_requested.connect(self._on_annotation_properties)
        self.addItem(item)
        self._annotations.append(item)
        return item

    def _do_add_annotation(self, data: TextAnnotationData) -> TextAnnotationItem:
        """Silent primitive: ensure data is registered in the sheet, then build the item.

        Args:
            data: TextAnnotationData to add.

        Returns:
            The newly created TextAnnotationItem.
        """
        if data not in self._sheet.annotations:
            self._sheet.annotations.append(data)
        return self._create_annotation(data)

    def _do_remove_annotation_by_data(self, data: TextAnnotationData) -> None:
        """Remove the item(s) matching *data* from the scene and sheet list.

        Args:
            data: The TextAnnotationData whose owning item should be removed.
        """
        for item in list(self._annotations):
            if item.data is data:
                self._annotations.remove(item)
                self.removeItem(item)
        if data in self._sheet.annotations:
            self._sheet.annotations.remove(data)

    def add_annotation(self, data: TextAnnotationData) -> TextAnnotationItem:
        """Add a text annotation to the scene and persist it in the sheet.

        No undo support yet — Task 7 routes creation through a command.

        Args:
            data: TextAnnotationData describing the new annotation.

        Returns:
            The created TextAnnotationItem.
        """
        return self._do_add_annotation(data)

    def remove_annotation(self, item: TextAnnotationItem) -> None:
        """Remove *item* from the scene and from sheet.annotations.

        Args:
            item: The TextAnnotationItem to remove.
        """
        self._do_remove_annotation_by_data(item.data)

    def get_annotations(self) -> list[TextAnnotationItem]:
        """Return a snapshot list of all live TextAnnotationItems on this scene.

        Returns:
            A new list (not the internal list) of TextAnnotationItem instances.
        """
        return list(self._annotations)

    # ── Place-mode (Task 5) ──────────────────────────────────────────────

    def begin_place_text(self, pos: QPointF) -> TextAnnotationItem:
        """Place a transient TextAnnotationItem at *pos* and enter edit mode.

        The item is added to the scene but is NOT tracked in sheet.annotations
        until commit_place_text() confirms it is non-empty. This lets an empty
        Esc/focus-out cancel leave absolutely nothing behind.

        All lengths in paper mm; *pos* is clamped to the paper rect.

        Args:
            pos: Desired placement position in scene (paper-mm) coordinates.

        Returns:
            The newly created TextAnnotationItem in inline-edit mode.
        """
        pw, ph = PAPER_SIZES[self._sheet.paper_size]
        x = max(0.0, min(pos.x(), pw))
        y = max(0.0, min(pos.y(), ph))
        data = TextAnnotationData(x=x, y=y, text="")
        item = TextAnnotationItem(data)  # TRANSIENT: not tracked, not in sheet
        self.addItem(item)
        self._pending_text = item
        item.begin_edit()
        return item

    def commit_place_text(self, item: TextAnnotationItem) -> None:
        """Finalise or discard a pending placement item.

        Reads the current plain-text from *item*. If it is blank (empty or
        whitespace-only) the transient item is silently removed and nothing is
        tracked. Otherwise the item is removed and its data is persisted via
        add_annotation(), creating a properly tracked replacement item on the
        scene. Task 7 will swap the add_annotation() call for an AddText
        undo command.

        Args:
            item: The TextAnnotationItem returned by begin_place_text().
        """
        self._pending_text = None
        text = item.toPlainText()
        self.removeItem(item)           # discard the transient editor item
        if text.strip() == "":
            return                      # auto-delete empty; nothing tracked
        item.data.text = text
        self.add_annotation(item.data)  # Task 7 swaps for AddTextAnnotationCommand

    def _on_delete_annotation(self, item: TextAnnotationItem) -> None:
        """Slot: defer-remove *item* via QTimer to avoid reentrant scene changes.

        Mirrors _on_delete_viewport — uses QTimer.singleShot(0) to defer the
        removeItem call out of the item's own signal handler. Skips items
        whose inline editor is still active.

        Args:
            item: The TextAnnotationItem that emitted delete_requested.
        """
        if getattr(item, "_editing", False):
            return
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda it=item: self.remove_annotation(it))

    def _on_annotation_properties(self, item: TextAnnotationItem) -> None:
        """Slot: open annotation properties dialog (Task 6) or push undo command (Task 7).

        Args:
            item: The TextAnnotationItem that emitted properties_requested.
        """
        pass  # implemented in Task 6 (dialog) / Task 7 (command)

    # ── Public API (preserved) ──────────────────────────────────────────

    @property
    def paper_size(self) -> str:
        return self._sheet.paper_size

    @paper_size.setter
    def paper_size(self, size: str):
        if size in PAPER_SIZES:
            self._sheet.paper_size = size
            self._setup()

    @property
    def sheet(self) -> Sheet:
        return self._sheet

    @property
    def title_block(self) -> TitleBlockItem:
        return self._title

    def refresh_viewport(self):
        for vp in self._viewports:
            vp.mark_dirty()

    def dispose(self):
        """Disconnect every viewport's source-change signal.

        Call this on a transient PaperScene built only for export/print
        before discarding it, to avoid leaking ``changed`` connections into
        the live model/elevation scenes.
        """
        for vp in self._viewports:
            vp.disconnect_source()


# ─────────────────────────────────────────────────────────────────────────────
# Title-block editor dialog
# ─────────────────────────────────────────────────────────────────────────────

class TitleBlockDialog(QDialog):
    def __init__(self, title_block_or_sheet, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Title Block")
        # Accept either a TitleBlockItem (legacy) or Sheet
        if hasattr(title_block_or_sheet, 'title_block_fields'):
            self._fields = title_block_or_sheet.title_block_fields
            self._tb = None
        else:
            self._tb = title_block_or_sheet
            self._fields = title_block_or_sheet.fields

        layout = QFormLayout(self)
        self._edits: dict[str, QLineEdit] = {}

        for key, value in self._fields.items():
            edit = QLineEdit(value)
            if key == "Scale":
                edit.setReadOnly(True)
                edit.setStyleSheet("background: #f0f0f0;")
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
            if key != "Scale":
                self._fields[key] = edit.text()
        if self._tb is not None:
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
    sheet : Sheet
        The sheet data model driving the paper layout.
    resolver : ViewResolver
        Resolves source view type + name to (scene, rect) pairs.
    """

    navigate_to_view = pyqtSignal(str, str)

    def __init__(self, sheet: Sheet, resolver: ViewResolver, parent=None):
        super().__init__(parent)
        self._sheet = sheet
        self._resolver = resolver

        self.paper_scene = PaperScene(sheet, resolver)
        self.paper_scene.navigate_to_view.connect(self.navigate_to_view.emit)

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

        self._add_text_btn = QPushButton("Add Text")
        self._add_text_btn.setCheckable(True)
        self._add_text_btn.setToolTip("Click to place a text annotation on the sheet")
        toolbar.addWidget(self._add_text_btn)

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
        self.view = PaperGraphicsView(self.paper_scene)
        layout.addWidget(self.view)

        # Wire Add Text button to view (view must exist first)
        self._add_text_btn.toggled.connect(self.view.set_add_text_mode)
        self.view._add_text_btn = self._add_text_btn

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
        # Sync programmatic title block fields from sheet
        self.paper_scene.title_block.fields = self._sheet.title_block_fields
        self.paper_scene.refresh_viewport()

    def edit_title_block(self):
        """Public: open the title block editor dialog."""
        self._edit_title()

    def _refresh(self):
        self.paper_scene.refresh_viewport()

    def _fit(self):
        self.view.fitInView(self.paper_scene.sceneRect(),
                            Qt.AspectRatioMode.KeepAspectRatio)
