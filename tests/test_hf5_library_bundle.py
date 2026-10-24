"""HF5 Task 10 -- .fpdb bundles Fill Types (schema 3); load merges by name, project wins (G7)."""
import json

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import block_library
from firepro3d import fill_types as ft
from firepro3d.block_definition import BlockDefinition
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.filled_region import FilledRegionItem
from firepro3d.geometry_2d import LineItem
from firepro3d.hatch_patterns import LEGACY_ALIAS, shipped_pattern_files
from firepro3d.model_space import Model_Space

RED = FillLayers(BackgroundLayer("#ff0000", 1.0))
BLUE = FillLayers(BackgroundLayer("#0000ff", 1.0))


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _render(scene, area=QRectF(0, 0, 120, 120), size=120) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, size, size), area)
    p.end()
    return img


def _rgb(img, x, y):
    return QColor(img.pixel(x, y)).getRgb()[:3]


def _region_rec(type_id):
    a, b, c, d = QPointF(10, 10), QPointF(110, 10), QPointF(110, 110), QPointF(10, 110)
    r = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]])
    r.set_fill_type(type_id)
    return r.to_dict()


def _host(type_id, name="Host"):
    return BlockDefinition.new(name=name, library="Lib", series="S", origin=(0.0, 0.0),
                               primitives=[_region_rec(type_id)])


def _table(*types):
    ft.set_project_table(ft.FillTypeTable(list(types)))


def _saved(type_layers=RED, type_id="cid", name="Concrete"):
    _table(ft.FillType(type_id, name, type_layers))
    return block_library.save_to_library(_host(type_id))


def _placed_pixel(sc, defn_id):
    sc.place_block_instance(defn_id, (0.0, 0.0))
    return _rgb(_render(sc), 60, 60)


def _with_patterns():
    ms = Model_Space()
    ms.load_blocks_outside_history([p for _b, p in shipped_pattern_files()])
    return ms, LEGACY_ALIAS["diagonal"]


def test_save_writes_used_types_and_schema_3(qapp):
    ms, pat = _with_patterns()
    assert pat in ms._block_definitions
    concrete = ft.FillType("cid", "Concrete", FillLayers(
        BackgroundLayer("#ff0000", 1.0), PatternLayer(pat, "#000000", 1.0, 1.0)))
    _table(concrete, ft.FillType("unused", "Unused", BLUE))
    host = _host("cid")
    ms.register_block_definition(host)
    path = block_library.save_to_library(host, bundled=ms.block_registry.bundle_for(host.id))
    data = _read(path)
    assert data["schema"] == 3
    assert data["fill_types"] == [concrete.to_payload()]        # used types only
    assert pat in data["bundled"]                               # type -> pattern bundles
    assert block_library.read_bundled_fill_types(path) == data["fill_types"]


def test_no_typed_region_stays_schema_1(qapp):
    _table(ft.FillType("cid", "Concrete", RED))
    d = BlockDefinition.new(name="Plain", library="Lib", series="S", primitives=[], origin=(0.0, 0.0))
    data = _read(block_library.save_to_library(d))
    assert data["schema"] == 1 and "fill_types" not in data


def test_nested_closure_types_bundle(qapp):
    """A type used only by a nested definition travels with the host."""
    _table(ft.FillType("cid", "Concrete", RED))
    inner = _host("cid", name="Inner")
    ms = Model_Space()
    ms.register_block_definition(inner)
    outer = BlockDefinition.new(name="Outer", library="Lib", series="S", origin=(0.0, 0.0),
                                primitives=[{"type": "block_instance", "block_id": inner.id,
                                             "pos": [0.0, 0.0]}])
    ms.register_block_definition(outer)
    path = block_library.save_to_library(outer, bundled=ms.block_registry.bundle_for(outer.id))
    data = _read(path)
    assert data["schema"] == 3 and [r["name"] for r in data["fill_types"]] == ["Concrete"]


def test_alias_id_is_bundled_under_the_kept_id(qapp):
    """A record typed with a load-time duplicate's alias id bundles the kept type, canonical id."""
    ft.set_project_table(ft.FillTypeTable.from_payload([
        ft.FillType("keep", "Concrete", RED).to_payload(),
        ft.FillType("dup", "concrete", BLUE).to_payload()]))
    data = _read(block_library.save_to_library(_host("dup")))
    assert [r["id"] for r in data["fill_types"]] == ["keep"]
    assert data["primitives"][0]["fill_type"] == "keep"


