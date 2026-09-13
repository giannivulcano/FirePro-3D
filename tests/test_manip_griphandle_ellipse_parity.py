"""Posted-event grip drag of a real EllipseItem == legacy apply_grip outcome;
one undo per gesture; Esc restores; snap parity (grid fallback).

U3 migration of EllipseItem onto manip_handles(). Mirrors the CircleItem shape
(an ellipse is a generalized circle): centre (0) round move grip; the 4 axis
endpoints (major rx = 1,2; minor ry = 3,4) are square sizing grips. Zero special
drag semantics (the legacy grip path only Ctrl-constrains Wall/Gridline/Line);
apply_grip carries the edit math (centre = translate; major = rx + rotation;
minor = ry)."""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.construction_geometry import EllipseItem
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _make_ellipse():
    # centre (0,0), rx 60, ry 40, rotation 0 (Y-up CCW+):
    #   grip 0 = centre      (0, 0)
    #   grip 1 = major +x    (60, 0)
    #   grip 2 = major -x    (-60, 0)
    #   grip 3 = minor (90)  (0, -40)
    #   grip 4 = minor (270) (0, 40)
    return EllipseItem(QPointF(0, 0), 60.0, 40.0, 0.0)


def test_ellipse_manip_handles_shape():
    e = _make_ellipse()
    hs = e.manip_handles()
    assert len(hs) == 5                               # centre + 4 axis endpoints
    assert all(isinstance(h, GripHandle) for h in hs)
    assert [h.index for h in hs] == [0, 1, 2, 3, 4]
    assert all(h.role is HandleRole.GRIP for h in hs)
    # house rule (mirror CircleItem): centre round; axis sizing grips square
    assert hs[0].circular is True
    assert all(h.circular is False for h in hs[1:])
    # each rides its grip point
    for i, h in enumerate(hs):
        assert h.scene_position(None) == e.grip_points()[i]


def _drive_handle(item, index, drag_to, mods=Qt.KeyboardModifier.NoModifier):
    """Run a handle's live-apply drag lifecycle against a headless fake scene."""
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


def test_major_grip_apply_matches_legacy():
    """Grip 1 (major +x) exercises the rx + rotation branch of apply_grip."""
    legacy = _make_ellipse()
    legacy.apply_grip(1, QPointF(80, 30))

    migrated = _make_ellipse()
    _drive_handle(migrated, 1, QPointF(80, 30))
    assert migrated.to_dict() == legacy.to_dict()


def test_minor_grip_apply_matches_legacy():
    """Grip 3 (minor) exercises the ry branch of apply_grip."""
    legacy = _make_ellipse()
    legacy.apply_grip(3, QPointF(0, -55))

    migrated = _make_ellipse()
    _drive_handle(migrated, 3, QPointF(0, -55))
    assert migrated.to_dict() == legacy.to_dict()


def test_centre_grip_apply_matches_legacy():
    """Grip 0 exercises the translate branch of apply_grip."""
    legacy = _make_ellipse()
    legacy.apply_grip(0, QPointF(15, -25))

    migrated = _make_ellipse()
    _drive_handle(migrated, 0, QPointF(15, -25))
    assert migrated.to_dict() == legacy.to_dict()


def _post_drag(view, scene, path):
    """Post press->moves->release through the viewport (real event dispatch)."""
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


