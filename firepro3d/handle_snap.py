"""Handle snap (S2): while a selection moves, its own snap points (endpoints,
midpoints, centres, quadrants, text-box points) snap to other geometry.

Targets are collected ONCE per gesture — the moving items are excluded and
nothing else changes during a drag — culled to the view's visible rect, into a
px-cell grid; each mouse move then tests every handle against its neighbouring
cells (O(handles)). Underlay geometry is queried per handle through each
group's spatial index. The model scene is NoIndex, so a per-handle
``SnapEngine.find()`` (≈40–140 ms at 2k–8k items) is not viable.
Governing spec: selection-manipulator.md §Move.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsItemGroup

from . import snap_engine as _se
from .constants import HANDLE_SNAP_MAX_HANDLES
from .pipe import Pipe
from .snap_engine import OsnapResult, SNAP_PRIORITY
from .underlay_snap_index import UnderlaySnapIndex

HANDLE_TYPES = frozenset({"endpoint", "midpoint", "center", "quadrant"})
_UNDERLAY_TAGS = ("DXF Underlay", "PDF Underlay")


def _tag(item) -> object:
    # Unbound call: TextItem shadows QGraphicsItem.data with its
    # TextAnnotationData property, so item.data(0) would raise.
    return QGraphicsItem.data(item, 0)


class HandleSnapSession:
    """One move gesture's handle-snap state.

    Args:
        engine: The scene's ``SnapEngine`` (toggles + collectors).
        scene: The model scene.
        view: The view the drag happens in (zoom + visible rect).
        moving: Items being moved (excluded as targets, sources of handles).
        anchor: Scene point the handle offsets are measured from (the grab
            point / Move base point / dragged grip's rest position).
    """

    def __init__(self, engine, scene, view, moving, anchor: QPointF):
        self._engine = engine
        self._scale = _se._safe_scale(view.transform().m11())
        self._moving = set(moving)
        # Handles: offsets from the anchor, deduped; endpoints first (stable
        # sort by snap priority) so the cap keeps the strongest handles.
        seen: set[tuple[float, float]] = set()
        raw: list[tuple[int, QPointF]] = []
        for it in moving:
            for kind, p, _n in engine._collect(it):
                key = (round(p.x(), 6), round(p.y(), 6))
                if kind in HANDLE_TYPES and key not in seen:
                    seen.add(key)
                    raw.append((SNAP_PRIORITY.get(kind, 99),
                                QPointF(p.x() - anchor.x(), p.y() - anchor.y())))
        raw.sort(key=lambda t: t[0])
        self._handles = [h for _p, h in raw[:HANDLE_SNAP_MAX_HANDLES]]
        # Targets: named points of non-moving items in the visible rect.
        self._cell = _se.px_to_scene(float(_se.SNAP_TOLERANCE_PX), self._scale)
        self._grid: dict[tuple[int, int], list[tuple[str, QPointF, object]]] = {}
        self._underlays: list[QGraphicsItemGroup] = []
        if not self._handles:
            return
        # Walk scene.items() WITHOUT a rect: the scene is NoIndex, and a rect
        # query calls every item's (Python) boundingRect/shape — ~110 ms at 8k
        # items vs <1 ms unfiltered. Points are culled to the visible rect
        # (padded by one aperture) instead.
        c = self._cell or 1.0
        vis = view.mapToScene(view.viewport().rect()).boundingRect().adjusted(
            -c, -c, c, c)
        x0, y0, x1, y1 = vis.left(), vis.top(), vis.right(), vis.bottom()
        grid = self._grid
        floor = math.floor
        for item in scene.items():
            parent = item.parentItem()
            if parent is not None and _tag(parent) in _UNDERLAY_TAGS:
                continue            # indexed underlay children: via the group
            if isinstance(item, QGraphicsItemGroup) and _tag(item) in _UNDERLAY_TAGS:
                if (isinstance(QGraphicsItem.data(item, 4), UnderlaySnapIndex)
                        and item.isVisible()
                        and item.sceneBoundingRect().intersects(vis)):
                    self._underlays.append(item)
                continue
            if not item.isVisible() or self._is_moving(item):
                continue
            if item.zValue() > 150 or _tag(item) == "origin":
                continue
            if engine.skip_pipes and isinstance(item, Pipe):
                continue
            for kind, p, _n in engine._collect(item):
                px, py = p.x(), p.y()
                if (kind in HANDLE_TYPES
                        and x0 <= px <= x1 and y0 <= py <= y1):
                    # Inlined _key (hot loop: every visible target point).
                    grid.setdefault((floor(px / c), floor(py / c)), []).append(
                        (kind, p, item))

    def _is_moving(self, item) -> bool:
        p = item
        while p is not None:
            if p in self._moving:
                return True
            p = p.parentItem()
        return False

    def _key(self, p: QPointF) -> tuple[int, int]:
        c = self._cell or 1.0
        return (math.floor(p.x() / c), math.floor(p.y() / c))

    def best(self, anchor_now: QPointF):
        """Best handle-to-target hit for the anchor at *anchor_now*.

        Returns:
            ``(corrected_anchor, OsnapResult)`` — the anchor position that puts
            the winning handle exactly on its target, and the target as a snap
            result (for the marker) — or None when no handle is within the
            aperture of a target.
        """
        if not self._handles:
            return None
        aperture = float(_se.SNAP_TOLERANCE_PX)
        band = float(_se.SNAP_PRIORITY_BAND_PX)
        best = None   # (d_px, prio, handle, kind, target, src)
        ax, ay = anchor_now.x(), anchor_now.y()
        for h in self._handles:
            q = QPointF(ax + h.x(), ay + h.y())
            kx, ky = self._key(q)
            cands = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cands.extend(self._grid.get((kx + dx, ky + dy), ()))
            if self._underlays:
                cands.extend(self._underlay_targets(q))
            for kind, p, src in cands:
                d_px = math.hypot(p.x() - q.x(), p.y() - q.y()) * self._scale
                if d_px > aperture:
                    continue
                prio = SNAP_PRIORITY.get(kind, 99)
                if best is None or _se._band_beats(d_px, prio, best[0], best[1], band):
                    best = (d_px, prio, h, kind, p, src)
        if best is None:
            return None
        _d, _pr, h, kind, p, src = best
        corrected = QPointF(p.x() - h.x(), p.y() - h.y())
        return corrected, OsnapResult(point=QPointF(p), snap_type=kind,
                                      source_item=src)

    def _underlay_targets(self, q: QPointF):
        out = []
        r = self._cell
        rect = QRectF(q.x() - r, q.y() - r, 2 * r, 2 * r)
        for group in self._underlays:
            xf = group.sceneTransform()
            inv, ok = xf.inverted()
            if not ok:
                continue
            lr = inv.mapRect(rect)
            bounds = (lr.x(), lr.y(), lr.x() + lr.width(), lr.y() + lr.height())
            index = QGraphicsItem.data(group, 4)
            for g in index.query(lr.x(), lr.y(), lr.width(), lr.height()):
                for kind, p, _n in self._engine._collect_from_geom(g, xf, bounds):
                    if kind in HANDLE_TYPES:
                        out.append((kind, p, group))
        return out
