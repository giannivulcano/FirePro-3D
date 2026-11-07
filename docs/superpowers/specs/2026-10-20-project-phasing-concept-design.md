---
status: proposal          # concept ratified 2026-10-20 (brainstorm sections 1-5, approach A); unbuilt -- slices PH1-PH8
last-verified: 2026-11-06
verified-commit: da92c5c4
applies-to:
  - firepro3d/displayable_item.py
  - firepro3d/paper_display.py
  - firepro3d/paper_space.py
  - firepro3d/level_manager.py
  - firepro3d/section_scene.py
  - firepro3d/section_marker.py
  - firepro3d/display_manager.py
  - firepro3d/network_codec.py
  - firepro3d/scene_io.py
  - firepro3d/model_space.py
  - firepro3d/hydraulic_solver.py
  - firepro3d/pipe.py
  - firepro3d/fitting.py
  - firepro3d/block_instance.py
  - firepro3d/water_supply.py
  - firepro3d/underlay.py
  - firepro3d/underlay_manager.py
  - firepro3d/model_browser.py
  - firepro3d/property_manager.py
  - firepro3d/settings/template.py
  - firepro3d/feature_placement_controller.py
  # new: phase_registry.py, phase_display.py
source-tasks: ["Project phasing (2026-10-20)"]
---

# Project Phasing -- Concept Design

> **Rule A.** The *what* (D-PH1...D-PH20, AC1-AC15) is owned by
> [`docs/specs/project-phasing.md`](../../specs/project-phasing.md). This doc owns the
> *how* (PD1-PD5) and the build slices. It cites D-PH ids instead of restating them.
>
> **Re-checked 2026-11-06** against main at landing. Code facts below are current as of that
> check; each slice's plan still re-greps them. New mechanisms marked as-proposed await that
> slice's plan gate.

## Goal

Implement D-PH1...D-PH20 on top of the existing override passes (approach A), without
waiting on WM3 (colour cascade) or a port of the Qt-pen classes to the linetype renderer.

## Architecture & Constraints

- Containment C1/C8: model space holds placed entities only, so 2D drafting is phased
  through its block placement (D-PH3) and definitions carry no phase (D-PH16).
- Dual serialization: the undo snapshot and the file save share each kind's
  `to_dict` / `serialize_*`. A phase key added to a serializer covers both paths.
- One visibility owner on plan tabs: the `_set_level_vis` closure in
  `LevelManager.apply_to_scene` already combines the level filter and user-hidden state.
  Phase visibility joins it rather than adding a second writer of `setVisible`. Section and
  elevation tabs build proxies in `SectionScene`, outside that closure, so their phase
  filter sits at proxy build (as-proposed). Underlays (their own loop in `apply_to_scene`)
  and fittings (`Fitting.refresh_for_view`) also sit outside the closure, so PH5's plan
  enumerates every visibility writer.
- Paper overrides are transient: `apply_paper_overrides` saves, overrides and
  `restore_model_display` restores every slot it writes. The phase step follows the same
  contract, so a viewport never leaks state into the model or another viewport.
- Linetype convention (`linetypes.md`): renderer-capable strokes use the linetype
  renderer. The Qt-pen classes approximate the linetype as a pen dash pattern until the
  filed port ("Migrate other strokes to linetypes").

## Approaches considered

| | Approach | Verdict |
|---|---|---|
| A | Phase layer inside the existing override passes (paper pass + canvas tab apply/restore) | **Chosen**: reuses the hook, slots and save/restore; no WM3 dependency (phase colour is whole-element) |
| B | Paint-time query of a global phase context in every item's `paint` | Rejected: touches every paint, adds canvas cache invalidation, duplicates the passes |
| C | Port all Qt-pen classes to the renderer and land WM3 first, then a thin override | Rejected for now: two large prerequisites gate a P1 feature |

## Design Decisions (how)

### PD1 -- Data model (section 1)

- **`phase_registry.py`**: an ordered list of statuses
  `{id, name, builtin, graphics{colour, fill, weight, linetype, opacity}, include_in_calc}`.
  Built-in ids are `new`, `existing`, `demolition` (names renamable, D-PH19). It is saved
  as the top-level project key `"phases"` (the `"levels"` pattern) and seeded from the
  project template: `_blank_template_payload` (`settings/template.py`) gains the key, and a
  template without it gives factory graphics. Graphics live in the registry, not QSettings
  (D-PH11).
- **Element phase** is a status id string, default `"new"`:
  - A `phase` attribute plus one shared "Phase" panel row (enum of registry names) on one
    named class set: `WallSegment`, `WallOpening`, `FloorOpening`, `FloorSlab`, `RoofItem`,
    `Room`, `Pipe`, `Sprinkler`. `DisplayableItemMixin` also carries `Node`, `TextItem`,
    `FilledRegionItem` and the 2D geometry classes, so a rule on the bare mixin over-reaches.
  - The same attribute and row on `BlockInstance`, `WaterSupply` and `Underlay` (no mixin).
  - Each kind's explicit serializer writes `"phase"`: `to_dict` / `from_dict`, or
    `serialize_pipe` / `serialize_water_supply` in `network_codec.py`.
  - Pipe: the existing `_properties["Phase"]` row becomes this field (no second key).
  - Sprinkler: an explicit `"phase"` key in the node entry (`serialize_node` / `deserialize_node`).
  - Fitting: `phase_override` (None = derived), stored in the node entry next to
    `fitting_display_overrides`.
