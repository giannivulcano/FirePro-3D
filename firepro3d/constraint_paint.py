"""Constraint canvas paint + glyph pick — parametric-constraint-system.md §10, D3/D4, D11, D27.

Painted in viewport px after ``resetTransform`` (the ``readout_paint`` idiom):
screen-constant, non-printing, never part of a scene item. Draws, in order,
the non-printing X/Y axes through the fixed origin (D3/D4), the target glow
of the hovered / selected constraint (D11), the boxed glyphs (D27) and, when
a pick session is live, its markers (D21, Task 12).

Pick order (§10): grips > dim labels > glyphs > origin/axes > HALO geometry.
:func:`glyph_at` defers to a manipulator grip under the point; the caller
(``Model_View``) runs the readout label pick first and HALO after.
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPen

from . import theme as th
from .icons import DARK, LIGHT, themed_icon
from .sketch_adapters import adapter_for
from .theme import M

# Hover / selected target glow (approved mockup: 7 px round stroke, ~0.35 alpha).
GLOW_WIDTH_PX = 7.0
GLOW_ALPHA = 90
GLOW_POINT_R_PX = 6.0


def _icon_theme() -> str:
    return DARK if th.detect().name == "dark" else LIGHT


def _box_px() -> int:
    return M.CONSTRAINT_GLYPH_PX + 2 * M.CONSTRAINT_GLYPH_PAD_PX


def _ref_geom(ref, by):
    """Scene-space geometry of one ref.

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
    pts = ad.points(it, 0)
    if h in pts:
        return "point", QPointF(*pts[h].eval(x)[0])
    eds = ad.edges(it, 0)
    if h in eds:
        a, b = eds[h]
        return "edge", (QPointF(*a.eval(x)[0]), QPointF(*b.eval(x)[0]))
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


def _anchor(view, c, by) -> QPointF | None:
    """Viewport-px centre of *c*'s glyph: 12 px off its geometry (plus half
    the box) on the side away from the entity centroid (D27)."""
    geoms = [(r, _ref_geom(r, by)) for r in c.refs]
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


def glyph_layouts(view, ctl) -> list:
    """``[(cid, QRectF viewport px)]`` — one boxed glyph per constraint (D27).

    Several glyphs on one anchor sit side by side. Empty when the controller
    is disabled (plan scenes) or Show Constraints is off.
    """
    if not ctl.enabled or not ctl.show_glyphs or not ctl.constraints:
        return []
    by = ctl.item_by_uid()
    box = _box_px()
    out, used = [], {}
    for c in ctl.constraints:
        try:
            anchor = _anchor(view, c, by)
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


def dirty_rect(view, ctl) -> QRect:
    """Viewport rect covering every glyph and the target glow (repaint region)."""
    out = QRectF()
    for _cid, r in glyph_layouts(view, ctl):
        out = out.united(r)
    path = _glow_path(view, ctl, _glow_ids(ctl))
    if not path.isEmpty():
        out = out.united(path.boundingRect())
    if out.isEmpty():
        return QRect()
    pad = GLOW_WIDTH_PX + 2
    return out.adjusted(-pad, -pad, pad, pad).toAlignedRect()


def _grip_under(view, ctl, vp_pt) -> bool:
    live = getattr(ctl._scene, "_live_manip", None)
    manip = live() if callable(live) else None
    if manip is None or not manip.isVisible():
        return False
    return bool(manip.hit_handle(view.mapToScene(QPointF(vp_pt).toPoint())))


def glyph_at(view, ctl, vp_pt) -> str | None:
    """Constraint id of the glyph under *vp_pt* (viewport px), or None.

    A manipulator grip under the point wins (§10 pick order: grips > glyphs).
    """
    if not ctl.enabled or not ctl.show_glyphs or not ctl.constraints:
        return None
    p = QPointF(vp_pt)
    for cid, r in reversed(glyph_layouts(view, ctl)):
        if r.adjusted(-2, -2, 2, 2).contains(p):
            return None if _grip_under(view, ctl, p) else cid
    return None


def _glow_ids(ctl) -> list:
    return [(cid, tok) for cid, tok in ((ctl.selected_id, "selection"),
                                        (ctl.hover_id, "selection_hover"))
            if cid is not None]


def _glow_path(view, ctl, ids) -> QPainterPath:
    path = QPainterPath()
    by_id = {c.id: c for c in ctl.constraints}
    by = None
    vp = QRectF(view.viewport().rect())
    o = QPointF(view.mapFromScene(QPointF(0.0, 0.0)))
    for cid, _tok in ids:
        c = by_id.get(cid)
        if c is None:
            continue
        by = by if by is not None else ctl.item_by_uid()
        path.addPath(_refs_path(view, c.refs, by, vp, o))
    return path


def _refs_path(view, refs, by, vp, o) -> QPainterPath:
    path = QPainterPath()
    for r in refs:
        try:
            g = _ref_geom(r, by)
        except Exception:
            g = None
        if g is None:
            continue
        kind, val = g
        if kind == "point":
            path.addEllipse(QPointF(view.mapFromScene(val)), GLOW_POINT_R_PX, GLOW_POINT_R_PX)
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


def paint(painter: QPainter, view, ctl) -> None:
    """Axes, hover/selected target glow, glyphs, then pick markers (one pass)."""
    if not ctl.enabled:
        return
    t = th.detect()
    painted = getattr(ctl, "_painted", None)
    if isinstance(painted, dict):
        painted[id(view)] = dirty_rect(view, ctl)    # old region for the next repaint
    painter.save()
    try:
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _paint_axes(painter, view, t)
        # Target glow: selected first, hover on top (D11).
        for cid, tok in _glow_ids(ctl):
            path = _glow_path(view, ctl, [(cid, tok)])
            if path.isEmpty():
                continue
            pen = QPen(t.color(tok, GLOW_ALPHA), GLOW_WIDTH_PX)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        lays = glyph_layouts(view, ctl) if ctl.show_glyphs else []
        if lays:
            by_id = {c.id: c for c in ctl.constraints}
            icon_t = _icon_theme()
            pad = M.CONSTRAINT_GLYPH_PAD_PX
            rad = M.CONSTRAINT_GLYPH_RADIUS_PX
            for cid, r in lays:
                c = by_id[cid]
                if cid == ctl.selected_id:
                    tok, w = "selection", 1.6
                elif cid == ctl.hover_id:
                    tok, w = "selection_hover", 1.0
                else:
                    tok, w = "line_strong", 1.0
                painter.setOpacity(1.0 if c.enabled else 0.4)
                painter.setBrush(t.color("surface"))
                painter.setPen(QPen(t.color(tok), w))
                # Inset half a px so a 1 px border covers whole pixel columns.
                painter.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rad, rad)
                icon = themed_icon(f"constraint_{c.type}_icon.svg", icon_t)
                ir = r.adjusted(pad, pad, -pad, -pad).toRect()
                painter.drawPixmap(ir, icon.pixmap(ir.size()))
            painter.setOpacity(1.0)
        pick = getattr(ctl, "pick", None)
        if pick is not None and hasattr(pick, "paint"):
            pick.paint(painter, view, t)
    finally:
        painter.restore()
