"""LTS-1 / LTS-5 data: the optional `screen` key and its reading."""
from firepro3d.block_definition import BlockDefinition
from firepro3d.linetype_render import LinetypeDef
from tests.lt3_support import make_linetype


def test_keyless_repeat_reads_scale_with_zoom():
    d = make_linetype()
    assert d.repeat == {"length": 9.0, "size": "drafting"}      # byte-identical
    assert LinetypeDef.from_block(d).screen == "scale"


def test_fixed_survives_definition_round_trip():
    d = make_linetype(screen="fixed")
    assert d.repeat == {"length": 9.0, "size": "drafting", "screen": "fixed"}
    d2 = BlockDefinition.from_dict(d.to_dict())
    assert d2.repeat["screen"] == "fixed"
    assert LinetypeDef.from_block(d2).screen == "fixed"


def test_unknown_screen_value_normalises_to_scale():
    d = make_linetype()
    d.set_repeat({"length": 9.0, "size": "drafting", "screen": "bogus"})
    assert d.repeat == {"length": 9.0, "size": "drafting"}
    assert LinetypeDef.from_block(d).screen == "scale"
