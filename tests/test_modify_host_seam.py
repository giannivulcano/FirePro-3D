"""ModifyHostMixin seam (elevation-parity design D2, area B).

Structural tripwires for the relocation (Model_Space names keep resolving
through inheritance) plus, from Task B-6, the end-to-end guard that a
non-Model_Space host built from the mixin runs the modify tools.
"""
import pytest

from firepro3d.model_space import Model_Space
from firepro3d.modify_host import ModifyHostMixin

_MOVED = ("_show_status", "_snap_view", "_active_view_scale",
          "update_preview_node", "_move_preview_node", "_preview_from_move",
          "_move_paste_move", "_move_rotate", "_move_array", "_move_reflect",
          "_press_copy_base", "_press_paste_move", "begin_move_from",
          "_begin_move_handle_snap", "_move_handle_snap",
          "_apply_move_displacement", "_apply_paste_displacement",
          "_press_rotate", "_apply_rotate_by", "_press_array",
          "_apply_array_dynamic_input", "_press_scale", "_move_scale",
          "_apply_scale_factor", "_press_reflect", "_shape_paths_for_move",
          "_clipboard_ghost_paths", "_build_move_ghost_base", "move_items",
          "clipboard_payload", "clipboard_data")


def test_model_space_is_a_modify_host():
    assert issubclass(Model_Space, ModifyHostMixin)


@pytest.mark.parametrize("name", _MOVED)
def test_moved_member_has_one_home(name):
    """Each relocated member is defined once, on the mixin (no shadow copy
    left on Model_Space), and resolves from Model_Space by inheritance."""
    assert name in vars(ModifyHostMixin)
    assert name not in vars(Model_Space)
    assert getattr(Model_Space, name) is getattr(ModifyHostMixin, name)


def test_signals_declared_once_on_the_mixin(model_space):
    assert "instructionChanged" in vars(ModifyHostMixin)
    assert "modeChanged" in vars(ModifyHostMixin)
    assert "instructionChanged" not in vars(Model_Space)
    assert "modeChanged" not in vars(Model_Space)
    ms = model_space            # held for the test's life
    got = []
    ms.modeChanged.connect(got.append)
    ms.set_mode("select")
    assert got == ["select"]


_STATE = ("_copy_is_cut", "_paste_payload", "pick_base_pos", "_selected_items",
          "_move_ghost", "_move_ghost_base", "_ghost_dimmed",
          "_move_handle_session", "_offset_source", "_offset_dist",
          "_offset_side", "_offset_typed", "_offset_sticky",
          "_offset_sticky_locked", "_rotate_pivot", "_rotate_start_deg",
          "_rotate_ray", "_array_base", "_array_dir", "_array_spacing",
          "_array_row_spacing", "_array_total", "_array_start_deg",
          "_array_variant", "_array_angle_locked", "_array_memory",
          "_scale_base", "_scale_ref", "_scale_variant", "_mirror_axis",
          "_flip_center", "_flip_lr", "_flip_ud", "_flip_quad")


def test_init_modify_host_owns_the_transient_state(model_space):
    """Every modify transient a Model_Space starts with is the one
    _init_modify_host() sets (one home), with the same initial values."""
    from firepro3d.constants import ARRAY_DEFAULT_MEMORY
    from firepro3d.modify_tools_controller import ModifyToolsController
    ms = model_space
    assert isinstance(ms._modify_ctl, ModifyToolsController)
    assert ms._modify_ctl._scene is ms
    expected = {"_copy_is_cut": False, "_paste_payload": None,
                "pick_base_pos": None, "_selected_items": None,
                "_move_ghost": [], "_move_ghost_base": [], "_ghost_dimmed": [],
                "_move_handle_session": None, "_offset_source": None,
                "_offset_dist": 0.0, "_offset_side": 1.0,
                "_offset_typed": False, "_offset_sticky": None,
                "_offset_sticky_locked": False, "_rotate_pivot": None,
                "_rotate_start_deg": None, "_rotate_ray": None,
                "_array_base": None, "_array_dir": None,
                "_array_spacing": 0.0, "_array_row_spacing": 0.0,
                "_array_total": None, "_array_start_deg": None,
                "_array_variant": "linear", "_array_angle_locked": None,
                "_array_memory": {v: dict(f) for v, f
                                  in ARRAY_DEFAULT_MEMORY.items()},
                "_scale_base": None, "_scale_ref": None,
                "_scale_variant": "length", "_mirror_axis": None,
                "_flip_center": None, "_flip_lr": False, "_flip_ud": False,
                "_flip_quad": None}
    assert set(expected) == set(_STATE)
    for name, value in expected.items():
        assert getattr(ms, name) == value, name
    # The array memory is per scene, never the shared constant.
    assert ms._array_memory is not ARRAY_DEFAULT_MEMORY


