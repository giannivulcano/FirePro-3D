"""SB2b G-M3 -- Renumber: reading order per level, scopes, options, one undo step, Gridline rule."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPushButton

from firepro3d import marks
from firepro3d.gridline import GridlineItem
from firepro3d.property_manager import PropertyManager
from firepro3d.renumber_dialog import RenumberDialog, _OrderThumb
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening


def _two_level_doors(scene):
    lm = scene._level_manager
    if lm.get("Level 2") is None:
        lm.add_level("Level 2", elevation=3000.0)
    out = {}
    for lvl in ("Level 2", "Level 1"):          # Level 2 first: order must come from elevation
        w = WallSegment(QPointF(0, 0), QPointF(9000, 0), thickness_mm=200.0)
        w.level = lvl
        scene.addItem(w)
        scene._walls.append(w)
        for x, mark in ((7000, "D9"), (1000, "D3")):
            op = WallOpening(w, feature_id="door_914", offset_along=x)
            op.level = lvl
            w.openings.append(op)
            scene.addItem(op)
            marks.set_mark(op, mark)
            out[(lvl, x)] = op
    return out


def _plan(scene, cat, scope, level=None, restart=False, keep=False):
    return marks.renumber_plan(scene, cat, scope, level,
                               restart_per_level=restart, keep_order=keep)


def _ok_button(dlg):
    return [b for b in dlg.findChildren(QPushButton) if b.text() == "OK"][0]


def test_whole_project_level_by_level_reading_order(qapp, shown_model_view):
    view, scene = shown_model_view
    d = _two_level_doors(scene)
    mapping = _plan(scene, "Door", "project")
    assert {k: mapping[d[k]] for k in d} == {
        ("Level 1", 1000): "D1", ("Level 1", 7000): "D2",
        ("Level 2", 1000): "D3", ("Level 2", 7000): "D4"}


def test_rows_top_to_bottom_then_left_to_right(qapp, shown_model_view):
    """Two rows on one level: the upper row (smaller scene y) numbers first, each left -> right."""
    view, scene = shown_model_view
    ops = {}
    for y in (5000.0, 0.0):
        w = WallSegment(QPointF(0, y), QPointF(9000, y), thickness_mm=200.0)
        w.level = "Level 1"
        scene.addItem(w)
        scene._walls.append(w)
        for x in (6000, 2000):
            op = WallOpening(w, feature_id="door_914", offset_along=x)
            op.level = "Level 1"
            w.openings.append(op)
            scene.addItem(op)
            ops[(y, x)] = op
    mapping = _plan(scene, "Door", "project")
    assert [mapping[ops[k]] for k in ((0.0, 2000), (0.0, 6000), (5000.0, 2000), (5000.0, 6000))] == \
        ["D1", "D2", "D3", "D4"]


def test_dialog_ok_is_one_undo_step(qapp, shown_model_view):
    view, scene = shown_model_view
    d = _two_level_doors(scene)
    scene.push_undo_state()
    depth = len(scene._undo_stack)
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    assert dlg.footer_text().startswith("4 elements, ")
    ok = _ok_button(dlg)
    assert ok.isEnabled()
    ok.click()
    assert len(scene._undo_stack) == depth + 1
    assert marks.get_mark(d[("Level 1", 1000)]) == "D1"
    assert marks.get_mark(d[("Level 2", 7000)]) == "D4"
    scene.undo()
    assert sorted(marks.get_mark(op) for op in marks.items_of_category(scene, "Door")) == \
        ["D3", "D3", "D9", "D9"]


def test_no_change_pushes_nothing(qapp, shown_model_view):
    view, scene = shown_model_view
    _two_level_doors(scene)
    marks.apply_marks(scene, _plan(scene, "Door", "project"))
    scene.push_undo_state()
    depth = len(scene._undo_stack)
    assert marks.apply_marks(scene, _plan(scene, "Door", "project")) is False
    assert len(scene._undo_stack) == depth
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    assert not dlg.ok_enabled()                         # 0 change: OK disabled (mockup)
    assert dlg.footer_text() == "4 elements, 0 change"


def test_level_scope_keeps_others_and_starts_above(qapp, shown_model_view):
    view, scene = shown_model_view
    d = _two_level_doors(scene)
    mapping = _plan(scene, "Door", "level", "Level 1")
    assert set(mapping) == {d[("Level 1", 1000)], d[("Level 1", 7000)]}
    assert [mapping[d[("Level 1", 1000)]], mapping[d[("Level 1", 7000)]]] == ["D10", "D11"]


def test_selected_scope(qapp, shown_model_view):
    view, scene = shown_model_view
    d = _two_level_doors(scene)
    scene.clearSelection()
    d[("Level 2", 7000)].setSelected(True)
    assert _plan(scene, "Door", "selected") == {d[("Level 2", 7000)]: "D10"}


def test_dialog_scope_radios_drive_the_mapping(qapp, shown_model_view):
    view, scene = shown_model_view
    d = _two_level_doors(scene)
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    dlg.set_scope("level", "Level 1")
    assert set(dlg.current_mapping()) == {d[("Level 1", 1000)], d[("Level 1", 7000)]}
    assert dlg.footer_text().startswith("2 elements, ")
    dlg.set_scope("project")
    assert len(dlg.current_mapping()) == 4


def test_restart_per_level_with_level_token(qapp, shown_model_view):
    view, scene = shown_model_view
    _two_level_doors(scene)
    lm = scene._level_manager
    lm.get("Level 1").number, lm.get("Level 2").number = 1, 2
    scene.mark_patterns["Door"] = "{level}{n:02}"
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    assert dlg._restart.isEnabled() and dlg._restart.isChecked()
    assert sorted(dlg.current_mapping().values()) == ["101", "102", "201", "202"]
    dlg._restart.setChecked(False)
    assert sorted(dlg.current_mapping().values()) == ["101", "102", "203", "204"]


def test_restart_disabled_without_level_token(qapp, shown_model_view):
    view, scene = shown_model_view
    _two_level_doors(scene)
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    assert not dlg._restart.isEnabled() and not dlg._restart.isChecked()


def test_keep_order_sorts_by_existing_number(qapp, shown_model_view):
    view, scene = shown_model_view
    d = _two_level_doors(scene)
    marks.set_mark(d[("Level 1", 1000)], "D9")
    marks.set_mark(d[("Level 1", 7000)], "D3")
    plain = _plan(scene, "Door", "level", "Level 1")
    assert [plain[d[("Level 1", 1000)]], plain[d[("Level 1", 7000)]]] == ["D10", "D11"]
    keep = _plan(scene, "Door", "level", "Level 1", keep=True)
    assert [keep[d[("Level 1", 7000)]], keep[d[("Level 1", 1000)]]] == ["D10", "D11"]


def _gridlines(scene):
    out = {}
    for p1, p2, lab in ((QPointF(5000, 0), QPointF(5000, 9000), "X"),
                        (QPointF(0, 0), QPointF(0, 9000), "Y"),
                        (QPointF(-1000, 8000), QPointF(9000, 8000), "Q"),
                        (QPointF(-1000, 1000), QPointF(9000, 1000), "R")):
        gl = GridlineItem(p1, p2, lab)
        scene._register_gridline(gl)
        out[lab] = gl
    return out


def test_gridline_orientation_rule(qapp, shown_model_view):
    """Verticals 1, 2 left -> right; horizontals A, B bottom -> top (larger scene y = lower on plan = A)."""
    view, scene = shown_model_view
    g = _gridlines(scene)
    mapping = _plan(scene, "Gridline", "project")
    assert {lab: mapping[gl] for lab, gl in g.items()} == {"Y": "1", "X": "2", "Q": "A", "R": "B"}


def test_gridline_dialog_disables_pattern_and_checks(qapp, shown_model_view):
    view, scene = shown_model_view
    g = _gridlines(scene)
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Gridline")
    assert not dlg._pattern.isEnabled()
    assert not dlg._restart.isEnabled() and not dlg._keep.isEnabled()
    dlg.accept()
    assert [marks.get_mark(g[k]) for k in ("Y", "X", "Q", "R")] == ["1", "2", "A", "B"]


def test_blank_pattern_disables_ok_and_accept_writes_nothing(qapp, shown_model_view):
    view, scene = shown_model_view
    d = _two_level_doors(scene)
    scene.mark_patterns["Door"] = ""
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    assert "Pattern is blank: set one in Project Settings to renumber" in dlg.footer_text()
    assert not dlg.ok_enabled()
    dlg.accept()
    assert marks.get_mark(d[("Level 1", 1000)]) == "D3"


def test_table_shows_old_new_and_mockup_metrics(qapp, shown_model_view):
    view, scene = shown_model_view
    _two_level_doors(scene)
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    assert dlg.table_rows()[0] == ("Level 1", "D3", "D1")
    assert dlg._table.verticalHeader().defaultSectionSize() == 30
    assert [dlg._table.horizontalHeaderItem(i).text() for i in range(3)] == ["Level", "Old", "New"]
    assert dlg._body_outer.contentsMargins().left() == 20
    assert [dlg._cat.itemText(i) for i in range(dlg._cat.count())] == list(marks.RENUMBER_CATEGORIES)


def test_thumbnails_per_level(qapp, shown_model_view):
    view, scene = shown_model_view
    _two_level_doors(scene)
    dlg = RenumberDialog(scene, parent=None)
    dlg.set_category("Door")
    assert len(dlg._thumbs.findChildren(_OrderThumb)) == 2
    dlg.set_category("Gridline")
    assert len(dlg._thumbs.findChildren(_OrderThumb)) == 0


def test_duplicate_warn_clears_on_panel_after_renumber(qapp, shown_model_view):
    """Two doors share a Mark, one is selected; Renumber -> the panel row's warn state clears."""
    view, scene = shown_model_view
    d = _two_level_doors(scene)
    a, b = d[("Level 1", 1000)], d[("Level 1", 7000)]
    marks.set_mark(a, "D3")
    marks.set_mark(b, "D3")
    pm = PropertyManager()
    scene.requestPropertyUpdate.connect(pm.show_properties)     # main.py wires the same signal
    scene.clearSelection()
    a.setSelected(True)
    pm.show_properties(a)
    pm._do_refresh()
    assert pm._prop_widgets["Mark"].property("markDup") == "true"
    marks.apply_marks(scene, _plan(scene, "Door", "project"))      # the signal alone refreshes the panel
    assert pm._prop_widgets["Mark"].property("markDup") in (None, "", "false")
    assert pm._prop_widgets["Mark"].text() == marks.get_mark(a)


@pytest.fixture(scope="module")
def _window(qapp):
    import main as _main_module
    from firepro3d import snap_engine
    from firepro3d.view_3d import View3D
    from tests._mainwindow_helpers import dispose_main_window
    _main_module.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = _main_module.MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def test_manage_ribbon_renumber_button_opens_the_dialog(qapp, _window, monkeypatch):
    from firepro3d.ribbon_bar import RibbonButton
    btns = [b for b in _window.findChildren(RibbonButton)]
    texts = [b.text().replace("\n", " ") for b in btns]
    assert "Renumber" in texts and "Project Settings" in texts
    assert texts.index("Renumber") == texts.index("Project Settings") + 1
    seen = []
    monkeypatch.setattr(RenumberDialog, "exec", lambda self: seen.append(self) or 0)
    btns[texts.index("Renumber")].click()
    assert len(seen) == 1 and isinstance(seen[0], RenumberDialog)
    assert btns[texts.index("Renumber")].toolTip().startswith("Renumber element Marks")
