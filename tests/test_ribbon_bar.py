"""Tests for the ribbon widget library (docs/specs/ribbon-bar.md)."""
from PyQt6.QtWidgets import QComboBox
from firepro3d.ribbon_bar import RibbonGroup


def test_add_widget_inserts_into_button_row(qapp):
    grp = RibbonGroup("Test")
    w = QComboBox()
    returned = grp.add_widget(w)
    assert returned is w
    assert w.parent() is not None
    assert grp._btn_row.indexOf(w) != -1


def test_add_widget_flushes_small_column(qapp):
    grp = RibbonGroup("Test")
    grp.add_small_button("A", None, None)
    grp.add_widget(QComboBox())
    assert grp._small_count == 0
