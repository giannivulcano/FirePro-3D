"""SB4f AC3 / AC4 data half: persisted fields, number rules, undoable edits."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.paper_space import Sheet, SheetViewData, ViewportProperties
from firepro3d.property_manager import PropertyManager
from tests._sb4d_helpers import dispose, plan_scene
from tests._sb4f_helpers import place


def _data(**kw):
    return SheetViewData("plan", "Plan: Level 1", "T", 0.0, 0.0, 0.0, 10.0, 10.0, **kw)


def test_round_trip():
    d = SheetViewData.from_dict(_data(show_title=False, title_offset=(3.0, -2.5),
                                      view_number="A3").to_dict())
    assert d.show_title is False
    assert d.title_offset == (3.0, -2.5)
    assert d.view_number == "A3"


def test_legacy_record_defaults():
    rec = _data().to_dict()
    del rec["show_title"], rec["title_offset"]
    d = SheetViewData.from_dict(rec)
    assert d.show_title is True and d.title_offset == (0.0, 0.0)


def test_next_view_number_fills_the_lowest_gap():
    s = Sheet.create_default()
    s.sheet_views[:] = [_data(view_number=n) for n in ("1", "3", "A")]
    assert s.next_view_number() == "2"
    s.sheet_views[:] = []
    assert s.next_view_number() == "1"


def test_view_number_refusal():
    s = Sheet.create_default()
    a, b = _data(view_number="1"), _data(view_number="2")
    s.sheet_views[:] = [a, b]
    assert s.view_number_refusal("3") is None
    assert s.view_number_refusal(" 1 ", ignore=a) is None
    assert "already used" in s.view_number_refusal("1", ignore=b)
    assert "blank" in s.view_number_refusal("   ")


def test_add_assigns_lowest_unused_and_delete_never_renumbers(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        _v, ps, vp1 = place(ms, sec, det)
        vp2 = ps.add_viewport(_data())
        vp3 = ps.add_viewport(_data())
        assert [v.data.view_number for v in (vp1, vp2, vp3)] == ["1", "2", "3"]
        ps.remove_viewport(vp2)
        assert [v.data.view_number for v in ps.get_viewports()] == ["1", "3"]
        assert ps.add_viewport(_data()).data.view_number == "2"
    finally:
        dispose(ms, sec, tabs)


def test_undoing_a_removal_keeps_a_legacy_blank_number(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        _v, ps, vp = place(ms, sec, det)
        vp.data.view_number = ""
        ps.remove_viewport(vp)
        ps.undo_stack.undo()
        assert ps.get_viewports()[0].data.view_number == ""
    finally:
        dispose(ms, sec, tabs)


def test_loaded_blank_number_stays_blank(qapp):
    from tests._sb4d_helpers import add_sheet, paper_view
    ms, sec, det, tabs = plan_scene()
    try:
        sheet = add_sheet(ms, "FP-1.0", [("plan", "Plan: Level 1")])
        _view, ps = paper_view(ms, sec, det, sheet)      # the load path: _setup
        assert ps.get_viewports()[0].data.view_number == ""
    finally:
        dispose(ms, sec, tabs)


def test_panel_rows(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        _v, ps, vp = place(ms, sec, det)
        props = ViewportProperties(ps, vp).get_properties()
        assert props["Number"] == {"type": "string", "value": "1", "free_text": True}
        assert props["Show Title"] == {"type": "bool", "value": True}
    finally:
        dispose(ms, sec, tabs)


@pytest.mark.parametrize("key,value,attr,want", [
    ("Number", "A7", "view_number", "A7"),
    ("Show Title", False, "show_title", False),
])
def test_panel_edit_is_one_undo_step(qapp, key, value, attr, want):
    ms, sec, det, tabs = plan_scene()
    try:
        _v, ps, vp = place(ms, sec, det)
        before = getattr(vp.data, attr)
        ViewportProperties(ps, vp).set_property(key, value)
        assert getattr(vp.data, attr) == want
        assert ps.undo_stack.count() == 2        # add + this edit
        ps.undo_stack.undo()
        assert getattr(vp.data, attr) == before
    finally:
        dispose(ms, sec, tabs)


@pytest.mark.parametrize("typed", ["2", "   "])
def test_panel_refuses_a_duplicate_or_blank_with_a_notice(qapp, typed):
    ms, sec, det, tabs = plan_scene()
    seen = []
    try:
        _v, ps, vp = place(ms, sec, det)
        ps.add_viewport(_data())
        ms._show_status = lambda msg, *a: seen.append(msg)
        ViewportProperties(ps, vp).set_property("Number", typed)
        assert vp.data.view_number == "1"
        assert len(seen) == 1
        assert ps.undo_stack.count() == 2        # no edit pushed
    finally:
        dispose(ms, sec, tabs)


def _number_row(ms, ps, vp):
    """The real Number row of a shown panel, with the viewport's panel loaded."""
    pm = PropertyManager()
    pm.resize(400, 600)
    pm.show()
    QTest.qWaitForWindowExposed(pm)
    pm.show_properties(ViewportProperties(ps, vp))
    QApplication.processEvents()
    return pm, pm._prop_widgets["Number"]


