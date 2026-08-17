---
status: proposal
last-verified: 2026-08-17
verified-commit: feef032
applies-to:
  - firepro3d/dynamic_input.py   # new
  - firepro3d/model_space.py
  - firepro3d/model_view.py
  - firepro3d/dimension_edit.py
  - firepro3d/scale_manager.py
  - firepro3d/node.py
source-tasks:
  - "TODO.md — Dynamic Input engine — extract + generalize (§4)"
---

# Dynamic Input HUD — Design Spec

> **Governing spec:** `docs/specs/inferred-dimension-driven-placement.md` §4. On
> completion this design replaces §4 **in place** — no parallel spec file. §4.2,
> §4.3 and §4.6 as written today are superseded; see *Divergences from current
> §4*.

## Goal

One editable, cursor-following HUD that both **reports** the live geometry of an
in-progress placement and **accepts** typed values to drive it precisely —
replacing today's two disconnected surfaces (the read-only Dim HUD and the modal
`_DynInput` dialog) across every placement and transform mode.

## Motivation

Today the same numbers exist twice. `Model_View.drawForeground` block 4 paints a
read-only "Dim HUD" from `Model_Space._draw_dim_hint`; pressing Tab (or a digit)
opens `_DynInput`, a **modal frameless `QDialog` defined as a local class nested
inside `_handle_tab_input`**, instantiated ad hoc at 8 call sites. Consequences:

- The editable path is unreachable except through a modal that blackholes the
  canvas — the drawing cannot be seen updating while typing.
- Field types are string-sentinel'd (`"°"` angle, `"#"` count, else dimension);
  each call site rebuilds its own field tuples.
- It duplicates `DimensionEdit`, the house numeric widget, and does it worse:
  `_DynInput.value()` **returns `0.0` on parse failure**, silently committing
  geometry at zero. `DimensionEdit` reverts to last-valid.
- Every mode's commit logic is duplicated between the click path and the Tab
  path — `draw_rectangle` builds a `RectangleItem`, appends to `_draw_rects`,
  clears the preview and pushes undo in *two* places.
- Nothing is reusable: adding dynamic input to pipe/wall means copying the
  pattern a ninth time.

Organising by **geometric primitive** rather than entity type is the leverage:
pipe, wall, gridline, polyline and the line tool are all *a line from an anchor*,
so one Line schema serves five clients.

## Architecture & Constraints

**Dynamic input is not a geometry engine.** `snap_engine.py` and
`inference_engine.py` are pure, Qt-free `resolve(cursor, refs) -> result`
resolvers. Dynamic input is an *interaction component*: it consumes a resolved
position and produces a committed one. It stays where §3.1 of the governing spec
puts it — coordinated at the `Model_Space` seam alongside inference, **not** a
third peer engine.

### The core idea

**Dynamic input is an alternative *point source*, not an alternative *commit
path*.** The HUD resolves typed values into the same point the mouse would have
produced, then calls the commit path the click already uses. One commit per mode,
reached from either input method. Commit parity stops being something tests must
catch and becomes structural.

```
                    cursor mode                        input mode
                         │                                  │
   mouse move ──► get_effective_position ──┐        typed text
                         │                │             │
                  _constrain_angle /       │      DimensionEdit.commit()
                  snap_point_45            │             │
                         │                 │      schema.resolve(anchor, values)
                         ▼                 │             │
              publish_placement_state ─────┤             │
                (resolved point +          │             │
                 HUD readout)              │             │
                         │                 ▼             ▼
                    click ──────────►  applier(point | params)
                                            │
                                    existing commit path
                              (item + undo + preview cleanup)
```

### Two exclusive modes

Cursor mode and input mode never overlap. There is no "pin a field and keep
sweeping" state — the user is either picking a point on screen or typing an exact
one.

