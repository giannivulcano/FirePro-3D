---
status: implemented         # Implemented 2026-11-16 (0.106.0); Phase 3 sections approved 2026-11-14 (approach A, partial-override rule, sections 1-5)
last-verified: 2026-11-16
verified-commit: f5bf752f   # PH3 (0.106.0)
governing-spec: docs/specs/project-phasing.md   # owns the what (D-PH*, AC*); this doc owns PH3's how
concept: docs/superpowers/specs/2026-10-20-project-phasing-concept-design.md   # PD2, PD3, PH3 slice row
applies-to:
  - firepro3d/phase_display.py        # new
  - firepro3d/paper_display.py        # phase merge at row lookup, fittings, underlays, labels
  - firepro3d/paper_space.py          # SheetViewData.phase_display, commit_viewport_edit, ViewportProperties
  - firepro3d/block_instance.py       # _paper_fill_colour slot
  - firepro3d/phase_registry.py       # sip guard, graphics type-check
  - firepro3d/weight_refs.py          # ("phase", sid) holder
  - firepro3d/phases_tab.py           # weight combo refresh
---

# PH3 -- Sheet viewport phasing (build design)

**Implemented 2026-11-16 (0.106.0):** the contract now lives in `docs/specs/project-phasing.md` ("Sheet viewport phasing (PH3, as built)", D-PH8 / D-PH13 / D-PH17 notes); this doc is the historical build design.
**As built:** `project-phasing.md` governs wherever it differs from this doc. In particular: `FORCED` names every slot the status set (colour, fill, line weight, opacity), not only the colour slots (DD1); a section / elevation proxy with no source reads its Hide host's status (opening frames, a slab's occlusion mask, which also hides with a hidden host); a sprinkler proxy reads its node's sprinkler, and the sprinkler / water supply key set follows the item's paper category so section proxies take it too; Display Manager OK with a Phases change re-plots an open sheet. The status Fill reaching section / elevation faces (DD1) shipped as built; its semantics are an open design follow-up (`todo_open.md` "Phase Fill semantics").

## Goal

Sheet viewports (plan, detail, elevation, section; never schematic) get a Phasing tick plus a
Show tick per status. With Phasing on, the paper pass hides unshown statuses and plots each
status's Colour / Fill / Line Wt / Opacity from the Phases tab, in As Authored ON and OFF rows.
Host labels follow their host. PDF export plots what the sheet shows. Linetype (dash) is PH4.

## Motivation

The phase data (PH1) and the Phases tab (PH2) exist, but nothing renders by phase. PH3 makes
the demo plan and new-work plan deliverable from one model (D-PH1).

## Architecture & Constraints

- Paper overrides are transient: `apply_paper_overrides` saves, overrides, and
  `restore_model_display` restores every slot it writes (paper-space.md §6.2). PH3 adds no
  restore logic of its own beyond the new block fill slot.
- PDF export reaches the same `SheetViewport.paint` -> `apply_paper_overrides` call as the
  on-screen sheet (`export_pdf` -> `render_sheet` -> `PaperScene.render`), so AC14 holds by
  construction and is guarded, not built.
- The global Color Mode is retired; each paper category row has `as_authored` (`row_as_authored`).
- `effective_phase(item)` is the single phase reader (PD1).

## Approaches

| | Approach | Verdict |
|---|---|---|
| A | Merge the item's phase graphics into its category row dict before the existing per-type helpers run | **Chosen**: reuses every saved slot; restore unchanged; one call per dispatch site |
| B | Post-pass over `saved` entries overwriting slots | Rejected: extra save keys, duplicates per-type knowledge |
| C | Pass phase values into each `_apply_*` helper | Rejected: ~10 helper signatures |

## Design Decisions

### DD1 -- `phase_display.py` (new)

