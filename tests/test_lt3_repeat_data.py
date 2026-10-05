"""LT3 H3-g -- BlockDefinition.repeat (mirrors HF2 tile)."""
import json
from firepro3d.block_definition import BlockDefinition
from tests.lt3_support import make_linetype


def test_repeat_normalised_and_round_trips():
    d = make_linetype(length=9, size="model")
    assert d.repeat == {"length": 9.0, "size": "model"}
    d2 = BlockDefinition.from_dict(json.loads(json.dumps(d.to_dict())))
    assert d2.repeat == {"length": 9.0, "size": "model"}


def test_repeat_absent_is_none_and_size_defaults_drafting():
    d = BlockDefinition.new(name="X", library="L", series="S", primitives=[],
                            origin=(0, 0))
    assert d.repeat is None and d.to_dict()["repeat"] is None
    d.set_repeat({"length": 5})
    assert d.repeat == {"length": 5.0, "size": "drafting"}


def test_set_repeat_bumps_version():
    d = make_linetype()
    v = d.version
    d.set_repeat({"length": 12})
    assert d.version == v + 1


def test_library_index_flags_repeat(tmp_path):
    from firepro3d import block_library
    d = make_linetype()
    path = block_library.save_to_library(d, root=str(tmp_path))
    import os
    idx = json.load(open(os.path.join(os.path.dirname(path), "index.json")))
    assert next(iter(idx.values()))["repeat"] is True
