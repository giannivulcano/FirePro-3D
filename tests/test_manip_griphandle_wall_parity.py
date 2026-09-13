"""Posted-event / lifecycle grip drag of a real WallSegment == legacy apply_grip
outcome; endpoints Ctrl-constrain against the opposite endpoint and propagate to
joined walls; one undo per gesture; Esc atomically restores the dragged wall AND
every propagated sibling; width/mid grips never propagate.

U3 migration of WallSegment onto manip_handles(). Mirrors
test_manip_griphandle_line_parity.py, extended for wall propagation + sibling
snapshot/restore (WallEndpointGripHandle)."""
from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.wall import WallSegment
from firepro3d.manip_handle import GripHandle, WallEndpointGripHandle
from firepro3d.manip_math import HandleRole


def _make_wall():
    """Horizontal wall pt1=(0,0), pt2=(500,0), thickness 100mm."""
    return WallSegment(QPointF(0.0, 0.0), QPointF(500.0, 0.0), thickness_mm=100.0)


class _StubScene:
    """Plain-scene stand-in; records the duck-typed wall-graph calls the handle
    makes so the handle contract can be asserted in isolation."""
    _tools = None
    _grip_item = None
    _grip_dragging = False

    def __init__(self):
        self.prop_calls = []
        self.snap_calls = []
        self.restore_calls = []

    def get_effective_position(self, p):
        return QPointF(p)

    def _propagate_wall_endpoint(self, item, old, new):
        self.prop_calls.append((QPointF(old), QPointF(new)))

    def _snapshot_wall_endpoints(self, exclude):
        self.snap_calls.append(exclude)
        return [("SNAP", exclude)]

    def _restore_wall_endpoints(self, snapshot):
        self.restore_calls.append(snapshot)


class _StubM:
    _commit_hook = None

    def __init__(self, sc):
        self._sc = sc

    def scene(self):
        return self._sc

    def _reflow_live(self):
        pass


def test_wall_manip_handles_shape():
    w = _make_wall()
    hs = w.manip_handles()
    assert len(hs) == 4
    assert [h.index for h in hs] == [0, 1, 2, 3]
    assert all(h.role is HandleRole.GRIP for h in hs)
    # endpoints 0/1: wall endpoint handles, round, constrain against the opposite
    assert isinstance(hs[0], WallEndpointGripHandle) and hs[0].circular is True
    assert isinstance(hs[1], WallEndpointGripHandle) and hs[1].circular is True
    assert hs[0].opposite_index == 1 and hs[1].opposite_index == 0
    # mid (2) = round move grip; width (3) = square thickness grip; both plain
    assert type(hs[2]) is GripHandle and hs[2].circular is True
    assert type(hs[3]) is GripHandle and hs[3].circular is False
    for i, h in enumerate(hs):
        assert h.scene_position(None) == w.grip_points()[i]


def test_width_grip_render_angle_aligns_with_wall():
    """The square width grip (index 3) must rotate to the wall's centerline
    orientation so its edges align with the wall (like RectangleItem edge grips /
    EllipseItem axis grips). The round endpoint/centre grips ignore the hook."""
    import math
    # Diagonal wall so the alignment angle is unambiguously non-zero.
    w = WallSegment(QPointF(0.0, 0.0), QPointF(100.0, 100.0), thickness_mm=100.0)
    expected = -math.degrees(w.centerline_angle_rad())      # Y-up degrees
    assert w.grip_render_angle(3) == expected
    assert abs(expected) > 1.0                              # genuinely rotated
    hs = w.manip_handles()
    # The square width grip's rendered angle picks up grip_render_angle(3)...
    assert hs[3]._render_angle() == expected
    # ...while the round grips (endpoints/centre) are rotation-invariant -> 0.
    assert hs[0]._render_angle() == 0.0
    assert hs[2]._render_angle() == 0.0


def test_endpoint_drag_propagates_old_to_new():
    w = _make_wall()
    h = w.manip_handles()[1]                       # pt2 endpoint
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(500, 100), Qt.KeyboardModifier.NoModifier)
    # propagation fired old(pre-apply endpoint) -> new(applied endpoint)
    assert sc.prop_calls == [(QPointF(500, 0), QPointF(500, 100))]
    assert w.grip_points()[1] == QPointF(500, 100)


def test_ctrl_constrains_endpoint_against_opposite():
    calls = []

    class _CScene(_StubScene):
        def _constrain_angle(self, anchor, raw):
            calls.append(QPointF(anchor))
            return QPointF(42, 42)                 # sentinel

    w = _make_wall()                               # pt1=(0,0), pt2=(500,0)
    h0 = w.manip_handles()[0]                      # pt1, opposite=1 (pt2)
    sc = _CScene(); m = _StubM(sc)
    h0.on_press(m)
    h0.on_drag(m, QPointF(10, 90), Qt.KeyboardModifier.ControlModifier)
    assert calls == [QPointF(500, 0)]              # anchor = opposite endpoint
    assert w.grip_points()[0] == QPointF(42, 42)   # applied = constrain result


