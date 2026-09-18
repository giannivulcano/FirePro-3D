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

from .constants import DEFAULT_TEXT_HEIGHT_MM


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
    opaque_bg:
        When ``True``, render a white fill behind the text box.
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
    align: str = "L"                             # 'L' | 'C' | 'R'
    opaque_bg: bool = False
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
            "color": self.color, "align": self.align,
            "opaque_bg": self.opaque_bg,
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
            opaque_bg=bool(d.get("opaque_bg", False)),
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

from PyQt6.QtCore import Qt, QPointF, QRectF                      # noqa: E402
from PyQt6.QtGui import (                                          # noqa: E402
    QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QTransform,
)
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QMenu  # noqa: E402

from .constants import (                                           # noqa: E402
    DEFAULT_LEVEL, MIN_TEXT_WRAP_WIDTH_MM,
    SELECTION_GRIP_OUTLINE_WIDTH_MM, SELECTION_GRIP_SIZE_MM,
    TEXT_BOX_MARGIN_MM, TEXT_METRIC_REF_PX,
)
from .displayable_item import DisplayableItemMixin                 # noqa: E402
from .geometry_2d import Geometry2DMixin                           # noqa: E402


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

        # Bake-at-rest rotation state (data-only — NO held Qt transform).
        # _angle mirrors self._data.angle for the map* overrides; _pivot is
        # transient (None → follow the box centre at rest).
        self._angle: float = float(data.angle)
        self._pivot: QPointF | None = None

        self.init_displayable(DEFAULT_LEVEL)
        self.init_geometry2d(DEFAULT_LEVEL)

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
        """True when the host scene sizes text device-independently (PaperScene).

        A Model_Space / Block-Editor scene (or an off-scene item) sizes text in
        plain scene units instead.
        """
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
            self.document().setDocumentMargin(TEXT_BOX_MARGIN_MM / scale)
        if d.wrap_width_mm > 0 and scale > 0:
            self.setTextWidth(d.wrap_width_mm / scale)
        else:
            self.setTextWidth(-1)
            self.setTextWidth(self.document().idealWidth())

    def itemChange(self, change, value):
        """Re-derive the sizing mode when the item lands on / leaves a scene,
        and live-sync data.x/y on every move."""
        Change = QGraphicsItem.GraphicsItemChange
        if change == Change.ItemSceneHasChanged:
            # The scene (hence the sizing mode) just changed — reformat so the
            # same data renders at the right physical size on this surface.
            self.prepareGeometryChange()
            self._apply_format()
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
        """Paint the text block with an opaque-bg knockout and inline-edit frame.

        Renders (with the bake-at-rest rotation applied like NoteAnnotation):
        (1) a solid-white knockout over the box rect when ``opaque_bg`` is set,
        (2) the text via super(), (3) the lighter #88aaff cosmetic border while
        inline-editing (the EDITING state — distinct from SELECTED, whose frame
        is drawn by the scene's SelectionManipulator).
        """
        box = self._box_rect_local()
        painter.save()
        if self._angle != 0.0:
            painter.setWorldTransform(self._rotation_transform(), True)
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
        text = self._data.text or ""
        if text.strip() == "":
            return QPainterPath()

        doc = self.document()
        doc.documentLayout().documentSize()   # force the lazy layout to run
        font = self.font()
        outline = QPainterPath()
        block = doc.begin()
        while block.isValid():
            layout = block.layout()
            block_pos = layout.position()      # block's offset within the document
            block_text = block.text()
            for i in range(layout.lineCount()):
                line = layout.lineAt(i)
                # Each newline starts a NEW block (not a new line in one block),
                # so the baseline is block_offset + intra-block line y + ascent.
                base_x = block_pos.x() + line.x()
                base_y = block_pos.y() + line.y() + line.ascent()
                start = line.textStart()
                length = line.textLength()
                # A block never contains a newline (Qt splits blocks on \n), so
                # the run text is used as-is.
                run_text = block_text[start:start + length].rstrip("  \n")
                if run_text:
                    outline.addText(QPointF(base_x, base_y), font, run_text)
            block = block.next()

        if self._angle != 0.0:
            outline = self._rotation_transform().map(outline)
        return outline

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

    def apply_grip(self, index: int, pos: QPointF):
        """Resize (edges/corners) or translate (centre) by dragging a grip.

        Reproduces the box-native resize: horizontal drags set wrap width,
        vertical drags set box height (content-min clamped); the opposite edge
        stays fixed.  Font (``height_mm``) is never touched.
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
        _, ch = self._content_size()
        new_w = max(new_r.width(), MIN_TEXT_WRAP_WIDTH_MM)
        new_h = max(new_r.height(), ch)
        self._reanchor(new_r.left(), new_r.top())
        self.prepareGeometryChange()
        self.setTextWidth(new_w)
        scale = self.scale() or 1.0
        self._data.wrap_width_mm = new_w * scale
        self._data.box_height_mm = new_h * scale
        self.sync_data_from_item()

    def _reanchor(self, local_dx: float, local_dy: float):
        """Shift pos() by a LOCAL-frame offset (honours rotation at angle != 0)."""
        delta = self.mapToScene(QPointF(local_dx, local_dy)) - self.mapToScene(QPointF(0.0, 0.0))
        self.moveBy(delta.x(), delta.y())

    # ── Selection-manipulator adapter (translate / scale / rotate) ──────────
    # Governing spec: docs/specs/selection-manipulator.md.

    def manip_capabilities(self) -> set:
        """Translate + scale + rotate; scale drops when rotated (box-native
        resize is only correct axis-aligned — matches NoteAnnotation/Rectangle)."""
        if self._angle != 0.0:
            return {"translate", "rotate"}
        return {"translate", "scale", "rotate"}

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
        _, ch = self._content_size()
        new_w = max(new_r.width(), MIN_TEXT_WRAP_WIDTH_MM)
        new_h = max(new_r.height(), ch)
        self._reanchor(new_r.left(), new_r.top())
        self.prepareGeometryChange()
        self.setTextWidth(new_w)
        scale = self.scale() or 1.0
        self._data.wrap_width_mm = new_w * scale
        self._data.box_height_mm = new_h * scale
        self.sync_data_from_item()

    # ── Closed-path protocol (Text is NOT fillable) ─────────────────────────

    def get_closed_path(self) -> None:
        """Text has no fillable closed path — its box fill is ``opaque_bg``, a
        separate mechanism.  Returning None keeps ``is_fillable()`` False, which
        suppresses the mixin's Fill property rows."""
        return None

    # ── Primitive property protocol (geom2d level/offset; fill suppressed) ──

    def get_properties(self) -> dict:
        """Return the panel form dict — text formatting + the geom2d rows.

        Fill rows stay suppressed because ``is_fillable()`` is False.
        """
        props = {
            "Type":      {"type": "label",  "value": "Text"},
            "Text":      {"type": "string", "value": self._data.text},
            "Height":    {"type": "dimension", "value": self._fmt(self._data.height_mm),
                          "value_mm": self._data.height_mm},
            "Bold":      {"type": "toggle", "value": bool(self._data.bold)},
            "Italic":    {"type": "toggle", "value": bool(self._data.italic)},
            "Underline": {"type": "toggle", "value": bool(self._data.underline)},
            "Alignment": {"type": "enum", "options": ["L", "C", "R"],
                          "value": self._data.align},
            "Opaque Background": {"type": "toggle", "value": bool(self._data.opaque_bg)},
        }
        geom2d = self._geom2d_properties()
        # Text carries no level semantics (containment spec) — strip the level
        # rows that _geom2d_properties() always appends.
        for key in ("Level", "Level Offset", "Elevation"):
            geom2d.pop(key, None)
        props.update(geom2d)
        return props

    def set_property(self, key: str, value) -> None:
        if key == "Text":
            self._data.text = str(value)
            self.setPlainText(self._data.text)
        elif key == "Height":
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
        elif key == "Opaque Background":
            self._data.opaque_bg = bool(value)
        elif self._geom2d_set(key, value):
            return
        else:
            return
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
        """Revert to the pre-edit text and exit edit mode without committing."""
        self._editing = False
        scene = self.scene()
        if scene is not None and getattr(scene, "_editing_item", None) is self:
            scene._editing_item = None
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setPlainText(self._text_before_edit)
        self._data.text = self._text_before_edit
        self.prepareGeometryChange()
        self._apply_format()

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
            self.commit_edit()
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        """Route key events to the editor or to item-level commands."""
        if self._editing:
            if event.key() == Qt.Key.Key_Escape:
                self.commit_edit()
                self.clearFocus()
                event.accept()
                return
            super().keyPressEvent(event)   # Enter=newline, Delete=char
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """Show a Delete context menu on right-click (native editor menu while
        inline-editing)."""
        if self._editing:
            super().contextMenuEvent(event)
            return
        menu = QMenu()
        menu.addAction("Delete")
        # TODO(containment C7/deletion-routing): wire Delete action when deletion routing lands
        menu.exec(event.screenPos())
