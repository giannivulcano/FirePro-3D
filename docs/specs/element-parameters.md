---
status: proposal          # SB2a designed 2026-10-24, unbuilt
last-verified: 2026-10-24
verified-commit: a8fea641
applies-to:
  - firepro3d/element_params.py        # new (SB2a): registry, ParamSpec, HostValue, category_of
  - firepro3d/block_instance.py        # host + host_values() + refresh_bound() seam only (rest under block-system.md)
  - firepro3d/block_attributes.py      # format_value HostValue branch only (schema under block-system.md)
  - firepro3d/block_attributes_editor.py  # host-key dropdown only
  - firepro3d/block_properties_info.py # Host category row only
source-tasks: "SB2a — Element attribute registry (todo_open.md, System Blocks build); grill SB2 Q1–Q19 + SB2a deltas D-a/D-b, design sections 1–4 approved 2026-10-24"
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
- `host_values(item) -> dict[key, HostValue]` for the item's category; `HostValue(raw, kind)` exposes `text` (the kind formatter's string in project units) and `number` (the same quantity as a bare float in display units, or `None` for text kinds).
- **Formatting** goes by kind through `ScaleManager` (Rule A: the kinds, spellings and imperial-only status of pressure / flow / velocity are owned by `units-and-formatting.md`). SB2a adds `format_area_mm2`, `format_volume_mm3`, `format_pressure`, `format_flow`, `format_velocity` (+ `*_value` numeric twins); Room's `_fmt_area` / `_fmt_volume` move onto them (no copy). `format_length` and `format_angle` are reused.
- **Attribute resolution** (schema owned by `block-system.md`, SB1a): `block_attributes.format_value` gains one branch — given a `HostValue`, a `text` attribute prints `.text`, a `number` attribute prints `.number` at the attribute's `precision`; prefix / suffix wrap either; `None` → placeholder. The SB1a override rule is unchanged (a present instance value wins, printed as typed).
- **Host seam** on `BlockInstance`: `host` (code-set only in SB2a — D-a; not serialized); `host_values()` returns `element_params.host_values(host)` when a live host is set (`host.scene() is not None`), else `None`. `refresh_bound()` re-resolves the bound strings and, only when they change, calls `prepareGeometryChange()` + `update()` (closes the SB1a "host-value change re-shapes without prepareGeometryChange" follow-up for this path).
- **Refresh triggers:** `Model_Space._refresh_all_labels` (the unit / precision change path, called by `main.py` after Project Settings) calls `refresh_bound()` on every instance with a host; the property-panel commit for an element calls it on that element's bound instances via `scene.instances_bound_to(item)`. Grip / move edits of a host are not wired in SB2a (SB3).

## Design Decisions

| # | Decision | Ratified by |
|---|---|---|
| E1 | Categories = Room, Pipe, Sprinkler, Wall, Door, Window, Opening (3 categories over `WallOpening`), Gridline | grill Q2/Q4 |
| E2 | Built-in set = the element's keyed data (stored / geometry / hydraulic / related), not panel rows; display styling (Colour, Line Type…) is never a key | grill Q14–Q16 |
| E3 | Keys PascalCase; related keys dotted (`Level.Name`); labels in the table below | design §1 |
| E4 | Mark and Level.Number are listed now and return `None` until SB2b, except Room Mark (= today's Room Tag) and Gridline Mark (= its Label, Q3) | delta D-b, grill Q3/Q6 |
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
| Gridline | Mark (= Label) | Length (mm), Angle (°) | — | — (no level) |

### Block Editor pickers (design §3)

- **Host category** = the panel `enum` row: `(none)` + `CATEGORIES`; an unknown file value appears as an extra `⚠ <name> — unknown category` entry. Changing it never rewrites host keys.
- **Host key** (Attributes editor column) = a dropdown like the type / source columns: non-selectable tier headers, items `Label (Key)`, an unknown key kept as `⚠ <key> — unknown key`. Disabled when source = instance or category = `(none)`; an existing value is still stored.

## Acceptance Criteria

1. `PARAMS` holds exactly the key table above for the 8 categories, each with label, kind, tier and a getter returning the canonical raw value or `None`.
2. `category_of` returns the right category for every class, including each `WallOpening` kind, and `None` for anything else.
3. Values render in project display units by kind; a unit switch re-formats bound text through `_refresh_all_labels`.
4. A block bound to a category resolves `@[key]` from a real host through `host_values()`; a host property edit updates the text with `prepareGeometryChange`.
5. The Block Editor shows the Host category dropdown and per-attribute host-key dropdowns grouped by tier; unknown category / key are kept, shown in the warn colour, and the block loads.

## Edge Cases & Error Handling

- Getter failure or missing data → `None` → placeholder; one bad element never breaks paint.
- Deleted host (`scene() is None`) → treated as no host → placeholders.
- Uncalibrated scene → `pixels_per_mm` default 1.0 (1 px = 1 mm), as everywhere else.

## Verification Checklist

- **G1** real Room, Wall, Door, Pipe (+ nodes), Sprinkler, Gridline through real constructors on a scene: every key's raw value against a hand-derived one (a 4 m × 3 m room → Area 12e6 mm²; door Width 915 mm), a calibrated scene (ppm 2), and a unit switch (imperial ↔ m) changing `HostValue.text`.
- **G-B1** a block bound to `Door` with `@[W]`→`Width`, `@[R]`→`Room.Name`, `.host` = a real door in a real room: painted bound text = the formatted values; a width edit committed through the property panel (`property_manager` dispatch) updates the text and `boundingRect`; a unit switch + `_refresh_all_labels` reflows it.
- **G-B2** each category's host-key items = its `PARAMS` keys in tier groups; a loaded block with `KFactor` on `Door` and a category `Foo` keeps both through OK, shows the warn entries, and loads.
- Unit: `category_of` over every category and an unrelated item.
- Smoke: Block Editor Host category row + host-key dropdowns.

## Divergences ledger

| # | Divergence | Disposition |
|---|---|---|
| D1 | Room's own area / perimeter (`room.py` shoelace) treats scene px as mm, ignoring `pixels_per_mm`; the registry applies calibration | follow-up (pre-existing) |
| D2 | Host-bound text does not refresh on grip / move edits of the host | SB3 wires real hosts |
| D3 | `BlockInstance.host` is not serialized | SB3 / SB6 |
| D4 | Pressure / flow / velocity have no metric variant | owned by `units-and-formatting.md` D2 |
