from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from firepro3d.model_space import Model_Space


def test_halo_update_sets_top_candidate(qapp):
    sc = Model_Space()
    n = sc.add_node(0.0, 0.0)
    changed = sc.halo_update(QPointF(0.0, 0.0), aperture_scene=8.0, dt=QTransform())
    assert sc.halo_item() is n
    assert changed is True


def test_halo_update_early_out_when_top_unchanged(qapp):
    sc = Model_Space()
    sc.add_node(0.0, 0.0)
    sc.halo_update(QPointF(0.0, 0.0), aperture_scene=8.0, dt=QTransform())
    changed = sc.halo_update(QPointF(1.0, 1.0), aperture_scene=8.0, dt=QTransform())
    assert changed is False        # same top candidate -> early-out (no repaint)


def test_halo_suppressed_in_tool_mode(qapp):
    sc = Model_Space()
    sc.add_node(0.0, 0.0)
    sc.set_mode("wall")
    changed = sc.halo_update(QPointF(0.0, 0.0), aperture_scene=8.0, dt=QTransform())
    assert changed is False
    assert sc.halo_item() is None


from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication


def _move(view, vp_pointf):
    ev = QMouseEvent(QEvent.Type.MouseMove, vp_pointf,
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)


def test_posted_move_highlights_top_item(qapp):
    from firepro3d.model_view import Model_View
    sc = Model_Space(); view = Model_View(sc); view.resize(400, 400); view.show()
    QApplication.processEvents()
    n = sc.add_node(0.0, 0.0)
    vp = view.mapFromScene(QPointF(0.0, 0.0))     # QPoint in viewport coords
    _move(view, QPointF(vp))
    assert sc.halo_item() is n
