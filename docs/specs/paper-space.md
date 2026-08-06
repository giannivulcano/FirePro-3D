# Paper Space — Design Spec

**Date:** 2026-04-09
**Complexity:** Large
**Status:** partial — Phase-1 (sheet/viewports/title block) + the single-sheet plot step + **sheet text annotations (§9)** + **parametric title block templates (§8 step 0 — governed by `titleblock-template-system.md`; `TitleBlockDialog` retired, view-title pt→mm fix landed, `Sheet` gained `orientation`/`revisions`)** are built, alongside the unified paper-space undo/redo stack (§17) and the dirty-flag / crash-recovery persistence contract (§17.7). Batch/multi-sheet UI and the remaining annotation types (leader/line/cloud/north-arrow/scale-bar) are pending; viewport properties are slated to move from `SheetViewPropertiesDialog` into the panel (follow-up). **Multi-sheet management is designed (§19, 2026-08-06) and in build — §19 is proposal until the build stamps it.**
**Last verified:** 2026-07-22
**Verified commit:** 23fa804
**Applies to:** `firepro3d/paper_space.py`, `firepro3d/paper_export.py`, `firepro3d/paper_display.py`, `firepro3d/paper_commands.py` (undo commands), `firepro3d/constants.py` (`DEFAULT_TEXT_HEIGHT_MM`, `TEXT_BOX_MARGIN_MM`, `SELECTION_*`), `main.py` (dirty-flag + load/recovery orchestration — §17.7)
**Source tasks:** TODO.md "Spec session: paper space — full MVP scope"
**Adjacent specs:** `view-relationships.md`, `snapping-engine.md`, `pipe-placement-methodology.md`, `project-browser.md` (sheet tree — §19.5), `titleblock-template-system.md` (Sheet No — §19.7)

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

### 4.10 Mixed Paper Sizes Per Sheet Set [deferred 2026-08-06 — see §19.1]

Different sheets can have different paper sizes. Typical FP set: ANSI D for plans, ANSI B for details, Letter for cover/schedules. **Deferred behind the per-size title-block template library** (the single project template can only dress one size): the multi-sheet MVP enforces a uniform size project-wide (§19.1). The data model keeps per-sheet `paper_size` so this re-enables without a format change.

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
  orientation: str          # "" = native PAPER_SIZES orientation; "landscape"/"portrait" override
                            # (effective dims via sheet_page_mm() — one home for the swap rule)
  title_block_fields: dict  # open {field_name: value}; sheet-scoped keys (Title, Drawing No, Rev, Date) —
                            # project-scoped legacy keys migrate to Project Info on load (titleblock spec §Value Model)
  sheet_views: list[SheetViewData]
  annotations: list[TextAnnotationData]
  revisions: list[dict]     # {"no","description","date"} — rendered by the template's revision-table cell
