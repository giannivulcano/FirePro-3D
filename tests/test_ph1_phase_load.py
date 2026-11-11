"""PH1 AC4 data half (D-PH6) + the "phases" project key (PD1).

Raw sources: D-PH6 "saved pipe phases are honoured (Demo -> Demolition), every
other element loads New"; the fixture tests/fixtures/ph1_pre_phasing_v12.fpd
was written by the pre-phasing code (Task 0) with pipe Phase New / Existing /
Demo in that order; PD1 "saved as the top-level project key phases";
concept edge cases "an unknown status id reads as new and logs one info line".
"""
import json
import logging
import shutil
from pathlib import Path

from firepro3d import phase_registry as pr
from firepro3d.model_space import Model_Space
from tests._ph1_helpers import add_wall, load, ph1_cleanup, save_raw, scene  # noqa: F401

FIXTURE = Path(__file__).parent / "fixtures" / "ph1_pre_phasing_v12.fpd"


def test_pre_phasing_file_loads_per_d_ph6(qapp, tmp_path):
    src = tmp_path / "old.fpd"
    shutil.copyfile(FIXTURE, src)                       # never touch the fixture
    assert json.loads(src.read_text(encoding="utf-8"))["version"] == 12
    pr.set_project_table(pr.PhaseRegistry.from_list(        # a stale table the open must replace
        [{"id": "existing", "name": "Existing", "graphics": {"colour": "#ff0000"}}]))
    ms = scene()
    assert ms.load_from_file(str(src))                         # not load(): it resets first
    by_x = sorted(ms.sprinkler_system.pipes, key=lambda p: p.node1.scenePos().x())
    assert [p.phase for p in by_x] == ["new", "existing", "demolition"]
    others = [*ms._walls, *[o for w in ms._walls for o in w.openings], *ms._floor_slabs,
              *ms._roofs, *ms._rooms, *ms.sprinkler_system.sprinklers, ms.water_supply_node]
    assert len(others) == 7 and {o.phase for o in others} == {"new"}
    assert pr.project_table().to_list() == pr.PhaseRegistry().to_list()   # factory seed
    _path, raw = save_raw(ms, tmp_path, "resaved.fpd")
    assert raw["version"] == Model_Space.SAVE_VERSION == 13
    assert all("Phase" not in p["properties"] for p in raw["pipes"])
    assert [p.get("phase") for p in sorted(raw["pipes"], key=lambda e: e["node1_id"])] \
        == [None, "existing", "demolition"]


def test_migrate_payload_moves_the_legacy_pipe_text(qapp):
    """C2: the migration on the raw fixture payload (the one home of New/Existing/Demo)."""
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pr.migrate_payload(payload)
    pipes = sorted(payload["pipes"], key=lambda e: e["node1_id"])
    assert all("Phase" not in p["properties"] for p in pipes)
    assert [p.get("phase") for p in pipes] == [None, "existing", "demolition"]


def _count_pushes_during_load(path):
    ms = scene()
    calls = []
    real = ms.push_undo_state
    ms.push_undo_state = lambda: (calls.append(1), real())[1]
    assert ms.load_from_file(path)
    return len(calls)


def test_a_legacy_load_pushes_no_extra_undo_step(qapp, tmp_path):
    """C2: no load path reaches request_undo_push. Control = the same fixture with
    every pipe's legacy Phase key stripped (base bf6771de: 2 pushes per load, P-10)."""
    legacy = tmp_path / "legacy.fpd"
    shutil.copyfile(FIXTURE, legacy)
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for p in raw["pipes"]:
        p["properties"].pop("Phase", None)
    control = tmp_path / "control.fpd"
    control.write_text(json.dumps(raw), encoding="utf-8")
    assert _count_pushes_during_load(str(legacy)) == _count_pushes_during_load(str(control))


def test_phases_key_round_trips_the_registry(qapp, tmp_path):
    rows = pr.PhaseRegistry().to_list()
    rows[1]["graphics"]["colour"] = "#123456"
    pr.set_project_table(pr.PhaseRegistry.from_list(rows))
    path, raw = save_raw(scene(), tmp_path)
    assert raw["phases"] == rows
    load(path)                                          # load() resets first
    assert pr.project_table().to_list() == rows


def test_unknown_status_in_a_file_reads_new_with_one_log_line(qapp, tmp_path, caplog):
    ms = scene()
    add_wall(ms); add_wall(ms)
    path, raw = save_raw(ms, tmp_path)
    for w in raw["walls"]:
        w["phase"] = "deleted-custom"
    Path(path).write_text(json.dumps(raw), encoding="utf-8")
    caplog.set_level(logging.INFO, logger="firepro3d.phase_registry")
    out = load(path)
    assert [w.phase for w in out._walls] == ["new", "new"]
    assert len([r for r in caplog.records if "deleted-custom" in r.getMessage()]) == 1
