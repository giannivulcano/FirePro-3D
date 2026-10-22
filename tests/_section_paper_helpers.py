"""Shared PDF helpers for section / elevation sheet-viewport guards.

Real export through ``paper_export.export_pdf`` (transient PaperScene ->
apply_paper_overrides -> render -> restore); the resolver returns
``(scene, crop)`` so any QGraphicsScene (plan or SectionScene) plots through
the real sheet-viewport path. Idioms from tests/test_lt1_block_paper.py.
"""
from unittest.mock import MagicMock

import fitz
from PyQt6.QtCore import QPointF, QRectF

VP_X, VP_Y, VP_W = 65.0, 30.0, 80.0      # A4, one 80 mm-square viewport
PT = 25.4 / 72.0                          # PDF points -> mm


def crop_at(centre: QPointF, scale: float) -> QRectF:
    half = VP_W / 2.0 / scale
    return QRectF(centre.x() - half, centre.y() - half, 2 * half, 2 * half)


def export_scene(tmp_path, scene, scale, centre, name):
    """Export one sheet whose single viewport shows *scene* at *scale*,
    cropped to an 80 mm / scale square centred on scene point *centre*."""
    from firepro3d import paper_export
    from firepro3d.paper_space import Sheet, SheetViewData, ViewResolver
    sheet = Sheet.create_default()
    sheet.paper_size = "A4"
    sheet.sheet_views = [SheetViewData("plan", "Plan: Level 1", "P", scale,
                                       VP_X, VP_Y, VP_W, VP_W)]
    resolver = MagicMock(spec=ViewResolver)
    crop = crop_at(centre, scale)
    resolver.resolve.side_effect = lambda vt, vn: (scene, QRectF(crop))
    out = tmp_path / name
    paper_export.export_pdf([sheet], resolver, str(out), dpi=300)
    return out


def to_paper(pt: QPointF, centre: QPointF, scale: float) -> tuple[float, float]:
    """Paper mm of scene point *pt* in the viewport centred on *centre*."""
    cx, cy = VP_X + VP_W / 2.0, VP_Y + VP_W / 2.0
    return (cx + (pt.x() - centre.x()) * scale, cy + (pt.y() - centre.y()) * scale)


def drawings(pdf):
    """Every PDF drawing as a dict with mm geometry:
    ``{"rect": (x0, y0, x1, y1), "type", "width", "color", "fill",
    "fill_opacity", "dashes"}``."""
    doc = fitz.open(str(pdf))
    try:
        res = []
        for d in doc[0].get_drawings():
            r = d["rect"]
            res.append({
                "rect": tuple(v * PT for v in (r.x0, r.y0, r.x1, r.y1)),
                "type": d.get("type") or "",
                "width": (d.get("width") or 0.0) * PT,
                "color": d.get("color"),
                "fill": d.get("fill"),
                "fill_opacity": d.get("fill_opacity"),
                "dashes": d.get("dashes"),
            })
        return res
    finally:
        doc.close()


def strokes_near(pdf, rect_mm, tol=0.5):
    """Stroked drawings whose rect matches *rect_mm* (x0, y0, x1, y1) within
    *tol* mm on every edge (selected by geometry only, never by width)."""
    out = []
    for d in drawings(pdf):
        if "s" not in d["type"]:
            continue
        if all(abs(a - b) <= tol for a, b in zip(d["rect"], rect_mm)):
            out.append(d)
    return out
