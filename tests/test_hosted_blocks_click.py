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
    ghosts = [i for i in sec.items() if getattr(i, "_is_ghost", False)]
    assert len(ghosts) == 1                     # exactly one ghost, never doubled
    assert not any(c is ghosts[0] for c in sec._hosted_copies.values())
    # the re-armed ghost sits at the click's snapped point, not the origin
    assert ghosts[0].block_pos() == pytest.approx(
        (inst.host["along_mm"], -inst.host["elevation_mm"]), abs=1.0)
    v.close()


def test_shift_space_rotates_plus_90(qapp, section_scene_for):
    ms, sec, gl, v = _view(section_scene_for)
    sec.begin_place_block(defn(ms).id)
    QTest.keyClick(v.viewport(), Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)
    assert sec._place_rot == pytest.approx(90.0)
    v.close()


def test_leaving_the_section_tab_cancels_placement(qapp):
    from tests.test_section_manager import _main_window
    from tests._mainwindow_helpers import dispose_main_window
    win = _main_window()
    try:
        d = defn(win.scene)
        win._activate_elevation("north")
        QApplication.processEvents()
        sec = win.central_tabs.currentWidget().scene()
        win._on_block_activated(d.id)
        assert sec._place_block_id == d.id
        win.central_tabs.setCurrentIndex(0)
        QApplication.processEvents()
        assert sec._place_block_id is None
        assert not any(getattr(i, "_is_ghost", False) for i in sec.items())
    finally:
        dispose_main_window(win)


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


def _armed_section_window():
    """Real MainWindow, shown, on a section tab with a block armed."""
    from tests.test_section_manager import _main_window
    win = _main_window()
    win.show()
    QTest.qWaitForWindowExposed(win)
    d = defn(win.scene)
    win._activate_elevation("north")
    QApplication.processEvents()
    sec = win.central_tabs.currentWidget().scene()
    return win, d, sec


def test_esc_on_a_section_tab_cancels_armed_placement(qapp):
    """S3: the window-level Esc shortcut ends section placement (smoke S3)."""
    from tests._mainwindow_helpers import dispose_main_window
    win, d, sec = _armed_section_window()
    try:
        win._on_block_activated(d.id)
        assert sec._place_block_id == d.id
        plan_mode = win.scene.mode
        QTest.keyClick(win.windowHandle(), Qt.Key.Key_Escape)
        QApplication.processEvents()
        assert sec._place_block_id is None
        assert not any(getattr(i, "_is_ghost", False) for i in sec.items())
        assert win.scene.mode == plan_mode
    finally:
        dispose_main_window(win)


def test_section_placement_shows_the_place_block_badge(qapp):
    """S2: arming shows PLACE BLOCK in the footer; Esc returns to SELECT."""
    from tests._mainwindow_helpers import dispose_main_window
    win, d, sec = _armed_section_window()
    try:
        win._on_block_activated(d.id)
        assert win.footer.mode_badge.text() == "PLACE BLOCK"
        assert "rotate" in win.footer.instruction.text()
        QTest.keyClick(win.windowHandle(), Qt.Key.Key_Escape)
        QApplication.processEvents()
        assert win.footer.mode_badge.text() == "SELECT"
    finally:
        dispose_main_window(win)


def test_section_placement_clears_the_properties_panel(qapp):
    """S1: arming section placement clears the panel like the plan arm does."""
    from tests._mainwindow_helpers import dispose_main_window
    win, d, sec = _armed_section_window()
    try:
        gl = gridline(win.scene, (0, 0), (0, 1000), "G1")
        win.prop_manager.show_properties(gl)
        assert win.prop_manager._targets == [gl]
        win._on_block_activated(d.id)
        assert win.prop_manager._targets == []
    finally:
        dispose_main_window(win)


def _flip_window():
    """Armed section window plus a gridline the north elevation can host on."""
    win, d, sec = _armed_section_window()
    gl = None
    for y in (-500.0, 500.0, -3000.0, 3000.0, 0.0):
        g = gridline(win.scene, (-2000, y), (2000, y), "H%d" % int(y))
        sec.rebuild()
        if sec.can_host_at(QPointF(0.0, -1500.0)):
            gl = g
            break
        win.scene._gridlines.remove(g)
        win.scene.removeItem(g)
    assert gl is not None, "no host gridline for the north elevation"
    win._on_block_activated(d.id)
    view = win.central_tabs.currentWidget()
    view.setFocus()
    QApplication.processEvents()
    return win, d, sec, gl, view


def _place_flipped(keys):
    from tests._mainwindow_helpers import dispose_main_window
    win, d, sec, gl, view = _flip_window()
    try:
        for k in keys:
            QTest.keyClick(win.windowHandle(), k)
            QApplication.processEvents()
        ghost = sec._place_ghost
        ghost_pose = (ghost.block_rotation(), ghost.block_mirrored())
        inst = sec.click_place_block(QPointF(0.0, -1500.0))
        assert inst is not None
        (cp,) = sec._hosted_copies.values()
        return ((inst.block_rotation(), inst.block_mirrored()), ghost_pose,
                (cp.block_rotation(), cp.block_mirrored()))
    finally:
        dispose_main_window(win)


def test_left_arrow_mirrors_ghost_and_placed_block(qapp):
    """G16 parity: <- mirrors left-right live; the placed block keeps the pose and
    its section copy renders mirrored in that same view."""
    from firepro3d.block_pose import reflect_pose
    want = reflect_pose(0.0, False, 90.0)
    placed, ghost, copy = _place_flipped([Qt.Key.Key_Left])
    assert want[1] is True
    assert ghost == pytest.approx(want) and placed == pytest.approx(want)
    assert copy[1] is True and copy[0] == pytest.approx(want[0])


def test_up_arrow_flips_top_bottom(qapp):
    from firepro3d.block_pose import reflect_pose
    want = reflect_pose(0.0, False, 0.0)
    placed, ghost, copy = _place_flipped([Qt.Key.Key_Up])
    assert ghost == pytest.approx(want) and placed == pytest.approx(want)
    assert copy[1] is True and copy[0] == pytest.approx(want[0])


def test_two_left_arrows_cancel(qapp):
    placed, ghost, copy = _place_flipped([Qt.Key.Key_Left, Qt.Key.Key_Right])
    assert placed == pytest.approx((0.0, False)) and ghost == pytest.approx((0.0, False))
    assert copy[1] is False


def test_flip_after_space_uses_screen_axis(qapp):
    from firepro3d.block_pose import reflect_pose
    want = reflect_pose(-90.0, False, 90.0)
    placed, _g, _c = _place_flipped([Qt.Key.Key_Space, Qt.Key.Key_Left])
    assert placed == pytest.approx(want)


def test_section_place_block_hint_mentions_flip(qapp):
    win, d, sec = _armed_section_window()
    from tests._mainwindow_helpers import dispose_main_window
    try:
        win._on_block_activated(d.id)
        assert "flip" in win.footer.instruction.text()
    finally:
        dispose_main_window(win)
