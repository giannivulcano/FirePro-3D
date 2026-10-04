"""Selection dimension readouts (2d-geometry.md §8, selection-mode.md §15).

A readout is a transient, painted record — never a QGraphicsItem and never a
child of its primitive. Primitives describe their dimensions via
``dimension_specs() -> list[DimSpec]``; ``SelectionReadoutController`` turns
the live selection into painted, pickable, editable labels.
"""
from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass
from typing import Callable

from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRect, QRectF


@dataclass(frozen=True)
class DimSpec:
    """One dimension a primitive reports.

    Attributes:
        kind: ``"linear"`` or ``"angular"``.
        key: Stable id within the item (``"length"``, ``"seg:2"``,
            ``"ang:1"``) — survives rebuilds mid-drag.
        field: HUD field label (``"Length"``, ``"R1"``, ``"Angle 2"``).
        prefix: Label prefix (``""``, ``"R"``, ``"R1"``, ``"R2"``).
        value: mm (linear) or degrees (angular).
        field_kind: ``"dimension"`` (length, mm) or ``"span"`` (degrees).
        apply: Pure setter taking one float — no undo (caller owns undo).
        minimum: Accepted values are strictly greater than this.
        maximum: Accepted values are <= this (None = unbounded).
        a, b: Linear endpoints (scene coords).
        away: Linear label goes to the side of a→b away from this point
            (None = prefer screen-up / screen-left).
        center: Angular vertex (scene coords).
        ref_radius: Angular leg length (scene); the reference arc radius is
            a fraction of it and the label hides if the arc would exceed it.
        start_deg, span_deg: Angular sweep, Y-up degrees CCW from +x.
    """
    kind: str
    key: str
    field: str
    prefix: str
    value: float
    field_kind: str
    apply: Callable[[float], None]
    minimum: float = 0.0
    maximum: float | None = None
    a: QPointF | None = None
    b: QPointF | None = None
    away: QPointF | None = None
    center: QPointF | None = None
    ref_radius: float = 0.0
    start_deg: float = 0.0
    span_deg: float = 0.0


def readout_text(spec: DimSpec, scale_manager) -> str:
    """Display string for *spec*: prefix + unit-formatted value."""
    from .scale_manager import ScaleManager
    if spec.field_kind == "span":
        body = ScaleManager.format_span(spec.value)
    elif scale_manager is not None:
        body = scale_manager.format_length(spec.value)
    else:
        body = f"{spec.value:.1f} mm"
    return f"{spec.prefix} {body}" if spec.prefix else body


def map_spec(spec: DimSpec, t) -> DimSpec:
    """*spec* as drawn under the scene-space ``QTransform`` *t*.

    Pure. Linear: endpoints (and ``away``) map; ``value`` scales with the
    mapped a→b length. Angular: the centre and both legs map, the sweep is
    re-measured (a mirroring *t* reverses its direction) and ``value`` follows
    the span; ``ref_radius`` scales with the start leg.
    """
    from dataclasses import replace

    def m(p):
        return None if p is None else t.map(QPointF(p))

    if spec.kind == "linear":
        a, b = m(spec.a), m(spec.b)
        value = spec.value
        if spec.a is not None and spec.b is not None:
            d0 = math.hypot(spec.b.x() - spec.a.x(), spec.b.y() - spec.a.y())
            if d0 > 0:
                value = spec.value * math.hypot(b.x() - a.x(), b.y() - a.y()) / d0
        return replace(spec, a=a, b=b, away=m(spec.away), value=value)

    if spec.center is None:
        return spec
    from .arc_math import point_at, yup_angle
    c0, r0 = spec.center, spec.ref_radius or 1.0
    c = m(c0)
    p_start = m(point_at(c0, r0, spec.start_deg))
    p_end = m(point_at(c0, r0, spec.start_deg + spec.span_deg))
    start = yup_angle(c, p_start)
    sweep = (yup_angle(c, p_end) - start) % 360.0          # CCW, [0, 360)
    ccw = spec.span_deg >= 0
    if t.determinant() < 0:                                 # mirrored
        ccw = not ccw
    if sweep == 0.0 and spec.span_deg != 0.0:
        sweep = 360.0
    span = sweep if ccw else sweep - 360.0
    value = span if math.isclose(spec.value, spec.span_deg) else spec.value
    ref = (math.hypot(p_start.x() - c.x(), p_start.y() - c.y())
           if spec.ref_radius else spec.ref_radius)
    return replace(spec, center=c, start_deg=start, span_deg=span,
                   value=value, ref_radius=ref)


