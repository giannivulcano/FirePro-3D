"""Smoke round 1, item 1: the move preview follows the cursor (real mouse gesture).

A TextItem carries a Qt ``scale()`` (reference font, ``setScale(h / cap)``). The
held preview must put the item where the cursor is on every frame, not only at
the commit.
"""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt

from firepro3d.block_editor import BlockEditorWidget
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextAnnotationData, TextItem
from tests._note_helpers import mouse


def _text(sc, x=0.0, y=0.0):
    item = TextItem(TextAnnotationData(text="abc", x=x, y=y, wrap_width_mm=30.0,
                                       box_height_mm=10.0, height_mm=3.0))
    sc.addItem(item)
    sc._texts.append(item)
    return item


@pytest.mark.parametrize("delta", [(40.0, 0.0), (0.0, 25.0)])
def test_held_preview_tracks_the_cursor_in_the_block_editor(qapp, delta):
    proj = Model_Space()
    w = BlockEditorWidget(proj)
    try:
        w.resize(1000, 700)
        w.show()
        qapp.processEvents()
        sc = w.editor_scene
        view = sc.views()[0]
        view.resetTransform()
        view.scale(4.0, 4.0)
        view.centerOn(0.0, 0.0)
        item = _text(sc)
        sc.clearSelection()
        item.setSelected(True)
        qapp.processEvents()
        start = item.sceneBoundingRect().center()
        grab = QPointF(start.x() - 8.0, start.y() + 2.0)   # the box body, off the centre grip
        rest = item.sceneTransform().map(QPointF(0.0, 0.0))
        mouse(view, QEvent.Type.MouseButtonPress, grab)
        dx, dy = delta
        for i in (1, 2, 3, 4):
            p = QPointF(grab.x() + dx * i / 4, grab.y() + dy * i / 4)
            mouse(view, QEvent.Type.MouseMove, p, buttons=Qt.MouseButton.LeftButton,
                  button=Qt.MouseButton.NoButton)
            got = item.sceneTransform().map(QPointF(0.0, 0.0))
            assert (got.x() - rest.x(), got.y() - rest.y()) == pytest.approx(
                (dx * i / 4, dy * i / 4), abs=0.5), f"frame {i}"
        end = QPointF(grab.x() + dx, grab.y() + dy)
        mouse(view, QEvent.Type.MouseButtonRelease, end, buttons=Qt.MouseButton.NoButton)
        got = item.sceneTransform().map(QPointF(0.0, 0.0))
        assert (got.x() - rest.x(), got.y() - rest.y()) == pytest.approx((dx, dy), abs=0.5)
    finally:
        w.hide()
        w.deleteLater()
        qapp.processEvents()
