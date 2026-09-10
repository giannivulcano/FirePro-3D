"""Posted-event / lifecycle grip drag of a real GridlineItem == legacy apply_grip
outcome; ALL grips carry multi-select parallel-delta; endpoints Ctrl-constrain
against the opposite endpoint; one undo per gesture; Esc atomically restores the
dragged gridline AND every parallel-delta sibling; the legacy _PullTabGrip visuals
are gone and _find_grip_hit skips the migrated item.

U3 migration of GridlineItem onto manip_handles(). Mirrors
test_manip_griphandle_wall_parity.py, adapted for parallel-delta (all grips) +
bubble-standoff grips."""
import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.gridline import GridlineItem


def _add_gl(scene, p1, p2, label="1"):
    gl = GridlineItem(QPointF(*p1), QPointF(*p2), label=label)
    scene.addItem(gl)
    scene._gridlines.append(gl)
    return gl


# --------------------------------------------------------------------------
# Scene methods: parallel-delta + snapshot/restore
# --------------------------------------------------------------------------

def test_propagate_applies_same_delta_to_other_selected_gridlines(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")      # vertical
    b = _add_gl(scene, (300, 0), (300, 5000), "2")  # vertical, parallel
    a.setSelected(True); b.setSelected(True)
    b0 = QPointF(b.grip_points()[1])
    scene._propagate_gridline_grip(a, 1, QPointF(0, 700))
    assert b.grip_points()[1] == QPointF(b0.x(), b0.y() + 700)


def test_propagate_skips_non_gridlines_and_locked_and_self(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")
    locked = _add_gl(scene, (300, 0), (300, 5000), "2")
    locked._locked = True
    a.setSelected(True); locked.setSelected(True)
    before = QPointF(locked.grip_points()[1])
    scene._propagate_gridline_grip(a, 1, QPointF(0, 700))
    assert locked.grip_points()[1] == before          # locked apply_grip no-ops


def test_snapshot_excludes_dragged_and_restore_puts_back(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")
    b = _add_gl(scene, (300, 0), (300, 5000), "2")
    a.setSelected(True); b.setSelected(True)
    snap = scene._snapshot_gridline_grips(a, 1)
    assert {rec[0] for rec in snap} == {b}             # a excluded
    b.apply_grip(1, QPointF(300, 9999))                # move b
    scene._restore_gridline_grips(snap)
    assert b.grip_points()[1] == QPointF(300, 5000)    # restored


# --------------------------------------------------------------------------
# GridlineGripHandle contract (in isolation, via a recording stub scene)
# --------------------------------------------------------------------------

from firepro3d.manip_handle import GridlineGripHandle, EndpointGripHandle  # noqa: E402
from firepro3d.manip_math import HandleRole  # noqa: E402


class _StubScene:
    """Records the duck-typed gridline scene calls so the handle contract can be
    asserted in isolation."""
    _tools = None
    _grip_item = None
    _grip_dragging = False

    def __init__(self):
        self.prop_calls = []
        self.snap_calls = []
        self.restore_calls = []

    def get_effective_position(self, p):
        return QPointF(p)

    def _propagate_gridline_grip(self, item, index, delta):
        self.prop_calls.append((index, QPointF(delta)))

    def _snapshot_gridline_grips(self, exclude, index):
        self.snap_calls.append((exclude, index))
        return [("SNAP", exclude, index)]

    def _restore_gridline_grips(self, snapshot):
        self.restore_calls.append(snapshot)


class _StubM:
    _commit_hook = None

    def __init__(self, sc):
        self._sc = sc

    def scene(self):
        return self._sc

    def _reflow_live(self):
        pass


def _make_gl():
    return GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")  # vertical


def test_gridline_handle_is_endpoint_subclass_with_right_opposites():
    gl = _make_gl()
    hs = gl.manip_handles()
    assert len(hs) == 4
    assert [h.index for h in hs] == [0, 1, 2, 3]
    assert all(h.role is HandleRole.GRIP for h in hs)
    assert all(isinstance(h, GridlineGripHandle) for h in hs)
    assert isinstance(hs[0], EndpointGripHandle)
    assert hs[0].opposite_index == 1 and hs[1].opposite_index == 0
    assert hs[2].opposite_index is None and hs[3].opposite_index is None
    # endpoints round; bubble-standoff grips square
    assert hs[0].circular is True and hs[1].circular is True
    assert hs[2].circular is False and hs[3].circular is False


def test_endpoint_apply_matches_legacy_and_propagates():
    legacy = _make_gl(); legacy.apply_grip(1, QPointF(40, 6200))
    migrated = _make_gl()
    h = migrated.manip_handles()[1]
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(40, 6200), Qt.KeyboardModifier.NoModifier)
    assert migrated.to_dict() == legacy.to_dict()
    # parallel-delta fired with (index, applied-old delta)
    assert sc.prop_calls[0][0] == 1
    assert sc.prop_calls[0][1] == QPointF(0, 1200)   # far went 5000 -> 6200 on-axis


def test_bubble_grip_apply_matches_legacy_and_propagates():
    legacy = _make_gl(); legacy.apply_grip(2, QPointF(40, -1500))
    migrated = _make_gl()
    h = migrated.manip_handles()[2]
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(40, -1500), Qt.KeyboardModifier.NoModifier)
    assert math.isclose(migrated.bubble1_offset(), legacy.bubble1_offset(), abs_tol=1e-6)
    assert sc.prop_calls[0][0] == 2                  # bubble grips propagate too


def test_ctrl_constrains_endpoint_against_opposite():
    calls = []

    class _CScene(_StubScene):
        def _constrain_angle(self, anchor, raw):
            calls.append(QPointF(anchor))
            return QPointF(0, 4000)                   # on-axis sentinel

    gl = _make_gl()                                   # origin (0,0), far (0,5000)
    h0 = gl.manip_handles()[0]                         # pt at index0, opposite=1
    sc = _CScene(); m = _StubM(sc)
    h0.on_press(m)
    h0.on_drag(m, QPointF(30, 100), Qt.KeyboardModifier.ControlModifier)
    assert calls == [QPointF(0, 5000)]                # anchor = opposite endpoint


def test_bubble_grip_never_constrains_even_with_ctrl():
    calls = []

    class _CScene(_StubScene):
        def _constrain_angle(self, anchor, raw):
            calls.append((anchor, raw))
            return QPointF(9, 9)

    gl = _make_gl()
    h2 = gl.manip_handles()[2]                          # bubble grip, opposite None
    sc = _CScene(); m = _StubM(sc)
    h2.on_press(m)
    h2.on_drag(m, QPointF(0, -1500), Qt.KeyboardModifier.ControlModifier)
    assert calls == []                                 # bubble grip: no constrain


def test_press_snapshots_siblings_and_cancel_restores_them():
    gl = _make_gl()
    h = gl.manip_handles()[1]
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    assert sc.snap_calls == [(gl, 1)]                  # snapshot excludes dragged, keyed by index
    h.on_drag(m, QPointF(0, 6000), Qt.KeyboardModifier.NoModifier)
    h.on_cancel(m)
    assert sc.restore_calls == [[("SNAP", gl, 1)]]
    assert gl.grip_points()[1] == QPointF(0, 5000)     # dragged grip restored


# --------------------------------------------------------------------------
# Coexistence gate
# --------------------------------------------------------------------------

def test_gridline_uses_manip_handles_gate():
    from firepro3d.selection_manipulator import _item_uses_manip_handles
    assert _item_uses_manip_handles(_make_gl()) is True


def test_legacy_grip_paths_skip_migrated_gridline(qapp, shown_model_view):
    view, scene = shown_model_view
    gl = _add_gl(scene, (0, 0), (0, 5000), "1")
    scene.set_mode("select")
    gl.setSelected(True)
    # A point exactly on the far endpoint grip: legacy _find_grip_hit must skip it.
    hit = scene._tools._find_grip_hit(QPointF(gl.grip_points()[1]))
    assert hit is None or hit[0] is not gl


class _LeftPress:
    """Minimal QGraphicsSceneMouseEvent stand-in for _LockIndicator.mousePressEvent."""
    def __init__(self, pos):
        self._pos = pos

    def accept(self):
        pass


def test_lock_toggle_hides_manip_grips(qapp, shown_model_view):
    view, scene = shown_model_view
    gl = _add_gl(scene, (0, 0), (0, 5000), "1")
    scene.set_mode("select")
    gl.setSelected(True)
    QApplication.processEvents()
    # Simulate the lock indicator click: lock, then nudge a rebake.
    gl._lock_indicator.mousePressEvent(_LeftPress(QPointF(gl.bubble1.pos())))
    QApplication.processEvents()
    assert gl._locked is True
    # grip_hittable now False for every index -> no hittable handle
    assert all(not gl.grip_hittable(i) for i in range(4))


# --------------------------------------------------------------------------
# Integration — real Model_Space + its live manipulator (driven lifecycle)
# --------------------------------------------------------------------------

def _drive_grip(scene, gl, index, start, path, mods=Qt.KeyboardModifier.NoModifier):
    """Select *gl*, install its handle *index* on the scene's live manipulator,
    and drive press -> moves through the manipulator (the lifecycle the view
    posts). Returns the manipulator so callers can finish or cancel."""
    scene.set_mode("select")
    gl.setSelected(True)
    QApplication.processEvents()
    m = scene._live_manip()
    h = gl.manip_handles()[index]
    m._begin_handle(h, QPointF(*start), QPointF(*start))
    for pt in path:
        m._update(QPointF(*pt), mods, QPointF(*pt))
    return m


def test_multiselect_endpoint_drag_moves_all_selected(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")
    b = _add_gl(scene, (300, 0), (300, 5000), "2")
    a.setSelected(True); b.setSelected(True)
    b_far0 = QPointF(b.grip_points()[1])
    m = _drive_grip(scene, a, index=1, start=(0, 5000), path=[(0, 5500), (0, 6000)])
    m._finish(QPointF(0, 6000), Qt.KeyboardModifier.NoModifier)
    assert a.grip_points()[1].y() != 5000                 # dragged moved
    assert b.grip_points()[1].y() == b_far0.y() + 1000    # sibling moved same delta on-axis


def test_one_commit_per_gesture(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")
    _add_gl(scene, (300, 0), (300, 5000), "2")
    calls = []
    scene._live_manip()._commit_hook = lambda mode: calls.append(mode)
    m = _drive_grip(scene, a, index=1, start=(0, 5000), path=[(0, 5500), (0, 6000)])
    m._finish(QPointF(0, 6000), Qt.KeyboardModifier.NoModifier)
    assert calls == ["grip"]


def test_esc_atomically_restores_dragged_and_siblings(qapp, shown_model_view):
    view, scene = shown_model_view
    a = _add_gl(scene, (0, 0), (0, 5000), "1")
    b = _add_gl(scene, (300, 0), (300, 5000), "2")
    a.setSelected(True); b.setSelected(True)
    a_before = a.to_dict(); b_before = b.to_dict()
    calls = []
    scene._live_manip()._commit_hook = lambda mode: calls.append(mode)
    m = _drive_grip(scene, a, index=1, start=(0, 5000), path=[(0, 5800), (0, 6200)])
    assert a.grip_points()[1].y() != 5000                 # mutated live
    assert b.grip_points()[1].y() != 5000
    m.cancel_drag()
    assert a.to_dict() == a_before                        # dragged restored
    assert b.to_dict() == b_before                        # sibling restored
    assert calls == []                                    # no commit on cancel


def test_locked_gridline_shows_no_hittable_grips(qapp, shown_model_view):
    view, scene = shown_model_view
    gl = _add_gl(scene, (0, 0), (0, 5000), "1")
    gl._locked = True
    assert all(not gl.grip_hittable(i) for i in range(4))


def test_hidden_bubble_grip_not_hittable(qapp, shown_model_view):
    view, scene = shown_model_view
    gl = _add_gl(scene, (0, 0), (0, 5000), "1")
    gl.bubble1.setVisible(False)
    assert gl.grip_hittable(2) is False                   # bubble1 standoff grip
    assert gl.grip_hittable(0) is True                    # endpoint still hittable
