"""Arrangements tab internals: strip canvas, pool list, and tab assembly.

Governing spec: docs/specs/titleblock-template-system.md rev 3 (DD-16/17).
Manual mouse tracking ONLY — native Qt DnD is banned here (testability).
The canvas hosts ONE TitleBlockTemplateItem and hit-tests solved rects;
gestures mutate the layout via the pure ops in titleblock_template.
:class:`ArrangementsTab` assembles the three DD-17 columns (pool | canvas |
placement props) as a dumb widget — signals out, ``refresh(layout)`` in.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import (
    QEvent, QPointF, QRectF, Qt, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QFocusEvent, QKeyEvent, QMouseEvent, QPainter, QPen,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QGraphicsScene, QGraphicsView, QGroupBox,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from .constants import TB_INSERT_BAND_PX, TB_POOL_CARD_W
from .dimension_edit import DimensionEdit
from .scale_manager import ScaleManager
from .titleblock_template import (
    Slot, TemplateLayout, move_field, pair_field, solve_layout, unplace_field,
)

# Module-level ScaleManager used as the dimension parser (same pattern as
# titleblock_editor._sm: standalone → bare numbers parse as mm).
_sm = ScaleManager()


@dataclass
class DropZone:
    """Zone classification returned by :meth:`StripCanvas.zone_at` (DD-16).

    Attributes:
        kind: One of ``"insert"``, ``"pair_left"``, ``"pair_right"``,
            ``"full"``, or ``"outside"``.
        row_index: Always a ``layout.rows`` index (not a solved-row index).
            For ``"insert"``: insertion index 0..len(layout.rows) (append =
            len).  For ``"pair_left"``/``"pair_right"``/``"full"``: the
            originating ``layout.rows`` index for the target row (translated
            via ``SolvedLayout.row_layout_indices``).  ``-1`` when not
            applicable (``"outside"``).
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
        gestureStarting: Emitted ONCE per mutating gesture, BEFORE the layout
            is touched — the editor dialog pushes its undo snapshot here.
            Never emitted for dead drops (zone ``full``, no-op reinsert,
            own-half pair) or cancelled drags (Esc).
        gestureCompleted: Emitted ONCE per mutating gesture, AFTER the layout
            mutation and ``refresh()`` — the dialog refreshes dependents here.

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

    #: Emitted once per mutating gesture BEFORE mutation (undo snapshot hook).
    gestureStarting = pyqtSignal()

    #: Emitted once per mutating gesture AFTER mutation + refresh().
    gestureCompleted = pyqtSignal()

    #: Manhattan distance (viewport px) a press must travel to become a drag.
    DRAG_THRESHOLD_PX = 4

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

        # Drag overlay state — consumed by drawForeground.
        self._zone_hint: DropZone | None = None
        self._ghost_pos: QPointF | None = None
        self._ghost_label: str = ""

        # Drag state machine.
        self._press_view_pos: QPointF | None = None
        self._drag_field_id: str = ""
        self._dragging: bool = False

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

        # Deferred for import cost, not for a cycle: paper_space is a large
        # import hub and is only needed once a canvas actually renders.
        # (There is no circular import — paper_space does not import this
        # module.)
        from .paper_space import TitleBlockTemplateItem  # noqa: PLC0415
        item = TitleBlockTemplateItem(self.solved, lay, values)
        item.setFlag(
            item.GraphicsItemFlag.ItemIsSelectable, False
        )
        self._scene.addItem(item)

        sr = self.solved.strip_rect
        self._scene.setSceneRect(sr.adjusted(-5, -5, 5, 5))

        # Clear stale selection: if the selected field is no longer rendered,
        # reset it and notify callers.
        if (self.selected_field_id
                and self.selected_field_id not in self.solved.cell_field_ids):
            self.selected_field_id = ""
            self.selectionChanged.emit("")

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
        """Return the solved-row index under *scene_pos*, or -1.

        Uses the first-cell rect of each row's span to determine the y band
        [top, bottom) occupied by that row.

        Args:
            scene_pos: Point in scene (mm) coordinates.

        Returns:
            Solved-row index (index into ``solved.row_spans``), or ``-1``.
        """
        if self.solved is None:
            return -1
        for ri, (first_idx, _n) in enumerate(self.solved.row_spans):
            r = self.solved.cell_rects[first_idx]
            if r.top() <= scene_pos.y() < r.bottom():
                return ri
        return -1

    def _boundaries(self) -> list[float]:
        """Return the list of insert-boundary y-coordinates (scene mm).

        ``boundaries[k]`` is the y-coordinate of row boundary k:

        * boundary 0 = top of the strip (insert before solved row 0)
        * boundary k = bottom of solved row k-1 (insert before solved row k)

        Used by :meth:`zone_at` and :meth:`drawForeground`.
        """
        sr = self.solved.strip_rect
        result: list[float] = [sr.top()]
        for first_idx, _n in self.solved.row_spans:
            result.append(self.solved.cell_rects[first_idx].bottom())
        return result

    def _solved_insert_to_layout(self, solved_k: int) -> int:
        """Translate a solved insertion index to a ``layout.rows`` insertion index.

        Inserting before solved row *k* = inserting before layout row
        ``row_layout_indices[k]``.  Appending (``k == len(row_spans)``) maps to
        ``len(layout.rows)`` (append to layout rows too).

        Args:
            solved_k: Solved-row insertion index (0..n_solved_rows inclusive).

        Returns:
            Corresponding ``layout.rows`` insertion index.
        """
        rli = self.solved.row_layout_indices
        if solved_k < len(rli):
            return rli[solved_k]
        # Append: after all solved rows → after all layout rows.
        lay = self._layout_ref
        return len(lay.rows) if lay is not None else solved_k

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
        # a quarter of the height of each adjacent row, ensuring the row interior
        # is always reachable regardless of pixel scale.
        boundaries = self._boundaries()

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
                # Insert index is a layout.rows index.
                # Inserting before solved row k = before layout row
                # row_layout_indices[k]; appending (k == n_rows) = len(lay.rows).
                lay_insert = self._solved_insert_to_layout(k)
                return DropZone("insert", row_index=lay_insert)

        # Determine which solved row the cursor is in.
        row_i = self._row_at(scene_pos)

        if row_i == -1:
            # Could be above the strip (cursor in the inflated margin above top)
            # or below all rows inside the strip.  Distinguish by y position.
            if scene_pos.y() < sr.top():
                lay_insert = self._solved_insert_to_layout(0)
                return DropZone("insert", row_index=lay_insert)
            # Below all rows but inside the strip (and not on the last boundary).
            lay_insert = self._solved_insert_to_layout(len(self.solved.row_spans))
            return DropZone("insert", row_index=lay_insert)

        # Translate solved row index → layout row index for returned DropZone.
        lay_row_index = self.solved.row_layout_indices[row_i]

        # Classify within the row using the SOLVED row (what's visibly rendered).
        # n_solved = number of cells actually rendered in this solved row.
        first_solved_idx, n_solved = self.solved.row_spans[row_i]
        solved_cell_ids = self.solved.cell_field_ids[
            first_solved_idx: first_solved_idx + n_solved]

        row_cx = sr.center().x()  # strip centre — row always spans full width

        if n_solved == 1:
            sole_id = solved_cell_ids[0]
            if dragged_field_id and dragged_field_id == sole_id:
                # Dragging a field over its own single-slot row → no valid op.
                return DropZone("full", row_index=lay_row_index)
            # Offer pair half-zones: one rendered cell, room for a partner.
            if scene_pos.x() < row_cx:
                return DropZone("pair_left", row_index=lay_row_index)
            return DropZone("pair_right", row_index=lay_row_index)

        # n_solved == 2: two cells rendered in this row.
        if dragged_field_id and dragged_field_id in solved_cell_ids:
            # Member of this paired row: allow swap targeting.
            if scene_pos.x() < row_cx:
                return DropZone("pair_left", row_index=lay_row_index)
            return DropZone("pair_right", row_index=lay_row_index)
        # Outsider trying to enter a full paired row → full cue.
        return DropZone("full", row_index=lay_row_index)

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
            # zone.row_index is always a layout.rows index; translate to
            # a solved-row index for visual lookup in boundaries/_row_rect.
            rli = self.solved.row_layout_indices
            lay_ri = zone.row_index

            if zone.kind == "insert":
                # Horizontal insertion line at the row boundary y.
                # Find solved boundary index: boundary k = insert before solved row k.
                # Translate layout insert index back to a solved boundary index.
                # boundary 0 = strip top; boundary k = bottom of solved row k-1.
                boundaries = self._boundaries()
                # Find solved boundary index whose layout translation == lay_ri.
                # boundary k corresponds to "before solved row k" → layout index rli[k].
                # Append (k == n_solved) → len(lay.rows).
                lay = self._layout_ref
                n_solved = len(rli)
                solved_bk = None
                for bk in range(n_solved + 1):
                    bk_lay = rli[bk] if bk < n_solved else (
                        len(lay.rows) if lay else n_solved)
                    if bk_lay == lay_ri:
                        solved_bk = bk
                        break
                if solved_bk is not None and 0 <= solved_bk < len(boundaries):
                    by = boundaries[solved_bk]
                    pen = QPen(QColor("#2f80ed"), sel_pen_w)
                    painter.setPen(pen)
                    painter.drawLine(QPointF(sr.left(), by),
                                     QPointF(sr.right(), by))

            elif zone.kind in ("pair_left", "pair_right", "full"):
                # Translate layout row index to solved row index.
                solved_ri = next(
                    (k for k, li in enumerate(rli) if li == lay_ri), None)
                if solved_ri is not None and 0 <= solved_ri < len(self.solved.row_spans):
                    row_rect = self._row_rect(solved_ri)
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
        """Handle Esc (cancel in-flight drag) and Delete (unplace selection).

        Esc while dragging calls :meth:`cancel_drag` — no mutation, no
        gesture signals (DD-16: cancelled drag = no undo snapshot).  The
        Esc branch runs BEFORE the Delete branch; a mouse release arriving
        after the cancel is a no-op because ``cancel_drag`` clears both
        ``_dragging`` and ``_drag_field_id``.

        Emits :attr:`unplaceRequested` with the current ``selected_field_id``
        when Delete is pressed while a field is selected.

        Args:
            ev: The key press event.
        """
        if ev.key() == Qt.Key.Key_Escape and self._dragging:
            self.cancel_drag()
            ev.accept()
            return
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

        Also arms the drag state machine: stores ``_press_view_pos`` and
        ``_drag_field_id``; the drag itself starts only once the cursor
        travels :attr:`DRAG_THRESHOLD_PX` (Manhattan, viewport px).

        Args:
            ev: The mouse press event.
        """
        if ev.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(ev.position().toPoint())
            self.select_at(scene_pos)
            self._press_view_pos = ev.position()
            idx = self.cell_index_at(scene_pos)
            self._drag_field_id = (
                self.solved.cell_field_ids[idx]
                if (self.solved is not None and idx >= 0)
                else ""
            )
            self._dragging = False
            ev.accept()
        else:
            super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        """Advance the drag state machine while the left button is held.

        Crosses the Manhattan :attr:`DRAG_THRESHOLD_PX` once, then updates
        the zone hint + ghost overlays on every move (via
        :meth:`show_drop_hint`).

        Args:
            ev: The mouse move event.
        """
        if (self._drag_field_id
                and (ev.buttons() & Qt.MouseButton.LeftButton)
                and self._press_view_pos is not None):
            if (not self._dragging
                    and (ev.position() - self._press_view_pos
                         ).manhattanLength() > self.DRAG_THRESHOLD_PX):
                self._dragging = True
            if self._dragging:
                sp = self.mapToScene(ev.position().toPoint())
                self.show_drop_hint(sp, self._drag_field_id)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        """Complete or abandon the gesture on left-button release.

        A completed drag classifies the final zone and applies the drop
        (:meth:`_apply_drop`); a plain click (threshold never crossed)
        leaves the press-time selection as-is.  A release after
        :meth:`cancel_drag` is a no-op (``_dragging`` already cleared).

        Args:
            ev: The mouse release event.
        """
        if (ev.button() == Qt.MouseButton.LeftButton
                and self._press_view_pos is not None):
            if self._dragging and self._drag_field_id:
                zone = self.zone_at(
                    self.mapToScene(ev.position().toPoint()),
                    self._drag_field_id)
                self._apply_drop(self._drag_field_id, zone)
            self._end_drag()
            self._press_view_pos = None
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    # ── Drop hint (public — also used by PoolList as an external drag source) ─

    def show_drop_hint(self, scene_pos: QPointF, field_id: str) -> None:
        """Show the zone-hint + ghost overlays for a drag over *scene_pos*.

        Public so that :class:`PoolList` (external drag source) can drive the
        overlays without touching canvas privates.

        Zone downgrade: if the raw zone kind is ``"insert"``, ``"pair_left"``,
        or ``"pair_right"`` but :meth:`_drop_would_mutate` returns False (dead
        drop — e.g. same-position reinsert, own-half pair, dangling-partner
        target), the stored hint is downgraded to
        ``DropZone("full", zone.row_index)`` so the overlay reads red (dead)
        instead of blue (live).  Ghost label is kept regardless.

        Note on pool-drag vs canvas-drag: pool drags pass the real field_id
        of an UNPLACED field — an unplaced field's insert is always live, so
        pool hints are never downgraded by the ``_drop_would_mutate`` check.
        Canvas drags pass the dragged placed field's id — correct downgrades.
        The asymmetry is intentional; see also :meth:`apply_pool_drop`'s use
        of ``dragged_field_id=""`` semantics.

        Args:
            scene_pos: Current cursor position in scene (mm) coordinates.
            field_id: The field being dragged (affects zone classification;
                unplaced pool fields classify identically to ``""``).
        """
        zone = self.zone_at(scene_pos, field_id)
        if (zone.kind in ("insert", "pair_left", "pair_right")
                and not self._drop_would_mutate(field_id, zone)):
            zone = DropZone("full", zone.row_index)
        self._zone_hint = zone
        self._ghost_pos = scene_pos
        fmap = self._layout_ref.field_map() if self._layout_ref else {}
        f = fmap.get(field_id)
        self._ghost_label = f.name if f else ""
        self.viewport().update()

    def clear_drop_hint(self) -> None:
        """Clear the zone-hint + ghost overlays (public counterpart)."""
        self._zone_hint = None
        self._ghost_pos = None
        self._ghost_label = ""
        self.viewport().update()

    # ── Drop application ──────────────────────────────────────────────────────

    def apply_pool_drop(self, field_id: str, scene_pos: QPointF) -> None:
        """Apply a drop of an UNPLACED (pool) field at *scene_pos*.

        Public entry point for :class:`PoolList`.  Zone classification uses
        ``dragged_field_id=""`` semantics (pool fields are never rendered, so
        outsider classification is correct).  ``outside`` drops are dead for
        pool fields (unplacing an unplaced field would not mutate).

        Args:
            field_id: The pool field being dropped.
            scene_pos: Drop position in scene (mm) coordinates.
        """
        zone = self.zone_at(scene_pos)
        self._apply_drop(field_id, zone)

    def _insert_index_after_removal(self, lay: TemplateLayout,
                                    field_id: str, raw_index: int) -> int:
        """Translate a pre-removal insert index to the ops' post-removal index.

        ``zone_at`` returns insertion indices against the CURRENT
        ``layout.rows``; ``place_field``/``move_field`` interpret the index
        AFTER the dragged field's own single-slot row has been removed.  When
        that row sits above the insertion point the index shifts down by one.
        A pair member's removal does not remove a row → no adjustment.

        Args:
            lay: The layout whose rows are being examined (trial or live).
            field_id: The dragged field.
            raw_index: Insertion index into the current ``layout.rows``.

        Returns:
            The equivalent insertion index after removal.
        """
        for ri, row in enumerate(lay.rows):
            if len(row) == 1 and row[0].field_id == field_id:
                if ri < raw_index:
                    return raw_index - 1
                break
        return raw_index

    def _dispatch(self, lay: TemplateLayout, field_id: str,
                  zone: DropZone) -> None:
        """Apply the zone's op to *lay* (the insert/pair/outside three-way).

        Shared dispatch used by both :meth:`_apply_drop` (live layout) and
        :meth:`_drop_would_mutate` (trial layout).  ``full`` zones are
        rejected before reaching this method.

        Drop prediction: :meth:`_drop_would_mutate` dry-runs these ops on a
        trial layout — new guards added to the underlying ops
        (:func:`~firepro3d.titleblock_template.pair_field`,
        :func:`~firepro3d.titleblock_template.move_field`,
        :func:`~firepro3d.titleblock_template.unplace_field`) are picked up
        automatically.

        Args:
            lay: Layout to mutate (live or trial).
            field_id: The dragged field.
            zone: The classified drop zone.
        """
        if zone.kind == "insert":
            move_field(lay, field_id,
                       self._insert_index_after_removal(lay, field_id,
                                                        zone.row_index))
        elif zone.kind in ("pair_left", "pair_right"):
            pair_field(lay, field_id, zone.row_index,
                       "left" if zone.kind == "pair_left" else "right")
        elif zone.kind == "outside":
            unplace_field(lay, field_id)

    def _drop_would_mutate(self, field_id: str, zone: DropZone) -> bool:
        """Predict whether applying *zone* for *field_id* mutates the layout.

        Uses a dry-run on a shallow-copied trial layout so that every guard
        inside the pure ops (``pair_field``, ``move_field``, ``unplace_field``)
        is automatically honoured — no analytic mirror required.  ``fields``
        is shared (ops never mutate it); ``rows`` is per-slot-copied so
        mutations to the trial stay isolated from the live layout.

        Dead-drop detection (returns False):
        * zone ``full`` or unknown.
        * unknown field_id.
        * Any op that leaves ``trial.rows`` structurally identical to the real
          layout rows (field_id order only; min_height/sizing cannot change
          from a drop).

        For ``outside`` zones the op is skipped; the check is simpler: a field
        not currently placed cannot be unplaced.

        Args:
            field_id: The dragged field.
            zone: The classified drop zone.

        Returns:
            True if the drop would change ``layout.rows``.
        """
        lay = self._layout_ref
        if lay is None or field_id not in lay.field_map():
            return False
        if zone.kind == "full":
            return False
        if zone.kind == "outside":
            return field_id in lay.placed_ids()
        # Build a shallow-copy trial: share fields list (never mutated by ops),
        # deep-copy rows at the Slot level so mutations stay isolated.
        trial = TemplateLayout(
            fields=lay.fields,
            rows=[[Slot(s.field_id, s.min_height_mm, s.sizing) for s in row]
                  for row in lay.rows],
        )
        self._dispatch(trial, field_id, zone)
        real_ids = [[s.field_id for s in row] for row in lay.rows]
        trial_ids = [[s.field_id for s in row] for row in trial.rows]
        return trial_ids != real_ids

    def _apply_drop(self, field_id: str, zone: DropZone) -> None:
        """Apply a completed drop: mutate the layout, refresh, signal.

        Emits :attr:`gestureStarting` BEFORE the mutation and
        :attr:`gestureCompleted` after ``refresh()`` — exactly once each, and
        ONLY when the drop actually mutates the layout
        (:meth:`_drop_would_mutate`); dead drops (zone ``full``, own-half
        pairs, same-position reinserts, unplacing an unplaced field) emit
        nothing so no empty undo snapshot is pushed.

        ``refresh()`` (scene.clear()) is safe here: this runs from the VIEW's
        mouse handler with no scene mouse grabber — the press was accepted at
        the view level and never forwarded to the scene items.

        Args:
            field_id: The dragged field.
            zone: The classified drop zone (from :meth:`zone_at`).
        """
        lay = self._layout_ref
        if lay is None or zone.kind == "full":
            return
        if not self._drop_would_mutate(field_id, zone):
            return
        self.gestureStarting.emit()      # snapshot BEFORE mutation
        self._dispatch(lay, field_id, zone)
        self.refresh()
        self.gestureCompleted.emit()

    # ── Drag lifecycle ────────────────────────────────────────────────────────

    def cancel_drag(self) -> None:
        """Cancel the in-flight drag: no mutation, NO gesture signals (DD-16).

        Clears the drag state so the trailing mouse release is a no-op.
        """
        self._end_drag()

    def _end_drag(self) -> None:
        """Reset the drag state machine and clear all drag overlays."""
        self._drag_field_id = ""
        self._dragging = False
        self.clear_drop_hint()

    def focusOutEvent(self, ev: QFocusEvent) -> None:
        """Cancel an in-flight drag when the canvas loses keyboard focus.

        If a drag is in progress when focus leaves (e.g. the user
        Alt-tabs away mid-gesture), the drag is cancelled silently — no
        mutation and no gesture signals — so the layout is never left in a
        partially applied state.

        Args:
            ev: The focus-out event.
        """
        if self._dragging:
            self.cancel_drag()
        super().focusOutEvent(ev)


class PoolList(QListWidget):
    """Unplaced-field cards; manual drag source into the bound canvas.

    Rows show a kind glyph + field name + first text line; the field id is
    stored under ``Qt.ItemDataRole.UserRole``.  Dragging uses the same manual
    mouse tracking as :class:`StripCanvas` (no native Qt DnD — DD-16): Qt
    keeps delivering move/release events to the pressed widget, so the pool
    maps its local positions through global coordinates onto the canvas
    viewport and drives the canvas's public drop-hint / drop API.

    Pool refresh stays OUTSIDE this class: the owning tab re-calls
    :meth:`set_fields` with ``layout.pool_fields()`` after each gesture.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas: StripCanvas | None = None
        self._drag_field_id: str = ""

    def bind_canvas(self, canvas: StripCanvas) -> None:
        """Bind the target canvas that receives drops from this pool.

        Args:
            canvas: The :class:`StripCanvas` to drop onto.
        """
        self._canvas = canvas

    def set_fields(self, fields) -> None:
        """Rebuild the card list from *fields* (the unplaced pool).

        Each row renders ``"<glyph> <name>\n   <first text line>"`` where the
        glyph is ▤ for a revision table, 🖼 for an image field, 🅣 for a
        text/empty field.

        Args:
            fields: Iterable of ``FieldDef`` (typically
                ``layout.pool_fields()``).
        """
        self.clear()
        for f in fields:
            first = (f.text.splitlines() or [""])[0]
            if f.kind == "revision_table":
                glyph = "▤"
            elif f.image_data:
                glyph = "🖼"
            else:
                glyph = "🅣"
            item = QListWidgetItem(f"{glyph} {f.name}\n   {first}")
            item.setData(Qt.ItemDataRole.UserRole, f.id)
            self.addItem(item)

    # ── Manual drag source ────────────────────────────────────────────────────

    def _canvas_scene_pos(self, ev: QMouseEvent) -> QPointF | None:
        """Map the event position onto the canvas scene, or None if outside.

        Args:
            ev: A mouse event delivered to this widget's viewport.

        Returns:
            The scene (mm) position on the bound canvas, or ``None`` when no
            canvas is bound or the cursor is outside the canvas viewport.
        """
        if self._canvas is None:
            return None
        gp = self.viewport().mapToGlobal(ev.position().toPoint())
        vp_pos = self._canvas.viewport().mapFromGlobal(gp)
        if not self._canvas.viewport().rect().contains(vp_pos):
            return None
        return self._canvas.mapToScene(vp_pos)

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        """Stash the pressed card's field id as the drag payload.

        Args:
            ev: The mouse press event.
        """
        super().mousePressEvent(ev)
        item = self.itemAt(ev.position().toPoint())
        self._drag_field_id = (item.data(Qt.ItemDataRole.UserRole)
                               if item is not None else "")

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        """Drive the canvas drop-hint overlays while dragging over it.

        Args:
            ev: The mouse move event (delivered here — the pool holds the
                implicit mouse grab).
        """
        if (self._drag_field_id
                and (ev.buttons() & Qt.MouseButton.LeftButton)
                and self._canvas is not None):
            sp = self._canvas_scene_pos(ev)
            if sp is not None:
                self._canvas.show_drop_hint(sp, self._drag_field_id)
            else:
                self._canvas.clear_drop_hint()
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        """Drop the dragged field onto the canvas, if released over it.

        Delegates to :meth:`StripCanvas.apply_pool_drop` (gesture signals are
        emitted by the canvas, only for mutating drops).  Releasing outside
        the canvas does nothing.  Always clears the hint overlays + stash.

        Args:
            ev: The mouse release event.
        """
        if self._drag_field_id and self._canvas is not None:
            sp = self._canvas_scene_pos(ev)
            if sp is not None:
                self._canvas.apply_pool_drop(self._drag_field_id, sp)
            self._canvas.clear_drop_hint()
        self._drag_field_id = ""
        super().mouseReleaseEvent(ev)

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        """Esc mid-pool-drag cancels: clear stash + canvas hint, no signals.

        Args:
            ev: The key press event.
        """
        if ev.key() == Qt.Key.Key_Escape and self._drag_field_id:
            self._drag_field_id = ""
            if self._canvas is not None:
                self._canvas.clear_drop_hint()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def focusOutEvent(self, ev: QFocusEvent) -> None:
        """Cancel an in-flight pool drag when the pool loses keyboard focus.

        Clears the drag stash and any canvas hint overlays so the layout is
        never left with a stale drop indicator.

        Args:
            ev: The focus-out event.
        """
        if self._drag_field_id:
            self._drag_field_id = ""
            if self._canvas is not None:
                self._canvas.clear_drop_hint()
        super().focusOutEvent(ev)


