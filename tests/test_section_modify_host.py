"""Elevation parity area C: the section is a modify host (design D2).

Hosted-block copies in a section are write-back copies of plan-store model
blocks; the section's modify tools change the MODEL block (pose + host
record). Fixture: ``test_hosted_blocks_edit._setup`` -- placed section
(0,0)-(10000,0), depth 8000; gridline B (0,-3000)-(6000,-3000); block "A"
placed at section (2500, -1200) -> host along 2500, elevation 1200.
"""
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d import hosted_blocks as hb
from firepro3d.section_marker import SectionMarker
from tests._modify_tools_helpers import ignore_os_mouse
from tests._snap_polish_helpers import click, move
from tests.test_hosted_blocks_edit import _setup

PLACED_ALONG, PLACED_ELEV = 2500.0, 1200.0        # _setup's QPointF(2500, -1200)


def _section(ms, a, b, look, depth=8000.0, name="S2"):
    """Another section over the same model, rebuilt once."""
    from firepro3d.section_scene import SectionScene
    m = SectionMarker(name, QPointF(*a), QPointF(*b), look, depth)
    s = SectionScene(m, ms, ms._level_manager, ms.scale_manager)
    s.rebuild()
    return s


def _same_side(ms):
    """Parallel section, same side as _setup's (gridline B 2000 mm deep)."""
    return _section(ms, (0, -1000), (10000, -1000), 1, name="Same")


def _far_side(ms):
    """Parallel section looking from gridline B's other side (3000 mm deep)."""
    return _section(ms, (0, -6000), (10000, -6000), -1, name="Far")


def _pose(cp):
    return (round(cp.block_pos()[0], 3), round(cp.block_pos()[1], 3),
            round(cp.block_rotation(), 3), cp.block_mirrored(),
            round(cp.block_scale(), 6))


def _inverse(sec, cp, src, old_xy):
    """The candidate write-back (probe only): inverse of section_pose."""
    gl = sec._ms.gridline_by_uid(src.host["gridline"])
    back = hb.facing_of(sec._basis, gl) != int(src.host.get("facing", 1))
    x, y = cp.block_pos()
    src.host["along_mm"] = (float(src.host["along_mm"])
                            + (x - old_xy[0]) * hb.h_sign(sec._basis, gl))
    src.host["elevation_mm"] = -y
    rot = cp.block_rotation()
    src.set_block_rotation(-rot if back else rot)
    src.set_block_mirrored(cp.block_mirrored() != back)
    src.set_block_scale(cp.block_scale() * sec._ppm())
    sec._ms._sync_hosted_blocks(gl)


