"""Arrangements tab internals: strip canvas (drag controller + pool in Task 9/10).

Governing spec: docs/specs/titleblock-template-system.md rev 3 (DD-16/17).
Manual mouse tracking ONLY — native Qt DnD is banned here (testability).
The canvas hosts ONE TitleBlockTemplateItem and hit-tests solved rects;
gestures mutate the layout via the pure ops in titleblock_template.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from PyQt6.QtCore import (
    QEvent, QPointF, QRectF, Qt, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QKeyEvent, QMouseEvent, QPainter, QPen,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsView,
)

from .constants import TB_INSERT_BAND_PX
from .titleblock_template import TemplateLayout, solve_layout


@dataclass
class DropZone:
    """Zone classification returned by :meth:`StripCanvas.zone_at` (DD-16).

    Attributes:
        kind: One of ``"insert"``, ``"pair_left"``, ``"pair_right"``,
            ``"full"``, or ``"outside"``.
        row_index: For ``"insert"``: insertion index 0..n_rows (append = n_rows).
            For ``"pair_left"``/``"pair_right"``/``"full"``: the target row
            index in ``layout.rows``.  ``-1`` when not applicable.
    """

    kind: str
    row_index: int = -1


# ─────────────────────────────────────────────────────────────────────────────
# Zoom factor per wheel notch
# ─────────────────────────────────────────────────────────────────────────────
_ZOOM_FACTOR = 1.15


class StripCanvas(QGraphicsView):
    """True-render strip canvas for the Arrangements tab (DD-17).

    Hosts a single :class:`~firepro3d.paper_space.TitleBlockTemplateItem` on
    a private ``QGraphicsScene`` and implements hit-testing, zone detection,
    selection, and the Delete-key unplace signal entirely through manual mouse
    tracking — no native Qt drag-and-drop (spec constraint, DD-16).

    Signals:
        selectionChanged: Emitted with the newly selected ``field_id`` (or
            ``""`` when selection is cleared).
        unplaceRequested: Emitted with the selected ``field_id`` when the
            user presses Delete while a cell is selected.

    Notes:
        ``refresh()`` calls ``scene().clear()`` and is therefore unsafe to
        call from within a QGraphicsItem event handler (project memory:
        *scene.clear() in item event frames* — see MEMORY.md).  Always invoke
        it from outside the scene's paint/event stack (e.g. from a completed
        gesture callback).
    """

    #: Emitted with the field_id of the newly selected cell (or "" for clear).
    selectionChanged = pyqtSignal(str)

    #: Emitted with the field_id of the selected cell on Delete key press.
    unplaceRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        # Provider: callable () -> (TemplateLayout, paper_w_mm, paper_h_mm, values)
        self._provider = None

        # Most recently solved layout — None until refresh() is called.
        self.solved = None
        # Reference to the TemplateLayout used in the last solve (for zone logic).
        self._layout_ref: TemplateLayout | None = None

        # Selection state
        self.selected_field_id: str = ""

        # Drag state stubs — populated by Task 9 DragController; read here for
        # drawForeground overlays.
        self._zone_hint: DropZone | None = None
        self._ghost_pos: QPointF | None = None
        self._ghost_label: str = ""

        # Press position (viewport px) — stored for Task 9's gesture threshold.
        self._press_view_pos: QPointF | None = None
        # Field id under press — used by Task 9 to initiate a drag.
        self._drag_field_id: str = ""

    # ── Provider ──────────────────────────────────────────────────────────────

    def set_provider(self, provider) -> None:
        """Set the data provider callable.

        Args:
            provider: Callable with no arguments that returns
                ``(TemplateLayout, paper_w_mm, paper_h_mm, values)``
                where *values* is a ``dict`` of resolved field values.
        """
        self._provider = provider

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Re-solve the layout and rebuild the scene.

        Calls ``scene().clear()`` then adds one
        :class:`~firepro3d.paper_space.TitleBlockTemplateItem`.
        The item's ``ItemIsSelectable`` flag is left OFF — the canvas owns all
        selection state.

        Do NOT call this from within a scene-item event handler; ``clear()``
        destroys items mid-event and causes silent native crashes (see project
        memory: *Never scene.clear() in item event frames*).
        """
        if self._provider is None:
            return

        lay, pw, ph, values = self._provider()
        self._layout_ref = lay
        self.solved = solve_layout(lay, pw, ph, values)

        self._scene.clear()

        # Import here to avoid a circular import at module level
        # (paper_space imports nothing from titleblock_arrange).
        from .paper_space import TitleBlockTemplateItem  # noqa: PLC0415
        item = TitleBlockTemplateItem(self.solved, lay, values)
        item.setFlag(
            item.GraphicsItemFlag.ItemIsSelectable, False
        )
        self._scene.addItem(item)

        sr = self.solved.strip_rect
        self._scene.setSceneRect(sr.adjusted(-5, -5, 5, 5))

        self.viewport().update()

    # ── Zoom / fit ────────────────────────────────────────────────────────────

    def fit_strip(self) -> None:
        """Fit the entire strip into the viewport (default zoom after refresh).

        Uses ``KeepAspectRatio`` so the strip is never clipped.
        """
        if self.solved is None:
            return
        sr = self.solved.strip_rect
        self.fitInView(sr.adjusted(-2, -2, 2, 2),
                       Qt.AspectRatioMode.KeepAspectRatio)

    # ── Hit testing ───────────────────────────────────────────────────────────

    def cell_index_at(self, scene_pos: QPointF) -> int:
        """Return the flat cell index whose rect contains *scene_pos*, or -1.

        Args:
            scene_pos: Point in scene (mm) coordinates.

        Returns:
            Flat index into ``solved.cell_rects`` / ``solved.cell_field_ids``,
            or ``-1`` when no cell contains the point.
        """
        if self.solved is None:
            return -1
        for i, r in enumerate(self.solved.cell_rects):
            if r.contains(scene_pos):
                return i
        return -1

    def _row_at(self, scene_pos: QPointF) -> int:
        """Return the row index (into ``layout.rows``) under *scene_pos*, or -1.

        Uses the first-cell rect of each row's span to determine the y band
        [top, bottom) occupied by that row.

        Args:
            scene_pos: Point in scene (mm) coordinates.

        Returns:
            Row index in ``layout.rows``, or ``-1``.
        """
        if self.solved is None:
            return -1
        for ri, (first_idx, _n) in enumerate(self.solved.row_spans):
            r = self.solved.cell_rects[first_idx]
            if r.top() <= scene_pos.y() < r.bottom():
                return ri
        return -1

    # ── Zone detection ────────────────────────────────────────────────────────

    def zone_at(self, scene_pos: QPointF,
                dragged_field_id: str = "") -> DropZone:
        """Classify the drop zone at *scene_pos* for a drag gesture (DD-16).

        The returned :class:`DropZone` drives visual overlays (Task 9) and the
        drop handler (Task 9).  This method is pure — it does not mutate state.

        Zone rules (in priority order):

        1. ``solved`` is None → ``outside``.
        2. Outside the strip (inflated by ``2 × band_mm`` in scene mm) → ``outside``.
        3. Within the per-boundary hit-band around a row boundary (top of strip
           = boundary 0; each row's first-cell bottom = boundary k) → ``insert``
           at k.  The per-boundary band is ``min(band_mm, quarter of each adjacent
           row height)`` so the interior of every row is always reachable even
           when rows are small relative to the pixel band.
        4. Inside a row:

           * Row with 1 slot, sole occupant == ``dragged_field_id``
             → ``full`` (own single row: no valid gesture).
           * Row with 1 slot, occupant != ``dragged_field_id``
             → ``pair_left`` or ``pair_right`` by x vs strip centre.
           * Row with 2 slots, ``dragged_field_id`` is a member
             → ``pair_left`` / ``pair_right`` (swap targeting by x vs strip centre).
           * Row with 2 slots, ``dragged_field_id`` is NOT a member
             → ``full`` (already full; no room).

        5. Below all rows, still inside the strip → ``insert`` at ``len(rows)``.

        Args:
            scene_pos: Query point in scene (mm) coordinates.
            dragged_field_id: Field being dragged, or ``""`` for pure
                hit-testing (affects pair/full classification).

        Returns:
            A :class:`DropZone` describing the zone.
        """
        if self.solved is None:
            return DropZone("outside")

        sr = self.solved.strip_rect
        band_mm = self._px_to_mm(TB_INSERT_BAND_PX)
        inflated = sr.adjusted(-2 * band_mm, -2 * band_mm,
                               2 * band_mm, 2 * band_mm)
        if not inflated.contains(scene_pos):
            return DropZone("outside")

        # Build per-row heights for adaptive band capping.
        row_heights: list[float] = []
        for first_idx, _n in self.solved.row_spans:
            row_heights.append(self.solved.cell_rects[first_idx].height())

        # Build boundary list: strip top + bottom of each row's first cell.
        # boundary[k] is the y-coordinate of row boundary k; inserting at k
        # means "before row k" (boundary 0 = before row 0, boundary n = append).
        # For each boundary k, compute an adaptive per-band that is at most
        # half the height of each adjacent row, ensuring the row interior is
        # always reachable regardless of pixel scale.
        boundaries: list[float] = [sr.top()]
        for first_idx, _n in self.solved.row_spans:
            boundaries.append(self.solved.cell_rects[first_idx].bottom())

        # boundary k sits between row k-1 (above) and row k (below).
        # Cap the band to a quarter of each adjacent row's height so that the
        # interior (midpoint) of every row remains reachable regardless of the
        # pixel-to-mm scale.  A quarter-height cap guarantees the centre of any
        # row is at least one quarter-height clear of a boundary band.
        n_rows = len(row_heights)
        for k, by in enumerate(boundaries):
            qtr_above = (row_heights[k - 1] / 4) if k > 0 else float("inf")
            qtr_below = row_heights[k] / 4 if k < n_rows else float("inf")
            eff_band = min(band_mm, qtr_above, qtr_below)
            if abs(scene_pos.y() - by) < eff_band:
                return DropZone("insert", row_index=k)

        # Determine which row the cursor is in.
        row_i = self._row_at(scene_pos)

        if row_i == -1:
            # Could be above the strip (cursor in the inflated margin above top)
            # or below all rows inside the strip.  Distinguish by y position.
            if scene_pos.y() < sr.top():
                return DropZone("insert", row_index=0)
            # Below all rows but inside the strip (and not on the last boundary).
            return DropZone("insert", row_index=len(self.solved.row_spans))

        # Classify within the row.
        lay = self._layout_ref
        if lay is None:
            return DropZone("outside")

        row = lay.rows[row_i]
        member_ids = [s.field_id for s in row]
        n = len(row)

        row_cx = sr.center().x()  # strip centre — row always spans full width

        if n == 1:
            sole_id = member_ids[0]
            if dragged_field_id and dragged_field_id == sole_id:
                # Dragging a field over its own single-slot row → no valid op.
                return DropZone("full", row_index=row_i)
            # Offer pair half-zones.
            if scene_pos.x() < row_cx:
                return DropZone("pair_left", row_index=row_i)
            return DropZone("pair_right", row_index=row_i)

        # n == 2
        if dragged_field_id and dragged_field_id in member_ids:
            # Member of this paired row: allow swap targeting.
            if scene_pos.x() < row_cx:
                return DropZone("pair_left", row_index=row_i)
            return DropZone("pair_right", row_index=row_i)
        # Outsider trying to enter a full paired row → full cue.
        return DropZone("full", row_index=row_i)

    # ── Coordinate conversion ─────────────────────────────────────────────────

    def _px_to_mm(self, px: float) -> float:
        """Convert viewport pixels to scene mm at the current zoom level.

        Uses the horizontal scale factor from the view transform.  Guards
        against near-zero scale (e.g. before the view has been laid out).

        Args:
            px: Pixel size to convert.

        Returns:
            Equivalent size in scene mm units.
        """
        scale = max(self.transform().m11(), 1e-6)
        return px / scale

    # ── Selection ─────────────────────────────────────────────────────────────

    def select_at(self, scene_pos: QPointF) -> None:
        """Select the cell under *scene_pos*, or clear selection if empty.

        Emits :attr:`selectionChanged` with the new ``field_id`` (or ``""``).

        Args:
            scene_pos: Click point in scene (mm) coordinates.
        """
        idx = self.cell_index_at(scene_pos)
        if idx >= 0:
            fid = self.solved.cell_field_ids[idx]
        else:
            fid = ""
        if fid != self.selected_field_id:
            self.selected_field_id = fid
            self.selectionChanged.emit(fid)
        else:
            # Re-clicking the same cell: still emit to allow callers to react.
            self.selectionChanged.emit(fid)
        self.viewport().update()

    # ── Overlay painting ─────────────────────────────────────────────────────

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        """Paint interaction overlays on top of the rendered item (DD-17).

        Draws:

        * **Selection outline** — blue (#2f80ed) pen around every cell whose
          ``field_id`` matches ``selected_field_id``.
        * **Zone hint overlays** — driven by ``_zone_hint`` (set by Task 9):

          - ``insert`` → blue horizontal line across the strip at the boundary y.
          - ``pair_left`` / ``pair_right`` → translucent blue half-row fill.
          - ``full`` → translucent red full-row fill.

        * **Ghost label** — semi-transparent dark-gray text at ``_ghost_pos``
          (set by Task 9 during a drag).

        Overlays are painted in foreground coordinates (same as scene mm).
        The renderer item itself is never mutated.

        Args:
            painter: Active QPainter.
            rect: Dirty rect (scene coordinates).
        """
        super().drawForeground(painter, rect)
        if self.solved is None:
            return

        sel_pen_w = self._px_to_mm(2)

        # ── Selection outline ─────────────────────────────────────────────────
        if self.selected_field_id:
            pen = QPen(QColor("#2f80ed"), sel_pen_w)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for i, fid in enumerate(self.solved.cell_field_ids):
                if fid == self.selected_field_id:
                    painter.drawRect(self.solved.cell_rects[i])

        # ── Zone hint overlays ────────────────────────────────────────────────
        zone = self._zone_hint
        if zone is not None and zone.kind != "outside":
            sr = self.solved.strip_rect
            ri = zone.row_index

            if zone.kind == "insert":
                # Horizontal insertion line at the row boundary y.
                boundaries: list[float] = [sr.top()]
                for first_idx, _ in self.solved.row_spans:
                    boundaries.append(
                        self.solved.cell_rects[first_idx].bottom())
                if 0 <= ri < len(boundaries):
                    by = boundaries[ri]
                    pen = QPen(QColor("#2f80ed"), sel_pen_w)
                    painter.setPen(pen)
                    painter.drawLine(QPointF(sr.left(), by),
                                     QPointF(sr.right(), by))

            elif zone.kind in ("pair_left", "pair_right", "full"):
                if 0 <= ri < len(self.solved.row_spans):
                    row_rect = self._row_rect(ri)
                    if zone.kind == "full":
                        color = QColor("#2f80ed")
                        color.setAlpha(40)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(color))
                        painter.drawRect(row_rect)
                    else:
                        color = QColor("#2f80ed")
                        color.setAlpha(60)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(color))
                        cx = row_rect.center().x()
                        if zone.kind == "pair_left":
                            half = QRectF(row_rect.left(), row_rect.top(),
                                          cx - row_rect.left(), row_rect.height())
                        else:
                            half = QRectF(cx, row_rect.top(),
                                          row_rect.right() - cx, row_rect.height())
                        painter.drawRect(half)

        # ── Ghost label ───────────────────────────────────────────────────────
        if self._ghost_pos is not None and self._ghost_label:
            painter.setPen(QColor("#555555"))
            painter.drawText(self._ghost_pos, self._ghost_label)

    def _row_rect(self, row_index: int) -> QRectF:
        """Compute the full-width row rect for *row_index* (scene mm).

        Derived from the strip's x span and the first cell's y span for that
        row.

        Args:
            row_index: Index into ``solved.row_spans``.

        Returns:
            A ``QRectF`` covering the full strip width for the given row.
        """
        sr = self.solved.strip_rect
        first_idx, n = self.solved.row_spans[row_index]
        r = self.solved.cell_rects[first_idx]
        return QRectF(sr.left(), r.top(), sr.width(), r.height())

    # ── Keyboard handling ─────────────────────────────────────────────────────

    def event(self, ev: QEvent) -> bool:
        """Accept the Delete ShortcutOverride so KeyPress is delivered (project memory).

        Qt routes the Delete key through a ShortcutOverride check first;
        if the view does not accept it the KeyPress event is never seen.

        Args:
            ev: The event to process.

        Returns:
            ``True`` if the event was consumed; otherwise delegates to super.
        """
        if (ev.type() == QEvent.Type.ShortcutOverride
                and isinstance(ev, QKeyEvent)
                and ev.key() == Qt.Key.Key_Delete):
            ev.accept()
            return True
        return super().event(ev)

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        """Handle Delete key to unplace the selected field.

        Emits :attr:`unplaceRequested` with the current ``selected_field_id``
        when Delete is pressed while a field is selected.  Esc is reserved for
        Task 9 (cancel in-flight drag).

        Args:
            ev: The key press event.
        """
        if ev.key() == Qt.Key.Key_Delete and self.selected_field_id:
            self.unplaceRequested.emit(self.selected_field_id)
            ev.accept()
            return
        super().keyPressEvent(ev)

    # ── Mouse handling ────────────────────────────────────────────────────────

    def wheelEvent(self, ev: QWheelEvent) -> None:
        """Zoom in/out by a fixed factor per wheel notch.

        Args:
            ev: The wheel event.
        """
        delta = ev.angleDelta().y()
        if delta > 0:
            self.scale(_ZOOM_FACTOR, _ZOOM_FACTOR)
        elif delta < 0:
            self.scale(1.0 / _ZOOM_FACTOR, 1.0 / _ZOOM_FACTOR)
        ev.accept()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        """Handle left-button press: select the cell under the cursor.

        Also stores ``_press_view_pos`` and ``_drag_field_id`` for Task 9's
        gesture threshold.

        Args:
            ev: The mouse press event.
        """
        if ev.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(ev.position().toPoint())
            self.select_at(scene_pos)
            self._press_view_pos = ev.position()
            # Capture the field under the press for Task 9.
            idx = self.cell_index_at(scene_pos)
            self._drag_field_id = (
                self.solved.cell_field_ids[idx]
                if (self.solved is not None and idx >= 0)
                else ""
            )
            ev.accept()
        else:
            super().mousePressEvent(ev)
