"""StripCanvas: render, hit-testing, zone detection, selection, gestures."""
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QFocusEvent, QHelpEvent, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QToolTip

from firepro3d.constants import TB_INSERT_BAND_PX
from firepro3d.titleblock_template import (
    FieldDef, Slot, TemplateLayout, make_default_template,
)
from firepro3d.titleblock_arrange import StripCanvas, DropZone

_app = QApplication.instance() or QApplication([])

PAPER_W, PAPER_H = 863.6, 558.8


def _canvas(layout=None):
    lay = layout or make_default_template().layout
    canvas = StripCanvas()
    canvas.set_provider(lambda: (lay, PAPER_W, PAPER_H, {}))
    canvas.refresh()
    canvas.resize(400, 600)
    canvas.show()
    return canvas, lay


class TestCanvasBasics:
    def test_renders_one_item(self):
        canvas, _ = _canvas()
        assert len(canvas.scene().items()) >= 1

    def test_refresh_resolves_and_sets_scene_rect(self):
        canvas, lay = _canvas()
        assert canvas.solved is not None
        assert canvas.scene().sceneRect().contains(canvas.solved.strip_rect)

    def test_fit_shows_whole_strip(self):
        canvas, _ = _canvas()
        canvas.fit_strip()
        vis = canvas.mapToScene(canvas.viewport().rect()).boundingRect()
        assert vis.contains(canvas.solved.strip_rect)

    def test_click_selects_cell(self):
        canvas, lay = _canvas()
        centre = canvas.solved.cell_rects[1].center()
        canvas.select_at(centre)
        assert canvas.selected_field_id == canvas.solved.cell_field_ids[1]

    def test_click_empty_clears_selection(self):
        canvas, _ = _canvas()
        canvas.select_at(canvas.solved.cell_rects[1].center())
        far = QPointF(canvas.solved.strip_rect.left() - 100,
                      canvas.solved.strip_rect.top())
        canvas.select_at(far)
        assert canvas.selected_field_id == ""

    def test_selection_signal_emitted(self):
        canvas, _ = _canvas()
        got = []
        canvas.selectionChanged.connect(got.append)
        canvas.select_at(canvas.solved.cell_rects[1].center())
        assert got == [canvas.solved.cell_field_ids[1]]