def test_load_into_fresh_project_adds_type_and_pattern(qapp):
    """G7 first half: the type and its pattern block arrive, the placed region paints red."""
    ms, pat = _with_patterns()
    _table(ft.FillType("cid", "Concrete", FillLayers(
        BackgroundLayer("#ff0000", 1.0), PatternLayer(pat, "#000000", 1.0, 1.0))))
    host = _host("cid")
    ms.register_block_definition(host)
    path = block_library.save_to_library(host, bundled=ms.block_registry.bundle_for(host.id))
    ft.reset_project_table()
    fresh = Model_Space()
    summary = fresh.load_blocks_from_files([path])
    assert summary["loaded"] == ["Host"]
    t = ft.project_table().by_name("Concrete")
    assert t is not None and t.layers.background.color == "#ff0000"
    loaded = fresh.get_block_definition(host.id)
    assert loaded.primitives[0]["fill_type"] == t.id
    assert fresh.get_block_definition(pat) is not None          # pattern block bundled in
    assert _placed_pixel(fresh, host.id)[0] > 200               # red-ish fill under the pattern


def test_collision_project_wins(qapp):
    """G7 second half: a same-name project type wins; regions re-point; no duplicate."""
    path = _saved(RED)
    _table(ft.FillType("proj", "Concrete", BLUE))
    fresh = Model_Space()
    fresh.load_blocks_from_files([path])
    tbl = ft.project_table()
    assert [t.name for t in tbl.all()] == ["Concrete"] and tbl.all()[0].layers == BLUE
    loaded = fresh.get_block_definition(_read(path)["id"])
    assert loaded.primitives[0]["fill_type"] == "proj"
    assert _placed_pixel(fresh, loaded.id) == (0, 0, 255)


def test_id_clash_with_other_name_gets_fresh_id(qapp):
    path = _saved(RED)
    _table(ft.FillType("cid", "Other", BLUE))                  # same id, other name
    fresh = Model_Space()
    fresh.load_blocks_from_files([path])
    tbl = ft.project_table()
    assert tbl.get("cid").name == "Other" and tbl.get("cid").layers == BLUE
    new = tbl.by_name("Concrete")
    assert new is not None and new.id != "cid" and new.layers == RED
    loaded = fresh.get_block_definition(_read(path)["id"])
    assert loaded.primitives[0]["fill_type"] == new.id
    assert _placed_pixel(fresh, loaded.id) == (255, 0, 0)


def test_load_marks_project_dirty(qapp):
    path = _saved(RED)
    ft.reset_project_table()
    fresh = Model_Space()
    fresh.load_blocks_from_files([path])
    ft.reset_project_table()                    # same-version re-load: skipped, no undo step
    fresh._dirty = False
    assert fresh.load_blocks_from_files([path])["skipped"] == ["Host"]
    assert ft.project_table().by_name("Concrete") is not None
    assert fresh._dirty is True                 # the merge alone dirties the project


def test_refused_load_adds_no_types(qapp, tmp_path):
    path = _saved(RED)
    ft.reset_project_table()
    before = [t.to_payload() for t in ft.project_table().all()]
    sc = Model_Space()
    sc.register_block_definition(_host("x"))                    # same lib/series/name, new id
    summary = sc.load_blocks_from_files([path])
    assert summary["refused"]
    assert [t.to_payload() for t in ft.project_table().all()] == before
    bad = tmp_path / "bad.fpdb"
    bad.write_text("{not json", encoding="utf-8")
    assert Model_Space().load_blocks_from_files([str(bad)])["failed"]
    assert [t.to_payload() for t in ft.project_table().all()] == before


def test_reload_adds_missing_type(qapp):
    path = _saved(RED)
    host_id = _read(path)["id"]
    ft.reset_project_table()
    sc = Model_Space()
    sc.load_blocks_from_files([path])
    ft.reset_project_table()                                    # type lost; library still has it
    assert ft.project_table().by_name("Concrete") is None
    assert sc.reload_block_definition(host_id) is True
    t = ft.project_table().by_name("Concrete")
    assert t is not None and sc.get_block_definition(host_id).primitives[0]["fill_type"] == t.id


def test_load_block_file_canonicalises_alias_ids(qapp):
    """Carry-in: the bare loaders re-point a typed record before from_dict (alias-aware)."""
    path = _saved(RED)
    data = _read(path)
    data["primitives"][0]["fill_type"] = "dup"                  # no row for it: project alias
    data.pop("fill_types")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    ft.set_project_table(ft.FillTypeTable.from_payload([
        ft.FillType("keep", "Concrete", RED).to_payload(),
        ft.FillType("dup", "concrete", BLUE).to_payload()]))
    assert block_library.load_block_file(path).primitives[0]["fill_type"] == "keep"
    assert block_library.load_block_file_with_bundle(path)[0].primitives[0]["fill_type"] == "keep"


