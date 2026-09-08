# Block Editor v2 — Design (HOW)

> Date: 2026-09-07 · Governs: the Block Editor authoring surface (block-system v2).
> The **WHAT** was locked in a `/grill-me` session; this doc is the **HOW**. The durable
> contract is folded into `docs/specs/block-system.md` §"Block Editor (v2)"; this dated doc
> holds the transient design rationale + fork decisions.

## Goal

A standalone canvas-tab editor for authoring and editing `BlockDefinition`s with the existing
2D-geometry tools, **disconnected from all model views**. It fills the v2 Editor that
`block-system.md` reserves throughout (DD-10, the deferred lists, the "Open in Editor" stub).

## Locked WHAT (problem definition)

### Entry points (6 flows)

| Entry | `id` | Seeded with | Save affects placed instances? |
|---|---|---|---|
| Create Block button (blank) | new | nothing | no |
| Create Block button (w/ selection) | new | **copy** of selection | no (until replace-prompt) |
| Quick Block button (selection only) | new | selection (**consumed**) + `MakeBlockDialog` name | no |
| Manager → Create new (blank) | new | nothing | no |
| Manager → Create new based off selected | new | clone of def (geometry + attributes) | no |
| Manager → Open in Editor | **same** | existing def | **yes → confirm at Save** |

### Locked decisions

- **Two create paths kept:** editor (primary "Create Block") + **Quick Block** (instant
  consume-and-bake from selection, separate ribbon button, existing `MakeBlockDialog` name prompt).
- **Seeded editor = non-destructive COPY.** The model is touched only at Save, via a
  "replace source with an instance?" prompt (default yes), as one undo. Cancel/close never mutates
  the model.
- **Edit-in-place (same `id`):** Save bumps `version` and repaints **every** instance (flyweight
  invariant, `set_primitives`); an "updates N instances" confirm fires at Save when instances exist.
- **Import DXF / DWG / PDF → editable primitives** at correct mm scale (reuse the
  `import_scale = real_mm / source_units` convention). **SVG deferred.**
- **Metadata authoring in the editor:** name + editable library/series combos; validated at Save
  (non-blank, `(library, series, name)` unique); rename keeps `id`. **Manager detail panel stays
  read-only** (satisfies `todo_open.md:66` — the editor *is* the editing surface).
- **Snapped "Set Origin" tool** + persistent marker, default bbox top-left (folds in
  `todo_open.md:60`), stored definition-local.
- **Save:** project registry first, then **opt-in** "save to library?" (reuse S3 `save_to_library`
  + `BlockNameCollision`). Stay-open Save; discard-prompt on dirty close; **one editor per
  definition**.
- **Restricted "Block Editor" ribbon context** while an editor tab is active (2D geometry +
  modify/transform + constraints + editor verbs only); property panel reused; no level chrome.
- **Breaking change:** "Create Block" now opens the editor; the instant bake moves to "Quick Block".
  No schema migration (`.fpdb`/`.fpd` unchanged; `attributes` already reserved).

### Deferred (explicit follow-ups)

SVG import; attribute **authoring** (the `attributes` field is *carried* by the clone path, not
edited); trace-over-underlay import fallback; **layer-subset** selection on import;
**calibrate-by-pick** import scale; annotative `scale_mode`; text-in-blocks.

## Architecture & Constraints

**One-liner:** the editor is a standalone `Model_Space` *scratchpad* hosted in a closable tab; the
user draws/imports there with the fully-reused 2D toolchain; **Save** commits a definition to the
**project** scene through one arm's-length method.

### Fork decisions

1. **Editor scene = reuse `Model_Space` standalone** (not a minimal dedicated scene). `Model_Space`
   is not a singleton; its `__init__` is side-effect-light (in-memory controllers/lists; no global
   registration, no worker spawn; `_level_manager`/`_plan_view_manager` stay `None`). Reusing it
   inherits — with zero reimplementation — the mode dispatch, `GeometryDrawingController` /
   `PlacementInputCoordinator` / Dynamic-Input HUD wiring, `SnapEngine`, grips, the
   selection-manipulator, and `push_undo_state`. A minimal `BlockEditorScene` was rejected: the
   reuse-sweep "facade" underestimates the mouse-event dispatch + grip + manipulator surface, and a
   parallel scene class is the "parallel-system arbitration" bug magnet. Reusing `Model_Space` also
   *aligns with* the ongoing decomposition (the editor benefits as controllers extract).
   - **Invariant:** the editor scene runs **headless of level/plan-view managers** (block geometry
     is definition-local/2D); those `Model_Space` paths stay dormant.
   - **Risk managed:** `Model_Space` code that assumes it is *the* plan scene (vestigial `views()[0]`,
     `level_manager` reach-ins) stays dormant because the editor injects no managers and owns its own
     view list.

2. **Undo = reuse the editor instance's own `push_undo_state`.** Isolation is structural (separate
   instance); the drawing tools already call `push_undo_state` on their scene, so undo "just works"
   per editor. The editor tab's Ctrl+Z/Y route to *its* scene (tab-scoped shortcut routing). Captures
   geometry only (other entity lists are empty in the editor scene). No new `QUndoStack`.