class TestZoneDetection:
    def test_row_boundary_is_insert(self):
        canvas, _ = _canvas()
        r0 = canvas.solved.cell_rects[0]
        z = canvas.zone_at(QPointF(r0.center().x(), r0.bottom()))
        assert z.kind == "insert" and z.row_index == 1

    def test_top_of_strip_inserts_at_zero(self):
        canvas, _ = _canvas()
        strip = canvas.solved.strip_rect
        z = canvas.zone_at(QPointF(strip.center().x(), strip.top()))
        assert z.kind == "insert" and z.row_index == 0

    def test_single_row_halves_pair(self):
        canvas, lay = _canvas()
        # Find first single-slot solved row structurally (not by hardcoded index)
        ri_solved = next(
            i for i, (first, n) in enumerate(canvas.solved.row_spans)
            if n == 1
        )
        r = canvas.solved.cell_rects[canvas.solved.row_spans[ri_solved][0]]
        mid_y = r.center().y()
        left = canvas.zone_at(QPointF(r.left() + r.width() * 0.25, mid_y))
        right = canvas.zone_at(QPointF(r.left() + r.width() * 0.75, mid_y))
        assert (left.kind, right.kind) == ("pair_left", "pair_right")
        assert left.row_index == right.row_index == ri_solved

    def test_paired_row_middle_is_full_for_outsider(self):
        canvas, lay = _canvas()
        ri = next(i for i, row in enumerate(lay.rows) if len(row) == 2)
        member_ids = {s.field_id for s in lay.rows[ri]}
        # Pick a field that is in a different (single-slot) row — a real outsider.
        outsider_id = next(
            s.field_id
            for row in lay.rows
            if len(row) == 1
            for s in row
            if s.field_id not in member_ids
        )
        first, _n = canvas.solved.row_spans[ri]
        r = canvas.solved.cell_rects[first]
        z = canvas.zone_at(QPointF(r.right(), r.center().y()),
                           dragged_field_id=outsider_id)
        assert z.kind == "full"

    def test_paired_row_halves_for_member_swap(self):
        canvas, lay = _canvas()
        ri = next(i for i, row in enumerate(lay.rows) if len(row) == 2)
        member = lay.rows[ri][0].field_id
        first, _n = canvas.solved.row_spans[ri]
        r = canvas.solved.cell_rects[first]      # left cell of the pair
        # Query the LEFT cell's centre — must land in pair_left exactly.
        z = canvas.zone_at(QPointF(r.center().x(), r.center().y()),
                           dragged_field_id=member)
        assert z.kind == "pair_left"
        assert z.row_index == ri

    def test_own_single_row_interior_is_full(self):
        canvas, lay = _canvas()
        # Find first single-slot solved row structurally (not by hardcoded index)
        ri_solved = next(
            i for i, (first, n) in enumerate(canvas.solved.row_spans)
            if n == 1
        )
        first_idx = canvas.solved.row_spans[ri_solved][0]
        fid = canvas.solved.cell_field_ids[first_idx]
        r = canvas.solved.cell_rects[first_idx]
        z = canvas.zone_at(QPointF(r.center().x(), r.center().y()),
                           dragged_field_id=fid)
        assert z.kind == "full"

    def test_outside_strip(self):
        canvas, _ = _canvas()
        strip = canvas.solved.strip_rect
        z = canvas.zone_at(QPointF(strip.left() - 50, strip.center().y()))
        assert z.kind == "outside"

    def test_below_last_row_appends(self):
        fs = [FieldDef(id="a", name="a")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 20.0)]])
        canvas, _ = _canvas(lay)
        strip = canvas.solved.strip_rect
        # far below the single 20mm row, inside the strip, away from any band
        z = canvas.zone_at(QPointF(strip.center().x(),
                                   strip.top() + 200.0))
        assert z.kind == "insert" and z.row_index == 1

    def test_above_strip_gap_inserts_at_top(self):
        canvas, _ = _canvas()
        strip = canvas.solved.strip_rect
        band = canvas._px_to_mm(TB_INSERT_BAND_PX)
        # just above the top edge, inside the inflated outside-margin,
        # but beyond boundary 0's capped band
        z = canvas.zone_at(QPointF(strip.center().x(),
                                   strip.top() - band * 1.5))
        assert z.kind == "insert" and z.row_index == 0


class TestZoneDanglingRows:
    """Issue 1: zone_at row_index must be a layout.rows index, not a solved-row index."""

    def test_zone_row_index_is_layout_index_with_dangling_row(self):
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs,
                             rows=[[Slot("ghost")],      # fully dangling → not rendered
                                   [Slot("a", 20.0)], [Slot("b", 20.0)]])
        canvas, _ = _canvas(lay)
        # first RENDERED row is "a" (solved row 0, layout row 1)
        r = canvas.solved.cell_rects[0]
        z = canvas.zone_at(QPointF(r.left() + r.width() * 0.25, r.center().y()))
        assert z.kind == "pair_left" and z.row_index == 1   # layout index!

    def test_half_dangling_pair_classifies_from_rendered(self):
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs,
                             rows=[[Slot("a", 20.0), Slot("ghost")], [Slot("b", 20.0)]])
        canvas, _ = _canvas(lay)
        r = canvas.solved.cell_rects[0]     # renders as ONE cell
        z = canvas.zone_at(QPointF(r.left() + r.width() * 0.75, r.center().y()))
        # row visibly has ONE rendered cell — there is room for a pair partner.
        # The zone should reflect what's rendered (pair_right), not full.
        # NOTE on Task 9 integrity: pair_field on a layout row that still holds
        # 2 slots (one dangling) will no-op via the len>=2 guard in pair_field;
        # that is acceptable (op-level guard prevents data corruption) — but the
        # ZONE should still reflect what the user sees: one rendered cell, room
        # for a partner on the right.
        assert z.kind == "pair_right"       # room visibly available, not "full"


