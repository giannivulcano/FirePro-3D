---
status: partial          # SB3 (room tag) BUILT 2026-10-29, checkpoint PASSED; SB3b (per-room tag style) BUILT 2026-10-30; SB4a (pipe label: top-level host-bound label + Hide when empty) BUILT 2026-11-01; SB4b (plan gridline bubble: child label per end, outline trim, Tag row) BUILT 2026-11-03; SB4c (elevation / section gridline bubbles + level datum head as System blocks) BUILT 2026-11-03; SB4d (view-marker heads: cardinal elevation head, placed-section head, detail callout) BUILT 2026-11-04; SB4f (sheet viewport view title as a System block, plus the viewport Number the section / detail heads cite) BUILT 2026-11-04; SB4e (remaining intrinsic labels), placed tags (phase 6) and sheet tags (phase 7) are not built
last-verified: 2026-11-05  # section piping Account: s8a section label note only, rest not re-audited; prior 2026-11-04  # SB4f Account: new s8e (sheet viewport view title), s8d reversal (heads bind Number, PAINT_WHEN_BLANK), s1 / s2 / s3 / s4 / s7 / s10 / header / applies-to re-audited against dab5a2f2; rest not re-audited; prior 2026-11-04  # SB4d Account: new s8d (view-marker heads), header / ownership / applies-to / guards table, s1 / s2 / s8 Room-tag top-level + category count; rest not re-audited; prior 2026-11-04  # text leaders Account: Note block ownership pointer only, rest not re-audited; prior 2026-11-03  # SB4c Account: s1/s2/s3/s4/s7/s8/s8b/s8c (new Elevation bubbles + level datum head section)/s10/build order re-audited against 8d95a864; prior 2026-11-03  # SB4b Account: s1/s2/s3/s4/s7/s8/s8b (new Gridline section)/s10 re-audited against 7b6e90fc; prior 2026-11-02  # text-sizing-wrap Account: s6 hug rule re-pointed at the Shrink flag (hugged_text_record seeds Wrap OFF + Shrink ON) only, rest not re-audited; prior 2026-11-01  # SB4a Account: s1/s2/s3/s4/s5a/s6a/s7/s8/s8a/s10 re-audited against 0924bcd6; prior 2026-10-30 (SB3b), 2026-10-29 (SB3 promotion from the concept)
verified-commit: 539eda40  # section piping on main (v0.91.0); prior dab5a2f2  # SB4f on main (v0.87.0); prior 5185b8cc  # SB4d merge on main (v0.86.0) + seed restyle; prior 820f47c8  # text leaders merge on main (v0.85.0); prior 8d95a864  # SB4c merge on main (v0.83.0); prior 7b6e90fc  # SB4b merge on main (v0.81.0); prior 6693013b  # merge feat/text-sizing-wrap (v0.80.0); prior 0924bcd6   # SB4a merge on main; prior 7e5d3b15 (SB3b), 8be9034a (SB3)
applies-to:
  - firepro3d/bound_label.py          # BoundLabelItem, OutlinedLabel (SB4c), TagBlockHost, eligible_definition, resolve_annotation_block
  - firepro3d/section_scene.py        # SB4c: ElevGridlineItem bubbles, LevelDatumHead / ElevDatumItem, SectionScene.annotation_block + refresh_annotation_tags (the block side; the section projection is section-view-subsystem.md)
  - firepro3d/annotation_choices.py   # SB3b: the one shared picker list (pane + Room Tag row), disk-walk / parse caches
  - firepro3d/system_blocks.py        # SYSTEM_DEFAULTS, ANNOTATION_CATEGORIES, LABEL_FIELD, PAINT_WHEN_BLANK
  - firepro3d/system_blocks/Tags/     # the shipped RoomTag + PipeLabel + GridlineBubble + LevelDatum + ElevationHead + SectionHead + DetailCallout + ViewTitle .fpdb (SB4f: SectionHead / DetailCallout bind Number)
  - firepro3d/view_title_label.py     # SB4f: ViewTitleLabel(OutlinedLabel) (the sheet viewport's title + composite line, hit forwarding), extent_below_box (the drop clamp)
  - firepro3d/view_marker_head.py     # SB4d: ViewMarkerHead(OutlinedLabel), enclosing_radius (the marker heads; marker geometry stays with section-view-subsystem.md)
  - firepro3d/section_marker.py       # SB4d: head / head_a / head_b, R_k-sized wedge + triangle (rest under section-view-subsystem.md)
  - firepro3d/detail_view.py          # SB4d: DetailMarker.bubble, _paint_callout (rest under view-relationships.md)
  - firepro3d/block_attributes.py     # bound_text_ops, hugged_text_record, blank_keys / collapse_shifts / hide_empty_shifts (Hide when empty)
  - firepro3d/pipe.py                 # the Pipe owns its label, tag_block, update_label / sync_label_z
  - firepro3d/gridline.py             # SB4b: GridlineBubble(OutlinedLabel) (child label, duplicate ring), GridlineItem(TagBlockHost), sparse tag_block
  - firepro3d/network_codec.py        # sparse pipe tag_block (serialize_pipe / deserialize_pipe)
  - firepro3d/text_item.py            # TextData.hide_empty + the Block Editor checkbox
  - firepro3d/render_op.py            # paint_ops (lifted from BlockInstance.paint)
  - firepro3d/room.py                 # the Room owns its tag, show_label, label_offset
  - firepro3d/model_space.py          # annotation_defaults, annotation_block, refresh_annotation_tags, annotationLabelsChanged (SB4f)
  - firepro3d/scene_io.py             # annotation_defaults key; SB4f: _refresh_view_head_copies (the D2 head swap on load)
  - firepro3d/paper_space.py          # SB4f: PaperScene.annotation_block / refresh_annotation_tags, the viewport's ViewTitleLabel wiring (rest: paper-space.md)
  - firepro3d/settings/panes.py       # AnnotationPane
  - firepro3d/settings/template.py    # annotation_defaults in the .fpdt
  - firepro3d/paper_display.py        # the tag through _apply_block
  - firepro3d/block_explode.py        # explode hugs bound text before substituting; honours hide_empty
  - firepro3d/display_manager.py      # Room + Pipe rows: font None; Grid Line row: fill None, no Scale, `_apply_gridline` tints the line only; Level Datum row: fill None, font None, no Scale (SB4c; the row rule is homed in grid-system.md 10.1); Elevation / Section / Detail Marker rows: line-only, same shape (SB4d)
source-tasks:
  - "SB4f -- Convert the sheet viewport view title to a System block, with a per-viewport show/hide toggle for the title (todo_closed.md; design record superpowers/specs/2026-11-04-sb4f-view-title-design.md)"
  - "SB4d -- Convert the elevation-marker head and the detail-callout bubble to System blocks + the annotation band (todo_closed.md; design record superpowers/specs/2026-11-03-sb4d-view-marker-heads-design.md)"
  - "SB4c -- Convert the elevation gridline bubble + level datum head to System blocks (todo_closed.md; design record superpowers/specs/2026-11-03-sb4c-elev-bubble-datum-design.md)"
  - "SB4b -- Convert the plan gridline bubble to a System block (todo_closed.md; design record superpowers/specs/2026-11-02-sb4b-gridline-bubble-design.md)"
  - "SB4a -- Convert the pipe label to a System block (todo_closed.md; design record superpowers/specs/2026-10-31-sb4a-pipe-label-design.md)"
  - "SB3 -- First vertical slice: room tag drawn by a System block via BoundLabelItem + the Project Settings Annotation defaults pane (todo_closed.md)"
  - "System Blocks -- author the app's own 2D annotation graphics ... (concept, 2026-09-29)"
