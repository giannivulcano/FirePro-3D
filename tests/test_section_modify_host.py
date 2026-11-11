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
from firepro3d.block_instance import BlockInstance
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
    The transforms call ``BlockInstance``'s own ``manip_*`` (not the copy's
    override, which since C-3 writes back itself) so the probe's test-side
    inverse stays the only write.
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
    BlockInstance.manip_rotate(f, 90.0, QPointF(old[0] - 500.0, old[1]))
    want = _pose(f)
    assert want[:3] == (2000.0, -1700.0, 120.0)      # 30 + 90; (500,0) turned up
    _inverse(sec, f, inst, old)
    for s in (sec, same, far):
        s.rebuild()
    f, p, b = (s._hosted_copies[id(inst)] for s in (sec, same, far))
    assert _pose(f) == want and _pose(p) == want
    assert b.block_rotation() == pytest.approx(-120.0) and b.block_mirrored()

    old = b.block_pos()                       # mirror in the FAR section
    BlockInstance.manip_reflect(b, QPointF(old[0] + 100.0, 0.0),
                                QPointF(old[0] + 100.0, -1000.0))
    want_far = _pose(b)
    _inverse(far, b, inst, old)
    for s in (sec, far):
        s.rebuild()
    assert _pose(far._hosted_copies[id(inst)]) == want_far

    f = sec._hosted_copies[id(inst)]           # scale x2 about an off-origin base
    old = f.block_pos()
    BlockInstance.manip_scale_about(f, QPointF(old[0] - 100.0, old[1] + 100.0), 2.0)
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
    # A pending debounced rebuild must not outlive the test: it would fire in
    # the NEXT test's event loop on this dropped scene (selectedItems() on a
    # scene whose model is gone aborts: access violation).
    sec._rebuild_timer.stop()
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


# -- C-3: rotate / flip / scale write the model block ------------------------

def _hosted(ms, gl):
    """The model blocks hosted on gridline *gl* (undo re-creates instances)."""
    return ms.hosted_blocks_on(ms.gridline_by_uid(gl._uid))


def test_rotate_tool_turns_the_model_block_about_the_view_normal(host):
    """AC3 / AC11: Rotate 90 deg (Y-up CCW) about a pivot 500 mm left of the
    insertion point turns the MODEL block (rotation 90) and swings its host
    point to along 2000 / elevation 1700; one undo step; re-projected in this
    section, a same-side parallel section and the far-side one (rotation
    negated, mirror toggled there -- hosted-blocks D4); undo restores.
    RED when: ``self._write_back(old)`` is deleted from
    ``_HostedBlockCopy.manip_rotate`` (model stays 0 deg at along 2500)."""
    ms, sec, gl, inst, view, statuses = host
    same, far = _same_side(ms), _far_side(ms)
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("rotate") is True
    click(view, QPointF(2000.0, -1200.0))                 # pivot
    click(view, QPointF(3000.0, -1200.0))                 # start ray, heading 0
    move(view, QPointF(2000.0, -2200.0))
    click(view, QPointF(2000.0, -2200.0))                 # end ray, heading 90
    assert inst.block_rotation() == pytest.approx(90.0)
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG - 500.0)
    assert inst.host["elevation_mm"] == pytest.approx(PLACED_ELEV + 500.0)
    assert inst.host["gridline"] == gl._uid and inst.host["offset_mm"] == 0.0
    assert ms._undo_pos == pos0 + 1
    for s in (sec, same, far):
        s.rebuild()
    assert _pose(sec._hosted_copies[id(inst)])[:4] == (2000.0, -1700.0, 90.0, False)
    assert _pose(same._hosted_copies[id(inst)])[2:4] == (90.0, False)
    assert _pose(far._hosted_copies[id(inst)])[2:4] == (-90.0, True)
    ms.undo()
    (back,) = _hosted(ms, gl)
    assert back.block_rotation() == pytest.approx(0.0)
    assert back.host["along_mm"] == pytest.approx(PLACED_ALONG)


