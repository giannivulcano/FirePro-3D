---
status: proposal
last-verified: 2026-09-17
verified-commit: a624ed3
applies-to:
  - firepro3d/underlay.py
  - firepro3d/block_definition.py
  - firepro3d/block_instance.py
  - firepro3d/model_space.py   # placement + reference rendering
source-tasks:
  - "todo_open.md → design: Underlay reference-graphic unification (contract C4)"
---

# Reference Graphic Model — Block ↔ Underlay Unification — Design Spec

> **Status: proposal (target architecture).** Resolves the deferred **C4** of
> `model-space-containment-contract.md`. Records the *intended* unification: an
> Underlay is a **special case of a Block** — both are **imported/placeable
> reference geometry**. Today they are two separate systems (see the Divergences
> ledger); this spec is the direction they converge to. **Implementation is
> gated on a performance spike (R4) and is not scheduled here.**
>
> Rule A: mechanics owned elsewhere are linked, not restated — rendering/cache
> mechanics → `underlay-workflow.md`; definition/flyweight → `block-system.md`;
> the model-space containment invariants (C1/C3) → `model-space-containment-contract.md`.

## Goal

Give the user a single mental model — *"an underlay is just a block with
reference layers on top"* — and an honest architecture that holds it, without
breaking the performance and non-interference properties that make big DXF
underlays usable today.

## Motivation

The driver is **conceptual cleanliness** (design grill C4·Q1 = driver (c)):
underneath, an underlay and an imported block are the *same thing* — imported
reference geometry converted to native primitives. The Block Editor already
imports DXF/DWG/PDF into native primitives; underlays do the same conversion but
were built as a separate, batched, non-editable system. Unifying the *model*
(one genus, one definition shape) stops the two from drifting and gives future
"convert underlay ↔ block" capability a home — while the specializations that
force distinct *rendering* stay explicit, not accidental.

## Architecture & Constraints

Invariants `R1…R8` (binding). "Reference Graphic" is the genus; **Block** (the
reusable/editable kind) and **Underlay** (the imported large-reference kind) are
its two user-facing members.

### R1 — One import front-end → native primitives + layers → a definition

Importing a drawing (DXF/DWG/PDF) converts it to **native primitives** (the same
primitive vocabulary blocks use, per `block-system.md`) **plus layer metadata**.
The result is a **definition**, which may be **embedded one-off** (the typical
underlay — a project-local import, a definition with a single instance) or
**promoted to the reusable library** (a formal `.fpdb` block). Same definition
shape either way. Curve fidelity follows the block-editor import path (curves
preserved), not the underlay-flatten path.

### R2 — In model space, every placed instance is a locked reference

Consistent with `model-space-containment-contract.md` C1: a placed instance
(Block *or* Underlay) is a **locked unit**. Its individual primitives are **not
selectable or editable in a plan view**. The *only* surface that edits primitives
is the **Block Editor** (the definition). "Editing an underlay" = open its
definition in the editor.

### R3 — Block vs Underlay is a *capability bundle*, not editable-vs-locked

Both are locked references (R2). The user-facing distinction is a bundle of
capabilities on the placed reference:

| Capability | Block instance (default bundle) | Underlay (reference bundle) |
|---|---|---|
| Render | normal (per-item) | **lightweight** option available (R4) |
| Level scope | single level + Z (`…contract` C3) | **multi-level list** (`["*"]` = all) |
| Layer visibility | n/a (single implicit layer, R6) | **per-layer show/hide** |
| Primitive visibility | n/a | **per-primitive show/hide** |
| Snap / align | yes | yes |

"Underlay" is literally "a Block placed with the reference bundle."

### R4 — Rendering: unified native-primitive DATA, dual render path (target Z) — **spike-gated**

- **Data:** the reference holds **native primitives + layers**, so snap,
  per-primitive visibility, and (definition-side) editing all operate on real
  primitives.
- **Render:** a **`lightweight` flag** (chosen at import — *lightweight vs
  default*) makes the renderer **batch primitives per-layer into cosmetic paths**
  (the mechanism `underlay-workflow.md` documents: cosmetic ≤1.0px fast-stroker +
  freeze-blit), skipping per-item scene objects; `default` renders per-item.
