---
status: partial            # frame axis + FontSelect + Frame group + fill model + annotation panel LANDED 2026-09-22; model-surface render + panel polish LANDED 2026-09-22 (feat/model-text-outline-render); style presets/SHX/overrides deferred
last-verified: 2026-09-22
verified-commit: af36ed6
applies-to:
  - firepro3d/text_item.py        # TextItem + TextAnnotationData (unified primitive + data model; frame + fill fields)
  - firepro3d/font_group.py       # ribbon "Text" group controller (FontGroupController)
  - firepro3d/frame_group.py      # ribbon "Frame" group controller
  - firepro3d/ui_kit.py           # FontSelect + custom panel inputs Selector/Stepper/Swatch
  - firepro3d/property_manager.py # shared property panel + render types + panel metric tokens (theme.M.PROP_*)
  - firepro3d/paper_display.py    # named line-weights (resolve_line_weight_mm / FACTORY_LINE_WEIGHTS) reused for the frame
source-tasks:
  - "todo_open.md → UI: Text primitives ribbon (frame axis / font widget) — 2026-09-21 brainstorm"
  - "todo_open.md → B: Sheet-text printed border property (None/Solid/Dashed) [P3] — absorbed by the frame axis"
  - "todo_open.md → B: Absorb the Modify→Text group into the entity-aware Font group [P3]"
  - "Downloads/Ribbon Text Group — Spec.md (draft, 2026-09-21) — seed for the deferred style-preset phase"
---

# Text Annotation System — Design Spec (forged on first touch)

> **Status: partial.** Forged 2026-09-21 to close the SPEC-INDEX orphan for the
> **Text primitive + Text ribbon** (previously split across `ribbon-bar.md`,
> `paper-space.md §9`, and `model-space-containment-contract.md` C5).
>
> - **CURRENT (code-verified):** the unified `TextItem` / `TextAnnotationData`
>   primitive (containment C5, landed) and the Word-style `FontGroupController`
>   ribbon group.
> - **PROPOSAL (designed here, unbuilt):** the **frame axis** (box border), the
>   separate **Frame** ribbon group + `FrameGroupController`, and the
>   **`FontSelect`** `ui_kit` widget.
>
> The **containment invariants** (Text is the 9th primitive, one data model,
> level-less, edited on paper + model surfaces) are owned by
> `model-space-containment-contract.md` (C5) — this spec links up and does not
> restate them (Rule A). Undo-routed paper-text writes are owned by
> `paper-space.md §9.6`. Named line-weights are owned by `paper_display.py`
> (`FACTORY_LINE_WEIGHTS` / `resolve_line_weight_mm`). Ribbon group/label/icon
> mechanics are owned by `ribbon-bar.md` and `icon-style-guide.md`.

## Goal

Give text annotations a **box-frame axis** (a printed border with visibility,
line-type, named weight, and corner style) and consolidate all text editing into
two ribbon containers on the Draft tab — a **Text** group (font/height/style/
color/justification) and a **Frame** group (the box/line controls) — with the
font picker promoted to a reusable `ui_kit` widget (`FontSelect`).

## Motivation