def test_no_ctrl_no_constrain():
    calls = []

    class _CScene(_StubScene):
        def _constrain_angle(self, anchor, raw):
            calls.append((anchor, raw))
            return QPointF(42, 42)

    w = _make_wall()
    h1 = w.manip_handles()[1]
    sc = _CScene(); m = _StubM(sc)
    h1.on_press(m)
    h1.on_drag(m, QPointF(300, 70), Qt.KeyboardModifier.NoModifier)
    assert calls == []                             # constrain NOT called
    assert w.grip_points()[1] == QPointF(300, 70)


# --------------------------------------------------------------------------
# Wall-controller snapshot/restore helpers (via the Model_Space bridges)
# --------------------------------------------------------------------------

def _add_wall(scene, p1, p2):
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=100.0)
    scene.addItem(w)
    scene._walls.append(w)
    return w


def test_snapshot_excludes_dragged_and_captures_all_other_endpoints(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_wall(scene, (-200, 0), (0, 0))
    b = _add_wall(scene, (0, 0), (0, 200))
    c = _add_wall(scene, (0, 0), (200, 100))

    snap = scene._snapshot_wall_endpoints(a)       # dragging a
    walls_in_snap = {rec[0] for rec in snap}
    assert walls_in_snap == {b, c}                 # a excluded
    # both endpoints of each other wall captured
    assert sorted(idx for _, idx, _ in snap) == [0, 0, 1, 1]


def test_restore_puts_endpoints_back(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_wall(scene, (-200, 0), (0, 0))
    b = _add_wall(scene, (0, 0), (0, 200))

    snap = scene._snapshot_wall_endpoints(a)
    b.apply_grip(0, QPointF(999, 999))             # move b away
    assert b.grip_points()[0] == QPointF(999, 999)

    scene._restore_wall_endpoints(snap)
    assert b.grip_points()[0] == QPointF(0, 0)     # restored


# --------------------------------------------------------------------------
# Coexistence gate + endpoint apply parity
# --------------------------------------------------------------------------

def test_wall_provides_manip_handles():
    assert _make_wall().manip_handles()


def test_endpoint_grip_apply_matches_legacy():
    legacy = _make_wall(); legacy.apply_grip(1, QPointF(480, 60))
    migrated = _make_wall()
    h = migrated.manip_handles()[1]
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(480, 60), Qt.KeyboardModifier.NoModifier)
    assert migrated.to_dict() == legacy.to_dict()


def test_width_grip_apply_matches_legacy_and_no_propagate():
    legacy = _make_wall(); legacy.apply_grip(3, QPointF(250, -120))
    migrated = _make_wall()
    h = migrated.manip_handles()[3]                # width grip (plain GripHandle)
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(250, -120), Qt.KeyboardModifier.NoModifier)
    assert migrated.to_dict() == legacy.to_dict()
    assert sc.prop_calls == []                     # width grip must NOT propagate
    assert sc.snap_calls == []                     # nor snapshot siblings


def test_mid_grip_translates_whole_wall_and_no_propagate():
    w = _make_wall()
    h = w.manip_handles()[2]                        # mid / move grip
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(250, 50), Qt.KeyboardModifier.NoModifier)  # mid -> (250,50)
    assert w.grip_points()[0] == QPointF(0, 50)     # whole wall translated +50 in y
    assert w.grip_points()[1] == QPointF(500, 50)
    assert sc.prop_calls == []


def test_press_snapshots_siblings_and_cancel_restores_them():
    w = _make_wall()
    h = w.manip_handles()[1]                        # endpoint
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    assert sc.snap_calls == [w]                     # snapshot excludes the dragged wall
    h.on_drag(m, QPointF(500, 60), Qt.KeyboardModifier.NoModifier)
    h.on_cancel(m)
    assert sc.restore_calls == [[("SNAP", w)]]      # siblings restored from snapshot
    assert w.grip_points()[1] == QPointF(500, 0)    # dragged endpoint restored


# --------------------------------------------------------------------------
# Integration — real Model_Space + its live manipulator (posted / driven)
# --------------------------------------------------------------------------
#
# NOTE: SelectionManipulator._finish has the real signature
# ``_finish(self, scene_pos, mods)`` (2 args, verified in
# firepro3d/selection_manipulator.py:1017) — NOT the 3-arg form the plan draft
# guessed. The driver + call sites below use the real 2-arg lifecycle; the
# manipulator is never bypassed.


def _pt(qp):
    return (qp.x(), qp.y())


def _drive_grip(scene, wall, index, start, path, mods=Qt.KeyboardModifier.NoModifier):
    """Select *wall*, install its handle *index* on the scene's live
    manipulator, and drive press -> moves through the manipulator (the same
    lifecycle the view posts). Returns the manipulator (so callers can finish
    or cancel). Does NOT release."""
    scene.set_mode("select")
    wall.setSelected(True)
    QApplication.processEvents()
    m = scene._live_manip()
    h = wall.manip_handles()[index]
    m._begin_handle(h, QPointF(*start), QPointF(*start))
    for pt in path:
        m._update(QPointF(*pt), mods, QPointF(*pt))
    return m


