"""LW-DC T5 -- library merge by width (LW-DC-10).

Guards load the REAL fixtures tests/fixtures/blocks/{sprinkler_2,pipe_break}.fpdb
through ``Model_Space.load_blocks_from_files`` into a Defaults project; the
expected paper mm per stroke is the mm in the file's own raw bundled
``weights`` map for that stroke's authored name, never the module under test.
"""
import json
import shutil
from pathlib import Path

import pytest

from firepro3d import block_library
from firepro3d import paper_display as pd
from firepro3d import weight_refs as wr
from firepro3d.block_definition import BlockDefinition
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef
from firepro3d.text_item import TextAnnotationData, TextItem

FIXDIR = Path(__file__).parent / "fixtures" / "blocks"


@pytest.fixture(autouse=True)
def _defaults(qapp):
    pd.set_weight_aliases({})
    pd.set_project_line_weights(pd.DEFAULT_LINE_WEIGHTS)
    yield
    pd.set_weight_aliases({})
    pd.reset_project_line_weights()


def _stroke_weights(prims):
    """Every ``style.weight`` of a primitive record list, in document order,
    at any depth (raw JSON walk)."""
    out = []

    def walk(o):
        if isinstance(o, dict):
            st = o.get("style")
            if isinstance(st, dict) and "weight" in st:
                out.append(st["weight"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(prims)
    return out


@pytest.mark.parametrize("fixture", ["sprinkler_2.fpdb", "pipe_break.fpdb"])
def test_fixture_strokes_draw_at_their_authored_mm(fixture, tmp_path):
    src = tmp_path / fixture
    shutil.copyfile(FIXDIR / fixture, src)             # never touch the fixture
    raw = json.loads(src.read_text(encoding="utf-8"))
    authored = _stroke_weights(raw["primitives"])
    assert authored and set(authored) == {"Thin"}
    want = [raw["weights"][n] for n in authored]
    assert want == [0.35] * len(want)                  # raw source: Thin was .35

    ms = Model_Space()
    try:
        res = ms.load_blocks_from_files([str(src)])
        assert not res["failed"] and not res["refused"]
        defn = ms._block_definitions[res["ids"][str(src)]]
        got = _stroke_weights(defn.primitives)
        assert len(got) == len(want)
        assert [pd.resolve_line_weight_mm(n) for n in got] == pytest.approx(want)
        assert set(got) == {"Medium"}                  # merged into the Default
        assert [d.name for d in pd.project_line_weights()] == [
            d.name for d in pd.DEFAULT_LINE_WEIGHTS]   # no stray row added
    finally:
        ms.cleanup()


def _lib_text_def(weight, mm, name="Tag"):
    """Save a text definition authored in a project whose *weight* is *mm*."""
    pd.set_project_line_weights([LineWeightDef(weight, mm)])
    prim = TextItem(TextAnnotationData(text="X", border=True,
                                       border_weight=weight)).to_dict()
    defn = BlockDefinition.new(name=name, library="Lib", series="S",
                               primitives=[prim], origin=(0.0, 0.0))
    path = block_library.save_to_library(defn)
    pd.set_project_line_weights(pd.DEFAULT_LINE_WEIGHTS)
    return path


def _load_text_weight(path):
    ms = Model_Space()
    try:
        res = ms.load_blocks_from_files([path])
        defn = ms._block_definitions[res["ids"][path]]
        return [p["border_weight"] for p in defn.primitives if p.get("type") == "text"]
    finally:
        ms.cleanup()


def test_synthetic_thin_035_names_medium_and_draws_035(qapp):
    path = _lib_text_def("Thin", 0.35)
    assert json.loads(Path(path).read_text(encoding="utf-8"))["weights"] == {"Thin": 0.35}
    (name,) = _load_text_weight(path)
    assert name == "Medium"
    assert pd.resolve_line_weight_mm(name) == pytest.approx(0.35)


def test_unmatched_mm_is_added_as_custom_old(qapp):
    path = _lib_text_def("Thin", 0.33)                 # no row of .33 exists
    (name,) = _load_text_weight(path)
    assert name == "Thin (old)"
    assert pd.resolve_line_weight_mm("Thin (old)") == pytest.approx(0.33)
    assert pd.resolve_line_weight_mm("Thin") == pytest.approx(0.18)    # Default untouched
    assert not pd.is_default_weight("Thin (old)")


def test_same_mm_row_is_left_alone(qapp):
    path = _lib_text_def("Thin", 0.18)
    (name,) = _load_text_weight(path)
    assert name == "Thin"
    assert [d.name for d in pd.project_line_weights()] == [
        d.name for d in pd.DEFAULT_LINE_WEIGHTS]


def test_absent_name_is_added_under_its_name(qapp):
    path = _lib_text_def("Pen X", 0.42)
    (name,) = _load_text_weight(path)
    assert name == "Pen X"
    assert pd.resolve_line_weight_mm("Pen X") == pytest.approx(0.42)


def test_merge_returns_added_and_mapping(qapp):
    added, mapping = pd.merge_project_line_weights(
        {"Thinnest": 0.18, "Thin": 0.35, "Thin2": 0.33, "Pen": 0.42})
    assert mapping == {"Thinnest": "Thin", "Thin": "Medium"}
    assert added == ["Thin2", "Pen"]


def test_retarget_definition_refs_is_simultaneous_and_covers_every_kind():
    from tests.wm2_support import nested_record, sprinkler_def
    spr = sprinkler_def({"circle": "A", "cross": "B", "deflector": "A"})
    txt = TextItem(TextAnnotationData(
        text="d", border=True, border_weight="A",
        leader={"type": "straight", "end": "none", "weight": "B"})).to_dict()
    host = BlockDefinition.new(
        name="H", library="L", series="S", origin=(0.0, 0.0),
        primitives=[txt, nested_record(spr.id, {"weight": "A"})])
    n = wr.retarget_definition_refs([spr, host], {"A": "B", "B": "A"})
    assert _stroke_weights(spr.primitives) == ["B", "A", "B"]          # swapped
    t = host.primitives[0]
    assert (t["border_weight"], t["leader"]["weight"]) == ("B", "A")
    assert host.primitives[1]["overrides"]["weight"] == "B"
    assert n == 6
    assert wr.retarget_definition_refs([spr], {}) == 0


def test_reload_remaps_a_bundled_nested_definition(qapp):
    """Reload merges the weights BEFORE _add_bundled, so a nested definition
    the reload re-adds is re-pointed too (the reordered site)."""
    from tests.wm2_support import nested_record
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35)])
    nest = BlockDefinition.new(
        name="Nest", library="Lib", series="S", origin=(0.0, 0.0),
        primitives=[TextItem(TextAnnotationData(
            text="n", border=True, border_weight="Thin")).to_dict()])
    host = BlockDefinition.new(name="Host", library="Lib", series="S", origin=(0.0, 0.0),
                               primitives=[nested_record(nest.id)])
    path = block_library.save_to_library(host, bundled={nest.id: nest.to_dict()})
    pd.set_project_line_weights(pd.DEFAULT_LINE_WEIGHTS)
    ms = Model_Space()
    try:
        res = ms.load_blocks_from_files([path])
        bid = res["ids"][path]
        assert [p["border_weight"] for p in ms._block_definitions[nest.id].primitives] == ["Medium"]
        del ms._block_definitions[nest.id]            # force the reload to re-add it
        assert ms.reload_block_definition(bid)
        (prim,) = ms._block_definitions[nest.id].primitives
        assert prim["border_weight"] == "Medium"
        assert pd.resolve_line_weight_mm(prim["border_weight"]) == pytest.approx(0.35)
    finally:
        ms.cleanup()
