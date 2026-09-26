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
