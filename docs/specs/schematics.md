---
status: proposal          # concept ratified 2026-10-07 (grill Q1–Q18 + brainstorm SD1–SD11); unbuilt — slices SV1–SV4
last-verified: 2026-10-07
verified-commit: 7f97f687
applies-to:               # seams this contract governs once built; today every file is owned by the spec named in parentheses
  - firepro3d/block_definition.py     # `kind` key + `never_placed` accessor only (rest: block-system.md)
  - firepro3d/block_editor.py         # kind-aware open / title / capability lock / Save dialog only (rest: block-system.md)
  - firepro3d/block_library.py        # `root=` reuse + one-tier series dir only (rest: block-system.md)
  - firepro3d/app_data.py             # `schematics_dir()` + `SCHEMATIC_DIR_KEY` + migration entry
  - firepro3d/project_browser.py      # Schematics root, `schematic` role, verbs, drag payload (rest: project-browser.md)
  - firepro3d/paper_space.py          # `ViewResolver` schematic branch, drop default, crop rule (rest: paper-space.md)
  - firepro3d/model_space.py          # delete refusal "used on sheets", refusal sites via `never_placed` (rest: model-space-architecture.md)
  - main.py                           # browser signal wiring, stale-tab prefix, Go-to-view branch
  # new: schematic_scene.py (SchematicSceneManager + materializer home)
source-tasks: ["Schematic views concept — block-like definition authored in a Schematic Editor, stored project or system, placed on sheets only as a viewport; SV1…SVn series (2026-10-07)"]
---

# Schematics — Design Spec

> **Rule A.** This spec owns the *what*: decisions **D-S1…D-S18**, ratified in the
> 2026-10-07 grill (Q1–Q18). The *how* (SD1–SD11) and the build slices SV1–SV4
> live in [`docs/superpowers/specs/2026-10-07-schematics-concept-design.md`](../superpowers/specs/2026-10-07-schematics-concept-design.md).
> Specs this contract amends link here (see "Cross-spec reconciliation"); they
> never restate a D-S decision. Nothing below is built — every clause is
> as-intended until a slice's Account stamps it.

## Goal

A **schematic** is a block-like 2D definition — typical details (hanger, wet
valve trim, riser nipple) and per-project riser / isometric diagrams — authored
with the full Block Editor toolset, kept in the project or saved as a reusable
**template** in a system folder, listed in the Project Browser under
**2D Model › Schematics**, and placed on sheets **only as a viewport**. It is the
one mechanism by which block content reaches paper.

## Motivation

- The containment contract (C9) sends "notes about the drawing" to paper, but
  paper today has no way to show authored linework except free sheet text; the
  typical-detail and riser-diagram deliverables have no home.
- The deferred P1 task "Paper-space block placement" would have put loose
  `BlockInstance`s on `PaperScene` — a second placement system next to
  viewports (the parallel-system smell C1 exists to kill). A schematic viewport
  reuses the existing sheet-view pipeline (crop, scale, title bubble, undo, PDF)
  instead.
- Templates (wet-valve schematics, hanger details) recur across projects; the
  block library's save/load/bundle machinery already solves "shared vs
  bespoke" for blocks and is reused as-is.

## Architecture & Constraints

- **Containment amendment (supersedes the paper half of C2/C3 and the P1 task).**
  A sheet holds exactly three kinds of content: **viewports** (model views and
  schematic views), the **title block**, and **sheet text**. No `BlockInstance`
  of any kind — user or System — is ever a child of `PaperScene`. C9's "a north
  arrow / legend is a paper Block" is re-read as "a paper *schematic* or
  title-block territory" (sheet furniture is decided when SB4f is built).
- **A schematic is a `BlockDefinition` with `kind == "schematic"`** in the
  project's one block registry — nesting, usage counting, cycle guard, bundling
  and undo capture are the shipped block mechanisms, not copies.
- **Never instanced.** No placement site (model drop, Insert, paste, nesting
  into a block or another schematic) accepts a schematic; it is refused with its
  own reason string, the way pattern and linetype blocks are refused today.
