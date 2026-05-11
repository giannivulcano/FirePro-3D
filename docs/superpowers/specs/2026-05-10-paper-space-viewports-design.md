# Paper Space Viewports & Title Block — Design Spec

**Date:** 2026-05-10
**Complexity:** Large
**Status:** Draft
**Parent spec:** `docs/specs/paper-space.md` (MVP Phase 1, scoped subset)
**Grill-me session:** Same conversation, Phase 2

---

## 1. Goal

Enable multi-viewport paper space with drag-from-browser placement, scale control, and title block field integration on a single sheet.

## 2. Motivation

The existing paper space scaffold (`paper_space.py`, 763 LOC) renders one fixed viewport with no scale control, no view selection, no persistence, and no field overlay on DXF/PDF title blocks. This work turns it into a functional sheet compositor: users drag views from the browser, choose a scale, position/resize viewports, and see title block fields auto-populated — matching the Revit workflow they already know.

## 3. Scope

### In

- Single sheet, always-present "Paper Space" tab
- Three source view types: plan, detail, elevation (no 3D)
- Placement: drag views from a new "Views" group in the browser tree (grouped by type)
- Pre-placement dialog: Title + Scale selection, reopenable via right-click "Properties..."
- Viewport interaction: movable + resize grips (8 handles), select + Delete key, right-click context menu
- Multiple viewports per sheet
- Scale: presets (imperial + metric) + custom, auto-populates title block Scale field ("AS NOTED" when mixed)
- Auto-sizing: viewport sized from source view content bounds at chosen scale
- Title block: DXF artwork as Qt paths (ANSI B/D) + Qt-drawn field overlay, programmatic fallback for other sizes
- Dirty-flag + pixmap cache rendering
- Serialization: round-trip save/load under `"sheets"` key, backward compat
- Double-click "Go to View" navigation
- Right-click dialog for post-placement property editing

### Out

- Multi-sheet management (tabs, create/delete/reorder)
- PDF export / print
- Toolbar "Add View" button
- Layer overrides per viewport
- Annotations
- Property panel integration
- 3D viewport hosting
- DXF ATTDEF-based field positioning

## 4. Architecture

### 4.1 Three-Layer Split (Option C)

```
Sheet (data)           SheetViewport (scene item)      PaperSpaceWidget (UI)
  SheetViewData          pixmap cache + dirty flag        drop target
  title_block_fields     resize grips                     toolbar
  to_dict/from_dict      context menu                     zoom/pan
                         source scene rendering
                    
ViewResolver (bridge)  PaperScene (compositor)         ModelBrowser (drag source)
  resolve(type, name)    manages SheetViewport items      Views group
  available_views()      title block overlay              drag MIME encoding
                         scale auto-population
```

All new classes live in `paper_space.py`. No new files.

### 4.2 Data Model

```python
@dataclass
class SheetViewData:
    source_view_type: str    # "plan" | "detail" | "elevation"
    source_view_name: str    # e.g. "Level 1", "Detail 1", "North"
    title: str               # display name on sheet (defaults to source view name)
    scale: float             # ratio, e.g. 0.01 for 1:100
    x: float                 # position on sheet (mm from left)
    y: float                 # position on sheet (mm from top)
    w: float                 # width on sheet (mm)
    h: float                 # height on sheet (mm)

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> SheetViewData: ...

@dataclass
class Sheet:
    number: str              # "FP-1.0"
    name: str                # "Fire Suppression Layout"
    paper_size: str          # "ANSI D"
    title_block_fields: dict # 9 fields: Company, Project, Title, Scale, etc.
    sheet_views: list[SheetViewData]

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> Sheet: ...
```

- `scale` stored as float ratio (0.01 = 1:100). Display strings are a presentation concern.
- `title_block_fields` owns the field data; `TitleBlockItem` and `TitleBlockFieldOverlay` read from it.

### 4.3 ViewResolver

```python
class ViewResolver:
    def __init__(self, model_scene, plan_view_manager,
                 detail_manager, elevation_manager): ...

    def resolve(self, view_type: str, view_name: str
                ) -> tuple[QGraphicsScene, QRectF] | None:
        """Returns (source_scene, source_rect) or None if not found."""

    def available_views(self) -> dict[str, list[str]]:
        """Returns {"Floor Plans": [...], "Details": [...], "Elevations": [...]}."""
```

Resolution logic:
- `plan` → `Model_Space` scene, source rect from items visible within the plan view's Z-range
- `detail` → `Model_Space` scene, source rect from `DetailMarker.crop_rect`
- `elevation` → `ElevationScene` instance for that direction, full scene bounds

Returns `None` for dangling references (deleted source view).

Single instance created in `main.py`, passed to `PaperScene` and `ModelBrowser`.

### 4.4 SheetViewport

