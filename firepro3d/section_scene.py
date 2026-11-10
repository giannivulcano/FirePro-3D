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
    QGraphicsEllipseItem,
    QGraphicsItem, QStyle,
)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QPointF, QLineF, QTimer
from PyQt6.QtGui import (
    QPen, QColor, QBrush, QPainterPath,
    QPainterPathStroker, QPainter,
)

from PyQt6.QtCore import QSettings

from .constants import (DEFAULT_LEVEL, TOKEN_AUTO, TOKEN_BG,
                        ELEV_GRIDLINE_END_PAD_MM, ELEV_GRIDLINE_PEN_W_MM,
                        Z_DEPTH_CEIL, Z_ANNOT_GRID, Z_ANNOT_TAG,
                        RISER_SYMBOL_SIZE_MM)
from . import theme as th
from .paper_display import paper_pass_active, shows_selection
from .colour_tokens import resolve_colour, resolve_pen_brush, section_fill_colour
from .block_instance import BlockInstance
from .block_pose import reflect_pose
from . import materials
from .displayable_item import draw_section_type
from .halo_selection import HaloSelectionMixin
from .bound_label import BoundLabelItem, OutlinedLabel
from .cad_math import CAD_Math
from .section_marker import SectionBasis, ZONE_CUT, ZONE_BEHIND, ZONE_HIDDEN
from .section_pipe_symbols import (cut_symbol_path, end_on_path, kept_spans,
                                   radius_of)

if TYPE_CHECKING:
    from .model_space import Model_Space
    from .level_manager import LevelManager
    from .scale_manager import ScaleManager

# Data role for storing source entity reference on projected items
_ROLE_SOURCE = Qt.ItemDataRole.UserRole

# Marker role so elevation views can filter these from Ctrl+A
_ROLE_ELEV_ANNOTATION = Qt.ItemDataRole.UserRole + 1

# Footer status when a section placement finds no host gridline (hosted-blocks G9).
HOSTED_REFUSAL = ("Can't place here — a block in a section needs a "
                  "gridline parallel to the cut inside the view's depth.")

# Depth walk (_assign_depth_z_values): farthest item first from _DEPTH_Z_START
# in _DEPTH_Z_STEP steps, clamped at constants.Z_DEPTH_CEIL so projected model
# items never reach the annotation band (SB4d D5 / Q17).
_DEPTH_Z_START = -50.0
_DEPTH_Z_STEP = 0.01
# Hosted section copies sit in the tag band, near over far (SB4d D5): 100,000
# copies fit below Z_ANNOT_GRID.
_HOSTED_Z_STEP = 0.001


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
    _paper_cat = None           # paper category of a projected proxy (AC2), e.g. "Wall"
    _paper_pen_width = None     # paper pass: pen width in scene units, non-cosmetic
    _always_draw_shape = False  # a stock paint would ignore the item's _draw_shape

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
        w = self._paper_pen_width
        if w is not None and pen.style() != Qt.PenStyle.NoPen:
            pen = QPen(pen)
            pen.setWidthF(w)
            pen.setCosmetic(False)
        return pen, brush

    def _draw_shape(self, painter) -> None:
        raise NotImplementedError

    def paint(self, painter, option, widget=None):
        if paper_pass_active():     # selection never plots (wall polish D11, L42)
            option.state &= ~QStyle.StateFlag.State_Selected
        if (self._pen_src is None and self._brush_src is None
                and self._paper_pen_width is None and not self._always_draw_shape):
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
    SNAP_AS_RECT = True  # snap_engine._snaps_as_rect: the rectangle snap set (D3)


class _ElevProxyLine(_ElevReadOnlyProxyMixin, _SrcLine):
    """Read-only line proxy (pipes). Trimmed at the symbols in front of it:
    a symbol is hollow, so a pipe must stop at its edge (s5)."""

    _spans = None             # QLineF pieces left after the trim; None = whole
    pipe_label = None         # the section label this line owns (paper, Hide)

    def set_spans(self, spans) -> None:
        ln = self.line()
        self._spans = [QLineF(ln.pointAt(a), ln.pointAt(b)) for a, b in spans]
        self._always_draw_shape = True
        self.update()

    def _draw_shape(self, painter):
        if self._spans is None:
            super()._draw_shape(painter)
            return
        for piece in self._spans:
            painter.drawLine(piece)


class _ElevProxyEllipse(_ElevReadOnlyProxyMixin, _SrcEllipse):
    """Read-only ellipse proxy (sprinklers)."""

    HALO_AREA = True  # HALO: solid projection — cursor inside = direct hit


class _ElevCutRect(_ElevProxyRect):
    """A cut cross-section (wall / slab): the source element's material draws
    the body + hatch inside the rect (By element pattern = the outline
    colour), outline in the category Colour (s5; materials.md)."""

    _section_element = None  # the cut wall / slab; its material resolves at paint
    _section_src = None      # paper-pass body colour only ("" = no body); None in model
    _hatch_scene = None      # the SectionScene (paper override / block registry)

    def set_section(self, element, hatch_scene):
        self._section_element = element
        self._hatch_scene = hatch_scene

    def _draw_shape(self, painter):
        pen, _brush = self.resolved_pen_brush()
        path = QPainterPath()
        path.addRect(self.rect())
        draw_section_type(painter, path, self._hatch_scene, self,
                          materials.fill_type_of(self._section_element), pen.color(), 1.0,
                          paper_body=self._section_src)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect())


class _ElevPipeSymbol(_ElevProxyEllipse):
    """A pipe drawn as a symbol: stroked ink in the pipe colour, an optional
    body inside the circle. ``rect()`` is the symbol's plan-size box."""

    _ink = None               # QPainterPath of the stroked symbol

    def set_ink(self, path) -> None:
        self._ink = path

    def _draw_shape(self, painter):
        pen, _brush = self.resolved_pen_brush()
        body = section_fill_colour(self._brush_src, self)
        if body is not None:
            r = radius_of(self.rect().width())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(body)
            painter.drawEllipse(self.rect().center(), r, r)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._ink)


class _ElevCutEllipse(_ElevPipeSymbol):
    """A cut pipe: the plan riser symbol, Section colour inside the circle (s5)."""

    _no_sheet_body = True     # P6: a body in the row colour would hide the S


class _ElevEndOnSymbol(_ElevPipeSymbol):
    """An uncut pipe running toward the viewer: the "C" (s5)."""


class _ElevPipeLabel(BoundLabelItem):
    """A pipe's label in a section (R-8): the plan's block, host = the model
    pipe, top-level so it draws in the annotation band. Built per rebuild; the
    line proxy owns it for the paper pass and Hide."""


class _HostedBlockCopy(BlockInstance):
    """Section copy of a gridline-hosted model block (hosted-blocks D8).

    ``_ROLE_SOURCE`` names the model block; a drag lands on the model via
    :meth:`translate` (D10) and the section rebuilds from it.
    """

    def translate(self, dx: float, dy: float) -> None:
        sc = self.scene()
        move = getattr(sc, "_move_hosted_source", None) if sc is not None else None
        if move is not None:
            move(self, dx, dy)
        super().translate(dx, dy)          # live feedback until the rebuild


# ─────────────────────────────────────────────────────────────────────────────
# ElevGridlineItem — selectable gridline in elevation view
# ─────────────────────────────────────────────────────────────────────────────

