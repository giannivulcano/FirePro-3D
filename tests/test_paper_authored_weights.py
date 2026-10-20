"""Raw 2D shapes plot their authored named weight on sheets (AC1-AC4).

Paper "Construction" category is set to "Thick" (0.50 mm) so the category
fallback is distinguishable from every named weight used here
(Thin 0.35 / Thickest 0.70). Rendered at PPM px per paper mm; the ink
thickness is the longest dark run down any column in the middle half of
the viewport image (side edges of rectangles/regions lie outside it).
"""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import paper_display as pd
from firepro3d.block_definition import BlockDefinition
from firepro3d.fill_layers import FillLayers
from firepro3d.filled_region import FilledRegionItem
from firepro3d.geometry_2d import LineItem, PolylineItem, RectangleItem
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
from tests._paper_iso_helpers import _DetailMgrStub
from tests.lt3_support import hidden
from tests.test_filled_region import square_pieces

PPM = 20                     # render px per paper mm
CAT = "Thick"                # Construction category weight under test (0.50 mm)
TOL_PX = 1.5


class _PlanStub:
    _views: dict = {}

    def get(self, name):
        return None


class _DetailStub:
    detail_names: list = []

    def get_marker(self, name):
        return None


@pytest.fixture
def construction_thick(qapp):
    """B&W paper, Construction = Thick; restores the categories after."""
    save_paper_color_mode(PaperColorMode.BW)
    before = pd.load_paper_categories()
    cats = pd.load_paper_categories()
    cats["Construction"]["line_weight"] = CAT
    pd.save_paper_categories(cats)
    yield pd.resolve_line_weight_mm(CAT)
    pd.save_paper_categories(before)


