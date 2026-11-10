"""Shown MainWindow with placed section tabs (elevation-parity guards).

Real entry points only: the section tab is current and focused, context menus
are real QContextMenuEvents posted to the view (QMenu.exec captured), and the
Model Browser menu is its own ``customContextMenuRequested`` slot. Events are
posted with sendEvent, never QTest.mouseMove (that moves the real cursor).
"""
from PyQt6.QtWidgets import QApplication


def settle(scene):
    """Stop *scene*'s debounced rebuild and rebuild now (a forced rebuild)."""
    scene._rebuild_timer.stop()
    scene.rebuild()
    QApplication.processEvents()
