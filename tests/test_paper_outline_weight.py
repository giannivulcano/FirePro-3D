"""Wall / Room / Floor / Roof outlines plot at the paper category weight.

Real PDF export through ``paper_export.export_pdf`` (transient PaperScene ->
apply_paper_overrides -> render -> restore), harness idioms from
tests/test_lt1_block_paper.py. Strokes are selected by geometry only (strictly
inside the viewport box), never by width.
"""
from unittest.mock import MagicMock

import fitz
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor

from firepro3d import paper_display as pd
from firepro3d.floor_slab import FloorSlab
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from firepro3d.roof import RoofItem
from firepro3d.room import Room
from firepro3d.wall import WallSegment

_VP_X, _VP_Y, _VP_W = 65.0, 30.0, 80.0
_SQ = [QPointF(-1200, -1200), QPointF(1200, -1200),
       QPointF(1200, 1200), QPointF(-1200, 1200)]


def _crop(scale):
    half = _VP_W / 2.0 / scale
    return QRectF(-half, -half, 2 * half, 2 * half)


def _build(kind):
    ms = Model_Space()
    if kind == "Wall":
        w = WallSegment(QPointF(-1500, 0), QPointF(1500, 0), thickness_mm=200)
        w.level = ms.active_level
        ms._walls.append(w)
        ms.addItem(w)
    elif kind == "Room":
        ms.addItem(Room(boundary=_SQ, color="#4488cc"))
    elif kind == "Floor":
        ms.addItem(FloorSlab(_SQ))
    elif kind == "Roof":
        ms.addItem(RoofItem(_SQ))
    elif kind == "HipRoof":
        r = RoofItem(_SQ)
        r._roof_type = "hip"          # pyramid on a square: 4 ridge/hip lines
        r._overhang_mm = 300.0        # overhang outline + dotted inner outline
        ms.addItem(r)
    return ms


def _export(tmp_path, ms, scale):
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"
    sheet.sheet_views = [SheetViewData("plan", "Plan: Level 1", "P", scale,
                                       _VP_X, _VP_Y, _VP_W, _VP_W)]
    resolver = MagicMock(spec=ViewResolver)
    resolver.resolve.side_effect = lambda vt, vn: (ms, QRectF(_crop(scale)))
    out = tmp_path / "o.pdf"
    paper_export.export_pdf([sheet], resolver, str(out), dpi=300)
    return out


def _inner_stroke_widths(pdf):
    """Width (mm) of every stroked path strictly inside the viewport box."""
    pt = 25.4 / 72.0
    doc = fitz.open(str(pdf))
    try:
        res = []
        for d in doc[0].get_drawings():
            if "s" not in (d.get("type") or ""):
                continue
            r = d["rect"]
            x0, y0, x1, y1 = (v * pt for v in (r.x0, r.y0, r.x1, r.y1))
            if (_VP_X + 1 < x0 and x1 < _VP_X + _VP_W - 1
                    and _VP_Y + 1 < y0 and y1 < _VP_Y + _VP_W - 1):
                res.append((d["width"] or 0.0) * pt)
        return res
    finally:
        doc.close()


def _set_weight(kind, weight):
    cats = pd.load_paper_categories()
    cats[kind]["line_weight"] = weight
    pd.save_paper_categories(cats)


@pytest.mark.parametrize("scale", [0.02, 0.01])            # 1:50, 1:100
@pytest.mark.parametrize("weight", ["Very Light", "Heavy"])
@pytest.mark.parametrize("kind", ["Wall", "Room", "Floor", "Roof"])
def test_outline_plots_at_category_weight(qapp, tmp_path, kind, weight, scale):
    save_paper_color_mode(PaperColorMode.BW)
    _set_weight(kind, weight)
    widths = _inner_stroke_widths(_export(tmp_path, _build(kind), scale))
    want = pd.resolve_line_weight_mm(weight)
    assert widths, "no outline stroke found inside the viewport"
    assert all(abs(w - want) < 0.02 for w in widths), (widths, want)


