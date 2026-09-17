---
status: proposal
last-verified: 2026-09-16
verified-commit: bf332b2
applies-to:
  - firepro3d/feature.py
  - firepro3d/wall_opening.py   # the first Feature (Opening); behavior today governed by wall-room-floor-system.md §7
  # future: firepro3d/feature_manager*.py, firepro3d/feature_editor*.py
source-tasks:
  - "todo_open.md → Opening element: Phase B Feature Manager / Phase C Feature Editor"
  - "todo_open.md → design: settle the Feature hierarchy naming"
---

# Feature System — Design Spec (forged on first touch)

> **Status: proposal.** This spec is **forged to close the SPEC-INDEX orphan**
> during the 2026-09-16 containment-contract design. It records the *intended*
> Feature contract. It is **not** current behavior: today only the **Opening**
> Feature exists, built with bespoke paint and governed by
> `wall-room-floor-system.md §7`. This spec is the home the Feature system
> converges to when Phase B (Manager) / Phase C (Editor) are built.
>
> The **containment invariants** (what a Feature may contain, where it lives)
> are owned by `model-space-containment-contract.md` (C2, C6). This spec owns the
> **Feature-internal contract**; it links up and does not restate those (Rule A).

## Goal

Define what a **Feature** is: the modeled, placeable building-element cousin of a
Block. A Feature answers "how does this real-world building object represent
itself in plan, in each elevation, and in 3D — and how is it hosted?"

## Motivation

The application needs an extensible way to add building objects (doors, windows,
casework, fixtures, equipment, diffusers) without hand-coding a bespoke class per
object the way Wall/Floor/Roof/Room are coded. Features are that system:
data-driven definitions, placed as instances, hosted onto model geometry. See
`project-suite-vision`.

## Architecture & Constraints

### F1 — A Feature composes Blocks (from the containment contract, C2)

A Feature definition =
`{ plan Block + elevation Block(s) + 3D geometry + parameters + host strategy }`.
The 2D representations are **Blocks** (authored in the Block Editor); the Feature
references them. Representations are **independently authored** — the plan symbol
is not auto-derived from the 3D (e.g. a door is open in plan, closed in 3D), per
`wall-room-floor-system.md §7.8`.

### F2 — Classification: Building vs Architectural (from C6)

- **Building Features** — Wall / Floor / Roof / Room (+ structural). **Built-in
  Features**: they satisfy the Feature *concept* but keep their bespoke
  parametric engines (`wall-room-floor-system.md`) and bespoke representations
  (they do **not** compose Blocks — the C2a exception). Not rewritten into the
  data-driven path in this milestone.
- **Architectural Features** — openings, casework, fixtures, equipment,
  diffusers, etc. Library-authored, data-driven, compose Blocks (F1).

### F3 — Host strategies

A Feature declares a `host_type` (per `wall-room-floor-system.md §7.16`):
Wall (openings — the only one built), Floor, Ceiling, Face, or Level/free
(unhosted). Host strategy drives placement + lifecycle (e.g. wall-hosted
openings delete with their wall).

### F4 — Naming / storage contract (locked 2026-09-04, `block-system.md`)

3-tier `Class / SubClass / Type` folders; `.fpdf` type-definition files;
non-parametric (size = read-only attribute of the Type). Openings decompose into
`Door` / `Window` / `Opening` Classes. This contract is **locked for migration
discipline** — do not re-key on-disk libraries twice.

> **Open naming question (deferred):** `feature.py` currently uses
> `Category → Type → FeatureDef`, but the user's Revit-aligned model expects
> `Category → Family → Type` (`user_revit_mental_model`). Settle before Phase B
> ships any on-disk keys. Tracked in `todo_open.md`.

## Design Decisions

- **Compose Blocks rather than a separate 2D authoring path** — one 2D primitive
  vocabulary + one editor (containment contract C2). Rationale + rejected
  "siblings" alternative live in `model-space-containment-contract.md`.
- **Built-in Features keep bespoke engines** — Wall/Floor/Roof/Room are too
  integral for the generic data-driven path today; the Feature Editor may one day
  be rich enough to author a wall generically, but not this milestone (C6/C2a).

## Acceptance Criteria (spec-forging only; build is deferred)

- [x] The orphan is closed: SPEC-INDEX points Feature modules here.
- [x] The Feature-internal contract (F1–F4) is recorded and linked to the
      containment contract for the invariants it does not own.
- [ ] Phase B (Manager) / Phase C (Editor) builds converge to F1–F4 and
      re-stamp this spec `partial`/`current` as code lands.

## Verification Checklist

- [x] `status: proposal` — reads as design, not current behavior.
- [x] Rule A — containment invariants linked, not restated; naming contract
      linked to `block-system.md`, not duplicated.
- [x] SPEC-INDEX orphan row promoted to a governing-spec row.

## Existing Code Context

- `wall_opening.py` — the first Feature (Opening), bespoke paint, governed today
  by `wall-room-floor-system.md §7`. An early special case that reconciles to F1
  (compose a plan Block) when the Feature system is built out (C2a).
- `feature.py` — current definition/instance scaffolding + `features_by_category()`.
- Future: `feature_manager*.py` (Phase B), `feature_editor*.py` (Phase C).
