"""tests/test_ribbon_mode_button_sync.py — Create-tab mode buttons unhighlight (#217).

Bug (user, 2026-09-16): after opening the Block Editor, Create-tab mode buttons
(Rectangle/Spline/Polyline…) stayed green-highlighted and never cleared on mode
exit — the Block Editor registered its buttons into the SAME `_mode_buttons` dict
under the same mode keys, evicting the Create-tab buttons, so `_sync_mode_buttons`
could no longer un-check them.  Fix: the Block Editor uses its own
`_block_mode_buttons` registry; `_sync_mode_buttons` syncs both.

MainWindow-based (mirrors tests/test_stale_view_tabs.py) — pops a window.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    main_mod.View3D = View3D
    w = main_mod.MainWindow()
    yield w
    w._modified = False
    w.close()


def test_block_editor_does_not_evict_create_tab_buttons(mw, qapp):
    create_btn = mw._mode_buttons.get("draw_rectangle")
    assert create_btn is not None, "no Create-tab draw_rectangle button"

    mw._open_block_editor()
    qapp.processEvents()

    # The Create-tab button is untouched in the main registry...
    assert mw._mode_buttons.get("draw_rectangle") is create_btn
    # ...and the Block Editor registered its own, separate button.
    assert "draw_rectangle" in mw._block_mode_buttons
    assert mw._block_mode_buttons["draw_rectangle"] is not create_btn


def test_sync_clears_create_tab_button_after_block_editor(mw, qapp):
    create_btn = mw._mode_buttons["draw_rectangle"]
    mw._open_block_editor()
    qapp.processEvents()

    # Simulate the Create-tab button left checked, then exit to select.
    create_btn.setChecked(True)
    mw._sync_mode_buttons("select")
    assert not create_btn.isChecked(), "Create-tab button stuck checked after mode exit"


def test_sync_checks_only_active_mode_across_registries(mw, qapp):
    mw._open_block_editor()
    qapp.processEvents()
    create_btn = mw._mode_buttons["draw_rectangle"]
    other_btn = mw._mode_buttons.get("draw_circle")

    mw._sync_mode_buttons("draw_rectangle")
    assert create_btn.isChecked()
    if other_btn is not None:
        assert not other_btn.isChecked()
