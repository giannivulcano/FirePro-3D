"""
test_ribbon_bar_primitives.py
Tests for RibbonBar.insert_page / remove_page (Task C0 — dynamic-page primitives).
"""

from firepro3d.ribbon_bar import RibbonBar


def test_insert_page_keeps_index_parity(qapp):
    rb = RibbonBar()
    rb.add_page("A"); rb.add_page("B")            # indices 0,1
    page = rb.insert_page("CTX", 1, contextual=True)
    assert rb._tab_bar.tabText(1) == "CTX"
    assert rb._stack.widget(1) is page
    rb._tab_bar.setCurrentIndex(1)
    assert rb._stack.currentIndex() == 1          # parity holds


def test_remove_page_removes_both(qapp):
    rb = RibbonBar()
    rb.add_page("A"); ctx = rb.insert_page("CTX", 1)
    rb.remove_page(1)
    assert rb._tab_bar.count() == 1
    assert rb._stack.count() == 1
