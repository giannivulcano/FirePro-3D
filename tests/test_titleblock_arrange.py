"""StripCanvas: render, hit-testing, zone detection, selection."""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

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
        canvas, _ = _canvas()
        r = canvas.solved.cell_rects[1]          # default row 1 = Company, single
        mid_y = r.center().y()
        left = canvas.zone_at(QPointF(r.left() + r.width() * 0.25, mid_y))
        right = canvas.zone_at(QPointF(r.left() + r.width() * 0.75, mid_y))
        assert (left.kind, right.kind) == ("pair_left", "pair_right")
        assert left.row_index == right.row_index == 1

    def test_paired_row_middle_is_full_for_outsider(self):
        canvas, lay = _canvas()
        ri = next(i for i, row in enumerate(lay.rows) if len(row) == 2)
        first, _n = canvas.solved.row_spans[ri]
        r = canvas.solved.cell_rects[first]
        z = canvas.zone_at(QPointF(r.right(), r.center().y()))
        assert z.kind == "full"

    def test_paired_row_halves_for_member_swap(self):
        canvas, lay = _canvas()
        ri = next(i for i, row in enumerate(lay.rows) if len(row) == 2)
        member = lay.rows[ri][0].field_id
        first, _n = canvas.solved.row_spans[ri]
        r = canvas.solved.cell_rects[first]      # left cell of the pair
        z = canvas.zone_at(QPointF(r.center().x(), r.center().y()),
                           dragged_field_id=member)
        assert z.kind in ("pair_left", "pair_right")
        assert z.row_index == ri

    def test_own_single_row_interior_is_full(self):
        canvas, lay = _canvas()
        # row 1 is single (Company); dragging its own field over its interior
        fid = lay.rows[1][0].field_id
        r = canvas.solved.cell_rects[1]
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