- **Authoring surface = the Block Editor** (containment C7): same scratchpad
  `Model_Space`, same ribbon page, one tab per definition. Differences are
  listed in D-S14 only.
- **Viewport = the only consumer.** The sheet-view pipeline (`paper-space.md`
  §5.2/§6) is reused unchanged; a schematic contributes a new
  `source_view_type` value and a non-model source scene, as elevations already
  do.
- **Storage.** Project copy in `.fpd` `block_definitions` (same list as blocks,
  distinguished by `kind`); templates as `.fpdb` under
  `<user_data_root>/schematics/<Series>/`, own settings key, migrated with the
  other user-data folders.

## Design Decisions (as-intended — ratified 2026-10-07 grill Q1–Q18)

### Scope

- **D-S1 Content.** Target deliverables: static typical details and
  per-project riser / isometric diagrams — hand-authored linework, nested
  blocks and text with no live link to the model. **Revisit trigger:**
  data-driven schematics (riser reading the hydraulic model, host-bound tags)
  are a named follow-up gated on System Blocks SB5/SB6, not part of this
  contract. **Out of scope:** legends / symbol keys — a schedule-like
  placed-table feature (`paper-space.md` §9.1), not a schematic.
- **D-S2 Sheet containment.** A sheet holds viewports + title block + sheet
  text only (Architecture, first bullet). The P1 "Paper-space block placement"
  task is superseded; SB7's paper-tag host becomes (viewport, element) only.
- **D-S3 Never instanced.** A schematic appears only as a sheet viewport.
  Refused at every placement and nesting site with `SCHEMATIC_REASON`.
- **D-S4 Visibility.** Schematics are listed **only** in the Project Browser
  (2D Model › Schematics). They are hidden from the Blocks browser, Insert
  Block and the Block Open picker's block roots. The Block Manager lists them
  behind a **Kind** column / filter so rename, delete and Used-in housekeeping
  still work there.

### Storage & templates

- **D-S5 Library root.** Templates live in `<user_data_root>/schematics`
  (settings key `paths/schematic_dir`, overridable in System Settings like the
  block / hatch / linetype folders), never under the block library root. The
  folder joins the user-data migration set.
- **D-S6 Project copy on place; explicit push-back.** Opening a template
  (D-S9) copies the definition into the project (`.fpd`), exactly like blocks'
  load-on-place. Edits change **only** the project copy. **Save as Template**
  (editor verb + browser verb) writes the current definition back to the
  schematics folder; nothing is linked or auto-synced.
- **D-S15 Grouping.** One optional **Series** tier: `Schematics › <Series> ›
  leaf`; ungrouped leaves sit under the root. On disk
  `<schematics>/<Series>/<name>.fpdb` + per-folder `index.json` (folder wins
  over a stored series, as the open block bug ratifies).
- **D-S11c Templates bundle.** Save as Template bundles the nested block
  definitions (the shipped schema-2 `bundled` field) so a template opens on a
  fresh project with its symbols; loading adopts them with the existing same-id
  skip / replace rule.
- **D-S11d Collision.** Save as Template over an existing `(series, name)`
  shows the blocks' **Overwrite / Rename / Cancel** dialog. Re-loading a
  template whose id is already in the project follows the same-id skip /
  replace rule (idempotent).

### Authoring

- **D-S7 Drawing space.** Real-size millimetres in the editor (block parity);
  the viewport scales for paper. **NTS is the default** for a schematic
  viewport (`scale == 0`, the shipped free-size letterbox mode); any scale
  preset may be chosen afterwards. Text keeps the paper-fixed-mm sizing it has
  in blocks.
- **D-S9 New Schematic.** Browser root verb **New Schematic…** opens a dialog
  with two choices — **Blank** or **From template** (picker over the schematics
  folder). Either opens a `Schematic:` editor tab. **Save** writes the
  definition into the project (project undo, one step). The editor's **Save as
  Template** writes it to the schematics folder (D-S6).
