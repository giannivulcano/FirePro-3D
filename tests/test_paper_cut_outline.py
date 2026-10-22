"""AC1: a plan wall / floor slab cut by the view range plots its outline at
the full paper category weight (fill -> section hatch -> outline).

Real PDF export (tests/_section_paper_helpers.py) rasterised by MuPDF at
40 px/mm over a clip around the item's top face; the outline's dark run down
a column = its plotted width. The section body is set white so only the
outline (and hatch lines, which only lengthen a run) read dark; the minimum
over several columns rejects a hatch line touching the face.
"""
import fitz
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.floor_slab import FloorSlab
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from firepro3d.wall import WallSegment
from tests._section_paper_helpers import export_scene, to_paper

PX_PER_MM = 40
SCALE = 0.02                                   # 1:50
_ORIGIN = QPointF(0.0, 0.0)


def _set_paper(kind, lw_mm):
    cats = pd.load_paper_categories()
    cats[kind]["line_weight"] = pd.nearest_weight_name(lw_mm)
    cats[kind]["section_color"] = "#ffffff"     # white body: only lines read dark
    cats[kind]["fill"] = "#ffffff"
    pd.save_paper_categories(cats)
    return pd.resolve_line_weight_mm(cats[kind]["line_weight"])


def _build(kind, cut):
    ms = Model_Space()
    if kind == "Wall":
        it = WallSegment(QPointF(-1500, 0), QPointF(1500, 0), thickness_mm=200)
        it.level = ms.active_level
        ms._walls.append(it)
        ms.addItem(it)
        top_y = -100.0                          # scene y of the top face
    else:
        it = FloorSlab([QPointF(-1200, -1200), QPointF(1200, -1200),
                        QPointF(1200, 1200), QPointF(-1200, 1200)])
        ms.addItem(it)
        top_y = -1200.0
    it._is_section_cut = cut
    return ms, top_y


def _min_first_dark_run(pdf, face_y_mm):
    """Min over 9 columns of the first dark run's length (px) in a clip
    spanning 2 mm above to 2 mm below the face."""
    doc = fitz.open(str(pdf))
    try:
        pt = 72.0 / 25.4
        clip = fitz.Rect(100.0 * pt, (face_y_mm - 2.0) * pt,
                         110.0 * pt, (face_y_mm + 2.0) * pt)
        pix = doc[0].get_pixmap(dpi=int(PX_PER_MM * 25.4), clip=clip)
        runs = []
        for x in range(pix.width // 10, pix.width, pix.width // 10)[:9]:
            n, seen = 0, False
            for y in range(pix.height):
                r, g, b = pix.pixel(x, y)[:3]
                dark = (r + g + b) / 3.0 < 128
                if dark:
                    n += 1
                    seen = True
                elif seen:
                    break
            runs.append(n)
        return min(runs)
    finally:
        doc.close()


@pytest.mark.parametrize("lw_mm", [0.35, 0.7])
@pytest.mark.parametrize("cut", [False, True])
@pytest.mark.parametrize("kind", ["Wall", "Floor"])
def test_cut_outline_plots_full_category_weight(qapp, tmp_path, kind, cut, lw_mm):
    save_paper_color_mode(PaperColorMode.BW)
    lw = _set_paper(kind, lw_mm)
    ms, top_y = _build(kind, cut)
    pdf = export_scene(tmp_path, ms, SCALE, _ORIGIN, f"{kind}_{cut}_{lw_mm}.pdf")
    face_y_mm = to_paper(QPointF(0.0, top_y), _ORIGIN, SCALE)[1]
    got = _min_first_dark_run(pdf, face_y_mm)
    assert abs(got - round(lw * PX_PER_MM)) <= 1, (kind, cut, lw, got)
