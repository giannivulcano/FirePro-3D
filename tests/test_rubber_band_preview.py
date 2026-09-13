from PyQt6.QtCore import QRectF, QPointF, QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


def test_rubber_band_hits_matches_commit(qapp):
    """The extracted query returns the same resolved items the commit selects.

    Uses the transform-free (dt=None) marker-inflation coords proven in
    test_rubber_band_select.py: a window at (4800,4800,600,600) fully contains
    the inflated marker shape of a node placed at (5000,5000).
    """
    sc = Model_Space()
    inside = sc.add_node(5000.0, 5000.0)
    hits = sc.rubber_band_hits(QRectF(4800, 4800, 600, 600),
                               crossing=False, dt=None)
    assert inside in hits
    # Parity with commit_rubber_band: committing selects exactly the hits.
    sc.commit_rubber_band(QRectF(4800, 4800, 600, 600),
                          crossing=False, additive=False)
    assert inside.isSelected()


def _mk(qapp):
    sc = Model_Space()
    view = Model_View(sc)
    view.resize(600, 600)
    view.show()
    QApplication.processEvents()
    sc.set_mode(None)
    return sc, view


def test_preview_populates_during_drag_and_clears_on_release(qapp):
    sc, v = _mk(qapp)
    n = sc.add_node(0.0, 0.0)
    # Empty top-left start, drag to bottom-right enclosing the origin marker
    # (same working coords as test_ltr_drag_is_window in test_rubber_band_select).
    p1 = QPointF(50, 50)
    p2 = QPointF(550, 550)
    press = QMouseEvent(QEvent.Type.MouseButtonPress, p1, Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    move = QMouseEvent(QEvent.Type.MouseMove, p2, Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    rel = QMouseEvent(QEvent.Type.MouseButtonRelease, p2, Qt.MouseButton.LeftButton,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(v.viewport(), press)
    QApplication.sendEvent(v.viewport(), move)
    assert n in sc._band_preview            # previewed mid-drag
    QApplication.sendEvent(v.viewport(), rel)
    assert sc._band_preview == []           # cleared on release
    assert n.isSelected()                   # and committed


def test_preview_clears_on_escape_cancel(qapp):
    sc, v = _mk(qapp)
    n = sc.add_node(0.0, 0.0)
    p1 = QPointF(50, 50)
    p2 = QPointF(550, 550)
    press = QMouseEvent(QEvent.Type.MouseButtonPress, p1, Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    move = QMouseEvent(QEvent.Type.MouseMove, p2, Qt.MouseButton.LeftButton,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(v.viewport(), press)
    QApplication.sendEvent(v.viewport(), move)
    assert n in sc._band_preview
    # Escape ladder's band-cancel rung must also clear the preview.
    sc._escape_ladder()
    assert sc._band_preview == []