class TestRefreshClearsStaleSelection:
    """Issue 2: refresh() must clear selected_field_id when its field is gone."""

    def test_refresh_clears_stale_selection(self):
        canvas, lay = _canvas()
        canvas.select_at(canvas.solved.cell_rects[1].center())
        fid = canvas.selected_field_id
        got = []
        canvas.selectionChanged.connect(got.append)
        from firepro3d.titleblock_template import unplace_field
        unplace_field(lay, fid)
        canvas.refresh()
        assert canvas.selected_field_id == ""
        assert got == [""]


class TestDeleteKeyUnplace:
    def test_delete_emits_unplace_for_selection(self):
        canvas, _ = _canvas()
        canvas.select_at(canvas.solved.cell_rects[1].center())
        fid = canvas.selected_field_id
        got = []
        canvas.unplaceRequested.connect(got.append)
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent
        # ShortcutOverride path first (project memory: views must accept it)
        ov = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Delete,
                       Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(canvas, ov)
        assert ov.isAccepted()
        press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete,
                          Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(canvas, press)
        assert got == [fid]

    def test_delete_no_selection_no_signal(self):
        canvas, _ = _canvas()
        got = []
        canvas.unplaceRequested.connect(got.append)
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent
        press = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete,
                          Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(canvas, press)
        assert got == []


class TestMousePressSelection:
    def test_viewport_click_selects(self):
        canvas, _ = _canvas()
        canvas.fit_strip()
        target = canvas.solved.cell_rects[1].center()
        vp_pos = QPointF(canvas.mapFromScene(target))
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, vp_pos,
                         canvas.viewport().mapToGlobal(vp_pos.toPoint()).toPointF(),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(canvas.viewport(), ev)
        assert canvas.selected_field_id == canvas.solved.cell_field_ids[1]


# ─────────────────────────────────────────────────────────────────────────────
# Task 9: drag gestures + pool drag source
# ─────────────────────────────────────────────────────────────────────────────

