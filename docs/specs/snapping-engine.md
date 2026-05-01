# Snapping Engine — Specification

> **Status:** North-star design + decomposed roadmap (spec-only — no code changes delivered by this document)
> **Source files:** `firepro3d/snap_engine.py`, `firepro3d/model_view.py`, `firepro3d/model_space.py`, `firepro3d/dxf_preview_dialog.py`, `firepro3d/annotations.py` (HatchItem)
> **Date:** 2026-04-07
> **Revision:** 1 (post grill + brainstorm session)

---

## 1. Goal & Motivation

### 1.1 Goal

Define a coherent, polished, AutoCAD-style Object Snap (OSNAP) subsystem for FirePro3D, document the gap between today's `snap_engine.py` and that target, and decompose the gap into a prioritized roadmap of focused follow-up tasks.

### 1.2 Primary objective: recall first

> **The engine MUST surface every snap candidate the user reasonably expects.**
> Minimizing noise candidates is a secondary objective. When the two conflict, recall wins.

Rationale: a *missed* snap breaks flow (the user has to zoom, hunt, or place free-hand) whereas a *noisy* snap is visible and recoverable (the user sees the wrong marker and nudges the cursor). Misses are rarer but more costly to a drafting session.

### 1.3 Ranked pain points (drives the roadmap)

| Rank | Pain | Where it shows up |
|---|---|---|
| 1 | **Wrong-target detection** — engine picks the wrong snap, or fails to surface the right one | §6, §7 |
| 2 | **Tolerance sweet-spot is hard to dial in** | §13 (deferred, but acknowledged) |
| 3 | **Quality regresses as features are added** — no test safety net | §10 |
| 4 | **No coherent design doc** — system feels pieced together | This document |

### 1.4 Why now

The snapping engine has a disproportionate impact on drafting throughput. Pain #1 has been observed reproducibly (wall-corner case study, hatch-noise case study — see §7). The engine has accreted feature-by-feature without a written reference, and the next planned subsystems (inferred placement, snap-from, apparent intersection — see §2) all assume a stable OSNAP foundation. Specing now produces a foundation; deferring guarantees the next subsystem inherits the same pain.

---

## 2. Scope

### 2.1 In scope (this spec)

- The OSNAP subsystem: object snap to features of existing scene geometry.
- Audit of which item types should and should not contribute snap candidates.
- Description of the current pick algorithm and the target pick algorithm.
- **Named/semantic snap targets** on complex objects (walls now, pipes-with-fittings near-term) — borrowed from Revit.
- Test strategy (described, not implemented).
- A decomposed roadmap of follow-up TODO items (§12).

### 2.2 Adjacent (named, lightly described, not specced)

- **Ortho mode** — currently implemented inside `Node.snap_point_45` and orthogonal-constraint logic in `model_space.py`, separate from `snap_engine.py`. Shares the F-key UX surface and the user can't always tell ortho from OSNAP in practice. Mentioned in §9 so the keyboard contract is internally consistent; not redesigned here.

### 2.3 Deferred (out of scope, with reason — each is a candidate future spec)

