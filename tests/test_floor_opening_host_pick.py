"""FeaturePlacementController floor-void host pick / cycle / draft / commit
(floor-opening design A6).  Placement through the real view: test_floor_opening_placement.py.

Raw sources: LevelManager() seeds Level 1 @ 0.0, Level 2 @ DEFAULT_LEVEL_GAP_MM,
Level 3 @ 2x (level_manager.DEFAULT_LEVELS); DEFAULT_PATTERNS["Opening"] = "O{n}".
"""
from PyQt6.QtCore import QPointF

from firepro3d import marks
from firepro3d.feature_placement_controller import FloorOpeningDraft
from firepro3d.floor_slab import FloorSlab

LOW = [(-1000, -800), (1000, -800), (1000, 800), (-1000, 800)]
HIGH = [(-900, -700), (900, -700), (900, 700), (-900, 700)]
TRI = [QPointF(-200, -200), QPointF(200, -200), QPointF(200, 200)]


def _slab(scene, pts, top_level):
    s = FloorSlab(points=[QPointF(*p) for p in pts])
    s._top_level = top_level
    scene.addItem(s)
    scene._floor_slabs.append(s)
    return s


def test_slabs_at_point_topmost_first_visible_fill_only(qapp, model_scene):
    scene = model_scene()
    low = _slab(scene, LOW, "Level 1")
    high = _slab(scene, HIGH, "Level 2")
    hidden = _slab(scene, HIGH, "Level 3")
    hidden.setVisible(False)
    _slab(scene, LOW, "No Such Level")            # unresolvable top: skipped
    ctl = scene._feature_ctl
    assert ctl.floor_slabs_at(QPointF(0, 0)) == [high, low]
    assert ctl.floor_slabs_at(QPointF(950, 0)) == [low]      # HIGH spans +-900
    assert ctl.floor_slabs_at(QPointF(5000, 0)) == []


def test_arm_cycle_highlight_and_clear(qapp, model_scene):
    scene = model_scene()
    low = _slab(scene, LOW, "Level 1")
    high = _slab(scene, HIGH, "Level 2")
    ctl = scene._feature_ctl
    assert ctl.arm_floor_host(QPointF(0, 0)) is True
    assert ctl.floor_opening_host() is high
    hl = scene._floor_opening_host_hl
    assert hl.scene() is scene and hl.path() == high.path()
    assert ctl.cycle_floor_host() is True
    assert ctl.floor_opening_host() is low and hl.path() == low.path()
    assert ctl.cycle_floor_host() is True
    assert ctl.floor_opening_host() is high                  # wraps
    ctl.clear_floor_host_pick()
    assert ctl.floor_opening_host() is None
    assert hl.scene() is None and scene._floor_opening_host_hl is None


def test_cycle_with_one_candidate_is_not_consumed(qapp, model_scene):
    scene = model_scene()
    low = _slab(scene, LOW, "Level 1")
    ctl = scene._feature_ctl
    assert ctl.cycle_floor_host() is False                   # nothing armed
    assert ctl.arm_floor_host(QPointF(950, 0)) is True
    assert ctl.cycle_floor_host() is False
    assert ctl.floor_opening_host() is low


def test_arm_off_every_floor_rejects_with_status(qapp, model_scene):
    scene = model_scene()
    _slab(scene, LOW, "Level 1")
    seen = []
    scene.instructionChanged.connect(seen.append)
    ctl = scene._feature_ctl
    assert ctl.arm_floor_host(QPointF(5000, 0)) is False
    assert seen == ["Click on a floor to place an opening"]
    assert ctl.floor_opening_host() is None
    assert scene._floor_opening_host_hl is None


def test_draft_is_a_preview_never_on_the_host(qapp, model_scene):
    scene = model_scene()
    low = _slab(scene, LOW, "Level 1")
    ctl = scene._feature_ctl
    ctl.arm_floor_host(QPointF(0, 0))
    draft = ctl.begin_floor_opening_draft(QPointF(-200, -200))
    assert isinstance(draft, FloorOpeningDraft)
    assert scene._floor_active is draft and draft.scene() is scene
    draft.add_point(QPointF(200, -200))
    assert draft.last_point() == QPointF(200, -200)
    assert low.openings == [] and scene._floor_slabs == [low]
    assert marks.items_of_category(scene, "Opening") == []
    n_undo = len(scene._undo_stack)
    assert ctl.commit_floor_opening_draft() is None          # 2 points: discarded
    assert draft.scene() is None and scene._floor_active is None
    assert low.openings == [] and len(scene._undo_stack) == n_undo
    assert ctl.floor_opening_host() is None


def test_commit_appends_mints_pushes_and_selects(qapp, shown_model_view):
    view, scene = shown_model_view
    low = _slab(scene, LOW, "Level 1")
    scene.set_mode("floor_opening")      # registered in TB5; here any mode key works
    ctl = scene._feature_ctl
    assert ctl.arm_floor_host(QPointF(0, 0)) is True
    n_undo = len(scene._undo_stack)
    op = ctl.commit_floor_opening(TRI)
    assert op is not None and low.openings == [op]
    assert op.host is low and op.feature_id == "floor_sketched"
    assert op.points == TRI and op.scene() is scene
    assert marks.get_mark(op) == "O1"
    assert len(scene._undo_stack) == n_undo + 1
    assert scene._floor_opening_host_hl is None              # pick torn down


def test_commit_under_three_points_discards_without_undo(qapp, model_scene):
    scene = model_scene()
    low = _slab(scene, LOW, "Level 1")
    ctl = scene._feature_ctl
    ctl.arm_floor_host(QPointF(0, 0))
    n_undo = len(scene._undo_stack)
    assert ctl.commit_floor_opening(TRI[:2]) is None
    assert low.openings == [] and len(scene._undo_stack) == n_undo