def _mouse(widget, etype, view_pos, button=Qt.MouseButton.LeftButton,
           buttons=Qt.MouseButton.LeftButton):
    ev = QMouseEvent(etype, view_pos,
                     widget.mapToGlobal(view_pos.toPoint()).toPointF(),
                     button, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


def _drag_on_canvas(canvas, scene_from, scene_to):
    vp = canvas.viewport()
    p1 = QPointF(canvas.mapFromScene(scene_from))
    p2 = QPointF(canvas.mapFromScene(scene_to))
    _mouse(vp, QEvent.Type.MouseButtonPress, p1)
    _mouse(vp, QEvent.Type.MouseMove, (p1 + p2) / 2)
    _mouse(vp, QEvent.Type.MouseMove, p2)
    _mouse(vp, QEvent.Type.MouseButtonRelease, p2,
           buttons=Qt.MouseButton.NoButton)


def _rows(lay):
    return [[s.field_id for s in r] for r in lay.rows]


def _spy_gestures(canvas):
    starts, completes = [], []
    canvas.gestureStarting.connect(lambda: starts.append(1))
    canvas.gestureCompleted.connect(lambda: completes.append(1))
    return starts, completes


def _cell_center(canvas, fid):
    i = canvas.solved.cell_field_ids.index(fid)
    return canvas.solved.cell_rects[i].center()


class TestCanvasGestures:
    def _simple(self):
        fs = [FieldDef(id=i, name=i, text=i) for i in ("a", "b", "c", "d")]
        lay = TemplateLayout(fields=fs,
                             rows=[[Slot("a", 40.0)], [Slot("b", 40.0)],
                                   [Slot("c", 40.0)]])
        return _canvas(lay)

    def _paired(self):
        fs = [FieldDef(id=i, name=i, text=i) for i in ("a", "b", "c")]
        lay = TemplateLayout(fields=fs,
                             rows=[[Slot("a", 40.0)],
                                   [Slot("b", 40.0), Slot("c", 40.0)]])
        return _canvas(lay)

    def test_reorder_drag(self):
        canvas, lay = self._simple()
        starts, completes = _spy_gestures(canvas)
        src = _cell_center(canvas, "a")
        c_idx = canvas.solved.cell_field_ids.index("c")
        dst = QPointF(src.x(), canvas.solved.cell_rects[c_idx].bottom())
        _drag_on_canvas(canvas, src, dst)
        assert _rows(lay) == [["b"], ["c"], ["a"]]
        assert starts == [1] and completes == [1]

    def test_pair_drag(self):
        canvas, lay = self._simple()
        starts, completes = _spy_gestures(canvas)
        src = _cell_center(canvas, "a")
        b_idx = canvas.solved.cell_field_ids.index("b")
        r1 = canvas.solved.cell_rects[b_idx]
        dst = QPointF(r1.left() + r1.width() * 0.75, r1.center().y())
        _drag_on_canvas(canvas, src, dst)
        assert _rows(lay) == [["b", "a"], ["c"]]
        assert starts == [1] and completes == [1]

    def test_unpair_by_drag_to_insert(self):
        canvas, lay = self._paired()
        starts, completes = _spy_gestures(canvas)
        src = _cell_center(canvas, "c")
        strip = canvas.solved.strip_rect
        dst = QPointF(strip.center().x(), strip.top())
        _drag_on_canvas(canvas, src, dst)
        assert _rows(lay) == [["c"], ["a"], ["b"]]
        assert starts == [1] and completes == [1]

    def test_unplace_drag_off_strip(self):
        canvas, lay = self._simple()
        starts, completes = _spy_gestures(canvas)
        src = _cell_center(canvas, "a")
        dst = QPointF(canvas.solved.strip_rect.left() - 80, src.y())
        _drag_on_canvas(canvas, src, dst)
        assert "a" not in {s.field_id for r in lay.rows for s in r}
        assert "a" in {f.id for f in lay.fields}            # still defined
        assert starts == [1] and completes == [1]

    def test_swap_sides_drag(self):
        canvas, lay = self._paired()
        starts, completes = _spy_gestures(canvas)
        src = _cell_center(canvas, "b")
        dst = _cell_center(canvas, "c")     # right half of the shared row
        _drag_on_canvas(canvas, src, dst)
        assert _rows(lay) == [["a"], ["c", "b"]]
        assert starts == [1] and completes == [1]

    def test_dead_drop_own_row_interior_no_signals(self):
        canvas, lay = self._simple()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        src = _cell_center(canvas, "a")
        dst = QPointF(src.x(), src.y() + 6)   # own row interior, off bands
        _drag_on_canvas(canvas, src, dst)
        assert _rows(lay) == before
        assert starts == [] and completes == []

    def test_dead_drop_own_half_no_signals(self):
        canvas, lay = self._paired()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        src = _cell_center(canvas, "b")       # left member of the pair
        dst = QPointF(src.x() + 6, src.y())   # still the left half
        _drag_on_canvas(canvas, src, dst)
        assert _rows(lay) == before
        assert starts == [] and completes == []

    def test_dead_drop_reinsert_same_position_no_signals(self):
        canvas, lay = self._simple()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        a_idx = canvas.solved.cell_field_ids.index("a")
        r0 = canvas.solved.cell_rects[a_idx]
        src = r0.center()
        dst = QPointF(src.x(), r0.bottom())   # insert between a and b → no-op
        _drag_on_canvas(canvas, src, dst)
        assert _rows(lay) == before
        assert starts == [] and completes == []

    def test_escape_cancels_drag(self):
        canvas, lay = self._simple()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        vp = canvas.viewport()
        src = QPointF(canvas.mapFromScene(_cell_center(canvas, "a")))
        _mouse(vp, QEvent.Type.MouseButtonPress, src)
        _mouse(vp, QEvent.Type.MouseMove, src + QPointF(0, 40))
        QApplication.sendEvent(canvas, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier))
        _mouse(vp, QEvent.Type.MouseButtonRelease, src + QPointF(0, 40),
               buttons=Qt.MouseButton.NoButton)
        assert _rows(lay) == before
        assert starts == [] and completes == []
        assert canvas._zone_hint is None      # overlays cleared

    def test_click_without_drag_only_selects(self):
        canvas, lay = self._simple()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        vp = canvas.viewport()
        p = QPointF(canvas.mapFromScene(_cell_center(canvas, "b")))
        _mouse(vp, QEvent.Type.MouseButtonPress, p)
        _mouse(vp, QEvent.Type.MouseButtonRelease, p,
               buttons=Qt.MouseButton.NoButton)
        assert canvas.selected_field_id == "b"
        assert _rows(lay) == before
        assert starts == [] and completes == []

    def test_threshold_not_crossed_no_drag(self):
        canvas, lay = self._simple()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        vp = canvas.viewport()
        p = QPointF(canvas.mapFromScene(_cell_center(canvas, "a")))
        _mouse(vp, QEvent.Type.MouseButtonPress, p)
        _mouse(vp, QEvent.Type.MouseMove, p + QPointF(0, 2))  # < threshold
        _mouse(vp, QEvent.Type.MouseButtonRelease, p + QPointF(0, 2),
               buttons=Qt.MouseButton.NoButton)
        assert _rows(lay) == before
        assert starts == [] and completes == []


