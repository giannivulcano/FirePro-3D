"""HALO ranks like SNAP: px distance to the drawn trace, Z only inside the band.

Repro of the 2026-09-24 screenshot: a tiny circle at an arc's end stole the
HALO while the cursor sat on the arc (old rank: Z, then distance to the
bounding-box CENTRE — the circle's centre is near, the arc's is far).
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsView

from firepro3d import halo_selection as hs
from firepro3d.geometry_2d import LineItem, CircleItem
from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space


def _pick(sc, cursor_scene, zoom):
    # A real view attached at the target zoom so IntersectsItemShape hit
    # widths (scene_hit_width) and ItemIgnoresTransformations bubbles resolve
    # exactly as they do in the running app (headless-safe: never shown).
    view = QGraphicsView(sc)
    view.setTransform(QTransform.fromScale(zoom, zoom))
    dt = view.viewportTransform()
    a_scene = hs.HALO_APERTURE_PX / zoom
    return sc.halo_candidates_at(cursor_scene, a_scene, dt)


@pytest.mark.parametrize("zoom", [2.0, 40.0])
def test_long_line_beats_small_circle_when_cursor_is_on_the_line(qapp, zoom):
    sc = Model_Space()
    ln = LineItem(QPointF(0, -1000), QPointF(0, 0))
    sc.addItem(ln)
    r_px = 12.0                                   # circle radius on screen
    circ = CircleItem(QPointF(0, (r_px + 2) / zoom), r_px / zoom)
    sc.addItem(circ)
    # Cursor ON the line, 10 px above its end (>= 10 px from the circle stroke).
    cursor = QPointF(0, -10.0 / zoom)
    got = _pick(sc, cursor, zoom)
    assert got and got[0] is ln


def test_higher_z_wins_inside_the_band(qapp):
    sc = Model_Space()
    near = LineItem(QPointF(-100, 0), QPointF(100, 0)); near.setZValue(1)
    high = LineItem(QPointF(-100, 8), QPointF(100, 8)); high.setZValue(5)
    sc.addItem(near); sc.addItem(high)
    got = _pick(sc, QPointF(0, 0), 1.0)          # near: 0 px, high: 8 px (< 12 band)
    assert got[0] is high


def test_closer_wins_outside_the_band(qapp):
    hs.HALO_PRIORITY_BAND_PX = 4
    sc = Model_Space()
    near = LineItem(QPointF(-100, 0), QPointF(100, 0)); near.setZValue(1)
    high = LineItem(QPointF(-100, 8), QPointF(100, 8)); high.setZValue(5)
    sc.addItem(near); sc.addItem(high)
    got = _pick(sc, QPointF(0, 0), 1.0)          # 8 px > 4 band -> distance decides
    assert got[0] is near


def test_aperture_is_judged_in_pixels(qapp):
    sc = Model_Space()
    ln = LineItem(QPointF(-100, 20), QPointF(100, 20))
    sc.addItem(ln)
    assert _pick(sc, QPointF(0, 0), 1.0) == []   # 20 px > 15 px aperture
    hs.HALO_APERTURE_PX = 25
    assert _pick(sc, QPointF(0, 0), 1.0) == [ln]


def test_gridline_bubble_hover_resolves_to_gridline(qapp):
    """Hovering a GridlineItem's bubble CENTRE must still resolve/rank the
    gridline first (bubble is a filled HALO_AREA child that resolves to its
    GridlineItem parent — same _halo_resolve path as a sprinkler->Node)."""
    sc = Model_Space()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 500), "A")
    sc.addItem(gl)
    view = QGraphicsView(sc)
    view.setTransform(QTransform.fromScale(1.0, 1.0))
    dt = view.viewportTransform()
    cursor = gl.bubble1.scenePos()
    got = sc.halo_candidates_at(cursor, hs.HALO_APERTURE_PX / 1.0, dt)
    assert got and got[0] is gl
