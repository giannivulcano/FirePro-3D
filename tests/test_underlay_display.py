"""Display management & view assignment (spec §16) — pens, visibility, DM tab."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGraphicsPathItem

from firepro3d import paper_display as pd
from firepro3d.constants import UNDERLAY_LINE_WIDTH_PX, UNDERLAY_MM_TO_PX_HINT
from firepro3d.model_space import Model_Space, underlay_layer_pen
from firepro3d.underlay import Underlay


@pytest.fixture(autouse=True)
def _factory_line_weights(monkeypatch):
    """Isolate weight-dependent tests from live QSettings (paper/line_weights).

    underlay_layer_pen -> resolve_line_weight_mm -> load_line_weights reads the
    developer's real QSettings; pin the module global to factory defaults
    (same idiom as tests/test_gridline_paper_scale.py::paper_env).
    """
    monkeypatch.setattr(pd, "load_line_weights",
                        lambda settings=None: list(pd.FACTORY_LINE_WEIGHTS))


def _geoms(layers=("A-WALL", "A-DOOR")):
    """Minimal stroked geometry dicts, one line per layer."""
    return [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100,
             "layer": ln} for ln in layers]


def _record(**kw):
    kw.setdefault("type", "dxf")
    kw.setdefault("path", "x.dxf")
    return Underlay(**kw)


class TestUnderlayLayerPen:
    def test_default_matches_today(self, qapp):
        pen = underlay_layer_pen(_record(), "A-WALL")
        assert pen.isCosmetic()
        assert pen.widthF() == pytest.approx(UNDERLAY_LINE_WIDTH_PX)
        assert pen.color().name() == "#c0c0c0"

    def test_layer_colour_override(self, qapp):
        rec = _record(layer_overrides={"A-WALL": {"colour": "#ff0000"}})
        assert underlay_layer_pen(rec, "A-WALL").color().name() == "#ff0000"
        assert underlay_layer_pen(rec, "A-DOOR").color().name() == "#c0c0c0"

    def test_named_weight_hint_width(self, qapp):
        # "Medium" is a factory weight = 0.25mm -> 0.25 * 6.0 = 1.5px
        rec = _record(line_weight_name="Medium")
        pen = underlay_layer_pen(rec, "A-WALL")
        assert pen.isCosmetic()  # NEVER zoom-scales (spec §3.4 invariant)
        assert pen.widthF() == pytest.approx(0.25 * UNDERLAY_MM_TO_PX_HINT)


class TestBuilderPerLayerPens:
    def test_builder_uses_per_layer_pens(self, qapp):
        scene = Model_Space()
        rec = _record(layer_overrides={"A-WALL": {"colour": "#ff0000"}})
        group, layers = scene._build_batched_underlay_group(_geoms(), rec)
        assert sorted(layers) == ["A-DOOR", "A-WALL"]
        by_layer = {c.data(1): c for c in group.childItems()
                    if isinstance(c, QGraphicsPathItem)}
        assert by_layer["A-WALL"].pen().color().name() == "#ff0000"
        assert by_layer["A-DOOR"].pen().color().name() == "#c0c0c0"
        for c in by_layer.values():
            assert c.pen().isCosmetic()


class TestPdfRecordColourSeam:
    """Reloaded PDF vector underlays must keep today's gray pen (§16.2 D4).

    PDF records don't serialize ``colour`` (to_dict omits it), so from_dict
    must default PDFs to the dataclass default "#c0c0c0" — the colour the
    PDF vector path always rendered with — not the DXF legacy "#ffffff".
    """

    def test_pdf_from_dict_colour_defaults_to_gray(self):
        u = Underlay.from_dict({"type": "pdf", "path": "plans/sheet.pdf"})
        assert u.colour == "#c0c0c0"

    def test_dxf_from_dict_colour_keeps_legacy_white(self):
        u = Underlay.from_dict({"type": "dxf", "path": "old.dxf"})
        assert u.colour == "#ffffff"


class TestRepenUnderlay:
    def test_repen_swaps_pens_in_place(self, qapp):
        scene = Model_Space()
        rec = _record()
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))
        child = next(c for c in group.childItems()
                     if c.data(1) == "A-WALL")
        assert child.pen().color().name() == "#c0c0c0"
        rec.layer_overrides["A-WALL"] = {"colour": "#00ff00"}
        scene.repen_underlay(rec)
        # same item object, new pen — no rebuild
        assert child.pen().color().name() == "#00ff00"

    def test_repen_applies_opacity(self, qapp):
        scene = Model_Space()
        rec = _record(opacity=0.4)
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))
        scene.repen_underlay(rec)
        assert group.opacity() == pytest.approx(0.4)


class TestLayerHiddenChokePoint:
    def test_hide_and_show_layer(self, qapp):
        scene = Model_Space()
        rec = _record()
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        scene.underlays.append((rec, group))
        fired = []
        scene.underlaysChanged.connect(lambda: fired.append(1))
        scene.set_underlay_layer_hidden(rec, group, "A-WALL", True)
        assert "A-WALL" in rec.hidden_layers
        assert all(not c.isVisible() for c in group.childItems()
                   if c.data(1) == "A-WALL")
        scene.set_underlay_layer_hidden(rec, group, "A-WALL", False)
        assert "A-WALL" not in rec.hidden_layers
        assert all(c.isVisible() for c in group.childItems()
                   if c.data(1) == "A-WALL")
        assert len(fired) == 2

    def test_noop_does_not_emit(self, qapp):
        scene = Model_Space()
        rec = _record()
        group, _ = scene._build_batched_underlay_group(_geoms(), rec)
        fired = []
        scene.underlaysChanged.connect(lambda: fired.append(1))
        scene.set_underlay_layer_hidden(rec, group, "A-WALL", False)  # already shown
        assert fired == []
