"""Constraint canvas paint + glyph pick — parametric-constraint-system.md §10, D3/D4, D11, D27.

Painted in viewport px after ``resetTransform`` (the ``readout_paint`` idiom):
screen-constant, non-printing, never part of a scene item. Draws, in order,
the non-printing X/Y axes through the fixed origin (D3/D4), the target glow
of the hovered / selected constraint (D11), the boxed glyphs (D27) and, when
a pick session is live, its markers (D21, Task 12).

Pick order (§10): grips > dim labels > glyphs > origin/axes > HALO geometry.
:func:`glyph_at` defers to a manipulator grip under the point; the caller
(``Model_View``) runs the readout label pick first and HALO after.

D32 visibility: a glyph shows only for a constraint touching a currently
selected entity, plus the selected constraint itself; Show Constraints
(``ctl.show_all``) is a temporary show-every-glyph override; a pick session
shows none (its markers carry the picking). Only visible glyphs pick.

VC9 F3: the visible set, the ``uid -> item`` map and the glyph layouts are
computed ONCE per frame (:func:`_frame`, keyed on the controller's
scene-change and selection counters, the view transform / size, the show-all
flag, the selected constraint, the pick session and the constraint list) and
shared by :func:`dirty_rect`, :func:`paint` and :func:`glyph_at`.
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPen

from . import sketch_model as sm
from . import theme as th
from .icons import DARK, LIGHT, themed_icon
from .sketch_adapters import adapter_for
from .theme import M


def _icon_theme() -> str:
    return DARK if th.detect().name == "dark" else LIGHT


def _box_px() -> int:
    return M.CONSTRAINT_GLYPH_PX + 2 * M.CONSTRAINT_GLYPH_PAD_PX


def _held_fn(ctl):
    """``item -> QTransform | None``: the live manipulator's held-preview
    delta (rest-pose scene -> drawn scene) mid-gesture, else None."""
    live = getattr(ctl._scene, "_live_manip", None)
    manip = live() if callable(live) else None
    if manip is None or not manip.is_dragging():
        return None
    return manip.held_delta


def _ref_geom(ref, by, held=None):
    """Scene-space geometry of one ref, where the item is DRAWN.

    Adapter values are the rest pose; under a held-transform preview
    (*held*, :func:`_held_fn`) the points are mapped through the item's held
    delta, so the anchor and the (``sceneBoundingRect``) centroid share one
    frame -- a mixed frame side-flips the glyph mid-drag (S1).

    Returns:
        ``("point", QPointF)``, ``("edge", (QPointF, QPointF))``,
        ``("axis", "x_axis" | "y_axis")`` or None when it does not resolve.
    """
    if not isinstance(ref, dict):
        return None
    if "ref" in ref:
        g = ref["ref"]
        if g == "origin":
            return "point", QPointF(0.0, 0.0)
        return ("axis", g) if g in ("x_axis", "y_axis") else None
    it = by.get(ref.get("uid"))
    h = ref.get("h")
    if it is None or not isinstance(h, str):
        return None
    ad = adapter_for(it)
    if ad is None:
        return None
    x = np.array(ad.read(it), dtype=float)
    t = held(it) if held is not None else None

    def _p(e):
        q = QPointF(*e.eval(x)[0])
        return t.map(q) if t is not None else q
    pts = ad.points(it, 0)
    if h in pts:
        return "point", _p(pts[h])
    eds = ad.edges(it, 0)
    if h in eds:
        a, b = eds[h]
        return "edge", (_p(a), _p(b))
    return None


def _centroid(ref, by) -> QPointF | None:
    it = by.get(ref.get("uid")) if isinstance(ref, dict) else None
    return it.sceneBoundingRect().center() if it is not None else None


def _away(dx, dy, mid, cen) -> tuple[float, float]:
    """Unit (dx, dy) flipped to point away from *cen*; a tie (the centroid on
    the anchor's line) breaks toward screen-down, then screen-right."""
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return 0.0, 1.0
    dx, dy = dx / L, dy / L
    s = 0.0 if cen is None else (mid.x() - cen.x()) * dx + (mid.y() - cen.y()) * dy
    if abs(s) < 1e-6:
        s = dy if abs(dy) > 1e-6 else dx
    return (dx, dy) if s > 0 else (-dx, -dy)


def _anchor(view, c, by, held=None) -> QPointF | None:
    """Viewport-px centre of *c*'s glyph: 12 px off its geometry (plus half
    the box) on the side away from the entity centroid (D27)."""
    geoms = [(r, _ref_geom(r, by, held)) for r in c.refs]
    geoms = [(r, g) for r, g in geoms if g is not None and g[0] != "axis"]
    if not geoms:
        return None
    d = M.CONSTRAINT_GLYPH_OFFSET_PX + _box_px() / 2.0
    edge = next(((r, g) for r, g in geoms if g[0] == "edge"), None)
    if edge is not None:
        r, (_k, (a, b)) = edge
        va, vb = QPointF(view.mapFromScene(a)), QPointF(view.mapFromScene(b))
        mid = (va + vb) / 2.0
        cen = _centroid(r, by)
        cen = QPointF(view.mapFromScene(cen)) if cen is not None else None
        nx, ny = _away(-(vb.y() - va.y()), vb.x() - va.x(), mid, cen)
    else:
        vps = [QPointF(view.mapFromScene(g[1])) for _r, g in geoms]
        mid = QPointF(sum(p.x() for p in vps) / len(vps),
                      sum(p.y() for p in vps) / len(vps))
        cens = [_centroid(r, by) for r, _g in geoms]
        cens = [QPointF(view.mapFromScene(q)) for q in cens if q is not None]
        if len(vps) >= 2 and (vps[-1] - vps[0]).manhattanLength() > 1e-6:
            dv = vps[-1] - vps[0]
            ref_pt = (QPointF(sum(q.x() for q in cens) / len(cens),
                              sum(q.y() for q in cens) / len(cens))
                      if cens else None)
            nx, ny = _away(-dv.y(), dv.x(), mid, ref_pt)
        else:
            cen = cens[0] if cens else None
            dx, dy = ((mid.x() - cen.x(), mid.y() - cen.y())
                      if cen is not None else (0.0, 1.0))
            nx, ny = _away(dx, dy, mid, cen) if math.hypot(dx, dy) > 1e-6 else (0.0, 1.0)
    return QPointF(mid.x() + nx * d, mid.y() + ny * d)


# ── D32 visibility + the per-frame cache (VC9 F3) ───────────────────────────

def visible_constraints(ctl, sel_uids) -> list:
    """D32: the constraints whose glyphs show.

    None during a pick session; every one under the Show Constraints
    override (``ctl.show_all``); else those touching a selected entity
    (*sel_uids*) plus the selected constraint.
    """
    if not ctl.enabled or getattr(ctl, "pick", None) is not None:
        return []
    if ctl.show_all:
        return list(ctl.constraints)
    from .constraint_controller import _safe_ref_uids
    return [c for c in ctl.constraints
            if c.id == ctl.selected_id or (_safe_ref_uids(c) or set()) & sel_uids]


def _selected_uids(ctl) -> set:
    try:
        sel = ctl._scene.selectedItems()
    except RuntimeError:                       # a dying scene
        return set()
    out = {getattr(it, "_uid", None) for it in sel}
    out.discard(None)
    return out


class _Frame:
    """One frame's glyph state: ``uid -> item`` (None when nothing shows),
    the held-preview mapper and the visible glyph layouts."""
    __slots__ = ("by", "held", "layouts")

    def __init__(self, by, held, layouts):
        self.by, self.held, self.layouts = by, held, layouts


def _frame_key(view, ctl) -> tuple:
    t = view.viewportTransform()
    vp = view.viewport()
    return (ctl._scene_gen, ctl._sel_gen, ctl.show_all, ctl.selected_id,
            getattr(ctl, "pick", None) is None, id(ctl.constraints),
            len(ctl.constraints), vp.width(), vp.height(),
            t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy())


def _frame(view, ctl) -> _Frame:
    """This frame's :class:`_Frame` for *view*, cached on the controller.

    The scene-change counter is bumped by ``ctl._on_scene_changed`` (every
    geometry change, incl. a held-preview transform), the selection counter
    by ``ctl._on_selection_changed``; a geometry change painted before its
    ``scene.changed`` arrives is corrected by that slot's old ∪ new repaint.
    """
    key = _frame_key(view, ctl)
    hit = ctl._frames.get(id(view))
    if hit is not None and hit[0] == key:
        return hit[1]
    fr = _compute_layouts(view, ctl)
    ctl._frames[id(view)] = (key, fr)
    return fr


def _compute_layouts(view, ctl) -> _Frame:
    """The uncached frame build (one per frame, VC9 F3)."""
    cons = visible_constraints(ctl, _selected_uids(ctl)) if ctl.constraints else []
    held = _held_fn(ctl)
    if not cons:
        return _Frame(None, held, [])
    by = ctl.item_by_uid()
    return _Frame(by, held, _layout(view, cons, by, held))


def _layout(view, cons, by, held) -> list:
    """``[(cid, QRectF viewport px)]`` for *cons*; several glyphs on one
    anchor sit side by side (D27)."""
    box = _box_px()
    out, used = [], {}
    for c in cons:
        try:
            anchor = _anchor(view, c, by, held)
        except Exception:                      # malformed (inert) record
            anchor = None
        if anchor is None:
            continue
        key = (round(anchor.x()), round(anchor.y()))
        k = used.get(key, 0)
        used[key] = k + 1
        x = round(anchor.x() - box / 2.0) + k * (box + M.CONSTRAINT_GLYPH_GAP_PX)
        y = round(anchor.y() - box / 2.0)
        out.append((c.id, QRectF(x, y, box, box)))
    return out


def glyph_layouts(view, ctl) -> list:
    """``[(cid, QRectF viewport px)]`` — one boxed glyph per VISIBLE
    constraint (D27, D32). Empty when the controller is disabled (plan
    scenes)."""
    if not ctl.enabled:
        return []
    return list(_frame(view, ctl).layouts)


def dirty_rect(view, ctl) -> QRect:
    """Viewport rect covering every visible glyph and the target glow."""
    if not ctl.enabled:
        return QRect()
    fr = _frame(view, ctl)
    out = QRectF()
    for _cid, r in fr.layouts:
        out = out.united(r)
    path = _glow_path(view, ctl, _glow_ids(ctl), fr)
    if not path.isEmpty():
        out = out.united(path.boundingRect())
    if out.isEmpty():
        return QRect()
    pad = M.CONSTRAINT_GLOW_W_PX + 2
    return out.adjusted(-pad, -pad, pad, pad).toAlignedRect()


def _grip_under(view, ctl, vp_pt) -> bool:
    live = getattr(ctl._scene, "_live_manip", None)
    manip = live() if callable(live) else None
    if manip is None or not manip.isVisible():
        return False
    return bool(manip.hit_handle(view.mapToScene(QPointF(vp_pt).toPoint())))


def glyph_at(view, ctl, vp_pt) -> str | None:
    """Constraint id of the VISIBLE glyph under *vp_pt* (viewport px), or None.

    A manipulator grip under the point wins (§10 pick order: grips > glyphs).
    """
    if not ctl.enabled or not ctl.constraints:
        return None
    p = QPointF(vp_pt)
    for cid, r in reversed(_frame(view, ctl).layouts):
        if r.adjusted(-2, -2, 2, 2).contains(p):
            return None if _grip_under(view, ctl, p) else cid
    return None


def _glow_ids(ctl) -> list:
    return [(cid, tok) for cid, tok in ((ctl.selected_id, "selection"),
                                        (ctl.hover_id, "selection_hover"))
            if cid is not None]


def _glow_path(view, ctl, ids, fr=None) -> QPainterPath:
    path = QPainterPath()
    if not ids:
        return path
    by_id = {c.id: c for c in ctl.constraints}
    by = fr.by if fr is not None else None
    held = fr.held if fr is not None else _held_fn(ctl)
    vp = QRectF(view.viewport().rect())
    o = QPointF(view.mapFromScene(QPointF(0.0, 0.0)))
    for cid, _tok in ids:
        c = by_id.get(cid)
        if c is None:
            continue
        by = by if by is not None else ctl.item_by_uid()
        path.addPath(_refs_path(view, c.refs, by, vp, o, held))
    return path


def _refs_path(view, refs, by, vp, o, held=None) -> QPainterPath:
    path = QPainterPath()
    for r in refs:
        try:
            g = _ref_geom(r, by, held)
        except Exception:
            g = None
        if g is None:
            continue
        kind, val = g
        if kind == "point":
            path.addEllipse(QPointF(view.mapFromScene(val)),
                            M.CONSTRAINT_GLOW_POINT_R_PX, M.CONSTRAINT_GLOW_POINT_R_PX)
        elif kind == "edge":
            path.moveTo(QPointF(view.mapFromScene(val[0])))
            path.lineTo(QPointF(view.mapFromScene(val[1])))
        elif val == "x_axis":
            path.moveTo(vp.left(), o.y() + 0.5)
            path.lineTo(vp.right(), o.y() + 0.5)
        else:
            path.moveTo(o.x() + 0.5, vp.top())
            path.lineTo(o.x() + 0.5, vp.bottom())
    return path


def _paint_axes(painter, view, t) -> None:
    o = QPointF(view.mapFromScene(QPointF(0.0, 0.0)))
    vp = QRectF(view.viewport().rect())
    pen = QPen(t.color("muted", int(round(255 * M.CONSTRAINT_AXES_ALPHA))), 1.0)
    pen.setCosmetic(True)
    pen.setDashPattern(list(M.CONSTRAINT_AXES_DASH))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawLine(QPointF(vp.left(), o.y() + 0.5), QPointF(vp.right() + 1, o.y() + 0.5))
    painter.drawLine(QPointF(o.x() + 0.5, vp.top()), QPointF(o.x() + 0.5, vp.bottom() + 1))


_TINT_TOKEN = {"free": "constraint_free", "defined": "ink", "conflict": "danger"}


def _tint_width(it, view) -> float:
    """The item's own stroke width in viewport px (min 1, CS2 gate) plus
    ``CONSTRAINT_TINT_EXTRA_PX``: an anti-aliased stroke straddles two pixel
    rows, so a same-width overlay only half-covers the item's own fringe."""
    pen_fn = getattr(it, "pen", None)
    if not callable(pen_fn):
        return 1.0
    p = pen_fn()
    w = p.widthF()
    if not p.isCosmetic():
        w *= abs(view.transform().m11())
    return max(1.0, w) + M.CONSTRAINT_TINT_EXTRA_PX


def _paint_tint(painter, view, ctl, t) -> None:
    """D39: re-stroke every participating, unselected item's drawn geometry
    (its HALO trace) in its state colour. Text is not tinted (CS2 gate,
    option b: the overlay cannot recolour QGraphicsTextItem glyphs)."""
    if not getattr(ctl, "show_status", False):
        return
    from .halo import halo_scene_path
    from .text_item import TextItem
    d = ctl.diagnostics()
    vt = view.viewportTransform()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for it in ctl.items():
        if isinstance(it, TextItem) or it.isSelected() or not it.isVisible():
            continue
        u = getattr(it, "_uid", None)
        if u is None:
            continue
        pen = QPen(t.color(_TINT_TOKEN[d.state(u)]), _tint_width(it, view))
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.drawPath(vt.map(halo_scene_path(it)))


def paint(painter: QPainter, view, ctl) -> None:
    """Axes, hover/selected target glow, glyphs, then pick markers (one pass)."""
    if not ctl.enabled:
        return
    t = th.detect()
    fr = _frame(view, ctl)
    painted = getattr(ctl, "_painted", None)
    if isinstance(painted, dict):
        painted[id(view)] = dirty_rect(view, ctl)    # old region for the next repaint
    painter.save()
    try:
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _paint_tint(painter, view, ctl, t)
        _paint_axes(painter, view, t)
        # Target glow: selected first, hover on top (D11).
        for cid, tok in _glow_ids(ctl):
            path = _glow_path(view, ctl, [(cid, tok)], fr)
            if path.isEmpty():
                continue
            pen = QPen(t.color(tok, M.CONSTRAINT_GLOW_ALPHA), M.CONSTRAINT_GLOW_W_PX)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        lays = fr.layouts
        if lays:
            by_id = {c.id: c for c in ctl.constraints}
            diag = ctl.diagnostics()
            icon_t = _icon_theme()
            pad = M.CONSTRAINT_GLYPH_PAD_PX
            rad = M.CONSTRAINT_GLYPH_RADIUS_PX
            for cid, r in lays:
                c = by_id[cid]
                if cid == ctl.selected_id:
                    tok, w = "selection", 1.6
                elif cid == ctl.hover_id:
                    tok, w = "selection_hover", 1.0
                elif cid in ctl.red:                      # CS2 D38: conflicting
                    tok, w = "danger", M.CONSTRAINT_STATE_BORDER_W
                elif cid in diag.redundant:               # CS2: redundant (amber)
                    tok, w = "warn", M.CONSTRAINT_STATE_BORDER_W
                else:
                    tok, w = "line_strong", 1.0
                # Suppressed and inert (unsupported, never solved) glyphs are
                # dimmed alike -- the panel's muted "Unsupported constraint"
                # row (VC9 F6); never a live-looking glyph.
                painter.setOpacity(1.0 if c.enabled and not c.inert
                                   else M.CONSTRAINT_INACTIVE_OPACITY)
                painter.setBrush(t.color("surface"))
                painter.setPen(QPen(t.color(tok), w))
                # Inset half a px so a 1 px border covers whole pixel columns.
                painter.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rad, rad)
                icon = themed_icon(sm.icon_for(c.type), icon_t)
                ir = r.adjusted(pad, pad, -pad, -pad).toRect()
                painter.drawPixmap(ir, icon.pixmap(ir.size()))
            painter.setOpacity(1.0)
        pick = getattr(ctl, "pick", None)
        if pick is not None and hasattr(pick, "paint"):
            pick.paint(painter, view, t)
    finally:
        painter.restore()
