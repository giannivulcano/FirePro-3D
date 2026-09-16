"""tests/test_rect_center_hud.py — centre-mode rectangle HUD shows full W/H.

Bug (user, 2026-09-16): placing a rectangle from its centre, the Dynamic-Input
HUD reported the *half*-extent (centre→edge), not the full width/height.  The
fix routes centre-mode rectangles through a dedicated ``rectangle_center`` schema
whose fields are the full width and height.

The pure seed/resolve functions are the observable ground truth of "the readout
shows the full width" (seed) and "a typed full width builds that rectangle"
(resolve → rect_sizing_points).
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF

from firepro3d.dynamic_input import (
    SCHEMAS,
    resolve_rectangle_center,
    seed_rectangle_center,
)
from firepro3d.geometry_2d import rect_sizing_points


def test_seed_reports_full_width_and_height():
    # Cursor 300 right / 200 up (scene Y-down) of the centre → full 600 x 400.
    vals = seed_rectangle_center(QPointF(0, 0), QPointF(300, 200))
    assert vals == {"W": 600.0, "H": 400.0}


def test_seed_is_quadrant_agnostic():
    # A down-left drag reports the same magnitudes (centre mode is symmetric).
    assert seed_rectangle_center(QPointF(0, 0), QPointF(-300, -200)) == {"W": 600.0, "H": 400.0}


def test_resolve_builds_full_size_rectangle():
    corner = resolve_rectangle_center(QPointF(0, 0), {"W": 600.0, "H": 400.0})
    pt1, pt2 = rect_sizing_points(QPointF(0, 0), corner, from_center=True)
    assert abs((pt2.x() - pt1.x()) - 600.0) < 1e-9
    assert abs((pt2.y() - pt1.y()) - 400.0) < 1e-9


def test_seed_resolve_round_trip_preserves_the_cursor_rectangle():
    centre, cursor = QPointF(50, -20), QPointF(350, 180)
    vals = seed_rectangle_center(centre, cursor)
    corner = resolve_rectangle_center(centre, vals)
    pt1, pt2 = rect_sizing_points(centre, corner, from_center=True)
    # Same rectangle the raw cursor would have produced.
    e1, e2 = rect_sizing_points(centre, cursor, from_center=True)
    assert abs(pt1.x() - e1.x()) < 1e-9 and abs(pt1.y() - e1.y()) < 1e-9
    assert abs(pt2.x() - e2.x()) < 1e-9 and abs(pt2.y() - e2.y()) < 1e-9


def test_center_schema_has_full_width_height_fields():
    schema = SCHEMAS["rectangle_center"]
    assert [f.name for f in schema.fields] == ["W", "H"]


def test_draw_rectangle_center_mode_selects_center_schema(shown_model_view):
    _view, scene = shown_model_view
    scene.set_mode("draw_rectangle")
    scene._draw_rect_from_center = True
    assert scene._rectangle_schema_for_step() is SCHEMAS["rectangle_center"]
    scene._draw_rect_from_center = False
    assert scene._rectangle_schema_for_step() is SCHEMAS["rectangle"]
