---
status: proposal          # system build deferred (Phase B/C); F4 naming SETTLED + Phase-A code re-keyed 2026-09-21
last-verified: 2026-10-31  # floor-opening Account: F3 Floor host strategy built, F4 instance classes, code context; rest not re-audited; prior 2026-10-24  # Editor/Build design Account: proposal pointer only, rest not re-audited; prior 2026-10-04   # F4: tier-1 label keys the Display Manager (display_category)
verified-commit: 1c1e59c6   # floor-opening (v0.76.0, merged to main); prior 58769fc5   # Editor/Build design (pointer only); prior cbfe14f     # prior 7934ccf
applies-to:
  - firepro3d/feature.py
  - firepro3d/wall_opening.py   # the first Feature (Opening); behavior today governed by wall-room-floor-system.md §7
  - firepro3d/floor_opening.py  # floor-hosted Opening instance (F3 Floor strategy); behavior governed by wall-room-floor-system.md §11.11
  - main.py                     # _last_feature keying + host_type routing of Feature Browser / ribbon entry only (F3)
  # future: firepro3d/feature_manager*.py, firepro3d/feature_editor*.py
source-tasks:
  - "todo_open.md → Opening element: Phase B Feature Manager / Phase C Feature Editor"
  - "todo_closed.md → design: settle Feature hierarchy naming (Feature > Family > Type, 2026-09-21)"
---

# Feature System — Design Spec (forged on first touch)

> **Proposed change (2026-10-24, unbuilt):** `docs/superpowers/specs/2026-10-24-editor-build-tabs-design.md` -- built-in Features' defining geometry (wall centerlines) becomes constraint-editable in plan. Until its build slices ship, the as-built text below stands.

> **Status: proposal.** This spec is **forged to close the SPEC-INDEX orphan**
> during the 2026-09-16 containment-contract design. It records the *intended*
> Feature contract. It is **not** current behavior: today only the **Opening**
> Feature exists, built with bespoke paint and governed by
> `wall-room-floor-system.md §7` (wall-hosted) and `§11.11` (floor-hosted void,
> 2026-10-31). This spec is the home the Feature system
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
Wall, Floor, Ceiling, Face, or Level/free (unhosted). Host strategy drives
placement + lifecycle (e.g. wall-hosted openings delete with their wall).

**Built strategies (as of 2026-10-31):**

- **Wall** — door / window / blank openings (`WallOpening`); placement, cut and
  lifecycle owned by `wall-room-floor-system.md §7`.
- **Floor** — the floor void (`FloorOpening`, floor-opening build 2026-10-31):
  one Type, `FEATURE_REGISTRY["floor_sketched"]` = Opening > Floor > Sketched
  (`kind` `"blank"`, `host_type` `"Floor"`; the shape is sketched, so its size
  defaults are unused). Placement, cut and lifecycle owned by
  `wall-room-floor-system.md §11.11`; build contract
  `docs/superpowers/specs/2026-10-30-floor-opening-design.md` (A5).

**Routing reads `host_type`** (its first production reader): a Feature Browser
activation (`main.py` `_on_feature_activated`) enters the `"floor_opening"` mode
for a `host_type == "Floor"` Type and the `"opening"` mode for a wall Type; the
Architecture-ribbon **Floor Opening** button enters `"floor_opening"` with the
last-used Floor Type. Because the wall Blank and the floor void share `kind`
`"blank"`, the last-used memory `_last_feature` is keyed by **`(kind,
host_type)`**, and the floor default lives in its own constant
`DEFAULT_FLOOR_OPENING_FEATURE`, apart from the kind-keyed
`DEFAULT_FEATURE_FOR_TYPE`, so the wall Blank button can never resolve to a floor
Type. Wall-side Type readers filter `host_type == "Wall"`
(`nearest_feature_for`, `WallOpening._types_for_feature`).

### F4 — Naming / storage contract (SETTLED 2026-09-21)

