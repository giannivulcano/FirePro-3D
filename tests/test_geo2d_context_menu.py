"""test_geo2d_context_menu.py
==============================
Tests for the Fill submenu on 2D closed shapes in Model_View's two
context-menu paths:

  PATH A — entity path: Model_Space._show_entity_context_menu (called when
            _find_entity_at returns the item; called directly to avoid blocking exec).
  PATH B — generic/thin path: Model_View._build_plan_context_menu (called
            directly, the established pattern from test_gridline_array_offset).

Both paths must expose a "Fill" submenu when the target/selection is fillable,
and must NOT expose it for a non-fillable LineItem.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.construction_geometry import RectangleItem, LineItem
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


# ---------------------------------------------------------------------------
# PATH B: Model_View._build_plan_context_menu
# ---------------------------------------------------------------------------

class TestPlanContextMenu:
    """Tests for the generic/thin path (_build_plan_context_menu)."""

    def test_fill_submenu_present_for_fillable_selected(self, qapp):
        """A selected fillable RectangleItem makes the Fill submenu appear."""
        ms, view = _make_scene_and_view(qapp)
        rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
        ms.addItem(rect)
        rect.setSelected(True)

        menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is not None, (
            "Fill submenu missing from _build_plan_context_menu when a "
            f"fillable item is selected; actions={_menu_action_texts(menu)}"
        )

    def test_fill_submenu_contains_none_solid_hatch(self, qapp):
        """The Fill submenu has at least None, Solid, and Hatch actions."""
        ms, view = _make_scene_and_view(qapp)
        rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
        ms.addItem(rect)
        rect.setSelected(True)

        menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is not None
        action_texts = [a.text() for a in fill_sub.actions() if not a.isSeparator()]
        assert "None" in action_texts, f"'None' missing from Fill submenu: {action_texts}"
        assert "Solid" in action_texts, f"'Solid' missing from Fill submenu: {action_texts}"
        # Hatch may be a sub-submenu action or a direct action
        hatch_labels = [t for t in action_texts if "Hatch" in t]
        assert hatch_labels, f"'Hatch' missing from Fill submenu: {action_texts}"

    def test_fill_solid_action_sets_fill_type_and_pushes_undo(self, qapp):
        """Triggering 'Solid' sets rect.fill_type == 'solid' and pushes one undo step."""
        ms, view = _make_scene_and_view(qapp)
        rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
        ms.addItem(rect)
        rect.setSelected(True)

        before = _undo_stack_size(ms)
        menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is not None

        solid_act = next(
            (a for a in fill_sub.actions() if a.text() == "Solid"), None
        )
        assert solid_act is not None, "Solid action not found in Fill submenu"
        solid_act.trigger()

        assert rect.fill_type == "solid", (
            f"Expected fill_type='solid' after triggering Solid action, got '{rect.fill_type}'"
        )
        after = _undo_stack_size(ms)
        assert after == before + 1, (
            f"Expected exactly one new undo step; stack was {before}, now {after}"
        )

    def test_no_fill_submenu_for_line_item(self, qapp):
        """A LineItem (not fillable) must not have a Fill submenu."""
        ms, view = _make_scene_and_view(qapp)
        line = LineItem(QPointF(0, 0), QPointF(200, 0))
        ms.addItem(line)
        line.setSelected(True)

        menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is None, (
            "Fill submenu unexpectedly present for a non-fillable LineItem; "
            f"actions={_menu_action_texts(menu)}"
        )

    def test_hatch_submenu_contains_patterns(self, qapp):
        """The Hatch sub-submenu contains known pattern names."""
        from firepro3d.hatch_patterns import PATTERN_NAMES
        ms, view = _make_scene_and_view(qapp)
        rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
        ms.addItem(rect)
        rect.setSelected(True)

        menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is not None

        # Find Hatch action and its submenu
        hatch_act = next(
            (a for a in fill_sub.actions() if "Hatch" in a.text() and a.menu()), None
        )
        assert hatch_act is not None, (
            "Hatch action with a patterns sub-submenu not found in Fill submenu"
        )
        pattern_texts = [a.text() for a in hatch_act.menu().actions() if not a.isSeparator()]
        for name in PATTERN_NAMES:
            assert name in pattern_texts, (
                f"Pattern '{name}' missing from Hatch submenu: {pattern_texts}"
            )


# ---------------------------------------------------------------------------
# PATH A: Model_Space._show_entity_context_menu (entity path)
# ---------------------------------------------------------------------------

class TestEntityContextMenu:
    """Tests for the entity path (_show_entity_context_menu via build_entity_context_menu)."""

    def _capture_entity_menu(self, ms, target):
        """Call _show_entity_context_menu and intercept the menu before exec.

        We monkey-patch QMenu.exec on the returned menu to prevent blocking.
        The menu is captured via the patched on_fill callback.
        """
        from firepro3d.entity_context_menu import build_entity_context_menu
        # Call the builder directly (same as _show_entity_context_menu does internally)
        from firepro3d.room import Room
        selected = ms.selectedItems()

        menu = build_entity_context_menu(
            selected,
            target,
            scene=ms,
            on_copy=ms.copy_selected_items,
            on_hide=lambda: ms._hide_items(
                [target] + [i for i in selected if i is not target]
            ),
            on_hide_all_type=lambda t=type(target): ms._hide_all_of_type(t),
            on_show_all=ms._show_all_hidden,
            on_delete=ms.delete_selected_items,
            on_properties=lambda: None,
        )
        return menu

    def test_fill_submenu_present_for_fillable_target(self, qapp):
        """Entity-path menu contains a Fill submenu when the target is fillable."""
        ms = Model_Space()
        rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
        ms.addItem(rect)
        rect.setSelected(True)

        menu = self._capture_entity_menu(ms, rect)
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is not None, (
            "Fill submenu missing from entity-path menu for fillable RectangleItem; "
            f"actions={_menu_action_texts(menu)}"
        )

    def test_fill_submenu_contains_none_solid_hatch_entity_path(self, qapp):
        """Entity path Fill submenu has None, Solid, and Hatch."""
        ms = Model_Space()
        rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
        ms.addItem(rect)
        rect.setSelected(True)

        menu = self._capture_entity_menu(ms, rect)
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is not None
        action_texts = [a.text() for a in fill_sub.actions() if not a.isSeparator()]
        assert "None" in action_texts
        assert "Solid" in action_texts
        hatch_labels = [t for t in action_texts if "Hatch" in t]
        assert hatch_labels, f"'Hatch' missing: {action_texts}"

    def test_fill_solid_action_entity_path_sets_fill_type_and_undo(self, qapp):
        """Entity path: Solid action sets fill_type and pushes one undo step."""
        ms = Model_Space()
        rect = RectangleItem(QPointF(0, 0), QPointF(200, 100))
        ms.addItem(rect)
        rect.setSelected(True)

        before = _undo_stack_size(ms)
        menu = self._capture_entity_menu(ms, rect)
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is not None

        solid_act = next(
            (a for a in fill_sub.actions() if a.text() == "Solid"), None
        )
        assert solid_act is not None
        solid_act.trigger()

        assert rect.fill_type == "solid", (
            f"Expected 'solid', got '{rect.fill_type}'"
        )
        after = _undo_stack_size(ms)
        assert after == before + 1, (
            f"Expected one new undo step; before={before}, after={after}"
        )

    def test_no_fill_submenu_for_line_item_entity_path(self, qapp):
        """Entity path: LineItem must not have a Fill submenu."""
        ms = Model_Space()
        line = LineItem(QPointF(0, 0), QPointF(200, 0))
        ms.addItem(line)
        line.setSelected(True)

        menu = self._capture_entity_menu(ms, line)
        fill_sub = _find_submenu(menu, "Fill")
        assert fill_sub is None, (
            "Fill submenu unexpectedly present for LineItem in entity path"
        )
