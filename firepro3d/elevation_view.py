"""
elevation_view.py
=================
QGraphicsView for displaying a SectionScene.

Provides middle-button pan, scroll-wheel zoom, F to fit, coordinate display.
Matches the interaction patterns from Model_View.py.
"""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QKeySequence, QShortcut

from . import theme as th

_log = logging.getLogger(__name__)


class SectionView(QGraphicsView):
    """Display widget for a SectionScene with pan/zoom interaction."""

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
            QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate
        )

        # No scrollbars — pan via middle mouse
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Selection band is scene-drawn (see drawForeground + the band lifecycle
        # in mousePress/Move/Release) — Qt-native RubberBandDrag would fight it.
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        # Zoom anchored under mouse
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Blocks-browser drag over this view (hosted-blocks D9); None = no drag.
        self._block_drop = None
        self.setAcceptDrops(True)

        # Pan state
        self._panning = False
        self._pan_start = QPoint()
        self._zoom_factor = 1.15

        # Scene-drawn band state (viewport px). _rb_start is latched on press;
        # _rb_active/_rb_end track the live window/crossing band (mirrors
        # Model_View). HALO aperture is the app-wide halo_selection module
        # global (selection-mode §4.5) — read live, not cached here.
        self._rb_start = None
        self._rb_active = False
        self._rb_end = None

        # Ctrl+A — select all (excluding gridlines and datums)
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(
            self._select_all_items)

    # ── Select All (filter annotations) ──────────────────────────────────

    def _select_all_items(self):
        from .section_scene import ElevGridlineItem, ElevDatumItem
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

    # ── Block drag & drop (gridline-hosted placement, hosted-blocks D9) ──

    def dragEnterEvent(self, event):
        from . import block_drop
        sc = self.scene()
        try:
            payload = block_drop.block_payload(event)
            if payload is None or sc is None or not hasattr(sc, "place_hosted_block"):
                super().dragEnterEvent(event)
                return
            defn, _pool, refusal = block_drop.resolve_block_drag(sc._ms, payload)
            if refusal:
                sc._ms._show_status(refusal)
                event.ignore()
                return
            self._block_drop = {"payload": payload, "name": defn.name}
            event.acceptProposedAction()
        except Exception:
            self._abort_block_drop(event, "enter")

    def dragMoveEvent(self, event):
        if self._block_drop is None:
            super().dragMoveEvent(event)
            return
        try:
            sc = self.scene()
            pt = sc.snap_section_point(self.mapToScene(event.position().toPoint()), self)
            if sc.can_host_at(pt):
                event.acceptProposedAction()
            else:
                event.ignore()                     # no-drop cursor (G9)
        except Exception:
            self._abort_block_drop(event, "move")

    def dragLeaveEvent(self, event):
        self._block_drop = None
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        st, self._block_drop = self._block_drop, None
        if st is None:
            super().dropEvent(event)
            return
        try:
            from .blocks_browser import ensure_block_loaded
            sc = self.scene()
            pt = sc.snap_section_point(self.mapToScene(event.position().toPoint()), self)
            block_id = ensure_block_loaded(sc._ms, st["payload"]["id"],
                                           st["payload"].get("path"), st["name"],
                                           None, self)
            if block_id is None or sc.place_hosted_block(block_id, pt) is None:
                event.ignore()
                return
            event.acceptProposedAction()
        except Exception:
            self._abort_block_drop(event, "drop")

    def _abort_block_drop(self, event, stage: str) -> None:
        """Log, drop the drag state, ignore (a Qt drag handler must not raise)."""
        _log.exception("Section block drag %s failed", stage)
        self._block_drop = None
        event.ignore()

    # ── Pan (middle mouse) ───────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        sc = self.scene()
        if (event.button() == Qt.MouseButton.LeftButton and sc is not None
                and getattr(sc, "_place_block_id", None) is not None):
            try:
                pt = sc.snap_section_point(
                    self.mapToScene(event.position().toPoint()), self)
                sc.click_place_block(pt)
            except Exception:
                _log.exception("Section block placement click failed")
            self.viewport().update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # Latch the band start (viewport px). Let the scene press run first
            # (HALO-committed select / manipulator handle press); it accepts the
            # event when it commits a selection or consumes a handle. If it did
            # NOT accept (empty canvas), arm the scene-drawn band.
            self._rb_start = event.pos()
            self._rb_active = False
            self._rb_end = None
            super().mousePressEvent(event)
            sc = self.scene()
            if (not event.isAccepted()) and sc is not None:
                self._rb_active = True
                self._rb_end = event.pos()
                if hasattr(sc, "_rb_active_flag"):
                    sc._rb_active_flag = True
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            return
        scene_pos = self.mapToScene(event.pos())
        self._emit_coords(scene_pos)
        sc = self.scene()
        if sc is not None and getattr(sc, "_place_block_id", None) is not None:
            try:
                sc.move_place_ghost(sc.snap_section_point(scene_pos, self))
            except Exception:
                _log.exception("Section block placement move failed")
            self.viewport().update()
            event.accept()
            return
        if self._rb_active:
            # Live scene-drawn band: extend it and repaint. No live
            # preselection preview (user decision 2026-09-24 — recomputing
            # rubber_band_hits and HALO-outlining every hit item on each move
            # was too slow on a large drawing; selection-mode §6.3). The
            # single-item HALO update is skipped while banding too (suppressed
            # scene-side via _rb_active_flag).
            self._rb_end = event.pos()
            self.viewport().update()
            return
        # HALO hover update (scene-agnostic engine on the mixin).
        if sc is not None and hasattr(sc, "halo_update"):
            from . import halo_selection
            a_scene = halo_selection.HALO_APERTURE_PX / max(self.transform().m11(), 1e-9)
            if sc.halo_update(scene_pos, a_scene, self.viewportTransform()):
                self.viewport().update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if event.button() == Qt.MouseButton.LeftButton and self._rb_active:
            sc = self.scene()
            start = self._rb_start
            end = self._rb_end or event.pos()
            dist = ((end - start).manhattanLength()
                    if start is not None else 0)
            if dist >= 5 and sc is not None and hasattr(sc, "commit_rubber_band"):
                # Real drag → commit the window/crossing selection.
                start_scene = self.mapToScene(start)
                end_scene = self.mapToScene(end)
                crossing = end.x() < start.x()
                rect = QRectF(start_scene, end_scene).normalized()
                additive = bool(event.modifiers()
                                & Qt.KeyboardModifier.ControlModifier)
                sc.commit_rubber_band(rect, crossing, additive,
                                      self.viewportTransform())
            # A <5px "drag" is a click — selection was handled on press. Always
            # clear the band state.
            self._rb_active = False
            self._rb_end = None
            self._rb_start = None
            if sc is not None:
                if hasattr(sc, "_rb_active_flag"):
                    sc._rb_active_flag = False
            self.viewport().update()
            super().mouseReleaseEvent(event)
            return
        self._rb_start = None
        super().mouseReleaseEvent(event)

    # ── Overlay: HALO highlight + scene-drawn band ────────────────────────

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        scene = self.scene()
        if scene is None:
            return
        from .halo import paint_halo_highlight, paint_rubber_band
        theme = th.detect()
        # HALO hover highlight (gated on suppression like the plan view).
        if (hasattr(scene, "_halo_suppressed")
                and not scene._halo_suppressed()):
            halo = scene.halo_item() if hasattr(scene, "halo_item") else None
            if halo is not None:
                paint_halo_highlight(painter, self, halo, theme)
        # Live band rect (no preselection preview — see mouseMoveEvent).
        if self._rb_active:
            if self._rb_end is not None and self._rb_start is not None:
                paint_rubber_band(painter, self, self._rb_start,
                                  self._rb_end, theme)

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
        sc = self.scene()
        # Armed block placement owns Space (rotate; Shift = reverse) and Esc.
        if sc is not None and getattr(sc, "_place_block_id", None) is not None:
            if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                rev = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                sc.rotate_place_block(90.0 if rev else -90.0)   # as Model_Space
                self.viewport().update()
                event.accept()
                return
            # Arrows flip on screen (as Model_Space): <-/-> left-right, up/down
            # top-bottom; auto-repeat ignored, any real modifier is another chord.
            if (event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                                Qt.Key.Key_Up, Qt.Key.Key_Down)
                    and (event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier)
                    == Qt.KeyboardModifier.NoModifier):
                if not event.isAutoRepeat():
                    sc.flip_place_block(
                        "h" if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) else "v")
                    self.viewport().update()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                sc.cancel_place_block()
                self.viewport().update()
                event.accept()
                return
        # Spacebar cycles overlapping HALO candidates (mirrors the plan view's
        # select-mode Space handling → _halo_cycle).
        if (event.key() == Qt.Key.Key_Space and not event.isAutoRepeat()
                and sc is not None and hasattr(sc, "_halo_cycle")):
            if sc._halo_cycle():
                self.viewport().update()
                event.accept()
                return
        # Escape ladder: cancel band → reset HALO → clear selection.
        if event.key() == Qt.Key.Key_Escape and sc is not None \
                and hasattr(sc, "_escape_ladder"):
            if sc._escape_ladder():
                self.viewport().update()
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
