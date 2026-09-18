---
status: proposal
last-verified: 2026-09-17
verified-commit: ac74e67
applies-to:
  # Implementation design for the containment-contract code migration (C5, C1/C8, C7).
  # Invariants are owned by model-space-containment-contract.md (Rule A — linked, not restated).
  - firepro3d/model_space.py
  - firepro3d/geometry_2d.py
  - firepro3d/annotations.py
  - firepro3d/paper_space.py
  - firepro3d/block_definition.py
  - firepro3d/block_instance.py
  - firepro3d/scene_io.py
  - firepro3d/main.py
  - firepro3d/ribbon_bar.py
related-contract: model-space-containment-contract.md
source-tasks:
  - "todo_open.md → [feature] Implement the containment contract — model placement-only + Text primitive + ribbon rework + clean-drop load [P1]"
---

# Containment Contract — Implementation Design (C5 · C1/C8 · C7)

> **Status: proposal (unbuilt).** This is the *how* for the code migration that
> closes item 4 of the containment contract's Deferred-work list. The *what* —
> the nine containment invariants — is owned by
> [`model-space-containment-contract.md`](model-space-containment-contract.md);
> this doc does not restate them (Rule A), it links to the C-numbers.
>
> **This session's scope:** C5, C1/C8, C7. **Deferred (filed follow-ups):** C3
> (level-on-instance), C2/C6 (Feature composition), Block-Editor constraints,
> Paper-space dimension annotations.

## Goal

Migrate the code so Model Space is **placement-only** in behaviour: unify the two
text systems into a single Text primitive that works as block content *and*
paper annotation (C5), gate loose-geometry/text/dimension authoring out of the
plan scene and silently drop legacy loose content on load (C1/C8), and rework the
ribbon to match the surface topology (C7). Built as one feature branch, three
ordered slices.

## Motivation

See the contract's Motivation. The concrete driver here: the *how* was ambiguous
on three load-bearing points — how a scene knows its authoring/rendering role,
how block-content text renders at scene scale through the flyweight, and how the
clean drop coordinates across the two independent serialization paths. This doc
pins those before planning.

## Architecture & Constraints

### A1 — Scene role (foundational; both C1 and C5 consume it)

The plan scene and the Block-Editor scratchpad are the **same `Model_Space`
class** (`block_editor.py` hosts an isolated `Model_Space` + `Model_View`), so
`isinstance` cannot distinguish them; `PaperScene` is a separate class. Introduce
a `scene_role` on `Model_Space` (`"plan"` | `"block_editor"`) and a minimal scene
protocol both consumers query without knowing scene internals:

- `authoring_allowed(mode) -> bool` — backed by a per-role allowed-modes set. The
  **plan** role forbids the 8 loose primitives + `text` + `dimension`; the
  **block_editor** role permits them. `set_mode` consults this — one gate, not
  scattered guards.
- `device_independent_text() -> bool` — `PaperScene` → `True`; `Model_Space`
  (either role) → `False`. Drives C5 Text sizing.

This is the single structured concept the migration adds; it leaves a clean
extension point for elevation/3D scenes later.

### A2 — C5: the unified Text primitive