def test_flip_arrow_and_enter_flip_the_model_block(host):
    """AC3: Flip left-right (the real Right-arrow, then Enter, on the
    SectionView) mirrors the MODEL block across the vertical line through
    the selection's centre: mirrored, rotation 0, along mirrored about the
    centre; one undo step; the far side sees it un-mirrored (D4).
    RED when: ``self._write_back(old)`` is deleted from
    ``_HostedBlockCopy.manip_reflect``."""
    ms, sec, gl, inst, view, statuses = host
    far = _far_side(ms)
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("flip") is True
    cx = sec._flip_center.x()                             # the tool's own centre
    QTest.keyClick(view, Qt.Key.Key_Right)
    QTest.keyClick(view, Qt.Key.Key_Return)
    assert inst.block_mirrored() is True
    assert inst.block_rotation() == pytest.approx(0.0)
    assert inst.host["along_mm"] == pytest.approx(2.0 * cx - PLACED_ALONG)
    assert inst.host["elevation_mm"] == pytest.approx(PLACED_ELEV)
    assert ms._undo_pos == pos0 + 1
    far.rebuild()
    assert far._hosted_copies[id(inst)].block_mirrored() is False


def test_scale_tool_scales_the_model_block(host):
    """AC3: Scale with base 500 mm left of the insertion point, reference at
    the insertion point (1x = 500 mm), new size at 1000 mm -> factor 2: the
    MODEL block's scale is 2 and its host point moves to along 3000; one
    undo step; a parallel section shows the doubled block.
    RED when: ``self._write_back(old)`` is deleted from
    ``_HostedBlockCopy.manip_scale_about``."""
    ms, sec, gl, inst, view, statuses = host
    same = _same_side(ms)
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("scale") is True
    click(view, QPointF(2000.0, -1200.0))                 # base
    click(view, QPointF(2500.0, -1200.0))                 # reference: 500 mm = 1x
    move(view, QPointF(3000.0, -1200.0))
    click(view, QPointF(3000.0, -1200.0))                 # 1000 mm -> x2
    assert inst.block_scale() == pytest.approx(2.0)
    assert inst.host["along_mm"] == pytest.approx(3000.0)
    assert inst.host["elevation_mm"] == pytest.approx(PLACED_ELEV)
    assert ms._undo_pos == pos0 + 1
    same.rebuild()
    assert same._hosted_copies[id(inst)].block_scale() == pytest.approx(2.0)


def test_a_bare_write_back_is_one_deferred_step(host, qapp):
    """AC11: a copy turned outside a tool (no tool push follows) still
    records exactly one undo step, from the deferred flush.
    RED when: the ``self._mark_section_edit()`` line is deleted from
    ``SectionScene._write_hosted_pose`` (no step at all)."""
    ms, sec, gl, inst, view, statuses = host
    pos0 = ms._undo_pos
    cp = sec._hosted_copies[id(inst)]
    cp.manip_rotate(45.0, QPointF(*cp.block_pos()))
    assert inst.block_rotation() == pytest.approx(45.0)
    qapp.processEvents()
    qapp.processEvents()
    assert ms._undo_pos == pos0 + 1


@pytest.mark.parametrize("op", ["rotate", "reflect", "scale"])
def test_far_side_write_back_round_trips_through_the_projection(
        qapp, section_scene_for, op):
    """A far-side section's Rotate / Reflect / Scale write the model block so
    that rebuilding that section reproduces the copy's edited pose (D2 / D4:
    rotation negated and mirror toggled when the host is seen from behind).
    """
    ms, sec, gl, inst = _setup(section_scene_for)
    far = _far_side(ms)
    sec.rebuild()
    cp = far._hosted_copies[id(inst)]
    old = cp.block_pos()
    if op == "rotate":
        cp.manip_rotate(90.0, QPointF(old[0] - 500.0, old[1]))
    elif op == "reflect":
        cp.manip_reflect(QPointF(old[0] + 100.0, 0.0),
                         QPointF(old[0] + 100.0, -1000.0))
    else:
        cp.manip_scale_about(QPointF(old[0] - 100.0, old[1] + 100.0), 2.0)
    want = _pose(cp)
    far.rebuild()
    assert _pose(far._hosted_copies[id(inst)]) == want


