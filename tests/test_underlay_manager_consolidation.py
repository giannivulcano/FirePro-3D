import inspect
import firepro3d.dxf_preview_dialog as dpd
import firepro3d.display_manager as dm
import firepro3d.model_browser as mb


def test_import_dialog_has_no_level_combo():
    assert "_level_combo" not in inspect.getsource(dpd)


def test_display_manager_has_no_underlays_tab():
    src = inspect.getsource(dm)
    assert "_build_underlays_tab" not in src
    assert "_underlay_snapshot" not in src
    assert "hidden_in_views" not in src


def test_browser_underlay_menu_has_no_change_level():
    """Model Browser underlay context menu must not contain edit actions."""
    src = inspect.getsource(mb)
    assert "Change Level" not in src, (
        "Change Level action must be removed from model_browser (editing "
        "belongs in Underlay Manager)"
    )
    assert "Relink…" not in src, (
        "Relink… action must be removed from model_browser (editing "
        "belongs in Underlay Manager)"
    )


def test_browser_underlay_no_layer_child_nodes():
    """Model Browser must not create per-layer child nodes under underlays."""
    src = inspect.getsource(mb)
    assert "_toggle_underlay_layer" not in src, (
        "_toggle_underlay_layer must be removed — layer child nodes are gone"
    )
    assert "_set_underlay_level" not in src, (
        "_set_underlay_level must be removed — level editing moved to Underlay Manager"
    )


def test_browser_underlay_uses_levels_not_level():
    """Level readout must use data.levels (list), not old data.level (str)."""
    src = inspect.getsource(mb)
    assert "data.levels" in src, "Level readout must reference data.levels"
    # data.level (the old single-value attr) must not be read on underlay records
    import re
    # Allow "data.level" only inside comments/strings but not as code
    # Simple check: the literal assignment 'data.level =' must be gone
    assert "data.level =" not in src, (
        "data.level assignment must be gone — use data.levels"
    )
