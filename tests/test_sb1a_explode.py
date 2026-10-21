"""SB1a: Explode bakes the resolved string (A9); nested bakes outermost values."""
from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_explode import explode_instances
from firepro3d.model_space import Model_Space
from firepro3d.text_item import TextItem


def _text(text, **kw):
    d = {"type": "text", "text": text, "x": 0.0, "y": 0.0, "height_mm": 5.0}
    d.update(kw)
    return d


def _attr(key, **kw):
    return normalise_attr({"key": key, **kw})


def _setup():
    ms = Model_Space(scene_role="block_editor")
    child = BlockDefinition.new(name="C", library="", series="", origin=(0.0, 0.0),
                                primitives=[_text("@[Mark]", keep_upright=True)])
    child.attributes = [_attr("Mark", default="child")]
    ms.register_block_definition(child)
    host = BlockDefinition.new(
        name="H", library="", series="", origin=(0.0, 0.0),
        primitives=[_text("@[Mark]/@[Nope]", y=-10.0),
                    {"type": "block_instance", "block_id": child.id, "x": 0.0, "y": 0.0}])
    host.attributes = [_attr("Mark", default="host")]
    ms.register_block_definition(host)
    inst = ms.place_block_instance(host.id, (0.0, 0.0))
    inst.set_attributes({"Mark": "X7"})
    return ms, inst


def test_explode_flatten_bakes_resolved_strings(qapp):
    ms, inst = _setup()
    inst.set_block_rotation(180.0)
    made = explode_instances(ms, [inst], flatten=True)
    texts = sorted(t._data.text for t in made if isinstance(t, TextItem))
    assert texts == ["X7", "X7/@[Nope]"]            # outermost value; unknown literal
    up = [t for t in made if isinstance(t, TextItem) and t._data.text == "X7"][0]
    assert up._data.keep_upright is False           # baked pose, flag dropped
    assert abs(((up._angle % 360.0) + 90.0) % 360.0 - 90.0) < 1e-6   # reads upright (0 or 360)


def test_explode_one_level_copies_outer_values_to_child(qapp):
    from firepro3d.block_instance import BlockInstance
    ms, inst = _setup()
    made = explode_instances(ms, [inst], flatten=False)
    kids = [i for i in made if isinstance(i, BlockInstance)]
    assert len(kids) == 1 and kids[0].attributes == {"Mark": "X7"}


def test_flatten_outermost_default_wins_without_override(qapp):
    """A1 / A9: with no instance override, the nested child's text bakes the
    OUTERMOST definition's default, not its own (the ``values=`` threading
    through the flatten recursion -- a ``set_attributes`` copy alone cannot
    carry a default)."""
    ms = Model_Space(scene_role="block_editor")
    child = BlockDefinition.new(name="C", library="", series="", origin=(0.0, 0.0),
                                primitives=[_text("@[Mark]")])
    child.attributes = [_attr("Mark", default="child")]
    ms.register_block_definition(child)
    host = BlockDefinition.new(
        name="H", library="", series="", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": child.id, "x": 0.0, "y": 0.0}])
    host.attributes = [_attr("Mark", default="host")]
    ms.register_block_definition(host)
    inst = ms.place_block_instance(host.id, (0.0, 0.0))   # no override
    made = explode_instances(ms, [inst], flatten=True)
    assert [t._data.text for t in made if isinstance(t, TextItem)] == ["host"]
