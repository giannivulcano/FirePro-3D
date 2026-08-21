# Paper-Space Viewport / Detail-Crop Cluster — Design

**Date:** 2026-08-21
**Status:** approved (brainstorm) — pending implementation plan
**Governing specs to update on completion:** `docs/specs/paper-space.md`, `docs/specs/view-relationships.md`
**Primary modules:** `paper_space.py`, `model_view.py`, `view_marker.py`, `detail_view.py`, `paper_display.py`, `paper_commands.py`, `scene_io.py`, `main.py`

---

## Goal

Make paper-space viewports honest and clean for the AHJ plot package:

1. A detail placed on a sheet shows **only** the geometry inside its crop rectangle.
2. Elevation-marker furniture never appears on plotted sheets.
3. Detail boundary boxes plot on their host plan by default, hideable per sheet, and never frame their own detail viewport.
4. Revision / Rev / Date editing is reachable without selecting the (now non-selectable) title block.
5. A viewport's on-paper size is governed by its **stated scale**, not free-dragged — so the drawing never lies about its scale.

## Motivation

Today a viewport's on-paper `w/h` is free-draggable and the *actual* scale is back-computed as `min(vp/source)` — so resizing silently rescales the drawing. The same free-resize breaks the aspect match between the viewport box and the crop rect; Qt's `KeepAspectRatio` then letterboxes the crop inside `vp_rect`, and because the only clip is `setClipRect(vp_rect)` (the whole box), out-of-crop geometry leaks into the letterbox margins. Concerns (1) and (5) share this root. Concerns (2)–(4) are paper-render visibility / UI-routing corrections that keep authoring furniture out of the deliverable and make the revision data reachable.

## Architecture & Constraints

- **Single render path.** `paper_export.render_sheet` builds a transient `PaperScene` and calls `scene.render(...)`, which drives the same `SheetViewport.paint()` as the on-screen sheet. Fixing `paint()` fixes screen preview **and** exported PDF together — PDF/screen parity is by construction, not a second code path. (`paper_export.py:72-98`.)
- **On-screen model canvas is never touched by the paper pass.** `apply_paper_overrides` runs only during `SheetViewport.paint`. All paper-only suppression lives there; the model canvas keeps showing furniture (elevation markers on selection, detail markers always).
- **Paper state is single-path.** New per-viewport state lives on `SheetViewData` (part of the paper `Sheet`), serialized only via `Sheet.to_dict/from_dict`. The model-scene dual-serialization rule (`scene_io` + undo `_capture_network`) does **not** apply — this state is not model-scene state.
- **House rules:** plotted PDF is the visual acceptance gate; tests drive the real render/selection entry points and are red-verified.

## Design Decisions

### D1 — Crop region is the source of truth (concerns 1 + 5) — *Approach A*

- `SheetViewData` (`paper_space.py:270`) gains `crop_rect: QRectF` in **source-scene (model) coordinates** — the window this viewport shows.
- `scale` stays authoritative. `w`/`h` become **derived caches**: `w = crop_rect.width()·scale`, `h = crop_rect.height()·scale`, recomputed on any crop or scale change. They remain serialized (cache/compat) but are never an independent input.
- **`paint()` (`paper_space.py:776`):** render with `crop_rect` as the source rect. Since `w/h = crop×scale`, viewport aspect == crop aspect → `render(painter, vp_rect, crop_rect)` maps 1:1 with **no `KeepAspectRatio` letterbox**; `setClipRect(vp_rect)` clips exactly at the crop edge. `paper_scale` passed to `apply_paper_overrides` = `scale` (i.e. `w/crop.width()`), no longer back-computed.
- **Grips (`_apply_grip_resize`, `:995`):**
  - **Plan / elevation viewports:** grip drag mutates `crop_rect` (moved edge/corner = `Δpaper ÷ scale` in model space, anchored at the opposite edge); `w/h` recomputed; `scale` untouched. Default `crop_rect` at placement = full source extent (`itemsBoundingRect` / elevation bounds).
  - **Detail viewports:** grips **inert**. `crop_rect` is read-only, sourced from `marker.crop_rect` via `ViewResolver._resolve_detail` (`:645`). Resize a detail by editing its marker in the model.
- **Scale change** (panel/dialog, `_on_viewport_properties` `:3538`): keep `crop_rect`, recompute `w/h`. Free `w/h` resize is removed.
- **Panning deferred (v1 = resize only).** No gesture to slide the crop window over the model at fixed size. Reframe by moving edges. A dedicated pan is a filed follow-up if a sheet ever needs "same window, different region."

### D2 — Paper-only exclusion + context hide (concerns 2 + 3)

One decision point inside the `apply_paper_overrides` pass (`paper_display.py:439`), which already walks `scene.items(crop_rect)` and can `setVisible(False)`:

- **(2) Elevation markers — HARD RULE.** `ViewMarkerArrow` and `SharedCropBox` (`view_marker.py`) declare `PAPER_EXCLUDED = True`. The paper pass force-hides any item carrying the flag **unconditionally** — independent of selection state and of any Display-Manager "Elevation Marker" category (the hard rule wins). On-screen unchanged. Future section-view markers simply won't set the flag, so they will plot.
- **(3) Detail boundary boxes.** `DetailMarker` does **not** set `PAPER_EXCLUDED` (default ON). Two context rules evaluated against the viewport being painted (the pass receives the `SheetViewData`, or the two facts it needs):
  - **Self-hide:** if `viewport.source_view_type == "detail"`, hide the `DetailMarker` whose id == `source_view_name`. Nested / other detail markers still render.
  - **Per-sheet hide:** hide any `DetailMarker` whose id ∈ `viewport.hidden_detail_ids`.
