"""DM chrome revision AC1, AC2, AC4 (Model table look), AC5 -- real MainWindow,
real app QSS, observable chrome (VC3)."""
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QFrame, QLabel, QPushButton

from firepro3d.house_dialog import HouseDialog
from firepro3d.theme import detect
from firepro3d.ui_kit import TopTabs
from tests._dm_theme_helpers import dispose_dm, mw, open_dm, table_px  # noqa: F401

_LEFT = Qt.MouseButton.LeftButton


def test_dm_is_a_house_dialog_with_header_controls_and_footer(mw):
    dlg = open_dm(mw)
    try:
        assert isinstance(dlg, HouseDialog) and dlg.property("houseDialog") is True
        header = dlg.findChild(QFrame, "shellHeader")
        assert header is not None and header.isVisible()
        assert any(l.text() == "Display Manager" for l in header.findChildren(QLabel))
        assert any(l.pixmap() is not None and not l.pixmap().isNull()
                   for l in header.findChildren(QLabel))          # header icon rendered
        assert set(dlg._win_controls) == {"min", "max", "close"}
        assert dlg._resizable is True
        footer = dlg.findChild(QFrame, "footerBar")
        assert footer is not None and footer.isVisible()
    finally:
        dispose_dm(dlg)


def test_tabs_are_top_tabs_in_order_and_paper_context_opens_paper(mw):
    dlg = open_dm(mw, "model")
    try:
        assert isinstance(dlg._tabs, TopTabs)
        assert [dlg._tabs.tabText(i) for i in range(dlg._tabs.count())] == [
            "Model", "Paper Space", "Line Weights", "Fill Types", "Materials"]
        assert dlg._tabs.currentIndex() == 0
        dlg._tabs.setCurrentIndex(3)                       # Fill Types: footer actions off
        assert not dlg._reset_btn.isEnabled() and not dlg._default_btn.isEnabled()
        dlg._tabs.setCurrentIndex(4)                       # Materials: footer actions off too
        assert not dlg._reset_btn.isEnabled() and not dlg._default_btn.isEnabled()
        dlg._tabs.setCurrentIndex(0)
        assert dlg._reset_btn.isEnabled() and dlg._default_btn.isEnabled()
    finally:
        dispose_dm(dlg)
    dlg = open_dm(mw, "paper")
    try:
        assert dlg._tabs.currentIndex() == 1 and dlg._tabs.tabText(1) == "Paper Space"
    finally:
        dispose_dm(dlg)


def test_footer_order_primary_and_buttons_act(mw):
    dlg = open_dm(mw)
    try:
        footer = dlg.findChild(QFrame, "footerBar")
        btns = sorted(footer.findChildren(QPushButton),
                      key=lambda b: b.mapTo(dlg, b.rect().topLeft()).x())
        assert [b.text() for b in btns] == ["Reset All", "Set as Default", "Cancel", "OK"]
        ok = btns[-1]
        assert ok.isDefault() and ok.property("variant") == "primary"
        gap_left = btns[1].mapTo(dlg, btns[1].rect().topRight()).x()
        assert btns[2].mapTo(dlg, btns[2].rect().topLeft()).x() - gap_left > 40   # left cluster | right cluster
        QTest.mouseClick(ok, _LEFT)
        assert dlg.result() == QDialog.DialogCode.Accepted
    finally:
        dispose_dm(dlg)
    dlg = open_dm(mw)
    try:
        cancel = next(b for b in dlg.findChild(QFrame, "footerBar").findChildren(QPushButton)
                      if b.text() == "Cancel")
        QTest.mouseClick(cancel, _LEFT)
        assert dlg.result() == QDialog.DialogCode.Rejected
    finally:
        dispose_dm(dlg)


def test_model_tree_wears_the_underlay_table_look(mw):
    dlg = open_dm(mw)
    try:
        t = detect()
        tree = dlg._tree
        assert table_px(tree) == t.table.lower()                       # house table background
        grp = tree.topLevelItem(0)
        line_y = tree.visualItemRect(grp).bottom()
        vp = tree.viewport()
        assert vp.grab().toImage().pixelColor(vp.width() - 5, line_y).name() == t.line.lower()  # row line
    finally:
        dispose_dm(dlg)


def test_saved_size_survives_the_house_footer_adjustsize(mw):
    from PyQt6.QtCore import QSettings, QSize
    QSettings("GV", "FirePro3D").setValue("display_manager/window_size", QSize(1111, 777))
    dlg = open_dm(mw)
    try:
        assert dlg.size() == QSize(1111, 777)
        assert QSettings("GV", "FirePro3D").value("display_manager/window_size") == QSize(1111, 777)
    finally:
        dispose_dm(dlg)


def test_closed_dm_is_deleted_and_drops_its_theme_listeners(mw):
    """Seam review I1: the menu path (_open_display_manager, real exec()) must not
    leave the closed dialog alive under MainWindow, still subscribed to theme_bus.
    The kit's theme handlers are real Qt slots, so their connections drop with the
    widgets even while a Python wrapper (``seen``) outlives them."""
    from PyQt6.QtCore import QEvent, QTimer
    from PyQt6.QtWidgets import QApplication
    from firepro3d.display_manager import DisplayManager
    from firepro3d.theme import theme_bus
    bus = theme_bus()
    base = bus.receivers(bus.changed)
    seen = {}

    def close_modal():
        dlg = QApplication.activeModalWidget() or mw.findChildren(DisplayManager)[0]
        seen["dlg"] = dlg
        seen["live"] = bus.receivers(bus.changed)
        dlg.reject()

    QTimer.singleShot(0, close_modal)
    mw._open_display_manager()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()
    assert isinstance(seen["dlg"], DisplayManager)
    assert seen["live"] > base                          # rows really listened while open
    assert mw.findChildren(DisplayManager) == []
    assert bus.receivers(bus.changed) == base
