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


def test_rotated_rect_drops_scale_capability(qapp):
    """A rotated rect exposes move+rotate only (resize is unsafe while rotated)."""
    from firepro3d.selection_manipulator import item_capabilities
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    assert "scale" in item_capabilities(r)          # axis-aligned: resizable
    r.set_angle(30.0)
    caps = item_capabilities(r)
    assert caps == {"translate", "rotate"}          # rotated: no scale
    r.set_angle(0.0)
    assert "scale" in item_capabilities(r)          # back to resizable


def test_manip_scale_holds_anchor_no_translate(qapp):
    """Regression (live smoke 2026-08-30): resizing a rect via the TOP-RIGHT
    handle held the wrong corner fixed, so the rect jumped (translated) on
    commit. manip_scale must hold the given anchor fixed for ANY corner/edge."""
    # top-right drag → anchor = bottom-left (0,50); scale 2x about it
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r.manip_scale(2.0, 2.0, QPointF(0, 50))
    rect = r.rect().normalized()
    assert abs(rect.left() - 0.0) < 1e-6 and abs(rect.bottom() - 50.0) < 1e-6   # BL fixed
    assert abs(rect.width() - 200.0) < 1e-6 and abs(rect.height() - 100.0) < 1e-6

    # bottom-right drag → anchor = top-left; the previously-working diagonal
    r2 = RectangleItem(QPointF(10, 10), QPointF(110, 60))
    r2.manip_scale(1.5, 1.5, QPointF(10, 10))
    rr = r2.rect().normalized()
    assert abs(rr.left() - 10.0) < 1e-6 and abs(rr.top() - 10.0) < 1e-6         # TL fixed
    assert abs(rr.width() - 150.0) < 1e-6 and abs(rr.height() - 75.0) < 1e-6

    # right-edge drag → anchor = left-mid (0,25), single axis (fy == 1)
    r3 = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    r3.manip_scale(2.0, 1.0, QPointF(0, 25))
    r3r = r3.rect().normalized()
    assert abs(r3r.left() - 0.0) < 1e-6                                         # left fixed
    assert abs(r3r.width() - 200.0) < 1e-6 and abs(r3r.height() - 50.0) < 1e-6  # height unchanged
