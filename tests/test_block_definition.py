"""Guard tests for BlockDefinition (Block system S1)."""
import uuid
from firepro3d.block_definition import BlockDefinition


def _line_dict(x1=0.0, y1=0.0, x2=100.0, y2=0.0):
    """A minimal draw_line primitive dict (see construction_geometry.LineItem.to_dict)."""
    return {"type": "draw_line", "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "color": "#ffffff", "width": 1.0}


def test_new_definition_has_uuid_and_defaults():
    d = BlockDefinition.new(name="Corner Joint", library="Typical Detail",
                            series="Wall Joints",
                            primitives=[_line_dict()], origin=(0.0, 0.0))
    uuid.UUID(hex=d.id)
    assert d.version == 1
    assert d.scale_mode == "real_size"
    assert d.attributes == []
    assert d.name == "Corner Joint"
    assert d.library == "Typical Detail"
    assert d.series == "Wall Joints"


def test_to_dict_from_dict_round_trip():
    d = BlockDefinition.new(name="A", library="L", series="S",
                            primitives=[_line_dict()], origin=(5.0, 7.0))
    d2 = BlockDefinition.from_dict(d.to_dict())
    assert d2.id == d.id
    assert d2.version == d.version
    assert d2.name == "A"
    assert d2.origin == (5.0, 7.0)
    assert d2.primitives == d.primitives
    assert d2.scale_mode == "real_size"
