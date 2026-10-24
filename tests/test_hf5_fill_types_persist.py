"""HF5 Task 2 -- the fill-type table travels with the project (AC1, AC10)."""
import json

import pytest

import main as _main_module
from firepro3d.view_3d import View3D          # heavy import required before MainWindow
_main_module.View3D = View3D
from main import MainWindow

from firepro3d import fill_types as ft
from firepro3d.fill_layers import BackgroundLayer, FillLayers
from firepro3d.model_space import Model_Space
from tests._mainwindow_helpers import dispose_main_window

RED = FillLayers(BackgroundLayer("#ff0000", 1.0))


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    # Keep the real ~/.firepro3d autosave untouched and skip the template-push modal.
    recovery = str(tmp_path / "autosave" / "recovery.FPD")
    monkeypatch.setattr(MainWindow, "_autosave_path",
                        staticmethod(lambda: recovery))
    monkeypatch.setattr(MainWindow, "_maybe_offer_template_push",
                        lambda self: None)
    w = MainWindow()
    yield w
    dispose_main_window(w)


def test_save_open_round_trip(qapp, tmp_path):
    ft.reset_project_table()
    added = ft.project_table().add(ft.FillType(ft.new_id(), "Red", RED))
    ms = Model_Space()
    path = str(tmp_path / "p.fpd")
    ms.save_to_file(path)
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)["fill_types"]
    assert any(r["id"] == added.id and r["name"] == "Red" for r in rows)
    ft.reset_project_table()
    assert ft.project_table().get(added.id) is None
    Model_Space().load_from_file(path)
    assert ft.project_table().get(added.id).layers == RED


def test_old_file_without_key_gets_seed(qapp, tmp_path):
    ms = Model_Space()
    path = str(tmp_path / "old.fpd")
    ms.save_to_file(path)
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    payload.pop("fill_types")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    ft.set_project_table(ft.FillTypeTable([ft.FillType("x", "Leftover", RED)]))
    Model_Space().load_from_file(path)
    names = {t.name for t in ft.project_table().all()}
    assert "Leftover" not in names and "Solid Black" in names


def test_new_project_resets_to_seed(main_window):
    ft.project_table().add(ft.FillType(ft.new_id(), "Stale", RED))
    main_window._modified = False
    main_window.new_file()
    assert ft.project_table().by_name("Stale") is None
    assert ft.project_table().by_name("Solid Black") is not None


def test_new_project_table_holds_category_section_types_without_any_wall(main_window):
    """VC9 M1: the display defaults add Wall Section / Floor Section AFTER the reset,
    so a brand-new (wall-less) project already lists them in its table."""
    main_window._modified = False
    main_window.new_file()
    assert not main_window.scene._walls
    names = {t.name for t in ft.project_table().all()}
    assert {"Wall Section", "Floor Section"} <= names


def test_startup_installs_seed_over_stale_table(qapp, tmp_path, monkeypatch):
    """MainWindow() startup resets the store (AC10): a table left by a prior session is gone."""
    ft.set_project_table(ft.FillTypeTable([ft.FillType("x", "Stale", RED)]))
    recovery = str(tmp_path / "autosave" / "recovery.FPD")
    monkeypatch.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
    monkeypatch.setattr(MainWindow, "_maybe_offer_template_push", lambda self: None)
    w = MainWindow()
    try:
        assert ft.project_table().by_name("Stale") is None
        assert ft.project_table().by_name("Solid Black") is not None
        assert ft.project_table().by_name("Wall Section") is not None   # VC9 M1
        assert ft.project_table().by_name("Floor Section") is not None
    finally:
        dispose_main_window(w)


def test_saved_typed_block_region_resolves_against_the_files_own_types(qapp, tmp_path):
    """M8: the file's fill_types load before block definitions parse / compile, so a
    typed region inside a saved block draws its type, not the fallback grey."""
    from PyQt6.QtCore import QPointF
    from firepro3d.filled_region import FilledRegionItem
    from firepro3d.geometry_2d import LineItem
    from firepro3d.render_op import FILL

    ft.reset_project_table()
    typed = ft.project_table().add(ft.FillType(ft.new_id(), "t", RED))
    a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    region = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c),
                                            LineItem(c, d), LineItem(d, a)]])
    region.set_fill_type(typed.id)
    ms = Model_Space()
    defn = ms.commit_block_definition(block_id=None, name="Host", library="L", series="S",
                                      primitives=[region.to_dict()], origin=(0.0, 0.0),
                                      place_instance=False)
    path = str(tmp_path / "typed_block.fpd")
    ms.save_to_file(path)
    ft.reset_project_table()                      # a different session's table
    assert ft.project_table().get(typed.id) is None
    ms2 = Model_Space()
    ms2.load_from_file(path)
    ops = ms2._block_definitions[defn.id].render_ops()
    fills = [o for o in ops if o.kind == FILL]
    assert fills and fills[0].colour == "#ff0000"             # type t, not the fallback #808080


