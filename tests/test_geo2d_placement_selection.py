"""tests/test_geo2d_placement_selection.py — placement selection contract.

Contract (user, 2026-09-16): every 2D-geometry primitive is selected on
placement commit, and placing several in a row leaves ONLY the last-placed item
selected — selection must NOT accumulate.

Driven through the REAL entry point (posted ``QMouseEvent`` / ``QKeyEvent`` on a
shown+activated view), never by calling private handlers, so the fix is proven on
the same seam the user exercises.  ``QTest.mouseMove`` is inert here.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication


def _press_at(view, scene_pt: QPointF) -> None:
    """Post a real left-button click (press+release) at *scene_pt* through *view*."""
    vp = view.mapFromScene(scene_pt)
    for etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(
            etype,
            QPointF(vp),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def _key(view, key: Qt.Key) -> None:
    for etype in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        ev = QKeyEvent(etype, key, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def _assert_only_last_selected(scene, type_list_attr: str) -> None:
    """After two placements, exactly the last-placed item of that list is selected."""
    placed = getattr(scene, type_list_attr)
    assert len(placed) == 2, f"expected 2 placed in {type_list_attr}, got {len(placed)}"
    sel = scene.selectedItems()
    assert len(sel) == 1, f"expected 1 selected, got {len(sel)} ({type_list_attr})"
    assert sel[0] is placed[-1], "the LAST-placed item must be the selected one"
    assert not placed[0].isSelected(), "the first-placed item must be deselected"


def test_circle_placement_no_accumulation(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_circle")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0))
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0))
    _assert_only_last_selected(scene, "_draw_circles")


def test_line_placement_no_accumulation(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_line")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(600, 0))
    _press_at(view, QPointF(0, 2000)); _press_at(view, QPointF(600, 2000))
    _assert_only_last_selected(scene, "_draw_lines")


def test_rectangle_placement_no_accumulation(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_rectangle")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 200)); _press_at(view, QPointF(400, 200))
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 200)); _press_at(view, QPointF(2400, 200))
    _assert_only_last_selected(scene, "_draw_rects")


def test_polyline_placement_no_accumulation(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("polyline")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(300, 0)); _press_at(view, QPointF(300, 300))
    _key(view, Qt.Key.Key_Return)
    _press_at(view, QPointF(0, 2000)); _press_at(view, QPointF(300, 2000)); _press_at(view, QPointF(300, 2300))
    _key(view, Qt.Key.Key_Return)
    _assert_only_last_selected(scene, "_polylines")


def test_arc_placement_no_accumulation(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_arc")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0)); _press_at(view, QPointF(0, 400))
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0)); _press_at(view, QPointF(2000, 400))
    _assert_only_last_selected(scene, "_draw_arcs")


def test_polygon_placement_no_accumulation(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("polygon")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0)); _press_at(view, QPointF(400, 100))
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0)); _press_at(view, QPointF(2400, 100))
    _assert_only_last_selected(scene, "_draw_polygons")


# ── regression guards: ellipse + spline already clear; keep them single-select ──


def test_ellipse_placement_no_accumulation(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_ellipse")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 0)); _press_at(view, QPointF(0, 200))
    _press_at(view, QPointF(2000, 0)); _press_at(view, QPointF(2400, 0)); _press_at(view, QPointF(2000, 200))
    _assert_only_last_selected(scene, "_draw_ellipses")


def test_spline_placement_no_accumulation(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_spline")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(300, 0)); _press_at(view, QPointF(300, 300))
    _key(view, Qt.Key.Key_Return)
    _press_at(view, QPointF(0, 2000)); _press_at(view, QPointF(300, 2000)); _press_at(view, QPointF(300, 2300))
    _key(view, Qt.Key.Key_Return)
    _assert_only_last_selected(scene, "_draw_splines")
