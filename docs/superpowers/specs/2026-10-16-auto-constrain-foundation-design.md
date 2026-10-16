---
status: proposal          # designed 2026-10-16 (AC1 /todo run, Phase 3); unbuilt. On landing, promoted into parametric-constraint-system.md §13 + D138-D147 -- that spec becomes the one home, this doc the design record
last-verified: 2026-10-16
verified-commit: 55c78f02
applies-to:
  - firepro3d/auto_constrain.py           # NEW pure: snap-type map, handle_candidates, resolve_snap, plan_joins
  - firepro3d/constraint_controller.py    # auto_join (muted clean-only add, no undo push); PickState._candidates -> handle_candidates
  - firepro3d/geometry_drawing_controller.py  # line / polyline press capture + commit hooks
  - firepro3d/model_space.py              # _finish_polyline hook, Delete-key vertex pop, placement clear
  - firepro3d/constants.py                # AUTO_CONSTRAIN_KEY, AUTO_CONSTRAIN_MATCH_TOL_MM
  - main.py                               # Auto Constrain ribbon button (Constrain group)
  - firepro3d/graphics/Ribbon/constraint_auto_constrain_icon.svg
source-tasks:
  - todo_open.md "AC1 — Auto Constrain foundation: toggle, Shift inverter, snap→handle resolver, line / polyline joins (amends D8)" [type:feature] [P2]
  - todo_closed.md "Auto-constrain on placement …" [type:design] (2026-10-16 grill Q1-Q16)
related:
  - docs/specs/parametric-constraint-system.md   # governing spec (D8, D9, D21, D32, D43, D44, D58, §6, §8, §10)
  - docs/specs/snapping-engine.md                # OsnapResult, snap kinds, PER-from rule, pick modes take no snap
  - docs/specs/2d-geometry.md                    # §4 placement workflows (line / polyline)
  - docs/specs/ribbon-bar.md                     # §3.4 Block Editor tab groups
---

# Auto Constrain Foundation (AC1) — Design Spec

## Goal

In the Block Editor, drawing a line, reference line or polyline whose clicks land on OSNAP snaps records the matching constraints automatically, SolidWorks "automatic relations" style: a click on an existing endpoint / midpoint / centre / the origin joins the new point to it (**Coincident**); a click on an existing edge or circle / arc (nearest, perpendicular) puts the new point on it (**Point-on-curve**), and a perpendicular snap also makes the new segment **Perpendicular** to that edge. A ribbon toggle (default ON, persisted) turns the behaviour on or off; **Shift** inverts it for one click. Precision over coverage: only exact, unambiguous inferences are recorded, and anything redundant or conflicting is silently dropped.

## Motivation

Block symbols are drawn by snapping lines onto existing geometry; today the user must then re-pick every join with the Coincident tool (D8 "snaps never create constraints"). The 2026-10-16 design grill overturned D8 for placement (rulings Q1-Q16, `todo_closed.md`). AC1 is the foundation every later Auto Constrain task builds on: the toggle, the Shift rule, the snap → handle resolver, the clean-only add and the undo folding (AC2 H/V, AC3 other shapes, AC4 Offset, and the deferred INT / TAN / QUA, drag and typed-dims designs).

## Architecture & Constraints

- Governing spec: `docs/specs/parametric-constraint-system.md`. This design **amends D8** only through the Auto Constrain rule; D9 (admit + flag) stays for manual adds — auto adds are clean-only (grill Q9). D43 (Coincident record shapes, point-first), D44 (infinite line / full circle, by-construction refusal), D58 (edge midpoints are point handles) and D32 (glyph visibility) hold unchanged.
- **Pure core out, Qt shell in** (spec §3): the snap-type map, the per-item handle enumeration, the resolver and the join planner live in a new pure module `firepro3d/auto_constrain.py` (no scene writes; it reads adapters and `OsnapResult` fields). The controller owns the only write (`auto_join`); the placement controller owns capture.
- **One handle enumeration.** `PickState._candidates` already yields every item's `(kind, ref, a, b)` handles in scene space; its per-item body is lifted to `auto_constrain.handle_candidates(item, *, curvy, axes)` and `_candidates` calls it per item (GENERALIZE — the pick mode and the resolver can never disagree about what a handle is). Nested block handles (`<path>:<h>`, D105) arrive through `_NestedAdapter` with no special case.
- **Editor only.** Capture runs only when `scene.constraint_ctl.enabled` (the `block_editor` role); the plan scene never records a join (C1/C8).
- File format: unchanged. Joins are ordinary `coincident` / `point_on_curve` / `perpendicular` records (§6.3). No schema bump.
- Constants in `firepro3d/constants.py` (`AUTO_CONSTRAIN_KEY`, `AUTO_CONSTRAIN_MATCH_TOL_MM`); no magic numbers.

