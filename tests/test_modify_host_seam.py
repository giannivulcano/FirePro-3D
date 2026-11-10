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