class ArrangementsTab(QWidget):
    """Three-column Arrangements tab (spec DD-17): pool | canvas | props.

    Deliberately dumb: it owns no dialog/undo knowledge.  Signals flow OUT
    through the child widgets (:class:`StripCanvas` gesture/selection signals,
    ``min_height.valueChanged``, ``sizing.currentTextChanged``) and data flows
    IN through :meth:`refresh`.

    Columns:

    1. "Unplaced fields:" label + :class:`PoolList` (fixed
       ``TB_POOL_CARD_W`` width).
    2. Warning banner (hidden when empty) above the :class:`StripCanvas`
       (pool-bound) + a "Fit" button → :meth:`StripCanvas.fit_strip`.
    3. "Placement" group (min-height ``DimensionEdit`` + Static/Dynamic
       sizing combo; disabled until the dialog enables it on selection)
       above the relocated strip-border group (DD-16: placement props
       editable without tab-bouncing).
    """

    def __init__(self, strip_border_group: QWidget,
                 parent: QWidget | None = None):
        """Build the three columns.

        Args:
            strip_border_group: The dialog's "Info Strip Border" group widget;
                re-parented here by insertion into column 3's layout (DD-17:
                strip border lives on the Arrangements tab).
            parent: Optional parent widget.
        """
        super().__init__(parent)
        cols = QHBoxLayout(self)
        cols.setSpacing(6)

        # ── Column 1: unplaced-field pool ─────────────────────────────────
        left = QVBoxLayout()
        left.addWidget(QLabel("Unplaced fields:"))
        self.pool = PoolList()
        self.pool.setFixedWidth(TB_POOL_CARD_W)
        left.addWidget(self.pool, stretch=1)
        cols.addLayout(left)

        # ── Column 2: warning banner + strip canvas + Fit ─────────────────
        centre = QVBoxLayout()
        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet("color: #b8620a; font-size: 11px;")
        self.banner.setVisible(False)
        centre.addWidget(self.banner)
        self.canvas = StripCanvas()
        self.pool.bind_canvas(self.canvas)
        centre.addWidget(self.canvas, stretch=1)
        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self.canvas.fit_strip)
        centre.addWidget(fit_btn)
        cols.addLayout(centre, stretch=1)

        # ── Column 3: placement props + relocated strip border ────────────
        right = QVBoxLayout()
        self.props_group = QGroupBox("Placement")
        pf = QFormLayout(self.props_group)
        pf.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.min_height = DimensionEdit(None, initial_mm=10.0,
                                        parser=_sm.parse_dimension,
                                        minimum=0.0)
        pf.addRow("Min height (mm):", self.min_height)
        self.sizing = QComboBox()
        self.sizing.addItems(["Static", "Dynamic"])
        pf.addRow("Sizing:", self.sizing)
        self.props_group.setEnabled(False)   # until a placed cell is selected
        right.addWidget(self.props_group)
        right.addWidget(strip_border_group)  # re-parented here (DD-17)
        right.addStretch()
        cols.addLayout(right)

    def refresh(self, layout: TemplateLayout) -> None:
        """Re-sync pool + canvas + warning banner from *layout*.

        The canvas re-solves through its provider (which must already point
        at the same working layout); the banner mirrors the solver warnings.

        Args:
            layout: The working :class:`TemplateLayout` (or an empty one to
                clear the tab gracefully).
        """
        self.pool.set_fields(layout.pool_fields())
        self.canvas.refresh()
        warns = list(self.canvas.solved.warnings) if self.canvas.solved else []
        self.banner.setText("\n".join(warns))
        self.banner.setVisible(bool(warns))
