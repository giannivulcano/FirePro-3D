"""
array_dialog.py
===============
Modal dialog for creating linear and polar arrays of selected items.

Includes a live preview that renders lightweight bounding-box outlines
on the canvas as parameters are changed.

Returned by :meth:`get_params` as a plain dict ready for
``Model_Space.array_items()``.
"""

from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QTabWidget, QWidget,
    QLabel, QDoubleSpinBox, QSpinBox, QCheckBox, QDialogButtonBox,
    QAbstractSpinBox, QGraphicsRectItem, QGraphicsEllipseItem,
    QGraphicsItemGroup,
)
from PyQt6.QtGui import QPen, QColor, QBrush, QTransform
from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer

from .dimension_edit import DimensionEdit


_PREVIEW_COLOR = QColor(0, 180, 255, 100)
_PREVIEW_PEN   = QPen(QColor(0, 180, 255, 160), 1, Qt.PenStyle.DashLine)
_PREVIEW_PEN.setCosmetic(True)
_MAX_PREVIEW_COPIES = 200   # cap to avoid sluggishness


class ArrayDialog(QDialog):
    """
    Two-tab dialog for array creation with live canvas preview.

    Linear tab
    ----------
    - Rows  (int ≥ 1)
    - Columns  (int ≥ 1)
    - X Spacing  (float, display units)
    - Y Spacing  (float, display units)

    Polar tab
    ---------
    - Centre X / Y  (float, display units)
    - Count  (int ≥ 2)
    - Total angle  (0 < θ ≤ 360 °)
    - Rotate items checkbox
    """

    def __init__(self, parent=None, scale_manager=None, scene=None,
                 selected_items=None):
        super().__init__(parent)
        self.setWindowTitle("Array")
        self.setMinimumWidth(320)
        self._sm = scale_manager
        self._scene = scene
        self._selected = selected_items or []

        # Compute a combined bounding rect for the selection (scene coords)
        self._sel_rect = QRectF()
        for item in self._selected:
            r = item.sceneBoundingRect()
            self._sel_rect = self._sel_rect.united(r)

        self._preview_items: list = []
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(60)
        self._debounce.timeout.connect(self._update_preview)

        self._build_ui()

        # Initial preview
        QTimer.singleShot(0, self._update_preview)

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._linear_tab(), "Linear")
        self._tabs.addTab(self._polar_tab(),  "Polar")
        self._tabs.currentChanged.connect(self._schedule_preview)
        outer.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _linear_tab(self) -> QWidget:
        w    = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._lin_rows = QSpinBox()
        self._lin_rows.setRange(1, 10_000)
        self._lin_rows.setValue(3)
        self._lin_rows.setSingleStep(1)
        self._lin_rows.valueChanged.connect(self._schedule_preview)

        self._lin_cols = QSpinBox()
        self._lin_cols.setRange(1, 10_000)
        self._lin_cols.setValue(3)
        self._lin_cols.setSingleStep(1)
        self._lin_cols.valueChanged.connect(self._schedule_preview)

        self._lin_xs = DimensionEdit(self._sm, initial_mm=100.0)
        self._lin_xs.valueChanged.connect(self._schedule_preview)

        self._lin_ys = DimensionEdit(self._sm, initial_mm=100.0)
        self._lin_ys.valueChanged.connect(self._schedule_preview)

        form.addRow("Rows:",      self._lin_rows)
        form.addRow("Columns:",   self._lin_cols)
        form.addRow("X Spacing:", self._lin_xs)
        form.addRow("Y Spacing:", self._lin_ys)

        note = QLabel(
            "<small>Spacing is measured from the <em>origin</em> of each copy.<br>"
            "Negative spacing arrays in the opposite direction.</small>"
        )
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _polar_tab(self) -> QWidget:
        w    = QWidget()
        form = QFormLayout(w)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._pol_cx = QDoubleSpinBox()
        self._pol_cx.setRange(-1_000_000, 1_000_000)
        self._pol_cx.setValue(0)
        self._pol_cx.setDecimals(2)
        self._pol_cx.valueChanged.connect(self._schedule_preview)

        self._pol_cy = QDoubleSpinBox()
        self._pol_cy.setRange(-1_000_000, 1_000_000)
        self._pol_cy.setValue(0)
        self._pol_cy.setDecimals(2)
        self._pol_cy.valueChanged.connect(self._schedule_preview)

        self._pol_count = QSpinBox()
        self._pol_count.setRange(2, 10_000)
        self._pol_count.setValue(6)
        self._pol_count.valueChanged.connect(self._schedule_preview)

        self._pol_angle = QDoubleSpinBox()
        self._pol_angle.setRange(0.1, 360.0)
        self._pol_angle.setValue(360.0)
        self._pol_angle.setDecimals(1)
        self._pol_angle.setSuffix("  °")
        self._pol_angle.valueChanged.connect(self._schedule_preview)

        self._pol_rotate = QCheckBox("Rotate items to follow arc")
        self._pol_rotate.setChecked(True)
        self._pol_rotate.toggled.connect(self._schedule_preview)

        form.addRow("Centre X:",    self._pol_cx)
        form.addRow("Centre Y:",    self._pol_cy)
        form.addRow("Count:",       self._pol_count)
        form.addRow("Total angle:", self._pol_angle)
        form.addRow("",             self._pol_rotate)
        return w

    # ── Preview ──────────────────────────────────────────────────────────────

    def _schedule_preview(self, *_args):
        """Debounce preview updates so rapid spin changes stay smooth."""
        self._debounce.start()

    def _clear_preview(self):
        """Remove all preview items from the scene."""
        if self._scene is None:
            return
        for item in self._preview_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._preview_items.clear()

    def _update_preview(self):
        """Regenerate lightweight preview outlines on the canvas."""
        self._clear_preview()
        if self._scene is None or self._sel_rect.isNull():
            return

        rect = self._sel_rect
        pen = _PREVIEW_PEN
        brush = QBrush(QColor(0, 180, 255, 30))

        if self._tabs.currentIndex() == 0:
            self._preview_linear(rect, pen, brush)
        else:
            self._preview_polar(rect, pen, brush)

        # Refresh viewport
        for v in self._scene.views():
            v.viewport().update()

    def _preview_linear(self, rect: QRectF, pen, brush):
        rows = self._lin_rows.value()
        cols = self._lin_cols.value()
        xs = self._lin_xs.value_mm()
        ys = self._lin_ys.value_mm()

        count = 0
        for r in range(rows):
            for c in range(cols):
                if r == 0 and c == 0:
                    continue
                if count >= _MAX_PREVIEW_COPIES:
                    return
                offset_x = c * xs
                offset_y = -r * ys
                preview = QGraphicsRectItem(
                    rect.x() + offset_x,
                    rect.y() + offset_y,
                    rect.width(),
                    rect.height(),
                )
                preview.setPen(pen)
                preview.setBrush(brush)
                preview.setZValue(999)
                self._scene.addItem(preview)
                self._preview_items.append(preview)
                count += 1

    def _preview_polar(self, rect: QRectF, pen, brush):
        cx = self._to_scene(self._pol_cx.value())
        cy = self._to_scene(self._pol_cy.value())
        count = max(2, self._pol_count.value())
        ta = self._pol_angle.value()

        if abs(ta - 360) < 0.01:
            step = math.radians(ta / count)
        else:
            step = math.radians(ta / (count - 1))

        # Centre of selection
        sel_cx = rect.center().x()
        sel_cy = rect.center().y()

        drawn = 0
        for i in range(1, count):
            if drawn >= _MAX_PREVIEW_COPIES:
                return
            angle = step * i
            cos_a, sin_a = math.cos(angle), math.sin(angle)

            # Rotate selection centre around (cx, cy)
            ox = sel_cx - cx
            oy = sel_cy - cy
            new_cx = cx + ox * cos_a - oy * sin_a
            new_cy = cy + ox * sin_a + oy * cos_a

            preview = QGraphicsRectItem(
                new_cx - rect.width() / 2,
                new_cy - rect.height() / 2,
                rect.width(),
                rect.height(),
            )
            preview.setPen(pen)
            preview.setBrush(brush)
            preview.setZValue(999)

            if self._pol_rotate.isChecked():
                preview.setTransformOriginPoint(preview.boundingRect().center())
                preview.setRotation(math.degrees(angle))

            self._scene.addItem(preview)
            self._preview_items.append(preview)
            drawn += 1

        # Draw centre marker
        r = 6
        marker = QGraphicsEllipseItem(cx - r, cy - r, 2 * r, 2 * r)
        marker.setPen(QPen(QColor(255, 100, 0, 200), 2))
        marker.setBrush(QBrush(QColor(255, 100, 0, 60)))
        marker.setZValue(999)
        self._scene.addItem(marker)
        self._preview_items.append(marker)

    # ── Cleanup on close ─────────────────────────────────────────────────────

    def done(self, result):
        """Override to ensure preview is always cleaned up."""
        self._debounce.stop()
        self._clear_preview()
        super().done(result)

    # ── Result ────────────────────────────────────────────────────────────────

    def _to_scene(self, val: float) -> float:
        """Convert display-unit value to scene units."""
        if self._sm:
            return self._sm.display_to_scene(val)
        return val

    def get_params(self) -> dict:
        """Return dialog settings as a dict for ``Model_Space.array_items()``."""
        if self._tabs.currentIndex() == 0:
            return {
                "mode":      "linear",
                "rows":      self._lin_rows.value(),
                "cols":      self._lin_cols.value(),
                "x_spacing": self._lin_xs.value_mm(),
                "y_spacing": self._lin_ys.value_mm(),
            }
        else:
            return {
                "mode":         "polar",
                "cx":           self._to_scene(self._pol_cx.value()),
                "cy":           self._to_scene(self._pol_cy.value()),
                "count":        self._pol_count.value(),
                "total_angle":  self._pol_angle.value(),
                "rotate_items": self._pol_rotate.isChecked(),
            }
