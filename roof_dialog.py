"""
roof_dialog.py
==============
Dialog for configuring roof properties before or after placement.
Includes an illustration panel on the right that updates with the
selected roof type.
"""

from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox,
    QComboBox, QDoubleSpinBox, QLineEdit, QLabel, QFrame,
)
from PyQt6.QtGui import QColor, QPixmap, QPainter, QPen, QFont, QPolygonF
from PyQt6.QtCore import Qt, QPointF

from roof import ROOF_TYPES, DEFAULT_PITCH_DEG, DEFAULT_EAVE_HEIGHT_FT, \
    DEFAULT_OVERHANG_FT

# Path where user-supplied images will live (one per roof type).
# If an image file exists it is used; otherwise a programmatic sketch is drawn.
_IMG_DIR = os.path.join(os.path.dirname(__file__), "graphics", "roof_types")

_IMG_W = 220
_IMG_H = 180


def _placeholder_pixmap(roof_type: str) -> QPixmap:
    """Draw a simple schematic cross-section for the given roof type."""
    pix = QPixmap(_IMG_W, _IMG_H)
    pix.fill(QColor("#1e1e1e"))

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    wall_pen = QPen(QColor("#888888"), 2)
    roof_pen = QPen(QColor("#D2B48C"), 2)
    label_pen = QPen(QColor("#aaaaaa"), 1)

    margin = 30
    base_y = _IMG_H - 40
    left = margin
    right = _IMG_W - margin
    mid = _IMG_W // 2
    wall_top = base_y - 60

    # Ground line
    p.setPen(QPen(QColor("#555555"), 1, Qt.PenStyle.DashLine))
    p.drawLine(10, base_y, _IMG_W - 10, base_y)

    # Walls
    p.setPen(wall_pen)
    p.drawLine(left, base_y, left, wall_top)
    p.drawLine(right, base_y, right, wall_top)

    # Roof shape
    p.setPen(roof_pen)
    p.setBrush(QColor(210, 180, 140, 60))

    if roof_type == "flat":
        poly = QPolygonF([
            QPointF(left - 10, wall_top),
            QPointF(right + 10, wall_top),
            QPointF(right + 10, wall_top - 8),
            QPointF(left - 10, wall_top - 8),
        ])
        p.drawPolygon(poly)

    elif roof_type == "gable":
        peak_y = wall_top - 55
        ridge_left = mid - 30
        ridge_right = mid + 30
        # Left slope
        poly = QPolygonF([
            QPointF(left - 10, wall_top),
            QPointF(ridge_left, peak_y),
            QPointF(ridge_right, peak_y),
            QPointF(right + 10, wall_top),
        ])
        p.drawPolygon(poly)
        # Ridge line connecting the two peaks
        ridge_pen_dash = QPen(QColor("#D2B48C"), 2, Qt.PenStyle.DashDotLine)
        p.setPen(ridge_pen_dash)
        p.drawLine(int(ridge_left), int(peak_y), int(ridge_right), int(peak_y))

    elif roof_type == "hip":
        peak_y = wall_top - 50
        ridge_l = mid - 25
        ridge_r = mid + 25
        poly = QPolygonF([
            QPointF(left - 10, wall_top),
            QPointF(ridge_l, peak_y),
            QPointF(ridge_r, peak_y),
            QPointF(right + 10, wall_top),
        ])
        p.drawPolygon(poly)
        # Ridge line
        p.setPen(QPen(QColor("#D2B48C"), 2, Qt.PenStyle.DashDotLine))
        p.drawLine(int(ridge_l), int(peak_y), int(ridge_r), int(peak_y))

    elif roof_type == "shed":
        high_y = wall_top - 50
        poly = QPolygonF([
            QPointF(left - 10, high_y),
            QPointF(right + 10, wall_top),
            QPointF(right + 10, wall_top),
            QPointF(left - 10, high_y),
        ])
        p.drawPolygon(poly)
        p.setPen(roof_pen)
        p.drawLine(int(left - 10), int(high_y), int(right + 10), int(wall_top))

    # Label
    p.setPen(label_pen)
    p.setFont(QFont("Segoe UI", 10))
    p.drawText(0, 0, _IMG_W, 24, Qt.AlignmentFlag.AlignCenter,
               roof_type.capitalize())

    p.end()
    return pix


