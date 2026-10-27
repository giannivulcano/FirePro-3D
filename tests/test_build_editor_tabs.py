"""Build + Editor ribbon tabs (editor-build design §1; AC1-AC3, guards T1/T2).

Real MainWindow, shown, under the LIVE app QSS + font (VC3).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QToolButton

from firepro3d import snap_engine
from tests._mainwindow_helpers import dispose_main_window


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


def _remove(w, *items):
    w.scene.clearSelection()
    for it in items:
        try:
            w.scene.removeItem(it)
        except Exception:
            pass


def _plan_wall(w):
    from firepro3d.wall import WallSegment
    wall = WallSegment(QPointF(0, 0), QPointF(1000, 0))
    w.scene.addItem(wall)
    return (wall,)


def _plan_pipe(w):
    pipe = w.scene.add_pipe(w.scene.add_node(0, -800), w.scene.add_node(1000, -800))
    return (pipe, pipe.node1, pipe.node2)


# ── T2: selection never inserts or switches a ribbon tab (AC2, G4/G6) ────────

@pytest.mark.parametrize("make", ["wall", "pipe"])
def test_plan_user_selection_jumps_to_editor_and_clear_restores(mw, qapp, monkeypatch, make):
    inserted = []
    real_insert = mw.ribbon.insert_page
    monkeypatch.setattr(mw.ribbon, "insert_page",
                        lambda *a, **k: inserted.append(a) or real_insert(*a, **k))
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)                                   # Sprinkler Systems
    qapp.processEvents()
    before = _titles(mw)
    items = _plan_wall(mw) if make == "wall" else _plan_pipe(mw)
    try:
        items[0].setSelected(True)
        qapp.processEvents()
        assert inserted == [] and _titles(mw) == before
        assert tb.currentIndex() == mw._editor_page_index, "selection did not jump to Editor"
        mw.scene.clearSelection()
        qapp.processEvents()
        assert tb.currentIndex() == 2, "clearing did not restore the prior tab"
    finally:
        _remove(mw, *items)
        qapp.processEvents()


def test_clear_keeps_a_tab_the_user_moved_to(mw, qapp):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)
    items = _plan_wall(mw)
    try:
        items[0].setSelected(True)
        qapp.processEvents()
        assert tb.currentIndex() == mw._editor_page_index
        tb.setCurrentIndex(1)                                # user moves on
        mw.scene.clearSelection()
        qapp.processEvents()
        assert tb.currentIndex() == 1
    finally:
        _remove(mw, *items)
        qapp.processEvents()


def test_placement_auto_select_does_not_jump(mw, qapp):
    from PyQt6.QtCore import QEvent, QRectF
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(1)                                    # Architecture
    view, sc = mw.view, mw.scene
    view.resetTransform()
    view.fitInView(QRectF(-1500, -2000, 6000, 4000), Qt.AspectRatioMode.KeepAspectRatio)
    qapp.processEvents()
    n0 = len(sc._walls)
    sc.set_mode("wall")
    vp = view.viewport()
    for pt in (QPointF(0, 3000), QPointF(2000, 3000)):
        p = view.mapFromScene(pt)
        for et in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            QApplication.sendEvent(vp, QMouseEvent(et, QPointF(p), QPointF(vp.mapToGlobal(p)),
                                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                   Qt.KeyboardModifier.NoModifier))
    qapp.processEvents()
    placed = list(sc._walls[n0:])
    try:
        assert len(placed) == 1 and placed[0].isSelected(), "placement did not auto-select"
        assert tb.currentIndex() == 1, "the placement's auto-select jumped the ribbon"
        assert sc._auto_selected == frozenset({id(placed[0])}), "marker not held in select"
        sc.set_mode("wall")                                  # M8: a tool mode ends the marker
        assert sc._auto_selected is None, "stale _auto_selected survived a tool mode"
        sc.set_mode("select")
        sc.clearSelection()
        placed[0].setSelected(True)                          # now a user selection
        qapp.processEvents()
        assert tb.currentIndex() == mw._editor_page_index
    finally:
        sc.set_mode("select")
        _remove(mw, *placed)
        qapp.processEvents()


def test_block_editor_selection_jumps_to_editor_and_clear_returns_to_build(mw, qapp):
    from firepro3d.geometry_2d import LineItem
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    tb = mw.ribbon._tab_bar
    assert tb.currentIndex() == mw._build_page_index         # B3 entry
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    ed.editor_scene.addItem(ln)
    ed.editor_scene._draw_lines.append(ln)
    ln.setSelected(True)
    qapp.processEvents()
    assert tb.currentIndex() == mw._editor_page_index
    ed.editor_scene.clearSelection()
    qapp.processEvents()
    assert tb.currentIndex() == mw._build_page_index


def test_selection_on_a_paper_canvas_never_jumps(mw, qapp):
    mw._activate_paper_sheet()
    qapp.processEvents()
    assert mw._canvas_kind == "paper"
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)
    items = _plan_wall(mw)
    try:
        items[0].setSelected(True)                           # plan scene, paper current
        qapp.processEvents()
        assert tb.currentIndex() == 2
        # M6 moved-companion: the same selection made on the plan canvas jumps.
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
        qapp.processEvents()
        mw.scene.clearSelection()
        items[0].setSelected(True)
        qapp.processEvents()
        assert tb.currentIndex() == mw._editor_page_index, "plan selection did not jump"
    finally:
        _remove(mw, *items)
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
        qapp.processEvents()


@pytest.mark.parametrize("kind", ["paper", "3d", "section"])
def test_selection_on_a_non_edit_canvas_never_jumps(mw, qapp, kind):
    """M7: the kind gate holds on every canvas where Editor is not live."""
    undo = _open_canvas(mw, qapp, kind)
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)
    items = _plan_wall(mw)
    try:
        assert mw._canvas_kind == kind
        items[0].setSelected(True)                           # plan scene, other canvas current
        qapp.processEvents()
        assert tb.currentIndex() == 2, f"selection jumped on a {kind} canvas"
        undo()
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
        qapp.processEvents()
        mw.scene.clearSelection()
        items[0].setSelected(True)                           # moved-companion: plan jumps
        qapp.processEvents()
        assert tb.currentIndex() == mw._editor_page_index
    finally:
        _remove(mw, *items)
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
        qapp.processEvents()


# ── I1: leaving a canvas restores the pre-jump tab ───────────────────────────

@pytest.mark.parametrize("leave", ["close", "switch"])
def test_leaving_a_block_after_a_selection_jump_restores_the_original_tab(mw, qapp, leave):
    from firepro3d.geometry_2d import LineItem
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)                                    # Sprinkler Systems
    qapp.processEvents()
    ed = mw.block_editor_manager.open_new()
    qapp.processEvents()
    assert tb.currentIndex() == mw._build_page_index
    ln = LineItem(QPointF(0, 0), QPointF(100, 0))
    ed.editor_scene.addItem(ln)
    ed.editor_scene._draw_lines.append(ln)
    ln.setSelected(True)
    qapp.processEvents()
    assert tb.currentIndex() == mw._editor_page_index, "selection did not jump"
    if leave == "close":
        mw.block_editor_manager.close(ed)
    else:
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    assert tb.currentIndex() == 2, "left the block stuck on Editor"


@pytest.mark.parametrize("kind", ["paper", "3d", "section"])
def test_plan_selection_then_leaving_for_a_non_edit_canvas_restores_the_tab(mw, qapp, kind):
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)
    items = _plan_wall(mw)
    undo = lambda: None
    try:
        items[0].setSelected(True)
        qapp.processEvents()
        assert tb.currentIndex() == mw._editor_page_index, "selection did not jump"
        undo = _open_canvas(mw, qapp, kind)
        assert mw._canvas_kind == kind
        assert tb.currentIndex() == 2, f"leaving for {kind} kept Editor"
    finally:
        undo()
        _remove(mw, *items)
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
        qapp.processEvents()


def test_plan_selection_then_a_detail_tab_keeps_editor(mw, qapp):
    from PyQt6.QtCore import QRectF
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)
    items = _plan_wall(mw)
    try:
        items[0].setSelected(True)
        qapp.processEvents()
        assert tb.currentIndex() == mw._editor_page_index
        mw.detail_manager.create_detail("I1 Detail", QRectF(0, 0, 1000, 1000), "Level 1")
        mw.detail_manager.open_detail("I1 Detail")
        qapp.processEvents()
        assert mw._canvas_kind == "detail"
        assert tb.currentIndex() == mw._editor_page_index, "plan -> detail dropped Editor"
    finally:
        mw.detail_manager.close_detail("I1 Detail")
        _remove(mw, *items)
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
        qapp.processEvents()


def test_plan_selection_then_entering_a_block_returns_to_the_original_tab(mw, qapp):
    """F2: entering a block after a plan jump hands B3 the original tab."""
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(2)                                    # Sprinkler Systems
    items = _plan_wall(mw)
    ed = None
    try:
        items[0].setSelected(True)
        qapp.processEvents()
        assert tb.currentIndex() == mw._editor_page_index, "selection did not jump"
        ed = mw.block_editor_manager.open_new()
        qapp.processEvents()
        assert tb.currentIndex() == mw._build_page_index     # B3 entry
        mw.block_editor_manager.close(ed)
        ed = None
        qapp.processEvents()
        assert tb.currentIndex() == 2, "closing the block returned to Editor"
    finally:
        if ed is not None:
            mw.block_editor_manager.close(ed)
        _remove(mw, *items)
        mw.central_tabs.setCurrentIndex(_plan_index(mw))
        qapp.processEvents()


# ── T1a: roster + groups (AC1, G3/B5) ────────────────────────────────────────

ROSTER = ["Manage", "Architecture", "Sprinkler Systems", "Analyze", "Draft",
          "Build", "Editor"]
EDIT_ORDER = ["Copy", "Cut", "Paste", "Duplicate", "Delete", "Move", "Rotate",
              "Scale", "Flip", "Mirror", "Offset", "Array", "Explode"]


def _reading_order(group):
    """Button captions in on-screen reading order (column, then row)."""
    btns = [b for b in group.findChildren(QToolButton) if b.isVisible()]
    btns.sort(key=lambda b: (b.mapTo(group, b.rect().topLeft()).x() // 4,
                             b.mapTo(group, b.rect().topLeft()).y()))
    return [b.text() for b in btns]


def test_roster_is_seven_tabs_and_block_editor_is_gone(mw, qapp):
    assert _titles(mw) == ROSTER
    assert _page(mw, "Block Editor") is None


def test_build_and_editor_groups(mw, qapp):
    mw.ribbon._tab_bar.setCurrentIndex(ROSTER.index("Build"))
    qapp.processEvents()
    assert [t for t, _g in _groups(_page(mw, "Build"))] == [
        "BLOCK", "DEFINITION", "2D GEOMETRY"]
    mw.ribbon._tab_bar.setCurrentIndex(ROSTER.index("Editor"))
    qapp.processEvents()
    assert [t for t, _g in _groups(_page(mw, "Editor"))] == [
        "EDIT", "CONSTRAIN", "INSPECT"]
    assert _reading_order(_group(_page(mw, "Editor"), "Edit")) == EDIT_ORDER


# ── T1b: per-group enable state for every canvas kind (AC1, design §1 table) ─

NO_EDITOR_TIP = "Open or create a block to edit"
NIV = "Not available in this view"
KINDS = ("plan", "detail", "block", "schematic", "section", "paper", "3d")
PAGE_OF = {"Block": "Build", "Definition": "Build", "2D Geometry": "Build",
           "Edit": "Editor", "Constrain": "Editor", "Inspect": "Editor"}
# group -> {kind: off tooltip}; a kind not listed = the group is live there.
OFF = {
    "Block": {},
    "Definition": {"plan": NO_EDITOR_TIP, "detail": NO_EDITOR_TIP,
                   "section": NIV, "paper": NIV, "3d": NIV},
    "2D Geometry": {"plan": NO_EDITOR_TIP, "detail": NO_EDITOR_TIP,
                    "section": NIV, "paper": NIV, "3d": NIV},
    "Edit": {"section": NIV, "paper": NIV, "3d": NIV},
    "Constrain": {"section": NIV, "paper": NIV, "3d": NIV},
    "Inspect": {"section": NIV, "paper": NIV, "3d": NIV},
}
# One button per live group that must be enabled (selection-independent).
PROBE = {"Block": ("New", "Open", "Manager", "Insert"), "Definition": ("Save",),
         "2D Geometry": ("Line", "Fill"), "Constrain": ("Smart Dimension",),
         "Inspect": ("Show Constraints",)}
# Edit buttons enabled with the canvas's probe selection (B2): a plan wall,
# or a block-editor line; the clipboard holds no FirePro3D payload.  Array
# stays live on a wall (user ruling 2026-10-26: it copies walls through the
# paste path; ``can_start("array", [wall])`` is True).
EDIT_ON = {
    "plan": {"Copy", "Cut", "Duplicate", "Delete", "Move", "Rotate", "Array"},
    "detail": {"Copy", "Cut", "Duplicate", "Delete", "Move", "Rotate", "Array"},
    "block": {"Copy", "Cut", "Duplicate", "Delete", "Move", "Rotate", "Scale",
              "Flip", "Mirror", "Offset", "Array"},
    "schematic": {"Copy", "Cut", "Duplicate", "Delete", "Move", "Rotate",
                  "Scale", "Flip", "Mirror", "Offset", "Array"},
}


def _open_canvas(mw, qapp, kind):
    """Make a *kind* canvas current; return the cleanup callable."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QApplication
    from firepro3d.geometry_2d import LineItem
    QApplication.clipboard().setText("probe-not-a-payload")
    items, undo = [], lambda: None
    if kind in ("plan", "detail"):
        items = list(_plan_wall(mw))
        undo = lambda: _remove(mw, *items)
        if kind == "detail":
            mw.detail_manager.create_detail("T1 Detail", QRectF(0, 0, 1000, 1000),
                                            "Level 1")
            mw.detail_manager.open_detail("T1 Detail")

            def undo():
                _remove(mw, *items)
                mw.detail_manager.close_detail("T1 Detail")
    elif kind in ("block", "schematic"):
        ed = (mw.block_editor_manager.open_new() if kind == "block"
              else mw.block_editor_manager.open_new(kind="schematic"))
        qapp.processEvents()
        ln = LineItem(QPointF(0, 0), QPointF(100, 0))
        ed.editor_scene.addItem(ln)
        ed.editor_scene._draw_lines.append(ln)
        items = [ln]
    elif kind == "section":
        assert mw.section_manager.marker("north") is not None
        mw.section_manager.open_section("north")
        undo = lambda: mw.section_manager.close_section("north")
    elif kind == "paper":
        mw._activate_paper_sheet()
    elif kind == "3d":
        mw.view3d_tab.open()
        undo = lambda: mw.view3d_tab.close(remember=False)
    qapp.processEvents()
    for it in items:
        it.setSelected(True)
    qapp.processEvents()
    return undo


