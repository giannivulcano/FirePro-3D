"""
roof_dialog.py
==============
Dialog for configuring roof properties before or after placement.
Includes an illustration panel on the right that updates with the
selected roof type.
"""

from __future__ import annotations

import math
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox,
    QComboBox, QDoubleSpinBox, QLineEdit, QLabel, QFrame, QPushButton,
    QColorDialog,
)
from PyQt6.QtGui import QColor, QPixmap, QPainter, QPen, QFont, QPolygonF
from PyQt6.QtCore import Qt, QPointF

from roof import ROOF_TYPES, DEFAULT_PITCH_DEG
from scale_manager import DisplayUnit
from dimension_edit import DimensionEdit

# Path where user-supplied images will live (one per roof type).
_IMG_DIR = os.path.join(os.path.dirname(__file__), "graphics", "roof_types")

_IMG_W = 220
_IMG_H = 180

RIDGE_DIRECTIONS = ("auto", "horizontal", "vertical")


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

    p.setPen(QPen(QColor("#555555"), 1, Qt.PenStyle.DashLine))
    p.drawLine(10, base_y, _IMG_W - 10, base_y)

    p.setPen(wall_pen)
    p.drawLine(left, base_y, left, wall_top)
    p.drawLine(right, base_y, right, wall_top)

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
        poly = QPolygonF([
            QPointF(left - 10, wall_top),
            QPointF(ridge_left, peak_y),
            QPointF(ridge_right, peak_y),
            QPointF(right + 10, wall_top),
        ])
        p.drawPolygon(poly)
        p.setPen(QPen(QColor("#D2B48C"), 2, Qt.PenStyle.DashDotLine))
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
    """Modal dialog for setting roof parameters."""

    def __init__(self, parent=None, *, defaults: dict | None = None,
                 levels: list | None = None, scale_manager=None,
                 level_manager=None):
        super().__init__(parent)
        self.setWindowTitle("Roof Properties")
        self.setMinimumWidth(580)
        self._defaults = defaults or {}
        self._level_manager = level_manager
        if self._level_manager is not None:
            self._levels = self._level_manager.levels
        else:
            self._levels = levels or []
        self._sm = scale_manager
        self._build_ui()

    # ── Helpers ────────────────────────────────────────────────────────

    def _fmt_mm(self, mm: float) -> str:
        """Format a value in mm for display using project units."""
        if self._sm:
            return self._sm.format_length(mm)
        return f"{mm:.1f} mm"

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
        self._pitch_spin.valueChanged.connect(self._on_pitch_changed)
        form.addRow("Roof Slope:", self._pitch_spin)

        # Ridge direction (gable only)
        self._ridge_combo = QComboBox()
        self._ridge_combo.addItems([d.capitalize() for d in RIDGE_DIRECTIONS])
        cur_ridge = self._defaults.get("ridge_direction", "auto")
        ridge_idx = (RIDGE_DIRECTIONS.index(cur_ridge)
                     if cur_ridge in RIDGE_DIRECTIONS else 0)
        self._ridge_combo.setCurrentIndex(ridge_idx)
        form.addRow("Ridge Direction:", self._ridge_combo)

        # Eave level (reference level for eave height)
        self._eave_combo = QComboBox()
        default_level = self._defaults.get("level", "")
        if self._levels:
            best_idx = 0
            for i, lvl in enumerate(self._levels):
                elev_mm = lvl.elevation
                label = f"{lvl.name}  ({self._fmt_mm(elev_mm)})"
                self._eave_combo.addItem(label, lvl.elevation)
                if lvl.name == default_level:
                    best_idx = i
            self._eave_combo.setCurrentIndex(best_idx)
        else:
            self._eave_combo.addItem(f"Default  ({self._fmt_mm(0.0)})", 0.0)
        self._eave_combo.currentIndexChanged.connect(self._on_eave_changed)
        form.addRow("Eave Level:", self._eave_combo)

        # Eave height = level elevation + offset (read-only)
        self._eave_height_label = QLabel()
        self._eave_height_label.setStyleSheet(
            "background: #2a2a2a; color: grey; padding: 4px 6px;"
            " border: 1px solid #555; border-radius: 2px;")
        form.addRow("Eave Height:", self._eave_height_label)

        # Offset above the selected level (DimensionEdit, stores mm)
        offset_mm = self._defaults.get("eave_height_mm", 0.0)
        self._eave_offset_edit = DimensionEdit(
            self._sm, initial_mm=offset_mm)
        self._eave_offset_edit.valueChanged.connect(self._on_eave_changed)
        form.addRow("Offset:", self._eave_offset_edit)

        # Peak height (read-only)
        self._peak_height_label = QLabel()
        self._peak_height_label.setStyleSheet(
            "background: #2a2a2a; color: grey; padding: 4px 6px;"
            " border: 1px solid #555; border-radius: 2px;")
        form.addRow("Peak Height:", self._peak_height_label)

        # Set initial eave/peak height display
        self._on_eave_changed()

        # Overhang (DimensionEdit, stores mm)
        overhang_mm = self._defaults.get("overhang_mm", 0.0)
        self._overhang_edit = DimensionEdit(
            self._sm, initial_mm=overhang_mm)
        form.addRow("Eave Overhang:", self._overhang_edit)

        # Colour picker
        self._color_value = self._defaults.get("color", "#D2B48C")
        self._color_btn = QPushButton()
        self._color_btn.setFixedHeight(28)
        self._update_color_swatch()
        self._color_btn.clicked.connect(self._pick_color)
        form.addRow("Colour:", self._color_btn)

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

        # Trigger initial image + hint + ridge visibility
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
        is_gable = roof_type == "gable"
        self._pitch_spin.setEnabled(not is_flat)
        self._ridge_combo.setEnabled(is_gable)
        if is_flat:
            self._pitch_spin.setValue(0.0)
            self._pitch_hint.setText("Flat roofs have no slope.")
        else:
            if self._pitch_spin.value() == 0.0:
                self._pitch_spin.setValue(DEFAULT_PITCH_DEG)
            if is_gable:
                self._pitch_hint.setText("Ridge runs along the selected axis.")
            elif roof_type == "hip":
                self._pitch_hint.setText("All edges slope up to a central peak.")
            elif roof_type == "shed":
                self._pitch_hint.setText("First edge is high, opposite is at eave.")

        pix = _load_or_generate(roof_type)
        self._img_label.setPixmap(pix)
        self._update_peak_height()

    def _on_eave_changed(self, *_args):
        level_elev_mm = self._eave_combo.currentData()
        if level_elev_mm is None:
            level_elev_mm = 0.0
        offset_mm = self._eave_offset_edit.value_mm()
        total_mm = level_elev_mm + offset_mm
        self._eave_height_label.setText(self._fmt_mm(total_mm))
        self._update_peak_height()

    def _on_pitch_changed(self, *_args):
        self._update_peak_height()

    def _update_peak_height(self):
        """Compute and display estimated peak height."""
        level_elev_mm = self._eave_combo.currentData() or 0.0
        offset_mm = self._eave_offset_edit.value_mm()
        eave_mm = level_elev_mm + offset_mm
        pitch = self._pitch_spin.value()

        if pitch <= 0:
            self._peak_height_label.setText(self._fmt_mm(eave_mm))
            return

        # half_span_mm is computed from the polygon if editing an existing roof
        half_span_mm = self._defaults.get("half_span_mm", 0.0)
        if half_span_mm > 0:
            ridge_rise_mm = half_span_mm * math.tan(math.radians(pitch))
            peak_mm = eave_mm + ridge_rise_mm
            self._peak_height_label.setText(self._fmt_mm(peak_mm))
        else:
            self._peak_height_label.setText("N/A (place roof first)")

    def _update_color_swatch(self):
        self._color_btn.setStyleSheet(
            f"background-color: {self._color_value};"
            f" border: 1px solid #666; border-radius: 3px;")
        self._color_btn.setText(self._color_value)

    def _pick_color(self):
        current = QColor(self._color_value)
        color = QColorDialog.getColor(current, self, "Pick Roof Colour")
        if color.isValid():
            self._color_value = color.name()
            self._update_color_swatch()

    # ── Data retrieval ────────────────────────────────────────────────

    def get_params(self) -> dict:
        """Return a dict of roof parameters (all dimensions in mm)."""
        eave_level_name = ""
        if self._levels:
            idx = self._eave_combo.currentIndex()
            if 0 <= idx < len(self._levels):
                eave_level_name = self._levels[idx].name

        return {
            "name":            self._name_edit.text().strip(),
            "roof_type":       ROOF_TYPES[self._type_combo.currentIndex()],
            "pitch_deg":       self._pitch_spin.value(),
            "ridge_direction": RIDGE_DIRECTIONS[self._ridge_combo.currentIndex()],
            "eave_height_mm":  self._eave_offset_edit.value_mm(),
            "eave_level":      eave_level_name,
            "overhang_mm":     self._overhang_edit.value_mm(),
            "color":           self._color_value,
        }
