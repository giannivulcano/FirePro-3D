"""SF1 -- Project Settings fits the Marks table; dialog size remembered per project (.fpd)."""
import json

import pytest
from PyQt6.QtTest import QTest

from firepro3d import theme
from firepro3d.settings.project_settings_dialog import ProjectSettingsDialog


@pytest.fixture
def app_qss(qapp):
    old = qapp.styleSheet()
    qapp.setStyleSheet(theme.build_app_qss(theme.detect()))
    try:
        yield qapp
    finally:
        qapp.setStyleSheet(old)


def _dlg(scene):
    return ProjectSettingsDialog(scene=scene, get_info=lambda: {}, set_info=lambda d: None)


def _show_marks(dlg):
    dlg.show()
    QTest.qWaitForWindowExposed(dlg)
    dlg._rail.tabSelected.emit("marks")
    QTest.qWait(30)
    return dlg._panes["marks"]._table


def _assert_fits(table):
    assert not table.verticalScrollBar().isVisible()
    assert not table.horizontalScrollBar().isVisible()
    vp = table.viewport().rect()
    last = table.visualItemRect(table.item(table.rowCount() - 1, 0))
    assert last.height() > 0 and vp.contains(last)
    assert table.item(table.rowCount() - 1, 0).text() == "Room"
    # all three columns fully inside the viewport
    assert sum(table.columnWidth(c) for c in range(3)) <= vp.width()


def test_g_s1_marks_table_fits_at_default_size(app_qss, shown_model_view):
    _, scene = shown_model_view
    dlg = _dlg(scene)
    _assert_fits(_show_marks(dlg))


def test_g_s1_marks_table_fits_at_minimum_size(app_qss, shown_model_view):
    _, scene = shown_model_view
    dlg = _dlg(scene)
    table = _show_marks(dlg)
    dlg.resize(dlg.minimumSizeHint())
    QTest.qWait(30)
    assert dlg.size().height() >= dlg.minimumSizeHint().height()
    _assert_fits(table)


def _state(scene):
    return (len(scene._undo_stack), scene._undo_pos)


@pytest.mark.parametrize("path", ["cancel", "ok"])
def test_g_s2_close_records_size_without_dirty_or_undo(app_qss, shown_model_view, path):
    _, scene = shown_model_view
    fired = []
    scene.sceneModified.connect(lambda: fired.append(1))
    before = _state(scene)
    dlg = _dlg(scene)
    dlg.show(); QTest.qWaitForWindowExposed(dlg)
    dlg.resize(900, 700); QTest.qWait(30)
    (dlg.reject if path == "cancel" else dlg._on_ok)()
    assert scene.project_settings_size == (900, 700)
    assert _state(scene) == before
    assert fired == []


def test_g_s2_roundtrip_through_fpd_and_reopen(app_qss, shown_model_view, tmp_path):
    _, scene = shown_model_view
    dlg = _dlg(scene)
    dlg.show(); QTest.qWaitForWindowExposed(dlg)
    dlg.resize(900, 700); QTest.qWait(30)
    dlg.reject()
    f = str(tmp_path / "p.fpd")
    scene.save_to_file(f)
    assert json.load(open(f, encoding="utf-8"))["project_settings_size"] == [900, 700]
    scene._clear_scene()
    assert scene.project_settings_size is None
    scene.load_from_file(f)
    assert scene.project_settings_size == (900, 700)
    dlg2 = _dlg(scene)
    dlg2.show(); QTest.qWaitForWindowExposed(dlg2)
    assert (dlg2.width(), dlg2.height()) == (900, 700)


def test_g_s2_old_file_without_key_opens_at_fitted_default(app_qss, shown_model_view, tmp_path):
    _, scene = shown_model_view
    default = _dlg(scene)
    dsize = (default.width(), default.height())
    f = str(tmp_path / "p.fpd")
    scene.save_to_file(f)
    data = json.load(open(f, encoding="utf-8"))
    del data["project_settings_size"]
    json.dump(data, open(f, "w", encoding="utf-8"))
    scene.project_settings_size = (1000, 800)
    scene.load_from_file(f)
    assert scene.project_settings_size is None
    d = _dlg(scene)
    assert (d.width(), d.height()) == dsize


def test_g_s2_recorded_size_clamped_to_minimum(app_qss, shown_model_view):
    _, scene = shown_model_view
    scene.project_settings_size = (10, 10)
    d = _dlg(scene)
    assert d.width() >= d.minimumSizeHint().width()
    assert d.height() >= d.minimumSizeHint().height()


def test_g_s2_template_carries_no_size(shown_model_view, tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    from firepro3d.settings import template
    _, scene = shown_model_view
    scene.project_settings_size = (900, 700)
    path = template.save_current_as_default(scene)
    assert "project_settings_size" not in json.load(open(path, encoding="utf-8"))


def test_g_s1_marks_pane_min_width_shows_all_columns(app_qss):
    from firepro3d.constants import MARKS_NEXT_COL_MIN_WIDTH_PX
    from firepro3d.settings.panes import MarksPane
    pane = MarksPane(scene=None)
    pane.fit_table()
    t = pane._table
    need = t.columnWidth(0) + t.columnWidth(1) + MARKS_NEXT_COL_MIN_WIDTH_PX
    pane.resize(10, 10)
    pane.show(); QTest.qWaitForWindowExposed(pane); QTest.qWait(30)
    assert t.viewport().width() >= need
    assert not t.horizontalScrollBar().isVisible()
