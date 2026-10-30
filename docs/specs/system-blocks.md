---
status: partial          # SB3 (room tag, the first vertical slice) BUILT 2026-10-29, checkpoint PASSED; SB3b (per-room tag style) BUILT 2026-10-30; SB4a-e (remaining intrinsic labels), placed tags (phase 6) and sheet tags (phase 7) are not built
last-verified: 2026-10-30  # SB3b Account: s2/s3/s7/s8/s10 + the status/ownership lines re-audited against 7e5d3b15; prior 2026-10-29  # SB3 Account: promoted from the concept (consolidating contract for what is built; the concept stays as history)
verified-commit: 7e5d3b15   # SB3b + L283 merge on main; prior 8be9034a   # SB3 landing on main (feat/sb3-room-tag 409afacb..8be9034a, ff)
applies-to:
  - firepro3d/bound_label.py          # BoundLabelItem, eligible_definition, resolve_annotation_block
  - firepro3d/annotation_choices.py   # SB3b: the one shared picker list (pane + Room Tag row), disk-walk / parse caches
  - firepro3d/system_blocks.py        # SYSTEM_DEFAULTS, ANNOTATION_CATEGORIES, LABEL_FIELD
  - firepro3d/system_blocks/Tags/     # the shipped RoomTag .fpdb
  - firepro3d/block_attributes.py     # bound_text_ops, hugged_text_record (lifted/added for the tag)
  - firepro3d/render_op.py            # paint_ops (lifted from BlockInstance.paint)
  - firepro3d/room.py                 # the Room owns its tag, show_label, label_offset
  - firepro3d/model_space.py          # annotation_defaults, annotation_block, refresh_room_tags
  - firepro3d/scene_io.py             # annotation_defaults key
  - firepro3d/settings/panes.py       # AnnotationPane
  - firepro3d/settings/template.py    # annotation_defaults in the .fpdt
  - firepro3d/paper_display.py        # the tag through _apply_block
  - firepro3d/block_explode.py        # explode hugs bound text before substituting
  - firepro3d/display_manager.py      # Room row: font None (rest under display-manager's own spec)
source-tasks:
  - "SB3 -- First vertical slice: room tag drawn by a System block via BoundLabelItem + the Project Settings Annotation defaults pane (todo_closed.md)"
  - "System Blocks -- author the app's own 2D annotation graphics ... (concept, 2026-09-29)"
---

# System Blocks -- Spec (intrinsic labels drawn by annotation blocks)

> **Status: partial.** This spec is the consolidating contract for what is **built**:
> the host-bound label seam (`BoundLabelItem`), block resolution with a guaranteed
> fallback (`annotation_block`), the Project Settings Annotation pane, and the first
> conversion (the Room tag). It was promoted from the concept
> [`2026-09-29-system-blocks-concept-design.md`](../superpowers/specs/2026-09-29-system-blocks-concept-design.md)
> on 2026-10-29; that document is kept as **history** (the grill Q1-Q16, the
> architecture F1-F8, the not-yet-built phases 4-7). The slice's own design record is
> [`2026-10-28-sb3-room-tag-slice-design.md`](../superpowers/specs/2026-10-28-sb3-room-tag-slice-design.md)
> (ratified decisions Q1-Q13, D-A..D-E). Not built: the remaining intrinsic labels
> (SB4a-e), placed tags (concept F7, Tag tool), sheet-scoped tags. **SB3b (built
> 2026-10-30)** adds the per-room tag block (`Room.tag_block`, sections 3 / 8) and the
> shared picker list that also widens the Annotation pane to the user library (section 7).

## Ownership (Rule A)

This spec owns: the `BoundLabelItem` contract, the annotation-block resolver and its
fallback chain, `annotation_defaults` (model, persistence, pane), `SYSTEM_DEFAULTS`,
the Room tag's behaviour (incl. the per-room `tag_block` semantics and the shared picker
list `annotation_choices`), the hug rule for host-bound text, and the SB3 reassessment
checkpoint. It links, never restates:

- Block definition / flyweight / System tier / library roots / Promote:
  [`block-system.md`](block-system.md) ("System library tier (SB1b, 2026-10-23)").
