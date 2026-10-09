"""
geometry_2d.py
=========================
Reference-geometry items for FirePro 3D.

PolylineItem      — a multi-click open polyline on the active user layer.
"""

from __future__ import annotations

import logging
import math
import uuid
import weakref

from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem, QGraphicsLineItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsEllipseItem,
    QStyle,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (QPen, QColor, QPainter, QPainterPath, QBrush,
                         QPainterPathStroker, QPolygonF, QTransform)
from . import crisp_stroke as _cs
from .constants import CRISP_AXIS_TOL
from .displayable_item import DisplayableItemMixin
from .hatch_patterns import DEFAULT_TILE_REF
from . import end_render as _er
from .linetype_render import badge_pad_px, printed_factor
from .paper_display import paper_legacy_px, paper_pass_active, resolve_line_weight_mm
from .scale_manager import ScaleManager
from .stroke_style import (BY_BLOCK, END_KEYWORDS, NO_ENDS, NONE, canvas_px,
                           canvas_weight_name, has_ends,
                           is_linetype_ref, linetype_block, open_stroke,
                           resolve_ends, resolve_stroke, toggle_mirrored)
from .view_scale import scene_hit_width

_DEFAULT_FILL_PATTERN = DEFAULT_TILE_REF
# End-slot values that are never an end-block id (stroke_style.is_end_ref):
# the LT5 _item_ends fast-path gate.
_NON_ID_ENDS = frozenset((*END_KEYWORDS, BY_BLOCK, ""))
_AA = QPainter.RenderHint.Antialiasing
_log = logging.getLogger(__name__)
# Controllers whose tint lookup already failed and was logged (log once each).
_TINT_FAIL_LOGGED = weakref.WeakSet()

# Degenerate-geometry floor (mm) shared by every typed-dimension setter/spec
# that needs to reject a vanishingly short segment (2d-geometry.md §8).
_EPS_LEN = 1e-9
# Size floors the items clamp to. The constraint solver's D29 collapse check
# (sketch_adapters) imports these, so each floor has ONE home.
CIRCLE_MIN_RADIUS = 1.0     # CircleItem.set_radius
ARC_MIN_RADIUS = 0.01       # ArcItem.set_radius / solver write-back
RECT_MIN_SIZE = 1e-6        # solver write-back of a rectangle's w / h


def _manip_wraps(item) -> bool:
    """True when the scene's selection manipulator currently boxes *item*.

    Governing spec: docs/specs/selection-manipulator.md — the manipulator
    frame is the single selection boundary, so a wrapped item must NOT also
    paint its own ``isSelected()`` highlight (grip squares are drawn separately
    by Model_View and are unaffected).  Cheap and headless-safe (no view/manip
    → False, i.e. the pre-manipulator boundary still paints).
    """
    manip = getattr(item.scene(), "_manipulator", None) if item.scene() else None
    if manip is None:
        return False
    from PyQt6 import sip
    if sip.isdeleted(manip):     # scene rebuild (load/new/sheet) deleted it
        return False
    return manip.wraps(item)


def constraint_tint(item):
    """D39 tint colour for *item*'s canvas stroke (MW-12 / H-MW-g).

    Reads the scene's ``ConstraintController.tint_color`` through ``getattr``
    (tests install fake controllers without it). The ``enabled`` check is the
    non-editor fast path: plan / paper scenes never reach ``tint_color``. A
    failing lookup loses only the tint, never the item's stroke: it is
    logged once per controller and the item paints in its own colour.

    Args:
        item: The painting item (a ``Geometry2DMixin`` primitive or a
            ``BlockInstance``).

    Returns:
        The state colour to set on the painter-local pen copy, or None.
    """
    sc = item.scene()
    ctl = getattr(sc, "constraint_ctl", None) if sc is not None else None
    fn = getattr(ctl, "tint_color", None)
    if not callable(fn) or not getattr(ctl, "enabled", False):
        return None
    try:
        return fn(item)
    except Exception:
        try:
            first = ctl not in _TINT_FAIL_LOGGED
            if first:
                _TINT_FAIL_LOGGED.add(ctl)
        except TypeError:            # not weak-referenceable: log every time
            first = True
        if first:
            _log.exception("D39 tint lookup failed; painting untinted")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Geometry2DMixin
# ─────────────────────────────────────────────────────────────────────────────

