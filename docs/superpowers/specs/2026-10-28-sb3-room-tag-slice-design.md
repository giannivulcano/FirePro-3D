---
status: proposal
last-verified: 2026-10-28
verified-commit: b9328614
applies-to:
  - firepro3d/bound_label.py          # new: BoundLabelItem
  - firepro3d/system_blocks.py        # new: SYSTEM_DEFAULTS
  - firepro3d/system_blocks/Tags/     # shipped RoomTag .fpdb
  - firepro3d/block_attributes.py     # bound_text_ops (lifted)
  - firepro3d/render_op.py            # paint_ops (lifted)
  - firepro3d/block_instance.py       # calls the lifted helpers
  - firepro3d/room.py                 # label -> BoundLabelItem
  - firepro3d/model_space.py          # annotation_defaults + annotation_block()
  - firepro3d/scene_io.py             # annotation_defaults key
  - firepro3d/settings/panes.py       # AnnotationPane
  - firepro3d/settings/template.py    # annotation_defaults in the template
  - firepro3d/paper_display.py        # room tag through _apply_block
  - firepro3d/display_manager.py      # Room row font key retired
  # the label_scene_rect special case is Model_Space._halo_room_hit (model_space.py above)
source-tasks:
  - "SB3 -- First vertical slice: room tag drawn by a System block via BoundLabelItem + the Project Settings Annotation defaults pane (todo_open.md, [type:feature], P1)"
---

# SB3 -- Room tag as a System block (first vertical slice) -- Design Spec

> **Status: proposal.** Nothing here is built. Parent concept:
> [`2026-09-29-system-blocks-concept-design.md`](2026-09-29-system-blocks-concept-design.md)
> (Q4 intrinsic labels, Q5 block resolution, F1 split cache, F4 System tier, F5
> `BoundLabelItem`, G1-G7 guards, build phase 3 + the reassessment checkpoint).
> Annotative sizing contract: [`2026-10-23-sb1c-annotative-sizing-design.md`](2026-10-23-sb1c-annotative-sizing-design.md).
> Every decision below was ratified through `AskUserQuestion` in the 2026-10-28
> Phase 2 grill (Q1-Q13) and the Phase 3 approach / design approval (P5: locked).

## Goal

The room label is drawn by a **System block** (`RoomTag`, authored by the user in
the Block Editor and promoted to the shipped System library) through one reusable
child item, `BoundLabelItem`, whose data source is the Room it belongs to. A
Project Settings **Annotation** pane maps category -> block
(`annotation_defaults`), cloned from the template. The built-in HTML room label
retires. This is concept build phase 3; passing it (and the checkpoint) unblocks
SB4a-e.

## Motivation

Proves the two seams every later conversion rides on -- the bound-text render
pipeline shared between a placed `BlockInstance` and a host-owned label, and the
project-level block resolution with a guaranteed fallback -- on the simplest
intrinsic label before touching pipes, bubbles and heads.

## Ratified decisions (Phase 2 grill, 2026-10-28)

