"""DM smoke round 2 guards (VC3): the real MainWindow entry point, the app's real
stylesheet, a shown dialog, observable ground truth (grabbed pixels, header-model
text / alignment, widget geometry). QSettings is isolated by conftest."""
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QApplication, QDoubleSpinBox, QLabel, QToolButton,
                             QTreeWidget)

from firepro3d.theme import detect
from tests._dm_theme_helpers import dispose_dm, mw, open_dm  # noqa: F401

_HCENTER = int(Qt.AlignmentFlag.AlignHCenter.value)
_GLYPH_COLS = ("VIS", "COLOUR", "FILL", "SECTION")


def _flag(a) -> int:
    return int(getattr(a, "value", a))


def _px(img, p: QPoint) -> QColor:
    dpr = img.devicePixelRatio()
    return img.pixelColor(int(p.x() * dpr), int(p.y() * dpr))


def _near(c: QColor, hexc: str, tol: int = 4) -> bool:
    e = QColor(hexc)
    return all(abs(a - b) <= tol for a, b in
               ((c.red(), e.red()), (c.green(), e.green()), (c.blue(), e.blue())))


def _blend(over_hex: str, alpha: int, under_hex: str) -> QColor:
    o, u, a = QColor(over_hex), QColor(under_hex), alpha / 255.0
    return QColor(round(o.red() * a + u.red() * (1 - a)),
                  round(o.green() * a + u.green() * (1 - a)),
                  round(o.blue() * a + u.blue() * (1 - a)))


# 1 ───────────────────────────────────────────────────────────────────────────
def test_selected_tab_carries_the_accent_soft_fill(mw):
    dlg = open_dm(mw)
    try:
        t = detect()
        tabs, bar = dlg._tabs, dlg._tabs._bar
        img = tabs.grab().toImage()
        r = bar.tabRect(bar.currentIndex())
        sel = bar.mapTo(tabs, QPoint(r.left() + 4, r.center().y()))   # padding, clear of text
        other = bar.tabRect(1)
        unsel = bar.mapTo(tabs, QPoint(other.left() + 4, other.center().y()))
        want = _blend(t.accent, 34, t.surface)                         # accent_soft over the surface
        assert _near(_px(img, sel), want.name(), 4), (_px(img, sel).name(), want.name())
        assert _near(_px(img, unsel), t.surface, 3), _px(img, unsel).name()   # unselected: bare surface
    finally:
        dispose_dm(dlg)


# 2 ───────────────────────────────────────────────────────────────────────────
def test_tab_strip_never_shows_scroll_buttons_even_narrow(mw):
    dlg = open_dm(mw)
    try:
        dlg.setMinimumSize(0, 0)
        dlg.resize(260, 400)
        QApplication.processEvents()
        bar = dlg._tabs._bar
        bar.setMaximumWidth(150)                                       # narrower than its four tabs
        QApplication.processEvents()
        assert bar.width() < bar.sizeHint().width()                    # genuinely overflowing
        shown = [b for b in bar.findChildren(QToolButton) if b.isVisible()]
        assert shown == []
    finally:
        dispose_dm(dlg)


# 3 ───────────────────────────────────────────────────────────────────────────
def _tree_headers(tree: QTreeWidget):
    hi = tree.headerItem()
    return [(hi.text(c), _flag(hi.textAlignment(c))) for c in range(tree.columnCount())]


def _check_headers(pairs):
    for text, align in pairs:
        assert text == text.upper(), text
        if text in _GLYPH_COLS:
            assert align & _HCENTER, (text, align)


def test_model_paper_and_lw_headers_are_caps_and_glyph_columns_centred(mw):
    dlg = open_dm(mw)
    try:
        model = _tree_headers(dlg._tree)
        paper = _tree_headers(dlg._ps_tree)
        assert {t for t, _ in model} >= set(_GLYPH_COLS)
        assert {t for t, _ in paper} >= set(_GLYPH_COLS)
        _check_headers(model)
        _check_headers(paper)
        lw = dlg._lw_table
        lw_texts = [lw.horizontalHeaderItem(c).text() for c in range(lw.columnCount())]
        assert lw_texts and all(x == x.upper() for x in lw_texts), lw_texts
    finally:
        dispose_dm(dlg)


