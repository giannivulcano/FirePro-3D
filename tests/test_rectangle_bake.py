"""RectangleItem bake-at-rest: no Qt transform at rest; angle is data."""
from PyQt6.QtCore import QPointF
from firepro3d.construction_geometry import RectangleItem


def test_set_angle_holds_no_qt_transform(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.set_angle(30.0)
    assert r.rotation() == 0.0
    assert r._angle == 30.0


def test_round_trip_serialization_unchanged(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.set_angle(30.0, QPointF(10, 10))
    d = r.to_dict()
    r2 = RectangleItem.from_dict(d)
    assert r2._angle == 30.0
    assert r2.to_dict() == d


def test_shape_covers_rotated_footprint(qapp):
    # shape() must return the rotated footprint in the item's (identity-pos)
    # local frame so Qt's scene hit-test (items(pos)/sceneTransform) tracks the
    # rotated rect — the held Qt transform used to do this for free.  A 100x10
    # rect turned 90° is now taller than wide.
    r = RectangleItem(QPointF(0, 0), QPointF(100, 10))
    r.set_angle(90.0)
    br = r.shape().boundingRect()
    assert br.height() > br.width()
