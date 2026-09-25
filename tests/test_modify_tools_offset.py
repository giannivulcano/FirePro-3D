"""D9 workflow: pick (or preselected) → cursor side/distance → click/Enter; sticky; re-arm.

scene-tools.md D9: source = the single selected offsettable item, else "Pick
object to offset"; the cursor sets side + distance and the ghost follows; the
HUD Distance commits at the typed distance on the cursor's side; click/Enter
commits a new item (source kept), one undo; the tool stays armed with the last
distance sticky; Esc → Select; a too-large inward offset shows no ghost, posts
"Offset too large" and creates nothing. Text is not offsettable.
"""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from tests._modify_tools_helpers import PRIMITIVES, add_primitive
from tests._snap_polish_helpers import click, close_view, make_view, move

# D9: Text is not offsettable — excluded here, guarded separately below.
OFFSETTABLE = [n for n in PRIMITIVES if not n.startswith("text")]


def _type_distance(scene, text):
    assert scene.begin_dynamic_input() is True
    scene.dynamic_input.editor("Distance").setText(text)
    scene.dynamic_input._accept()


def _statuses(scene):
    log = []
    orig = scene._show_status
    scene._show_status = lambda msg, timeout=5000: (log.append(msg),
                                                    orig(msg, timeout))
    return log


