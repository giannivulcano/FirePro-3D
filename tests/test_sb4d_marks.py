"""SB4d guard 5 (D3): Detail and Section are full Marks categories -- mint
on create, pattern {n}, duplicate flag, Renumber, load adopts the name
token once, blank panel edit refused. Cardinals never mint. (Markers do not
paste today -- design P-D5 -- so there is no paste mint site.)"""
import json

import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d import marks
from tests._sb4d_helpers import dispose, head_def, plan_scene


def test_categories_and_patterns():
    assert marks.MARK_CATEGORIES[-2:] == ("Section", "Detail")
    assert marks.DEFAULT_PATTERNS["Section"] == "{n}" and marks.DEFAULT_PATTERNS["Detail"] == "{n}"
    assert marks.RENUMBER_CATEGORIES == marks.MARK_CATEGORIES + ("Gridline",)


def test_mint_on_create_and_cardinals_never_mint(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        sec.seed_cardinals()
        s1 = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
        s2 = sec.place_section(QPointF(0.0, 9000.0), QPointF(5000.0, 9000.0))
        assert (s1._mark, s2._mark) == ("1", "2")
        assert all(sec.marker(c)._mark == "" for c in ("north", "south", "east", "west"))
        assert marks.mint(ms, sec.marker("north")) == ""          # Elevation is not a Mark category
        ms.mark_patterns = {"Detail": "D{n}"}
        d1 = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        d2 = det.create_detail("Detail 2", QRectF(3000.0, 0.0, 2000.0, 2000.0))
        assert (d1._mark, d2._mark) == ("D1", "D2")
    finally:
        dispose(ms, sec, tabs)


def test_duplicate_flag_renumber_and_head_refresh(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail", texts=(("Mark", -2.0),))
        d1 = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        d2 = det.create_detail("Detail 2", QRectF(3000.0, 0.0, 2000.0, 2000.0))
        marks.set_mark(d2, "1")
        assert marks.duplicate_info(ms, d1) == "2 details share Mark 1"
        plan = marks.renumber_plan(ms, "Detail", "project", restart_per_level=False, keep_order=False)
        assert marks.apply_marks(ms, plan)
        assert sorted((d1._mark, d2._mark)) == ["1", "2"]
        assert d2.bubble.host_values({"Mark"})["Mark"].text == d2._mark
        assert marks.sort_point(d1) == (1000.0, 1000.0)            # crop centre
        s = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
        assert marks.sort_point(s) == (2500.0, 0.0)                # cut midpoint
    finally:
        dispose(ms, sec, tabs)


def test_load_adopts_the_name_token_once(qapp, tmp_path):
    ms, sec, det, tabs = plan_scene()
    try:
        sec.seed_cardinals()
        s = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
        d = det.create_detail("Detail 4", QRectF(0.0, 0.0, 2000.0, 2000.0))
        marks.set_mark(s, "A7")
        path = tmp_path / "m.fp3d"
        ms.save_to_file(str(path))
        payload = json.loads(path.read_text(encoding="utf-8"))
        rec_s = next(r for r in payload["sections"] if r["name"] == s.name)
        rec_d = payload["detail_views"][0]
        assert rec_s["mark"] == "A7" and rec_d["mark"] == "1"
        assert all("mark" not in r for r in payload["sections"] if r.get("cardinal"))   # cardinals: key-less
        rec_s.pop("mark")                                           # a pre-SB4d file
        rec_d.pop("mark")
        path.write_text(json.dumps(payload), encoding="utf-8")
    finally:
        dispose(ms, sec, tabs)
    ms2, sec2, det2, tabs2 = plan_scene()
    try:
        ms2.load_from_file(str(path))
        assert sec2.marker("Section 1")._mark == "1"               # name token "1"
        assert det2.get_marker("Detail 4")._mark == "4"            # name token "4"
        assert sec2.marker("north")._mark == ""
    finally:
        dispose(ms2, sec2, tabs2)


def test_blank_panel_edit_is_refused(qapp, monkeypatch):
    from firepro3d.property_manager import PropertyManager
    ms, sec, det, tabs = plan_scene()
    try:
        d = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        msgs = []
        monkeypatch.setattr(ms, "_show_status", lambda m, timeout=5000: msgs.append(m))
        pm = PropertyManager()
        pm.show_properties(d)
        edit = pm._prop_widgets["Mark"]
        assert edit.text() == "1"
        edit.setText("   ")
        edit.editingFinished.emit()
        assert d._mark == "1"
        assert msgs == ["Mark can't be blank - restored to 1"]
    finally:
        dispose(ms, sec, tabs)


def test_blank_mark_survives_save_load_and_undo_recreate(qapp, tmp_path):
    """Phase 5 ruling (T15 review I1): a blank pattern mints "" and the record
    always carries the ``mark`` key, so neither a reload nor an undo re-create
    adopts the name token (M7) -- only a key-less pre-SB4d record does (Q20)."""
    ms, sec, det, tabs = plan_scene()
    try:
        ms.mark_patterns = {"Section": "", "Detail": ""}
        s = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
        d = det.create_detail("Detail 4", QRectF(0.0, 0.0, 2000.0, 2000.0))
        assert s._mark == "" and d._mark == ""
        assert s.to_dict()["mark"] == "" and d.to_dict()["mark"] == ""
        # undo re-create path: the record rebuilt through the manager keeps blank
        rebuilt = sec._marker_from_record(s.to_dict())
        assert rebuilt is not None and rebuilt._mark == ""
        path = tmp_path / "blank.fp3d"
        ms.save_to_file(str(path))
    finally:
        dispose(ms, sec, tabs)
    ms2, sec2, det2, tabs2 = plan_scene()
    try:
        ms2.load_from_file(str(path))
        assert sec2.marker(s.name)._mark == ""
        assert det2.get_marker("Detail 4")._mark == ""
    finally:
        dispose(ms2, sec2, tabs2)
