---
status: shipped          # SB2a built 2026-10-24 (feat/sb2-element-params); SB2b Marks section designed 2026-10-24 (feat/sb2b-marks), not yet built
last-verified: 2026-10-24  # SB2a Account: re-read against the built code (host_values category gate, HostValue sm, host-key enable rule, Room delegates); prior 2026-10-24 forge
verified-commit: a6122a0e   # SB2a Account; prior a8fea641
applies-to:
  - firepro3d/element_params.py        # new (SB2a): registry, ParamSpec, HostValue, category_of
  - firepro3d/block_instance.py        # element_host + host_values() + refresh_bound() seam only (rest under block-system.md)
  - firepro3d/block_attributes.py      # format_value HostValue branch only (schema under block-system.md)
  - firepro3d/block_attributes_editor.py  # host-key dropdown only
  - firepro3d/block_properties_info.py # Host category row only
  # SB2b (designed; applies once built): marks.py (new), renumber_dialog.py (new), settings/panes.py (Marks pane),
  # settings/template.py (carried keys), level_manager.py + level_widget.py (Level.number, level undo),
  # model_space.py (_capture_network / _restore_network levels; paste_items L1410 branches; mint calls),
  # network_codec.py, wall.py, wall_opening.py, room.py, pipe.py, sprinkler.py, gridline.py (Mark storage / panel row),
  # wall_placement_controller.py, feature_placement_controller.py, pipe_network_controller.py,
  # sprinkler_workflow_controller.py (mint sites), property_manager.py (warn row state), main.py (ribbon Renumber)
source-tasks: "SB2a — Element attribute registry (todo_open.md, System Blocks build); grill SB2 Q1–Q19 + SB2a deltas D-a/D-b, design sections 1–4 approved 2026-10-24. SB2b — Marks: grill Q1–Q13 + deltas R1–R6, design sections 1–4 + served mockup approved 2026-10-24 (absorbs todo L1410 paste)"
---

# Element Parameters — Governing Spec

Concept: `docs/superpowers/specs/2026-09-29-system-blocks-concept-design.md` (F2 reading host data, Q6 bindable tiers, display-units rule). This spec owns the **element attribute registry**: which keyed values each element category exposes to host-bound blocks, how they are read, and how they reach `@[key]` text. Marks (SB2b) and custom Feature attributes (SB2c) extend it in place.

## Goal

A block whose definition names a **host category** can bind each host-sourced attribute to a **host key** of that category, and a placed instance with a host shows that host's live value in project display units.

## Motivation

Tags and intrinsic labels (SB3–SB6) must read element data without parsing the property panel, whose labels and pre-formatted strings (`1"Ø`) are unstable and unit-baked (concept F2, rejected option).

## Architecture & Constraints

