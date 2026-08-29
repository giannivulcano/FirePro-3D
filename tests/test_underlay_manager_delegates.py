"""Tests for the Underlay Manager per-column delegates (Task 9b).

Focus:
  * paint() does not crash on BOTH an underlay index and a layer index for
    every delegate (rendered onto a real QPixmap via QPainter with a real
    QStyleOptionViewItem).
  * A raster-PDF underlay row paints blank (no crash) for colour/weight/snap.
  * editorEvent routing for ToggleDelegate("visible") flips visibility on both
    an underlay row and a layer row (through the real model so setData routes).

Modal editorEvents (colour dialog, weight menu, levels keep-open menu) are NOT
driven here — Task 18 smoke covers those.  We do exercise their paint paths.
"""
from PyQt6.QtCore import QEvent, QModelIndex, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QGraphicsPixmapItem, QStyleOptionViewItem

from firepro3d.underlay import Underlay
from firepro3d.theme import DARK
from firepro3d.underlay_manager_model import UnderlayTreeModel, Col
from firepro3d.underlay_manager_delegates import (
    ToggleDelegate,
    ColourDelegate,
    WeightDelegate,
    LevelsDelegate,
)


# --------------------------------------------------------------------------
# Fakes (mirrors tests/test_underlay_manager_model.py)
# --------------------------------------------------------------------------
class _FakeGroup:
    def __init__(self, layers=None):
        self._layers = layers or []

    def data(self, idx):
        return self._layers if idx == 2 else None

    def childItems(self):
        return []


from PyQt6.QtCore import QObject, pyqtSignal


class _FakeScene(QObject):
    underlaysChanged = pyqtSignal()

    def __init__(self, underlays):
        super().__init__()
        self.underlays = underlays
        self.active_level = "L1"
        self.repen_calls = []
        self.apply_calls = 0
        _outer = self

        class _LM:
            def apply_to_scene(_s, _scene, _active=None):
                _outer.apply_calls += 1

        self.level_mgr = _LM()

    def repen_underlay(self, rec):
        self.repen_calls.append(rec)

    def set_underlay_layer_hidden(self, rec, group, layer, hidden):
        if hidden and layer not in rec.hidden_layers:
            rec.hidden_layers.append(layer)
        elif not hidden and layer in rec.hidden_layers:
            rec.hidden_layers.remove(layer)


def _dxf_record():
    return Underlay(type="dxf", path="/tmp/p.dxf", levels=["L1"], colour="#111111")


def _dxf_model():
    rec = _dxf_record()
    scene = _FakeScene([(rec, _FakeGroup(["GRID", "WALLS"]))])
    model = UnderlayTreeModel(scene, DARK, lambda: ["L1", "L2"])
    return rec, scene, model


def _raster_pdf_model():
    rec = Underlay(type="pdf", path="/tmp/p.pdf", levels=["L1"])
    scene = _FakeScene([(rec, QGraphicsPixmapItem())])
    model = UnderlayTreeModel(scene, DARK, lambda: ["L1", "L2"])
    return rec, scene, model


def _option():
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 120, 34)
    return opt


def _paint(delegate, index):
    """Render a delegate onto a real pixmap. Returns True on no-crash."""
    pm = QPixmap(120, 34)
    pm.fill()
    painter = QPainter(pm)
    opt = _option()
    delegate.paint(painter, opt, index)
    painter.end()
    return True


def _release_event(option):
    pt = QPointF(option.rect.center())
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pt,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


# --------------------------------------------------------------------------
# paint: no crash on both row kinds
# --------------------------------------------------------------------------
def _both_indices(model):
    top = model.index(0, 0, QModelIndex())
    child = model.index(0, 0, top)  # "GRID"
    return top, child


def test_toggle_visible_paint_both_kinds(qapp):
    _rec, _scene, model = _dxf_model()
    d = ToggleDelegate(DARK, "visible")
    top = model.index(0, int(Col.VIS), QModelIndex())
    child = model.index(0, int(Col.VIS), model.index(0, 0, QModelIndex()))
    assert _paint(d, top)
    assert _paint(d, child)


def test_toggle_snap_paint_both_kinds(qapp):
    _rec, _scene, model = _dxf_model()
    d = ToggleDelegate(DARK, "snap")
    top = model.index(0, int(Col.SNAP), QModelIndex())
    child = model.index(0, int(Col.SNAP), model.index(0, 0, QModelIndex()))
    assert _paint(d, top)
    assert _paint(d, child)


def test_colour_paint_both_kinds(qapp):
    _rec, _scene, model = _dxf_model()
    d = ColourDelegate(DARK)
    top = model.index(0, int(Col.COLOUR), QModelIndex())
    child = model.index(0, int(Col.COLOUR), model.index(0, 0, QModelIndex()))
    assert _paint(d, top)
    assert _paint(d, child)


def test_weight_paint_both_kinds(qapp):
    _rec, _scene, model = _dxf_model()
    d = WeightDelegate(DARK)
    top = model.index(0, int(Col.WEIGHT), QModelIndex())
    child = model.index(0, int(Col.WEIGHT), model.index(0, 0, QModelIndex()))
    assert _paint(d, top)
    assert _paint(d, child)


def test_levels_paint_both_kinds(qapp):
    _rec, _scene, model = _dxf_model()
    d = LevelsDelegate(DARK, lambda: ["L1", "L2"])
    top = model.index(0, int(Col.LEVELS), QModelIndex())
    child = model.index(0, int(Col.LEVELS), model.index(0, 0, QModelIndex()))
    assert _paint(d, top)
    assert _paint(d, child)


