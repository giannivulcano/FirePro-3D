"""SB6 AC2 / D9 / D10 -- a tag's leader is a Note leader: none while off; on, a shoulder
leaves the tag box at a right angle (default: the right edge at mid-height, 6 printed mm),
then knee -> tip at the host anchor. The knee grip re-picks the edge as on Notes; the tip
grip moves the tip, which then follows the host; the tag's own Leader Weight / Leader End
rows restyle it in one undo step each; the Display Manager has no Tags row.

Observable: rendered pixels (tests/_sb6_helpers.ink). Scene geometry from the raw wall and
the WallTag.fpdb hexagon (5 mm x drawing scale 100: +/-500 x +/-433 scene). The tag sits at
(0, -3000), so the default shoulder runs (500, -3000) -> knee (1100, -3000) and the run goes
knee -> anchor (0, 0); the old straight leader ran x = 0 from the box down to the anchor.
Render rect (-1500, -4000, 3000, 4500) at 300 x 450 px = 10 units / px."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d import paper_display as pd
from tests._sb6_helpers import (add_wall, drop_panel, expected_pose, ink, panel_for, place_tag,
                                render, tags_of)
from tests._snap_polish_helpers import click, close_view, make_view, move

RECT = QRectF(-1500.0, -4000.0, 3000.0, 4500.0)
SHAFT = (-60.0, -2000.0, 60.0, -1000.0)        # on the old straight leader, clear of the new run
R_SHOULDER = (650.0, -3040.0, 950.0, -2960.0)   # the default shoulder, clear of box and knee
L_SHOULDER = (-950.0, -3040.0, -650.0, -2960.0)
ABOVE_R_SHOULDER = (650.0, -3300.0, 950.0, -3100.0)   # a slanted (non-right-angle) start would ink here


def _scene(make_model_space, leader):
    from firepro3d.level_manager import LevelManager
    ms = make_model_space()
    ms._level_manager = LevelManager()
    w = add_wall(ms)
    ms.push_undo_state()
    return ms, place_tag(ms, w, leader=leader, u=0.0, v=-3000.0)


def _img(ms):
    return render(ms, RECT, 300, 450)


def _drag_grip(ms, tag, index, to):
    """Drag *tag*'s leader grip *index* to scene *to* through the live manipulator's
    handle path (the Note grip path)."""
    tag.setSelected(True)
    QApplication.processEvents()
    m = ms._live_manip()
    (handle,) = [h for h in tag.manip_extra_handles() if h.index == index]
    g0 = QPointF(tag.grip_points()[index])
    m._begin_handle(handle, g0, g0)
    m._update(to, Qt.KeyboardModifier.NoModifier, to)
    m._finish(to, Qt.KeyboardModifier.NoModifier)
    return g0


def test_ac2_no_leader_when_off(qapp, make_model_space, real_system_library):
    ms, tag = _scene(make_model_space, leader=False)
    img = _img(ms)
    assert ink(img, RECT, *SHAFT) == 0 and ink(img, RECT, *R_SHOULDER) == 0


def test_ac2_leader_leaves_the_tag_box_edge_at_a_right_angle(qapp, make_model_space,
                                                             real_system_library):
    """Rewritten (VC5): the straight tag-origin -> anchor leader is superseded by the
    Note shoulder + knee (D9 revised 2026-11-16)."""
    ms, tag = _scene(make_model_space, leader=True)
    img = _img(ms)
    assert ink(img, RECT, *R_SHOULDER) > 0                               # [RED: shoulder]
    assert ink(img, RECT, *ABOVE_R_SHOULDER) == 0                        # level: a right angle off the edge
    assert ink(img, RECT, *SHAFT) == 0                                   # not the old straight path
    mid = (550.0 - 60.0, -1500.0 - 60.0, 550.0 + 60.0, -1500.0 + 60.0)  # knee (1100,-3000) -> anchor midpoint
    assert ink(img, RECT, *mid) > 0


def test_ac2_knee_grip_re_picks_the_edge(qapp, make_model_space, real_system_library):
    """Rewritten (VC5): the knee no longer adds an elbow to a straight leader; it re-solves
    the shoulder's edge as on Notes (text_leader.solve_knee)."""
    ms, tag = _scene(make_model_space, leader=True)
    img = _img(ms)
    assert ink(img, RECT, *L_SHOULDER) == 0 and ink(img, RECT, *R_SHOULDER) > 0
    p0 = ms._undo_pos
    g0 = _drag_grip(ms, tag, 0, QPointF(-1100.0, -3000.0))           # to the other side
    assert (g0.x(), g0.y()) == pytest.approx((1100.0, -3000.0), abs=1.0)   # the default knee
    assert ms._undo_pos == p0 + 1
    (tag,) = tags_of(ms)
    assert tag.tag["leader"]["edge"] == "L"                              # [RED: solve_knee]
    img = _img(ms)
    assert ink(img, RECT, *L_SHOULDER) > 0                               # the ink moved with it
    assert ink(img, RECT, *R_SHOULDER) == 0


