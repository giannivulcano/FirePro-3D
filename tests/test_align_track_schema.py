import math
from PyQt6.QtCore import QPointF
from firepro3d.dynamic_input import SCHEMAS, resolve_track


def test_track_schema_registered_as_placement():
    s = SCHEMAS["track"]
    assert s.returns_point is True            # a placement schema (resolves to a point)
    assert [f.name for f in s.fields] == ["Distance"]


def test_resolve_track_places_distance_along_injected_direction():
    # origin (2,3), unit dir +x, distance 5 → (7,3)
    values = {"Distance": 5.0, "__dir__": (1.0, 0.0)}
    pt = resolve_track(QPointF(2.0, 3.0), values)
    assert math.isclose(pt.x(), 7.0) and math.isclose(pt.y(), 3.0)


def test_resolve_track_signed_distance_reverses():
    values = {"Distance": -4.0, "__dir__": (0.0, 1.0)}
    pt = resolve_track(QPointF(0.0, 0.0), values)
    assert math.isclose(pt.x(), 0.0) and math.isclose(pt.y(), -4.0)
