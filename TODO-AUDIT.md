# TODO-AUDIT — open-task consolidation proposal (DRAFT for review)

_Generated 2026-09-02. PROPOSAL ONLY — no task file was edited. Verify before applying._

## Summary (counts: 4 drop / 6 merge-clusters / ~205 keep)

- **DROP: 4** high-confidence (3 inline-signalled + verified-shipped, 1 pure-pointer stub)
- **MERGE: 6** clusters (~15 tasks collapse to 6)
- **KEEP: everything else**, including all legitimately-deferred P3/post-MVP/Deferred-OUT items.

Conservative bias: when a task had any residual scope beyond what shipped, it stayed KEEP with a note.

---

## DROP (4)

- **Underlay Manager dialog chrome revamp** (section: Tasks / Import Underlay dialog) —
  `- [ ] **Underlay Manager dialog chrome revamp** — ✅ **superseded by the shipped chrome-match above.** [type:Task] [P2] [subject:UX]`
  Reason: **inline self-declared superseded** ("✅ superseded by the shipped chrome-match above"). The parent "Underlay Manager chrome-match + import polish" node is a done-parent; its follow-ups (lines 50-54) are the live remainder. This top-level restatement is pure dead weight. Highest-confidence DROP.

- **Viewport resize = crop not scale** (section: Paper Space Follow-Ups) —
  `- [ ] Viewport resize = crop not scale — dragging viewport handles should move the crop box, not change physical size. Scale should only change on explicit definition. `paper_space.py` [type:Task] [P2] [subject:CAD]`
  Reason: **SHIPPED, verified in source.** `firepro3d/paper_space.py:_resize_on_paper` (≈L1008-1062) is documented as "the single home for the crop×scale resize … For scale>0 this changes `crop_rect` at fixed scale (Revit crop model)". Handle drags change `crop_rect` at fixed scale; scale only changes via `commit_viewport_edit(..., scale=s)` (explicit panel/dialog). Exactly the requested behavior.

- **Wire import DPI / import-mode preferences** (section: Tasks / Ribbon overhaul) —
  `- [ ] **Wire import DPI / import-mode preferences** — **→ folded into the PDF Import Polish cluster (item 1, Import section).** `dxf_preview_dialog.py`, `preferences_dialog.py` [type:Task] [P3] [subject:UX]`
  Reason: **inline "folded into" pointer** + **VERIFIED SHIPPED.** `firepro3d/preferences_dialog.py` has the PDF-import pane wiring `import/pdf_dpi` + `import/pdf_import_mode` QSettings keys — `_dpi_combo` (72/150/300), `_mode_combo`, plus save/restore (L730-808). The DPI/import-mode preference is live and seeds the import dialog. Fully done.

- **Batch multi-page PDF import** (section: Underlay Workflow Follow-Ups) —
  `- [ ] Batch multi-page PDF import [ref:underlay-spec§2.2] — **superseded 2026-08-28: reframed to single-page selection-by-name (PDF Import Polish cluster item 3); batch NOT wanted (import one sheet at a time).** [type:Backlog] [P3] [subject:CAD]`
  Reason: **inline "superseded … batch NOT wanted"** — explicitly retracted as a direction and reframed into a shipped cluster. No residual scope.

---

## MERGE (6 clusters)

### Cluster 1: Hydraulic results as a separate paper-space view
Tasks:
- `- [ ] Hydraulic results as separate view — velocity color-coding should create its own view rather than overriding plan view colors, so it can display independently in paper space. `hydraulic_solver.py`, `model_space.py` [type:Task] [P2] [subject:Hydraulic Calculator]` (Paper Space Follow-Ups, L343)
- `- [ ] Replace velocity color-coding with pipe hf heatmap — normalize friction loss to system max; color pipes green/orange/red by relative hf. `model_space.py`, `hydraulic_report.py` [ref:hydraulic-spec§11.2,D4] [type:Task] [P2] [subject:Hydraulic Calculator]` (Hydraulic Solver Follow-Ups, L237)
→ Proposed single task: "**Hydraulic-results view (separate view + hf heatmap)** — create a dedicated results view (not a plan-view color override) so it displays independently in paper space; color pipes by friction loss normalized to system max (green/orange/red hf heatmap) instead of the current velocity coloring. `hydraulic_solver.py`, `model_space.py`, `hydraulic_report.py` [ref:hydraulic-spec§11.2,D4, project-hydraulic-results-view] [type:Task] [P2] [subject:Hydraulic Calculator]"
Rationale: Both describe the same feature per the `project_hydraulic_results_view` memory ("velocity color-coding should be its own view, not override plan colors"). One is the container (separate view), the other the content (hf metric). NOT implemented (only 3D radiation heatmap exists in `view_3d.py`). Merge, don't drop.

