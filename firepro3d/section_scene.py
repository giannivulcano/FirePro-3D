"""
section_scene.py
================
QGraphicsScene that projects 3D model entities onto a vertical elevation plane.

Each elevation direction (North/South/East/West) projects onto a different axis:
  North (looking from +Y → -Y): H = world X, V = world Z
  South (looking from -Y → +Y): H = -world X, V = world Z
  East  (looking from +X → -X): H = -world Y, V = world Z
  West  (looking from -X → +X): H = world Y, V = world Z

Scene coordinates: H increases rightward, V (= -Z) increases downward (Qt convention).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsEllipseItem, QGraphicsSimpleTextItem, QGraphicsPathItem,
    QGraphicsItem, QGraphicsTextItem, QStyle,
)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QPointF, QLineF, QTimer
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QFont, QFontMetricsF, QPainterPath,
    QPainterPathStroker, QPainter,
)

from PyQt6.QtCore import QSettings

from .constants import DEFAULT_LEVEL, TOKEN_AUTO, TOKEN_BG
from . import theme as th
from .colour_tokens import resolve_colour, resolve_pen_brush, section_fill_colour
from .displayable_item import draw_section_hatch
from .halo_selection import HaloSelectionMixin
from .section_marker import SectionBasis, ZONE_CUT, ZONE_BEHIND, ZONE_HIDDEN

if TYPE_CHECKING:
    from .model_space import Model_Space
    from .level_manager import LevelManager
    from .scale_manager import ScaleManager

# Data role for storing source entity reference on projected items
_ROLE_SOURCE = Qt.ItemDataRole.UserRole

# Marker role so elevation views can filter these from Ctrl+A
_ROLE_ELEV_ANNOTATION = Qt.ItemDataRole.UserRole + 1


# ─────────────────────────────────────────────────────────────────────────────
# Colour-source items — stored colour strings resolved per paint (HF1)
# ─────────────────────────────────────────────────────────────────────────────

class _ColourSrcMixin:
    """Paints with stored colour *strings* (``#hex`` | ``token:*`` | ``""``)
    resolved on the surface the item paints on, never latched at build time.

    An elevation scene is rendered on the canvas and, through a sheet viewport,
    onto paper (PDF / print) from the same items: a colour resolved when the
    view was built would plot canvas ink on white paper. ``set_colour_src``
    records the sources; ``paint`` resolves them with ``item=self`` so the
    paper pass (or a ``paints_on_paper`` scene) picks the paper surface.
    Items with no source paint as a stock Qt item.
    """

    _pen_src = None
    _brush_src = None
    _src_alpha = None
    _src_tint = None            # callable(QColor) -> QColor, e.g. lighter(150)

    def set_colour_src(self, pen=None, brush=None, alpha=None, tint=None) -> None:
        """Record the stored pen / brush colour strings (``None`` = leave that
        half as set). The pen / brush also get the canvas colour now so any
        reader of them sees a valid colour."""
        self._pen_src, self._brush_src = pen, brush
        self._src_alpha, self._src_tint = alpha, tint
        p, b = self.resolved_pen_brush()
        if pen is not None:
            self.setPen(p)
        if brush is not None:
            self.setBrush(b)

    def resolved_pen_brush(self):
        """``(pen, brush)`` to paint with right now (see ``resolve_pen_brush``)."""
        brush = self.brush() if hasattr(self, "brush") else QBrush()   # lines: none
        pen, brush = resolve_pen_brush(self, self.pen(), brush,
                                       self._pen_src, self._brush_src,
                                       self._src_alpha)
        if self._src_tint is not None:
            if self._pen_src is not None:
                pen.setColor(self._src_tint(pen.color()))
            if self._brush_src is not None:
                brush = QBrush(self._src_tint(brush.color()))
        return pen, brush

    def _draw_shape(self, painter) -> None:
        raise NotImplementedError

    def paint(self, painter, option, widget=None):
        if self._pen_src is None and self._brush_src is None:
            super().paint(painter, option, widget)
            return
        pen, brush = self.resolved_pen_brush()
        painter.setPen(pen)
        painter.setBrush(brush)
        self._draw_shape(painter)
        if option.state & QStyle.StateFlag.State_Selected:
            fg = option.palette.windowText().color()
            bg = QColor(Qt.GlobalColor.black if fg.red() > 127
                        else Qt.GlobalColor.white)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for col, style in ((bg, Qt.PenStyle.SolidLine),
                               (fg, Qt.PenStyle.DashLine)):
                painter.setPen(QPen(col, 0, style))
                painter.drawRect(self.boundingRect())


class _SrcRect(_ColourSrcMixin, QGraphicsRectItem):
    def _draw_shape(self, painter):
        painter.drawRect(self.rect())


class _SrcLine(_ColourSrcMixin, QGraphicsLineItem):
    def _draw_shape(self, painter):
        painter.drawLine(self.line())


class _SrcEllipse(_ColourSrcMixin, QGraphicsEllipseItem):
    def _draw_shape(self, painter):
        painter.drawEllipse(self.rect())


class _SrcPath(_ColourSrcMixin, QGraphicsPathItem):
    def _draw_shape(self, painter):
        painter.drawPath(self.path())


class _SrcSimpleText(_ColourSrcMixin, QGraphicsSimpleTextItem):
    def _draw_shape(self, painter):
        painter.setFont(self.font())
        painter.setPen(QPen(painter.brush().color()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(QPointF(0, QFontMetricsF(self.font()).ascent()),
                         self.text())


class _ElevLabel(QGraphicsTextItem):
    """Bubble label whose colour is a stored string resolved per paint."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._src = None
        self._tint = None

    def set_colour_src(self, src, tint=None) -> None:
        self._src, self._tint = src, tint
        self.setDefaultTextColor(self._now())     # canvas colour for readers

    def _now(self) -> QColor:
        c = resolve_colour(self._src, item=self)
        return self._tint(c) if self._tint is not None else c

    def paint(self, painter, option, widget=None):
        if self._src is None:
            super().paint(painter, option, widget)
            return
        painter.setFont(self.font())
        painter.setPen(self._now())
        painter.drawText(self.boundingRect(), Qt.AlignmentFlag.AlignCenter,
                         self.toPlainText())


# ─────────────────────────────────────────────────────────────────────────────
# Read-only proxy items — model entities projected into elevation (§3.1)
# ─────────────────────────────────────────────────────────────────────────────

class _ElevReadOnlyProxyMixin:
    """Grants the SelectionManipulator wrap (frame parity with the plan scene)
    to an otherwise read-only elevation projection.

    The manipulator only wraps items that declare a ``"translate"`` capability
    (``item_capabilities`` → ``rebake`` exclusion; see design decision #4).
    Elevation projects model entities (walls/openings/pipes/sprinklers/floor-
    slabs/roofs) as READ-ONLY items — geometry is authored only in plan
    (``view-relationships.md §3.1``). To get *selection parity* (the frame
    shows on click) without making them editable, this mixin supplies a **no-op**
    ``manip_translate``: it grants the capability so the frame wraps, but the
    interior-drag bakes nothing. Proxies deliberately implement no
    ``manip_handles``/``manip_scale``/``manip_rotate`` → the manipulator shows
    the **frame + zero editing handles**.
    """

    def manip_translate(self, dx: float, dy: float) -> None:
        """No-op: elevation projections are not editable (§3.1). Exists solely
        to obtain the manipulator frame for selection parity with plan."""
        # Intentionally inert — read-only projection.

    def manip_handles(self):
        """Explicitly ZERO editing handles: frame-only parity for a read-only
        proxy. Declaring this (returning ``[]``) is authoritative in
        ``SelectionManipulator._active_handles`` — it suppresses the rigid
        resize fallback that a bare translate-only item (e.g. a Node) receives,
        so the projection never looks editable (design decision #4)."""
        return []


class _ElevProxyRect(_ElevReadOnlyProxyMixin, _SrcRect):
    """Read-only rect proxy (walls, opening voids, floor slabs, roofs)."""

    HALO_AREA = True  # HALO: solid projection — cursor inside = direct hit


class _ElevProxyLine(_ElevReadOnlyProxyMixin, _SrcLine):
    """Read-only line proxy (pipes)."""


class _ElevProxyEllipse(_ElevReadOnlyProxyMixin, _SrcEllipse):
    """Read-only ellipse proxy (sprinklers)."""

    HALO_AREA = True  # HALO: solid projection — cursor inside = direct hit


class _ElevCutRect(_ElevProxyRect):
    """A cut cross-section (wall / slab): Section colour body + Section
    pattern hatch inside the rect, outline in the category Colour (s5)."""

    _section_src = None
    _pattern = "diagonal"
    _hatch_scene = None      # the model scene (pattern registry / drafting factor)

    def set_section(self, section_src, pattern, hatch_scene):
        self._section_src = section_src
        self._pattern = pattern or "diagonal"
        self._hatch_scene = hatch_scene

    def _draw_shape(self, painter):
        pen, _brush = self.resolved_pen_brush()
        path = QPainterPath()
        path.addRect(self.rect())
        draw_section_hatch(painter, path, self._hatch_scene,
                           color=pen.color(), pattern=self._pattern,
                           line_width=1.0,
                           section_fill=section_fill_colour(self._section_src, self),
                           hatch_scale=1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())


class _ElevCutEllipse(_ElevProxyEllipse):
    """A cut pipe: filled circle of the drawn OD in the Section colour (s5)."""


# ─────────────────────────────────────────────────────────────────────────────
# ElevGridlineItem — selectable gridline in elevation view
# ─────────────────────────────────────────────────────────────────────────────

class _ElevBubble(_SrcEllipse):
    """Bubble at a gridline/datum endpoint in elevation view.

    Clicking selects the parent composite item.  Visual appearance mirrors
    the plan-view GridBubble.
    """

    HALO_AREA = True  # HALO: filled bubble — cursor inside = direct hit

    def __init__(self, radius: float, label: str, color: QColor,
                 fill: QColor, parent: QGraphicsItem | None = None,
                 color_src: str | None = None, fill_src: str | None = None):
        super().__init__(-radius, -radius, 2 * radius, 2 * radius, parent)
        self._radius = radius
        pen = QPen(color, max(1, radius * 0.04))
        self.setPen(pen)
        self.setBrush(QBrush(fill))
        self.setZValue(500)

        self._label = _ElevLabel(label, self)
        self._label.setDefaultTextColor(color.lighter(150))
        font = QFont("Consolas")
        font.setPixelSize(max(1, int(radius * 0.9)))
        font.setBold(True)
        self._label.setFont(font)
        self._center_label()
        if color_src is not None or fill_src is not None:
            # Stored strings: resolved per paint on the surface painted on.
            self.set_colour_src(pen=color_src, brush=fill_src)
        if color_src is not None:
            self._label.set_colour_src(color_src, lambda c: c.lighter(150))

    def set_label(self, text: str):
        self._label.setPlainText(text)
        self._center_label()

    def _center_label(self):
        br = self._label.boundingRect()
        self._label.setPos(-br.width() / 2, -br.height() / 2)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        parent = self.parentItem()
        if parent is not None and parent.isSelected():
            r = self._radius
            base_color = self.resolved_pen_brush()[0].color()
            highlight = QPen(base_color.lighter(150), max(1, r * 0.08))
            painter.setPen(highlight)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def mousePressEvent(self, event):
        parent = self.parentItem()
        if parent is not None:
            scene = parent.scene()
            if scene is not None:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    parent.setSelected(not parent.isSelected())
                else:
                    scene.clearSelection()
                    parent.setSelected(True)
        event.accept()


class ElevGridlineItem(QGraphicsLineItem):
    """Interactive gridline in an elevation view — selectable with grip handles."""

    def __init__(self, h_pos: float, v_top: float, v_bot: float,
                 label: str, bubble_r: float,
                 color: QColor, fill: QColor, pen_w: float,
                 opacity: float = 1.0,
                 color_src: str | None = None, fill_src: str | None = None):
        super().__init__(h_pos, v_top, h_pos, v_bot)
        # Stored colour strings (display-manager values): resolved per paint,
        # so a sheet viewport plots them on paper. ``color`` / ``fill`` are
        # their canvas resolution, kept for readers and the no-source case.
        self._grid_src = color_src
        self._h = h_pos
        self._bubble_r = bubble_r
        self._label = label  # gridline label used as override key

        # Line pen — suppress default; drawn manually in paint()
        self.setPen(QPen(Qt.PenStyle.NoPen))

        self._grid_color = color
        self._pen_w = pen_w

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(50)   # in front of walls/floors/roofs
        self.setOpacity(opacity)
        self.setData(_ROLE_ELEV_ANNOTATION, True)

        # Bubbles at top and bottom
        self.bubble1 = _ElevBubble(bubble_r, label, color, fill, self,
                                   color_src, fill_src)
        self.bubble2 = _ElevBubble(bubble_r, label, color, fill, self,
                                   color_src, fill_src)
        self._update_bubble_positions()

    def _update_bubble_positions(self):
        line = self.line()
        self.bubble1.setPos(line.p1())
        self.bubble2.setPos(line.p2())

    # ── Drawing ──────────────────────────────────────────────────────────

    def boundingRect(self):
        br = super().boundingRect()
        m = self._bubble_r
        return br.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        # Include the line segment so Qt paint culling doesn't hide the
        # line when both bubbles scroll off-screen (same class of bug as
        # the Room shape() fix — see TODO.md shape() audit).
        line = self.line()
        line_path = QPainterPath()
        line_path.moveTo(line.p1())
        line_path.lineTo(line.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._pen_w * 4, 8))
        path = stroker.createStroke(line_path)
        r = self._bubble_r
        path.addEllipse(self.bubble1.pos(), r, r)
        path.addEllipse(self.bubble2.pos(), r, r)
        return path

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        line = self.line()
        p1, p2 = line.p1(), line.p2()

        # Shorten to meet bubbles at edge
        dy = p2.y() - p1.y()
        length = abs(dy)
        if length > 1e-9:
            uy = dy / length
            r1 = self._bubble_r * self.bubble1.scale()
            r2 = self._bubble_r * self.bubble2.scale()
            draw_p1 = QPointF(p1.x(), p1.y() + uy * r1) if self.bubble1.isVisible() else p1
            draw_p2 = QPointF(p2.x(), p2.y() - uy * r2) if self.bubble2.isVisible() else p2
        else:
            draw_p1, draw_p2 = p1, p2

        grid_color = (self._grid_color if self._grid_src is None
                      else resolve_colour(self._grid_src, item=self))
        pen = QPen(grid_color, self._pen_w, Qt.PenStyle.DashDotLine)
        painter.setPen(pen)
        painter.drawLine(draw_p1, draw_p2)

        if self.isSelected():
            sel_pen = QPen(grid_color.lighter(150),
                           self._pen_w * 2, Qt.PenStyle.DashDotLine)
            painter.setPen(sel_pen)
            painter.drawLine(draw_p1, draw_p2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.bubble1.update()
            self.bubble2.update()
        return super().itemChange(change, value)

    # ── Grip handles ─────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        line = self.line()
        return [line.p1(), line.p2()]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Move grip along the vertical line (constrained to H position)."""
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        if index == 0:
            self.setLine(self._h, new_pos.y(), self._h, p2.y())
        elif index == 1:
            self.setLine(self._h, p1.y(), self._h, new_pos.y())
        self._update_bubble_positions()
        self.update()

    def manip_handles(self):
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0, 1})

    def manip_translate(self, dx: float, dy: float):
        """Axis-constrained interior move (§3.1 read-only-geometry invariant).

        H is pinned to ``self._h`` (a lateral shift would author geometry), so
        ``dx`` is dropped; ``dy`` shifts both endpoints, moving the vertical
        draw-extent as a whole. Mirrors how ``apply_grip`` writes the line and
        keeps the bubbles in sync. Granting this capability is what lets the
        SelectionManipulator wrap the gridline (see design decision #4).
        """
        line = self.line()
        self.setLine(self._h, line.p1().y() + dy,
                     self._h, line.p2().y() + dy)
        self._update_bubble_positions()
        self.update()

    def _commit_grip_override(self):
        """Write current Z-extent back to the scene's override dict.

        Called after a grip drag completes so the scene can persist the
        user-adjusted top/bottom extents for this gridline.
        """
        scene = self.scene()
        if scene and hasattr(scene, "_gridline_z_overrides"):
            line = self.line()
            scene._gridline_z_overrides[self._label] = {
                "v_top": line.p1().y(),
                "v_bot": line.p2().y(),
            }


class ElevDatumItem(QGraphicsLineItem):
    """Interactive level datum in an elevation view — selectable with grip handles."""

    def __init__(self, v_pos: float, h_min: float, h_max: float,
                 level_name: str, elev_str: str,
                 bubble_r: float, datum_color: QColor, fill_color: QColor,
                 pen_w: float, name_font: QFont, elev_font: QFont,
                 scale: float = 1.0, opacity: float = 1.0,
                 color_src: str | None = None, fill_src: str | None = None):
        super().__init__(h_min, v_pos, h_max, v_pos)
        # Stored colour strings, resolved per paint (see ElevGridlineItem).
        self._color_src = color_src
        self._fill_src = fill_src
        self._v = v_pos
        self._h_min = h_min
        self._h_max = h_max
        self._bubble_r = bubble_r
        self._datum_color = datum_color
        self._fill_color = fill_color
        self._pen_w = pen_w
        self._scale = scale
        self._level_name = level_name.upper() if level_name else "LEVEL"
        self._elev_str = elev_str

        # Preserve the original fonts so grip moves don't lose sizing
        self._name_font = QFont(name_font)
        self._elev_font = QFont(elev_font)

        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(50)   # in front of walls/floors/roofs
        self.setOpacity(opacity)
        self.setData(_ROLE_ELEV_ANNOTATION, True)

        # ── Bubble (4-quadrant) at left end ──────────────────────────────
        bx = h_min - bubble_r * 0.5
        self._bx = bx
        self._build_bubble(bx, v_pos, bubble_r, datum_color, fill_color, pen_w)

        # ── Labels ───────────────────────────────────────────────────────
        self._build_labels()

    def _build_bubble(self, bx, by, r, datum_color, fill_color, pen_w):
        """Build the 4-quadrant datum bubble as child items."""
        circle_pen = QPen(datum_color, pen_w)
        circle_pen.setCosmetic(False)
        cs, fs = self._color_src, self._fill_src

        circle = _SrcEllipse(bx - r, by - r, r * 2, r * 2, self)
        circle.setPen(circle_pen)
        circle.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        circle.setZValue(51)
        circle.set_colour_src(pen=cs)

        for ln in (_SrcLine(bx - r, by, bx + r, by, self),
                   _SrcLine(bx, by - r, bx, by + r, self)):
            ln.setPen(circle_pen)
            ln.set_colour_src(pen=cs)

        arc_rect = QRectF(bx - r, by - r, r * 2, r * 2)

        lq = QPainterPath()
        lq.moveTo(bx, by); lq.arcTo(arc_rect, 0, 90); lq.closeSubpath()
        lq.moveTo(bx, by); lq.arcTo(arc_rect, 180, 90); lq.closeSubpath()
        lq_item = _SrcPath(lq, self)
        lq_item.setPen(QPen(Qt.PenStyle.NoPen))
        lq_item.setBrush(QBrush(datum_color))
        lq_item.setZValue(52)
        lq_item.set_colour_src(brush=cs)

        fq = QPainterPath()
        fq.moveTo(bx, by); fq.arcTo(arc_rect, 90, 90); fq.closeSubpath()
        fq.moveTo(bx, by); fq.arcTo(arc_rect, 270, 90); fq.closeSubpath()
        fq_item = _SrcPath(fq, self)
        fq_item.setPen(QPen(Qt.PenStyle.NoPen))
        fq_item.setBrush(QBrush(fill_color))
        fq_item.setZValue(52)
        fq_item.set_colour_src(brush=fs)

    def _build_labels(self):
        """Create or recreate label items using the stored fonts."""
        tag_gap = 50 * self._scale
        tag_x = self._bx + self._bubble_r + tag_gap

        self._name_text = _SrcSimpleText(self._level_name, self)
        self._name_text.setFont(self._name_font)
        self._name_text.setBrush(QBrush(self._datum_color))
        self._name_text.set_colour_src(brush=self._color_src)
        name_br = self._name_text.boundingRect()
        self._name_text.setPos(tag_x, self._v - name_br.height() - 20)
        self._name_text.setZValue(53)

        self._elev_text = _SrcSimpleText(self._elev_str, self)
        self._elev_text.setFont(self._elev_font)
        self._elev_text.setBrush(QBrush(self._datum_color.lighter(130)))
        self._elev_text.set_colour_src(brush=self._color_src,
                                       tint=lambda c: c.lighter(130))
        self._elev_text.setPos(tag_x, self._v + 20)
        self._elev_text.setZValue(53)

    # ── Drawing ──────────────────────────────────────────────────────────

    def boundingRect(self):
        br = super().boundingRect()
        m = self._bubble_r * 2
        return br.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        r = self._bubble_r
        path.addEllipse(QPointF(self._bx, self._v), r, r)
        return path

    def paint(self, painter, option, widget=None):
        # The datum line is drawn by the scene's drawForeground() so it
        # remains visible even when the bubble has scrolled off-screen.
        # Do NOT call super().paint() — the base QGraphicsLineItem must
        # not draw its own line.
        pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    # ── Grip handles ─────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        line = self.line()
        return [line.p1(), line.p2()]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Move grip along the horizontal line (constrained to V position)."""
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        if index == 0:
            new_x = new_pos.x()
            self.setLine(new_x, self._v, p2.x(), self._v)
            r = self._bubble_r
            self._bx = new_x - r * 0.5
            self._reposition_children()
        elif index == 1:
            self.setLine(p1.x(), self._v, new_pos.x(), self._v)
        self.prepareGeometryChange()
        self.update()

    def _reposition_children(self):
        """Rebuild child items after left-grip move, preserving fonts."""
        for child in list(self.childItems()):
            if self.scene():
                self.scene().removeItem(child)

        self._build_bubble(self._bx, self._v, self._bubble_r,
                           self._datum_color, self._fill_color, self._pen_w)
        self._build_labels()

    def manip_handles(self):
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0, 1})

    def manip_translate(self, dx: float, dy: float):
        """Axis-constrained interior move (§3.1 read-only-geometry invariant).

        V is pinned to ``self._v`` (a vertical shift would author the datum's
        level elevation), so ``dy`` is dropped; ``dx`` shifts both endpoints,
        moving the horizontal draw-extent. The left endpoint carries the bubble
        + labels, so mirror ``apply_grip``'s left branch: advance ``self._bx``
        and rebuild the children (session-only, not persisted — parity).
        """
        line = self.line()
        new_x1 = line.p1().x() + dx
        new_x2 = line.p2().x() + dx
        self.setLine(new_x1, self._v, new_x2, self._v)
        self._bx += dx
        self._reposition_children()
        self.prepareGeometryChange()
        self.update()


