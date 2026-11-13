"""LW-DC T2 -- the scene-level weight reference sweep (weight_refs.py):
count, simultaneous retarget (swap) and exact journal restore across every
holder kind."""
import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d import paper_display as pd
from firepro3d import weight_refs as wr
from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef
from firepro3d.paper_space import Sheet
from firepro3d.text_item import TextAnnotationData, TextItem
from firepro3d.underlay import Underlay
from tests.test_leader_dependencies import LEADER, _note_def, _note_with_leader
from tests.wm2_support import nested_record, sprinkler_def

ALL_KINDS = {"ann", "lead_ann", "item", "lead_item", "raw", "inst",
             "lead_inst", "style_inst", "prim", "lead_prim", "sprim", "nrec"}
# one per sweep kind (12) + Blocks + 1 category + underlay default + layer
A_HOLDERS = len(ALL_KINDS) + 4


@pytest.fixture(autouse=True)
def _table():
    pd.set_project_line_weights([*pd.project_line_weights(),
                                 LineWeightDef("A", 0.40),
                                 LineWeightDef("B", 0.60)])
    pd.set_weight_aliases({})
    pd.set_model_blocks_weight(None)
    yield
    pd.set_weight_aliases({})
    pd.set_model_blocks_weight(None)
    pd.reset_project_line_weights()


@pytest.fixture
def settings(tmp_path):
    s = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    yield s


def _leader(w):
    return dict(LEADER, end="none", weight=w)


def _world(settings, a="A", b="B"):
    """A scene holding one holder of every kind named *a*, plus a few named
    *b* (a raw plan line and an underlay layer override)."""
    ms = Model_Space()
    # Model Blocks weight + its QSettings key, one paper category.
    pd.set_model_blocks_weight(a, canonical=False)
    settings.setValue("display/Blocks/line_weight", a)
    cats = pd.load_paper_categories(settings)
    cats["Wall"]["line_weight"] = a
    pd.save_paper_categories(cats, settings)
    # underlay default + a layer override (+ a b-named layer override)
    rec = Underlay(type="dxf", path="x.dxf", line_weight_name=a,
                   layer_overrides={"L1": {"line_weight": a},
                                    "L2": {"line_weight": b}})
    ms.underlays.append((rec, None))
    # sheet text: border + leader
    sheet = Sheet.create_default()
    ann = TextAnnotationData(text="s", border=True, border_weight=a,
                             leader=_leader(a))
    sheet.annotations.append(ann)
    ms._sheets = [sheet]
    # model text: border + leader
    txt = TextItem(TextAnnotationData(text="m", border=True, border_weight=a,
                                      leader=_leader(a)))
    ms.addItem(txt)
    ms._texts.append(txt)
    # styled raw plan line (a) and one named b
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["weight"] = a
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    lb = LineItem(QPointF(0, 5), QPointF(10, 5))
    lb.style["weight"] = b
    ms.addItem(lb)
    ms._draw_lines.append(lb)
    # definition: text border + leader, styled stroke, nested-record override
    spr = sprinkler_def()
    ms.register_block_definition(spr)
    prim_txt = TextItem(TextAnnotationData(
        text="d", border=True, border_weight=a, leader=_leader(a))).to_dict()
    pln = LineItem(QPointF(0, 0), QPointF(3, 0))
    pln.style["weight"] = a
    host = BlockDefinition.new(
        name="H", library="L", series="S", origin=(0.0, 0.0),
        primitives=[prim_txt, pln.to_dict(),
                    nested_record(spr.id, {"weight": a})])
    ms.register_block_definition(host)
    # placed block override; a Note with leader + border weight
    inst = ms.place_block_instance(spr.id, (0.0, 0.0), level=ms.active_level,
                                   overrides={"weight": a})
    ms.register_block_definition(_note_def())
    note = _note_with_leader(ms, end="none", weight=a)
    note.note["style"] = {"border_weight": a}
    return ms, {"rec": rec, "ann": ann, "txt": txt, "ln": ln, "lb": lb,
                "inst": inst, "note": note, "host": host}


