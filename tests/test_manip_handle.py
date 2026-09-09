"""Handle-level units for U2 (manip_handle.py). Pure-ish: no live gesture."""
import math
import pytest
from PyQt6.QtCore import QPointF, QRectF
from firepro3d.manip_math import HandleRole, _ROLE_GEOM, _rect_point, _RESIZE_ROLES
from firepro3d.manip_handle import Handle, ResizeHandle, RotateHandle


RECT = QRectF(100.0, 200.0, 300.0, 160.0)  # arbitrary frame rect


@pytest.mark.parametrize("role", list(_RESIZE_ROLES))
def test_resize_handle_scene_position_mirrors_role_geom(role):
    u, v, _, _ = _ROLE_GEOM[role]
    h = ResizeHandle(role)
    assert h.scene_position(RECT) == _rect_point(RECT, u, v)


def test_rotate_handle_scene_position_is_top_mid():
    h = RotateHandle()
    assert h.scene_position(RECT) == _rect_point(RECT, 0.5, 0.0)


def test_resize_handle_gesture_mode_and_role():
    h = ResizeHandle(HandleRole.BOTTOM_RIGHT)
    assert h.gesture_mode == "resize"
    assert h.role is HandleRole.BOTTOM_RIGHT
    assert h.hud_schema == "manip_resize"


def test_rotate_handle_gesture_mode():
    h = RotateHandle()
    assert h.gesture_mode == "rotate"
    assert h.role is HandleRole.ROTATE
    assert h.hud_schema == "manip_rotate"


def test_handle_is_abstract_lifecycle():
    with pytest.raises(NotImplementedError):
        Handle().scene_position(RECT)


def test_rotate_handle_knob_outline_uses_border_width(qapp):
    """The rotate knob outline must draw at the passed border_width (0.3),
    not the stem pen's width (1.0). Guards the FIX-1 paint regression."""
    from PyQt6.QtGui import QColor, QPainter, QPixmap

    pm = QPixmap(64, 64)
    real = QPainter(pm)

    class _Proxy:
        def __init__(self, p):
            self._p = p
            self.log = []

        def __getattr__(self, n):
            return getattr(self._p, n)

        def setPen(self, pen):
            self.log.append(("pen", pen.widthF()))
            self._p.setPen(pen)

        def drawEllipse(self, *a):
            self.log.append(("ellipse", self._p.pen().widthF()))
            self._p.drawEllipse(*a)

        def drawLine(self, *a):
            self.log.append(("line", self._p.pen().widthF()))
            self._p.drawLine(*a)

    proxy = _Proxy(real)
    RotateHandle().paint(proxy, size=8.0, border=QColor("#63BE8B"),
                         fill=QColor("#222"), hover=False, border_width=0.3)
    real.end()
    ellipses = [w for (k, w) in proxy.log if k == "ellipse"]
    assert ellipses, "knob ellipse was not drawn"
    assert abs(ellipses[-1] - 0.3) < 1e-6, \
        f"knob outline width {ellipses[-1]} != border_width 0.3"
