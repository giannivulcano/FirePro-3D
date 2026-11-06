"""Paper polish AC4: the view title's stroke is a true 0.30 mm at every zoom and
in the sheet render, measured as ink across the bubble's left edge."""
from dataclasses import replace

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.level_manager import PlanViewManager
from firepro3d.paper_export import render_sheet
from firepro3d.paper_space import ViewResolver, sheet_page_mm
from tests._sb4d_helpers import dispose, plan_scene
from tests._sb4f_helpers import BOX, place

X, Y, W, H = BOX
# Bubble centre = the title's default spot (X + 4, Y + H + 4.5), radius 3 (block
# ops, P4 probe): the row through the centre crosses the stroke at x = 31.
SCAN = QRectF(X, Y + H + 4.0, 2.0, 1.0)


@pytest.fixture
def rig(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    yield ms, sec, det
    dispose(ms, sec, tabs)


def _row(paint, px: float) -> list:
    w, h = int(SCAN.width() * px), int(SCAN.height() * px)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    paint(p, QRectF(0, 0, w, h))
    p.end()
    return [QColor(img.pixel(x, y)).lightness() for y in range(h) for x in range(w)]


def _scene_paint(ps):
    def paint(p, target):
        ps.render(p, target, SCAN)
    return paint


def _ink_mm(paint, px: float, dark: int) -> float:
    # Averaged over every row of the scan (mm of stroke per row), not one sample:
    # a 0.9 px stroke on a flattened curve depends on where one row lands. The
    # bubble's curvature across SCAN's 1 mm height adds about 1% (0.3 / cos of a
    # small angle).
    rows = int(SCAN.height() * px)
    return sum((255 - v) / (255 - dark) for v in _row(paint, px)) / px / rows


# At 3 px/mm a cosmetic 1 px stroke (0.333 mm) also lands inside the 10% bar, so
# 3.0 pins the result and cannot go RED; 12 and 48 are what go RED without the hooks.
@pytest.mark.parametrize("px", [3.0, 12.0, 48.0])
def test_bubble_stroke_is_true_mm_at_every_zoom(rig, px):
    view, ps, vp = place(*rig)
    dark = min(_row(_scene_paint(ps), 96.0))
    assert dark < 60
    assert _ink_mm(_scene_paint(ps), px, dark) == pytest.approx(0.30, rel=0.10)


def test_bubble_stroke_is_true_mm_in_a_300_dpi_sheet_render(rig):
    ms, sec, det = rig
    view, ps, vp = place(ms, sec, det)
    dark = min(_row(_scene_paint(ps), 96.0))
    pvm = PlanViewManager()
    pvm.create("Level 1", ms._level_manager)
    resolver = ViewResolver(ms, pvm, det, sec, level_manager=ms._level_manager)
    px = 300.0 / 25.4

    def paint(p, target):
        page_w, page_h = sheet_page_mm(ps.sheet)
        p.translate(-SCAN.x() * px, -SCAN.y() * px)
        render_sheet(ps.sheet, resolver, p, QRectF(0, 0, page_w * px, page_h * px))
    assert _ink_mm(paint, px, dark) == pytest.approx(0.30, rel=0.10)


def test_a_named_weight_stroke_keeps_its_own_mm(rig, monkeypatch):
    """Heavy = 0.35 mm (paper_display's factory table), past the 10% bar from 0.30."""
    view, ps, vp = place(*rig)
    lab = vp._title_label
    d = lab.definition()
    dark = min(_row(_scene_paint(ps), 96.0))
    orig = d.render_ops_variant

    def heavy(*a, **k):
        return [replace(o, weight="Heavy") if o.kind == "stroke" else o
                for o in orig(*a, **k)]
    monkeypatch.setattr(d, "render_ops_variant", heavy)
    lab.refresh()
    assert _ink_mm(_scene_paint(ps), 48.0, dark) == pytest.approx(0.35, rel=0.05)