| # | Decision | Rationale (user) |
|---|---|---|
| Q1 | The shipped RoomTag shows **Name only** (`@[Name]`). | Smallest delta for the first visual gate; Mark/Area are a Block Editor edit. Supersedes the SB2b "canvas label shows name, not Mark" test's mechanism (rewritten against the bound field). |
| Q2 | **Annotative everywhere**: model canvas = authored mm x drawing scale, paper = authored mm. | WYSIWYG, one mechanism; SB1c D11 "keep today (150 mm model)" for rooms is **superseded**. |
| Q3 | Click on the tag selects the **Room**; one move grip at the tag anchor writes `label_offset`; no rotate grip. | Same as today; offsets carry over. |
| Q4 | Tag draws in the **block's authored colours** (Automatic = theme ink). Room row colour no longer tints it; Room row `font` key **retires**. | Same as every block; SB1c D12 precedent for retiring a DM size key. |
| Q5a | Pane picker = **System blocks + project-embedded blocks** with `host_category == "Room"`; default row "RoomTag (System)". Per-room tag style is **SB3b** (filed). | Library blocks enter the project through the Blocks browser as today. |
| Q5b | Pane OK **marks the project modified, no undo step**; the Marks pane is fixed to mark modified too. | Project settings are not undoable (Revit-like). |
| Q6 | Mapped id missing from project + libraries -> **SYSTEM_DEFAULTS RoomTag + one load notice**; the mapping stays in the file. | G5 "never vanishes"; a later Reload can resolve it. |
| Q7 | G6 bar: **<= 0.25 ms per labelled room**, full-view headless render (200 rooms <= 50 ms, 1000 <= 250 ms); 9-rooms-in-view <= 25 ms. Base at b9328614: 14 / 42 / 141 ms for 50 / 200 / 1000 rooms; zoomed 12-22 ms. | ~1.8x headroom for glyph-outline paint over HTML text. |
| Q8 | Visual gate = **base screenshot of a reference .fpd + the live new build**; approval freezes the G7 pixel lock. | No in-app toggle (old painter retired). |
| Q9 | **Retire the built-in label** (QGraphicsTextItem/HTML, `_RoundedRectBgItem`, `_label_font_size`, `_label_font_color`, `ROOM_LABEL_PAPER_CAP_MM`, `_apply_room_label_paper_height`). Saved `show_label` + `label_offset` **carry over as-is**; DM `font` never read; **no format bump**. | The block replaces the label; no fallback painter. |
| Q10 | Checkpoint verdict -> dated section in `docs/specs/system-blocks.md`; SB4a-e lines get "checkpoint passed <date>". | One home for the concept's gate. |
| Q11 | **'Tags' series**; the user authors RoomTag (host category Room, one `@[Name]` text, origin at the text centre, annotative) -> Workbench -> Promote to System; the run commits the `.fpdb` and freezes its id into `SYSTEM_DEFAULTS`. | Concept Q13 "user-designed". |
| Q12 | Template saves the id; a new project resolves System -> library roots (embedding) -> G5 fallback. | Same resolver as a missing project block. |
| Q13 | **Retire the C1 label-rect pick restriction** (`label_scene_rect`, HALO gather + rubber-band special case); rooms are candidates by polygon. A tag whose bound fields all resolve empty **paints nothing**. | HALO preselection disambiguates now. |
| D-A | Approach **B**: lightweight `BoundLabelItem(QGraphicsItem)` + helpers lifted from `BlockInstance`. | No `isinstance(BlockInstance)` leakage into HALO / snaps / level filter / `_blocks`; one implementation of bound text + op painting. |

As-proposed (not gated; flag if wrong): the panel row keeps its name "Show
Label"; Room row visibility / opacity hide the tag with the room; the paper pass
routes the tag through the existing annotative `_apply_block` (SB1c D6).

## Architecture & Constraints

### Components