def test_probe_hosted_pose_is_the_in_plane_pose(qapp, section_scene_for):
    """D2 step-1 probe: the model block's pose IS its pose in the host
    gridline's plane (front: as is; far side: rotation negated, mirror
    toggled -- hosted-blocks D4), and the inverse of that projection is
    exact for a rotate about an off-origin pivot, a mirror (front and far
    side) and a scale. So rotate / mirror / scale in a section are
    expressible in ``_pose_rot`` / ``_pose_mirrored`` / ``_pose_scale``.
    RED when: ``hosted_blocks.section_pose`` stops negating the far-side
    rotation (``-rotation if back else rotation`` -> ``rotation``)."""
    ms, sec, gl, inst = _setup(section_scene_for)
    same, far = _same_side(ms), _far_side(ms)
    inst.set_block_rotation(30.0)
    for s in (sec, same, far):
        s.rebuild()
    f, p, b = (s._hosted_copies[id(inst)] for s in (sec, same, far))
    assert (f.block_rotation(), f.block_mirrored()) == (30.0, False)
    assert (p.block_rotation(), p.block_mirrored()) == (30.0, False)
    assert (b.block_rotation(), b.block_mirrored()) == (-30.0, True)

    old = f.block_pos()                       # rotate 90 about 500 mm left
    f.manip_rotate(90.0, QPointF(old[0] - 500.0, old[1]))
    want = _pose(f)
    assert want[:3] == (2000.0, -1700.0, 120.0)      # 30 + 90; (500,0) turned up
    _inverse(sec, f, inst, old)
    for s in (sec, same, far):
        s.rebuild()
    f, p, b = (s._hosted_copies[id(inst)] for s in (sec, same, far))
    assert _pose(f) == want and _pose(p) == want
    assert b.block_rotation() == pytest.approx(-120.0) and b.block_mirrored()

    old = b.block_pos()                       # mirror in the FAR section
    b.manip_reflect(QPointF(old[0] + 100.0, 0.0), QPointF(old[0] + 100.0, -1000.0))
    want_far = _pose(b)
    _inverse(far, b, inst, old)
    for s in (sec, far):
        s.rebuild()
    assert _pose(far._hosted_copies[id(inst)]) == want_far

    f = sec._hosted_copies[id(inst)]           # scale x2 about an off-origin base
    old = f.block_pos()
    f.manip_scale_about(QPointF(old[0] - 100.0, old[1] + 100.0), 2.0)
    want = _pose(f)
    _inverse(sec, f, inst, old)
    sec.rebuild()
    assert _pose(sec._hosted_copies[id(inst)]) == want
    assert inst.block_scale() == pytest.approx(2.0)


# -- C-2: the section is a modify host ---------------------------------------
from tests.test_modify_host_seam import _differing_pixels


def _show(sec):
    """A real SectionView on *sec*, deaf to the OS mouse, 1 px = 10 mm,
    centred on the hosted block."""
    from firepro3d.elevation_view import SectionView
    view = ignore_os_mouse(SectionView(sec))
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.scale(0.1, 0.1)
    view.centerOn(2500.0, -1200.0)
    QApplication.processEvents()
    return view


@pytest.fixture
def host(qapp, section_scene_for, monkeypatch):
    """``(ms, sec, gl, inst, view, statuses)``: _setup's hosted block shown in
    a real SectionView, its copy the only selection, snap OFF (clicks land
    exactly where posted), footer statuses recorded. The tuple holds the
    Model_Space for the test's life.

    QGraphicsView maps a mouse event through an INTEGER viewport point; at
    1 px = 10 mm with an integral scroll offset, every scene point the tests
    post (multiples of 10 mm) round-trips exactly."""
    ms, sec, gl, inst = _setup(section_scene_for)
    view = _show(sec)
    sec.toggle_snap(False)                       # area D-5
    sec._rebuild_timer.stop()
    sec.rebuild()
    sec.select_items([sec._hosted_copies[id(inst)]])
    statuses = []
    monkeypatch.setattr(sec, "_show_status",
                        lambda m, timeout=5000: statuses.append(m))
    yield ms, sec, gl, inst, view, statuses
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def _pipe_proxy(ms, sec):
    """A pipe parallel to the cut -> one read-only selectable proxy."""
    from firepro3d.section_scene import _ROLE_SOURCE
    pipe = ms.add_pipe(ms.add_node(1000, -1500), ms.add_node(8000, -1500))
    sec.rebuild()
    (line,) = [it for it in sec.items() if it.data(_ROLE_SOURCE) is pipe
               and it.flags() & it.GraphicsItemFlag.ItemIsSelectable]
    return line


@pytest.mark.parametrize("tool, ok", [
    ("move", True), ("rotate", True), ("flip", True), ("mirror", True),
    ("scale", True), ("copy", True), ("cut", True), ("duplicate", True),
    ("offset", False), ("fillet", False)])
