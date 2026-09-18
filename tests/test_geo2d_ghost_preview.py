"""tests/test_geo2d_ghost_preview.py — line/polyline ghosts match the ref style.

Bug (user smoke, 2026-09-16): the line ghost reused the shared preview_pipe
(darkGray, width 3 — the pipe style) and the polyline ghost used the item's
solid pen, so neither matched the width-1 dashed reference-line style the other
2D-geo previews use. Line now sets preview_pipe to the reference style per move
(and set_mode resets it to darkGray for pipe/set_scale); the polyline is ghosted
dashed during placement and restored solid on finalize.
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
        QApplication.sendEvent(view.viewport(), QKeyEvent(etype, key, Qt.KeyboardModifier.NoModifier))
    QApplication.processEvents()


def test_line_ghost_is_width1_dashed(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_line")
    scene._draw_line_anchor = QPointF(0, 0)
    scene._preview_from_line(QPointF(100, 0))
    pen = scene.preview_pipe.pen()
    assert pen.style() == Qt.PenStyle.DashLine
    assert pen.widthF() == 1.0


def test_preview_pipe_resets_to_pipe_style_on_mode_switch(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("draw_line")
    scene._draw_line_anchor = QPointF(0, 0)
    scene._preview_from_line(QPointF(100, 0))
    assert scene.preview_pipe.pen().widthF() == 1.0    # line style
    scene.set_mode("pipe")
    assert scene.preview_pipe.pen().widthF() == 3.0     # pipe darkGray default restored


def test_polyline_ghost_dashed_then_solid_on_finalize(shown_model_view):
    view, scene = shown_model_view
    scene.set_mode("polyline")
    _press_at(view, QPointF(0, 0))          # create the active polyline
    pl = scene._polyline_active
    assert pl is not None
    assert pl.pen().style() == Qt.PenStyle.DashLine
    assert pl.pen().widthF() == 1.0

    _press_at(view, QPointF(300, 0)); _press_at(view, QPointF(300, 300))
    _key(view, Qt.Key.Key_Return)           # finalize
    finalized = scene._polylines[-1]
    assert finalized.pen().style() == Qt.PenStyle.SolidLine
