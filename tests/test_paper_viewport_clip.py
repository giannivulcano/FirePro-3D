"""Concern-1 crop clip: a section-cut wall's solid fill must not bleed past the
viewport crop box. REAL WallSegment, pixel assertion, red-verified.

Root cause (fixed): draw_section_hatch used setClipPath(ReplaceClip), discarding
the paper viewport's fitted clip, so a section-cut wall straddling the crop edge
painted its solid section fill outside the box. Fix = IntersectClip.
"""
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QImage, QPainter, QColor
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.model_space import Model_Space
from tests._paper_iso_helpers import make_wall, _DetailMgrStub


def _left_bleed_pixels(vp, data, margin=40):
    """Render the viewport with a margin; count non-white pixels LEFT of the box."""
    img = QImage(int(data.w + 2 * margin), int(data.h + 2 * margin + 20),
                 QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.translate(margin, margin)
    vp.paint(p, None, None)
    p.end()
    white = QColor("white").rgb()
    return sum(img.pixel(x, y) != white
               for x in range(0, margin - 1) for y in range(img.height()))


def test_section_cut_wall_fill_does_not_bleed_past_crop(qapp):
    ms = Model_Space()
    lm = LevelManager(); pvm = PlanViewManager(); pvm.create("Level 1", lm)
    # Wall straddles the crop's left edge (x<0 is OUTSIDE crop 0..1000).
    w = make_wall(ms, (-4000, 500), (600, 500), "Level 1")
    w._display_section_color = "#808080"     # solid gray section fill
    ms.active_level = "Level 1"; ms.active_view_key = "plan:Plan: Level 1"
    lm.apply_to_scene(ms, "Level 1")
    # Real plan/detail views section-cut walls at the cut plane. apply_to_scene
    # resets the flag, so set it after (the no-op skip preserves it because the
    # viewport level matches the on-screen level).
    w._is_section_cut = True

    resolver = ViewResolver(ms, pvm, _DetailMgrStub(), None, level_manager=lm)
    sheet = Sheet.create_default()
    data = SheetViewData("plan", "Plan: Level 1", "P", 0.05, 40, 40, 0, 0)
    paper = PaperScene(sheet, resolver)
    vp = paper.add_viewport(data)
    data.crop_rect = QRectF(0, 0, 1000, 1000)
    vp._recompute_size_from_scale()

    assert w._is_section_cut is True          # guard: the section path is exercised
    bleed = _left_bleed_pixels(vp, data)
    assert bleed == 0, f"section-cut wall fill bled {bleed}px past the crop box"