def test_manager_save_path_writes_types(qapp, tmp_path):
    """The real Blocks-manager save writes the bundle with the types."""
    from firepro3d.block_manager import BlockManagerDialog
    _table(ft.FillType("cid", "Concrete", RED))
    sc = Model_Space()
    host = _host("cid")
    sc.register_block_definition(host)

    class _MW:
        settings = None
    dlg = BlockManagerDialog(sc, _MW(), apply_stylesheet=False, root=str(tmp_path))
    try:
        row = dlg.model.row_for_id(host.id)
        dlg.view.setCurrentIndex(dlg.proxy.mapFromSource(dlg.model.index(row, 0)))
        dlg._save_to_library()
        data = _read(str(tmp_path / "Lib" / "S" / "Host.fpdb"))
        assert data["schema"] == 3 and [r["name"] for r in data["fill_types"]] == ["Concrete"]
    finally:
        dlg.close()


def _rename_rows(path, mapping):
    """Hand-edit a saved .fpdb: rename its bundled Fill Type rows (id -> name)."""
    data = _read(path)
    for row in data["fill_types"]:
        row["name"] = mapping[row["id"]]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def test_reserved_bundled_names_are_renamed_not_added_as_is(qapp):
    """Group E review Minor 1: a bundled row named "(Custom)" or "? ..." would
    shadow / mis-pick in the region panel. It is renamed (never skipped: the
    regions already point at its id) through the real .fpdb load path."""
    for n, (bad, want) in enumerate((("(Custom)", "(Custom) (imported)"),
                                     ("? deadbeef", "deadbeef"),
                                     ("? (custom)", "(custom) (imported)"))):
        _table(ft.FillType("cid", "Concrete", RED))
        path = block_library.save_to_library(_host("cid", f"Host{n}"))
        _rename_rows(path, {"cid": bad})
        ft.reset_project_table()
        fresh = Model_Space()
        assert fresh.load_blocks_from_files([path])["loaded"] == [f"Host{n}"]
        names = [t.name for t in ft.project_table().all()]
        assert want in names and not any(ft.reserved_name(n) for n in names)
        t = ft.project_table().by_name(want)
        loaded = fresh.get_block_definition(_read(path)["id"])
        assert loaded.primitives[0]["fill_type"] == t.id        # regions keep their type
        assert t.layers == RED                                   # and its look
        assert _placed_pixel(fresh, loaded.id) == (255, 0, 0)    # not the grey fallback


def test_reserved_name_renamed_type_follows_project_wins(qapp):
    """The renamed name still merges by name: a project type of that name wins."""
    path = _saved(RED, "cid", "Concrete")
    _rename_rows(path, {"cid": "(Custom)"})
    _table(ft.FillType("proj", "(Custom) (imported)", BLUE))
    fresh = Model_Space()
    fresh.load_blocks_from_files([path])
    assert [t.name for t in ft.project_table().all()] == ["(Custom) (imported)"]   # no second row
    loaded = fresh.get_block_definition(_read(path)["id"])
    assert loaded.primitives[0]["fill_type"] == "proj"


def test_multi_file_load_announces_added_types_once(qapp):
    """Group E review Minor 2: every bus notify repaints every live scene, so a
    batch load of N type-bearing files notifies (and emits sceneModified) once.
    The sceneModified baseline is the same two files loaded with the types
    already in the project (nothing merges; the load's own emits remain)."""
    _table(ft.FillType("a", "Alpha", RED), ft.FillType("b", "Beta", BLUE))
    p1 = block_library.save_to_library(_host("a", "Host A"))
    p2 = block_library.save_to_library(_host("b", "Host B"))

    def load(reset):
        if reset:
            ft.reset_project_table()
        else:
            _table(ft.FillType("a", "Alpha", RED), ft.FillType("b", "Beta", BLUE))
        fresh = Model_Space()
        bus, modified = [], []
        ft.fill_type_bus().changed.connect(lambda: bus.append(1))
        fresh.sceneModified.connect(lambda: modified.append(1))
        fresh._dirty = False
        summary = fresh.load_blocks_from_files([p1, p2])
        assert summary["loaded"] == ["Host A", "Host B"]
        return fresh, len(bus), len(modified)

    _fresh, bus0, base_modified = load(reset=False)
    assert bus0 == 0                                  # nothing merged, nothing announced
    fresh, bus, modified = load(reset=True)
    assert {"Alpha", "Beta"} <= {t.name for t in ft.project_table().all()}
    assert bus == 1 and modified == base_modified + 1
    assert fresh._dirty is True
    # the single-file reload path still announces its own merge
    ft.reset_project_table()
    hits = []
    ft.fill_type_bus().changed.connect(lambda: hits.append(1))
    assert fresh.reload_block_definition(_read(p1)["id"]) is True
    assert len(hits) == 1
