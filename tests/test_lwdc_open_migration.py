"""LW-DC T3 -- project-open merge-by-width migration (LW-DC-8) and the
schema stamp on save.

Guards drive the REAL loader (``Model_Space.load_from_file``) on the shipped
pre-schema-2 fixtures. Expected paper mm per holder comes from the fixture's
own raw JSON weight table (a name missing from it -> its old factory mm,
MW-6), never from the module under test.
"""
import json
import shutil
from pathlib import Path

import pytest

from firepro3d import paper_display as pd
from firepro3d import weight_refs as wr
from firepro3d.block_definition import BlockDefinition
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef
from tests.wm2_support import sprinkler_def

FIXDIR = Path(__file__).parent / "fixtures"
FIXTURES = ["hf5_legacy.fpd", "ph1_pre_phasing_v12.fpd"]
# MW-6 old factory mm for a name a file's own table lacks (raw, hand-written).
_OLD_FACTORY_MM = {"Very Light": .13, "Light": .18, "Medium": .25, "Heavy": .35,
                   "Very Heavy": .50, "Thinnest": .18, "Thinner": .25, "Thin": .35,
                   "Thick": .50, "Thickest": .70}
_MADE = []


@pytest.fixture(autouse=True)
def _clean(qapp):
    pd.reset_project_line_weights()
    pd.set_model_blocks_weight(None)
    yield
    for ms in _MADE:
        ms.cleanup()
    _MADE.clear()
    pd.set_weight_aliases({})
    pd.set_model_blocks_weight(None)
    pd.reset_project_line_weights()


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    _MADE.append(ms)
    return ms


def _raw_mm(raw_table, name):
    by = {e["name"]: e["width_mm"] for e in raw_table}
    return by[name] if name in by else _OLD_FACTORY_MM[name]


_CYCLE = ["Thinnest", "Thin", "Thinner", "Thick", "Light", "Thickest"]


def _inject_by_name_weights(payload):
    """Give every stroke style in the file's block definitions a legacy weight
    name (cycled over MW names, one a name the table lacks) so the sweep has
    holders; returns how many were set."""
    n = 0

    def walk(o):
        nonlocal n
        if isinstance(o, dict):
            st = o.get("style")
            if isinstance(st, dict) and "weight" in st:
                st["weight"] = _CYCLE[n % len(_CYCLE)]
                n += 1
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(payload.get("block_definitions"))
    return n


def _holders(ms):
    return [(kind, name) for name, (kind, _r) in wr.iter_weight_refs(ms)]


@pytest.mark.parametrize("fixture", FIXTURES)
def test_legacy_fixture_open_keeps_paper_mm(fixture, tmp_path, monkeypatch):
    src = tmp_path / fixture
    shutil.copyfile(FIXDIR / fixture, src)            # never touch the fixture
    payload = json.loads(src.read_text(encoding="utf-8"))
    assert "line_weight_schema" not in payload["paper_display"]
    injected = _inject_by_name_weights(payload)
    src.write_text(json.dumps(payload), encoding="utf-8")
    assert injected or fixture.startswith("ph1")
    raw_table = payload["paper_display"]["line_weights"]
    raw_cats = {k: v["line_weight"] for k, v in payload["paper_display"]["categories"].items()
                if v.get("line_weight")}
    raw_blocks = payload["display_settings"]["Blocks"]["line_weight"]

    # Old names per holder, in sweep order: the same load with the migration off.
    monkeypatch.setattr(pd, "apply_pending_weight_migration", lambda *a, **k: False)
    old = _scene()
    assert old.load_from_file(str(src))
    old_names = _holders(old)
    assert bool(old_names) == bool(injected)
    monkeypatch.undo()

    ms = _scene()
    assert ms.load_from_file(str(src))
    new = _holders(ms)
    assert [k for k, _ in new] == [k for k, _ in old_names]
    assert len(new) == len(old_names)
    live = set(pd.weight_names())
    for (kind, new_name), (_k, old_name) in zip(new, old_names):
        assert new_name in live, (kind, new_name)
        assert pd.resolve_line_weight_mm(new_name) == pytest.approx(
            _raw_mm(raw_table, old_name)), (kind, old_name, new_name)
    assert {d.name for d in pd.DEFAULT_LINE_WEIGHTS} <= {d.name for d in pd.project_line_weights()}
    assert [d.name for d in pd.project_line_weights()][:7] == [
        d.name for d in pd.DEFAULT_LINE_WEIGHTS]

    # Categories + Model Blocks weight: through the loader's own payload, then
    # the second apply (apply_paper_display_from_project) must be idempotent.
    pd.apply_paper_display_from_project(ms._loaded_paper_display)
    assert [d.name for d in pd.project_line_weights()][:7] == [
        d.name for d in pd.DEFAULT_LINE_WEIGHTS]
    cats = pd.load_paper_categories()
    for key, old_name in raw_cats.items():
        assert cats[key]["line_weight"] in live
        assert pd.resolve_line_weight_mm(cats[key]["line_weight"]) == pytest.approx(
            _raw_mm(raw_table, old_name)), key
    blocks_new = ms._loaded_display_settings["Blocks"]["line_weight"]
    assert blocks_new in live
    assert pd.resolve_line_weight_mm(blocks_new) == pytest.approx(
        _raw_mm(raw_table, raw_blocks))


