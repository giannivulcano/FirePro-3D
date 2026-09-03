# firepro3d/underlay_controller.py
"""UnderlayController — the underlay/import concern lifted off Model_Space.

Decomposition slice (governing spec: docs/specs/model-space-architecture.md §5).
A PLAIN object (not a QObject): the async worker uses lambda slots and
`underlaysChanged` stays defined on the scene, so no QObject affinity is wanted.
Owns the underlay list, the async DXF worker bridge, and the place_import
transient state; back-references the scene for scene-graph mutation + signal
emission. The freeze controller is NOT owned here — it stays `scene._underlay_freeze`.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF


class UnderlayController:
    def __init__(self, scene):
        self._scene = scene
        self.items: list = []               # was Model_Space.underlays
        self._dxf_worker = None
        self._dxf_progress = None
        self._dxf_import_params = None
        self._place_import_params = None
        self._place_import_ghost = None
        self._place_import_bounds = QRectF(-50, -50, 100, 100)
        self._place_import_preserve_mgmt = None
        self._place_import_remove_old = None

    def reset(self) -> None:
        """Clear the underlay list in place (routes the former `underlays = []`)."""
        self.items = []
