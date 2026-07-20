"""Unit tests for firepro3d/paper_commands.py — per-command redo/undo.

Each command is constructed standalone against a PaperScene and exercised by
calling redo()/undo() directly (no main.py, no Ctrl+Z routing — that is 7b).
Assertions target the persistent data object plus the live scene tracking
lists, since commands key on data identity.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QDialog, QGraphicsScene

from firepro3d.paper_space import (
    PaperScene, Sheet, SheetViewData, TextAnnotationData, ViewResolver,
)
from firepro3d.paper_commands import (
    AddTextAnnotationCommand, DeleteTextAnnotationCommand,
    MoveTextAnnotationCommand, ResizeTextBoxCommand,
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
    """ResizeTextBoxCommand restores x and wrap on undo (right-corner drag form)."""
    scene = _text_scene()
    data = TextAnnotationData(text="word " * 20, x=10, y=10, wrap_width_mm=0.0)
    scene._do_add_annotation(data)
    # Right-corner drag: x/y unchanged (10, 10), wrap changes 0→60, box_height 0→0
    cmd = ResizeTextBoxCommand(scene, data, (10.0, 10.0, 0.0, 0.0), (10.0, 10.0, 60.0, 0.0))
    cmd.redo()
    assert data.wrap_width_mm == 60.0
    assert data.x == pytest.approx(10.0)
    cmd.undo()
    assert data.wrap_width_mm == 0.0
    assert data.x == pytest.approx(10.0)


def test_wrap_resize_text_command_left_corner_redo_undo(qapp):
    """Left-corner ResizeTextBoxCommand restores x and wrap atomically (4-tuple form)."""
    scene = _text_scene()
    data = TextAnnotationData(text="word " * 20, x=10, y=10, wrap_width_mm=60.0)
    scene._do_add_annotation(data)
    # Left-corner drag: x moves from 10→20, wrap shrinks from 60→50, y/bh unchanged
    cmd = ResizeTextBoxCommand(scene, data, (10.0, 10.0, 60.0, 0.0), (20.0, 10.0, 50.0, 0.0))
    cmd.redo()
    assert data.x == pytest.approx(20.0)
    assert data.wrap_width_mm == pytest.approx(50.0)
    it = _find_text_item(scene, data)
    assert it.pos().x() == pytest.approx(20.0)
    cmd.undo()
    assert data.x == pytest.approx(10.0)
    assert data.wrap_width_mm == pytest.approx(60.0)
    assert it.pos().x() == pytest.approx(10.0)


def test_resize_text_box_command_4tuple_redo_undo(qapp):
    """ResizeTextBoxCommand restores x, y, wrap_width_mm, and box_height_mm on undo."""
    scene = _text_scene()
    data = TextAnnotationData(text="word " * 20, x=10, y=10,
                              wrap_width_mm=60.0, box_height_mm=0.0)
    scene._do_add_annotation(data)
    # Simulate a TL drag: x+5, y+3, wrap-5, box_height from auto to 25
    old = (10.0, 10.0, 60.0, 0.0)
    new = (15.0, 13.0, 55.0, 25.0)
    cmd = ResizeTextBoxCommand(scene, data, old, new)
    cmd.redo()
    assert data.x == pytest.approx(15.0)
    assert data.y == pytest.approx(13.0)
    assert data.wrap_width_mm == pytest.approx(55.0)
    assert data.box_height_mm == pytest.approx(25.0)
    it = _find_text_item(scene, data)
    assert it.pos().x() == pytest.approx(15.0)
    assert it.pos().y() == pytest.approx(13.0)
    cmd.undo()
    assert data.x == pytest.approx(10.0)
    assert data.y == pytest.approx(10.0)
    assert data.wrap_width_mm == pytest.approx(60.0)
    assert data.box_height_mm == pytest.approx(0.0)
    assert it.pos().x() == pytest.approx(10.0)
    assert it.pos().y() == pytest.approx(10.0)


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
# Data-identity tracking (I1) + empty-edit undo baseline (I2)
# ─────────────────────────────────────────────────────────────────────────────

def test_two_value_identical_annotations_both_tracked(qapp):
    """Value-identical annotations must both persist + be independently removable."""
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    d1 = TextAnnotationData(text="N", x=1, y=1)
    d2 = TextAnnotationData(text="N", x=1, y=1)   # value-identical, distinct identity
    scene._do_add_annotation(d1)
    scene._do_add_annotation(d2)
    assert len(scene.sheet.annotations) == 2
    scene._do_remove_annotation_by_data(d1)
    assert scene.sheet.annotations == [d2] or (
        len(scene.sheet.annotations) == 1 and scene.sheet.annotations[0] is d2)
    # The surviving sibling is still removable by its own identity.
    scene._do_remove_annotation_by_data(d2)
    assert scene.sheet.annotations == []


def test_two_value_identical_viewports_both_tracked(qapp):
    """Identity tracking holds for viewports too (parity with annotations)."""
    scene = _viewport_scene()
    v1 = _vp_data()
    v2 = _vp_data()   # value-identical, distinct identity
    scene._do_add_viewport(v1)
    scene._do_add_viewport(v2)
    assert len(scene.sheet.sheet_views) == 2
    scene._do_remove_viewport_by_data(v1)
    assert len(scene.sheet.sheet_views) == 1
    assert scene.sheet.sheet_views[0] is v2


def test_empty_edit_of_existing_block_undo_restores_text(qapp):
    """Emptying an existing block then undoing restores its ORIGINAL text."""
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    item = scene.add_annotation(TextAnnotationData(text="Hi", x=2, y=2))
    # Mirror commit_edit(): the live block's data.text is already "" by the time
    # _push_text_edit runs. Without the fix the DeleteCommand would store text=""
    # and undo would restore an EMPTY block.
    item.data.text = ""
    scene._push_text_edit(item.data, "Hi", "")          # old="Hi", new=""
    # The emptied block is no longer tracked (DeleteText.redo ran).
    assert all(a is not item.data for a in scene.sheet.annotations)
    scene.undo_stack.undo()
    restored = scene.get_annotations()
    assert any(a.toPlainText() == "Hi" for a in restored)


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


# ─────────────────────────────────────────────────────────────────────────────
# Viewport properties: scale → w/h re-derivation (I3)
# ─────────────────────────────────────────────────────────────────────────────

# Source rect the stub resolver hands back; scale × these = derived w/h.
_SRC_RECT = QRectF(0, 0, 10000, 8000)


class _StubVPDialog:
    """Stand-in for SheetViewPropertiesDialog mirroring its caller-read API.

    _on_viewport_properties constructs it as ``Dialog(source_view_name, data)``
    and reads exec()/get_title/get_show_border/get_scale/get_position/get_size.
    Configured values are injected by the monkeypatched factory.
    """
    title = None
    show_border = None
    scale = None
    position = None
    size = None

    def __init__(self, source_view_name, data):
        self._data = data

    def exec(self):
        return QDialog.DialogCode.Accepted

    def get_title(self):
        return self.title if self.title is not None else self._data.title

    def get_show_border(self):
        return (self.show_border if self.show_border is not None
                else self._data.show_border)

    def get_scale(self):
        return self.scale if self.scale is not None else self._data.scale

    def get_position(self):
        return self.position

    def get_size(self):
        return self.size


def _resolving_scene():
    """PaperScene whose resolver returns a real (scene, _SRC_RECT) source."""
    src = QGraphicsScene()
    src.addRect(_SRC_RECT)
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.return_value = (src, _SRC_RECT)
    return PaperScene(Sheet.create_default(), resolver)


def _patch_vp_dialog(monkeypatch, **cfg):
    """Patch SheetViewPropertiesDialog with a preconfigured _StubVPDialog."""
    stub = type("_VPDlg", (_StubVPDialog,), cfg)
    monkeypatch.setattr(
        "firepro3d.paper_space.SheetViewPropertiesDialog", stub)


def test_viewport_properties_scale_rederives_wh(qapp, monkeypatch):
    """Changing only the scale re-derives w/h from source_rect × new scale."""
    scene = _resolving_scene()
    data = _vp_data(scale=0.01, w=400.0, h=300.0)
    scene._do_add_viewport(data)
    _patch_vp_dialog(monkeypatch, scale=0.02)   # no explicit position/size

    vp = _find_viewport(scene, data)
    scene._on_viewport_properties(vp)

    assert scene.undo_stack.count() == 1
    # redo() applied new_fields synchronously → derived from _SRC_RECT × 0.02.
    assert data.scale == 0.02
    assert data.w == pytest.approx(_SRC_RECT.width() * 0.02)   # 200.0
    assert data.h == pytest.approx(_SRC_RECT.height() * 0.02)  # 160.0


def test_viewport_properties_explicit_size_overrides_scale(qapp, monkeypatch):
    """An explicit size override wins over the scale-derived w/h."""
    scene = _resolving_scene()
    data = _vp_data(scale=0.01, w=400.0, h=300.0)
    scene._do_add_viewport(data)
    _patch_vp_dialog(monkeypatch, scale=0.02, size=(123.0, 45.0))

    vp = _find_viewport(scene, data)
    scene._on_viewport_properties(vp)

    assert scene.undo_stack.count() == 1
    assert data.w == pytest.approx(123.0)   # explicit override, NOT 200.0
    assert data.h == pytest.approx(45.0)


def test_update_from_sheet_clears_undo_stack(qapp):
    """Loading a sheet via update_from_sheet wipes the undo history (§17.5)."""
    scene = PaperScene(Sheet.create_default(), _stub_resolver())
    scene._undo_stack.push(
        AddTextAnnotationCommand(scene, TextAnnotationData(text="X", x=1, y=1)))
    assert scene._undo_stack.count() > 0
    scene.update_from_sheet(Sheet.create_default())
    assert scene._undo_stack.count() == 0
    assert not scene._undo_stack.canUndo()
