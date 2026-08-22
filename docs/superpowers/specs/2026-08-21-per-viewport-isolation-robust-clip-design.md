# Per-Viewport View Isolation + Robust Crop Clip — Design

**Date:** 2026-08-21
**Status:** approved (brainstorm) — "what" locked via grill; "how" settled; pending implementation plan
**Branch:** `feat/paper-space-crop-cluster`
**Governing specs to update on completion:** `docs/specs/paper-space.md` (§6.2 render flow), `docs/specs/view-relationships.md`
**Primary modules:** `paper_space.py`, `paper_display.py`, `main.py`, `level_manager.py` (read), `detail_view.py` (read)
**Source task:** todo.md — "Per-viewport view isolation + robust crop clip (P1 follow-up to the crop cluster)"

---

## Goal

Make each paper-space viewport plot **its own bound view**, cropped honestly:

1. A plan/detail viewport shows the geometry of *its* level and cut-plane, regardless of which level/plan is active on-screen (#2/#3/#4).
2. No geometry of any item type bleeds past the crop edge — including `ItemIgnoresTransformations`-child items (gridline bubbles/leaders, walls) — with vector-preserving output (#1, closes concern-1 PARTIAL).

## Motivation

`ViewResolver._resolve_plan`/`_resolve_detail` both return the single live model scene, whose visibility is whatever `LevelManager.apply_to_scene` last set for the on-screen active level. A viewport never applies *its own* view's level before `scene.render()`, so a Level-3 detail plots Level-1 content when Level 1 is active, a plan viewport plots the last-active plan, and non-active-level construction geometry doesn't plot at all. Separately, `setClipRect(fitted)` is not honored for ITT-child items under off-screen `scene.render()`, so the crop leaks — the crop cluster shipped concern 1 PARTIAL.

## Architecture & Constraints

- **Single render path** (unchanged): `SheetViewport.paint()` drives both screen preview and `paper_export.render_sheet`. Fixing `paint()` fixes both — parity by construction.
- **Shared live scene.** Isolation mutates the *shared* model scene's per-item visibility/opacity/selectable/Z (via `apply_to_scene`) during the paper pass, then must restore it exactly. This is the central risk.
- **Reuse the established save/apply/restore idiom** (`apply_paper_overrides`/`restore_model_display`; copy-to-level at `model_space.py:9524`). No parallel machinery.
- **No new persisted state / no `.fpd` schema change / no migration** (locked scope boundary).
- **House rules:** plotted PDF is the visual gate; tests use REAL domain items + assert on rendered pixels; red-verify.

## Design Decisions

### D1 — Level-context resolution belongs to `ViewResolver`
`_apply_plan_level` (main.py:1046) and `_apply_detail_level` (main.py:1203) already resolve `(level_name, view_height, view_depth)` for a plan/detail name (incl. detail→plan inheritance). Relocate that resolution so a viewport can obtain its own context without going through `main.py`:
- `ViewResolver` gains a `_level_manager` ref and `resolve_level_context(view_type, view_name) -> (level_name, view_height, view_depth) | None` (elevation → `None`, already isolated).
- `main._apply_plan_level`/`_apply_detail_level` refactor to call the shared resolver (one home for the resolution; kills the duplication).

### D2 — Level apply/restore wraps the render in `paint()`
Around the existing `apply_paper_overrides` → `render` → `restore_model_display` block:
1. Snapshot the scene's restore context: `active_level`, `active_view_key`.
2. If `resolve_level_context` yields a context, `level_mgr.apply_to_scene(scene, level, vh, vd)` + set `active_level`/`active_view_key` to this viewport's view (so the underlay `hidden_in_views` sweep at `level_manager.py:502` uses the right key).
3. `apply_paper_overrides` (runs on now-correct visible set) → `render` → `restore_model_display`.
4. **Restore** by re-applying the snapshot's active view context (mirrors `model_space.py:9524`), in `finally`.

Ordering matters: level visibility first (hides off-level items) so `apply_paper_overrides` (which only touches visible items) naturally skips them.

### D3 — Echo suppression extends over the level mutations
The `_suppress_paper_echo` window (currently around the override block) must widen to cover `apply_to_scene` apply **and** restore, so the extra `changed` emissions don't re-dirty sibling viewports → repaint loop.

### D4 — Performance mitigation — v1 = no-op skip; batching filed as follow-up
Naive cost = N viewports × 2 full-scene sweeps (apply + restore) per paint, and `changed` fires often. **v1 (this task):**
- **No-op skip:** track the currently-applied paper level on the scene; a viewport re-applies `apply_to_scene` only when its `(level, vh, vd)` differs from what's already applied; the shared restore runs once the applied level differs from the on-screen active level. On the common case (viewports sharing a level) this collapses N sweeps toward 1.
**Filed follow-up (only if smoke test lags on a many-distinct-levels sheet):** render-session batching in `paper_export.render_sheet` — group viewports by level, apply once per distinct level, restore once at session end. Perf ceiling stays a hard acceptance criterion — this escalation is in-scope this task if the budget is blown.

### D5 — Robust crop clip — investigation-gated; vector-first (spike-informed)
**Spike finding (2026-08-21, throwaway, real `Model_Space` + `WallSegment` + `GridlineItem` → `QImage`):** the bleed is **not a `setClipRect` failure**. `ItemIgnoresTransformations` children (gridline bubbles) compute a **degenerate device position** under off-screen `scene.render()` (ITT position math needs a view) and render at the *wrong* place — landing *inside* the clip region rather than being culled. All vector-clip variants (`setClipRect`, `setClipPath`, re-asserted `IntersectClip`) behaved identically → swapping the clip primitive does **not** fix it.

Leading fix is therefore vector-preserving and already half-present: `_apply_gridline` (paper_display.py) already turns ITT **off** for bubbles via `enter_paper_mode` during the paper pass. The plan's **first clip task is a systematic-debugging spike on real project geometry** to confirm exactly which items still bleed (bubbles despite `enter_paper_mode`? leaders? walls — and *why* a wall carries an ITT child) and then pick, in order of preference:
- **(a, preferred) Extend ITT-off coverage** during the paper pass to every offending item type — vector-preserving, cheap, matches the existing gridline pattern.
- **(b) Targeted geometry clip** for any item that genuinely cannot drop ITT.
- **(c) Intermediate-pixmap raster fallback** — render the viewport to a pixmap, clip, blit; rasterizes that region (loses vector). **Escalation only, needs explicit user approval.**

**Honest caveat:** a pure-vector fix for *every* case can't be guaranteed until the real-geometry spike runs; the spike strongly suggests (a) covers it, and (c) is never reached silently.

### D6 — Unresolvable level context degrades, never crashes
View resolves but level context is empty → render with no isolation (today's behavior); still restore the live scene cleanly.

## Acceptance Criteria (locked in grill)
- [ ] Paper viewport's visible-item set == the on-screen view of the same name (level + cut-plane), even with a different level active on-screen — asserted in rendered pixels.
- [ ] Zero non-background pixels outside `fitted` for any item type (walls, gridline bubbles/leaders) at any size/aspect; identical in preview and exported PDF.
- [ ] Exported PDF clipped content stays vector; rasterization only as an approved escalation.
- [ ] After any preview/export, live scene restored exactly to the currently-active on-screen level — incl. mid-render `paint()` throw (`finally`).
- [ ] No new repaint loop / model-canvas flicker; `changed`/repaint settles to zero.
- [ ] No perceptible editing lag on a representative multi-viewport sheet; mitigation in-scope if blown.
- [ ] No new persisted state / no schema change / no migration.
- [ ] Unresolvable level context still renders (no-isolation) + restores cleanly.

## Testing Expectations (gaming-proof gate)
- [ ] Real domain items only (`WallSegment`, `GridlineItem`, real `Model_Space`, real levels) — never `QGraphicsRectItem` stand-ins.
- [ ] Assert on rendered pixels via `paper_export.render_sheet` / `PaperScene.render` → `QImage`, not method-call spies/flags.
- [ ] Every test red-verified (fails with fix reverted).
- [ ] Final gate: user smoke-tests a real exported PDF (real walls, gridlines, levels, placed detail).

## Verification Checklist
- [ ] All acceptance criteria met; full suite green (chunked).
- [ ] Fold D1–D6 into `docs/specs/paper-space.md §6.2`; record isolation contract in `view-relationships.md`; stamp `last-verified`/`verified-commit`.

## Out of Scope / Filed Follow-ups
- Stale-binding cascade repair (renamed/deleted level → viewport/underlay bindings).
- Per-viewport arbitrary-level pinning (would need stored state).
- Crop-window panning at fixed size.