Sheet notes and callouts routinely need a printed box around the text (general
notes, keynotes, revision clouds' cousins). Today `TextItem` has only an
`opaque_bg` white knockout — no visible border, weight, line-type, or corner
treatment — and the ribbon exposes a single Word-style Font group built on a raw
`QFontComboBox` that can't carry font previews or (later) SHX entries. This slice
adds the frame and the reusable font widget; it is the buildable first cut of the
larger draft "Ribbon Text Group" vision (style presets / overrides / SHX), which
is **explicitly deferred** (see Deferred ledger).

## Architecture & Constraints

- **One primitive, one data model.** All text is `TextItem` backed by
  `TextAnnotationData` held by shared reference (C5). The frame is **four new
  fields on `TextAnnotationData`** — never a second entity or a parallel model —
  so the same data renders the frame on whichever surface (`PaperScene` device-
  independent, or `Model_Space`/Block-Editor scene-mm) the item sits on.
- **Reuse the named line-weight system.** The frame weight is a **named**
  line-weight (`"Very Light"`…`"Very Heavy"`, `FACTORY_LINE_WEIGHTS` in
  `paper_display.py`) resolved via `resolve_line_weight_mm()` — the same
  mechanism walls/pipes plot through. No second free-mm weight mechanism.
- **Reuse the commit/undo path.** Every ribbon/panel commit routes through
  `TextItem.set_property`, which already pushes a `FormatTextCommand` on a paper
  scene (`paper-space.md §9.6`) and does a plain geom2d set on a model scene.
  Multi-select edits wrap in one undo macro (as `FontGroupController` already
  does). The frame controls add keys to this path; no new undo machinery.
- **Two ribbon containers, vertical labels.** A **Text** group and a separate
  **Frame** group, each with a left-side vertical group label (the app's
  `_VLabel` chrome, `ribbon-bar.md`). `FrameGroupController` is a sibling to
  `FontGroupController` in its own module (`frame_group.py`) — one purpose per
  file.
- **`FontSelect` is a standard `ui_kit` widget.** Theme-tokenized
  (`theme.detect()`), governed by `ui-design-system.md`, with a documented
  **font-source seam** so a future SHX section slots in without a rewrite.

## Design Decisions

Decisions locked in the 2026-09-21 brainstorm (mockup:
`docs/mockups/ribbon-text-group.html`):

1. **Scope = frame axis + font widget first.** Style presets, per-property
   overrides, SHX fonts, and the launcher dialog are **deferred** to a later
   phase. The draft `Ribbon Text Group — Spec.md` is that phase's seed.
2. **Frame lives on all text** (paper + model), because C5 already unified the
   primitive — the fields are on `TextAnnotationData`, not paper-only.
3. **Weight = named paper line-weight category** (reuse), not a free mm value.
4. **Border color = the text color** — no separate border-color field this slice
   (a dedicated frame color can be added later without a migration: absence ⇒
   text color).
5. **No wrap toggle — text always wraps.** The box always has a width (from
   placement/resize); text wraps to it and the box auto-grows in height. This
   removes the old auto-width-vs-wrap ambiguity. (Any residual auto-width path
   in `TextItem` is normalized to always-wrap — see Divergences.)
6. **Corner = preset enum**, `square | round | chamfer`. *(Superseded 2026-09-22
   — see As-built "model-surface render + panel polish": the panel now exposes a
   **definable `border_corner_radius_mm`**; `0` falls back to the original fixed
   proportional radius `TEXT_FRAME_CORNER_FRAC` of the shorter box side.)* The **ribbon** expresses it as three
   mutually-exclusive icon buttons (**Square**, **Fillet**, **Chamfer** — a
   3-way radio, exactly one active, default Square); the **property panel** shows
   the same value as an **icon segmented control** (same three icons).
7. **Two separate containers** (Text, Frame) — the user's explicit layout, over
   folding the frame into the Text group as a third row.
8. **Fill = colour + opacity, not a bool** (2026-09-21 panel design). The legacy
   `opaque_bg: bool` (white knockout) evolves into a real box fill: a **fill
   colour** (none = transparent) and a **fill opacity** 0–100%. Absorbs the
   "Colored highlight for sheet text" todo.
9. **Annotation-text panel is grouped** (Text / Format / Frame / Fill), with
   Font + Height in Format, Height shown as a **bare number (no unit)**, and the
   font/fill colours + opacity added — see the Property-panel section.

## Data model

Four new fields on `TextAnnotationData` (`text_item.py`), all with back-compat
defaults so pre-existing `.fpd` files load with the border off:

| Field | Type | Default | Notes |
|---|---|---|---|
| `border` | `bool` | `False` | Frame visibility. |
| `border_weight` | `str` | `"Light"` | Named line-weight → `resolve_line_weight_mm()`. |
| `border_line_type` | `str` | `"solid"` | `solid` \| `dashed` \| `dotted` \| `dashdot`. |
| `border_corner` | `str` | `"square"` | `square` \| `round` \| `chamfer`. |

**Fill fields (panel phase — evolve `opaque_bg`):**

| Field | Type | Default | Notes |
|---|---|---|---|
| `fill_color` | `str` | `""` | Box fill colour hex; `""` = no fill (transparent). |
| `fill_opacity` | `float` | `100.0` | Fill alpha as a percentage 0–100. |

- `color` (existing) is the **font colour**; `fill_color` is the box fill — two independent colours.
- **`opaque_bg` migration:** `from_dict` maps a legacy `opaque_bg=True` → `fill_color="#ffffff", fill_opacity=100`; `False`/absent → `fill_color=""`. The `opaque_bg` field/rows are removed from the data model, `paint`, panels, and the paper `_TEMPLATE_FIELDS`/migration/capture sites (grep `opaque_bg` — 12 sites). `paint` fills the box with `QColor(fill_color)` at `fill_opacity/100` alpha when `fill_color` is set (replacing the white knockout).
- `to_dict` / `from_dict` gain all four border fields plus the two fill fields (`from_dict` uses `.get(..., default)`).
- **Dual-serialization parity:** the fields are added to *both* the file path
  (`TextItem.to_dict`/`from_dict`, consumed by `scene_io`) **and** whatever
  undo-capture path serializes text records — verified before merge
  (`project_dual_serialization_paths`).
- Border color is **not** stored (decision 4) — the renderer reads `data.color`.

## Rendering

In `TextItem.paint`, after the `opaque_bg` knockout and the text (and inside the
existing bake-at-rest rotation `save()/restore()` block), when `data.border`:

1. Build a `QPainterPath` for `_box_rect_local()` with the corner treatment:
   **square** = plain rect; **round** = quarter-arc fillets; **chamfer** = 45°
   cut. Corner size = `TEXT_FRAME_CORNER_FRAC × min(box_w, box_h)` (local units).
2. Stroke with a `QPen`: color = `QColor(data.color)`; width = the local-frame
   mapping of `resolve_line_weight_mm(data.border_weight)` so the border **plots
   at the true mm weight** on paper (divide by `scale()` like the other paper
   pens) and renders at mm in scene units on a model surface; line-type →
   `Qt.PenStyle` / dash pattern; `NoBrush`.
3. The frame path is inside the same rotation transform as the text, so it
   tracks the box on rotate.

`boundingRect`/`shape` already pad for the grip halo and cover the full box, so
the stroked border needs no extra bounds growth (its half-weight is ≤ the grip
pad at real weights).

## Ribbon layout

**Text group** (`FontGroupController`, `font_group.py` — existing, two rows):
- Row 1: `FontSelect` · Height field + spinner.
- Row 2: B / I / U · color swatch · L / C / R (standard align icons).
- Vertical "Text" label at left; launcher ⛭ stub (deferred style manager).

**Frame group** (`FrameGroupController`, `frame_group.py` — NEW):
- Row 1: `[Border] | [Square] [Fillet] [Chamfer]` icon buttons — Border toggles
  visibility; Square/Fillet/Chamfer are a 3-way corner radio (exactly one active,
  default Square).
- Row 2: Line-type combo.
- Row 3: Line-weight combo (named categories).
- Vertical "Frame" label at left. Corner radio + combos disable when Border off.

**Icons (NEW, mockup-gated):** four SVGs — `text_border`, `corner_square`,
`corner_fillet`, `corner_chamfer` — authored through the render-through-loader
harness at light+dark per `icon-style-guide.md`, gated before wiring.

Both controllers commit through `TextItem.set_property` with the keys
`Border`, `Border Weight`, `Line Type`, `Corner` added to `_text_panel_change`,
`_text_panel_properties` (paper form) and the model `get_properties`/
`set_property` branches, plus property-panel rows.

## FontSelect (ui_kit widget)

`class FontSelect(QComboBox)` in `ui_kit.py`, theme-tokenized:

- **Model:** TrueType families from `QFontDatabase`, with **section headers** and
  a documented **font-source seam** (a source list → sections) so an SHX source
  slots in later. Ships TrueType-only.
- **Item delegate:** family name left, preview `"AaBb 0123"` rendered **in that
  face** right.
- **Behavior:** type-ahead search; recently-used pinned at top (max 5); checkmark
  on the current family. Emits `fontChanged(str family)`.
- `font_group.py` swaps its raw `QFontComboBox` → `FontSelect`. Other
  `QFontComboBox` sites (`titleblock_editor.py`, `property_manager.py`) may
  migrate later — **not** in this slice.

## Property panel (annotation text)

The panel phase (2026-09-21, mock `docs/mockups/property-panel-text.html`) makes a
selected `TextItem`'s property panel the editing surface for **model / Block-Editor
text** (the ribbon Text/Frame groups stay paper-scoped). The panel wiring already
exists and is generic — the Block-Editor scene routes `selectionChanged →
update_property_manager` and `requestPropertyUpdate → show_properties`, and
`PropertyManager._show_properties_inner` renders any item's `get_properties()`. So
the work is in **`TextItem.get_properties()` (model branch)** + **new
`property_manager` render types**.

**Grouped form** (`get_properties` emits `header`-type rows):

- **Text** — Content.
- **Format** — Font · Height · B/I/U · Alignment · Font colour.
- **Frame** — Border · Corner · Line type · Line weight.
- **Fill** — Fill colour · Opacity (0–100%).

**New/changed panel render types in `property_manager.py`:**

- **`icon_enum`** — a segmented icon-button control (exactly-one-active) for
  **Corner** (Square/Fillet/Chamfer, reusing the frame icons). Each option carries
  an icon name; commits the chosen value via `_apply_property`.
- **B/I/U as a compact button group** — the three bool keys render as pressable
  buttons (not three sliding switches).
- **`number`** — Height as a **bare integer field, no unit** (not the mm
  `dimension` formatter). Value is the pixel-size the panel shows/parses.
- **`percent`** — Opacity as a 0–100 slider with a `%` readout, bound to
  `fill_opacity`.
- **`color`** (existing) — used for both **Font colour** (`color`) and **Fill
  colour** (`fill_color`). Fill Color rows emit `"allow_none": True` and pass the
  raw `fill_color` (no `or "#ffffff"` masking), so `ui_kit.Swatch` offers the house
  picker's **No Fill** chip and shows the No-Fill glyph + "None" when empty
  (todo #70; picker contract in `ui-design-system.md` D6).

Frame rows disable when `border` is off; the Opacity row disables when
`fill_color` is empty (none) — via the generic `meta["disabled"]` flag in
`property_manager` (model + paper panels). Picking No Fill leaves `fill_opacity`
untouched. Like every panel row, `disabled` is computed from the first selected item. Commits route through `TextItem.set_property`, and on
the model/Block-Editor surface the scene snapshots for undo (paper keeps
`FormatTextCommand`). The model-branch `TextItem.set_property` pushes **one**
post-change `scene.push_undo_state()` per commit, and only when `to_dict()` changed.
This landed in the 2026-09-22 todo #70 smoke fix; before it, the model branch never
snapshotted, and Ctrl+Z reverted the placement.

## Inline edit (model surface) — PROPOSAL (2026-09-22 grill + design)

> Status: **proposal, unbuilt** (branch `feat/model-text-inline-edit`). Scope =
> model plan views, detail views, and the Block Editor. **The model-surface
> primitive sets the edit contract; paper text conforms later** (filed follow-up —
> paper keeps its current edit behaviour until then). Out of scope: model text seen
> through a paper viewport, elevation/3D, per-character formatting (own todo).

### Goal

Double-click a model / Block-Editor `TextItem` and type **live, inline, in the
scene** — visible caret + selection, keys owned by the editor, one undo step per
edit session.

### Motivation

The panel Content box is the only model-text edit path today. Inline edit is
blocked by (a) the live engine-less-device bug — `super().paint()` (the
`QGraphicsTextItem` document renderer, which draws the caret) renders nothing on
the live viewport (see As-built todo #62); and (b) key hijack — app shortcuts fire
while typing.

### Behaviour contract (locked, Phase-2 grill)

- **Entry:** double-click inside the box's rotated rect in Select mode (selected
  or not, including over the manipulator frame interior; a manipulator *handle*
  wins) → edit, caret at the click. **Enter / F2** with exactly one editable text
  selected → edit, caret at end. Inert while a placement tool is active. Only
  top-level, visible, selectable `TextItem`s are candidates (block-contained text
  is edited in the Block Editor).
- **Exit = commit, always** (no cancel key; Ctrl+Z reverts afterwards): Esc,
  Ctrl+Enter, press outside the box, `set_mode` (tool switch / ribbon command),
  modal dialog, plan-tab / level switch, Block Editor enter/leave, save / save-as /
  autosave / export / plot, close. **Enter = newline.** Window deactivation
  (Alt+Tab) and popups do **not** commit.
- **Key ownership while editing:** every key belongs to the editor except the
  commit keys and **Ctrl+S** (commits, then saves). Letters/Space type; arrows /
  Home / End / Ctrl+arrows move (Shift extends); Tab inserts a tab; Delete /
  Backspace edit chars; Ctrl+A/C/X/V act on text; Ctrl+Z/Y are the editor's own
  typing history. Ctrl+B/I/U and F1–F12 are swallowed (inert).
- **Undo:** one scene step per edit session, pushed at commit only if `to_dict()`
  changed. Place + type + commit = **one** step (no placeholder step). Panel /
  grip changes during an edit are their own steps and never capture uncommitted
  text.
- **Empty:** a new placement starts **empty** (no literal "Text") with the caret
  showing; committing it empty discards it (no step). Committing an existing box
  emptied **deletes** it (one step; Ctrl+Z restores).
- **Visuals / mouse:** blinking caret in the font colour (visible at all zooms, on
  any fill, rotated); accent selection highlight; click / drag-select /
  double-click word / triple-click line / Shift+click / native Cut-Copy-Paste
  menu; live reflow + auto-grow height. **No distinct edit frame** — the normal
  selection frame + grips stay live: grips resize/rotate mid-edit (text reflows,
  edit continues); a body drag inside the box **selects text** (not move).
- **Property panel stays live** during an edit; format changes apply to the whole
  box without ending it.

### Architecture & Constraints

- **Self-paint on the model surface (Decision IE1).** The model branch of
  `TextItem.paint` **never calls `super().paint()`**. The Qt text control still
  owns all editing *logic* (`TextEditorInteraction`: cursor, selection, clipboard,
  typing undo, word/line clicks) and its state is read from `textCursor()`; only
  the *painting* is ours. This completes the todo #62 principle — the model
  surface renders exclusively through direct painter ops that work live — and
  removes the `engine==0` spam source. The Qt root cause is filed as a separate
  low-priority diagnostic, relevant only if a model-surface text item ever needs
  Qt's own document rendering again.
- **One line-geometry helper (GENERALIZE).** The per-line origin math in
  `_glyph_outline_local()` (block offset + manual horizontal-align offset +
  vertical-align slack — Qt keeps every `QTextLine` at x==0) is extracted to
  `_line_origin(block, line) -> (x, y)`; glyph outlines, caret, and selection all
  use it so they cannot drift.
- **One key-ownership predicate.** `editing_text_item(scene)` (module function in
  `text_item.py`) returns the live, editing `TextItem` from `scene._editing_item`
  or `None`. It is the sole "editor owns the key" test for every layer below;
  paper space's inline `_editing_item` checks migrate onto it (paper *behaviour*
  unchanged).
- **One commit funnel.** `Model_Space.commit_text_edit()` (idempotent) is the only
  path that ends a model edit session; every trigger calls it.

### Design

**Key routing (3 layers).**
1. `Model_View.event`: while `editing_text_item(scene)`, **accept every
   `ShortcutOverride` except Ctrl+S** — Qt then delivers a plain KeyPress instead
   of firing any window `QShortcut` (bare `B`, `/`, `Shift+A`, Delete, Escape,
   Ctrl+Z/Y/C/V/A/D/O/N, F3, F11 in `main.py`), ribbon, or `QAction` shortcut.
   `save_file` calls `commit_text_edit()` first.
2. `Model_View.keyPressEvent` and 3. `Model_Space.keyPressEvent`: first statement —
   if editing, bypass to the default handler (skips tool letters, Home, Tab→HUD,
   ←/→ variant cycle, Space ambiguity cycle, polygon ↑/↓). `QGraphicsScene` then
   delivers the key to the focused `TextItem`.
4. `TextItem.keyPressEvent` (editing): Esc / Ctrl+Enter → commit; Ctrl+B/I/U and
   F1–F12 swallowed; everything else → Qt text control. Not editing: Enter/F2
   entry lives in `Model_Space.keyPressEvent`'s non-editing branch.

Detail views inherit via `Model_View`; the Block Editor inherits if its view is a
`Model_View` (verify in the plan).

**Mouse routing.** A gate at the top of `Model_Space` press / move / release /
double-click, ahead of the manipulator / HALO / per-mode dispatch:
- *Entry* (Select mode, double-click inside a candidate's rotated box, not on a
  handle): `begin_edit()`, then place the caret by mapping the scene point into the
  **unrotated local layout frame** (the item's composed map overrides) and
  `documentLayout().hitTest()`.
- *While editing:* press inside the box and not on a handle → forwarded to the
  `TextItem` as a text-control mouse event with the position **rewritten to
  unrotated local** (Qt cannot see the baked rotation); the item grabs the mouse so
  move/release follow; double/triple-click word/line selection comes free. Press
  on a handle → manipulator (resize/rotate), then keyboard focus is restored to
  the item (click-focus lands before handlers). Press outside the box →
  `commit_text_edit()`, then normal handling of the same click.

**Commit triggers + focus policy.** `commit_text_edit()` is called from: Esc /
Ctrl+Enter / outside press; the top of `set_mode()`; and in `main.py` the tops of
save / save-as / autosave / export / plot / plan-tab switch / level switch / Block
Editor enter-leave / `closeEvent` (the plan greps every entry point). On the model
surface `TextItem.focusOutEvent` commits **unless** the reason is
`ActiveWindowFocusReason` / `PopupFocusReason`, the new focus widget is inside
the `PropertyManager` (panel stays live), or focus stays within one of the
scene's own views (an in-scene focus-item change, e.g. a manipulator-handle press —
in-scene clicks are owned by the mouse gate, which commits explicitly on an
outside press). A modal takes focus → commits. Paper
focus-out behaviour unchanged.

**Undo.** Session start records `before = to_dict()` and `is_new_placement`.
`_press_text` **no longer pushes a snapshot** and creates the item with empty text.
At commit: new + empty → remove item, no push; existing + empty → delete via the
normal delete path + one push; else push once iff `to_dict() != before`. Mid-edit
panel/grip snapshots cannot capture typed text because `_data.text` is written
only at commit (guard test pins this). Undo / redo / `_restore_network` call
`commit_text_edit()` first (safety net; Ctrl+Z cannot reach scene undo while
editing). `_delete_single_item` on the editing item ends the session without a
commit (clears `_editing_item`, releases focus).

**Painting (model branch, inside the rotated save/restore).** Order: fill →
**selection highlight** (per line overlapping the selection: rect from
`line.cursorToX(start)` to `cursorToX(end)` × line height, theme `selection` token
≈40% alpha, behind glyphs) → glyph outlines → **caret** (when blink-on: vertical
line at `cursorToX(pos)` spanning the line height, **font colour**, cosmetic 1.5 px;
empty doc → first-line origin with font-metric height) → border. The dashed
`#88aaff` edit frame is **removed**. **Blink:** a per-item `QTimer` at
`QApplication.cursorFlashTime()/2`, started by `begin_edit`, stopped at commit;
repaints only the caret rect; any key / cursor / selection change resets the phase
to on.

### Acceptance Criteria

- [ ] Every Behaviour-contract bullet above holds on a plan view, a detail view,
      and the Block Editor.
- [ ] While editing, bare letters / Space / arrows / Tab / Home / Delete / Ctrl+A/C/V
      / Ctrl+Z land in the document and leave tool mode, scene selection, scene
      items, and the scene undo stack unchanged; when NOT editing they keep their
      app meaning (negative path from the default state).
- [ ] Caret + selection highlight render with `QGraphicsTextItem.paint` a no-op
      (the live failure mode), correctly placed for L/C/R, T/M/B, and rotated.
- [ ] No `engine==0` / `Painter not active` output while editing live.
- [ ] Undo counts: place+type+commit = 1 step; no-op edit = 0; empty new = 0 and
      no item; empty existing = 1 (Ctrl+Z restores); mid-edit panel change stores
      the pre-edit text.

### Verification Checklist

- [ ] Routing / entry / commit / undo / empty guards drive a **shown** `Model_View`
      with posted events (shortcuts via `windowHandle()`); each shown RED with its
      fix reverted.
- [ ] Pixel guards (caret / highlight) RED when the caret is routed back through
      `super().paint()`.
- [ ] Full suite once, chunked (full-suite crash playbook).
- [ ] **Live smoke signed off by the user** (caret visible + blinking, highlight,
      typing echo, grips mid-edit, Alt+Tab keeps the edit) — headless green alone is
      not done for this live-only class.

## Acceptance Criteria

- [ ] `border`/`border_weight`/`border_line_type`/`border_corner` exist on
  `TextAnnotationData` with the defaults above; `to_dict`/`from_dict` round-trip;
  a pre-frame `.fpd` loads with `border == False`.
- [ ] Frame renders per corner (square/round/chamfer), line-type, and named
  weight on **both** a paper and a model `TextItem` — driven through
  `set_property` on real domain objects; each guard shown RED with the paint
  branch reverted.
- [ ] Border color follows `data.color` (no separate field).
- [ ] Frame commits are undo-routed (one `FormatTextCommand` per commit on
  paper; multi-select wraps in one macro) and sync to the property panel.
- [ ] `FontSelect` emits `fontChanged`, previews in-face, pins ≤5 recents,
  type-ahead selects, checkmarks current — driven as a **widget**, not slots.
- [ ] The border **plots** at its named mm weight at export scale (the exported
  artifact, not on-screen, is the gate).
- [ ] Text always wraps to its box (no wrap control); box auto-grows in height.
- [ ] **Fill model:** `fill_color` + `fill_opacity` on `TextAnnotationData`
  round-trip; legacy `opaque_bg=True` migrates to `fill_color="#ffffff",
  fill_opacity=100`; `paint` fills the box with `QColor(fill_color)` at
  `fill_opacity/100` alpha; no `opaque_bg` references remain.
- [ ] **Annotation panel:** selecting a model/Block-Editor `TextItem` shows the
  grouped form (Text/Format/Frame/Fill) with the new render types (`icon_enum`
  Corner, B/I/U buttons, bare-number Height, `percent` Opacity, font+fill colours),
  driven as widgets; edits apply to the item and are undo-reversible on that scene.

## Verification Checklist

- [ ] All acceptance criteria met.
- [ ] Tests pass (headless unit + a paper-export render assertion for the weight).
- [ ] No regressions in existing `TextItem` paint / edit / manipulator behavior.
- [ ] Launch-smoke: Draft tab shows Text + Frame groups; frame controls drive a
  live model-space and paper-space text (live-only render classes dodge headless
  — `project_live_render_bugs_dodge_headless`).
- [ ] Four Frame icons gated + wired; render-through-loader test green.

## Deferred / Divergences ledger

- **D1 — Style presets + per-property overrides.** The draft spec's `TextStyle`
  bundle + override model is deferred. Seed: `Downloads/Ribbon Text Group —
  Spec.md`. The launcher ⛭ opens this manager when built.
- **D2 — SHX fonts.** `FontSelect` ships TrueType-only behind a font-source seam;
  the SHX section + stroke-font preview pixmaps land with D1.
- **D3 — Separate border color.** Absent ⇒ text color; a dedicated field can be
  added later without migration.
- **D4 — Always-wrap normalization.** Today `TextItem` treats `wrap_width_mm == 0`
  as auto-width (no wrap). Decision 5 makes text always wrap; the implementation
  normalizes placement/resize so a width is always present. Any code path that
  still emits `wrap_width_mm == 0` for a live box is a divergence to close in the
  build, not a supported mode.
- **D5 — Absorbed todo items.** "Sheet-text printed border (None/Solid/Dashed)"
  is superseded by this frame axis (richer: weight + corner). "Colored highlight
  for sheet text" (`opaque_bg → background color`) is absorbed by the Fill model
  (colour + opacity). "Absorb Modify→Text group into the entity-aware Font group"
  overlaps the ribbon consolidation and should be reconciled when that item is
  picked up (it is the "extend the paper-only ribbon to model text" follow-up).
- **D6 — Ribbon stays paper-scoped.** `_font_group_targets` (main.py) returns
  targets only on a `PaperSpaceWidget`, and only `paper_scene.selectionChanged`
  drives `_update_font_group_context`. So the ribbon Text/Frame groups edit **paper
  text**; **model / Block-Editor text is edited via the property panel** (panel
  phase). Extending the ribbon to model text needs the model-scene selection wiring
  + undo routing (the D5 "entity-aware Font group" item) — deferred.

## As-built (2026-09-22, `feat/text-annotation-frame`, 33 commits)

Landed: the frame axis (border/line-type/named-weight/corner) on `TextAnnotationData`
+ `TextItem.paint`; the **fill model** (`fill_color`/`fill_opacity`, `opaque_bg`
migrated); `FontSelect`; the **Frame** ribbon group + 4 authored icons; and the
**grouped annotation property panel** (Text/Format/Frame/Fill) on the shared
`PropertyManager`. Panel inputs were rebuilt as **custom self-painted `ui_kit`
widgets** — `Selector` (dropdown), `Stepper` (spinner), `Swatch` (colour+hex) —
because the native `QComboBox`/`QSpinBox`/`QPushButton` chrome fought styling
(arrows dropping, drop-down tone, inconsistent widths). Panel styling was split
onto two widgets (panel bg on the PM via bare `background`+WA_StyledBackground;
field/button tones on the inner `form_container`) — a widget can't paint its own
bg AND style its children from one sheet. All panel metrics are tokenized in
**`theme.M.PROP_*`** (single source of truth for every entity panel).

## As-built (2026-09-22, `feat/model-text-outline-render`, todo #62)

Resolved the P1 "annotation text box doesn't render its panel settings" — which
live investigation revealed was **model-surface text rendering nothing at all**
(only the HALO boundary showed). Root cause: `super().paint()` (the
`QGraphicsTextItem` document renderer) produces no output on the live viewport's
engine-less device (the pre-existing engine==0 bug — UI-follow-ups §L75-76), while
direct painter ops (the box fill) draw fine.

Landed:
- **Model/Block-Editor text renders via filled glyph outlines.** `TextItem.paint`
  now draws model-surface text with `painter.fillPath(_glyph_outline_local(), color)`
  (the same painter-fill path that works live), not `super().paint()`. Paper text
  keeps the document renderer (works on the paper device). `_glyph_outline_local()`
  (unrotated) was extracted from `render_outline_path()` (block-compile, still
  pre-rotated) and now also applies the **horizontal alignment** offset manually
  (Qt keeps every `QTextLine` at x==0 and aligns only at draw time — L/C/R was a
  no-op before) and the **vertical alignment** offset within the box-height slack.
- **New `TextAnnotationData` fields** (all serialized both ways): `valign` (T/M/B),
  `cell_padding_mm` (was the fixed `TEXT_BOX_MARGIN_MM`), `border_corner_radius_mm`
  (0 = the proportional default — **reverses Design Decision 6's "no radius field"**).
  Panel rows added: V Align (`icon_enum` + authored `align_top/middle/bottom.svg`),
  Padding, Corner Radius.
- **Border pen is cosmetic on the model surface** (constant device width at all
  zooms, matching the sibling 2D primitives; named weight → device px via
  `_BORDER_WEIGHT_PX`), true-mm on paper.
- **Model-placement defaults** (`_press_text`, real-size scene mm): white ink,
  `DEFAULT_MODEL_TEXT_HEIGHT_MM=100`, solid border on, `border_weight="Medium"`,
  `DEFAULT_MODEL_TEXT_PADDING_MM=15`. Paper defaults unchanged (3/16", black, 1 mm).
- **Font-constant resize.** Model text drops the `"scale"` manip capability
  (surface-aware via `is_device_independent()`), so a corner drag resizes the box
  via the live parametric grips (`apply_grip`, font untouched) instead of the
  box-native uniform-transform preview (which scaled the glyphs and snapped back).
  Paper text keeps its tested box-native scale path.

**Remaining known issues (P1 follow-ups, filed in todo_open):**
- **Inline double-click edit** on the model surface — *designed 2026-09-22, see
  "Inline edit (model surface) — PROPOSAL"; build on `feat/model-text-inline-edit`.*
  The display renders, but the
  edit **caret** still hits the L75-76 engine-less-device paint bug; needs its own
  root-cause.
- ~~Custom colour-picker widget with "No Fill"~~ — **LANDED 2026-09-22**
  (`feat/colour-picker`, todo #70): true `fill_color=""` No Fill replaces the
  0%-opacity stopgap on both surfaces.
