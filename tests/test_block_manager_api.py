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


def _write_fpdb(tmp_path, defn, name=None):
    """Write defn.to_dict() to a .fpdb file, return its path."""
    import json
    p = tmp_path / f"{name or defn.name}.fpdb"
    p.write_text(json.dumps(defn.to_dict()), encoding="utf-8")
    return str(p)


def test_load_embeds_and_is_placeable_and_undoable(model_space, tmp_path):
    d = _def(name="Corner")
    path = _write_fpdb(tmp_path, d)
    model_space.push_undo_state()                       # baseline (empty)

    summary = model_space.load_blocks_from_files([path])
    assert summary["loaded"] == ["Corner"]
    assert model_space.get_block_definition(d.id) is not None
    # placeable
    inst = model_space.place_block_instance(d.id, (0.0, 0.0))
    assert inst in model_space._block_instances

    model_space.remove_block_instance(inst)
    model_space.undo()                                  # unloads the batch
    assert model_space.get_block_definition(d.id) is None


def test_load_collision_rules(model_space, tmp_path):
    # already-loaded id -> skip
    a = _def(name="A")
    model_space.register_block_definition(a)
    same = _write_fpdb(tmp_path, a, name="A_again")
    s1 = model_space.load_blocks_from_files([same])
    assert s1["skipped"] == ["A"] and s1["loaded"] == []

    # same id, higher version -> replace (backref rebuilt + repaint)
    inst = model_space.place_block_instance(a.id, (0.0, 0.0))
    newer = _def(name="A")
    newer.id = a.id                                     # same identity
    newer.set_primitives([{"type": "draw_line", "pt1": [0, 0], "pt2": [400, 0],
                           "color": "#ffffff", "lineweight": 1.0}])  # version 2, wider
    wide_before = inst.boundingRect().width()
    pth = _write_fpdb(tmp_path, newer, name="A_v2")
    s2 = model_space.load_blocks_from_files([pth])
    assert s2["replaced"] == ["A"]
    assert model_space.get_block_definition(a.id).version == newer.version
    assert inst.boundingRect().width() > wide_before    # repainted to new geometry
    assert inst in model_space.get_block_definition(a.id)._instances

    # different id, same (library, series, name) -> refuse
    clash = _def(name="A")                              # fresh uuid, same L/S/name
    pth2 = _write_fpdb(tmp_path, clash, name="A_clash")
    s3 = model_space.load_blocks_from_files([pth2])
    assert s3["refused"] == ["A"] and s3["loaded"] == []


def test_load_batch_single_undo(model_space, tmp_path):
    d1 = _def(name="One")
    d2 = _def(name="Two")
    p1, p2 = _write_fpdb(tmp_path, d1), _write_fpdb(tmp_path, d2)
    model_space.push_undo_state()                       # baseline (empty)
    depth_before = len(model_space._undo_stack)

    summary = model_space.load_blocks_from_files([p1, p2])
    assert set(summary["loaded"]) == {"One", "Two"}
    assert len(model_space._undo_stack) == depth_before + 1   # exactly ONE push

    model_space.undo()                                  # reverts whole batch
    assert model_space.get_block_definition(d1.id) is None
    assert model_space.get_block_definition(d2.id) is None


def test_load_unreadable_file_counts_failed(model_space, tmp_path):
    bad = tmp_path / "bad.fpdb"
    bad.write_text("{broken", encoding="utf-8")
    good = _def(name="Good")
    gp = _write_fpdb(tmp_path, good)
    summary = model_space.load_blocks_from_files([str(bad), gp])
    assert summary["failed"] == [str(bad)]
    assert summary["loaded"] == ["Good"]
    assert model_space.get_block_definition(good.id) is not None
