"""Stroke corner joints (design docs/superpowers/specs/2026-11-03-stroke-corner-joins-design.md).

Qt cannot miter across two ``drawPath`` calls, so a corner shared by two
strokes (two items, or the two runs of the crisp axis split) is closed by
filling the OUTER wedge between their flat ends in the stroke's colour.
``joint_wedge`` is pure math; ``JointIndex`` pairs coincident ends inside one
container; ``joinable`` is the paint-time AC4 / AC6 match.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from .constants import STROKE_MITER_LIMIT

_EPS = 1e-9


def joint_wedge(corner: QPointF, d_a, d_b, half_w: float,
                limit: float = STROKE_MITER_LIMIT) -> QPolygonF | None:
    """The outer wedge closing the corner of two flat-ended strokes (D2).

    Qt semantics (P4 probe, 2026-11-03): a MiterJoin past its limit is not
    bevelled, it is *clipped*. Both outer edges, extended past the corner,
    are cut at ``limit * half_w`` from the corner's flat-end foot (Qt limit =
    ``limit / 2`` pen widths), joined by a chord. The wedge reproduces that
    so a patched joint is pixel-identical to an in-item vertex.

    Args:
        corner: The shared endpoint.
        d_a: Unit direction of stroke A *away* from the corner (dx, dy).
        d_b: Unit direction of stroke B away from the corner.
        half_w: Half the stroke width, in the frame of *corner*.
        limit: Miter limit as the PDF ratio (miter length / width).

    Returns:
        ``[corner, outer edge of A, miter tip, outer edge of B]``; past the
        limit ``[corner, outer edge of A, clip on A's edge, clip on B's edge,
        outer edge of B]``; None when the strokes are collinear (straight
        through: nothing to fill) or overlap (parallel / zero tangent).
    """
    ax, ay = d_a
    bx, by = d_b
    cross = ax * by - ay * bx
    if abs(cross) < _EPS or half_w <= 0.0:
        return None                      # straight through, reversed or degenerate
    dot = ax * bx + ay * by
    # Outer normals: perpendicular to each stroke, pointing away from the other.
    na = (-ay, ax) if (-ay * bx + ax * by) < 0.0 else (ay, -ax)
    nb = (-by, bx) if (-by * ax + bx * ay) < 0.0 else (by, -bx)
    cx, cy = corner.x(), corner.y()
    pa = QPointF(cx + na[0] * half_w, cy + na[1] * half_w)
    pb = QPointF(cx + nb[0] * half_w, cy + nb[1] * half_w)
    # Interior angle theta between the strokes: cos = dot. The miter tip lies
    # on each outer edge's extension at half_w / tan(theta / 2) past the
    # corner (and half_w / sin(theta / 2) from it along the exterior bisector).
    half = math.acos(max(-1.0, min(1.0, dot))) / 2.0
    s = math.sin(half)
    t = math.tan(half)
    if s < _EPS or t < _EPS or 1.0 / t > limit:
        cut = limit * half_w
        return QPolygonF([
            corner, pa,
            QPointF(pa.x() - ax * cut, pa.y() - ay * cut),
            QPointF(pb.x() - bx * cut, pb.y() - by * cut),
            pb,
        ])
    bx_, by_ = -(ax + bx), -(ay + by)
    n = math.hypot(bx_, by_)
    reach = half_w / s
    tip = QPointF(cx + bx_ / n * reach, cy + by_ / n * reach)
    return QPolygonF([corner, pa, tip, pb])
