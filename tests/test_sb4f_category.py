"""SB4f AC1: the View Title category, its three keys, the shipped seed and the
PaperScene forwarder."""
import json

import pytest
from PyQt6.QtCore import QRectF

from tests._sb4d_helpers import dispose, plan_scene
from tests._sb4f_helpers import place


def test_registries(qapp):
    from firepro3d import element_params as ep
    from firepro3d import system_blocks as sb
    assert ep.CATEGORIES[-1] == "View Title"
    assert [(k, s.tier, s.kind) for k, s in ep.PARAMS["View Title"].items()] == [
        ("Number", 1, "text"), ("Title", 1, "text"), ("Scale", 1, "text")]
    assert sb.ANNOTATION_CATEGORIES[-1] == "View Title"
    assert sb.LABEL_FIELD["View Title"] == "Scale"
    assert sb.SYSTEM_DEFAULTS["View Title"] == "system-tags-viewtitle"
    assert "View Title" not in sb.PAINT_WHEN_BLANK


def test_shipped_seed(qapp):
    from firepro3d import block_library
    from firepro3d.assets import system_blocks_path
    from firepro3d.bound_label import eligible_definition
    from firepro3d.render_op import STROKE
    path = system_blocks_path("Tags", "ViewTitle.fpdb")
    d = block_library.load_block_file(path)
    assert d is not None and d.id == "system-tags-viewtitle"
    assert eligible_definition(d, "View Title")
    assert [a["host_key"] for a in d.effective_attributes()
            if a.get("source") == "host"] == ["Number", "Title", "Scale"]
    strokes = [o.path.boundingRect() for o in d.render_ops() if o.kind == STROKE]
    assert any(abs(b.width() - 6.0) < 1e-6 and abs(b.height() - 6.0) < 1e-6 for b in strokes)
    with open(path, encoding="utf-8") as fh:
        texts = {p["text"]: p for p in json.load(fh)["primitives"] if p["type"] == "text"}
    assert texts["@[Number]"]["height_mm"] == 2.0 and texts["@[Number]"]["bold"]
    assert texts["@[Title]"]["height_mm"] == 2.2 and texts["@[Title]"]["bold"]
    assert texts["@[Scale]"]["height_mm"] == 1.6 and texts["@[Scale]"]["color"] == "#444444"


@pytest.mark.parametrize("scale", [0.0, 0.01])
def test_viewport_values(qapp, scale):
    from firepro3d import element_params as ep
    from firepro3d.paper_space import float_to_scale_str
    ms, sec, det, tabs = plan_scene()
    try:
        _view, _ps, vp = place(ms, sec, det, "detail", view_number="7")
        vp.data.scale = scale
        vp.data.title = "Level One"              # as typed, never upper-cased (G6)
        assert ep.category_of(vp) == "View Title"
        hv = ep.host_values(vp)
        assert hv["Number"].text == "7"
        assert hv["Title"].text == "Level One"
        assert hv["Scale"].text == ("NTS" if scale == 0.0 else float_to_scale_str(scale))
    finally:
        dispose(ms, sec, tabs)


def test_paper_scene_forwards_to_the_model_resolver(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    try:
        _view, ps, _vp = place(ms, sec, det)
        d = ps.annotation_block("View Title")
        assert d is not None and d.id == "system-tags-viewtitle"
    finally:
        dispose(ms, sec, tabs)


def test_paper_scene_without_a_model_answers_none(qapp):
    from unittest.mock import MagicMock
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    ps = PaperScene(Sheet.create_default(), MagicMock(spec=ViewResolver))
    assert ps.annotation_block("View Title") is None


def test_orphan_box_is_paper_sized(qapp):
    from firepro3d.bound_label import BoundLabelItem, PLACEHOLDER_MM
    assert BoundLabelItem.placeholder_mm == PLACEHOLDER_MM == 200.0
