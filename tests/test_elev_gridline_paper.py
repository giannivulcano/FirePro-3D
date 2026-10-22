"""AC3 / AC4: elevation gridlines plot like the plan gridline (weight,
paper-mm dash-dot, B&W colour, true-scale bubble) and elevation level datums
plot through the "Level Datum" paper row. Real PDF export of a plan scene and
a north elevation through a sheet viewport; selection by geometry."""
import re

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from tests._section_paper_helpers import (VP_W, VP_X, drawings, export_scene,
                                          to_paper)

X_MM = VP_X + VP_W / 2.0                       # the gridline plots at the box centre


def _plan_scene():
    ms = Model_Space()
    gl = GridlineItem(QPointF(2500.0, -1000.0), QPointF(2500.0, 1000.0), label="1")
    ms._gridlines.append(gl); ms.addItem(gl)
    return ms, QPointF(2500.0, 0.0)


def _elev_scene(section_scene_for):
    from firepro3d.section_scene import ElevGridlineItem
    ms, sec = section_scene_for("north")
    gl = GridlineItem(QPointF(2500.0, -3000.0), QPointF(2500.0, 3000.0), label="1")
    ms._gridlines.append(gl); ms.addItem(gl)
    sec._gridline_z_overrides["1"] = {"v_top": -1500.0, "v_bot": 500.0}   # 2 m: fits 1:50
    sec.rebuild()
    (eg,) = [i for i in sec.items() if isinstance(i, ElevGridlineItem)]
    assert eg.line().y1() == pytest.approx(-1500.0)          # override survived rebuild
    return sec, eg, QPointF(eg.line().x1(), -500.0)


def _vertical_line(pdf):
    hits = [d for d in drawings(pdf) if "s" in d["type"]
            and abs(d["rect"][0] - X_MM) < 0.5 and abs(d["rect"][2] - X_MM) < 0.5
            and d["rect"][3] - d["rect"][1] > 5.0]
    assert hits, "no gridline stroke"
    return max(hits, key=lambda d: d["rect"][3] - d["rect"][1])


def _bubble_dia(pdf):
    dias = [d["rect"][2] - d["rect"][0] for d in drawings(pdf) if "s" in d["type"]
            and abs((d["rect"][0] + d["rect"][2]) / 2.0 - X_MM) < 0.5
            and abs((d["rect"][2] - d["rect"][0]) - (d["rect"][3] - d["rect"][1])) < 0.2
            and d["rect"][2] - d["rect"][0] > 1.0]
    assert dias, "no bubble stroke"
    return max(dias)


def _dash_mm(d):
    nums = [float(n) for n in re.findall(r"[\d.]+", (d["dashes"] or "").split("]")[0])]
    return [n * 25.4 / 72.0 for n in nums]


def _same_dashes(a, b):
    da, db = _dash_mm(a), _dash_mm(b)
    return len(da) == len(db) > 0 and all(abs(x - y) <= 0.02 * max(x, y) for x, y in zip(da, db))


@pytest.mark.parametrize("scale", [0.01, 0.02])            # 1:100, 1:50
def test_elevation_gridline_plots_like_plan(qapp, tmp_path, section_scene_for, scale):
    save_paper_color_mode(PaperColorMode.BW)
    ms, c = _plan_scene()
    plan_pdf = export_scene(tmp_path, ms, scale, c, f"plan_{scale}.pdf")
    sec, eg, ce = _elev_scene(section_scene_for)
    elev_pdf = export_scene(tmp_path, sec, scale, ce, f"elev_{scale}.pdf")
    pl, el = _vertical_line(plan_pdf), _vertical_line(elev_pdf)
    expect = pd.resolve_line_weight_mm(pd.load_paper_categories()["Grid Line"]["line_weight"])
    assert pl["width"] == pytest.approx(expect, abs=0.01)     # control: the plan row
    assert el["width"] == pytest.approx(pl["width"], abs=0.01)
    assert _same_dashes(el, pl), (_dash_mm(el), _dash_mm(pl))
    assert tuple(el["color"]) == tuple(pl["color"]) == (0.0, 0.0, 0.0)
    assert _bubble_dia(elev_pdf) == pytest.approx(_bubble_dia(plan_pdf), abs=0.05)


def test_hidden_grid_line_row_hides_elevation_gridline(qapp, tmp_path, section_scene_for):
    save_paper_color_mode(PaperColorMode.BW)
    cats = pd.load_paper_categories()
    cats["Grid Line"]["visible"] = False
    pd.save_paper_categories(cats)
    sec, eg, ce = _elev_scene(section_scene_for)
    pdf = export_scene(tmp_path, sec, 0.01, ce, "hidden.pdf")
    assert not [d for d in drawings(pdf) if "s" in d["type"]
                and abs(d["rect"][0] - X_MM) < 0.5 and abs(d["rect"][2] - X_MM) < 0.5
                and d["rect"][3] - d["rect"][1] > 5.0]
    assert eg.isVisible()                                     # restored after the pass


def test_paper_pass_restores_elevation_gridline(qapp, tmp_path, section_scene_for):
    save_paper_color_mode(PaperColorMode.BW)             # the pass swaps colour srcs
    sec, eg, ce = _elev_scene(section_scene_for)

    def _state():
        b, lb = eg.bubble1, eg.bubble1._label
        return (eg._grid_src, b.rect(), b._pen_src, b._brush_src,
                lb.font().pixelSize(), lb.scale(), lb._src, lb._tint, eg.opacity())
    before = _state()
    export_scene(tmp_path, sec, 0.01, ce, "restore.pdf")
    assert _state() == before
    assert eg._paper_line_w_mm == 0.0 and eg.bubble1._paper_pen_width is None