- **D-S14 Editor delta.** Identical to the Block Editor except: (a) the
  capability slot (hatch tile / linetype repeat) is unavailable — both toggles
  disabled with a tooltip; (b) the tab is titled `Schematic: <name>` and the
  Save dialog is "Save Schematic" with **Series** (no Library tier) and an
  "Also save as Template" toggle in place of "Also save to library". The
  shared permanent Block Editor ribbon page serves both; its Block group verbs
  act on whichever tab is current. The origin marker stays (harmless, keeps
  parity).
- **D-S16 Entry point.** Project Browser only: the Schematics root context
  menu offers **New Schematic…**; a leaf offers **Open / Rename / Duplicate /
  Delete / Save as Template**. (Rename and Duplicate exist for no other view
  today — they are introduced for schematics only.)
- **D-S17 Undo scope.** New / Save / Rename / Duplicate / Delete / load-from-
  template of a schematic = one **project** undo snapshot each
  (`commit_block_definition` parity). Drop / move / resize / delete of a
  schematic **viewport** = **paper** `QUndoStack` commands (`paper-space.md`
  §4.12/§17). Save as Template is a file write, not undoable.

### Browser & viewport

- **D-S8 Browser gestures.** Dragging a leaf onto a sheet places a viewport
  (`MIME_VIEW`, the plan/detail gesture). A schematic on any sheet shows the
  placed style (italics) like plans / details. Double-click a leaf opens its
  editor tab.
- **D-S10 Viewport rules.**
  - **Crop tracks the schematic's full extent live** (the detail-marker rule,
    not the frozen plan rule): editing the schematic re-fits every viewport of
    it; no stale crop state is persisted.
  - **Multi-sheet:** the same schematic may be placed on several sheets (no view
    type has a one-sheet rule).
  - **Title bubble + number + scale** under the box, hand-painted like plans;
    the scale text reads `NTS` when NTS. (SB4f later converts the title for all
    view kinds.)
  - **Non-navigable into the model:** Go to View / double-click opens the
    Schematic Editor tab; the context menu offers Go to View and Delete only
    (no plan-only detail-hide entries).
- **D-S12 Paper display.** No new Display-Manager row. Inside a schematic
  viewport, nested block instances plot under the paper **Blocks** row, raw
  primitives under **Construction**, text under its existing handling — exactly
  as the same items would inside a plan viewport. WM2 placement overrides apply
  unchanged.

### Lifecycle

- **D-S11a Delete placed = refused.** Deleting a schematic that is on any
  sheet is refused with "used on sheets <numbers>"; remove the viewports first.
  A delete path never creates a "View not found" placeholder.
- **D-S11b Nested usage counts.** A block nested in a schematic cannot be
  deleted while the schematic uses it (the shipped `users_of` refusal; the
  message names the schematic). The Block Manager's Used-in lists schematics.
- **D-S13 Guards.** Acceptance is gated by guards G1–G6 in the concept doc
  (round trip, refusals, viewport NTS / live crop / PDF, library, delete
  refusal, browser) — each drives the real path with real objects and asserts
  observable ground truth (VC3).
- **D-S18 Build order.** SV1 definition + editor + browser → SV2 viewport →
  SV3 library / templates → SV4 polish + reconciliation (concept doc SD11).

## Input / Output (schema deltas — additive, no version bump)

- `BlockDefinition.to_dict` / `.fpdb` / `.fpd` `block_definitions[]`: `"kind":
  "block" | "schematic"` (missing → `"block"`).
- `index.json` entry: `"kind"` next to `tile` / `repeat`.
- `SheetViewData.source_view_type`: new value `"schematic"`;
  `source_view_name` holds the **definition id** (rename-stable); the display
  name is resolved at paint.
- QSettings: `paths/schematic_dir`.
- Drag payload: `MIME_VIEW` `{"view_type": "schematic", "view_name": <id>}`.

## Edge Cases & Error Handling

- **Missing schematic on load** (`.fpd` sheet references an id not in
  `block_definitions`): the viewport shows the existing "View not found"
  placeholder; the definition is not invented.
- **Template referencing a block absent from the project and not bundled**
  (hand-edited file): the nested record renders the shipped missing-block
  badge; nothing is dropped.
- **Empty schematic placed:** extent falls back to the resolver's default
  rect (the plan / elevation rule); the box is still placeable and resizable.
