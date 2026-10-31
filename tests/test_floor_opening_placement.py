"""Floor-void placement through the REAL view (floor-opening design A6, AC1/AC2).

Posted QMouseEvent / QKeyEvent on the SHOWN Model_View (conftest shown_model_view:
m11 = 0.25, visible +-1596 x +-1196, 80-unit snap aperture).  Click points sit
>= 300 units from every slab vertex / edge midpoint so no snap moves them.
Raw sources: LevelManager() seeds Level 2 @ DEFAULT_LEVEL_GAP_MM above Level 1
(level_manager.DEFAULT_LEVELS); DEFAULT_PATTERNS["Opening"] = "O{n}".
"""
from PyQt6.QtCore import QPointF, Qt

from firepro3d import marks
from firepro3d.floor_slab import FloorSlab
from tests.test_floor_placement_workflow import _click, _key

LOW = [(-1000, -800), (1000, -800), (1000, 800), (-1000, 800)]
HIGH = [(-900, -700), (900, -700), (900, 700), (-900, 700)]


def _slab(scene, pts, top_level="Level 1", name=""):
    s = FloorSlab(points=[QPointF(*p) for p in pts])
    s._top_level = top_level
    s.name = name
    scene.addItem(s)
    scene._floor_slabs.append(s)
    return s


def _voids(scene):
    return [i for i in scene.items() if type(i).__name__ == "FloorOpening"]


def _to_polygon(scene):
    scene.cycle_placement_variant(+1)      # corner rect -> centre rect
    scene.cycle_placement_variant(+1)      # centre rect -> polygon
    assert scene._floor_primitive == "polygon"


def test_first_click_off_every_floor_is_rejected_with_status(qapp, shown_model_view):
    """GUARD AC1: empty-space first click -> no-op + status line."""
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    seen = []
    scene.instructionChanged.connect(seen.append)
    n_undo = len(scene._undo_stack)
    _click(view, QPointF(1400, 1000))          # off the slab (+-1000 x +-800)
    assert "Click on a floor to place an opening" in seen
    assert scene._mode_placement_anchor() is None          # nothing armed
    _click(view, QPointF(-300, -300))          # a real floor click now arms
    _click(view, QPointF(300, -300))
    _click(view, QPointF(0, 300))
    assert len(slab.openings) == 1             # the rejected click did not count
    assert len(scene._undo_stack) == n_undo + 1


def test_rect_void_commits_on_host_and_selects(qapp, shown_model_view):
    """GUARD AC1/A6: corner rect commits ONE void on the host, one undo step,
    single placement -> Select with the void selected."""
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    assert scene._floor_primitive == "rect" and scene._floor_rect_from_center is False
    n_undo = len(scene._undo_stack)
    _click(view, QPointF(-300, -300))          # base: on the slab -> host armed
    _click(view, QPointF(300, -300))           # first side
    _click(view, QPointF(0, 300))              # depth -> commit
    assert len(slab.openings) == 1
    op = slab.openings[0]
    assert op.host is slab and op.feature_id == "floor_sketched"
    assert len(op.points) == 4
    assert _voids(scene) == [op]
    assert scene._floor_slabs == [slab]        # no slab was built
    assert len(scene._undo_stack) == n_undo + 1
    assert marks.get_mark(op) == "O1"
    assert scene.mode == "select" and op.isSelected()


def test_centre_rect_variant_commits_a_void(qapp, shown_model_view):
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    scene.cycle_placement_variant(+1)
    assert scene._floor_rect_from_center is True
    _click(view, QPointF(0, 0))                # centre
    _click(view, QPointF(300, 0))              # edge midpoint
    _click(view, QPointF(0, 300))              # depth
    assert len(slab.openings) == 1 and len(slab.openings[0].points) == 4


