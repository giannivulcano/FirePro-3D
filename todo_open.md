# TODO — Open Tasks

> Active/backlog tasks only. Completed work lives in `todo_closed.md` (archive). The `/todo` skill reads THIS file for task selection and moves finished tasks to `todo_closed.md`.
>
> **Task shape** (governed by the task-taxonomy spec): every task is a top-level `- [ ]` line carrying exactly one `[type:bug|feature|design|maint]` tag (first bracket), a plain-English summary, a `[P1|P2|P3]` marker, and an optional `[subject:*]` area tag — with a nested `- Details:` bullet holding file refs, metadata, edge cases, and lineage. Subsystem `##`/`###` headers group by *area*, never by type.

## Paper-space sheet output

- [ ] [type:feature] Per-character (rich-text run) formatting for sheet text [P2] [subject:Architecture]
  - Details: formatting currently applies to the whole block. Spec-level change: `TextAnnotationData` moves from block-level fields to runs (§5.3); QGraphicsTextItem rich-text/QTextCharFormat path; panel + template semantics for partial selections. Needs a spec session first. `paper_space.py`, `docs/specs/paper-space.md §5.3/§9`. Lineage: Sheet-space annotations → property-panel replacement (both done parents).
- [ ] [type:bug] `WallSegment.paint` cosmetic pen ignores the paper "Wall" line-weight [P2] [subject:CAD]
  - Details: `paint()` builds a local `QPen(...).setCosmetic(True)` and never reads `self.pen()`, so `apply_paper_overrides`/`_apply_generic`'s `setPen(width=lw_mm)` is a no-op on wall outlines (walls plot at a fixed cosmetic width regardless of the paper "Wall" line-weight category). Route the wall outline pen through `_display_color`+category weight like the fill. Sibling reference: the pipe line-weight paper-normalization was fixed 2026-09-03 (`fix/pipe-paper-line-weight` → `paper_display._apply_pipe` now divides `lw_mm/paper_scale`, §9.9.1) — the wall version needs the *opposite* fix (make `WallSegment.paint` read the applied pen instead of a hardcoded cosmetic one). `wall.py`, `paper_display.py`.
- [ ] [type:maint] Batch per-level viewport isolation if a many-levels sheet ever lags [P2] [subject:Architecture]
  - Details: v1 applies/restores per differing viewport; a many-distinct-levels sheet does N sweeps. If it ever lags, batch in `paper_export.render_sheet` (group viewports by level, apply once per level, restore once). Filed in `paper-space.md §6.6`; not needed at current viewport counts. Imperceptible-perf → maint. `paper_export.py`.
- [ ] [type:feature] Retrofit wall/floor/roof/geometry template persistence [P2] [subject:Architecture]
  - Details: property-panel spec D0 — pipe/sprinkler/text templates persist, these reset per session. `main.py`, `model_space.py`.
- [ ] [type:feature] Text-box placement polish — rubber-band placement + "Fit to contents" [P2] [subject:UX]
  - Details: (user, 2026-07-20 wrap) (a) click-drag rubber-band placement — drag on Add-Text click sets the initial box size (click-only keeps auto-size); (b) property-panel "Fit to contents" button — resets `box_height_mm`/wrap to the content extents (undo-routed). `paper_space.py`, `property_manager.py`.
- [ ] [type:feature] Absorb the Modify→Text group into the entity-aware Font group [P2] [subject:UX]
  - Details: ribbon-bar spec D2 end state — NoteAnnotation gains family/hex-color/underline (data-model upgrade) and the Font group targets model text too (routed via `push_undo_state`); legacy Modify→Text group deleted. ref: ribbon-bar-spec D2. `main.py`, `annotations.py`, `font_group.py`.
- [ ] [type:feature] Colored highlight for sheet text [P2] [subject:CAD]
  - Details: `opaque_bg: bool` → background color (True→white migration); Word-style highlight palette in Font group + panel. `paper_space.py`, `font_group.py`.
- [ ] [type:feature] Contextual Modify tab that appears on selection and matches the entity [P2] [subject:UX]
  - Details: from the 2026-07-16 ribbon-bar spec grill, D8. Revit-style: Modify tab hidden when nothing is selected, appears+activates on selection, contents specific to the selected entity type, disappears on deselect. Replaces the always-visible tab + force-switch. Needs a design pass (per-entity group registry, QTabBar dynamic insert/remove). ref: ribbon-bar-spec D8. `main.py`, `ribbon_bar.py`.
- [ ] [type:feature] Sheet-text leaders — add/delete leader + leader properties [P2] [subject:Architecture]
  - Details: right-click add/delete leader; leader properties in the panel. (Deferred in the 2026-06-25 grill; pulled back by smoke test.) `paper_space.py`.
- [ ] [type:feature] Sheet-text printed border property (None/Solid/Dashed) [P2] [subject:CAD]
  - Details: (user request, 2026-07-20 smoke) panel dropdown for a printed box border: None (default) / Solid / Dashed / etc.; renders in export as authored; new `TextAnnotationData` field + panel enum row + paint. Distinct from the selection boundary (which is UI-only). `paper_space.py`.
- [ ] [type:bug] Latent point-size ~2.4× PDF over-sizing in the legacy title-block fallback text [P2] [subject:CAD]
  - Details: `TitleBlockItem` (`TitleBlockFieldOverlay` + the CEL DXF/PDF chain deleted 2026-09-26; `TitleBlockItem` is now always hidden — re-check whether any pt text still renders before building). Scoped down 2026-07-22: viewport view-titles + the "View not found" placeholder were converted to the mm primitive (`_draw_mm_text`, DPI-regression-tested) with the titleblock-template build; the remaining pt text lives only in the no-template fallback chain (renders for projects without a parametric template). ref: paper-space §4.11. `paper_space.py`.
- [ ] [type:feature] Expose paper-space text as a Display-Manager category [P2] [subject:Architecture]
  - Details: project-level colour / opaque-bg customization. `display_manager.py`, `paper_display.py`, `paper_space.py`.
- [ ] [type:bug] Blocks drawn with the default white pen are invisible on sheets and in PDF export [P2] [subject:CAD]
  - Details: found by the nested-blocks VC9 seam probe 2026-09-30, PROVEN PRE-EXISTING (branch touches neither `paper_display.py` nor `BlockInstance._display_pen_color`): white-pen block ops plot white-on-white, plain and nested alike. Apply the paper white→black display rule to BlockInstance ops. `block_instance.py`, `paper_display.py`. Memory: paper white/invisible render class.

## Hydraulic calc deliverable

> Cardinal elevations on sheets ALREADY WORK (`ViewResolver`). Riser: cardinal elevation + imported standard detail — reuse, no build.

- [ ] [type:feature] Storage protection criteria system (NFPA 13 Table 4.3.1.7.1) [P2] [subject:Sprinkler Design]
  - Details: when Room hazard is Miscellaneous/Low-Piled/High-Piled Storage, conditional Protection Criteria fields appear (Commodity Classification I–IV/Group A plastics, Type of Storage, Storage Height; ceiling height already computed); table lookup resolves to a design curve (OH1/OH2/EH1/EH2 or "See Chapter 25") + hose allowances + duration; resolved curve inherited by design areas AND consumed by auto-populate; badge STORAGE HEIGHT cell fills. Today all three storage classes disengage inheritance with a warning. Needs its own grill (table encoding scope, Chapter-25 rows, in-rack). Lineage: Design-Area Criteria System (done parent). `room.py`, `nfpa_curves.py`, `design_area.py`, `auto_populate_dialog.py`.
- [ ] [type:feature] Hose allowance inside/outside split [P2] [subject:Hydraulic Calculator]
  - Details: WaterSupply gains Inside + Outside hose allowance (old single value migrates to Outside on load); solver total = inside + outside; report + badge HOSE cells (currently TBD) read both. `water_supply.py`, `hydraulic_solver.py`, `hydraulic_report.py`, `design_area.py`.
- [ ] [type:feature] Domestic water allowance → solver demand [P2] [subject:Hydraulic Calculator]
  - Details: currently informational (badge/WaterSupply property only); add to the supply-curve check like hose stream, with report line items. `hydraulic_solver.py`, `hydraulic_report.py`.
- [ ] [type:feature] Auto-generated one-line riser diagram from pipe/valve topology [P2] [subject:Sprinkler Design]
  - Details: desired POST-MVP differentiator (plays to the hydraulic/topology strength). Arbitrary-angle section-view subsystem is deferred OUT of the MVP (2026-06-23) — cardinal elevations suffice. `model_space.py`, new module.

## Documentation reorg

- [ ] [type:maint] Doc reorg execution — `docs/specs/`→`docs/design/`, archive superpowers, backfill frontmatter [P2] [subject:Documentation]
  - Details: `docs/specs/`→`docs/design/`, `docs/superpowers/`→`docs/_archive/` (excluded from build), backfill `status`/`applies-to` frontmatter on specs, add a Design nav tab. Milestone-level. See `DOCS-REVIEW.md` Part 3 + `docs/specs/SPEC-INDEX.md`.

## Text annotation system

> Feature landed 2026-09-22 on `feat/text-annotation-frame` (frame axis + FontSelect + fill model + grouped annotation property panel + custom Selector/Stepper/Swatch inputs + tokenized panel metrics `theme.M.PROP_*`). Governing spec `docs/specs/text-annotation-system.md`. Follow-ups below.

- [ ] [type:feature] Text style presets + per-property overrides + SHX (draft-spec phase 2) [P2] [subject:UX]
  - Details: the deferred larger vision from `Downloads/Ribbon Text Group — Spec.md` (seed): named `TextStyle` bundles (font/height/width-factor/B-I-U) + per-entity overrides + the launcher/style-manager dialog + SHX fonts (FontSelect already has a font-source seam). ref: text-annotation-system D1/D2.
- [ ] [type:feature] Extend the ribbon Text/Frame groups to model/Block-Editor text (undo-routed) [P2] [subject:UX]
  - Details: the ribbon Text/Frame groups are paper-scoped (`_font_group_targets` returns targets only on a `PaperSpaceWidget`; only `paper_scene.selectionChanged` drives `_update_font_group_context`). Wire model/Block-Editor selection + route model-text commits through the scene undo snapshot. Overlaps the "Absorb Modify→Text into the entity-aware Font group" item. ref: text-annotation-system D6. `main.py`.
