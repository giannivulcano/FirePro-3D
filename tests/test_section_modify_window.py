"""Elevation parity area C through the real window: section modify tools,
clipboard and undo (AC1 scene side, AC2, AC3, AC4, AC11).

Shown MainWindow (``test_section_routing.section_win`` ->
``test_hosted_blocks_edit._window_with_hosted_block``): placed section
(0,0)-(10000,0) current, hosted block placed at section (2500, -1200) on the
default gridline A (plan y = 0). Keys go through the window's wired
QShortcuts; mouse events are posted to the section view's viewport.
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.constants import (HOSTED_PASTE_IN_PLAN, SECTION_EDIT_SKIPPED,
                                 SECTION_PASTE_NO_HOST)
from tests._modify_tools_helpers import ignore_os_mouse
from tests._snap_polish_helpers import click, move
from tests.test_section_routing import (  # noqa: F401 -- section_win is a fixture
    parallel_pipe, plan_index, press, proxies_of, rebuild, section_win)

PLACED_ALONG, PLACED_ELEV = 2500.0, 1200.0   # _window_with_hosted_block's QPointF(2500, -1200)


def _aim(view, sec):
    """*view* deaf to the OS mouse at 1 px = 10 mm on the block (posted
    multiples of 10 mm round-trip exactly), its scene's snap off."""
    ignore_os_mouse(view)
    view.resetTransform()
    view.scale(0.1, 0.1)
    view.centerOn(2500.0, -1200.0)
    sec.toggle_snap(False)
    QApplication.processEvents()
    return view


def _ready(win, sec, inst):
    """The current section view aimed (``_aim``), the debounced placement
    rebuild done and the block's copy the selection."""
    view = _aim(win.central_tabs.currentWidget(), sec)
    rebuild(sec)
    sec.select_items([sec._hosted_copies[id(inst)]])
    QApplication.processEvents()
    return view


def _host(ms, inst):
    return ms.gridline_by_uid(inst.host["gridline"])


def _hosted(ms, gl_):
    return ms.hosted_blocks_on(ms.gridline_by_uid(gl_._uid))


def _open(win, a, b):
    """Place + open a section tab and make it current."""
    m = win.section_manager.place_section(QPointF(*a), QPointF(*b))
    view = win.section_manager.open_section(m.name)
    win.central_tabs.setCurrentWidget(view)
    QApplication.processEvents()
    return view, view.scene()


def _status(win):
    return win.statusBar().currentMessage()


def test_shift_r_rotates_the_model_block_in_one_undo_step(section_win):
    """AC1 scene side / AC3 / AC11: Shift+R on the section tab, three clicks
    (pivot 500 mm left, start ray heading 0, end ray heading 90): the MODEL
    block turns 90 deg and its host point swings to along 2000 / elevation
    1700, one undo step; a parallel section re-projects it after a forced
    rebuild; Ctrl+Z restores both.
    RED when: ``self._write_back(old)`` is deleted from
    ``_HostedBlockCopy.manip_rotate``."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = _ready(win, sec, inst)
    host_gl = _host(ms, inst)
    behind = win.section_manager.get_or_build_scene(
        win.section_manager.place_section(QPointF(0.0, 1000.0),
                                          QPointF(10000.0, 1000.0)).name)
    pos0 = ms._undo_pos
    press(win, "Shift+R")
    assert sec.mode == "rotate"
    click(view, QPointF(2000.0, -1200.0))
    click(view, QPointF(3000.0, -1200.0))
    move(view, QPointF(2000.0, -2200.0))
    click(view, QPointF(2000.0, -2200.0))
    assert inst.block_rotation() == pytest.approx(90.0)
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG - 500.0)
    assert inst.host["elevation_mm"] == pytest.approx(PLACED_ELEV + 500.0)
    assert ms._undo_pos == pos0 + 1
    rebuild(sec)
    rebuild(behind)
    for s in (sec, behind):
        cp = s._hosted_copies[id(inst)]
        assert cp.block_rotation() == pytest.approx(90.0)
        assert cp.block_pos() == pytest.approx((2000.0, -1700.0))
    press(win, "Ctrl+Z")
    assert ms._undo_pos == pos0
    (back,) = _hosted(ms, host_gl)
    assert back.block_rotation() == pytest.approx(0.0)
    assert back.host["along_mm"] == pytest.approx(PLACED_ALONG)


def test_mixed_selection_skips_and_read_only_refuses_on_the_footer(section_win):
    """AC2 / R3: copy + pipe proxy selected, Shift+M acts on the copy only and
    the footer says "1 items skipped (edit in plan)"; the proxy alone ->
    Shift+M refuses with the same footer text and no mode; the plan never
    enters Move.
    RED when: ``modify_selection`` returns ``list(self.selectedItems())``
    (the proxy is captured; no skip text)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    _ready(win, sec, inst)
    pipe = parallel_pipe(ms, sec)
    (line,) = proxies_of(sec, pipe)
    cp = sec._hosted_copies[id(inst)]
    plan_mode0 = ms.mode
    sec.select_items([cp, line])
    press(win, "Shift+M")
    assert sec.mode == "move"
    assert sec._selected_items == [cp]
    assert _status(win) == SECTION_EDIT_SKIPPED.format(n=1)
    press(win, "Escape")
    sec.select_items([line])
    press(win, "Shift+M")
    assert sec.mode in (None, "select")
    assert _status(win) == SECTION_EDIT_SKIPPED.format(n=1)
    assert ms.mode == plan_mode0


