import math

from PyQt6.QtWidgets import (
    QGraphicsView, QScrollBar,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsRectItem,
)
from PyQt6.QtCore import Qt, QPoint, QPointF, QLineF
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPolygon, QFont
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

        # Hide scroll bars — panning via middle-mouse drag
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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
        Overlay drawn on top of all scene content.

        Renders four things (in order):
        1. Snap trace — dashed ghost of the item being snapped to (scene coords).
        2. Grip handles — small squares on selected geometry items (viewport coords).
        3. OSNAP snap indicator — coloured shape at snap point (viewport coords).
        4. Dim HUD — live dimension text near the cursor (viewport coords).
        """
        super().drawForeground(painter, rect)
        scene = self.scene()
        if scene is None:
            return

        snap_result = getattr(scene, "_snap_result", None)

        # ── 1. Snap trace (scene coordinates — no resetTransform) ─────────────
        if snap_result is not None and snap_result.source_item is not None:
            src = snap_result.source_item
            color = QColor(SNAP_COLORS.get(snap_result.snap_type, "#aaaaaa"))
            trace_pen = QPen(color, 1)
            trace_pen.setStyle(Qt.PenStyle.DashLine)
            trace_pen.setCosmetic(True)
            painter.save()
            painter.setPen(trace_pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

            if isinstance(src, QGraphicsLineItem):
                ln = src.line()
                p1 = src.mapToScene(ln.p1())
                p2 = src.mapToScene(ln.p2())
                painter.drawLine(QLineF(p1, p2))
            elif isinstance(src, QGraphicsEllipseItem):
                painter.drawEllipse(src.mapRectToScene(src.rect()))
            elif isinstance(src, QGraphicsPathItem):
                painter.drawPath(src.mapToScene(src.path()))
            elif isinstance(src, QGraphicsRectItem):
                painter.drawRect(src.mapRectToScene(src.rect()))

            painter.restore()

        # ── 2. Grip handles (viewport coordinates) ────────────────────────────
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

        # ── 3. OSNAP snap indicator (viewport coordinates) ────────────────────
        if snap_result is not None:
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
                    QPoint(int(x),     int(y) - s),
                    QPoint(int(x) + s, int(y)),
                    QPoint(int(x),     int(y) + s),
                    QPoint(int(x) - s, int(y)),
                ])
                painter.drawPolygon(poly)
            elif marker == "cross":
                painter.drawLine(int(x) - s, int(y) - s, int(x) + s, int(y) + s)
                painter.drawLine(int(x) + s, int(y) - s, int(x) - s, int(y) + s)

            painter.restore()

        # ── 4. Dim HUD (viewport coordinates, near cursor) ───────────────────
        dim_hint = getattr(scene, "_draw_dim_hint", None)
        vp_cursor = getattr(self, "_last_vp_pos", None)
        if dim_hint and vp_cursor:
            painter.save()
            painter.resetTransform()
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            font = QFont("Consolas", 9)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(dim_hint)
            tx = vp_cursor.x() + 14
            ty = vp_cursor.y() - 6
            # Keep within viewport bounds
            vp_w = self.viewport().width()
            vp_h = self.viewport().height()
            if tx + text_rect.width() + 6 > vp_w:
                tx = vp_cursor.x() - text_rect.width() - 14
            if ty - text_rect.height() < 0:
                ty = vp_cursor.y() + text_rect.height() + 6

            bg_r = text_rect.adjusted(-4, -2, 4, 2).translated(tx, ty - text_rect.height())
            painter.fillRect(bg_r, QColor(0, 0, 0, 190))
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(tx, ty, dim_hint)

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
        elif event.button() == Qt.MouseButton.LeftButton:
            # When clicking on a grip handle the scene will consume the event.
            # However, QGraphicsView starts rubber-band selection before the
            # scene processes the click (grip handles are foreground overlays,
            # not real scene items).  Detect the grip hit here and suppress
            # rubber-band by temporarily switching to NoDrag for this press.
            sc = self.scene()
            if (sc is not None
                    and getattr(sc, "mode", None) is None
                    and hasattr(sc, "_find_grip_hit")):
                scene_pos = self.mapToScene(event.pos())
                if sc._find_grip_hit(scene_pos) is not None:
                    self._grip_press_active = True
                    self.setDragMode(QGraphicsView.DragMode.NoDrag)
                    super().mousePressEvent(event)
                    return
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._last_vp_pos = event.pos()   # used by drawForeground for dim HUD
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
            if getattr(self, "_grip_press_active", False):
                self._grip_press_active = False
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            super().mouseReleaseEvent(event)

    # -----------------------------
    # Tab — exact dimension input
    # -----------------------------

    def focusNextPrevChild(self, next_child: bool) -> bool:
        """Block Qt's built-in Tab focus-traversal when a draw mode is active.

        Without this override Qt consumes Tab for widget focus cycling and it
        never reaches keyPressEvent, so _handle_tab_input() would never fire.
        """
        sc = self.scene()
        if sc is not None and getattr(sc, "mode", None) in (
            "draw_line", "draw_rectangle", "draw_circle",
            "construction_line", "polyline",
        ):
            return False   # let Tab fall through to keyPressEvent
        return super().focusNextPrevChild(next_child)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            sc = self.scene()
            if sc is not None and hasattr(sc, "_handle_tab_input"):
                sc._handle_tab_input()
                event.accept()
                return
        if event.key() == Qt.Key.Key_F:
            self.fit_to_screen()
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Fit to screen ─────────────────────────────────────────────────────

    def fit_to_screen(self):
        """Zoom to fit all scene content within the viewport."""
        sc = self.scene()
        if sc is None:
            return
        rect = sc.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            # Nothing in scene — center on origin
            self.resetTransform()
            self.centerOn(QPointF(0, 0))
            return
        # Add 5% margin
        margin = max(rect.width(), rect.height()) * 0.05
        rect.adjust(-margin, -margin, margin, margin)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fit_to_screen()
            return
        super().mouseDoubleClickEvent(event)
