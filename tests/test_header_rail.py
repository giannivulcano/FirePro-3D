"""Header rail (chrome revamp): identity + Save/Undo/Redo + project/dirty state."""
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import Qt, QEvent, QPointF
from firepro3d.header_rail import HeaderRail


def _mouse(kind, buttons=Qt.MouseButton.LeftButton):
    pt = QPointF(40, 8)
    return QMouseEvent(kind, pt, pt, Qt.MouseButton.LeftButton, buttons,
                       Qt.KeyboardModifier.NoModifier)


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


def test_header_drag_offset_set_on_press_cleared_on_release(qapp):
    """Left-press on a restored window arms the drag; release clears it."""
    h = HeaderRail(app_version="9.9")   # top-level, not maximized/fullscreen
    h.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress))
    assert h._drag_offset is not None
    h.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease,
                               buttons=Qt.MouseButton.NoButton))
    assert h._drag_offset is None


def test_header_double_click_requests_maximize(qapp):
    h = HeaderRail(app_version="9.9")
    fired = []
    h.maximizeRequested.connect(lambda: fired.append(1))
    h.mouseDoubleClickEvent(_mouse(QEvent.Type.MouseButtonDblClick))
    assert fired == [1]


def test_header_separators_are_visible(qapp):
    """The two section dividers render HEADER_SEP_H tall in the muted role.

    Guard: pre-2026-09-30 they were width-only QFrames that laid out 0 px tall.
    """
    from PyQt6.QtWidgets import QFrame
    from PyQt6.QtGui import QColor
    from firepro3d import theme as th
    h = HeaderRail(app_version="9.9")
    h.resize(900, th.M.HEADER_H)
    h.show()
    qapp.processEvents()
    seps = [f for f in h.findChildren(QFrame) if f.width() == th.M.SEAM]
    assert len(seps) == 2
    img = h.grab().toImage()
    want = QColor(getattr(th.detect(), th.HEADER_SEP_ROLE))
    for s in seps:
        x = s.geometry().x()
        hits = sum(1 for y in range(h.height())
                   if img.pixelColor(x, y).name() == want.name())
        assert hits >= th.M.HEADER_SEP_H - 1


def test_header_logo_is_the_themed_glyph(qapp):
    from PyQt6.QtGui import QColor
    from firepro3d import theme as th
    h = HeaderRail(app_version="9.9")
    pm = h._icon.pixmap()
    assert pm is not None and not pm.isNull()
    assert pm.width() == th.M.HEADER_ICON
    img = pm.toImage()
    acc = QColor(th.detect().accent)
    assert any(abs(img.pixelColor(x, y).green() - acc.green()) < 30
               and abs(img.pixelColor(x, y).red() - acc.red()) < 30
               and img.pixelColor(x, y).alpha() > 200
               for x in range(img.width()) for y in range(img.height()))
