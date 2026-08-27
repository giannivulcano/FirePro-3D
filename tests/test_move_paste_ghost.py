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


def test_move_ghost_status_readout(ms_view):
    ms, view = ms_view
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    ms.addItem(gl); ms._gridlines.append(gl); gl.setSelected(True)
    ms._selected_items = [gl]
    ms.set_mode("move")
    ms._press_paste_move(None, QPointF(0, 0), QPointF(0, 0), None, None, None)
    # Capture the status messages emitted during the ghost drag.
    captured = []
    ms._show_status = lambda msg, timeout=5000: captured.append(msg)
    # Move: dx=+2000 (scene x), dy=-1500 (scene y down -> display Y-up flips sign)
    ms._move_paste_move(None, QPointF(2000, 1500))
    assert captured, "expected a status readout during paste/move ghost drag"
    last = captured[-1]
    assert "dx=2000.0" in last
    assert "dy=-1500.0" in last          # display Y-up: -offset.y()
    assert f"dist={math.hypot(2000.0, 1500.0):.1f}" in last


def test_move_ghost_cleared_on_mode_exit(ms_view):
    ms, view = ms_view
    ms._move_ghost = [QPainterPath()]
    ms.set_mode("select")
    assert ms._move_ghost == []


# NOTE: two tests removed here in Task 6 — ``test_paste_activates_inference``
# and ``test_move_excludes_moving_gridline_from_refs`` — asserted the RETIRED
# auto-proximity alignment behavior (cursor auto-snaps X to a nearby gridline
# during paste; move self-excludes the mover from the reference set via
# ``_align_exclude_ids``/``_collect_alignment_refs``).  That whole path is
# removed by design (replaced by the ALIGN acquire model); the paste/move GHOST
# rendering + geometry tests above/below still cover the live behavior.


# ── GridlineItem is movable by the generic move (bug: it wasn't) ───────────
#
# move_items moves a Node via moveBy and everything else via translate.
# GridlineItem was the one selectable geometry with neither, so it was
# silently skipped — its ghost previewed a move the commit never performed.
# translate() conforms it to the same interface; these pin the commit, not
# just the preview the ghost tests already cover.


def test_gridline_translate_shifts_origin(qapp):
    gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="1")
    ox, oy = gl.grip_points()[0].x(), gl.grip_points()[0].y()
    fx, fy = gl.grip_points()[1].x(), gl.grip_points()[1].y()
    gl.translate(300, -200)
    # Rigid shift: both endpoints move by the same vector.
    assert gl.grip_points()[0].x() == pytest.approx(ox + 300)
    assert gl.grip_points()[0].y() == pytest.approx(oy - 200)
    assert gl.grip_points()[1].x() == pytest.approx(fx + 300)
    assert gl.grip_points()[1].y() == pytest.approx(fy - 200)


def test_gridline_translate_respects_lock(qapp):
    gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="1")
    gl._locked = True
    gl.translate(300, -200)
    assert gl.grip_points()[0].x() == pytest.approx(1000.0)   # unchanged


def test_move_items_moves_a_selected_gridline(ms_view):
    """The real regression: the generic move commit now moves a gridline."""
    ms, view = ms_view
    gl = GridlineItem(QPointF(1000, 0), QPointF(1000, 5000), label="1")
    ms.addItem(gl); ms._gridlines.append(gl); gl.setSelected(True)
    ms._selected_items = [gl]
    ms.set_mode("move")
    ms.move_items(QPointF(300, -200))
    assert gl.grip_points()[0].x() == pytest.approx(1300.0)
    assert gl.grip_points()[0].y() == pytest.approx(-200.0)


def test_move_ghost_base_built_when_base_click_hits_a_grip(qapp):
    """Regression: clicking the base point ON the moved item (a grip hit) took an
    early-return shortcut that set the base point but never built the ghost — so
    the common case (click the thing you're moving) showed no ghost."""
    from PyQt6.QtCore import Qt, QEvent
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtTest import QTest
    ms = Model_Space(); ms.setSceneRect(-500, -500, 1000, 1000)
    view = Model_View(ms); view.resize(600, 600); view.show(); view.resetTransform()
    QTest.qWaitForWindowExposed(view)
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    ms.addItem(gl); ms._gridlines.append(gl); gl.setSelected(True)
    ms._selected_items = ms.selectedItems()
    ms.set_mode("move")
    # Base click exactly on the gridline's origin grip.
    vp = QPointF(view.mapFromScene(QPointF(0, 0)))
    g = QPointF(view.viewport().mapToGlobal(vp.toPoint()))
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, vp, g,
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(view.viewport(), ev)
    qapp.processEvents()
    assert ms.node_start_pos is not None                 # base point set (via grip)
    assert len(ms._move_ghost_base) >= 1, "grip base-click must still build the ghost"
    view.hide()
