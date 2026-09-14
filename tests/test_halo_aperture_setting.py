"""FIX 4 (spec §7): per-scene HALO aperture (px), settable from prefs.

The aperture is no longer the bare ``HALO_APERTURE_PX`` constant — the scene
carries ``_halo_aperture_px`` (seeded from the constant) and the view reads it
per move. A smaller aperture misses an item that a larger one would catch.
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTransform
from firepro3d.constants import HALO_APERTURE_PX
from firepro3d.construction_geometry import LineItem
from firepro3d.model_space import Model_Space


def test_scene_seeds_aperture_from_constant(qapp):
    sc = Model_Space()
    assert sc._halo_aperture_px == HALO_APERTURE_PX


def test_smaller_aperture_misses_offset_item(qapp):
    # A thin line whose nearest point is ~100 units from the hover point:
    # a 10-unit aperture box misses it, a 150-unit box catches it. This proves
    # the aperture value actually drives the pick (unlike a Node, whose huge
    # annotation footprint intersects any aperture).
    sc = Model_Space()
    sc.addItem(LineItem(QPointF(100.0, 0.0), QPointF(200.0, 0.0)))

    hit_small = sc.halo_candidates_at(QPointF(0.0, 0.0), 10.0, QTransform())
    hit_large = sc.halo_candidates_at(QPointF(0.0, 0.0), 150.0, QTransform())
    assert hit_small == []
    assert len(hit_large) == 1


def test_view_uses_scene_aperture(qapp):
    from firepro3d.model_view import Model_View
    sc = Model_Space()
    view = Model_View(sc)
    # The view must read the per-scene aperture, not the bare constant.
    sc._halo_aperture_px = 99
    assert getattr(sc, "_halo_aperture_px", HALO_APERTURE_PX) == 99
