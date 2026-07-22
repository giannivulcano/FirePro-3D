---
status: partial           # rev 1–2 current (built, smoke-tested 2026-07-22); rev 3 sections marked (proposal) pending build
last-verified: 2026-07-22
verified-commit: 23fa804
applies-to:
  - firepro3d/titleblock_template.py   # data model + layout solver + token engine + library I/O
  - firepro3d/titleblock_editor.py     # editor window
  - firepro3d/titleblock_arrange.py    # (rev 3, planned) Arrangements canvas + drag controller + pool list
  - firepro3d/paper_space.py           # TitleBlockTemplateItem renderer, resolution chain, view-titles
source-tasks:
  - "Title block template editor (TODO.md, P1 Architecture)"
  - "Fields + Arrangements editor tabs (TODO.md, P2 UX — rev 3)"
  - "Fix latent point-size ~2.4× PDF over-sizing (view-titles folded in; TitleBlockItem remainder stays open)"
  - "Title block field overlay with measured positions (OBSOLETED — artwork path superseded)"
---

# Title Block Template System — Design Spec

Grill 2026-07-21 (scope, parametric-replaces-artwork, storage, value scoping, save semantics, edge cases); design approved same day (approach A module trio; mockup-gated: arrangement A "Corporate top-down", filleted default corners). **Revision 2026-07-22 (smoke-test round 1):** single-size templates replace the per-size variant family; template drives the sheet's size/orientation; dynamic/static cell sizing; editor reorganized into Overview / Drawing Area / Info Strip tabs. **Revision 3 (2026-07-22 grill + design, PROPOSAL until built):** field-definition pool + drag-and-drop Arrangements; cell kinds collapse to `field` + `revision_table`; `@[Key]` token text; editor tabs become Overview / Drawing Area / Fields / Arrangements. Rev-3 deltas are marked **(proposal)** throughout; unmarked text is code-verified current behavior.

## Goal