- **One module, pure getters** (approach 1, ratified): `element_params.py` holds every category's key table. Element classes are not edited to declare keys; getters read their real fields.
- `ParamSpec(key, label, kind, tier, getter)`; `PARAMS: dict[category, dict[key, ParamSpec]]` in tier order; `CATEGORIES` in Q2 order: Room, Pipe, Sprinkler, Wall, Door, Window, Opening, Gridline.
- `category_of(item) -> str | None`: an `isinstance` table; `WallOpening` (the one class behind the `DoorOpening` / `WindowOpening` aliases) splits by `_type` `door` / `window` / `blank` → Door / Window / Opening. Any other item → `None`. No candidate class subclasses another (1b probe), so table order is not load-bearing today; new subclasses go before their base.
- Getters return a **raw value in canonical units** or `None`: lengths mm, area mm², volume mm³, pressure psi, flow gpm, velocity ft/s, pipe inner diameter in, angle degrees, text str. Scene-px quantities convert through the scene `ScaleManager.pixels_per_mm` (area by its square). A getter that raises or meets missing data (no scene, unknown level, no host wall, no result) yields `None`.
- `host_values(item) -> dict[key, HostValue]` for the item's category; `HostValue(raw, kind, sm)` (`sm` = the item's scene `ScaleManager`, optional) exposes `text` (the kind formatter's string in project units) and `number` (the same quantity as a bare float in display units, or `None` for text kinds).
- **Formatting** goes by kind through `ScaleManager` (Rule A: the kinds, spellings and imperial-only status of pressure / flow / velocity are owned by `units-and-formatting.md`). SB2a adds `format_area_mm2`, `format_volume_mm3`, `format_pressure`, `format_flow`, `format_velocity`, `format_bearing` (+ `*_value` numeric twins); Room's `_fmt_area` / `_fmt_volume` stay as thin delegates to the two area / volume formatters (no copy of the formatting). `format_length` is reused; the `angle` kind prints through `ScaleManager.format_bearing` (0..360, so a straight-down gridline reads 270°) and its `.number` is the same wrapped value; other app angles keep `format_angle`.
- **Attribute resolution** (schema owned by `block-system.md`, SB1a): `block_attributes.format_value` gains one branch — given a `HostValue`, a `text` attribute prints `.text`, a `number` attribute prints `.number` at the attribute's `precision`; prefix / suffix wrap either; `None` → placeholder. The SB1a override rule is unchanged (a present instance value wins, printed as typed).
- **Host seam** on `BlockInstance`: `element_host` (code-set only in SB2a — D-a; not serialized; distinct from the gridline-hosting `host` record); `host_values()` returns `element_params.host_values(element_host)` when a live host is set (`element_params.is_live`, which reaches a sprinkler's scene through its node) **and** the definition's `host_category` is a known category that equals `category_of(element_host)`; otherwise `None` (a host of another category, or an unknown category, resolves to placeholders). `refresh_bound()` re-resolves the bound strings and, only when they change, calls `prepareGeometryChange()` + `update()` (closes the SB1a "host-value change re-shapes without prepareGeometryChange" follow-up for this path).
- **Refresh triggers:** `Model_Space._refresh_all_labels` (the unit / precision change path, called by `main.py` after Project Settings) calls `refresh_bound()` on every instance with an `element_host`; the property-panel commit for an element calls it on that element's bound instances via `scene.instances_bound_to(item)`. Grip / move edits of a host are not wired in SB2a (SB3).

## Design Decisions

| # | Decision | Ratified by |
|---|---|---|
| E1 | Categories = Room, Pipe, Sprinkler, Wall, Door, Window, Opening (3 categories over `WallOpening`), Gridline | grill Q2/Q4 |
| E2 | Built-in set = the element's keyed data (stored / geometry / hydraulic / related), not panel rows; display styling (Colour, Line Type…) is never a key | grill Q14–Q16 |
| E3 | Keys PascalCase; related keys dotted (`Level.Name`); labels in the table below | design §1 |
| E4 | Mark and Level.Number are listed now and return `None` until SB2b, except Room Mark (= today's Room Tag) and Gridline Mark (= its Label, Q3); SB2b replaces the `None` getters with the stored Mark / `Level.number` (§ Marks) | delta D-b, grill Q3/Q6; SB2b |
| E5 | Host link is a code seam only in SB2a; no in-app bind command; placed blocks show placeholders until SB3 / SB6 set hosts | delta D-a |
| E6 | Door / Window / Opening Room = the room containing a point just past the wall face on the swing / facing side, else the other side, else `None` | design §1 |
| E7 | T3 reads `scene.hydraulic_result` as the pipe-label overlay does: `None` before a solve or for an element the solve did not reach; stale after an edit until cleared or re-run | design §4 |
| E8 | `HostValue` text / number split: a text attribute shows the unit-formatted string, a number attribute the bare display-unit number at its own precision | design §2 |
| E9 | Unknown `host_category` or `host_key` from a file is kept, shown as a warn entry in the editor, saved back unchanged, and resolves to the placeholder; the block always loads | grill Q17, design §3 |
| E10 | Picker warn colour = the theme `warn` token (UI chrome); `#ff8800` stays for drawing-side duplicate flags (Q9) | design §3 |

### Key table (design §1)

Tiers: T1 stored, T2 geometry, T3 hydraulic, T4 related. `[label]` given where it differs from the key.

| Category | T1 | T2 | T3 | T4 |
|---|---|---|---|---|
| Room | Name, Mark, HazardClass [Hazard class], Occupancy, SystemType [System type], CeilingType [Ceiling type] | Area (mm²), Perimeter (mm), CeilingHeight [Ceiling height] (mm), Volume (Area × CeilingHeight, mm³) | — | Level.Name, Level.Number |
| Wall | Name, Mark, Thickness (mm) | Length (centreline, mm), Height (computed, mm) | — | Level.Name, Level.Number |
| Door / Window / Opening | Mark, Family, Type (Feature type name, `FeatureDef.type_name`), Width, Height, Sill (mm) | — | — | Wall.Mark, Wall.Name, Room.Name, Room.Mark, Level.Name, Level.Number |
| Pipe | Mark, Diameter (nominal, the existing `Ø 1"` / `Ø 25 mm` display strings), Schedule, Material, CFactor [C-factor] | Length (true 3D, mm), InnerDiameter [Inner diameter] (in) | Flow (gpm), Velocity (ft/s), FrictionLoss [Friction loss] (psi) | Level.Name, Level.Number |
| Sprinkler | Mark, Manufacturer, Model, Orientation, KFactor [K-factor], Temperature, MinPressure [Min pressure] (psi), CoverageArea [Coverage area] (sq ft) | Elevation (node z, mm) | Pressure (psi at its node), Flow (K√P, gpm), NodeNumber [Node number] (solver label) | Room.Name, Room.Mark (via the node's room link), Level.Name, Level.Number |
| Gridline | Mark (= Label) | Length (mm), Angle (0–360°) | — | — (no level) |

### Block Editor pickers (design §3)

- **Host category** = the panel `enum` row: `(none)` + `CATEGORIES`; an unknown file value appears as an extra `⚠ <name> — unknown category` entry. Changing it never rewrites host keys.
- **Host key** (Attributes editor column) = a dropdown like the type / source columns: non-selectable tier headers, items `Label (Key)`, an unknown key kept as `⚠ <key> — unknown key`. Enabled only when source = host and the block's category is a known one; disabled for source = instance, category `(none)` or an unknown category (an existing value is still stored).

## Acceptance Criteria

1. `PARAMS` holds exactly the key table above for the 8 categories, each with label, kind, tier and a getter returning the canonical raw value or `None`.
2. `category_of` returns the right category for every class, including each `WallOpening` kind, and `None` for anything else.
3. Values render in project display units by kind; a unit switch re-formats bound text through `_refresh_all_labels`.
4. A block bound to a category resolves `@[key]` from a real host through `host_values()`; a host property edit updates the text with `prepareGeometryChange`.
5. The Block Editor shows the Host category dropdown and per-attribute host-key dropdowns grouped by tier; unknown category / key are kept, shown in the warn colour, and the block loads.

## Edge Cases & Error Handling

- Getter failure or missing data → `None` → placeholder; one bad element never breaks paint.
- Deleted host (`element_params.is_live` false, which reaches a sprinkler's scene through its node) → treated as no host → placeholders.
- Uncalibrated scene → `pixels_per_mm` default 1.0 (1 px = 1 mm), as everywhere else.

## Verification Checklist

- **G1** real Room, Wall, Door, Pipe (+ nodes), Sprinkler, Gridline through real constructors on a scene: every key's raw value against a hand-derived one (a 4 m × 3 m room → Area 12e6 mm²; door Width 914 mm), a calibrated scene (ppm 2), and a unit switch (imperial ↔ m) changing `HostValue.text`.
- **G-B1** a block bound to `Door` with `@[W]`→`Width`, `@[R]`→`Room.Name`, `.element_host` = a real door in a real room: painted bound text = the formatted values; a width edit committed through the property panel (`property_manager` dispatch) updates the text and `boundingRect`; a unit switch + `_refresh_all_labels` reflows it.
- **G-B2** each category's host-key items = its `PARAMS` keys in tier groups; a loaded block with `KFactor` on `Door` and a category `Foo` keeps both through OK, shows the warn entries, and loads.
- Unit: `category_of` over every category and an unrelated item.
- Smoke: Block Editor Host category row + host-key dropdowns.

## Marks (SB2b)

Status: designed, not built. Ratified by the SB2 grill Q1–Q13 (todo_open.md SB2b line), the SB2b Phase 2 deltas R1–R6, the Phase 3 approaches A1–A4, design sections 1–4 and the served UI mockup (`D:/Custom Code/FPD Design/sb2b-marks/index.html`, approved 2026-10-24; the look of every SB2b surface is that page's).

### Goal

Every element of the seven element categories carries an instance **Mark** for tags, schedules and stable references: auto-assigned from a per-category project pattern when the element is created, kept through edits, editable in the panel, flagged when duplicated, and renumbered on demand. Levels gain an editable **Number** that patterns can print. Level-manager edits become undoable. Paste-family commands copy walls, rooms, floors and roofs (todo L1410, absorbed).

### Architecture & Constraints

- **Storage.** `_mark: str` on `WallSegment`, `WallOpening`, `Room`; a `"Mark"` entry in `_properties` on `Pipe` and `Sprinkler` (network_codec persists only `_properties` keys and `set_property` drops unknown ones). Gridline Mark **is** its Label (`grid_label`, Q3) — no second field. Serialized key `mark` (Wall, WallOpening, Room); Room still reads the legacy `tag` key when `mark` is absent and writes `mark` only. `Room._tag` is retired in favour of `_mark`; its readers (room label, model browser tooltip, sprinkler-workflow room fallback, the Room / Opening / Sprinkler `Room.Mark` getters) move to it. Undo (`_capture_network` / `_restore_network`) uses the same `to_dict` / `from_dict` / codec functions, so Marks ride undo with no extra code.
- **`marks.py`** (new, pure where possible): pattern parse / format, next-number scan, duplicate detection, reading-order sort, `mint(scene, item)`, `renumber(scene, category, scope, options) -> {item: new_mark}`.
- **Patterns.** One per category, stored in the project (`.fpd`, a `mark_patterns` dict) and carried by *Save current as default* (`settings/template.py` carried keys + blank payload + loader). Tokens: `{n}` the counter; `{n:0W}` the counter zero-padded to at least W digits (never truncated); `{level}` the element's `Level.number` (Gridline: no `{level}`, it has no level); every other character literal. Defaults (Q4, Room changed by the user 2026-10-24): Door `D{n}`, Window `W{n}`, Opening `O{n}`, Wall `WL{n}`, Pipe `P{n}`, Sprinkler `S{n}`, Room `{level}{n:02}`.
- **Next number (Q5).** For an element, resolve the pattern's `{level}` to that element's level number, then next = (highest `n` among the category's Marks that match that resolved pattern) + 1, or 1 when none match. Gaps are never refilled except by Renumber. A blank pattern mints a blank Mark.
- **Mint seam (A1).** No single creation choke point exists, so `marks.mint(scene, item)` is called explicitly at every creation site: the wall chain and wall rectangle (`wall_placement_controller`), opening placement (`feature_placement_controller`), both room paths (`_press_room`, `_press_room_manual`; Room **Name** stays `Room N`), `PipeNetworkController.add_pipe`, sprinkler placement and auto-populate (`sprinkler_workflow_controller`), and every `paste_items` branch (Paste, Duplicate, Array, Copy-to-level, Duplicate-level). File load, undo / redo, move, rotate, mirror and stretch never call it.
- **Pipe split (R1).** `split_pipe` / `_split_vertical_pipe` delete the original and create two pipes: the half touching the original's start node (n1) receives the original Mark; the n2-side half mints.
- **Paste coverage (R2, todo L1410).** `paste_items` gains branches for walls (with their nested openings), rooms, floors and roofs: new uid, new Mark per Mark-bearing element. A design area is pasted only when every sprinkler it references is in the same paste (its record refers to member nodes by id); otherwise it is skipped and the footer says so.
- **Panel.** Each category's panel gets a `Mark` row (Room: replaces `Room Tag`; Gridline keeps its `Label` row). A panel edit that clears the Mark is refused: the value reverts and a status message shows on the main window status bar (R5). Blank Marks from old files (Q6) or a blank pattern stay blank and can be typed later.
- **Duplicates (Q9, Q10, R6).** A duplicate = two or more elements of one category with the same non-blank Mark, project-wide, exact match. Detection generalizes gridline `check_duplicate_labels` and re-runs after every Mark change (panel commit, mint, paste, Renumber, undo / redo, load). The panel Mark row shows the theme `warn` token (dynamic property + repolish) and a tooltip `N <category plural> share Mark <m>`; gridlines keep their `#ff8800` bubble. Screen-only: nothing is flagged on paper or in PDF.
- **Renumber (Q11, Q12, R3, A4).** Ribbon Manage › Settings, a `Renumber` large button after `Project Settings` → house dialog: Category (the seven + Gridline); Scope = whole project / selected elements / one level; the pattern read-only; *Restart on each level* (enabled only when the pattern holds `{level}`, and then ticked by default so Renumber agrees with per-level minting); *Keep current order, just close gaps*; a live Level | Old | New preview with per-level order thumbnails and `N elements, M change`; OK applies as **one undo step**. Order: level by level, lowest elevation first; within a level reading order on the element's sort point (wall / pipe midpoint, opening insertion point, room centroid, sprinkler node) — rows top → bottom (largest model y first; same row when within 600 mm of the row's first element), then left → right. *Keep current order* sorts by the existing Mark number. Out-of-scope elements keep their Marks and the renumbered set starts above the highest out-of-scope number of the resolved pattern; whole-project scope starts at 1; *Restart on each level* restarts at 1 per level. Gridline: pattern and restart disabled; verticals 1, 2, 3 left → right, horizontals A, B, C bottom → top (the `auto_label` orientation rule). Renumber never edits patterns.
- **Patterns UI (A3).** Project Settings gains a third rail row **Marks** (after Project Info, Units & Precision): table Category | Pattern (editable) | Next (read-only, recomputed per keystroke through a delegate on `textEdited`); token hint line; a blank pattern previews `(blank)`. Project Settings stays OK / Cancel and off the undo path (pattern edits never rewrite Marks).
- **Level Number (Q13).** `Level.number: int`, saved with the level; the Level manager dock gains an editable Number column (Name stretch, Number / Elevation resize-to-contents). A new level gets its position by elevation (lowest = 1); an old file assigns numbers by elevation order on open; a stored number never shifts when levels are added; duplicate numbers are allowed and not flagged. `{level}` and the `Level.Number` key print it.
- **Level undo (R4, A2).** The level list (with numbers), each underlay record's `levels`, the plan views and the active level enter the undo snapshot. Every Level-manager edit — add, delete, duplicate, rename, elevation, Number — pushes one undo step. Restore re-applies them, recomputes elevations (`update_elevations`) and refreshes the Level manager, view tabs and level combo.

### Design Decisions

| # | Decision | Ratified by |
|---|---|---|
| M1 | Marks serve tags, schedules and stable IDs; Renumber is manual only | grill Q1 |
| M2 | Gridline Label is its Mark; row stays "Label"; orange bubble unchanged | grill Q3 |
| M3 | Default patterns as listed; Room `{level}{n:02}` | grill Q4; Room changed by the user 2026-10-24 (because: the 101 / 401 room-numbering convention) |
| M4 | A pattern edit never rewrites Marks; next = highest matching the current resolved pattern + 1 | grill Q5 |
| M5 | Room Tag → Mark (value carries; old blank rooms stay blank; new rooms mint) | grill Q6 |
| M6 | Room label until SB3 = Name | grill Q7 |
| M7 | Mint on create / paste family; keep on edit / undo / load; delete never reuses; blank pattern → blank | grill Q8 |
| M8 | Pipe split: n1-side half keeps, n2-side half mints | R1 |
| M9 | L1410 paste coverage absorbed into SB2b (logged phase-drift) | R2 (because: copies must mint, and copies of walls / rooms did not exist) |
| M10 | Duplicate flag: panel row warn token + count tooltip; screen-only | grill Q9; R6 (E10 keeps UI chrome on theme tokens) |
| M11 | Uniqueness per category, whole project | grill Q10 |
| M12 | Renumber order, scope, options and one undo step as above | grill Q11 / Q12; section 2 |
| M13 | Gridline is a Renumber category, orientation rule | R3 |
| M14 | Level Number stored, editable, default by elevation, never shifts | grill Q13; section 3 |
| M15 | All Level-manager edits undoable via the snapshot (because a partial set would let an unrelated undo delete a level) | R4, A2 |
| M16 | Mark is free text; a panel edit to blank is refused; other blanks stay | R5 (+ Phase 3 reconcile) |
| M17 | Explicit per-site mint helper | A1 |
| M18 | Patterns UI = Project Settings Marks rail row; Next per keystroke | A3, mockup |
| M19 | Renumber dialog layout = the served mockup | A4, mockup |

Out of scope (no code path today; rules recorded for when one appears): a Door ↔ Window swap on a placed opening re-mints in the new category (Q8); a wall split keeps the Mark on the first part (Q8).

### Acceptance Criteria

1. Marks, patterns and Level Numbers survive `.fpd` save / load and undo / redo; an old file's Room `tag` opens as its Mark.
2. Each creation site mints the next Mark for its category; edits, undo and load keep Marks; a pipe split hands the n1 half the old Mark; a blank pattern mints blank.
3. Paste / Duplicate / Array / Copy-to-level create walls (+ openings), rooms, floors and roofs, each Mark-bearing copy with a new Mark; a design area without all its sprinklers is skipped with a footer note.
4. Duplicate Marks flag the panel row (warn token, count tooltip) and clear when resolved; nothing shows on paper / PDF.
5. Renumber produces reading-order Marks per the rules above, leaves out-of-scope Marks untouched, and one undo restores every Mark.
6. A pattern edit changes no existing Mark; the next element follows the new pattern.
7. Every Level-manager edit is one undo step and undo restores item levels, underlay levels, plan views and the active level.
8. Clearing a Mark in the panel reverts it with a status message.
9. Every SB2b UI surface matches the approved mockup.

### Verification Checklist

- **G2** round-trip: real Door, Wall, Room, Pipe, Sprinkler, Gridline + patterns + Level Numbers through `.fpd` save / load and undo / redo; old-file `tag`.
- **G-M1** mint through each real tool (wall chain + rect, door, both room paths, drawn pipe, placed + auto-populated sprinkler) and each paste-family command; pipe split by dropping a sprinkler on it; blank pattern.
- **G-P1** L1410: repro first; then Paste / Duplicate of a wall with a door, a room, a floor, a roof, a design area with and without its sprinklers.
- **G-M2** duplicate flag via the property panel; cleared when fixed; absent from a PDF export.
- **G-M3** Renumber on doors over two levels, each scope / option; out-of-scope untouched; one undo; Gridline orientation rule.
- **G-M4** pattern edit (`DR-{n:02}`): existing Marks unchanged; the next door follows it.
- **G-L1** level rename / elevation / Number / add / delete / duplicate, each undone and redone.
- Blank-revert through the panel. Smoke: every surface against the mockup.

## Divergences ledger

| # | Divergence | Disposition |
|---|---|---|
| D1 | Room's own area / perimeter (`room.py` shoelace) treats scene px as mm, ignoring `pixels_per_mm`; the registry applies calibration | follow-up (pre-existing); filed as todo 'Room panel area / perimeter ignore pixels_per_mm' |
| D2 | Host-bound text does not refresh on grip / move edits of the host, nor on undo / redo of a host edit or deleting a host (none fires `refresh_bound`); the text and bounds re-resolve at the next paint or trigger | SB3 / SB6 wire the explicit triggers with real hosts; +1 filed on SB6 |
| D3 | `BlockInstance.host` is not serialized | SB3 / SB6; +1 filed on SB6 |
| D4 | Pressure / flow / velocity have no metric variant | owned by `units-and-formatting.md` D2 |
