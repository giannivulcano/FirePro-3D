"""Shared teardown for test MainWindows (test-harness.md Invariant 6 note).

``close()`` + ``deleteLater()`` + ``processEvents()`` does not delete a window
at fixture-teardown loop level: DeferredDelete is never dispatched there, so the
window lingers until an unrelated later test pumps events -- where its
destruction-time signals fire mid-module, and an app-wide ``setStyleSheet``
repolish walks its half-dead widgets (native access violation / heap
corruption). ``dispose_main_window`` destroys it now.
"""
from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication


def dispose_main_window(win) -> None:
    """Close and destroy a test MainWindow immediately.

    Clears the plan selection first (a selected plan item at close crashes
    the process -- filed bug), drops the dirty flag so ``close()`` cannot
    raise the save prompt, then forces the pending DeferredDelete. Safe on
    ``None`` and on an already-deleted wrapper.

    Args:
        win: The ``MainWindow`` to destroy, or ``None``.
    """
    if win is None or sip.isdeleted(win):
        return
    win._modified = False
    scene = getattr(win, "scene", None)
    if scene is not None and not sip.isdeleted(scene):
        scene.clearSelection()
    win.close()
    win.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    QApplication.processEvents()
