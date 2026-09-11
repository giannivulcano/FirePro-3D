"""Lifecycle grip drag of a real Room's label grip == legacy apply_grip outcome;
the single label-centre grip is a round move grip present only when the label is
visible; a label-hidden room exposes NO grip and the coexistence gate is off.

U3 migration of Room onto manip_handles(). Room is the simplest migrated item:
one conditional label-move grip, zero special semantics (no Ctrl-constrain, no
sibling propagation) — and the first item to exercise the state-dependent empty
manip_handles() path."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.room import Room
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _labeled_room(name="101"):
    """Square room with a visible label (so grip_points() has the label grip)."""
    room = Room(boundary=[QPointF(0, 0), QPointF(1000, 0),
                          QPointF(1000, 1000), QPointF(0, 1000)])
    room.name = name
    room._update_label()
    return room


def _add_room(scene, name="101"):
    room = _labeled_room(name)
    scene.addItem(room)
    scene._rooms.append(room)
    return room


# --------------------------------------------------------------------------
# Handle shape + state-dependent presence
# --------------------------------------------------------------------------

def test_labeled_room_has_one_round_move_grip(qapp):
    room = _labeled_room()
    assert len(room.grip_points()) == 1          # label-centre grip present
    hs = room.manip_handles()
    assert len(hs) == 1
    assert type(hs[0]) is GripHandle
    assert hs[0].index == 0
    assert hs[0].role is HandleRole.GRIP
    assert hs[0].circular is True                # label = move affordance -> round
    assert hs[0].scene_position(None) == room.grip_points()[0]


def test_label_hidden_room_exposes_no_grip_and_gate_off(qapp):
    from firepro3d.selection_manipulator import _item_uses_manip_handles
    room = Room(boundary=[QPointF(0, 0), QPointF(1000, 0),
                          QPointF(1000, 1000), QPointF(0, 1000)])
    # No name/tag -> label hidden -> no grip.
    assert room.grip_points() == []
    assert room.manip_handles() == []
    # State-dependent path: empty manip_handles -> gate treats as not-migrated;
    # harmless because grip_points() is also empty (nothing renders either way).
    assert _item_uses_manip_handles(room) is False


def test_labeled_room_gate_on(qapp):
    from firepro3d.selection_manipulator import _item_uses_manip_handles
    assert _item_uses_manip_handles(_labeled_room()) is True


# --------------------------------------------------------------------------
# Apply parity + coexistence
# --------------------------------------------------------------------------

class _StubScene:
    _tools = None
    _grip_item = None
    _grip_dragging = False

    def get_effective_position(self, p):
        return QPointF(p)


class _StubM:
    _commit_hook = None

    def __init__(self, sc):
        self._sc = sc

    def scene(self):
        return self._sc

    def _reflow_live(self):
        pass


def test_label_grip_apply_matches_legacy(qapp):
    legacy = _labeled_room(); legacy.apply_grip(0, QPointF(700, 400))
    migrated = _labeled_room()
    h = migrated.manip_handles()[0]
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(700, 400), Qt.KeyboardModifier.NoModifier)
    assert migrated.to_dict() == legacy.to_dict()


def test_legacy_grip_paths_skip_migrated_room(qapp, shown_model_view):
    view, scene = shown_model_view
    room = _add_room(scene)
    scene.set_mode("select")
    room.setSelected(True)
    hit = scene._tools._find_grip_hit(QPointF(room.grip_points()[0]))
    assert hit is None or hit[0] is not room


# --------------------------------------------------------------------------
# Integration — real Model_Space + its live manipulator (driven lifecycle)
# --------------------------------------------------------------------------

def test_label_grip_drag_moves_label_one_commit(qapp, shown_model_view):
    view, scene = shown_model_view
    room = _add_room(scene)
    scene.set_mode("select")
    room.setSelected(True)
    QApplication.processEvents()
    start = QPointF(room.grip_points()[0])
    calls = []
    m = scene._live_manip()
    m._commit_hook = lambda mode: calls.append(mode)
    h = room.manip_handles()[0]
    m._begin_handle(h, start, start)
    m._update(QPointF(start.x() + 300, start.y() + 200),
              Qt.KeyboardModifier.NoModifier,
              QPointF(start.x() + 300, start.y() + 200))
    m._finish(QPointF(start.x() + 300, start.y() + 200), Qt.KeyboardModifier.NoModifier)
    assert room.grip_points()[0] != start        # label moved
    assert calls == ["grip"]
