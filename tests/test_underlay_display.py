"""Display management & view assignment (spec §16) — pens, visibility, DM tab."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QGraphicsPathItem

from firepro3d.constants import UNDERLAY_LINE_WIDTH_PX, UNDERLAY_MM_TO_PX_HINT
from firepro3d.model_space import Model_Space, underlay_layer_pen
from firepro3d.underlay import Underlay


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