def test_ctrl_c_v_into_a_parallel_section_and_the_refusals(section_win):
    """AC4 / R4 / R5 / AC11: Ctrl+C (base at the insertion point) in the
    section, Ctrl+V + a click at (4000, -500) in a parallel section: a new
    model block on the SAME host gridline at along 4000 / elevation 500, one
    undo step, shown in the first section after a rebuild. Ctrl+V in a
    section that does not show the host gridline refuses (R4); on the plan
    tab it refuses too (R5); neither places anything.
    RED when: the ``paste_refusal`` check is deleted from
    ``ModifyToolsController.begin_paste`` (the plan / cross Paste arms)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = _ready(win, sec, inst)
    host_gl = _host(ms, inst)
    press(win, "Ctrl+C")
    assert sec.mode == "copy_base"
    click(view, QPointF(2500.0, -1200.0))
    v2, sec2 = _open(win, (0.0, 1000.0), (10000.0, 1000.0))   # 1000 mm behind, same side
    _aim(v2, sec2)
    pos0 = ms._undo_pos
    press(win, "Ctrl+V")
    assert sec2.mode == "paste"
    click(v2, QPointF(4000.0, -500.0))
    (new,) = [b for b in _hosted(ms, host_gl) if b is not inst]
    assert new.host["along_mm"] == pytest.approx(4000.0)
    assert new.host["elevation_mm"] == pytest.approx(500.0)
    assert ms._undo_pos == pos0 + 1
    rebuild(sec)
    assert id(new) in sec._hosted_copies
    n_blocks = len(ms._block_instances)

    v3, sec3 = _open(win, (3000.0, 2000.0), (3000.0, -8000.0))
    press(win, "Ctrl+V")
    assert sec3.mode in (None, "select")
    assert _status(win) == SECTION_PASTE_NO_HOST

    win.central_tabs.setCurrentIndex(plan_index(win))
    QApplication.processEvents()
    press(win, "Ctrl+V")
    assert ms.mode != "paste"
    assert _status(win) == HOSTED_PASTE_IN_PLAN
    assert len(ms._block_instances) == n_blocks
    assert ms._undo_pos == pos0 + 1


# -- C-9c: typed input on a section tab --------------------------------------
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest


def _engage(view, sec, key):
    """A real digit / Tab on the section view; returns the engaged HUD."""
    QTest.keyClick(view, key)
    hud = sec.dynamic_input
    assert hud is not None and hud.is_engaged()
    return hud


def test_typed_move_distance(section_win):
    """AC3 / AC11 with C-9: Shift+M, base click, "500 mm" / "300 mm" typed
    (dX / dY, Y-up): the MODEL block moves to along 3000 / elevation 1500;
    one undo step; the HUD closes.
    RED when: ``self._plc = PlacementInputCoordinator(self)`` is deleted from
    ``SectionScene.__init__`` (no HUD on the digit)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = _ready(win, sec, inst)
    pos0 = ms._undo_pos
    press(win, "Shift+M")
    click(view, QPointF(2500.0, -1200.0))
    hud = _engage(view, sec, Qt.Key.Key_5)
    QTest.keyClicks(hud.editor("dX"), "00 mm")
    QTest.keyClick(hud.editor("dX"), Qt.Key.Key_Tab)
    QTest.keyClicks(hud.editor("dY"), "300 mm")
    QTest.keyClick(hud.editor("dY"), Qt.Key.Key_Return)
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG + 500.0)
    assert inst.host["elevation_mm"] == pytest.approx(PLACED_ELEV + 300.0)
    assert ms._undo_pos == pos0 + 1
    assert sec.dynamic_input is None and sec.mode in (None, "select")