def _retype(row, text):
    row.setFocus()
    row.selectAll()
    QTest.keyClick(row, Qt.Key.Key_Delete)
    QTest.keyClicks(row, text)
    QTest.keyClick(row, Qt.Key.Key_Return)
    QTest.qWait(300)                             # past the panel's debounced refresh


@pytest.mark.parametrize("typed", ["A5", "1-A"])
def test_typing_letters_over_a_numeric_number_commits_them(qapp, real_system_library, typed):
    """AC4 "any text": the row starts at the auto number "1", which parses as a
    float, and takes letters through real key events."""
    ms, sec, det, tabs = plan_scene()
    seen = []
    pm = None
    try:
        _v, ps, vp = place(ms, sec, det)
        ms._show_status = lambda msg, *a: seen.append(msg)
        pm, row = _number_row(ms, ps, vp)
        assert row.text() == "1"
        _retype(row, typed)
        assert vp.data.view_number == typed
        assert seen == []
    finally:
        if pm is not None:
            pm.close()
            pm.deleteLater()
        dispose(ms, sec, tabs)


def test_clearing_the_number_row_is_refused_and_shows_the_old_value(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    seen = []
    pm = None
    try:
        _v, ps, vp = place(ms, sec, det)
        ms._show_status = lambda msg, *a: seen.append(msg)
        pm, row = _number_row(ms, ps, vp)
        steps = ps.undo_stack.count()
        _retype(row, "")
        assert vp.data.view_number == "1"
        assert len(seen) == 1
        assert ps.undo_stack.count() == steps    # no edit pushed
        assert pm._prop_widgets["Number"].text() == "1"
    finally:
        if pm is not None:
            pm.close()
            pm.deleteLater()
        dispose(ms, sec, tabs)


@pytest.mark.parametrize("legacy", ["", "1"])
def test_bare_focus_out_on_an_unchanged_number_is_silent(qapp, legacy):
    """Panel rows commit on focus-out: a legacy blank or duplicate number the
    user never touched raises nothing."""
    ms, sec, det, tabs = plan_scene()
    seen = []
    try:
        _v, ps, vp = place(ms, sec, det)
        ps.add_viewport(_data(view_number="1"))     # a tolerated legacy duplicate
        vp.data.view_number = legacy
        ms._show_status = lambda msg, *a: seen.append(msg)
        count = ps.undo_stack.count()
        ViewportProperties(ps, vp).set_property("Number", legacy)
        assert seen == [] and ps.undo_stack.count() == count
    finally:
        dispose(ms, sec, tabs)


def test_geometry_command_restores_title_offset_and_keeps_the_5_tuple(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        _v, ps, vp = place(ms, sec, det)
        old = ps._viewport_geom(vp.data)
        assert len(old) == 6
        vp.data.title_offset = (5.0, 6.0)
        new = ps._viewport_geom(vp.data)
        ps._push_viewport_geometry(vp.data, old, new)
        ps.undo_stack.undo()
        assert vp.data.title_offset == (0.0, 0.0)
        ps.undo_stack.redo()
        assert vp.data.title_offset == (5.0, 6.0)
        vp.data.x = 40.0                         # native move keeps its 5-tuple
        ps._push_viewport_geometry(vp.data, old[:5], ps._viewport_geom(vp.data)[:5])
        ps.undo_stack.undo()
        assert vp.data.x == 30.0 and vp.data.title_offset == (5.0, 6.0)
    finally:
        dispose(ms, sec, tabs)
