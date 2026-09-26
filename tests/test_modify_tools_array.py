"""D10: base -> cursor direction+spacing -> Spacing·Count(total) HUD -> N-1 copies, 1 undo.

Linear, on-canvas only; Count is the TOTAL including the original; the
copies are independent (not associative); the tool returns to Select with
the ORIGINAL selection selected.
"""
import pytest
from PyQt6.QtCore import QPointF

from tests._modify_tools_helpers import PRIMITIVES, add_primitive, grips
from tests._snap_polish_helpers import click, close_view, make_view, move


@pytest.mark.parametrize("name", list(PRIMITIVES))
def test_array_typed_count_is_total(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = grips(item)
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("array")
        assert scene.mode == "array"
        click(view, QPointF(0, 0))                          # base
        move(view, QPointF(200, 0))                         # direction +X
        assert scene.begin_dynamic_input() is True
        scene.dynamic_input.editor("Spacing").setText("200")
        scene.dynamic_input.editor("Count").setText("4")
        scene.dynamic_input._accept()
        lst = getattr(scene, attr)
        assert len(lst) == 4                                # [RED]
        for k in range(1, 4):
            assert grips(lst[k]) == pytest.approx(
                [(x + 200 * k, y) for x, y in before], abs=0.5)
        assert grips(lst[0]) == pytest.approx(before, abs=1e-6)
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
        assert lst[0] is item and item.isSelected()
        assert not any(c.isSelected() for c in lst[1:])
        assert item.opacity() == pytest.approx(1.0)        # D11 dim restored
        assert scene._move_ghost == []
        scene.undo()
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_array_count_below_two_refused(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(100, 0))
        assert scene.begin_dynamic_input() is True
        scene.dynamic_input.editor("Count").setText("1")
        scene.dynamic_input._accept()
        assert len(getattr(scene, attr)) == 1
        assert scene._undo_pos == p0
        assert scene.mode == "array"                        # HUD refused, tool live
    finally:
        close_view(view, scene)


def test_array_click_commits_cursor_spacing(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")
        p0 = scene._undo_pos
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(0, -150)); click(view, QPointF(0, -150))
        lst = getattr(scene, attr)
        assert len(lst) == scene._array_count_default       # [RED]
        assert scene._array_count_default == 3
        for k in range(1, 3):
            assert lst[k]._center.x() == pytest.approx(0.0, abs=0.5)
            assert lst[k]._center.y() == pytest.approx(-150.0 * k, abs=0.5)
        assert scene._undo_pos == p0 + 1
        assert item.isSelected()
    finally:
        close_view(view, scene)


def test_array_ghost_is_count_minus_one_translated_copies(qapp):
    """D11: the live ghost shows every copy the commit would create."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(0, -120))
        base = scene._move_ghost_base
        assert base
        n = scene._array_count_default
        assert len(scene._move_ghost) == (n - 1) * len(base)            # [RED]
        tops = sorted(round(p.boundingRect().center().y())
                      for p in scene._move_ghost)
        c0 = round(base[0].boundingRect().center().y())
        assert tops == sorted(c0 - 120 * k for k in range(1, n))
        assert item.opacity() < 1.0                                     # dimmed
        # Typed Count refreshes the ghost on Tab (field commit).
        assert scene.begin_dynamic_input() is True
        ed = scene.dynamic_input.editor("Count")
        ed.setText("5")
        scene.dynamic_input._step_focus(ed, 1)          # the Tab handler
        assert len(scene._move_ghost) == 4 * len(base)
    finally:
        close_view(view, scene)


def test_undo_mid_array_cancels_the_tool(qapp):
    """N2: an undo mid-Array ends the tool — no stale base, dim or ghost."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(100, 0))
        assert scene._move_ghost
        scene.undo()
        assert scene.mode in (None, "select")                          # [RED]
        assert scene._array_base is None
        assert scene._move_ghost == []
        for it in getattr(scene, attr):
            assert it.opacity() == pytest.approx(1.0)
    finally:
        close_view(view, scene)


def test_array_escape_creates_nothing(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "rect")
        p0 = scene._undo_pos
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(100, 0))
        QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
        assert scene.mode in (None, "select")
        assert getattr(scene, attr) == [item]
        assert scene._undo_pos == p0
        assert item.opacity() == pytest.approx(1.0)
        assert scene._move_ghost == []
    finally:
        close_view(view, scene)


def test_array_needs_a_selection(qapp):
    view, scene = make_view(scale=1.0)
    try:
        assert scene._modify_ctl.start("array") is False
        assert scene.mode != "array"
    finally:
        close_view(view, scene)


def _type(scene, **fields):
    assert scene.begin_dynamic_input() is True
    for name, text in fields.items():
        scene.dynamic_input.editor(name).setText(text)
    scene.dynamic_input._accept()


def _rects(paths):
    return sorted((round(r.x(), 1), round(r.y(), 1),
                   round(r.width(), 1), round(r.height(), 1))
                  for r in (p.boundingRect() for p in paths))


