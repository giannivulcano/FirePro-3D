---
status: proposal          # designed 2026-07-21, unbuilt
last-verified: 2026-07-21
verified-commit: 2a27d5d
applies-to:
  - firepro3d/titleblock_template.py   # (new) data model + layout solver + library I/O
  - firepro3d/titleblock_editor.py     # (new) editor window
  - firepro3d/paper_space.py           # TitleBlockTemplateItem renderer, resolution chain, view-titles
source-tasks:
  - "Title block template editor (TODO.md, P1 Architecture)"
  - "Fix latent point-size ~2.4× PDF over-sizing (view-titles folded in; TitleBlockItem remainder stays open)"
  - "Title block field overlay with measured positions (OBSOLETED — artwork path superseded)"
---

# Title Block Template System — Design Spec

Grill 2026-07-21 (scope, parametric-replaces-artwork, family model, storage, value scoping, save semantics, edge cases); design approved same day (approach A module trio; mockup-gated: arrangement A "Corporate top-down", filleted default corners).

## Goal

Users author **parametric title block templates** in a dedicated editor — margins, bordered areas with fillet/sharp corners, and a right-edge info strip built from a stack of typed cells — save them to a personal library, and apply **one template family per project**. Sheets render the template with live field values (project metadata, per-sheet values, auto fields) and export it vector-crisp at true paper-mm size.

## Motivation

The AHJ submittal package (MVP) plots through paper space. Today's title block is a hardcoded resolution chain (CEL DXF → PDF → programmatic) with field values painted at **hardcoded fractional positions** that don't match the DXF artwork, pt-sized text that exports ~2.4× oversized, and no way to customize anything. A firm must be able to put *its own* title block on issued drawings.

**V1 is parametric, not artwork-based.** The Revit-style free-form element editor and DXF-artwork field regions were considered (grill) and rejected for v1: DXF title blocks carry text as curves (no TEXT/MTEXT — see `project_dxf_titleblock_text_as_curves` finding), making artwork field-mapping a poor first investment. The parametric model covers real title blocks with far less machinery. Consequence: the "field overlay with measured positions" TODO item is **obsoleted**.

## Architecture & Constraints

Approach A — arm's-length module trio (read the model → emit results; never entangle into scene internals):

| Unit | Responsibility |
|---|---|
| `titleblock_template.py` (new) | Dataclasses (`TitleBlockTemplate`, `TemplateVariant`, `CellSpec`, `BorderStyle`), **layout solver** (`solve_layout`, `validate` — pure mm math, no QGraphics types), library I/O (`%APPDATA%/FirePro3D/titleblocks/`, `.fpd` embed, divergence compare) |
| `TitleBlockTemplateItem` in `paper_space.py` | QGraphicsItem painting a `SolvedLayout` + values; slotted at the **top** of the title-block resolution chain |
| `titleblock_editor.py` (new) | Modal editor window: form panel + live preview; working-copy Save/Cancel; snapshot undo |

Constraints:

- **One render path.** The editor preview hosts the *same* `TitleBlockTemplateItem` on a private scene; PDF export renders through the off-screen `PaperScene` rebuild unchanged (data-driven `_setup`, as with sheet text).
- **mm sizing invariant.** All template text uses the paper-space §9.4 primitive (`setPixelSize` + cap-height `setScale`); `setPointSizeF` is banned in this subsystem. Folded fix: viewport **view-titles** convert to the same primitive. The legacy `TitleBlockItem`/`TitleBlockFieldOverlay` pt sizing remains (fallback-only path) — tracked in TODO, not fixed here.
- **Dirty/undo contracts.** Template Save and per-sheet value writes follow paper-space §17.7 (`sheetModified`); value writes ride the paper `QUndoStack` (§17). Template *editing* has its own in-editor snapshot undo — model/paper undo stacks are untouched by editor sessions.
- **B&W independence.** The title block renders **as authored** always; the `paper_display` B&W/line-weight pipeline governs viewport content only.
- **Serialization.** Template + revisions ride `scene_io` only (paper space is not in `_capture_network` — matches existing behavior; see `project_dual_serialization_paths` memory: no second path to update).

## Design Decisions