class TestPoolDrag:
    def _setup(self):
        from firepro3d.titleblock_arrange import PoolList
        fs = [FieldDef(id=i, name=i, text=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 40.0)]])
        canvas, _ = _canvas(lay)
        pool = PoolList()
        pool.bind_canvas(canvas)
        pool.set_fields(lay.pool_fields())
        pool.resize(200, 300)
        pool.show()
        return canvas, pool, lay

    def _pool_local_for_canvas_scene(self, canvas, pool, scene_pos):
        """Map a canvas scene point to POOL-viewport-local coords via global."""
        target_global = canvas.viewport().mapToGlobal(
            canvas.mapFromScene(scene_pos))
        return QPointF(pool.viewport().mapFromGlobal(target_global))

    def test_pool_to_canvas_place(self):
        canvas, pool, lay = self._setup()
        starts, completes = _spy_gestures(canvas)
        item_rect = pool.visualItemRect(pool.item(0))
        _mouse(pool.viewport(), QEvent.Type.MouseButtonPress,
               QPointF(item_rect.center()))
        a_idx = canvas.solved.cell_field_ids.index("a")
        target_scene = QPointF(canvas.solved.strip_rect.center().x(),
                               canvas.solved.cell_rects[a_idx].bottom())
        local = self._pool_local_for_canvas_scene(canvas, pool, target_scene)
        _mouse(pool.viewport(), QEvent.Type.MouseMove, local)
        _mouse(pool.viewport(), QEvent.Type.MouseButtonRelease, local,
               buttons=Qt.MouseButton.NoButton)
        assert _rows(lay) == [["a"], ["b"]]
        assert starts == [1] and completes == [1]

    def test_pool_release_outside_canvas_no_op(self):
        canvas, pool, lay = self._setup()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        item_rect = pool.visualItemRect(pool.item(0))
        _mouse(pool.viewport(), QEvent.Type.MouseButtonPress,
               QPointF(item_rect.center()))
        # A point guaranteed outside the canvas viewport rect.
        outside_global = canvas.viewport().mapToGlobal(
            QPointF(-300, -300).toPoint())
        local = QPointF(pool.viewport().mapFromGlobal(outside_global))
        _mouse(pool.viewport(), QEvent.Type.MouseMove, local)
        _mouse(pool.viewport(), QEvent.Type.MouseButtonRelease, local,
               buttons=Qt.MouseButton.NoButton)
        assert _rows(lay) == before
        assert starts == [] and completes == []

    def test_pool_escape_cancels(self):
        canvas, pool, lay = self._setup()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        item_rect = pool.visualItemRect(pool.item(0))
        _mouse(pool.viewport(), QEvent.Type.MouseButtonPress,
               QPointF(item_rect.center()))
        a_idx = canvas.solved.cell_field_ids.index("a")
        target_scene = QPointF(canvas.solved.strip_rect.center().x(),
                               canvas.solved.cell_rects[a_idx].bottom())
        local = self._pool_local_for_canvas_scene(canvas, pool, target_scene)
        _mouse(pool.viewport(), QEvent.Type.MouseMove, local)
        assert canvas._zone_hint is not None  # hint shown while over canvas
        QApplication.sendEvent(pool, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier))
        assert canvas._zone_hint is None
        _mouse(pool.viewport(), QEvent.Type.MouseButtonRelease, local,
               buttons=Qt.MouseButton.NoButton)
        assert _rows(lay) == before
        assert starts == [] and completes == []

    def test_pool_glyphs(self):
        from firepro3d.titleblock_arrange import PoolList
        fs = [FieldDef(id="r", name="Rev", kind="revision_table"),
              FieldDef(id="i", name="Logo", image_data="abc"),
              FieldDef(id="t", name="Note", text="hello\nworld")]
        pool = PoolList()
        pool.set_fields(fs)
        assert pool.item(0).text().startswith("▤")
        assert pool.item(1).text().startswith("🖼")
        assert pool.item(2).text().startswith("🅣")
        assert "hello" in pool.item(2).text()
        assert "world" not in pool.item(2).text()   # first line only
        assert pool.item(0).data(Qt.ItemDataRole.UserRole) == "r"