- Bound-field registry, `HostValue`, Marks: [`element-parameters.md`](element-parameters.md).
- Annotative sizing (k, Scale with zoom vs Fixed size, paper 1/S):
  [`2026-10-23-sb1c-annotative-sizing-design.md`](../superpowers/specs/2026-10-23-sb1c-annotative-sizing-design.md).
- Paper pass: [`paper-space.md`](paper-space.md) 9.9. Units: [`units-and-formatting.md`](units-and-formatting.md).
- Containment: [`model-space-containment-contract.md`](model-space-containment-contract.md) C9.
- Room fields and persistence: [`wall-room-floor-system.md`](wall-room-floor-system.md).
- Selection: [`selection-mode.md`](selection-mode.md). Z-order: `view-relationships.md` 7.3 + `constants.py`.

## 1. Two kinds of annotation, one graphic source

An **intrinsic label** is owned by its element, automatic, toggled per element, and
needs no persisted reference: it is drawn by a `BoundLabelItem` child of the host.
A **placed tag** is a standalone hosted instance (concept F7) and is **not built**.
Both are drawn by blocks authored in the one Block Editor. Today exactly one category
is converted: `Room` (`system_blocks.ANNOTATION_CATEGORIES == ("Room",)`).

## 2. `BoundLabelItem` (`bound_label.py`)

A lightweight `QGraphicsItem`, **not** a `BlockInstance` subclass (SB3 D-A: no
`isinstance(BlockInstance)` leakage into HALO, snaps, the level filter or the
block-instance list).

- **Host and data.** A child of the host (`host = parentItem()`); the host is the data
  source through the `element_params` getters (`host_values`, asked only for the keys the
  block binds plus the category's label field -- the keyed form is owned by
  `element-parameters.md`). The pull happens at paint; there is no per-element change signal.
- **Definition.** `definition()` is the scene's `annotation_block(category, host.tag_block)`
  (section 3): the host's own block id first (`tag_block`; `None` on a host without one),
  then the project default.
- **Pose and sizing.** `set_anchor(pt)` moves the block origin (`setPos`); the annotative
  factor k is folded into the ops, so `boundingRect` / `shape` / the paper pass need no
  extra scaling code. The contract for k (and its pre-resolved-definition parameter) is the
  SB1c design doc.
- **Eligibility** (`bound_label.eligible_definition(defn, category)`): Scale mode
  Annotative, On screen = Scale with zoom, and `host_category == category`. Anything else
  is "treated as missing" (section 3).
- **Cached bounds.** `boundingRect` is cached in `_rect`; `refresh()` and the
  `_paper_scale` setter drop it. With no scene the rect is empty and not cached.
- **Paints nothing** when (a) every host-bound string resolves to raw `None` (a nameless
  room), or (b) the host hides it -- the Room does so when its centroid is degenerate
  (no boundary included; `Room._update_label`). A tag whose block resolves nowhere draws the red orphan placeholder
  **only** when the scene has a resolver **and** the host has a label to lose
  (`LABEL_FIELD[category]` present with a non-None raw value); a nameless room with no
  resolvable block draws nothing (ratified 2026-10-28, checkpoint contradiction (a)).
- **Not** selectable, movable or snappable; invisible to HALO, snaps, the level filter
  and the block-instance list; **never serialized** (the host owns `show_label` and
  `label_offset`).
- **Paper hooks.** `_paper_scale`, `_paper_pen_width`, `_paper_pen_color` are set by
  `paper_display._apply_block` during a viewport pass (section 8).
- **One implementation of bound text and op painting.** `block_attributes.bound_text_ops`
  and `render_op.paint_ops` were lifted from `BlockInstance`; `BlockInstance` wraps them.
  Guard: the AC10 ops/render digests (`tests/test_sb3_parity.py`).
- **Static-geometry reuse (F1).** The tag paints `defn.render_ops_variant(False, k)` (the
  shared static list) plus the `bound_text_ops` glyphs, rebuilt only when a resolved
  string changes. `_state()` resolves the definition and host values once per paint.

## 3. Block resolution (`Model_Space.annotation_block(category, mapped=None)`)

1. **The element's own id (SB3b).** When `mapped` is given (`Room.tag_block`) and the
   project copy of that id is eligible, it wins. Otherwise that id alone is resolved
   (`_resolve_mapped(..., fallback=False)`: project registry -> System tier -> library
   roots, no `SYSTEM_DEFAULTS` step); a miss falls through to step 2 with one notice
   ("... using the project default"). The id itself is kept on the element.