def test_typed_rotate_angle(section_win):
    """AC3 / AC11 with C-9: Shift+R, pivot 500 mm left, "90" typed: the MODEL
    block turns 90 deg and swings to along 2000 / elevation 1700; one step.
    RED when: ``return self._modify_hud_key(event)`` in
    ``ModifyHostMixin.modify_key_press`` becomes ``return False`` (the digit
    never engages)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = _ready(win, sec, inst)
    pos0 = ms._undo_pos
    press(win, "Shift+R")
    click(view, QPointF(2000.0, -1200.0))                 # pivot
    hud = _engage(view, sec, Qt.Key.Key_9)
    QTest.keyClicks(hud.editor("Angle"), "0")
    QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Return)
    assert inst.block_rotation() == pytest.approx(90.0)
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG - 500.0)
    assert inst.host["elevation_mm"] == pytest.approx(PLACED_ELEV + 500.0)
    assert ms._undo_pos == pos0 + 1


def test_typed_scale_factor_after_the_right_arrow(section_win):
    """AC3 / AC11 with C-9: Shift+S, base 500 mm left, reference at the
    insertion point, Right (Length -> Factor), "3" typed: the MODEL block's
    scale is 3 and its host point moves to along 2000 + 3 * 500 = 3500.
    RED when: the <-/-> branch is deleted from ``_modify_hud_key`` (the
    variant stays Length; no Factor field)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = _ready(win, sec, inst)
    pos0 = ms._undo_pos
    press(win, "Shift+S")
    click(view, QPointF(2000.0, -1200.0))                 # base
    click(view, QPointF(2500.0, -1200.0))                 # reference = 1x (500 mm)
    QTest.keyClick(view, Qt.Key.Key_Right)
    assert sec._scale_variant == "factor"
    hud = _engage(view, sec, Qt.Key.Key_3)
    QTest.keyClick(hud.editor("Factor"), Qt.Key.Key_Return)
    assert inst.block_scale() == pytest.approx(3.0)
    assert inst.host["along_mm"] == pytest.approx(3500.0)
    assert ms._undo_pos == pos0 + 1


