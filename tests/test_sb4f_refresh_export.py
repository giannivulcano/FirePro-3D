"""SB4f AC1 / AC3: a registry or mapping change reaches the live sheet through
the real widget wiring; sheet export paints or hides the title."""
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.level_manager import PlanViewManager
from firepro3d.paper_export import render_sheet
from firepro3d.paper_space import (PaperSpaceWidget, SheetViewData, ViewResolver,
                                   sheet_page_mm)
from tests._sb4d_helpers import add_sheet, dispose, head_def, plan_scene
from tests._sb4f_helpers import BOX

X, Y, W, H = BOX


def _resolver(ms, sec, det):
    pvm = PlanViewManager()
    pvm.create("Level 1", ms._level_manager)
    return ViewResolver(ms, pvm, det, sec, level_manager=ms._level_manager)


def test_model_refresh_reaches_the_live_sheet(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    w = None
    try:
        sheet = add_sheet(ms, "FP-1.0")
        sheet.sheet_views.append(
            SheetViewData("plan", "Plan: Level 1", "T", 0.0, *BOX))
        w = PaperSpaceWidget(sheet, _resolver(ms, sec, det))
        vp = w.paper_scene.get_viewports()[0]
        assert vp._placeholder is False
        lab = vp._title_label
        lab.boundingRect()
        assert lab._line[0] == pytest.approx(3.0, abs=0.05)    # the seed
        head_def(ms, "View Title", shape="square")             # half side 4
        ms.refresh_annotation_tags()
        lab.boundingRect()
        assert lab._line[0] == pytest.approx(4.0, abs=0.05)
    finally:
        if w is not None:
            w.deleteLater()
        dispose(ms, sec, tabs)


def _ink_below_box(sheet, resolver) -> int:
    """Dark pixels in the strip under the box of a sheet rendered through the
    real export path (``render_sheet``, the PDF / print painter path)."""
    pw, ph = sheet_page_mm(sheet)
    px = 6
    img = QImage(int(pw * px), int(ph * px), QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    render_sheet(sheet, resolver, p, QRectF(0, 0, img.width(), img.height()))
    p.end()
    x0, x1 = int(X * px), int((X + W) * px)
    y0, y1 = int((Y + H + 0.6) * px), int((Y + H + 8.5) * px)
    return sum(1 for y in range(y0, y1) for x in range(x0, x1)
               if QColor(img.pixel(x, y)).lightness() < 128)


def test_export_paints_the_title_and_hidden_paints_nothing(qapp, real_system_library):
    """AC3: shown puts title ink under the box; hidden is the control and puts
    none, with the same sheet, box and resolver otherwise."""
    ms, sec, det, tabs = plan_scene()
    try:
        sheet = add_sheet(ms, "FP-1.0")
        data = SheetViewData("plan", "Plan: Level 1", "T", 0.0, *BOX, show_title=False)
        sheet.sheet_views.append(data)
        resolver = _resolver(ms, sec, det)
        hidden = _ink_below_box(sheet, resolver)
        data.show_title = True
        shown = _ink_below_box(sheet, resolver)
        assert hidden == 0
        assert shown > 20          # a title line plus text, not stray antialiasing
    finally:
        dispose(ms, sec, tabs)
