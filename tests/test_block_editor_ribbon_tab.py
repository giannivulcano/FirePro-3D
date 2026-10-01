"""The permanent Block Editor ribbon tab (ribbon-bar.md §3.2/§3.8; block-system.md).

Real MainWindow, shown, under the LIVE app QSS + font. The Block Editor page is
a base tab (last, after Draft) that exists with no editor open: its Block group
(New / Open / Manager / Insert) is always live, the editor-only groups are
disabled with a "no editor" tooltip until an editor tab is current; entering an
editor tab switches the ribbon to the page and leaving restores the prior tab.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from firepro3d import snap_engine

NO_EDITOR_TIP = "Open or create a block to edit"
PAGE = "Block Editor"
EDITOR_GROUPS = ("Definition", "2D Geometry", "Edit", "Modify")


@pytest.fixture(scope="module")
def mw(qapp, tmp_path_factory):
    import os
    from firepro3d import theme as th
    prev_qss, prev_font = qapp.styleSheet(), qapp.font()
    prev_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(tmp_path_factory.mktemp("appdata"))
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    w = main_mod.MainWindow()
    w.resize(1400, 850)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(200)
    yield w
    # A plan selection alive at close kills the process (filed) — clear first.
    w.scene.clearSelection()
    w._modified = False
    w.close()
    w.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)
    if prev_appdata is None:
        os.environ.pop("APPDATA", None)
    else:
        os.environ["APPDATA"] = prev_appdata


def _editors(w):
    from firepro3d.block_editor import BlockEditorWidget
    return [w.central_tabs.widget(i) for i in range(w.central_tabs.count())
            if isinstance(w.central_tabs.widget(i), BlockEditorWidget)]


def _plan_index(w):
    for i in range(w.central_tabs.count()):
        if w.central_tabs.tabText(i).startswith("Plan: "):
            return i
    raise AssertionError("no plan tab")


@pytest.fixture(autouse=True)
def _clean(mw, qapp):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    mw.ribbon._tab_bar.setCurrentIndex(0)
    qapp.processEvents()
    yield
    for e in _editors(mw):
        mw.block_editor_manager.close(e)
    mw.scene.clearSelection()
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()


# ── helpers ──────────────────────────────────────────────────────────────────

def _titles(w):
    tb = w.ribbon._tab_bar
    return [tb.tabText(i) for i in range(tb.count())]


def _page(w, title):
    tb = w.ribbon._tab_bar
    for i in range(tb.count()):
        if tb.tabText(i) == title:
            return w.ribbon._stack.widget(i)
    return None


def _groups(page):
    """``[(TITLE, RibbonGroup)]`` in on-page (layout) order."""
    from firepro3d.ribbon_bar import RibbonGroup
    from PyQt6.QtWidgets import QLabel
    out = []
    lay = page._layout
    for i in range(lay.count()):
        g = lay.itemAt(i).widget()
        if isinstance(g, RibbonGroup):
            out.append((g.findChildren(QLabel)[0].text(), g))
    return out


def _group(page, title):
    for t, g in _groups(page):
        if t == title.upper():
            return g
    raise AssertionError(title)


def _buttons(group):
    return {b.text(): b for b in group.findChildren(QToolButton)}


def _editor_only_buttons(w):
    page = _page(w, PAGE)
    out = []
    for title in EDITOR_GROUPS:
        out.extend(_buttons(_group(page, title)).values())
    return out


def _add_plan_pipe(w):
    pipe = w.scene.add_pipe(w.scene.add_node(0, -800), w.scene.add_node(1000, -800))
    return pipe


def _remove_pipe(w, pipe):
    w.scene.clearSelection()
    for it in (pipe, pipe.node1, pipe.node2):
        try:
            w.scene.removeItem(it)
        except Exception:
            pass


def _goto_page(w, qapp):
    tb = w.ribbon._tab_bar
    tb.setCurrentIndex(_titles(w).index(PAGE))
    qapp.processEvents()


# ── G1: roster ───────────────────────────────────────────────────────────────

def test_block_editor_is_last_base_tab_and_architecture_lost_block_group(mw):
    assert not _editors(mw)
    titles = _titles(mw)
    assert titles == ["Manage", "Architecture", "Sprinkler Systems", "Analyze",
                      "Draft", PAGE]
    arch = _page(mw, "Architecture")
    assert "BLOCK" not in [t for t, _g in _groups(arch)]


# ── G2: layout A ─────────────────────────────────────────────────────────────

def test_group_order_large_new_open_and_one_line_small_captions(mw):
    from firepro3d.ribbon_bar import RibbonButton, RibbonSmallButton
    page = _page(mw, PAGE)
    assert [t for t, _g in _groups(page)] == [
        "BLOCK", "DEFINITION", "2D GEOMETRY", "EDIT", "MODIFY"]
    block = _buttons(_group(page, "Block"))
    assert set(block) == {"New", "Open", "Manager", "Insert"}
    assert type(block["New"]) is RibbonButton
    assert type(block["Open"]) is RibbonButton
    assert type(block["Manager"]) is RibbonSmallButton
    assert type(block["Insert"]) is RibbonSmallButton
    defn = _buttons(_group(page, "Definition"))
    assert set(defn) == {"Save", "Save As", "Import", "Set Origin", "Edit Attributes"}
    smalls = page.findChildren(RibbonSmallButton)
    larges = [b for b in page.findChildren(QToolButton)
              if not isinstance(b, RibbonSmallButton)]
    assert sorted(b.text() for b in larges) == ["New", "Open"]
    assert smalls and all("\n" not in b.text() for b in smalls), \
        [b.text() for b in smalls if "\n" in b.text()]
    assert all(b.toolTip() for b in page.findChildren(QToolButton))


# ── G3: no editor current ────────────────────────────────────────────────────

def _assert_no_editor_state(w):
    for b in _editor_only_buttons(w):
        assert not b.isEnabled(), b.text()
        assert b.toolTip() == NO_EDITOR_TIP, (b.text(), b.toolTip())
    for b in _buttons(_group(_page(w, PAGE), "Block")).values():
        assert b.isEnabled(), b.text()
        assert b.toolTip() and b.toolTip() != NO_EDITOR_TIP


def test_no_editor_disables_editor_groups_with_tooltip(mw, qapp):
    _goto_page(mw, qapp)
    _assert_no_editor_state(mw)
    # The selection/clipboard-driven refresh must not re-enable them: give the
    # PLAN scene a selection, then fire the clipboard + refresh triggers.
    mw.block_editor_manager.open_new()          # connects the refresh once
    qapp.processEvents()
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    pipe = _add_plan_pipe(mw)
    clip = QApplication.clipboard()
    prev = clip.text()
    try:
        pipe.setSelected(True)
        clip.setText("probe-block-editor-ribbon")
        qapp.processEvents()
        mw._refresh_modify_buttons()
        _assert_no_editor_state(mw)
    finally:
        clip.setText(prev)
        _remove_pipe(mw, pipe)
        qapp.processEvents()


def test_edit_attributes_stays_disabled_with_an_editor(mw, qapp):
    mw.block_editor_manager.open_new()
    qapp.processEvents()
    attr = _buttons(_group(_page(mw, PAGE), "Definition"))["Edit Attributes"]
    assert not attr.isEnabled()
    assert attr.toolTip() == "Edit block attributes (coming soon)"


# ── G4: entering / leaving an editor tab ─────────────────────────────────────

def test_entering_editor_switches_page_and_leaving_restores(mw, qapp):
    mw.ribbon._tab_bar.setCurrentIndex(2)                 # Sprinkler Systems
    qapp.processEvents()
    mw.block_editor_manager.open_new()
    qapp.processEvents()
    assert _titles(mw)[mw.ribbon._tab_bar.currentIndex()] == PAGE
    assert mw.ribbon._stack.currentWidget() is _page(mw, PAGE)
    page = _page(mw, PAGE)
    for title in ("Definition", "2D Geometry"):
        for label, b in _buttons(_group(page, title)).items():
            if label == "Edit Attributes":
                continue
            assert b.isEnabled(), label
            assert b.toolTip() and b.toolTip() != NO_EDITOR_TIP, label
    # Edit/Modify follow _refresh_modify_buttons (empty editor selection).
    mods = mw._be_modify_buttons
    for label in mw._MODIFY_NEEDS_SELECTION:
        assert not mods[label].isEnabled(), label
    assert mods["Offset"].isEnabled()
    assert not mods["Explode"].isEnabled()
    for b in mods.values():
        assert b.toolTip() != NO_EDITOR_TIP
    # Draw buttons actually drive the editor scene.
    QTest.mouseClick(mw._block_mode_buttons["draw_line"], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert _editors(mw)[0].editor_scene.mode == "draw_line"
    _editors(mw)[0].editor_scene.set_mode("select")
    # Leave → the ribbon returns to the tab current before entering.
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    assert mw.ribbon._tab_bar.currentIndex() == 2
    _assert_no_editor_state(mw)


# ── G5: Block group buttons drive the real handlers ──────────────────────────

def test_block_group_buttons(mw, qapp, monkeypatch):
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    _goto_page(mw, qapp)
    btns = _buttons(_group(_page(mw, PAGE), "Block"))

    QTest.mouseClick(btns["New"], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert isinstance(mw.central_tabs.currentWidget(), BlockEditorWidget)
    assert len(_editors(mw)) == 1

    QTest.mouseClick(btns["Manager"], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    try:
        assert mw._block_manager.isVisible()
    finally:
        mw._block_manager.hide()

    mw._left_tabs.setCurrentIndex(0)
    if mw._left_tabs.currentWidget() is mw.blocks_browser:
        mw._left_tabs.setCurrentIndex(1)
    QTest.mouseClick(btns["Insert"], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert mw._left_tabs.currentWidget() is mw.blocks_browser

    defn = BlockDefinition.new(name="Pick Me", library="L", series="S",
                               primitives=[], origin=(0.0, 0.0))
    mw.scene.register_block_definition(defn)
    seen = {}

    class _FakeOpen:
        def __init__(self, scene, parent=None, **_kw):
            seen["scene"] = scene

        def exec(self):
            return 1

        def chosen_id(self):
            return defn.id

    import firepro3d.block_open_dialog as bod
    monkeypatch.setattr(bod, "BlockOpenDialog", _FakeOpen)
    try:
        QTest.mouseClick(btns["Open"], Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert seen["scene"] is mw.scene
        cur = mw.central_tabs.currentWidget()
        assert isinstance(cur, BlockEditorWidget)
        assert getattr(cur, "_editor_key", None) == defn.id
        assert mw.central_tabs.tabText(mw.central_tabs.currentIndex()) == "Block: Pick Me"
    finally:
        for e in _editors(mw):
            mw.block_editor_manager.close(e)
        qapp.processEvents()
        mw.scene._block_definitions.pop(defn.id, None)
        mw.scene.blockDefinitionsChanged.emit()


# ── G6: plan selection while an editor is current ────────────────────────────

def test_plan_selection_with_editor_current_inserts_no_contextual_tab(mw, qapp):
    mw.block_editor_manager.open_new()
    qapp.processEvents()
    pipe = _add_plan_pipe(mw)
    try:
        pipe.setSelected(True)
        qapp.processEvents()
        assert _titles(mw)[-1] == PAGE
        assert not any(t.startswith("Modify") for t in _titles(mw)), _titles(mw)
        assert _titles(mw)[mw.ribbon._tab_bar.currentIndex()] == PAGE
    finally:
        _remove_pipe(mw, pipe)
        qapp.processEvents()


# ── review Minor 1: a plan mode never lights a disabled page button ──────────

def test_plan_mode_does_not_check_disabled_block_editor_button(mw, qapp):
    move = mw._be_modify_buttons["Move"]
    assert not move.isEnabled()
    pipe = _add_plan_pipe(mw)
    try:
        pipe.setSelected(True)
        mw.scene.set_mode("move")
        qapp.processEvents()
        assert mw.scene.mode == "move"
        assert not move.isChecked()
        assert not any(b.isChecked() for b in mw._block_mode_buttons.values())
    finally:
        mw.scene.set_mode("select")
        _remove_pipe(mw, pipe)
        qapp.processEvents()
    # Inside an editor the same key still lights (parity with #217 sync).
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    mw._sync_mode_buttons("move")
    assert move.isChecked()
    mw._sync_mode_buttons("select")
    assert not move.isChecked()


# ── review Minor 3a: plan contextual tab on entry ────────────────────────────

def test_entering_editor_drops_plan_contextual_and_leaving_restores_its_base(mw, qapp):
    mw.ribbon._tab_bar.setCurrentIndex(2)                 # Sprinkler Systems
    qapp.processEvents()
    pipe = _add_plan_pipe(mw)
    try:
        pipe.setSelected(True)
        qapp.processEvents()
        assert any(t.startswith("Modify") for t in _titles(mw)), _titles(mw)
        mw.block_editor_manager.open_new()
        qapp.processEvents()
        assert not any(t.startswith("Modify") for t in _titles(mw)), _titles(mw)
        assert _titles(mw)[mw.ribbon._tab_bar.currentIndex()] == PAGE
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
        qapp.processEvents()
        assert _titles(mw)[mw.ribbon._tab_bar.currentIndex()] == "Sprinkler Systems"
        assert _titles(mw)[-1] == PAGE
    finally:
        _remove_pipe(mw, pipe)
        qapp.processEvents()


# ── review Minor 3b: closing the last editor onto an empty canvas ────────────
# (Kept LAST: it closes every canvas tab; the finally re-opens the plan.)

def test_closing_last_editor_to_empty_canvas_leaves_page_disabled(mw, qapp):
    from firepro3d.block_editor import BlockEditorWidget
    mw.ribbon._tab_bar.setCurrentIndex(1)                 # Architecture
    qapp.processEvents()
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    assert _titles(mw)[mw.ribbon._tab_bar.currentIndex()] == PAGE
    try:
        for i in range(mw.central_tabs.count() - 1, -1, -1):
            if not isinstance(mw.central_tabs.widget(i), BlockEditorWidget):
                mw._on_tab_close_requested(i)
                qapp.processEvents()
        assert [mw.central_tabs.widget(i) for i in range(mw.central_tabs.count())] == [ed]
        mw._on_tab_close_requested(mw.central_tabs.indexOf(ed))
        qapp.processEvents()
        assert mw.central_tabs.count() == 0
        tb = mw.ribbon._tab_bar
        assert 0 <= tb.currentIndex() < tb.count()
        assert _titles(mw)[tb.currentIndex()] == "Architecture"
        assert mw.ribbon._stack.currentWidget() is _page(mw, "Architecture")
        QApplication.clipboard().setText("probe-empty-canvas")
        qapp.processEvents()
        mw._refresh_modify_buttons()
        _assert_no_editor_state(mw)
    finally:
        mw._activate_plan_view("Level 1")
        qapp.processEvents()