def test_second_apply_is_idempotent_and_stashes_nothing(tmp_path):
    src = tmp_path / "h.fpd"
    shutil.copyfile(FIXDIR / "hf5_legacy.fpd", src)
    ms = _scene()
    assert ms.load_from_file(str(src))
    table = [d.to_dict() for d in pd.project_line_weights()]
    pd.apply_paper_display_from_project(ms._loaded_paper_display)
    pd.apply_paper_display_from_project(ms._loaded_paper_display)
    assert [d.to_dict() for d in pd.project_line_weights()] == table
    assert pd._PENDING_LW_MIGRATION is None


def _mw_scene_with_custom_thin():
    """A project whose table has a CUSTOM 'Thin' 0.30 (a Default-name clash)
    and a text-with-border definition + placed block both naming 'Thin'."""
    pd.set_project_line_weights([LineWeightDef("Thin", .30), LineWeightDef("My Pen", .40)])
    ms = _scene()
    spr = sprinkler_def({"circle": "Thin", "cross": "Thin", "deflector": "Thin"})
    ms.register_block_definition(spr)
    from firepro3d.text_item import TextAnnotationData, TextItem
    prim_txt = TextItem(TextAnnotationData(
        text="d", border=True, border_weight="Thin")).to_dict()
    host = BlockDefinition.new(name="H", library="L", series="S",
                               origin=(0.0, 0.0), primitives=[prim_txt])
    ms.register_block_definition(host)
    ms.place_block_instance(spr.id, (0.0, 0.0), level=ms.active_level,
                            overrides={"weight": "Thin"})
    return ms, host


def test_custom_thin_clash_becomes_thin_old_at_030_and_save_reopen_is_stable(tmp_path):
    ms, host = _mw_scene_with_custom_thin()
    path = tmp_path / "c.fpd"
    assert ms.save_to_file(str(path), backup=False)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["paper_display"]["line_weight_schema"] == pd.LINE_WEIGHT_SCHEMA
    del payload["paper_display"]["line_weight_schema"]      # a pre-schema-2 file
    path.write_text(json.dumps(payload), encoding="utf-8")

    pd.reset_project_line_weights()
    out = _scene()
    assert out.load_from_file(str(path))
    names = [n for _k, n in _holders(out)]
    assert names and set(names) == {"Thin (old)"}
    assert pd.resolve_line_weight_mm("Thin (old)") == pytest.approx(.30)
    assert pd.resolve_line_weight_mm("Thin") == pytest.approx(.18)       # the Default
    assert pd.resolve_line_weight_mm("My Pen") == pytest.approx(.40)

    # Save -> reopen: stamped schema 2, no second migration, names stable.
    path2 = tmp_path / "c2.fpd"
    assert out.save_to_file(str(path2), backup=False)
    saved = json.loads(path2.read_text(encoding="utf-8"))
    assert saved["paper_display"]["line_weight_schema"] == 2
    table = [d.to_dict() for d in pd.project_line_weights()]
    pd.reset_project_line_weights()
    again = _scene()
    assert again.load_from_file(str(path2))
    assert pd._PENDING_LW_MIGRATION is None
    assert {n for _k, n in _holders(again)} == {"Thin (old)"}
    assert [d.to_dict() for d in pd.project_line_weights()] == table


def test_schema2_table_installs_with_missing_defaults_added():
    pd.apply_project_weights({"line_weight_schema": 2,
                              "line_weights": [{"name": "Pen", "width_mm": .4}]},
                             stash=True)
    assert pd._PENDING_LW_MIGRATION is None
    assert {d.name for d in pd.DEFAULT_LINE_WEIGHTS} <= {d.name for d in pd.project_line_weights()}
    assert "Pen" in pd.weight_names()


def test_unstamped_table_installs_unchanged_then_stashes():
    rows = [{"name": "Thin", "width_mm": .35}, {"name": "Thick", "width_mm": .50}]
    pd.apply_project_weights({"line_weights": rows}, stash=True)
    assert [(d.name, d.width_mm) for d in pd.project_line_weights()] == [
        ("Thin", .35), ("Thick", .50)]
    assert pd._PENDING_LW_MIGRATION is not None
    pd.apply_project_weights({"line_weights": rows})          # no stash: cleared
    assert pd._PENDING_LW_MIGRATION is None


