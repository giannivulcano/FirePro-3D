"""SB6 AC2 / D9 -- a tag's leader: none while off; a straight line from the tag to its
host anchor while on; its weight and End follow the Tags style; dragging the knee grip
adds the one elbow. Observable: rendered pixels (tests/_sb6_helpers.ink), with the
scene geometry derived from the raw wall and the WallTag.fpdb hexagon (5 mm x drawing
scale 100: +/-500 x +/-433 scene), so a straight leader runs x = 0 from y = -2567 to the
anchor (0, 0). Render rect (-1500, -4000, 3000, 4500) at 300 x 450 px = 10 units / px."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d import hosted_dependents
from firepro3d import paper_display as pd
from tests._sb6_helpers import add_wall, ink, place_tag, render

RECT = QRectF(-1500.0, -4000.0, 3000.0, 4500.0)
SHAFT = (-60.0, -2000.0, 60.0, -1000.0)        # on the straight leader, clear of tag and wall


def _scene(make_model_space, leader):
    from firepro3d.level_manager import LevelManager
    ms = make_model_space()
    ms._level_manager = LevelManager()
    w = add_wall(ms)
    ms.push_undo_state()
    return ms, place_tag(ms, w, leader=leader, u=0.0, v=-3000.0)


def _img(ms):
    return render(ms, RECT, 300, 450)


def test_ac2_no_leader_when_off(qapp, make_model_space, real_system_library):
    ms, tag = _scene(make_model_space, leader=False)
    assert ink(_img(ms), RECT, *SHAFT) == 0


def test_ac2_straight_leader_from_tag_to_host_anchor(qapp, make_model_space, real_system_library):
    ms, tag = _scene(make_model_space, leader=True)
    img = _img(ms)
    assert ink(img, RECT, *SHAFT) > 0                                     # [RED: leader op]
    assert ink(img, RECT, 200.0, -2000.0, 600.0, -1000.0) == 0           # straight: nothing off-axis


def test_ac2_leader_weight_follows_the_tags_style(qapp, make_model_space, real_system_library):
    ms, tag = _scene(make_model_space, leader=True)
    rows = sorted(pd.project_line_weights(), key=lambda d: d.width_mm)
    box = (-100.0, -1600.0, 100.0, -1400.0)
    pd.set_tag_leader_weight(rows[0].name)
    hosted_dependents.refresh_tag_leaders(ms)
    thin = ink(_img(ms), RECT, *box)
    pd.set_tag_leader_weight(rows[-1].name)
    hosted_dependents.refresh_tag_leaders(ms)
    thick = ink(_img(ms), RECT, *box)
    assert thick > thin > 0                                               # [RED: weight getter]


def test_ac2_leader_end_follows_the_tags_style(qapp, make_model_space, real_system_library):
    ms, tag = _scene(make_model_space, leader=True)
    box = (-100.0, -90.0, 100.0, -10.0)         # the host end: the arrow's body, inside the wall band
    arrow = ink(_img(ms), RECT, *box)
    pd.set_tag_leader_end("none")
    hosted_dependents.refresh_tag_leaders(ms)
    plain = ink(_img(ms), RECT, *box)
    assert arrow > plain > 0                                              # [RED: end getter]


def test_ac2_knee_grip_adds_one_elbow(qapp, make_model_space, real_system_library):
    ms, tag = _scene(make_model_space, leader=True)
    mid = (500.0 - 60.0, -750.0 - 60.0, 500.0 + 60.0, -750.0 + 60.0)    # midpoint of knee (1000,-1500) -> anchor (0,0)
    assert ink(_img(ms), RECT, *mid) == 0
    tag.setSelected(True)
    QApplication.processEvents()
    m = ms._live_manip()
    p0 = ms._undo_pos
    (handle,) = tag.manip_extra_handles()
    g0, g1 = QPointF(tag.grip_points()[0]), QPointF(1000.0, -1500.0)
    assert (g0.x(), g0.y()) == pytest.approx((0.0, -1500.0))              # straight leader: grip at its midpoint
    m._begin_handle(handle, g0, g0)
    m._update(g1, Qt.KeyboardModifier.NoModifier, g1)
    m._finish(g1, Qt.KeyboardModifier.NoModifier)
    assert ms._undo_pos == p0 + 1
    assert tag.tag["leader"]["knee"] == pytest.approx([1000.0, -1500.0], abs=60.0)   # raw: u = x, v = y here
    assert ink(_img(ms), RECT, *mid) > 0                                  # [RED: knee write]


def test_m2_unmoved_host_committed_step_does_not_reshape_leaders(
        qapp, make_model_space, real_system_library):
    """A committed step that did not move the host leaves a leader tag's built
    leader alone (observable: the memoised leader list survives the step -- a
    re-shape clears it); a moved host re-shapes it and the host end follows."""
    ms, tag = _scene(make_model_space, leader=True)
    img = _img(ms)                                   # builds + memoises the leader
    built = tag._leader_cache
    assert built is not None and built[2] is not built[0]
    ms.push_undo_state()
    ms.push_undo_state()
    assert tag._leader_cache is built                # [RED: narrowing] unmoved host: untouched
    wall = ms._walls[0]
    wall.translate(500.0, 0.0)                       # anchor (0, 0) -> (500, 0)
    ms.push_undo_state()
    assert tag._leader_cache is not built            # re-shaped (cleared; rebuilt at the next paint)
    img = _img(ms)
    end_box = (500.0 - 100.0, -400.0, 500.0 + 100.0, -110.0)
    assert ink(img, RECT, *end_box) > 0              # the shaft now arrives at the new anchor: the leader re-shaped


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