def test_first_click_picks_the_topmost_slab(qapp, shown_model_view):
    """GUARD AC2: highest resolved top first; the void cuts only its host.

    Both slabs are visible because no level-visibility pass has run (in a real
    Level-1 plan the Level-2 slab is z-range hidden); the pick only needs isVisible().
    """
    view, scene = shown_model_view
    low = _slab(scene, LOW, "Level 1", "Low")
    high = _slab(scene, HIGH, "Level 2", "High")
    assert low.isVisible() and high.isVisible()
    assert high.z_range_mm()[1] > low.z_range_mm()[1]
    scene.set_mode("floor_opening")
    _click(view, QPointF(-300, -300))
    assert scene._floor_opening_host_hl.path() == high.path()     # highlighted
    _click(view, QPointF(300, -300))
    _click(view, QPointF(0, 300))
    assert len(high.openings) == 1 and low.openings == []
    assert all(holes == [] for _outer, holes in low.cut_region())   # low is not cut (F6)


def test_spacebar_cycles_the_host_between_stacked_slabs(qapp, shown_model_view):
    """GUARD AC2: Space while drawing moves the pick to the lower slab."""
    view, scene = shown_model_view
    low = _slab(scene, LOW, "Level 1", "Low")
    high = _slab(scene, HIGH, "Level 2", "High")
    scene.set_mode("floor_opening")
    _click(view, QPointF(-300, -300))
    _key(view, Qt.Key.Key_Space)
    assert scene._floor_opening_host_hl.path() == low.path()
    _click(view, QPointF(300, -300))
    _click(view, QPointF(0, 300))
    assert high.openings == [] and len(low.openings) == 1
    assert low.openings[0].host is low
    assert all(holes == [] for _outer, holes in high.cut_region())  # high is not cut (F6)
    assert scene._floor_opening_host_hl is None                   # torn down


def test_polygon_void_closes_near_first_and_commits(qapp, shown_model_view):
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    _click(view, QPointF(-300, -300))
    _click(view, QPointF(300, -300))
    _click(view, QPointF(300, 300))
    assert slab.openings == []                 # the draft is not on the host
    _click(view, QPointF(-300, -300))          # near the first vertex -> close
    assert len(slab.openings) == 1 and len(slab.openings[0].points) == 3
    assert scene._floor_active is None and scene.mode == "select"
    assert scene._floor_slabs == [slab]


def test_polygon_enter_with_three_points_commits(qapp, shown_model_view):
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    for p in ((-300, -300), (300, -300), (300, 300)):
        _click(view, QPointF(*p))
    _key(view, Qt.Key.Key_Return)
    assert len(slab.openings) == 1 and scene.mode == "select"


def test_polygon_under_three_points_discards_without_undo(qapp, shown_model_view):
    """GUARD AC1: Enter with 2 points -> no void, no undo entry, draft gone, re-armed."""
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    n_undo = len(scene._undo_stack)
    _click(view, QPointF(-300, -300))
    _click(view, QPointF(300, -300))
    draft = scene._floor_active
    assert draft is not None and draft.scene() is scene
    _key(view, Qt.Key.Key_Return)
    assert slab.openings == [] and _voids(scene) == []
    assert draft.scene() is None and scene._floor_active is None
    assert len(scene._undo_stack) == n_undo
    assert scene.mode == "floor_opening"       # re-armed at step 0
    assert scene._floor_opening_host_hl is None


def test_delete_pops_draft_vertices_then_disarms(qapp, shown_model_view):
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    _click(view, QPointF(-300, -300))
    _click(view, QPointF(300, -300))
    _key(view, Qt.Key.Key_Delete)
    assert len(scene._floor_active._points) == 1
    _key(view, Qt.Key.Key_Delete)
    assert scene._floor_active is None and scene._floor_opening_host_hl is None
    assert slab in scene._floor_slabs          # Delete never deleted the slab


def test_switching_to_floor_discards_the_void_draft(qapp, shown_model_view):
    """GUARD: leaving floor_opening mid-draw never keeps (or slab-commits) the draft."""
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    for p in ((-300, -300), (300, -300), (300, 300)):
        _click(view, QPointF(*p))
    draft = scene._floor_active
    scene.set_mode("floor")
    assert draft.scene() is None and scene._floor_active is None
    assert slab.openings == [] and scene._floor_slabs == [slab]
    assert scene._floor_opening_host_hl is None