# -- C-4: copies are model blocks --------------------------------------------
from firepro3d.constants import ARRAY_DEFAULT_MEMORY


def _new_block(ms, gl, old):
    """The one hosted block on *gl* that is not *old*."""
    (new,) = [b for b in _hosted(ms, gl) if b is not old]
    return new


def test_duplicate_places_a_model_block_on_the_same_gridline(host):
    """AC3 / AC11: Duplicate base (2500,-1200) -> (3500,-700): a SECOND
    model block hosted on gridline B at along 3500 / elevation 700, same
    pose; the original untouched; one undo step; the new copy selected.
    RED when: ``cp = self._place_hosted_record(obj, offset)`` in
    ``SectionScene.paste_items`` becomes ``cp = None`` ("Nothing duplicated")."""
    from firepro3d.section_scene import _ROLE_SOURCE
    ms, sec, gl, inst, view, statuses = host
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("duplicate") is True
    click(view, QPointF(2500.0, -1200.0))
    click(view, QPointF(3500.0, -700.0))
    new = _new_block(ms, gl, inst)
    assert new.host["along_mm"] == pytest.approx(3500.0)
    assert new.host["elevation_mm"] == pytest.approx(700.0)
    assert new.block_id == inst.block_id and new.block_rotation() == 0.0
    assert new.isVisible() is False                       # hosted: never in plan (D11)
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG)
    assert ms._undo_pos == pos0 + 1
    assert [c.data(_ROLE_SOURCE) for c in sec.selectedItems()] == [new]
    sec.rebuild()
    assert id(new) in sec._hosted_copies


@pytest.mark.parametrize("aim, step", [
    ((3500.0, -1200.0), (1000.0, 0.0)),                    # along the gridline
    ((2500.0, -2200.0), (0.0, 1000.0))])                   # vertically
def test_array_copies_along_the_gridline_or_vertically(host, aim, step):
    """AC3: a linear Array by clicks only (the remembered Count, 3 =
    ARRAY_DEFAULT_MEMORY) aimed 1000 mm along h or up creates Count-1 model
    blocks on gridline B at 1000 mm pitch; one undo step.
    RED when: ``SectionScene._paste_accepts`` returns False for a
    ``section_host`` record (Array refuses: nothing copyable)."""
    ms, sec, gl, inst, view, statuses = host
    pos0 = ms._undo_pos
    count = ARRAY_DEFAULT_MEMORY["linear"]["Count"]
    assert sec._modify_ctl.start("array") is True
    click(view, QPointF(2500.0, -1200.0))
    move(view, QPointF(*aim))
    click(view, QPointF(*aim))
    got = sorted((round(b.host["along_mm"], 3), round(b.host["elevation_mm"], 3))
                 for b in _hosted(ms, gl) if b is not inst)
    want = sorted((PLACED_ALONG + k * step[0], PLACED_ELEV + k * step[1])
                  for k in range(1, count))
    assert got == want
    assert ms._undo_pos == pos0 + 1


def test_copy_writes_the_section_payload(host):
    """R4 / R5 contract (and area E's): Copy writes ``scene_role = "section"``
    and the hosted record = the copy's pose in this section + section_host;
    no plan ``host`` key (a plan paste must never place it).
    RED when: the ``d["section_host"] = ...`` line is deleted from
    ``_HostedBlockCopy.to_dict``."""
    ms, sec, gl, inst, view, statuses = host
    assert sec._modify_ctl.start("copy") is True
    click(view, QPointF(2500.0, -1200.0))                 # base
    payload = sec.clipboard_payload()
    assert payload["scene_role"] == "section"
    assert payload["base"] == pytest.approx([2500.0, -1200.0])
    (rec,) = payload["items"]
    assert rec["type"] == "block_instance" and rec["block_id"] == inst.block_id
    assert rec["pos"] == [2500.0, -1200.0]
    assert rec["section_host"] == {"gridline": gl._uid, "offset_mm": 0.0}
    assert "host" not in rec
    assert inst in ms._block_instances                     # Copy deletes nothing