- **Rename collision inside the project:** refused like block
  `set_block_metadata` collisions.
- **Editor open while a viewport shows the schematic:** the viewport renders
  the **saved** definition; unsaved editor work is invisible on paper until
  Save (editor = scratchpad).
- **Project close / new file:** schematic editor tabs are swept with the other
  stale view tabs; render scenes are disposed.

## Acceptance Criteria

- [ ] D-S2: `PaperScene` never holds a `BlockInstance`; the P1 task is moved to
      todo_closed as superseded.
- [ ] D-S3: every placement / nesting site refuses a schematic with
      `SCHEMATIC_REASON` (G2).
- [ ] D-S4/D-S16: Schematics root + Series + leaves with the six verbs; hidden
      from the Blocks browser / Insert / Open block roots (G6).
- [ ] D-S6/D-S9/D-S11c/d: New (blank | template), Save, Save as Template with
      bundling and collision dialog (G4).
- [ ] D-S7/D-S10: drop → NTS viewport sized to content; edit → every viewport
      re-fits; title bubble reads NTS; PDF contains the strokes (G3).
- [ ] D-S11a/b: delete refusals (G5).
- [ ] D-S17: one project undo step per definition op; paper stack for viewports
      (G1 asserts both).
- [ ] Round trip `.fpd` save / reopen keeps the schematic, its viewport and its
      contents (G1).

## Verification Checklist

- [ ] Guards G1–G6 (concept doc) RED with each slice's change reverted, GREEN
      with it.
- [ ] Full suite green; registry-enumerating tests updated (concept doc
      keep-green list).
- [ ] Cross-spec reconciliation below applied as each slice lands; this spec's
      `status` moves `proposal → partial → current` per slice.

## Cross-spec reconciliation (to amend when the build lands — Rule A)

- `model-space-containment-contract.md` — C2 "(a) placeable standalone in Model
  Space *and* Paper Space" → Paper via schematic viewport only; C3 "Paper-placed
  Block instance is sheet-scoped" → retired; C9 "north arrow / legend is a paper
  Block" → pointer to D-S2 (sheet furniture decided at SB4f). Task hit-list:
  P1 "Paper-space block placement" superseded.
- `block-system.md` — "paper-placement rules pending — a known gap" → resolved
  by pointer to D-S2/D-S3; `kind` key in the `.fpdb` schema section; Block
  Editor contract gains the D-S14 delta pointer; `never_placed` accessor joins
  the capability-refusal paragraph.
- `paper-space.md` — §3.2 "sheet views are consumers of named views" gains the
  schematic source; §4.3 catalog note; §5.2 `source_view_type` enum + id-in-name
  rule; §6.1 placement flow (NTS default for schematics); §6.6 isolation N/A
  for schematics; §9.1 legends stay a placed-table item (D-S1).
- `project-browser.md` — Schematics leaves `_MS_STUBS`; new role, signals,
  refresh API, context menu, `mimeData` payload, placed-views root; the
  "double-click a stub opens the plan" behaviour is retired for the real root.
- `2026-09-29-system-blocks-concept-design.md` (System Blocks) — Q2 / SB7
  paper-tag host = (viewport, element) only; SB4f unchanged (converts the
  title for every view kind, schematics included).
- `settings-dialog.md` — System Settings path row for the schematics folder.
- `scene-io.md` — `kind` carried by both serialization paths (the
  `_capture_network` / `_restore_network` undo path and `.fpd`).
- `SPEC-INDEX.md` — this spec's row (added with the concept).

## Deferred / revisit triggers

- **Data-driven schematics** (riser reading the hydraulic model; host-bound tags
  inside a schematic) — after System Blocks SB5/SB6; needs a design pass of its
  own (D-S1).
- **Sheet furniture** (north arrow, scale bar) — decided when SB4f converts the
  view title; candidates are a System schematic or title-block content (D-S2).
- **Legends / symbol keys** — the placed-table feature (`paper-space.md` §9.1),
  schedule-like, not a schematic (D-S1).
- **Nesting a schematic inside another schematic** — declined in Q3; revisit if
  a "typical trim" sub-detail is wanted inside risers.
