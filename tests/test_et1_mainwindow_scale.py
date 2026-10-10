"""ET1 G1 (MainWindow half) -- a project drawing-scale change reaches an
open block editor through the units sync, and a freshly opened editor is
seeded with it. Runs in its OWN pytest process (module-scoped MainWindow)."""
from tests.test_constraint_pick_ribbon import mw, win_with_editor  # noqa: F401


def test_g1_project_scale_change_reaches_open_editor(win_with_editor, qapp):
    mw = win_with_editor
    ed = mw._test_editor
    old = mw.scene.scale_manager.drawing_scale
    try:
        mw.scene.scale_manager.drawing_scale = 200.0
        mw._on_project_settings_changed()
        qapp.processEvents()
        assert ed.editor_scene.scale_manager.drawing_scale == 200.0
        ed2 = mw.block_editor_manager.open_new()
        qapp.processEvents()
        assert ed2.editor_scene.scale_manager.drawing_scale == 200.0
    finally:
        mw.scene.scale_manager.drawing_scale = old
        mw._on_project_settings_changed()
        qapp.processEvents()