3. **`geom_dict → primitive` factory = a new pure module `geometry_import.py`.**
   `geom_dicts_to_primitives(geoms, import_scale) -> list[Geometry2DItem]` — stateless (no scene, no
   Qt-parenting), unit-testable with plain dicts, **shareable with the future Feature Editor**.
   - Kind mapping: `line→LineItem`, `circle→CircleItem`, `arc→ArcItem`,
     `path_points→PolylineItem` (closed→closed), `ellipse→PolylineItem` (tessellated),
     `text→skipped`. Splines / PDF Béziers already arrive tessellated as `path_points` from the
     workers → editable (faceted) polylines (accepted v2 trade).
   - Scale applied to coordinates during conversion via the shared `import_scale` convention.
   - Also `bbox_top_left(primitives)` (the origin default helper).
   - **Import UX (lean):** reuse the existing async workers (`dxf_import_worker`,
     `pdf_import_worker`, `dwg_converter`) for extraction; resolve scale via a **minimal** scale/unit
     control (NOT the full `UnderlayImportDialog`, which emits an `Underlay` record + placement).
     Imported primitives drop into the editor scene as a selected group. **Unsupported kinds are
     skipped + counted** and surfaced in the status bar ("Imported 42 primitives; skipped 3 text").

4. **Shell hosting.** A `BlockEditorManager` (mirrors `ElevationManager`/`DetailViewManager`) owns
   editor tabs + a `{block_id: tab}` registry (one-per-definition guard). Each tab is a
   `BlockEditorWidget` wrapping a `Model_View` over its own `Model_Space` instance, added to
   `central_tabs` as a **closable, ephemeral** tab. Tab-change flips the ribbon to the restricted
   Block Editor context. Dirty on any `sceneModified` since the last commit/open; closing a dirty tab
   → `themed_confirm` "Discard changes to 'X'?".

5. **Save internals = one arm's-length method on the project scene** —
   `Model_Space.commit_block_definition(*, block_id, name, library, series, primitives, origin,
   place_instance, source_items)`:
   - **new** (`block_id is None`): `BlockDefinition.new(...)` → `register_block_definition`;
   - **edit-in-place** (`block_id` given): `get_block_definition(id)` → `set_primitives` (version
     bump + repaint all instances) + metadata update;
   - optionally deletes `source_items` (the seeded-create originals) and drops one instance at
     `origin`;
   - **pushes exactly one undo.**
   `make_block_from_selection` / Quick Block become thin callers of the same core ("linework →
   definition" is one code path). `save_to_library` stays a separate opt-in call after commit.

6. **Spec home = append "Block Editor (v2)" to `block-system.md`** (Rule A one-home) + this dated
   design doc. New modules join the spec's `applies-to`.

### Consolidated commit UX — `BlockSaveDialog`

Extends the themed `MakeBlockDialog`: name field + editable library/series **combos** (prefilled
from registry) + **"save to library?"** checkbox +, contextually, the **"replace source with an
instance?"** choice (seeded create) and the **"updates N instances"** warning (edit-in-place with
instances). One dialog = one atomic commit. The property panel still shows per-**primitive**
properties during editing; block-level identity is authored here at Save.

## Components (new)

| Component | Responsibility | Depends on |
|---|---|---|
| `BlockEditorManager` | Tab lifecycle; `{block_id: tab}` registry; open/focus/close; ribbon-context switch | `central_tabs`, `BlockEditorWidget`, project `Model_Space` |
| `BlockEditorWidget` | `Model_View` over an isolated `Model_Space`; holds project-scene ref + seed-item refs; Import/Set-Origin actions; dirty tracking | `Model_Space`, `Model_View`, `geometry_import`, `BlockSaveDialog` |
| `geometry_import.py` (pure) | `geom_dicts_to_primitives(geoms, import_scale)`, `bbox_top_left(primitives)` | `construction_geometry` |
| `BlockSaveDialog` | Collect/validate metadata + save-to-library + contextual commit prompts | `MakeBlockDialog`, registry query API |
| `Model_Space.commit_block_definition(...)` | Arm's-length new-vs-edit commit; propagation; source-delete + place; one undo | `BlockDefinition`, registry API |

**Reused as-is:** `Model_View` (`model_view.py:26`); `GeometryDrawingController` /
`PlacementInputCoordinator` / Dynamic-Input HUD; `SnapEngine.find`; `solve_constraints`; all
`construction_geometry` primitives; `BlockDefinition.new`/`set_primitives`/`render_ops`,
`BlockInstance.on_definition_changed`, registry API (`register`/`_swap`/`delete`/`reload`/
`load_blocks_from_files`/`set_block_metadata`, `model_space.py:1423-1601`); DXF/PDF/DWG extraction
workers (kind-preserving geom dicts, `dxf_import_worker.py:446-673`); S3 `save_to_library` +
`BlockNameCollision`.

## Data Flow

**New / seeded create:** open tab → (copy selection into editor scene; retain project-scene seed
refs) → draw / import / set-origin → Save → `BlockSaveDialog` →
`commit_block_definition(block_id=None, …, source_items=<seed>)` → register + optional
delete-source + place, one undo → opt-in `save_to_library`.

