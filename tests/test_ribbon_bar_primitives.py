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


def test_ribbon_button_metrics_are_tokens(qapp):
    from firepro3d.theme import M
    from firepro3d.ribbon_bar import RibbonButton, RibbonSmallButton, RibbonBar
    b, s, rb = RibbonButton("X"), RibbonSmallButton("Y"), RibbonBar()
    assert b.iconSize().width() == M.RIBBON_LARGE_ICON == 40
    assert s.iconSize().width() == M.RIBBON_SMALL_ICON == 18
    assert s.height() == M.RIBBON_SMALL_H
    assert rb._stack.height() == M.RIBBON_STACK_H


def _ink_rows_in(img, rect, bg):
    rows = []
    for y in range(rect.top(), rect.bottom() + 1):
        for x in range(rect.left(), rect.right() + 1):
            c = img.pixelColor(x, y)
            if (abs(c.red() - bg.red()) + abs(c.green() - bg.green())
                    + abs(c.blue() - bg.blue())) > 150:
                rows.append(y)
                break
    return rows


def test_large_buttons_reserve_a_two_line_text_box(qapp):
    """Smoke 2026-09-30: two-line captions ("Create" / "Block") were clipped.

    Every large button reserves RIBBON_BTN_TEXT_LINES lines under the icon,
    text top + centre aligned; one- and two-line buttons are the same height;
    rendered ink of a two-line caption stays inside the button.
    """
    from PyQt6.QtGui import QColor, QIcon
    from firepro3d import theme as th
    from firepro3d.theme import M
    from firepro3d.ribbon_bar import RibbonBar
    old_ss = qapp.styleSheet()
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    try:
        rb = RibbonBar()
        g = rb.add_page("A").add_group("Block")
        from firepro3d.icons import themed_icon
        one = g.add_large_button("Wall", themed_icon("wall_icon.svg", "dark"), None)
        two = g.add_large_button("Create\nBlock", QIcon(), None)
        wrap = g.add_large_button("Project Settings", QIcon(), None)
        rb.resize(600, 160); rb.show(); qapp.processEvents()
        assert one.height() == two.height() == wrap.height()
        fm = two.fontMetrics()
        box_top = M.RIBBON_BTN_PAD + M.RIBBON_LARGE_ICON + M.RIBBON_ICON_TEXT_GAP
        assert two.height() >= box_top + M.RIBBON_BTN_TEXT_LINES * fm.lineSpacing() + M.RIBBON_BTN_PAD
        bg = QColor(th.detect().surface)
        for btn, lines in ((two, 2), (wrap, 2), (one, 1)):
            img = btn.grab().toImage()
            r = btn.rect().adjusted(1, box_top, -1, -1)
            rows = _ink_rows_in(img, r, bg)
            assert rows, btn.text()
            assert max(rows) <= btn.height() - 2, f"{btn.text()!r} text clipped"
            # top-aligned: ink starts in the first line slot
            assert min(rows) < box_top + fm.lineSpacing(), btn.text()
            # line count: ink reaches the second line slot only for 2-line text
            reaches_2nd = max(rows) >= box_top + fm.lineSpacing() + 2
            assert reaches_2nd == (lines == 2), btn.text()
        # the icon itself is painted in the icon slot above the text box
        img = one.grab().toImage()
        icon_slot = one.rect().adjusted(1, M.RIBBON_BTN_PAD, -1,
                                        -(one.height() - box_top + M.RIBBON_ICON_TEXT_GAP))
        assert _ink_rows_in(img, icon_slot, bg), "large-button icon not painted"
    finally:
        qapp.setStyleSheet(old_ss)
