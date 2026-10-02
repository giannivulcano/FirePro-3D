"""Pure helpers: convert imported geometry dicts to editable primitives, and
compute a definition origin. No scene, no Qt-parenting — unit-testable with
plain dicts. Shared by the Block Editor and (future) Feature Editor.

See docs/specs/block-system.md §"Block Editor (v2)".
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF

from .geometry_2d import (LineItem, CircleItem, PolylineItem, ArcItem, EllipseItem,
                          SplineItem, periodic_control_points)


def _geometric_bbox(item):
    """Return the pure geometric (pen-free) bounding QRectF for a primitive.

    ``sceneBoundingRect()`` inflates by the cosmetic pen width, which gives
    wrong results for diagonal lines.  We extract the underlying geometry
    directly from each known construction-geometry type.

    Args:
        item: a LineItem, CircleItem, or PolylineItem.

    Returns:
        A ``QRectF`` representing the tight geometric bounding box.
    """
    if isinstance(item, LineItem):
        ln = item.line()
        x_min, x_max = min(ln.x1(), ln.x2()), max(ln.x1(), ln.x2())
        y_min, y_max = min(ln.y1(), ln.y2()), max(ln.y1(), ln.y2())
        return QRectF(x_min, y_min, x_max - x_min, y_max - y_min)
    if isinstance(item, CircleItem):
        # QGraphicsEllipseItem.rect() is the exact bounding geometry.
        return item.rect()
    if isinstance(item, PolylineItem):
        pts = item._points
        if not pts:
            return QRectF(0, 0, 0, 0)
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    if hasattr(item, "geometric_rect"):
        # BlockInstance: pen-free posed bounds (boundingRect adds a pen margin).
        return item.geometric_rect()
    # Fallback for unknown item types — use sceneBoundingRect.
    return item.sceneBoundingRect()


def geometric_bounds(items) -> QRectF | None:
    """Union of the items' pen-free geometric bounding rects.

    Args:
        items: construction-geometry primitives and/or BlockInstances.

    Returns:
        The union ``QRectF``, or None when *items* is empty.
    """
    rects = [_geometric_bbox(it) for it in items]
    if not rects:
        return None
    left = min(r.left() for r in rects)
    top = min(r.top() for r in rects)
    right = max(r.right() for r in rects)
    bottom = max(r.bottom() for r in rects)
    return QRectF(left, top, right - left, bottom - top)


def geom_dicts_to_primitives(geoms, import_scale: float = 1.0, *,
                             lineweight: float = 1.0):
    """Convert kind-tagged import geom dicts to editable primitives.

    Handles ``line`` -> LineItem, ``circle`` -> CircleItem, ``path_points`` ->
    PolylineItem (closed flag honoured), ``arc`` -> ArcItem, ``ellipse_full`` ->
    EllipseItem, ``spline`` -> SplineItem (a closed periodic DXF SPLINE -> a
    periodic one, DD7). Coordinates are multiplied by
    *import_scale* (``real_mm / source_units``); spline knots and weights are
    parametric and are not scaled. Unsupported kinds (``text``, ``unknown``)
    are skipped and counted, never raised.

    A malformed dict of a *supported* kind (missing required keys, wrong value
    type) increments ``skipped`` and continues — KeyError/TypeError never abort
    the batch.

    A path_points dict with exactly 2 points and ``closed=True`` produces an
    open polyline; ``PolylineItem.close()`` is a no-op for fewer than 3 points.

    ``import_scale`` must be > 0.

    Args:
        geoms: list of extraction dicts (dxf/pdf/dwg worker output).
        import_scale: real-mm per source-unit multiplier (must be > 0).
        lineweight: Pen weight for every produced primitive (the Block
            Editor passes the standard new-geometry weight).

    Returns:
        ``(items, skipped)`` — the primitive list and the skipped-dict count.
    """
    s = float(import_scale)
    lw = float(lineweight)
    items = []
    skipped = 0
    for g in geoms:
        kind = g.get("kind")
        color = g.get("color", "#ffffff")
        layer = g.get("layer", "")  # source-layer tag (reference-graphic R1)
        it = None
        if kind == "line":
            try:
                it = LineItem(QPointF(g["x1"] * s, g["y1"] * s),
                              QPointF(g["x2"] * s, g["y2"] * s), color, lw)
            except (KeyError, TypeError):
                skipped += 1
        elif kind == "circle":
            try:
                cx = (g["x"] + g["w"] / 2.0) * s
                cy = (g["y"] + g["h"] / 2.0) * s
                r = (g["w"] / 2.0) * s
                it = CircleItem(QPointF(cx, cy), r, color, lw)
            except (KeyError, TypeError):
                skipped += 1
        elif kind == "path_points":
            pts = g.get("points", [])
            if len(pts) < 2:
                skipped += 1
                continue
            try:
                poly = PolylineItem(QPointF(pts[0][0] * s, pts[0][1] * s), color, lw)
                for px, py in pts[1:]:
                    poly.append_point(QPointF(px * s, py * s))
                if g.get("closed"):
                    poly.close()
                it = poly
            except (KeyError, TypeError):
                skipped += 1
        elif kind == "spline":
            pts = g.get("control_points", [])
            if len(pts) < 2:
                skipped += 1
                continue
            try:
                cps = [QPointF(px * s, py * s) for px, py in pts]
                uniq = (periodic_control_points(cps, int(g.get("degree", 3)),
                                                g.get("knots"), g.get("weights"))
                        if g.get("closed") else None)
                if uniq is not None:          # DD7: closed DXF SPLINE -> periodic
                    it = SplineItem(uniq, 3, None, None, color, lw, closed=True)
                else:
                    it = SplineItem(cps, int(g.get("degree", 3)),
                                    g.get("knots"), g.get("weights"), color, lw)
            except (KeyError, TypeError):
                skipped += 1
        elif kind == "arc":
            try:
                cx = (g["rx"] + g["rw"] / 2.0) * s
                cy = (g["ry"] + g["rh"] / 2.0) * s
                r = (g["rw"] / 2.0) * s
                it = ArcItem(QPointF(cx, cy), r, g["start"], g["span"], color, lw)
            except (KeyError, TypeError):
                skipped += 1
        elif kind == "ellipse_full":
            try:
                cx = g["pos_cx"] * s
                cy = g["pos_cy"] * s
                rx = (g["w"] / 2.0) * s
                ry = (g["h"] / 2.0) * s
                it = EllipseItem(QPointF(cx, cy), rx, ry,
                                 g.get("rotation", 0.0), color, lw)
            except (KeyError, TypeError):
                skipped += 1
        else:
            skipped += 1
        if it is not None:
            if layer:
                it.layer = layer
            items.append(it)
    return items, skipped
