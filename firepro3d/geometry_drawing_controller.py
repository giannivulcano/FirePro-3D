"""GeometryDrawingController — concern #6's simple 2D-drawing primitives
extracted from ``Model_Space`` (decomposition slice 8).

A plain object (not a QObject) holding a back-ref to the scene. Unlike the
pipe/sprinkler/underlay controllers, this collaborator is a **behavior home**:
it owns NO state. All geometry drawing state — the persisted ``_draw_lines`` /
``_draw_rects`` / ``_draw_circles`` / ``_polylines`` lists AND every transient
anchor/preview/flag — stays on the scene (reached via ``self._scene``), because
the already-extracted ``PlacementInputCoordinator`` reads it. This controller
owns the Line / Rectangle / Circle / Polyline drawing *methods* and the single
idempotent ``clear()`` teardown.

Scope note: ``draw_gridline`` shares the line handlers but its item factory
(``_make_line_like``) stays scene-side (dual-concern with the gridline concern);
Arc + Polygon are deferred to Slice 9 (into this same controller).

Design: docs/superpowers/specs/2026-09-04-geometry-drawing-slice-design.md
Behavior (Rule A): docs/specs/2d-geometry.md
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor, QBrush
from PyQt6.QtWidgets import (QGraphicsRectItem, QGraphicsEllipseItem,
                             QGraphicsItem)

from .construction_geometry import CircleItem, PolylineItem
from .constants import SELECTION_OUTLINE_COLOR


class GeometryDrawingController:
    def __init__(self, scene):
        self._scene = scene

    def clear(self, new_mode) -> None:
        """Idempotent teardown for the simple-primitive draw modes.

        Absorbs the line/rect/circle/polyline branches of ``set_mode``'s teardown
        cascade. Each per-primitive guard is preserved verbatim (``if new_mode !=
        "<mode>": …``) so staying in a mode mid-placement still preserves that
        primitive's in-progress state. Operates on scene-side state via
        ``self._scene`` (behavior-home model). Populated in C3.
        """
        # Wired in C3 (set_mode teardown relocation).

    # ── Line (shared with draw_gridline; the item factory _make_line_like
    #    stays scene-side because it builds a GridlineItem in gridline mode) ────

    def _preview_from_line(self, tip) -> None:
        """Point the rubber-band line at ``tip`` (already constrained/resolved).

        Anchored at ``_draw_line_anchor`` — the ``draw_line``/``draw_gridline``
        first-click point.  A no-op before the anchor is armed.
        """
        anchor = self._scene._draw_line_anchor
        if anchor is None:
            return
        self._scene.preview_pipe.setLine(anchor.x(), anchor.y(), tip.x(), tip.y())
        self._scene.preview_pipe.show()

    def _move_draw_line(self, event, snapped):
        _anchor = self._scene._draw_line_anchor
        if _anchor is None:
            self._scene.update_preview_node(snapped)   # cursor preview before first click
        if _anchor is not None:
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._scene._constrain_angle(_anchor, snapped)
            self._preview_from_line(tip)
            # Publishing here — after the Ctrl constraint — is what keeps
            # the readout and the HUD's seed from disagreeing.
            self._scene.publish_placement_state(_anchor, tip)
        else:
            self._scene.preview_pipe.hide()

    def _press_draw_line(self, event, pos, snapped, item_under, node_under, pipe_under):
        _is_grid = self._scene.mode == "draw_gridline"
        if self._scene._draw_line_anchor is None:
            self._scene._draw_line_anchor = snapped
            self._scene.update_preview_node(snapped)
            self._scene.instructionChanged.emit("Pick end point" if _is_grid else "Pick second point")
        else:
            # Place the item (apply Ctrl constraint if held)
            tip = snapped
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                tip = self._scene._constrain_angle(self._scene._draw_line_anchor, snapped)
            self._commit_draw_line_at(tip)

    def _commit_draw_line_at(self, tip):
        """Commit the armed line-like placement, ending at ``tip``.

        This is the commit half of :meth:`_press_draw_line`, split out so that
        Dynamic Input is an alternative *point source* rather than an
        alternative *commit path*: a typed exact point and a mouse click land
        in this one method, so they cannot drift apart.

        ``tip`` is expected to be fully constrained already (OSNAP, ALIGN,
        Ctrl) — this method applies no further constraint. A too-short line is
        rejected and leaves the anchor armed so the user can re-pick.

        The item factory ``_make_line_like`` stays scene-side (dual-concern:
        it builds a ``GridlineItem`` in ``draw_gridline`` mode).

        Returns:
            True when a line was committed, False when it was refused (no
            anchor, or under the too-short floor). Decision D2: the caller
            turns a False into a flagged HUD field rather than the placement
            silently evaporating into a status-bar message the user never sees.
        """
        anchor = self._scene._draw_line_anchor
        if anchor is None:
            return False
        _is_grid = self._scene.mode == "draw_gridline"
        # Reject zero-length lines
        if math.hypot(tip.x() - anchor.x(),
                      tip.y() - anchor.y()) < 0.5:
            self._scene._show_status(
                "Gridline too short — skipped" if _is_grid else "Line too short — skipped",
                timeout=2000)
            return False
        self._scene._make_line_like(anchor, tip)
        for v in self._scene.views(): v.viewport().update()
        self._scene._draw_line_anchor = None
        self._scene.clear_placement_state()
        self._scene.preview_pipe.hide()
        self._scene.push_undo_state()
        self._scene.instructionChanged.emit("Pick start point" if _is_grid else "Pick first point")
        return True

    # ── Circle ────────────────────────────────────────────────────────────────

    def _preview_from_circle(self, rim) -> None:
        """Redraw the circle preview so ``rim`` lands on its circumference.

        The radius is the distance from ``_draw_circle_center`` to ``rim``. A
        no-op until both the centre and the preview item exist.
        """
        if self._scene._draw_circle_center is None or self._scene._draw_circle_preview is None:
            return
        r = math.hypot(rim.x() - self._scene._draw_circle_center.x(),
                       rim.y() - self._scene._draw_circle_center.y())
        cx, cy = self._scene._draw_circle_center.x(), self._scene._draw_circle_center.y()
        self._scene._draw_circle_preview.setRect(cx - r, cy - r, 2 * r, 2 * r)

    def _move_draw_circle(self, event, snapped):
        if self._scene._draw_circle_center is None:
            self._scene.update_preview_node(snapped)   # cursor preview before first click
        else:
            self._scene.preview_node.hide()
        self._scene.preview_pipe.hide()
        if self._scene._draw_circle_center is not None and self._scene._draw_circle_preview is not None:
            self._preview_from_circle(snapped)
            # The HUD widget is the readout (S1); the rim point carries the
            # radius, since the commit takes the hypot.
            self._scene.publish_placement_state(self._scene._draw_circle_center, snapped)

    def _press_draw_circle(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._scene._draw_circle_center is None:
            self._scene._draw_circle_center = snapped
            self._scene.update_preview_node(snapped)
            self._scene.instructionChanged.emit("Pick radius point")
            # Create preview circle
            preview = QGraphicsEllipseItem(snapped.x(), snapped.y(), 0, 0)
            _prev_pen = QPen(QColor(self._scene._geom_color_lw()[0]), 2, Qt.PenStyle.DashLine)
            _prev_pen.setCosmetic(True)
            preview.setPen(_prev_pen)
            preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            preview.setZValue(200)
            self._scene.addItem(preview)
            self._scene._draw_circle_preview = preview
        else:
            self._commit_draw_circle_at(snapped)

    def _commit_draw_circle_at(self, rim):
        """Commit the armed circle with ``rim`` on its circumference.

        The commit half of :meth:`_press_draw_circle`, split out so Dynamic
        Input is an alternative *point source* rather than an alternative
        *commit path*.

        Only the distance from the centre matters — the radius is a ``hypot``
        — which is what lets ``resolve_circle`` return a bare ``+X`` point for
        a typed radius without encoding a meaningless direction.

        Returns:
            True when a circle was committed, False when it was refused (no
            centre, or a radius under the too-small floor).

        A refusal now leaves the centre armed and the preview up, matching the
        line and rectangle commits.
        """
        centre = self._scene._draw_circle_center
        if centre is None:
            return False
        r = math.hypot(rim.x() - centre.x(), rim.y() - centre.y())
        if r < 0.5:
            self._scene._show_status("Circle radius too small — skipped", timeout=2000)
            return False
        tmpl = self._scene._get_geometry_template()
        _c, _lw = self._scene._geom_color_lw()
        item = CircleItem(centre, r, _c, _lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        self._scene.addItem(item)
        self._scene._draw_circles.append(item)
        item.setSelected(True)
        for v in self._scene.views(): v.viewport().update()
        # Remove preview
        if self._scene._draw_circle_preview is not None:
            self._scene.removeItem(self._scene._draw_circle_preview)
            self._scene._draw_circle_preview = None
        self._scene._draw_circle_center = None
        self._scene.clear_placement_state()
        self._scene.push_undo_state()
        self._scene.instructionChanged.emit("Pick center point")
        return True

    # ── Polyline (the dual-concern Delete-pop helper
    #    _delete_or_pop_polyline_vertex stays scene-side — it also handles floor) ─

    _POLYLINE_CLOSE_RING_PX = 14  # half-side of the bounding square, screen px

    def _preview_from_polyline(self, tip) -> None:
        """Extend the active polyline's rubber-band to ``tip`` (already resolved).

        A no-op before the first vertex exists.  Polyline draws its preview
        through the item's own ``update_preview`` rather than ``preview_pipe``,
        so it does not share ``_preview_from_line``.
        """
        if self._scene._polyline_active is None:
            return
        self._scene._polyline_active.update_preview(tip)

    def _show_polyline_close_indicator(self, pt) -> None:
        """Show (lazily-create) the hollow ring on *pt* signalling close-cue.

        A fixed screen-size QGraphicsEllipseItem with ItemIgnoresTransformations
        (stays 14 px regardless of zoom), coloured with ``SELECTION_OUTLINE_COLOR``.
        """
        r = self._POLYLINE_CLOSE_RING_PX
        if self._scene._polyline_close_indicator is None:
            ring = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
            pen = QPen(QColor(SELECTION_OUTLINE_COLOR), 2)
            pen.setCosmetic(True)
            ring.setPen(pen)
            ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            ring.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            ring.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            ring.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            ring.setZValue(201)  # above Z_OVERLAY (200)
            self._scene.addItem(ring)
            self._scene._polyline_close_indicator = ring
        self._scene._polyline_close_indicator.setPos(pt)
        self._scene._polyline_close_indicator.show()

    def _hide_polyline_close_indicator(self) -> None:
        """Hide the close-cue ring (keeps the item alive for reuse)."""
        if self._scene._polyline_close_indicator is not None:
            self._scene._polyline_close_indicator.hide()

    def _move_polyline(self, event, snapped):
        if self._scene._polyline_active is None:
            self._scene.update_preview_node(snapped)   # cursor preview before first click
        else:
            self._scene.preview_node.hide()
        self._scene.preview_pipe.hide()
        if self._scene._polyline_active is not None:
            pl = self._scene._polyline_active
            pts = pl._points
            if len(pts) >= 3:
                scale = self._scene._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                if math.hypot(snapped.x() - pts[0].x(), snapped.y() - pts[0].y()) <= tol:
                    self._scene.update_preview_node(pts[0])
                    self._show_polyline_close_indicator(pts[0])
                    self._preview_from_polyline(pts[0])
                    # Keep the HUD readout live on the closing segment.
                    self._scene.publish_placement_state(pts[-1], pts[0])
                    return
            self._hide_polyline_close_indicator()
            tip = snapped
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and len(self._scene._polyline_active._points) >= 1):
                tip = self._scene._constrain_angle(
                    self._scene._polyline_active._points[-1], snapped
                )
            self._preview_from_polyline(tip)
            # Publishing here — after the Ctrl constraint — is what keeps the
            # readout and the HUD's seed from disagreeing with the preview.
            self._scene.publish_placement_state(
                self._scene._polyline_active._points[-1], tip)

    def _press_polyline(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._scene._polyline_active is None:
            # First click — create the polyline item
            tmpl = self._scene._get_geometry_template()
            _c, _lw = self._scene._geom_color_lw()
            pl = PolylineItem(snapped, _c, _lw)
            pl.level = tmpl.level
            pl._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
            self._scene.addItem(pl)
            self._scene._polylines.append(pl)
            self._scene._polyline_active = pl
            self._scene.update_preview_node(snapped)
            self._scene.instructionChanged.emit("Pick next point (Enter to finish)")
        else:
            pts = self._scene._polyline_active._points
            # Close-on-start: ≥3 vertices and click within tolerance of pts[0].
            if len(pts) >= 3:
                scale = self._scene._active_view_scale()
                tol = 8.0 / max(scale, 1e-6)
                d0 = math.hypot(snapped.x() - pts[0].x(), snapped.y() - pts[0].y())
                if d0 <= tol:
                    pl = self._scene._polyline_active
                    pl.close()
                    pl.finalize()
                    self._scene._polyline_active = None
                    self._hide_polyline_close_indicator()
                    pl.setSelected(True)
                    self._scene.preview_pipe.hide()
                    for v in self._scene.views(): v.viewport().update()
                    self._scene.push_undo_state()
                    self._scene.instructionChanged.emit("Pick first point")
                    return
            # Subsequent clicks — append vertex (apply Ctrl constraint if held)
            tip = snapped
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and len(self._scene._polyline_active._points) >= 1):
                tip = self._scene._constrain_angle(
                    self._scene._polyline_active._points[-1], snapped
                )
            self._commit_polyline_at(tip)
        # don't let super() deselect items mid-draw

    def _commit_polyline_at(self, tip):
        """Append one vertex to the active polyline at ``tip``.

        The commit half of :meth:`_press_polyline`, split out so that Dynamic
        Input is an alternative *point source* rather than an alternative
        *commit path*: a typed exact point and a mouse click land here, so they
        cannot drift apart.

        Deliberately does **not** push an undo state — polyline undo is pushed
        once when the chain is finalized, not per vertex. Unlike the line commit
        the placement stays live afterwards: the new vertex becomes the next
        anchor, so the HUD is reseeded for the following segment.

        Returns:
            True when a vertex was appended, False when no polyline is active.
        """
        pl = self._scene._polyline_active
        if pl is None:
            return False
        pl.append_point(tip)
        # The published point described the segment just committed; the next
        # frame republishes from the new anchor.
        self._scene.clear_placement_state()
        return True