| Unit | Role |
|---|---|
| `bound_label.BoundLabelItem(QGraphicsItem)` **new** | Child of a host element; `host = parentItem()`. `definition()` = `scene.annotation_block(category)`. `_paper_scale` (set by the paper pass). Pose = translate(anchor) x annotative *k* from `annotative.annotative_factor(self, painter)` (Scale with zoom only; a Fixed-size definition is treated as missing, one log line). `boundingRect` / `shape` = ops bbox x *k* from `annotative.model_factor`. `set_anchor(QPointF)` with `prepareGeometryChange`. Paints nothing when every bound string is empty. Not selectable, not movable, no snaps; visible iff host `show_label`. Not serialized (the host owns it). |
| `block_attributes.bound_text_ops(defn, attributes, host_values, mirrored, scale, ov_args, cache) -> (ops, cache)` **lifted** from `BlockInstance._bound_ops` | One implementation; the method becomes a wrapper holding its cache. Parity guard: a golden ops digest for a bound `BlockInstance` is identical before and after the lift. |
| `render_op.paint_ops(painter, ops, pose, resolve_stroke, ...)` **lifted** from the loop in `BlockInstance.paint` | Same loop body; `BlockInstance.paint` calls it. The exact parameter list is a plan item (P4: read the loop's free variables first). |
| `Model_Space.annotation_defaults: dict[str, str]` + `annotation_block(category) -> BlockDefinition \| None` | Resolver chain: project registry -> System `block_library.shipped_index()` (embedded on first use through the existing load path, outside undo) -> library roots (embedded) -> `SYSTEM_DEFAULTS[category]` shipped file -> `None`. A miss on the mapped id emits one notice through the load-warning channel; the mapping is kept. Result memoised per (category, mapped id, registry version). |
| `system_blocks.SYSTEM_DEFAULTS = {"Room": "<frozen uuid>"}` **new module** | The uuid is read from the promoted `.fpdb` (concept F4 frozen ids). |
| `firepro3d/system_blocks/Tags/<id>.fpdb` | The user-authored RoomTag. `assets.py` already resolves the series folder. |
| `Room` | Drops the HTML label, `_RoundedRectBgItem`, `_label_font_size/_color`, `label_scene_rect`; gains `self._tag = BoundLabelItem(self)` anchored at centroid + `label_offset`. Grip / `label_offset` / `show_label` / `mark` persistence unchanged. `set_property("Room Name")` -> `self._tag.update()` (pull-on-paint; the ops cache is keyed on the resolved strings). |
| `settings/panes.AnnotationPane` + `_TABS` / `_panes` row "Annotation" | One row per `SYSTEM_DEFAULTS` category (Room). Combo of eligible blocks (project registry + System index, `host_category == "Room"`, `scale_mode == "annotative"`), default entry "RoomTag (System)". Apply -> `scene.annotation_defaults` -> `on_changed` -> `main._on_project_settings_changed` (modified flag) -> every room tag `prepareGeometryChange()` + `update()`. `MarksPane.apply` gets the same `on_changed` call. |
| `scene_io` / `settings/template.py` | `annotation_defaults` key written and read (missing -> `{}`; non-str values dropped); `save_current_as_default` copies it; `apply_template_settings` overlays it. No `SAVE_VERSION` bump. |
| `paper_display` | `_apply_room_label_paper_height` + its restore deleted; the paper walk's Room branch calls `_apply_block(room._tag, room_cat, color_mode, lw_mm, paper_scale)` and restores it -- the one annotative path (SB1c D6). The constant `ROOM_LABEL_PAPER_CAP_MM` retires. |
| `display_manager` | Room row `font` key retired (header, editor, write-back, reset; stored value never read -- SB1c D12 shape). |
| `Model_Space._halo_room_hit` (HALO click + rubber-band hook) | Reduced to the polygon target; `label_scene_rect` removed. |
| Refresh hooks | `_refresh_all_labels` (units) and `reprepare_annotative` (drawing scale) also walk room tags. |

### Data flow

Paint: Qt paints `Room` then its child `BoundLabelItem.paint` -> `defn = scene.annotation_block("Room")` -> `host_values = element_params` getters for `defn.host_category` on the Room -> `bound_text_ops` (memoised) + `defn.render_ops_variant(False, k)` -> `paint_ops`.
Edit: Room name change -> `tag.update()`. Units / drawing scale change -> existing hooks walk the tags. Pane OK -> `annotation_defaults` -> tags re-prepared.
Persistence: `annotation_defaults` in the `.fpd` and the template; Room keeps `mark`, `show_label`, `label_offset`.

### Constraints

- Containment C9 gains the *host-bound annotation -> model* class (concept F8); the tag is a child of a model item and never a scene-level entity.
- Rule A: Z-order, units, paper 9.9, the annotative contract and the registry are linked, not restated.
- No `isinstance(BlockInstance)` site gains a new branch; `BoundLabelItem` is invisible to HALO, snaps, the level filter and `scene._block_instances`.
- Shipped System files are never written by the app outside the dev-gated Promote path (`block-system.md` System tier).

## Design Decisions

| # | Fork | Chosen | Rejected | Why |
|---|---|---|---|---|
| D-A | Item shape | B: lightweight item + lifted helpers | A: subclass `BlockInstance` as a child; C: off-scene `BlockInstance` renderer | A leaks a 1700-line selectable/snappable surface into every `isinstance` site; C needs a scene shim for `annotative_factor`. |
| D-B | Resolution | `Model_Space.annotation_block()` with the fallback chain + per-category memo | Resolve in the pane only | The tag must resolve on load with no pane open; one resolver serves the pane, the paint and the template. |
| D-C | Embedding | Embed a System / library definition into the project on first resolve, outside undo | Resolve each paint from the library | Concept Q8: the embedded copy is authoritative; a project renders identically after an app update. |
| D-D | Dirty / undo | Modified flag, no undo (Q5b) | Undo command | Settings are not undoable elsewhere; Marks pane aligned. |
| D-E | Legacy | Carry `show_label` + `label_offset`, no bump (Q9) | Rescale / reset offsets | Same key, same frame (mm from the centroid). |

## Acceptance Criteria

- [ ] AC1 A room shows the mapped block's tag at its centroid + `label_offset`, annotative in model and paper (Q2); the HTML label and its helpers are gone (Q9 list), and `label_scene_rect` with its HALO special case (Q13).
- [ ] AC2 Renaming a room through the property panel changes the rendered tag text (G1); an empty Name paints nothing (Q13).
- [ ] AC3 `annotation_defaults` round-trips through `.fpd` save/load and template save/apply (G2); a legacy file loads with `show_label` and `label_offset` unchanged.
- [ ] AC4 A PDF export at two drawing scales measures the tag's cap height at the authored mm (G3); the model view at the project scale measures authored mm x scale.
- [ ] AC5 A mapped id missing from project and libraries draws the SYSTEM_DEFAULTS RoomTag with one load notice; the mapping is kept (Q6, G5). The shipped `.fpdb` cannot be written outside the dev gate.
- [ ] AC6 G6 bench: <= 0.25 ms per labelled room full view at 200 and 1000 rooms, <= 25 ms zoomed to 9 rooms (`-m perf`, interleaved base/HEAD, raw lines to a file).
- [ ] AC7 Visual gate: the user approves the live tag against the base screenshot; the approved design is frozen by a pixel-sampled lock test (G7).
- [ ] AC8 Dragging the tag grip through the real view changes `label_offset`; undo restores it (Q3).
- [ ] AC9 The Annotation pane lists System + project blocks with `host_category == "Room"`, applies on OK and marks the project modified; the Marks pane marks modified too (Q5a/Q5b).
- [ ] AC10 `bound_text_ops` / `paint_ops` parity: a bound `BlockInstance`'s ops digest is identical before and after the lift.
- [ ] AC11 Retired strings (`label_scene_rect`, `ROOM_LABEL_PAPER_CAP_MM`, `_RoundedRectBgItem`, `_label_font_size`, `_label_font_color`, `_apply_room_label_paper_height`) are absent from `firepro3d/` and `tests/`; the Room row `font` key is gone from the Display Manager.

## Verification Checklist

- [ ] All acceptance criteria met, each with its guard (VC3: real path, RED with the fix reverted).
- [ ] Full suite green on the final tree (VC6).
- [ ] Reassessment checkpoint run and recorded (Q10): G6 result, F1 static-geometry reuse, spec-amendment count.
- [ ] Account: `docs/specs/system-blocks.md` promoted from the concept (consolidating contract); pointers in `block-system.md`, `wall-room-floor-system.md`, `paper-space.md` 9.9, `settings-dialog.md`, `model-space-containment-contract.md` C9, `element-parameters.md`; SB1c D10/D11 room rows marked superseded.
- [ ] SB3b (per-room tag style) filed.

## Edge Cases & Error Handling

- Mapped block missing everywhere, shipped RoomTag also absent -> the red orphan placeholder path (never vanishes).
- Block authored against an unknown host key -> the field placeholder (existing `resolve_fields` behaviour).
- Mapped block not annotative or wrong `host_category` -> treated as missing (log + fallback).
- Room with no boundary / degenerate centroid -> tag not painted.
- Paper pass on a hidden tag (`show_label` False) -> skipped.

## User-only steps (Phase 4 batches these)

1. Author RoomTag in the Block Editor on the new build: host category Room, one text `@[Name]`, origin at the text centre, Scale mode Annotative, On screen Scale with zoom. Save to the Workbench.
2. Promote to System into the `Tags` series (dev gate).
3. Approve the visual gate against the base screenshot (smoke).

## Performance

Per-paint cost = resolver memo hit + ops cache hit + `paint_ops` over a handful of ops; glyph outlines rebuild only on a resolved-string change (F1). G6 bench shapes and bar: Q7.