1. **Parametric replaces artwork** (grill): a project with a template never renders the DXF/PDF chain; that chain remains solely as the no-template fallback. Built-in defaults stay untouched.
2. **Template = named family of per-paper-size variants; one family per project.** A sheet's paper size selects the variant. Missing variant → built-in default → programmatic fallback, with a warning (status bar + log).
3. **Form + live preview** editing (not direct manipulation) — smaller v1, precise `DimensionEdit` input; canvas grips can layer on later.
4. **One editor window does it all:** ribbon Draft tab → "Title Block" opens it (replacing the retired `TitleBlockDialog` binding). Inside: library picker + New/Duplicate/Delete, variant tabs (+ "Add size…"), parameter groups, cell list, **"Use for this project"**.
5. **Storage: user library + full embed.** Library file per template (`<uuid>.json`, logo embedded base64 → self-contained). The `.fpd` embeds the full template dict; **embedded copy is authoritative** on open. Divergence (same uuid, different `modified`) → explicit push/pull/ignore notice; never silent sync.
6. **Right strip only in MVP.** Strip position (bottom/top for portrait) is a filed future improvement; the data model reserves `strip_edge: "right"` so files stay forward-compatible.
7. **Seeded default template** (mockup-gated 2026-07-21): arrangement **A — Corporate top-down** (logo, company, project, address, title, paired Scale|Date, Drawn|Checked, Drawing No|Rev, revision table, stamp), **filleted** default corners (radius 10 mm) on drawing-area and strip borders.
8. **Overflow: keep text size, wrap, push lower cells down** — never shrink text. Clip + warn past the strip bottom; Save is blocked only when the *minimum* (unwrapped) stack can't fit.
9. **Value scoping** (grill): project-scoped = Company, Project, Address, Drawn By, Checked By; sheet-scoped = Title, Drawing No, Rev, Date (manual issue date). Auto = Scale (exists), `Sheet No` (reserved for multi-sheet), optional auto-Date.
10. **Rejected alternatives:** grow-`paper_space.py`-in-place (entangles layout math with paint in the biggest paper module); QTextDocument rendering (no mm/fillet/print control).

## Data Model

All dataclasses have `to_dict`/`from_dict`; unknown keys ignored on load (forward compat).

```python
@dataclass
class BorderStyle:
    visible: bool = True
    width_mm: float = 0.5
    color: str = "#000000"
    corner: str = "fillet"          # "sharp" | "fillet"
    fillet_radius_mm: float = 10.0

@dataclass
class CellSpec:
    kind: str                        # "field" | "static_text" | "logo" | "revision_table" | "stamp"
    field_key: str = ""              # field cells: key into the value model
    label: str = ""                  # small-caps label; "" = no label row
    static_text: str = ""            # static_text cells
    min_height_mm: float = 10.0
    pair_with_next: bool = False     # two-per-row; row height = max of the pair
    font_family: str = "Arial"
    cap_height_mm: float = 3.0       # value text; labels render at a fixed fraction
    bold: bool = True
    italic: bool = False
    alignment: str = "left"          # "left" | "center" | "right"
    fill_color: str = ""             # "" = no fill (per-section fill, user note 2026-07-21)
    border: BorderStyle = ...        # per-cell border (defaults: visible thin, sharp)
    logo_data: str = ""              # logo cells: base64 PNG
    logo_fit: str = "contain"
    revision_rows: int = 3           # revision_table: newest-first row count

@dataclass
class TemplateVariant:
    paper_size: str                  # key into PAPER_SIZES
    margin_edge_mm: float = 10.0     # paper edge → drawing area (all sides)
    margin_strip_mm: float = 5.0     # drawing area → info strip
    strip_width_mm: float = 90.0
    strip_edge: str = "right"        # MVP fixed; reserved for future bottom/top
    area_border: BorderStyle = ...   # drawing-area frame
    strip_border: BorderStyle = ...
    cells: list[CellSpec] = ...      # top-to-bottom

@dataclass
class TitleBlockTemplate:
    name: str
    uuid: str
    modified: str                    # ISO date; divergence compare key
    variants: dict[str, TemplateVariant]   # paper_size → variant
```

