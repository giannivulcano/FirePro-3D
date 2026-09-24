"""Selection dimension readouts (2d-geometry.md §8, selection-mode.md §15).

A readout is a transient, painted record — never a QGraphicsItem and never a
child of its primitive. Primitives describe their dimensions via
``dimension_specs() -> list[DimSpec]``; ``SelectionReadoutController`` turns
the live selection into painted, pickable, editable labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6 import sip
from PyQt6.QtCore import QPointF


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


class SelectionReadoutController:
    """Owns selection dimension readouts on one Model_Space (selection-mode §15).

    Stateless between frames: ``entries()`` re-reads the live selection on
    every call, so geometry changes need no notification, only repaints.
    Readouts are painted overlay records, never ``QGraphicsItem``s.
    """

    def __init__(self, scene):
        self._scene = scene
        self._hover = None            # (id(item), key) or None
        self._edit = None             # edit session (Task 11) or None
        scene.selectionChanged.connect(self._on_selection_changed)
        scene.changed.connect(self._on_scene_changed)
        scene.modeChanged.connect(self._on_mode_changed)

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
        """(item, spec) for every dimension of every selected primitive."""
        if not self.readouts_active():
            return []
        out = []
        for it in self._scene.selectedItems():
            fn = getattr(it, "dimension_specs", None)
            if callable(fn):
                out.extend((it, s) for s in fn())
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
            self._scene.instructionChanged.emit(
                f"{e.spec.field} · click to edit" if e is not None else "")
        return changed, e is not None

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
        for e in self.layouts(view):
            if not e.layout.fits or self._key(e) == editing_key:
                continue
            if halo_on and self.is_hovered(e):
                painter.save()
                painter.resetTransform()
                paint_halo_path(painter, label_path(e.layout), th)
                painter.restore()
            paint_readout(painter, e.layout, th)

    # ── repaint wiring ───────────────────────────────────────────────────
    def refresh(self) -> None:
        """Full-viewport repaint on every view.

        Labels sit outside item dirty regions, so ``MinimalViewportUpdate``
        would otherwise leave them stale.
        """
        if not self._scene_alive():
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
        if self._scene_alive() and self.readouts_active():
            self.refresh()

    def _on_selection_changed(self) -> None:
        if not self._scene_alive():
            return
        self._hover = None
        if self.is_editing():
            self.cancel_edit()
        self.refresh()

    def _on_mode_changed(self, _mode) -> None:
        if not self._scene_alive():
            return
        if self.is_editing():
            self.cancel_edit()
        self.refresh()

    # ── edit session (Task 11) ───────────────────────────────────────────
    def is_editing(self) -> bool:
        """Whether a readout edit session is open."""
        return self._edit is not None

    def begin_edit(self, view, e: ReadoutEntry) -> None:
        """Open the one-field HUD on *e* (implemented in Task 11)."""
        raise NotImplementedError

    def cancel_edit(self) -> None:
        """Close any open edit session without applying (Task 11)."""
        self._edit = None

    @property
    def hud(self):
        """The open edit session's HUD, else None."""
        return getattr(self._edit, "hud", None)