| | Cursor mode | Input mode |
|---|---|---|
| HUD | live, read-only | editable, focused |
| Mouse / cursor | drives geometry (OSNAP + inference + Ctrl) | **inert** |
| Drives the value | cursor | keyboard |

### Module boundary

**`dynamic_input.py` (new)** — no `QGraphicsScene` knowledge.

- `FieldKind` — `DIMENSION` / `ANGLE` / `COUNT`. Three `DimensionEdit` configs,
  not three widgets.
- `FieldSpec(name, label, kind, minimum=None)` — declarative descriptors.
- `Schema(name, fields, resolve)` — registry of the six schemas.
- `resolve(anchor, values) -> QPointF | dict` — pure functions, testable with no
  scene and no `QApplication`.
- `DynamicInputHud(QWidget)` — builds `DimensionEdit`s from a `Schema`, parents
  to `view.viewport()`, positions near the cursor reusing the painted HUD's
  edge-flip logic. Emits `committed(dict)` / `cancelled()`.

**`Model_Space`** — owns interaction state: mode→schema mapping,
`get_placement_anchor()`, `publish_placement_state()`, the appliers, and
engage-key detection in `keyPressEvent`.

**`Model_View`** — viewport concerns only: hosting the widget, repositioning on
scroll/zoom, and key routing so Esc and Ctrl+Z still reach the scene.

### Seeding invariant (WYSIWYG)

**As-built bug:** `_last_scene_pos` (`model_space.py`) stores the **raw** cursor,
and `_defaults_from` seeds from it. Every mode computes its final constrained
point (`_constrain_angle`, `snap_point_45`) as a throwaway local inside
`mouseMoveEvent`. Today's `_DynInput` therefore seeds from an unconstrained
position — the HUD can open showing numbers that do not match what is on screen.

**Fix:** `publish_placement_state(anchor, point)`, called once per mode per frame
at the point where that mode has finished constraining its position — i.e.
exactly where `_draw_dim_hint` is assigned today. It stores the resolved point
for the HUD to seed from and derives the readout string *from the active schema*
instead of hand-formatting it. One helper closes the seed bug, collapses the
scattered `_draw_dim_hint` assignments, and makes the live readout and the seeded
values the same numbers by construction.

### Reuse ledger (binding — from the Phase-1b reuse sweep)

| Need | Existing — reuse as-is |
|---|---|
| Numeric field | `DimensionEdit` — `parser`/`formatter`/`minimum` hooks collapse dimension/angle/count into three configs of one widget; `_seed_text` guard and revert-to-last-valid already solve seeding and bad parse |
| Commit-before-action | `DimensionDelegate.setModelData` → `editor.commit()` |
| Viewport-child editing widget | `Model_View._start_spacing_edit` already parents a `QLineEdit` to `self.viewport()` |
| Overlay position/edge-flip | Dim HUD, `model_view.py` `drawForeground` block 4 |
| Seed value | `Model_Space.get_effective_position` |
| Ctrl angle constraint | `Model_Space._constrain_angle` |
| Undo boundary | `Model_Space.push_undo_state` |
| Exit ladder | `Model_Space.keyPressEvent` Esc ladder |

### Generalize (collapse in the same change)

1. `_defaults_from(anchor)` — promote out of `_handle_tab_input`; it is the seed
   contract for every schema.
2. **`get_placement_anchor()`** — one accessor replacing the ad-hoc anchor
   variables of the in-scope modes (`node_start_pos`, `_polyline_active`,
   `_draw_line_anchor`, `_draw_rect_anchor`, `_draw_circle_center`,
   `_wall_anchor`). Without it the HUD adds a seventh. `_cline_anchor` is
   excluded — `construction_line` is out of scope.
3. `_draw_dim_hint` assignments collapse into `publish_placement_state`.
4. Digit-key type-to-seed is hard-gated to four modes; the engage-set rule makes
   it schema-driven.

## Design Decisions

### Settled in Phase 2 (binding)