def _ink_px(img):
    """Longest dark vertical run (px) over the middle-half columns."""
    best = 0
    for x in range(img.width() // 4, 3 * img.width() // 4):
        run = 0
        for y in range(img.height()):
            if QColor(img.pixel(x, y)).lightness() < 128:
                run += 1
                best = max(best, run)
            else:
                run = 0
    return best


def _paint(vp, w, h):
    img = QImage(int(w * PPM), int(h * PPM), QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.scale(PPM, PPM)
    vp.paint(p, None, None)
    p.end()
    return img


def _style(item, weight, linetype=None):
    item.style["weight"] = weight
    if linetype is not None:
        item.style["linetype"] = linetype
    return item


# shape factories: (model_span) -> item spanning the crop horizontally
def _line(span):
    return LineItem(QPointF(-0.2 * span, 0.5 * span), QPointF(1.2 * span, 0.5 * span))


def _poly(span):
    pl = PolylineItem(QPointF(-0.2 * span, 0.5 * span))
    pl.append_point(QPointF(1.2 * span, 0.5 * span))
    return pl


def _rect(span):
    return RectangleItem(QPointF(-0.2 * span, 0.3 * span), QPointF(1.2 * span, 0.7 * span))


SHAPES = {"line": _line, "polyline": _poly, "rect": _rect}
# (weight, use dashed linetype with dash weight Thickest, expected mm or None = CAT)
WEIGHTS = {
    "named_thin": ("Thin", False, 0.35),
    "named_thickest": ("Thickest", False, 0.70),
    "by_linetype_continuous": ("by_linetype", False, None),
    "by_linetype_dashed": ("by_linetype", True, 0.70),
}


def _plan_viewport(items, linetype_owner):
    """Real plan viewport at 1:20 over a 2000 mm crop -> 100 mm box."""
    ms = linetype_owner
    for it in items:
        it.level = "Level 1"
        ms.addItem(it)
        {LineItem: ms._draw_lines, PolylineItem: ms._polylines,
         RectangleItem: ms._draw_rects}[type(it)].append(it)
    lm = LevelManager()
    pvm = PlanViewManager()
    pvm.create("Level 1", lm)
    ms.active_level = "Level 1"
    ms.active_view_key = "plan:Plan: Level 1"
    lm.apply_to_scene(ms, "Level 1")
    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)
    data = SheetViewData("plan", "Plan: Level 1", "P", 0.05, 0, 0, 0, 0)
    paper = PaperScene(Sheet.create_default(), resolver)
    vp = paper.add_viewport(data)
    data.crop_rect = QRectF(0, 0, 2000, 2000)
    vp._recompute_size_from_scale()
    return vp, data.w, data.h


def _schematic_viewport(proj, prim_dicts):
    from firepro3d.schematic_scene import SchematicSceneManager
    sch = BlockDefinition.new(name="Riser", library="", series="",
                              primitives=prim_dicts, origin=(0.0, 0.0),
                              kind="schematic")
    proj.register_block_definition(sch)
    proj.push_undo_state()
    resolver = ViewResolver(proj, _PlanStub(), _DetailStub(), None,
                            schematic_scenes=SchematicSceneManager(proj))
    sheet = Sheet.create_default()
    proj._sheets = [sheet]
    vp = PaperScene(sheet, resolver).add_viewport(
        SheetViewData("schematic", sch.id, "", 1.0, 20.0, 20.0, 110.0, 110.0))
    return vp, vp._data.w, vp._data.h


def _expected_px(mm, cat_mm):
    return (cat_mm if mm is None else mm) * PPM


@pytest.mark.parametrize("wkey", list(WEIGHTS))
@pytest.mark.parametrize("shape", list(SHAPES))
def test_g1_plan_viewport_raw_shape_plots_authored_weight(construction_thick, shape, wkey):
    weight, dashed, mm = WEIGHTS[wkey]
    ms = Model_Space()
    lt = hidden(ms, weight="Thickest") if dashed else None
    item = _style(SHAPES[shape](2000.0), weight, lt)
    vp, w, h = _plan_viewport([item], ms)
    got = _ink_px(_paint(vp, w, h))
    want = _expected_px(mm, construction_thick)
    assert abs(got - want) <= TOL_PX, (shape, wkey, got, want)


def _region():
    """100 mm square outline at (10,10), no fill (only the outline inks)."""
    r = FilledRegionItem.from_pieces([square_pieces()])
    r.fill_layers = FillLayers()
    r.outline = True
    return r


@pytest.mark.parametrize("wkey", list(WEIGHTS))
@pytest.mark.parametrize("shape", list(SHAPES) + ["region"])
def test_g2_schematic_viewport_raw_shape_plots_authored_weight(construction_thick, shape, wkey):
    weight, dashed, mm = WEIGHTS[wkey]
    proj = Model_Space()
    lt = hidden(proj, weight="Thickest") if dashed else None
    item = _region() if shape == "region" else SHAPES[shape](100.0)
    _style(item, weight, lt)
    vp, w, h = _schematic_viewport(proj, [item.to_dict()])
    got = _ink_px(_paint(vp, w, h))
    want = _expected_px(mm, construction_thick)
    assert abs(got - want) <= TOL_PX, (shape, wkey, got, want)


def test_g3_canvas_pen_restored_after_paper_pass(construction_thick):
    """AC4: the paper pass leaves the canvas pen exactly as it found it."""
    ms = Model_Space()
    item = _style(_line(2000.0), "Thickest")
    vp, w, h = _plan_viewport([item], ms)
    item._sync_stroke_pen()
    before = item.pen()
    _paint(vp, w, h)
    after = item.pen()
    assert (after.widthF(), after.isCosmetic(), after.color().name()) == \
        (before.widthF(), before.isCosmetic(), before.color().name())


@pytest.mark.parametrize("weight,mm", [("Thickest", 0.70), ("by_linetype", None)])
def test_g4_block_op_in_schematic_viewport_unchanged(construction_thick, weight, mm):
    """AC3: block ops keep LT2-5 -- named = own mm; By Linetype = Blocks weight."""
    proj = Model_Space()
    sym = BlockDefinition.new(
        name="Sym", library="L", series="S",
        primitives=[_style(_line(100.0), weight).to_dict()], origin=(0.0, 0.0))
    proj.register_block_definition(sym)
    proj.push_undo_state()
    vp, w, h = _schematic_viewport(
        proj, [{"type": "block_instance", "block_id": sym.id,
                "pos": [0.0, 0.0], "rotation": 0.0}])
    blocks_mm = pd.resolve_line_weight_mm(
        pd.load_paper_categories()["Blocks"]["line_weight"])
    got = _ink_px(_paint(vp, w, h))
    want = (blocks_mm if mm is None else mm) * PPM
    assert abs(got - want) <= TOL_PX, (weight, got, want)
