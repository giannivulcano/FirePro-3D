"""Acceptance (f) / D4: project file gains "sections"; absence seeds four
cardinals; round-trip restores markers, boxes and overrides; no SAVE_VERSION bump."""
import json
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.section_marker import CARDINALS


def _scene_with_manager(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.section_manager import SectionManager
    ms = Model_Space()
    lm = LevelManager(); ms._level_manager = lm
    sm = ScaleManager(); ms.scale_manager = sm
    mgr = SectionManager(ms, lm, sm, QTabWidget())
    ms._section_manager = mgr
    return ms, mgr


def test_save_version_unchanged():
    from firepro3d.model_space import Model_Space
    assert Model_Space.SAVE_VERSION == 11          # D4 / S4: no bump (value at 682c1edd)


def test_round_trip_restores_placed_section(qapp, tmp_path):
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    s = mgr.place_section(QPointF(100.0, 200.0), QPointF(5100.0, 1200.0))
    s.flip(); s.set_geometry(s.cut_a, s.cut_b, 4321.0)
    s.gridline_z_overrides["A"] = {"v_top": -9000.0, "v_bot": 100.0}
    north = mgr.markers["north"]
    north.set_geometry(north.cut_a, north.cut_b, 7777.0)        # user-owned cardinal box
    path = tmp_path / "p.fp3d"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [d["name"] for d in payload["sections"]] == ["North", "South", "East", "West", "Section 1"]
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    assert set(mgr2.markers) == set(CARDINALS) | {"Section 1"}
    s2 = mgr2.markers["Section 1"]
    assert s2.to_dict() == s.to_dict()
    assert mgr2.markers["north"].auto_extent is False and mgr2.markers["north"].depth == 7777.0
    assert mgr2.markers["south"].auto_extent is True
    assert all(m.scene() is ms2 for m in mgr2.markers.values())
    assert mgr2.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0)).name == "Section 2"


def test_missing_key_seeds_four_cardinals(qapp, tmp_path):
    ms, mgr = _scene_with_manager(qapp)
    path = tmp_path / "old.fp3d"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["sections"]                                       # a pre-section project file
    path.write_text(json.dumps(payload), encoding="utf-8")
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    assert set(mgr2.markers) == set(CARDINALS) and all(m.auto_extent for m in mgr2.markers.values())


def test_one_missing_cardinal_reseeded(qapp, tmp_path):
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    path = tmp_path / "edited.fp3d"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sections"] = [d for d in payload["sections"] if d["cardinal"] != "east"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    assert set(mgr2.markers) == set(CARDINALS)


def test_hand_edited_unbuildable_records_do_not_crash_load(qapp, tmp_path):
    """Spec s13: a zero-depth / zero-length / key-less record is skipped, the file loads,
    the section is simply absent (a cardinal among them is re-seeded)."""
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    mgr.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    path = tmp_path / "bad.fp3d"
    ms.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    for d in payload["sections"]:
        if d["cardinal"] == "west":
            d["depth"] = 0.0
        if d["name"] == "Section 1":
            d["cut_b"] = list(d["cut_a"])
    payload["sections"].append({"name": "Section 9"})
    good = {"cut_a": [0.0, 0.0], "cut_b": [5000.0, 0.0], "look_sign": 1, "depth": 3000.0,
            "cardinal": None, "auto_extent": False, "gridline_z_overrides": {}}
    payload["sections"] += [
        dict(good, name="Section 10", cut_a=["1", "2"]),                 # string coordinates
        dict(good, name="Section 11", look_sign="x"),                    # non-numeric look_sign
        dict(good, name="Section 12", gridline_z_overrides=[1, 2]),      # non-dict overrides
        dict(good, name="Section 13", cardinal=["north"]),               # unhashable cardinal
        dict(good, name="North"),                                        # placed name == a cardinal key
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    ms2, mgr2 = _scene_with_manager(qapp)
    ms2.load_from_file(str(path))
    assert set(mgr2.markers) == set(CARDINALS)
    for k in mgr2.markers:
        assert mgr2.get_or_build_scene(k) is not None


def test_new_scene_clear_drops_markers_without_dead_wrappers(qapp):
    """_clear_scene (New / Open) deletes every scene item: the manager must not
    keep the deleted markers (the undo baseline pushed at its end reads them)."""
    ms, mgr = _scene_with_manager(qapp)
    mgr.seed_cardinals()
    mgr.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    ms._clear_scene()
    assert mgr.markers == {}
    assert "sections" in ms._capture_network() and ms._capture_network()["sections"] == []
