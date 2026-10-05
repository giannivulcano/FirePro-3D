"""LT3 H3-b -- stroke_pieces() traces exactly what each primitive draws."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPathStroker

from firepro3d import path_walk as pw
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RectangleItem,
                                   RegularPolygonItem, SplineItem)


def _items():
    pl = PolylineItem(QPointF(0, 0))
    for p in (QPointF(40, 0), QPointF(40, 30)):
        pl.append_point(p)
    pl._closed = True
    pl._rebuild_path()
    rect = RectangleItem(QPointF(0, 0), QPointF(50, 20))
    rect.set_angle(30.0)
    # Moved after rotation about an explicit pivot (pivot travels with it).
    rect_moved = RectangleItem(QPointF(0, 0), QPointF(50, 20))
    rect_moved.set_angle(-40.0, QPointF(5, 5))
    rect_moved.translate(12.0, -7.0)
    circ_moved = CircleItem(QPointF(5, 5), 20)
    circ_moved.translate(-9.0, 14.0)
    return [LineItem(QPointF(0, 0), QPointF(30, 40)), pl, rect,
            CircleItem(QPointF(5, 5), 20), ArcItem(QPointF(0, 0), 25, 30, 120),
            RegularPolygonItem.from_dict({"type": "polygon", "center": [0, 0],
                                          "radius_mm": 20, "sides": 6,
                                          "rotation": 10}),
            EllipseItem(QPointF(3, 4), 30, 12, 25.0),
            SplineItem([QPointF(0, 0), QPointF(10, 20), QPointF(30, -5), QPointF(50, 10)]),
            rect_moved, circ_moved,
            ArcItem(QPointF(2, -3), 18, 300, -150),      # CW input, crosses 0°
            SplineItem([QPointF(0, 0), QPointF(20, 25), QPointF(45, 0),
                        QPointF(20, -15)], closed=True)]


@pytest.mark.parametrize("idx", range(12))
def test_pieces_lie_on_drawn_geometry(qapp, idx):
    item = _items()[idx]
    from firepro3d.halo import _halo_trace_path_local
    base = _halo_trace_path_local(item)
    stroker = QPainterPathStroker()
    stroker.setWidth(0.2)                     # ±0.1 mm band around the drawn path
    band = stroker.createStroke(base)
    pieces = item.stroke_pieces()
    assert pieces
    for p in pieces:
        L = pw.length(p)
        for k in range(21):
            q = pw.point_at(p, L * k / 20)
            assert band.contains(q), (type(item).__name__, p, q)
    # Coverage: piece length ≈ drawn length.
    assert pw.total_length(pieces) == pytest.approx(base.length(), rel=2e-3)