def _dicts_close(a, b, tol: float = 1e-9) -> bool:
    """Structural equality with float tolerance (rel/abs *tol*)."""
    if isinstance(a, float) or isinstance(b, float):
        try:
            return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
        except (TypeError, ValueError):
            return False
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(
            _dicts_close(a[k], b[k], tol) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(
            _dicts_close(x, y, tol) for x, y in zip(a, b))
    return a == b


def _degenerate_axis(p1: QPointF, p2: QPointF) -> bool:
    """True when the mirror axis p1-p2 has (near-)zero length (DD1).

    ``CAD_Math.mirror_point`` treats such an axis as identity, but the
    per-item orientation terms (Rect / Arc / Polygon / Ellipse) would still
    flip, half-applying the reflection — so every ``manip_reflect`` is a
    no-op instead. Same 1e-12 length² threshold as ``mirror_point``."""
    dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
    return dx * dx + dy * dy < 1e-12


class Geometry2DMixin:
    """Shared level-plane placement + fill for 2D draw geometry.

    MRO: ``class X(Geometry2DMixin, DisplayableItemMixin, <QtBase>)``.
    Call ``init_displayable()`` then ``init_geometry2d()`` in ``__init__``.
    Fill fields are defined here but fill RENDERING is deferred to a later
    task — do not render fill in paint().
    """

    def init_geometry2d(self):
        """Initialise fill state.  Call after ``init_displayable(level=None)``.

        2D primitives are **definition-local and level-less** (containment C3):
        they carry no level / elevation offset — that scope lives on the placed
        BlockInstance. Only the reference-graphic ``layer`` tag + fill state live
        here.
        """
        # Source-layer tag for imported reference geometry (reference-graphic
        # unification, R1). Empty for authored primitives — a reference
        # definition batch-compiles per this tag. See
        # docs/specs/reference-graphic-model.md.
        self.layer: str = ""
        # Stable primitive id (parametric-constraint-system.md §6.1): minted at
        # creation, carried by to_dict/from_dict (undo, load, editor seed);
        # copy paths mint a new one at Model_Space._add_from_dict.
        self._uid: str = uuid.uuid4().hex
        self.fill_type: str = "none"          # "none" | "solid" | "hatch"
        self.fill_pattern: str = _DEFAULT_FILL_PATTERN
        self.fill_opacity: float = 0.45       # solid-fill opacity (0.0–1.0)
        # fill colour lives in DisplayableItemMixin._display_fill_color
        # Stroke style record (linetypes.md LT2-1): the source of truth for
        # linetype / weight / ends / authored colour. None on unstyled
        # subclasses (ReferenceLineItem, TextItem). Set by _init_stroke.
        self.style: dict | None = None
        # True while a placement ghost pen owns the pen (PolylineItem).
        self._ghost_pen: bool = False
        # The continuous stroke's crisp axis-split, by value (MW-7 / H-MW-f).
        self._mw_split_cache = _cs.SplitCache()
        # Unresolvable linetype id seen at the last paint (badge, LT3-10) and
        # the id the item's tooltip currently names (sync_missing_tooltip).
        self._lt_missing: str | None = None
        # str (a linetype id) or, while an end type is missing (LT5),
        # ``(missing_id, end_ids)`` -- linetype_render.sync_missing_tooltip.
        self._lt_tip_id: str | tuple | None = None
        # LT5: ((trims, pieces), path) of the Continuous stroke trimmed for
        # its ends, and that path's crisp split (lazy) -- an untrimmed stroke
        # never touches either (the base path keeps _mw_split_cache).
        self._end_trim_cache = None
        self._end_split_cache = None

    # Unstyled subclasses (ReferenceLineItem) set this False (LT2-1).
    _STYLED = True

    def _init_stroke(self, color, lineweight: float = 1.0) -> None:
        """Set the record from the constructor colour and the initial pen.

        *lineweight* only seeds the initial cosmetic pen (ghosts / reference
        compile); the record is Continuous / By Linetype (WM-10 factory);
        draw tools then stamp the current (``stroke_style.apply_current``).
        """
        from . import stroke_style
        hexcol = stroke_style._hex(color)
        if self._STYLED:
            self.style = stroke_style.default_style(hexcol)
        pen = QPen(QColor(hexcol))
        pen.setWidthF(lineweight)
        pen.setCosmetic(True)
        self.setPen(pen)

    def boundingRect(self) -> QRectF:
        """Qt base bounds padded to cover the cosmetic stroke at this zoom.

        Qt pads by ``widthF / 2`` in item units, but a cosmetic pen's width is
        screen px (LT2 weights reach ~18 px), so a heavy stroke zoomed out paints
        past the bounds + the view's 2 px margin and leaves trails. Pad by the
        pen half-width plus half the selection highlight's +1.5 px, converted at
        the current view zoom. Non-cosmetic (paper-pass) pens are already
        bounded correctly by the base. Subclass overrides (Rect, Arc) call
        ``super().boundingRect()`` and so inherit the pad. Stroked Qt bases
        only: ``TextItem`` (a ``QGraphicsTextItem``, no pen) measures its
        content via ``super().boundingRect()`` and must get the raw base.
        LT5: drawn ends (``_ends_rect``) grow the base first, so the pen pad
        covers their strokes too.
        """
        base = super().boundingRect()
        if not isinstance(self, (QAbstractGraphicsShapeItem, QGraphicsLineItem)):
            return base
        ends = self._item_ends()            # LT5: NO_ENDS for every end-less stroke
        if ends is not NO_ENDS:
            ends_r = self._ends_rect(ends)
            if ends_r is not None:
                base = base.united(ends_r)
        pen = self.pen()
        if not pen.isCosmetic() or pen.style() == Qt.PenStyle.NoPen:
            return base
        px = pen.widthF() / 2.0 + 0.75
        # A missing linetype (LT3-10) draws its canvas glyph at the stroke's
        # mid-length: pad for it only while the reference is unresolved,
        # decided by a registry lookup (right before the first paint; a
        # resolving linetype keeps the Continuous bounds -- manipulator frame,
        # copy base point). Flips are announced by BlockRegistry.invalidate.
        if self.style is not None:
            ref = self.style.get("linetype")
            if is_linetype_ref(ref):
                sc = self.scene()
                reg = getattr(sc, "block_registry", None) if sc is not None else None
                if linetype_block(ref, reg) is None:
                    px = max(px, badge_pad_px())
        p = scene_hit_width(self, px, px)
        return base.adjusted(-p, -p, p, p)

    def _sync_stroke_pen(self) -> None:
        """Derive the pen from the record at paint (H-c).

        Colour = the Display Manager colour if set, else ``style.colour``;
        width = the canvas px of the resolved weight; cosmetic. Skipped while a
        placement ghost owns the pen, while a paper pass has set a
        non-cosmetic pen (paper_display._apply_construction), and for the
        whole of any paper pass (``paper_display.paper_pass_active``). Unstyled items
        keep the pre-LT2 behaviour (display colour onto the pen).

        Returns:
            The LT3-8 ``ResolvedStroke`` (None for unstyled items) -- resolved
            once per paint and handed to ``_paint_routed_stroke``.
        """
        dc = getattr(self, "_display_color", None)
        if self.style is None:
            if dc:
                pen = QPen(self.pen())
                pen.setColor(QColor(dc))
                self.setPen(pen)
            return None
        rs = self._resolved_stroke()
        pen = self.pen()            # PyQt returns a copy
        if self._ghost_pen or not pen.isCosmetic():
            return rs
        if paper_pass_active():
            return rs               # paper pass owns the pen (no ping-pong)
        pen.setColor(QColor(dc or self.style["colour"]))
        pen.setWidthF(canvas_px(rs.weight))
        pen.setCosmetic(True)
        self.setPen(pen)
        return rs

    def _resolved_stroke(self):
        """LT3-8 cascade for this primitive (None for unstyled items)."""
        st = self.style
        if st is None:
            return None
        reg = None
        if is_linetype_ref(st.get("linetype")):   # only ids consult the registry
            sc = self.scene()
            reg = getattr(sc, "block_registry", None) if sc is not None else None
        return resolve_stroke(st, reg)

    def _lt_args(self) -> dict:
        """Surface inputs of ``linetype_render.length_factor`` (LT3-5)."""
        sc = self.scene()
        if sc is None:
            return {"paper_scale": None, "role": None, "drawing_scale": None}
        sm = getattr(sc, "scale_manager", None)
        return {"paper_scale": getattr(sc, "_hatch_paper_scale", None),  # viewport pass
                "role": getattr(sc, "scene_role", None),
                "drawing_scale": sm.drawing_scale if sm is not None else None}

    def _linetype_factor(self, lt, device_scale=None) -> float:
        """LT3-5 length factor (``linetype_render.length_factor``)."""
        from .linetype_render import length_factor
        return length_factor(lt, device_scale=device_scale, **self._lt_args())

    def _paint_routed_stroke(self, painter, option, widget, rs,
                             draw_highlight, lt_frame=None) -> bool:
        """The stroke + plain selection highlight of the 8 styled paints (H3-f).

        Draws through the linetype renderer when it can; otherwise the Qt
        base stroke and, when selected (and not manipulator-boxed),
        ``draw_highlight(painter)`` with the accent highlight pen set.
        *lt_frame* is the world transform the dashes draw under (Rect: the
        unrotated item frame, since its ``stroke_pieces()`` carry the
        rotation); None keeps the painter's. Returns True when dashed.
        """
        pen = self.pen()                # painter-local copy (MW-7 / MW-12)
        if rs is not None and pen.isCosmetic() and paper_pass_active():
            # No paper category reset this pen (Ellipse / Polygon / Spline):
            # its canvas width must not reach paper -- plot the frozen pre-MW
            # mapping of the resolved weight (MW-1 / MW-4).
            pen.setWidthF(paper_legacy_px(resolve_line_weight_mm(
                canvas_weight_name(rs.weight))))
        tint = constraint_tint(self)
        if tint is not None:
            pen.setColor(tint)          # pen COPY: never setPen (delta 2)
        ends = self._item_ends(rs)      # LT5: NO_ENDS = today's path, unchanged
        if ends is not NO_ENDS and has_ends(ends):
            return self._paint_stroke_with_ends(painter, option, widget, rs,
                                                ends, pen, draw_highlight)
        if rs is None or (rs.lt is None and not rs.missing_id
                          and self._lt_tip_id is None):
            self._lt_missing = None      # Continuous fast path (LT3-11)
            dashed = False
        elif lt_frame is None:
            dashed = self._paint_linetyped(painter, rs, pen)
        else:
            painter.save()
            try:
                painter.setWorldTransform(lt_frame)
                dashed = self._paint_linetyped(painter, rs, pen)
            finally:
                painter.restore()
        if dashed:
            return True
        self._paint_base_stroke(painter, option, widget, pen)
        if self.isSelected() and not _manip_wraps(self):
            highlight = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            highlight.setCosmetic(True)
            painter.setPen(highlight)
            draw_highlight(painter)
        return False

    # ── LT5 ends ─────────────────────────────────────────────────────────────

    def _ends_open(self) -> bool:
        """True when this primitive has free ends (LT5 Q2) -- the one open /
        closed rule, ``stroke_style.open_stroke``."""
        return open_stroke(self)

    def _closed_clears_ends(self) -> None:
        """A stroke that is now closed drops its explicit end ids (user
        ruling 2026-10-08): they could never draw, yet would count as uses.

        Called from the open -> closed chokepoints (``PolylineItem.close``,
        ``ArcItem._rebuild_path``, ``SplineItem._regenerate``) before the
        path is set, so the change rides the same undo step as the close.
        ``visible`` / ``mirrored`` are kept.
        """
        from .stroke_style import clear_explicit_ends, has_explicit_ends
        st = getattr(self, "style", None)
        f = getattr(self, "is_closed", None)
        if not (has_explicit_ends(st) and callable(f) and f()):
            return
        self.prepareGeometryChange()            # the ends leave the bounds
        clear_explicit_ends(st)

    def _item_ends(self, rs=None):
        """This stroke's resolved ``(start, finish)`` ends (LT5).

        ``stroke_style.NO_ENDS`` -- the pre-LT5 path, no registry work --
        for unstyled items, placement ghosts (LT3-6: the continuous base),
        By Linetype ends on a stroke whose linetype carries no default
        (every legacy drawing) and closed shapes. *rs* is this paint's
        ``ResolvedStroke`` when the caller has one.
        """
        st = self.style
        if st is None or self._ghost_pen:
            return NO_ENDS
        # Hot (every paint + boundingRect): inline, no helper calls. A slot
        # names an end only via a visible end-block id (is_end_ref); without
        # one, only a linetype default can draw -- and never when both slots
        # are "none". Returning NO_ENDS is only ever a shortcut for "the
        # resolver draws nothing"; anything else goes through resolve_ends.
        s, f = st.get("start"), st.get("finish")
        es = s.get("end") if s.__class__ is dict else None
        ef = f.get("end") if f.__class__ is dict else None
        reg = None
        if not ((es.__class__ is str and es not in _NON_ID_ENDS
                 and s.get("visible", True))
                or (ef.__class__ is str and ef not in _NON_ID_ENDS
                    and f.get("visible", True))):
            if es == NONE and ef == NONE:
                return NO_ENDS                   # both None: no lookup
            if rs is not None:                   # paint: the resolved reading
                lt = rs.lt
                if lt is None or not (lt.start_end or lt.finish_end):
                    return NO_ENDS
            else:                                # boundingRect: registry gate
                ref = st.get("linetype")
                if not is_linetype_ref(ref):
                    return NO_ENDS
                reg = self._tile_registry()
                if not _er.linetype_has_default_end(ref, reg):
                    return NO_ENDS
        if not self._ends_open():
            return NO_ENDS
        if reg is None:
            reg = self._tile_registry()
        if rs is None:
            rs = resolve_stroke(st, reg)
        return resolve_ends(st, rs.lt, reg)

    def _ends_rect(self, ends=None) -> QRectF | None:
        """Item-local bounds of the ends this item draws (LT5 / ET1), or None.

        Scale-with-zoom ends: their exact extent at this surface's printed
        factor; Fixed-size ends on a model canvas: at the screen factor for
        the current view zoom (the badge-pad convention -- the zoom hook
        re-prepares them, spec C); a missing end: the badge pad around its
        attach point. Non-cosmetic (paper) pens add half their width here
        (the Qt base only pads its own path). *ends* is the caller's
        ``_item_ends()`` when it has one.
        """
        if ends is None:
            ends = self._item_ends()
        if ends is NO_ENDS or not has_ends(ends):
            return None
        pen = self.pen()
        w = pen.widthF()
        cos = pen.isCosmetic()
        bp = badge_pad_px()
        a = self._lt_args()
        unit = scene_hit_width(self, 1.0, 1.0)          # scene units per device px
        r = _er.ends_rect(self.stroke_pieces(), ends,
                          printed=printed_factor(**a),
                          screen=_er.screen_factor(paper_scale=a["paper_scale"],
                                                   role=a["role"],
                                                   device_scale=1.0 / unit),
                          badge=scene_hit_width(self, bp, bp))
        if r is not None and not cos:
            r = r.adjusted(-w / 2.0, -w / 2.0, w / 2.0, w / 2.0)
        return r

    def _paint_stroke_with_ends(self, painter, option, widget, rs, ends, pen,
                                draw_highlight) -> bool:
        """LT5: the stroke trimmed for the resolved *ends*, then the ends.

        ``_paint_routed_stroke``'s contract (returns True when dashed). The
        stroke stops ``end_trims`` short of each end: dashes keep their
        untrimmed phase (``expand(trims=)``, D-L9 / E12); a Continuous (or
        LOD / LTS-7 short) stroke draws its cached trimmed path, a zero trim
        the unchanged base stroke. Ends draw on every surface with the
        line's painter-local pen (never LOD-dropped); the selection
        highlight covers them. Paper passes use the true-mm printed factor;
        a Fixed-size end on a model canvas the screen factor (ET1), and a
        stroke too short for its Fixed-size trims draws plain with no ends
        (Q7).
        """
        from .hatch_render import _device_scale
        pieces = self.stroke_pieces()
        a = self._lt_args()
        ff = printed_factor(**a)
        sf = _er.screen_factor(paper_scale=a["paper_scale"], role=a["role"],
                               device_scale=_device_scale(painter))
        trims = _er.end_trims(ends, printed=ff, screen=sf)
        if _er.short_on_screen(pieces, ends, trims, sf):     # ET1 Q7 (LTS-7 parity)
            trims = _er.NO_TRIMS
            ends = _er.badges_only(ends)
        miss = tuple(e.missing_id for e in ends if e.missing_id)
        dashed = self._paint_linetyped(painter, rs, pen, trims=trims, end_ids=miss)
        hl = None
        if self.isSelected() and not _manip_wraps(self):
            hl = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            hl.setCosmetic(True)
        untrimmed = trims == _er.NO_TRIMS
        if not dashed:
            if untrimmed:
                self._paint_base_stroke(painter, option, widget, pen)
            else:
                self._paint_trimmed_stroke(painter, pieces, trims, pen)
            if hl is not None:
                if untrimmed:
                    painter.setPen(hl)
                    draw_highlight(painter)
                else:
                    self._paint_trimmed_stroke(painter, pieces, trims, hl)
        sc = self.scene()
        drew = _er.paint_ends(painter, pieces, ends, pen, printed=ff, screen=sf, scene=sc)
        _er.mark_screen_ends(self, drew)
        if hl is not None:
            _er.paint_ends(painter, pieces, ends, hl, printed=ff, screen=sf,
                           scene=sc, badges=False)
        return dashed

    def _paint_trimmed_stroke(self, painter, pieces, trims, pen) -> None:
        """Stroke *pieces* cut by *trims* (LT5): the path cached per item on
        (trims, pieces); its crisp split in ``_end_split_cache`` (cosmetic
        canvas pens only -- paper / non-cosmetic draw unsplit). An
        over-trimmed stroke draws nothing (its ends still draw, Q5)."""
        key = (trims, pieces)
        c = self._end_trim_cache
        if c is None or c[0] != key:
            c = self._end_trim_cache = (key, _er.trimmed_path(pieces, *trims))
        path = c[1]
        if path.isEmpty():
            return
        painter.save()
        try:
            if self._end_split_cache is None:
                self._end_split_cache = _cs.SplitCache()
            _cs.stroke_cached(self._end_split_cache, painter, path, pen)
        finally:
            painter.restore()

    # True on single-segment items (LineItem): ``_paint_base_stroke`` takes
    # its analytic one-segment fast path (MW-13).
    _CRISP_LINE = False

    def _crisp_base_path(self) -> QPainterPath:
        """The Qt base item's own stroke geometry, item-local (MW-7)."""
        if isinstance(self, QGraphicsLineItem):
            ln = self.line()
            p = QPainterPath(ln.p1())
            p.lineTo(ln.p2())
            return p
        p = QPainterPath()
        if isinstance(self, QGraphicsRectItem):
            p.addRect(self.rect())
            return p
        if isinstance(self, QGraphicsEllipseItem):
            p.addEllipse(self.rect())
            return p
        return QPainterPath(self.path())

    def _paint_base_stroke(self, painter, option, widget, pen) -> None:
        """Continuous stroke: cosmetic pens through the crisp split (cached
        per item, H-MW-f); non-cosmetic (paper) via the unchanged Qt paint."""
        if not pen.isCosmetic():
            super().paint(painter, option, widget)
            return
        if self._CRISP_LINE and not self._ghost_pen and self.style is not None:
            # One straight segment (MW-13 fast path): classify analytically
            # from the line and the painter's 2x2 -- no path, split or cache.
            # Exactly axis (split_axis's rule, inlined: hot) draws aliased;
            # anything else under the painter's own AA hint. Paper passes
            # draw unsplit (the stroke_cached gate).
            ln = self.line()
            painter.setPen(pen)
            if not paper_pass_active() and painter.testRenderHint(_AA):
                xf = painter.worldTransform()
                dx, dy = ln.dx(), ln.dy()
                vx = dx * xf.m11() + dy * xf.m21()
                vy = dx * xf.m12() + dy * xf.m22()
                ax = vx if vx >= 0.0 else -vx
                ay = vy if vy >= 0.0 else -vy
                if (ax > 0.0 or ay > 0.0) and \
                        (ax if ax < ay else ay) <= CRISP_AXIS_TOL * math.hypot(vx, vy):
                    painter.setRenderHint(_AA, False)
                    painter.drawLine(ln)
                    painter.setRenderHint(_AA, True)
                    return
            painter.drawLine(ln)
            return
        painter.save()
        try:
            if self._ghost_pen or self.style is None:
                # Not weight-mapped (placement ghosts; unstyled reference
                # lines): outside MW-7's scope, so unsplit -- but still the
                # pen copy, so a painter-local tint reaches them (MW-12).
                _cs.stroke(painter, self._crisp_base_path(), pen, None)
            else:
                _cs.stroke_cached(self._mw_split_cache, painter,
                                  self._crisp_base_path(), pen)
        finally:
            painter.restore()

    def _paint_linetyped(self, painter, rs, pen=None, trims=(0.0, 0.0),
                         end_ids=()) -> bool:
        """Draw the stroke (+ selection highlight) through the linetype renderer.

        *rs* is this paint's ``ResolvedStroke`` (from ``_sync_stroke_pen``).
        *pen* is the painter-local stroke pen (None = ``self.pen()``).
        *trims* (LT5) drop the dashes within the end trims, phase untouched;
        *end_ids* are this paint's missing end ids for the tooltip.
        Returns False when the caller must draw its unchanged plain stroke
        (Continuous / unresolved / malformed / LOD / ghost).
        Records ``_lt_missing`` for the badge and names it in the item's
        tooltip (LT3-10).
        """
        # Ghost previews stay on the continuous base, no badge (LT3-6).
        self._lt_missing = (rs.missing_id if rs is not None and not self._ghost_pen
                            else None)
        if rs is not None and (self._lt_missing or self._lt_tip_id or end_ids):
            from .linetype_render import sync_missing_tooltip
            sync_missing_tooltip(self, self._lt_missing, end_ids=end_ids)
        if rs is None or rs.lt is None or self._ghost_pen:
            return False
        from .linetype_render import paint_stroke
        pieces = self.stroke_pieces()
        from .hatch_render import _device_scale
        factor = self._linetype_factor(rs.lt, _device_scale(painter))   # LTS-3
        from .linetype_render import fixed_on_canvas
        a = self._lt_args()
        fixed = fixed_on_canvas(rs.lt, paper_scale=a["paper_scale"], role=a["role"])
        o = self.mapFromScene(QPointF(0.0, 0.0))        # Block Editor origin (D4)
        anchor = (o.x(), o.y())
        pen = pen if pen is not None else self.pen()
        if not paint_stroke(painter, pieces, rs.lt, pen,
                            factor=factor, anchor=anchor, fixed=fixed,
                            trims=trims):
            return False
        if self.isSelected() and not _manip_wraps(self):
            hl = QPen(self.pen().color().lighter(150), self.pen().widthF() + 1.5)
            hl.setCosmetic(True)
            paint_stroke(painter, pieces, rs.lt, hl, factor=factor, anchor=anchor,
                         fixed=fixed, trims=trims)
        return True

    def _paint_lt_badge(self, painter) -> None:
        """Missing-linetype glyph at mid-length; canvas only (LT3-10)."""
        if not self._lt_missing:
            return
        from .paper_display import paper_pass_active
        if paper_pass_active():
            return
        from .linetype_render import mid_point, paint_missing_badge
        at = mid_point(self.stroke_pieces())
        if at is not None:
            paint_missing_badge(painter, at)

    def _set_style_field(self, key: str, value) -> None:
        """Apply a panel style edit to the record (LT2-7), then repaint.

        For ``"Linetype"`` *value* is the resolved ref (``continuous`` or a
        linetype block id -- ``linetype_ref_from_value``).
        """
        from .stroke_style import _hex, weight_from_label
        v = str(value)
        if key == "Linetype":
            self.prepareGeometryChange()     # badge pad follows the linetype ref
            self.style["linetype"] = v
        elif key == "Weight":
            self.style["weight"] = weight_from_label(v)
        else:
            self.style["colour"] = _hex(v)
        self._sync_stroke_pen()
        self.update()

    def _set_linetype_from_panel(self, value: str) -> None:
        """Apply a panel Linetype pick (LT3-12; mirrors the D-A36/D-A37
        Pattern pick).

        A ``"Missing (<id>)"`` label or an unknown label changes nothing (the
        stored ref is never rewritten). A Linetypes-folder linetype is loaded
        into the project first: the ref is set BEFORE the load so the load's
        one undo snapshot carries it, and a failed load restores the old ref.
        Any other pick is one undo step via ``_dim_edit``.
        """
        from .hatch_patterns import picker_exclude
        from .linetype_choices import (ensure_linetype_available,
                                       is_missing_label,
                                       linetype_ref_from_value)
        from .stroke_style import is_linetype_ref
        if is_missing_label(value):
            return                            # LT3-10: never rewrite a missing ref
        reg = self._tile_registry()
        ref = linetype_ref_from_value(value, reg, picker_exclude(self.scene()))
        if ref is None:
            return
        if is_linetype_ref(ref) and reg is not None and reg.get(ref) is None:
            old = self.style["linetype"]
            self._set_style_field("Linetype", ref)
            if not ensure_linetype_available(ref, self.scene()):
                self._set_style_field("Linetype", old)
            return
        self._dim_edit(lambda r: self._set_style_field("Linetype", r), ref)

    def _set_end_field(self, which: str, field: str, value) -> None:
        """Write one end-record field (LT5 Q10), keeping the others
        (``mirrored`` included) and normalising through the record helper
        (ET1: a 1x Scale drops its key in memory too), then repaint (bounds
        cover the ends)."""
        self.prepareGeometryChange()
        rec = dict(self.style[which])
        rec[field] = value
        from .stroke_style import _end
        self.style[which] = _end(rec)
        self._sync_stroke_pen()
        self.update()

    def _set_end_from_panel(self, key: str, value) -> None:
        """Apply a Start End / Finish End / Visible panel edit (LT5 Q10).

        One undo step via ``_dim_edit``. A ``"Missing: ..."`` or unknown
        label changes nothing. An End Types folder end is loaded into the
        project first: the ref is set BEFORE the load so the load's one
        snapshot carries it; a failed load restores the old ref. In a Block
        Editor the load's step lives in the project scene, so the editor
        pushes its own step (one per scene). Locked inside an end type (Q8).
        """
        sc = self.scene()
        if _ends_lock_tip(sc) is not None:
            return                     # Q8 / I3: capability content is plain
        which, field = _END_ROW_KEYS[key]
        if field == "visible":
            on = value if isinstance(value, bool) else str(value) in (
                "True", "true", "1")
            self._dim_edit(lambda v: self._set_end_field(which, "visible", v),
                           bool(on))
            return
        from .capabilities import end_ref_from_value, ensure_end_available
        from .hatch_patterns import picker_exclude
        from .stroke_style import is_end_ref
        reg = self._tile_registry()
        ref = end_ref_from_value(value, reg, picker_exclude(sc))
        if ref is None:
            return
        if is_end_ref(ref) and reg is not None and reg.get(ref) is None:
            old = self.style[which]["end"]
            self._set_end_field(which, "end", ref)
            if not ensure_end_available(ref, sc):
                self._set_end_field(which, "end", old)
                return
            owner = getattr(sc, "_block_registry_owner", None)
            if owner is not None and owner is not sc:
                self._push_undo()                  # the editor's own step
            return
        self._dim_edit(lambda r: self._set_end_field(which, "end", r), ref)

    def is_fillable(self) -> bool:
        """True if this item has a closed path (rectangle, circle, closed polyline)."""
        gcp = getattr(self, "get_closed_path", None)
        return gcp is not None and gcp() is not None

    def _g2d_sm(self):
        sc = self.scene()
        return getattr(sc, "scale_manager", None) if sc else None

    def _tile_registry(self):
        """The block registry pattern pickers resolve project tiles through."""
        sc = self.scene()
        return getattr(sc, "block_registry", None) if sc else None

    def _parse_dim(self, value):
        """Parse a display-formatted or raw numeric value to mm (float or None)."""
        if isinstance(value, (int, float)):
            return float(value)
        sm = self._g2d_sm()
        if sm is not None:
            try:
                return sm.parse_dimension(str(value))
            except Exception:
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _fmt(self, mm: float) -> str:
        """Format *mm* as a display string using the scene ScaleManager."""
        sm = self._g2d_sm()
        return sm.format_length(mm) if sm else f"{mm:.1f}"

    def dimension_specs(self) -> list:
        """Selection dimension readouts this primitive reports (2d-geometry §8).

        Default: none (Text, Spline). Pure — never owns or paints anything.
        """
        return []

    def _push_undo(self) -> None:
        """One scene undo step after a typed dimension edit (mutate-then-push).

        Routed through ``Model_Space.request_undo_push`` so a multi-target
        panel commit (``PropertyManager._apply_property`` inside
        ``scene.deferred_undo_push()``) coalesces into ONE step.
        """
        sc = self.scene()
        if sc is None:
            return
        req = getattr(sc, "request_undo_push", None)
        if callable(req):
            req()
        elif hasattr(sc, "push_undo_state"):
            sc.push_undo_state()

    def _dim_edit(self, setter, value) -> None:
        """Panel dimension edit: ``setter(value)``, then one undo step —
        skipped when the edit changed nothing (a no-op commit is no step)."""
        before = self.to_dict()
        setter(value)
        if not _dicts_close(before, self.to_dict()):
            self._push_undo()

    def _geom2d_properties(self) -> dict:
        # Level-less (containment C3): no Level / Level Offset / Elevation rows.
        props: dict = {}
        if self.style is not None:
            from .hatch_patterns import picker_exclude
            sc = self.scene()
            in_end = getattr(sc, "block_end", None) is not None
            props.update(stroke_rows(
                self.style, self._tile_registry(), picker_exclude(sc),
                locked=in_end or getattr(sc, "block_repeat", None) is not None,
                locked_tip=_LOCKED_END_LINETYPE_TIP if in_end else None,
                ends=self._ends_open(), ends_locked_tip=_ends_lock_tip(sc)))
            props["Colour"] = {"type": "color", "value": self.style["colour"]}
        if self.is_fillable():
            props["Fill"] = {"type": "enum",
                             "options": ["none", "solid", "hatch"],
                             "value": self.fill_type}
            if self.fill_type == "hatch":
                from .hatch_patterns import (MISSING_PATTERN_LABEL, canonical_ref,
                                             picker_exclude, tile_choices)
                reg = self._tile_registry()
                choices = tile_choices(reg, picker_exclude(self.scene()))
                options = [n for n, _ in choices]
                ref = canonical_ref(self.fill_pattern)
                value = next((n for n, r in choices if r == ref), None)
                if value is None:
                    # D-A36: an unresolvable stored ref shows as missing (not as
                    # the first option) and is kept until the user picks one.
                    options = [MISSING_PATTERN_LABEL] + options
                    value = MISSING_PATTERN_LABEL
                props["Pattern"] = {"type": "enum", "options": options,
                                    "value": value}
            if self.fill_type in ("solid", "hatch"):
                props["Fill Colour"] = {"type": "color",
                                        "value": self._display_fill_color or "#888888"}
            if self.fill_type == "solid":
                props["Fill Opacity"] = {
                    "type":  "string",
                    "value": str(round(self.fill_opacity * 100)),
                    "suffix": "%",
                }
        return props

    def _geom2d_set(self, key: str, value) -> bool:
        """Handle a property set for mixin-owned keys.  Returns True if consumed."""
        if self.style is not None and key in _END_ROW_KEYS:
            self._set_end_from_panel(key, value)
            return True
        if self.style is not None and key == "Linetype":
            self._set_linetype_from_panel(str(value))
            return True
        if self.style is not None and key in ("Weight", "Colour"):
            if key == "Weight" and _is_block_only_weight_label(value):
                return True                    # WM2 Q5: not a primitive value
            self._dim_edit(lambda v: self._set_style_field(key, v), value)
            return True
        if key == "Fill":
            self.fill_type = str(value)
            self.update()
            return True
        if key == "Pattern":
            from .hatch_patterns import (MISSING_PATTERN_LABEL, picker_exclude,
                                         ref_from_value, ensure_pattern_available)
            if str(value) == MISSING_PATTERN_LABEL:
                return True               # D-A36: never rewrite the stored ref
            old = self.fill_pattern
            self.fill_pattern = ref_from_value(str(value), self._tile_registry(),
                                               picker_exclude(self.scene()))
            # D-A37: a library pattern loads into the project first. Set before
            # the load so its one undo snapshot carries the new ref too; a
            # failed load keeps the stored ref.
            if not ensure_pattern_available(self.fill_pattern, self.scene()):
                self.fill_pattern = old
            self.update()
            return True
        if key == "Fill Colour":
            self._display_fill_color = str(value)
            self.update()
            return True
        if key == "Fill Opacity":
            try:
                pct = float(value)
            except (TypeError, ValueError):
                return True  # reject non-numeric; keep prior
            pct = max(0.0, min(100.0, pct))
            self.fill_opacity = pct / 100.0
            self.update()
            return True
        return False

    def _geom2d_to_dict(self, d: dict) -> dict:
        """Stamp mixin fields onto *d* and return it (level-less — C3)."""
        d["uid"] = self._uid
        if self.style is not None:
            from .stroke_style import normalize_style
            d.pop("color", None)
            d.pop("lineweight", None)
            d["style"] = normalize_style(self.style)
        if getattr(self, "layer", ""):
            d["layer"] = self.layer
        if self.fill_type != "none":
            d["fill"] = {
                "type":    self.fill_type,
                "pattern": self.fill_pattern,
                "color":   self._display_fill_color or "#888888",
                "opacity": self.fill_opacity,
            }
        return d

    def _geom2d_from_dict(self, data: dict):
        """Restore mixin fields from *data* (level-less — C3).

        Pre-C3 dicts may carry ``level``/``level_offset_mm``; they are ignored.
        A legacy dict without ``uid`` keeps the uid minted at construction.
        """
        uid = data.get("uid")
        if uid:
            self._uid = str(uid)
        if self._STYLED and self.style is not None:
            from .stroke_style import default_style, normalize_style
            # Always a fresh record (never the caller's dict), independent of
            # data["type"]; a legacy dict migrates from "color" (D-L17a).
            raw = data.get("style")
            st = (normalize_style(raw) if isinstance(raw, dict)
                  else default_style(data.get("color") or "#ffffff"))
            self.style = st
            pen = QPen(self.pen())
            pen.setColor(QColor(st["colour"]))
            pen.setWidthF(1.0)                      # px dropped (D-L17a)
            pen.setCosmetic(True)
            self.setPen(pen)
        self.layer = data.get("layer", "")
        f = data.get("fill")
        if f:
            self.fill_type = f.get("type", "none")
            from .hatch_patterns import canonical_ref
            self.fill_pattern = canonical_ref(f.get("pattern", _DEFAULT_FILL_PATTERN))
            self._display_fill_color = f.get("color")
            self.fill_opacity = f.get("opacity", 0.45)


def _scene_hit_width(item) -> float:
    """~10 screen px at the visible view's zoom (see view_scale)."""
    return scene_hit_width(item, 10.0, 6.0)


# ─────────────────────────────────────────────────────────────────────────────
# PolylineItem
# ─────────────────────────────────────────────────────────────────────────────

class PolylineItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """
    A multi-segment polyline (optionally flagged closed via `close()`) drawn by successive mouse clicks.

    The path is rebuilt each time a new point is appended so the
    partial line is always visible in the scene.

    Parameters
    ----------
    color : str | QColor
        Stroke color, typically derived from the active user layer.
    lineweight : float
        Cosmetic pixel width (default 1.0).
    """

    def __init__(self, start: QPointF, color: str | QColor = "#ffffff",
                 lineweight: float = 1.0):
        super().__init__()
        self._points: list[QPointF] = [start]
        self._closed: bool = False

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        self._init_stroke(color, lineweight)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._lineweight = lineweight   # restored (solid) by finalize() after a dashed ghost
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self._rebuild_path()

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type": {"type": "label", "value": "Polyline"},
            "Vertices": {"type": "label", "value": str(len(self._points))},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if self._geom2d_set(key, value):
            return

    # ── Public API ────────────────────────────────────────────────────────────

    def append_point(self, pt: QPointF):
        """Add the next vertex and rebuild the path."""
        self._points.append(pt)
        self._rebuild_path()

    def last_point(self) -> QPointF:
        """The most recently placed vertex (placement rubber-band anchor).

        Returns:
            A copy of the last vertex. Callers guard the empty case.
        """
        return QPointF(self._points[-1])

    def update_preview(self, pt: QPointF):
        """Temporarily extend path to *pt* for the cursor-follow preview."""
        # Rebuild with the tentative last point
        path = QPainterPath(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        path.lineTo(pt)
        if self._closed and len(self._points) >= 3:
            path.closeSubpath()
        self.setPath(path)

    def finalize(self):
        """Snap the path to the committed points and stop accepting input.

        Restores the committed SOLID pen at the item's lineweight — during
        placement the polyline is ghosted in the width-1 dashed reference style
        (set by ``_press_polyline``); a finalized polyline renders solid.
        """
        p = QPen(self.pen())
        p.setStyle(Qt.PenStyle.SolidLine)
        p.setWidthF(getattr(self, "_lineweight", 1.0))
        self.setPen(p)
        self._ghost_pen = False
        self._rebuild_path()

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """Return all vertex positions as grip handles (one per vertex)."""
        return list(self._points)

    def apply_grip(self, index: int, pos: QPointF):
        """Move vertex *index* to *pos* and rebuild the path."""
        if 0 <= index < len(self._points):
            self._points[index] = pos
            self._rebuild_path()

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def _seg_indices(self) -> list[int]:
        n = len(self._points)
        return list(range(n)) if self.is_closed() else list(range(max(n - 1, 0)))

    def _seg_len(self, i: int) -> float:
        a, b = self._points[i], self._points[(i + 1) % len(self._points)]
        return math.hypot(b.x() - a.x(), b.y() - a.y())

    def _vertex_sweep(self, i: int):
        """(start_deg, span_deg, ccw) of the <=180° angle at vertex *i*;
        ccw=True when the next leg is CCW of the previous one."""
        from .arc_math import yup_angle
        n = len(self._points)
        v = self._points[i]
        a_prev = yup_angle(v, self._points[(i - 1) % n])
        a_next = yup_angle(v, self._points[(i + 1) % n])
        inc = (a_next - a_prev) % 360.0
        if inc <= 180.0:
            return a_prev, inc, True
        return a_next, 360.0 - inc, False

    def set_segment_length(self, i: int, length_mm: float) -> None:
        """Set segment *i*'s length, moving only its end vertex (wraps).

        No-op for a non-finite/non-positive length, a degenerate segment, or
        an *i* outside the current segment set (index robustness — this is
        called from paint-adjacent HUD/readout code, so it must never raise).
        """
        if not math.isfinite(length_mm) or length_mm <= 0:
            return
        n = len(self._points)
        if not (0 <= i < n) or i not in self._seg_indices():
            return
        j = (i + 1) % n
        a, b = self._points[i], self._points[j]
        cur = math.hypot(b.x() - a.x(), b.y() - a.y())
        if cur < _EPS_LEN:
            return
        k = length_mm / cur
        self._points[j] = QPointF(a.x() + (b.x() - a.x()) * k,
                                  a.y() + (b.y() - a.y()) * k)
        self._rebuild_path()

    def set_vertex_angle(self, i: int, theta_deg: float) -> None:
        """Set the <=180° angle at vertex *i* by rotating vertex (i+1)%n about
        it (same side kept). Clamped to (0, 180].

        No-op for a non-finite angle, too few vertices, an *i* outside
        [0, n), or (open polyline) an *i* that is not an interior vertex —
        index robustness (see :meth:`set_segment_length`).
        """
        if not math.isfinite(theta_deg):
            return
        n = len(self._points)
        if n < 3 or not (0 <= i < n):
            return
        if not self.is_closed() and not (0 < i < n - 1):
            return
        theta = min(max(float(theta_deg), 1e-6), 180.0)
        v = self._points[i]
        j = (i + 1) % n
        from .arc_math import yup_angle
        a_prev = yup_angle(v, self._points[(i - 1) % n])
        a_next = yup_angle(v, self._points[j])
        _, _, ccw = self._vertex_sweep(i)
        target = a_prev + theta if ccw else a_prev - theta
        d = math.radians(target - a_next)
        dx, dy = self._points[j].x() - v.x(), self._points[j].y() - v.y()
        c, s = math.cos(d), math.sin(d)
        self._points[j] = QPointF(v.x() + dx * c + dy * s,
                                  v.y() - dx * s + dy * c)
        self._rebuild_path()

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        n = len(self._points)
        if n < 2:
            return []
        specs = []
        zero = set()
        for i in self._seg_indices():
            seg_len = self._seg_len(i)
            if not math.isfinite(seg_len) or seg_len < _EPS_LEN:
                zero.update({i, (i + 1) % n})
                continue
            j = (i + 1) % n
            specs.append(DimSpec(
                kind="linear", key=f"seg:{i}", field=f"Seg {i + 1}", prefix="",
                value=seg_len, field_kind="dimension",
                apply=lambda v, i=i: self.set_segment_length(i, v),
                a=QPointF(self._points[i]), b=QPointF(self._points[j])))
        verts = range(n) if self.is_closed() else range(1, n - 1)
        for i in verts:
            if i in zero:
                continue
            start, span, _ = self._vertex_sweep(i)
            # Doubled-back vertex (the outgoing leg folds back onto the
            # incoming one): a degenerate ~0° angle, skip it.
            if not math.isfinite(span) or span < 1e-6:
                continue
            leg = min(self._seg_len((i - 1) % n), self._seg_len(i))
            specs.append(DimSpec(
                kind="angular", key=f"ang:{i}", field=f"Angle {i + 1}", prefix="",
                value=span, field_kind="span",
                apply=lambda v, i=i: self.set_vertex_angle(i, v),
                maximum=180.0, center=QPointF(self._points[i]),
                ref_radius=leg, start_deg=start, span_deg=span))
        return specs

    def manip_handles(self):
        """U3: expose each vertex as a live-apply grip. All grips are
        vertices (no midpoint/convenience grips), so all render round per the
        house rule (vertex/endpoint grips = round disc; midpoints = square).
        S3a: under Ctrl a vertex grip angle-constrains against the PREVIOUS
        vertex; an open polyline's start vertex constrains against the next
        one, and a closed polyline wraps (vertex 0 against n−1)
        (``vertex_chain_grip_handles``). Move is the manipulator's
        interior-drag (no centre grip). The manipulator renders/hit-tests/
        commits them; the legacy grip paths skip this item (coexistence gate)."""
        from .manip_handle import vertex_chain_grip_handles
        return vertex_chain_grip_handles(self, closed=self.is_closed())

    def translate(self, dx: float, dy: float):
        """Move all vertices by (dx, dy)."""
        self._points = [QPointF(p.x() + dx, p.y() + dy) for p in self._points]
        self._rebuild_path()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate of all vertices about ``pivot`` (Y-up CCW+)."""
        from .cad_math import CAD_Math
        self._points = [CAD_Math.rotate_point(p, pivot, -angle_deg)
                        for p in self._points]
        self._rebuild_path()

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror of every vertex across the infinite line p1-p2 (DD1).

        Closed flag and fill are untouched (the item is edited in place)."""
        if _degenerate_axis(p1, p2):
            return              # zero-length axis: no-op, never half-applied
        from .cad_math import CAD_Math
        self._points = [CAD_Math.mirror_point(p, p1, p2) for p in self._points]
        self._rebuild_path()
        toggle_mirrored(self.style)          # LT5 Q9

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale of every vertex about ``base`` (DD1).

        Not ``manip_scale``: that name makes the manipulator treat the item
        as box-resizable (``item_capabilities``)."""
        from .cad_math import CAD_Math
        self._points = [CAD_Math.scale_point(p, base, factor)
                        for p in self._points]
        self._rebuild_path()

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Return True if this polyline is flagged closed (≥3 vertices)."""
        return self._closed and len(self._points) >= 3

    def close(self):
        """Flag the polyline closed (needs ≥3 vertices).  Idempotent."""
        if len(self._points) >= 3:
            self._closed = True
            self._closed_clears_ends()            # LT5: closed -> no ends
            self._rebuild_path()

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetypes.md LT3 H3-b)."""
        from .path_walk import Seg
        pts = self._points
        segs = [Seg(a.x(), a.y(), b.x(), b.y()) for a, b in zip(pts, pts[1:])]
        if self.is_closed():
            segs.append(Seg(pts[-1].x(), pts[-1].y(), pts[0].x(), pts[0].y()))
        return tuple(segs)

    def get_closed_path(self) -> QPainterPath | None:
        """Return a closed QPainterPath if flagged closed, else None."""
        if not self.is_closed():
            return None
        poly = QPolygonF(self._points)
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        return path

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":       "polyline",
            "points":     [[p.x(), p.y()] for p in self._points],
            "closed":     self._closed,
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "PolylineItem":
        pts = [QPointF(p[0], p[1]) for p in data["points"]]
        color = data.get("color", "#ffffff")
        lw = data.get("lineweight", 1.0)
        closed = data.get("closed")
        if closed is None:
            # Legacy: closure was a duplicated last vertex coincident with the
            # first.  Detect, flag closed, and drop the duplicate.
            if (len(pts) >= 4
                    and abs(pts[0].x() - pts[-1].x()) < 1e-3
                    and abs(pts[0].y() - pts[-1].y()) < 1e-3):
                pts = pts[:-1]
                closed = True
            else:
                closed = False
        obj = cls(pts[0], color, lw)
        for p in pts[1:]:
            obj.append_point(p)
        obj._closed = bool(closed)
        obj._geom2d_from_dict(data)
        obj._rebuild_path()
        return obj

    # ── Internal ─────────────────────────────────────────────────────────────

    def _rebuild_path(self):
        if not self._points:
            return
        path = QPainterPath(self._points[0])
        for p in self._points[1:]:
            path.lineTo(p)
        if self._closed and len(self._points) >= 3:
            path.closeSubpath()
        self.setPath(path)

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Derive the pen from the style record (+ display colour).
        rs = self._sync_stroke_pen()
        # Draw fill FIRST (behind the outline)
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)),
                          to_scene=self.sceneTransform())
        self._paint_routed_stroke(painter, option, widget, rs,
                                  lambda p: p.drawPath(self.path()))
        self._paint_lt_badge(painter)

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a viewport-scale-aware stroked path so thin polylines are clickable.

        When the polyline is closed and filled, the interior is also included
        so the shape is interior-clickable.
        """
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                path = path.united(cp)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# LineItem  — finite 2-point line (AutoCAD-style Line tool)
# ─────────────────────────────────────────────────────────────────────────────

class LineItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsLineItem):
    """
    A finite 2-point line with configurable colour and lineweight.

    Parameters
    ----------
    pt1, pt2    : QPointF  — start and end points
    color       : str | QColor — stroke colour (default white for dark theme)
    lineweight  : float — cosmetic pixel width (default 1.0)
    """

    _CRISP_LINE = True      # one segment: _paint_base_stroke fast path (MW-13)

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._pt1 = pt1
        self._pt2 = pt2

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        self._init_stroke(color, lineweight)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        self.setLine(pt1.x(), pt1.y(), pt2.x(), pt2.y())

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type": {"type": "label", "value": "Line"},
            "Length": {"type": "dimension", "value": self._fmt(self.line().length()),
                       "value_mm": self.line().length(), "minimum": 0.0},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "Length":
            v = self._parse_dim(value)
            if v is not None and v > 0:
                self._dim_edit(self.set_length, v)
            return
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":        "draw_line",
            "pt1":         [self._pt1.x(), self._pt1.y()],
            "pt2":         [self._pt2.x(), self._pt2.y()],
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "LineItem":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        """Return [pt1, midpoint, pt2] as grip handles."""
        mid = QPointF((self._pt1.x() + self._pt2.x()) / 2,
                      (self._pt1.y() + self._pt2.y()) / 2)
        return [self._pt1, mid, self._pt2]

    def apply_grip(self, index: int, pos: QPointF):
        """Move a grip handle to *pos*.  index 0=pt1, 1=midpoint, 2=pt2."""
        if index == 0:
            self._pt1 = pos
        elif index == 1:
            # Mid-grip: translate entire line
            dx = pos.x() - (self._pt1.x() + self._pt2.x()) / 2
            dy = pos.y() - (self._pt1.y() + self._pt2.y()) / 2
            self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
            self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        elif index == 2:
            self._pt2 = pos
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_length(self, length_mm: float) -> None:
        """Set the length, keeping ``pt1`` and the direction. No-op if <= 0
        or the line is degenerate."""
        if not math.isfinite(length_mm):
            return
        dx = self._pt2.x() - self._pt1.x()
        dy = self._pt2.y() - self._pt1.y()
        cur = math.hypot(dx, dy)
        if length_mm <= 0 or cur < _EPS_LEN:
            return
        k = length_mm / cur
        self._pt2 = QPointF(self._pt1.x() + dx * k, self._pt1.y() + dy * k)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        length = math.hypot(self._pt2.x() - self._pt1.x(),
                            self._pt2.y() - self._pt1.y())
        if not math.isfinite(length) or length < _EPS_LEN:
            return []
        return [DimSpec(kind="linear", key="length", field="Length", prefix="",
                        value=length, field_kind="dimension",
                        apply=self.set_length, minimum=0.0,
                        a=QPointF(self._pt1), b=QPointF(self._pt2))]

    def manip_handles(self):
        """U3: [pt1, midpoint, pt2] as live-apply grips. Endpoints (0, 2) render
        round and Ctrl-angle-constrain against the opposite endpoint
        (EndpointGripHandle); the midpoint (1) also renders round — it translates
        the whole line, so it is a move grip (round per the house rule), not a
        geometric midpoint — with a plain GripHandle (no constrain, matching the
        legacy path, which only constrained endpoint grips). The manipulator
        renders/hit-tests/commits them; the legacy grip paths skip this item
        (coexistence gate)."""
        from .manip_handle import EndpointGripHandle, TranslateGripHandle
        return [
            EndpointGripHandle(self, 0, opposite_index=2, circular=True),
            TranslateGripHandle(self, 1, circular=True),   # S2 handle snap
            EndpointGripHandle(self, 2, opposite_index=0, circular=True),
        ]

    def translate(self, dx: float, dy: float):
        """Move the entire line by (dx, dy)."""
        self._pt1 = QPointF(self._pt1.x() + dx, self._pt1.y() + dy)
        self._pt2 = QPointF(self._pt2.x() + dx, self._pt2.y() + dy)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate of both endpoints about ``pivot`` (Y-up CCW+)."""
        from .cad_math import CAD_Math
        self._pt1 = CAD_Math.rotate_point(self._pt1, pivot, -angle_deg)
        self._pt2 = CAD_Math.rotate_point(self._pt2, pivot, -angle_deg)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror of both endpoints across the infinite line p1-p2 (DD1).
        Inherited by ``ReferenceLineItem`` (type, printed flag and the dashed
        reference pen are kept: the item is edited in place)."""
        if _degenerate_axis(p1, p2):
            return              # zero-length axis: no-op, never half-applied
        from .cad_math import CAD_Math
        self._pt1 = CAD_Math.mirror_point(self._pt1, p1, p2)
        self._pt2 = CAD_Math.mirror_point(self._pt2, p1, p2)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())
        toggle_mirrored(self.style)          # LT5 Q9 (no-op unstyled)

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale of both endpoints about ``base`` (DD1).
        Not ``manip_scale`` (see ``item_capabilities``)."""
        from .cad_math import CAD_Math
        self._pt1 = CAD_Math.scale_point(self._pt1, base, factor)
        self._pt2 = CAD_Math.scale_point(self._pt2, base, factor)
        self.setLine(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y())

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Lines are never closed shapes."""
        return False

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetypes.md LT3 H3-b)."""
        from .path_walk import Seg
        return (Seg(self._pt1.x(), self._pt1.y(), self._pt2.x(), self._pt2.y()),)

    def get_closed_path(self) -> None:
        """Lines have no closed path."""
        return None

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Derive the pen from the style record (+ display colour).
        rs = self._sync_stroke_pen()
        self._paint_routed_stroke(painter, option, widget, rs,
                                  lambda p: p.drawLine(self.line()))
        self._paint_lt_badge(painter)

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a viewport-scale-aware stroked path so the line is easily clickable."""
        path = QPainterPath()
        path.moveTo(self._pt1)
        path.lineTo(self._pt2)
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        return stroker.createStroke(path)