1. One editable HUD; `_DynInput` and its nested class are deleted.
2. Two exclusive modes (above).
3. Engage set: `0-9`, `.`, `-`, `Tab`. Letters, F-keys and other modifier-held
   combinations pass through.
4. WYSIWYG seeding from the resolved position, never the raw cursor.
5. Enter commits; Esc returns to cursor mode ahead of the existing ladder.
6. Schemas organised by geometric primitive.
7. Pipe angle relative-when-connected (45° multiples, validated), absolute-when-free.
8. `DimensionEdit` backs every field.
9. Field parse/commit happens before placement commit.

### A — HUD rendering: viewport-child `QWidget`

A small frameless widget parented to `view.viewport()`, moved to follow the
cursor.

*Rejected — painted (extend `drawForeground`):* would hand-roll caret, selection,
Home/End, backspace and IME — reimplementing precisely the redundancy this task
removes — and cannot use `DimensionEdit` at all.

*Rejected — `QGraphicsTextItem` (the `TextAnnotationItem` route):* real editing
for free, but it is a *scene* item — needs counter-scaling against zoom, Z-order
care, and `contains()`+`shape()` overrides, and inherits the known paint-culling
and stale-drag-trail traps. Still no `DimensionEdit`.

*Chosen because:* it is the only route where `DimensionEdit` drops in unchanged,
so parser/formatter/minimum, the seed guard and revert-to-last-valid all come
free — and revert-to-last-valid is what kills the `_DynInput.value() → 0.0` bug.
Viewport coordinates mean no zoom fighting. `_start_spacing_edit` establishes the
pattern, so this is not new machinery. **Cost:** keyboard-focus routing (below).

### Keybindings — Tab is universal, Space takes the displaced jobs

`Tab` is bound today in three modes, and `_handle_tab_input` returns early for
each: `select` (cycle similar elements), `pipe` (cycle Z-stacked node
candidates), `wall`/`wall_rect` (cycle alignment Center→Left→Right). Those jobs
move to **Space**, which is unbound throughout the codebase (`Key_Space` appears
nowhere in `firepro3d/` or `main.py`).

| | Cursor mode | Input mode |
|---|---|---|
| **Tab** | engage input mode — universal | next field |
| **Shift+Tab** | — | previous field (native Qt focus chain; no binding needed) |
| **Space** | cycle the ambiguity (select: similar elements · pipe: Z-stacked candidates · wall: alignment) | **types a literal space** — required for `12' 6"` and `3 ft` |

Carve-out: the "modifier-held passes through" rule holds for every combination.
Claiming Space forecloses AutoCAD's "Space repeats last command" if that is ever
wanted.

### B — Angle convention: static methods on `ScaleManager`

`format_angle(deg) -> str` and `parse_angle(text) -> float | None`, mirroring
`parse_dimension`'s existing `@staticmethod` shape. Every `DimensionEdit`
consumer already holds a `ScaleManager`, and future clients (gridline angle in
the property panel, the rotate dialog, wall angle) find them where they would
look. Rejected: private to `dynamic_input.py` — the first other consumer would
copy them.

- **Display:** decimal degrees with the `°` glyph inside the string (`45°`,
  `-16.4°`), trailing zeros trimmed, two-decimal cap. Folding the glyph in means
  one `DimensionEdit` with a `formatter` and no sibling label widget.
- **Parse:** bare number = degrees; optional trailing `°` or `deg`; negatives
  accepted. Anything else → `None`, routing into revert-to-last-valid.
- **Range:** normalize display to −180…180, matching what `_defaults_from`
  already produces from `atan2`. Any input accepted and normalized, so `270`
  yields `-90°`.
- **Convention:** Y-up, 0° = right, 90° = up — already the house convention.
- **Precision:** *not* tied to `sm.precision`, which drives fractional-inch
  denominators and is meaningless for angles.

This convention is written into `docs/specs/units-and-formatting.md`, not only
into code (Rule A — one fact, one home).