2. The project default is `annotation_defaults[category]`, else `SYSTEM_DEFAULTS[category]`.
3. A project block with that id that is eligible wins.
4. Otherwise `bound_label.resolve_annotation_block` walks, for the mapped id and then the
   `SYSTEM_DEFAULTS` id: project registry -> System tier -> library roots
   (`block_library._find_by_id`, System tier first). A file hit is **embedded into the
   project on first resolve, outside undo** (`load_blocks_outside_history`), and accepted
   only when eligible (an ineligible file is never embedded).
5. Nothing resolves -> `None` (the tag draws the placeholder or nothing, section 2).

The resolver step lives in `Model_Space._resolve_mapped`. Its result is memoised in
`_annot_memo`, keyed `(category, mapped id, fallback)` -- the same id resolves differently
as a per-element id (`fallback=False`) and as the project default (`fallback=True`) -- and
cleared on `blockDefinitionsChanged` (`_on_block_definitions_changed`); the same handler
re-shapes every room tag through `refresh_room_tags()`, except while `_annot_resolving`
(the resolver itself embedding a file) -- the memo clear always runs.

A mapped id that is missing, not annotative, not Scale-with-zoom, or of the wrong
`host_category` is **treated as missing**: one log line plus one status-bar notice via
`_show_status` (the first view whose window has a status bar), remembered per
`(category, mapped id, fallback)` triple in `_annot_notified` so it fires once per triple,
not per memo life. A room pinned to the same missing id as the project default therefore
gets two distinct notices: the per-room miss ("using the project default") and the
default's own ("using the System default"). **The mapping stays in the file**, so a later
Reload or library fix can resolve it.
The notice fires at the **first resolve** of the mapping -- normally the eager resolve at
the end of a file load (`scene_io.load_from_file`), a template apply or a pane apply.
Known gap, filed: the notice is lost when no window has a status bar yet.

## 4. `SYSTEM_DEFAULTS` and ids

`system_blocks.SYSTEM_DEFAULTS = {"Room": "system-tags-roomtag"}` guarantees a fallback
for every converted category. Shipped ids are frozen **slugs**
(`system-<series>-<name>`, minted by `system_promote`; a re-promote keeps the id), **not
uuids** -- the concept's F4 wording "frozen uuids" is corrected by this pointer.
`LABEL_FIELD = {"Room": "Name"}` names the host field whose empty raw value means
"nothing to show". The shipped System file is never written by the app outside the
dev-gated Promote path (`block-system.md`).

## 5. The shipped RoomTag (`firepro3d/system_blocks/Tags/RoomTag.fpdb`)

User-authored 2026-10-28 and promoted to the System tier: host category Room, one host
attribute `Name` bound to the Room's `Name`, one bordered text `@[Name]` (3 mm Arial,
rounded border), Scale mode Annotative, On screen Scale with zoom, the text centre on the
block's y axis. It shows the **Name only** (Q1); the Mark stays a separate key the tag
does not read (`tests/test_sb2b_mark_storage.py::test_room_label_shows_name_not_mark`).
Mark or Area is a Block Editor edit of a copy, then a mapping change. The tag draws in
the block's **authored colours** (Automatic = theme ink); the Display Manager Room row
colour no longer tints it.

## 6. The hug rule for host-bound text (2026-10-29)

An author sizes a bound text box round the placeholder, so a wider value would wrap and a
shorter one would sit in a loose box. A host-bound text primitive therefore **auto-sizes
width and height round its resolved value**, anchored at the authored box's alignment
point (`block_attributes.hugged_text_record(rec, value)`): `wrap_width_mm` and
`box_height_mm` are dropped (0 = auto-fit) and `x` / `y` move so the auto box's
`align` x `valign` point stays where the authored box's was. Static text (no fields,
`keep_upright` included) and a record authored auto-fit on both axes are untouched; an
axis authored 0 keeps its position on that axis. The gate is "the record has fields".
`bound_text_ops` hugs before binding, and `block_explode` hugs before substituting, so an
exploded tag lands in the same box it was drawn in (explode parity). Guards:
`tests/test_sb3_bound_label.py` (`test_bound_text_box_*`, `test_exploded_bound_text_lands_in_the_hugged_box`).

## 7. `annotation_defaults`: model, persistence, pane