# ─────────────────────────────────────────────────────────────────────────────
# ReferenceLineItem — non-printing finite reference/construction line
# ─────────────────────────────────────────────────────────────────────────────

class ReferenceLineItem(LineItem):
    """A finite 2-point *reference* line: a non-printing drafting aid.

    Subclasses :class:`LineItem`, inheriting all grip/manipulator/translate/
    rotate behaviour AND snap participation for free (the snap engine matches
    ``isinstance(item, LineItem)``). Differences:

    * Always rendered in the canonical width-1 dashed reference style.
    * Carries a per-item ``printed`` flag (default False). ``printed=False``
      excludes it from paper-space plots/exports AND from a block's rendered
      / exploded output (pure scaffolding — still saved in the definition and
      re-seeded on reopen, D23); ``printed=True`` graduates it to real
      output geometry (still dashed).
    * Its own "Reference Lines" Display-Manager category.
    """

    # Unstyled (LT2-1): fixed reference style, keeps color/lineweight keys.
    _STYLED = False

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0,
                 printed: bool = False):
        super().__init__(pt1, pt2, color, lineweight)
        self.printed = bool(printed)
        # Canonical reference-line style: width-1 dashed cosmetic, geom colour.
        pen = QPen(QColor(color) if isinstance(color, str) else color)
        pen.setWidthF(1.0)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)

    # ── Properties ────────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type": {"type": "label", "value": "Reference Line"},
            "Colour": {"type": "label", "value": self.pen().color().name()},
            "Length": {"type": "dimension", "value": self._fmt(self.line().length()),
                       "value_mm": self.line().length(), "minimum": 0.0},
            "Printed": {"type": "toggle", "value": bool(self.printed)},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "Printed":
            self.printed = bool(value)
            self.update()
            return
        if key == "Length":
            v = self._parse_dim(value)
            if v is not None and v > 0:
                self._dim_edit(self.set_length, v)
            return
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":        "reference_line",
            "pt1":         [self._pt1.x(), self._pt1.y()],
            "pt2":         [self._pt2.x(), self._pt2.y()],
            "color":       self.pen().color().name(),
            "lineweight":  self.pen().widthF(),
            "printed":     bool(self.printed),
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "ReferenceLineItem":
        pt1 = QPointF(data["pt1"][0], data["pt1"][1])
        pt2 = QPointF(data["pt2"][0], data["pt2"][1])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0), data.get("printed", False))
        obj._geom2d_from_dict(data)
        return obj