---

# System Blocks -- Spec (intrinsic labels drawn by annotation blocks)

> **Status: partial.** This spec is the consolidating contract for what is **built**:
> the host-bound label seam (`BoundLabelItem`), block resolution with a guaranteed
> fallback (`annotation_block`), the Project Settings Annotation pane, and the first
> conversion (the Room tag) the second (the Pipe label, SB4a), the third (the plan Gridline bubble, SB4b) and the fourth (the elevation / section gridline bubbles and the level datum head, SB4c). It was promoted from the concept
> [`2026-09-29-system-blocks-concept-design.md`](../superpowers/specs/2026-09-29-system-blocks-concept-design.md)
> on 2026-10-29; that document is kept as **history** (the grill Q1-Q16, the
> architecture F1-F8, the not-yet-built phases 4-7). The slice's own design record is
> [`2026-10-28-sb3-room-tag-slice-design.md`](../superpowers/specs/2026-10-28-sb3-room-tag-slice-design.md)
> (ratified decisions Q1-Q13, D-A..D-E). Not built: the remaining intrinsic labels
> (SB4e), placed tags (concept F7, Tag tool), sheet-scoped tags. **SB3b (built
> 2026-10-30)** adds the per-room tag block (`Room.tag_block`, sections 3 / 8) and the
> shared picker list that also widens the Annotation pane to the user library (section 7).
> **SB4a (built 2026-11-01)** converts the pipe label (section 8a): a top-level
> host-bound label, the `TagBlockHost` mixin shared with Room, and the generic
> *Hide when empty* text option (section 6a). Its design record is
> [`2026-10-31-sb4a-pipe-label-design.md`](../superpowers/specs/2026-10-31-sb4a-pipe-label-design.md)
> (D1-D11).
> **SB4b (built 2026-11-03)** converts the plan gridline bubble (section 8b): a child
> label per gridline end, the line trimmed at the block outline, and the Tag row on the
> gridline. Its design record is
> [`2026-11-02-sb4b-gridline-bubble-design.md`](../superpowers/specs/2026-11-02-sb4b-gridline-bubble-design.md)
> (D1-D15, kept as history; the contract now lives here and in [`grid-system.md`](grid-system.md) 4.2).
> **SB4c (built 2026-11-03)** draws the elevation / section gridline bubbles with the plan
> gridline's block and makes the level datum head a System block (section 8c). Its design
> record is [`2026-11-03-sb4c-elev-bubble-datum-design.md`](../superpowers/specs/2026-11-03-sb4c-elev-bubble-datum-design.md)
> (D1-D6, with an As-built section; the contract now lives here, in [`grid-system.md`](grid-system.md)
> 8 / 10.1 and in [`section-view-subsystem.md`](section-view-subsystem.md)).
> **SB4d (built 2026-11-04)** draws the three view-marker heads (cardinal elevation, placed
> section, detail callout) with System blocks and puts every annotation in one z band above the
> model (section 8d; the band itself is owned by `view-relationships.md` 7.3). Its design record is
> [`2026-11-03-sb4d-view-marker-heads-design.md`](../superpowers/specs/2026-11-03-sb4d-view-marker-heads-design.md)
> (D1-D8, with Phase 4 reconciliations; the contract now lives here).
> **SB4f (built 2026-11-04)** draws the title under each sheet viewport with a System block and makes
> the viewport number the one the section / detail heads cite (section 8e; section 8d's Mark slot is
> reversed). Its design record is
> [`2026-11-04-sb4f-view-title-design.md`](../superpowers/specs/2026-11-04-sb4f-view-title-design.md) (G1-G12, D1-D6; the contract now lives here and in
> [`paper-space.md`](paper-space.md) 5.2 / 9.9).

## Ownership (Rule A)

- The shipped Note block (`system_blocks/Annotations/Note.fpdb`, a view-owned note, no host category): [text leaders design D8](../superpowers/specs/2026-11-04-text-leader-annotations-design.md).

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
- Paper pass, and the sheet viewport that hosts the view title (data, geometry, grip, panel, drop dialog, PDF): [`paper-space.md`](paper-space.md) 5.2 / 9.9 / 19.4. Units: [`units-and-formatting.md`](units-and-formatting.md).
- Containment: [`model-space-containment-contract.md`](model-space-containment-contract.md) C9.
- Room fields and persistence: [`wall-room-floor-system.md`](wall-room-floor-system.md).
- Pipe fields, geometry and the placement preview: [`pipe-placement-methodology.md`](pipe-placement-methodology.md).
- Gridline fields, geometry, grips, lock and the Display Manager line tint: [`grid-system.md`](grid-system.md).
- Selection: [`selection-mode.md`](selection-mode.md). Z-order: `view-relationships.md` 7.3 + `constants.py`.

## 1. Two kinds of annotation, one graphic source