- **Model.** `Model_Space.annotation_defaults: dict[str, str]` (category -> block id).
  Keyed by category, not family.
- **`.fpd`.** `scene_io` writes and reads the `annotation_defaults` key (missing -> `{}`;
  non-str values dropped). **No `SAVE_VERSION` bump.** Legacy `show_label` and
  `label_offset` carry over unchanged (same frame: mm from the centroid).
- **Template (`.fpdt`).** `save_current_as_default` copies it; `apply_template_settings`
  overlays it onto the scene and **eagerly resolves/embeds** the mapped block (even for a
  pre-SB3 template with no key), so the embed never happens inside a `paint()`; a new
  project resolves System -> library roots -> `SYSTEM_DEFAULTS`.
- **Pane** (Project Settings > Annotation, `AnnotationPane`; rail list owned by
  [`settings-dialog.md`](settings-dialog.md)): one row per `ANNOTATION_CATEGORIES`.
  The choice list is `annotation_choices.choices` -- the **one home**, shared with the Room
  Tag row (section 8); `AnnotationPane.choices` is a wrapper over it. Entries: the
  project's eligible blocks, labelled "(Project)" (or "(System)" when the embedded block's
  library is System), then eligible shipped blocks the project has not embedded,
  "(System)", then eligible user-library `.fpdb` files the project has not embedded,
  "(Library)" (SB3b). The default row reads "RoomTag (System)". A current mapping that is
  missing or ineligible is kept as an extra "(missing)" / "(not eligible)" entry appended
  by the shared list. A "(Library)" pick is embedded outside history by the resolver
  (section 3) when the mapping is applied; the pane's apply stays non-undoable.
  `annotation_choices` caches its two disk walks (`shipped_defs`, `library_defs`) by a
  stat stamp of the `.fpdb` files -- `(path, mtime_ns, size)`, a directory scan only -- and
  its parse cache (`parsed_file`) by `(mtime_ns, size)`; `parsed_file` returns one shared
  **read-only** `BlockDefinition` (read name / library / eligibility off it, never register
  it into a scene). A library file with a duplicate id is not listed.
  `apply()` writes `scene.annotation_defaults` and fires `on_changed` (the main window's
  modified flag) **only when the effective mapping changed** (compared with
  `SYSTEM_DEFAULTS` applied); **no undo step** (project settings are not undoable).
  `revert()` restores the snapshot and refreshes the tags. Apply and revert drop the
  memo, embed the mapped blocks eagerly, then `refresh_room_tags()`.
  The Marks pane's matching modified-flag rule (Q5b) is owned by `settings-dialog.md`.

## 8. The Room tag

- **Ownership.** `Room` creates its tag (`self._tag = BoundLabelItem(self)`, Z_OVERLAY) and
  owns `show_label`, `label_offset` and persistence (fields:
  [`wall-room-floor-system.md`](wall-room-floor-system.md)). `Room._update_label` anchors the
  tag at centroid + `label_offset` and calls `tag.refresh()`; when `show_label` is off or
  the centroid is degenerate it hides the tag instead. A name change (`set_property`)
  refreshes it too.
- **Per-room tag block (SB3b).** `Room.tag_block` (a property over `_tag_block`; `None` =
  follows the project default, the value a new room has) names the block that draws this
  room's tag; `BoundLabelItem` resolves it first (section 3). A change of the project
  default therefore moves only the rooms whose `tag_block` is `None`. Persistence: a sparse
  `tag_block` key on the room record (written only when set; missing / non-str / empty ->
  `None`), on both serialization paths ([`wall-room-floor-system.md`](wall-room-floor-system.md)
  12.3; [`scene-io.md`](scene-io.md) 2). Copy/paste and Duplicate Level carry it (both
  rebuild rooms from `to_dict` through `paste_items`).
- **Tag row (SB3b).** The Room panel has a "Tag" enum row under Show Label. Its first entry
  is "Project default (<resolved block name>)" (= `None`); the rest are the shared list
  (`annotation_choices.choices`, section 7) including "(Library)" entries and the kept
  "(missing)" / "(not eligible)" entry for a pinned id that no longer resolves. The setter
  (`Room._set_tag`) maps the label back to a choice, embeds a "(Library)" file first
  (`blocks_browser.ensure_block_loaded`), assigns, and requests **one undo step**
  (`Model_Space.request_undo_push`; embed and assignment are the same step). A multi-room
  selection uses the first-target form with `< mixed >`; committing `< mixed >` (or any
  stale label) is a no-op ([`property-panel.md`](property-panel.md) 3.5).
