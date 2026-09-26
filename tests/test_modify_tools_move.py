"""D3/D7: Move translates every primitive, one undo, originals stay selected."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from tests._modify_tools_helpers import PRIMITIVES, add_primitive, grips
from tests._snap_polish_helpers import click, close_view, make_view, move


def _esc(view):
    """The real Escape path: a key event to the view -> scene keyPressEvent."""
    QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)


@pytest.mark.parametrize("name", list(PRIMITIVES))
def test_move_every_primitive(qapp, name):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, name)
        before = grips(item)
        p0 = scene._undo_pos
        scene._modify_ctl.start("move")
        click(view, QPointF(0, 0))
        base = QPointF(scene.node_start_pos)
        move(view, QPointF(300, 0)); click(view, QPointF(300, 0))
        dx, dy = 300 - base.x(), -base.y()
        assert grips(item) == pytest.approx([(x + dx, y + dy) for x, y in before], abs=0.5)
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
        assert item.isSelected()                    # D3: originals selected [RED]
        assert scene.selectedItems() == [item]
        scene.undo()
        assert grips(getattr(scene, attr)[0]) == pytest.approx(before, abs=0.01)
    finally:
        close_view(view, scene)


def test_move_hud_dx_dy_keeps_selection(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "rect")
        before = grips(item)
        p0 = scene._undo_pos
        scene._modify_ctl.start("move")
        click(view, QPointF(0, 0))
        move(view, QPointF(5, 5))
        assert scene.begin_dynamic_input() is True
        scene.dynamic_input.editor("dX").setText("1000")
        scene.dynamic_input.editor("dY").setText("0")
        scene.dynamic_input._accept()
        assert grips(item) == pytest.approx([(x + 1000, y) for x, y in before], abs=0.01)
        assert scene._undo_pos == p0 + 1
        assert scene.mode in (None, "select")
        assert item.isSelected()                    # D3 on the HUD path [RED]
    finally:
        close_view(view, scene)


def test_move_real_esc_changes_nothing(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, attr = add_primitive(scene, "line")
        before = grips(item)
        p0 = scene._undo_pos
        scene._modify_ctl.start("move")
        click(view, QPointF(0, 0)); move(view, QPointF(200, 50))
        _esc(view)                                  # real Esc path
        assert scene.mode in (None, "select")
        assert len(getattr(scene, attr)) == 1
        assert grips(getattr(scene, attr)[0]) == before
        assert scene._undo_pos == p0
        assert item.opacity() == pytest.approx(1.0)
    finally:
        close_view(view, scene)