An **intrinsic label** is owned by its element, automatic, toggled per element, and
needs no persisted reference: it is drawn by a `BoundLabelItem` the host owns (a child
for Gridline, Level, the view-marker heads and the sheet viewport's view title, a top-level item for Pipe and (since SB4d, so it clears model items at any elevation -- `view-relationships.md` 7.3) Room -- section 2).
A **placed tag** is a standalone hosted instance (concept F7) and is **not built**.
Both are drawn by blocks authored in the one Block Editor. Today eight categories
are converted: `Room`, `Pipe`, `Gridline`, `Level`, `Elevation`, `Section`, `Detail` and `View Title` (`system_blocks.ANNOTATION_CATEGORIES == ("Room", "Pipe", "Gridline", "Level", "Elevation", "Section", "Detail", "View Title")`; the three before the last are section 8d, `View Title` is section 8e).

## 2. `BoundLabelItem` (`bound_label.py`)

A lightweight `QGraphicsItem`, **not** a `BlockInstance` subclass (SB3 D-A: no
`isinstance(BlockInstance)` leakage into HALO, snaps, the level filter or the
block-instance list).

- **Host and data.** `BoundLabelItem(host, *, child=True, parent=None)`: a child of the host by
  default (Gridline, the datum head, the view-marker heads); `child=False` makes a **top-level** item (Pipe, SB4a D1; Room, SB4d D5 -- the room syncs it from its `itemChange`, so the tag sits in the annotation band, `view-relationships.md` 7.3);
  a given `parent` is the graphics parent while `host` stays the data source (SB4c D1: an
  elevation bubble is a child of its `ElevGridlineItem` and reads the PLAN gridline). Either way
  `host` is the explicit `_host`, never `parentItem()`. The host is the data
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
- **Orphan box size.** `placeholder_mm` is a class attribute (default `bound_label.PLACEHOLDER_MM`) read at the
  three orphan-box sites (bounds, paint, outline); a sheet-native label overrides it (`ViewTitleLabel`, section 8e).
- **Paints nothing** when (a) every host-bound string resolves to raw `None` (a nameless
  room) -- except for `system_blocks.PAINT_WHEN_BLANK` categories (`Gridline`, SB4b D3; the full list is in section 4), whose
  static ops still draw with the bound text empty -- or (b) the host hides it -- the Room does so when its centroid is degenerate
  (no boundary included; `Room._update_label`), or the Pipe when Show Label is off, the
  pipe is vertical or hidden (section 8a). A tag whose block resolves nowhere draws the red orphan placeholder
  **only** when the scene has a resolver **and** the host has a label to lose
  (`LABEL_FIELD[category]` present with a non-None raw value); a nameless room with no
  resolvable block draws nothing (ratified 2026-10-28, checkpoint contradiction (a)).
- **Not** selectable, movable or snappable; invisible to HALO, snaps, the level filter
  and the block-instance list; **never serialized** (the host owns `show_label`,
  `label_offset` and `tag_block`).
- **Paper hooks.** `_paper_scale`, `_paper_pen_width`, `_paper_pen_color` are set by
  `paper_display._apply_block` during a viewport pass (section 8).
- **Dead host.** `host_values` returns `None` for a host that is no longer live, a category
  mismatch, or a cross-scene host whose C++ object is already gone (a plan gridline deleted
  under an open section, SB4c D1): bound fields then show their placeholders (E9) and the
  orphan placeholder box is **not** drawn (it needs a live host value), so nothing raises.
- **`OutlinedLabel(BoundLabelItem)`** (SB4c D1, lifted from SB4b's `GridlineBubble`): the
  outline / trim / overlay machinery shared by labels whose host trims a line at the block
  outline. `outline_path()` = the union of the closed subpaths of the block's static ops at
  the current k (text ops ignored; the orphan placeholder box when the block resolves nowhere;
  the bounds rect when nothing closes), cached until `refresh()` or a paper-scale change; the
  union operands are snapped to `WALL_OUTLINE_SNAP` first, because a Block Editor restyle
  leaves ~1e-12 noise on coincident corners and Qt's clipper then returns an empty union.
  `trim_distance(ux, uy)` = the distance from the block origin along the unit direction to where
  it leaves the outline (0 when the origin is outside it). `overlay_pens()` (base: none) lists
  the screen-only rings stroked round the outline after the ops, none during a paper pass.
- **Subclasses.** A host may subclass the label for category-specific behaviour:
  `GridlineBubble(OutlinedLabel)` (section 8b, 8c) adds the duplicate flag and its rings;
  `LevelDatumHead(OutlinedLabel)` (section 8c) adds the datum's selection ring.
- **One implementation of bound text and op painting.** `block_attributes.bound_text_ops`
  and `render_op.paint_ops` were lifted from `BlockInstance`; `BlockInstance` wraps them.
  Guard: the AC10 ops/render digests (`tests/test_sb3_parity.py`).
- **Static-geometry reuse (F1).** The tag paints `defn.render_ops_variant(False, k)` (the
  shared static list) plus the `bound_text_ops` glyphs, rebuilt only when a resolved
  string changes. `_state()` resolves the definition and host values once per paint.
- **Hide when empty.** A bound text carrying `hide_empty` is dropped from the ops (glyphs,
  border, fill) when every host field it names is blank, and the bound texts beyond it
  close the slot (section 6a).

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

**Section scenes (SB4c D1).** A label in a `SectionScene` (an elevation bubble, a datum head)
resolves through `SectionScene.annotation_block(category, mapped=None)`, which forwards to the
model scene's `annotation_block` -- one resolver, one memo, one notice set; it returns `None`
(placeholder / nothing, section 2) when the model scene is already gone (a queued paint during
teardown). The `mapped` id is read from the label's data host (`tag_block`), so an elevation
bubble follows its plan gridline's Tag row.

**Paper scenes (SB4f).** A label on a sheet resolves through `PaperScene.annotation_block(category,
mapped=None)`, the same forwarder pattern: it calls the model scene's `annotation_block` (the paper scene's
block-registry owner) and returns `None` when that scene is already gone. The sheet's view title is the one
consumer (section 8e).

The resolver step lives in `Model_Space._resolve_mapped`. Its result is memoised in
`_annot_memo`, keyed `(category, mapped id, fallback)` -- the same id resolves differently
as a per-element id (`fallback=False`) and as the project default (`fallback=True`) -- and
cleared on `blockDefinitionsChanged` (`_on_block_definitions_changed`); the same handler
re-shapes every intrinsic label (room tags, pipe labels, plan gridline bubbles, and every open
section's elevation bubbles and datum heads) through `refresh_annotation_tags()`, except while `_annot_resolving`
(the resolver itself embedding a file) -- the memo clear always runs. `refresh_annotation_tags` ends by emitting
`Model_Space.annotationLabelsChanged`; the live `PaperSpaceWidget` connects it to `PaperScene.refresh_annotation_tags`,
so every sheet view title re-shapes with the rest (section 8e).

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

`system_blocks.SYSTEM_DEFAULTS` (`"Room"` -> `"system-tags-roomtag"`, `"Pipe"` ->
`"system-tags-pipelabel"`, `"Gridline"` -> `"system-tags-gridlinebubble"`, `"Level"` ->
`"system-tags-leveldatum"`, plus the SB4d heads (section 8d) and `"View Title"` -> `"system-tags-viewtitle"`, SB4f) guarantees a fallback for every converted category. Shipped ids are frozen **slugs**
(`system-<series>-<name>`, minted by `system_promote`; a re-promote keeps the id), **not
uuids** -- the concept's F4 wording "frozen uuids" is corrected by this pointer.
`LABEL_FIELD` (`"Room"` -> `"Name"`, `"Pipe"` -> `"Diameter"`, `"Gridline"` -> `"Mark"`, `"Level"` -> `"Level.Name"`, the SB4d heads (section 8d), `"View Title"` -> `"Scale"`; a pipe's Diameter is never
`None`, so a pipe whose block resolves nowhere draws the red placeholder) names the host field whose empty raw value means
"nothing to show". `PAINT_WHEN_BLANK` (`frozenset({"Gridline", "Elevation", "Section", "Detail"})`; the last two since SB4f, section 8d) lists the categories whose static geometry still draws when every host-bound field is blank (section 2); `"Level"` is not listed, because `Level.Elevation` is never `None`, so a datum head never has every field blank. The shipped System file is never written by the app outside the
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

## 5a. The shipped PipeLabel (`firepro3d/system_blocks/Tags/PipeLabel.fpdb`)

Id `system-tags-pipelabel`; host category Pipe, Scale mode Annotative, On screen Scale
with zoom; four host attributes bound to the Pipe's `Diameter`, `Length`, `Flow` and
`FrictionLoss`, one text each (`@[Diameter]` above the origin, `@[Length]` below, then
`@[Flow]` and `@[FrictionLoss]`, the last two *Hide when empty*). Colours are authored
(Diameter / Length Automatic; Flow and FrictionLoss fixed colours); the Display Manager
Pipe colour tints the pipe only. Field keys, raw units and the 3D `Length`:
`element-parameters.md`.

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

*As of 2026-11-02 the hug is the text's own Shrink to fit:* `hugged_text_record` no longer resizes the
record; it writes the seeded flags (Wrap OFF + Shrink ON unless authored) and `TextItem`
lays the box out round the value, keeping the authored alignment point. An author may turn
Shrink off on a bound text. Contract: [`superpowers/specs/2026-11-01-text-sizing-wrap-design.md`](../superpowers/specs/2026-11-01-text-sizing-wrap-design.md) D4 / D5 (G12, G13).

## 6a. Hide when empty (SB4a)

`TextAnnotationData.hide_empty` (default `False`, serialized sparse like `keep_upright`)
is a Block-Editor-only checkbox ("Hide when empty", beside *Keep upright* in
`TextItem.get_properties`); a plan-view text ignores it. A host-bound text with
`hide_empty` whose every `@[key]` is **blank** is dropped by `bound_text_ops`. Blank = a
host-sourced attribute with no instance override whose host value is `None` or has raw
`None` (`block_attributes.blank_keys`; `BlockInstance._bound_values` keys on values plus
blanks, so a blank change re-shapes). Each remaining bound text **on the same side of the
block origin (block y axis; a box's side is its centre's) beyond a dropped box moves
toward the origin by the dropped box's slot** (its near edge to the near edge of the next
box beyond it); a dropped box centred on the origin closes nothing; static primitives
never move (`collapse_shifts` / `hide_empty_shifts` -- the one rule). `block_explode`
applies the same rule, so an exploded label lands where it was drawn (explode parity);
it threads the outermost host's blanks through the flatten recursion. Bounds shrink
through `_compute_rect`.

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
  "(Library)" (SB3b). The Room default row reads "RoomTag (System)", the Pipe row "PipeLabel (System)", the Gridline row "GridlineBubble (System)", the Level row (labelled "Level tag") "LevelDatum (System)" (the project default only: the datum has no per-level Tag row, section 8c). The View Title row (labelled "View Title tag") reads "ViewTitle (System)" (SB4f; the project default only, section 8e). A current mapping that is
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
  memo, embed the mapped blocks eagerly, then `refresh_annotation_tags()`.
  The Marks pane's matching modified-flag rule (Q5b) is owned by `settings-dialog.md`.

## 8. The Room tag (and the shared Tag row)

- **Ownership.** `Room` creates its tag (`self._tag = BoundLabelItem(self, child=False)`, a
  **top-level** item in the annotation band's tag sub-band since SB4d, `view-relationships.md`
  7.3; `Room.itemChange` joins / leaves the room's scene, follows its visibility and opacity)
  and owns `show_label`, `label_offset` and persistence (fields:
  [`wall-room-floor-system.md`](wall-room-floor-system.md)). `Room._update_label` anchors the
  tag (in scene coordinates) at centroid + `label_offset` and calls `tag.refresh()`; when `show_label` is off or
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
- **Tag row (SB3b; shared since SB4a).** The `TagBlockHost` mixin (`bound_label.py`) owns
  `tag_block`, `_tag_row()` and `_set_tag()` for every host with a tag (Room, Pipe, Gridline); a
  host sets `_TAG_CATEGORY` and implements `_tag_changed()` (Room: `tag.refresh()`; Pipe:
  `update_label()`; Gridline: `_tag_changed` refreshes both bubbles and re-shapes the line). The Room panel has a "Tag" enum row under Show Label. Its first entry
  is "Project default (<resolved block name>)" (= `None`); the rest are the shared list
  (`annotation_choices.choices`, section 7) including "(Library)" entries and the kept
  "(missing)" / "(not eligible)" entry for a pinned id that no longer resolves. The setter
  (`TagBlockHost._set_tag`) maps the label back to a choice, embeds a "(Library)" file first
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
  `_apply_room_label_paper_height` are retired ([`paper-space.md`](paper-space.md) 9.9).
- **Visibility.** The Room row's visibility / opacity hide the tag with the room.
- **Refresh hooks.** `_refresh_all_labels` (units), `annotative.reprepare_annotative`
  (drawing scale) and the pane apply/revert walk every intrinsic label (room tags, pipe
  labels, gridline bubbles, and every open section's elevation bubbles and datum heads,
  section 8c) through `Model_Space.refresh_annotation_tags()` (the former `refresh_room_tags`).
- **Retired** (guard `tests/test_sb3_retired_strings.py`, AC11): the HTML room label,
  `_RoundedRectBgItem`, `_label_font_size`, `_label_font_color`, `label_scene_rect`, the
  HALO label-rect click and rubber-band special cases, `ROOM_LABEL_PAPER_CAP_MM`,
  `_apply_room_label_paper_height`, and the Display Manager Room row's font (the row
  carries `font: None`; `_category_has_font("Room")` is false).

## 8a. The Pipe label (SB4a)

**In sections and elevations (2026-11-05).** `SectionScene` builds its own top-level label
(`_ElevPipeLabel`, a `BoundLabelItem` hosted on the model pipe) per rebuild. Its line proxy owns
it for the paper pass and Hide, and it is neither selectable nor framed. Which pipes get one:
[`section-view-subsystem.md`](section-view-subsystem.md) s5.

- **Ownership.** `Pipe` creates its label (`self.label = BoundLabelItem(self, child=False)`)
  and owns `Show Label`, `tag_block` and the lifecycle; the label is a **top-level** scene
  item (a child cannot draw above an item stacked above its parent, so a child would hide
  under nodes). `Pipe.update_label()` is the single entry (solve, clear, Diameter,
  geometry, Display Manager all call it): adds the label to the pipe's scene, hides it
  when the pipe is hidden, Show Label is off or the pipe is vertical, else anchors it at
  the pipe midpoint and rotates the **whole label** to the pipe angle kept in [-90, 90)
  (`label._pose_rot`, so an authored `keep_upright` text still reads upright). The
  removal sites remove `pipe.label` with the pipe.
- **Z.** `Pipe.sync_label_z()` sets the label to `max(Z_OVERLAY, pipe z + Z_LABEL_ABOVE_PIPE)`
  (`constants.py`); the level manager's elevation z pass re-syncs it, so the label stays
  above its pipe, nodes, sprinklers and fittings at any elevation. Z ladder:
  `view-relationships.md` 7.3.
- **Content.** Drawn by the block mapped for Pipe (section 3, default PipeLabel, section
  5a). Pipe `Flow` / `Velocity` / `FrictionLoss` read `None` when the solve did not reach
  the pipe or gave it zero flow (`element-parameters.md` E7), which is what *Hide when
  empty* keys on; `Length` is the 3D length.
- **Tag row / persistence.** The Pipe panel's "Tag" enum row sits under Show Label
  (`TagBlockHost`, section 8; one undo step, `< mixed >` no-op). `tag_block` is a sparse
  key in `network_codec.serialize_pipe` / `deserialize_pipe` (the one codec for `.fpd` and
  the undo snapshot; missing / non-str / empty -> `None`); no `SAVE_VERSION` bump. Pipe
  split (`pipe_network_controller`) and `Pipe.set_properties` (template) carry the id.
  Copy/paste of a pipe carries **no** pipe properties at all (pre-existing, filed) --
  `tag_block` included.
- **Paper.** The paper walk's Pipe branch routes a visible label through
  `paper_display._apply_block(...)` with opacity 1 (the one annotative path, as Room);
  `restore_model_display` restores the label's paper hooks. The old forced label colour
  (`pipe_label_color`) is gone ([`paper-space.md`](paper-space.md) 9.9).
- **Retired** (guard `tests/test_sb4a_retired_strings.py`): the HTML pipe label,
  `QGraphicsTextItem` label, `Pipe.set_label_position`, the `Label Size` property (a legacy
  file's key is dropped by `Pipe.set_property`'s unknown-key skip), the fixed
  `#00aaff` / `#ffaa00` colours, and the Display Manager Pipe row's font (`font: None`;
  `_apply_pipe` has no `font_size` path). The placement preview label keeps a fixed
  `constants.PIPE_PREVIEW_LABEL_IN` ([`pipe-placement-methodology.md`](pipe-placement-methodology.md)).

