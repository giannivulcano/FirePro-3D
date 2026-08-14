import json
import math
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QApplication
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.gridline import GridlineItem


@pytest.fixture
def ms_view(qapp):
    ms = Model_Space()
    view = Model_View(ms); view.resize(600, 600); view.resetTransform()
    view.centerOn(0, 0)
    QApplication.processEvents()
    yield ms, view
    view.hide()


def test_scene_has_move_ghost_attr(ms_view):
    ms, view = ms_view
    assert ms._move_ghost == []
    assert ms._inference_exclude_ids == set()


def test_drawforeground_survives_move_ghost(ms_view):
    ms, view = ms_view
    p = QPainterPath(); p.moveTo(0, 0); p.lineTo(0, 5000)
    ms._move_ghost = [p]
    view.viewport().repaint()  # Model_View.drawForeground runs block 8; must not raise
    # sanity: the override is the one in play
    assert isinstance(view, Model_View)


def test_clipboard_ghost_paths_gridline(ms_view):
    ms, view = ms_view
    data = [{"type": "gridline", "origin": [0, 0], "length": 5000.0,
             "angle": 90.0, "bubble1_offset": 1000.0, "bubble2_offset": 1000.0,
             "label": "1"}]
    paths = ms._clipboard_ghost_paths(data)
    assert len(paths) >= 1
    br = paths[0].boundingRect()
    # line from (0,0) to (0,-5000): x spans ~0, y spans 0..-5000
    assert math.isclose(br.left(), 0.0, abs_tol=1.0)
    assert math.isclose(br.right(), 0.0, abs_tol=1.0)
    assert math.isclose(br.top(), -5000.0, abs_tol=1.0)
    assert math.isclose(br.bottom(), 0.0, abs_tol=1.0)


def test_move_ghost_base_from_selected_items(ms_view):
    ms, view = ms_view
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    ms.addItem(gl); ms._gridlines.append(gl); gl.setSelected(True)
    ms._selected_items = [gl]
    base = ms._build_move_ghost_base(is_paste=False)
    assert len(base) >= 1


def test_clipboard_ghost_paths_node_with_pipes(ms_view):
    ms, view = ms_view
    data = [{"type": "node", "x": 100.0, "y": 200.0,
             "pipes": [{"x": 500.0, "y": 200.0}]}]
    paths = ms._clipboard_ghost_paths(data)
    assert len(paths) >= 1
    br = paths[0].boundingRect()
    # cross centered at (100,200) + a pipe seg to (500,200): x spans ~ (100-120) .. 500
    assert br.right() >= 499.0        # pipe reaches x=500
    assert math.isclose(br.top(), 200.0 - 120.0, abs_tol=1.0)   # cross half-size above centre


def test_clipboard_ghost_paths_empty(ms_view):
    ms, view = ms_view
    assert ms._clipboard_ghost_paths(None) == []
    assert ms._clipboard_ghost_paths([]) == []


def test_move_ghost_follows_cursor(ms_view):
    ms, view = ms_view
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    ms.addItem(gl); ms._gridlines.append(gl); gl.setSelected(True)
    ms._selected_items = [gl]
    ms.set_mode("move")
    # First click sets the base point + captures base paths
    ms._press_paste_move(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    assert ms.node_start_pos == QPointF(0, 0)
    assert len(ms._move_ghost_base) >= 1
    # Cursor move builds the translated ghost
    ms._move_paste_move(None, QPointF(2000, 0))
    assert len(ms._move_ghost) >= 1
    el = ms._move_ghost[0].elementAt(0)
    assert math.isclose(el.x, 2000.0, abs_tol=1.0)


def test_move_ghost_cleared_on_mode_exit(ms_view):
    ms, view = ms_view
    ms._move_ghost = [QPainterPath()]
    ms.set_mode("select")
    assert ms._move_ghost == []