@pytest.mark.parametrize("kind", KINDS)
def test_canvas_kind_table(mw, qapp, kind):
    undo = _open_canvas(mw, qapp, kind)
    try:
        for group, offs in OFF.items():
            page = _page(mw, PAGE_OF[group])
            btns = _buttons(_group(page, group))
            if kind in offs:
                for label, b in btns.items():
                    assert not b.isEnabled(), (kind, group, label)
                    assert b.toolTip() == offs[kind], (kind, group, label, b.toolTip())
                continue
            for label, b in btns.items():
                assert b.toolTip() not in (NO_EDITOR_TIP, NIV), (kind, group, label)
            if group == "Edit":
                on = {l for l, b in btns.items() if b.isEnabled()}
                assert on == EDIT_ON[kind], (kind, on)
            else:
                for label in PROBE[group]:
                    assert btns[label].isEnabled(), (kind, group, label)
    finally:
        undo()
        qapp.processEvents()


def test_schematic_narrowing_runs_after_the_table(mw, qapp):
    """(c): a schematic keeps D-S14 narrowing on top of the live Definition group."""
    _open_canvas(mw, qapp, "schematic")
    d = _buttons(_group(_page(mw, "Build"), "Definition"))
    for label in ("Pattern Tile", "Linetype", "End Type", "Edit Attributes"):
        assert not d[label].isEnabled(), label
    assert d["Save as Template"].isEnabled()


