"""Escape during a point-pick sub-mode must EXIT the sub-mode, not close the
dialog (Bug 1). A subsequent Escape (no pick mode active) must still close it.

Real QKeyEvents are posted through the event system (not slot calls) because
this codebase has a history of slot-level tests passing while event wiring is
broken.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent


def _escape_event() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                     Qt.KeyboardModifier.NoModifier)


def test_escape_exits_pick_mode_without_closing(qapp):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")

    rejected = []
    dlg.rejected.connect(lambda: rejected.append(True))

    # Enter the base-point pick sub-mode the way _start_pick_base does.
    dlg._start_pick_base()
    assert dlg._pick_mode == "base"

    # First Escape: exits the pick mode, dialog stays open (rejected NOT fired).
    qapp.sendEvent(dlg, _escape_event())
    assert dlg._pick_mode is None
    assert rejected == []                     # dialog did NOT close/reject
    # Pick cursor was released back to pan mode.
    assert dlg._preview_view._mode == "pan"

    # Second Escape (no pick mode active): the dialog rejects/closes as before.
    qapp.sendEvent(dlg, _escape_event())
    assert rejected == [True]

    dlg.deleteLater()


def test_escape_cancels_scale_pick_and_clears_markers(qapp):
    from firepro3d.underlay_import_dialog import UnderlayImportDialog
    dlg = UnderlayImportDialog(None, levels=["Level 1"], current_level="Level 1")

    dlg._start_pick2()
    assert dlg._pick_mode == "scale_pt1"

    qapp.sendEvent(dlg, _escape_event())
    assert dlg._pick_mode is None
    assert dlg._pick_markers == []
    assert dlg._pick_pts == []
    assert dlg._preview_view._mode == "pan"

    dlg.deleteLater()