## 8b. The Gridline bubble (SB4b)

Gridline-side behaviour (geometry, grips, lock, Properties rows, serialization) is owned by
[`grid-system.md`](grid-system.md) 4.2; this section holds the block-side contract.

- **Ownership.** `GridlineItem` (a `TagBlockHost`, `_TAG_CATEGORY = "Gridline"`) creates one
  `GridlineBubble(OutlinedLabel)` per end (`bubble1` / `bubble2`, `child=True`: visibility,
  opacity and z cascade from the gridline). `_rebuild_geometry` calls `set_anchor` at each
  standoff; the bubble is **never rotated**, so it stays upright on an angled gridline.
  Per-end visibility stays `bubbleN.isVisible()`.
- **Content.** Host field `Mark` (`LABEL_FIELD["Gridline"]`) -- the gridline's label. The
  panel row is named `Mark` and a blank Mark is refused there (`element-parameters.md` M2 /
  M16), but a blank can still arrive from an old file or Renumber: `PAINT_WHEN_BLANK` keeps the
  block's static geometry, and the shipped seed's Mark placeholder `-` shows in the circle.
- **Outline and trim.** `outline_path()` / `trim_distance(ux, uy)` are `OutlinedLabel`'s (section
  2). `GridlineItem.drawn_endpoints()` trims each visible end by it, on screen and on paper, so
  the line meets any block shape, not only the circle.
