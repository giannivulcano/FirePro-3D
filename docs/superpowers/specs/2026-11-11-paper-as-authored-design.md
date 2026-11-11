---
status: built  # 0.99.0, feature/paper-as-authored
last-verified: 2026-11-11
verified-commit: e2d57467   # paper-as-authored Account (built 0.99.0); prior e7ac8f15 (branch base, design time)
applies-to:
  - firepro3d/paper_display.py
  - firepro3d/colour_tokens.py
  - firepro3d/colour_picker.py
  - firepro3d/display_manager.py
  - firepro3d/ui_kit.py
source-tasks: ["todo_open.md: Paper Space \"As Authored\" per-row toggle: remove the Color Mode dropdown [P2]"]
---

# Paper Space "As Authored" per-row toggle — Design Spec

Ratified inputs (do not re-ask): the task line's rulings (1)-(6), the Phase 2
grill G1-G6 and AC1-AC7 (all on the task line in `todo_open.md`), and the
Phase 3 rulings R1-R5 below.

## Goal

Every Display Manager Paper Space row (except Hatch) gets an **As Authored**
toggle. ON: the row's items plot on sheets / PDF / print in their own
(authored) colours. OFF: the row's Colour / Fill / Section are painted over
them. The global Color Mode dropdown (Full Color / B&W / Custom) is removed;
the per-row toggle plus its chips is the whole model.

## Motivation

Under B&W / Custom the paper pass paints one category colour over every item
of a row, so authored block colours, WM3 placement Colour overrides and loose
Construction primitives lose their colour; Full Color is all-or-nothing. A
per-row choice lets a sheet keep coloured blocks while pipes plot black.

## Architecture & Constraints

- The paper pass (`paper_display.apply_paper_overrides` /
  `restore_model_display`) stays the single place paper colours are applied;
  screen, PDF export and print share it, so parity is structural.
