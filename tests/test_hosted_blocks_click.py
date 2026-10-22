"""G15/G16: activate + click placement in a section, Space rotates, Esc
cancels, cursor snaps to datums / gridline verticals / crossings."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.section_scene import ElevDatumItem, ElevGridlineItem
from tests._hosted_blocks_helpers import gridline, defn
from tests.test_section_classification import _placed_scene


def _view(section_scene_for):
    from firepro3d.elevation_view import SectionView
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    gl = gridline(ms, (0, -3000), (6000, -3000), "B")
    gridline(ms, (2000, 0), (2000, -6000), "2")   # perpendicular: projects a vertical at h=2000
    sec.rebuild()
    v = SectionView(sec)
    v.resize(900, 700)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.fit_to_screen()
    QApplication.processEvents()
    return ms, sec, gl, v


def test_click_places_and_space_rotates(qapp, section_scene_for):
    ms, sec, gl, v = _view(section_scene_for)
    d = defn(ms)
    sec.begin_place_block(d.id)
    assert sec._place_ghost is not None
    QTest.keyClick(v.viewport(), Qt.Key.Key_Space)
    # Space is Model_Space's step: -90 (clockwise on screen); the ghost follows.
    assert sec._place_rot == pytest.approx(-90.0)
    assert sec._place_ghost.block_rotation() == pytest.approx(-90.0)
    pt = v.mapFromScene(QPointF(4000.0, -1500.0))
    QTest.mouseMove(v.viewport(), pt)
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, pt)
    (inst,) = ms.hosted_blocks_on(gl)
    assert inst.block_rotation() == pytest.approx(-90.0)
    assert inst.host["along_mm"] == pytest.approx(4000.0, abs=100.0)
    assert sec._place_block_id == d.id          # stays armed after a click (repeat)
    assert sec._place_ghost is not None         # ghost re-created by the rebuild
    v.close()


def test_esc_cancels(qapp, section_scene_for):
    ms, sec, gl, v = _view(section_scene_for)
    sec.begin_place_block(defn(ms).id)
    QTest.keyClick(v.viewport(), Qt.Key.Key_Escape)
    assert sec._place_block_id is None and sec._place_ghost is None
    assert not any(it.scene() is sec and getattr(it, "_is_ghost", False)
                   for it in sec.items())
    v.close()


def test_snap_to_gridline_vertical_and_datum(qapp, section_scene_for):
    ms, sec, gl, v = _view(section_scene_for)
    vx = next(it for it in sec.items() if isinstance(it, ElevGridlineItem))
    dv = next(it for it in sec.items() if isinstance(it, ElevDatumItem))
    hx = vx.mapToScene(vx.line().p1()).x()
    vy = dv.mapToScene(dv.line().p1()).y()
    tol = sec._snap_tol_scene(v)
    assert tol > 0
    # crossing: near both
    p = sec.snap_section_point(QPointF(hx + tol * 0.5, vy - tol * 0.5), v)
    assert (p.x(), p.y()) == pytest.approx((hx, vy))
    # vertical only: y is left alone
    p = sec.snap_section_point(QPointF(hx + tol * 0.5, vy - tol * 5), v)
    assert (p.x(), p.y()) == pytest.approx((hx, vy - tol * 5))
    # datum only: x is left alone
    p = sec.snap_section_point(QPointF(hx + tol * 5, vy - tol * 0.5), v)
    assert (p.x(), p.y()) == pytest.approx((hx + tol * 5, vy))
    # beyond tolerance: untouched
    far = QPointF(hx + tol * 3, vy - tol * 3)
    assert sec.snap_section_point(far, v) == far
    v.close()


def test_snapped_click_lands_on_the_vertical(qapp, section_scene_for):
    """A click within the aperture of a gridline vertical places AT it (end to end)."""
    ms, sec, gl, v = _view(section_scene_for)
    vx = next(it for it in sec.items() if isinstance(it, ElevGridlineItem))
    hx = vx.mapToScene(vx.line().p1()).x()
    tol = sec._snap_tol_scene(v)
    sec.begin_place_block(defn(ms).id)
    pt = v.mapFromScene(QPointF(hx + tol * 0.5, -1500.0))
    QTest.mouseMove(v.viewport(), pt)
    QTest.mouseClick(v.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, pt)
    (inst,) = ms.hosted_blocks_on(gl)
    assert inst.host["along_mm"] == pytest.approx(hx, abs=1e-6)
    v.close()


def test_blocks_browser_activation_routes_to_the_section_tab(qapp):
    """Library activation (Blocks browser -> _on_block_activated) on a Section
    tab arms the section's placement, not the plan scene's (G16)."""
    from tests.test_section_manager import _main_window
    from tests._mainwindow_helpers import dispose_main_window
    from firepro3d.elevation_view import SectionView
    win = _main_window()
    try:
        ms = win.scene
        d = defn(ms)
        win._activate_elevation("north")
        QApplication.processEvents()
        cur = win.central_tabs.currentWidget()
        assert isinstance(cur, SectionView)
        win._on_block_activated(d.id)
        assert cur.scene()._place_block_id == d.id
        assert ms.mode != "place_block"
        cur.scene().cancel_place_block()
        win.central_tabs.setCurrentIndex(0)
        QApplication.processEvents()
        win._on_block_activated(d.id)           # a non-section tab keeps the plan path
        assert ms.mode == "place_block"
        assert cur.scene()._place_block_id is None
    finally:
        dispose_main_window(win)
