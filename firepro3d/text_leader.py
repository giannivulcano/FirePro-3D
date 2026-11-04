"""Text leader geometry (design 2026-11-04-text-leader-annotations D3 / D4).

A leader is one open stroke attach -> knee -> tip. The attach-to-knee part
(the shoulder) leaves a box edge at a right angle. The record keeps the edge,
a 0-1 attach fraction and the shoulder length, so a box resize keeps the
leader on its edge; the tip is absolute in the surface frame (D7).

All functions work in one frame, the box frame, with *box* in mm.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF

from .constants import (TEXT_LEADER_DEFAULT_SHOULDER_MM, TEXT_LEADER_DEFAULT_TIP_MM,
                        TEXT_LEADER_END_ID, TEXT_LEADER_MIN_SHOULDER_MM)

DEFAULT_END_ID = TEXT_LEADER_END_ID
_EDGES = ("L", "R", "T", "B")


def attach_and_knee(box: QRectF, rec: dict) -> tuple[QPointF, QPointF]:
    """The attach point and knee of *rec* on *box*."""
    e, t, s = rec["edge"], float(rec["t"]), float(rec["shoulder_mm"])
    if e in ("L", "R"):
        y = box.top() + t * box.height()
        x = box.left() if e == "L" else box.right()
        return QPointF(x, y), QPointF(x - s if e == "L" else x + s, y)
    x = box.left() + t * box.width()
    y = box.top() if e == "T" else box.bottom()
    return QPointF(x, y), QPointF(x, y - s if e == "T" else y + s)


def _outside(box: QRectF, p: QPointF) -> dict:
    return {"L": box.left() - p.x(), "R": p.x() - box.right(),
            "T": box.top() - p.y(), "B": p.y() - box.bottom()}


def solve_knee(box: QRectF, drag: QPointF, rec: dict) -> dict:
    """The edge, fraction and shoulder for a knee dragged to *drag* (D4).

    The edge the point is furthest outside of wins, a tie keeps the current
    edge. The along-edge coordinate clamps to the edge. A point inside the box
    lands on the nearest edge at the minimum shoulder.
    """
    out = _outside(box, drag)
    best = max(out.values())
    if best <= 0.0:
        edge = max(out, key=out.get)          # least far inside = nearest edge
        shoulder = TEXT_LEADER_MIN_SHOULDER_MM
    else:
        cur = rec.get("edge")
        edge = cur if out.get(cur, -1.0) == best else max(out, key=out.get)
        shoulder = max(best, TEXT_LEADER_MIN_SHOULDER_MM)
    if edge in ("L", "R"):
        span, pos = box.height(), drag.y() - box.top()
    else:
        span, pos = box.width(), drag.x() - box.left()
    t = 0.5 if span <= 0.0 else max(0.0, min(1.0, pos / span))
    return {"edge": edge, "t": t, "shoulder_mm": shoulder}


def default_leader(box: QRectF, to_surface: QPointF) -> dict:
    """A new leader, right edge at mid-height. *to_surface* maps box frame to
    the surface frame by plain addition (the box origin there)."""
    rec = {"edge": "R", "t": 0.5, "shoulder_mm": TEXT_LEADER_DEFAULT_SHOULDER_MM}
    _a, k = attach_and_knee(box, rec)
    d = TEXT_LEADER_DEFAULT_TIP_MM
    rec.update(tip_x=k.x() + d + to_surface.x(), tip_y=k.y() + d + to_surface.y(),
               end=DEFAULT_END_ID, weight="")
    return rec


def normalise(rec) -> dict | None:
    """A clean copy of a stored record, or None when it cannot draw."""
    if not isinstance(rec, dict) or rec.get("edge") not in _EDGES:
        return None
    try:
        return {"edge": rec["edge"],
                "t": max(0.0, min(1.0, float(rec.get("t", 0.5)))),
                "shoulder_mm": max(TEXT_LEADER_MIN_SHOULDER_MM,
                                   float(rec.get("shoulder_mm", 0.0))),
                "tip_x": float(rec["tip_x"]), "tip_y": float(rec["tip_y"]),
                "end": str(rec.get("end") or DEFAULT_END_ID),
                "weight": str(rec.get("weight") or "")}
    except (KeyError, TypeError, ValueError):
        return None