- `PhaseDisplay(enabled: bool = False, hidden: frozenset[str] = frozenset())`, frozen dataclass.
  `to_dict() -> {"enabled": bool, "hidden": sorted list}`; `from_dict(d | None)`: missing/None ->
  disabled; ids not in the registry are dropped (concept edge case).
- Pass context: `begin_pass(viewport_data)` / `end_pass()` (module-level, set in a `try/finally`
  around the pass). Active only when `viewport_data.phase_display.enabled` and
  `source_view_type != "schematic"`; otherwise inactive.
- `merge(cat, item, *, keys=ALL_KEYS) -> dict`: inactive context -> returns `cat` itself
  (identity; AC4 pixel-identical). Active: `sid = effective_phase(item)`; None (an unphased
  datum / annotation, D-PH3) -> returns `cat` itself, so gridlines, levels and notes always
  plot (plan gate 2026-11-14); otherwise returns a shallow copy with:
  - `visible = False` when `sid in hidden`;
  - `color` <- graphics colour; `fill` and `section_color` <- graphics fill (AC15: in a paper
    pass `draw_section_type` draws hatch lines in the element colour and the background from
    `_display_section_color`, so the pattern stays, its lines take the status colour and the
    fill replaces its background); `line_weight` <- graphics weight (R2, replace);
    `opacity` <- graphics opacity (R1, replace; integer percent);
  - a graphics value of None ("—") leaves the row's value (R1 clarified: "—" keeps the category);
  - `_phase_forced: frozenset` naming the colour slots the phase set (`color`, `fill`).
- `keys` restricts the merge: labels (R4) and underlays (R5) use `{visible, color, opacity}`;
  sprinkler / water supply / fittings use `{visible, color, opacity}` (D-PH13: SVG, no fill/weight).

### DD2 -- Partial override in As Authored rows (ratified 2026-11-14)

Only the slots the phase sets are overridden; every slot left at "—" keeps As Authored. The
helpers that branch on `authored` (`_apply_generic`, `_apply_block`, `_apply_construction`,
`_apply_pipe`, marker / gridline helpers, proxy branch, fitting / SVG tint, underlay) write a
colour slot when `not authored or slot in cat.get("_phase_forced", ())`. With the factory
statuses (Existing sets colour and fill) the rule is invisible; it matters for custom graphics.

### DD3 -- Hook points in `apply_paper_overrides`

- Item loop: `cat = phase_display.merge(cats.get(cat_key), item)` at the row lookup, before
  `authored = row_as_authored(cat)`. Hidden items reach the existing `visible` check after
  `saved.append(entry)`, so restore re-shows them. Branches before the save (section /
  elevation proxies, elevation Grid Line / Level Datum) get their visibility through the same
  check or an added one (plan step 1 probes which).
- Fitting loop and underlay loop: the same merge with their key sets.
- Label dispatch (pipe label, room tag, hydraulic node badge, `_ElevPipeLabel`, any
  `BoundLabelItem` with a phased host): merge with the **host** item and label keys. Tags drawn
  inside a `BlockInstance` (`_bound_ops`) already take the instance's `_paper_pen_color`.
- `SheetViewport.paint` wraps the call in `begin_pass(self._data)` / `end_pass()`.

### DD4 -- Block fill slot

`BlockInstance._paper_fill_colour: QColor | None` (init None). `_apply_block` writes it from the
merged `fill` when the phase forced it; the `block_paper` saved tuple grows to carry it and
restore resets it. `BlockInstance.paint` uses it as the brush of filled ops when set
(whole-instance; no WM3 dependency, concept PD3).

### DD5 -- Viewport data, undo, panel

- `SheetViewData.phase_display: PhaseDisplay` (default disabled); `to_dict` writes
  `"phase_display"`; `from_dict` reads it with the disabled default, so pre-phasing files plot
  identically (D-PH6) with no migration step.
- `commit_viewport_edit(..., phase_display=None)` joins the old/new field diff and pushes one
  `ChangeViewportPropertiesCommand` ("Edit Viewport").