def test_endpoint_drag_moves_both_joined_walls(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_wall(scene, (-200, 0), (0, 0))        # grip 1 = shared (0,0)
    b = _add_wall(scene, (0, 0), (0, 200))         # grip 0 = shared (0,0)

    m = _drive_grip(scene, a, index=1, start=(0, 0), path=[(30, -20), (50, -50)])
    m._finish(QPointF(50, -50), Qt.KeyboardModifier.NoModifier)

    assert a.grip_points()[1] != QPointF(0, 0)     # dragged endpoint moved
    assert b.grip_points()[0] != QPointF(0, 0)     # coincident endpoint followed
    assert abs(a.grip_points()[1].x() - b.grip_points()[0].x()) < 1e-6
    assert abs(a.grip_points()[1].y() - b.grip_points()[0].y()) < 1e-6


def test_three_walls_at_vertex_all_follow(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_wall(scene, (-200, 0), (0, 0))
    b = _add_wall(scene, (0, 0), (0, 200))
    c = _add_wall(scene, (0, 0), (200, 100))

    m = _drive_grip(scene, a, index=1, start=(0, 0), path=[(-30, 80)])
    m._finish(QPointF(-30, 80), Qt.KeyboardModifier.NoModifier)

    for other in (b, c):
        assert abs(other.grip_points()[0].x() - a.grip_points()[1].x()) < 1e-6
        assert abs(other.grip_points()[0].y() - a.grip_points()[1].y()) < 1e-6


def test_isolated_wall_and_far_endpoint_untouched(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_wall(scene, (-200, 0), (0, 0))
    b = _add_wall(scene, (0, 0), (0, 200))
    iso = _add_wall(scene, (-300, -200), (-100, -200))
    b_far = QPointF(b.grip_points()[1])
    iso0, iso1 = QPointF(iso.grip_points()[0]), QPointF(iso.grip_points()[1])

    m = _drive_grip(scene, a, index=1, start=(0, 0), path=[(50, -50)])
    m._finish(QPointF(50, -50), Qt.KeyboardModifier.NoModifier)

    assert b.grip_points()[1] == b_far             # b's far end fixed
    assert iso.grip_points()[0] == iso0            # isolated wall untouched
    assert iso.grip_points()[1] == iso1


def test_width_grip_drag_does_not_propagate(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_wall(scene, (-200, 0), (0, 0))
    b = _add_wall(scene, (0, 0), (0, 200))
    b0 = QPointF(b.grip_points()[0])

    m = _drive_grip(scene, a, index=3, start=_pt(a.grip_points()[3]),
                    path=[(0, -250)])
    m._finish(QPointF(0, -250), Qt.KeyboardModifier.NoModifier)

    assert b.grip_points()[0] == b0                # width grip never propagates


def test_one_commit_per_gesture(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_wall(scene, (-200, 0), (0, 0))
    _add_wall(scene, (0, 0), (0, 200))
    calls = []
    scene._live_manip()._commit_hook = lambda mode: calls.append(mode)

    m = _drive_grip(scene, a, index=1, start=(0, 0), path=[(30, -20), (50, -50)])
    m._finish(QPointF(50, -50), Qt.KeyboardModifier.NoModifier)

    assert calls == ["grip"]


def test_esc_atomically_restores_dragged_and_siblings(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_wall(scene, (-200, 0), (0, 0))
    b = _add_wall(scene, (0, 0), (0, 200))
    c = _add_wall(scene, (0, 0), (200, 100))
    a_before = a.to_dict(); b_before = b.to_dict(); c_before = c.to_dict()
    calls = []
    scene._live_manip()._commit_hook = lambda mode: calls.append(mode)

    m = _drive_grip(scene, a, index=1, start=(0, 0), path=[(40, -40), (80, -80)])
    # mutated live (join dragged apart from origin)
    assert a.grip_points()[1] != QPointF(0, 0)
    assert b.grip_points()[0] != QPointF(0, 0)
    m.cancel_drag()

    assert a.to_dict() == a_before                 # dragged wall restored
    assert b.to_dict() == b_before                 # sibling restored
    assert c.to_dict() == c_before                 # sibling restored
    assert calls == []                             # no commit on cancel


def test_hosted_opening_rides_endpoint_drag(qapp, shown_model_view):
    """A door hosted on the wall follows when the wall endpoint is grip-dragged
    (parity: apply_grip -> _rebuild_path repositions openings, unchanged)."""
    from firepro3d.wall_opening import DoorOpening
    view, scene = shown_model_view
    a = _add_wall(scene, (0, 0), (1000, 0))
    door = DoorOpening(a, offset_along=500.0, width_mm=900.0)
    a.openings.append(door)
    scene.addItem(door)
    a._rebuild_path()
    door_y_before = door.scenePos().y()

    m = _drive_grip(scene, a, index=1, start=(1000, 0), path=[(1000, 300)])
    m._finish(QPointF(1000, 300), Qt.KeyboardModifier.NoModifier)

    # the wall now rises toward pt2; the hosted door must move off the old axis
    assert door.scenePos().y() != door_y_before
