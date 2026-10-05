"""LT3 H3-b -- stroke_pieces() traces exactly what each primitive draws."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPathStroker

from firepro3d import path_walk as pw
from firepro3d.geometry_2d import (ArcItem, CircleItem, EllipseItem, LineItem,
                                   PolylineItem, RectangleItem,
                                   RegularPolygonItem, SplineItem)


def _closed_polyline():
    pl = PolylineItem(QPointF(0, 0))
    for p in (QPointF(40, 0), QPointF(40, 30)):
        pl.append_point(p)
    pl._closed = True
    pl._rebuild_path()
    return pl


def _rotated_rect():
    rect = RectangleItem(QPointF(0, 0), QPointF(50, 20))
    rect.set_angle(30.0)
    return rect


def _rotated_moved_rect():
    # Moved after rotation about an explicit pivot (pivot travels with it).
    rect = RectangleItem(QPointF(0, 0), QPointF(50, 20))
    rect.set_angle(-40.0, QPointF(5, 5))
    rect.translate(12.0, -7.0)
    return rect


def _moved_circle():
    c = CircleItem(QPointF(5, 5), 20)
    c.translate(-9.0, 14.0)
    return c


# Factories (built inside the test, under the qapp fixture).
_FACTORIES = [
    lambda: LineItem(QPointF(0, 0), QPointF(30, 40)),
    _closed_polyline,
    _rotated_rect,
    lambda: CircleItem(QPointF(5, 5), 20),
    lambda: ArcItem(QPointF(0, 0), 25, 30, 120),
    lambda: RegularPolygonItem.from_dict({"type": "polygon", "center": [0, 0],
                                          "radius_mm": 20, "sides": 6,
                                          "rotation": 10}),
    lambda: EllipseItem(QPointF(3, 4), 30, 12, 25.0),
    lambda: SplineItem([QPointF(0, 0), QPointF(10, 20), QPointF(30, -5),
                        QPointF(50, 10)]),
    _rotated_moved_rect,
    _moved_circle,
    lambda: ArcItem(QPointF(2, -3), 18, 300, -150),      # CW input, crosses 0°
    lambda: SplineItem([QPointF(0, 0), QPointF(20, 25), QPointF(45, 0),
                        QPointF(20, -15)], closed=True),
]


def _assert_traces_drawn(item, pieces):
    """Every piece lies within ±0.1 mm of the drawn path, and covers it."""
    from firepro3d.halo import _halo_trace_path_local
    base = _halo_trace_path_local(item)
    stroker = QPainterPathStroker()
    stroker.setWidth(0.2)                     # ±0.1 mm band around the drawn path
    band = stroker.createStroke(base)
    assert pieces
    for p in pieces:
        L = pw.length(p)
        for k in range(21):
            q = pw.point_at(p, L * k / 20)
            assert band.contains(q), (type(item).__name__, p, q)
    # Coverage: piece length ≈ drawn length.
    assert pw.total_length(pieces) == pytest.approx(base.length(), rel=2e-3)


@pytest.mark.parametrize("idx", range(len(_FACTORIES)))
def test_pieces_lie_on_drawn_geometry(qapp, idx):
    item = _FACTORIES[idx]()
    _assert_traces_drawn(item, item.stroke_pieces())


def test_spline_pieces_cached_until_geometry_edit(qapp):
    s = SplineItem([QPointF(0, 0), QPointF(10, 20), QPointF(30, -5), QPointF(50, 10)])
    first = s.stroke_pieces()
    assert s.stroke_pieces() is first            # reused, not re-flattened
    s.translate(7.0, -3.0)
    moved = s.stroke_pieces()
    assert moved is not first and moved != first
    _assert_traces_drawn(s, moved)
    s.apply_grip(2, QPointF(35, 25))
    gripped = s.stroke_pieces()
    assert gripped != moved
    _assert_traces_drawn(s, gripped)
    assert s.stroke_pieces() is gripped


@pytest.mark.parametrize("cps", [[], [QPointF(4, 4)]])
def test_degenerate_spline_has_no_pieces(qapp, cps):
    assert SplineItem(cps).stroke_pieces() == ()
