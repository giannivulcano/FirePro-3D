"""Modal NFPA design-point picker.

Wraps the interactive DensityAreaGraph from the auto-populate dialog so a
Room's Protection Criteria can select (area, density) on the hazard curve.
"""

from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QVBoxLayout)

from .auto_populate_dialog import DensityAreaGraph


class DesignPointDialog(QDialog):
    """Pick a design point on the active hazard's density/area curve."""

    def __init__(self, hazard: str, current: tuple[float, float] | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Design Point")
        self._point: tuple[float, float] | None = current

        lay = QVBoxLayout(self)
        self._graph = DensityAreaGraph()
        self._graph.set_active_hazard(hazard)
        if current:
            self._graph.set_selected_point(current[0], current[1])
        self._graph.pointSelected.connect(self._on_point)
        lay.addWidget(self._graph)

        self._lbl = QLabel(self._fmt())
        lay.addWidget(self._lbl)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _fmt(self) -> str:
        if not self._point:
            return "Click the curve to select a design point."
        area, dens = self._point
        return f"Selected: {area:.0f} sq ft @ {dens:.3f} gpm/ft²"

    def _on_point(self, density: float, area: float):
        self._point = (area, density)
        self._lbl.setText(self._fmt())

    def selected_point(self) -> tuple[float, float] | None:
        return self._point
