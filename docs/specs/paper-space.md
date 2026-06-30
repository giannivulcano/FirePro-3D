# Paper Space — Design Spec

**Date:** 2026-04-09
**Complexity:** Large
**Status:** partial — Phase-1 (sheet/viewports/title block) + the single-sheet plot step (PDF export + print) are built. **Sheet text annotations + a unified paper-space undo/redo stack were designed 2026-06-26 and are in build this cycle — see §9 and §17 (those two sections are the contract for unbuilt code until Phase 6 stamps them).** Batch/multi-sheet UI and the remaining annotation types (leader/line/cloud/north-arrow/scale-bar) are pending.
**Last verified:** 2026-06-25 (built behavior; §9/§17 are design-ahead-of-code)
**Verified commit:** 2c6b9fb
**Applies to:** `firepro3d/paper_space.py`, `firepro3d/paper_export.py`, `firepro3d/paper_display.py`, `firepro3d/paper_commands.py` (new — undo commands), `firepro3d/constants.py` (`DEFAULT_TEXT_HEIGHT_MM`)
**Source tasks:** TODO.md "Spec session: paper space — full MVP scope"
**Adjacent specs:** `view-relationships.md`, `snapping-engine.md`, `pipe-placement-methodology.md`

---

## 1. Goal

Enable FirePro3D users to compose construction document sheet sets by placing scaled references to model views onto paper sheets, annotating them, and exporting to PDF for AHJ submittal.

## 2. Motivation

Fire protection engineers design in model space but deliver paper documents. Without paper space, there is no path from model to submittal. The existing 763-LOC implementation is a scaffold — it renders one live view per sheet with no persistence, no scale control, no export, and no annotations. This spec defines the complete paper space subsystem so that FirePro3D can produce real construction document sets.

## 3. Architecture & Constraints

### 3.1 Three-Layer Architecture

1. **Sheet Model** (data) — `Sheet` objects holding metadata (name, number, paper size), an ordered list of `SheetView` references, paper-space annotations, title block field values, and revision history. Serialized to project JSON. No Qt dependency.

2. **Sheet Scene** (rendering) — `PaperScene` (`QGraphicsScene`) that composes the visual representation: paper background, title block artwork, sheet view render regions, and annotation items. Each sheet view renders by calling `scene.render()` on its source view's `QGraphicsScene` (`Model_Space` for plan/detail, `ElevationScene` for elevations).

3. **Sheet Widget** (UI) — `PaperSpaceWidget` wrapping a `QGraphicsView` with toolbar controls (paper size, add view, export, print). One widget per open sheet tab.

### 3.2 Key Constraints

- **Sheet views are consumers, not configurators.** They reference views from existing managers (`PlanViewManager`, `DetailViewManager`, `ViewMarkerManager`) and add only presentation properties: scale, position on sheet, size, crop override, layer visibility overrides.
- **Scale lives on the sheet view.** Source views work in real-world mm (1px = 1mm). The sheet view scales down for paper presentation.
- **Three rendering categories** flow through sheet views differently:
  - *Labels* (room names, pipe sizes, gridline bubbles): render through sheet views, scaled by `paper_height_mm` property
  - *Constraints* (dimensional, parametric): filtered out, never render on sheets
  - *Annotations* (text, leaders, revision clouds): paper-space-only items, do not exist in model space
- **Dirty-flag update model.** Source scenes emit `changed` signal → sheet views mark dirty → re-render only on next paint.
- **View-only interaction with *model geometry*.** Model entities are never picked or edited *through* a viewport — double-click / right-click "Go to View" navigates to the source. Sheet-native items (the viewports themselves, and sheet text annotations — §9) are directly selectable, movable, and editable on the sheet; that is sheet authoring, not model editing.
- **Existing patterns preserved.** Serialization follows the `to_dict()`/`from_dict()` pattern. Title block 3-tier fallback (DXF → PDF → programmatic) retained and extended.

## 4. Design Decisions

### 4.1 Sheet View vs Viewport

Chose "Sheet View" — a linked reference to a named view, Revit-style. Rejected AutoCAD-style viewports (mutable view configuration, layer freeze tables). Sheet views are lightweight: they point to a source view and add presentation properties only.

### 4.2 Scale Ownership

Scale on the sheet view, not the source view. Source views are always 1:1 (1px = 1mm). The same view can appear at 1:100 on one sheet and 1:50 on another. Scale auto-propagates to the title block Scale field.

### 4.3 No Unified View Catalog

Sheet view picker queries `PlanViewManager`, `DetailViewManager`, and `ViewMarkerManager` directly at runtime. Avoids premature abstraction. A catalog can wrap these later without breaking paper space.

### 4.4 Rendering via scene.render()

Each view type already has a `QGraphicsScene`. Sheet views call `scene.render(painter, target_rect, source_rect)` on the appropriate scene. Simple, always live, consistent across view types.

### 4.5 Annotations Are Paper-Space-Only

Model space has labels (identity/property display). Paper space has annotations (documentation). The thin-lines toggle bridges the gap: labels render at fixed screen size during editing, true scale in paper space. Constraints never render on sheets.

### 4.6 Vector PDF Export

`QPdfWriter` + `QPainter` produces native vector PDF paths. Text is embedded as PDF text objects (selectable/searchable). Only `TitleBlockPdfItem` (pixmap from PDF raster) and future imported images produce raster content.

### 4.7 DXF Export Target

True paper space DXF export using `LAYOUT`/`VIEWPORT` entities via ezdxf, not flat geometry. Deferred to future implementation but the spec defines the target so architecture accounts for it.