def test_typed_spacing_overrides_cursor_distance(qapp):
    """I-3a: the cursor sets the direction; a typed Spacing sets the pitch."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")           # (0,0)-(100,0)
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 0))
        _type(scene, Spacing="150", Count="3")
        lst = getattr(scene, attr)
        assert [round(l.line().p1().x()) for l in lst] == [0, 150, 300]   # [RED]
        assert all(round(l.line().p1().y()) == 0 for l in lst)
    finally:
        close_view(view, scene)


def test_array_follows_a_diagonal_aim(qapp):
    """I-3b: copies go along the base->cursor ray, not an axis."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "circle")         # centre (0,0)
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(120, -120))
        _type(scene, Spacing="100", Count="3")
        lst = getattr(scene, attr)
        d = 100 / 2 ** 0.5
        for k in (1, 2):
            assert lst[k]._center.x() == pytest.approx(d * k, abs=0.5)   # [RED]
            assert lst[k]._center.y() == pytest.approx(-d * k, abs=0.5)
    finally:
        close_view(view, scene)


def test_spacing_zero_is_refused(qapp):
    """I-3c: Spacing 0 creates nothing, pushes no undo, keeps the tool live."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(100, 0))
        _type(scene, Spacing="0", Count="3")
        assert len(getattr(scene, attr)) == 1
        assert scene._undo_pos == p0
        assert scene.mode == "array"
    finally:
        close_view(view, scene)


def test_array_in_plan_scene_copies_nodes_and_gridlines(qapp):
    """I-3d: a Node and a GridlineItem array through the shared paste path,
    one undo step; undo restores the pre-state."""
    from firepro3d.gridline import GridlineItem
    view, scene = make_view(role="plan", scale=1.0)
    try:
        node = scene.add_node(0.0, 200.0)
        gl = GridlineItem(QPointF(-300, 0), QPointF(-300, 400), label="Z9")
        scene._register_gridline(gl)
        scene.push_undo_state()
        n_nodes = len(scene.sprinkler_system.nodes)
        n_gl = len(scene._gridlines)
        scene.clearSelection(); node.setSelected(True); gl.setSelected(True)
        p0 = scene._undo_pos
        assert scene._modify_ctl.start("array") is True
        click(view, QPointF(500, -300)); move(view, QPointF(800, -300))
        _type(scene, Spacing="300", Count="4")
        assert len(scene.sprinkler_system.nodes) == n_nodes + 3        # [RED]
        assert len(scene._gridlines) == n_gl + 3
        xs = sorted(round(n.pos().x()) for n in scene.sprinkler_system.nodes)
        assert xs == [0, 300, 600, 900]
        gxs = sorted(round(g.grip_points()[0].x()) for g in scene._gridlines)
        assert gxs == [-300, 0, 300, 600]
        assert scene._undo_pos == p0 + 1
        assert node.isSelected() and gl.isSelected()
        scene.undo()
        assert len(scene.sprinkler_system.nodes) == n_nodes
        assert len(scene._gridlines) == n_gl
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("name", ["line", "rect_rotated", "spline", "text"])
def test_ghost_matches_the_committed_copies(qapp, name):
    """I-3e / D11: the ghost on screen is exactly what the click creates."""
    from firepro3d.transform_ghost import ghost_base_paths
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(90, -160))
        ghost = _rects(scene._move_ghost)
        assert ghost
        click(view, QPointF(90, -160))
        copies = getattr(scene, attr)[1:]
        assert len(copies) == scene._array_count_default - 1
        assert _rects(ghost_base_paths(copies)) == ghost                # [RED]
    finally:
        close_view(view, scene)


def test_no_aim_no_ghost(qapp):
    """I-1: before the cursor sets a direction the commit would refuse, so
    a typed Count must not ghost any copies."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0))                                      # base only
        assert scene.begin_dynamic_input() is True
        ed = scene.dynamic_input.editor("Count")
        ed.setText("4")
        scene.dynamic_input._step_focus(ed, 1)                          # Tab
        assert scene._move_ghost == []                                  # [RED]
        scene.dynamic_input._accept()
        assert len(getattr(scene, attr)) == 1                           # refused
    finally:
        close_view(view, scene)


def test_enter_commits_at_the_cursor_aim(qapp):
    """D10 click/Enter: a real Return with the HUD closed commits the
    cursor spacing with the default total."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0)); move(view, QPointF(0, -150))
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        lst = getattr(scene, attr)
        assert len(lst) == scene._array_count_default                   # [RED]
        assert [round(l.line().p1().y()) for l in lst] == [0, -150, -300]
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
    finally:
        close_view(view, scene)


def test_enter_without_aim_is_refused(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    view, scene = make_view(scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        item, attr = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("array")
        click(view, QPointF(0, 0))                                      # no aim
        QTest.keyClick(view.viewport(), Qt.Key.Key_Return)
        assert len(getattr(scene, attr)) == 1
        assert scene._undo_pos == p0
        assert scene.mode == "array"
        assert msgs and msgs[-1].startswith("Array needs a direction")  # [RED]
    finally:
        close_view(view, scene)