@dataclass
class ReadoutEntry:
    """A spec bound to its item and laid out for one view.

    Attributes:
        item: The selected primitive that reported ``spec``.
        spec: The dimension being displayed.
        layout: ``readout_paint.ReadoutLayout`` in that view's viewport px.
    """
    item: object
    spec: DimSpec
    layout: object


@dataclass
class _EditSession:
    """One open readout edit (selection-mode §15 input mode).

    Attributes:
        view: The ``Model_View`` whose viewport parents the HUD.
        hud: The one-field ``DynamicInputHud``.
        item: The primitive being edited.
        spec: The dimension being edited (its ``apply`` is the setter).
        key: ``(id(item), spec.key)`` — the label hidden while editing.
        kind: The ``FieldKind`` of the HUD's single field.
    """
    view: object
    hud: object
    item: object
    spec: DimSpec
    key: tuple
    kind: object
    commit: object = None       # CS4: a dim edit drives its constraint instead


class SelectionReadoutController:
    """Owns selection dimension readouts on one Model_Space (selection-mode §15).

    Stateless between frames: ``entries()`` re-reads the live selection on
    every call, so geometry changes need no notification, only repaints.
    Readouts are painted overlay records, never ``QGraphicsItem``s.
    """

    # D57 (smoke ruling 2026-10-03): Smart Dimension owns edge lengths in the
    # Block Editor, so the transient length / width / height / segment
    # readouts are off; angular + radius readouts stay until CS5. The
    # readout machinery itself is unchanged (its tests opt back in).
    show_edge_lengths = False

    def __init__(self, scene):
        self._scene = scene
        self._hover = None            # (id(item), key) or None
        self._edit = None             # edit session (Task 11) or None
        # Last instruction-line text emitted by anyone else on this scene —
        # restored when the cursor leaves a label (hover replaces it).
        self._last_instruction = ""
        self._emitting = False
        # id(view) -> viewport-px rect of everything painted there last frame
        # (the "old" half of the scene-change dirty region).
        self._painted: dict[int, QRect] = {}
        # Readouts only ever show in the Block Editor (readouts_active gate).
        # Connecting ``changed`` at all makes Qt route every item update
        # through updateScene instead of the direct item->view path, and each
        # slot costs a Python call — so plan scenes connect nothing.
        # ``scene_role`` is set before the controller is composed.
        self._enabled = getattr(scene, "scene_role", None) == "block_editor"
        if self._enabled:
            scene.selectionChanged.connect(self._on_selection_changed)
            scene.changed.connect(self._on_scene_changed)
            scene.modeChanged.connect(self._on_mode_changed)
            scene.instructionChanged.connect(self._on_instruction)

    # ── gate ─────────────────────────────────────────────────────────────
    def readouts_active(self) -> bool:
        """Whether readout labels are visible (and therefore pickable).

        Cheap by construction: it runs on every ``scene.changed``, so it never
        iterates scene items — only the selection set.
        """
        sc = self._scene
        if getattr(sc, "scene_role", None) != "block_editor":
            return False
        if getattr(sc, "mode", None) not in (None, "select"):
            return False
        plc = getattr(sc, "_plc", None)
        if plc is not None and plc.is_input_mode():
            return False
        from .text_item import editing_text_item
        if editing_text_item(sc) is not None:
            return False
        from . import selection_manipulator as _sm
        n = len(sc.selectedItems())
        return 1 <= n <= _sm.GRIP_OBJECT_LIMIT      # read at call time

    # ── specs / layout / pick ────────────────────────────────────────────
    def entries(self) -> list[tuple[object, DimSpec]]:
        """(item, spec) for every dimension of every selected primitive.

        Mid-gesture, specs are mapped through the manipulator's held preview
        (``SelectionManipulator.held_delta``) so labels follow a move drag
        live instead of jumping on release.
        """
        if not self.readouts_active():
            return []
        live = getattr(self._scene, "_live_manip", None)
        manip = live() if callable(live) else None
        dragging = manip is not None and manip.is_dragging()
        from .constraint_dims import is_edge_readout
        out = []
        for it in self._scene.selectedItems():
            fn = getattr(it, "dimension_specs", None)
            if not callable(fn):
                continue
            specs = fn()
            t = manip.held_delta(it) if dragging else None
            if t is not None and not t.isIdentity():
                specs = [map_spec(s, t) for s in specs]
            # D57 (smoke ruling 2026-10-03): Smart Dimension owns edge lengths;
            # angular + radius readouts stay until CS5.
            out.extend((it, s) for s in specs
                       if self.show_edge_lengths or not is_edge_readout(s.key))
        return out

    def layouts(self, view) -> list[ReadoutEntry]:
        """``entries()`` laid out in *view*'s viewport pixels."""
        from .readout_paint import layout_angular, layout_linear
        sm = getattr(self._scene, "scale_manager", None)
        out = []
        for it, s in self.entries():
            text = readout_text(s, sm)
            lay = (layout_linear(view, s, text) if s.kind == "linear"
                   else layout_angular(view, s, text))
            out.append(ReadoutEntry(it, s, lay))
        return out

    def entry_at(self, view, vp_pt) -> ReadoutEntry | None:
        """Topmost fitting label under *vp_pt* (viewport px).

        Returns None when a manipulator handle is under the point: grips win
        (pick precedence, selection-mode §15).
        """
        if not self.readouts_active():
            return None                        # plan scene: every mouse move
        vp_pt = QPointF(vp_pt)
        live = getattr(self._scene, "_live_manip", None)
        manip = live() if callable(live) else None
        if manip is not None and manip.isVisible():
            if manip.hit_handle(view.mapToScene(vp_pt.toPoint())):
                return None
        from .readout_paint import hit_layout
        for e in reversed(self.layouts(view)):
            if hit_layout(e.layout, vp_pt):
                return e
        return None

    @staticmethod
    def _key(e: ReadoutEntry):
        return (id(e.item), e.spec.key)

    def hover_at(self, view, vp_pt) -> tuple[bool, bool]:
        """Update the hovered label from a cursor at *vp_pt*.

        Returns:
            ``(changed, on_label)``: whether the hover target changed, and
            whether the cursor is over a label.
        """
        e = None if self.is_editing() else self.entry_at(view, vp_pt)
        new = self._key(e) if e is not None else None
        changed = new != self._hover
        self._hover = new
        if changed:
            # On a label: its hint. Leaving: restore whatever the line showed
            # before (the select-mode instruction, a HALO readout, ...).
            text = (f"{e.spec.field} · click to edit" if e is not None
                    else self._last_instruction)
            self._emitting = True
            try:
                self._scene.instructionChanged.emit(text)
            finally:
                self._emitting = False
        return changed, e is not None

    def _on_instruction(self, text) -> None:
        """``instructionChanged`` slot: remember others' text. Never raises."""
        if not self._emitting:
            self._last_instruction = text if isinstance(text, str) else ""

    def is_hovered(self, e: ReadoutEntry) -> bool:
        """Whether *e* is the current hover target."""
        return self._hover == self._key(e)

    def press_at(self, view, vp_pt) -> bool:
        """Open the editor on a label under *vp_pt*. True if consumed."""
        e = self.entry_at(view, vp_pt)
        if e is None:
            return False
        self.begin_edit(view, e)
        return True

    # ── paint ────────────────────────────────────────────────────────────
    def paint(self, painter, view, th) -> None:
        """Paint every fitting label (and the hover glow) for *view*."""
        from .readout_paint import label_path, paint_readout
        from .halo import paint_halo_path
        halo_on = bool(getattr(self._scene, "halo_enabled", True))
        editing_key = getattr(self._edit, "key", None)
        entries = self.layouts(view)
        self._painted[id(view)] = self._dirty_rect(entries)
        for e in entries:
            if not e.layout.fits or self._key(e) == editing_key:
                continue
            if halo_on and self.is_hovered(e):
                painter.save()
                painter.resetTransform()
                paint_halo_path(painter, label_path(e.layout), th)
                painter.restore()
            paint_readout(painter, e.layout, th)

    # ── repaint wiring ───────────────────────────────────────────────────
    @staticmethod
    def _dirty_rect(entries) -> QRect:
        """Viewport-px bounds of every fitting label (+ reference arc), padded
        for the hover glow, arrowheads and antialiasing. Empty if none."""
        from .constants import SELDIM_DIRTY_PAD_PX as pad
        from .readout_paint import label_path
        out = QRectF()
        for e in entries:
            lay = e.layout
            if not lay.fits:
                continue
            out = out.united(label_path(lay).boundingRect())
            if lay.arc_center is not None:
                C, r = lay.arc_center, lay.arc_radius_px
                out = out.united(QRectF(C.x() - r, C.y() - r, 2 * r, 2 * r))
        if out.isEmpty():
            return QRect()
        return out.adjusted(-pad, -pad, pad, pad).toAlignedRect()

    def refresh(self) -> None:
        """Full-viewport repaint on every view.

        Labels sit outside item dirty regions, so ``MinimalViewportUpdate``
        would otherwise leave them stale.
        """
        if not self._enabled or not self._scene_alive():
            return
        for v in self._scene.views():
            if not sip.isdeleted(v):
                v.viewport().update()

    def _scene_alive(self) -> bool:
        """False once the scene's C++ object is gone.

        A dying QGraphicsScene still emits ``selectionChanged`` (items are
        cleared in its destructor) after sip has marked the wrapper deleted;
        touching it then raises inside a Qt slot, which PyQt6 turns into a
        silent process abort (exit 0xC0000409 at interpreter shutdown). Every
        slot below bails out first.
        """
        return not sip.isdeleted(self._scene)

    def _on_scene_changed(self, _regions) -> None:
        """Dirty old ∪ new readout rects per view — never the full viewport.

        Scene changes arrive on every grip step; a full-viewport repaint there
        re-renders the whole scene. A Qt slot: never raises.
        """
        try:
            if not self._scene_alive():
                return
            self._repaint_regions()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("readout region repaint failed")

    def _repaint_regions(self) -> None:
        """``viewport().update(old ∪ new)`` per view: the readout region
        painted last frame united with where the labels are now."""
        active = self.readouts_active()
        for v in self._scene.views():
            if sip.isdeleted(v):
                continue
            old = self._painted.get(id(v), QRect())
            new = self._dirty_rect(self.layouts(v)) if active else QRect()
            dirty = old.united(new)
            if not dirty.isEmpty():
                v.viewport().update(dirty)

    def _on_selection_changed(self) -> None:
        """Selection changed: drop hover, end any edit, repaint old ∪ new
        readout regions (never the full viewport). A Qt slot: never raises."""
        try:
            if not self._scene_alive():
                return
            self._hover = None
            if self.is_editing():
                self.cancel_edit()
            self._repaint_regions()
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "readout selection-change handling failed")

    def _on_mode_changed(self, _mode) -> None:
        """Mode changed: end any edit, full repaint. A Qt slot: never raises."""
        try:
            if not self._scene_alive():
                return
            if self.is_editing():
                self.cancel_edit()
            self.refresh()
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "readout mode-change handling failed")

    # ── edit session ─────────────────────────────────────────────────────
    def is_editing(self) -> bool:
        """Whether a readout edit session is open."""
        return self._edit is not None

    def editing_key(self):
        """The open edit's key (``(id(item), key)`` or ``("dim", cid)``)."""
        return getattr(self._edit, "key", None)

    def begin_edit(self, view, e: ReadoutEntry, *, commit=None, key=None) -> None:
        """Open a latched, engaged one-field HUD on *e* (selection-mode §15).

        The HUD seeds from the spec's live value, latches to the label's scene
        position (so pan/zoom carry it) and takes the keyboard: from here until
        commit/cancel ``Model_Space.is_input_mode()`` is True.

        CS4: *commit* (``value_mm -> None``) replaces the spec's setter + undo
        push (a persisted dim drives its constraint, which pushes its own
        step); *key* names the edited label (``("dim", cid)``).
        """
        from .dynamic_input import DynamicInputHud, FieldKind, FieldSpec, Schema
        self.cancel_edit()
        kind = (FieldKind.SPAN if e.spec.field_kind == "span"
                else FieldKind.DIMENSION)
        schema = Schema(name="readout",
                        fields=(FieldSpec(e.spec.field, e.spec.field, kind,
                                          e.spec.minimum),),
                        resolve=lambda _anchor, values: values,
                        returns_point=False)
        sm = getattr(self._scene, "scale_manager", None)
        hud = DynamicInputHud(schema, sm, view.viewport())
        # set_values takes schema (scene) units for DIMENSION and converts to
        # mm with the same calibration guard, so mirror it on the way in.
        seed = e.spec.value
        if kind is FieldKind.DIMENSION and sm is not None and sm.is_calibrated:
            seed = sm.mm_to_scene(seed)
        hud.set_values({e.spec.field: seed})
        self._edit = _EditSession(view=view, hud=hud, item=e.item, spec=e.spec,
                                  key=key if key is not None else self._key(e),
                                  kind=kind, commit=commit)
        hud.committed.connect(self._on_committed)
        hud.cancelled.connect(self._on_cancelled)
        anchor = view.mapToScene(e.layout.center.toPoint())
        view.place_dynamic_input(hud, anchor)
        hud.show()
        hud.engage()
        # The canvas goes inert (selection-mode §15): drop any geometry HALO
        # left from before the edit; _halo_suppressed() keeps it off after.
        clear = getattr(self._scene, "halo_clear", None)
        if callable(clear):
            clear()
        self.refresh()

    def _on_committed(self, values: dict) -> None:
        """HUD ``committed`` slot: validate, apply, push one undo step.

        A Qt slot — it must never raise (PyQt6 aborts the process on an
        exception escaping a slot), so everything is guarded.
        """
        s = self._edit
        if s is None or not self._scene_alive() or sip.isdeleted(s.hud):
            return
        try:
            from .dynamic_input import FieldKind
            v = float(values.get(s.spec.field, s.spec.value))
            if s.kind is FieldKind.DIMENSION:
                v = s.hud.scene_to_mm(v)
            if (v <= s.spec.minimum
                    or (s.spec.maximum is not None and v > s.spec.maximum)):
                s.hud.reject_commit()          # stays open, red border
                return
            if math.isclose(v, s.spec.value, rel_tol=1e-9, abs_tol=1e-9):
                self._end_session()            # no-op commit: no apply, no step
                return
        except Exception:
            import logging
            logging.getLogger(__name__).exception("readout commit read failed")
            self.cancel_edit()
            return
        if s.commit is not None:               # CS4: a dim edit drives its constraint
            self._end_session()
            try:
                s.commit(v)                    # set_value pushes its own undo step
            except Exception:
                import logging
                logging.getLogger(__name__).exception("dim commit failed")
            return
        try:
            # Constraint seam (parametric-constraint-system §8): the typed
            # edit's values are goals; the rest re-solves when the context
            # exits — BEFORE the undo push below snapshots.
            ctl = getattr(self._scene, "constraint_ctl", None)
            with (ctl.edit([s.item], typed=True) if ctl is not None
                  else contextlib.nullcontext()):
                s.spec.apply(v)
        except Exception:                      # never half-apply into undo
            import logging
            logging.getLogger(__name__).exception("readout apply failed")
            self.cancel_edit()
            return
        try:
            self._scene.push_undo_state()      # mutate-then-push: one step
        except Exception:
            import logging
            logging.getLogger(__name__).exception("readout undo push failed")
        try:
            refit = getattr(self._scene, "notify_geometry_edited", None)
            if callable(refit):
                refit()                        # re-fit the manipulator frame
        except Exception:
            import logging
            logging.getLogger(__name__).exception("readout frame refit failed")
        self._end_session()
        try:
            # The property panel shows the same dimensions: re-read them.
            # Same payload MainWindow.update_property_manager passes.
            sel = list(self._scene.selectedItems())
            self._scene.requestPropertyUpdate.emit(sel if sel else [s.item])
        except Exception:
            import logging
            logging.getLogger(__name__).exception("readout panel refresh failed")

    def _on_cancelled(self) -> None:
        """HUD ``cancelled`` slot (Escape). Never raises."""
        try:
            self.cancel_edit()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("readout cancel failed")

    def cancel_edit(self) -> None:
        """Close any open edit session without applying."""
        if self._edit is not None:
            self._end_session()

    def _end_session(self) -> None:
        """Tear the HUD down, release the latch and hand focus back."""
        s, self._edit = self._edit, None
        if s is None:
            return
        hud = s.hud
        if not sip.isdeleted(hud):
            for sig, slot in ((hud.committed, self._on_committed),
                              (hud.cancelled, self._on_cancelled)):
                try:
                    sig.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            hud.hide()
            hud.deleteLater()
        view = s.view
        if view is not None and not sip.isdeleted(view):
            view._dyn_anchor_scene = None      # don't leak the latch to placement
            view.setFocus()
        self.refresh()

    @property
    def hud(self):
        """The open edit session's HUD, else None."""
        return getattr(self._edit, "hud", None)