def test_levels_paint_all_levels_chip(qapp):
    rec = _dxf_record()
    rec.levels = ["*"]
    scene = _FakeScene([(rec, _FakeGroup(["GRID"]))])
    model = UnderlayTreeModel(scene, DARK, lambda: ["L1", "L2"])
    d = LevelsDelegate(DARK, lambda: ["L1", "L2"])
    top = model.index(0, int(Col.LEVELS), QModelIndex())
    assert _paint(d, top)


def test_levels_paint_no_levels_chip(qapp):
    rec = _dxf_record()
    rec.levels = []
    scene = _FakeScene([(rec, _FakeGroup(["GRID"]))])
    model = UnderlayTreeModel(scene, DARK, lambda: ["L1", "L2"])
    d = LevelsDelegate(DARK, lambda: ["L1", "L2"])
    top = model.index(0, int(Col.LEVELS), QModelIndex())
    assert _paint(d, top)


# --------------------------------------------------------------------------
# raster-PDF underlay row paints blank (no crash) for colour/weight/snap
# --------------------------------------------------------------------------
def test_raster_pdf_colour_paints_blank(qapp):
    _rec, _scene, model = _raster_pdf_model()
    top = model.index(0, int(Col.COLOUR), QModelIndex())
    assert _paint(ColourDelegate(DARK), top)


def test_raster_pdf_weight_paints_blank(qapp):
    _rec, _scene, model = _raster_pdf_model()
    top = model.index(0, int(Col.WEIGHT), QModelIndex())
    assert _paint(WeightDelegate(DARK), top)


def test_raster_pdf_snap_paints_blank(qapp):
    _rec, _scene, model = _raster_pdf_model()
    top = model.index(0, int(Col.SNAP), QModelIndex())
    assert _paint(ToggleDelegate(DARK, "snap"), top)


# --------------------------------------------------------------------------
# editorEvent routing: ToggleDelegate("visible") on both row kinds
# --------------------------------------------------------------------------
def test_toggle_visible_editor_underlay(qapp):
    rec, _scene, model = _dxf_model()
    assert rec.visible is True
    d = ToggleDelegate(DARK, "visible")
    idx = model.index(0, int(Col.VIS), QModelIndex())
    opt = _option()
    handled = d.editorEvent(_release_event(opt), model, opt, idx)
    assert handled is True
    assert rec.visible is False


def test_toggle_visible_editor_layer(qapp):
    rec, _scene, model = _dxf_model()
    parent = model.index(0, 0, QModelIndex())
    idx = model.index(0, int(Col.VIS), parent)  # "GRID"
    assert "GRID" not in rec.hidden_layers
    d = ToggleDelegate(DARK, "visible")
    opt = _option()
    handled = d.editorEvent(_release_event(opt), model, opt, idx)
    assert handled is True
    assert "GRID" in rec.hidden_layers  # now hidden


def test_toggle_snap_editor_underlay(qapp):
    rec, _scene, model = _dxf_model()
    assert rec.snap is True
    d = ToggleDelegate(DARK, "snap")
    idx = model.index(0, int(Col.SNAP), QModelIndex())
    opt = _option()
    handled = d.editorEvent(_release_event(opt), model, opt, idx)
    assert handled is True
    assert rec.snap is False


def test_toggle_snap_editor_layer_ignored(qapp):
    # Snap does not apply to layer rows -> editorEvent returns False, no change.
    rec, _scene, model = _dxf_model()
    parent = model.index(0, 0, QModelIndex())
    idx = model.index(0, int(Col.SNAP), parent)
    d = ToggleDelegate(DARK, "snap")
    opt = _option()
    handled = d.editorEvent(_release_event(opt), model, opt, idx)
    assert handled is False
    assert rec.snap is True


def test_toggle_snap_editor_raster_ignored(qapp):
    # Snap on a raster-PDF underlay row is not editable -> returns False.
    rec, _scene, model = _raster_pdf_model()
    idx = model.index(0, int(Col.SNAP), QModelIndex())
    d = ToggleDelegate(DARK, "snap")
    opt = _option()
    handled = d.editorEvent(_release_event(opt), model, opt, idx)
    assert handled is False


def test_colour_editor_raster_ignored(qapp):
    # A raster-PDF underlay row is not editable -> editorEvent returns False
    # WITHOUT opening the modal QColorDialog.
    rec, _scene, model = _raster_pdf_model()
    idx = model.index(0, int(Col.COLOUR), QModelIndex())
    d = ColourDelegate(DARK)
    opt = _option()
    handled = d.editorEvent(_release_event(opt), model, opt, idx)
    assert handled is False


def test_weight_editor_raster_ignored(qapp):
    rec, _scene, model = _raster_pdf_model()
    idx = model.index(0, int(Col.WEIGHT), QModelIndex())
    d = WeightDelegate(DARK)
    opt = _option()
    handled = d.editorEvent(_release_event(opt), model, opt, idx)
    assert handled is False


def test_levels_editor_layer_ignored(qapp):
    # Levels apply to underlay rows only -> layer row returns False.
    rec, _scene, model = _dxf_model()
    parent = model.index(0, 0, QModelIndex())
    idx = model.index(0, int(Col.LEVELS), parent)
    d = LevelsDelegate(DARK, lambda: ["L1", "L2"])
    opt = _option()
    handled = d.editorEvent(_release_event(opt), model, opt, idx)
    assert handled is False
