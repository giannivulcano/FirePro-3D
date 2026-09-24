"""RectangleItem bake-at-rest: no Qt transform at rest; angle is data."""
from PyQt6.QtCore import QPointF
from firepro3d.geometry_2d import RectangleItem


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


def test_rect_never_exposes_scale_capability(qapp):
    """Task 9: a rect resizes via its own local-frame grips at EVERY angle, so it
    never exposes the manipulator's rigid ``scale`` path (move + rotate only)."""
    from firepro3d.selection_manipulator import item_capabilities
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    assert item_capabilities(r) == {"translate", "rotate"}
    r.set_angle(30.0)
    assert item_capabilities(r) == {"translate", "rotate"}
    assert not hasattr(r, "manip_scale")
    assert not hasattr(r, "manip_box_extra_handles")


def _drag(r, index, to):
    """Drive grip *index* through its real RectGripHandle lifecycle."""
    from PyQt6.QtCore import Qt

    class _Scene:
        _tools = None; _grip_item = None; _grip_dragging = False
        def get_effective_position(self, p): return QPointF(p)

    class _M:
        _commit_hook = None; _moved = True
        def __init__(self): self.sc = _Scene()
        def scene(self): return self.sc
        def _reflow_live(self): pass
        def _end_drag(self): pass

    h = r.manip_handles()[index]
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(to), Qt.KeyboardModifier.NoModifier)
    h.on_release(m, QPointF(to), Qt.KeyboardModifier.NoModifier)


def test_grip_resize_holds_opposite_no_translate(qapp):
    """Regression (live smoke 2026-08-30, migrated from the retired
    ``manip_scale`` bake): a TOP-RIGHT resize held the wrong corner fixed so the
    rect jumped on commit. The grip resize must hold the opposite corner/edge
    fixed for ANY corner/edge (same numbers as the old manip_scale test)."""
    # top-right drag → bottom-left (0,50) fixed; 2x
    r = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    _drag(r, 2, QPointF(200, -50))
    rect = r.rect().normalized()
    assert abs(rect.left() - 0.0) < 1e-6 and abs(rect.bottom() - 50.0) < 1e-6   # BL fixed
    assert abs(rect.width() - 200.0) < 1e-6 and abs(rect.height() - 100.0) < 1e-6

    # bottom-right drag → top-left fixed; 1.5x
    r2 = RectangleItem(QPointF(10, 10), QPointF(110, 60))
    _drag(r2, 4, QPointF(160, 85))
    rr = r2.rect().normalized()
    assert abs(rr.left() - 10.0) < 1e-6 and abs(rr.top() - 10.0) < 1e-6         # TL fixed
    assert abs(rr.width() - 150.0) < 1e-6 and abs(rr.height() - 75.0) < 1e-6

    # right-edge drag → left edge fixed, single axis
    r3 = RectangleItem(QPointF(0, 0), QPointF(100, 50))
    _drag(r3, 3, QPointF(200, 999))
    r3r = r3.rect().normalized()
    assert abs(r3r.left() - 0.0) < 1e-6                                         # left fixed
    assert abs(r3r.width() - 200.0) < 1e-6 and abs(r3r.height() - 50.0) < 1e-6  # height unchanged
