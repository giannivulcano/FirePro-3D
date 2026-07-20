"""Paper persistence: sheetModified signal, dirty flag, recovery parity.

Scene-level tests exercise PaperScene.sheetModified directly; MainWindow-level
tests cover the _modified flag, crash recovery, and resolver identity.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from firepro3d.paper_space import (
    PaperScene, PaperSpaceWidget, Sheet, TextAnnotationData, ViewResolver,
)
from firepro3d.paper_commands import AddTextAnnotationCommand


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stub_resolver():
    """ViewResolver with all-None managers — safe for sheets with no viewports."""
    return ViewResolver(None, None, None, None)


def _text_scene():
    return PaperScene(Sheet.create_default(), _stub_resolver())


def _spy(scene):
    """Collect sheetModified emissions."""
    hits = []
    scene.sheetModified.connect(lambda: hits.append(1))
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# Scene-level: sheetModified emission rules
# ─────────────────────────────────────────────────────────────────────────────

def test_sheet_modified_on_command_push_undo_redo(qapp):
    scene = _text_scene()
    hits = _spy(scene)
    data = TextAnnotationData(text="N", x=10, y=10)
    scene.undo_stack.push(AddTextAnnotationCommand(scene, data))
    assert len(hits) == 1, "command push must emit sheetModified"
    scene.undo_stack.undo()
    assert len(hits) == 2, "undo must emit sheetModified (dirty rule: undo dirties)"
    scene.undo_stack.redo()
    assert len(hits) == 3, "redo must emit sheetModified"


def test_sheet_modified_suppressed_during_update_from_sheet(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="N", x=10, y=10)
    scene.undo_stack.push(AddTextAnnotationCommand(scene, data))  # non-empty stack
    hits = _spy(scene)
    scene.update_from_sheet(Sheet.create_default())
    # _setup() rebuild + undo_stack.clear() (which fires indexChanged) must not leak
    assert hits == [], "load-path rebuild must not emit sheetModified"


def test_sheet_modified_on_paper_size_change_only(qapp):
    scene = _text_scene()
    hits = _spy(scene)
    same = scene.paper_size
    scene.paper_size = same
    assert hits == [], "no-op paper size set must not emit"
    other = "ANSI B" if same != "ANSI B" else "ANSI D"
    scene.paper_size = other
    assert len(hits) == 1, "real paper size change must emit sheetModified"
    assert scene.paper_size == other
