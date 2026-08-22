"""Bug #3: 2D construction/draw geometry must plot on paper sheets.

Root cause (fixed): RectangleItem/CircleItem/ArcItem/... default to pen color
white (#ffffff) and read self.pen() directly in paint(). apply_paper_overrides
had no paper category for them, so _category_for_item returned None and they
were skipped -> white pen on white paper -> invisible.

Fix: a paper-only "Construction" category (FACTORY color #000000) that sets the
item's PEN COLOR (not just _display_color). Default paper color mode is BW.

REAL domain items + rendered-pixel assertions (never synthetic QGraphicsRectItem).
Red-verify: with the fix reverted, (a) counts 0 non-white pixels inside the box.
"""
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QImage, QPainter, QColor
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.model_space import Model_Space
from firepro3d.construction_geometry import RectangleItem, CircleItem
from tests._paper_iso_helpers import _DetailMgrStub


def _render(vp, data, margin=40):
    """Render viewport into a white QImage translated by *margin*; return image."""
    img = QImage(int(data.w + 2 * margin), int(data.h + 2 * margin + 20),
                 QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.translate(margin, margin)
    vp.paint(p, None, None)
    p.end()
    return img


def _non_white_inside(img, data, margin=40):
    white = QColor("white").rgb()
    return sum(img.pixel(x, y) != white
               for x in range(margin + 2, int(margin + data.w - 2))
               for y in range(margin + 2, int(margin + data.h - 2)))


def _build(scene):
    """Wire a real plan viewport over crop 0..1000 for *scene* (active Level 1)."""
    lm = LevelManager()
    pvm = PlanViewManager()
    pvm.create("Level 1", lm)
    scene.active_level = "Level 1"
    scene.active_view_key = "plan:Plan: Level 1"
    lm.apply_to_scene(scene, "Level 1")
    resolver = ViewResolver(scene, pvm, _DetailMgrStub(), None, level_manager=lm)
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Plan: Level 1", "P", 0.05, 40, 40, 0, 0)
    paper = PaperScene(sheet, resolver)
    vp = paper.add_viewport(data)
    data.crop_rect = QRectF(0, 0, 1000, 1000)
    vp._recompute_size_from_scale()
    return vp, data


def test_default_rectangle_plots_black_on_paper(qapp):
    ms = Model_Space()
    # DEFAULT color = white #ffffff (invisible on white paper before the fix).
    rect = RectangleItem(QPointF(200, 200), QPointF(800, 800))
    rect.level = "Level 1"
    assert rect.pen().color().name() == "#ffffff"   # guard: white default
    ms._draw_rects.append(rect)
    ms.addItem(rect)

    vp, data = _build(ms)
    img = _render(vp, data)

    # (a) The white default rect now plots (black on paper) — non-white pixels
    # inside the crop box. Red-verify: 0 before the fix (white on white).
    inside = _non_white_inside(img, data)
    assert inside > 0, f"rectangle did not plot: {inside} non-white pixels inside"

    # (b) After render, the pen color is restored to the model white.
    assert rect.pen().color().name() == "#ffffff"


def test_default_circle_plots_black_on_paper(qapp):
    ms = Model_Space()
    circle = CircleItem(QPointF(500, 500), 300)     # default white
    circle.level = "Level 1"
    assert circle.pen().color().name() == "#ffffff"
    ms._draw_circles.append(circle)
    ms.addItem(circle)

    vp, data = _build(ms)
    img = _render(vp, data)

    inside = _non_white_inside(img, data)
    assert inside > 0, f"circle did not plot: {inside} non-white pixels inside"
    assert circle.pen().color().name() == "#ffffff"


def test_construction_line_width_is_true_on_paper_mm(qapp):
    """The construction pen width must render at true ON-PAPER mm, not
    model-units-times-scale (which is a sub-pixel hairline at architectural
    scale — plots black but "very thin", the smoke-test symptom).

    Renders supersampled at a known px/mm and measures the top-edge line
    thickness. Red-verify: with the buggy width (lw_mm, no /paper_scale) the
    dark core is < 2 px; the fix (lw_mm / paper_scale) yields a real weight.
    """
    ppm = 20                      # render px per paper-mm (~500 dpi)
    scale = 0.05                  # 1:20 viewport
    ms = Model_Space()
    rect = RectangleItem(QPointF(200, 200), QPointF(800, 800))  # white default
    rect.level = "Level 1"
    ms._draw_rects.append(rect)
    ms.addItem(rect)

    lm = LevelManager(); pvm = PlanViewManager(); pvm.create("Level 1", lm)
    ms.active_level = "Level 1"; ms.active_view_key = "plan:Plan: Level 1"
    lm.apply_to_scene(ms, "Level 1")
    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Plan: Level 1", "P", scale, 0, 0, 0, 0)
    paper = PaperScene(sheet, resolver)
    vp = paper.add_viewport(data)
    data.crop_rect = QRectF(0, 0, 1000, 1000)
    vp._recompute_size_from_scale()

    # Supersampled render: painter scaled by ppm, viewport box at (0,0).
    W = int(data.w * ppm); H = int(data.h * ppm)
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.scale(ppm, ppm)
    vp.paint(p, None, None)
    p.end()

    # Rect top edge on paper: y = 200 model * scale = 10mm -> 10*ppm px.
    edge_y = int(200 * scale * ppm)          # 200px
    col_x = int(500 * scale * ppm)           # rect mid-x -> 500px
    # Count DARK pixels (near-black core, excludes faint antialiased hairline)
    # in a vertical band spanning the top edge.
    dark = 0
    for y in range(edge_y - 8, edge_y + 8):
        px = img.pixel(col_x, y)
        r, g, b = (px >> 16) & 0xFF, (px >> 8) & 0xFF, px & 0xFF
        if r < 100 and g < 100 and b < 100:
            dark += 1
    # True 0.18mm ("Light") on paper at ppm=20 -> ~3-4 px dark core.
    # Buggy (0.18 * 0.05 = 0.009mm) -> ~0.18px -> a faint hairline, < 2 dark px.
    assert dark >= 2, f"construction line too thin: {dark} dark px (hairline bug)"
