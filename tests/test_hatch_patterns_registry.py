"""Built-in tiles, legacy alias and registry refs (hatch D-A28/D-A29, HD4a)."""
from PyQt6.QtCore import QPointF
from firepro3d import hatch_patterns as hp
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem, RectangleItem
from firepro3d.model_space import Model_Space


def _tile_def(name="P", tile=None):
    return BlockDefinition.new(
        name=name, library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile=tile or {"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})


def test_legacy_names_resolve_to_builtin_tiles(qapp):
    for name in ("diagonal", "cross_hatch", "horizontal", "concrete"):
        t = hp.resolve_tile(name, None)
        assert t is not None and t.tile is not None, name
        assert t.id == hp.LEGACY_ALIAS[name]
        assert t.render_ops(), f"{name} tile has no geometry"
    brick = hp.resolve_tile(hp.BUILTIN_BRICK, None)
    assert brick.tile["size"] == "model" and brick.tile["row_shift"] == 112.5


def test_tile_round_trips_through_to_dict(qapp):
    d = _tile_def()
    d2 = BlockDefinition.from_dict(d.to_dict())
    assert d2.tile == {"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"}
    plain = BlockDefinition.from_dict(BlockDefinition.new(
        name="X", library="L", series="S", primitives=[], origin=(0, 0)).to_dict())
    assert plain.tile is None


def test_tile_choices_lists_builtins_then_project_tiles(qapp):
    sc = Model_Space()
    sc.register_block_definition(_tile_def("Zig"))
    sc.register_block_definition(BlockDefinition.new(
        name="Symbol", library="L", series="S", origin=(0, 0),
        primitives=[LineItem(QPointF(0, 0), QPointF(1, 0)).to_dict()]))
    names = [n for n, _ in hp.tile_choices(sc.block_registry)]
    assert names[:5] == ["Diagonal", "Cross Hatch", "Horizontal", "Concrete", "Brick"]
    assert "Zig" in names and "Symbol" not in names


def test_legacy_fill_pattern_canonicalised_on_load(qapp):
    r = RectangleItem(QPointF(0, 0), QPointF(10, 10))
    d = r.to_dict()
    d["fill"] = {"type": "hatch", "pattern": "diagonal", "color": "#000000", "opacity": 1.0}
    r2 = RectangleItem.from_dict(d)
    assert r2.fill_pattern == hp.BUILTIN_DIAGONAL
    assert r2.to_dict()["fill"]["pattern"] == hp.BUILTIN_DIAGONAL


def test_pattern_reference_is_a_registry_dependency(qapp):
    sc = Model_Space()
    pat = _tile_def("Zig")
    sc.register_block_definition(pat)
    r = RectangleItem(QPointF(0, 0), QPointF(10, 10))
    r.fill_type, r.fill_pattern = "hatch", pat.id
    host = BlockDefinition.new(name="Host", library="L", series="S",
                               origin=(0, 0), primitives=[r.to_dict()])
    sc.register_block_definition(host)
    reg = sc.block_registry
    assert pat.id in reg.closure(host.id)               # bundled with the host
    assert host.id in reg.users_of(pat.id)              # delete guard / G5 invalidation
    assert reg.would_cycle(pat.id, host.id)             # host can't go inside its pattern


def test_builtin_pattern_ref_is_never_reported_missing(qapp):
    sc = Model_Space()
    r = RectangleItem(QPointF(0, 0), QPointF(10, 10))
    r.fill_type, r.fill_pattern = "hatch", "diagonal"
    host = BlockDefinition.new(
        name="Host", library="L", series="S", origin=(0, 0),
        primitives=[r.to_dict(),
                    {"type": "block_instance", "block_id": "gone",
                     "pos": [0.0, 0.0], "rotation": 0.0}])
    sc.register_block_definition(host)
    missing = sc.block_registry.missing_nested()
    assert missing == {"gone": {host.id}}      # nested symbol reported, builtin not


def test_project_tile_named_like_builtin_is_pickable(qapp):
    sc = Model_Space()
    proj = _tile_def("Diagonal")
    sc.register_block_definition(proj)
    rect = RectangleItem(QPointF(0, 0), QPointF(10, 10))
    sc.addItem(rect)
    rect.fill_type = "hatch"
    opts = rect.get_properties()["Pattern"]["options"]
    assert "Diagonal" in opts and "Diagonal (project)" in opts
    assert len(set(opts)) == len(opts)
    rect.set_property("Pattern", "Diagonal (project)")
    assert rect.fill_pattern == proj.id
    assert rect.get_properties()["Pattern"]["value"] == "Diagonal (project)"
    rect.set_property("Pattern", "Diagonal")
    assert rect.fill_pattern == hp.BUILTIN_DIAGONAL


def test_tile_dict_is_a_copy(qapp):
    b = hp.builtin_tiles()[hp.BUILTIN_BRICK]
    b.tile["w"] = 1.0
    assert hp.builtin_tiles()[hp.BUILTIN_BRICK].tile["w"] == 225.0