def test_cut_removes_the_model_block_in_one_step(host):
    """R3 / AC11: Cut (base click) copies the record and deletes the MODEL
    block in one undo step; undo brings it back.
    RED when: ``SectionScene._bulk_delete`` returns ``[], 0`` without
    deleting (the block stays)."""
    ms, sec, gl, inst, view, statuses = host
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("cut") is True
    click(view, QPointF(2500.0, -1200.0))
    assert inst not in ms._block_instances
    assert sec.clipboard_payload()["items"][0]["section_host"]["gridline"] == gl._uid
    assert ms._undo_pos == pos0 + 1
    ms.undo()
    assert len(_hosted(ms, gl)) == 1


# -- C-5: paste rules R4 / R5 ------------------------------------------------
import json


def _copy_block(sec, view):
    """Section Copy of the selected hosted copy, base at its insertion point."""
    assert sec._modify_ctl.start("copy") is True
    click(view, QPointF(2500.0, -1200.0))


def _record_status(monkeypatch, scene):
    got = []
    monkeypatch.setattr(scene, "_show_status",
                        lambda m, timeout=5000: got.append(m))
    return got


def test_paste_lands_at_the_cursor_on_the_host_gridline(host):
    """R4 / AC4 / AC11: Ctrl+V's tool in the same section, click at
    (4000, -500): a new model block on gridline B at along 4000 /
    elevation 500 (the cursor sets both); one undo step.
    RED when: ``h, v = float(p[0]) + offset.x(), ...`` in
    ``_place_hosted_record`` drops ``+ offset`` (the copy lands on the
    original); or ``SectionScene.get_block_definition`` is deleted (the
    ghost path swallows the AttributeError: no ghost; integrator OPEN-6)."""
    ms, sec, gl, inst, view, statuses = host
    _copy_block(sec, view)
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("paste") is True
    move(view, QPointF(4000.0, -500.0))
    assert sec._move_ghost                                # OPEN-6: the paste ghost rides the cursor
    click(view, QPointF(4000.0, -500.0))
    new = _new_block(ms, gl, inst)
    assert new.host["along_mm"] == pytest.approx(4000.0)
    assert new.host["elevation_mm"] == pytest.approx(500.0)
    assert ms._undo_pos == pos0 + 1


def test_paste_into_a_parallel_section(host, monkeypatch):
    """AC4 / AC3: copied in one section, pasted in a parallel one: the new
    model block sits on gridline B where clicked there, and the first
    section shows it after a rebuild.
    RED when: ``shows_host_gridline`` returns False (the paste is refused)."""
    ms, sec, gl, inst, view, statuses = host
    _copy_block(sec, view)
    same = _same_side(ms)
    same_view = _show(same)
    try:
        same.toggle_snap(False)
        _record_status(monkeypatch, same)
        pos0 = ms._undo_pos
        assert same._modify_ctl.start("paste") is True
        click(same_view, QPointF(4000.0, -500.0))
        new = _new_block(ms, gl, inst)
        assert new.host["along_mm"] == pytest.approx(4000.0)
        assert new.host["elevation_mm"] == pytest.approx(500.0)
        assert ms._undo_pos == pos0 + 1
        sec.rebuild()
        assert id(new) in sec._hosted_copies
    finally:
        same_view.close()
        same_view.deleteLater()
        QApplication.processEvents()


def test_paste_refused_where_the_host_gridline_is_not_shown(host, monkeypatch):
    """R4: a section cut across gridline B (not parallel) does not show it:
    Paste refuses with the footer reason, no mode, nothing placed.
    RED when: the ``paste_refusal`` check is deleted from ``begin_paste``
    (Paste arms; status is not the refusal)."""
    from firepro3d.constants import SECTION_PASTE_NO_HOST
    ms, sec, gl, inst, view, statuses = host
    _copy_block(sec, view)
    cross = _section(ms, (3000, 2000), (3000, -8000), 1, name="Cross")
    got = _record_status(monkeypatch, cross)
    assert cross._modify_ctl.start("paste") is False
    assert cross.mode in (None, "select")
    assert got[-1] == SECTION_PASTE_NO_HOST
    assert len(_hosted(ms, gl)) == 1