- **BLOCKING PREREQUISITE:** a **performance spike** must prove that
  batched-render-*built-from-native-primitives* matches today's hand-batched
  path on a real large DXF **before** implementation. **Fallback = target (Y):**
  a **dual representation** where `lightweight` keeps today's batched-path record
  intact and `default`/native is a separate, promote-on-demand representation.
  (See Performance below.)

### R5 — Selectability: unit-level, de-prioritized, lockable

A placed reference is **selectable as a whole unit** (move / delete / re-assign
levels / open definition) but **ranks below design elements** in the
halo/rubber-band pick order, plus a per-reference **"lock in place"** toggle for
fully-inert references. This preserves the "reference must not hijack selection"
intent (`underlay-workflow.md`) while giving underlays the unit-selectability
blocks have. **Dependency:** the selection-mode system is `partial`
(`selection-mode.md`) — de-prioritized ranking must land there.

### R6 — Layers are primarily an imported-reference concern

Layer metadata comes from import. **Authored blocks** get a **single implicit
default layer**; explicit multi-layer *authoring inside blocks* is **deferred**
(not needed by the reference use case that motivates this).

### R7 — "Underlay" survives as a user-facing concept

Internally reference-mode block; in the UI, **"Underlay"** stays as its own name
+ entry point (= "import a drawing as a large reference") and keeps its dedicated
ribbon group (`model-space-containment-contract.md` C7). "Block" = "reusable
authored/editable definition." Two words because they map to two user intents.

### R8 — Migration: migrate, don't drop

Unlike the containment contract's loose-geometry clean-drop (C8), existing
underlays are real imported content. On load, existing underlay records
**re-extract to the unified native-primitive reference model** through the
pipeline (source path + `.fpd.cache` already exist); if the source file is
missing, **fall back to the cached geometry** as a locked reference. Finalize the
mechanism at implementation; the *principle* is migrate-not-drop.

## Design Decisions

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Unification scope (C4·Q1/Q2) | Conceptual genus → **target architecture** (underlay = special-case block) | Descriptive framing only | Captures the user's model as *intended* direction, not just a note |
| Reference-ness (C4·Q4, revised) | **All model instances locked** (C1); Block/Underlay = capability bundle | "Editable vs reference" placement mode | In model space nothing is editable — the axis collapses |
| Render (C4·Q3) | **(Z)** unified data + dual render — **spike PASSED 2026-09-17, (Z) confirmed** | (X) always-native; (Y) dual-representation | (Z) is truest to "just a block with layers"; batched-from-primitives held interaction parity (see Performance) |
| Selectability (C4·Q5) | Unit-level, de-prioritized, lockable | Non-selectable / managed-only | Unifies with blocks while protecting design-element selection |

## Performance & Security

The **make-or-break** is R4. Today one underlay renders as **one batched
`QGraphicsPathItem` per layer** (dozens of scene items) — that is what keeps a
100k-entity DXF interactive. Naively rendering the native primitives as 100k
individual scene items will not match it. The spike must A/B, on a **real large
DXF**:
1. today's hand-batched cosmetic path (baseline),
2. native primitives as individual cosmetic scene items,
3. native primitives **batched per-layer into cosmetic paths at render time** (the R4 target).

Accept (Z) only if (3) ≈ (1) at the zoom/pan interaction bar
(`underlay-workflow.md §18`). Otherwise ship (Y). (Per project rule: bench the
mechanism on real data before building the perf story.)

### Spike result (2026-09-17) — (Z) ACCEPTED

Benched on the **Sleeman reference DXF** (169 MB → **437,824 geoms / 47 layers /
3.23 M vertices**; 286k lines, 141k polylines, 9k circles, 412 ellipses, 551
text) via `tools/perf_probe_reference_render.py`. The probe drives the **real
interaction hot path** — `snap_engine.find(cursor, scene, xf, align_paths=rays)`
with SNAP **and** ALIGN active, then a viewport repaint — swept across the
viewport at ×0.5–×8 and during a pan. This is the right metric because the model
scene runs `NoIndex` (`model_space.py`; cosmetic-pen items mis-cull under the
BSP), so `find`'s `scene.items(rect)` degrades to an O(n) scan whose cost is set
by the representation's **scene-item count**.

