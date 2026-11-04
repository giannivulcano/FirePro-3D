"""Shared fixtures for the Display Manager chrome-revision guards (VC3: the real
MainWindow entry point ``_make_display_manager`` under the app's real QSS)."""
import pytest
from PyQt6.QtCore import QEvent, QPointF
from PyQt6.QtWidgets import QApplication

from tests._mainwindow_helpers import dispose_main_window


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow (isolated QSettings via conftest), same recipe as test_hf5_guards."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d import snap_engine
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def open_dm(mw, ctx="model"):
    """The real construction path (signal wiring included), shown, not exec'd."""
    dlg = mw._make_display_manager(ctx)
    dlg.show()
    QApplication.processEvents()
    return dlg


def dispose_dm(dlg):
    from PyQt6 import sip
    if sip.isdeleted(dlg):
        return
    dlg.hide()
    dlg.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()


def add_wall(mw, y=0.0):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, y), QPointF(4000, y))
    w.level = "Level 1"
    mw.scene._walls.append(w)
    mw.scene.addItem(w)
    return w


def table_px(table, x_from_right=5, y=3):
    """Colour of the table viewport at (w - x_from_right, y): inside the first row,
    clear of its bottom line, so it is the table background."""
    vp = table.viewport()
    return vp.grab().toImage().pixelColor(vp.width() - x_from_right, y).name()
