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
from PyQt6.QtGui import QPen, QColor, QBrush, QPainterPath
from PyQt6.QtWidgets import (QGraphicsRectItem, QGraphicsEllipseItem,
                             QGraphicsLineItem, QGraphicsPathItem,
                             QGraphicsItem)

from .construction_geometry import (CircleItem, PolylineItem, RectangleItem,
                                    ArcItem, RegularPolygonItem)
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
        ``self._scene`` (behavior-home model). Polygon/arc/text teardown stays
        inline in ``set_mode`` (Slice 9 / other concerns).
        """
        s = self._scene
        # Cancel in-progress polyline
        if new_mode != "polyline" and s._polyline_active is not None:
            # Cancel: always discard the in-progress polyline
            # (Enter commits via finalize() and sets _polyline_active=None
            #  before reaching here, so this path is only hit by Escape/mode-change)
            if s._polyline_active.scene() is s:
                s.removeItem(s._polyline_active)
            if s._polyline_active in s._polylines:
                s._polylines.remove(s._polyline_active)
            s._polyline_active = None
        self._hide_polyline_close_indicator()
        # Cancel in-progress draw geometry
        if new_mode not in ("draw_line", "draw_gridline"):
            s._draw_line_anchor = None
        if new_mode != "draw_rectangle":
            s._draw_rect_anchor = None
            s._draw_rect_rotating = False
            s._draw_rect_sized_pt1 = None
            s._draw_rect_sized_pt2 = None
            s._draw_rect_pivot = None
            self._clear_rect_ref_lines()
            if s._draw_rect_preview is not None:
                if s._draw_rect_preview.scene() is s:
                    s.removeItem(s._draw_rect_preview)
                s._draw_rect_preview = None
        if new_mode != "draw_circle":
            s._draw_circle_center = None
            if s._draw_circle_preview is not None:
                if s._draw_circle_preview.scene() is s:
                    s.removeItem(s._draw_circle_preview)
                s._draw_circle_preview = None
        # Polygon teardown (slice 9)
        if new_mode != "polygon":
            s._polygon_center = None
            s._polygon_rotating = False
            s._polygon_sized_radius = None
            if s._polygon_preview is not None:
                if s._polygon_preview.scene() is s:
                    s.removeItem(s._polygon_preview)
                s._polygon_preview = None
            self._clear_polygon_ref_items()
        # Arc teardown (slice 9)
        if new_mode != "draw_arc":
            s._draw_arc_center = None
            s._draw_arc_radius = 0.0
            s._draw_arc_start_deg = 0.0
            s._draw_arc_step = 0
            if s._draw_arc_radius_line is not None:
                if s._draw_arc_radius_line.scene() is s:
                    s.removeItem(s._draw_arc_radius_line)
                s._draw_arc_radius_line = None
            if s._draw_arc_preview is not None:
                if s._draw_arc_preview.scene() is s:
                    s.removeItem(s._draw_arc_preview)
                s._draw_arc_preview = None
            self._clear_arc_ref_lines()

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

    # ── Rectangle (3-step size→rotate; the generic ref-line factory
    #    _make_ref_line stays scene-side — shared by arc/polygon/wall/floor) ────

    def _preview_from_rectangle(self, corner) -> None:
        """Redraw the rectangle preview to the resolved far ``corner``.

        Honours the from-centre branch (symmetric half-extents) and, in corner
        mode, the ``normalized()`` corner logic.  A no-op until both the anchor
        and the preview item exist.
        """
        if self._scene._draw_rect_anchor is None or self._scene._draw_rect_preview is None:
            return
        if self._scene._draw_rect_from_center:
            # Center mode: anchor is center, rect extends symmetrically
            hw = abs(corner.x() - self._scene._draw_rect_anchor.x())
            hh = abs(corner.y() - self._scene._draw_rect_anchor.y())
            rect = QRectF(
                self._scene._draw_rect_anchor.x() - hw,
                self._scene._draw_rect_anchor.y() - hh,
                2 * hw, 2 * hh,
            )
        else:
            rect = QRectF(self._scene._draw_rect_anchor, corner).normalized()
        self._scene._draw_rect_preview.setRect(rect)

    def _preview_rectangle_rotation(self, angle_deg) -> None:
        """Spin the sized preview rect to ``angle_deg`` about the stored pivot.

        Angle-driven (the sized rect is fixed, only orientation follows the
        cursor/typed angle).  Uses the same Qt transform ``RectangleItem.set_angle``
        will (origin at the pivot, Y-up angle negated for Qt's CW ``setRotation``)
        so the ghost matches the committed item.  A no-op until the preview rect
        and the pivot both exist.
        """
        if self._scene._draw_rect_preview is None or self._scene._draw_rect_pivot is None:
            return
        self._scene._draw_rect_preview.setTransformOriginPoint(self._scene._draw_rect_pivot)
        self._scene._draw_rect_preview.setRotation(-angle_deg)   # Y-up CCW → Qt CW negate
        self._update_rect_ref_lines(angle_deg)

    def _update_rect_ref_lines(self, angle_deg) -> None:
        """Point the two rotate-step guides from the pivot (protractor).

        ``_draw_rect_ref_line0`` is the horizontal 0° datum; ``_draw_rect_ref_lineA``
        is the current sweep at ``angle_deg`` (Y-up).  Both run the sized rect's
        diagonal length so they frame the rectangle.  A no-op until both guides
        and the sized rect exist.
        """
        piv = self._scene._draw_rect_pivot
        if (piv is None or self._scene._draw_rect_ref_line0 is None
                or self._scene._draw_rect_ref_lineA is None
                or self._scene._draw_rect_sized_pt1 is None
                or self._scene._draw_rect_sized_pt2 is None):
            return
        p1, p2 = self._scene._draw_rect_sized_pt1, self._scene._draw_rect_sized_pt2
        length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
        rad = math.radians(angle_deg)
        self._scene._draw_rect_ref_line0.setLine(piv.x(), piv.y(),
                                                 piv.x() + length, piv.y())
        self._scene._draw_rect_ref_lineA.setLine(
            piv.x(), piv.y(),
            piv.x() + length * math.cos(rad),
            piv.y() - length * math.sin(rad))   # Y-up: subtract sin

    def _clear_rect_ref_lines(self) -> None:
        """Remove both rotate-step guides from the scene."""
        for attr in ("_draw_rect_ref_line0", "_draw_rect_ref_lineA"):
            line = getattr(self._scene, attr, None)
            if line is not None:
                if line.scene() is self._scene:
                    self._scene.removeItem(line)
                setattr(self._scene, attr, None)

    def _move_draw_rectangle(self, event, snapped):
        if self._scene._draw_rect_rotating:
            # Rotate step: the sized rect is fixed; spin the ghost to the pivot→
            # cursor heading and publish so the HUD reads out the orientation.
            self._scene.preview_node.hide()
            self._scene.preview_pipe.hide()
            # Ctrl angle-snaps the rotation to ``_snap_angle_deg`` increments.
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._scene._draw_rect_pivot is not None):
                snapped = self._scene._constrain_angle(self._scene._draw_rect_pivot, snapped)
            angle = self._rect_rotation_angle_to(snapped)
            self._preview_rectangle_rotation(angle)
            self._scene.publish_placement_state(self._scene._draw_rect_pivot, snapped)
            return
        if self._scene._draw_rect_anchor is None:
            self._scene.update_preview_node(snapped)   # cursor preview before first click
        else:
            self._scene.preview_node.hide()
        self._scene.preview_pipe.hide()
        if self._scene._draw_rect_anchor is not None and self._scene._draw_rect_preview is not None:
            self._preview_from_rectangle(snapped)
            # Published unnormalised so the signed extents reach the schema.
            self._scene.publish_placement_state(self._scene._draw_rect_anchor, snapped)

    def _press_draw_rectangle(self, event, pos, snapped, item_under, node_under, pipe_under):
        if self._scene._draw_rect_rotating:
            # Third click: commit at the orientation from the pivot to the click.
            if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and self._scene._draw_rect_pivot is not None):
                snapped = self._scene._constrain_angle(self._scene._draw_rect_pivot, snapped)
            self._commit_rectangle_rotated(
                self._rect_rotation_angle_to(snapped))
        elif self._scene._draw_rect_anchor is None:
            self._scene._draw_rect_anchor = snapped
            self._scene.update_preview_node(snapped)
            _instr = "Pick opposite corner" if not self._scene._draw_rect_from_center else "Pick corner (from center)"
            self._scene.instructionChanged.emit(_instr)
            # Create preview rect
            preview = QGraphicsRectItem(QRectF(snapped, snapped))
            _prev_pen = QPen(QColor(self._scene._geom_color_lw()[0]), 2, Qt.PenStyle.DashLine)
            _prev_pen.setCosmetic(True)
            preview.setPen(_prev_pen)
            preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            preview.setZValue(200)
            self._scene.addItem(preview)
            self._scene._draw_rect_preview = preview
        else:
            # Second click: size the axis-aligned rect and enter the rotate step.
            self._advance_rectangle_to_rotate_step(snapped)

    def _rect_rotation_angle_to(self, cursor) -> float:
        """Return the absolute orientation (Y-up degrees from +x) pivot→``cursor``.

        0° when the cursor is due-east of the pivot.  Shared by the third mouse
        click and the rotate preview so both read the same heading.  Falls back
        to 0° when the pivot is unset.
        """
        piv = self._scene._draw_rect_pivot
        if piv is None:
            return 0.0
        return math.degrees(math.atan2(-(cursor.y() - piv.y()),
                                       cursor.x() - piv.x()))

    def _rect_sizing_points(self, corner):
        """Return the axis-aligned ``(pt1, pt2)`` the sizing step produces.

        Delegates to ``rect_sizing_points`` (shared with wall-rect placement).
        Returns ``(None, None)`` when unarmed.
        """
        from .construction_geometry import rect_sizing_points
        anc = self._scene._draw_rect_anchor
        if anc is None:
            return None, None
        return rect_sizing_points(anc, corner, self._scene._draw_rect_from_center)

    def _advance_rectangle_to_rotate_step(self, corner) -> bool:
        """Advance an armed rectangle from the sizing step to the rotate step.

        Stores the sized axis-aligned rect + its pivot (the first-click anchor
        in corner mode, the rect centre — equal to the anchor — in centre mode),
        sets ``_draw_rect_rotating``, re-fits the preview, and lays the rotation
        reference guides.  Shared by the mouse second click and the sizing
        Dynamic Input applier.

        Returns:
            True when the rect advanced, False when refused (no anchor, or an
            extent under the too-small floor).
        """
        pt1, pt2 = self._rect_sizing_points(corner)
        if pt1 is None:
            return False
        # Reject zero-size rectangles (decision D2 — same threshold as the old
        # 2-click commit).
        if abs(pt2.x() - pt1.x()) < 0.5 or abs(pt2.y() - pt1.y()) < 0.5:
            self._scene._show_status("Rectangle too small — skipped", timeout=2000)
            return False
        self._scene._draw_rect_sized_pt1 = pt1
        self._scene._draw_rect_sized_pt2 = pt2
        # Pivot: corner mode turns about the first-click anchor; centre mode
        # turns about the rect centre = the anchor.
        self._scene._draw_rect_pivot = QPointF(self._scene._draw_rect_anchor)
        self._scene._draw_rect_rotating = True
        # Snap the preview to the final sized rect; the rotate preview spins it.
        if self._scene._draw_rect_preview is not None:
            self._scene._draw_rect_preview.setRect(QRectF(pt1, pt2).normalized())
        # Rotation reference guides (0° datum + live sweep), drawn from the pivot.
        # _make_ref_line stays scene-side (generic, shared across concerns).
        self._clear_rect_ref_lines()
        self._scene._draw_rect_ref_line0 = self._scene._make_ref_line()
        self._scene._draw_rect_ref_lineA = self._scene._make_ref_line()
        self._update_rect_ref_lines(0.0)
        self._scene.clear_placement_state()
        self._scene.instructionChanged.emit("Pick rotation / type angle")
        return True

    def _apply_rectangle_dynamic_input(self, geometry) -> bool:
        """Route a resolved rectangle value to the right step's applier.

        At the sizing step the ``rectangle`` schema resolves to a far-corner
        QPointF (advance to the rotate step); at the rotate step the ``rotation``
        schema resolves to a ``{"angle_deg": …}`` dict (commit).
        """
        if self._scene._draw_rect_rotating:
            return self._apply_rectangle_rotation(geometry)         # dict
        return self._advance_rectangle_to_rotate_step(geometry)      # QPointF

    def _apply_rectangle_rotation(self, geometry) -> bool:
        """Rotate-step applier: commit the sized rect at the typed angle."""
        return self._commit_rectangle_rotated(geometry["angle_deg"])

    def _commit_rectangle_rotated(self, angle_deg) -> bool:
        """Commit the sized rectangle rotated to ``angle_deg`` about its pivot.

        The 2-click sizing already produced ``_draw_rect_sized_pt1/_pt2`` and
        the ``_draw_rect_pivot``; this builds the ``RectangleItem`` and applies
        ``set_angle(angle_deg, pivot)`` (a 0° rotate leaves it axis-aligned).
        Shared by the third mouse click and the ``rotation`` Dynamic Input value.

        Returns:
            True when a ``RectangleItem`` was committed, False when the sizing
            state is missing or degenerate.
        """
        pt1 = self._scene._draw_rect_sized_pt1
        pt2 = self._scene._draw_rect_sized_pt2
        if pt1 is None or pt2 is None:
            return False
        if abs(pt2.x() - pt1.x()) < 0.5 or abs(pt2.y() - pt1.y()) < 0.5:
            return False
        tmpl = self._scene._get_geometry_template()
        _c, _lw = self._scene._geom_color_lw()
        item = RectangleItem(pt1, pt2, _c, _lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        item.set_angle(angle_deg, self._scene._draw_rect_pivot)
        self._scene.addItem(item)
        self._scene._draw_rects.append(item)
        item.setSelected(True)
        for v in self._scene.views(): v.viewport().update()
        # Remove preview
        if self._scene._draw_rect_preview is not None:
            self._scene.removeItem(self._scene._draw_rect_preview)
            self._scene._draw_rect_preview = None
        _from_centre = self._scene._draw_rect_from_center
        # Reset the full rect state (anchor + rotate step + sized rect + pivot).
        self._scene._draw_rect_anchor = None
        self._scene._draw_rect_rotating = False
        self._scene._draw_rect_sized_pt1 = None
        self._scene._draw_rect_sized_pt2 = None
        self._scene._draw_rect_pivot = None
        self._clear_rect_ref_lines()
        self._scene.clear_placement_state()
        self._scene.push_undo_state()
        self._scene.instructionChanged.emit(
            "Pick center point" if _from_centre else "Pick first corner")
        return True

    # ── Arc (3-step centre→radius/start→span; variant-aware. The generic
    #    ref-line factory _make_ref_line stays scene-side) ─────────────────────

    def _set_arc_ref_lines(self) -> None:
        """Place the span-step arc guides: a 0° datum + the start-angle radial.

        Both are static through the span step (radius and start angle are fixed;
        only the sweep changes), so this runs once at the step-1→2 transition.
        The arc sweep runs from the start radial, so together they read as a
        protractor.  A no-op until the centre and both guides exist.
        """
        s = self._scene
        c = s._draw_arc_center
        if (c is None or s._draw_arc_ref_line0 is None
                or s._draw_arc_ref_start is None):
            return
        cx, cy, r = c.x(), c.y(), s._draw_arc_radius
        s._draw_arc_ref_line0.setLine(cx, cy, cx + r, cy)   # 0° datum
        sr = math.radians(s._draw_arc_start_deg)            # Y-up
        s._draw_arc_ref_start.setLine(
            cx, cy, cx + r * math.cos(sr), cy - r * math.sin(sr))

    def _update_arc_sweep_ref(self, cursor) -> None:
        """Point the live sweep radial from the centre to the arc endpoint.

        The endpoint sits on the radius circle at the cursor's bearing, so the
        radial ends exactly where the arc preview does.  A no-op until the sweep
        guide and centre exist.
        """
        s = self._scene
        c = s._draw_arc_center
        if c is None or s._draw_arc_ref_sweep is None:
            return
        cx, cy, r = c.x(), c.y(), s._draw_arc_radius
        end_deg = math.degrees(math.atan2(-(cursor.y() - cy), cursor.x() - cx))
        er = math.radians(end_deg)
        s._draw_arc_ref_sweep.setLine(
            cx, cy, cx + r * math.cos(er), cy - r * math.sin(er))

    def _clear_arc_ref_lines(self) -> None:
        """Remove the span-step arc guides from the scene."""
        s = self._scene
        for attr in ("_draw_arc_ref_line0", "_draw_arc_ref_start",
                     "_draw_arc_ref_sweep"):
            line = getattr(s, attr, None)
            if line is not None:
                if line.scene() is s:
                    s.removeItem(line)
                setattr(s, attr, None)

    def _preview_from_arc(self, resolved) -> None:
        """Redraw the arc preview from the resolved point ``resolved``.

        Step-aware, mirroring what ``_move_draw_arc`` draws so the mouse path and
        the Dynamic Input field-commit path share one preview updater:

        * step 1 points the radius line from the stored centre at ``resolved``;
        * step 2 rebuilds the arc sweep path from start deg to the bearing of
          ``resolved`` on the radius circle.

        A pure preview updater: no state mutation, no publish, and a no-op when
        the relevant preview item or the centre is None (before the first click,
        or between steps).
        """
        s = self._scene
        if s._draw_arc_center is None:
            return
        if s._draw_arc_step == 1:
            if s._draw_arc_radius_line is None:
                return
            cx = s._draw_arc_center.x()
            cy = s._draw_arc_center.y()
            s._draw_arc_radius_line.setLine(cx, cy,
                                            resolved.x(), resolved.y())
        elif s._draw_arc_step == 2:
            if s._draw_arc_preview is None:
                return
            cx = s._draw_arc_center.x()
            cy = s._draw_arc_center.y()
            r = s._draw_arc_radius
            end_deg = math.degrees(
                math.atan2(-(resolved.y() - cy), resolved.x() - cx)
            )
            span = end_deg - s._draw_arc_start_deg
            if span <= 0:
                span += 360.0
            path = QPainterPath()
            rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            path.arcMoveTo(rect, s._draw_arc_start_deg)
            path.arcTo(rect, s._draw_arc_start_deg, span)
            s._draw_arc_preview.setPath(path)

    def _move_draw_arc(self, event, snapped):
        s = self._scene
        s.preview_pipe.hide()
        if s._draw_arc_step == 0:
            # Before the first click there is no anchor, so no HUD; just track
            # the cursor.
            s.update_preview_node(snapped)
            return
        # Steps 1 and 2 draw through the shared preview updater and publish the
        # resolved point so the DynamicInputHud (decision S1) is the readout.
        # The painted ``_draw_dim_hint`` (block 4) is retired for arc: publish
        # clears it, so a mode that publishes state stops painting block 4.
        s.preview_node.hide()
        # Ctrl angle-snaps the centre→cursor ray (the radius/start bearing at
        # step 1, the sweep end at step 2) to ``_snap_angle_deg`` increments.
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and s._draw_arc_center is not None):
            snapped = s._constrain_angle(s._draw_arc_center, snapped)
        self._preview_from_arc(snapped)
        if s._draw_arc_step == 2:
            self._update_arc_sweep_ref(snapped)   # live sweep radial
        s.publish_placement_state(s._draw_arc_center, snapped)

    def _press_draw_arc(self, event, pos, snapped, item_under, node_under, pipe_under):
        s = self._scene
        if s._draw_arc_step == 0:
            # Click 1 — set centre
            s._draw_arc_center = snapped
            s._draw_arc_step = 1
            s.update_preview_node(snapped)
            s.instructionChanged.emit("Pick start angle point")
            # Create radius preview line (centre → cursor)
            line = QGraphicsLineItem(snapped.x(), snapped.y(),
                                     snapped.x(), snapped.y())
            _prev_pen = QPen(QColor(s._geom_color_lw()[0]), 2, Qt.PenStyle.DashLine)
            _prev_pen.setCosmetic(True)
            line.setPen(_prev_pen)
            line.setZValue(200)
            s.addItem(line)
            s._draw_arc_radius_line = line
        elif s._draw_arc_step == 1:
            # Click 2 — set start point (defines radius + start angle).  Shared
            # with the Dynamic Input rim applier via ``_commit_draw_arc_rim_at``.
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                snapped = s._constrain_angle(s._draw_arc_center, snapped)
            self._commit_draw_arc_rim_at(snapped)
        elif s._draw_arc_step == 2:
            # Click 3 — set end point → commit arc
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                snapped = s._constrain_angle(s._draw_arc_center, snapped)
            self._commit_draw_arc_at(snapped)

    def _advance_arc_to_span_step(self) -> None:
        """Advance an armed arc from step 1 to step 2 (radius → span).

        Removes the radius preview line, creates the arc preview path item, sets
        ``_draw_arc_step = 2`` and emits the "pick end" instruction.  Shared
        verbatim by the mouse step-1 click and the Dynamic Input rim applier so
        both hand off to the span step identically.
        """
        s = self._scene
        s._draw_arc_step = 2
        s.instructionChanged.emit("Pick end angle point")
        # Remove radius line, create arc preview path
        if s._draw_arc_radius_line is not None:
            s.removeItem(s._draw_arc_radius_line)
            s._draw_arc_radius_line = None
        preview = QGraphicsPathItem()
        _prev_pen = QPen(QColor(s._geom_color_lw()[0]), 2, Qt.PenStyle.DashLine)
        _prev_pen.setCosmetic(True)
        preview.setPen(_prev_pen)
        preview.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        preview.setZValue(200)
        s.addItem(preview)
        s._draw_arc_preview = preview
        # Span-step angle guides: 0° datum + start radial (static) + a live sweep
        # radial that tracks the cursor.
        self._clear_arc_ref_lines()
        s._draw_arc_ref_line0 = s._make_ref_line()
        s._draw_arc_ref_start = s._make_ref_line()
        s._draw_arc_ref_sweep = s._make_ref_line()
        self._set_arc_ref_lines()

    def _commit_draw_arc_rim_at(self, point) -> bool:
        """Step-1 applier: fix radius + start angle, then advance to the span step.

        Variant-aware.  In center-first, ``point`` is the rim: radius and start°
        are measured from the stored centre.  In start-first, ``point`` is the
        CENTRE and the first click (``_draw_arc_center``) is the START, so the
        radius/start° are measured from ``point`` to that start, then ``point``
        is stored as the real centre for the span math.

        Shared by the mouse step-1 click (center-first, parity-preserving) and
        the Dynamic Input ``line`` schema, which resolves Length=radius +
        Angle=start° into this rim point.

        Args:
            point: The rim (center-first) or the centre (start-first).

        Returns:
            True when the arc advanced to step 2, False when the radius is under
            the too-small floor (a degenerate rim).
        """
        # Cycle-free variant constant (mirrors placement_input_coordinator.py:43).
        from firepro3d.model_space import _ARC_VARIANT_START
        s = self._scene
        if s._arc_variant == _ARC_VARIANT_START:
            # ``point`` is the centre; the first click is the start point.
            cx, cy = point.x(), point.y()
            start = s._draw_arc_center
            r = math.hypot(start.x() - cx, start.y() - cy)
            if r < 0.01:
                return False
            s._draw_arc_radius = r
            s._draw_arc_start_deg = math.degrees(
                math.atan2(-(start.y() - cy), start.x() - cx)
            )
            # Store the real centre for the span derivation.
            s._draw_arc_center = QPointF(point)
        else:
            # center-first: ``point`` is the rim, measured from the stored centre.
            cx, cy = s._draw_arc_center.x(), s._draw_arc_center.y()
            r = math.hypot(point.x() - cx, point.y() - cy)
            if r < 0.01:
                return False
            s._draw_arc_radius = r
            s._draw_arc_start_deg = math.degrees(
                math.atan2(-(point.y() - cy), point.x() - cx)
            )
        self._advance_arc_to_span_step()
        return True

    def _arc_end_point_for_span(self, span_deg) -> "QPointF":
        """Return the sweep endpoint on the radius circle for ``span_deg``.

        The stored centre/radius/start° plus the typed span give a bearing
        ``start° + span`` (Y-up), projected onto the radius circle.  Feeds
        ``_commit_draw_arc_at``, which re-derives the span from this point, so
        the Dynamic Input span and the mouse third click share one commit.
        """
        s = self._scene
        cx, cy = s._draw_arc_center.x(), s._draw_arc_center.y()
        r = s._draw_arc_radius
        end_deg = s._draw_arc_start_deg + span_deg
        return QPointF(cx + r * math.cos(math.radians(end_deg)),
                       cy - r * math.sin(math.radians(end_deg)))

    def _apply_arc_dynamic_input(self, geometry) -> bool:
        """Route a resolved arc value to the right step's applier.

        Arc's schema is step-dependent, so its applier is too: at step 1 the
        ``line`` schema resolves to a rim QPointF, at step 2 the ``arc_span``
        schema resolves to a ``{"span_deg": …}`` dict.

        Returns:
            The step applier's verdict, or False outside steps 1/2.
        """
        s = self._scene
        if s._draw_arc_step == 1:
            return self._commit_draw_arc_rim_at(geometry)          # QPointF
        if s._draw_arc_step == 2:
            return self._commit_draw_arc_at(
                self._arc_end_point_for_span(geometry["span_deg"]))  # dict
        return False

    def _commit_draw_arc_at(self, end_point) -> bool:
        """Commit the in-progress arc, sweeping to ``end_point``.

        Shared commit path for both the third mouse click and (later) the
        Dynamic Input span value.  Reads the stored centre/radius/start angle,
        derives the span by projecting ``end_point`` onto the radius circle, and
        rejects a degenerate sweep (near 0 or near 360).

        Args:
            end_point: The sweep endpoint; only its bearing from the centre is
                used (the span is projected onto the stored radius circle).

        Returns:
            True when an ``ArcItem`` was committed, False when the arc is
            unarmed (no centre) or the span is under the too-small floor.
        """
        s = self._scene
        if s._draw_arc_center is None:
            return False
        cx, cy = s._draw_arc_center.x(), s._draw_arc_center.y()
        end_deg = math.degrees(
            math.atan2(-(end_point.y() - cy), end_point.x() - cx)
        )
        span = end_deg - s._draw_arc_start_deg
        # Normalise span to positive CCW direction
        if span <= 0:
            span += 360.0
        # Reject near-zero arcs
        if abs(span) < 0.5 or abs(span - 360.0) < 0.5:
            s._show_status("Arc span too small — skipped", timeout=2000)
            return False
        tmpl = s._get_geometry_template()
        _c, _lw = s._geom_color_lw()
        item = ArcItem(s._draw_arc_center, s._draw_arc_radius,
                       s._draw_arc_start_deg, span, _c, _lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        s.addItem(item)
        s._draw_arcs.append(item)
        item.setSelected(True)
        for v in s.views(): v.viewport().update()
        # Clean up previews
        if s._draw_arc_preview is not None:
            s.removeItem(s._draw_arc_preview)
            s._draw_arc_preview = None
        self._clear_arc_ref_lines()
        s._draw_arc_center = None
        s._draw_arc_radius = 0.0
        s._draw_arc_start_deg = 0.0
        s._draw_arc_step = 0
        s.push_undo_state()
        s.instructionChanged.emit("Pick center point")
        return True

    # ── Polygon (3-step centre→radius→rotate, ↑/↓ sides + ←/→ inscribed. The
    #    generic ref factories _make_ref_line/_make_ref_circle stay scene-side;
    #    _inset_polygon (edit-tools staticmethod) stays scene-side) ────────────

    def _clear_polygon_ref_items(self) -> None:
        """Remove the polygon rotate-step reference circle and radial line."""
        s = self._scene
        for attr in ("_polygon_ref_circle", "_polygon_ref_lineA"):
            item = getattr(s, attr, None)
            if item is not None:
                if item.scene() is s:
                    s.removeItem(item)
                setattr(s, attr, None)

    def _polygon_readout(self) -> str:
        """Return the live-state suffix shown in every polygon instruction line.

        Format: ``"{n} sides (↑/↓)  ·  {shape} (←/→)"``.  Called by
        ``_press_polygon``, ``_cycle_polygon_sides``, and
        ``_toggle_polygon_inscribed`` so the full hint always includes the
        current step prompt.
        """
        s = self._scene
        shape = "inscribed" if s._polygon_inscribed else "circumscribed"
        return f"{s._polygon_sides} sides (↑/↓)  ·  {shape} (←/→)"

    def _press_polygon(self, event, pos, snapped, item_under, node_under, pipe_under):
        s = self._scene
        if s._polygon_rotating:
            # Step 2: commit at the pivot→click orientation.
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and s._polygon_center is not None):
                snapped = s._constrain_angle(s._polygon_center, snapped)
            self._commit_polygon_rotated(self._polygon_rotation_angle_to(snapped))
        elif s._polygon_center is None:
            # Step 0: arm the centre.
            s._polygon_center = snapped
            s.update_preview_node(snapped)
            s.instructionChanged.emit(
                f"Pick radius  |  {self._polygon_readout()}")
        else:
            # Step 1: set the radius and advance to the rotate step.
            self._advance_polygon_to_rotate_step(snapped)

    def _polygon_rotation_angle_to(self, cursor) -> float:
        """Return absolute Y-up orientation (degrees from +x) centre→``cursor``.

        0° when the cursor is due-east of the centre (axis-aligned first vertex).
        Falls back to 0° when the centre is unset (guard — rotate step always has
        one).
        """
        c = self._scene._polygon_center
        if c is None:
            return 0.0
        return math.degrees(math.atan2(-(cursor.y() - c.y()),
                                       cursor.x() - c.x()))

    def _advance_polygon_to_rotate_step(self, rim) -> bool:
        """Advance an armed polygon from the sizing step to the rotate step.

        Stores the sized radius (``_polygon_sized_radius``), sets
        ``_polygon_rotating = True``, rebuilds the ghost at rotation 0
        (axis-aligned), and shows the reference circle + a 0° datum line.
        Shared by the mouse second click and the sizing Dynamic Input applier.

        Args:
            rim: The radius-pick point (fully constrained).

        Returns:
            True when advanced; False when rejected (no centre, or radius < 0.5).
        """
        s = self._scene
        c = s._polygon_center
        if c is None:
            return False
        r = math.hypot(rim.x() - c.x(), rim.y() - c.y())
        if r < 0.5:
            s._show_status("Polygon radius too small — skipped", timeout=2000)
            return False
        s._polygon_sized_radius = r
        s._polygon_rotating = True
        # Rebuild ghost axis-aligned (rotation 0) at the fixed radius.
        if s._polygon_preview is not None and s._polygon_preview.scene() is s:
            s.removeItem(s._polygon_preview)
            s._polygon_preview = None
        s._polygon_preview = self._build_polygon_ghost(c, r, 0.0)
        # Reference circle centred on the centre at the sized radius.
        self._clear_polygon_ref_items()
        s._polygon_ref_circle = s._make_ref_circle()
        s._polygon_ref_circle.setRect(
            c.x() - r, c.y() - r, 2 * r, 2 * r)
        # Radial reference line (0° datum) from centre eastwards.
        s._polygon_ref_lineA = s._make_ref_line()
        s._polygon_ref_lineA.setLine(c.x(), c.y(), c.x() + r, c.y())
        s.clear_placement_state()
        s.instructionChanged.emit(
            f"Pick rotation angle  |  {self._polygon_readout()}")
        return True

    def _apply_polygon_dynamic_input(self, geometry) -> bool:
        """Route a resolved polygon value to the right step's applier.

        At the sizing step the ``polygon`` schema resolves to a radius QPointF
        (advance to the rotate step); at the rotate step the ``rotation`` schema
        resolves to a ``{"angle_deg": …}`` dict (commit).  Mirrors
        ``_apply_rectangle_dynamic_input``.
        """
        if self._scene._polygon_rotating:
            return self._commit_polygon_rotated(geometry["angle_deg"])   # dict
        return self._advance_polygon_to_rotate_step(geometry)             # QPointF

    def _commit_polygon_rotated(self, angle_deg) -> bool:
        """Commit the sized polygon at ``angle_deg`` orientation (Y-up, degrees).

        Builds ``RegularPolygonItem`` from the stored centre and sized radius,
        clears all placement state, and pushes undo.  Shared by the third mouse
        click and the ``rotation`` Dynamic Input value.

        Args:
            angle_deg: Absolute orientation, Y-up degrees from +x.

        Returns:
            True when committed; False when sizing state is missing.
        """
        s = self._scene
        c = s._polygon_center
        r = s._polygon_sized_radius
        if c is None or r is None:
            return False
        tmpl = s._get_geometry_template()
        _c, _lw = s._geom_color_lw()
        item = RegularPolygonItem(c, sides=s._polygon_sides, radius_mm=r,
                                  rotation_deg=angle_deg,
                                  inscribed=s._polygon_inscribed,
                                  color=_c, lineweight=_lw)
        item.level = tmpl.level
        item._level_offset_mm = getattr(tmpl, "_level_offset_mm", 0.0)
        s.addItem(item)
        s._draw_polygons.append(item)
        item.setSelected(True)
        # Remove preview ghost.
        if s._polygon_preview is not None:
            if s._polygon_preview.scene() is s:
                s.removeItem(s._polygon_preview)
            s._polygon_preview = None
        # Clear all placement state.
        s._polygon_center = None
        s._polygon_rotating = False
        s._polygon_sized_radius = None
        self._clear_polygon_ref_items()
        s.clear_placement_state()
        for v in s.views(): v.viewport().update()
        s.push_undo_state()
        s.instructionChanged.emit(
            f"Pick centre point  |  {self._polygon_readout()}")
        return True

    def _commit_polygon_at(self, rim):
        """Legacy 2-step commit: radius-pick point carries both radius and rotation.

        Kept for backward compatibility with the HUD ``polygon`` schema resolver
        which returns a QPointF on the rim circle.  In 3-step placement this is
        only reached via ``_apply_polygon_dynamic_input`` at the sizing step,
        which calls ``_advance_polygon_to_rotate_step`` instead — so this method
        is no longer the commit path.  It is preserved so external callers (e.g.
        tests that pre-date the 3-step change) can still advance the sizing step
        by passing a point.
        """
        return self._advance_polygon_to_rotate_step(rim)

    def _build_polygon_ghost(self, center, radius, rotation_deg) -> "RegularPolygonItem":
        """Create and return a dashed ghost RegularPolygonItem added to the scene."""
        s = self._scene
        _c, _lw = s._geom_color_lw()
        ghost = RegularPolygonItem(center, sides=s._polygon_sides, radius_mm=radius,
                                   rotation_deg=rotation_deg,
                                   inscribed=s._polygon_inscribed,
                                   color=_c, lineweight=_lw)
        pen = QPen(QColor(_c), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        ghost.setPen(pen)
        ghost.setZValue(200)
        ghost.setFlag(ghost.GraphicsItemFlag.ItemIsSelectable, False)
        s.addItem(ghost)
        return ghost

    def _preview_from_polygon(self, tip):
        """Live ghost of the polygon during the sizing step (centre→tip).

        During the sizing step, tip sets both radius and rotation; the ghost
        tracks both live.  During the rotate step, use ``_preview_polygon_rotation``
        instead (which keeps a fixed radius and only spins the ghost).
        """
        s = self._scene
        if s._polygon_center is None:
            return
        c = s._polygon_center
        dx, dy = tip.x() - c.x(), tip.y() - c.y()
        r = math.hypot(dx, dy)
        if r < 0.5:
            return
        # During sizing step, rotation tracks the cursor bearing.
        rot = 0.0  # axis-aligned during sizing step (rotation added at step 2)
        if s._polygon_preview is not None and s._polygon_preview.scene() is s:
            s.removeItem(s._polygon_preview)
        s._polygon_preview = self._build_polygon_ghost(c, r, rot)
        # Also update / create the reference circle (shows bounding circle).
        if s._polygon_ref_circle is None:
            s._polygon_ref_circle = s._make_ref_circle()
        s._polygon_ref_circle.setRect(c.x() - r, c.y() - r, 2 * r, 2 * r)

    def _preview_polygon_rotation(self, angle_deg) -> None:
        """Spin the sized-radius polygon ghost to ``angle_deg`` during rotate step.

        Mirrors ``_preview_rectangle_rotation``: only the ghost's orientation
        changes, the radius is fixed at ``_polygon_sized_radius``.  Also updates
        the radial reference line.  A no-op until the ghost and centre exist.
        """
        s = self._scene
        c = s._polygon_center
        r = s._polygon_sized_radius
        if c is None or r is None:
            return
        # Rebuild ghost at the fixed radius and new rotation.
        if s._polygon_preview is not None and s._polygon_preview.scene() is s:
            s.removeItem(s._polygon_preview)
        s._polygon_preview = self._build_polygon_ghost(c, r, angle_deg)
        # Update the radial reference line to follow the cursor heading.
        if s._polygon_ref_lineA is not None:
            rad = math.radians(angle_deg)
            s._polygon_ref_lineA.setLine(
                c.x(), c.y(),
                c.x() + r * math.cos(rad),
                c.y() - r * math.sin(rad))  # Y-up: subtract sin

    def _move_polygon(self, event, snapped):
        s = self._scene
        if s._polygon_rotating:
            # Rotate step: ghost is fixed-radius, only orientation changes.
            s.preview_node.hide()
            s.preview_pipe.hide()
            if (event is not None
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    and s._polygon_center is not None):
                snapped = s._constrain_angle(s._polygon_center, snapped)
            angle = self._polygon_rotation_angle_to(snapped)
            self._preview_polygon_rotation(angle)
            s.publish_placement_state(s._polygon_center, snapped)
            return
        if s._polygon_center is None:
            s.update_preview_node(snapped)   # cursor preview before first click
        else:
            s.preview_node.hide()
        s.preview_pipe.hide()
        if s._polygon_center is not None:
            self._preview_from_polygon(snapped)
            s.publish_placement_state(s._polygon_center, snapped)

    def _cycle_polygon_sides(self, direction: int):
        s = self._scene
        s._polygon_sides = max(3, min(120, s._polygon_sides + direction))
        if s._last_scene_pos is not None:
            if s._polygon_rotating:
                angle = self._polygon_rotation_angle_to(s._last_scene_pos)
                self._preview_polygon_rotation(angle)
            else:
                self._preview_from_polygon(s._last_scene_pos)
        if s._polygon_rotating:
            s.instructionChanged.emit(
                f"Pick rotation angle  |  {self._polygon_readout()}")
        elif s._polygon_center is not None:
            s.instructionChanged.emit(
                f"Pick radius  |  {self._polygon_readout()}")
        else:
            s.instructionChanged.emit(
                f"Pick centre point  |  {self._polygon_readout()}")

    def _toggle_polygon_inscribed(self):
        s = self._scene
        s._polygon_inscribed = not s._polygon_inscribed
        if s._last_scene_pos is not None:
            if s._polygon_rotating:
                angle = self._polygon_rotation_angle_to(s._last_scene_pos)
                self._preview_polygon_rotation(angle)
            else:
                self._preview_from_polygon(s._last_scene_pos)
        if s._polygon_rotating:
            s.instructionChanged.emit(
                f"Pick rotation angle  |  {self._polygon_readout()}")
        elif s._polygon_center is not None:
            s.instructionChanged.emit(
                f"Pick radius  |  {self._polygon_readout()}")
        else:
            s.instructionChanged.emit(
                f"Pick centre point  |  {self._polygon_readout()}")
