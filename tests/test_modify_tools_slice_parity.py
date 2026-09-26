"""Slice 1 parity: Move relocated into ModifyToolsController (behaviour home)."""
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import click, close_view, make_view, move


def test_controller_is_composed(qapp):
    view, scene = make_view(scale=1.0)
    try:
        from firepro3d.modify_tools_controller import ModifyToolsController
        assert isinstance(scene._modify_ctl, ModifyToolsController)
    finally:
        close_view(view, scene)


def test_move_tool_moves_a_line_by_two_clicks(qapp):
    view, scene = make_view(scale=1.0)
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(a); scene._draw_lines.append(a)
        scene.push_undo_state(); p0 = scene._undo_pos
        a.setSelected(True)
        scene.set_mode("move")
        click(view, QPointF(0, 0))
        move(view, QPointF(50, -300))
        click(view, QPointF(50, -300))
        pts = a.grip_points()
        assert abs(pts[0].x() - 50) < 0.01 and abs(pts[0].y() + 300) < 0.01
        assert scene._undo_pos == p0 + 1
    finally:
        close_view(view, scene)


def test_clear_drops_move_ghost(qapp):
    view, scene = make_view(scale=1.0)
    try:
        scene._move_ghost = ["x"]; scene._move_ghost_base = ["x"]
        scene._modify_ctl.clear("select")
        assert scene._move_ghost == [] and scene._move_ghost_base == []
    finally:
        close_view(view, scene)