- **Migration**: the next free `SAVE_VERSION` (12 is taken by Printed schematics; 13 at the
  2026-11-06 check), as its own step in the `scene_io` load beside `migrate_old_schematics`.
  `migrate_project_payload` is HF1 colour-only and returns early from v11, so it cannot hold
  this. Below that version, pipe `Phase` values map to ids (`Demo` -> `demolition`), the `"phases"` registry is seeded
  with factory graphics, and every `SheetViewData` gets `phase_display.enabled = False`
  (D-PH6). A missing `phase` key always reads as `new`.
- **`effective_phase(item)`** is the single reader for render, hydraulics, quantities and
  the browser. Block contents resolve to the outermost instance, elevation proxies to their
  `_ROLE_SOURCE` element, and fittings to the override or else the D-PH4 rule over all
  connected pipes.

### PD2 -- Per-view settings (section 2)

- One value type `PhaseDisplay {enabled: bool, hidden: set[status id]}`:
  - `SheetViewData.phase_display`, serialized `{"enabled", "hidden": sorted}` (the
    `hidden_detail_ids` precedent); missing -> disabled.
  - `PlanView.phase_display`, saved with `"plan_views"`.
  - Elevation and section: per section view, saved on its `SectionMarker` record in
    `"sections"` (the `_gridline_z_overrides` precedent: a `SectionScene` property that
    reads the marker).
- A **hidden** set rather than a shown set, so a custom status added later shows
  everywhere without migrating views (D-PH19).
- UI: `ViewportProperties` gets a Phasing checkbox plus one Show row per status, disabled
  while off and absent on schematic viewports. Edits go through `commit_viewport_edit`
  (paper undo). Plan, elevation and section tabs get the same rows in the view section of the panel
  (nothing selected) plus a tab context-menu entry. Those edits are view state: they set
  the dirty flag but are not undoable, like View Range.
- The Phases tab edits a copy of the registry graphics and follows the Display Manager's
  OK / Cancel snapshot pattern and its Reset All button.

### PD3 -- Rendering (section 3)

- **`phase_display.py`** holds the pass context (the active `PhaseDisplay` plus registry
  graphics). A sheet viewport sets it around its `apply_paper_overrides` call; a canvas tab
  sets it on activation.
- **Paper**: a phase step runs after the category step in `apply_paper_overrides`, using
  the same save, override and restore:
  - hidden status -> `setVisible(False)`;
  - colour -> the slots the pass already writes (`_display_color`, `_paper_pen_color`, SVG
    tint), in every colour mode (D-PH9: `new` writes nothing);
  - fill -> `_display_fill_color`, plus a small whole-instance fill-colour slot on
    `BlockInstance` (whole-instance only, so no WM3 dependency). That slot reaches
    Solid-mode elements only: a hatch or section-cut body draws through
    `draw_section_type` + `materials.fill_type_of`, so D-PH10's pattern rule needs a
    pass-scoped line colour and background there, section proxies included (as-proposed);
  - weight -> `_paper_pen_width`; opacity -> `setOpacity` (saved);
  - linetype -> a pass-scoped linetype ref. Blocks apply it as a transient WM2 placement
    override (outer-wins covers nested blocks). The Qt-pen classes get it through
    `DisplayableItemMixin._outline_pen`, which turns the linetype's dash and gap lengths
    into a pen dash pattern at true paper mm. Pipes and gridlines, which build
    their own pens today, are routed through that hook.
- **Canvas**: on plan tabs phase visibility joins `_set_level_vis` (visible = level, and
  not user-hidden, and status shown); section and elevation tabs filter at proxy build. The
  snap engine already skips invisible items (`snap_engine.py`, `isVisible`) and the HALO
  pick filters on it too (`halo_selection.py`). A click-level P4 probe of pick exclusion
  still runs as the first step of PH5. Graphics use the same slots in canvas units and are
  restored when the tab is left or phasing is turned off.
- **Host-bound labels/tags** resolve their host's `effective_phase` (D-PH17).

### PD4 -- Behaviours (section 4)

- **Templates** are instances of the element class, so they get the Phase row. Each
  placement controller copies `phase` from its template. The plan must enumerate every
  site: pipe, sprinkler, wall, floor, roof, room, opening (doors, windows and openings place
  through `feature_placement_controller.py`), block placement, water supply.
- **Set Phase**: a right-click submenu, one undoable command through the model undo
  snapshot; non-phased items in a selection are skipped.
- **Model Browser**: a "Group by: Level | Phase" toggle plus a status filter.
- **Underlay Manager**: a Phase column. Underlays are not on the undo stack today, so the
  edit only sets the dirty flag.
