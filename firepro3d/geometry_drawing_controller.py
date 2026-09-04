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
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem

from .construction_geometry import CircleItem


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
