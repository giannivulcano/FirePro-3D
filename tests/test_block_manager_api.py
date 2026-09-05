"""Model_Space block-management API (Block system S4)."""
from firepro3d.block_definition import BlockDefinition
from firepro3d import block_library as bl


def _def(name="A", library="L", series="S"):
    return BlockDefinition.new(name=name, library=library, series=series,
                               primitives=[{"type": "draw_line", "pt1": [0, 0],
                                            "pt2": [100, 0], "color": "#ffffff",
                                            "lineweight": 1.0}],
                               origin=(0.0, 0.0))


def test_instance_count_and_signal(model_space):
    d = _def()
    model_space.register_block_definition(d)
    fired = []
    model_space.blockInstancesChanged.connect(lambda: fired.append(1))

    assert model_space.instance_count(d.id) == 0
    a = model_space.place_block_instance(d.id, (0.0, 0.0))
    assert model_space.instance_count(d.id) == 1
    model_space.place_block_instance(d.id, (50.0, 0.0))
    assert model_space.instance_count(d.id) == 2
    model_space.remove_block_instance(a)
    assert model_space.instance_count(d.id) == 1
    # signal fired on each place (2) and each remove (1)
    assert len(fired) == 3


def test_delete_refused_while_instances_exist(model_space):
    d = _def()
    model_space.register_block_definition(d)
    model_space.place_block_instance(d.id, (0.0, 0.0))
    assert model_space.delete_block_definition(d.id) is False
    assert model_space.get_block_definition(d.id) is d   # still registered


def test_delete_removes_and_is_undoable(model_space):
    d = _def()
    model_space.register_block_definition(d)
    model_space.push_undo_state()                        # baseline snapshot (with defn)

    assert model_space.delete_block_definition(d.id) is True
    assert model_space.get_block_definition(d.id) is None

    model_space.undo()                                   # restore baseline
    restored = model_space.get_block_definition(d.id)
    assert restored is not None and restored.id == d.id


def test_reload_from_library_rebuilds_backrefs_and_repaints(model_space, tmp_path):
    root = str(tmp_path)
    d = _def()
    model_space.register_block_definition(d)
    inst = model_space.place_block_instance(d.id, (0.0, 0.0))
    bl.save_to_library(d, root=root)                     # library == embedded (v1)

    # Diverge the embedded copy: longer line -> wider bound, version bumps to 2.
    d.set_primitives([{"type": "draw_line", "pt1": [0, 0], "pt2": [400, 0],
                       "color": "#ffffff", "lineweight": 1.0}])
    assert bl.source_status(d, root=root) == "modified"
    wide = inst.boundingRect().width()

    model_space.push_undo_state()                        # baseline (modified state)
    assert model_space.reload_block_definition(d.id, root=root) is True

    reloaded = model_space.get_block_definition(d.id)
    assert reloaded is not None and reloaded.version == 1
    # instance now resolves to the library geometry (narrower) and repainted
    assert inst.boundingRect().width() < wide
    # backref rebuilt so future edits still propagate
    assert inst in reloaded._instances

    model_space.undo()                                   # back to modified copy
    assert model_space.get_block_definition(d.id).version == 2


def test_reload_absent_returns_false(model_space, tmp_path):
    d = _def()
    model_space.register_block_definition(d)
    assert model_space.reload_block_definition(d.id, root=str(tmp_path)) is False


def test_set_metadata_valid_rename_keeps_id_and_is_undoable(model_space):
    d = _def(name="Old")
    model_space.register_block_definition(d)
    old_id = d.id
    model_space.push_undo_state()                        # baseline (name "Old")

    assert model_space.set_block_metadata(d.id, "New", "Lib2", "Ser2") is True
    assert d.name == "New" and d.library == "Lib2" and d.series == "Ser2"
    assert d.id == old_id                                # identity stable

    model_space.undo()
    assert model_space.get_block_definition(old_id).name == "Old"


def test_set_metadata_blank_rejected(model_space):
    d = _def(name="Keep")
    model_space.register_block_definition(d)
    assert model_space.set_block_metadata(d.id, "   ", "L", "S") is False
    assert model_space.set_block_metadata(d.id, "X", "", "S") is False
    assert model_space.set_block_metadata(d.id, "X", "L", "") is False
    assert d.name == "Keep" and d.library == "L" and d.series == "S"


def test_set_metadata_collision_rejected(model_space):
    a = _def(name="A", library="L", series="S")
    b = _def(name="B", library="L", series="S")
    model_space.register_block_definition(a)
    model_space.register_block_definition(b)
    # renaming B onto A's (library, series, name) collides
    assert model_space.set_block_metadata(b.id, "A", "L", "S") is False
    assert b.name == "B"
    # a no-op "rename" of A to its own identity is allowed (excludes self)
    assert model_space.set_block_metadata(a.id, "A", "L", "S") is True
