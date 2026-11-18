---
status: partial           # concept ratified 2026-10-20 (grill Q1-Q19 + brainstorm sections 1-5); PH1 data model built 2026-11-12 (v0.101.0); PH2 Display Manager Phases tab built 2026-11-12; PH3 sheet viewport phasing built 2026-11-16 (v0.106.0); PH4-PH8 unbuilt
last-verified: 2026-11-17  # paper-pass Account: D-PH Restore bullet pointer only, rest not re-audited; prior 2026-11-16  # PH3 Account: status, D-PH8/9/10/13/17/18 as-built notes, AC4/5/7/9/12/13/14/15, Phase graphics paragraph, edge cases, applies-to; rest not re-audited; prior 2026-11-14  # project-tables Account: D-PH6 / D-PH11 pointers only, rest not re-audited; prior 2026-11-12
verified-commit: 2ce5b3b2  # paper pass protocol (0.107.3; D-PH Restore bullet pointer only); prior f5bf752f  # PH3 (0.106.0; status, D-PH8/9/10/13/17/18, AC4/5/7/9/12/13/14/15, Phase graphics, edge cases only); prior b5f653ea  # project-tables refactor (pointers only); prior 1ac77114  # PH2 (merge to main; status, AC6, AC7, applies-to phases_tab.py); prior f2f0db3e  # PH1 (v0.101.0; status, D-PH4, D-PH5, AC1-AC4, AC12, edge cases); prior da92c5c4
applies-to:
  - firepro3d/phase_registry.py
  - firepro3d/phases_tab.py
  - firepro3d/displayable_item.py
  - firepro3d/paper_display.py
  - firepro3d/paper_space.py
  - firepro3d/level_manager.py
  - firepro3d/section_scene.py
  - firepro3d/section_marker.py
  - firepro3d/display_manager.py
  - firepro3d/network_codec.py
  - firepro3d/scene_io.py
  - firepro3d/hydraulic_solver.py
  - firepro3d/pipe.py
  - firepro3d/fitting.py
  - firepro3d/block_instance.py
  - firepro3d/underlay.py
  - firepro3d/model_browser.py
  - firepro3d/underlay_manager.py
  - firepro3d/settings/template.py
  - firepro3d/phase_display.py       # PH3: PhaseDisplay, paper pass context, row merge (D-PH8, D-PH13, D-PH17)
  - firepro3d/weight_refs.py         # PH3: the ("phase", sid) weight holder only (rest owned by linetypes.md)
source-tasks: ["Project phasing -- assign a phase (New / Existing / Demolition; custom phases later) to every model element; sheet views display by phase (2026-10-20)"]
---

# Project Phasing -- Design Spec

