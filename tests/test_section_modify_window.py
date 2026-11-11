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
