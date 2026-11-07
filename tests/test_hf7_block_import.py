"""HF7 D4, D7 (G7, G11): fills into the Block Editor."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import block_library, fill_types, hatch_tile, import_fills
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.constants import IMPORTED_SOLID_TYPE
from firepro3d.filled_region import FilledRegionItem
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests._hf7_helpers import extract, new_doc, ring_hatch, square

pytestmark = pytest.mark.usefixtures("qapp")    # Model_Space needs a QApplication


def _editor():
    proj = Model_Space()
    return proj, BlockEditorWidget(proj)


def _hatch(msp, name, *, scale=1.0, angle=0.0, x=0.0, layer="0"):
    h = msp.add_hatch(dxfattribs={"layer": layer})
    h.paths.add_polyline_path(square(x, 0, 100), is_closed=True, flags=1)
    h.set_pattern_fill(name, scale=scale, angle=angle)
    return h


def _regions(w):
    return list(w.editor_scene._filled_regions)


def _import(w, doc, tmp_path):
    geoms = extract(doc, tmp_path, preserve_curves=True)
    return w._add_imported_geoms(geoms, 1.0)


def test_solid_and_solid_hatch_become_regions_on_imported_solid(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    msp.add_solid([(0, 0), (10, 0), (0, 10), (10, 10)])
    h = ring_hatch(msp, x=20)
    h.rgb = (10, 20, 30)
    _import(w, doc, tmp_path)
    regions = _regions(w)
    t = fill_types.project_table().by_name(IMPORTED_SOLID_TYPE)
    assert len(regions) == 2 and all(r.fill_type == t.id for r in regions)
    assert all(r.outline is False for r in regions)
    assert len(regions[1]._loops) == 2
    assert regions[1].fill_layers.background.color == "#0a141e"


def test_white_solid_is_an_ordinary_region(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    h = ring_hatch(msp)
    h.rgb = (255, 255, 255)
    _import(w, doc, tmp_path)
    assert _regions(w)[0].fill_layers.background.color == "#ffffff"


def test_ring_hatch_imports_with_its_hole(qapp, tmp_path):
    """exact_loops are in source order, not depth-oriented: the region must still
    be a ring (the hole empty), whatever the winding of the children."""
    proj, w = _editor()
    doc, msp = new_doc()
    ring_hatch(msp)
    _import(w, doc, tmp_path)
    r = _regions(w)[0]
    box = r.path().boundingRect()
    in_ring = QPointF(box.left() + box.width() * 0.1, box.center().y())
    in_hole = box.center()
    assert r.path().contains(in_ring)
    assert not r.path().contains(in_hole)


def test_two_scales_share_one_block_and_type(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    _hatch(msp, "ANSI31", scale=2.0)
    _hatch(msp, "ANSI31", scale=6.0, x=200)
    _import(w, doc, tmp_path)
    regions = _regions(w)
    blocks = [d for d in proj._block_definitions.values() if d.library == "Imported"]
    types = [t for t in fill_types.project_table().all() if t.name.startswith("ANSI31 (imported)")]
    assert len(regions) == 2 and len(blocks) == 1 and len(types) == 1
    assert blocks[0].tile["size"] == "model" and blocks[0].series == "Patterns"
    a, b = (r.fill_layers.pattern for r in regions)
    assert a.ref == b.ref == blocks[0].id
    assert a.scale == 1.0 and b.scale == pytest.approx(3.0)


def test_rotated_copy_stays_separate(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    _hatch(msp, "ANSI31", scale=2.0)
    _hatch(msp, "ANSI31", scale=2.0, angle=30.0, x=200)
    _import(w, doc, tmp_path)
    assert len([d for d in proj._block_definitions.values() if d.library == "Imported"]) == 2


def test_later_import_finds_the_block(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    _hatch(msp, "ANSI37", scale=2.0)
    _import(w, doc, tmp_path)
    doc2, msp2 = new_doc()
    _hatch(msp2, "ANSI37", scale=4.0)
    _import(w, doc2, tmp_path)
    assert len([d for d in proj._block_definitions.values() if d.library == "Imported"]) == 1


def test_anonymous_pattern_is_named_hatch(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    h = _hatch(msp, "ANSI31", scale=2.0)
    h.dxf.pattern_name = "_USER"
    _import(w, doc, tmp_path)
    assert fill_types.project_table().by_name("Hatch (imported)") is not None


def test_unconvertible_gives_lines_boundary_and_report(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    _hatch(msp, "GRATE", scale=20.0, angle=151.72)
    geoms = extract(doc, tmp_path, preserve_curves=True)
    items, skipped, report = import_fills.build_items(geoms, lineweight=1.0, project_scene=proj)
    assert any(isinstance(i, LineItem) for i in items)
    assert not any(isinstance(i, FilledRegionItem) for i in items)
    assert report == [("GRATE", 1, "lines and boundary")]


def test_many_lines_keep_the_boundary_only(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(import_fills, "HATCH_IMPORT_MAX_EDIT_LINES", 1)
    proj, w = _editor()
    doc, msp = new_doc()
    _hatch(msp, "GRATE", scale=5.0, angle=151.72)
    items, _, report = import_fills.build_items(
        extract(doc, tmp_path, preserve_curves=True), lineweight=1.0, project_scene=proj)
    assert report[0][2] == "boundary only"
    assert not any(isinstance(i, LineItem) for i in items)


def test_clean_import_shows_no_dialog(qapp, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("firepro3d.themed_message.themed_info", lambda *a, **k: calls.append(a))
    proj, w = _editor()
    doc, msp = new_doc()
    ring_hatch(msp)
    _import(w, doc, tmp_path)
    assert calls == []


def test_report_dialog_lists_a_row(qapp, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("firepro3d.themed_message.themed_info", lambda *a, **k: calls.append(a))
    proj, w = _editor()
    doc, msp = new_doc()
    _hatch(msp, "GRATE", scale=20.0, angle=151.72)
    _import(w, doc, tmp_path)
    assert len(calls) == 1 and "GRATE" in calls[0][2]


def test_order_keys_follow_the_stream(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    msp.add_line((0, 0), (10, 0))
    ring_hatch(msp)
    msp.add_line((0, 5), (10, 5))
    items, _, _ = import_fills.build_items(
        extract(doc, tmp_path, preserve_curves=True), lineweight=1.0, project_scene=proj)
    zs = [i.to_dict()["draw_z"] for i in items]
    assert zs == sorted(zs) and all(-0.9 < z < -0.1 for z in zs)


def test_lines_only_import_path_is_unchanged(qapp, tmp_path):
    proj, w = _editor()
    doc, msp = new_doc()
    msp.add_line((0, 0), (10, 0))
    _import(w, doc, tmp_path)
    assert "draw_z" not in w.editor_scene._draw_lines[0].to_dict()


def test_text_beside_a_fill_is_skipped_not_raised(qapp, tmp_path):
    """Text is not a primitive the editor import produces (geometry_import skips
    it), so it never reaches set_draw_z; the fill still imports."""
    proj, w = _editor()
    doc, msp = new_doc()
    msp.add_text("LABEL", dxfattribs={"insert": (5, 5), "height": 3})
    ring_hatch(msp, x=50)
    added, skipped = _import(w, doc, tmp_path)
    assert len(_regions(w)) == 1 and skipped >= 1 and added >= 1


def test_same_pattern_converts_once(qapp, tmp_path, monkeypatch):
    calls = []
    real = hatch_tile.convert
    monkeypatch.setattr(hatch_tile, "convert", lambda f: calls.append(1) or real(f))
    proj, w = _editor()
    doc, msp = new_doc()
    for i in range(3):
        _hatch(msp, "ANSI31", scale=2.0, x=200 * i)
    _import(w, doc, tmp_path)
    assert len(_regions(w)) == 3 and len(calls) == 1


def test_import_is_one_undo_step_in_the_editor(qapp, tmp_path):
    proj, w = _editor()
    sc = w.editor_scene
    doc, msp = new_doc()
    ring_hatch(msp)
    msp.add_line((0, 0), (10, 0))
    before = len(sc._undo_stack)
    _import(w, doc, tmp_path)
    assert len(sc._undo_stack) == before + 1
    sc.undo()
    assert _regions(w) == [] and sc._draw_lines == []


def test_undoing_the_project_keeps_the_pattern_block(qapp, tmp_path):
    proj, w = _editor()
    proj.push_undo_state()
    doc, msp = new_doc()
    _hatch(msp, "ANSI31", scale=2.0)
    _import(w, doc, tmp_path)
    block = next(d for d in proj._block_definitions.values() if d.library == "Imported")
    proj.undo()
    assert block.id in proj._block_definitions
    assert _regions(w)[0].fill_layers.pattern.ref == block.id


def test_library_round_trip_into_a_fresh_project(qapp, tmp_path):
    """G7: the sequence of test_hf5_library_bundle's fresh-project test."""
    proj, w = _editor()
    doc, msp = new_doc()
    _hatch(msp, "ANSI31", scale=2.0)
    ring_hatch(msp, x=200)
    _import(w, doc, tmp_path)
    defn = w.commit_block("Imported Fills", "L", "S")
    path = block_library.save_to_library(defn, bundled=proj.block_registry.bundle_for(defn.id))
    fill_types.reset_project_table()
    fresh = Model_Space()
    assert fresh.load_blocks_from_files([path])["loaded"] == ["Imported Fills"]
    table = fill_types.project_table()
    t = table.by_name("ANSI31 (imported)")
    assert t is not None and table.by_name(IMPORTED_SOLID_TYPE) is not None
    assert fresh.get_block_definition(t.layers.pattern.ref).tile["size"] == "model"
