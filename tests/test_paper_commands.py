"""Unit tests for firepro3d/paper_commands.py — per-command redo/undo.

Each command is constructed standalone against a PaperScene and exercised by
calling redo()/undo() directly (no main.py, no Ctrl+Z routing — that is 7b).
Assertions target the persistent data object plus the live scene tracking
lists, since commands key on data identity.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from firepro3d.paper_space import (
    PaperScene, Sheet, SheetViewData, TextAnnotationData, ViewResolver,
)
from firepro3d.paper_commands import (
    AddTextAnnotationCommand, DeleteTextAnnotationCommand,
    MoveTextAnnotationCommand, WrapResizeTextCommand,
    EditTextCommand, FormatTextCommand,
    AddViewportCommand, RemoveViewportCommand,
    ViewportGeometryCommand, ChangeViewportPropertiesCommand,
    _find_text_item, _find_viewport,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _stub_resolver():
    """ViewResolver with all-None managers — safe for sheets with no viewports."""
    return ViewResolver(None, None, None, None)


def _text_scene():
    """PaperScene for text-only tests (resolver never invoked)."""
    return PaperScene(Sheet.create_default(), _stub_resolver())


def _viewport_scene():
    """PaperScene whose resolver returns None — viewports build as placeholders.

    Placeholder viewports are still added to the scene + tracked, which is all
    the data-/scene-state assertions in these tests need.
    """
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = None
    return PaperScene(Sheet.create_default(), resolver)


def _vp_data(**kw):
    base = dict(source_view_type="plan", source_view_name="L1", title="L1",
                scale=0.01, x=50.0, y=50.0, w=400.0, h=300.0)
    base.update(kw)
    return SheetViewData(**base)


# ─────────────────────────────────────────────────────────────────────────────
# Text annotation commands
# ─────────────────────────────────────────────────────────────────────────────

def test_add_text_command_redo_undo(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="N", x=1, y=1)
    cmd = AddTextAnnotationCommand(scene, data)
    cmd.redo()
    assert data in scene.sheet.annotations
    assert _find_text_item(scene, data) is not None
    cmd.undo()
    assert data not in scene.sheet.annotations
    assert _find_text_item(scene, data) is None


def test_delete_text_command_redo_undo(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="N", x=1, y=1)
    scene._do_add_annotation(data)
    cmd = DeleteTextAnnotationCommand(scene, data)
    cmd.redo()
    assert data not in scene.sheet.annotations
    assert _find_text_item(scene, data) is None
    cmd.undo()
    assert data in scene.sheet.annotations
    assert _find_text_item(scene, data) is not None


def test_move_text_command_redo_undo(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="N", x=10, y=10)
    scene._do_add_annotation(data)
    cmd = MoveTextAnnotationCommand(scene, data, (10.0, 10.0), (40.0, 55.0))
    cmd.redo()
    assert (data.x, data.y) == pytest.approx((40.0, 55.0))
    it = _find_text_item(scene, data)
    assert (it.pos().x(), it.pos().y()) == pytest.approx((40.0, 55.0))
    cmd.undo()
    assert (data.x, data.y) == pytest.approx((10.0, 10.0))
    assert (it.pos().x(), it.pos().y()) == pytest.approx((10.0, 10.0))


def test_wrap_resize_text_command_redo_undo(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="word " * 20, x=10, y=10, wrap_width_mm=0.0)
    scene._do_add_annotation(data)
    cmd = WrapResizeTextCommand(scene, data, 0.0, 60.0)
    cmd.redo()
    assert data.wrap_width_mm == 60.0
    cmd.undo()
    assert data.wrap_width_mm == 0.0


def test_edit_text_command_redo_undo(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="old", x=1, y=1)
    scene._do_add_annotation(data)
    cmd = EditTextCommand(scene, data, "old", "new")
    cmd.redo()
    assert data.text == "new"
    assert _find_text_item(scene, data).toPlainText() == "new"
    cmd.undo()
    assert data.text == "old"
    assert _find_text_item(scene, data).toPlainText() == "old"


def test_format_text_command_redo_undo(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="x", x=1, y=1, bold=False,
                             color="#000000", height_mm=3.0, align="L")
    scene._do_add_annotation(data)
    old = {"bold": False, "color": "#000000", "height_mm": 3.0, "align": "L"}
    new = {"bold": True, "color": "#ff0000", "height_mm": 5.0, "align": "C"}
    cmd = FormatTextCommand(scene, data, old, new)
    cmd.redo()
    assert data.bold is True
    assert data.color == "#ff0000"
    assert data.height_mm == 5.0
    assert data.align == "C"
    it = _find_text_item(scene, data)
    assert it.font().bold() is True
    assert it.defaultTextColor().name() == "#ff0000"
    cmd.undo()
    assert data.bold is False
    assert data.color == "#000000"
    assert data.height_mm == 3.0
    assert data.align == "L"


# ─────────────────────────────────────────────────────────────────────────────
# Viewport commands
# ─────────────────────────────────────────────────────────────────────────────

def test_add_viewport_command_redo_undo(qapp):
    scene = _viewport_scene()
    data = _vp_data()
    cmd = AddViewportCommand(scene, data)
    cmd.redo()
    assert data in scene.sheet.sheet_views
    assert _find_viewport(scene, data) is not None
    assert len(scene.get_viewports()) == 1
    cmd.undo()
    assert data not in scene.sheet.sheet_views
    assert _find_viewport(scene, data) is None
    assert len(scene.get_viewports()) == 0


def test_remove_viewport_command_redo_undo(qapp):
    scene = _viewport_scene()
    data = _vp_data()
    scene._do_add_viewport(data)
    cmd = RemoveViewportCommand(scene, data)
    cmd.redo()
    assert data not in scene.sheet.sheet_views
    assert _find_viewport(scene, data) is None
    cmd.undo()
    assert data in scene.sheet.sheet_views
    assert _find_viewport(scene, data) is not None


def test_viewport_geometry_command_redo_undo(qapp):
    scene = _viewport_scene()
    data = _vp_data(x=50, y=50, w=400, h=300)
    scene._do_add_viewport(data)
    old = (50.0, 50.0, 400.0, 300.0)
    new = (100.0, 120.0, 500.0, 350.0)
    cmd = ViewportGeometryCommand(scene, data, old, new)
    cmd.redo()
    assert (data.x, data.y, data.w, data.h) == new
    vp = _find_viewport(scene, data)
    assert (vp.pos().x(), vp.pos().y()) == pytest.approx((100.0, 120.0))
    cmd.undo()
    assert (data.x, data.y, data.w, data.h) == old
    assert (vp.pos().x(), vp.pos().y()) == pytest.approx((50.0, 50.0))


def test_change_viewport_properties_command_redo_undo(qapp):
    scene = _viewport_scene()
    data = _vp_data(title="Old", show_border=True, scale=0.01)
    scene._do_add_viewport(data)
    old = {"title": "Old", "show_border": True, "scale": 0.01}
    new = {"title": "New", "show_border": False, "scale": 0.02}
    cmd = ChangeViewportPropertiesCommand(scene, data, old, new)
    cmd.redo()
    assert data.title == "New"
    assert data.show_border is False
    assert data.scale == 0.02
    cmd.undo()
    assert data.title == "Old"
    assert data.show_border is True
    assert data.scale == 0.01


# ─────────────────────────────────────────────────────────────────────────────
# Stack integration + re-enqueue guard
# ─────────────────────────────────────────────────────────────────────────────

def test_undo_stack_add_undo_redo_end_to_end(qapp):
    scene = _text_scene()
    data = TextAnnotationData(text="N", x=1, y=1)
    scene.undo_stack.push(AddTextAnnotationCommand(scene, data))
    assert data in scene.sheet.annotations
    scene.undo_stack.undo()
    assert data not in scene.sheet.annotations
    scene.undo_stack.redo()
    assert data in scene.sheet.annotations


def test_apply_guard_suppresses_gesture_push(qapp):
    """_push_* helpers must not enqueue while a command is being applied."""
    scene = _text_scene()
    data = TextAnnotationData(text="N", x=1, y=1)
    scene._do_add_annotation(data)

    scene._applying_command = True
    scene._push_text_move(data, (1, 1), (5, 5))
    assert scene.undo_stack.count() == 0

    scene._applying_command = False
    scene._push_text_move(data, (1, 1), (5, 5))
    assert scene.undo_stack.count() == 1

    # Unchanged geometry pushes nothing even when not applying.
    scene._push_text_move(data, (5, 5), (5, 5))
    assert scene.undo_stack.count() == 1


def test_viewport_geometry_push_guard(qapp):
    scene = _viewport_scene()
    data = _vp_data()
    scene._do_add_viewport(data)

    scene._applying_command = True
    scene._push_viewport_geometry(data, (50, 50, 400, 300), (60, 60, 400, 300))
    assert scene.undo_stack.count() == 0

    scene._applying_command = False
    scene._push_viewport_geometry(data, (50, 50, 400, 300), (60, 60, 400, 300))
    assert scene.undo_stack.count() == 1