**Sheet additions** (`Sheet.to_dict`): `revisions: list[dict]` (`{"no": str, "description": str, "date": str}`); `title_block_fields` becomes an open dict (arbitrary keys allowed). **Project additions** (`scene_io` payload): `titleblock_template: dict | None` (the full embedded template).

**Library:** `%APPDATA%/FirePro3D/titleblocks/<uuid>.json`, directory created on first use. Corrupt/unparseable file → skipped with a warning; never crashes the library list.

## Layout Solver

Pure functions; QRectF/QFontMetrics allowed, QGraphics types are not.

- `solve_layout(variant, paper_w_mm, paper_h_mm, values: dict[str, str]) -> SolvedLayout`
  1. Drawing-area rect = paper − `margin_edge_mm` (all sides) − (`strip_width_mm` + `margin_strip_mm`) on the right.
  2. Strip rect down the right edge (full height inside margins).
  3. Cells walk top-to-bottom: start at `min_height_mm`; wrap the value text at cell width (QFontMetrics at cap-height-derived pixel size) → grow the cell and **push lower cells down** if wrapped height exceeds the minimum. `pair_with_next` → two half-width cells; row height = taller of the two. Revision table → header + `revision_rows` newest-first entries. Logo/stamp keep configured heights.
  4. Cells extending past the strip bottom are clipped at the border and flagged in `SolvedLayout.warnings`.
- `validate(variant) -> list[str]` — save-blocking floors: margins ≥ 0; `strip_width_mm` ≥ 20; drawing area ≥ 100 mm each dimension; `fillet_radius_mm` ≤ half the smaller bordered-rect dimension; ≥ 1 cell; field cells have non-empty `field_key`; the minimum (unwrapped) stack fits the strip.
- `SolvedLayout`: area/strip rects, per-cell resolved rects (label sub-rect + value sub-rect), wrapped text lines, warnings.

## Renderer & Resolution Chain

`TitleBlockTemplateItem(QGraphicsItem)` paints a `SolvedLayout`: fills → borders (`QPainterPath.addRoundedRect` when `corner == "fillet"`) → labels/values/static text (mm primitive §9.4) → logo pixmap (placeholder box + warning if `logo_data` missing/undecodable) → revision rows → stamp box (empty bordered area).

Resolution order in `PaperScene._setup` (supersedes paper-space §8.1):

1. Project template has a variant for the sheet's paper size → `TitleBlockTemplateItem`.
2. Project template exists but lacks the size → **warn**, fall to 3 (grill decision 2).
3. No template (or fallback): existing chain — DXF → PDF → programmatic (`TitleBlockDxfItem` → `TitleBlockPdfItem` → `TitleBlockItem`), unchanged.

Template Save re-renders open sheets and emits `sheetModified` (§17.7).

## Editor (`titleblock_editor.py`)

Modal window, ribbon Draft tab → "Title Block".

- **Left form panel:** template picker (library combo, New/Duplicate/Delete, "Use for this project"); variant tabs per paper size + "Add size…"; groups: Margins (`DimensionEdit`s), Area/Strip borders (visible, width, color swatch, sharp/fillet + radius), Cells — list widget (add/remove/reorder; per-cell expander: kind, field-key picker, label, min height, pairing, text style, fill color, border).
- **Field-key picker** groups: Auto (Scale, Date (auto), Sheet No — disabled until multi-sheet) / Sheet (Title, Drawing No, Rev, Date + free-typed new keys) / Project (8 standard Project Info keys + current custom rows, read live).
- **Right: live preview** — private `QGraphicsScene` + `TitleBlockTemplateItem`, re-solved per form change with sample values; inline warning banner (validation + overflow). Zoom-to-fit.
- **Session semantics:** working copy; **Save** = write library JSON + project embed + re-render + dirty; **Cancel** discards; **Ctrl+Z/Y** = snapshot stack of the working dict, one snapshot per form gesture (grid-dialog pattern). Save disabled while `validate()` is non-empty.

## Value Model & Editing Surfaces

Field-key resolution at render: **auto → per-sheet → Project Info (standard, then custom rows) → ""**.

