"""Shown MainWindow with placed section tabs (elevation-parity area E guards).

Real entry points only: the section tab is current and focused, context menus
are real QContextMenuEvents posted to the view (QMenu.exec captured), and the
Model Browser menu is its own ``customContextMenuRequested`` slot. Events are
posted with sendEvent, never QTest.mouseMove (that moves the real cursor).
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMenu, QTreeWidgetItemIterator

CUT_A, CUT_B, DEPTH = QPointF(0.0, 0.0), QPointF(10000.0, 0.0), 8000.0


def open_section_window(n_sections: int = 1):
    """A shown MainWindow with *n_sections* placed sections over one cut
    (parallel views of the same model), each with an open tab; the first tab
    is current and focused.

    Returns:
        ``(win, markers, views)``. The caller disposes *win* with
        ``tests._mainwindow_helpers.dispose_main_window`` and keeps
        ``win.scene`` referenced for the test's life.
    """
    from tests.test_section_manager import _main_window
    win = _main_window()
    sm = win.section_manager
    markers = []
    for _ in range(n_sections):
        m = sm.place_section(CUT_A, CUT_B)
        m.set_geometry(CUT_A, CUT_B, DEPTH, user=False)
        markers.append(m)
    win.show()
    QTest.qWaitForWindowExposed(win)
    views = [sm.open_section(m.name) for m in markers]
    QApplication.processEvents()
    show_tab(win, views[0])
    return win, markers, views


def show_tab(win, view):
    """Make *view*'s tab current and give it keyboard focus."""
    win.central_tabs.setCurrentWidget(view)
    QApplication.processEvents()
    view.setFocus()
    QApplication.processEvents()


def settle(scene):
    """Stop *scene*'s debounced rebuild and rebuild now (a forced rebuild)."""
    scene._rebuild_timer.stop()
    scene.rebuild()
    QApplication.processEvents()


def aim(view, scene_pt, px_per_mm: float = 4.0):
    """Zoom *view* to *px_per_mm* and centre it on *scene_pt*, so a posted
    event lands within a quarter millimetre of the point."""
    view.resetTransform()
    view.scale(px_per_mm, px_per_mm)
    view.centerOn(scene_pt)
    QApplication.processEvents()


def right_click(view, scene_pt, monkeypatch):
    """Post a real QContextMenuEvent at *scene_pt*; return the captured menu."""
    menus = []
    monkeypatch.setattr(QMenu, "exec", lambda self, *a: menus.append(self))
    vp = view.viewport()
    pt = view.mapFromScene(scene_pt)
    QApplication.sendEvent(vp, QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse, pt, vp.mapToGlobal(pt)))
    QApplication.processEvents()
    return menus[-1] if menus else None


def action(menu, text):
    """The action of *menu* labelled *text* (StopIteration when absent)."""
    return next(a for a in menu.actions() if a.text() == text)


def texts(menu) -> list:
    """The non-separator action labels of *menu*, in order."""
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def browser_menu(win, entities, monkeypatch):
    """Select *entities*' rows in the Model Browser and open its real context
    menu (the tree's customContextMenuRequested); return the captured menu."""
    from firepro3d.model_browser import _ROLE_ENTITY
    mb = win.model_browser
    mb.refresh()
    tree = mb._tree
    tree.clearSelection()
    want = {id(e) for e in entities}
    it = QTreeWidgetItemIterator(tree)
    while it.value() is not None:
        row = it.value()
        if row.data(0, _ROLE_ENTITY) in want:
            row.setSelected(True)
        it += 1
    menus = []
    monkeypatch.setattr(QMenu, "exec", lambda self, *a: menus.append(self))
    tree.customContextMenuRequested.emit(tree.viewport().rect().center())
    QApplication.processEvents()
    return menus[-1] if menus else None