- [ ] [type:feature] Paper text inline edit parity with the model primitive [P2] [subject:UX]
  - Details: 2026-09-22 grill decision — the model-surface primitive sets the edit contract (spec text-annotation-system § "Inline edit (model surface) — AS-BUILT": commit-always exits, editor owns every key but Ctrl+S, single undo step, empty-deletes, text-wins-over-centre-grip, self-painted caret). Paper text keeps its older behaviour (dashed #88aaff edit frame, `_on_edit_finished`, `commit_place_text`, paper QUndoStack). Bring paper onto the same contract (likely a paper-side `TextEditController` sharing the predicate + funnel). `firepro3d/paper_space.py`, `firepro3d/text_item.py`.
- [ ] [type:bug] A real Content change in the property panel mid-inline-edit wipes the live typing and double-pushes undo [P3] [subject:UX]
  - Details: seam review 2026-09-23 (M6). The stale focus-out replay (`value == _data.text`) is now a no-op, but a GENUINE Content edit in the panel while the same box is inline-editing calls `setPlainText` (discards typed text) and `set_property` pushes a step, then the session commit pushes a second. Decide: either end the inline session before applying a panel Content change, or disable the Content row while inline-editing. `firepro3d/text_item.py` `_set_property_model`, `firepro3d/property_manager.py`.
- [ ] [type:design] Ribbon Font-group combos end a live model inline edit (the panel doesn't) [P3] [subject:UX]
  - Details: seam review 2026-09-23 (m5). The Font group's editable family/size combos take focus on click and are not the `PropertyManager`, so the inline-edit focus policy commits. Moot while the ribbon is paper-scoped (D6); decide when "Extend the ribbon Text/Frame groups to model text" lands (keep-live list vs commit). `firepro3d/text_item.py` `_focus_out_keeps_edit`, `firepro3d/font_group.py`.
- [ ] [type:maint] Diagnose why the QGraphicsTextItem document renderer hits an engine-less device on the live model viewport [P3] [subject:Architecture]
  - Details: the model surface now sidesteps it entirely (glyph outlines #62 + self-painted caret/selection, 2026-09-23), so this is diagnostic only — relevant if a model-surface text item ever needs Qt's own document rendering. Memory `project_qpainter_engineless_qgraphicstextitem`: never band-aid via `QWidget.paintEngine()`. Needs a live readout at the paint device.

## UI follow-ups

> From the 2026-09-05 UI-cleanup batch.

- [ ] [type:bug] Placement crosshair missing on the visible plan view [P2] [subject:UX]
  - Details: user, 2026-09-08 U3 smoke — confirmed PRE-EXISTING, NOT U3: the U3 branch's only `model_view.py` change is the grip-loop `continue`, which doesn't run during placement; the crosshair enable/draw path is untouched. The accent crosshair (`ui/crosshair`, default ON) is applied once at startup by `main.py:747 _apply_crosshair` looping `self.scene.views()` → `set_crosshair_enabled`. Leading hypothesis: the `Model_Space vestigial-view` bug (`scene.views()` = a hidden index-0 view + one per plan tab, `project_model_space_vestigial_view_bug`) — at startup the crosshair may be enabled only on the vestigial/not-yet-visible view, so the real visible tab never gets it → no crosshair on placement. Diagnostic: toggling Preferences→UI crosshair off/on re-runs `_apply_crosshair` over the current views and (if this is it) restores it. Fix direction: apply the crosshair to the active/visible view (and on tab-open), not just once at startup over `views()[0]`; or gate on `_active_view()`. Live-only. `main.py` (`_apply_crosshair`), `firepro3d/model_view.py` (`_crosshair_enabled`).
- [ ] [type:bug] Title Block editor tab pages paint BLACK live (Overview/Fields/Arrangements) [P2] [subject:UX]
  - Details: user smoke, 2026-09-15 — the `TopTabs` page content area renders flat black in the running app on all three component tabs (Overview info rail, Fields form/info rail, Arrangements). **Live-only: NOT reproducible offscreen** — `dlg.grab()`/`QGraphicsView.grab` under offscreen QPA render the intended `surface` fill correctly (see the many green renders this session), so headless tests can't catch it (`project_live_render_bugs_dodge_headless`, `project_offscreen_qpa_no_fonts_72dpi`). Went ~4 non-converging rounds live-patching; STOPPED per the /todo cascade rule and filed here. **Tried, all failed to fix live:** (1) `content` `QFrame#tbEditorContent { background: surface }` targeted stylesheet; (2) `TopTabs` container + `topTabsBarRow`/`topTabsStackRow`/`topTabsStack` + each page pinned `background: transparent` via targeted objectName selectors; (3) same but pinned OPAQUE `background: <surface>` (per `project_unstyled_qwidget_black_live` "set a bg"). None cleared the black live. **LEADING HYPOTHESIS (try FIRST next session, high-confidence, cheap):** a Qt-stylesheet `background:` rule does NOT paint on a *plain* `QWidget` unless `WA_StyledBackground` is set — the `QStackedWidget` pages (`overview_widget`, `fields_widget`, `ArrangementsTab`) and the `TopTabs` rows are plain `QWidget`s, so their objectName `background:` rule is silently ignored and Qt paints the default (black under the dark house palette). Fix candidates in order: (a) `page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)` on each page + row in `TopTabs.add_tab`/`__init__` (keeps the stylesheet approach); (b) `page.setAutoFillBackground(True)` + set the page's `QPalette.Window` role to `surface` (palette route — but house-dialog QSS may override palette, `project_unstyled_qwidget_black_live`); (c) give the pages a real styled parent (wrap each page body in a `QFrame` with `WA_StyledBackground`). **Diagnostic protocol:** run the app (FULLY restart — a file edit does NOT reload the process), add a temporary live readout at the black widget (dump `widget.testAttribute(WA_StyledBackground)`, `widget.palette().color(QPalette.Window).name()`, `widget.styleSheet()`, `widget.autoFillBackground()`), trust the running app over the code reading. Separately confirm whether the `QGraphicsView` preview/canvas backdrops (dark area beyond the paper) are part of the same complaint or a distinct "set `setBackgroundBrush(surface)`" item. Solid core (convention rollout, rail dividers, margins, maximize, Drawing-Area→Overview merge) is LANDED + test-green (`3144ff8`, `bb183b0`, `0978230`, `c851209`, `866afb7`, `04ff40b`) on `feat/titleblock-ansi-d-default`. `firepro3d/ui_kit.py` (`TopTabs.__init__`/`add_tab`), `firepro3d/titleblock_editor.py`, `firepro3d/titleblock_arrange.py`. ref: ui-design-system.
## UI Design-System follow-ups

> From `docs/specs/ui-design-system.md` deferred waves + P4/P5 review notes (2026-09-06).

- [ ] [type:bug] Return in any `HouseDialog` rejects instead of pressing the primary button [P2] [subject:UX]
  - Details: found 2026-09-22 building the colour picker (todo #70); reproduced on an unmodified `HouseDialog` (focus lands on `_WinDot`, Return → result 0). Two causes: (1) `house_dialog.set_footer_buttons` calls `btn.setDefault(True)` while the footer QFrame is unparented, so QDialog never registers it (a repeat `setDefault(True)` is a no-op); (2) the frameless title-bar dots (`frameless_shell._WinDot`, QPushButton) are autoDefault and take initial focus. Fix: parent/attach the footer before `setDefault`, `_WinDot.setAutoDefault(False)` (+ `NoFocus`). Then delete the local workaround in `colour_picker.ColourPickerDialog.__init__`. Guard: a plain HouseDialog + QTest Return → Accepted. `house_dialog.py`, `frameless_shell.py`. ref: ui-design-system D6.
- [ ] [type:maint] Migrate the hand-rolled QPushButton colour swatches onto `ui_kit.Swatch` [P3] [subject:Code Quality]
  - Details: todo #70 follow-up (grill Q7, out of scope there). Five stylesheet-swatch helpers do the same job: `display_manager._update_swatch` (+ section-pattern variants), `titleblock_editor._make_swatch/_update_swatch`, `roof_dialog._update_color_swatch`, inline in `fs_visibility_dialog._pick`. Each migration changes that dialog's layout (Swatch adds a hex label; Display Manager rows are tight + carry hatch previews) → per-dialog parity smoke. All already route through `colour_picker.pick_colour`. User 2026-09-22 (smoke): the **Display Manager** colour chips should match the property-panel `Swatch` style. Do this as part of a full Display Manager chrome revision, not piecemeal.
- [ ] [type:design] Define No Fill semantics for Display Manager category/instance fills [P3] [subject:UX]
  - Details: todo #70 follow-up. The house picker supports opt-in No Fill (`pick_colour(allow_none=True)`), but Display Manager `fill` currently uses `None` to mean inherit/undefined, not transparent — so No Fill was NOT offered there. Decide: is transparent a distinct state from inherit? `display_manager.py` category/instance/paper fill pickers.
- [ ] [type:feature] Screen eyedropper for the house colour picker [P3] [subject:UX]
  - Details: todo #70 grill Q2 deferral — pick a colour from anywhere on screen (needs a full-screen grab overlay). `colour_picker.py`.
- [ ] [type:maint] Deferred wave: migrate the ~20 native-title-bar dialogs onto `HouseDialog` [P2] [subject:UX]
  - Details: conversion waves. Checklist in the spec: `PreferencesDialog`, `DisplayManager`, `TitleBlockEditorDialog`, `AutoPopulateDialog`, `SprinklerManagerDialog`, `RoofDialog`, `WallDialog`, `PaperExportDialog`, `ArrayDialog`, `CalibrateDialog`, `LevelDialog`, `ViewRangeDialog`, `ThermalRadiationDialog`, `DesignPointDialog`, `FSVisibilityDialog`, `SectionPatternDialog`, `SheetViewPropertiesDialog`, `RevisionsDialog`, `_RecordEditDialog`, `AlgorithmParamsDialog`. Each is a per-dialog parity relocation (header/body/footer + `houseDialog` marker). ref: ui-design-system.
- [ ] [type:maint] Complex-dialog body-container transparency check [P3] [subject:UX]
  - Details: the P4 smoke found simple dialogs' bare-`QWidget` bodies inherited the dark canvas fill (fixed via `body_layout()`); the managers/import pass their own container widgets to `set_body(margin=(0,0,0,0))`. Verify those containers don't show a dark mismatch in any uncovered gaps (mostly tiled, so likely fine); if they do, set the container transparent or route through a transparent wrapper. `underlay_manager.py`, `block_manager.py`, `underlay_import_dialog.py`.
- [ ] [type:maint] Extend the metrics-drift guard test to the complex dialogs [P3] [subject:Testing]
  - Details: once their body CONTENT sizing (column widths, filter widths) is separated from chrome — the guard (`test_metrics_drift_guard.py`) currently covers only `house_dialog.py`/`ui_kit.py`/`themed_message.py` (+ header/footer rails).
- [ ] [type:maint] Post-migration cleanups (P4/P5 review NOTEs, all inert) [P3] [subject:Code Quality]
  - Details: dead `findChild(QDialogButtonBox)` fallback in `underlay_import_dialog._set_controls_enabled`; `apply_stylesheet=False` now leaves the `houseDialog` marker set while blanking the sheet (harmless — marker with no sheet does nothing); pre-existing dead `numericInputRequested` signal (`main._on_numeric_input_requested` is never emitted). `underlay_import_dialog.py`, `underlay_manager.py`, `block_manager.py`, `main.py`.
- [ ] [type:maint] `themed_input_number` unit awareness [P3] [subject:UX]
  - Details: the dimension variant builds `DimensionEdit(None, initial_mm=…)` (`scale_manager=None` → bare-mm display/parse). If a caller needs unit-system-aware display (imperial), thread a `ScaleManager` through the helper. Minor. `themed_message.py`.
- [ ] [type:maint] Live theme-switch-while-open wiring [P3] [subject:UX]
  - Details: folds into the existing "Latched `detect()`" item; `HouseDialog.restyle()` seam now exists. ref: ui-design-system.
- [ ] [type:maint] Tokenize Title Block canvas/preview painter colours [P3] [subject:UX]
  - Details: 2026-09-15 tokenization audit (title-block dialog convention rollout). The dialog's *stylesheet* chrome is fully tokenized (TopTabs/SwitchBar/Section/rail-header/`_vrule`/`_pool_rail_qss` all use `detect().<token>`; the only stylesheet hex are the intentional `#000`/`#fff` field-default-ink + white-paper preview, theme-exempt). Remaining findings are **QPainter/backdrop colours** (not caught by the `setStyleSheet` hexguard) that should move to tokens: (1) `StripCanvas.__init__` `setBackgroundBrush(QColor("#505050"))` — canvas backdrop grey → a themed backdrop token (or `surface`); (2) StripCanvas cell-selection outline `QColor("#2f80ed")` (blue, several call-sites) — decide: intentionally distinct-from-accent, or should be `accent` (green)?; (3) `QColor("#555555")` painter pen; (4) the editor preview `QGraphicsView`s (`_preview_view`, `_field_preview_view`) set **no** `setBackgroundBrush`, so they inherit a dark/near-black default backdrop (the field preview's black-below-the-logo) — set an explicit themed brush. All pre-existing except (4)'s visibility surfaced this session. Bundle with the live-black-bg follow-up if that turns out to share a root. `firepro3d/titleblock_arrange.py` (`StripCanvas`), `firepro3d/titleblock_editor.py` (preview views). ref: ui-design-system §D2.

## Settings dialog follow-ups

> From the 2026-09-14 Settings dialog redesign (`feat/settings-dialog`). Governing spec `docs/specs/settings-dialog.md`.

- [ ] [type:feature] User Profile + full `.fpdt` template subsystem [P3] [subject:Architecture]
  - Details: the deferred long-term vision. Near-term shipped a single AppData `default.fpdt` (opens on startup + New Project via `apply_template_settings`) + a "Save current Project Settings as default" button. Full version: a User-Profile settings layer under System Settings and/or a managed `.fpdt` template library (multiple templates, per-paper-size, project-template picker on New). `settings/template.py`, `main.py`. ref: settings-dialog §5 D7.
- [ ] [type:maint] Dedupe underlay import's `_ToggleSwitch` onto `ui_kit.ToggleSwitch` [P3] [subject:Code Quality]
  - Details: `underlay_import_dialog._ToggleSwitch` (the painted iOS switch) was promoted into `ui_kit.ToggleSwitch` (now the tokenized standard). Migrate the import dialog's "place at origin" usage onto `ui_kit.ToggleSwitch` and delete the local class (kept during the redesign to avoid touching the import dialog's tested code). `underlay_import_dialog.py`, `ui_kit.py`.
- [ ] [type:maint] Settings redesign minor cleanups (seam-review NOTEs + dead default) [P3] [subject:Code Quality]
  - Details: (a) `apply_template_settings` name overlaps between `paper_space` (text templates) and `settings/template.py` — namespaced at call sites, no collision, but a readability trap; (b) `clone_template_into` doesn't strip the `"template": true` marker (harmless — not wired into startup/new, and a cloned project never re-saves it; add a strip if ever wired); (c) dead `grid_mm` key lingers in `settings/panes._FACTORY_DEFAULTS` (widget removed, a test still asserts the key). `settings/template.py`, `settings/panes.py`.

## Block System

> 2D symbol definitions + instances; sibling to Features. Governing spec `docs/specs/block-system.md`; landed slices S1–S4.6 in todo_closed.md.

- [ ] [type:feature] Paper-space block placement — sheet-scoped block instances + drag a block from the Blocks browser onto a sheet [P1] [subject:Architecture]
  - Details: user, 2026-09-29 (nested-blocks grill Q3): sheets must accept block drops like the Block Editor and plan views. Sibling task, run right after the nested-blocks task (which builds the drag gesture target-agnostic). Contract C2/C3: a Paper-placed Block instance is sheet-scoped (no level). Needs: sheet-scoped instance on `PaperScene`, a per-op `QUndoCommand` (paper-space §17 stack, not the model snapshot), sheet serialization, PDF/print output, selection + manipulator on the sheet, the sheet drop branch (reuse `PaperGraphicsView` MIME drop pattern `paper_space.py` dropEvent). ref: paper-space, block-system ("paper placement is a known gap"), model-space-containment-contract C2/C3.
- [ ] [type:feature] Rename a saved block in place from the Block Editor [P2] [subject:UX]
  - Details: block polish 2026-09-23 (spec-audit finding). Silent Save keeps name/library/series and Save As makes a NEW id, so the editor can no longer rename a saved block in place (keep `id`, instances follow) — only the Manager's collision Rename reaches `set_block_metadata`. Options: a "Block Properties…" editor verb opening `BlockSaveDialog` in "edit" context (which also restores the "updates N instances" notice), or inline rename in the Blocks browser / Manager. `block_editor.py`, `blocks_browser.py`, `block_manager.py`. ref: `block-system.md` "Save, import placement & library".
  - Widened 2026-09-30 (nested-blocks smoke): also change LIBRARY and SERIES in place — the user asked "how do i switch the metadata in app?"; today `set_block_metadata` is reachable only through the Manager's save-collision Rename (name only).
- [ ] [type:feature] Grip object limit for large selections (AutoCAD GRIPOBJLIMIT-style) [P3] [subject:UX]
  - Details: block polish 2026-09-23 — selecting a whole imported PDF sheet shows ~100k control-point grips (fast after the grip-point cache, but visually overwhelming). Above N selected items (~100) show frame + move only, no per-item grips. `selection_manipulator.py` `_active_handles`; ref `selection-manipulator.md`.


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
- [ ] [type:maint] Autofilter polish (partly done 2026-09-05) [P3] [subject:UX]
  - Details: S4.x follow-up — `feat/block-manager-autofilter-polish`: funnel/native-sort-indicator overlap fixed (native indicator suppressed; `FilterHeader` paints its own sort caret left of the funnel) + column widths/order/sort persisted across sessions (`QHeaderView.saveState/restoreState` blob under `BlockManager/headerState`, None-guarded). Footer already reads "N of M blocks · K instances" (adequate — left as-is). Remaining/optional: group-count roll-up N/A (flat). `block_manager.py`.
- [ ] [type:feature] Feature re-architecture (deferred sibling milestone) [P2] [subject:Architecture]
  - Details: the locked-but-unbuilt Feature contract from the block grill: 3-tier `Class/SubClass/Type` + `.fpdf`, non-parametric (size = read-only attr of the Type def), openings decomposed into `Door`/`Window`/`Opening` Classes, + the Feature projection-map (which Block draws a Feature in plan/each elevation; no plan block → fallback to true 3D projection) + Feature Editor projection panel + "Generate from 3D". Naming/extension locked in `block-system.md`; supersedes the Feature naming item at the Opening-element cluster. Own milestone.
- [ ] [type:bug] A library block whose folder disagrees with its stored series jumps folders in the Blocks tree when loaded — folder must win [P2] [subject:UX]
  - Details: user smoke 2026-09-30 — `Typical Details/Dimensional Lumber/2x4.fpdb` stored series "Wet Valve Schematics": italic leaves group by FOLDER, project blocks by stored library/series (`BlocksBrowser._grouped`, pre-existing at c60baa2). USER DECISION: **folder wins** — loading adopts the folder's library/series; the browser never moves a block. User's file fixed by hand (backup `2x4.fpdb.bak`). `blocks_browser.py`, `block_library.py`, `model_space.load_blocks_from_files`. ref: block-system.
- [ ] [type:bug] Open Block Editors don't repaint nested blocks after a project undo/redo or project load [P3] [subject:CAD]
  - Details: nested-blocks G2 review (concern c). Undo restore / scene_io load recreate definition objects; open editors' nested instances only repaint on their next `registry.invalidate`. Add a registry-wide invalidate at the end of the project-role `_restore_network` and scene_io load. `model_space.py`, `scene_io.py`, `block_registry.py`.
- [ ] [type:bug] Pasting a block into its own Block Editor isn't refused until Save [P3] [subject:CAD]
  - Details: nested-blocks G2/VC9 reviews. Paste has no cycle check (`paste_items` block_instance branch); A-in-A shows until the commit guard refuses it at Save. Refuse at paste with the LOOP_REASON footer. `model_space.py`, `modify_tools_controller.py`.
- [ ] [type:maint] Paste ghost for block instances [P3] [subject:UX]
  - Details: nested-blocks G2 review (concern a, pre-existing). `_clipboard_ghost_paths` returns [] for `block_instance` records, so pasting a block shows no ghost. `modify_tools_controller.py`.
- [ ] [type:bug] Blocks browser wires both itemActivated and itemDoubleClicked to the same slot [P3] [subject:UX]
  - Details: nested-blocks G3/VC9 (pre-existing). On Windows a double-click can fire both → duplicate footer / double activation (in practice the double-click slot's tree refresh suppresses itemActivated). Connect one. `blocks_browser.py`.
- [ ] [type:bug] Unreadable library block on double-click shows only a footer, not the read-failure dialog [P3] [subject:UX]
  - Details: nested-blocks G3 re-review. The activation guard refuses before load ("This block can't be read"), so `block_library.load_failure_message`'s read-failure branch is unreachable from double-click and drop. Show the dialog on read failure. `blocks_browser.py`, `model_view.py`.
- [ ] [type:maint] Explode enable predicate should match `can_explode` [P3] [subject:UX]
  - Details: nested-blocks G4 review. The Modify ▸ Explode button is enabled for any selected block incl. reference / missing-definition ones the command then refuses (status only). Align `_refresh_modify_buttons` with `block_explode.can_explode`. `main.py`.
- [ ] [type:bug] A rolled-back failed Explode loses the selection [P3] [subject:UX]
  - Details: nested-blocks G4 re-review. `explode_selected_blocks` restores via `_restore_network`, which rebuilds items → selection lost. Re-select the restored instance. `model_space.py`.
- [ ] [type:bug] Library load: bundled deps enter by id only (possible duplicate names) [P3] [subject:CAD]
  - Details: nested-blocks G5/VC9 reviews. `_add_bundled` adds a bundled definition when its id is absent without a (library, series, name) clash check → a different-id project block with the same name can be duplicated. Spec D11 silent. `model_space.py`.
- [ ] [type:feature] Library-load feedback gaps: refused reload silent; drop/double-click never show missing nested blocks [P3] [subject:UX]
  - Details: nested-blocks G5 review. Block Manager `_reload` ignores a False return (loop refusal → no feedback); a successful drop/double-click load never surfaces `summary["missing"]` (only Load-from-Library does). Also parent the project-load missing-nested modal (scene_io) to the main window instead of None. `block_manager.py`, `model_view.py`, `blocks_browser.py`, `scene_io.py`.
- [ ] [type:maint] Retire test-only block_library loaders [P3] [subject:Cleanup]
  - Details: nested-blocks G5/VC9. `reload_from_library` and `load_block_file` have no production caller after `load_block_file_with_bundle`; retire or re-route (grep tests). `block_library.py`.
- [ ] [type:maint] Test gap: library-leaf drag ghost resolves nested blocks project-first [P3] [subject:Testing]
  - Details: nested-blocks G5 re-review. `Model_View` ghost resolver (`sc.get_block_definition(i) or pool.get(i)`) is untested — reverting to bundle-first keeps the drag tests green. Hover-preview only. `tests/test_block_drag_drop.py`.
- [ ] [type:maint] Optional perf-marker test for the Block Manager Used-in rebuild [P3] [subject:Testing]
  - Details: user-ratified bar 2026-09-29: 300 defs × 50 prims, depth-2, median of 5 ≤ 50 ms (measured 1.4–2.4 ms after `users_map`). No suite guard by design (host noise); consider a `-m perf` test. `block_manager.py`, `block_registry.py`.
- [ ] [type:maint] Block specs: reconcile pre-existing contradictions found at the nested-blocks Account [P3] [subject:Documentation]
  - Details: nested-blocks Account 2026-09-30 (record: session scratchpad findings/account.md). (1) model-space-containment-contract.md frontmatter/body say "proposal (unbuilt)" while its ledger says C1/C3 landed and SPEC-INDEX says partial; (2) block-system Decision 10 still says "geometry-immutable (no Editor yet)" vs the built Block Editor section; (3) block-system's by-id edge case names `reload_from_library` (no production caller — see the loader-retire task); (4) the nested-blocks design doc's D-sections read as the original design (the As-built amendments override them — fold them in or mark superseded); (5) block-system's runtime-home bullet restates the snap-point list next to its link (Rule A). Needs a DECISION too: a missing nested definition's red placeholder yields snap points (it compiles as linework) while an orphan top-level instance yields none — pick one behaviour.

### System Blocks build (concept: `docs/superpowers/specs/2026-09-29-system-blocks-concept-design.md`)

> Filed 2026-09-29 by the System Blocks concept run (grill Q1–Q16 + architecture F1–F8, all ratified except F6 = proposal pending its probe). Build order = the concept doc's Build Order (phases 0–7); phase 0 = merge `feat/nested-blocks` (the open Nested blocks task). **Reassess checkpoint after SB3** — stop/redesign if the G6 perf guard fails, bound text can't share static ops, or the slice balloons. Each task carries its F8 spec amendments; guards G1–G7 per the concept doc.

- [ ] [type:feature] SB1a — Block-side binding core: `@[key]` fields in block text, attribute definitions + per-instance values/overrides, split static/bound render cache, keep-upright text, Block Editor authoring (host category, field picker, sample-value preview) [P2] [subject:Architecture]
  - Details: CS2 (2026-10-02, D40): the Block Editor's nothing-selected property panel is now the block view (`firepro3d/block_properties_info.py` — Name / Primitives / Constraints / Status); attribute definitions belong in an "Attributes" section of that view. concept F1 (split cache keyed by definition version + resolved strings), F3 (no kind field: annotation = `scale_mode:"annotative"` + `host_category`; reserved `attributes` list holds `{key,label,type,source:host|instance,host_key,default,prefix,suffix,precision,placeholder}`; text refs attribute keys; reuse `titleblock_template.substitute`), Q11 authoring 1–6. **Absorbs** the former "Block attributes" feature (instance-entered attributes); its deferred `=[AttributeName]` dimension-driven geometry stays with the parametric-constraint spec session. Needs phase 0 (nested-blocks `BlockRegistry` invalidation). Guards G1 (with a stub host until SB2), G2, G5-cache-sharing half of G6. F8: amend `block-system.md` decisions 6 + 9 in place. `block_definition.py`, `block_instance.py`, `text_item.py`, `block_editor.py`, `titleblock_template.py`. Tier Large.
- [ ] [type:feature] SB1b — System library tier: shipped read-only `firepro3d/system_blocks/<Series>/`, multi-root `block_library` (System + User), frozen System ids, `SYSTEM_DEFAULTS` fallback map, Blocks browser System-first with lock + "Duplicate to library…" [P2] [subject:Architecture]
  - Details: concept F4 + Q8 (read-only, Duplicate-to-customize, project embeds, pull-only updates via existing library status + explicit Reload, guaranteed fallback). Series = Tags, Labels, Gridlines, Markers, Symbols, Icons, Reference; library name "System" reserved. Guard G5. F8: `block-system.md` System tier + multi-root section. `block_library.py`, `app_data.py`, `assets.py`, `blocks_browser.py`, `block_manager.py`.
- [ ] [type:feature] SB1c — Annotative sizing: `PlanView.scale` (+ detail-view scale), annotative blocks paint at printed size × painting-view scale, one scene-scoped paper override replaces the §9.9 per-category label helpers [P2] [subject:Architecture]
  - Details: concept F6 — **proposal, pending a human gate**: first plan step is a P4 probe of view resolution from `paint(widget)` and conservative `boundingRect` (max live-view scale + `prepareGeometryChange`) against HALO pick, rubber-band and viewport clip; re-ratify F6 with the probe result before building. Q10: bubbles stop being screen-fixed. Guard G3 (PDF cap height at two viewport scales = authored mm). F8: `view-relationships.md` (PlanView.scale; per-paint scaling on the shared scene, not a third view pattern §5.3) + `paper-space.md §9.9`. Supersedes "Pipe labels adopt the §9.9 true-scale mechanism"; the "Thin-lines toggle" task should be re-checked against this (view scale makes model labels true-scale by default). `level_manager.py`, `detail_view.py`, `paper_display.py`, `model_view.py`.
- [ ] [type:feature] SB2 — Typed element parameters + Marks: `element_params` registry (category → ParamSpec with stable key, kind, tier T1–T4, raw typed getter), `category_of(item)`, Mark on taggable elements with per-category auto-number pattern, duplicate flagging, Renumber [P2] [subject:Architecture]
  - Details: concept F2 + Q6 + Q7. Getters return raw typed values (mm, mm², gpm, psi) or `None` (e.g. before a solve); formatting by kind through `ScaleManager`; T4 one-hop keys namespaced (`Level.Name`); `get_properties()` untouched. `category_of` orders subclass before base (see project memory on isinstance dispatch). Room `Room Tag` becomes its Mark (migration Q13). Mark on both serialization paths. Type Mark deferred to Features. Parallel with SB1a–c. New owning spec `docs/specs/element-parameters.md` (forge with this task). Guards G1 (real hosts), G2. `element_params.py` (new), `pipe.py`, `room.py`, `wall.py`, `wall_opening.py`, `sprinkler.py`, `node.py`, `gridline.py`, `settings/panes.py`, `scene_io.py`, `network_codec.py`, `model_space.py`.
- [ ] [type:feature] SB3 — First vertical slice: room tag drawn by a System block via `BoundLabelItem` + the Project Settings "Annotation defaults" pane (category → block, cloned from template) — then the reassess checkpoint [P2] [subject:Architecture]
  - Details: concept F5 + Q4/Q5/Q13. User designs the RoomTag block in the Block Editor → saved to System library → code switches the room label to it → visual gate (side-by-side in the running app, user approves) → pixel-sampled lock test (G7). Carry over `tag`/`show_label`/`label_offset`; retire the Room paper `label_height_mm` helper in favour of the block's printed size. G6 perf metric + threshold confirmed with the user before this task starts. On completion: run the checkpoint and promote the concept doc to `docs/specs/system-blocks.md` (SPEC-INDEX row). F8: containment C9 amendment (host-bound annotation → model). Depends SB1a, SB1b, SB1c, SB2. `bound_label.py` (new), `room.py`, `settings/panes.py`, `settings/template.py`, `paper_display.py`.
- [ ] [type:feature] SB4a — Convert the pipe label to a System block (user-designed, visual gate) [P3] [subject:CAD]
  - Details: concept Q9/Q13, after the SB3 checkpoint passes. Fields: Diameter, Length, hydraulic flow/friction (T3, placeholder before a solve); `keep_upright` replaces the pipe's flip logic; carry over Show Label + offset; per-pipe Label Size retires. Supersedes the old "Pipe labels adopt the §9.9 true-scale mechanism" task. `pipe.py`.
- [ ] [type:feature] SB4b — Convert the plan gridline bubble to a System block via `BoundLabelItem` (composite rule: line stays bespoke) [P3] [subject:CAD]
  - Details: concept Q9 composite rule + F6 (no longer screen-fixed; `§9.9.1` bubble pass folds into the annotative override). Carry over per-end visibility/standoff + duplicate-warning colour. Retires the `halo_trace_path` special case if the composite trace comes free. After SB3 checkpoint. `gridline.py`, `paper_display.py`, `halo.py`.
- [ ] [type:feature] SB4c — Convert the elevation gridline bubble + level datum head to System blocks [P3] [subject:CAD]
  - Details: concept Q9 (heads only; extents/lines stay bespoke in `elevation_scene.py`). Datum fields: `Level.Name`, `Level.Elevation` (T4/T1). After SB3 checkpoint. `elevation_scene.py`.
- [ ] [type:feature] SB4d — Convert the elevation-marker head and the detail-callout bubble to System blocks [P3] [subject:CAD]
  - Details: concept Q9 composite rule — tangent wedge / crop box / leader-to-crop-edge routing stay bespoke; only the head/bubble graphic + its text (direction letter; detail number + level) come from blocks. Coordinate with the open spec sessions "view markers & shared crop box" and "detail view markers & crop geometry". After SB3 checkpoint. `view_marker.py`, `detail_view.py`.
- [ ] [type:feature] SB4e — Convert the hydraulic node badge to a System block [P3] [subject:Hydraulic Calculator]
  - Details: concept Q9; T3 fields (node number, P, q, Q) with placeholders before a solve; Badge Position carries over. After SB3 checkpoint. `hydraulic_node_badge.py`, `node.py`.
- [ ] [type:feature] SB4f — Convert the sheet viewport view title to a System block [P3] [subject:CAD]
  - Details: concept Q9; fields view number, title, scale (paper-scoped, printed size = paper mm). After SB3 checkpoint. `paper_space.py`.
- [ ] [type:feature] SB4g — Convert sprinkler (3 variants), water-supply and riser symbols to System *symbol* blocks (real size) [P3] [subject:CAD]
  - Details: concept Q9 — symbol blocks, `scale_mode: real_size` with the existing Display-Manager scale multiplier; riser show/hide logic stays in `pipe.py`. Early instance of containment C2 (element composes a Block). After SB3 checkpoint. `sprinkler.py`, `water_supply.py`, `pipe.py`, `graphics/`.
- [ ] [type:feature] SB5 — Hosting foundation: stable `uid` on every model element (both serialization paths, re-applied on undo restore, new on copy/paste) + scene uid index + `HostedDependents` host-geometry hook + delete cascade [P2] [subject:Architecture]
  - Details: concept F7. Pull-on-paint for text (no per-element signals); push for position, generalized from wall→opening `_reposition`. Dangling `host_uid` on load → "?" placeholder + warning. Gated on the phase-4 outcome. Guards G2 (uid round-trip), G4 groundwork. Owning spec: `element-parameters.md` (hosting section). `model_space.py`, `scene_io.py`, `network_codec.py`, every element's `to_dict`/`from_dict`.
- [ ] [type:feature] SB6 — Placed tags: `HostedTagItem`, category-aware Tag tool (hover preview, click place), Q3 host lifecycle, optional leaders (straight/one elbow), wall + door tags [P2] [subject:Architecture]
  - Details: concept Q3/Q5/Q12 + F7. Several tags per host; drag changes offset only; type change re-resolves or shows "?"; cascade delete in one undo step; per-instance swap within host category; leader style from Display Manager category. Depends SB5 + phase-4 readiness. Guard G4. `hosted_tag.py` (new), `model_space.py`, ribbon (Tag button).
- [ ] [type:feature] SB7 — Paper (sheet-scoped) tags: host = (viewport, element); viewport deletion behaves as host deletion [P3] [subject:Architecture]
  - Details: concept Q2 option B. Depends SB6 + the P1 "Paper-space block placement" task. Host moves map through the viewport transform. `paper_space.py`, `hosted_tag.py`.
- [ ] [type:feature] SBV — Valve element (prerequisite for valve tags) [P3] [subject:Architecture]
  - Details: surfaced by the System Blocks concept (Q7) — no valve element exists anywhere (grep 0 hits). Likely an Architectural-style Feature/fitting on the pipe network with a Mark; needs its own design pass. Valve tags then come free via SB6.

## Block Editor constraint system (spec: `docs/specs/parametric-constraint-system.md`)

One constraint type per session, in order (spec §12). Every session: §11 guard tests (math / real-scene E2E drag / save-reopen / undo / diagnostics pixel-sampled / ribbon+icon) → full suite → user smoke + approval → flip the spec's §7.3/§12 row to built + stamp `verified-commit` → reconcile smoke deltas → only then the next session. Decisions D1–D20 + B1–B4 are ratified (2026-09-29 grill); do not re-litigate — a session pins only its own catalogue row (ref order, helper fields, degenerate cases) before building.

- [ ] [type:feature] CS3 — Coincident (point↔point, point↔origin, point-on-curve / point-on-axis) [P1] [subject:CAD]
  - Details: spec §7.3. The primary way to keep drawn shapes joined (D8: snaps never constrain) — make it one click + two picks. Depends CS2.
- [ ] [type:feature] CS4 — Smart Dimension: linear (length, aligned, Δx, Δy) + lock-a-readout promotion + Driving/Reference [P1] [subject:CAD]
  - Details: spec D7/D12, §10. Persisted dims reuse `readout_paint` + the readout HUD editor; label placement picks aligned/Δx/Δy; a permanent dim suppresses its transient readout. Depends CS3.
- [ ] [type:feature] CS5 — Smart Dimension: radius / diameter / angle [P1] [subject:CAD]
  - Details: spec §7.3 (atan2 angle residual, from refs[0] to refs[1] CCW Y-up). Depends CS4.
- [ ] [type:feature] CS6 — Concentric [P1] [subject:CAD]
  - Details: spec §7.3 (substituted). Depends CS5.
- [ ] [type:feature] CS7 — Symmetric (about an edge, X/Y axis, or reference line) [P1] [subject:CAD]
  - Details: spec D13, §7.3 (2 DOF; entity pairs expand to handle pairs). Mirror stays an unlinked scene tool. Depends CS6.
- [ ] [type:feature] CS8 — Fix [P1] [subject:CAD]
  - Details: spec §7.3. Depends CS7.
- [ ] [type:feature] CS9 — Parallel [P1] [subject:CAD]
  - Details: spec §7.3 (normalized cross). Depends CS8.
- [ ] [type:feature] CS10 — Perpendicular [P1] [subject:CAD]
  - Details: spec §7.3 (normalized dot). Depends CS9.
- [ ] [type:feature] CS11 — Equal (lengths / radii) [P1] [subject:CAD]
  - Details: spec §7.3 (unsquared). Depends CS10.
- [ ] [type:feature] CS12 — Tangent (line–arc/circle, arc–arc) [P1] [subject:CAD]
  - Details: spec §7.3 (signed distance + `helper.side` / `helper.internal`). Depends CS11.
- [ ] [type:feature] CS13 — Midpoint [P1] [subject:CAD]
  - Details: spec §7.3. Depends CS12.
- [ ] [type:feature] CS14 — Collinear [P1] [subject:CAD]
  - Details: spec §7.3. Depends CS13.
- [ ] [type:feature] CS15 — Smart Dimension: point–line distance [P1] [subject:CAD]
  - Details: spec §7.3 (signed, side in `helper`). Depends CS14. After CS15 the spec `status` → current.
- [ ] [type:maint] Retire the Align tool (Shift+L, mode `"align"`, `_execute_align`) — redundant with Move + the snap system [P3] [subject:CAD]
  - Details: user, 2026-09-29 constraint grill (D2). ALIGN *tracking* in the snap system stays — only the Align modify tool goes. The padlock/`AlignmentConstraint` half is retired by CS1; if this runs first, retire both. Whole-repo grep (`"align"` mode, `_press_align`, `_execute_align`, Shift+L shortcut, `tests/test_align_tool.py`, `docs/superpowers/specs/2026-04-30-align-tool-design.md`, `scene-tools.md`). Confirm with the user that nothing else rides on the tool before removal.
- [ ] [type:bug] Explode drops a closed polyline's closing segment [P3] [subject:CAD]
  - Details: found reading code in the 2026-09-29 constraint grounding (NOT reproduced yet — run the repro first): `SceneTools.explode_selected_items` loops `range(len(pts)-1)` and ignores `_closed`, so a closed N-vertex polyline explodes to N−1 lines. `scene_tools.py`. ref: scene-tools.md.
- [ ] [type:maint] D18 rect-heavy drag perf — vectorised derived rows, skip the D34 second solve when no size/angle variable moves, no full-snapshot rewrite per D35 frame; since CS2 also the commit diagnostics [P1] [subject:CAD]
  - Details: CS2 P4 ruling (user, 2026-10-02): the CS2 diagnostics (economy-SVD row basis + ordered Gram-Schmidt) cost ~170 ms on the rect-heavy 299x900 component vs the 50 ms commit bar — strict-xfail `test_d18_rect_heavy_cs2_diagnostics` (tests/test_constraint_live_drag.py); the D18 bench compositions pass. Likely the same sparsity fix (the dense J is mostly zeros). Also: the CS2 `restore()` derives red with one single-constraint build per constraint (`_unsatisfied`) — cheap, but measure it with the rest. CS1 VC9 R1 (user ruling 2026-10-02: bench now, optimise later — land BEFORE CS3, where Coincident makes big row components common). Strict-xfail bench `test_d18_rect_heavy_worst_case_drag_frames` (one component, 100 rects + 100 lines, 299 Horizontal): grip-drag frame ~19 ms, D35 body-drag frame ~57 ms vs the 8 ms bar. Also watch the honest `one_component` line bench: 7.8 ms on a memory-starved host (3–4 ms normally). Spec D18 AC stays open until this lands. `sketch_solver.py`, `constraint_controller.py`.
- [ ] [type:feature] Horizontal / Vertical on an exactly perpendicular line rotates it instead of reporting a conflict [P2] [subject:CAD]
  - Details: CS2 (2026-10-02, D36 consequence). A line has no rotation variable, so least-change H on an exactly vertical line (or V on an exactly horizontal one) can only collapse it to a point -> D36 conflict -> red. Pre-CS2 it silently collapsed. SolidWorks rotates the line about its midpoint, keeping its length. Needs a design pass: a length-preserving goal (or a temporary rotation parameterisation) for the add-time solve only; keep D22/D34 for everything else. ref: parametric-constraint-system.md D22/D36.
- [ ] [type:maint] Diagnostics attribution consistency — conflicts in fix-list order, redundancy equalities-before-rows [P3] [subject:CAD]
  - Details: CS2 reviews (2026-10-02, minor): `Diagnostics.conflicts` is attributed in fix-list order, not `cid_rank` (unused for red — red is admission, D38 — but misleading); redundancy marks a later row amber when a later EQUALITY made two earlier rows identical (documented in §7.4). Also `_equality_redundancy` sorts cids missing from `cid_rank` aliases-before-fixes. Unify on `cid_rank` across classes if it ever matters. `sketch_solver.py`.
- [ ] [type:maint] `ConstraintController.load()` per-group solve loop is no longer exercised distinctly [P3] [subject:Testing]
  - Details: CS2 review m-3 (2026-10-02): after the D37/D38 rewrite of `test_open_solves_each_group_despite_a_conflict_elsewhere`, replacing load()'s per-group loop with one whole-system solve still passes all load tests (red constraints now sit out). Either simplify load() to one solve or add a guard that needs per-group writes. `constraint_controller.py`.
- [ ] [type:maint] `test_constrained_body_drag_moves_the_partner_and_glyph_every_frame` flaked once in a full a–d chunk run [P3] [subject:Testing]
  - Details: CS2 VC6 (2026-10-02): 1 failure in 2 runs of `tests/test_[a-d]*.py` (passed in isolation, twice alongside every constraint file, and in the chunk re-run). Real-input posted-event test (same family as the filed offset/array real-input flakes). Tint-ghost hypothesis rejected: Qt pads exposed rects 2 px for AA, covering the D39 tint's +1 px. No traceback captured (--tb=no) — next occurrence: run with --tb=short.
- [ ] [type:feature] Solver globalisation — line search / trust region so a single large jump converges [P2] [subject:CAD]
  - Details: CS2 (2026-10-02): a second case — Vertical on an axis-aligned rectangle's top edge starts at a singular point (d(x_tr - x_tl)/dθ = 0 at θ = 0), so the solve shrinks w (D29) and fails -> red, although a 90° rotation satisfies it. CS1 Task 3/4b reviews: on nonlinear row chains a single pinned jump ≳30 mm (typed edit, transform, fast mouse) stalls (residual 2–22 mm; MAX_ITERS doesn't help) → hold-last-good instead of applying. Frame-by-frame mouse drags are fine. Needed once CS3+ add nonlinear types. `sketch_solver.py`.
- [ ] [type:bug] D35 live body drag snaps to constrained partners' STALE positions (handle-snap targets collected once at press) [P3] [subject:CAD]
  - Details: CS1 VC9 R2. Partners are moved by the solver every frame but stay snap targets at their press-time spots. `selection_manipulator.py` handle-snap session.
- [ ] [type:bug] D35 live resize accumulates solver drift over a long gesture (incremental re-scaling of last frame's corrections) [P3] [subject:CAD]
  - Details: CS1 VC9 R3. Esc is exact; only the committed result drifts. Fix: apply each frame's TOTAL scale to the session snapshot. Only reachable for box-native (Text) resize today. `selection_manipulator.py`.
- [ ] [type:bug] A rolled-back constrained transform still pushes an empty undo step [P3] [subject:CAD]
  - Details: CS1 Task 10 review M1: when `ctl.edit()` rolls back (conflict), the tool's own `push_undo_state()` still records an unchanged step. `constraint_controller.py` edit seam + modify_tools commit sites.
- [ ] [type:bug] Join / geometry Explode / Break remove items via `removeItem` directly, bypassing the constraint cascade [P3] [subject:CAD]
  - Details: CS1 Task 8/VC9 review. Unreachable in the Block Editor today (no button/shortcut) — wire `constraint_ctl.on_items_removed` (+ "N constraints removed") when any of them is exposed. `scene_tools.py`.
- [ ] [type:maint] D4 migration (`BlockEditorWidget._translate_all`) needs a controller seam before CS3 [P2] [subject:CAD]
  - Details: CS1 Task 7 review. Opening a definition translates every seeded item before constraints load; once CS3 adds origin-tied constraints (Coincident-to-origin) the migration must translate through the controller (or load constraints first and solve). CS3 precondition. `block_editor.py`.
- [ ] [type:bug] Align multi-select branch assumes the target is first in the group (`[target] + group[1:]`) [P3] [subject:CAD]
  - Details: CS1 Task 8 fix round: if the target isn't first, one selected item is dropped and the target can move twice. Pre-existing. `scene_tools._execute_align`.
- [ ] [type:maint] Lazy uid minting for throwaway compile items [P3] [subject:Architecture]
  - Details: CS1 Task 5 review M4: `uuid4` (~3.7 µs) now runs for every throwaway item built in `BlockDefinition._compile` / `text_snap_points` / reference compile → ~0.18 s per 50k primitives on a large DXF reference. Mint lazily on first `_uid` read / to_dict. `geometry_2d.py`.
- [ ] [type:maint] Primitive-uid guard gaps — Text paste mint, Mirror/Offset mint, editor commit carrying a LINE uid [P3] [subject:CAD]
  - Details: CS1 Task 5 review M5. The `_add_from_dict` choke point is guarded; these paths aren't directly. `tests/test_primitive_uid.py`.
- [ ] [type:bug] Flaky: `test_constraint_panel.py::test_row_hover_sets_hover_id_and_glows` (order-dependent) [P3] [subject:Testing]
  - Details: CS1 round A: fails sometimes in combined runs; proven pre-existing at 85c7987 in a worktree; passes alone. Likely real-cursor/enter-event interference — reuse the `_NoRealMouse` viewport filter from `tests/test_constraint_live_drag.py`.
- [ ] [type:bug] Flaky: `test_move_handle_snap.py::test_move_tool_recollects_on_pan_out_or_zoom` (`assert 1 >= 2` once in the m-q chunk) [P3] [subject:Testing]
  - Details: CS1 VC6 2026-10-02: failed once in the m-q chunk (host loaded, app running), passed in the earlier full m-r chunk and 3/3 isolated — NOT proven pre-existing (VC7 not run). Posted middle-button pan; likely real-cursor/load interference.
- [ ] [type:design] Neutral icon for unknown / future constraint types [P3] [subject:UX]
  - Details: CS1 round B: unknown types currently reuse `constraint_show_constraints_icon.svg` at 40% opacity (`sketch_model.icon_for`). A dedicated neutral glyph needs the icon mockup gate (40-unit two-token family, D25).
- [ ] [type:design] Duplicate-constraint policy (e.g. Horizontal on a line's edge AND on its two endpoints) [P3] [subject:CAD]
  - Details: user question at CS1 smoke 2026-10-02. Same equation twice → REDUNDANT, not conflicting. As built (D9 admit + flag) it is admitted and solves fine; CS2 colours it amber. Decide in CS2 whether exact duplicates are refused at add ("Already constrained") instead. Recommendation given: keep D9 + amber.
- [ ] [type:maint] Spec §6.1: state the primitive-uid uniqueness scope [P3] [subject:Documentation]
  - Details: CS1 Task 5 review M1: unique per definition / scene; definition clones (Block Manager "New from selected", Save As, Create Block from selection) keep the source uids by design (§6.1 seed carries, §6.2 refs resolve within one definition). One sentence in `docs/specs/parametric-constraint-system.md` §6.1.
- [ ] [type:maint] Doc drift found by the CS1 Account prose review (pre-existing) [P3] [subject:Documentation]
  - Details: (1) `docs/specs/align-placement.md` ~166 still describes the retired pinned insertion marker (Set Origin retired by D4); (2) parametric-constraint-system.md D26 `constraint_free` token is not in `theme.py` yet — note it lands with CS2; (3) §11 item 6 "enables only on a valid selection" contradicts D12/D21 + code (empty selection enables pick mode); (4) 2d-geometry.md ~228 claims `_AXIS_MIN` equals the circle/polygon radius floors — it doesn't; (5) block-system.md status comment doesn't mention CS1 (cosmetic); (6) §6.2 `HandleRef` is a dict shape with no class — add a one-line note; (7) `docs/architecture/io.md:28` still says "Serialize hatches, constraints" (C8-era drift). Findings: CS1 session review_account.md.

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
- [ ] [type:maint] Task-1 minor: redundant page-0 PDF worker churn + semi-synthetic error-path test [P3] [subject:Code Quality]
  - Details: redundant page-0 PDF worker churn on a Modify of a non-zero page (two workers superseded before the target); the PDF error-path test is semi-synthetic (calls `_on_pdf_extract_error` directly rather than a raising worker). `underlay_import_dialog.py`.

## PDF/DXF import geometry inflation

- [ ] [type:maint] DXF geometry inflation — bench-first flatten tuning [P2] [subject:CAD]
  - Details: filed 2026-08-30 from task 73; PDF sibling shipped. Bench whether DXF `SPLINE entity.flattening(0.5)` (`dxf_import_worker.py:549`) and the fixed-count ARC/ELLIPSE tessellation (`steps=64`) actually inflate a reference DXF underlay before changing anything. Note the unit gap: DXF tolerance is in drawing units (mm/inch/feet, file-dependent), not paper points — decide unit-normalization (e.g. via `$INSUNITS`/extents) so a fixed number means a fixed plotted deviation. Consider a Preferences knob mirroring the PDF one. Needs a representative DXF underlay to visually gate. `dxf_import_worker.py`, `underlay_cache.py`, `settings/panes.py`. ref: underlay-workflow §18.5.

## MainWindow chrome polish (2026-09-30 user batch)


## Block Editor ribbon follow-ups (from the always-available tab build, 2026-09-30)

- [ ] [type:feature] Dedicated ribbon icons for Open / Save / Save As / Set Origin / Import (Block Editor tab) [P3] [subject:UX]
  - Details: 2026-09-30 mockup gate — Save + Save As borrow the Create-Block icon, Set Origin borrows Insert, Import borrows Manager, Open uses Manager's. Author 48-unit two-token icons via the icon-style-guide method (mockup-gated contact sheet); Set Origin is retired by CS1, so skip it if CS1 lands first. `firepro3d/graphics/Ribbon/`, `main.py` `_init_block_editor_tab`. ref: icon-style-guide, ribbon-bar.
- [ ] [type:bug] Leaving a Block Editor tab doesn't restore the plan-selection contextual tab [P3] [subject:UX]
  - Details: pre-existing (same in the old contextual-page code), noted by the 2026-09-30 review: entering an editor removes a showing "Modify | <Element>" tab; after leaving, the plan selection is still active but the contextual tab only returns on the next selection change. Re-run `_on_selection_changed_contextual` in `_hide_block_editor_ribbon`. `main.py`. ref: ribbon-bar §3.8.
- [ ] [type:bug] `tests/test_opening_ribbon.py` crashes the test process (exit 127) every run — pre-existing [P2] [subject:Testing]
  - Details: found 2026-09-30 (Block Editor ribbon build), proven at `a0a4547` in a worktree (orchestrator re-proved). Native/slot crash with no traceback; check for the close-time `selectionChanged` family (see the 3D-view follow-ups) or a raise inside a Qt slot (run with an excepthook). `tests/test_opening_ribbon.py`. ref: test-harness.
- [ ] [type:bug] `tests/test_underlay_manager_dialog.py` segfaults intermittently (exit 139) — pre-existing [P3] [subject:Testing]
  - Details: found 2026-09-30, segfaulted at base `a0a4547`; on HEAD crashed once then passed 14/14. Same native teardown family as `test_grip_object_limit.py`. ref: test-harness.
- [ ] [type:maint] `BlockOpenDialog` / Blocks browser tree indentation literal → `theme.M` token [P4] [subject:UX]
  - Details: 2026-09-30 review minor — `setIndentation(16)` is duplicated in `block_open_dialog.py` and `blocks_browser.py`; one `M` token (browser trees share `ui_kit.browser_tree_qss()`). ref: ui-design-system.
- [ ] [type:maint] Spec hygiene from the Block Editor ribbon Account [P4] [subject:Docs]
  - Details: 2026-09-30 Account findings, pre-existing: parametric-constraint-system.md D15 cites icon-style-guide §7 for "no greyed placeholders" but §7 is the no-shipped-placeholder_icon.svg rule (and the plan geo2d contextual tab ships disabled constraint placeholders D15 doesn't record); ribbon-bar.md D7 still says one ribbon test exists and its §5 acceptance criterion omits `_block_mode_buttons`; model-space-containment-contract.md `status: proposal` is stale. ref: parametric-constraint-system, ribbon-bar, model-space-containment-contract.

## 3D view follow-ups (from the closable 3D tab build, 2026-09-30)

- [ ] [type:bug] MainWindow close with a plan item selected crashes the test process (exit 127) [P2] [subject:Testing]
  - Details: found 2026-09-30 (closable-3D-tab Task 10), proven pre-existing at `7233649` in a worktree (1/3 plain runs exit 127; hooked run shows the RuntimeError). At `MainWindow.close()` the scene's destruction emits `selectionChanged` → `_on_selection_changed_contextual` → `self.scene.selectedItems()` → "wrapped C/C++ object of type Model_Space has been deleted" inside a Qt slot. Workaround in `tests/test_view3d_tab_mainwindow.py` fixture (clear selection before close). Fix in production: disconnect/guard the contextual slot on teardown (`sip.isdeleted`). Likely one cause of the "native GL degradation" crashes; related to the module-singleton fixture item in this file. `main.py`. ref: test-harness.
- [ ] [type:bug] Checkable draw/tool buttons stay lit when `set_mode` refuses on an empty canvas [P3] [subject:UX]
  - Details: 2026-09-30 — `Model_Space.set_mode` refuses non-select modes while `view_available` is False (view-3d.md I5), but checkable ribbon buttons that set themselves checked before calling it can stay highlighted. Radiation (F6) already calls `_sync_mode_buttons` after refusing; generalize (e.g. re-sync mode buttons on refusal). `main.py`, `firepro3d/model_space.py`. ref: view-3d, ribbon-bar.
- [ ] [type:bug] Radiation report dock keeps the previous project's results after New/Open [P3] [subject:Analysis]
  - Details: 2026-09-30 — the 3D heatmap is now cleared by `View3D.reset_for_project` (view-3d.md I9), but `MainWindow.radiation_report` / `radiation_dock` and `_radiation_*` state are not reset on `new_file` / `_apply_loaded_file`. `main.py` (`_clear_radiation`). ref: view-3d; thermal radiation is an orphan subsystem (forge on first touch).
- [ ] [type:bug] Plan tools arm on the hidden plan scene while the 3D / Paper / Block-Editor tab is current — verify [P3] [subject:UX]
  - Details: 2026-09-30 grill + seam review — ribbon plan tools call `self.scene.set_mode` regardless of the current tab (Modify tools refuse on Paper only). A Block-Editor-only canvas counts as "a view open" (user-ratified, view-3d.md I5), so it is covered by this item. Repro first, then decide refuse vs auto-open plan. `main.py`. ref: view-3d, scene-tools.
- [ ] [type:feature] Save the 3D camera per project in the `.fpd` [P3] [subject:3D]
  - Details: 2026-09-30 grill (view-3d.md I9) — today new/open re-fits the camera; persisting position/focal/up/projection per project was deferred. `firepro3d/view_3d.py`, `firepro3d/scene_io.py`. ref: view-3d, scene-io.
- [ ] [type:design] Unify 3D pick with the scene selection [P3] [subject:3D]
  - Details: 2026-09-30 grill (view-3d.md I8) — 3D keeps a private `_3d_selected` list next to the scene selection (Delete routes through `Model_Space.delete_items`). Design a single selection model (2D⇄3D highlight, one property panel, selectionChanged loop handling). ref: view-3d, selection-mode (Leg C 3D).
- [ ] [type:maint] Extract canvas-tab management out of `main.py` [P3] [subject:Architecture]
  - Details: 2026-09-30 (closable-3D-tab approach C, deferred) — plan/detail/elevation/paper/Block-Editor/3D tab open-close-activate logic + the empty-canvas stack live inline in `main.py` (over the 1000-line tripwire). `View3DTabController` is the pattern to generalize. ref: view-3d, mainwindow-chrome-revamp-stage2.
- [ ] [type:maint] View3D hygiene ledger D14/D16 [P3] [subject:3D]
  - Details: from view-3d.md §9 — D14: Fit All / Ortho / Refresh toolbar buttons lack tooltips; colours/tolerances are module constants not tokens; theme read once; unused imports/constants. D16: line-fallback pipe width uses the first pipe's diameter; water supply always at Z=0; floor planes sized to nodes only. `firepro3d/view_3d.py`. ref: view-3d.
- [ ] [type:maint] Stale docstring in `tests/test_view_3d.py` TestCleanup [P4] [subject:Testing]
  - Details: 2026-09-30 — `test_rebuild_after_cleanup_is_noop`'s docstring still says the debounced refresh slot calls `view_3d.rebuild()`; since the closable-3D-tab build `_refresh_all_views` no longer touches 3D (View3D rebuilds via its own `sceneModified` → `request_rebuild`). Reword; keep the guard. ref: view-3d.
- [ ] [type:bug] Project Browser keeps the construction-time ScaleManager after New/Open [P3] [subject:UX]
  - Details: found 2026-09-30 at the closable-3D-tab Account (project-browser.md D8, pre-existing): `ProjectBrowser.set_scale_manager` has no caller, so level-elevation tooltips format with stale units after load/new. Wire it next to `View3D.reset_for_project` in `new_file` / `_apply_loaded_file`. `main.py`, `firepro3d/project_browser.py`. ref: project-browser, units-and-formatting.
- [ ] [type:design] Elevation canvas paints `ground` while plan/3D/empty canvas paint `surface` [P3] [subject:UX]
  - Details: 2026-09-30 Account — `elevation_scene` uses `theme.canvas_bg` (= `ground`); the plan viewport inherits `surface` from main.py's selector-less canvas-wrap QSS; 3D + the empty-canvas pane were set to `surface` at the user's smoke. Decide one canvas token (and whether `canvas_bg` should be renamed/re-pointed). Mockup gate. `firepro3d/theme.py`, `firepro3d/elevation_scene.py`, `main.py`. ref: mainwindow-chrome-revamp-stage2, architecture/theming.
- [ ] [type:bug] `test_grip_object_limit.py` access-violates at process exit (exit 139) after 7/7 pass — pre-existing [P3] [subject:Testing]
  - Details: found 2026-09-30 (closable-3D-tab Account); proven at branch base `dedd21e` in a worktree (3/4 runs crash; 4/4 at HEAD). Native exit-time crash, no Python frame — likely the same lingering-MainWindow / teardown family as the items in this file. `tests/test_grip_object_limit.py`. ref: test-harness.
- [ ] [type:maint] Stale comments after the closable-3D-tab build [P4] [subject:3D]
  - Details: 2026-09-30 Account — the `View3D.rebuild()` comment still cites the `_view_refresh_timer` refresh; `ViewCube._build_rotation` docstring cites vispy (view-3d.md D12 partial); `view-relationships.md` §9 open question 5 ("3D rebuild triggers") is answered by `view-3d.md` §2.3 — close it with a link; `mainwindow-chrome-revamp-stage2.md` is `current` but its acceptance/verification checkboxes were never ticked. Fold into the D14/D16 hygiene item if convenient. ref: view-3d, view-relationships.

## Accent-colour / status-chrome unification

> Chrome Revamp Stage 2 shipped 2026-09-19 (`feat/chrome-revamp-stage2`; governing spec `docs/specs/mainwindow-chrome-revamp-stage2.md`): browser LeftTabs, canvas TopTabs language, three-tone window scheme, property-panel overline, middle-surface tokenization. Follow-ups below.

- [ ] [type:feature] Browser LeftTabs tab icons (mockup-gated) [P3] [subject:UX]
  - Details: Stage-2 LeftTabs (Project/Model/Features/Blocks) ship text-only; author 4 tab icons per the icon style guide (mockup-gated) and wire via `LeftTabs.addTab(..., icon=)`. `firepro3d/ui_kit.py` (LeftTabs), `firepro3d/graphics/`. ref: icon-style-guide, mainwindow-chrome-revamp-stage2.
- [ ] [type:maint] DRY the selected-tab fill/border override across tab surfaces [P3] [subject:Code Quality]
  - Details: the "selected = accent-soft fill + 1px accent outline + accent bar" override is copied in 3 places (ribbon `build_ribbon_qss`, canvas `#centralTabs`, browser `#leftTabsBar`); extract a `theme._tab_selected_fill_qss(sel, edge=)` helper (sibling to `_tab_language_qss`) so the highlight language has one home. `firepro3d/theme.py`. ref: mainwindow-chrome-revamp-stage2.
- [ ] [type:maint] Live theme-switch for the Stage-2 rails/widgets [P3] [subject:UX]
  - Details: header/footer rails, LeftTabs, and the canvas wrap latch `detect()` at construction (WA_StyledBackground bg set once), so a runtime Preferences→UI theme switch doesn't restyle them until relaunch. Folds into the existing "Latched `detect()`" item — have `MainWindow._apply_theme` re-apply the rail/wrap backgrounds. `main.py`, `firepro3d/header_rail.py`, `firepro3d/footer_rail.py`, `firepro3d/ui_kit.py`.
- [ ] [type:maint] Full chrome unification (follow-up) [P3] [subject:UX]
  - Details: the deferred remainder of the accent-unify task: (a) migrate the OFF-state pill/toolbar greys (`#888`/`#555`/`#243a4e`/`#3a607e`/`#99bbdd`) and the SNAP toolbar `:checked` background (`#2a5a8a`) onto theme tokens; (b) add live theme-switch restyling so a Preferences→UI change repaints without relaunch — needs icon-loader cache invalidation (spec §6 says process-lifetime today) + re-applying the pill/badge/toolbar styles; (c) add `main.py` to the `test_theme_chrome_hexguard.py` allow-list once (a) lands. Bundles with the "Latched `detect()` in construction-time consumers" item. `main.py`, `firepro3d/icons.py`, `firepro3d/theme.py`, `tests/test_theme_chrome_hexguard.py`.

## Floor placement workflow

- [ ] [type:feature] Roof twin — mirror the floor two-boundary + wall-mirrored placement onto roofs [P2] [subject:Architecture]
  - Details: apply this identical two-boundary + wall-mirrored-placement treatment to `roof.py`/`roof_rect` (the agreed fast follow-up; roof is structurally identical to floor). `roof.py`, `model_space.py`.
- [ ] [type:feature] Paper-viewport dynamic view-height parity [P3] [subject:Architecture]
  - Details: T4's `compute_view_height` recompute is scoped to on-screen `_apply_plan_level`; paper `SheetViewport` still renders from the cached `pv.view_height` via the resolver. Wire the dynamic upper-bound (or the explicit flag) into paper rendering so plotted sheets match on-screen. `paper_space.py`, `paper_export.py`, `level_manager.py`.
- [ ] [type:design] Wall/roof template-name behavior diverges from floor [P3] [subject:UX]
  - Details: floor now seeds placed instances from the template name (uniquified "Slab/Slab 1/…"); walls/roofs still auto-number "Wall N"/"Roof N" and show a vestigial editable template Name. Decide whether to unify them onto the floor behavior. `model_space.py`.
- [ ] [type:maint] T5 placement test-hardening gaps [P3] [subject:Testing]
  - Details: holistic-review notes — typed-HUD-dimension commit test for floor rect; center-rect 3-step placement test; cross-primitive-cycle-guard (cycling mid-placement refused) test; Delete-pop test for the floor polygon. `tests/test_floor_placement_workflow.py`.
- [ ] [type:feature] RegularPolygon as a floor boundary primitive (dropped scoping option, 2026-08-27) [P3] [subject:CAD]
  - Details: register the parametric N-gon into the floor ←/→ cycle (↑/↓ sides), if wanted. `model_space.py`, `floor_slab.py`.

## ALIGN placement & misc CAD

- [ ] [type:bug] Doors at ground level (elevation 0) don't render in plan/sheets until a level switch [P2] [subject:CAD]
  - Details: user, 2026-08-27 paper-space-bundle smoke test — NOT yet root-caused; a live-only render bug, needs the running app. Symptom: a door hosted on a ground-level (elevation 0) wall shows a solid wall, no door in plan view AND on sheets; the door is visible in 3D; switching the active level away and back (or nudging the level elevation off 0) makes it appear and it persists. Ruled out (headless, proven): the data/z/visibility/geometry are all correct through the FULL save→`load_from_file`→`apply_to_scene` path — after load the opening is in `wall.openings`, `isVisible()==True`, z-pinned above its host wall (`op.z=30.83 > wall.z=30.78`, the §585 `Z_CAT_OPENING` pin), path non-empty, `z_range=(0,2032)`. `_apply_z_filter` at `[view_depth=-1000, view_height=2000]` keeps it visible. The plan gap is drawn by `WallOpening._paint_symbol` filling `_gap_rect` with the scene-bg colour (needs `op.z>wall.z`, which holds) — NOT `_is_section_cut`-dependent. A MainWindow `_load_project` test asserts the door visible after load and passes (doesn't reproduce). A speculative "build ViewResolver before `_activate_plan_view`" fix was tried and reverted — it's a functional no-op. Leading hypothesis: a live-only stale-paint / missing viewport invalidate on first load. Next (needs the live app): (a) does zoom in/out alone (repaint, no `apply_to_scene`) fix it? → pure stale-paint → force a repaint/`scene.update()` after load; (b) is the door selectable where it should be vs nothing there? Also compare vs `main` to confirm pre-existing vs a bundle regression. `wall_opening.py` (`_paint_symbol`/`_gap_rect`), `model_view.py`, `main.py`, `level_manager.py`.
- [ ] [type:feature] ALIGN: Parallel-OFFSET tracking (perpendicular offset from a reference line) [P2] [subject:CAD]
  - Details: user, 2026-08-26 ALIGN smoke test — the parallel behavior actually wanted. The shipped direction-acquire "Parallel" only constrains direction (draw parallel, length along it) and is defaulted OFF (`ALIGN_DIR_PARALLEL_DEFAULT=False`, flaky track-swap flicker). What the user wants is in-placement OFFSET: acquire a reference line, then a typed distance places your point/line parallel to the reference at that perpendicular offset (AutoCAD OFFSET as a live snapping aid). Distinct feature — needs its own grill→design→build: side selection, snap-to-offset-guide vs type-distance, single offset vs repeating array, how the offset guide renders, and whether it replaces or coexists with the direction-track parallel. Reuse the direction-acquire plumbing (`align_controller.py` flavor="direction", `align_engine.py` parallel ray) but the ray becomes an offset line (parallel at distance D) and the HUD field is a perpendicular offset. `align_engine.py`, `align_controller.py`, `model_space.py`, `dynamic_input.py`, `settings/panes.py`, `docs/specs/align-placement.md`.
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

## Model Space Containment Contract (2026-09-16 design grill — follow-ups)

> Design landed: `docs/specs/model-space-containment-contract.md` (proposal) + forged `docs/specs/feature-system.md`. The contract makes Model Space **placement-only** (Features + Block instances + Underlays; no loose geometry/markup/text), moves all markup/text to Paper Space, reframes **Feature = composes Blocks** (supersedes "siblings"), makes 2D primitives definition-local/level-less, adds **Text as the 9th primitive** (unified data model), dissolves the Create tab, and clean-drops legacy loose geometry on load. Ribbon mockup: `docs/mockups/ribbon-containment-contract.html`. **Implementation is deferred; these are the next steps.** Superseded/relocated existing items are enumerated in the contract's "Task hit-list".

- [ ] [type:feature] Reference-graphic unification — deferred follow-ups (post core-internal slice) [P2] [subject:Architecture]
  - Details: the core-internal re-home LANDED 2026-09-17 (`feat/reference-graphic-unification`; core-internal slice in todo_closed.md — Underlay re-homed on a reference `BlockDefinition`, batched render/snap repointed at it, transparent migration). Remaining pieces, each its own slice: **(4b) curve-fidelity import flip** — flip underlay import to `_preserve_curves=True` after verifying snap parity on parametric (arc/spline/ellipse) underlay geoms in `UnderlaySnapIndex._geom_bounds` + `snap_engine._collect_from_geom` (closes RD1; `dwg_converter.append_geom_to_path` already renders them); **(R5) selection de-prioritization + "lock in place" toggle** — depends on selection-mode ranking; **edit-underlay-in-Block-Editor** — rep-2 materialization, its own perf problem; **per-primitive visibility**; **convert/promote underlay↔block**. ref: reference-graphic-model.md (Deferred work + Divergences RD1/RD3/RD4). `underlay_import_dialog.py`, `dxf_import_worker.py`, `snap_engine.py`, `selection-mode`.

## 2D geometry: first-class level-plane placement + fill

> `EllipseItem` + `SplineItem` native 2D-geometry primitives LANDED 2026-09-08 on `feat/ellipse-spline-primitives` (landed items in `todo_closed.md`). Follow-ups below. **⚠️ Several items in this + the placement-polish sections are superseded/relocated by the Model Space Containment Contract (2026-09-16) — see that section + the spec's Task hit-list before picking one up.**

### Hatch & Fill build (concept: `docs/superpowers/specs/2026-10-01-hatch-and-fill-concept-design.md`; what = `docs/specs/hatch-and-fill.md` D-A1–D-A27)

> Filed 2026-10-01 by the Hatch & Fill concept run (grill Q1–Q27 + brainstorm HD1–HD8, all ratified). HF1 ∥ HF2 independent; then HF3 → HF4/HF5 → HF6 → HF7; HF8 waits on SB1b, HF9 on SB1c. Each slice carries its guards (G1–G12 in the concept doc) and its linked-spec amendments ("Cross-spec reconciliation" in `hatch-and-fill.md`).

- [ ] [type:feature] HF1 — Colour tokens: ColourValue (`#hex` | `token:auto` | `token:accent`) + `resolve_colour(value, surface)` + surface context (paper/print/PDF/previews = light values, B&W = black) + `theme.changed` live repaint + picker/Swatch Automatic·Accent row + load migration of defaults + format bump + raw-`QColor(hex)` hexguard [P2] [subject:UX]
  - Details: concept HD6; D-A18–D-A21. Automatic becomes the default for new 2D geometry + text (replaces hard-coded `#ffffff`). Latched consumers (text default colour, SVG tints, labels, gridlines, block render cache) subscribe to `theme.changed`. Amend `ui-design-system.md` D6 + `architecture/theming.md`. DXF ACI 7 / PDF pure black → Automatic lands here or with HF6/HF7 (importer side). Guards G8, G9 (colour half), G12 (theme-switch bar). New `colour_value.py`, `theme.py`, `colour_picker.py`, `ui_kit.py`, `paper_display.py`, `main.py`, `geometry_2d.py`, `text_item.py`, `scene_io.py`. Tier Large.
- [ ] [type:feature] HF2 — World-unit pattern renderer + pattern-tile blocks: `BlockDefinition.tile {w,h,row_shift,size}`, Block Editor tile frame + live repeat preview, tiled renderer (IntersectClip, origin, scale, LOD tone, cell cap) replacing Qt brush patterns/SVG parser/`views()[0]`, `RenderOp` compile with fill/pattern ops (fixes H1–H6) [P2] [subject:CAD]
  - Details: concept HD4 + D-A8–D-A11. Pattern pickers list only tiled blocks; tiled blocks not placeable as symbols. Section-cut walls/floors route through the renderer. Ships test patterns only (real set = HF8). Guards G3, G4, G5, G12 (placed-blocks bar). Amend `block-system.md`. `block_definition.py`, `block_instance.py`, `block_editor.py`, `hatch_patterns.py`, `displayable_item.py`, `wall.py`, `floor_slab.py`. Tier Large.
- [ ] [type:feature] HF3 — FilledRegion primitive + Select-objects creation + dissolve per-item fill (migrate `prim["fill"]` → region + shape) + modify-tool rules D-A13 + dead-code removal (H9) [P2] [subject:CAD]
  - Details: concept HD2; D-A1, D-A2, D-A7, D-A12, D-A13, D-A16, D-A26. 10th 2D primitive joins every primitive registry (block compile, Explode, clipboard type dispatch, paper, HALO, snap, both serialization paths). Ribbon Fill tool in the Block Editor + Paper tabs (with tooltips; family parity with other placement tools). Fill context submenus/ribbon fill buttons become "Region from this shape" (retires the H7 undo-ordering bug + the duplicated submenus). Guards G9. Depends HF2. Amend `2d-geometry.md` (fill section), `scene-io.md`. `geometry_2d.py` (or `filled_region.py`), `scene_tools.py`, `model_space.py`, `entity_context_menu.py`, `model_view.py`, `main.py`, `paper_space.py`. Tier Large.
- [ ] [type:feature] HF4 — Pick-point region finder: windowed arrangement from `halo_scene_path` edges, 1 mm weld, face-at-click with islands, exact-curve rebuild, hover preview + "Not enclosed" hint [P2] [subject:CAD]
  - Details: concept HD3; D-A3–D-A6. Perf bar ≤ 50 ms/move on ~500 primitives (confirm bench with user first). Guards G1, G2, G12 (hover bar). Depends HF3. New `region_finder.py`, `model_space.py`, `snap_engine.py` (region boundary snaps). Tier Large.
- [ ] [type:feature] HF5 — Fill Types: project table + resolution + Fill Types manager (**mockup-gated**) + Display Manager section column → Fill Type (remove dead Roof column) + `.fpdb` schema 3 bundling (types + pattern blocks, project wins) + "used by N" delete guards [P2] [subject:CAD]
  - Details: concept HD5; D-A14, D-A15, D-A17. Guards G6, G7. Depends HF3. New `fill_types.py`, `display_manager.py`, `block_library.py`, `block_registry.py`, `settings/template.py`, `scene_io.py`. Tier Large.
- [ ] [type:feature] HF6 — PDF fills: read type/fill/fill_opacity/even_odd/seqno, separate subpaths, glyph-run grouping; underlay batches split into paint-order runs + cache version bump; Block Editor import → FilledRegions on "Imported Solid" [P3] [subject:CAD]
  - Details: concept HD7; D-A21, D-A22. Supersedes the former "Import fills — detect + preserve…" feature (PDF half). Perf bar: underlay with fills ≤ 1.5× stroke-only frame time on the real FS plan PDF. Guards G10, G12. Fix `underlay-workflow.md` §16.3. Depends HF3, HF5. `pdf_import_worker.py`, `geometry_import.py`, `dwg_converter.py`, `underlay_controller.py`, `underlay_cache.py`, `block_import_dialog.py`. Tier Large.
- [ ] [type:feature] HF7 — DXF SOLID + HATCH: SOLID vertex order 0-1-3-2 → filled; HATCH via `hatch.paths` (+ islands); underlay = fill + pattern lines; Block Editor = region + project-only pattern block converted from the HATCH line families (rational-slope tile, deduped) + "(imported)" type; unconvertible → lines + import-report note [P3] [subject:CAD]
  - Details: concept HD7; D-A23. P4 probe passed 2026-10-01 (ezdxf 1.4.2: `hatch.paths`, `hatch.pattern.lines`, `ezdxf.render.hatching`). Supersedes the DXF half of the former Import-fills feature. Fix `underlay-workflow.md` §10.5 (claims HATCH works). Guard G11. Depends HF6. `dxf_import_worker.py`, `block_import_dialog.py`. Tier Large.
- [ ] [type:feature] HF8 — Ship System > Hatches series + template Fill Types [P3] [subject:CAD]
  - Details: D-A24 set — Drafting: Diagonal 45°/135°, Cross-hatch 45°, Horizontal, Vertical, Grid, Concrete, Earth, Sand, Insulation (batt), Steel (ANSI31-style); Model: Brick (stretcher bond), Block/CMU, Tile 300×300, Stone. Template types: Solid Black, Solid Grey 20%, Concrete Section, Earth, Insulation, Imported Solid. Retires `graphics/hatch_patterns/*.svg`. Add the Hatches series to the System Blocks concept. Depends HF5 + SB1b.
- [ ] [type:feature] HF9 — Drafting patterns at printed size in model-placed blocks (view-scale term of the renderer) [P3] [subject:CAD]
  - Details: D-A10; until built, Drafting patterns in model fall back to real size. Depends SB1c (`PlanView.scale`).
- [ ] [type:bug] DXF HATCH imports nothing — `virtual_entities()` doesn't exist on ezdxf 1.4.2 `Hatch`; the AttributeError is swallowed [P2] [subject:CAD]
  - Details: proven 2026-10-01 (`hasattr(Hatch,'virtual_entities') == False`; sweep D: solid + ANSI31 fixtures import empty). `dxf_import_worker.py` composite branch (`INSERT/DIMENSION/HATCH…` → `entity.virtual_entities()`). Stopgap until HF7: emit `hatch.paths` boundary outlines (+ pattern lines via `ezdxf.render.hatching`). Also DXF SOLID imports as a bowtie (vertex order 0-1-3-2). Reproduce first.
- [ ] [type:feature] Import AutoCAD `.PAT` files → pattern-tile blocks [P3] [subject:CAD]
  - Details: D-A8 follow-up; reuse HF7's line-family → tile conversion. After HF7.
- [ ] [type:feature] Recover real text from PDF glyph-outline fills [P3] [subject:CAD]
  - Details: D-A22 follow-up — HF6 imports glyph text as one region per text run; map runs back to editable text using the page's text spans.
- [ ] [type:feature] Roof section cut hatch [P3] [subject:CAD]
  - Details: D-A17 follow-up — the dead Roof section column is removed in HF5; implement roof section-cut drawing through Fill Types if wanted. `roof.py`.
- [ ] [type:design] Filled Region: associative boundary + Sketch / Edit Boundary mode + manual draw order [P3] [subject:CAD]
  - Details: D-A1/D-A3/D-A7 deferrals. Associative needs System Blocks SB5 stable uids; Sketch mode is the Revit "Edit Boundary"; draw order = bring forward/send back among regions/items.

### Linetypes build (concept: `docs/superpowers/specs/2026-10-02-linetypes-concept-design.md`; what = `docs/specs/linetypes.md` D-L1–D-L23)

> Filed 2026-10-02 by the linetype concept run (grill Q1–Q23 + brainstorm LD-A, LD1–LD7, all ratified). LT1 ∥ LT2; then LT3 → LT4 → LT5 → LT6 → LT7/LT8. Each slice carries its guards (G1–G11 in the concept doc) and its spec amendments ("Cross-spec reconciliation" in `linetypes.md`). End goal (user): build system geometry (gridline, pipe, leader) from primitives.

- [ ] [type:feature] LT1 — Project-scoped named weights (`.fpd`; QSettings = template; `.fpdb` bundles used weights, project wins) + Display Manager "Blocks" category weight + `_category_for_item` BlockInstance case + canvas px = mm × `UNDERLAY_MM_TO_PX_HINT` + view-level Thin Lines toggle [P2] [subject:CAD]
  - Details: concept LD4; D-L5, D-L13, D-L14, D-L17. Fixes block linework plotting cosmetic on PDF. Retire `text_item._BORDER_WEIGHT_PX` + `frame_group` weight copies onto the shared mapping. Guards G4 (category half), G8 (weights half). `paper_display.py`, `display_manager.py`, `scene_io.py`, `block_library.py`, `model_view.py`. Amend the paper-space DM design §7.2. Tier Large.
- [ ] [type:feature] LT2 — Stroke style record on `Geometry2DMixin` (`style: {linetype, weight, start, finish, colour}`; move `"lineweight"` out of per-class `to_dict`) + `copy_style` used by explode/clipboard/join/break/trim/fillet/chamfer/offset/polyline swap + legacy migration (Continuous + By Block, px dropped) + format bump + ribbon/panel current Linetype/Weight (D-L18) [P2] [subject:CAD]
  - Details: concept LD1; D-L17a, D-L18, D-L23b. Until LT3 renders, style is stored + preserved (Continuous only). Guard G9 + style survives every edit tool. Check both serialization paths (`scene_io` + `_capture_network`). `geometry_2d.py`, `scene_tools.py`, `block_explode.py`, `tool_geometry.py`, `model_space.py`, `scene_io.py`. Tier Large.
- [ ] [type:feature] LT3 — `path_walk.py` (arc-length walker + axis phase D-L9/D-L9b) + `stroke_style.resolve_stroke` cascade + `linetype_render.expand` (explicit-geometry dashes, LOD < 2 px, cache) + `StrokeOp` compile (stroke half of hatch HD4 RenderOp) + `BlockInstance.paint` stops forcing cosmetic [P2] [subject:CAD]
  - Details: concept LD-A, LD2, LD3; D-L3, D-L4–D-L6, D-L9, D-L17, D-L23e. Coordinate with HF2 (whichever lands first owns the RenderOp refactor). Reuse gridline dash normalisation for viewport scale. Guards G1, G2, G3, G4, G11. Depends LT1, LT2. Tier Large.
- [ ] [type:feature] LT4 — `repeat` capability + Block Editor repeat frame (shared with HF2 tile frame) + property-panel Pattern list (Dash/Gap/Dot) + live preview + `block_registry.referenced_ids` (style refs) + capability-filtered pickers [P2] [subject:CAD]
  - Details: concept LD1, LD5, LD6; D-L1, D-L12, D-L20, D-L23a. **Mockup-gated** (new widgets: Pattern list, frame). Tooltips on every new control. Guard G8 (bundle/closure half). Depends LT3. Tier Large.
- [ ] [type:feature] LT5 — `end` capability (Fixed / Weight-relative, trim, attach point +X) + end rendering + per-end override + per-end Visible + By Block chain through placements and nested records (placement/nested `style` slot) [P2] [subject:CAD]
  - Details: concept LD1–LD3; D-L5–D-L8b, D-L11, D-L23c/d. End-block authoring mode in the Block Editor (mockup-gated). Guards G4 (nested half), G5. Depends LT4. Tier Large.
- [ ] [type:feature] LT6 — Embedded symbols/text in repeat units (fit-skip, upright, tangent on curves) + `@[key]` attributes in end blocks (System Blocks F3) [P2] [subject:CAD]
  - Details: concept LD3; D-L10, D-L15, D-L19. Guards G6, G7. Depends LT5 + SB1 attributes. Tier Large.
- [ ] [type:feature] LT7 — Ship System > Linetypes (General: Continuous, Hidden, Center, Phantom, Dot, Fire-FP, Sprinkler-S; Piping: Branch, Main, Cross Main, Existing, Drain) + System > End Types (Flat, Round, Square, Arrow, Open Arrow, Arrow 30°, Tick, Dot, Slash, Box, None, Grid Bubble) [P3] [subject:CAD]
  - Details: concept LD5; D-L8, D-L12, D-L22. Add the series to the System Blocks concept. Depends LT6 + SB1b.
- [ ] [type:feature] LT8 — Linetype perf bench + fixes: 2,000 linetyped segments + 400 end blocks, pan/zoom ≤ 16 ms/frame and ≤ 1.5× Continuous [P3] [subject:CAD]
  - Details: D-L21; guard G10. Confirm the bench (scene, interaction, threshold) with the user before any fix; A/B on real data. Depends LT6.
- [ ] [type:design] Instance parameters — per-placement Yes/No + exposed driving dimensions (constraint system) + binding to style properties (D-L11) [P2] [subject:CAD]
  - Details: linetype concept Q11. Revit-family-parameter analogue: e.g. gridline Start Bubble / End Bubble (→ end Visible), Leader Length (→ driving dim). Overlaps `parametric-constraint-system.md` and System Blocks instance attributes. Prerequisite for gridline-from-primitives.
- [ ] [type:design] Gridline built from primitives — system block: primary line + two leaders (definable length) + toggleable bubble end blocks, later jogged (polyline) leaders [P3] [subject:CAD]
  - Details: user end goal (2026-10-02). Extends System Blocks concept (its row "the line/leader/crop stays bespoke"). Depends LT6, LT7, instance parameters. Supersedes the "Display-Manager linetype property for gridlines" half of the Gridline Revit-UX task.
- [ ] [type:design] Pipe as a linear Feature — plan block = one line in a piping linetype (Linetype By Block, Weight By Linetype); "Line Type" enum → Linetype property (Piping series) + migration [P3] [subject:Architecture]
  - Details: D-L22. `pipe.py` (`MAIN_WIDTH_MM`/`BRANCH_WIDTH_MM` width class), `feature-system.md` (no pipe coverage yet). Depends LT7, feature system, instance parameters.
- [ ] [type:feature] Migrate other strokes to linetypes: filled-region outline (D-A7 "line style"), text-box border (replaces `border_line_type` enum), and system items' hard-coded Qt dashes (room, design area, roof inner/ridge, detail marker, elevation datum, reference line) [P3] [subject:CAD]
  - Details: D-L2 follow-up; split per consumer when picked up. After LT3 (LT7 for named system linetypes).
- [ ] [type:feature] DXF import: LTYPE (simple + complex text/shape) → project linetype blocks (deduped) + DXF lineweight → nearest named weight [P3] [subject:CAD]
  - Details: D-L16. `dxf_import_worker.py`, `geometry_import.py` (today: colour only; one uniform lineweight). After LT6.
- [ ] [type:feature] PDF import: dash arrays + line caps → linetypes on Block Editor import; underlays draw dashes as authored [P3] [subject:CAD]
  - Details: D-L16. `pdf_import_worker.py` reads `width` only today. After LT4.

- [ ] [type:feature] Geometric snaps (perpendicular/nearest/tangent, intersection) for ellipse and spline [P3] [subject:CAD]
  - Details: deferred in the 2026-09-08 build, logged in `2d-geometry.md §5` — perpendicular / nearest / tangent on a rotated ellipse (ellipse-segment = quartic) + nearest/perpendicular on a NURBS (numerical projection) + phase-4 intersection participation for both. Named-point snaps (centre/quadrants/endpoints/control-points) already ship. `snap_engine.py`.
- [ ] [type:feature] Vertical / "elevation plane" (section-based) anchoring for 2D geometry [P3] [subject:Architecture]
  - Details: the deferred half of the placement model: draw/anchor 2D geometry on an elevation's vertical cut plane (crosses the current 2D-plan-only authoring contract, `view-relationships §3.1`). Needs its own grill. `geometry_2d.py`, `elevation_scene.py`.
- [ ] [type:feature] Project flat 2D geometry into elevation scenes [P3] [subject:Architecture]
  - Details: flat 2D geometry now has world-Z but isn't projected into elevation scenes. `elevation_scene.py`.
- [ ] [type:feature] Render filled closed 2D shapes in 3D and extrude to solids [P3] [subject:Architecture]
  - Details: the payoff this task lays the foundation for: render filled closed 2D shapes flat in 3D, then extrude to solids (ties into "Generic 3D solid modeling in the Create tab"). `view_3d.py`, `geometry_2d.py`.
- [ ] [type:feature] Line-weight field for the "2D Geometry" Display category [P3] [subject:UX]
  - Details: T10 wired colour/visibility/opacity (mirroring Design Area, which has no weight); add a line-weight field if per-category 2D-geometry weight is wanted. `display_manager.py`, `geometry_2d.py`.
- [ ] [type:feature] Explode Polygon → closed polyline + parametric re-edit polish + HUD "Sides" count field [P3] [subject:CAD]
  - Details: deferred 2026-08-24 — Explode Polygon → closed polyline (free per-vertex deformation) + parametric re-edit polish + "Sides" as a HUD COUNT field (Option A dropped the mixed radius+count schema; sides via ↑/↓ + panel only today). `geometry_2d.py`, `dynamic_input.py`.

## 2D-geometry placement polish (2026-09-16 user batch — remaining)

> Batch 1 (placement selection, centre-rect HUD, Ctrl-resize, Shift+handle, block-editor ghost dot, plan-view crosshair) shipped on `fix/2d-geo-placement-batch1`; Batch 2 (reference-line standard C, two-click text F2, contextual-ribbon redesign E, icon family K, line/polyline ghost fix) on `feat/2d-geo-polish-batch2`; the finite reference/construction line (D) on `feat/reference-line` — all in todo_closed.md. Remaining are the smaller follow-ups filed along the way:

- [ ] [type:feature] Preference to choose the placement cursor style (simple vs accent crosshair) [P3] [subject:UX]
  - Details: user, 2026-09-16 — the accent crosshair is now placement-mode gated (`ui/crosshair`), but the user wants a setting to pick the *simple* OS cross cursor vs the full-viewport accent crosshair. Add a System-Settings UX option; `_resolve_cursor`/drawForeground already branch on `_crosshair_enabled` — thread a style enum. `firepro3d/model_view.py`, `firepro3d/settings/panes.py`, `main.py`. ref: settings-dialog.
- [ ] [type:maint] Single-placement: cover the remaining floor/roof close gestures [P3] [subject:UX]
  - Details: 2026-09-16 single-placement wired the common commit endpoints (2D geo all; wall line/rect; opening; floor rect + polygon close-near-first; roof polygon-close + rect). The floor/roof polygon **Enter** and **double-click** finish gestures do NOT yet call `_end_placement_switch`, so those specific finishes stay in the tool (minor inconsistency; Esc still exits). Wire `_end_placement_switch` into the floor/roof Enter + double-click close paths (`model_space.py` keyPress/doubleClick handlers) for full parity. `model_space.py`.

## 2D-geometry selection dimension readouts

- [ ] [type:maint] Shared dimension-overlay painter for gridline spacing + constraint dims (fixes stale-during-drag) [P3] [subject:Architecture]
  - Details: user-agreed follow-up of the 2D selection-readouts task, 2026-09-24. `Model_View.drawForeground` §3b (constraint dims: `QFont("Consolas", 9)`, raw `:.1f`, ignores units) and §3c (gridline spacing: hard-coded `#0066cc`, 9pt bold) each hand-roll their paint; gridline spacing is recomputed only on selection change so it goes stale during a drag; its editor is a raw 100px `QLineEdit` (`_start_spacing_edit`). Move both onto the readout painter + HUD editor built for 2D primitives. `model_view.py`, `model_space.py`. ref: grid-system §5.4/§5.5, parametric-constraint-system.
- [ ] [type:feature] ALIGN §8 Selection Dimensions for nodes/sprinklers on the shared readout component [P3] [subject:CAD]
  - Details: user-agreed follow-up, 2026-09-24 — `align-placement.md §8` [PROPOSAL] (node spacing dims to pipe-connected neighbours, typed edit slides the node along the pipe). Build on the 2D selection-readout component (label paint, overlay pick ahead of HALO, latched one-field HUD, undo). `model_space.py`, `node.py`, `sprinkler.py`. ref: align-placement §8.
- [ ] [type:bug] Manipulator typed move/resize HUD is unreachable (nothing calls `engage()`) [P3] [subject:UX]
  - Details: 2026-09-24 reuse sweep — `SelectionManipulator._open_hud/_feed_hud/_on_hud_committed` + `Handle.commit_typed` implement the spec'd typed path (selection-manipulator.md §HUD) but only `placement_input_coordinator.py` ever calls `.engage(`; Tab routes to `scene.begin_dynamic_input`, which refuses in select mode. Wire an engage gesture. `selection_manipulator.py`, `model_space.py`. ref: selection-manipulator.
- [ ] [type:feature] Overlap avoidance between selection dimension readouts [P3] [subject:UX]
  - Details: user-agreed follow-up, 2026-09-24 — v1 only hides labels that don't fit their segment/arc; labels from adjacent features can still collide. Add a simple de-overlap pass if it bites in use. ref: 2d-geometry (readouts section).
- [ ] [type:bug] Selection readouts: labels paint over manipulator grips [P3] [subject:UX]
  - Details: 2026-09-24 seam review M7 — readouts are drawn in `Model_View.drawForeground`, after the manipulator's `_HandleItem` grips, so an overlapping label hides a grip that still wins the pick. No overlap at the shipped offsets; revisit if it shows. `model_view.py`, `selection_readouts.py`. ref: selection-mode §15.
- [ ] [type:maint] `Model_Space._on_selection_changed` full-repaints every view on each selection change [P3] [subject:Architecture]
  - Details: 2026-09-24 readouts fix round — pre-existing (gridline spacing / underlay record path) `for v in self.views(): v.viewport().update()` on every selection change, plan + editor scenes. Bench on a large plan drawing; repaint only the gridline-spacing overlay region if it costs. `model_space.py`. Memory: prioritize performance in scene iteration.
- [ ] [type:maint] Extend panel undo coalescing beyond 2D-geometry setters [P3] [subject:Architecture]
  - Details: 2026-09-24 — `Model_Space.deferred_undo_push()` / `request_undo_push()` coalesce a multi-target panel commit into one undo step, but only for setters that route through `Geometry2DMixin._push_undo`; other families' `set_property` that call `push_undo_state()` directly (e.g. gridline) still push one step per target. `property_manager.py`, `gridline.py`, others. ref: property-panel §3.3.

## Ribbon overhaul

- [ ] [type:bug] HUD Enter-commit drops keyboard focus onto the Block Editor tab's close button [P2] [subject:UX]
  - Details: live trace 2026-09-29 (`/todo` scene-tools smoke): after Move committed via numpad Enter in the HUD, `SET_MODE 'move' -> None` and `QApplication.focusWidget()` became `_TabCloseButton` (not the canvas); the next Tab/digits went there until a canvas click (window-level Shift+letter shortcuts still fire). `end_dynamic_input` (`placement_input_coordinator.py`) reclaims focus only when the HUD still held it — the editor being hidden first likely lets Qt pass focus down the chain. Repro with a shown MainWindow + Block Editor (real Enter at the HUD), guard: focus is the visible `Model_View` after every HUD commit. Check every modify tool + placement commit.
- [ ] [type:feature] Feedback when Tab is refused before the tool has an anchor ("Pick base point first") [P3] [subject:UX]
  - Details: live trace 2026-09-29 — Tab at Move step 0 is correctly refused (`schema=displacement requires_anchor=True anchor=None`) but silently, which reads as "Tab doesn't work". Show a status/instruction hint on a refused Tab engage (all anchored schemas).
- [ ] [type:maint] Harden wall-clock perf guards against host noise (offset ghost ≤ 30 ms, handle-snap ≤ 16 ms) [P3] [subject:Testing]
  - Details: 2026-09-29 — even standalone (`-m perf`, test-harness Invariant 8) the offset guard swung open40_near 23–42 ms / closed39_in 21–37 ms with the same-process LineItem baseline itself 3.2–7.8 ms (~700 MB RAM free → paging). Threshold is never loosened; options: more best-of passes / warm-up, a quiet-host precondition check (skip-with-reason when the line baseline exceeds a bound), or a CPU-time measure. Bench before choosing.
- [ ] [type:bug] Copy-to-Level carries the source level onto pasted node copies [P2] [subject:CAD]
  - Details: found 2026-09-25 (G5 review) — `copy_items_to_level` (`model_space.py`) passes node records whose level/ceiling fields override the target level `add_node` just set. Pre-existing. Repro + guard first.
- [ ] [type:bug] Pasting/duplicating/arraying a sprinkler node with a pipe creates a zero-length self-pipe [P2] [subject:Hydraulic Calculator]
  - Details: VC7-proven pre-existing at `2ad947d` (G8 review): `paste_items` node branch recreates a pipe from the node to itself; Array repeats it once per copy → corrupts the hydraulic network. `model_space.py` `paste_items`.
- [ ] [type:maint] `tests/test_no_rotate_knob.py` intermittent teardown access violation (rc 139) [P3] [subject:Testing]
  - Details: crashes after both tests pass in ~1/3 runs at base too; fixture only calls `view.close()` — add `scene.cleanup()` + `deleteLater` per the full-suite crash playbook.
- [ ] [type:maint] Intermittent end-of-chunk access violation in the `tests/test_[e-g]*.py` chunk [P3] [subject:Testing]
  - Details: found 2026-09-28 (batch A dead-code sweep, full chunked suite). All 597 tests pass, then the process dies (0xC0000005, exit 139) at `_pytest/runner.py:147` (`item.funcargs = None`) right after the last test `test_grip_object_limit::test_pane_apply_sets_global_and_qsettings_revert_restores` — a Qt object GC'd at fixture release. Alternating fresh-process A/B: working tree 2/9 crashed (the first two runs), base `698ad01` 0/8. Not attributable (batch A only touched QSettings-isolation lines in test files of that chunk) nor proven pre-existing. Next: bisect by pairing the chunk's MainWindow/scene-building modules with the last test in a child process; check whether a parentless pane/scene from an earlier test is being collected there. Same class as the `test_no_rotate_knob` teardown AV above. `tests/`.
- [ ] [type:maint] End-of-chunk native fault in the `tests/test_[m-r]*.py` chunk — location-dependent (main checkout only) [P3] [subject:Testing]
  - Details: found 2026-09-29 (Offset per-vertex build, VC6/VC7). After the last test (`test_rubber_band_select::test_rtl_drag_is_crossing`) passes, the process faults at interpreter shutdown with no Python frame: at `8576f74` in the MAIN checkout (`D:/Custom Code/FirePro3D`) `0xC0000005` exit 139 4/4 runs; base `2db6b4f` in the main checkout raised `0x80010108` (RPC_E_DISCONNECTED, COM) at the same point but survived (rc 0). The EXACT same code in a fresh worktree under `%TEMP%` ran clean every time (9 runs, base / mixes / full HEAD). So it tracks the checkout location/environment, not the code — suspects: something the main checkout carries that a fresh worktree lacks (path with a space, accumulated per-checkout state), or a COM/OLE (clipboard / drag-drop) object released after QApplication. Sequential tallies are unreliable here (playbook: alternate fresh processes). Sibling of the `[e-g]` end-of-chunk task above; the full-suite crash playbook applies.
- [ ] [type:maint] Whole `tests/test_[s-z]*.py` chunk aborts natively in test_scene_tools.py — reproducible, pre-existing [P2] [subject:Testing]
  - Details: nested-blocks VC6 2026-09-30. Exit 127 in `test_scene_tools.py` (TestBreakAtPoint / TestExtractEdges) 4/4 on 345f1b7 and 3/3 on base 3964a2a when the earlier s-z files share the process (also with test_scene_role excluded); passes split into 3 processes (109 + 98 + 1816 = 2023). Location/GC-timing sensitive (reproduced at base with `gc.set_threshold(900,10,10)`); `_StubScene` fixture leaves a scene↔view cycle and only `view.close()`s. Related to the m-r end-of-chunk fault above.
  - Note 2026-10-01: likely fixed by f766f73 (scene fixture GC fix, same root cause) — the whole s-z chunk ran clean in ONE process at c8ff4f4 (2105 passed, exit 0). Close after one more confirming VC6 run.
- [ ] [type:maint] Real-input offset/array modify tests flake ~1-in-5 in multi-file runs [P3] [subject:Testing]
  - Details: found 2026-09-29 (Offset per-vertex build). `tests/test_offset_item.py` + `tests/test_modify_tools_offset.py` in one process: base `2db6b4f` 1/5 runs failed (`test_offset_sticky_typed_distance_locks_next_pick`, `test_typed_zero_releases_the_locked_distance`), HEAD 1/5 (`test_offset_hud_seeds_the_live_cursor_distance` read 357.3 instead of 30, `test_offset_cursor_near_source_is_not_snapped_onto_it[cursor0-4.0]`); also seen in the m-r chunk: `test_modify_tools_array::test_array_typed_count_is_total[refline]`, `test_move_handle_snap`, `test_polyline_polygon_ctrl` (none reproduce in isolation). The cursor distance looks taken from a different point than the posted move — suspect real OS cursor position / hover events leaking into the shown 800x600 view (cf. the flaky `test_elev_selection_interaction` real-mouse task). Pin the view off the real cursor (or disable mouse tracking during the post) and re-measure.
  - Note 2026-10-01: root cause proven — the user's real OS mouse crossing shown test windows (spontaneous events re-aim tools). `ignore_os_mouse(view)` in `tests/_modify_tools_helpers.py` (6c25766) fixes it for flip/mirror/scale/array/ghost tests. Fix direction: adopt it in `tests/_snap_polish_helpers.make_view` repo-wide and fold the per-file `make_view` wrappers (flip_mirror, array, array_variants) into it.
- [ ] [type:maint] Batch/cache the HALO glow for large transform ghosts (Array Count 200 ≈ 0.7–0.9 s/move) [P3] [subject:Performance]
  - Details: G8 review — 199 `paint_halo_path` calls × 6 strokes dominate; array logic itself ~1 ms. D11 has no copy cap, so this is a perf follow-up, not a blocker. Bench per the deferred-repaint rule before fixing.
  - Note 2026-10-01: Array now draws one merged trace-only `LiteGhostPath` above `ARRAY_GHOST_FULL_MAX` (3b17e94; 50×50 repaint ~5 ms). Remaining: ghost BUILD ~36 ms per cursor move at 50×50; other transforms (Move/Rotate with many items) still pay full HALO.
- [ ] [type:design] Shift+letter modify shortcuts on the 3D and elevation tabs [P3] [subject:UX]
  - Details: G3 review S-2 — on those tabs `_active_scene()` is the hidden plan scene, so Shift+M etc. would act on it (Paper tab is already refused). Decide refuse vs route; amend `scene-tools.md` D2.
- [ ] [type:feature] Scene tools → architecture contextual tabs (wall/room/floor/roof) — milestone 2 of the scene-tools ribbon work [P2] [subject:UX]
  - Details: user, 2026-09-25 — after the 2D-Geometry milestone lands, add the same Copy/Cut/Paste/Duplicate/Move/Rotate/Offset/Array group + Shift+key shortcuts to the architecture contextual tabs. Depends on "Tier-3 paste-path (`paste_items`) unify + copy-but-no-paste bug" (walls/rooms/floors/roofs dropped on paste). Overlaps "Populate contextual tabs with per-entity modify groups". Also covers **plan block instances** (Move/Rotate/Copy/Array on placed blocks — `BlockInstance` needs `manip_rotate`) per scene-tools.md D1/D13. `main.py`, `model_space.py`, `scene_tools.py`.
- [ ] [type:design] Group items (select a set, treat as one) for 2D geometry [P3] [subject:CAD]
  - Details: user, 2026-09-25 "should add a way to group items?" — undecided: relation to blocks (a group vs an anonymous block), selection/edit-in-group semantics, serialization, nesting. Grill before build. `block_system.md` overlap.
- [ ] [type:design] Trim tool surfacing for 2D geometry [P3] [subject:CAD]
  - Details: user, 2026-09-25 "maybe a trim item?" — `scene_tools.py` already has trim/extend; decide after the scene-tools audit whether it only needs ribbon wiring + shortcut or a workflow redesign. Watch the suspected ArcItem trim Y-flip bug. 2026-09-25 audit (`scene-tools.md` §3 + §5.9): targets Line/Circle/Arc only; rect/circle as cutting edge crash (DV3); no polyline/polygon/ellipse/spline; arc keeps the clicked piece (DV7). Open: multi-edge (AutoCAD TRIM) vs single edge; polyline/rect targets.
- [ ] [type:feature] Author the ~46 missing ribbon icons per the new style guide (mockup-gated) [P2] [subject:UX]
  - Details: Floor icon shipped 2026-08-28 with the floor-workflow task. Architecture-tab set shipped 2026-08-28 on `feat/architecture-tab-icons`, grill→mockup-gate→build: authored wall/roof/room/door/window/blank/detail/levels; re-authored `gridline_icon.svg` (was hardcoded `#ffffff` → white-on-white in light theme, violated §4.1); re-authored (thinned) `floor_icon.svg` to match wall depth. Axo 3D family (2:1 dimetric matching floor) for Building elements, 2D symbols for openings/datums; two-token compliant; render-through-loader mockup harness at 54/27px light+dark. Guard tests in `tests/test_icon_theming.py`. Remaining placeholders live in the Create/Sprinkler-Systems/Analyze/Draft/Manage tabs + Tools/Page groups.
- [ ] [type:feature] Populate contextual tabs with per-entity modify groups for wall/room/roof/pipe [P2] [subject:UX]
  - Details: wire type-specific modify tools + the reusable `_build_graphic_override_group` and `_build_placement_group` (both protocol-gated, currently floor/geo2d-only) into the wall/room/roof/pipe/etc. contextual tabs; carry template persistence for wall/roof (floor done). `main.py`, `model_space.py`. ref: ribbon-bar-spec.
- [ ] [type:feature] Wire paper-scene selection into contextual tabs + add Viewport & Sheet Text tabs [P2] [subject:UX]
  - Details: wire the paper scene's selection into the contextual-tab resolver (model-scene-only today), then add the Viewport tab (scale presets / show-border / delete) and a Sheet Text tab (migrate the Draft→Font group into it). `main.py`, `ribbon_bar.py`, `docs/specs/ribbon-bar.md §3.8`. ref: ribbon-bar-spec D9, paper-space §19.4.
- [ ] [type:bug] Restore the radiation dock on startup + wire ImportPane forward-keys read-back [P3] [subject:UX]
  - Details: `restore_settings` restores browser/properties/hydraulics docks but not radiation; GeneralPane persists a default that has no effect until this is wired. `main.py`.
- [ ] [type:feature] Generic 3D solid modeling (extrude/hole/boolean) in the Create tab [P3] [subject:Architecture]
  - Details: generic 3D solid modeling (extrude/hole/boolean) in the Create tab.

## Gridline Revit-aligned UX re-architecture

- [ ] [type:feature] App-wide Y-up display sweep for property panels [P3] [subject:UX]
  - Details: property panels currently show raw Qt Y (down-positive) everywhere (sprinkler/node/etc.); gridline was flipped to up-positive for this branch. Sweep the app to a consistent up-positive display/parse convention. `sprinkler.py`, `node.py`, `property_manager.py`, ….
- [ ] [type:feature] Project angled gridlines into elevation views [P3] [subject:Architecture]
  - Details: currently only exactly-cardinal gridlines project into elevations; angled projection deferred (section-view territory). `elevation_scene.py`.
- [ ] [type:feature] Perpendicular bubble elbow/leader for gridlines [P3] [subject:CAD]
  - Details: jog a bubble off the line with a leader (Revit "add elbow"); per-view leader independence. `gridline.py`, `paper_space.py`.
- [ ] [type:feature] On-canvas rotate handle + Display-Manager linetype property for gridlines [P3] [subject:CAD]
  - Details: angle currently edited in the panel; linetype is fixed dash-dot. `gridline.py`, `model_space.py`, `display_manager.py`.
- [ ] [type:feature] Extend the inference engine to wall/pipe/sprinkler providers and consumers [P3] [subject:Architecture]
  - Details: the engine is generic but only gridlines provide references + only gridline placement/grip consume it; add wall/pipe/sprinkler providers + placement-tool + body-drag consumers, and the deferred guide types (wall-proximity, extension, equal-spacing) per `inferred-dimension-driven-placement.md`. `inference_engine.py`, `wall.py`, `pipe.py`, `model_space.py`.
- [ ] [type:maint] Extract + generalize the Dynamic Input engine into a reusable non-modal HUD (§4) [P2] [subject:Architecture]
  - Details: user, 2026-08-16 — `_DynInput` is a modal `QDialog` nested inside a `model_space.py` method, redefined/instantiated ad hoc per mode; extract to a reusable top-level controller/widget (`dynamic_input.py`), generalize to all placement modes (pipe/wall/arc/rectangle), and (design decision) move from Tab-triggered modal to a live non-modal HUD per §4.3/§4.5; coordinate with the inference engine at the Model_Space seam (typed value overrides snap/inference). Update `inferred-dimension-driven-placement.md §4` in place. `model_space.py`, new `dynamic_input.py`, `model_view.py`. ref: inferred-dimension-driven-placement §4. Lineage: `feat/dynamic-input-hud` D3 scope COMPLETE 2026-08-20 (plan/findings ledger gitignored); shipped one-HUD lifecycle (S1–S3), Line/Rectangle/Circle schemas, polyline, T16 (gridline offset/array), T15 (move + a `GridlineItem.translate` fix), T11 (cycling off Tab, since replaced by Space), T17/T21/T22 (spec §4 rewrite + SPEC-INDEX). HUD clients T18 (wall) 2026-08-24 + T19 (pipe) 2026-09-03 landed (see `todo_closed.md`). Known gap: offset_side/rotate/scale/fillet/chamfer lost their Tab exact-input — needs re-homing.

## Placement-UX overhaul

- [ ] [type:feature] Roof rect placement parity with the base→angle+W→H rect flow [P3] [subject:CAD]
  - Details: 2026-09-23 grill — 2D/wall/floor rects moved to the 3-click ellipse-like flow; roof rect is still a separate 2-click axis-aligned no-HUD flow (`model_space.py` `_move_roof_rect`/`_press_roof_rect`). `model_space.py`. ref: wall-room-floor-system.

- [ ] [type:feature] Merge Line and Polyline into one ←/→ cycle tool [P2] [subject:UX]
  - Details: user, 2026-08-21 — host both under one `draw_line` mode with a line/polyline variant flag (per the `_PLACEMENT_VARIANTS` framework), branching the existing 2-click line vs N-click polyline handlers on it. Remove the placeholder `K` polyline shortcut (`Model_View._TOOL_SHORTCUTS` + Polyline tooltip) once this lands. `model_space.py`, `model_view.py`, `main.py`.
- [ ] [type:bug] HUD-Tab ghost never refreshes for wall/floor/roof placement [P3] [subject:UX]
  - Details: user, 2026-09-05 wall-slice smoke — pre-existing, NOT a slice-10 regression (confirmed identical on `main`). While the Dynamic-Input HUD is engaged during wall placement, Tab-committing a field fires `fieldCommitted` → `_on_dynamic_input_field_committed` → `_preview_from_resolved(resolved)` → `_PREVIEW_DISPATCH.get("wall")` → None → no-op, so the on-canvas ghost sits frozen at its engage-time seed until the placement commits (the mouse ghost works — it routes via `_MOVE_DISPATCH`/real mouse events). Root cause: `_PREVIEW_DISPATCH` has no `wall`/`floor`/`roof` entries, and `_preview_from_resolved` calls `getattr(self,name)(resolved)` with ONE arg while the arch-placement move handlers take `(event, snapped)`. Fix = behavior addition (own grill/design): add a `_preview_from_wall(resolved)` adapter (line → 2nd point; rect-sizing → opposite corner; rect-rotate currently mis-routes to `_preview_rectangle_rotation` when `mode=="wall"` — needs a wall-rect rotate preview) + a `_PREVIEW_DISPATCH["wall"]` entry, then the floor/roof twins. Now that wall placement lives in `WallPlacementController`, the adapter has a clean home. `placement_input_coordinator.py`, `wall_placement_controller.py`, `model_space.py`. ref: inferred-dimension-driven-placement §4.
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
- [ ] [type:feature] Decide on decimal-comma input for dimension/angle fields [P3] [subject:UX]
  - Details: user call, 2026-08-19 — `parse_dimension`/`parse_angle` reject `1,5` as ambiguous against a thousands separator, and `1e3` as a likely typo. The comma is the natural numpad decimal key on European layouts, which matters now the numpad opens the HUD. Grammar's home is `units-and-formatting.md §3.1`. `scale_manager.py`.
- [ ] [type:maint] Narrow `reject_commit()` if it reads noisy [P3] [subject:UX]
  - Details: a refused commit flags every `DIMENSION` field, since appliers refuse on a magnitude and either extent may be at fault on rectangle. Nominate the culprit if that proves annoying in use. `dynamic_input.py`, `model_space.py`.
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

- [ ] [type:feature] Underlay snap glyphs orient to the DXF/PDF segment, not the underlay group [P3] [subject:CAD]
  - Details: follow-up of the 2026-09-29 glyph-orientation task (snapping-engine §9.2 "Known gap"). `_query_underlay_snaps` calls `ctx.check(..., group, ...)` with no segment, so `snap_tangent_deg` falls back to the group's scene rotation. Carry the index geometry's segment (as `source_lines`) on underlay candidates — check the trace path doesn't then light up differently. `snap_engine.py`, `underlay_snap_index.py`.
- [ ] [type:maint] F3 integration test on real keypress [P3] [subject:Testing]
  - Details: QTest.keyClick did not dispatch through QAction shortcut on headless Windows; investigate pytest-qt / qtbot or alternate dispatch.
- [ ] [type:design] Spec session: pipe-with-fitting named targets [P2] [subject:CAD]
  - Details: ref: snap-spec §8.3.
- [ ] [type:bug] Phase-4 intersections on curves use the Bézier control polygon [P3] [subject:CAD]
  - Details: found 2026-09-24 (snap-polish 1b, S4). `snap_engine.py` phase-4 (`_check_geometry_intersections` path-element extraction) intersects raw path elements incl. Bézier control points, so a line crossing an arc/ellipse/spline gets no intersection snap at the true crossing. Same flattening fix as S4 (`toSubpathPolygons`). Also: DXF curve control points emitted as endpoint snaps. ref: snapping-engine §6.1.
- [ ] [type:bug] Block-compiled text drops its border frame + fill [P3] [subject:CAD]
  - Details: found 2026-09-24 (snap-polish 1b, S6) — unconfirmed: a TextItem's frame border/fill never reach the compiled block render_ops (only glyph outlines). Reproduce first. `block_definition.py`, `text_item.py`. ref: block-system.
- [ ] [type:feature] Snap trace outlines a TextItem's box when text is the snap source [P3] [subject:UX]
  - Details: found 2026-09-24 (snap-polish G2 review S2). `paint_snap_indicator` trace (snapping-engine §9.2.1) has no TextItem branch, so snapping to a text corner/mid/centre shows the marker but no box trace. Add a branch drawing the rotated frame polygon. `snap_engine.py`.
- [ ] [type:feature] ALIGN crossings dwell-acquirable [P3] [subject:CAD]
  - Details: found 2026-09-24 (snap-polish 1b, S5) — the dwell machine is fed only the real snap result, so an ALIGN crossing (align_intersection) can't itself be acquired. `align_controller.py`, `model_space.py`. ref: align-placement.
- [ ] [type:bug] `_align_snap_dict` id collision for source-less points [P3] [subject:CAD]
  - Details: found 2026-09-24 (snap-polish 1b, S5) — points with no source item get `hash(snap_type)` as id, so two of the same type collide (acquire/hysteresis identity). `model_space.py`.
- [ ] [type:design] Roof placement has no governing spec section [P3] [subject:Docs]
  - Details: found 2026-09-24 (snap-polish Task 13). Roof polygon/rect placement (click flow, close → RoofDialog, Ctrl, HUD absence — `_move_roof` publishes no placement state) is described nowhere; forge a section in `wall-room-floor-system.md` (orphan-gate on next roof touch).
- [ ] [type:bug] Spline endpoint snaps include off-curve interior control points [P3] [subject:CAD]
  - Details: found 2026-09-24 (snap-polish Task 13). `snap_engine._collect` SplineItem branch emits every `grip_points()` control point as `endpoint`; interior control points of a Bézier/NURBS lie off the curve → snaps to empty space. Emit only the true curve ends (+ maybe on-curve knots). `snap_engine.py`. ref: snapping-engine §5 note 11.
- [ ] [type:feature] ALIGN suspended while SNAP is off — hide acquired markers + dim the ALIGN pill [P3] [subject:CAD]
  - Details: from the 2026-09-26 design grill (ratified, `align-placement.md` §6.1). Engine gate already suspends ALIGN when F3 is off; build the visible half: (1) gate the `+` acquired markers in `Model_View.drawForeground` on SNAP as well as ALIGN — do NOT clear `AlignController.acquired` in `toggle_snap` (hide, restore on F3 on); (2) ALIGN footer pill keeps its checked (F11) state but renders dimmed with tooltip "ALIGN suspended — SNAP (F3) is off" while SNAP is off — wire `snapToggled` into `_update_guides_indicator` / `footer.set_align_on`. P4 first step: probe that a dynamic-property selector (e.g. `[suspended="true"]`) combined with `:checked` actually renders on the footer `QToolButton` (repolish on change; verify by pixel sampling — unstyled pseudo-states render as base). Guards (VC3): acquire a point, F3 off → marker not painted + pill dimmed/tooltip; F3 on → same marker back. Needs a user smoke (visual).
- [ ] [type:maint] Flaky `test_elev_selection_interaction::test_empty_click_deselects` under real mouse input [P3] [subject:Testing]
  - Details: found 2026-09-25 (snap-polish final suite, 1/5337; same tree passed the previous run, 3/3 isolated, passes in the full 83-file prefix; no elevation/halo/conftest code touched by the batch). Mechanism proven: the elevation press is HALO-committed (commits the current `halo_item()`), so a hover over the gridline arriving between the test's `_move((5,5))` and its press — e.g. the real OS cursor over the suite's visible window — keeps the gridline selected. Harden: have the test (or `ElevationView` press) re-pick HALO at the press position when it differs from the last hover point; consider whether the live press should also re-pick (a real press always follows a hover at the same point, so likely test-only). `tests/test_elev_selection_interaction.py`, `elevation_view.py`, `halo_selection.py`.
- [ ] [type:bug] Cursor snap runs on every middle-button pan step (pan lag) [P3] [subject:Performance]
  - Details: found 2026-09-24 (snap-polish G4 RR bench, pre-existing). During a pan, each replayed mouse move runs `get_effective_position` (full `find()`, O(n) on the NoIndex scene) + repaint: ~170 ms/step at 2k items headless. Skip snapping while a pan is in progress (middle button held / view panning flag). Bench first on a real file. `model_view.py`, `model_space.py`.
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
- [ ] [type:design] Spec session: auto-populate sprinkler placement algorithm [P3] [subject:Architecture]
  - Details: NFPA 13 density/area curve interpolation, polygon decomposition into rectangles (scanline), branch-line direction detection (1/2/3+ pipe logic), `_walk_branch()` algorithm, wall-proximity 2× rule, edge cases (L-shaped rooms, concave rooms, dead-end branches, multiple design areas). `auto_populate_dialog.py`, `design_area.py`.
- [ ] [type:design] Spec session: annotations [P3] [subject:Architecture]
  - Details: NoteAnnotation (MText-like word-wrap, bold/italic, alignment), DimensionAnnotation (two-point + offset witness lines). `annotations.py`. (The hatch half — HatchItem, SVG pattern loader, Qt brush patterns — was superseded 2026-10-01 by the Hatch & Fill concept: `docs/specs/hatch-and-fill.md` + slices HF1–HF9.)

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
- [ ] [type:feature] Optional dedicated centre move-handle (general) [P3] [subject:UX]
  - Details: move is interior-drag today (grab anywhere in the frame), no visible centre handle by design. PARTIAL 2026-09-10: RectangleItem now shows a centre move grip in BOTH states (rotated = parametric grip 8; unrotated box-native = `manip_box_extra_handles()` appended to the rigid set). The general case (multi-select group centre, paper viewport/text, other rigid-fallback selections) is still interior-drag only — generalize via a rigid CENTRE/MOVE handle if wanted app-wide. `selection_manipulator.py`.
- [ ] [type:feature] Elevation edit undo + datum-extent persistence [P3] [subject:Architecture]
  - Details: split out of U5 Leg B (2026-09-14). Elevation has no undo stack — gridline/datum annotation-extent grip edits commit directly (parity, no undo). Add an undo path (own stack or a bridge to the model stack) so elevation extent edits are undoable; also make the datum's horizontal extent persist (gridline extent already persists via `_gridline_z_overrides`/`to_dict`; datum is session-only). `elevation_scene.py`, `elevation_manager.py`.
- [ ] [type:feature] manip_handles for 2D-geometry-in-elevation (rides Leg B frame) [P3] [subject:Architecture]
  - Details: split out of U5 Leg B. When 2D geometry can be placed/anchored in elevation (see "Vertical / elevation plane anchoring for 2D geometry" + "Project flat 2D geometry into elevation scenes"), give those items `manip_handles()` so they ride the elevation `SelectionManipulator` frame Leg B built. `geometry_2d.py`, `elevation_scene.py`.
- [ ] [type:feature] U5 Leg C — 3D-scene selection + handle providers [P2] [subject:Architecture]
  - Details: pick-ray/actor selection + handle providers for the 3D view. `view_3d.py` is a SPEC-INDEX **orphan** — forge a 3D-view selection governing spec first (orphan gate). Depends on plan-view selection-mode (Leg A, done). `view_3d.py`. ref: selection-manipulator §Unification U5, "Spec session: 3D view selection mode".
- [ ] [type:bug] Ctrl+click over the manipulator frame is swallowed (no additive toggle there) [P2] [subject:UX]
  - Details: PRE-EXISTING, surfaced by the U5 Leg A seam review. The manipulator interior-press guard (`model_space.py` ~4267) routes any press over the frame to the manipulator BEFORE `_press_select_item`, excluding only Shift — so a Ctrl+click additive/toggle landing on the frame never reaches selection once something is selected. Can't simply add Ctrl to the exclusion (a Ctrl+press on a resize handle starts Ctrl-from-centre scale). Needs a design pass distinguishing Ctrl+click-additive (frame interior) from Ctrl+press-on-handle-scale. `model_space.py`, `selection_manipulator.py`.
- [ ] [type:feature] HALO "pick from list" for dense stacks [P3] [subject:UX]
  - Details: deferred from U5 Leg A (part of the user's HALO design). When Spacebar-cycling through many overlapping candidates gets tedious, offer a pick-from-list dropdown at the cursor. `model_space.py`, `model_view.py`. ref: selection-mode §4 (HALO).
- [ ] [type:maint] HALO hover on huge drawings: spatial index for the model scene [P2] [subject:Performance]
  - Details: 2026-09-24 bench (Block Editor, Sample.pdf): the HALO `scene.items(box)` pre-filter is ~50 ms/move @ 20k primitives (~200 ms+ @ 85k) because Model_Space is `NoIndex`; identical on main, px ranking adds only 3–7 ms. NoIndex was chosen deliberately — needs its own perf spike (BspTreeIndex vs a HALO-side cache) on real data. `model_space.py`, `halo_selection.py`.
- [ ] [type:bug] Remaining `views()[0]` zoom reads (render + tool tolerances) [P2] [subject:UX]
  - Details: found 2026-09-24 while fixing hit widths. In the app `views()[0]` is the vestigial never-shown view frozen at m11 = 1.0 (snapping-engine.md §14.4), so these are world-unit, not screen-constant: `displayable_item.py` + `hatch_patterns.py` hatch tile size, `wall.py` hatch spacing, `pipe.py` endpoint dots, `scene_tools.py` pick tolerances (3 sites). Route through `view_scale.scene_view_scale` (render sites may prefer `painter.deviceTransform()`).
- [ ] [type:bug] Intermittent: test_elev_selection_interaction::test_empty_click_deselects [P3] [subject:Test-infra]
  - Details: failed 1 of 3 identical runs of a 601-test battery right after the 2026-09-24 HALO merge (gridline stayed selected after a posted click at viewport (5,5) post-`fit_to_screen`); passes alone, in every file-pair bisect, and in 2 re-runs. Unexplained — not proven pre-existing. Suspects: window exposure/geometry timing (fit depends on the real viewport size) or the now-15 px HALO aperture reaching a bubble near the corner. Reproduce with repeated battery runs before changing anything.
- [ ] [type:maint] Large-selection select_items cost (~8–10 s @ 85k primitives) [P3] [subject:Performance]
  - Details: 2026-09-24 bench: Ctrl+A / whole-drawing band = one `selectionChanged` now, but the per-item `setSelected` loop + manipulator rebake over 85k items still costs ~8–10 s headless. Profile the listeners (manipulator `_top_level_only`/bounds union, property panel) before optimising. `halo_selection.py`, `selection_manipulator.py`.
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
- [ ] [type:maint] Route `main.py` `sceneModified.connect(model_browser.refresh)` through `schedule_refresh` [P3] [subject:Architecture]
  - Details: the direct connection rebuilds the whole tree synchronously on every scene change (duplicate work: `set_scene` also connects `sceneModified→schedule_refresh`), and a synchronous rebuild mid-`itemChanged` emission `clear()`s the tree item Qt is still processing (re-entrancy landmine; didn't crash in repros but is fragile). `main.py`, `model_browser.py`.
- [ ] [type:feature] Ability to select/access individual items within an underlay group [P3] [subject:CAD]
  - Details: future feature to interact with sub-items of an imported underlay.
- [ ] [type:bug] Missing-underlay messages point users to a Relink action that doesn't exist [P3] [subject:UX]
  - Details: found 2026-09-26 (paper/underlay doc fixes). The load warning (`scene_io.py`, "Missing Underlay Files") says "Use right-click → Relink in the browser tree", and the canvas placeholder label (`underlay_controller.py`) says "Missing — right-click to relink" — but neither the browser (Remove only) nor the canvas offers Relink; it lives only in the Underlay Manager (`underlay-workflow.md` §5.4). Fix the two strings to point at Underlay Manager → Relink… (or add the action where they point). Repro: open a project whose underlay file was moved.

## Code Health & Architectural Debt (from 2026-04-29 gap analysis)

- [ ] [type:maint] Model_Space decomposition — continue the domain-controller slices [P1] [subject:Architecture]
  - Details: current size ~7,829 lines; next slice = room (reads scene-side `_walls`), then floor/roof/gridline. Governing spec `docs/specs/model-space-architecture.md`. Grilled contract: pure core out / side-effect shell stays; four binding seams (universal scene-graph mutation, undo-snapshot glue, dual-serialization unified to one `NetworkCodec`, ordered idempotent `set_mode`→`clear()` teardown); extracting a concern converts `main`/`view` bare-attr reach-ins into public scene methods same-commit. Slices 1–11 landed (tool-geometry+constraint-solver, SceneTools composition, NetworkCodec unify, underlay controller, pipe/node controller, sprinkler-workflow controller, placement-input coordinator, 2D-geometry drawing, arc+polygon, wall-placement, feature-placement) — see todo_closed.md. `main.py` (MainWindow, #2 monolith) is a sibling task with its own spec (below). Why it matters: the single biggest bug surface in the codebase (two context menus, two view paths, focus loss, z-order, ALIGN scope/first-point/angled-extension bugs). `model_space.py`, `scene_tools.py`, `scene_io.py`, `tool_geometry.py`, `constraints.py`. ref: model-space-architecture.
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

- [ ] [type:bug] Block Editor DXF import of a full ellipse mirrors its rotation (30° arrives as 150°) [P3] [subject:CAD]
  - Details: found 2026-10-01 by the scene-tools P1 batch 1b arc-angle census (probe `probe_ell.py` in that session's scratchpad). `dxf_import_worker.py` full-ellipse branch emits `"rotation": -rotation` (Y-flip for the scene), then `geometry_import.py` (~:182) feeds that Y-down angle to the Y-up `EllipseItem`. Fix at one hop only; `test_geometry_import.py:94` pins the ellipse rotation if the fix lands in `geometry_import`. Check periodic DXF splines too (import drops the spline `closed` flag). Convention: `project_rotation_conventions_yup_vs_qt`.
- [ ] [type:feature] DWG import: paper-space viewport compositing [P2] [subject:CAD]
  - Details: Revit DWGs place building geometry and gridline/dimension annotations at separate model-space coordinates, composited via paper-space viewports. Current import shows raw model space where they're physically separated. Need to read viewport clip boundaries + transforms and remap block coordinates to overlay annotations with building geometry. `dxf_preview_dialog.py`, `dwg_converter.py`.
- [ ] [type:maint] Multi-layout import extraction is O(all model space) per layout switch [P2] [subject:CAD]
  - Details: selecting any layout re-walks all ~49,628 model-space entities and explodes every INSERT/HATCH/DIMENSION regardless of viewport (`_entity_in_viewport` returns True for them), producing ~388k explosion geoms filtered down to ~7.5k for a single sheet. Two improvements: (A) extract model space once, filter per layout — cache the unfiltered geoms and apply only the cheap viewport-bounds filter on each layout switch instead of re-extracting; (B) bbox-prefilter blocks — test INSERT/HATCH/DIMENSION extents via `ezdxf.bbox.extents([ent], fast=True)` (generous margin) and skip exploding those outside the viewport. B is the dominant per-layout win and is localized; A helps multi-layout switching. `dxf_import_worker.py:_entity_in_viewport`, `dxf_preview_dialog.py:_DialogExtractWorker._run_inner`, `dwg_converter.py`.

## Paper Space Follow-Ups (from 2026-05-11 implementation)

## Title block template editor

> Follow-ups from the 2026-09-15 title-block bundle (`feat/titleblock-ansi-d-default`, Tasks A–F). Governing specs: `titleblock-template-system.md`, `settings-dialog.md`, `ui-design-system.md`.

- [ ] [type:feature] Dedicated "set default title block" control [P3] [subject:UX]
  - Details: today the `.fpdt` link (`titleblock_template_uuid`) is set only as a side effect of "Save current project settings as default" (it captures the current project's embedded template uuid). Add an explicit picker (choose which library template new projects inherit) — e.g. in the Title Block editor or Project Settings. ref: titleblock-template-system DD-23. `titleblock_editor.py`, `settings/`.
- [ ] [type:maint] House-theme the E3 data-migration prompt [P3] [subject:UX]
  - Details: `GeneralPane.migrate_prompt_if_needed` uses a plain `QMessageBox` (Copy/Move/Leave). Replace with a house-styled `themed_*` / `HouseDialog` prompt for chrome parity. `settings/panes.py`. ref: settings-dialog §4.5b.
- [ ] [type:feature] TopTabs richness: per-tab icons + status badges [P3] [subject:UX]
  - Details: `ui_kit.TopTabs` shipped with the core look only (2026-09-15). Follow-ups from the reference `DIALOG_TABS_SPEC.md`: (a) 13px per-tab icons (needs 4 tab icons authored, mockup-gated); (b) modified-dot + warn-badge behaviors (a warn dot on a tab whose page has a validation issue, wired to the editor's `_show_warnings`/validate state). `ui_kit.py`, `titleblock_editor.py`, `theme.py`. ref: ui-design-system Tab-style catalog.
- [ ] [type:maint] Adopt TopTabs in the other top-tab dialogs [P3] [subject:UX]
  - Details: migrate remaining bare-`QTabWidget` house dialogs onto `ui_kit.TopTabs` as they're touched (e.g. Block Editor). Reference `underlay_manager` kit also carries a full `SectionDialog` shell (rail+tabs+header+footer) if a deeper unification is later wanted. ref: ui-design-system Tab-style catalog.
- [ ] [type:bug] Revision date cell needs a double-click (not single) to open the picker [P3] [subject:UX]
  - Details: user, 2026-09-15 smoke (accepted as follow-up). The RevisionsDialog Date column (`_RevisionDateDelegate` over `QTableWidget`, `AllEditTriggers`) opens the `QDateEdit` on double-click / current-changed, not on a single click into an unselected cell (first click selects, second opens). Investigate the edit-trigger/selection interplay or a delegate `editorEvent` single-click-to-edit. `paper_space.py` (`RevisionsDialog`, `_RevisionDateDelegate`).
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

- [ ] [type:feature] Remote area selection mechanism [P3] [subject:Hydraulic Calculator]
  - Details: no way to designate the most-demanding remote area for hydraulic design. Currently uses all design sprinklers equally. Need UI to mark remote area + solver to validate it as most demanding. `hydraulic_solver.py`, `design_area.py`.
- [ ] [type:feature] Paper space Phase 2 implementation [P2] [subject:Architecture]
  - Details: annotations layer, label/thin-line scaling, layer overrides per viewport, DXF export. Phase 1 (sheet management, sheet views, PDF print) is partial. See `docs/specs/paper-space.md` Phase 2. `paper_space.py`.

## Documentation Gaps (from 2026-04-29 gap analysis)


## Codebase Audit — Census 2026-09-09 (see audit/FINDINGS.md)

> F1–F3 done 2026-09-09 (moved to todo_closed.md). F4 REJECTED — vulture's "unused variables" were required Qt slot/override parameters (`currentCellChanged` slots need row/col/prev_row/prev_col; `focusNextPrevChild` is a QWidget override) — removing them breaks the Qt wiring. Not dead code.

- [ ] [type:maint] [cleanup:delete] Investigate + remove 3 unused classes [P3] [subject:Cleanup]
  - Details: @60% — `FSVisibilityDialog`, `LoaderWorker` (loading.py), `LoadingBar` (loading_bar.py). Grep instantiation/dynamic-access first; EXCLUDE ui_kit.* (unbuilt-by-design). Import-smoke after. (audit F#6, risk:med, effort:M)
- [ ] [type:maint] [cleanup:delete] Investigate + remove 16 candidate-dead functions [P3] [subject:Cleanup]
  - Details: @60% (see audit/vulture.txt) — e.g. `geometry_intersect.circle_circle_intersections`, `align_engine.point_along_ray`, `block_library.list_library`, `hatch_patterns.{refresh_patterns,is_builtin,make_hatch_tile}`, `underlay_cache.delete_cache`, `manip_math.transform_angle_deg`. Grep caller+test+dynamic-access per function before deleting. (audit F#5, risk:low, effort:M)
- [ ] [type:maint] Sweep the remaining `self`-capturing lambda connects in `main.py` against test-harness Invariant 6 [P3] [subject:Architecture]
  - Details: follow-up of the 2026-09-23 GC access-violation fix, which converted only the proven paper-scene `indexChanged` / `add_text_mode_toggled` lambdas to bound methods. Others remain (`levelsChanged`, project-browser `activateModelSpace`/`sheetSelected`, QAction/QShortcut `triggered`/`activated`, …) — none proven to emit during destruction. Convert any whose sender can outlive the MainWindow (parentless / Python-owned) to bound methods; the rest are low-risk children. `main.py`, `docs/specs/test-harness.md` Invariant 6.
- [ ] [type:maint] `test_text_inline_routing.py` real-input tests flake in full-suite runs only [P3] [subject:Testing]
  - Details: block polish 2026-09-23 — two DIFFERENT tests failed once each in 14-min full runs and pass 3/3 in isolation: `test_ctrl_c_ctrl_v_while_editing_leave_scene_untouched` (system clipboard) and `test_drag_inside_selects_text_not_moves` (posted mouse drag). Likely window-activation/focus or shared-clipboard state leaking from an earlier test. Suspect the same lingering-MainWindow family as the module-singleton fixture item below. ref: `test-harness.md`.
  - Sighting 2026-09-29 (readout/glyph batch VC6): `test_lost_release_mid_session_does_not_hijack_next_handle_drag` failed once in the s-z chunk (main checkout), passed 3/3 alone and in a same-change positive-control chunk in a `%TEMP%` worktree; base s-z chunk clean once — not yet proven pre-existing.
- [ ] [type:maint] `test_snap_curve_accuracy.py` real-input tests flake as a whole file (pre-existing at base) [P3] [subject:Testing]
  - Details: found 2026-09-29 (readout/glyph batch VC7). At base `1965c66` in a `%TEMP%` worktree the isolated file failed 4 tests at once (`test_circle_endpoint_lands_on_circle[0.25/1.0]`, `test_arc_outside_cursor_lands_on_arc`, `test_ellipse_outside_cursor_lands_on_curve`) on ~1 run in 8; alternating base/HEAD A/B showed the same rate either side. All use `_drag_line_end_to` real-input drags — same class as the real-input offset/array flake. Likely window activation/focus; check the drag helper's exposure/activation wait.
- [ ] [type:maint] Module-singleton MainWindow fixtures never actually delete the window [P3] [subject:Testing]
  - Details: found 2026-09-23. `close()` + `deleteLater()` (+ `processEvents()`) does not dispatch DeferredDelete at that loop level, so the window lingers until an unrelated later test's pump flushes it — its destruction-time signals then fire mid-way through another module (why native crashes *move* with selection) and windows/VTK contexts accumulate. Fix direction: a shared conftest teardown helper that closes, `deleteLater()`s and `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)` + `gc.collect()` deterministically; migrate the ~10 `_main_window_singleton`/`_mw` fixtures. `tests/conftest.py`, test-harness.md Invariant 6 fixture note.


- [ ] [type:bug] Snap engine's segment iterator omits a closed polyline's closing edge [P3] [subject:CAD]
  - Details: found 2026-10-01 (scene-tools P1 plan drafting, Part B). `SnapEngine._iter_geometry_segments` (feeds phase-4 intersections and ALIGN geometry segments) skips the seam edge of a closed polyline, so no intersection / ALIGN segment comes from it. The batch's `axis_picker` adds the edge itself as a workaround; fix at the iterator and drop the workaround. Repro first. `snap_engine.py`, `axis_picker.py`, `snapping-engine.md` §6.1.
- [ ] [type:maint] Polar array: re-dim when the variant changes (skipped items stay dimmed) [P4] [subject:UX]
  - Details: scene-tools P1 plan C-10 — `start("array")` dims the whole transformable set before a variant is chosen; Polar then copies only the rotatable non-Node subset, so skipped items stay dimmed during the gesture (restored on exit). Re-dim in the variant apply-fn. Minor D11 deviation. `modify_tools_controller.py`, `transform_ghost.py`.
- [ ] [type:maint] `Model_Space.copy_selected_items` is test-only after the context-menu Copy change [P4] [subject:Cleanup]
  - Details: scene-tools P1 plan C-13 — after slice 10.3 both context menus start the base-point pick; copy-to-level uses `copy_items_to_level`, so `copy_selected_items` keeps only test callers (`test_block_seams.py`, `test_gridline_array_offset.py`). Retire it with those tests rewritten (VC5), or keep as a documented internal API.
- [ ] [type:feature] Flip / Mirror / Scale for block instances (persisted mirror flag + scale pose) [P3] [subject:CAD]
  - Details: 2026-10-01 grill (scene-tools P1 batch) excluded block instances from Flip, Mirror and Scale (skipped with a status count) because `BlockInstance` has no mirror/scale pose field. Needs: persisted flag/scale (both serialization paths), render cache, snap collectors, paper/PDF output. `block_instance.py`, `block-system.md`, `scene-tools.md`.
- [ ] [type:feature] "Closed" property toggle for splines and polylines (open/close after drawing) [P3] [subject:UX]
  - Details: 2026-10-01 grill (scene-tools P1 batch) — closing is only possible while drawing (click-near-first); a periodic closed spline can't be reopened and an open one can't be closed later. Property-panel checkbox on spline + polyline; spline toggles periodic ⇄ clamped. `geometry_2d.py`, `property-panel.md`, `2d-geometry.md`.
  - Note 2026-10-01: `SplineItem.get_properties()` shows no closed/periodic row today (Degree reads 3 on a periodic spline) — include it.
- [ ] [type:feature] Space flips the arc side in the Center and Start arc variants (not only End Points) [P1] [subject:CAD]
  - Details: user, 2026-10-01 smoke of the scene-tools P1 batch. Today Space toggles minor ↔ major only in the End Points variant at step 2 (`Model_Space.cycle_placement_ambiguity`, `GeometryDrawingController._toggle_arc_ep_major`); Center/Start always sweep CCW from the start to the cursor (`_preview_from_arc` / `_commit_draw_arc_at` normalise span > 0), so the other side needs a re-pick. Proposed: Space at the span step toggles CCW ↔ CW — preview, `arc_span` HUD sign and commit follow; reset per placement, like End Points. `geometry_drawing_controller.py`, `model_space.py`, `2d-geometry.md` §4.
- [ ] [type:bug] DWG underlays never snap and are never a mirror axis — "DWG Underlay" tag missing from `_UNDERLAY_TAGS` [P2] [subject:CAD]
  - Details: found 2026-10-01 (scene-tools P1 Slice 4 re-review RR-3; proven at 7766316). Also `snap_engine.py` keeps a second local underlay-tag tuple in `_iter_geometry_segments` (~:1219, used ~:1330) beside `_UNDERLAY_TAGS` (~:500) — collapse onto `_is_underlay_group`, then add the DWG tag once. `snap_engine.py`, `axis_picker.py`, `snapping-engine.md`.
- [ ] [type:bug] `paste_items` cannot create walls, rooms, floors, roofs or design areas (Paste/Duplicate/Array silently drop them) [P2] [subject:CAD]
  - Details: found 2026-10-01 (scene-tools P1 Slice 7 review I3; root at 7f486f5). Array now refuses them up front via `Model_Space._paste_accepts` (e90e83a); Paste/Duplicate still drop them. `model_space.py` `paste_items`, `scene-tools.md`.
- [ ] [type:maint] Tests write the autosave `recovery.FPD` into the real home folder (`~/.firepro3d/autosave`), hanging later MainWindow fixtures on the Recover dialog [P2] [subject:Testing]
  - Details: found 2026-10-01 (scene-tools P1 execution). The APPDATA monkeypatch misses it; runs were isolated with USERPROFILE/HOME. Fix: conftest-level redirect of the autosave dir (or HOME) for every test. `tests/conftest.py`, `autosave`, `test-harness.md`.
- [ ] [type:bug] Delete mid-pick leaves Move/Rotate/Flip/Mirror armed with a ghost of the deleted item (Enter then reports "0 item(s)") [P3] [subject:UX]
  - Details: found 2026-10-01 (scene-tools P1 Slice 5 review F2; Move/Rotate behave the same at base). Drop deleted items from the tool's targets/dim list and refuse/end when none remain. `modify_tools_controller.py`.
- [ ] [type:bug] Break on an arc can create a zero-span arc (click on an endpoint, or both circle break points coincide) [P3] [subject:CAD]
  - Details: found 2026-10-01 (scene-tools P1 Slice 1 review M-2, pre-existing). `scene_tools.py` `_break_item` / `_break_at_point`. Pick up with 'Surface the remaining scene tools'.
- [ ] [type:bug] Trim on an arc uses the first intersection, not the one nearest the click [P3] [subject:CAD]
  - Details: found 2026-10-01 (scene-tools P1 Slice 1 review M-3, pre-existing). `scene_tools.py` `_handle_trim_click` (`int_angles[0]`).
- [ ] [type:bug] Tangent snap fires on a click already on a circle (visual 30°/120° clicks land at 25.14°/115.14°) [P3] [subject:CAD]
  - Details: found 2026-10-01 (scene-tools P1 Slice 1 guard authoring), unverified. Investigate whether tangent should yield to nearest/on-curve when the cursor is on the curve. `snap_engine.py`.
- [ ] [type:bug] Origin snap beats the close ring when vertex 0 is 8–12 px from (0,0) — the click adds a vertex at the origin instead of closing [P3] [subject:CAD]
  - Details: found 2026-10-01 (scene-tools P1 Slice 9 review S1; Slice 2 × Slice 9 interaction). Repro: spline v0 at (40,0), zoom 0.25. `geometry_drawing_controller.py` `close_hit`, `snap_engine.py` origin priority band.
- [ ] [type:bug] A typed HUD point near vertex 0 closes a floor but adds a near-duplicate vertex on polylines and splines [P3] [subject:UX]
  - Details: found 2026-10-01 (scene-tools P1 Slice 9 review S3, not from this batch). Decide one rule (route typed points through `close_hit`?). `geometry_drawing_controller.py`, `model_space.py`.
- [ ] [type:maint] Room manual close/pop and shift-click floor vertex delete keep their own 8 px literals — route through `CLOSE_HIT_PX` / `close_hit` [P4] [subject:Architecture]
  - Details: found 2026-10-01 (scene-tools P1 Slice 9; `model_space.py` `tol = 8.0` ×2 + `vtx_tol`).
- [ ] [type:bug] Closed DXF SPLINEs with non-uniform knots or weights still draw a stray tail (Block import and underlay) [P3] [subject:Import]
  - Details: found 2026-10-01 (scene-tools P1 Slice 8 review M1). DD7 maps only uniform cubic periodic splines; the fallback `_bspline_path` evaluates the full unclamped knot range. `geometry_2d.py`, `geometry_import.py`, `dxf_import_worker.py`.
- [ ] [type:bug] `_parse_count` accepts `1e3`/`1_000`, and typing `inf` raises OverflowError inside `editingFinished` [P3] [subject:UX]
  - Details: found 2026-10-01 (scene-tools P1 Slice 6 fix round, pre-existing). Move COUNT format/parse onto `ScaleManager` with the shared `_NUM` grammar (like `format_factor`), add the units-spec §3 row. Also `ScaleManager._ANGLE_RE` re-spells the number grammar (accepts a leading `+`). `dynamic_input.py`, `scale_manager.py`, `units-and-formatting.md`.
- [ ] [type:bug] Tiny Scale factors scale non-uniformly (Circle floors at 1 mm, Arc 0.01 mm, Ellipse 0.5×0.5) [P4] [subject:CAD]
  - Details: found 2026-10-01 (scene-tools P1 Slice 3/6 reviews). Refuse up front when any item would hit its floor, or document. `geometry_2d.py` radius floors, `modify_tools_controller.py` Scale.
- [ ] [type:maint] Perf guard `test_offset_real_mouse_move_is_fast` fails intermittently under load (open40 44–77 ms vs 30 ms bar) [P3] [subject:Testing]
  - Details: found 2026-10-01 (proven at 890e43e and 004f575); passed in the quiet VC6 perf run at c8ff4f4. Quote the LineItem baseline next to the verdict, or make the bar relative. `tests/test_modify_tools_offset.py`.
- [ ] [type:maint] Mode-badge guard: derive `_dispatched_modes` from the live ribbon registries too; guard the `sender()` branch of `_mode_signal_scene` [P4] [subject:Testing]
  - Details: found 2026-10-01 (scene-tools P1 Slice 10 review). `main.py`, `tests/test_modify_tools_ribbon.py`.
- [ ] [type:maint] Spec drift found at the scene-tools P1 Account (pre-existing): dead `applies-to` paths, red-marker retirement vs origin snap, snapping-engine status header [P3] [subject:Docs]
  - Details: found 2026-10-01 (Account review B1–B3). (1) `align-placement.md` applies-to lists `firepro3d/main.py` (it is repo-root `main.py`); `underlay-workflow.md` lists untracked `firepro3d/underlay_manager_theme.py`. (2) `parametric-constraint-system.md` D4 (proposal) retires the Block Editor red origin marker, which the `origin` snap kind now uses as a source — reconcile before building D4. (3) `snapping-engine.md` frontmatter says `status: current` but its opening blockquote still calls it a spec-only north-star. Also: `docs/contributing/adding-tools.md` walkthrough (old mixin + mouse dispatch) is stale beyond the 2026-10-01 banner — rewrite or retire; `MainWindow._on_confirm_requested` Yes/No else-arm has no emitter since the legacy Mirror retired — prune or keep (scene-tools §7).
- [ ] [type:feature] Surface the remaining scene tools (Extend, Break, Fillet, Chamfer, Stretch, Merge, Join, Explode) [P3] [subject:CAD]
  - Details: 2026-09-25 grill D14 — unreachable after the ribbon removal; as-built defects in `scene-tools.md` §1.1/§3/§6 (RefLine → Line on break/join). Decide per tool: surface (+ shortcut + HUD), or delete with coupled tests (VC5). Depends on the arc-angle bug. Scale + Mirror split out 2026-10-01 into their own line.