### Cluster 2: Populate contextual tabs + generalize the reusable placement/override groups
Tasks:
- `Populate each contextual tab with its type-specific modify tools.` (Ribbon overhaul, L123)
- `**Generalize the Graphic Override group to other entity types** … wire it into wall/room/roof/pipe/etc. contextual tabs (feeds L122 "populate contextual tabs").` (Revise floor placement, L74)
- `**Adopt the reusable `_build_placement_group` in other contextual tabs** — … wire it into wall/floor/roof/etc. contextual tabs (the broader "populate contextual tabs" follow-up).` (2D geometry, L117)
- `**L105/L35 wall+roof remainder** … Wall/roof still need contextual placement groups + template persistence.` (Revise floor placement, L75)
→ Proposed single task: "**Populate contextual tabs with per-entity groups** — wire type-specific modify tools + the reusable `_build_graphic_override_group` and `_build_placement_group` (both protocol-gated, currently floor/geo2d-only) into the wall/room/roof/pipe/etc. contextual tabs; carry template persistence for wall/roof (floor done). `main.py`, `model_space.py` [ref:ribbon-bar-spec] [type:Task] [P2] [subject:UX]"
Rationale: Four tasks that all self-reference each other as "feeds/the broader … follow-up" for the single "populate contextual tabs" effort. They are one work item split across filing sessions.

### Cluster 3: Paper-scene contextual-tab parity (viewport/sheet-text tabs)
Tasks:
- `**Ribbon contextual Viewport tab** … Depends on the partial contextual-tab machinery being wired to the **paper** scene's selection (see the "Paper-scene contextual parity" item …)` (Paper-space AHJ, L13)
- `**Paper-scene contextual parity** — contextual tabs are model-scene-driven only; wire the paper scene's selection to the same resolver (Viewport/Sheet Text tabs).` (Ribbon overhaul, L124)
- `Migrate Draft→Font group into a "Sheet Text" contextual tab.` (Ribbon overhaul, L130)
- `Migrate the Draft→Font group into a "Sheet Text" contextual tab` also echoed by `**Migrate Draft→Font group into a "Sheet Text" contextual tab.**` — same line.
→ Proposed single task: "**Paper-scene contextual tabs** — wire the paper scene's selection into the contextual-tab resolver (model-scene-only today), then add the Viewport tab (scale presets / show-border / delete) and a Sheet Text tab (migrate the Draft→Font group into it). `main.py`, `ribbon_bar.py` [ref:ribbon-bar-spec D9, paper-space §19.4] [type:Task] [P2] [subject:UX]"
Rationale: The Viewport-tab and Sheet-Text-tab tasks both explicitly block on the one "paper-scene contextual parity" prerequisite. Collapse the prerequisite + its two consumers into one deliverable (keep the P2 of the highest member).

### Cluster 4: Model_Space decomposition — the umbrella is filed twice
Tasks:
- `**Decompose `model_space.py` (~11.3k lines)…**` (Tasks section, L85) — the user-raised umbrella with slice progress ledger.
- `**Model_Space decomposition** (in progress on `refactor/model-space-slice1…`)` (Code Health & Architectural Debt, L304) — the governed umbrella with the same slice roadmap.
→ Proposed single task: keep ONE umbrella (recommend the L304 governed entry that cites `docs/specs/model-space-architecture.md` and carries the live slice-4b state + follow-ups), fold L85's narrative rationale into it as background. Keep all child slice follow-ups (Underlay slice, 4b items, main.py sibling) under the single umbrella.
Rationale: Two open umbrella tasks track the identical decomposition effort with duplicated slice roadmaps. One should be the canonical home; the other's unique content (the "why it matters / bug-surface" rationale) merges in. NOT a drop — the work is active.

### Cluster 5: main.py Preferences/Settings consolidation
Tasks:
- `Continue folding remaining scattered settings into the Preferences dialog … + the future user-profile settings layer …` (Ribbon overhaul, L131)
- `**Unified Settings dialog** … consolidate scattered settings … into one Settings dialog instead of separate dialogs.` (Dynamic-input follow-ups, L162)
- `**Normalize the legacy snap dialog's QSettings store** … consider retiring the redundant Manage "Snap Settings" button (now in Preferences).` (Ribbon overhaul, L128) — partial overlap (the snap-dialog normalization is the concrete first step of the consolidation).
→ Proposed single task: "**Consolidate settings into the Preferences dialog** — fold remaining scattered/legacy dialogs (Project Info, Import/Export, Snap/OSNAP incl. normalizing the legacy snap dialog's bare `QSettings()` store and retiring the redundant Manage 'Snap Settings' button, Inference, Display) into the one Preferences dialog; keep the swappable source for the future user-profile layer. `main.py`, `preferences_dialog.py` [type:Task] [P3] [subject:UX]"
Rationale: L131 and L162 are the same "one settings home" ask; L128's snap-store normalization is its concrete sub-step (keep the QSettings-key-mismatch bug detail as a sub-bullet). Consider keeping L128 separate if the reviewer prefers to track the bug independently — flagged.

