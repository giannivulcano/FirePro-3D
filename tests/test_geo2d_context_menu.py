"""test_geo2d_context_menu.py
==============================
UP2 (R7): both right-click paths offer "Fill…" / "Fill Pattern…" (the UP1
picker) for the selected fillable 2D shapes, never the retired Fill submenu.

  PATH A — entity path: Model_Space._build_entity_context_menu (production
            builder, no exec).
  PATH B — plan path: Model_View._build_plan_context_menu.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import RectangleItem, LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scene_and_view(qapp):
    """Return (Model_Space, Model_View) — view is shown so Qt is happy."""
    ms = Model_Space()
    view = Model_View(ms)
    view.resize(800, 600)
    QApplication.processEvents()
    return ms, view


def _menu_action_texts(menu) -> list[str]:
    """Flat list of top-level action titles in *menu* (separators excluded)."""
    return [a.text() for a in menu.actions() if not a.isSeparator() and a.text()]


def _find_submenu(menu, title: str):
    """Return the QMenu for a top-level action whose text matches *title*, or None."""
    for a in menu.actions():
        if a.text() == title and a.menu() is not None:
            return a.menu()
    return None


def _undo_stack_size(scene) -> int:
    return len(getattr(scene, "_undo_stack", []))


FILL = "Fill…"
FILL_PATTERN = "Fill Pattern…"


def _action(menu, text):
    return next((a for a in menu.actions() if a.text() == text), None)


def _undoable_rects(ms, n=2):
    """*n* selected rects on the undo snapshot's draw list, baseline pushed."""
    rects = []
    for i in range(n):
        r = RectangleItem(QPointF(300 * i, 0), QPointF(300 * i + 200, 100))
        ms.addItem(r); ms._draw_rects.append(r); r.setSelected(True)
        rects.append(r)
    ms.push_undo_state()
    return rects


def _stub_pick(monkeypatch, result):
    """Replace colour_picker.pick_fill; returns the list of recorded calls."""
    from firepro3d import colour_picker
    calls = []
    def fake(initial, parent=None, **kw):
        calls.append((initial, kw))
        return result
    monkeypatch.setattr(colour_picker, "pick_fill", fake)
    return calls


# ---------------------------------------------------------------------------
# PATH B: Model_View._build_plan_context_menu
# ---------------------------------------------------------------------------

class TestPlanContextMenu:
    """PATH B — plan view generic menu."""

    def test_entries_replace_submenu_for_two_fillable(self, qapp):
        """G1(B): 2 fillable rects → both entries, no Fill submenu."""
        ms, view = _make_scene_and_view(qapp)
        _undoable_rects(ms)
        menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
        texts = _menu_action_texts(menu)
        assert FILL in texts and FILL_PATTERN in texts, texts
        assert _find_submenu(menu, "Fill") is None, texts

    def test_no_entries_for_line_item(self, qapp):
        """G1(B): a lone LineItem → neither entry."""
        ms, view = _make_scene_and_view(qapp)
        line = LineItem(QPointF(0, 0), QPointF(200, 0))
        ms.addItem(line); line.setSelected(True)
        texts = _menu_action_texts(
            view._build_plan_context_menu(ms, ms.selectedItems(), "select"))
        assert FILL not in texts and FILL_PATTERN not in texts, texts

    def test_fill_pattern_writes_both_one_undo_step(self, qapp, monkeypatch, shipped_hatches):
        """G2: Fill Pattern… → brick on both rects; +1 undo; undo → none; redo → back."""
        from firepro3d.fill_layers import PatternLayer
        from firepro3d.hatch_patterns import BUILTIN_BRICK
        ms, view = _make_scene_and_view(qapp)
        shipped_hatches(ms)
        _undoable_rects(ms)
        pos0 = ms._undo_pos
        layer = PatternLayer(BUILTIN_BRICK)
        _stub_pick(monkeypatch, layer)
        menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
        _action(menu, FILL_PATTERN).trigger()
        assert [r.fill_layers.pattern for r in ms._draw_rects] == [layer, layer]
        assert ms._undo_pos == pos0 + 1
        ms.undo()                                   # items rebuilt: re-read the list
        assert [r.fill_layers.pattern for r in ms._draw_rects] == [None, None]
        ms.redo()
        assert [r.fill_layers.pattern for r in ms._draw_rects] == [layer, layer]


