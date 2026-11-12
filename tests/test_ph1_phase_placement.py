"""PH1 AC3 (D-PH5): each placement tool commits its template's phase; kinds with
no template place as New (ruling 1); the registry is seeded from the template.

Raw sources: D-PH5 ("the template has a Phase field, committed on placement,
sticky"; ruling 2026-11-11: room / floor opening / water supply / block place
as New); concept PD4 Templates + Template persistence; property-panel.md §3.7
(pipe / sprinkler templates persisted in QSettings template/pipe|sprinkler).
Click drivers: probe P-06 (posted events on shown_model_view; no OS cursor).
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QDialog

from firepro3d import phase_registry as pr
from firepro3d.constants import DEFAULT_CEILING_OFFSET_MM, DEFAULT_LEVEL
from firepro3d.pipe import Pipe
from firepro3d.sprinkler import Sprinkler
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening
from tests._ph1_helpers import block_definition, click, ph1_cleanup, scene  # noqa: F401


def _pipe_template():
    t = Pipe(None, None)
    t.node1_ceiling_level = t.node2_ceiling_level = DEFAULT_LEVEL
    t.node1_ceiling_offset = t.node2_ceiling_offset = DEFAULT_CEILING_OFFSET_MM
    return t


def test_wall_chain_takes_the_template_phase(qapp, shown_model_view):
    view, sc = shown_model_view
    sc._get_wall_template().set_property("Phase", "Existing")
    sc.set_mode("wall")
    click(view, QPointF(0, 0)); click(view, QPointF(1000, 0))
    sc.set_mode("wall")                     # single placement returned to Select; template untouched
    click(view, QPointF(0, 800)); click(view, QPointF(1000, 800))
    assert [w.phase for w in sc._walls] == ["existing", "existing"]   # sticky: the 2nd wall too


def test_wall_rect_takes_the_template_phase(qapp, shown_model_view):
    view, sc = shown_model_view
    sc._get_wall_template().set_property("Phase", "Demolition")
    sc.set_mode("wall_rect")
    click(view, QPointF(0, 0)); click(view, QPointF(3000, 0)); click(view, QPointF(3000, 2000))
    assert [w.phase for w in sc._walls] == ["demolition"] * 4


def test_floor_polygon_takes_the_template_phase(qapp, shown_model_view):
    view, sc = shown_model_view
    sc.set_mode("floor")
    sc.cycle_placement_variant(+1); sc.cycle_placement_variant(+1)
    sc._get_floor_template().set_property("Phase", "Existing")
    sc.set_mode("floor")
    for x, y in ((0, 0), (1000, 0), (1000, 1000), (0, 0)):
        click(view, QPointF(x, y))
    assert [s.phase for s in sc._floor_slabs] == ["existing"]


def test_floor_rect_takes_the_template_phase(qapp):
    ms = scene()
    ms._get_floor_template().set_property("Phase", "Demolition")
    ms._floor_rect_sized_pt1, ms._floor_rect_sized_pt2 = QPointF(0, 0), QPointF(1000, 1000)
    ms._floor_rect_pivot = QPointF(0, 0)
    assert ms._commit_floor_rect_rotated(0.0)
    assert [s.phase for s in ms._floor_slabs] == ["demolition"]


@pytest.mark.parametrize("variant", ["polygon", "rect"])
def test_roof_takes_the_template_phase(qapp, monkeypatch, variant):
    from firepro3d.roof_dialog import RoofDialog
    monkeypatch.setattr(RoofDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    ms = scene()
    ms._get_roof_template().set_property("Phase", "Existing")
    if variant == "polygon":
        for p in (QPointF(0, 0), QPointF(900, 0), QPointF(900, 700), QPointF(0, 0)):
            ms._press_roof(None, p, p, None, None, None)
    else:
        for p in (QPointF(0, 0), QPointF(900, 700)):
            ms._press_roof_rect(None, p, p, None, None, None)
    assert [r.phase for r in ms._roofs] == ["existing"]


def test_opening_takes_the_template_phase(qapp, shown_model_view):
    view, sc = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(3000, 0), thickness_mm=200.0)
    sc.addItem(w); sc._walls.append(w)
    t = WallOpening(feature_id="door_914")
    t.set_property("Phase", "Existing")
    sc.set_mode("opening", template=t)
    click(view, QPointF(800, 0))
    assert [o.phase for o in w.openings] == ["existing"]


def test_pipe_takes_the_template_phase(qapp, shown_model_view):
    view, sc = shown_model_view
    t = _pipe_template()
    t.set_property("Phase", "Demolition")
    sc.set_mode("pipe", t)
    click(view, QPointF(0, 0)); click(view, QPointF(1000, 0))
    assert [p.phase for p in sc.sprinkler_system.pipes] == ["demolition"]


def test_sprinkler_takes_the_template_phase(qapp, shown_model_view):
    view, sc = shown_model_view
    t = Sprinkler(None)
    t.set_property("Phase", "Existing")
    sc.set_mode("sprinkler", t)
    click(view, QPointF(1000, 0))
    assert [s.phase for s in sc.sprinkler_system.sprinklers] == ["existing"]


def test_template_less_kinds_place_as_new(qapp, shown_model_view):
    """Ruling 1. Every click stays inside the pinned view (+-1596 x +-1196 at m11 = 0.25)
    and > 80 units (the snap aperture) from any vertex / edge midpoint."""
    from firepro3d.floor_slab import FloorSlab
    view, sc = shown_model_view
    sc.set_mode("room_manual")
    for x, y in ((-1400, -1000), (-600, -1000), (-600, -400), (-1400, -400), (-1400, -1000)):
        click(view, QPointF(x, y))
    slab = FloorSlab(points=[QPointF(200, 200), QPointF(1400, 200),
                             QPointF(1400, 1000), QPointF(200, 1000)])
    sc.addItem(slab); sc._floor_slabs.append(slab)
    slab.phase = "existing"                 # a void keeps its own phase (D-PH16)
    sc.set_mode("floor_opening")
    for p in ((500, 450), (1100, 450), (800, 760)):        # corner rect: base, side, depth
        click(view, QPointF(*p))
    sc.add_node(-1000.0, 600.0)
    sc.set_mode("water_supply")
    click(view, QPointF(-1000, 600))
    d = block_definition(sc)
    sc.set_mode("place_block", template=d.id)
    click(view, QPointF(-300, -800))
    got = [sc._rooms[0].phase, slab.openings[0].phase,
           sc.water_supply_node.phase, sc._block_instances[0].phase]
    assert got == ["new", "new", "new", "new"]


def test_template_carries_the_registry(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    from firepro3d.settings import template
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    rows = pr.PhaseRegistry().to_list()
    rows[1]["graphics"]["fill"] = "#ABCDEF"
    pr.set_project_table(pr.PhaseRegistry.from_list(rows))
    template.save_current_as_default(scene())
    pr.reset_project_table()
    template.apply_template_settings(scene())
    assert pr.project_table().to_list() == rows


def test_blank_template_seeds_the_factory(qapp, tmp_path, monkeypatch):
    import json
    from firepro3d import app_data
    from firepro3d.settings import template
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    with open(template.ensure_template(), encoding="utf-8") as fh:
        assert json.load(fh)["phases"] == pr.PhaseRegistry().to_list()


def test_floor_template_phase_persists_with_the_floor_recipe(qapp, tmp_path):
    from PyQt6.QtCore import QSettings
    s = QSettings(str(tmp_path / "floor.ini"), QSettings.Format.IniFormat)
    a = scene()
    a._get_floor_template().set_property("Phase", "Demolition")
    a.save_floor_template_settings(s)
    b = scene()
    b.load_floor_template_settings(s)
    assert b._get_floor_template().phase == "demolition"


def test_collinear_extension_takes_the_template_phase(qapp, shown_model_view):
    """VC9 F2 ruling (2026-11-11): drawing straight on from an Existing pipe's free end
    merges into that pipe (pipe_network_controller._try_extend_collinear), and the
    merged pipe takes the template's phase, so the new work is not recorded as Existing."""
    view, sc = shown_model_view
    t = _pipe_template()
    t.set_property("Phase", "Existing")
    sc.set_mode("pipe", t)
    click(view, QPointF(0, 0)); click(view, QPointF(1000, 0))
    t2 = _pipe_template()
    t2.set_property("Phase", "New")
    sc.set_mode("pipe", t2)
    click(view, QPointF(1000, 0)); click(view, QPointF(2000, 0))
    pipes = list(sc.sprinkler_system.pipes)
    assert len(pipes) == 1                       # the collinear merge ran
    assert pipes[0].phase == "new"
