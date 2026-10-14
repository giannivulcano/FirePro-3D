"""Constraint controller — the Qt shell of the sketch solver.

parametric-constraint-system.md §3, §8. Composed into every Model_Space;
active only for ``scene_role == "block_editor"`` (D2). Every geometry edit in
the editor routes through one of the seams below; with no constraints each
seam is a no-op (the pre-constraint behaviour).

Solve policy (§7.2): goals are the items' current values (weight 1, D22),
the item(s) an edit changed are goals at ``W_EDIT``, a drag's grabbed handle
is pinned at ``W_PIN``; constraints are hard. Only the union-find
components containing a changed handle are solved. On failure nothing is
written back and any edit already applied is undone (D10 hold-last-good).
"""
from __future__ import annotations

import contextlib
import copy
import logging
import math
import uuid
from dataclasses import dataclass

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import QPoint, QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QPen, QPolygonF

from . import sketch_model as sm
from . import theme as _theme
from .geometry_2d import SplineItem
from .paper_display import paper_pass_active
from .sketch_adapters import ANG_WRITE_TOL, DEGEN_EPS, POS_WRITE_TOL, adapter_for
from .sketch_solver import (BUILDERS, LIN_TOL, NumpySolver, System, W_EDIT, W_PIN,
                            const_point)
from .text_item import TextItem
from .theme import M

# Model_Space tracking lists whose items can carry constraints (§5.1).
_PARTICIPATING = ("_draw_lines", "_draw_rects", "_draw_circles",
                  "_draw_arcs", "_draw_ellipses", "_polylines", "_draw_polygons",
                  "_texts", "_block_instances")
# D39 / MW-12: state -> theme token for the paint-time tint (H-MW-g).
_TINT_TOKEN = {"free": "constraint_free", "defined": "ink", "conflict": "danger"}
_log = logging.getLogger(__name__)
CONFLICT_STATUS = "Over-constrained: the change was not applied"
INVALID_STATUS = "Invalid constraint"
REDUNDANT_STATUS = "Redundant constraint: already implied by others"   # D42
TRIVIAL_STATUS = "That point is already on it by construction -- pick another target"
# D17 (CS3); "flipped" since the 2026-10-12 ruling: Flip refuses a fully
# defined BLOCK instance only (D45; see modify_tools_controller.flip_refusal_targets).
GROUNDED_STATUS = ("Fully defined geometry can't be moved, rotated, scaled or "
                   "flipped -- delete or suppress a constraint first")
TYPED_TOL = 1e-6        # D31: a typed value lands within this (mm / rad)
# D34 translate-first pass (_solve_x): it is taken outright when it holds the
# edit within HONOUR_TOL; otherwise only when it moves the edit at most
# HONOUR_RATIO times as far as the plain-weights solve does (bar pinned on the
# VC9 F4 / shrink probes: translatable cases measure ~1.01, a forced resize 2+).
HONOUR_TOL = 1e-6
HONOUR_RATIO = 1.1
# Every tracking list that holds an editor primitive with a ``_uid``, including
# the adapter-less ones (spline, D5): a record that names one still resolves
# for Save (§6.4) even though it can never be solved in v1.
_PRIMITIVE_LISTS = _PARTICIPATING + ("_draw_splines",)


@dataclass(frozen=True)
class SketchDiag:
    """Commit-level diagnostics (§7.4, D39/D41): sketch DOF, amber ids,
    per-item remaining DOF, and the uids touched by a red constraint."""
    dof: int
    redundant: frozenset
    item_dof: dict
    conflict_uids: frozenset

    def state(self, uid) -> str:
        """``"conflict"`` / ``"defined"`` / ``"free"`` for an item uid."""
        if uid in self.conflict_uids:
            return "conflict"
        return "defined" if self.item_dof.get(uid, 1) == 0 else "free"


def removed_status(n: int) -> str:
    """§8 status after an operation consumed constrained entities."""
    return f"{n} constraint{'' if n == 1 else 's'} removed"


class PartnerWatch:
    """D46 (refined 2026-10-10): a drag's constraint partners, watched for
    movement. A partner stays a snap target until a snap query first sees
    the solve has moved it (its adapter values off their press-time read);
    from then on it is excluded for the rest of the gesture -- monotone, so a target never
    flickers back while its spot is stale.

    The latch is per item (a moved partner's unmoved points go too) and is an
    anti-flicker choice: a partner back exactly at its press-time read is no
    longer stale, but would otherwise toggle as a target frame to frame. A
    partner with no adapter is not watched -- the solve cannot write it, so
    it stays a plain target.

    Args:
        partners: ``ConstraintController.drag_partners`` result, read at
            press (items at rest).
    """

    _EPS = 1e-9

    def __init__(self, partners=()):
        self._rest = {}
        for it in partners:
            ad = adapter_for(it)
            if ad is not None:
                self._rest[it] = (ad, list(ad.read(it)))
        self._moved: set = set()

    def __contains__(self, item) -> bool:
        return item in self._rest

    def __len__(self) -> int:
        return len(self._rest)

    def __iter__(self):
        return iter(self._rest)

    def moved(self, item) -> bool:
        """Whether the solve has moved partner *item* since press (latched)."""
        if item in self._moved:
            return True
        rec = self._rest.get(item)
        if rec is None:
            return False
        ad, vals = rec
        now = ad.read(item)
        if len(now) != len(vals) or any(abs(a - b) > self._EPS
                                        for a, b in zip(now, vals)):
            self._moved.add(item)
            return True
        return False


def _safe_ref_uids(c) -> set | None:
    """``sm.ref_uids`` that tolerates a malformed (inert, newer-build) record.

    Returns:
        The referenced uids, or None when a ref has neither ``ref`` nor ``uid``.
    """
    try:
        return sm.ref_uids(c)
    except (KeyError, TypeError):
        return None


def _is_reflection(point_map) -> bool:
    """Whether *point_map* reverses orientation (Flip / Mirror)."""
    o = point_map(QPointF(0.0, 0.0))
    x = point_map(QPointF(1.0, 0.0))
    y = point_map(QPointF(0.0, 1.0))
    return ((x.x() - o.x()) * (y.y() - o.y()) - (x.y() - o.y()) * (y.x() - o.x())) < 0.0


def _angle_helper_ok(h) -> bool:
    """D72: ``{"dirs": [±1, ±1], "sign": ±1}`` exactly."""
    if not isinstance(h, dict):
        return False
    d, s = h.get("dirs"), h.get("sign")
    return (isinstance(d, list) and len(d) == 2
            and all(x in (1, -1) and not isinstance(x, bool) for x in d)
            and s in (1, -1) and not isinstance(s, bool))


_AXIS_D = {"x_axis": (1.0, 0.0), "y_axis": (0.0, 1.0)}

PICK_SAME_POINT_STATUS = "Pick a different point"
DIM_REFERENCE_STATUS = ("Dimension added as Reference -- it would over-define the "
                        "sketch")                                    # D52
DIM_ZERO_STATUS = "Pick two separate points"
DIM_REFERENCE_HINT = "Reference dimension -- set it to Driving to edit"   # D52
DIM_SUPPRESSED_HINT = "Suppressed dimension -- unsuppress it to edit"
DIM_REPEAT_STATUS = "Already dimensioned"                                # D56
DIM_RECT_REPEAT_STATUS = ("Already dimensioned -- a rectangle's opposite sides "
                          "share one {}")                                # D56
DIM_TEXT_STATUS = "Text boxes can't be dimensioned yet"                 # CS3c AC6
DIM_ANGLE_ZERO_STATUS = "Pick an edge with length"                          # D77
DIM_COLLINEAR_STATUS = "Lines are collinear -- nothing to dimension"        # D77/D81


def _xy(p) -> tuple[float, float]:
    return (p.x(), p.y())


def _seg_dist(p, a, b) -> float:
    """Distance from *p* to segment *ab* (all viewport px)."""
    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p.x() - ax) * dx + (p.y() - ay) * dy) / L2))
    return math.hypot(p.x() - ax - t * dx, p.y() - ay - t * dy)


def _vp_to_scene(view, vp_pt) -> QPointF:
    """Exact scene point of a viewport-px point (no int rounding)."""
    inv, _ok = view.viewportTransform().inverted()
    return inv.map(QPointF(vp_pt))


class PickState:
    """D21 hover-marker pick mode for one constraint type.

    Every participating primitive's §5.1 point handles (and the origin) show
    as hollow square markers. H / V: the hover is the nearest point within
    ``CONSTRAINT_PICK_POINT_TOL_PX`` or — before the first point pick — the
    nearest edge within ``CONSTRAINT_PICK_EDGE_TOL_PX`` (viewport px).
    Coincident (CS3): a point plus a point / origin / edge / circle-arc curve
    / X-Y axis, in either order -- two non-points never pair. Hover priority:
    points > edges + curves > axes (each within its px tolerance).
    """

    def __init__(self, ctl, ctype: str):
        self.ctl, self.ctype = ctl, ctype
        self.picks: list[dict] = []
        self.kinds: list[str] = []
        self.hover: dict | None = None
        self.hover_kind: str | None = None      # "point" / "edge" / "curve" / "axis"
        self.pending: list | None = None         # CS4b D63: dim refs awaiting placement
        self.pending_type: str | None = None     # CS5 D69: the pending dim's record type
        self.cursor: QPointF | None = None       # last hover (viewport px) for the preview

    def _candidates(self):
        """``(kind, ref, a, b)`` scene-space: point ``(p, None | "mid")``
        (``"mid"`` = an edge midpoint, CS3b), edge
        ``(a, b)``, curve ``(centre, (r, item))``, axis ``(None, None)``."""
        coincident = self.ctype == "coincident"
        for it in self.ctl.items():
            uid = getattr(it, "_uid", None)
            if uid is None:
                continue
            ad = adapter_for(it)
            x = np.array(ad.read(it), dtype=float)
            mids = ad.mid_names(it)
            hidden = ad.hidden_names(it)
            for name, e in ad.points(it, 0).items():
                if name in hidden:                    # CS3c: legacy text ins
                    continue
                # CS3b: b = "mid" tags an edge midpoint (a triangle marker).
                yield ("point", {"uid": uid, "h": name}, QPointF(*e.eval(x)[0]),
                       "mid" if name in mids else None)
            for name, (a, b) in ad.edges(it, 0).items():
                yield ("edge", {"uid": uid, "h": name},
                       QPointF(*a.eval(x)[0]), QPointF(*b.eval(x)[0]))
            if coincident:
                for name, cv in ad.curves(it, 0).items():
                    if name in hidden:                # CS5 D79: defining circles
                        continue
                    yield ("curve", {"uid": uid, "h": name},
                           QPointF(*cv.center.eval(x)[0]), (float(x[cv.r]), it))
        yield "point", {"ref": "origin"}, QPointF(0.0, 0.0), None
        if coincident:
            yield "axis", {"ref": "x_axis"}, None, None
            yield "axis", {"ref": "y_axis"}, None, None

    def _allowed(self, kind: str) -> bool:
        if self.ctype != "coincident":
            return kind == "point" or (kind == "edge" and not self.picks)
        return kind == "point" or not self.picks or self.kinds[0] == "point"

    @staticmethod
    def _curve_vp(view, centre, r) -> tuple:
        """(viewport centre, viewport radius) of a curve candidate."""
        vc = QPointF(view.mapFromScene(centre))
        rim = QPointF(view.mapFromScene(QPointF(centre.x() + r, centre.y())))
        return vc, math.dist(_xy(vc), _xy(rim))

    @classmethod
    def _dist(cls, view, vp_pt, kind, a, b) -> float:
        """Viewport-px distance to a point / edge / curve candidate (axes are
        measured inline in :meth:`hover_at`). A curve is its drawn outline:
        a circle all round, an arc only within its span."""
        if kind == "point":
            return math.dist(_xy(vp_pt), _xy(view.mapFromScene(a)))
        if kind == "edge":
            return _seg_dist(vp_pt, view.mapFromScene(a), view.mapFromScene(b))
        r, it = b
        vc, rp = cls._curve_vp(view, a, r)
        d = abs(math.dist(_xy(vp_pt), _xy(vc)) - rp)
        span = getattr(it, "_span_deg", None)
        if span is not None and span < 360.0:          # an arc: its drawn span only
            sp = view.mapToScene(QPoint(int(round(vp_pt.x())), int(round(vp_pt.y()))))
            t = math.degrees(math.atan2(-(sp.y() - a.y()), sp.x() - a.x()))
            if (t - it._start_deg) % 360.0 > span:
                return math.inf
        return d

    def hover_at(self, view, vp_pt) -> dict | None:
        """Nearest allowed candidate: points (point tol) > edges / curves
        (edge tol) > axes (edge tol)."""
        if self.pending is not None:             # D63: placing -- no marker hover
            self.hover = self.hover_kind = None
            return None
        cands = [c for c in self._candidates() if self._allowed(c[0])]
        o = view.mapFromScene(QPointF(0.0, 0.0))
        best = None
        for kinds, tol in ((("point",), M.CONSTRAINT_PICK_POINT_TOL_PX),
                           (("edge", "curve"), M.CONSTRAINT_PICK_EDGE_TOL_PX),
                           (("axis",), M.CONSTRAINT_PICK_EDGE_TOL_PX)):
            for kind, ref, a, b in cands:
                if kind not in kinds:
                    continue
                if kind == "axis":
                    d = (abs(vp_pt.y() - o.y()) if ref["ref"] == "x_axis"
                         else abs(vp_pt.x() - o.x()))
                else:
                    d = self._dist(view, vp_pt, kind, a, b)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, ref, kind)
            if best is not None:
                break
        self.hover = best[1] if best else None
        self.hover_kind = best[2] if best else None
        return self.hover

    def status(self) -> str:
        label = sm.REGISTRY[self.ctype].label
        n = len(self.picks)
        if self.ctype == "coincident":
            what = ("pick a point" if n and self.kinds[0] != "point" else
                    "pick a point, then a point, edge, circle/arc or axis")
            return f"{label}: {what} ({n}/2) · Esc to cancel"
        if self.ctype == "dim_distance":         # CS4b D63
            if self.pending is not None:
                return f"{label}: click to place the dimension · Esc to cancel"
            return f"{label}: pick an edge or 2 points ({n}/2) · Esc to cancel"
        return f"{label}: pick 2 points or 1 edge ({n}/2) · Esc to cancel"

    def paint(self, painter, view, t) -> None:
        """Hover / picked edge, curve and axis glow, then the markers: hollow
        ``muted`` squares (triangles for edge midpoints, CS3b), filled
        ``accent`` for the hovered (enlarged) and already-picked handles."""
        half = M.CONSTRAINT_PICK_MARKER_HALF_PX
        cands = list(self._candidates())
        o = QPointF(view.mapFromScene(QPointF(0.0, 0.0)))
        vpr = QRectF(view.viewport().rect())
        for kind, ref, a, b in cands:
            if kind == "point" or not (ref == self.hover or ref in self.picks):
                continue
            pen = QPen(t.color("accent", M.CONSTRAINT_PICK_EDGE_GLOW_ALPHA),
                       M.CONSTRAINT_PICK_EDGE_GLOW_W_PX)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if kind == "edge":
                painter.drawLine(QPointF(view.mapFromScene(a)), QPointF(view.mapFromScene(b)))
            elif kind == "curve":
                vc, rp = self._curve_vp(view, a, b[0])
                painter.drawEllipse(vc, rp, rp)
            elif ref["ref"] == "x_axis":
                painter.drawLine(QPointF(vpr.left(), o.y() + 0.5),
                                 QPointF(vpr.right(), o.y() + 0.5))
            else:
                painter.drawLine(QPointF(o.x() + 0.5, vpr.top()),
                                 QPointF(o.x() + 0.5, vpr.bottom()))
        for kind, ref, a, tag in cands:
            if kind != "point":
                continue
            hov = ref == self.hover
            on = hov or ref in self.picks
            s = half + (1.5 if hov else 0.0)
            p = QPointF(view.mapFromScene(a))
            painter.setPen(QPen(t.color("accent" if on else "muted"), 1.3))
            painter.setBrush(t.color("accent" if on else "surface"))
            if tag == "mid":                          # CS3b: edge midpoint
                painter.drawPolygon(QPolygonF([QPointF(p.x(), p.y() - s),
                                               QPointF(p.x() + s, p.y() + s),
                                               QPointF(p.x() - s, p.y() + s)]))
            else:
                painter.drawRect(QRectF(p.x() - s, p.y() - s, 2 * s, 2 * s))
        if self.pending is not None and self.cursor is not None:
            from .constraint_dims import paint_preview      # CS4b D63
            paint_preview(painter, view, self.ctl,
                          (self.pending_type or "dim_distance", self.pending),
                          self.cursor, t)


