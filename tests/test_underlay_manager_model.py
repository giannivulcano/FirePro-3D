"""Tests for the Underlay Manager tree model (Task 10)."""
from PyQt6.QtCore import QObject, pyqtSignal, Qt, QModelIndex

from firepro3d.underlay import Underlay
from firepro3d.underlay_manager_theme import DARK
from firepro3d.underlay_manager_model import (
    UnderlayTreeModel,
    Col,
)


class _FakeScene(QObject):
    underlaysChanged = pyqtSignal()

    def __init__(self, underlays):
        super().__init__()
        self.underlays = underlays
        self.active_level = "L1"
        self.repen_calls = []
        self.apply_calls = 0
        self.layer_hidden_calls = []
        _outer = self

        class _LM:
            def apply_to_scene(_s, _scene, _active=None):
                _outer.apply_calls += 1

        self.level_mgr = _LM()

    def repen_underlay(self, rec):
        self.repen_calls.append(rec)

    def set_underlay_layer_hidden(self, rec, group, layer, hidden):
        self.layer_hidden_calls.append((rec, group, layer, hidden))
        if hidden and layer not in rec.hidden_layers:
            rec.hidden_layers.append(layer)
        elif not hidden and layer in rec.hidden_layers:
            rec.hidden_layers.remove(layer)


def _dxf_record():
    rec = Underlay(type="dxf", path="/tmp/p.dxf", levels=["L1"], colour="#111111")
    rec.layer_names = [("WALLS", 10), ("GRID", 4)]
    return rec


def _raster_pdf_record():
    rec = Underlay(type="pdf", path="/tmp/p.pdf", levels=["L1"])
    rec.layer_names = []
    return rec


def _make_model(records):
    underlays = [(r, object()) for r in records]
    scene = _FakeScene(underlays)
    model = UnderlayTreeModel(scene, DARK, lambda: ["L1", "L2"])
    return scene, model


def test_top_level_rowcount(qapp):
    rec = _dxf_record()
    _scene, model = _make_model([rec])
    assert model.rowCount(QModelIndex()) == 1


def test_dxf_has_two_layer_children(qapp):
    rec = _dxf_record()
    _scene, model = _make_model([rec])
    top = model.index(0, 0, QModelIndex())
    assert model.rowCount(top) == 2


def test_raster_pdf_has_no_children(qapp):
    rec = _raster_pdf_record()
    _scene, model = _make_model([rec])
    top = model.index(0, 0, QModelIndex())
    assert model.rowCount(top) == 0


def test_setdata_colour_routes_repen(qapp):
    rec = _dxf_record()
    scene, model = _make_model([rec])
    idx = model.index(0, int(Col.COLOUR), QModelIndex())
    assert model.setData(idx, "#abcdef", Qt.ItemDataRole.EditRole) is True
    assert rec.colour == "#abcdef"
    assert rec in scene.repen_calls


def test_setdata_levels_routes_apply(qapp):
    rec = _dxf_record()
    scene, model = _make_model([rec])
    idx = model.index(0, int(Col.LEVELS), QModelIndex())
    assert model.setData(idx, ["L1", "L2"], Qt.ItemDataRole.EditRole) is True
    assert rec.levels == ["L1", "L2"]
    assert scene.apply_calls >= 1


def test_setdata_snap_toggles(qapp):
    rec = _dxf_record()
    _scene, model = _make_model([rec])
    idx = model.index(0, int(Col.SNAP), QModelIndex())
    assert model.setData(idx, False, Qt.ItemDataRole.EditRole) is True
    assert rec.snap is False


def test_setdata_vis_routes_apply(qapp):
    rec = _dxf_record()
    scene, model = _make_model([rec])
    idx = model.index(0, int(Col.VIS), QModelIndex())
    assert model.setData(idx, False, Qt.ItemDataRole.EditRole) is True
    assert rec.visible is False
    assert scene.apply_calls >= 1


def test_setdata_layer_colour_override(qapp):
    rec = _dxf_record()
    scene, model = _make_model([rec])
    parent = model.index(0, 0, QModelIndex())
    child = model.index(0, int(Col.COLOUR), parent)
    assert model.setData(child, "#00ff00", Qt.ItemDataRole.EditRole) is True
    assert rec.layer_overrides["WALLS"]["colour"] == "#00ff00"
    assert rec in scene.repen_calls


def test_setdata_layer_vis_toggles(qapp):
    rec = _dxf_record()
    scene, model = _make_model([rec])
    parent = model.index(0, 0, QModelIndex())
    child = model.index(0, int(Col.VIS), parent)
    assert model.setData(child, True, Qt.ItemDataRole.EditRole) is True
    assert "WALLS" in rec.hidden_layers
    assert scene.layer_hidden_calls  # routed through the choke point


def test_parent_maps_layer_to_underlay(qapp):
    rec = _dxf_record()
    _scene, model = _make_model([rec])
    parent = model.index(0, 0, QModelIndex())
    child = model.index(1, 0, parent)  # GRID
    assert child.isValid()
    back = model.parent(child)
    assert back.isValid()
    assert back.row() == 0
    from firepro3d.underlay_manager_model import UnderlayRole
    assert model.data(back, UnderlayRole) is rec


def test_layer_name_display(qapp):
    rec = _dxf_record()
    _scene, model = _make_model([rec])
    parent = model.index(0, 0, QModelIndex())
    child = model.index(0, int(Col.NAME), parent)
    assert model.data(child, Qt.ItemDataRole.DisplayRole) == "WALLS"


def test_underlaysChanged_resets(qapp):
    rec = _dxf_record()
    scene, model = _make_model([rec])
    assert model.rowCount(QModelIndex()) == 1
    scene.underlays.append((_dxf_record(), object()))
    scene.underlaysChanged.emit()
    assert model.rowCount(QModelIndex()) == 2
