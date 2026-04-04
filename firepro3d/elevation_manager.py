"""
elevation_manager.py
====================
Creates and manages elevation view tabs in the central tab widget.

Each direction (North/South/East/West) gets at most one tab.  Opening an
already-open direction switches to its existing tab.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QTabWidget
from PyQt6.QtCore import QTimer

from .elevation_scene import ElevationScene
from .elevation_view import ElevationView

if TYPE_CHECKING:
    from .model_space import Model_Space
    from .level_manager import LevelManager
    from .scale_manager import ScaleManager


class ElevationManager:
    """Manages elevation view tabs (one per compass direction).

    Parameters
    ----------
    model_space : Model_Space
        Legacy 2D scene (data source).
    level_manager : LevelManager
        Shared level / elevation lookup.
    scale_manager : ScaleManager
        Coordinate conversion.
    tab_widget : QTabWidget
        Central tab widget where elevation tabs are added.
    """

    def __init__(self, model_space: "Model_Space",
                 level_manager: "LevelManager",
                 scale_manager: "ScaleManager",
                 tab_widget: QTabWidget):
        self._ms = model_space
        self._lm = level_manager
        self._sm = scale_manager
        self._tabs = tab_widget

        # direction → (ElevationScene, ElevationView, tab_index)
        self._views: dict[str, tuple[ElevationScene, ElevationView]] = {}

    def open_elevation(self, direction: str) -> ElevationView:
        """Open or switch to an elevation view tab for *direction*.

        Returns the ElevationView widget.
        """
        direction = direction.lower()
        tab_name = f"Elevation: {direction.title()}"

        # If already open, just switch to it
        if direction in self._views:
            scene, view = self._views[direction]
            for i in range(self._tabs.count()):
                if self._tabs.widget(i) is view:
                    self._tabs.setCurrentIndex(i)
                    return view
            # Tab was removed externally — recreate
            del self._views[direction]

        # Create new scene + view
        scene = ElevationScene(direction, self._ms, self._lm, self._sm)
        view = ElevationView(scene, self._sm)
        scene.rebuild()

        idx = self._tabs.addTab(view, tab_name)
        self._tabs.setCurrentIndex(idx)

        # Fit after the widget is shown and has a valid size
        QTimer.singleShot(50, view.fit_to_screen)

        self._views[direction] = (scene, view)
        return view

    def close_elevation(self, direction: str):
        """Close the elevation tab for *direction*."""
        direction = direction.lower()
        entry = self._views.pop(direction, None)
        if entry is None:
            return
        scene, view = entry
        for i in range(self._tabs.count()):
            if self._tabs.widget(i) is view:
                self._tabs.removeTab(i)
                break

    def close_all(self):
        """Close all elevation tabs."""
        for d in list(self._views.keys()):
            self.close_elevation(d)

    def get_view(self, direction: str) -> ElevationView | None:
        entry = self._views.get(direction.lower())
        return entry[1] if entry else None

    def get_scene(self, direction: str) -> ElevationScene | None:
        entry = self._views.get(direction.lower())
        return entry[0] if entry else None

    @property
    def open_directions(self) -> list[str]:
        return list(self._views.keys())

    def rebuild_all(self):
        """Rebuild all open elevation scenes (e.g. after level changes)."""
        for scene, view in self._views.values():
            scene.rebuild()
