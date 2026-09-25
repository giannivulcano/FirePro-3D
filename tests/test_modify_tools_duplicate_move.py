"""D6: Duplicate = Move that keeps the original; D7: Move moves Text too."""
import pytest
from PyQt6.QtCore import QPointF

from tests._modify_tools_helpers import PRIMITIVES, add_primitive, grips
from tests._snap_polish_helpers import click, close_view, make_view, move


@pytest.mark.parametrize("name", list(PRIMITIVES))
def test_duplicate_keeps_original_and_places_copy(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = grips(item); p0 = scene._undo_pos
        scene._modify_ctl.start("duplicate")
        assert scene.mode == "duplicate"
        assert item.isSelected()                             # I-2: entry keeps selection
        click(view, QPointF(0, 0))
        base = QPointF(scene.node_start_pos)
        move(view, QPointF(300, 0)); click(view, QPointF(300, 0))
        lst = getattr(scene, attr)
        assert len(lst) == 2                                 # [RED]
        assert grips(lst[0]) == before
        dx, dy = 300 - base.x(), 0 - base.y()
        assert grips(lst[1]) == pytest.approx([(x + dx, y + dy) for x, y in before], abs=0.5)
        assert scene._undo_pos == p0 + 1
        assert lst[1].isSelected() and not lst[0].isSelected()
        assert scene.mode in (None, "select")
        scene.undo()
        assert len(getattr(scene, attr)) == 1
    finally:
        close_view(view, scene)


def test_duplicate_can_snap_onto_its_original(qapp):
    """Original stays a snap target: drop the copy's p1 onto the original's p2."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")          # (0,0)-(100,0)
        scene._modify_ctl.start("duplicate")
        click(view, QPointF(0, 0)); move(view, QPointF(102, 2)); click(view, QPointF(102, 2))
        new = getattr(scene, attr)[1]
        assert grips(new)[0] == pytest.approx((100.0, 0.0), abs=0.01)   # [RED]
    finally:
        close_view(view, scene)


def test_move_still_excludes_its_own_items(qapp):
    """Move (not Duplicate): the moved line is no target for its own handles."""
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")          # (0,0)-(100,0)
        scene._modify_ctl.start("move")
        click(view, QPointF(0, 0)); move(view, QPointF(102, 2)); click(view, QPointF(102, 2))
        assert grips(item)[0] == pytest.approx((102.0, 2.0), abs=0.5)
    finally:
        close_view(view, scene)


def test_duplicate_hud_dx_dy(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        scene._modify_ctl.start("duplicate")
        click(view, QPointF(0, 0))
        move(view, QPointF(5, 5))
        assert scene.begin_dynamic_input() is True
        scene.dynamic_input.editor("dX").setText("1000")
        scene.dynamic_input.editor("dY").setText("0")
        scene.dynamic_input._accept()
        lst = getattr(scene, attr)
        assert len(lst) == 2
        assert grips(lst[0])[0] == pytest.approx((0.0, 0.0), abs=0.01)
        assert grips(lst[1])[0] == pytest.approx((1000.0, 0.0), abs=0.01)
    finally:
        close_view(view, scene)


def test_duplicate_esc_cancels(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        p0 = scene._undo_pos
        scene._modify_ctl.start("duplicate")
        click(view, QPointF(0, 0)); move(view, QPointF(300, 0))
        scene.set_mode(None)
        assert len(getattr(scene, attr)) == 1
        assert scene._undo_pos == p0
        assert scene._move_ghost == [] and scene._move_ghost_base == []
    finally:
        close_view(view, scene)


def test_move_tool_moves_text(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    view, scene = make_view(scale=1.0)
    try:
        t = TextItem(TextAnnotationData(text="T", x=0.0, y=0.0, height_mm=20.0))
        scene.addItem(t); scene._texts.append(t); scene.push_undo_state()
        t.setSelected(True)
        x0 = t.to_dict()["x"]
        scene._modify_ctl.start("move")
        click(view, QPointF(0, 0)); move(view, QPointF(50, 0)); click(view, QPointF(50, 0))
        assert t.to_dict()["x"] == pytest.approx(x0 + 50, abs=0.5)      # [RED]
    finally:
        close_view(view, scene)