def _snapshot(ms, settings):
    """Every observable holder value, by the sweep + the non-sweep holders."""
    refs = sorted((kind, id(r if not isinstance(r, tuple) else r[1]), name)
                  for name, (kind, r) in wr.iter_weight_refs(ms))
    cats = {k: v.get("line_weight")
            for k, v in pd.load_paper_categories(settings).items()}
    rec = ms.underlays[0][0]
    return (refs, cats, pd.model_blocks_weight(),
            settings.value("display/Blocks/line_weight"),
            rec.line_weight_name,
            {k: v.get("line_weight") for k, v in rec.layer_overrides.items()})


def test_every_sweep_kind_is_built_and_counted(qapp, settings):
    ms, _w = _world(settings)
    kinds = {kind for name, (kind, _r) in wr.iter_weight_refs(ms) if name == "A"}
    assert kinds == ALL_KINDS
    assert wr.weight_ref_count(ms, settings, "A") == A_HOLDERS
    assert wr.weight_ref_count(ms, settings, "B") == 2
    assert wr.weight_ref_count(ms, settings, "Nobody") == 0
    assert wr.is_weight_in_use(ms, settings, "A")
    assert not wr.is_weight_in_use(ms, settings, "Nobody")


def test_swap_is_simultaneous_and_restore_is_exact(qapp, settings):
    ms, w = _world(settings)
    before = _snapshot(ms, settings)
    journal = wr.retarget_weight_refs(ms, settings, {"A": "B", "B": "A"})
    # single hop: A -> B and B -> A (a sequential sweep would collapse them)
    assert wr.weight_ref_count(ms, settings, "B") == A_HOLDERS
    assert wr.weight_ref_count(ms, settings, "A") == 2
    assert pd.model_blocks_weight() == "B"
    assert settings.value("display/Blocks/line_weight") == "B"
    assert pd.load_paper_categories(settings)["Wall"]["line_weight"] == "B"
    assert w["rec"].line_weight_name == "B"
    assert w["rec"].layer_overrides["L1"]["line_weight"] == "B"
    assert w["rec"].layer_overrides["L2"]["line_weight"] == "A"
    assert w["lb"].style["weight"] == "A" and w["ln"].style["weight"] == "B"
    assert w["inst"].overrides["weight"] == "B"
    assert w["note"].note["leader"]["weight"] == "B"
    assert w["note"].note["style"]["border_weight"] == "B"
    assert w["ann"].border_weight == "B" and w["ann"].leader["weight"] == "B"
    host = ms.block_registry.get(w["host"].id)
    assert host.primitives[0]["border_weight"] == "B"
    assert host.primitives[2]["overrides"]["weight"] == "B"
    wr.restore_weight_refs(ms, settings, journal)
    assert _snapshot(ms, settings) == before
    assert wr.weight_ref_count(ms, settings, "A") == A_HOLDERS


def test_unmapped_names_are_untouched_and_journal_is_empty(qapp, settings):
    ms, _w = _world(settings)
    before = _snapshot(ms, settings)
    assert wr.retarget_weight_refs(ms, settings, {"Nobody": "A"}) == []
    assert _snapshot(ms, settings) == before


def test_blocks_key_absent_before_is_removed_on_restore(qapp, settings):
    ms = Model_Space()
    pd.set_model_blocks_weight("A", canonical=False)
    assert settings.value("display/Blocks/line_weight") is None
    j = wr.retarget_weight_refs(ms, settings, {"A": "B"})
    assert settings.value("display/Blocks/line_weight") == "B"
    wr.restore_weight_refs(ms, settings, j)
    assert settings.value("display/Blocks/line_weight") is None
    assert pd.model_blocks_weight() == "A"


def test_placed_block_override_is_written_raw_for_the_cancel_replay(qapp, settings):
    """With the Old->B alias live, retargeting B->Old must store the raw old
    name (not canonicalise it back to B), and restore puts B back."""
    ms = Model_Space()
    spr = sprinkler_def()
    ms.register_block_definition(spr)
    inst = ms.place_block_instance(spr.id, (0.0, 0.0), level=ms.active_level,
                                   overrides={"weight": "B"})
    pd.set_weight_aliases({"Old": "B"})
    j = wr.retarget_weight_refs(ms, settings, {"B": "Old"})
    assert inst.overrides["weight"] == "Old"
    wr.restore_weight_refs(ms, settings, j)
    assert inst.overrides["weight"] == "B"
