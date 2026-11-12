"""PH1 AC1 / D-PH3 / D-PH16 for block placements and underlays.

Raw sources: concept PD1 (ids; same attribute + row on BlockInstance and
Underlay); D-PH3 (text / annotation carries no phase: a Note is an annotation
block); D-PH16 (definitions carry no phase); scene-io.md (underlays are not on
the undo stack).
"""
import pytest

from tests._ph1_helpers import (FIND, add_block, block_definition, load, panel,  # noqa: F401
                                ph1_cleanup, save_raw, scene)


@pytest.fixture
def _silence_missing_underlay_modal(monkeypatch):
    import firepro3d.themed_message as _tm
    monkeypatch.setattr(_tm, "themed_warn", lambda *a, **k: None)


def test_block_phase_survives_save_and_load(qapp, tmp_path):
    ms = scene()
    add_block(ms).phase = "existing"
    path, raw = save_raw(ms, tmp_path)
    assert raw["blocks"][0]["phase"] == "existing"
    assert FIND["block"](load(path)).phase == "existing"


def test_block_phase_rides_undo_and_the_panel(qapp, panel):
    ms = scene()
    inst = add_block(ms)
    ms.push_undo_state()
    pos = ms._undo_pos
    pm = panel(inst)
    pm._prop_widgets["Phase"].setCurrentText("Demolition")
    assert inst.phase == "demolition" and ms._undo_pos == pos + 1
    ms.undo()
    assert FIND["block"](ms).phase == "new"
    ms.redo()
    assert FIND["block"](ms).phase == "demolition"


def test_definitions_carry_no_phase(qapp):
    ms = scene()
    inst = add_block(ms)
    inst.phase = "existing"
    assert "phase" not in inst.to_nested_dict()


def test_a_note_has_no_phase_row(qapp):
    ms = scene()
    d = block_definition(ms)
    plain = ms.place_block_instance(d.id, (0.0, 0.0))
    note = ms.place_block_instance(d.id, (500.0, 0.0))
    note.note = {"view": "Level 1"}          # an annotation block (D-PH3: text carries none)
    assert "Phase" in plain.get_properties()
    assert "Phase" not in note.get_properties()


def test_underlay_phase_survives_save_and_load(qapp, tmp_path, _silence_missing_underlay_modal):
    from firepro3d.underlay import Underlay
    ms = scene()
    data = Underlay(type="dxf", path=str(tmp_path / "no_such.dxf"))
    ms._create_underlay_placeholder(data)
    data.phase = "existing"
    path, raw = save_raw(ms, tmp_path)
    assert raw["underlays"][0]["phase"] == "existing"
    out = load(path)
    assert out.underlays[0][0].phase == "existing"


def test_underlay_panel_row_edits_the_record(qapp, panel):
    from firepro3d.underlay import Underlay
    u = Underlay(type="dxf", path="a.dxf")
    pm = panel(u)
    pm._prop_widgets["Phase"].setCurrentText("Demolition")
    assert u.phase == "demolition"


def test_underlay_duplicate_keeps_the_phase(qapp, tmp_path, monkeypatch):
    """I2 / D-PH16 copies keep the source's phase, through the context-menu action."""
    from PyQt6.QtCore import QPoint
    import firepro3d.underlay_context_menu as ucm
    from firepro3d.underlay import Underlay
    ms = scene()
    data = Underlay(type="dxf", path=str(tmp_path / "no_such.dxf"))
    ms._create_underlay_placeholder(data)
    data.phase = "demolition"
    seen = []
    monkeypatch.setattr(ms, "import_dxf", lambda *a, **k: seen.append(k["_record"]))

    def _pick_duplicate(menu, *_args):          # the modal menu: click "Duplicate"
        next(act for act in menu.actions() if act.text() == "Duplicate").trigger()
    monkeypatch.setattr(ucm.QMenu, "exec", _pick_duplicate)
    ucm.UnderlayContextMenu.show(ms, data, ms.underlays[0][1], QPoint(0, 0))
    assert [r.phase for r in seen] == ["demolition"]


def test_underlay_pick_new_position_keeps_the_phase(qapp, tmp_path):
    """VC9 F1: Modify > "Pick new position" builds a fresh record and carries the
    management fields (underlay_controller._UNDERLAY_MGMT_FIELDS); phase rides with them."""
    import ezdxf
    from PyQt6.QtCore import QPointF
    from firepro3d.model_space import Model_Space
    from firepro3d.underlay import Underlay
    from tests.test_underlay_modify_flow import _StubParams, _build_underlay_group, _cleanup_worker
    dxf_file = tmp_path / "pick.dxf"
    doc = ezdxf.new()
    doc.layers.add("A-WALL")
    doc.modelspace().add_line((0, 0), (100, 100), dxfattribs={"layer": "A-WALL"})
    doc.saveas(str(dxf_file))
    ms = Model_Space()
    record = Underlay(type="dxf", path="old.dxf", x=5.0, y=5.0)
    record.phase = "existing"
    ms.underlays.append((record, _build_underlay_group(ms, x=5.0, y=5.0)))
    params = _StubParams(file_type="dxf", file_path=str(dxf_file), selected_layers=["A-WALL"],
                         geom_list=[{"kind": "line", "layer": "A-WALL",
                                     "x1": 0, "y1": 0, "x2": 10, "y2": 10}])
    ms.begin_replace_underlay_placement(record, params)
    ms._commit_place_import(QPointF(200, 300))
    fresh = [d for d, _ in ms.underlays]
    assert len(fresh) == 1 and fresh[0] is not record
    assert fresh[0].phase == "existing"
    _cleanup_worker(ms)
