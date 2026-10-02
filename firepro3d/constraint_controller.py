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
from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QPen

from . import sketch_model as sm
from .sketch_adapters import adapter_for
from .sketch_solver import BUILDERS, NumpySolver, System, W_EDIT, W_PIN, const_point
from .theme import M

# Model_Space tracking lists whose items can carry constraints (§5.1).
_PARTICIPATING = ("_draw_lines", "_reference_lines", "_draw_rects", "_draw_circles",
                  "_draw_arcs", "_draw_ellipses", "_polylines", "_draw_polygons",
                  "_texts", "_block_instances")
_log = logging.getLogger(__name__)
CONFLICT_STATUS = "Over-constrained: the change was not applied"
INVALID_STATUS = "Invalid constraint"
REDUNDANT_STATUS = "Redundant constraint: already implied by others"   # D42
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


def _safe_ref_uids(c) -> set | None:
    """``sm.ref_uids`` that tolerates a malformed (inert, newer-build) record.

    Returns:
        The referenced uids, or None when a ref has neither ``ref`` nor ``uid``.
    """
    try:
        return sm.ref_uids(c)
    except (KeyError, TypeError):
        return None


PICK_SAME_POINT_STATUS = "Pick a different point"


def _xy(p) -> tuple[float, float]:
    return (p.x(), p.y())


def _seg_dist(p, a, b) -> float:
    """Distance from *p* to segment *ab* (all viewport px)."""
    ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p.x() - ax) * dx + (p.y() - ay) * dy) / L2))
    return math.hypot(p.x() - ax - t * dx, p.y() - ay - t * dy)


