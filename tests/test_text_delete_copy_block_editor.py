"""Guard -- Delete / copy of a selected TextItem (Block Editor + plan).

``TextItem.data`` is a ``TextAnnotationData`` property that shadows
``QGraphicsItem.data()``; ``delete_items`` / ``copy_selected_items`` filtered the
capability frame with ``item.data(0)`` and raised ``TypeError`` for any text.
"""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._snap_polish_helpers import click, close_view, make_view


def _scene_with_selected_text(role):
    from firepro3d.text_item import TextAnnotationData, TextItem

    view, scene = make_view(role=role, mode="select")
    t = TextItem(TextAnnotationData(text="HELLO", x=1000.0, y=1000.0,
                                    wrap_width_mm=500.0, height_mm=100.0))
    scene.addItem(t)
    scene._texts.append(t)
    t.setSelected(True)
    QApplication.processEvents()
    return view, scene, t


@pytest.mark.parametrize("role", ["block_editor", "plan"])
def test_delete_key_removes_selected_text(qapp, role):
    view, scene, t = _scene_with_selected_text(role)
    try:
        view.setFocus()
        QTest.keyClick(view.viewport(), Qt.Key.Key_Delete)
        QApplication.processEvents()
        assert t.scene() is None
        assert t not in scene._texts
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("role", ["block_editor", "plan"])
def test_delete_items_api_removes_text(qapp, role):
    view, scene, t = _scene_with_selected_text(role)
    try:
        scene.delete_selected_items()
        assert t.scene() is None
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("role", ["block_editor", "plan"])
def test_copy_selected_text_does_not_raise(qapp, role):
    view, scene, t = _scene_with_selected_text(role)
    try:
        scene.copy_selected_items()
        assert t.scene() is scene           # copy leaves the source in place
    finally:
        close_view(view, scene)
