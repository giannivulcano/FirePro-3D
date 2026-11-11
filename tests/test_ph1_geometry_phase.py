"""PH1 AC1 / D-PH3 for the to_dict kinds: the phase survives save/load and undo,
and the shared Phase row edits it through the real panel.

Raw sources: concept PD1 (status ids "new"/"existing"/"demolition", the shared
"Phase" row is an enum of the registry names "New"/"Existing"/"Demolition");
spec "Edge Cases": a file without a phase key -> New.
"""
import pytest

from tests._ph1_helpers import ADD, FIND, load, panel, ph1_cleanup, save_raw, scene  # noqa: F401

KINDS = ["wall", "opening", "floor_slab", "floor_opening", "roof", "room"]
RAW = {   # where each kind's record sits in the saved payload
    "wall": lambda p: p["walls"][0],
    "opening": lambda p: p["walls"][0]["openings"][0],
    "floor_slab": lambda p: p["floor_slabs"][0],
    "floor_opening": lambda p: p["floor_slabs"][0]["openings"][0],
    "roof": lambda p: p["roofs"][0],
    "room": lambda p: p["rooms"][0],
}


@pytest.mark.parametrize("kind", KINDS)
def test_phase_survives_save_and_load(qapp, tmp_path, kind):
    ms = scene()
    ADD[kind](ms).phase = "demolition"
    path, raw = save_raw(ms, tmp_path)
    assert RAW[kind](raw)["phase"] == "demolition"          # the id is what is stored
    assert FIND[kind](load(path)).phase == "demolition"


@pytest.mark.parametrize("kind", KINDS)
def test_new_writes_no_key_and_a_missing_key_reads_new(qapp, tmp_path, kind):
    ms = scene()
    ADD[kind](ms)
    path, raw = save_raw(ms, tmp_path)
    assert "phase" not in RAW[kind](raw)
    assert FIND[kind](load(path)).phase == "new"


@pytest.mark.parametrize("kind", KINDS)
def test_panel_row_edits_phase_as_one_undo_step(qapp, panel, kind):
    ms = scene()
    item = ADD[kind](ms)
    ms.push_undo_state()
    pos = ms._undo_pos
    pm = panel(item)
    row = item.get_properties()["Phase"]
    assert row["options"] == ["New", "Existing", "Demolition"] and row["value"] == "New"
    pm._prop_widgets["Phase"].setCurrentText("Existing")
    assert item.phase == "existing"
    assert ms._undo_pos == pos + 1
    ms.undo()
    assert FIND[kind](ms).phase == "new"
    ms.redo()
    assert FIND[kind](ms).phase == "existing"


def test_opening_keeps_its_own_phase_in_a_demolished_wall(qapp, tmp_path):
    """D-PH16: openings keep their own phase."""
    ms = scene()
    op = ADD["opening"](ms)
    op._wall.phase = "demolition"
    path, _raw = save_raw(ms, tmp_path)
    out = load(path)
    assert FIND["wall"](out).phase == "demolition"
    assert FIND["opening"](out).phase == "new"
