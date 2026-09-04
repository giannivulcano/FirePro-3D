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

from .construction_geometry import CircleItem, PolylineItem, RectangleItem
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
