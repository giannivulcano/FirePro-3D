"""SB1a: definition schema fields + compile split (design S1/S2)."""
from PyQt6.QtGui import QTransform

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_attributes import normalise_attr


def _text(text, x=0.0, y=0.0, angle=0.0, **kw):
    d = {"type": "text", "text": text, "x": x, "y": y, "height_mm": 3.0, "angle": angle}
    d.update(kw)
    return d


def _attr(key, **kw):
    return normalise_attr({"key": key, **kw})


def test_definition_fields_round_trip():
    d = BlockDefinition.new(name="t", library="", series="",
                            primitives=[_text("@[Mark]")], origin=(0.0, 0.0))
    assert d.host_category == "" and d.scale_mode == "real_size"
    d.attributes = [_attr("Mark", default="A1")]
    d.host_category = "Rooms"
    d.scale_mode = "annotative"
    back = BlockDefinition.from_dict(d.to_dict())
    assert back.attributes == [_attr("Mark", default="A1")]
    assert back.host_category == "Rooms"
    assert back.scale_mode == "annotative"
    # absent keys => empty / defaults (no schema bump)
    legacy = BlockDefinition.from_dict({"id": "x", "primitives": []})
    assert legacy.attributes == [] and legacy.host_category == ""


def test_effective_attributes_outermost_wins(qapp):
    child = BlockDefinition.new(name="c", library="", series="",
                                primitives=[_text("@[Mark] @[Sub]")], origin=(0.0, 0.0))
    child.attributes = [_attr("Mark", default="child"), _attr("Sub", default="s")]
    host = BlockDefinition.new(
        name="h", library="", series="",
        primitives=[{"type": "block_instance", "block_id": child.id, "pos": [0.0, 0.0]}],
        origin=(0.0, 0.0))
    host.attributes = [_attr("Mark", default="host")]
    reg = {child.id: child, host.id: host}
    for d in reg.values():
        d._resolve = reg.get
    eff = host.effective_attributes()
    assert [r["key"] for r in eff] == ["Mark", "Sub"]
    assert eff[0]["default"] == "host"          # outermost wins (A1)
    assert eff[1]["default"] == "s"


def test_keep_upright_sparse():
    from firepro3d.text_item import TextAnnotationData
    d = TextAnnotationData.from_dict({"type": "text", "text": "x"})
    assert d.keep_upright is False
    assert "keep_upright" not in d.to_dict()
    d.keep_upright = True
    assert d.to_dict()["keep_upright"] is True
    assert TextAnnotationData.from_dict(d.to_dict()).keep_upright is True


def test_compile_splits_bound_prims(qapp):
    d = BlockDefinition.new(
        name="t", library="", series="",
        primitives=[_text("plain"), _text("@[Mark]", x=5.0),
                    _text("up", x=9.0, keep_upright=True),
                    {"type": "draw_line", "pt1": [0.0, 0.0], "pt2": [1.0, 0.0]}],
        origin=(1.0, 2.0))
    ops = d.render_ops()
    assert [op.kind for op in ops] == ["text", "stroke"]        # bound prims skipped
    bp = d.bound_prims()
    assert [b.prim["text"] for b in bp] == ["@[Mark]", "up"]
    # the transform is the origin shift
    assert bp[0].transform.map(0.0, 0.0) == (-1.0, -2.0)   # QTransform.map(x, y) -> tuple
    assert d.bound_prims() is bp                                  # cached with the ops
    d.set_primitives([_text("@[Mark]")])
    assert d.bound_prims() is not bp


def test_nested_bound_prims_carry_child_pose(qapp):
    child = BlockDefinition.new(name="c", library="", series="",
                                primitives=[_text("@[Mark]")], origin=(0.0, 0.0))
    host = BlockDefinition.new(
        name="h", library="", series="",
        primitives=[{"type": "block_instance", "block_id": child.id, "pos": [10.0, 0.0]}],
        origin=(0.0, 0.0))
    reg = {child.id: child, host.id: host}
    for d in reg.values():
        d._resolve = reg.get
    assert host.render_ops() == []                      # nothing static
    bp = host.bound_prims()
    assert len(bp) == 1 and bp[0].prim["text"] == "@[Mark]"
    assert bp[0].transform.map(0.0, 0.0) == (10.0, 0.0)


def test_effective_attributes_tracks_reassignment():
    d = BlockDefinition.new(name="t", library="", series="",
                            primitives=[], origin=(0.0, 0.0))
    d.attributes = [_attr("Old")]
    assert [r["key"] for r in d.effective_attributes()] == ["Old"]
    d.attributes = [_attr("New")]
    assert [r["key"] for r in d.effective_attributes()] == ["New"]
