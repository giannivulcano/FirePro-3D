"""VC9 M2 -- the project's pressure / flow / velocity precision reach a Block
Editor scene (opened or already open), so hydraulic tags print with it.
Uses the module-scoped MainWindow fixture from test_constraint_pick_ribbon."""
from tests.test_constraint_pick_ribbon import mw, win_with_editor  # noqa: F401

_HYD = ("pressure_precision", "flow_precision", "velocity_precision")


def test_editor_scene_carries_project_hydraulic_precision(win_with_editor, qapp):
    mw = win_with_editor
    sm = mw.scene.scale_manager
    old = [getattr(sm, a) for a in _HYD]
    ed2 = None
    try:
        sm.pressure_precision, sm.flow_precision, sm.velocity_precision = 3, 2, 2
        mw._on_project_settings_changed()               # open editor follows
        qapp.processEvents()
        esm = mw._test_editor.editor_scene.scale_manager
        assert [getattr(esm, a) for a in _HYD] == [3, 2, 2]
        assert esm.format_pressure(12.3456) == "12.346 psi"
        ed2 = mw.block_editor_manager.open_new()        # a fresh editor is seeded
        qapp.processEvents()
        assert ed2.editor_scene.scale_manager.format_pressure(12.3456) == "12.346 psi"
    finally:
        if ed2 is not None:
            try:
                mw.block_editor_manager.close(ed2)
            except RuntimeError:
                pass
        sm.pressure_precision, sm.flow_precision, sm.velocity_precision = old
        mw._on_project_settings_changed()
        qapp.processEvents()