def test_init_modify_host_refuses_a_host_missing_a_required_method(qapp):
    from PyQt6.QtWidgets import QGraphicsScene

    class _Bare(ModifyHostMixin, QGraphicsScene):
        pass

    with pytest.raises(TypeError, match="push_undo_state"):
        _Bare()._init_modify_host()


# The modify rows of the five Model_Space tables, copied from the raw source
# at the pre-B-4 tree (model_space.py, the literal dict rows), NOT read back
# from the module after the move (integrator R-B-01).
HEAD_PRESS_ROWS = {
    "paste": "_press_paste_move", "copy_base": "_press_copy_base",
    "duplicate": "_press_paste_move", "move": "_press_paste_move",
    "rotate": "_press_rotate", "array": "_press_array",
    "scale": "_press_scale", "flip": "_press_reflect",
    "mirror": "_press_reflect"}
HEAD_MOVE_ROWS = {
    "move": "_move_paste_move", "paste": "_move_paste_move",
    "copy_base": "_move_preview_node", "duplicate": "_move_paste_move",
    "rotate": "_move_rotate", "scale": "_move_scale", "array": "_move_array",
    "flip": "_move_reflect", "mirror": "_move_reflect"}
HEAD_PREVIEW_ROWS = {
    "move": "_preview_from_move", "paste": "_preview_from_move",
    "duplicate": "_preview_from_move"}
HEAD_SCHEMA_ROWS = {
    "move": "displacement", "paste": "displacement",
    "duplicate": "displacement", "rotate": "rotate_by",
    "scale": "scale_factor"}
HEAD_APPLIER_ROWS = {
    "move": "_apply_move_displacement", "paste": "_apply_paste_displacement",
    "duplicate": "_apply_move_displacement", "rotate": "_apply_rotate_by",
    "scale": "_apply_scale_factor", "array": "_apply_array_dynamic_input"}


def test_model_space_tables_carry_the_modify_slices():
    """Each Model_Space table holds the mixin's slice unchanged (the slice is
    the one home of the modify rows, splatted into the plan tables), and the
    slices equal the HEAD source rows."""
    pairs = ((Model_Space._PRESS_DISPATCH, ModifyHostMixin._MODIFY_PRESS_DISPATCH, HEAD_PRESS_ROWS),
             (Model_Space._MOVE_DISPATCH, ModifyHostMixin._MODIFY_MOVE_DISPATCH, HEAD_MOVE_ROWS),
             (Model_Space._PREVIEW_DISPATCH, ModifyHostMixin._MODIFY_PREVIEW_DISPATCH, HEAD_PREVIEW_ROWS),
             (Model_Space._SCHEMA_FOR_MODE, ModifyHostMixin._MODIFY_SCHEMA_FOR_MODE, HEAD_SCHEMA_ROWS),
             (Model_Space._APPLIER_FOR_MODE, ModifyHostMixin._MODIFY_APPLIER_FOR_MODE, HEAD_APPLIER_ROWS))
    for table, slice_, head in pairs:
        assert slice_ and {k: table[k] for k in slice_} == slice_
        assert slice_ == head
        assert {k: table[k] for k in head} == head
    assert set(ModifyHostMixin._MODIFY_PRESS_DISPATCH) == ModifyHostMixin._MODIFY_MODES
    assert set(ModifyHostMixin._MODIFY_MOVE_DISPATCH) == ModifyHostMixin._MODIFY_MODES
    # Model_Space hosts every controller tool; the mixin default hosts the
    # ten section tools (no Offset / Fillet: they need the 2D-geometry lists).
    from firepro3d.modify_tools_controller import ModifyToolsController
    assert Model_Space._HOST_TOOLS == frozenset(ModifyToolsController._TOOL_MODE)
    assert ModifyHostMixin._HOST_TOOLS == frozenset(
        ModifyToolsController._TOOL_MODE) - {"offset", "fillet"}


@pytest.mark.parametrize("mode, text", [
    ("move", "Pick base point"), ("copy_base", "Pick base point"),
    ("duplicate", "Pick base point"), ("rotate", "Pick pivot point"),
    ("scale", "Pick base point"), ("mirror", "Pick mirror axis")])