def test_section_offers_the_section_tools_only(host, tool, ok):
    """D2 / AC1 scene side: the section hosts the select-first section tools
    for a hosted copy; Offset / Fillet (plan 2D-geometry tools) never, not
    even with nothing selected (A-8's EDIT_ON["section"]).
    RED when: ``SectionScene`` drops ``ModifyHostMixin`` from its bases
    (no ``_modify_ctl``: AttributeError)."""
    ms, sec, gl, inst, view, statuses = host
    cp = sec._hosted_copies[id(inst)]
    assert sec._modify_ctl.can_start(tool, [cp]) is ok
    if not ok:
        assert sec._modify_ctl.can_start(tool, []) is False


def test_read_only_selection_refuses_with_the_skip_message(host):
    """R3 / AC2: only a projected model proxy selected -> the tool refuses,
    no mode, footer "1 items skipped (edit in plan)".
    RED when: ``modify_selection`` returns ``list(self.selectedItems())``."""
    from firepro3d.constants import SECTION_EDIT_SKIPPED
    ms, sec, gl, inst, view, statuses = host
    line = _pipe_proxy(ms, sec)
    sec.select_items([line])
    assert sec._modify_ctl.start("move") is False
    assert sec.mode in (None, "select")
    assert statuses[-1] == SECTION_EDIT_SKIPPED.format(n=1)


def test_mixed_selection_acts_on_the_copy_and_reports_the_skip(host):
    """R3 / AC2: copy + proxy selected -> Move captures the copy only and
    the footer reports the one skipped proxy.
    RED when: the ``self._show_status(...)`` line in
    ``SectionScene._capture_modify_selection`` is deleted."""
    from firepro3d.constants import SECTION_EDIT_SKIPPED
    ms, sec, gl, inst, view, statuses = host
    line = _pipe_proxy(ms, sec)
    cp = sec._hosted_copies[id(inst)]
    sec.select_items([cp, line])
    assert sec._modify_ctl.start("move") is True
    assert sec._selected_items == [cp]
    assert SECTION_EDIT_SKIPPED.format(n=1) in statuses


def test_move_tool_end_to_end_on_a_section_view(host, qapp):
    """AC3 / AC11: base click, a button-less move (the ghost follows), the
    destination click -> the MODEL block's host moves by the picked vector,
    one undo step (the deferred drag flush adds none), back to Select.
    RED when: the ``if self.modify_mouse_press(event):`` lines are deleted
    from ``SectionScene.mousePressEvent`` (nothing moves). (The plan also
    named the ``__init__`` ``_create_manipulator()`` call; it is redundant --
    ``rebuild`` / ``select_items`` heal the manipulator through
    ``_live_manip`` -- so deleting it leaves this test green.)"""
    ms, sec, gl, inst, view, statuses = host
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("move") is True
    click(view, QPointF(2500.0, -1200.0))                 # base = insertion point
    move(view, QPointF(3000.0, -1700.0))
    assert sec._move_ghost                                # the ghost rides the cursor
    click(view, QPointF(3000.0, -1700.0))                 # +500 h, 500 up
    qapp.processEvents()
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG + 500.0)
    assert inst.host["elevation_mm"] == pytest.approx(PLACED_ELEV + 500.0)
    assert ms._undo_pos == pos0 + 1
    assert sec.mode in (None, "select")


def test_halo_hover_pauses_while_a_tool_runs(host):
    """Plan parity (Model_Space._halo_mode_ok): Select-mode hover picks the
    copy; with Move running the same hover picks nothing.
    RED when: ``SectionScene._halo_mode_ok`` is deleted (mixin default True)."""
    ms, sec, gl, inst, view, statuses = host
    cp = sec._hosted_copies[id(inst)]
    move(view, QPointF(2550.0, -1200.0))                  # on the block's line
    assert sec.halo_item() is cp                           # precondition: Select
    assert sec._modify_ctl.start("move") is True
    move(view, QPointF(2552.0, -1200.0))
    assert sec.halo_item() is None