> **Status: partial (PH1 built 2026-11-12, v0.101.0; PH2 2026-11-12; PH3 built 2026-11-16, v0.106.0).** The data model is in code:
> `phase_registry.py` holds the status registry (saved as `"phases"`), the shared Phase
> panel row, the D-PH6 migration (`SAVE_VERSION` 13), the D-PH4 fitting derivation and
> `effective_phase`; every D-PH3 kind carries `phase`, and placement, paste, duplicate and
> array carry it. Sheet viewports render by phase (PH3, `phase_display.py`: see "Sheet
> viewport phasing (PH3, as built)" below). Demolition dashing (PH4), the canvas tab control
> (PH5) and the hydraulics (PH6) do not use it yet. This spec
> owns the *what* (decisions D-PH1...D-PH20). The *how* and the build slices PH1-PH8 are
> owned by [`../superpowers/specs/2026-10-20-project-phasing-concept-design.md`](../superpowers/specs/2026-10-20-project-phasing-concept-design.md).
> Promote each decision to "as built" here as its slice lands.
>
> **Re-checked 2026-11-06** against main when this design landed (1,004 commits after it was
> written). D-PH8, D-PH10, D-PH12, D-PH13 and AC8 carry dated rulings; D-PH14 carries a dated note; AC15 is new.
> Stale code facts were corrected in the concept doc.

## Goal

One model produces both retrofit deliverables: a **demolition plan** (existing + demolished
work) and a **new-work plan** (existing + new work). Every phased model element carries a
phase status. Each sheet viewport, and each plan, elevation or section canvas tab, chooses which
statuses it shows. The Display Manager defines how each status plots: New as authored,
Existing grey, Demolition dashed.

## Motivation

Fire-protection retrofit drawings must show which pipe, heads and building elements stay,
which are removed and which are new. Today the only way is duplicate geometry or manual
recolouring. Revit-like phasing makes it a per-element property plus a per-view filter, and
it lets the hydraulic calc ignore removed work.

## Design Decisions

Each row was ratified at a human gate (grill question or approved design section); the
"because" is the user's stated or selected rationale.

| ID | Decision | Gate / because |
|---|---|---|
| D-PH1 | End goal: Demo plan + New-work plan from one model (retrofit). | Q1 |
| D-PH2 | A phase is a **status label** (one status per element), not a Revit timeline (no created/demolished stages). | Q2: fits demo + new plans; simplest to assign and read |
| D-PH3 | Phased kinds: walls, openings, floors, roofs, rooms, pipes, sprinklers, water supply, block placements, underlays. Datum/annotation items (gridlines, level datums, view/detail markers, text, dimensions, design areas, hydraulic badges) carry none and always plot normally. 2D drafting takes its block placement's phase (model space holds no loose geometry, containment C1/C8). | Q3 + section 1 |
| D-PH4 | Fittings derive their phase from all connected pipes: any New -> New; else any Existing -> Existing; else Demolition. A per-fitting override is allowed. Ruled 2026-11-11 (PH1): the override is a **Fitting Phase** row on the node's panel, `Auto (<derived>)` plus each status; picking Auto clears the override. A saved override id the project no longer has loads as Auto (built PH1). | Q4 + PH1 FP1 |
| D-PH5 | New elements default to New. The pre-placement property-panel template has a Phase field, committed on placement, sticky like the template's other fields. Ruled 2026-11-11 (PH1): kinds with no pre-placement template today (room, floor opening, water supply, block placement) always place as New; giving them templates is a follow-up. Ruled 2026-11-11 (PH1, Phase 5): drawing a pipe straight on from a free pipe end still merges into that pipe, and the merged pipe takes the template's phase. The template Phase stays set across a sprinkler catalog pick and Auto-populate (R7). | Q5 (user's own answer) + PH1 FP1 + PH1 Phase 5 ask |
| D-PH6 | Legacy projects: saved pipe phases are honoured (Demo -> Demolition), every other element loads New, and viewports saved before phasing load with Phasing **off**, so old sheets plot identically. Where the phase-id migration sits in the open order: [`scene-io.md`](scene-io.md) §3a "Project tables". | Q6: old sheets must not change until opted in |
| D-PH7 | The phase-display setting lives on each **sheet viewport** now. View-level defaults (inherited by viewports) are left to the view-templates spec session. | Q7: one plan view per level today; no view duplication needed |
| D-PH8 | Viewport control: a **Phasing** master tick plus one **Show <status>** tick per status. Off = plots exactly as today. Plan, detail, elevation and section viewports, never schematic viewports (section added 2026-11-06: cardinal elevations are section views since the section subsystem shipped). Built PH3 (2026-11-16): property-panel rows `Phasing` and, only while it is ticked, one `Show <status>` per status in registry order (PH3 R6); each edit is one undo step; a schematic viewport has neither row and ignores a stored value. Field and panel mechanics: [`paper-space.md`](paper-space.md) §5.2 / §19.4. | Q8 + Q19 |
| D-PH9 | New plots with **no override** (as today in every paper colour mode). Only other statuses get overrides. Built PH3: New's graphics are all "—" (locked, PH2), so a New element plots its paper row unchanged. | Q9: Revit semantics |
| D-PH10 | A Display Manager **Phases** tab defines each status's graphics: Colour / Fill / Line Wt / Linetype / Opacity, "--" = no override. Factory: New none; Existing grey lines + light-grey fill; Demolition linetype System > Line Types > Demolition (dashed; the stored value is in D-PH20), colour unchanged. On an element drawing a Material pattern (hatch or section cut) the pattern stays: the status Colour drives its lines, fixed-colour patterns included, and the status Fill replaces its background (ruled 2026-11-06). Built PH3: the status Fill fills the element's Fill and Section colour slots, so section / elevation cut and projected faces take it too; shipped as built at the PH3 smoke (2026-11-16), and where a status Fill should apply is an open design follow-up (`todo_open.md` "Phase Fill semantics"). | user request + Q10 |
| D-PH11 | Phase graphics are saved **in the project** and seeded from the project template. The template phases overlay at New / startup after the seed reset, and the file's phases install on open: order owned by [`scene-io.md`](scene-io.md) §3a "Project tables". | Q11: deliverable identical on any machine |
| D-PH12 | Plan, elevation and section canvas tabs each get the same Phasing control (default off), independent of sheets (section added 2026-11-06). | Q12 |
| D-PH13 | Demolition dashing reaches outlines (walls, floors, roofs, rooms, openings), pipes and block strokes (nested included). SVG symbols (sprinkler, water supply, riser) dash once SB4g makes them System blocks; fittings, also SVG (plain types are hidden today by `Fitting.SHOW_PLAIN_SYMBOLS`), dash once their own follow-up makes them blocks (ruled 2026-11-06). Until then they get colour/opacity only. Underlays take colour only. Text is never dashed. Built PH3 (dash itself is PH4): sprinklers and water supplies (the plan symbol and its section / elevation proxy alike) and fittings take a hidden status, Colour and Opacity, no Fill or Line Wt; ruled PH3 R5 (2026-11-14): underlays are never dashed and take a hidden status, Colour and Opacity, superseding "colour only" above. | Q13 + the Phase 2 ratification table + PH3 R5 |
| D-PH14 | Hydraulics exclude Demolition elements; Existing and New are included; the report lists the exclusions. Quantities count New only (no quantities feature exists yet, 2026-11-06; this binds the first one built). | Q14 |
| D-PH15 | Bulk editing: property-panel multi-edit, right-click **Set Phase**, Model Browser group/filter by phase, Underlay Manager Phase column. Ruled 2026-11-11: property-panel multi-edit ships in PH7 with Set Phase. | Q15 + PH1 FP1 |
| D-PH16 | Block contents take the placed instance's phase; openings and heads keep their own (panel warns on an opening in a demolished wall); copies keep the source's phase. Definitions carry no phase (explode is Block-Editor-only, C1). Ruled 2026-11-11: PH1 makes pasted, duplicated and arrayed pipes keep the source pipe's properties (phase included) and adds water supply to paste. | Q16 + section 4 + PH1 FP1 |
| D-PH17 | A hidden status means not drawn, not pickable, not snappable. Host-bound labels/tags follow their host (hidden with it, coloured when shown, never dashed). Dimensions are unaffected. The status bar notes when an edit hides the selection. Built PH3 on sheets: a hidden status is not plotted; pipe labels, room tags and section / elevation proxy labels hide with their host and, when shown, take its status Colour and Opacity (PH3 R4); section opening frames and a slab's occlusion mask follow their host's status. Not pickable / not snappable and the status-bar notice belong to the canvas tabs (PH5). | Q18 |
| D-PH18 | PDF export and print plot exactly what the sheet shows. 3D view has no phase display in this build (follow-up). Built PH3: export and print reach the same viewport paint as the on-screen sheet. | Q19 |
| D-PH19 | Custom statuses (later slice PH8): built-ins New / Existing / Demolition are always present, renamable, not deletable; custom statuses are added in the Phases tab with their own graphics row, appear in every picker and as a Show tick (default shown), and carry an Include-in-calc tick (default on); deleting one in use asks which status receives its elements. | Q17 |
| D-PH20 | The Demolition factory linetype comes from LT7's System linetypes (a "Demolition" entry); the dash slice (PH4) is ordered after LT7. Ruled LT7 R5 (2026-11-17), built LT7: the factory value is the System block id `system-line-types-demolition` (`constants.PHASE_DEMOLITION_LINETYPE`; the block ships in System > `Line Types`, [`linetypes.md`](linetypes.md) "LT7"). A stored legacy name `"Demolition"` (pre-LT7 files and saved defaults) maps to that id where every row is parsed (`phase_registry._norm_graphic`), so it loads, copies and saves as the id. | section 3 + LT7 R5 |

## Acceptance Criteria

AC1-AC14 as ratified in Phase 2, AC15 added 2026-11-06 (task lines in `todo_open.md`, "## Project phasing"):

- [x] AC1 every phased kind (D-PH3) has a Phase, editable in the property panel (PH1). An underlay Phase edit marks the project unsaved with no undo step, as underlay edits do (R6).
- [x] AC2 fitting derivation + override (D-PH4) (PH1).
- [x] AC3 template Phase committed on placement through every placement tool (D-PH5) (PH1).
- [x] AC4 legacy load per D-PH6; a pre-phasing sheet renders pixel-identical. Load half built in PH1 (v12 fixture guard); render half built in PH3: a viewport record with no `phase_display` loads with Phasing off (no migration step), and a Phasing-off pass returns each paper row unchanged (guard AC4r).
- [x] AC5 viewport Phasing + Show ticks (D-PH8). *(PH3, 2026-11-16: undoable, saved with the viewport.)*
- [x] AC6 Phases tab with factory graphics (D-PH10, D-PH9). *(PH2, 2026-11-12: `phases_tab.PhasesTab`, appended after Materials; columns STATUS / COLOUR / FILL / LINE WT / LINETYPE / OPACITY; `None` = "—" no override in every cell; the New row is shown and locked to "—" (D-PH9); Reset All = D-PH10 factory into the working copy; Set as Default writes only the template's `"phases"` key (`settings/template.save_phases_as_default`); Demolition's linetype showed `missing_label("Demolition")` until LT7 (D-PH20); since LT7 (2026-11-18) it shows "Demolition", the shipped block. Stored units: colour/fill as the picker returns them (`""` = No Fill, a real override), weight a line-weight **name**, linetype a block id, opacity an **integer percent** 0–100.)*
- [x] AC7 phase graphics round-trip in the project file (D-PH11). *(PH2: the tab edits a `PhaseRegistry.copy()`; OK installs it via `set_project_table` only on a net change, outside undo, and dirties the project (a folder linetype it names loads outside undo too); Cancel leaves the registry untouched. PH3: OK with a net Phases change also re-plots an open sheet.)*
- [ ] AC8 plan/elevation/section tab control (D-PH12).
- [ ] AC9 Demolition dashing coverage (D-PH13). PH3 built the non-dash half on sheets (status Colour / Fill / Line Wt / Opacity per kind, D-PH13 note); the dash is PH4.
- [ ] AC10 hydraulic exclusion + report line (D-PH14).
- [ ] AC11 bulk editing tools (D-PH15).
- [ ] AC12 parent/child + copy rules (D-PH16). PH1 built the copy rules: paste, duplicate and array keep each element's phase and the fitting override, and pipes keep their whole record. A water-supply paste is refused while the project has one (R5). PH3 built the render half: the paper pass reads each item's status through `effective_phase` (a block child resolves to its outermost placement; a placement paints its contents as one instance). Still to build: the opening-in-a-demolished-wall warning (PH7).
- [ ] AC13 hide semantics (D-PH17). Sheet half built in PH3; canvas tabs PH5.
- [x] AC14 PDF/print = sheet (D-PH18). *(PH3: same paint path; guarded.)*
- [x] AC15 a Material pattern keeps its pattern under a phase override (D-PH10, added 2026-11-06). *(PH3: the hatch stays, lines in the status Colour, background in the status Fill; where Fill applies is the open "Phase Fill semantics" follow-up, D-PH10.)*

## Sheet viewport phasing (PH3, as built)

Build design (historical, approach and DD1-DD6): [`../superpowers/specs/2026-11-14-ph3-sheet-phasing-design.md`](../superpowers/specs/2026-11-14-ph3-sheet-phasing-design.md). Where it differs, this section governs.

- **Pass context.** `phase_display.begin_pass(viewport_data)` / `end_pass()` bracket the viewport's paper pass (in a `finally`). The pass is active only when the viewport's Phasing is ticked and it is not a schematic viewport.
- **Merge at the row lookup.** `phase_display.merge(row, item, keys=...)` returns the paper row itself when the pass is inactive or `effective_phase(item)` is None (an unphased datum or annotation, D-PH3, plots as-is). Otherwise it returns a copy: `visible` False for a hidden status, and each status graphic that is set (not "—") **replaces** the row's Colour, Fill (into both `fill` and `section_color`), Line Wt or Opacity. The copy names the slots the status set (`phase_display.FORCED`).
- **Slots per kind.** Outlines, pipes, blocks and their section / elevation proxies take all four. Sprinklers, water supplies (keyed on the item's paper category, so a section proxy follows too) and fittings take hide, Colour and Opacity (D-PH13). Host labels and tags take hide, Colour and Opacity from the host's status (R4); a label's opacity is the status Opacity when set, else 1. Underlays take hide, Colour and Opacity (R5).
- **Partial override in As Authored rows (DD2, ratified 2026-11-14).** A row with As Authored ON keeps the authored value for every slot the status leaves at "—"; a slot the status sets is written in As Authored ON and OFF rows alike. On a block placement a status Fill paints every fill and pattern op of the instance.
- **Proxy status.** A section / elevation proxy reads its source element's status; a sprinkler proxy (sourced on its node) reads the node's sprinkler; an item with only a Hide host (opening frame lines, a slab's occlusion mask) reads that host's status. A mask with no paper category hides when its host's status is hidden.
- **Stored graphics units (PH2 + PH3 DD6).** Colour and Fill as the picker returns them; Line Wt a line-weight **name**; Linetype a block id; Opacity an **integer percent** 0-100 that replaces the row's opacity (not multiplied; ruled at the PH3 plan, R1). On install / load a non-number, bool or non-finite Opacity reads "—", others are rounded and clamped to 0-100; a non-string Colour / Fill / Line Wt / Linetype reads "—".
- **Line Wt is a by-name weight reference.** Each status's Line Wt is a weight holder (`weight_refs`, kind `("phase", sid)`): a Line Weights rename follows it, and deleting a weight a status uses counts it and goes through the replace-then-delete dialog (rules: [`linetypes.md`](linetypes.md) LW-DC-4 / LW-DC-5). The Phases tab's working copy follows the same rename / replace, and its weight combos rebuild when the tab is shown.
- **Restore.** Every slot PH3 writes is saved by the pass and restored by `restore_model_display` (each owner's `exit_paper_pass`, paper-space.md §6.2.1), including the label opacity, the underlay group opacity and the block fill slot.

## Verification Checklist

- [ ] Each slice's VC3 guards (concept doc, "Build slices") shown RED with the change reverted.
- [ ] A project saved before phasing opens and its sheets render pixel-identical to its pre-phasing base (D-PH6).
- [x] Offscreen sheet render and PDF export agree (D-PH18). *(PH3: `tests/test_ph3_sheet_render.py` AC14 guard; the pre-phasing render half is its AC4r guard, legacy and Phasing-off viewports against an identity merge.)*
- [x] Account (done at landing, 2026-11-06): reconcile `view-relationships.md` §7.4 (phasing is the first built view override; paper viewports already hold per-viewport state) and `paper-space.md` §4.9 (layer overrides retired with the layer system).

## Edge Cases

| Case | Rule |
|---|---|
| Opening (New/Existing) in a Demolition wall | allowed; panel warning row (D-PH16) |
| Tee whose branch is demolished | drawn by derived status over all pipes; for the calc its fitting type derives from the remaining pipes |
| Demolished head inside a design area | not a design head (D-PH14) |
| Edit hides the current selection on a phased tab | the item disappears; status bar notice (D-PH17) |
| Status renamed | every picker, row and Show tick relabels; ids never change |
| File without a `phase` key | element is New |
| Saved status id the project does not have | element reads New (one info log line); a fitting override reads Auto |
| Viewport hides a status id the project does not have | the id is dropped on load (PH3) |
| Schematic viewport with a stored `phase_display` | ignored; the schematic plots as-is (D-PH8) |
| Item deleted while a pass reads it | reads not phased (`effective_phase` returns None, PH3 DD6) |
| Malformed stored graphics (non-numeric Opacity, non-string Colour) | reads "—"; the Display Manager still opens (PH3 DD6) |
| A status named "Title" or "Border" | its `Show <status>` row collides with the viewport's own Show Title / Show Border row: known gap, filed in `todo_open.md` (settle at PH8) |
