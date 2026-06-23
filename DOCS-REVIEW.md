# FirePro3D — Documentation Review & Reorg Proposal
*Code-verified audit of all 65 docs under `docs/` (13 curated + 14 specs + 38 superpowers artifacts). 69 agents, every load-bearing claim checked against `firepro3d/` source. 2026-06-22.*

## Executive summary

**The single most important finding: your best documentation is unpublished, and your published documentation is the most stale.**

- The mkdocs site nav ships only `index`, `getting-started`, `architecture/` (8 pages), `contributing/` (3 pages), and the auto-generated `reference/`. That's the **thin** layer — and it carries the **most factual errors** (a removed layer system still taught in 6 docs, fictional APIs in the how-tos, wrong file extension, wrong Z-order).
- `docs/specs/` (14 docs, **not in nav**) holds the **richest, most code-faithful** knowledge in the repo — `snapping-engine`, `view-relationships`, `sprinkler-system-components`, `hydraulic-solver-and-reporting`, `wall-room-floor-system`. Several are *more accurate than the curated architecture pages they overlap*. Nobody browsing the site can see any of it.
- `docs/specs/` secretly mixes **two genres**: living "current-behavior" contracts (publish these) and forward-looking "design-for-unbuilt-feature" specs (`section-view-subsystem`, `selection-mode`, `inferred-dimension-driven-placement`, `paper-space`). Both wear identical `Status: Approved` headers, so a reader can't tell "how it works" from "the plan."
- `docs/superpowers/` (38 dated specs+plans) is build history — valuable provenance, but it's living inside the user-facing docs tree.

**Three systemic drift mechanisms** (root causes, not instances):
1. **Removed-feature lag** — the layer system was deleted; 6 curated docs still teach `user_layer`. The `display_mode` Level feature was removed; `level-system.md` still documents it.
2. **Resolved-vs-open inversion** — multiple specs list divergences/open-questions as pending that are *already shipped* (sprinkler D2/D3/D9, wall §13, constraints Q3/Q4), and a few describe *unbuilt* targets as current (hydraulic 3-tab report + heatmap).
3. **Hand-copied volatile facts** — line numbers, LOC counts, method counts are embedded everywhere and rot instantly.

**No advertised feature is vaporware** — hydraulics, thermal radiation, 3D, DXF/DWG/PDF import, multi-floor, snapping are all real and substantial. But two published claims are false and should be fixed first: (a) "DXF import/**export**" — export does not exist (ezdxf is read-only); (b) `getting-started.md` certifies a **broken install** — `requirements.txt` omits `pyvista`/`pyvistaqt`/`vtk` which `view_3d.py` hard-imports at startup, so a clean clone crashes on launch.

## The five highest-leverage fixes (do these regardless of reorg)
1. **Sweep `user_layer` out of all 6 curated docs** (`display-system`, `io`, `entities`, `guide`, `adding-entities`, `level-system`) — the layer system is gone.
2. **Pick ONE Z-order source of truth** (`view-relationships.md §7.3`, which `constants.py` already defers to) and reconcile `display-system.md`, `guide.md`, `overview.md` to it — they currently invent ranges and omit the real runtime elevation-based ordering.
3. **Fix `getting-started.md` + `requirements.txt`** so a clean install actually launches; document ODA File Converter for DWG.
4. **Fix the two false published claims** (`index.md` DXF "export"; the install path).
5. **Replace fictional APIs in the how-tos** (`_snap_or_raw`, `_geom_to_item()`, `SnapEngine.snap()`, `apply_for_level()`, `Model_Space.py` capitalization) — a contributor copying these today gets `AttributeError`s.

---

*The four detailed analyses below are the full, code-verified findings: (1) consolidation map across 12 topic clusters, (2) gap analysis / additional needed docs, (3) reorganization proposal with migration table + nav + anti-drift convention, (4) project scope/shape synthesis + contradiction map + the questions we'll use to validate scope.*

---


# SESSION DECISIONS — grill, 2026-06-22

These decisions were reached in the grill session and **refine the proposals below** (especially Part 3). Where they conflict with Part 3, these win.

1. **Audience = future-self + the AI loop.** Docs are optimized for accuracy + anti-drift, not publishing polish. The end-user gaps (User Guide, shortcuts, glossary) and mkdocs nav polish are **deprioritized**.
2. **Docs are the AI's leash**, not a reference manual — they hold the intended architecture in front of the AI so a local fix doesn't cause cross-subsystem breakage. This makes **accuracy safety-critical** (a wrong spec actively misdirects), which re-elevates the audit's "resolved-listed-as-open" and "proposal-as-current" findings from cosmetic to dangerous.
3. **Two layers, kept** — `architecture/` = cross-subsystem ripple map; `design/` specs = per-subsystem contracts. Justified functionally (blast-radius map vs. local invariants), not for browsing.
4. **Rule A — one fact, one home.** Architecture links to specs; never restates owned facts; no line/LOC counts. (C-vs-A is moot since the AI maintains both.)
5. **Binding via the `/todo` skill (now implemented):** **Ground** (load governing specs before coding, Phase 1b) → **Forge** (blocking spec-creation + `/grill-me` for orphan subsystems) → **Account** (re-audit + stamp specs at wrap-up). Indexed by `docs/specs/SPEC-INDEX.md` + `applies-to` frontmatter.
6. **Frontmatter `status / last-verified / verified-commit / applies-to`** is load-bearing (powers grounding + orphan detection). Status vocabulary `current | proposal | partial | deprecated` replaces the meaningless "Approved/Draft".
7. **Backfill = lazy-only.** Orphans (thermal radiation, 3D view, `.fpd` I/O) get a spec on first touch, not proactively. Accepted exposure until then.
## Scope/shape decisions (resumed grill, 2026-06-23)