def test_esc_reaches_the_running_tool_through_the_view(host):
    """The real Esc key on the SectionView ends the tool ("Mode cancelled"),
    not the select-mode escape ladder (which would only clear the selection).
    RED when: the modify-mode branch is deleted from
    ``SectionView.keyPressEvent``."""
    ms, sec, gl, inst, view, statuses = host
    assert sec._modify_ctl.start("move") is True
    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert sec.mode in (None, "select")
    assert statuses[-1] == "Mode cancelled"


def test_section_view_paints_the_move_ghost(host):
    """D2: the shared painter draws the Move ghost in the SectionView; Esc
    takes it away.
    RED when: the ``paint_modify_overlays(painter, self, scene)`` line is
    deleted from ``SectionView.drawForeground``."""
    ms, sec, gl, inst, view, statuses = host
    view.resetTransform()
    view.scale(0.5, 0.5)                                  # the 100 mm block = 50 px
    view.centerOn(2500.0, -1700.0)
    QApplication.processEvents()
    assert sec._modify_ctl.start("move") is True
    click(view, QPointF(2500.0, -1200.0))
    move(view, QPointF(2500.0, -2000.0))                  # ghost 800 mm up, clear of the copy
    region = view.mapFromScene(QRectF(2450.0, -2050.0, 200.0, 100.0)).boundingRect()
    with_ghost = view.viewport().grab(region).toImage()
    QTest.keyClick(view, Qt.Key.Key_Escape)
    QApplication.processEvents()
    without = view.viewport().grab(region).toImage()
    assert _differing_pixels(with_ghost, without) > 20


def test_a_debounced_rebuild_waits_for_the_running_tool(host, qapp):
    """A model edit's debounced rebuild fires while Move runs: the copy the
    tool holds survives, the commit lands on the model, and the held rebuild
    runs once the tool ends.
    RED when: the hold branch (``if ... in self._MODIFY_MODES: ...
    return``) is deleted from ``_rebuild_when_idle`` (the copy is replaced
    mid-tool: the identity assert fails)."""
    ms, sec, gl, inst, view, statuses = host
    cp = sec._hosted_copies[id(inst)]
    assert sec._modify_ctl.start("move") is True
    sec._schedule_rebuild()
    QTest.qWait(250)                                      # > the 100 ms debounce
    assert sec._hosted_copies[id(inst)] is cp and cp.scene() is sec
    click(view, QPointF(2500.0, -1200.0))
    click(view, QPointF(2800.0, -1200.0))
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG + 300.0)
    QTest.qWait(250)                                      # the held rebuild ran
    assert sec._hosted_copies[id(inst)] is not cp


def test_a_direct_rebuild_ends_the_running_tool(host):
    """A direct ``rebuild()`` (context-menu Refresh, a datum toggle) would
    delete the copies a tool holds: it ends the tool first.
    RED when: the ``self.set_mode(None)`` guard at the top of ``rebuild``
    is deleted (mode stays "move" over deleted copies)."""
    ms, sec, gl, inst, view, statuses = host
    assert sec._modify_ctl.start("move") is True
    sec.rebuild()
    assert sec.mode in (None, "select")
    assert not sec._selected_items


def test_one_snap_engine_call_per_move_in_a_tool(host, monkeypatch):
    """D-6 x C-2: while a modify tool runs, a mouse move resolves the cursor
    ONCE (the scene's dispatch), not again in the view.
    RED when: the ``getattr(sc, "mode", None) not in ... _MODIFY_MODES``
    clause is deleted from ``SectionView.mouseMoveEvent`` (2 calls)."""
    ms, sec, gl, inst, view, statuses = host
    assert sec._modify_ctl.start("move") is True
    click(view, QPointF(2500.0, -1200.0))
    calls = []
    real = sec.get_effective_position
    monkeypatch.setattr(sec, "get_effective_position",
                        lambda p: (calls.append(p), real(p))[1])
    move(view, QPointF(2700.0, -1300.0))
    assert len(calls) == 1
