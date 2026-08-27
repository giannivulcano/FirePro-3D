"""Model Browser entity deletion — context menu + Delete key (spec §4.3).

The browser delegates to the scene's canonical delete_selected_items(); it does
not re-implement deletion. Underlay rows are excluded.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QTreeWidgetItem

from firepro3d.model_browser import ModelBrowser, _ROLE_ENTITY, _ROLE_UNDERLAY
from firepro3d.wall import WallSegment


@pytest.fixture
def browser_with_wall(model_space):
    scene = model_space
    wall = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    scene.addItem(wall)
    scene._walls.append(wall)
    b = ModelBrowser()
    b.set_scene(scene)
    b.refresh()
    return b, scene, wall


def _wall_row(browser, wall):
    def walk(item):
        for i in range(item.childCount()):
            c = item.child(i)
            if c.data(0, _ROLE_ENTITY) == id(wall):
                return c
            found = walk(c)
            if found is not None:
                return found
        return None
    return walk(browser._tree.invisibleRootItem())


def test_delete_selected_removes_entity(browser_with_wall):
    b, scene, wall = browser_with_wall
    row = _wall_row(b, wall)
    assert row is not None, "wall row not found in browser tree"
    row.setSelected(True)
    b._delete_selected_entities()
    assert wall not in scene._walls
    assert wall not in scene.items()


def test_delete_delegates_to_scene_path(browser_with_wall, monkeypatch):
    """The browser must call delete_selected_items exactly once (no re-impl)."""
    b, scene, wall = browser_with_wall
    calls = []
    real = scene.delete_selected_items
    monkeypatch.setattr(scene, "delete_selected_items",
                        lambda: (calls.append(1), real())[-1])
    _wall_row(b, wall).setSelected(True)
    b._delete_selected_entities()
    assert calls == [1], "delete must delegate to delete_selected_items once"
    assert wall not in scene._walls


def test_delete_key_triggers_delete(browser_with_wall):
    b, scene, wall = browser_with_wall
    _wall_row(b, wall).setSelected(True)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete,
                   Qt.KeyboardModifier.NoModifier)
    handled = b.eventFilter(b._tree, ev)
    assert handled is True, "Delete key must be consumed by the browser"
    assert wall not in scene._walls


def test_delete_empty_selection_is_noop(browser_with_wall):
    b, scene, wall = browser_with_wall
    b._tree.clearSelection()
    b._delete_selected_entities()  # must not raise
    assert wall in scene._walls


def test_underlay_row_excluded_from_delete(browser_with_wall, monkeypatch):
    b, scene, wall = browser_with_wall
    called = []
    monkeypatch.setattr(scene, "delete_selected_items",
                        lambda: called.append(1))
    ul_row = QTreeWidgetItem(b._tree, ["fake underlay"])
    ul_row.setData(0, _ROLE_UNDERLAY, 0)
    b._tree.clearSelection()
    ul_row.setSelected(True)
    b._delete_selected_entities()
    assert called == [], "underlay rows must not trigger entity deletion"
    assert wall in scene._walls


def test_non_delete_key_ignored(browser_with_wall):
    b, scene, wall = browser_with_wall
    _wall_row(b, wall).setSelected(True)
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A,
                   Qt.KeyboardModifier.NoModifier)
    assert b.eventFilter(b._tree, ev) is False
    assert wall in scene._walls
