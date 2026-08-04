---
status: current           # rev 3 + 2026-08-04 editor-UX batch, user smoke-tested 2026-08-04
last-verified: 2026-08-04
verified-commit: 7e89d5d
applies-to:
  - firepro3d/titleblock_template.py   # data model + layout solver + token engine + arrangement ops + library I/O
  - firepro3d/titleblock_editor.py     # editor window (Overview / Drawing Area / Fields / Arrangements)
  - firepro3d/titleblock_arrange.py    # Arrangements canvas + drag controller + pool list
  - firepro3d/paper_space.py           # TitleBlockTemplateItem renderer, resolution chain, view-titles
source-tasks:
  - "Title block template editor (TODO.md, P1 Architecture)"
  - "Fields + Arrangements editor tabs (TODO.md, P2 UX — rev 3)"
  - "Fix latent point-size ~2.4× PDF over-sizing (view-titles folded in; TitleBlockItem remainder stays open)"
  - "Title block field overlay with measured positions (OBSOLETED — artwork path superseded)"
---

# Title Block Template System — Design Spec

Grill 2026-07-21 (scope, parametric-replaces-artwork, storage, value scoping, save semantics, edge cases); design approved same day (approach A module trio; mockup-gated: arrangement A "Corporate top-down", filleted default corners). **Revision 2 (2026-07-22, smoke round 1):** single-size templates replace the per-size variant family; template drives the sheet's size/orientation; dynamic/static cell sizing. **Revision 3 (2026-07-22 grill + design; built 2026-07-23/24):** field-definition pool + drag-and-drop Arrangements; cell kinds collapse to `field` + `revision_table`; `@[Key]` token text; editor tabs become Overview / Drawing Area / Fields / Arrangements. **Editor-UX batch (2026-08-04 grill; built same day):** grouped Fields form; explicit `image_height_mm` (DD-15 revised); per-field `text_color`; per-edge cell borders (DD-19); Save / Save && Close / Close with mid-session live apply (DD-20); Arrangements name tooltips. This document describes as-built behavior.

## Goal