class ElevGridlineItem(QGraphicsLineItem):
    """Interactive gridline in an elevation view — selectable with grip handles.

    Each end carries a ``GridlineBubble`` (SB4c D2) whose data host is the
    PLAN gridline *gridline*: it draws that gridline's resolved block
    (``tag_block`` -> project default, through ``SectionScene.annotation_block``)
    with the live ``@[Mark]``, annotative (k = the drawing scale on screen,
    1 / S on paper). ``bubble1`` (plan Bubble 1) sits at the top end
    (``line().p1()``, v_top), ``bubble2`` (plan Bubble 2) at the bottom.
    Per-end visibility and the duplicate flag are copied from the plan
    bubbles at build; a plan edit rebuilds the section through
    ``sceneModified`` (D6). The line trims at each visible bubble's block
    outline, on screen and paper. Overlay contract read by
    ``GridlineBubble.overlay_pens``: ``_paper_render``, ``_grid_color``,
    ``isSelected()``. *gridline* None = a detached item (unit tests): both
    bubbles resolve nothing and paint nothing.
    """

    def __init__(self, h_pos: float, v_top: float, v_bot: float,
                 label: str, color: QColor, pen_w: float,
                 opacity: float = 1.0, color_src: str | None = None,
                 *, gridline=None):
        super().__init__(h_pos, v_top, h_pos, v_bot)
        # Stored colour string (display-manager value): resolved per paint, so
        # a sheet viewport plots it on paper. ``color`` is its canvas
        # resolution, kept for readers, the selection ring and the no-source case.
        self._grid_src = color_src
        self._h = h_pos
        self._label = label  # gridline label used as override key
        self._gridline = gridline  # the plan GridlineItem: the bubbles' data host

        # Line pen — suppress default; drawn manually in paint()
        self.setPen(QPen(Qt.PenStyle.NoPen))

        self._grid_color = color
        self._pen_w = pen_w
        # Write-together unit: set by enter_paper_pass, cleared by exit_paper_pass.
        self._paper_render = False    # paper pass: overlay rings off (GridlineBubble contract)
        self._paper_line_w_mm = 0.0   # paper pass (AC3): ON-PAPER mm, dash normaliser
        self._paper_line_w = 0.0      # paper pass: line width, scene units

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(Z_ANNOT_GRID)   # annotation band: gridline sub-band (SB4d D5)
        self.setOpacity(opacity)
        self.setData(_ROLE_ELEV_ANNOTATION, True)

        # Bubbles: the plan gridline's annotation block, top and bottom (D2).
        from .gridline import GridlineBubble
        self.bubble1 = GridlineBubble(gridline, parent=self)   # top    = plan Bubble 1
        self.bubble2 = GridlineBubble(gridline, parent=self)   # bottom = plan Bubble 2
        if gridline is not None:
            # isVisibleTo: the plan end's own toggle, not the plan item's
            # display visibility (a plan-hidden gridline still shows here).
            self.bubble1.setVisible(gridline.bubble1.isVisibleTo(gridline))
            self.bubble2.setVisible(gridline.bubble2.isVisibleTo(gridline))
            self.bubble1.set_duplicate(gridline.bubble1._duplicate)
            self.bubble2.set_duplicate(gridline.bubble2._duplicate)
        self._update_bubble_positions()

    def _update_bubble_positions(self):
        line = self.line()
        self.bubble1.set_anchor(line.p1())
        self.bubble2.set_anchor(line.p2())
        self.prepareGeometryChange()   # the trimmed span + hit shape follow the bubbles

    # ── Drawing ──────────────────────────────────────────────────────────

    def boundingRect(self):
        """``QGraphicsLineItem.boundingRect`` derives from the virtual
        :meth:`shape` (the NoPen pen is 1.0 wide), so it already holds both
        visible bubble outlines; the margin covers the selection pen
        (2 x ``_pen_w``) and the paper weight."""
        br = super().boundingRect()
        m = max(self._pen_w, self._paper_line_w, 1.0)
        return br.adjusted(-m, -m, m, m)

    def drawn_endpoints(self) -> tuple[QPointF, QPointF]:
        """The painted span: each visible end trimmed where the vertical leaves
        that bubble's block outline (SB4c D2 / AC4). The ray from bubble 1
        runs toward bubble 2 -- (0, +1) when bubble 1 is the top end
        (v_top < v_bot, Qt y-down)."""
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            return p1, p2
        ux, uy = dx / length, dy / length
        t1 = self.bubble1.trim_distance(ux, uy) if self.bubble1.isVisible() else 0.0
        t2 = self.bubble2.trim_distance(-ux, -uy) if self.bubble2.isVisible() else 0.0
        return (QPointF(p1.x() + ux * t1, p1.y() + uy * t1),
                QPointF(p2.x() - ux * t2, p2.y() - uy * t2))

    def _outlines_local(self) -> QPainterPath:
        p = QPainterPath()
        for b in (self.bubble1, self.bubble2):
            if b.isVisible():
                p.addPath(self.mapFromItem(b, b.outline_path()))
        return p

    def shape(self) -> QPainterPath:
        """Hit area: the drawn line with a generous stroke (so Qt paint
        culling keeps the line when both bubbles scroll off-screen) plus both
        visible bubble outlines, so a press on a bubble finds the gridline."""
        p1, p2 = self.drawn_endpoints()
        line_path = QPainterPath()
        line_path.moveTo(p1)
        line_path.lineTo(p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self._pen_w * 4, 8))
        path = stroker.createStroke(line_path)
        path.addPath(self._outlines_local())   # hit area: the visible bubble outlines
        return path

    def halo_trace_path(self, scene_scale=None) -> QPainterPath:
        """Composite HALO trace: the trimmed line plus both visible bubble
        outlines, mirroring :meth:`paint` (plan ``GridlineItem`` parity).
        ``scene_scale`` is accepted for the hook signature and unused."""
        p1, p2 = self.drawn_endpoints()
        path = QPainterPath()
        path.moveTo(p1)
        path.lineTo(p2)
        path.addPath(self._outlines_local())
        return path

    def halo_area_path(self) -> QPainterPath:
        """HALO: a cursor inside a bubble outline is a direct hit (as the
        filled bespoke bubble was); ``halo_pick_distance_px`` reads this hook."""
        return self._outlines_local()

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        draw_p1, draw_p2 = self.drawn_endpoints()

        grid_color = (self._grid_color if self._grid_src is None
                      else resolve_colour(self._grid_src, item=self))
        if self._paper_line_w_mm:
            from .gridline import _dash_pattern_mm
            pen = QPen(grid_color, self._paper_line_w)
            pen.setDashPattern(_dash_pattern_mm(self._paper_line_w_mm))
        else:
            pen = QPen(grid_color, self._pen_w, Qt.PenStyle.DashDotLine)
        painter.setPen(pen)
        painter.drawLine(draw_p1, draw_p2)

        if shows_selection(self) and not self._paper_line_w_mm:
            sel_pen = QPen(grid_color.lighter(150),
                           self._pen_w * 2, Qt.PenStyle.DashDotLine)
            painter.setPen(sel_pen)
            painter.drawLine(draw_p1, draw_p2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.bubble1.update()
            self.bubble2.update()
        return super().itemChange(change, value)

    def enter_paper_pass(self, line_w_mm: float, paper_scale: float,
                         color_src=None) -> dict:
        """Plot the LINE like the plan gridline for one sheet-viewport render
        (AC3, parity with ``paper_display._apply_gridline``): the "Grid Line"
        row's weight and the paper-mm dash-dot; *color_src* replaces the
        stored colour string (B&W / Custom), ``None`` keeps it. Sets
        ``_paper_render`` (the bubbles' rings drop). The bubbles are
        annotation blocks: the paper walk gives each visible one
        ``_apply_block`` (SB4c D4), and the trim then follows their printed
        outline."""
        S = max(paper_scale, 1e-9)
        saved = {"grid_src": self._grid_src}
        self.prepareGeometryChange()
        self._paper_render = True
        self._paper_line_w_mm = line_w_mm
        self._paper_line_w = line_w_mm / S
        if color_src is not None:
            self._grid_src = color_src
        self.bubble1.update()
        self.bubble2.update()
        self.update()
        return saved

    def exit_paper_pass(self, saved: dict) -> None:
        self.prepareGeometryChange()
        self._grid_src = saved["grid_src"]
        self._paper_render = False
        self._paper_line_w_mm = self._paper_line_w = 0.0
        self.bubble1.update()
        self.bubble2.update()
        self.update()

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


class LevelDatumHead(OutlinedLabel):
    """The level datum's head (SB4c D3): the project's "Level" annotation block
    (shipped seed ``LevelDatum``: 4-quadrant symbol + @[Level.Name] /
    @[Level.Elevation]) at the datum's left end, block origin on the line.

    A child of its ``ElevDatumItem``, which is also the data host (``_level``):
    visibility and opacity cascade from it; never rotated. The datum reads
    ``trim_distance(1, 0)`` to start its line at the outline and
    ``outline_path`` for its hit shape. The one overlay is the selection ring:
    screen only -- never with the datum's ``_paper_render`` flag set, never
    inside a paper pass.
    """

    def __init__(self, datum):
        super().__init__(datum)                  # child=True: parent + host

    def overlay_pens(self) -> list:
        dt = self.parentItem()
        if dt is None or getattr(dt, "_paper_render", False) or not shows_selection(dt):
            return []
        pen = QPen(dt.line_color().lighter(150), 2.0)
        pen.setCosmetic(True)
        return [pen]


class ElevDatumItem(QGraphicsLineItem):
    """Interactive level datum in an elevation / section view -- selectable,
    two grips.

    Keeps its ``Level`` (``_level``, the element_params "Level" host: renames
    mutate it in place, so the head re-paints with no rebuild) and owns one
    ``LevelDatumHead`` (``head``) whose block origin sits on the line at
    ``_bx``. The dash-dot line is painted by ``SectionScene.drawForeground``
    from ``line_start_h()`` (the head's outline) to ``_h_max``, so it stays
    visible when the head scrolls off-screen (SB4c D3 / AC4).
    """

    def __init__(self, v_pos: float, h_min: float, h_max: float, level,
                 datum_color: QColor, pen_w: float, *, opacity: float = 1.0,
                 color_src: str | None = None, scale_manager=None):
        super().__init__(h_min, v_pos, h_max, v_pos)
        self._level = level
        # format_utils.get_scale_manager fallback: a SectionScene has no
        # ``scale_manager`` attribute, so Level.Elevation formats through this.
        self._scale_manager_ref = scale_manager
        self._color_src = color_src   # stored colour string, resolved per paint (HF1)
        self._v = v_pos
        self._h_min = h_min
        self._h_max = h_max
        self._datum_color = datum_color
        self._pen_w = pen_w
        self._paper_render = False    # paper pass (SB4c D4): set / cleared by enter / exit_paper_pass
        self._paper_line_w_mm = 0.0   # paper pass: ON-PAPER mm, dash normaliser
        self._paper_line_w = 0.0      # paper pass: datum line width, scene units
        # Head origin = today's circle centre: half a BUBBLE_RADIUS_MM (model
        # mm) left of the crop edge; the head itself is annotative.
        from .gridline import BUBBLE_RADIUS_MM
        self._bx = h_min - BUBBLE_RADIUS_MM * 0.5
        self.head = LevelDatumHead(self)
        self.head.set_anchor(QPointF(self._bx, v_pos))

        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(Z_ANNOT_GRID)   # annotation band: gridline sub-band (SB4d D5)
        self.setOpacity(opacity)
        self.setData(_ROLE_ELEV_ANNOTATION, True)

    # ── Head ─────────────────────────────────────────────────────────────

    def line_color(self) -> QColor:
        """The line colour now: the stored source resolved per paint (HF1)."""
        return (self._datum_color if self._color_src is None
                else resolve_colour(self._color_src, item=self))

    def line_start_h(self) -> float:
        """Scene h where the datum line starts: where the ray from the head
        origin toward the line's far end (``_h_max``, the h ``drawForeground``
        draws to) leaves the head's block outline -- derived, as
        ``ElevGridlineItem`` derives its bubbles' rays from p1 -> p2; (+1, 0)
        whenever the head sits left of the far end. No trim when the head is
        hidden or draws nothing. Screen and paper alike: during a paper pass
        the head's k is 1 / S, so the outline is the printed one."""
        ux = 1.0 if self._h_max >= self._bx else -1.0
        t = self.head.trim_distance(ux, 0.0) if self.head.isVisible() else 0.0
        return self._bx + ux * t

    def snap_segment(self) -> "tuple[QPointF, QPointF]":
        """The DRAWN segment's ends, item coordinates: from the head's edge
        (``line_start_h``, where ``drawForeground`` starts the line) to the
        far end -- the endpoint / midpoint snaps ``SnapEngine._line_snaps``
        offers (OPEN-2 ruling 2026-11-10: snap to the drawn line). T48 (F-2)
        points the far end at ``line_end_h()``."""
        return (QPointF(self.line_start_h(), self._v),
                QPointF(self.line().p2().x(), self._v))

    def refresh_head(self) -> None:
        """Re-shape the head (block mapping, drawing scale, units, paper hooks)
        and this item's bounds + hit shape, which include it."""
        self.prepareGeometryChange()
        self.head.refresh()
        self.update()

    def _move_head(self, bx: float) -> None:
        self._bx = bx
        self.head.set_anchor(QPointF(bx, self._v))

    # ── Drawing ──────────────────────────────────────────────────────────

    def boundingRect(self):
        br = super().boundingRect()
        head = getattr(self, "head", None)
        if head is not None:
            hr = head.boundingRect()
            if not hr.isEmpty():
                br = br.united(head.mapRectToParent(hr))
        return br

    def shape(self) -> QPainterPath:
        """Hit area: the head's block outline -- a press on the head selects
        the datum (the line itself is scene foreground, as before)."""
        head = getattr(self, "head", None)
        if head is None:
            return QPainterPath()
        return head.mapToParent(head.outline_path())

    def halo_trace_path(self, scene_scale=None) -> QPainterPath:
        """Composite HALO trace mirroring what is drawn: the line from the
        head's outline to ``_h_max`` (``drawForeground``) plus the head
        outline -- never the raw ``line()`` from ``h_min`` inside the head
        (``ElevGridlineItem`` parity). ``scene_scale`` is unused."""
        path = QPainterPath()
        h_start = self.line_start_h()
        if self._h_max > h_start:
            path.moveTo(QPointF(h_start, self._v))
            path.lineTo(QPointF(self._h_max, self._v))
        path.addPath(self.shape())
        return path

    def paint(self, painter, option, widget=None):
        # The datum line is drawn by the scene's drawForeground() so it
        # remains visible even when the head has scrolled off-screen; the
        # head paints itself. Do NOT call super().paint() -- the base
        # QGraphicsLineItem must not draw its own line.
        pass

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
            head = getattr(self, "head", None)
            if head is not None:
                head.update()                    # the selection ring (screen only)
        return super().itemChange(change, value)

    def enter_paper_pass(self, line_w_mm: float, paper_scale: float,
                         color_src=None) -> dict:
        """Plot the LINE through the "Level Datum" paper row for one sheet-
        viewport render: its weight and the gridline's paper-mm dash-dot
        (``drawForeground``); *color_src* replaces the stored colour string
        (B&W / Custom), ``None`` keeps it. Sets ``_paper_render`` (the head's
        ring drops), as ``ElevGridlineItem.enter_paper_pass`` does. The head is
        an annotation block and takes ``paper_display._apply_block`` in the
        walk (SB4c D4)."""
        S = max(paper_scale, 1e-9)
        saved = {"color_src": self._color_src}
        self.prepareGeometryChange()
        self._paper_render = True
        self._paper_line_w_mm = line_w_mm
        self._paper_line_w = line_w_mm / S
        if color_src is not None:
            self._color_src = color_src
        self.head.update()
        self.update()
        return saved

    def exit_paper_pass(self, saved: dict) -> None:
        self.prepareGeometryChange()
        self._color_src = saved["color_src"]
        self._paper_render = False
        self._paper_line_w_mm = self._paper_line_w = 0.0
        self.head.update()
        self.update()

    # ── Grip handles ─────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        line = self.line()
        return [line.p1(), line.p2()]

    def apply_grip(self, index: int, new_pos: QPointF):
        """Move grip along the horizontal line (constrained to V position);
        the left grip carries the head (moved, never rebuilt)."""
        from .gridline import BUBBLE_RADIUS_MM
        line = self.line()
        p1, p2 = line.p1(), line.p2()
        self.prepareGeometryChange()
        if index == 0:
            new_x = new_pos.x()
            self.setLine(new_x, self._v, p2.x(), self._v)
            self._move_head(new_x - BUBBLE_RADIUS_MM * 0.5)
        elif index == 1:
            self.setLine(p1.x(), self._v, new_pos.x(), self._v)
        self.update()

    def manip_handles(self):
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0, 1})

    def manip_translate(self, dx: float, dy: float):
        """Axis-constrained interior move (§3.1 read-only-geometry invariant).

        V is pinned to ``self._v`` (a vertical shift would author the datum's
        level elevation), so ``dy`` is dropped; ``dx`` shifts both endpoints,
        moving the horizontal draw-extent, and carries the head (session-only,
        not persisted -- parity).
        """
        line = self.line()
        self.prepareGeometryChange()
        self.setLine(line.p1().x() + dx, self._v, line.p2().x() + dx, self._v)
        self._move_head(self._bx + dx)
        self.update()