### C — Schemas produce geometry; `Model_Space` applies it

Contract: `schema.resolve(anchor, values) -> geometry`, where *geometry* is a
point (or point pair) for placement schemas and a parameter dict for transform
schemas. `Model_Space` dispatches to the matching applier — placement appliers
are the existing click-commit paths; transform appliers are the three small
blocks that already exist.

*Rejected — schemas own their own commit (status quo, relocated):* cheapest, but
preserves two commit paths per mode forever and forces `dynamic_input.py` to know
about `RectangleItem`, `_draw_rects` and `_get_geometry_template()`, so the module
could not be scene-free or unit-testable without Qt.

### D — Chained modes

- **`construction_line` is dropped from scope.** `ConstructionLine`'s `pt1`/`pt2`
  only set *direction* — `_recompute_line()` extends the drawn line far past both
  points so it reads as infinite. Its Length field is a **visual no-op** today.
  Retiring the tool in favour of alignment guides is a separate task (see
  Follow-ups).
- **Enter closes the HUD**, commits the segment, and returns to cursor mode for
  free placement — including for `polyline` and `pipe`. Rejected: staying open
  and re-seeding for chained runs; it adds a rung to the Esc ladder in exactly
  the modes where exiting is most common.

### E — Scope and order

- **Slice 1 — machinery + proof:** Line schema on `draw_line`/`draw_gridline`.
  Best proving ground: both already have digit type-to-seed and existing tests,
  and they exercise both hard field kinds (dimension and angle). Everything
  architectural lands here — `dynamic_input.py`, the HUD widget,
  `get_placement_anchor()`, `publish_placement_state()`, `format_angle`/`parse_angle`.
- **Slice 2 — fan-out over existing call sites:** rectangle, circle, polyline,
  move, gridline offset/array. **`_DynInput` is deleted at the end of this
  slice** — every behavior that exists today exists in the new system.
- **Slice 3 — new clients:** wall, then pipe.
- **B5 lands as the first commit on the branch** (see Prerequisites), because
  pipe's relative-angle field encodes the bug otherwise.
- **`draw_arc` deferred.** `_draw_arc_step` runs centre → start → end, so its
  field set changes per step — a schema-lifecycle feature nothing else needs.

### Divergences from current §4 (corrected in place)

- §4.2 "angle … Read-only (display only)" and "**Non-overridable**" for pipes —
  superseded. Fitting validity is preserved by *validating* the typed angle, not
  by forbidding it.
- §4.6 "the angle is locked to the nearest 45° increment **at all times**" — not
  true of the code: a pipe with no connections free-draws with a soft 7.5° snap.
  The lock is relative to the reference pipe and only when connected.
- §4.3 "Move cursor → length/angle update live" *and* "Type digits" as concurrent
  behaviours — superseded by two exclusive modes.
- §4.2 lists `construction_line` under Length+Angle — dropped (Length is a no-op).

## Input / Output

Six schemas, ten client modes.

| Schema | Fields | `resolve()` returns | Clients |
|---|---|---|---|
| **Line** | Length `DIMENSION` (min 0) · Angle `ANGLE` | point = anchor + L∠θ | `draw_line`, `draw_gridline`, `polyline`, `wall`, `pipe` |
| **Rectangle** | X `DIMENSION` · Y `DIMENSION` | `(pt1, pt2)`, honoring `_draw_rect_from_center` | `draw_rectangle` |
| **Circle** | Radius `DIMENSION` (min 0) | radius; centre is the anchor | `draw_circle` |
| **Displacement** | dX `DIMENSION` · dY `DIMENSION` | offset `QPointF` (Y-up → Y-down flip) | `move` |
| **Distance** | Distance `DIMENSION` | float | `gridline_offset` |
| **SpacingCount** | Spacing `DIMENSION` · Count `COUNT` (min 1) | `{spacing, count}` | `gridline_array` |

### Client specifics