```

(The parametric template itself embeds at the project level — payload key `titleblock_template`, owned by `titleblock-template-system.md`.)

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
  height_mm: float   = DEFAULT_TEXT_HEIGHT_MM   # CAP height; default 4.7625 mm (3/16"), in constants.py
  wrap_width_mm: float = 0.0       # 0 = auto-width to longest line; >0 = word-wrap at this paper width
  font_family: str   = ""          # "" => Arial default; else QFontDatabase family
  bold: bool         = False
  italic: bool       = False
  color: str         = "#000000"   # authored hex; default BLACK
  align: str         = "L"         # 'L' | 'C' | 'R'
  opaque_bg: bool    = False       # paint a solid-white knockout rect behind the box
  underline: bool    = False       # [2026-07-16] full-block underline
  box_height_mm: float = 0.0       # [2026-07-20] stored box height; 0 = auto-fit content.
                                   # Effective box height = max(stored, content) — the box
                                   # auto-grows with content, never clips it.
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

> **Custom templates are governed by `titleblock-template-system.md`** (current — built 2026-07-22): **parametric** single-size templates (margins, bordered areas, right-strip cell stack) authored in the Title Block editor (Draft tab), stored in a per-user library and embedded in the `.fpd`, one per project; the template drives the sheet's page size/orientation. That design **superseded** the earlier custom-DXF/PDF + ATTDEF/JSON-sidecar plan (never built) — the DXF-artwork chain survives only as the no-template fallback. This section documents the built-in chain; the template layer's contract lives in its own spec (Rule A).

### 8.1 Template Resolution Order (Per Sheet)

0. Project parametric template matching the sheet's size+orientation → `TitleBlockTemplateItem` (see `titleblock-template-system.md`)
1. Built-in DXF template matching the sheet's paper size → vector rendering via `TitleBlockDxfItem`
2. Built-in PDF template matching the sheet's paper size → raster rendering via `TitleBlockPdfItem`
3. Built-in programmatic fallback → `TitleBlockItem` with geometric drawing (paints via merged `DEFAULT_TITLE_BLOCK_FIELDS` defaults — post-migration sheets may lack project-scoped keys)

### 8.2 Built-in Template Files

```
firepro3d/
  default titleblocks/
    CEL Titleblock (ANSI B) R0.dxf      # existing
    CEL Titleblock (ANSI B) R0.pdf      # existing
    CEL Titleblock (ANSI D) R0.dxf      # existing
    CEL Titleblock (ANSI D) R0.pdf      # existing
```

### 8.3 Field Mapping (as built)

- **DXF/PDF templates:** field values are painted over the artwork by `TitleBlockFieldOverlay` at **hardcoded fractional positions** (`_get_field_layout`) — they are *not* measured from the artwork geometry. Known divergence; superseded rather than fixed (custom parametric templates own field placement — `titleblock-template-system.md`).
- **Programmatic template:** field positions hardcoded in `TitleBlockItem`.

### 8.4 Field Set

Current 9 fields (extensible): Company, Project, Title, Scale (auto-populated from sheet view), Drawing No, Rev, Date, Drawn By, Checked By.

### 8.5 Scale Field Auto-Population

When a sheet has one sheet view, its scale propagates to the title block Scale field. With multiple sheet views at different scales, the field shows "AS NOTED" and each sheet view renders its own scale label.

## 9. Annotations & Labels

### 9.1 Sheet Text Annotations [built 2026-07-02]

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

- **Sizing (invariant, §9.4):** `font.setPixelSize(_TEXT_METRIC_REF)` + `setScale(height_mm / QFontMetricsF(font).capHeight())`, `transformOrigin = (0, 0)`. **Never** `setPointSizeF`; **never** `ItemIgnoresTransformations`. Grip resizing never touches `height_mm`.
- **Box model [2026-07-20]:** the visual box is `_box_rect_local()` — width from the text layout (`wrap_width_mm == 0` → `setTextWidth(-1)` auto-size via `idealWidth`; `> 0` → `setTextWidth(wrap_width_mm / scale)`), height = `max(content, box_height_mm / scale)`. An inner **`TEXT_BOX_MARGIN_MM`** (constants.py) insets text from the box edge on all sides via the document margin (set before the textWidth logic so it participates in layout). Opaque-bg knockout fills the box, not just the glyphs.
- **Resize grips [2026-07-20]:** the canonical **8-handle** selection style (`architecture/theming.md` §"Canvas selection & resize grips"; shared `SELECTION_*` constants): corners resize both axes anchoring the opposite corner, edge midpoints one axis; left/top handles move the anchor with the far edge pinned; min width `MIN_TEXT_WRAP_WIDTH_MM`, min height = content. Auto width/height seed from the visual extent at press. One drag = one `ResizeTextBoxCommand` (§17.2).
- **Hit/paint geometry [2026-07-20]:** `boundingRect` = box **padded by the grip halo** (grips straddle the border; unpadded rects leave stale-paint trails on drag). `shape()` **and** `contains()` are both overridden to the full box (+ halo while selected) — `QGraphicsTextItem`'s defaults limit hits to the glyph strip, and scene point-queries consult `contains()`, not just `shape()`. Grip placement/resize math read the *unpadded* box (`mapRectToScene(_box_rect_local())`). Never narrow `shape()` (paint-culling trap).
- **Inline edit:** double-click → `setTextInteractionFlags(TextEditorInteraction)`; **Enter inserts a newline**; focus-out commits; **Esc commits** too [2026-07-20 smoke — both placement and existing-block edits; `cancel_edit()` remains as the programmatic revert API and undo recovers any commit]; committing empty/whitespace content auto-deletes the block.
- **Paint:** if `opaque_bg`, a solid-white knockout of the box *before* `super().paint()`; a dashed `#88aaff` cosmetic frame while **editing** (distinct state); the **selected** state uses the canonical dashed `SELECTION_OUTLINE_COLOR` boundary + 8 grips. **`zValue = 15`** — above viewports (z=5) and the title block (z=10), so text is never occluded.
- **Move / clamp:** `itemChange` clamps the proposed anchor into the paper rect on `ItemPositionChange` and live-syncs `x/y` into the data on `ItemPositionHasChanged` (mirrors `SheetViewport`). Delete key removes the block when selected, but deletes a character while editing. The full box catches clicks (grab-anywhere) — a sparse note is not click-through.

