# TODO — Open Tasks

> Active/backlog tasks only. Completed work lives in `todo_closed.md` (archive). The `/todo` skill reads THIS file for task selection and moves finished tasks to `todo_closed.md`.
>
> **Task shape** (governed by the task-taxonomy spec): every task is a top-level `- [ ]` line carrying exactly one `[type:bug|feature|design|maint]` tag (first bracket), a plain-English summary, a `[P1|P2|P3]` marker, and an optional `[subject:*]` area tag — with a nested `- Details:` bullet holding file refs, metadata, edge cases, and lineage. Subsystem `##`/`###` headers group by *area*, never by type.

## 🎯 Current Focus — MVP: AHJ Package (decided 2026-06-23 grill; full rationale in `DOCS-REVIEW.md`)

MVP = the plotted **AHJ submittal package (drawings + calcs)** for the Sprinkler Design core of the FPE suite (see `project-suite-vision` / `project-mvp-priority-model` memories).

### B. Paper-space AHJ output (the MVP blocker — most machinery already exists)

- [ ] [type:feature] Per-character (rich-text run) formatting for sheet text [P2] [subject:Architecture]
  - Details: formatting currently applies to the whole block. Spec-level change: `TextAnnotationData` moves from block-level fields to runs (§5.3); QGraphicsTextItem rich-text/QTextCharFormat path; panel + template semantics for partial selections. Needs a spec session first. `paper_space.py`, `docs/specs/paper-space.md §5.3/§9`. Lineage: Sheet-space annotations → property-panel replacement (both done parents).
- [ ] [type:bug] `WallSegment.paint` cosmetic pen ignores the paper "Wall" line-weight [P3] [subject:CAD]
  - Details: `paint()` builds a local `QPen(...).setCosmetic(True)` and never reads `self.pen()`, so `apply_paper_overrides`/`_apply_generic`'s `setPen(width=lw_mm)` is a no-op on wall outlines (walls plot at a fixed cosmetic width regardless of the paper "Wall" line-weight category). Route the wall outline pen through `_display_color`+category weight like the fill. Sibling reference: the pipe line-weight paper-normalization was fixed 2026-09-03 (`fix/pipe-paper-line-weight` → `paper_display._apply_pipe` now divides `lw_mm/paper_scale`, §9.9.1) — the wall version needs the *opposite* fix (make `WallSegment.paint` read the applied pen instead of a hardcoded cosmetic one). `wall.py`, `paper_display.py`.
- [ ] [type:maint] Batch per-level viewport isolation if a many-levels sheet ever lags [P3] [subject:Architecture]
  - Details: v1 applies/restores per differing viewport; a many-distinct-levels sheet does N sweeps. If it ever lags, batch in `paper_export.render_sheet` (group viewports by level, apply once per level, restore once). Filed in `paper-space.md §6.6`; not needed at current viewport counts. Imperceptible-perf → maint. `paper_export.py`.
- [ ] [type:feature] Retrofit wall/floor/roof/geometry template persistence [P3] [subject:Architecture]
  - Details: property-panel spec D0 — pipe/sprinkler/text templates persist, these reset per session. `main.py`, `model_space.py`.
- [ ] [type:feature] Text-box placement polish — rubber-band placement + "Fit to contents" [P2] [subject:UX]
  - Details: (user, 2026-07-20 wrap) (a) click-drag rubber-band placement — drag on Add-Text click sets the initial box size (click-only keeps auto-size); (b) property-panel "Fit to contents" button — resets `box_height_mm`/wrap to the content extents (undo-routed). `paper_space.py`, `property_manager.py`.
- [ ] [type:feature] Absorb the Modify→Text group into the entity-aware Font group [P3] [subject:UX]
  - Details: ribbon-bar spec D2 end state — NoteAnnotation gains family/hex-color/underline (data-model upgrade) and the Font group targets model text too (routed via `push_undo_state`); legacy Modify→Text group deleted. ref: ribbon-bar-spec D2. `main.py`, `annotations.py`, `font_group.py`.
- [ ] [type:feature] Colored highlight for sheet text [P3] [subject:CAD]
  - Details: `opaque_bg: bool` → background color (True→white migration); Word-style highlight palette in Font group + panel. `paper_space.py`, `font_group.py`.
- [ ] [type:feature] Contextual Modify tab that appears on selection and matches the entity [P3] [subject:UX]
  - Details: from the 2026-07-16 ribbon-bar spec grill, D8. Revit-style: Modify tab hidden when nothing is selected, appears+activates on selection, contents specific to the selected entity type, disappears on deselect. Replaces the always-visible tab + force-switch. Needs a design pass (per-entity group registry, QTabBar dynamic insert/remove). ref: ribbon-bar-spec D8. `main.py`, `ribbon_bar.py`.
- [ ] [type:feature] Sheet-text leaders — add/delete leader + leader properties [P2] [subject:Architecture]
  - Details: right-click add/delete leader; leader properties in the panel. (Deferred in the 2026-06-25 grill; pulled back by smoke test.) `paper_space.py`.
- [ ] [type:feature] Sheet-text printed border property (None/Solid/Dashed) [P3] [subject:CAD]
  - Details: (user request, 2026-07-20 smoke) panel dropdown for a printed box border: None (default) / Solid / Dashed / etc.; renders in export as authored; new `TextAnnotationData` field + panel enum row + paint. Distinct from the selection boundary (which is UI-only). `paper_space.py`.
- [ ] [type:bug] Latent point-size ~2.4× PDF over-sizing in the legacy title-block fallback text [P3] [subject:CAD]
  - Details: `TitleBlockItem`/`TitleBlockFieldOverlay`. Scoped down 2026-07-22: viewport view-titles + the "View not found" placeholder were converted to the mm primitive (`_draw_mm_text`, DPI-regression-tested) with the titleblock-template build; the remaining pt text lives only in the no-template fallback chain (renders for projects without a parametric template). ref: paper-space §4.11. `paper_space.py`.
- [ ] [type:feature] Expose paper-space text as a Display-Manager category [P3] [subject:Architecture]
  - Details: project-level colour / opaque-bg customization. `display_manager.py`, `paper_display.py`, `paper_space.py`.

### C. Hydraulic calc deliverable

> Cardinal elevations on sheets ALREADY WORK (`ViewResolver`). Riser (MVP): cardinal elevation + imported standard detail — reuse, no build.

- [ ] [type:feature] Storage protection criteria system (NFPA 13 Table 4.3.1.7.1) [P2] [subject:Sprinkler Design]
  - Details: when Room hazard is Miscellaneous/Low-Piled/High-Piled Storage, conditional Protection Criteria fields appear (Commodity Classification I–IV/Group A plastics, Type of Storage, Storage Height; ceiling height already computed); table lookup resolves to a design curve (OH1/OH2/EH1/EH2 or "See Chapter 25") + hose allowances + duration; resolved curve inherited by design areas AND consumed by auto-populate; badge STORAGE HEIGHT cell fills. Today all three storage classes disengage inheritance with a warning. Needs its own grill (table encoding scope, Chapter-25 rows, in-rack). Lineage: Design-Area Criteria System (done parent). `room.py`, `nfpa_curves.py`, `design_area.py`, `auto_populate_dialog.py`.
- [ ] [type:feature] Hose allowance inside/outside split [P3] [subject:Hydraulic Calculator]
  - Details: WaterSupply gains Inside + Outside hose allowance (old single value migrates to Outside on load); solver total = inside + outside; report + badge HOSE cells (currently TBD) read both. `water_supply.py`, `hydraulic_solver.py`, `hydraulic_report.py`, `design_area.py`.
- [ ] [type:feature] Domestic water allowance → solver demand [P3] [subject:Hydraulic Calculator]
  - Details: currently informational (badge/WaterSupply property only); add to the supply-curve check like hose stream, with report line items. `hydraulic_solver.py`, `hydraulic_report.py`.
- [ ] [type:feature] Auto-generated one-line riser diagram from pipe/valve topology [P3] [subject:Sprinkler Design]
  - Details: desired POST-MVP differentiator (plays to the hydraulic/topology strength). Arbitrary-angle section-view subsystem is deferred OUT of the MVP (2026-06-23) — cardinal elevations suffice. `model_space.py`, new module.

### Post-MVP order

- [ ] [type:feature] #1 post-MVP: selection-mode hub (hover pre-highlight + crossing rubber-band + Tab disambiguation + label-only click) [P2] [subject:Architecture]
  - Details: spec done (`docs/specs/selection-mode.md`). ref: selection-mode-spec.
- [ ] [type:maint] Doc reorg execution — `docs/specs/`→`docs/design/`, archive superpowers, backfill frontmatter [P2] [subject:Documentation]
  - Details: `docs/specs/`→`docs/design/`, `docs/superpowers/`→`docs/_archive/` (excluded from build), backfill `status`/`applies-to` frontmatter on specs, add a Design nav tab. Milestone-level. See `DOCS-REVIEW.md` Part 3 + `docs/specs/SPEC-INDEX.md`.

## UI follow-ups

> From the 2026-09-05 UI-cleanup batch.

- [ ] [type:bug] Placement crosshair missing on the visible plan view [P2] [subject:UX]
  - Details: user, 2026-09-08 U3 smoke — confirmed PRE-EXISTING, NOT U3: the U3 branch's only `model_view.py` change is the grip-loop `continue`, which doesn't run during placement; the crosshair enable/draw path is untouched. The accent crosshair (`ui/crosshair`, default ON) is applied once at startup by `main.py:747 _apply_crosshair` looping `self.scene.views()` → `set_crosshair_enabled`. Leading hypothesis: the `Model_Space vestigial-view` bug (`scene.views()` = a hidden index-0 view + one per plan tab, `project_model_space_vestigial_view_bug`) — at startup the crosshair may be enabled only on the vestigial/not-yet-visible view, so the real visible tab never gets it → no crosshair on placement. Diagnostic: toggling Preferences→UI crosshair off/on re-runs `_apply_crosshair` over the current views and (if this is it) restores it. Fix direction: apply the crosshair to the active/visible view (and on tab-open), not just once at startup over `views()[0]`; or gate on `_active_view()`. Live-only. `main.py` (`_apply_crosshair`), `firepro3d/model_view.py` (`_crosshair_enabled`).
- [ ] [type:feature] Frameless MainWindow → true immersive fullscreen with a custom header strip [P2] [subject:UX]
  - Details: deferred from the UI-cleanup batch; the `ui/immersive` mode currently = `showMaximized`, which keeps the OS title bar but the Windows taskbar stays visible — user wants header shown AND taskbar hidden, which Windows won't do natively for a framed window. Enabler insight: a custom title strip is app content, so it survives `showFullScreen()` → frameless MainWindow + custom strip + `showFullScreen()` = covers the whole screen (taskbar hidden) with the header visible. Adopt `FramelessShellMixin` (currently `QDialog`-oriented, used by Underlay/Block managers) on the MainWindow app-wide (replaces the native title bar for ALL sessions — not just immersive). Own grill→design→build. Enablers LANDED 2026-09-06 with the UI Design-System task: governing spec `docs/specs/ui-design-system.md` records this as deferred wave #2; the `HouseDialog`/`build_dialog_qss`/`theme.M` infra + `restyle()` seam exist. Step 1 = parameterize the mixin's hardcoded `FramelessWindowHint | Dialog` flag → a `window_type` arg. Risks: wrong flag for a top-level window; MainWindow chrome restructure (strip above the ribbon; min/max/close/drag/Aero-snap/multi-monitor maximize); and the VTK native-child-window crash class (View3D forces native sibling windows — the qFatal surface). Then `_apply_immersive` switches from `showMaximized` to `showFullScreen`. `main.py`, `firepro3d/frameless_shell.py`, `firepro3d/preferences_dialog.py`. ref: ribbon-bar-spec, theming.md.

## UI Design-System follow-ups

> From `docs/specs/ui-design-system.md` deferred waves + P4/P5 review notes (2026-09-06).

- [ ] [type:maint] Deferred wave: migrate the ~20 native-title-bar dialogs onto `HouseDialog` [P2] [subject:UX]
  - Details: conversion waves. Checklist in the spec: `PreferencesDialog`, `DisplayManager`, `TitleBlockEditorDialog`, `AutoPopulateDialog`, `SprinklerManagerDialog`, `RoofDialog`, `WallDialog`, `PaperExportDialog`, `ArrayDialog`, `CalibrateDialog`, `LevelDialog`, `ViewRangeDialog`, `ThermalRadiationDialog`, `DesignPointDialog`, `FSVisibilityDialog`, `SectionPatternDialog`, `SheetViewPropertiesDialog`, `RevisionsDialog`, `_RecordEditDialog`, `AlgorithmParamsDialog`. Each is a per-dialog parity relocation (header/body/footer + `houseDialog` marker). ref: ui-design-system.
- [ ] [type:maint] Complex-dialog body-container transparency check [P3] [subject:UX]
  - Details: the P4 smoke found simple dialogs' bare-`QWidget` bodies inherited the dark canvas fill (fixed via `body_layout()`); the managers/import pass their own container widgets to `set_body(margin=(0,0,0,0))`. Verify those containers don't show a dark mismatch in any uncovered gaps (mostly tiled, so likely fine); if they do, set the container transparent or route through a transparent wrapper. `underlay_manager.py`, `block_manager.py`, `underlay_import_dialog.py`.
- [ ] [type:maint] Extend the metrics-drift guard test to the complex dialogs [P3] [subject:Testing]
  - Details: once their body CONTENT sizing (column widths, filter widths) is separated from chrome — the guard (`test_metrics_drift_guard.py`) currently covers only `house_dialog.py`/`ui_kit.py`/`make_block_dialog.py`/`themed_message.py`.
- [ ] [type:maint] Post-migration cleanups (P4/P5 review NOTEs, all inert) [P3] [subject:Code Quality]
  - Details: dead `findChild(QDialogButtonBox)` fallback in `underlay_import_dialog._set_controls_enabled`; `apply_stylesheet=False` now leaves the `houseDialog` marker set while blanking the sheet (harmless — marker with no sheet does nothing); pre-existing dead `numericInputRequested` signal (`main._on_numeric_input_requested` is never emitted). `underlay_import_dialog.py`, `underlay_manager.py`, `block_manager.py`, `main.py`.