**Wall** is just another Line client. Alignment (Center/Left/Right) is a
*template* property cycled with Space, not a geometry field.

**Pipe** carries the only real logic, all in the angle field:

- Anchor is `node_start_pos`.
- **Connected** (`node_start_pos.pipes` non-empty) → field labelled **`Rel Angle`**,
  value relative to the reference pipe, validated as a 45° multiple. A
  non-multiple is **rejected with a status reason, never rounded** — rounding
  would place a pipe the user did not ask for and assign it a fitting
  classification they did not choose.
- **Free** (no connections) → field labelled **`Angle`**, absolute, any value.
  The 7.5° soft snap remains a cursor-mode behavior; a typed angle is exact.

## Edge Cases & Error Handling

All of it routes through behavior `DimensionEdit` already has.

| Case | Behavior |
|---|---|
| Unparseable text | Revert to last valid, no signal. Kills the `_DynInput.value() → 0.0` bug. |
| Enter with an invalid field | Field reverts, **placement does not commit**, HUD stays open. |
| Pipe angle not a 45° multiple when connected | Rejected with a status reason; HUD stays open. |
| No anchor yet (nothing clicked) | HUD does not engage; digits fall through. `get_placement_anchor() is None` is the single gate. |
| Zoom/scroll while in input mode | Allowed; HUD stays anchored where it opened rather than chasing an inert cursor. |

### Keyboard-focus hazards (the real cost of route A's rejection)

1. **Escape vs. the window-level `QShortcut`.** `main.py` binds Escape
   window-wide, and a window `QShortcut` beats a focused widget unless that
   widget accepts the `ShortcutOverride` event. `DynamicInputHud` accepts
   `ShortcutOverride` for `Key_Escape` while open — the mechanism paper-space
   already uses. Without it, Esc skips the HUD rung and cancels the whole mode.
2. **`Ctrl+Z` differs by mode, deliberately.** `QLineEdit` owns text undo, so a
   focused field consumes Ctrl+Z regardless. **Input mode: text undo** (standard
   in every application). **Cursor mode: scene undo**, never swallowed by the
   engage-set check — which is what the "modifier-held passes through" rule was
   protecting.
3. **`Enter` ordering.** `DimensionEdit` commits on `editingFinished`, which does
   *not* fire when Return is pressed without focus leaving. The HUD calls
   `edit.commit()` on every field before reading values — the same fix
   `DimensionDelegate.setModelData` already carries. Missing this silently
   commits stale seeded values.

## Acceptance Criteria

- [ ] Every mode with a `_DynInput` call site today works through the new HUD
      with **identical commit results**: move dX/dY, line Length/Angle, rectangle
      X/Y, polyline, gridline offset, gridline array Spacing/Count, circle Radius.
- [ ] `wall` and `pipe` gain dynamic input via the Line schema.
- [ ] The HUD renders live and read-only during cursor mode for all placement
      primitives.
- [ ] Typing `0-9` / `.` / `-` / Tab enters input mode and the first keystroke
      lands in the primary field; letters and other modifier combinations pass
      through.
- [ ] Space cycles the ambiguity in cursor mode (select / pipe candidates / wall
      alignment) and types a literal space in input mode.
- [ ] Entering input mode seeds from the **resolved** position — verified with
      OSNAP active, with inference active, and with Ctrl held.
- [ ] In input mode, mouse movement and clicks do not alter pending geometry.
- [ ] Enter commits the focused field's typed text even without leaving the field.
- [ ] Invalid input reverts to last valid — **no commit at 0.0**.
- [ ] Esc returns to cursor mode without cancelling the mode; the existing ladder
      is unchanged below that.
- [ ] Connected pipes accept only 45° multiples relative to the reference pipe
      (rejected, not rounded); free pipes accept any angle.
- [ ] `_DynInput` and the nested class in `_handle_tab_input` are **deleted**.
- [ ] The `QTimer` + `activeModalWidget` dance in `tests/test_gridline_seed.py`
      is removed — no modal left to drive.
