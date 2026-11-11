"""Elevation-parity D7: a project file's label-keyed gridline_z_overrides
re-key to the gridline uid on load (the real load_from_file path); a label
that is duplicated or names no gridline is dropped with a log line."""
import json
import logging

from tests._hosted_blocks_helpers import gridline
from tests.test_section_persistence import _scene_with_manager

OV_A = {"v_top": -4000.0, "v_bot": 600.0}
OV_B = {"v_top": -3000.0, "v_bot": 400.0}
OV_Q = {"v_top": -2000.0, "v_bot": 200.0}


def _legacy_file(qapp, tmp_path, *, strip_uids=False):
    """Save a project with gridlines A, B, B (B duplicated), then hand-edit
    the north marker's overrides to the pre-D7 label-keyed form."""
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    gridline(ms, (0.0, -1000.0), (0.0, 1000.0), "A")
    gridline(ms, (3000.0, -1000.0), (3000.0, 1000.0), "B")
    gridline(ms, (6000.0, -1000.0), (6000.0, 1000.0), "B")
    path = tmp_path / "legacy.fpd"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    north = next(d for d in payload["sections"] if d["cardinal"] == "north")
    north["gridline_z_overrides"] = {"A": OV_A, "B": OV_B, "Q": OV_Q}
    north.pop("datum_ends", None)                        # a pre-D7 record
    if strip_uids:
        for g in payload["gridlines"]:
            g.pop("uid", None)                           # a pre-uid gridline record
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


def test_label_key_migrates_to_uid_and_bad_labels_drop(qapp, tmp_path, caplog):
    path, payload = _legacy_file(qapp, tmp_path)
    uid_a = next(g["uid"] for g in payload["gridlines"] if g["label"] == "A")
    ms2, mgr2 = _scene_with_manager(qapp)
    caplog.set_level(logging.INFO, logger="firepro3d.section_manager")
    ms2.load_from_file(str(path))
    north = mgr2.markers["north"]
    assert north.gridline_z_overrides == {uid_a: OV_A}
    assert north.datum_ends == {}
    text = caplog.text
    assert "'B'" in text and "ambiguous" in text
    assert "'Q'" in text and "unknown" in text
    # The re-keyed record drives the projection after a rebuild.
    from firepro3d.section_scene import ElevGridlineItem
    sec = mgr2.get_or_build_scene("north")
    sec.rebuild()
    (eg,) = [i for i in sec.items()
             if isinstance(i, ElevGridlineItem) and i._gridline._uid == uid_a]
    assert (eg.line().y1(), eg.line().y2()) == (OV_A["v_top"], OV_A["v_bot"])


def test_label_key_migrates_onto_a_freshly_minted_uid(qapp, tmp_path):
    """A file whose gridlines predate the uid field: each loads with a new
    uid, and the label key still lands on the one A gridline."""
    path, _payload = _legacy_file(qapp, tmp_path, strip_uids=True)
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    (gl_a,) = [g for g in ms2._gridlines if g._label_text == "A"]
    assert mgr2.markers["north"].gridline_z_overrides == {gl_a._uid: OV_A}


def test_migration_is_idempotent_across_a_resave_and_reload(qapp, tmp_path):
    """Load -> save -> load keeps the same uid-keyed records: no duplicate, no
    dropped entry (the migration never re-runs on a uid-keyed record)."""
    path, payload = _legacy_file(qapp, tmp_path)
    uid_a = next(g["uid"] for g in payload["gridlines"] if g["label"] == "A")
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    mgr2.markers["north"].datum_ends["Level 1"] = {"left": -10.0, "right": 20.0}
    path2 = tmp_path / "resaved.fpd"
    ms2.save_to_file(str(path2))
    ms3, mgr3 = _scene_with_manager(qapp)
    ms3.load_from_file(str(path2))
    north = mgr3.markers["north"]
    assert north.gridline_z_overrides == {uid_a: OV_A}
    assert north.datum_ends == {"Level 1": {"left": -10.0, "right": 20.0}}
    assert north.to_dict() == mgr2.markers["north"].to_dict()