- **Opening warning**: the panel shows "Host wall is Demolition" when an opening's status
  is not Demolition and its wall's is.
- **Copies**: block paste and duplicate already use `to_dict`. Pipe paste is fixed to
  carry the source pipe's `_properties` (today it creates a default pipe: the open P2 bug
  "Pasted pipes lose all their properties"). Sprinkler paste carries `phase`. Walls, floors,
  roofs and rooms paste through their own `from_dict` branches in `paste_items`, so the
  `to_dict` key carries.
- **Hydraulics**: `HydraulicSolver` filters `system.pipes` (read in `_build_adjacency` and
  in `solve`'s pipe count) and the design heads by `effective_phase != "demolition"` (PH8: the registry's
  `include_in_calc`). Fitting types for the calc derive from the non-demolished pipes at
  each node; that code overlaps the open P2 bug "Verify: a node's fitting loss may be
  charged to every pipe". The report adds "N demolished pipes / M heads excluded".

### PD5 -- Dependencies

- **LT7** ships the factory Demolition linetype (D-PH20); PH4 is ordered after it.
- **SB4g** (System symbol blocks) enables symbol dashing (D-PH13); until then symbols take
  colour and opacity only, with no extra work. Fittings: see D-PH13.
- **WM3** is not a dependency (PD3 fill and colour are whole-element).
- **View templates** (spec session): view-level phase defaults (D-PH7).

## Build slices

| Slice | Delivers | Depends on | VC3 guards (real path -> ground truth) |
|---|---|---|---|
| **PH1 Data model** | registry + `"phases"`; `phase` on every kind + panel row; pipe `Phase` folded in; migration step; `effective_phase`; fitting derivation + override; template copy at every placement site (AC1-AC4, AC12) | -- | save/load round-trip of each kind's phase; pre-phasing fixture with a pipe `Demo` loads per D-PH6; fitting rule over the four junction cases; placing through each tool commits the template's phase |
| **PH2 Phases tab** | Display Manager Phases tab; OK / Cancel / Reset All; project-saved, template-seeded (AC6, AC7) | PH1 | tab edit, then OK, then save/load keeps graphics; Cancel leaves the registry untouched |
| **PH3 Sheet phasing** | `PhaseDisplay` on viewports + panel rows; paper hide / colour / fill / weight / opacity in every colour mode; host labels follow (AC5, AC9 minus dash, AC13 paper, AC14, AC15) | PH1, PH2 | offscreen sheet render and PDF export: Existing pixels grey, hidden status absent, Phasing-off render pixel-identical to the pre-phasing base |
| **PH4 Demolition linetype** | pass linetype ref; blocks via a transient WM2 override (nested too); Qt-pen classes via `_outline_pen` dash in paper mm (AC9) | PH3, LT7 | sampled pixels along a Demolition wall, pipe and nested-block stroke show gaps at the linetype's paper-mm period |
| **PH5 Canvas tabs** | plan, elevation + section `PhaseDisplay`; visibility through `_set_level_vis` on plan tabs, proxy build on section tabs; not pickable or snappable; status-bar notice (AC8, AC13) | PH1 | shown plan tab scrolled off the origin: a hidden element is not drawn, is no snap candidate, and a click does not select it (first step: P4 pick probe) |
| **PH6 Hydraulics** | solver excludes Demolition; fitting types from the remaining pipes; report line (AC10) | PH1 | a network with a demolished branch solves equal to the same network with the branch deleted; the report lists the exclusion |
| **PH7 Editing tools** | Set Phase (undoable); Model Browser group/filter; Underlay Manager column; opening warning; pipe paste keeps properties (AC11, AC12) | PH1 | each driven through its real entry point (menu action, browser click, manager cell) |
| **PH8 Custom statuses** | D-PH19 | PH2-PH5 | (designed at its own run) |

Order: PH1 -> PH2 -> PH3 -> PH5 -> PH6 -> PH7; PH4 once LT7 has shipped. PH6 and PH7 need
only PH1 and may move earlier.

## Follow-ups (filed at 4f)

- 3D phase display (hide Demolition / grey Existing in 3D) -- new task.
- View-level phase defaults -- `+1 occurrence` on "Spec session: Drafting overrides / view templates".
- Symbol dashing -- note on SB4g.
- "Demolition" linetype -- note on LT7.
- Qt-pen classes to the linetype renderer -- `+1 occurrence` on "Migrate other strokes to linetypes".
- Fitting symbols to blocks -- new task (2026-11-06, D-PH13).

## Edge Cases & Error Handling

Owned by `project-phasing.md` "Edge Cases" (Rule A). Implementation notes:

- An unknown status id in a file (for example a deleted custom status) reads as `new`
  and logs one info line.
- A `PhaseDisplay.hidden` id not in the registry is ignored on load.
- `SheetViewport.paint` already calls `restore_model_display(saved)` in a `finally`; the
  phase step writes only into `saved`, so a render exception cannot leave a model item
  hidden or recoloured.
