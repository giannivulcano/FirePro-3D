"""SB4d D2 / D4: the three view-marker categories, their host values (the
Sheet slot reads SheetManager.sheets_holding) and the shipped seeds."""
import json

import pytest
from PyQt6.QtCore import QPointF, QRectF

from tests._sb4d_helpers import add_sheet, dispose, plan_scene


def test_registries(qapp):
    from firepro3d import element_params as ep
    from firepro3d import system_blocks as sb
    assert ep.CATEGORIES[-3:] == ("Elevation", "Section", "Detail")
    assert [(k, s.tier, s.kind) for k, s in ep.PARAMS["Elevation"].items()] == [("Direction", 1, "text")]
    for cat in ("Section", "Detail"):
        assert [(k, s.tier, s.kind) for k, s in ep.PARAMS[cat].items()] == [
            ("Mark", 1, "text"), ("Sheet", 4, "text")]
    assert sb.ANNOTATION_CATEGORIES == ("Room", "Pipe", "Gridline", "Level",
                                        "Elevation", "Section", "Detail")
    assert (sb.LABEL_FIELD["Elevation"], sb.LABEL_FIELD["Section"], sb.LABEL_FIELD["Detail"]) == (
        "Direction", "Mark", "Mark")
    assert "Elevation" in sb.PAINT_WHEN_BLANK and "Section" not in sb.PAINT_WHEN_BLANK
    assert (sb.SYSTEM_DEFAULTS["Elevation"], sb.SYSTEM_DEFAULTS["Section"],
            sb.SYSTEM_DEFAULTS["Detail"]) == ("system-tags-elevationhead",
                                              "system-tags-sectionhead",
                                              "system-tags-detailcallout")


def test_category_of_splits_section_markers_on_cardinal(qapp):
    from firepro3d import element_params as ep
    ms, sec, det, tabs = plan_scene()
    try:
        sec.seed_cardinals()
        placed = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
        d = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        assert {ep.category_of(sec.marker(c)) for c in ("north", "south", "east", "west")} == {"Elevation"}
        assert ep.category_of(placed) == "Section"
        assert ep.category_of(d) == "Detail"
        hv = ep.host_values(sec.marker("east"))
        assert hv["Direction"].text == "E"
    finally:
        dispose(ms, sec, tabs)


def test_sheet_slot_reads_the_first_holding_sheet_in_sheet_order(qapp):
    """Blank when unplaced; the holding sheet's number; a legacy
    two-placement project cites the first sheet in SHEET order (Q6g), not
    the lowest number."""
    from firepro3d import element_params as ep
    ms, sec, det, tabs = plan_scene()
    try:
        d = det.create_detail("Detail 1", QRectF(0.0, 0.0, 2000.0, 2000.0))
        s = sec.place_section(QPointF(0.0, 0.0), QPointF(5000.0, 0.0))
        assert ep.host_values(d, {"Sheet"})["Sheet"].raw is None
        add_sheet(ms, "FP-1.0", [("plan", "Plan: Level 1")])
        add_sheet(ms, "FP-1.5", [("section", "Detail 1")])   # same name, other view type: never a detail's sheet
        add_sheet(ms, "FP-3.0", [("detail", "Detail 1"), ("section", s.name)])
        add_sheet(ms, "FP-2.0", [("detail", "Detail 1")])
        assert ep.host_values(d, {"Sheet"})["Sheet"].text == "FP-3.0"
        assert ep.host_values(s, {"Sheet"})["Sheet"].text == "FP-3.0"
        from firepro3d.paper_space import SheetManager, sheets_holding
        assert [x.number for x in sheets_holding(ms._sheets, "detail", "Detail 1")] == ["FP-3.0", "FP-2.0"]
        assert [x.number for x in SheetManager(ms._sheets).sheets_holding("detail", "Detail 1")] == [
            "FP-3.0", "FP-2.0"]
    finally:
        dispose(ms, sec, tabs)


def _first_cut_mm(radius_r):
    """First-cut seed radius (D2): r x BUBBLE_RADIUS_MM model mm at the default
    drawing scale 100 (ScaleManager._drawing_scale = 100.0) = r * R / 100 authored mm."""
    from firepro3d.gridline import BUBBLE_RADIUS_MM
    return radius_r * BUBBLE_RADIUS_MM / 100.0


@pytest.mark.parametrize("fname,bid,cat,keys,r_mm,split", [
    ("ElevationHead.fpdb", "system-tags-elevationhead", "Elevation", ["Direction"], _first_cut_mm(3.0), False),
    # Section + Detail restyled at smoke (Q19, 2026-11-04): 8 mm diameter driven by a
    # dim_diameter constraint (the second restyle; the first cut was 10 mm).
    ("SectionHead.fpdb", "system-tags-sectionhead", "Section", ["Mark", "Sheet"], 4.0, True),
    ("DetailCallout.fpdb", "system-tags-detailcallout", "Detail", ["Mark", "Sheet"], 4.0, True),
])
def test_shipped_seed(qapp, fname, bid, cat, keys, r_mm, split):
    """Shipped seeds: Elevation / Section at the first-cut proportions (D2, 3R / 2R),
    Detail at its smoke restyle (Q19) -- circle radius r_mm authored mm, the split
    line spanning the full diameter, the bound text in host-key order."""
    from firepro3d import block_library
    from firepro3d.assets import system_blocks_path
    from firepro3d.bound_label import eligible_definition
    from firepro3d.render_op import STROKE
    path = system_blocks_path("Tags", fname)
    d = block_library.load_block_file(path)
    assert d is not None and d.id == bid
    assert d.library == block_library.SYSTEM_LIBRARY and d.series == "Tags"
    assert eligible_definition(d, cat)
    assert [a["host_key"] for a in d.effective_attributes() if a.get("source") == "host"] == keys
    strokes = [o.path.boundingRect() for o in d.render_ops() if o.kind == STROKE]
    assert any(abs(b.width() - 2 * r_mm) < 1e-6 and abs(b.height() - 2 * r_mm) < 1e-6 for b in strokes)
    assert any(abs(b.height()) < 1e-9 and abs(b.width() - 2 * r_mm) < 1e-6
               and abs(b.left() + r_mm) < 1e-6 for b in strokes) is split      # centred on the circle
    with open(path, encoding="utf-8") as fh:
        texts = [p["text"] for p in json.load(fh)["primitives"] if p["type"] == "text"]
    assert texts == [f"@[{k}]" for k in keys]