# ─────────────────────────────────────────────────────────────────────────────
# Item 2: Hint downgrade — dead drops must advertise "full" (red), not live
# ─────────────────────────────────────────────────────────────────────────────

class TestHintDowngrade:
    """show_drop_hint must downgrade insert/pair zones that would be dead drops."""

    def test_hint_downgrades_dead_drop_to_full(self):
        """Hovering a's own upper boundary (same-position reinsert) → 'full'."""
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 40.0)], [Slot("b", 40.0)]])
        canvas, _ = _canvas(lay)
        r0 = canvas.solved.cell_rects[0]
        # hovering a's own upper boundary (insert at 0 → same-position reinsert = dead)
        canvas.show_drop_hint(
            QPointF(r0.center().x(), canvas.solved.strip_rect.top()), "a")
        assert canvas._zone_hint.kind == "full"

    def test_hint_live_insert_stays_insert(self):
        """Hovering b's lower boundary with field 'a' → live insert, stays 'insert'."""
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 40.0)], [Slot("b", 40.0)]])
        canvas, _ = _canvas(lay)
        b_idx = canvas.solved.cell_field_ids.index("b")
        r1 = canvas.solved.cell_rects[b_idx]
        # drop 'a' after 'b' — that is a live reorder
        canvas.show_drop_hint(QPointF(r1.center().x(), r1.bottom()), "a")
        assert canvas._zone_hint.kind == "insert"

    def test_hint_own_half_pair_downgrades_to_full(self):
        """Dragging 'b' (left of a pair) back onto its own left half → 'full'."""
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(
            fields=fs, rows=[[Slot("b", 40.0), Slot("a", 40.0)]])
        canvas, _ = _canvas(lay)
        b_idx = canvas.solved.cell_field_ids.index("b")
        r = canvas.solved.cell_rects[b_idx]
        # b is the left cell; hover its own left-half centre
        canvas.show_drop_hint(QPointF(r.center().x(), r.center().y()), "b")
        assert canvas._zone_hint.kind == "full"

    def test_hint_pool_unplaced_insert_stays_live(self):
        """An unplaced pool field's insert hint must NOT be downgraded."""
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 40.0)]])
        # "b" is unplaced (pool)
        canvas, _ = _canvas(lay)
        r0 = canvas.solved.cell_rects[0]
        # Drop "b" (unplaced) at top-of-strip insert band → always live
        canvas.show_drop_hint(
            QPointF(r0.center().x(), canvas.solved.strip_rect.top()), "b")
        assert canvas._zone_hint.kind == "insert"

    def test_hint_ghost_label_kept_on_downgrade(self):
        """Ghost label must still be set even when the hint is downgraded."""
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 40.0)], [Slot("b", 40.0)]])
        canvas, _ = _canvas(lay)
        r0 = canvas.solved.cell_rects[0]
        canvas.show_drop_hint(
            QPointF(r0.center().x(), canvas.solved.strip_rect.top()), "a")
        assert canvas._zone_hint.kind == "full"
        assert canvas._ghost_label == "a"   # name of FieldDef(id="a", name="a")


# ─────────────────────────────────────────────────────────────────────────────
# Item 3: Grab-loss cleanup — focusOutEvent cancels in-flight drags
# ─────────────────────────────────────────────────────────────────────────────

