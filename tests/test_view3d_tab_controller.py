"""View3DTabController unit guards (view-3d.md I1-I4, I7)."""
from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QTabWidget, QWidget
from PyQt6 import sip


class _Fake3D(QWidget):
    def __init__(self):
        super().__init__()
        self.cleared = 0

    def clear_pick(self):
        self.cleared += 1


def _ctl(qapp, extra_tabs: int = 1):
    from firepro3d.view3d_tab import View3DTabController
    tabs = QTabWidget()
    v = _Fake3D()
    tabs.addTab(v, "3D Model")
    for i in range(extra_tabs):
        tabs.addTab(QWidget(), f"Plan: Level {i + 1}")
    return tabs, v, View3DTabController(tabs, v, QSettings("GV", "FirePro3D"))


def _pref(default):
    return QSettings("GV", "FirePro3D").value("ui/view3d_open", default, type=bool)


def test_close_hides_keeps_widget_and_writes_pref(qapp):
    tabs, v, c = _ctl(qapp)
    c.close()
    assert tabs.indexOf(v) == -1 and not sip.isdeleted(v)
    assert tabs.count() == 1
    assert v.cleared == 1
    assert _pref(True) is False
    assert not c.is_open()


def test_open_reinserts_leftmost_and_current(qapp):
    tabs, v, c = _ctl(qapp)
    c.close()
    tabs.setCurrentIndex(0)
    c.open()
    assert tabs.indexOf(v) == 0 and tabs.currentWidget() is v
    assert tabs.tabText(0) == "3D Model"
    assert _pref(False) is True
    c.open()                                    # idempotent (double-fire)
    assert tabs.count() == 2
    assert tabs.indexOf(v) == 0 and tabs.currentWidget() is v


def test_open_leftmost_with_three_tabs_and_later_current(qapp):
    tabs, v, c = _ctl(qapp, extra_tabs=2)
    c.close()
    assert tabs.count() == 2
    tabs.setCurrentIndex(1)                     # last plan tab current
    c.open()
    assert tabs.count() == 3
    assert tabs.indexOf(v) == 0 and tabs.currentWidget() is v
    assert [tabs.tabText(i) for i in range(3)] == [
        "3D Model", "Plan: Level 1", "Plan: Level 2"]


def test_open_when_already_open_but_not_current_selects_it(qapp):
    tabs, v, c = _ctl(qapp, extra_tabs=2)
    tabs.setCurrentIndex(2)
    c.open()
    assert tabs.count() == 3 and tabs.currentWidget() is v


def test_startup_pref_closed_closes_without_rewriting(qapp):
    QSettings("GV", "FirePro3D").setValue("ui/view3d_open", False)
    tabs, v, c = _ctl(qapp)
    c.apply_startup_pref()
    assert not c.is_open()
    assert tabs.indexOf(v) == -1 and not sip.isdeleted(v)
    assert _pref(True) is False


def test_startup_pref_default_keeps_tab_open(qapp):
    tabs, v, c = _ctl(qapp)                     # no pref stored -> default True
    c.apply_startup_pref()
    assert c.is_open() and tabs.indexOf(v) == 0
    assert v.cleared == 0


def test_close_remember_false_does_not_write_pref(qapp):
    QSettings("GV", "FirePro3D").setValue("ui/view3d_open", True)
    tabs, v, c = _ctl(qapp)
    c.close(remember=False)
    assert not c.is_open() and not sip.isdeleted(v)
    assert _pref(False) is True