def test_duplicate_type_ids_repoint_and_stay_repointed_across_save_open(qapp, tmp_path):
    """Review: a name-duplicate type's regions (block definition record + typed region)
    re-point to the kept id on open and survive save / reopen, not 'missing'."""
    import json
    from PyQt6.QtCore import QPointF
    from firepro3d.filled_region import FilledRegionItem
    from firepro3d.geometry_2d import LineItem
    from firepro3d.render_op import FILL

    ft.reset_project_table()
    keep = ft.project_table().add(ft.FillType("keep", "Red", RED))
    a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    region = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)]])
    region.set_fill_type(keep.id)
    ms = Model_Space()
    defn = ms.commit_block_definition(block_id=None, name="Host", library="L", series="S",
                                      primitives=[region.to_dict()], origin=(0.0, 0.0),
                                      place_instance=False)
    p1 = str(tmp_path / "a.fpd")
    ms.save_to_file(p1)
    with open(p1, encoding="utf-8") as fh:
        payload = json.load(fh)
    payload["fill_types"].append({"id": "dup", "name": "red",
                                  "background": {"color": "#0000ff", "opacity": 1.0}})
    payload["block_definitions"][defn.id]["primitives"][0]["fill_type"] = "dup"
    with open(p1, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    p2 = str(tmp_path / "b.fpd")
    ft.reset_project_table()
    ms2 = Model_Space()
    ms2.load_from_file(p1)
    assert ms2._block_definitions[defn.id].primitives[0]["fill_type"] == "keep"
    ms2.save_to_file(p2)
    ft.reset_project_table()
    ms3 = Model_Space()
    ms3.load_from_file(p2)
    prim = ms3._block_definitions[defn.id].primitives[0]
    assert prim["fill_type"] == "keep" and ft.project_table().get("keep") is not None
    fills = [o for o in ms3._block_definitions[defn.id].render_ops() if o.kind == FILL]
    assert fills and fills[0].colour == "#ff0000"
    reg = FilledRegionItem.from_dict(prim)
    assert reg.fill_type == "keep" and not reg.fill_type_missing


def test_floor_override_alias_repoints_and_survives_save_open(qapp, tmp_path):
    """VC9 M2: a floor's per-item section_type naming a name-duplicate type's alias id
    opens as the kept id (not '? dup'), and stays so across a second save / open."""
    import json
    from PyQt6.QtCore import QPointF
    from firepro3d.floor_slab import FloorSlab

    ft.reset_project_table()
    ft.project_table().add(ft.FillType("keep", "Red", RED))
    ms = Model_Space()
    slab = FloorSlab([QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)])
    slab._display_overrides["section_type"] = "keep"
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    p1 = str(tmp_path / "a.fpd")
    ms.save_to_file(p1)
    with open(p1, encoding="utf-8") as fh:
        payload = json.load(fh)
    payload["fill_types"].append({"id": "dup", "name": "red",
                                  "background": {"color": "#0000ff", "opacity": 1.0}})
    assert len(payload["floor_slabs"]) == 1
    payload["floor_slabs"][0]["display_overrides"]["section_type"] = "dup"
    with open(p1, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    p2 = str(tmp_path / "b.fpd")
    ft.reset_project_table()
    ms2 = Model_Space()
    ms2.load_from_file(p1)
    assert ms2._floor_slabs[0]._display_overrides["section_type"] == "keep"
    ms2.save_to_file(p2)
    ft.reset_project_table()
    ms3 = Model_Space()
    ms3.load_from_file(p2)
    assert ms3._floor_slabs[0]._display_overrides["section_type"] == "keep"
    assert ft.project_table().get("keep") is not None
