"""Regression: the picker's priority-override band must not collapse at low
snap tolerance.

The picker (`_SnapCtx.check`) lets a higher-priority snap win over a closer
lower-priority one when both fall within a "priority band". Historically that
band was ``tolerance * 0.3``, so it shrank with the user's tolerance setting.
At a small tolerance (e.g. 5 px) the band collapsed to ~1.5 units, and an
``intersection`` (priority 0) near a crossing would lose to the *closer*
``perpendicular`` / ``nearest`` foot on one of the crossing lines — the user
sees "intersection snap is broken" at low tolerance even though the candidate
is emitted.

See docs/specs/snapping-engine.md §6.1 (and Pain #2, "tolerance sweet-spot").

The fix bases the band on a fixed pixel constant (capped at the tolerance), so
it stays usable at any tolerance. At the default 40 px tolerance the band is
unchanged (12 px), so this test also pins that default.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsScene

from firepro3d import snap_engine
from firepro3d.construction_geometry import LineItem
from firepro3d.snap_engine import SnapEngine


def _scene() -> QGraphicsScene:
    s = QGraphicsScene()
    s._walls = []
    s._gridlines = []
    return s


@pytest.fixture
def crossing_scene(qapp) -> QGraphicsScene:
    """Horizontal + vertical line crossing at (100, 0).

    The crossing is *not* a midpoint or endpoint of either line, and no other
    snap target sits near it, so only intersection / perpendicular / nearest
    compete for a cursor placed near the crossing.
    """
    s = _scene()
    h = LineItem(QPointF(0, 0), QPointF(300, 0))        # midpoint (150, 0)
    s.addItem(h)
    v = QGraphicsLineItem(QLineF(QPointF(100, -50),     # midpoint (100, 50)
                                 QPointF(100, 150)))
    s.addItem(v)
    return s


@pytest.mark.parametrize("tol_px", [5, 10, 20, 40])
def test_intersection_wins_at_all_tolerances(crossing_scene, monkeypatch,
                                             tol_px):
    """Cursor offset *along* the horizontal line near the crossing must still
    resolve to the intersection, regardless of the configured tolerance.

    Cursor (104, 1): the perpendicular/nearest foot on the horizontal line is
    (104, 0) at distance 1 — closer than the intersection at (100, 0),
    d ~= 4.12. Before the fix, tol_px in {5, 10} pick perpendicular; after the
    fix the intersection (priority 0) wins at every tolerance.
    """
    monkeypatch.setattr(snap_engine, "SNAP_TOLERANCE_PX", tol_px)
    eng = SnapEngine()  # all snaps on, including nearest + perpendicular
    result = eng.find(QPointF(104, 1), crossing_scene, QTransform())

    assert result is not None, f"tol={tol_px}px: expected a snap, got None"
    assert result.snap_type == "intersection", (
        f"tol={tol_px}px: expected intersection, got {result.snap_type} "
        f"at ({result.point.x():.1f}, {result.point.y():.1f})"
    )
    assert abs(result.point.x() - 100.0) < 1.0
    assert abs(result.point.y() - 0.0) < 1.0
