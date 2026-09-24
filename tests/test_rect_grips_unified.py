"""Task 9 guard: a RectangleItem always shows its own 9 local-frame grips at
every angle (no box-native rigid resize path). Corner/edge grips resize from
the PRESS-time rect: Ctrl = symmetric about the centre, Shift (corners) = keep
aspect, Ctrl+Shift = both. The angle is always preserved; Esc restores."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt

from firepro3d.geometry_2d import RectangleItem, rect_grip_resize
from firepro3d.manip_handle import RectGripHandle
from firepro3d.selection_manipulator import item_capabilities

CTRL, SHIFT = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier
NONE = Qt.KeyboardModifier.NoModifier


class _Scene:
    _tools = None; _grip_item = None; _grip_dragging = False
    def get_effective_position(self, p): return QPointF(p)


class _M:
    _commit_hook = None; _moved = True
    def __init__(self): self.sc = _Scene()
    def scene(self): return self.sc
    def _reflow_live(self): pass
    def _end_drag(self): pass


def _close(a, b, tol=1e-6):
    return abs(a.x() - b.x()) < tol and abs(a.y() - b.y()) < tol


def test_pure_resize_modes():
    r0 = QRectF(0, 0, 40, 20)
    assert rect_grip_resize(r0, 4, QPointF(50, 30), False, False) == QRectF(0, 0, 50, 30)
    assert rect_grip_resize(r0, 4, QPointF(50, 30), True, False) == QRectF(-10, -10, 60, 40)
    assert rect_grip_resize(r0, 4, QPointF(80, 22), False, True) == QRectF(0, 0, 80, 40)
    assert rect_grip_resize(r0, 3, QPointF(60, 99), True, False) == QRectF(-20, 0, 80, 20)
    assert rect_grip_resize(r0, 3, QPointF(60, 99), False, True) == QRectF(0, 0, 60, 20)


def test_pure_ctrl_shift_both():
    r0 = QRectF(0, 0, 40, 20)          # centre (20, 10), aspect 2
    r = rect_grip_resize(r0, 4, QPointF(60, 12), True, True)
    assert r.center() == QPointF(20, 10)
    assert r.width() / r.height() == pytest.approx(2.0)
    assert r == QRectF(-20, -10, 80, 40)  # fx=2 dominates (fy=0.2)


def test_pure_centre_translates():
    r0 = QRectF(0, 0, 40, 20)
    assert rect_grip_resize(r0, 8, QPointF(25, 15), True, True) == QRectF(5, 5, 40, 20)


@pytest.mark.parametrize("angle", [0.0, 30.0])
def test_same_nine_grips_at_every_angle(angle):
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    it.set_angle(angle, QPointF(0, 0))
    hs = it.manip_handles()
    assert len(hs) == 9 and all(isinstance(h, RectGripHandle) for h in hs)
    assert [h.index for h in hs] == list(range(9))
    assert "scale" not in item_capabilities(it)


@pytest.mark.parametrize("angle,pivot", [(0.0, QPointF(0, 0)),
                                         (30.0, QPointF(0, 0)),
                                         (30.0, None)])
def test_ctrl_keeps_centre_angle_preserved(angle, pivot):
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    it.set_angle(angle, pivot)
    c0 = it.grip_points()[8]
    h = it.manip_handles()[4]                       # BR corner
    m = _M()
    h.on_press(m)
    target = it.mapToScene(QPointF(50, 30))
    h.on_drag(m, target, CTRL)
    c1 = it.grip_points()[8]
    assert _close(c1, c0)
    assert it._angle == pytest.approx(angle)
    # Dragged corner lands on the cursor (local frame, not axis-aligned scene).
    assert _close(it.grip_points()[4], target)


def test_plain_corner_holds_opposite_corner_rotated():
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    it.set_angle(30.0, QPointF(0, 0))
    tl0 = it.grip_points()[0]
    h = it.manip_handles()[4]
    m = _M()
    h.on_press(m)
    target = it.mapToScene(QPointF(60, 35))
    h.on_drag(m, target, NONE)
    h.on_drag(m, target, NONE)
    assert _close(it.grip_points()[0], tl0)
    assert _close(it.grip_points()[4], target)


def test_drag_runs_from_press_time_rect():
    """Repeated on_drag calls are absolute from r0 (no accumulation)."""
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    h = it.manip_handles()[4]
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(50, 30), CTRL)
    h.on_drag(m, QPointF(50, 30), CTRL)
    assert it.rect() == QRectF(-10, -10, 60, 40)


def test_shift_on_edge_has_no_effect():
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    h = it.manip_handles()[3]                       # RM edge
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(60, 99), SHIFT)
    assert it.rect() == QRectF(0, 0, 60, 20)


def test_shift_keeps_aspect_and_esc_restores():
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    h = it.manip_handles()[4]
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(80, 22), SHIFT)
    r = it.rect()
    assert r.width() / r.height() == pytest.approx(2.0)
    h.on_cancel(m)
    assert it.rect() == QRectF(0, 0, 40, 20)


def test_esc_restores_ctrl_resize_both_sides():
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    it.set_angle(30.0, QPointF(0, 0))
    h = it.manip_handles()[4]
    m = _M()
    h.on_press(m)
    h.on_drag(m, it.mapToScene(QPointF(50, 30)), CTRL)
    h.on_cancel(m)
    assert it.rect() == QRectF(0, 0, 40, 20)
    assert it._angle == pytest.approx(30.0)


def test_release_commits_once_with_final_point():
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    h = it.manip_handles()[4]
    m = _M()
    commits = []
    m._commit_hook = commits.append
    h.on_press(m)
    h.on_drag(m, QPointF(45, 25), CTRL)
    h.on_release(m, QPointF(50, 30), CTRL)
    assert it.rect() == QRectF(-10, -10, 60, 40)
    assert commits == ["grip"]


def test_centre_pivot_plain_drag_holds_opposite_corner_and_esc_exact():
    """Review follow-up: a rotated rect with a centre-following pivot
    (``_pivot is None``) must not drift — a plain BR drag holds TL in scene;
    Esc restores the rect AND ``_pivot is None``."""
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    it.set_angle(30.0)                                   # _pivot is None
    tl0 = it.grip_points()[0]
    h = it.manip_handles()[4]
    m = _M()
    h.on_press(m)
    br = it.grip_points()[4]
    target = QPointF(br.x() + 40, br.y() + 40)
    h.on_drag(m, target, NONE)
    h.on_drag(m, target, NONE)
    assert _close(it.grip_points()[0], tl0)
    assert _close(it.grip_points()[4], target)
    h.on_cancel(m)
    assert it._pivot is None
    assert it.rect() == QRectF(0, 0, 40, 20)


def test_centre_pivot_click_without_drag_leaves_pivot_none():
    it = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    it.set_angle(30.0)
    h = it.manip_handles()[4]
    m = _M()
    m._moved = False
    h.on_press(m)
    h.on_release(m, it.grip_points()[4], NONE)
    assert it._pivot is None


def test_frame_redundant_only_for_unrotated_rect(qapp):
    from PyQt6.QtWidgets import QGraphicsScene
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    r = RectangleItem(QPointF(0, 0), QPointF(40, 20))
    scene.addItem(r)
    m = SelectionManipulator(scene)
    r.setSelected(True); qapp.processEvents()
    assert m._items == [r]
    assert m._frame_is_redundant() is True               # outline == frame
    r.set_angle(30.0, QPointF(0, 0))
    assert m._frame_is_redundant() is False              # rotated: keep frame
