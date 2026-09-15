"""Project (per-.fpd) settings dialog — Project Info / Units & Precision.

See docs/specs/settings-dialog.md §4.2.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QStackedWidget, QWidget

from firepro3d.house_dialog import HouseDialog
from firepro3d.settings.panes import ProjectInfoPane, UnitsPane
from firepro3d.ui_kit import SideTabs


class ProjectSettingsDialog(HouseDialog):
    """Per-project settings dialog with Project Info and Units & Precision panes.

    Uses HouseDialog chrome + SideTabs rail + QStackedWidget body.
    """

    _TABS = [
        ("project_info", "Project Info"),
        ("units",        "Units & Precision"),
    ]

    def __init__(
        self,
        *,
        scene,
        get_info: Callable[[], dict],
        set_info: Callable[[dict], None],
        on_changed: Callable[[], None] | None = None,
        parent=None,
    ):
        super().__init__(parent, title="Project Settings", resizable=True,
                         controls=("min", "max", "close"), min_width=560)

        self._scene = scene
        self._panes = {
            "project_info": ProjectInfoPane(get_info=get_info, set_info=set_info),
            "units": UnitsPane(
                scale_manager=scene.scale_manager, on_changed=on_changed
            ),
        }

        body = QWidget()
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)

        self._rail = SideTabs()
        self._stack = QStackedWidget(objectName="detailsPanel")

        for key, label in self._TABS:
            self._rail.add_tab(key, label)
            pane = self._panes[key]
            pane.load()
            self._stack.addWidget(pane)

        self._rail.tabSelected.connect(self._on_rail)
        h.addWidget(self._rail)
        h.addWidget(self._stack, 1)
        self.set_body(body, margin=(0, 0, 0, 0))

        # extra_left is a QWidget (QPushButton subclasses QWidget) — accepted directly
        save_default = QPushButton("Save as default for new projects")
        save_default.clicked.connect(self._on_save_default)
        self.set_footer_buttons(
            primary=("OK", self._on_ok),
            cancel=True,
            extra_left=save_default,
        )

    # ── public ───────────────────────────────────────────────────────────────

    def rail_keys(self) -> list[str]:
        """Return the ordered list of tab keys."""
        return [k for k, _ in self._TABS]

    # ── private ──────────────────────────────────────────────────────────────

    def _on_rail(self, key: str) -> None:
        self._stack.setCurrentIndex(self.rail_keys().index(key))

    def _apply_all(self) -> None:
        for p in self._panes.values():
            p.apply()

    def _on_ok(self) -> None:
        self._apply_all()
        self.accept()

    def _on_save_default(self) -> None:
        # Commit staged edits to the live project first, then persist to template.
        self._apply_all()
        from firepro3d.settings import template
        template.save_current_as_default(self._scene)

    def reject(self) -> None:  # type: ignore[override]
        for p in self._panes.values():
            p.revert()
        super().reject()