- **Per-sheet values:** property panel when the rendered title block is selected on the sheet (duck-typed `get_properties`/`set_property`; writes ride the paper `QUndoStack`; §17.7 dirty). Plus **Edit Revisions…** panel button → No/Description/Date table dialog writing `sheet.revisions`.
- **Project values:** Project Information dialog only (existing surface).
- **`TitleBlockDialog` retires** along with its ribbon binding.
- **Migration on load** (legacy 9-key `title_block_fields`), one-way + idempotent, no visible change until a template exists: Company → Project Info custom "Company" *if absent*; Project → `name` *if empty*; Drawn By/Checked By → custom rows *if absent*; Title/Drawing No/Rev/Date stay per-sheet; Scale key dropped (auto).

## Edge Cases & Error Handling

- Embedded template authoritative; library divergence → explicit push/pull/ignore notice (uuid + `modified` compare), never silent.
- Missing size variant → warn + built-in fallback (chain 3).
- Missing/corrupt logo → bordered placeholder + warning; never a broken image on a plot.
- Corrupt library JSON → skip + warn.
- Overflow → wrap/grow/push; clip + warn at strip bottom; degenerate minimum blocks Save.
- Library dir auto-created on first use.
- No-template projects: byte-identical rendering to today (acceptance-tested).

## Performance & Security

Solver runs per form change in the editor (tens of cells — trivial) and once per sheet rebuild. Logo base64 inflates `.fpd`/library files; acceptable (single image, PNG). No external I/O beyond APPDATA + project file.

## Code Style & Testing

Conventions per CLAUDE.md (mm storage, `constants.py` for new literals — strip/margin/floor defaults; Google docstrings; relative imports). Tests (`tests/test_titleblock_template.py`, `tests/test_titleblock_editor.py` + additions to `tests/test_paper_export.py`):

- **Solver unit:** stack math, pairing, wrap/grow/push-down, clip warnings, validation floors, revision-row resolution.
- **Serialization:** template/library round-trip, embed round-trip, migration idempotence, divergence detection, corrupt-file skip.
- **Behavior:** editor Save/Cancel/snapshot-undo; `sheetModified` on Save and on panel value writes (undo-routed); resolution-chain selection incl. fallback + warning.
- **Export-render:** templated sheet → PDF (QPdfWriter), assert page + non-empty content (pattern of `test_paper_export.py`); view-title mm-sizing regression (no `setPointSizeF` in the viewport title path; rendered height ≈ spec'd mm).
- Red-verify behavior tests where feasible (functional-over-source-inspection rule).

## Acceptance Criteria

- [ ] Editor opens from Draft tab; create/duplicate/delete/save templates in the user library; "Use for this project" applies the family.
- [ ] Parametric authoring: margins, area/strip borders (fillet/sharp + radius, width, color), strip width; cell stack with add/remove/reorder, pairing, per-cell fill + border + text style; all five cell kinds render.
- [ ] Live preview updates per form change; validation + overflow warnings inline; Save blocked on floors; Cancel discards; in-editor Ctrl+Z/Y.
- [ ] Sheets render the template (right strip, arrangement per template) with resolved values; PDF export matches on-screen at true mm (view-titles included — no pt oversizing in new paths).
- [ ] One family per project; per-size variants; missing size → warning + built-in fallback; no-template projects render exactly as before.
- [ ] Values: panel edits sheet fields (undo-routed, dirties); Edit Revisions works; Project Info feeds project fields live; legacy fields migrate idempotently.
- [ ] `.fpd` embed authoritative; divergence notice offers push/pull; template survives save/load/crash-recovery (rides `_apply_loaded_file`).
- [ ] Seeded default: arrangement A, filleted corners, ANSI B + ANSI D + Letter variants.
- [ ] Test suite per §Code Style & Testing green; full suite green (chunked per OneDrive flake protocol).

## Verification Checklist

- [ ] All acceptance criteria demonstrated (user smoke test on a real project incl. plot).
- [ ] No regression: legacy project opens byte-identical (no template), CEL chain intact.
- [ ] `sheetModified`/dirty contract honored for Save, panel writes, revisions (§17.7).
- [ ] paper-space.md §8 updated to link here (Rule A); SPEC-INDEX row added; TODO items reconciled (editor done; overlay-obsoleted noted; pt-bug scoped down to legacy items).
- [ ] Spec re-audited + stamped (`status: current`, `verified-commit`) at wrap-up.
