"""tests/test_align_perpendicular.py — Perpendicular tracking (spec: 4th
per-direction toggle).

When the first placement point lands on an angled directional object's endpoint,
the auto-acquired active anchor inherits that object's direction. In addition to
the collinear Extension ray, ALIGN now emits a PERPENDICULAR ray (object dir
rotated 90°) through that endpoint — so the user can draw ACROSS the object.

Mirrors test_align_anchor_extension.py: drives the real click entry point
(posted QMouseEvent on a shown view) and asserts GROUND TRUTH collinearity of the
resolved point with the perpendicular line, never "a ray exists".
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
def test_perpendicular_ray_snaps_across_endpoint(shown_model_view, angle_deg):
    """After the first click on an angled endpoint, a cursor placed near the
    PERPENDICULAR line through the endpoint soft-snaps ONTO that perpendicular
    line (object direction rotated 90°)."""
    view, scene = shown_model_view
    scene.set_mode("draw_line")

    rad = math.radians(angle_deg)
    ep = (300.0 * math.cos(rad), 300.0 * math.sin(rad))
    u = (math.cos(rad), math.sin(rad))              # source (line) direction
    perp = (-u[1], u[0])                            # rotated 90°
    line = LineItem(QPointF(0.0, 0.0), QPointF(ep[0], ep[1]))
    scene.addItem(line)

    _left_click(view, scene, QPointF(ep[0], ep[1]))
    assert scene._align_anchor_direction() is not None

    # A cursor ~100 units along the PERPENDICULAR through the endpoint, offset
    # ~8 units sideways (inside the perpendicular ray's aperture). The sideways
    # offset is along the source direction u (which is perpendicular to perp).
    across = (ep[0] + perp[0] * 100.0, ep[1] + perp[1] * 100.0)
    off = (across[0] + u[0] * 8.0, across[1] + u[1] * 8.0)
    p = scene.get_effective_position(QPointF(off[0], off[1]))

    # Ground truth: resolved point is collinear with the perpendicular direction
    # through the endpoint. cross((p - endpoint), perp) ≈ 0.
    cross = (p.x() - ep[0]) * perp[1] - (p.y() - ep[1]) * perp[0]
    assert abs(cross) < 1e-3, (
        f"{angle_deg}°: resolved {p.x():.2f},{p.y():.2f} not collinear with the "
        f"perpendicular through the endpoint (cross-error {cross:.3f})")
