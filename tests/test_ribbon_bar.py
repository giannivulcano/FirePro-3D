"""Tests for the ribbon widget library (docs/specs/ribbon-bar.md)."""
from PyQt6.QtWidgets import QComboBox, QLabel
from firepro3d.ribbon_bar import RibbonGroup, RibbonButton, RibbonBar


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


# ── Density + vertical ALL-CAPS group labels (chrome revamp Task 3) ───────────

def test_group_label_is_uppercase_vertical(qapp):
    g = RibbonGroup("File")
    lbls = [w for w in g.findChildren(QLabel)]
    assert any(l.text() == "FILE" for l in lbls)   # ALL-CAPS


def test_large_button_is_compact(qapp):
    b = RibbonButton("X")
    assert b.height() <= 92         # was 111


def test_small_button_is_compact(qapp):
    from firepro3d.ribbon_bar import RibbonSmallButton
    b = RibbonSmallButton("X")
    assert b.height() <= 28         # was 33


def test_page_stack_is_compact(qapp):
    rb = RibbonBar()
    assert rb._stack.height() <= 110  # was 150
