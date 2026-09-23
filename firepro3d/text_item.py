"""text_item.py — Unified text primitive + shared data model (containment C5).

This module is the single home for:

* ``TextAnnotationData`` — the serialisable dataclass that backs all text.
* ``TextItem`` — the unified, scene-context-sized text primitive (C5.3) that
  merges the two historical renderers (paper-space ``TextAnnotationItem`` and
  model-space ``NoteAnnotation``) into one class backed by
  ``TextAnnotationData`` (held by shared reference).  Its sizing mode follows
  the host scene's ``device_independent_text()`` hook.

The legacy ``TextAnnotationItem`` (paper_space.py) and ``NoteAnnotation``
(annotations.py) are RETIRED in a later containment task; until then they
coexist and this module does not rewire them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from .constants import DEFAULT_TEXT_HEIGHT_MM, TEXT_BOX_MARGIN_MM


@dataclass
class TextAnnotationData:
    """Serialisable data for one text annotation.

    Lengths are in the surface's own mm: paper-mm when the item lives on a
    sheet, scene-mm when it lives in a model or block-editor scene.

    Shared by reference with its ``TextItem`` (never copied), exactly like
    ``SheetViewData`` ↔ ``SheetViewport``.

    Fields
    ------
    text:
        Raw string content (may contain newlines).
    x, y:
        Position on the paper sheet (mm from sheet origin).
    height_mm:
        CAP height of the rendered text, in paper mm.
    wrap_width_mm:
        Word-wrap column width; 0 = auto (no wrap).
    box_height_mm:
        Explicit box height; 0 = auto-fit content.
    font_family:
        Font family name; empty string → Arial default.
    bold, italic, underline:
        Font style flags.
    color:
        Authored hex colour string, default black ``"#000000"``.
    align:
        Horizontal alignment: ``'L'`` | ``'C'`` | ``'R'``.
    fill_color:
        Box fill hex colour string; empty string means no fill.
    fill_opacity:
        Fill alpha as a percentage 0–100 (default 100 = fully opaque).
    border:
        When ``True``, draw a framing rectangle around the text box.
    border_weight:
        Named line-weight token (resolved via ``resolve_line_weight_mm``).
    border_line_type:
        Stroke style: ``'solid'`` | ``'dashed'`` | ``'dotted'`` | ``'dashdot'``.
    border_corner:
        Corner treatment: ``'square'`` | ``'round'`` | ``'chamfer'``.
    angle:
        Rotation in degrees (Y-up CCW+, same convention as the rest of the
        model).  Default ``0.0``.  Pivot is transient/recomputed at rest and
        is **not** serialised.
    type:
        Discriminator for future annotation kinds; always ``"text"`` for this
        class.
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
    align: str = "L"                             # horizontal: 'L' | 'C' | 'R'
    valign: str = "T"                            # vertical: 'T' | 'M' | 'B'
    fill_color: str = ""                          # box fill hex; "" = no fill
    fill_opacity: float = 100.0                   # fill alpha percentage 0-100
    cell_padding_mm: float = TEXT_BOX_MARGIN_MM   # inner padding text↔box edge (surface mm)
    border: bool = False                         # frame visibility
    border_weight: str = "Medium"                # named line-weight (resolve_line_weight_mm)
    border_line_type: str = "solid"              # 'solid'|'dashed'|'dotted'|'dashdot'
    border_corner: str = "square"                # 'square'|'round'|'chamfer'
    border_corner_radius_mm: float = 0.0         # 0 = auto proportional (TEXT_FRAME_CORNER_FRAC)
    angle: float = 0.0                           # rotation degrees, Y-up CCW+; pivot not serialised
    type: str = "text"                           # discriminator for future annotation types

    def to_dict(self) -> dict:
        return {
            "type": self.type, "text": self.text,
            "x": self.x, "y": self.y,
            "height_mm": self.height_mm, "wrap_width_mm": self.wrap_width_mm,
            "box_height_mm": self.box_height_mm,
            "font_family": self.font_family,
            "bold": self.bold, "italic": self.italic, "underline": self.underline,
            "color": self.color, "align": self.align, "valign": self.valign,
            "fill_color": self.fill_color, "fill_opacity": self.fill_opacity,
            "cell_padding_mm": self.cell_padding_mm,
            "border": self.border, "border_weight": self.border_weight,
            "border_line_type": self.border_line_type, "border_corner": self.border_corner,
            "border_corner_radius_mm": self.border_corner_radius_mm,
            "angle": self.angle,
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
            valign=d.get("valign", "T"),
            fill_color=(d.get("fill_color")
                        if d.get("fill_color") is not None
                        else ("#ffffff" if bool(d.get("opaque_bg", False)) else "")),
            fill_opacity=float(d.get("fill_opacity", 100.0)),
            cell_padding_mm=float(d.get("cell_padding_mm", TEXT_BOX_MARGIN_MM)),
            border=bool(d.get("border", False)),
            border_weight=d.get("border_weight", "Medium"),
            border_line_type=d.get("border_line_type", "solid"),
            border_corner=d.get("border_corner", "square"),
            border_corner_radius_mm=float(d.get("border_corner_radius_mm", 0.0)),
            angle=float(d.get("angle", 0.0)),
            type=d.get("type", "text"),
        )


# ═════════════════════════════════════════════════════════════════════════════
# TextItem — the unified text primitive (containment C5.3)
# ═════════════════════════════════════════════════════════════════════════════
#
# Merges the two historical text renderers into one class backed by
# ``TextAnnotationData`` (held by shared reference):
#
#   • ``paper_space.TextAnnotationItem`` — device-independent paper text
#     (setPixelSize(TEXT_METRIC_REF_PX) + geometric setScale(height_mm/cap),
#     zoom-invariant), box/opaque-bg knockout, in-place edit lifecycle,
#     translate+scale manipulator, contains() point-query fix.
#   • ``annotations.NoteAnnotation`` — model-space text with bake-at-rest
#     rotation (data-only ``_angle``/``_pivot`` + composed map overrides) and a
#     translate+scale+rotate manipulator that drops scale when rotated.
#
# The SIZING MODE follows the scene: a PaperScene reports
# ``device_independent_text() == True`` → the paper path; a Model_Space /
# Block-Editor scene reports False → the font is sized so the cap height equals
# ``height_mm`` in SCENE units (scale() == 1, scales with zoom).  The mode is
# re-derived whenever the item is added to a scene (``itemChange``), so the same
# data lands at the right physical size on whichever surface it is placed.
#
# Governing spec: docs/specs/2026-09-17-containment-implementation-design.md §A2.
# Retirement of the two old classes and the paper repoint happen in a LATER task.

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, pyqtSignal   # noqa: E402
from PyQt6.QtGui import (                                          # noqa: E402
    QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QTransform,
)
from PyQt6.QtWidgets import (                                      # noqa: E402
    QApplication, QGraphicsItem, QGraphicsTextItem, QMenu,
)

from . import theme                                                 # noqa: E402
from .constants import (                                           # noqa: E402
    DEFAULT_LEVEL, MIN_TEXT_WRAP_WIDTH_MM,
    SELECTION_GRIP_OUTLINE_WIDTH_MM, SELECTION_GRIP_SIZE_MM,
    TEXT_CARET_WIDTH_PX, TEXT_METRIC_REF_PX, TEXT_SELECTION_ALPHA,
)
from .displayable_item import DisplayableItemMixin                 # noqa: E402
from .geometry_2d import Geometry2DMixin                           # noqa: E402


