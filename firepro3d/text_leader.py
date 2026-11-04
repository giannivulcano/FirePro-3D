"""Text leader geometry (design 2026-11-04-text-leader-annotations D3 / D4).

A leader is one open stroke attach -> knee -> tip. The attach-to-knee part
(the shoulder) leaves a box edge at a right angle. The record keeps the edge,
a 0-1 attach fraction and the shoulder length, so a box resize keeps the
leader on its edge; the tip is absolute in the surface frame (D7).

All functions work in one frame, the box frame, with *box* in mm.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QTransform

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


def _to_parent(item, p: QPointF) -> QPointF:
    """A box-frame point (mm) to the item's parent frame (rotation, scale, pos)."""
    s = item.scale() or 1.0
    return item.mapToParent(item._rotation_transform().map(QPointF(p.x() / s, p.y() / s)))


def _from_parent(item, p: QPointF) -> QPointF:
    """Inverse of :func:`_to_parent`: a parent-frame point to the box frame, mm."""
    s = item.scale() or 1.0
    inv, ok = item._rotation_transform().inverted()
    local = (inv if ok else QTransform()).map(item.mapFromParent(p))
    return QPointF(local.x() * s, local.y() * s)


def _box_mm(item) -> QRectF:
    """The item's box in the box frame (local frame scaled to mm)."""
    s = item.scale() or 1.0
    r = item._box_rect_local()
    return QRectF(r.left() * s, r.top() * s, r.width() * s, r.height() * s)


def box_frame_points(item) -> tuple | None:
    """``(attach, knee, tip)`` of *item*'s leader in the item's box frame, mm.

    The box frame is the unrotated local frame scaled to mm. The tip is mapped
    in from the surface (parent frame, where ``x`` / ``y`` live) through the
    item's own rotation, so a rotated box keeps its shoulder perpendicular and
    its tip on target.
    """
    rec = item.data.leader
    if not rec:
        return None
    a, k = attach_and_knee(_box_mm(item), rec)
    return a, k, _from_parent(item, QPointF(rec["tip_x"], rec["tip_y"]))


def style_record(rec: dict, colour: str) -> dict:
    """The stroke style of a leader: no start end, *rec*'s end on the tip."""
    from .stroke_style import NONE, default_style
    st = default_style(colour)
    st["start"] = {"end": NONE, "visible": True}
    st["finish"] = {"end": rec.get("end") or DEFAULT_END_ID, "visible": True}
    return st


def surface_stroke_op(item, t: QTransform):
    """The leader as one STROKE ``RenderOp`` through *t* (parent -> ops frame).

    Mirrors ``text_box_ops``: box-frame points go through rotation, scale and
    pos, then *t*. The tip is the stored absolute point mapped by *t* alone, so
    it is exact.
    """
    pts = box_frame_points(item)
    if pts is None:
        return None
    from PyQt6.QtGui import QPainterPath, QPen
    from .path_walk import Seg
    from .render_op import STROKE, RenderOp
    d = item.data
    a = t.map(_to_parent(item, pts[0]))
    k = t.map(_to_parent(item, pts[1]))
    tip = t.map(QPointF(d.leader["tip_x"], d.leader["tip_y"]))
    path = QPainterPath(a)
    path.lineTo(k)
    path.lineTo(tip)
    st = style_record(d.leader, d.color)
    return RenderOp(STROKE, path, pen=QPen(), weight=d.leader.get("weight") or d.border_weight,
                    colour=d.color,
                    pieces=(Seg(a.x(), a.y(), k.x(), k.y()), Seg(k.x(), k.y(), tip.x(), tip.y())),
                    linetype=st["linetype"], origin=QPointF(0.0, 0.0),
                    ends=(st["start"], st["finish"]))


def panel_rows(rec: dict | None, registry, exclude=(), fallback_weight: str = "") -> dict:
    """Leader rows: the toggle, plus End and Weight while on (design D6).

    Args:
        rec: The stored leader record, or None when off.
        registry: Project block registry the End picker resolves through.
        exclude: Block ids the End picker leaves out.
        fallback_weight: The weight a leader with no weight of its own draws
            at (the frame's), shown as the Weight row's value.
    """
    rows = {"Leader": {"type": "bool", "value": bool(rec)}}
    if not rec:
        return rows
    from .capabilities import end_choices
    from .paper_display import picker_weight_name, weight_names
    choices = end_choices(registry, exclude)
    value = next((n for n, r in choices if r == rec["end"]), None)
    rows["Leader End"] = {"type": "enum", "options": [n for n, _ in choices],
                          "value": value or (choices[0][0] if choices else "")}
    shown = rec["weight"] or fallback_weight
    rows["Leader Weight"] = {"type": "enum", "options": weight_names(),
                             "value": picker_weight_name(shown) if shown
                             else weight_names()[0]}
    return rows


def set_panel_row(rec: dict, key: str, value, registry, exclude=()) -> None:
    """Apply a Leader End / Leader Weight commit to *rec*."""
    if key == "Leader End":
        from .capabilities import end_choices
        ref = next((r for n, r in end_choices(registry, exclude) if n == value), None)
        if ref is not None:
            rec["end"] = ref
    elif key == "Leader Weight":
        rec["weight"] = str(value)