- **Hit and HALO.** `GridlineItem.shape()` = the stroked line plus both visible outlines (a
  press on a bubble selects the gridline; the label accepts no buttons); `halo_trace_path` =
  the trimmed line plus both outlines; `halo_area_path` = the outlines. Snaps skip the child
  bubbles (parent not None), as before.
- **Overlays (screen only, never on paper).** `GridlineBubble.overlay_pens()` (the `OutlinedLabel` hook): selected gridline
  -> the outline stroked `_grid_color.lighter(150)`, cosmetic 2 px; duplicate Mark -> stroked
  `#ff8800`, cosmetic, drawn last. Both are skipped while the gridline's `_paper_render` is set.
- **Tag row / persistence.** The Gridline panel's "Tag" enum row sits under Bubble 2 Offset (not
  on the off-scene placement template: it would show only the default); both ends share the
  mapped block. `tag_block` is a sparse key in `GridlineItem.to_dict` / `from_dict` (the one
  serializer for `.fpd`, undo and paste); `_clone_parallel` (offset / array copies) carries it.
  No `SAVE_VERSION` bump.
- **Display Manager.** The Grid Line row has `fill: None`, is in `_NO_SCALE_CATEGORIES`, and
  `display_manager._apply_gridline` tints the **line** colour + opacity + visibility only; a
  saved Fill / Scale is ignored. The bubble keeps its authored colours.
- **Paper.** The paper walk's Gridline branch styles the line (`paper_display._apply_gridline`:
  weight + paper-mm dash) and routes each visible bubble through `_apply_block(...)` with
  opacity 1; `restore_model_display` restores the block hooks. The old paper-mode geometry
  swap is retired ([`paper-space.md`](paper-space.md) 9.9.1).
- **Refresh.** `refresh_annotation_tags` walks every gridline's bubbles and re-shapes the
  gridline (`prepareGeometryChange`), because the trim moves with the block and k.
- **Shipped seed** `firepro3d/system_blocks/Tags/GridlineBubble.fpdb` (id
  `system-tags-gridlinebubble`; host category Gridline; Annotative, On screen Scale with zoom):
  a 10 mm circle with centre / diameter constraints, a centred Shrink-to-fit `@[Mark]` text
  (Consolas bold, Automatic colours), Mark placeholder `-`. User-designed at the SB4b smoke.
- **Elevation / section bubbles** draw the same block through section-scene children of the
  elevation gridline: section 8c.
- **Retired** (guard `tests/test_sb4b_retired_strings.py`): `GridBubble`, `RADIUS_PX`,
  `enter_paper_mode` / `exit_paper_mode`, the plan use of `bubble_paper_geometry` and
  `_paper_bubble_r`, the `scene_scale` bubble radius in `halo_trace_path`, the gridline's
  `_display_scale`, and the Display Manager Grid Line Fill / Scale. (`bubble_paper_geometry`,
  `_paper_bubble_r` and the paper-cap constants are fully gone since SB4c, section 8c.)

## 8c. Elevation bubbles + level datum head (SB4c)

Section / elevation geometry (projection, crop, the datum and gridline lines) is owned by
[`section-view-subsystem.md`](section-view-subsystem.md); the gridline-side rules (per-end
visibility, Z-extent overrides) by [`grid-system.md`](grid-system.md) 8; the Display Manager
Level Datum row by `grid-system.md` 10.1. This section holds the block-side contract. The
decisions D1-D6 and their as-built corrections are in
[`2026-11-03-sb4c-elev-bubble-datum-design.md`](../superpowers/specs/2026-11-03-sb4c-elev-bubble-datum-design.md)
(history; Rule A). Concept Q9 composite rule: heads only; the lines and extents stay bespoke in
`section_scene.py`. Datum line + head as one linear block is deferred to SB8.

