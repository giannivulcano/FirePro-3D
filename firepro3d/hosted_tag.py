"""Placed-tag frame maths (SB6 placed tags, design
docs/superpowers/specs/2026-11-15-sb6-placed-tags-design.md D1-D6, D9, D10).

A placed tag is a ``BlockInstance`` whose ``_host_uid`` names a wall or a wall
opening and whose ``tag`` record is::

    {"offset": [u_mm, v_mm], "orientation": "horizontal" | "aligned",
     "leader": None | {"edge", "t", "shoulder_mm", "tip": [u_mm, v_mm],
                       "end", "weight"},
     "block": <id> | None}

``u`` runs along the host direction, ``v`` along ``WallSegment.normal()``,
both mm from the host anchor (D2). The leader is a Note leader
(``text_leader``, D9): ``edge`` / ``t`` / ``shoulder_mm`` seat the shoulder on
the tag box in the tag's box frame (printed mm); ``tip`` is a host-frame
point like ``offset``, so the tip follows the host; ``end`` / ``weight`` are
the tag's own Leader End / Leader Weight rows (D10, ``""`` = the Notes
fallback weight). The plan pose is derived from the record;
nothing here writes the scene (``resolve`` drops a stale swap from the record
it is handed, D6).

Frames: scene units are mm x ppm, Qt Y-down. ``centerline_angle_rad`` is a
scene-frame angle; a ``BlockInstance`` rotation is Y-up CCW degrees, so the
aligned rotation is ``-degrees(angle)`` (``WallSegment.grip_render_angle``).
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF

from . import text_leader as _tl
from .constants import TAG_ORIENT_ALIGNED, TAG_ORIENT_HORIZONTAL

ORIENTATIONS = (TAG_ORIENT_HORIZONTAL, TAG_ORIENT_ALIGNED)


def new_record(offset=(0.0, 0.0), orientation: str = TAG_ORIENT_HORIZONTAL,
               leader: bool = False) -> dict:
    """A fresh tag record (D1).

    Args:
        offset: ``(u, v)`` in mm from the host anchor.
        orientation: ``"horizontal"`` or ``"aligned"``.
        leader: True gives the default leader (:func:`new_leader`, R5).

    Returns:
        The record; no block swap.
    """
    return {"offset": [float(offset[0]), float(offset[1])],
            "orientation": orientation if orientation in ORIENTATIONS else TAG_ORIENT_HORIZONTAL,
            "leader": new_leader() if leader else None,
            "block": None}


def new_leader(text_rec: dict | None = None) -> dict:
    """A tag leader record (D9) from a ``text_leader`` record (default:
    ``text_leader.default_leader``): its edge, fraction, shoulder, End and
    weight, with the tip at the host anchor (``[0, 0]``) instead of the
    text leader's surface-absolute ``tip_x`` / ``tip_y``."""
    rec = text_rec if text_rec is not None else _tl.default_leader(QRectF(), QPointF())
    out = {k: v for k, v in rec.items() if k not in ("tip_x", "tip_y")}
    out["tip"] = [0.0, 0.0]
    return out


def _pair(value):
    """``[a, b]`` floats from a stored pair, or None when malformed / not finite."""
    try:
        a, b = float(value[0]), float(value[1])
    except (TypeError, ValueError, IndexError, KeyError):
        return None
    return [a, b] if math.isfinite(a) and math.isfinite(b) else None


def normalise(rec) -> dict | None:
    """A clean copy of a stored tag record, or None when it has no usable
    offset (a corrupt file never raises in a rebuild; the block then loads as
    an ordinary bound block). A bad orientation reads Horizontal, a leader
    that cannot draw (``text_leader.normalise``) none, a bad tip the host
    anchor, a bad swap no swap."""
    if not isinstance(rec, dict):
        return None
    off = _pair(rec.get("offset"))
    if off is None:
        return None
    orient = rec.get("orientation")
    if orient not in ORIENTATIONS:
        orient = TAG_ORIENT_HORIZONTAL
    leader = _normalise_leader(rec.get("leader"))
    block = rec.get("block")
    return {"offset": off, "orientation": orient, "leader": leader,
            "block": block if isinstance(block, str) and block else None}


def _normalise_leader(rec) -> dict | None:
    """A clean tag leader record, or None (see :func:`normalise`)."""
    if not isinstance(rec, dict):
        return None
    clean = _tl.normalise(dict(rec, tip_x=0.0, tip_y=0.0))
    if clean is None:
        return None
    out = new_leader(clean)
    out["tip"] = _pair(rec.get("tip")) or [0.0, 0.0]
    return out


