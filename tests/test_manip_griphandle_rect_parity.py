"""RectangleItem U3 box-native migration.

Rect provides manip_handles() (9 grips). For an UNROTATED rect the manipulator
shows its rigid
RESIZE handles (_is_box_native_single → _active_handles returns the rigid set),
NOT the parametric grips — no double-up. A ROTATED rect drops the scale cap, so
its parametric grips surface (live-apply; apply_grip resizes in the rect's own
local frame), replacing the legacy green grips.
"""
import pytest
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import RectangleItem
from firepro3d.manip_handle import GripHandle, ResizeHandle, RotateHandle
from firepro3d.manip_math import HandleRole

_ROUND = {0, 2, 4, 6, 8}          # corners + centre round; edge midpoints square


def _make_rect():
    return RectangleItem(QPointF(0, 0), QPointF(100, 60))


def test_rect_manip_handles_shape():
    r = _make_rect()
    hs = r.manip_handles()
    assert len(hs) == 9
    assert all(isinstance(h, GripHandle) for h in hs)
    assert [h.index for h in hs] == list(range(9))
    assert all(h.role is HandleRole.GRIP for h in hs)
    # corners (0,2,4,6) + centre (8) round; edge midpoints (1,3,5,7) square
    for i, h in enumerate(hs):
        assert h.circular is (i in _ROUND), f"grip {i} circular={h.circular}"


def test_provides_manip_handles_both_states():
    """A rect provides its own manip handles whether rotated or not."""
    r = _make_rect()
    assert r.manip_handles()                               # unrotated
    r.set_angle(30.0, QPointF(50, 30))
    assert r.manip_handles()                               # rotated


def test_grip_render_angle_is_rect_angle():
    r = _make_rect()
    assert r.grip_render_angle(1) == 0.0
    r.set_angle(30.0, QPointF(50, 30))
    assert r.grip_render_angle(1) == pytest.approx(30.0)


def test_unrotated_rect_shows_resize_handles_plus_centre_move(qapp):
    """Box-native single rect: the active handles are the rigid RESIZE/ROTATE set
    PLUS the centre MOVE grip — the 8 edge/corner parametric grips do NOT show
    (they'd double up with the resize handles), but the centre handle is present
    for the unrotated rect too (consistency with the rotated parametric path)."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    r = _make_rect(); scene.addItem(r)
    m = SelectionManipulator(scene)
    r.setSelected(True); qapp.processEvents()
    assert m._is_box_native_single(r) is True
    active = m._active_handles()
    rigid = [h for h in active if isinstance(h, (ResizeHandle, RotateHandle))]
    grips = [h for h in active if isinstance(h, GripHandle)]
    assert len(rigid) == 9                       # 8 resize + rotate knob
    assert [h.index for h in grips] == [8]       # only the centre MOVE grip
    assert grips[0].circular is True             # round


def test_unrotated_rect_centre_grip_moves(qapp):
    """The centre grip on an unrotated (box-native) rect translates it."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(600, 600); view.show()
    qapp.processEvents()
    r = _make_rect(); scene.addItem(r)
    m = SelectionManipulator(scene)
    r.setSelected(True); qapp.processEvents()
    centre = next(h for h in m._active_handles()
                  if isinstance(h, GripHandle) and h.index == 8)
    c0 = r.grip_points()[8]
    _drive_handle(r, 8, QPointF(c0.x() + 30, c0.y() - 20))
    c1 = r.grip_points()[8]
    assert abs(c1.x() - (c0.x() + 30)) < 1e-6
    assert abs(c1.y() - (c0.y() - 20)) < 1e-6


def test_rotated_rect_shows_parametric_grips(qapp):
    """A rotated rect drops scale → not box-native → its live-apply parametric
    grips surface via the manipulator (replacing the legacy green grips)."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    r = _make_rect(); r.set_angle(30.0, QPointF(50, 30)); scene.addItem(r)
    m = SelectionManipulator(scene)
    r.setSelected(True); qapp.processEvents()
    assert m._is_box_native_single(r) is False
    active = m._active_handles()
    grips = [h for h in active if isinstance(h, GripHandle)]
    assert len(grips) == 9
    assert [h.index for h in grips] == list(range(9))


def _drive_handle(item, index, drag_to, mods=Qt.KeyboardModifier.NoModifier):
    h = item.manip_handles()[index]

    class _Scene:
        _tools = None
        _grip_item = None
        _grip_dragging = False
        def get_effective_position(self, pt): return QPointF(pt)
    class _M:
        _commit_hook = None
        def scene(self_m): return sc
        def _reflow_live(self_m): pass
    sc = _Scene()
    m = _M()
    h.on_press(m)
    h.on_drag(m, QPointF(drag_to), mods)
    return h, m


def test_rotated_corner_grip_apply_matches_legacy():
    """Driving corner grip 0 through the live-apply lifecycle == calling
    apply_grip directly — the rotated-rect resize runs in the local frame."""
    legacy = _make_rect(); legacy.set_angle(30.0, QPointF(50, 30))
    legacy.apply_grip(0, QPointF(-10, -5))

    migrated = _make_rect(); migrated.set_angle(30.0, QPointF(50, 30))
    _drive_handle(migrated, 0, QPointF(-10, -5))
    assert migrated.rect() == legacy.rect()
    assert migrated._angle == legacy._angle


def _post_drag(view, scene, path):
    from PyQt6.QtWidgets import QApplication
    for i, pt in enumerate(path):
        vp = view.mapFromScene(pt)
        etype = (QEvent.Type.MouseButtonPress if i == 0
                 else QEvent.Type.MouseButtonRelease if i == len(path) - 1
                 else QEvent.Type.MouseMove)
        btn = Qt.MouseButton.LeftButton
        ev = QMouseEvent(etype, vp.toPointF(),
                         view.viewport().mapToGlobal(vp).toPointF(),
                         btn, btn if etype != QEvent.Type.MouseButtonRelease
                         else Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)


def test_posted_drag_centre_grip_moves_rotated_rect(qapp):
    """End-to-end: a posted drag on the centre grip (8) of a rotated rect,
    routed through the manipulator (no legacy path), translates the rect."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(600, 600); view.show()
    qapp.processEvents()
    r = _make_rect(); r.set_angle(30.0, QPointF(50, 30)); scene.addItem(r)
    m = SelectionManipulator(scene)
    r.setSelected(True); qapp.processEvents()
    c0 = r.grip_points()[8]
    target = QPointF(c0.x() + 40, c0.y() - 25)
    _post_drag(view, scene, [c0, QPointF(c0.x() + 20, c0.y() - 12), target])
    qapp.processEvents()
    c1 = r.grip_points()[8]
    assert abs(c1.x() - target.x()) < 1e-6
    assert abs(c1.y() - target.y()) < 1e-6


