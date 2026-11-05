"""Real-object builders shared by the SB4f guards (design
docs/superpowers/specs/2026-11-04-sb4f-view-title-design.md)."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter

from tests._sb4d_helpers import add_sheet, paper_view

BOX = (30.0, 30.0, 100.0, 80.0)      # x, y, w, h on the sheet, mm


def place(ms, sec, det, kind="plan", number="FP-1.0", **fields):
    """``(view, paper_scene, viewport)``: one real viewport on a new sheet.

    *kind* "plan": NTS (scale 0), so the box keeps BOX and carries the
    "scale" capability. *kind* "detail": a 10000 x 8000 detail at 0.01, so the
    live crop derives the same box, with no "scale" capability."""
    from firepro3d.paper_space import SheetViewData
    sheet = add_sheet(ms, number)
    view, ps = paper_view(ms, sec, det, sheet)
    if kind == "detail":
        det.create_detail("Detail 1", QRectF(0.0, 0.0, 10000.0, 8000.0))
        data = SheetViewData("detail", "Detail 1", "LEVEL ONE", 0.01, *BOX, **fields)
    else:
        data = SheetViewData("plan", "Plan: Level 1", "LEVEL ONE", 0.0, *BOX, **fields)
    vp = ps.add_viewport(data)
    assert vp._placeholder is False
    return view, ps, vp


def dark_px(scene, rect: QRectF, px: int = 6) -> int:
    """Pixels darker than mid-grey in *rect* (scene mm) of *scene*, rendered at
    *px* pixels per mm on white."""
    w, h = max(1, int(rect.width() * px)), max(1, int(rect.height() * px))
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return sum(1 for y in range(h) for x in range(w)
               if QColor(img.pixel(x, y)).lightness() < 128)
