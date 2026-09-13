from PyQt6.QtCore import QPointF, QEvent, Qt
from PyQt6.QtGui import QKeyEvent, QTransform
from PyQt6.QtWidgets import QApplication
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.node import Node


def _esc(target):
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, ev)


def test_escape_clears_selection_in_select_mode(qapp):
    sc = Model_Space()
    view = Model_View(sc)
    view.resize(300, 300)
    view.show()
    QApplication.processEvents()
    # "select" mode is exempt from set_mode's auto-deselect, so the ONLY thing
    # that can clear this selection on Escape is the ladder's clearSelection
    # branch. The ladder returns early (event.accept/return) when it consumes,
    # so the fall-through set_mode(None) never runs -> mode stays "select".
    sc.set_mode("select")
    n = sc.add_node(0.0, 0.0)
    n.setSelected(True)
    sc.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                               Qt.KeyboardModifier.NoModifier))
    assert not n.isSelected()
    # Ladder consumed the key and returned before the fall-through set_mode(None).
    assert sc.mode == "select"


def test_escape_resets_halo_cycle_before_clearing_selection(qapp):
    sc = Model_Space()
    a = Node(0.0, 0.0)
    b = Node(0.0, 0.0)
    sc.addItem(a)
    sc.addItem(b)
    sc.set_mode(None)
    sc.halo_update(QPointF(0, 0), 8.0, QTransform())
    sc._halo_index = 1
    # HALO active + nothing selected: escape clears the HALO cycle first, no
    # selection change needed.
    consumed = sc._escape_ladder()
    assert consumed is True
    assert sc.halo_item() is None and sc._halo_candidates == []