@pytest.mark.parametrize("name", OFFSETTABLE)
def test_offset_preselected_by_typed_distance(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = item.to_dict()
        p0 = scene._undo_pos
        scene._modify_ctl.start("offset")
        assert scene.mode == "offset_side"                  # preselected → skip pick
        move(view, QPointF(400, -400))                      # outside / one side
        _type_distance(scene, "5")
        items = getattr(scene, attr)
        assert len(items) == 2                              # [RED]
        new = items[-1]
        assert type(new) is type(item) and new.scene() is scene
        assert item.to_dict() == before                     # source kept, untouched
        assert scene._undo_pos == p0 + 1
        assert scene.mode == "offset"                       # re-armed
        assert scene._offset_sticky == pytest.approx(5.0)
        scene.undo()
        assert len(getattr(scene, attr)) == 1               # one undo step
    finally:
        close_view(view, scene)


def test_offset_typed_distance_geometry_on_cursor_side(qapp):
    """Circle r=50, cursor outside, typed 5 → a concentric r=55 circle."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        scene._modify_ctl.start("offset")
        move(view, QPointF(400, -400))
        _type_distance(scene, "5")
        new = getattr(scene, attr)[-1]
        assert new._radius == pytest.approx(55.0)
        assert (new._center.x(), new._center.y()) == pytest.approx((0.0, 0.0))
    finally:
        close_view(view, scene)


def test_offset_cursor_ghost_follows(qapp):
    """The ghost is the candidate offset item's traced path (D11 style)."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")                      # r=50
        scene._modify_ctl.start("offset")
        move(view, QPointF(80, 0))                          # outside, 30 away
        assert len(scene._move_ghost) == 1
        br = scene._move_ghost[0].boundingRect()
        assert br.width() / 2 == pytest.approx(80.0, abs=0.5)
        move(view, QPointF(20, 0))                          # inside, 30 away
        br = scene._move_ghost[0].boundingRect()
        assert br.width() / 2 == pytest.approx(20.0, abs=0.5)
    finally:
        close_view(view, scene)


def test_offset_too_large_refuses(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")         # r=50
        scene._modify_ctl.start("offset")
        move(view, QPointF(1, 0))                           # inside
        log = _statuses(scene)
        p0 = scene._undo_pos
        scene.begin_dynamic_input()
        scene.dynamic_input.editor("Distance").setText("80")
        scene.dynamic_input._accept()
        assert len(getattr(scene, attr)) == 1
        assert scene._undo_pos == p0
        assert scene.dynamic_input is not None              # stays open (reject_commit)
        assert "Offset too large" in log
    finally:
        close_view(view, scene)


def test_offset_too_large_by_cursor_shows_no_ghost(qapp):
    """Rect 100x50: the cursor at the centre asks for a 25 mm inset → degenerate."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "rect")           # (0,0)-(100,-50)
        scene._modify_ctl.start("offset")
        log = _statuses(scene)
        move(view, QPointF(50, -25))
        assert scene._move_ghost == []
        assert "Offset too large" in log
        click(view, QPointF(50, -25))
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_offset_pick_when_nothing_selected(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        scene.clearSelection()
        instr = []
        scene.instructionChanged.connect(instr.append)
        scene._modify_ctl.start("offset")
        assert scene.mode == "offset"
        assert instr and instr[-1] == "Pick object to offset"
        click(view, QPointF(50, 0))                         # pick the line
        assert scene.mode == "offset_side"
        move(view, QPointF(50, -20)); click(view, QPointF(50, -20))
        assert len(getattr(scene, attr)) == 2
        new = getattr(scene, attr)[-1]
        assert abs(new.grip_points()[0].y() + 20) < 0.5
        assert scene.mode == "offset"                       # stays armed
    finally:
        close_view(view, scene)


def test_offset_enter_commits_cursor_distance(qapp):
    """Bare Enter commits like a click (D9 step 4) — one helper, no twin."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")           # (0,0)-(100,0)
        p0 = scene._undo_pos
        scene._modify_ctl.start("offset")
        move(view, QPointF(50, 30))
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        assert len(getattr(scene, attr)) == 2
        new = getattr(scene, attr)[-1]
        assert new.grip_points()[0].y() == pytest.approx(30.0, abs=0.5)
        assert scene._undo_pos == p0 + 1
    finally:
        close_view(view, scene)


def test_offset_sticky_typed_distance_locks_next_pick(qapp):
    """After a typed commit the next picked source reuses the distance; the
    cursor only picks the side (D9 step 5)."""
    view, scene = make_view(scale=1.0)
    try:
        line, attr = add_primitive(scene, "line")           # (0,0)-(100,0)
        scene._modify_ctl.start("offset")
        move(view, QPointF(50, 40))
        _type_distance(scene, "5")                          # line at y=5
        assert scene.mode == "offset"
        click(view, QPointF(50, 0))                         # pick the source again
        assert scene.mode == "offset_side"
        move(view, QPointF(50, -40)); click(view, QPointF(50, -40))
        ys = sorted(round(it.grip_points()[0].y(), 3) for it in getattr(scene, attr))
        assert ys == [-5.0, 0.0, 5.0]
    finally:
        close_view(view, scene)


def test_offset_refuses_text(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "text")
        scene._modify_ctl.start("offset")
        assert scene.mode == "offset"                       # not armed on Text
        assert scene._offset_source is None
        click(view, QPointF(5, -5))                         # on the text box
        assert scene.mode == "offset"
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_undo_mid_offset_cancels_the_tool(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")
        scene._modify_ctl.start("offset")
        move(view, QPointF(80, 0))
        assert scene.mode == "offset_side"
        scene.undo()
        assert scene.mode in (None, "select")
        assert scene._offset_source is None
        assert scene._move_ghost == []
    finally:
        close_view(view, scene)


def test_offset_esc_exits(qapp):
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")
        scene._modify_ctl.start("offset")
        move(view, QPointF(50, 20))
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
        assert scene.mode in (None, "select")
        assert scene._offset_source is None
        assert scene._offset_sticky is None
        assert scene._move_ghost == []
    finally:
        close_view(view, scene)


def test_offset_hud_seeds_the_live_cursor_distance(qapp):
    """The Distance HUD opens on the cursor distance — not the gridline
    replicate spacing fallback (_replicate_spacing / 1000)."""
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "circle")                      # r=50
        scene._modify_ctl.start("offset")
        move(view, QPointF(80, 0))                          # 30 outside
        assert scene.begin_dynamic_input() is True
        assert scene.dynamic_input.current_values()["Distance"] == \
            pytest.approx(30.0, abs=0.05)
    finally:
        close_view(view, scene)