# ---------------------------------------------------------------------------
# PATH A: Model_Space._build_entity_context_menu (entity path)
# ---------------------------------------------------------------------------

class TestEntityContextMenu:
    """PATH A — entity right-click menu."""

    def test_entries_replace_submenu_for_fillable_selection(self, qapp):
        """G1(A): fillable selection → Fill… + Fill Pattern…, no Fill submenu."""
        ms = Model_Space()
        a, b = _undoable_rects(ms)
        menu = ms._build_entity_context_menu(a)
        texts = _menu_action_texts(menu)
        assert FILL in texts and FILL_PATTERN in texts, texts
        assert _find_submenu(menu, "Fill") is None, texts

    def test_entries_show_when_clicked_item_is_not_fillable(self, qapp):
        """AC1: ≥1 fillable in the selection is enough (clicked a line)."""
        ms = Model_Space()
        (r,) = _undoable_rects(ms, 1)
        line = LineItem(QPointF(0, 0), QPointF(200, 0))
        ms.addItem(line); line.setSelected(True)
        texts = _menu_action_texts(ms._build_entity_context_menu(line))
        assert FILL in texts and FILL_PATTERN in texts, texts

    def test_no_entries_for_line_or_reference_only(self, qapp):
        """G1(A): no fillable (a line; a reference rect) → neither entry."""
        ms = Model_Space()
        line = LineItem(QPointF(0, 0), QPointF(200, 0))
        ms.addItem(line); line.setSelected(True)
        ref = RectangleItem(QPointF(0, 0), QPointF(50, 50))
        ms.addItem(ref); ref.set_property("Reference", True); ref.setSelected(True)
        assert ref.reference
        for target in (line, ref):
            texts = _menu_action_texts(ms._build_entity_context_menu(target))
            assert FILL not in texts and FILL_PATTERN not in texts, texts
            assert _find_submenu(ms._build_entity_context_menu(target), "Fill") is None

    def test_fill_no_layer_turns_every_background_off_one_step(self, qapp, monkeypatch):
        """G3: Fill… → NO_LAYER clears both backgrounds in one undo step."""
        from firepro3d.fill_layers import NO_LAYER, BackgroundLayer
        ms = Model_Space()
        a, b = _undoable_rects(ms)
        for r in (a, b):
            r.set_property("Fill", BackgroundLayer("#ff0000", 1.0))
        pos0 = ms._undo_pos
        _stub_pick(monkeypatch, NO_LAYER)
        menu = ms._build_entity_context_menu(a)     # unparented: keep it alive
        _action(menu, FILL).trigger()
        assert a.fill_layers.background is None and b.fill_layers.background is None
        assert ms._undo_pos == pos0 + 1

    def test_picker_args_and_cancel(self, qapp, monkeypatch, shipped_hatches):
        """G4: pattern mode, initial = clicked shape's layer, registry/exclude
        as the panel passes; cancel (None) writes nothing, pushes nothing."""
        from firepro3d.fill_layers import PatternLayer
        from firepro3d.hatch_patterns import (BUILTIN_BRICK, BUILTIN_DIAGONAL,
                                              picker_exclude)
        ms = Model_Space(); shipped_hatches(ms)
        a, b = _undoable_rects(ms)
        a.set_property("Fill Pattern", PatternLayer(BUILTIN_DIAGONAL))
        b.set_property("Fill Pattern", PatternLayer(BUILTIN_BRICK))
        pos0 = ms._undo_pos
        before = (a.fill_layers, b.fill_layers)
        calls = _stub_pick(monkeypatch, None)
        menu = ms._build_entity_context_menu(b)     # unparented: keep it alive
        _action(menu, FILL_PATTERN).trigger()
        ((initial, kw),) = calls
        assert initial == b.fill_layers.pattern            # the clicked shape
        assert kw["pattern"] is True
        assert kw["registry"] is ms.block_registry
        assert frozenset(kw["exclude"]) == picker_exclude(ms)   # frozenset (hatch_patterns.py:253)
        assert (a.fill_layers, b.fill_layers) == before    # cancel: no change
        assert ms._undo_pos == pos0
        calls.clear()
        menu = ms._build_entity_context_menu(a)
        _action(menu, FILL).trigger()
        ((initial, kw),) = calls
        assert initial is None and kw["pattern"] is False  # no background yet