| Representation | scene items | **snap ms** (×0.5–×8) | paint ms | one-time build | peak RSS |
|---|---|---|---|---|---|
| (1) baseline — hand-batched path + `UnderlaySnapIndex` (today) | **68** | **0.27–0.58** | 172–242 | 15–19 s | **1,305 MB** |
| (2) native primitives as **individual** scene items | 437,288 | **11,355–18,300** | 3,470–14,032 | 81 s | 2,971 MB |
| (3) native primitives **batched** per-layer + index (target Z) | **68** | **0.24–0.31** | 85–215 | 76 s | 2,765 MB |

**Findings:**
- **(3) ≈ (1) at the interaction bar.** Snap stays **sub-millisecond** and paint
  matches the batched cost the §18 freeze-blit already mitigates — full
  zoom/pan/SNAP/ALIGN parity with today. **→ accept (Z).**
- **(2) is non-viable** (as the spec predicted): the `NoIndex` O(n) scan makes a
  single snap **11–18 seconds**. Individual-scene-item rendering of native
  primitives is off the table; batching is mandatory.
- The (3) deltas are the *secondary* costs only: one-time build ~4–5× (437k
  primitive creation) and ~2× resident RSS. Both are **over-stated** by the
  bench, which held all 437k primitives resident — which **R2 does not require**
  in a plan view: snap runs off the `UnderlaySnapIndex`, render off the batched
  paths, and native primitives need only materialize in the **Block Editor**
  (definition editing). Held lazily, model-space resident cost ≈ baseline and
  the build cost becomes an import/editor-open cost (the "secondary but
  important" bucket per the task owner), further optimizable.

**Implementation constraints this pins down:**
1. Render MUST be batched per-layer cosmetic paths (never per-primitive items).
2. Snap MUST run off the `UnderlaySnapIndex` (or an equivalent spatial index),
   never a scene walk — the `NoIndex` scene makes per-item snap fatal.
3. Native primitives are the definition-side data model; in plan views they are
   **not** held as scene items and ideally materialized lazily to keep resident
   memory at baseline.

## Acceptance Criteria (design-only deliverable)

- [x] Unified Reference-Graphic model recorded (R1–R8); Underlay = special-case Block.
- [x] The rendering target (Z) + spike gate + (Y) fallback are explicit.
- [x] Model-space locked-reference rule reconciled with containment contract C1/C3.
- [x] Migration principle (migrate-not-drop) recorded.
- [x] Performance spike run + target/fallback chosen — **(Z) accepted** on the
  Sleeman 437k-geom DXF (see Performance → Spike result, 2026-09-17).
- [ ] Implementation (follow-up task) — unified import, reference bundle, render, selection ranking, migration.

## Verification Checklist

- [x] `status: proposal` — reads as target, not current behavior.
- [x] Rule A — rendering/cache → `underlay-workflow.md`; definition → `block-system.md`; C1/C3 → containment contract.
- [x] SPEC-INDEX row added; containment-contract C4 pointer updated.
- [x] Post-spike (2026-09-17): (Z) recorded with numbers; `status` stays
  `proposal` until implementation lands (re-stamp `partial`/`current` then).

## Divergences ledger (today vs. this target)

| # | Target | As-built today | Closes when |
|---|---|---|---|
| RD1 | R1 one import → native primitives + layers | Block import → native primitives; **underlay import → flattened/batched paths** (separate pipeline) | unified import lands |
| RD2 | R3 Block/Underlay = capability bundle on one model | Two separate systems (`Underlay` record vs `BlockDefinition`/`BlockInstance`) | unification lands |
| RD3 | R4 native-primitive data + dual render | underlay = batched paths only, no native primitives, non-editable | **spike passed 2026-09-17 → (Z)**; render batched + snap via index (never per-item scene objects); closes when the unified render/snap lands |
| RD4 | R5 selectable-as-unit, de-prioritized | underlay non-selectable (managed only) | selection-mode ranking lands |

## Deferred work (follow-up tasks)

1. ~~**Performance spike (blocking)** — R4 A/B on a real large DXF; choose (Z) or (Y).~~
   **DONE 2026-09-17 → (Z)** (`tools/perf_probe_reference_render.py`; numbers in Performance).
2. **Implementation** — unified import front-end, reference capability bundle,
   render path(s), selection de-prioritization + lock toggle, migration (R8).
3. **Explicit block-layer authoring** (R6) — only if a use case appears.
