"""Handle snap (S2): while a selection moves, its own snap points (endpoints,
midpoints, centres, quadrants, text-box points) snap to other geometry.

The handles (the moving items' own snap points, as offsets from the gesture
anchor) are captured ONCE, at rest. The targets — every other item's snap
points, culled to the view's visible rect — are collected once per gesture into
a px-cell grid (the Move tool re-collects them after a zoom/pan between its
clicks, see :meth:`HandleSnapSession.sync_view`); each mouse move then tests
every handle against its neighbouring cells (O(handles)). Underlay geometry is
queried per handle through each group's spatial index. The model scene is
NoIndex, so a per-handle ``SnapEngine.find()`` (≈40–140 ms at 2k–8k items) is
not viable. Governing spec: selection-manipulator.md §Move.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsItemGroup

from . import snap_engine as _se
from .constants import HANDLE_SNAP_MAX_HANDLES
from .pipe import Pipe
from .snap_engine import OsnapResult, SNAP_PRIORITY
from .underlay_snap_index import UnderlaySnapIndex

HANDLE_TYPES = frozenset({"endpoint", "midpoint", "center", "quadrant"})
_UNDERLAY_TAGS = ("DXF Underlay", "PDF Underlay")
# A target within this scene distance of a handle's OWN rest point is that
# handle's current position (a connected line, a wall join, …) — snapping to it
# would pin the handle at rest, so no move shorter than the aperture could land.
_SELF_REST_EPS = 1e-6


class HandleSnapResult(OsnapResult):
    """An ``OsnapResult`` published by a handle snap (marker only).

    Distinct type so the scene's cursor picker never feeds it back as its
    hysteresis ``held`` result: it is a handle's target, not a cursor snap.
    """


def _tag(item) -> object:
    """The item's ``data(0)`` type tag.

    Args:
        item: Any scene item.

    Returns:
        The tag (e.g. ``"DXF Underlay"``, ``"origin"``) or None. Unbound call:
        TextItem shadows ``QGraphicsItem.data`` with its TextAnnotationData
        property, so ``item.data(0)`` would raise.
    """
    return QGraphicsItem.data(item, 0)


def _is_underlay_group(item) -> bool:
    """Whether *item* is a tagged DXF/PDF underlay group."""
    return isinstance(item, QGraphicsItemGroup) and _tag(item) in _UNDERLAY_TAGS


class HandleSnapSession:
    """One move gesture's handle-snap state.

    Args:
        engine: The scene's ``SnapEngine`` (toggles + collectors).
        scene: The model scene.
        view: The view the drag happens in (zoom + visible rect).
        moving: Items being moved (excluded as targets, sources of handles).
            Must be at rest (no preview transform) when the session is built.
        anchor: Scene point the handle offsets are measured from (the grab
            point / Move base point / dragged grip's rest position).
    """

    def __init__(self, engine, scene, view, moving, anchor: QPointF):
        self._engine = engine
        self._scene = scene
        self._moving = set(moving)
        self._anchor0 = QPointF(anchor)
        self._handles = self._build_handles(engine, moving, anchor)
        self._grid: dict[tuple[int, int], list[tuple[str, QPointF, object, object]]] = {}
        self._underlays: list[QGraphicsItemGroup] = []
        self._scale = 1.0
        self._cell = 1.0
        self._view_key = None
        self._build_targets(view)

    # ── build ──────────────────────────────────────────────────────────────

    @staticmethod
    def _build_handles(engine, moving, anchor: QPointF) -> list[QPointF]:
        """The moving items' own snap points as offsets from *anchor*.

        Deduped and capped at ``HANDLE_SNAP_MAX_HANDLES``. Centre points (a
        block's insertion point, a circle's centre) are kept first so a large
        block's many vertices never crowd its insertion point out; the rest
        follow by snap priority (endpoints before midpoints …).
        """
        seen: set[tuple[float, float]] = set()
        raw: list[tuple[tuple[int, int], QPointF]] = []
        for it in moving:
            for kind, p, _n in engine._collect(it):
                key = (round(p.x(), 6), round(p.y(), 6))
                if kind in HANDLE_TYPES and key not in seen:
                    seen.add(key)
                    rank = (0 if kind == "center" else 1,
                            SNAP_PRIORITY.get(kind, 6))
                    raw.append((rank, QPointF(p.x() - anchor.x(),
                                              p.y() - anchor.y())))
        raw.sort(key=lambda t: t[0])
        return [h for _r, h in raw[:HANDLE_SNAP_MAX_HANDLES]]

    @staticmethod
    def _view_state(view) -> tuple:
        """Hashable (transform, visible rect) key of *view*."""
        t = view.transform()
        r = view.mapToScene(view.viewport().rect()).boundingRect()
        return (t.m11(), t.m12(), t.m21(), t.m22(),
                round(r.x(), 6), round(r.y(), 6),
                round(r.width(), 6), round(r.height(), 6))

    def sync_view(self, view) -> None:
        """Re-collect the targets if *view*'s zoom/pan changed since the build.

        Only valid while the moving items are at rest (the Move tool, whose
        preview is a ghost); the handles are never rebuilt.
        """
        if view is not None and self._view_state(view) != self._view_key:
            self._build_targets(view)

    def _build_targets(self, view) -> None:
        """Collect every non-moving item's snap points in *view*'s visible rect.

        Walks ``scene.items()`` WITHOUT a rect: the scene is NoIndex, and a
        rect query calls every item's (Python) boundingRect/shape — ~110 ms
        at 8k items vs <1 ms unfiltered. Points are culled to the visible
        rect (padded by one aperture) instead. Underlay groups are kept for
        per-move index queries; their children are skipped through one
        identity set (no per-child method calls — DXF underlays reach 100k+
        children).
        """
        engine = self._engine
        self._view_key = self._view_state(view)
        self._scale = _se._safe_scale(view.transform().m11())
        self._cell = _se.px_to_scene(float(_se.SNAP_TOLERANCE_PX), self._scale) or 1.0
        self._grid = {}
        self._underlays = []
        if not self._handles:
            return
        c = self._cell
        vis = view.mapToScene(view.viewport().rect()).boundingRect().adjusted(
            -c, -c, c, c)
        x0, y0, x1, y1 = vis.left(), vis.top(), vis.right(), vis.bottom()
        grid = self._grid
        floor = math.floor
        items = self._scene.items()
        # Pass 1 (isinstance only, no Qt calls per child): underlay groups
        # and the identity set of their children.
        skip: set = set()
        for item in items:
            if _is_underlay_group(item):
                skip.update(item.childItems())
                if (isinstance(QGraphicsItem.data(item, 4), UnderlaySnapIndex)
                        and item.isVisible()
                        and item.sceneBoundingRect().intersects(vis)):
                    self._underlays.append(item)
                skip.add(item)
        # Nodes in the moving set drag their pipes (which stretch): those
        # pipes' points are wrong by construction, so they are not targets.
        moving_nodes = {it for it in self._moving if hasattr(it, "pipes")}
        for item in items:
            if item in skip:
                continue
            if not item.isVisible() or self._is_moving(item):
                continue
            if item.zValue() > 150 or _tag(item) == "origin":
                continue
            if isinstance(item, Pipe):
                if engine.skip_pipes:
                    continue
                if (getattr(item, "node1", None) in moving_nodes
                        or getattr(item, "node2", None) in moving_nodes):
                    continue
            for kind, p, name in engine._collect(item):
                px, py = p.x(), p.y()
                if (kind in HANDLE_TYPES
                        and x0 <= px <= x1 and y0 <= py <= y1):
                    # Inlined _key (hot loop: every visible target point).
                    grid.setdefault((floor(px / c), floor(py / c)), []).append(
                        (kind, p, item, name))

    def _is_moving(self, item) -> bool:
        """Whether *item* or any ancestor is in the moving set.

        Args:
            item: A scene item.

        Returns:
            True for a moving item or one of its children.
        """
        p = item
        while p is not None:
            if p in self._moving:
                return True
            p = p.parentItem()
        return False

    def _key(self, p: QPointF) -> tuple[int, int]:
        """The grid cell of scene point *p* (cell side = one aperture).

        Args:
            p: Scene point.

        Returns:
            Integer (column, row) cell key.
        """
        c = self._cell
        return (math.floor(p.x() / c), math.floor(p.y() / c))

    # ── per move ───────────────────────────────────────────────────────────

    def best(self, anchor_now: QPointF):
        """Best handle-to-target hit for the anchor at *anchor_now*.

        A target lying on a handle's own REST position is skipped for that
        handle (it is where the handle already is — a connected line's end).

        Returns:
            ``(corrected_anchor, HandleSnapResult)`` — the anchor position that
            puts the winning handle exactly on its target, and the target as a
            snap result (for the marker) — or None when no handle is within
            the aperture of a target.
        """
        if not self._handles:
            return None
        aperture = float(_se.SNAP_TOLERANCE_PX)
        band = float(_se.SNAP_PRIORITY_BAND_PX)
        best = None   # (d_px, prio, handle, kind, target, src, name)
        ax, ay = anchor_now.x(), anchor_now.y()
        rx0, ry0 = self._anchor0.x(), self._anchor0.y()
        for h in self._handles:
            hx, hy = h.x(), h.y()
            q = QPointF(ax + hx, ay + hy)
            restx, resty = rx0 + hx, ry0 + hy
            kx, ky = self._key(q)
            cands = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    cands.extend(self._grid.get((kx + dx, ky + dy), ()))
            if self._underlays:
                cands.extend(self._underlay_targets(q))
            for kind, p, src, name in cands:
                px, py = p.x(), p.y()
                if (abs(px - restx) < _SELF_REST_EPS
                        and abs(py - resty) < _SELF_REST_EPS):
                    continue
                d_px = math.hypot(px - q.x(), py - q.y()) * self._scale
                if d_px > aperture:
                    continue
                prio = SNAP_PRIORITY.get(kind, 6)
                if best is None or _se._band_beats(d_px, prio, best[0], best[1], band):
                    best = (d_px, prio, h, kind, p, src, name)
        if best is None:
            return None
        _d, _pr, h, kind, p, src, name = best
        corrected = QPointF(p.x() - h.x(), p.y() - h.y())
        return corrected, HandleSnapResult(point=QPointF(p), snap_type=kind,
                                           source_item=src, name=name)

    def _underlay_targets(self, q: QPointF) -> list:
        """Underlay snap points within one aperture cell of *q*.

        Args:
            q: Scene point (a handle's current position).

        Returns:
            ``(kind, point, group, name)`` tuples from each kept underlay
            group's spatial index.
        """
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
                for kind, p, name in self._engine._collect_from_geom(g, xf, bounds):
                    if kind in HANDLE_TYPES:
                        out.append((kind, p, group, name))
        return out