- **Selection.** Click on the tag selects the **Room**. HALO and the rubber band treat a
  Room as a candidate by its **polygon's scene bbox** (`Model_Space._halo_room_hit`); the
  C1 label-rect restriction is retired (Q13; [`selection-mode.md`](selection-mode.md)).
- **Grip.** One move grip at the tag anchor (shown while the label is visible, the room is
  named and has a boundary) writes `label_offset` (`Room.apply_grip`); no rotate grip.
- **Paper.** The paper walk's Room branch routes the tag through
  `paper_display._apply_block(...)` (SB1c D6, the one annotative path), skipping a hidden
  tag, and restores it afterwards. `ROOM_LABEL_PAPER_CAP_MM` and
  `_apply_room_label_paper_height` are retired; `GRIDLINE_BUBBLE_PAPER_CAP_MM` stays until
  SB4b ([`paper-space.md`](paper-space.md) 9.9).
- **Visibility.** The Room row's visibility / opacity hide the tag with the room.
- **Refresh hooks.** `_refresh_all_labels` (units), `annotative.reprepare_annotative`
  (drawing scale) and the pane apply/revert walk the room tags through
  `refresh_room_tags()`.
- **Retired** (guard `tests/test_sb3_retired_strings.py`, AC11): the HTML room label,
  `_RoundedRectBgItem`, `_label_font_size`, `_label_font_color`, `label_scene_rect`, the
  HALO label-rect click and rubber-band special cases, `ROOM_LABEL_PAPER_CAP_MM`,
  `_apply_room_label_paper_height`, and the Display Manager Room row's font (the row
  carries `font: None`; `_category_has_font("Room")` is false).

## 9. Performance (G6)

Bar (Q7): at most 0.25 ms per labelled room on a full-view headless render (200 rooms
<= 50 ms, 1000 rooms <= 250 ms) and the 9-rooms-in-view zoom <= 25 ms
(`tests/test_sb3_perf.py`, `-m perf`, interleaved base/HEAD). The paint path stays inside
it through three things: the keyed host getters (only the bound keys run; `element-parameters.md`),
the pre-resolved definition passed into the annotative factor (SB1c design doc), and one
definition resolve per paint (`BoundLabelItem._state()`).

## 10. Guards (tests to run when touching this subsystem)

| Guard | Test file |
|---|---|
| AC10 ops/render digest parity of the lift | `test_sb3_parity.py` |
| G1 live binding, empty name paints nothing, degenerate centroid, cached rect, a non-label field (`@[Area]`) renders | `test_sb3_bound_label.py` |
| AC11 retired strings, DM Room row font | `test_sb3_retired_strings.py` |
| AC3/AC9 `annotation_defaults` round-trip (`.fpd`, `.fpdt`), pane | `test_sb3_annotation_defaults.py` |
| AC5 fallback to the shipped RoomTag + one notice | `test_sb3_system_default.py` |
| AC5 notice through the real window (own process) | `test_sb3_mainwindow.py` |
| AC4 paper mm at two scales; model = mm x drawing scale | `test_sb3_paper.py` |
| AC6 / G6 perf bar | `test_sb3_perf.py` (`-m perf`) |
| AC7 / G7 pixel lock of the approved tag | `test_sb3_pixel_lock.py` |
| Q1 the tag shows the Name, not the Mark | `test_sb2b_mark_storage.py::test_room_label_shows_name_not_mark` |
| SB3b G1 two rooms, two tag blocks (`test_g1_*`); G2 a missing per-room id falls back to the project default with one notice (`test_g2_*`); AC5 a default change moves only `None` rooms (`test_ac5_*`); AC6 `tag_block` round-trips file / undo / paste (`test_ac6_*`) | `test_sb3b_room_tag_style.py` |
| SB3b G6 / AC3 the pane lists the eligible library tag and embeds a pick outside history (`test_g6_pane_*`); the shared list keeps a missing / ineligible current (`test_shared_choices_keep_*`) | `test_sb3b_room_tag_style.py` |
| SB3b G3 / AC1 / AC2 Room Tag row: one undo step for two rooms, `< mixed >` no-op, undo / redo swap (`test_g3_*`); the "(Library)" pick embeds and assigns in one step (`test_g6_room_row_*`); the row shows "(missing)" / "(not eligible)" (`test_tag_row_shows_missing_*`) | `test_sb3b_room_tag_style.py` |
| SB3b review-fix guards: a room pinned to the same missing id as the default, both orders, two distinct notices (`test_i1_*`); the choice list walks the disk once per panel build and sees new library files (`test_i2_*`); `parsed_file` re-parses a same-mtime rewrite of a different size (`test_m1_*`); a failed library embed names the bare block and assigns nothing (`test_m2_*`); an ineligible per-room id falls back with one notice and the row says "(not eligible)" (`test_m4_*`) | `test_sb3b_room_tag_style.py` |
| L283 `display_overrides` survive undo / `.fpd` / paste for every holder, the Room included (it rides the same mixin helper) | `test_l283_display_overrides.py` |