**Quick Block:** selection → `MakeBlockDialog` name → `make_block_from_selection` (thin caller of
`commit_block_definition` core) → consume + bake, one undo. No editor tab.

**Edit-in-place:** Open-in-Editor → focus-or-open tab seeded from existing def → edit → Save (warns
N instances) → `commit_block_definition(block_id=<id>, …)` → `set_primitives` bumps version +
repaints every instance, one undo.

## Edge Cases & Error Handling

- **Cancel / close a dirty editor:** discard-prompt; the project scene is never mutated (copy
  invariant), so discard is a no-op on the model.
- **Open-in-Editor for an already-open `id`:** focus the existing tab (no second editor).
- **Import with unsupported kinds:** skip + count + status message; never crash, never silent-drop.
- **Import scale unresolved / bad units:** fall back to 1:1 with a warning rather than mis-scaling
  silently (surface the assumption).
- **Save with blank/duplicate metadata:** `BlockSaveDialog` refuses Save (reuse `set_block_metadata`
  rules); a block editing itself does not collide with itself.
- **Edit-in-place of a definition whose `id` vanished from the registry** (deleted elsewhere while
  open): refuse commit with a message; offer save-as-new.
- **Empty editor (no primitives) at Save:** refuse; nothing to define.

## Testing (acceptance bar)

**Headless hard-gate (must be green):**
- Identity per flow: blank→new `id`; seeded-create→new `id` + model unchanged until replace-prompt;
  Quick Block→consumes + bakes; clone→new `id` inheriting geometry + attributes; Open-in-Editor→same
  `id`.
- `commit_block_definition` edit-in-place **bumps version and repaints every instance** (assert with
  real `BlockInstance` objects — flyweight invariant).
- Seeded-create replace-prompt: yes→originals gone + one instance at origin; no→originals stay, def
  registered; each is **one undo**.
- Metadata validation: blank/collision refuses; rename keeps `id`.
- Origin: stored definition-local; instance grabs at the picked point.
- `geometry_import`: DXF/DWG/PDF fixture → N editable primitives of the right kinds (not batched
  paths); scale correct (500 mm symbol → 500 mm); skip-count for text/unsupported.
- Round-trip: block authored in editor → `.fpd` save → reload identical.

**Live smoke checklist:** open each entry point; draw with 2D tools + snapping + a constraint in the
editor tab; import a real file and grip-edit a resulting primitive; set origin; Save → place
instances; edit-in-place → all instances update on canvas; dirty-close prompt; one-editor-per-def
focus; ribbon shows only 2D-geometry tools while the editor tab is active.

**No-regression:** existing block make/manage/place + all entity save/load/undo unaffected;
full-suite run once (known native-crash loci).

**Discipline:** `qapp` fixture (no pytest-qt); drive shown views with posted events for
focus/dispatch/render; imported-file-at-real-scale + live-canvas items are smoke-only; each guard
shown RED with the fix reverted.

## Build Order (slices — each its own plan→implement→commit)

1. **BE1 — `geometry_import.py` + `commit_block_definition`** (pure/headless core; factory +
   arm's-length commit; refactor `make_block_from_selection` onto the shared core). Fully unit-tested
   headless. No UI.
2. **BE2 — Editor shell** (`BlockEditorManager` + `BlockEditorWidget` + isolated `Model_Space` tab +
   restricted ribbon context + dirty/close/one-per-def). Wire "Create Block" (blank + seeded) and
   the Manager's Create-new/Open-in-Editor entry points; `BlockSaveDialog`.
3. **BE3 — Set Origin tool** (snapped pick + persistent marker; folds in `todo_open.md:60`).
4. **BE4 — Import into the editor** (worker reuse + minimal scale control + factory drop-in +
   skip-count).
5. **BE5 — Quick Block button** (separate ribbon button; the instant path on the shared core) +
   icons/polish + spec stamp.

## Acceptance Criteria

- [ ] All 6 entry flows open/behave per the table (identity + seeding + non-destructive copy).
- [ ] Edit-in-place Save bumps version + repaints all instances; confirm shown when instances exist.
- [ ] Import DXF/DWG/PDF yields editable primitives at correct mm scale; unsupported skipped+counted.
- [ ] Metadata authored + validated in the editor; Manager stays read-only; rename keeps `id`.
- [ ] Snapped Set-Origin; origin stored definition-local; instances grab at it.
- [ ] Save project-first + opt-in library; stay-open Save; dirty-close prompt; one editor per def.
- [ ] Restricted ribbon context while editor active; property panel reused; no level chrome.
- [ ] `.fpd` round-trip identical; no regression to existing block/entity save/load/undo.

## Verification Checklist

- [ ] Headless hard-gate green; `geometry_import` + `commit_block_definition` unit+integration.
- [ ] Live smoke checklist walked in the running app.
- [ ] Full-suite run once (native-crash loci noted, not new).
- [ ] `block-system.md` "Block Editor (v2)" section added; `applies-to` + `status` updated;
  `last-verified`/`verified-commit` stamped; SPEC-INDEX unchanged (same subsystem).