# --- Fix round 1: F3 (async underlays), F4 (table-less), F5 (mid-load rows) ---

_MW_ROWS = [("Thinnest", .18), ("Thinner", .25), ("Thin", .35),
            ("Thick", .50), ("Thickest", .70)]


def _unstamped(path, mutate):
    """Re-write a saved project as a pre-schema-2 file; *mutate(payload)*."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    pdsp = payload.setdefault("paper_display", {})
    pdsp.pop("line_weight_schema", None)
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _wait(cond, timeout=30.0):
    import time
    from PyQt6.QtWidgets import QApplication
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    return cond()


def test_f3_async_underlay_weight_migrates_after_the_build(qapp, tmp_path):
    """MW project, underlay names "Thin" (0.35 in the file's own table), cache
    miss -> the record is built by the worker AFTER load_from_file returns."""
    import ezdxf
    from firepro3d.underlay import Underlay
    dxf = tmp_path / "u.dxf"
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (100, 0), dxfattribs={"layer": "0"})
    doc.saveas(str(dxf))
    ms = _scene()
    rec = Underlay(type="dxf", path=str(dxf), line_weight_name="Thin",
                   layer_overrides={"0": {"line_weight": "Thin"}})
    ms._create_underlay_placeholder(rec)
    path = tmp_path / "p.fpd"
    assert ms.save_to_file(str(path), backup=False)
    raw_rows = [{"name": n, "width_mm": mm} for n, mm in _MW_ROWS]
    _unstamped(path, lambda p: p["paper_display"].update(
        line_weights=raw_rows, line_weight_aliases={}))
    raw_mm = {r["name"]: r["width_mm"] for r in raw_rows}["Thin"]      # 0.35

    pd.reset_project_line_weights()
    out = _scene()
    assert out.load_from_file(str(path))
    assert _wait(lambda: bool(out.underlays)), "async underlay never built"
    built = out.underlays[0][0]
    assert pd.resolve_line_weight_mm(built.line_weight_name) == pytest.approx(raw_mm)
    ov = built.layer_overrides["0"]["line_weight"]
    assert pd.resolve_line_weight_mm(ov) == pytest.approx(raw_mm)
    assert built.line_weight_name in pd.weight_names()


def test_f3_cache_hit_underlay_is_migrated_once(qapp, tmp_path):
    """A cache-hit underlay is built DURING load from the already-migrated
    payload; the end-of-load sweep must not map it a second time. "Thinnest"
    (0.18) is the chain case: one hop -> Default "Thin" (0.18), a second hop
    would read that as MW "Thin" (0.35) -> "Medium"."""
    import ezdxf
    from firepro3d.underlay import Underlay
    dxf = tmp_path / "u.dxf"
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (100, 0), dxfattribs={"layer": "0"})
    doc.saveas(str(dxf))
    raw_rows = [{"name": n, "width_mm": mm} for n, mm in _MW_ROWS]
    raw_mm = {r["name"]: r["width_mm"] for r in raw_rows}["Thinnest"]   # 0.18

    # Build the underlay once (async), then save: the save writes its cache.
    ms = _scene()
    ms._create_underlay_placeholder(Underlay(
        type="dxf", path=str(dxf), line_weight_name="Thin",
        layer_overrides={"0": {"line_weight": "Thin"}}))
    seed = tmp_path / "seed.fpd"
    assert ms.save_to_file(str(seed), backup=False)
    first = _scene()
    assert first.load_from_file(str(seed))
    assert _wait(lambda: bool(first.underlays)), "async underlay never built"
    path = tmp_path / "p.fpd"
    assert first.save_to_file(str(path), backup=False)

    def old(p):
        p["paper_display"].update(line_weights=raw_rows, line_weight_aliases={})
        for u in p["underlays"]:
            u["line_weight_name"] = "Thinnest"
            u["layer_overrides"] = {"0": {"line_weight": "Thinnest"}}
    _unstamped(path, old)

    pd.reset_project_line_weights()
    out = _scene()
    assert out.load_from_file(str(path))
    assert out.underlays, "expected a synchronous cache-hit build during load"
    built = out.underlays[0][0]
    assert pd.resolve_line_weight_mm(built.line_weight_name) == pytest.approx(raw_mm)
    ov = built.layer_overrides["0"]["line_weight"]
    assert pd.resolve_line_weight_mm(ov) == pytest.approx(raw_mm)


def test_f4_tableless_file_maps_old_names_statically(qapp, tmp_path):
    """A pre-LT1 file has no table: an old "Medium" is 0.25 mm (base value)
    -> Default "Fine", not the schema-2 template's 0.35 "Medium"."""
    ms = _scene()
    ms.register_block_definition(sprinkler_def(
        {"circle": "Medium", "cross": "Medium", "deflector": "Medium"}))
    path = tmp_path / "t.fpd"
    assert ms.save_to_file(str(path), backup=False)

    def strip(p):
        p["paper_display"] = {"categories": {"Wall": {"line_weight": "Medium"}}}
    _unstamped(path, strip)

    pd.reset_project_line_weights()
    out = _scene()
    assert out.load_from_file(str(path))
    pd.apply_paper_display_from_project(out._loaded_paper_display)
    old_medium = _OLD_FACTORY_MM["Medium"]                              # 0.25
    names = [n for _k, n in _holders(out)]
    assert names and all(pd.resolve_line_weight_mm(n) == pytest.approx(old_medium)
                         for n in names)
    wall = pd.load_paper_categories()["Wall"]["line_weight"]
    assert pd.resolve_line_weight_mm(wall) == pytest.approx(old_medium)


def test_f5_row_added_mid_load_survives_the_migration(qapp, tmp_path, monkeypatch):
    """A library merge that adds "Pen" 0.6 between the stash and the apply
    must not lose the row (nor the refs naming it)."""
    ms = _scene()
    ms.register_block_definition(sprinkler_def(
        {"circle": "Pen", "cross": "Pen", "deflector": "Pen"}))
    path = tmp_path / "m.fpd"
    assert ms.save_to_file(str(path), backup=False)
    raw_rows = [{"name": n, "width_mm": mm} for n, mm in _MW_ROWS]
    _unstamped(path, lambda p: p["paper_display"].update(
        line_weights=raw_rows, line_weight_aliases={}))

    real = pd.apply_pending_weight_migration

    def with_merge(*a, **k):
        pd.merge_project_line_weights({"Pen": 0.6})   # what the mid-load merge does
        return real(*a, **k)
    monkeypatch.setattr(pd, "apply_pending_weight_migration", with_merge)
    pd.reset_project_line_weights()
    out = _scene()
    assert out.load_from_file(str(path))
    assert "Pen" in pd.weight_names()
    assert pd.resolve_line_weight_mm("Pen") == pytest.approx(0.6)
    assert {n for _k, n in _holders(out)} == {"Pen"}


@pytest.mark.parametrize("fixture", FIXTURES)
def test_f8_open_through_mainwindow_keeps_paper_mm(fixture, tmp_path, monkeypatch):
    """The real entry point: ``MainWindow._apply_loaded_file`` (open + crash
    recovery), not a hand-copied load sequence. Holder names are injected
    into a COPY of the fixture; expected mm come from its raw JSON table."""
    import main as _m
    from firepro3d.view_3d import View3D
    from tests._mainwindow_helpers import dispose_main_window
    _m.View3D = View3D
    src = tmp_path / fixture
    shutil.copyfile(FIXDIR / fixture, src)
    payload = json.loads(src.read_text(encoding="utf-8"))
    assert "line_weight_schema" not in payload["paper_display"]
    injected = _inject_by_name_weights(payload)
    src.write_text(json.dumps(payload), encoding="utf-8")
    raw_table = payload["paper_display"]["line_weights"]
    raw_cats = {k: v["line_weight"] for k, v in payload["paper_display"]["categories"].items()
                if v.get("line_weight")}
    raw_blocks = payload["display_settings"]["Blocks"]["line_weight"]
    # Old names per holder: the same file loaded with the migration off (not
    # every injected style is a holder - only what the sweep reaches).
    monkeypatch.setattr(pd, "apply_pending_weight_migration", lambda *a, **k: False)
    old = _scene()
    assert old.load_from_file(str(src))
    old_names = [n for _k, n in _holders(old)]
    assert bool(old_names) == bool(injected)
    monkeypatch.undo()
    pd.reset_project_line_weights()
    pd.set_model_blocks_weight(None)
    expected = sorted(_raw_mm(raw_table, n) for n in old_names)

    monkeypatch.setattr(_m.MainWindow, "_maybe_offer_template_push", lambda self: None)
    w = _m.MainWindow()
    try:
        assert w._apply_loaded_file(str(src)) is not False
        got = sorted(pd.resolve_line_weight_mm(n)
                     for n, _r in wr.iter_weight_refs(w.scene))
        assert got == pytest.approx(expected)
        assert [d.name for d in pd.project_line_weights()][:7] == [
            d.name for d in pd.DEFAULT_LINE_WEIGHTS]
        cats = pd.load_paper_categories()
        for key, old_name in raw_cats.items():
            assert pd.resolve_line_weight_mm(cats[key]["line_weight"]) == pytest.approx(
                _raw_mm(raw_table, old_name)), key
        assert pd.resolve_line_weight_mm(pd.model_blocks_weight()) == pytest.approx(
            _raw_mm(raw_table, raw_blocks))
    finally:
        dispose_main_window(w)