### 4.8 Title Block Template Library

Multiple templates per paper size. Named anchor points (DXF `ATTDEF` entities or JSON sidecar) define where dynamic fields render over static artwork. Ships with defaults for ANSI B and ANSI D; user can add custom templates.

### 4.9 Full Layer Overrides Per Sheet View

Each sheet view can independently show or hide any layer, overriding the source view's visibility. Not limited to hide-only.

### 4.10 Mixed Paper Sizes Per Sheet Set

Different sheets can have different paper sizes. Typical FP set: ANSI D for plans, ANSI B for details, Letter for cover/schedules.

### 4.11 Sheet Text Is a Purpose-Built Item, Not a Reused Model-Space Note

`TextAnnotationItem` (§9.3) is a **new** `QGraphicsTextItem` subclass, **not** the model-space `NoteAnnotation`. `NoteAnnotation` sizes in **points** (DPI-dependent → ~2.4× oversize in the 300-dpi PDF, and it cannot express a fractional paper-mm height), defaults to **white** (invisible on paper), and carries model-space coupling (`level`, the `Layer` enum, Model_View grips). Reusing or subclassing it imports the wrong sizing model plus dead baggage and binds two subsystems by inheritance (violating the arm's-length-module invariant). Instead the new item reuses *patterns* — the `SheetViewport` lifecycle (shared `_data`, signals, `itemChange` sync, deferred delete) and `HatchItem`'s `to_dict`/`from_dict` — but owns its sizing (`setPixelSize` + cap-height `setScale`, §9.4) and serialization. *Latent follow-up:* the existing `TitleBlockItem` / viewport view-title point-size text carries the same ~2.4× PDF over-sizing and is fixed separately.

### 4.12 Paper-Space Undo Is a `QUndoStack`, Not a Snapshot

Paper-space ops are small, discrete, individually-serializable placed items, so a `QUndoStack` with per-op `QUndoCommand`s (free redo, command labels, action enable/disable, per-command unit tests) is the right tool — versus the model-space whole-network dict snapshot (`_capture_network`/`_restore_network`), which is justified there only by deep node↔pipe↔constraint interconnection that paper space lacks (`_capture_network` never even captures `_sheets`). A snapshot here would `clear()`+rebuild the entire sheet (re-parsing the DXF title block, re-rendering every viewport) on every trivial undo — flicker plus a perf regression. See §17.

## 5. Data Model & Serialization

### 5.1 Sheet Data Structure

Serialized to project JSON under a top-level `"sheets"` key:

```
Sheet:
  number: str              # user-defined, e.g. "FP-1.0"
  name: str                # e.g. "Level 1 Sprinkler Plan"
  paper_size: str           # key into PAPER_SIZES, e.g. "ANSI D"
  title_block_template: str # template filename or "programmatic"
  title_block_fields: dict  # {field_name: value} — Company, Project, etc.
  sheet_views: list[SheetViewData]
  annotations: list[AnnotationData]
  revision_history: list[RevisionEntry]
```

### 5.2 Sheet View Data

```
SheetViewData:
  source_view_type: str     # "plan" | "elevation" | "detail" | "3d"
  source_view_name: str     # e.g. "Plan: Level 1", "Detail 3", "East"
  scale: str                # e.g. "1:100", "1/4\"=1'-0\"", or custom ratio
  x: float                  # position on sheet (mm from left)
  y: float                  # position on sheet (mm from top)
  w: float                  # width on sheet (mm)
  h: float                  # height on sheet (mm)
  crop_override: dict|null  # {x, y, w, h} in model-space mm, or null
  layer_overrides: dict     # {layer_name: bool} — true=visible, false=hidden
```

### 5.3 Annotation Data

MVP ships a single annotation type — **text** — as a typed dataclass (`TextAnnotationData`), serialized in the sheet's `annotations` array. The `type` discriminator reserves the array for the deferred types (§9.1, §17); when they land they get their own dataclasses dispatched on `type`. `to_dict`/`from_dict` mirror `SheetViewData` / `HatchItem` (`.get`-defaulted) — the **data** class owns serialization, not the item.

```
TextAnnotationData:
  type: str          = "text"      # discriminator for future annotation types
  text: str          = ""          # raw multi-line string ("\n"-separated)
  x: float           = 0.0         # anchor = item top-left, paper mm (1 PaperScene unit = 1 mm)
  y: float           = 0.0
  height_mm: float   = DEFAULT_TEXT_HEIGHT_MM   # CAP height; default 3.175 mm (1/8"), in constants.py
  wrap_width_mm: float = 0.0       # 0 = auto-width to longest line; >0 = word-wrap at this paper width
  font_family: str   = ""          # "" => Arial default; else QFontDatabase family
  bold: bool         = False
  italic: bool       = False
  color: str         = "#000000"   # authored hex; default BLACK
  align: str         = "L"         # 'L' | 'C' | 'R'
  opaque_bg: bool    = False       # paint a solid-white knockout rect behind the glyphs
```

`Sheet.annotations: list[TextAnnotationData]` is the persistent, shared-by-reference source of truth (the item holds it, never copies — exactly like `SheetViewData`↔`SheetViewport`). Backward-compat: `Sheet.from_dict` reads `d.get("annotations", [])`, so pre-feature `.fpd` files load with an empty list (no `SAVE_VERSION` bump, consistent with how `sheet_views` was added).

### 5.4 Revision Entry

```
RevisionEntry:
  rev: str                  # e.g. "A", "1", "R1"
  date: str                 # ISO date
  description: str
  drawn_by: str
```

### 5.5 Sheet Ordering

The `"sheets"` array order in JSON is the document set order. Reordering is a list operation.

### 5.6 Backward Compatibility

Existing project files without a `"sheets"` key load normally with an empty sheet set.

## 6. Sheet View Rendering Pipeline

### 6.1 Placement Flow

1. User drags view from project browser or clicks "Add View" button
2. Picker shows available views grouped by type (Plans / Elevations / Details), queried from `PlanViewManager`, `DetailViewManager`, `ViewMarkerManager`
3. Floating preview attaches to cursor on the sheet
4. Click places the sheet view; default scale is 1:100
5. User adjusts scale, position, size, crop via property panel

### 6.2 Render Flow (Per Sheet View Paint Cycle)

1. Check dirty flag — skip if clean and cached
2. Resolve source view → get the owning `QGraphicsScene`:
   - Plan: `Model_Space` scene, source rect from plan view's full content bounds
   - Detail: `Model_Space` scene, source rect from `DetailMarker.crop_rect`
   - Elevation: `ElevationScene` instance, source rect from scene bounds
3. Apply crop override if set (intersect with source rect)
4. Apply layer visibility overrides: temporarily hide/show items on the source scene by toggling `QGraphicsItem.setVisible()` based on the sheet view's `layer_overrides` dict. This is a render-time-only mutation — visibility is restored immediately after the render call (step 7). Alternative: if concurrent rendering becomes an issue, render to an intermediate pixmap with per-item visibility checks instead of mutating the source scene.
5. Apply constraint filter: temporarily hide items tagged as constraints (same toggle mechanism as step 4)
6. Call `scene.render(painter, target_rect_on_sheet, source_rect_in_model)`
7. Restore all visibility state changed in steps 4-5
8. Draw sheet view border (black hairline; blue dashed when selected)
9. Mark clean

### 6.3 Dirty-Flag Lifecycle

- Source scene emits `QGraphicsScene.changed` signal
- All sheet views referencing that scene connect to it and set `self._dirty = True`
- `paint()` checks `_dirty` before re-rendering
- Manual "Refresh" button forces all sheet views dirty

### 6.4 Scale Computation

- Scale ratio `s` = e.g. 1/100 for "1:100"
- Source rect width in model mm → sheet view width = `source_width_mm * s`
- Or inverse: user sets sheet view size → source rect = `sheet_size / s`
- "Fit to view" computes `s` from source bounds and current sheet view size, snaps to nearest standard scale

### 6.5 Standard Scale Presets

Imperial: 1/8"=1'-0", 3/16"=1'-0", 1/4"=1'-0", 3/8"=1'-0", 1/2"=1'-0", 3/4"=1'-0", 1"=1'-0", 1-1/2"=1'-0", 3"=1'-0"

Metric: 1:200, 1:100, 1:75, 1:50, 1:25, 1:20, 1:10, 1:5, 1:1

Custom: user-entered ratio (e.g., "1:125")

## 7. PDF Export & Print

> **As-built (2026-06-25, `paper_export.py`).** Single-sheet **vector PDF export** (`export_pdf`) and **system-dialog print** (`print_sheets`) are implemented and surfaced via the Draft ribbon → **Plot** group ("Export PDF" / "Print"). Both functions take `list[Sheet]` and loop pages with `newPage()` honouring per-page size, so batch multi-page is a thin add — but only the single active sheet is reachable today (multi-sheet management is a separate task). The render source is a **transient off-screen `PaperScene`** built from sheet data + the shared `ViewResolver` (`render_sheet`), then `dispose()`d — so the on-screen `SheetViewport` → `apply_paper_overrides` B&W/line-weight pipeline (`paper_display.py`) is reproduced verbatim with no second render path. **Deferred:** the §7.5 multi-sheet export dialog (sheet checkboxes, single-multipage-vs-separate-files) and §7.1 batch modes — they need multi-sheet management first. Current export UI is a save dialog + a 150/300/600 DPI picker.

### 7.1 PDF Export Modes

1. **Single sheet** — export active sheet to one PDF file
2. **Batch (multi-page)** — select sheets or "all", export to single PDF with one page per sheet. Pages can have different sizes (mixed paper sizes handled natively by `QPdfWriter` via `setPageSize()` per page).
3. **Per-sheet separate files** — select sheets, each exports to its own PDF file. Naming convention: `{sheet_number} - {sheet_name}.pdf`

### 7.2 Export Pipeline

1. Create `QPdfWriter` with first sheet's page size
2. Create `QPainter` on the writer
3. For each sheet:
   - Set page size (`QPdfWriter` supports per-page size changes)
   - Set resolution (default 300 DPI for print quality)
   - Render paper background, title block, all sheet views, annotations via the same paint path used for screen display
   - `newPage()` between sheets
4. End painter, close writer

### 7.3 Vector Fidelity

`QPainter` renders `QGraphicsScene` geometry as vector PDF paths natively. Text is embedded as PDF text objects (selectable/searchable). Only `TitleBlockPdfItem` (pixmap from PDF raster) and future imported images produce raster content.

### 7.4 Print Workflow

1. **Single sheet:** Active sheet → `QPrintDialog` → system print dialog → render via same paint pipeline with `QPrinter` instead of `QPdfWriter`
2. **Batch:** Sheet selection dialog → `QPrintDialog` → loop sheets, `newPage()` between them. `QPrinter` handles mixed page sizes via `setPageSize()` per page.

### 7.5 Export UI

Menu action "Export to PDF..." opens a dialog with:
- Sheet selection (checkboxes, "Select All")
- Mode toggle: single multi-page PDF vs separate files
- Output path picker
- Resolution selector (150 / 300 / 600 DPI)

## 8. Title Block Template System

### 8.1 Template Resolution Order (Per Sheet)

1. Custom DXF template matching the sheet's paper size → vector rendering via `TitleBlockDxfItem`
2. Custom PDF template matching the sheet's paper size → raster rendering via `TitleBlockPdfItem`
3. Built-in programmatic fallback → `TitleBlockItem` with geometric drawing

### 8.2 Template Library Structure

```
firepro3d/
  default titleblocks/
    CEL Titleblock (ANSI B) R0.dxf      # existing
    CEL Titleblock (ANSI B) R0.pdf      # existing
    CEL Titleblock (ANSI D) R0.dxf      # existing
    CEL Titleblock (ANSI D) R0.pdf      # existing
    CEL Titleblock (Letter) R0.dxf      # to add
  custom titleblocks/                    # user-added templates
    <firm_name> (ANSI D).dxf
    <firm_name> (ANSI D).fields.json    # field mapping sidecar
```

### 8.3 Field Mapping

- **DXF templates:** `ATTDEF` entities with tag names matching field keys (e.g., tag `PROJECT` maps to the Project field). On render, attribute values are replaced with the sheet's field values and drawn as text at the attribute's insertion point, height, and rotation.
- **JSON sidecar** (fallback for templates without ATTDEFs): defines field positions, font size, and alignment relative to the template's coordinate system.
- **Programmatic template:** Field positions hardcoded in `TitleBlockItem` as today.

### 8.4 Field Set

Current 9 fields (extensible): Company, Project, Title, Scale (auto-populated from sheet view), Drawing No, Rev, Date, Drawn By, Checked By.

### 8.5 Scale Field Auto-Population

When a sheet has one sheet view, its scale propagates to the title block Scale field. With multiple sheet views at different scales, the field shows "AS NOTED" and each sheet view renders its own scale label.

## 9. Annotations & Labels

### 9.1 Sheet Text Annotations [in build this cycle — 2026-06-26]

Free-placed **multi-line text blocks** are the MVP annotation type and the last piece of the paper-space AHJ deliverable. They are `QGraphicsItem`s added directly to `PaperScene`, exist only on the sheet (never in model space or model data), and serialize in the sheet's `annotations` array (§5.3).

| Type | Status |
|------|--------|
| **Text** (multi-line, font/height/bold/italic/color/alignment/opaque-bg) | **Built this cycle** |
| Leader · Line / Rectangle · Revision cloud · North arrow · Scale bar | Deferred (§17) |
| Legends / schedules | A separate Revit-style **placed-table** feature (built elsewhere, dropped on a sheet like a viewport) — *not* a text annotation |

The `type` discriminator on `TextAnnotationData` reserves the `annotations` array for the deferred types.

### 9.2 Text Annotation Data

Defined in §5.3. Key contracts: `height_mm` is **cap height** (matches the AutoCAD/Revit "text height" convention); `wrap_width_mm == 0` means auto-width (no wrap), `> 0` means word-wrap at that paper width; default color is black; serialization is `.get`-defaulted on the **data** class.

### 9.3 Text Annotation Item — `TextAnnotationItem(QGraphicsTextItem)`

Purpose-built (§4.11); holds its `TextAnnotationData` by **shared reference** (mirrors `SheetViewport`↔`SheetViewData`). Flags `ItemIsMovable | ItemIsSelectable | ItemSendsGeometryChanges | ItemIsFocusable`.

- **Sizing (invariant, §9.4):** `font.setPixelSize(_TEXT_METRIC_REF)` + `setScale(height_mm / QFontMetricsF(font).capHeight())`, `transformOrigin = (0, 0)`. **Never** `setPointSizeF`; **never** `ItemIgnoresTransformations`.
- **Width / wrap:** `wrap_width_mm == 0` → `setTextWidth(-1)` (auto-size; alignment uses `idealWidth`); `> 0` → `setTextWidth(wrap_width_mm / scale)` (paper-mm → unscaled local units). A horizontal **resize grip** drawn on the right edge while selected drags `wrap_width_mm` (min-width clamp; hit-test/clamp via `sceneBoundingRect`/`mapToScene`, since `boundingRect` is unscaled).
- **Inline edit:** double-click → `setTextInteractionFlags(TextEditorInteraction)`; **Enter inserts a newline**; focus-out commits; **Esc reverts** to the pre-edit text; committing empty/whitespace content auto-deletes the block.
- **Paint:** if `opaque_bg`, a solid-white knockout `fillRect(boundingRect())` *before* `super().paint()`; a dashed `#88aaff` cosmetic focus frame while editing. **`zValue = 15`** — above viewports (z=5) and the title block (z=10), so text is never occluded.
- **Move / clamp:** `itemChange` clamps the proposed anchor into the paper rect on `ItemPositionChange` and live-syncs `x/y` into the data on `ItemPositionHasChanged` (mirrors `SheetViewport`). Delete key removes the block when selected, but deletes a character while editing.

Dropped from `NoteAnnotation`: white default, `level`, `Layer` enum, `grip_points`/`apply_grip`, integer `setPointSize`.

### 9.4 Paper-Fixed mm Sizing (the invariant)

Text height is a real paper millimetre — identical on the 96-dpi screen and in the 300-dpi PDF/print — achieved with a **device-independent pixel-size font + geometric `setScale`** (§9.3), not a point size. Point sizes are DPI-dependent and render ~2.4× oversize through `paper_export` (`QPdfWriter.setResolution(300)` vs the 96-dpi screen); this is the same latent bug the existing title block / view-titles carry (§4.11 follow-up). Precedent: `model_space.py` dimension text already sizes via `setPixelSize`. `_TEXT_METRIC_REF` is a large constant (e.g. 1000) so `QFontMetricsF` is precise; recompute the scale only on a height/family/bold/italic change, not per paint.

### 9.5 Authoring Interactions

An **"Add Text"** button on the `PaperSpaceWidget` toolbar enters place-mode; a click on the sheet drops a *transient* item already in inline edit. The first non-empty commit pushes an `AddTextAnnotation` command; an empty or Esc-cancelled placement discards silently (nothing on the undo stack). Existing blocks: double-click → inline edit; drag → move (anchor clamped to the paper rect); right-click → **Properties…**; `Delete` → remove when selected (a character while editing). Event-driven deletes defer via `QTimer.singleShot` (no reentrant destruction), mirroring viewport delete.

### 9.6 Properties Dialog — `TextAnnotationPropertiesDialog`

Mirrors `SheetViewPropertiesDialog`: `QDialog` + `QFormLayout`, `QDialogButtonBox(Ok|Cancel)`, values pulled post-`exec()` via `get_*` accessors — **the caller applies the change through an undo command; the dialog never mutates the item.** Rows: multi-line text editor, `QFontComboBox` (family), height, bold, italic, color swatch (`property_manager._pick_color` idiom, `#000000` default, cancel-guarded), alignment combo, opaque-background checkbox. The height field seeds via `ScaleManager.format_length(height_mm)` and reads back via `ScaleManager.parse_dimension(text, fallback_unit="mm")` — `fallback_unit` is forced to `"mm"` (not `bare_number_unit()`, which is `ft` in imperial); a bare leading fraction (`1/8"`) is pre-processed (insert a leading `0 `) so it parses, with placeholder `e.g. 0 1/8" or 3.18mm`; on `None` the old height is kept. Height display follows the model-space unit setting.

### 9.7 Color & B&W Independence

Authored color and the opaque-background fill plot **as authored, independent of the viewport B&W override** — automatically, because a `TextAnnotationItem` is a direct `PaperScene` child and is never inside the `SheetViewport` source-render that `paper_display.apply_paper_overrides` mutates (and `_category_for_item` returns `None` for it regardless). Default color is black, so a normal plot is all-black; a deliberately-colored note plots in its color. *(Follow-up: expose paper-space text as a Display-Manager category for project-level color / background customization.)*

### 9.8 Persistence & Export

Annotations round-trip via `Sheet.to_dict`/`from_dict` under the `"sheets"` key — **no `scene_io.py` or `paper_export.py` changes.** Export/print are free because `PaperScene._setup` rebuilds annotation items from `Sheet.annotations`, and the transient export scene (`paper_export.render_sheet`) reuses `_setup`. **Invariant:** `Sheet.annotations` is authoritative — every move/edit/format/wrap-resize writes through to the data object **live** (export and print read the dataclass, not the live items, and do *not* call `_sync_sheet_before_save`), exactly as `SheetViewData` stays current via `SheetViewport.itemChange`.

### 9.9 Model-Space Labels [Phase 2 — pending]

Labels are existing model-space items (room names, pipe sizes, node IDs, gridline bubbles) that render through sheet views. They gain a `paper_height_mm` property — the height they should appear at on paper.

- **Model-space editing (thin-lines OFF):** Labels render at `paper_height_mm` in model units. At 1:1 they are tiny. This is "true scale" — WYSIWYG preview of print output.
- **Model-space editing (thin-lines ON, default):** Labels render at a fixed readable screen size via `ItemIgnoresTransformations`. Standard editing workflow.
- **Sheet view rendering:** Labels always render at `paper_height_mm` scaled by the sheet view's scale factor. Thin-lines toggle has no effect in paper space.

### 9.10 Constraint Filter

Sheet view rendering skips any item where `item.data(ROLE_KEY) == "constraint"` (or equivalent category tag). Constraints are authoring aids — they never appear on construction documents.

## 10. Edge Cases & Error Handling

### 10.1 Dangling References

- Source view deleted while a sheet view references it → sheet view renders a placeholder ("View not found: Plan: Level 2") with a warning icon. Property panel shows the broken reference. User can reassign or delete the sheet view.
- On project load, validate all `source_view_name` references against current managers. Log warnings for any unresolved.

### 10.2 Empty Source Views

Source view with no geometry → sheet view renders as empty white rectangle with border. Not an error.

### 10.3 Scale Extremes

- Very large scales (1:1, 1:10) may produce sheet views larger than the paper. Clip to paper printable area. Warn user if sheet view extends beyond sheet bounds.
- Very small scales (1:1000+) may produce unreadable content. No restriction — user's judgment.

### 10.4 Title Block Template Missing

DXF/PDF template file not found on load → fall through to next tier (DXF → PDF → programmatic). Log warning.

Custom template directory does not exist → create on first use.

### 10.5 PDF Export Failures

- Output path not writable → error dialog, no partial file.
- Sheet with zero sheet views → export the sheet anyway (title block + annotations only, valid for cover sheets).

### 10.6 Mixed Paper Size Printing

Printer does not support a sheet's paper size → QPrinter/OS dialog handles tray selection or scaling. Not FirePro3D's problem to solve.

### 10.7 Concurrent Editing

User modifies model while PDF export is in progress → export captures state at render time. No locking needed — `QPainter` serializes the render.

## 11. Performance & Security

### 11.1 Rendering Performance

- Dirty-flag prevents redundant re-renders. Off-screen sheet views (tabs not visible) do not paint.
- Multiple sheet views per sheet each call `scene.render()`. For sheets with 4-5 views this is fast (Qt's scene rendering is hardware-accelerated). If profiling reveals bottlenecks, pixmap caching can be added per sheet view without architectural change.
- PDF export of large sheet sets (20+ sheets) may take several seconds. Run export on a worker thread with progress dialog.

### 11.2 Memory

- Each open sheet tab holds a `PaperScene`. Closed tabs release their scene. Sheet data (the model) stays in memory as part of the project.
- Raster title blocks (`TitleBlockPdfItem`) cache a `QPixmap`. One pixmap per unique template per paper size — not per sheet.

### 11.3 File Size

- Sheet data in project JSON is lightweight (metadata + coordinates). A 20-sheet project adds approximately 10-20 KB to the file.
- PDF export size depends on model complexity. Vector output is typically smaller than raster.

### 11.4 Security

- Custom title block templates loaded from disk — DXF parsed via ezdxf (trusted library), PDF via `QPdfDocument`. No script execution from templates.
- PDF export writes to user-selected path only. No network operations.

## 12. Existing Code Context

| File | Role |
|------|------|
| `firepro3d/paper_space.py` | Sheet subsystem: `Sheet`/`SheetViewData`/**`TextAnnotationData`** (data + serialization), `ViewResolver` (view→scene/rect bridge), `SheetViewport`, **`TextAnnotationItem`**, `PaperScene` (composition + `dispose()` + **`QUndoStack`** owner), `PaperSpaceWidget`, title blocks (`TitleBlockDxfItem`/`PdfItem`/`Item`), dialogs (incl. **`TextAnnotationPropertiesDialog`**) |
| `firepro3d/paper_commands.py` | **(new)** `QUndoCommand` subclasses for paper-space undo/redo — viewport (`Add`/`Remove`/`Geometry`/`ChangeProperties`) + text (`Add`/`Delete`/`Geometry`/`Edit`/`Format`). Keyed on persistent data identity; no `main.py` import (§17) |
| `firepro3d/paper_export.py` | Plot step: `render_sheet` (transient off-screen scene), `export_pdf(sheets,…)` (vector PDF), `print_sheets(sheets,…)`, `default_pdf_filename` |
| `firepro3d/paper_display.py` | Paper-space display overrides (B&W/line-weight/visibility) applied per viewport render — `apply_paper_overrides`/`restore_model_display` |
| `firepro3d/scene_io.py` | Project serialization (`save_to_file`/`load_from_file`); persists `scene._sheets` under the JSON `"sheets"` key (list — already multi-sheet-ready) |
| `firepro3d/level_manager.py` | `PlanView`, `PlanViewManager` — queried by `ViewResolver` |
| `firepro3d/detail_view.py` | `DetailViewManager`, `DetailMarker` — queried by `ViewResolver`, provides crop rects |
| `firepro3d/elevation_scene.py` | `ElevationScene` (`QGraphicsScene`) — render target for elevation sheet views |
| `firepro3d/elevation_view.py` | `ElevationView` (`QGraphicsView`) — elevation UI widget |
| `firepro3d/view_marker.py` | `ViewMarkerManager` — elevation view names |
| `firepro3d/model_space.py` | `Model_Space` (`QGraphicsScene`) — render target for plan/detail sheet views; owns `_sheets` |
| `firepro3d/annotations.py` | `NoteAnnotation`, `DimensionAnnotation`, `HatchItem` — **model-space only**. Sheet text is a separate `TextAnnotationItem` in `paper_space.py` (§4.11); `NoteAnnotation`'s inline-edit/formatting *structure* and `HatchItem`'s `to_dict`/`from_dict` *pattern* are reused, the classes are not |
| `firepro3d/default titleblocks/` | DXF + PDF templates for ANSI B/D |

> Note: the per-sheet-view **layer overrides** of §4.9 predate the layer-system removal (the `user_layer` system is gone — see `architecture/display-system.md`). When built, per-view visibility overrides ride on the Display Manager / `paper_display.py` categories, not a `UserLayerManager`.

## 13. Code Style & Testing

### 13.1 Conventions

- Python 3.x with PyQt6
- Google-style docstrings
- Module naming: `lowercase_with_underscores` (PEP 8)
- Relative imports within `firepro3d/`
- All geometry in millimeters
- Constants in `firepro3d/constants.py`
- Serialization via `to_dict()`/`from_dict()` class methods

### 13.2 Testing

**Unit tests:**
- Scale computation (ratio parsing, named preset lookup, fit-to-view calculation)
- Source rect calculation (from view bounds, crop override intersection)
- Serialization round-trip (`Sheet.to_dict()` → JSON → `Sheet.from_dict()`)
- Layer override merging (base visibility + per-sheet-view overrides)
- Title block field auto-population (single scale vs "AS NOTED")
- Backward compatibility (project JSON without `"sheets"` key)
- `TextAnnotationData` round-trip (every field) + sheet dict lacking `"annotations"` → `[]`
- Cap-height sizing math (`height_mm` → `setScale`); wrap-width local↔paper conversion; empty-text and anchor-clamp logic
- Each `QUndoCommand` in `paper_commands.py`: `redo()` applies, `undo()` restores the data object — for every text **and** viewport command (constructed standalone, no `main.py`)

**Integration tests:**
- Create project → add geometry → create sheet → place sheet view → verify render is non-empty
- Full export pipeline: create project → geometry → sheet → export PDF → verify PDF has correct page count, non-zero file size, and correct page dimensions
- Dangling reference: delete source view → verify sheet view shows placeholder
- Dirty-flag: modify model geometry → verify sheet view re-renders on next paint
- Add a text annotation → it is present on `PaperScene`; export → non-empty PDF and the transient scene contains the text item (proves the data-driven plot path)
- Annotations save/load round-trip identically; undo/redo end-to-end (add→undo→gone→redo→back; move→undo→original position)

## 14. Implementation Phases

### Phase 1 — MVP

- Sheet management: create, rename, reorder, delete sheets with user-defined number and name
- Mixed paper sizes per sheet within a set
- Sheet views: place plan, detail, and elevation views onto sheets
- Placement via drag from project browser + "Add View" toolbar button
- Sheet view properties: scale (presets + custom), position, size, optional crop
- "Fit to view" scale convenience
- Scale auto-propagates to title block Scale field ("AS NOTED" for mixed scales)
- Live rendering via dirty-flag `scene.render()` on source scene
- View-only interaction with double-click / right-click "Go to View" navigation
- Title block: 3-tier rendering (DXF → PDF → programmatic), editable fields
- Sheet persistence: full round-trip save/load in project JSON
- PDF export: single sheet, batch multi-page, per-sheet separate files — vector output
- Print: system dialog, single + batch with mixed page sizes
- Project browser: sheet tree with drag-to-reorder
- Backward compatibility: projects without sheets load normally

### Phase 2 — Annotations & Overrides

- Full layer visibility overrides per sheet view (show/hide any layer)
- Paper-space annotations: text, leaders, lines, rectangles, revision clouds, north arrows, scale bars
- Per-sheet revision history (rev, date, description, drawn_by)
- Label thin-lines toggle + `paper_height_mm` property on label items
- Constraint rendering filter in sheet views
- Title block template library with field mapping (ATTDEF + JSON sidecar)

### Phase 3 — Future

- Schedules, tables, legends, imported images
- 3D sheet view hosting
- True DXF paper space export (`LAYOUT`/`VIEWPORT` entities via ezdxf)
- Custom title block template builder UI

## 15. Acceptance Criteria

### MVP

- [ ] Sheet management: create, rename, reorder, delete sheets with user-defined number and name
- [ ] Mixed paper sizes per sheet within a set
- [ ] Sheet views: place plan, detail, and elevation views onto sheets
- [ ] Placement via drag from project browser + "Add View" toolbar button
- [ ] Sheet view properties: scale (presets + custom), position, size, optional crop
- [ ] "Fit to view" scale convenience
- [ ] Scale auto-propagates to title block Scale field ("AS NOTED" for mixed scales)
- [ ] Live rendering via dirty-flag `scene.render()` on source scene
- [ ] View-only interaction with double-click / right-click "Go to View" navigation
- [ ] Title block: 3-tier rendering (DXF → PDF → programmatic), editable fields
- [ ] Sheet persistence: full round-trip save/load in project JSON
- [x] PDF export: **single sheet, vector output** (`paper_export.export_pdf`) — batch multi-page / per-sheet files deferred (blocked on multi-sheet management)
- [x] Print: **single sheet** via system dialog (`paper_export.print_sheets`) — batch deferred
- [ ] Project browser: sheet tree with drag-to-reorder
- [ ] Backward compatibility: projects without sheets load normally

### Phase 2

- [ ] Full layer visibility overrides per sheet view (show/hide any layer)
- **Sheet text annotations [this cycle — §9]:**
  - [ ] "Add Text" places a new, immediately inline-editable block; empty/cancelled placement auto-deletes with nothing on the undo stack
  - [ ] Double-click inline-edits (Enter = newline; focus-out commits; Esc reverts); Delete removes when selected, edits a character while editing
  - [ ] Properties dialog sets font/height/bold/italic/color/alignment/opaque-bg; height accepts `1/8"` or `3mm`
  - [ ] Drag moves (anchor clamped to paper); horizontal grip sets `wrap_width_mm` (word-wrap); text is **cap-height** sized and identical on screen and in the 300-dpi PDF
  - [ ] Text persists across save/load; old projects without `annotations` load clean; text plots in exported PDF + print in authored color (default black), unaffected by viewport B&W mode
- **Paper-space undo/redo [this cycle — §17]:**
  - [ ] Undo/redo works for text create/edit/move/format/wrap-resize **and** viewport add/move/resize/delete; Ctrl+Z/Y/Shift+Z + ribbon both route to the paper stack when a sheet is active; stack resets on project load / new file
  - [ ] One canonical `PaperScene` drives the visible tab, edits, save, and export (duplicate-widget prerequisite collapsed)
- [ ] Leader / line / rectangle / revision cloud / north arrow / scale bar annotations (deferred — §18)
- [ ] Per-sheet revision history (rev, date, description, drawn_by)
- [ ] Label thin-lines toggle + `paper_height_mm` property on label items
- [ ] Constraint rendering filter in sheet views
- [ ] Title block template library with field mapping (ATTDEF + JSON sidecar)

### Phase 3

- [ ] Schedules, tables, legends, imported images
- [ ] 3D sheet view hosting
- [ ] True DXF paper space export (`LAYOUT`/`VIEWPORT` entities via ezdxf)
- [ ] Custom title block template builder UI

## 16. Verification Checklist

- [ ] All MVP acceptance criteria pass
- [ ] Unit tests: scale computation, source rect calculation, serialization round-trip, layer override merging
- [ ] Integration tests: create project → add geometry → create sheet → place sheet view → export PDF → verify PDF has correct page count and is non-empty
- [ ] Existing behavior: model space editing, view switching, project save/load unaffected
- [ ] PDF export produces vector paths (text selectable in a PDF reader)
- [ ] Mixed paper size batch export produces correct page sizes
- [ ] Sheet views update when model geometry changes (dirty-flag)
- [ ] Project files without sheets load without error (backward compatibility)

## 17. Paper-Space Undo & Redo [added 2026-06-26]

A unified, **paper-space-scoped**, session-only undo/redo stack covering the new sheet-text ops **and** the previously-non-undoable viewport ops. Rationale for `QUndoStack` over a snapshot: §4.12. Title-block field edits stay **out** (follow-up).

### 17.1 Architecture

- `QUndoStack` is owned by `PaperScene` (the stable object that owns the `Sheet` + the viewport/annotation tracking lists and survives `_setup()` rebuilds). An `_applying_command` guard (mirror of `Model_Space._in_undo_restore`) wraps every command's `redo`/`undo` so programmatic `setPos`/add/remove do not re-enqueue commands.
- Commands key on **persistent data identity** (`SheetViewData` / `TextAnnotationData` in the `Sheet` lists), **never** raw item pointers — `_setup()` and the paper-size setter destroy and recreate every `QGraphicsItem`, so item references go dangling. Commands resolve item↔data through the scene's tracking lists.
- Public `add_*` / `remove_*` become thin wrappers over silent `_do_*` primitives that the commands call (the old bodies, keeping `_update_scale_field()` inside so the title-block Scale field stays correct under undo/redo).
- Commands live in a new `firepro3d/paper_commands.py` (importing nothing from `main.py`) so each is unit-testable in isolation: construct → `redo()` / `undo()` → assert on the data object.

### 17.2 Command set

Viewport: `AddViewportCommand`, `RemoveViewportCommand`, `ViewportGeometryCommand` (move **and** resize, `mergeWith`/`id()` to collapse a drag), `ChangeViewportPropertiesCommand` (title/show_border/scale + derived w,h). Text: `AddTextAnnotationCommand` (pushed only on the first non-empty commit), `DeleteTextAnnotationCommand`, `TextGeometryCommand` (move **and** wrap-resize, `mergeWith`), `EditTextCommand`, `FormatTextCommand`.

### 17.3 Gesture capture

Move/resize/wrap-resize capture the geometry at `mousePressEvent` and push **one** command at `mouseReleaseEvent` (only if changed and not `_applying_command`); the continuous `itemChange` live-sync stays underneath, untouched. Never push from `itemChange` (it fires every tick and on programmatic `setPos`).

### 17.4 Keyboard & ribbon routing

`QUndoStack.createUndoAction` / `createRedoAction` → `Ctrl+Z` / `Ctrl+Y` (plus `Ctrl+Shift+Z` for redo, matching model-space), `setShortcutContext(WidgetWithChildrenShortcut)` on the paper view. `PaperGraphicsView.event()` accepts `ShortcutOverride` for those keys (mirror the existing `Key_Delete` handling) so they reach the widget action ahead of the window-scoped ribbon button. The ribbon Undo/Redo buttons dispatch on `central_tabs.currentWidget()` (paper stack vs `Model_Space`).

### 17.5 Lifetime & reset

Never serialized (session-only by construction). Cleared in `PaperScene.update_from_sheet` (the single project-load choke point) and in `new_file` (which must also reset `_sheet`/paper scene — today it does not). The paper-size setter rebuilds from data and clears the stack (acceptable for MVP).

### 17.6 Prerequisite — one canonical `PaperScene` (mandatory)

`_activate_paper_sheet` currently constructs a **second** `PaperSpaceWidget`, so the on-screen scene is not `self.paper_space_widget.paper_scene` (which is what load/title-block/export target). This is collapsed (reuse the canonical widget) so the undo stack, edits, save, and export all bind to the **one visible scene**. Pre-existing latent bug; mandatory for correct undo.

## 18. Out of Scope

- **View catalog unification** — paper space queries existing managers directly, no new abstraction
- **Annotation scale system in model space** — paper space defines annotations as paper-space-only; the label thin-lines toggle is defined here but the broader annotation scale rework is separate
- **Cross-view selection sync** — deferred in view-relationships spec (§1.3)
- **Editing through sheet views** — view-only, not interactive
- **Revision workflow / approvals** — data model defined, workflow process is separate
- **Custom title block template builder UI** — field mapping defined, authoring tool deferred
- **Sheet-text follow-ups (deferred from the 2026-06-26 build):** other annotation types (leader / line / rectangle / revision cloud / north arrow / scale bar); legends & schedules as Revit-style **placed tables**; copy / paste / duplicate of text blocks; rotated text; border-box; rich (per-character) text; cross-sheet / shared "same note on every sheet" content; title-block-field-edit undo; paper-space text as a **Display-Manager category** (project-level color / background customization); and the latent **point-size ~2.4× PDF over-sizing** fix for `TitleBlockItem` + viewport view-titles (§4.11).