Users author **parametric title block templates** in a dedicated editor — margins, bordered areas with fillet/sharp corners, and a right-edge info strip built from a stack of typed cells — save them to a personal library, and apply **one single-size template per project** (the template drives the sheet's page). Sheets render the template with live field values (project metadata, per-sheet values, auto fields) and export it vector-crisp at true paper-mm size. **(proposal, rev 3)** Fields are reusable *definitions* in a per-template pool — authored on a Fields tab (multi-line `@[Key]` token text + optional image), arranged onto the strip by drag-and-drop on an Arrangements tab; definitions survive unplacement.

## Motivation

The AHJ submittal package (MVP) plots through paper space. Today's title block is a hardcoded resolution chain (CEL DXF → PDF → programmatic) with field values painted at **hardcoded fractional positions** that don't match the DXF artwork, pt-sized text that exports ~2.4× oversized, and no way to customize anything. A firm must be able to put *its own* title block on issued drawings.

**V1 is parametric, not artwork-based.** The Revit-style free-form element editor and DXF-artwork field regions were considered (grill) and rejected for v1: DXF title blocks carry text as curves (no TEXT/MTEXT — see `project_dxf_titleblock_text_as_curves` finding), making artwork field-mapping a poor first investment. The parametric model covers real title blocks with far less machinery. Consequence: the "field overlay with measured positions" TODO item is **obsoleted**.

**Rev 3 motivation (proposal):** the rev-2 Info Strip tab conflates what a field *is* with where it *sits* (one long form + a reorder-button list), and the five cell kinds forced artificial choices (a company block wants text *and* a logo). The pool/arrangement split plus token text mirrors the user's Revit mental model and makes layout experimentation safe — rearranging can never destroy a field's configuration.

## Architecture & Constraints

Approach A — arm's-length module trio (read the model → emit results; never entangle into scene internals):

| Unit | Responsibility |
|---|---|
| `titleblock_template.py` | Dataclasses, **layout solver** (`solve_layout`, `validate` — pure mm math, no QGraphics types), **(proposal)** token engine (`resolve_text`, pure regex), library I/O (`%APPDATA%/FirePro3D/titleblocks/`, `.fpd` embed, divergence compare), legacy-field + **(proposal)** cell-format migration |
| `TitleBlockTemplateItem` in `paper_space.py` | QGraphicsItem painting a `SolvedLayout` + values; slotted at the **top** of the title-block resolution chain |
| `titleblock_editor.py` | Modal editor window: tabs + live preview; working-copy Save/Cancel; snapshot undo |
| `titleblock_arrange.py` **(proposal, rev 3)** | Arrangements tab internals: strip canvas view (hosts the real renderer item + hit-testing on solved rects), shared manual drag controller (pool→canvas and intra-canvas), pool card list. Composed by the editor dialog; keeps `titleblock_editor.py` reviewable. |

Constraints:

- **One render path.** The editor preview hosts the *same* `TitleBlockTemplateItem` on a private scene; PDF export renders through the off-screen `PaperScene` rebuild unchanged (data-driven `_setup`, as with sheet text). **(proposal)** The Arrangements canvas and the Fields tab single-field preview reuse the same item — the canvas draws interaction affordances only in `drawForeground`, never in the item.
- **mm sizing invariant.** All template text uses the paper-space §9.4 primitive (`setPixelSize` + cap-height `setScale`); `setPointSizeF` is banned in this subsystem. Folded fix: viewport **view-titles** convert to the same primitive. The legacy `TitleBlockItem`/`TitleBlockFieldOverlay` pt sizing remains (fallback-only path) — tracked in TODO, not fixed here.
- **No native Qt drag-and-drop (proposal).** All Arrangements gestures are manual mouse tracking (press/move/release + a drag controller) per the house pattern (`Model_Space` has no native item drag) — native `QDrag.exec` blocks and cannot be driven by widget-level tests (project rule: tests drive widgets, not slots).
- **Dirty/undo contracts.** Template Save and per-sheet value writes follow paper-space §17.7 (`sheetModified`); value writes ride the paper `QUndoStack` (§17). Template *editing* has its own in-editor snapshot undo — model/paper undo stacks are untouched by editor sessions.
- **B&W independence.** The title block renders **as authored** always; the `paper_display` B&W/line-weight pipeline governs viewport content only.
- **Serialization.** Template + revisions ride `scene_io` only (paper space is not in `_capture_network` — matches existing behavior; see `project_dual_serialization_paths` memory: no second path to update).

## Design Decisions

1. **Parametric replaces artwork** (grill): a project with a template never renders the DXF/PDF chain; that chain remains solely as the no-template fallback. Built-in defaults stay untouched.
2. **Template = ONE paper size + orientation; one template per project; the template drives the sheet** (revised 2026-07-22, superseding the variant-family model). A template holds a single layout for a single `paper_size` + `orientation` (landscape/portrait; PAPER_SIZES dims swapped for non-native orientation). Applying a template to the project **sets the sheet's paper size and orientation** (Revit model — the title block defines the page). If the user afterwards changes the sheet size manually and it no longer matches, the sheet falls back to built-in default → programmatic, with a warning (status bar + log). Templates display as "Name (SIZE)" — e.g. "FirePro Default (ANSI D)" — with ", Portrait" appended when non-native.
3. **Form + live preview** editing (not direct manipulation) for template geometry (margins, borders); **(proposal, rev 3)** the *cell arrangement* graduates to direct manipulation (drag-and-drop on the true render) — the one place a form fights the user's spatial intent.
4. **One editor window does it all:** ribbon Draft tab → "Title Block" opens it. Inside: library picker (entries "Name (SIZE)") + New/Duplicate/Delete, component tabs — rev 2: Overview / Drawing Area / Info Strip; **(proposal, rev 3)**: **Overview / Drawing Area / Fields / Arrangements** — and **"Use for this project"**.
5. **Storage: user library + full embed.** Library file per template (`<uuid>.json`, logo embedded base64 → self-contained). The `.fpd` embeds the full template dict; **embedded copy is authoritative** on open. Divergence (same uuid, different `modified`) → explicit push/pull/ignore notice; never silent sync. **(proposal)** Divergence compares post-migration `modified` stamps — an old-format library twin of a migrated embed does not false-positive.
6. **Right strip only in MVP.** Strip position (bottom/top for portrait) is a filed future improvement; the data model reserves `strip_edge: "right"` so files stay forward-compatible.
7. **Seeded default template** (mockup-gated 2026-07-21; revised 2026-07-22): arrangement **A — Corporate top-down** (logo, company, project, address, title, paired Scale|Date, Drawn|Checked, Drawing No|Rev, revision table, stamp), **filleted** default corners (radius 10 mm) on drawing-area and strip borders; **ANSI D landscape**, stamp cell **dynamic** (strip fills to the bottom). **(proposal)** Re-authored natively in the rev-3 model (same visual arrangement); `DEFAULT_SEED_MODIFIED` bumps.
8. **Overflow: keep text size, wrap, push lower cells down** — never shrink text. Clip + warn past the strip bottom; Save is blocked only when the *minimum* (unwrapped) stack can't fit.
8b. **Dynamic vs static cell sizing** (added 2026-07-22): each placement has `sizing: "static" | "dynamic"` (default static). Static rows behave per DD-8. After the static pass, leftover strip height is distributed among **dynamic** rows proportionally to their `min_height_mm` (equal shares when equal), each never below its wrapped/static minimum — so a stack containing any dynamic row always fills the strip exactly. No dynamic rows → DD-8 behavior unchanged. The seeded default marks the **stamp** dynamic.
9. **Value scoping** (grill): project-scoped = Company, Project, Address, Drawn By, Checked By; sheet-scoped = Title, Drawing No, Rev, Date (manual issue date). Auto = Scale (exists), `Sheet No` (reserved for multi-sheet), optional auto-Date.
10. **Rejected alternatives:** grow-`paper_space.py`-in-place (entangles layout math with paint in the biggest paper module); QTextDocument rendering (no mm/fillet/print control).

**Rev-3 decisions (2026-07-22 grill + design session — all proposal until built):**

11. **Pool ontology.** Field *definitions* exist independently of *placement*. Fields tab owns the roster (create/edit/delete + intrinsics); Arrangements owns placement (which fields, order, pairing, sizing, min height). Unplace (drag off strip, or select + Delete key) returns a field to the pool with its configuration intact; delete exists only on the Fields tab (warns when placed). New fields start unplaced. One placement per definition (duplicate content = duplicate the definition).
12. **Unified field.** Cell kinds collapse to `field` + `revision_table`. A field = name + optional label + one multi-line **text template** with `@[Key]` tokens + optional image (base64 PNG, contain-fit), rendered stacked label → image → text (`image_position: "top"` reserved for a future side-by-side option). Stamp = empty field (typically dynamic); logo = image-only field. Old kinds `field_key`/`static_text`/`logo`/`stamp` migrate one-way, idempotently.
13. **Token semantics.** `@[Key]` resolves through the existing value chain. Known key + empty value → renders empty. Unknown key → renders **literally** + non-blocking warning (doubles as the escape hatch; no escape syntax). Known set = `build_field_values().keys()` — that function now seeds all standard sheet + project keys with `""` so "known but empty" needs no second key list. Malformed tokens (unclosed/nested) don't match the regex → literal, no special cases. `validate()` never sees values, so token issues structurally cannot block Save.
14. **Explicit rows replace `pair_with_next`.** `TemplateLayout` stores `fields: list[FieldDef]` + `rows: list[list[Slot]]` (1–2 slots per row; the row *is* the pairing; `len(row) ≤ 2` validated). DnD gestures map 1:1 onto the structure; dangling-pair-flag states become unrepresentable. Rejected: placement list with a `pair_with_next` flag (gesture→flag translation + inconsistency class), in-place `placed` flag (placement custody stays muddled).
15. **Image = remainder band.** In a combined cell the image gets the space left after label + text: cell height = `max(min_height, label + text + pad)` exactly as today, text stays sacred (DD-8), image contain-fits between label and text. No `image_height_mm` knob; the author sizes the cell. Band ≤ 0 → image hidden + non-blocking warning. The solver never decodes images (stays pure; aspect fitting happens at paint). Logo-only fields behave exactly as rev-2 logo cells. Rejected: explicit image height (second height knob fighting min-height), aspect-derived (solver decodes; height shifts when strip width changes).
16. **Manual drag machinery.** A shared drag controller serves pool→canvas and intra-canvas drags (Qt keeps delivering move/release to the pressed widget, so cross-widget tracking needs no native DnD). The canvas hosts **one** renderer item and hit-tests solved rects — no per-cell QGraphicsItems; gestures mutate the working dict → re-solve → re-render. Gesture vocabulary: drag from pool + insertion line = place full-width; vertical drag = reorder; drop on left/right half of a single-slot row = pair (drop on partner's half = swap sides); paired rows offer only above/below zones + "full" cue; drag off strip = unplace; click = select (placement props); select + Delete = unplace (view must accept the Delete ShortcutOverride — known trap); **Esc cancels an in-flight drag** (no snapshot).
17. **Arrangements tab = three columns.** Pool cards (unplaced only; card = name + kind glyph + first-line content preview) | strip canvas (default zoom = fit whole strip; wheel zoom + fit button) | placement properties on selection (min height `DimensionEdit`, sizing combo) above the relocated **strip-border group**. Solver warnings (overflow, unknown tokens, image-no-room) surface in an inline banner here as well as on Overview. Mockup-gated 2026-07-22 (three-column picked over sidebar-stack and top-tray options).
18. **Fields tab = roster + intrinsics + single-field preview.** Roster lists *all* definitions with a placed/unplaced indicator (pool shows only unplaced — different question). Form: name, label, multi-line text editor + "Insert field ▾" token helper (the old grouped key picker, now inserting at cursor), image choose/clear + thumbnail, type combo (field / revision table — the latter swaps text/image inputs for `revision_rows`), text style, fill, cell border. The selected definition renders live as **one true cell** (one-row mini solve at current strip width) via the same renderer item; preview slot min-height = the placed slot's value when placed, else `TB_PREVIEW_MIN_MM` (`constants.py`, nominal — keeps an unplaced image-only field's band visible).

## Data Model

All dataclasses have `to_dict`/`from_dict`; unknown keys ignored on load (forward compat).

**Rev 2 (current, built):** `CellSpec` (kind ∈ 5 kinds, `field_key`, `static_text`, `logo_data`, placement facts `min_height_mm`/`sizing`/`pair_with_next`, typography, fill, border) in `TemplateLayout.cells: list[CellSpec]` — see git history at `23fa804` for the full shape.

**Rev 3 (proposal):**

```python
@dataclass
class FieldDef:                      # intrinsic — survives unplacement
    id: str                          # short uuid; Slot references it
    kind: str = "field"              # "field" | "revision_table"
    name: str = ""                   # identity in roster/pool/warnings
    label: str = ""                  # small-caps label row; "" = none
    text: str = ""                   # multi-line; @[Key] tokens resolve at solve time
    image_data: str = ""             # base64 PNG; "" = no image
    image_fit: str = "contain"
    image_position: str = "top"      # reserved (future side-by-side)
    font_family: str = "Arial"
    cap_height_mm: float = 3.0
    bold: bool = True
    italic: bool = False
    alignment: str = "left"
    fill_color: str = ""             # "" = no fill
    border: BorderStyle = ...        # per-cell border
    revision_rows: int = 3           # revision_table only

@dataclass
class Slot:                          # placement — one strip position
    field_id: str
    min_height_mm: float = 10.0
    sizing: str = "static"           # "static" | "dynamic" (DD-8b)

@dataclass
class TemplateLayout:
    margin_edge_mm / margin_strip_mm / strip_width_mm / strip_edge  # unchanged
    area_border / strip_border: BorderStyle                          # unchanged
    fields: list[FieldDef]           # the whole roster (placed + unplaced)
    rows: list[list[Slot]]           # top-to-bottom; 1–2 slots; row = pairing
```

Pool = fields whose id appears in no row. `TitleBlockTemplate` (name/uuid/modified/paper_size/orientation/layout) is unchanged. **Migration (proposal):** `_migrate_cells(cells) -> (fields, rows)` inside `TitleBlockTemplate.from_dict` — chains `pair_with_next` into two-slot rows; `field_key="X"` → `text="@[X]"`; `static_text` → `text`; `logo` → image-only; `stamp` → empty field; names generated label → field-key → kind-name, deduped. The rev-1 `variants` shim chains through it, so any historical file loads. One-way; save writes rev-3 format; `from_dict(to_dict(x)) == x` for rev-3 dicts.

**Sheet/Project additions (current, built):** `Sheet.orientation` ("" = native; `sheet_page_mm()` owns the swap rule), `Sheet.revisions: list[dict]`, open `title_block_fields` dict, `scene_io` payload `titleblock_template: dict | None`.

**Library:** `%APPDATA%/FirePro3D/titleblocks/<uuid>.json`, directory created on first use. Corrupt/unparseable file → skipped with a warning; never crashes the library list.

## Layout Solver

Pure functions; QRectF/QFontMetricsF allowed, QGraphics types are not. **(proposal)** The solver never decodes images.

- `solve_layout(layout, paper_w_mm, paper_h_mm, values) -> SolvedLayout`
  1. Drawing-area rect = paper − `margin_edge_mm` (all sides) − (`strip_width_mm` + `margin_strip_mm`) on the right; strip rect down the right edge.
  2. **(proposal)** Rows walk top-to-bottom over `rows` (the rev-2 `pair_with_next` grouping loop retires). Per slot: resolve the field's text via `resolve_text(field.text, values)` (unresolved keys → `warnings`); wrap at slot width; cell height = `max(min_height_mm, label_row + wrapped_text + 2·pad)`; row height = max of its slots. Revision table → header + `revision_rows` newest-first entries. **Image band** = cell height − label row − text height (remainder, DD-15); ≤ 0 → no band + warning.
  3. Dynamic pass (DD-8b) unchanged: leftover strip height distributed among dynamic rows ∝ `min_height_mm`.
  4. Cells past the strip bottom are clipped + flagged in `warnings`.
- **(proposal)** `SolvedLayout` keeps flat row-major index-aligned lists (renderer indexing survives) and gains per-cell **sub-rects**: `label_rect / image_rect / text_rect` — the stacking math has one home; the renderer paints, never re-derives.
- `validate(layout, paper_w_mm, paper_h_mm) -> list[str]` — save-blocking floors: margins ≥ 0; strip width ≥ `TB_STRIP_MIN_MM`; drawing area ≥ `TB_AREA_MIN_MM` each dimension; fillet ≤ half the bordered rect's smaller dimension; cap heights > 0; min heights ≥ 0; minimum (unwrapped) stack fits the strip. **(proposal)** Changed: "≥ 1 cell" → **"≥ 1 placed row"**; new `len(row) ≤ 2` and every `Slot.field_id` resolves; **dropped**: "field cells need a field key" (empty fields are legal — that's the stamp). Unplaced definitions are an **info-level note**, never blocking. Signature still excludes `values` — token warnings are structurally non-blocking.

