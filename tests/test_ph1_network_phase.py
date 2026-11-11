"""PH1 AC1 for pipes, sprinklers, water supply; fitting override persistence; split copies.

Raw sources: concept PD1 ("Pipe: the existing _properties["Phase"] row becomes
this field (no second key)"; "Sprinkler: an explicit key in the node entry";
"Fitting: phase_override stored in the node entry next to
fitting_display_overrides"); ids new/existing/demolition.
"""
import pytest
from PyQt6.QtCore import QPointF

from tests._ph1_helpers import (ADD, FIND, add_pipe, load, panel, ph1_cleanup,  # noqa: F401
                                save_raw, scene)

NET = ["pipe", "sprinkler", "water_supply"]


@pytest.mark.parametrize("kind", NET)
def test_phase_survives_save_and_load(qapp, tmp_path, kind):
    ms = scene()
    ADD[kind](ms).phase = "demolition"
    path, raw = save_raw(ms, tmp_path)
    if kind == "pipe":
        rec = raw["pipes"][0]
        assert rec["phase"] == "demolition" and "Phase" not in rec["properties"]
    elif kind == "sprinkler":
        rec = next(n for n in raw["nodes"] if n["sprinkler"])
        assert rec["sprinkler_phase"] == "demolition"
        assert "Phase" not in rec["sprinkler"]                 # not stored twice
    else:
        rec = raw["water_supply"]
        assert rec["phase"] == "demolition" and "Phase" not in rec["properties"]
    assert FIND[kind](load(path)).phase == "demolition"


@pytest.mark.parametrize("kind", NET)
def test_panel_row_edits_phase_as_one_undo_step(qapp, panel, kind):
    ms = scene()
    item = ADD[kind](ms)
    ms.push_undo_state()
    pos = ms._undo_pos
    shown = item.node if kind == "sprinkler" else item         # the canvas selects the node
    pm = panel(shown)
    pm._prop_widgets["Phase"].setCurrentText("Existing")
    assert item.phase == "existing" and ms._undo_pos == pos + 1
    ms.undo()
    assert FIND[kind](ms).phase == "new"
    ms.redo()
    assert FIND[kind](ms).phase == "existing"


def test_pipe_phase_is_no_longer_a_stored_property(qapp):
    p = add_pipe(scene())      # a bare Pipe(None, None) cannot format its ceiling-offset rows
    assert "Phase" not in p._properties
    row = p.get_properties()["Phase"]
    assert row["options"] == ["New", "Existing", "Demolition"]


def test_fitting_override_survives_file_and_undo(qapp, tmp_path):
    ms = scene()
    pipe = add_pipe(ms)
    pipe.node1.fitting.phase_override = "existing"
    path, raw = save_raw(ms, tmp_path)
    rec = next(n for n in raw["nodes"] if n.get("fitting_phase_override"))
    assert rec["fitting_phase_override"] == "existing"
    out = load(path)
    assert sorted(str(n.fitting.phase_override) for n in out.sprinkler_system.nodes) \
        == ["None", "existing"]
    ms.push_undo_state()
    ms._restore_network(ms._capture_network())
    assert sorted(str(n.fitting.phase_override) for n in ms.sprinkler_system.nodes) \
        == ["None", "existing"]


def test_splitting_a_pipe_keeps_its_phase(qapp):
    ms = scene()
    pipe = add_pipe(ms)
    pipe.phase = "existing"
    ms.split_pipe(pipe, QPointF(500.0, 0.0))
    assert [p.phase for p in ms.sprinkler_system.pipes] == ["existing", "existing"]


def test_vertical_split_keeps_its_phase(qapp):
    from firepro3d.constants import DEFAULT_CEILING_OFFSET_MM, DEFAULT_LEVEL
    from firepro3d.node import Node
    from firepro3d.pipe import Pipe
    ms = scene()
    na, nb = Node(0, 0), Node(0, 0)
    for n, z in ((na, 0.0), (nb, 3000.0)):
        ms.addItem(n); ms.sprinkler_system.add_node(n); n.z_pos = z
    pipe = ms.add_pipe(na, nb, _propagate_ceiling=False)
    pipe.phase = "demolition"
    t = Pipe(None, None)
    t.node1_ceiling_level = t.node2_ceiling_level = DEFAULT_LEVEL
    t.node1_ceiling_offset = t.node2_ceiling_offset = DEFAULT_CEILING_OFFSET_MM
    assert ms._pipe_ctl._find_or_split_vertical_at_z(QPointF(0, 0), 1500.0, t) is not None
    assert [p.phase for p in ms.sprinkler_system.pipes] == ["demolition", "demolition"]