class PickState:
    """D21 hover-marker pick mode for one constraint type.

    Every participating primitive's §5.1 point handles (and the origin) show
    as hollow square markers; the hover is the nearest point within
    ``CONSTRAINT_PICK_POINT_TOL_PX`` or — before the first point pick — the
    nearest edge within ``CONSTRAINT_PICK_EDGE_TOL_PX`` (viewport px).
    """

    def __init__(self, ctl, ctype: str):
        self.ctl, self.ctype = ctl, ctype
        self.picks: list[dict] = []
        self.hover: dict | None = None
        self.hover_kind: str | None = None      # "point" / "edge"

    def _candidates(self):
        """``(kind, ref, a, b)`` scene-space; ``b`` is None for a point."""
        for it in self.ctl.items():
            uid = getattr(it, "_uid", None)
            if uid is None:
                continue
            ad = adapter_for(it)
            x = np.array(ad.read(it), dtype=float)
            for name, e in ad.points(it, 0).items():
                yield "point", {"uid": uid, "h": name}, QPointF(*e.eval(x)[0]), None
            for name, (a, b) in ad.edges(it, 0).items():
                yield ("edge", {"uid": uid, "h": name},
                       QPointF(*a.eval(x)[0]), QPointF(*b.eval(x)[0]))
        yield "point", {"ref": "origin"}, QPointF(0.0, 0.0), None

    def hover_at(self, view, vp_pt) -> dict | None:
        """Nearest point within tol; else (no picks yet) nearest edge."""
        cands = list(self._candidates())
        best = None
        for kind, ref, a, _b in cands:
            if kind != "point":
                continue
            d = math.dist(_xy(vp_pt), _xy(view.mapFromScene(a)))
            if d <= M.CONSTRAINT_PICK_POINT_TOL_PX and (best is None or d < best[0]):
                best = (d, ref, kind)
        if best is None and not self.picks:
            for kind, ref, a, b in cands:
                if kind != "edge":
                    continue
                d = _seg_dist(vp_pt, view.mapFromScene(a), view.mapFromScene(b))
                if d <= M.CONSTRAINT_PICK_EDGE_TOL_PX and (best is None or d < best[0]):
                    best = (d, ref, kind)
        self.hover = best[1] if best else None
        self.hover_kind = best[2] if best else None
        return self.hover

    def status(self) -> str:
        label = sm.REGISTRY[self.ctype].label
        return f"{label}: pick 2 points or 1 edge ({len(self.picks)}/2) · Esc to cancel"

    def paint(self, painter, view, t) -> None:
        """Hover-edge glow, then the markers: hollow ``muted`` squares, filled
        ``accent`` for the hovered (enlarged) and already-picked handles."""
        half = M.CONSTRAINT_PICK_MARKER_HALF_PX
        cands = list(self._candidates())
        for kind, ref, a, b in cands:
            if kind == "edge" and ref == self.hover:
                pen = QPen(t.color("accent", M.CONSTRAINT_PICK_EDGE_GLOW_ALPHA),
                           M.CONSTRAINT_PICK_EDGE_GLOW_W_PX)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(QPointF(view.mapFromScene(a)), QPointF(view.mapFromScene(b)))
        for kind, ref, a, _b in cands:
            if kind != "point":
                continue
            hov = ref == self.hover
            on = hov or ref in self.picks
            s = half + (1.5 if hov else 0.0)
            p = QPointF(view.mapFromScene(a))
            painter.setPen(QPen(t.color("accent" if on else "muted"), 1.3))
            painter.setBrush(t.color("accent" if on else "surface"))
            painter.drawRect(QRectF(p.x() - s, p.y() - s, 2 * s, 2 * s))


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
        # Per-frame glyph-layout cache tokens (constraint_paint._frame, VC9 F3):
        # bumped on every scene change / item-selection change.
        self._scene_gen = 0
        self._sel_gen = 0
        self._frames: dict = {}                # id(view) -> (key, _Frame)
        self._drag_extra: list = []            # body-drag selection items outside the ctx
        # Zero-arg callbacks run when the constraint selection / list changes
        # (the ribbon's Delete Constraints enable state, main.py).
        self.state_listeners: list = []
        self._solver = NumpySolver()
        self._drag_snap = None
        self._last_good = None
        self._drag_ctx = None
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
            if not c.enabled or c.inert or c.id in self.red:
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
        kinds = tuple(self._ref_kind(r, by) for r in c.refs)
        return None not in kinds and kinds in spec.patterns

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
            BUILDERS[c.type](c.id, self._ends(c, slots), sys_)
        return sys_, slots, np.array(w, dtype=float)

    def _resolve(self, ref, slots):
        if sm.is_ground(ref):
            if ref["ref"] == "origin":
                return const_point(0.0, 0.0)
            raise ValueError(f"ground {ref['ref']!r} is not a point")
        it, ad, off = slots[ref["uid"]]
        pts = ad.points(it, off)
        return pts[ref["h"]] if ref["h"] in pts else ad.edges(it, off)[ref["h"]]

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
               typed=None) -> bool:
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
            for _u, (it, ad, off) in slots.items():
                sys_.x[off:off + ad.nvars(it)] = ad.read(it)
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
        self._write(slots, sys_.x, x)
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

    # ── edit seams (§8) ──────────────────────────────────────────────────
    @contextlib.contextmanager
    def edit(self, items, *, typed: bool = False):
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
        the status bar reports the conflict.
        """
        items = list(items)
        if not items or not self.enabled or not self.touches(items):
            yield
            return
        snap = self._snapshot(items)
        yield
        pins = self._typed_pins(items, snap) if typed else None
        if not self._solve(edited=items, typed=pins):
            self._restore(snap)
            self._report_conflict(reassert=True)
        self._commit_gen += 1          # diagnostics recompute; no red re-check (D37)

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
        self._drag_ctx = self._build(self.active())
        slots = self._drag_ctx[1]
        # Adapter-backed selection items outside the solve (unconstrained):
        # part of last-good so a held conflict holds the whole selection.
        self._drag_extra = [(k, it) for k, (it, _v) in self._drag_snap.items()
                            if k not in slots]
        self._last_good = self._good_state()

    def _good_state(self) -> dict:
        """Current values of the session's items. From the cached slots (=
        every constrained item) plus the body selection's extras: no per-frame
        rescan of the scene lists (D18 drag bar)."""
        good = {u: (it, list(ad.read(it)))
                for u, (it, ad, _off) in self._drag_ctx[1].items()}
        for k, it in self._drag_extra:
            good[k] = (it, list(adapter_for(it).read(it)))
        return good

    def drag(self, item, grip_index: int) -> None:
        """One drag frame: *item*'s grip was applied; pin it and re-solve."""
        if self._drag_snap is None:
            return
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
            reset: Restore the session snapshot first, so *apply* applies the
                gesture's TOTAL delta (a body move); False = *apply* is
                incremental (a resize).

        Returns:
            True when solved (written back, now last-good). False = a
            conflict: nothing was written beyond *apply*; the caller undoes
            any non-adapter part of *apply*, then calls :meth:`hold_last_good`.
            Without a session *apply* just runs (True).
        """
        if self._drag_snap is None:
            apply()
            return True
        if reset:
            self._restore(self._drag_snap)
        apply()
        if self._solve(edited=list(items), ctx=self._drag_ctx):
            self._last_good = self._good_state()
            return True
        return False

    def hold_last_good(self) -> None:
        """D10: restore the session's last good state and report the conflict."""
        self._restore(self._last_good)
        self._report_conflict()

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
    def add(self, ctype: str, refs: list):
        """Add a constraint and apply it (D22 least change).

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
        c = sm.Constraint.new(ctype, refs)
        if not self._valid(c):
            self._status(INVALID_STATUS)
            return None
        self.constraints.append(c)
        ok = self._solve(focus=sm.ref_uids(c))
        if not ok:
            self.red.add(c.id)               # D38: the newcomer is the culprit
        self._committed(skip=(c.id,))
        if not ok:
            self._report_conflict()          # nothing written: hold last good
        elif c.id in self.diagnostics().redundant:
            self._status(REDUNDANT_STATUS)   # D42
        return c

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
        self._recheck_red()              # structural: a partner may be gone (D37)
        self._commit_gen += 1
        return before - len(self.constraints)

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
        before = (p.hover_kind, p.hover)
        p.hover_at(view, vp_pt)
        if (p.hover_kind, p.hover) != before:
            self._repaint()

    def pick_press(self, view, vp_pt) -> bool:
        """Accumulate a pick; add the constraint once the arity is met.

        An edge (only offered before the first point pick) completes at once;
        points accumulate to two. A second pick naming the same handle is
        refused with the status "Pick a different point" (§7.3 Horizontal).

        Returns:
            True when the constraint was added (the session has ended).
        """
        p = self.pick
        if p is None:
            return False
        ref = p.hover_at(view, vp_pt)
        if ref is None:
            return False
        if p.hover_kind == "edge":
            refs = [ref]
        else:
            if ref in p.picks:
                self._status(PICK_SAME_POINT_STATUS)
                return False
            p.picks.append(ref)
            if len(p.picks) < 2:
                self._scene.instructionChanged.emit(p.status())
                self._repaint()
                return False
            refs = list(p.picks)
        ctype = p.ctype
        self.pick = None
        self._scene.set_mode("select")
        self.add(ctype, refs)
        return True

    def selection_refs(self, ctype: str):
        """D21 selection-first: one selected line / reference line -> ``[edge]``.

        Returns:
            The refs to add, or None when the selection is not valid for it.
        """
        from .geometry_2d import LineItem      # covers ReferenceLineItem
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
                text=kind,
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
               tuple((c.id, c.enabled) for c in self.constraints),
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
            for u, (it, ad, off) in slots.items():
                item_dof[u] = d.dof_of(range(off, off + ad.nvars(it)))
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

    def restore(self, records) -> None:
        """Undo restore (items are already rebuilt with their uids)."""
        if not self.enabled:
            return
        by = self.item_by_uid()
        self.constraints = [self._adopt(r, by) for r in records or []]
        self.selected_id = self.hover_id = None
        self._end_session()      # a drag context holds the pre-restore items
        self.red = set()
        self.red = self._admit_in_order(self.active())   # D38, list order
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
        self.restore(records)
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
                      rotation_deg=None) -> None:
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
        everything. (The Symmetric rule lands with its session.)

        Args:
            records: ``internal_records`` output (constraint dicts).
            uid_map: Source primitive uid -> new copy's uid.
            mirror_axis: ``(p1, p2)`` QPointFs of a Mirror's axis, else None.
            rotation_deg: The copy's rotation (Polar Array), else None.
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
        new = []
        for c in sm.remap_for_copy(cons, uid_map):
            if not self._valid(c, by):
                c.raw, c.invalid = c.to_dict(), True
            self.constraints.append(c)
            new.append(c)
        # D38: a copied constraint that cannot join (e.g. a source's red one)
        # is red on the copy too.
        self.red |= self._admit_in_order(
            [c for c in new if c.enabled and not c.inert])
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
        return props

    def set_property(self, key, value) -> None:
        c = self.c
        if key == "Suppressed" and c is not None and not c.inert:
            self.ctl.set_enabled(c.id, not bool(value))
