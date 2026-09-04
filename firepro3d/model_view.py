import math

from PyQt6.QtWidgets import (
    QGraphicsView, QScrollBar, QMenu, QGraphicsItem,
)
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QEvent, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QKeyEvent
from . import theme as th
from .snap_engine import paint_snap_indicator

_DETAIL_BORDER_COLOR = "#4488cc"

# Sentinel for place_dynamic_input: "reposition, do not re-latch the anchor".
# Distinct from None, which explicitly clears the anchor back to cursor-relative.
_KEEP_ANCHOR = object()

class Model_View(QGraphicsView):
    # Emitted when a PDF/DXF/DWG file is dropped onto the canvas
    drop_import_requested = pyqtSignal(str)

    # Gap between the cursor and the dynamic-input HUD, matching the offset
    # drawForeground uses for the painted Dim HUD the widget replaces.
    _DYN_INPUT_OFFSET = 14

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(self.renderHints() | QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)

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
            "polygon":                _C.CrossCursor,
            "draw_gridline":          _C.CrossCursor,
            "pipe":                   _C.CrossCursor,
            "sprinkler":              _C.CrossCursor,
            "water_supply":           _C.CrossCursor,
            "dimension":              _C.CrossCursor,
            "text":                   _C.CrossCursor,
            "set_scale":              _C.CrossCursor,
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

        Renders (in order):
        1. Snap trace + OSNAP marker — dashed ghost of the snapped item(s) plus
           the coloured snap-point glyph, both from the shared paint_snap_indicator
           (see snap_engine) so this view and the import-dialog preview match.
        2. Grip handles — small squares on selected geometry items (viewport coords).
        3. Dim HUD — live dimension text near the cursor (viewport coords).

        Note: the snap trace+marker draw BEFORE grip handles (the shared painter
        emits them together). During a snapped grip-drag (snapping is active when
        ``mode != "select"`` OR ``_grip_dragging``) the marker and the active grip
        square co-occur at the snap point; the grip then paints over the marker
        centre. This overlap is cosmetic (the marker outline still rings the grip)
        and was accepted when the painter was unified.
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

        # ── 1. Snap trace + marker (shared painter — see snap_engine) ─────────
        # Trace (dashed scene-coord ghost of the snapped item(s)) and the
        # colour-coded marker glyph are drawn by the one shared function so the
        # main plan view and the import-dialog preview stay pixel-identical.
        paint_snap_indicator(painter, self, snap_result)

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
            _sel_t = th.detect()
            _manip = getattr(scene, "_manipulator", None)
            from PyQt6 import sip
            if _manip is not None and sip.isdeleted(_manip):
                _manip = None
            for item in selected:
                # A box-native item shows the manipulator's own resize handles;
                # its parametric grips must not also draw (double handles).
                if _manip is not None and _manip.provides_handles_for(item):
                    continue
                for idx, gpt in enumerate(item.grip_points()):
                    # Don't render a handle for a grip that can't be picked
                    # (e.g. a hidden gridline bubble) — mirrors _find_grip_hit.
                    if hasattr(item, "grip_hittable") and not item.grip_hittable(idx):
                        continue
                    vp = self.mapFromScene(gpt)
                    is_active = (item is active_item and idx == active_idx)
                    fill = QColor(_sel_t.selection_active if is_active else _sel_t.selection)
                    painter.setPen(QPen(QColor(_sel_t.selection), 1))
                    painter.setBrush(QBrush(fill))
                    painter.drawRect(vp.x() - 4, vp.y() - 4, 8, 8)
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

        # ── 3c. Gridline spacing dimensions (viewport coordinates) ────────
        spacing_dims = getattr(scene, '_gridline_spacing_dims', [])
        # Cache for double-click hit detection (dims may be cleared by
        # the second press of a double-click before the event fires).
        # Keep old cache for 1 paint cycle so the double-click handler
        # can still find them after deselection clears the scene list.
        if spacing_dims:
            self._last_spacing_dims = list(spacing_dims)
            self._spacing_cache_age = 0
        else:
            age = getattr(self, '_spacing_cache_age', 0) + 1
            self._spacing_cache_age = age
            if age > 2:
                self._last_spacing_dims = []
        if spacing_dims:
            painter.save()
            painter.resetTransform()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for dim in spacing_dims:
                vp_from = self.mapFromScene(dim["from_pt"])
                vp_to = self.mapFromScene(dim["to_pt"])
                color = QColor("#0066cc")

                # Dashed dimension line
                painter.setPen(QPen(color, 1.5, Qt.PenStyle.DashLine))
                painter.drawLine(vp_from, vp_to)

                # Witness ticks
                dx = vp_to.x() - vp_from.x()
                dy = vp_to.y() - vp_from.y()
                length = math.hypot(dx, dy)
                if length > 1:
                    nx = -dy / length * 6
                    ny = dx / length * 6
                    painter.setPen(QPen(color, 1.5))
                    for vp in (vp_from, vp_to):
                        painter.drawLine(
                            int(vp.x() - nx), int(vp.y() - ny),
                            int(vp.x() + nx), int(vp.y() + ny))

                # Distance label
                mid = QPointF(
                    (vp_from.x() + vp_to.x()) / 2,
                    (vp_from.y() + vp_to.y()) / 2)
                sm = getattr(scene, 'scale_manager', None)
                text = (sm.scene_to_display(dim["distance"])
                        if sm else f"{dim['distance']:.1f}")
                painter.setPen(QPen(color))
                font = painter.font()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(int(mid.x()) + 4, int(mid.y()) - 4, text)
            painter.restore()

        # ── 4. Dim HUD (viewport coordinates, near cursor) ───────────────────
        # Only for modes the ``DynamicInputHud`` widget does not serve yet.
        # One HUD, not two (decision S1): a mode with an applier gets the
        # widget and leaves ``_draw_dim_hint`` unset, so the exclusion is
        # enforced at the one place that assigns the string
        # (``Model_Space.publish_placement_state``) rather than by a second
        # test here that could drift away from it.
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

        # ── 6. ALIGN acquire-and-track overlay ──────────────────────────
        # Two layers: the live result's tracking vectors (dashed, from the
        # participating rays carried on ``source_lines``) and the acquired-set
        # ``+`` markers.  Both paint in VIEWPORT coords like the OSNAP glyph
        # block so the dash + glyph size stay pixel-constant at any zoom.
        # Gated on the master ALIGN toggle as well as the controller's
        # existence: set_align_enabled(False) clears ``_align_result`` (vectors
        # stop) but NOT ``_align_controller.acquired``, so without this gate an
        # F11-off with points already acquired would strand the ``+`` markers on
        # screen until the next mode change.  The gate also cheaply short-circuits
        # the (already-empty) vectors path.
        ctrl = getattr(scene, "_align_controller", None)
        if ctrl is not None and scene.get_align_enabled():
            from .constants import (ALIGN_GUIDE_COLOR, ALIGN_GUIDE_DASH,
                                    ALIGN_GLYPH_PX, ALIGN_ACQUIRE_COLOR)
            align_res = getattr(scene, "_align_result", None)
            src_lines = getattr(align_res, "source_lines", None) if align_res else None
            # Dashed viewport-spanning tracking vectors for the live result.
            if src_lines:
                gpen = QPen(QColor(ALIGN_GUIDE_COLOR), 1)
                gpen.setCosmetic(True)
                gpen.setDashPattern(ALIGN_GUIDE_DASH)
                painter.save()
                painter.setPen(gpen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                for ln in src_lines:
                    painter.drawLine(ln)      # scene-coord QLineF, cosmetic pen
                painter.restore()
            # '+' acquired markers (viewport coords).
            acquired = ctrl.acquired_points()
            if acquired:
                painter.save()
                painter.resetTransform()
                plus_pen = QPen(QColor(ALIGN_ACQUIRE_COLOR), 1)
                plus_pen.setCosmetic(True)
                painter.setPen(plus_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                r = ALIGN_GLYPH_PX
                for pt in acquired:
                    vp = self.mapFromScene(QPointF(pt[0], pt[1]))
                    painter.drawLine(QPointF(vp.x() - r, vp.y()),
                                     QPointF(vp.x() + r, vp.y()))
                    painter.drawLine(QPointF(vp.x(), vp.y() - r),
                                     QPointF(vp.x(), vp.y() + r))
                painter.restore()

        # ── 7. Gridline array/offset ghost preview (scene-coord dashed lines) ──
        ghost = getattr(scene, "_replicate_ghost", None)
        if ghost:
            from .constants import ALIGN_GUIDE_COLOR
            gp = QPen(QColor(ALIGN_GUIDE_COLOR), 1)
            gp.setCosmetic(True)
            gp.setDashPattern([3.0, 3.0])
            painter.save()
            painter.setPen(gp)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            for (o, f) in ghost:
                painter.drawLine(o, f)
            painter.restore()

        # ── 8. Move/paste ghost silhouette (scene-coord cosmetic outline) ──
        mghost = getattr(scene, "_move_ghost", None)
        if mghost:
            from .constants import ALIGN_GUIDE_COLOR
            mp = QPen(QColor(ALIGN_GUIDE_COLOR), 1)
            mp.setCosmetic(True)
            painter.save()
            painter.setPen(mp)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for path in mghost:
                painter.drawPath(path)
            painter.restore()

    # ─────────────────────────────
    # Drag & Drop (PDF / DXF import)
    # ─────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile().lower()
                if path.endswith(('.pdf', '.dxf', '.dwg')):
                    event.acceptProposedAction()
                    self._drop_highlight = True
                    self.viewport().update()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(('.pdf', '.dxf', '.dwg')):
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
            if path.lower().endswith(('.pdf', '.dxf', '.dwg')):
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
        # Pure horizontal scroll (trackpad swipe) is not a zoom — bail before
        # freezing or scaling.
        if event.angleDelta().y() == 0:
            return
        # Freeze-blit the underlays for the gesture BEFORE the transform
        # changes (capture must be at pre-gesture resolution).
        sc = self.scene()
        if sc is not None and hasattr(sc, "_underlay_freeze"):
            sc._underlay_freeze.begin(self)
        # Zoom in/out
        if event.angleDelta().y() > 0:
            factor = self._zoom_factor
        else:
            factor = 1 / self._zoom_factor

        # Zoom relative to cursor
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

        old_pos = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        new_pos = self.mapToScene(event.position().toPoint())
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())
        # scale()/translate() change the transform without scrolling, so
        # scrollContentsBy does not always fire — re-place explicitly.
        self._reposition_dynamic_input()

    # -----------------------------
    # Pan with middle mouse button
    # -----------------------------
    def mousePressEvent(self, event):
        sc = self.scene()
        hud = getattr(sc, "dynamic_input", None) if sc is not None else None
        if hud is not None and sc.is_input_mode():
            # Gated on input mode, not on the HUD existing: under decision S1 a
            # HUD is on screen for the whole placement, and while it is only a
            # readout this press is an ordinary canvas click that must reach the
            # scene and commit.
            #
            # Once a field is engaged, the scene's handlers already make the
            # press inert for geometry, but Qt assigns click-focus in
            # QApplication::notify before any of them run, so the HUD loses the
            # keyboard regardless.  Take it back here — while a field is
            # engaged, Ctrl+Z belongs to the text field, not to the scene's undo
            # stack.  Middle-button panning is still armed: navigating the
            # canvas while typing is expected.
            if event.button() == Qt.MouseButton.MiddleButton:
                self._panning = True
                self._pan_start = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            hud.restore_focus()
            event.accept()
            return
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
                    and hasattr(sc, "_tools")):
                if sc._tools._find_grip_hit(scene_pos) is not None:
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
            # Lazy begin-on-first-move: a middle-click that never drags
            # freezes nothing; later moves hit the frozen fast path and
            # just extend the settle timer.
            sc = self.scene()
            if sc is not None and hasattr(sc, "_underlay_freeze"):
                sc._underlay_freeze.begin(self)
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
            # Pan release = definitive gesture end -> immediate crisp
            # restore (wheel zoom keeps the settle timer instead).
            if sc is not None and hasattr(sc, "_underlay_freeze"):
                sc._underlay_freeze.end()
            mode = getattr(sc, "mode", None) if sc else None
            self.setCursor(self._mode_cursors.get(
                mode, Qt.CursorShape.ArrowCursor))
        elif event.button() == Qt.MouseButton.LeftButton:
            if getattr(self, "_grip_press_active", False):
                self._grip_press_active = False
                # Restore rubber-band in modes that use it
                sc = self.scene()
                mode = getattr(sc, "mode", "select") if sc else "select"
                if mode in ("select", "stretch"):
                    self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            else:
                # If this was a click (not a drag), temporarily suppress
                # rubber-band so Qt doesn't deselect everything with an
                # empty rubber-band rect.  The scene's press handler
                # already handled item selection.
                rb_start = getattr(self, "_rb_start", None)
                if rb_start is not None:
                    dist = (event.pos() - rb_start).manhattanLength()
                    if dist < 5:
                        self.setDragMode(QGraphicsView.DragMode.NoDrag)
                        super().mouseReleaseEvent(event)
                        sc = self.scene()
                        mode = getattr(sc, "mode", "select") if sc else "select"
                        if mode in ("select", "stretch"):
                            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
                        self._rb_start = None
                        return
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
                    sc._tools.begin_stretch_crossing(crossing_rect)
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
        """Block Qt's built-in Tab focus-traversal so Tab stays on the canvas.

        Without this, Tab walks the focus chain out of the view and into the
        ribbon.  That matters in two places: ``keyPressEvent`` needs Tab to
        engage the dynamic-input HUD, and once the HUD is open its own Tab
        field-cycling must not lose focus to a ribbon widget mid-edit.

        Args:
            next_child: Qt's traversal direction; ignored, both are blocked.

        Returns:
            False always, meaning "focus was not moved".
        """
        return False

    # Single-key drawing-tool shortcuts.  Scene-focus-gated by construction:
    # they live on the view, so they never fire while a HUD field or another
    # widget holds focus, and they are *bare* keys — Ctrl/Shift combinations fall
    # through to their own bindings (select-all, copy, the Shift+G grid toggle).
    _TOOL_SHORTCUTS = {
        Qt.Key.Key_L: "draw_line",
        Qt.Key.Key_R: "draw_rectangle",
        Qt.Key.Key_C: "draw_circle",
        Qt.Key.Key_A: "draw_arc",
        Qt.Key.Key_G: "draw_gridline",
        # TODO: K is a PLACEHOLDER for polyline — remove once Line+Polyline merge
        # into one cycle tool (polyline becomes a Line variant, no own shortcut).
        Qt.Key.Key_K: "polyline",
        Qt.Key.Key_P: "polygon",
        Qt.Key.Key_W: "wall",
        Qt.Key.Key_F: "floor",
    }

    def event(self, ev: QEvent) -> bool:
        """Accept the Delete ShortcutOverride during polyline placement.

        The window-level ``QShortcut(Delete)`` in ``main.py`` fires
        ``delete_selected_items`` and suppresses delivery of the KeyPress event
        to the scene, so ``Model_Space.keyPressEvent``'s Delete branch (which
        calls ``_delete_or_pop_polyline_vertex``) is never reached.  Accepting
        the ShortcutOverride here makes Qt skip the window shortcut and deliver
        a plain KeyPress to the view instead, which ``QGraphicsView`` forwards
        to the scene as normal.

        The accept is conditional: it only applies when an in-progress polyline
        exists (``mode == "polyline"`` and ``_polyline_active`` is not None), so
        Delete still fires ``delete_selected_items`` in every other context.

        Args:
            ev: The event to handle.

        Returns:
            True if the event was consumed; otherwise delegates to super.
        """
        if (ev.type() == QEvent.Type.ShortcutOverride
                and isinstance(ev, QKeyEvent)
                and ev.key() == Qt.Key.Key_Delete):
            sc = self.scene()
            if (getattr(sc, "mode", None) == "polyline"
                    and getattr(sc, "_polyline_active", None) is not None):
                ev.accept()
                return True
            # Floor polygon placement pops its last vertex on Delete too.
            if (getattr(sc, "mode", None) == "floor"
                    and getattr(sc, "_floor_active", None) is not None):
                ev.accept()
                return True
        return super().event(ev)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            sc = self.scene()
            # Tab engages the on-canvas HUD.  The event is accepted only when
            # the scene actually opened one: a refused engage (no schema, or a
            # placement schema with no anchor) must leave Tab free to reach
            # whatever else the key is bound to.
            if (sc is not None and hasattr(sc, "begin_dynamic_input")
                    and sc.begin_dynamic_input()):
                event.accept()
                return
        if (event.modifiers() == Qt.KeyboardModifier.NoModifier
                and event.key() in self._TOOL_SHORTCUTS):
            sc = self.scene()
            if sc is not None and hasattr(sc, "set_mode"):
                sc.set_mode(self._TOOL_SHORTCUTS[event.key()])
                event.accept()
                return
        # Note: bare F is a tool shortcut (floor) handled above; Fit-to-Screen
        # is reached via the ribbon "Fit to Screen" button.
        super().keyPressEvent(event)

    def scrollContentsBy(self, dx, dy):  # noqa: N802 (Qt naming)
        """Keep the HUD beside its anchor when the view scrolls.

        ``QAbstractScrollArea`` scrolls *child widgets* along with the
        content, so a viewport-parented HUD is dragged by every pan and walks
        off the screen after a few of them.  Repositioning from the latched
        scene anchor overrides that with an absolute move.
        """
        super().scrollContentsBy(dx, dy)
        self._reposition_dynamic_input()

    def _reposition_dynamic_input(self) -> None:
        """Re-place the open HUD, if there is one parented here."""
        sc = self.scene()
        hud = getattr(sc, "dynamic_input", None) if sc is not None else None
        if hud is None or hud.parentWidget() is not self.viewport():
            return
        self.place_dynamic_input(hud)

    def place_dynamic_input(self, hud, scene_anchor=_KEEP_ANCHOR) -> None:
        """Position the dynamic-input *hud* near the cursor in the viewport.

        Mirrors the painted Dim HUD rule in :meth:`drawForeground`: offset down
        and to the right of the cursor, flipping to the other side of it when
        the widget would otherwise overflow the viewport.  The widget HUD is
        what replaced that readout for the modes it serves, so the two must sit
        in the same place — a different offset would make the readout appear to
        jump between modes.

        Two placement regimes, selected by *scene_anchor* (decision S1):

        *Cursor-relative* (``scene_anchor=None``) — the HUD is a passive
        readout, so it tracks the pointer exactly as the painted string did.
        ``Model_Space._sync_dynamic_input`` calls this every frame.

        *Scene-latched* (``scene_anchor`` = the resolved point) — the HUD is
        engaged, the cursor is inert, and the numbers on screen belong to a
        specific piece of geometry.  Latching to a scene point is what carries
        it with the drawing through pan and zoom instead of stranding it on the
        glass, and stops it chasing a pointer whose movement means nothing.

        Args:
            hud: The ``DynamicInputHud`` to move.  It must already be a child
                of this view's viewport.  Falls back to the viewport centre
                when no cursor position has been recorded yet (Tab pressed
                before the mouse has entered the view).
            scene_anchor: A scene point to latch to, ``None`` to go back to
                following the cursor, or the ``_KEEP_ANCHOR`` sentinel (the
                default) to reposition without changing regime.
        """
        # sizeHint, not width(): the HUD has never been laid out at this point,
        # so its current geometry is the default 100x30 and the edge-flip would
        # be computed against the wrong extent.
        hud.adjustSize()
        w = hud.width()
        h = hud.height()
        vp_w = self.viewport().width()
        vp_h = self.viewport().height()

        if scene_anchor is not _KEEP_ANCHOR:
            # Set per regime change, never accumulated: an engage that resolves
            # no point must fall back to the cursor rather than silently inherit
            # the previous placement's anchor.
            self._dyn_anchor_scene = (QPointF(scene_anchor)
                                      if scene_anchor is not None else None)

        anchor_scene = getattr(self, "_dyn_anchor_scene", None)
        if anchor_scene is not None:
            # The anchor is a *scene* point, so pan and zoom move the HUD with
            # the drawing instead of leaving it stranded on the glass.
            vp_cursor = self.mapFromScene(anchor_scene)
        else:
            vp_cursor = getattr(self, "_last_vp_pos", None)
        if vp_cursor is None:
            hud.move(max(0, (vp_w - w) // 2), max(0, (vp_h - h) // 2))
            return

        x = vp_cursor.x() + self._DYN_INPUT_OFFSET
        y = vp_cursor.y() + self._DYN_INPUT_OFFSET
        if x + w > vp_w:
            x = vp_cursor.x() - w - self._DYN_INPUT_OFFSET
        if y + h > vp_h:
            y = vp_cursor.y() - h - self._DYN_INPUT_OFFSET
        # Flipping can push a HUD wider/taller than the cursor's margin off the
        # near edge, so clamp after the flip rather than trusting it.
        hud.move(max(0, min(x, vp_w - w)), max(0, min(y, vp_h - h)))

    # ── Fit to screen ─────────────────────────────────────────────────────

    def fit_to_screen(self):
        """Zoom to fit all scene content (or clip rect) within the viewport."""
        # Drop any gesture freeze first: the transient pixmap item must not
        # inflate itemsBoundingRect(), and fit ends the gesture anyway.
        sc0 = self.scene()
        if sc0 is not None and hasattr(sc0, "abort_underlay_freeze"):
            sc0.abort_underlay_freeze()
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
                                sc._tools._solve_constraints()
                                sc.push_undo_state()
                                self.viewport().update()
                            return
                    except (IndexError, AttributeError):
                        pass
                # Check for double-click on a gridline spacing dimension.
                # Use the cached copy because the second press of the
                # double-click may deselect the gridline, clearing the
                # scene's live list before we get here.
                cached = getattr(self, '_last_spacing_dims', [])
                for dim in cached:
                    vp_mid = self.mapFromScene(dim["midpoint"])
                    if math.hypot(event.pos().x() - vp_mid.x(),
                                  event.pos().y() - vp_mid.y()) < 20:
                        self._start_spacing_edit(dim, event.pos())
                        return
                # Double-click on a gridline body/bubble → select it reliably.
                # The second press of the double-click can otherwise land on
                # empty space and clear the selection (see comment above).
                from .gridline import GridlineItem
                for it in sc.items(scene_pos):
                    parent = it.parentItem() if hasattr(it, "parentItem") else None
                    gl = (it if isinstance(it, GridlineItem)
                          else parent if isinstance(parent, GridlineItem) else None)
                    if gl is not None:
                        sc.clearSelection()
                        gl.setSelected(True)
                        if hasattr(sc, "requestPropertyUpdate"):
                            sc.requestPropertyUpdate.emit(gl)
                        return
        super().mouseDoubleClickEvent(event)

    def _start_spacing_edit(self, dim, screen_pos):
        """Open an inline editor to change gridline spacing distance."""
        from PyQt6.QtWidgets import QLineEdit
        from firepro3d.scale_manager import ScaleManager
        from firepro3d.gridline import GridlineItem
        scene = self.scene()
        sm = getattr(scene, 'scale_manager', None)
        # Use the selection snapshot that was captured when the dims were
        # computed — by the time this handler fires the double-click has
        # already deselected everything.
        selected_snapshot = list(
            getattr(scene, '_gridline_spacing_selected', []))
        # Display in formatted units (e.g. 24'-0" or 7315.2 mm)
        current_text = (sm.format_length(dim["distance"])
                        if sm else f"{dim['distance']:.1f} mm")

        editor = QLineEdit(self.viewport())
        editor.setText(current_text)
        editor.setFixedWidth(100)
        editor.move(int(screen_pos.x()) - 50, int(screen_pos.y()) - 12)
        editor.selectAll()
        editor.show()
        editor.setFocus()

        def _accept():
            text = editor.text().strip()
            if sm:
                parsed_mm = ScaleManager.parse_dimension(
                    text, sm.bare_number_unit())
            else:
                try:
                    parsed_mm = float(text)
                except ValueError:
                    parsed_mm = None
            if parsed_mm is not None:
                scene._apply_spacing_edit(dim, parsed_mm, selected_snapshot)
            editor.deleteLater()

        def _cancel():
            editor.deleteLater()

        editor.returnPressed.connect(_accept)
        editor.editingFinished.connect(_cancel)

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

        selected = scene.selectedItems()
        mode = getattr(scene, "mode", None)
        menu = self._build_plan_context_menu(scene, selected, mode)
        menu.exec(event.globalPos())

    # ── Fill submenu helper ────────────────────────────────────────────────

    @staticmethod
    def _build_fill_submenu(parent_menu: QMenu, scene, target) -> QMenu | None:
        """Build and attach a Fill submenu to *parent_menu* for *target*.

        Returns the created QMenu, or None if *target* is not fillable.
        The submenu is appended to *parent_menu* before returning.
        Mutations route through push_undo_state + item.set_property — the same
        undo idiom used by the ribbon / property panel.
        """
        if not getattr(target, "is_fillable", lambda: False)():
            return None

        from .hatch_patterns import PATTERN_NAMES

        fill_menu = parent_menu.addMenu("Fill")

        def _apply(fill_type, pattern=None):
            sc = target.scene()
            if sc is None:
                return
            sc.push_undo_state()
            target.set_property("Fill", fill_type)
            if pattern is not None:
                target.set_property("Pattern", pattern)
            target.update()

        none_act = fill_menu.addAction("None")
        none_act.triggered.connect(lambda _=False: _apply("none"))

        solid_act = fill_menu.addAction("Solid")
        solid_act.triggered.connect(lambda _=False: _apply("solid"))

        hatch_menu = fill_menu.addMenu("Hatch")
        for name in PATTERN_NAMES:
            _name = name  # capture
            act = hatch_menu.addAction(_name)
            act.triggered.connect(
                lambda _=False, n=_name: _apply("hatch", n)
            )

        return fill_menu

    def _build_plan_context_menu(self, scene, selected, mode) -> QMenu:
        """Build the generic plan-view right-click menu and return it (no exec).

        Extracted so tests can call this directly without blocking on exec().
        """
        menu = QMenu(self)

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

            # Gridline-specific actions: shown when exactly one gridline selected
            from .gridline import GridlineItem
            grid_sel = [i for i in selected if isinstance(i, GridlineItem)]
            if len(grid_sel) == 1:
                menu.addSeparator()
                _g = grid_sel[0]
                arr = menu.addAction("Array Gridlines…")
                arr.triggered.connect(
                    lambda _checked=False, g=_g: scene._start_gridline_replicate(g, "array")
                )
                off = menu.addAction("Offset Gridline…")
                off.triggered.connect(
                    lambda _checked=False, g=_g: scene._start_gridline_replicate(g, "offset")
                )

            # Fill submenu: shown when exactly one fillable item is selected
            fillable = [i for i in selected if getattr(i, "is_fillable", lambda: False)()]
            if len(fillable) == 1:
                menu.addSeparator()
                self._build_fill_submenu(menu, scene, fillable[0])
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

        return menu

    def _select_all_items(self):
        from .gridline import GridlineItem
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
