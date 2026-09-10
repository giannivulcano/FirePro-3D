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