Users author **parametric title block templates** in a dedicated editor — margins, bordered areas with fillet/sharp corners, and a right-edge info strip — save them to a personal library, and apply **one single-size template per project** (the template drives the sheet's page). Fields are reusable *definitions* in a per-template pool: authored on a Fields tab (multi-line `@[Key]` token text + optional image), arranged onto the strip by drag-and-drop on an Arrangements tab; definitions survive unplacement. Sheets render the template with live field values (project metadata, per-sheet values, auto fields) and export vector-crisp at true paper-mm size.

## Motivation

The AHJ submittal package (MVP) plots through paper space. The pre-template title block was a hardcoded resolution chain (CEL DXF → PDF → programmatic) with field values painted at hardcoded fractional positions, pt-sized text that exported ~2.4× oversized, and no way to customize anything. A firm must be able to put *its own* title block on issued drawings.

**V1 is parametric, not artwork-based.** The Revit-style free-form element editor and DXF-artwork field regions were considered (grill) and rejected for v1: DXF title blocks carry text as curves (no TEXT/MTEXT — see `project_dxf_titleblock_text_as_curves` finding), making artwork field-mapping a poor first investment. Consequence: the "field overlay with measured positions" TODO item is **obsoleted**.

**Rev 3 motivation:** the rev-2 Info Strip tab conflated what a field *is* with where it *sits* (one long form + a reorder-button list), and the five cell kinds forced artificial choices (a company block wants text *and* a logo). The pool/arrangement split plus token text mirrors the user's Revit mental model and makes layout experimentation safe — rearranging can never destroy a field's configuration.

## Architecture & Constraints

Arm's-length modules (read the model → emit results; never entangle into scene internals):

| Unit | Responsibility |
|---|---|
| `titleblock_template.py` | Dataclasses, **layout solver** (`solve_layout`, `validate` — pure mm math, no QGraphics types, never decodes images), token engine (`resolve_text`, pure regex), **arrangement ops** (`place_field`/`unplace_field`/`move_field`/`pair_field` — the only sanctioned layout mutations), library I/O (`%APPDATA%/FirePro3D/titleblocks/`, `.fpd` embed, divergence compare), legacy-field + rev-2 cell-format migration |
| `TitleBlockTemplateItem` in `paper_space.py` | QGraphicsItem painting a `SolvedLayout` + values; slotted at the **top** of the title-block resolution chain |
| `titleblock_editor.py` | Modal editor window: tabs + live previews; working-copy Save/Cancel; snapshot undo |
| `titleblock_arrange.py` | Arrangements tab internals: `StripCanvas` (hosts the real renderer item + hit-testing on solved rects; overlays only in `drawForeground`), manual drag machinery (pool→canvas and intra-canvas), `PoolList`, `ArrangementsTab` (dumb composed widget — signals out, `refresh(layout)` in) |

Constraints:

- **One render path.** All previews — Overview full-sheet, Fields single-cell, Arrangements canvas — host the *same* `TitleBlockTemplateItem`; PDF export renders through the off-screen `PaperScene` rebuild unchanged. Preview surfaces lay a white paper rect beneath the item (the renderer assumes white paper; the app theme is dark).
- **mm sizing invariant.** All template text uses the paper-space §9.4 primitive (`setPixelSize` + cap-height scale); `setPointSizeF` is banned in this subsystem. Folded fix: viewport **view-titles** use the same primitive. The legacy `TitleBlockItem`/`TitleBlockFieldOverlay` pt sizing remains (fallback-only path) — tracked in TODO, not fixed here.
- **No native Qt drag-and-drop.** All Arrangements gestures are manual mouse tracking (press/move/release + drag state machine) per the house pattern (`Model_Space` has no native item drag) — native `QDrag.exec` blocks and cannot be driven by widget-level tests (project rule: tests drive widgets, not slots).
- **Dirty/undo contracts.** Template Save and per-sheet value writes follow paper-space §17.7 (`sheetModified`); value writes ride the paper `QUndoStack` (§17). Template *editing* has its own in-editor snapshot undo (capped at `_UNDO_STACK_MAX`) — model/paper undo stacks are untouched by editor sessions.
- **B&W independence.** The title block renders **as authored** always; the `paper_display` B&W/line-weight pipeline governs viewport content only.
- **Serialization.** Template + revisions ride `scene_io` only (paper space is not in `_capture_network`; see `project_dual_serialization_paths` memory: no second path to update).

## Design Decisions

1. **Parametric replaces artwork** (grill): a project with a template never renders the DXF/PDF chain; that chain remains solely as the no-template fallback. Built-in defaults stay untouched.
2. **Template = ONE paper size + orientation; one template per project; the template drives the sheet.** A template holds a single layout for a single `paper_size` + `orientation` (PAPER_SIZES dims swapped for non-native orientation). Applying a template **sets the sheet's paper size and orientation** (Revit model). A later manual sheet change that breaks the match falls back to built-in default → programmatic, with a warning (status bar + log). Templates display as "Name (SIZE)", with ", Portrait"/", Landscape" appended when non-native.
3. **Form + live preview** for template geometry (margins, borders); the *cell arrangement* uses direct manipulation (drag-and-drop on the true render) — the one place a form fights the user's spatial intent.
4. **One editor window does it all:** ribbon Draft tab → "Title Block". Library picker ("Name (SIZE)") + New/Duplicate/Delete, component tabs **Overview / Drawing Area / Fields / Arrangements**, and **"Use for this project"**.
5. **Storage: user library + full embed.** Library file per template (`<uuid>.json`, images embedded base64 → self-contained). The `.fpd` embeds the full template dict; **embedded copy is authoritative** on open. Divergence (same uuid, different `modified`) → explicit push/pull/ignore notice; never silent sync. Comparison uses post-migration `modified` stamps — an old-format library twin of a migrated embed does not false-positive. Loading never writes migrated formats back to disk; only explicit Save/Push do.
6. **Right strip only in MVP.** `strip_edge: "right"` reserved for future bottom/top.
7. **Seeded default template**: arrangement A "Corporate top-down" (logo, company, project, address, title, paired Scale|Date, Drawn|Checked, Drawing No|Rev, revision table, stamp), filleted frames (radius 10 mm), ANSI D landscape, stamp dynamic. Re-authored natively in the rev-3 model with identical visual output; `DEFAULT_SEED_MODIFIED = "2026-07-23"`.
8. **Overflow: keep text size, wrap, push lower cells down** — never shrink text. Clip + warn past the strip bottom; Save is blocked only when the *minimum* (unwrapped) stack can't fit.
8b. **Dynamic vs static sizing** (per placement, DD-11): leftover strip height after the static pass is distributed among **dynamic** rows proportionally to their `min_height_mm` — a stack containing any dynamic row fills the strip exactly. The seeded default marks the **stamp** dynamic. A paired row is dynamic if either slot is (per-slot storage, per-row solve — the props panel edits the slot; see Known Limitations).
9. **Value scoping** (grill): project-scoped = the `PROJECT_STD_KEYS` set (Project, Project Number, **Address Line 1/2/3**, Client, **Client Address Line 1/2/3**, Designer, Description — City/State replaced by free-form address lines 2026-08-04) plus custom rows (Company, Drawn By, Checked By arrive as migrated custom rows); sheet-scoped = Title, Drawing No, Rev, Date. Auto = Scale, `Sheet No` (reserved for multi-sheet; **not** in the known-key set, so a hand-typed `@[Sheet No]` renders literally + warns — consistent between previews and sheets), auto-Date ("Date (auto)"). **Legacy token aliases** (`PROJECT_TOKEN_ALIASES`): `@[Address]` stays token-known and mirrors Address Line 1 (the seeded default uses it); `@[City]`/`@[State]` stay known-but-empty (their data migrates into Address Line 2 via `migrate_project_info` on load — one-way, idempotent: `address`→`address1`, `city`+`state` join ", " → `address2`, new keys win). Aliases are not offered in the Insert-field picker.
10. **Rejected alternatives:** grow-`paper_space.py`-in-place; QTextDocument rendering (no mm/fillet/print control).

**Rev-3 decisions (2026-07-22 grill + design; as-built):**

11. **Pool ontology.** Field *definitions* exist independently of *placement*. Fields tab owns the roster (create/edit/delete + intrinsics); Arrangements owns placement (which fields, order, pairing, sizing, min height). Unplace (drag off strip, or select + Delete key) returns a field to the pool with its configuration intact; delete exists only on the Fields tab (warns when placed; also unplaces). New/duplicated fields start unplaced, names deduped. One placement per definition (duplicate content = duplicate the definition).
12. **Unified field.** Cell kinds are `field` + `revision_table`. A field = name + optional label + one multi-line **text template** with `@[Key]` tokens + optional image (base64 PNG, contain-fit), rendered stacked label → image → text (`image_position: "top"` reserved for future side-by-side). Stamp = empty field (typically dynamic); logo = image-only field. Rev-2 kinds `field_key`/`static_text`/`logo`/`stamp` migrate one-way, idempotently.
13. **Token semantics.** `@[Key]` resolves through the existing value chain. Known key + empty value → renders empty. Unknown key → renders **literally** + non-blocking warning (doubles as the escape hatch; no escape syntax). Known set = `build_field_values().keys()` — the function seeds all standard project + sheet keys with `""` (derived from `PROJECT_STD_KEYS` + `DEFAULT_TITLE_BLOCK_FIELDS`, one home — no second key list). The editor's `_SAMPLE_VALUES` key set derives from the same constants, so token-known/unknown behaves identically in previews and on sheets. Malformed tokens (unclosed/nested/empty) don't match the regex → literal. `validate()` never sees values, so token issues structurally cannot block Save.
14. **Explicit rows replace `pair_with_next`.** `TemplateLayout` stores `fields: list[FieldDef]` + `rows: list[list[Slot]]` (1–2 slots per row; the row *is* the pairing; `len(row) ≤ 2` validated). Gestures map 1:1 onto the structure; dangling-pair-flag states are unrepresentable. Pool = fields whose id appears in no row.
15. **Image band: remainder by default, explicit by request** (revised 2026-08-04). `FieldDef.image_height_mm = 0` (default, and all migrated/legacy fields) keeps the original remainder-band behavior: cell height = `max(min_height, label + text + pad)`, image contain-fits between label and bottom-anchored text. A positive `image_height_mm` makes the cell grow to `label + image_height + text + 2·pad` and the band exactly that tall (mm is how a printed logo is specified); the band is clamped + warned only in the defensive taller-constraint case, and revision tables ignore the knob in both passes. Band ≤ 0 → image hidden + non-blocking warning. Text stays sacred (DD-8). The solver never decodes images (aspect fitting happens at paint; per-FieldDef pixmap cache keyed by id).
16. **Manual drag machinery.** A drag state machine (4 px Manhattan threshold) serves intra-canvas drags; `PoolList` is a manual drag source mapping pool-local → global → canvas coordinates, using only public canvas API (`show_drop_hint`/`clear_drop_hint`/`apply_pool_drop`). The canvas hosts **one** renderer item and hit-tests solved rects — no per-cell QGraphicsItems; gestures mutate the working layout via the pure ops → re-solve → re-render. Gesture vocabulary: drag from pool + insertion line = place full-width; vertical drag = reorder; drop on left/right half of a single-slot row = pair (drop on partner's half = swap sides; own half = no-op); paired rows offer above/below zones + "full" cue for outsiders, halves for member swap; drag off strip = unplace; click = select (placement props); select + Delete = unplace (view accepts the Delete ShortcutOverride — known trap); **Esc or focus loss cancels an in-flight drag** (no snapshot; release-after-cancel inert; idle Esc still rejects the dialog).
    - **Zone hit-testing:** insertion bands at row boundaries are `TB_INSERT_BAND_PX` (px, zoom-converted) capped at a quarter of each adjacent row's height, so row interiors stay reachable at any zoom; `DropZone.row_index` is a **`layout.rows` index** (via `SolvedLayout.row_layout_indices`), dangling-slot-safe; pair/full classification follows the *rendered* row occupancy.
    - **No empty snapshots:** drops are gated by a **dry-run prediction** (`_drop_would_mutate` runs the real ops on a trial layout and compares row structure — new op guards are picked up automatically); dead drops emit no gesture signals, and actionable-looking hints for dead drops are downgraded to the "full" cue.
17. **Arrangements tab = three columns** (mockup-gated 2026-07-22): pool cards (unplaced only; kind glyph + name + first text line) | strip canvas (white paper backdrop on neutral gray, **fit-to-strip on first show**, wheel zoom + Fit button) | placement props on selection (min height `DimensionEdit`, Static/Dynamic combo) above the relocated **strip-border group**. Solver warnings surface in an inline banner. Non-gesture edits that affect the strip (border group, Overview margins/strip width) re-solve the canvas.
18. **Fields tab = roster + intrinsics + single-field preview.** Roster lists *all* definitions with ●/○ placed indicators. The intrinsics form is **grouped** (2026-08-04): **Identity** (name / label / type combo — revision table swaps text/image inputs for `revision_rows`), **Content** (multi-line text editor, commit on focus-out, + "Insert field ▾" token menu (Auto / Sheet / Project groups; `Sheet No` disabled until multi-sheet); image group = 120×72 thumbnail + choose/clear + **Height (mm)** input (0 = auto, DD-15); revision rows), **Text Style** (font, cap height, bold+italic on one row, alignment, **text colour** swatch — DD-21), **Fill & Border** (fill; cell-border group incl. edge checkboxes — DD-19). The selected definition renders live as **one true cell** (one-row mini solve at current strip width, white backdrop; the mini strip **re-solves at the natural cell height** when content — e.g. an explicit image height — exceeds the nominal preview strip, so the preview never clips what a real sheet would show); preview slot min-height = the placed slot's value when placed, else `TB_PREVIEW_MIN_MM`. One snapshot per form gesture; no-op commits (unchanged values, cancelled color dialogs, per-keystroke churn) push nothing — the font combo commits on `activated`/`editingFinished`, never per keystroke.

**2026-08-04 editor-UX batch decisions:**

19. **Per-edge cell borders.** `BorderStyle` carries `edge_top/edge_bottom/edge_left/edge_right` (default all on). Edge selection applies to **field cells only** — the editor never shows edge checkboxes for the Drawing Area / Info Strip frame groups and omits edge keys from their dicts (soft invariant; the renderer applies flags to any BorderStyle). **Fillet requires all four edges**: with any edge off the Corner/Fillet controls disable (tooltip) and the renderer paints straight per-edge segments (SquareCap closes shared corners). `visible` stays the master toggle; pre-edge dicts load as all-four-on → identical rendering. Note: adjacent cells each paint their own side of a shared boundary — turning one cell's edge off does not remove the neighbour's line.
20. **Save / Save && Close / Close** (replaces the single Save-and-close button). **Save** (ApplyRole) writes the library, stamps `modified`, and **stays open**, emitting `templateSaved(copy)`; MainWindow live-applies it (embed + sheet size/orientation + rebuild + §17.7 dirty) **iff** the saved uuid matches the project's embedded template — editing an unrelated library template never touches the project. **Save && Close** = Save then accept (the pre-batch behavior; the resulting double-apply is idempotent by contract — see `_apply_titleblock_template`). **Close** rejects; unsaved edits discard, but a **saved use-intent survives**: "Use for this project" followed by a successful Save applies the saved copy even when the dialog is closed via Close (`result_saved` flag). Validation gates both save buttons identically. Live-save keeps embed and library in sync, which reduces divergence prompts (DD-5) rather than interacting badly with them.
21. **Text colour.** One `text_color` per field (default `#000000`) painted by the single `_draw_text_mm` choke point — label, body text, and revision-table text all take it; revision-table **divider lines stay black** (table chrome). Migration/legacy default renders identically.
22. **Arrangements tooltips.** Hovering a strip cell shows the field's **name only** (fallback: id) via a `viewportEvent` ToolTip intercept over the solved cell rects; pool cards carry `setToolTip(name)`. Stamps and the revision table — the cells whose render doesn't identify them — are exactly the point. Placement facts stay in the props panel.

## Data Model

All dataclasses have `to_dict`/`from_dict`; unknown keys ignored on load (forward compat).

```python
@dataclass
class FieldDef:                      # intrinsic — survives unplacement
    id: str                          # short uuid (new_field_id()); Slot references it
    kind: str = "field"              # "field" | "revision_table"
    name: str = ""                   # identity in roster/pool/warnings
    label: str = ""                  # small-caps label row; "" = none
    text: str = ""                   # multi-line; @[Key] tokens resolve at solve time
    image_data: str = ""             # base64 PNG; "" = no image
    image_fit: str = "contain"
    image_position: str = "top"      # reserved (future side-by-side)
    image_height_mm: float = 0.0     # explicit band height; 0 = remainder band (DD-15)
    font_family: str = "Arial"
    cap_height_mm: float = 3.0
    bold: bool = True
    italic: bool = False
    alignment: str = "left"
    text_color: str = "#000000"      # label + body + revision text (DD-21)
    fill_color: str = ""             # "" = no fill
    border: BorderStyle = ...        # per-cell border; edge_top/bottom/left/right (DD-19)
    revision_rows: int = 3           # revision_table only

@dataclass
class Slot:                          # placement — one strip position
    field_id: str
    min_height_mm: float = 10.0
    sizing: str = "static"           # "static" | "dynamic" (DD-8b)

@dataclass
class TemplateLayout:
    margin_edge_mm / margin_strip_mm / strip_width_mm / strip_edge   # unchanged
    area_border / strip_border: BorderStyle                          # unchanged
    fields: list[FieldDef]           # the whole roster (placed + unplaced)
    rows: list[list[Slot]]           # top-to-bottom; 1–2 slots; row = pairing
    # helpers: field_map() / placed_ids() / pool_fields()
```

`TitleBlockTemplate` (name/uuid/modified/paper_size/orientation/layout) unchanged. **Migration:** `_migrate_cells(cells) -> (fields, rows)` lives in **`TemplateLayout.from_dict`** (fires when a dict carries `cells` without `fields`; when both are present, `fields` wins) — chains `pair_with_next` into two-slot rows; `field_key="X"` → `text="@[X]"`; `static_text` → `text`; `logo` → image-only; `stamp` → empty field; names generated label → field-key → kind-name, deduped. The rev-1 `variants` shim in `TitleBlockTemplate.from_dict` chains through it, so any historical file loads. One-way; save writes rev-3; `from_dict(to_dict(x)) == x` for rev-3 dicts. Field ids are regenerated on each rev-2 migration but are referenced only *within* the template dict — nothing else persists them.

**Sheet/Project storage (built rev 1–2):** `Sheet.orientation` ("" = native; `sheet_page_mm()` owns the swap rule), `Sheet.revisions: list[dict]`, open `title_block_fields` dict, `scene_io` payload `titleblock_template: dict | None` (stored opaquely — nothing outside this subsystem introspects it).

**Library:** `%APPDATA%/FirePro3D/titleblocks/<uuid>.json`, directory created on first use, atomic writes. Corrupt/unparseable file → skipped with a warning.

## Layout Solver

Pure functions; QRectF/QFontMetricsF allowed, QGraphics types are not; never decodes images.

- `solve_layout(layout, paper_w_mm, paper_h_mm, values) -> SolvedLayout`
  1. Drawing-area rect = paper − `margin_edge_mm` (all sides) − (`strip_width_mm` + `margin_strip_mm`) on the right; strip rect down the right edge.
  2. Rows walk top-to-bottom over `rows`. Slots referencing missing fields are dropped with a warning; fully-dangling rows are skipped. Per slot: resolve the field's text via `resolve_text(field.text, values)` (unknown keys → warnings); wrap at slot width; cell height = `max(min_height_mm, label_row + wrapped_text + 2·pad)` — or, with an explicit image height (DD-15: `image_data` + `image_height_mm > 0`, non-revision-table), `max(min_height_mm, label_row + image_height_mm + wrapped_text + 2·pad)`; row height = max of its slots. Revision table → header + `revision_rows` newest-first entries. **Image band** = remainder (cell − label − text) by default, or exactly `image_height_mm` when explicit (clamped + "reduced to fit" warning in the defensive case); ≤ 0 → no band + warning. Both passes share the same explicit-image predicate (incl. the revision-table exclusion) — mirrored-guard drift here caused a spurious-warning bug once.
  3. Dynamic pass (DD-8b): leftover strip height distributed among dynamic rows ∝ `min_height_mm` (designer-set minimum, not wrap-grown height).
  4. Sub-rect pass (after the dynamic pass): per-cell `label_rect / image_rect / text_rect` — the stacking math has one home; the renderer paints, never re-derives. No-image cells keep rev-2 top-aligned text positioning exactly.
  5. Cells past the strip bottom are clipped + flagged.
- `SolvedLayout`: area/strip rects; flat row-major index-aligned `cell_rects` / `cell_field_ids` / `cell_lines` / sub-rect lists / `cell_revision_rows`; `row_spans` (first flat idx, n) and `row_layout_indices` (solved row → `layout.rows` index, dangling-safe); `warnings` — four kinds: unknown token key, dangling slot dropped, image no-room, strip overflow.
- `validate(layout, paper_w_mm, paper_h_mm) -> list[str]` — save-blocking floors: margins ≥ 0; strip width ≥ `TB_STRIP_MIN_MM`; drawing area ≥ `TB_AREA_MIN_MM` each dimension; fillet ≤ half the bordered rect's smaller dimension; cap heights > 0 (all fields, incl. unplaced — a bad pool definition blocks Save); slot min heights ≥ 0; **≥ 1 placed row**; `len(row) ≤ 2`; every `Slot.field_id` resolves; minimum (unwrapped) stack fits the strip. The rev-2 "field cells need a field key" floor is gone — empty fields are legal (that's the stamp). Unplaced definitions are info-level only, never blocking. Signature excludes `values` — token warnings are structurally non-blocking.

**Token engine**, same module: `TOKEN_RE = r"@\[([^\[\]]+)\]"`; `resolve_text(text, values) -> (str, list[str])` substitutes known keys (`values.keys()`), leaves unknown tokens literal, returns unknown keys deduped in first-appearance order.

**Arrangement ops**, same module — the only sanctioned layout mutations (canvas drops, Delete-unplace, and editor actions all route here): `place_field(layout, fid, row_index)` (new full-width row at clamped index, interpreted **after** removal of the field's own single-slot row; moves if already placed), `move_field` (alias), `unplace_field` (definition survives), `pair_field(layout, fid, row_index, side)` (left inserts, right appends; member on partner's half swaps; own half / own single row / full row / unknown id / bad index → no-op). Guards here are picked up by the canvas's dry-run drop prediction automatically.

## Renderer & Resolution Chain

`TitleBlockTemplateItem(QGraphicsItem)` paints a `SolvedLayout`: fills → one hoisted strip clip around content (labels, contain-fit image bands from the per-field pixmap cache, revision rows, text — all via solver sub-rects, mm primitive §9.4; the text pen is the field's `text_color`, DD-21) → borders (cells, then area, then strip; `addRoundedRect` when fillet and all four edges on, straight per-edge segments otherwise, DD-19). A stamp is an empty field cell — no special paint path. Undecodable images → warning + no paint, never a broken image on a plot.

Resolution order in `PaperScene._setup` (supersedes paper-space §8.1):

1. Project template matches the sheet (`paper_size` + effective orientation agree) → `TitleBlockTemplateItem`.
2. Template exists but doesn't match (manual sheet change) → **warn** (status bar via `titleblock_warning`), fall to 3.
3. No template: legacy chain — DXF → PDF → programmatic, unchanged.

**Template drives the sheet (DD-2):** on apply, MainWindow sets `sheet.paper_size`/`sheet.orientation` from the template before the rebuild. The load path does NOT force size/orientation (the `.fpd`'s stored page is authoritative; a persisted mismatch renders the fallback + warning, never a silent resize). A manual paper-size change resets `sheet.orientation` to native.

Template Save re-renders open sheets and emits `sheetModified` (§17.7) — both on Save && Close (accept path) and mid-session via `templateSaved` → `MainWindow._on_titleblock_saved_live` (uuid-match, corrupt-embed-guarded; DD-20). `_apply_titleblock_template` is the single apply implementation for both paths and **must stay idempotent** (Save && Close runs it twice with identical payloads).

## Value Model & Editing Surfaces

Resolution at render happens per **token** (DD-13): **auto → per-sheet → Project Info (standard, then custom rows) → ""** for known keys; unknown keys stay literal. `build_field_values` seeds every standard key with `""` (known-key set = its key set).

- **Per-sheet values:** property panel when the rendered title block is selected on the sheet (duck-typed `get_properties`/`set_property`, display-keyed — no field ids; writes ride the paper `QUndoStack`; §17.7 dirty). Plus **Edit Revisions…** panel button → table dialog writing `sheet.revisions`.
- **Project values:** Project Information dialog only (existing surface; writes exactly the keys `PROJECT_STD_KEYS` maps from, plus custom rows).
- **Migration on load** (legacy 9-key `title_block_fields`), one-way + idempotent: Company → Project Info custom "Company" *if absent*; Project → `name` *if empty*; Drawn By/Checked By → custom rows *if absent*; Title/Drawing No/Rev/Date stay per-sheet; Scale key dropped (auto).

## Edge Cases & Error Handling

- Embedded template authoritative; library divergence → explicit push/pull/ignore (post-migration `modified` compare), never silent; loading never rewrites library files.
- Template/sheet mismatch → warn + built-in fallback (chain 3).
- Unknown `@[Key]` → literal + warning (never silently empty); known-but-empty → empty (never a literal token on a plot).
- Image band ≤ 0 → image hidden + warning. Missing/corrupt image → warning, no paint.
- `Slot.field_id` not in `fields` (hand-edited file) → slot dropped with a warning at solve; blocking at validate.
- Corrupt library JSON → skip + warn. Library dir auto-created.
- Overflow → wrap/grow/push; clip + warn at strip bottom; degenerate minimum blocks Save.
- Rev-1/rev-2 files (library or embed) migrate silently in memory on load; save writes rev-3. No-template projects render exactly as before (regression-pinned).
- Drag robustness: Esc / focus loss cancels; release-after-cancel inert; dead drops (own half, own position, full rows) mutate nothing and push no snapshot.

## Known Limitations (follow-ups filed in TODO.md)

- Solver/renderer warnings surface in the **editor** (banner + preview) but are silently dropped on real sheets — a template that overflows with real project values renders clipped with no message.
- The sheet-mismatch warning names only the paper size; an orientation-only mismatch reads confusingly.
- Placement props edit the **slot**; on a mixed static|dynamic pair the row solves dynamic while the selected static member displays "Static" (per-slot storage, per-row solve) — needs an "effective" hint.
- The Fields tab lives inline in `titleblock_editor.py` (a `FieldsTab` widget extraction to mirror `ArrangementsTab` was deferred mid-branch).
- `_do_save`'s `project_template_result` refresh is not gated on template identity: Use template A → Save → switch to B → edit → Save B applies **B** to the project without an explicit "Use" (pre-existing via the old Save button; more visible since 2026-08-04). Fix direction: uuid-gate the refresh.
- The editor dialog is not `deleteLater()`'d per open (scene/undo snapshots accumulate per MainWindow session; import dialog sets the precedent).

## Performance & Security

Solver runs per form change in the editor, once per sheet rebuild, and once per completed gesture (plus one redundant solve per gesture via the tab refresh — accepted at strip scale). Per-mouse-move work is zone classification + a dry-run on the tiny rows list — no solve, no image decoding. Image base64 inflates `.fpd`/library files; acceptable. No external I/O beyond APPDATA + project file.

## Code Style & Testing

Conventions per CLAUDE.md (mm storage; `constants.py` owns `TB_PREVIEW_MIN_MM`, `TB_INSERT_BAND_PX`, `TB_POOL_CARD_W` + rev-1 TB_ constants; Google docstrings; relative imports). Tests: `tests/test_titleblock_template.py`, `tests/test_titleblock_editor.py`, `tests/test_titleblock_arrange.py`, `tests/test_titleblock_render.py`, + `tests/test_paper_space.py`/`tests/test_paper_export.py` additions:

- **Solver/token/ops unit:** stack math, row pairing, wrap/grow/push-down, remainder-band math (incl. band ≤ 0), sub-rect geometry, dynamic distribution basis (min-height, not wrap growth), validation floors, token substitution/dedup/malformed passthrough, all arrangement-op edges (own-half, own-single-row, clamping, prop preservation).
- **Serialization/migration:** round-trips, migration idempotence (all four rev-2 kinds, paired chains, variants-era chain-through, cells+fields precedence), divergence detection, corrupt-file skip; **frozen rev-2 seeded-default parity fixture** (verbatim from `23fa804`) pinning cell count, row shape, dynamic stamp, and token parity; rev-2 `.fpd` embed load through the real save/load path.
- **Widget-driven behavior** (project rule; sabotage/red-verified): editor Save/Cancel/snapshot-undo, Fields-tab form commits incl. focus-out text commit and border-group wiring, all drag gestures via synthesized viewport mouse events (place/reorder/pair/swap/unpair/unplace, Esc cancel, threshold, dead-drop no-signal), Delete-unplace via the ShortcutOverride path, pool→canvas cross-widget drag, snapshot-per-gesture depth pins, non-gesture canvas sync, white-backdrop and first-show-fit pins.
- **Export-render:** templated sheet → PDF page + content assertions; combined image+text cell asserts the image's pixels actually appear; view-title mm-sizing regression.

## Acceptance Criteria

Rev 1–2 (built, smoke-tested 2026-07-22 — see git history at `23fa804`). Rev 3 (built 2026-07-23/24, smoke-tested 2026-07-24):

- [x] Fields tab: roster with placed indicators; New/Duplicate/Delete (delete warns when placed; also unplaces); intrinsics form incl. multi-line text + Insert field ▾ token menu, image choose/clear/thumbnail, type combo; live single-field true-render preview; new fields start unplaced.
- [x] Arrangements tab: three columns; all DD-16 gestures incl. Esc-cancel and select+Delete; overlays never alter the rendered item; inline warning banner; white paper backdrop + fit on first show.
- [x] Token text: `@[Key]` resolves per DD-13 on sheet render, PDF export, and both editor previews; unknown keys render literally + warn; known-empty render empty; preview/sheet known-key parity.
- [x] Combined cells: image + text stack per DD-15; logo-only and stamp render identically to rev 2; image-no-room warns.
- [x] Data model: `FieldDef` + `Slot` + `rows`; `pair_with_next` states unrepresentable; `image_position` reserved.
- [x] Migration: rev-1/rev-2 files (library and `.fpd`) load and render visually identical; save writes rev-3; idempotent; seeded default re-authored + stamp bumped; divergence post-migration.
- [x] Undo: one snapshot per completed gesture; cancelled/dead drops none; undo restores fields+rows together; placement props resync after undo.
- [x] Validation: ≥ 1 placed row; `len(row) ≤ 2`; dangling ids blocked; field-key floor removed; unplaced note info-only.
- [x] Full suite green (chunked per OneDrive flake protocol): 1840 non-3D + 75 3D at `31d1c99`.

## Verification Checklist

- [x] All rev-3 acceptance criteria demonstrated (user smoke test 2026-07-24; one fix round — dark preview backdrop + first-show fit, `31d1c99`).
- [x] No regression: rev-2 template projects render identically (frozen parity fixture); no-template projects untouched; CEL chain intact.
- [x] `sheetModified`/dirty contract honored for Save (§17.7).
- [x] Holistic whole-branch seam review passed (main↔editor API, scene_io opacity, resolution chain, field-id stability, library divergence, value parity, undo/Esc routing, performance).
- [x] Spec re-audited: proposal markers removed, as-built deltas folded in, `status: current`, stamped; SPEC-INDEX row updated; TODO reconciled.
