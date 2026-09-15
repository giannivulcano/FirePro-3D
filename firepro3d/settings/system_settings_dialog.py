"""System (app-wide) settings dialog — General/UX/UI/Import.

See docs/specs/settings-dialog.md §4.2.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QStackedWidget, QWidget

from firepro3d.house_dialog import HouseDialog
from firepro3d.settings.panes import GeneralPane, ImportPane, UIPane, UXPane
from firepro3d.ui_kit import SideTabs


class SystemSettingsDialog(HouseDialog):
    """App-wide settings dialog with General / UX / UI / Import panes.

    Uses HouseDialog chrome + SideTabs rail + QStackedWidget body.
    """

    _TABS = [
        ("general", "General"),
        ("ux",      "UX"),
        ("ui",      "UI"),
        ("import",  "Import"),
    ]

    def __init__(
        self,
        *,
        scene=None,
        view=None,
        snap_toolbar=None,
        on_theme_changed=None,
        on_crosshair_changed=None,
        on_immersive_changed=None,
        parent=None,
    ):
        super().__init__(parent, title="System Settings", resizable=True, min_width=620)

        self._panes = {
            "general": GeneralPane(),
            "ux": UXPane(scene=scene, view=view, snap_toolbar=snap_toolbar),
            "ui": UIPane(
                on_theme_changed=on_theme_changed,
                on_crosshair_changed=on_crosshair_changed,
                on_immersive_changed=on_immersive_changed,
            ),
            "import": ImportPane(),
        }

        body = QWidget()
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)

        self._rail = SideTabs()
        self._stack = QStackedWidget()

        for key, label in self._TABS:
            self._rail.add_tab(key, label)
            pane = self._panes[key]
            pane.load()
            self._stack.addWidget(pane)

        self._rail.tabSelected.connect(self._on_rail)
        h.addWidget(self._rail)
        h.addWidget(self._stack, 1)
        self.set_body(body)

        # extra_left is a QWidget (QPushButton subclasses QWidget) — accepted directly
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply_all)
        self.set_footer_buttons(
            primary=("OK", self._on_ok),
            cancel=True,
            extra_left=apply_btn,
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

    def reject(self) -> None:  # type: ignore[override]
        for p in self._panes.values():
            p.revert()
        super().reject()