One class — `TextItem(Geometry2DMixin, DisplayableItemMixin, QGraphicsTextItem)`
— backed by `TextAnnotationData` (paper's superset + `angle`/`pivot`). It
replaces **both** `NoteAnnotation` (model) and `TextAnnotationItem` (paper).

- **Unified data model:** hex color, `height_mm` (cap height), font
  family/bold/italic/underline, `opaque_bg`, alignment, `wrap_width_mm`,
  `box_height_mm`, `angle`/`pivot`. **No `level`** (primitives are
  definition-local per C3 direction; standalone model text is retired anyway).
  Model `NoteAnnotation`'s poorer subset (4-color enum, point-size font) is
  discarded — a breaking change, acceptable under C8 clean drop.
- **Sizing mode follows the scene** (A1): `device_independent_text()==True`
  (paper) uses the existing `TEXT_METRIC_REF_PX` + geometric-scale path
  (zoom-invariant); `False` (model/Block-Editor) renders at scene-mm and scales
  with zoom. Same data, mode chosen from the scene it is added to. `height_mm` is
  always "physical cap height in that surface's own mm."
- **Primitive-family membership:** implements `get_properties`/`set_property`
  (+ `_geom2d_*` hooks), `to_dict`/`from_dict`, the 9-box `grip_points`/
  `apply_grip` protocol (both text items already share it), `manip_*`
  (translate/scale/**rotate** — the paper rotate handle is enabled this session),
  `paint`/`shape`/`contains` (carry over paper's `contains()` override —
  the "QGraphicsTextItem contains()+shape() together" gotcha). `get_closed_path()
  → None` (Text is not fillable; its box fill is `opaque_bg`, a distinct mechanism
  from `fill_type`). Registered in the `scene_io` from_dict dispatch and the
  parallel-list collectors.
- **Compile to outlined glyphs (block content):** Text exposes a **local-coord
  glyph-outline `QPainterPath`** that `BlockDefinition._compile` picks up through
  its existing `_local_path(item)` step, so Text flows into the shared
  `render_ops = list[(QPen, QPainterPath)]` like any primitive. Placed
  `BlockInstance`s (a flyweight: translate+rotate pose, **no scale**, no child
  items) paint the outline, which scales with the block and zooms with the view.
  **Instance text is not individually editable in Model Space** — you edit the
  block definition; font resolves at compile.
  - **Fidelity: document-faithful.** The baked outline mirrors the live
    `QTextDocument` layout (wrap width, alignment, box height, line breaks),
    outlining each positioned glyph-run — so a placed block matches the authored
    text. (Rejected: a single `QPainterPath.addText` of the raw string, which
    bakes wrapped/aligned multi-line text wrong.)

### A3 — C1/C8: authoring gate + silent clean drop

- **Authoring gate (C1):** nothing is deleted from the primitive/text classes
  (they survive for the Block-Editor + Paper contexts). The plan `Model_Space`'s
  `set_mode` refuses the forbidden modes via `authoring_allowed()` (A1). The
  Create-tab tools that trigger those modes are removed in the **C7** slice, so
  between C1 and C7 the gate is the backstop (a forbidden mode is a no-op).
- **Silent clean drop (C8):** two independent paths, both drop-and-do-not-reintroduce:
  - **`scene_io.load_from_file`:** remove the deserialize loops for the removed
    payload keys (`draw_lines`, `polylines`, `reference_lines`,
    `draw_rectangles`, `draw_circles`, `draw_arcs`, `draw_ellipses`,
    `draw_splines`, `polygons`, the `note`/`dimension` entries in `annotations`,
    the constraints block). Keys present in a legacy file are **read-but-discarded**;
    a single `logging` line records counts (no UI). The **legacy-hatch migration**
    block (which today re-creates `PolylineItem`s) is deleted — legacy hatch is
    dropped.
  - **`_capture_network`/`_restore_network`:** remove the geometry + note/dimension
    capture/restore blocks so no in-session undo round-trips forbidden content.
  - **`save_to_file`** stops writing the removed keys, so a load→save of a legacy
    file cleanly sheds them.
- **Entanglements:** model-scene **constraints** (capture/restore +
  `_all_geometry_items`-indexed save/load) are removed — constraints only ever
  referenced loose geometry; discarded on load, not dangled. **Clipboard**
  loose-geometry paste branches + the copy `to_dict` capture for these types are
  removed (block instances still copy/paste).
- **Orphan-gate deliverable:** `scene-io.md` is forged **before** this slice's
  code (see [`scene-io.md`](scene-io.md)).

### A4 — C7: ribbon rework

Mechanical, gated on the existing mockup
(`docs/mockups/ribbon-containment-contract.html`) at the start of the slice.
Dissolve the Create tab; add a "Block" group + relocate the Underlay group to
Architecture; retire the Quick-Block and Text-Block buttons; add the Text tool to
the Block-Editor "2D Geometry" group (`_block_mode_buttons`) and the Paper
context. `_contextual_index` auto-derives from tab count. Governed by
`ribbon-bar.md` (close D10).

## Design Decisions

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Scene role | `scene_role` + scene protocol (A1) | Per-scene capability object; ad-hoc booleans | Minimal shared concept both slices need; keeps Text scene-agnostic; single testable gate |
| Text class | One `TextItem` on `TextAnnotationData` | Keep two subclasses; keep paper sheet-text separate | C5 "one item, one renderer"; paper model is the superset |
| Text sizing | Mode from `device_independent_text()` | Two subclasses per surface | Same data means the right physical mm in both surfaces |
| Block-content text | Outlined glyphs in `render_ops`, doc-faithful | Live child text item; single-run `addText` | Preserves the flyweight; correct scaling; matches authored layout |
| C1 removal | Gate authoring by scene role | Delete draw modes from `Model_Space` | Block Editor reuses the same class — deletion would break it |
| Clean drop | Silent, read-but-discard, log line | Modal / toast; skip keys entirely | User call (Q6); counts logged for diagnostics |

## Acceptance Criteria

**Slice C5**
- [ ] One `TextItem` replaces `NoteAnnotation` + `TextAnnotationItem`; the two old classes are gone.
- [ ] Text round-trips through **both** serialization paths (file + `_capture_network` undo).
- [ ] Text is registered as the 9th primitive (from_dict dispatch + parallel-list collectors + Block-Editor palette membership).
- [ ] Paper Text rotates (rotate handle enabled); rotation bakes into the data + serializes.
- [ ] Sizing behaviour asserted via `boundingRect`: block-content/model Text bounds scale with the model scene; paper Text bounds are device-independent across zoom.
- [ ] A block containing Text compiles to outlined glyphs; a placed instance renders them (live-smoke gate for glyph pixels — headless is tofu).
- [ ] Block-Editor live text-edit path smoke-tested for the `QPainter engine==0` risk.

**Slice C1/C8**
- [ ] `scene-io.md` forged, in `SPEC-INDEX.md`, stamped.
- [ ] Plan `Model_Space` refuses the 8 primitives + `text` + `dimension` (drive `set_mode`; assert no item created on click).
- [ ] Loading a synthetic legacy `.fpd` with loose geometry + notes + dimensions + constraints + hatch → scene lists empty, no exceptions; a re-save omits them; `_restore_network` does not reintroduce them.
- [ ] Block instances + library definitions load/render unaffected.
- [ ] Clean drop logs counts (no UI).

**Slice C7**
- [ ] Ribbon matches the signed-off mockup: Create tab absent; Architecture has Block + Underlay groups; Quick/Text-Block buttons gone; Text tool present in Block-Editor + Paper contexts (assert widget structure, not source text).
- [ ] House-style smoke passed.

**Cross-cutting**
- [ ] Each slice leaves the app launchable and the suite green; colliding stale tests updated within the causing slice, pre-existing-vs-regression proven.
- [ ] Six contract-affected specs + `scene-io.md` re-audited/stamped in Phase 6; contract's per-spec-body-rewrites box closed for delivered invariants.

## Verification Checklist
- [ ] All acceptance criteria met.
- [ ] Tests pass at the specified level (headless guards + named live-smokes).
- [ ] No regressions in block instances, paper text, or project load of a contract-era `.fpd`.
- [ ] Rule A honoured — this doc links to the contract's C-numbers, does not restate them.

## Existing Code Context
- Scene role / authoring: `model_space.py` (`set_mode`, `_geom_ctl` = `GeometryDrawingController`), `block_editor.py` (isolated `Model_Space`).
- Text today: `annotations.py` (`NoteAnnotation`), `paper_space.py` (`TextAnnotationData` / `TextAnnotationItem`), `font_group.py`, `property_manager.py`.
- Primitive family: `geometry_2d.py` (`Geometry2DMixin`).
- Blocks: `block_definition.py` (`_compile`, `render_ops`), `block_instance.py` (flyweight).
- Serialization: `scene_io.py` (file), `model_space.py` (`_capture_network`/`_restore_network`), `network_codec.py` (`serialize_note`).
- Ribbon: `main.py` (`init_ribbon`, `_init_create_tab`, `_init_architecture_tab`, `_build_block_editor_context`), `ribbon_bar.py`.

## Code Style & Testing
Per CLAUDE.md: PyQt6, mm-internal geometry, relative imports within `firepro3d/`,
Google docstrings. Tests: `venv/Scripts/python.exe -m pytest`; no pytest-qt (use
the `qapp` fixture); guards assert observable ground truth with real domain
objects and are demonstrated RED with the fix reverted.
