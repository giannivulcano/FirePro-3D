"""SB2b A3 / G-M4 -- Marks pane edits patterns; Next previews per keystroke; edits never rewrite Marks."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLineEdit

from firepro3d import marks
from firepro3d.settings.panes import MarksPane
from firepro3d.settings.project_settings_dialog import ProjectSettingsDialog
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening


def _door(scene, x, mark):
    w = scene._walls[0]
    op = WallOpening(w, feature_id="door_914", offset_along=x)
    op.level = w.level
    w.openings.append(op); scene.addItem(op)
    marks.set_mark(op, mark)
    return op


def _scene_with_doors(shown_model_view):
    view, scene = shown_model_view
    w = WallSegment(QPointF(0, 0), QPointF(6000, 0), thickness_mm=200.0)
    w.level = scene.active_level
    scene.addItem(w); scene._walls.append(w)
    _door(scene, 1000, "D1"); _door(scene, 3000, "D4")
    return view, scene


def _row(pane, category):
    t = pane._table
    return next(r for r in range(t.rowCount()) if t.item(r, 0).text() == category)


def test_dialog_has_marks_rail_row_third(qapp, shown_model_view):
    view, scene = shown_model_view
    dlg = ProjectSettingsDialog(scene=scene, get_info=lambda: {}, set_info=lambda d: None)
    assert dlg.rail_keys() == ["project_info", "units", "marks"]


def test_next_previews_per_keystroke(qapp, shown_model_view):
    view, scene = _scene_with_doors(shown_model_view)
    pane = MarksPane(scene=scene)
    pane.load(); pane.show(); QTest.qWaitForWindowExposed(pane)
    r = _row(pane, "Door")
    assert pane._table.item(r, 2).text() == "D5"
    pane._table.editItem(pane._table.item(r, 1))
    editor = pane._table.findChild(QLineEdit)
    editor.selectAll()
    QTest.keyClicks(editor, "DR-{n:02}")              # real keystrokes -> textEdited
    assert pane._table.item(r, 2).text() == "DR-01"   # no DR- Marks yet -> 1
    editor.selectAll(); QTest.keyClick(editor, Qt.Key.Key_Backspace)
    assert pane._table.item(r, 2).text() == "(blank)"


def test_apply_writes_patterns_and_never_rewrites_marks(qapp, shown_model_view):
    view, scene = _scene_with_doors(shown_model_view)
    pane = MarksPane(scene=scene)
    pane.load()
    r = _row(pane, "Door")
    pane._table.item(r, 1).setText("DR-{n:02}")
    pane.apply()
    assert scene.mark_patterns["Door"] == "DR-{n:02}"
    assert [marks.get_mark(d) for d in marks.items_of_category(scene, "Door")] == ["D1", "D4"]
    new = _door(scene, 5000, "")
    marks.mint(scene, new)
    assert marks.get_mark(new) == "DR-01"


def test_revert_restores_snapshot(qapp, shown_model_view):
    view, scene = _scene_with_doors(shown_model_view)
    pane = MarksPane(scene=scene)
    pane.load()
    pane._table.item(_row(pane, "Wall"), 1).setText("X{n}")
    pane.apply()
    pane.revert()
    assert scene.mark_patterns["Wall"] == "WL{n}"


def test_dialog_ok_applies_marks_pane(qapp, shown_model_view):
    """The real dialog path: OK writes the Marks pane; Cancel restores the snapshot."""
    view, scene = _scene_with_doors(shown_model_view)
    dlg = ProjectSettingsDialog(scene=scene, get_info=lambda: {}, set_info=lambda d: None)
    pane = dlg._panes["marks"]
    pane._table.item(_row(pane, "Door"), 1).setText("DR-{n:02}")
    dlg._on_ok()
    assert scene.mark_patterns["Door"] == "DR-{n:02}"
    assert [marks.get_mark(d) for d in marks.items_of_category(scene, "Door")] == ["D1", "D4"]
    dlg2 = ProjectSettingsDialog(scene=scene, get_info=lambda: {}, set_info=lambda d: None)
    dlg2._panes["marks"]._table.item(_row(dlg2._panes["marks"], "Door"), 1).setText("ZZ{n}")
    dlg2._panes["marks"].apply()
    dlg2.reject()
    assert scene.mark_patterns["Door"] == "DR-{n:02}"


def test_pane_metrics_match_mockup(qapp, shown_model_view):
    view, scene = shown_model_view
    pane = MarksPane(scene=scene)
    t = pane._table
    assert [t.horizontalHeaderItem(c).text() for c in range(3)] == ["Category", "Pattern", "Next"]
    assert t.rowCount() == 7 and t.columnWidth(0) == 110 and t.columnWidth(1) == 200
    assert t.verticalHeader().defaultSectionSize() == 30
    assert not (t.item(0, 0).flags() & Qt.ItemFlag.ItemIsEditable)
    assert not (t.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable)