def test_posted_drag_moves_major_grip(qapp):
    """End-to-end: a posted drag on the major-axis grip (index 1) moves it,
    routed through the manipulator (no legacy path). apply_grip stores rx +
    rotation and reprojects, so the grip lands exactly at the drop point."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    e = _make_ellipse()
    scene.addItem(e)
    SelectionManipulator(scene)
    e.setSelected(True)
    qapp.processEvents()
    # major grip at (60, 0) -> drag to (80, 20)
    _post_drag(view, scene, [QPointF(60, 0), QPointF(70, 10), QPointF(80, 20)])
    qapp.processEvents()
    moved = e.grip_points()[1]
    assert abs(moved.x() - 80) < 1e-6
    assert abs(moved.y() - 20) < 1e-6
    # the centre is untouched by an axis-grip drag
    assert e.grip_points()[0] == QPointF(0, 0)


def test_posted_drag_moves_centre_grip(qapp):
    """A posted drag on the centre grip (index 0) translates the ellipse."""
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    e = _make_ellipse()
    scene.addItem(e)
    SelectionManipulator(scene)
    e.setSelected(True)
    qapp.processEvents()
    _post_drag(view, scene, [QPointF(0, 0), QPointF(10, -10), QPointF(20, -20)])
    qapp.processEvents()
    centre = e.grip_points()[0]
    assert abs(centre.x() - 20) < 1e-6
    assert abs(centre.y() - (-20)) < 1e-6


def test_one_commit_per_gesture(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    e = _make_ellipse(); scene.addItem(e)
    SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    e.setSelected(True); qapp.processEvents()
    _post_drag(view, scene, [QPointF(60, 0), QPointF(70, 10), QPointF(80, 20)])
    qapp.processEvents()
    assert calls == ["grip"]                          # exactly one commit


def test_esc_restores_and_no_commit(qapp):
    from firepro3d.selection_manipulator import SelectionManipulator
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    calls = []
    e = _make_ellipse(); scene.addItem(e)
    before = e.to_dict()
    m = SelectionManipulator(scene, commit_hook=lambda mode: calls.append(mode))
    e.setSelected(True); qapp.processEvents()
    # press + move (mutates rx via the major grip), then cancel (Esc)
    h = e.manip_handles()[1]
    m._begin_handle(h, QPointF(60, 0), QPointF(60, 0))
    m._update(QPointF(80, 20), Qt.KeyboardModifier.NoModifier, QPointF(80, 20))
    assert e._rx != 60.0                               # mutated live
    m.cancel_drag()
    assert e.to_dict() == before                        # restored exactly
    assert calls == []                                  # no undo entry on cancel


def test_provides_manip_handles():
    """The ellipse provides its own manipulator handles (migrated)."""
    assert _make_ellipse().manip_handles()


def test_grip_render_angle_tracks_rotation():
    """The square axis grips report the ellipse's orientation as their render
    angle, and it stays in sync after a rotate (manip_rotate)."""
    e = EllipseItem(QPointF(0, 0), 60.0, 40.0, 30.0)
    assert e.grip_render_angle(1) == 30.0
    assert e.grip_render_angle(3) == 30.0
    e.manip_rotate(20.0, QPointF(0, 0))               # rotate after the fact
    assert e.grip_render_angle(1) == 50.0             # grips stay aligned


def test_square_grip_shape_rotates_with_ellipse():
    """A square axis grip's hit-shape rotates with the ellipse: at 45deg the
    rotated square's bounding box is ~sqrt(2)x wider than the axis-aligned one.
    The round centre grip is rotation-invariant (unchanged)."""
    from firepro3d.manip_handle import GripHandle
    flat = EllipseItem(QPointF(0, 0), 60.0, 40.0, 0.0)
    tilt = EllipseItem(QPointF(0, 0), 60.0, 40.0, 45.0)
    h_flat = GripHandle(flat, 1, circular=False)
    h_tilt = GripHandle(tilt, 1, circular=False)
    w_flat = h_flat.shape(size=10.0, grab_pad=0.0).boundingRect().width()
    w_tilt = h_tilt.shape(size=10.0, grab_pad=0.0).boundingRect().width()
    assert w_tilt > w_flat * 1.3                       # ~sqrt(2) = 1.414
    # the round centre grip (circular) ignores the render angle entirely
    c_flat = GripHandle(flat, 0, circular=True)
    c_tilt = GripHandle(tilt, 0, circular=True)
    assert (c_flat.shape(size=10.0, grab_pad=0.0).boundingRect()
            == c_tilt.shape(size=10.0, grab_pad=0.0).boundingRect())


def test_grip_orientation_tracks_live_rotate(qapp):
    """While the rotate knob is dragged (held-preview, before the release bake),
    the square grips pick up the manipulator's LIVE preview rotation so they turn
    with the ellipse; the round centre grip stays invariant."""
    import pytest
    from firepro3d.selection_manipulator import SelectionManipulator
    from firepro3d.manip_math import HandleRole
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400); view.show()
    qapp.processEvents()
    e = _make_ellipse()                                # rotation 0 at rest
    scene.addItem(e)
    m = SelectionManipulator(scene)
    e.setSelected(True); qapp.processEvents()
    assert m._preview_rotation_deg() == 0.0            # not rotating yet

    # begin a rotate on the knob and drag to induce a live preview rotation
    rot_host = m._handles[HandleRole.ROTATE]
    start = rot_host.handle.scene_position(m._rect)    # top-edge midpoint
    m._begin_handle(rot_host.handle, start, start)
    m._update(QPointF(-40, 0), Qt.KeyboardModifier.NoModifier, QPointF(-40, 0))

    preview = m._preview_rotation_deg()
    assert abs(preview) > 1.0                          # a real rotation is live
    square = next(h.handle for h in m._host_pool
                  if h.isVisible() and not h.handle.circular)
    centre = next(h.handle for h in m._host_pool
                  if h.isVisible() and h.handle.circular)
    # base (item angle) is 0, so the square grip's render angle == the live preview
    assert square._render_angle() == pytest.approx(preview)
    assert centre._render_angle() == 0.0              # round grip: invariant

    # the rotate knob swings with the frame too (was: stayed vertical live).
    rot_handle = rot_host.handle
    assert rot_handle._live_preview_rotation() == pytest.approx(preview)
    # at rest the knob sits straight above the anchor (bounding centre on the
    # vertical axis, x≈0); a ~90° live preview swings it off-axis.
    knob_cx = rot_handle.shape(size=10.0, grab_pad=0.0).boundingRect().center().x()
    assert abs(knob_cx) > 5.0
    m.cancel_drag()
    # after cancel the preview is gone → knob back on the vertical axis
    assert rot_handle._live_preview_rotation() == 0.0
    knob_cx0 = rot_handle.shape(size=10.0, grab_pad=0.0).boundingRect().center().x()
    assert abs(knob_cx0) < 1e-6
