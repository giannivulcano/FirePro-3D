---
status: proposal
last-verified: 2026-09-29
verified-commit: c60baa2
applies-to:
  # Nothing is built yet. These are the modules the phased build will touch.
  - firepro3d/block_definition.py     # split static/bound compile, attribute schema, annotative scale_mode
  - firepro3d/block_instance.py       # per-instance bound-text cache, attribute overrides
  - firepro3d/block_library.py        # multi-root (System read-only + User)
  - firepro3d/blocks_browser.py       # System tier, lock, Duplicate-to-library
  - firepro3d/block_editor.py         # host category, field picker, instance attributes, sample preview
  - firepro3d/text_item.py            # @[key] fields in the text primitive, keep_upright
  - firepro3d/titleblock_template.py  # shared @[Key] substitution (reuse)
  - firepro3d/level_manager.py        # PlanView.scale
  - firepro3d/detail_view.py          # detail-view scale; callout bubble via BoundLabelItem
  - firepro3d/paper_display.py        # §9.9 per-category helpers become one annotative override
  - firepro3d/settings/panes.py       # Annotation defaults pane (category -> block)
  - firepro3d/settings/template.py    # annotation_defaults cloned from the template
  - firepro3d/pipe.py                 # pipe label -> BoundLabelItem
  - firepro3d/room.py                 # room tag -> BoundLabelItem; Room Tag becomes the Mark
  - firepro3d/gridline.py             # GridBubble -> BoundLabelItem (composite rule)
  - firepro3d/view_marker.py          # elevation-marker head -> BoundLabelItem
  - firepro3d/elevation_scene.py      # elevation bubble + datum head
  - firepro3d/hydraulic_node_badge.py # badge -> BoundLabelItem
  - firepro3d/paper_space.py          # viewport title; later, sheet-scoped tags
  - firepro3d/scene_io.py             # uid + attributes + annotation_defaults round-trip
  - firepro3d/model_space.py          # uid index, hosted-dependent cascade, Tag tool
  # new modules: element_params.py, bound_label.py, hosted_tag.py, firepro3d/system_blocks/
source-tasks:
  - "System Blocks — author the app's own 2D annotation graphics … (todo_open.md, [type:design], 2026-09-29)"
  - "Redefine reference/annotation graphics … as block-backed composites (folded in, superseded)"
  - "Block attributes — author text/numeric attributes … (absorbed as instance attributes)"
---

# System Blocks — Concept Design

> **Status: proposal (concept).** This document records a *design decision*, not
> current behaviour. Nothing here is built. The grill (Phase 2, Q1–Q16) settled
> **what** to build, and the brainstorm (Phase 3, F1–F8) settled **how**, at
> architecture level. Each build phase gets its own plan, and its own owning spec
> where F8 says so. Invariants owned elsewhere are linked, not restated (Rule A).
>
> **Ratification (P5):** Q1–Q16 were ratified in the 2026-09-29 grill, and F1–F5,
> F7 and F8 were approved by the user on 2026-09-29, so all of these are **locked**.
> **F6 is still a proposal, pending a human gate.** It depends on an unverified
> framework behaviour (per-view bounding and pick). That probe is the first step of
> the Phase 1 plan.

## Goal

The app's own 2D annotation graphics become **blocks** that ship in a read-only
**System library**. These are tags, labels, gridline and datum bubbles, elevation
and detail marker heads, and element symbols. The user can author them in the
Block Editor, and they read live data from the element they annotate:
`BLOCK(PipeLabel)` shows `Pipe.diameter`, and a `DoorTag` shows the door's Mark.
In Revit terms, tag families with labels bound to parameters.

## Motivation

All three payoffs weigh equally (Q1):

1. **New annotation types without code.** Wall, door and (later) valve tags,
   markers and symbols become data. None of these tags exist today.
2. **Office standards.** A firm restyles its labels and tags once. The restyled
   set travels in the project template.
3. **Consolidation.** Today there are 18 hand-rolled annotation painters, each
   re-implementing paint, shape, selection chrome, paper sizing and HALO trace.
   Twelve converge on one mechanism. This also dissolves the blocker in the folded
   task: gridlines are parametric and bubbles are screen-fixed, and the composite
   rule (Q9) and view-scale sizing (Q10/F6) together remove that blocker.

## Architecture & Constraints

### Two kinds of annotation, one graphic source (Q4)

