"""SB6 D8 / R5 -- Architecture > Annotations: a Tag mode button (live on plan and
detail, off on a section, D14) and a checkable Leader toggle, off by default, that
decides whether new tags get a leader."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest

import main as _main_module
from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
_main_module.View3D = View3D
from firepro3d import snap_engine
from main import MainWindow
from tests._mainwindow_helpers import dispose_main_window
from tests._sb6_helpers import LEADER, add_wall


@pytest.fixture(scope="module")
def main_window(qapp):
    saved = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    dispose_main_window(win)
    snap_engine.SNAP_TOLERANCE_PX = saved


def test_tag_button_enters_tag_mode_on_plan_and_is_off_on_a_section(main_window):
    btn = main_window._mode_buttons["tag"]
    main_window._set_canvas_context("plan")
    assert btn.isEnabled()
    btn.click()
    assert main_window.scene.mode == "tag" and btn.isChecked()
    main_window.scene.set_mode(None)
    main_window._set_canvas_context("section")
    assert not btn.isEnabled()
    main_window._set_canvas_context("plan")


def test_leader_toggle_is_off_by_default_and_drives_new_tags(main_window, real_system_library):
    tb = main_window._tag_leader_btn
    sc = main_window.scene
    assert tb.isCheckable() and not tb.isChecked() and sc.tag_leader_on is False
    # Test isolation only: the module-scoped window memoised the annotation-block lookup (to "no System tier")
    # before this fixture swapped the real System tier in; clear it so the lookup runs again.
    sc._annot_memo.clear()
    w = add_wall(sc)
    sc.push_undo_state()
    try:
        tb.click()
        assert tb.isChecked() and sc.tag_leader_on is True
        on = sc._tag_ctl.place_at(w, QPointF(800.0, 0.0))
        assert on.tag["leader"] == LEADER
        tb.click()
        assert sc.tag_leader_on is False
        off = sc._tag_ctl.place_at(w, QPointF(-800.0, 0.0))
        assert off.tag["leader"] is None
    finally:
        sc.delete_items([w])                  # the cascade takes both tags (SB5 D6)


def test_leader_button_then_tag_click_on_a_wall_places_a_leader_tag(main_window, real_system_library):
    """GC1: the real Leader button, the real Tag button, a posted mouse click on a wall in the
    shown view -> the placed tag carries a leader record (the whole ribbon -> tool chain)."""
    from PyQt6.QtCore import QPointF
    from tests._modify_tools_helpers import ignore_os_mouse
    from tests._sb6_helpers import tags_of
    from tests._snap_polish_helpers import click, move
    main_window._set_canvas_context("plan")
    sc, view = main_window.scene, main_window.view
    sc._annot_memo.clear()                    # test isolation: see the Leader toggle test above
    ignore_os_mouse(view)
    w = add_wall(sc)
    sc.push_undo_state()
    tb = main_window._tag_leader_btn
    try:
        assert not tb.isChecked()
        tb.click()                            # Leader on
        assert tb.isChecked()
        main_window._mode_buttons["tag"].click()
        assert sc.mode == "tag"
        view.resetTransform()
        view.scale(0.1, 0.1)
        view.centerOn(0, 0)
        QTest.qWait(30)
        pt = QPointF(800.0, 0.0)              # on the wall's 200 mm band
        move(view, pt)
        click(view, pt)
        (tag,) = [t for t in tags_of(sc) if t._host_uid == w._uid]
        assert tag.tag["leader"] == LEADER
    finally:
        if tb.isChecked():
            tb.click()
        sc.set_mode(None)
        sc.delete_items([w])
