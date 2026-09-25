"""Regression test for snap-engine roadmap item 5 (docs/specs/snapping-engine.md §12).

``nearest`` and ``perpendicular`` are independent toggles. ``nearest`` is the
cursor foot; ``perpendicular`` exists ONLY as PER-from a placement start point
(snap-polish smoke item 1) — with no start point there is no ⊥ candidate at
all. With a start point both are emitted: ⊥ at the foot FROM the start, nearest
at the cursor foot. (The original bug nested ``nearest`` under ``elif``,
silencing it whenever ``snap_perpendicular`` was on.)
"""

from __future__ import annotations

from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtWidgets import QGraphicsLineItem

from firepro3d.snap_engine import SnapEngine


def _make_engine(perp: bool, nearest: bool) -> SnapEngine:
    engine = SnapEngine()
    engine.snap_perpendicular = perp
    engine.snap_nearest = nearest
    return engine


def test_both_emitted_when_both_toggles_on(qapp):
    """With a start point: ⊥ at the foot FROM the start, nearest at the
    cursor foot — two independent candidates."""
    line = QGraphicsLineItem(QLineF(QPointF(0, 0), QPointF(100, 0)))
    engine = _make_engine(perp=True, nearest=True)

    results = engine._geometric_snaps(QPointF(50, 20), line, QPointF(30, 200))

    types = [t for t, _ in results]
    assert "perpendicular" in types
    assert "nearest" in types

    perp_pt = next(p for t, p in results if t == "perpendicular")
    near_pt = next(p for t, p in results if t == "nearest")
    assert (perp_pt.x(), perp_pt.y()) == (30.0, 0.0)     # foot from the start
    assert (near_pt.x(), near_pt.y()) == (50.0, 0.0)     # cursor foot


def test_no_start_point_emits_nearest_only(qapp):
    """No placement start point → no ⊥ at all; the cursor foot is nearest."""
    line = QGraphicsLineItem(QLineF(QPointF(0, 0), QPointF(100, 0)))
    engine = _make_engine(perp=True, nearest=True)
    types = [t for t, _ in engine._geometric_snaps(QPointF(50, 20), line)]
    assert types == ["nearest"]


def test_only_perpendicular_when_nearest_off(qapp):
    line = QGraphicsLineItem(QLineF(QPointF(0, 0), QPointF(100, 0)))
    engine = _make_engine(perp=True, nearest=False)
    types = [t for t, _ in engine._geometric_snaps(
        QPointF(50, 20), line, QPointF(30, 200))]
    assert "perpendicular" in types
    assert "nearest" not in types


def test_only_nearest_when_perpendicular_off(qapp):
    """Previously broken: nearest was unreachable under the elif."""
    line = QGraphicsLineItem(QLineF(QPointF(0, 0), QPointF(100, 0)))
    engine = _make_engine(perp=False, nearest=True)
    types = [t for t, _ in engine._geometric_snaps(
        QPointF(50, 20), line, QPointF(30, 200))]
    assert "nearest" in types
    assert "perpendicular" not in types
