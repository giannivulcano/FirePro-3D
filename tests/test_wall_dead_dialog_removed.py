"""Guard: the dead wall edit dialog stays gone (maint, HF1 seam-review line).

``WallSegment._open_edit_dialog`` had no caller, and its ``WallDialog`` colour row
was a raw ``QLineEdit`` whose ``get_params`` fell back to ``#cccccc``, so wiring it
would have silently recoloured a No-colour wall and bypassed the universal picker.
Both were deleted; a wall is edited through the property panel.
"""
import importlib.util

from firepro3d.wall import WallSegment


def test_wall_segment_has_no_edit_dialog_entry_point():
    assert not hasattr(WallSegment, "_open_edit_dialog")


def test_wall_dialog_module_is_gone():
    assert importlib.util.find_spec("firepro3d.wall_dialog") is None
