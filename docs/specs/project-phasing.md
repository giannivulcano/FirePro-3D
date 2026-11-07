---
status: proposal          # concept ratified 2026-10-20 (grill Q1-Q19 + brainstorm sections 1-5); unbuilt -- slices PH1-PH8
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
  - firepro3d/hydraulic_solver.py
  - firepro3d/pipe.py
  - firepro3d/fitting.py
  - firepro3d/block_instance.py
  - firepro3d/underlay.py
  - firepro3d/model_browser.py
  - firepro3d/underlay_manager.py
  - firepro3d/settings/template.py
  # new: phase_registry.py, phase_display.py
source-tasks: ["Project phasing -- assign a phase (New / Existing / Demolition; custom phases later) to every model element; sheet views display by phase (2026-10-20)"]
---

# Project Phasing -- Design Spec

> **Status: proposal.** Nothing below exists in code yet except the pipe `Phase`
> property (`pipe.py`, enum New / Existing / Demo), which nothing renders. This spec
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
| D-PH4 | Fittings derive their phase from all connected pipes: any New -> New; else any Existing -> Existing; else Demolition. A per-fitting override is allowed. | Q4 |
| D-PH5 | New elements default to New. The pre-placement property-panel template has a Phase field, committed on placement, sticky like the template's other fields. | Q5 (user's own answer) |
| D-PH6 | Legacy projects: saved pipe phases are honoured (Demo -> Demolition), every other element loads New, and viewports saved before phasing load with Phasing **off**, so old sheets plot identically. | Q6: old sheets must not change until opted in |
| D-PH7 | The phase-display setting lives on each **sheet viewport** now. View-level defaults (inherited by viewports) are left to the view-templates spec session. | Q7: one plan view per level today; no view duplication needed |
| D-PH8 | Viewport control: a **Phasing** master tick plus one **Show <status>** tick per status. Off = plots exactly as today. Plan, detail, elevation and section viewports, never schematic viewports (section added 2026-11-06: cardinal elevations are section views since the section subsystem shipped). | Q8 + Q19 |
| D-PH9 | New plots with **no override** (as today in every paper colour mode). Only other statuses get overrides. | Q9: Revit semantics |
| D-PH10 | A Display Manager **Phases** tab defines each status's graphics: Colour / Fill / Line Wt / Linetype / Opacity, "--" = no override. Factory: New none; Existing grey lines + light-grey fill; Demolition linetype Demolition (dashed), colour unchanged. On an element drawing a Material pattern (hatch or section cut) the pattern stays: the status Colour drives its lines, fixed-colour patterns included, and the status Fill replaces its background (ruled 2026-11-06). | user request + Q10 |
| D-PH11 | Phase graphics are saved **in the project** and seeded from the project template. | Q11: deliverable identical on any machine |
| D-PH12 | Plan, elevation and section canvas tabs each get the same Phasing control (default off), independent of sheets (section added 2026-11-06). | Q12 |
| D-PH13 | Demolition dashing reaches outlines (walls, floors, roofs, rooms, openings), pipes and block strokes (nested included). SVG symbols (sprinkler, water supply, riser) dash once SB4g makes them System blocks; fittings, also SVG (plain types are hidden today by `Fitting.SHOW_PLAIN_SYMBOLS`), dash once their own follow-up makes them blocks (ruled 2026-11-06). Until then they get colour/opacity only. Underlays take colour only. Text is never dashed. | Q13 + the Phase 2 ratification table |
| D-PH14 | Hydraulics exclude Demolition elements; Existing and New are included; the report lists the exclusions. Quantities count New only (no quantities feature exists yet, 2026-11-06; this binds the first one built). | Q14 |
| D-PH15 | Bulk editing: property-panel multi-edit, right-click **Set Phase**, Model Browser group/filter by phase, Underlay Manager Phase column. | Q15 |
| D-PH16 | Block contents take the placed instance's phase; openings and heads keep their own (panel warns on an opening in a demolished wall); copies keep the source's phase. Definitions carry no phase (explode is Block-Editor-only, C1). | Q16 + section 4 |
| D-PH17 | A hidden status means not drawn, not pickable, not snappable. Host-bound labels/tags follow their host (hidden with it, coloured when shown, never dashed). Dimensions are unaffected. The status bar notes when an edit hides the selection. | Q18 |
| D-PH18 | PDF export and print plot exactly what the sheet shows. 3D view has no phase display in this build (follow-up). | Q19 |
| D-PH19 | Custom statuses (later slice PH8): built-ins New / Existing / Demolition are always present, renamable, not deletable; custom statuses are added in the Phases tab with their own graphics row, appear in every picker and as a Show tick (default shown), and carry an Include-in-calc tick (default on); deleting one in use asks which status receives its elements. | Q17 |
| D-PH20 | The Demolition factory linetype comes from LT7's System > Linetypes (a "Demolition" entry added to its General list); the dash slice is ordered after LT7. | section 3 |

## Acceptance Criteria

AC1-AC14 as ratified in Phase 2, AC15 added 2026-11-06 (task lines in `todo_open.md`, "## Project phasing"):

- [ ] AC1 every phased kind (D-PH3) has a Phase, editable in the property panel.
- [ ] AC2 fitting derivation + override (D-PH4).
- [ ] AC3 template Phase committed on placement through every placement tool (D-PH5).
- [ ] AC4 legacy load per D-PH6; a pre-phasing sheet renders pixel-identical.
- [ ] AC5 viewport Phasing + Show ticks (D-PH8).
- [ ] AC6 Phases tab with factory graphics (D-PH10, D-PH9).
- [ ] AC7 phase graphics round-trip in the project file (D-PH11).
- [ ] AC8 plan/elevation/section tab control (D-PH12).
- [ ] AC9 Demolition dashing coverage (D-PH13).
- [ ] AC10 hydraulic exclusion + report line (D-PH14).
- [ ] AC11 bulk editing tools (D-PH15).
- [ ] AC12 parent/child + copy rules (D-PH16).
- [ ] AC13 hide semantics (D-PH17).
- [ ] AC14 PDF/print = sheet (D-PH18).
- [ ] AC15 a Material pattern keeps its pattern under a phase override (D-PH10, added 2026-11-06).

## Verification Checklist

- [ ] Each slice's VC3 guards (concept doc, "Build slices") shown RED with the change reverted.
- [ ] A project saved before phasing opens and its sheets render pixel-identical to its pre-phasing base (D-PH6).
- [ ] Offscreen sheet render and PDF export agree (D-PH18).
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