def editing_text_item(scene) -> "TextItem | None":
    """The TextItem currently inline-editing on *scene*, else ``None``.

    The single "does the text editor own this key/click?" test for every input
    layer (model view, model scene, paper view).  Reads the ``_editing_item``
    marker that :meth:`TextItem.begin_edit` sets, validated as still alive, on
    this scene, and still editing.
    """
    if scene is None:
        return None
    item = getattr(scene, "_editing_item", None)
    if item is None:
        return None
    try:
        alive = item.scene() is scene and bool(getattr(item, "_editing", False))
    except RuntimeError:                  # wrapped C++ object already deleted
        alive = False
    return item if alive else None


class _LayoutOffsets(NamedTuple):
    """Document-wide input to :meth:`TextItem._line_origin`.

    Horizontal alignment is deliberately NOT carried here: Qt's own
    ``QTextLine.cursorToX``/``xToCursor`` are alignment-aware, while
    ``QTextLine.x()`` is not, so callers derive any horizontal alignment
    shift from those Qt calls directly rather than from a cached flag here.

    Attributes:
        voff: Vertical-alignment offset (local, unscaled units) of the whole
            text block within the box — ``0.0`` for top, half the box/content
            slack for middle, and the full slack for bottom alignment.
    """

    voff: float


class TextItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsTextItem):
    """A unified, scene-context-sized text block backed by ``TextAnnotationData``.

    Placed on either a device-independent PaperScene (paper-mm text, zoom
    invariant) or a Model_Space / Block-Editor scene (scene-mm text, scales
    with zoom).  The data object is held by SHARED REFERENCE (``self._data``),
    exactly like the paper ``TextAnnotationItem`` and ``SheetViewData`` ↔
    ``SheetViewport``.

    Rotation is stored as DATA (``self._data.angle``, bake-at-rest — NO held Qt
    item transform): ``paint``/``boundingRect``/``shape`` and the composed
    ``mapToScene``/``mapFromScene``/``mapRectToScene`` overrides read it so the
    rendered/hit footprint tracks the rotated box.  ``_angle`` mirrors the data
    field for those overrides; ``_pivot`` is transient (recomputed at rest).
    """

    # Emitted (with self) when the block requests its own deletion — a
    # not-editing Delete key or a context-menu "Delete".  The paper scene
    # connects this to route through DeleteTextAnnotationCommand (parity with
    # the retired paper TextAnnotationItem); deletion routing on the model
    # surface lands in a later containment task.
    delete_requested = pyqtSignal(object)

    _ALIGN = {
        "L": Qt.AlignmentFlag.AlignLeft,
        "C": Qt.AlignmentFlag.AlignCenter,
        "R": Qt.AlignmentFlag.AlignRight,
    }

    def __init__(self, data: "TextAnnotationData", parent=None):
        # QGraphicsTextItem takes the initial text; the mixins take no ctor args
        # (their state is set by init_displayable()/init_geometry2d() below).
        QGraphicsTextItem.__init__(self, data.text, parent)
        self._data = data
        self._editing = False
        self._text_before_edit = data.text

        # Inline-edit session state (model surface; spec § Inline edit).
        self._caret_timer: QTimer | None = None
        self._caret_on = False
        self._edit_before: dict | None = None   # to_dict() at session start
        self._edit_is_new = False               # session started by placement

        # Bake-at-rest rotation state (data-only — NO held Qt transform).
        # _angle mirrors self._data.angle for the map* overrides; _pivot is
        # transient (None → follow the box centre at rest).
        self._angle: float = float(data.angle)
        self._pivot: QPointF | None = None

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

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

    # ── Sizing mode (follows the scene) ─────────────────────────────────────

    def is_device_independent(self) -> bool:
        """True when text is sized device-independently (paper surface).

        Follows the host scene's ``device_independent_text()`` hook (PaperScene
        → True; Model_Space / Block-Editor → False).  An explicit
        ``_force_device_independent`` overrides the scene lookup so an OFF-scene
        paper template (``current_text_template``) sizes + formats as paper text
        even though it has no scene yet.
        """
        forced = getattr(self, "_force_device_independent", None)
        if forced is not None:
            return bool(forced)
        sc = self.scene()
        fn = getattr(sc, "device_independent_text", None)
        return bool(fn()) if callable(fn) else False

    def _apply_format(self) -> None:
        """Rebuild font, colour, alignment, scale, and wrap from self._data.

        In device-independent (paper) mode the font uses a large reference pixel
        size and ``setScale`` maps cap-height units to paper mm (zoom invariant),
        exactly like the retired ``TextAnnotationItem``.  In scene-mm (model /
        block-editor) mode the font is sized so its cap height equals
        ``height_mm`` in SCENE units and ``setScale`` stays 1 (the box scales
        with zoom like every other model primitive).
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
        if self.is_device_independent():
            # Paper path: reference-px font + geometric scale to paper mm.
            scale = h / cap if cap > 0 else 1.0
        else:
            # Scene-mm path: bake the cap→mm ratio into the font pixel size so a
            # plain scene item (scale 1) has cap height == h in scene units, and
            # scales naturally with the viewport zoom.
            if cap > 0:
                f.setPixelSize(max(1, round(TEXT_METRIC_REF_PX * h / cap)))
                self.setFont(f)
            scale = 1.0
        self.setScale(scale)
        # Inner margin: set BEFORE wrap/auto-width so idealWidth() accounts for it.
        if scale > 0:
            self.document().setDocumentMargin(self._data.cell_padding_mm / scale)
        if d.wrap_width_mm > 0 and scale > 0:
            self.setTextWidth(d.wrap_width_mm / scale)
        else:
            self.setTextWidth(-1)
            self.setTextWidth(self.document().idealWidth())

    def itemChange(self, change, value):
        """Re-derive the sizing mode when the item lands on / leaves a scene,
        clamp to the paper rect on a paper surface, live-sync data.x/y, and
        end a live inline-edit session cleanly if the item is removed from
        its scene mid-edit (deleted, undone, or reparented).

        ``ItemSceneChange`` fires BEFORE the scene actually changes, so
        ``self.scene()`` here still reads the OLD scene — the only place the
        old scene's ``_editing_item`` marker can still be read once the item
        is gone from it.
        """
        Change = QGraphicsItem.GraphicsItemChange
        if change == Change.ItemSceneChange and value is None and self._editing:
            old_scene = self.scene()
            self._stop_caret_blink()
            self._editing = False
            if old_scene is not None and getattr(old_scene, "_editing_item", None) is self:
                old_scene._editing_item = None
        if change == Change.ItemSceneHasChanged:
            # The scene (hence the sizing mode) just changed — reformat so the
            # same data renders at the right physical size on this surface.
            self.prepareGeometryChange()
            self._apply_format()
        elif change == Change.ItemPositionChange:
            # Paper surface only: clamp the proposed position to the sheet rect
            # (parity with the retired paper TextAnnotationItem).  A model scene
            # has no sheet and imposes no clamp.
            sc = self.scene()
            sheet = getattr(sc, "sheet", None) if sc is not None else None
            if sheet is not None:
                from .paper_space import sheet_page_mm
                pw, ph = sheet_page_mm(sheet)
                return QPointF(max(0.0, min(value.x(), pw)),
                               max(0.0, min(value.y(), ph)))
        elif change == Change.ItemPositionHasChanged:
            self.sync_data_from_item()
        return super().itemChange(change, value)

    # ── Box geometry ────────────────────────────────────────────────────────

    def _box_rect_local(self) -> QRectF:
        """The box bounding rect in item-local UNSCALED coordinates.

        Width comes from the text layout (``textWidth`` already reflects wrap);
        height is ``max(content height, box_height_mm / scale)`` so the box
        auto-grows with content but never shrinks below the stored height.
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

    def _frame_path(self) -> "QPainterPath":
        """Border path for the box rect, honoring the corner style (local frame)."""
        r = self._box_rect_local()
        path = QPainterPath()
        if self._data.border_corner == "square":
            path.addRect(r)
            return path
        cap = min(r.width(), r.height()) / 2.0        # geometric max radius
        if self._data.border_corner_radius_mm > 0:
            # Explicit radius (surface mm → local units), clamped so it never
            # exceeds half the shorter side.
            scale = self.scale() or 1.0
            rad = min(self._data.border_corner_radius_mm / scale, cap)
        else:
            from .constants import TEXT_FRAME_CORNER_FRAC
            rad = TEXT_FRAME_CORNER_FRAC * min(r.width(), r.height())
        if self._data.border_corner == "round":
            path.addRoundedRect(r, rad, rad)
            return path
        # chamfer: 45-degree cut of size `rad` at each corner
        l, t, ri, b = r.left(), r.top(), r.right(), r.bottom()
        path.moveTo(l + rad, t)
        path.lineTo(ri - rad, t); path.lineTo(ri, t + rad)
        path.lineTo(ri, b - rad); path.lineTo(ri - rad, b)
        path.lineTo(l + rad, b); path.lineTo(l, b - rad)
        path.lineTo(l, t + rad); path.closeSubpath()
        return path

    # Named border weight → cosmetic device-px width on the model / Block-Editor
    # surface (constant at all zooms, matching the sibling 2D primitives, whose
    # default lineweight is 1.0px cosmetic).  The paper surface uses the true mm
    # weight instead (it plots).  "Light" == 1.0 mirrors the primitive default.
    _BORDER_WEIGHT_PX = {
        "Very Light": 0.5, "Light": 1.0, "Medium": 1.5,
        "Heavy": 2.0, "Very Heavy": 3.0,
    }

    def _frame_pen(self) -> "QPen":
        """Pen for the border: text colour + line-type, aligned with the sibling
        2D primitives.

        On the model / Block-Editor surface the pen is **cosmetic** (constant
        device width at all zooms) — the named paper line-weights are sub-pixel at
        editor zoom, so they map to fixed device-px widths (``_BORDER_WEIGHT_PX``).
        On the paper surface the true named mm weight is used (divided by scale
        like the other paper pens) so the border still plots at its real width.
        """
        pen = QPen(QColor(self._data.color))
        pen.setStyle({
            "solid": Qt.PenStyle.SolidLine, "dashed": Qt.PenStyle.DashLine,
            "dotted": Qt.PenStyle.DotLine, "dashdot": Qt.PenStyle.DashDotLine,
        }.get(self._data.border_line_type, Qt.PenStyle.SolidLine))
        if self.is_device_independent():
            from .paper_display import resolve_line_weight_mm
            scale = self.scale() or 1.0
            pen.setWidthF(max(resolve_line_weight_mm(self._data.border_weight) / scale, 1e-4))
        else:
            pen.setCosmetic(True)
            pen.setWidthF(self._BORDER_WEIGHT_PX.get(self._data.border_weight, 1.0))
        return pen

    def boundingRect(self) -> QRectF:
        """Visual/selection extent — padded for the grip halo, rotated footprint.

        Grips straddle the box corners, so the rect is padded unconditionally
        (Qt's dirty tracking would otherwise leave trails on drag).  When the box
        is rotated (bake-at-rest), the padded rect's rotated footprint is
        returned so Qt's scene index / culling wraps the real shape.
        """
        rect = self._box_rect_local()
        s = self.scale() or 1.0
        pad = (SELECTION_GRIP_SIZE_MM / 2 + SELECTION_GRIP_OUTLINE_WIDTH_MM) / s
        base = rect.adjusted(-pad, -pad, pad, pad)
        if self._angle == 0.0:
            return base
        return self._rotation_transform().mapRect(base)

    def shape(self) -> QPainterPath:
        """Full-box hit area (grab anywhere in the box, not just on glyphs).

        Rotated by the data ``_angle`` about the pivot so scene hit-testing
        tracks the rotated footprint.  Only ever WIDER than the default —
        narrowing shape() breaks Qt's paint culling.
        """
        path = QPainterPath()
        path.addRect(self._box_rect_local())
        if self._angle != 0.0:
            path = self._rotation_transform().map(path)
        return path

    def contains(self, point) -> bool:
        """Point hit-test via shape().

        QGraphicsTextItem overrides ``contains()`` with its own text-content
        test, so scene point queries (itemAt, click routing) would ignore the
        widened shape() without this override (fixes point-query trails).
        """
        return self.shape().contains(point)

    # ── Bake-at-rest rotation (data-only; NO Qt item transform) ─────────────
    # Ported from NoteAnnotation.  A text item's pos() is nonzero (its origin),
    # so the map* overrides COMPOSE the local rotation with super()'s pos
    # translation.  Qt's mapToScene is non-virtual in C++, so these only
    # intercept Python callers (grip/snap); Qt rendering uses
    # paint/boundingRect/shape (all baked below).

    def set_angle(self, angle_deg: float, pivot: "QPointF | None" = None) -> None:
        """Set the bake-at-rest rotation (Y-up CCW+).  Single source of truth is
        ``self._data.angle``; ``_angle`` mirrors it for the map overrides."""
        self._angle = float(angle_deg)
        self._data.angle = self._angle
        if pivot is not None:
            # Manipulator passes a SCENE pivot → store LOCAL (pos-removal only;
            # Qt rotation() is always 0, so this never un-applies _angle).
            self._pivot = QGraphicsTextItem.mapFromScene(self, QPointF(pivot))
        else:
            self._pivot = None          # follow the box centre on resize
        self.prepareGeometryChange()
        self.update()

    def _rotation_origin(self) -> QPointF:
        return QPointF(self._pivot) if self._pivot is not None else self._box_rect_local().center()

    def _rotation_transform(self) -> QTransform:
        m = QTransform()
        if self._angle == 0.0:
            return m
        o = self._rotation_origin()
        m.translate(o.x(), o.y())
        m.rotate(-self._angle)          # Y-up CCW → Qt CW negate
        m.translate(-o.x(), -o.y())
        return m

    def mapToScene(self, *args):
        """Local→scene through the data rotation, composed with pos (super())."""
        if self._angle == 0.0:
            return super().mapToScene(*args)
        t = self._rotation_transform()
        if len(args) == 2:                       # (x, y)
            return super().mapToScene(t.map(QPointF(args[0], args[1])))
        obj = args[0]
        if isinstance(obj, (QPointF, QPainterPath)):
            return super().mapToScene(t.map(obj))
        return super().mapToScene(*args)         # unknown overload → best effort

    def mapFromScene(self, *args):
        """Scene→local inverse of :meth:`mapToScene`."""
        if self._angle == 0.0:
            return super().mapFromScene(*args)
        inv, ok = self._rotation_transform().inverted()
        if not ok:
            inv = QTransform()
        if len(args) == 2:
            return inv.map(super().mapFromScene(QPointF(args[0], args[1])))
        obj = args[0]
        if isinstance(obj, (QPointF, QPainterPath)):
            return inv.map(super().mapFromScene(obj))
        return super().mapFromScene(*args)

    def mapRectToScene(self, rect: QRectF) -> QRectF:
        """Axis-aligned scene bounds of the rotated local ``rect`` (+pos)."""
        if self._angle == 0.0:
            return super().mapRectToScene(rect)
        return super().mapRectToScene(self._rotation_transform().mapRect(rect))

    # ── Paint (opaque-bg knockout + baked rotation + editing frame) ─────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        """Paint the text block with an optional fill and inline-edit frame.

        Renders (with the bake-at-rest rotation applied like NoteAnnotation):
        (1) a colour fill over the box rect when ``fill_color`` is set,
        (2) the text via super() on paper / glyph outlines + self-painted
        selection + caret on the model surface, (3) the paper-only dashed
        editing frame.
        """
        box = self._box_rect_local()
        painter.save()
        if self._angle != 0.0:
            painter.setWorldTransform(self._rotation_transform(), True)
        if self._data.fill_color:
            c = QColor(self._data.fill_color)
            c.setAlphaF(max(0.0, min(1.0, self._data.fill_opacity / 100.0)))
            painter.fillRect(box, c)
        if self.is_device_independent():
            # Paper surface: the QGraphicsTextItem document renderer works on the
            # paper viewport device (zoom-invariant, live caret) — keep it.
            super().paint(painter, option, widget)
        else:
            # Model / Block-Editor surface: EVERYTHING is drawn through direct
            # painter ops, never super().paint() — the document renderer draws
            # nothing on the live viewport's engine-less device (todo #62 /
            # engine==0).  Selection highlight → glyph outlines → caret.
            if self._editing:
                sel = theme.detect().color("selection", TEXT_SELECTION_ALPHA)
                for r in self.selection_rects_local():
                    painter.fillRect(r.intersected(box), sel)
            outline = self._glyph_outline_local()
            if not outline.isEmpty():
                painter.fillPath(outline, QColor(self._data.color))
            if self._editing and self._caret_on:
                cr = self.caret_rect_local()
                pen = QPen(QColor(self._data.color))
                pen.setCosmetic(True)
                pen.setWidthF(TEXT_CARET_WIDTH_PX)
                painter.setPen(pen)
                painter.drawLine(cr.topLeft(), cr.bottomLeft())
        if self._data.border:
            painter.setPen(self._frame_pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._frame_path())
        if self._editing and self.is_device_independent():
            # Paper keeps its dashed EDITING frame; the model surface shows the
            # normal selection frame only (spec § Inline edit — no edit frame).
            pen = QPen(QColor("#88aaff"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
        painter.restore()

    # ── Glyph-outline path (block-content compile; containment C5.4) ────────

    def render_outline_path(self) -> QPainterPath:
        """Return the text as filled glyph outlines in the item's LOCAL frame.

        Document-faithful: laid out through the live ``QTextDocument`` so wrap
        width, alignment, box height and line breaks are honoured (per design
        §A2 — NOT a single ``addText`` of the raw string).  The glyph runs are
        outlined at the layout-computed baseline of each line and united into
        one path.

        The path is in the same LOCAL, unscaled coordinate frame that
        ``_box_rect_local``/``grip_points`` use (font pixel size is baked so the
        cap height equals ``height_mm`` in local units; ``setScale`` is 1 for a
        model/block-editor scene — the surface a block is authored on).  The
        item's bake-at-rest rotation (``self._angle`` about its pivot) is applied
        to the returned path directly, because ``BlockDefinition._compile`` maps
        primitives via Qt ``mapToParent`` which does NOT see the data-baked
        rotation.

        Returns an empty ``QPainterPath`` for empty text.
        """
        outline = self._glyph_outline_local()
        if not outline.isEmpty() and self._angle != 0.0:
            outline = self._rotation_transform().map(outline)
        return outline

    def _glyph_outline_local(self) -> QPainterPath:
        """Glyph outlines in the LOCAL, UNSCALED, UN-rotated frame.

        Glyphs come from the live ``QTextDocument`` layout, so wrap width,
        alignment, box height, line breaks — and any in-progress inline-edit
        text — are honoured.  Returns an empty path when there are no glyphs.

        Unlike :meth:`render_outline_path`, the bake-at-rest rotation is NOT
        applied: ``paint`` renders through an already-rotated painter and needs
        the unrotated glyphs, whereas block compilation needs them pre-rotated.
        """
        offsets = self._layout_offsets()
        font = self.font()
        doc = self.document()
        outline = QPainterPath()
        block = doc.begin()
        while block.isValid():
            layout = block.layout()
            block_text = block.text()
            for i in range(layout.lineCount()):
                line = layout.lineAt(i)
                origin = self._line_origin(block, line, offsets)
                # _line_origin is deliberately UNALIGNED (see its docstring):
                # QTextLine.cursorToX/xToCursor are alignment-aware, so asking
                # Qt where the line's own first character lands gives the
                # aligned x directly, without re-deriving alignment here.
                align_off = line.cursorToX(line.textStart())[0] - line.x()
                start = line.textStart()
                length = line.textLength()
                # A block never contains a newline (Qt splits blocks on \n), so
                # the run text is used as-is.
                run_text = block_text[start:start + length].rstrip("\u2028\u2029\n")
                if run_text:
                    outline.addText(QPointF(origin.x() + align_off, origin.y() + line.ascent()),
                                    font, run_text)
            block = block.next()
        return outline

    # ── Line geometry shared by glyphs, caret, selection, hit-test ───────────

    def _layout_offsets(self) -> _LayoutOffsets:
        """Document-wide input to :meth:`_line_origin`.

        Forces the (otherwise lazy) text layout to run so every
        ``QTextLine``/``QTextBlock`` queried afterwards is up to date.

        Returns:
            _LayoutOffsets: the vertical-alignment offset of the whole text
            block within the box (see :class:`_LayoutOffsets`).
        """
        doc = self.document()
        doc.documentLayout().documentSize()   # force the lazy layout to run
        vslack = max(0.0, self._box_rect_local().height()
                     - super().boundingRect().height())
        voff = (vslack if self._data.valign == "B"
                else vslack / 2.0 if self._data.valign == "M" else 0.0)
        return _LayoutOffsets(voff)

    def _line_origin(self, block, line, offsets: _LayoutOffsets | None = None) -> QPointF:
        """Painted top-left of *line*, in the LOCAL, UNSCALED, UN-rotated,
        UN-ALIGNED frame.

        ``QTextLine.x()`` stays at ``0`` regardless of the paragraph's
        horizontal alignment — Qt only applies that shift inside
        ``QTextLine.cursorToX``/``xToCursor`` (and at paint time), never in
        ``line.x()`` itself. This method therefore returns the *unaligned*
        origin; callers that need the aligned x (currently only the
        glyph-outline path, via :meth:`_glyph_outline_local`) derive the
        shift themselves from ``cursorToX``/``xToCursor``, which ARE
        alignment-aware. Callers that already route every x through
        ``cursorToX``/``xToCursor`` (caret/selection/hit-test) get the
        correct aligned position for free and must NOT add a shift here, or
        alignment would be double-applied.

        Args:
            block: The ``QTextBlock`` containing *line*.
            line: The ``QTextLine`` to place.
            offsets: A precomputed :meth:`_layout_offsets` result, to avoid
                recomputing it once per line; computed lazily when omitted.

        Returns:
            QPointF: the line's unaligned top-left, in local unscaled
            coordinates. The glyph baseline is ``origin.y() + line.ascent()``.
        """
        voff = (offsets if offsets is not None else self._layout_offsets()).voff
        bp = block.layout().position()
        return QPointF(bp.x() + line.x(), bp.y() + line.y() + voff)

    def _line_for_position(self, pos: int):
        """Resolve document position *pos* to its block, line, and offset.

        Args:
            pos: An absolute ``QTextDocument`` character position.

        Returns:
            tuple[QTextBlock, QTextLine | None, int]: ``(block, line, rel)``
            — the block containing *pos*, the ``QTextLine`` within that
            block that *pos* falls on, and ``rel``, *pos* made
            block-relative and clamped so it is at most the end-of-text
            position (the block separator slot), never past it — matching
            the block-relative addressing ``cursorToX``/``xToCursor`` expect
            elsewhere in this class. ``line`` is only ever ``None`` if the
            block has no laid-out lines at all.

        Note:
            At a soft-wrap boundary, Qt's own cursor affinity maps the
            position at the end of line N to the start of line N+1 (standard
            Qt behaviour) — ``lineForTextPosition`` follows that mapping, so
            a *rel* sitting exactly on such a boundary resolves to line N+1.
        """
        doc = self.document()
        block = doc.findBlock(pos)
        if not block.isValid():
            block = doc.lastBlock()
        layout = block.layout()
        rel = max(0, min(pos - block.position(), block.length() - 1))
        line = layout.lineForTextPosition(rel)
        if not line.isValid():
            line = layout.lineAt(layout.lineCount() - 1) if layout.lineCount() else None
        return block, line, rel

    def caret_rect_local(self) -> QRectF:
        """Zero-width caret rect (painted frame) for the current text cursor."""
        offsets = self._layout_offsets()
        block, line, rel = self._line_for_position(self.textCursor().position())
        if line is None:
            # Defensive fallback only: _layout_offsets() above already forced
            # the lazy layout to run via documentLayout().documentSize(), so
            # every block has >=1 valid QTextLine afterwards and this branch
            # should be unreachable in practice.
            m = self.document().documentMargin()
            return QRectF(m, m + offsets.voff, 0.0, QFontMetricsF(self.font()).height())
        origin = self._line_origin(block, line, offsets)
        x, _ = line.cursorToX(rel)
        return QRectF(origin.x() + (x - line.x()), origin.y(), 0.0, line.height())

    def selection_rects_local(self) -> list[QRectF]:
        """Per-line highlight rects (painted frame) for the cursor's selection.

        A selection that crosses a block boundary includes the newline
        joining the two blocks as a real (if glyph-less) selectable
        character. Since there is no glyph to highlight, that newline gets
        its own narrow rect — one space's horizontal advance wide — appended
        after that line's own rect, so a selected blank line / line break
        still gets visible feedback.
        """
        cur = self.textCursor()
        if not cur.hasSelection():
            return []
        s, e = cur.selectionStart(), cur.selectionEnd()
        offsets = self._layout_offsets()
        newline_w = QFontMetricsF(self.font()).horizontalAdvance(" ")
        rects: list[QRectF] = []
        block = self.document().findBlock(s)
        while block.isValid() and block.position() <= e:
            layout = block.layout()
            bpos = block.position()
            line_count = layout.lineCount()
            for i in range(line_count):
                line = layout.lineAt(i)
                ls = bpos + line.textStart()
                line_end = ls + line.textLength()
                origin = self._line_origin(block, line, offsets)
                a, b = max(s, ls), min(e, line_end)
                if a < b:
                    xa, _ = line.cursorToX(a - bpos)
                    xb, _ = line.cursorToX(b - bpos)
                    rects.append(QRectF(origin.x() + (xa - line.x()), origin.y(),
                                        xb - xa, line.height()))
                # The block-joining newline sits at `line_end` on this (the
                # block's last) line and is only "selected" when the
                # selection extends strictly past it.
                if i == line_count - 1 and block.next().isValid() and s <= line_end < e:
                    xe, _ = line.cursorToX(line_end - bpos)
                    rects.append(QRectF(origin.x() + (xe - line.x()), origin.y(),
                                        newline_w, line.height()))
            block = block.next()
        return rects

    def cursor_position_at(self, local_pt: QPointF) -> int:
        """Document position nearest *local_pt* (painted, un-rotated frame).

        The inverse of :meth:`caret_rect_local`: the line whose painted band
        contains (or is nearest to) the point's y, then ``QTextLine.xToCursor``
        on the x relative to that line's painted origin. A point above the
        first line or below the last resolves to that nearest line (the
        running ``dy`` minimum below), matching common editor hit-testing.
        """
        offsets = self._layout_offsets()
        best = None                       # (dy, position)
        block = self.document().begin()
        while block.isValid():
            layout = block.layout()
            for i in range(layout.lineCount()):
                line = layout.lineAt(i)
                origin = self._line_origin(block, line, offsets)
                top, bot = origin.y(), origin.y() + line.height()
                y = local_pt.y()
                dy = 0.0 if top <= y < bot else min(abs(y - top), abs(y - bot))
                if best is None or dy < best[0]:
                    rel = line.xToCursor(local_pt.x() - origin.x() + line.x())
                    best = (dy, block.position() + rel)
            block = block.next()
        return best[1] if best is not None else 0

    # ── Grip protocol (9 box grips) ─────────────────────────────────────────
    # Indices (clockwise from top-left, matching RectangleItem/NoteAnnotation):
    #   0=TL  1=TM  2=TR  3=RM  4=BR  5=BM  6=BL  7=LM  8=Centre

    def _content_size(self) -> tuple[float, float]:
        r = super().boundingRect()
        return r.width(), r.height()

    def grip_points(self) -> list[QPointF]:
        r = self._box_rect_local()
        cx, cy = r.center().x(), r.center().y()
        local = [
            QPointF(r.left(),  r.top()),    QPointF(cx, r.top()),          QPointF(r.right(), r.top()),
            QPointF(r.right(), cy),         QPointF(r.right(), r.bottom()), QPointF(cx, r.bottom()),
            QPointF(r.left(),  r.bottom()), QPointF(r.left(),  cy),        QPointF(cx, cy),
        ]
        return [self.mapToScene(p) for p in local]

    # Which axes a grip drag touches (containment C5.7 review I2 — the
    # axis-isolated box resize ported from the legacy paper
    # ``_resize_box_on_paper``).  A left/right MID-edge (3,7) changes ONLY the
    # width; a top/bottom MID-edge (1,5) changes ONLY the height; corners
    # (0,2,4,6) change both.  Freezing the untouched axis is what keeps an
    # auto-height (0) box auto-height after a pure-horizontal drag.
    _GRIP_CHANGES_X = frozenset({0, 2, 3, 4, 6, 7})
    _GRIP_CHANGES_Y = frozenset({0, 1, 2, 4, 5, 6})

    def apply_grip(self, index: int, pos: QPointF):
        """Resize (edges/corners) or translate (centre) by dragging a grip.

        Reproduces the box-native resize: horizontal drags set wrap width,
        vertical drags set box height (content-min clamped); the opposite edge
        stays fixed.  Font (``height_mm``) is never touched.  A mid-edge drag is
        axis-isolated (review I2): a left/right mid-edge writes ONLY
        ``wrap_width_mm`` and a top/bottom mid-edge writes ONLY
        ``box_height_mm`` — the untouched axis' stored field is left exactly as
        it was (so an auto-height 0 box stays 0 after a horizontal drag).
        """
        local = self.mapFromScene(pos)
        r = self._box_rect_local()
        # First horizontal resize from auto-width: seed wrap from content width.
        if self.textWidth() <= 0 and index in (0, 2, 3, 4, 6, 7):
            self.setTextWidth(r.width())
            r = self._box_rect_local()
        l, t, ri, b = r.left(), r.top(), r.right(), r.bottom()
        if   index == 0: nl, nt, nr, nb = local.x(), local.y(), ri, b
        elif index == 1: nl, nt, nr, nb = l, local.y(), ri, b
        elif index == 2: nl, nt, nr, nb = l, local.y(), local.x(), b
        elif index == 3: nl, nt, nr, nb = l, t, local.x(), b
        elif index == 4: nl, nt, nr, nb = l, t, local.x(), local.y()
        elif index == 5: nl, nt, nr, nb = l, t, ri, local.y()
        elif index == 6: nl, nt, nr, nb = local.x(), t, ri, local.y()
        elif index == 7: nl, nt, nr, nb = local.x(), t, ri, b
        elif index == 8:
            dx, dy = local.x() - r.center().x(), local.y() - r.center().y()
            self._reanchor(dx, dy)
            return
        else:
            return
        new_r = QRectF(QPointF(nl, nt), QPointF(nr, nb)).normalized()
        self._reanchor(new_r.left(), new_r.top())
        self.prepareGeometryChange()
        self._commit_box_size(
            new_r.width() if index in self._GRIP_CHANGES_X else None,
            new_r.height() if index in self._GRIP_CHANGES_Y else None,
        )
        self.sync_data_from_item()

    def _content_height_mm(self) -> float:
        """Current text-content height in surface mm (the auto-height seed)."""
        scale = self.scale() or 1.0
        return super().boundingRect().height() * scale

    def _commit_box_size(self, local_w: "float | None", local_h: "float | None"):
        """Write the box wrap/height for the changed axes, clamped in MM.

        ``local_w``/``local_h`` are the proposed box extents in the item's LOCAL
        (unscaled) frame; ``None`` skips that axis (mid-edge isolation, review
        I2).  The min clamps are applied in SURFACE MM (``MIN_TEXT_WRAP_WIDTH_MM``
        wrap, content-height for the box) — NOT local units — so a paper item
        (scale != 1) clamps to the same physical minimum the retired paper
        ``_resize_box_on_paper`` used.  Font ``height_mm`` is never touched.
        """
        scale = self.scale() or 1.0
        if local_w is not None:
            new_w_mm = max(local_w * scale, MIN_TEXT_WRAP_WIDTH_MM)
            self.setTextWidth(new_w_mm / scale)
            self._data.wrap_width_mm = new_w_mm
        if local_h is not None:
            new_h_mm = max(local_h * scale, self._content_height_mm())
            self._data.box_height_mm = new_h_mm

    def _reanchor(self, local_dx: float, local_dy: float):
        """Shift pos() by a LOCAL-frame offset (honours rotation at angle != 0)."""
        delta = self.mapToScene(QPointF(local_dx, local_dy)) - self.mapToScene(QPointF(0.0, 0.0))
        self.moveBy(delta.x(), delta.y())

    # ── Selection-manipulator adapter (translate / scale / rotate) ──────────
    # Governing spec: docs/specs/selection-manipulator.md.

    def manip_capabilities(self) -> set:
        """Translate + rotate on the model surface; + scale on paper.

        A model/Block-Editor text resize is a **font-constant box resize**
        (``apply_grip`` changes wrap width / box height, never the cap height), not
        a uniform scale.  The box-native "scale" path previews via a uniform
        ``setTransform`` that scales the glyphs during the drag and snaps them back
        to the set height on release (WYSIWYG break).  Dropping "scale" routes the
        resize through the live parametric grips (``manip_handles`` → ``apply_grip``),
        so the text stays a consistent height throughout the drag.

        Paper text keeps the box-native translate+scale+rotate path (device-
        independent, undo-routed, and unchanged by this fix)."""
        if self.is_device_independent():
            return {"translate", "scale", "rotate"}
        return {"translate", "rotate"}

    def manip_translate(self, dx: float, dy: float):
        self.moveBy(dx, dy)

    def manip_bounds(self) -> QRectF:
        return self.mapRectToScene(self._box_rect_local())

    def manip_handles(self):
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0, 2, 4, 6, 8})

    def manip_box_extra_handles(self):
        from .manip_handle import GripHandle
        return [GripHandle(self, 8, circular=True)]   # centre move grip (unrotated)

    def grip_render_angle(self, index: int) -> float:
        return self._angle

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        self.set_angle(self._angle + angle_deg, pivot)

    def manip_scale(self, fx: float, fy: float, anchor: "QPointF") -> None:
        """Baked resize about a scene *anchor* by (fx, fy) in the box's own
        frame — reproduces the manipulator preview for any handle.  Font
        untouched."""
        r = self._box_rect_local()
        a = self.mapFromScene(anchor)
        left   = a.x() + (r.left()   - a.x()) * fx
        right  = a.x() + (r.right()  - a.x()) * fx
        top    = a.y() + (r.top()    - a.y()) * fy
        bottom = a.y() + (r.bottom() - a.y()) * fy
        new_r = QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()
        self._reanchor(new_r.left(), new_r.top())
        self.prepareGeometryChange()
        # Axis isolation (review I2): a mid-edge handle passes fx == 1 or
        # fy == 1 — leave that axis' stored field untouched so an auto-height
        # (0) box is not silently frozen by a pure-horizontal drag.  The min
        # clamps are applied in MM inside _commit_box_size.
        eps = 1e-9
        self._commit_box_size(
            new_r.width() if abs(fx - 1.0) > eps else None,
            new_r.height() if abs(fy - 1.0) > eps else None,
        )
        self.sync_data_from_item()

    # ── Closed-path protocol (Text is NOT fillable) ─────────────────────────

    def get_closed_path(self) -> None:
        """Text has no fillable closed path — its box fill is ``fill_color``, a
        separate mechanism.  Returning None keeps ``is_fillable()`` False, which
        suppresses the mixin's Fill property rows."""
        return None

    # ── Property protocol (scene-context-sized, like the font/box) ──────────
    #
    # PAPER (device-independent) surface: the panel + ribbon Font group expect
    # the Word-style paper form (Font/Height-as-pt/Color/Alignment=Left|Center|
    # Right) AND undo-routed writes (paper-space.md §9.6 — every commit pushes a
    # FormatTextCommand keyed on the shared data).  This is the behaviour the
    # retired paper ``TextAnnotationItem`` carried; the containment repoint (C5)
    # moves it here so the one ``TextItem`` serves both surfaces.
    #
    # MODEL / block-editor surface: the geom2d primitive protocol (no undo
    # stack of its own — the scene snapshots for undo), with L/C/R alignment.

    def _on_paper(self) -> bool:
        """True when the host scene is a paper (device-independent) surface."""
        return self.is_device_independent()

    def get_properties(self) -> dict:
        """Return the panel form dict for the current surface.

        On a paper surface the Word-style paper form is returned (formatting
        only; content is edited inline); otherwise the geom2d model form.
        """
        if self._on_paper():
            from .paper_space import _text_panel_properties
            return _text_panel_properties(self._data)
        d = self._data
        props = {
            "Text":     {"type": "header", "value": "Text"},
            "Content":  {"type": "multiline", "value": d.text},
            "Format":   {"type": "header", "value": "Format"},
            "Font":     {"type": "font", "value": d.font_family or "Arial"},
            "Height":   {"type": "number", "value": int(round(d.height_mm)), "minimum": 1},
            "Padding":  {"type": "number", "value": int(round(d.cell_padding_mm)), "minimum": 0},
            "Style":    {"type": "bool_group",
                         "keys": [("Bold", "B"), ("Italic", "I"), ("Underline", "U")],
                         "values": {"Bold": d.bold, "Italic": d.italic, "Underline": d.underline}},
            "Alignment": {"type": "icon_enum", "value": d.align,
                          "options": [("L", "align_left.svg"), ("C", "align_center.svg"),
                                      ("R", "align_right.svg")]},
            "V Align":  {"type": "icon_enum", "value": d.valign,
                         "options": [("T", "align_top.svg"), ("M", "align_middle.svg"),
                                     ("B", "align_bottom.svg")]},
            "Font Color": {"type": "color", "value": d.color or "#000000"},
            "Frame":    {"type": "header", "value": "Frame"},
            "Line Type": {"type": "enum",
                          "options": ["none", "solid", "dashed", "dotted", "dashdot"],
                          "value": ("none" if not d.border else d.border_line_type)},
            "Border Weight": {"type": "enum",
                              "options": ["Very Light", "Light", "Medium", "Heavy", "Very Heavy"],
                              "value": d.border_weight},
            "Corner":   {"type": "icon_enum", "value": d.border_corner,
                         "options": [("square", "corner_square.svg"),
                                     ("round", "corner_fillet.svg"),
                                     ("chamfer", "corner_chamfer.svg")]},
            "Corner Radius": {"type": "number", "value": int(round(d.border_corner_radius_mm)),
                              "minimum": 0},
            "Fill":     {"type": "header", "value": "Fill"},
            "Fill Color":   {"type": "color", "value": d.fill_color, "allow_none": True},
            "Fill Opacity": {"type": "percent", "value": float(d.fill_opacity),
                             "disabled": not d.fill_color},
        }
        geom2d = self._geom2d_properties()
        # Text carries no level semantics (containment spec) — strip the level
        # rows that _geom2d_properties() always appends.
        for key in ("Level", "Level Offset", "Elevation"):
            geom2d.pop(key, None)
        props.update(geom2d)
        return props

    def set_property(self, key: str, value) -> None:
        if self._on_paper():
            self._set_property_paper(key, value)
            return
        # Model / Block-Editor surface: one panel commit = one undo snapshot
        # (post-change, like Wall.set_property); a no-op commit pushes nothing.
        before = self.to_dict()
        self._set_property_model(key, value)
        sc = self.scene()
        if sc is not None and hasattr(sc, "push_undo_state") \
                and self.to_dict() != before:
            sc.push_undo_state()

    def _set_property_model(self, key: str, value) -> None:
        """Apply a model-surface panel commit to ``_data`` (no undo push)."""
        if key == "Text":
            self._data.text = str(value)
            self.setPlainText(self._data.text)
        elif key == "Content":
            self._data.text = str(value)
            self.setPlainText(self._data.text)
        elif key == "Font":
            self._data.font_family = str(value)
        elif key == "Font Color":
            self._data.color = str(value)
        elif key == "Height":
            try:
                mm = float(value)
            except (TypeError, ValueError):
                mm = self._parse_dim(value)
            if mm is not None and mm > 0:
                self._data.height_mm = mm
        elif key == "Bold":
            self._data.bold = bool(value)
        elif key == "Italic":
            self._data.italic = bool(value)
        elif key == "Underline":
            self._data.underline = bool(value)
        elif key == "Alignment":
            self._data.align = str(value)
        elif key == "V Align":
            self._data.valign = str(value)
        elif key == "Padding":
            try:
                self._data.cell_padding_mm = max(0.0, float(value))
            except (TypeError, ValueError):
                return
        elif key == "Fill Color":
            self._data.fill_color = str(value)
        elif key == "Fill Opacity":
            self._data.fill_opacity = float(value)
        elif key == "Border":
            self._data.border = bool(value)
        elif key == "Border Weight":
            self._data.border_weight = str(value)
        elif key == "Line Type":
            # Panel drives border on/off via a "none" sentinel (no Border toggle).
            if str(value) == "none":
                self._data.border = False
            else:
                self._data.border = True
                self._data.border_line_type = str(value)
        elif key == "Corner":
            self._data.border_corner = str(value)
        elif key == "Corner Radius":
            try:
                self._data.border_corner_radius_mm = max(0.0, float(value))
            except (TypeError, ValueError):
                return
        elif self._geom2d_set(key, value):
            return
        else:
            return
        self.prepareGeometryChange()
        self._apply_format()

    def _set_property_paper(self, key: str, value) -> None:
        """Apply a paper-panel commit through the paper undo stack (§9.6).

        On a scene with an undo stack, pushes a FormatTextCommand (one command
        per commit — the panel/ribbon wraps multi-select in a macro).  Off-scene
        (the pre-placement template) or while a command is being applied, writes
        the field directly and reformats.  Mirrors the retired paper
        ``TextAnnotationItem.set_property`` exactly so the ribbon Font group and
        the property panel keep undo-routed formatting for free.
        """
        from .paper_space import _text_panel_change
        from .paper_commands import FormatTextCommand
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

    # ── Serialisation ───────────────────────────────────────────────────────

    def sync_data_from_item(self) -> None:
        """Write the current scene position back into the data object."""
        self._data.x = self.pos().x()
        self._data.y = self.pos().y()

    def to_dict(self) -> dict:
        """Serialise to the shared "text" record (data.to_dict()), position-synced.

        NO ``level`` key (text carries no level semantics in this task).
        """
        self.sync_data_from_item()
        self._data.angle = self._angle
        return dict(self._data.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "TextItem":
        data = TextAnnotationData.from_dict(d)
        obj = cls(data)
        obj.setPos(data.x, data.y)
        if data.angle:
            obj.set_angle(data.angle)
        return obj

    # ── A. Inline-edit lifecycle (carried from TextAnnotationItem) ──────────

    def is_effectively_empty(self) -> bool:
        """True when the block contains only whitespace."""
        return self.toPlainText().strip() == ""

    def begin_edit(self) -> None:
        """Enter inline-edit mode: enable text interaction and take focus."""
        self._editing = True
        self._text_before_edit = self._data.text
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        sc = self.scene()
        if sc is not None:
            sc._editing_item = self

    def commit_edit(self) -> str:
        """Commit the edited text into data and exit edit mode."""
        self._editing = False
        sc = self.scene()
        if sc is not None and getattr(sc, "_editing_item", None) is self:
            sc._editing_item = None
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        new_text = self.toPlainText()
        self._data.text = new_text
        self.prepareGeometryChange()
        self._apply_format()
        return new_text

    def cancel_edit(self) -> None:
        """Revert to the pre-edit text and exit edit mode without committing.

        On a paper scene a still-pending placement (``scene._pending_text`` is
        self) is routed through ``commit_place_text`` so an empty Esc leaves
        nothing tracked (parity with the retired paper TextAnnotationItem).
        """
        self._editing = False
        scene = self.scene()
        if scene is not None and getattr(scene, "_editing_item", None) is self:
            scene._editing_item = None
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setPlainText(self._text_before_edit)
        self._data.text = self._text_before_edit
        self.prepareGeometryChange()
        self._apply_format()
        if scene is not None and getattr(scene, "_pending_text", None) is self:
            scene.commit_place_text(self)

    def _on_edit_finished(self) -> None:
        """End inline editing with paper undo bookkeeping.

        A pending placement (``scene._pending_text`` is self) routes to
        ``commit_place_text`` (discards empty, else pushes AddText).  An existing
        tracked block commits the edit (applies the new text live) and records
        the change via the scene's ``_push_text_edit`` helper.  Off a paper
        scene (model surface) this is a plain ``commit_edit`` — the model scene
        snapshots for undo separately.
        """
        scene = self.scene()
        if scene is not None and getattr(scene, "_pending_text", None) is self:
            scene.commit_place_text(self)
            return
        old = self._text_before_edit
        new = self.commit_edit()
        if scene is not None and hasattr(scene, "_push_text_edit"):
            scene._push_text_edit(self._data, old, new)

    def _start_caret_blink(self) -> None:
        """Start the self-painted caret blink (platform flash rate)."""
        if self._caret_timer is None:
            self._caret_timer = QTimer(self)
            self._caret_timer.timeout.connect(self._toggle_caret)
        self._caret_on = True
        flash = QApplication.cursorFlashTime()
        if flash > 0:                     # 0/negative = platform "no blink"
            self._caret_timer.start(max(1, flash // 2))
        self.update()

    def _stop_caret_blink(self) -> None:
        """Stop the blink timer and hide the caret."""
        if self._caret_timer is not None:
            self._caret_timer.stop()
        self._caret_on = False
        self.update()

    def _toggle_caret(self) -> None:
        """Flip the caret's visible/hidden phase (blink-timer tick).

        Guards against a stray timer tick firing after the session ended or
        the item left its scene (e.g. deleted mid-edit) — stop the timer
        instead of touching a dead/unparented item.
        """
        if not self._editing or self.scene() is None:
            if self._caret_timer is not None:
                self._caret_timer.stop()
            return
        self._caret_on = not self._caret_on
        self.update()

    def _reset_caret_phase(self) -> None:
        """Show the caret now and restart the blink (after a key / cursor move)."""
        if not self._editing:
            return
        self._caret_on = True
        if self._caret_timer is not None and self._caret_timer.isActive():
            self._caret_timer.start()
        self.update()

    _SWALLOWED_FKEYS = frozenset(getattr(Qt.Key, f"Key_F{i}") for i in range(1, 13))

    def mouseDoubleClickEvent(self, event) -> None:
        """Paper: enter inline-edit on double-click.  Model: the scene's mouse
        gate (TextEditController) owns entry — ignore here so a double-click
        while a placement tool is active can never enter edit."""
        if not self._on_paper():
            event.ignore()
            return
        if not self._editing:
            self.begin_edit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _request_commit(self) -> None:
        """Model surface: end the session through the scene's commit funnel."""
        sc = self.scene()
        if sc is not None and hasattr(sc, "commit_text_edit"):
            sc.commit_text_edit()
        else:
            self.commit_edit()

    def _focus_out_keeps_edit(self, event) -> bool:
        """Model-surface focus-out exceptions (spec § Inline edit)."""
        if event.reason() in (Qt.FocusReason.ActiveWindowFocusReason,
                              Qt.FocusReason.PopupFocusReason):
            return True
        fw = QApplication.focusWidget()
        sc = self.scene()
        if fw is not None and sc is not None and any(
                fw is v or fw is v.viewport() for v in sc.views()):
            return True               # in-scene focus-item change (e.g. handle press)
        w = fw
        while w is not None:
            # Name match (not isinstance) avoids importing the panel module here.
            if type(w).__name__ == "PropertyManager":
                return True           # panel stays live during an edit
            w = w.parentWidget()
        return False

    def focusOutEvent(self, event) -> None:
        """Paper: auto-commit on focus loss.  Model: commit unless the focus
        change is window deactivation / popup / in-scene / the property panel."""
        if self._editing and not self._on_paper():
            if not self._focus_out_keeps_edit(event):
                self._request_commit()
            super().focusOutEvent(event)
            return
        if self._editing:
            self._on_edit_finished()
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        """Route key events to the editor or to item-level commands.

        Model surface while editing: Esc / Ctrl+Enter commit; Ctrl+B/I/U and
        F1–F12 (without Alt) are swallowed; Alt+F-key (e.g. Alt+F4) is left
        ignored so the window system still gets it; everything else goes to
        the Qt text control.  Paper while editing: Esc ends the edit
        (``_on_edit_finished``).  Not editing: Delete emits
        ``delete_requested``.
        """
        if self._editing and not self._on_paper():
            key = event.key()
            mods = event.modifiers()
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            alt = bool(mods & Qt.KeyboardModifier.AltModifier)
            if key == Qt.Key.Key_Escape or (
                    ctrl and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
                self._request_commit()
                event.accept()
                return
            if alt and key in self._SWALLOWED_FKEYS:
                # Alt+F4 (and any other Alt+F-key) must reach the window
                # system to close/act on the app — never swallow it here.
                event.ignore()
                return
            if (ctrl and key in (Qt.Key.Key_B, Qt.Key.Key_I, Qt.Key.Key_U)) \
                    or key in self._SWALLOWED_FKEYS:
                event.accept()
                return
            super().keyPressEvent(event)
            self._reset_caret_phase()
            return
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

    def contextMenuEvent(self, event) -> None:
        """Show a Delete context menu on right-click (native editor menu while
        inline-editing)."""
        if self._editing:
            super().contextMenuEvent(event)
            return
        menu = QMenu()
        delete = menu.addAction("Delete")
        action = menu.exec(event.screenPos())
        if action == delete:
            self.delete_requested.emit(self)