8. **Product shape = a fire-protection-engineering SUITE.** Core deliverable / MVP = **Sprinkler Design** (layout → NFPA 13 hydraulics → plotted AHJ package). Thermal radiation = the **first additional suite module** (built, kept, NOT MVP); smoke modelling etc. are future modules.
9. **The MVP deliverable is the full AHJ package produced IN-TOOL** (drawings + calcs). In-tool drawing output is the job → **paper-space sheet export (PDF/print) is the #1 MVP-blocking item.** Hydraulic calc export already ships; drawing export does not.
10. **Paper-space MVP scope** (most machinery already exists — sheets, plan+elevation viewport hosting, B&W/line-weight print overrides, ANSI title blocks): the only real builds are the **plot step** (sheet→PDF/print) and **sheet-space annotations** (notes/legend). Plan dimensions already render through viewports.
11. **Sections:** cardinal elevations (already host on sheets) + riser cover it → **arbitrary-angle section-view subsystem DEFERRED** (stays a proposal; the big rewrite is avoided).
12. **Riser:** MVP interim = cardinal elevation + imported standard detail. **Auto-generated one-line riser diagram from topology = post-MVP roadmap** (a real differentiator).
13. **Hydraulic report → 3-tab** (Summary / Node Summary / Graph); schedules to CSV only. Build the **Node Summary**. Spec §9 is the *target* → mark `status: partial`, keep D7 as an **active** divergence (do NOT rewrite §9 to match the 5-tab code).
14. **Layers: "levels not layers" is committed and permanent.** Safe to purge `user_layer` from the 6 docs; rename `DEFAULT_USER_LAYER → DEFAULT_ANNOTATION_GROUP` (it's only an annotation category now); document `hidden_layers` as distinct DXF source-layer visibility.
15. **Selection-mode = #1 post-MVP** (full hub: hover + crossing rubber-band + Tab disambiguation + label-only click). Spec kept as the contract.
16. **Architecture posture:** MVP-focus; **let the platform/module seam emerge** from the second real module (don't abstract a platform now). Adopt the **arm's-length-module** invariant immediately (modules read the model, emit results; never entangle into `Model_Space`). `Model_Space` decomposition stays pain-driven.

**Banked this session:** `/todo` skill (ground/forge/account hooks), `spec-template.md` frontmatter, `docs/specs/SPEC-INDEX.md`, project `CLAUDE.md` governance section. **Not yet executed** (future todos): the directory reorg/moves, the drift fixes (`user_layer` sweep, Z-order reconcile, fictional-API fixes, install fix).

---

# PART 1 — CONSOLIDATION MAP (overlap clusters)

# Overlap & Consolidation Map — FirePro3D Docs

## Cluster 1: Snapping / OSNAP Engine

**Member docs**
- `docs/specs/snapping-engine.md` (canonical spec, actively maintained, code-faithful)
- `docs/specs/osnap-toolbar.md` (per-type toggle UI spec + as-built)
- `docs/specs/inferred-dimension-driven-placement.md` (unbuilt, depends on snap engine)
- `docs/superpowers/plans/2026-04-07-snap-engine-items-1-3-10.md`
- `docs/superpowers/plans/2026-04-08-osnap-ux-pair.md`
- `docs/superpowers/plans/2026-04-08-snap-primitive-unit-tests.md`
- `docs/superpowers/plans/2026-04-10-snap-engine-cluster.md`
- `docs/superpowers/plans/2026-05-22-hybrid-snap-preview.md` (superseded)
- `docs/superpowers/plans/2026-05-23-lazy-underlay-snap.md`
- `docs/superpowers/plans/2026-05-23-snap-engine-fallback-for-import-dialog.md`
- `docs/superpowers/plans/2026-06-22-osnap-toolbar.md`

**Canonical:** `docs/specs/snapping-engine.md` (engine), with `docs/specs/osnap-toolbar.md` kept as the dedicated UI sibling it deliberately defers to.

**Merge:** Collapse the F3/toolbar/persistence subsections of `snapping-engine.md` (§9.4–§9.6, §13 Q1) into one-line pointers to `osnab-toolbar.md` to remove the changelog-over-spec duplication.

**Archive (all implemented, design captured in the two specs):** all 7 superpowers plans above. `2026-05-22-hybrid-snap-preview.md` is explicitly *superseded* by `2026-05-23-lazy-underlay-snap.md` and should be archived first.

**Salvage before archiving:**
- `_FACE_COLLAPSE_SCENE_EPS=3.0` thin-wall suppression heuristic + the deferred "derive threshold from view transform" fix (only in `2026-04-07` plan) → add one line to `snapping-engine.md` §8.
- The data(4)-present-vs-absent dual-path snap contract (from the two `2026-05-23` plans) → already in `snapping-engine.md` notes 7–8; verify, then archive.

**CONTRADICTION FLAG:** `snapping-engine.md` §4 catalog / §5 matrix note 6 / roadmap item 6 all claim **ArcItem produces NO tangent candidates ("bug")**, but `snap_engine.py:1127-1142` implements arc tangent. The spec is stale-wrong here — flip those three to done/works.

---

## Cluster 2: Underlay / Import I/O (DXF / DWG / PDF)

**Member docs**
- `docs/architecture/io.md` (curated, published) ← architecture home
- `docs/specs/underlay-workflow.md` (Rev 7, living subsystem spec, code-faithful)
- `docs/superpowers/specs/2026-05-20-multi-layout-dxf-import-design.md`
- Plans: `2026-04-13-underlay-workflow.md`, `2026-04-13-underlay-refresh-fix.md`, `2026-04-24-underlay-polish-cluster.md`, `2026-04-24-pdf-vector-and-snap-bugs.md`, `2026-05-13-underlay-caching.md`, `2026-05-14-dwg-import.md`, `2026-05-15-import-dialog-progress-bar.md`, `2026-05-20-multi-layout-dxf-import.md`, `2026-05-22-batched-underlay-rendering.md`, `2026-05-24-layout-aware-reload.md`

**Canonical:** `docs/specs/underlay-workflow.md` (detailed subsystem reference) feeding `docs/architecture/io.md` (published summary). Two-tier, both kept.

**Merge:** Distill the code-confirmed durable sections of `underlay-workflow.md` (data model, path resolution, DXF/DWG/PDF pipeline, ODA flow, caching, batched rendering, snap index) into `io.md` with cross-references; have `io.md` link the spec for depth.

**Archive (all implemented):** all 10 plans + the `2026-05-20` superpowers design (design fully captured in `io.md` lines 122–148).

**Salvage before archiving:**
- "Vector PDFs re-extract from source on reload; transform re-applied from persisted params" + "snap engine requires tagged QGraphicsItemGroup" (from `2026-04-24-pdf-vector-and-snap-bugs.md`) → `io.md`.
- "data(5) raw-geom cache write avoids large-DXF UI freeze; raster PDFs not cached" (from `2026-05-13-underlay-caching.md`) → `io.md`.
- "deferred-invisible-items approach tried and rejected for repaint cost → grid index" decision log (from `2026-05-22-batched-underlay-rendering.md`) → `io.md`.
- MTEXT `ps_to_ms` text-size scaling + QFontMetricsF alignment offsets (from `2026-05-20` design) → `io.md`.

**CONTRADICTIONS FLAG (io.md is wrong vs. code AND vs. the underlay spec):**
1. **File extension:** `io.md:12` says `.fp3d`; rest of repo (incl. `io.md:122` `.fpd.cache/`) and `underlay-workflow.md` use **`.fpd`**. Self-inconsistent.
2. **Cache version:** `io.md:122` says **3**; code is `_CACHE_VERSION = 4`.
3. **Fabricated API:** `io.md` (lines 99, 164) and `pdf_import_worker.py:7` docstring reference `_geom_to_item()` which **does not exist** (real path: `_on_dxf_finished`/`_append_geom_to_path`/`_build_pen_cache`).
4. **Version migration:** `io.md:78-80` describes legacy feet/inch + `elevation_mm` migration that **has no code**.

---

## Cluster 3: Paper Space / Sheets / Title Blocks

**Member docs**
- `docs/specs/paper-space.md` (full vision parent spec, mostly aspirational)
- `docs/superpowers/specs/2026-05-10-paper-space-viewports-design.md` (Phase-1 subset, shipped)
- `docs/superpowers/specs/2026-05-12-paper-space-display-manager-design.md` (print overrides extension, shipped)
- `docs/superpowers/plans/2026-05-10-paper-space-viewports.md`
- `docs/superpowers/plans/2026-05-12-paper-space-display-manager.md`
- (touches `docs/specs/view-relationships.md`, `docs/architecture/display-system.md`)

**Canonical:** `docs/specs/paper-space.md` — but it must absorb the as-built reality. **No published architecture page exists for paper space** (only an incidental mention in `level-system.md`); create `docs/architecture/paper-space.md` only once the subsystem stabilizes.

**Merge:** Fold the as-built data model from `2026-05-10-paper-space-viewports-design.md` into the parent (`§5` Sheet/SheetViewData dataclasses), fix the `§12` inventory, and add an "as-built vs planned" section. Then demote the subset design to historical.

**Archive:** both `2026-05-10` and `2026-05-12` plans (implemented). Archive the `2026-05-10-paper-space-viewports-design.md` *after* its data model is folded into the parent.

**Salvage before archiving (NOT in any curated doc):**
- Temporary-mutation viewport rendering (save→apply→`scene.render()`→restore-in-finally) + safety rationale; real **non-cosmetic mm pens** vs model-space cosmetic pens; B&W factory default; SVG-retint + Fitting-wrapper gotchas (from the `2026-05-12` spec/plan) → `docs/architecture/display-system.md` (new "Paper-space overrides + line weights" section).
- Drag MIME contract `application/x-firepro3d-view`; ANSI B/D hand-measured `FIELD_LAYOUTS` vs programmatic fallback (from `2026-05-10` design) → future paper-space architecture page.

**CONTRADICTIONS / STALENESS FLAG in `paper-space.md`:** `§2/§12` "763 LOC scaffold" (actual 1666); class `PaperViewport` (actual **`SheetViewport`**); `firepro3d/user_layer_manager.py` (does not exist → `layer_manager.py`); `firepro3d/default titleblocks/` (actual repo-root `./default titleblocks/`); `§5.2` `SheetViewData.scale:str`+`crop_override`+`layer_overrides` (actual `scale:float`, none of the others). Also `view-relationships.md` still uses the old `PaperViewport` name and the `paper_space.py:507` render line (actual `:444`).

---

## Cluster 4: Hydraulics / Analysis

**Member docs**
- `docs/architecture/analysis.md` (curated, published)
- `docs/specs/hydraulic-solver-and-reporting.md` (rich, code-accurate algorithm spec)
- `docs/superpowers/plans/2026-04-29-hydraulic-correctness-cluster.md`
- (overlaps `docs/specs/sprinkler-system-components.md` §3.3 solver interface)

**Canonical:** `docs/specs/hydraulic-solver-and-reporting.md` for the verified algorithm core; promote a condensed version into the published `docs/architecture/analysis.md`.

**Merge:** Mine the corrected solver/formula/HydraulicResult/equivalent-length sections of the spec into `analysis.md`. Cross-link `sprinkler-system-components.md` §3.3 (solver interface boundary) rather than restating.

**Archive:** `2026-04-29-hydraulic-correctness-cluster.md` (all four H1–H4 fixes shipped).

**Salvage before archiving (NOT in curated `analysis.md`):**
- NFPA 13 Table 22.4.3.1.1 equivalent-length data + `FITTING_TYPE_MAP` decisions (wye→45° elbow; vertical→horizontal; cap/"no fitting"→0).
- "Supply node's own fitting excluded from equivalent length."
- H4 uncalibrated-scale hard-block rationale; H2 hose-stream-in-supply-check behavior.
→ all to `analysis.md`.

**CONTRADICTIONS FLAG:**
1. **`analysis.md` HydraulicResult is stale** — omits `required_node_pressures` and `hose_stream_gpm` (both exist in `hydraulic_solver.py:49,51`). Add them or use an mkdocstrings directive.
2. **Internal contradiction inside the spec itself:** `§9` documents a 3-tab report and `§11.2` a friction-loss heatmap as *current*, but `§12` correctly lists D7 (5→3 tabs) and D4 (velocity→hf heatmap) as **open P2**. Code still has 5 tabs + velocity coloring. The body lies about shipped features. Move §9/§11.2 targets into the D4/D7 divergence rows.
3. Spec Verification Checklist says "5 guards + 2 new validations"; only 1 (loop detection) survived (D8 withdrawn).

---

## Cluster 5: Grid System / Gridlines

**Member docs**
- `docs/specs/grid-system.md` (consolidated subsystem spec, mostly implemented)
- `docs/superpowers/plans/2026-04-10-grid-system-architecture.md`
- (Align participation overlaps Cluster 7; elevation overlaps Cluster 8)

**Canonical:** `docs/specs/grid-system.md`; distill verified facts into published `docs/architecture/entities.md`.

**Archive:** `2026-04-10-grid-system-architecture.md` (implemented; rationale lives in the spec).

**Salvage:** legacy serialization key-rename map + `bubble_overshoot=length*0.06` + 90°-CCW perpendicular-vector convention → ensure they survive as `gridline.py` comments (low value).

**CONTRADICTIONS FLAG in `grid-system.md` (phantom/never-built details):**
- `§4.1` lists `_bubble1_visible/_bubble2_visible` and `_user_layer` fields that **do not exist** (visibility read off child bubbles; `user_layer` removed repo-wide).
- `§4.4` serializes `user_layer` (not emitted) and shows `display_overrides` always-present (only when non-empty).
- `§9.2` claims old-format detection by a `'type':'grid_line'` key — code detects by **absence of `'p1'`** (uses `start`/`end`).
- `§7.2` dialog column table omits the real **Locked** column (7 cols, not 6).
- Align mover stated as `set_perpendicular_position()`; code uses `move_perpendicular`; lock status string differs.

---

## Cluster 6: Display / Visibility / Theming

**Member docs**
- `docs/architecture/display-system.md` (curated, published)
- `docs/architecture/theming.md` (curated, published — distinct: QSS/tokens)
- `docs/superpowers/specs/2026-05-10-visibility-display-cluster-design.md`
- `docs/superpowers/plans/2026-05-10-visibility-display-cluster.md`
- `docs/superpowers/specs/2026-05-12-paper-space-display-manager-design.md` (also Cluster 3)
- (`view-relationships.md` §7.3/§8 hold the best Z-order content)

**Canonical:** `docs/architecture/display-system.md`. Keep `theming.md` **separate** (no real overlap — it's QSS/theme tokens, and is the cleanest curated doc in the repo).

**Merge:** Make the Z-ordering table in `display-system.md` the single source; cross-reference (don't duplicate) from `overview.md`/`entities.md`/`guide.md`. Reconcile with `constants.py` and `view-relationships.md` §7.3 (constants.py defers to it as Z-order source of truth).

**Archive:** the `2026-05-10` visibility spec + plan (implemented).

**Salvage before archiving (NOT in curated docs):**
- Riser symbol hosted on **Pipe** not Node; suppressed when either endpoint node visible (avoid double symbol); fixed 300mm size; top-level `Z_OVERLAY` item needing cleanup at 3 pipe-removal sites + `setVisible` cascade gotcha.
- `_set_level_vis` early-return is universal across all entity types (hidden = fully inert).
- Fitting-is-not-a-QGraphicsItem visibility handling + `_show_all_hidden` self.items() gap.
→ all to `display-system.md`.

**CONTRADICTIONS FLAG:**
1. **`display-system.md` Z-ordering section is materially wrong:** maps underlays to `Z_BELOW_GEOMETRY=-100` (actually that's the origin cross; underlays use `Z_UNDERLAY=-79`); "Construction = 50" (actual `Z_CONSTRUCTION=1`); claims constant-less -50/50 rows are "defined in constants.py"; omits the entire elevation-based runtime `Z_ELEV_SCALE + Z_CAT_*` mechanism (the actual primary draw-order system).
2. **`display-system.md` DisplayableItemMixin table** implies `init_displayable()` sets `user_layer` — it does not (and `user_layer` is removed). Same error appears in `entities.md`, `guide.md`, `adding-entities.md`, `io.md`, `level-system.md`.

---

## Cluster 7: Constraints / Align Tool

**Member docs**
- `docs/specs/parametric-constraint-system.md` (constraint base/solver/serialization)
- `docs/superpowers/specs/2026-04-30-align-tool-design.md`
- `docs/superpowers/plans/2026-04-30-align-tool.md`
- (Align participation also in `grid-system.md`)

**Canonical:** `docs/specs/parametric-constraint-system.md` (only in-depth `constraints.py` doc). Fold the constraint-relevant bits of the align-tool design into it; leave the dated align spec as historical.

**Archive:** `2026-04-30-align-tool.md` plan (implemented). Keep `2026-04-30-align-tool-design.md` in place until its unique rationale is promoted.

**Salvage before archiving:** AlignmentConstraint dual-mode reference model (`reference_item` vs `reference_line`) + the **"underlay geometry lacks stable identity, so store two absolute scene points"** rationale → `docs/architecture/entities.md` (Align/AlignmentConstraint are mentioned in **no** curated doc).

**CONTRADICTIONS FLAG:**
1. **Spec vs code:** `parametric-constraint-system.md` Open Questions #3 and #4 claim visual rendering and dimensional-distance editing are **unimplemented** — both are shipped (`model_view.py:355-399` and `:765-792`). §8.1 says "visual point rendering is not implemented in the paint path" — false.
2. **Spec design vs shipped model:** align-tool design models targets via `target_edge_index` + parallel-edge resolution; shipped `AlignmentConstraint` is point-based (`target_point` + `perp_direction`).
3. **Latent code bug surfaced (not a doc task, but record it):** `model_view.py:364` accesses `c.item_a/c.item_b` unconditionally; those exist only on `DimensionalConstraint`, so concentric/alignment indicators would AttributeError if drawn by that loop.

---

## Cluster 8: Level / View / Section / Elevation System

**Member docs**
- `docs/architecture/level-system.md` (curated, published)
- `docs/specs/view-relationships.md` (best Z-order + world-Z-vs-render-Z model in repo)
- `docs/specs/section-view-subsystem.md` (unbuilt proposal)
- `docs/specs/selection-mode.md` (unbuilt target-state contract; depends on Z-priority)
- (overlaps `overview.md`, `display-system.md`, `entities.md`)

**Canonical:** `docs/architecture/level-system.md` (published) + `docs/specs/view-relationships.md` (deep). Promote the code-verified core of `view-relationships.md` (§2 vocab, §3.2/§3.3 two-Z + world-Z property table, §4 taxonomy, §7.1 view range, §7.3/§8 depth sort) into the published architecture set (`display-system.md` / a new views page).

**Keep un-published (aspirational, correctly out of nav):** `section-view-subsystem.md` (no code; none of `section_*.py` exist), `selection-mode.md` (headline features unbuilt). Add explicit "Unimplemented / proposal" banners to both.

**Salvage:** the cardinal-equivalence proof + per-entity section rules (from `section-view-subsystem.md`) — keep only; promote to `display-system.md` only after section views ship.

**CONTRADICTIONS FLAG:**
1. **`level-system.md` documents a REMOVED feature:** `display_mode` (Auto/Hidden/Faded/Visible) + 25%/50% cross-level opacity — gone (`from_dict` comment: "display_mode is ignored on load (removed feature)"; actual cross-level opacity is 1.0).
2. **`apply_for_level()` does not exist** — real method is `apply_to_scene(scene, active_level, ...)`. Same wrong name appears in `overview.md` (line 139) and a stale `level_manager.py:257` docstring. Fix both docs together.
3. `view-relationships.md`: `PaperViewport`→`SheetViewport` rename; wall `_base_offset_mm/_top_offset_mm` described as "Reserved (not applied)" but they **are** applied (`wall.py:457-458`); `_Z_SCALE`→`Z_ELEV_SCALE`.

---

## Cluster 9: Walls / Rooms / Floors / Openings

**Member docs**
- `docs/specs/wall-room-floor-system.md` (deepest algorithmic spec; joinery, room detection, occlusion)
- `docs/superpowers/plans/2026-04-27-wall-cleanup-cluster.md`
- (overlaps published `docs/architecture/entities.md`)

**Canonical:** `docs/specs/wall-room-floor-system.md`. Its joinery/room-detection/occlusion content is unmatched — consider promoting to a new `docs/architecture/wall-room-floor.md` **after** corrections.

**Archive:** `2026-04-27-wall-cleanup-cluster.md` (all 5 tasks shipped; migration rationale already in code comments).

**Salvage:** opening-reposition `_split_vertical_pipe` ordering gotcha is pipe-cluster, not here — n/a. Wall migration mappings already in `wall.py` comments.

**CONTRADICTIONS / INVENTED CONTENT FLAG in `wall-room-floor-system.md`:**
- `§13` "Divergences" table presents **already-implemented** work as pending (alignment rename, Miter removal, opening reposition, offset clamping all shipped) — rewrite/delete.
- `§13` says serialized `'Miter' → 'Butt'`; code maps `'Miter' → 'Solid'`.
- `§9.4` ceiling-type names (Bar joist / Concrete T / Metal deck / Wood joist) are **fabricated** — actual `CEILING_TYPES` strings differ (NFPA-coded). Correctness liability for an NFPA-facing doc.
- `§7.8` window presets described as a width×height grid; code uses **4 fixed (w,h) pairs**.
- `§5.3/§13` reference nonexistent constants `WALL_JOIN_TOLERANCE`/`WALL_MAX_MITER_FACTOR` (real: `MITER_TOL`, `MAX_MITER_FACTOR`, `AUTO_JOIN_TOLERANCE`, `TEE_TOLERANCE`).
- `§13` "dead code room.py:338-339" — wrong line refs (valid return + def).

**Cross-doc CONTRADICTION:** `entities.md` says WallSegment alignment is **Center/Interior/Exterior**; actual code (and the spec, post-cleanup) is **Center/Left/Right**.

---

## Cluster 10: Pipe Placement / Sprinkler Components

**Member docs**
- `docs/specs/pipe-placement-methodology.md` (hybrid spec + bug backlog)
- `docs/specs/sprinkler-system-components.md` (physical-component backbone reference)
- Plans: `2026-04-04-pipe-placement-3d-fixes.md` (partial/superseded), `2026-05-07-pipe-placement-cluster.md`, `2026-05-06-z-blind-snap-fix.md`, `2026-05-09-pipe-data-integrity-cluster.md`
- (solver interface overlaps Cluster 4)

**Canonical:** Split `pipe-placement-methodology.md`: keep the stable data-model/state-machine/geometry-correction sections as a reference (feed `entities.md`); move the §16 bug backlog to the task tracker. `sprinkler-system-components.md` stays the physical-backbone reference (feed `entities.md` contracts).

**Archive:** `2026-05-07-pipe-placement-cluster.md`, `2026-05-06-z-blind-snap-fix.md`, `2026-05-09-pipe-data-integrity-cluster.md` (all implemented). Archive `2026-04-04-pipe-placement-3d-fixes.md` as **superseded** by `2026-05-07-pipe-placement-cluster.md`.

**Salvage before archiving:**
- z_hint + view-range disambiguation contract (two-tier bbox-then-distance, inclusive bounds, `z_hint=None` backward-compat, `"Plan: {level}"` key, paste/pipe z_hint heuristics) from `2026-05-06` → `entities.md`.
- Z-coplanarity branch-slot rule ("max 4 = max 4 coplanar connections", `Z_COPLANAR_TOL`) from `2026-05-07` → `entities.md`.
- Riser-fitting visibility tie-break ladder + "labels are top-level Z_OVERLAY items, not children" + `setVisible`-cascade gotcha from `2026-05-09` → `entities.md`/`display-system.md`.

**CONTRADICTIONS FLAG:**
1. **`2026-04-04-pipe-placement-3d-fixes.md` vs shipped design:** plan/spec assert "all geometry validation uses 3D vectors"; code **rejected** that and uses 2D + `Z_COPLANAR_TOL` coplanarity filter. `pipe-placement-methodology.md` still asserts the aspirational 3D-vector rule — correct it.
2. **`pipe-placement-methodology.md` stale "bugs":** B4 (find_nearby_node z_hint) and B7 (cross-level backtrack) are listed as open but **fixed** in code. B5/B10/B11 genuinely still open.
3. **`sprinkler-system-components.md` divergences D2/D3/D9 listed open but implemented:** SprinklerRecord already has the 7 "future" fields; "Concealed" orientation already exists; template key bug already fixed (`main.py:2282-2292`).

---

## Cluster 11: Documentation System / Packaging (meta)

**Member docs**
- `docs/superpowers/specs/2026-04-04-documentation-design.md`
- `docs/superpowers/plans/2026-04-04-documentation-and-packaging.md`
- (outputs are the entire curated `docs/` tree + `mkdocs.yml`)

**Canonical:** n/a (meta). The curated docs ARE the output.

**Archive:** both (fully implemented). Plan's only rationale stub is superseded by the richer `docs/architecture/refactoring.md`.

**Salvage before archiving:** Decisions Log rationale from the design spec (flat-package choice #2; `.gitignore` shrink #3; NumPy→Google docstring conversion #4; `allow_inspection:false` so docs build never imports PyQt6/VTK #6; `ASSETS_DIR` unification) → `docs/architecture/overview.md` or `contributing/guide.md`.

---

## Cluster 12: Layer-System Removal (cross-cutting cleanup)

**Member docs**
- `docs/superpowers/specs/2026-05-13-remove-layer-system-design.md`
- `docs/superpowers/plans/2026-05-13-remove-layer-system.md`

**Canonical:** n/a. **This is the root cause of the single most widespread stale claim in the curated docs** — `user_layer` still documented as live in **`display-system.md:25/27`, `io.md:53`, `entities.md`, `guide.md`, `adding-entities.md`, `level-system.md`**.

**Archive:** both (implemented; `user_layer_manager.py` deleted, zero refs remain).

**Salvage before archiving:** (1) old `user_layer`/`user_layers` JSON keys are **silently ignored** on load (no migration); (2) hardcoded fallbacks (underlay white #ffffff/1.5px, geometry #ffffff/2.0px); (3) `DEFAULT_USER_LAYER` deliberately retained for annotations/undo compat; (4) DXF source-layer visibility (`hidden_layers`) is **unrelated** and untouched → fold into `display-system.md` + `io.md`, then fix the six curated docs that still reference `user_layer`.

---

## Redundant / Deletable / Archivable List

**Archive (implemented impl plans + shipped superpowers specs — un-published, no unique surviving knowledge after salvage):**
- `docs/superpowers/plans/2026-04-04-documentation-and-packaging.md`
- `docs/superpowers/plans/2026-04-04-pipe-placement-3d-fixes.md` *(superseded)*
- `docs/superpowers/plans/2026-04-07-snap-engine-items-1-3-10.md`
- `docs/superpowers/plans/2026-04-08-osnap-ux-pair.md`
- `docs/superpowers/plans/2026-04-08-snap-primitive-unit-tests.md`
- `docs/superpowers/plans/2026-04-10-snap-engine-cluster.md`
- `docs/superpowers/plans/2026-04-10-grid-system-architecture.md`
- `docs/superpowers/plans/2026-04-13-underlay-workflow.md`
- `docs/superpowers/plans/2026-04-13-underlay-refresh-fix.md`
- `docs/superpowers/plans/2026-04-24-underlay-polish-cluster.md`
- `docs/superpowers/plans/2026-04-24-pdf-vector-and-snap-bugs.md`
- `docs/superpowers/plans/2026-04-27-wall-cleanup-cluster.md`
- `docs/superpowers/plans/2026-04-29-hydraulic-correctness-cluster.md`
- `docs/superpowers/plans/2026-04-30-align-tool.md`
- `docs/superpowers/plans/2026-05-06-z-blind-snap-fix.md`
- `docs/superpowers/plans/2026-05-07-pipe-placement-cluster.md`
- `docs/superpowers/plans/2026-05-09-pipe-data-integrity-cluster.md`
- `docs/superpowers/plans/2026-05-10-visibility-display-cluster.md`
- `docs/superpowers/plans/2026-05-10-paper-space-viewports.md`
- `docs/superpowers/plans/2026-05-12-paper-space-display-manager.md`
- `docs/superpowers/plans/2026-05-13-remove-layer-system.md`
- `docs/superpowers/plans/2026-05-13-underlay-caching.md`
- `docs/superpowers/plans/2026-05-14-dwg-import.md`
- `docs/superpowers/plans/2026-05-15-import-dialog-progress-bar.md`
- `docs/superpowers/plans/2026-05-20-multi-layout-dxf-import.md`
- `docs/superpowers/plans/2026-05-22-hybrid-snap-preview.md` *(superseded by 2026-05-23-lazy-underlay-snap)*
- `docs/superpowers/plans/2026-05-22-batched-underlay-rendering.md`
- `docs/superpowers/plans/2026-05-23-lazy-underlay-snap.md`
- `docs/superpowers/plans/2026-05-23-snap-engine-fallback-for-import-dialog.md`
- `docs/superpowers/plans/2026-05-24-layout-aware-reload.md`
- `docs/superpowers/plans/2026-06-22-osnap-toolbar.md`
- `docs/superpowers/specs/2026-04-04-documentation-design.md` *(after salvaging Decisions Log)*
- `docs/superpowers/specs/2026-05-10-paper-space-viewports-design.md` *(after folding data model into parent spec)*
- `docs/superpowers/specs/2026-05-10-visibility-display-cluster-design.md` *(after salvage → display-system.md)*
- `docs/superpowers/specs/2026-05-12-paper-space-display-manager-design.md` *(after salvage → display-system.md)*
- `docs/superpowers/specs/2026-05-13-remove-layer-system-design.md` *(after salvage + fixing the 6 curated docs)*
- `docs/superpowers/specs/2026-05-20-multi-layout-dxf-import-design.md` *(after salvage → io.md)*
- `docs/superpowers/specs/2026-04-30-align-tool-design.md` *(after salvage → entities.md)*

**Hard delete:** none. Every artifact either carries salvageable rationale or is a load-bearing canonical/spec. (No two docs are byte-redundant; "redundancy" here is plan-vs-shipped-code, resolved by archiving plans.)

**Keep un-published, NOT mergeable (aspirational; add "Unimplemented" banners):**
- `docs/specs/section-view-subsystem.md`
- `docs/specs/selection-mode.md`
- `docs/specs/inferred-dimension-driven-placement.md`

**Most consequential cross-doc fixes to do during consolidation (single source of truth violations):**
1. `user_layer` removal not swept from 6 curated docs (Cluster 12).
2. Z-ordering documented inconsistently/wrongly across `display-system.md`, `guide.md`, `view-relationships.md`, `constants.py` — pick `view-relationships.md §7.3` as source, reconcile all (Clusters 6, 8).
3. `apply_for_level` (nonexistent) in `level-system.md` + `overview.md` → `apply_to_scene` (Cluster 8).
4. `.fp3d` → `.fpd` and fabricated `_geom_to_item()` / migration logic in `io.md` (Cluster 2).
5. Hand-maintained line/method counts across `overview.md`, `entities.md`, `display-system.md`, `refactoring.md`, `level-system.md` are all stale — drop them or auto-generate.


---

# PART 2 — GAP ANALYSIS (additional needed docs)

# FirePro3D Documentation — Gap Analysis: Missing & Under-Served Docs

## Method

I compared three things: (1) **advertised** capabilities in `index.md`, (2) **actually-implemented** features per the audit (code-verified), and (3) what the **curated/published** docs (`docs/architecture/*`, `docs/contributing/*`, `index.md`, `getting-started.md` — the only pages in `mkdocs.yml` nav) actually cover.

**Headline finding:** The published site is **100% contributor/architecture-facing**. There is **zero end-user documentation** — no usage guide, no workflow walkthrough, no keyboard reference, no glossary. Several substantial, fully-implemented subsystems (thermal radiation, 3D view, section/elevation views, paper space) have **no dedicated curated page** despite being advertised or prominent. Meanwhile the large body of accurate, code-verified design knowledge sits **unpublished** in `docs/specs/` and `docs/superpowers/`.

---

## Vaporware / Accuracy Risk Flags (address first — these are factual liabilities)

Per the audit, **no advertised feature is pure vaporware** — every headline capability has substantial backing code. But there are two real **overstatement / "advertised but partial"** risks that documentation currently misrepresents:

| Claim | Reality (audit-verified) | Risk |
|---|---|---|
| **"DXF import/export — ezdxf"** (index.md tech-stack table) | ezdxf is used **read-only**. No DXF write/export path exists anywhere in the repo; export is limited to hydraulic/thermal **PDF/CSV reports**. | **Misleading** — implies round-trip DXF that does not exist. Fix wording to "DXF/DWG import" and add ODA File Converter row. |
| **"clone → install → run"** (getting-started.md) | `requirements.txt` omits `pyvista`, `pyvistaqt`, `vtk`, which `view_3d.py` hard-imports in the startup path (`main.py:2981`). A clean install **crashes on launch**. ODA File Converter (DWG import) is also undocumented. | **App-breaking** for new users/contributors. Not a doc-gap per se, but the *Getting Started* doc certifies a broken process. |

Neither is vaporware, but both should be corrected as part of any doc effort. **3D is real** (PyVista/VTK), **thermal radiation is real** (`thermal_radiation_solver.py`, full Stefan-Boltzmann model + fire curves), **multi-floor/section/elevation is real**, **hydraulics is real and high-quality**.

---

## Prioritized List of Missing / Under-Served Docs

### P1 — High priority (advertised features with no usable doc, or whole audiences unserved)

---

#### P1.1 — User Guide / Workflows (the single biggest gap)
- **Status:** Does not exist. The entire published site is for contributors.
- **Audience:** End users (fire-protection designers, the project owner's actual day-to-day persona — Revit-mental-model engineers doing AHJ submittals).
- **What it should contain:** A task-oriented set of "how do I…" workflows: start a project; set up levels/grids; import a DXF/DWG/PDF underlay and calibrate scale; draw walls/rooms; place sprinklers and pipes; run a hydraulic calc and read results; run a thermal radiation analysis; compose a paper-space sheet and export the report PDF. Screenshots of ribbon/Model Space/property panel.
- **Why it matters:** The product *advertises* user-facing capabilities (2D CAD editing, hydraulic analysis, NFPA 13 compliance) but offers a new user **nothing** to actually operate the tool. This is the highest-leverage doc for the product's stated purpose. The owner's domain expertise (NFPA 13, multi-system, AHJ submissions) makes a credible end-user guide both feasible and valuable.
- **Note:** Likely a *section* of the nav ("User Guide" with several pages), not one file.

#### P1.2 — Thermal Radiation Analysis (architecture/analysis is hydraulic-heavy; thermal is thinly covered)
- **Status:** Under-served. `analysis.md` covers thermal but the audit notes thermal is "thinly documented elsewhere"; there is no dedicated user-facing or deep architecture page. `thermal_radiation_dialog.py` / `thermal_radiation_report.py` / `fire_curves.py` have no usage doc.
- **Audience:** Both — users running the analysis, and developers maintaining the `RadiationModel` ABC.
- **What it should contain:** The surface-to-surface radiation workflow (`RadiationModel` → `StandardSurfaceRadiationModel`, Stefan-Boltzmann view factors, `STEFAN_BOLTZMANN=5.67e-8`, 12.5 kW/m² default threshold, `extract_surface_mesh()` → `get_3d_mesh()`); the fire curves (ISO 834, CAN/ULC S101, constant-temperature); how to run the dialog and interpret the report; assumptions/limitations.
- **Why it matters:** It is one of seven advertised headline features, is fully implemented and non-trivial, and is the **least-documented** of the analysis engines. The architecture content can be mined directly from the (currently unpublished) audit-verified material.

#### P1.3 — Hydraulic Analysis: promote the verified core to the published site
- **Status:** `architecture/analysis.md` exists but is thin and has a stale `HydraulicResult` field list (missing `required_node_pressures`, `hose_stream_gpm`) and omits hose-stream allowance + supply-elevation correction. The **excellent, code-accurate** `docs/specs/hydraulic-solver-and-reporting.md` is **unpublished**.
- **Audience:** Engineers verifying NFPA 13 methodology against hand calcs; developers.
- **What it should contain:** The corrected `analysis.md` plus a promoted, condensed version of the verified spec core — the 4-phase algorithm, every NFPA 13 §22.4.2 formula/constant, the equivalent-length table (Table 22.4.3.1.1) + `Fitting.type` mapping, node numbering. Drop or convert the hand-transcribed dataclass to an mkdocstrings directive to stop drift.
- **Why it matters:** Hazen-Williams/NFPA 13 is a flagship advertised feature; the best documentation of it is hidden, and the published version is partially wrong. Engineering-grade, verifiable content.

#### P1.4 — Getting Started fixes + Installation correctness (treat as a doc deliverable)
- **Status:** Published but certifies a broken install (missing 3D deps; no ODA setup; UI descriptions imprecise; no "verify it launched" step).
- **Audience:** New users and contributors.
- **What it should contain:** Corrected dependency story (3D stack installable via the documented command), ODA File Converter setup for DWG import, accurate dock/tab UI description, a launch-verification step, and a Windows VTK/PyQt6 troubleshooting note.
- **Why it matters:** It is the literal first thing anyone does. Broken onboarding undermines every other doc.

---

### P2 — Medium priority (real subsystems / domain knowledge that strengthen the site)

---

#### P2.1 — Views: 3D View + Section/Elevation Views
- **Status:** No dedicated page. 3D (`view_3d.py`, PyVista/VTK) is only mentioned in passing across architecture docs. Section/elevation (`elevation_*.py`, `detail_view.py`, view markers) is touched in `level-system.md` but the actual subsystem (ElevationScene/View/Manager, world-Z vs render-Z, depth sorting, marker persistence) is undocumented in curated form. The audit-verified `docs/specs/view-relationships.md` (the best world-Z/render-Z synthesis in the repo) is unpublished.
- **Audience:** Both — users navigating views; developers working on view materialization/projection.
- **What it should contain:** The plan/section/3D taxonomy; the two-Z model (world Z mm vs render zValue) and the world-Z property table; how elevation views project and filter; how the 3D view extracts `get_3d_mesh()`; the marker → `openViewRequested` flow. Note: a *future* arbitrary-angle "section view" subsystem is **designed but unimplemented** (`docs/specs/section-view-subsystem.md`) — document only what ships, flag the rest as planned.
- **Why it matters:** 3D viz and multi-floor cross-sections are advertised features; "views" is a core mental model (Revit-aligned) the owner cares about, and the canonical knowledge is currently unpublished.

#### P2.2 — Project File Format & Persistence (the `.fpd` schema)
- **Status:** Under-served and **wrong** in `architecture/io.md` (says `.fp3d` — actual extension is `.fpd`; fabricates non-existent version-migration logic; cites a non-existent `_geom_to_item()`).
- **Audience:** Developers (serialization, migration, debugging corrupt projects); power users.
- **What it should contain:** Correct `.fpd` JSON schema, `SAVE_VERSION=9` (recorded for forward-compat; **no** migration code currently exists — say so), per-entity serialization contract via `SceneIOMixin`, the `sheets` key, underlay cache (`.fpd.cache/`, `_CACHE_VERSION=4`), and the silent-ignore of removed `user_layer` keys.
- **Why it matters:** Persistence is foundational; the current published doc is factually misleading (wrong extension is the worst kind of error). The rich, accurate `docs/specs/underlay-workflow.md` content can feed this.

#### P2.3 — NFPA 13 Domain / Compliance Reference
- **Status:** NFPA values are scattered (coverage limits in `entities.md`/`guide.md`, formulas in `analysis.md`, hazard classes in constants) with **drifted/invented** entries (audit found fictional ceiling-type names in a spec; `guide.md` drops the "Miscellaneous Storage" hazard row).
- **Audience:** Fire-protection engineers and AHJ reviewers; new contributors needing domain grounding.
- **What it should contain:** Single authoritative reference: hazard classifications (all 7), `NFPA_MAX_COVERAGE_SQFT` per class, density/area curves, equivalent-length table, velocity thresholds, ceiling/compartment types — each tied to the NFPA 13 section it implements, generated/linked from `constants.py` to prevent drift.
- **Why it matters:** "NFPA 13 compliance" is an advertised pillar and the owner's core expertise. A consolidated, correct domain reference is high-credibility content and a single source of truth that stops the divergence the audit repeatedly found.

#### P2.4 — Testing Strategy / Contributor Testing Guide
- **Status:** Does not exist. The repo has **39 test files** including a bootstrapped headless pytest harness, a snap-engine matrix harness, and known cross-test VTK-teardown hazards (per user memory: run full suite, View3D cleanup).
- **Audience:** Contributors.
- **What it should contain:** How to run the suite (and the "run two halves / full suite before claiming done" guidance), the QApplication/headless fixture pattern, the snap matrix/primitive layers, the VTK plotter teardown gotcha (multiple MainWindows), and how to write tests for a new entity/tool.
- **Why it matters:** A 39-file suite with real concurrency/teardown gotchas is undocumented; this directly serves the `contributing/` audience that the site already targets, and codifies hard-won lessons.

---

### P3 — Lower priority (polish, discoverability, smaller surfaces)

---

#### P3.1 — Keyboard Shortcuts / Hotkey Reference
- **Status:** None. Shortcuts are real and scattered (F3 OSNAP, Tab cycling/`_handle_tab_input`, Delete/ShortcutOverride handling, ribbon tab-scoped vs window-level shortcuts, tool AL/mode keys).
- **Audience:** End users (primarily), contributors (secondarily).
- **What it should contain:** A single table of global and mode-specific shortcuts, noting the tab-scoped-vs-global distinction.
- **Why:** Pure usability/discoverability; cheap to produce, no architecture risk. Depends on P1.1 existing to have a home.

#### P3.2 — Glossary
- **Status:** None. Mixed AutoCAD/Revit/NFPA/Qt vocabulary (OSNAP, underlay, sheet view vs viewport, world-Z/render-Z, section cut, K-factor, hazard class, level vs floor slab).
- **Audience:** New users and new contributors.
- **What it should contain:** One-line definitions of domain + app-specific terms, cross-linked from other docs.
- **Why:** Low effort, raises coherence across both audiences; valuable given the deliberate Revit-aligned vocabulary.

#### P3.3 — Paper Space / Sheet Composition & Report Export
- **Status:** No curated page. Phase-1 paper space **is implemented** (`paper_space.py` ~1666 LOC: sheets, viewports, title-block overlay, display-manager print overrides) but PDF export/print/multi-sheet are **not** built. Design lives unpublished in `docs/specs/paper-space.md` (stale) + superpowers specs.
- **Audience:** Users composing AHJ submittal sheets; developers.
- **What it should contain:** What ships today (drag views to a sheet, scale, title-block fields, B&W/line-weight print overrides) with an explicit **"as-built vs planned"** boundary (no PDF export / print / multi-sheet yet). 
- **Why P3 not higher:** It's not in `index.md`'s headline feature list and the user-facing surface is incomplete; documenting it now risks promising unbuilt PDF export. Best done once the subsystem stabilizes, or as a clearly-scoped "current capabilities" note.

#### P3.4 — Constraints / Align & Snapping (contributor reference)
- **Status:** No curated page; excellent unpublished specs exist (`parametric-constraint-system.md`, `snapping-engine.md`, `osnap-toolbar.md`). Snapping/constraints are implemented and mature.
- **Audience:** Contributors adding constraint types or snap behavior.
- **What it should contain:** The `Constraint` base contract + solver, the OSNAP pick algorithm/priority bands, the OSNAP toolbar. Distill the verified spec cores into `architecture/` (e.g., fold into display-system or a new page).
- **Why P3:** Strong content already exists (just unpublished) and the audience is narrow; promotion is valuable but not urgent versus end-user gaps.

---

## Summary Table

| Priority | Doc | Audience | Exists today? |
|---|---|---|---|
| **P1.1** | User Guide / Workflows | End users | No (whole audience unserved) |
| **P1.2** | Thermal Radiation Analysis | Both | Thinly, in analysis.md |
| **P1.3** | Hydraulic Analysis (promote verified core, fix drift) | Engineers/devs | Partial + stale |
| **P1.4** | Getting Started / Install correctness | Users/contributors | Yes, but certifies broken install |
| **P2.1** | Views: 3D + Section/Elevation | Both | Scattered mentions only |
| **P2.2** | `.fpd` File Format & Persistence | Devs/power users | Yes but factually wrong |
| **P2.3** | NFPA 13 Domain/Compliance Reference | FP engineers/contributors | Scattered + drifted |
| **P2.4** | Testing Strategy | Contributors | No |
| **P3.1** | Keyboard Shortcuts | Users | No |
| **P3.2** | Glossary | New users/contributors | No |
| **P3.3** | Paper Space / Report Export | Users/devs | No (subsystem partial) |
| **P3.4** | Constraints/Align + Snapping (promote) | Contributors | Unpublished specs only |

## Cross-cutting recommendations
1. **Add a "User Guide" nav section** — the published site currently has *no* end-user entry point; this is the structural gap behind P1.1, P3.1, P3.2, P3.3.
2. **Mine, don't rewrite:** much P1–P2 architecture content already exists, audit-verified, in unpublished `docs/specs/` (hydraulic-solver, view-relationships, underlay-workflow, wall-room-floor, sprinkler-components). Promote corrected cores into `architecture/`; leave dated `superpowers/` artifacts archived.
3. **Kill drift at the source:** prefer mkdocstrings `:::` directives or `constants.py`-generated tables over hand-transcribed dataclasses/line-counts — the audit's most common defect across *every* curated doc was stale hand-copied numbers/fields.
4. **No vaporware to retract**, but **fix the two overstatements** (DXF "export"; the broken install path) before publishing anything new, since they are the only outright-false claims on the published site.


---

# PART 3 — REORGANIZATION PROPOSAL

# FirePro3D `docs/` Reorganization Proposal

## Guiding principles

1. **The published site (mkdocs nav) carries only evergreen, code-verified, current content.** Aspirational or partially-stale specs must not ship to readers who "should be able to answer without reading code."
2. **Living subsystem specs that are code-accurate get a real home in the nav** — a new top-level **Design** section — instead of rotting in an un-discoverable `docs/specs/` silo.
3. **Dated dev-workflow artifacts (superpowers) are history, not docs.** They leave the published tree entirely and move to a clearly-marked archive that mkdocs never builds.
4. **A frontmatter status convention** makes drift visible and lets a future audit be `grep`-able rather than a full re-read.

The audit splits the 14 `docs/specs/` files cleanly into three fates:
- **Promote to published Design nav** (current / code-faithful): `snapping-engine`, `osnap-toolbar`, `underlay-workflow`, `hydraulic-solver-and-reporting` (after the §9/§11.2 fixes), `view-relationships`, `sprinkler-system-components`, `wall-room-floor-system`, `grid-system`, `parametric-constraint-system`, `pipe-placement-methodology`. These are the repo's best architectural knowledge and several are *more accurate than the curated architecture pages*.
- **Keep in Design but mark `proposal` (unbuilt / aspirational)**: `selection-mode`, `section-view-subsystem`, `inferred-dimension-driven-placement`, `paper-space`. These are explicitly forward-looking; publishing them as fact would mislead, but they are valuable design intent. They go in a **Design → Proposals** subsection that the nav labels as not-yet-built.
- The dated specs/plans under `docs/superpowers/` are all implemented-or-superseded history → archive.

---

## 1. Proposed directory tree

```
docs/
├── index.md                         # landing (curated)
├── getting-started.md               # setup (curated)
│
├── architecture/                    # PUBLISHED — high-level, stable orientation
│   ├── overview.md
│   ├── entities.md
│   ├── display-system.md
│   ├── theming.md
│   ├── level-system.md
│   ├── analysis.md
│   ├── io.md
│   └── refactoring.md
│
├── design/                          # PUBLISHED — deep, per-subsystem design references
│   │                                #   (promoted from docs/specs/, code-verified)
│   ├── snapping-engine.md
│   ├── osnap-toolbar.md
│   ├── underlay-workflow.md
│   ├── hydraulic-solver-and-reporting.md
│   ├── view-relationships.md
│   ├── sprinkler-system-components.md
│   ├── wall-room-floor-system.md
│   ├── grid-system.md
│   ├── parametric-constraint-system.md
│   ├── pipe-placement-methodology.md
│   └── proposals/                   # PUBLISHED but flagged status: proposal (unbuilt)
│       ├── selection-mode.md
│       ├── section-view-subsystem.md
│       ├── inferred-dimension-driven-placement.md
│       └── paper-space.md
│
├── contributing/                    # PUBLISHED
│   ├── guide.md
│   ├── adding-entities.md
│   └── adding-tools.md
│
├── gen_ref_pages.py                 # API ref generator (unchanged)
├── requirements.txt                 # docs build deps (unchanged)
│
└── _archive/                        # NOT BUILT — excluded from mkdocs (see §3)
    ├── README.md                    # "Historical AI-dev artifacts. Not maintained. Not in site."
    ├── specs/                       # (empty after migration — see note)
    └── superpowers/
        ├── specs/                   # 7 dated design specs (all implemented)
        └── plans/                   # 31 dated implementation plans
```

> Notes:
> - `reference/` is virtual (generated at build time by `gen_ref_pages.py` + `literate-nav`); it is not a checked-in directory and is unchanged.
> - `docs/_archive/` is kept **inside** `docs/` (not moved out of the repo) so the history stays version-controlled and `git log --follow`-able, but the leading underscore + an `exclude_docs` rule keep it out of the built site. If you prefer it off the docs path entirely, the alternative is a top-level `archive/` sibling to `docs/` — either works; I recommend `docs/_archive/` for discoverability by contributors.

---

## 2. Migration table

Covers **every** current doc. The 31 superpowers plans are collapsed to one row (identical action). The 7 superpowers specs are one row (identical action). Each promoted spec is listed individually because its note differs.

| current-path | action | new-path | note |
|---|---|---|---|
| `docs/index.md` | keep + edit | `docs/index.md` | Fix tech-stack cell `DXF import/export` → `DXF/DWG import` (ezdxf is read-only); optionally add ODA File Converter row. Add cross-links to new Design section. |
| `docs/getting-started.md` | keep + edit | `docs/getting-started.md` | Fix missing 3D deps (`pyvista`/`pyvistaqt`/`vtk`) in `requirements.txt` or call them out; add ODA File Converter prerequisite. |
| `docs/architecture/overview.md` | keep + edit | `docs/architecture/overview.md` | Move entry point to repo-root `main.py`; drop hard-coded line counts; `snap`→`find`, `apply_for_level`→`apply_to_scene`; reclassify DisplayManager (QDialog, not injected service). |
| `docs/architecture/entities.md` | keep + edit | `docs/architecture/entities.md` | Remove `user_layer` claim (layer system removed); fix Wall alignment to Center/Left/Right; Pipe diameter ¾″ + CPVC; drop phantom `Room.sprinklers_inside()/area_sqft()`; remove line counts. |
| `docs/architecture/display-system.md` | keep + edit | `docs/architecture/display-system.md` | Rewrite Z-ordering section (Z_UNDERLAY=-79, Z_CONSTRUCTION=1, add runtime Z_CAT_* model); drop `user_layer`; add Paper-space overrides + Line-Weights subsection (from promoted superpowers knowledge). |
| `docs/architecture/theming.md` | keep | `docs/architecture/theming.md` | Accurate. Optional: note `detect()` is runtime-palette-driven; note pill example relies on global QSS. |
| `docs/architecture/level-system.md` | keep + edit | `docs/architecture/level-system.md` | Remove `display_mode` field/Auto-Hidden-Faded-Visible (removed); `apply_for_level`→`apply_to_scene`; document Z-range intersection visibility. |
| `docs/architecture/analysis.md` | keep + edit | `docs/architecture/analysis.md` | Add `required_node_pressures` + `hose_stream_gpm` to HydraulicResult; mention hose-stream allowance + supply-elevation correction; cross-link to `design/hydraulic-solver-and-reporting.md`. |
| `docs/architecture/io.md` | keep + edit | `docs/architecture/io.md` | `.fp3d`→`.fpd`; cache version 3→4; replace fabricated `_geom_to_item()`; rewrite "Version migration" (no migration exists); cross-link to `design/underlay-workflow.md`. |
| `docs/architecture/refactoring.md` | keep + edit | `docs/architecture/refactoring.md` | Replace stale line counts with magnitudes; fix undo "entire scene/underlays" (excludes underlays); add verified-against-commit/date header. |
| `docs/contributing/guide.md` | keep + edit | `docs/contributing/guide.md` | Delete layer-system convention; rewrite Z-order table from `constants.py`; fix `centre_svg_on_origin` docstring example; add Misc Storage row. |
| `docs/contributing/adding-entities.md` | keep + edit | `docs/contributing/adding-entities.md` | Remove `user_layer`/`active_user_layer`; `Model_Space.py`→`model_space.py`; replace fictional `_snap_or_raw`; align save/load example with real node schema. |
| `docs/contributing/adding-tools.md` | keep + edit | `docs/contributing/adding-tools.md` | `Model_Space.py`→`model_space.py`; replace `_snap_or_raw(event)` with `get_effective_position(event.scenePos())`/`find_snap_point`; note grip dispatch ordering. |
| `docs/specs/snapping-engine.md` | **promote** | `docs/design/snapping-engine.md` | `status: current`. Fix one stale claim: ArcItem tangent **is** implemented (flip §4/§5/roadmap-6 to done). Canonical OSNAP engine reference. |
| `docs/specs/osnap-toolbar.md` | **promote** | `docs/design/osnap-toolbar.md` | `status: current`. Refresh drifted file:line refs (prefer symbols); reconcile §8.5 with as-built ribbon-toggle; test count 8→7. |
| `docs/specs/underlay-workflow.md` | **promote** | `docs/design/underlay-workflow.md` | `status: current`. Fix header ("spec-only, no code" is false — shipped); reconcile §15 priority table; collapse Revision changelog to a footer. |
| `docs/specs/hydraulic-solver-and-reporting.md` | **promote** | `docs/design/hydraulic-solver-and-reporting.md` | `status: current`. **Blocking fix before publish:** move §9 (3-tab) and §11.2 (hf heatmap) into D4/D7 as pending; correct "2 new validations"→1; flip status from Draft. |
| `docs/specs/view-relationships.md` | **promote** | `docs/design/view-relationships.md` | `status: current`. `PaperViewport`→`SheetViewport` (+ line 507→444); wall offsets are applied not reserved; `_Z_SCALE`→`Z_ELEV_SCALE`; fix §3.3 broken table. |
| `docs/specs/sprinkler-system-components.md` | **promote** | `docs/design/sprinkler-system-components.md` | `status: current`. Close D2/D3/D9 (already implemented); expand §4.1 to 17 fields; defaults 15→16; flip Draft→Current. |
| `docs/specs/wall-room-floor-system.md` | **promote** | `docs/design/wall-room-floor-system.md` | `status: current`. Delete/rewrite stale §13 divergences (all shipped); fix §9.4 ceiling names + §7.8 window presets from source; real constant names; flip Draft. |
| `docs/specs/grid-system.md` | **promote** | `docs/design/grid-system.md` | `status: current`. Drop phantom `_user_layer`/`_bubble*_visible`; fix §9.2 migration detection (absence of `p1`); add Locked column; fix Align mover/status string. |
| `docs/specs/parametric-constraint-system.md` | **promote** | `docs/design/parametric-constraint-system.md` | `status: current`. Mark Open-Questions #3/#4 resolved (rendering + distance-edit shipped); fix conflict-message wording; note the `item_a/item_b` paint bug as a code TODO. |
| `docs/specs/pipe-placement-methodology.md` | **promote** + split | `docs/design/pipe-placement-methodology.md` | `status: current`. Strip stale `:line` refs; mark B4/B7 fixed; separate implemented vs aspirational fitting types. Move the §16 bug/enhancement backlog out to the task tracker. |
| `docs/specs/selection-mode.md` | promote as **proposal** | `docs/design/proposals/selection-mode.md` | `status: proposal`. Largely unbuilt (hover highlight, crossing rubber-band, Tab disambiguation). Fix stale `:3374` ref; add "approved but unbuilt" banner. |
| `docs/specs/section-view-subsystem.md` | promote as **proposal** | `docs/design/proposals/section-view-subsystem.md` | `status: proposal`. Unimplemented (no `section_*.py`). Fix self-contradictory `_STATE_VERSION` (5 not 4). |
| `docs/specs/inferred-dimension-driven-placement.md` | promote as **proposal** | `docs/design/proposals/inferred-dimension-driven-placement.md` | `status: proposal`. Greenfield. Fix §10.4 fabricated `_OsnapToolbar`/`snap/` persistence ref; note real `SnapEngine.find()`. |
| `docs/specs/paper-space.md` | promote as **proposal** | `docs/design/proposals/paper-space.md` | `status: partial`. Phase-1 core shipped; PDF export/print/annotations/multi-sheet unbuilt. Fix §12 inventory (1666 LOC, `SheetViewport`, repo-root titleblocks, `layer_manager.py`); reconcile §5 data model with shipped dataclasses. |
| `docs/superpowers/specs/2026-04-04-documentation-design.md` (and the other 6 dated specs) | **archive** | `docs/_archive/superpowers/specs/<same-filename>` | All 7 implemented. Before archiving, promote the rationale that is NOT in curated docs: layer-removal contradiction → fix `display-system.md`/`io.md`; paper-space display-override + line-weight technique → `display-system.md`; riser-on-Pipe + no-double-symbol invariant → `display-system.md`. |
| `docs/superpowers/plans/*.md` (all **31** dated plans) | **archive** | `docs/_archive/superpowers/plans/<same-filename>` | All implemented or superseded. Pure historical build records. Before archiving, fold the handful of unique gotchas the audit flagged (find_nearby_node z_hint contract; coplanar-branch-slot rule; Fitting-not-a-QGraphicsItem visibility; top-level Z_OVERLAY pipe label + setVisible cascade; UnderlaySnapIndex data(4) dual-path; NFPA equiv-length table) into `architecture/entities.md` / `analysis.md` / `display-system.md` / `io.md` as noted per-file in the audit. |
| `docs/superpowers/` (the directory itself) | remove after migration | — | Empty after specs+plans moved to `_archive/`; delete the now-empty tree. |
| `docs/specs/` (the directory itself) | remove after migration | — | Empty after all 14 files promoted to `design/`; delete. |

**Net:** 14 specs promoted (10 to `design/`, 4 to `design/proposals/`), 38 superpowers artifacts archived, 0 deleted (history preserved), and the published nav gains a Design tab.

---

## 3. Required `mkdocs.yml` changes

Two changes: (a) exclude the archive from the build, (b) add the Design nav section.

```yaml
# (a) Stop mkdocs from building the archive. Material >=9.x honors exclude_docs.
exclude_docs: |
  _archive/

# (b) Nav: insert a Design section between Architecture and Contributing.
nav:
  - Home: index.md
  - Getting Started: getting-started.md
  - Architecture:
    - Overview: architecture/overview.md
    - Entities: architecture/entities.md
    - Display System: architecture/display-system.md
    - Theming & UI Style: architecture/theming.md
    - Level System: architecture/level-system.md
    - Analysis: architecture/analysis.md
    - I/O: architecture/io.md
    - Refactoring Candidates: architecture/refactoring.md
  - Design:
    - Snapping Engine: design/snapping-engine.md
    - OSNAP Toolbar: design/osnap-toolbar.md
    - Underlay Workflow: design/underlay-workflow.md
    - Hydraulic Solver & Reporting: design/hydraulic-solver-and-reporting.md
    - View Relationships: design/view-relationships.md
    - Sprinkler System Components: design/sprinkler-system-components.md
    - Wall, Room & Floor System: design/wall-room-floor-system.md
    - Grid System: design/grid-system.md
    - Parametric Constraints: design/parametric-constraint-system.md
    - Pipe Placement: design/pipe-placement-methodology.md
    - "Proposals (not yet built)":
      - Selection Mode: design/proposals/selection-mode.md
      - Section Views: design/proposals/section-view-subsystem.md
      - Inferred / Dimension-Driven Placement: design/proposals/inferred-dimension-driven-placement.md
      - Paper Space: design/proposals/paper-space.md
  - Contributing:
    - Guide: contributing/guide.md
    - Adding Entities: contributing/adding-entities.md
    - Adding Tools: contributing/adding-tools.md
  - API Reference: reference/
```

Notes:
- `exclude_docs` is the supported mechanism in current mkdocs / mkdocs-material; the leading-underscore convention is a belt-and-suspenders signal. (If you stay on an older mkdocs that lacks `exclude_docs`, the `not_in_nav` plugin or simply keeping `_archive/` outside `docs/` achieves the same.)
- With `navigation.tabs` already enabled, **Design** becomes a fourth top tab — visually distinct from Architecture (orientation) vs Design (depth), which is the intended `reference` vs `design` separation.
- `gen-files`, `literate-nav`, and `mkdocstrings` are untouched; `reference/` still auto-generates.

---

## 4. Doc-status frontmatter convention (drift prevention)

Add a YAML frontmatter block to **every** Markdown file under `architecture/`, `design/`, and `contributing/`. mkdocs-material renders frontmatter silently (it does not print it), and it becomes the single `grep`-able signal a future audit keys on — replacing the full re-read the current audit required.

```yaml
---
status: current          # current | proposal | partial | deprecated
last-verified: 2026-06-22 # ISO date the claims were checked against HEAD
verified-commit: aaec44a  # short SHA the doc was verified against (optional but ideal)
applies-to:               # source modules this doc describes (enables targeted re-audit)
  - firepro3d/snap_engine.py
  - firepro3d/model_view.py
owner: design             # team/area, not a person
---
```

Field semantics:

| field | values / format | meaning |
|---|---|---|
| `status` | `current` | code-verified and accurate as of `last-verified`. The default for published architecture/design pages. |
| | `proposal` | design intent for **unbuilt** work. Renders with a banner (see below). Used by the four `design/proposals/` pages. |
| | `partial` | mix of shipped + planned (e.g. `paper-space.md`); body must label which sections are which. |
| | `deprecated` | describes a removed/superseded subsystem; kept only for history; should not be in nav. |
| `last-verified` | `YYYY-MM-DD` | last code-verification pass. CI/audit flags any published `status: current` doc whose `last-verified` is older than N days (suggest 90). |
| `verified-commit` | short SHA | exact commit the verification ran against; lets a reviewer `git diff <sha>..HEAD -- <applies-to>` to see if drift is even possible. |
| `applies-to` | list of repo paths | scopes a re-audit to the modules that changed — turns "re-read all docs" into "re-check docs whose `applies-to` intersects the diff." |
| `owner` | string | area of responsibility. |

Enforcement (cheap, high-leverage):
- **Render-time banner for non-current docs.** Add an `overrides/main.html` partial (or a small `mkdocs-macros` hook) that, when `page.meta.status != "current"`, injects an admonition at the top: e.g. *"⚠ Proposal — this subsystem is not yet implemented"* (`proposal`), or *"⚠ Partially implemented — see section labels"* (`partial`). This guarantees a reader can never mistake `design/proposals/paper-space.md` for shipped behavior, which is the whole reason it's safe to publish them.
- **A pre-commit / CI check** (`scripts/check_doc_status.py`): fail the build if any file in `architecture|design|contributing` lacks frontmatter, has `status: current` with `last-verified` older than 90 days, or references a path in `applies-to` that no longer exists. This converts silent drift into a loud, dated failure.
- **`docs/_archive/` is exempt** (excluded from the build), so dated artifacts never need frontmatter and never trigger the staleness check.

This convention directly attacks the two failure modes the audit found everywhere: stale `:line` references (mitigated by preferring `file:symbol` and pinning `verified-commit`) and removed-subsystem references like `user_layer` (caught by `applies-to` + the diff-scoped re-audit).

---

## Summary of decisions (decisive answers to the brief)

- **Should specs be in the mkdocs nav?** Yes — the 10 code-faithful ones, under a new top-level **Design** tab. The 4 aspirational ones also publish but live in **Design → Proposals** with a render-time "not built" banner driven by `status: proposal`. None stay in the un-discoverable `docs/specs/` silo.
- **Fate of `docs/specs/`:** dissolved. All 14 files move into `docs/design/` (or `design/proposals/`); the empty directory is deleted.
- **Fate of `docs/superpowers/`:** removed from the published tree. All 7 specs + 31 plans move to `docs/_archive/superpowers/` (kept in-repo for history, excluded from the site via `exclude_docs`), after promoting the small set of unique rationale/gotchas the audit flagged into the curated architecture pages.
- **reference vs design separation:** achieved — `architecture/` = orientation, `design/` = subsystem depth, `reference/` = auto-generated API, `_archive/` = history.


---

# PART 4 — SCOPE/SHAPE SYNTHESIS & CONTRADICTION MAP

# FirePro3D — Scope/Shape Synthesis & Contradiction Map

## 1. Scope & Shape: De-Facto Product Truth

**Product vision (as-built).** FirePro3D is a desktop fire-protection sprinkler design tool that is, in practice, a *2D-input / 3D-semantics CAD editor* purpose-built for NFPA 13 work. The user draws in a plan-view canvas (millimeters internally), but every entity carries true world-Z, and the app composites elevation views, a 3D PyVista model, and (partially) paper-space sheets from that single model. The strongest, most code-faithful subsystems are the hydraulic solver, snapping engine, and DXF/DWG/PDF underlay import — these are mature and verification-grade. The thinnest/aspirational areas are paper space (Phase-1 only), section views (unbuilt), and the "smart drafting" inference layer (unbuilt).

**Target user (inferred + confirmed by owner memory).** A practicing fire-protection engineer/designer with hands-on NFPA 13 knowledge who thinks in a *Revit mental model* (linked views, paper-space annotations, presentation-layer scale, levels not layers) rather than AutoCAD. The owner prioritizes pressure over velocity, understands multi-system design and AHJ submittals. So the product is "Revit-shaped CAD for sprinkler hydraulics," not "AutoCAD clone."

**Subsystem map (de-facto status):**

| Subsystem | Status | Notes |
|---|---|---|
| CAD canvas (Model_Space/Model_View) | Mature | QGraphicsScene hub, mode-string state machine |
| Entities (node/pipe/sprinkler/wall/room/floor/roof/annotations) | Mature | All present, mostly via DisplayableItemMixin |
| Display / theming | Mature | Display Manager (per-category + per-instance overrides); theme.py token system |
| Levels / elevation / scale | Mature | LevelManager, ElevationManager, ScaleManager; Z-range visibility |
| Snapping (OSNAP) | Mature (best-maintained spec) | 8 snap types, 4-phase picker, UnderlaySnapIndex |
| Grid system | Mature | Single GridlineItem, lock/perp-move, elevation projection |
| Walls/rooms/floors | Mature | Joinery, room boundary-walk, occlusion, NFPA coverage |
| Pipe placement | Mature (with open bugs) | 2-click state machine, geometry corrections, risers |
| Sprinkler systems | Mature | SprinklerDatabase, templates, fitting assignment |
| Hydraulics | Mature | Hazen-Williams 4-phase, NFPA 13 equivalent lengths, hose stream |
| Thermal radiation | Implemented, lightly documented | RadiationModel ABC, Stefan-Boltzmann, fire curves |
| Import / underlay | Mature | DXF/DWG(ODA)/PDF, caching, multi-layout, batched render |
| Paper space | Phase-1 only | Single-sheet compositor; NO PDF export, NO print, NO annotations |
| Views / sections | Elevations built; **sections unbuilt** | SectionScene/View/Manager do not exist |
| Selection | **Baseline only; target model unbuilt** | No hover-highlight, no crossing rubber-band, no Tab disambiguation |
| Parametric constraints | Built (3 types) | Concentric/Dimensional/Alignment |

**Layered architecture (confirmed).** `main.py` (repo root) is the entry point and owns `MainWindow`. `Model_Space(SceneToolsMixin, SceneIOMixin, QGraphicsScene)` is the central hub. Manager *services* it genuinely owns/delegates to: ScaleManager, LevelManager, SnapEngine, SprinklerSystem, PlanViewManager, ElevationManager. **DisplayManager is NOT an injected service** — it is a QDialog plus module-level apply functions plus per-entity `_display_overrides` (a recurring doc error). Decoupling via ~12+ pyqtSignals. Undo = full-network JSON snapshot (`UNDO_MAX=50`), persistence = JSON `.fpd` (`SAVE_VERSION=9`).

---

## 2. The Entity Model

Two distinct families share the `DisplayableItemMixin` contract (`init_displayable()` — does NOT call `super().__init__()`; sets `level`, `_display_color`, `_display_overrides`, section attrs; provides `z_range_mm()`/`is_cut_by()`).

**A. Piping / hydraulic network (graph topology):**
- **Node** (`DisplayableItemMixin + QGraphicsEllipseItem`) — connection point; carries `z_pos` derived from `ceiling_level.elevation + ceiling_offset` (default −50.8 mm); max **4 coplanar** connections; holds `pipes[]`.
- **Pipe** (`+QGraphicsLineItem`) — edge between two Nodes; diameter ¾″–8″, materials incl. CPVC, C-factor, schedule→bore tables; stores per-endpoint ceiling attrs (`node1/node2_ceiling_*`), NOT its own ceiling.
- **Sprinkler** (`+QGraphicsSvgItem`) — terminal device; K-factor, orientation (Upright/Pendent/Sidewall/**Concealed**), 3 graphic styles.
- **Fitting** — **the outlier**: a plain class (NOT a QGraphicsItem), wraps a `_TintedSvg` child parented to a Node; duplicates display attributes manually; type auto-determined by `determine_type()` truth table.
- **WaterSupply** — source node; hose-stream allowance, supply curve.

**B. Architectural geometry (spatial):**
- **Room** (`+QGraphicsPolygonItem`) — boundary-detected polygon; NFPA hazard/compartment/ceiling types, coverage math, two-tier (tagged + spatial) sprinkler detection.
- **WallSegment** (`+QGraphicsPathItem`) — centerline + thickness; alignment **Center/Left/Right**; join modes **Auto/Butt/Solid** (Miter removed); auto-joinery.
- **WallOpening / DoorOpening / WindowOpening** — owned by a wall, absolute offset-along, reposition-on-edit.
- **FloorSlab** (`+QGraphicsPathItem`) — polygon slab; occlusion masking; ear-clip 3D mesh.
- **RoofItem** — slope/3D mesh.

**C. Annotation / construction:** DimensionAnnotation, NoteAnnotation, HatchItem, GridlineItem, plus ConstructionLine/Polyline/Line/Rectangle/Circle/Arc, and parametric Constraints (Concentric/Dimensional/Alignment).

**Relationship summary:** The network family is a *graph* (Nodes ↔ Pipes, Fittings hang off Nodes, Sprinklers terminate it, WaterSupply feeds it) consumed by the hydraulic solver. The geometry family is *spatial* (Rooms detected from Walls; FloorSlabs/Roofs bound levels; Openings owned by Walls) and drives NFPA coverage + 3D meshing. Levels tie both families together via world-Z and view-range filtering.

---

## 3. Contradictions & Ambiguities

**A. The removed layer system — curated docs still document it as live (HIGH severity, multiple docs).**
The layer system (`UserLayerManager`, `user_layer`) was *deleted* (`docs/superpowers/specs/2026-05-13-remove-layer-system-design.md`, Status: Complete; verified: 0 `user_layer` occurrences in code). Yet:
- `docs/architecture/display-system.md` lists `user_layer` in the DisplayableItemMixin attribute table.
- `docs/architecture/io.md` lists `user_layer` as a serialization field.
- `docs/architecture/entities.md` claims `init_displayable()` sets `user_layer` (default "Default").
- `docs/contributing/guide.md` documents `DEFAULT_USER_LAYER` as a "drawing layer" convention and shows a `node.py` import of it that doesn't exist.
- `docs/contributing/adding-entities.md` references `user_layer`, `active_user_layer`, and save/load of `user_layer` — all fictional now.
These will actively misdirect a new contributor.

**B. `apply_for_level` vs `apply_to_scene` (two curated docs wrong).**
`docs/architecture/overview.md` (Mermaid) and `docs/architecture/level-system.md` both name `LevelManager.apply_for_level()`. The real method is `apply_to_scene(scene, active_level, ...)` (confirmed; `apply_for_level` survives only as a stale docstring at level_manager.py:257).

**C. `display_mode` (Auto/Hidden/Faded/Visible, 25%/50% opacity) — fully removed but `level-system.md` documents it.**
`docs/architecture/level-system.md` describes a Level `display_mode` field and faded-opacity cross-level rendering. Code (confirmed) ignores `display_mode` on load; cross-level items render at opacity 1.0 via Z-range intersection. The doc's entire Mermaid visibility flow models a removed feature.

**D. Z-ordering documented wrong in `display-system.md` and `guide.md`.**
Both map underlays to `Z_BELOW_GEOMETRY=-100` (actually the origin cross; underlays use `Z_UNDERLAY=-79`), invent ranges ("Walls/Floors 0-50", "Nodes 10+", "Construction=50"), and omit the *actual primary mechanism* — the runtime elevation-based `Z_ELEV_SCALE + Z_CAT_*` ordering. `constants.py` itself defers to `docs/specs/view-relationships.md §7.3` as source of truth, so three places must reconcile.

**E. Fictional/stale APIs in contributor how-tos (will break a contributor copying them).**
- `_snap_or_raw(event)` — does not exist (`adding-entities.md`, `adding-tools.md`); real path is `get_effective_position()` / `find_snap_point()`.
- `Model_Space.py` (capitalized) — file is `model_space.py` (both how-tos).
- `_geom_to_item()` — fabricated function named twice in `io.md` (and mirrored in a `pdf_import_worker.py` docstring); real path is `_on_dxf_finished` / `_append_geom_to_path` / `_build_pen_cache`.
- `SnapEngine.snap(pos, items)` — real method is `find(...)` (`overview.md` table + Mermaid).

**F. Project file extension contradiction.**
`docs/architecture/io.md` says `.fp3d` at line 12 but `.fpd.cache` at line 122 — internally inconsistent. Truth is `.fpd` everywhere (confirmed; matches owner memory).

**G. Aspirational sections written as current behavior (the most dangerous class).**
- `docs/specs/hydraulic-solver-and-reporting.md` §9 documents a 3-tab report (Summary / Node Summary / Graph) as current — code has the *old 5-tab* layout. §11.2 documents a friction-loss heatmap as current — code uses absolute velocity thresholds. These are open divergences D4/D7 written as done.
- `docs/specs/selection-mode.md` (Status: "Approved") describes hover pre-highlight, crossing rubber-band, Tab disambiguation — *none implemented*. "Approved" reads as "done."
- `docs/specs/section-view-subsystem.md` (Status: "Approved") — entire SectionScene/View/Marker/Manager subsystem unbuilt.

**H. Specs whose divergence ledgers are inverted (resolved items listed as open).**
- `docs/specs/sprinkler-system-components.md`: D2 (extended SprinklerRecord fields), D3 ("Concealed" orientation — confirmed in code), D9 (template-key bug) are all *already fixed* but listed as open.
- `docs/specs/wall-room-floor-system.md` §13: the entire "Divergences" table describes changes already implemented (alignment rename, Miter removal, offset clamping, MITER_TOL extraction); also invents constant names (`WALL_JOIN_TOLERANCE`) and fabricates ceiling-type strings (§9.4) and window-preset axes (§7.8).
- `docs/specs/parametric-constraint-system.md`: Open Questions #3 (visual rendering) and #4 (dimensional distance editing) are *already implemented*.

**I. AlignmentConstraint spec vs as-built mismatch.**
`docs/superpowers/specs/2026-04-30-align-tool-design.md` models alignment via `target_edge_index` + parallel-edge resolution. Shipped code (confirmed) is *point-based*: `target_point` + `perp_direction`, with dual `reference_line`/`reference_item` modes. The dual-mode underlay-fixed-line rationale exists ONLY in this spec and no curated doc.

**J. PaperViewport → SheetViewport rename not propagated.**
`docs/specs/view-relationships.md` and `docs/specs/paper-space.md` reference `PaperViewport` (class renamed to `SheetViewport`); paper-space.md §12 also has wrong LOC (763 vs 1666), wrong title-block path (`firepro3d/default titleblocks/` vs repo-root), wrong module (`user_layer_manager.py` vs `layer_manager.py`), and a data model (§5.2 `scale:str`, `crop_override`, `layer_overrides`) that doesn't match the shipped dataclass.

**K. Wall offsets: "reserved" vs applied.**
`view-relationships.md` §3.3 says `_base_offset_mm`/`_top_offset_mm` are "reserved (not applied)" — code applies them in `z_range_mm()`.

**L. Pervasive line-number drift + LOC counts in nearly every architecture doc** (overview, entities, display-system, io, refactoring all cite stale line/method counts). Owner memory already flags this as a known repo-wide pattern.

**M. Spec status fields are unreliable.** Many specs say "Draft" though shipped (grid-system, wall-room-floor, sprinkler-components, hydraulic-solver); two say "Approved" though *unbuilt* (selection-mode, section-view). Status is not a trustworthy signal anywhere.

---

## 4. Open Design Questions / Unresolved Decisions

1. **Layer system: settled or vestigial?** Removed in code, but `DEFAULT_USER_LAYER` deliberately retained for annotations/undo compat. Is that a permanent annotation concept, or debt to finish removing? Docs haven't caught up either way.
2. **Paper-space scope & timeline.** Phase-1 single-sheet compositor shipped; the *whole point* (PDF export, print, multi-sheet, annotations, title-block templates) for AHJ submittal is unbuilt. Is this P1 MVP-blocking or deferred? (Owner's MVP model lists paper space as P1.)
3. **Section views: commit or kill?** A full "Approved" spec exists to *replace* the cardinal-only elevation system with arbitrary-angle sections. Never started. Is this still the direction, or are elevations sufficient?
4. **Selection-mode target model.** A complete cross-spec "hub" contract (hover highlight, crossing window, Tab disambiguation, room label-only click) is approved but unbuilt — and other specs *defer to it*. Is this a near-term priority or shelfware?
5. **Constraint system maturity & exposure.** Three constraint types ship and are more complete than docs admit, but there's a latent code bug (model_view.py constraint paint loop accesses `item_a`/`item_b` that only exist on DimensionalConstraint → AttributeError risk for concentric/alignment under selection). Is the constraint system a first-class feature or experimental?
6. **Thermal radiation maturity.** Fully implemented but thinly documented and absent from most subsystem discussion. Is it a headline feature, a research spike, or a maintained product capability?
7. **Auto-populate maturity.** `auto_populate_dialog.py` + density/area curves exist; pipe-placement spec frames it as partially implemented with open bugs. Production-ready?
8. **Hydraulic report direction.** Spec wants 3-tab NFPA-style; code has 5-tab. Which is the intended UX? (Also friction-loss heatmap vs velocity coloring — owner memory says velocity coloring should be a *separate* results view, suggesting the heatmap target may be reconsidered.)
9. **DXF export.** Landing page implies "import/export"; no export exists. Is DXF/DWG write-back ever in scope, or import-only forever?
10. **Doc strategy: specs as living docs vs dated artifacts.** `docs/specs/` are un-published, status-unreliable, and drift badly; `docs/superpowers/` are dated plans. What is the canonical source of truth — code, architecture/ docs, or specs? The audit repeatedly recommends promoting verified spec content into published architecture docs.
11. **Pipe placement open bugs (B5/B10/B11).** Insertion-order-dependent `snap_point_45` (pipes[0]), single-vertical fitting inspection, 2D label length on 3D pipes — confirmed still open. Triage priority?
12. **Undo cost model.** Full-network JSON snapshot × 50 — flagged for command-based refactor. Acceptable or a perf liability at scale?

---

## 5. The Sharpest Questions for the Owner (grilling seeds)

1. **"You built a 2D-input/3D-semantics editor with Revit-style levels, linked views, and paper-space annotations. Walk me through the one workflow — from blank canvas to AHJ submittal — that this product must nail. Where does that workflow currently dead-end?"** *(Exposes whether the as-built subsystem mix actually serves the core job, and surfaces that paper-space export is the likely dead-end.)*

2. **"Paper space is the deliverable for AHJ submittal, yet PDF export, print, multi-sheet, and annotations are all unbuilt. Is the product shippable without them, or is everything before paper-space just plumbing for a feature that doesn't exist yet?"** *(Forces a hard call on MVP completeness vs the P1 claim.)*

3. **"You have an 'Approved' spec to replace cardinal elevations with arbitrary-angle section views, and another 'Approved' spec rewriting the entire selection model — neither started. What does 'Approved' mean in this project, and which of these is a commitment vs a wish?"** *(Attacks the meaning of status across all specs.)*

4. **"The hydraulic spec documents a 3-tab NFPA report and a friction-loss heatmap as if they exist; the code has 5 tabs and velocity coloring. Which is the truth you want — and did the spec lead the code or did the code quietly overrule the spec?"** *(Surfaces who governs: spec or code.)*

5. **"The layer system was deleted, but five published docs still teach it and `DEFAULT_USER_LAYER` lingers for annotations. Is 'levels not layers' a finished decision, or did you leave a door open?"** *(Tests whether the Revit-vs-AutoCAD model is fully committed.)*

6. **"Fitting is the only entity that isn't a QGraphicsItem and doesn't use the mixin — it hand-duplicates display state and is flagged for refactor. Is that an intentional design boundary, or accumulated debt you've learned to live with?"** *(Questions a structural inconsistency in the entity model.)*

7. **"Undo snapshots the entire network as JSON on every action, capped at 50. At what project size does that hurt, and have you actually hit it — or is the command-based-undo refactor premature?"** *(Distinguishes real pain from speculative debt.)*

8. **"Thermal radiation is fully implemented but barely documented and absent from your subsystem conversations. Is it a product pillar, a differentiator you're under-selling, or a spike you haven't decided to keep?"** *(Forces classification of an orphaned-but-built feature.)*

9. **"Auto-populate, the constraint system, and the inference/smart-drafting layer sit at very different maturities. If you had to cut one to focus, which earns its keep with the fire-protection engineer, and why?"** *(Prioritization among the 'smart' features.)*

10. **"Your specs claim divergences are 'open' that are actually fixed, and 'open questions' that are actually answered in code. How are you supposed to trust any spec's ledger — and what's the canonical source of truth for this project: code, architecture docs, or specs?"** *(Directly targets doc strategy.)*

11. **"Snapping is your best-maintained spec — kept in lockstep with code via dated annotations. What did you do differently there, and why doesn't every subsystem get that discipline?"** *(Extracts the process that works, to generalize it.)*

12. **"A practicing engineer prioritizes pressure over velocity. Your on-scene pipe coloring is velocity-based and your hydraulic UX is split across specs and code. Does the current analysis presentation match how the engineer actually reads a system, or how the code happened to evolve?"** *(Domain-expertise vs implementation drift.)*

13. **"You store everything in millimeters with true world-Z under a 2D drawing surface. Where has that 2D-input/3D-truth split bitten you — pipe placement coplanarity, room ceiling Z, riser visibility — and is the abstraction still earning its complexity?"** *(Probes the foundational architectural bet via its known pain points.)*

14. **"There's a latent crash in the constraint paint loop (concentric/alignment items hitting `item_a`/`item_b`). How exposed is the constraint feature to real users right now — is it shipped, gated, or quietly half-on?"** *(Tests honesty about feature exposure vs maturity.)*

15. **"If a new contributor followed your own how-to docs today, they'd reference a deleted layer system, a fictional `_snap_or_raw`, and a miscapitalized filename. Who is the documentation actually for — onboarding contributors, future-you, or the AI dev workflow — and which audience are you willing to let down?"** *(Forces an explicit doc-audience decision.)*

16. **"Across the board, line counts and line-number references rot instantly, yet specs keep embedding them. Is the fix discipline (stop citing line numbers), tooling (auto-generate), or accepting specs as dated snapshots that get archived, not maintained?"** *(Resolves the systemic drift mechanism, not just instances.)*

17. **"You have a parent paper-space vision spec and a child subset spec that actually shipped, with the parent now stale and unlinked. When you carve an MVP subset out of a big vision, what's your rule for keeping the parent honest — or do you let it rot as a vision artifact?"** *(Process question on spec lifecycle.)*

18. **"Of everything built but undocumented-or-mis-documented — thermal, constraints, the elevation Z-ordering engine, the underlay caching/snap-index — what is the one capability you'd be most upset to see a user or contributor never discover?"** *(Surfaces the owner's own sense of hidden value, seeds promotion priorities.)*

---

Relevant absolute paths for the grilling session:
- Curated (published) with errors: `D:\Custom Code\FirePro3D\docs\architecture\{overview,entities,display-system,level-system,io}.md`, `docs\contributing\{guide,adding-entities,adding-tools}.md`, `docs\index.md`, `docs\getting-started.md`
- Aspirational-as-current / status-unreliable specs: `docs\specs\{selection-mode,section-view-subsystem,hydraulic-solver-and-reporting,paper-space,view-relationships,wall-room-floor-system,sprinkler-system-components,parametric-constraint-system,pipe-placement-methodology}.md`
- Canonical Z-order source of truth (per constants.py): `docs\specs\view-relationships.md` §7.3
- Layer-removal record: `docs\superpowers\specs\2026-05-13-remove-layer-system-design.md`
- Code hubs: `firepro3d\model_space.py`, `firepro3d\level_manager.py`, `firepro3d\constants.py`, `firepro3d\constraints.py`