def test_plan_entry_instruction_unchanged(model_space, mode, text):
    """Behaviour-neutral: the plan scene still emits the same entry line."""
    got = []
    model_space.instructionChanged.connect(got.append)
    model_space.set_mode(mode)
    assert model_space.mode == mode
    assert got and got[-1] == text


def test_model_view_paints_modify_overlays_through_the_shared_function(
        qapp, monkeypatch):
    """Model_View hands its modify overlays to the one shared painter."""
    from PyQt6.QtCore import QPointF
    from firepro3d import modify_host
    from firepro3d.geometry_2d import LineItem
    from tests._snap_polish_helpers import click, close_view, make_view, move
    calls = []
    real = modify_host.paint_modify_overlays
    monkeypatch.setattr(modify_host, "paint_modify_overlays",
                        lambda p, v, s: (calls.append((v, s)), real(p, v, s)))
    view, scene = make_view(scale=1.0)   # Block Editor role, as the move suites
    try:
        line = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(line); scene._draw_lines.append(line)
        scene.select_items([line])
        scene._modify_ctl.start("move")
        click(view, QPointF(0, 0)); move(view, QPointF(0, 200))
        view.viewport().repaint()
        assert (view, scene) in calls
    finally:
        close_view(view, scene)


# ── Second host (Task B-6): the seam area C mounts SectionScene on ────────
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (QApplication, QGraphicsRectItem, QGraphicsScene,
                             QGraphicsView)

from firepro3d.constraint_controller import ConstraintController
from firepro3d.geometry_2d import LineItem
from firepro3d.halo_selection import HaloSelectionMixin
from firepro3d.modify_host import paint_modify_overlays
from firepro3d.modify_tools_controller import ModifyToolsController
from tests._modify_tools_helpers import grips, ignore_os_mouse
from tests._snap_polish_helpers import click, move


class _MinimalHost(HaloSelectionMixin, ModifyHostMixin, QGraphicsScene):
    """The smallest modify host: the mixin + one controller, nothing else."""

    def __init__(self):
        super().__init__()
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.scene_role = "modify_host_test"   # not plan / block_editor: constraints off
        self.constraint_ctl = ConstraintController(self)
        self._init_halo_state()
        self._init_modify_host()
        # Real hosts hold a SelectionManipulator (accepts hover); without one
        # hover-accepting item Qt drops button-less moves before the scene
        # (P4c). Mirror that precondition.
        sentinel = QGraphicsRectItem(4000, 4000, 1, 1)
        sentinel.setAcceptHoverEvents(True)
        self.addItem(sentinel)
        self.undo_pushes = 0
        self.statuses = []

    # Required host methods (REQUIRED_HOST_METHODS; select_items comes
    # from HaloSelectionMixin).
    def push_undo_state(self):
        self.undo_pushes += 1

    def _clipboard_item_dicts(self, items):
        return [it.to_dict() for it in items if hasattr(it, "to_dict")]

    def paste_items(self, offset, data=None, constraints=None, rotation_deg=None):
        return []

    def _paste_accepts(self, obj):
        return False

    def _add_from_dict(self, d):
        return None

    def _bulk_delete(self, selected, selected_set):
        return [], 0

    def _show_status(self, message, timeout=5000):   # observed, not a window
        self.statuses.append(message)

    # The host's event handlers try the modify slice first (what C adds to
    # SectionScene).
    def mousePressEvent(self, event):
        if self.modify_mouse_press(event):
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.modify_mouse_move(event):
            return
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if self.modify_key_press(event):
            return
        super().keyPressEvent(event)


class _HostView(QGraphicsView):
    """A host view painting the shared modify overlays (what C / D add to
    SectionView.drawForeground)."""

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        paint_modify_overlays(painter, self, self.scene())


@pytest.fixture
def host_view(qapp):
    host = _MinimalHost()
    view = ignore_os_mouse(_HostView(host))
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.centerOn(50, 150)
    QApplication.processEvents()
    yield view, host                 # the test holds both for its life
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def _line(host):
    line = LineItem(QPointF(0, 0), QPointF(100, 0))
    host.addItem(line)
    host.select_items([line])
    return line


def _flat(pts):
    return [c for p in pts for c in p]


def _differing_pixels(a, b) -> int:
    assert a.size() == b.size()
    return sum(1 for y in range(a.height()) for x in range(a.width())
               if a.pixel(x, y) != b.pixel(x, y))


