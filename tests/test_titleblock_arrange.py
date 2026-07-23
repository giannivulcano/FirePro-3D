"""StripCanvas: render, hit-testing, zone detection, selection."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

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
