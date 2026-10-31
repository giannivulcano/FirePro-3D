"""Floor void rendering: plan see-through + hit-test (A4 plan) and the 3D hole (A4 3D)."""
import math

import pytest
from PyQt6.QtCore import QPointF as P
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from firepro3d.floor_slab import FloorSlab
from firepro3d.floor_opening import FloorOpening


def _rect(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


def _add(scene, slab, *voids):
    scene.addItem(slab)
    scene._floor_slabs.append(slab)
    for pts in voids:
        op = FloorOpening(pts, host=slab)
        slab.add_opening(op)
        scene.addItem(op)
    return slab


def _pixel(view, scene_pt):
    """Colour of the shown viewport at *scene_pt* (device-pixel aware)."""
    QApplication.processEvents()
    img = view.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    vp = view.mapFromScene(scene_pt)
    return QColor(img.pixel(int(vp.x() * dpr), int(vp.y() * dpr)))


def test_plan_hole_shows_the_level_below(qapp, shown_model_view):
    view, scene = shown_model_view
    lower = FloorSlab(points=_rect(-1200, -1200, 1200, 1200), color="#3366cc")
    lower._top_mode = "absolute"
    lower._top_abs_z_mm = 0.0
    upper = FloorSlab(points=_rect(-1000, -1000, 1000, 1000), color="#cc3333")
    upper._top_mode = "absolute"
    upper._top_abs_z_mm = 5000.0
    _add(scene, lower)
    _add(scene, upper, _rect(-300, -300, 300, 300))
    scene._level_manager.apply_to_scene(scene, "Level 1",
                                        view_height=6000.0, view_depth=-1.0)
    # Preconditions: the upper slab masks what is under it and draws above it.
    assert upper._is_occluding and upper.zValue() > lower.zValue()
    in_hole = _pixel(view, P(0, 0))
    upper.setVisible(False)
    for op in upper.openings:
        op.setVisible(False)
    reference = _pixel(view, P(0, 0))           # the level below, no upper slab at all
    bg = view.viewport().palette().color(view.viewport().palette().ColorRole.Base)
    assert reference != bg                       # sanity: the lower slab tints the spot
    assert in_hole == reference                  # see-through: no mask, no upper fill


def test_click_in_hole_does_not_pick_the_slab(qapp, model_scene):
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)),
                _rect(1000, 1000, 2000, 2000))
    (op,) = slab.openings
    hits = scene.items(P(1500, 1500))
    assert slab not in hits and op in hits
    assert slab in scene.items(P(500, 500))     # material still picks the slab


def test_swallowed_slab_keeps_a_pickable_outline(qapp, model_scene):
    scene = model_scene()
    slab = _add(scene, FloorSlab(points=_rect(0, 0, 4000, 3000)),
                _rect(-100, -100, 4100, 3100))
    assert slab.cut_region() == []
    assert slab in scene.items(P(4000, 1500))   # on its boundary stroke
    assert slab not in scene.items(P(2000, 1500))
    assert slab.path().elementCount() == 5      # path() is still the full boundary


def test_void_outline_uses_its_display_colour(qapp, shown_model_view):
    view, scene = shown_model_view
    slab = _add(scene, FloorSlab(points=_rect(-1000, -1000, 1000, 1000)),
                _rect(-300, -300, 300, 300))
    slab._display_fill_color = ""               # no fill: only outlines paint
    (op,) = slab.openings
    op._display_color = "#00ff00"               # the Opening DM colour (PART B sets it)
    QApplication.processEvents()
    img = view.viewport().grab().toImage()
    dpr = img.devicePixelRatio()
    vp = view.mapFromScene(P(0, -300))          # midpoint of the void's top edge
    greens = []
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            c = QColor(img.pixel(int((vp.x() + dx) * dpr), int((vp.y() + dy) * dpr)))
            greens.append(c.green() > 180 and c.red() < 90 and c.blue() < 90)
    assert any(greens)
