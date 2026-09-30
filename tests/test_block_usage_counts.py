"""Nested-block Edit Block routing (AC12 open) — more usage tests land in G5."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem


@pytest.fixture(scope="module")
def _main_window_singleton(qapp, tmp_path_factory):
    """Module-scoped MainWindow (test_modify_tools_ribbon.py pattern; the
    autosave path is redirected so a real recovery file can't pop a modal)."""
    import main as _main_module
    from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
    _main_module.View3D = View3D
    from main import MainWindow
    recovery = str(tmp_path_factory.mktemp("autosave") / "recovery.FPD")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
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


def _line_def(name, x0=0.0, x1=100.0, y=0.0, origin=(0.0, 0.0), extra=()):
    prims = [LineItem(QPointF(x0, y), QPointF(x1, y)).to_dict(), *extra]
    return BlockDefinition.new(name=name, library="L", series="S",
                               primitives=prims, origin=origin)


def _nested(block_id, x, y, rot=0.0):
    return {"type": "block_instance", "block_id": block_id,
            "pos": [x, y], "rotation": rot}


def _forget_defs(proj, *defs):
    """Drop test definitions from the shared MainWindow scene (singleton hygiene)."""
    for d in defs:
        proj._block_definitions.pop(d.id, None)
    proj.blockDefinitionsChanged.emit()


def _close_all(mgr):
    for w in list(mgr.open_editors()):
        w._modified = False
        mgr.close(w)
    QApplication.processEvents()


def test_edit_block_opens_or_focuses_the_nested_blocks_tab(qapp, main_window):
    proj = main_window.scene
    b = _line_def("B")
    proj.register_block_definition(b)
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    proj.register_block_definition(a)
    mgr = main_window.block_editor_manager
    try:
        wa = mgr.edit_definition(a.id)          # open + seed (Block Manager path)
        QApplication.processEvents()
        nested = wa.editor_scene._block_instances[0]
        wa.editor_scene.blockEditRequested.emit(nested.block_id)
        QApplication.processEvents()
        opened = [w for w in mgr.open_editors() if w._edit_block_id == b.id]
        assert len(opened) == 1
        assert len(opened[0].gather_primitives()) == 1     # seeded from B, not blank
        wa.editor_scene.blockEditRequested.emit(nested.block_id)   # again → focus, no duplicate
        QApplication.processEvents()
        assert len([w for w in mgr.open_editors() if w._edit_block_id == b.id]) == 1
    finally:
        _close_all(mgr)
        _forget_defs(proj, a, b)


def test_double_click_on_a_nested_block_opens_its_editor_tab(qapp, main_window):
    """Real input: a left double-click on the nested instance in A's editor
    view opens (then focuses) B's editor tab."""
    proj = main_window.scene
    b = _line_def("B", x0=-200.0, x1=200.0)
    proj.register_block_definition(b)
    a = _line_def("A", x0=0.0, x1=10.0, y=-500.0, extra=[_nested(b.id, 0, 0)])
    proj.register_block_definition(a)
    mgr = main_window.block_editor_manager
    try:
        wa = mgr.edit_definition(a.id)          # open + seed (Block Manager path)
        QApplication.processEvents()
        es = wa.editor_scene
        assert es.mode in (None, "select")
        v = wa.view
        v.resetTransform()
        v.centerOn(0, 0)
        QApplication.processEvents()
        pt = v.mapFromScene(QPointF(50, 0))
        QTest.mouseDClick(v.viewport(), Qt.MouseButton.LeftButton, pos=pt)
        QApplication.processEvents()
        opened = [w for w in mgr.open_editors() if w._edit_block_id == b.id]
        assert len(opened) == 1
        assert len(opened[0].gather_primitives()) == 1     # seeded from B, not blank
        assert main_window._active_editor_widget() is opened[0]
        mgr._tabs.setCurrentWidget(wa)
        QApplication.processEvents()
        QTest.mouseDClick(v.viewport(), Qt.MouseButton.LeftButton, pos=pt)
        QApplication.processEvents()
        assert len([w for w in mgr.open_editors() if w._edit_block_id == b.id]) == 1
        assert main_window._active_editor_widget() is opened[0]
    finally:
        _close_all(mgr)
        _forget_defs(proj, a, b)
