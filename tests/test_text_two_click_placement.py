"""tests/test_text_two_click_placement.py — model-space text box uses the dragged size.

Bug (user, 2026-09-16): a model-space text block was placed with auto (one-line)
height regardless of the two-click drag — it read as a "zero height" single-click
placement.  The commit now captures the dragged box HEIGHT (clamped to the
content height), mirroring rectangle placement.

Driven through the real posted-event path.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication


def _press_at(view, scene_pt: QPointF) -> None:
    vp = view.mapFromScene(scene_pt)
    for etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(etype, QPointF(vp), Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(view.viewport(), ev)
    QApplication.processEvents()


def test_two_click_text_captures_dragged_height(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"   # containment C1: loose text authoring
    scene.set_mode("text")
    _press_at(view, QPointF(0, 0))          # anchor
    _press_at(view, QPointF(400, 300))      # opposite corner → 400 x 300 box
    # Containment C5: model text is now a TextItem in scene._texts backed by
    # TextAnnotationData (box height = data.box_height_mm), not a NoteAnnotation.
    note = scene._texts[-1]
    # The box height reflects the drag (not the auto one-line height).
    assert note.data.box_height_mm >= 250, f"box height not captured: {note.data.box_height_mm}"
    # And it is the stored box, not auto (0).
    assert note.data.box_height_mm > 0


def test_taller_drag_gives_taller_box(shown_model_view):
    view, scene = shown_model_view
    scene.scene_role = "block_editor"   # containment C1: loose text authoring
    scene.set_mode("text")
    _press_at(view, QPointF(0, 0)); _press_at(view, QPointF(400, 150))
    short = scene._texts[-1].data.box_height_mm
    scene.set_mode("text")
    _press_at(view, QPointF(0, 2000)); _press_at(view, QPointF(400, 2600))
    tall = scene._texts[-1].data.box_height_mm
    assert tall > short + 100
