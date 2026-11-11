---
status: built             # designed 2026-11-09 (Phase 3, elevation-parity run); built + closed 0.98.0 (2026-11-11); "As built" notes under each decision record where the code differs. Governing specs now own the facts (Rule A)
last-verified: 2026-11-11  # Account: As-built amendments under D1-D8 + checklist; prior 2026-11-09
verified-commit: 6dc388ed   # elevation-parity close (0.98.0); prior e18cc00f
applies-to:
  - main.py
  - firepro3d/section_scene.py
  - firepro3d/elevation_view.py
  - firepro3d/section_manager.py
  - firepro3d/section_marker.py
  - firepro3d/modify_tools_controller.py
  - firepro3d/model_space.py
  - firepro3d/modify_host.py
  - firepro3d/snap_engine.py
  - firepro3d/constants.py
  - firepro3d/note_controller.py
  - firepro3d/entity_context_menu.py
  - firepro3d/level_manager.py
  - firepro3d/model_browser.py
  - firepro3d/scene_io.py
source-tasks:
  - "todo_open.md: Elevation / section canvas parity with plan UX (umbrella) [P1]"
  - "absorbed: Hide on a section proxy lasts only until the next section rebuild"
  - "absorbed: Shift+letter modify shortcuts on the 3D and elevation tabs"
  - "absorbed: Elevation edit undo + datum-extent persistence"
  - "absorbed: Level datum right grip is invisible"
  - "absorbed: Gridline-hosted blocks: full modify tools and copy/paste in section views"
  - "absorbed: Elevation proxy selection look"
  - "absorbed: Notes in section and elevation views"
  - "absorbed (2D half): Per-view datum extents slice 2"
---

# Elevation / Section Parity with Plan UX — Design Spec

Sections and elevations are one class (`SectionScene` / `SectionView`); every
rule here applies to both. Governing specs this design amends (Rule A: they own
their facts, this doc links): `docs/specs/section-view-subsystem.md` (§3.2, §6,
§8, §16.4), `docs/specs/scene-tools.md` (D1/D2 routing), `docs/specs/selection-mode.md`
(§14), `docs/specs/selection-manipulator.md`, `docs/specs/view-relationships.md`
(§3.1, §7.5), `docs/specs/grid-system.md` (§8.3).

## Goal

On a section or elevation tab the user works the way they do in plan: the
modify tools, clipboard, snap, Hide, context menu, selection look, footer
readout and Properties panel behave as in plan, scoped to what a section may
edit; Notes can be placed in a section; datum and gridline end edits stick and
undo.

## Motivation

User 2026-11-09: "Scene tools don't work in elevation currently, Selection read
out matching plan view, level datum resetting on switch, etc generally bring
elevations/sections into parity with plan UX and features. Hiding Pipe doesn't
work". Today the window shortcuts drive the hidden plan scene from a section
tab, Hide is undone by the next rebuild, datum edits reset on any model edit,
and the selection look and readout differ from plan.

## Architecture & Constraints

- Model items (walls, pipes, sprinklers, slabs, roofs) stay geometry-read-only
  in sections (view-relationships §3.1). Section-native editable items: gridline
  -hosted blocks, section Notes, gridline / level-datum ends.
- Section scenes are rebuilt from the model (`rebuild()` clears and
  re-projects, debounced on `Model_Space.sceneModified`). Anything editable in a
  section is therefore a **write-back copy** of a model-side record, never a
  section-only item.
- One shared project undo stack (the plan `Model_Space` stack); its snapshot
  already captures blocks and section markers.
- No new per-class reimplementation: the modify engine, snap engine, context
  menu builder, Note and hide paths are the plan ones, reached through shared
  seams (GENERALIZE), never copied.

## Design Decisions

Phase 2 rulings R1–R16 (grill 2026-11-09, ratified) are summarised where used;
Phase 3 decisions D1–D5 were ratified by AskUserQuestion on 2026-11-09.

