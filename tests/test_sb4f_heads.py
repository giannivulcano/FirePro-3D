"""SB4f AC5: the head's top slot is the number of the viewport showing the view,
blank while unplaced with the head still drawn; Mark stays the browser identity."""
import pytest
from PyQt6.QtCore import QPointF, QRectF

from firepro3d import element_params as ep
from tests._sb4d_helpers import add_sheet, dispose, paper_view, plan_scene


@pytest.fixture
def rig(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    yield ms, sec, det
    dispose(ms, sec, tabs)


def test_number_reads_the_viewport_on_the_first_sheet_in_order(rig):
    ms, sec, det = rig
    d = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
    assert ep.host_values(d, {"Number"})["Number"].raw is None
    add_sheet(ms, "FP-1.5", [("section", "Detail 1")]).sheet_views[0].view_number = "9"  # other type
    add_sheet(ms, "FP-3.0", [("plan", "Level 1"), ("detail", "Detail 1")]
              ).sheet_views[1].view_number = "4"
    add_sheet(ms, "FP-2.0", [("detail", "Detail 1")]).sheet_views[0].view_number = "6"
    assert ep.host_values(d, {"Number"})["Number"].text == "4"


def test_section_number(rig):
    ms, sec, det = rig
    s = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    add_sheet(ms, "FP-3.0", [("section", s.name)]).sheet_views[0].view_number = "2"
    assert ep.host_values(s, {"Number"})["Number"].text == "2"


def test_blank_legacy_number_is_a_blank_slot(rig):
    ms, sec, det = rig
    d = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
    add_sheet(ms, "FP-3.0", [("detail", "Detail 1")])       # view_number ""
    assert ep.host_values(d, {"Number"})["Number"].raw is None


def test_unplaced_head_still_draws(rig):
    ms, sec, det = rig
    d = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
    s = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
    assert d.bubble.paints()
    assert s.head_a.paints()


def test_shipped_heads_bind_number_not_mark(rig):
    ms, sec, det = rig
    for cat in ("Section", "Detail"):
        defn = ms.annotation_block(cat)
        keys = [a["host_key"] for a in defn.effective_attributes() if a.get("source") == "host"]
        assert keys == ["Number", "Sheet"]


def test_number_edit_and_undo_reach_the_head(rig):
    ms, sec, det = rig
    d = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
    sheet = add_sheet(ms, "FP-3.0", [("detail", "Detail 1")])
    sheet.sheet_views[0].view_number = "7"
    _view, ps = paper_view(ms, sec, det, sheet)
    calls = []
    real = d.refresh_heads
    d.refresh_heads = lambda: (calls.append(1), real())[1]
    ps.commit_viewport_edit(ps.get_viewports()[0], view_number="9")
    assert calls and d.bubble.host_values({"Number"})["Number"].text == "9"
    calls.clear()
    ps.undo_stack.undo()
    assert calls and d.bubble.host_values({"Number"})["Number"].text == "7"
