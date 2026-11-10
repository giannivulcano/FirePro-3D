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
