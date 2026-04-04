import math

from PyQt6.QtWidgets import (
    QGraphicsView, QScrollBar, QMenu,
    QGraphicsLineItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsRectItem,
)
from PyQt6.QtCore import Qt, QPoint, QPointF, QLineF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPolygon, QFont
import theme as th
from snap_engine import SNAP_COLORS, SNAP_MARKERS

_DETAIL_BORDER_COLOR = "#4488cc"

class Model_View(QGraphicsView):
    # Emitted when a PDF/DXF file is dropped onto the canvas
    drop_import_requested = pyqtSignal(str)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(self.renderHints() | QPainter.RenderHint.Antialiasing)
        # FullViewportUpdate prevents cosmetic-pen items (gridlines) from
        # being culled at high zoom — Qt can't compute update regions for
        # items with zero scene-unit pen width.
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        # Pan variables
        self._panning = False
        self._pan_start = QPoint()
        self._zoom_factor = 1.15  # Zoom speed multiplier

        # Detail view clip rect (None = no clipping, full plan view)
        self._clip_rect: QRectF | None = None
        self._detail_name: str | None = None

        # Grid overlay
        self._grid_visible = False
        self._grid_size = 10       # scene-space units between dots

        # Hide scroll bars — panning via middle-mouse drag
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Rubber-band selection — only active in select/stretch modes
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        if hasattr(scene, "modeChanged"):
            scene.modeChanged.connect(self._on_mode_changed)

        # Mode-dependent cursor shapes
        _C = Qt.CursorShape
        self._mode_cursors = {
            None:                     _C.ArrowCursor,
            "select":                 _C.ArrowCursor,
            "draw_line":              _C.CrossCursor,
            "draw_rectangle":         _C.CrossCursor,
            "draw_circle":            _C.CrossCursor,
            "draw_arc":               _C.CrossCursor,
            "polyline":               _C.CrossCursor,
            "gridline":               _C.CrossCursor,
            "pipe":                   _C.CrossCursor,
            "sprinkler":              _C.CrossCursor,
            "water_supply":           _C.CrossCursor,
            "dimension":              _C.CrossCursor,
            "text":                   _C.CrossCursor,
            "set_scale":              _C.CrossCursor,
            "construction_line":      _C.CrossCursor,
            "trim":                   _C.CrossCursor,
            "trim_pick":              _C.CrossCursor,
            "extend":                 _C.CrossCursor,
            "extend_pick":            _C.CrossCursor,
            "merge_points":           _C.CrossCursor,
            "constraint_concentric":  _C.CrossCursor,
            "constraint_dimensional": _C.CrossCursor,
            "design_area":            _C.CrossCursor,
            "move":                   _C.SizeAllCursor,
            "paste":                  _C.SizeAllCursor,
            "offset":                 _C.PointingHandCursor,
            "offset_side":            _C.PointingHandCursor,
            "hatch":                  _C.PointingHandCursor,
        }
        if hasattr(scene, "modeChanged"):
            scene.modeChanged.connect(self._on_mode_changed)

        # Accept drag-drop for PDF/DXF import
        self.setAcceptDrops(True)
        self._drop_highlight = False

        # One-time flag for initial zoom on first show
        self._first_show = True

    def _on_mode_changed(self, mode: str):
        """Update viewport cursor to match the active scene mode."""
        if self._panning:
            return
        cursor = self._mode_cursors.get(mode, Qt.CursorShape.ArrowCursor)
        self.setCursor(cursor)

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

        # ── Detail view clip mask ─────────────────────────────────────────
        if self._clip_rect is not None:
            # Draw a semi-opaque mask outside the crop boundary
            mask_color = QColor(scene.backgroundBrush().color())
            mask_color.setAlpha(210)
            painter.setBrush(QBrush(mask_color))
            painter.setPen(Qt.PenStyle.NoPen)

            cr = self._clip_rect
            # Top strip
            if rect.top() < cr.top():
                painter.drawRect(QRectF(rect.left(), rect.top(),
                                        rect.width(), cr.top() - rect.top()))
            # Bottom strip
            if rect.bottom() > cr.bottom():
                painter.drawRect(QRectF(rect.left(), cr.bottom(),
                                        rect.width(), rect.bottom() - cr.bottom()))
            # Left strip (between top and bottom of crop)
            if rect.left() < cr.left():
                painter.drawRect(QRectF(rect.left(), cr.top(),
                                        cr.left() - rect.left(), cr.height()))
            # Right strip
            if rect.right() > cr.right():
                painter.drawRect(QRectF(cr.right(), cr.top(),
                                        rect.right() - cr.right(), cr.height()))

            # Draw crop boundary outline
            crop_pen = QPen(QColor(_DETAIL_BORDER_COLOR), 2, Qt.PenStyle.DashLine)
            crop_pen.setCosmetic(True)
            painter.setPen(crop_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(cr)

        snap_result = getattr(scene, "_snap_result", None)

        # ── 1. Snap trace (scene coordinates — no resetTransform) ─────────────
        if snap_result is not None and snap_result.source_item is not None:
            color = QColor(SNAP_COLORS.get(snap_result.snap_type, "#aaaaaa"))
            trace_pen = QPen(color, 1)
            trace_pen.setStyle(Qt.PenStyle.DashLine)
            trace_pen.setCosmetic(True)
            painter.save()
            painter.setPen(trace_pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

            # Draw all source items (source_item + optional source_item2)
            _sources = [snap_result.source_item]
            _src2 = getattr(snap_result, "source_item2", None)
            if _src2 is not None:
                _sources.append(_src2)
            for src in _sources:
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

        # ── 1b. Floor vertex dots during placement ─────────────────────────────
        floor_active = getattr(scene, "_floor_active", None)
        if floor_active is not None and hasattr(floor_active, "_points"):
            pts = floor_active._points
            if pts:
                painter.save()
                painter.resetTransform()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                for idx, fpt in enumerate(pts):
                    vp = self.mapFromScene(fpt)
                    # First vertex green (close target), others blue
                    if idx == 0 and len(pts) >= 3:
                        fill = QColor("#00cc44")
                    else:
                        fill = QColor("#3399ff")
                    painter.setPen(QPen(QColor("#000000"), 1))
                    painter.setBrush(QBrush(fill))
                    painter.drawEllipse(vp, 5, 5)
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
            elif marker == "right_angle":
                # ⊥ perpendicular symbol: right-angle corner
                painter.drawLine(int(x) - s, int(y), int(x), int(y))
                painter.drawLine(int(x), int(y), int(x), int(y) - s)
                painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)
            elif marker == "tangent_circle":
                # Tangent: small circle with horizontal line through bottom
                painter.drawEllipse(int(x) - s, int(y) - s, 2 * s, 2 * s)
                painter.drawLine(int(x) - s - 2, int(y) + s, int(x) + s + 2, int(y) + s)
            elif marker == "x_cross":
                # Intersection: X inside a square
                painter.drawRect(int(x) - s, int(y) - s, 2 * s, 2 * s)
                painter.drawLine(int(x) - s, int(y) - s, int(x) + s, int(y) + s)
                painter.drawLine(int(x) + s, int(y) - s, int(x) - s, int(y) + s)

            painter.restore()

        # ── 3b. Constraint indicators (viewport coordinates) ───────────────
        constraints = getattr(scene, "_constraints", [])
        if constraints:
            painter.save()
            painter.resetTransform()
            for c in constraints:
                if not c.enabled:
                    continue
                # Only show constraint when one of the constrained items is selected
                if not (c.item_a.isSelected() or c.item_b.isSelected()):
                    continue
                vis = c.visual_points()
                for vtype, vpt in vis:
                    vp = self.mapFromScene(vpt)
                    cx, cy = int(vp.x()), int(vp.y())
                    if vtype == "concentric":
                        # Draw bullseye icon
                        color = QColor("#ff4400") if not c.satisfied else QColor("#00cc44")
                        painter.setPen(QPen(color, 2))
                        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                        painter.drawEllipse(cx - 6, cy - 6, 12, 12)
                        painter.drawEllipse(cx - 3, cy - 3, 6, 6)
                    elif vtype == "dimensional":
                        color = QColor("#ff4400") if not c.satisfied else QColor("#0066cc")
                        # Draw constraint dimension with witness lines
                        try:
                            pa = c.item_a.grip_points()[c.grip_a]
                            pb = c.item_b.grip_points()[c.grip_b]
                            vpa = self.mapFromScene(pa)
                            vpb = self.mapFromScene(pb)
                            # Dimension line
                            painter.setPen(QPen(color, 1.5, Qt.PenStyle.DashLine))
                            painter.drawLine(vpa, vpb)
                            # Witness ticks (short perpendicular marks)
                            import math
                            dx = vpb.x() - vpa.x()
                            dy = vpb.y() - vpa.y()
                            length = math.hypot(dx, dy)
                            if length > 1:
                                nx = -dy / length * 6  # perpendicular, 6px
                                ny = dx / length * 6
                                painter.setPen(QPen(color, 1.5))
                                painter.drawLine(
                                    int(vpa.x() - nx), int(vpa.y() - ny),
                                    int(vpa.x() + nx), int(vpa.y() + ny))
                                painter.drawLine(
                                    int(vpb.x() - nx), int(vpb.y() - ny),
                                    int(vpb.x() + nx), int(vpb.y() + ny))
                            # Distance label at midpoint
                            painter.setFont(QFont("Consolas", 9))
                            painter.setPen(QPen(color))
                            mid_x = int((vpa.x() + vpb.x()) / 2)
                            mid_y = int((vpa.y() + vpb.y()) / 2)
                            painter.drawText(mid_x + 4, mid_y - 4, f"{c.distance:.1f}")
                        except (IndexError, AttributeError):
                            # Fallback: simple "D" square
                            painter.setPen(QPen(color, 2))
                            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                            painter.drawRect(cx - 5, cy - 5, 10, 10)
                            painter.setFont(QFont("Arial", 7))
                            painter.drawText(cx - 3, cy + 3, "D")
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

        # ── 5. Drag-drop overlay (viewport coordinates) ────────────────────
        if getattr(self, "_drop_highlight", False):
            painter.save()
            painter.resetTransform()
            vp = self.viewport().rect()
            painter.setPen(QPen(QColor("#4fa3e0"), 3))
            painter.setBrush(QBrush(QColor(79, 163, 224, 30)))
            painter.drawRect(vp.adjusted(2, 2, -2, -2))
            painter.setFont(QFont("Segoe UI", 14))
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(
                QRectF(vp), Qt.AlignmentFlag.AlignCenter, "Drop to Import"
            )
            painter.restore()

    # ─────────────────────────────
    # Drag & Drop (PDF / DXF import)
    # ─────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile().lower()
                if path.endswith(('.pdf', '.dxf')):
                    event.acceptProposedAction()
                    self._drop_highlight = True
                    self.viewport().update()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(('.pdf', '.dxf')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_highlight = False
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        import os
        self._drop_highlight = False
        self.viewport().update()
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.pdf', '.dxf')):
                if os.path.isfile(path):
                    self.drop_import_requested.emit(path)
                    event.acceptProposedAction()
                    return
        event.ignore()

    # -----------------------------
    # Initial zoom on first show
    # -----------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            # Default view: ~40 m wide, centred on origin
            half_w = 20_000  # 20 m in mm (scene units)
            vp = self.viewport().rect()
            aspect = vp.height() / max(vp.width(), 1)
            half_h = half_w * aspect
            self.fitInView(
                QRectF(-half_w, -half_h, half_w * 2, half_h * 2),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

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
            # Track rubber-band start for crossing selection (stretch mode)
            self._rb_start = event.pos()
            sc = self.scene()
            scene_pos = self.mapToScene(event.pos())

            # When clicking on a grip handle the scene will consume the event.
            # However, QGraphicsView starts rubber-band selection before the
            # scene processes the click (grip handles are foreground overlays,
            # not real scene items).  Detect the grip hit here and suppress
            # rubber-band by temporarily switching to NoDrag for this press.
            if (sc is not None
                    and hasattr(sc, "_find_grip_hit")):
                if sc._find_grip_hit(scene_pos) is not None:
                    self._grip_press_active = True
                    self.setDragMode(QGraphicsView.DragMode.NoDrag)
                    super().mousePressEvent(event)
                    return

            # In select mode, when clicking directly on an item the scene
            # handles selection via _press_select_item.  Suppress
            # rubber-band for this press so the view's mouseReleaseEvent
            # doesn't clear the selection with an empty rubber-band rect.
            if (sc is not None
                    and getattr(sc, "mode", None) in (None, "select")
                    and sc.items(scene_pos)):
                self._item_press_active = True
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
            sc = self.scene()
            mode = getattr(sc, "mode", None) if sc else None
            self.setCursor(self._mode_cursors.get(
                mode, Qt.CursorShape.ArrowCursor))
        elif event.button() == Qt.MouseButton.LeftButton:
            if getattr(self, "_grip_press_active", False) or getattr(self, "_item_press_active", False):
                self._grip_press_active = False
                self._item_press_active = False
                # Only restore rubber-band in modes that use it
                sc = self.scene()
                mode = getattr(sc, "mode", "select") if sc else "select"
                if mode in ("select", "stretch"):
                    self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            # Crossing selection for stretch mode: detect right-to-left drag
            sc = self.scene()
            rb_start = getattr(self, "_rb_start", None)
            if (sc is not None and rb_start is not None
                    and getattr(sc, "mode", None) == "stretch"
                    and getattr(sc, "_stretch_base", None) is None):
                end = event.pos()
                dx = end.x() - rb_start.x()
                dy = end.y() - rb_start.y()
                # Right-to-left drag with enough distance = crossing selection
                if dx < -5 and (abs(dx) > 10 or abs(dy) > 10):
                    tl = self.mapToScene(min(rb_start.x(), end.x()),
                                         min(rb_start.y(), end.y()))
                    br = self.mapToScene(max(rb_start.x(), end.x()),
                                         max(rb_start.y(), end.y()))
                    crossing_rect = QRectF(tl, br).normalized()
                    sc.begin_stretch_crossing(crossing_rect)
            self._rb_start = None
            super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)

    # -----------------------------------------
    # Mode change → toggle rubber-band drag
    # -----------------------------------------

    def _on_mode_changed(self, mode):
        """Disable rubber-band selection during drawing / placement modes
        and switch to crosshair cursor for precise drawing."""
        if mode in ("select", "stretch"):
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)

    # -----------------------------
    # Tab — exact dimension input
    # -----------------------------

    def focusNextPrevChild(self, next_child: bool) -> bool:
        """Always block Qt's built-in Tab focus-traversal so Tab reaches
        keyPressEvent → _handle_tab_input() for all modes (select, draw, wall…)."""
        return False

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
        if event.key() == Qt.Key.Key_G:
            sc = self.scene()
            mode = getattr(sc, "mode", "select") if sc else "select"
            if mode == "select":
                self.set_grid(not self._grid_visible)
                event.accept()
                return
        super().keyPressEvent(event)

    # ── Fit to screen ─────────────────────────────────────────────────────

    def fit_to_screen(self):
        """Zoom to fit all scene content (or clip rect) within the viewport."""
        sc = self.scene()
        if sc is None:
            return
        # Detail views: fit to the crop rect instead of full scene
        if self._clip_rect is not None:
            rect = QRectF(self._clip_rect)
            margin = max(rect.width(), rect.height()) * 0.05
            rect.adjust(-margin, -margin, margin, margin)
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            return
        rect = sc.itemsBoundingRect()
        if rect.isNull() or rect.isEmpty():
            # Nothing in scene — center origin in both X and Y
            self.resetTransform()
            vp = self.viewport().rect()
            w, h = vp.width(), vp.height()
            self.setSceneRect(QRectF(-w / 2, -h / 2, w, h))
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
        # Check for double-click on a dimensional constraint label
        if event.button() == Qt.MouseButton.LeftButton:
            sc = self.scene()
            if sc is not None:
                scene_pos = self.mapToScene(event.pos())
                for c in getattr(sc, "_constraints", []):
                    if not c.enabled or not hasattr(c, "distance"):
                        continue
                    try:
                        pa = c.item_a.grip_points()[c.grip_a]
                        pb = c.item_b.grip_points()[c.grip_b]
                        import math
                        mid_x = (pa.x() + pb.x()) / 2
                        mid_y = (pa.y() + pb.y()) / 2
                        dist = math.hypot(scene_pos.x() - mid_x, scene_pos.y() - mid_y)
                        # Hit test: within ~15 scene units of midpoint
                        scale = self.transform().m11()
                        tol = 15.0 / max(scale, 1e-6)
                        if dist <= tol:
                            from PyQt6.QtWidgets import QInputDialog
                            val, ok = QInputDialog.getDouble(
                                self, "Edit Constraint Distance",
                                "Distance:", c.distance, 0.01, 1_000_000, 3)
                            if ok:
                                c.distance = val
                                sc._solve_constraints()
                                sc.push_undo_state()
                                self.viewport().update()
                            return
                    except (IndexError, AttributeError):
                        pass
        super().mouseDoubleClickEvent(event)

    # ── Right-click context menu ───────────────────────────────────────────

    def contextMenuEvent(self, event):
        scene = self.scene()
        if scene is None:
            return

        # Let the scene handle entity-specific context menus first
        scene_pos = self.mapToScene(event.pos())
        target = scene._find_entity_at(scene_pos) if hasattr(scene, "_find_entity_at") else None
        if target is not None:
            # Delegate to scene's contextMenuEvent
            super().contextMenuEvent(event)
            return

        menu = QMenu(self)
        selected = scene.selectedItems()
        mode = getattr(scene, "mode", None)

        # If in a drawing mode, offer Cancel
        if mode and mode != "select":
            cancel_act = menu.addAction("Cancel")
            cancel_act.triggered.connect(lambda: scene.set_mode("select"))
            menu.addSeparator()

        # Undo / Redo
        undo_act = menu.addAction("Undo")
        undo_act.triggered.connect(scene.undo)
        redo_act = menu.addAction("Redo")
        redo_act.triggered.connect(scene.redo)
        menu.addSeparator()

        # Selection-dependent actions
        if selected:
            hide_act = menu.addAction("Hide")
            hide_act.triggered.connect(lambda: scene._hide_items(list(selected)))
            show_all_act = menu.addAction("Show All Hidden")
            show_all_act.triggered.connect(scene._show_all_hidden)
            menu.addSeparator()
            delete_act = menu.addAction("Delete")
            delete_act.triggered.connect(scene.delete_selected_items)
            copy_act = menu.addAction("Copy")
            copy_act.triggered.connect(scene.copy_selected_items)
            dup_act = menu.addAction("Duplicate")
            dup_act.triggered.connect(lambda: scene.set_mode("duplicate"))
            menu.addSeparator()
            desel_act = menu.addAction("Deselect All")
            desel_act.triggered.connect(scene.clearSelection)
        else:
            show_all_act = menu.addAction("Show All Hidden")
            show_all_act.triggered.connect(scene._show_all_hidden)
            menu.addSeparator()
            sel_all = menu.addAction("Select All")
            sel_all.triggered.connect(self._select_all_items)

        # Paste (if clipboard has data)
        if hasattr(scene, "clipboard_data") and scene.clipboard_data():
            paste_act = menu.addAction("Paste")
            paste_act.triggered.connect(lambda: scene.set_mode("paste"))

        menu.exec(event.globalPos())

    def _select_all_items(self):
        from gridline import GridlineItem
        scene = self.scene()
        if scene:
            scene.blockSignals(True)
            for item in scene.items():
                if isinstance(item, GridlineItem):
                    continue
                if getattr(item, "_exclude_from_bulk_select", False):
                    continue
                if item.flags() & item.GraphicsItemFlag.ItemIsSelectable:
                    item.setSelected(True)
            scene.blockSignals(False)
            scene.selectionChanged.emit()
            self.viewport().update()