def test_elevation_datum_plots_through_level_datum_row(qapp, tmp_path, section_scene_for):
    save_paper_color_mode(PaperColorMode.BW)
    sec, eg, ce = _elev_scene(section_scene_for)
    pdf = export_scene(tmp_path, sec, 0.01, ce, "datum.pdf")
    expect = pd.resolve_line_weight_mm(
        pd.load_paper_categories()["Level Datum"]["line_weight"])
    y = to_paper(QPointF(0.0, 0.0), ce, 0.01)[1]                 # Level 1: v = 0
    lines = [d for d in drawings(pdf) if "s" in d["type"]
             and abs(d["rect"][1] - y) < 0.3 and abs(d["rect"][3] - y) < 0.3
             and d["rect"][2] - d["rect"][0] > 10.0]
    assert lines, "no datum stroke"
    d = max(lines, key=lambda d: d["rect"][2] - d["rect"][0])
    assert d["width"] == pytest.approx(expect, abs=0.01)
    assert tuple(d["color"]) == (0.0, 0.0, 0.0)
    assert _same_dashes(d, _vertical_line(pdf)), (_dash_mm(d),)  # same paper-mm dash-dot


def test_custom_grid_line_colour_reaches_elevation_gridline(qapp, tmp_path, section_scene_for):
    """Custom mode: the row colour (not the paper-surface token default)
    reaches the elevation line and bubble, as on the plan gridline."""
    save_paper_color_mode(PaperColorMode.CUSTOM)
    cats = pd.load_paper_categories()
    cats["Grid Line"]["color"] = "#cc0000"
    pd.save_paper_categories(cats)
    red = (0.8, 0.0, 0.0)
    ms, c = _plan_scene()
    plan_pdf = export_scene(tmp_path, ms, 0.01, c, "plan_custom.pdf")
    sec, eg, ce = _elev_scene(section_scene_for)
    elev_pdf = export_scene(tmp_path, sec, 0.01, ce, "elev_custom.pdf")
    for pdf in (plan_pdf, elev_pdf):
        col = _vertical_line(pdf)["color"]
        assert tuple(round(v, 2) for v in col) == red, (pdf.name, col)
        rings = [d for d in drawings(pdf) if "s" in d["type"]
                 and abs((d["rect"][0] + d["rect"][2]) / 2.0 - X_MM) < 0.5
                 and abs((d["rect"][2] - d["rect"][0]) - (d["rect"][3] - d["rect"][1])) < 0.2
                 and 1.0 < d["rect"][2] - d["rect"][0] < 20.0]   # not the viewport frame
        assert rings and all(tuple(round(v, 2) for v in d["color"]) == red
                             for d in rings), (pdf.name, [d["color"] for d in rings])


def _datum_line(pdf, ce):
    import fitz
    y = to_paper(QPointF(0.0, 0.0), ce, 0.01)[1]                 # Level 1: v = 0
    pt = 25.4 / 72.0
    doc = fitz.open(str(pdf))
    try:
        # Any type: Qt's PDF engine plots a translucent stroke as a filled
        # outline ("f", colour and opacity on the fill side).
        hits = [d for d in doc[0].get_drawings()
                if abs(d["rect"].y0 * pt - y) < 0.3 and abs(d["rect"].y1 * pt - y) < 0.3
                and (d["rect"].x1 - d["rect"].x0) * pt > 10.0]
    finally:
        doc.close()
    assert hits, "no datum stroke"
    return max(hits, key=lambda d: d["rect"].x1 - d["rect"].x0)


def test_level_datum_row_colour_and_opacity_reach_datum_line(qapp, tmp_path, section_scene_for):
    """Custom row colour and row Opacity reach the drawForeground datum line."""
    save_paper_color_mode(PaperColorMode.CUSTOM)
    cats = pd.load_paper_categories()
    cats["Level Datum"]["color"] = "#cc0000"
    cats["Level Datum"]["opacity"] = 50
    pd.save_paper_categories(cats)
    sec, eg, ce = _elev_scene(section_scene_for)
    d = _datum_line(export_scene(tmp_path, sec, 0.01, ce, "datum_custom.pdf"), ce)
    col = d.get("color") or d.get("fill")
    op = d.get("stroke_opacity") if d.get("color") else d.get("fill_opacity")
    assert tuple(round(v, 2) for v in col) == (0.8, 0.0, 0.0), col
    assert op == pytest.approx(0.5, abs=0.02), op


def test_paper_pass_restores_elevation_datum(qapp, tmp_path, section_scene_for):
    from firepro3d.section_scene import ElevDatumItem, _ColourSrcMixin
    save_paper_color_mode(PaperColorMode.BW)             # the pass swaps colour srcs
    sec, eg, ce = _elev_scene(section_scene_for)
    (dt,) = [i for i in sec.items()                      # Level 1, inside the crop
             if isinstance(i, ElevDatumItem) and abs(i._v) < 1e-6]

    def _state():
        kids = [(c._pen_src, c._brush_src, c._src_tint, c._paper_pen_width)
                for c in dt.childItems() if isinstance(c, _ColourSrcMixin)]
        return (dt._color_src, dt._fill_src, dt._paper_line_w_mm, dt.opacity(), kids)
    before = _state()
    seen = []
    orig = dt.enter_paper_pass
    dt.enter_paper_pass = lambda *a, **k: seen.append(1) or orig(*a, **k)
    export_scene(tmp_path, sec, 0.01, ce, "datum_restore.pdf")
    assert seen                                          # the pass reached the datum
    assert _state() == before
