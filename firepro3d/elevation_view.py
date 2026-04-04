"""
elevation_view.py
=================
QGraphicsView for displaying an ElevationScene.

Provides middle-button pan, scroll-wheel zoom, F to fit, coordinate display.
Matches the interaction patterns from Model_View.py.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QKeySequence, QShortcut

import theme as th


class ElevationView(QGraphicsView):
    """Display widget for an ElevationScene with pan/zoom interaction."""

    cursorMoved = pyqtSignal(str)   # "H: … Z: …"

    def __init__(self, elev_scene, scale_manager=None, parent=None):
        super().__init__(elev_scene, parent)
        self._sm = scale_manager
        self._elev_scene = elev_scene

        # Rendering
        self.setRenderHints(
            self.renderHints() | QPainter.RenderHint.Antialiasing
        )
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )

        # No scrollbars — pan via middle mouse
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Rubber-band drag select (left-click drag)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        # Zoom anchored under mouse
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Pan state
        self._panning = False
        self._pan_start = QPoint()
        self._zoom_factor = 1.15

        # Ctrl+A — select all (excluding gridlines and datums)
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(
            self._select_all_items)

    # ── Select All (filter annotations) ──────────────────────────────────

    def _select_all_items(self):
        from elevation_scene import ElevGridlineItem, ElevDatumItem
        scene = self.scene()
        if scene:
            scene.blockSignals(True)
            for item in scene.items():
                if isinstance(item, (ElevGridlineItem, ElevDatumItem)):
                    continue
                if item.flags() & item.GraphicsItemFlag.ItemIsSelectable:
                    item.setSelected(True)
            scene.blockSignals(False)
            scene.selectionChanged.emit()
            self.viewport().update()

    # ── Grip handle rendering ────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        scene = self.scene()
        if scene is None:
            return

        selected = [i for i in scene.selectedItems() if hasattr(i, "grip_points")]
        if not selected:
            return

        active_item = getattr(scene, "_grip_item", None)
        active_idx = getattr(scene, "_grip_index", -1)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for item in selected:
            for idx, gpt in enumerate(item.grip_points()):
                vp = self.mapFromScene(gpt)
                is_active = (item is active_item and idx == active_idx)
                fill = QColor("#ff4400") if is_active else QColor("#00aaff")
                painter.setPen(QPen(QColor("#000000"), 1))
                painter.setBrush(QBrush(fill))
                painter.drawRect(vp.x() - 4, vp.y() - 4, 8, 8)
        painter.end()

    # ── Pan (middle mouse) ───────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
        else:
            # Emit cursor coordinates
            scene_pos = self.mapToScene(event.pos())
            self._emit_coords(scene_pos)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)

    # ── Zoom (scroll wheel) ──────────────────────────────────────────────

    def wheelEvent(self, event):
        factor = self._zoom_factor if event.angleDelta().y() > 0 else 1.0 / self._zoom_factor
        old_pos = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    # ── Keyboard ─────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F:
            self.fit_to_screen()
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Fit to screen ────────────────────────────────────────────────────

    def fit_to_screen(self):
        """Zoom to fit all scene content with margin."""
        sc = self.scene()
        if sc is None:
            return
        rect = sc.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            return
        margin = max(rect.width(), rect.height()) * 0.1 + 100
        rect.adjust(-margin, -margin, margin, margin)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    # ── Coordinate display ───────────────────────────────────────────────

    def _emit_coords(self, scene_pos: QPointF):
        """Format elevation scene coords as H/Z string for status bar."""
        h = scene_pos.x()
        z = -scene_pos.y()  # elevation scene Y = -Z
        if self._sm and hasattr(self._sm, "format_length"):
            h_str = self._sm.format_length(h)
            z_str = self._sm.format_length(z)
        else:
            h_str = f"{h:.0f} mm"
            z_str = f"{z:.0f} mm"
        self.cursorMoved.emit(f"H: {h_str}  Z: {z_str}")
