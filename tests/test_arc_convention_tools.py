"""DD9 arc-convention guards (scene-tools P1 batch, Slice 1).

Every arc-aware tool must read/write arc angles in the ArcItem convention
(Y-up CCW, ``arc_math.yup_angle`` / ``point_at``). Ground truth is the PAINTED
geometry — the arc's own ``path()`` sampled and mapped to the scene — compared
against points defined independently here by their *visual* angle (screen up
= scene -y). Real path: a shown Model_View over a real
``Model_Space(scene_role="block_editor")``, the tool entered with ``set_mode``,
real posted clicks (and a real Return for Fillet).
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest

from firepro3d import geometry_intersect as gi
from firepro3d.geometry_2d import ArcItem, CircleItem, LineItem, PolylineItem
from tests._snap_polish_helpers import click, close_view, make_view

R = 100.0
TOL = 0.05     # mm


def _vis(deg: float, r: float = R, cx: float = 0.0, cy: float = 0.0) -> QPointF:
    """Scene point at VISUAL angle *deg* (0 = right, 90 = screen-up)."""
    a = math.radians(deg)
    return QPointF(cx + r * math.cos(a), cy - r * math.sin(a))


def _painted(item, t: float) -> QPointF:
    """Scene point at fraction *t* along the item's painted path."""
    return item.mapToScene(item.path().pointAtPercent(t))


def _near(p: QPointF, q, tol: float = TOL) -> bool:
    qx, qy = (q.x(), q.y()) if isinstance(q, QPointF) else q
    return math.hypot(p.x() - qx, p.y() - qy) <= tol


def _covers(item, q, tol: float = 0.5) -> bool:
    """Whether the painted path passes within *tol* mm of point *q*."""
    qx, qy = (q.x(), q.y()) if isinstance(q, QPointF) else q
    return min(math.hypot(s.x() - qx, s.y() - qy)
               for s in (_painted(item, i / 720.0) for i in range(721))) <= tol


def _ends_match(item, a, b, tol: float = TOL) -> bool:
    s, e = _painted(item, 0.0), _painted(item, 1.0)
    return ((_near(s, a, tol) and _near(e, b, tol))
            or (_near(s, b, tol) and _near(e, a, tol)))


def _add(scene, item, attr):
    scene.addItem(item)
    getattr(scene, attr).append(item)
    return item


def _baseline(scene):
    scene.push_undo_state()
    return scene._undo_pos


# ── Line x arc intersection (Trim's only arc path) ──────────────────────────

def test_line_arc_intersection_lies_on_the_painted_arc(qapp):
    arc = ArcItem(QPointF(0, 0), R, 0.0, 180.0)    # painted on the visual top
    pts = gi.line_arc_intersections(QPointF(50, -200), QPointF(50, 200),
                                    arc._center, arc._radius,
                                    arc._start_deg, arc._span_deg)
    assert len(pts) == 1
    assert _near(pts[0], (50.0, -86.6025), 1e-3)                        # [RED]
    assert _covers(arc, pts[0])                    # ...on the PAINTED arc
