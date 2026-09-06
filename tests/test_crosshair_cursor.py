"""Guards for the accent crosshair cursor (Model_View)."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QPainter, QColor

from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d import theme as _th


def _make_view(qapp):
    scene = Model_Space()
    view = Model_View(scene)
    view.resize(400, 300)
    view.show()
    from PyQt6.QtTest import QTest
    QTest.qWaitForWindowExposed(view)
    return scene, view


def test_crosshair_enabled_blanks_cursor(qapp):
    scene, view = _make_view(qapp)
    view.set_crosshair_enabled(True)
    assert view.cursor().shape() == Qt.CursorShape.BlankCursor
    view.set_crosshair_enabled(False)
    assert view.cursor().shape() != Qt.CursorShape.BlankCursor
    view.close()


def test_crosshair_renders_accent_lines(qapp):
    scene, view = _make_view(qapp)
    view.set_crosshair_enabled(True)
    view._last_vp_pos = view.viewport().rect().center()
    img = QImage(view.viewport().size(), QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.black)
    p = QPainter(img)
    # drawForeground paints in viewport coords via resetTransform.
    view.drawForeground(p, view.mapToScene(view.viewport().rect()).boundingRect())
    p.end()
    accent = QColor(_th.detect().accent)
    cy = view._last_vp_pos.y()
    # Scan the cursor row for at least one accent-coloured pixel.
    found = any(
        QColor(img.pixel(x, cy)).getRgb()[:3] == accent.getRgb()[:3]
        for x in range(0, img.width())
    )
    assert found, "no accent crosshair pixels rendered on the cursor row"
    view.close()
