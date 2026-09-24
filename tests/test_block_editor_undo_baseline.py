"""Block Editor: seeded geometry is the undo baseline (user smoke 2026-09-24).

Opening an editor on an existing block / selection seeds primitives without
resetting the undo stack, so the stack stayed [empty-construction-state]. The
first edit pushed [empty, edited] and Ctrl+Z restored the EMPTY state — the
whole block vanished. Mirrors the default-grid fix in main.py (seed = index 0,
cannot be undone away).
"""
from PyQt6.QtCore import QPointF

from firepro3d.block_editor import BlockEditorWidget
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _seeded_editor(n=3):
    w = BlockEditorWidget(Model_Space())
    dicts = [LineItem(QPointF(i * 10, 0), QPointF(i * 10 + 5, 0)).to_dict()
             for i in range(n)]
    w.seed_from_dicts(dicts)
    return w


def test_undo_after_first_edit_restores_the_seeded_block(qapp):
    w = _seeded_editor(3)
    sc = w.editor_scene
    victim = w.gather_primitives()[0]
    sc.select_items([victim])
    sc.delete_selected_items()                     # a real edit (pushes undo)
    assert len(w.gather_primitives()) == 2
    sc.undo()
    assert len(w.gather_primitives()) == 3         # seeded block, not empty


def test_seeded_state_cannot_be_undone_away(qapp):
    w = _seeded_editor(3)
    sc = w.editor_scene
    assert not sc.can_undo()                       # the seed is the baseline
    sc.undo()
    assert len(w.gather_primitives()) == 3


def test_seeding_leaves_the_editor_clean(qapp):
    w = _seeded_editor(2)
    assert not w.is_dirty()
