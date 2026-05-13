# Paper Space Display Manager Tab — Design Spec

**Date:** 2026-05-12
**Status:** Draft
**Depends on:** Display Manager (`display_manager.py`), Paper Space (`paper_space.py`)

## 1. Goal

Add two tabs to the Display Manager dialog — "Paper Space" for per-category print display overrides, and "Line Weights" for defining named pen weights — so engineers can control how viewports render on sheets independently of the model-space display.

## 2. Motivation

AHJ submittals are typically black-and-white with specific line weights per category (heavy walls, medium pipes, thin gridlines). Today, paper-space viewports render in full color using model-space display settings with cosmetic 1px pens. There is no way to control print appearance separately from the working model.

## 3. Architecture & Constraints

### 3.1 Override Scope

Global paper-space overrides — one set of category display settings applies to all viewports on all sheets. Per-viewport overrides are a future feature.

### 3.2 Rendering Approach — Temporary Mutation

Paper-space overrides are applied via temporary mutation of scene items during viewport rendering:

1. `_apply_paper_overrides()`: save current display state, apply paper-space category settings
2. `scene.render()`: items paint with overridden values
3. `_restore_model_display()`: restore original display state

This is safe because Qt GUI rendering is single-threaded — no other paint event can interleave. It follows the same pattern the paper-space spec (§6.2 steps 4-7) already plans for layer visibility overrides.

### 3.3 Cascade

Paper-space category settings override everything unconditionally during viewport rendering. Per-instance model overrides do not bleed through — if B&W mode sets all pipes to black, a pipe with a red per-instance override in model space still renders black in paper space.

### 3.4 Constraint: No Per-Instance Rows

The paper-space tab shows category-level overrides only. No per-instance rows. This keeps the tab focused on presentation output rather than individual item control.

## 4. Design Decisions

### D1: Properties Exposed

The paper-space tab exposes five properties per category:

| Property | Type | Notes |
|----------|------|-------|
| Colour | hex | Pen/stroke colour |
| Fill | hex | Fill colour |
| Section Colour | hex | Section-cut hatch colour |
| Line Weight | dropdown (named) | References a line weight definition |
| Opacity | int 0-100 | Transparency |

**Excluded from paper-space tab:** Visible (controlled by layer visibility), Scale (model concern), Font (model concern), per-instance rows.

Section pattern and section scale inherit from model-space settings. Only section colour is overridable in paper space.

### D2: Color Mode

A dropdown at the top of the Paper Space tab with three states:

| Mode | Behaviour |
|------|-----------|
| Full Color | Colour/Fill/Section columns disabled (inherit from model). Line Weight and Opacity still apply. |
| B&W | All categories set to black stroke (#000000), white fill (#ffffff), black section (#000000). User can tweak individual categories (auto-switches to Custom). |
| Custom | User has manually edited colour values. |

**State transitions:**
- Selecting B&W populates all colour fields with black/white
- Editing any colour/fill/section value while in Full Color or B&W switches mode to Custom
- Selecting Full Color disables colour columns (values preserved but ignored)
- Factory default: **B&W**

### D3: Line Weight Definitions

A two-column table on a dedicated "Line Weights" tab:

| Name | Width (mm) |
|------|-----------|
| Very Light | 0.13 |
| Light | 0.18 |
| Medium | 0.25 |
| Heavy | 0.35 |
| Very Heavy | 0.50 |

- User can add custom named weights and remove unused ones
- Names must be unique, widths must be positive and ≤ 3.00mm
- Sorted ascending by width
- Remove is disabled when a weight is referenced by any paper-space category
- Editable inline (double-click cell)
- Renaming a weight cascades to all category references (categories store by name)
- Add/Remove buttons below the table

### D4: Factory Default Line Weight Assignments

| Category | Default Line Weight |
|----------|-------------------|
| Wall | Heavy |
| Roof | Medium |
| Room | Very Light |
| Floor | Medium |
| Pipe | Medium |
| Sprinkler | Medium |
| Fitting | Medium |
| Water Supply | Medium |
| Node | Light |
| Hydraulic Badge | Very Light |
| Grid Line | Very Light |
| Level Datum | Very Light |
| Elevation Marker | Very Light |
| Detail Marker | Light |

### D5: Line Weight Application

Model-space items use cosmetic pens (1px regardless of zoom). During paper-space rendering, the temporary mutation replaces cosmetic pens with real-width pens: `QPen(color, width_mm)`. Since the viewport renders at a known scale via `scene.render(painter, target_rect, source_rect)`, the pen width in scene coordinates (mm) produces the correct physical width on paper.

### D6: SVG Item Handling

Sprinkler, Fitting, Water Supply, and Hydraulic Badge use SVG renderers. During temporary mutation:
- Call existing `_recolor_svg_bytes()` to swap stroke/fill colours
- Cache original SVG renderer data for restore
- On restore, reinstate original SVG data

## 5. Display Manager Dialog Structure

### 5.1 Tab Layout

```
┌───────────────────────────────────────────────────┐
│  [Model]  [Paper Space]  [Line Weights]           │
├───────────────────────────────────────────────────┤
│  (tab content area)                               │
├───────────────────────────────────────────────────┤
│  [Set as Default]        [OK] [Cancel] [Reset All]│
└───────────────────────────────────────────────────┘
```

### 5.2 Model Tab

Existing tree widget, unchanged. Moved from the dialog's central widget into the first tab page.

### 5.3 Paper Space Tab

Color Mode dropdown at top. Below it, a tree widget with 6 columns:

| Column | Width | Widget |
|--------|-------|--------|
| Name | stretch | text |
| Colour | 60px | colour swatch button |
| Fill | 60px | colour swatch button |
| Section | 60px | colour swatch button (disabled if category has no section) |
| Line Weight | 100px | QComboBox populated from Line Weights tab |
| Opacity | 90px | QSpinBox 0-100 |

Same 3-group structure (Fire Suppression, Architecture, Grids & Levels) with 14 category rows. No per-instance child rows.

### 5.4 Line Weights Tab

Two-column QTableWidget (Name: QLineEdit, Width: QDoubleSpinBox 0.01-3.00). Add and Remove buttons below. Sorted by width ascending.

### 5.5 Context-Aware Default Tab

- Opened from model space (plan view, elevation view): defaults to Model tab
- Opened from paper space: defaults to Paper Space tab
- Detected via `central_tabs.currentWidget()` — if it's a `PaperSpaceWidget`, open to Paper Space tab

### 5.6 Button Bar Behaviour

- **Set as Default:** saves the active tab's settings to QSettings
- **Reset All:** resets the active tab to factory defaults
- **OK:** commits all three tabs
- **Cancel:** reverts all three tabs via snapshot/restore
- Live preview on all tabs — changes apply immediately, Cancel reverts

## 6. Viewport Rendering Pipeline

### 6.1 Current Flow (SheetViewport.paint)

```
paint() → fillRect white → setClipRect → scene.render() → draw border/title
```

### 6.2 New Flow

```
paint()
  → fillRect white
  → setClipRect
  → _apply_paper_overrides(source_scene)
  → scene.render()
  → _restore_model_display(source_scene)
  → draw border/title
```

### 6.3 _apply_paper_overrides(scene)

1. Collect visible items in `_source_rect` via spatial filter (not all scene items)
2. For each item, determine display category via `_category_for_item()` (isinstance checks, O(1))
3. Save current state to temporary dict: `{item: {color, fill, section_color, pen, opacity}}`
4. Apply paper-space overrides:
   - If `FULL_COLOR`: skip colour/fill/section, apply line weight + opacity only
   - If `BW` or `CUSTOM`: apply all five properties
5. For SVG items: call `_recolor_svg_bytes()`, cache original renderer

### 6.4 _restore_model_display(scene)

1. Walk saved dict, restore each item's original properties
2. For SVG items: restore cached renderer data

### 6.5 Performance

- Spatial filter: only items within viewport source rect are processed
- Dirty flag: mutation only occurs on dirty repaints, not every paint cycle
- Category lookup: O(1) isinstance check per item

## 7. Persistence

### 7.1 QSettings (Global Defaults)

```
paper/color_mode                         = "bw"
paper/line_weights                       = [{"name": "...", "width": 0.13}, ...]
paper/categories/{category_key}/color    = "#000000"
paper/categories/{category_key}/fill     = "#ffffff"
paper/categories/{category_key}/section_color = "#000000"
paper/categories/{category_key}/line_weight   = "Medium"
paper/categories/{category_key}/opacity       = 100
```

"Set as Default" writes current paper-space tab state here. New projects and projects without `paper_display` settings start with these values.

### 7.2 Project File (.fpd JSON)

```json
{
  "paper_display": {
    "color_mode": "bw",
    "categories": {
      "Pipe": {
        "color": "#000000",
        "fill": "#ffffff",
        "section_color": "#000000",
        "line_weight": "Medium",
        "opacity": 100
      }
    }
  }
}
```

Saved via the existing `get_display_settings_for_save()` / `apply_project_display_settings()` pattern in `scene_io.py`. Line weight definitions are NOT saved per-project — they are global (QSettings only).

### 7.3 Load Priority

1. Project file `paper_display` key (if present)
2. QSettings `paper/` keys (if no project settings)
3. Factory defaults (if no QSettings)

### 7.4 Backward Compatibility

Old projects without a `paper_display` key load factory defaults (B&W mode with standard line weights). No migration needed.

## 8. Acceptance Criteria

1. Display Manager dialog has 3 tabs: Model (existing, unchanged), Paper Space, Line Weights
2. Paper Space tab shows 14 categories in 3 groups with Colour, Fill, Section Colour, Line Weight, Opacity columns — no Visible, Scale, Font, or per-instance rows
3. Color Mode dropdown (Full Color / B&W / Custom) with correct state transitions: Full Color disables colour columns, B&W populates black/white, editing colours switches to Custom
4. Line Weights tab has a two-column editable table with Add/Remove; factory defaults: Very Light (0.13), Light (0.18), Medium (0.25), Heavy (0.35), Very Heavy (0.50)
5. Viewports render using paper-space overrides via temporary mutation — category settings override all model display including per-instance overrides
6. Line weights applied as real pen widths (not cosmetic)
7. Live preview — changes update viewports immediately, Cancel reverts
8. Persistence: line weight definitions in QSettings; category overrides + color mode in both QSettings and project file
9. Default tab matches active workspace context (model vs paper space)
10. Default color mode: B&W with factory line weight assignments
11. "Set as Default" / "Reset All" scoped to active tab

## 9. Testing Strategy

### 9.1 Unit Tests (~40-50 tests)

**Line weight definitions:**
- CRUD: add, remove, rename, reorder by width
- Validation: reject duplicate names, reject negative/zero width, reject >3.00mm
- Remove guard: can't remove weight in use by a category
- Persistence: round-trip through QSettings
- Factory reset: restores default 5 entries

**Paper-space category overrides:**
- Factory defaults: all 14 categories have expected values
- Color mode transitions: Full Color ↔ B&W ↔ Custom with correct side effects
- Cascade: paper overrides win over model per-instance overrides
- Persistence: round-trip through QSettings and project file JSON
- Backward compat: project without `paper_display` loads factory defaults

**Temporary mutation:**
- Apply/restore cycle: items return to exact original state
- Full Color mode: colours unchanged, only line weight + opacity applied
- BW mode: all colours become black/white
- SVG items: recoloured and restored correctly
- Spatial filter: only items in source rect are mutated

### 9.2 Integration Tests (~10-15 tests)

- Viewport renders with paper-space pen widths (verify QPen width)
- Dirty flag triggers repaint after paper-space settings change
- Display Manager opens to correct tab based on workspace context
- Project save/load preserves paper-space display settings
- "Set as Default" / "Reset All" scoped correctly

### 9.3 No GUI Interaction Tests

Consistent with existing test conventions. Headless Windows Qt testing has known shortcut dispatch issues.