| Kind | What it is | Examples | Needs stable ids? |
|---|---|---|---|
| **Intrinsic label** | Owned by its element, automatic, toggled per element or category. Drawn by a `BoundLabelItem` child of the host (F5). | pipe label, room tag, grid/elevation/datum bubble, hydraulic badge, viewport title, elevation and detail marker heads | **No.** The element owns it, so no reference is persisted. |
| **Placed tag** | A standalone hosted instance the user places (`HostedTagItem`, F7). | wall tag, door tag, (valve tag once a Valve element exists) | **Yes** (element `uid`). |

Both are drawn by System (or user-duplicated) blocks and authored in the one Block Editor.

### Where annotations live (Q2), a containment amendment

- **Model, level-scoped:** host-bound annotations live in Model Space on the host's
  level. They show in every plan, detail and paper viewport of that level, sized
  per view (F6). This **amends containment C9** by adding a third class,
  *host-bound annotation → model*. Free notes, keynotes, legends and north arrows
  stay on paper. C1/C9 are amended, not reversed.
- **Paper, sheet-scoped:** a sheet tag hosts **(viewport, element)**. If its
  viewport is deleted, the tag behaves as if its host were deleted. This depends
  on the P1 paper-space block placement task.
- **The upgrade path to view-scoped tags stays open.** Revit-style per-view tags
  would be a third view pattern (`view-relationships.md §5.3`). They are not in
  scope, and nothing here forecloses them.

### Host lifecycle (Q3), for placed tags

| Host event | Tag behaviour |
|---|---|
| moves or rotates | follows, keeping its offset in the host-anchor frame; `keep_upright` text flips so it stays readable |
| data changes | the text updates live (pull-on-paint, F7) |
| deleted | the tag is deleted in the same undo step |
| changes type or category | re-resolves to the new category's default block; if none exists, it shows a visible **"?"** placeholder and never vanishes |
| tag dragged | only the offset changes; the host is unchanged (re-hosting is an explicit command) |
| several tags per host | allowed |

### Block resolution (Q5)

- A block declares its **`host_category`**, which also scopes the fields it can bind.
- The project holds **`annotation_defaults: {category: block_id}`**, for both
  intrinsic labels and placed tags. It is edited in Project Settings and cloned
  from the template.
- The Tag tool is category-aware: hovering previews the host's default tag.
- Per instance, a tag can swap to any block with the same `host_category`.
- The key is the category, not the family. Per-family defaults are a possible
  later refinement.

### Bindable data (Q6)

| Tier | Content | In scope |
|---|---|---|
| T1 | stored properties (diameter, name, Mark, level) | ✅ |
| T2 | computed geometry (length, area, elevation) | ✅ |
| T3 | analysis results (flow, friction loss, pressure); `None` before a solve | ✅ |
| T4 | one hop to a related element (`Level.Name`, `Room.Name`, system name) | ✅ |
| T5 | aggregates, and any expression language | ❌ (the design-criteria table stays bespoke) |

By default, values render in the **project's display units** through the
`ScaleManager` formatters (`docs/specs/units-and-formatting.md`), so a unit
switch reflows every label. Each field can set a prefix, suffix, precision
override, and a placeholder for an empty or `None` value.

### Marks (Q7)

- Every taggable element gets an instance **`Mark`**. It is editable in the panel
  and saved on both the file path and the undo path.
- The Room's `Room Tag` becomes its Mark.
- Marks are auto-assigned per category from a pattern in Project Settings (e.g.
  `D{n}`). Copy and paste take the next number.
- Duplicates are **flagged, not blocked**, reusing the gridline duplicate-warning
  style.
- A **Renumber** command runs per category, optionally per level.
- **Type Mark** is deferred to the Feature parameter engine (`feature-system.md` F4).
- The **Valve** element is out of scope and filed separately.

### System library (Q8)

- The System library ships **read-only**. Its categories are Tags, Labels,
  Gridlines, Markers, Symbols, Icons and Reference.
- To customize a block, **Duplicate** it into a user or office library and point
  `annotation_defaults` at the copy.
- A project **embeds** every block it uses, and the embedded copy is authoritative
  (`block-system.md` decision 4), so a project renders identically after an app
  update.
- A newer shipped version surfaces only as the existing library-status marker,
  and **Reload is explicit**.
- The code-level **`SYSTEM_DEFAULTS`** table guarantees a fallback for every
  intrinsic-label category.

### Conversion scope and the composite rule (Q9)

**Composite rule:** a parametric item stays a bespoke item, and it takes its
*fixed* sub-graphics (bubble, head, symbol) from System blocks.