def anchor(host):
    """``(scene point, scene angle rad)`` of *host*'s tag anchor (R3), or None.

    Wall: the true centreline midpoint and its angle. Wall opening (door /
    window / opening): ``center_on_wall()`` and its wall's angle; None while
    the opening has no wall.
    """
    from .wall_opening import WallOpening
    if isinstance(host, WallOpening):
        w = host.wall
        if w is None:
            return None
        return QPointF(host.center_on_wall()), w.centerline_angle_rad()
    mid = getattr(host, "centerline_midpoint", None)
    if mid is None:
        return None
    return QPointF(mid()), host.centerline_angle_rad()


def scene_point(host, uv, ppm: float):
    """Scene point of host-frame ``(u, v)`` mm, or None without an anchor."""
    a = anchor(host)
    if a is None:
        return None
    p, ang = a
    c, s = math.cos(ang), math.sin(ang)
    u, v = float(uv[0]), float(uv[1])
    return QPointF(p.x() + (u * c - v * s) * ppm, p.y() + (u * s + v * c) * ppm)


def offset_from_scene(host, ppm: float, scene_pt):
    """Host-frame ``[u, v]`` mm of *scene_pt* (the inverse of
    :func:`scene_point`; placement, drag and the knee grip), or None."""
    a = anchor(host)
    if a is None or ppm <= 0.0:
        return None
    p, ang = a
    c, s = math.cos(ang), math.sin(ang)
    dx, dy = (scene_pt.x() - p.x()) / ppm, (scene_pt.y() - p.y()) / ppm
    return [dx * c + dy * s, -dx * s + dy * c]


def rotation(rec: dict, host) -> float:
    """The tag's Y-up rotation (D5): 0 for Horizontal, the host angle for Aligned."""
    if rec.get("orientation") != TAG_ORIENT_ALIGNED:
        return 0.0
    a = anchor(host)
    return -math.degrees(a[1]) if a is not None else 0.0


def pose(rec: dict, host, ppm: float):
    """``(x, y, rotation)`` of a tag (D2 / D5), or None without an anchor."""
    pt = scene_point(host, rec["offset"], ppm)
    if pt is None:
        return None
    return pt.x(), pt.y(), rotation(rec, host)


def tip_scene(rec: dict, host, ppm: float):
    """The leader tip in the scene (stored in the host frame, D9), or None
    without a leader or an anchor."""
    leader = rec.get("leader")
    if not leader:
        return None
    return scene_point(host, leader["tip"], ppm)


def resolve(rec: dict, host, scene):
    """The block id a tag on *host* draws (D6 / D11 / R8).

    The swapped ``block`` while it is an eligible tag of *host*'s category
    (``bound_label.eligible_definition``); otherwise the swap is dropped from
    *rec* and the category's project default resolves
    (``scene.annotation_block``). None when nothing resolves (the four tag
    categories always resolve through ``SYSTEM_DEFAULTS`` when the System
    tier is present).
    """
    from . import element_params
    from .bound_label import eligible_definition
    cat = element_params.category_of(host)
    if not cat:
        return None
    swap = rec.get("block")
    if swap:
        d = scene.get_block_definition(swap)
        if d is not None and eligible_definition(d, cat):
            return swap
        rec["block"] = None
    fn = getattr(scene, "annotation_block", None)
    d = fn(cat) if callable(fn) else None
    return d.id if d is not None else None


def moves_with_host(host) -> bool:
    """True when *host* moves in the same gesture as a tag being moved: it is
    selected, or it is an opening whose wall is (D4: the host's re-pose then
    puts the tag back where the move left it, so its offset must not change)."""
    if host.isSelected():
        return True
    w = getattr(host, "wall", None)
    return w is not None and w.isSelected()


def leader_op(pts, end: str, weight: str):
    """The leader as one open STROKE ``RenderOp`` through *pts* (op frame:
    attach, knee, tip): no start end, *end* on the last point (the tip),
    named *weight* (``""`` = the Notes fallback, ``text_item.
    default_border_weight``), Automatic colour -- the op shape
    ``text_leader.surface_stroke_op`` builds for a text leader inside a
    block."""
    from PyQt6.QtGui import QPainterPath, QPen
    from .constants import TOKEN_AUTO
    from .path_walk import Seg
    from .render_op import STROKE, RenderOp
    from .text_leader import style_record
    path = QPainterPath(pts[0])
    for p in pts[1:]:
        path.lineTo(p)
    from .text_item import default_border_weight
    weight = weight or default_border_weight()
    st = style_record({"end": end}, TOKEN_AUTO)
    pieces = tuple(Seg(a.x(), a.y(), b.x(), b.y()) for a, b in zip(pts, pts[1:]))
    return RenderOp(STROKE, path, pen=QPen(), weight=weight, colour=TOKEN_AUTO,
                    pieces=pieces, linetype=st["linetype"], origin=QPointF(0.0, 0.0),
                    ends=(st["start"], st["finish"]))
