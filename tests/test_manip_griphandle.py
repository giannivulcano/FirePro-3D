"""U3 GripHandle contract + manipulator-fix unit tests."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QCursor

from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


class _FakeItem:
    """Minimal item exposing the grip protocol for contract tests."""
    def __init__(self, pts, hittable=None):
        self._pts = list(pts)
        self._hittable = hittable  # None => all hittable
        self.applied = []          # (index, QPointF) log

    def grip_points(self):
        return list(self._pts)

    def grip_hittable(self, idx):
        return True if self._hittable is None else self._hittable[idx]

    def apply_grip(self, index, pos):
        self.applied.append((index, pos))
        self._pts[index] = pos


def _resize_roles():
    from firepro3d.manip_math import _RESIZE_ROLES
    return _RESIZE_ROLES


def test_grip_role_is_non_rigid():
    assert hasattr(HandleRole, "GRIP")
    assert HandleRole.GRIP not in _resize_roles()


def test_scene_position_tracks_grip_points():
    item = _FakeItem([QPointF(10, 20), QPointF(40, 20)])
    h = GripHandle(item, 1)
    # frame_rect is ignored; the handle rides the actual grip point
    assert h.scene_position(QRectF(0, 0, 999, 999)) == QPointF(40, 20)


def test_gesture_mode_opens_no_hud():
    item = _FakeItem([QPointF(0, 0)])
    h = GripHandle(item, 0)
    assert h.gesture_mode == "grip"
    assert h.hud_schema is None
    from firepro3d.selection_manipulator import _SCHEMA_FOR_MODE
    assert "grip" not in _SCHEMA_FOR_MODE  # => _open_hud early-returns


def test_visible_mirrors_grip_hittable():
    item = _FakeItem([QPointF(0, 0), QPointF(1, 1)], hittable=[True, False])
    assert GripHandle(item, 0).visible(None) is True
    assert GripHandle(item, 1).visible(None) is False


def test_role_is_grip_for_zvalue():
    item = _FakeItem([QPointF(0, 0)])
    assert GripHandle(item, 0).role is HandleRole.GRIP
