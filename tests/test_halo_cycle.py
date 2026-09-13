from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from firepro3d.model_space import Model_Space
from firepro3d.node import Node


def _two_coincident_nodes(sc):
    a = Node(0.0, 0.0)
    b = Node(0.0, 0.0)
    sc.addItem(a)
    sc.addItem(b)
    return a, b


def test_spacebar_cycles_halo_candidates(qapp):
    sc = Model_Space()
    a, b = _two_coincident_nodes(sc)
    sc.halo_update(QPointF(0.0, 0.0), 8.0, QTransform())
    assert len(sc._halo_candidates) == 2
    first = sc.halo_item()
    assert sc.cycle_placement_ambiguity() is True
    assert sc.halo_item() is not first
    assert sc.halo_item() in (a, b)


def test_cycle_similar_selection_is_gone(qapp):
    sc = Model_Space()
    assert not hasattr(sc, "_cycle_similar_selection")


def test_single_candidate_does_not_cycle(qapp):
    sc = Model_Space()
    sc.add_node(0.0, 0.0)
    sc.halo_update(QPointF(0.0, 0.0), 8.0, QTransform())
    assert sc.cycle_placement_ambiguity() is False  # <2 candidates


# ── A8: left-click commits the HALO-highlighted (cycled) candidate ──────────
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication
from firepro3d.model_view import Model_View


def _click(view, vp_pointf, ctrl=False):
    mods = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
    for t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(t, vp_pointf, Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, mods)
        QApplication.sendEvent(view.viewport(), ev)


def test_click_commits_cycled_candidate(qapp):
    sc = Model_Space(); view = Model_View(sc); view.resize(400, 400); view.show()
    QApplication.processEvents()
    a = Node(0.0, 0.0); b = Node(0.0, 0.0); sc.addItem(a); sc.addItem(b)
    sc.set_mode(None)   # resting select mode routes to _press_select_item
    sc.halo_update(QPointF(0.0, 0.0), 8.0, view.viewportTransform())
    assert len(sc._halo_candidates) == 2
    # The press path's item_under is the TOPMOST scene item, which (for these
    # two coincident nodes) is _halo_candidates[1] — the reverse of the halo
    # ranking.  Cycling the halo to candidate[0] therefore targets the item the
    # Qt-native/topmost pick would MISS, so the assertion actually discriminates
    # the halo_item() preference from the plain item_under pick.
    target = sc._halo_candidates[0]
    sc._halo_index = 0                       # halo highlights the non-topmost
    vp = QPointF(view.mapFromScene(QPointF(0.0, 0.0)))
    _click(view, vp)
    assert target.isSelected()
    assert not sc._halo_candidates[1].isSelected()
