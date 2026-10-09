"""SV2 Tasks 2-3 -- the shared materializer + SchematicSceneManager
(concept SD2 + SV2 delta)."""
from PyQt6.QtCore import QPointF, QRectF

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_instance import BlockInstance
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _sym(proj):
    d = BlockDefinition.new(
        name="Sym", library="L", series="S",
        primitives=[LineItem(QPointF(0, 0), QPointF(0, 40)).to_dict()],
        origin=(0.0, 0.0))
    proj.register_block_definition(d)
    return d


def _schematic_prims(sym_id, length=100.0):
    return [LineItem(QPointF(0, 0), QPointF(length, 0)).to_dict(),
            {"type": "block_instance", "block_id": sym_id,
             "pos": [50.0, 10.0], "rotation": 0.0}]


def _schematic(proj, sym_id, name="Riser"):
    d = BlockDefinition.new(name=name, library="", series="",
                            primitives=_schematic_prims(sym_id),
                            origin=(0.0, 0.0), kind="schematic")
    proj.register_block_definition(d)
    return d


def test_materialize_then_clear_round_trip(qapp):
    from firepro3d import schematic_scene as ss
    proj = Model_Space()
    sym = _sym(proj)
    sc = Model_Space(scene_role="block_editor")
    sc.borrow_block_registry(proj.block_registry, owner=proj)
    ss.materialize_primitives(sc, _schematic_prims(sym.id))
    items = ss.materialized_items(sc)
    assert [type(i).__name__ for i in items] == ["LineItem", "BlockInstance"]
    assert all(i.scene() is sc for i in items)
    ss.clear_materialized(sc)
    assert ss.materialized_items(sc) == []
    assert not any(isinstance(i, (LineItem, BlockInstance)) for i in sc.items())


def test_editor_seed_uses_the_shared_materializer(qapp, monkeypatch):
    from firepro3d import schematic_scene as ss
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    sym = _sym(proj)
    seen = []
    real = ss.materialize_primitives
    monkeypatch.setattr(ss, "materialize_primitives",
                        lambda scene, dicts: (seen.append(scene),
                                              real(scene, dicts))[1])
    w = BlockEditorWidget(proj)
    w.seed_from_dicts(_schematic_prims(sym.id))
    assert seen == [w.editor_scene]
    assert [type(i).__name__ for i in w.gather_primitives()] == [
        "LineItem", "BlockInstance"]


# -- SchematicSceneManager ----------------------------------------------------

def _mgr():
    from firepro3d.schematic_scene import SchematicSceneManager
    proj = Model_Space()
    sym = _sym(proj)
    proj.push_undo_state()                          # state A: sym only
    sch = _schematic(proj, sym.id)
    proj.push_undo_state()                          # state B: + schematic
    return proj, sym, sch, SchematicSceneManager(proj)


def _kinds(scene):
    from firepro3d import schematic_scene as ss
    return [type(i).__name__ for i in ss.materialized_items(scene)]


def test_scene_for_materializes_and_is_reused(qapp):
    proj, sym, sch, mgr = _mgr()
    sc = mgr.scene_for(sch.id)
    assert _kinds(sc) == ["LineItem", "BlockInstance"]
    assert mgr.scene_for(sch.id) is sc
    assert sch.id in mgr.live_ids()
    assert sc in proj.block_registry._scenes        # nested repaint path
    assert sym._instances == []                     # render scenes add no backrefs


def test_extent_is_pen_free_bounds_padded(qapp):
    proj, sym, sch, mgr = _mgr()
    mgr.scene_for(sch.id)
    # line 0..100 at y=0 + nested vertical x=50, y 10..50 -> (0,0,100,50);
    # pad = max(1 mm, 2 % of 100) = 2 mm per side.
    assert mgr.extent(sch.id) == QRectF(-2, -2, 104, 54)


def test_empty_schematic_extent_is_default_rect(qapp):
    from firepro3d.schematic_scene import SchematicSceneManager
    proj = Model_Space()
    d = BlockDefinition.new(name="Empty", library="", series="", primitives=[],
                            origin=(0.0, 0.0), kind="schematic")
    proj.register_block_definition(d)
    mgr = SchematicSceneManager(proj)
    mgr.scene_for(d.id)
    assert mgr.extent(d.id) == QRectF(0, 0, 1000, 1000)


def test_edit_rebuilds_in_place(qapp):
    proj, sym, sch, mgr = _mgr()
    sc = mgr.scene_for(sch.id)
    proj.commit_block_definition(
        block_id=sch.id, name="Riser", library="", series="",
        primitives=_schematic_prims(sym.id, length=200.0), origin=(0.0, 0.0),
        place_instance=False)
    assert mgr.scene_for(sch.id) is sc              # same object (SV2 delta)
    assert mgr.extent(sch.id) == QRectF(-4, -4, 208, 58)
    assert _kinds(sc) == ["LineItem", "BlockInstance"]   # not duplicated


def test_nested_block_edit_refits_extent(qapp):
    proj, sym, sch, mgr = _mgr()
    mgr.scene_for(sch.id)
    proj.commit_block_definition(
        block_id=sym.id, name="Sym", library="L", series="S",
        primitives=[LineItem(QPointF(0, 0), QPointF(0, 90)).to_dict()],
        origin=(0.0, 0.0), place_instance=False)
    mgr.scene_for(sch.id)
    assert mgr.extent(sch.id).bottom() == 100 + 2   # nested now 10..100


def test_undo_redo_new_definition_object_rebuilds(qapp):
    proj, sym, sch, mgr = _mgr()
    mgr.scene_for(sch.id)
    proj.undo()                                     # schematic gone
    assert sch.id not in mgr.live_ids()             # disposed by the handler
    assert mgr.scene_for(sch.id) is None
    proj.redo()                                     # restored as a NEW object
    sc = mgr.scene_for(sch.id)
    assert _kinds(sc) == ["LineItem", "BlockInstance"]


def test_dispose_detaches_from_registry(qapp):
    proj, sym, sch, mgr = _mgr()
    sc = mgr.scene_for(sch.id)
    mgr.dispose_all()
    assert mgr.live_ids() == set()
    assert sc not in proj.block_registry._scenes


def test_plain_block_and_unknown_id_resolve_to_none(qapp):
    proj, sym, sch, mgr = _mgr()
    assert mgr.scene_for(sym.id) is None
    assert mgr.scene_for("nope") is None
    assert mgr.display_name(sch.id) == "Riser"
    assert mgr.display_name(sym.id) is None


def test_cache_holds_definition_object_across_undo_redo(qapp):
    proj, sym, sch, mgr = _mgr()
    mgr.scene_for(sch.id)
    assert mgr._keys[sch.id][0] is proj.get_block_definition(sch.id)
    proj.undo()
    proj.redo()
    mgr.scene_for(sch.id)
    new = proj.get_block_definition(sch.id)
    assert new is not sch
    assert mgr._keys[sch.id][0] is new


def test_kind_change_disposes_render_scene(qapp):
    proj, sym, sch, mgr = _mgr()
    mgr.scene_for(sch.id)
    sch.kind = "block"
    proj.blockDefinitionsChanged.emit()
    assert sch.id not in mgr.live_ids()
    assert mgr.scene_for(sch.id) is None
