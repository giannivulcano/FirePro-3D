"""FIX 3 (spec §3.3): HALO status-bar stack readout.

The scene emits a preselection readout ("<Type> — <i> of <N>", with the item
name appended when present) via ``instructionChanged`` whenever the HALO
highlight changes on hover or is advanced by a spacebar cycle. No readout is
emitted (an empty string clears the line) when there are no candidates.
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from firepro3d.model_space import Model_Space
from firepro3d.node import Node


def _spy(sc):
    seen = []
    sc.instructionChanged.connect(seen.append)
    return seen


def test_hover_emits_stack_readout(qapp):
    sc = Model_Space()
    a = Node(0.0, 0.0)
    b = Node(0.0, 0.0)
    sc.addItem(a)
    sc.addItem(b)
    seen = _spy(sc)
    changed = sc.halo_update(QPointF(0.0, 0.0), 8.0, QTransform())
    assert changed is True
    assert len(sc._halo_candidates) == 2
    # readout names the type + 1-based index of N
    assert seen, "expected a readout on hover with candidates"
    assert seen[-1] == "Node — 1 of 2"


def test_cycle_emits_updated_readout(qapp):
    sc = Model_Space()
    sc.addItem(Node(0.0, 0.0))
    sc.addItem(Node(0.0, 0.0))
    sc.halo_update(QPointF(0.0, 0.0), 8.0, QTransform())
    seen = _spy(sc)
    assert sc.cycle_placement_ambiguity() is True
    assert seen[-1] == "Node — 2 of 2"


def test_no_candidates_clears_readout(qapp):
    sc = Model_Space()
    sc.addItem(Node(0.0, 0.0))
    sc.halo_update(QPointF(0.0, 0.0), 8.0, QTransform())
    seen = _spy(sc)
    # move far away -> no candidates -> readout cleared (empty string)
    sc.halo_update(QPointF(9999.0, 9999.0), 8.0, QTransform())
    assert seen[-1] == ""


def test_readout_appends_name_when_present(qapp):
    sc = Model_Space()
    a = Node(0.0, 0.0)
    b = Node(0.0, 0.0)
    a.name = "N1"
    sc.addItem(a)
    sc.addItem(b)
    seen = _spy(sc)
    sc.halo_update(QPointF(0.0, 0.0), 8.0, QTransform())
    # top candidate is deterministic by rank; whichever it is, if it has a
    # name the readout includes it.
    top = sc.halo_item()
    if getattr(top, "name", None):
        assert top.name in seen[-1]
