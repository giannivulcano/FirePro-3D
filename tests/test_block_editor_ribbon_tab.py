"""The permanent Build + Editor ribbon tabs (ribbon-bar.md §3.2/§3.8; block-system.md).

Real MainWindow, shown, under the LIVE app QSS + font. Build and Editor are base
tabs (last, after Draft) that exist with no editor open: Build's Block group
(New / Open / Manager / Insert) is always live, the editor-only groups are
disabled with a "no editor" tooltip until an editor tab is current; entering an
editor tab makes Build current and leaving restores the prior tab.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from firepro3d import snap_engine
from tests._mainwindow_helpers import dispose_main_window

NO_EDITOR_TIP = "Open or create a block to edit"
BUILD = "Build"
EDITOR = "Editor"
ROSTER = ["Manage", "Architecture", "Sprinkler Systems", "Analyze", "Draft",
          BUILD, EDITOR]
# (page, group) of every button gated by the canvas kind.
GATED = ((BUILD, "Definition"), (BUILD, "2D Geometry"), (EDITOR, "Edit"),
         (EDITOR, "Constrain"), (EDITOR, "Inspect"))


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
    dispose_main_window(w)
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
    out = []
    for page, title in GATED:
        out.extend(_buttons(_group(_page(w, page), title)).values())
    return out


# Groups a plan / detail canvas still can't use (Edit is live there, B2).
PLAN_OFF = (("Build", "Definition"), ("Build", "2D Geometry"))


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
    tb.setCurrentIndex(_titles(w).index(BUILD))
    qapp.processEvents()


# ── G1: roster ───────────────────────────────────────────────────────────────

def test_build_and_editor_are_the_last_base_tabs_and_architecture_lost_block_group(mw):
    assert not _editors(mw)
    titles = _titles(mw)
    assert titles == ROSTER
    arch = _page(mw, "Architecture")
    assert "BLOCK" not in [t for t, _g in _groups(arch)]


# ── G2: layout A ─────────────────────────────────────────────────────────────

def test_group_order_large_new_open_and_one_line_small_captions(mw):
    from firepro3d.ribbon_bar import RibbonButton, RibbonSmallButton
    page = _page(mw, BUILD)
    editor = _page(mw, EDITOR)
    assert [t for t, _g in _groups(page)] == [
        "BLOCK", "DEFINITION", "2D GEOMETRY"]
    assert [t for t, _g in _groups(editor)] == [
        "EDIT", "CONSTRAIN", "INSPECT"]            # B5: Edit + Modify merged
    block = _buttons(_group(page, "Block"))
    assert set(block) == {"New", "Open", "Manager", "Insert"}
    assert type(block["New"]) is RibbonButton
    assert type(block["Open"]) is RibbonButton
    assert type(block["Manager"]) is RibbonSmallButton
    assert type(block["Insert"]) is RibbonSmallButton
    defn = _buttons(_group(page, "Definition"))
    assert set(defn) == {"Save", "Save As", "Import", "Edit Attributes",
                         "Pattern Tile",       # hatch D-A32 (HF2 Task 7)
                         "Linetype",           # linetypes LT4-11f
                         "End Type",           # LT5 Q12
                         "Save as Template"}   # schematics.md D-S6 (SV3)
    both = page.findChildren(QToolButton) + editor.findChildren(QToolButton)
    smalls = [b for b in both if isinstance(b, RibbonSmallButton)]
    larges = [b for b in both
              if not isinstance(b, RibbonSmallButton)]
    # CS4 (parametric-constraint-system D15/§10): Constrain leads with a large
    # Smart Dimension button.
    assert sorted(b.text() for b in larges) == ["New", "Open", "Smart Dimension"]
    assert smalls and all("\n" not in b.text() for b in smalls), \
        [b.text() for b in smalls if "\n" in b.text()]
    assert all(b.toolTip() for b in both)


# ── G3: no editor current ────────────────────────────────────────────────────

def _assert_plan_state(w):
    """Plan canvas: Definition / 2D Geometry off with the no-editor tooltip;
    Edit, Constrain and Inspect are live (real tooltips; Edit's enable state
    per ``can_start``); the Block group is live."""
    for page, title in PLAN_OFF:
        for b in _buttons(_group(_page(w, page), title)).values():
            assert not b.isEnabled(), b.text()
            assert b.toolTip() == NO_EDITOR_TIP, (b.text(), b.toolTip())
    for title in ("Edit", "Constrain", "Inspect"):
        for b in _buttons(_group(_page(w, EDITOR), title)).values():
            assert b.toolTip() and b.toolTip() != NO_EDITOR_TIP, b.text()
    for b in _buttons(_group(_page(w, BUILD), "Block")).values():
        assert b.isEnabled(), b.text()
        assert b.toolTip() and b.toolTip() != NO_EDITOR_TIP


def test_no_editor_disables_editor_groups_with_tooltip(mw, qapp):
    _goto_page(mw, qapp)
    _assert_plan_state(mw)
    # The selection/clipboard-driven refresh must not re-enable the editor-only
    # groups: give the PLAN scene a selection, then fire the clipboard +
    # refresh triggers. Edit is live in plan: its enable state is exactly the
    # rule production uses (can_start per label, plus Delete).
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
        _assert_plan_state(mw)
        ctl = mw.scene._modify_ctl
        sel = mw.scene.selectedItems()
        assert sel
        expected = {label for label, tool in mw._TOOL_OF_LABEL.items()
                    if ctl.can_start(tool, sel)} | {"Delete"}
        # Copy is the plan-live probe (a lone pipe is not directly movable
        # per _transformable); Move is covered by the wall tests in
        # test_build_editor_tabs.py.
        assert "Copy" in expected
        btns = mw._be_modify_buttons
        on = {label for label, b in btns.items() if b.isEnabled()}
        assert on == expected, (on, expected)
        assert not btns["Explode"].isEnabled()          # Block-Editor-only (C3)
    finally:
        clip.setText(prev)
        _remove_pipe(mw, pipe)
        qapp.processEvents()


def test_edit_attributes_opens_the_attributes_editor(mw, qapp, monkeypatch):
    """SB1a smoke ruling 2026-10-21: the Definition group's Edit Attributes
    button (the pre-SB1a placeholder) is live on a block editor and opens the
    Attributes editor for the current editor; a schematic keeps it disabled
    (schematics.md D-S14)."""
    from firepro3d import block_attributes_editor as bae
    opened = []
    monkeypatch.setattr(bae.AttributesEditorDialog, "exec",
                        lambda self: opened.append(self._editor) or 0)
    w = mw.block_editor_manager.open_new()
    qapp.processEvents()
    attr = _buttons(_group(_page(mw, BUILD), "Definition"))["Edit Attributes"]
    assert attr.isEnabled()
    assert attr.toolTip() not in (NO_EDITOR_TIP, "Edit block attributes (coming soon)")
    QTest.mouseClick(attr, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert opened == [w]
    # A schematic editor: disabled with the schematic tooltip, click inert.
    mw.block_editor_manager.open_new(kind="schematic")
    qapp.processEvents()
    attr = _buttons(_group(_page(mw, BUILD), "Definition"))["Edit Attributes"]
    assert not attr.isEnabled()
    assert attr.toolTip() == mw._BE_ATTR_SCHEMATIC_TIP
    QTest.mouseClick(attr, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert opened == [w]


# ── G4: entering / leaving an editor tab ─────────────────────────────────────

def test_entering_editor_switches_page_and_leaving_restores(mw, qapp):
    mw.ribbon._tab_bar.setCurrentIndex(2)                 # Sprinkler Systems
    qapp.processEvents()
    mw.block_editor_manager.open_new()
    qapp.processEvents()
    assert _titles(mw)[mw.ribbon._tab_bar.currentIndex()] == BUILD
    assert mw.ribbon._stack.currentWidget() is _page(mw, BUILD)
    page = _page(mw, BUILD)
    for title in ("Definition", "2D Geometry"):
        for label, b in _buttons(_group(page, title)).items():
            if label in ("Save as Template", "Fill"):
                continue      # schematic-only (SV3) / selection-gated (HF3)
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
    _assert_plan_state(mw)


# ── G5: Block group buttons drive the real handlers ──────────────────────────

def test_block_group_buttons(mw, qapp, monkeypatch):
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.block_editor import BlockEditorWidget
    _goto_page(mw, qapp)
    btns = _buttons(_group(_page(mw, BUILD), "Block"))

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


# ── HF2 Task 7: Pattern Tile toggle (hatch D-A32) ────────────────────────────

def test_pattern_tile_button_toggles_and_follows_undo(mw, qapp):
    w = mw.block_editor_manager.open_new()
    qapp.processEvents()
    try:
        btn = _buttons(_group(_page(mw, BUILD), "Definition"))["Pattern Tile"]
        assert btn.isEnabled() and btn.isCheckable() and not btn.isChecked()
        assert "pattern" in btn.toolTip().lower()
        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert w.editor_scene.block_tile is not None
        assert w.editor_scene.tile_frame_item() is not None
        assert btn.isChecked()
        w.editor_scene.undo()                              # undo the toggle
        qapp.processEvents()
        assert w.editor_scene.block_tile is None
        assert not btn.isChecked()
    finally:
        mw.block_editor_manager.close(w)
        qapp.processEvents()


# ── review Minor 3b: closing the last editor onto an empty canvas ────────────
# (Kept LAST: it closes every canvas tab; the finally re-opens the plan.)

def test_closing_last_editor_to_empty_canvas_leaves_editor_groups_off(mw, qapp):
    from firepro3d.block_editor import BlockEditorWidget
    mw.ribbon._tab_bar.setCurrentIndex(1)                 # Architecture
    qapp.processEvents()
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    assert _titles(mw)[mw.ribbon._tab_bar.currentIndex()] == BUILD
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
        # The empty canvas is kind plan with view_available False: the editor
        # groups are off with the no-editor tip and every Edit button is off
        # (can_start) with its real tooltip.
        _assert_plan_state(mw)
        for b in mw._be_modify_buttons.values():
            assert not b.isEnabled(), b.text()
    finally:
        mw._activate_plan_view("Level 1")
        qapp.processEvents()


# ── HF3: the Fill button (R8) ────────────────────────────────────────────────

def test_fill_button_is_editor_only_always_enabled(mw, qapp):
    """HF4 AC1: Fill is live whenever a Block Editor is active -- with nothing
    selected it enters Pick point; with boundary candidates it runs HF3."""
    from PyQt6.QtCore import QPointF
    from firepro3d.geometry_2d import LineItem
    mw.block_editor_manager.open_new()
    qapp.processEvents()
    fill = _buttons(_group(_page(mw, BUILD), "2D Geometry"))["Fill"]
    assert fill is mw._be_fill_btn and fill in _editor_only_buttons(mw)
    assert fill.toolTip() == "Fill: select closed curves, or click with nothing selected to pick a point"
    mw._refresh_modify_buttons()
    assert fill.isEnabled()                                  # empty selection: still enabled
    es = _editors(mw)[0].editor_scene
    QTest.mouseClick(fill, Qt.MouseButton.LeftButton)        # nothing selected -> Pick point
    qapp.processEvents()
    assert es.mode == "pick_region"
    es.set_mode(None)
    a, b, c, d = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    for ln in (LineItem(a, b), LineItem(b, c), LineItem(c, d), LineItem(d, a)):
        es.addItem(ln); es._draw_lines.append(ln); ln.setSelected(True)
    qapp.processEvents()
    mw._refresh_modify_buttons()
    assert fill.isEnabled()
    QTest.mouseClick(fill, Qt.MouseButton.LeftButton)        # candidates -> HF3 chain closure
    qapp.processEvents()
    assert len(es._filled_regions) == 1 and es.selectedItems() == es._filled_regions
    mw._refresh_modify_buttons()
    assert fill.isEnabled()                                  # a region alone is no candidate, but the button stays live
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