- **Ownership.** `ElevGridlineItem(..., gridline=gl)` keeps the PLAN `GridlineItem` and owns two
  `GridlineBubble(gl, parent=self)` children: `bubble1` at the top end (`line().p1()`, plan
  Bubble 1) and `bubble2` at the bottom (plan Bubble 2). The plan gridline is the **data host**
  (`BoundLabelItem`'s `parent=`, section 2), so each bubble draws that gridline's resolved
  block (`tag_block`, else the project default, section 3) with its live `@[Mark]`, annotative
  (k = the drawing scale on screen, 1 / S on paper), never rotated. `ElevDatumItem` keeps its
  `Level` (`_level`; a rename mutates it in place) and owns one `LevelDatumHead(OutlinedLabel)`
  (`head`, `child=True`) whose block origin sits on the line half a `BUBBLE_RADIUS_MM` left of the
  crop edge; the left grip and an interior move carry it (session-only, as the datum's
  extent). `gridline=None` (unit tests) = a detached item whose bubbles paint nothing.
- **Content.** Bubble: as 8b (`Mark`). Head: the `Level` category (`element-parameters.md`:
  `Level.Name` text as typed, `Level.Elevation` length formatted by the project ScaleManager;
  `category_of(ElevDatumItem) == "Level"`, getters read `_level`). A `SectionScene` has no
  `scale_manager` attribute, so the datum carries the model's live ScaleManager as
  `_scale_manager_ref` (the `format_utils.get_scale_manager` fallback). Seed bound fields:
  `LABEL_FIELD["Level"] = "Level.Name"`.
- **Visibility and duplicate flag.** The top bubble is visible iff `gl.bubble1.isVisibleTo(gl)`,
  the bottom iff `gl.bubble2.isVisibleTo(gl)`: the plan end's own toggle, independent of the plan
  item's display visibility (a plan-hidden gridline still shows here). Both are copied at build,
  with the duplicate flag; a plan edit rebuilds the section (Refresh below).
- **Outline and trim.** `OutlinedLabel` (section 2). `ElevGridlineItem.drawn_endpoints()` trims
  each visible end where the vertical leaves that bubble's outline; the ray from each bubble
  toward its line is derived from `p1 -> p2` (the top bubble's is (0, +1) in Qt y-down, the bottom's
  (0, -1)). `ElevDatumItem.line_start_h()` = where the ray from the head origin toward `_h_max`
  (+1, 0) leaves the head outline (0 trim when the head is hidden or draws nothing);
  `SectionScene.drawForeground` draws the datum line from it, so the line stays visible when the
  head scrolls off-screen. Screen and paper alike (on paper k is 1 / S, so the outline is the
  printed one). The elevation line geometry constants are `ELEV_GRIDLINE_END_PAD_MM` /
  `ELEV_GRIDLINE_PEN_W_MM` (`constants.py`).
- **Hit and HALO.** `ElevGridlineItem.shape()` = the stroked drawn line plus both visible bubble
  outlines; `halo_trace_path` = the trimmed line plus both outlines; `halo_area_path` = the
  outlines. `ElevDatumItem.shape()` = the head outline (a press on the head selects the datum; the
  line is scene foreground); `halo_trace_path` = the line from `line_start_h()` to `_h_max` plus
  the head outline, never the raw `line()` from `h_min` inside the head. Both items' `boundingRect`
  holds the heads. `SectionScene._halo_resolve` walks the **full parent chain** to the owning
  gridline / datum, and `_manip_exclude` (the `SelectionManipulator` exclude predicate) excludes
  any `BoundLabelItem`, so only the top-level gridline / datum is framed.
- **Overlays (screen only, never on paper).** The bubbles use `GridlineBubble.overlay_pens()`
  (selection ring, orange duplicate ring), reading the host item's overlay contract on
  `ElevGridlineItem`: `_paper_render`, `_grid_color`, `isSelected()`. `LevelDatumHead.overlay_pens()`
  = the selection ring only (the datum line colour `.lighter(150)`, cosmetic 2 px), never with the
  datum's `_paper_render` set.
- **Resolver forwarding.** `SectionScene.annotation_block(category, mapped=None)` forwards to
  `Model_Space.annotation_block` (section 3). A deleted plan gridline under an open section reads as
  a dead host (`host_values` -> `None`, section 2): static ops still draw with placeholder text, no
  orphan box, no raise.
- **Display Manager.** The Grid Line and Level Datum rows act on the **line only** here
  (`SectionScene._gridline_display_props` / `_datum_display_props` read colour, opacity and
  visibility; colour tints the line, visible / opacity act on the whole item). The Level Datum
  row has `fill: None`, `font: None` and is in `_NO_SCALE_CATEGORIES`; elevation no longer reads
  the Grid Line Fill / Scale. The row rule is homed in `grid-system.md` 10.1. The heads keep
  their authored colours.
- **Paper.** The paper walk's elevation branch (`paper_display`) calls the item's
  `enter_paper_pass` for the line (weight + paper-mm dash; `_paper_render` on; colour in B&W /
  Custom) and then `_apply_block` with opacity 1 on each visible head from `_elev_heads(item)`
  (`bubble1` / `bubble2` / `head`); `restore_model_display` replays each head's three paper hooks
  and refreshes it, then calls `exit_paper_pass`. Both items' paper hooks call
  `prepareGeometryChange()` because the trim and bounds move with the paper k. `_HAS_FILL` has no
  "Grid Line" / "Level Datum" ([`paper-space.md`](paper-space.md) 9.9.1).
- **Refresh.** `SectionScene.refresh_annotation_tags()` calls `refresh()` on each elevation
  gridline's bubbles and re-shapes the gridline, and `refresh_head()` on each datum (the head
  re-shapes, `prepareGeometryChange`, then the scene foreground updates because the datum lines
  start at the outline). `Model_Space.refresh_annotation_tags` also walks
  `self._section_manager.open_scenes` (when set), so a mapping, registry, units or drawing-scale
  change reaches every open section; `annotative.reprepare_annotative` goes through it. Every UI
  path that changes what a bubble shows (a Properties Mark / Bubble 1 / Bubble 2 commit, a Tag
  pick) already emits `sceneModified`, which reschedules the section rebuild
  (`SectionScene._schedule_rebuild`); nothing extra is wired, and Mark is pulled at paint.
- **Shipped seed** `firepro3d/system_blocks/Tags/LevelDatum.fpdb` (id `system-tags-leveldatum`;
  host category Level; Annotative; a user restyle at the SB4c smoke -- verify against the file
  before relying on numbers): a 3 mm-radius circle (6 mm across) with a horizontal and a vertical
  centre line and two filled quadrants, `@[Level.Name]` (Arial bold, 2.7 mm, left-aligned,
  Shrink on) above the datum line and `@[Level.Elevation]` (Arial, 2.4 mm) below it (today's
  layout), both starting 6.25 mm right of the origin; the outline (trim, ring, hit) is the circle -- text never moves it.
  Project default only: the Annotation pane's "Level tag" row, no per-level Tag row; the name is
  shown as typed.