### Cluster 6: DimensionEdit adoption sweep (migrate ad-hoc numeric inputs)
Tasks:
- `**Migrate hand-rolled numeric inputs to `DimensionEdit`** … `array_dialog.py`, `calibrate_dialog.py`, `main.py` (~2302/2309) parse dimensions ad hoc …` (Dynamic-input follow-ups, L161)
- `**Migrate hydraulic-report/water-supply etc.**` — (no separate task; only L161 exists) — see note.
→ Proposed: this is actually a SINGLE task already (L161). Listed here only to record that the reviewer asked to watch for DimensionEdit duplicates — none found beyond L161. NOT a merge; KEEP L161 as-is.
Rationale: Included for completeness of the duplicate-hunt; withdraw this cluster (no true duplicate).

---

## KEEP (summary)

All remaining ~205 open tasks are KEEP. Notable groupings verified as still-valid:

- **Paper-space AHJ (section B):** rich-text runs, text-box placement polish, leaders, border property, DisplayManager text category, WallSegment cosmetic-pen bug — all still-open; no shipped-signal found.
- **Hydraulic calc (section C):** storage-protection criteria, hose inside/outside split, domestic-water demand — all real NFPA gaps, KEEP.
- **Deferred OUT of MVP / Post-MVP order:** section-view subsystem (explicitly DEFERRED, spec stays proposal), one-line riser (P3 post-MVP), selection-mode hub, doc reorg — KEEP per constraint (do NOT reverse intentional deferrals).
- **Snapping / View-Relationships / Code-Review-Audit spec sessions:** ~20 "Spec session: X" backlog items — each names a DISTINCT subsystem (elevation scene, detail view, 3D pipeline, roof, door/window, floor openings, property manager, display system, scene tools, constraints, annotations, auto-populate, layer management, drafting overrides, cross-view selection, paper-viewport overrides, elevation/3D selection mode). No two cover the same ground → NO merge. KEEP all.
- **Underlay/Import follow-ups:** the sub-bullets under the done-parents (levels reconciliation, DRY consume, font warning, custom-scale persistence, duplicate-drops-fields, calibration tol, cache-key mismatch, DXF flatten bench, DWG viewport compositing, multi-layout O(n) perf) are all distinct live bugs/tasks. KEEP.
- **U2–U5 selection-manipulator unification + Handle model:** live P1 architecture roadmap. KEEP.
- **model_space slice follow-ups (4b, underlay slice, tier-2/3, paste bugs):** live. KEEP.
- **Documentation Gaps (L376-380):** the "update stale metrics" tasks cite outdated LOC numbers, but the TASK (refresh the docs) is still valid — KEEP; do NOT drop just because the numbers themselves are stale (that IS the work).
- **Dead-code tasks (layer_manager.py removal L296, git-tracked sprinklers.json retire, SceneTools thin wrappers):** VERIFIED still-present. `firepro3d/layer_manager.py` exists and `LayerManager` is only self-referenced (docstring usage; never instantiated elsewhere) → the removal task is still actionable. KEEP.

### Nearly-dropped but KEPT (flagged)
- **"Fix latent point-size ~2.4× PDF over-sizing" (L25)** — scoped-down 2026-07-22; the viewport-title/placeholder part shipped, but the note says "remaining pt text lives only in the no-template fallback chain" → residual scope remains. KEEP (do not drop the whole task on a partial-ship).
- **"Full OSNAP visual treatment in import dialog" (L178)** & **"Wire import DPI" (L126, DROPPED)** — both "folded into cluster" pointers, but L178 explicitly says "the real gap is the duplicated `drawForeground` painter … file separately if wanted" → residual scope → KEEP. Only L126 (pure fold-in, no residual) is dropped.
- **"Underlay Manager dialog chrome revamp" vs its follow-ups** — dropped the umbrella (superseded), KEPT the 5 concrete follow-ups (font warning, DRY consume, FramelessShell spec, dark-contrast, etc.).

---

## Uncertain / needs user decision

1. **Cluster 5 (settings consolidation)** — L128's snap-QSettings-normalization carries a concrete key-mismatch bug (`QSettings()` vs `QSettings("GV","FirePro3D")`). If you'd rather track that bug independently of the big consolidation ask, keep L128 separate and merge only L131+L162.
2. **Cluster 4 (model_space decomposition double-umbrella)** — both entries are live and content-rich; this is a documentation-hygiene merge, not a scope change. Confirm which entry becomes canonical (recommend the governed L304 one).
3. **"Full OSNAP visual treatment in import dialog" (L178)** — left as KEEP because it names a residual gap (duplicated `drawForeground` painter drift) beyond the shipped source-item trace. Confirm you still want the DRY-painter consolidation; if not, it can join the DROP list.
