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
    v = _shown(sc)
    br = BlocksBrowser(sc, root=str(tmp_path))
    try:
        _drag(v, _mime_for(br, "B"), [QPointF(0, 0), QPointF(55, -40)], drop=False)
        g = sc._place_block_ghost
        assert g is not None and g.block_pos() == pytest.approx((55.0, -40.0), abs=1.0)
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
        # B onto B's own editor → refused
        assert not _drag(v, _mime_for(br, "B"), [QPointF(10, 10)])
        assert wb.editor_scene._block_instances == []
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
        # clash: a DIFFERENT id with the same (library, series, name) in the project
        clash_src = _line_def("Clash")
        block_library.save_to_library(clash_src, root=str(tmp_path))
        sc.register_block_definition(_line_def("Clash"))       # same name, other id
        br.refresh()
        shown = []
        monkeypatch.setattr("firepro3d.themed_message.themed_info",
                            lambda *a, **k: shown.append(a))
        n = len(sc._block_instances)
        _drag(v, _mime_for(br, "Clash", library_only=True), [QPointF(50, 50)])
        assert len(sc._block_instances) == n and shown
        assert clash_src.id not in sc._block_definitions
    finally:
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


def test_double_click_places_into_the_active_canvas(qapp, main_window):
    proj = main_window.scene
    b = _line_def("B")
    proj.register_block_definition(b)
    w = main_window.block_editor_manager.open_new()
    QApplication.processEvents()
    try:
        main_window._on_block_activated(b.id)
        assert w.editor_scene.mode == "place_block"
        assert proj.mode != "place_block"
    finally:
        w.editor_scene.set_mode("select")
        main_window.block_editor_manager.close(w)
        QApplication.processEvents()
