"""SB1a: schema round-trips -- .fpd, .fpdb schema 1 + 2 (bundled), undo (AC2 / G2)."""
from firepro3d import block_library
from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.model_space import Model_Space


def _text(text, **kw):
    d = {"type": "text", "text": text, "x": 0.0, "y": 0.0, "height_mm": 5.0}
    d.update(kw)
    return d


def _attr(key, **kw):
    return normalise_attr({"key": key, **kw})


def _scene_with_tag():
    ms = Model_Space()
    child = BlockDefinition.new(name="C", library="", series="", origin=(0.0, 0.0),
                                primitives=[_text("@[Sub]", keep_upright=True)])
    child.attributes = [_attr("Sub", default="s")]
    ms.register_block_definition(child)
    d = BlockDefinition.new(
        name="Tag", library="Lib", series="Ser", origin=(0.0, 0.0),
        primitives=[_text("@[Mark]", keep_upright=True),
                    {"type": "block_instance", "block_id": child.id, "x": 1.0, "y": 2.0}])
    d.attributes = [_attr("Mark", default="A1"),
                    _attr("Area", type="number", precision=2, source="host", host_key="Room.Area")]
    d.host_category = "Rooms"
    d.scale_mode = "annotative"
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (10.0, 20.0))
    inst.set_attributes({"Mark": "B7", "Area": "3"})
    return ms, d, inst


def _assert_fields(d2, d):
    assert d2.attributes == d.attributes
    assert d2.host_category == "Rooms" and d2.scale_mode == "annotative"
    assert d2.primitives[0]["keep_upright"] is True
    assert "attributes" not in d2.primitives[1]


def test_fpd_round_trip(tmp_path, qapp):
    ms, d, inst = _scene_with_tag()
    path = str(tmp_path / "t.fpd")
    assert ms.save_to_file(path)
    ms2 = Model_Space()
    ms2.load_from_file(path)
    d2 = ms2.get_block_definition(d.id)
    _assert_fields(d2, d)
    i2 = ms2._block_instances[0]
    assert i2.attributes == {"Mark": "B7", "Area": "3"}


def test_fpdb_schema_1_and_bundled_round_trip(tmp_path, qapp):
    ms, d, inst = _scene_with_tag()
    child = ms.get_block_definition(d.primitives[1]["block_id"])
    p1 = block_library.save_to_library(d, root=str(tmp_path / "r1"))
    d1 = block_library.load_block_file(p1)
    _assert_fields(d1, d)
    p2 = block_library.save_to_library(d, root=str(tmp_path / "r2"),
                                       bundled={child.id: child.to_dict()})
    d2, bundled = block_library.load_block_file_with_bundle(p2)
    _assert_fields(d2, d)
    sub = bundled[0]
    assert sub.attributes == [_attr("Sub", default="s")]
    assert sub.primitives[0]["keep_upright"] is True


def test_undo_round_trip(qapp):
    ms, d, inst = _scene_with_tag()
    ms.push_undo_state()
    inst.set_attributes({"Mark": "C9"})
    ms.push_undo_state()
    ms.undo()
    i = ms._block_instances[0]
    assert i.attributes == {"Mark": "B7", "Area": "3"}
    d2 = ms.get_block_definition(d.id)
    _assert_fields(d2, d)
    ms.redo()
    assert ms._block_instances[0].attributes == {"Mark": "C9"}


def test_legacy_nested_attributes_ignored(qapp):
    rec = {"id": "x", "primitives": [
        {"type": "block_instance", "block_id": "y", "x": 0.0, "y": 0.0,
         "attributes": {"Mark": "old"}}]}
    d = BlockDefinition.from_dict(rec)
    assert "attributes" not in d.primitives[0]


def test_text_item_to_dict_keeps_upright(qapp):
    """The Block Editor commit path (``TextItem.to_dict`` -> definition prims)
    must carry ``keep_upright``; definition prims are raw dicts, so the
    definition round-trips above never touch ``TextAnnotationData.to_dict``."""
    from firepro3d.text_item import TextItem
    on = TextItem.from_dict(_text("@[Mark]", keep_upright=True)).to_dict()
    off = TextItem.from_dict(_text("@[Mark]")).to_dict()
    assert on["keep_upright"] is True
    assert "keep_upright" not in off
    d = BlockDefinition.new(name="T", library="", series="", origin=(0.0, 0.0),
                            primitives=[on])
    d2 = BlockDefinition.from_dict(d.to_dict())
    assert d2.primitives[0]["keep_upright"] is True
