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
from firepro3d.construction_geometry import RectangleItem, CircleItem
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


# ─────────────────────────────────────────────────────────────────────────────
# Test C — per-viewport level isolation
# ─────────────────────────────────────────────────────────────────────────────

def test_level_isolation_filled_rect_in_correct_viewport_only(qapp):
    """DURABLE pixel proof of per-viewport level isolation for filled 2D geometry.

    Setup:
      - rect_l1 on Level 1 at model y=200..400  (maps to pixel rows near top of crop)
      - rect_l2 on Level 2 at model y=600..800  (maps to pixel rows near bottom)

    Level-1 viewport (cropped 0..1000):
      - rect_l1 should be visible → non-white pixels in its y-band.
      - rect_l2 should be HIDDEN (wrong level) → white in its y-band.

    Level-2 viewport (same crop):
      - rect_l2 should be visible → non-white pixels in its y-band.
      - rect_l1 should be HIDDEN (wrong level) → white in its y-band.

    Renders each viewport directly (not the full PaperScene) using distinct
    model-space y positions so the two items land on different pixel rows.
    The only way to get the correct band inked and the wrong band blank is if
    level isolation swapped visibility before each render.
    """
    ms = Model_Space()
    lm = LevelManager()
    pvm = PlanViewManager()
    pvm.create("Level 1", lm)
    pvm.create("Level 2", lm)
    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)

    # Rect on Level 1 — distinct y range well inside crop, clearly separated.
    rect_l1 = RectangleItem(QPointF(100, 200), QPointF(900, 400))
    rect_l1.level = "Level 1"
    rect_l1.fill_type = "solid"
    rect_l1._display_fill_color = "#333333"
    rect_l1.fill_opacity = 1.0
    ms._draw_rects.append(rect_l1)
    ms.addItem(rect_l1)

    # Rect on Level 2 — different y range.
    rect_l2 = RectangleItem(QPointF(100, 600), QPointF(900, 800))
    rect_l2.level = "Level 2"
    rect_l2.fill_type = "solid"
    rect_l2._display_fill_color = "#333333"
    rect_l2.fill_opacity = 1.0
    ms._draw_rects.append(rect_l2)
    ms.addItem(rect_l2)

    # ── Build Level-1 viewport ───────────────────────────────────────────────
    scale = 0.05
    sheet = Sheet.create_default()
    data_l1 = SheetViewData("plan", "Plan: Level 1", "L1", scale, 40, 40, 0, 0)
    paper_l1 = PaperScene(sheet, resolver)
    vp_l1 = paper_l1.add_viewport(data_l1)
    data_l1.crop_rect = QRectF(0, 0, 1000, 1000)
    vp_l1._recompute_size_from_scale()

    # ── Build Level-2 viewport ───────────────────────────────────────────────
    sheet2 = Sheet.create_default()
    data_l2 = SheetViewData("plan", "Plan: Level 2", "L2", scale, 40, 40, 0, 0)
    paper_l2 = PaperScene(sheet2, resolver)
    vp_l2 = paper_l2.add_viewport(data_l2)
    data_l2.crop_rect = QRectF(0, 0, 1000, 1000)
    vp_l2._recompute_size_from_scale()

    # Make Level 1 active (on-screen state) — the "wrong" state for L2 viewport.
    ms.active_level = "Level 1"
    ms.active_view_key = "plan:Plan: Level 1"
    lm.apply_to_scene(ms, "Level 1")
    assert rect_l1.isVisible() is True   # sanity
    assert rect_l2.isVisible() is False  # sanity: L2 rect hidden on L1 screen

    # ── Render and probe helpers ─────────────────────────────────────────────
    vp_w = int(data_l1.w)
    vp_h = int(data_l1.h)
    margin = 8

    def render_vp(vp):
        img = QImage(vp_w + 2 * margin, vp_h + 2 * margin,
                     QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.translate(margin, margin)
        vp.paint(p, None, None)
        p.end()
        return img

    # Pixel row for the CENTRE of each rect under scale 0.05
    # model y -> paper y = model_y * scale; offset by margin
    def paper_y_of(model_y):
        return int(round(model_y * scale)) + margin

    y_band_l1_center = paper_y_of(300)   # centre of L1 rect (200..400 -> y=300)
    y_band_l2_center = paper_y_of(700)   # centre of L2 rect (600..800 -> y=700)

    # Probe interior x range (skip border columns ~2px each side)
    ix_lo = margin + 6
    ix_hi = vp_w + margin - 6

    def band_peak(img, cy, half=10):
        lo = max(0, cy - half)
        hi = min(img.height(), cy + half + 1)
        return max((_row_interior_nonwhite(img, y, ix_lo, ix_hi)
                    for y in range(lo, hi)), default=0)

    # ── Level-1 viewport render ──────────────────────────────────────────────
    img_l1 = render_vp(vp_l1)

    l1_vp_l1_peak = band_peak(img_l1, y_band_l1_center)  # L1 rect in L1 vp → should ink
    l2_vp_l1_peak = band_peak(img_l1, y_band_l2_center)  # L2 rect in L1 vp → should be blank

    interior_w = ix_hi - ix_lo
    print(f"[L1 vp] l1 rect band peak={l1_vp_l1_peak}  "
          f"l2 rect band peak={l2_vp_l1_peak}  interior_w={interior_w}")

    assert l1_vp_l1_peak > 0, (
        f"Level-1 rect not inked in Level-1 viewport (peak={l1_vp_l1_peak}). "
        f"Fill did not plot through the paper render path."
    )
    assert l2_vp_l1_peak == 0, (
        f"Level-2 rect appeared in Level-1 viewport (peak={l2_vp_l1_peak}). "
        f"Per-viewport isolation is broken for filled 2D geometry."
    )

    # ── Level-2 viewport render ──────────────────────────────────────────────
    img_l2 = render_vp(vp_l2)

    l2_vp_l2_peak = band_peak(img_l2, y_band_l2_center)  # L2 rect in L2 vp → should ink
    l1_vp_l2_peak = band_peak(img_l2, y_band_l1_center)  # L1 rect in L2 vp → should be blank

    print(f"[L2 vp] l2 rect band peak={l2_vp_l2_peak}  "
          f"l1 rect band peak={l1_vp_l2_peak}  interior_w={interior_w}")

    assert l2_vp_l2_peak > 0, (
        f"Level-2 rect not inked in Level-2 viewport (peak={l2_vp_l2_peak}). "
        f"Fill did not plot or level isolation failed to restore L2 for its viewport."
    )
    assert l1_vp_l2_peak == 0, (
        f"Level-1 rect appeared in Level-2 viewport (peak={l1_vp_l2_peak}). "
        f"Per-viewport isolation is broken: L1 items visible in L2 viewport."
    )

    # On-screen scene state restored to Level 1 (the pre-render active level).
    assert ms.active_level == "Level 1"
    assert ms.active_view_key == "plan:Plan: Level 1"
