---
status: proposal
last-verified: 2026-09-16
verified-commit: bf332b2
applies-to:
  # Cross-subsystem containment contract. Owns the containment INVARIANTS only;
  # each subsystem spec below owns its own mechanics and links up to this doc (Rule A).
  - firepro3d/model_space.py
  - firepro3d/geometry_2d.py
  - firepro3d/block_definition.py
  - firepro3d/block_instance.py
  - firepro3d/paper_space.py
source-tasks:
  - "todo_open.md → design: rethink 2D-geometry / Block-Editor / Model-Space contract (2026-09-16 grill)"
---

# Model Space Containment & Authoring Contract — Design Spec

> **Status: proposal (unbuilt).** This document is the top-level *leash* for a
> milestone-scale rework. It records the containment invariants agreed in the
> 2026-09-16 design grill. It does **not** describe current behavior — today's
> code diverges from it on every major point (see the Divergences ledger). The
> per-subsystem specs it references keep their own `status`; this doc governs the
> *containment invariants* they must converge to, and nothing else (Rule A).

## Goal

Give the application a single, unambiguous answer to the question **"what is
allowed to exist in each surface — Model Space, the Block Editor, and Paper
Space?"** Today that boundary is blurred: Model Space is simultaneously a
building model *and* a freehand 2D drawing surface *and* a place to drop text
notes. This contract makes each surface do one job:

- **Model Space** = the *building model* — only positioned model entities.
- **Block Editor** = the *authoring surface* — where reusable 2D graphics are drawn.
- **Paper Space** = the *documentation output* — where the model is annotated for the AHJ package.

## Motivation

The MVP is the plotted AHJ submittal package (`project-mvp-priority-model`), and
the user's mental model is Revit-aligned (`user_revit_mental_model`): you don't
scribble loose lines into a Revit model — you place families, and drawing-level
markup lives in sheets/drafting views. The current architecture fights that: 2D
geometry is a first-class, level-scoped *model* citizen, which spawns a growing
tail of "make loose model geometry do more" work (project-into-elevations,
extrude-to-solid, elevation-plane anchoring) that deepens the blur instead of
resolving it. Drawing a hard line now — before the Feature system and the
3D-authoring work expand — keeps every downstream subsystem honest and prevents
the "which surface owns this?" arbitration bugs (`parallel_system_arbitration_smell`).

## Architecture & Constraints

The contract is nine invariants. They are numbered `C1…C9` and are the binding
facts; subsystem specs must not restate or contradict them.

### C1 — Hard spine: Model Space is placement-only

Model Space contains **only built model entities**: Features (built-in +
library-authored), placed **Block instances**, and **Underlays** (reference).
There is **no loose authored geometry, no free markup, and no free text** in the
model. All markup, detailing, dimensioning, leaders, revision clouds, tags, and
text live in **Paper Space**. Model = the model; paper = the deliverable.

### C2 — Block / Feature taxonomy: a Feature *composes* Blocks

- A **Block** is a reusable **2D graphic definition** authored in the Block
  Editor. It has two roles: (a) **placeable standalone** in Model Space *and*
  Paper Space, and (b) the **2D-representation slot inside a Feature**
  (plan Block + per-elevation Blocks).
- A **Feature** is a modeled building element =
  `{ plan Block + elevation Block(s) + 3D geometry + parameters + host strategy }`.
  A Feature **composes Blocks** for its 2D representations.
- This **replaces the former "siblings" contract** (`block-system.md`) in which
  Block (`.fpdb`) and Feature (`.fpdf`) were disjoint parallel libraries. Blocks
  remain independently authored and placeable; Features now *reference* Blocks.

> **Derived clarification (C2a):** the "composes Blocks" rule applies to
> *library-authored* (Architectural) Features. **Built-in Features** (C6) keep
> bespoke representations, not composed Blocks. Existing openings (bespoke paint
> today) are an early special case reconciled when the Feature system is built out.

### C3 — Level scope lives on the instance, not the geometry

- 2D primitives are **definition-local and level-less** (they live inside a Block
  definition, in origin-relative coordinates).
