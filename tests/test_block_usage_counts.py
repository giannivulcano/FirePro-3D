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


def test_edit_block_never_reseeds_an_open_dirty_tab(qapp, main_window):
    """Requesting Edit Block for an already-open, modified editor focuses it
    and keeps the user's edit (no re-seed, no duplicate)."""
    proj = main_window.scene
    b = _line_def("B")
    proj.register_block_definition(b)
    mgr = main_window.block_editor_manager
    try:
        wb = mgr.edit_definition(b.id)
        QApplication.processEvents()
        extra = LineItem(QPointF(0, 50), QPointF(80, 50))
        wb.editor_scene.addItem(extra); wb.editor_scene._draw_lines.append(extra)
        wb.editor_scene._draw_lines[0].translate(0, 10)         # move the seeded line
        mgr.open_new()                                          # focus elsewhere
        QApplication.processEvents()
        assert mgr.edit_definition(b.id) is wb
        QApplication.processEvents()
        assert main_window._active_editor_widget() is wb
        lines = wb.editor_scene._draw_lines
        assert len(lines) == 2 and extra in lines
        assert abs(lines[0]._pt1.y() - 10.0) < 1e-6              # the move survived
        assert len([w for w in mgr.open_editors() if w._edit_block_id == b.id]) == 1
    finally:
        _close_all(mgr)
        _forget_defs(proj, b)


def test_block_manager_open_in_editor_seeds_fresh_and_focuses_open(qapp, main_window):
    """Block Manager ▸ Open in Editor goes through the one Edit Block path:
    a fresh tab is seeded; an open tab the user emptied is focused, never
    re-seeded."""
    from types import SimpleNamespace
    from firepro3d.block_manager import BlockManagerDialog
    proj = main_window.scene
    b = _line_def("B")
    proj.register_block_definition(b)
    mgr = main_window.block_editor_manager
    fake = SimpleNamespace(_current_def=lambda: b, main_window=main_window,
                           raise_=lambda: None)
    try:
        BlockManagerDialog._open_in_editor(fake)
        QApplication.processEvents()
        wb = [w for w in mgr.open_editors() if w._edit_block_id == b.id]
        assert len(wb) == 1 and len(wb[0].gather_primitives()) == 1
        wb = wb[0]
        es = wb.editor_scene
        for ln in list(es._draw_lines):                         # the user empties it
            es.removeItem(ln); es._draw_lines.remove(ln)
        BlockManagerDialog._open_in_editor(fake)
        QApplication.processEvents()
        assert [w for w in mgr.open_editors() if w._edit_block_id == b.id] == [wb]
        assert wb.gather_primitives() == []                     # not re-seeded
        assert main_window._active_editor_widget() is wb
    finally:
        _close_all(mgr)
        _forget_defs(proj, b)


# ── Task 12: "Used in" counts, delete refusal, save message (D12; AC10, AC11) ──

from firepro3d.model_space import Model_Space


def test_used_in_counts_direct_and_indirect(qapp):
    from firepro3d.block_manager import BlockTableModel, Col, SortRole
    sc = Model_Space()
    c = _line_def("C"); b = _line_def("B", extra=[_nested(c.id, 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    for d in (c, b, a):
        sc.register_block_definition(d)
    m = BlockTableModel(sc)
    row = m.row_for_id(c.id)
    assert m.data(m.index(row, Col.USED_IN), Qt.ItemDataRole.DisplayRole) == "2"
    assert m.data(m.index(row, Col.USED_IN), SortRole) == 2           # numeric sort key
    assert m.data(m.index(m.row_for_id(a.id), Col.USED_IN),
                  Qt.ItemDataRole.DisplayRole) == "0"
    assert m.headerData(Col.USED_IN, Qt.Orientation.Horizontal) == "Used in"
    assert Col.USED_IN == m.columnCount() - 1 and Col.STATUS == 4     # new LAST column


def test_delete_refused_while_nested_names_users(qapp):
    sc = Model_Space()
    b = _line_def("B"); a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    sc.register_block_definition(b); sc.register_block_definition(a)
    assert sc.delete_block_definition(b.id) is False
    assert b.id in sc._block_definitions
    assert sc.block_users_message(b.id) == \
        "\u201cB\u201d is used inside: A \u2014 explode or remove it there first."
    assert sc.block_users_message(a.id) is None


def test_delete_refused_for_indirect_use_names_all_users(qapp):
    sc = Model_Space()
    c = _line_def("C"); b = _line_def("B", extra=[_nested(c.id, 0, 0)])
    a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    for d in (c, b, a):
        sc.register_block_definition(d)
    assert sc.delete_block_definition(c.id) is False
    assert c.id in sc._block_definitions
    assert sc.block_users_message(c.id) == \
        "\u201cC\u201d is used inside: A, B \u2014 explode or remove it there first."


def test_manager_delete_shows_the_users_message(qapp, monkeypatch):
    import firepro3d.themed_message as tm
    from firepro3d.block_manager import BlockManagerDialog
    sc = Model_Space()
    b = _line_def("B"); a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    sc.register_block_definition(b); sc.register_block_definition(a)
    shown = []
    monkeypatch.setattr(tm, "themed_info", lambda *args, **k: shown.append(args))

    class _MW:
        settings = None
    dlg = BlockManagerDialog(sc, _MW(), apply_stylesheet=False)
    try:
        row = dlg.model.row_for_id(b.id)
        dlg.view.setCurrentIndex(dlg.proxy.mapFromSource(dlg.model.index(row, 0)))
        dlg._delete()
        assert b.id in sc._block_definitions
        assert shown and shown[-1][2] == sc.block_users_message(b.id)
    finally:
        dlg.close()


def test_save_message_counts_user_blocks(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    b = _line_def("B"); a = _line_def("A", extra=[_nested(b.id, 0, 0)])
    proj.register_block_definition(b); proj.register_block_definition(a)
    proj.place_block_instance(b.id, (0.0, 0.0))
    w = BlockEditorWidget(proj, block_id=b.id)
    w.seed_from_definition(b)
    msgs = []
    # _show_status writes to the host window's status bar; capture the text.
    w.editor_scene._show_status = lambda message, timeout=5000: msgs.append(message)
    try:
        w.save(None)
        assert "updated 1 placed instance(s) and 1 block(s) that use it" in msgs[-1]
    finally:
        w.editor_scene.cleanup()