def test_floor_slab_placement_unchanged(qapp, shown_model_view):
    """Regression: the shared machinery still builds a FloorSlab in floor mode."""
    view, scene = shown_model_view
    scene.set_mode("floor")
    _click(view, QPointF(-300, -300))
    _click(view, QPointF(300, -300))
    _click(view, QPointF(0, 300))
    assert len(scene._floor_slabs) == 1 and _voids(scene) == []
    assert scene.mode == "select" and scene._floor_slabs[0].isSelected()


def _post(view, et, scene_pt):
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    vp = view.viewport(); p = view.mapFromScene(scene_pt)
    QApplication.sendEvent(vp, QMouseEvent(et, p.toPointF(), vp.mapToGlobal(p).toPointF(),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def test_polygon_double_click_commits_the_void(qapp, shown_model_view):
    """GUARD A6: double-click is a void commit point (the double-click vertex is dropped, as for slabs)."""
    from PyQt6.QtCore import QEvent
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    for p in ((-300, -300), (300, -300), (300, 300)):
        _click(view, QPointF(*p))
    _click(view, QPointF(-300, 300))                       # press 1 of the double
    _post(view, QEvent.Type.MouseButtonDblClick, QPointF(-300, 300))
    _post(view, QEvent.Type.MouseButtonRelease, QPointF(-300, 300))
    assert len(slab.openings) == 1 and len(slab.openings[0].points) == 3
    assert [i for i in scene.items() if type(i).__name__ == "FloorOpeningDraft"] == []
    assert scene._floor_active is None and scene.mode == "select"


def _drafts(scene):
    return [i for i in scene.items() if type(i).__name__ == "FloorOpeningDraft"]


def _draw_three(view, scene):
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    for p in ((-300, -300), (300, -300), (300, 300)):
        _click(view, QPointF(*p))
    assert len(_drafts(scene)) == 1


def test_delete_pop_to_first_step_shows_the_floor_opening_text(qapp, shown_model_view):
    """GUARD (TB4-5 review M1): Delete-pop to step 0 shows the host-pick text, not the slab text."""
    view, scene = shown_model_view
    _slab(scene, LOW)
    scene.set_mode("floor_opening")
    _to_polygon(scene)
    _click(view, QPointF(-300, -300))
    seen = []
    scene.instructionChanged.connect(seen.append)
    _key(view, Qt.Key.Key_Delete)
    assert seen[-1] == "Click on a floor to place an opening"
    assert "Pick first boundary point" not in seen


def test_escape_mid_draw_leaves_no_draft_void_or_undo(qapp, shown_model_view):
    """GUARD (TB4-5 review M2a): Esc mid-draw -> draft gone, host untouched, no undo entry."""
    view, scene = shown_model_view
    slab = _slab(scene, LOW)
    n_undo = len(scene._undo_stack)
    _draw_three(view, scene)
    _key(view, Qt.Key.Key_Escape)
    assert _drafts(scene) == [] and scene._floor_active is None
    assert slab.openings == [] and _voids(scene) == []
    assert len(scene._undo_stack) == n_undo


def test_clear_scene_mid_draw_leaves_no_draft_and_resets_state(qapp, shown_model_view):
    """GUARD (TB4-5 review M2b): scene_io clear mid-draw -> no draft, floor_opening state reset."""
    view, scene = shown_model_view
    _slab(scene, LOW)
    _draw_three(view, scene)
    scene._clear_scene()
    assert _drafts(scene) == [] and _voids(scene) == []
    assert scene._floor_active is None and scene._floor_slabs == []
    assert scene._floor_opening_candidates == [] and scene._floor_opening_host_hl is None
    assert scene.mode != "floor_opening"


def test_save_mid_draw_holds_no_draft_or_void_record(qapp, shown_model_view, tmp_path):
    """GUARD (TB4-5 review M2c): a project saved mid-draw carries the slab only, no void."""
    import json
    view, scene = shown_model_view
    _slab(scene, LOW)
    _draw_three(view, scene)
    path = tmp_path / "mid_draw.fpd"
    scene.save_to_file(str(path))
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert len(data["floor_slabs"]) == 1
    assert data["floor_slabs"][0].get("openings", []) == []
    assert "FloorOpeningDraft" not in text