Dropped from `NoteAnnotation`: white default, `level`, `Layer` enum, `grip_points`/`apply_grip`, integer `setPointSize`.

### 9.4 Paper-Fixed mm Sizing (the invariant)

Text height is a real paper millimetre — identical on the 96-dpi screen and in the 300-dpi PDF/print — achieved with a **device-independent pixel-size font + geometric `setScale`** (§9.3), not a point size. Point sizes are DPI-dependent and render ~2.4× oversize through `paper_export` (`QPdfWriter.setResolution(300)` vs the 96-dpi screen); this is the same latent bug the existing title block / view-titles carry (§4.11 follow-up). Precedent: `model_space.py` dimension text already sizes via `setPixelSize`. `_TEXT_METRIC_REF` is a large constant (e.g. 1000) so `QFontMetricsF` is precise; recompute the scale only on a height/family/bold/italic change, not per paint.

### 9.5 Authoring Interactions [revised 2026-07-20 — ribbon supersedes the widget toolbar]

**Add Text is a checkable ribbon button** (Draft tab → Annotate group; the `PaperSpaceWidget` toolbar is retired — the widget exposes a public command API: `change_paper` / `set_add_text_mode` / `refresh_viewport` / `fit_sheet`, with Refresh/Fit as Draft-tab small buttons). Clicking it from a model tab **auto-activates the paper sheet tab** first; the button un-checks on placement, mode exit, leaving the paper tab, and **Esc** (the view accepts the `ShortcutOverride` for `Key_Escape` while in place-mode so the window-level Escape `QShortcut` can't steal it). Entering the mode emits `add_text_mode_toggled`, which shows the **text template** in the property panel (§9.6) and targets the ribbon Font group at it.

A click on the sheet drops a *transient* item already in inline edit, **seeded from `PaperScene.text_template`** (formatting fields only — never text/position/wrap/box). The first non-empty commit (focus-out **or Esc** — Esc means "done typing", not cancel) pushes an `AddTextAnnotation` command; an empty commit discards silently (nothing on the undo stack). Existing blocks: double-click → inline edit; drag → move from **anywhere in the box** (grab-anywhere, §9.3); right-click → **Delete only**; `Delete` → remove when selected (a character while editing). Event-driven deletes defer via `QTimer.singleShot` (no reentrant destruction), mirroring viewport delete.

### 9.6 Formatting Surfaces — Property Panel + Ribbon Font Group [revised 2026-07-20]

`TextAnnotationPropertiesDialog` is **deleted**. Formatting has two coexisting surfaces sharing one write path:

- the right-side **property panel**: `TextAnnotationItem` implements the duck-typed `get_properties()`/`set_property()` protocol (rows: font, height, bold, italic, underline, color, alignment, opaque background, plus a read-only **Leader** placeholder for the leader follow-up);
- the **Draft-tab Font group** (`font_group.py` `FontGroupController`, governed by `ribbon-bar.md`): a quick-format subset (family, Word-ladder pt size, grow/shrink, B/I/U, color, alignment) that drives the SAME `set_property` route — enabled only when the paper tab is active with sheet text selected (or in Add-Text mode, targeting the template), one undo macro per multi-select gesture, no command on no-op gestures, Word-style mixed-value display, and mutual re-sync with the panel.

Widget/write-path mechanics are owned by `property-panel.md` (§3.2/§3.3 — Rule A); this section owns the text-specific contracts:

- **Undo routing (§17):** `set_property` on a scene-attached item pushes one `FormatTextCommand`; the panel wraps multi-select commits in a stack macro (one Ctrl+Z reverts all targets). Off-scene items (the template) write directly — no stack.
- **Selection wiring:** `PaperScene.selectionChanged`, `undo_stack.indexChanged`, and tab changes all re-populate the panel (main window `update_paper_property_manager`); only `TextAnnotationItem`s are shown — viewports keep `SheetViewPropertiesDialog` (follow-up filed). **While Add-Text mode is active the panel keeps showing the template** (refreshes must not blank it — e.g. an undo mid-placement fires `indexChanged` with nothing selected).
- **Height field (Word-style pt):** displays/parses **em-based font points** (`"12 pt"` visually matches 12 pt Arial in Word) via the font's capHeight/em ratio at `TEXT_METRIC_REF_PX`; storage stays cap-height mm (§5.3, §9.4 invariant untouched). Bare numbers and `pt` suffixes mean points; explicit dimension strings (`1/8"`, `3mm`) still parse as literal cap heights via `_parse_text_height_mm` (bare leading fractions pre-processed). Guards: blank/unparseable/**non-positive** input keeps the stored value (a zero would divide-by-zero in `_apply_format`'s wrap-scale); an **untouched** field keeps the exact stored `height_mm` (`DimensionEdit` seed guard — avoids display-precision re-quantization, e.g. imperial 3/16"→1/4" at 1/8" resolution).
- **Template ("last-used defaults"):** `MainWindow.current_text_template` is an off-scene `TextAnnotationItem` (pipe/sprinkler pattern); its data object is aliased to `PaperScene.text_template` and persists across sessions via QSettings `template/text` (`text_template_to_settings`/`apply_template_settings`, string-coercion + non-positive-height fallback). Pre-placement edits only — placed-item edits never flow back.

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
| `firepro3d/paper_space.py` | Sheet subsystem: `Sheet`/`SheetViewData`/**`TextAnnotationData`** (data + serialization), `ViewResolver` (view→scene/rect bridge), `SheetViewport`, **`TextAnnotationItem`**, `PaperScene` (composition + `dispose()` + **`QUndoStack`** owner), `PaperSpaceWidget`, title blocks (`TitleBlockTemplateItem` template renderer + legacy `TitleBlockDxfItem`/`PdfItem`/`Item` fallbacks), `sheet_page_mm`, dialogs (`SheetViewPropertiesDialog`, `RevisionsDialog` — `TitleBlockDialog` retired 2026-07-21; sheet text has no dialog; §9.6 panel) |
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
- [ ] Mixed paper sizes per sheet within a set *(deferred 2026-08-06 — uniform size for the multi-sheet MVP, §4.10/§19.1)*
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

Viewport: `AddViewportCommand`, `RemoveViewportCommand`, `ViewportGeometryCommand` (move **and** resize), `ChangeViewportPropertiesCommand` (title/show_border/scale + derived w,h). Text: `AddTextAnnotationCommand` (pushed only on the first non-empty commit; on emptying an existing block it restores the original text so undo brings it back intact), `DeleteTextAnnotationCommand`, `MoveTextAnnotationCommand`, `ResizeTextBoxCommand` (renamed from `WrapResizeTextCommand` 2026-07-20; carries the full `(x, y, wrap_width_mm, box_height_mm)` old/new tuples — one command per 8-handle drag), `EditTextCommand`, `FormatTextCommand`. *(As-built: move and box-resize are two separate commands; no `mergeWith`/`id()` is needed because each drag captures geometry at mouse-press and pushes exactly one command at release. Commands key on persistent `SheetViewData`/`TextAnnotationData` **identity** — the sheet-list membership/removal is identity-based, so two value-identical annotations stay distinct.)* Multi-select formatting commits — from the panel **or** the ribbon Font group — arrive wrapped in a **stack macro** (one `FormatTextCommand` per target inside; one undo step total; no macro/commands at all when every target is a no-op — `property-panel.md §3.3`).

### 17.3 Gesture capture

Move/resize/wrap-resize capture the geometry at `mousePressEvent` and push **one** command at `mouseReleaseEvent` (only if changed and not `_applying_command`); the continuous `itemChange` live-sync stays underneath, untouched. Never push from `itemChange` (it fires every tick and on programmatic `setPos`).

### 17.4 Keyboard & ribbon routing

`QUndoStack.createUndoAction` / `createRedoAction` → `Ctrl+Z` / `Ctrl+Y` (plus `Ctrl+Shift+Z` for redo, matching model-space), `setShortcutContext(WidgetWithChildrenShortcut)` on the paper view. `PaperGraphicsView.event()` accepts `ShortcutOverride` for those keys (mirror the existing `Key_Delete` handling) so they reach the widget action ahead of the window-scoped ribbon button. The ribbon Undo/Redo buttons dispatch on `central_tabs.currentWidget()` (paper stack vs `Model_Space`).

### 17.5 Lifetime & reset [as-built 2026-07-20]

Never serialized (session-only by construction). Cleared in `PaperScene.update_from_sheet` (the single project-load choke point); `new_file` and every load path reach it through `PaperSpaceWidget.set_sheet` (§17.7). The paper-size setter does **not** clear the stack — commands key on persistent data identity (§17.1) and survive the `_setup()` rebuild, so clearing is unnecessary; the setter also skips no-op assignments (same size → no rebuild, no signal) and emits `sheetModified` on a real change.

### 17.6 Prerequisite — one canonical `PaperScene` (mandatory)

`_activate_paper_sheet` currently constructs a **second** `PaperSpaceWidget`, so the on-screen scene is not `self.paper_space_widget.paper_scene` (which is what load/title-block/export target). This is collapsed (reuse the canonical widget) so the undo stack, edits, save, and export all bind to the **one visible scene**. Pre-existing latent bug; mandatory for correct undo.

### 17.7 Dirty Flag & Crash Recovery [added 2026-07-20]

Paper mutations participate in the project-wide unsaved-changes flag (`MainWindow._modified`: title `*`, save prompts, autosave eligibility) via **`PaperScene.sheetModified`** (a `pyqtSignal()`), connected to a minimal `MainWindow._on_paper_modified` (sets the flag + title only — deliberately *not* `_on_scene_modified`, so paper edits never trigger the model-space 3D-view refresh debounce).

**Emission rule — dirties iff it changes bytes `Sheet.to_dict()` would emit:**

| Surface | Emits? | Mechanism |
|---|---|---|
| Text + viewport commands, undo, redo | Yes | relay from `undo_stack.indexChanged` |
| Paper size change | Yes (real change only) | setter emits; no-op sets skipped entirely |
| Title-block field edit (dialog OK with a change) | Yes | `_edit_title` snapshots fields, emits on diff |
| Load/new rebuild (`update_from_sheet`, incl. its `undo_stack.clear()` → `indexChanged` and programmatic Scale-field write) | **No** | `_suppress_modified` guard around the rebuild |
| Add-Text **template** edits | **No** | QSettings-only; off-scene item never routes through the stack |
| Cancelled dialogs / no-op gestures | **No** | no data change → no command → no emit |

Semantics are **latch-until-save** (matching model space): undo/redo dirty; undoing back to the save point does *not* un-dirty (no `QUndoStack` clean-state tracking).

**Load paths & crash recovery.** `PaperSpaceWidget.set_sheet(sheet, resolver)` is the single load-path entry point: it rebinds `widget._sheet`, the scene's resolver (`PaperScene.set_resolver` — before `update_from_sheet`, since `SheetViewport` captures the resolver at construction), and rebuilds via `update_from_sheet`. Open, crash recovery, and `new_file` all route through it — a stale `widget._sheet` previously sent post-load title-block edits into a detached dict. `_check_recovery` (main.py) restores via the shared `_apply_loaded_file()` with **full File→Open parity**, deviating only in: `_current_file=None` (first Save prompts Save-As), `_modified=True`, and no recent-files entry. Declined recovery deletes the autosave and changes nothing. Coverage: `tests/test_paper_persistence.py`.

## 18. Out of Scope

- **View catalog unification** — paper space queries existing managers directly, no new abstraction
- **Annotation scale system in model space** — paper space defines annotations as paper-space-only; the label thin-lines toggle is defined here but the broader annotation scale rework is separate
- **Cross-view selection sync** — deferred in view-relationships spec (§1.3)
- **Editing through sheet views** — view-only, not interactive
- **Revision workflow / approvals** — data model defined, workflow process is separate
- **Custom title block template builder UI** — field mapping defined, authoring tool deferred
- **Sheet-text follow-ups (deferred from the 2026-06-26 build):** other annotation types (leader / line / rectangle / revision cloud / north arrow / scale bar); legends & schedules as Revit-style **placed tables**; copy / paste / duplicate of text blocks; rotated text; border-box; rich (per-character) text; cross-sheet / shared "same note on every sheet" content; title-block-field-edit undo; paper-space text as a **Display-Manager category** (project-level color / background customization); and the latent **point-size ~2.4× PDF over-sizing** fix for `TitleBlockItem` + viewport view-titles (§4.11).

## 19. Multi-Sheet Management [designed 2026-08-06 — proposal until build stamps it]

Resolves the single-sheet bottleneck: `main.py` currently overwrites `scene._sheets = [self._sheet]` on save and loads only `_sheets[0]`, silently dropping extra sheets — the headline bug this section kills. The `.fpd` format is untouched (the `"sheets"` list already round-trips; **zero `scene_io.py` changes**, and no active-sheet key is ever persisted).

### 19.1 Identity & invariants (grilled 2026-08-06)

- **`Sheet.number` is the identity:** required, unique per project; `name` free-form, non-unique. UI displays `"{number} - {name}"`. Legacy/empty numbers tolerated on load; collisions rejected at entry (old value kept + status-bar message).
- **≥1 sheet invariant:** deleting the last sheet is blocked. Delete always confirms with a content summary (views/annotations counts).
- **Sheet-level ops are non-undoable** (create/delete/rename/renumber/reorder); the paper undo stack **clears on sheet switch** (free via `update_from_sheet`, §17.5). Content ops stay undoable per sheet.
- **Uniform paper size (MVP):** size/orientation changes (ribbon Paper Size, template "Use for this project") apply to **all** sheets. Per-sheet `paper_size` stays in the data model; mixed sizes re-enable when the per-size template library lands (deferred follow-up).
- **Active sheet rules:** first in list on load; new sheet on create; successor (else predecessor) on deleting the active sheet. Never persisted.

### 19.2 `SheetManager`

Pure-Python class in `paper_space.py` operating **by reference** on the same list `scene._sheets` binds (the persisted home). Owns: ordered `sheets`, `get(number)`, `validate_number(number, ignore)`, `suggest_number()` (pattern-following: FP-1.0 → FP-2.0, plain 1 → 2), `create()` (auto number + default name, appended, instant — no dialog), `delete(sheet)` (raises on last; returns the neighbor to activate), `reorder(numbers)`. No Qt imports — invariants are plain-unit-testable. `MainWindow` orchestrates: call manager → switch via the existing `PaperSpaceWidget.set_sheet(sheet, resolver)` primitive → push UI (browser `set_sheets`, tab title `"{number} - {name}"`, panel) → dirty.

### 19.3 Dirty-flag additions (§17.7 table extension)

| Surface | Emits? | Mechanism |
|---|---|---|
| Sheet create / delete / rename / renumber / reorder | Yes (real change only) | `MainWindow` calls `_on_paper_modified()` directly after the manager op |
| Rejected rename/renumber, cancelled delete, no-op reorder | No | no data change |
| Sheet switch | No | `update_from_sheet` rebuild is `_suppress_modified`-guarded (unchanged) |

### 19.4 Sheet properties panel & Esc

- `SheetProperties` adapter (duck-typed `get_properties`/`set_property`, `property-panel.md` protocol) wraps `(sheet, manager, callbacks)`. Rows: **Number** (validated), **Name**; read-only Paper Size / Orientation. Renumbering the active sheet refreshes tab title, browser row, titleblock Sheet No, and dirties.
- **Panel precedence (paper tab):** paper-scene selection → else browser-selected sheet (`sheetSelected`) → else **active sheet**. The panel is never blank on the paper tab.
- **Esc:** `_on_escape` branches on the paper tab — clears `PaperScene` selection (not the model scene), panel falls back to sheet properties; Esc on empty selection is a panel no-op. (Model-space Esc-blanks-panel is a filed follow-up: empty selection should show active-view properties.)

### 19.5 Browser contract

Sheet-tree mechanics (pure push, row keying by number, `createPaperSheet()`/`deletePaperSheet(number)`/`sheetSelected(number)`/`sheetOrderChanged(list)`, guarded internal-move `dropEvent`, in-place `set_placed_views` restyle) are owned by `project-browser.md` §"Multi-sheet design deltas" — Rule A, link only. Placed-views recompute triggers live here: on load, on `_on_paper_modified`, after sheet ops (from all sheets' `sheet_views`).

### 19.6 Batch export & print (activates §7.1/§7.5)

New `paper_export_dialog.py`: sheet checklist in document-set order (all checked, Select All), mode radio (single multi-page PDF / separate files), output picker (file vs directory per mode), DPI combo (150/**300**/600), OK disabled at zero selection. Multi-page mode feeds the selection straight to `paper_export.export_pdf(sheets, …)` (already loops `newPage()`); separate-files mode loops per sheet, naming `{number} - {name}.pdf` with `\/:*?"<>|` → `_`. Print reuses the dialog (path/DPI hidden) → `QPrintDialog` → `print_sheets(selection, …)`. Page order = list order. Zero-viewport sheets export (cover sheets, §10.5).

### 19.7 "Sheet No" auto field

`build_field_values` resolves "Sheet No" → the sheet's `number` (manually authored in the sheet properties panel — one home); the editor's disabled picker entry flips enabled (+ `_SAMPLE_VALUES` sample). Batch export renders it per-sheet via the existing per-sheet `render_sheet` values.

### 19.8 Testing contract (grilled)

Unit: manager invariants (uniqueness, suggest, ≥1, neighbor, reorder), Sheet No in `build_field_values`, placed-views computation, filename sanitization. Widget-driven: browser create/delete/reorder flows end-to-end incl. phantom-free cancel; panel number/name commits via `editingFinished`; Esc fallback. Integration: **3-sheet save→load→save round-trip** (headline regression), batch page count == selection, per-file naming, per-op dirty emissions, undo-clear on switch, legacy single-sheet `.fpd` intact, recovery restores all sheets. Never construct a real-driver `QPrinter` in tests (`QPdfWriter`/mocks only — known SEH hazard).

