# Paper Space — Design Spec

**Date:** 2026-04-09
**Complexity:** Large
**Status:** Draft
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
- **View-only interaction.** No picking or editing through sheet views. Double-click or right-click "Go to View" navigates to the source model view.
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

```
AnnotationData:
  type: str                 # "text" | "leader" | "line" | "rectangle" |
                            # "revision_cloud" | "north_arrow" | "scale_bar"
  geometry: dict            # type-specific position/shape data
  properties: dict          # type-specific styling (font, color, etc.)
```

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

### 9.1 Paper-Space Annotations [Phase 2]

Annotations are `QGraphicsItem` subclasses added directly to `PaperScene`. They exist only on the sheet — not in model space, not in the project's model data. They serialize in the sheet's `annotations` array.

| Type | Description |
|------|-------------|
| Text | Multi-line text block with font, size, alignment, color |
| Leader | Arrow + landing line + text callout |
| Line / Rectangle | Simple geometry for markup |
| Revision cloud | Arc-segment boundary around changed areas, linked to a revision entry |
| North arrow | Symbol, fixed set of built-in styles |
| Scale bar | Graphic scale bar, auto-sized from sheet view scale |

**Future annotation types** [Phase 3]: Schedules/tables, legends, imported images (logos, site photos), symbol blocks.

### 9.2 Model-Space Labels [Phase 2]

Labels are existing model-space items (room names, pipe sizes, node IDs, gridline bubbles) that render through sheet views. They gain a `paper_height_mm` property — the height they should appear at on paper.

- **Model-space editing (thin-lines OFF):** Labels render at `paper_height_mm` in model units. At 1:1 they are tiny. This is "true scale" — WYSIWYG preview of print output.
- **Model-space editing (thin-lines ON, default):** Labels render at a fixed readable screen size via `ItemIgnoresTransformations`. Standard editing workflow.
- **Sheet view rendering:** Labels always render at `paper_height_mm` scaled by the sheet view's scale factor. Thin-lines toggle has no effect in paper space.

### 9.3 Constraint Filter

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

| File | LOC | Role |
|------|-----|------|
| `firepro3d/paper_space.py` | 763 | Current scaffold: `PaperSpaceWidget`, `PaperScene`, `PaperViewport`, `TitleBlockItem`, `TitleBlockDxfItem`, `TitleBlockPdfItem`, `TitleBlockDialog` |
| `firepro3d/scene_io.py` | — | Project serialization (`save_to_file`/`load_from_file`), JSON format — extend for `"sheets"` key |
| `firepro3d/level_manager.py` | — | `PlanView`, `PlanViewManager` — queried by sheet view picker |
| `firepro3d/detail_view.py` | — | `DetailViewManager`, `DetailMarker` — queried by sheet view picker, provides crop rects |
| `firepro3d/elevation_scene.py` | 1233 | `ElevationScene` (`QGraphicsScene`) — render target for elevation sheet views |
| `firepro3d/elevation_view.py` | — | `ElevationView` (`QGraphicsView`) — elevation UI widget |
| `firepro3d/view_marker.py` | — | `ViewMarkerManager` — queried for elevation view names |
| `firepro3d/user_layer_manager.py` | — | Layer system — extended for per-sheet-view overrides |
| `firepro3d/model_space.py` | — | `Model_Space` (`QGraphicsScene`) — render target for plan/detail sheet views |
| `firepro3d/annotations.py` | 739 | `NoteAnnotation`, `DimensionAnnotation` — currently model-space; annotations migrate to paper-space-only |
| `firepro3d/default titleblocks/` | — | DXF + PDF templates for ANSI B/D |

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

**Integration tests:**
- Create project → add geometry → create sheet → place sheet view → verify render is non-empty
- Full export pipeline: create project → geometry → sheet → export PDF → verify PDF has correct page count, non-zero file size, and correct page dimensions
- Dangling reference: delete source view → verify sheet view shows placeholder
- Dirty-flag: modify model geometry → verify sheet view re-renders on next paint

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
- [ ] PDF export: single sheet, batch multi-page, per-sheet separate files — vector output
- [ ] Print: system dialog, single + batch with mixed page sizes
- [ ] Project browser: sheet tree with drag-to-reorder
- [ ] Backward compatibility: projects without sheets load normally

### Phase 2

- [ ] Full layer visibility overrides per sheet view (show/hide any layer)
- [ ] Paper-space annotations: text, leaders, lines, rectangles, revision clouds, north arrows, scale bars
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

## 17. Out of Scope

- **View catalog unification** — paper space queries existing managers directly, no new abstraction
- **Annotation scale system in model space** — paper space defines annotations as paper-space-only; the label thin-lines toggle is defined here but the broader annotation scale rework is separate
- **Cross-view selection sync** — deferred in view-relationships spec (§1.3)
- **Editing through sheet views** — view-only, not interactive
- **Revision workflow / approvals** — data model defined, workflow process is separate
- **Custom title block template builder UI** — field mapping defined, authoring tool deferred
