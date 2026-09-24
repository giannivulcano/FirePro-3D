"""tests/test_geo2d_placement_selection.py — placement selection + single-placement.

Contract (user, 2026-09-16):
  * every 2D-geometry primitive is selected on placement commit, and only the
    last-placed item stays selected (no accumulation);
  * placement is SINGLE-placement — after committing one item the tool returns to
    Select mode with the item selected (so its manipulator frame shows), instead
    of re-arming for another.

Driven through the REAL entry point (posted ``QMouseEvent`` / ``QKeyEvent`` on a
shown+activated view).  Because placement returns to Select, each subsequent
placement re-enters the tool mode first.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _block_editor_role(shown_model_view):
    """Containment C1: authors loose geometry; flip the shared scene to
    Block-Editor role (role only gates ``authoring_allowed``)."""
    _view, scene = shown_model_view
    scene.scene_role = "block_editor"


def _press_at(view, scene_pt: QPointF) -> None:
    vp = view.mapFromScene(scene_pt)
    for etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(etype, QPointF(vp), Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def _key(view, key: Qt.Key) -> None:
    for etype in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        ev = QKeyEvent(etype, key, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def _assert_last_selected_and_in_select(scene, type_list_attr: str) -> None:
    """After placement: only the last-placed item selected AND back in Select."""
    placed = getattr(scene, type_list_attr)
    assert len(placed) == 2, f"expected 2 placed in {type_list_attr}, got {len(placed)}"
    sel = scene.selectedItems()
    assert len(sel) == 1, f"expected 1 selected, got {len(sel)} ({type_list_attr})"
    assert sel[0] is placed[-1], "the LAST-placed item must be the selected one"
    assert not placed[0].isSelected(), "the first-placed item must be deselected"
    assert scene.mode == "select", "single-placement must return to Select mode"


def test_circle_single_placement(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_circle")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0))
    scene.set_mode("draw_circle")
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0))
    _assert_last_selected_and_in_select(scene, "_draw_circles")


def test_line_single_placement(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_line")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(600, 0))
    scene.set_mode("draw_line")
    _press_at(view, QPointF(0, 2000)); _press_at(view, QPointF(600, 2000))
    _assert_last_selected_and_in_select(scene, "_draw_lines")


def test_rectangle_single_placement(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_rectangle")
    # 3-click: base → side end → depth (2d-geometry.md §4).
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0)); _press_at(view, QPointF(400, 200))
    scene.set_mode("draw_rectangle")
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0)); _press_at(view, QPointF(2400, 200))
    _assert_last_selected_and_in_select(scene, "_draw_rects")


def test_polyline_single_placement(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("polyline")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(300, 0)); _press_at(view, QPointF(300, 300))
    _key(view, Qt.Key.Key_Return)
    scene.set_mode("polyline")
    _press_at(view, QPointF(0, 2000)); _press_at(view, QPointF(300, 2000)); _press_at(view, QPointF(300, 2300))
    _key(view, Qt.Key.Key_Return)
    _assert_last_selected_and_in_select(scene, "_polylines")


def test_arc_single_placement(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_arc")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0)); _press_at(view, QPointF(0, 400))
    scene.set_mode("draw_arc")
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0)); _press_at(view, QPointF(2000, 400))
    _assert_last_selected_and_in_select(scene, "_draw_arcs")


def test_polygon_single_placement(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("polygon")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0)); _press_at(view, QPointF(400, 100))
    scene.set_mode("polygon")
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0)); _press_at(view, QPointF(2400, 100))
    _assert_last_selected_and_in_select(scene, "_draw_polygons")


def test_ellipse_single_placement(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_ellipse")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0)); _press_at(view, QPointF(0, 200))
    scene.set_mode("draw_ellipse")
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0)); _press_at(view, QPointF(2000, 200))
    _assert_last_selected_and_in_select(scene, "_draw_ellipses")


def test_spline_single_placement(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_spline")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(300, 0)); _press_at(view, QPointF(300, 300))
    _key(view, Qt.Key.Key_Return)
    scene.set_mode("draw_spline")
    _press_at(view, QPointF(0, 2000)); _press_at(view, QPointF(300, 2000)); _press_at(view, QPointF(300, 2300))
    _key(view, Qt.Key.Key_Return)
    _assert_last_selected_and_in_select(scene, "_draw_splines")