def test_second_host_runs_move_end_to_end(host_view):
    """Start -> base click -> move -> destination click on a non-Model_Space
    host: the item moves by the picked displacement, one undo push, back to
    Select with the original selected (scene-tools D3).
    RED when: the ``getattr(self, name)(event, scene_pos, snapped, None,
    None, None)`` call in ``modify_mouse_press`` is replaced by ``pass``
    (the press is swallowed, nothing moves; integrator R-B-02: deleting the
    "move" row also empties ``_MODIFY_MODES`` and fails at ``start``)."""
    view, host = host_view
    line = _line(host)
    before = grips(line)
    instr = []
    host.instructionChanged.connect(instr.append)
    assert host._modify_ctl.start("move") is True
    assert host.mode == "move"
    assert instr[-1] == "Pick base point"
    click(view, QPointF(0, 0))                       # base (fixture point)
    base = QPointF(host.pick_base_pos)
    move(view, QPointF(0, 300))
    assert host._move_ghost                           # ghost rides the cursor
    click(view, QPointF(0, 300))                      # destination commits
    dx, dy = 0.0 - base.x(), 300.0 - base.y()
    assert _flat(grips(line)) == pytest.approx(
        _flat([(x + dx, y + dy) for x, y in before]), abs=0.5)
    assert host.undo_pushes == 1
    assert host.mode is None
    assert host.selectedItems() == [line]


def test_second_host_paints_the_ghost_and_esc_cancels(host_view):
    """The shared painter draws the Move ghost in the host's view; the real
    Esc key ends the tool with nothing moved and no undo push.
    RED when: the ``paint_ghost(painter, mghost, th.detect())`` call is
    deleted from paint_modify_overlays (with- and without-ghost grabs match)."""
    view, host = host_view
    line = _line(host)
    before = grips(line)
    assert host._modify_ctl.start("move") is True
    click(view, QPointF(0, 0))
    move(view, QPointF(0, 300))
    region = view.mapFromScene(QRectF(-10, 290, 120, 20)).boundingRect()
    with_ghost = view.viewport().grab(region).toImage()
    QTest.keyClick(view, Qt.Key.Key_Escape)           # real key -> scene
    assert host.mode is None
    assert host.statuses[-1] == "Mode cancelled"
    QApplication.processEvents()
    without = view.viewport().grab(region).toImage()
    assert _differing_pixels(with_ghost, without) > 20
    assert grips(line) == before
    assert host.undo_pushes == 0


def test_second_host_refuses_a_tool_it_does_not_host(host_view):
    """Offset needs the plan 2D-geometry lists: refused with a status, no
    mode. RED when: the _HOST_TOOLS check is removed from start()
    (begin_offset returns True)."""
    view, host = host_view
    line = _line(host)
    assert host._modify_ctl.can_start("offset", [line]) is False
    assert host._modify_ctl.can_start("move", [line]) is True
    assert host._modify_ctl.start("offset") is False
    assert host.mode is None
    assert host.statuses[-1] == ModifyToolsController.TOOL_NOT_HOSTED


def test_editable_selection_hook_feeds_the_tool(host_view):
    """start() acts on modify_selection(), not the raw selection; an empty
    editable set refuses with the host's hint.
    RED when: start() reads ``s.selectedItems()`` again (the read-only line
    is captured) / _refusal_hint returns the literal "Select items first"."""
    view, host = host_view
    editable = _line(host)
    readonly = LineItem(QPointF(0, 50), QPointF(100, 50))
    host.addItem(readonly)
    host.select_items([editable, readonly])
    host.modify_selection = lambda: [editable]
    assert host._modify_ctl.start("move") is True
    assert host._selected_items == [editable]
    host.set_mode(None)
    host.select_items([readonly])
    host.modify_selection = lambda: []
    host.modify_empty_hint = lambda: "1 items skipped (edit in plan)"
    assert host._modify_ctl.start("move") is False
    assert host.mode is None
    assert host.statuses[-1] == "1 items skipped (edit in plan)"


def test_a_host_enters_only_its_declared_extra_modes(host_view):
    """S4 (integration): the generic set_mode enters a non-modify mode only
    when the host declares it in ``_HOST_EXTRA_MODES`` (SectionScene
    declares "note", T37); any other mode stays ignored.
    RED when: the ``and mode not in self._HOST_EXTRA_MODES`` clause is
    deleted from ``ModifyHostMixin.set_mode`` (the host stays in Select)."""
    view, host = host_view
    seen = []
    host.modeChanged.connect(seen.append)
    host.set_mode("note")
    assert host.mode is None and seen == []             # not declared: ignored
    host._HOST_EXTRA_MODES = frozenset({"note"})
    host.set_mode("note")
    assert host.mode == "note" and seen == ["note"]
    host.set_mode(None)
    assert host.mode is None