class ConstraintController:
    """Owns the editor's constraint list and every solve seam (spec §3, §8)."""

    def __init__(self, scene):
        self._scene = scene
        self.enabled = getattr(scene, "scene_role", "plan") == "block_editor"
        self.constraints: list[sm.Constraint] = []
        self.selected_id: str | None = None
        self.hover_id: str | None = None
        # D32: glyphs show only for constraints touching a selected entity,
        # plus the selected constraint; Show Constraints is a temporary
        # show-every-glyph override, default off.
        self.show_all = False
        # D39: Constraint Status (Inspect toggle) -- geometry tinted by state,
        # default ON, editor only.
        self.show_status = True
        # () -> the nothing-selected panel target (main.py: the D40 block view).
        self.panel_fallback = None
        self.pick: PickState | None = None     # D21 pick session
        # D37/D38: ids of admitted constraints whose admission broke
        # solvability. They sit out of every solve until a STRUCTURAL commit
        # re-checks them (derived state -- never saved; re-derived in list
        # order on load / undo restore / paste).
        self.red: set[str] = set()
        self._commit_gen = 0           # bumps on every commit-level change (diagnostics key)
        self._diag = None              # (key, SketchDiag)
        self._tint_memo = None         # (token, SketchDiag, {uid: state}) -- H-MW-g
        self._tint_colors = None       # (Theme, {state: QColor}) -- H-MW-g
        self._build_cache = None       # (key, sys, slots, base) -- D18 _build reuse
        # Per-frame glyph-layout cache tokens (constraint_paint._frame, VC9 F3):
        # bumped on every scene change / item-selection change.
        self._scene_gen = 0
        self._sel_gen = 0
        self._label_gen = 0     # CS4b: a dim offset change (frame key, no diag recompute)
        self.dim_drag = None    # CS4b D64: [cid, old label, press vp, moved]
        self._frames: dict = {}                # id(view) -> (key, _Frame)
        self._drag_extra: list = []            # body-drag selection items outside the ctx
        # Zero-arg callbacks run when the constraint selection / list changes
        # (the ribbon's Delete Constraints enable state, main.py).
        self.state_listeners: list = []
        self._solver = NumpySolver()
        self._drag_snap = None
        self._last_good = None
        self._drag_ctx = None
        self._drag_cur = None                  # session: slot values as last written (D18)
        self._drag_base = None                 # session: slot values at begin_drag
        self._drag_layout = None               # session: _slot_layout (D18)
        self._painted: dict = {}               # id(view) -> last glyph/glow QRect
        if self.enabled:
            scene.selectionChanged.connect(self._on_selection_changed)
            scene.changed.connect(self._on_scene_changed)

    # ── canvas selection / repaint (D11, constraint_paint) ───────────────
    def select(self, cid) -> None:
        """Select a constraint (glyph / panel-row click); item selection clears."""
        self._scene.clearSelection()
        self.selected_id = cid
        self._repaint()
        self._notify_state()
        self._refresh_panel()

    def clear_selected(self) -> bool:
        """Drop the selected constraint (Esc / a missed press). True if one was."""
        if self.selected_id is None:
            return False
        self.selected_id = None
        self._repaint()
        self._notify_state()
        self._refresh_panel()
        return True

    def delete_selected(self) -> int:
        """Delete the selected constraint (geometry untouched); one undo step."""
        return self.delete([self.selected_id]) if self.selected_id else 0

    def _notify_state(self) -> None:
        """Run :attr:`state_listeners`; a failing listener never escapes."""
        for cb in list(self.state_listeners):
            try:
                cb()
            except Exception:
                _log.exception("constraint state listener failed")

    def _refresh_panel(self) -> None:
        """Re-show the property panel's current context after a constraint
        change (the ``requestPropertyUpdate`` refresh path, property-panel.md):
        the selected constraint's :class:`ConstraintAdapter`, else the item
        selection, else nothing. Rebuilt from ids every time -- never a held
        item/record reference (undo replaces both)."""
        sig = getattr(self._scene, "requestPropertyUpdate", None)
        if sig is None:
            return
        if self.find(self.selected_id) is not None:
            sig.emit(ConstraintAdapter(self, self.selected_id))
            return
        sel = self._scene.selectedItems()
        if sel:
            sig.emit(sel)
        else:                            # D40: the block view, not a blank panel
            fb = self.panel_fallback
            sig.emit(fb() if callable(fb) else None)

    def find(self, cid):
        """The constraint with id *cid*, or None."""
        if cid is None:
            return None
        return next((c for c in self.constraints if c.id == cid), None)

    def _on_selection_changed(self) -> None:
        """An item selection clears the selected constraint. A Qt slot: a
        dying scene still emits, so bail when its wrapper is gone; never raises."""
        self._sel_gen += 1                     # D32 visibility follows the selection
        try:
            if sip.isdeleted(self._scene):
                return
            if self.selected_id is not None and self._scene.selectedItems():
                self.selected_id = None
                self._repaint()
                self._notify_state()
        except Exception:
            _log.exception("constraint selection-change handling failed")

    def _on_scene_changed(self, _regions) -> None:
        """Glyphs + glow sit outside item dirty regions (MinimalViewportUpdate):
        repaint old ∪ new glyph region per view. A Qt slot: never raises.

        Bumps the per-frame layout token first: the layouts computed here are
        the ones paint and the hover pick reuse this frame (VC9 F3)."""
        self._scene_gen += 1
        try:
            if sip.isdeleted(self._scene) or not self.constraints and not self._painted:
                return
            from .constraint_paint import dirty_rect
            from PyQt6.QtCore import QRect
            for v in self._scene.views():
                if sip.isdeleted(v):
                    continue
                new = dirty_rect(v, self)
                dirty = self._painted.get(id(v), QRect()).united(new)
                self._painted[id(v)] = new
                if not dirty.isEmpty():
                    v.viewport().update(dirty)
        except Exception:
            _log.exception("constraint glyph repaint failed")

    def reset(self) -> None:
        """New / Open: drop every constraint and all transient state."""
        self.constraints = []
        self.selected_id = self.hover_id = None
        self.pick = None
        self.red = set()
        self._commit_gen += 1
        self._end_session()

    # ── items ────────────────────────────────────────────────────────────
    def items(self) -> list:
        """Every scene item that can carry a constraint (has an adapter)."""
        out = []
        for attr in _PARTICIPATING:
            out.extend(getattr(self._scene, attr, ()))
        return [it for it in out if adapter_for(it) is not None]

    def item_by_uid(self) -> dict:
        """``uid -> item`` over :meth:`items`."""
        return {getattr(it, "_uid", None): it for it in self.items()}

    def active(self) -> list:
        """Solvable constraints: enabled, built and valid (not inert), not red
        (D37), refs resolve."""
        by = set(self.item_by_uid())
        out = []
        for c in self.constraints:
            if (not c.enabled or c.inert or c.id in self.red
                    or (c.type in sm.VALUED and not c.driving)):    # D7/D52 Reference
                continue
            uids = _safe_ref_uids(c)
            if uids is not None and uids <= by:
                out.append(c)
        return out

    def constrained_uids(self) -> set:
        """Uids referenced by any active constraint."""
        return {u for c in self.active() for u in (_safe_ref_uids(c) or ())}

    def touches(self, items) -> bool:
        """Whether any of *items* is referenced by an active constraint."""
        uids = self.constrained_uids()
        return any(getattr(it, "_uid", None) in uids for it in items)

    def drag_partners(self, items) -> list:
        """Items a drag of *items* can move through the solve: everything
        constraint-connected to them (active constraints, transitively),
        *items* excluded. A drag's snap sessions watch them (``PartnerWatch``):
        a partner is a target until the solve moves it, then its spot is stale
        (D46, refined 2026-10-10; was CS1 VC9 R2).
        """
        if not self.enabled:
            return []
        uids = {getattr(it, "_uid", None) for it in items} - {None}
        cons = self.active()
        if not uids or not cons:
            return []
        by = self.item_by_uid()
        out = []
        for group in self._groups(cons):
            if group & uids:
                out += [by[u] for u in group - uids if u in by]
        return out

    def refuse_grounded(self, items) -> bool:
        """D17 (CS3 ruling): True -- with ``GROUNDED_STATUS`` posted -- when
        any of *items* is fully defined (its own D41 state, per-item DOF 0).
        A partly grounded item is not refused: the solve moves it along its
        free DOF. The one predicate behind the Move / Rotate / Scale entry
        (``Model_Space.set_mode``) and their commits, and behind the Flip
        entry / ``commit_reflect`` check -- which passes only the block
        instances among the targets (``flip_refusal_targets``, D45 as refined
        2026-10-12): a grounded primitive flips and re-solves, a grounded
        block's mirror / rotation sit outside the solver."""
        if not self.enabled or not items:
            return False
        uids = {getattr(it, "_uid", None) for it in items} & self.constrained_uids()
        if not uids:
            return False
        d = self.diagnostics()
        if any(u in d.item_dof and d.state(u) == "defined" for u in uids):
            self._status(GROUNDED_STATUS)
            return True
        return False

    def constraints_on(self, item) -> list:
        """Every constraint (active or not) that references *item*."""
        u = getattr(item, "_uid", None)
        return [c for c in self.constraints if u in (_safe_ref_uids(c) or ())]

    # ── validation (one check for add / load / restore / paste) ──────────
    @staticmethod
    def _ref_kind(ref, by) -> str | None:
        """``"point"`` / ``"edge"`` / ``"axis"`` for one ref, or None when it
        does not resolve (unknown uid / handle / ground, malformed)."""
        if not isinstance(ref, dict):
            return None
        if "ref" in ref:
            g = ref["ref"]
            if g == "origin":
                return "point"
            return "axis" if g in ("x_axis", "y_axis") else None
        it = by.get(ref.get("uid"))
        h = ref.get("h")
        if it is None or not isinstance(h, str):
            return None
        ad = adapter_for(it)
        if h in ad.points(it, 0):
            return "point"
        if h in ad.edges(it, 0):
            return "edge"
        if h in ad.curves(it, 0):
            return "curve"
        return None

    def _valid(self, c, by=None) -> bool:
        """Whether a built-type record can be solved here: every uid resolves,
        every handle exists on its adapter, and the ref kinds match one of
        ``REGISTRY[type].patterns`` (origin = point; X/Y axis = axis)."""
        spec = sm.REGISTRY.get(c.type)
        if spec is None or not spec.implemented:
            return False
        if not isinstance(c.refs, list) or not c.refs:
            return False
        if not all(isinstance(r, dict) for r in c.refs):
            return False
        # Two refs naming one handle (§7.3): compare identities, not dicts.
        idents = {("ref", r["ref"]) if "ref" in r else ("uid", r.get("uid"), r.get("h"))
                  for r in c.refs}
        if len(idents) != len(c.refs):
            return False
        if by is None:
            by = self.item_by_uid()
        if c.type in sm.VALUED:                 # §6.3: a dim needs D > 0 (D77 max)
            v = c.value
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(v) or v <= 0.0
                    or v >= sm.VALUE_MAX.get(c.type, math.inf)):
                return False
        if c.type == "dim_angle" and not _angle_helper_ok(c.helper):
            return False
        if c.type == "dim_point_line" and not (
                isinstance(c.helper, dict) and c.helper.get("side") in (1, -1)
                and not isinstance(c.helper.get("side"), bool)):
            return False
        kinds = tuple(self._ref_kind(r, by) for r in c.refs)
        if c.type == "dim_arc_angle" and None not in kinds:
            r0 = c.refs[0]
            it = by.get(r0.get("uid"))
            cv = adapter_for(it).curves(it, 0).get(r0.get("h")) if it is not None else None
            if cv is None or cv.span is None:
                return False
        return None not in kinds and kinds in spec.patterns

    def _identically_satisfied(self, c) -> bool:
        """CS3 pin: a point_on_curve whose residual is zero for ANY values of
        its items (a line's own end on its edge, an arc's own end on its
        curve, the origin on an axis) adds nothing -- refused at add. Probed
        numerically: three positive perturbations of every variable (keeps
        radii positive) all leave every row at zero."""
        if c.type != "point_on_curve":
            return False
        sys_, _slots, _w = self._build_fresh([c])
        if sys_.aliases or sys_.fixes:
            return False
        rng = np.random.default_rng(0)
        for _ in range(3):
            x = sys_.x + rng.uniform(0.5, 5.0, len(sys_.x))
            if any(abs(r.fn(x)[0]) > 1e-9 for r in sys_.rows):
                return False
        return True

    def _adopt(self, record, by) -> sm.Constraint:
        """A stored / pasted record as a Constraint. Unreadable or invalid
        records are kept VERBATIM and inert (never solved, saved as-is, §6.4)."""
        try:
            c = sm.Constraint.from_dict(record)
        except Exception:                       # not a dict, unreadable fields
            return sm.Constraint(id=uuid.uuid4().hex, type="", refs=[],
                                 raw=copy.deepcopy(record))
        if not c.inert and not self._valid(c, by):
            c.raw = copy.deepcopy(record)
            c.invalid = True
        return c

    # ── system build ─────────────────────────────────────────────────────
    def _build(self, cons):
        """:meth:`_build_fresh`, reusing the last System when the constraint
        set and the items' structure are unchanged -- only x is re-read (D18
        commit bar: the commit solve and its diagnostics share one build).
        Callers must not keep mutating a returned System's ``x`` across
        builds (a drag session uses :meth:`_build_fresh`)."""
        by = self.item_by_uid()
        try:
            key = (tuple((c.id, c.type, repr(c.refs), c.value, c.driving, repr(c.helper))
                         for c in cons),
                   tuple((u, id(by[u]), adapter_for(by[u]).struct_key(by[u]))
                         for c in cons for u in (_safe_ref_uids(c) or ())))
        except KeyError:
            return self._build_fresh(cons)
        hit = self._build_cache
        if hit is not None and hit[0] == key:
            _k, sys_, slots, base = hit
            for _u, (it, ad, off) in slots.items():
                sys_.x[off:off + ad.nvars(it)] = ad.read(it)
            return sys_, slots, base
        sys_, slots, base = self._build_fresh(cons)
        self._build_cache = (key, sys_, slots, base)
        return sys_, slots, base

    def _build_fresh(self, cons):
        """(System, slots ``uid -> (item, adapter, offset)``, base weights)."""
        by = self.item_by_uid()
        slots, x, w = {}, [], []
        for c in cons:
            for u in (_safe_ref_uids(c) or ()):
                if u not in slots:
                    it = by[u]
                    ad = adapter_for(it)
                    slots[u] = (it, ad, len(x))
                    x.extend(ad.read(it))
                    w.extend(ad.var_weights(it))
        sys_ = System(x=np.array(x, dtype=float))
        for c in cons:
            kw = {"value": float(c.value)} if c.type in sm.VALUED else {}
            if c.type in ("dim_angle", "dim_point_line"):
                kw["helper"] = c.helper
            BUILDERS[c.type](c.id, self._ends(c, slots), sys_, **kw)
        return sys_, slots, np.array(w, dtype=float)

    def _resolve(self, ref, slots):
        if sm.is_ground(ref):
            g = ref["ref"]
            if g == "origin":
                return const_point(0.0, 0.0)
            if g in ("x_axis", "y_axis"):
                return g                       # build_point_on_curve's axis target
            raise ValueError(f"unknown ground {g!r}")
        it, ad, off = slots[ref["uid"]]
        h = ref["h"]
        pts = ad.points(it, off)
        if h in pts:
            return pts[h]
        eds = ad.edges(it, off)
        if h in eds:
            return eds[h]
        return ad.curves(it, off)[h]

    def _ends(self, c, slots):
        res = [self._resolve(r, slots) for r in c.refs]
        return res[0] if len(res) == 1 else (res[0], res[1])

    @staticmethod
    def _var_indices(slots, uids) -> list:
        out = []
        for u in uids:
            slot = slots.get(u)
            if slot is not None:
                it, ad, off = slot
                out.extend(range(off, off + ad.nvars(it)))
        return out

    # ── solve + write-back (one write per item, §3) ──────────────────────
    def _solve(self, *, edited=(), pin=None, ctx=None, focus=None,
               typed=None, reset: bool = False) -> bool:
        """One solve + write-back.

        Args:
            edited: Items whose current values are goals at ``W_EDIT``.
            pin: ``(item, grip_index)`` — the drag's grabbed handle, ``W_PIN``.
            ctx: A cached ``(sys, slots, base_weights)`` from :meth:`begin_drag`:
                the System structure is reused across drag frames (only x is
                refreshed) — the D18 8 ms drag bar depends on it.
            focus: Uids whose components must be solved (a new or re-enabled
                constraint's items). ``None`` = no focus given.
            typed: ``{uid: [local var index]}`` -- a TYPED edit's changed
                variables (D31): pinned at ``W_PIN`` and required to land
                within ``TYPED_TOL`` of the typed value, else the solve fails.
            reset: A D35 reset frame -- the session-start values are the goals
                of every item the caller did not move (D18; the snapshot is
                not rewritten).

        Only the components holding *edited* / *focus* variables are solved
        (§7.2 components). With neither given, every component is; with a
        focus / edit that names no solver variable, nothing is (and that is
        not a failure).

        Returns:
            True when converged (and written back); False = nothing written.
        """
        if ctx is None:
            cons = self.active()
            if not cons:
                return True
            sys_, slots, base = self._build(cons)
        else:
            sys_, slots, base = ctx
            cur = self._drag_cur
            moved = []
            for it in edited:                  # only the items the caller moved (D18)
                slot = slots.get(getattr(it, "_uid", None))
                if slot is not None:
                    _it, ad, off = slot
                    vals = ad.read(_it)
                    cur[off:off + len(vals)] = vals
                    moved.append((off, len(vals)))
            sys_.x[:] = self._drag_base if reset else cur
            for off, n in moved:
                sys_.x[off:off + n] = cur[off:off + n]
        weights = base.copy()
        edited_uids = {getattr(i, "_uid", None) for i in edited}
        honour = self._var_indices(slots, edited_uids)   # the edit's own vars
        for u in edited_uids:
            slot = slots.get(u)
            if slot is not None:
                it, ad, off = slot
                weights[off:off + ad.nvars(it)] *= W_EDIT
        pinned = []
        for u, ks in (typed or {}).items():          # D31: typed = exact
            slot = slots.get(u)
            if slot is not None:
                pinned.extend(slot[2] + k for k in ks)
        if pin is not None:
            item, grip = pin
            slot = slots.get(getattr(item, "_uid", None))
            if slot is not None:
                pinned.extend(slot[2] + k for k in slot[1].pin_vars(item, grip))
        for i in pinned:
            weights[i] *= W_PIN
        if edited or focus is not None:
            active = self._var_indices(slots, edited_uids | set(focus or ()))
            if not active:
                return True                     # nothing of ours to solve
        else:
            active = None
        x = self._solve_x(sys_, slots, weights, active, honour=pinned or honour)
        if x is None:
            return False
        for u, ks in (typed or {}).items():
            slot = slots.get(u)
            if slot is not None and any(
                    abs(x[slot[2] + k] - sys_.x[slot[2] + k]) > TYPED_TOL for k in ks):
                return False                    # the typed value can't be honoured
        if ctx is None:
            self._write(slots, sys_.x, x)
        else:
            self._write_tracked(slots, sys_.x, x, self._drag_cur)
        return True

    def _solve_x(self, sys_, slots, weights, active, honour=()):
        """The solved full-space x, or None (not converged / D29 collapse).

        D34 "translate, then resize, then rotate": a translate-first pass
        makes every size and angle variable ``W_PIN`` stiffer (their W_SIZE /
        ANG_W ratio kept), so geometry moves rather than resizes / tilts
        whenever a move satisfies -- the plain weights alone let a rect meet a
        point partly by tilting (VC9 F4). Constraints are hard, so that pass
        still resizes / rotates when nothing else satisfies.

        The pass must not cost the EDIT: when it moves an *honour* variable
        (the drag pin / typed values, else the edited items' variables) by
        more than ``HONOUR_TOL``, the plain-weights solve is run as well and
        wins unless the pass moves the edit at most ``HONOUR_RATIO`` times as
        far (e.g. a line moved against a rect that can only shrink: the
        translate-first pass would just move the line back); when the plain
        solve fails, such a pass is a conflict too -- it only "solved" by
        undoing the edit. A failed or collapsing pass falls back to the plain
        solve (and its D29 retry).

        Args:
            honour: Full-space indices whose goals are the edit itself.
        """
        pref = self._stiffened(slots, weights, "stiff_vars")
        if np.array_equal(pref, weights):              # no size / angle vars
            return self._solve_plain(sys_, slots, weights, active)
        res = self._solver.solve(sys_, sys_.x.copy(), pref, active=active)
        if not res.converged or self._collapses(slots, sys_.x, res.x):
            return self._solve_plain(sys_, slots, weights, active)
        dev = self._deviation(res.x, sys_.x, honour)
        if dev <= HONOUR_TOL:
            return res.x
        plain = self._solve_plain(sys_, slots, weights, active)
        if plain is None:
            return None         # the pass only "solved" by undoing the edit
        if dev <= HONOUR_RATIO * self._deviation(plain, sys_.x, honour):
            return res.x
        return plain

    @staticmethod
    def _deviation(x, goal, idx) -> float:
        """Max |x - goal| over *idx* (0 when empty)."""
        if not len(idx):
            return 0.0
        idx = np.asarray(idx, dtype=np.intp)
        return float(np.max(np.abs(x[idx] - goal[idx])))

    def _solve_plain(self, sys_, slots, weights, active):
        """The plain-weights solve + the D29 collapse retry, or None."""
        res = self._solver.solve(sys_, sys_.x.copy(), weights, active=active)
        if not res.converged:
            return None
        # D29: a solve that can only be satisfied by collapsing a shape is a CONFLICT.
        if self._collapses(slots, sys_.x, res.x):
            # The least-change answer collapsed a shape; retry with every size
            # variable stiff (W_PIN) so a non-collapsing answer (e.g. a rotate)
            # wins if one exists. Still collapsing / unsolved -> conflict.
            stiff = self._stiffened(slots, weights, "size_floors")
            res = self._solver.solve(sys_, sys_.x.copy(), stiff, active=active)
            if not res.converged or self._collapses(slots, sys_.x, res.x):
                return None
        return res.x

    @staticmethod
    def _stiffened(slots, weights, which: str):
        """*weights* with each slot's ``ad.<which>(item)`` variables x W_PIN."""
        out = weights.copy()
        for _u, (it, ad, off) in slots.items():
            for i in getattr(ad, which)(it):
                out[off + i] *= W_PIN
        return out

    @staticmethod
    def _write(slots, x_old, x_new, uids=None) -> None:
        """Exactly one write-back per item the solve CHANGED (§3) -- beyond
        the adapter's write tolerance, so a pinned item's solver jitter is
        never written (a rect write canonicalises its pivot, VC9 F2). Per
        variable, only a materially moved one takes its solved value; the
        rest keep the item's old value (``ad.settled``, VC9 R5)."""
        for u, (it, ad, off) in slots.items():
            if uids is not None and u not in uids:
                continue
            n = ad.nvars(it)
            old = x_old[off:off + n]
            new = x_new[off:off + n]
            if ad.changed(it, old, new):
                ad.write(it, np.array(ad.settled(it, old, new), dtype=float))

    def _write_tracked(self, slots, goal, x_new, cur) -> None:
        """Drag-session write-back (D18). Each item's target is exactly what
        the stateless path leaves it at -- ``ad.settled`` against this
        frame's goal when the solve changed it (``ad.changed``), else the goal
        itself -- and it is written only when that differs from its tracked
        value *cur* (updated in place), so a reset frame never rewrites the
        snapshot. Decided over whole arrays (the base-adapter tolerance rules,
        which no adapter overrides) via the session's slot layout."""
        items, starts, var_item, tol = self._drag_layout
        if not items:
            return
        moved = np.abs(x_new - goal) > tol           # beyond the write tolerance
        settled = np.where(moved, x_new, goal)
        changed = np.logical_or.reduceat(moved, starts)
        tgt = np.where(changed[var_item], settled, goal)
        need = np.logical_or.reduceat(tgt != cur, starts)
        for k in np.flatnonzero(need):
            it, ad, off, n = items[k]
            ad.write(it, tgt[off:off + n].copy())
        cur[:] = tgt

    @staticmethod
    def _slot_layout(slots, nx: int) -> tuple:
        """``(items, starts, var_item, tol)`` for :meth:`_write_tracked`:
        per-slot ``(item, adapter, offset, n)``, ascending start offsets, each
        variable's slot index and write tolerance (``ANG_WRITE_TOL`` for the
        adapter's angle variables, else ``POS_WRITE_TOL``)."""
        items, starts = [], []
        var_item = np.zeros(nx, dtype=np.intp)
        tol = np.full(nx, POS_WRITE_TOL)
        for _u, (it, ad, off) in slots.items():
            n = ad.nvars(it)
            var_item[off:off + n] = len(items)
            for i in ad.angle_vars(it):
                tol[off + i] = ANG_WRITE_TOL
            items.append((it, ad, off, n))
            starts.append(off)
        return items, np.array(starts, dtype=np.intp), var_item, tol

    @staticmethod
    def _collapses(slots, x_old, x_new) -> bool:
        """D29 over every slot (rules in ``_Adapter.collapses``)."""
        for _u, (it, ad, off) in slots.items():
            n = ad.nvars(it)
            if ad.collapses(it, x_old[off:off + n], x_new[off:off + n]):
                return True
        return False

    def _snapshot(self, extra=()) -> dict:
        """``key -> (item, values)`` for every constrained item plus every
        adapter-backed item in *extra* (an edit's own items)."""
        by = self.item_by_uid()
        snap = {u: (by[u], list(adapter_for(by[u]).read(by[u])))
                for u in self.constrained_uids() if u in by}
        for it in extra:
            ad = adapter_for(it)
            key = getattr(it, "_uid", None) or id(it)
            if ad is not None and key not in snap:
                snap[key] = (it, list(ad.read(it)))
        return snap

    @staticmethod
    def _restore(snap) -> None:
        for _u, (it, vals) in (snap or {}).items():
            ad = adapter_for(it)
            if list(ad.read(it)) != vals:
                ad.write(it, np.array(vals, dtype=float))

    def _report_conflict(self, *, reassert: bool = False) -> None:
        """Status-bar conflict message. *reassert*: show it again once the
        caller's commit has finished -- a transform commit posts its own
        success status right after the edit context exits (review M1)."""
        self._status(CONFLICT_STATUS)
        if reassert:
            scene = self._scene
            QTimer.singleShot(0, lambda: None if sip.isdeleted(scene)
                              else self._status(CONFLICT_STATUS))

    def _status(self, msg: str) -> None:
        show = getattr(self._scene, "_show_status", None)
        if callable(show):
            show(msg, 5000)

    def _repaint(self) -> None:
        for v in self._scene.views():
            if not sip.isdeleted(v):
                v.viewport().update()

    # ── D39 tint (MW-12 / H-MW-g) ────────────────────────────────────────
    def tint_color(self, item):
        """D39 state colour for *item*'s canvas stroke (H-MW-g).

        None unless this is the Block Editor with Constraint Status on, the
        item participates (uid known to the diagnostics), is not selected,
        not text and not a ghost (an in-progress / placement preview keeps
        its own colour -- user, 2026-10-06), and no paper pass is live.

        Args:
            item: A scene item about to paint its stroke.

        Returns:
            The state colour, painted by the caller on a painter-local pen
            COPY (never ``setPen``, delta 2) -- a shared cached QColor, so
            callers must not mutate it -- or None for no tint.
        """
        if (not (self.enabled and self.show_status) or item.isSelected()
                or getattr(item, "_ghost_pen", False)
                or getattr(item, "_is_ghost", False)):
            return None
        # TextItem: D39 option b. SplineItem: defensive only -- splines are
        # not in _PARTICIPATING, so their uids never reach the diagnostics.
        if isinstance(item, (TextItem, SplineItem)) or paper_pass_active():
            return None
        u = getattr(item, "_uid", None)
        st = self._tint_states().get(u) if u is not None else None
        if st is None:
            return None
        t = _theme.detect()
        tc = self._tint_colors
        if tc is None or tc[0] is not t:
            tc = self._tint_colors = (t, {s: t.color(k) for s, k in _TINT_TOKEN.items()})
        return tc[1][st]

    def _tint_states(self) -> dict:
        """The D39 state of every participating uid, memoised (delta 5).

        Memoised per frame token / diagnostics result: ``diagnostics()``
        rebuilds its key over every item, so a per-item call would be O(n^2)
        per frame. A newly observed result ``update()``s the (live) items
        whose state changed -- at most one frame stale.

        Returns:
            ``{uid: "free" | "defined" | "conflict"}`` over ``item_dof`` only
            (``SketchDiag.state`` reads unknown uids as "free").
        """
        sc = self._scene
        tok = (self._commit_gen, self._scene_gen, len(self.constraints),
               sum(len(getattr(sc, n, ()) or ()) for n in _PARTICIPATING))
        m = self._tint_memo
        if m is not None and m[0] == tok:
            return m[2]
        d = self.diagnostics()
        if m is not None and m[1] is d:
            self._tint_memo = (tok, d, m[2])
            return m[2]
        states = {u: d.state(u) for u in d.item_dof}
        self._tint_memo = (tok, d, states)
        if m is not None:
            prev = m[2]
            by = self.item_by_uid()
            for u in states.keys() | prev.keys():
                if states.get(u) != prev.get(u):
                    it = by.get(u)
                    if it is not None and not sip.isdeleted(it):
                        it.update()
        return states

    # ── edit seams (§8) ──────────────────────────────────────────────────
    @contextlib.contextmanager
    def edit(self, items, *, typed: bool = False, scale: float | None = None,
             point_map=None):
        """Wrap a typed / panel / transform mutation of *items*.

        The mutated items' new values become ``W_EDIT`` goals and the rest
        re-solves on exit. *typed* (D31 -- the readout and property-panel
        seams only; transforms are not typed): the variables the edit CHANGED
        are pinned at ``W_PIN`` and honoured exactly, the edited item's
        unchanged variables keep ``W_EDIT`` (D6 anchors), other geometry
        yields; if nothing can yield it is a conflict. The rest re-solves on exit — callers push undo AFTER the context exits. An
        empty *items* (e.g. Scale by 1) or untouched items is a pure no-op.
        On failure the WHOLE edit is rolled back (D10) — every adapter-backed
        item in *items*, constrained or not, plus every constrained item — and
        the status bar reports the conflict. The rollback also restores a block
        instance's pose parts that live outside the solver variables
        (rotation, mirrored, scale). *scale* (D54, the Scale tool
        only): every driving dim whose refs all lie inside *items* is
        multiplied by it before the solve and restored on a rollback.
        *point_map* (CS4b D65 -- Rotate / Flip / Scale only): a scene-point
        mapper equal to the tool's transform; every placed dim internal to
        *items* keeps its place by carrying a point on its dim line through it.
        """
        items = list(items)
        scaled = (self._scale_dims(items, scale)
                  if scale is not None and items and self.enabled else [])
        # CS4b D65: anchors before the untouched early exit -- a Reference /
        # suppressed / red dim is not 'active' but still has to follow.
        anchors = (self._dim_anchors(items)
                   if point_map is not None and items and self.enabled else [])
        if not items or not self.enabled or not self.touches(items):
            try:
                yield
            except BaseException:
                for c, v in scaled:
                    c.value = v
                raise
            self._carry_dim_labels(anchors, point_map)
            return
        snap = self._snapshot(items)
        poses = [(it, it.block_rotation(), it.block_mirrored(), it.block_scale())
                 for it in items if hasattr(it, "block_mirrored")]
        flipped = (self._flip_dim_signs(items)
                   if point_map is not None and _is_reflection(point_map) else [])
        try:
            yield
        except BaseException:
            for c, v in scaled:
                c.value = v
            self._unflip_dim_signs(flipped)
            raise
        pins = self._typed_pins(items, snap) if typed else None
        if not self._solve(edited=items, typed=pins):
            self._restore(snap)
            for it, r, mir, sc in poses:   # pose parts outside the solver vars (DD8)
                it.set_block_rotation(r)
                it.set_block_mirrored(mir)
                it.set_block_scale(sc)
            for c, v in scaled:
                c.value = v
            self._unflip_dim_signs(flipped)
            self._report_conflict(reassert=True)
        else:
            self._carry_dim_labels(anchors, point_map)
        self._commit_gen += 1          # diagnostics recompute; no red re-check (D37)

    def _flip_dim_signs(self, items) -> list:
        """D76: negate σ of every angle dim (and ``side`` of every point-line
        dim, D81) internal to *items* -- a reflection mirrors the sector /
        side -- BEFORE the solve, so it keeps its value."""
        uids = {getattr(i, "_uid", None) for i in items} - {None}
        out = []
        for c in self.constraints:
            us = _safe_ref_uids(c)
            if c.inert or not us or not us <= uids:
                continue
            if c.type == "dim_angle" and _angle_helper_ok(c.helper):
                c.helper["sign"] = -c.helper["sign"]
                out.append(c)
            elif (c.type == "dim_point_line" and isinstance(c.helper, dict)
                    and c.helper.get("side") in (1, -1)):
                c.helper["side"] = -c.helper["side"]
                out.append(c)
        return out

    @staticmethod
    def _unflip_dim_signs(flipped) -> None:
        for c in flipped:
            key = "sign" if c.type == "dim_angle" else "side"
            c.helper[key] = -c.helper[key]

    def _dim_anchor(self, c, by, uids):
        """CS4b D65: the scene point mid-way along placed dim *c*'s dim line
        when its refs all lie inside *uids* (no ground refs), else None.
        CS5 D76: a radial dim's anchor is its leader's hit point on the
        curve. A point-line dim is carried like a distance dim (D81)."""
        from . import dim_graphics as dg
        if c.type not in ("dim_distance", "dim_point_line", "dim_radius",
                          "dim_diameter") or c.inert:
            return None
        if c.type in ("dim_radius", "dim_diameter"):
            from .constraint_dims import _radial_points, dim_geom
            lab = c.label if isinstance(c.label, dict) else {}
            ang = lab.get("angle")
            us = _safe_ref_uids(c)
            if (isinstance(ang, bool) or not isinstance(ang, (int, float))
                    or not us or not us <= uids):
                return None
            g = dim_geom(self, c, by)
            return _radial_points(g, float(ang))[0] if g is not None else None
        off = dg.offset_of(c.label)
        us = _safe_ref_uids(c)
        if (off is None or not us or not us <= uids or not isinstance(c.refs, list)
                or any(sm.is_ground(r) for r in c.refs)):
            return None
        e = self.dim_ends(c, by)
        n = dg.unit_normal(*e) if e is not None else None
        if n is None:
            return None
        a, b = e
        return QPointF((a.x() + b.x()) / 2 + n[0] * off,
                       (a.y() + b.y()) / 2 + n[1] * off)

    def _dim_anchors(self, items) -> list:
        """``[(dim, anchor, middle)]`` for the placed dims internal to
        *items* (D65 / CS5 D76), read before a transform: a linear dim's
        dim-line anchor + measured-edge middle; a radial dim's leader hit
        (middle unused, None)."""
        uids = {getattr(i, "_uid", None) for i in items} - {None}
        by = self.item_by_uid()
        out = []
        for c in self.constraints:
            p = self._dim_anchor(c, by, uids)
            if p is None:
                continue
            if c.type in sm.LINEAR_DIMS:
                a, b = self.dim_ends(c, by)
                out.append((c, p, QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)))
            else:
                out.append((c, p, None))
        return out

    def _refit_edge(self, c, target, by) -> None:
        """D65: a single-edge dim moves to the same-measure edge of its item
        (a rect's opposite side, any polygon side, D56) whose middle is
        nearest *target* -- a reflection can swap which handle names the
        mirrored edge, and the dim must keep measuring that edge."""
        from .constraint_dims import measure_key
        refs = c.refs if isinstance(c.refs, list) else []
        if len(refs) != 1 or not isinstance(refs[0], dict) or sm.is_ground(refs[0]):
            return
        uid = refs[0].get("uid")
        it = by.get(uid)
        ad = adapter_for(it) if it is not None else None
        key = measure_key(c, by)
        if ad is None or key is None:
            return
        best, best_d = None, None
        for name in ad.edges(it, 0):
            cand = sm.Constraint.new(c.type, [{"uid": uid, "h": name}])
            if measure_key(cand, by) != key:
                continue
            e = self.dim_ends(cand, by)
            if e is None:
                continue
            m = QPointF((e[0].x() + e[1].x()) / 2, (e[0].y() + e[1].y()) / 2)
            d = math.hypot(m.x() - target.x(), m.y() - target.y())
            if best_d is None or d < best_d:
                best, best_d = name, d
        if best is not None and best != refs[0].get("h"):
            c.refs = [{"uid": uid, "h": best}]

    def _carry_dim_labels(self, anchors, point_map) -> None:
        """Re-fit each anchored linear dim to its mapped edge and re-derive
        its offset from its mapped anchor (D65); re-aim each radial leader at
        its mapped hit point (CS5 D76)."""
        from . import dim_graphics as dg
        from .constraint_dims import dim_geom
        if not anchors:
            return
        by = self.item_by_uid()
        for c, p, m in anchors:
            if c.type not in sm.LINEAR_DIMS:
                g = dim_geom(self, c, by)
                if g is not None:
                    q = point_map(p)
                    c.label = {**(c.label or {}), "angle": math.degrees(math.atan2(
                        -(q.y() - g.centre.y()), q.x() - g.centre.x()))}
                continue
            self._refit_edge(c, point_map(m), by)
            e = self.dim_ends(c, by)
            if e is not None:
                c.label = dg.with_offset(c.label, dg.signed_offset(
                    e[0], e[1], point_map(p)))
        self._label_gen += 1

    def _scale_dims(self, items, factor) -> list:
        """D54: ``[(dim, old value)]`` for the driving dims internal to *items*
        (no ground refs), each multiplied by *factor*."""
        uids = {getattr(i, "_uid", None) for i in items} - {None}
        out = []
        for c in self.constraints:
            if (c.type not in sm.LENGTH_DIMS or c.inert or not c.driving
                    or c.value is None):
                continue
            us = _safe_ref_uids(c)
            if (us and us <= uids and isinstance(c.refs, list)
                    and not any(sm.is_ground(r) for r in c.refs)):
                out.append((c, c.value))
                c.value = c.value * float(factor)
        return out

    @staticmethod
    def _typed_pins(items, snap) -> dict:
        """D31: ``{uid: [local index]}`` of each edited item's variables that
        changed (> 1e-12) against the pre-edit snapshot."""
        pins = {}
        for it in items:
            ad = adapter_for(it)
            u = getattr(it, "_uid", None)
            if ad is None or u not in snap:
                continue
            old = snap[u][1]
            ks = [k for k, (a, b) in enumerate(zip(old, ad.read(it)))
                  if abs(float(b) - float(a)) > 1e-12]
            if ks:
                pins[u] = ks
        return pins

    def _end_session(self) -> None:
        self._drag_snap = self._last_good = self._drag_ctx = None
        self._frame_start = None
        self._drag_cur = self._drag_base = self._drag_layout = None
        self._drag_extra = []

    @property
    def dragging(self) -> bool:
        """Whether a drag session (grip or D35 body drag) is open."""
        return self._drag_snap is not None

    def begin_drag(self, items) -> None:
        """Open a drag session (any stale session is dropped).

        Args:
            items: The grip drag's item, or (D35) a body / resize drag's whole
                selection. No session opens unless one of them is constrained.
        """
        self._end_session()
        items = (list(items) if isinstance(items, (list, tuple, set, frozenset))
                 else [items])
        if not (self.enabled and self.touches(items)):
            return
        self._drag_snap = self._snapshot(items)
        self._drag_ctx = self._build_fresh(self.active())   # never the cached System
        self._drag_base = self._drag_ctx[0].x.copy()
        self._drag_cur = self._drag_base.copy()
        slots = self._drag_ctx[1]
        self._drag_layout = self._slot_layout(slots, len(self._drag_base))
        # Adapter-backed selection items outside the solve (unconstrained):
        # part of last-good so a held conflict holds the whole selection.
        self._drag_extra = [(k, it) for k, (it, _v) in self._drag_snap.items()
                            if k not in slots]
        self._last_good = self._good_state()

    def _good_state(self):
        """Last-good record: the tracked slot values (an array copy -- no
        per-frame rescan or read, D18) plus the body selection's extras."""
        extras = [(k, it, list(adapter_for(it).read(it))) for k, it in self._drag_extra]
        return (self._drag_cur.copy(), extras)

    def drag(self, item, grip_index: int) -> None:
        """One drag frame: *item*'s grip was applied; pin it and re-solve."""
        if self._drag_snap is None:
            return
        self._frame_start = self._last_good     # rewind_frame target (CS3)
        if self._solve(edited=(item,), pin=(item, grip_index), ctx=self._drag_ctx):
            self._last_good = self._good_state()
        else:
            self.hold_last_good()               # D10 hold last good

    def drag_frame(self, items, apply, *, reset: bool = True) -> bool:
        """One D35 body / resize drag frame on the open session.

        Args:
            items: The dragged selection: ``W_EDIT`` goals of the solve (D34
                translate-first applies).
            apply: Zero-arg callable that applies the frame's delta to the
                real geometry (the release bake's own path).
            reset: Restore the moved items to the session snapshot first
                (the rest take the snapshot as their goals, D18), so *apply*
                applies the gesture's TOTAL delta (a body move); False =
                *apply* is incremental (a resize).

        Returns:
            True when solved (written back, now last-good). False = a
            conflict: nothing was written beyond *apply*; the caller undoes
            any non-adapter part of *apply*, then calls :meth:`hold_last_good`.
            Without a session *apply* just runs (True).
        """
        if self._drag_snap is None:
            apply()
            return True
        if reset:                      # only the moved items go back physically (D18)
            keys = {getattr(it, "_uid", None) or id(it) for it in items}
            self._restore({k: v for k, v in self._drag_snap.items() if k in keys})
        apply()
        if self._solve(edited=list(items), ctx=self._drag_ctx, reset=reset):
            self._last_good = self._good_state()
            return True
        return False

    def hold_last_good(self) -> None:
        """D10: restore the session's last good state and report the conflict."""
        self._restore_good(self._last_good)
        self._report_conflict()

    def rewind_frame(self) -> None:
        """Quietly restore the state at the START of the last grip frame
        (before its :meth:`drag` solve) and make it last-good again, so the
        grip can re-apply its own rule at the position the constraints allow
        (CS3 smoke ruling)."""
        start = getattr(self, "_frame_start", None)
        if start is not None:
            self._restore_good(start)
            self._last_good = start

    def _restore_good(self, good) -> None:
        """Write a ``_good_state`` record back to the items."""
        if good is not None:
            cur, extras = good
            snap = {u: (it, list(cur[off:off + ad.nvars(it)]))
                    for u, (it, ad, off) in self._drag_ctx[1].items()}
            snap.update({k: (it, vals) for k, it, vals in extras})
            self._restore(snap)
            self._drag_cur[:] = cur

    def end_drag(self) -> None:
        """Close the drag session (the caller then pushes undo)."""
        self._end_session()
        self._commit_gen += 1

    def cancel_drag(self) -> None:
        """Esc: restore EVERY item the gesture's solves wrote, close the session."""
        if self._drag_snap is not None:
            self._restore(self._drag_snap)
        self._end_session()
        self._commit_gen += 1

    # ── red set (D37/D38) ────────────────────────────────────────────────
    def _try(self, cons) -> bool:
        """Whether *cons* alone is satisfiable from the current geometry
        (D29/D34/D36 rules included). Nothing is written."""
        if not cons:
            return True
        sys_, slots, base = self._build(cons)
        return self._solve_x(sys_, slots, base, None) is not None

    def _admit_in_order(self, cons) -> set:
        """D38: ids of *cons* that cannot join, in list order. Each
        constraint-connected group is tried whole first; only a failing group
        is admitted one constraint at a time."""
        red = set()
        for uids in self._groups(cons):
            group = [c for c in cons if (_safe_ref_uids(c) or set()) & uids]
            if self._try(group):
                continue
            ok = []
            for c in group:
                if self._try(ok + [c]):
                    ok.append(c)
                else:
                    red.add(c.id)
        return red

    def _unsatisfied(self, cons) -> set:
        """Ids of *cons* NOT satisfied by the current (committed) geometry --
        each judged alone, nothing solved or written. Undo restore and paste
        derive red with this (CS2 review I-1): a committed snapshot satisfies
        exactly its live non-red constraints, so this reproduces the live red
        set; a "satisfiable after a solve" test would re-admit a red one that
        a geometry edit made satisfiable WITHOUT applying it."""
        out = set()
        for c in cons:
            sys_, _slots, _w = self._build([c])
            x = sys_.x
            res = [abs(x[i] - x[j]) for i, j, _ in sys_.aliases]
            res += [abs(x[i] - v) for i, v, _ in sys_.fixes]
            res += [abs(row.fn(x)[0]) for row in sys_.rows]
            if res and max(res) > LIN_TOL:
                out.add(c.id)
        return out

    def mark_unsatisfied_red(self, cons) -> set:
        """D38: red-mark each of *cons* the committed geometry violates.

        The live counterpart of the undo-restore derivation (``_unsatisfied``,
        CS2 review I-1): after a commit that moved / created geometry without
        a solve (paste, an LT4-8 Pattern-list ripple), a constraint it leaves
        unsatisfied shows red instead of staying active-unapplied, so the live
        red set equals the one an undo / redo restore derives. Disabled,
        inert and Reference (non-driving dim, F1) constraints are never red.
        Nothing is solved or written.

        Args:
            cons: Candidate constraint records.

        Returns:
            The ids newly or already red among *cons* that are unsatisfied.
        """
        bad = self._unsatisfied(
            [c for c in cons if c.enabled and not c.inert
             and not (c.type in sm.VALUED and not c.driving)])   # F1: Reference never red
        if not bad <= self.red:
            self.red |= bad
            self._commit_gen += 1        # diagnostics key (red changed)
        return bad

    def _recheck_red(self, skip=()) -> None:
        """D37: after a STRUCTURAL commit, each red constraint (list order)
        re-joins if it is satisfiable again -- its solve is written back.
        Never run after a geometry edit (a released drag must not jump)."""
        for c in list(self.constraints):
            if c.id not in self.red or c.id in skip:
                continue
            self.red.discard(c.id)
            if not c.enabled or c.inert:
                continue
            if not self._solve(focus=_safe_ref_uids(c) or set()):
                self.red.add(c.id)

    # ── model ops ────────────────────────────────────────────────────────
    def _sizes_a_text(self, refs) -> bool:
        """CS3c AC6: a dim on a text edge, or between two handles of one
        text, would size the box -- refused until text dims ship."""
        by = self.item_by_uid()
        texts = [r.get("uid") for r in refs if isinstance(r, dict)
                 and isinstance(by.get(r.get("uid")), TextItem)]
        if any(r.get("h") in ("top", "right", "bottom", "left") for r in refs
               if isinstance(r, dict) and r.get("uid") in texts):
            return True
        return len(texts) == 2 and texts[0] == texts[1]

    def add(self, ctype: str, refs: list, *, value: float | None = None,
            label: dict | None = None, helper: dict | None = None):
        """Add a constraint and apply it (D22 least change).

        A dim (``sm.VALUED``) takes *value*, else its current measure
        (D50); two coincident points are refused (status "Pick two separate
        points"); a dim that would be redundant at creation is admitted as
        Reference (D52, status). *label* is a dim's placement record
        (CS4b D62, ``{"offset": mm}``; CS5 D74 ``{"angle": deg}``); None =
        auto. *helper* is the record's helper (D72 angle sector
        ``{"dirs", "sign"}``; D81 point-line ``{"side"}``).

        A conflicting constraint is still admitted (D9) and the geometry holds
        its last good state (D10). Pushes one undo step.

        Returns:
            The new ``Constraint``, or None when refused: a disabled scene, an
            unknown / unbuilt type, or refs that do not validate (unknown uid
            or handle, wrong kind / arity -- status "Invalid constraint").
        """
        spec = sm.REGISTRY.get(ctype)
        if not self.enabled or spec is None or not spec.implemented:
            return None
        if ctype == "dim_distance":
            from .constraint_dims import edge_for_points
            edge = edge_for_points(refs, self.item_by_uid())
            if edge is not None:
                refs = [edge]                   # an edge's own ends == that edge
        c = sm.Constraint.new(ctype, refs)
        if helper is not None:
            c.helper = copy.deepcopy(helper)
        if ctype == "dim_point_line" and helper is None:
            c.helper = {"side": self._point_line_side(c)}
        if ctype in sm.VALUED:
            refusal = self._dim_refusal(c)
            if refusal is not None:
                self._status(refusal)
                return None
            c.value = value if value is not None else self.measure(c)
            if label is not None:
                c.label = copy.deepcopy(label)           # CS4b D62 placement
        if not self._valid(c):
            self._status(INVALID_STATUS)
            return None
        if self._identically_satisfied(c):
            self._status(TRIVIAL_STATUS)
            return None
        self.constraints.append(c)
        ok = self._solve(focus=sm.ref_uids(c))
        if not ok:
            self.red.add(c.id)               # D38: the newcomer is the culprit
        reference = False
        if ok and ctype in sm.VALUED and c.id in self.diagnostics().redundant:
            c.driving = False                # D52: never over-define at creation
            reference = True
        self._committed(skip=(c.id,))
        if not ok:
            self._report_conflict()          # nothing written: hold last good
        elif reference:
            self._status(DIM_REFERENCE_STATUS)
        elif c.id in self.diagnostics().redundant:
            self._status(REDUNDANT_STATUS)   # D42
        return c

    def _point_line_side(self, c) -> int:
        """D81: the ``side`` (±1) whose signed distance (``_on_line``'s
        ``cross(p - a, d)``) the current geometry has; +1 when degenerate."""
        from .constraint_paint import _ref_geom
        e = self.dim_ends(c)
        if e is None:
            return 1
        p = e[1]
        g = _ref_geom(c.refs[1], self.item_by_uid())
        if g is None:
            return 1
        if g[0] == "axis":
            d, o = _AXIS_D[g[1]], QPointF(0.0, 0.0)
        else:
            d = (g[1][1].x() - g[1][0].x(), g[1][1].y() - g[1][0].y())
            o = g[1][0]
        cr = (p.x() - o.x()) * d[1] - (p.y() - o.y()) * d[0]
        return 1 if cr >= 0 else -1

    def delete(self, ids) -> int:
        """Delete constraints by id (geometry untouched); one undo step."""
        ids = set(ids)
        before = len(self.constraints)
        self.constraints = [c for c in self.constraints if c.id not in ids]
        self.red &= {c.id for c in self.constraints}
        if self.selected_id in ids:
            self.selected_id = None
        n = before - len(self.constraints)
        if n:
            self._committed()
        return n

    def set_enabled(self, cid: str, enabled: bool) -> None:
        """Suppress / unsuppress one constraint; re-enabling re-solves it.
        An inert record is read-only (§6.4: kept verbatim) -- a no-op."""
        for c in self.constraints:
            if c.id == cid and c.enabled != enabled and not c.inert:
                c.enabled = enabled
                bad = False
                if enabled:
                    bad = not self._solve(focus=_safe_ref_uids(c) or set())
                    if bad:
                        self.red.add(c.id)       # D38: re-enabling broke it
                else:
                    self.red.discard(c.id)
                self._committed(skip=(c.id,) if bad else ())
                if bad:
                    self._report_conflict()

    # ── dims (CS4, D50-D55) ──────────────────────────────────────────────
    def dim_ends(self, c, by=None, held=None):
        """Scene ``(a, b)`` a distance dim measures (its edge's ends, or its
        two points; the origin counts), else None."""
        from .constraint_paint import _ref_geom
        if not isinstance(c.refs, list):
            return None
        by = self.item_by_uid() if by is None else by
        gs = [_ref_geom(r, by, held) for r in c.refs]
        if len(gs) == 1 and gs[0] is not None and gs[0][0] == "edge":
            return gs[0][1]
        if c.type == "dim_distance" and len(gs) == 2 and all(
                g is not None and g[0] == "point" for g in gs):
            return gs[0][1], gs[1][1]
        if (c.type == "dim_point_line" and len(gs) == 2 and gs[0] is not None
                and gs[0][0] == "point" and gs[1] is not None):
            p = gs[0][1]
            if gs[1][0] == "axis":
                foot = (QPointF(p.x(), 0.0) if gs[1][1] == "x_axis"
                        else QPointF(0.0, p.y()))
                return foot, p
            if gs[1][0] == "edge":
                a, b = gs[1][1]
                dx, dy = b.x() - a.x(), b.y() - a.y()
                L2 = dx * dx + dy * dy
                if L2 < 1e-18:
                    return None
                t = ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / L2
                return QPointF(a.x() + t * dx, a.y() + t * dy), p
        return None

    @staticmethod
    def _edge_len(ref, by) -> float:
        from .constraint_paint import _ref_geom
        g = _ref_geom(ref, by)
        if g is None or g[0] != "edge":
            return math.inf
        a, b = g[1]
        return math.hypot(b.x() - a.x(), b.y() - a.y())

    def _dim_refusal(self, c) -> str | None:
        """The add-time refusal status of dim *c* -- D59 text sizing, a zero
        distance, a D56 repeat -- or None. CS4b D63 runs it before placement."""
        if self._sizes_a_text(c.refs):
            return DIM_TEXT_STATUS
        if c.type == "dim_angle":
            from .constraint_dims import dim_geom
            by = self.item_by_uid()
            if any(isinstance(r, dict) and not sm.is_ground(r)
                   and self._edge_len(r, by) <= DEGEN_EPS for r in c.refs):
                return DIM_ANGLE_ZERO_STATUS
            if dim_geom(self, c, by) is None:
                return INVALID_STATUS        # parallel pairs never get here (D81)
        m = self.measure(c)
        if c.type in sm.LENGTH_DIMS and m is not None and m <= DEGEN_EPS:
            return DIM_COLLINEAR_STATUS if c.type == "dim_point_line" else DIM_ZERO_STATUS
        rep = self._repeats_a_dim(c)
        if rep is not None:                       # D56: one dim per measure
            return (DIM_RECT_REPEAT_STATUS.format(rep[2])
                    if isinstance(rep, tuple) and rep[0] == "rect"
                    else DIM_REPEAT_STATUS)
        return None

    def dim_precheck(self, refs):
        """CS4b D63 / CS5 D69: ``(record type, refs)`` a Smart Dimension pick
        would add (an edge's own ends are that edge, D56; polygon / ellipse
        centre picks become R dims), or None with the refusal status posted
        -- so a refused pick never asks for a placement click."""
        from .constraint_dims import classify_dim, edge_for_points
        by = self.item_by_uid()
        hit = classify_dim(refs, by)
        if hit is None:
            self._status(INVALID_STATUS)
            return None
        ctype, refs = hit
        if ctype == "dim_distance":
            edge = edge_for_points(refs, by)
            if edge is not None:
                refs = [edge]
        c = sm.Constraint.new(ctype, refs)
        if ctype == "dim_angle":
            c.helper = {"dirs": [1, 1], "sign": 1}
        elif ctype == "dim_point_line":
            c.helper = {"side": self._point_line_side(c)}
        refusal = self._dim_refusal(c)
        if refusal is None:
            c.value = self.measure(c)
            if c.value is None or not self._valid(c):
                refusal = INVALID_STATUS
        if refusal is not None:
            self._status(refusal)
            return None
        return ctype, refs

    def _repeats_a_dim(self, c):
        """D56 (smoke ruling 2026-10-03): *c* measures exactly what an
        existing dim already measures (same edge, the edge's own ends, a
        rect's opposite edge, the same two points). A dim merely implied
        through other constraints is not a repeat -- D52 makes it Reference.

        Returns:
            The repeated measure key, or None.
        """
        from .constraint_dims import is_dim, measure_key
        by = self.item_by_uid()
        key = measure_key(c, by)
        if key is None:
            return None
        hit = any(is_dim(d) and d.id != c.id and measure_key(d, by) == key
                  for d in self.constraints)
        return key if hit else None

    def measure(self, c) -> float | None:
        """The geometry's current measure for any dim (mm, or degrees for
        angles; a Ø is twice the radius) -- the Reference text (D52)."""
        from .constraint_dims import angle_value, dim_geom
        g = dim_geom(self, c)
        if g is None:
            return None
        if g.kind == "linear":
            return math.hypot(g.b.x() - g.a.x(), g.b.y() - g.a.y())
        if g.kind == "radial":
            return 2.0 * g.r if c.type == "dim_diameter" else g.r
        if g.kind == "sweep":
            return g.span_deg
        return angle_value(g, c.helper) if _angle_helper_ok(c.helper) else None

    def set_value(self, cid: str, value: float) -> bool:
        """Drive a dim to *value* mm (D53/D55). An edge with a readout moves by
        the readout's typed setter (its D6 anchor law) under D31 exactness;
        otherwise least change. Unhonourable -> nothing changes, conflict
        status, no undo step. True when applied (one undo step)."""
        from .constraint_dims import readout_for
        c = self.find(cid)
        if (c is None or c.inert or c.type not in sm.VALUED or not c.driving
                or not c.enabled):                 # F2: a suppressed dim is read-only
            return False
        try:
            v = float(value)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(v) or v <= 0.0:
            return False
        if v >= sm.VALUE_MAX.get(c.type, math.inf):    # D77: angle range
            return False
        if (c.value is not None and c.id not in self.red
                and math.isclose(v, c.value, rel_tol=1e-12, abs_tol=1e-9)):
            return True                            # F5: unchanged -- no undo step
        hit = (self._angle_apply(c) if c.type == "dim_angle" else
               self._pl_apply(c) if c.type == "dim_point_line" else
               readout_for(self, c))
        old, was_red = c.value, c.id in self.red
        items = [hit[0]] if hit is not None else []
        snap = self._snapshot(items)
        c.value = v
        self.red.discard(c.id)
        try:
            if hit is not None:
                hit[1].apply(v)
                ok = self._solve(edited=items, typed=self._typed_pins(items, snap))
            else:
                ok = self._solve(focus=_safe_ref_uids(c) or set())
        except Exception:                          # F10: never leave a half-applied value
            _log.exception("dim set_value failed")
            ok = False
        if not ok:
            self._restore(snap)
            c.value = old
            if was_red:
                self.red.add(c.id)
            self._commit_gen += 1
            self._report_conflict()
            self._repaint()
            return False
        self._committed()
        return True

    def _angle_apply(self, c):
        """D73: ``(item, spec-like)`` whose ``apply(v)`` rotates the moving
        edge (the second; the edge itself for an edge + axis) about its end
        nearer the vertex so the angle reads *v*, or None (least change) when
        that edge has no raw end."""
        from types import SimpleNamespace
        from .constraint_dims import dim_geom
        by = self.item_by_uid()
        g = dim_geom(self, c, by)
        if g is None or not _angle_helper_ok(c.helper):
            return None
        axis = g.seg2 is None
        mref = c.refs[0] if axis else c.refs[1]
        it = by.get(mref.get("uid"))
        ad = adapter_for(it) if it is not None else None
        if ad is None:
            return None
        ea, eb = ad.edges(it, 0)[mref["h"]]
        if ea.raw is None or eb.raw is None:
            return None
        s1, s2 = (float(s) for s in c.helper["dirs"])
        sign = float(c.helper["sign"])
        V = g.vertex
        fixed = (s2 * g.d2[0], s2 * g.d2[1]) if axis else (s1 * g.d1[0], s1 * g.d1[1])
        sm_ = s1 if axis else s2

        def apply(v):
            th = math.radians(float(v)) * sign * (-1.0 if axis else 1.0)
            fx, fy = fixed
            n = math.hypot(fx, fy)
            ux, uy = fx / n, fy / n
            dx, dy = ux * math.cos(th) - uy * math.sin(th), ux * math.sin(th) + uy * math.cos(th)
            vals = list(ad.read(it))
            pa = (vals[ea.raw[0]], vals[ea.raw[1]]); pb = (vals[eb.raw[0]], vals[eb.raw[1]])
            near_a = math.hypot(pa[0] - V.x(), pa[1] - V.y()) <= math.hypot(pb[0] - V.x(), pb[1] - V.y())
            L = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
            # oriented edge direction (b - a) must equal sm_ * (dx, dy)
            ox, oy = sm_ * dx * L, sm_ * dy * L
            if near_a:
                vals[eb.raw[0]], vals[eb.raw[1]] = pa[0] + ox, pa[1] + oy
            else:
                vals[ea.raw[0]], vals[ea.raw[1]] = pb[0] - ox, pb[1] - oy
            ad.write(it, vals)
        return it, SimpleNamespace(apply=apply)

    def _pl_apply(self, c):
        """D81: translate the second edge (the point's edge; raw ends only)
        along the line's normal so the distance reads *v*; else None."""
        from types import SimpleNamespace
        by = self.item_by_uid()
        pref = c.refs[0]
        it = by.get(pref.get("uid")) if isinstance(pref, dict) else None
        ad = adapter_for(it) if it is not None else None
        if ad is None:
            return None
        h = pref.get("h")
        edge = ("edge" if h == "mid" else
                f"s{h[1:]}" if isinstance(h, str) and h.startswith("m") and h[1:].isdigit()
                else None)
        ends = ad.edges(it, 0).get(edge) if edge else None
        if ends is None or ends[0].raw is None or ends[1].raw is None:
            return None
        e = self.dim_ends(c, by)
        if e is None:
            return None
        foot, p = e
        n = math.hypot(p.x() - foot.x(), p.y() - foot.y())
        if n < 1e-12:
            return None
        ux, uy = (p.x() - foot.x()) / n, (p.y() - foot.y()) / n

        def apply(v):
            dlt = float(v) - n
            vals = list(ad.read(it))
            for r in (ends[0].raw, ends[1].raw):
                vals[r[0]] += ux * dlt
                vals[r[1]] += uy * dlt
            ad.write(it, vals)
        return it, SimpleNamespace(apply=apply)

    def set_dim_kind(self, cid: str, ctype: str) -> bool:
        """D71: switch a circle / arc radial dim between ``dim_radius`` and
        ``dim_diameter`` -- value doubled / halved, placement + geometry kept,
        one undo step. False when *cid* is not such a dim or already *ctype*."""
        from .geometry_2d import ArcItem, CircleItem
        c = self.find(cid)
        if (c is None or c.inert or ctype not in ("dim_radius", "dim_diameter")
                or c.type not in ("dim_radius", "dim_diameter") or c.type == ctype):
            return False
        it = self.item_by_uid().get(c.refs[0].get("uid"))
        if not isinstance(it, (CircleItem, ArcItem)):
            return False
        c.type = ctype
        if c.value is not None:
            c.value = c.value * (2.0 if ctype == "dim_diameter" else 0.5)
        self._label_gen += 1
        self._committed()
        return True

    def can_toggle_kind(self, c) -> bool:
        """D71: a circle / arc radial dim offers Radius / Diameter."""
        from .geometry_2d import ArcItem, CircleItem
        it = self.item_by_uid().get(c.refs[0].get("uid")) if c.refs else None
        return isinstance(it, (CircleItem, ArcItem))

    def open_dim_edit(self, cid: str, view) -> bool:
        """Open the readout HUD on a driving dim (D50/D51); a Reference dim
        posts a hint instead (D52). True when the HUD opened."""
        from .constraint_dims import edit_entry, is_dim
        c = self.find(cid)
        ro = getattr(self._scene, "readouts", None)
        if c is None or not is_dim(c) or ro is None or view is None:
            return False
        if not c.driving:
            self._status(DIM_REFERENCE_HINT)
            return False
        if not c.enabled:                          # F2
            self._status(DIM_SUPPRESSED_HINT)
            return False
        e = edit_entry(view, self, c)
        if e is None:
            return False
        ro.begin_edit(view, e, commit=lambda v, cid=cid: self.set_value(cid, v),
                      key=("dim", cid))
        return True

    def set_driving(self, cid: str, driving: bool) -> None:
        """Driving <-> Reference (D7/D52). Re-driving starts from the current
        length (no jump); one that over-defines goes red / amber per D9."""
        c = self.find(cid)
        driving = bool(driving)
        if (c is None or c.inert or c.type not in sm.VALUED
                or c.driving == driving):
            return
        c.driving = driving
        bad = False
        if driving:
            m = self.measure(c)
            if m is not None and m > 0.0:
                c.value = m
            bad = not self._solve(focus=_safe_ref_uids(c) or set())
            if bad:
                self.red.add(c.id)
        else:
            self.red.discard(c.id)
        self._committed(skip=(c.id,) if bad else ())
        if bad:
            self._report_conflict()
        elif driving and c.id in self.diagnostics().redundant:
            self._status(REDUNDANT_STATUS)

    def on_items_removed(self, items) -> int:
        """Cascade-delete constraints touching removed items (caller pushes undo)."""
        uids = {getattr(i, "_uid", None) for i in items}
        uids.discard(None)
        before = len(self.constraints)
        self.constraints = [c for c in self.constraints
                            if not ((_safe_ref_uids(c) or set()) & uids)]
        if self.selected_id not in {c.id for c in self.constraints}:
            self.selected_id = None
        self.red &= {c.id for c in self.constraints}
        n = before - len(self.constraints)
        if n:                            # structural only when something cascaded
            self._recheck_red()          # (CS2 review I-2; D37)
        self._commit_gen += 1
        return n

    def _committed(self, skip=()) -> None:
        self._recheck_red(skip)          # D37: structural commit re-check
        self._commit_gen += 1
        self._scene.push_undo_state()
        refit = getattr(self._scene, "notify_geometry_edited", None)
        if callable(refit):
            refit()
        self._repaint()
        self._notify_state()
        self._refresh_panel()

    # ── pick mode (D21) ──────────────────────────────────────────────────
    def begin_pick(self, ctype: str) -> None:
        """Start a pick session for *ctype* (status shows the pick count)."""
        if not self.enabled:
            return
        self.pick = PickState(self, ctype)
        self._scene.instructionChanged.emit(self.pick.status())
        self._repaint()

    def cancel_pick(self) -> None:
        """End any pick session (no constraint added)."""
        if self.pick is not None:
            self.pick = None
            self._repaint()

    def pick_hover(self, view, vp_pt) -> None:
        """Mouse move in pick mode: update the hovered handle / edge."""
        p = self.pick
        if p is None:
            return
        if p.pending is not None:                  # CS4b D63: live preview follows
            p.cursor = QPointF(vp_pt)
            self._repaint()
            return
        before = (p.hover_kind, p.hover)
        p.hover_at(view, vp_pt)
        if (p.hover_kind, p.hover) != before:
            self._repaint()

    def pick_press(self, view, vp_pt) -> bool:
        """Accumulate a pick; add the constraint once the arity is met.

        H / V: an edge (only offered before the first point pick) completes
        at once; points accumulate to two. Coincident (CS3): two picks, at
        least one a point; two points add ``coincident``, a point plus an
        edge / curve / axis adds ``point_on_curve`` stored point-first. A
        second pick naming the same handle is refused with the status "Pick a
        different point" (§7.3 Horizontal).

        Returns:
            True when the constraint was added (the session has ended).
        """
        p = self.pick
        if p is None:
            return False
        if p.pending is not None:                  # CS4b D63: the placement click
            return self._place_dim(view, vp_pt)
        ref = p.hover_at(view, vp_pt)
        if ref is None:
            return False
        ctype = p.ctype
        if ctype != "coincident" and p.hover_kind == "edge":
            refs = [ref]
        else:
            if ref in p.picks:
                self._status(PICK_SAME_POINT_STATUS)
                return False
            p.picks.append(ref)
            p.kinds.append(p.hover_kind)
            if len(p.picks) < 2:
                self._scene.instructionChanged.emit(p.status())
                self._repaint()
                return False
            refs = list(p.picks)
            if ctype == "coincident":
                if p.kinds[0] != "point":           # stored point-first (CS3 pin)
                    refs.reverse()
                both_points = p.kinds[0] == p.kinds[1] == "point"
                ctype = "coincident" if both_points else "point_on_curve"
        if ctype == "dim_distance":                # CS4b D63: placement next
            hit = self.dim_precheck(refs)
            if hit is None:
                self.pick = PickState(self, ctype)  # refused: start over, tool live
                self._repaint()
                return False
            p.pending_type, p.pending = hit
            p.cursor = QPointF(vp_pt)
            self._scene.instructionChanged.emit(p.status())
            self._repaint()
            return False
        self.pick = None
        self._scene.set_mode("select")
        self.add(ctype, refs)
        return True

    def _place_dim(self, view, vp_pt) -> bool:
        """D63: store the cursor's offset, add the dim, open the HUD (D50)."""
        from .constraint_dims import placement_for
        p = self.pick
        refs = p.pending
        ctype = p.pending_type or p.ctype
        helper, label = placement_for(self, ctype, refs, _vp_to_scene(view, vp_pt))
        self.pick = PickState(self, p.ctype)       # D50: the tool stays live
        c = self.add(ctype, refs, label=label, helper=helper or None)
        self._scene.instructionChanged.emit(self.pick.status())
        self._repaint()
        if c is not None and c.driving:
            self.open_dim_edit(c.id, view)
        return True

    def begin_dim_placement(self, refs) -> bool:
        """D63: a selected line skips to the placement click. False when
        refused (status posted) or no Smart Dimension session is running."""
        p = self.pick
        if p is None or p.ctype != "dim_distance":
            return False
        hit = self.dim_precheck(refs)
        if hit is None:
            return False
        p.pending_type, p.pending = hit
        self._scene.instructionChanged.emit(p.status())
        self._repaint()
        return True

    def reset_dim_pick(self) -> bool:
        """D63 Esc: drop a half-made dim (picks or a pending placement), keep
        the tool live. False when there was nothing to drop."""
        p = self.pick
        if (p is None or p.ctype != "dim_distance"
                or (not p.picks and p.pending is None)):
            return False
        self.pick = PickState(self, p.ctype)
        self._scene.instructionChanged.emit(self.pick.status())
        self._repaint()
        return True

    # ── dim drag (CS4b D64) ───────────────────────────────────────────────
    def begin_dim_drag(self, cid, vp_pt) -> None:
        """Arm a select-mode drag of dim *cid* (moves only past the drag
        distance, so a click just selects). An arc sweep never moves (D75)."""
        c = self.find(cid)
        if (c is None or c.inert or c.type == "dim_arc_angle"
                or c.type not in sm.VALUED):
            return
        self.dim_drag = [cid, (copy.deepcopy(c.label), copy.deepcopy(c.helper), c.value),
                         QPointF(vp_pt), False]

    def dim_drag_to(self, view, vp_pt) -> bool:
        """Follow the cursor (D64 offset / D72 sector / D74 leader angle).
        True while a drag is armed."""
        from PyQt6.QtWidgets import QApplication
        d = self.dim_drag
        if d is None:
            return False
        if not d[3]:
            if ((QPointF(vp_pt) - d[2]).manhattanLength()
                    < QApplication.startDragDistance()):
                return True
        self.drag_dim_to_scene(d[0], _vp_to_scene(view, vp_pt))
        return True

    def drag_dim_to_scene(self, cid, p) -> bool:
        """The drag update at scene point *p* (headless seam). An angle's new
        sector is re-measured (geometry never moves, D72)."""
        from .constraint_dims import placement_for
        c = self.find(cid)
        if c is None:
            self.dim_drag = None
            return False
        if self.dim_drag is None or self.dim_drag[0] != cid:
            self.begin_dim_drag(cid, QPointF())
            if self.dim_drag is None:
                return False
        self.dim_drag[3] = True
        helper, label = placement_for(self, c.type, c.refs, p)
        if c.type == "dim_angle":
            if helper and helper != c.helper:
                c.helper = helper
                m = self.measure(c)
                if m is not None and c.driving:
                    c.value = m
                self._commit_gen += 1
        elif label is not None:
            c.label = {**(c.label if isinstance(c.label, dict) else {}), **label}
        self._label_gen += 1
        self._repaint()
        return True

    def end_dim_drag(self) -> bool:
        """Release: one undo step when the dim moved. True when a drag was armed."""
        d, self.dim_drag = self.dim_drag, None
        if d is None:
            return False
        if d[3]:
            self._label_gen += 1
            self._scene.push_undo_state()
            self._repaint()
        return True

    def cancel_dim_drag(self) -> bool:
        """Esc mid-drag: restore label / sector / value. True only when a
        moving drag was undone (an armed, unmoved press lets Esc deselect as
        usual)."""
        d, self.dim_drag = self.dim_drag, None
        if d is None or not d[3]:
            return False
        c = self.find(d[0])
        if c is not None:
            c.label, c.helper, c.value = d[1]
        self._label_gen += 1
        self._commit_gen += 1
        self._repaint()
        return True

    def selection_refs(self, ctype: str):
        """D21 selection-first: one selected line / reference line -> ``[edge]``.

        Returns:
            The refs to add, or None when the selection is not valid for it.
        """
        from .geometry_2d import LineItem      # reference lines too (RG1)
        try:
            sel = self._scene.selectedItems()
        except RuntimeError:
            return None
        if (len(sel) == 1 and isinstance(sel[0], LineItem)
                and getattr(sel[0], "_uid", None) is not None):
            return [{"uid": sel[0]._uid, "h": "edge"}]
        return None

    # ── property panel (§10, D11/D27) ────────────────────────────────────
    def ref_text(self, ref, by=None) -> str:
        """Display text for one ref: ``"Line · edge"``, ``"Origin"``,
        ``"X Axis"``; ``"?"`` parts for an unresolvable / malformed ref."""
        if not isinstance(ref, dict):
            return "?"
        if "ref" in ref:
            return str(ref["ref"]).replace("_", " ").title()
        if by is None:
            by = self.item_by_uid()
        it = by.get(ref.get("uid"))
        kind = type(it).__name__.removesuffix("Item") if it is not None else "?"
        return f"{kind} · {ref.get('h', '?')}"

    @staticmethod
    def kind_text(c) -> str:
        """Row / panel name: the type label, or "Unsupported constraint" for
        any inert record (unknown type AND invalid refs, §6.4)."""
        return "Unsupported constraint" if c.inert else c.label_text

    def targets_text(self, c, sep: str, by=None) -> str:
        """Every ref of *c* as :meth:`ref_text`, joined by *sep*."""
        refs = c.refs if isinstance(c.refs, list) else []
        if by is None:
            by = self.item_by_uid()
        return sep.join(self.ref_text(r, by) for r in refs)

    def panel_rows(self, target) -> dict | None:
        """``ActionRowList`` kwargs for the panel's Constraints section, or
        None when *target* has none (a non-editor scene / a gone constraint).

        *target* is a scene item (its constraints, D11) or a
        :class:`ConstraintAdapter` (that one constraint). Inert rows are
        read-only: Delete only, no Suppress (§6.4).
        """
        if not self.enabled:
            return None
        if isinstance(target, ConstraintAdapter):
            c = target.c
            if c is None:
                return None
            cons = [c]
        else:
            cons = self.constraints_on(target)
        from .icons import themed_icon
        from .constraint_paint import _icon_theme
        icon_t = _icon_theme()
        by = self.item_by_uid()
        diag = self.diagnostics()
        rows = []
        for c in cons:
            kind = self.kind_text(c)
            actions = []
            if not c.inert:
                actions.append((
                    "suppress", "●" if c.enabled else "◌",
                    ("Suppress — keep the constraint but don't solve it" if c.enabled
                     else "Unsuppress — solve this constraint again"),
                    lambda _=False, cid=c.id, en=c.enabled: self.set_enabled(cid, not en)))
            actions.append(("delete", "✕", "Delete constraint (Del)",
                            lambda _=False, cid=c.id: self.delete([cid])))
            rows.append(dict(
                # One icon home (sketch_model.icon_for, VC9 F6): an inert row
                # keeps its type's icon (muted), an unknown type the neutral one.
                icon=themed_icon(sm.icon_for(c.type), icon_t),
                text=(self.dim_text(c) if c.type in sm.VALUED and not c.inert
                      else kind),
                subtext=self.targets_text(c, " ↔ ", by),
                muted=not c.enabled or c.inert,
                strike=not c.enabled and not c.inert,
                state=("danger" if c.id in self.red
                       else "warn" if c.id in diag.redundant else ""),
                tooltip=(f"{kind} — click to select" if not c.inert else
                         "Unsupported constraint — kept as saved, never solved"),
                actions=actions,
                on_click=lambda cid=c.id: self.select(cid),
                on_hover=lambda on, cid=c.id: self._hover_row(cid, on)))
        if isinstance(target, ConstraintAdapter):
            footer, fstate = "", ""
        else:            # D41: the element's own state, not the sketch DOF
            footer, fstate = self.item_state_text(getattr(target, "_uid", None))
        return dict(title=f"Constraints · {len(rows)}", rows=rows,
                    footer=footer, footer_state=fstate,
                    empty="No constraints on this entity")

    def dim_text(self, c) -> str:
        """Panel row text of a dim: ``Smart Dimension · 300.0 mm`` /
        ``R 12.5`` / ``Ø 25`` / ``60°`` (a Reference dim: the measure in
        parentheses)."""
        from .scale_manager import ScaleManager
        from .constraint_dims import readout_for
        smgr = getattr(self._scene, "scale_manager", None)
        v = c.value if c.driving else self.measure(c)
        if v is None:
            return c.label_text
        if c.type in sm.ANGLE_DIMS:
            s = ScaleManager.format_span(v)
        else:
            s = smgr.format_length(v) if smgr is not None else f"{v:.1f} mm"
            hit = readout_for(self, c) if c.type != "dim_distance" else None
            if hit is not None and hit[1].prefix:
                s = f"{hit[1].prefix} {s}"
        return f"{c.label_text} · {s if c.driving else f'({s})'}"

    def _hover_row(self, cid, on) -> None:
        """Panel-row hover drives the canvas glow like a glyph hover (D11)."""
        if on:
            self.hover_id = cid
        elif self.hover_id == cid:
            self.hover_id = None
        else:
            return
        self._repaint()

    # ── diagnostics ──────────────────────────────────────────────────────
    def diagnostics(self) -> SketchDiag:
        """Cached on (commit generation, constraint ids/enabled, red ids,
        participating item uids): never recomputed per drag frame (§7.4)."""
        items = self.items()
        key = (self._commit_gen,
               tuple((c.id, c.enabled, c.driving, c.value) for c in self.constraints),
               frozenset(self.red),
               tuple(sorted(str(getattr(i, "_uid", "")) for i in items)))
        if self._diag is not None and self._diag[0] == key:
            return self._diag[1]
        item_dof = {}
        for it in items:
            u = getattr(it, "_uid", None)
            if u is not None:
                item_dof[u] = adapter_for(it).nvars(it)
        total = sum(item_dof.values())
        dof, redundant = total, frozenset()
        cons = self.active()
        if cons:
            sys_, slots, _w = self._build(cons)
            sys_.cid_rank = {c.id: k for k, c in enumerate(cons)}
            d = self._solver.diagnose(sys_)
            redundant = frozenset(d.redundant)
            ordered = list(slots.items())
            dofs = d.dof_of_many([range(off, off + ad.nvars(it))
                                  for _u, (it, ad, off) in ordered])
            for (u, _slot), n in zip(ordered, dofs):
                item_dof[u] = n
            dof = total - (len(sys_.x) - d.dof)
        conflict = frozenset(u for c in self.constraints if c.id in self.red
                             for u in (_safe_ref_uids(c) or ()))
        out = SketchDiag(dof, redundant, item_dof, conflict)
        self._diag = (key, out)
        return out

    def sketch_dof(self) -> int:
        """Sum of participating items' variables minus what constraints remove."""
        return self.diagnostics().dof

    def item_state_text(self, uid) -> tuple[str, str]:
        """D41 element footer: ``(text, state)``."""
        d = self.diagnostics()
        if uid not in d.item_dof:        # non-participating (spline): no state
            return "", ""
        st = d.state(uid)
        if st == "conflict":
            return "Conflicting", st
        if st == "defined":
            return "Fully defined", st
        return f"Under-defined · {d.item_dof.get(uid, 0)} DOF", st

    def sketch_state(self) -> tuple[str, str]:
        """D40 block Status badge: ``(text, state)``. An empty sketch is
        under-defined (0 DOF), never "fully defined"."""
        d = self.diagnostics()
        if self.red:
            return "Over-constrained", "conflict"
        if d.dof == 0 and d.item_dof:
            return "Fully defined", "defined"
        return f"Under-defined · {d.dof} DOF", "free"

    # ── undo / persistence / copy ────────────────────────────────────────
    def capture(self) -> list:
        """Undo snapshot of the constraint list."""
        return [c.to_dict() for c in self.constraints] if self.enabled else []

    def restore(self, records, *, _solvable: bool = False) -> None:
        """Undo restore (items are already rebuilt with their uids).

        Red (D38) is re-derived: a constraint the committed geometry does not
        satisfy is red (review I-1). ``load`` passes ``_solvable`` -- it solves
        right after, so a constraint is red only if it cannot join in list
        order (``_admit_in_order``)."""
        if not self.enabled:
            return
        self._build_cache = None   # items were rebuilt: an id() may be reused
        by = self.item_by_uid()
        self.constraints = [self._adopt(r, by) for r in records or []]
        self.selected_id = self.hover_id = None
        self._end_session()      # a drag context holds the pre-restore items
        self.red = set()
        cons = self.active()
        self.red = (self._admit_in_order(cons) if _solvable
                    else self._unsatisfied(cons))         # D38
        self._commit_gen += 1

    def primitive_uids(self) -> set:
        """Uids of EVERY editor primitive, adapter-backed or not (spline)."""
        out = set()
        for attr in _PRIMITIVE_LISTS:
            out.update(getattr(it, "_uid", None) for it in getattr(self._scene, attr, ()))
        out.discard(None)
        return out

    def to_records(self) -> list:
        """Save: every inert record verbatim (§6.4 -- a newer build's data is
        never lost, whatever it names), plus every solvable record whose uid
        refs resolve against ALL editor primitives."""
        by = self.primitive_uids()
        out = []
        for c in self.constraints:
            uids = _safe_ref_uids(c)
            if c.inert or uids is None or uids <= by:
                out.append(c.to_dict())
        return out

    def load(self, records) -> None:
        """Definition open: adopt the saved records, then the first solve
        (D18 "open = load + first solve"), one constraint-connected group at a
        time so an admitted conflict in one group never blocks another. No
        undo push -- the result is part of the seeded baseline -- and no
        status: a group that fails stays as loaded."""
        self.restore(records, _solvable=True)
        if not self.enabled:
            return
        cons = self.active()
        if not cons:
            return
        sys_, slots, base = self._build(cons)
        for group in self._groups(cons):
            active = self._var_indices(slots, group)
            if not active:
                continue
            x = self._solve_x(sys_, slots, base, active)
            if x is None:
                continue
            self._write(slots, sys_.x, x, uids=group)
            for u in group:
                it, ad, off = slots[u]
                n = ad.nvars(it)
                sys_.x[off:off + n] = x[off:off + n]

    @staticmethod
    def _groups(cons) -> list:
        """Item-uid groups connected through shared constraints."""
        parent: dict = {}

        def find(u):
            while parent.setdefault(u, u) != u:
                parent[u] = parent[parent[u]]
                u = parent[u]
            return u
        for c in cons:
            uids = list(_safe_ref_uids(c) or ())
            for u in uids:
                find(u)
            for u in uids[1:]:
                parent[find(u)] = find(uids[0])
        out: dict = {}
        for u in parent:
            out.setdefault(find(u), set()).add(u)
        return list(out.values())

    def internal_records(self, items) -> list:
        """§8 copy: constraints whose refs all lie inside *items* (no grounds)."""
        uids = {getattr(i, "_uid", None) for i in items}
        uids.discard(None)
        return [c.to_dict() for c in self.constraints
                if not c.inert and c.refs
                and all(isinstance(r, dict) and not sm.is_ground(r)
                        and r.get("uid") in uids for r in c.refs)]

    def paste_records(self, records, uid_map: dict, mirror_axis=None,
                      rotation_deg=None, point_map=None) -> None:
        """Remap copied constraints onto the new items' uids (no undo push).

        Only constraints internal to the copied set survive (§8, via
        ``sm.remap_for_copy``); unreadable records are dropped (they cannot be
        internal) and a remapped record that does not validate on the copies
        is kept verbatim and inert.

        D30 (user, 2026-10-02): a transformed copy keeps a constraint only if
        the transform preserves it. Horizontal and Vertical (D42) survive a
        rotation that is a multiple of 180 deg (+-1e-6) and a reflection
        across a horizontal / vertical axis; any other rotation or mirror axis
        drops them (no H<->V swap), and the copy keeps its transformed
        geometry (it is not re-solved). Translation-only copies keep
        everything. Coincident / point-on-curve are kept under every
        transform (CS3). (The Symmetric rule lands with its session.)

        Args:
            records: ``internal_records`` output (constraint dicts).
            uid_map: Source primitive uid -> new copy's uid.
            mirror_axis: ``(p1, p2)`` QPointFs of a Mirror's axis, else None.
            rotation_deg: The copy's rotation (Polar Array), else None.
            point_map: CS4b D65 (Mirror): the reflection as a scene-point
                mapper; a copied placed dim gets the offset that puts it at
                its source's mirrored place.
        """
        if not self.enabled or not isinstance(records, list) or not records:
            return                              # (clipboard JSON is untrusted)
        cons = []
        for r in records:
            try:
                cons.append(sm.Constraint.from_dict(r))
            except Exception:
                continue
        keep_hv = True
        if mirror_axis is not None:
            p1, p2 = mirror_axis
            ang = math.degrees(math.atan2(p2.y() - p1.y(), p2.x() - p1.x())) % 90.0
            keep_hv = min(ang, 90.0 - ang) <= 1e-6
        if keep_hv and rotation_deg is not None:
            m = float(rotation_deg) % 180.0
            keep_hv = min(m, 180.0 - m) <= 1e-6
        if not keep_hv:
            cons = [c for c in cons if c.type not in ("horizontal", "vertical")]
        by = self.item_by_uid()
        src_uids = set(uid_map)
        new = []
        for src in cons:
            anchor = (self._dim_anchor(src, by, src_uids)
                      if point_map is not None else None)
            if anchor is not None and src.type in sm.LINEAR_DIMS:
                sa, sb = self.dim_ends(src, by)
                mid = QPointF((sa.x() + sb.x()) / 2, (sa.y() + sb.y()) / 2)
            for c in sm.remap_for_copy([src], uid_map):
                if not self._valid(c, by):
                    c.raw, c.invalid = c.to_dict(), True
                elif anchor is not None and src.type in ("dim_radius", "dim_diameter"):
                    from .constraint_dims import dim_geom        # D76: leader mirrored
                    g = dim_geom(self, c, by)
                    if g is not None:
                        q = point_map(anchor)
                        c.label = {**(c.label or {}), "angle": math.degrees(math.atan2(
                            -(q.y() - g.centre.y()), q.x() - g.centre.x()))}
                elif (rotation_deg is not None and point_map is None
                        and src.type in ("dim_radius", "dim_diameter")
                        and isinstance(c.label, dict)
                        and isinstance(c.label.get("angle"), (int, float))
                        and not isinstance(c.label.get("angle"), bool)):
                    # D76: the Polar Array turns the copy by *rotation_deg*
                    # (Y-up CCW, == manip_rotate's argument); so does its leader.
                    c.label = {**c.label, "angle": c.label["angle"] + float(rotation_deg)}
                elif anchor is not None and src.type in sm.LINEAR_DIMS:  # D65
                    from . import dim_graphics as dg
                    self._refit_edge(c, point_map(mid), by)
                    e = self.dim_ends(c, by)
                    if e is not None:
                        c.label = dg.with_offset(c.label, dg.signed_offset(
                            e[0], e[1], point_map(anchor)))
                self.constraints.append(c)
                new.append(c)
        if point_map is not None and _is_reflection(point_map):
            for c in new:                      # D76 / D81: a mirrored copy keeps
                if c.inert:                    # its value on the mirrored sector
                    continue
                if c.type == "dim_angle" and _angle_helper_ok(c.helper):
                    c.helper["sign"] = -c.helper["sign"]
                elif c.type == "dim_point_line" and isinstance(c.helper, dict) \
                        and c.helper.get("side") in (1, -1):
                    c.helper["side"] = -c.helper["side"]
        # D38: a copied constraint the copied geometry does not satisfy (e.g.
        # a source's red one) is red on the copy too -- never active-unapplied
        # (review I-1).
        self.mark_unsatisfied_red(new)
        self._commit_gen += 1


