"""tests/test_align_anchor_extension.py — spec D3: the AUTO-ACQUIRED active anchor
inherits its object's DIRECTION when the first point lands on a directional object.

When the user STARTS a placement (line/wall/gridline) by snapping the FIRST point
onto an existing directional object's endpoint, the auto-acquired active anchor
should inherit that object's direction and project an Extension ray along its
angle — so the user can extend end-to-end at the existing angle (continue a wall
collinearly).

Today ``_align_anchor_direction()`` returns None (H/V only). These tests drive the
real click entry point (posted QMouseEvent on a shown view) and assert GROUND TRUTH
collinearity of the resulting extension, never "a result exists".
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from firepro3d.construction_geometry import LineItem


def _left_click(view, scene, scene_pt: QPointF) -> None:
    """Post a real LEFT press at *scene_pt* on the shown *view*."""
    vp = view.mapFromScene(scene_pt).toPointF()
    ev = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        vp,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mousePressEvent(ev)


@pytest.mark.parametrize("angle_deg", [20.0, 45.0, 70.0])
def test_anchor_inherits_endpoint_direction(shown_model_view, angle_deg):
    """First click on an angled line's endpoint arms an anchor whose direction is
    the line's unit direction."""
    view, scene = shown_model_view
    scene.set_mode("draw_line")

    rad = math.radians(angle_deg)
    ep = (300.0 * math.cos(rad), 300.0 * math.sin(rad))
    u = (math.cos(rad), math.sin(rad))
    line = LineItem(QPointF(0.0, 0.0), QPointF(ep[0], ep[1]))
    scene.addItem(line)

    _left_click(view, scene, QPointF(ep[0], ep[1]))

    d = scene._align_anchor_direction()
    assert d is not None, "anchor must inherit the endpoint's object direction"
    # Unit direction, up to sign (the extension ray is bidirectional).
    dot = abs(d[0] * u[0] + d[1] * u[1])
    assert dot == pytest.approx(1.0, abs=1e-3), (
        f"{angle_deg}°: anchor dir {d} not collinear with source {u}")


@pytest.mark.parametrize("angle_deg", [20.0, 45.0, 70.0])
def test_extension_ray_snaps_beyond_endpoint(shown_model_view, angle_deg):
    """After the first click on an angled endpoint, the cursor beyond the endpoint
    along the collinear extension soft-snaps ONTO that extension line (not the
    anchor's H/V line)."""
    view, scene = shown_model_view
    scene.set_mode("draw_line")

    rad = math.radians(angle_deg)
    ep = (300.0 * math.cos(rad), 300.0 * math.sin(rad))
    u = (math.cos(rad), math.sin(rad))
    line = LineItem(QPointF(0.0, 0.0), QPointF(ep[0], ep[1]))
    scene.addItem(line)

    _left_click(view, scene, QPointF(ep[0], ep[1]))
    assert scene._align_anchor_direction() is not None

    # A cursor ~100 units past the endpoint along the extension, offset ~8 units
    # perpendicular (inside the extension ray's aperture).
    beyond = (ep[0] + u[0] * 100.0, ep[1] + u[1] * 100.0)
    off = (beyond[0] - u[1] * 8.0, beyond[1] + u[0] * 8.0)
    p = scene.get_effective_position(QPointF(off[0], off[1]))

    # Ground truth: resolved point is collinear with the source direction through
    # the endpoint (anchor). cross((p - endpoint), u) ≈ 0.
    cross = (p.x() - ep[0]) * u[1] - (p.y() - ep[1]) * u[0]
    assert abs(cross) < 1e-3, (
        f"{angle_deg}°: resolved {p.x():.2f},{p.y():.2f} not collinear with the "
        f"anchor's inherited extension (cross-error {cross:.3f})")


def test_empty_space_anchor_has_no_direction(shown_model_view):
    """Starting the first point in EMPTY space → no inherited direction (H/V only,
    no phantom extension)."""
    view, scene = shown_model_view
    scene.set_mode("draw_line")

    # Far from any geometry (scene is empty here).
    _left_click(view, scene, QPointF(500.0, 500.0))

    assert scene._align_anchor_direction() is None