- **Retired** (guard `tests/test_sb4c_retired_strings.py`): `_ElevBubble`, `_ElevLabel`,
  `bubble_paper_geometry`, `GRIDLINE_BUBBLE_PAPER_CAP_MM`, `GRIDLINE_BUBBLE_LABEL_EM_FRAC`,
  `_paper_bubble_r`, `_bubble_r`, the bespoke quadrant / font / upper-casing items, and the
  Display Manager fill / scale / font reads for both rows. `BUBBLE_RADIUS_MM` is **kept**
  (`section_marker` / `detail_view` proportion base, and the datum head's origin offset).

## 8d. View-marker heads (SB4d)

Three heads are System blocks: the cardinal **elevation** head, the head at each end of a placed
**section**, and the **detail** callout bubble. Marker geometry (crop box, cut line, depth, the
section/elevation instance) stays with [`section-view-subsystem.md`](section-view-subsystem.md)
s5 / s6; the detail marker with [`view-relationships.md`](view-relationships.md) 6; the Marks
rules with [`element-parameters.md`](element-parameters.md); the sheet rules with
[`paper-space.md`](paper-space.md); the Display Manager rows with [`grid-system.md`](grid-system.md)
10.1; the draw order (the annotation band's marker sub-band, the bounded section depth walk, snap)
with `view-relationships.md` 7.3 (Rule A: no z value is restated here). This section holds the
block-side contract. The decisions D1-D8, the acceptance criteria and the Phase 4 reconciliations
are in [`2026-11-03-sb4d-view-marker-heads-design.md`](../superpowers/specs/2026-11-03-sb4d-view-marker-heads-design.md)
(the ratified record; the contract now lives here).

- **Categories and seeds.** `ANNOTATION_CATEGORIES` gains **Elevation**, **Section**, **Detail**
  (one Annotation-pane row each; project default only -- no per-marker Tag row, follow-up filed).
  `LABEL_FIELD`: Elevation `Direction`, Section `Mark`, Detail `Mark`; `PAINT_WHEN_BLANK` lists
  Elevation (like Gridline, a blank letter keeps the circle) and, since SB4f, Section and Detail: an
  unplaced head binds only `Number` and `Sheet`, both blank, and must still draw (this reverses the SB4d
  wording that left them on the "paints nothing" rule). `SYSTEM_DEFAULTS`:
  `system-tags-elevationhead`, `system-tags-sectionhead`, `system-tags-detailcallout`, the
  shipped `firepro3d/system_blocks/Tags/ElevationHead.fpdb` / `SectionHead.fpdb` /
  `DetailCallout.fpdb` (all Annotative, host category as named). Seeds: Elevation = a circle with
  `@[Direction]`; Section and Detail = a circle split by a horizontal line, `@[Number]` above (SB4f; SB4d bound `@[Mark]` here) and
  `@[Sheet]` below. The sizes were restyled at the SB4d smoke (Section / Detail heads are 8 mm
  across) -- verify against the files before relying on numbers.
- **Ownership.** `ViewMarkerHead(OutlinedLabel)` (`view_marker_head.py`) is one class for all
  three; its category comes from the host through `element_params.category_of` (the
  `SectionMarker` splits on `cardinal`). `SectionMarker` owns `head` (cardinal, at
  `_cardinal_centre()`) **or** `head_a` / `head_b` (placed, origins on the cut endpoints `_a` /
  `_b`); `DetailMarker` owns `bubble` at its `_bubble_pos` (serialized, a grip drags it). Every
  head is a `child=True` label whose data host is its marker (the `GridlineBubble` pattern,
  section 2), non-selectable (the manipulator never wraps it). Hit / trim read the block outline
  (`outline_path()` / `trim_distance()`); the one overlay is the screen-only selection ring.
- **Sizing and orientation.** Annotative (section 1 / `2026-10-23-sb1c-annotative-sizing-design.md`):
  k = the drawing scale on screen, 1 / S on paper. The head is **never rotated** -- the placed
  section's label is upright (a breaking change: it used to turn along the cut).
- **Composite rule (concept Q9).** Only the head and its text come from the block. The cardinal
  wedge, the section triangle, the detail crop box and leader, and the section cut line stay
  bespoke in `section_marker.py` / `detail_view.py`, **sized from the head's outline at the
  current k**: `ViewMarkerHead.enclosing_radius()` (the smallest origin-centred circle holding the
  outline) gives `R_k`; the wedge is built tangent to it and the triangle's half-base and height
  derive from it (a circle head reproduces the old geometry; a rectangular head gets its
  circumcircle). With no resolved outline `R_k` falls back to the seed proportion
  (`_R_CARDINAL` / `_R_SECTION`, multiples of `BUBBLE_RADIUS_MM`, kept only for this).
- **Marks and the Sheet slot.** Section (placed only) and Detail are full Marks categories
  (pattern `{n}`; `element-parameters.md`): `Mark` is minted on create and stays the browser identity and a panel row (SB4f: it no longer shows on the head);
  the top slot binds `Number` (below), the bottom slot binds `Sheet`, the number of the sheet holding a viewport bound to the marker's
  view (`paper_space.sheets_holding`, also `SheetManager.sheets_holding`; blank when the view is
  unplaced; a legacy file with two placements cites the first sheet in sheet order). Elevation
  binds only `Direction`; a cardinal never mints a Mark and never plots. A marker has no paste
  site, so Marks mint at the two creation sites only. A load adopts the view-name token as the
  Mark once when a record has no `mark` key; a record that carries one (placed records always do)
  keeps it. The heads re-read on a Mark edit, a viewport placement or removal, a sheet
  create / delete / renumber, and a mapping / drawing-scale change (`refresh_view_marker_heads`,
  called from `refresh_annotation_tags`); the Sheet is pulled at paint. **The Number slot (SB4f)** is the
  `SheetViewData.view_number` of the viewport showing the view, on the first sheet holding it in sheet order
  (`element_params._view_number`, the `_view_sheet` rule; blank when the view is unplaced or the number is
  blank). A Number edit and its undo reach the heads through `PaperScene._resync_viewport` ->
  `_refresh_source_heads`. The number's own rules are `paper-space.md` 5.2; the key rows are
  `element-parameters.md`. The shipped `SectionHead.fpdb` / `DetailCallout.fpdb` went up a `version` and
  `base_version`; a project copy is brought up on load (section 8e, the head swap).
- **Detail tab.** In a detail's own tab the item paints nothing (like its marker); the tab's
  `Model_View.drawForeground` repaints the own detail's leader and head bright above the crop
  mask through `DetailMarker._paint_callout` (the head painted through its own `paint` under its
  scene transform). Other details' markers stay hidden in that tab, as before. The callout stays
  draggable.
- **Display Manager.** Three rows -- "Elevation Marker", "Section Marker", "Detail Marker" -- act
  on the **line only** (Colour tints the crop box / leader / cut line / arrow; `fill: None`,
  `font: None`, all three in `_NO_SCALE_CATEGORIES`); the heads keep their authored colours. The
  row rule is homed in `grid-system.md` 10.1.
- **Paper.** The paper walk calls `_apply_block` on each visible head from
  `paper_display._marker_heads(item)` (`head` / `head_a` / `head_b` / `bubble`), so a head prints
  at its authored mm (k = 1 / S) and the marker re-fits its arrow / leader to the paper k.
  `_HAS_FILL` lists no marker. A cardinal elevation never plots (`PAPER_EXCLUDED`);
  `paper-space.md` 9.9 owns the pass.
- **Retired** (guard `tests/test_sb4d_retired_strings.py`): the bespoke circle / text paint,
  `_display_font_size`, `_label_font`, `_label_angle`, `_head_polygon`, `_TAG_RADIUS`,
  `Z_DETAIL_MARKER`, `Z_LABEL_ABOVE_PIPE`, and the Display Manager Fill / Font / Scale reads for the
  marker rows.
- **Not built (filed):** the per-marker Tag row, a `{a}` letter token, a per-sheet pick if
  multi-placement returns, the node-badge block conversion (SB4e; the badge is only moved into the
  band here).

## 8e. The sheet viewport view title (SB4f)

The title under each sheet viewport is a System block: a number bubble, the title and the scale. The
viewport side (data, default spot, grip, panel rows, drop dialog, clamp, PDF) is
[`paper-space.md`](paper-space.md) 5.2 / 9.9 / 19.4 and the key rows are
[`element-parameters.md`](element-parameters.md) (Rule A: not restated here). This section holds the
block-side contract. The decisions G1-G12, D1-D6 and the acceptance criteria are in
[`2026-11-04-sb4f-view-title-design.md`](../superpowers/specs/2026-11-04-sb4f-view-title-design.md)
(the ratified record; the contract now lives here).

- **Category and seed.** `ANNOTATION_CATEGORIES` gains **View Title** (one Annotation-pane row; the
  project default only -- no per-viewport Tag row, a per-viewport block pick is not built).
  `SYSTEM_DEFAULTS["View Title"] = "system-tags-viewtitle"`; `LABEL_FIELD["View Title"] = "Scale"`, the one key
  that is never blank, so a missing block always draws the orphan box; the category is **not** in
  `PAINT_WHEN_BLANK`. The shipped `firepro3d/system_blocks/Tags/ViewTitle.fpdb` is Annotative with its origin
  at the bubble centre: a 3 mm radius circle with `@[Number]`, `@[Title]` above the line and `@[Scale]` below it
  (the sizes were set at the SB4f smoke -- verify against the file before relying on numbers). The title shows
  as typed, not upper-cased.
- **Ownership.** `ViewTitleLabel(OutlinedLabel)` (`view_title_label.py`) is a `child=True` label whose data
  host is its `SheetViewport` (`element_params.category_of` maps a `SheetViewport` to `View Title`). It is not
  a `BlockInstance` and never a block under `PaperScene` (containment C9; `schematics.md` D-S2). The block comes
  from `PaperScene.annotation_block` (section 3).
- **Sheet-native sizing.** `PaperScene` has no `scene_role`, so the annotative factor is k = 1 with no
  `_paper_scale`: the block prints at its authored paper mm, on screen and in the PDF. It paints as authored,
  independent of the viewport's B&W override. The orphan box is `placeholder_mm = VIEW_TITLE_PLACEHOLDER_MM`
  (8 mm, `constants.py`).
- **The line (D4).** The label, not the viewport, paints the composite line, so the viewport's hit area stays
  the box: black, `VIEW_TITLE_LINE_PEN_MM`, at the block origin's y, from the outline's right edge
  (`trim_distance(1, 0)`) to the box's right edge while the outline sits below the box and left of that edge,
  otherwise a fixed box width. Text ops do not count toward the outline, so on the seed the line leaves the
  bubble's edge. `_compute_rect` unions the line into the bounds.
- **Hit.** The label accepts the left and right buttons and forwards press, move, release, double-click and
  context-menu events to its viewport, so the title acts as the viewport body (select, native drag, navigate,
  menu). Which hooks the title grip registers on is `paper-space.md` 9.9.
- **Refresh.** `Model_Space.annotationLabelsChanged` -> `PaperScene.refresh_annotation_tags` (section 3) re-syncs
  every title on a registry, mapping, units or scale change; a transient export scene is built fresh and needs
  no wiring.
- **Head swap on load (D2).** `scene_io._refresh_view_head_copies` runs right after the block definitions are
  read, before items build, for the Section and Detail head ids only. A project copy is **untouched** when
  `base_version is None or version == base_version`; an untouched copy older than the library file is replaced by
  the library copy (its `base_version` set to its `version`), outside undo. An edited copy still bound to `Mark`
  is kept and counted: one status notice for the load. `source_status` is not used -- it reads an edited copy as
  `library` when the version numbers happen to match.
- **PDF.** The title plots as glyph paths, not a text layer (ruled accepted at the SB4f smoke; follow-up filed in
  `todo_open.md`). Owner: `paper-space.md` 7.3.
- **Retired** (guard `tests/test_sb4f_retired_strings.py`): `SheetViewport._VIEW_TITLE_H` and the hand-painted
  bubble, title and scale in `SheetViewport.paint`.
- **Not built (filed):** sheet furniture (north arrow, scale bar) as viewport-bound System blocks -- ruled to reuse
  this mechanism (a host-bound label on a paper item, never a paper `BlockInstance`); a per-viewport title block
  pick.

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
| SB4a pipe label: Ø / 3D Length / Flow / FrictionLoss content, same angle for left- and right-pointing pipes, above a node, vertical / Show Label off hidden, short pipes labelled, legacy `Label Size` loads clean, `tag_block` round-trips the codec + one-undo-step Tag row, paper mm at two scales, DM Pipe colour does not tint the label, split keeps the tag, z after the level pass, `reprepare_annotative` resizes pipe labels | `test_sb4a_pipe_label.py` |
| SB4a Hide when empty: `collapse_shifts`, drop + slot close in the drawn ops, zero flow collapses, explode parity (incl. flattened nested) | `test_sb4a_hide_empty.py` |
| SB4a retired pipe-label strings | `test_sb4a_retired_strings.py` |
| SB4a G8 perf bar (pipes; `-m perf`) | `test_sb4a_perf.py` |
| SB4b gridline bubble: category + default registered, blank Mark keeps the circle (a blank room name still paints nothing), seed eligibility + `@[Mark]` binding, annotative size at two drawing scales, upright on a 30 deg line, line trim for circle and rectangle blocks + orphan box, HALO trace, per-end visibility / grips / lock, paper mm at two scales + the duplicate ring never plots, DM Grid Line tints the line only, saved Fill / Scale ignored, Tag row below Bubble 2 Offset + one undo step + `tag_block` round-trip + offset / array copy + missing-id notice, bubble click / Ctrl+click through a shown view, bounds cover the hit area, rings render round the outline, legacy file loads, Properties row is Mark | `test_sb4b_gridline_bubble.py` |
| SB4b retired gridline-bubble strings | `test_sb4b_retired_strings.py` |
| SB4c elevation bubbles: `BoundLabelItem` `parent=` vs host, `OutlinedLabel` base without overlays, `SectionScene` resolver forwarding, a dead cross-scene host reads as dead, the plan gridline's `tag_block` / Mark drive the elevation bubble, per-end plan toggle hides the matching end in every section, line trim at a non-circular outline (screen and paper scale), bounds cover the hit area, the manipulator never wraps the bubbles, section and model refresh reach open sections, rings on screen and never on paper, a bubble click selects the gridline | `test_sb4c_elev_bubble.py` |
| SB4c level datum head: `Level` category + `category_of`, the shipped seed, one head per datum at the left end, Name / Elevation paint and a rename repaints, name as typed, line starts at the head outline (screen and paper), selection ring screen only, head scales with the drawing scale, press / HALO / grips / interior move, paper mm at two scales, DM Level Datum row line-only with stale values ignored, colour tints the line not the head, a noisy nested-quadrant outline still trims, HALO trace | `test_sb4c_level_datum.py` |
| SB4c retired elevation-bubble / datum-head strings, `BUBBLE_RADIUS_MM` kept | `test_sb4c_retired_strings.py` |
| SB4d view-marker heads: three categories + defaults + seeds registered, annotative size at two drawing scales, paper mm at two scales, cardinal never plots, upright text on a 30 deg cut, wedge / triangle tangent to a circle head and to a square head's circumcircle, the arrow follows k | `test_sb4d_categories.py`, `test_sb4d_heads.py`, `test_sb4d_paper_heads.py` |
| SB4d Marks (mint on create, pattern, duplicate flag, Renumber, load adopts the name token, blank refused), one-sheet rule + Sheet slot, mainwindow sheet refresh | `test_sb4d_marks.py`, `test_sb4d_one_sheet.py`, `test_sb4d_mainwindow_sheets.py` |
| SB4d detail tab callout above the mask, DM rows line-only (stale Fill / Font / Scale ignored), retired strings | `test_sb4d_detail_tab.py`, `test_sb4d_dm_rows.py`, `test_sb4d_retired_strings.py` |
| SB4d annotation band (z census, plan + section scenes, bounded depth walk, paper order, snap parity, top-level room tag / badge) -- the contract is `view-relationships.md` 7.3 | `test_sb4d_z_census.py`, `test_sb4d_band_plan.py`, `test_sb4d_band_section.py`, `test_sb4d_depth_walk.py`, `test_sb4d_paper_order.py`, `test_sb4d_snap_parity.py`, `test_sb4d_toplevel_labels.py` |
| SB4f view title: category / seed / registries, `PaperScene` forwarder, orphan box at 8 mm | `test_sb4f_category.py` |
| SB4f title item: block paints below the box, hide / placeholder paint nothing, line from outline to box edge or box width, resize / restyle / long title, no recursion without a closed outline, click / drag / double-click / right-click reach the viewport | `test_sb4f_title_item.py` |
| SB4f Section / Detail heads bind Number (first sheet in order, blank legacy, unplaced head still draws, edit + undo reach the head) | `test_sb4f_heads.py` |
| SB4f load: the D2 head swap, edited-copy notice, library without the seed, stable after save / load | `test_sb4f_load.py` |
| SB4f live refresh through `annotationLabelsChanged`; export paints / hides the title | `test_sb4f_refresh_export.py` |
| SB4f retired title strings | `test_sb4f_retired_strings.py` |
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
conversion, SB4a-e (SB4a, the pipe label, is built 2026-11-01; SB4b, the plan gridline bubble, 2026-11-03; SB4c, the elevation / section gridline bubbles + level datum head, 2026-11-03; todo lines; each user-designed and visually gated, G7). Phases 5-7
(uids and hosting, placed tags, sheet tags) are gated on phase 4 and described in the
concept.
