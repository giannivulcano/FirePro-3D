"""tests/test_rect_center_hud.py — centre-mode rectangle HUD shows full W/H.

Bug (user, 2026-09-16): placing a rectangle from its centre, the Dynamic-Input
HUD reported the *half*-extent (centre→edge), not the full width/height.  The
rectangle (2D / wall / floor) now places base → side → depth; the centre
variant's ``rect_side_center`` / ``rect_depth_center`` schemas both carry FULL
extents.  (The 2-click ``rectangle_center`` schema this file first guarded was
retired with the sizing → rotate flow.)
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF

from firepro3d.dynamic_input import SCHEMAS


def test_draw_rectangle_center_mode_selects_center_schema(shown_model_view):
    _view, scene = shown_model_view
    scene.scene_role = "block_editor"   # containment C1: loose authoring here
    scene.set_mode("draw_rectangle")
    scene._draw_rect_from_center = True
    assert scene._rectangle_schema_for_step() is SCHEMAS["rect_side_center"]
    scene._draw_rect_side_pt = QPointF(10, 0)          # depth step
    assert scene._rectangle_schema_for_step() is SCHEMAS["rect_depth_center"]
    scene._draw_rect_from_center = False
    assert scene._rectangle_schema_for_step() is SCHEMAS["rect_depth"]
    scene._draw_rect_side_pt = None
    assert scene._rectangle_schema_for_step() is SCHEMAS["rect_side"]


def test_centre_side_hud_reads_full_width():
    """User bug (2026-09-16) carried to the 3-click flow: centre W is FULL."""
    vals = SCHEMAS["rect_side_center"].seed(QPointF(0, 0), QPointF(300, 0))
    assert vals["Length"] == 600.0