class SectionScene(HaloSelectionMixin, QGraphicsScene):
    """Projects model entities onto a vertical plane for elevation display."""

    entitySelected = pyqtSignal(object)   # picked legacy entity
    cursorMoved = pyqtSignal(str)         # formatted "H: … Z: …"

    def __init__(self, marker, model_space: "Model_Space",
                 level_manager: "LevelManager", scale_manager: "ScaleManager",
                 parent=None):
        super().__init__(parent)
        self._marker = marker
        self._direction = marker.cardinal or "section"   # legacy readers (tests, tab titles)
        self._basis = None                                # refreshed per rebuild
        self._ms = model_space
        self._lm = level_manager
        self._sm = scale_manager
        self._refresh_basis()    # projections work before the first rebuild
        self._zones: dict[int, str] = {}
        self._cut_items: list = []
        self._show_datums = True

        # Per-view Z-extent overrides keyed by gridline label live on the
        # marker (see the ``_gridline_z_overrides`` property) so they persist.
        # Keyed by gridline label → {"v_top": float, "v_bot": float}

        # Grip-drag state (mirrors Model_Space pattern). KEPT after the legacy
        # _find_grip_hit path was retired: the manipulator's live-apply
        # GripHandle BORROWS these during a drag (same contract as the plan
        # scene — see U4).
        self._grip_item = None
        self._grip_index: int = -1
        self._grip_dragging = False

        # HALO preselection + scene-drawn rubber-band state (mixin).
        self._init_halo_state()

        # Theme (re-applied by rebuild(), so a live theme switch follows)
        self._apply_theme_colours()
        self._datum_color = QColor("#4488cc")

        # Large scene rect (in mm)
        self.setSceneRect(-500000, -500000, 1000000, 1000000)

        # Debounce rebuild
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(100)
        self._rebuild_timer.timeout.connect(self.rebuild)
        self._ms.sceneModified.connect(self._schedule_rebuild)
        self.selectionChanged.connect(self._on_selection_changed)

        # Selection manipulator — sole grip owner (retires _find_grip_hit).
        # Mirrors Model_Space._create_manipulator with an elevation commit hook
        # (no undo — elevation has none) and an exclude that keeps datum bubble
        # decoration out of the wrap so only the top-level item is framed.
        self._manipulator = None
        self._create_manipulator()

    # ── Selection manipulator ──────────────────────────────────────────────

    def _create_manipulator(self):
        """(Re)create the scene's selection manipulator and stash it."""
        from .selection_manipulator import SelectionManipulator
        self._manipulator = SelectionManipulator(
            self, commit_hook=self._commit_elev_grip,
            handle_units="px", exclude=self._manip_exclude)
        return self._manipulator

    def _live_manip(self):
        """Return the manipulator, recreating it if a scene rebuild deleted its
        underlying C++ object (rebuild() calls self.clear(), which removes the
        manipulator scene item — same self-heal as Model_Space._live_manip)."""
        from PyQt6 import sip
        m = getattr(self, "_manipulator", None)
        if m is not None and not sip.isdeleted(m):
            return m
        return self._create_manipulator()

    def _manip_exclude(self, item) -> bool:
        """Items the manipulator must never wrap: the gridline/datum bubble
        decoration (child ``_ElevBubble``), so only the top-level selectable
        gridline/datum is framed."""
        return isinstance(item, _ElevBubble)

    def _commit_elev_grip(self, mode):
        """Manipulator commit hook (no undo). Persist each selected gridline's
        adjusted Z-extent into ``_gridline_z_overrides``; datum edits are
        session-only (parity)."""
        for it in self.selectedItems():
            if isinstance(it, ElevGridlineItem):
                it._commit_grip_override()

    # ── HALO hooks ─────────────────────────────────────────────────────────

    def _halo_resolve(self, item):
        """Resolve a hit decoration to its selectable owner: walk the FULL parent
        chain so a bubble's label text (a grandchild) resolves to the gridline/
        datum too; everything else is identity."""
        p = item.parentItem()
        while p is not None:
            if isinstance(p, (ElevGridlineItem, ElevDatumItem)):
                return p
            p = p.parentItem()
        return item

    def _emit_halo_readout(self):
        """Emit the HALO stack readout (§3.3) on ``cursorMoved``.

        Defined now to avoid a latent AttributeError from the mixin's
        ``halo_update``; the elevation view's HALO wiring lands in the next
        task. Format mirrors Model_Space: ``"<Type> — <i> of <N>"``."""
        item = self.halo_item()
        if item is None:
            return
        n = len(self._halo_candidates)
        self.cursorMoved.emit(f"{type(item).__name__} — {self._halo_index + 1} of {n}")

    # ── Selection sync ───────────────────────────────────────────────────

    def _on_selection_changed(self):
        """When items are selected (click or rubber-band), emit source entity."""
        selected = self.selectedItems()
        if selected:
            # Emit the last selected item's source entity
            for item in reversed(selected):
                source = item.data(_ROLE_SOURCE)
                if source is not None:
                    self.entitySelected.emit(source)
                    return
        self.entitySelected.emit(None)

    # ── Mouse handling ────────────────────────────────────────────────────
    # The legacy grip path (_find_grip_hit + _grip_dragging lifecycle) was
    # retired in U5 Leg B: the SelectionManipulator is the sole grip owner.
    # The _grip_item/_grip_index/_grip_dragging attrs are KEPT — the
    # manipulator's live-apply GripHandle borrows them during a drag.

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Don't pass right-click to base — it deselects items.
            # contextMenuEvent handles right-click menus separately.
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # HALO-committed selection (mirrors Model_Space._press_select_item).
            # A press on a manipulator handle must fall through to super() so the
            # manipulator's _HandleItem child consumes it (grip-drag) — never
            # commit selection over a handle.
            pos = event.scenePos()
            manip = self._live_manip()
            # A press over the manipulator frame/handle falls through to super()
            # so the manipulator's _HandleItem child consumes it (grip-drag /
            # interior move) — never commit a fresh HALO selection over it.
            on_manip = (manip is not None and manip.isVisible()
                        and manip.hit_test(pos))
            if not on_manip:
                ctrl = bool(event.modifiers()
                            & Qt.KeyboardModifier.ControlModifier)
                # Prefer the HALO-highlighted (hovered/cycled) candidate over the
                # raw topmost pick, so a Spacebar-cycled preselection is what the
                # click commits; fall back to the topmost selectable under cursor.
                target = self.halo_item()
                if target is None:
                    for it in self.items(pos):
                        r = self._halo_resolve(it)
                        if r is not None and (
                                r.flags()
                                & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                            target = r
                            break
                if not ctrl:
                    self.clearSelection()
                if target is not None:
                    target.setSelected(
                        not target.isSelected() if ctrl else True)
                    # Accept so the view does NOT arm a rubber band over a
                    # committed selection; empty press falls through to super()
                    # (which leaves the cleared selection for a fresh band).
                    event.accept()
                    return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Show right-click context menu for elevation view entities."""
        from .entity_context_menu import build_entity_context_menu

        # Find entity under cursor
        target = None
        for item in self.items(event.scenePos()):
            source = item.data(_ROLE_SOURCE)
            if source is not None:
                target = item
                break
            if isinstance(item, (ElevDatumItem, ElevGridlineItem)):
                target = item
                break

        if target is not None and not target.isSelected():
            self.clearSelection()
            target.setSelected(True)

        selected = self.selectedItems()
        source_entity = target.data(_ROLE_SOURCE) if target else None

        menu = build_entity_context_menu(
            selected,
            target,
            scene=self._ms,
            on_hide=lambda: self._hide_elev_items(
                [target] + [i for i in selected if i is not target]
            ),
            on_show_all=lambda: self._show_all_elev_hidden(),
            on_delete=lambda: self._delete_elev_selected(),
            on_properties=lambda: (
                self.entitySelected.emit(source_entity) if source_entity else None
            ),
            on_refresh=lambda: self.rebuild(),
        )
        menu.exec(event.screenPos())

    def _hide_elev_items(self, items):
        """Hide elevation items and their source entities."""
        for item in items:
            source = item.data(_ROLE_SOURCE) if item else None
            if source is not None and hasattr(source, "_display_overrides"):
                source._display_overrides["visible"] = False
            item.setVisible(False)

    def _show_all_elev_hidden(self):
        """Restore all hidden source entities and rebuild."""
        self._ms._show_all_hidden()
        self.rebuild()

    def _delete_elev_selected(self):
        """Delete source entities for selected elevation items."""
        for item in list(self.selectedItems()):
            source = item.data(_ROLE_SOURCE) if item else None
            if source is not None and hasattr(source, "setSelected"):
                source.setSelected(True)
        self._ms.delete_selected_items()
        self.rebuild()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def direction(self) -> str:
        return self._direction

    @property
    def marker(self):
        return self._marker

    @property
    def basis(self):
        return self._basis

    @property
    def _gridline_z_overrides(self) -> dict:
        return self._marker.gridline_z_overrides

    @property
    def show_datums(self) -> bool:
        return self._show_datums

    @show_datums.setter
    def show_datums(self, val: bool):
        self._show_datums = val
        self.rebuild()

    # ── Coordinate projection ────────────────────────────────────────────

    def _ppm(self) -> float:
        """Pixels-per-mm (calibration factor), default 1.0."""
        return self._sm.pixels_per_mm if self._sm.is_calibrated else 1.0

    def _scene_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert legacy scene coords (pixels) to world mm with Y flip."""
        ppm = self._ppm()
        return sx / ppm, -sy / ppm

    def _refresh_basis(self):
        """Rebuild the oblique basis from the marker's current geometry."""
        a = self._scene_to_world(self._marker.cut_a.x(), self._marker.cut_a.y())
        b = self._scene_to_world(self._marker.cut_b.x(), self._marker.cut_b.y())
        self._basis = SectionBasis.from_cut(a, b, self._marker.look_sign,
                                            self._marker.depth / self._ppm())

    def zone_of(self, source) -> str:
        """Zone the last rebuild assigned to *source* (cut / behind / hidden).

        Keyed by ``id(source)``; valid only within one rebuild."""
        return self._zones.get(id(source), ZONE_HIDDEN)

    def _wall_zone(self, wall) -> str:
        """Zone of *wall*: the one _project_walls recorded, else classified
        from its footprint (walls the wall pass skipped -- Display Manager
        hidden, zero height -- still carry their openings, as before)."""
        zone = self._zones.get(id(wall))
        if zone is not None:
            return zone
        try:
            quad = wall.mitered_quad()
        except Exception:
            quad = wall.quad_points()
        pts = [self._scene_to_world(p.x(), p.y()) for p in quad]
        zone = self._basis.classify_polygon(pts)[0]
        self._zones[id(wall)] = zone
        return zone

    def _clip_h(self, h_min: float, h_max: float):
        """Lateral clip to the crop box; None when nothing remains (s4.2)."""
        lo, hi = max(h_min, self._basis.h_min), min(h_max, self._basis.h_max)
        return (lo, hi) if hi - lo >= 0.5 else None

    def _project(self, wx: float, wy: float, wz: float) -> tuple[float, float]:
        """Project world (mm) coords onto the section 2D plane.

        Returns (h, v) where h is the horizontal scene coord along the cut
        line and v = -wz (Qt Y increases downward, Z increases upward).
        """
        return self._basis.project(wx, wy, wz)

    def _level_z(self, level_name: str) -> float:
        lvl = self._lm.get(level_name)
        return lvl.elevation if lvl else 0.0

    # ── Rebuild ──────────────────────────────────────────────────────────

    def _schedule_rebuild(self):
        if not self._rebuild_timer.isActive():
            self._rebuild_timer.start()

    def _apply_theme_colours(self):
        """Canvas background + edge/line colour from the current theme."""
        bg = QColor(th.detect().canvas_bg)
        self.setBackgroundBrush(QBrush(bg))
        # Legacy canvas readout only (the HF1 guard reads it): edges now paint
        # TOKEN_AUTO, resolved per paint, so this never reaches a sheet plot.
        br = bg.redF() * 0.299 + bg.greenF() * 0.587 + bg.blueF() * 0.114
        self._edge_color = QColor("#d0d0d0") if br < 0.5 else QColor("#000000")

    def rebuild(self):
        """Clear and re-project all entities from the model."""
        self._apply_theme_colours()
        self._marker.auto_fit(self._ms)           # geometry re-seeded (s4.3); basis below reads it
        self._refresh_basis()
        self._zones = {}
        self._cut_items = []
        self.clear()
        self._depth_items: list[tuple[float, list]] = []  # (depth, [items])
        self._project_level_datums()
        self._project_walls()
        self._project_openings()
        self._project_pipes()
        self._project_sprinklers()
        self._project_floor_slabs()
        self._project_roofs()
        self._project_gridlines()
        self._render_cut_items()
        self._project_geometry_2d()
        self._assign_depth_z_values()

    def _register_depth_item(self, depth: float, *items):
        """Register scene items at a given depth for unified Z assignment."""
        self._depth_items.append((depth, list(items)))

    def _assign_depth_z_values(self):
        """Sort all depth-registered items farthest-first and assign Z-values.

        Items at the same depth are drawn in registration order.
        Farther items get lower Z (drawn first / behind).
        """
        self._depth_items.sort(key=lambda x: x[0])
        z = -50.0
        for depth, items in self._depth_items:
            for item in items:
                item.setZValue(z)
                z += 0.01
        self._depth_items = []

    # ── Foreground (datum lines) ─────────────────────────────────────────

    def drawForeground(self, painter, rect):
        """Draw datum lines from the bubble to h_max (gridline extent).

        Drawn in foreground so lines remain visible even when the bubble
        has scrolled out of the viewport.
        """
        super().drawForeground(painter, rect)
        for item in self.items():
            if not isinstance(item, ElevDatumItem):
                continue
            if not item.isVisible():
                continue
            v = item._v
            h_start = item._bx + item._bubble_r
            h_end = item._h_max
            if h_end <= h_start:
                continue

            datum_color = (item._datum_color if item._color_src is None
                           else resolve_colour(item._color_src, item=item))
            pen = QPen(datum_color, item._pen_w, Qt.PenStyle.DashDotLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(h_start, v), QPointF(h_end, v))

            if item.isSelected():
                sel_pen = QPen(datum_color.lighter(150),
                               item._pen_w * 2, Qt.PenStyle.DashDotLine)
                painter.setPen(sel_pen)
                painter.drawLine(QPointF(h_start, v), QPointF(h_end, v))

    # ── Walls ────────────────────────────────────────────────────────────

    def _project_walls(self):
        props = self._wall_display_props()
        if not props["visible"]:
            return
        dm_color = props["color"]       # stored strings: resolved per paint
        dm_fill = props["fill"]
        dm_opacity = props["opacity"] / 100.0
        has_explicit_fill = props.get("has_explicit_fill", False)

        ppm = self._ppm()

        # Collect all wall rects with their depth for sorting
        wall_rects: list[tuple[float, QGraphicsRectItem]] = []

        for wall in getattr(self._ms, "_walls", []):
            # Get Z extents
            base_z = 0.0
            top_z = wall._height_mm
            base_lvl = self._lm.get(wall._base_level)
            if base_lvl:
                base_z = base_lvl.elevation + wall._base_offset_mm
            top_lvl = self._lm.get(wall._top_level)
            if top_lvl:
                top_z = top_lvl.elevation + wall._top_offset_mm
            else:
                top_z = base_z + wall._height_mm
            if abs(top_z - base_z) < 1.0:
                continue

            # Get mitered 2D quad corners, convert to world mm
            try:
                p1l, p1r, p2r, p2l = wall.mitered_quad()
            except Exception:
                p1l, p1r, p2r, p2l = wall.quad_points()

            corners_world = []
            for pt in (p1l, p1r, p2r, p2l):
                wx, wy = self._scene_to_world(pt.x(), pt.y())
                corners_world.append((wx, wy))

            zone, h_lo, h_hi = self._basis.classify_polygon(corners_world)
            self._zones[id(wall)] = zone
            if zone == ZONE_HIDDEN:
                continue
            if zone == ZONE_CUT:
                self._cut_items.append(("wall", wall, (h_lo, h_hi, base_z, top_z)))
                continue

            # Project to elevation H axis
            h_values = [self._project(wx, wy, 0)[0]
                        for wx, wy in corners_world]
            h_min = min(h_values)
            h_max = max(h_values)
            clipped = self._clip_h(h_min, h_max)
            if clipped is None:
                continue
            h_min, h_max = clipped
            width = h_max - h_min
            if width < 0.5:
                continue

            # Compute depth (distance from camera along view direction)
            # for sorting: closer walls should be drawn on top (higher Z)
            all_wx = [c[0] for c in corners_world]
            all_wy = [c[1] for c in corners_world]
            centroid_x = sum(all_wx) / len(all_wx)
            centroid_y = sum(all_wy) / len(all_wy)
            depth = self._basis.sort_key(centroid_x, centroid_y)

            # Elevation scene rect: (h_min, -top_z) to (h_max, -base_z)
            v_top = -top_z      # Qt Y for top of wall
            v_bottom = -base_z  # Qt Y for bottom of wall
            height = v_bottom - v_top

            rect = _ElevProxyRect(h_min, v_top, width, height)

            # Use display manager colour; fall back to wall's own colour.
            # Sources, not QColors: a sheet viewport resolves them on paper.
            pen = QPen(QColor(0, 0, 0), 1)
            pen.setCosmetic(True)
            rect.setPen(pen)
            fill_src, fill_alpha = dm_fill, None
            if not has_explicit_fill and hasattr(wall, "_colour"):
                # Opaque (the outline is opaque already); "" resolves fully
                # transparent whatever the alpha.
                fill_src, fill_alpha = wall._colour, 255
            rect.set_colour_src(pen=dm_color, brush=fill_src, alpha=fill_alpha)
            rect.setOpacity(dm_opacity)

            rect.setData(_ROLE_SOURCE, wall)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            wall_rects.append((depth, rect))

        for depth, rect in wall_rects:
            self.addItem(rect)
            self._register_depth_item(depth, rect)

    # ── Openings ─────────────────────────────────────────────────────────

    def _project_openings(self):
        """Project wall openings (doors, windows, blanks) into elevation (§7.8.2).

        For each opening on a visible wall:
        - Computes the opening's H extent (along-wall) by projecting the two
          along-wall edge points through the same coordinate path as _project_walls.
        - Computes the V extent from the level elevation + sill/head heights.
        - Draws a void rect (white fill) to interrupt the wall poché, then adds
          type-specific frame/sill schematic lines.
        - Tags the primary void rect with ``_ROLE_SOURCE = opening`` so elevation
          views can round-trip source references.
        """
        import math as _math

        # Edges / voids are colour *sources* (TOKEN_AUTO / TOKEN_BG) resolved per
        # paint, so a sheet viewport plots them black / white on paper (600).
        frame_pen = QPen(self._edge_color, 1)
        frame_pen.setCosmetic(True)

        for wall in getattr(self._ms, "_walls", []):
            if not getattr(wall, "openings", None):
                continue
            # Task 5 renders head / sill for cut walls; until then only
            # walls behind the cut carry their openings.
            if self._wall_zone(wall) != ZONE_BEHIND:
                continue

            for op in wall.openings:
                # ── Along-wall endpoints in scene coords ──────────────────
                a = wall.centerline_angle_rad()
                half_w = op.width_scene() / 2.0
                base = wall.centerline_pt1
                cx_scene = base.x() + op._offset_along * _math.cos(a)
                cy_scene = base.y() + op._offset_along * _math.sin(a)
                dx = half_w * _math.cos(a)
                dy = half_w * _math.sin(a)
                p_left = (cx_scene - dx, cy_scene - dy)
                p_right = (cx_scene + dx, cy_scene + dy)

                # ── Convert to world mm then to elevation H ───────────────
                wl_x, wl_y = self._scene_to_world(*p_left)
                wr_x, wr_y = self._scene_to_world(*p_right)
                h_left = self._project(wl_x, wl_y, 0)[0]
                h_right = self._project(wr_x, wr_y, 0)[0]
                h_min = min(h_left, h_right)
                h_max = max(h_left, h_right)
                clipped = self._clip_h(h_min, h_max)
                if clipped is None:
                    continue
                h_min, h_max = clipped
                width = h_max - h_min
                if width < 0.5:
                    continue

                # ── Vertical extent ───────────────────────────────────────
                lvl_name = getattr(op, "level", None) or getattr(wall, "_base_level", None)
                lvl = self._lm.get(lvl_name) if lvl_name else None
                if lvl is None:
                    lvl_elev = 0.0
                else:
                    lvl_elev = lvl.elevation
                bot_z = lvl_elev + op._sill_mm
                top_z = bot_z + op._height_mm
                if abs(top_z - bot_z) < 1.0:
                    continue
                v_top = -top_z
                v_bottom = -bot_z

                # ── Depth (same convention as _project_walls) ─────────────
                wc_x = (wl_x + wr_x) / 2.0
                wc_y = (wl_y + wr_y) / 2.0
                depth = self._basis.sort_key(wc_x, wc_y)

                # ── Void rect (interrupts wall poché) ─────────────────────
                void_rect = _ElevProxyRect(h_min, v_top, width, v_bottom - v_top)
                void_pen = QPen(Qt.PenStyle.NoPen)
                void_rect.setPen(void_pen)
                void_rect.set_colour_src(brush=TOKEN_BG)
                void_rect.setData(_ROLE_SOURCE, op)
                void_rect.setFlag(
                    QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)

                # ── Frame rect (outline of the opening) ───────────────────
                frame_rect = _SrcRect(h_min, v_top, width, v_bottom - v_top)
                frame_rect.setPen(frame_pen)
                frame_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                frame_rect.set_colour_src(pen=TOKEN_AUTO)

                items_to_add = [void_rect, frame_rect]

                op_type = getattr(op, "_type", "blank")

                if op_type == "window":
                    # Horizontal sill line at bottom of opening
                    sill_line = _SrcLine(h_min, v_bottom, h_max, v_bottom)
                    sill_line.setPen(frame_pen)
                    sill_line.set_colour_src(pen=TOKEN_AUTO)
                    items_to_add.append(sill_line)

                elif op_type == "door":
                    # Centre vertical line for double-leaf doors
                    if getattr(op, "_leaves", 1) == 2:
                        h_mid = (h_min + h_max) / 2.0
                        mid_line = _SrcLine(h_mid, v_top, h_mid, v_bottom)
                        mid_line.setPen(frame_pen)
                        mid_line.set_colour_src(pen=TOKEN_AUTO)
                        items_to_add.append(mid_line)

                # blank: void + frame only — no extra lines

                for item in items_to_add:
                    self.addItem(item)
                self._register_depth_item(depth, *items_to_add)

    # ── Pipes ────────────────────────────────────────────────────────────

    def _project_pipes(self):
        from .constants import PIPE_COLORS as _PIPE_COLORS
        pipe_items: list[tuple[float, QGraphicsLineItem]] = []

        for pipe in self._ms.sprinkler_system.pipes:
            n1, n2 = pipe.node1, pipe.node2
            if n1 is None or n2 is None:
                continue
            # Get world positions
            wx1, wy1 = self._scene_to_world(n1.scenePos().x(), n1.scenePos().y())
            wx2, wy2 = self._scene_to_world(n2.scenePos().x(), n2.scenePos().y())
            z1 = getattr(n1, "z_pos", 0.0)
            z2 = getattr(n2, "z_pos", 0.0)

            zone, h_cut, t_cut = self._basis.classify_segment((wx1, wy1), (wx2, wy2))
            self._zones[id(pipe)] = zone
            if zone == ZONE_HIDDEN:
                continue
            if zone == ZONE_CUT:
                self._cut_items.append(("pipe", pipe, (h_cut, z1 + t_cut * (z2 - z1))))
                continue

            h1, v1 = self._project(wx1, wy1, z1)
            h2, v2 = self._project(wx2, wy2, z2)

            # Lateral clip to the crop box, by parameter (either orientation).
            lo, hi = self._basis.h_min, self._basis.h_max
            if abs(h2 - h1) > 1e-9:
                ta = (lo - h1) / (h2 - h1)
                tb = (hi - h1) / (h2 - h1)
                t0, t1 = max(0.0, min(ta, tb)), min(1.0, max(ta, tb))
                if t0 < t1:
                    h1, v1, h2, v2 = (h1 + t0 * (h2 - h1), v1 + t0 * (v2 - v1),
                                      h1 + t1 * (h2 - h1), v1 + t1 * (v2 - v1))

            col_name = pipe._properties.get("Colour", {}).get("value", "Red")
            color = QColor(_PIPE_COLORS.get(col_name, "#e62828"))

            line = _ElevProxyLine(h1, v1, h2, v2)
            pen = QPen(color, 2)
            pen.setCosmetic(True)
            line.setPen(pen)
            line.setData(_ROLE_SOURCE, pipe)
            line.setFlag(QGraphicsLineItem.GraphicsItemFlag.ItemIsSelectable, True)

            # Depth for sorting
            cx = (wx1 + wx2) / 2
            cy = (wy1 + wy2) / 2
            depth = self._basis.sort_key(cx, cy)
            pipe_items.append((depth, line))

        for depth, line in pipe_items:
            self.addItem(line)
            self._register_depth_item(depth, line)

    # ── Sprinklers ───────────────────────────────────────────────────────

    def _project_sprinklers(self):
        spr_items: list[tuple[float, QGraphicsEllipseItem]] = []

        for node in self._ms.sprinkler_system.nodes:
            if not node.has_sprinkler():
                continue
            wx, wy = self._scene_to_world(node.scenePos().x(), node.scenePos().y())
            self._zones[id(node)] = self._basis.classify_point((wx, wy))
            if self._zones[id(node)] == ZONE_HIDDEN:
                continue
            z = getattr(node, "z_pos", 0.0)
            h, v = self._project(wx, wy, z)

            orient = node.sprinkler._properties.get(
                "Orientation", {}).get("value", "Upright")
            if orient == "Pendent":
                color = QColor("#ff3232")
            elif orient == "Sidewall":
                color = QColor("#32c832")
            else:
                color = QColor("#3264ff")

            r = 30.0  # mm radius
            ellipse = _ElevProxyEllipse(h - r, v - r, r * 2, r * 2)
            pen = QPen(color, 1.5)
            pen.setCosmetic(True)
            ellipse.setPen(pen)
            ellipse.setBrush(QBrush())
            ellipse.setData(_ROLE_SOURCE, node)
            ellipse.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)

            depth = self._basis.sort_key(wx, wy)
            spr_items.append((depth, ellipse))

        for depth, ellipse in spr_items:
            self.addItem(ellipse)
            self._register_depth_item(depth, ellipse)

    # ── Floor slabs ──────────────────────────────────────────────────────

    def _project_floor_slabs(self):
        props = self._floor_display_props()
        if not props["visible"]:
            return
        dm_color = props["color"]       # stored strings: resolved per paint
        dm_fill = props["fill"]
        dm_opacity = props["opacity"] / 100.0

        # Each entry: (depth, mask_rect, visible_rect)
        slab_rects: list[tuple[float, QGraphicsRectItem, QGraphicsRectItem]] = []

        for slab in getattr(self._ms, "_floor_slabs", []):
            # Resolve the slab's true world-Z from the two-boundary model.
            # Use this scene's own LevelManager explicitly: the slab lives in
            # the model scene (self._ms), not in this elevation scene, so
            # slab.z_range_mm() (which resolves via slab.scene()._level_manager)
            # is not guaranteed to reach the LM this view was built with.
            zr = slab._z_range_with_lm(self._lm)
            if zr is None:
                continue  # unresolvable (missing level etc.) — skip, degenerate-safe
            bot_z, top_z = zr

            pts = getattr(slab, "_points", [])
            if not pts:
                continue
            h_vals = []
            world_pts = []
            for pt in pts:
                wx, wy = self._scene_to_world(pt.x(), pt.y())
                world_pts.append((wx, wy))
                h, _ = self._project(wx, wy, 0)
                h_vals.append(h)
            h_min, h_max = min(h_vals), max(h_vals)

            zone, h_lo, h_hi = self._basis.classify_polygon(world_pts)
            self._zones[id(slab)] = zone
            if zone == ZONE_HIDDEN:
                continue
            if zone == ZONE_CUT:
                self._cut_items.append(("slab", slab, (h_lo, h_hi, bot_z, top_z)))
                continue
            clipped = self._clip_h(h_min, h_max)
            if clipped is None:
                continue
            h_min, h_max = clipped

            # Compute depth (same convention as walls)
            cx = sum(w[0] for w in world_pts) / len(world_pts)
            cy = sum(w[1] for w in world_pts) / len(world_pts)
            depth = self._basis.sort_key(cx, cy)

            # Elevation view is Y-down: higher world-Z projects to a more
            # negative v-coordinate, so negate both boundaries.
            v_top = -top_z
            v_bottom = -bot_z
            width = h_max - h_min
            height = v_bottom - v_top

            # Opaque mask rect — hides items behind the slab
            mask = _SrcRect(h_min, v_top, width, height)
            mask.setPen(QPen(Qt.PenStyle.NoPen))
            mask.set_colour_src(brush=TOKEN_BG)       # canvas bg on canvas, white on paper
            mask.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, False)

            # Visible slab rect with styled fill
            rect = _ElevProxyRect(h_min, v_top, width, height)
            pen = QPen(QColor(0, 0, 0), 1)
            pen.setCosmetic(True)
            rect.setPen(pen)
            rect.set_colour_src(pen=dm_color, brush=dm_fill)
            rect.setOpacity(dm_opacity)
            rect.setData(_ROLE_SOURCE, slab)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            slab_rects.append((depth, mask, rect))

        for depth, mask, rect in slab_rects:
            self.addItem(mask)
            self.addItem(rect)
            # Register mask + visible rect at the same depth as walls;
            # the unified sorter places them at the correct Z relative
            # to walls at the same depth (mask first, then visible rect).
            self._register_depth_item(depth, mask, rect)

    # ── Roofs ────────────────────────────────────────────────────────────

    def _project_roofs(self):
        props = self._roof_display_props()
        if not props["visible"]:
            return
        dm_color = props["color"]       # stored strings: resolved per paint
        dm_fill = props["fill"]
        dm_opacity = props["opacity"] / 100.0

        for roof in getattr(self._ms, "_roofs", []):
            mesh_data = None
            try:
                mesh_data = roof.get_3d_mesh(level_manager=self._lm)
            except Exception:
                pass
            if mesh_data is None:
                continue

            verts = mesh_data.get("vertices", [])
            if not verts:
                continue
            col = mesh_data.get("color", (0.8, 0.7, 0.5, 0.5))

            # Project all vertices and draw outline polygon
            elev_pts = []
            for vx, vy, vz in verts:
                h, v = self._project(vx, vy, vz)
                elev_pts.append(QPointF(h, v))

            if not elev_pts:
                continue

            # Roofs are never cut-rendered in v1 (s5): classify only to drop
            # hidden roofs and clip laterally.
            zone = self._basis.classify_polygon(
                [(vx, vy) for vx, vy, vz in verts])[0]
            self._zones[id(roof)] = zone
            if zone == ZONE_HIDDEN:
                continue

            # Draw convex hull outline (simplified)
            h_vals = [p.x() for p in elev_pts]
            v_vals = [p.y() for p in elev_pts]
            clipped = self._clip_h(min(h_vals), max(h_vals))
            if clipped is None:
                continue
            rect = _ElevProxyRect(
                clipped[0], min(v_vals),
                clipped[1] - clipped[0], max(v_vals) - min(v_vals),
            )
            pen = QPen(QColor(0, 0, 0), 1)
            pen.setCosmetic(True)
            rect.setPen(pen)
            rect.set_colour_src(pen=dm_color, brush=dm_fill)
            rect.setOpacity(dm_opacity)
            rect.setData(_ROLE_SOURCE, roof)
            rect.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            rect.setZValue(-70)
            self.addItem(rect)

    # ── Cut items (spec s5) ──────────────────────────────────────────────

    def _render_cut_items(self):
        """Draw every footprint the classification put AT the cut (s5)."""
        from .constants import PIPE_COLORS as _PIPE_COLORS
        wall_props = self._wall_display_props()
        floor_props = self._floor_display_props()
        pipe_sec = self._pipe_display_props()["section"]
        pen_black = QPen(QColor(0, 0, 0), 1)
        pen_black.setCosmetic(True)
        for kind, src, data in self._cut_items:
            if kind in ("wall", "slab"):
                props = wall_props if kind == "wall" else floor_props
                h_lo, h_hi, z_bot, z_top = data
                spans = (self._wall_cut_spans(src, z_bot, z_top) if kind == "wall"
                         else [(z_bot, z_top)])
                for z0, z1 in spans:
                    if z1 - z0 < 1.0 or h_hi - h_lo < 0.5:
                        continue
                    rect = _ElevCutRect(h_lo, -z1, h_hi - h_lo, z1 - z0)
                    rect.setPen(pen_black)
                    rect.set_colour_src(pen=props["color"])
                    rect.set_section(props["section"], props["section_pattern"], self._ms)
                    rect.setOpacity(props["opacity"] / 100.0)
                    rect.setData(_ROLE_SOURCE, src)
                    rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                    self.addItem(rect)
                    self._register_depth_item(0.0, rect)
            elif kind == "pipe":
                h, z = data
                od = src.display_width_mm() * getattr(src, "_display_scale", 1.0)
                col_name = src._properties.get("Colour", {}).get("value", "Red")
                own = _PIPE_COLORS.get(col_name, "#e62828")
                circ = _ElevCutEllipse(h - od / 2.0, -z - od / 2.0, od, od)
                pen = QPen(QColor(own), 1)
                pen.setCosmetic(True)
                circ.setPen(pen)
                circ.set_colour_src(pen=own, brush=pipe_sec or own)
                circ.setData(_ROLE_SOURCE, src)
                circ.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                self.addItem(circ)
                self._register_depth_item(0.0, circ)

    def _wall_cut_spans(self, wall, base_z: float, top_z: float) -> list[tuple[float, float]]:
        """Vertical spans of the cut face: the whole wall, or -- when the
        crossing falls inside an opening -- below the sill (windows) and above
        the head (s5). Scene coords for the along-wall test."""
        import math as _math
        a = wall.centerline_angle_rad()
        p1 = wall.centerline_pt1
        ux, uy = _math.cos(a), _math.sin(a)
        ma, mb = self._marker.cut_a, self._marker.cut_b
        cx, cy = mb.x() - ma.x(), mb.y() - ma.y()
        den = ux * cy - uy * cx
        if abs(den) < 1e-9:
            return [(base_z, top_z)]                       # collinear: no opening carve
        t = ((ma.x() - p1.x()) * cy - (ma.y() - p1.y()) * cx) / den   # along-wall offset
        for op in getattr(wall, "openings", None) or []:
            half = op.width_scene() / 2.0
            if not (op._offset_along - half <= t <= op._offset_along + half):
                continue
            op_lvl = getattr(op, "level", None) or getattr(wall, "_base_level", None)
            z0 = (self._level_z(op_lvl) if op_lvl else 0.0) + op._sill_mm
            z1 = z0 + op._height_mm
            spans = []
            if getattr(op, "_type", "blank") == "window" and z0 > base_z:
                spans.append((base_z, min(z0, top_z)))
            if z1 < top_z:
                spans.append((max(z1, base_z), top_z))
            return spans
        return [(base_z, top_z)]

    # ── Display manager helpers ──────────────────────────────────────────

    def _wall_display_props(self) -> dict:
        """Read Wall display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Wall/color",   "#666666"),
            "fill":    s.value("display/Wall/fill",    "#999999"),
            "opacity": int(float(s.value("display/Wall/opacity", 100))),
            "visible": str(s.value("display/Wall/visible", "true")).lower() not in ("false", "0"),
            "has_explicit_fill": s.contains("display/Wall/fill"),
            "section": s.value("display/Wall/section", "#666666"),
            "section_pattern": s.value("display/Wall/section_pattern", "diagonal"),
        }

    def _roof_display_props(self) -> dict:
        """Read Roof display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Roof/color",   "#8B4513"),
            "fill":    s.value("display/Roof/fill",    "#D2B48C"),
            "opacity": int(float(s.value("display/Roof/opacity", 100))),
            "visible": str(s.value("display/Roof/visible", "true")).lower() not in ("false", "0"),
        }

    def _floor_display_props(self) -> dict:
        """Read Floor display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Floor/color",   "#8888cc"),
            "fill":    s.value("display/Floor/fill",    "#8888cc"),
            "opacity": int(float(s.value("display/Floor/opacity", 100))),
            "visible": str(s.value("display/Floor/visible", "true")).lower() not in ("false", "0"),
            "section": s.value("display/Floor/section", "#666666"),
            "section_pattern": s.value("display/Floor/section_pattern", "diagonal"),
        }

    def _pipe_display_props(self) -> dict:
        """Read the Pipe Section colour (None in the default row)."""
        s = QSettings("GV", "FirePro3D")
        return {"section": s.value("display/Pipe/section", None)}

    def _gridline_display_props(self) -> dict:
        """Read Grid Line display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Grid Line/color",   "#4488cc"),
            "fill":    s.value("display/Grid Line/fill",    "#1a1a2e"),
            "opacity": int(float(s.value("display/Grid Line/opacity", 100))),
            "visible": str(s.value("display/Grid Line/visible", "true")).lower() not in ("false", "0"),
            "scale":   float(s.value("display/Grid Line/scale", 1.0)),
        }

    def _datum_display_props(self) -> dict:
        """Read Level Datum display properties from QSettings (display manager)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Level Datum/color",   "#4488cc"),
            "fill":    s.value("display/Level Datum/fill",    "#1a1a2e"),
            "opacity": int(float(s.value("display/Level Datum/opacity", 100))),
            "visible": str(s.value("display/Level Datum/visible", "true")).lower() not in ("false", "0"),
            "scale":   float(s.value("display/Level Datum/scale", 1.0)),
            "font":    int(float(s.value("display/Level Datum/font", 10))),
        }

    # ── Gridlines ────────────────────────────────────────────────────────

    def _project_gridlines(self):
        props = self._gridline_display_props()
        if not props["visible"]:
            return

        grid_src, fill_src = props["color"], props["fill"]   # resolved per paint
        grid_color = resolve_colour(grid_src)
        fill_color = resolve_colour(fill_src)
        opacity = props["opacity"] / 100.0
        bubble_scale = props["scale"]
        BUBBLE_R = 203.2 * bubble_scale  # 8" in mm, scaled
        gl_pen_w = max(1.0, BUBBLE_R * 0.04)

        for gl in getattr(self._ms, "_gridlines", []):
            line_geom = gl.line()

            # A gridline shows where its infinite line crosses the cut line
            # inside the crop box (872, D7a); parallel / outside = absent.
            wx1, wy1 = self._scene_to_world(line_geom.x1(), line_geom.y1())
            wx2, wy2 = self._scene_to_world(line_geom.x2(), line_geom.y2())
            h_avg = self._gridline_crossing_h((wx1, wy1), (wx2, wy2))
            if h_avg is None:
                continue

            levels = self._lm.levels
            if not levels:
                continue
            z_min = min(l.elevation for l in levels) - 1000
            z_max = max(l.elevation for l in levels) + 4000

            label_text = getattr(gl, "_label_text", "")
            v_top = -z_max - BUBBLE_R - 50
            v_bot = -z_min + BUBBLE_R + 50

            # Apply per-view override if the user has grip-dragged this gridline
            if label_text in self._gridline_z_overrides:
                ov = self._gridline_z_overrides[label_text]
                v_top = ov.get("v_top", v_top)
                v_bot = ov.get("v_bot", v_bot)

            item = ElevGridlineItem(
                h_avg, v_top, v_bot, label_text, BUBBLE_R,
                grid_color, fill_color, gl_pen_w, opacity,
                color_src=grid_src, fill_src=fill_src)
            self.addItem(item)

    # ── Construction geometry ────────────────────────────────────────────

    def _project_geometry_2d(self):
        # Loose 2D primitives are Block-definition-local and level-less
        # (containment C1/C3) — they no longer live in the plan scene, so there
        # is nothing to project into elevation. Block-instance elevation
        # projection is a deferred Feature-representation concern (grill fork B).
        return

    # ── Level datums ─────────────────────────────────────────────────────

    def _datum_extent(self) -> tuple[float, float]:
        """H range of the datum lines = the crop box (s5)."""
        return self._basis.h_min, self._basis.h_max

    def _gridline_crossing_h(self, p, q):
        """h of the crossing of the INFINITE gridline p->q with the cut line,
        or None when parallel or outside [h_min, h_max] (872, D7a)."""
        b = self._basis
        d1, d2 = b.d(*p), b.d(*q)
        if abs(d2 - d1) < 1e-9:
            return None                                   # parallel to the cut
        t = d1 / (d1 - d2)                                # unbounded: any t
        h = b.h(p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))
        if not (b.h_min - 1e-9 <= h <= b.h_max + 1e-9):
            return None
        return h

    def _project_level_datums(self):
        if not self._show_datums:
            return

        # Use Level Datum display properties from display manager
        props = self._datum_display_props()
        if not props.get("visible", True):
            return
        datum_src = props["color"]                      # resolved per paint
        fill_src = props.get("fill", "#1a1a2e")
        datum_color = resolve_colour(datum_src)
        fill_color = resolve_colour(fill_src)
        opacity = props["opacity"] / 100.0
        scale = props.get("scale", 1.0)

        h_min, h_max = self._datum_extent()

        # Datum line pen — dash-dot-dash, weight matched to gridline
        from .gridline import BUBBLE_RADIUS_MM
        grid_props = self._gridline_display_props()
        grid_scale = grid_props.get("scale", 1.0)
        pen_w = max(1.0, BUBBLE_RADIUS_MM * 0.04 * grid_scale)

        # Text size: base 175mm, scaled by display manager font size (pt)
        font_pt = props.get("font", 10)
        text_height = 175.0 * scale * (font_pt / 10.0)
        name_font = QFont("Consolas")
        name_font.setPixelSize(max(1, int(text_height)))
        name_font.setBold(True)

        elev_font = QFont("Consolas")
        elev_font.setPixelSize(max(1, int(text_height * 0.8)))

        # Bubble radius matches gridline bubbles
        bubble_r = BUBBLE_RADIUS_MM * scale

        for lvl in self._lm.levels:
            z = lvl.elevation
            v = -z  # Qt Y

            elev_str = self._sm.format_length(z) if self._sm else f"{z:.0f} mm"

            item = ElevDatumItem(
                v, h_min, h_max,
                lvl.name, elev_str,
                bubble_r, datum_color, fill_color,
                pen_w, name_font, elev_font,
                scale, opacity, color_src=datum_src, fill_src=fill_src)
            self.addItem(item)

    # ── Selection ────────────────────────────────────────────────────────
    # Selection is handled by Qt's built-in rubber-band + ItemIsSelectable
    # flags, routed through _on_selection_changed() which emits entitySelected.
