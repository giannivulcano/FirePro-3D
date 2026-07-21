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
from .constants import (
    DEFAULT_TEXT_HEIGHT_MM, TEXT_METRIC_REF_PX, MIN_TEXT_WRAP_WIDTH_MM,
    SELECTION_OUTLINE_COLOR, SELECTION_OUTLINE_WIDTH_MM,
    SELECTION_GRIP_OUTLINE_WIDTH_MM, SELECTION_GRIP_SIZE_MM,
    TEXT_BOX_MARGIN_MM,
    TB_CELL_PAD_MM, TB_LABEL_ROW_MM, TB_REV_ROW_MM, TB_LABEL_CAP_FRAC,
    TB_REV_CAP_MM, TB_LABEL_CAP_MIN_MM, TB_REV_PEN_MM,
)
from .scale_manager import ScaleManager
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QGraphicsPixmapItem, QGraphicsObject, QGraphicsTextItem,
    QGraphicsSceneContextMenuEvent, QComboBox,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QGraphicsDropShadowEffect,
    QMenu, QCheckBox, QColorDialog,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF, QSize, QByteArray, pyqtSignal
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QFont, QFontMetricsF, QTransform, QPixmap,
    QPainterPath, QImage, QUndoStack,
)
from .paper_commands import (
    AddTextAnnotationCommand, DeleteTextAnnotationCommand,
    MoveTextAnnotationCommand, ResizeTextBoxCommand,
    EditTextCommand, FormatTextCommand,
    AddViewportCommand, RemoveViewportCommand,
    ViewportGeometryCommand, ChangeViewportPropertiesCommand,
    _find_viewport,
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
    box_height_mm: float = 0.0                   # 0 = auto-fit content; >0 = stored box height
    font_family: str = ""                        # "" => Arial default
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = "#000000"                       # authored hex, default black
    align: str = "L"                             # 'L' | 'C' | 'R'
    opaque_bg: bool = False
    type: str = "text"                           # discriminator for future annotation types

    def to_dict(self) -> dict:
        return {
            "type": self.type, "text": self.text,
            "x": self.x, "y": self.y,
            "height_mm": self.height_mm, "wrap_width_mm": self.wrap_width_mm,
            "box_height_mm": self.box_height_mm,
            "font_family": self.font_family,
            "bold": self.bold, "italic": self.italic, "underline": self.underline,
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
            box_height_mm=float(d.get("box_height_mm", 0.0)),
            font_family=d.get("font_family", ""),
            bold=bool(d.get("bold", False)), italic=bool(d.get("italic", False)),
            underline=bool(d.get("underline", False)),
            color=d.get("color", "#000000"), align=d.get("align", "L"),
            opaque_bg=bool(d.get("opaque_bg", False)),
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
    revisions: list[dict] = field(default_factory=list)
    """Revision history for this sheet. Each entry: {"no", "description", "date"}."""

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
            "revisions": [dict(r) for r in self.revisions],
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
            revisions=[dict(r) for r in d.get("revisions", [])],
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

_GRIP_SIZE = SELECTION_GRIP_SIZE_MM   # alias kept for SheetViewport internal use
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
        self._geom_at_press = None   # (x, y, w, h) captured on mousePress

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
            _draw_mm_text(
                painter,
                vp_rect,
                f"View not found:\n{self._data.source_view_name}",
                cap_mm=3.0,
                color="#8b0000",
                align=Qt.AlignmentFlag.AlignCenter,
            )
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
                painter.setPen(QPen(QColor(SELECTION_OUTLINE_COLOR),
                                    SELECTION_OUTLINE_WIDTH_MM, Qt.PenStyle.DashLine))
            else:
                painter.setPen(QPen(Qt.GlobalColor.black, 0.3))
            painter.drawRect(vp_rect)
        elif self.isSelected():
            # Still show selection indicator even without border
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(SELECTION_OUTLINE_COLOR),
                                SELECTION_OUTLINE_WIDTH_MM, Qt.PenStyle.DashLine))
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
        _draw_mm_text(
            painter,
            QRectF(bubble_cx - bubble_r, bubble_cy - bubble_r,
                   bubble_r * 2, bubble_r * 2),
            self._data.view_number or "1",
            2.0,
            bold=True,
            align=Qt.AlignmentFlag.AlignCenter,
        )

        # Horizontal line from bubble right perimeter to viewport edge
        line_x_start = bubble_cx + bubble_r
        painter.setPen(QPen(Qt.GlobalColor.black, 0.3))
        painter.drawLine(QPointF(line_x_start, bubble_cy),
                         QPointF(w, bubble_cy))

        # Title text — ALL CAPS, bold, ABOVE the line
        text_x = line_x_start + 1.5
        title_rect_above = QRectF(text_x, title_y, w - text_x, bubble_cy - title_y - 0.3)
        _draw_mm_text(
            painter,
            title_rect_above,
            self._data.title.upper(),
            2.2,
            bold=True,
            align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
        )

        # Scale text below the line
        if self._data.scale == 0.0:
            scale_text = "NTS"
        else:
            scale_text = float_to_scale_str(self._data.scale)
        title_rect_below = QRectF(text_x, bubble_cy + 0.3, w - text_x, bubble_r + 0.5)
        _draw_mm_text(
            painter,
            title_rect_below,
            scale_text,
            1.6,
            align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            color="#444444",
        )

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
        painter.setPen(QPen(QColor(SELECTION_OUTLINE_COLOR), SELECTION_GRIP_OUTLINE_WIDTH_MM))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        for r in self._grip_rects():
            painter.drawRect(r)

    def _hit_grip(self, pos: QPointF) -> int:
        for i, r in enumerate(self._grip_rects()):
            if r.contains(pos):
                return i
        return -1

    def mousePressEvent(self, event):
        # Snapshot geometry on every press so move/resize releases can push a
        # single ViewportGeometryCommand (covers both the grip-resize branch
        # and the plain-move branch).
        self._geom_at_press = (self._data.x, self._data.y,
                               self._data.w, self._data.h)
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
            self._push_geometry_if_changed()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._push_geometry_if_changed()

    def _push_geometry_if_changed(self):
        """Push a ViewportGeometryCommand if geometry changed since mousePress.

        Records one undo command per completed move/resize gesture. The live
        data is already current (synced during the drag); the command is for
        undo history only. No-op when the geometry is unchanged, when there is
        no captured press geometry, or when a command is being applied.
        """
        old = self._geom_at_press
        self._geom_at_press = None
        if old is None:
            return
        new = (self._data.x, self._data.y, self._data.w, self._data.h)
        if old == new:
            return
        scene = self.scene()
        if scene is None or not hasattr(scene, "_push_viewport_geometry"):
            return
        scene._push_viewport_geometry(self._data, old, new)

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
            event.accept()   # mirror TextAnnotationItem: don't propagate Delete
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

    _ALIGN = {
        "L": Qt.AlignmentFlag.AlignLeft,
        "C": Qt.AlignmentFlag.AlignCenter,
        "R": Qt.AlignmentFlag.AlignRight,
    }
    _GRIP_MM = SELECTION_GRIP_SIZE_MM   # paper-mm size of grip squares (shared selection style)

    def __init__(self, data: "TextAnnotationData", parent=None):
        super().__init__(data.text, parent)
        self._data = data
        self._editing = False
        self._text_before_edit = data.text
        self._pos_at_press = None
        self._wrap_at_press = None
        self._box_height_at_press = None    # stored box height at the start of a resize
        self._x_at_press = None             # anchor x when a left-corner drag starts
        self._y_at_press = None             # anchor y when a top-handle drag starts
        self._right_at_press = None         # pinned right edge for left-corner drags
        self._bottom_at_press = None        # pinned bottom edge for top-handle drags
        self._grip_handle = None            # handle index 0-7 (TL,TM,TR,ML,MR,BL,BM,BR) or None
        self._grip_corner = None            # deprecated alias kept for back-compat (unused)
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
        f.setUnderline(d.underline)
        f.setPixelSize(TEXT_METRIC_REF_PX)
        self.setFont(f)
        self.setDefaultTextColor(QColor(d.color))
        opt = self.document().defaultTextOption()
        opt.setAlignment(self._ALIGN.get(d.align, Qt.AlignmentFlag.AlignLeft))
        self.document().setDefaultTextOption(opt)
        cap = QFontMetricsF(f).capHeight()
        h = d.height_mm if d.height_mm > 0 else DEFAULT_TEXT_HEIGHT_MM
        scale = h / cap if cap > 0 else 1.0
        self.setScale(scale)
        # Inner margin: set BEFORE wrap/auto-width so idealWidth() accounts for it.
        if scale > 0:
            self.document().setDocumentMargin(TEXT_BOX_MARGIN_MM / scale)
        if d.wrap_width_mm > 0 and scale > 0:
            self.setTextWidth(d.wrap_width_mm / scale)
        else:
            self.setTextWidth(-1)
            self.setTextWidth(self.document().idealWidth())

    def _box_rect_local(self) -> QRectF:
        """Return the box bounding rect in item-local unscaled coordinates.

        Width comes from the text layout (textWidth already reflects wrap).
        Height is max(content height, stored box_height_mm / scale) so the box
        auto-grows with content but never shrinks below the stored height.

        Returns:
            QRectF(0, 0, width, effective_height) in local unscaled coords.
        """
        content = super().boundingRect()
        width = content.width()
        scale = self.scale() or 1.0
        box_h_mm = self._data.box_height_mm
        if box_h_mm > 0 and scale > 0:
            height = max(content.height(), box_h_mm / scale)
        else:
            height = content.height()
        return QRectF(0, 0, width, height)

    def boundingRect(self) -> QRectF:
        """Return the item's visual/selection extent — padded for the selection halo.

        Grips are squares centred ON the box corners (half of each hangs outside
        the box).  Without padding Qt's dirty-region tracking misses the overhang
        and leaves stale trails when the item is dragged.  Padding is applied
        unconditionally (not only when selected) so Qt never needs a
        prepareGeometryChange on every selection toggle.

        Everything that means "the visual box" (opaque-bg fill, selection boundary,
        grip placement, resize math) keeps using _box_rect_local() — ONLY
        boundingRect grows.

        Returns:
            The box rect expanded by the selection-grip halo in local unscaled
            coordinates.
        """
        rect = self._box_rect_local()
        s = self.scale() or 1.0
        pad = (SELECTION_GRIP_SIZE_MM / 2 + SELECTION_GRIP_OUTLINE_WIDTH_MM) / s
        return rect.adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        """Full-box hit area — grab anywhere in the box, not just on the glyphs.

        QGraphicsTextItem's default shape is the text-content rect, which makes
        the empty area of a tall box (and the outer half of the border-straddling
        grips) miss the item entirely. While selected, the grip halo is included
        so every handle square is fully clickable. Only ever WIDER than the
        default — narrowing shape() breaks Qt's paint culling.
        """
        path = QPainterPath()
        path.addRect(self.boundingRect() if self.isSelected()
                     else self._box_rect_local())
        return path

    def contains(self, point) -> bool:
        """Point hit-test via shape() — QGraphicsTextItem overrides contains()
        with its own text-content test, so scene point queries (itemAt, click
        routing) would ignore the widened shape() without this override."""
        return self.shape().contains(point)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """Paint the text block with opaque fill, edit frame, and selection grips.

        Renders in order: (1) solid-white knockout over the box rect when
        opaque_bg is set, (2) the text via super(), (3) dashed #88aaff cosmetic
        border while inline-editing (distinct state), (4) canonical selection
        dashed boundary + 8 grips while selected but not editing.

        Grips are drawn in item-local unscaled coords at SELECTION_GRIP_SIZE_MM /
        scale so they appear the correct paper-mm size on screen and in export.

        Args:
            painter: Active QPainter for the scene.
            option: Style option (passed through to super).
            widget: Optional target widget (passed through to super).
        """
        box = self._box_rect_local()
        if self._data.opaque_bg:
            painter.fillRect(box, QColor("#ffffff"))
        super().paint(painter, option, widget)
        if self._editing:
            pen = QPen(QColor("#88aaff"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
        elif self.isSelected():
            s = self.scale() or 1.0
            # Dashed selection boundary
            painter.setPen(QPen(QColor(SELECTION_OUTLINE_COLOR),
                                SELECTION_OUTLINE_WIDTH_MM / s, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
            # 8 grip squares at corners + edge midpoints
            gs = self._GRIP_MM / s
            half = gs / 2
            cx = (box.left() + box.right()) / 2
            cy = (box.top() + box.bottom()) / 2
            handles = [
                QRectF(box.left()  - half, box.top()    - half, gs, gs),  # TL
                QRectF(cx          - half, box.top()    - half, gs, gs),  # TM
                QRectF(box.right() - half, box.top()    - half, gs, gs),  # TR
                QRectF(box.left()  - half, cy           - half, gs, gs),  # ML
                QRectF(box.right() - half, cy           - half, gs, gs),  # MR
                QRectF(box.left()  - half, box.bottom() - half, gs, gs),  # BL
                QRectF(cx          - half, box.bottom() - half, gs, gs),  # BM
                QRectF(box.right() - half, box.bottom() - half, gs, gs),  # BR
            ]
            painter.setPen(QPen(QColor(SELECTION_OUTLINE_COLOR),
                                SELECTION_GRIP_OUTLINE_WIDTH_MM / s))
            painter.setBrush(QBrush(Qt.GlobalColor.white))
            for h in handles:
                painter.drawRect(h)

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
        sc = self.scene()
        if sc is not None:
            sc._editing_item = self

    def commit_edit(self) -> str:
        """Commit the edited text into data and exit edit mode.

        Returns:
            The committed plain-text string (may be empty/whitespace).
        """
        self._editing = False
        sc = self.scene()
        if sc is not None and getattr(sc, "_editing_item", None) is self:
            sc._editing_item = None
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
        scene = self.scene()
        if scene is not None and getattr(scene, "_editing_item", None) is self:
            scene._editing_item = None
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setPlainText(self._text_before_edit)
        self._data.text = self._text_before_edit
        self._apply_format()
        # Esc during place-mode: route through commit_place_text so the
        # transient item is removed and nothing is left tracked.
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

        While editing: Esc always commits — for a pending placement it routes
        through commit_place_text() (empty still auto-discards); for an existing
        block it calls _on_edit_finished() which commits and pushes an
        EditTextCommand so the change is undoable. All other keys (Enter for
        newline, Delete for character) pass through to the editor.
        While not editing: Delete emits delete_requested; other keys delegate
        to super().
        """
        if self._editing:
            if event.key() == Qt.Key.Key_Escape:
                self._on_edit_finished()
                self.clearFocus()
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
        pushes an AddTextAnnotationCommand otherwise. For an existing tracked
        annotation, commits the edit (which applies the new text live) and then
        records the change on the undo stack via the scene's _push_text_edit
        helper (empty content auto-deletes; an unchanged commit pushes nothing).
        """
        scene = self.scene()
        if scene is not None and getattr(scene, "_pending_text", None) is self:
            scene.commit_place_text(self)
            return
        old = self._text_before_edit
        new = self.commit_edit()
        if scene is not None and hasattr(scene, "_push_text_edit"):
            scene._push_text_edit(self._data, old, new)

    def sync_data_from_item(self) -> None:
        """Write the current scene position back into the data object (paper mm)."""
        self._data.x = self.pos().x()
        self._data.y = self.pos().y()

    # ── Property-panel protocol (spec property-panel.md §3.1) ────────────────

    def get_properties(self) -> dict:
        """Return the panel form dict (formatting only; content stays inline)."""
        return _text_panel_properties(self._data)

    def set_property(self, key: str, value) -> None:
        """Apply a panel commit through the paper undo stack.

        On a scene with an undo stack, pushes a FormatTextCommand (one command
        per commit — the panel wraps multi-select in a macro). Off-scene
        (template pattern) or while a command is being applied, writes the
        field directly and reformats.

        Args:
            key: Panel property key.
            value: The committed panel value.
        """
        change = _text_panel_change(self._data, key, value)
        if change is None:
            return
        scene = self.scene()
        stack = getattr(scene, "undo_stack", None) if scene is not None else None
        if stack is not None and not getattr(scene, "_applying_command", False):
            field = next(iter(change))
            old = {field: getattr(self._data, field)}
            stack.push(FormatTextCommand(scene, self._data, old, change))
        else:
            for f, v in change.items():
                setattr(self._data, f, v)
            self.prepareGeometryChange()
            self._apply_format()

    def contextMenuEvent(self, event) -> None:
        """Show the Delete context menu on right-click.

        While inline-editing, delegates to super() so the native copy/paste
        editor menu is shown instead. Formatting is edited via the property
        panel (selection populates it) — there is no Properties dialog.
        """
        if self._editing:
            super().contextMenuEvent(event)
            return
        menu = QMenu()
        delete = menu.addAction("Delete")
        action = menu.exec(event.screenPos())
        if action == delete:
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

    # ── C. 8-handle box resize grips ─────────────────────────────────────────

    # Handle index map (mirrors SheetViewport handle ordering):
    # 0=TL, 1=TM, 2=TR, 3=ML, 4=MR, 5=BL, 6=BM, 7=BR
    _LEFT_HANDLES  = (0, 3, 5)   # move x + shrink/grow wrap (right edge pinned)
    _RIGHT_HANDLES = (2, 4, 7)   # grow/shrink wrap (anchor x pinned)
    _TOP_HANDLES   = (0, 1, 2)   # move y + shrink/grow box height (bottom pinned)
    _BOTTOM_HANDLES = (5, 6, 7)  # grow/shrink box height (anchor y pinned)

    def _corner_grip_rects(self) -> dict:
        """Return the 8 grip hit-rectangles in scene (paper-mm) coordinates.

        Each grip is a _GRIP_MM × _GRIP_MM square centred on the corresponding
        corner or edge midpoint of the logical box (_box_rect_local mapped to
        scene coords). Uses _box_rect_local() — not sceneBoundingRect() — so
        that the padding added to boundingRect() for stale-trail prevention
        (Fix 1, 2026-07-20) does not displace the grip positions. Used by
        mousePressEvent for hit-testing. Keys: "TL","TM","TR","ML","MR","BL","BM","BR".

        Returns:
            dict mapping handle name → QRectF in scene (paper-mm) coordinates.
        """
        sbr = self.mapRectToScene(self._box_rect_local())
        g = self._GRIP_MM
        half = g / 2
        cx = sbr.center().x()
        cy = sbr.center().y()
        return {
            "TL": QRectF(sbr.left()  - half, sbr.top()    - half, g, g),
            "TM": QRectF(cx          - half, sbr.top()    - half, g, g),
            "TR": QRectF(sbr.right() - half, sbr.top()    - half, g, g),
            "ML": QRectF(sbr.left()  - half, cy           - half, g, g),
            "MR": QRectF(sbr.right() - half, cy           - half, g, g),
            "BL": QRectF(sbr.left()  - half, sbr.bottom() - half, g, g),
            "BM": QRectF(cx          - half, sbr.bottom() - half, g, g),
            "BR": QRectF(sbr.right() - half, sbr.bottom() - half, g, g),
        }

    def _hit_grip_handle(self, scene_pos) -> "int | None":
        """Return the 0-based handle index hit by scene_pos, or None.

        Handle indices: 0=TL, 1=TM, 2=TR, 3=ML, 4=MR, 5=BL, 6=BM, 7=BR.

        Args:
            scene_pos: QPointF in scene (paper-mm) coordinates.

        Returns:
            Integer handle index (0-7), or None if no grip was hit.
        """
        names = ["TL", "TM", "TR", "ML", "MR", "BL", "BM", "BR"]
        grips = self._corner_grip_rects()
        for i, name in enumerate(names):
            if grips[name].contains(scene_pos):
                return i
        return None

    def mousePressEvent(self, event) -> None:
        """Start an 8-handle box resize drag when a grip is hit; otherwise begin move.

        Left handles (TL/ML/BL): pin right edge, move anchor + adjust wrap.
        Right handles (TR/MR/BR): pin anchor, adjust wrap (x unchanged).
        Top handles (TL/TM/TR): pin bottom edge, move anchor y + adjust box height.
        Bottom handles (BL/BM/BR): pin anchor y, adjust box height.
        Corners = both axes. Midpoints = one axis only.

        On auto-width (wrap_width_mm == 0), seeds from visual width.
        On auto-height (box_height_mm == 0), seeds from current content height in mm.
        """
        if self.isSelected():
            handle = self._hit_grip_handle(event.scenePos())
            if handle is not None:
                self._resizing = True
                self._grip_handle = handle
                # Seed x/wrap
                self._x_at_press = self._data.x
                if self._data.wrap_width_mm > 0:
                    self._wrap_at_press = self._data.wrap_width_mm
                else:
                    self._wrap_at_press = self.sceneBoundingRect().width()
                self._right_at_press = self._x_at_press + self._wrap_at_press
                # Seed y/box_height
                self._y_at_press = self._data.y
                scale = self.scale() or 1.0
                content_h_mm = super().boundingRect().height() * scale
                if self._data.box_height_mm > 0:
                    self._box_height_at_press = self._data.box_height_mm
                else:
                    self._box_height_at_press = content_h_mm
                self._bottom_at_press = self._y_at_press + self._box_height_at_press
                # Keep legacy alias in sync for any code still reading _grip_corner
                _names = ["TL", "TM", "TR", "ML", "MR", "BL", "BM", "BR"]
                self._grip_corner = _names[handle]
                event.accept()
                return
        self._pos_at_press = (self._data.x, self._data.y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Adjust wrap_width_mm, box_height_mm, x, and y during an 8-handle drag.

        Left handles: pin right edge; x and wrap adjust.
        Right handles: pin anchor x; only wrap adjusts.
        Top handles: pin bottom edge; y and box_height adjust.
        Bottom handles: pin anchor y; only box_height adjusts.
        Corner handles: both axes. Mid-edge handles: one axis.
        Vertical resize never touches font height_mm.
        """
        if self._resizing:
            handle = self._grip_handle
            sx = event.scenePos().x()
            sy = event.scenePos().y()
            scale = self.scale() or 1.0
            content_h_mm = super().boundingRect().height() * scale

            # Horizontal axis
            if handle in self._LEFT_HANDLES:
                right = self._right_at_press
                new_x = min(sx, right - MIN_TEXT_WRAP_WIDTH_MM)
                new_w = right - new_x
                self._data.x = new_x
                self._data.wrap_width_mm = new_w
                self.setPos(new_x, self._data.y)
            elif handle in self._RIGHT_HANDLES:
                new_w = max(MIN_TEXT_WRAP_WIDTH_MM, sx - self._x_at_press)
                self._data.wrap_width_mm = new_w

            # Vertical axis
            if handle in self._TOP_HANDLES:
                bottom = self._bottom_at_press
                min_h = content_h_mm
                new_h = max(min_h, bottom - sy)
                actual_dy = self._box_height_at_press - new_h
                new_y = self._y_at_press + actual_dy
                self._data.y = new_y
                self._data.box_height_mm = new_h
                self.setPos(self._data.x, new_y)
            elif handle in self._BOTTOM_HANDLES:
                min_h = content_h_mm
                new_h = max(min_h, sy - self._y_at_press)
                self._data.box_height_mm = new_h

            self.prepareGeometryChange()
            self._apply_format()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Finish a resize or move drag and notify the undo hook."""
        if self._resizing:
            self._resizing = False
            handle = self._grip_handle
            self._grip_handle = None
            self._grip_corner = None
            old_state = (self._x_at_press, self._y_at_press,
                         self._wrap_at_press, self._box_height_at_press)
            new_state = (self._data.x, self._data.y,
                         self._data.wrap_width_mm, self._data.box_height_mm)
            self._x_at_press = None
            self._y_at_press = None
            self._wrap_at_press = None
            self._box_height_at_press = None
            self._right_at_press = None
            self._bottom_at_press = None
            self._on_box_resized(old_state, new_state)
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

        Routes to the scene's _push_text_move helper to record a
        MoveTextAnnotationCommand on the undo stack. The data is already
        updated live by itemChange; the command is for undo history only.

        Args:
            old_xy: (x, y) paper-mm position before the drag.
            new_xy: (x, y) paper-mm position after the drag.
        """
        scene = self.scene()
        if scene is not None and hasattr(scene, "_push_text_move"):
            scene._push_text_move(self._data, old_xy, new_xy)

    def _on_box_resized(self, old_state: tuple, new_state: tuple) -> None:
        """Hook called after a completed 8-handle box resize drag.

        Routes to the scene's _push_text_box_resize helper to record a
        ResizeTextBoxCommand on the undo stack. x, y, wrap_width_mm, and
        box_height_mm are already updated live by mouseMoveEvent; the command
        is for undo history only.

        Args:
            old_state: ``(old_x, old_y, old_wrap_width_mm, old_box_height_mm)``
                       before the resize.
            new_state: ``(new_x, new_y, new_wrap_width_mm, new_box_height_mm)``
                       after the resize.
        """
        scene = self.scene()
        if scene is not None and hasattr(scene, "_push_text_box_resize"):
            scene._push_text_box_resize(self._data, old_state, new_state)


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
# Sheet-text panel helpers (spec property-panel.md §3.1)
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


_PANEL_ALIGN_TO_CODE = {"Left": "L", "Center": "C", "Right": "R"}
_PANEL_CODE_TO_ALIGN = {"L": "Left", "C": "Center", "R": "Right"}


MM_PER_PT = 25.4 / 72.0   # 1 typographic point in paper mm


def _text_cap_ratio(data: "TextAnnotationData") -> float:
    """Return the cap-height / em-size ratio for *data*'s font.

    Word-style font sizes ("12 pt") measure the em body; stored height_mm is
    cap height (§5.3). This ratio converts between the two for the panel's
    pt display. Computed at TEXT_METRIC_REF_PX for metric precision (§9.4).

    Args:
        data: The TextAnnotationData whose font (family/bold/italic) applies.

    Returns:
        capHeight / em ratio (e.g. ~0.716 for Arial); 0.7 fallback if the
        metric degenerates.
    """
    f = QFont(data.font_family) if data.font_family else QFont("Arial")
    f.setBold(data.bold)
    f.setItalic(data.italic)
    f.setPixelSize(TEXT_METRIC_REF_PX)
    ratio = QFontMetricsF(f).capHeight() / TEXT_METRIC_REF_PX
    return ratio if ratio > 0 else 0.7


def _font_pt_from_mm(data: "TextAnnotationData", mm: float) -> float:
    """Convert a stored cap height (mm) to the Word-style font pt size."""
    return mm / (MM_PER_PT * _text_cap_ratio(data))


def _mm_from_font_pt(data: "TextAnnotationData", pt: float) -> float:
    """Convert a Word-style font pt size to the stored cap height (mm)."""
    return pt * MM_PER_PT * _text_cap_ratio(data)


def _format_height_pt(data: "TextAnnotationData", mm: float) -> str:
    """Format a cap height for the panel: Word-style pt, e.g. ``"12 pt"``."""
    pt = round(_font_pt_from_mm(data, mm), 1)
    return f"{pt:g} pt"


def _parse_height_pt(data: "TextAnnotationData", text: str) -> float | None:
    """Parse the panel height field: bare numbers / ``pt`` mean font points.

    ``"12"`` and ``"12 pt"`` parse as a Word-style 12 pt font size (converted
    to cap-height mm via the font's metrics). Explicit dimension strings such
    as ``'1/8"'`` or ``"3mm"`` still parse as literal cap heights through
    :func:`_parse_text_height_mm`.

    Args:
        data: The TextAnnotationData whose font drives the pt conversion.
        text: The user's input string.

    Returns:
        Cap height in mm, or None if unparseable.
    """
    t = text.strip().lower()
    if t.endswith("pt"):
        t = t[:-2].strip()
    try:
        return _mm_from_font_pt(data, float(t))
    except ValueError:
        return _parse_text_height_mm(text)


def _text_panel_properties(data: "TextAnnotationData") -> dict:
    """Property-panel form dict for a sheet text annotation (§9.6 panel path).

    Formatting only — content is edited inline on the canvas and wrap width
    via the drag grip. Height displays/parses as a Word-style pt font size
    (storage stays cap-height mm). The trailing "Leader" label row is a
    placeholder for the leader follow-up task (real leader rows will replace
    it).

    Args:
        data: The TextAnnotationData to render.

    Returns:
        An ordered property dict in PropertyManager meta format.
    """
    return {
        "Font": {"type": "font", "value": data.font_family or "Arial"},
        "Height": {"type": "dimension", "value": data.height_mm,
                   "value_mm": data.height_mm,
                   "parser": lambda text, d=data: _parse_height_pt(d, text),
                   "formatter": lambda mm, d=data: _format_height_pt(d, mm),
                   "minimum": 0.0},
        "Bold": {"type": "bool", "value": data.bold},
        "Italic": {"type": "bool", "value": data.italic},
        "Underline": {"type": "bool", "value": data.underline},
        "Color": {"type": "color", "value": data.color or "#000000"},
        "Alignment": {"type": "enum",
                      "value": _PANEL_CODE_TO_ALIGN.get(data.align, "Left"),
                      "options": ["Left", "Center", "Right"]},
        "Opaque Background": {"type": "bool", "value": data.opaque_bg},
        "Leader": {"type": "label", "value": "None"},
    }


def _text_panel_change(data: "TextAnnotationData", key: str, value) -> dict | None:
    """Map a panel commit to a ``{field: new_value}`` change dict.

    Coerces panel display values to data-field values (alignment labels to
    L/C/R codes, checkbox states to bool, height to float). Non-positive
    heights are rejected (§9.6 — a zero cap height must never be stored).

    Args:
        data: The target TextAnnotationData.
        key: Panel property key (e.g. "Bold").
        value: The committed panel value.

    Returns:
        A one-entry change dict, or None when the key is unknown, the value
        invalid, or the value unchanged.
    """
    if key == "Font":
        field, new = "font_family", str(value)
        # "" renders as Arial (the panel seeds the picker with it), so
        # re-committing "Arial" over an empty field is a no-op — without this,
        # the first font-picker interaction pushes a phantom undo command.
        if (getattr(data, field) or "Arial") == new:
            return None
        return {field: new}
    elif key == "Height":
        try:
            new = float(value)
        except (TypeError, ValueError):
            return None
        if new <= 0:
            return None
        field = "height_mm"
    elif key == "Bold":
        field, new = "bold", bool(value)
    elif key == "Italic":
        field, new = "italic", bool(value)
    elif key == "Underline":
        field, new = "underline", bool(value)
    elif key == "Color":
        field, new = "color", str(value)
    elif key == "Alignment":
        # Strict: the multi-select "< mixed >" placeholder (or any non-label
        # string) must not silently coerce to Left and push a command.
        code = _PANEL_ALIGN_TO_CODE.get(str(value))
        if code is None:
            return None
        field, new = "align", code
    elif key == "Opaque Background":
        field, new = "opaque_bg", bool(value)
    else:
        return None
    if getattr(data, field) == new:
        return None
    return {field: new}


_TEMPLATE_FIELDS = ("height_mm", "font_family", "bold", "italic", "underline",
                    "color", "align", "opaque_bg")


def text_template_to_settings(data: "TextAnnotationData") -> dict:
    """Extract the persistable formatting fields for QSettings storage."""
    return {f: getattr(data, f) for f in _TEMPLATE_FIELDS}


def apply_template_settings(data: "TextAnnotationData", raw: dict) -> None:
    """Restore formatting fields from a QSettings dict onto *data*.

    QSettings (Windows registry backend) may return every value as a string,
    so each field is coerced explicitly. Invalid or non-positive heights fall
    back to DEFAULT_TEXT_HEIGHT_MM — a template must never seed a zero cap
    height (§9.6).

    Args:
        data: The template TextAnnotationData to mutate in place.
        raw: The dict previously produced by text_template_to_settings().
    """
    def _b(v) -> bool:
        return v if isinstance(v, bool) else str(v).lower() == "true"

    if "height_mm" in raw:
        try:
            h = float(raw["height_mm"])
        except (TypeError, ValueError):
            h = 0.0
        data.height_mm = h if h > 0 else DEFAULT_TEXT_HEIGHT_MM
    if "font_family" in raw:
        data.font_family = str(raw["font_family"])
    if "bold" in raw:
        data.bold = _b(raw["bold"])
    if "italic" in raw:
        data.italic = _b(raw["italic"])
    if "underline" in raw:
        data.underline = _b(raw["underline"])
    if "color" in raw:
        data.color = str(raw["color"])
    if "align" in raw:
        a = str(raw["align"])
        data.align = a if a in ("L", "C", "R") else "L"
    if "opaque_bg" in raw:
        data.opaque_bg = _b(raw["opaque_bg"])


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

        # Paper-space undo/redo is dispatched directly in keyPressEvent
        # (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z). A QAction shortcut cannot be used:
        # event() must accept the ShortcutOverride for those keys to beat the
        # window-scoped ribbon Ctrl+Z, which suppresses any QAction shortcut and
        # delivers the keystroke as a plain KeyPress — so keyPressEvent handles it.

        # Match Model_View navigation style
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor("#c0c0c0")))
        # No scrollbars — pan/zoom (and wheel) still navigate the sheet
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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

    def _owner_widget(self):
        """Walk the parent chain to find the widget owning set_add_text_mode.

        Returns:
            The first ancestor widget that has a ``set_add_text_mode`` method
            (typically :class:`PaperSpaceWidget`), or *None* if not found.
        """
        widget = self.parent()
        while widget is not None and not hasattr(widget, "set_add_text_mode"):
            widget = widget.parent()
        return widget

    # ── Delete key handling ────────────────────────────────────────────

    def event(self, event):
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.ShortcutOverride:
            if event.key() == Qt.Key.Key_Delete:
                event.accept()
                return True
            # While a note is being inline-edited, keep Escape for the editor
            # (cancel_edit); otherwise the window-level QShortcut("Escape") in
            # MainWindow steals it. Same reason Delete is accepted above.
            # Also accept Escape while in add-text mode so the window-level
            # QShortcut("Escape") doesn't fire _on_escape before keyPressEvent
            # can cancel the mode.
            if event.key() == Qt.Key.Key_Escape and (
                    getattr(self._paper_scene, "_editing_item", None) is not None
                    or self._add_text_mode):
                event.accept()
                return True
            # Deliver Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z as a plain KeyPress to
            # keyPressEvent (which dispatches to the paper undo stack) instead of
            # letting the window-scoped ribbon Ctrl+Z/Y shortcut fire.
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and event.key() in (Qt.Key.Key_Z, Qt.Key.Key_Y)):
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        # Escape while in add-text mode: cancel placement and exit the mode.
        # event() accepts the ShortcutOverride for Key_Escape when _add_text_mode
        # is True, so the window-level QShortcut("Escape") does not steal this.
        if event.key() == Qt.Key.Key_Escape and self._add_text_mode:
            owner = self._owner_widget()
            if owner is not None:
                owner.set_add_text_mode(False)
            else:
                self.set_add_text_mode(False)
            event.accept()
            return

        # Paper undo/redo — only when NOT inline-editing a note, so the text
        # editor's own Ctrl+Z isn't hijacked. Handled here rather than via a
        # QAction because event() accepts the ShortcutOverride for these keys.
        mods = event.modifiers()
        if (mods & Qt.KeyboardModifier.ControlModifier
                and getattr(self._paper_scene, "_editing_item", None) is None):
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            key = event.key()
            if key == Qt.Key.Key_Z and not shift:
                self._paper_scene.undo_stack.undo()
                event.accept()
                return
            if key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and shift):
                self._paper_scene.undo_stack.redo()
                event.accept()
                return
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
                QTimer.singleShot(0, lambda a=it: scene._undo_stack.push(
                    DeleteTextAnnotationCommand(scene, a.data)))
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
            owner = self._owner_widget()
            if owner is not None:
                owner.set_add_text_mode(False)
            else:
                self.set_add_text_mode(False)
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
# Parametric title block (docs/specs/titleblock-template-system.md)
# ─────────────────────────────────────────────────────────────────────────────

# Project→name mapping must stay in sync with _LEGACY_PROJECT_KEYS in titleblock_template.py
_PROJECT_STD_KEYS = {"Project": "name", "Project Number": "number",
                     "Address": "address", "City": "city", "State": "state",
                     "Client": "client", "Designer": "designer",
                     "Description": "description"}


def build_field_values(sheet: "Sheet", project_info: dict) -> dict:
    """Resolve field values: auto → per-sheet → Project Info → "".

    Precedence per spec §Value Model: later assignments below override earlier
    ones, so Project Info seeds first, sheet fields override it, and the
    auto-computed keys (Scale, Date (auto)) always win.

    Args:
        sheet: The sheet being rendered.
        project_info: The Model_Space._project_info dict.

    Returns:
        Flat value dict for the layout solver; "__revisions__" carries the
        sheet's revision list (oldest-first).
    """
    vals: dict = {}
    for display, info_key in _PROJECT_STD_KEYS.items():
        if project_info.get(info_key):
            vals[display] = project_info[info_key]
    for row in project_info.get("custom", []):
        if isinstance(row, dict) and row.get("key"):
            vals[row["key"]] = row.get("value", "")
    vals.update({k: v for k, v in sheet.title_block_fields.items() if v})
    vals["Scale"] = _compute_scale_field(sheet)           # auto wins
    vals["Date (auto)"] = datetime.date.today().strftime("%d %b %Y")
    vals["__revisions__"] = list(sheet.revisions)
    return vals


def _draw_mm_text(
    painter: QPainter,
    rect: QRectF,
    text: str,
    cap_mm: float,
    *,
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
    color: str = "#000000",
) -> None:
    """Draw text at a true paper-mm cap height (§9.4 primitive).

    Uses the same setPixelSize + painter-scale technique as
    TitleBlockTemplateItem._draw_text_mm so that text size is independent
    of device DPI (fixes the ~2.4× PDF over-sizing bug for view titles).
    """
    f = QFont("Arial")
    f.setBold(bold)
    f.setPixelSize(TEXT_METRIC_REF_PX)
    fm = QFontMetricsF(f)
    cap_px = fm.capHeight() or 1.0
    s = cap_mm / cap_px
    if s <= 0:
        return
    painter.save()
    painter.setFont(f)
    painter.setPen(QPen(QColor(color), 0.1))
    painter.translate(rect.topLeft())
    painter.scale(s, s)
    painter.drawText(
        QRectF(0, 0, rect.width() / s, rect.height() / s),
        align,
        text,
    )
    painter.restore()


class TitleBlockTemplateItem(QGraphicsItem):
    """Paints a SolvedLayout — the single render path for template blocks.

    mm-sized by construction (§9.4): text draws through a painter scale from
    a setPixelSize reference font (point-size APIs are banned here per §9.4).
    Renders fills first, then per-cell content clipped to the strip, then
    borders on top.
    """

    def __init__(self, layout, variant, values: dict, parent=None):
        super().__init__(parent)
        self._layout = layout
        self._variant = variant
        self._values = values
        self.warnings: list[str] = list(layout.warnings)
        self._logo_pixmaps: dict[int, QPixmap] = {}
        for i, cell in enumerate(variant.cells):
            if cell.kind == "logo" and cell.logo_data:
                pm = QPixmap()
                try:
                    raw = QByteArray.fromBase64(cell.logo_data.encode("ascii"))
                    ok = pm.loadFromData(raw, "PNG") and not pm.isNull()
                except UnicodeEncodeError:
                    ok = False
                if not ok:
                    self.warnings.append("Logo image could not be decoded.")
                else:
                    self._logo_pixmaps[i] = pm
        self.setZValue(1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def boundingRect(self) -> QRectF:
        lay, var = self._layout, self._variant
        united = lay.strip_rect.united(lay.area_rect)
        pad = max(
            var.area_border.width_mm,
            var.strip_border.width_mm,
            *(c.border.width_mm for c in var.cells),
        ) / 2
        return united.adjusted(-pad, -pad, pad, pad)

    def _draw_border(self, painter: QPainter, rect: QRectF, style) -> None:
        if not style.visible:
            return
        painter.setPen(QPen(QColor(style.color), style.width_mm))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if style.corner == "fillet" and style.fillet_radius_mm > 0:
            path = QPainterPath()
            path.addRoundedRect(rect, style.fillet_radius_mm,
                                style.fillet_radius_mm)
            painter.drawPath(path)
        else:
            painter.drawRect(rect)

    def _draw_text_mm(self, painter: QPainter, rect: QRectF, lines: list,
                      cell, *, cap_mm: float | None = None,
                      bold: bool | None = None) -> None:
        """Draw wrapped lines at a paper-mm cap height (mm primitive)."""
        f = QFont(cell.font_family or "Arial")
        f.setBold(cell.bold if bold is None else bold)
        f.setItalic(cell.italic)
        f.setPixelSize(TEXT_METRIC_REF_PX)
        fm = QFontMetricsF(f)
        cap_px = fm.capHeight() or 1.0
        s = (cap_mm if cap_mm is not None else cell.cap_height_mm) / cap_px
        if s <= 0:
            return
        painter.save()
        painter.setFont(f)
        painter.setPen(QPen(Qt.GlobalColor.black, 0.1))
        painter.translate(rect.topLeft())
        painter.scale(s, s)
        align = {"left": Qt.AlignmentFlag.AlignLeft,
                 "center": Qt.AlignmentFlag.AlignHCenter,
                 "right": Qt.AlignmentFlag.AlignRight}.get(
                     cell.alignment, Qt.AlignmentFlag.AlignLeft)
        y = 0.0
        for line in lines:
            painter.drawText(
                QRectF(0, y, rect.width() / s, fm.lineSpacing()),
                align | Qt.AlignmentFlag.AlignVCenter, line)
            y += fm.lineSpacing()
        painter.restore()

    def _draw_label(self, painter: QPainter, rect: QRectF, cell) -> None:
        if not cell.label:
            return
        cap = max(TB_LABEL_CAP_MIN_MM, cell.cap_height_mm * TB_LABEL_CAP_FRAC)
        self._draw_text_mm(painter, rect, [cell.label.upper()], cell,
                           cap_mm=cap, bold=False)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        lay, var = self._layout, self._variant
        for i, cell in enumerate(var.cells):
            if cell.fill_color:
                painter.fillRect(lay.cell_rects[i], QColor(cell.fill_color))
        # Hoist ONE clip around the whole content loop (composes with caller
        # clips in export paths via IntersectClip). spec DD-8.
        painter.save()
        painter.setClipRect(lay.strip_rect, Qt.ClipOperation.IntersectClip)
        for i, cell in enumerate(var.cells):
            rect = lay.cell_rects[i]
            inner = rect.adjusted(TB_CELL_PAD_MM, TB_CELL_PAD_MM,
                                  -TB_CELL_PAD_MM, -TB_CELL_PAD_MM)
            self._draw_label(painter, inner, cell)
            content = inner.adjusted(
                0, TB_LABEL_ROW_MM if cell.label else 0.0, 0, 0)
            if cell.kind in ("field", "static_text"):
                self._draw_text_mm(painter, content, lay.cell_lines[i], cell)
            elif cell.kind == "logo":
                pm = self._logo_pixmaps.get(i)
                if pm is not None:
                    target = QRectF(content)
                    # Use float scaling to avoid truncation at small sizes.
                    scaled = QSizeF(pm.size()).scaled(
                        target.size(), Qt.AspectRatioMode.KeepAspectRatio)
                    dx = (target.width() - scaled.width()) / 2
                    dy = (target.height() - scaled.height()) / 2
                    painter.drawPixmap(
                        QRectF(target.left() + dx, target.top() + dy,
                               scaled.width(), scaled.height()),
                        pm, QRectF(pm.rect()))
                # empty logo_data: reserved bordered box, no warning
            elif cell.kind == "revision_table":
                rows = lay.cell_revision_rows.get(i, [])
                y = content.top()
                painter.setPen(QPen(Qt.GlobalColor.black, TB_REV_PEN_MM))
                # Header row — the solver's +1 reservation is this header band.
                self._draw_text_mm(
                    painter,
                    QRectF(content.left(), y, content.width(), TB_REV_ROW_MM),
                    ["No  Description  Date"], cell,
                    cap_mm=TB_REV_CAP_MM, bold=True)
                y += TB_REV_ROW_MM
                painter.drawLine(QPointF(content.left(), y),
                                 QPointF(content.right(), y))
                for rev in rows:
                    line = (f'{rev.get("no", "")}  '
                            f'{rev.get("description", "")}  '
                            f'{rev.get("date", "")}')
                    self._draw_text_mm(
                        painter,
                        QRectF(content.left(), y, content.width(),
                               TB_REV_ROW_MM),
                        [line], cell, cap_mm=TB_REV_CAP_MM, bold=False)
                    y += TB_REV_ROW_MM
                    painter.drawLine(QPointF(content.left(), y),
                                     QPointF(content.right(), y))
            # "stamp": reserved empty bordered area — nothing to draw
        painter.restore()
        for i, cell in enumerate(var.cells):
            if cell.border.visible:
                self._draw_border(painter, lay.cell_rects[i], cell.border)
        self._draw_border(painter, lay.area_rect, var.area_border)
        self._draw_border(painter, lay.strip_rect, var.strip_border)


# ─────────────────────────────────────────────────────────────────────────────
# Paper scene
# ─────────────────────────────────────────────────────────────────────────────

class PaperScene(QGraphicsScene):
    """QGraphicsScene representing one paper layout.

    Coordinate system: 1 scene unit = 1 mm.
    """

    navigate_to_view = pyqtSignal(str, str)
    sheetModified = pyqtSignal()

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
        self._editing_item = None  # TextAnnotationItem currently in inline edit
        self._pending_text: "TextAnnotationItem | None" = None
        self._undo_stack = QUndoStack(self)
        self._applying_command = False
        self._suppress_modified = False
        self._undo_stack.indexChanged.connect(self._on_stack_index_changed)
        self.text_template: "TextAnnotationData | None" = None  # Add-Text seed
        self._template: "TitleBlockTemplate | None" = None
        self._scene_project_info: dict = {}
        self.titleblock_warning: str = ""
        self._setup()

    def _apply(self, fn):
        """Run *fn* with the re-enqueue guard raised.

        Programmatic setPos / add / remove performed by a command's redo/undo
        must not push further commands via the gesture hooks. The guard mirrors
        Model_Space._in_undo_restore.

        Args:
            fn: A zero-argument callable performing the scene mutation.
        """
        self._applying_command = True
        try:
            fn()
        finally:
            self._applying_command = False

    def set_template(self, template: "TitleBlockTemplate | None",
                     project_info: "dict | None" = None) -> None:
        """Install the project template (or None) and rebuild the sheet.

        Rebuild runs through _setup, which is emission-suppressed (§17.7) —
        installing a template never dirties the project by itself.

        Args:
            template: A TitleBlockTemplate object, or None to revert to the
                legacy DXF/PDF/programmatic chain.
            project_info: Optional project-info dict (used by build_field_values).
                When None the existing _scene_project_info is kept.
        """
        self._template = template
        if project_info is not None:
            self._scene_project_info = project_info
        self._suppress_modified = True
        try:
            self._setup()
        finally:
            self._suppress_modified = False

    def _refresh_titleblock(self) -> None:
        """Re-render the title block after value/revision changes (undo cmds).

        Runs _setup emission-suppressed so re-rendering the title block after
        an undo/redo command does not dirty the project.
        """
        self._suppress_modified = True
        try:
            self._setup()
        finally:
            self._suppress_modified = False

    @property
    def undo_stack(self) -> QUndoStack:
        """The paper-space-scoped QUndoStack owned by this scene."""
        return self._undo_stack

    def _on_stack_index_changed(self, _idx: int) -> None:
        """Relay undo-stack activity as a sheet-data mutation.

        indexChanged fires on push, undo, redo AND clear(); the clear during
        a load-path rebuild is suppressed via _suppress_modified so opening a
        project never marks it dirty.
        """
        if not self._suppress_modified:
            self.sheetModified.emit()

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

        # Title block resolution: template → DXF → PDF → programmatic (§8.1)
        use_external_title = False
        self.titleblock_warning = ""

        if self._template is not None:
            variant = self._template.variants.get(self._sheet.paper_size)
            if variant is not None:
                from .titleblock_template import solve_layout
                values = build_field_values(self._sheet, self._scene_project_info)
                sl = solve_layout(variant, w, h, values)
                tb = TitleBlockTemplateItem(sl, variant, values)
                self.addItem(tb)
                self._title_tb = tb
                use_external_title = True
            else:
                self.titleblock_warning = (
                    f"Template '{self._template.name}' has no "
                    f"{self._sheet.paper_size} variant — using built-in "
                    "title block."
                )

        dxf_path = TITLE_BLOCK_DXFS.get(self._sheet.paper_size)
        if not use_external_title and dxf_path and os.path.isfile(dxf_path):
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

    def _do_add_viewport(self, data: SheetViewData) -> SheetViewport:
        """Silent primitive: register *data* in the sheet and build its viewport.

        Preserves the original add_viewport behaviour: assigns a view_number
        when blank, appends to sheet.sheet_views (idempotent), creates the
        viewport item, and refreshes the title-block Scale field. Called by
        AddViewportCommand.redo / RemoveViewportCommand.undo.

        Args:
            data: SheetViewData to add.

        Returns:
            The newly created SheetViewport.
        """
        if not data.view_number:
            data.view_number = str(len(self._sheet.sheet_views) + 1)
        # Identity check (not value `in`): SheetViewData has value-equality, so a
        # value-identical second viewport must still be tracked separately.
        if all(v is not data for v in self._sheet.sheet_views):
            self._sheet.sheet_views.append(data)
        vp = self._create_viewport(data)
        self._update_scale_field()
        return vp

    def _do_remove_viewport_by_data(self, data: SheetViewData) -> None:
        """Silent primitive: remove the viewport(s) matching *data*.

        Mirrors the original remove_viewport behaviour (drop from _viewports +
        sheet.sheet_views, removeItem, refresh Scale field) but keys on data
        identity so it works after a _setup() rebuild recreates items. Called
        by RemoveViewportCommand.redo / AddViewportCommand.undo.

        Args:
            data: SheetViewData whose owning viewport should be removed.
        """
        for vp in list(self._viewports):
            if vp.data is data:
                self._viewports.remove(vp)
                self.removeItem(vp)
        # Identity removal (not value `.remove`): only drop the exact object, so
        # a value-identical sibling viewport is left untouched.
        self._sheet.sheet_views[:] = [
            v for v in self._sheet.sheet_views if v is not data
        ]
        self._update_scale_field()

    def _resync_viewport(self, data: SheetViewData) -> None:
        """Re-apply *data*'s position/size to its live viewport item.

        Used by ViewportGeometryCommand / ChangeViewportPropertiesCommand after
        they mutate the data object, so the on-screen item and Scale field
        reflect the (un)done state.

        Args:
            data: SheetViewData whose live viewport should be re-synced.
        """
        vp = _find_viewport(self, data)
        if vp is not None:
            vp.setPos(data.x, data.y)
            vp.prepareGeometryChange()
            vp.mark_dirty()
        self._update_scale_field()

    def add_viewport(self, data: SheetViewData) -> SheetViewport:
        """Add a viewport for *data* via an undoable command.

        The pushed AddViewportCommand runs its redo() synchronously, so the
        viewport is created immediately and returned (preserving the original
        contract for callers such as dropEvent).

        Args:
            data: SheetViewData describing the new viewport.

        Returns:
            The created SheetViewport.
        """
        self._undo_stack.push(AddViewportCommand(self, data))
        return _find_viewport(self, data)

    def remove_viewport(self, viewport: SheetViewport):
        """Remove *viewport* via an undoable RemoveViewportCommand.

        Args:
            viewport: The SheetViewport to remove (keyed on its data).
        """
        self._undo_stack.push(RemoveViewportCommand(self, viewport.data))

    def _push_viewport_geometry(self, data, old, new):
        """Push a ViewportGeometryCommand for a completed move/resize gesture.

        No-op while a command is being applied or when geometry is unchanged.

        Args:
            data: SheetViewData whose geometry changed.
            old: (x, y, w, h) before the gesture.
            new: (x, y, w, h) after the gesture.
        """
        if not self._applying_command and old != new:
            self._undo_stack.push(ViewportGeometryCommand(self, data, old, new))

    def get_viewports(self) -> list[SheetViewport]:
        return list(self._viewports)

    def update_from_sheet(self, sheet: Sheet):
        """Rebuild the scene for *sheet* and reset the undo history.

        Loading a project (or starting a new one) swaps the backing sheet and
        repopulates every item from persisted data. That repopulation must not
        be undoable, so the paper-space undo stack is cleared once the scene is
        rebuilt (paper-space spec §17.5).

        Args:
            sheet: The sheet whose persisted content becomes the new scene.
        """
        self._suppress_modified = True
        try:
            self._sheet = sheet
            self._setup()
            self._undo_stack.clear()
        finally:
            self._suppress_modified = False

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
        data = viewport.data
        dlg = SheetViewPropertiesDialog(data.source_view_name, data)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # Snapshot the fields the dialog mutates (incl. derived w/h) BEFORE
        # applying, then compute the new values without touching the data
        # object — the command applies/reverts them. The ordering below
        # (scale-derived w/h first, then explicit size override) preserves the
        # original inline behaviour exactly.
        old_fields = {
            "title": data.title, "show_border": data.show_border,
            "scale": data.scale, "x": data.x, "y": data.y,
            "w": data.w, "h": data.h,
        }
        new_title = dlg.get_title()
        new_show_border = dlg.get_show_border()
        new_scale = dlg.get_scale()
        new_x, new_y = data.x, data.y
        new_w, new_h = data.w, data.h
        if new_scale != data.scale and new_scale != 0.0:
            result = self._resolver.resolve(
                data.source_view_type, data.source_view_name)
            if result:
                _, src_rect = result
                new_w = src_rect.width() * new_scale
                new_h = src_rect.height() * new_scale
        pos = dlg.get_position()
        if pos:
            new_x, new_y = pos
        size = dlg.get_size()
        if size:
            new_w, new_h = size
        new_fields = {
            "title": new_title, "show_border": new_show_border,
            "scale": new_scale, "x": new_x, "y": new_y,
            "w": new_w, "h": new_h,
        }
        if new_fields != old_fields:
            self._undo_stack.push(
                ChangeViewportPropertiesCommand(self, data, old_fields, new_fields))

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
        # Identity check (not value `in`): TextAnnotationData has value-equality,
        # so two value-identical blocks must both be tracked separately.
        if all(a is not data for a in self._sheet.annotations):
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
        # Identity removal (not value `.remove`): only drop the exact object, so
        # a value-identical sibling annotation is left untouched.
        self._sheet.annotations[:] = [
            a for a in self._sheet.annotations if a is not data
        ]

    def add_annotation(self, data: TextAnnotationData) -> TextAnnotationItem:
        """Silently add a text annotation to the scene and persist it in the sheet.

        This is the non-undoable helper that wraps the _do_add_annotation
        primitive. Undoable creation goes through commit_place_text(), which
        pushes an AddTextAnnotationCommand; that command's redo path calls the
        same primitive. Direct callers (e.g. tests, programmatic seeding) use
        this when an undo entry is not wanted.

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
        if self.text_template is not None:
            t = self.text_template
            data.height_mm = t.height_mm
            data.font_family = t.font_family
            data.bold = t.bold
            data.italic = t.italic
            data.underline = t.underline
            data.color = t.color
            data.align = t.align
            data.opaque_bg = t.opaque_bg
        item = TextAnnotationItem(data)  # TRANSIENT: not tracked, not in sheet
        self.addItem(item)
        self._pending_text = item
        item.begin_edit()
        return item

    def commit_place_text(self, item: TextAnnotationItem) -> None:
        """Finalise or discard a pending placement item.

        Reads the current plain-text from *item*. If it is blank (empty or
        whitespace-only) the transient item is silently removed and nothing is
        tracked. Otherwise the transient item is removed and the creation is
        recorded on the undo stack by pushing an AddTextAnnotationCommand; that
        command's redo() builds the properly tracked replacement item
        synchronously.

        Args:
            item: The TextAnnotationItem returned by begin_place_text().
        """
        self._pending_text = None
        text = item.toPlainText()
        self.removeItem(item)           # discard the transient editor item
        if text.strip() == "":
            return                      # auto-delete empty; nothing tracked
        item.data.text = text
        # First non-empty commit: record the creation on the undo stack. The
        # command's redo() builds the tracked replacement item synchronously.
        self._undo_stack.push(AddTextAnnotationCommand(self, item.data))

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
        QTimer.singleShot(0, lambda it=item: self._undo_stack.push(
            DeleteTextAnnotationCommand(self, it.data)))

    # ── Undo push helpers (called from item gesture hooks) ───────────────

    def _push_text_move(self, data, old, new):
        """Push a MoveTextAnnotationCommand for a completed move gesture.

        No-op while a command is being applied or when the anchor is unchanged.
        """
        if not self._applying_command and old != new:
            self._undo_stack.push(MoveTextAnnotationCommand(self, data, old, new))

    def _push_text_box_resize(self, data, old_state, new_state):
        """Push a ResizeTextBoxCommand for a completed 8-handle box resize gesture.

        No-op while a command is being applied or when all four fields are unchanged.

        Args:
            data: The TextAnnotationData being resized.
            old_state: ``(old_x, old_y, old_wrap_width_mm, old_box_height_mm)``
                       before the gesture.
            new_state: ``(new_x, new_y, new_wrap_width_mm, new_box_height_mm)``
                       after the gesture.
        """
        if not self._applying_command and old_state != new_state:
            self._undo_stack.push(ResizeTextBoxCommand(self, data, old_state, new_state))

    def _push_text_edit(self, data, old_text, new_text):
        """Record an inline-edit commit on the undo stack.

        Empty/whitespace content auto-deletes the block (DeleteText); a changed
        non-empty commit pushes an EditText command; an unchanged commit pushes
        nothing.

        For the empty branch the original *old_text* is written back onto the
        data object before the DeleteText command is pushed, so undoing the
        delete rebuilds the block with its ORIGINAL text rather than an empty
        one. (commit_edit() has already set ``data.text == ""`` on the live item;
        the DeleteCommand.redo removes that item immediately, and its undo path
        — _do_add_annotation — builds a fresh item from this restored data.)

        Args:
            data: The TextAnnotationData of the block being committed.
            old_text: The block's text before the edit began.
            new_text: The block's text as just committed.
        """
        if new_text.strip() == "":
            data.text = old_text  # so undo of the delete restores the original block
            self._undo_stack.push(DeleteTextAnnotationCommand(self, data))
        elif new_text != old_text:
            self._undo_stack.push(EditTextCommand(self, data, old_text, new_text))

    def _annotation_scale_manager(self) -> ScaleManager:
        """Return a ScaleManager for panel dimension fields.

        Prefers the model scene's ScaleManager (reached via the resolver) so the
        height field formats in the user's current units; falls back to a fresh
        ``ScaleManager()`` when the resolver does not expose a usable model
        scene (e.g. stub/mock resolvers in tests).

        Returns:
            A ScaleManager instance.
        """
        model_scene = getattr(self._resolver, "_scene", None)
        sm = getattr(model_scene, "scale_manager", None)
        if isinstance(sm, ScaleManager):
            return sm
        return ScaleManager()

    # ── Public API (preserved) ──────────────────────────────────────────

    def set_resolver(self, resolver: ViewResolver) -> None:
        """Swap the view resolver used for subsequent viewport builds.

        Must be called before update_from_sheet() on a load path so rebuilt
        SheetViewports capture the new resolver (they take it at construction).
        """
        self._resolver = resolver

    @property
    def paper_size(self) -> str:
        return self._sheet.paper_size

    @paper_size.setter
    def paper_size(self, size: str):
        if size in PAPER_SIZES and size != self._sheet.paper_size:
            self._sheet.paper_size = size
            self._setup()
            self.sheetModified.emit()

    @property
    def sheet(self) -> Sheet:
        return self._sheet

    @property
    def scale_manager(self) -> ScaleManager:
        """ScaleManager for panel dimension fields (delegates to the resolver's model scene)."""
        return self._annotation_scale_manager()

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
    Complete Paper Space panel: a QGraphicsView of PaperScene (commands live on the ribbon).

    Parameters
    ----------
    sheet : Sheet
        The sheet data model driving the paper layout.
    resolver : ViewResolver
        Resolves source view type + name to (scene, rect) pairs.
    """

    navigate_to_view = pyqtSignal(str, str)
    add_text_mode_toggled = pyqtSignal(bool)

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

        self.view = PaperGraphicsView(self.paper_scene)
        layout.addWidget(self.view)

        # Fit to sheet on first show
        self._fit()

    # ── Public command API (ribbon-driven; toolbar retired 2026-07-16) ──────

    def change_paper(self, size: str):
        """Public: change paper size and fit the view."""
        self.paper_scene.paper_size = size
        self._fit()

    def set_sheet(self, sheet: Sheet, resolver: ViewResolver) -> None:
        """Public: rebind this widget (and its scene) to *sheet* + *resolver*.

        The single load-path entry point: keeps widget._sheet, the scene's
        sheet, and the resolver in lockstep so title-block edits and viewport
        builds target the live project data (a stale widget._sheet previously
        sent post-load title-block edits into a detached dict).
        """
        self._sheet = sheet
        self._resolver = resolver
        self.paper_scene.set_resolver(resolver)
        self.paper_scene.update_from_sheet(sheet)

    def set_add_text_mode(self, on: bool) -> None:
        """Public: enter/leave text place mode; emits add_text_mode_toggled."""
        on = bool(on)
        # Guard also means listeners only ever hear real state changes — _sync_add_text_ribbon_btn (main.py) depends on the signal never firing when view and button already agree.
        if on == self.view._add_text_mode:
            return
        self.view.set_add_text_mode(on)
        self.add_text_mode_toggled.emit(on)

    def refresh_viewport(self):
        """Public: repaint the model-space previews."""
        self.paper_scene.refresh_viewport()

    def fit_sheet(self):
        """Public: fit the whole sheet in the view."""
        self._fit()

    def _edit_title(self):
        fields = self._sheet.title_block_fields
        before = dict(fields)
        dlg = TitleBlockDialog(self.paper_scene.title_block, self)
        dlg.exec()
        # Sync programmatic title block fields from sheet
        self.paper_scene.title_block.fields = fields
        self.paper_scene.refresh_viewport()
        if fields != before:
            self.paper_scene.sheetModified.emit()

    def edit_title_block(self):
        """Public: open the title block editor dialog."""
        self._edit_title()

    def _fit(self):
        self.view.fitInView(self.paper_scene.sceneRect(),
                            Qt.AspectRatioMode.KeepAspectRatio)
