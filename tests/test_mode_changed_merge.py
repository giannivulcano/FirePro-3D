"""FIX 1: single merged _on_mode_changed keeps drag mode + crosshair-aware cursor.

There must be exactly one _on_mode_changed. It sets drag mode (select/None ->
NoDrag, stretch -> RubberBandDrag, else NoDrag) AND routes the cursor through
_resolve_cursor so the accent crosshair (BlankCursor) is honored on mode change.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsView
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


def test_select_mode_is_nodrag(qapp):
    sc = Model_Space()
    view = Model_View(sc)
    sc.set_mode("select")
    assert view.dragMode() == QGraphicsView.DragMode.NoDrag


def test_stretch_mode_is_rubberband(qapp):
    sc = Model_Space()
    view = Model_View(sc)
    sc.set_mode("stretch")
    assert view.dragMode() == QGraphicsView.DragMode.RubberBandDrag


def test_drawing_mode_cursor_routes_through_resolve(qapp):
    sc = Model_Space()
    view = Model_View(sc)
    # crosshair on -> _resolve_cursor returns BlankCursor for any drawing mode
    view.set_crosshair_enabled(True)
    sc.set_mode("draw_line")
    assert view.cursor().shape() == Qt.CursorShape.BlankCursor
    # crosshair off -> the mode's mapped cursor (CrossCursor for draw_line)
    view.set_crosshair_enabled(False)
    sc.set_mode("draw_line")
    assert view.cursor().shape() == Qt.CursorShape.CrossCursor