class TestGrabLoss:
    """focusOutEvent on StripCanvas/PoolList must cancel in-flight drag."""

    def _armed_canvas(self):
        """Return a canvas with a drag armed past the threshold."""
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 40.0)], [Slot("b", 40.0)]])
        canvas, _ = _canvas(lay)
        vp = canvas.viewport()
        src = QPointF(canvas.mapFromScene(_cell_center(canvas, "a")))
        far = src + QPointF(0, 60)
        # Press + move past threshold to arm drag
        _mouse(vp, QEvent.Type.MouseButtonPress, src)
        _mouse(vp, QEvent.Type.MouseMove, far)
        assert canvas._dragging, "drag should be armed"
        return canvas, lay

    def test_canvas_focusout_cancels_drag(self):
        """FocusOut while dragging: _dragging cleared, no mutation, no signals."""
        canvas, lay = self._armed_canvas()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        fo = QFocusEvent(QEvent.Type.FocusOut)
        QApplication.sendEvent(canvas, fo)
        assert not canvas._dragging
        assert canvas._zone_hint is None
        assert _rows(lay) == before
        assert starts == [] and completes == []

    def test_canvas_focusout_release_is_noop(self):
        """After focus-out cancel, trailing mouse release does not mutate."""
        canvas, lay = self._armed_canvas()
        before = _rows(lay)
        starts, completes = _spy_gestures(canvas)
        # Cancel via focus-out
        QApplication.sendEvent(canvas, QFocusEvent(QEvent.Type.FocusOut))
        # Now simulate the release that might still arrive
        vp = canvas.viewport()
        far = QPointF(canvas.mapFromScene(_cell_center(canvas, "b")))
        _mouse(vp, QEvent.Type.MouseButtonRelease, far,
               buttons=Qt.MouseButton.NoButton)
        assert _rows(lay) == before
        assert starts == [] and completes == []

    def test_pool_focusout_clears_stash_and_hint(self):
        """Pool focusOut clears _drag_field_id and canvas hint."""
        from firepro3d.titleblock_arrange import PoolList
        fs = [FieldDef(id=i, name=i) for i in ("a", "b")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("a", 40.0)]])
        canvas, _ = _canvas(lay)
        pool = PoolList()
        pool.bind_canvas(canvas)
        pool.set_fields(lay.pool_fields())
        pool.resize(200, 300)
        pool.show()
        # Arm pool drag manually
        pool._drag_field_id = "b"
        canvas._zone_hint = DropZone("insert", 1)   # simulate a hint being set
        # Send focus-out to pool
        QApplication.sendEvent(pool, QFocusEvent(QEvent.Type.FocusOut))
        assert pool._drag_field_id == ""
        assert canvas._zone_hint is None


# ─────────────────────────────────────────────────────────────────────────────
# Field-name tooltips (grill 2026-08-04 item 2): canvas cells + pool cards
# ─────────────────────────────────────────────────────────────────────────────

