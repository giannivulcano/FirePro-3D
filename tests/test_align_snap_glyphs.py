"""Smoke item 3 guard — ALIGN snaps paint the regular snap glyphs.

Pixel-sampled from the real ``Model_View`` paint (grab of the viewport):
  * align_path on a ``perpendicular`` ray → the ⊥ glyph (magenta);
  * align_path on any other ray (hv / extension / parallel) → the nearest
    glyph (white cross);
  * align_intersection → the intersection X glyph (yellow).
"""
import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from firepro3d.geometry_2d import LineItem
from firepro3d.snap_engine import SNAP_COLORS
from tests._snap_polish_helpers import click, close_view, dwell, make_view, move


def _count_colour(view, scene_pt, hexcol, half=9):
    """Pixels of exactly *hexcol* in a (2*half+1)² box around *scene_pt*."""
    img = view.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    vp = view.viewportTransform().map(scene_pt)
    want = QColor(hexcol).rgb()
    cx, cy = int(round(vp.x() * dpr)), int(round(vp.y() * dpr))
    h = int(math.ceil(half * dpr))
    n = 0
    for x in range(cx - h, cx + h + 1):
        for y in range(cy - h, cy + h + 1):
            if 0 <= x < img.width() and 0 <= y < img.height() and img.pixel(x, y) == want:
                n += 1
    return n


def test_align_path_on_perpendicular_ray_paints_perpendicular_glyph(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(-1000, 300), QPointF(1000, -300)))
        click(view, QPointF(-400, 120))               # arm ON the line
        s = scene._mode_placement_anchor()
        n = math.hypot(2000, -600)
        u = (2000 / n, -600 / n)
        perp = (-u[1], u[0])
        cur = QPointF(s.x() + 800 * perp[0] + 10 * u[0], s.y() + 800 * perp[1] + 10 * u[1])
        move(view, cur)
        res = scene._align_result
        assert res is not None and res.snap_type == "align_path"
        assert _count_colour(view, res.point, SNAP_COLORS["perpendicular"]) >= 10
    finally:
        close_view(view, scene)


def test_align_path_on_hv_ray_paints_nearest_glyph(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(-2000, 0), QPointF(0, 0)))
        dwell(view, QPointF(0, 0))
        move(view, QPointF(800, 10))
        res = scene._align_result
        assert res is not None and res.snap_type == "align_path"
        assert _count_colour(view, res.point, SNAP_COLORS["nearest"]) >= 10
    finally:
        close_view(view, scene)


def test_align_intersection_paints_intersection_glyph(qapp):
    view, scene = make_view(mode="draw_line")
    try:
        scene.addItem(LineItem(QPointF(-2000, 0), QPointF(0, 0)))
        scene.addItem(LineItem(QPointF(1000, 2000), QPointF(1000, 1000)))
        dwell(view, QPointF(0, 0))
        dwell(view, QPointF(1000, 1000))
        move(view, QPointF(1012, 12))
        res = scene._align_result
        assert res is not None and res.snap_type == "align_intersection"
        assert _count_colour(view, res.point, SNAP_COLORS["intersection"]) >= 10
    finally:
        close_view(view, scene)
