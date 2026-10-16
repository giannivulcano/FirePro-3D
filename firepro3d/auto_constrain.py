"""Auto Constrain -- snap -> handle resolution and join planning
(parametric-constraint-system.md §13; design AC1 AD1-AD10).

Pure: reads primitive adapters (``sketch_adapters``) and ``OsnapResult``
fields, never writes the scene. ``ConstraintController.auto_join`` performs
the only write; ``GeometryDrawingController`` captures and plans.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QPointF

from .constants import AUTO_CONSTRAIN_MATCH_TOL_MM
from .sketch_adapters import adapter_for
from .sketch_solver import curve_radius

POINT_SNAPS = frozenset({"endpoint", "midpoint", "center"})   # AD6 -> a point handle
EDGE_SNAPS = frozenset({"nearest", "perpendicular"})          # AD6 -> an edge, else a curve


def seg_dist(p, a, b) -> float:
    """Distance from *p* to segment *ab* (any one unit, QPointF-like)."""
    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p.x() - ax) * dx + (p.y() - ay) * dy) / L2))
    return math.hypot(p.x() - ax - t * dx, p.y() - ay - t * dy)


def item_handles(it, *, curvy: bool = True):
    """Yield one item's ``(kind, ref, a, b)`` handles in scene space.

    point ``(p, None | "mid")`` (``"mid"`` = an edge midpoint, D58), edge
    ``(a, b)``, curve ``(centre, (r, item))`` -- only when *curvy*. Hidden
    handles (text ``ins``, polygon ``radius``, ellipse ``rx`` / ``ry``) never.
    The one enumeration shared by pick mode (``PickState._candidates``) and
    the Auto Constrain resolver.
    """
    uid = getattr(it, "_uid", None)
    ad = adapter_for(it)
    if uid is None or ad is None:
        return
    x = np.array(ad.read(it), dtype=float)
    mids = ad.mid_names(it)
    hidden = ad.hidden_names(it)
    for name, e in ad.points(it, 0).items():
        if name in hidden:                    # CS3c: legacy text ins
            continue
        yield ("point", {"uid": uid, "h": name}, QPointF(*e.eval(x)[0]),
               "mid" if name in mids else None)
    for name, (a, b) in ad.edges(it, 0).items():
        yield ("edge", {"uid": uid, "h": name},
               QPointF(*a.eval(x)[0]), QPointF(*b.eval(x)[0]))
    if curvy:
        for name, cv in ad.curves(it, 0).items():
            if name in hidden:                # CS5 D79: defining circles
                continue
            yield ("curve", {"uid": uid, "h": name},
                   QPointF(*cv.center.eval(x)[0]), (curve_radius(cv, x), it))