- **New state:** `SheetViewData.hidden_detail_ids: set[str]` — marker ids hidden **in this host-plan viewport only** (per-sheet by construction). Default empty = all shown.
- **Hide UI:** right-click a detail boundary box in a paper viewport → **"Hide detail on this sheet"** / inverse. Direct manipulation on the exact box; reuses the existing paper context-menu pattern; no new viewport property panel. On-screen model marker always visible.

### D3 — Title block non-selectable; revisions via Sheet Properties (concern 4)

- `TitleBlockTemplateItem` (`paper_space.py:2824`): `ItemIsSelectable = False`; remove its per-sheet `get_properties`/`set_property` (`:2871-2933`); relocate `_open_revisions_dialog` (`:2935`). Audit `main.py:2672-2682` `show_properties(template)` calls and reroute/remove any that relied on selecting the title block; keep titleblock-editor access working (double-click to open editor stays).
- `SheetProperties` (`paper_space.py:553`) `get_properties` gains, after the existing rows: `"Rev"` (string), `"Date"` (string), and a `"Edit Revisions…"` button opening the existing `RevisionsDialog`.
- **Undoability:** Sheet Number/Name stay non-undoable (as today). Rev/Date/Revisions **stay undoable** — `SheetProperties` resolves the active `PaperScene`'s undo stack and routes `Rev`/`Date` through `SetSheetFieldCommand`, revisions through `EditRevisionsCommand`, preserving the §17.7 dirty relay. Assumes the edited sheet is the active paper sheet; if the stack can't be resolved, fall back to a direct write + `on_change` (dirty).
- Template design stays entirely in the titleblock editor.
- **Deferred (filed P3):** per-revision "By" / "Approved By" column.

### D4 — Persistence & undo

- `Sheet.to_dict/from_dict`: serialize `crop_rect` (`{x,y,w,h}`) and `hidden_detail_ids` (list).
- **Migration** (Approach A): missing `crop_rect` → full source extent with `w/h` recomputed from stored `scale` (legacy free-resized viewports snap to displaying at their honest stated scale — intended, may visibly resize old viewports); missing `hidden_detail_ids` → `[]`.
- `ViewportGeometryCommand` (`paper_commands.py:132`) extends to snapshot/restore `crop_rect` alongside x/y/w/h.
- Detail per-sheet hide toggle → an undoable command on the paper stack (new small command or a generic viewport-field command).

## Acceptance Criteria

1. A detail on a sheet shows only geometry inside its crop rect — nothing outside bleeds, at any viewport size/aspect — identical in on-screen preview and exported PDF.
2. The elevation-marker apparatus (N/S/E/W arrows + `SharedCropBox`) never renders in any paper viewport or exported PDF, regardless of selection. On-screen behavior unchanged.
3. A detail viewport never draws its own crop box; a host-plan viewport shows detail boundary boxes by default; each box is hideable per sheet; nested/other boxes still show. Paper only; on-screen marker always visible.
4. The title block cannot be selected on a sheet. Selecting the sheet shows Rev, Date, and "Edit Revisions…" in Sheet Properties; those edits are undoable and set the dirty flag. Template design still edited only in the titleblock editor.
5. After a grip drag, the viewport's effective on-paper scale equals its stated scale (`w/h == crop_rect × scale`); scale changes only via panel/dialog.
6. `crop_rect` and `hidden_detail_ids` round-trip through save/load; legacy files migrate to honest scale.

## Verification Checklist

- [ ] Functional test: detail viewport at mismatched aspect → no out-of-crop geometry, asserted via rendered coverage **and** through `paper_export.render_sheet` (PDF parity). Red-verified.
- [ ] Functional test: post-grip effective scale == stated scale; `w/h == crop×scale`.
- [ ] Functional test: `render_sheet` of a plan with elevation markers → zero `ViewMarkerArrow`/`SharedCropBox` output; on-screen still shows them on marker selection.
- [ ] Functional test: detail self-hide; host-plan default-on; per-sheet hide removes one box on one sheet while it persists on another; nested still shows.
- [ ] Functional test: title block not selectable; sheet selection surfaces Rev/Date/Edit-Revisions; edits undoable + dirty.
- [ ] Functional test: save/load round-trips `crop_rect` + `hidden_detail_ids`; legacy migration snaps to honest scale.
- [ ] Full suite green (chunked); smoke-test on a real sheet with a placed detail, elevation markers, and a revision entry; verify the exported PDF.
- [ ] Fold D1–D3 into `docs/specs/paper-space.md`; record the elevation/detail paper contract + section-view "will plot" intent in `docs/specs/view-relationships.md`; stamp `last-verified`/`verified-commit`.

## Out of Scope / Filed Follow-ups

- Crop-window **panning** at fixed size (v1 is resize-only).
- Per-revision **"By"/"Approved By"** column (P3).
- Section-view marker subsystem (unbuilt; will plot when built — recorded as intent only).
