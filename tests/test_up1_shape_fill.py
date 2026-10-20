"""UP1 shape two-layer fill guards G2 (end-to-end), G4-G9 + R10 / D2."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QGraphicsScene

from firepro3d import colour_picker
from firepro3d.fill_layers import (NO_LAYER, BackgroundLayer, FillLayers,
                                   PatternLayer)
from firepro3d.geometry_2d import RectangleItem


def _render(scene, src=QRectF(0, 0, 120, 120), size=120) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), src)
    p.end()
    return img


def _interior(img, lo=30, hi=90, step=2):
    return [QColor(img.pixel(x, y)) for y in range(lo, hi, step) for x in range(lo, hi, step)]


@pytest.fixture(autouse=True)
def _collect_qt_garbage():
    """Collect each test's unparented panels/scenes at teardown, between
    tests. Left to the cyclic GC, they were collected inside a later test's
    processEvents (a Model_View build) and killed the process (0xC0000409;
    reproduced at aeab43ff). No processEvents here: that is the hazard."""
    import gc
    yield
    gc.collect()


def _rect():
    return RectangleItem(QPointF(10, 10), QPointF(110, 110))


def _ms_with_hatches(shipped_hatches):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    shipped_hatches(ms)
    return ms


# G4 / R8: a new closed shape paints nothing inside; rows default to none.
def test_new_shape_has_no_fill_and_two_none_rows(qapp):
    r = _rect()
    sc = QGraphicsScene(); sc.addItem(r)
    assert r.fill_layers.is_empty and not r._draws_fill()
    assert all(c.rgb() == QColor("white").rgb() for c in _interior(_render(sc)))
    props = r.get_properties()
    assert props["Fill"]["type"] == "fill" and props["Fill"]["value"] is None
    assert props["Fill Pattern"]["pattern"] is True and props["Fill Pattern"]["value"] is None
    for old in ("Fill Colour", "Fill Opacity", "Pattern"):
        assert old not in props                                     # H8 rows retired


# AC3: both layers in one paint, each at its own opacity.
def test_background_and_pattern_paint_together(qapp, shipped_hatches):
    ms = _ms_with_hatches(shipped_hatches)
    r = _rect(); ms.addItem(r)
    r.set_property("Fill", BackgroundLayer("#0000ff", 1.0))
    # scale 0.1: the diagonal tile is a 424 mm drafting cell at scale 1.0,
    # wider than this 100 mm rect, so only a reduced scale puts lines inside.
    r.set_property("Fill Pattern", PatternLayer("builtin-hatch-diagonal", "#00ff00", 1.0, 0.1))
    px = _interior(_render(ms))
    assert any(c.blue() > 200 and c.green() < 60 for c in px)       # background
    # Pattern lines are antialiased onto the blue ground: a line pixel is
    # greener than it is blue; a background-only fill has none.
    assert any(c.green() > c.blue() for c in px)


# G5 / R13: the override Fill colour recolours both layers.
def test_override_fill_recolours_both_layers(qapp, shipped_hatches):
    ms = _ms_with_hatches(shipped_hatches)
    r = _rect(); ms.addItem(r)
    r.fill_layers = FillLayers(BackgroundLayer("#0000ff", 1.0),
                               PatternLayer("builtin-hatch-diagonal", "#00ff00", 1.0, 0.1))
    r._display_overrides = {"fill": "#ff0000"}
    px = _interior(_render(ms))
    assert not any(c.green() > 150 for c in px)                    # no green pattern left
    assert not any(c.blue() > 150 for c in px)                     # no blue background left
    assert all(c.red() > 200 for c in px)


def test_override_no_fill_hides_both_layers(qapp):
    r = _rect()
    r.fill_layers = FillLayers(BackgroundLayer("#0000ff", 1.0), PatternLayer("x"))
    r._display_overrides = {"fill": ""}
    assert not r._draws_fill()


# G6 / R14: pattern-only interior is a HALO area; no-fill is edge only.
@pytest.mark.parametrize("layers, hit", [
    (FillLayers(pattern=PatternLayer("builtin-hatch-diagonal")), True),
    (FillLayers(background=BackgroundLayer("#888888")), True),
    (FillLayers(), False),
])
def test_halo_interior_pick_follows_any_layer(qapp, layers, hit):
    from tests._snap_polish_helpers import close_view, make_view, move
    view, scene = make_view(role="plan", scale=1.0, mode="select")
    try:
        r = RectangleItem(QPointF(0, 0), QPointF(200, 200))
        r.fill_layers = layers
        scene.addItem(r)
        move(view, QPointF(100, 100))
        assert (scene.halo_item() is r) is hit
    finally:
        close_view(view, scene)


# G7: to_dict / from_dict, copy and undo/redo preserve both layers.
def test_round_trip_copy_and_undo_preserve_both_layers(qapp):
    from firepro3d.model_space import Model_Space
    both = FillLayers(BackgroundLayer("#3366cc", 0.3),
                      PatternLayer("builtin-hatch-diagonal", "token:auto", 0.7, 2.0))
    r = _rect(); r.fill_layers = both
    d = r.to_dict()
    assert RectangleItem.from_dict(d).fill_layers == both
    ms = Model_Space()
    ms._add_from_dict(dict(d, fill=None))          # copy path, unfilled
    ms.push_undo_state()
    item = ms._draw_rects[-1]
    with ms.deferred_undo_push():
        item.set_property("Fill", both.background)
        item.set_property("Fill Pattern", both.pattern)
    assert ms._draw_rects[-1].fill_layers == both
    ms.undo()
    assert ms._draw_rects[-1].fill_layers.is_empty
    ms.redo()
    assert ms._draw_rects[-1].fill_layers == both
    ms._add_from_dict(ms._draw_rects[-1].to_dict())              # Paste / Duplicate
    assert ms._draw_rects[-1].fill_layers == both


def test_no_op_layer_write_pushes_no_undo_step(qapp):
    from firepro3d.model_space import Model_Space
    ms = Model_Space()
    ms._add_from_dict(_rect().to_dict())
    ms.push_undo_state()
    item = ms._draw_rects[-1]
    before = ms._undo_pos
    item.set_property("Fill", NO_LAYER)                           # already off
    assert ms._undo_pos == before


# m7: FillSwatch._pick emits layerChanged even when the picked layer equals the
# current one; the setters must absorb that (_dim_edit: an equal write is no step).
def test_equal_layer_rewrite_pushes_no_second_undo_step(qapp, shipped_hatches):
    ms = _ms_with_hatches(shipped_hatches)
    ms._add_from_dict(_rect().to_dict())
    ms.push_undo_state()
    item = ms._draw_rects[-1]
    bg = BackgroundLayer("#3366cc", 0.5)
    pat = PatternLayer("builtin-hatch-diagonal", "#ff0000", 0.5, 2.0)
    p0 = ms._undo_pos
    item.set_property("Fill", bg)
    p1 = ms._undo_pos
    assert p1 == p0 + 1                                           # the first write is a step
    item.set_property("Fill", BackgroundLayer("#3366cc", 0.5))    # equal, new object
    assert ms._undo_pos == p1
    item.set_property("Fill Pattern", pat)
    p2 = ms._undo_pos
    assert p2 == p1 + 1
    item.set_property("Fill Pattern", PatternLayer("builtin-hatch-diagonal", "#ff0000", 0.5, 2.0))
    assert ms._undo_pos == p2


# G2 end-to-end: real panel swatch click -> real dialog widgets -> shape layers.
def test_panel_fill_pattern_swatch_drives_dialog_to_shape(qapp, monkeypatch, shipped_hatches):
    from firepro3d.property_manager import PropertyManager
    from firepro3d.ui_kit import FillSwatch
    ms = _ms_with_hatches(shipped_hatches)
    r = _rect(); ms.addItem(r)
    pm = PropertyManager(); pm.show_properties(r)
    sw = next(s for s in pm.findChildren(FillSwatch) if s._context == "Fill Pattern")
    seen = {}
    def _exec(self):
        self.show()
        chip = self._pattern_chips[1]
        seen["ref"] = chip.value
        QTest.mouseClick(chip, Qt.MouseButton.LeftButton)
        self._opacity.setValue(60)
        self._scale.setText("2")
        self.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(colour_picker.ColourPickerDialog, "exec", _exec)
    QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    assert r.fill_layers.pattern == PatternLayer(seen["ref"], "token:auto", 0.6, 2.0)  # D2
    assert r.fill_layers.background is None


# R10: a layer created by the UI starts at 100 %.
def test_new_background_from_picker_starts_opaque(qapp, monkeypatch):
    from firepro3d.property_manager import PropertyManager
    from firepro3d.ui_kit import FillSwatch
    sc = QGraphicsScene(); r = _rect(); sc.addItem(r)
    pm = PropertyManager(); pm.show_properties(r)
    sw = next(s for s in pm.findChildren(FillSwatch) if s._context == "Fill")
    def _exec(self):
        self._set_colour(QColor("#00ff00"))
        self.accept()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(colour_picker.ColourPickerDialog, "exec", _exec)
    QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    assert r.fill_layers.background == BackgroundLayer("#00ff00", 1.0)


# G8: multi-select apply of Fill Pattern writes every shape.
def test_multi_select_fill_pattern_writes_every_shape(qapp, monkeypatch):
    from firepro3d.property_manager import PropertyManager
    from firepro3d.ui_kit import FillSwatch
    sc = QGraphicsScene(); a, b = _rect(), _rect(); sc.addItem(a); sc.addItem(b)
    pm = PropertyManager(); pm.show_properties([a, b])
    new = PatternLayer("builtin-hatch-diagonal", "#ff0000", 0.5, 1.5)
    monkeypatch.setattr(colour_picker, "pick_fill", lambda *x, **k: new)
    sw = next(s for s in pm.findChildren(FillSwatch) if s._context == "Fill Pattern")
    QTest.mouseClick(sw._chip, Qt.MouseButton.LeftButton)
    assert a.fill_layers.pattern == new and b.fill_layers.pattern == new


def _fill_pattern_action(path, ms, r):
    """The "Fill Pattern…" action for *r* from the entity (A) or plan (B) menu;
    returns (menu, action) — keep *menu* alive, it owns the action."""
    r.setSelected(True)
    if path == "entity":
        menu = ms._build_entity_context_menu(r)
    else:
        from PyQt6.QtWidgets import QApplication
        from firepro3d.model_view import Model_View
        view = Model_View(ms); QApplication.processEvents()
        menu = view._build_plan_context_menu(ms, ms.selectedItems(), "select")
        menu._keep_view = view
    return menu, next(a for a in menu.actions() if a.text() == "Fill Pattern…")


# A refused library load (D-A37) leaves the shape unfilled through both menus.
@pytest.mark.parametrize("path", ["entity", "view"])
def test_refused_library_load_leaves_menu_pick_unfilled(qapp, monkeypatch, tmp_path, path):
    from PyQt6.QtCore import QSettings
    from firepro3d import app_data, block_library as bl, hatch_patterns
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_space import Model_Space
    # One pattern in the Hatch patterns folder, none in the project: library-only.
    root = tmp_path / "patterns_root"; root.mkdir()
    QSettings("GV", "FirePro3D").setValue(app_data.HATCH_DIR_KEY, str(root))
    bl.save_to_library(BlockDefinition.new(
        name="Zig", library="System", series="Hatches", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"}), root=str(root))
    ms = Model_Space()
    r = _rect(); ms.addItem(r)
    assert r.fill_layers.is_empty
    monkeypatch.setattr(hatch_patterns, "ensure_pattern_available", lambda *a, **k: False)
    zig = next(bid for n, bid, _p in hatch_patterns.library_patterns() if n == "Zig")
    monkeypatch.setattr(colour_picker, "pick_fill", lambda *a, **k: PatternLayer(zig))
    menu, act = _fill_pattern_action(path, ms, r)
    act.trigger()
    assert r.fill_layers.is_empty, r.fill_layers


# Programmatic set_property bypasses PatternLayer's own scale check: the paint
# sanitises a bad scale to 1.0.
@pytest.mark.parametrize("bad", [0.0, float("nan"), -1.0])
def test_bad_pattern_scale_paints_like_scale_one(qapp, shipped_hatches, bad):
    def render_with(scale):
        ms = _ms_with_hatches(shipped_hatches)
        r = _rect(); ms.addItem(r)
        r.set_property("Fill Pattern", PatternLayer("builtin-hatch-diagonal", "#00ff00", 1.0, scale))
        return _render(ms)
    assert render_with(bad) == render_with(1.0)


# Absence of "fill" in a record means empty (to_dict omits empty fills).
def test_from_dict_without_fill_key_clears_layers(qapp):
    r = _rect()
    r.fill_layers = FillLayers(BackgroundLayer("#0000ff"), PatternLayer("builtin-hatch-diagonal"))
    d = r.to_dict()
    d.pop("fill")
    r._geom2d_from_dict(d)
    assert r.fill_layers.is_empty


def test_reference_shape_keeps_layers_but_hides_rows_and_paint(qapp):
    r = _rect()
    r.fill_layers = FillLayers(BackgroundLayer("#0000ff"))
    r.reference = True
    assert not r._draws_fill()
    assert "Fill" not in r.get_properties() and "Fill Pattern" not in r.get_properties()
    assert r.to_dict()["fill"] == {"background": {"color": "#0000ff", "opacity": 1.0}}


# S-M4: a shape's pattern layer keeps its (library-only) ref in the project's
# pattern set, so a save carries the tile.
def test_shape_pattern_ref_is_collected_by_project_pattern_refs(qapp):
    from firepro3d import hatch_patterns
    from firepro3d.model_space import Model_Space
    ref = "library-only-zig"
    assert ref != hatch_patterns.DEFAULT_TILE_REF
    ms = Model_Space()
    r = _rect(); ms.addItem(r)
    r.fill_layers = FillLayers(None, PatternLayer(ref))
    assert ref in hatch_patterns.project_pattern_refs(ms)


# S-M7: a background + pattern record paints the same pixels as a loose shape
# and as a block-instance primitive (the two paint paths share the record).
def test_background_and_pattern_loose_matches_block_instance(qapp, shipped_hatches):
    from firepro3d.block_definition import BlockDefinition
    from tests.test_up1_legacy_fill_golden import (
        _INNER, _POS, _RECT, _SPAN, _render as _g_render, _scene)
    prim = dict(_RECT)
    prim["fill"] = {"background": {"color": "#3366cc", "opacity": 0.5},
                    "pattern": {"ref": "builtin-hatch-diagonal", "color": "#cc3333",
                                "opacity": 0.5, "scale": 0.5}}
    # Non-default pattern opacity and scale: a block compile that dropped the
    # PATTERN op's alpha or scale (RenderOp defaults 255 / 1.0) must show.
    loose_item = RectangleItem.from_dict(prim)
    assert not loose_item.fill_layers.is_empty
    assert loose_item.fill_layers.background is not None
    assert loose_item.fill_layers.pattern is not None
    ms = _scene(qapp, shipped_hatches)
    ms.addItem(loose_item)
    loose = _g_render(ms, QRectF(0, 0, _SPAN, _SPAN))

    ms2 = _scene(qapp, shipped_hatches)
    d = BlockDefinition.new(name="Parity", library="L", series="S",
                            origin=(0.0, 0.0), primitives=[loose_item.to_dict()])
    ms2.register_block_definition(d)
    ms2.place_block_instance(d.id, _POS)
    block = _g_render(ms2, QRectF(_POS[0], _POS[1], _SPAN, _SPAN))

    white = QColor("white").rgba()
    inked = sum(1 for y in _INNER for x in _INNER if loose.pixel(x, y) != white)
    assert inked == len(_INNER) ** 2, "background layer did not paint"
    assert len({loose.pixel(x, y) for y in _INNER for x in _INNER}) > 1, "no pattern over the background"
    assert loose == block

    # The non-default values must change the render, or the parity above
    # would not prove the block path carries them.
    plain = dict(_RECT)
    plain["fill"] = {"background": {"color": "#3366cc", "opacity": 0.5},
                     "pattern": {"ref": "builtin-hatch-diagonal", "color": "#cc3333",
                                 "opacity": 1.0, "scale": 1.0}}
    ms3 = _scene(qapp, shipped_hatches)
    ms3.addItem(RectangleItem.from_dict(plain))
    assert _g_render(ms3, QRectF(0, 0, _SPAN, _SPAN)) != loose