# ─────────────────────────────────────────────────────────────────────────────
# RectangleItem  — axis-aligned rectangle (two corner clicks)
# ─────────────────────────────────────────────────────────────────────────────

class RectangleItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsRectItem):
    """
    An axis-aligned rectangle defined by two opposite corners.

    Parameters
    ----------
    pt1, pt2    : QPointF — opposite corners (order does not matter)
    color       : str | QColor
    lineweight  : float — cosmetic pixel width
    """

    def __init__(self, pt1: QPointF, pt2: QPointF,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        rect = QRectF(pt1, pt2).normalized()
        super().__init__(rect)

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        self._init_stroke(color, lineweight)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

        # Rotation state (baked-at-rest — selection-manipulator.md).  The rect
        # stays axis-aligned in local coords; the rotation is stored as DATA
        # (``_angle``/``_pivot``), NOT a held Qt item transform.  ``rotation()``
        # is always 0 at rest.  ``_pivot`` is None when the origin should track
        # the rect centre on resize; an explicit pivot is stored and left fixed.
        # paint/shape/boundingRect/grip_points and the map* overrides all read
        # the rotation from ``_rotation_transform()`` so the rendered/hit
        # footprint matches the old held-transform footprint byte-for-byte.
        self._angle: float = 0.0
        self._pivot: QPointF | None = None

    # ── Rotation ───────────────────────────────────────────────────────────

    def set_angle(self, angle_deg: float, pivot: "QPointF | None" = None) -> None:
        """Rotate the rectangle to ``angle_deg`` (from +x) about ``pivot``.

        Bake-at-rest: the angle/pivot are stored as DATA — NO Qt item transform
        is applied (``rotation()`` stays 0).  ``paint``/``shape``/``boundingRect``
        and the ``mapToScene``/``mapFromScene``/``mapRectToScene`` overrides read
        this state so the rotated rect renders and hit-tests exactly as the old
        ``setRotation``/``setTransformOriginPoint`` path did.  ``pivot`` defaults
        to the rect centre (tracked on resize when ``_pivot is None``).
        """
        self._angle = float(angle_deg)
        if pivot is not None:
            self._pivot = QPointF(pivot)
        else:
            self._pivot = None          # origin follows rect centre on resize
        # Data-only: drop any held transform (a load path or legacy caller may
        # have left one) and refresh the cached rotated footprint.
        self.prepareGeometryChange()
        self.update()

    # ── Rotation helpers (data-only footprint) ────────────────────────────

    def _rotation_origin(self) -> QPointF:
        """Resolved rotation pivot: the explicit ``_pivot`` or the rect centre."""
        return QPointF(self._pivot) if self._pivot is not None else self.rect().center()

    def _rotation_transform(self) -> QTransform:
        """Local→scene rotation matrix equivalent to the retired held transform.

        Mirrors the old ``setRotation(-_angle)`` about the resolved pivot: a
        Y-up CCW ``_angle`` becomes Qt's CW-positive ``rotate(-_angle)`` about
        the origin.  Identity at angle 0, so unrotated rects keep the plain
        local==scene contract.
        """
        m = QTransform()
        if self._angle == 0.0:
            return m
        o = self._rotation_origin()
        m.translate(o.x(), o.y())
        m.rotate(-self._angle)          # Y-up CCW → Qt CW negate
        m.translate(-o.x(), -o.y())
        return m

    # ── map* overrides (route rotation through data, not a held transform) ──

    def mapToScene(self, *args):
        """Local→scene through the data rotation (item pos is identity).

        Overridden so external callers that historically relied on the held Qt
        rotation (snap_engine, tool_geometry, grip_points…) keep working after
        the bake-at-rest migration.  Accepts the same overloads used in-tree:
        a ``QPointF``, an ``(x, y)`` pair, or a ``QPainterPath``.
        """
        t = self._rotation_transform()
        if len(args) == 2:                       # (x, y)
            return t.map(QPointF(args[0], args[1]))
        obj = args[0]
        if isinstance(obj, QPainterPath):
            return t.map(obj)
        return t.map(QPointF(obj))

    def mapToParent(self, *args):
        """Local→parent through the data rotation, then Qt's own pos/transform.

        Overridden like :meth:`mapToScene` so ``mapToParent`` consumers (e.g.
        ``BlockDefinition._compile``) see the rotated footprint instead of the
        axis-aligned local ``rect()``.  Same overloads: ``QPointF``, ``(x, y)``
        or ``QPainterPath``.
        """
        t = self._rotation_transform()
        if len(args) == 2:                       # (x, y)
            return super().mapToParent(t.map(QPointF(args[0], args[1])))
        obj = args[0]
        if isinstance(obj, QPainterPath):
            return super().mapToParent(t.map(obj))
        return super().mapToParent(t.map(QPointF(obj)))

    def mapFromScene(self, *args):
        """Scene→local inverse of :meth:`mapToScene`."""
        inv, ok = self._rotation_transform().inverted()
        if not ok:
            inv = QTransform()
        if len(args) == 2:
            return inv.map(QPointF(args[0], args[1]))
        obj = args[0]
        if isinstance(obj, QPainterPath):
            return inv.map(obj)
        return inv.map(QPointF(obj))

    def mapRectToScene(self, rect: QRectF) -> QRectF:
        """Bounding rect of ``rect`` after the data rotation.

        Matches Qt's held-transform ``mapRectToScene`` (returns the axis-aligned
        bounds of the rotated rect), preserving offset/snap-distance callers.
        """
        return self._rotation_transform().mapRect(rect)

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        r = self.rect()
        props = {
            "Type": {"type": "label", "value": "Rectangle"},
            "Width": {"type": "dimension", "value": self._fmt(r.width()),
                      "value_mm": r.width(), "minimum": 0.0},
            "Height": {"type": "dimension", "value": self._fmt(r.height()),
                       "value_mm": r.height(), "minimum": 0.0},
            "Angle": {"type": "label", "value": f"{self._angle:.1f}"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "Width":
            v = self._parse_dim(value)
            if v is not None and v > 0:
                self._dim_edit(self.set_width, v)
            return
        if key == "Height":
            v = self._parse_dim(value)
            if v is not None and v > 0:
                self._dim_edit(self.set_height, v)
            return
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        r = self.rect()
        # Persist ``pivot`` as null when the rotation follows the rect centre
        # (``_pivot is None``) and as [x, y] only for an explicit pinned pivot.
        # Storing the resolved centre instead would round-trip the render but
        # pin the origin, so a later resize (reachable via undo, which uses this
        # same path) would rotate about the stale point instead of re-centring.
        pivot = None if self._pivot is None else [self._pivot.x(), self._pivot.y()]
        d = {
            "type":        "draw_rectangle",
            "x":           r.x(),
            "y":           r.y(),
            "w":           r.width(),
            "h":           r.height(),
            "angle":       self._angle,
            "pivot":       pivot,
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "RectangleItem":
        pt1 = QPointF(data["x"], data["y"])
        pt2 = QPointF(data["x"] + data["w"], data["y"] + data["h"])
        obj = cls(pt1, pt2, data.get("color", "#ffffff"),
                  data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        # Back-compat: pre-rotation records have no "angle"/"pivot" — default to
        # 0° about the rect centre, an identity transform (renders axis-aligned
        # exactly as before).  A stored null pivot means "follow the centre", so
        # it restores as _pivot=None (set_angle re-derives + keeps tracking).
        angle = data.get("angle", 0.0)
        pivot = QPointF(*data["pivot"]) if data.get("pivot") else None
        obj.set_angle(angle, pivot)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────
    # Grip indices (clockwise from top-left):
    #   0=TL  1=TM  2=TR  3=RM  4=BR  5=BM  6=BL  7=LM  8=Centre

    def grip_points(self) -> list[QPointF]:
        """Return the 9 grips in SCENE coords.

        Corners are computed in the axis-aligned LOCAL rect, then mapped through
        the item transform (``mapToScene``) so a rotated rectangle reports its
        grips in scene space.  At angle 0 the transform is identity and this is a
        no-op, preserving the original scene-coord contract for consumers.
        """
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        local = [
            QPointF(r.left(),  r.top()),                  # 0 TL
            QPointF(cx,        r.top()),                  # 1 TM
            QPointF(r.right(), r.top()),                  # 2 TR
            QPointF(r.right(), cy),                       # 3 RM
            QPointF(r.right(), r.bottom()),               # 4 BR
            QPointF(cx,        r.bottom()),               # 5 BM
            QPointF(r.left(),  r.bottom()),               # 6 BL
            QPointF(r.left(),  cy),                       # 7 LM
            QPointF(cx,        cy),                       # 8 Centre
        ]
        return [self.mapToScene(p) for p in local]

    def apply_grip(self, index: int, pos: QPointF):
        """Resize or translate the rectangle by dragging one of its 9 grips.

        ``pos`` arrives in SCENE coords; it is mapped to LOCAL first so the
        resize runs in the rectangle's own (rotated) frame (one home:
        :func:`rect_grip_resize`, plain mode — no Ctrl/Shift). Interactive
        drags go through ``RectGripHandle``, which resizes from the PRESS-time
        rect with the modifiers; this is the programmatic single-shot path.
        """
        if not 0 <= index <= 8:
            return
        self.prepareGeometryChange()
        self.setRect(rect_grip_resize(self.rect(), index, self.mapFromScene(pos),
                                      False, False))
        # A centre-following pivot (``_pivot is None``) re-derives from the new
        # rect centre automatically (see ``_rotation_origin``).

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def _resize_keeping(self, new_rect: QRectF, anchor_local: QPointF,
                        anchor_local_new: QPointF) -> None:
        """Apply *new_rect*, then translate so the anchor corner stays put in
        scene (a centre-following pivot would otherwise slide it)."""
        before = self.mapToScene(anchor_local)
        self.prepareGeometryChange()
        self.setRect(new_rect)
        after = self.mapToScene(anchor_local_new)
        self.translate(before.x() - after.x(), before.y() - after.y())

    def set_width(self, width_mm: float) -> None:
        """Set the local-x extent, keeping the left edge. No-op if <= 0."""
        if not math.isfinite(width_mm):
            return
        if width_mm <= 0:
            return
        r = self.rect()
        bl = QPointF(r.left(), r.bottom())
        self._resize_keeping(QRectF(r.left(), r.top(), width_mm, r.height()),
                             bl, bl)

    def set_height(self, height_mm: float) -> None:
        """Set the local-y extent, keeping the bottom edge. No-op if <= 0."""
        if not math.isfinite(height_mm):
            return
        if height_mm <= 0:
            return
        r = self.rect()
        bl = QPointF(r.left(), r.bottom())
        self._resize_keeping(
            QRectF(r.left(), r.bottom() - height_mm, r.width(), height_mm),
            bl, bl)

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        r = self.rect()
        specs = []
        if math.isfinite(r.width()) and r.width() >= _EPS_LEN:
            bl = self.mapToScene(QPointF(r.left(), r.bottom()))
            br = self.mapToScene(QPointF(r.right(), r.bottom()))
            c = self.mapToScene(r.center())
            specs.append(DimSpec(
                kind="linear", key="width", field="Width", prefix="",
                value=r.width(), field_kind="dimension",
                apply=self.set_width, a=bl, b=br, away=c))
        if math.isfinite(r.height()) and r.height() >= _EPS_LEN:
            br = self.mapToScene(QPointF(r.right(), r.bottom()))
            tr = self.mapToScene(QPointF(r.right(), r.top()))
            c = self.mapToScene(r.center())
            specs.append(DimSpec(
                kind="linear", key="height", field="Height", prefix="",
                value=r.height(), field_kind="dimension",
                apply=self.set_height, a=br, b=tr, away=c))
        return specs

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self.setRect(self.rect().translated(dx, dy))
        # Carry an explicit pivot with the rect (every rotate-step rect has one)
        # so a rotated rect keeps swinging about the same relative origin after a
        # move.  A centre-following pivot re-derives from the new centre.
        if self._pivot is not None:
            self._pivot = QPointF(self._pivot.x() + dx, self._pivot.y() + dy)

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Rectangles are always closed shapes."""
        return True

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetypes.md LT3 H3-b)."""
        # Rotation is data: the axis-aligned local rect's corners mapped through
        # the same _rotation_transform() paint() applies to the painter.
        from .path_walk import Seg
        r, t = self.rect(), self._rotation_transform()
        c = [t.map(p) for p in (r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft())]
        return tuple(Seg(a.x(), a.y(), b.x(), b.y()) for a, b in zip(c, c[1:] + c[:1]))

    def get_closed_path(self) -> QPainterPath:
        """Return a QPainterPath rectangle for hatching / fill operations."""
        path = QPainterPath()
        path.addRect(self.rect())
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Derive the pen from the style record (+ display colour).
        rs = self._sync_stroke_pen()
        # Bake-at-rest: rotation is DATA, not a held item transform, so rotate
        # the painter about the pivot here (local rect stays axis-aligned).
        # save/restore keeps the rotation local to this paint call.
        base_xf = painter.worldTransform()
        painter.save()
        try:
            if self._angle != 0.0:
                painter.setWorldTransform(self._rotation_transform(), True)
            # Draw fill FIRST (behind the outline).
            if getattr(self, "fill_type", "none") != "none":
                cp = self.get_closed_path()
                if cp is not None:
                    from .displayable_item import draw_fill
                    # The painter frame is rotated: painter-local → item via the
                    # rotation, then item → scene (Qt row-vector order), so the
                    # hatch stays in scene axes (D-A11).
                    draw_fill(painter, cp, self.scene(), self.fill_type,
                              self.fill_pattern, self._display_fill_color or "#888888",
                              alpha=int(round(self.fill_opacity * 255)),
                              to_scene=self._rotation_transform() * self.sceneTransform())
            # Linetype dashes draw in the UNROTATED item frame (stroke_pieces()
            # already carry the rotation), after the fill so it stays behind.
            self._paint_routed_stroke(painter, option, widget, rs,
                                      lambda p: p.drawRect(self.rect()),
                                      lt_frame=base_xf)
            if self.isSelected():
                # Corner-diagonal reference guides — shown whenever selected (a content
                # aid, NOT the selection highlight). Canonical width-1 dashed style,
                # matching EllipseItem's axis guides.
                ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
                ref.setCosmetic(True)
                painter.setPen(ref)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                for a, b in self._selection_ref_segments():
                    painter.drawLine(a, b)
        finally:
            painter.restore()
        self._paint_lt_badge(painter)

    def _selection_ref_segments(self):
        """Corner-diagonal reference guides, in the rect's LOCAL (axis-aligned)
        frame — the paint rotation transform orients them for a rotated rect."""
        r = self.rect()
        return [(r.topLeft(), r.bottomRight()), (r.topRight(), r.bottomLeft())]

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        """Rotated-footprint bounds (bake-at-rest — no held item transform).

        The base rect ``boundingRect`` is the axis-aligned local rect; with the
        rotation baked to data we return the rotated footprint's bounds so Qt's
        scene index / culling wraps the real shape (the held transform did this
        for free before).
        """
        base = super().boundingRect()
        if self._angle == 0.0:
            return base
        return self._rotation_transform().mapRect(base)

    def shape(self) -> QPainterPath:
        """Return a stroked outline path so the rectangle border is clickable.

        When filled, also include the interior so clicking anywhere inside
        selects the rectangle.  The path is rotated by the data ``_angle`` about
        the pivot so scene hit-testing tracks the rotated footprint.
        """
        cp = self.get_closed_path()  # addRect path in local coords
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(cp)
        if getattr(self, "fill_type", "none") != "none":
            path = path.united(cp)
        if self._angle != 0.0:
            path = self._rotation_transform().map(path)
        return path

    # ── Manipulator capability protocol (selection-manipulator.md) ──────────

    def manip_handles(self):
        """U3: the rect's own 9 live-apply grips at EVERY angle.

        Corners (0,2,4,6) + centre (8) render round; edge midpoints (1,3,5,7)
        square and align to the rect's angle via ``grip_render_angle``. Each is
        a ``RectGripHandle``: local-frame resize from the press-time rect,
        Ctrl = symmetric about the centre, Shift (corners) = keep aspect,
        centre grip = move. The rect exposes no ``scale`` capability, so the
        manipulator's rigid resize handles never surface for it. S2: the
        centre (8) is a ``RectTranslateGripHandle`` (handle snap)."""
        from .manip_handle import RectGripHandle, RectTranslateGripHandle
        return [(RectTranslateGripHandle if i == 8 else RectGripHandle)(
                    self, i, circular=i in (0, 2, 4, 6, 8))
                for i in range(9)]

    def manip_frame_redundant(self) -> bool:
        """True while unrotated: the rect's own outline coincides with the
        manipulator's axis-aligned frame, so the dashed frame is suppressed.
        A rotated rect keeps the frame (its bounds add information)."""
        return self._angle == 0.0

    def grip_render_angle(self, index: int) -> float:
        """Rotate the square edge-midpoint grips to the rect's baked Y-up
        orientation so their edges align with the (rotated) rect edges; the round
        corner/centre grips ignore it (rotation-invariant)."""
        return self._angle

    def manip_bounds(self) -> QRectF:
        """The rect's own geometry in scene coords so the manipulator frame
        hugs the shape (not the pen-padded ``sceneBoundingRect``).  For a rotated
        rect this is the axis-aligned bounds of the rotated footprint."""
        return self.mapRectToScene(self.rect())

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rotate: accumulate ``angle_deg`` onto the current angle about
        ``pivot`` (Y-up CCW+).  One home with ``set_angle`` so the manipulator
        and the placement rotate-step cannot drift.

        Composes with an existing rotation: turning by ``a2`` about ``pivot``
        after ``a1`` about the rect's own origin ``o`` equals turning by
        ``a1 + a2`` about ``o`` and then translating ``o`` to its rotated
        position — so the origin is kept and the rect is translated (a bare
        ``set_angle(a1 + a2, pivot)`` would re-rotate the whole ``a1`` about
        the new pivot and shift an already-rotated rect).
        """
        from .cad_math import CAD_Math
        o = self._rotation_origin()
        new_o = CAD_Math.rotate_point(o, pivot, -angle_deg)
        self.set_angle(self._angle + angle_deg,
                       None if self._pivot is None else o)
        self.translate(new_o.x() - o.x(), new_o.y() - o.y())

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror across the infinite line p1-p2 (DD1): still a rect.

        With θ = the axis' Y-up heading, reflecting a rect drawn at ``_angle``
        about its origin ``o`` equals rotating by ``2θ − _angle`` about the
        mirrored origin ``o'`` a local rect flipped top-for-bottom about ``o``
        (Refl_θ·Rot(α) = Rot(2θ−α)·Refl_0). A rect is 180°-symmetric, so a
        heading ≥ 180 is folded by 180 with a left-for-right flip instead
        (Rot(180)·Refl_0 = Refl_vertical) — an axis-aligned rect mirrored
        across an axis-aligned line stays at angle 0. The pivot semantics are
        kept (centre-following stays None; an explicit pivot moves to o').
        """
        if _degenerate_axis(p1, p2):
            return              # zero-length axis: no-op, never half-applied
        from .arc_math import _norm360, yup_angle
        from .cad_math import CAD_Math
        theta = yup_angle(p1, p2)
        o = self._rotation_origin()
        new_o = CAD_Math.mirror_point(o, p1, p2)
        r = self.rect()
        ang = _norm360(2.0 * theta - self._angle)
        if ang >= 180.0 - 1e-9:
            ang = max(0.0, ang - 180.0)
            new = QRectF(new_o.x() - (r.right() - o.x()),
                         new_o.y() + (r.top() - o.y()),
                         r.width(), r.height())
        else:
            new = QRectF(new_o.x() + (r.left() - o.x()),
                         new_o.y() - (r.bottom() - o.y()),
                         r.width(), r.height())
        if ang < 1e-9:
            ang = 0.0
        self.prepareGeometryChange()
        self.setRect(new)
        self.set_angle(ang, None if self._pivot is None else new_o)
        toggle_mirrored(self.style)          # LT5 Q9

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale about ``base`` (DD1): a uniform scale commutes
        with the data rotation, so the origin ``o`` maps to ``o'`` and the
        local rect is scaled about ``o`` then re-seated on ``o'``; the angle
        and the pivot semantics are kept. Not ``manip_scale`` (a rect must
        never become box-resizable — test_rect_grips_unified)."""
        from .cad_math import CAD_Math
        o = self._rotation_origin()
        new_o = CAD_Math.scale_point(o, base, factor)
        r = self.rect()
        new = QRectF(new_o.x() + (r.left() - o.x()) * factor,
                     new_o.y() + (r.top() - o.y()) * factor,
                     r.width() * factor, r.height() * factor)
        self.prepareGeometryChange()
        self.setRect(new)
        self.set_angle(self._angle, None if self._pivot is None else new_o)


# ─────────────────────────────────────────────────────────────────────────────
# CircleItem  — circle defined by centre + edge point
# ─────────────────────────────────────────────────────────────────────────────

class CircleItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsEllipseItem):
    """
    A circle defined by its centre and one point on the circumference.

    Parameters
    ----------
    center  : QPointF — circle centre in scene coordinates
    radius  : float   — radius in scene units
    color   : str | QColor
    lineweight : float — cosmetic pixel width
    """

    def __init__(self, center: QPointF, radius: float,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        self._center = center
        self._radius = radius
        r = radius
        super().__init__(center.x() - r, center.y() - r, 2 * r, 2 * r)

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        self._init_stroke(color, lineweight)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type": {"type": "label", "value": "Circle"},
            "Centre": {"type": "label", "value": f"({self._center.x():.1f}, {self._center.y():.1f})"},
            "Radius": {"type": "dimension", "value": self._fmt(self._radius),
                       "value_mm": self._radius,
                       "minimum": 1.0 - 1e-9},   # reject below the 1 mm floor
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "Radius":
            v = self._parse_dim(value)
            if v is not None and v > 0:
                self._dim_edit(self.set_radius, v)
            return
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":        "draw_circle",
            "cx":          self._center.x(),
            "cy":          self._center.y(),
            "radius":      self._radius,
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "CircleItem":
        center = QPointF(data["cx"], data["cy"])
        obj = cls(center, data["radius"],
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────
    # Grip indices: 0=centre  1=right  2=top  3=left  4=bottom

    def grip_points(self) -> list[QPointF]:
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        return [
            QPointF(cx,     cy),      # 0 centre
            QPointF(cx + r, cy),      # 1 right  (0°)
            QPointF(cx,     cy - r),  # 2 top    (90°)
            QPointF(cx - r, cy),      # 3 left   (180°)
            QPointF(cx,     cy + r),  # 4 bottom (270°)
        ]

    def apply_grip(self, index: int, pos: QPointF):
        """Translate (index 0) or resize (index 1-4)."""
        import math as _math
        if index == 0:
            self._center = pos
        else:
            self._radius = _math.hypot(
                pos.x() - self._center.x(),
                pos.y() - self._center.y(),
            )
            if self._radius < 1:
                self._radius = 1
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_radius(self, radius_mm: float) -> None:
        """Set the radius, keeping the centre (floor 1 mm, as apply_grip)."""
        if not math.isfinite(radius_mm):
            return
        self._radius = max(CIRCLE_MIN_RADIUS, float(radius_mm))
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        c, r = QPointF(self._center), self._radius
        if not math.isfinite(r):
            return []
        # Just below the 1 mm floor, so the floor value itself is still
        # accepted (``minimum`` is a strict "greater than").
        return [DimSpec(kind="linear", key="radius", field="Radius", prefix="R",
                        value=r, field_kind="dimension", apply=self.set_radius,
                        minimum=1.0 - 1e-9,
                        a=c, b=QPointF(c.x() + r, c.y()),
                        away=QPointF(c.x(), c.y() + r))]   # label above the radial

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate about ``pivot`` (Y-up CCW+): the centre moves; the
        circle shape is rotation-invariant so the radius is unchanged."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.rotate_point(self._center, pivot, -angle_deg)
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror across the infinite line p1-p2 (DD1): the centre moves;
        a circle is mirror-symmetric so the radius is unchanged."""
        if _degenerate_axis(p1, p2):
            return              # zero-length axis: no-op, never half-applied
        from .cad_math import CAD_Math
        self._center = CAD_Math.mirror_point(self._center, p1, p2)
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        self.setRect(cx - r, cy - r, 2 * r, 2 * r)
        toggle_mirrored(self.style)          # LT5 Q9

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale about ``base`` (DD1): centre scaled, radius ×
        factor through ``set_radius`` (its 1 mm floor applies)."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.scale_point(self._center, base, factor)
        self.set_radius(self._radius * factor)

    def manip_handles(self):
        """U3: expose parametric grips as live-apply GripHandles (center +
        4 radius). The manipulator renders/hit-tests/commits them; the legacy
        grip paths skip this item (coexistence gate). Grip 0 is the centre/move
        grip (circular); the 4 radius grips are square parametric points.
        S2: the centre is a ``TranslateGripHandle`` (handle snap)."""
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0}, translate={0})

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Circles are always closed shapes."""
        return True

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetypes.md LT3 H3-b)."""
        from .path_walk import Arc
        return (Arc(self._center.x(), self._center.y(), self._radius, 0.0, 360.0),)

    def get_closed_path(self) -> QPainterPath:
        """Return a QPainterPath ellipse for hatching / fill operations."""
        path = QPainterPath()
        path.addEllipse(self.rect())
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Derive the pen from the style record (+ display colour).
        rs = self._sync_stroke_pen()
        # Draw fill FIRST (behind the outline)
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)),
                          to_scene=self.sceneTransform())
        self._paint_routed_stroke(painter, option, widget, rs,
                                  lambda p: p.drawEllipse(self.rect()))
        if self.isSelected():
            # Radius guide + bounding box — shown whenever selected (a content aid,
            # NOT the selection highlight). Canonical width-1 dashed style.
            ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref.setCosmetic(True)
            painter.setPen(ref)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect())               # bounding box
            for a, b in self._selection_ref_segments():
                painter.drawLine(a, b)                  # radius guide
        self._paint_lt_badge(painter)

    def _selection_ref_segments(self):
        """A single radius guide from the centre to the right edge (local coords)."""
        r = self.rect()
        return [(r.center(), QPointF(r.right(), r.center().y()))]

    # ── Shape / hit-test ─────────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        """Return a stroked ellipse outline path so the circle border is clickable.

        When filled, also include the interior so clicking anywhere inside
        selects the circle.
        """
        cp = self.get_closed_path()  # addEllipse path in local coords
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(cp)
        if getattr(self, "fill_type", "none") != "none":
            path = path.united(cp)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# ArcItem
# ─────────────────────────────────────────────────────────────────────────────

class ArcItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """
    A circular arc defined by centre, radius, start angle and span angle.
    Angles are in degrees, measured counter-clockwise from the +X axis
    (Qt convention: positive span = CCW, angles in 1/16ths internally but
    we use QPainterPath.arcTo which takes plain degrees).
    """

    def __init__(self, center: QPointF, radius: float,
                 start_deg: float, span_deg: float,
                 color: str = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._center = QPointF(center)
        self._radius = max(radius, 0.01)
        # Store every arc in CCW form (span > 0): a negative (CW) span — e.g.
        # legacy saves — is the same geometric arc starting at
        # start + span. The grip refits assume CCW start→end.
        from .arc_math import _norm360
        if span_deg < 0:
            start_deg, span_deg = start_deg + span_deg, -span_deg
        self._start_deg = _norm360(start_deg)
        self._span_deg = span_deg

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        self._init_stroke(color, lineweight)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlags(
            self.GraphicsItemFlag.ItemIsSelectable |
            self.GraphicsItemFlag.ItemIsMovable
        )
        self._rebuild_path()

    def _rebuild_path(self):
        self._closed_clears_ends()                # LT5: a 360 deg arc is closed
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        path = QPainterPath()
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        path.arcMoveTo(rect, self._start_deg)
        path.arcTo(rect, self._start_deg, self._span_deg)
        self.setPath(path)

    # ── Properties ─────────────────────────────────────────────────────────

    def get_properties(self) -> dict:
        props = {
            "Type":        {"type": "label", "value": "Arc"},
            "Centre":      {"type": "label", "value": f"({self._center.x():.1f}, {self._center.y():.1f})"},
            "Radius":      {"type": "dimension", "value": self._fmt(self._radius),
                            "value_mm": self._radius,
                            "minimum": 0.01 - 1e-12},   # reject below the floor
            "Start Angle": {"type": "label", "value": f"{self._start_deg:.1f}°"},
            "Span":        {"type": "dimension",
                            "value": ScaleManager.format_span(self._span_deg),
                            "value_mm": self._span_deg,
                            "parser": ScaleManager.parse_span,
                            "formatter": ScaleManager.format_span, "minimum": 0.0,
                            # set_property accepts 0 < span < 360 only
                            "maximum": 360.0 - 1e-6},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "Radius":
            v = self._parse_dim(value)
            if v is not None and v > 0:
                self._dim_edit(self.set_radius, v)
            return
        if key == "Span":
            try:
                v = float(value)
            except (TypeError, ValueError):
                return
            if math.isfinite(v) and 0 < v < 360:
                self._dim_edit(self.set_span, v)
            return
        if self._geom2d_set(key, value):
            return

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = {
            "type":       "arc",
            "cx":         self._center.x(),
            "cy":         self._center.y(),
            "radius":     self._radius,
            "start_deg":  self._start_deg,
            "span_deg":   self._span_deg,
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "ArcItem":
        center = QPointF(data["cx"], data["cy"])
        obj = cls(center, data["radius"], data["start_deg"], data["span_deg"],
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        return obj

    # ── Grip protocol ─────────────────────────────────────────────────────────

    def grip_points(self) -> list[QPointF]:
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        sa = math.radians(self._start_deg)
        ea = math.radians(self._start_deg + self._span_deg)
        return [
            QPointF(cx, cy),                                    # 0 centre
            QPointF(cx + r * math.cos(sa), cy - r * math.sin(sa)),  # 1 start
            QPointF(cx + r * math.cos(ea), cy - r * math.sin(ea)),  # 2 end
        ]

    def arc_midpoint(self) -> QPointF:
        """The point halfway along the arc (Y-up start + span/2)."""
        from .arc_math import point_at
        return point_at(self._center, self._radius,
                        self._start_deg + self._span_deg / 2.0)

    def begin_endpoint_refit(self) -> None:
        """Snapshot the endpoint-drag reference (called by the grip on press)."""
        pts = self.grip_points()
        self._arc_refit_ref = {"start": pts[1], "end": pts[2],
                               "mid": self.arc_midpoint(),
                               "center": QPointF(self._center),
                               "radius": self._radius}

    def end_endpoint_refit(self) -> None:
        self._arc_refit_ref = None

    def apply_grip(self, index: int, pos: QPointF):
        """Re-shape the arc from a grip drag (user 2026-09-23).

        * 0 centre — both endpoints stay fixed; the centre is projected onto
          their perpendicular bisector (radius/bulge follow; CCW start→end is
          kept, so crossing the chord grows the arc through a semicircle into a
          major arc). A full-circle arc (no chord) translates instead.
        * 1 start / 2 end — the centre, radius and the other endpoint stay
          fixed (user 2026-09-24); *pos* is projected radially onto the circle
          and only the dragged endpoint's angle changes. A span within 0.5° of
          0° / 360° (or *pos* on the centre) holds the last valid shape.
        """
        from .arc_math import project_to_bisector, yup_angle, _norm360
        if index == 0:
            pts = self.grip_points()
            s, e = pts[1], pts[2]
            proj = project_to_bisector(s, e, pos)
            if proj is None or abs(self._span_deg) >= 360.0 - 1e-6:
                self._center = QPointF(pos)
            else:
                c, _t = proj
                r = math.hypot(s.x() - c.x(), s.y() - c.y())
                ts = yup_angle(c, s)
                span = (yup_angle(c, e) - ts) % 360.0   # CCW start→end kept
                if r < 0.01 or span < 1e-6:
                    return                       # hold last valid shape
                self._center = c
                self._radius = r
                self._start_deg = _norm360(ts)
                self._span_deg = span
        elif index in (1, 2):
            c = self._center
            if math.hypot(pos.x() - c.x(), pos.y() - c.y()) < 1e-9:
                return                           # no radial direction
            theta = yup_angle(c, pos)
            if index == 1:
                start = theta
                span = (self._start_deg + self._span_deg - theta) % 360.0
            else:
                start = self._start_deg
                span = (theta - self._start_deg) % 360.0
            if span < 0.5 or span > 359.5:
                return                           # hold last valid shape
            self._start_deg = _norm360(start)
            self._span_deg = span
        else:
            return
        self._rebuild_path()

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_span(self, span_deg: float) -> None:
        """Set the included angle, keeping centre / radius / start (end moves
        CCW). Clamped to (0, 360)."""
        if not math.isfinite(span_deg):
            return
        self._span_deg = min(max(float(span_deg), 1e-6), 360.0 - 1e-6)
        self._rebuild_path()

    def set_radius(self, radius_mm: float) -> None:
        """Set the radius, keeping centre and both angles (floor 0.01 mm)."""
        if not math.isfinite(radius_mm):
            return
        self._radius = max(float(radius_mm), ARC_MIN_RADIUS)
        self._rebuild_path()

    def dimension_specs(self) -> list:
        from .arc_math import point_at
        from .selection_readouts import DimSpec
        c = QPointF(self._center)
        if not (math.isfinite(self._span_deg) and math.isfinite(self._radius)):
            return []
        return [
            DimSpec(kind="angular", key="angle", field="Angle", prefix="",
                    value=self._span_deg, field_kind="span",
                    apply=self.set_span, maximum=360.0 - 1e-6,
                    center=c, ref_radius=self._radius,
                    start_deg=self._start_deg, span_deg=self._span_deg),
            DimSpec(kind="linear", key="radius", field="Radius", prefix="R",
                    value=self._radius, field_kind="dimension",
                    apply=self.set_radius,
                    # Just below the 0.01 mm floor, so the floor value itself
                    # is still accepted (``minimum`` is a strict "greater than").
                    minimum=0.01 - 1e-12,
                    a=c, b=point_at(c, self._radius, self._start_deg),
                    away=point_at(c, self._radius,
                                  self._start_deg + self._span_deg)),
        ]

    def manip_handles(self):
        """U3: centre grip (bisector slide) + start/end ``ArcEndpointGripHandle``s
        (slide along the circle). All round (house rule)."""
        from .manip_handle import GripHandle, ArcEndpointGripHandle
        return [GripHandle(self, 0, circular=True),
                ArcEndpointGripHandle(self, 1),
                ArcEndpointGripHandle(self, 2)]

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._rebuild_path()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate about ``pivot`` (Y-up CCW+): rotate the centre and
        advance the start angle by ``angle_deg`` (Y-up); span unchanged."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.rotate_point(self._center, pivot, -angle_deg)
        self._start_deg = (self._start_deg + angle_deg) % 360.0
        self._rebuild_path()

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror across the infinite line p1-p2 (DD1, Y-up angles).

        A reflection reverses orientation, so the old END becomes the new
        START: start' = 2θ − (start + span), span kept (θ = the axis' Y-up
        heading via ``arc_math.yup_angle``)."""
        if _degenerate_axis(p1, p2):
            return              # zero-length axis: no-op, never half-applied
        from .arc_math import _norm360, yup_angle
        from .cad_math import CAD_Math
        theta = yup_angle(p1, p2)
        self._center = CAD_Math.mirror_point(self._center, p1, p2)
        self._start_deg = _norm360(2.0 * theta
                                   - (self._start_deg + self._span_deg))
        self._rebuild_path()
        # LT5 Q9 / E5: the old END is the new START -- swap the end records
        # so each stays on its physical end, then mirror both.
        st = self.style
        if st is not None:
            st["start"], st["finish"] = st["finish"], st["start"]
        toggle_mirrored(st)

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale about ``base`` (DD1): centre scaled, radius ×
        factor (``set_radius`` floor), angles unchanged."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.scale_point(self._center, base, factor)
        self.set_radius(self._radius * factor)

    # ── Closed-path protocol ─────────────────────────────────────────────────

    def is_closed(self) -> bool:
        """Return True if the arc spans a full 360 degrees (i.e. a full circle)."""
        return abs(self._span_deg) >= 360

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetypes.md LT3 H3-b)."""
        # Stored CCW (span > 0) with Qt arcTo angles, exactly as _rebuild_path.
        from .path_walk import Arc
        return (Arc(self._center.x(), self._center.y(), self._radius,
                    self._start_deg, self._span_deg),)

    def get_closed_path(self) -> QPainterPath | None:
        """Return a QPainterPath ellipse if the arc is a full circle, else None."""
        if not self.is_closed():
            return None
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        path = QPainterPath()
        path.addEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        return path

    # ── Paint (selection highlight) ──────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        # Derive the pen from the style record (+ display colour).
        rs = self._sync_stroke_pen()
        # Draw fill FIRST (behind the outline); only applies when arc is closed
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)),
                          to_scene=self.sceneTransform())
        self._paint_routed_stroke(painter, option, widget, rs,
                                  lambda p: p.drawPath(self.path()))
        if self.isSelected():
            # Centre→start / centre→end reference radials — shown whenever
            # selected (a content aid, NOT the selection highlight). Canonical
            # width-1 dashed style, matching EllipseItem's axis guides.
            ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref.setCosmetic(True)
            painter.setPen(ref)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for a, b in self._selection_ref_segments():
                painter.drawLine(a, b)
        self._paint_lt_badge(painter)

    def _selection_ref_segments(self):
        """Reference radials centre→start and centre→end (scene coords)."""
        c, s, e = self.grip_points()
        return [(c, s), (c, e)]

    def itemChange(self, change, value):
        # The selected bounds grow to cover the radials (the centre can lie
        # outside the arc's path bounds) — tell the scene before they change.
        if change == self.GraphicsItemChange.ItemSelectedChange:
            self.prepareGeometryChange()
        return super().itemChange(change, value)

    def boundingRect(self) -> QRectF:
        """Path bounds; when selected, also the centre so the reference
        radials repaint/cull correctly. Hit-testing uses :meth:`shape`, which
        stays the stroked arc."""
        base = super().boundingRect()
        if not self.isSelected():
            return base
        c = self._center
        return base.united(QRectF(c.x() - 1.0, c.y() - 1.0, 2.0, 2.0))

    def shape(self) -> QPainterPath:
        """Return a stroked arc path; when the arc is a closed circle and is
        filled, also include the interior for interior hit-testing.
        """
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                path = path.united(cp)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# RegularPolygonItem — parametric regular N-gon
# ─────────────────────────────────────────────────────────────────────────────

_POLY_MIN_SIDES = 3
_POLY_MAX_SIDES = 120


class RegularPolygonItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """A parametric regular polygon defined by centre/sides/radius/rotation.

    ``_radius_mm`` is the *defining* radius the user picked: the circumradius
    (centre->vertex) when ``_inscribed`` is True, or the apothem (centre->edge
    midpoint) when False.  Vertices are always derived, never stored.
    """

    def __init__(self, center: QPointF, sides: int = 6, radius_mm: float = 0.0,
                 rotation_deg: float = 0.0, inscribed: bool = True,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._center = QPointF(center)
        self._sides = max(_POLY_MIN_SIDES, min(_POLY_MAX_SIDES, int(sides)))
        self._radius_mm = float(radius_mm)
        self._rotation_deg = float(rotation_deg)
        self._inscribed = bool(inscribed)

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        self._init_stroke(color, lineweight)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self._regenerate()

    def _circumradius(self) -> float:
        if self._inscribed:
            return self._radius_mm
        return self._radius_mm / math.cos(math.pi / self._sides)

    def vertices(self) -> list[QPointF]:
        rv = self._circumradius()
        step = 360.0 / self._sides
        # For circumscribed polygons the natural orientation places a flat edge
        # facing the user (apothem along +X axis), which means the first vertex
        # is offset by half a step from the rotation origin.
        base = self._rotation_deg + (0.0 if self._inscribed
                                     else 180.0 / self._sides)
        out = []
        for k in range(self._sides):
            a = math.radians(base + k * step)
            # Y-up convention (CCW-positive, app-wide): a positive rotation
            # swings vertices up (−y in Qt scene), so sin is negated.  Matches
            # the placement rotate angle, the dashed reference line, and the
            # shared "rotation" HUD schema.  apply_grip() negates dy to stay the
            # exact inverse of this.
            out.append(QPointF(self._center.x() + rv * math.cos(a),
                               self._center.y() - rv * math.sin(a)))
        return out

    def _regenerate(self):
        verts = self.vertices()
        path = QPainterPath()
        if verts:
            path.addPolygon(QPolygonF(verts))
            path.closeSubpath()
        self.setPath(path)
        self.update()

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetypes.md LT3 H3-b)."""
        from .path_walk import Seg
        v = self.vertices()
        return tuple(Seg(a.x(), a.y(), b.x(), b.y()) for a, b in zip(v, v[1:] + v[:1]))

    def get_closed_path(self) -> QPainterPath | None:
        p = QPainterPath()
        p.addPolygon(QPolygonF(self.vertices()))
        p.closeSubpath()
        return p

    def get_properties(self) -> dict:
        props = {
            "Type":     {"type": "label", "value": "Polygon"},
            "Sides":    {"type": "string", "value": str(self._sides)},
            "Radius":   {"type": "dimension",
                         "value": self._fmt(self._radius_mm),
                         "value_mm": self._radius_mm},
            "Rotation": {"type": "string",
                         "value": f"{self._rotation_deg:.2f}", "suffix": "°"},
            "Shape":    {"type": "enum",
                         "options": ["inscribed", "circumscribed"],
                         "value": "inscribed" if self._inscribed else "circumscribed"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "Sides":
            try:
                self._sides = max(_POLY_MIN_SIDES, min(_POLY_MAX_SIDES, int(float(value))))
            except (TypeError, ValueError):
                return
            self._regenerate()
            return
        if key == "Radius":
            r = self._parse_dim(value)
            if r is not None and r > 0:
                self._dim_edit(self.set_radius, r)
            return
        if key == "Rotation":
            try:
                self._rotation_deg = float(str(value).replace("°", "").strip())
            except (TypeError, ValueError):
                return
            self._regenerate()
            return
        if key == "Shape":
            self._inscribed = (str(value) == "inscribed")
            self._regenerate()
            return
        if self._geom2d_set(key, value):
            self._regenerate()
            return

    def grip_points(self) -> list[QPointF]:
        return [QPointF(self._center)] + self.vertices()

    def apply_grip(self, index: int, pos: QPointF):
        if index == 0:
            self._center = QPointF(pos)
            self._regenerate()
            return
        vi = index - 1
        if not (0 <= vi < self._sides):
            return
        dx, dy = pos.x() - self._center.x(), pos.y() - self._center.y()
        rv = math.hypot(dx, dy)
        if rv < 0.5:
            return
        step = 360.0 / self._sides
        # The base angle for vertex 0 is _rotation_deg + circ_offset.
        # Solve: ang = _rotation_deg + circ_offset + vi * step
        # circ_offset mirrors the same half-step applied in vertices(); the two
        # must stay in sync — this line is the inverse of vertices()'s `base`.
        circ_offset = 0.0 if self._inscribed else 180.0 / self._sides
        # Y-up angle of the drag point (−dy): the exact inverse of vertices(),
        # which places vertex vi at angle (rotation + circ_offset + vi*step) in
        # the Y-up frame.  So the dragged vertex lands exactly under the cursor.
        ang = math.degrees(math.atan2(-dy, dx))
        self._rotation_deg = ang - circ_offset - vi * step
        self._radius_mm = rv if self._inscribed else rv * math.cos(math.pi / self._sides)
        self._regenerate()

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_radius(self, mm: float) -> None:
        """Set the stored defining radius (circumradius if inscribed, apothem if
        circumscribed); keeps centre / sides / rotation. No-op if <= 0."""
        if not math.isfinite(mm):
            return
        if mm <= 0:
            return
        self._radius_mm = float(mm)
        self._regenerate()

    def dimension_specs(self) -> list:
        from .arc_math import point_at
        from .selection_readouts import DimSpec
        if not math.isfinite(self._radius_mm):
            return []
        c = QPointF(self._center)
        b = point_at(c, self._radius_mm, self._rotation_deg)
        away = point_at(c, self._radius_mm, self._rotation_deg + 90.0)
        return [DimSpec(kind="linear", key="radius", field="Radius", prefix="R",
                        value=self._radius_mm, field_kind="dimension",
                        apply=self.set_radius, a=c, b=b, away=away)]

    def manip_handles(self):
        """U3: expose the centre + each vertex as a live-apply GripHandle.

        All grips render round per the house rule: the centre is a move grip
        and the vertices are the polygon's defining points (dragging a vertex
        resizes + rotates — the edit math lives in apply_grip). Zero special
        drag semantics: the legacy grip path explicitly excludes polygon from
        Ctrl-constrain, so no EndpointGripHandle/_transform_point. Same shape
        as ArcItem/Spline. The manipulator renders/hit-tests/commits them; the
        legacy grip paths skip this item (coexistence gate)."""
        from .manip_handle import default_grip_handles
        # S2: the centre (0) is a whole-item move grip → TranslateGripHandle.
        return default_grip_handles(
            self, circular=set(range(len(self.grip_points()))), translate={0})

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._regenerate()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        """Baked rigid rotate about ``pivot`` (Y-up CCW+): rotate the centre and
        advance the parametric orientation ``_rotation_deg`` by ``angle_deg``."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.rotate_point(self._center, pivot, -angle_deg)
        self._rotation_deg = (self._rotation_deg + angle_deg) % 360.0
        self._regenerate()

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror across the infinite line p1-p2 (DD1, Y-up angles):
        rotation' = 2θ − rotation. A vertex at heading a maps to 2θ − a; the
        circumscribed half-step offset 180/n contributes 2·180/n = one full
        step, so the vertex SET is identical for both shapes."""
        if _degenerate_axis(p1, p2):
            return              # zero-length axis: no-op, never half-applied
        from .arc_math import _norm360, yup_angle
        from .cad_math import CAD_Math
        theta = yup_angle(p1, p2)
        self._center = CAD_Math.mirror_point(self._center, p1, p2)
        self._rotation_deg = _norm360(2.0 * theta - self._rotation_deg)
        self._regenerate()
        toggle_mirrored(self.style)          # LT5 Q9

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale about ``base`` (DD1): centre scaled, the
        defining radius × factor; sides / rotation / inscribed kept."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.scale_point(self._center, base, factor)
        self.set_radius(self._radius_mm * factor)

    def to_dict(self) -> dict:
        d = {
            "type":        "polygon",
            "center":      [self._center.x(), self._center.y()],
            "sides":       self._sides,
            "radius_mm":   self._radius_mm,
            "rotation":    self._rotation_deg,
            "inscribed":   self._inscribed,
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "RegularPolygonItem":
        c = data["center"]
        obj = cls(QPointF(c[0], c[1]),
                  sides=data.get("sides", 6),
                  radius_mm=data.get("radius_mm", 0.0),
                  rotation_deg=data.get("rotation", 0.0),
                  inscribed=data.get("inscribed", True),
                  color=data.get("color", "#ffffff"),
                  lineweight=data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        obj._regenerate()
        return obj

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        rs = self._sync_stroke_pen()
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)),
                          to_scene=self.sceneTransform())
        self._paint_routed_stroke(painter, option, widget, rs,
                                  lambda p: p.drawPath(self.path()))
        if self.isSelected():
            # Dashed circumradius reference circle — shown whenever selected
            # (manipulator-wrapped or not): a content aid, NOT the highlight.
            # Canonical reference-line style (width-1 dashed).
            rv = self._circumradius()
            cx, cy = self._center.x(), self._center.y()
            ref_pen = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref_pen.setCosmetic(True)
            painter.setPen(ref_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(cx - rv, cy - rv, 2 * rv, 2 * rv))
        self._paint_lt_badge(painter)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            path = path.united(self.get_closed_path())
        return path


# ─────────────────────────────────────────────────────────────────────────────
# EllipseItem — centre + two half-axes + Y-up rotation
# ─────────────────────────────────────────────────────────────────────────────

_AXIS_MIN = 0.5   # anti-degeneracy floor (mm), matches circle/polygon


class EllipseItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """An ellipse defined by centre, semi-major (rx), semi-minor (ry) and a
    Y-up rotation of the major axis.

    Path-based (not a native QGraphicsEllipseItem) because the rotation is
    data-parametric and paint-applied — never Qt setRotation — matching the
    app-wide Y-up / CCW-positive convention used by RegularPolygonItem.
    """

    def __init__(self, center: QPointF, rx: float, ry: float,
                 rotation_deg: float = 0.0,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0):
        super().__init__()
        self._center = QPointF(center)
        self._rx = max(float(rx), _AXIS_MIN)
        self._ry = max(float(ry), _AXIS_MIN)
        self._rotation_deg = float(rotation_deg)

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        self._init_stroke(color, lineweight)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self._regenerate()

    def _ellipse_path_local(self) -> QPainterPath:
        p = QPainterPath()
        p.addEllipse(QPointF(0.0, 0.0), self._rx, self._ry)
        return p

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetypes.md LT3 H3-b)."""
        # Frame translate(c)·rotate(−rot), the same as get_closed_path.
        from .path_walk import EllipseArc
        return (EllipseArc(self._center.x(), self._center.y(), self._rx, self._ry,
                           self._rotation_deg, 0.0, 360.0),)

    def get_closed_path(self) -> QPainterPath:
        t = QTransform()
        t.translate(self._center.x(), self._center.y())
        t.rotate(-self._rotation_deg)
        return t.map(self._ellipse_path_local())

    def is_closed(self) -> bool:
        return True

    def _regenerate(self):
        self.setPath(self.get_closed_path())
        self.update()

    def _axis_endpoint(self, semi: float, angle_off_deg: float) -> QPointF:
        a = math.radians(self._rotation_deg + angle_off_deg)
        return QPointF(self._center.x() + semi * math.cos(a),
                       self._center.y() - semi * math.sin(a))

    def grip_points(self) -> list[QPointF]:
        return [
            QPointF(self._center),
            self._axis_endpoint(self._rx, 0.0),
            self._axis_endpoint(self._rx, 180.0),
            self._axis_endpoint(self._ry, 90.0),
            self._axis_endpoint(self._ry, 270.0),
        ]

    def apply_grip(self, index: int, pos: QPointF):
        if index == 0:
            self._center = QPointF(pos)
            self._regenerate()
            return
        dx = pos.x() - self._center.x()
        dy = pos.y() - self._center.y()
        dist = math.hypot(dx, dy)
        if dist < _AXIS_MIN:
            return
        if index in (1, 2):
            self._rx = dist
            ang = math.degrees(math.atan2(-dy, dx))
            self._rotation_deg = (ang - (180.0 if index == 2 else 0.0)) % 360.0
        elif index in (3, 4):
            self._ry = dist
        self._regenerate()

    # ── Typed dimensions (2d-geometry.md §8) ─────────────────────────────

    def set_rx(self, mm: float) -> None:
        """R1 (rx semi-axis); keeps centre + rotation. Floor _AXIS_MIN."""
        if not math.isfinite(mm):
            return
        self._rx = max(float(mm), _AXIS_MIN)
        self._regenerate()

    def set_ry(self, mm: float) -> None:
        """R2 (ry semi-axis); keeps centre + rotation. Floor _AXIS_MIN."""
        if not math.isfinite(mm):
            return
        self._ry = max(float(mm), _AXIS_MIN)
        self._regenerate()

    def dimension_specs(self) -> list:
        from .selection_readouts import DimSpec
        if not (math.isfinite(self._rx) and math.isfinite(self._ry)):
            return []
        c = QPointF(self._center)
        # Just below _AXIS_MIN, so the floor value itself is still accepted
        # (``minimum`` is a strict "greater than").
        floor = _AXIS_MIN - 1e-9
        return [
            DimSpec(kind="linear", key="r1", field="R1", prefix="R1",
                    value=self._rx, field_kind="dimension", apply=self.set_rx,
                    minimum=floor,
                    a=c, b=self._axis_endpoint(self._rx, 0.0),
                    away=self._axis_endpoint(self._ry, 90.0)),
            DimSpec(kind="linear", key="r2", field="R2", prefix="R2",
                    value=self._ry, field_kind="dimension", apply=self.set_ry,
                    minimum=floor,
                    a=c, b=self._axis_endpoint(self._ry, 90.0),
                    away=self._axis_endpoint(self._rx, 0.0)),
        ]

    def manip_handles(self):
        """U3: expose parametric grips as live-apply GripHandles (centre + 4
        axis endpoints). Mirrors CircleItem (an ellipse is a generalized
        circle): grip 0 is the centre/move grip (round); the 4 axis-endpoint
        grips (major rx = 1,2; minor ry = 3,4) are square sizing points — the
        major pair also rotates. Zero special drag semantics (the legacy grip
        path only Ctrl-constrains Wall/Gridline/Line); apply_grip carries the
        edit math. The manipulator renders/hit-tests/commits them; the legacy
        grip paths skip this item (coexistence gate). S2: the centre is a
        ``TranslateGripHandle`` (handle snap)."""
        from .manip_handle import default_grip_handles
        return default_grip_handles(self, circular={0}, translate={0})

    def grip_render_angle(self, index: int) -> float:
        """U3 grip-shape hook: rotate the square axis grips to the ellipse's
        orientation so their edges align radially with the major/minor axes (and
        stay aligned after a rotate). Returns the Y-up ``_rotation_deg``; the
        round centre grip ignores it (rotation-invariant). Each axis radial is
        ``_rotation_deg`` mod 90, so one box angle aligns all four squares."""
        return self._rotation_deg

    def translate(self, dx: float, dy: float):
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self._regenerate()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        from .cad_math import CAD_Math
        self._center = CAD_Math.rotate_point(self._center, pivot, -angle_deg)
        self._rotation_deg = (self._rotation_deg + angle_deg) % 360.0
        self._regenerate()

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror across the infinite line p1-p2 (DD1, Y-up angles):
        the major-axis heading maps to 2θ − rotation; rx / ry are kept."""
        if _degenerate_axis(p1, p2):
            return              # zero-length axis: no-op, never half-applied
        from .arc_math import _norm360, yup_angle
        from .cad_math import CAD_Math
        theta = yup_angle(p1, p2)
        self._center = CAD_Math.mirror_point(self._center, p1, p2)
        self._rotation_deg = _norm360(2.0 * theta - self._rotation_deg)
        self._regenerate()
        toggle_mirrored(self.style)          # LT5 Q9

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale about ``base`` (DD1): centre scaled, rx / ry ×
        factor (``_AXIS_MIN`` floor), rotation unchanged."""
        from .cad_math import CAD_Math
        self._center = CAD_Math.scale_point(self._center, base, factor)
        self._rx = max(self._rx * factor, _AXIS_MIN)
        self._ry = max(self._ry * factor, _AXIS_MIN)
        self._regenerate()

    def get_properties(self) -> dict:
        props = {
            "Type":     {"type": "label", "value": "Ellipse"},
            "Centre":   {"type": "label",
                         "value": f"({self._center.x():.1f}, {self._center.y():.1f})"},
            "R1": {"type": "dimension",
                   "value": self._fmt(self._rx), "value_mm": self._rx},
            "R2": {"type": "dimension",
                   "value": self._fmt(self._ry), "value_mm": self._ry},
            "Rotation": {"type": "string",
                         "value": f"{self._rotation_deg:.2f}", "suffix": "°"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if key == "R1":
            r = self._parse_dim(value)
            if r is not None and r >= _AXIS_MIN:
                self._dim_edit(self.set_rx, r)
            return
        if key == "R2":
            r = self._parse_dim(value)
            if r is not None and r >= _AXIS_MIN:
                self._dim_edit(self.set_ry, r)
            return
        if key == "Rotation":
            try:
                self._rotation_deg = float(str(value).replace("°", "").strip())
            except (TypeError, ValueError):
                return
            self._regenerate()
            return
        if self._geom2d_set(key, value):
            self._regenerate()
            return

    def to_dict(self) -> dict:
        d = {
            "type":        "draw_ellipse",
            "cx":          self._center.x(),
            "cy":          self._center.y(),
            "rx":          self._rx,
            "ry":          self._ry,
            "rotation":    self._rotation_deg,
        }
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "EllipseItem":
        obj = cls(QPointF(data["cx"], data["cy"]),
                  data["rx"], data["ry"], data.get("rotation", 0.0),
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0))
        obj._geom2d_from_dict(data)
        obj._regenerate()
        return obj

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        rs = self._sync_stroke_pen()
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)),
                          to_scene=self.sceneTransform())
        self._paint_routed_stroke(painter, option, widget, rs,
                                  lambda p: p.drawPath(self.path()))
        if self.isSelected():
            # Dashed major + minor axis reference guides — shown whenever the
            # ellipse is selected (manipulator-wrapped or not): a content aid,
            # NOT the selection highlight. Canonical reference-line style
            # (width-1 dashed) matching the placement-time radial guide.
            ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
            ref.setCosmetic(True)
            painter.setPen(ref)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            gp = self.grip_points()
            painter.drawLine(gp[1], gp[2])   # major axis (major+ ↔ major-)
            painter.drawLine(gp[3], gp[4])   # minor axis (minor+ ↔ minor-)
        self._paint_lt_badge(painter)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            path = path.united(self.get_closed_path())
        return path


# ─────────────────────────────────────────────────────────────────────────────
# SplineItem — editable NURBS / B-spline
# ─────────────────────────────────────────────────────────────────────────────


def _is_bezier_chain(n: int, degree: int, knots, weights) -> bool:
    """True for a non-rational clamped cubic whose every interior knot has
    multiplicity 3 — i.e. a chain of cubic Bézier spans (``n == 3k + 1``)."""
    if degree != 3 or n < 4 or (n - 1) % 3 or not knots:
        return False
    if weights and any(abs(w - 1.0) > 1e-12 for w in weights):
        return False
    if len(knots) != n + 4:
        return False
    k = knots
    if not (k[0] == k[1] == k[2] == k[3] and k[-1] == k[-2] == k[-3] == k[-4]):
        return False
    interior = k[4:-4]
    return all(interior[i] == interior[i + 1] == interior[i + 2]
               and (i == 0 or interior[i] > interior[i - 1])
               for i in range(0, len(interior), 3))


_PERIODIC_WRAP_EPS = 1e-6   # wrapped DXF control points coincide within this


def periodic_control_points(control_points: list[QPointF], degree: int,
                            knots: list[float] | None,
                            weights: list[float] | None) -> list[QPointF] | None:
    """DD7 DXF mapping: the unique control points of a closed uniform cubic.

    A closed DXF SPLINE in the periodic form — degree 3, wrapped control points
    (the last 3 repeat the first 3), a uniform knot vector of ``n + 4`` knots,
    absent or uniform weights — maps to ``SplineItem(unique, closed=True)``.

    Args:
        control_points: The SPLINE's control points as stored (wrapped).
        degree: The SPLINE degree.
        knots: The stored knot vector (required — a periodic SPLINE has one).
        weights: The stored weights, or None / empty.

    Returns:
        The ``n - 3`` unique control points, or None when the SPLINE is not in
        that form (the caller keeps today's verbatim path).
    """
    n = len(control_points)
    if int(degree) != 3 or n < 6 or not knots or len(knots) != n + 4:
        return None
    for a, b in zip(control_points[:3], control_points[-3:]):
        if (abs(a.x() - b.x()) > _PERIODIC_WRAP_EPS
                or abs(a.y() - b.y()) > _PERIODIC_WRAP_EPS):
            return None
    steps = [k1 - k0 for k0, k1 in zip(knots, knots[1:])]
    h = steps[0]
    if h <= 0 or any(abs(st - h) > 1e-9 * max(1.0, abs(h)) for st in steps):
        return None
    if weights and any(abs(w - weights[0]) > 1e-12 * max(1.0, abs(weights[0]))
                       for w in weights):
        return None
    return [QPointF(p) for p in control_points[:-3]]


def _periodic_bezier_spans(control_points: list[QPointF]) -> list[tuple]:
    """The ``n`` cubic Bézier spans ``(b0, b1, b2, b3)`` of a periodic uniform
    cubic (DD7 formulas, see ``_periodic_bezier_path``). Each span's ``b0`` is
    the previous span's ``b3`` object and the last ``b3`` evaluates span 0's
    ``b0`` in the same order, so the seam is bit-exact. Needs >= 3 points."""
    pts = control_points
    n = len(pts)
    p0, p1, p2 = pts[0], pts[1 % n], pts[2 % n]
    b0 = QPointF((p0.x() + 4 * p1.x() + p2.x()) / 6,
                 (p0.y() + 4 * p1.y() + p2.y()) / 6)
    spans = []
    for i in range(n):
        p1, p2, p3 = pts[(i + 1) % n], pts[(i + 2) % n], pts[(i + 3) % n]
        b1 = QPointF((2 * p1.x() + p2.x()) / 3, (2 * p1.y() + p2.y()) / 3)
        b2 = QPointF((p1.x() + 2 * p2.x()) / 3, (p1.y() + 2 * p2.y()) / 3)
        b3 = QPointF((p1.x() + 4 * p2.x() + p3.x()) / 6,
                     (p1.y() + 4 * p2.y() + p3.y()) / 6)
        spans.append((b0, b1, b2, b3))
        b0 = b3
    return spans


def periodic_spline_polyline(control_points: list[QPointF], degree: int,
                             knots: list[float] | None,
                             weights: list[float] | None,
                             distance: float = 0.5,
                             segments: int = 4) -> list[QPointF] | None:
    """DD7 flattening of a closed periodic DXF SPLINE (underlay import).

    Same mapping as ``periodic_control_points`` and the same curve as the
    editable / preview path (``_periodic_bezier_spans``), flattened like
    ezdxf's ``flattening(distance, segments)``: each span is cut into
    ``segments`` pieces, each piece subdivided until its control points lie
    within ``distance`` of its chord.

    Returns:
        The closed loop's vertices WITHOUT a seam duplicate, or None when the
        SPLINE is not in the DD7 periodic form (caller keeps its own path).
    """
    uniq = periodic_control_points(control_points, degree, knots, weights)
    if uniq is None:
        return None

    def _pt(b, t):
        u = 1.0 - t
        c0, c1, c2, c3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        return (c0 * b[0][0] + c1 * b[1][0] + c2 * b[2][0] + c3 * b[3][0],
                c0 * b[0][1] + c1 * b[1][1] + c2 * b[2][1] + c3 * b[3][1])

    def _flat(b):
        (x0, y0), (x3, y3) = b[0], b[3]
        dx, dy = x3 - x0, y3 - y0
        L = math.hypot(dx, dy)
        for x, y in (b[1], b[2]):
            d = (math.hypot(x - x0, y - y0) if L < 1e-12
                 else abs((x - x0) * dy - (y - y0) * dx) / L)
            if d > distance:
                return False
        return True

    def _sub(b, t0, t1):
        """Bézier control points of the piece [t0, t1] (blossoming)."""
        def _blossom(a, c, e):
            q = list(b)
            for t in (a, c, e):
                q = [((1 - t) * q[k][0] + t * q[k + 1][0],
                      (1 - t) * q[k][1] + t * q[k + 1][1]) for k in range(len(q) - 1)]
            return q[0]
        return (_blossom(t0, t0, t0), _blossom(t0, t0, t1),
                _blossom(t0, t1, t1), _blossom(t1, t1, t1))

    out: list[QPointF] = []

    def _emit(b, t0, t1, depth=0):
        piece = _sub(b, t0, t1)
        if depth >= 16 or _flat(piece):
            out.append(QPointF(*_pt(b, t0)))
            return
        tm = (t0 + t1) / 2
        _emit(b, t0, tm, depth + 1)
        _emit(b, tm, t1, depth + 1)

    seg = max(1, int(segments))
    for span in _periodic_bezier_spans(uniq):
        b = tuple((p.x(), p.y()) for p in span)
        for k in range(seg):
            _emit(b, k / seg, (k + 1) / seg)
    return out


def _periodic_bezier_path(control_points: list[QPointF]) -> QPainterPath:
    """Smooth closed (periodic) uniform cubic B-spline as exact cubic Béziers.

    DD7 (scene-tools P1 batch): span *i* uses control points ``i..i+3``
    (wrapped) — ``b0 = (p0+4p1+p2)/6``, ``b1 = (2p1+p2)/3``,
    ``b2 = (p1+2p2)/3``, ``b3 = (p1+4p2+p3)/6`` — drawn natively with
    ``cubicTo`` and closed. Evaluating only the valid knot domain (not the full
    range ezdxf flattens) is what keeps the seam closed with a continuous
    tangent. P4-verified against ``ezdxf.math.closed_uniform_bspline`` to 4e-14
    mm. Needs >= 3 control points (callers guarantee it).
    """
    path = QPainterPath()
    spans = _periodic_bezier_spans(control_points)
    path.moveTo(spans[0][0])
    for _b0, b1, b2, b3 in spans:
        path.cubicTo(b1, b2, b3)
    path.closeSubpath()
    return path


def _bspline_path(control_points: list[QPointF], degree: int,
                  knots: list[float] | None,
                  weights: list[float] | None,
                  closed: bool = False) -> QPainterPath:
    """Build a QPainterPath tessellating a NURBS/B-spline via ezdxf.math.BSpline.

    ezdxf is a pure evaluator here (no DXF I/O) — respects the read-only-DXF
    rule.  ``order = degree + 1``; a curve with fewer control points than
    ``degree+1`` auto-lowers by clamping the order to the control-point count.
    ``closed`` (>= 3 control points) draws the smooth periodic uniform cubic
    instead (DD7, ``_periodic_bezier_path``); degree/knots/weights are ignored.
    """
    path = QPainterPath()
    n = len(control_points)
    if n == 0:
        return path
    if n == 1:
        path.moveTo(control_points[0])
        return path
    if closed and n >= 3:
        return _periodic_bezier_path(control_points)
    if _is_bezier_chain(n, degree, knots, weights):
        # Piecewise-Bézier form (e.g. PDF-imported curves): each span IS a
        # cubic Bézier, so Qt draws it exactly and natively — ~100x faster
        # than the pure-Python NURBS flattening below.
        path.moveTo(control_points[0])
        for i in range(1, n, 3):
            path.cubicTo(control_points[i], control_points[i + 1],
                         control_points[i + 2])
        return path
    from ezdxf.math import BSpline
    order = min(degree + 1, n)
    cps = [(p.x(), p.y()) for p in control_points]
    spline = BSpline(cps, order=order,
                     knots=knots if knots else None,
                     weights=weights if weights else None)
    pts = list(spline.flattening(0.5))
    if not pts:
        return path
    path.moveTo(pts[0][0], pts[0][1])
    for p in pts[1:]:
        path.lineTo(p[0], p[1])
    return path


def _auto_knots(n_points: int, degree: int) -> list[float]:
    """Return the clamped-uniform knot vector ezdxf would generate for *n_points*
    control points at *degree* (already clamped to n_points-1)."""
    from ezdxf.math import BSpline
    order = min(degree + 1, n_points)
    cps = [(0.0, 0.0)] * n_points
    return list(BSpline(cps, order=order).knots())


class SplineItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsPathItem):
    """An editable NURBS/B-spline.

    Data model is the full DXF SPLINE payload (control points + degree + knot
    vector + optional weights) so an imported spline round-trips exactly.
    Authored splines are the constrained subset: cubic (degree lowers under 4
    control points), auto clamped-uniform knots, non-rational.
    ``closed=True`` makes it a smooth periodic closed uniform cubic (DD7); a
    legacy closed spline (first == last control point) stays the clamped,
    kinked form.
    """

    def __init__(self, control_points: list[QPointF], degree: int = 3,
                 knots: list[float] | None = None,
                 weights: list[float] | None = None,
                 color: str | QColor = "#ffffff", lineweight: float = 1.0,
                 *, closed: bool = False):
        super().__init__()
        self._control_points = [QPointF(p) for p in control_points]
        n = len(self._control_points)
        # DD7: a smooth periodic closed spline — valid only with >= 3 control
        # points; always a uniform non-rational cubic (no knots / weights).
        self._closed = bool(closed) and n >= 3
        if self._closed:
            self._degree = 3
            self._knots = None
            self._weights = None
        else:
            self._degree = max(1, min(int(degree), max(n - 1, 1)))
            # ezdxf's BSpline rejects order 1 (a single control point), so a
            # degenerate 0/1-point spline gets no auto knot vector —
            # _bspline_path handles n < 2 via its own early return.
            self._knots = (list(knots) if knots
                           else (_auto_knots(n, self._degree) if n >= 2 else None))
            self._weights = list(weights) if weights else None

        self.init_displayable(level=None)   # level-less primitive (C3)
        self.init_geometry2d()

        self._init_stroke(color, lineweight)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self._regenerate()

    def _regenerate(self):
        self._closed_clears_ends()            # LT5: a spline that closes
        self._stroke_pieces_cache = None      # stroke_pieces() memo (LT3 H3-b)
        self.setPath(_bspline_path(self._control_points, self._degree,
                                   self._knots, self._weights,
                                   closed=self._closed))
        self.update()

    def is_closed(self) -> bool:
        """Periodic (DD7) or the legacy coincident-end (kinked) closed form."""
        if self._closed:
            return True
        cps = self._control_points
        return len(cps) >= 3 and cps[0] == cps[-1]

    def is_periodic(self) -> bool:
        """True for a smooth periodic closed spline (DD7) — not the legacy
        coincident-end form (snap emits no endpoints for it)."""
        return self._closed

    def stroke_pieces(self) -> tuple:
        """Analytic stroke pieces in item-local coords (linetypes.md LT3 H3-b)."""
        # Flattening is the costly step (paint calls this per frame): memoised
        # until _regenerate — the sole setPath site — clears it.
        cached = getattr(self, "_stroke_pieces_cache", None)
        if cached is None:
            from .path_walk import Curve
            c = Curve.from_path(self.path())
            cached = (c,) if len(c.pts) >= 2 else ()
            self._stroke_pieces_cache = cached
        return cached

    def get_closed_path(self) -> QPainterPath | None:
        if not self.is_closed():
            return None
        p = QPainterPath(self.path())
        p.closeSubpath()
        return p

    def grip_points(self) -> list[QPointF]:
        return [QPointF(p) for p in self._control_points]

    def apply_grip(self, index: int, pos: QPointF):
        if 0 <= index < len(self._control_points):
            self._control_points[index] = QPointF(pos)
            self._regenerate()

    def manip_handles(self):
        """U3: expose each control point as a live-apply GripHandle. Control
        points are the spline's defining ("vertex") points — all render round
        per the house rule (vertex grips = round disc; midpoints = square); a
        spline has no midpoint/convenience grips. No move-centre grip (move is
        the manipulator's interior-drag). The manipulator renders/hit-tests/
        commits them; the legacy grip paths skip this item (coexistence gate)."""
        from .manip_handle import default_grip_handles
        return default_grip_handles(
            self, circular=set(range(len(self._control_points))))

    def translate(self, dx: float, dy: float):
        self._control_points = [QPointF(p.x() + dx, p.y() + dy)
                                for p in self._control_points]
        self._regenerate()

    def manip_rotate(self, angle_deg: float, pivot: "QPointF") -> None:
        from .cad_math import CAD_Math
        self._control_points = [CAD_Math.rotate_point(p, pivot, -angle_deg)
                                for p in self._control_points]
        self._regenerate()

    def manip_reflect(self, p1: "QPointF", p2: "QPointF") -> None:
        """Baked mirror of the control points across the line p1-p2 (DD1).

        Only the control points change: degree, knots, weights and any closed
        flag (Slice 8 ``_closed``) are left exactly as they are."""
        if _degenerate_axis(p1, p2):
            return              # zero-length axis: no-op, never half-applied
        from .cad_math import CAD_Math
        self._control_points = [CAD_Math.mirror_point(p, p1, p2)
                                for p in self._control_points]
        self._regenerate()
        toggle_mirrored(self.style)          # LT5 Q9

    def manip_scale_about(self, base: "QPointF", factor: float) -> None:
        """Baked uniform scale of the control points about ``base`` (DD1);
        degree / knots / weights / closed flag untouched."""
        from .cad_math import CAD_Math
        self._control_points = [CAD_Math.scale_point(p, base, factor)
                                for p in self._control_points]
        self._regenerate()

    def get_properties(self) -> dict:
        props = {
            "Type":     {"type": "label", "value": "Spline"},
            "Points":   {"type": "label", "value": str(len(self._control_points))},
            "Degree":   {"type": "label", "value": str(self._degree)},
            "Rational": {"type": "label", "value": "yes" if self._weights else "no"},
        }
        props.update(self._geom2d_properties())
        return props

    def set_property(self, key: str, value):
        if self._geom2d_set(key, value):
            self._regenerate()
            return

    def to_dict(self) -> dict:
        d = {
            "type":           "draw_spline",
            "control_points": [[p.x(), p.y()] for p in self._control_points],
            "degree":         self._degree,
            "knots":          list(self._knots) if self._knots else None,
            "weights":        list(self._weights) if self._weights else None,
        }
        if self._closed:
            d["closed"] = True          # DD7: written only when set
        return self._geom2d_to_dict(d)

    @classmethod
    def from_dict(cls, data: dict) -> "SplineItem":
        cps = [QPointF(x, y) for x, y in data["control_points"]]
        obj = cls(cps, data.get("degree", 3),
                  data.get("knots"), data.get("weights"),
                  data.get("color", "#ffffff"), data.get("lineweight", 1.0),
                  closed=bool(data.get("closed", False)))
        obj._geom2d_from_dict(data)
        obj._regenerate()
        return obj

    def paint(self, painter, option, widget=None):
        option.state &= ~QStyle.StateFlag.State_Selected
        rs = self._sync_stroke_pen()
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                from .displayable_item import draw_fill
                draw_fill(painter, cp, self.scene(), self.fill_type,
                          self.fill_pattern, self._display_fill_color or "#888888",
                          alpha=int(round(self.fill_opacity * 255)),
                          to_scene=self.sceneTransform())
        self._paint_routed_stroke(painter, option, widget, rs,
                                  lambda p: p.drawPath(self.path()))
        if self.isSelected():
            # Dashed control-polygon reference guide (straight lines between the
            # control points) — shown whenever selected (manipulator or not):
            # a content aid, NOT the selection highlight. Canonical reference-
            # line style, matching the placement-time control-polygon guide.
            if len(self._control_points) >= 2:
                ref = QPen(self.pen().color(), 1, Qt.PenStyle.DashLine)
                ref.setCosmetic(True)
                painter.setPen(ref)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                legs = list(zip(self._control_points, self._control_points[1:]))
                if self._closed:        # periodic: the guide is a loop
                    legs.append((self._control_points[-1], self._control_points[0]))
                for a, b in legs:
                    painter.drawLine(a, b)
        self._paint_lt_badge(painter)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(_scene_hit_width(self))
        path = stroker.createStroke(self.path())
        if getattr(self, "fill_type", "none") != "none":
            cp = self.get_closed_path()
            if cp is not None:
                path = path.united(cp)
        return path


# ─────────────────────────────────────────────────────────────────────────────
# GeometryTemplate — pre-placement defaults for geometry tools
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Pure geometry helpers — shared by 2D-geo / wall / floor rectangle placement
# ─────────────────────────────────────────────────────────────────────────────

# Grip indices (clockwise from top-left): 0 TL 1 TM 2 TR 3 RM 4 BR 5 BM 6 BL 7 LM 8 C
_RECT_CORNER_OPPOSITE = {0: 4, 2: 6, 4: 0, 6: 2}


def rect_grip_resize(r0: QRectF, index: int, p: QPointF,
                     from_center: bool, keep_aspect: bool) -> QRectF:
    """New LOCAL rect after dragging grip *index* of the press-time rect *r0*.

    Args:
        r0: The press-time rect, in the item's LOCAL (axis-aligned) frame.
        index: Grip index (0 TL, 1 TM, 2 TR, 3 RM, 4 BR, 5 BM, 6 BL, 7 LM,
            8 centre).
        p: The drag point in the same LOCAL frame.
        from_center: Ctrl — resize symmetrically about the ``r0`` centre.
        keep_aspect: Shift — keep ``r0``'s aspect ratio (corners only; no
            effect on edge grips).

    Returns:
        The new normalised local rect. The centre grip (8) translates.
    """
    cx, cy = r0.center().x(), r0.center().y()
    l, t, ri, b = r0.left(), r0.top(), r0.right(), r0.bottom()
    if index == 8:
        return r0.translated(p.x() - cx, p.y() - cy)
    if index in _RECT_CORNER_OPPOSITE:
        pts = {0: (l, t), 2: (ri, t), 4: (ri, b), 6: (l, b)}
        ox, oy = pts[index]
        ax, ay = (cx, cy) if from_center else pts[_RECT_CORNER_OPPOSITE[index]]
        dx, dy = p.x() - ax, p.y() - ay
        if keep_aspect:
            bx, by = ox - ax, oy - ay
            fx = dx / bx if bx else 0.0
            fy = dy / by if by else 0.0
            s = fx if abs(fx) >= abs(fy) else fy
            dx, dy = s * bx, s * by
        corner = QPointF(ax + dx, ay + dy)
        other = QPointF(ax - dx, ay - dy) if from_center else QPointF(ax, ay)
        return QRectF(corner, other).normalized()
    # Edges: one axis only (Shift has no effect).
    if index in (1, 5):
        y = p.y()
        if from_center:
            return QRectF(QPointF(l, y), QPointF(ri, 2 * cy - y)).normalized()
        return QRectF(QPointF(l, y), QPointF(ri, b if index == 1 else t)).normalized()
    if index in (3, 7):
        x = p.x()
        if from_center:
            return QRectF(QPointF(x, t), QPointF(2 * cx - x, b)).normalized()
        return QRectF(QPointF(x, t), QPointF(l if index == 3 else ri, b)).normalized()
    return QRectF(r0)


def rect_side_frame(base, side_pt):
    """Return the frame of the first rect side ``base → side_pt``.

    Args:
        base: The first placement click (QPointF).
        side_pt: The second placement click (QPointF).

    Returns:
        ``(length, angle_deg, (nx, ny))`` — ``angle_deg`` is Y-up degrees CCW
        from +x and ``(nx, ny)`` the unit left normal (Qt coords), the
        direction a POSITIVE depth extends.  None when the side is degenerate.
    """
    dx, dy = side_pt.x() - base.x(), side_pt.y() - base.y()
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    ux, uy = dx / length, dy / length
    return length, math.degrees(math.atan2(-dy, dx)), (uy, -ux)


def rect_signed_depth(base, side_pt, cursor) -> float:
    """Signed perpendicular distance of *cursor* from the side line (+ = left).

    Returns 0.0 for a degenerate side.
    """
    f = rect_side_frame(base, side_pt)
    if f is None:
        return 0.0
    nx, ny = f[2]
    return (cursor.x() - base.x()) * nx + (cursor.y() - base.y()) * ny


def rect_side_ghost(base, cursor, from_center):
    """Return the segment drawn while picking the first side.

    ``base → cursor`` in the corner variant; the full side centred on *base*
    (mirrored through it) in the centre variant.
    """
    if from_center:
        return (QPointF(2 * base.x() - cursor.x(), 2 * base.y() - cursor.y()),
                QPointF(cursor))
    return QPointF(base), QPointF(cursor)


def rect_from_side_and_depth(base, side_pt, depth, from_center):
    """Solve the 3-click rectangle (base → side → depth; 2d-geometry.md §4).

    Corner variant: *base* is a corner, ``base → side_pt`` is the first side
    (W, angle) and *depth* the signed second side (H, + = left of the side).
    Centre variant: *base* is the centre, ``|base → side_pt|`` is HALF of W
    along the angle and ``|depth|`` is half of H.

    Args:
        base: First click (corner or centre), QPointF.
        side_pt: Second click (side end or side midpoint), QPointF.
        depth: Signed perpendicular depth (see ``rect_signed_depth``).
        from_center: True for the centre variant.

    Returns:
        ``(pt1, pt2, angle_deg, pivot)`` such that
        ``RectangleItem(pt1, pt2).set_angle(angle_deg, pivot)`` and
        ``rotated_rect_corners(pt1, pt2, angle_deg, pivot)`` give the
        rectangle — the unrotated local rect about ``pivot = base``.  None
        when a FULL extent is under 0.5 mm.
    """
    return _rect_solve(base, side_pt, depth, from_center, 0.5)


def _rect_solve(base, side_pt, depth, from_center, min_extent):
    """``rect_from_side_and_depth`` with the minimum FULL extent as a parameter.

    ``min_extent=0.0`` admits a zero-depth (line-along-the-side) rect — the
    ghost shape — while commits use the 0.5 mm floor.  None for a
    degenerate (zero-length) side whatever the floor.
    """
    f = rect_side_frame(base, side_pt)
    if f is None:
        return None
    length, angle, _n = f
    bx, by = base.x(), base.y()
    if from_center:
        h = abs(depth)
        if 2 * length < min_extent or 2 * h < min_extent:
            return None
        return (QPointF(bx - length, by - h), QPointF(bx + length, by + h),
                angle, QPointF(base))
    if length < min_extent or abs(depth) < min_extent:
        return None
    # Unrotated local frame: the side runs +x from base, positive depth is
    # Y-up (screen -y); set_angle then turns it about base onto the real side.
    r = QRectF(QPointF(bx, by), QPointF(bx + length, by - depth)).normalized()
    return r.topLeft(), r.bottomRight(), angle, QPointF(base)


def apply_rect_ghost(preview, base, side_pt, cursor, from_center):
    """Fit a ``QGraphicsRectItem`` ghost to the 3-click rect at *cursor*.

    One home for the 2D / wall / floor depth-step ghost.  Uses the same Qt
    transform ``RectangleItem.set_angle`` does, so the ghost matches the
    committed item.  The ghost is drawn WITHOUT the 0.5 mm floor, so a
    near-zero depth shows as a line along the first side (not a stale shape).

    Returns:
        The ``rect_from_side_and_depth`` solution — None when a full extent is
        under 0.5 mm (the commit would refuse it) even though the ghost was
        still drawn.
    """
    depth = rect_signed_depth(base, side_pt, cursor)
    ghost = _rect_solve(base, side_pt, depth, from_center, 0.0)
    if preview is not None and ghost is not None:
        pt1, pt2, ang, piv = ghost
        preview.setRotation(0.0)
        preview.setRect(QRectF(pt1, pt2).normalized())
        preview.setTransformOriginPoint(piv)
        preview.setRotation(-ang)        # Y-up CCW → Qt CW negate
    return rect_from_side_and_depth(base, side_pt, depth, from_center)


def rotated_rect_corners(pt1, pt2, angle_deg, pivot):
    """Return the four scene-space corners (TL, TR, BR, BL) of an axis-aligned
    rect after applying a Y-up CCW rotation of ``angle_deg`` about ``pivot``.

    This replicates what ``RectangleItem(pt1, pt2).set_angle(angle_deg, pivot)``
    + ``mapToScene(local_corner)`` produces:

    * ``set_angle`` calls ``setRotation(-angle_deg)`` (Y-up CCW → Qt CW negate).
    * Qt's ``mapToScene`` with rotation ``-angle_deg`` applies the matrix:
      ``x' = cos(a)*dx + sin(a)*dy``, ``y' = -sin(a)*dx + cos(a)*dy``
      where ``dx = p.x() - pivot.x()``, ``dy = p.y() - pivot.y()``.

    Args:
        pt1: Top-left corner of the axis-aligned rect (QPointF).
        pt2: Bottom-right corner of the axis-aligned rect (QPointF).
        angle_deg: Y-up CCW angle in degrees.
        pivot: Scene-space rotation origin (QPointF).

    Returns:
        List of four QPointF in order TL, TR, BR, BL.
    """
    from .cad_math import CAD_Math
    local = [
        QPointF(pt1.x(), pt1.y()),   # TL
        QPointF(pt2.x(), pt1.y()),   # TR
        QPointF(pt2.x(), pt2.y()),   # BR
        QPointF(pt1.x(), pt2.y()),   # BL
    ]
    # Y-up CCW angle → CAD_Math's screen-space rotate takes the negation
    # (the same CW negate ``set_angle`` applies via ``setRotation``).
    return [CAD_Math.rotate_point(p, pivot, -angle_deg) for p in local]


_LINETYPE_TIP = ("Linetype of the stroke. Continuous is solid; linetypes "
                 "from the Linetypes folder load into the project when picked.")
_WEIGHT_TIP = ("Line weight. By Linetype uses the linetype's designed weight "
               "(shown in brackets); a named weight overrides it.")
_LOCKED_LINETYPE_TIP = "Lines inside a linetype are always Continuous"
_LOCKED_END_LINETYPE_TIP = "Lines inside an end type are always Continuous"
_LOCKED_WEIGHT_TIP = ("New lines take the linetype's Weight "
                      "(set it in the Repeat section)")
_PLACEMENT_LINETYPE_TIP = (
    "Linetype for every stroke in this block, nested blocks included. "
    "As Authored keeps each stroke's own linetype.")
_PLACEMENT_WEIGHT_TIP = (
    "Line weight for every stroke in this block, nested blocks included. "
    "As Authored keeps each stroke's own weight; By Category uses the "
    "Display Manager “Blocks” weight (shown in brackets).")
_LOCKED_PLACEMENT_TIP = (
    "Strokes in a pattern tile or linetype unit draw Continuous at the "
    "pattern's own pen, so a nested block can't override them here.")

# LT5 Q10 panel rows -> (end, record field).
_END_ROW_KEYS = {"Start End": ("start", "end"), "Finish End": ("finish", "end"),
                 "Start Visible": ("start", "visible"),
                 "Finish Visible": ("finish", "visible")}
_END_TIP = ("End type drawn at this end of the line. By Linetype uses the "
            "linetype's default (shown in brackets); None draws a plain end. "
            "End types from the End Types folder load into the project when "
            "picked.")
_END_VISIBLE_TIP = ("Show this end's end type. Off draws a plain end but "
                    "keeps the pick.")
_LOCKED_END_TIP = "Lines inside an end type are always Continuous with plain ends"
_LOCKED_LT_END_TIP = ("Lines inside a linetype draw plain ends -- set the "
                      "linetype's default ends in its Start End / Finish End rows")
_LOCKED_TILE_END_TIP = "Lines inside a pattern tile draw plain ends"


def _ends_lock_tip(scene) -> str | None:
    """Why the end rows are locked in *scene* (a capability Block Editor:
    end type Q8, linetype / pattern tile seam I3), or None (unlocked)."""
    if getattr(scene, "block_end", None) is not None:
        return _LOCKED_END_TIP
    if getattr(scene, "block_repeat", None) is not None:
        return _LOCKED_LT_END_TIP
    if getattr(scene, "block_tile", None) is not None:
        return _LOCKED_TILE_END_TIP
    return None


def _end_rows(style: dict, registry, exclude, locked_tip: str | None) -> dict:
    """Start End / Finish End + Start / Finish Visible rows (LT5 Q10).

    Args:
        style: The primitive's style record.
        registry: Project block registry (or None).
        exclude: Block ids the picker must not offer (``picker_exclude``).
        locked_tip: Disable every row with this "why" tooltip (a capability
            Block Editor, :func:`_ends_lock_tip`); None = editable.

    Returns:
        The four rows: the two pickers, then the two Visible checkboxes.
    """
    from .capabilities import end_choices
    from .stroke_style import BY_LINETYPE, _end, end_label
    choices = end_choices(registry, exclude)
    rows, vis = {}, {}
    for which, title in (("start", "Start"), ("finish", "Finish")):
        rec = _end(style.get(which))
        ref = rec["end"]
        head = end_label(BY_LINETYPE, style["linetype"], registry, which=which)
        options = [head, *(n for n, _ in choices)]
        value = (head if ref == BY_LINETYPE
                 else next((n for n, r in choices if r == ref), None))
        if value is None:
            # Q13: an unresolvable / non-end id shows as missing (kept until
            # re-picked).
            value = end_label(ref, style["linetype"], registry, which=which)
            options = [value] + options
        rows[f"{title} End"] = {"type": "enum", "options": options,
                                "value": value, "tooltip": _END_TIP}
        vis[f"{title} Visible"] = {"type": "bool", "value": bool(rec["visible"]),
                                   "tooltip": _END_VISIBLE_TIP}
    rows.update(vis)
    if locked_tip:
        for meta in rows.values():
            meta["disabled"] = True
            meta["tooltip"] = locked_tip
    return rows


def _is_block_only_weight_label(value) -> bool:
    """True for a placement-only Weight label (WM2 Q5): "As Authored" or
    "By Category (...)" -- never a primitive value."""
    from .stroke_style import AS_AUTHORED_LABEL, BY_CATEGORY_LABEL
    v = str(value)
    return v == AS_AUTHORED_LABEL or v.startswith(BY_CATEGORY_LABEL)


def stroke_rows(style: dict, registry, exclude=(), *, locked: bool = False,
                placement: bool = False, ends: bool = False,
                ends_locked_tip: str | None = None,
                locked_tip: str | None = None) -> dict:
    """Linetype + Weight panel rows for a style record (WM1; shared by
    primitives and the GeometryTemplate).

    Args:
        style: ``{"linetype", "weight", ...}`` (a primitive record or the
            current).
        registry: Project block registry (or None).
        exclude: Linetype ids the picker must not offer (``picker_exclude``).
        locked: The primitive lives in a linetype Block Editor (LT4-4 / H4-f):
            the Linetype row is disabled with a "why" tooltip.
        placement: Rows for a placed block / nested record (WM2 Q4): As
            Authored + By Category instead of By Linetype.
        ends: Add the LT5 Start End / Finish End / Visible rows (open
            primitives only -- never the template or a placement).
        ends_locked_tip: Disable the end rows with this "why" tooltip (a
            capability Block Editor: end type Q8, linetype / tile I3).
        locked_tip: The locked Linetype row's "why" tooltip (default: the
            linetype-unit one).
    """
    from .paper_display import model_blocks_weight as _pd_blocks
    from .paper_display import picker_weight_name, weight_names
    from .linetype_choices import linetype_choices, missing_label
    from .stroke_style import (AS_AUTHORED, AS_AUTHORED_LABEL, BY_CATEGORY,
                               BY_CATEGORY_LABEL, BY_LINETYPE, weight_label)
    lt = style["linetype"]
    choices = linetype_choices(registry, exclude)
    if placement:
        choices = [(AS_AUTHORED_LABEL, AS_AUTHORED), *choices]
    options = [n for n, _ in choices]
    value = next((n for n, r in choices if r == lt), None)
    if value is None:
        # LT3-10: an unresolvable id shows as missing (kept until re-picked).
        value = missing_label(lt)
        options = [value] + options
    w = style["weight"]
    if placement:
        by_cat = f"{BY_CATEGORY_LABEL} ({picker_weight_name(_pd_blocks())})"
        head = [AS_AUTHORED_LABEL, by_cat]
        value_w = {AS_AUTHORED: AS_AUTHORED_LABEL,
                   BY_CATEGORY: by_cat}.get(w) or picker_weight_name(w)
        tip_lt, tip_w = _PLACEMENT_LINETYPE_TIP, _PLACEMENT_WEIGHT_TIP
    else:
        by_lt = weight_label(BY_LINETYPE, lt, registry)
        head = [by_lt]
        value_w = by_lt if w == BY_LINETYPE else picker_weight_name(w)
        tip_lt, tip_w = _LINETYPE_TIP, _WEIGHT_TIP
    rows = {
        "Linetype": {"type": "enum", "options": options, "value": value,
                     "tooltip": tip_lt},
        "Weight": {"type": "enum", "options": [*head, *weight_names()],
                   "value": value_w, "tooltip": tip_w},
    }
    if locked:
        rows["Linetype"]["disabled"] = True
        rows["Linetype"]["tooltip"] = locked_tip or _LOCKED_LINETYPE_TIP
    if ends:
        rows.update(_end_rows(style, registry, exclude, ends_locked_tip))
    return rows


class GeometryTemplate:
    """Pre-placement template for the 2D draw tools (property-panel.md §3.7).

    Its Linetype / Weight rows ARE the current style for the next primitive
    (linetypes.md WM-10): a pick here moves the current; editing a selected
    primitive never does. ``_scene_ref`` (set by the scene's
    ``_get_geometry_template``) supplies the project registry for the
    picker; the template is off-scene, so it has no ``scene()``.
    """

    def __init__(self, scene=None):
        # Level-less (containment C3): geometry templates carry no level.
        self.name: str = "(Template)"
        self._scene_ref = scene

    def _registry(self):
        return getattr(self._scene_ref, "block_registry", None)

    def _exclude(self):
        from .hatch_patterns import picker_exclude
        return picker_exclude(self._scene_ref)

    def get_properties(self) -> dict:
        from . import stroke_style as ss
        cur = ss.current_style()
        if getattr(self._scene_ref, "block_repeat", None) is not None:
            return self._linetype_unit_properties(cur)
        if getattr(self._scene_ref, "block_end", None) is not None:
            return self._end_unit_properties(cur)
        if (ss.is_linetype_ref(cur["linetype"])
                and ss.linetype_block(cur["linetype"], self._registry()) is None):
            ss.set_current(linetype=ss.CONTINUOUS)       # WM1: not in this project
            cur = ss.current_style()
        props = {"Type": {"type": "label", "value": "Geometry"}}
        props.update(stroke_rows(cur, self._registry(), self._exclude()))
        props["Linetype"]["tooltip"] = (
            "Linetype for the next primitive you draw (kept between sessions). "
            "Linetypes from the Linetypes folder load into the project when picked.")
        props["Weight"]["tooltip"] = (
            "Line weight for the next primitive you draw (kept between sessions). "
            "By Linetype uses the linetype's designed weight (shown in brackets).")
        return props

    def _linetype_unit_properties(self, cur: dict) -> dict:
        """Rows inside a linetype Block Editor (LT4-4 / H4-f).

        Show what ``stroke_style.apply_current`` will actually stamp on the
        next primitive -- Continuous and the linetype's dash Weight (the
        current Weight when there is no single dash weight) -- both locked.
        The stored current is never changed here (WM-10).
        """
        from . import stroke_style as ss
        from .linetype_authoring import pattern_weight
        shown = {"linetype": ss.CONTINUOUS,
                 "weight": pattern_weight(self._scene_ref) or cur["weight"]}
        props = {"Type": {"type": "label", "value": "Geometry"}}
        props.update(stroke_rows(shown, self._registry(), self._exclude(),
                                 locked=True))
        props["Weight"]["disabled"] = True
        props["Weight"]["tooltip"] = _LOCKED_WEIGHT_TIP
        return props

    def _end_unit_properties(self, cur: dict) -> dict:
        """Rows inside an end-type Block Editor (LT5 Q8): Linetype shows
        Continuous, locked; Weight stays the current (end strokes draw at
        the using line's weight, Q7). The stored current is never changed."""
        from . import stroke_style as ss
        shown = {"linetype": ss.CONTINUOUS, "weight": cur["weight"]}
        props = {"Type": {"type": "label", "value": "Geometry"}}
        props.update(stroke_rows(shown, self._registry(), self._exclude(),
                                 locked=True, locked_tip=_LOCKED_END_LINETYPE_TIP))
        props["Weight"]["tooltip"] = (
            "Line weight for the next primitive you draw (kept between "
            "sessions). End strokes draw at the using line's weight.")
        return props

    def set_property(self, key: str, value):
        from . import stroke_style as ss
        if key == "Weight":
            ss.set_current(weight=ss.weight_from_label(value))
        elif key == "Linetype":
            from .linetype_choices import (ensure_linetype_available,
                                           is_missing_label,
                                           linetype_ref_from_value)
            if is_missing_label(str(value)):
                return
            ref = linetype_ref_from_value(str(value), self._registry(),
                                          self._exclude())
            if ref is None:
                return
            if not ensure_linetype_available(ref, self._scene_ref):
                return                                   # failed folder load
            ss.set_current(linetype=ref)
