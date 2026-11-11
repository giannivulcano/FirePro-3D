"""PH1 AC2 (D-PH4) and the effective_phase reader (PD1).

Raw sources: D-PH4 "any New -> New; else any Existing -> Existing; else
Demolition; a per-fitting override"; ruling 2026-11-11 "Fitting Phase row on
the node's panel, Auto (<derived>) plus each status; picking Auto clears the
override"; PD1 "block contents -> outermost instance, elevation proxies -> their
_ROLE_SOURCE element"; D-PH3 datum/annotation items carry none.
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsRectItem

from firepro3d import phase_registry as pr
from tests._ph1_helpers import (add_block, add_pipe, add_wall, panel,  # noqa: F401
                                ph1_cleanup, scene)


def _junction(ms, phases):
    """A centre node with one pipe per phase (up to the 4-pipe cap)."""
    hub = ms.add_node(0.0, 0.0)
    ends = [(1000.0, 0.0), (0.0, 1000.0), (-1000.0, 0.0), (0.0, -1000.0)]
    for (x, y), ph in zip(ends, phases):
        ms.add_pipe(hub, ms.add_node(x, y)).phase = ph
    return hub


@pytest.mark.parametrize("phases, expected", [
    (("new", "existing", "demolition"), "new"),        # any New -> New
    (("existing", "demolition"), "existing"),          # else any Existing -> Existing
    (("demolition", "demolition"), "demolition"),      # else Demolition
    (("existing", "existing", "existing", "existing"), "existing"),
], ids=["tee-any-new", "elbow-existing", "elbow-demolition", "cross-existing"])
def test_fitting_derives_from_all_connected_pipes(qapp, phases, expected):
    ms = scene()
    hub = _junction(ms, phases)
    assert pr.effective_phase(hub.fitting) == expected


def test_override_wins_and_auto_clears_it_through_the_node_panel(qapp, panel):
    ms = scene()
    hub = _junction(ms, ("new", "existing"))
    ms.push_undo_state()
    pos = ms._undo_pos
    pm = panel(hub)
    row = hub.get_properties()["Fitting Phase"]
    assert row["options"] == ["Auto (New)", "New", "Existing", "Demolition"]
    assert row["value"] == "Auto (New)"
    pm._prop_widgets["Fitting Phase"].setCurrentText("Demolition")
    assert hub.fitting.phase_override == "demolition"
    assert pr.effective_phase(hub.fitting) == "demolition"
    assert ms._undo_pos == pos + 1
    pm2 = panel(hub)
    pm2._prop_widgets["Fitting Phase"].setCurrentText("Auto (New)")
    assert hub.fitting.phase_override is None
    assert pr.effective_phase(hub.fitting) == "new"


def test_pipe_panel_node_sections_show_no_fitting_phase_row(qapp, panel):
    """I1: the pipe panel's NODE 1 / NODE 2 loop (property_manager.py:690-742) turns
    every non level_ref / label row into a free-text field; the Fitting Phase
    picker belongs to the node's own panel only."""
    from PyQt6.QtWidgets import QLabel
    ms = scene()
    pipe = add_pipe(ms)
    texts = [w.text() for w in panel(pipe).findChildren(QLabel)]
    assert "NODE 1" in texts and "Fitting Phase" not in texts
    assert "Fitting Phase" in [w.text() for w in panel(pipe.node1).findChildren(QLabel)]


def test_a_pipeless_fitting_reads_new(qapp):
    ms = scene()
    assert pr.effective_phase(ms.add_node(0.0, 0.0).fitting) == "new"


def test_section_proxies_resolve_to_their_source(qapp, section_scene_for):
    from firepro3d.section_scene import section_source_of
    ms, elev = section_scene_for("north")
    wall = add_wall(ms)
    wall.phase = "existing"
    pipe = ms.add_pipe(ms.add_node(0.0, 500.0), ms.add_node(3000.0, 500.0))
    pipe.phase = "demolition"
    elev.rebuild()
    got = {}
    for it in elev.items():
        src = section_source_of(it)
        if src is wall or src is pipe:
            got[type(src).__name__] = pr.effective_phase(it)
    assert got == {"WallSegment": "existing", "Pipe": "demolition"}


def test_block_children_take_the_outermost_instance(qapp):
    ms = scene()
    inst = add_block(ms)
    inst.phase = "demolition"
    child = QGraphicsRectItem(0, 0, 10, 10)
    child.setParentItem(inst)
    assert pr.effective_phase(child) == "demolition"


def test_unphased_items_read_none(qapp):
    from firepro3d.gridline import GridlineItem
    ms = scene()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000))
    node = ms.add_node(0.0, 0.0)
    inst = add_block(ms)
    inst.note = {"view": "Level 1"}
    assert [pr.effective_phase(x) for x in (gl, node, inst)] == [None, None, None]