- [ ] `get_placement_anchor()` exists and the in-scope ad-hoc anchor reads route
      through it.
- [ ] `publish_placement_state()` exists and the scattered `_draw_dim_hint`
      assignments route through it.

## Code Style & Testing

Three layers. Behavior-exercising tests only — no `inspect.getsource` guards.

**(a) No Qt.** Schema field specs; `resolve()` for all six schemas;
`format_angle`/`parse_angle` round-trips; angle normalization (`270` → `-90°`);
pipe 45°-multiple validation. Pure functions, no `QApplication`.

**(b) Widget-driven**, using the session-scoped `qapp` fixture and real
`QTest.keyClick` — never slot calls (slot-level tests pass while signal wiring is
broken):

- digit engages and the keystroke lands in field 1; Tab engages with field 1 selected
- Tab advances, Shift+Tab reverses
- Space types a space in input mode, cycles in cursor mode
- Enter commits typed text *without* leaving the field — red-verified by stashing
  the `commit()` call
- Esc returns to cursor mode and does **not** cancel the mode — must be a real key
  event, not a slot call (the window-`QShortcut` trap)
- mouse move/click inert while input mode is active
- Ctrl+Z reaches scene undo in cursor mode; is text undo in input mode

**(c) Commit parity**, per schema: drive a placement by mouse and by HUD, assert
identical resulting geometry. Largely structural under the chosen design — both
paths call the same applier — so these guard the `resolve()` math.

Each changed behaviour red-verified (test fails with the fix stashed). Full suite
before "done" (two halves if it flakes). Do **not** reassign sip methods such as
`QDialog.exec` — it corrupts the C++ slot binding process-wide.

## Verification Checklist

- [ ] All acceptance criteria met
- [ ] Tests pass at all three layers; full suite green
- [ ] No regressions in gridline placement/offset/array, move/paste, line tools,
      wall placement, or pipe placement
- [ ] Governing spec `inferred-dimension-driven-placement.md` §4 rewritten **in
      place**, `[PROPOSAL]` markers cleared, frontmatter stamped
- [ ] Angle convention landed in `units-and-formatting.md` (Rule A)
- [ ] `pipe-placement-methodology.md` updated for the B5 fix and stamped
- [ ] `SPEC-INDEX.md` updated with `dynamic_input.py`

## Dependencies & Prerequisites

- **B5 — first commit on the branch.** `Node.snap_point_45` picks its reference
  from `self.pipes[0]` (insertion order) rather than the contextual pipe, so the
  45° grid is misaligned when branching
  (`docs/specs/pipe-placement-methodology.md` §4.1). Own tests; pipe's
  relative-angle field is not trustworthy until it lands.
- **Angle convention** must be written into `units-and-formatting.md` before the
  Line schema fans out to five clients.

## Tech Context

- **Framework:** PyQt6; `QGraphicsScene`/`QGraphicsView` (`Model_Space` /
  `Model_View`).
- **Units:** geometry in mm; display/parse owned by `ScaleManager`
  (`format_length` / `parse_dimension` / `bare_number_unit`).
- **Testing:** no `pytest-qt`; session-scoped `qapp` fixture in `conftest.py`.

## Follow-ups (not in this slice)

Logged in `TODO.md`:

- Retire construction lines in favour of alignment guides — wired into 11
  modules; existing `.fpd` files hold `{"type": "construction_line"}` records, so
  the load path needs a decision, not just deletions.
- `DimensionEdit` arithmetic input (`3ft - 1.5ft` → `1'-6"`).
- Migrate remaining hand-rolled numeric inputs (`array_dialog.py`,
  `calibrate_dialog.py`, `main.py`, and `Model_View._start_spacing_edit`) to
  `DimensionEdit`.
- `draw_arc` dynamic input — per-step field sets.