`QGraphicsObject` subclass replacing the current `PaperViewport`. Inherits from `QGraphicsObject` (not `QGraphicsItem`) to support Qt signals for navigation.

**Rendering:**
- Pixmap cache: render source scene into `QPixmap` on first paint or when dirty
- Connect to source scene's `changed` signal → `_dirty = True`
- `paint()` draws cached pixmap scaled to viewport rect
- Scale/resize changes set dirty

**Interaction:**
- `ItemIsMovable`, `ItemIsSelectable` flags
- 8 resize grips (corners + edge midpoints) drawn when selected
- Dragging a grip resizes the viewport (scale stays fixed, visible area changes)
- Minimum size: 20mm x 20mm
- Selected: blue dashed border. Unselected: black hairline border.

**Context menu (right-click):**
- "Properties..." → opens `SheetViewPropertiesDialog`
- "Go to View" → emits `navigate_to_view` signal
- "Delete" → removes viewport from sheet

**Double-click:** same as "Go to View"

**Placeholder:** when `ViewResolver.resolve()` returns `None`, renders a gray rectangle with "View not found: {name}" text and warning icon.

### 4.5 PaperScene Changes

- Remove single fixed `_viewport` from `_setup()`
- Hold list of `SheetViewport` items
- Public API:
  - `add_viewport(data: SheetViewData) -> SheetViewport`
  - `remove_viewport(viewport: SheetViewport)`
  - `update_from_sheet(sheet: Sheet)` — rebuild all viewports from data model (used on load)
  - `get_viewports() -> list[SheetViewport]`
- `add_viewport` / `remove_viewport` mutate both scene items and `Sheet.sheet_views`
- Scale auto-population: viewport add/remove/scale change → update `Sheet.title_block_fields["Scale"]`

### 4.6 Title Block Field Overlay

`TitleBlockFieldOverlay(QGraphicsItem)` draws editable field values as Qt text on top of DXF/PDF artwork.

```python
# Per-template field positions: {field_name: (x, y, w, h, font_size)}
# Coordinates in mm relative to paper origin
FIELD_LAYOUTS = {
    "ANSI D": { "Company": (...), "Project": (...), ... },
    "ANSI B": { "Company": (...), "Project": (...), ... },
}
```

- For ANSI B/D: field positions measured from DXF geometry cell locations
- For other sizes: programmatic `TitleBlockItem` draws both artwork and fields (no overlay needed)
- Overlay reads from `Sheet.title_block_fields`

**Scale auto-population:**
1. Viewport added/removed/scale changed → `PaperScene._update_scale_field()`
2. One viewport → Scale = scale string (e.g., "1:100")
3. Multiple viewports, same scale → Scale = that scale string
4. Multiple viewports, different scales → Scale = "AS NOTED"

### 4.7 Browser Tree — Views Group + Drag

Added to `ModelBrowser.refresh()`:

```
Views
  ├─ Floor Plans
  │   ├─ Level 1
  │   └─ Level 2
  ├─ Details
  │   ├─ Detail 1
  │   └─ Detail 2
  └─ Elevations
      ├─ North
      └─ East
```

**Drag protocol:**
- `DragEnabled` flag on leaf view nodes only
- Custom MIME type: `application/x-firepro3d-view`
- MIME data encodes `view_type` + `view_name`
- Leaf nodes store `("sheet_view", view_type, view_name)` tuple in `UserRole`

**Already-placed indicator:** views on the sheet render in italic font in the browser.

### 4.8 Drop Handling

1. `PaperSpaceWidget.QGraphicsView` overrides `dragEnterEvent`, `dragMoveEvent`, `dropEvent`
2. On drop: decode MIME → open `SheetViewPropertiesDialog` (Title + Scale)
3. If accepted: `ViewResolver.resolve()` gets source bounds → compute viewport size at chosen scale → `PaperScene.add_viewport()` at drop position
4. If viewport exceeds printable area, clamp to fit

### 4.9 Serialization

**Save** — `scene_io.py` adds to payload:
```python
payload["sheets"] = [sheet.to_dict() for sheet in self._sheets]
```

**Load:**
```python
if "sheets" in payload:
    self._sheets = [Sheet.from_dict(d) for d in payload["sheets"]]
```

No `"sheets"` key → empty list (backward compat).

Single sheet: the `"sheets"` list is future-compatible but only index 0 is used.

**Load flow:**
1. Deserialize `Sheet` from JSON
2. `PaperScene.update_from_sheet(sheet)` creates `SheetViewport` items
3. `ViewResolver.resolve()` reconnects each viewport to source scene
4. Dangling references → placeholder rendering

### 4.10 Wiring in main.py

