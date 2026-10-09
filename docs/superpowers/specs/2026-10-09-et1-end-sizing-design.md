---
status: proposal   # designed 2026-10-09, unbuilt; on build folded into an "ET1 — as built" section of linetypes.md (Rule A)
last-verified: 2026-10-09
verified-commit: bee3c3cc
applies-to:
  - firepro3d/end_render.py          # k per end: printed | screen, × per-use scale; short-stroke gate; memo keys
  - firepro3d/end_authoring.py       # SEED, On screen field, Size retired
  - firepro3d/stroke_style.py        # per-end record "scale"; ResolvedEnd.scale
  - firepro3d/block_definition.py    # _norm_end: {"trim"[, "screen"]}
  - firepro3d/linetype_render.py     # screen_fixed_here (LTS gate shared), printed_factor unchanged
  - firepro3d/geometry_2d.py         # raw paint / bounds callers, Scale rows, _screen_ends mark
  - firepro3d/block_instance.py      # placed paint / bounds callers, _screen_ends mark
  - firepro3d/capability_panel.py    # end-type editor rows: On screen · Trim · Preview
  - firepro3d/model_space.py         # zoom hook: re-prepare marked items
  - firepro3d/model_view.py          # wheelEvent → scene zoom hook
  - firepro3d/schematic_scene.py     # schematic render scene drawing_scale = 1
  - firepro3d/block_editor.py        # schematic editor drawing_scale = 1
  - firepro3d/tooltips.py            # new: app-level tooltip wrap filter
  - firepro3d/constants.py           # TOOLTIP_MAX_PX, FIXED_END_PX_PER_MM alias
  - main.py                          # _seed_editor_units copies drawing_scale (block editors); tooltips.install
source-tasks: [todo_open.md "ET1 -- End-type sizing polish"]
---

# ET1 — End-type sizing polish — Design

> The *what* was ratified in this run's Phase-2 grill (Q1–Q10, 2026-10-09;
> recorded below under "What"). This doc is the *how*; on build it is folded
> into an "ET1 — as built" section of `docs/specs/linetypes.md`, which stays
> the one home (Rule A). It **amends** LT5-4 (Sizing), D-L8b (Line weight
> retired; caps retired from the LT7 catalog), LTS-9f (ends now follow an
> On screen row of their own) and extends LTS-7 (short-stroke rule) to ends.

## Goal

An end type authored once in printed mm reads right on every canvas: the
Block Editor previews it at the project drawing scale like the plan canvas,
a line can scale the end it uses, an end can be screen-constant on model
canvases, and the tooltips that describe all this wrap at a capped width.

## Motivation

A 3 mm arrow is the right printed size, but the Block Editor drew it at real
size beside metre-scale block geometry (unreadable), the definition carried
a second sizing mode (Line weight) nobody needs once caps leave the catalog,
a line could not vary an end's size without a second end type, and the
tooltip explaining the sizing modes rendered 1,241 px wide on one line.
Gridline bubbles (LT5-1, the north star) need per-use size and a readable
authoring preview before LT7 ships the System End Types.

## What (ratified 2026-10-09)

- **Q1 Editor preview.** The definition-level "model or paper" toggle is
  dropped. The Block Editor previews Fixed ends **and Drafting linetypes** at
  the project drawing scale, as the plan canvas already does (measured: plan
  k = drawing scale, paper k = 1/paper scale, editor k = 1 before this task).
- **Q2 Which scale.** Block editors follow the project drawing scale through
  the same chokepoint that syncs units and precision (`_seed_editor_units`);
  **schematic editors keep real size** (NTS content has no scale).