class TestTooltips:
    """Hover identification: cells render their OUTPUT, so the field name is
    invisible on the true render — the tooltip is the only name affordance.
    Name only; placement facts live in the props panel."""

    def _send_help_event(self, canvas, vp_pos):
        ev = QHelpEvent(QEvent.Type.ToolTip, vp_pos,
                        canvas.viewport().mapToGlobal(vp_pos))
        QApplication.sendEvent(canvas.viewport(), ev)
        return ev

    def test_canvas_tooltip_names_field_under_cursor(self):
        canvas, _ = _canvas()
        canvas.fit_strip()
        fid = canvas.solved.cell_field_ids[0]
        fname = canvas._layout_ref.field_map()[fid].name
        vp_pos = canvas.mapFromScene(canvas.solved.cell_rects[0].center())
        self._send_help_event(canvas, vp_pos)
        assert QToolTip.text() == fname

    def test_canvas_tooltip_names_revision_table_and_stamp(self):
        # The rev table and the empty stamp are the unidentifiable cells —
        # they MUST be name-identifiable on hover (grill item 2).
        canvas, lay = _canvas()
        canvas.fit_strip()
        for want in ("Revision Table", "Stamp"):
            fid = next(f.id for f in lay.fields if f.name == want)
            idx = canvas.solved.cell_field_ids.index(fid)
            vp_pos = canvas.mapFromScene(canvas.solved.cell_rects[idx].center())
            self._send_help_event(canvas, vp_pos)
            assert QToolTip.text() == want

    def test_canvas_tooltip_empty_off_strip(self, monkeypatch):
        # QToolTip.hideText() fades out asynchronously (text() can stay stale
        # for ~300ms), so assert deterministically at the QToolTip API
        # boundary: an off-strip hover must never showText and must hideText.
        canvas, _ = _canvas()
        canvas.fit_strip()
        shown, hidden = [], []
        monkeypatch.setattr(QToolTip, "showText",
                            lambda *a, **kw: shown.append(a))
        monkeypatch.setattr(QToolTip, "hideText",
                            lambda: hidden.append(1))
        off = canvas.solved.strip_rect.topLeft() + QPointF(-30.0, -30.0)
        vp_pos = canvas.mapFromScene(off)
        ev = self._send_help_event(canvas, vp_pos)
        assert shown == []
        assert hidden == [1]
        assert ev.isAccepted()

    def test_canvas_tooltip_safe_before_first_refresh(self, monkeypatch):
        # solved is None until refresh(); a ToolTip event must not crash.
        shown = []
        monkeypatch.setattr(QToolTip, "showText",
                            lambda *a, **kw: shown.append(a))
        canvas = StripCanvas()        # no provider, never refreshed
        canvas.resize(200, 200)
        canvas.show()
        vp_pos = QPoint(50, 50)
        ev = QHelpEvent(QEvent.Type.ToolTip, vp_pos,
                        canvas.viewport().mapToGlobal(vp_pos))
        QApplication.sendEvent(canvas.viewport(), ev)
        assert shown == []

    def test_canvas_tooltip_unnamed_field_falls_back_to_id(self):
        fs = [FieldDef(id="anon", name="", text="hello")]
        lay = TemplateLayout(fields=fs, rows=[[Slot("anon", 40.0)]])
        canvas, _ = _canvas(lay)
        canvas.fit_strip()
        vp_pos = canvas.mapFromScene(canvas.solved.cell_rects[0].center())
        self._send_help_event(canvas, vp_pos)
        assert QToolTip.text() == "anon"

    def test_pool_cards_carry_name_tooltips(self):
        from firepro3d.titleblock_arrange import PoolList
        fs = [FieldDef(id="r", name="Rev Table", kind="revision_table"),
              FieldDef(id="i", name="Logo", image_data="abc"),
              FieldDef(id="t", name="Note", text="hello\nworld")]
        pool = PoolList()
        pool.set_fields(fs)
        for i, f in enumerate(fs):
            assert pool.item(i).toolTip() == f.name
            assert pool.item(i).toolTip()          # non-empty


# ─────────────────────────────────────────────────────────────────────────────
# White paper background + fit-on-first-show
# ─────────────────────────────────────────────────────────────────────────────

class TestCanvasWhiteBackground:
    def test_canvas_has_white_paper_background(self):
        canvas, _ = _canvas()
        from PyQt6.QtWidgets import QGraphicsRectItem
        rects = [it for it in canvas.scene().items()
                 if isinstance(it, QGraphicsRectItem)]
        assert any(r.brush().color().name() == "#ffffff" for r in rects)
        # must be behind the renderer item
        bg = next(r for r in rects if r.brush().color().name() == "#ffffff")
        assert bg.zValue() < 0

    def test_first_show_fits_strip(self):
        lay = make_default_template().layout
        canvas = StripCanvas()
        canvas.set_provider(lambda: (lay, PAPER_W, PAPER_H, {}))
        canvas.refresh()
        canvas.resize(400, 600)
        canvas.show()
        _app.processEvents()
        vis = canvas.mapToScene(canvas.viewport().rect()).boundingRect()
        assert vis.contains(canvas.solved.strip_rect)

    def test_second_show_does_not_refit(self):
        """After the user zooms in, a second show must NOT reset the zoom."""
        lay = make_default_template().layout
        canvas = StripCanvas()
        canvas.set_provider(lambda: (lay, PAPER_W, PAPER_H, {}))
        canvas.refresh()
        canvas.resize(400, 600)
        canvas.show()
        _app.processEvents()
        # Zoom in manually
        canvas.scale(3.0, 3.0)
        t_after_zoom = canvas.transform().m11()
        # Hide + show again (simulates tab switch)
        canvas.hide()
        canvas.show()
        _app.processEvents()
        assert abs(canvas.transform().m11() - t_after_zoom) < 1e-6
