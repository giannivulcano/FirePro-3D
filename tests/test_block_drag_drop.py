"""Drag a block from the Blocks browser onto a canvas (AC2, AC4, AC5, AC13)."""
import json
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from main import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def _main_window_singleton(qapp):
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False
    win.close()
    win.deleteLater()


@pytest.fixture
def main_window(_main_window_singleton):
    yield _main_window_singleton


def _line_def(name, extra=()):
    prims = [LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict(), *extra]
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=(0.0, 0.0))


def _leaf(browser, name, library_only=False):
    """The tree leaf called *name* (``library_only``: the italic one)."""
    from firepro3d.blocks_browser import _ROLE_PATH
    t = browser._tree
    for i in range(t.topLevelItemCount()):
        lib = t.topLevelItem(i)
        for j in range(lib.childCount()):
            ser = lib.child(j)
            for k in range(ser.childCount()):
                leaf = ser.child(k)
                if leaf.text(0) != name:
                    continue
                if library_only and not leaf.data(0, _ROLE_PATH):
                    continue
                return leaf
    raise AssertionError(name)


def test_block_leaf_mime_carries_id(qapp, tmp_path):
    from firepro3d.blocks_browser import BlocksBrowser
    from firepro3d.mime_types import MIME_BLOCK
    sc = Model_Space()
    b = _line_def("B")
    sc.register_block_definition(b)
    br = BlocksBrowser(sc, root=str(tmp_path))
    mime = br._tree.mimeData([_leaf(br, "B")])
    assert mime.hasFormat(MIME_BLOCK)
    assert json.loads(bytes(mime.data(MIME_BLOCK)).decode()) == {"id": b.id, "path": None}
    folder = br._tree.topLevelItem(0)
    assert not br._tree.mimeData([folder]).hasFormat(MIME_BLOCK)


# ── Task 7: drop onto plan views / the Block Editor (D7) ───────────────────
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import (QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent,  # noqa: E402
                         QDropEvent)
from firepro3d.model_view import Model_View  # noqa: E402
from firepro3d.scale_manager import ScaleManager  # noqa: E402


def _shown(scene):
    scene.scale_manager = ScaleManager()
    v = Model_View(scene)
    v.resize(900, 700)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.resetTransform()
    v.centerOn(0, 0)
    QApplication.processEvents()
    return v


def _mime_for(browser, name, library_only=False):
    return browser._tree.mimeData([_leaf(browser, name, library_only)])  # the REAL payload