def test_typed_linear_array_count_and_spacing(section_win):
    """AC3 in full / AC11: Shift+A, base at the insertion point, aim up,
    Tab, then Angle 90 / Spacing "1000 mm" / Count 4 (the TOTAL): three new
    model blocks on the host gridline at elevations 2200 / 3200 / 4200;
    one undo step.
    RED when: the Tab branch is deleted from ``SectionView.keyPressEvent``
    (Tab engages nothing)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = _ready(win, sec, inst)
    host_gl = _host(ms, inst)
    pos0 = ms._undo_pos
    press(win, "Shift+A")
    assert sec._array_variant == "linear"
    click(view, QPointF(2500.0, -1200.0))                 # base
    move(view, QPointF(2500.0, -2200.0))                  # aim: straight up
    hud = _engage(view, sec, Qt.Key.Key_Tab)
    QTest.keyClicks(hud.editor("Angle"), "90")
    QTest.keyClick(hud.editor("Angle"), Qt.Key.Key_Tab)
    QTest.keyClicks(hud.editor("Spacing"), "1000 mm")
    QTest.keyClick(hud.editor("Spacing"), Qt.Key.Key_Tab)
    QTest.keyClicks(hud.editor("Count"), "4")
    QTest.keyClick(hud.editor("Count"), Qt.Key.Key_Return)
    got = sorted((round(b.host["along_mm"], 3), round(b.host["elevation_mm"], 3))
                 for b in _hosted(ms, host_gl) if b is not inst)
    assert got == [(PLACED_ALONG, PLACED_ELEV + k * 1000.0) for k in (1, 2, 3)]
    assert ms._undo_pos == pos0 + 1


def test_left_arrow_polar_array(section_win):
    """AC3 in full: Shift+A, Left (Linear -> Polar, the variant list wraps),
    centre 500 mm left of the insertion point, Tab, Count 4 / Total 360: three
    rotated model blocks at 90 / 180 / 270 deg about the centre -- (along,
    elevation, rotation) = (2000, 1700, 90), (1500, 1200, 180),
    (2000, 700, 270); one undo step.
    RED when: ``self._write_back(old)`` is deleted from
    ``_HostedBlockCopy.manip_rotate`` (the three pasted copies keep the
    original's pose: all at along 2500, rotation 0)."""
    win, ms, sec, gl, plan_gl, inst = section_win
    view = _ready(win, sec, inst)
    host_gl = _host(ms, inst)
    pos0 = ms._undo_pos
    press(win, "Shift+A")
    QTest.keyClick(view, Qt.Key.Key_Left)
    assert sec._array_variant == "polar"
    click(view, QPointF(2000.0, -1200.0))                 # centre
    hud = _engage(view, sec, Qt.Key.Key_Tab)
    QTest.keyClicks(hud.editor("Count"), "4")
    QTest.keyClick(hud.editor("Count"), Qt.Key.Key_Tab)
    QTest.keyClicks(hud.editor("Total"), "360")
    QTest.keyClick(hud.editor("Total"), Qt.Key.Key_Return)
    got = sorted((round(b.host["along_mm"], 3), round(b.host["elevation_mm"], 3),
                  round(b.block_rotation() % 360.0, 3))
                 for b in _hosted(ms, host_gl) if b is not inst)
    assert got == sorted([(2000.0, 1700.0, 90.0), (1500.0, 1200.0, 180.0),
                          (2000.0, 700.0, 270.0)])
    assert ms._undo_pos == pos0 + 1


def test_hud_is_seeded_from_the_live_cursor(section_win):
    """OPEN-5 (integrator; R-C9a-01): Shift+M, base click, a button-less move
    300 mm right and 300 mm up, then Tab: the HUD opens seeded with the live
    displacement, not zeros -- the Move tool's ``publish_placement_state``
    (modify_tools_controller.py:779) reaches the section's coordinator
    through T52's mixin shell.
    RED when: a no-op ``publish_placement_state`` is defined on SectionScene
    (T37's dropped override): the resolved point stays None, dX / dY seed 0."""
    from firepro3d.scale_manager import ScaleManager
    win, ms, sec, gl, plan_gl, inst = section_win
    view = _ready(win, sec, inst)
    sec.toggle_snap(False)                                # exact cursor points (setup, T18)
    press(win, "Shift+M")
    click(view, QPointF(2500.0, -1200.0))                 # base (the placement, C-8 probe)
    move(view, QPointF(2800.0, -1500.0))                  # +300 h, 300 up (Y-up)
    got = sec.get_resolved_point()
    assert got is not None and (got.x(), got.y()) == pytest.approx((2800.0, -1500.0))
    hud = _engage(view, sec, Qt.Key.Key_Tab)
    dx = ScaleManager.parse_dimension(hud.editor("dX").text())
    dy = ScaleManager.parse_dimension(hud.editor("dY").text())
    assert (dx, dy) == pytest.approx((300.0, 300.0), abs=2.0)   # 2 mm: a 1/16" display round
