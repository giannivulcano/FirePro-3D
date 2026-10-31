"""Guards for the Block Editor select-all / rotate perf bug (2026-10-31).

G1: a modify-tool commit emits a constant number of selectionChanged,
independent of the selection size (was one per reselected item -> O(n^2)
across the listeners). G2/G4: one property-panel show builds each target's
get_properties() once and scans each capability folder once.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _editor_scene():
    from firepro3d.block_editor import BlockEditorWidget
    w = BlockEditorWidget(Model_Space())
    return w, w.editor_scene


def _lines(sc, n):
    out = []
    for i in range(n):
        it = LineItem(QPointF(i * 10.0, 0.0), QPointF(i * 10.0, 100.0))
        sc.addItem(it)
        sc._draw_lines.append(it)
        out.append(it)
    return out


def _arm(sc, tool, items):
    """Select *items* and arm *tool* the way the Step 1 probe recorded."""
    sc.select_items(items)
    sc._selected_items = list(items)
    sc._rotate_pivot = QPointF(0.0, 0.0)
    sc._array_variant = "polar"
    sc._array_base = QPointF(0.0, 0.0)
    sc.mode = tool


def _prep(sc, tool):
    """Pre-commit steps that must not count toward the emit tally."""
    ctl = sc._modify_ctl
    if tool == "copy":
        sc.set_mode("copy_base")
        sc._selected_items = list(sc.selectedItems())
    elif tool == "paste":
        # The real Copy -> Paste entry: write the clipboard, then arm paste.
        sc._copy_is_cut = False
        assert ctl.write_clipboard(list(sc._selected_items), QPointF(0.0, 0.0))
        sc.set_mode(None)
        assert ctl.begin_paste() is True
        sc._selected_items = []


def _commit(sc, tool):
    ctl = sc._modify_ctl
    if tool == "rotate":
        assert ctl.commit_rotate(30.0) is True
    elif tool == "duplicate":
        ctl.commit_duplicate(QPointF(5.0, 0.0))
    elif tool == "array":
        assert ctl.commit_array({"count": 3, "total_deg": 360.0}) is True
    elif tool == "copy":
        ctl.press_copy_base(None, QPointF(0.0, 0.0), QPointF(0.0, 0.0))
    elif tool == "paste":
        ctl.commit_paste(QPointF(5.0, 0.0))
    elif tool == "move":
        assert ctl._apply_move_displacement({"offset": QPointF(5.0, 0.0)}) is True


def _emits_for(tool, n):
    w, sc = _editor_scene()
    items = _lines(sc, n)
    _arm(sc, tool, items)
    _prep(sc, tool)
    hits = []
    sc.selectionChanged.connect(lambda: hits.append(1))
    _commit(sc, tool)
    return len(hits), len(sc.selectedItems())


@pytest.mark.parametrize("tool", ["rotate", "duplicate", "array", "move", "copy", "paste"])
def test_commit_emits_constant_selection_changed(qapp, tool):
    small, sel_small = _emits_for(tool, 4)
    big, sel_big = _emits_for(tool, 40)
    assert sel_big >= 40                      # the commit still leaves its result selected
    assert big == small, f"{tool}: {small} emits at n=4 but {big} at n=40"
    assert big <= 2


def _explode_emits(n):
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    d = BlockDefinition.new(
        name="E", library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(i * 10.0, 0), QPointF(i * 10.0, 50)).to_dict()
                    for i in range(n)])
    proj.register_block_definition(d)
    ms = BlockEditorWidget(proj).editor_scene     # explode is Block-Editor-only (C1)
    inst = ms.place_block_instance(d.id, (0.0, 0.0))
    ms.select_items([inst])
    hits = []
    ms.selectionChanged.connect(lambda: hits.append(1))
    new = ms.explode_selected_blocks()
    assert len(new) == n and all(it.isSelected() for it in new)
    return len(hits)


def test_explode_reselect_is_one_batch(qapp):
    assert _explode_emits(40) == _explode_emits(4) <= 2