def _load_or_generate(roof_type: str) -> QPixmap:
    """Try to load a user image; fall back to the programmatic sketch."""
    for ext in ("png", "jpg", "svg"):
        path = os.path.join(_IMG_DIR, f"{roof_type}.{ext}")
        if os.path.isfile(path):
            pm = QPixmap(path)
            if not pm.isNull():
                return pm.scaled(_IMG_W, _IMG_H,
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
    return _placeholder_pixmap(roof_type)


class RoofDialog(QDialog):
    """Modal dialog for setting roof parameters.

    Usage::

        dlg = RoofDialog(parent, levels=level_list)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            params = dlg.get_params()
    """

    def __init__(self, parent=None, *, defaults: dict | None = None,
                 levels: list | None = None, scale_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Roof Properties")
        self.setMinimumWidth(580)
        self._defaults = defaults or {}
        self._levels = levels or []        # list of Level objects
        self._sm = scale_manager
        self._unit_suffix = self._sm.display_unit_suffix() if self._sm else " ft"
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)

        body = QHBoxLayout()

        # ── Left: form ────────────────────────────────────────────────
        left = QVBoxLayout()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name
        self._name_edit = QLineEdit(self._defaults.get("name", ""))
        form.addRow("Name:", self._name_edit)

        # Roof type
        self._type_combo = QComboBox()
        self._type_combo.addItems([t.capitalize() for t in ROOF_TYPES])
        cur_type = self._defaults.get("roof_type", "flat")
        idx = list(ROOF_TYPES).index(cur_type) if cur_type in ROOF_TYPES else 0
        self._type_combo.setCurrentIndex(idx)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Roof Type:", self._type_combo)

        # Pitch / slope
        self._pitch_spin = QDoubleSpinBox()
        self._pitch_spin.setRange(0.0, 89.0)
        self._pitch_spin.setDecimals(1)
        self._pitch_spin.setSuffix("°")
        self._pitch_spin.setValue(self._defaults.get("pitch_deg", DEFAULT_PITCH_DEG))
        form.addRow("Roof Slope:", self._pitch_spin)

        # Eave level (reference level for eave height)
        self._eave_combo = QComboBox()
        default_level = self._defaults.get("level", "")
        if self._levels:
            best_idx = 0
            for i, lvl in enumerate(self._levels):
                label = f"{lvl.name}  ({lvl.elevation:.1f}{self._unit_suffix})"
                self._eave_combo.addItem(label, lvl.elevation)
                if lvl.name == default_level:
                    best_idx = i
            self._eave_combo.setCurrentIndex(best_idx)
        else:
            self._eave_combo.addItem(f"Default  (0.0{self._unit_suffix})", 0.0)
        self._eave_combo.currentIndexChanged.connect(self._on_eave_changed)
        form.addRow("Eave Level:", self._eave_combo)

        # Eave height = level elevation (read-only) + offset
        self._eave_height_spin = QDoubleSpinBox()
        self._eave_height_spin.setRange(0.0, 500.0)
        self._eave_height_spin.setDecimals(2)
        self._eave_height_spin.setSuffix(self._unit_suffix)
        self._eave_height_spin.setReadOnly(True)
        self._eave_height_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._eave_height_spin.setStyleSheet("background: #2a2a2a; color: grey;")
        form.addRow("Eave Height:", self._eave_height_spin)

        # Offset above the selected level
        self._eave_offset_spin = QDoubleSpinBox()
        self._eave_offset_spin.setRange(-500.0, 500.0)
        self._eave_offset_spin.setDecimals(2)
        self._eave_offset_spin.setSuffix(self._unit_suffix)
        self._eave_offset_spin.setValue(
            self._defaults.get("eave_height_ft", DEFAULT_EAVE_HEIGHT_FT))
        self._eave_offset_spin.valueChanged.connect(self._on_eave_changed)
        form.addRow("Offset:", self._eave_offset_spin)

        # Set initial eave height display
        self._on_eave_changed()

        # Overhang
        self._overhang_spin = QDoubleSpinBox()
        self._overhang_spin.setRange(0.0, 100.0)
        self._overhang_spin.setDecimals(2)
        self._overhang_spin.setSuffix(self._unit_suffix)
        self._overhang_spin.setValue(
            self._defaults.get("overhang_ft", DEFAULT_OVERHANG_FT))
        form.addRow("Eave Overhang:", self._overhang_spin)

        # Colour
        self._color_edit = QLineEdit(
            self._defaults.get("color", "#D2B48C"))
        self._color_edit.setPlaceholderText("#RRGGBB")
        form.addRow("Colour:", self._color_edit)

        left.addLayout(form)

        # Pitch hint
        self._pitch_hint = QLabel("")
        self._pitch_hint.setStyleSheet("color: grey; font-size: 11px;")
        left.addWidget(self._pitch_hint)
        left.addStretch()

        body.addLayout(left, 1)

        # ── Right: illustration ───────────────────────────────────────
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._img_label = QLabel()
        self._img_label.setFixedSize(_IMG_W, _IMG_H)
        self._img_label.setFrameShape(QFrame.Shape.StyledPanel)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet(
            "background: #1e1e1e; border: 1px solid #444; border-radius: 4px;")
        right.addWidget(self._img_label)

        body.addLayout(right, 0)
        outer.addLayout(body)

        # Trigger initial image + hint
        self._on_type_changed(self._type_combo.currentIndex())

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_type_changed(self, index: int):
        roof_type = ROOF_TYPES[index]
        is_flat = roof_type == "flat"
        self._pitch_spin.setEnabled(not is_flat)
        if is_flat:
            self._pitch_spin.setValue(0.0)
            self._pitch_hint.setText("Flat roofs have no slope.")
        elif roof_type == "gable":
            self._pitch_hint.setText("Ridge runs along the longest axis.")
        elif roof_type == "hip":
            self._pitch_hint.setText("All edges slope up to a central peak.")
        elif roof_type == "shed":
            self._pitch_hint.setText("First edge is high, opposite is at eave.")

        # Update illustration
        pix = _load_or_generate(roof_type)
        self._img_label.setPixmap(pix)

    def _on_eave_changed(self, *_args):
        level_elev = self._eave_combo.currentData()
        if level_elev is None:
            level_elev = 0.0
        offset = self._eave_offset_spin.value()
        self._eave_height_spin.setValue(level_elev + offset)

    # ── Data retrieval ────────────────────────────────────────────────

    def get_params(self) -> dict:
        """Return a dict of roof parameters."""
        # Extract the level name from the combo
        eave_level_name = ""
        if self._levels:
            idx = self._eave_combo.currentIndex()
            if 0 <= idx < len(self._levels):
                eave_level_name = self._levels[idx].name

        return {
            "name":           self._name_edit.text().strip(),
            "roof_type":      ROOF_TYPES[self._type_combo.currentIndex()],
            "pitch_deg":      self._pitch_spin.value(),
            "eave_height_ft": self._eave_offset_spin.value(),
            "eave_level":     eave_level_name,
            "overhang_ft":    self._overhang_spin.value(),
            "color":          self._color_edit.text().strip() or "#D2B48C",
        }