@pytest.mark.parametrize("scale", [0.02, 0.01])
def test_roof_secondary_lines_plot_at_roof_weight(qapp, tmp_path, scale):
    save_paper_color_mode(PaperColorMode.BW)
    _set_weight("Roof", "Heavy")
    widths = _inner_stroke_widths(_export(tmp_path, _build("HipRoof"), scale))
    want = pd.resolve_line_weight_mm("Heavy")
    # overhang outline + dotted inner outline + 4 hip lines (composition check)
    assert len(widths) >= 3, widths
    assert all(abs(w - want) < 0.02 for w in widths), (widths, want)


def test_hook_is_paper_only_and_restored(qapp):
    """The pass sets lw/paper_scale; restore removes it; canvas pen stays 1 px."""
    ms = _build("Wall")
    wall = ms._walls[0]
    saved = pd.apply_paper_overrides(ms, _crop(0.02), paper_scale=0.02)
    lw = pd.resolve_line_weight_mm(pd.load_paper_categories()["Wall"]["line_weight"])
    assert wall._paper_pen_width == pytest.approx(lw / 0.02)
    paper_pen = wall._outline_pen(QColor("#000000"))
    assert not paper_pen.isCosmetic()
    pd.restore_model_display(saved)
    assert getattr(wall, "_paper_pen_width", None) is None
    canvas_pen = wall._outline_pen(QColor("#000000"))
    assert canvas_pen.isCosmetic() and canvas_pen.widthF() == 1.0


from firepro3d.wall_opening import WallOpening

_OP_IDS = {"Door": "door_914", "Window": "window_900", "Opening": "blank_900"}


def _build_opening(kind):
    ms = _build("Wall")
    w = ms._walls[0]
    op = WallOpening(wall=w, feature_id=_OP_IDS[kind], offset_along=1500.0)
    ms.addItem(op)
    w.openings.append(op)
    op._reposition()
    return ms


@pytest.mark.parametrize("scale", [0.02, 0.01])
@pytest.mark.parametrize("kind", ["Door", "Window", "Opening"])
def test_opening_plots_at_its_category_weight(qapp, tmp_path, kind, scale):
    save_paper_color_mode(PaperColorMode.BW)
    _set_weight("Wall", "Heavy")      # 0.35
    _set_weight(kind, "Medium")       # 0.25 -- distinct from 1.5 px (0.127)
    widths = _inner_stroke_widths(_export(tmp_path, _build_opening(kind), scale))
    wall_w = pd.resolve_line_weight_mm("Heavy")
    op_w = pd.resolve_line_weight_mm("Medium")
    assert any(abs(w - op_w) < 0.02 for w in widths), widths
    assert all(abs(w - wall_w) < 0.02 or abs(w - op_w) < 0.02
               for w in widths), widths


@pytest.mark.parametrize("kind", ["Door", "Window", "Opening"])
def test_hidden_opening_category_hides_symbol(qapp, tmp_path, kind):
    """Hiding the opening's OWN row drops its strokes (stroke count, not width:
    under the Wall row an opening would plot at the wall weight)."""
    save_paper_color_mode(PaperColorMode.BW)
    _set_weight("Wall", "Heavy")
    shown = _inner_stroke_widths(_export(tmp_path, _build_opening(kind), 0.02))
    cats = pd.load_paper_categories()
    cats[kind]["visible"] = False
    pd.save_paper_categories(cats)
    hidden = _inner_stroke_widths(_export(tmp_path, _build_opening(kind), 0.02))
    wall_w = pd.resolve_line_weight_mm("Heavy")
    assert 0 < len(hidden) < len(shown), (shown, hidden)
    assert all(abs(w - wall_w) < 0.02 for w in hidden), hidden


def test_paper_tab_lists_openings_under_architecture():
    from firepro3d.display_manager import DisplayManager
    arch = DisplayManager._PS_GROUPS["Architecture"]
    assert arch[:4] == ["Wall", "Door", "Window", "Opening"]
