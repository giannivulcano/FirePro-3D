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