- [ ] [type:maint] `themed_input_number` unit awareness [P3] [subject:UX]
  - Details: the dimension variant builds `DimensionEdit(None, initial_mm=…)` (`scale_manager=None` → bare-mm display/parse). If a caller needs unit-system-aware display (imperial), thread a `ScaleManager` through the helper. Minor. `themed_message.py`.
- [ ] [type:maint] Live theme-switch-while-open wiring [P3] [subject:UX]
  - Details: folds into the existing "Latched `detect()`" item; `HouseDialog.restyle()` seam now exists. ref: ui-design-system.

## Block System

> 2D symbol definitions + instances; sibling to Features. Governing spec `docs/specs/block-system.md`; landed slices S1–S4.6 in todo_closed.md.

- [ ] [type:feature] Interactive snapped origin-pick for make-from-selection [P3] [subject:UX]
  - Details: S2.x smoke follow-up. v1 uses the selection bounding-box top-left as the block origin (modeless, testable); wire a `set_scale`-style transient single-click snapped origin-pick so the user chooses the insertion base. `main.py`, `model_space.py`.
- [ ] [type:feature] Snap/ALIGN completeness for blocks (first cut landed 2026-09-04) [P3] [subject:CAD]
  - Details: S2.x smoke follow-up. `snap_engine._collect` now emits a BlockInstance's insertion origin (center) + transformed geometry endpoints; ALIGN point-acquire follows for free. Deferred: midpoints/quadrants/intersections of block geometry (circles emit bézier nodes, not center/quadrants), and directional ALIGN (parallel-to-a-block-edge — `_source_item_direction` returns None for blocks today). `snap_engine.py`, `model_space.py`.
- [ ] [type:feature] Block thumbnails (the deferred S4 "+ thumbnails") [P3] [subject:UX]
  - Details: S4.x follow-up. Render `BlockDefinition.render_ops()` → `QPixmap`; PNG-next-to-`.fpdb` + `index.json` `thumbnail` field; keyed `(id, version)`; preview column in the Manager + Blocks browser. `block_manager.py`, `block_library.py`, `blocks_browser.py`.
- [ ] [type:feature] Default / preloaded blocks [P3] [subject:Architecture]
  - Details: S4.x follow-up. A curated block set shipped with the app + auto-preload into a project via project templates / user profile (user's stated direction; S4.5 loads only what's on disk).
- [ ] [type:feature] Load-collision: rename-on-load [P3] [subject:UX]
  - Details: S4.x follow-up. Loading a different-`id` block whose `(library,series,name)` is already loaded is refused; offer a rename-on-load instead. `model_space.py`, `block_manager.py`.
- [ ] [type:feature] Save-collision: rename-on-collision (deferred from the 2026-09-05 identity-lookups fix) [P3] [subject:UX]
  - Details: S4.x follow-up. A cross-`id` Save-to-Library filename collision now warns + offers overwrite/cancel (`BlockNameCollision`); a true rename option (pick a new name instead of clobbering) is deferred because block metadata is read-only outside the v2 Editor. Wire rename once the Editor / inline-rename exists. `block_manager.py`, `main.py`.
- [ ] [type:maint] Autofilter polish (partly done 2026-09-05) [P3] [subject:UX]
  - Details: S4.x follow-up — `feat/block-manager-autofilter-polish`: funnel/native-sort-indicator overlap fixed (native indicator suppressed; `FilterHeader` paints its own sort caret left of the funnel) + column widths/order/sort persisted across sessions (`QHeaderView.saveState/restoreState` blob under `BlockManager/headerState`, None-guarded). Footer already reads "N of M blocks · K instances" (adequate — left as-is). Remaining/optional: group-count roll-up N/A (flat). `block_manager.py`.
- [ ] [type:feature] Feature re-architecture (deferred sibling milestone) [P2] [subject:Architecture]
  - Details: the locked-but-unbuilt Feature contract from the block grill: 3-tier `Class/SubClass/Type` + `.fpdf`, non-parametric (size = read-only attr of the Type def), openings decomposed into `Door`/`Window`/`Opening` Classes, + the Feature projection-map (which Block draws a Feature in plan/each elevation; no plan block → fallback to true 3D projection) + Feature Editor projection panel + "Generate from 3D". Naming/extension locked in `block-system.md`; supersedes the Feature naming item at the Opening-element cluster. Own milestone.

## Underlay Import dialog

- [ ] [type:maint] DRY the Modify pending-state consume [P3] [subject:Code Quality]
  - Details: fold the 3 consume sites (sync PDF + `_on_extract_finished` + memoized `_extract_for_layout`) into one `_consume_pending_modify_state()` helper and remove the side-effecting pending-layer read from `_populate_layer_list`. `underlay_import_dialog.py`.
- [ ] [type:maint] Dark-theme white-on-accent contrast [P3] [subject:UX]
  - Details: `on_accent=#ffffff` on the dark accent `#63BE8B` (light green) may read low-contrast on primary buttons/switch-checked; if so, use `accent_ink` for dark specifically. `theme.py`.
