---
status: current          # code-verified as-built behavior; divergences ledger at end
last-verified: 2026-07-16
verified-commit: 778786d
applies-to:
  - firepro3d/property_manager.py
  - firepro3d/dimension_edit.py
source-tasks: "TODO.md §B follow-up: property-panel editing for sheet text (orphan-gate spec forged on first touch)"
---

# Property Panel — Governing Spec

**Date forged:** 2026-07-08 (Phase 1b orphan gate — reverse-engineered from as-built code)
**Adjacent docs:** `architecture/entities.md` §"Property system" (entity-side protocol overview — ripple map), `specs/sprinkler-system-components.md` (sprinkler cascade data), `specs/paper-space.md` §9 (sheet text, pending panel integration)

## 1. Goal

One right-side dock panel (`PropertyManager`) is the single place the user inspects and edits properties of whatever is currently selected — model entities, multi-selections, pre-placement **templates**, or view-level info objects — without modal dialogs.

## 2. Motivation

Modal property dialogs interrupt CAD flow. The panel gives Revit-style always-visible editing: click an item, edit a field, see the change live. The same panel doubles as the **pre-placement template editor** — entering a placement mode shows the prototype's properties so defaults are set *before* the first click.

## 3. Architecture & Constraints

### 3.1 The duck-typed property protocol

The panel renders anything exposing:

- `get_properties() -> dict[str, meta]` — ordered dict; `meta` keys: `type`, `value`, plus type-specific extras (`options`, `callback`, `value_mm`, `suffix`, `readonly`).
- `set_property(key, value)` — write-back; the *entity* owns coercion/side-effects.

The panel never imports entity modules for rendering decisions except the special cases in §3.4. Objects without `get_properties` render nothing (empty panel, no error).

### 3.2 Widget-per-type registry (as-built: if/elif chain)

