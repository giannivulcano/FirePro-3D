"""tests/test_align_extension_angled.py — BUG B: extension tracking at any angle.

Dwelling on the endpoint of an ANGLED line and tracking its extension (collinear
past the endpoint) must snap the cursor onto that extension ray, just as it does
for a horizontal/vertical source.  The user reports extension only works for
axis-aligned objects.

Root cause (see snap_engine._SnapCtx.check): the acquired point's H/V rays and
its extension ray are all ``align_path`` (equal picker priority), and the H/V
rays are always checked first.  Without a same-priority "closest wins" rule, a
closer extension foot could never displace a farther H/V foot once the H/V ray
was the incumbent — so extension tracking failed for every non-axis-aligned
source.  It appeared to "work" for H/V only because the H/V ray coincides with
the extension ray when the source is axis-aligned.

Ground truth (never a flag flip): the resolved point is collinear with the true
source direction (cross-product with the unit direction ≈ 0), NOT parked on the
endpoint's horizontal/vertical line.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.construction_geometry import LineItem


def _acquire_real_endpoint(scene, line_item, endpoint):
    """Snap *endpoint* of *line_item* through the real SNAP path, then dwell-acquire.

    Captures the direction from the real ``OsnapResult.source_item`` exactly as
    the interactive dwell feed does, so the extension ray is built from the true
    source geometry.
    """
    scene.get_effective_position(QPointF(endpoint[0], endpoint[1]))
    snap = scene._align_snap_dict(scene._snap_result)
    assert snap is not None and snap["snap_type"] == "endpoint"
    assert snap["direction"] is not None, "endpoint must capture a direction"
    scene._align_controller.on_move(endpoint, snap, elapsed_ms=500)
    return snap["direction"]


# Angles chosen to exercise the failure: axis-aligned pass even before the fix
# (H/V ray coincides with the extension); a symmetric 45° also happened to pass;
# shallow/steep angles are where the H/V ray masks the extension.
@pytest.mark.parametrize("angle_deg", [0.0, 20.0, 45.0, 70.0, 90.0, 135.0])
def test_extension_snaps_at_any_angle(shown_model_view, angle_deg):
    view, scene = shown_model_view
    scene.set_mode("draw_gridline")
    assert scene._align_active_item is not None

    # Line from origin at the given angle (scene Y grows downward — the sign is
    # irrelevant to the collinearity assertion).
    rad = math.radians(angle_deg)
    ep = (300.0 * math.cos(rad), 300.0 * math.sin(rad))
    line = LineItem(QPointF(0.0, 0.0), QPointF(ep[0], ep[1]))
    scene.addItem(line)

    u = _acquire_real_endpoint(scene, line, ep)

    # A cursor ~100 units past the endpoint along the extension, offset ~8 units
    # perpendicular (well inside the align aperture of the extension ray, and in
    # the shallow-angle cases also inside the H/V ray's aperture — which is
    # exactly the masking condition).
    beyond = (ep[0] + u[0] * 100.0, ep[1] + u[1] * 100.0)
    off = (beyond[0] - u[1] * 8.0, beyond[1] + u[0] * 8.0)

    p = scene.get_effective_position(QPointF(off[0], off[1]))

    # Ground truth: the resolved point lies on the true extension line through
    # the endpoint (collinear with the captured direction), not on the endpoint's
    # H or V line.  cross((p - endpoint), u) ≈ 0.
    cross = (p.x() - ep[0]) * u[1] - (p.y() - ep[1]) * u[0]
    assert abs(cross) < 1e-3, (
        f"{angle_deg}°: resolved point {p.x():.2f},{p.y():.2f} is not collinear "
        f"with the source extension (cross-error {cross:.3f})")
