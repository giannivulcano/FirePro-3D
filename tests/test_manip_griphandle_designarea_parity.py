"""Lifecycle grip drag of a real DesignArea's badge grip == legacy apply_grip
outcome; the single badge-centre grip is a round move grip present only when the
badge is visible; a badge-hidden area exposes NO grip and the coexistence gate is
off.

U3 migration of DesignArea onto manip_handles(). A Room twin: one conditional
badge-move grip, zero special semantics (no Ctrl-constrain, no sibling
propagation)."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.design_area import DesignArea
from firepro3d.manip_handle import GripHandle
from firepro3d.manip_math import HandleRole


def _da_with_badge(visible=True):
    da = DesignArea()
    da.badge.setVisible(visible)
    return da


def _add_da(scene):
    """Add a design area whose badge is genuinely visible in-scene: the badge
    shows only when the area has members (``_sync_badge`` gates on
    ``bool(self._sprinklers)``) and is not in design-area edit mode. A stub
    member + a matching level + a post-select ``_sync_badge`` satisfy that."""
    da = DesignArea()
    da._sprinklers = [object()]          # non-empty -> _sync_badge shows the badge
    da.level = "Level 1"                 # match the fixture's active level (not filtered out)
    scene.addItem(da)
    scene.design_areas.append(da)
    scene.set_mode("select")             # not "design_area" -> not editing
    da._sync_badge()
    return da


# --------------------------------------------------------------------------
# Handle shape + state-dependent presence
# --------------------------------------------------------------------------

def test_visible_badge_has_one_round_move_grip(qapp):
    da = _da_with_badge(visible=True)
    assert len(da.grip_points()) == 1
    hs = da.manip_handles()
    assert len(hs) == 1
    assert type(hs[0]) is GripHandle
    assert hs[0].index == 0
    assert hs[0].role is HandleRole.GRIP
    assert hs[0].circular is True                 # badge = move affordance -> round
    assert hs[0].scene_position(None) == da.grip_points()[0]


def test_hidden_badge_exposes_no_grip(qapp):
    da = _da_with_badge(visible=False)
    assert da.grip_points() == []
    assert da.manip_handles() == []


def test_visible_badge_exposes_grip(qapp):
    assert _da_with_badge(visible=True).manip_handles()


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


def test_badge_grip_apply_matches_legacy(qapp):
    legacy = _da_with_badge(); legacy.apply_grip(0, QPointF(700, 400))
    migrated = _da_with_badge()
    h = migrated.manip_handles()[0]
    sc = _StubScene(); m = _StubM(sc)
    h.on_press(m)
    h.on_drag(m, QPointF(700, 400), Qt.KeyboardModifier.NoModifier)
    assert migrated.badge_offset() == legacy.badge_offset()


# --------------------------------------------------------------------------
# Integration — real Model_Space + its live manipulator (driven lifecycle)
# --------------------------------------------------------------------------

def test_badge_grip_drag_moves_badge_one_commit(qapp, shown_model_view):
    view, scene = shown_model_view
    da = _add_da(scene)
    scene.set_mode("select")
    da.setSelected(True)
    QApplication.processEvents()
    start = QPointF(da.grip_points()[0])
    calls = []
    m = scene._live_manip()
    m._commit_hook = lambda mode: calls.append(mode)
    h = da.manip_handles()[0]
    target = QPointF(start.x() + 300, start.y() + 200)
    m._begin_handle(h, start, start)
    m._update(target, Qt.KeyboardModifier.NoModifier, target)
    m._finish(target, Qt.KeyboardModifier.NoModifier)
    assert da.grip_points()[0] != start          # badge moved
    assert calls == ["grip"]