def test_ac2_tip_grip_moves_the_arrow_and_the_tip_follows_a_host_move(qapp, real_system_library):
    view, scene = make_view(role="plan", scale=0.1)
    try:
        w = add_wall(scene)
        scene.push_undo_state()
        tag = place_tag(scene, w, leader=True, u=0.0, v=-3000.0)
        new_tip = (-700.0, -1000.0, -500.0, -800.0)                      # around (-600, -900)
        assert ink(_img(scene), RECT, *new_tip) == 0
        p0 = scene._undo_pos
        g0 = _drag_grip(scene, tag, 1, QPointF(-600.0, -900.0))
        assert (g0.x(), g0.y()) == pytest.approx((0.0, 0.0), abs=1e-6)  # a new tip: the host anchor
        assert scene._undo_pos == p0 + 1
        (tag,) = tags_of(scene)
        assert ink(_img(scene), RECT, *new_tip) > 0                      # [RED: tip write]
        # a real Move of the host carries the tip (host frame, D9)
        scene.clearSelection()
        w.setSelected(True)
        scene._modify_ctl.start("move")
        click(view, QPointF(0.0, 0.0))
        move(view, QPointF(300.0, 700.0))
        click(view, QPointF(300.0, 700.0))
        assert (w.pt1.x(), w.pt1.y()) != (-2000.0, 0.0)                  # the wall really moved
        (tag,) = tags_of(scene)
        x, y, _r = expected_pose(w, u=-600.0, v=-900.0)                 # anchor' + R . tip_uv, raw endpoints
        t = tag.grip_points()[1]
        assert (t.x(), t.y()) == pytest.approx((x, y), abs=1.0)          # [RED: tip not host-frame]
        img = _img(scene)
        assert ink(img, RECT, x - 100.0, y - 100.0, x + 100.0, y + 100.0) > 0
        assert ink(img, RECT, *new_tip) == 0                             # it left the old spot
    finally:
        close_view(view, scene)


def _weight_names():
    rows = sorted(pd.project_line_weights(), key=lambda d: d.width_mm)
    return pd.picker_weight_name(rows[0].name), pd.picker_weight_name(rows[-1].name)


def test_ac2_leader_weight_row_restyles_this_tag_in_one_step(qapp, tmp_path, make_model_space,
                                                             real_system_library):
    """Rewritten (VC5): the weight is the tag's own Leader Weight row (D10), not the
    Display Manager Tags row."""
    ms, tag = _scene(make_model_space, leader=True)
    lo, hi = _weight_names()
    pm = panel_for(tag, tmp_path)
    try:
        props = tag.get_properties()
        assert "Leader End" in props and "Leader Weight" in props       # the Note rows (D10)
        pm._apply_property("Leader Weight", lo)
        thin = ink(_img(ms), RECT, *R_SHOULDER)
        p0 = ms._undo_pos
        pm._apply_property("Leader Weight", hi)
        assert ms._undo_pos == p0 + 1                                    # one undo step
        (tag,) = tags_of(ms)
        thick = ink(_img(ms), RECT, *R_SHOULDER)
        assert thick > thin > 0                                          # [RED: weight row]
    finally:
        drop_panel(pm)