- **Q3 Caps.** Line weight sizing goes; Fixed (1 authored mm = 1 printed mm)
  is the only size. Flat / Round / Square caps are **retired from the LT7
  catalog** (a weight-tracking cap is a pen property, and LT5-3 already draws
  the pen's cap on end-less lines).
- **Q4 Migration.** The `size` key is dropped from the end record; any stored
  value (incl. `weight_relative`) loads as Fixed, trim read as authored mm.
  No format bump, no message.
- **Q5 Per-use Scale.** One **Scale per end** on the line (rows Start Scale /
  Finish Scale), stored in the per-end record as `scale`, written only when
  ≠ 1; multiplies the end's k, Trim included; applies whether the end is the
  line's own pick or the linetype default; hidden on closed items, the
  Geometry template and placements; locked with the capability lock tip.
- **Q6 On screen.** A per-definition **On screen: Fixed size | Scale with
  zoom** row in the end-type editor with LTS-1..3 semantics (model canvases
  only; Fixed size = printed mm × 6 px/mm at any zoom; sheets / PDF true mm);
  the per-use Scale multiplies it. Stored end without the key = Scale with
  zoom; a new end seeds Fixed size; LT7's shipped ends ship Fixed size.
- **Q7 Short stroke.** LTS-7 parity: on a model canvas, a stroke whose
  on-screen length is under the sum of its Fixed-size trims draws its plain
  stroke with no ends (whole item; inside a placed block per stroke op).
  Paper keeps LT5-4 (no stroke, both ends).
- **Q8 Tooltips.** One chokepoint caps plain tooltips at **360 px**: a tip
  whose longest line is wider wraps (rich text, newline → break); shorter
  tips stay pixel-identical. Breaks are authored in every tip this task
  touches; an app-wide breaks sweep is a maint follow-up.
- **Q9 Testing.** Six VC3 guard groups (Acceptance Criteria); perf stays
  report-only on `tests/test_lt5_perf.py` with one added Fixed-size scene.
- **Q10 Defaults (a)–(g).** End-type editor rows End type · On screen · Trim
  · Preview (Trim always a project length); line rows Start End · Start
  Visible · Start Scale · Finish End · Finish Visible · Finish Scale (Scale
  0.1–10, bad input reverts, one undo step incl. multi-selection); the
  authoring canvas and the 4 px/mm panel swatch unchanged (LTS-6 parity);
  Explode / copy style / Join / Mirror carry Scale with its physical end like
  `mirrored`; lines inside placed blocks follow the end's On screen and the
  authored Scale (WM-11 stands); a linetype's default ends follow each end's
  own On screen; follow-ups per "Retirements and follow-ups".

## Architecture & Constraints

- **Flyweight compile** (LT5): ends are resolved and drawn at paint, never
  compiled into ops — k now depends on the paint's device scale for Fixed-size
  ends, which is exactly why.
- **One renderer** (`end_render.py`) for raw primitives, `BlockInstance` and
  paper/PDF; **one place decides k** (approach A, user-approved): callers
  supply two numbers (`printed`, `screen`), the renderer picks per end.
- **LTS parity, not a parallel system:** the scope test for "screen-constant
  here" is the LTS gate (`role in (plan, block_editor)`, no paper scale, not
  `paper_pass_active()`), promoted from `fixed_on_canvas` into a shared
  predicate both callers use; the px/mm constant is shared.
- **Fast paths untouched** for end-less strokes (E1 parity; the `_item_ends`
  / `_op_ends` gates are not changed).
- Snap / HALO / `shape()` stay on the base line (LT3-6); bounds and the
  selection highlight cover ends (LT5-14).
- **Records byte-stable where unchanged:** every key added is written only
  when non-default (`mirrored` idiom), so LT2 goldens, pre-ET1 `.fpd` /
  `.fpdb` files and default records serialise identically.

## Design Decisions

### A — Data

- `BlockDefinition.end = {"trim": mm >= 0[, "screen": "fixed"]}` via
  `_norm_end`: `size` is read and discarded (any value → Fixed); `screen`
  kept only when `"fixed"` (the `_norm_repeat` idiom, H-LTS-a). `_END_SIZES`,
  `end_render.WEIGHT_RELATIVE` / `FIXED` and `end_authoring.SIZE_LABELS`
  retire. `EndDef` gains `screen: str` (`"fixed"` | `"scale"`, default
  `"scale"`) and loses `size`.
- Per-end line record `{"end", "visible"[, "mirrored"][, "scale"]}`:
  `stroke_style._end` keeps `scale` only when it is a finite float > 0 and
  ≠ 1 (rounded as stored; 1.0 and bad values drop the key). `ResolvedEnd`
  gains `scale: float` (default 1.0; `NO_ENDS` updated); `_resolve_end`
  carries it from the record (a Visible-off end still carries it, unused).
  `toggle_mirrored`, `clear_explicit_ends`, `copy_style`
  (`normalize_style`), Explode's verbatim record, `render_op.ends` and the
  clipboard / undo / `.fpd` paths need no change: they copy whole records.
