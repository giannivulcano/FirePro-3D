"""Pattern (tiled) blocks are never placed as symbols (hatch D-A34)."""
from PyQt6.QtCore import QPointF, Qt

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _tiled_def(proj):
    d = BlockDefinition.new(name="Zig", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
                            tile={"w": 5, "h": 5, "row_shift": 0, "size": "model"})
    proj.register_block_definition(d)
    return d


def test_place_block_mode_refused_for_a_pattern(qapp):
    proj = Model_Space()
    d = _tiled_def(proj)
    proj.set_mode("place_block", template=d.id)
    assert proj.mode != "place_block"


def test_plain_block_still_placeable(qapp):
    proj = Model_Space()
    d = BlockDefinition.new(name="Plain", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()])
    proj.register_block_definition(d)
    proj.set_mode("place_block", template=d.id)
    assert proj.mode == "place_block"


def test_drag_gate_refuses_a_pattern(qapp):
    from firepro3d.model_view import Model_View
    proj = Model_Space()
    d = _tiled_def(proj)
    _defn, _pool, reason = Model_View._resolve_block_drag(proj, {"id": d.id})
    assert reason and "can't be placed" in reason


def test_drag_gate_refuses_a_library_only_pattern(qapp, tmp_path):
    from firepro3d import block_library
    from firepro3d.model_view import Model_View
    proj = Model_Space()
    d = BlockDefinition.new(name="LibZig", library="L", series="S", origin=(0, 0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
                            tile={"w": 5, "h": 5, "row_shift": 0, "size": "model"})
    path = block_library.save_to_library(d, root=str(tmp_path))
    assert proj.get_block_definition(d.id) is None
    _defn, _pool, reason = Model_View._resolve_block_drag(
        proj, {"id": d.id, "path": str(path)})
    assert reason and "can't be placed" in reason


def test_browser_badges_pattern_blocks(qapp):
    from firepro3d.blocks_browser import BlocksBrowser
    proj = Model_Space()
    _tiled_def(proj)
    b = BlocksBrowser(proj)
    b.refresh()
    leaf = b._tree.findItems("Zig", Qt.MatchFlag.MatchRecursive)[0]
    assert not leaf.icon(0).isNull()
    assert "pattern" in leaf.toolTip(0).lower()