| Subsystem | Reason for deferral |
|---|---|
| Tolerance auto-tuning UX | Pain #2; meaningful only after recall is fixed. Future spec inherits a dataset from this work — see §13. |
| New snap types (parallel, extension, from, apparent intersection) | Feature work, not review work. Belongs in subsystem-specific specs. |
| OSNAP toolbar UI for per-type toggles | UX feature. The keyboard/marker contract here gives the future toolbar a target. |
| Performance / O(n²) intersection scans | Only address if profiling reveals it as a *recall* bottleneck. Premature otherwise. |
| 3D / multi-level snap behavior | Belongs in the views-relationship spec (separate P1 task). |
| Polar tracking | Separate subsystem; AutoCAD treats it independently of OSNAP. |
| Grid snap (snap to a regular spacing independent of objects) | Separate subsystem; FirePro3D currently uses gridlines as objects, not as a spacing constraint. |
| Object snap tracking (OTRACK) | AutoCAD's killer feature for offset placement; deserves its own spec. |
| **Inferred / dimension-driven placement** (Revit's spine) | **Flagged as the next priority spec after this one.** |
| Snap-from / temporary tracking | Subsystem of OTRACK family. |
| Apparent intersection | 3D feature; couples to multi-level snap. |

---

## 3. Reference model

### 3.1 Spine: AutoCAD

The existing `snap_engine.py` is already AutoCAD-shaped: priority-banded picker, marker colors per snap type, per-type boolean toggles, single `find()` call returning one best snap. FirePro3D's users (fire protection drafters) are overwhelmingly AutoCAD-trained, and recall-first is easier to audit in AutoCAD's flat "what does this item type produce?" model than in Revit's contextual "what does the active tool ask for?" model.

**AutoCAD conventions adopted:**

| Convention | How it lands in FirePro3D |
|---|---|
| **Running OSNAPs**, persistent until toggled | Per-type instance booleans on `SnapEngine` (already present). UI toggle surface deferred to a future toolbar spec. |
| **Single-key one-shot overrides** (`END`, `MID`, `INT`, `CEN`, `NEA`, `PER`, `TAN`, `QUA`) | Reserved as a future keybinding addition. Not delivered by this spec, but the snap-type names in §4 must match the AutoCAD short names so the future bindings are unambiguous. |
| **F-key global toggle** for OSNAPs | F3 reserved (matches AutoCAD muscle memory). Currently no binding — added as a roadmap item. |
| **AutoSnap marker + tooltip** as the core UX surface | Markers are present (§9). Tooltips deferred — note the named-target decision in §8 uses marker variants instead. |
| **Marker colors carry meaning** (each snap type its own color) | Current `SNAP_COLORS` dict already follows this. Locked. |
| **Snap tolerance is a screen-pixel constant**, not a scene-unit one | Current `SNAP_TOLERANCE_PX = 40` follows this. Locked, even though tuning is deferred. |

**AutoCAD conventions explicitly rejected:**

| Convention | Reason for rejection |
|---|---|
| Separate **AutoSnap aperture** vs **snap aperture** as two tunables | One tolerance constant is enough; two confuses users and bloats the future tolerance UX. |
| **Gravity** (cursor pulled visually toward snap) | Conflicts with FirePro3D's free-cursor expectation; the marker is the indicator, the cursor doesn't move. |

### 3.2 Borrowed from Revit: named/semantic targets

AutoCAD treats every "endpoint" the same — yellow square, no semantic distinction. This breaks down on complex objects like walls, where a single `WallSegment` exposes two centerline endpoints, four quad-corner points (face × end), and several edge midpoints, all rendered identically. The user has no way to disambiguate "snap to wall corner (outer face)" from "snap to centerline end" — they're both yellow squares competing for the same pixel.

Revit solves this by making targets **named** ("centerline-end-A", "face-left-corner-B"). FirePro3D borrows the *concept* but stays inside the AutoCAD picker model: see §8.

### 3.3 Not borrowed from Revit

| Concept | Reason for rejection |
|---|---|
| Contextual snap-by-tool (different snaps depending on whether you're placing a wall vs a duct) | Violates AutoCAD predictability; recall harder to audit. |
| Inferred dimension guides | This is a separate subsystem (§2.3). Belongs in the next spec. |
| "Aligns with face of wall above" alignment guides | This is OTRACK (§2.3). Deferred. |

---

## 4. Snap type catalog

Eight snap types are defined today. Status reflects the engine's current behavior, not the target.

| Type | Marker | Color | AutoCAD short | Priority | Produced by | Status |
|---|---|---|---|---|---|---|
| **endpoint** | square | `#ffff00` yellow | `END` | 1 | Line endpoints, polyline vertices, rectangle corners, arc start/end, wall centerline ends, wall face corners, generic path vertices | works |
| **midpoint** | triangle | `#00ff88` green | `MID` | 2 | Line midpoints, polyline segment midpoints, rectangle edge centers, wall centerline midpoint, wall face-edge midpoints, arc angular midpoint | works |
| **intersection** | x-cross | `#ffff00` yellow | `INT` | 0 | Gridline×gridline (phase 2), segment×segment and segment×circle (phase 4) | works — same-parent suppression (§6.3 Change A) + endpoint protection band (§6.3 Change B) fix prior over-aggressiveness; gridline intersections now compete via standard picker instead of force-winning |
| **center** | circle | `#00eeee` cyan | `CEN` | 3 | Circle/ellipse centers, rectangle centers, arc centers | works |
| **quadrant** | diamond | `#ff8800` orange | `QUA` | 5 | Circle 0°/90°/180°/270° points, arc quadrant points within angular range | works |
| **perpendicular** | right-angle | `#ff00ff` magenta | `PER` | 4 | Foot-of-perpendicular onto any line/segment/wall edge/rectangle edge/polyline segment/arc/circle (cursor-dependent) | works |
| **tangent** | tangent-circle | `#88ff00` lime | `TAN` | 6 | Tangent line from cursor to a full circle | **bug** — only implemented for `QGraphicsEllipseItem` full circles. Arcs do not produce tangent candidates. |
| **nearest** | cross | `#aaaaaa` grey | `NEA` | 7 | Closest point on a segment (fallback only — currently emitted by `_geometric_snaps` only when perpendicular is disabled) | **buggy** — coupling to perpendicular toggle is non-obvious; nearest is effectively unavailable when perpendicular is on |

---

## 5. Item type × snap type matrix

Rows are item types currently handled by `SnapEngine._collect()` (and adjacent paths in `_check_scene_items`, `_check_geometry_intersections`). Cells use a four-state vocabulary:

- **✓** — supported and works
- **plan** — planned by this spec, not implemented
- **N/A** — does not apply by design (rationale in notes if needed)
- **bug** — should work but doesn't, or works wrongly (becomes a §12 roadmap item)

| Item type | end | mid | int | cen | qua | per | tan | nea |
|---|---|---|---|---|---|---|---|---|
| `LineItem` | ✓ | ✓ | ✓ (via phase 4) | N/A | N/A | ✓ | N/A | bug¹ |
| `ConstructionLine` | ✓ | ✓ | bug² | N/A | N/A | **bug²** | N/A | **bug²** |
| `GridlineItem` | ✓ | ✓ | ✓ (phase 2 + 4) | N/A | N/A | ✓ | N/A | bug¹ |
| Generic `QGraphicsLineItem` (`Pipe`) | ✓ | ✓ | ✓ (phase 4) | N/A | N/A | ✓ | N/A | bug¹ |
| `RectangleItem` | ✓ (corners) | ✓ (edge centers) | ✓ (phase 4) | ✓ | N/A | ✓ | N/A | bug¹ |
| `QGraphicsEllipseItem` (full circle) | N/A | N/A | ✓ (phase 4 vs segments) | ✓ | ✓ | ✓ | ✓ | bug¹ |
| `QGraphicsEllipseItem` (Node) | N/A | N/A | N/A | ✓ | N/A (suppressed) | N/A | N/A | N/A |
| `WallSegment` | **bug³** | ✓ (centerline + face mids) | **bug⁴** | N/A⁵ | N/A | ✓ (5 segments) | N/A | bug¹ |
| `PolylineItem` | ✓ (vertices) | ✓ (segment mids) | ✓ (phase 4) | N/A | N/A | ✓ | N/A | bug¹ |
| `ArcItem` | ✓ (start/end) | ✓ (angular) | ✓ (phase 4 vs segments) | ✓ | ✓ (in-range) | ✓ (closest on circumference) | **bug⁶** | bug¹ |
| Generic `QGraphicsPathItem` (DXF) | ✓ (vertices) | ✓ (segment mids) | ✓ (phase 4) | N/A | N/A | ✓ | N/A | bug¹ |
| `HatchItem` (subclass of `QGraphicsPathItem`) | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

**Notes:**
1. ~~**Nearest is unreachable when perpendicular is on.**~~ **Fixed 2026-04-08** (roadmap item 5). `_geometric_snaps` now emits `perpendicular` and `nearest` as independent candidates; the picker's priority band resolves the winner. Regression test: `tests/test_snap_nearest_perpendicular_decoupling.py`.
2. **ConstructionLine semantics are inconsistent with its visual.** `ConstructionLine` IS a `QGraphicsLineItem` subclass (`construction_geometry.py:54`), so phase-1 `_geometric_snaps` fires its line branch — but via `item.line()`, which returns the *extended drawn* line, not the `pt1`/`pt2` anchors. Phase 4 (`_check_geometry_intersections` line 335) treats it as a **finite** segment between `pt1`/`pt2`, missing intersections outside the anchor range even though the line is conceptually infinite. **Deferred** (roadmap item 4 downgraded to P3): the ConstructionLine two-click tool is effectively unused; revisit if/when the feature sees real usage.
3. `WallSegment` *does* emit endpoints today (centerline ends + 4 face corners), but the picker drops them in favor of nearby intersections — see case study §7.1. Tagged **bug** because the user-visible behavior is "endpoint missed" even though the candidate exists.
4. `WallSegment` contributes its two face edges as segments to phase 4. When two walls meet, this produces *real* corner intersections (good) but also produces wall-internal face crossings between same-parent edges, which the picker treats as ordinary intersections (bad). See §6 and §7.
5. Walls have no meaningful geometric center. Marked N/A by design.
6. Tangent is implemented only for full `QGraphicsEllipseItem`; the `ArcItem` branch in `_geometric_snaps` produces perpendicular but not tangent.
7. ~~Generic `QGraphicsPathItem` items (DXF imports) emit endpoints and midpoints in `_collect`, but `_check_geometry_intersections` has no branch for them.~~ **Fixed.** Phase 4 now extracts segments from `QGraphicsPathItem` items (DXF imports) and `_phase4_items()` descends into underlay groups. DXF path items fully participate in phase-4 intersection scans.

**`HatchItem` is intentionally all-N/A.** It is correctly skipped in phase 1 and matches no branch in phase 4, so it contributes zero candidates today. The hatch-noise case study (§7.2) is *not* caused by HatchItem leakage — see that section for the real cause.

---

## 6. Pick algorithm

### 6.1 Current algorithm (4 phases + priority-band picker)

`SnapEngine.find()` runs four phases in order, each calling `_SnapCtx.check()` to compare candidates against the running best:

1. **Phase 1 — Scene items in search rect.** Iterates `scene.items(search_rect)`. Child items are checked first: children of `DXF Underlay` / `PDF Underlay` groups are descended into for `_collect()` snaps (endpoint/midpoint/center/quadrant); all other child items are skipped. Top-level items skip `DimensionAnnotation`, `NoteAnnotation`, `HatchItem`, the origin marker, items above z=150, pipes (in design-area mode), and underlay groups themselves. For each surviving top-level item, calls `_collect()` for static snaps and `_geometric_snaps()` for cursor-dependent snaps (perpendicular/nearest/tangent).
2. **Phase 2 — Gridline×gridline intersections.** Pairwise iterates visible gridlines, computes intersection points, and routes them through `_SnapCtx.check()` with the standard priority-band picker (no longer force-wins over other candidates).
3. **Phase 3 — Gridline static + perpendicular snaps.** Calls `_collect()` and `_geometric_snaps()` for each visible gridline (gridlines have a bubbles-only `shape()` so they're missed by `scene.items(search_rect)`).
4. **Phase 4 — Geometry×geometry intersections.** Re-iterates `scene.items(search_rect)` via `_phase4_items()`, which descends into DXF/PDF underlay groups. Extracts segments from `ConstructionLine`, `QGraphicsLineItem`, `PolylineItem`, `RectangleItem`, `WallSegment`, `QGraphicsPathItem` (DXF geometry), and circles from `CircleItem`. Pairs them all and emits `intersection` candidates for any crossing within tolerance. Each intersection candidate carries both source items (`source_item`, `source_item2`) and the actual segment geometry (`source_lines`) for per-segment highlighting.

The **picker** (`_SnapCtx.check()`) uses a "priority band":

```
band = tolerance × 0.3   # ≈ 12px at the default 40px tolerance

A candidate becomes the new best if:
  • it's strictly closer than (best_dist − band), OR
  • it's within (best_dist + band) AND has higher priority (lower number)
```

Priorities (`SNAP_PRIORITY` dict): `intersection=0`, `endpoint=1`, `midpoint=2`, `center=3`, `perpendicular=4`, `quadrant=5`, `tangent=6`, `nearest=7`.

### 6.2 Why this algorithm produces the case-study bugs

The combination **`intersection=0` + 12px priority band + phase 4 emitting wall-internal face crossings** is the root cause of both case studies in §7.

Concretely: when the cursor is near a wall corner, phase 1 emits the corner as `endpoint` (priority 1). Phase 4 finds the crossing of that wall's left and right face edges (a real geometric intersection inside the wall thickness, near the corner) and emits it as `intersection` (priority 0). Both are within the 12px priority band of each other. The picker rule prefers the higher-priority candidate within the band, so **the intersection wins and the endpoint is silently suppressed**. The user sees the cyan/yellow X marker drift toward the wall thickness instead of locking to the corner.

The same mechanism explains the hatch case study: the wall's face edges run alongside the visual hatch fill (since the hatch lives between the two faces), and a face×face intersection that the user perceives as "snapping to the hatch line" is actually a phase-4 intersection between the two wall faces. `HatchItem` itself contributes nothing to the snap pool — the original "missing HatchItem filter" hypothesis is wrong.

### 6.3 Target algorithm

Three changes, all to the picker and the phase-4 emitter. Each is described as a *design direction*, not a code-level fix.

**Change A — Same-parent intersection suppression.** A phase-4 intersection candidate whose two source segments belong to the *same* parent object (both faces of one wall, two segments of one polyline, etc.) is filtered out before reaching the picker. Cross-object intersections (wall A's face × wall B's face, pipe × gridline, etc.) are unaffected. This is the surgical fix: it preserves all real intersections while killing the geometrically meaningless internal ones.

**Change B — Endpoint protection band.** When an `endpoint` candidate exists within tolerance of the cursor, intersection candidates within a smaller protection radius (recommended: half the priority band, ≈6px) of that endpoint are suppressed. This protects endpoints generally — not just for walls — against any intersection that happens to land near a corner. Composes with Change A but is independent of it; either alone partially fixes the bugs, both together fix them robustly.

**Change C — `intersection` priority remains at 0**, *not* dropped to 1. The brainstorming session considered dropping intersection to priority 1 (tied with endpoint, distance breaks ties) as a simpler alternative. **Rejected** because it changes the picker's behavior across every cross-object intersection in the engine, breaking muscle memory in cases where intersection-wins-over-endpoint is actually correct (e.g. snapping to where a pipe crosses a gridline near a node — the user wants the crossing, not the node). Changes A + B fix the wall-internal case without this side effect.

The target picker, in prose: *"Within the priority band, higher priority wins as today, except (i) intersection candidates whose source segments share a parent are dropped before reaching the picker, and (ii) intersection candidates within ~6px of any in-tolerance endpoint candidate are also dropped."*

**This document does not specify the implementation.** The roadmap items in §12 cover the implementation as separate one-session tasks.

---

## 7. Case studies

### 7.1 Wall corner missed (false negative)

**User action.** Drafting a new wall in plan view. Cursor approaches the existing wall corner (outer face × end-cap intersection).

**Expected behavior.** Yellow square marker on the wall corner; click locks the new wall's start to that point.

**Observed behavior.** No corner marker. The yellow X-cross intersection marker appears slightly offset *into* the wall thickness, snapping to a point that isn't visually meaningful. Workaround: zoom in until the offset becomes obvious, then nudge the cursor toward the corner; sometimes this resolves, sometimes not.

**Root cause.** §6.2: phase 4 emits a `wall-left-face × wall-right-face` intersection inside the wall thickness, near the corner. That intersection has priority 0; the corner endpoint has priority 1. Both are within the 12px priority band. The picker prefers the higher priority within the band, so the intersection wins and the endpoint is suppressed.

**Fix shape.** §6.3 Change A (same-parent suppression) eliminates the wall-internal face crossing. §6.3 Change B (endpoint protection band) provides defense in depth for any future case where a cross-object intersection happens to land near an endpoint. Verification: a regression fixture that places two `WallSegment` instances in an L joint and asserts that `find()` returns a `(snap_type='endpoint', source_item=<wall>)` for cursor positions within tolerance of the corner.

### 7.2 Hatch detected as intersection (false positive)

**User action.** Hovering near a wall whose interior is filled with a diagonal hatch pattern, while drafting another object.

**Expected behavior.** Snap to the wall's centerline, face edges, corners, or midpoints — whatever is appropriate. Definitely not to the hatch.

**Observed behavior.** Yellow X-cross intersection markers appear at points that visually coincide with hatch line positions inside the wall.

**Original misdiagnosis (corrected by this spec).** The earlier hypothesis was that `HatchItem` was leaking through phase 4 because `_check_geometry_intersections` lacks the `HatchItem` filter that `_check_scene_items` has. **This is wrong.** `HatchItem` extends `QGraphicsPathItem` and matches *no* branch in phase 4's segment/circle extractor (`ConstructionLine`, `QGraphicsLineItem`, `PolylineItem`, `RectangleItem`, `WallSegment`, `CircleItem`). It contributes zero segments today regardless of any filter.

**Real root cause.** Identical to §7.1. The "hatch intersections" the user sees are phase 4's wall-internal face×face crossings — the hatch fill happens to live in exactly the same physical region (between the two wall faces), so a face×face intersection visually appears to be "on the hatch." This was concealed by the visual coincidence.

**Fix shape.** §6.3 Change A is sufficient. Change B is a no-op for this case (no nearby endpoint to protect) but harmless.

**Why the misdiagnosis matters.** A future engineer reading this case study without §6 would have spent a session adding a `HatchItem` filter to phase 4, found the bug unfixed, and chased it elsewhere. The corrected diagnosis is a load-bearing piece of this spec.

### 7.3 Additional case studies

The §5 matrix audit surfaces the following lower-severity bugs that also become roadmap items but do not need full case-study walk-throughs:

- **`ConstructionLine` has no perpendicular, no nearest, and contributes no phase-4 intersections** (matrix note 2). Single root cause (`isinstance` check is wrong type) but three user-visible failures.
- **`nearest` is unreachable on every line-bearing item type when perpendicular is on** (matrix note 1). The `_geometric_snaps` emitter uses `if perpendicular: ... elif nearest: ...`, so `nearest` is only available when perpendicular is explicitly toggled off. Users expect both to compete by distance + priority.

---

## 8. Named-target extension (Revit borrow)

### 8.1 Concept

Some item types expose multiple geometrically distinct snap targets that all share the same snap *type* (e.g. a wall has both "centerline endpoint" and "face-corner endpoint" — both are `endpoint` candidates rendered as yellow squares). The user has no way to disambiguate.

The fix is to attach a **semantic name** to each emitted candidate, and to render named candidates with **marker glyph variants** — chosen over tooltip text (Q1 of the brainstorm session) for visual consistency with AutoCAD's marker-driven UX.

### 8.2 Marker glyph variants (v1)

Two new variants, additive to the existing 8 marker glyphs:

| Variant | Used by | Meaning |
|---|---|---|
| **hollow square** (yellow outline, transparent fill) | `WallSegment` face-corner endpoints | Endpoint that lives on the wall *face*, not the centerline. |
| **hollow triangle** (green outline, transparent fill) | `WallSegment` face-edge midpoints | Midpoint of a wall *face edge*, not the centerline. |

The existing **outlined** square and **outlined** triangle continue to mean "centerline endpoint / midpoint" or "ordinary endpoint / midpoint on simple objects." **Outlined = primary / centerline / default; filled = secondary / face** — the rule was inverted during implementation (April 2026) because all pre-existing markers in FirePro3D were already rendered outlined, and introducing new outlined variants would have required changing every non-wall glyph. The user-facing disambiguation is preserved: at an L-joint the filled face-corner glyph reads clearly against the outlined centerline-end glyph. See roadmap item 3.

### 8.3 Item type coverage

| Item type | Named targets | Status |
|---|---|---|
| `WallSegment` | centerline-end-A, centerline-end-B, centerline-mid, face-left-corner-A, face-left-corner-B, face-right-corner-A, face-right-corner-B, face-left-mid, face-right-mid | **planned by this spec** (roadmap §12 item 3) |
| `Pipe` (with attached `Fitting`) | centerline-end-A, centerline-end-B, fitting-port-N | **planned (future spec)** — pipe-with-fitting named targets are large enough to merit their own design session (see §12 item 13) |
| All other item types | none | N/A — no disambiguation needed |

**T-joint inferred targets (deferred).** When one wall terminates into the face of another, there is no candidate at the T-point today (neither endpoint nor phase-4 intersection; the walls do not cross). This is an *inferred* target — it belongs to the wall placement / joinery spec (tracked in `TODO.md` as a separate P1 spec & grill session, surfaced 2026-04 during the item-3 grill) and to the inferred-placement subsystem (roadmap item 14). This spec commits only to the L-joint case, which is handled by items 1 + 3.

### 8.4 Picker integration

Named targets do **not** introduce new entries into `SNAP_PRIORITY`. They share priority with the underlying snap type (face-corner endpoints are still priority 1, etc.) and compete on distance with all other endpoints. The only difference is the marker glyph used to render them. This keeps the picker algebra unchanged and confines the change to (a) `_collect()` emitting `(snap_type, point, name)` triples instead of `(snap_type, point)` pairs, and (b) the foreground marker renderer choosing a variant glyph when a name is present.

---

## 9. UX surface

### 9.1 Markers

The 8 base marker glyphs from §4 plus the 2 named-target variants from §8 are the entire visual surface. Marker color carries snap-type meaning (locked from §3); marker shape carries snap-type identity; marker fill (solid vs hollow) carries named-target distinction on objects that have one.

### 9.2 Marker rendering rule

Exactly one marker is drawn per `find()` call. If `find()` returns `None`, no marker. If multiple candidates tie on the picker, the picker breaks the tie deterministically (first-found wins after Changes A + B from §6.3).

### 9.2.1 Snap trace highlighting

When a snap result has a `source_item`, `Model_View.drawForeground()` draws a dashed-line trace in the snap type's color. Highlighting rules:

- **Intersection snaps with `source_lines`:** Only the two participating segments are drawn (not the full source items). This prevents entire DXF rectangles or multi-segment paths from lighting up when only two edges intersect.
- **Endpoint/midpoint on `QGraphicsPathItem`:** Only the 1–2 segments adjacent to the snap point are drawn, found by proximity check against path vertices and segment midpoints (1 mm² scene tolerance). Falls back to the full path if no adjacent segments match.
- **Simple items** (`QGraphicsLineItem`, `QGraphicsEllipseItem`, `QGraphicsRectItem`): The full item is drawn.
- **Both source items** (`source_item` + `source_item2`) are traced when present (intersection snaps always populate both).

### 9.3 Tooltip text

**Not adopted in v1.** AutoCAD's AutoSnap tooltip is desirable but adding it now competes with the marker-variant disambiguation chosen in §8. If user testing of the marker variants reveals they're not enough, tooltip text becomes a roadmap follow-up.

### 9.4 Keyboard contract

Reserved bindings (not bound today, do not implement in this spec, but no other feature should claim them):

| Key | Function | Notes |
|---|---|---|
| **F3** | Toggle all OSNAPs on/off (matches AutoCAD) | Roadmap item §12 item 11 |
| **`END`, `MID`, `INT`, `CEN`, `QUA`, `PER`, `TAN`, `NEA`** typed at the command prompt | One-shot snap override for the next pick | Deferred to the future OSNAP toolbar / command-line spec |

### 9.5 Status bar

A future OSNAP toolbar (deferred — §2.3) is the natural home for per-type toggle indication. This spec only commits to: the status bar must, at minimum, show whether OSNAPs are globally on or off when F3 is bound.

**2026-04-08 finding (roadmap item 12):** A code search of the project confirmed that no UI surface currently toggles the per-type `SnapEngine` booleans (`snap_endpoint`, `snap_midpoint`, `snap_intersection`, `snap_center`, `snap_quadrant`, `snap_nearest`, `snap_perpendicular`, `snap_tangent`). They remain reachable only by direct attribute access. The per-type toggle UI is therefore formally deferred to a dedicated OSNAP-toolbar spec session, which has been promoted from "deferred" to a P1 backlog task. The persistent OSNAP status-bar indicator delivered alongside this finding is the anchor the toolbar will later integrate with.

### 9.6 Settings persistence

Per-type toggle state is currently held only in `SnapEngine` instance attributes and is lost on application restart. The future toolbar spec inherits the responsibility to persist toggle state to `QSettings`. Not delivered here.

---

## 10. Test strategy

This spec **does not deliver tests**. It specifies what tests should exist so that pain #3 (regressions creep in) becomes detectable instead of vibes-based. Each item below is a candidate roadmap entry.

### 10.1 Layer 1 — Geometric primitive unit tests

`SnapEngine` contains three pure-function geometric primitives that have zero scene dependencies and are individually testable:

| Function | Test cases needed |
|---|---|
| `_line_line_intersect(a1, a2, b1, b2)` | Crossing inside both segments; crossing inside one but extension of the other; parallel; collinear overlapping; collinear non-overlapping; touching at endpoint; near-zero denominator (numerical edge) |
| `_line_circle_intersect(seg_a, seg_b, center, radius)` | Two intersections inside segment; two intersections one inside one outside; tangent (one intersection); no intersection; degenerate segment; degenerate radius |
| `_project_to_segment(pt, seg_a, seg_b)` | Foot inside segment; foot before `seg_a`; foot after `seg_b`; degenerate segment (returns `None`) |

### 10.2 Layer 2 — Matrix fixture tests

For every cell in the §5 matrix marked **✓** or **plan**, one fixture test that constructs a minimal `QGraphicsScene`, places one item of the row's type, and asserts that `SnapEngine.find()` returns the expected snap type at the expected point. Cells marked **bug** become regression fixtures *after* the bug is fixed (the test ships with the fix). Cells marked **N/A** get no test.

### 10.3 Layer 3 — Case study regression tests

One test per case study in §7. Each constructs the minimum scene necessary to reproduce the original bug and asserts the *target* algorithm behavior:

- §7.1: two `WallSegment` instances forming an L joint; assert corner endpoint wins.
- §7.2: one `WallSegment` with a `HatchItem` overlay; assert no `intersection` candidate is emitted from the wall's internal face crossings.

### 10.4 What is *not* tested

- No GUI / `QApplication` tests. All tests run headless against `QGraphicsScene` directly.
- No screenshot / image-diff tests of marker rendering — that's a future visual-regression initiative.
- No performance tests until profiling reveals a recall bottleneck.

---

## 11. Gap analysis

Single-line current-vs-target for each major section:

- **§3 reference model:** No written reference today → AutoCAD spine + Revit named-target borrow committed in writing.
- **§4 catalog:** 8 snap types defined in code without doc → catalog table exists, 3 types tagged buggy.
- **§5 matrix:** No item-type × snap-type audit ever performed → matrix exists; ~12 bug cells identified.
- **§6 picker:** Priority-banded picker with `intersection=0` suppressing endpoints; no documentation → target algorithm specified (Changes A + B); current algorithm explicitly described as the root cause of §7 bugs.
- **§7 case studies:** Two reproducible bugs, one with an actively misleading hypothesis → both reframed with shared root cause; misdiagnosis explicitly corrected.
- **§8 named targets:** All wall corners and centerline ends render as identical yellow squares → glyph-variant scheme defined for walls; pipes-with-fittings flagged as a future spec.
- **§9 UX surface:** Marker rendering only; no F-key, no tooltips, no toolbar → marker variants extended; F3 reserved; tooltip text deferred; toolbar deferred.
- **§10 test strategy:** Zero automated tests for `snap_engine.py` → three-layer test pyramid described (primitives, matrix fixtures, case-study regressions).
- **§13 deferred subsystems:** Tolerance, OTRACK, inferred placement, snap-from, apparent intersection — all in the user's head, none written down → all named in §2.3 with deferral reasons; "next priority" identified as inferred/dimension-driven placement.

---

## 12. Roadmap

Each item is sized for one focused work session (1–4 hours), closes at least one §5 matrix cell or §7 case study, carries a priority marker, and links back to the spec section that produced it.

| # | Pri | Subject | Done when | Ref |
|---|---|---|---|---|
| 1 | ~~done~~ | Implement same-parent intersection suppression (Change A) and endpoint protection band (Change B) in the picker | Both §7 case studies pass regression fixtures; no other matrix cell regresses | `[ref:snap-spec§6.3]` |
| 2 | **P1** | Phase-4 segment-source filter audit | `_check_geometry_intersections` only iterates item types whose §5 row contributes to phase 4 (`ConstructionLine`, `QGraphicsLineItem`, `PolylineItem`, `RectangleItem`, `WallSegment`, `CircleItem`); generic `QGraphicsPathItem` (DXF) added per matrix note 7 | `[ref:snap-spec§5,§6]` |
| 3 | ~~done~~ | `WallSegment` named-target marker variants | `_collect()` emits face vs centerline distinction; foreground renderer draws hollow squares for face corners and hollow triangles for face midpoints; legend updated | `[ref:snap-spec§8]` |
| 4 | **P3** (deferred) | Fix `ConstructionLine` perpendicular / nearest / phase-4 participation — deferred 2026-04-08: tool is effectively unused. See corrected matrix note 2. | All three matrix cells flip from **bug** to ✓; one regression test per cell | `[ref:snap-spec§5-row-ConstructionLine]` |
| 5 | ~~done~~ | Decouple `nearest` from the perpendicular toggle (matrix note 1) — **done 2026-04-08**. `_geometric_snaps` emits `perpendicular` and `nearest` as independent candidates in all three line/arc/circle branches. Regression test: `tests/test_snap_nearest_perpendicular_decoupling.py` | `nearest` is emitted whenever `snap_nearest` is on, independently of `snap_perpendicular`; the picker's priority band breaks ties as expected | `[ref:snap-spec§5-note-1]` |
| 6 | **P2** | `ArcItem` tangent support | `_geometric_snaps` arc branch emits tangent candidates when `snap_tangent` is on; matrix cell `ArcItem×tangent` flips to ✓ | `[ref:snap-spec§5-row-ArcItem]` |
| 7 | **P2** | Generic `QGraphicsPathItem` (DXF) phase-4 segments | Phase 4 extracts segment pairs from DXF path items; matrix cell flips from bug⁷ to ✓; regression test on a small DXF underlay fixture | `[ref:snap-spec§5-note-7]` |
| 8 | **P2** | Geometric primitive unit tests (§10.1) | `_line_line_intersect`, `_line_circle_intersect`, `_project_to_segment` covered by tests for every case in §10.1 tables | `[ref:snap-spec§10.1]` |
| 9 | **P2** | Matrix fixture test harness (§10.2) | One headless `QGraphicsScene` fixture test per ✓-cell in §5; harness pattern documented for future cells | `[ref:snap-spec§10.2]` |
| 10 | ~~done~~ | Case-study regression tests (§10.3) | Two regression tests pinned to §7.1 and §7.2 (in addition to the fixtures from item 1) | `[ref:snap-spec§10.3]` |
| 11 | ~~done~~ | Bind F3 to global OSNAP on/off and surface state in status bar | F3 toggles `SnapEngine.enabled`; status bar reflects current state | `[ref:snap-spec§9.4-§9.5]` `[done:2026-04-08]` |
| 12 | ~~done~~ | Confirm and (if absent) expose per-type OSNAP toggle UI surface | Verified absent; §9.5 amended and OSNAP toolbar spec promoted to P1 backlog task | `[ref:snap-spec§9.5]` `[done:2026-04-08]` |
| 13 | **P2 spec** | Spec session: pipe-with-fitting named targets | Design doc for `Pipe`/`Fitting` named-target glyphs and `_collect()` emission rules; brainstorm session conducted | `[ref:snap-spec§8.3]` |
| 14 | **P1 spec** | Spec session: inferred / dimension-driven placement (Revit subsystem) | Design doc for the next subsystem flagged in §2.3 as "next priority" | `[ref:snap-spec§2.3]` |

**Wall-corner fix (item 1) and intersection-source audit (item 2) are P1 because they directly resolve §7's reproducible recall bugs. The marker variants (item 3) is P1 because it's the user-visible payoff of items 1 and 2 — without it, the underlying corner is still indistinguishable from the centerline endpoint and the user gains less than they should.**

---

## 13. Open questions

1. **Per-type toggle UI surface.** The boolean attributes `snap_endpoint`, `snap_midpoint`, etc. exist on `SnapEngine` but a code search did not turn up a UI that toggles them. Roadmap item 12 confirms or denies; if denied, the OSNAP toolbar spec becomes a higher priority than its current "deferred" tag suggests.

2. ~~**DXF underlay child item recall.**~~ **Resolved.** Phase 1 now correctly descends into underlay group children for `_collect()` snaps (endpoint/midpoint). Phase 4 descends via `_phase4_items()` for intersection detection. Both phases handle DXF/PDF underlay children.

3. **Tolerance dataset hook (deferred subsystem feedforward).** While implementing the recall-first changes, instrument the engine to log near-miss cases (cursor position, all candidates within `tolerance × 1.5`, the candidate that won, and the distance margin to the second-best). This produces a dataset that the future tolerance UX spec inherits, replacing guesswork with measurement. **Not a blocking roadmap item** — implement opportunistically inside item 1 if cheap, otherwise spawn as a separate item later. Mentioned here so the door stays open.

4. **Multi-level visibility filtering.** When the active view shows only one level, should items on hidden levels still contribute snap candidates? Today the answer is implicit (whatever `scene.items()` returns is whatever is visible to QGraphics). The views-relationship spec (separate P1 task) is the right place to settle this — flagged here so that spec inherits the question, not this one.

5. **Marker variant proliferation.** §8 introduces 2 new glyph variants for walls. Pipes-with-fittings (item 13) will introduce more. At what point does the user stop being able to memorize the variant rules at a glance? Open question for the pipe spec — this spec commits only to the wall variants and notes the question.

---

*End of specification.*