| `type` | Widget | Commit trigger |
|---|---|---|
| `header` | section-divider `QLabel` (`── {key} ──`, bold secondary text) — no editor, no `value` key needed | — |
| `label` | read-only `QLabel` (sunken style) | — |
| `warning` | full-width amber header (`⚠ {key}`) + word-wrapped bullet body (`QLabel`, `Expanding` + `setMinimumWidth(1)` so long words don't force a wider dock minimum) | — |
| `string` (+ fallback) | `QLineEdit`; auto-attaches `QDoubleValidator` when current value parses as float | `editingFinished` |
| `enum` / `combo` | `QComboBox` from `options` | `currentTextChanged` |
| `color` | 60×24 swatch `QPushButton` → `QColorDialog` (`_pick_color`; stores hex in `_color_value` property; cancel-guarded) | dialog OK |
| `level_ref` | `QComboBox` populated from `LevelManager.levels` | `currentTextChanged` |
| `dimension` | `DimensionEdit` seeded from `meta["value_mm"]`; optional meta keys `parser`, `minimum`, `formatter` pass through (§3.8) | `editingFinished` → `value_mm()` |
| `bool` | `_MixedStateCheckBox` — Word-like tristate: `PartiallyChecked` is display-only for mixed multi-select; `nextCheckState` resolves partial → checked and clicks never cycle back into partial. Commits on **`clicked`**, not `toggled` (Qt's partial state reports `isChecked()` True, so the partial→checked click never fires `toggled`). Theme styles `::indicator:indeterminate` (accent fill) — without it the QSS renders partial identically to unchecked. | `clicked` → `isChecked()` |
| `font` | `QFontComboBox` (seeded via `setCurrentFont` when value truthy) | `currentFontChanged` → `family()` |
| `button` | `QPushButton` labelled `value`; fires `meta["callback"]` (exceptions swallowed), then debounced refresh | click |

`meta["readonly"]` disables/greys the widget. `meta["suffix"]` wraps the widget in an HBox with a grey italic suffix label.

**Width containment (rendering constraints, 2026-07-14):** every `QComboBox` variant (enum/combo/level_ref/font/legacy Level) gets `setMinimumContentsLength(8)` so long option strings can't force the form wider than the dock (the panel clips — `ScrollBarAlwaysOff`); `button` uses an **`Ignored`** horizontal size policy + a tooltip carrying the full face text, so long button faces (e.g. Design Point) shrink instead of widening the form.

### 3.3 Write path & refresh loop

`_apply_property(key, value)` → `set_property` on **every** target (multi-select), sprinkler cascade re-run when key ∈ {Manufacturer, Model, Orientation}, then `scene.sceneModified.emit()` (first target with a scene) and a **50 ms single-shot debounced refresh** (`_refresh_timer` → `_do_refresh` → full form rebuild). A `_refreshing` guard makes writes fired during rebuild no-ops (prevents re-entrant loops from `currentTextChanged` firing on `setCurrentText`).

**Write-path contract (grilled 2026-07-08; paper route built 2026-07-09):** direct mutation is **provisional**, not the long-term contract. The pluggable write route is now as-built for paper: `TextAnnotationItem.set_property` pushes commands on its scene's `QUndoStack` (`paper-space.md` §9.6/§17), and `_apply_property` wraps **multi-target** commits in a `beginMacro`/`endMacro` pair (duck-typed on a public `undo_stack` attribute — `Model_View` has none, so model space is unaffected; one panel commit = one undo step). Model-space targets stay direct-mutation **until model-space undo exists**, at which point they migrate to the same route. New target families must not add bare `set_property` writes without considering undo ownership.

### 3.4 Hard-coded entity special cases

The generic protocol has four baked-in exceptions (all in `_show_properties_inner`). **Grilled 2026-07-08: the *behaviors* are UX contract (users rely on them); their *location* inside the panel is tolerated debt — migrate into entity `get_properties()` only with cause.**

1. **Node→Sprinkler resolution:** a selected `Node` with `has_sprinkler()` shows the *sprinkler's* properties instead.
2. **Sprinkler DB cascade:** `_cascade_sprinkler_props` filters Model/Orientation options from the lazy singleton `SprinklerDatabase` and auto-fills read-only K-Factor / Coverage / Min Pressure / Temperature when exactly one record matches.
3. **Pipe node sections:** a `Pipe` appends "── Node 1/2 ──" header rows rendering each node's properties inline (level_ref/label/string only), plus a read-only "Absolute Elev." row.
4. **Legacy Level row:** items with a `.level` attribute but no `level_ref` property get a synthesized Level combo (`_change_level`), which also re-derives node `z_pos` from level elevation + ceiling offset and calls `level_manager.apply_to_scene`. **Suppressed (2026-07-14) when the entity's property dict already contains a `"Level"` key** — e.g. `DesignArea` exposes a read-only Level *label*; a second editable combo would be a duplicate lie.

### 3.5 Multi-select semantics

`show_properties(list)` — the **first** target's property dict defines the form; per-key values are compared across targets and differing ones render as `< mixed >` (cleared QLineEdit placeholder / injected combo item 0). Any commit applies to all targets (§3.3); targets lacking the key absorb the write via their own `set_property`. **Grilled 2026-07-08: this is the intended contract** (not a placeholder for intersection-of-keys semantics).

### 3.6 Selection sources (wiring lives in `main.py`)

- `scene.selectionChanged` → `MainWindow.update_property_manager()` → `show_properties(selectedItems())`; **placement modes are excluded** (`pipe`, `sprinkler`, `wall*`, `floor*`, `roof*`, `set_scale`, `design_area`) so template props aren't clobbered mid-placement.
- `scene.requestPropertyUpdate`, `view_3d.entitySelected`, `model_browser.entitySelected` → `show_properties` directly.
- Empty selection → `show_properties(PlanViewInfo)` (active plan/detail view info) — the panel is never "about nothing" on a plan tab.
- Elevation scenes: `scene.entitySelected` → `show_properties` (per-scene connect on creation).
- **Paper space (built 2026-07-09):** `paper_scene.selectionChanged` + `undo_stack.indexChanged` → `MainWindow.update_paper_property_manager()` — filters selection to `TextAnnotationItem`s, only acts while the paper tab is current; `_on_tab_changed` routes the panel to the active tab's context. `add_text_mode_toggled` shows the text template pre-placement. Viewports still use their dialog (follow-up).

### 3.7 Template pattern (pre-placement defaults / "last-used defaults")

A **template** is a real entity instance living *outside* any scene, shown in the panel when its placement mode activates:

- **Pipe/Sprinkler:** `MainWindow.current_pipe_template` / `current_sprinkler_template` (constructed at startup with null endpoints); `_scene_ref` set so `_get_scale_manager` resolves units. Placement copies values via `entity.set_properties(template)`. **Persisted across sessions** in `QSettings` (`template/pipe`, `template/sprinkler`) as raw `{key: value}` — saved in `save_settings`, restored after project load.
- **Sheet text (built 2026-07-09):** `MainWindow.current_text_template` — an off-scene `TextAnnotationItem` (`_scale_manager_ref` set; `set_property` writes directly, no undo). Its data object is aliased to `PaperScene.text_template`, which seeds `begin_place_text`. Persisted in `QSettings` (`template/text`) via `paper_space.text_template_to_settings`/`apply_template_settings` (explicit string coercion — the Windows registry backend stringifies — and non-positive-height fallback).
- **Wall/Floor/Roof/Geometry:** lazily-created scene-owned templates (`Model_View._get_*_template`, name `"(Template)"`), synced to the active level on each fetch; shown via `_on_mode_changed_template`. **Not persisted.**
- **Persistence policy (grilled 2026-07-08):** the persisted/non-persisted asymmetry is historical, not designed. *New* template families (e.g. sheet text) follow the **persisted** pattern from day one; retrofitting wall/floor/roof/geometry persistence is a separate low-priority follow-up. QSettings is the current store; a future per-user accounts feature may replace it — keep template persistence behind the existing save/restore helpers so the store can swap.
- ScaleManager resolution order for off-scene targets: `scene().scale_manager` → `_scale_manager_ref` → `_scene_ref.scale_manager` (`_get_scale_manager`).

### 3.8 `DimensionEdit` contract (`dimension_edit.py`)

`QLineEdit` storing **mm** internally; displays via `ScaleManager.format_length`; parses via `ScaleManager.parse_dimension(text, fallback=sm.bare_number_unit())`; empty/invalid input **reverts** to last valid value; `valueChanged(float mm)` on successful commit; select-all on focus. Per project convention (CLAUDE.md / memory), *all* dimension fields use this pattern — never `QDoubleSpinBox`.

**Optional overrides (added 2026-07-09, resolving D4):** `parser` (callable `str -> float|None`, replaces the whole parse path incl. fallback unit), `minimum` (accepted values must be strictly greater — non-positive rejection for text heights), `formatter` (callable `mm -> str`, replaces the display path — e.g. the sheet-text Word-style `"12 pt"` rendering). **Seed guard (always on):** an untouched or blank commit keeps the *exact* stored mm — re-parsing the displayed text would re-quantize it at display precision (imperial 3/16"→1/4" at 1/8" resolution).

**Table cells — `DimensionDelegate` (added 2026-07-16):** the same contract inside `QTableWidget`/item views. A `QStyledItemDelegate` whose editor is a `DimensionEdit`; on commit it writes the mm value to a configurable `value_role` (default `UserRole`) and the `format_length` string to `DisplayRole`. Consumers: level table elevation column (`level_widget.py`, role `UserRole`), gridlines dialog Offset/Spacing/Length columns (`grid_lines_dialog.py`, role `UserRole+1` = numeric sort key). **Tab-commit rule:** Qt calls `setModelData` *before* the editor's `editingFinished` fires on Tab-to-next-cell, so the delegate must call `DimensionEdit.commit()` (public force-parse) before reading `value_mm()` — reading without it silently reverts Tab-committed values. Any new dimension column uses this delegate; never a bespoke cell-commit path.

## 4. Design Decisions (as-built rationale)

- **Full form rebuild on refresh** (no per-widget diffing): simple, correct for ≤ a few dozen rows; acceptable because rebuilds are debounced (50 ms) and forms are small.
- **First-target-defines-form** multi-select: avoids computing a property-dict intersection; heterogeneous selections show the first item's keys (writes to targets lacking the key are silently absorbed by their `set_property`).
- **Panel emits `sceneModified`, not per-entity signals:** one coarse signal drives 3D rebuild + dirty flag; fine-grained reactivity is the entity's job via `set_property` side-effects.
- **Templates are live entity instances, not dicts:** placement copies from a fully-coerced entity, so template editing exercises the exact same `set_property` validation as post-placement editing.

## 5. Acceptance Criteria (for changes to this subsystem)

- [ ] Any new property `type` is added to the §3.2 table and renders in both light/dark themes.
- [ ] Writes still route through `_apply_property` (or a documented undo-aware variant — see Divergences D3).
- [ ] Multi-select `< mixed >` behavior preserved for the affected types.
- [ ] Template flows (§3.7) still show pre-placement and survive a QSettings round-trip where persisted.
- [ ] No regressions in the four special cases (§3.4).

## 6. Verification Checklist

- [ ] Manual: select node / pipe / sprinkler / wall / multi-select — form renders, edits apply, mixed indicator correct.
- [ ] Manual: enter pipe placement mode — template shows; place pipe — values copied.
- [ ] Unit restart round-trip: template values persist via QSettings.
- [ ] `sceneModified` fires exactly once per commit (no refresh-loop storms).

## 7. Divergences Ledger (as-built vs intended)

| # | Divergence | Status |
|---|---|---|
| D0 | **Wall/floor/roof/geometry templates don't persist** across sessions (historical asymmetry, §3.7). | Gap; low-priority follow-up to retrofit. |
| D1 | **Zero test coverage** — no test file references `PropertyManager` or `DimensionEdit`. | Gap; add coverage opportunistically when touching the panel. |
| D2 | ~~No paper-space wiring~~ | **Resolved 2026-07-09** — §3.6 paper wiring built; the dialog is deleted. Viewports remain dialog-based (follow-up filed in TODO.md). |
| D3 | ~~Direct-mutation write path vs paper-space undo invariant~~ | **Resolved 2026-07-09** — §3.3 pluggable write route as-built for paper (commands + multi-select macro); model space stays direct until model undo exists. |
| D4 | ~~`DimensionEdit` fallback unit not overridable~~ | **Resolved 2026-07-09** — §3.8 `parser`/`minimum`/`formatter` overrides + seed guard. |
| D5 | **`combo` is a duplicated `enum` branch** (verbatim copy), and the widget registry is a long if/elif rather than a dispatch table. | Cosmetic; refactor only with cause. |
| D6 | **`_change_level` reaches into node internals** (`node._properties["Ceiling Level"]["value"] = …`) instead of `set_property`. | Latent inconsistency; leave unless touched. |
| D7 | `_on_button_callback` swallows all exceptions silently. | Debugging hazard; leave unless touched. |
