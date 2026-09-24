"""HALO aperture + priority band are app-wide, user-tunable module globals
(selection-mode §4.5), persisted under NEW keys (old halo/aperture_px ignored)."""
from PyQt6.QtCore import QPointF, QEvent, QSettings, Qt
from PyQt6.QtGui import QMouseEvent, QTransform
from PyQt6.QtWidgets import QApplication

from firepro3d import halo_selection as hs
from firepro3d.constants import HALO_APERTURE_PX, HALO_PRIORITY_BAND_PX
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def test_defaults_are_15_and_12():
    assert (HALO_APERTURE_PX, HALO_PRIORITY_BAND_PX) == (15, 12)
    assert hs.HALO_APERTURE_PX == 15 and hs.HALO_PRIORITY_BAND_PX == 12


def test_smaller_aperture_misses_offset_item(qapp):
    sc = Model_Space()
    sc.addItem(LineItem(QPointF(100.0, 0.0), QPointF(200.0, 0.0)))
    assert sc.halo_candidates_at(QPointF(0, 0), 10.0, QTransform()) == []
    assert len(sc.halo_candidates_at(QPointF(0, 0), 150.0, QTransform())) == 1


def test_pane_apply_sets_globals_and_new_keys(qapp):
    from firepro3d.settings.panes import UXPane   # confirm real class name
    pane = UXPane()
    pane.load()
    pane._halo_aperture.setValue(22)
    pane._halo_band.setValue(5)
    pane.apply()
    assert (hs.HALO_APERTURE_PX, hs.HALO_PRIORITY_BAND_PX) == (22, 5)
    s = QSettings("GV", "FirePro3D")
    assert s.value("halo/pick_aperture_px", type=int) == 22
    assert s.value("halo/priority_band_px", type=int) == 5
    pane.revert()
    assert (hs.HALO_APERTURE_PX, hs.HALO_PRIORITY_BAND_PX) == (15, 12)


def test_scene_has_no_per_scene_aperture(qapp):
    assert not hasattr(Model_Space(), "_halo_aperture_px")


# ── proves the views actually READ the module global (it was dead before
# this task) — a reviewer flagged that a self-referential test would hide
# this, so drive a real shown view with posted QMouseEvents. ──────────────

def _post_move(view, vp_pt):
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(vp_pt), Qt.MouseButton.NoButton,
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)


def test_model_view_reads_halo_aperture_global(qapp):
    from firepro3d.model_view import Model_View
    saved = hs.HALO_APERTURE_PX
    try:
        sc = Model_Space()
        sc.set_mode(None)
        line = LineItem(QPointF(20.0, 0.0), QPointF(100.0, 0.0))
        sc.addItem(line)
        view = Model_View(sc)
        view.resize(600, 600)
        view.show()
        QApplication.processEvents()
        view.resetTransform()

        hover = view.mapFromScene(QPointF(0.0, 0.0))
        _post_move(view, hover)
        QApplication.processEvents()
        # Default 15 px aperture: nearest point on the line is 20 scene units
        # (== 20 px at identity zoom) away -> miss.
        assert sc.halo_item() is None

        hs.HALO_APERTURE_PX = 30
        hover2 = view.mapFromScene(QPointF(0.0, 1.0))  # 1 px-different -> registers
        _post_move(view, hover2)
        QApplication.processEvents()
        assert sc.halo_item() is line
    finally:
        hs.HALO_APERTURE_PX = saved


def test_elevation_view_reads_halo_aperture_global(qapp, elevation_scene_for):
    from firepro3d.elevation_view import ElevationView
    saved = hs.HALO_APERTURE_PX
    try:
        _ms, elev = elevation_scene_for("north")
        line = LineItem(QPointF(20.0, 0.0), QPointF(100.0, 0.0))
        elev.addItem(line)
        view = ElevationView(elev)
        view.resize(600, 600)
        view.show()
        QApplication.processEvents()
        view.resetTransform()

        hover = view.mapFromScene(QPointF(0.0, 0.0))
        _post_move(view, hover)
        QApplication.processEvents()
        assert elev.halo_item() is None

        hs.HALO_APERTURE_PX = 30
        hover2 = view.mapFromScene(QPointF(0.0, 1.0))
        _post_move(view, hover2)
        QApplication.processEvents()
        assert elev.halo_item() is line
    finally:
        hs.HALO_APERTURE_PX = saved
