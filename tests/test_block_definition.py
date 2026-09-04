"""Guard tests for BlockDefinition (Block system S1)."""
import uuid
from firepro3d.block_definition import BlockDefinition


def _line_dict(x1=0.0, y1=0.0, x2=100.0, y2=0.0):
    """A minimal draw_line primitive dict (see construction_geometry.LineItem.to_dict)."""
    return {"type": "draw_line", "pt1": [x1, y1], "pt2": [x2, y2],
            "color": "#ffffff", "lineweight": 1.0}


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


from PyQt6.QtGui import QPen, QPainterPath  # noqa: E402


def test_compile_produces_penpath_ops(qapp):
    d = BlockDefinition.new(name="A", library="L", series="S",
                            primitives=[_line_dict(0, 0, 100, 0)], origin=(0.0, 0.0))
    ops = d.render_ops()
    assert len(ops) == 1
    pen, path = ops[0]
    assert isinstance(pen, QPen)
    assert isinstance(path, QPainterPath)
    assert abs(path.boundingRect().width() - 100.0) < 1e-6


def test_render_ops_is_cached_same_identity(qapp):
    d = BlockDefinition.new(name="A", library="L", series="S",
                            primitives=[_line_dict()], origin=(0.0, 0.0))
    assert d.render_ops() is d.render_ops()  # compiled once, shared


def test_origin_is_subtracted(qapp):
    d = BlockDefinition.new(name="A", library="L", series="S",
                            primitives=[_line_dict(50, 0, 150, 0)], origin=(50.0, 0.0))
    _, path = d.render_ops()[0]
    assert abs(path.boundingRect().left() - 0.0) < 1e-6


def test_rebuild_bumps_version_and_recompiles(qapp):
    d = BlockDefinition.new(name="A", library="L", series="S",
                            primitives=[_line_dict(0, 0, 100, 0)], origin=(0.0, 0.0))
    ops_before = d.render_ops()
    d.set_primitives([_line_dict(0, 0, 200, 0)])
    assert d.version == 2
    assert d.render_ops() is not ops_before
    _, path = d.render_ops()[0]
    assert abs(path.boundingRect().width() - 200.0) < 1e-6