- A **Model-placed Block instance is level-scoped**: it carries a level + a Z /
  elevation offset and is filtered by the active level / view-range exactly like
  any placed model entity (see `view-relationships.md §7.1`).
- A **Paper-placed Block instance is sheet-scoped** (no level).

### C4 — Underlay reference-graphic unification → RESOLVED into a target architecture

The C4 design session ran (2026-09-16) and produced a **target architecture**:
an **Underlay is a special case of a Block** — both are *imported/placeable
reference geometry* — recorded in **`reference-graphic-model.md`** (proposal).
Key outcomes: one import front-end → native primitives + layers → a definition;
in model space all instances are **locked references** (no primitive editing);
Block-vs-Underlay is a **capability bundle** (Underlay adds lightweight render,
per-layer/per-primitive visibility, multi-level), *not* an editable-vs-locked
distinction; rendering targets unified native-primitive data + a batched
`lightweight` render path **gated on a performance spike** (fallback = keep
today's batched representation). Underlays remain **unchanged in code** until that
spike + implementation land. Mechanics stay governed by `underlay-workflow.md`;
the unification target is governed by `reference-graphic-model.md`.

### C5 — Text is a 2D primitive with a unified data model

- **Text is a first-class 2D-geometry primitive** (the "9th primitive"): a
  typeable box (position, box W/H, wrap, Word-style font per `user_word_like_text_ux`).
  It is authored inside Block definitions like any other primitive.
- **Standalone model-space text is retired.** Text appears in the model **only**
  as content of a placed Block/Feature.
- The **text data model is unified** across block-content and paper-space
  annotation: one Text item, one renderer. Paper Space layers on
  annotation-only affordances (leaders, borders, sheet-relative placement)
  atop the same primitive (see `paper-space.md`).

### C6 — Feature classification: Building vs Architectural (classification only)

- **Building vs Architectural is a classification, not a mechanism.** Both are
  Features (2D reps + 3D geometry + params + host strategy).
- **Building Features** = Wall / Floor / Roof / Room (+ structural). These are
  **built-in Features**: unified in mental model and ribbon, but keep their
  bespoke parametric engines (governed by `wall-room-floor-system.md`). They are
  *not* rewritten into the data-driven library path.
- **Architectural Features** = openings (door/window), casework, fixtures,
  equipment, diffusers, etc. — library-authored, compose Blocks (C2).

### C7 — Surface & ribbon topology

- **The permanent "Create" tab is dissolved.** The authoring surface *is* the
  **Block Editor** context. The 2D-geometry tool set (the 9 primitives incl.
  Text) exists **only** in the **Block Editor** and **Paper Space** contexts —
  never a Model-space tab.
- **Block *entry* commands → Architecture tab, new "Block" group**: Create Block
  (opens a Block Editor document), Insert Block, Block Manager. Architecture
  becomes: Building Features · Architectural Features · Datums · **Block** · Underlay.
- **Underlay ribbon group → Architecture** (UI co-location; **tentative**,
  pending the C4 design session — it may return to Manage).
- **Quick Block is retired** — its premise (bake a selection of loose *model*
  geometry) no longer exists under C1, so removal *follows from* the contract
  rather than reversing the v2 decision. Any future make-from-selection belongs
  to the Block-Editor / paper authoring context.
- **The "Text Block" ribbon button is retired** — Text is a primitive (C5), not
  a model-space mode.
- **Future 3D solid authoring** relocates to the Feature/Block Editor context
  (never a Model-space tab), consistent with C1.
- Governed by `ribbon-bar.md`; exact layout gated on the interactive mockup
  (`docs/mockups/ribbon-containment-contract.html`).

### C8 — Migration: clean drop

On loading a pre-contract `.fpd`, loose 2D geometry and model-space text notes
are **discarded** (with a warning/log). There is **no** migration machinery and
**no** grandfather mode; the legacy loose-geometry and model-text code paths are
**deleted**. (Justified by a near-empty existing-project corpus; carrying a
compat layer would re-introduce the parallel-system smell C1 exists to kill.)

### C9 — The containment boundary test

The line between "allowed in the model" and "paper-space only":

- **Model (allowed):** a **positioned object** with a meaningful location in the
  building — a Block instance or Feature (e.g. an equipment marker, a riser
  symbol). 2D-ness does not disqualify it.
- **Paper only:** **free-drawn linework** and **document annotations** that
  describe the *sheet* — text, dimensions, leaders, revision clouds, match lines,
  legends, keynotes, drawing tags.
- **The test:** *"Does it have a meaningful position in the building model?"* →
  model. *"Is it a note about the drawing?"* → paper. (Consequence: a north
  arrow / legend is a **paper** Block, not a model object.)

## Design Decisions

Full rationale for each invariant lives in the 2026-09-16 grill transcript.
Condensed:

| Decision | Chosen | Rejected alternative(s) | Why |
|---|---|---|---|
| Spine (C1) | Hard: model = placement-only | Soft "composition-first but loose survives" | Matches Revit model; kills the loose-geometry tail; one job per surface |
| Taxonomy (C2) | Feature composes Blocks | Keep Block/Feature as disjoint siblings | Matches `wall-room-floor §7.8` (Feature = plan + elevation + 3D reps); one editor, one primitive vocabulary |
| Level (C3) | On the instance | Keep primitives level-scoped | Definition is reusable/context-free; "which level does this show on?" is an instance question |
| Underlay (C4) | Defer | Merge now (literal or abstraction) | Literal merge breaks ~9 invariants; deserves a dedicated session |
| Text (C5) | 9th primitive, unified model | Keep paper sheet-text as a separate system | One renderer, not two; Text belongs to blocks *and* sheets |
| Feature class (C6) | Classification only; walls = built-in Features | Two mechanically-distinct systems / rewrite walls as generic Features | Unifies the mental model without a wall-engine rewrite |
| Ribbon (C7) | Dissolve Create; Block group in Architecture | Keep Create tab; keep Quick/Text Block | Loose-geometry tools have no model-space use; entry vs. authoring split cleanly |
| Migration (C8) | Clean drop | Non-destructive auto-wrap / grandfather | Near-empty corpus; compat layer re-introduces the smell |

## Reconciliation map — impact on the six affected specs

Each row is a *pointer + one-line delta*. The detailed rewrites are **follow-up
tasks**, not part of this design-only deliverable.

| Spec | Delta this contract imposes |
|---|---|
| `2d-geometry.md` | Reframe from "model-space drawing items" to "**Block-definition primitives** (definition-local, level-less)". Add **Text** as the 9th primitive (C5). Remove level/`_level_offset_mm`/`Z_CAT_CONSTRUCTION`/elevation-z-ordering language for primitives (moves to the instance, C3). Placement no longer occurs in Model Space. |
| `block-system.md` | **Replace the "siblings" contract** with "Feature composes Blocks" (C2). Record standalone-Block placement in **both** Model and Paper surfaces. Record **Quick Block retirement** (C7). Stale SPEC-INDEX row fixed (Editor v2 is *built*, not deferred). |
| `ribbon-bar.md` | Dissolve the Create tab; add the Architecture **Block** group; Underlay group → Architecture (tentative); retire Text-Block + Quick-Block buttons (C7). Update the base-tab roster + contextual-tab notes. |
| `underlay-workflow.md` | **No change** beyond a forward-pointer to C4 (pending unification session) + the tentative ribbon-home move. |
| `model-space-architecture.md` | Record the **containment invariant C1** (model = placed entities only) and the deletion of loose-geometry / model-text code paths (C8). |
| `view-relationships.md` | §3.1 authoring contract now reads: **Model geometry is composed by placing definitions**, not drawn loose. 2D-geometry level-scope rows (added 2026-08-22) are **superseded** — level scope is an *instance* property (C3). |
| **`feature-system.md`** (forged) | New governing spec (closes the orphan). Records C2/C6 as the Feature contract. See `feature-system.md`. |

## Task hit-list — `todo_open.md` items this contract changes

**Killed (contract forbids them):**
- `[bug] Model-space text notes show no text … QPainter engine==0` — model text retired (C1/C5).
- `[feature] Model-space text/note two-click placement (mirror rectangle)` — model text retired (C1/C5).
- `[feature] Quick Block` paths / references — Quick Block retired (C7).

**Relocated (from "loose model geometry" to Block-content or Paper):**
- `[feature] Project flat 2D geometry into elevation scenes` → becomes a **Block/Feature representation** concern, not loose-geometry projection.
- `[feature] Render filled closed 2D shapes in 3D and extrude to solids` → **Feature/Block Editor 3D-authoring** concern (C7).
- `[feature] Vertical / "elevation plane" anchoring for 2D geometry` → subsumed by Feature elevation-representation authoring (C2).
- `[feature] 2D-geometry contextual ribbon redesign (2026-09-16 [Image #3])` → re-scoped to the **Block Editor / Paper** contexts (no model-space geo2d tab).
- `[feature] Line-weight / hatch / Display-category knobs for 2D geometry` → **Block-content styling** concerns.
- `[feature] Add a finite construction/reference line as a Line-tool variant` → a **Block-Editor / Paper** primitive, not a model tool.

**Unaffected but worth noting:** the whole **2D-geometry placement polish batch** (reference lines, rotated-rect resize, cursor style) still applies **inside the Block Editor** authoring context.

## Acceptance Criteria (for this design-only deliverable)

- [x] The nine containment invariants (C1–C9) are recorded unambiguously.
- [x] The Block↔Feature relationship is stated as "Feature composes Blocks", superseding "siblings".
- [x] The reconciliation map names the delta for each of the six affected specs.
- [x] The task hit-list marks every affected `todo_open.md` item as killed / relocated / unaffected.
- [x] The orphan **Feature system** is forged into a governing spec (`feature-system.md`).
- [x] Deferred work (Underlay unification, Feature Manager/Editor, per-spec rewrites, implementation) is filed as follow-ups.
- [ ] Interactive ribbon mockup reviewed by the user (house-style gate).

## Verification Checklist

- [x] `status: proposal` — reads as design, not current behavior.
- [x] Rule A honored — invariants live here once; subsystem specs link up, don't restate.
- [x] No line/LOC counts.
- [x] SPEC-INDEX updated (new row + stale block-system row fixed + Feature orphan promoted).
- [ ] Per-spec rewrites (follow-up tasks) land + re-stamp their frontmatter.

## Divergences ledger (as-built today vs. this contract)

| # | Contract | As-built today | Closes when |
|---|---|---|---|
| D1 | C1 model = placement-only | Model Space is a live 2D drawing surface; 8 loose primitives are first-class level-scoped entities | loose-geometry authoring removed from Model Space |
| D2 | C2 Feature composes Blocks | Block & Feature are disjoint sibling libraries (`.fpdb`/`.fpdf`) | Feature-system build (Phase B/C) adopts composed Blocks |
| D3 | C3 level on the instance | 2D primitives carry `level` + `_level_offset_mm` + `Z_CAT_CONSTRUCTION` | primitives made definition-local |
| D4 | C5 Text = 9th primitive, unified | Text is a separate `NoteAnnotation` (model) + `TextAnnotationData` (paper); no Text primitive in blocks | Text primitive added + data model unified |
| D5 | C7 ribbon topology | Create tab exists (2D-Geometry + Blocks groups); Quick/Text-Block buttons live; Underlay in Manage | ribbon rework lands |
| D6 | C8 clean drop | loose geometry + model text serialize/load normally | legacy load paths deleted |

## Deferred work (filed as follow-up tasks)

1. **Underlay reference-graphic unification** (C4) — ✅ **design done 2026-09-16**
   → `reference-graphic-model.md` (target architecture). Remaining: the
   **performance spike** (blocking) + implementation are filed as follow-ups.
2. **Feature system build-out** — Feature Manager (Phase B) + Feature Editor
   (Phase C); adopt composed Blocks (C2) + reconcile existing openings (C2a).
3. **Per-spec rewrites** — the six deltas in the reconciliation map.
4. **Implementation** — the code migration itself (remove loose-geometry model
   authoring, add the Text primitive, ribbon rework, clean-drop load path).