# 4 ───────────────────────────────────────────────────────────────────────────
def _cell_corner(tree, widget):
    """Colour at the top-left corner of an item widget, read from the grabbed
    viewport (what the user sees: host + row)."""
    vp = tree.viewport()
    return _px(vp.grab().toImage(), widget.mapTo(vp, QPoint(1, 1)))


def test_eye_and_swatch_cells_paint_the_row_background(mw):
    dlg = open_dm(mw)
    try:
        t = detect()
        w = dlg._cat_data["Pipe"]["widgets"]
        eye_host = w["vis"].parentWidget()
        for name, widget in (("eye", eye_host), ("colour", w["color_btn"]),
                             ("fill", w["fill_btn"])):
            assert widget.isVisible(), name
            c = _cell_corner(dlg._tree, widget)
            assert c.name() != "#1e1e1e", name
            assert _near(c, t.table, 2), (name, c.name(), t.table)
        # the Paper tab shares the cell look
        dlg._tabs.setCurrentIndex(1)
        QApplication.processEvents()
        some = next(iter(dlg._paper_cat_data.values()))
        for name, widget in (("p-eye", some["vis"].parentWidget()),
                             ("p-colour", some["color_btn"])):
            assert widget.isVisible(), name
            c = _cell_corner(dlg._ps_tree, widget)
            assert _near(c, t.table, 2), (name, c.name(), t.table)
    finally:
        dispose_dm(dlg)


# 5 ───────────────────────────────────────────────────────────────────────────
def test_model_tree_columns_are_retired_and_blocks_weight_lives_on_line_weights(mw):
    dlg = open_dm(mw)
    try:
        tree = dlg._tree
        assert tree.columnCount() == 7
        assert [tree.headerItem().text(c) for c in range(7)] == [
            "NAME", "VIS", "COLOUR", "FILL", "SECTION", "OPACITY", ""]
        assert tree.findChildren(QDoubleSpinBox) == []
        combo = dlg._model_blocks_combo
        assert dlg._lw_tab.isAncestorOf(combo) and not tree.isAncestorOf(combo)
        assert not combo.isVisible()                               # LW tab not current
        dlg._tabs.setCurrentWidget(dlg._lw_tab)
        QApplication.processEvents()
        assert combo.isVisible()
        assert any(l.text().startswith("Model blocks weight") and l.isVisible()
                   for l in dlg._lw_tab.findChildren(QLabel))
    finally:
        dispose_dm(dlg)


# 7 ───────────────────────────────────────────────────────────────────────────
def _flush(dlg, table, *, below_divider=True, to_bottom=True):
    tabs = dlg._tabs
    tl = table.mapTo(tabs, QPoint(0, 0))
    br = table.mapTo(tabs, QPoint(table.width(), table.height()))
    div = tabs._divider
    div_bottom = div.mapTo(tabs, QPoint(0, div.height())).y()
    assert tl.x() == 0, tl
    assert br.x() == tabs.width(), (br, tabs.size())
    if to_bottom:
        assert br.y() == tabs.height(), (br, tabs.size())
    else:
        assert br.y() < tabs.height()          # a control row sits below the table
    if below_divider:
        assert tl.y() == div_bottom, (tl.y(), div_bottom)
    return tl


def test_tables_sit_flush_under_the_divider_and_to_the_page_edges(mw):
    dlg = open_dm(mw)
    try:
        _flush(dlg, dlg._tree)
        dlg._tabs.setCurrentWidget(dlg._lw_tab)
        QApplication.processEvents()
        _flush(dlg, dlg._lw_table, to_bottom=False)    # +/-/Blocks-weight row below
        dlg._tabs.setCurrentIndex(1)
        QApplication.processEvents()
        tl = _flush(dlg, dlg._ps_tree, below_divider=False)   # colour-mode row sits above it
        div = dlg._tabs._divider
        assert tl.y() > div.mapTo(dlg._tabs, QPoint(0, div.height())).y()
    finally:
        dispose_dm(dlg)