def section_source_of(item):
    """The model object a section item stands for (D8 readout + Properties).

    A projected proxy, hosted-block copy or Note copy carries it in
    ``_ROLE_SOURCE``; an elevation gridline stands for its plan
    ``GridlineItem``; a level datum for its ``Level``.

    Args:
        item: A QGraphicsItem of a SectionScene.

    Returns:
        The model object, or None (ghost, decoration, unsourced item).
    """
    src = QGraphicsItem.data(item, _ROLE_SOURCE)
    if src is not None:
        return src
    if isinstance(item, ElevGridlineItem):
        return item._gridline
    if isinstance(item, ElevDatumItem):
        return item._level
    return None


class SectionScene(HaloSelectionMixin, QGraphicsScene):
    """Projects model entities onto a vertical plane for elevation display."""

    entitySelected = pyqtSignal(object)   # picked legacy entity
    cursorMoved = pyqtSignal(str)         # formatted "H: … Z: …"
    modeChanged = pyqtSignal(str)         # "place_block" / "select" (footer badge)
    snapToggled = pyqtSignal(bool)        # toggle_snap() ran (footer SNAP pill; D3)
    # The footer line (elevation-parity D8): the HALO readout and tool hints.
    # MainWindow._on_section_scene_built connects it to footer.set_instruction.
    instructionChanged = pyqtSignal(str)

    # Drafting-tile paper scale during a paper-viewport render (hatch D-A30;
    # set/cleared by paper_display on the viewport's source scene). Declared so
    # the per-paint read in hatch_render hits.
    _hatch_paper_scale = None

    @property
    def block_registry(self):
        """The model scene's BlockRegistry (hatch_render reads it off the
        scene it is handed)."""
        return getattr(self._ms, "block_registry", None)

    def annotation_block(self, category: str, mapped: str | None = None):
        """The ``BlockDefinition`` that draws *category*'s intrinsic label in
        this scene: forwarded to the model scene's resolver (SB4c D1;
        ``Model_Space.annotation_block``, system-blocks.md section 3), so a
        ``BoundLabelItem`` here -- an elevation gridline bubble, a datum head
        -- draws the project's block. None when the model scene is gone
        (a queued paint during teardown)."""
        fn = getattr(self._ms, "annotation_block", None)
        try:
            return fn(category, mapped) if fn is not None else None
        except RuntimeError:          # model scene deleted under a queued paint
            return None

    def refresh_annotation_tags(self) -> None:
        """Re-shape the annotation-block labels this scene draws (SB4c D1):
        each elevation gridline's two bubbles (their bounds rect and outline
        are cached, so a mapping / registry / units / drawing-scale change
        needs ``refresh()``), then the gridline itself (its trim and hit
        shape follow the outline). Called for every open section by
        ``Model_Space.refresh_annotation_tags`` and by
        ``annotative.reprepare_annotative``. Each level datum's head too
        (SB4c D3), and each pipe label, then the scene foreground (the datum
        lines start at the head outline)."""
        for it in list(self.items()):
            try:
                if isinstance(it, ElevGridlineItem):
                    for b in (it.bubble1, it.bubble2):
                        b.refresh()
                    it.prepareGeometryChange()
                    it.update()
                elif isinstance(it, ElevDatumItem):
                    # SB4c D3: the head re-shapes; the datum's bounds / hit
                    # shape include it and drawForeground's line starts at it.
                    it.refresh_head()
                elif isinstance(it, _ElevPipeLabel):
                    it.refresh()
            except RuntimeError:          # wrapper outliving its C++ item (teardown)
                pass
        self.update()                     # foreground datum lines re-trim

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
        self._hosted_copies: dict = {}      # id(model block) -> section copy
        self._hosted_push_pending = False   # one undo step per drag (D10)
        self._place_block_id = None         # armed placement (hosted-blocks G16)
        self._place_ghost = None
        self._place_ghost_pt = None         # last ghost point (survives a rebuild)
        self._place_rot = 0.0
        self._place_mirrored = False
        self._show_datums = True
        # Elevation gridlines + level datums of the current build: the snap
        # engine's line targets (snap_line_items; elevation parity D3).
        self._snap_lines: list = []
        # Cursor snap (D3): the plan's SnapEngine, one per section scene; F3
        # toggles this scene only. Model_Space's attribute names, so the shared
        # manipulator / grip / handle-snap paths read them unchanged.
        from .snap_engine import SnapEngine
        # Read through the ``_snap_engine`` property, which syncs the plan's
        # per-type toggles on every read (integrator OPEN-1).
        self._snap_engine_obj = SnapEngine()
        self._snap_result = None          # the marker SectionView paints
        self._snap_enabled = True

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
            exclude=self._manip_exclude)
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
        """Items the manipulator must never wrap: annotation-block decoration
        children (the elevation gridline bubbles, SB4c D2; datum heads), so
        only the top-level selectable gridline / datum is framed."""
        from .bound_label import BoundLabelItem
        return isinstance(item, BoundLabelItem)

    def _commit_elev_grip(self, mode):
        """Manipulator commit hook (no undo). Persist each selected gridline's
        adjusted Z-extent into ``_gridline_z_overrides``; datum edits are
        session-only (parity)."""
        for it in self.selectedItems():
            if isinstance(it, ElevGridlineItem):
                it._commit_grip_override()
        # The manipulator's release hook closes a hosted drag: one undo step
        # now (the timer in _move_hosted_source is the fallback for a bare
        # translate with no gesture).
        self._flush_hosted_push()

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
        """Emit the HALO stack readout (selection-mode §3.3) on
        ``instructionChanged`` -- the footer line, as
        ``Model_Space._emit_halo_readout`` (elevation-parity D8).

        Format ``"<Type> — <i> of <N>"`` plus ``"  (<name>)"`` when the shown
        object has a name; *Type* is the model source the item stands for
        (``section_source_of``), so a pipe proxy reads ``Pipe``. An empty
        string (no candidate) clears the line.
        """
        item = self.halo_item()
        if item is None:
            self.instructionChanged.emit("")
            return
        src = section_source_of(item)
        shown = src if src is not None else item
        n = len(self._halo_candidates)
        readout = f"{type(shown).__name__} — {self._halo_index + 1} of {n}"
        name = getattr(shown, "name", None)
        if isinstance(name, str) and name:
            readout += f"  ({name})"
        self.instructionChanged.emit(readout)

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
            # target is None on a right-click over empty canvas (AC8): hide
            # the selection, never None. Area E's menu rewrite keeps this.
            on_hide=lambda: self._hide_elev_items(
                [i for i in [target] + [i for i in selected if i is not target]
                 if i is not None]
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
            lab = getattr(item, "pipe_label", None)
            if lab is not None:
                lab.setVisible(False)

    def _show_all_elev_hidden(self):
        """Restore all hidden source entities and rebuild."""
        self._ms._show_all_hidden()
        self.rebuild()

    def _move_hosted_source(self, copy, dx: float, dy: float) -> None:
        """A drag on a hosted copy moves its model block in its plane only:
        ``along_mm`` (by the section's h direction) + ``elevation_mm`` (D10).
        Host and offset are untouched, so a locked host gridline still lets
        the block move."""
        from . import hosted_blocks as hb
        src = copy.data(_ROLE_SOURCE)
        host = getattr(src, "host", None)
        gl = self._ms.gridline_by_uid(host.get("gridline")) if host else None
        if gl is None:
            return
        host["along_mm"] = float(host["along_mm"]) + dx * hb.h_sign(self._basis, gl)
        host["elevation_mm"] = float(host["elevation_mm"]) - dy
        self._ms._sync_hosted_blocks(gl)
        if not self._hosted_push_pending:
            self._hosted_push_pending = True
            QTimer.singleShot(0, self._flush_hosted_push)

    def _flush_hosted_push(self) -> None:
        """Push the one undo step for a hosted drag (no-op when none pending)."""
        if not self._hosted_push_pending:
            return
        self._hosted_push_pending = False
        self._ms.push_undo_state()

    # ── Shared project undo stack (elevation-parity R13 / D1) ────────────
    # A section owns no stack: every section edit pushes onto the plan
    # Model_Space's, and Ctrl+Z / Ctrl+Y / the header buttons on a section tab
    # (MainWindow._dispatch_undo -> _active_scene()) step that same stack.

    def _ready_for_shared_undo(self) -> bool:
        """End section-side state a restore would orphan; False = refuse.

        Refused while the section manipulator drags (the restore rebuilds the
        items under the gesture -- plan's ``_manip_drag_blocks_undo``). A
        hosted drag's deferred step is pushed first, so the undo reverts the
        drag. A running modify tool ends (plan's
        ``_cancel_modify_tool_for_undo``; ``_modify_ctl`` is area C's host).

        Returns:
            True when the shared stack may be stepped now.
        """
        m = self._live_manip()
        if m is not None and m.is_dragging():
            return False
        self._flush_hosted_push()
        ctl = getattr(self, "_modify_ctl", None)
        if ctl is not None and getattr(self, "mode", None) in ctl.CANCEL_ON_UNDO_MODES:
            self.set_mode(None)
        return True

    def undo(self) -> None:
        """Step the shared plan stack back (see ``_ready_for_shared_undo``)."""
        if self._ready_for_shared_undo():
            self._ms.undo()

    def redo(self) -> None:
        """Step the shared plan stack forward (see ``_ready_for_shared_undo``)."""
        if self._ready_for_shared_undo():
            self._ms.redo()

    def can_undo(self) -> bool:
        """The shared plan stack's undo state (header rail)."""
        return self._ms.can_undo()

    def can_redo(self) -> bool:
        """The shared plan stack's redo state (header rail)."""
        return self._ms.can_redo()

    def _delete_elev_selected(self):
        """Delete source entities for selected elevation items."""
        hosted = [it.data(_ROLE_SOURCE) for it in self.selectedItems()
                  if isinstance(it, _HostedBlockCopy)]
        others = [it for it in self.selectedItems()
                  if not isinstance(it, _HostedBlockCopy)]
        # Only the section's selection is deleted: a stale plan selection must
        # not ride along into delete_items / delete_selected_items.
        plan_sel = list(self._ms.selectedItems())
        self._ms.select_items(                    # clear + select, one emit (§5.9)
            [src for src in (it.data(_ROLE_SOURCE) if it else None for it in others)
             if src is not None and hasattr(src, "setSelected")])
        if hosted:
            # Plan-hidden model blocks: setSelected would not stick, so they
            # join the model selection in ONE explicit-list delete (one undo).
            self._ms.delete_items([h for h in hosted if h is not None]
                                  + list(self._ms.selectedItems()))
        else:
            self._ms.delete_selected_items()
        self._ms.select_items(plan_sel, clear=False)   # the plan selection survives
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

    # ── Gridline-hosted block placement (hosted-blocks D9) ───────────────

    def _hosted_target(self, scene_pt):
        """The host gridline for a placement at *scene_pt*, or None (G8/G9)."""
        from . import hosted_blocks as hb
        b = self._basis
        if b is None or not (b.h_min <= scene_pt.x() <= b.h_max):
            return None
        return hb.choose_host(b, getattr(self._ms, "_gridlines", []), self._ppm())

    def can_host_at(self, scene_pt) -> bool:
        """True when a block placed at *scene_pt* would find a host gridline."""
        return self._hosted_target(scene_pt) is not None

    def begin_place_block(self, block_id: str) -> None:
        """Arm section placement of *block_id*: a translucent ghost follows the
        cursor and a click places it on the host gridline (hosted-blocks G16)."""
        self._drop_place_state()                 # silent: no select flicker
        self._place_block_id, self._place_rot = block_id, 0.0
        self._place_mirrored = False
        g = _HostedBlockCopy(block_id=block_id, resolver=self._ms.get_block_definition)
        g._is_ghost = True
        g.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        g.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        g.set_block_scale(1.0 / self._ppm())          # section scene is mm
        g.setOpacity(0.5)
        g.setZValue(1000.0)
        self.addItem(g)
        self._place_ghost = g
        self.modeChanged.emit("place_block")

    def cancel_place_block(self) -> None:
        """Disarm section placement and drop the ghost (no-op when idle)."""
        was_armed = self._place_block_id is not None
        self._drop_place_state()
        if was_armed:
            self.modeChanged.emit("select")

    def _drop_place_state(self) -> None:
        """Clear the armed id, the placement's snap marker and the ghost,
        emitting nothing."""
        g, self._place_ghost = self._place_ghost, None
        self._place_block_id = None
        self._place_ghost_pt = None
        self._snap_result = None
        if g is not None and g.scene() is self:
            self.removeItem(g)

    def rotate_place_block(self, delta_deg: float) -> None:
        """Turn the armed placement by *delta_deg* (Y-up CCW+, same convention
        and normalisation as ``Model_Space.rotate_place_block``)."""
        r = (self._place_rot + delta_deg) % 360.0
        self._place_rot = r - 360.0 if r > 180.0 else r
        if self._place_ghost is not None:
            self._place_ghost.set_block_rotation(self._place_rot)

    def flip_place_block(self, axis: str) -> None:
        """Flip the armed placement across a SCREEN line through its origin
        (same pose algebra as ``Model_Space.flip_place_block``); each call
        toggles, live on the ghost.

        Args:
            axis: ``"h"`` for left/right (mirror across the screen-vertical
                line) or ``"v"`` for up/down (screen-horizontal line).
        """
        theta = 90.0 if axis == "h" else 0.0        # Y-up heading of the mirror line
        self._place_rot, self._place_mirrored = reflect_pose(
            self._place_rot, self._place_mirrored, theta)
        if self._place_ghost is not None:
            self._place_ghost.set_block_rotation(self._place_rot)
            self._place_ghost.set_block_mirrored(self._place_mirrored)

    def move_place_ghost(self, scene_pt) -> None:
        """Put the ghost at *scene_pt*; faded when no host gridline is in reach."""
        g = self._place_ghost
        self._place_ghost_pt = (scene_pt.x(), scene_pt.y())
        if g is not None:
            g.set_block_pos(scene_pt.x(), scene_pt.y())
            g.setOpacity(0.5 if self.can_host_at(scene_pt) else 0.2)

    def click_place_block(self, scene_pt):
        """Place the armed block at *scene_pt*; placement stays armed (repeat)."""
        bid = self._place_block_id
        if bid is None:
            return None
        self._place_ghost_pt = (scene_pt.x(), scene_pt.y())   # the re-armed ghost stays here
        return self.place_hosted_block(bid, scene_pt, rotation=self._place_rot,
                                       mirrored=self._place_mirrored)

    # ── Snap (elevation parity D3: the plan SnapEngine) ──────────────────

    def snap_line_items(self) -> list:
        """``SnapEngine`` hook: this build's elevation gridlines and level
        datums, taken by ``find()`` phases 2-4 like the plan's ``_gridlines``
        (``snap_engine._line_targets``). A datum's bounding rect is its head
        and a gridline's hit shape is trimmed at its bubbles, so the cursor
        rect query alone would miss the datum x gridline crossing (D3 step-1
        probe)."""
        return list(self._snap_lines)

    def _snap_view(self):
        """The view whose zoom drives the snap aperture: the shown SectionView,
        else the last attached one (headless tests attach without showing),
        else None (``Model_Space._snap_view`` parity)."""
        views = self.views()
        for v in views:
            if v.isVisible():
                return v
        return views[-1] if views else None

    def toggle_snap(self, enabled: bool | None = None) -> None:
        """Toggle or set THIS section's SNAP (F3 / the footer SNAP pill through
        ``MainWindow._active_scene()``); the plan scene's state is untouched
        (AC13). Mirrors ``Model_Space.toggle_snap``.

        Args:
            enabled: None flips; a bool sets.
        """
        if enabled is None:
            self._snap_enabled = not self._snap_enabled
        else:
            self._snap_enabled = bool(enabled)
        self._snap_engine.enabled = self._snap_enabled
        self._snap_result = None
        for v in self.views():
            v.viewport().update()
        self.snapToggled.emit(self._snap_enabled)

    @property
    def _snap_engine(self):
        """This section's ``SnapEngine`` with the plan engine's per-type
        toggles copied in on EVERY read (integrator OPEN-1): the manipulator,
        grip and Move handle-snap paths (``manip_handle.py:582``,
        ``selection_manipulator.py:916/1460/1476``,
        ``modify_tools_controller.py:831``) read ``scene._snap_engine`` and call
        the engine directly, never ``snap_point``. None before ``__init__``
        built it."""
        eng = getattr(self, "_snap_engine_obj", None)
        if eng is not None:
            self._sync_snap_type_toggles()
        return eng

    def _sync_snap_type_toggles(self) -> None:
        """Adopt the plan engine's per-type toggles (the footer osnap bar and
        Settings write the plan engine only), so a section snaps to the same
        kinds as plan."""
        from .snap_engine import SNAP_TYPE_TOGGLES
        src = getattr(self._ms, "_snap_engine", None)
        if src is None:
            return
        for attr in SNAP_TYPE_TOGGLES:
            setattr(self._snap_engine_obj, attr, getattr(src, attr))

    def snap_point(self, scene_pos) -> QPointF:
        """Snap *scene_pos* through this section's engine NOW (hosted-block
        placement, a Blocks-browser drag): F3 respected, the placement ghost
        (or the dragged grip item) excluded; the result is ``_snap_result``,
        the marker ``SectionView.drawForeground`` paints. Replaces the retired
        per-axis section snapper.

        Args:
            scene_pos: Cursor, section-scene coordinates.

        Returns:
            The snapped point, or a copy of *scene_pos* (no view, snap off,
            nothing in the aperture).
        """
        from .handle_snap import HandleSnapResult
        view = self._snap_view()
        if not self._snap_enabled or view is None:
            self._snap_result = None
            return QPointF(scene_pos)
        held = self._snap_result      # (the toggles sync on the _snap_engine read below)
        if isinstance(held, HandleSnapResult):
            held = None     # a handle's marker, not a cursor snap (Model_Space parity)
        res = self._snap_engine.find(
            QPointF(scene_pos), self, view.transform(),
            exclude=self._grip_item if self._grip_dragging else self._place_ghost,
            held=held)
        self._snap_result = res
        return QPointF(res.point) if res is not None else QPointF(scene_pos)

    def get_effective_position(self, scene_pos) -> QPointF:
        """The section's cursor-snap authority — ``Model_Space``'s name and
        contract, so ``GripHandle._cursor_point`` and the section modify host
        (area C) reach it: the engine runs while a grip drag or a tool mode is
        live, never in plain select mode nor in a raw-cursor mode
        (``snap_engine.raw_cursor_mode``). No ALIGN and no grid fallback in a
        section.

        Args:
            scene_pos: Cursor, section-scene coordinates.

        Returns:
            The snapped point, or a copy of *scene_pos* (and no marker).
        """
        from .snap_engine import raw_cursor_mode
        mode = getattr(self, "mode", None)          # ModifyHostMixin (area B); None before it
        live = ((self._grip_dragging or mode not in (None, "select"))
                and not raw_cursor_mode(mode, getattr(self, "pick_base_pos", None)))
        if not live:
            self._snap_result = None
            return QPointF(scene_pos)
        return self.snap_point(scene_pos)

    def place_hosted_block(self, block_id: str, scene_pt, rotation: float = 0.0,
                           mirrored: bool = False):
        """Place a gridline-hosted model block at section *scene_pt* (D9).

        Returns:
            The model instance, or None after the G9 refusal status.
        """
        from . import hosted_blocks as hb
        gl = self._hosted_target(scene_pt)
        if gl is None:
            self._ms._show_status(HOSTED_REFUSAL)
            return None
        host = hb.host_at(self._basis, gl, scene_pt.x(), -scene_pt.y(), self._ppm())
        inst = self._ms.place_block_instance(block_id, (0.0, 0.0), rotation=rotation,
                                             mirrored=mirrored, host=host)
        if inst is not None:
            inst.setVisible(False)                 # D11: hosted blocks never show in plan
            self._ms.push_undo_state()
            self.rebuild()
            cp = self._hosted_copies.get(id(inst))
            if cp is not None:
                self.clearSelection()
                cp.setSelected(True)
        return inst

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
        """Edge/line colour from the current theme. No background brush (AC5,
        plan parity with ``Model_Space``): the app QSS paints the canvas
        behind the view, and a brush here would plot on paper."""
        bg = QColor(th.detect().canvas_bg)
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
        self._snap_lines = []               # re-filled by the gridline / datum projections
        self._snap_result = None            # its source items die in clear()
        self._place_ghost = None            # clear() deletes it; re-armed below
        self.clear()
        self._depth_items: list[tuple[float, list]] = []  # (depth, [items])
        self._hosted_depth: list[tuple[float, object]] = []   # (sort key, top item), tag band
        self._project_level_datums()
        self._project_walls()
        self._project_hosted_blocks()
        self._project_openings()
        self._project_pipes()
        self._project_sprinklers()
        self._project_floor_slabs()
        self._project_roofs()
        self._project_gridlines()
        self._render_cut_items()
        self._project_geometry_2d()
        self._assign_depth_z_values()
        if self._place_block_id is not None:        # placement survives a rebuild
            bid, rot, gpt = self._place_block_id, self._place_rot, self._place_ghost_pt
            mir = self._place_mirrored
            self.begin_place_block(bid)
            self._place_rot, self._place_mirrored = rot, mir
            if self._place_ghost is not None:
                self._place_ghost.set_block_rotation(rot)
                self._place_ghost.set_block_mirrored(mir)
                if gpt is not None:
                    self._place_ghost_pt = gpt
                    self._place_ghost.set_block_pos(*gpt)

    def _project_hosted_blocks(self):
        """Copies of gridline-hosted model blocks whose host is parallel to
        this cut (hosted-blocks D8): depth-cropped, depth-ordered, laterally
        clipped, mirrored when seen from the host's other side.

        Visibility never follows the model block (always hidden in plan, D11).
        """
        from . import hosted_blocks as hb
        self._hosted_copies = {}
        ms, b, ppm = self._ms, self._basis, self._ppm()
        for src in list(getattr(ms, "_block_instances", [])):
            host = getattr(src, "host", None)
            if not host or not hb.valid_host(host):
                continue
            gl = ms.gridline_by_uid(host.get("gridline"))
            if gl is None or not hb.is_parallel(b, gl):
                continue
            pose = hb.section_pose(b, gl, host, src.block_rotation(),
                                   src.block_mirrored(), ppm)
            if pose is None:
                continue
            h, v, _d, mirrored, rot = pose
            rec = src.to_dict()
            rec.pop("host", None)                # the copy is not itself hosted
            cp = _HostedBlockCopy.from_dict(rec, ms.get_block_definition)
            cp.set_block_pos(h, v)
            cp.set_block_rotation(rot)
            cp.set_block_mirrored(mirrored)
            cp.set_block_scale(src.block_scale() / ppm)   # section scene is mm
            cp.setData(_ROLE_SOURCE, src)
            # Measure in the scene: an annotative copy sizes from its scene's
            # drawing scale, so its unparented bounds are the authored size.
            self.addItem(cp)
            br = cp.mapRectToScene(cp.boundingRect())
            top = cp
            if br.left() < b.h_min or br.right() > b.h_max:
                if self._clip_h(br.left(), br.right()) is None:
                    self.removeItem(cp)
                    continue
                clip = QGraphicsRectItem(QRectF(b.h_min, br.top() - 1.0,
                                                b.h_max - b.h_min, br.height() + 2.0))
                clip.setPen(QPen(Qt.PenStyle.NoPen))
                clip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, True)
                self.addItem(clip)
                cp.setParentItem(clip)
                top = clip
            wx, wy = hb.world_point(gl, host, ppm)
            self._hosted_depth.append((b.sort_key(wx, wy), top))   # tag band, not the depth walk (D5)
            self._hosted_copies[id(src)] = cp

    def _register_depth_item(self, depth: float, *items):
        """Register scene items at a given depth for unified Z assignment."""
        self._depth_items.append((depth, list(items)))

    def _assign_depth_z_values(self):
        """Sort all depth-registered items farthest-first and assign Z-values.

        Items at the same depth are drawn in registration order.
        Farther items get lower Z (drawn first / behind).
        """
        self._depth_items.sort(key=lambda x: x[0])
        z = _DEPTH_Z_START
        for depth, items in self._depth_items:
            for item in items:
                item.setZValue(min(z, Z_DEPTH_CEIL))   # bounded below the annotation band (SB4d Q17)
                z += _DEPTH_Z_STEP
        self._depth_items = []
        hosted = sorted(getattr(self, "_hosted_depth", ()), key=lambda x: x[0])
        for i, (_key, top) in enumerate(hosted):
            top.setZValue(Z_ANNOT_TAG + i * _HOSTED_Z_STEP)   # farthest first: near over far
        self._hosted_depth = []

    # ── Foreground (datum lines) ─────────────────────────────────────────

    def drawForeground(self, painter, rect):
        """Draw datum lines from the head's outline across the crop box (basis h_min..h_max).

        Drawn in foreground so lines remain visible even when the head
        has scrolled out of the viewport.
        """
        super().drawForeground(painter, rect)
        for item in self.items():
            if not isinstance(item, ElevDatumItem):
                continue
            if not item.isVisible():
                continue
            v = item._v
            h_start = item.line_start_h()
            h_end = item._h_max
            if h_end <= h_start:
                continue

            datum_color = item.line_color()
            painter.save()
            if item._paper_line_w_mm:
                from .gridline import _dash_pattern_mm
                pen = QPen(datum_color, item._paper_line_w)
                pen.setDashPattern(_dash_pattern_mm(item._paper_line_w_mm))
                # The scene painter carries no item opacity: apply the
                # "Level Datum" row Opacity the children get (AC4).
                painter.setOpacity(painter.opacity() * item.opacity())
            else:
                pen = QPen(datum_color, item._pen_w, Qt.PenStyle.DashDotLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(h_start, v), QPointF(h_end, v))
            painter.restore()

            if shows_selection(item) and not item._paper_line_w_mm:
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
            rect._paper_cat = "Wall"
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
            # Cut walls' head / sill carve lives in _wall_cut_spans; the
            # opening (void + frame) is drawn only for walls behind the cut.
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

                for it in items_to_add[1:]:          # the void is NoPen
                    it._paper_cat = op.display_category
                for item in items_to_add:
                    self.addItem(item)
                self._register_depth_item(depth, *items_to_add)

    # ── Pipes ────────────────────────────────────────────────────────────

    def _project_pipes(self):
        from .constants import PIPE_COLORS as _PIPE_COLORS
        from .fitting import Fitting
        lines = []                # (line, d1, d2)
        end_on = []               # (d near, pipe, near node, h, v, size)
        circles = []              # (h, v, r, d)
        cut_size = RISER_SYMBOL_SIZE_MM

        def add_line(pipe, a, b, sort):
            (h1, v1, d1), (h2, v2, d2) = a, b
            col_name = pipe._properties.get("Colour", {}).get("value", "Red")
            line = _ElevProxyLine(h1, v1, h2, v2)
            pen = QPen(QColor(_PIPE_COLORS.get(col_name, "#e62828")), 2)
            pen.setCosmetic(True)
            line.setPen(pen)
            line._paper_cat = "Pipe"
            line.setData(_ROLE_SOURCE, pipe)
            line.setFlag(QGraphicsLineItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.addItem(line)
            self._register_depth_item(sort, line)
            lines.append((line, d1, d2))
            self._add_pipe_label(pipe, line)

        for pipe in self._ms.sprinkler_system.pipes:
            n1, n2 = pipe.node1, pipe.node2
            if n1 is None or n2 is None:
                continue
            wx1, wy1 = self._scene_to_world(n1.scenePos().x(), n1.scenePos().y())
            wx2, wy2 = self._scene_to_world(n2.scenePos().x(), n2.scenePos().y())
            z1 = getattr(n1, "z_pos", 0.0)
            z2 = getattr(n2, "z_pos", 0.0)

            zone, h_cut, t_cut = self._basis.classify_segment((wx1, wy1), (wx2, wy2))
            self._zones[id(pipe)] = zone
            if zone == ZONE_HIDDEN:
                continue
            b = self._basis
            d1, d2 = b.d(wx1, wy1), b.d(wx2, wy2)
            if zone == ZONE_CUT:
                z_cut = z1 + t_cut * (z2 - z1)
                self._cut_items.append(("pipe", pipe, (h_cut, z_cut)))
                circles.append((h_cut, -z_cut, radius_of(cut_size), 0.0))
                # R-4: the part beyond the cut draws as a normal line.
                fx, fy, fz, fd = (wx1, wy1, z1, d1) if d1 > d2 else (wx2, wy2, z2, d2)
                hf, vf = self._project(fx, fy, fz)
                if fd > 1e-9 and math.hypot(hf - h_cut, vf + z_cut) >= 1.0:
                    a = self._clip_pipe_ends((h_cut, -z_cut, 0.0), (hf, vf, fd))
                    add_line(pipe, *a, b.sort_key((wx1 + wx2) / 2, (wy1 + wy2) / 2))
                continue

            h1, v1 = self._project(wx1, wy1, z1)
            h2, v2 = self._project(wx2, wy2, z2)
            if math.hypot(h2 - h1, v2 - v1) < 1.0:     # end-on, not crossing (R-6)
                if abs(d2 - d1) >= 1.0:                # else a zero-length pipe
                    near, dn = (n1, d1) if d1 <= d2 else (n2, d2)
                    size = Fitting.plan_symbol_mm(
                        near.fitting._max_connected_width_mm(),
                        getattr(pipe, "_display_scale", 1.0))
                    end_on.append((dn, pipe, near, h1, v1, size))
                continue
            a = self._clip_pipe_ends((h1, v1, d1), (h2, v2, d2))
            add_line(pipe, *a, b.sort_key((wx1 + wx2) / 2, (wy1 + wy2) / 2))

        self._draw_end_on_symbols(end_on, circles)
        circles.sort()
        hs = [c[0] for c in circles]
        r_max = max((c[2] for c in circles), default=0.0)
        for line, d1, d2 in lines:
            ln = line.line()
            spans = kept_spans((ln.x1(), ln.y1()), (ln.x2(), ln.y2()), d1, d2,
                               circles, hs, r_max)
            if spans is not None:
                line.set_spans(spans)
                if not spans and line.pipe_label is not None:  # nothing left to label
                    self.removeItem(line.pipe_label)
                    line.pipe_label = None

    def _clip_pipe_ends(self, a, b):
        """Lateral clip of a projected pipe to the crop box, by parameter
        (either orientation). *a*, *b* = (h, v, d); never clipped vertically."""
        (h1, v1, d1), (h2, v2, d2) = a, b
        lo, hi = self._basis.h_min, self._basis.h_max
        if abs(h2 - h1) > 1e-9:
            ta = (lo - h1) / (h2 - h1)
            tb = (hi - h1) / (h2 - h1)
            t0, t1 = max(0.0, min(ta, tb)), min(1.0, max(ta, tb))
            if t0 < t1:
                def at(t):
                    return (h1 + t * (h2 - h1), v1 + t * (v2 - v1), d1 + t * (d2 - d1))
                return at(t0), at(t1)
        return a, b

    def _draw_end_on_symbols(self, end_on, circles) -> None:
        """Draw each end-on pipe's C, nearest first; a point already holding a
        symbol keeps it (a run heading away stacks at one point). Appends the
        drawn circles to *circles* for the trim."""
        from .constants import PIPE_COLORS as _PIPE_COLORS
        taken = {(round(c[0]), round(c[1])) for c in circles}
        for dn, pipe, near, h, v, size in sorted(end_on, key=lambda r: r[0]):
            key = (round(h), round(v))
            if key in taken:
                continue
            taken.add(key)
            ux, uy = self._end_on_gap(pipe, near, h, v)
            col_name = pipe._properties.get("Colour", {}).get("value", "Red")
            own = _PIPE_COLORS.get(col_name, "#e62828")
            sym = _ElevEndOnSymbol(h - size / 2.0, v - size / 2.0, size, size)
            sym.set_ink(end_on_path(h, v, size, ux, uy))
            pen = QPen(QColor(own), 2)
            pen.setCosmetic(True)
            sym.setPen(pen)
            sym.set_colour_src(pen=own)
            sym._paper_cat = "Pipe"
            sym.setData(_ROLE_SOURCE, pipe)
            sym.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.addItem(sym)
            self._register_depth_item(-dn, sym)
            circles.append((h, v, radius_of(size), dn))

    def _end_on_gap(self, pipe, near, h, v) -> tuple[float, float]:
        """R-7: scene direction of the first in-view pipe joined at *near*,
        else down."""
        for other in near.pipes:
            if other is pipe or self._zones.get(id(other), ZONE_HIDDEN) == ZONE_HIDDEN:
                continue
            q = other.node1 if other.node2 is near else other.node2
            if q is None:
                continue
            wx, wy = self._scene_to_world(q.scenePos().x(), q.scenePos().y())
            hq, vq = self._project(wx, wy, getattr(q, "z_pos", 0.0))
            length = math.hypot(hq - h, vq - v)
            if length >= 1.0:
                return (hq - h) / length, (vq - v) / length
        return 0.0, 1.0

    def _add_pipe_label(self, pipe, line) -> None:
        """R-8, R-9: label a drawn line, following the pipe's Show Label."""
        if pipe._properties["Show Label"]["value"] != "True":
            return
        ln = line.line()
        mid, angle = CAD_Math.readable_line_pose(ln.p1(), ln.p2())
        lab = _ElevPipeLabel(pipe, child=False)
        self.addItem(lab)
        lab.set_anchor(mid)
        lab.setRotation(angle)
        lab._pose_rot = angle
        lab.setZValue(Z_ANNOT_TAG)
        lab.refresh()
        line.pipe_label = lab

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
            ellipse._paper_cat = "Sprinkler"
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
            rings = slab.cut_region()
            if not rings:                    # a void swallows the slab: no body (A4)
                self._zones[id(slab)] = ZONE_HIDDEN
                continue
            h_vals = []
            world_pts = []
            for pt in pts:
                wx, wy = self._scene_to_world(pt.x(), pt.y())
                world_pts.append((wx, wy))
                h, _ = self._project(wx, wy, 0)
                h_vals.append(h)
            if slab.openings:                # material extent: edge voids narrow it
                h_vals = [self._project(*self._scene_to_world(p.x(), p.y()), 0)[0]
                          for outer, _holes in rings for p in outer]
            h_min, h_max = min(h_vals), max(h_vals)

            zone, h_lo, h_hi = self._basis.classify_polygon(world_pts)
            self._zones[id(slab)] = zone
            if zone == ZONE_HIDDEN:
                continue
            if zone == ZONE_CUT:
                spans = self._slab_cut_spans(slab, rings, h_lo, h_hi)
                for s_lo, s_hi in spans:
                    self._cut_items.append(("slab", slab, (s_lo, s_hi, bot_z, top_z)))
                if spans:
                    continue
                # The cut line runs only through voids: draw the rest as elevation.
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
            rect._paper_cat = "Floor"
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

    def _slab_cut_spans(self, slab, rings, h_lo: float,
                        h_hi: float) -> list[tuple[float, float]]:
        """Horizontal spans where the cut line crosses slab material (A4 section).

        A void-less slab keeps the classified ``(h_lo, h_hi)``. With voids: one
        span per ``floor_cut.intervals_inside`` interval of the marker's cut
        segment (scene coords; ``h`` is affine in its parameter).

        Args:
            slab: The cut FloorSlab.
            rings: ``slab.cut_region()``.
            h_lo: Classified low h of the full footprint.
            h_hi: Classified high h of the full footprint.

        Returns:
            ``[(h_lo, h_hi), ...]`` ascending; empty when the cut line meets
            only voids.
        """
        if not slab.openings:
            return [(h_lo, h_hi)]
        from .floor_cut import intervals_inside
        ha, hb = self._basis.h_a, self._basis.h_b
        out = []
        for t0, t1 in intervals_inside(rings, self._marker.cut_a, self._marker.cut_b):
            a, b = ha + t0 * (hb - ha), ha + t1 * (hb - ha)
            out.append((min(a, b), max(a, b)))
        return sorted(out)

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
            rect._paper_cat = "Roof"
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
                    rect._paper_cat = "Wall" if kind == "wall" else "Floor"
                    rect.set_section(src, self)
                    rect.setOpacity(props["opacity"] / 100.0)
                    rect.setData(_ROLE_SOURCE, src)
                    rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                    self.addItem(rect)
                    self._register_depth_item(0.0, rect)
            elif kind == "pipe":
                h, z = data
                size = RISER_SYMBOL_SIZE_MM
                col_name = src._properties.get("Colour", {}).get("value", "Red")
                own = _PIPE_COLORS.get(col_name, "#e62828")
                sym = _ElevCutEllipse(h - size / 2.0, -z - size / 2.0, size, size)
                sym.set_ink(cut_symbol_path(h, -z, size))
                pen = QPen(QColor(own), 2)
                pen.setCosmetic(True)
                sym.setPen(pen)
                sym.set_colour_src(pen=own, brush=pipe_sec or None)
                sym._paper_cat = "Pipe"
                sym.setData(_ROLE_SOURCE, src)
                sym.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                self.addItem(sym)
                self._register_depth_item(0.0, sym)

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
        }

    def _pipe_display_props(self) -> dict:
        """Read the Pipe Section colour (None in the default row)."""
        s = QSettings("GV", "FirePro3D")
        return {"section": s.value("display/Pipe/section", None)}

    def _gridline_display_props(self) -> dict:
        """Read the Grid Line row from QSettings (Display Manager): colour
        (tints the line), opacity and visibility. The bubbles are annotation
        blocks; the Fill / Scale columns are retired (SB4b D11, SB4c D4)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Grid Line/color",   "#4488cc"),
            "opacity": int(float(s.value("display/Grid Line/opacity", 100))),
            "visible": str(s.value("display/Grid Line/visible", "true")).lower() not in ("false", "0"),
        }

    def _datum_display_props(self) -> dict:
        """Read the Level Datum row from QSettings (Display Manager): colour
        (tints the line), opacity and visibility (the whole datum). The head is
        the "Level" annotation block; Fill / Font / Scale are retired (SB4c D4)."""
        s = QSettings("GV", "FirePro3D")
        return {
            "color":   s.value("display/Level Datum/color",   "#4488cc"),
            "opacity": int(float(s.value("display/Level Datum/opacity", 100))),
            "visible": str(s.value("display/Level Datum/visible", "true")).lower() not in ("false", "0"),
        }

    # ── Gridlines ────────────────────────────────────────────────────────

    def _project_gridlines(self):
        props = self._gridline_display_props()
        if not props["visible"]:
            return

        grid_src = props["color"]                  # resolved per paint
        grid_color = resolve_colour(grid_src)
        opacity = props["opacity"] / 100.0
        # SB4c D2: the bubbles are the plan gridline's annotation block; the
        # Display Manager Grid Line Fill / Scale (retired from the UI in SB4b)
        # are no longer read here.

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
            v_top = -z_max - ELEV_GRIDLINE_END_PAD_MM
            v_bot = -z_min + ELEV_GRIDLINE_END_PAD_MM

            # Apply per-view override if the user has grip-dragged this gridline
            if label_text in self._gridline_z_overrides:
                ov = self._gridline_z_overrides[label_text]
                v_top = ov.get("v_top", v_top)
                v_bot = ov.get("v_bot", v_bot)

            item = ElevGridlineItem(
                h_avg, v_top, v_bot, label_text,
                grid_color, ELEV_GRIDLINE_PEN_W_MM, opacity,
                color_src=grid_src, gridline=gl)
            self.addItem(item)
            self._snap_lines.append(item)

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

        # Level Datum display row: colour tints the line; Visible / Opacity act
        # on the whole datum (SB4c D4). The head is the "Level" block.
        props = self._datum_display_props()
        if not props.get("visible", True):
            return
        datum_src = props["color"]                      # resolved per paint
        datum_color = resolve_colour(datum_src)
        opacity = props["opacity"] / 100.0

        h_min, h_max = self._datum_extent()

        # Datum line pen (model mm): the elevation gridline's frozen scale-1
        # weight (203.2 * 0.04) -- the Display Manager Scale columns are
        # retired (SB4b D11, SB4c D4).
        datum_pen_w = ELEV_GRIDLINE_PEN_W_MM

        # Level.Elevation formats in the project's live units. A SectionScene
        # has no ``scale_manager`` attribute, so format_utils.get_scale_manager
        # returns None for its items; the datum carries the model's live
        # ScaleManager as ``_scale_manager_ref`` instead of a new
        # SectionScene.scale_manager property, which would change every
        # projected proxy's get_scale_manager. ``_sm`` is the fallback (a
        # project load replaces the model's ScaleManager -- the
        # annotative._drawing_scale rule).
        sm = getattr(self._ms, "scale_manager", None) or self._sm

        for lvl in self._lm.levels:
            item = ElevDatumItem(-lvl.elevation, h_min, h_max, lvl, datum_color,
                                 datum_pen_w, opacity=opacity, color_src=datum_src,
                                 scale_manager=sm)
            self.addItem(item)
            item.refresh_head()       # the head resolves its block only once in a scene
            self._snap_lines.append(item)

    # ── Selection ────────────────────────────────────────────────────────
    # Selection is handled by Qt's built-in rubber-band + ItemIsSelectable
    # flags, routed through _on_selection_changed() which emits entitySelected.