- *Rejected:* a per-line Scale (the leader case needs two); writing
  `"scale": 1.0` always (breaks LT2 goldens); keeping `size` as a dead key.

### B — Factor and paint

- `end_render.end_scales(ed, e, *, printed, screen)` → `(screen if
  ed.screen == "fixed" and screen is not None else printed) * e.scale`.
  `end_trims`, `paint_ends`, `ends_rect`, `_ends_rect`, `ends_reach` take
  `printed=` / `screen=` in place of `fixed_factor=` / `weight_factor=`; the
  `_XF` key already holds k; the `_RECT` key adds each end's `scale` and the
  `screen` value (k is not in that key — the factors are).
- `linetype_render.screen_fixed_here(*, paper_scale, role) -> bool` = the
  LTS-2 scope test (role in `_FIXED_ROLES`, no paper scale, not a paper
  pass); `fixed_on_canvas(lt, ...)` becomes `lt.screen == "fixed" and
  screen_fixed_here(...)`. `screen` for a paint = `FIXED_END_PX_PER_MM /
  device_scale` when `screen_fixed_here`, else None. `FIXED_END_PX_PER_MM`
  is an alias of `FIXED_LINETYPE_PX_PER_MM` in `constants.py` (one value,
  LTS-3 parity).
- Raw callers (`Geometry2DMixin._paint_stroke_with_ends`, `_ends_rect`):
  `printed = printed_factor(**self._lt_args())` (unchanged), `screen` from
  the paint's `_device_scale(painter)` (paint) or `scene_hit_width(self,
  FIXED_END_PX_PER_MM, …)` (bounds, the badge-pad convention). Placed
  callers (`BlockInstance.paint` both op sites, `_end_pad`): `screen` from
  the posed device scale already computed for trims; `_end_pad_rows` keeps
  two reaches per row — printed-sized and screen-sized — so `_end_pad`
  multiplies the right one (the `wr` column is re-purposed, not added).
- **Short stroke (Q7):** in the raw path, after `end_trims`, when
  `screen is not None` and some drawn end is Fixed-size and `s0 + s1 >=
  pw.total_length(pieces)` → paint the plain base stroke (`_paint_base_stroke`)
  and skip `paint_ends` except missing badges; the placed per-op path does
  the same per op (`_stroke_op` with `path=None`, no `_draw_op_ends`). Paper
  passes never take the gate. `end_render.short_on_screen(ends, trims,
  pieces, screen)` holds the test so both paths share it.
- `end_authoring.preview_painter` keeps `END_PREVIEW_PX_PER_MM` as `printed`
  and passes `screen=None` (the swatch previews printed size, Q10-c).

### C — Bounds on zoom (the folded bug class)

- A Fixed-size end's scene extent changes with zoom while cached bounds do
  not; under `MinimalViewportUpdate` that culls at the viewport edge and
  trails on pan (the mechanism of the folded "line-weight end bounds" bug).
- `paint_ends` reports whether it drew a Fixed-size end at a screen factor
  (return value); `_paint_stroke_with_ends` / `BlockInstance.paint` set
  `self._screen_ends = True` on that paint (cleared when a paint draws none)
  and register the item in `scene._screen_end_items` (a `WeakSet`).
- `Model_View.wheelEvent` (and any other zoom step: fit, keyboard zoom —
  every path that calls `self.scale()`; grep at build) calls
  `scene.view_zoom_changed()` after the transform change, which runs
  `prepareGeometryChange()` on the registered items and clears the set (a
  later paint re-registers). Cost bounded by items that actually draw
  Fixed-size ends; nothing for Scale-with-zoom ends or end-less scenes.
- *Rejected:* a scene-wide `prepareGeometryChange` on zoom (O(n) every
  wheel step); sizing bounds for the largest possible reach (unbounded as
  the view zooms out).

### D — Editor scale

- `MainWindow._seed_editor_units` also copies `drawing_scale` into a block
  editor's ScaleManager (`w.kind == "block"`; schematic editors skip it) —
  the existing callers (project settings changed, unit / precision set,
  editor open) already fan out through `_sync_editor_units`, so a project
  scale change repaints open editors via the existing
  `_refresh_all_labels` + `update()`.
- `printed_factor` is unchanged in shape: role `"block_editor"` joins
  `"plan"` in returning the drawing scale (so Drafting linetypes follow too,
  Q1). Schematic editor scenes (`BlockEditorWidget.__init__`, kind
  `"schematic"`) and schematic render scenes (`schematic_scene.scene_for`)
  set their ScaleManager's `drawing_scale = 1.0` at construction, so they
  keep real size. Nothing else in an editor reads `drawing_scale` (block
  import, text, hatch don't).
- *Rejected:* a per-editor preview-scale picker (new UI); a scene flag read
  by `_lt_args` (a second rule beside the ScaleManager).

### E — Authoring rows

- End-type editor (`capability_panel.capability_rows`, kind `"end"`): rows
  **On screen** (enum `Fixed size` | `Scale with zoom`, the LTS row's
  strings) · **Trim** (dimension, always a project length; the `_wr_multiple`
  branch retires) · **Preview**. Write-back `end_authoring.set_end_field`
  gains `"On screen"` (mirrors `linetype_authoring.set_repeat_field`: write
  `"fixed"` or pop the key; same-value pick is a no-op) and loses `"Size"`.
  `begin_end` SEED = `{"trim": 0.0, "screen": "fixed"}`.
- Line rows (`geometry_2d._end_rows`): per end **Scale** after Visible — a
  `string` row with suffix `×` (the old weight-relative Trim idiom; the
  panel's number row is integer-only), value `f"{scale:g}"`; `_END_ROW_KEYS`
  gains `"Start Scale"` / `"Finish Scale"` → `(which, "scale")`;
  `_set_end_from_panel` parses a float (a trailing `×` tolerated), rejects
  outside 0.1–10 or non-finite (the panel refresh shows the old value), and
  writes through `_dim_edit` → `_set_end_field` (one step per edit; the
  multi-target path is the existing one). `_set_end_field` normalises the
  record through `_end` so 1.0 drops the key in memory too. Locked rows get
  the same lock tip; placements and the template get none (`ends=` False).
- Tips rewritten with breaks: `_END_TIP`, `_END_VISIBLE_TIP`, the new
  `_END_SCALE_TIP`, `capability_panel._END_SCREEN_TIP` (replaces
  `_END_SIZE_TIP`), `_END_TRIM_TIP`, the three lock tips. Mockup wording is
  the starting text (served page, 2026-10-09).

### F — Tooltip chokepoint

- New `firepro3d/tooltips.py`: `wrap(text, cap) -> str | None` (None when
  every line's `QFontMetrics(QToolTip.font()).horizontalAdvance` ≤ cap or
  the text is already rich; else `html.escape` + `\n` → `<br>` inside
  `<table width='{cap}'><tr><td>…</td></tr></table>`, the one form the
  probe showed wrapping at exactly the cap) and `install(app)` (a
  `QObject` filter on the `QApplication` for `QEvent.ToolTip` on a
  `QWidget` with a non-empty `toolTip()`: when `wrap` returns text, show it
  with `QToolTip.showText(ev.globalPos(), rich, widget, widget.rect())` and
  consume the event; otherwise return False so the widget shows its own
  tip). `constants.TOOLTIP_MAX_PX = 360`. Installed once in `main()` after
  `apply_app_font`; a `tests/conftest.py` fixture `tooltips_installed`
  installs / removes it per test. Graphics-item tips (the view viewport has
  an empty `toolTip()`) pass through untouched — the missing-badge tips are
  short.
- Probed 2026-10-09 (P4): the filter sees the event first; the long tip
  renders a 385 px label (cap + padding) with word wrap; a short tip's label
  is byte-identical in size and text.
- *Rejected:* a `tip()` helper at the ~130 call sites (misses the panel
  meta path and future sites); QSS `max-width` on `QToolTip` (ignored by
  the tip label); `<p>`/`<div style>` widths (not honoured).

### G — Retirements and follow-ups

- Retired: `WEIGHT_RELATIVE`, `SIZE_LABELS`, `_END_SIZES`, the Size row, the
  `× line weight` Trim mode and `_wr_multiple`, the weight-relative bounds
  branch in `_ends_rect` / `_end_pad`, `lt5_support.round_end` and the
  weight-relative test cases (rewritten to Fixed under VC5).
- `linetypes.md` at Account: LT5-4 (Fixed only; On screen for ends; Scale per
  use), D-L8b (caps retired, LT7 list), LTS-9f (ends follow their own On
  screen), LTS-7 (ends clause), LTS-2 (ends included), an "ET1 — as built"
  section; `ui-design-system.md` gains the tooltip convention (cap,
  chokepoint, authored breaks) with a one-line pointer from
  `property-panel.md`'s tooltip rule.
- Follow-ups filed at wrap-up: app-wide tooltip breaks sweep (maint); LT7
  task line edited (caps out, "ship Fixed size"); the per-placement
  end-override design task gets "per-use On screen override belongs here";
  the "Line-weight end bounds" bug and LT5 leftovers (b) and (d) close as
  superseded.

## Acceptance Criteria

Guards construct the scenario, drive the real paint / event path with real
objects and assert observable output; each is shown RED with the change
reverted (VC3).

- [ ] **G1 Editor scale.** A `Model_Space(scene_role="block_editor")` whose
      ScaleManager carries drawing scale 100 paints a 3 mm Fixed arrow 300 mm
      wide (pixels at a known px/mm) and a Drafting Hidden 6/3 as 600/300 mm
      dashes; the same scene at drawing scale 1 paints 3 mm / 6/3; a
      schematic editor opened from a MainWindow (`kind == "schematic"`) keeps
      k = 1; changing the project drawing scale through
      `_on_project_settings_changed` updates an open block editor's k.
- [ ] **G2 Record.** `BlockDefinition.to_dict()` of a new end type has no
      `size` key; `from_dict` of `{"size": "weight_relative", "trim": 1.5}`
      yields `{"trim": 1.5}` and paints Fixed; an LT5-written `.fpdb` with a
      weight-relative end loads and paints; `.fpdb` round-trips `screen`.
- [ ] **G3 Per-use Scale.** A line with `start.scale = 2` paints a head twice
      as long and a stroke stopping twice as far back on plan, in a Block
      Editor and in a real PDF; the key is absent from `to_dict()` at 1×
      (LT2 goldens unchanged); it round-trips `.fpd`, `.fpdb` (inside a
      block), copy / paste, undo and Explode; rows appear on an open Line,
      Polyline, Arc and Spline, not on a closed Polyline, the Geometry
      template or a placement; locked with the lock tip in an end-type /
      linetype / tile editor; a panel edit is one undo step for one and for
      two selected lines; `12` reverts.
- [ ] **G4 On screen.** A Fixed-size 3 mm end on the plan paints 18 px long
      at 0.08 and at 0.5 px/mm (× Scale when set), also inside a placed block
      and in a Block Editor; the PDF prints 3 mm; a Scale-with-zoom end
      doubles with zoom; a new end type's record seeds `screen: "fixed"`; a
      stored end without the key paints Scale with zoom; the panel swatch's
      pixels are unchanged from LT5.
- [ ] **G5 Short stroke.** A 100 mm line with two Fixed-size 18 px-trim ends
      at 0.1 px/mm (10 px long) paints its plain stroke and no end pixels;
      at 1 px/mm both ends and the trimmed stroke return; a placed block's
      op behaves the same; a PDF of the short case keeps LT5-4.
- [ ] **G6 Bounds on zoom.** After a wheel-zoom out on a view with a
      Fixed-size end, `boundingRect()` covers the end's new extent
      (`prepareGeometryChange` observed via the scene index: `items(rect)`
      at the end's new location returns the item); a Scale-with-zoom scene
      registers nothing.
- [ ] **G7 Tooltips.** Through `QHelpEvent` on a real widget under the app
      QSS: a tip with a 600 px line shows a tip label ≤ cap + padding with
      word wrap and a `<br>` per newline; a 200 px tip's label matches the
      pre-filter width / text exactly; every tip string this task authors
      has no line wider than the cap at the app tooltip font.
- [ ] **Perf (report-only).** `tests/test_lt5_perf.py` gains a Fixed-size
      ends scene; prints ratios vs the Scale-with-zoom scene; no bar.

## Verification Checklist

- [ ] All acceptance criteria met; each guard shown RED with the change
      reverted (or by TDD-first RED runs).
- [ ] Full suite green (VC6, chunked, `-m "not perf"`; perf standalone).
- [ ] LT5 goldens / E1 parity (end-less strokes byte-identical) unchanged.
- [ ] User smoke: Block Editor end preview at scale; Scale row; On screen row;
      zoom-out short stroke; tooltip wrap on the Start End row.
- [ ] Spec Account: linetypes.md ET1 section + amendments; ui-design-system
      tooltip convention; SPEC-INDEX pointers; follow-ups filed.

## Existing Code Context

- `end_render.py`: `EndDef.from_block` (cache on (id, version)), `end_scales`,
  `end_trims`, `paint_ends`, `ends_rect` (+ `_RECT` memo), `ends_reach`,
  `_frame_xf` / `_XF` memo, `trimmed_path`, `linetype_has_default_end`.
- `geometry_2d.py`: `_lt_args`, `_item_ends`, `_ends_rect`,
  `_paint_stroke_with_ends`, `_set_end_field`, `_set_end_from_panel`,
  `_END_ROW_KEYS`, `_end_rows`, `stroke_rows(ends=…)`, the `_END_*_TIP`
  strings.
- `block_instance.py`: `_lt_args`, `_op_ends`, `_draw_op_ends`,
  `_trimmed_op_path`, `_end_pad_rows` / `_end_pad`, two paint sites
  (linetyped op path and plain op path).
- `linetype_render.py`: `printed_factor`, `length_factor`,
  `fixed_on_canvas`, `_FIXED_ROLES`, `periods_on`, `sync_missing_tooltip`.
- `linetype_authoring.set_repeat_field("On screen")` and
  `capability_panel` kind `"repeat"` rows: the row to mirror.
- `main.py`: `_seed_editor_units` / `_sync_editor_units`, `main()` startup
  (font, QSS); `model_view.wheelEvent`.
- Tests: `tests/lt5_support.py`, `test_lt5_*.py` (22 files),
  `test_lts_canvas.py` (zoom-constancy guard pattern), `test_lt5_render_raw.py`
  (PDF export pattern via `_export`).

## Edge Cases & Error Handling

- Scale written as `"2"` / `"2 ×"` / `"2×"` parse; `"abc"`, `0`, `-1`,
  `inf`, `12` revert (panel refresh shows the old value).
- A Fixed-size end on a paper pass, a sheet or a viewport: `screen` is None
  → printed mm (LTS-2 scope). A detail view: its own device scale.
- A Visible-off end keeps its `scale` (round-trips, unused).
- `mirrored` + `scale`: independent flags on one record.
- A missing end at a scaled slot: badge only (no k).
- Both ends Fixed-size on a near-zero-length stroke: the Q7 gate wins
  (plain stroke); on paper LT5-4 (both ends, no stroke).
- A linetype default end that is Fixed-size inside a Scale-with-zoom
  linetype: the end follows its own row (Q10-f).
- Tooltip text already rich (none today): left alone (`Qt.mightBeRichText`).
- `QToolTip.font()` before any tip shown: Qt returns the app font — the
  measure is stable.

## Performance & Security

- End-less strokes: untouched gates, ≤ 1.1× bar remains (E1).
- Fixed-size ends recompute k per zoom step (memo misses on `_XF` / `_RECT`
  keyed by k / factors) — report-only on the LT5 bench; residual to LT8.
- The zoom hook is O(items that drew a Fixed-size end last paint).
- The tooltip filter runs one `horizontalAdvance` per line of the tip, only
  on `QEvent.ToolTip` (hover), never on paint.

## Code Style & Testing

- Google docstrings, constants in `constants.py`, relative imports inside
  the package; every new row / button has a tooltip (project rule) with
  authored breaks and no line over the cap.
- pytest via `./venv/Scripts/python.exe -m pytest` (never the activate
  script); probes only through pytest (conftest isolates QSettings); real
  paint into `QImage` / real PDF export for pixel guards; `QHelpEvent` for
  tooltip guards; VC3 RED shown per guard.
