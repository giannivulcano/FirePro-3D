# tests/test_polyline_closed.py
from PyQt6.QtCore import QPointF
from firepro3d.construction_geometry import PolylineItem

def _tri(closed=False):
    pl = PolylineItem(QPointF(0, 0))
    pl.append_point(QPointF(100, 0))
    pl.append_point(QPointF(0, 100))
    if closed:
        pl.close()
    return pl

def test_open_polyline_not_closed(qapp):
    pl = _tri(closed=False)
    assert pl.is_closed() is False
    assert pl.get_closed_path() is None

def test_close_sets_flag_no_duplicate_vertex(qapp):
    pl = _tri(closed=True)
    assert pl.is_closed() is True
    assert len(pl._points) == 3
    assert len(pl.grip_points()) == 3
    assert pl.get_closed_path() is not None

def test_closed_path_is_polygon(qapp):
    pl = _tri(closed=True)
    cp = pl.get_closed_path()
    assert cp.elementCount() >= 3

def test_serialization_round_trip_closed(qapp):
    pl = _tri(closed=True)
    d = pl.to_dict()
    assert d["closed"] is True
    pl2 = PolylineItem.from_dict(d)
    assert pl2.is_closed() is True
    assert len(pl2._points) == 3

def test_legacy_coincident_vertex_migrates_to_closed(qapp):
    legacy = {"type": "polyline", "color": "#ffffff", "lineweight": 1.0,
              "points": [[0, 0], [100, 0], [0, 100], [0, 0]]}
    pl = PolylineItem.from_dict(legacy)
    assert pl.is_closed() is True
    assert len(pl._points) == 3
    assert pl.get_closed_path() is not None

def test_legacy_open_stays_open(qapp):
    legacy = {"type": "polyline", "color": "#ffffff", "lineweight": 1.0,
              "points": [[0, 0], [100, 0], [0, 100]]}
    pl = PolylineItem.from_dict(legacy)
    assert pl.is_closed() is False
