"""tests/test_ribbon_mode_button_sync.py — 2D-geo mode buttons sync across registries.

History (#217, user 2026-09-16): when the Block Editor registered its mode
buttons into the SAME `_mode_buttons` dict as the (then-existing) Create tab under
the same mode keys, it evicted the Create-tab buttons so `_sync_mode_buttons`
could no longer un-check them. Fix: the Block Editor uses its own
`_block_mode_buttons` registry; `_sync_mode_buttons` syncs both.

Post-containment-contract (C7): the Create tab is dissolved — the loose
2D-geometry modes (draw_rectangle/…/text) left the MAIN ribbon entirely and now
live ONLY in the Block-Editor palette (`_block_mode_buttons`). The #217 collision
is therefore structurally impossible (the main ribbon has no 2D-geo modes), but
the surviving invariant still matters: those modes are Block-Editor-only, and
`_sync_mode_buttons` must check/clear them across BOTH registries.

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


def test_2d_geo_modes_are_block_editor_only(mw, qapp):
    """C7: loose 2D-geometry modes belong to the Block Editor, not the main ribbon."""
    # The main ribbon no longer carries the loose primitive modes.
    assert "draw_rectangle" not in mw._mode_buttons
    assert "text" not in mw._mode_buttons

    mw._open_block_editor()
    qapp.processEvents()

    # The Block Editor registered them in its own, separate registry.
    assert "draw_rectangle" in mw._block_mode_buttons
    assert "text" in mw._block_mode_buttons, "Text is the 9th primitive (C5) in the palette"


def test_sync_clears_block_editor_button_after_exit(mw, qapp):
    mw._open_block_editor()
    qapp.processEvents()

    block_btn = mw._block_mode_buttons["draw_rectangle"]
    # Simulate the button left checked, then exit to select.
    block_btn.setChecked(True)
    mw._sync_mode_buttons("select")
    assert not block_btn.isChecked(), "Block-Editor button stuck checked after mode exit"


def test_sync_checks_only_active_mode_across_registries(mw, qapp):
    mw._open_block_editor()
    qapp.processEvents()
    block_btn = mw._block_mode_buttons["draw_rectangle"]
    # A surviving main-ribbon mode button (Architecture) must stay unchecked
    # when a Block-Editor mode is the active one.
    wall_btn = mw._mode_buttons.get("wall")

    mw._sync_mode_buttons("draw_rectangle")
    assert block_btn.isChecked()
    if wall_btn is not None:
        assert not wall_btn.isChecked()
