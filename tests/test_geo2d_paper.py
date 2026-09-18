"""Paper-plot verification for filled 2D geometry (geo2d-level-fill feature).

Tests:
  A) A solid-filled RectangleItem on Level 1 plots non-white pixels in a
     Level-1 viewport.
  B) A hatch-filled CircleItem on Level 1 plots non-white pixels.
  C) Per-viewport level isolation: a RectangleItem on "Level 2" is invisible
     in a Level-1 viewport but renders in a Level-2 viewport.
     Uses distinct model-space Y to separate the two item rows in pixels.

Harness mirrors test_paper_construction_plots.py exactly.
"""
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QImage, QPainter, QColor

from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.model_space import Model_Space
from firepro3d.geometry_2d import RectangleItem, CircleItem
from tests._paper_iso_helpers import _DetailMgrStub


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (mirrored from test_paper_construction_plots.py)
# ─────────────────────────────────────────────────────────────────────────────

def _render(vp, data, margin=40):
    """Render *vp* into a white QImage with *margin* padding; return image."""
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


def _build_vp(scene, level_name, lm, pvm, resolver):
    """Wire a real plan viewport over crop 0..1000 for *scene* active on *level_name*."""
    scene.active_level = level_name
    scene.active_view_key = f"plan:Plan: {level_name}"
    lm.apply_to_scene(scene, level_name)
    sheet = Sheet.create_default()
    data = SheetViewData("plan", f"Plan: {level_name}", "P", 0.05, 40, 40, 0, 0)
    paper = PaperScene(sheet, resolver)
    vp = paper.add_viewport(data)
    data.crop_rect = QRectF(0, 0, 1000, 1000)
    vp._recompute_size_from_scale()
    return vp, data


def _row_interior_nonwhite(img, y, lo, hi):
    white = QColor("white").rgb()
    return sum(img.pixel(x, y) != white for x in range(lo, hi))


# ─────────────────────────────────────────────────────────────────────────────
# Test A — solid-filled rectangle plots on paper
# ─────────────────────────────────────────────────────────────────────────────

def test_solid_fill_rectangle_plots_on_paper(qapp):
    """A RectangleItem with fill_type='solid' must produce non-white pixels
    within the viewport interior when rendered through a paper viewport."""
    ms = Model_Space()
    lm = LevelManager()
    pvm = PlanViewManager()
    pvm.create("Level 1", lm)
    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)

    rect = RectangleItem(QPointF(200, 200), QPointF(800, 800))
    rect.level = "Level 1"
    rect.fill_type = "solid"
    rect.fill_pattern = "diagonal"
    rect.fill_opacity = 0.8
    rect._display_fill_color = "#333333"   # dark grey — clearly non-white on paper
    assert rect.pen().color().name() == "#ffffff"   # default white outline
    ms._draw_rects.append(rect)
    ms.addItem(rect)

    vp, data = _build_vp(ms, "Level 1", lm, pvm, resolver)
    img = _render(vp, data)

    inside = _non_white_inside(img, data)
    assert inside > 0, (
        f"solid-filled rectangle did not plot: {inside} non-white pixels inside "
        f"the viewport. Fill is white-on-white (fill not reaching paper render)."
    )

    # Pen colour restored to original white after render.
    assert rect.pen().color().name() == "#ffffff"


# ─────────────────────────────────────────────────────────────────────────────
# Test B — hatch-filled shape plots on paper
# ─────────────────────────────────────────────────────────────────────────────

def test_hatch_fill_circle_plots_on_paper(qapp):
    """A CircleItem with fill_type='hatch' must produce non-white interior
    pixels when rendered through a paper viewport."""
    ms = Model_Space()
    lm = LevelManager()
    pvm = PlanViewManager()
    pvm.create("Level 1", lm)
    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)

    circle = CircleItem(QPointF(500, 500), 300)
    circle.level = "Level 1"
    circle.fill_type = "hatch"
    circle.fill_pattern = "diagonal"
    circle._display_fill_color = "#000000"
    assert circle.pen().color().name() == "#ffffff"   # default white
    ms._draw_circles.append(circle)
    ms.addItem(circle)

    vp, data = _build_vp(ms, "Level 1", lm, pvm, resolver)
    img = _render(vp, data)

    inside = _non_white_inside(img, data)
    assert inside > 0, (
        f"hatch-filled circle did not plot: {inside} non-white pixels inside "
        f"the viewport. Hatch fill not reaching paper render."
    )

    # Pen colour restored.
    assert circle.pen().color().name() == "#ffffff"


# Test C (per-viewport level isolation for filled 2D primitives) retired
# under containment C3: primitives are level-less; block-instance level
# isolation is covered headless in test_block_instance_level.py.
