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
from tests._sb6_helpers import add_wall


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
    sc._annot_memo.clear()   # the module-scoped window memoised "no System tier" before the fixture swapped it in
    w = add_wall(sc)
    sc.push_undo_state()
    try:
        tb.click()
        assert tb.isChecked() and sc.tag_leader_on is True
        on = sc._tag_ctl.place_at(w, QPointF(800.0, 0.0))
        assert on.tag["leader"] == {"knee": None}
        tb.click()
        assert sc.tag_leader_on is False
        off = sc._tag_ctl.place_at(w, QPointF(-800.0, 0.0))
        assert off.tag["leader"] is None
    finally:
        sc.delete_items([w])                  # the cascade takes both tags (SB5 D6)