| Converted (12) | Kept bespoke |
|---|---|
| pipe label, room tag, hydraulic badge, viewport title | door/window swing: the Feature system build-out (its plan block per Type) |
| grid bubble (plan + elevation), datum bubble, elevation-marker head, detail-callout bubble: the head only, the line/leader/crop stays bespoke | fittings (12 topology-driven variants) |
| sprinkler symbols (3), water supply, riser symbol: *symbol* blocks, real size | design-criteria table (T5) |
| | title blocks: they already bind with `@[Key]`, so only the field language is reconciled (F8) |
| | constraint dimensions (authoring chrome) |

### Authoring (Q11), Block Editor

1. The author declares **annotation vs symbol** (F3: `scale_mode`) and, for an
   annotation, its **`host_category`**.
2. Text primitives take **`@[key]` fields** from a picker that lists the host
   category's T1–T4 parameters, mixed with static text (`Ø@[Diameter] – @[Length]`).
   This is the same syntax as title blocks.
3. **Instance attributes** have no host binding. They are text or number
   attributes with a default, typed per instance in the property panel, which
   absorbs the Block-attributes task. A host-bound field also accepts a
   per-instance override.
4. The editor previews **sample values**, with a toggle to show raw tokens.
5. A text primitive can be flagged **`keep_upright`**.
6. **The block origin is the anchor** that attaches the block to its host or leader.

### Leaders (Q12)

- Leaders are optional on **placed tags** and off by default.
- A leader is straight or has one elbow, with an elbow grip.
- The host end auto-attaches to the host's anchor and follows it. The tag end
  attaches to the block origin.
- The end style (arrow or dot) and the line weight come from the tag's Display
  Manager category.
- Intrinsic labels have no leader in v1.
- A leader belongs to the tag item, not to the block (composite rule).

## Design Decisions

