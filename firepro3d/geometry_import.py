"""Pure helpers: convert imported geometry dicts to editable primitives, and
compute a definition origin. No scene, no Qt-parenting — unit-testable with
plain dicts. Shared by the Block Editor and (future) Feature Editor.

See docs/specs/block-system.md §"Block Editor (v2)".
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF

from .construction_geometry import LineItem, CircleItem, PolylineItem


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
    from PyQt6.QtCore import QRectF
    if isinstance(item, LineItem):
        l = item.line()
        x_min, x_max = min(l.x1(), l.x2()), max(l.x1(), l.x2())
        y_min, y_max = min(l.y1(), l.y2()), max(l.y1(), l.y2())
        return QRectF(x_min, y_min, x_max - x_min, y_max - y_min)
    if isinstance(item, CircleItem):
        # QGraphicsEllipseItem.rect() is the exact bounding geometry.
        return item.rect()
    if isinstance(item, PolylineItem):
        pts = item._points
        if not pts:
            from PyQt6.QtCore import QRectF
            return QRectF(0, 0, 0, 0)
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    # Fallback for unknown item types — use sceneBoundingRect.
    return item.sceneBoundingRect()


def bbox_top_left(items) -> QPointF:
    """Top-left (min-x, min-y) of the union of the items' geometric bounding rects.

    Uses the coordinate-level (pen-free) bounding rect so that the result
    reflects the authored geometry, not the visual stroke inflation.

    Args:
        items: construction-geometry primitives (LineItem, CircleItem,
            PolylineItem subclasses).

    Returns:
        The union bounding-rect top-left as a ``QPointF``; (0, 0) when empty.
    """
    if not items:
        return QPointF(0.0, 0.0)
    rects = [_geometric_bbox(it) for it in items]
    min_x = min(r.left() for r in rects)
    min_y = min(r.top() for r in rects)
    return QPointF(min_x, min_y)


def geom_dicts_to_primitives(geoms, import_scale: float = 1.0):
    """Convert kind-tagged import geom dicts to editable primitives.

    Handles ``line`` -> LineItem, ``circle`` -> CircleItem, ``path_points`` ->
    PolylineItem (closed flag honoured). All coordinates are multiplied by
    *import_scale* (``real_mm / source_units``). Unsupported kinds (text,
    ellipse_full, unknown) are skipped and counted, never raised.

    Args:
        geoms: list of extraction dicts (dxf/pdf/dwg worker output).
        import_scale: real-mm per source-unit multiplier.

    Returns:
        ``(items, skipped)`` — the primitive list and the skipped-dict count.
    """
    s = float(import_scale)
    items = []
    skipped = 0
    for g in geoms:
        kind = g.get("kind")
        color = g.get("color", "#ffffff")
        if kind == "line":
            items.append(LineItem(QPointF(g["x1"] * s, g["y1"] * s),
                                  QPointF(g["x2"] * s, g["y2"] * s), color))
        elif kind == "circle":
            cx = (g["x"] + g["w"] / 2.0) * s
            cy = (g["y"] + g["h"] / 2.0) * s
            r = (g["w"] / 2.0) * s
            items.append(CircleItem(QPointF(cx, cy), r, color))
        elif kind == "path_points":
            pts = g.get("points", [])
            if len(pts) < 2:
                skipped += 1
                continue
            poly = PolylineItem(QPointF(pts[0][0] * s, pts[0][1] * s), color)
            for px, py in pts[1:]:
                poly.append_point(QPointF(px * s, py * s))
            if g.get("closed"):
                poly.close()
            items.append(poly)
        else:
            skipped += 1
    return items, skipped
