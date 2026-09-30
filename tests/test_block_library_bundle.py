"""Library round-trip of nested blocks (AC9, AC5 load side)."""
import json
import os

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d import block_library
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _line_def(name, extra=()):
    return BlockDefinition.new(name=name, library="L", series="S", origin=(0.0, 0.0),
                               primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(), *extra])


def _nested(bid):
    return {"type": "block_instance", "block_id": bid, "pos": [0, 0], "rotation": 0.0}


def _project_ABC():
    sc = Model_Space()
    c = _line_def("C"); b = _line_def("B", [_nested(c.id)]); a = _line_def("A", [_nested(b.id)])
    for d in (c, b, a):
        sc.register_block_definition(d)
    return sc, a, b, c


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_save_bundles_transitive_dependencies(qapp, tmp_path):
    sc, a, b, c = _project_ABC()
    path = block_library.save_to_library(a, root=str(tmp_path),
                                         bundled=sc.block_registry.bundle_for(a.id))
    data = _read(path)
    assert data["schema"] == 2
    assert set(data["bundled"]) == {b.id, c.id}
    assert data["bundled"][c.id]["name"] == "C"


def test_save_without_nesting_stays_schema_1(qapp, tmp_path):
    sc, a, b, c = _project_ABC()
    path = block_library.save_to_library(c, root=str(tmp_path),
                                         bundled=sc.block_registry.bundle_for(c.id))
    data = _read(path)
    assert "bundled" not in data and data.get("schema", 1) != 2


def test_load_into_fresh_project_brings_dependencies(qapp, tmp_path):
    sc, a, b, c = _project_ABC()
    path = block_library.save_to_library(a, root=str(tmp_path),
                                         bundled=sc.block_registry.bundle_for(a.id))
    fresh = Model_Space()
    fresh.load_blocks_from_files([path])
    assert {a.id, b.id, c.id} <= set(fresh._block_definitions)
    fresh.place_block_instance(a.id, (0.0, 0.0))
    assert len(fresh.get_block_definition(a.id).render_ops()) == 3   # A + B + C lines


def test_project_copy_wins_over_bundled_copy(qapp, tmp_path):
    sc, a, b, c = _project_ABC()
    path = block_library.save_to_library(a, root=str(tmp_path),
                                         bundled=sc.block_registry.bundle_for(a.id))
    other = Model_Space()
    mine = BlockDefinition.from_dict(b.to_dict())
    mine.primitives = [LineItem(QPointF(0, 0), QPointF(5, 5)).to_dict()]
    other.register_block_definition(mine)
    other.load_blocks_from_files([path])
    assert other.get_block_definition(b.id) is mine
    assert other.get_block_definition(b.id).primitives == mine.primitives


def test_looping_file_is_skipped_with_reason(qapp, tmp_path):
    sc, a, b, c = _project_ABC()
    # a file whose bundled C nests A → loading it into a project holding A forms A⊃B⊃C⊃A
    looping_c = BlockDefinition.from_dict(c.to_dict())
    looping_c.primitives.append(_nested(a.id))
    path = str(tmp_path / "loop.fpdb")
    rec = b.to_dict(); rec["schema"] = 2; rec["bundled"] = {c.id: looping_c.to_dict()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    ok = _line_def("Fine")
    ok_path = str(tmp_path / "fine.fpdb")
    with open(ok_path, "w", encoding="utf-8") as fh:
        json.dump(ok.to_dict(), fh)
    target = Model_Space()
    target.register_block_definition(a)                  # A nests B
    summary = target.load_blocks_from_files([path, ok_path])
    assert any("contain itself" in r for r in summary["refused"])
    assert b.id not in target._block_definitions       # nothing of the loop embedded
    assert c.id not in target._block_definitions
    assert ok.id in target._block_definitions           # the rest of the batch loads


def test_schema1_file_still_loads(qapp, tmp_path):
    d = _line_def("Old")
    path = str(tmp_path / "old.fpdb")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d.to_dict(), fh)
    loaded, bundled = block_library.load_block_file_with_bundle(path)
    assert loaded.id == d.id and bundled == []


def test_reload_adds_missing_bundled_dependencies(qapp, tmp_path):
    sc, a, b, c = _project_ABC()
    root = str(tmp_path)
    block_library.save_to_library(a, root=root,
                                  bundled=sc.block_registry.bundle_for(a.id))
    target = Model_Space()
    stale = BlockDefinition.from_dict(a.to_dict())
    stale.version = a.version + 1          # embedded copy diverged from library
    target.register_block_definition(stale)
    assert target.reload_block_definition(a.id, root=root) is True
    assert {b.id, c.id} <= set(target._block_definitions)
    assert len(target.get_block_definition(a.id).render_ops()) == 3


def test_editor_save_writes_the_bundle(qapp, tmp_path, monkeypatch):
    """Real Save through the Block Editor rewrites the library copy with the
    nested dependencies bundled."""
    import firepro3d.block_editor as be
    monkeypatch.setattr(block_library, "_root",
                        lambda root: root if root is not None else str(tmp_path))
    sc, a, b, c = _project_ABC()
    block_library.save_to_library(a)            # A already has a library copy (schema 1)
    tabs = QTabWidget()
    mgr = be.BlockEditorManager(tabs, sc)
    w = mgr.edit_definition(a.id)
    try:
        assert w.save() is not None
        found = block_library._find_by_id(a.id, None)
        path = os.path.join(block_library._series_dir(None, found[0], found[1]), found[2])
        data = _read(path)
        assert data["schema"] == 2
        assert set(data["bundled"]) == {b.id, c.id}
    finally:
        w._modified = False
        mgr.close(w)


def test_manager_save_writes_the_bundle(qapp, tmp_path):
    from firepro3d.block_manager import BlockManagerDialog
    sc, a, b, c = _project_ABC()

    class _MW:
        settings = None
    dlg = BlockManagerDialog(sc, _MW(), apply_stylesheet=False, root=str(tmp_path))
    try:
        row = dlg.model.row_for_id(a.id)
        dlg.view.setCurrentIndex(dlg.proxy.mapFromSource(dlg.model.index(row, 0)))
        dlg._save_to_library()
        data = _read(str(tmp_path / "L" / "S" / "A.fpdb"))
        assert data["schema"] == 2
        assert set(data["bundled"]) == {b.id, c.id}
    finally:
        dlg.close()