| # | Fork | Chosen | Rejected | Why |
|---|---|---|---|---|
| F1 | Bound text vs the flyweight | **Split cache.** The definition compiles static ops once and shares them (unchanged perf gate). Text primitives that contain fields are excluded. Each instance caches the glyph outlines of its bound text, keyed by `(definition version, resolved strings)`. The view scale is a paint transform, not a key. | (b) live `drawText` each paint; (c) per-instance full recompile | (b) breaks glyph-outline plot fidelity (`paper-space.md §9.4`) and text snap points; (c) fails the flyweight perf gate. The split keeps shared geometry shared and rebuilds outlines only when a value changes. |
| F2 | Reading host data | **`element_params` registry:** category → `{key: ParamSpec(key, label, kind, tier, getter)}`, where the getter returns a raw typed value (mm, mm², gpm, psi) or `None`. Formatting goes by `kind` through `ScaleManager`. A single `category_of(item)` does the dispatch, subclass before base. T4 keys are namespaced (`Level.Name`) through relation getters. `get_properties()` stays as the panel's concern. | Parsing `get_properties()` | Its keys are display labels and its values are pre-formatted strings (`1"Ø`), unstable and unit-baked. |
| F3 | Block schema | **No new "kind" field.** Annotation = `scale_mode: "annotative"` (already reserved) + `host_category`; symbol = `real_size`. `attributes` (the reserved list) holds attribute definitions `{key, label, type, source: host\|instance, host_key, default, prefix, suffix, precision, placeholder}`. Text references **attribute keys** through `@[key]`. The instance's `attributes` dict holds overrides and typed values. Substitution reuses `titleblock_template.substitute`. `keep_upright` is a text-primitive flag. | Text referencing host keys directly; a separate kind enum | The indirection routes bound, overridden and instance-typed values through one resolver. Reusing the reserved slots means no schema fork. |
| F4 | System tier | **Multi-root `block_library`:** `[System (read-only, shipped at firepro3d/system_blocks/ via asset_path()), User]`. The library name "System" is reserved. System block ids are **frozen uuids** (the Feature frozen-id precedent). The browser shows System first, with a lock, and has *Duplicate to library…*. `SYSTEM_DEFAULTS` maps category → System id. | Seeding an editable copy into user data | An in-place-editable System copy gets clobbered or forks on app update. Read-only plus Duplicate keeps shipped content and customized content cleanly apart. |
| F5 | Intrinsic-label seam | **One reusable `BoundLabelItem`,** a lightweight child item of the host that draws a block with the host as its data source. It replaces the pipe label text item, the room label child, `GridBubble`, `HydraulicNodeBadge`, `_ElevBubble` and the other heads. Composite items position their own `BoundLabelItem`s. The project settings gain `annotation_defaults`, with a Project Settings pane, cloned from the template. | Painting the label inside the host's `paint()` | That inflates the host's bounds and shape and breaks hit-testing. Every converted site is already an item, so the scene-object count is unchanged. |
| F6 *(pending a gate)* | Annotative sizing | `PlanView.scale` (the denominator, default 100) plus a detail-view scale. An annotative block paints scaled by the denominator of the **view currently painting** (`paint(widget)` → `Model_View` → its view). The paper pass sets **one** scene-scoped override (`1/S`) during a viewport render, replacing the per-category `§9.9` helpers. `boundingRect()` = the largest scale among live views, with a geometry change announced whenever any view's scale changes. | Screen-fixed in model; model-sized everywhere (Q10) | This is the only option where the authored printed size holds in both model and paper (WYSIWYG, Revit-like). **Probe first:** view resolution from `widget`, conservative bounds against HALO pick and viewport clip. |
| F7 | Ids + hosting (build phase 5) | Every model element gets a **`uid`** (uuid4 hex), minted on create and written by `to_dict` on **both** serialization paths. Undo restore re-applies the saved uid. Copy and paste mint new uids. A scene `uid → element` index is kept at the add/remove choke points. A `HostedTagItem` holds `host_uid`, an anchor-frame offset and leader data. **Text is pulled** at paint (F1's key limits rebuilds to real changes, so no per-element signals are needed). **Position is pushed** through one generalized `HostedDependents` host-geometry hook, modelled on the wall → opening `_reposition`. Delete cascades through the uid index. | A full per-element change-signal system | Elements are `QGraphicsItem`s, not QObjects, and have no signals. Pull-for-text avoids building one. Pushing only geometry mirrors the one hosting relationship that already works. |
| F8 | Spec amendments | See the list below. | — | Rule A: each fact goes to its owning spec. |

### F8: spec amendments (filed as follow-ups; this doc links, it does not own)

- `model-space-containment-contract.md` **C9**: the *host-bound annotation → model*
  class (Q2).
- `view-relationships.md`: `PlanView.scale` + detail-view scale. Record that this
  is per-paint scaling on the one shared scene, **not** a third view pattern (§5.3).
- `block-system.md`: decision 6 (text + fields in blocks), decision 9
  (`annotative` activated, attributes schema), the System tier and multi-root
  library.
- `paper-space.md §9.9`: the per-category label-height helpers are replaced by the
  single annotative override; the per-pipe Label Size and the Display Manager label
  heights retire (Q13).
- `feature-system.md`: a pointer to Mark and Type Mark ownership.
- `titleblock-template-system.md`: `@[Key]` is the app-wide field language.
- **New owning specs:** `system-blocks.md` (this subsystem, promoted from this
  concept when Phase 1 lands) and `element-parameters.md` (the registry, Marks,
  uids and hosting).

## Build Order (Q14)

| Phase | Delivers | Depends on |
|---|---|---|
| 0 | merge `feat/nested-blocks` (the `BlockRegistry` invalidation hook) | — |
| 1 | block-side core: F1 split cache, F3 schema + `@[key]` + instance attributes + `keep_upright`, F4 System tier, F6 probe → `PlanView.scale` + annotative paint + paper override, Block Editor authoring (Q11) | 0 |
| 2 | typed parameters: F2 registry for the categories being labelled, `category_of`, Mark + patterns + Renumber (Q7) | — (runs in parallel with 1) |
| 3 | **first vertical slice: room tag** end to end. The user designs it, it passes the visual gate, and the `annotation_defaults` pane lands. **Reassessment checkpoint (Q16).** | 1, 2 |
| 4 | the remaining intrinsic conversions, **one follow-up each**, each user-designed and visually gated (Q13): pipe label, grid bubble, elevation bubble + datum, elevation-marker head, detail-callout bubble, hydraulic badge, viewport title, sprinkler/water-supply/riser symbols | 3 (+ passing the checkpoint) |
| 5 | hosting foundation: F7 uids + index + `HostedDependents` | 2 |
| 6 | placed tags: the Tag tool, the Q3 lifecycle, Q12 leaders; wall and door tags | 4, 5 |
| 7 | paper, sheet-scoped tags (host = viewport + element) | 6 + the P1 paper-space block placement task |

**Reassessment checkpoint (after phase 3).** Stop or redesign before phase 4 if
any of these happen:

- the G6 performance guard fails at realistic scale;
- bound text cannot reuse the shared static geometry (F1);
- the room-tag slice needed more than a small set of spec amendments.

Phases 5–7 are gated separately on phase 4's outcome.

## Migration (Q13)

- Conversion is **per label**:
  1. The user designs the System block in the Block Editor and saves it.
  2. The code switches that label to it.
  3. A **visual gate**: side-by-side in the running app, and the user approves.

  The gate is the user's approval, not pixel parity with the old painter.
- Saved per-element behaviour **carries over**: Show Label, label offsets, bubble
  visibility, badge position.
- The Room's `Room Tag` becomes its Mark.
- The per-pipe **Label Size** and the Display Manager label heights **retire**, in
  favour of the block's authored printed size.
- Grid bubbles stop being screen-fixed (F6).
- The format bump is **one-way**: new files don't open in older builds.

## Acceptance Criteria (concept deliverable, design-only)

- [x] The Q1–Q16 problem definition is ratified in the grill (2026-09-29).
- [x] The F1–F8 architecture is approved (F6 pending a gate on its probe).
- [ ] Follow-up tasks are filed in `todo_open.md` for phases 0–7, the F8
      amendments, the Valve element, and the supersession of the folded
      reference-graphics task.

### Build-phase acceptance: guard tests (Q15, VC3)

Every build phase must meet the guards that apply to it:

| # | Guard | Scenario → observable truth |
|---|---|---|
| G1 | live binding | edit a room's name through the property panel → the rendered tag text changes; switch project units → a bound length re-formats |
| G2 | round-trip | attribute definitions, instance overrides and values, Marks, `annotation_defaults` (and later `uid` / `host_uid`) survive `.fpd` save/load **and** undo/redo |
| G3 | printed size | export a PDF with the tag in viewports at two scales → the measured cap height equals the authored mm in both; the model view at `PlanView.scale` is checked too |
| G4 | host lifecycle (phase 6) | move, rotate, delete, change type, and undo the host through the real tools → the Q3 table holds |
| G5 | System library | shipped blocks can't be written; Duplicate gives an editable copy; a missing mapped block falls back to `SYSTEM_DEFAULTS`, never vanishes |
| G6 | performance | a labelled network at realistic scale stays responsive; the static ops stay shared (the metric and threshold get confirmed with the user before phase 3) |
| G7 | visual gate | per conversion: the user approves in the running app, then a pixel-sampled lock test of the approved design |

## Verification Checklist

- [x] `status: proposal`. Reads as design, not current behaviour.
- [x] Rule A: containment, Z-order, units, paper `§9.9` and the Feature naming
      contract are linked, not restated.
- [x] P5: only human-gated decisions are marked locked; F6 is marked pending.
- [ ] The F8 amendments land in their owning specs when their build phases run.

## Existing Code Context (1b reuse sweep, 2026-09-29, verified at `c60baa2`)

- **Reuse as-is:**
  - `BlockDefinition` + the primitive-dict schema + the Library/Series folders
  - the Block Editor, which authors all 9 primitives including text
  - instance level scope, selection and snaps
  - `titleblock_template.substitute` (`@[Key]`)
  - the `ScaleManager` formatters
  - `BlockRegistry.invalidate` / `users_of` (in flight on `feat/nested-blocks`)
- **Generalize:**
  - text is baked to shared glyph outlines in `_compile` → F1
  - the reserved `attributes` slots are saved and loaded but unread → F3
  - pose has no scale → F6
  - `get_properties()` uses display-label keys and formatted-string values → F2
  - the wall → opening `_reposition` + delete cascade → `HostedDependents` (F7)
  - the paper `§9.9` per-category helpers → F6
- **Gaps:**
  - stable element ids (only `BlockDefinition.id` is a uuid in the model, and
    undo rebuilds every item)
  - an element-type registry
  - Marks: only Room Tag and the gridline label exist; there is no Valve element
  - tag → host references
  - dependent notification
  - a shipped System tier (today there is a single user root)
  - attribute authoring UI
- **Converted-site inventory:** 18 persistent hand-rolled sites, of which 12 are
  converted under Q9.

## Edge Cases & Error Handling

- A bound value is `None` (no hydraulic solve yet, no related element) → the
  field's placeholder shows, or blank.
- A field key is unknown to the host category (block authored against a newer
  registry) → the placeholder shows, plus a Block Manager warning; the tag is
  never dropped.
- The mapped block is missing from the project and the library → the
  `SYSTEM_DEFAULTS` block is used.
- A placed tag's host is missing on load (dangling `host_uid`) → a "?"
  placeholder tag plus a load warning, mirroring the nested-blocks
  missing-definition red placeholder.
- The same level is shown in two live views at different scales → one item,
  painted per view; conservative bounds (F6).
- A converted label is inside a nested block → not applicable: intrinsic labels
  belong to elements, not blocks.

## Performance

The flyweight perf gate (`block-system.md` "The flyweight core") holds for static
ops. The per-instance cost is one glyph-outline build per **change in a resolved
string**, not per paint. Pull-on-paint re-resolves values on every paint, so each
getter must be O(1) (attribute read or cached computation). T3 reads the
already-computed `hydraulic_result`. G6 sets the bar before phase 3.