**Proxy-only / partial coverage (SB3b acceptance, not fully guarded):**

- **AC4 "one resolve per paint"** has **no guard on the per-room (mapped) path**:
  `test_sb3_perf.py` times rooms with `tag_block = None` only. The invariant holds by
  construction (`BoundLabelItem._state()` resolves once per paint) but is not measured for a
  pinned room.
- **"Duplicate Level carries `tag_block` and `display_overrides`"** is guarded **by
  composition only**: the tests drive `paste_items(_clipboard_item_dicts(...))`, the path
  `copy_items_to_level` / `duplicate_level_entities` call, not those two entry points.

## Checkpoint 2026-10-29: PASSED

The concept's reassessment checkpoint (Q10/Q16) after build phase 3:

- [x] **G6 performance.** Idle-host re-bench 2026-10-29, 5 interleaved rounds, base
  `ab0edcd8` (HTML label) vs HEAD `7fa05c72`; medians base / HEAD: full view 200 rooms
  19.7 / 30.3 ms (bar 50), 1000 rooms 107.1 / 149.1 ms (bar 250), zoom 9 rooms
  6.7 / 8.0 ms (bar 25). HEAD worst runs 32.7 / 157.5 / 9.4 ms. Every bar met in 10/10 runs;
  HEAD/base ratio 1.5x / 1.4x / 1.2x. (An earlier loaded-host run at 1.9x failed one bar in
  3 of 5 runs; that drove the paint fix: keyed `host_values`, `defn` passthrough, one
  resolve per paint.)
- [x] **F1 static-geometry reuse: YES.** The tag paints the shared static variant list plus
  `bound_text_ops` glyphs rebuilt only on a resolved-string change.
- [x] **Spec amendments: a small set.** SB3 Account edited 12 files: this new spec, seven
  specs (`block-system`, `wall-room-floor-system`, `paper-space`, `settings-dialog`,
  `model-space-containment-contract`, `element-parameters`, `selection-mode`),
  `SPEC-INDEX`, and three design docs (the concept, the SB1c design, the SB3 slice design).
- **Verdict: PASS** (ratified by the user 2026-10-29). **SB4a-e are unblocked.**

Contradictions found during the build, and their resolution:

| # | Contradiction | Resolution |
|---|---|---|
| a | Slice design: a missing block draws the red orphan placeholder; but a nameless room with no resolvable block would show a placeholder for nothing | Draws nothing (ratified); the placeholder needs a label to lose (section 2) |
| b | Concept F4: "frozen uuids" | Frozen slugs (section 4) |
| c | Bound text inside an authored fixed-width box wrapped the value | The hug rule (section 6) |
| d | Slice AC5: "load notice" | Holds: the notice fires at the first resolve, which a file load triggers eagerly (section 3) |
| e | SB1c D10/D11: rooms keep a fixed model size and a paper cap | Superseded: annotative everywhere (Q2) |
| f | Concept: `annotation_defaults` "cloned from the template" | Holds (section 7) |

## Build order after the checkpoint

Phase 3 (this slice) is **done**, as is SB3b (per-room tag style, library-folder picker;
2026-10-30). Phase 4 is the follow-up per remaining intrinsic
conversion, SB4a-e (todo lines; each user-designed and visually gated, G7). Phases 5-7
(uids and hosting, placed tags, sheet tags) are gated on phase 4 and described in the
concept.