def test_ac2_leader_end_row_switches_this_tags_end_in_one_step(qapp, tmp_path, make_model_space,
                                                               real_system_library):
    """Rewritten (VC5): the End is the tag's own Leader End row (D10)."""
    from firepro3d.capabilities import end_choices
    ms, tag = _scene(make_model_space, leader=True)
    box = (-40.0, -95.0, 90.0, -5.0)            # the arrow body at the tip (run from the upper right)
    arrow = ink(_img(ms), RECT, *box)
    label = {r: n for n, r in end_choices(ms.block_registry, ())}["none"]
    pm = panel_for(tag, tmp_path)
    try:
        p0 = ms._undo_pos
        pm._apply_property("Leader End", label)
        assert ms._undo_pos == p0 + 1                                    # one undo step
        (tag,) = tags_of(ms)
        assert tag.tag["leader"]["end"] == "none"
        plain = ink(_img(ms), RECT, *box)
        assert arrow > plain > 0                                         # [RED: end row]
        pm.show_properties(None)
        ms.undo()
        (tag,) = tags_of(ms)
        assert tag.tag["leader"]["end"] == "system-endtypes-arrow"
    finally:
        drop_panel(pm)


def test_ac2_display_manager_has_no_tags_row_and_ignores_a_stale_key(qapp, make_model_space):
    """D10 revised: the DM Tags row is gone -- no row, no saved key; a project dict that
    still carries one applies without error (the branch never shipped: no migration)."""
    from PyQt6.QtWidgets import QLabel, QTreeWidgetItemIterator
    from firepro3d.display_manager import (DisplayManager, apply_project_display_settings,
                                           get_display_settings_for_save)
    ms = make_model_space()
    d = DisplayManager(ms)
    try:
        texts = []
        it = QTreeWidgetItemIterator(d._tree)
        while it.value() is not None:
            row = it.value()
            texts.append(row.text(0))
            host = d._tree.itemWidget(row, 0)
            if host is not None:
                texts += [lbl.text() for lbl in host.findChildren(QLabel)]
            it += 1
        assert texts and "Tags" not in texts                             # [RED: row removed]
    finally:
        d.reject()
    saved = get_display_settings_for_save()
    assert "Tags" not in saved
    apply_project_display_settings(ms, dict(saved, Tags={"leader_end": "none",
                                                         "leader_weight": "Thin"}))


def test_m2_unmoved_host_committed_step_does_not_reshape_leaders(
        qapp, make_model_space, real_system_library):
    """A committed step that did not move the host leaves a leader tag's built
    leader alone (observable: the memoised leader list survives the step -- a
    re-shape clears it); a moved host re-shapes it and the tip follows."""
    ms, tag = _scene(make_model_space, leader=True)
    _img(ms)                                         # builds + memoises the leader
    built = tag._leader_cache
    assert built is not None and built[2] is not built[0]
    ms.push_undo_state()
    ms.push_undo_state()
    assert tag._leader_cache is built                # [RED: narrowing] unmoved host: untouched
    wall = ms._walls[0]
    wall.translate(500.0, 0.0)                       # anchor (0, 0) -> (500, 0)
    ms.push_undo_state()
    assert tag._leader_cache is not built            # re-shaped (cleared; rebuilt at the next paint)
    end_box = (500.0 - 100.0, -400.0, 500.0 + 100.0, -110.0)
    assert ink(_img(ms), RECT, *end_box) > 0         # the run now arrives at the new anchor


def test_m4_leader_tag_selection_frame_is_the_tag_box_only(qapp, make_model_space, real_system_library):
    """User ruling (VC9 M4): the frame of a leader tag is the tag box, as a Note's is --
    not stretched down the leader to a host 3 m away."""
    from firepro3d.selection_manipulator import manip_bounds
    ms, with_leader = _scene(make_model_space, leader=True)
    plain = place_tag(ms, ms._walls[0], leader=False, u=0.0, v=-3000.0)
    want = plain.manip_bounds()
    got = with_leader.manip_bounds()
    assert got.height() < 1500.0                                          # the box, not ~3000 to the host
    assert (got.left(), got.top(), got.width(), got.height()) == pytest.approx(
        (want.left(), want.top(), want.width(), want.height()))           # [RED: leader out of the frame]
    f = manip_bounds(with_leader)                                         # the rect the manipulator draws
    assert f.height() == pytest.approx(want.height())
    assert with_leader._frame_rect(leader=False).height() < with_leader._frame_rect().height()