class ConstraintAdapter:
    """Non-item property-panel client for a selected constraint
    (property-panel.md adapter clients; spec §10, D11).

    Holds the constraint's id and re-resolves the record on every call, so an
    undo (which replaces every record) never leaves it pointing at a dead
    object. An inert record (§6.4) exposes no editable field.
    """

    def __init__(self, ctl, c):
        self.ctl = ctl
        self.cid = getattr(c, "id", c)

    @property
    def c(self):
        """The live record, or None once it is gone."""
        return self.ctl.find(self.cid)

    def scene(self):
        return self.ctl._scene

    def get_properties(self) -> dict:
        c = self.c
        if c is None:
            return {}
        props = {"Type": {"type": "label", "value": "Constraint"},
                 "Kind": {"type": "label", "value": self.ctl.kind_text(c)},
                 "Targets": {"type": "label", "value": self.ctl.targets_text(c, ", ")}}
        if not c.inert:
            props["Suppressed"] = {"type": "bool", "value": not c.enabled}
        if not c.inert and c.type in sm.VALUED:          # CS4: Value + Driving (D52)
            smgr = getattr(self.ctl._scene, "scale_manager", None)
            v = c.value if c.driving else self.ctl.measure(c)
            v = float(v) if v is not None else 0.0
            if c.type in sm.ANGLE_DIMS:
                props["Value"] = ({"type": "string", "value": f"{v:.2f}", "suffix": "°"}
                                  if c.driving else {"type": "label", "value": f"({v:.2f}°)"})
            else:
                fmt = smgr.format_length(v) if smgr is not None else f"{v:.1f} mm"
                props["Value"] = ({"type": "dimension", "value": fmt, "value_mm": v,
                                   "minimum": 0.0}
                                  if c.driving else {"type": "label", "value": f"({fmt})"})
            props["Driving"] = {"type": "bool", "value": bool(c.driving)}
            if c.type in ("dim_radius", "dim_diameter") and self.ctl.can_toggle_kind(c):
                props["Show as"] = {"type": "enum", "options": ["Radius", "Diameter"],
                                    "value": "Diameter" if c.type == "dim_diameter" else "Radius"}
        return props

    def set_property(self, key, value) -> None:
        c = self.c
        if key == "Suppressed" and c is not None and not c.inert:
            self.ctl.set_enabled(c.id, not bool(value))
        elif key == "Value" and c is not None:
            try:
                self.ctl.set_value(c.id, float(value))
            except (TypeError, ValueError):
                pass
        elif key == "Driving" and c is not None:
            self.ctl.set_driving(c.id, bool(value))
        elif key == "Show as" and c is not None:
            self.ctl.set_dim_kind(c.id, "dim_diameter" if value == "Diameter"
                                  else "dim_radius")