- `ViewportProperties.get_properties`: on non-schematic viewports a `Phasing` bool row; when
  enabled, one `Show <name>` bool row per registry status in registry order (R6: rows hidden
  while off). `set_property` builds the new `PhaseDisplay` and commits it.

### DD6 -- Hardening (folded PH2 leftovers, R7)

- `effective_phase`: a sip-deleted item returns None (`sip.isdeleted` guard).
- `PhaseRegistry` normalises graphics on install / from_list: opacity -> int clamped 0-100, a
  non-numeric value -> None; colour / fill / weight / linetype not str -> None.
- `weight_refs`: `iter_weight_refs` yields each phase graphics weight as
  `(name, ("phase", sid))`; `retarget_weight_refs` renames it in the live registry (and
  `PhasesTab.retarget_weights` in the tab's working copy); so deleting a weight a phase uses
  counts the phase and goes through the LW-DC-5 replace-then-delete dialog (the phase follows
  the pick; there is no refuse path), and a rename follows. The Phases tab's weight combo
  rebuilds from `weight_names()` when the tab is shown.

## Acceptance Criteria

From project-phasing.md (AC4 render half, AC5, AC9 minus dash, AC13 paper, AC14, AC15) plus:

- [ ] AC4r A viewport with no `phase_display` and a Phasing-off viewport render pixel-identical to base.
- [ ] AC5 Phasing + Show rows (R6) on plan / detail / elevation / section viewports; absent on schematic; undoable; saved.
- [ ] AC9p Existing walls, floors, roofs, rooms, openings, pipes, blocks plot the status colour / fill / weight / opacity in As Authored ON and OFF rows (R1-R3); sprinklers, water supply, fittings take colour + opacity; underlays colour + opacity (R5).
- [ ] AC13p A hidden status is not drawn; its host labels are not drawn; shown labels take the host's colour + opacity (R4).
- [ ] AC14 The exported PDF raster matches the on-screen sheet render.
- [ ] AC15 A hatched Existing wall keeps its hatch; hatch lines = status colour, background = status fill.
- [ ] DD2 A colour-only status in an As Authored row keeps the element's authored fill.
- [ ] DD6 Deleting a weight a phase uses counts the phase and replaces it with the pick; renaming it retargets the phase; a malformed opacity loads as None and the Display Manager opens.
- [ ] Every render leaves model items' visibility, opacity and colour slots as before (restore).

## Verification Checklist (VC3 guards)

- Offscreen render through a real `PaperScene` + `SheetViewport.paint` with real Wall (hatched
  material), FloorSlab, Pipe (+ label), BlockInstance, Sprinkler, Underlay at Existing /
  Demolition: sampled pixels = status colour in As Authored ON and OFF rows; Demolition unticked
  -> background pixels where the element and its label were.
- Opacity / weight: blended pixel matches the phase opacity; stroke px width matches the phase weight.
- Phasing off and no-key viewports: render image byte-equal to the render with `merge` forced to
  identity (RED: mutate `begin_pass` to activate regardless of `enabled`).
- `export_pdf` raster vs on-screen render agree at sampled points.
- Panel: `ViewportProperties.set_property` through the property panel -> undo -> rows and data restored.
- Restore: after render, each item's `isVisible`, `opacity`, `_display_color`, `_paper_fill_colour` equal pre-render.
- DD6: Display Manager Line Weights delete / rename driven through the tab with a phase using the weight.
- Each guard shown RED with the change reverted.

## Edge Cases

Owned by project-phasing.md "Edge Cases". Build notes: a hidden id not in the registry is dropped
on load; a schematic viewport ignores a stored `phase_display`; a render exception still reaches
`end_pass()` and `restore_model_display` (finally).

## Follow-ups

- PH4 dash (linetype) -- already filed.
- Sub-item opacity forced to 1.0 without restore (gridline bubbles, marker heads, pipe label) --
  prove pre-existing (VC7) during Phase 5 and file if so.