def _drag(view, mime, scene_pts, drop=True):
    vp = view.viewport()
    act = Qt.DropAction.CopyAction
    first = view.mapFromScene(scene_pts[0])
    enter = QDragEnterEvent(first, act, mime, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(vp, enter)
    accepted = enter.isAccepted()
    for p in scene_pts:
        mv = QDragMoveEvent(view.mapFromScene(p), act, mime, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, mv)
    if drop:
        dp = QDropEvent(QPointF(view.mapFromScene(scene_pts[-1])), act, mime,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(vp, dp)
    QApplication.processEvents()
    return accepted


def test_drop_on_plan_places_at_snapped_point_0deg_selected_one_undo(qapp, tmp_path):
    from firepro3d.blocks_browser import BlocksBrowser
    sc = Model_Space()
    b = _line_def("B")
    sc.register_block_definition(b)
    target = LineItem(QPointF(-300, 0), QPointF(-100, 0))      # endpoint to snap onto
    sc.addItem(target)
    sc._draw_lines.append(target)
    v = _shown(sc)
    br = BlocksBrowser(sc, root=str(tmp_path))
    sc.push_undo_state()
    try:
        near_end = QPointF(-103, 2)                              # within the aperture
        assert _drag(v, _mime_for(br, "B"), [QPointF(-250, 80), near_end])
        assert len(sc._block_instances) == 1
        inst = sc._block_instances[0]
        assert inst.block_pos() == (-100.0, 0.0)                 # snapped to the endpoint
        assert inst.block_rotation() == 0.0
        assert inst.level == sc.active_level
        assert inst.isSelected()
        assert sc.mode in (None, "select")                       # mode restored
        assert sc._place_block_ghost is None
        sc.undo()
        assert sc._block_instances == []
    finally:
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


def test_ghost_follows_during_drag(qapp, tmp_path):
    from firepro3d.blocks_browser import BlocksBrowser
    sc = Model_Space()
    b = _line_def("B")
    sc.register_block_definition(b)
    target = LineItem(QPointF(-300, 0), QPointF(-100, 0))      # endpoint to snap onto
    sc.addItem(target)
    sc._draw_lines.append(target)
    v = _shown(sc)
    br = BlocksBrowser(sc, root=str(tmp_path))
    try:
        _drag(v, _mime_for(br, "B"), [QPointF(0, 0), QPointF(55, -40)], drop=False)
        g = sc._place_block_ghost
        assert g is not None and g.block_pos() == pytest.approx((55.0, -40.0), abs=1.0)
        # mid-drag near the endpoint: the ghost sits on the SNAPPED point
        mv = QDragMoveEvent(v.mapFromScene(QPointF(-103, 2)), Qt.DropAction.CopyAction,
                            _mime_for(br, "B"), Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(v.viewport(), mv)
        assert sc._place_block_ghost is g
        assert g.block_pos() == (-100.0, 0.0)
        QApplication.sendEvent(v.viewport(), QDragLeaveEvent())
        assert sc._place_block_ghost is None
        assert sc.mode != "place_block"
    finally:
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


def test_drop_into_editor_nests_and_cycles_are_refused(qapp, tmp_path):
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.blocks_browser import BlocksBrowser
    proj = Model_Space()
    b = _line_def("B")
    proj.register_block_definition(b)
    a = _line_def("A", extra=[{"type": "block_instance", "block_id": b.id,
                               "pos": [0, 0], "rotation": 0.0}])
    proj.register_block_definition(a)
    c = _line_def("C")
    proj.register_block_definition(c)
    wb = BlockEditorWidget(proj, block_id=b.id)
    wb.seed_from_definition(b)
    v = wb.view
    v.resize(900, 700); v.show(); QTest.qWaitForWindowExposed(v)
    br = BlocksBrowser(proj, root=str(tmp_path))
    try:
        # A (⊃ B) onto B's editor → refused, nothing placed, footer reason
        msgs = []
        wb.editor_scene.instructionChanged.connect(msgs.append)
        assert not _drag(v, _mime_for(br, "A"), [QPointF(10, 10)])
        assert wb.editor_scene._block_instances == []
        assert any("can't contain itself" in m for m in msgs)
        assert "A contains B — a block can't contain itself" in msgs
        # B onto B's own editor → refused
        assert not _drag(v, _mime_for(br, "B"), [QPointF(10, 10)])
        assert wb.editor_scene._block_instances == []
        assert "B can't contain itself" in msgs          # exact user-visible text
        # an unrelated block C nests into B's editor
        assert _drag(v, _mime_for(br, "C"), [QPointF(10, 10)])
        assert [i.block_id for i in wb.editor_scene._block_instances] == [c.id]
    finally:
        wb.editor_scene.cleanup(); v.close(); QApplication.processEvents()


def test_italic_leaf_autoloads_on_drop_and_clash_refuses(qapp, tmp_path, monkeypatch):
    from firepro3d import block_library
    from firepro3d.blocks_browser import BlocksBrowser
    lib = _line_def("LibOnly")
    block_library.save_to_library(lib, root=str(tmp_path))
    sc = Model_Space()
    v = _shown(sc)
    br = BlocksBrowser(sc, root=str(tmp_path))
    shown = []   # patched up front: a load regression fails fast, never a modal
    monkeypatch.setattr("firepro3d.themed_message.themed_info",
                        lambda *a, **k: shown.append(a))
    try:
        assert lib.id not in sc._block_definitions
        # hover: the ghost previews the file's geometry, nothing is loaded
        _drag(v, _mime_for(br, "LibOnly"), [QPointF(0, 0)], drop=False)
        g = sc._place_block_ghost
        assert g is not None and g.render_ops()
        assert lib.id not in sc._block_definitions
        QApplication.sendEvent(v.viewport(), QDragLeaveEvent())
        _drag(v, _mime_for(br, "LibOnly"), [QPointF(0, 0)])
        assert lib.id in sc._block_definitions
        assert len(sc._block_instances) == 1
        assert shown == []
        # clash: a DIFFERENT id with the same (library, series, name) in the project
        clash_src = _line_def("Clash")
        block_library.save_to_library(clash_src, root=str(tmp_path))
        sc.register_block_definition(_line_def("Clash"))       # same name, other id
        br.refresh()
        n = len(sc._block_instances)
        _drag(v, _mime_for(br, "Clash", library_only=True), [QPointF(50, 50)])
        assert len(sc._block_instances) == n and len(shown) == 1
        # the double-click wording, naming the block
        assert shown[0][2] == ("Could not load “Clash”: a different block "
                               "already uses this name in the project.")
        assert clash_src.id not in sc._block_definitions
    finally:
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


def test_double_click_places_into_the_active_canvas(qapp, main_window):
    """AC13 through the real browser path: a real double-click on the leaf
    (BlocksBrowser itemDoubleClicked -> blockActivated -> MainWindow) with the
    Block Editor tab active arms the EDITOR; real clicks on the editor view
    place the instance there — none lands in the plan."""
    proj = main_window.scene
    b = _line_def("B_AC13")
    proj.register_block_definition(b)          # emits → the browser lists it
    w = main_window.block_editor_manager.open_new()
    QApplication.processEvents()
    QTest.qWaitForWindowExposed(w.view)
    plan_before = len(proj._block_instances)
    try:
        assert main_window.central_tabs.currentWidget() is w
        _dclick_leaf(main_window, b.name)
        assert w.editor_scene.mode == "place_block"
        assert proj.mode != "place_block"
        w.view.resetTransform()
        w.view.centerOn(0, 0)
        QApplication.processEvents()
        _click_place(w.view, QPointF(30, 20))
        placed = [(i.block_id, i.block_rotation()) for i in w.editor_scene._block_instances]
        assert placed == [(b.id, 0.0)]
        assert len(proj._block_instances) == plan_before
        assert all(i.block_id != b.id for i in proj._block_instances)
    finally:
        w.editor_scene.set_mode("select")
        main_window.block_editor_manager.close(w)
        _forget_defs(proj, b)
        QApplication.processEvents()


def test_detail_view_refuses_block_drops(qapp, tmp_path):
    """Detail views share the plan scene but refuse drops (only full plan
    views and the Block Editor accept)."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtWidgets import QTabWidget
    from firepro3d.blocks_browser import BlocksBrowser
    from firepro3d.detail_view import DetailViewManager
    sc = Model_Space()
    sc.scale_manager = ScaleManager()
    b = _line_def("B")
    sc.register_block_definition(b)
    tabs = QTabWidget()
    dm = DetailViewManager(sc, None, sc.scale_manager, tabs)
    dm.create_detail("Detail 1", QRectF(-500, -500, 1000, 1000))
    v = dm.open_detail("Detail 1")
    tabs.resize(900, 700); tabs.show(); QTest.qWaitForWindowExposed(tabs)
    v.resetTransform(); v.centerOn(0, 0); QApplication.processEvents()
    br = BlocksBrowser(sc, root=str(tmp_path))
    mode_before = sc.mode
    try:
        assert v._detail_name == "Detail 1"                     # a real detail view
        assert not _drag(v, _mime_for(br, "B"), [QPointF(0, 0), QPointF(20, 20)],
                         drop=False)
        assert sc._place_block_ghost is None
        assert sc.mode == mode_before
        _drag(v, _mime_for(br, "B"), [QPointF(20, 20)])
        assert sc._block_instances == []
        assert sc.mode == mode_before
    finally:
        sc.cleanup(); tabs.close(); tabs.deleteLater(); QApplication.processEvents()


# ── G3 review guards ───────────────────────────────────────────────────────
def _forget_defs(proj, *defs):
    """Drop test definitions from the shared MainWindow scene (singleton hygiene)."""
    for d in defs:
        proj._block_definitions.pop(d.id, None)
    proj.blockDefinitionsChanged.emit()


def test_block_enter_that_raises_leaves_no_drag_state(qapp, tmp_path, monkeypatch):
    """A raise while entering a block drag must not strand place_block / the
    drag state: the next (file) drag reaches the PDF/DXF import branch."""
    import os
    import sys
    from PyQt6.QtCore import QMimeData, QUrl
    from firepro3d.blocks_browser import BlocksBrowser
    escaped = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: escaped.append(a))
    sc = Model_Space()
    b = _line_def("B")
    sc.register_block_definition(b)
    v = _shown(sc)
    br = BlocksBrowser(sc, root=str(tmp_path))
    real_set_mode = sc.set_mode
    armed = [True]

    def _boom(mode, template=None):
        real_set_mode(mode, template=template)
        if mode == "place_block" and armed[0]:
            armed[0] = False
            raise RuntimeError("boom")
    real_set_mode("select")
    monkeypatch.setattr(sc, "set_mode", _boom)
    mode_before = sc.mode
    imports = []
    v.drop_import_requested.connect(imports.append)
    try:
        assert not _drag(v, _mime_for(br, "B"), [QPointF(0, 0)], drop=False)
        assert escaped == []                     # a Qt handler must not raise
        assert v._block_drag is None
        assert sc.mode == mode_before
        assert sc._place_block_ghost is None
        pdf = tmp_path / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(str(pdf))])
        assert _drag(v, md, [QPointF(10, 10), QPointF(30, 30)])
        assert [os.path.normcase(os.path.normpath(i)) for i in imports] == [
            os.path.normcase(str(pdf))]
        assert sc._block_instances == []
    finally:
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


def test_double_click_refuses_a_cycle_in_the_editor(qapp, main_window):
    proj = main_window.scene
    b = _line_def("B")
    proj.register_block_definition(b)
    a = _line_def("A", extra=[{"type": "block_instance", "block_id": b.id,
                               "pos": [0, 0], "rotation": 0.0}])
    proj.register_block_definition(a)
    w = main_window.block_editor_manager.open_for_definition(b.id)
    QApplication.processEvents()
    msgs = []
    w.editor_scene.instructionChanged.connect(msgs.append)
    mode_before = w.editor_scene.mode
    try:
        main_window._on_block_activated(a.id)
        assert w.editor_scene.mode == mode_before
        assert "A contains B \u2014 a block can't contain itself" in msgs
    finally:
        main_window.block_editor_manager.close(w)
        _forget_defs(proj, a, b)
        QApplication.processEvents()


def test_refused_double_click_on_italic_leaf_loads_nothing(qapp, main_window, tmp_path):
    """Double-click checks the cycle BEFORE loading, exactly like a drag."""
    from firepro3d import block_library
    proj = main_window.scene
    b = _line_def("B")
    proj.register_block_definition(b)
    lib_a = _line_def("LibA", extra=[{"type": "block_instance", "block_id": b.id,
                                      "pos": [0, 0], "rotation": 0.0}])
    block_library.save_to_library(lib_a, root=str(tmp_path))
    br = main_window.blocks_browser
    old_root = br._lib_root
    br._lib_root = str(tmp_path)
    br.refresh()
    w = main_window.block_editor_manager.open_for_definition(b.id)
    QApplication.processEvents()
    msgs = []
    w.editor_scene.instructionChanged.connect(msgs.append)
    undo_depth = len(proj._undo_stack)
    try:
        br._on_item_activated(_leaf(br, "LibA", library_only=True), 0)
        assert lib_a.id not in proj._block_definitions
        assert len(proj._undo_stack) == undo_depth
        assert w.editor_scene.mode != "place_block"
        assert "LibA contains B \u2014 a block can't contain itself" in msgs
    finally:
        main_window.block_editor_manager.close(w)
        _forget_defs(proj, b, lib_a)
        br._lib_root = old_root
        br.refresh()
        QApplication.processEvents()


# ── G5 review: drag-time cycle check uses the load's merge rule ─────────────

def _nest_rec(bid):
    return {"type": "block_instance", "block_id": bid, "pos": [0, 0], "rotation": 0.0}


def _bundle_case(tmp_path, *, project_b_nests_host):
    """Project holds host H and B; library-only X nests B and bundles its own
    B copy. Exactly one of the two B copies nests H."""
    from firepro3d import block_library
    proj = Model_Space()
    h = _line_def("H")
    proj.register_block_definition(h)
    b_proj = _line_def("B", extra=[_nest_rec(h.id)] if project_b_nests_host else ())
    proj.register_block_definition(b_proj)
    b_file = BlockDefinition.from_dict(b_proj.to_dict())
    b_file.primitives = [LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()]
    if not project_b_nests_host:
        b_file.primitives.append(_nest_rec(h.id))
    x = _line_def("X", extra=[_nest_rec(b_proj.id)])
    block_library.save_to_library(x, root=str(tmp_path),
                                  bundled={b_file.id: b_file.to_dict()})
    return proj, h, b_proj, x


def _host_editor(proj, h):
    from firepro3d.block_editor import BlockEditorWidget
    w = BlockEditorWidget(proj, block_id=h.id)
    w.seed_from_definition(h)
    v = w.view
    v.resize(900, 700); v.show(); QTest.qWaitForWindowExposed(v)
    return w, v


def test_drag_cycle_check_lets_the_project_copy_win(qapp, tmp_path, monkeypatch):
    """The bundle's B nests the host but the project's B does not: the load
    keeps the project's B, so no loop forms — the drag is accepted and the
    real load succeeds."""
    from firepro3d.blocks_browser import BlocksBrowser
    monkeypatch.setattr("firepro3d.themed_message.themed_info",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError(a)))
    proj, h, b_proj, x = _bundle_case(tmp_path, project_b_nests_host=False)
    w, v = _host_editor(proj, h)
    br = BlocksBrowser(proj, root=str(tmp_path))
    try:
        assert _drag(v, _mime_for(br, "X", library_only=True), [QPointF(10, 10)])
        assert x.id in proj._block_definitions
        assert proj.get_block_definition(b_proj.id) is b_proj      # project copy kept
        assert [i.block_id for i in w.editor_scene._block_instances] == [x.id]
    finally:
        w.editor_scene.cleanup(); v.close(); QApplication.processEvents()


def test_drag_cycle_check_sees_the_project_copy_nesting_the_host(qapp, tmp_path):
    """The project's B nests the host but the bundle's does not: loading X
    would give X ⊃ B ⊃ H inside H — the drag is refused, nothing loads."""
    from firepro3d.blocks_browser import BlocksBrowser
    proj, h, b_proj, x = _bundle_case(tmp_path, project_b_nests_host=True)
    w, v = _host_editor(proj, h)
    br = BlocksBrowser(proj, root=str(tmp_path))
    try:
        assert not _drag(v, _mime_for(br, "X", library_only=True), [QPointF(10, 10)])
        assert x.id not in proj._block_definitions
        assert w.editor_scene._block_instances == []
    finally:
        w.editor_scene.cleanup(); v.close(); QApplication.processEvents()


# ── VC9 seam round: italic drop / double-click = TWO undo steps (user decision) ─

def _plan_view(win):
    """Make the Plan tab current and return its (real) Model_View."""
    for i in range(win.central_tabs.count()):
        if win.central_tabs.tabText(i).startswith("Plan: "):
            win.central_tabs.setCurrentIndex(i)
            QApplication.processEvents()
            return win.central_tabs.widget(i)
    raise AssertionError("no Plan tab")


def _ctrl_z(view):
    """A real Ctrl+Z key press on *view* (the window-wide undo shortcut)."""
    view.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    QTest.keyClick(view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    QApplication.processEvents()


def _dclick_leaf(win, name, library_only=False):
    """A real mouse double-click on the Blocks browser leaf *name* (looked up
    after the browser is revealed — revealing it may rebuild the tree)."""
    win._focus_blocks_browser()
    QApplication.processEvents()
    tree = win.blocks_browser._tree
    leaf = _leaf(win.blocks_browser, name, library_only)
    tree.scrollToItem(leaf)
    QApplication.processEvents()
    at = tree.visualItemRect(leaf).center()
    # The OS sequence: press+release, then the double-click press+release.
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, at)
    QTest.mouseDClick(tree.viewport(), Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier, at)
    QApplication.processEvents()


def _click_place(view, scene_pt):
    """place_block with real mouse input: press for position, press again at
    the same point for 0° (anchor == cursor → the angle falls back to 0)."""
    from PyQt6.QtCore import QPoint
    vp_pt = view.mapFromScene(scene_pt)
    for _ in range(2):
        QTest.mouseMove(view.viewport(), vp_pt)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, QPoint(vp_pt))
        QApplication.processEvents()


def _drop_lib_instances(scene, block_id):
    for inst in [i for i in scene._block_instances if i.block_id == block_id]:
        if inst.scene() is scene:
            scene.removeItem(inst)
        scene._block_instances.remove(inst)


@pytest.mark.parametrize("how", ["drop", "double_click"])
def test_italic_leaf_load_and_place_are_two_undo_steps(qapp, main_window, tmp_path,
                                                       monkeypatch, how):
    """Ctrl+Z #1 removes the placed instance (the definition stays loaded);
    Ctrl+Z #2 unloads the definition — for a drop AND a double-click."""
    from firepro3d import block_library
    monkeypatch.setattr("firepro3d.themed_message.themed_info",
                        lambda *a, **k: pytest.fail(f"modal: {a}"))
    win = main_window
    proj = win.scene
    lib = _line_def(f"LibTwoStep_{how}")
    block_library.save_to_library(lib, root=str(tmp_path))
    view = _plan_view(win)
    br = win.blocks_browser
    old_root = br._lib_root
    br._lib_root = str(tmp_path)
    br.refresh()
    proj.set_mode("select")
    proj.push_undo_state()                   # baseline == the pre-test scene
    n0 = len(proj._block_instances)
    try:
        assert lib.id not in proj._block_definitions
        if how == "drop":
            assert _drag(view, _mime_for(br, lib.name, library_only=True),
                         [QPointF(0, 0), QPointF(40, 40)])
        else:
            _dclick_leaf(win, lib.name, library_only=True)
            assert proj.mode == "place_block"
            _click_place(view, QPointF(40, 40))
            proj.set_mode("select")
        assert lib.id in proj._block_definitions
        assert [i.block_id for i in proj._block_instances[n0:]] == [lib.id]
        _ctrl_z(view)                        # #1: the placement only
        assert len(proj._block_instances) == n0
        assert lib.id in proj._block_definitions
        _ctrl_z(view)                        # #2: the load
        assert lib.id not in proj._block_definitions
        assert len(proj._block_instances) == n0
    finally:
        proj.set_mode("select")
        _drop_lib_instances(proj, lib.id)
        _forget_defs(proj, lib)
        proj.push_undo_state()
        br._lib_root = old_root
        br.refresh()
        QApplication.processEvents()


# ── VC9 seam round: AC3 end to end (drag -> editor Save -> plan pixels) ────

def _lit_rows(scene, rect):
    """Lit-pixel count per rendered row of *rect* (black backdrop, 2 px/mm)."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QColor, QImage, QPainter
    w, h = int(rect.width() * 2), int(rect.height() * 2)
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.black)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), rect)
    p.end()
    rows = []
    for y in range(h):
        n = 0
        for x in range(w):
            c = QColor(img.pixel(x, y))
            if c.red() + c.green() + c.blue() > 200:
                n += 1
        rows.append(n)
    return rows


def test_nested_drag_save_renders_in_plan_and_follows_B_saves(qapp, tmp_path):
    """AC3: B's leaf dragged into A's editor, A saved through the editor's
    Save, a PLAN A draws B's pixels; editing + saving B in its own editor
    moves those pixels in the plan A."""
    from PyQt6.QtCore import QRectF
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.blocks_browser import BlocksBrowser
    proj = Model_Space()
    b = _line_def("B")                                   # (0,0)-(100,0)
    proj.register_block_definition(b)
    a = _line_def("A")
    proj.register_block_definition(a)
    wa = BlockEditorWidget(proj, block_id=a.id)
    wa.seed_from_definition(a)
    v = wa.view
    v.resize(900, 700); v.show(); QTest.qWaitForWindowExposed(v)
    v.resetTransform(); v.centerOn(0, 0); QApplication.processEvents()
    br = BlocksBrowser(proj, root=str(tmp_path))
    wb = None
    try:
        assert _drag(v, _mime_for(br, "B"), [QPointF(150, 250), QPointF(200, 300)])
        [nested] = wa.editor_scene._block_instances
        bx, by = nested.block_pos()
        assert wa.save() is a                            # the editor's real Save
        assert [p["block_id"] for p in a.primitives
                if p["type"] == "block_instance"] == [b.id]
        proj.place_block_instance(a.id, (0.0, 0.0))
        area = QRectF(bx - 20, by - 40, 140, 120)        # around B only
        row = lambda y_mm: int((y_mm - area.top()) * 2)  # scene y -> image row
        before = _lit_rows(proj, area)
        assert sum(before[row(by) - 3:row(by) + 4]) > 100   # B's line drawn in A
        assert sum(before[row(by + 50) - 3:row(by + 50) + 4]) == 0
        # edit B in its own editor and Save
        wb = BlockEditorWidget(proj, block_id=b.id)
        wb.seed_from_definition(b)
        wb.editor_scene._draw_lines[0].translate(0.0, 50.0)
        assert wb.save() is b
        after = _lit_rows(proj, area)
        assert sum(after[row(by) - 3:row(by) + 4]) == 0          # old B gone
        assert sum(after[row(by + 50) - 3:row(by + 50) + 4]) > 100   # new B drawn
    finally:
        for w in (wa, wb):
            if w is not None:
                w.editor_scene.cleanup()
        v.close(); proj.cleanup(); QApplication.processEvents()
