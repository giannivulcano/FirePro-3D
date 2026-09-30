"""A freshly opened Block Editor tab frames the block's own geometry (smoke 1).

Guards run on SHOWN views: the MainWindow's editor tabs, and a standalone
editor widget seeded before its first show (the ``showEvent`` 40 m default
must not override the fit).
"""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import CircleItem, LineItem
from firepro3d.model_space import Model_Space


@pytest.fixture(scope="module")
def _main_window_singleton(qapp, tmp_path_factory):
    """Module-scoped MainWindow (test_block_explode.py pattern; the autosave
    path is redirected so a real recovery file can't pop a modal)."""
    from PyQt6.QtTest import QTest
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
        QTest.qWait(250)          # let the deferred startup fits land
        yield win
        win._modified = False
        win.close()
        win.deleteLater()


@pytest.fixture
def main_window(_main_window_singleton):
    win = _main_window_singleton
    yield win
    mgr = win.block_editor_manager
    for w in list(mgr.open_editors()):
        w._modified = False
        mgr.close(w)
    QApplication.processEvents()


# A ~500 mm block authored well away from the origin, so the 40 m default
# (centred on the origin) cannot pass for a fit.
_X0, _Y0 = 3000.0, 2000.0
_BLOCK_RECT = QRectF(_X0, _Y0, 500.0, 400.0)


def _block_prims():
    return [LineItem(QPointF(_X0, _Y0), QPointF(_X0 + 500, _Y0)).to_dict(),
            LineItem(QPointF(_X0, _Y0 + 400), QPointF(_X0 + 500, _Y0 + 400)).to_dict(),
            CircleItem(QPointF(_X0 + 250, _Y0 + 200), 100).to_dict()]


def _defn(name="FitB"):
    return BlockDefinition.new(name=name, library="L", series="S",
                               origin=(_X0, _Y0), primitives=_block_prims())


def _settle():
    from PyQt6.QtTest import QTest
    QApplication.processEvents()
    QTest.qWait(50)


def _assert_framed(view, rect=_BLOCK_RECT):
    """*rect* (scene) mapped to viewport pixels fills >= 60 % of the viewport's
    width or height and lies fully inside it."""
    vp = view.viewport().rect()
    assert view.isVisible() and vp.width() > 200 and vp.height() > 200
    px = view.mapFromScene(rect).boundingRect()
    assert vp.contains(px), (px, vp)
    assert (px.width() >= 0.6 * vp.width() or px.height() >= 0.6 * vp.height()), (px, vp)


def _default_m11(view):
    """m11 of Model_View.showEvent's ~40 m default for this viewport."""
    vp = view.viewport().rect()
    return min((vp.width() - 2) / 40_000, (vp.height() - 2) / (40_000 * vp.height() / vp.width()))


def _forget(proj, *defs):
    for d in defs:
        proj._block_definitions.pop(d.id, None)
    proj.blockDefinitionsChanged.emit()


def test_edit_definition_fits_a_fresh_tab_to_the_block(qapp, main_window):
    """Block Manager ▸ Open in Editor / plan Edit Block both route here."""
    proj = main_window.scene
    d = _defn()
    proj.register_block_definition(d)
    try:
        w = main_window.block_editor_manager.edit_definition(d.id)
        _settle()
        assert main_window.central_tabs.currentWidget() is w
        _assert_framed(w.view)
    finally:
        _forget(proj, d)


def test_create_block_from_a_selection_fits_the_seeded_geometry(qapp, main_window):
    """Ribbon Create Block seeded from a plan selection (open_new + seed_from_dicts)."""
    proj = main_window.scene
    items = [LineItem.from_dict(p) for p in _block_prims()[:2]]
    try:
        proj.clearSelection()
        for it in items:
            proj.addItem(it); proj._draw_lines.append(it); it.setSelected(True)
        main_window._open_block_editor()
        _settle()
        w = main_window.central_tabs.currentWidget()
        assert len(w.gather_primitives()) == 2
        _assert_framed(w.view)
    finally:
        for it in items:
            if it.scene() is proj:
                proj.removeItem(it)
            if it in proj._draw_lines:
                proj._draw_lines.remove(it)


def test_a_blank_new_block_keeps_the_default_view(qapp, main_window):
    w = main_window.block_editor_manager.open_new()
    _settle()
    assert w.view.isVisible()
    assert w.view.transform().m11() == pytest.approx(_default_m11(w.view), rel=0.02)


def test_refocusing_an_open_tab_keeps_the_users_zoom(qapp, main_window):
    proj = main_window.scene
    d = _defn("FitRefocus")
    proj.register_block_definition(d)
    try:
        mgr = main_window.block_editor_manager
        w = mgr.edit_definition(d.id)
        _settle()
        w.view.scale(3.0, 3.0)                       # the user zooms in
        w.view.centerOn(QPointF(_X0 + 480, _Y0 + 10))
        _settle()
        t = w.view.transform()
        c = w.view.mapToScene(w.view.viewport().rect().center())
        main_window.central_tabs.setCurrentIndex(0)   # away …
        _settle()
        assert mgr.edit_definition(d.id) is w         # … and back via Edit Block
        _settle()
        assert main_window.central_tabs.currentWidget() is w
        assert w.view.transform() == t
        assert w.view.mapToScene(w.view.viewport().rect().center()) == c
    finally:
        _forget(proj, d)


def test_seeding_before_the_first_show_is_not_overridden_by_the_default(qapp):
    """The trap: a view seeded (and fitted) before it is ever shown still
    frames the block after showEvent's first-show default would have run."""
    from PyQt6.QtTest import QTest
    from firepro3d.block_editor import BlockEditorWidget
    proj = Model_Space()
    d = _defn("FitPreShow")
    proj.register_block_definition(d)
    w = BlockEditorWidget(proj, block_id=d.id)
    try:
        w.seed_from_definition(d)
        w.resize(900, 700); w.show(); QTest.qWaitForWindowExposed(w)
        _settle()
        _assert_framed(w.view)
    finally:
        w.hide()
        w.editor_scene.cleanup()
        proj.cleanup()