## Design Decisions

Ratified at this run's human gates (Phase 2 FP1 questions + the Phase 3 section approvals + the icon mockup gate, 2026-10-16), on top of the grill's Q1-Q16:

| # | Decision |
|---|---|
| AD1 | **Toggle (Q2):** a small checkable **Auto Constrain** button in the Block Editor Constrain group, after Collinear; state = QSettings `constraint/auto_constrain` (`constants.AUTO_CONSTRAIN_KEY`), default **True**, read at each press (no per-scene flag — every open editor follows one key, as D61's terminator key). The button mirrors the key; editor-only like its group. Icon **B** (mockup gate): the shipped Coincident junction + an accent 8-point spark, `constraint_auto_constrain_icon.svg`, 40-unit two-token (D25), in the `_CONSTRAINT_ICONS` guard. Tooltip: "Auto Constrain — add Coincident / On-curve / Perpendicular from the snaps you place with (Shift inverts for one click)". |
| AD2 | **Shift per click (Q3/Q4):** at each placement press, `infer = toggle XOR Shift`. Ctrl stays the 45° angle lock. |
| AD3 | **Capture at press:** when `infer` and `ctl.enabled`, the click's live `scene._snap_result` (set by `get_effective_position` just before the press handler) is resolved at once into a target and stored **with the committed point**. Line click 1 → the anchor's join slot; line click 2 → used in the same press; polyline → a per-vertex list on the geometry controller. |
| AD4 | **Exact-point validity:** a stored target is used only if its snap point equals the committed vertex within `AUTO_CONSTRAIN_MATCH_TOL_MM` (1e-3 mm). This one check drops the Ctrl lock (tip projected off the snap), an anchor re-armed by another path (track first point, HUD) and a popped-then-re-clicked vertex. |
| AD5 | **Typed points (Q11 + FP1):** a point committed from Dynamic Input carries no join; joins are **per click** — a line whose 1st click snapped and whose 2nd point was typed keeps its 1st click's join. |
| AD6 | **Resolver (`resolve_snap`):** `origin` → `{"ref": "origin"}` (a point); `endpoint` / `midpoint` / `center` → the `source_item`'s **point** handle at the snap point (nearest within tol; none → no join); `nearest` / `perpendicular` → the source's **edge** (`edge`, `s<i>`, rect / polygon / text side) whose segment holds the point, else a **curve** (circle / arc `curve`) it lies on. Everything else — `intersection`, `quadrant`, `tangent`, `align_path` / `align_intersection`, the grid fallback (no `OsnapResult`), a `source_item` with no adapter (spline, D5; non-participants) — resolves to nothing, **silently** (FP1). Targets = exactly the manual Coincident pick set (Q15): hidden handles never, text / nested / reference shapes in. |
| AD7 | **Join records (`plan_joins`, Q5):** point target → `coincident [new point, target]`; edge / curve target → `point_on_curve [new point, target]` (point-first, D43); a `perpendicular` snap on an **edge** also → `perpendicular [incoming segment, target edge]`. PER only exists from a placement start point (`snap_engine._foot_snaps`), so it is always a 2nd+ click and its segment is the incoming one (line `edge`; polyline `s<i-1>`). PER onto a circle / arc is a radial foot → `point_on_curve` only (no perpendicular-to-curve type). |
| AD8 | **Polyline at finish (FP1):** vertex targets are captured per press but the records are planned and added once, at finish (Enter / double-click / close-on-start), against the final item — so Esc / cancel leaves nothing to roll back. A 2-vertex finish (→ `LineItem`, S3b) remaps `v0`/`v1` → `p1`/`p2`, `s0` → `edge`, `m0` → `mid` and the polyline's own uid (a self-target) → the line's. The close-on-start click adds no join (closed by construction). Delete (`_delete_or_pop_polyline_vertex`, remove last vertex) pops that vertex's target. |
| AD9 | **Clean-only add (Q9) — `ConstraintController.auto_join(records)`:** each record goes through `add(..., _commit=False)` with the controller's status **muted** (a refusal — invalid, D44 by-construction — posts nothing); a refused record is skipped, a **red** one is popped (its id discarded from `red`; nothing was written, D10), a **redundant** one (`diagnostics().redundant`) is popped. Then one settle — D37 red re-check, `_commit_gen` bump, repaint, state notify, panel refresh — **without** `push_undo_state`. |
| AD10 | **One undo step (Q10):** the placement's own push (`_commit_draw_line_at`; the polyline finish / close) runs after `auto_join`, so shape + joins are one undo step; no status line — the new item is selected, so its glyphs (D32) are the feedback. |

## Acceptance Criteria

- [ ] With Auto Constrain ON, a line drawn from an existing line's endpoint (END) records one `coincident` on the right handles; a midpoint (MID) click records `coincident` on `mid` / `m<i>`; a circle centre (CEN) on `center`; the origin on `{"ref": "origin"}`.
- [ ] A click on an existing edge with NEA records `point_on_curve [new point, edge]`; on a circle / arc outline `point_on_curve [new point, curve]`.
- [ ] A PER snap on an edge records `point_on_curve` + `perpendicular [new segment, edge]`.
- [ ] Polyline: each vertex's snap joins at finish; a 2-vertex finish's joins land on the resulting line's `p1` / `p2`; Esc leaves no records; Delete (pop the last vertex) drops the popped vertex's join.
- [ ] Shift inverts per click both ways (ON + Shift → no join on that click; OFF + Shift → join).
- [ ] A typed (Dynamic Input) point gets no join; the other, clicked point keeps its own.
- [ ] Ctrl-locked tip off its snap → no join on that click.
- [ ] A redundant or conflicting inference leaves no record and posts no status; a refused one (D44) posts no status.
- [ ] One Ctrl+Z removes the shape and its joins together; redo restores both.
- [ ] Save → close → reopen keeps the join records.
- [ ] The toggle round-trips QSettings (under the conftest isolation); default ON; the button mirrors it.
- [ ] Plan scene: drawing a line on a snap records nothing (controller inert).
- [ ] Spec: D8 amended; new §13 Auto Constrain + D138-D147; §10 ribbon line; pointers from `2d-geometry.md` §4 and `snapping-engine.md` §3.

## Verification Checklist

- [ ] Guards (VC3) drive the real path: posted mouse presses on a shown Block Editor view with OSNAP on (`win_with_editor` / `be` fixtures), real snaps, assert the stored constraint records (type + refs) — each shown RED with its rule reverted.
- [ ] Pure resolver unit tests: one per snap kind × source class (line, rect, polyline, polygon, circle, arc, text, nested instance), plus the silent-nothing kinds.
- [ ] `PickState` keep-green: every existing pick-mode test passes after the `handle_candidates` lift (VC5).
- [ ] Icon passes `test_icon_theming.py` (`_CONSTRAINT_ICONS`).
- [ ] Full suite on the final tree (VC6 — Large tier).
- [ ] User smoke from the Phase 6 checklist.

## Existing Code Context

- `OsnapResult` (`snap_engine.py`): `point, snap_type, source_item, source_item2, source_lines, name` — no handle identity; `name` is wall-only. A placed block reports the block as `source_item` (block snap parity), so its handles are the nested ones.
- `Model_Space.get_effective_position` overwrites `_snap_result` on every move and returns the raw cursor in `constrain_*` pick modes; the press handler runs right after it, so the press reads the click's own snap.
- `GeometryDrawingController._press_draw_line` / `_commit_draw_line_at` (the commit pushes undo), `_press_polyline` / `_commit_polyline_at` (no push) / close-on-start (push); `Model_Space._finish_polyline` (Enter / double-click; 2-vertex → `LineItem`); the Delete-key vertex pop `_delete_or_pop_polyline_vertex`; HUD appliers (`_APPLIER_FOR_MODE`) call the `_commit_*_at` halves directly.
- `ConstraintController.add(_commit=False)` appends + solves + marks red without `_committed()`; `diagnostics()` is keyed on the constraint tuple, so it is fresh right after; `_identically_satisfied` covers `point_on_curve` / `perpendicular` (D44 / D113), not `coincident`.
- `_PARTICIPATING` includes `_polylines`, so the active chain is a participant mid-placement.

## Edge Cases & Error Handling

- Snap on a hidden handle's position (text `ins`) → the visible handle at that point if any, else nothing.
- Two handles at one point (a closed polyline's `v0` vs the chain under placement): the source item decides; on one item the first exact point wins (points before edges, D58).
- A polyline vertex snapped onto its own earlier vertex / segment → a same-item record (D44: legitimate); a closing click is handled by close-on-start.
- Item deleted between capture and finish: not reachable (no edit runs mid-placement); a ref that no longer resolves is refused by `add` (muted) and skipped.

## Code Style & Testing

Google docstrings, relative imports inside `firepro3d/`, constants in `constants.py`; tests under `tests/` (pytest + pytest-qt, the conftest QSettings isolation).