- Paper categories keep their current store (QSettings `paper/categories/*`,
  copied into / out of the project file's `paper_display`). The QSettings
  live-store bug (`todo_open.md` "Paper categories use QSettings as the live
  store") is **not** fixed here; `as_authored` is one more category property
  and rides along when that bug is fixed.
- Colour tokens resolve per paint (HF1, `docs/specs/hatch-and-fill.md`);
  token values are owned by `firepro3d/constants.py`.
- Paper colours and the pass contract: `docs/specs/paper-space.md` (§9.9 and
  the colour-tokens-on-paper clause). Blocks row: `docs/specs/linetypes.md`
  LT1-2 and WM3 D3/D5.

## Design Decisions

**D1 — Approach A (R3): `as_authored` is a field of each paper category.**
Each category dict gains `"as_authored": bool`, saved / loaded / snapshotted
with the row's other properties. `apply_paper_overrides` reads it per row.
Rejected: B (keep `PaperColorMode` per row — dead enum value, fails AC7's
grep); C (separate key->bool store — second store to keep in step).

**D2 — Rows.** Every `_CATEGORY_KEYS` row except Hatch (`_LW_ONLY`) has the
toggle. The Drafting group lists Hatch, Blocks, Underlay, Construction. A new
**"Underlay"** row joins `_CATEGORY_KEYS` there with the toggle and Colour only; its Visible, Fill,
Section, Line Weight and Opacity cells are disabled (R2) — underlay layers
keep their own weights and visibility. *(2026-11-11, VC9 fix round, user
ruling, commit 5b507783: the existing "Construction" row is now shown in the
Display Manager Drafting group, after Underlay; it was in `_CATEGORY_KEYS` but
unlisted in `_PS_GROUPS`. It carries the toggle and its other cells like any
other toggled row.)*

**D3 — Factory (new install / no stored value; G1, G6).** Every row ON.
Paper row Colour and Section = `token:auto`, Fill = `token:bg`; Underlay
Colour = `token:auto`. Model tab factory: Hydraulic Badge colour `#ffffff` ->
`token:auto`; fills `#000000` (Sprinkler), `#2b2b2e` (Water Supply),
`#2b2b2b` (Hydraulic Badge) -> `token:bg`. Every other Model factory colour
is unchanged (Wall stays `#666666` / `#999999` — the grill's "Wall #ffffff"
example was not the factory). Stored colours (QSettings, project files) are
never rewritten.

**D4 — Legacy load (G2, G3).** One function maps a legacy `color_mode`
string to per-row toggles, used only where a row has no stored
`as_authored`:

| Legacy mode | Rows | Underlay row |
|---|---|---|
| `full_color` | ON | ON |
| `custom` | OFF | ON |
| `bw`, missing `paper_display`, missing / unknown `color_mode` | OFF | OFF |

Rows keep their stored colours, so OFF rows plot exactly as before. A
missing row (Underlay in every old file) is backfilled from the factory
(`token:auto`), which plots black on paper — the same as today's B&W
underlay black.

**D5 — QSettings migrates once.** When `load_paper_categories` finds no
stored `as_authored` and the legacy `paper/color_mode` key exists, it derives
the toggles per D4, writes them, and removes `paper/color_mode`. With
neither present, rows are factory ON. Nothing writes `color_mode` again;
`get_paper_display_for_save` stops emitting it. Known one-way limitation: a
pre-change build opening a new file finds no `color_mode` and plots it B&W.

**D6 — Paper pass (per row).** `authored = cat["as_authored"]` replaces
`color_mode` in every `_apply_*` helper and inline branch: today's Full Color
branch is the ON branch, today's B&W / Custom branch is the OFF branch,
unchanged. Labels, bubbles, heads and section / elevation proxies follow
their owner row, as today.
- **Blocks:** ON -> authored op colours (`_paper_pen_color = None`) and
  `token:blocks` plots the Model "Blocks" colour resolved on paper (ruling 6);
  OFF -> the row colour for both.
- **Underlays:** ON -> each layer's effective colour; OFF -> the Underlay
  row colour (today: B&W forces `#000000`, Custom keeps layer colours).
- **SVG symbols (R6, replaces the Phase 3 "re-tint guard"):** with a row ON,
  an SVG category item (Sprinkler, Fitting, Water Supply, Hydraulic Badge)
  re-tints on paper when its effective Model colour **or fill** (own
  override, else the Model category value) is a token, each token resolved
  on the paper surface (Automatic -> black, Background -> white, Accent ->
  the light-theme accent); a hex half keeps its canvas value. With neither a
  token, the canvas tint plots unchanged (today's Full Color). The Phase 3
  guard ("re-tint only when `display/<key>/color` is saved") was dropped: a
  probe found `apply_default_display_settings` (`main.py` startup) writes
  that key for every category, and the canvas tints every SVG item at load.

**D7 — Tokens (R1, G5).** `colour_tokens._paper_mode` becomes a boolean
"painting on paper" check (built as `colour_tokens._on_paper`) (pass active, or a `paints_on_paper` scene). On
paper: Automatic -> black, Background -> white, **Accent -> the light-theme
accent always** (R1; an old B&W project with user-picked Accent text on an
unrowed item now plots it in the accent — accepted exception to G2).
`token:blocks` follows D6. `paper_pass_color_mode`, `_PASS_COLOR_MODE`,
`PaperColorMode`, `load_paper_color_mode` and `save_paper_color_mode` are
deleted. The universal colour picker's Theme row gains a third chip,
**"Background"** (`token:bg`); `picked_colour`, `token_label` and
`colour_from_label` accept it. `token:blocks` / `token:element` stay
internal.

**D8 — Display Manager tab (R4, R5).** The Color Mode row is removed. A new
column **AS AUTH.** sits between VIS and COLOUR holding a checkable painted
glyph button (`ui_kit`), the visibility eye's twin: 22 px cell, 17 px glyph,
glyph **A, palette** (R5) — accent when ON; faint plus a diagonal slash when
OFF; disabled-opacity when disabled; re-latches on `theme_bus().changed`.
ON greys Colour / Fill / Section; OFF makes them live (Fill / Section only
where the row has them). Hatch has no glyph; Underlay has glyph + Colour.
Tooltip: "As Authored: plot this row's items in their own colours (off =
paint the row colours over them)". Reset All -> D3 factory. Cancel restores
the snapshot including toggles. Picking a colour flips nothing.

Phase 3 rulings: R1 Accent always accent on paper; R2 Underlay row = toggle
+ Colour only; R3 approach A; R4 sections 1-5 approved as presented; R5 glyph
A (palette). All via AskUserQuestion, 2026-11-11. Phase 4 (2026-11-11): R5
re-ratified after the mockup PNGs were served to the user (A palette); R6
SVG symbols re-resolve token colour and fill on paper (D6).

## Acceptance Criteria

- [x] AC1 Each row except Hatch has the glyph left of Colour; ON greys
      Colour / Fill / Section, OFF makes them live; Underlay has glyph +
      Colour only.
- [x] AC2 A real sheet-viewport paint with a row ON plots authored colours
      (block op colour, WM3 placement Colour, Construction pen, a token
      re-resolved on paper, `token:blocks` -> Model Blocks colour) and with it
      OFF the row colour — painted pixel colour asserted, RED with the per-row
      branch reverted.
- [x] AC3 B&W, Custom and Full Color fixture projects plot pixel-identical to
      the branch base (D4); QSettings with a legacy `paper/color_mode`
      migrates the same way (D5) under isolated settings.
- [x] AC4 Underlay row ON -> layer colours, OFF -> row colour (D6).
- [x] AC5 "Background" offered in the picker; resolves canvas bg on screen,
      white on paper (D7).
- [x] AC6 New project: D3 factory tokens on both tabs, every row ON; a row
      set OFF in the paper settings opens a new project OFF (G1).
- [x] AC7 No `PaperColorMode`, `load/save_paper_color_mode`,
      `paper_pass_color_mode` or `color_mode` write remains (grep guard); the
      PDF export of an AC2 sheet matches the screen render.
- [x] AC8 SVG symbols (D6 / R6): with the row ON, a token Model fill
      (Background) plots white and a token colour (Automatic) black on paper;
      a hex colour plots its canvas hex; RED with the fill-token half reverted.
- [x] AC9 Accent on an unrowed item plots the light-theme accent on paper (D7).

## Verification Checklist

- [x] All acceptance criteria met, each guard shown RED with its rule
      reverted (VC3).
- [x] The 51 test files coupled to `color_mode` / `PaperColorMode` rewritten
      in the same task (VC5): B&W / Custom -> rows OFF, Full Color -> rows ON.
- [ ] Full suite green on the final tree (VC6). *(Not ticked: full suite waived by the user.)*
- [x] Smoke: open a B&W, a Custom and a Full Color project; toggle rows;
      export PDF; new project shows every row ON with token chips.
- [x] Account (2026-11-11): `paper-space.md`, `hatch-and-fill.md` (HF1 paper tokens),
      `linetypes.md` LT1-2 / WM3 D3, the 2026-05-12 paper-DM design
      reconciled in place, each linking this doc; propose closing
      `todo_open.md` line "Full Color mode: white-pen Construction geometry"
      (retired by G4 + D3) and the TextItem latched-colour-on-mode-change line.

## Existing Code Context

- `paper_display.py`: `PaperColorMode` and its load/save; `_CATEGORY_KEYS`,
  `_HAS_FILL`, `_HAS_SECTION`, `_LW_ONLY`; `_make_factory_category`;
  `load/save_paper_categories`; `get_paper_display_for_save`;
  `apply_paper_display_from_project`; `_apply_generic`,
  `_apply_construction`, `_apply_pipe`, `_apply_block`, `_apply_gridline`,
  `_apply_marker`, `_model_colour_token`; `apply_paper_overrides` (proxies,
  elevation lines, SVG tints, fittings, underlays).
- `colour_tokens.py`: `_paper_mode`, `_blocks_colour`, `resolve_colour`,
  `picked_colour`, `token_label`, `colour_from_label`.
- `colour_picker.py`: `_add_token_row`.
- `display_manager.py`: `_build_paper_space_tab`, `_on_color_mode_changed`,
  `_apply_color_mode_ui`, `_on_paper_color_clicked`,
  `_reset_paper_space_tab`, the Cancel snapshot, `_CATEGORIES` factory,
  `_PS_GROUPS`, `_SVG_CATEGORIES` rule.
- `ui_kit.py`: `EyeToggle`, `paint_eye`, `eye_color`, `round_pen`.

## Edge Cases & Error Handling

- A project row stored with `as_authored` but an old `color_mode` also
  present: the stored per-row value wins.
- A non-bool stored `as_authored` (QSettings strings "true"/"false"):
  parsed like `visible`.
- Underlay row OFF with a mask child: masks keep painting the sheet
  (unchanged skip).
- Hatch row: never carries `as_authored`; the pass never reads it there.
