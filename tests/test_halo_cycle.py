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