**Initialization order:**
1. Existing managers created as today
2. `ViewResolver` created with references to the four managers
3. `Sheet` created with defaults (paper_size="ANSI D", default fields)
4. `PaperScene` created with `Sheet` + `ViewResolver`
5. `PaperSpaceWidget` wraps `PaperScene`
6. `ModelBrowser` gets `ViewResolver` for Views group

**Go to View navigation:**
- `SheetViewport` emits `navigate_to_view(view_type, view_name)` signal
- `main.py` handler switches to the right tab:
  - plan → activate level, switch to plan tab
  - detail → open detail view tab
  - elevation → show elevation direction tab

## 5. Scale Computation

### 5.1 Presets

**Metric:** 1:200, 1:100, 1:75, 1:50, 1:25, 1:20, 1:10, 1:5, 1:1

**Imperial:** 1/8"=1'-0", 3/16"=1'-0", 1/4"=1'-0", 3/8"=1'-0", 1/2"=1'-0", 3/4"=1'-0", 1"=1'-0", 1-1/2"=1'-0", 3"=1'-0"

**Custom:** user-entered ratio string parsed to float.

### 5.2 Scale String ↔ Float Conversion

```python
def scale_to_float(s: str) -> float:
    """'1:100' → 0.01, '1/4\"=1\\'-0\"' → 1/(4*12) ≈ 0.0208"""

def float_to_scale_str(f: float) -> str:
    """0.01 → '1:100'. Matches nearest preset, falls back to '1:N'."""
```

### 5.3 Auto-Sizing on Placement

1. `ViewResolver.resolve()` returns source rect (model-space mm)
2. Viewport width = `source_rect.width() * scale`
3. Viewport height = `source_rect.height() * scale`
4. If larger than printable area, clamp proportionally
5. Center on drop point

## 6. Dialogs

### 6.1 SheetViewPropertiesDialog

Used both pre-placement and post-placement.

**Pre-placement fields:**
- Title (QLineEdit, defaults to source view name)
- Scale (QComboBox with presets + "Custom..." entry)

**Post-placement adds:**
- Position X, Y (QLineEdit with `format_length`/`parse_dimension`)
- Size W, H (QLineEdit with `format_length`/`parse_dimension`)

OK/Cancel buttons. Modal.

### 6.2 TitleBlockDialog

Existing dialog, modified to read/write `Sheet.title_block_fields` instead of `TitleBlockItem.fields`. Scale field shown as read-only (auto-populated).

## 7. Edge Cases

- **Dangling reference:** source view deleted → viewport renders placeholder with view name and warning
- **Empty source view:** no geometry in source → viewport renders empty white rect with border
- **Scale extremes:** viewport larger than paper → clamp to printable area with warning
- **Viewport overlap:** allowed, no z-order management (last placed is on top)
- **Delete key with no selection:** no-op
- **Drop outside printable area:** clamp viewport position to within paper bounds

## 8. Testing

### Unit Tests
- Scale computation: `scale_to_float` / `float_to_scale_str` round-trips, all presets
- Source rect resolution: plan (Z-filtered bounds), detail (crop rect), elevation (scene bounds)
- `Sheet` serialization round-trip: `to_dict()` → JSON → `from_dict()`, all fields preserved
- `SheetViewData` serialization round-trip
- Title block Scale auto-population: single scale, same scale, mixed scales → "AS NOTED"
- Backward compatibility: project JSON without `"sheets"` key loads with empty sheet set

### Integration Tests
- Dirty-flag: modify source scene → verify viewport `_dirty` set to True
- Dangling reference: mock a missing view → verify placeholder rendering (no crash)

### Manual Smoke Testing
- Drag plan/detail/elevation view from browser → scale dialog → viewport appears at correct size
- Move viewport by dragging, resize via grips
- Right-click → Properties → change scale → viewport resizes
- Double-click viewport → navigates to source view
- Select viewport + Delete → removed
- Save project → reload → viewports restored at correct positions/scales
- Title block Scale field updates as viewports are added/removed
- Views already placed show italic in browser

## 9. Files Modified

| File | Change |
|------|--------|
| `firepro3d/paper_space.py` | Add `SheetViewData`, `Sheet`, `ViewResolver`, `SheetViewport`, `TitleBlockFieldOverlay`, `SheetViewPropertiesDialog`. Refactor `PaperScene` for multi-viewport. Modify `PaperSpaceWidget` for drop handling. |
| `firepro3d/model_browser.py` | Add "Views" group with drag support. Already-placed italic indicator. |
| `firepro3d/scene_io.py` | Add `"sheets"` key to save/load payload. |
| `firepro3d/main.py` | Create `ViewResolver`, `Sheet`. Wire `PaperScene` with new args. Connect "Go to View" navigation. |
| `tests/test_paper_space.py` | Existing 43 tests; add new tests for scale, serialization, title block auto-population, dirty flag, dangling refs. |