def test_plan_refuses_a_hosted_block_clipboard(host, monkeypatch):
    """R5: hosted blocks never paste in plan -- the plan's Paste refuses with
    the footer reason, and its paste path places nothing (no plain block at
    the section coordinates).
    RED when: the ``if obj.get("section_host"): return False`` line is
    deleted from ``Model_Space._paste_accepts`` (a second block appears)."""
    from firepro3d.constants import HOSTED_PASTE_IN_PLAN
    ms, sec, gl, inst, view, statuses = host
    _copy_block(sec, view)
    got = _record_status(monkeypatch, ms)
    assert ms._modify_ctl.start("paste") is False
    assert got[-1] == HOSTED_PASTE_IN_PLAN
    assert ms.paste_items(QPointF(0.0, 0.0)) == []
    assert ms._block_instances == [inst]


def _clip(items):
    from firepro3d.constants import CLIPBOARD_FORMAT_VERSION
    QApplication.clipboard().setText(json.dumps(
        {"fp3d_clipboard": CLIPBOARD_FORMAT_VERSION, "base": [2500.0, -1200.0],
         "scene_role": "plan", "items": items, "constraints": []}))


def test_plan_items_refuse_in_a_section(host):
    """R5: a clipboard of plan items only (a node) refuses in a section.
    RED when: ``SectionScene.paste_refusal`` returns None for an all-refused
    clipboard (Paste arms, then "Nothing pasted")."""
    from firepro3d.constants import SECTION_PASTE_PLAN_ITEMS
    ms, sec, gl, inst, view, statuses = host
    _clip([{"type": "node", "x": 0.0, "y": 0.0}])
    assert sec._modify_ctl.start("paste") is False
    assert statuses[-1] == SECTION_PASTE_PLAN_ITEMS


def test_a_mixed_clipboard_pastes_the_fitting_part(host):
    """R5: hosted block + plan node on the clipboard: the section pastes the
    block and reports the node skipped.
    RED when: ``SectionScene.paste_refusal`` refuses on ANY refused record
    (``if len(accepted) < len(items): return SECTION_PASTE_PLAN_ITEMS``)."""
    ms, sec, gl, inst, view, statuses = host
    rec = sec._clipboard_item_dicts([sec._hosted_copies[id(inst)]])[0]
    _clip([rec, {"type": "node", "x": 0.0, "y": 0.0}])
    assert sec._modify_ctl.start("paste") is True
    click(view, QPointF(4000.0, -500.0))
    assert _new_block(ms, gl, inst).host["along_mm"] == pytest.approx(4000.0)
    assert statuses[-1] == "Pasted 1 item(s) (1 skipped)"


# -- C-6: Mirror across a section gridline -----------------------------------

def test_mirror_across_a_section_gridline_creates_a_mirrored_model_block(host):
    """AC3 / AC11: a plan gridline crossing the cut at x = 4000 projects an
    elevation gridline at h = 4000; Mirror picks it as the axis and creates
    a SECOND model block on gridline B at along 2*4000 - 2500 = 5500,
    mirrored (rotation 0 -> reflect_pose(0, False, +-90) = 0); the original
    stays; one undo step.
    RED when: ``axis_picker.pick_axis`` reads ``getattr(scene, "_gridlines",
    [])`` again instead of ``_line_targets(scene)`` (no axis: nothing
    mirrored)."""
    from firepro3d.section_scene import ElevGridlineItem
    from tests._hosted_blocks_helpers import gridline
    ms, sec, gl, inst, view, statuses = host
    gridline(ms, (4000, 2000), (4000, -8000), "4")         # crosses the cut
    sec.rebuild()
    sec.select_items([sec._hosted_copies[id(inst)]])
    (eg,) = [it for it in sec.items() if isinstance(it, ElevGridlineItem)
             and abs(it.mapToScene(it.line().p1()).x() - 4000.0) < 1e-6]
    a, b = eg.drawn_endpoints()
    mid = QPointF(4000.0, round((a.y() + b.y()) / 20.0) * 10.0)   # on the line, 10 mm grid
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("mirror") is True
    move(view, mid)
    click(view, mid)
    new = _new_block(ms, gl, inst)
    assert new.host["along_mm"] == pytest.approx(2 * 4000.0 - PLACED_ALONG)
    assert new.host["elevation_mm"] == pytest.approx(PLACED_ELEV)
    assert new.block_mirrored() is True
    assert new.block_rotation() == pytest.approx(0.0)
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG)
    assert inst.block_mirrored() is False
    assert ms._undo_pos == pos0 + 1


