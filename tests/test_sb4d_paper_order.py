"""SB4d guard 3: a sheet viewport plots through scene.render, so the
annotation band orders paper exactly as the screen -- a red tag block over a
20 m wall reads red on both (D5; precedent: pipe labels on paper)."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.paper_display import (PaperColorMode, apply_paper_overrides,
                                     restore_model_display, save_paper_color_mode)
from tests._sb4d_helpers import dispose, is_red, plan_scene, tag_def, wall

RECT = QRectF(3000.0, -1000.0, 2000.0, 2000.0)      # 10 mm per px; (4000, 0) -> px (100, 100)


def _pixel(ms):
    img = QImage(200, 200, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 200, 200), RECT, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return QColor(img.pixel(100, 100))


def test_guard3_paper_render_keeps_the_screen_order(qapp):
    save_paper_color_mode(PaperColorMode.FULL_COLOR)        # authored colours on paper (isolated settings)
    ms, sec, det, tabs = plan_scene()
    try:
        tall = wall(ms, top_offset=20000.0)                 # z 200.3
        inst = ms.place_block_instance(tag_def(ms).id, (4000.0, 0.0))
        ms._level_manager.apply_to_scene(ms)
        assert inst.zValue() > tall.zValue()
        assert is_red(_pixel(ms)), "screen: the wall paints over the tag"
        saved = apply_paper_overrides(ms, RECT, 0.01)
        try:
            assert is_red(_pixel(ms)), "paper: the wall plots over the tag"
        finally:
            restore_model_display(saved)
    finally:
        dispose(ms, sec, tabs)