- [ ] [type:feature] Per-element underlay selection (original ask #2) [P2] [subject:CAD]
  - Details: select/hide individual geometry elements within an underlay; needs its own spec (conflicts with the batched-QPainterPath perf model). `model_space.py`.
- [ ] [type:maint] App-wide typography role sweep [P3] [subject:UX]
  - Details: apply the Title/Body/Overline/Control roles across ribbon group labels + docks (import dialog + DimensionEdit done). `theme.py`, `main.py`, `ribbon_bar.py`, `property_manager.py`. ref: theming.md.
- [ ] [type:bug] PDF custom scale not persisted to QSettings [P3] [subject:UX]
  - Details: `_save_settings` reads the hidden raw `_custom_scale_edit` during a PDF-ratio session, so a calibrated/typed custom PDF scale resets to the seed next launch (DXF raw-factor persistence unaffected). Persist `_current_scale()` when `_ratio_fields_active()` + back-solve on restore. `underlay_import_dialog.py`.
- [ ] [type:bug] Import rotation field is sticky across imports [P3] [subject:UX]
  - Details: user, 2026-09-02 underlay-slice smoke — pre-existing, NOT the slice; branch-vs-`main` parity proven. The Placement-page Rotation field persists to `UnderlayImport/rotation` QSettings (`_save_settings`/`_restore_settings`) and is restored on the next dialog open, so a rotation set once silently reapplies to all subsequent imports (PDF and DXF — one shared field/key), which reads as "for some reason everything imports rotated N°". Decide the desired UX: reset rotation to 0 per fresh import (keep persistence only for Modify), or make the non-zero rotation more discoverable (highlight when ≠0). Calibration is scale-only (no angle), so this is the only sticky-rotation source. `underlay_import_dialog.py`.
- [ ] [type:bug] Duplicate underlay drops import fields [P3] [subject:CAD]
  - Details: `underlay_context_menu._duplicate` copies neither `selected_layers` nor `import_scale`/`import_base_x/y`, so a duplicated PDF renders all layers at a wrong transform. Same class as the Modify layer bug, different entry point. `underlay_context_menu.py`.
- [ ] [type:maint] Name-through-Modify integration test gap [P3] [subject:Testing]
  - Details: the "edited name survives `replace_underlay`/`apply_import_params_preserving_management`" path is verified only by reading + unit tests; add an integration test so a future removal of `name` from `_GEOMETRY_PLACEMENT_FIELDS` is caught. `tests/`.
- [ ] [type:feature] Cancel inert during GUI-thread preview-build [P3] [subject:CAD]
  - Details: same root as the spinner stutter, user-accepted. Extraction is cancellable now, but the post-extraction preview-path build blocks the GUI thread so Cancel (and the spinner) freeze there. Real fix = incremental/off-thread preview build (same territory as `underlay-workflow §18` perf work). `underlay_import_dialog.py`.
- [ ] [type:maint] Calibration snap tolerance is strict (2%) [P3] [subject:UX]
  - Details: a metric `1:10.3` measurement won't snap (only ≤~1:10.15). Bump `_SCALE_SNAP_TOL` to 0.03 if real-world picks land further off. `underlay_import_dialog.py`.
- [ ] [type:bug] PDF reload inline-cache key mismatch [P3] [subject:CAD]
  - Details: with a layer subset active, `_import_pdf_vectors` writes the inline cache under a `selected_layers=None` key while the reader keys include `selected_layers`, so the next reload cache-misses and re-extracts once (correct rendering throughout; masked after the first project Save). Fix the write key + tighten the "layer-agnostic cache key" comment. `model_space.py`.
- [ ] [type:bug] Snap marker z-order over grip during snapped grip-drag [P3] [subject:UX]
  - Details: cosmetic; documented in `drawForeground`. The unified painter draws the marker with the trace (before grips), so a grip fill paints over the marker centre during a snapped grip-drag. Restore marker-after-grips only if it visibly bothers. `model_view.py`, `snap_engine.py`.
- [ ] [type:maint] Task-1 minor: redundant page-0 PDF worker churn + semi-synthetic error-path test [P3] [subject:Code Quality]
  - Details: redundant page-0 PDF worker churn on a Modify of a non-zero page (two workers superseded before the target); the PDF error-path test is semi-synthetic (calls `_on_pdf_extract_error` directly rather than a raising worker). `underlay_import_dialog.py`.

## PDF/DXF import geometry inflation

- [ ] [type:maint] DXF geometry inflation — bench-first flatten tuning [P2] [subject:CAD]
  - Details: filed 2026-08-30 from task 73; PDF sibling shipped. Bench whether DXF `SPLINE entity.flattening(0.5)` (`dxf_import_worker.py:549`) and the fixed-count ARC/ELLIPSE tessellation (`steps=64`) actually inflate a reference DXF underlay before changing anything. Note the unit gap: DXF tolerance is in drawing units (mm/inch/feet, file-dependent), not paper points — decide unit-normalization (e.g. via `$INSUNITS`/extents) so a fixed number means a fixed plotted deviation. Consider a Preferences knob mirroring the PDF one. Needs a representative DXF underlay to visually gate. `dxf_import_worker.py`, `underlay_cache.py`, `preferences_dialog.py`. ref: underlay-workflow §18.5.

## Accent-colour / status-chrome unification

- [ ] [type:maint] Full chrome unification (follow-up) [P3] [subject:UX]
  - Details: the deferred remainder of the accent-unify task: (a) migrate the OFF-state pill/toolbar greys (`#888`/`#555`/`#243a4e`/`#3a607e`/`#99bbdd`) and the SNAP toolbar `:checked` background (`#2a5a8a`) onto theme tokens; (b) add live theme-switch restyling so a Preferences→UI change repaints without relaunch — needs icon-loader cache invalidation (spec §6 says process-lifetime today) + re-applying the pill/badge/toolbar styles; (c) add `main.py` to the `test_theme_chrome_hexguard.py` allow-list once (a) lands. Bundles with the "Latched `detect()` in construction-time consumers" item. `main.py`, `firepro3d/icons.py`, `firepro3d/theme.py`, `tests/test_theme_chrome_hexguard.py`.

## Floor placement workflow

- [ ] [type:feature] Roof twin — mirror the floor two-boundary + wall-mirrored placement onto roofs [P2] [subject:Architecture]
  - Details: apply this identical two-boundary + wall-mirrored-placement treatment to `roof.py`/`roof_rect` (the agreed fast follow-up; roof is structurally identical to floor). `roof.py`, `model_space.py`.
- [ ] [type:feature] Paper-viewport dynamic view-height parity [P3] [subject:Architecture]
  - Details: T4's `compute_view_height` recompute is scoped to on-screen `_apply_plan_level`; paper `SheetViewport` still renders from the cached `pv.view_height` via the resolver. Wire the dynamic upper-bound (or the explicit flag) into paper rendering so plotted sheets match on-screen. `paper_space.py`, `paper_export.py`, `level_manager.py`.
- [ ] [type:design] Wall/roof template-name behavior diverges from floor [P3] [subject:UX]
  - Details: floor now seeds placed instances from the template name (uniquified "Slab/Slab 1/…"); walls/roofs still auto-number "Wall N"/"Roof N" and show a vestigial editable template Name. Decide whether to unify them onto the floor behavior. `model_space.py`.
- [ ] [type:feature] Floor polygon Ctrl angle-constraint [P3] [subject:CAD]
  - Details: `_move_floor` (polygon) publishes the raw snapped point; `_move_wall` applies `_constrain_angle` under Ctrl before publishing. Add Ctrl angle-snap parity to floor polygon segments. `model_space.py`.
- [ ] [type:maint] T5 placement test-hardening gaps [P3] [subject:Testing]
  - Details: holistic-review notes — typed-HUD-dimension commit test for floor rect; center-rect 3-step placement test; cross-primitive-cycle-guard (cycling mid-placement refused) test; Delete-pop test for the floor polygon. `tests/test_floor_placement_workflow.py`.
- [ ] [type:feature] RegularPolygon as a floor boundary primitive (dropped scoping option, 2026-08-27) [P3] [subject:CAD]
  - Details: register the parametric N-gon into the floor ←/→ cycle (↑/↓ sides), if wanted. `model_space.py`, `floor_slab.py`.

## ALIGN placement & misc CAD

- [ ] [type:bug] Doors at ground level (elevation 0) don't render in plan/sheets until a level switch [P2] [subject:CAD]
  - Details: user, 2026-08-27 paper-space-bundle smoke test — NOT yet root-caused; a live-only render bug, needs the running app. Symptom: a door hosted on a ground-level (elevation 0) wall shows a solid wall, no door in plan view AND on sheets; the door is visible in 3D; switching the active level away and back (or nudging the level elevation off 0) makes it appear and it persists. Ruled out (headless, proven): the data/z/visibility/geometry are all correct through the FULL save→`load_from_file`→`apply_to_scene` path — after load the opening is in `wall.openings`, `isVisible()==True`, z-pinned above its host wall (`op.z=30.83 > wall.z=30.78`, the §585 `Z_CAT_OPENING` pin), path non-empty, `z_range=(0,2032)`. `_apply_z_filter` at `[view_depth=-1000, view_height=2000]` keeps it visible. The plan gap is drawn by `WallOpening._paint_symbol` filling `_gap_rect` with the scene-bg colour (needs `op.z>wall.z`, which holds) — NOT `_is_section_cut`-dependent. A MainWindow `_load_project` test asserts the door visible after load and passes (doesn't reproduce). A speculative "build ViewResolver before `_activate_plan_view`" fix was tried and reverted — it's a functional no-op. Leading hypothesis: a live-only stale-paint / missing viewport invalidate on first load. Next (needs the live app): (a) does zoom in/out alone (repaint, no `apply_to_scene`) fix it? → pure stale-paint → force a repaint/`scene.update()` after load; (b) is the door selectable where it should be vs nothing there? Also compare vs `main` to confirm pre-existing vs a bundle regression. `wall_opening.py` (`_paint_symbol`/`_gap_rect`), `model_view.py`, `main.py`, `level_manager.py`.
- [ ] [type:feature] ALIGN: Parallel-OFFSET tracking (perpendicular offset from a reference line) [P2] [subject:CAD]
  - Details: user, 2026-08-26 ALIGN smoke test — the parallel behavior actually wanted. The shipped direction-acquire "Parallel" only constrains direction (draw parallel, length along it) and is defaulted OFF (`ALIGN_DIR_PARALLEL_DEFAULT=False`, flaky track-swap flicker). What the user wants is in-placement OFFSET: acquire a reference line, then a typed distance places your point/line parallel to the reference at that perpendicular offset (AutoCAD OFFSET as a live snapping aid). Distinct feature — needs its own grill→design→build: side selection, snap-to-offset-guide vs type-distance, single offset vs repeating array, how the offset guide renders, and whether it replaces or coexists with the direction-track parallel. Reuse the direction-acquire plumbing (`align_controller.py` flavor="direction", `align_engine.py` parallel ray) but the ray becomes an offset line (parallel at distance D) and the HUD field is a perpendicular offset. `align_engine.py`, `align_controller.py`, `model_space.py`, `dynamic_input.py`, `preferences_dialog.py`, `docs/specs/align-placement.md`.
- [ ] [type:feature] ALIGN: discoverability + persistent render for direction-acquire (Parallel) [P2] [subject:UX]
  - Details: user, 2026-08-26 ALIGN smoke test. A direction-acquire (dwell an object's body → acquire its direction for a Parallel guide) currently shows no `+` marker (markers are only drawn for point-acquires, which have a point; a direction-acquire has `point=None`) — so acquiring a direction is invisible. Worse, tracking guides only render when the cursor is snapped to them, so a fixed parallel guide (anchored at the from-point) is invisible until you happen to move onto it. In scope: (1) a distinct direction-acquired indicator (e.g. a "∥" glyph on the acquired reference segment) so the acquire is visible; (2) persistently render the fixed parallel guide (dashed construction line through the from-point) once a direction is acquired + a from-point exists, instead of only-when-snapped; consider whether other acquired guides (extension/perpendicular) should also show a faint persistent path (weigh clutter — likely keep those snap-only). `align_controller.py`, `model_view.py`, `model_space.py`, `docs/specs/align-placement.md`.
- [ ] [type:feature] Re-evaluate the April pipe-3D work (branch `feature/pipe-3d-fixes`, 10 unmerged commits — kept as reference) [P3] [subject:Sprinkler Design]
  - Details: verified 2026-08-25 that NONE of it is on `main` (not superseded): 3D-vector geometry checks (backtrack/collinear/4th-branch/wye converted to 3D vectors; new `cad_math` utils `unit_vector_3d`/`dot_3d`/`angle_between_3d`/`outward_vectors_3d`), vertical riser fittings (`tee_vertical`/`cross_vertical` + SVGs for through-risers — likely valuable for the AHJ riser deliverable), Z-stacked riser-node movement (`z_hint` disambiguation in `find_nearby_node`), contextual `snap_point_45` (uses the reference pipe, not `pipes[0]`), and routing all pipe creation through `add_pipe()`. The branch is 1001 commits behind → do NOT merge/cherry-pick; re-implement the wanted pieces fresh against current `main`, using the branch as reference. First step: decide which of these features are still wanted. `cad_math.py`, `fitting.py`, `node.py`, `pipe.py`, `model_space.py`.

## Wall placement workflow

- [ ] [type:feature] Arc/circle curved walls [P3] [subject:CAD]
  - Details: needs a curved `WallSegment` entity (today it's fundamentally straight; ripples through miter/join/hosting/3D/section/snap). Register the arc/circle primitives into the wall ←/→ cycle once the entity exists. `wall.py`, `model_space.py`.
- [ ] [type:feature] Polygon walls [P3] [subject:CAD]
  - Details: closed loop of N straight mitered `WallSegment`s; ↑/↓ sets N (reserved by the parent task). Resolve the ←/→ vs ↑/↓ key contention (polygon's own placement uses ←/→ for inscribed/circumscribed). `wall.py`, `model_space.py`.
- [ ] [type:design] Review wall sub-variant + polygon-wall key scheme [P3] [subject:UX]
  - Details: when curved/polygon walls land — wall primitives currently expose no 2D-geo sub-variants (rect corner/centre, arc centre/start); revisit whether they should, and where the keys live. `model_space.py`.

## Opening element

- [ ] [type:design] Settle the Feature hierarchy naming BEFORE Phase B/C (raised 2026-09-04) [P3] [subject:Architecture]
  - Details: `feature.py` currently names the tiers Category → Type → FeatureDef (`features_by_category()` returns `dict[category]→dict[type]→list`), with `host_type` orthogonal. User's Revit-aligned mental model expects Category → Family → Type (`user_revit_mental_model`). Decide the canonical names now: renaming after Phase B (Manager UI) / Phase C (Editor) ship — and after any on-disk library keys off `category`/`type` — forces a data migration. Fold the decision into the Feature governing spec forged in Phase B. `feature.py`, `feature_browser.py`.
- [ ] [type:feature] Phase B — Feature Manager [P2] [subject:Architecture]
  - Details: Architecture-ribbon dialog: choose which Features load into the project; template-project prepopulation; Revit "Load Family". Promote the Feature system to its own governing spec here (SPEC-INDEX orphan). `main.py`, new `feature_manager*.py`.
- [ ] [type:feature] Phase C — Feature Editor v1 (constrained to void+symbol) [P2] [subject:Architecture]
  - Details: author new Features by drawing plan/elevation schematics with the 2D-geometry tools + defining size params, wall-cut, `host_type`. Free-form 3D solid authoring deferred to Editor v2 (needs the 3D solid-modeling "operations" system). `main.py`, new `feature_editor*.py`.
- [ ] [type:feature] Full parametrics for Features [P3] [subject:Architecture]
  - Details: beyond the Phase-A scale transform (arbitrary parameter→geometry binding / constraint engine). `constraints.py`, feature modules.
- [ ] [type:design] Feasibility/brainstorm: fold Sprinkler Systems into the Feature framework [P3] [subject:Architecture]
  - Details: Pipe/Fitting/Sprinkler/Valve/Pump. Reconcile the terminology tension first (there "Feature" = discipline/system grouping vs "Feature = concrete placeable definition" here). Own session.
- [ ] [type:feature] Additional host strategies [P3] [subject:Architecture]
  - Details: Floor-hosted (table, riser base), Ceiling-hosted (pendent sprinkler, diffuser), Face/Level-free. `host_type` is in the model from day one; wire the placement strategies.
- [ ] [type:feature] 3D: true solid CSG + re-mitre wall corners [P3] [subject:CAD]
  - Details: Phase A caps opening reveals (watertight shell) and switched `wall.get_3d_mesh` to `quad_points` so opening jambs stay perpendicular on joined walls, but 3D wall corners now butt-join (not mitred). Optionally rebuild walls+openings via PyVista `boolean_difference` (true watertight solids, mitred corners) — grounded as the alternative to reveal-capping; also sets up the future Create-tab "operations". `wall.py`, `view_3d.py`.
- [ ] [type:maint] Opening panel/polish (holistic-review + smoke follow-ups) [P3] [subject:UX]
  - Details: remove the inactive "Level Offset" field from the Openings contextual tab (reused from `_build_placement_group`; openings have no `_level_offset_mm`); rename the Display-Manager category "Opening"→"Openings" for spec parity; remove the now-dead `DOOR_PRESETS`/`WINDOW_PRESETS`/`DOOR_DEFAULT`/`WINDOW_DEFAULT` + the `**_legacy`/`preset` ctor shim in `wall_opening.py`; simplify the redundant `isinstance(item,(DoorOpening,WindowOpening))` in `model_space.py`. `main.py`, `wall_opening.py`, `display_manager.py`, `model_space.py`.

## 2D geometry: first-class level-plane placement + fill

> `EllipseItem` + `SplineItem` native 2D-geometry primitives LANDED 2026-09-08 on `feat/ellipse-spline-primitives` (landed items in `todo_closed.md`). Follow-ups below.

- [ ] [type:bug] Block Editor ribbon registers its mode buttons into the main ribbon's dict, dangling on tab close [P2] [subject:UX]
  - Details: Ribbon `_mode_buttons` dual-registration root fix (surfaced 2026-09-08 — `_sync_mode_buttons` crashed on a deleted Block-Editor `RibbonSmallButton`). A `sip.isdeleted` self-heal guard landed 2026-09-08, but the ROOT cause is the Block Editor ribbon's `_mode()` helper (`main.py:4488`) registering its buttons into the SAME `self._mode_buttons` dict as the main ribbon (overwriting shared-mode keys `draw_circle`/`draw_arc`/`draw_ellipse`/…); closing a Block Editor tab deletes them, dangling the dict. Separate the Block-Editor button registry from the main ribbon (per-surface `_mode_buttons`). `main.py`.
- [ ] [type:feature] Geometric snaps (perpendicular/nearest/tangent, intersection) for ellipse and spline [P3] [subject:CAD]
  - Details: deferred in the 2026-09-08 build, logged in `2d-geometry.md §5` — perpendicular / nearest / tangent on a rotated ellipse (ellipse-segment = quartic) + nearest/perpendicular on a NURBS (numerical projection) + phase-4 intersection participation for both. Named-point snaps (centre/quadrants/endpoints/control-points) already ship. `snap_engine.py`.
- [ ] [type:feature] Revise the block-editor import for full curve fidelity (preserve arcs/splines/ellipses) [P1] [subject:CAD]
  - Details: raised 2026-09-07; now UNBLOCKED — `EllipseItem`/`SplineItem` landed 2026-09-08 + registered in `_PRIMITIVE_FACTORY`. BE4 reuses `UnderlayImportDialog` (preview/scale/insertion/layers) and converts the result to native primitives, but the shared extraction tessellates arcs/splines/partial-ellipses and drops full ellipses (the block-editor factory `geom_dicts_to_primitives` maps LINE→LineItem, CIRCLE→CircleItem, everything else→PolylineItem/skip). Now that `EllipseItem`/`SplineItem` exist: (a) add a curve-preserving extraction path (emit `arc`/`ellipse`/`spline` entities — the DXF worker tessellates ARC deliberately for an angle-convention reason, so solve that for `ArcItem`), (b) map those entity dicts → native curve primitives in `geom_dicts_to_primitives`, (c) apply the dialog's rotation (`ImportParams.rotation`, not handled by `apply_import_transform`), and (d) consider a simplified editor variant of the dialog (hide levels/placement). Also flagged for live smoke: the dialog's async-extraction round-trip + DWG temp-DXF cleanup. `firepro3d/block_editor.py`, `firepro3d/geometry_import.py`, `firepro3d/dxf_import_worker.py`, `firepro3d/underlay_import_dialog.py`. ref: block-system.
- [ ] [type:feature] Vertical / "elevation plane" (section-based) anchoring for 2D geometry [P3] [subject:Architecture]
  - Details: the deferred half of the placement model: draw/anchor 2D geometry on an elevation's vertical cut plane (crosses the current 2D-plan-only authoring contract, `view-relationships §3.1`). Needs its own grill. `construction_geometry.py`, `elevation_scene.py`.
- [ ] [type:feature] Project flat 2D geometry into elevation scenes [P3] [subject:Architecture]
  - Details: flat 2D geometry now has world-Z but isn't projected into elevation scenes. `elevation_scene.py`.
- [ ] [type:feature] Render filled closed 2D shapes in 3D and extrude to solids [P3] [subject:Architecture]
  - Details: the payoff this task lays the foundation for: render filled closed 2D shapes flat in 3D, then extrude to solids (ties into "Generic 3D solid modeling in the Create tab"). `view_3d.py`, `construction_geometry.py`.
- [ ] [type:feature] Per-item hatch scale/density knob for 2D fills [P3] [subject:CAD]
  - Details: legacy manual angle/spacing was dropped for named patterns; a per-item hatch scale knob (like `draw_section_hatch`'s `hatch_scale`) if patterns read too dense/sparse at architectural scale. `construction_geometry.py`.
- [ ] [type:feature] Line-weight field for the "2D Geometry" Display category [P3] [subject:UX]
  - Details: T10 wired colour/visibility/opacity (mirroring Design Area, which has no weight); add a line-weight field if per-category 2D-geometry weight is wanted. `display_manager.py`, `construction_geometry.py`.
- [ ] [type:feature] Explode Polygon → closed polyline + parametric re-edit polish + HUD "Sides" count field [P3] [subject:CAD]
  - Details: deferred 2026-08-24 — Explode Polygon → closed polyline (free per-vertex deformation) + parametric re-edit polish + "Sides" as a HUD COUNT field (Option A dropped the mixed radius+count schema; sides via ↑/↓ + panel only today). `construction_geometry.py`, `dynamic_input.py`.
- [ ] [type:maint] Rename module `construction_geometry.py` → `geometry_2d.py` [P3] [subject:Code Quality]
  - Details: matches `Geometry2DMixin` + the "2D Geometry" ribbon group/category/tab; "construction geometry" is legacy from the retired `ConstructionLine`. Can't be `2d_geometry.py` (module names can't start with a digit). Cross-cutting import churn (~15 files: `model_space.py`, `scene_io.py`, `snap_engine.py`, `paper_display.py`, `model_view.py`, `entity_context_menu.py`, `displayable_item.py`, …). Do as its own mechanical commit after the 2D-geometry polish cluster lands, to keep the behavior diff clean.

## Ribbon overhaul

- [ ] [type:feature] Author the ~46 missing ribbon icons per the new style guide (mockup-gated) [P2] [subject:UX]
  - Details: Floor icon shipped 2026-08-28 with the floor-workflow task. Architecture-tab set shipped 2026-08-28 on `feat/architecture-tab-icons`, grill→mockup-gate→build: authored wall/roof/room/door/window/blank/detail/levels; re-authored `gridline_icon.svg` (was hardcoded `#ffffff` → white-on-white in light theme, violated §4.1); re-authored (thinned) `floor_icon.svg` to match wall depth. Axo 3D family (2:1 dimetric matching floor) for Building elements, 2D symbols for openings/datums; two-token compliant; render-through-loader mockup harness at 54/27px light+dark. Guard tests in `tests/test_icon_theming.py`. Remaining placeholders live in the Create/Sprinkler-Systems/Analyze/Draft/Manage tabs + Tools/Page groups.
- [ ] [type:feature] Populate contextual tabs with per-entity modify groups for wall/room/roof/pipe [P2] [subject:UX]
  - Details: wire type-specific modify tools + the reusable `_build_graphic_override_group` and `_build_placement_group` (both protocol-gated, currently floor/geo2d-only) into the wall/room/roof/pipe/etc. contextual tabs; carry template persistence for wall/roof (floor done). `main.py`, `model_space.py`. ref: ribbon-bar-spec.
- [ ] [type:feature] Wire paper-scene selection into contextual tabs + add Viewport & Sheet Text tabs [P2] [subject:UX]
  - Details: wire the paper scene's selection into the contextual-tab resolver (model-scene-only today), then add the Viewport tab (scale presets / show-border / delete) and a Sheet Text tab (migrate the Draft→Font group into it). `main.py`, `ribbon_bar.py`, `docs/specs/ribbon-bar.md §3.8`. ref: ribbon-bar-spec D9, paper-space §19.4.
- [ ] [type:maint] Forge a governing spec for the Preferences dialog [P3] [subject:Documentation]
  - Details: `preferences_dialog.py` is a new subsystem currently only covered by the design-of-record; promote it to `docs/specs/` + SPEC-INDEX (it's filed in the Orphans table).
- [ ] [type:bug] Restore the radiation dock on startup + wire ImportPane forward-keys read-back [P3] [subject:UX]
  - Details: `restore_settings` restores browser/properties/hydraulics docks but not radiation; GeneralPane persists a default that has no effect until this is wired. `main.py`.
- [ ] [type:feature] Generic 3D solid modeling (extrude/hole/boolean) in the Create tab [P3] [subject:Architecture]
  - Details: generic 3D solid modeling (extrude/hole/boolean) in the Create tab.
- [ ] [type:bug] Normalize the legacy snap dialog's QSettings store + retire the redundant Manage "Snap Settings" button [P3] [subject:UX]
  - Details: `_open_snap_tolerance_dialog`/`_open_snap_settings` (OSNAP toolbar right-click + Manage "Snap Settings") write `inference/alignment_guides` via bare `QSettings()`; SnappingPane uses `QSettings("GV","FirePro3D")`. Normalize the legacy dialog + retire the redundant Manage "Snap Settings" button (now in Preferences). `main.py`.
- [ ] [type:feature] Consolidate scattered/legacy settings dialogs into the one Preferences dialog [P3] [subject:UX]
  - Details: fold remaining scattered/legacy settings dialogs (Project Info, Import/Export, Inference, Display) into the one Preferences dialog; keep the swappable source for the future user-profile settings layer. Re-filed 2026-09-09: the TODO-AUDIT Cluster 5 merge of the "Continue folding scattered settings" + "Unified Settings dialog" tasks was lost when the audit was applied — originals removed, merge never filed. Snap-dialog QSettings normalization tracked separately above. `main.py`, `preferences_dialog.py`.

## Gridline Revit-aligned UX re-architecture

- [ ] [type:feature] App-wide Y-up display sweep for property panels [P3] [subject:UX]
  - Details: property panels currently show raw Qt Y (down-positive) everywhere (sprinkler/node/etc.); gridline was flipped to up-positive for this branch. Sweep the app to a consistent up-positive display/parse convention. `sprinkler.py`, `node.py`, `property_manager.py`, ….
- [ ] [type:feature] Project angled gridlines into elevation views [P3] [subject:Architecture]
  - Details: currently only exactly-cardinal gridlines project into elevations; angled projection deferred (section-view territory). `elevation_scene.py`.
- [ ] [type:feature] Perpendicular bubble elbow/leader for gridlines [P3] [subject:CAD]
  - Details: jog a bubble off the line with a leader (Revit "add elbow"); per-view leader independence. `gridline.py`, `paper_space.py`.
- [ ] [type:feature] On-canvas rotate handle + Display-Manager linetype property for gridlines [P3] [subject:CAD]
  - Details: angle currently edited in the panel; linetype is fixed dash-dot. `gridline.py`, `model_space.py`, `display_manager.py`.
- [ ] [type:feature] Move / copy-paste polish: context-menu Move entry + multi-copy paste [P3] [subject:UX]
  - Details: user, 2026-08-14 smoke — add a right-click (entity + canvas) context-menu entry for Move (parity with Ctrl+M; matches the Array/Offset menu pattern); consider a copy/paste menu entry too. Also: paste currently exits after one placement — evaluate AutoCAD-style multi-copy (stay live until Esc) and richer ghost fidelity for non-gridline entities. Move-menu point superseded by the transform-tools unification below. `model_space.py`, `model_view.py`, `entity_context_menu.py`.
- [ ] [type:feature] Transform tools: single-key shortcuts + unified right-click across all geometry [P1] [subject:UX]
  - Details: user, 2026-08-20 smoke — a cohesive pass over Move/Array/Offset: (1) single-key shortcuts A=Array, O=Offset, M=Move; (2) add Move to the gridline right-click menu; (3) relabel the gridline entries — drop the "Gridlines" word, show the shortcut: `Array (A)`, `Offset (O)`, `Move (M)`; (4) expand these three right-click entries to all drawn geometry (line, rect, circle, polyline, arc, …), not just gridlines; (5) rewire the Transform ribbon group (`main.py` ~1690) onto the same unified actions. Grill first — two implementations to reconcile: the on-canvas gridline-specific replicate (`gridline_array`/`gridline_offset` via `GridlineItem.offset_copy`/`array_copies`) vs the general-geometry ribbon tools (`array_dialog.py`, `offset`/`offset_side` mode). "Expand to all geometry" means deciding which becomes the one tool (likely generalize the on-canvas replicate to any item exposing `translate`). `entity_context_menu.py`, `model_view.py`, `model_space.py`, `main.py`, `array_dialog.py`.
- [ ] [type:feature] Extend the inference engine to wall/pipe/sprinkler providers and consumers [P3] [subject:Architecture]
  - Details: the engine is generic but only gridlines provide references + only gridline placement/grip consume it; add wall/pipe/sprinkler providers + placement-tool + body-drag consumers, and the deferred guide types (wall-proximity, extension, equal-spacing) per `inferred-dimension-driven-placement.md`. `inference_engine.py`, `wall.py`, `pipe.py`, `model_space.py`.
- [ ] [type:maint] Extract + generalize the Dynamic Input engine into a reusable non-modal HUD (§4) [P2] [subject:Architecture]
  - Details: user, 2026-08-16 — `_DynInput` is a modal `QDialog` nested inside a `model_space.py` method, redefined/instantiated ad hoc per mode; extract to a reusable top-level controller/widget (`dynamic_input.py`), generalize to all placement modes (pipe/wall/arc/rectangle), and (design decision) move from Tab-triggered modal to a live non-modal HUD per §4.3/§4.5; coordinate with the inference engine at the Model_Space seam (typed value overrides snap/inference). Update `inferred-dimension-driven-placement.md §4` in place. `model_space.py`, new `dynamic_input.py`, `model_view.py`. ref: inferred-dimension-driven-placement §4. Lineage: `feat/dynamic-input-hud` D3 scope COMPLETE 2026-08-20 (plan/findings ledger gitignored); shipped one-HUD lifecycle (S1–S3), Line/Rectangle/Circle schemas, polyline, T16 (gridline offset/array), T15 (move + a `GridlineItem.translate` fix), T11 (cycling off Tab, since replaced by Space), T17/T21/T22 (spec §4 rewrite + SPEC-INDEX). HUD clients T18 (wall) 2026-08-24 + T19 (pipe) 2026-09-03 landed (see `todo_closed.md`). Known gap: offset_side/rotate/scale/fillet/chamfer lost their Tab exact-input — needs re-homing.

## Placement-UX overhaul

- [ ] [type:feature] Merge Line and Polyline into one ←/→ cycle tool [P2] [subject:UX]
  - Details: user, 2026-08-21 — host both under one `draw_line` mode with a line/polyline variant flag (per the `_PLACEMENT_VARIANTS` framework), branching the existing 2-click line vs N-click polyline handlers on it. Remove the placeholder `K` polyline shortcut (`Model_View._TOOL_SHORTCUTS` + Polyline tooltip) once this lands. `model_space.py`, `model_view.py`, `main.py`.
- [ ] [type:bug] `arc_span` ArcLength desyncs on undo [P3] [subject:UX]
  - Details: editing Span writes ArcLength via `set_value_mm` (no `valueChanged`), so the HUD undo stack never records ArcLength and a Ctrl+Z restores only Span, leaving the derived field stale. Low impact (ArcLength never reaches the applier). Re-run the coupling after an undo that touches a coupled field. `dynamic_input.py`.
- [ ] [type:bug] HUD-Tab ghost never refreshes for wall/floor/roof placement [P3] [subject:UX]
  - Details: user, 2026-09-05 wall-slice smoke — pre-existing, NOT a slice-10 regression (confirmed identical on `main`). While the Dynamic-Input HUD is engaged during wall placement, Tab-committing a field fires `fieldCommitted` → `_on_dynamic_input_field_committed` → `_preview_from_resolved(resolved)` → `_PREVIEW_DISPATCH.get("wall")` → None → no-op, so the on-canvas ghost sits frozen at its engage-time seed until the placement commits (the mouse ghost works — it routes via `_MOVE_DISPATCH`/real mouse events). Root cause: `_PREVIEW_DISPATCH` has no `wall`/`floor`/`roof` entries, and `_preview_from_resolved` calls `getattr(self,name)(resolved)` with ONE arg while the arch-placement move handlers take `(event, snapped)`. Fix = behavior addition (own grill/design): add a `_preview_from_wall(resolved)` adapter (line → 2nd point; rect-sizing → opposite corner; rect-rotate currently mis-routes to `_preview_rectangle_rotation` when `mode=="wall"` — needs a wall-rect rotate preview) + a `_PREVIEW_DISPATCH["wall"]` entry, then the floor/roof twins. Now that wall placement lives in `WallPlacementController`, the adapter has a clean home. `placement_input_coordinator.py`, `wall_placement_controller.py`, `model_space.py`. ref: inferred-dimension-driven-placement §4.
- [ ] [type:bug] Ctrl/Shift+arrow also cycles a placement variant [P3] [subject:UX]
  - Details: the ←/→ cycle keys in `keyPressEvent` don't check modifiers, so a modified arrow cycles at step 0. Gate on `NoModifier` if it conflicts with any future modified-arrow binding. `model_space.py`.
- [ ] [type:feature] 3-point / arbitrary-rotated rectangle as a distinct placement mode [P3] [subject:CAD]
  - Details: the current rotate step layers rotation on an axis-aligned 2-click rect; a true 3-point rotated rect (baseline + depth) is deferred.
- [ ] [type:feature] Persist the chosen placement variant across restarts [P3] [subject:UX]
  - Details: QSettings — variant choice is session-sticky only today.
- [ ] [type:feature] Arc-wall placement mode [P3] [subject:CAD]
  - Details: the downstream goal the arc revamp unblocks (arc as a wall centreline). `wall.py`, `model_space.py`.
- [ ] [type:bug] Retire the orphan `MainWindow.view` that breaks `views()[0]` consumers [P2] [subject:Architecture]
  - Details: `main.py:400` — a `Model_View` attached to the plan scene but never parented, never shown, never added to `central_tabs`, so it is `scene.views()[0]`. It broke the HUD in smoke test (built correctly inside an invisible widget tree). Worked around locally by selecting the first visible view, but ~12 other `views()[0]` uses in `model_space.py` have the same latent bug — dialog parents at ~2190/6438/8106 parent onto the orphan, and zoom-scale reads at ~3634/6783/7227/7749 read its transform. Retiring it (or never attaching it to the scene) fixes all of them at once. `main.py`, `model_space.py`.
- [ ] [type:maint] Qt fixtures must `show()` their view [P3] [subject:Testing]
  - Details: the dynamic-input fixtures built a `Model_View` without showing it, which made `views()[0]` trivially correct and hid the orphan-view bug class entirely. Fixed in the dynamic-input test files; audit the other Qt fixtures in the suite for the same gap. `tests/`.
- [ ] [type:maint] Split `node_start_pos` into typed pipe-start and move-start fields [P3] [subject:Architecture]
  - Details: it holds a `Node` in pipe mode and a `QPointF` in move/paste mode, and call sites now branch on `isinstance` to cope. Split into `_pipe_start_node` / `_move_start_point` (~30 call sites). Blocks clean work on T15. `model_space.py`.
- [ ] [type:maint] De-duplicate the `_other_end(pipe)` idiom [P3] [subject:Architecture]
  - Details: inlined 5× in `model_space.py` (~1391, 1458, 1488, 5826, 5853); `Node._other_end` is a sixth and the only one guarding the detached-pipe case. `model_space.py`, `node.py`.
- [ ] [type:maint] Add `PolylineItem.last_point()` [P3] [subject:Architecture]
  - Details: `model_space` reaches into `_points[-1]` directly at several sites. `construction_geometry.py`, `model_space.py`.
- [ ] [type:feature] Decide on decimal-comma input for dimension/angle fields [P3] [subject:UX]
  - Details: user call, 2026-08-19 — `parse_dimension`/`parse_angle` reject `1,5` as ambiguous against a thousands separator, and `1e3` as a likely typo. The comma is the natural numpad decimal key on European layouts, which matters now the numpad opens the HUD. Grammar's home is `units-and-formatting.md §3.1`. `scale_manager.py`.
- [ ] [type:maint] Narrow `reject_commit()` if it reads noisy [P3] [subject:UX]
  - Details: a refused commit flags every `DIMENSION` field, since appliers refuse on a magnitude and either extent may be at fault on rectangle. Nominate the culprit if that proves annoying in use. `dynamic_input.py`, `model_space.py`.
- [ ] [type:feature] Retire construction lines in favour of alignment guides [P3] [subject:Architecture]
  - Details: user, 2026-08-16 — `ConstructionLine` is an AutoCAD xline (`pt1`/`pt2` set direction only; `_recompute_line` extends past both so it reads infinite). The inference engine now covers the same job — alignment references without a persistent object — matching the Revit reference-plane model. Decide what, if anything, xlines do that inference guides + OSNAP don't, then deprecate the drawing tool. Wired into 11 modules; existing `.fpd` files hold `{"type": "construction_line"}` records so the load path needs a decision, not just deletions. ref: inferred-dimension-driven-placement.
- [ ] [type:feature] `DimensionEdit` arithmetic input [P3] [subject:UX]
  - Details: user, 2026-08-16 — accept basic expressions in any dimension field and auto-evaluate on commit (`3ft - 1.5ft` → `1' - 6"`, `12" * 2`, `10ft/3`). No arithmetic parsing exists anywhere in the codebase today — net-new. Mixed units must normalise through `parse_dimension` per-term before evaluating; unparseable/unsafe expressions fall through the existing revert-to-last-valid path (never `eval()`). Benefits all 11 `DimensionEdit` consumers + the Dynamic Input HUD. `dimension_edit.py`, `scale_manager.py`. ref: units-and-formatting.
- [ ] [type:maint] Migrate hand-rolled numeric inputs to `DimensionEdit` [P3] [subject:Architecture]
  - Details: 2026-08-16 reuse sweep — `array_dialog.py`, `calibrate_dialog.py`, `main.py` (~2302/2309) parse dimensions ad hoc instead of using the canonical widget; they miss the seed guard, revert-to-last-valid, and unit-system reformat. `array_dialog.py`, `calibrate_dialog.py`, `main.py`. ref: units-and-formatting.

## Underlay pen / undo follow-ups

- [ ] [type:maint] Consolidate the two underlay pen-rendering paths into a shared helper [P3] [subject:Code Quality]
  - Details: the import preview dialog (`dxf_preview_dialog.py`) strokes geometry with cosmetic width-0 pens, while the placed-underlay builder (`model_space.py:_build_batched_underlay_group`) now uses a cosmetic `UNDERLAY_LINE_WIDTH_PX` pen. Two independent pen-construction sites that must stay visually consistent; consider a shared pen/path-builder helper so they can't drift (the original thick-line bug existed in only one of them).
- [ ] [type:bug] Include underlays in the undo system [P2] [subject:CAD]
  - Details: `_capture_network` / `_restore_network` intentionally exclude underlays; importing an underlay is not undoable (underlay persists through undo/redo). Quick fix (push_undo_state after import) done 2026-04-24; full fix requires serializing underlays into undo snapshots and clearing/restoring them in `_restore_network`. `model_space.py:_capture_network`, `model_space.py:_restore_network`.

## Snapping Engine Roadmap (from `docs/specs/snapping-engine.md` §12)

- [ ] [type:feature] Fix ConstructionLine perpendicular / nearest / phase-4 participation [P3] [subject:CAD]
  - Details: deferred — ConstructionLine tool is not in active use; revisit if the feature sees real usage. Spec §5 note 2 corrected 2026-04-08. ref: snap-spec §5-row-ConstructionLine.
- [ ] [type:maint] F3 integration test on real keypress [P3] [subject:Testing]
  - Details: QTest.keyClick did not dispatch through QAction shortcut on headless Windows; investigate pytest-qt / qtbot or alternate dispatch.
- [ ] [type:design] Decide whether F3 / global OSNAP toggle should also disable `_snap_to_underlay` [P3] [subject:CAD]
  - Details: decide whether F3 / global OSNAP toggle should also disable `_snap_to_underlay` (DXF underlay snap), or document the separation in the snap spec.
- [ ] [type:design] Spec session: pipe-with-fitting named targets [P2] [subject:CAD]
  - Details: ref: snap-spec §8.3.
- [ ] [type:bug] Underlay intersection snapping bails in very dense regions [P3] [subject:CAD]
  - Details: phase-4 returns early once segment extraction exceeds `_PHASE4_MAX_SEGMENTS` (256) to bound O(n²) pairing, so a cursor over a dense DXF area gets no intersection snap at all. Consider: spatial pre-pairing / only pairing segments whose bbox is near the cursor, or raising the cap with a smarter pairing structure. `snap_engine.py:_check_geometry_intersections`. ref: snap-spec §6.1.

## View Relationships Follow-Ups (from `docs/specs/view-relationships.md` §11)

- [ ] [type:feature] Implement section view subsystem [P3] [subject:Architecture]
  - Details: SectionScene, SectionView, SectionMarker, SectionManager, section placement tool, cardinal shortcuts, elevation system retirement. See `docs/specs/section-view-subsystem.md`. DEFERRED 2026-06-23 grill — cardinal elevations already host on sheets (ViewResolver); arbitrary-angle sections not needed for the AHJ MVP. Spec stays a proposal. ref: section-view-spec.
- [ ] [type:design] Spec session: Drafting overrides / view templates [P2] [subject:Architecture]
  - Details: defines resolution rules on top of catalog. ref: view-relationships §7.4.
- [ ] [type:design] Spec session: Cross-view selection / interaction sync [P2] [subject:Architecture]
  - Details: ref: view-relationships §1.3.
- [ ] [type:design] Spec session: Paper-viewport-specific overrides [P3] [subject:Architecture]
  - Details: depends on view-templates spec landing first. ref: view-relationships §7.4.

## Additional Spec Sessions

- [ ] [type:design] Spec session: Elevation view selection mode [P2] [subject:Architecture]
  - Details: selection/interaction model for elevation scenes. Depends on plan-view selection mode spec for shared conventions. `elevation_scene.py`.
- [ ] [type:design] Spec session: 3D view selection mode [P2] [subject:Architecture]
  - Details: selection/interaction model for 3D viewport (pick ray, actor selection, highlight). Depends on plan-view selection mode spec for shared conventions. `view_3d.py`.
- [ ] [type:design] Spec session: Roof elements [P2] [subject:Architecture]
  - Details: 4 roof types (flat/gable/hip/shed), ridge/hip line computation, pitch-to-peak-height formula, overhang offset algorithm (perpendicular-edge intersection with degenerate fallback), "auto" ridge direction heuristic (longest-edge midpoints), 3D mesh generation (pitched roofs incomplete today). `roof.py`.
- [ ] [type:design] Spec session: Door & window elements [P2] [subject:Architecture]
  - Details: wall-relative positioning (`offset_along` centerline), width-to-scene conversion chain (3-level fallback), swing arc geometry (doors), crossing-diagonal symbol (windows), hit-test scaling by zoom, preset libraries (doors 820-1800×2040mm, windows 600×1800mm), sill height. `wall_opening.py`.
- [ ] [type:design] Spec session: Floor openings & stairs [P2] [subject:Architecture]
  - Details: openings, stair geometry, multi-level connectivity, sprinkler coverage implications. No implementation exists today; this is a greenfield design spec.

## Code Review Audit — Spec Gaps (from 2026-04-09 audit)

> Grid system, scale calibration & underlay, wall/room/floor system, sprinkler components, hydraulic solver — see the subsystem sections above.

- [ ] [type:design] Spec session: elevation scene projection & rendering [P2] [subject:Architecture]
  - Details: cardinal-axis coordinate mapping (N/S/E/W → H,V plane), world Z → vertical axis, entity projection rules, Z-range filtering & view-depth semantics, gridline/datum placement, rebuild triggers, `_ROLE_SOURCE` sync-back to 2D. `elevation_scene.py`.
- [ ] [type:design] Spec session: detail view markers & crop geometry [P2] [subject:Architecture]
  - Details: rounded-rect crop box (fillet radius = 1.5× gridline bubble), bubble placement algorithm (leader line, "below center" default), dragging vs resizing interaction model, per-detail view-range override (None = inherit from parent plan), bubble radius = 3× gridline bubble. `detail_view.py`.
- [ ] [type:design] Spec session: 3D view rendering pipeline [P2] [subject:Architecture]
  - Details: PyVista/VTK mesh generation from entity geometry, 200-pipe cylinder threshold (fallback to lines), pick ray casting (15px tolerance), actor-to-entity bidirectional mapping lifecycle, dirty-flag lazy rebuild, radiation heatmap overlay, roof 3D mesh gap (flat only, no pitch), plotter/VTK GL-context lifecycle (`View3D.cleanup()` finalizes the `QtInteractor` on close — mandatory or contexts leak and crash multi-window/test scenarios; added 2026-06-22). `view_3d.py`.
- [ ] [type:design] Spec session: view markers & shared crop box [P2] [subject:Architecture]
  - Details: tangent-line circle geometry (R/sin(40°) point distance), four-marker cardinal positioning at crop-box edges, single shared crop box (not per-marker), 8-handle grip system, double-click → elevation view activation. `view_marker.py`.
- [ ] [type:design] Spec session: layer management system [P2] [subject:Architecture]
  - Details: DXF layer extraction (group data(2) field), QGraphicsItem data(1) layer-name matching, UserLayer lineweight mapping (5 named values, mm → cosmetic px best-fit), active-layer tracking, default layers (Default/Underlay/Annotations/Gridlines), per-item layer assignment protocol. `layer_manager.py`, `user_layer_manager.py`.
- [ ] [type:design] Spec session: property manager & type system [P2] [subject:Architecture]
  - Details: property type dispatch (label/string/enum/combo/color/level_ref/layer_ref/button/dimension), multi-select conflict resolution (blank when values differ), debounced refresh (50ms QTimer), lazy SprinklerDatabase loading, numeric field auto-validation. `property_manager.py`.
- [ ] [type:design] Spec session: display system override resolution [P2] [subject:Architecture]
  - Details: formalize the three-tier cascade contract (per-instance > project > QSettings > factory default), scope of per-instance vs per-category applicability, SVG recolouring cache invalidation, interaction with future view templates (ref: view-relationships §7.4). Deepens existing `docs/architecture/display-system.md`. `display_manager.py`.
- [ ] [type:design] Spec session: scene tools (geometry editing) [P2] [subject:Architecture]
  - Details: 16 tools in `SceneToolsMixin` — offset (line intersection, polyline offset), array (linear/polar, 200-copy preview cap), rotate/scale/mirror (anchor point transforms), join/explode (merge segments, decompose groups), break/break-at-point (segment splitting), fillet/chamfer, stretch (crossing-window selection), trim/extend (to intersections), merge/hatch (polygon merging, fill patterns), constraints (creation and solving). Per-tool workflow, algorithm, edge cases, and mode state machine integration. `scene_tools.py`.
- [ ] [type:design] Spec session: auto-populate sprinkler placement algorithm [P3] [subject:Architecture]
  - Details: NFPA 13 density/area curve interpolation, polygon decomposition into rectangles (scanline), branch-line direction detection (1/2/3+ pipe logic), `_walk_branch()` algorithm, wall-proximity 2× rule, edge cases (L-shaped rooms, concave rooms, dead-end branches, multiple design areas). `auto_populate_dialog.py`, `design_area.py`.
- [ ] [type:design] Spec session: parametric constraint system [P2] [subject:Architecture]
  - Details: extend foundation spec (`docs/specs/parametric-constraint-system.md`) with resolution order design, over-constrained detection, constraint visualization, editing UI, dependency graph, and new constraint types (H/V lock, equal spacing, tangent, parallel, perpendicular, fix/pin). Foundation spec covers existing 3 types + solver + serialization + lifecycle. `constraints.py`.
- [ ] [type:design] Spec session: annotations & hatch patterns [P3] [subject:Architecture]
  - Details: NoteAnnotation (MText-like word-wrap, bold/italic, alignment), DimensionAnnotation (two-point + offset witness lines), HatchItem (region fill with constraint interaction), SVG hatch pattern loader (24×24 viewBox tiling, seamless rules), built-in Qt brush patterns. `annotations.py`, `hatch_patterns.py`.

## Hydraulic Solver Follow-Ups (from `docs/specs/hydraulic-solver-and-reporting.md` §12)

- [ ] [type:bug] Block hydraulic calculation when scale uncalibrated [P2] [subject:Hydraulic Calculator]
  - Details: REVISIT — `is_calibrated` only applies to underlay scaling; scene is always 1 px = 1 mm so pipes drawn directly have correct lengths. Guard would block valid calculations on projects without underlays. Need to rethink when/if this is needed. `hydraulic_solver.py`. ref: hydraulic-spec §7.3, D8.
- [ ] [type:feature] Hydraulic-results view (separate view + hf heatmap) [P2] [subject:Hydraulic Calculator]
  - Details: create a dedicated results view (not a plan-view colour override) so it displays independently in paper space; colour pipes by friction loss normalized to system max (green/orange/red hf heatmap) instead of the current velocity colouring. `hydraulic_solver.py`, `model_space.py`, `hydraulic_report.py`. ref: hydraulic-spec §11.2, D4; project-hydraulic-results-view.
- [ ] [type:feature] Sprinkler legend/schedule as paper-space sheet content [P3] [subject:Architecture]
  - Details: the report's Sprinkler Schedule tab was removed (3-tab consolidation); an AHJ package wants the sprinkler legend on the drawing, not in the calc report. `paper_space.py`.
- [ ] [type:feature] Pipe material takeoff (BOM/estimating) [P3] [subject:Sprinkler Design]
  - Details: the report's Pipe Schedule tab was removed (3-tab consolidation); takeoff belongs in a future BOM/estimating feature.
- [ ] [type:bug] Node Summary Table numeric column sorting [P3] [subject:Hydraulic Calculator]
  - Details: header-click sorting is lexicographic ("10" < "2"; numeric columns sort as strings). Default BFS order is correct; fix via `Qt.ItemDataRole.EditRole` numeric data or disable sorting. `hydraulic_report.py`.
- [ ] [type:bug] Report exports re-read the live scene at export time while the embedded graph uses populate-time state [P3] [subject:Hydraulic Calculator]
  - Details: editing the water supply between Run and Export yields a PDF whose Water Supply section, graph, and stored result disagree. Consider snapshot-at-populate for AHJ documents. `hydraulic_report.py`.
- [ ] [type:feature] Multi-system hydraulic export — per-system sections in combined PDF [P3] [subject:Hydraulic Calculator]
  - Details: depends on sprinkler spec D8. `hydraulic_report.py`. ref: hydraulic-spec §9.4, D9.
- [ ] [type:feature] Professional PDF templates [P3] [subject:Hydraulic Calculator]
  - Details: company logo, engineer stamp area, page numbers. `hydraulic_report.py`. ref: hydraulic-spec §9.4, D10.

## Sprinkler System Components Follow-Ups (from `docs/specs/sprinkler-system-components.md` §14)

- [ ] [type:maint] Retire the git-tracked repo `sprinklers.json` [P3] [subject:Code Quality]
  - Details: now that runtime reads/writes `%APPDATA%`, the tracked seed file only feeds the one-time migration and dirties dev checkouts no more; `git rm` + `.gitignore` once migration has shipped a while. `sprinklers.json`, `.gitignore`.
- [ ] [type:maint] Shared `_app_data_dir()` helper [P3] [subject:Code Quality]
  - Details: `sprinkler_db._default_db_path()` and `titleblock_template._library_dir()` duplicate the `%APPDATA% or ~` + `FirePro3D` resolution; extract one helper both call. `sprinkler_db.py`, `titleblock_template.py`.
- [ ] [type:feature] SVG symbol system expansion [P3] [subject:Sprinkler Design]
  - Details: asymmetric sidewall symbol, orientation-driven selection, wall auto-detection, tab-cycle orientation, in-app symbol editor. `sprinkler.py`. ref: sprinkler-spec §8.1, D7.
- [ ] [type:feature] Multi-system SprinklerSystem [P3] [subject:Architecture]
  - Details: per-node/pipe system assignment, multiple instances, independent supply nodes, per-system hydraulic calculations. Separate spec recommended. `sprinkler_system.py`, `model_space.py`. ref: sprinkler-spec §9, D8.

## Wall, Room & Floor Slab Follow-Ups (from `docs/specs/wall-room-floor-system.md` §13–§14)

- [ ] [type:bug] Legacy face-snapped tee endpoints never form room-detection T-nodes [P3] [subject:CAD]
  - Details: `_detect_room_boundary` only tees endpoints within `TOL*3` (6mm) of the host centerline; pre-2026-07-13 files have tee endpoints on the face (~half-thickness away), so their tees never split walls in the room graph (pre-existing, surfaced by the tee-join rework). New walls are fine (centerline snap). Consider a load-time migration (re-snap face-parked tee endpoints to the centerline) or widening the detection band. `model_space.py:_detect_room_boundary`.
- [ ] [type:maint] Extend the 3-wall full-miter pie join to N-way junctions [P3] [subject:CAD]
  - Details: 4+-way crossings currently keep Butt (near-always orthogonal, looks fine); the angular-neighbour miter + junction-polygon vertices generalize if diagonal 4-ways show up in practice. `wall.py:_pie_miter_corners`.

## Underlay Workflow Follow-Ups (from `docs/specs/underlay-workflow.md` §15)

> Existing test-gap tasks (hydraulic solver, auto-populate, geometry utilities) already in sections above.

- [ ] [type:maint] Audit the ENTIRE codebase for non-tokenised chrome [P1] [subject:UX]
  - Details: the build migrated the 9 audited chrome hard-coders and added an anti-drift hex-guard, but the guard is scoped to that allowlist only. Sweep all of `firepro3d/` for chrome text and colours that bypass the `theme.py` two-layer tokens: raw hex / named colours (`grey`, `#...`, `rgb(...)`) in `setStyleSheet`, `QColor(...)`/`QPen`/`QBrush`/`QPalette` used for chrome (NOT canvas/geometry entities, which are Display-Manager-owned), and hard-coded `font-size`/`font-family`/point-size literals. Classify chrome (in scope) vs canvas content (out); tokenise the chrome; then extend `tests/test_theme_chrome_hexguard.py` to the full chrome file set so drift stays caught app-wide. Progress 2026-09-06: the UI Design-System task added the house dialog base + kit + 5 migrated dialogs to the hexguard allowlist (7 files) and forged a `test_metrics_drift_guard.py`; the full-app sweep of the remaining chrome modules is still open. `theme.py`, all chrome modules, `tests/test_theme_chrome_hexguard.py`. ref: theming.md.
- [ ] [type:feature] Label-rotate: NoteAnnotation + DimensionAnnotation [P2] [subject:UX]
  - Details: "all labels should be rotatable" (2026-08-31 grill). They're translate-only today, so a mixed selection including a note/dimension hides the group rotate knob. Give each a baked `manip_rotate` + `{"translate","rotate"}` capability (notes rotate the text glyph; dimensions rotate the two endpoints), routed through their serialize paths. `annotations.py`. Lineage: Adopt the `SelectionBox` manipulator app-wide → U1.
- [ ] [type:bug] RectangleItem group-rotate external-pivot reconciliation [P3] [subject:CAD]
  - Details: `RectangleItem.manip_rotate` stores the group's external scene pivot as `_pivot` (baked-at-rest); the footprint renders correctly rotated, but `rect()` (axis-aligned storage) no longer matches the visual centroid, so a subsequent resize can jump. Pre-existing RectangleItem design, exposed now that a rect can ride a mixed group rotate. Reconcile `rect()`/`_pivot` after a group rotate (or re-derive the pivot to the rect centre on the next resize). `construction_geometry.py`.
- [ ] [type:maint] Reuse cleanup: `rotated_rect_corners` via `CAD_Math.rotate_point` [P3] [subject:Code Quality]
  - Details: the standalone helper duplicates the Y-up→Qt rotation math the primitive now provides; collapse to one home (skipped in U1 to minimise change surface; verify `test_rectangle_bake.py` stays green). `construction_geometry.py`.
- [ ] [type:bug] Ctrl-resize jumps on release (from-centre anchor mismatch) [P3] [subject:CAD]
  - Details: PRE-EXISTING on `main` (U2 smoke 2026-09-08). During a Ctrl/from-centre resize the preview anchors about the frame centre (`resize_delta(from_center=True)` → anchor = `rect.center()`), but `_bake_scale` unconditionally bakes about the opposite corner (`_rect_point(r0, 1-u, 1-v)`); its docstring wrongly claims from-centre is "captured in factors". So the rect jumps ~the handle displacement on release. Fix: thread a from-centre flag into `_bake_scale` (anchor = `r0.center()` when Ctrl was used). Add a posted Ctrl-resize test asserting the bake anchor == centre. `selection_manipulator.py`.
- [ ] [type:maint] Rotated rect shows legacy green grips (no resize handles) [P3] [subject:UX]
  - Details: BY DESIGN today (U2 smoke) — `RectangleItem.manip_capabilities` drops `"scale"` when `_angle != 0` (box-resize shears a rotated rect) → `provides_handles_for`→False → legacy `drawForeground` grips render. Cosmetically collapses into U4 (one handle system); true rotated-rect resize is the separate item (see the RectangleItem group-rotate external-pivot reconciliation follow-up). Cross-ref U4. `construction_geometry.py`, `selection_manipulator.py`.
- [ ] [type:design] Shift-before-click starts a rubber-band instead of a Shift-constrained frame gesture [P3] [subject:UX]
  - Details: PRE-EXISTING (U2 smoke). Shift+press on the manipulator frame triggers the scene's additive-select rubber-band (`model_space`/`model_view` press routing, untouched by U2) rather than a Shift-ortho move / Shift-aspect resize. Decide UX: should a Shift+press landing on the frame/handle begin the constrained gesture (Shift applied at release)? `model_space.py`, `model_view.py`, `selection_manipulator.py`.
- [ ] [type:feature] Optional dedicated centre move-handle [P3] [subject:UX]
  - Details: move is interior-drag today (grab anywhere in the frame), no visible centre handle by design; add one for discoverability if wanted. `selection_manipulator.py`.
- [ ] [type:maint] U3 — migrate items onto `manip_handles`, one per PR [P1] [subject:Architecture]
  - Details: framework + CircleItem LANDED 2026-09-08 on `feat/u3-griphandle-circleitem`: live-apply `GripHandle` (`manip_handle.py`) calling each item's `apply_grip`; the `_begin_handle`/`_begin`/`hit_test`-pool/`_reflow_live` manipulator fixes; the `_item_uses_manip_handles` coexistence gate (drawForeground + `_find_grip_hit` skip migrated items); snap-parity via the scene's `get_effective_position` flag-borrow; four per-item semantics admitted as extension points. **PolylineItem + shared `default_grip_handles()` helper LANDED 2026-09-09 on `feat/u3-griphandle-polyline`** (helper is the common body of every `manip_handles()`; CircleItem refactored onto it; Polyline = round vertex grips, no special semantics). **SplineItem LANDED 2026-09-09 on `feat/u3-griphandle-spline`** (round control-point grips, same shape as Polyline, no special semantics). **LineItem LANDED 2026-09-09 on `feat/u3-griphandle-line`** (first with per-item semantics: endpoints round + Ctrl-angle-constrained vs the opposite endpoint via a reusable `EndpointGripHandle(GripHandle)._transform_point`→scene `_constrain_angle`; midpoint round (a move grip — translates the whole line; changed square→round 2026-09-10 per user). Also fixed a framework bug the migration surfaced: `GripHandle.on_cancel` restored EVERY grip, corrupting index-dependent grips like the line midpoint → now restores only the dragged grip. `test_scene_tools` generic `_find_grip_hit` tests moved to a migration-agnostic `_GripStub`). **ArcItem LANDED 2026-09-10 on `feat/u3-griphandle-arc`** (zero special semantics — the legacy grip path explicitly excludes arc from Ctrl-constrain; `default_grip_handles(self, circular={0,1,2})`, all-round grips: centre = move, start/end = geometric endpoints; same shape as Spline/Polyline). **RegularPolygonItem LANDED 2026-09-10 on `feat/u3-griphandle-polygon`** (zero special semantics — legacy grip path excludes polygon from Ctrl-constrain; `default_grip_handles(self, circular=all indices)`, all-round grips: centre = move, N vertices = defining points [vertex drag resizes + rotates via `apply_grip`], handle count tracks `_sides`; same shape as Arc). **EllipseItem LANDED 2026-09-10 on `feat/u3-griphandle-ellipse`** (mirrors CircleItem — an ellipse is a generalized circle: `default_grip_handles(self, circular={0})`, centre round move grip + 4 axis-endpoint sizing grips square [major rx=1,2 also rotates; minor ry=3,4], the square grips rotated to the ellipse orientation via a new opt-in `grip_render_angle(index)` GripHandle hook so they stay radially aligned at placement angle + after rotate, and LIVE during the rotate-knob held-preview via `SelectionManipulator._preview_rotation_deg()` [2026-09-10 smoke follow-ups]; zero special semantics, not box-native). Grip-shape house rule (2026-09-09 smoke; refined 2026-09-10): vertex/endpoint + centre/move grips render round (disc); only inert/derived convenience grips stay square — a midpoint that MOVES the whole item is a move grip → round (LineItem midpoint). Function, not position. Each item passes its round indices via `default_grip_handles(circular=…)`. As-built in `docs/specs/selection-manipulator.md §"U3 — GripHandle"`. Each remaining item exposes its parametric points as `GripHandle`s whose drag calls its existing `apply_grip`, carrying the per-item drag semantics that live in `model_space` today: Ctrl angle-constrain (wall/gridline endpoints — reuse `EndpointGripHandle`, opp 1↔0) via `_transform_point`; gridline multi-select parallel-delta + wall-endpoint propagation via `_after_apply`; the constraint-solver pass (always run). Parity-test each item (posted-event drag == legacy grip drag). **Rectangle is NOT a parametric migration (investigated 2026-09-09): it is box-native** — `manip_capabilities()` includes `"scale"` (unrotated), so `provides_handles_for` already routes a single rect to the manipulator's rigid RESIZE handles and both legacy paths skip it; giving it a plain `manip_handles()` would double up (8 resize + 9 grips). Its handle set IS the rigid resize set via `_active_handles()`'s fallback. **Scheduled into U3 before Wall (user 2026-09-10)** as a box-native SPECIAL migration (not a plain `default_grip_handles` case): reconcile `provides_handles_for`'s box-native skip with the `_item_uses_manip_handles` gate so the rect gets ONE handle set (the rigid resize handles), not resize + parametric grips; the rotated-rect case (caps drop `"scale"` → legacy green grips) is the separate "Rotated rect shows legacy green grips" todo. Remaining (simplest-first, one PR each): **Rectangle** (box-native special, above) · Wall (+propagation) · Gridline (+parallel-delta) · Room · DesignArea · Note/Dimension · Floor · Roof · elevation/detail/view-marker items. Follow-up nit: `_item_uses_manip_handles` treats an empty `manip_handles()` as "not migrated" (unreachable for CircleItem; handle when a state-dependent-hittability item lands). per-item modules, `model_space.py`. ref: selection-manipulator §Unification.
- [ ] [type:maint] U4 — retire the parallel systems [P1] [subject:Architecture]
  - Details: once every item provides `manip_handles`, delete the `drawForeground` grip loop, `scene_tools._find_grip_hit`, and the `provides_handles_for` arbitration predicate. One render path, one hit-test, one undo funnel; the "two systems fighting" bug class becomes impossible. `model_view.py`, `scene_tools.py`, `selection_manipulator.py`, `model_space.py`. ref: selection-manipulator §Unification.
- [ ] [type:maint] U5 — fold in selection-mode + other scenes [P1] [subject:Architecture]
  - Details: integrate hover pre-highlight / Tab-cycle / rubber-band (`selection-mode.md`) against the unified handles; add `manip_handles` providers for the elevation and 3D scenes (their own selection specs). `model_space.py`, `elevation_scene.py`, `view_3d.py`. ref: selection-manipulator §Unification, selection-mode.
- [ ] [type:maint] Level-chip tint parity (holistic-review note) [P3] [subject:UX]
  - Details: delegate level chips derive `chip`→`raised (#24282D)` / `chip_ink`→`muted (#98A1AA)`, slightly darker/dimmer than the old bespoke `#2C3137`/`#B7BFC7`. Legible, accepted at smoke; promote `chip`/`chip_ink` to their own primitives if exact parity is wanted. `theme.py`, `underlay_manager_delegates.py`.
- [ ] [type:feature] Latched `detect()` in construction-time consumers [P3] [subject:UX]
  - Details: migrated dialogs + the 3D toolbar call `detect()` in `__init__`, so a runtime Preferences→UI theme switch doesn't restyle already-open ones (they update on reopen). If live full-app theme switching is wanted, have `MainWindow._apply_theme` re-run each open consumer's styling (or repaint registry). Pre-existing pattern, not a regression. 2026-09-06: `HouseDialog.restyle()` seam now exists — so wiring the open-dialog restyle is the remaining work. `main.py`, chrome modules.
- [ ] [type:maint] `roof_dialog._img_label` light-on-dark border (nit) [P3] [subject:UX]
  - Details: the schematic-preview frame keeps a `# theme-exempt` fixed dark `#1e1e1e` backdrop but a token `border_subtle` border; under LIGHT that's a light border on a dark box. Cosmetic; tokenise or fully-exempt if it bothers. `roof_dialog.py`.
- [ ] [type:feature] View-owned per-view underlay visibility [P2] [subject:Architecture]
  - Details: re-home the removed `hidden_in_views` capability onto the view (PlanView/DetailView/`SheetViewport` stores which underlays IT hides); requirement of the drafting-overrides / view-templates spec (ref: view-relationships §7.4). Restores per-viewport underlay hiding (regressed in the interim).
- [ ] [type:feature] Underlay contextual ribbon tab [P3] [subject:UX]
  - Details: Scale/Rotate/Lock/Refresh/Remove on underlay selection (rides the contextual-tab-population work); canvas context menu is the interim home. `main.py`, `ribbon_bar.py`.
- [ ] [type:feature] Optional details-panel dimmer [P3] [subject:UX]
  - Details: opacity was fully retired; if colour-only dimming proves insufficient for tracing, re-add an opacity slider in the manager details panel (the `Underlay.opacity` field still exists). `underlay_manager.py`.
- [ ] [type:maint] Underlay Manager post-build cleanups [P3] [subject:Code Quality]
  - Details: vestigial `source_view_key` param on `paper_display.apply_paper_overrides` (only the deleted underlay-suppression stage used it; remove + update `paper_export`/`paper_space` callers); `_menu_pos` None-guard in `underlay_manager_delegates.py`.
- [ ] [type:maint] Preserve source DXF colours option [P3] [subject:CAD]
  - Details: re-deferred in the 2026-08-09 display-management design (needs (layer, colour) re-batching; per-layer overrides landed instead). ref: underlay-spec §2.2, §16-D5.
- [ ] [type:feature] Undoable underlay operations [P3] [subject:CAD]
  - Details: ref: underlay-spec §2.2.
- [ ] [type:bug] Fix the two latent exceptions behind the former silent crashes [P2] [subject:CAD]
  - Details: now survivable + logged, still bugs — (a) a scene item's Python `boundingRect` raises during `_q_processDirtyItems` (dump sig: `boundingRect` + 2× `itemChange`); (b) pyvistaqt `timerEvent` raises during 3D rebuild (numpy `logical_and` frame nearby). Watch `%LOCALAPPDATA%\FirePro3D\error.log` after real sessions — the traceback pinpoints the raiser; fix surgically then.
- [ ] [type:maint] Remove dead `layer_manager.py` [P3] [subject:Code Quality]
  - Details: `LayerManager` is never instantiated (docstring-only usage); if ever wired up, its `refresh()→_apply_all()` would fight `Underlay.hidden_layers` (defaults every layer to visible). Delete the module or reconcile with the browser-tree layer visibility path. `layer_manager.py`.
- [ ] [type:maint] Route `main.py` `sceneModified.connect(model_browser.refresh)` through `schedule_refresh` [P3] [subject:Architecture]
  - Details: the direct connection rebuilds the whole tree synchronously on every scene change (duplicate work: `set_scene` also connects `sceneModified→schedule_refresh`), and a synchronous rebuild mid-`itemChanged` emission `clear()`s the tree item Qt is still processing (re-entrancy landmine; didn't crash in repros but is fragile). `main.py`, `model_browser.py`.
- [ ] [type:feature] Ability to select/access individual items within an underlay group [P3] [subject:CAD]
  - Details: future feature to interact with sub-items of an imported underlay.

## Code Health & Architectural Debt (from 2026-04-29 gap analysis)

- [ ] [type:maint] Model_Space decomposition — continue the domain-controller slices [P1] [subject:Architecture]
  - Details: current size ~7,829 lines; next slice = room (reads scene-side `_walls`), then floor/roof/gridline. Governing spec `docs/specs/model-space-architecture.md`. Grilled contract: pure core out / side-effect shell stays; four binding seams (universal scene-graph mutation, undo-snapshot glue, dual-serialization unified to one `NetworkCodec`, ordered idempotent `set_mode`→`clear()` teardown); extracting a concern converts `main`/`view` bare-attr reach-ins into public scene methods same-commit. Slices 1–11 landed (tool-geometry+constraint-solver, SceneTools composition, NetworkCodec unify, underlay controller, pipe/node controller, sprinkler-workflow controller, placement-input coordinator, 2D-geometry drawing, arc+polygon, wall-placement, feature-placement) — see todo_closed.md. `main.py` (MainWindow, #2 monolith) is a sibling task with its own spec (below). Why it matters: the single biggest bug surface in the codebase (two context menus, two view paths, focus loss, z-order, ALIGN scope/first-point/angled-extension bugs). `model_space.py`, `scene_tools.py`, `scene_io.py`, `tool_geometry.py`, `constraints.py`. ref: model-space-architecture.
- [ ] [type:maint] Retire redundant per-test QSettings isolation now that the autouse fixture exists (#312 follow-up) [P3] [subject:Testing]
  - Details: filed 2026-09-09. The autouse `_isolate_qsettings` + class-level `_IsolatedQSettings` (conftest.py) supersedes the ad-hoc monkeypatch fixtures (`isolated_settings`, `patched_qsettings`, the `test_data_folder_setting` redirect) and the manual save/restore try/finally blocks in `test_preferences_dialog.py` / `test_crosshair_cursor.py` / `test_import_prefs_wiring.py` / `test_fullscreen_immersive.py` / `test_theme_tokens.py` / `test_gridline_paper_scale.py`. They still work (explicit-INI/monkeypatch takes precedence) — remove opportunistically to cut churn. `tests/`.
- [ ] [type:maint] `underlay-workflow.md` broader levels-drift sweep [P3] [subject:Documentation]
  - Details: §10.7 was reconciled 2026-09-08 (`levels` is dialog-authored placement, overwritten on Modify), but §7.3/§16.6 (≈ lines 151/315/373/959/975) still describe levels as managed "exclusively from the Underlay Manager" with the "import dialog Level combo removed" — the pre-Rev-8 narrative, contradicted by §10.1 "Levels re-added". Sweep the whole spec to the Rev-8 dialog-authored-levels model. `docs/specs/underlay-workflow.md`.
- [ ] [type:maint] Underlay slice — post-landing cleanups [P3] [subject:Code Quality]
  - Details: filed 2026-09-02 — (a) `underlay_controller.py` imports `underlay_layer_pen`/`_pdf_width_to_px`/`_record_levels` lazily inside methods from `model_space` to dodge the model_space↔controller import cycle — promote those pure helpers to a shared module so the controller can import them at top-level; (b) DWG-cleanup test gap — no test exercises the DWG `load_from_file` temp-file-cleanup path (the seam bug where `scene_io` wrote `_dwg_cleanup_path` onto a deleted bridge property was caught by review, not tests); add a DWG-underlay load test; (c) the subagents' targeted underlay test set missed `test_append_geom_to_path.py`/`test_pdf_text_render.py`/`test_import_dialog_preview.py` — they call `Model_Space._append_geom_to_path` statically; add those files to any future underlay-touching targeted set. `underlay_controller.py`, `tests/`. ref: model-space-architecture §5.
- [ ] [type:maint] Undo-perf bench: pipe restore via `add_pipe` [P3] [subject:Architecture]
  - Details: 4b routes `_restore_network` pipes through `add_pipe` (update_geometry + per-pipe fitting DM colours + coalesced viewport update); pipe-connected nodes get fitting colours applied twice (idempotent). `load_from_file` already bears this per-pipe cost on open, so not a new cost class — bench a large-network undo before optimizing (`feedback_perf_theory_needs_minimal_bench`); if it lags, add a bulk-restore path. `model_space.py`, `network_codec.py`.
- [ ] [type:maint] Tier-2 deserialize loop boilerplate [P3] [subject:Code Quality]
  - Details: the `for entry: X.from_dict(); addItem; list.append` loops for walls/rooms/floors/roofs/gridlines/construction-geo are duplicated across `load_from_file`+`_restore_network` (per-entity logic already single-homed in each `from_dict`). Low value / higher churn; fold in only if it stops paying rent. `scene_io.py`, `model_space.py`.
- [ ] [type:bug] Tier-3 paste-path (`paste_items`) unify + copy-but-no-paste bug [P3] [subject:CAD]
  - Details: `wall`/`room`/`floor_slab`/`roof` are captured by copy but silently dropped on paste (no branch); `block_item` pastes but isn't tracked in any list (orphaned from undo); gridline paste keys on a fragile structural heuristic (§4). Separate deserialize consumer + bug class → own slice. `model_space.py` (`paste_items`). ref: model-space-architecture §4.
- [ ] [type:bug] `Room.z_range_mm()` reads retired floor `.level` [P3] [subject:CAD]
  - Details: new two-boundary slabs don't reliably write `.level`, so ceiling-height can degrade. Not a deserialize-path issue; separate fix. `room.py`. ref: model-space-architecture §4.
- [ ] [type:bug] Pre-existing sprinkler round-trip instability (found during 4a) [P3] [subject:Sprinkler Design]
  - Details: a node's `sprinkler.get_properties()` derived rows (K-Factor/Coverage/Model options) are not byte-stable across save→load→save; unrelated to the codec. `sprinkler.py`.
- [ ] [type:maint] `main.py` (MainWindow) decomposition — sibling task, own spec [P2] [subject:Architecture]
  - Details: #2 monolith (~4,070 lines). Honor the cross-boundary dependency ledger (`model-space-architecture.md §5.1`): clean the bare-attr reach-ins (`_on_escape` → `scene.node_start_pos`/`_pipe_node_was_new`) into public scene methods as the pipe concern extracts. `main.py`.
- [ ] [type:maint] Drop the SceneTools thin wrappers once Slice B lands [P3] [subject:Code Quality]
  - Details: the `_offset_*`/`_compute_*`/`_get_item_segments`/`_point_to_segment_dist`/`extract_edges` wrappers delegate to `tool_geometry`; when callers move onto the composed `SceneTools`, retire the wrappers and point callers at `tool_geometry.*` directly. `scene_tools.py`, `model_space.py`.
- [ ] [type:maint] PEP 8 class naming [P3] [subject:Code Quality]
  - Details: `Model_Space`, `Model_View`, `CAD_Math` use underscores; should be `ModelSpace`, `ModelView`, `CADMath`. Requires renaming classes + updating all imports and string references. Low priority due to churn.

## Import

> PDF Import Polish cluster (2026-08-28, `feat/pdf-import-polish`) SHIPPED + smoke-tested. Governing specs: `underlay-workflow.md` (import) · `snapping-engine.md` · `icon-style-guide.md`. Remaining DWG/multi-layout items below.

- [ ] [type:feature] DWG import: paper-space viewport compositing [P2] [subject:CAD]
  - Details: Revit DWGs place building geometry and gridline/dimension annotations at separate model-space coordinates, composited via paper-space viewports. Current import shows raw model space where they're physically separated. Need to read viewport clip boundaries + transforms and remap block coordinates to overlay annotations with building geometry. `dxf_preview_dialog.py`, `dwg_converter.py`.
- [ ] [type:maint] Multi-layout import extraction is O(all model space) per layout switch [P2] [subject:CAD]
  - Details: selecting any layout re-walks all ~49,628 model-space entities and explodes every INSERT/HATCH/DIMENSION regardless of viewport (`_entity_in_viewport` returns True for them), producing ~388k explosion geoms filtered down to ~7.5k for a single sheet. Two improvements: (A) extract model space once, filter per layout — cache the unfiltered geoms and apply only the cheap viewport-bounds filter on each layout switch instead of re-extracting; (B) bbox-prefilter blocks — test INSERT/HATCH/DIMENSION extents via `ezdxf.bbox.extents([ent], fast=True)` (generous margin) and skip exploding those outside the viewport. B is the dominant per-layout win and is localized; A helps multi-layout switching. `dxf_import_worker.py:_entity_in_viewport`, `dxf_preview_dialog.py:_DialogExtractWorker._run_inner`, `dwg_converter.py`.

## Paper Space Follow-Ups (from 2026-05-11 implementation)

## Title block template editor

- [ ] [type:feature] Font-properties widget dialog for title block cell text styling [P3] [subject:UX]
  - Details: family/size/bold/italic in one picker, replacing the separate per-cell controls. `titleblock_editor.py`.
- [ ] [type:bug] Surface solver/renderer warnings on real sheets [P3] [subject:CAD]
  - Details: unknown tokens, image-no-room, and strip overflow warn in the editor banner but are silently dropped on sheets (`TitleBlockTemplateItem.warnings` unread after `PaperScene._setup`); a template that overflows with real project values renders clipped with no message. Route through `titleblock_warning`/status bar like the mismatch case. `paper_space.py`, `main.py`.
- [ ] [type:bug] Orientation-aware template-mismatch message [P3] [subject:UX]
  - Details: the fallback warning names only the paper size; an orientation-only mismatch reads "Template (ANSI D) does not match sheet size ANSI D". `paper_space.py`.
- [ ] [type:feature] "Effective sizing" hint on mixed pairs [P3] [subject:UX]
  - Details: placement props edit the Slot; on a static|dynamic pair the row solves dynamic while the selected static member shows "Static" (per-slot storage, per-row solve). Add an "effective: Dynamic (partner)" note in the props group. `titleblock_arrange.py`.
- [ ] [type:maint] Extract a `FieldsTab` widget mirroring `ArrangementsTab`'s shape [P3] [subject:Code Quality]
  - Details: extract from `titleblock_editor.py` (dialog owns working+snapshots; tabs own widgets) — deferred mid-branch to avoid churning ~400 test-covered lines. Also sweep the residual `variant` naming (`TitleBlockTemplateItem._variant`, editor locals) left by the solver's `layout` rename. `titleblock_editor.py`, `paper_space.py`.
- [ ] [type:maint] Defensive hardening pair (holistic review) [P3] [subject:Code Quality]
  - Details: `PaperScene._refresh_titleblock` should null `_title_tb` before rebuild (future-proofs a mid-swap dangle); editor preview sites should pass `dict(_SAMPLE_VALUES)` (shared-mutable-dict aliasing into `TitleBlockTemplateItem._values`). `paper_space.py`, `titleblock_editor.py`.
- [ ] [type:feature] Side-by-side image+text composition [P3] [subject:CAD]
  - Details: `FieldDef.image_position` is reserved ("top" only today); add "left"/"right" letterhead layouts if stacked proves insufficient. Spec DD-12. `titleblock_template.py`, `paper_space.py`.
- [ ] [type:feature] Insertion-band feel at low zoom [P3] [subject:UX]
  - Details: the quarter-row cap can shrink the drop band to ~±3 px at fit zoom on 10 mm rows (memory: priority bands must not scale with tolerance); if drag-to-insert ever feels fiddly, floor the effective band at ~4 px equivalents while keeping it under half the adjacent row height. `titleblock_arrange.py`.
- [ ] [type:bug] uuid-gate `_do_save`'s result refresh [P3] [subject:UX]
  - Details: Use template A → Save → select B → edit → Save B applies B to the project without an explicit "Use" (pre-existing via old Save; more visible with stay-open Save). Gate the `project_template_result` refresh on `working.uuid == project_template_result.uuid`. `titleblock_editor.py`.
- [ ] [type:maint] `deleteLater()` the editor dialog per open [P3] [subject:Code Quality]
  - Details: dialogs (scenes, undo snapshots, connections) accumulate per MainWindow session; import dialog sets the precedent. `main.py`.
- [ ] [type:maint] Canvas tooltip polish [P3] [subject:Code Quality]
  - Details: pass the cell's viewport rect to `QToolTip.showText` (native per-cell auto-hide) and `ignore()` instead of accept+hideText in the no-name branch (canonical Qt; matters if item-level tooltips are ever added). `titleblock_arrange.py`.
- [ ] [type:maint] `_pick_field_fill` reads the swatch property, not the model [P3] [subject:Code Quality]
  - Details: migrate to the model-read pattern `_pick_text_color` uses (source of truth). `titleblock_editor.py`.
- [ ] [type:feature] Strip position choice (bottom/top for portrait sheets) [P3] [subject:CAD]
  - Details: spec DD-6 reserved `strip_edge`; MVP is right-only. `titleblock_template.py`, `paper_space.py`.

## Gridline bubbles true-scale in paper space

- [ ] [type:bug] Unreproduced crash: viewport delete → qFatal [P2] [subject:Testing]
  - Details: user, 2026-08-08 smoke, one occurrence — select viewport + Delete (or context menu) died with `QWindow::setTransientParent` warning ("plan_view_Level 1Window must be a top level window") then 0xC0000409 abort in Qt6Widgets repaint machinery (WER dump `python.exe.20416.dmp` 8/8 10:52). NOT reproduced by user retry nor by scripted repro (real input + VTK-forced native windows + two viewports). Likely the pre-existing native-child-window class (VTK forces sibling tab pages native; no `AA_DontCreateNativeWidgetSiblings`). Monitoring: launch via `_debug_run.py` (repo root, untracked) to capture faulthandler stack + Qt messages in `_debug_crash.log` if it recurs. `paper_space.py`, `main.py`.
- [ ] [type:feature] Pipe labels adopt the §9.9 true-scale mechanism [P3] [subject:CAD]
  - Details: category-owned paper height + the same mutate/restore geometry stage; today pipe labels are model-unit sized (correct through viewports but not paper-height-driven). Room labels DONE 2026-08-27 ("Room" paper category `label_height_mm`=2.5mm, `apply_paper_overrides._apply_room_label_paper_height`). Pipe label COLOUR done 2026-09-03 (`fix/pipe-paper-line-weight`: `_apply_pipe` forces the label to the paper category colour + save/restore — was white-on-white). Remaining: pipe label SIZE — still model-unit sized; add a "Pipe" `label_height_mm` category key + an `_apply_pipe_label_paper_height` mirroring the room helper (font = `label_height_mm/paper_scale`, save/restore `Label Size`). `pipe.py`, `paper_display.py`. ref: paper-space §9.9.
- [ ] [type:feature] Thin-lines toggle (model-space true-scale WYSIWYG preview of labels) [P3] [subject:CAD]
  - Details: deferred in the 2026-08-07 grill — bubbles/labels render at paper size in model units when OFF. `gridline.py`, `model_view.py`. ref: paper-space §9.9.
- [ ] [type:design] Undo/redo for Display Manager paper-category settings [P3] [subject:UX]
  - Details: user, 2026-08-08 smoke — no DM setting participates in any undo stack today; Label Ht follows that convention. Wants a design pass (which stack? settings-level command pattern). `display_manager.py`.
- [ ] [type:maint] Per-entry exception tolerance in `restore_model_display` [P3] [subject:Code Quality]
  - Details: one raising entry aborts the remaining restores (unreachable same-thread today; hardening if the pass ever grows async). `paper_display.py`.

## Multi-sheet management

- [ ] [type:feature] Per-size title block template library [P2] [subject:CAD]
  - Details: one project template per paper size+orientation; unblocks per-sheet mixed paper sizes (spec §4.10, deferred in the 2026-08-06 grill). Needs its own grill (library keying, embed format, resolution order). `titleblock_template.py`, `paper_space.py`.
- [ ] [type:feature] Mixed paper sizes per sheet [P3] [subject:CAD]
  - Details: re-enable §4.10 once the per-size template library lands; data model already per-sheet, only the uniform-size UI rule relaxes. `main.py`, `paper_space.py`. ref: paper-space §4.10, §19.1.
- [ ] [type:design] Model-space empty-selection/Esc panel state [P3] [subject:UX]
  - Details: Esc in plan views blanks the property panel (window `_on_escape` → `clearSelection`); user decision 2026-08-06: empty selection should show the active view's properties (level, view range…). Own design pass. `main.py`, `property_manager.py`.
- [ ] [type:design] Gate placed-views recompute + browser push to relevant mutations [P3] [subject:Architecture]
  - Details: `_on_paper_modified` rebuilds the sheet tree and recomputes italics on every paper edit (text edits included); bounded but per-edit; also the known double panel-rebuild on sheet-meta change (comment at `_on_sheet_meta_changed`). Consider a viewport-change signal + tree diffing. `main.py`, `project_browser.py`.
- [ ] [type:bug] Drag-cursor polish [P3] [subject:UX]
  - Details: during an internal sheet drag the drop cursor shows over non-sheet rows (drop correctly rejected); scope `dragMoveEvent` acceptance to the sheet zone. `project_browser.py`.
- [ ] [type:bug] Intra-batch filename collision dedupe [P3] [subject:CAD]
  - Details: separate-files export: two numbers sanitizing to the same filename silently overwrite within one batch (overwrite confirm only checks disk). Suffix or warn. `main.py`, `paper_export.py`.
- [ ] [type:maint] Stale `LEGACY_SHEET_KEYS` tuple [P3] [subject:Code Quality]
  - Details: in `titleblock_template.py` still lists Title/Drawing No (docstring-only use) — trim to ("Rev","Date") on next touch.
- [ ] [type:feature] "Sheet X of Y" positional auto field [P3] [subject:CAD]
  - Details: only if wanted for AHJ sets; distinct from Sheet No (needs total-count invalidation). `paper_space.py`.
- [ ] [type:design] Per-sheet persistent undo stacks [P3] [subject:Architecture]
  - Details: undo history currently clears on sheet switch (grilled MVP rule); revisit if switching becomes frequent. `paper_space.py`.
- [ ] [type:feature] Toolbar "Add View" button [P3] [subject:CAD]
  - Details: secondary placement method alongside drag-from-browser. `paper_space.py`.
- [ ] [type:bug] `thermal_radiation_report._export_pdf` QPdfWriter twin (bug #371 sibling) [P3] [subject:CAD]
  - Details: `thermal_radiation_report.py:319` has the identical `QPrinter(HighResolution)+PdfFormat`→PDF pattern as the (fixed 2026-09-09) hydraulic report; latent same-class SEH. Not fixed with #371 because `thermal_radiation_report.py` is a SPEC-INDEX orphan (forge a governing spec on first touch) and has NO test files so it's not suite-reachable today. Mirror the hydraulic fix (→ `QPdfWriter`, set A4 + res 1200, `doc.print()`) when the thermal-radiation subsystem is next touched/specced. `firepro3d/thermal_radiation_report.py`.
- [ ] [type:maint] Batch/multi-page export content-placement verification [P3] [subject:Testing]
  - Details: when multi-sheet management + batch export UI land, add a render-content (not just page-dimension) assertion for mixed-size multi-page PDFs. The `paper_export` pipeline already loops `list[Sheet]` with the corrected per-page device rect (`_page_rect`), but page-2+ content placement is currently only structurally correct, not pixel-verified. `tests/test_paper_export.py`.

## NFPA 13 Compliance Gaps (from 2026-04-29 gap analysis)

- [ ] [type:feature] Remote area selection mechanism [P1] [subject:Hydraulic Calculator]
  - Details: no way to designate the most-demanding remote area for hydraulic design. Currently uses all design sprinklers equally. Need UI to mark remote area + solver to validate it as most demanding. `hydraulic_solver.py`, `design_area.py`.
- [ ] [type:feature] Paper space Phase 2 implementation [P2] [subject:Architecture]
  - Details: annotations layer, label/thin-line scaling, layer overrides per viewport, DXF export. Phase 1 (sheet management, sheet views, PDF print) is partial. See `docs/specs/paper-space.md` Phase 2. `paper_space.py`.

## Documentation Gaps (from 2026-04-29 gap analysis)

- [ ] [type:maint] Update architecture docs for undocumented components [P2] [subject:Documentation]
  - Details: 8 components added since docs were written: DesignArea (`design_area.py`), DetailView (`detail_view.py`), GridLine (`gridline.py`), WaterSupply (`water_supply.py`), BlockItem (`block_item.py`), Theme (`theme.py`), UserLayerManager (`user_layer_manager.py`), Constraints (`constraints.py`). Add to `docs/architecture/entities.md` and `docs/architecture/overview.md`.
- [ ] [type:maint] Update stale metrics in architecture docs [P3] [subject:Documentation]
  - Details: `model_space.py` listed as 7,195 lines (actual: 7,677), `scene_io.py` as 639 (actual: 672), `wall.py` as 1,028 (actual: 1,061). Update `docs/architecture/overview.md`, `docs/architecture/io.md`, `docs/architecture/refactoring.md`.
- [ ] [type:maint] Update refactoring.md [P3] [subject:Documentation]
  - Details: all identified problems remain unfixed and codebase has grown. Add notes about model_space.py growth (+482 lines), wall.py growth, and newly identified decomposition targets (detail_view.py, design_area.py, gridline.py). `docs/architecture/refactoring.md`.

## Codebase Audit — Census 2026-09-09 (see audit/FINDINGS.md)

> F1–F3 done 2026-09-09 (moved to todo_closed.md). F4 REJECTED — vulture's "unused variables" were required Qt slot/override parameters (`currentCellChanged` slots need row/col/prev_row/prev_col; `focusNextPrevChild` is a QWidget override) — removing them breaks the Qt wiring. Not dead code.

- [ ] [type:maint] [cleanup:delete] Investigate + remove 3 unused classes [P3] [subject:Cleanup]
  - Details: @60% — `FSVisibilityDialog`, `LoaderWorker` (loading.py), `LoadingBar` (loading_bar.py). Grep instantiation/dynamic-access first; EXCLUDE ui_kit.* (unbuilt-by-design). Import-smoke after. (audit F#6, risk:med, effort:M)
- [ ] [type:maint] [cleanup:delete] Investigate + remove 16 candidate-dead functions [P3] [subject:Cleanup]
  - Details: @60% (see audit/vulture.txt) — e.g. `geometry_intersect.circle_circle_intersections`, `align_engine.point_along_ray`, `block_library.list_library`, `hatch_patterns.{refresh_patterns,is_builtin,make_hatch_tile}`, `underlay_cache.delete_cache`, `manip_math.transform_angle_deg`. Grep caller+test+dynamic-access per function before deleting. (audit F#5, risk:low, effort:M)
- [ ] [type:maint] [cleanup:delete] Remove 3 unused deps from `requirements.txt` [P2] [subject:Cleanup]
  - Details: fonttools, freetype-py, requests (zero imports; verified). KEEP pytest-timeout (pytest plugin, deptry false positive). (audit F#17, risk:low, effort:S)
- [ ] [type:bug] Investigate pre-existing render-test failure `test_paper_space.py::TestTemplateItemRev3::test_default_template_paints` [P2] [subject:Testing]
  - Details: QImage paint assert L743 — fails on clean `main`, surfaced during audit F1–F3 cleanup. live-smoke-required. (audit F#21, risk:med, effort:M)
- [ ] [type:bug] Pre-existing failure `test_graphic_override.py::test_floor_tab_has_edit_and_graphic_override_groups` [P3] [subject:Testing]
  - Details: surfaced by the full-suite run during the 2026-09-09 U3 PolylineItem PR; confirmed fails identically on clean `main` (unrelated to U3). `_floor_page` asserts a `"Floor"` contextual tab title, but the app now renders `"Modify | Floor"` (the `Modify | <entity>` contextual-tab format). Likely a stale test to update to the current title format — but confirm the tab title is intentional (ref ribbon-bar-spec D8 contextual tabs) vs a title regression before editing the assert. `tests/test_graphic_override.py`, `main.py`.