# -- C-7: the selection survives a rebuild -----------------------------------

def test_moved_copy_stays_selected_after_the_debounced_rebuild(host):
    """Plan parity (scene-tools D3): after a section Move the moved block's
    rebuilt copy is still the selection.
    RED when: the ``self._reselect_editable(keep)`` line is deleted from
    ``rebuild`` (the rebuilt copy is not selected)."""
    ms, sec, gl, inst, view, statuses = host
    assert sec._modify_ctl.start("move") is True
    click(view, QPointF(2500.0, -1200.0))
    click(view, QPointF(2800.0, -1200.0))
    QTest.qWait(250)                                       # the debounced rebuild
    cp2 = sec._hosted_copies[id(inst)]
    assert sec.selectedItems() == [cp2]


# -- C-9b: typed input in a section ------------------------------------------

def test_typed_move_is_section_mm_on_a_calibrated_project(host):
    """C-9: on a CALIBRATED project (2 px per mm) a typed "500 mm" Move in a
    section moves the model block 500 mm along its gridline (section units are
    mm; the HUD must not divide by pixels_per_mm). Real digit / Tab / Return
    keys; one undo step; the HUD closes.
    RED when: ``SectionScene._hud_scale_manager`` returns ``self._sm`` (the
    calibrated project ScaleManager: the block moves 1000 mm)."""
    ms, sec, gl, inst, view, statuses = host
    ms.scale_manager.set_pixels_per_mm(2.0)
    sec.rebuild()
    cp = sec._hosted_copies[id(inst)]
    # gridline origin (0,-3000) px -> world (0, 1500) mm; along 2500 -> h 2500
    assert cp.block_pos() == pytest.approx((2500.0, -1200.0))   # precondition
    sec.select_items([cp])
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("move") is True
    click(view, QPointF(2500.0, -1200.0))
    QTest.keyClick(view, Qt.Key.Key_5)                    # engages, seeds "5"
    hud = sec.dynamic_input
    assert hud is not None and hud.is_engaged()
    QTest.keyClicks(hud.editor("dX"), "00 mm")
    QTest.keyClick(hud.editor("dX"), Qt.Key.Key_Tab)
    QTest.keyClicks(hud.editor("dY"), "0 mm")
    QTest.keyClick(hud.editor("dY"), Qt.Key.Key_Return)
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG + 500.0)
    assert inst.host["elevation_mm"] == pytest.approx(PLACED_ELEV)
    assert ms._undo_pos == pos0 + 1
    assert sec.dynamic_input is None


def test_tab_engages_and_a_canvas_click_is_inert_while_typing(host):
    """C-9: Tab on the SectionView engages the HUD; a canvas click while a
    field has the keyboard commits nothing and the tool stays live.
    RED when: the press gate (``if hud is not None and sc.is_input_mode():``)
    is deleted from ``SectionView.mousePressEvent`` (the click commits the
    Move: along 3000), or ``focusNextPrevChild`` is deleted (Tab leaves the
    view: no HUD)."""
    ms, sec, gl, inst, view, statuses = host
    pos0 = ms._undo_pos
    assert sec._modify_ctl.start("move") is True
    click(view, QPointF(2500.0, -1200.0))
    QTest.keyClick(view, Qt.Key.Key_Tab)
    assert sec.is_input_mode() is True
    click(view, QPointF(3000.0, -1200.0))
    assert inst.host["along_mm"] == pytest.approx(PLACED_ALONG)
    assert sec.mode == "move" and sec.is_input_mode() is True
    assert ms._undo_pos == pos0