# ── B3: entering a block/schematic canvas jumps to Build; restore rule ───────

def test_entering_an_editor_makes_build_current_and_leaving_restores(mw, qapp):
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(ROSTER.index("Sprinkler Systems"))
    qapp.processEvents()
    mw.block_editor_manager.open_new()
    qapp.processEvents()
    assert _titles(mw)[tb.currentIndex()] == "Build"
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    assert _titles(mw)[tb.currentIndex()] == "Sprinkler Systems"


def test_leaving_keeps_a_tab_the_user_moved_to(mw, qapp):
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(ROSTER.index("Sprinkler Systems"))
    mw.block_editor_manager.open_new()
    qapp.processEvents()
    tb.setCurrentIndex(ROSTER.index("Editor"))           # user moves off Build
    qapp.processEvents()
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    assert _titles(mw)[tb.currentIndex()] == "Editor"


def test_plan_or_paper_tab_change_never_switches_the_ribbon(mw, qapp):
    tb = mw.ribbon._tab_bar
    tb.setCurrentIndex(ROSTER.index("Draft"))
    qapp.processEvents()
    mw._activate_paper_sheet()
    qapp.processEvents()
    assert _titles(mw)[tb.currentIndex()] == "Draft"
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    assert _titles(mw)[tb.currentIndex()] == "Draft"


# ── R1: Editor buttons light for the plan scene's running tool ───────────────

def test_plan_move_lights_the_editor_move_button(mw, qapp):
    wall = _plan_wall(mw)
    move = mw._be_modify_buttons["Move"]
    try:
        wall[0].setSelected(True)
        qapp.processEvents()
        assert mw.scene._modify_ctl.start("move")
        qapp.processEvents()
        assert move.isChecked()
        mw.scene.set_mode("select")
        qapp.processEvents()
        assert not move.isChecked()
    finally:
        mw.scene.set_mode("select")
        _remove(mw, *wall)
        qapp.processEvents()


def test_off_canvas_never_lights_an_editor_button(mw, qapp):
    mw._activate_paper_sheet()
    qapp.processEvents()
    mw._sync_mode_buttons("move")
    assert not mw._be_modify_buttons["Move"].isChecked()