### D1 Routing (`main.py`)

- `_active_scene()` / `_active_view()` gain a section branch returning the
  current tab's `SectionScene` / `SectionView` (today only the Block Editor is
  special-cased). The inline `SectionView` branches in `_on_escape`,
  `_delete_if_not_editing` and block placement fold into this branch.
- `_GROUP_LIVE_KINDS`: "section" joins edit / inspect; annotate is live on a
  section for Note only. `_refresh_modify_buttons` follows.
- 3D tab: `_start_modify_tool` (and the clipboard keys) refuse with a footer
  message, as the Paper tab does (R16).
- Riding fixes: F3 -> `_active_scene().toggle_snap()` reaches the section; the
  `SectionView` Ctrl+A WindowShortcut (`elevation_view.py`) is removed so the
  single window shortcut routes through `_active_view()` (AC15); right-click
  Hide on an empty canvas filters out `None`.
- Delete keeps removing any selected source in one undo step (R2);
  section-view-subsystem §3.2 is corrected to restrict geometry edits, not
  Delete.
- **As built (Account 2026-11-11).** `"section"` joined `edit` and `annotate`
  (Note is that group's only gated button) -- it did **not** join `inspect`:
  Inspect stays off on sections, they have no constraints (U4). A section
  selection jumps to the Editor ribbon tab as in plan (U3). Ribbon / shortcut
  draw modes on a section are limited to `select` and `note`
  (`_SECTION_RIBBON_MODES`); others are refused with `_NOT_IN_VIEW_TIP`. The
  3D-tab refusal is `VIEW_3D_EDIT_REFUSED_HINT`; Paper keeps its silent
  refusal; the "refuse vs route" ruling is recorded in `scene-tools.md` D2.
  Owners: `section-view-subsystem.md` s17.1, `scene-tools.md` D1 / D2.

### D2 Modify host (ratified approach Q1: mount the shared engine)

- `ModifyToolsController` stays one class. Its host contract — `mode` /
  `set_mode` and its refusal gates, the modify-mode entries of the press / move
  / preview dispatch tables, the move / rotate / scale / flip / array ghost
  paint, typed-input params, `_show_status`, `instructionChanged` /
  `modeChanged`, `push_undo_state`, the clipboard hooks
  (`_clipboard_item_dicts`, `clipboard_payload`, `paste_items`,
  `_paste_accepts`) — is extracted from `Model_Space` into a `ModifyHostMixin`
  used by both `Model_Space` and `SectionScene` (scene-tools I1 keeps the
  controller composed per host).
- `SectionScene` overrides only:
  - `_selected_items` -> the editable subset (hosted-block copies, Note copies);
    a mixed selection acts on that subset and the footer says "N items skipped
    (edit in plan)"; nothing editable -> the tool refuses with that message
    (R3).
  - `push_undo_state` / undo -> the plan `_ms` stack, one step per commit (R13).
  - clipboard: `scene_role = "section"`; hosted blocks paste at the cursor on
    the host gridline under it (cursor sets along / elevation), refused when the
    view does not show that gridline (R4); cross-type pastes refuse via the
    existing `_paste_accepts` allow-list, a mixed clipboard pastes the fitting
    part and reports the rest skipped (R5).
- Write-back copies: `_HostedBlockCopy` already routes `translate` to the model
  block; it gains `manip_rotate`, `manip_reflect`, `manip_scale_about` writing
  the model block's pose (`_pose_rot`, `_pose_mirrored`, `_pose_scale`) and host
  record, then re-syncing. Copy / Duplicate / Array / Paste create model blocks
  through `place_block_instance(host=...)`. Rotate acts about the view normal,
  mirror across an in-plane axis, array along the gridline or vertically (Phase
  2 approval).
- **As-proposed, probed in plan step 1:** the mapping of an in-plane rotation /
  mirror onto the model block's pose fields (`hosted_blocks.py`).
- **As built (Account 2026-11-11).** The hook is `modify_selection()` (default:
  the whole selection; `SectionScene`: the editable subset) with
  `modify_empty_hint()` for the refusal text -- not `_selected_items`, which
  stays the captured-selection transient. `push_undo_state` is a **required**
  host method (`REQUIRED_HOST_METHODS`, no mixin default: scene items duck-type
  it with `hasattr`). Typed input (the Dynamic Input HUD) runs on sections for
  the modify tools (C-9), through the host's `_hud_scale_manager()`.
  `_HOST_EXTRA_MODES` lets a host run modes beyond Select and the modify modes
  (`SectionScene`: `note`); `_HOST_TOOLS` is the per-host tool list (Offset and
  Fillet stay `Model_Space`'s). The in-plane pose mapping is
  `SectionScene._write_hosted_pose`. Owners: `scene-tools.md` I1,
  `section-view-subsystem.md` s16.4 / s17.2.

### D3 Snap (Phase 3 Q2: one engine, retire per-axis)

- `SectionScene` owns a `SnapEngine` (`find()` needs only `scene.items()` plus
  optional attributes); `ElevGridlineItem` and `ElevDatumItem` join the
  snappable classes so they pass `is_snap_target`'s z gate. Targets: proxy
  endpoints / midpoints / intersections, gridlines, datums, hosted blocks (R15).
- `SectionView.drawForeground` paints `scene._snap_result` as `Model_View` does;
  F3 toggles the section's engine only.
- `snap_section_point` is retired; hosted-block placement uses the engine.
- **As-proposed, probed in plan step 1:** the datum x gridline crossing comes
  out of the engine's intersection pass; fallback (ratified) = add that crossing
  as an engine candidate.
- **As built (Account 2026-11-11).** `ElevGridlineItem` and `ElevDatumItem` do
  **not** join a snappable-class list: they reach the engine through the
  `snap_line_items()` line-target hook (`snap_engine._line_targets`, read by
  `find()` phases 2-3), because their bounding rects miss their lines. The
  datum x gridline crossing comes out of the engine's own intersection pass (no
  fallback candidate was needed). Proxy rects opt in with `SNAP_AS_RECT`;
  `_HostedBlockCopy` joined `ANNOT_Z_SNAPPABLE_CLASSES`. Owners:
  `snapping-engine.md` s14.7, `section-view-subsystem.md` s17.5.

### D4 Notes (R11; Phase 3 Q3: plan store, section key)

- A section Note is today's Note instance in the plan `_block_instances` with
  `note["view"] = "section:<name>"`, its position in the section's 2D frame.
  Plan's existing view filter hides it (no plan-side change).
- `SectionScene.rebuild()` projects it as a `_SectionNoteCopy` write-back copy;
  Move / Copy / Delete / undo / the Note editor reach the model instance
  through it. `note_allowed()` accepts a `section:` view -> the Note button is
  live on section tabs. Paste keeps notes within sections; into plan it refuses.
- Sheets render a section via `get_or_build_scene`, so its notes plot with no
  new path.
- **As built (Account 2026-11-11).** `note_allowed()` lives on `SectionScene`
  (a section's own record, or a pasted record whose `note["view"]` is a
  `section:` key); `note_tool_allowed()` is always True there. Owners:
  `text-annotation-system.md` (Notes rule), `section-view-subsystem.md` s17.7.
- `rename_section` / `delete_section` cascade via `note_controller.rekey_notes`
  / `remove_notes` inside the caller's step; `rekey_history` / `drop_history`
  only on a path that pushes no undo (detail-view precedent). Which section
  paths are undoable is probed in the plan.

### D5 Hide (R8/R9; Phase 3 Q4: one visibility pass)

- After every rebuild, `_apply_hidden_pass()` hides each proxy whose
  `_ROLE_SOURCE` has `_display_overrides["visible"] is False`. The pipe label
  gets its pipe as `_ROLE_SOURCE`, so every piece of a pipe goes together.
- `Model_Space._hide_items` / `_show_items` / `_show_all_hidden` /
  `_hide_all_of_type` emit one new `hiddenChanged` signal (still no
  `sceneModified`); `SectionManager` re-runs the pass on every open section
  scene — no rebuild.
- Section Hide calls `_ms._hide_items(sources)` (replacing the proxy-only
  `_hide_elev_items`). Hidden proxies are not painted, snapped or picked.
- Unhide: Model Browser per-item Show + section "Show All Hidden" (R9).
- Persistence = the existing `displayable_item` save; the suspected pipe
  override load gap (`network_codec.py`) is checked in the plan, fixed if it is
  real.
- **As built (Account 2026-11-11).** An item's Hide source is, in order, its
  `_ROLE_SOURCE`; its `_ROLE_HIDE_SOURCE` (decoration pieces -- opening frame /
  sill / mid line, slab mask -- that follow a source's Hide without becoming a
  pick, menu or Properties target); for an `ElevGridlineItem`, its plan
  `_gridline`. `SectionManager.reapply_hidden` is the `hiddenChanged` slot.
  Owners: `section-view-subsystem.md` s17.6, `architecture/display-system.md`.

### D6 Context menu (R10)

`SectionScene.contextMenuEvent` passes plan's callbacks to the shared
`build_entity_context_menu`: Hide, Hide All (<type>) (global), Show All Hidden,
Edit Block (hosted block / Note copy), Fit All, Copy, Cut (the section's
controller), Delete, Properties. Isolate is filed separately (design line).

**As built (Account 2026-11-11).** The menu adds **Fit All**
(`SectionView.fit_to_screen`) and keeps **Refresh** (`rebuild`) -- plan's menu has
neither; Deselect All comes from the shared builder. Hide All (`<type>`) names
the proxy's model source type (`hide_type_name`) and is offered for a hideable
source only (a datum stands for its Level, which no Hide takes). Owner:
`section-view-subsystem.md` s17.8.

### D7 Datum and gridline ends (R12; Phase 3 Q5: level-name key)

- `SectionMarker` gains `datum_ends: {level_name: {"left": x, "right": x}}` in
  section-scene x. `gridline_z_overrides` is re-keyed from label to gridline
  `uid` (values unchanged); on load a label key maps to the uid of the one
  gridline with that label, an ambiguous or unknown label is dropped with a log
  line.
- Both records ride `to_dict` / `from_dict`, `scene_io`, and the undo snapshot.
  `rebuild()` / `_project_level_datums` apply them; no record = today's auto
  extent.
- `_commit_elev_grip` writes the record for datums too and pushes one undo step
  (plan stack).
- `rename_level` re-keys every marker's `datum_ends` inside its undoable step;
  a level delete drops them inside its step.
- Right grip: `drawForeground` draws a datum to its own `p2`, not the fixed
  `_h_max`.
- The 3D half (model extents, 2D/3D grip tag) stays on the slice 2 line.

### D8 Selection look, readout, Properties (R6/R7/R14)

- `_ColourSrcMixin.paint` strips `State_Selected` as plan items do; the
  manipulator frame is the one boundary. `test_selection_never_plots.py`'s
  dashed-rect assertion is rewritten to assert its absence (VC5).
- The HALO "Type — i of N" text goes through the section's `instructionChanged`
  (from the host mixin) to the footer; the unconnected `SectionScene.cursorMoved`
  readout path is retired.
- `selectionChanged` -> `update_property_manager` with the section selection
  mapped to de-duplicated sources replaces the single-source `entitySelected`
  wiring; panel edits on model items stay allowed (R7).
- **As built (Account 2026-11-11).** `instructionChanged` is the host mixin's
  signal (not a `SectionScene` re-declaration). The source map is the module
  function `section_source_of` and the de-dup is `SectionScene._sources_of`
  (Properties, Hide and the context menu all use them). The unconnected
  `cursorMoved` **HALO** readout path was retired, but the `SectionScene.cursorMoved`
  signal itself stays: `TextEditController` emits it during a section Note
  drag-select. The selection survives a rebuild for editable copies (U1) and
  the selected gridline / datum draw their own selected line, not Qt's dashed
  box. Owners: `selection-mode.md` s14, `section-view-subsystem.md` s17.4.

## Acceptance Criteria

AC1–AC15 as ratified in Phase 2 (`.todo/phase2-elevation-parity-refined.md`,
copied into the plan):

- AC1 Section tab: Shift+M/C/R/F/S/A, Ctrl+C/X/V/D start on the section scene;
  ribbon Modify group live there.
- AC2 Mixed selection acts on the editable subset with the skip message; an
  all-read-only selection refuses.
- AC3 Hosted-block Move/Copy/Rotate/Mirror/Scale/Array change the model block
  (survive rebuild, visible in every parallel section), one undo step each.
- AC4 Ctrl+C/V of hosted blocks per R4/R5, within a section and into a parallel
  section.
- AC5 Delete per R2; spec fixed.
- AC6 HALO footer text in sections; Properties lists the full selection.
- AC7 Hide survives rebuild and save/reopen; plan-hidden items absent from
  sections; a pipe hides whole; Browser Show / Show All Hidden restore.
- AC8 Section context menu = plan's entries; right-click empty canvas never
  crashes.
- AC9 Notes placeable in a section, owned by it, persisted, renamed / deleted
  with it, plotted on its sheets, absent elsewhere.
- AC10 Datum + gridline ends persist per section (save/reopen, model edit, tab
  switch), uid-keyed with label migration, undoable; right grip draws where
  dragged.
- AC11 Every section edit is one step on the shared undo stack.
- AC12 Selected proxies show only the manipulator frame.
- AC13 Snap markers and targets per R15; F3 toggles the section's snap only.
- AC14 3D tab refuses modify / clipboard shortcuts with a message.
- AC15 Ctrl+A on a section tab selects the section's items once.

## Verification Checklist

- [ ] Plan step 1 probes: hosted in-plane pose mapping (D2); datum x gridline
      crossing from the engine (D3); undoable section rename / delete paths
      (D4); pipe override load gap (D5).
- [ ] Each AC has a guard driving the real entry point (shown MainWindow,
      section tab current, `keyClick` through the wired window `QShortcut`,
      QTest mouse on the section view) asserting model ground truth (block pose
      / host record, `_display_overrides`, marker records, `_undo_pos`) after a
      forced `rebuild()` and a save/load round-trip; each shown RED with its
      change reverted.
- [ ] `Model_Space` modify behaviour unchanged by the `ModifyHostMixin`
      extraction: the plan / detail / block-editor / schematic modify-tool tests
      pass before and after (VC5 coupled set).
- [ ] VC9 seam review; VC6 full suite; live smoke on a real project with
      sections, hosted blocks and pipes.
- [x] Account: section-view-subsystem §3.2 / §6 / §8 / §16.4 (+ new §17), scene-tools D1/D2/I1,
      model-space-architecture §2 / §5, selection-mode §4.1 / §14, selection-manipulator Leg B,
      grid-system §8.3 / §8.4, view-relationships §3.1 / §7.5, snapping-engine §5 / §6.1 / §14.7,
      text-annotation-system (section Notes), align-placement §5.4, architecture display-system /
      overview, SPEC-INDEX updated and stamped 2026-11-11 (`6dc388ed`).

## Edge Cases & Error Handling

- Paste of a hosted block where the target section does not show its host
  gridline -> refuse with message (R4).
- Label-keyed gridline override whose label is duplicated or gone -> dropped on
  load, logged.
- A Note whose section is deleted -> removed in the same step; undo restores
  both when the delete is undoable.
- Hidden source whose proxy is the current selection -> deselected by the pass.
- Modify tool started with only read-only proxies selected -> refusal message,
  no mode change.