The Feature hierarchy is **`Feature > Family > Type`** — Revit-aligned
(`user_revit_mental_model`). This supersedes both the earlier
`Category → Type → FeatureDef` code shape *and* the interim `Class / SubClass /
Type` labels: same three tiers, canonical labels.

| Tier | Meaning | Built-in examples |
|---|---|---|
| **Feature** | class of building element | Door, Window, Opening |
| **Family**  | a family within a Feature | Single-Flush, Double-Flush, Fixed, Blank |
| **Type**    | a concrete sized preset (the leaf `.fpdf`) | 813 × 2032 |

- **"Openings" umbrella dropped** — Door/Window/Opening *are* the top-tier Features.
- **On-disk path key:** `<Feature>/<Family>/<Type>.fpdf`
  (e.g. `Door/Single-Flush/813 × 2032.fpdf`). One `.fpdf` = one **Type**,
  self-contained today (geometry + fixed sizes). A Family-definition manifest appears
  in the Family folder when the parametric engine lands; Type files then slim to
  parameter values.
- **Parametric contract locked, engine deferred:** a **Family** owns geometry +
  parameter *definitions*; a **Type** is a fixed-value preset (size is read-only per
  Type — Revit-consistent; reconciles the earlier "non-parametric" framing). The
  parametric *engine* (arbitrary parameter→geometry binding) stays deferred to the
  "Full parametrics for Features" task; today a Family ships a fixed set of Types.
- **Terminology:** "Feature" is the tier-1 classification; a *placed* occurrence is a
  **Feature instance** (today `WallOpening` and `FloorOpening`). The serialized key `feature_id` is
  **retained** (it now denotes a *Type*) — renaming a persisted key would force the
  data migration this contract exists to prevent.

**Phase-A code** (`feature.py`, landed 2026-09-21): `FeatureDef` carries `kind`
(the paint/legacy discriminator `"door"|"window"|"blank"`; `feature_label()` maps it
to the Feature name — `blank → Opening`), `family`, and `type_name`;
`features_by_hierarchy()` returns `Feature → Family → Type`. The tier-1 label also
keys the Display Manager (`WallOpening.display_category`, 2026-10-04, and
`FloorOpening.display_category`, 2026-10-31 — contract in
`wall-room-floor-system.md` §7.8.1). Built-in `id`s are
**frozen**. This contract is **locked for migration discipline** — do not re-key
on-disk libraries or `feature_id` values twice.

## Design Decisions

- **Compose Blocks rather than a separate 2D authoring path** — one 2D primitive
  vocabulary + one editor (containment contract C2). Rationale + rejected
  "siblings" alternative live in `model-space-containment-contract.md`.
- **`Feature > Family > Type`, Revit-aligned** (F4) — chosen over the code's flat
  `Category → Type` and the interim `Class / SubClass / Type` because the user's
  mental model is Revit (`user_revit_mental_model`) and the Family tier (a family
  generating multiple sized Types) has no home in the flat shape. Tier *contents*
  were identical across all three candidates — only the labels differed.
- **Built-in Features keep bespoke engines** — Wall/Floor/Roof/Room are too
  integral for the generic data-driven path today; the Feature Editor may one day
  be rich enough to author a wall generically, but not this milestone (C6/C2a).

## Acceptance Criteria (spec-forging only; build is deferred)

- [x] The orphan is closed: SPEC-INDEX points Feature modules here.
- [x] The Feature-internal contract (F1–F4) is recorded and linked to the
      containment contract for the invariants it does not own.
- [x] F4 naming **settled** (`Feature > Family > Type`) and the Phase-A code
      (`feature.py`) re-keyed to it with frozen `id`s (2026-09-21).
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
- `floor_opening.py` — the floor-hosted Opening instance (F3 Floor strategy),
  governed by `wall-room-floor-system.md §11.11`; same bespoke-paint special case.
- `feature.py` — definition/instance scaffolding + `features_by_hierarchy()`
  (Feature → Family → Type) + `feature_label()`; `FeatureDef` fields
  `kind`/`family`/`type_name` per F4.
- Future: `feature_manager*.py` (Phase B), `feature_editor*.py` (Phase C).
