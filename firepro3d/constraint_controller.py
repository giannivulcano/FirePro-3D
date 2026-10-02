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

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import QTimer

from . import sketch_model as sm
from .sketch_adapters import adapter_for
from .sketch_solver import BUILDERS, NumpySolver, System, W_EDIT, W_PIN, const_point

# Model_Space tracking lists whose items can carry constraints (§5.1).
_PARTICIPATING = ("_draw_lines", "_reference_lines", "_draw_rects", "_draw_circles",
                  "_draw_arcs", "_draw_ellipses", "_polylines", "_draw_polygons",
                  "_texts", "_block_instances")
_log = logging.getLogger(__name__)
CONFLICT_STATUS = "Over-constrained: the change was not applied"
INVALID_STATUS = "Invalid constraint"


def _safe_ref_uids(c) -> set | None:
    """``sm.ref_uids`` that tolerates a malformed (inert, newer-build) record.

    Returns:
        The referenced uids, or None when a ref has neither ``ref`` nor ``uid``.
    """
    try:
        return sm.ref_uids(c)
    except (KeyError, TypeError):
        return None


class ConstraintController:
    """Owns the editor's constraint list and every solve seam (spec §3, §8)."""

    def __init__(self, scene):
        self._scene = scene
        self.enabled = getattr(scene, "scene_role", "plan") == "block_editor"
        self.constraints: list[sm.Constraint] = []
        self.selected_id: str | None = None
        self.hover_id: str | None = None
        self.show_glyphs = True
        self.pick = None                       # PickState (Task 12)
        self._solver = NumpySolver()
        self._drag_snap = None
        self._last_good = None
        self._drag_ctx = None

    def reset(self) -> None:
        """New / Open: drop every constraint and all transient state."""
        self.constraints = []
        self.selected_id = self.hover_id = None
        self.pick = None
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
        """Solvable constraints: enabled, built and valid (not inert), refs resolve."""
        by = set(self.item_by_uid())
        out = []
        for c in self.constraints:
            if not c.enabled or c.inert:
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
        try:                                    # two refs naming one handle (§7.3)
            if len({repr(sorted(r.items())) for r in c.refs}) != len(c.refs):
                return False
        except AttributeError:                  # a ref that is not a dict
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
    def _solve(self, *, edited=(), pin=None, ctx=None, focus=None) -> bool:
        """One solve + write-back.

        Args:
            edited: Items whose current values are goals at ``W_EDIT``.
            pin: ``(item, grip_index)`` — the drag's grabbed handle, ``W_PIN``.
            ctx: A cached ``(sys, slots, base_weights)`` from :meth:`begin_drag`:
                the System structure is reused across drag frames (only x is
                refreshed) — the D18 8 ms drag bar depends on it.
            focus: Uids whose components must be solved (a new or re-enabled
                constraint's items). ``None`` = no focus given.

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
        for u in edited_uids:
            slot = slots.get(u)
            if slot is not None:
                it, ad, off = slot
                weights[off:off + ad.nvars(it)] *= W_EDIT
        if pin is not None:
            item, grip = pin
            slot = slots.get(getattr(item, "_uid", None))
            if slot is not None:
                for k in slot[1].pin_vars(item, grip):
                    weights[slot[2] + k] *= W_PIN
        if edited or focus is not None:
            active = self._var_indices(slots, edited_uids | set(focus or ()))
            if not active:
                return True                     # nothing of ours to solve
        else:
            active = None
        x = self._solve_x(sys_, slots, weights, active)
        if x is None:
            return False
        self._write(slots, sys_.x, x)
        return True

    def _solve_x(self, sys_, slots, weights, active):
        """The solved full-space x, or None (not converged / D29 collapse)."""
        res = self._solver.solve(sys_, sys_.x.copy(), weights, active=active)
        if not res.converged:
            return None
        # D29: a solve that can only be satisfied by collapsing a shape is a CONFLICT.
        if self._collapses(slots, sys_.x, res.x):
            # The least-change answer collapsed a shape; retry with every size
            # variable stiff (W_PIN) so a non-collapsing answer (e.g. a rotate)
            # wins if one exists. Still collapsing / unsolved -> conflict.
            stiff = weights.copy()
            for _u, (it, ad, off) in slots.items():
                for i in ad.size_floors(it):
                    stiff[off + i] *= W_PIN
            res = self._solver.solve(sys_, sys_.x.copy(), stiff, active=active)
            if not res.converged or self._collapses(slots, sys_.x, res.x):
                return None
        return res.x

    @staticmethod
    def _write(slots, x_old, x_new, uids=None) -> None:
        """Exactly one write-back per changed item (§3)."""
        for u, (it, ad, off) in slots.items():
            if uids is not None and u not in uids:
                continue
            n = ad.nvars(it)
            new = x_new[off:off + n]
            if float(np.max(np.abs(new - x_old[off:off + n]))) > 1e-12:
                ad.write(it, new)

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
            v.viewport().update()

    # ── edit seams (§8) ──────────────────────────────────────────────────
    @contextlib.contextmanager
    def edit(self, items):
        """Wrap a typed / panel / transform mutation of *items*.

        The mutated items' new values become ``W_EDIT`` goals and the rest
        re-solves on exit — callers push undo AFTER the context exits. An
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
        if not self._solve(edited=items):
            self._restore(snap)
            self._report_conflict(reassert=True)

    def _end_session(self) -> None:
        self._drag_snap = self._last_good = self._drag_ctx = None

    def begin_drag(self, item) -> None:
        """Open a grip-drag session on *item* (any stale session is dropped)."""
        self._end_session()
        if not (self.enabled and self.touches([item])):
            return
        self._drag_snap = self._snapshot()
        self._last_good = self._drag_snap
        self._drag_ctx = self._build(self.active())

    def drag(self, item, grip_index: int) -> None:
        """One drag frame: *item*'s grip was applied; pin it and re-solve."""
        if self._drag_snap is None:
            return
        if self._solve(edited=(item,), pin=(item, grip_index), ctx=self._drag_ctx):
            # From the cached slots (= every constrained item): no per-frame
            # rescan of the scene lists (D18 drag bar).
            self._last_good = {u: (it, list(ad.read(it)))
                               for u, (it, ad, _off) in self._drag_ctx[1].items()}
        else:
            self._restore(self._last_good)      # D10 hold last good
            self._report_conflict()

    def end_drag(self) -> None:
        """Close the drag session (the caller then pushes undo)."""
        self._end_session()

    def cancel_drag(self) -> None:
        """Esc: restore EVERY item the gesture's solves wrote, close the session."""
        if self._drag_snap is not None:
            self._restore(self._drag_snap)
        self._end_session()

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
        if not self._solve(focus=sm.ref_uids(c)):
            self._report_conflict()          # nothing written: hold last good
        self._committed()
        return c

    def delete(self, ids) -> int:
        """Delete constraints by id (geometry untouched); one undo step."""
        ids = set(ids)
        before = len(self.constraints)
        self.constraints = [c for c in self.constraints if c.id not in ids]
        if self.selected_id in ids:
            self.selected_id = None
        n = before - len(self.constraints)
        if n:
            self._committed()
        return n

    def set_enabled(self, cid: str, enabled: bool) -> None:
        """Suppress / unsuppress one constraint; re-enabling re-solves it."""
        for c in self.constraints:
            if c.id == cid and c.enabled != enabled:
                c.enabled = enabled
                if (enabled and not c.inert
                        and not self._solve(focus=_safe_ref_uids(c) or set())):
                    self._report_conflict()
                self._committed()

    def on_items_removed(self, items) -> int:
        """Cascade-delete constraints touching removed items (caller pushes undo)."""
        uids = {getattr(i, "_uid", None) for i in items}
        uids.discard(None)
        before = len(self.constraints)
        self.constraints = [c for c in self.constraints
                            if not ((_safe_ref_uids(c) or set()) & uids)]
        if self.selected_id not in {c.id for c in self.constraints}:
            self.selected_id = None
        return before - len(self.constraints)

    def _committed(self) -> None:
        self._scene.push_undo_state()
        refit = getattr(self._scene, "notify_geometry_edited", None)
        if callable(refit):
            refit()
        self._repaint()

    # ── diagnostics ──────────────────────────────────────────────────────
    def sketch_dof(self) -> int:
        """Sum of participating items' variables minus what constraints remove."""
        total = sum(adapter_for(it).nvars(it) for it in self.items())
        cons = self.active()
        if not cons:
            return total
        sys_, _slots, _w = self._build(cons)
        return total - (len(sys_.x) - self._solver.diagnose(sys_).dof)

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

    def to_records(self) -> list:
        """Save: every constraint whose uid refs resolve (inert ones verbatim)."""
        by = set(self.item_by_uid())
        out = []
        for c in self.constraints:
            uids = _safe_ref_uids(c)
            if uids is None or uids <= by:   # unparseable inert refs: keep verbatim
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
        the transform preserves it. Horizontal survives a rotation that is a
        multiple of 180 deg (+-1e-6) and a reflection across a horizontal /
        vertical axis; any other rotation or mirror axis drops it, and the
        copy keeps its transformed geometry (it is not re-solved).
        Translation-only copies keep everything. (Vertical / Symmetric rules
        land with their sessions.)

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
        keep_h = True
        if mirror_axis is not None:
            p1, p2 = mirror_axis
            ang = math.degrees(math.atan2(p2.y() - p1.y(), p2.x() - p1.x())) % 90.0
            keep_h = min(ang, 90.0 - ang) <= 1e-6
        if keep_h and rotation_deg is not None:
            m = float(rotation_deg) % 180.0
            keep_h = min(m, 180.0 - m) <= 1e-6
        if not keep_h:
            cons = [c for c in cons if c.type != "horizontal"]
        by = self.item_by_uid()
        for c in sm.remap_for_copy(cons, uid_map):
            if not self._valid(c, by):
                c.raw, c.invalid = c.to_dict(), True
            self.constraints.append(c)
