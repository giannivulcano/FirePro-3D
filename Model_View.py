import math

from PyQt6.QtWidgets import QGraphicsView, QScrollBar
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPolygon
import theme as th
from snap_engine import SNAP_COLORS, SNAP_MARKERS

class Model_View(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(self.renderHints() | QPainter.RenderHint.Antialiasing)

        # Pan variables
        self._panning = False
        self._pan_start = QPoint()
        self._zoom_factor = 1.15  # Zoom speed multiplier

        # Grid overlay
        self._grid_visible = False
        self._grid_size = 10       # scene-space units between dots

        # Optional: smooth drag
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    # ─────────────────────────────
    # Grid overlay
    # ─────────────────────────────

    def set_grid(self, visible: bool, size: int | None = None):
        """Show / hide the dot grid and optionally update spacing."""
        self._grid_visible = visible
        if size is not None and size > 0:
            self._grid_size = size
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect):
        """Override: draw dot-grid behind scene content when enabled."""
        super().drawBackground(painter, rect)
        if not self._grid_visible:
            return

        grid_px = self._grid_size

        # Skip drawing if dots would be closer than 4 viewport pixels apart
        # (avoids a performance hit at very low zoom levels)
        scale = self.transform().m11()          # horizontal scale factor
        if grid_px * scale < 4.0:
            return

        # Dot colour from theme
        dot_color = QColor(th.detect().grid_dot)

        # Use a cosmetic pen so dots stay the same device-pixel size at all
        # zoom levels. Width=2 makes dots clearly visible without being distracting.
        pen = QPen(dot_color)
        pen.setWidthF(2.0)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        left = math.floor(rect.left()  / grid_px) * grid_px
        top  = math.floor(rect.top()   / grid_px) * grid_px

        x = left
        while x <= rect.right() + grid_px:
            y = top
            while y <= rect.bottom() + grid_px:
                painter.drawPoint(QPointF(x, y))
                y += grid_px
            x += grid_px

    def drawForeground(self, painter: QPainter, rect):
        """
        Overlay drawn in device (viewport) coordinates – not affected by zoom.

        Renders two things:
        1. Grip handles (small cyan squares) on selected geometry items.
        2. OSNAP snap indicator (coloured shape) at the nearest snap point.
        """
        super().drawForeground(painter, rect)
        scene = self.scene()
        if scene is None:
            return

        # ── 1. Grip handles ──────────────────────────────────────────────────
        selected = [i for i in scene.selectedItems() if hasattr(i, "grip_points")]
        active_item  = getattr(scene, "_grip_item",  None)
        active_idx   = getattr(scene, "_grip_index", -1)

        if selected:
            painter.save()
            painter.resetTransform()
            for item in selected:
                for idx, gpt in enumerate(item.grip_points()):
                    vp = self.mapFromScene(gpt)
                    is_active = (item is active_item and idx == active_idx)
                    fill  = QColor("#ff4400") if is_active else QColor("#00aaff")
                    painter.setPen(QPen(QColor("#000000"), 1))
                    painter.setBrush(QBrush(fill))
                    painter.drawRect(vp.x() - 4, vp.y() - 4, 8, 8)
            painter.restore()

        # ── 2. OSNAP snap indicator ───────────────────────────────────────────
        snap_result = getattr(scene, "_snap_result", None)
        if snap_result is None:
            return

        color  = QColor(SNAP_COLORS.get(snap_result.snap_type, "#ffffff"))
        marker = SNAP_MARKERS.get(snap_result.snap_type, "square")
        vp     = self.mapFromScene(snap_result.point)
        x, y   = vp.x(), vp.y()
        s      = 6   # half-size in screen pixels

        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(color, 2)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        if marker == "square":
            painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)

        elif marker == "circle":
            painter.drawEllipse(int(x) - s, int(y) - s, 2 * s, 2 * s)

        elif marker == "triangle":
            poly = QPolygon([
                QPoint(int(x),     int(y) - s),
                QPoint(int(x) + s, int(y) + s),
                QPoint(int(x) - s, int(y) + s),
            ])
            painter.drawPolygon(poly)

        elif marker == "diamond":
            poly = QPolygon([
                QPoint(int(x),         int(y) - s),
                QPoint(int(x) + s,     int(y)),
                QPoint(int(x),         int(y) + s),
                QPoint(int(x) - s,     int(y)),
            ])
            painter.drawPolygon(poly)

        elif marker == "cross":
            painter.drawLine(int(x) - s, int(y) - s, int(x) + s, int(y) + s)
            painter.drawLine(int(x) + s, int(y) - s, int(x) - s, int(y) + s)

        painter.restore()

    # -----------------------------
    # Zoom with mouse wheel
    # -----------------------------
    def wheelEvent(self, event):
        # Zoom in/out
        if event.angleDelta().y() > 0:
            factor = self._zoom_factor
        else:
            factor = 1 / self._zoom_factor

        # Zoom relative to cursor
        cursor_pos = self.mapToScene(event.position().toPoint())
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

        old_pos = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())

    # -----------------------------
    # Pan with middle mouse button
    # -----------------------------
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
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)
