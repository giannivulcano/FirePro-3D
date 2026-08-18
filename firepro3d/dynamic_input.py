"""
dynamic_input.py
================
Dynamic Input: the on-canvas HUD that both reports the live geometry of an
in-progress placement and accepts typed values to drive it precisely.

Schemas are organised by **geometric primitive**, not entity type — pipe,
wall, gridline, polyline and the line tool are all *a line from an anchor*,
so one Line schema serves five clients.

This module knows nothing about ``QGraphicsScene``.  A schema turns typed
values into the same point a mouse click would have produced; ``Model_Space``
hands that point to the existing click-commit path.  Dynamic input is an
alternative *point source*, not an alternative *commit path*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from PyQt6.QtCore import QEvent, QPointF, Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from . import theme
from .dimension_edit import DimensionEdit
from .scale_manager import ScaleManager


class FieldKind(Enum):
    """How a field is formatted, parsed and validated.

    Three kinds map to three ``DimensionEdit`` configurations — not three
    widgets.
    """
    DIMENSION = auto()
    ANGLE = auto()
    COUNT = auto()


@dataclass(frozen=True)
class FieldSpec:
    """Declarative description of one HUD field.

    Attributes:
        name: Key used in the values dict passed to a resolver.
        label: Short caption shown beside the editor in the HUD.
        kind: Formatting/parsing configuration for the editor.
        minimum: Follows ``DimensionEdit`` semantics — accepted values must
            be strictly greater than it, so ``0.0`` rejects zero and
            negatives.  ``None`` where negatives are legal (angles,
            displacement components).
    """
    name: str
    label: str
    kind: FieldKind
    minimum: float | None = None


@dataclass(frozen=True)
class Schema:
    """A field set plus the pure functions converting typed values to geometry.

    Attributes:
        name: Registry key.
        fields: Ordered field specs; order is the HUD's tab order.
        resolve: ``resolve(anchor, values)`` returns a ``QPointF`` for
            placement schemas and a plain dict for transform schemas.
        seed: The inverse of *resolve* for placement schemas, and ``None``
            for transforms — their seeds come from scene state rather than a
            cursor position.
        returns_point: Whether *resolve* yields a ``QPointF`` (placement) or a
            dict (transform).  Declared rather than inferred from ``seed``:
            "has an inverse" and "resolves to a point" are independent
            properties that merely coincide across today's six schemas.
            Callers branch on this to pick an applier, so a future schema that
            seeds from scene state yet resolves to a point must not be able to
            route itself to the wrong one.
    """
    name: str
    fields: tuple[FieldSpec, ...]
    resolve: Callable
    seed: Callable | None = None
    returns_point: bool = True

    @property
    def is_placement(self) -> bool:
        """True when this schema resolves to a point rather than a transform."""
        return self.returns_point


# ── Line ──────────────────────────────────────────────────────────────────
# Angles are Y-up (0° = right, 90° = up); scene Y is down, hence the negation.

def resolve_line(anchor: QPointF, values: dict) -> QPointF:
    """Return the endpoint *Length* away from *anchor* at *Angle*."""
    rad = math.radians(values["Angle"])
    length = values["Length"]
    return QPointF(anchor.x() + length * math.cos(rad),
                   anchor.y() - length * math.sin(rad))


def seed_line(anchor: QPointF, point: QPointF) -> dict:
    """Return the Length/Angle that ``resolve_line`` maps back to *point*."""
    dx = point.x() - anchor.x()
    dy = point.y() - anchor.y()
    return {"Length": math.hypot(dx, dy),
            "Angle": math.degrees(math.atan2(-dy, dx))}


# ── Rectangle ─────────────────────────────────────────────────────────────

def resolve_rectangle(anchor: QPointF, values: dict) -> QPointF:
    """Return the opposite-corner point *X*/*Y* away from *anchor*.

    Resolving to a corner rather than a size keeps this a point source, and
    signed extents let one point serve both rectangle modes: corner-to-corner
    builds ``QRectF(anchor, point).normalized()`` — where the sign chooses
    which quadrant the rectangle occupies — while from-centre re-applies
    ``abs()`` to derive half-extents and so ignores the sign.  Feeding this an
    unsigned *X*/*Y* would silently rebuild every corner-mode rectangle in the
    up-right quadrant.
    """
    return QPointF(anchor.x() + values["X"], anchor.y() - values["Y"])


def seed_rectangle(anchor: QPointF, point: QPointF) -> dict:
    """Return the signed X/Y extents from *anchor* to *point*, Y-up.

    The sign is kept so ``resolve_rectangle`` round-trips *point* exactly:
    in corner mode the drag direction is the geometry, not just a visual cue.
    Folding to a magnitude is left to the from-centre commit path, which
    ``abs()``es anyway.
    """
    return {"X": point.x() - anchor.x(),
            "Y": -(point.y() - anchor.y())}


# ── Circle ────────────────────────────────────────────────────────────────

def resolve_circle(anchor: QPointF, values: dict) -> QPointF:
    """Return any point *Radius* away from the centre *anchor*.

    Direction is arbitrary — the click path takes the hypot of the point
    against the centre, so only the distance survives.
    """
    return QPointF(anchor.x() + values["Radius"], anchor.y())


def seed_circle(anchor: QPointF, point: QPointF) -> dict:
    """Return the radius implied by *point* on a circle centred at *anchor*."""
    return {"Radius": math.hypot(point.x() - anchor.x(),
                                 point.y() - anchor.y())}


# ── Transforms ────────────────────────────────────────────────────────────
# Transforms modify existing geometry rather than producing a new point, so
# these return dicts the caller applies directly.

def resolve_displacement(anchor, values: dict) -> dict:
    """Return the move/copy offset for typed *dX*/*dY* (Y-up input)."""
    return {"offset": QPointF(values["dX"], -values["dY"])}


def resolve_distance(anchor, values: dict) -> dict:
    """Return the scalar distance for offset-style operations."""
    return {"distance": values["Distance"]}


def resolve_spacing_count(anchor, values: dict) -> dict:
    """Return spacing plus an integer count, floored at one.

    The editor yields a float, so the count is rounded and clamped: an array
    of zero items is never a useful commit.
    """
    return {"spacing": values["Spacing"],
            "count": max(1, int(round(values["Count"])))}


SCHEMAS: dict[str, Schema] = {
    "line": Schema(
        name="line",
        fields=(
            FieldSpec("Length", "L", FieldKind.DIMENSION, minimum=0.0),
            FieldSpec("Angle", "A", FieldKind.ANGLE),
        ),
        resolve=resolve_line,
        seed=seed_line,
    ),
    "rectangle": Schema(
        name="rectangle",
        fields=(
            # Signed, like displacement dX/dY: a left/down drag seeds a
            # negative extent, and in corner mode that sign is the geometry.
            # A 0.0 minimum would reject the seed the schema just produced.
            FieldSpec("X", "X", FieldKind.DIMENSION),
            FieldSpec("Y", "Y", FieldKind.DIMENSION),
        ),
        resolve=resolve_rectangle,
        seed=seed_rectangle,
    ),
    "circle": Schema(
        name="circle",
        fields=(
            FieldSpec("Radius", "R", FieldKind.DIMENSION, minimum=0.0),
        ),
        resolve=resolve_circle,
        seed=seed_circle,
    ),
    "displacement": Schema(
        name="displacement",
        fields=(
            FieldSpec("dX", "dX", FieldKind.DIMENSION),
            FieldSpec("dY", "dY", FieldKind.DIMENSION),
        ),
        resolve=resolve_displacement,
        returns_point=False,
    ),
    "distance": Schema(
        name="distance",
        fields=(
            FieldSpec("Distance", "Dist", FieldKind.DIMENSION, minimum=0.0),
        ),
        resolve=resolve_distance,
        returns_point=False,
    ),
    "spacing_count": Schema(
        name="spacing_count",
        fields=(
            FieldSpec("Spacing", "Sp", FieldKind.DIMENSION, minimum=0.0),
            FieldSpec("Count", "N", FieldKind.COUNT, minimum=0.0),
        ),
        resolve=resolve_spacing_count,
        returns_point=False,
    ),
}


# ── HUD widget ────────────────────────────────────────────────────────────

def _format_count(value: float) -> str:
    """Format a COUNT value as a bare integer (``"3"``, never ``"3.0"``)."""
    return str(int(round(value)))


def _parse_count(text: str) -> float | None:
    """Parse a bare integer count, tolerating a decimal the user typed.

    A fractional entry is **rounded rather than rejected** — typing ``2.6``
    yields ``3``, and the field is *not* flagged invalid.  This is deliberate
    and matches ``resolve_spacing_count``, which rounds the float the editor
    hands it anyway; rejecting here would only move the same rounding one
    layer down while making a near-miss keystroke feel like a hard error.  It
    is nonetheless a silent value substitution, so the reformat writes the
    rounded integer straight back into the field: the user sees ``3`` and can
    correct it before committing.

    Returns:
        The rounded count, or None when unparseable so ``DimensionEdit``
        reverts to the last valid value.
    """
    try:
        return float(round(float(str(text).strip())))
    except (TypeError, ValueError):
        return None


# ── Invalid-state colour ──────────────────────────────────────────────────
# ``theme.py`` carries a ``status_error`` token per variant, so the rejected
# border needs no literal of its own.

def effective_modifiers(event) -> Qt.KeyboardModifier:
    """Return *event*'s modifiers with ``KeypadModifier`` masked out.

    ``KeypadModifier`` is not a modifier in the Ctrl/Shift/Alt sense — it is
    Qt reporting *which physical key* produced the event, and it rides along
    on every numpad keystroke including Enter.  Code that compares
    ``event.modifiers()`` to ``NoModifier`` therefore silently refuses the
    whole numpad, which is how numpad digits could engage the HUD (that call
    site accepts the flag) while numpad Enter could not commit it.

    Masking rather than adding a second equality test keeps every branch
    consistent by construction: real modifiers survive, so ``Shift+Tab`` and
    ``Ctrl+Enter`` still gate exactly as before.

    Returns:
        The modifier set to compare against, keypad bit cleared.
    """
    return event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier


def _build_hud_style(t: theme.Theme) -> str:
    """Return the HUD stylesheet built from *t*'s tokens.

    Built per-instance rather than as a module constant so the HUD follows
    ``theme.detect()``: a constant would freeze whichever variant was current
    at import time and render the HUD unreadable under the other one.

    The ``[invalid="true"]`` rule is the visual half of ``_invalid``.  QSS
    replaces native painting, so a property selector with no matching rule
    fails *invisibly* — it renders as the base state — which is why this rule
    and ``_set_invalid_style`` must ship together.
    """
    return f"""
QWidget#DynamicInputHud {{
    background-color: {t.bg_raised};
    border: 1px solid {t.border_strong};
    border-radius: 4px;
}}
QLabel {{
    color: {t.text_secondary};
    font-family: 'Segoe UI';
    font-size: 8pt;
    background: transparent;
    border: none;
}}
QLineEdit {{
    background-color: {t.bg_sunken};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    border-radius: 3px;
    font-family: 'Consolas';
    font-size: 8pt;
    padding: 1px 3px;
}}
QLineEdit:focus {{
    border: 1px solid {t.accent_primary};
}}
QLineEdit[invalid="true"] {{
    border: 1px solid {t.status_error};
}}
QLineEdit[invalid="true"]:focus {{
    border: 1px solid {t.status_error};
}}
"""


class DynamicInputHud(QWidget):
    """Editable on-canvas readout driving an in-progress placement.

    One ``DimensionEdit`` is built per ``FieldSpec``; the three ``FieldKind``
    values select three *configurations* of that one widget rather than three
    different widgets, so the house parser, formatter, minimum handling and
    revert-to-last-valid behaviour come along unchanged.

    **Units boundary.** Schemas seed and resolve in *scene* units, while
    ``DimensionEdit`` stores and parses *millimetres*.  ``DIMENSION`` fields
    are therefore converted on the way in and back out; ``ANGLE`` and
    ``COUNT`` are dimensionless and pass straight through.  The conversion is
    deliberately guarded on calibration so the editor's text always agrees
    with ``Model_Space._format_schema_readout`` — see ``_scene_to_mm``.

    This widget is a plain child of whatever it is parented to (a viewport);
    it sets no window flags and is not a dialog.

    Attributes:
        committed: Emitted with the values dict when the user accepts.
        cancelled: Emitted when the user abandons the input.
    """

    committed = pyqtSignal(dict)
    cancelled = pyqtSignal()

    def __init__(self, schema: Schema, scale_manager: ScaleManager | None = None,
                 parent=None):
        """Build one editor per field of *schema*.

        Args:
            schema: The active schema; its field order is the layout order.
            scale_manager: Supplies formatting and the scene↔mm calibration.
                ``None`` degrades to treating 1 scene unit as 1 mm.
            parent: Owning widget, normally a ``QGraphicsView`` viewport.
        """
        super().__init__(parent)
        self._schema = schema
        self._sm = scale_manager
        self._editors: dict[str, DimensionEdit] = {}
        self._specs: dict[str, FieldSpec] = {f.name: f for f in schema.fields}
        self._invalid: set[str] = set()
        self._focused_name: str | None = None
        # Session undo (decision S3).  DimensionEdit._reformat calls setText on
        # every commit and QLineEdit.setText clears the widget's own undo
        # history, so the built-in per-field undo is destroyed by every focus
        # change and every Tab.  The HUD keeps the stack instead: entries are
        # (field name, value before the edit), pushed in the order made.
        self._undo_stack: list[tuple[str, float]] = []
        self._committed: dict[str, float] = {}
        self._undoing = False

        self.setObjectName("DynamicInputHud")
        # QSS on a plain QWidget only paints with this attribute set.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Built here, not at import: honours whichever variant is current.
        self.setStyleSheet(_build_hud_style(theme.detect()))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        for spec in schema.fields:
            label = QLabel(spec.label, self)
            layout.addWidget(label)
            editor = self._build_editor(spec)
            layout.addWidget(editor)
            self._editors[spec.name] = editor
            # Only *user* edits retire the invalid flag; a programmatic
            # setText (including the editor's own revert-reformat) must not,
            # or the flag would clear itself on the read that set it.
            editor.textEdited.connect(
                lambda _text, name=spec.name: self._clear_invalid(name))
            # valueChanged fires only for *accepted* new values, which is
            # exactly the granularity the session undo stack wants: rejected
            # entries revert on their own and are not edits to step back over.
            editor.valueChanged.connect(
                lambda mm, name=spec.name: self._record_edit(name, mm))
            # Set the property up front so the selector has something to match
            # from the first polish rather than only after a rejection.
            self._set_invalid_style(editor, False)
            # Keys are intercepted on the editor rather than overridden on it:
            # QLineEdit consumes Tab/Return itself, so the filter has to see
            # them first.  See ``eventFilter``.
            editor.installEventFilter(self)

    # ── Construction helpers ──────────────────────────────────────────────

    def _build_editor(self, spec: FieldSpec) -> DimensionEdit:
        """Return a ``DimensionEdit`` configured for *spec*'s kind."""
        if spec.kind is FieldKind.ANGLE:
            editor = DimensionEdit(
                None, initial_mm=0.0, parent=self,
                parser=ScaleManager.parse_angle,
                formatter=ScaleManager.format_angle,
                minimum=spec.minimum,
            )
        elif spec.kind is FieldKind.COUNT:
            editor = DimensionEdit(
                None, initial_mm=0.0, parent=self,
                parser=_parse_count, formatter=_format_count,
                minimum=spec.minimum,
            )
        else:
            # DIMENSION: the scale manager supplies parsing and formatting.
            # The minimum is expressed in scene units by the schema, so it is
            # converted into the mm domain the editor validates in.
            editor = DimensionEdit(
                self._sm, initial_mm=0.0, parent=self,
                minimum=(None if spec.minimum is None
                         else self._scene_to_mm(spec.minimum)),
            )
        editor.setMinimumWidth(70)
        return editor

    # ── Units boundary ────────────────────────────────────────────────────
    #
    # ``ScaleManager.scene_to_mm`` divides by pixels_per_mm *unconditionally*,
    # but ``scene_to_display`` — which renders the canvas readout — first
    # checks ``_calibrated`` and treats 1 scene unit as 1 mm when it is not.
    # Uncalibrated is the default state, so an unguarded conversion would
    # disagree with the readout on most drawings.  These two mirror
    # ``scene_to_display``'s guard so the editor text matches it exactly.
    #
    # ``scene_to_display_value``/``display_to_scene`` are deliberately *not*
    # used: they return a number in the current *display unit* (inches under
    # imperial), whereas ``DimensionEdit`` stores millimetres.

    def _scene_to_mm(self, scene_value: float) -> float:
        """Convert scene units to the mm ``DimensionEdit`` stores."""
        if self._sm is not None and self._sm.is_calibrated:
            return self._sm.scene_to_mm(scene_value)
        return scene_value

    def _mm_to_scene(self, mm: float) -> float:
        """Convert ``DimensionEdit``'s mm back to schema scene units."""
        if self._sm is not None and self._sm.is_calibrated:
            return self._sm.mm_to_scene(mm)
        return mm

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def schema(self) -> Schema:
        """The schema this HUD was built for."""
        return self._schema

    def field_names(self) -> tuple[str, ...]:
        """Field names in schema (tab) order."""
        return tuple(f.name for f in self._schema.fields)

    def editor(self, name: str) -> DimensionEdit:
        """Return the editor for field *name*.

        Raises:
            KeyError: If *name* is not a field of this schema.
        """
        return self._editors[name]

    def set_values(self, values: dict) -> None:
        """Seed the editors from *values*, expressed in schema units.

        ``DIMENSION`` entries are scene units and are converted to mm;
        ``ANGLE`` and ``COUNT`` are stored as given.  Names absent from
        *values* are left untouched.
        """
        for name, editor in self._editors.items():
            if name not in values:
                continue
            raw = float(values[name])
            spec = self._specs[name]
            if spec.kind is FieldKind.DIMENSION:
                raw = self._scene_to_mm(raw)
            editor.set_value_mm(raw)
        # A reseed replaces whatever text was rejected, so nothing stays flagged.
        for name in list(self._invalid):
            self._clear_invalid(name)
        # Seeding *is* the baseline the session undo stack unwinds towards, so
        # it starts a fresh stack rather than becoming an entry in the old one.
        self._undo_stack.clear()
        self._committed = {n: ed._value_mm for n, ed in self._editors.items()}

    def values(self) -> dict:
        """Return the current values in schema units.

        Every editor is force-committed first.  ``editingFinished`` does not
        fire when Return is pressed with focus still in the field, so without
        this the stale seeded value would be read instead of what the user
        typed — the same fix ``DimensionDelegate.setModelData`` applies.
        Rejected entries revert to their last valid value and are recorded
        for ``has_invalid_field``.

        The invalid record is *accumulated*, never reset here: the first read
        already reverted the offending field to clean text, so a read that
        cleared the set would find nothing wrong the second time and hand back
        geometry the user never typed.  Flags retire on user edits and on
        ``set_values``; see ``_clear_invalid``.
        """
        out: dict = {}
        for name, editor in self._editors.items():
            # The verdict comes from the editor's own commit path, never from
            # a re-parse here: acceptance cannot be read off the widget after
            # the fact (it reverts silently) nor inferred from the text, since
            # a *valid* entry usually reformats ("3ft" → "914.400 mm").
            if not editor.try_commit():
                self._mark_invalid(name)
            mm = editor.value_mm()
            spec = self._specs[name]
            out[name] = (self._mm_to_scene(mm)
                         if spec.kind is FieldKind.DIMENSION else mm)
        return out

    def has_invalid_field(self) -> bool:
        """Whether any field holds input that was rejected and not yet retyped.

        Sticky by design: it stays True across repeated ``values()`` reads
        until the user edits the offending field or ``set_values`` reseeds it.
        """
        return bool(self._invalid)

    def focus_first(self, seed: str = "") -> None:
        """Focus the first field, optionally replacing its text with *seed*.

        Args:
            seed: The keystroke that engaged the HUD.  When given it replaces
                the field's text and leaves the cursor at the end, so typing
                continues naturally; otherwise the existing text is selected
                for immediate overwrite.
        """
        if not self._schema.fields:
            return
        editor = self._editors[self._schema.fields[0].name]
        editor.setFocus(Qt.FocusReason.OtherFocusReason)
        if seed:
            # setText after focus: focusInEvent selects all, which would make
            # the seed look pre-selected and be wiped by the next keystroke.
            editor.setText(seed)
            editor.setCursorPosition(len(seed))
        else:
            editor.selectAll()

    def _record_edit(self, name: str, new_mm: float) -> None:
        """Push the value *name* held before this edit onto the undo stack.

        Suppressed while :meth:`undo` is applying a restore, or undoing would
        push its own inverse and the stack would never drain.
        """
        if self._undoing:
            return
        previous = self._committed.get(name)
        if previous is None or previous == new_mm:
            self._committed[name] = new_mm
            return
        self._undo_stack.append((name, previous))
        self._committed[name] = new_mm

    def undo(self) -> bool:
        """Step back one edit, returning focus to the field it belonged to.

        Walks back through the edits in the order they were made until the HUD
        is at its seeded state, then stops.  Returns True when something was
        undone; the caller consumes the key either way, because while the HUD
        is open Ctrl+Z belongs to it and must never reach the scene's undo
        stack — that is what deleted committed geometry in smoke testing.
        """
        # Half-typed text first.  The HUD consumes Ctrl+Z before QLineEdit sees
        # it, so the widget's own within-field undo is no longer reachable —
        # without this, typing "250" and hitting Ctrl+Z before Tab would do
        # nothing at all, which is how this landed in smoke testing.
        focused = self._editors.get(self._focused_name or "")
        if focused is not None and focused.text() != focused._seed_text:
            committed = self._committed.get(self._focused_name or "")
            self._undoing = True
            try:
                focused.set_value_mm(committed if committed is not None
                                     else focused._value_mm)
            finally:
                self._undoing = False
            self._clear_invalid(self._focused_name or "")
            return True

        if not self._undo_stack:
            return False
        name, previous = self._undo_stack.pop()
        editor = self._editors.get(name)
        if editor is None:
            return False
        self._undoing = True
        try:
            # valueChanged and set_value_mm both speak the editor's own slot
            # (mm for DIMENSION, degrees for ANGLE, a plain count for COUNT),
            # so the stored value round-trips without a unit conversion. The
            # scene<->mm conversion lives at the values()/set_values boundary.
            editor.set_value_mm(previous)
            self._committed[name] = previous
        finally:
            self._undoing = False
        self._clear_invalid(name)
        editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self._focused_name = name
        return True

    def restore_focus(self) -> None:
        """Return focus to the field the user was last editing.

        Qt gives click-focus to the widget under the cursor from
        ``QApplication::notify``, *before* any handler of ours runs, so a
        click on the canvas cannot be stopped from taking focus — it can only
        be given back.  Without this the HUD stays visible and
        ``is_input_mode()`` stays True while the keyboard is actually pointed
        at the view, so Ctrl+Z reaches scene undo and destroys committed
        geometry the user never meant to touch.

        Selection is deliberately *not* reset: the user is mid-edit, and
        re-selecting the text would make the next keystroke wipe what they
        already typed.
        """
        editor = self._editors.get(self._focused_name or "")
        if editor is None:
            self.focus_first()
            return
        editor.setFocus(Qt.FocusReason.OtherFocusReason)

    # ── Key handling ──────────────────────────────────────────────────────
    #
    # The HUD replaced a modal ``QDialog``.  A modal absorbed the whole
    # keyboard for free; a focused child widget does not, so routing is now
    # explicit — that is the deliberate cost of putting the input on canvas.
    #
    # Filtering on each editor rather than overriding ``keyPressEvent`` keeps
    # ``DimensionEdit`` free of HUD concerns and, more importantly, gets ahead
    # of ``QLineEdit``: Tab is consumed by focus handling and Return by
    # ``editingFinished`` before a subclass hook of ours would run.

    def eventFilter(self, obj, event):  # noqa: N802 (Qt naming)
        """Route HUD keys away from the editors before ``QLineEdit`` eats them.

        Two event types matter:

        ``ShortcutOverride``
            Claimed for **Escape only**.  ``main.py`` binds Escape window-wide
            with a ``QShortcut``, and a window shortcut outranks a focused
            widget unless that widget accepts this event — without it Escape
            would skip the HUD and cancel the entire placement mode.  The
            modifier test runs through ``_effective_modifiers`` so this branch
            and ``_handle_key`` cannot disagree about what "unmodified" means.
            No keypad has an Escape today, but the two tests are the same test
            and stating it once is what keeps them that way.  Nothing
            else is claimed: ``QLineEdit`` already accepts the overrides it
            needs (Ctrl+Z for text undo, Delete, the clipboard keys), and in
            input mode those belong to the text field, exactly as they do in
            every other application.  Scene undo is a cursor-mode concern.

        ``KeyPress``
            Tab/Backtab move between fields, Return/Enter accept, Escape
            cancels.  Everything else — crucially **Space**, without which
            ``12' 6"`` cannot be typed — falls through untouched.

        Returns:
            True when the event was consumed here, otherwise the base result.
        """
        if obj in self._editors.values():
            if event.type() == QEvent.Type.FocusIn:
                # Remembered so restore_focus can put the user back in the
                # field they were actually editing, not always the first one.
                for name, ed in self._editors.items():
                    if ed is obj:
                        self._focused_name = name
                        break
            elif event.type() == QEvent.Type.ShortcutOverride:
                mods = effective_modifiers(event)
                if (event.key() == Qt.Key.Key_Escape
                        and mods == Qt.KeyboardModifier.NoModifier):
                    # Accepting only marks "deliver this as a key press to me";
                    # the actual cancel happens in the KeyPress branch below.
                    event.accept()
                    return True
                if (event.key() == Qt.Key.Key_Z
                        and mods == Qt.KeyboardModifier.ControlModifier):
                    # The ribbon Undo button binds Ctrl+Z window-wide.  QLineEdit
                    # happens to claim this override today, which is the only
                    # reason scene undo did not fire from a focused field — an
                    # implementation detail of Qt, not a guarantee.  Claim it.
                    event.accept()
                    return True
            elif event.type() == QEvent.Type.KeyPress:
                if self._handle_key(obj, event):
                    return True
        return super().eventFilter(obj, event)

    def _handle_key(self, editor: DimensionEdit, event) -> bool:
        """Act on a key press in *editor*.

        Modifiers are matched exactly, mirroring the ``ShortcutOverride``
        branch's ``NoModifier`` test: the two must agree, or a combination the
        HUD acts on (``Ctrl+Escape``) would be one the HUD never claimed the
        override for.  Exact matching also leaves ``Ctrl+Tab`` and friends to
        Qt, where a future window-level binding can reach them.  Shift+Tab is
        the one legitimate modifier — Qt delivers it as ``Key_Backtab``, and
        some platforms keep ``Key_Tab`` with Shift set, so both are accepted.

        The comparison runs on ``effective_modifiers``, so the numpad — whose
        keys all carry ``KeypadModifier`` — reaches every branch here.  A user
        who engaged the HUD with numpad digits must be able to commit with
        numpad Enter.

        Returns:
            True when the key was consumed and must not reach the editor.
        """
        key = event.key()
        mods = effective_modifiers(event)
        bare = mods == Qt.KeyboardModifier.NoModifier
        shift_only = mods == Qt.KeyboardModifier.ShiftModifier

        if (key == Qt.Key.Key_Backtab and (bare or shift_only)) or (
                key == Qt.Key.Key_Tab and shift_only):
            self._step_focus(editor, -1)
            return True
        if key == Qt.Key.Key_Tab and bare:
            self._step_focus(editor, +1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and bare:
            self._accept()
            return True
        if key == Qt.Key.Key_Escape and bare:
            self.cancelled.emit()
            return True
        if (key == Qt.Key.Key_Z
                and mods == Qt.KeyboardModifier.ControlModifier):
            # Consumed whether or not anything was undone: while the HUD is
            # open Ctrl+Z is the HUD's, and letting an empty stack fall through
            # is precisely how scene undo deleted committed geometry.
            self.undo()
            return True
        return False

    def _step_focus(self, editor: DimensionEdit, step: int) -> None:
        """Move focus *step* fields from *editor*, wrapping at both ends.

        The field being left is committed first, so text typed without focus
        ever leaving is not discarded as a stale seed.  Its accept/reject
        verdict is recorded the same way ``values()`` records it — Tabbing past
        a rejected entry must not launder it, or the flag that blocks the
        commit would never be set.
        """
        names = self.field_names()
        if not names:
            return
        if not editor.try_commit():
            for name, ed in self._editors.items():
                if ed is editor:
                    self._mark_invalid(name)
                    break

        current = next((i for i, n in enumerate(names)
                        if self._editors[n] is editor), 0)
        nxt = self._editors[names[(current + step) % len(names)]]
        nxt.setFocus(Qt.FocusReason.TabFocusReason)
        # focusInEvent already selects all, but the single-field schema wraps
        # onto itself and so never re-enters focus.
        nxt.selectAll()

    def _accept(self) -> None:
        """Commit every field and emit ``committed`` unless something is invalid.

        ``values()`` does the force-commit, so Return read with focus still in
        a field returns what was typed rather than the seed.  It is called
        *before* the validity test because the test's answer depends on it:
        the flags are set by that very read.
        """
        values = self.values()
        if self.has_invalid_field():
            # Nothing is emitted and the HUD stays open; the red border from
            # ``_mark_invalid`` is the feedback.  Sticky by design, so a second
            # Return cannot slip the reverted value through.
            return
        self.committed.emit(values)

    # ── Validity ──────────────────────────────────────────────────────────

    def _mark_invalid(self, name: str) -> None:
        """Record field *name* as holding rejected input and restyle it."""
        self._invalid.add(name)
        self._set_invalid_style(self._editors[name], True)

    def _clear_invalid(self, name: str) -> None:
        """Retire field *name*'s invalid flag and its red border."""
        self._invalid.discard(name)
        self._set_invalid_style(self._editors[name], False)

    @staticmethod
    def _set_invalid_style(editor: DimensionEdit, invalid: bool) -> None:
        """Drive the ``invalid`` QSS property on *editor*.

        Qt resolves style-sheet property selectors once at polish time, so a
        property changed afterwards only takes effect once the widget is
        unpolished and re-polished.
        """
        editor.setProperty("invalid", "true" if invalid else "false")
        style = editor.style()
        style.unpolish(editor)
        style.polish(editor)
        editor.update()