**(proposal)** Token engine, same module: `TOKEN_RE = r"@\[([^\[\]]+)\]"`; `resolve_text(text, values) -> (str, list[str])` substitutes known keys (`values.keys()`), leaves unknown tokens literal, returns the unknown list.

## Renderer & Resolution Chain

`TitleBlockTemplateItem(QGraphicsItem)` paints a `SolvedLayout`: fills → borders (`QPainterPath.addRoundedRect` when fillet) → labels/values/static text (mm primitive §9.4) → image pixmaps (placeholder box + warning if undecodable) → revision rows. **(proposal)** Rev 3: paints the solver's per-cell sub-rects (label row, contain-fit image band, text lines); iterates (Slot, FieldDef) pairs resolved from the layout; a stamp is just an empty field cell — no special paint path.

Resolution order in `PaperScene._setup` (supersedes paper-space §8.1; unchanged by rev 3):

1. Project template matches the sheet (`paper_size` + orientation agree) → `TitleBlockTemplateItem`.
2. Template exists but doesn't match (manual sheet change) → **warn**, fall to 3.
3. No template: existing chain — DXF → PDF → programmatic, unchanged.

**Template drives the sheet (DD-2):** on apply, MainWindow sets `sheet.paper_size`/`sheet.orientation` from the template before the rebuild. The load path does NOT force size/orientation (the `.fpd`'s stored page is authoritative; a persisted mismatch renders the fallback + warning, never a silent resize). A manual paper-size change resets `sheet.orientation` to native.

Template Save re-renders open sheets and emits `sheetModified` (§17.7).

## Editor (`titleblock_editor.py` + `titleblock_arrange.py`)

Modal window, ribbon Draft tab → "Title Block". Left = template picker (library list "Name (SIZE[, Portrait])", New/Duplicate/Delete-with-confirm, "Use for this project"); validation warning label + Save/Cancel below the tabs, visible from every tab.

Component tabs — rev 2 (current): Overview / Drawing Area / Info Strip. **Rev 3 (proposal): Overview / Drawing Area / Fields / Arrangements:**

- **Overview** — unchanged: Paper Setup group (name, size dropdown, orientation radios, margin/strip-width `DimensionEdit`s) + full-sheet live preview.
- **Drawing Area** — unchanged: area border group. (Strip border moves out → Arrangements.)
- **Fields** — per DD-18: roster (all definitions, placed indicator, New/Duplicate/Delete) | intrinsics form with multi-line text + "Insert field ▾" | live single-field true-render preview.
- **Arrangements** — per DD-16/17: pool cards | strip canvas (one renderer item, manual drag controller, `drawForeground` overlays: insertion line, half highlight, full cue, ghost; wheel zoom, fit default) | placement props + strip border group; inline warning banner.

**Session semantics:** working copy; **Save** = write library JSON + project embed + re-render + dirty; **Cancel** discards; **Ctrl+Z/Y** = snapshot stack of the working dict, one snapshot per form gesture — **(proposal)** extended: each completed drag op, each Delete-unplace = one snapshot; cancelled drag (Esc / invalid drop) = none; undo restores `fields` + `rows` together (one working dict). Save disabled while `validate()` is non-empty.

## Value Model & Editing Surfaces

Field-key resolution at render: **auto → per-sheet → Project Info (standard, then custom rows) → ""**. **(proposal)** Rev 3: resolution happens per **token** inside the field text (DD-13) rather than per cell; `build_field_values` seeds all standard sheet + project keys with `""` (known-key set = `values.keys()`; behavioral no-op for rev-2 rendering since missing keys already resolved to "").

- **Per-sheet values:** property panel when the rendered title block is selected on the sheet (duck-typed `get_properties`/`set_property`; writes ride the paper `QUndoStack`; §17.7 dirty). Plus **Edit Revisions…** panel button → No/Description/Date table dialog writing `sheet.revisions`.
- **Project values:** Project Information dialog only (existing surface).
- **`TitleBlockDialog` retired** (rev 1).
- **Migration on load** (legacy 9-key `title_block_fields`), one-way + idempotent, no visible change until a template exists: Company → Project Info custom "Company" *if absent*; Project → `name` *if empty*; Drawn By/Checked By → custom rows *if absent*; Title/Drawing No/Rev/Date stay per-sheet; Scale key dropped (auto).

## Edge Cases & Error Handling

- Embedded template authoritative; library divergence → explicit push/pull/ignore notice (uuid + post-migration `modified` compare), never silent.
- Template/sheet mismatch → warn + built-in fallback (chain 3).
- Missing/corrupt image → bordered placeholder + warning; never a broken image on a plot.
- Corrupt library JSON → skip + warn. Library dir auto-created on first use.
- Overflow → wrap/grow/push; clip + warn at strip bottom; degenerate minimum blocks Save.
- No-template projects: byte-identical rendering to today (acceptance-tested).
- **(proposal)** Unknown `@[Key]` → literal + warning (never silently empty); known-but-empty → empty (never a literal token on a plot). Image band ≤ 0 → image hidden + warning. `Slot.field_id` not in `fields` (hand-edited file) → slot dropped with a load warning. Rev-2/rev-1 files migrate silently on load; save writes rev-3.

## Performance & Security

Solver runs per form change in the editor (tens of cells — trivial) and once per sheet rebuild; **(proposal)** drag feedback re-solves per mouse-move over the working dict (same trivial cost; no image decoding in the loop). Image base64 inflates `.fpd`/library files; acceptable. No external I/O beyond APPDATA + project file.

## Code Style & Testing

Conventions per CLAUDE.md (mm storage, `constants.py` for new literals; Google docstrings; relative imports). Tests (`tests/test_titleblock_template.py`, `tests/test_titleblock_editor.py`, **(proposal)** `tests/test_titleblock_arrange.py`, + `tests/test_paper_export.py` additions):

- **Solver unit:** stack math, row pairing, wrap/grow/push-down, clip warnings, validation floors, revision-row resolution; **(proposal)** remainder-band math (incl. band ≤ 0), sub-rect geometry, ≥1-placed-row + row-width floors.
- **(proposal) Token unit:** substitution, known-empty vs unknown-literal, malformed-token passthrough, warning lists, `build_field_values` key seeding.
- **Serialization:** template/library round-trip, embed round-trip, migration idempotence (**(proposal)** all four rev-2 kinds, paired chains, rev-2 seeded default, variants-era chain-through), divergence detection (incl. **(proposal)** old-format twin no-false-positive), corrupt-file skip.
- **Behavior:** editor Save/Cancel/snapshot-undo; `sheetModified` on Save and panel writes; resolution-chain selection incl. fallback + warning. **(proposal)** Widget-driven gesture tests — synthesized mouse press/move/release on the pool list and canvas viewport for place / reorder / pair / swap-sides / unpair / unplace, Esc-cancel (no snapshot), select + Delete-key unplace (ShortcutOverride accepted) — asserting the working dict and re-solved preview, not slots; public-canvas-API fallback only where a gesture provably can't be driven headlessly, justified per-test.
- **Export-render:** templated sheet → PDF, assert page + non-empty content; view-title mm-sizing regression. **(proposal)** Combined image+text cell renders in PDF output.
- Red-verify behavior tests where feasible (functional-over-source-inspection rule).

## Acceptance Criteria

Rev 1–2 (built, smoke-tested 2026-07-22): editor + library + apply-drives-sheet; Overview/Drawing Area/Info Strip tabs; parametric authoring incl. static/dynamic sizing; live preview + validation; sheet render + PDF/print at true mm; single-size template per project + mismatch fallback; panel/revisions/Project-Info value editing + legacy migration; `.fpd` embed authoritative + divergence notice; seeded default; suite green. (Checked boxes at `23fa804` — see git history.)

**Rev 3 (proposal — unchecked until built):**

- [ ] Fields tab: roster with placed indicators; New/Duplicate/Delete (delete warns when placed; also unplaces); intrinsics form (name, label, multi-line text + Insert field ▾ inserting `@[Key]` at cursor, image choose/clear + thumbnail, type combo, text style, fill, cell border); live single-field true-render preview; new fields start unplaced.
- [ ] Arrangements tab: three columns (pool cards | true-render strip canvas, fit-strip default zoom + wheel | placement props + strip border group); all DD-16 gestures work incl. Esc-cancel and select+Delete; overlays never alter the rendered item; inline warning banner.
- [ ] Token text: `@[Key]` resolves per DD-13 on sheet render, PDF export, editor previews; unknown keys render literally + warn; known-empty render empty.
- [ ] Combined cells: image + text stack per DD-15; logo-only and stamp (empty field) render identically to rev 2; image-no-room warns.
- [ ] Data model: `FieldDef` + `Slot` + `rows`; `pair_with_next` unrepresentable-invalid states gone; `image_position` reserved.
- [ ] Migration: any rev-1/rev-2 file (library or `.fpd` embed) loads and renders visually identical; save writes rev-3; idempotent; seeded default re-authored + `DEFAULT_SEED_MODIFIED` bumped; divergence uses post-migration stamps.
- [ ] Undo: one snapshot per completed gesture; cancelled drag none; undo restores fields+rows together.
- [ ] Validation: ≥ 1 placed row; `len(row) ≤ 2`; dangling `field_id` handled; field-key floor removed; unplaced note info-only.
- [ ] Test suite per §Code Style & Testing green; full suite green (chunked per OneDrive flake protocol).

## Verification Checklist

- [x] Rev 1–2 criteria demonstrated (user smoke test on a real project incl. plot) — at `23fa804`.
- [ ] **(rev 3)** All rev-3 acceptance criteria demonstrated (user smoke test incl. drag gestures on a real ANSI D template, token typo surfacing, yesterday's projects opening clean).
- [ ] **(rev 3)** No regression: rev-2 template projects render identically; no-template projects untouched; CEL chain intact.
- [ ] **(rev 3)** `sheetModified`/dirty contract honored for Save (§17.7).
- [ ] **(rev 3)** Spec re-audited: proposal markers removed, rev-2 remnants swept, `status: current`, `verified-commit` stamped at wrap-up; SPEC-INDEX `titleblock_arrange.py` row confirmed; TODO reconciled.
