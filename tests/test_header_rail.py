"""Header rail (chrome revamp): identity + Save/Undo/Redo + project/dirty state."""
from firepro3d.header_rail import HeaderRail


def test_header_reflects_state(qapp):
    h = HeaderRail(app_version="9.9")
    h.set_project(name="Office-Tower", path="C:/x/Office-Tower.fpd", dirty=True)
    assert h.project_text().startswith("Office-Tower")
    assert h.is_dirty_shown() is True
    h.set_undo_enabled(False)
    h.set_redo_enabled(True)
    assert h.undo_button().isEnabled() is False
    assert h.redo_button().isEnabled() is True


def test_header_dirty_clears(qapp):
    h = HeaderRail(app_version="9.9")
    h.set_project(name="Tower", path="C:/x/Tower.fpd", dirty=True)
    assert h.is_dirty_shown() is True
    h.set_project(name="Tower", path="C:/x/Tower.fpd", dirty=False)
    assert h.is_dirty_shown() is False


def test_header_buttons_emit_signals(qapp):
    h = HeaderRail(app_version="9.9")
    fired = []
    h.saveRequested.connect(lambda: fired.append("save"))
    h.undoRequested.connect(lambda: fired.append("undo"))
    h.redoRequested.connect(lambda: fired.append("redo"))
    h.save_button().click()
    h.undo_button().click()
    h.redo_button().click()
    assert fired == ["save", "undo", "redo"]
