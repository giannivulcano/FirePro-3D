"""Tests for the SheetViewport property-panel adapter (#3).

ViewportProperties supersedes the double-click SheetViewPropertiesDialog: the
panel and the dialog now share PaperScene.commit_viewport_edit, so the crop×scale
size derivation (concern 5) has a single home and every edit is undoable.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsRectItem, QDialog

from firepro3d.paper_space import (
    PaperScene, Sheet, SheetViewData, ViewResolver, ViewportProperties,
)


class _FakePlanMgr:
    def __init__(self):
        self._views = {"Level 1": object()}

    def get(self, name):
        return self._views.get(name)


class _FakeDetailMgr:
    def get_marker(self, name):
        return None

    @property
    def detail_names(self):
        return []


def _resolver(model):
    return ViewResolver(model, _FakePlanMgr(), _FakeDetailMgr(),
                        elevation_manager=None)


@pytest.fixture
def scene_and_vp(qapp):
    model = QGraphicsScene()
    model.addItem(QGraphicsRectItem(QRectF(0, 0, 1000, 500)))
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Level 1", "PLAN", 0.1, 0, 0, 0, 0)
    scene = PaperScene(sheet, _resolver(model))
    vp = scene.add_viewport(data)
    # Crop seeds to the full 1000×500 source extent.
    assert data.crop_rect.width() == pytest.approx(1000, abs=1.0)
    return scene, vp


def test_get_properties_exposes_expected_fields(scene_and_vp):
    scene, vp = scene_and_vp
    props = ViewportProperties(scene, vp).get_properties()
    assert props["Title"]["type"] == "string"
    assert props["Scale"]["type"] == "enum"
    assert "NTS" in props["Scale"]["options"]
    assert props["Show Border"]["type"] == "bool"
    assert props["Position X"]["type"] == "string"
    assert props["Position Y"]["type"] == "string"
    # Size is derived from crop × scale → read-only labels.
    assert props["Width"]["type"] == "label"
    assert props["Height"]["type"] == "label"


def test_title_edit_is_undoable(scene_and_vp):
    scene, vp = scene_and_vp
    ViewportProperties(scene, vp).set_property("Title", "PLAN A")
    assert vp.data.title == "PLAN A"
    scene.undo_stack.undo()
    assert vp.data.title != "PLAN A"


def test_show_border_toggle_is_undoable(scene_and_vp):
    scene, vp = scene_and_vp
    before = vp.data.show_border
    ViewportProperties(scene, vp).set_property("Show Border", not before)
    assert vp.data.show_border == (not before)
    scene.undo_stack.undo()
    assert vp.data.show_border == before


def test_scale_change_derives_size_and_is_undoable(scene_and_vp):
    scene, vp = scene_and_vp
    w0, h0 = vp.data.w, vp.data.h
    # Drive the shared helper the panel routes through.
    changed = scene.commit_viewport_edit(vp, scale=0.2)
    assert changed
    assert vp.data.scale == pytest.approx(0.2)
    assert vp.data.w == pytest.approx(1000 * 0.2, abs=0.5)
    assert vp.data.h == pytest.approx(500 * 0.2, abs=0.5)
    scene.undo_stack.undo()
    assert vp.data.w == pytest.approx(w0, abs=0.5)
    assert vp.data.h == pytest.approx(h0, abs=0.5)


def test_scale_nts_parses_to_zero(scene_and_vp):
    scene, vp = scene_and_vp
    ViewportProperties(scene, vp).set_property("Scale", "NTS")
    assert vp.data.scale == 0.0


def test_position_x_edit_keeps_y(scene_and_vp):
    scene, vp = scene_and_vp
    y0 = vp.data.y
    ViewportProperties(scene, vp).set_property("Position X", "42")
    assert vp.data.x == pytest.approx(42.0)
    assert vp.data.y == pytest.approx(y0)


def test_position_invalid_input_ignored(scene_and_vp):
    scene, vp = scene_and_vp
    x0 = vp.data.x
    count = scene.undo_stack.count()
    ViewportProperties(scene, vp).set_property("Position X", "not a number")
    assert vp.data.x == pytest.approx(x0)
    assert scene.undo_stack.count() == count, "invalid input must not push undo"


def test_commit_viewport_edit_noop_returns_false(scene_and_vp):
    scene, vp = scene_and_vp
    count = scene.undo_stack.count()
    assert scene.commit_viewport_edit(vp, title=vp.data.title) is False
    assert scene.undo_stack.count() == count


def test_dialog_path_routes_through_shared_helper(scene_and_vp, monkeypatch):
    """_on_viewport_properties (double-click) now shares commit_viewport_edit."""
    scene, vp = scene_and_vp

    class _FakeDlg:
        def __init__(self, name, data, parent=None):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def get_title(self):
            return "PLAN X"

        def get_show_border(self):
            return False

        def get_scale(self):
            return 0.2

        def get_position(self):
            return (vp.data.x, vp.data.y)

    monkeypatch.setattr(
        "firepro3d.paper_space.SheetViewPropertiesDialog", _FakeDlg)
    scene._on_viewport_properties(vp)
    assert vp.data.title == "PLAN X"
    assert vp.data.show_border is False
    assert vp.data.scale == pytest.approx(0.2)
    # Same crop×scale derivation as the panel.
    assert vp.data.w == pytest.approx(1000 * 0.2, abs=0.5)
