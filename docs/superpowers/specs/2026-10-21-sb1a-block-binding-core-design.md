---
status: proposal
last-verified: 2026-10-21
verified-commit: 33afbc32   # branch base (main) at design time
applies-to:
  - firepro3d/block_attributes.py          # new: attribute schema, formatting, resolver (pure)
  - firepro3d/block_attributes_dialog.py   # new: Edit Attributes dialog (placed instance)
  - firepro3d/block_attributes_editor.py   # new: Attributes editor dialog (Block Editor)
  - firepro3d/block_definition.py          # bound_prims split out of _compile; host_category / scale_mode authored
  - firepro3d/block_instance.py            # _bound_ops derived list; host_values() seam; set_attributes
  - firepro3d/block_explode.py             # bake resolved bound text
  - firepro3d/block_properties_info.py     # Block view: Attributes section, Host category, Scale mode
  - firepro3d/text_item.py                 # keep_upright flag; Insert field row (Block Editor surface)
  - firepro3d/block_editor.py              # sample-value preview + raw-token toggle
  - firepro3d/model_space.py               # can_edit_attributes / open_edit_attributes; entity-menu Edit Attributes item; editor block_meta + sample preview
  - firepro3d/model_view.py                # plan selection menu: Edit Attributes item
  - firepro3d/entity_context_menu.py       # on_edit_attributes action
  - main.py                                # ribbon Definition-group Edit Attributes (wired at smoke)
  - firepro3d/titleblock_template.py       # resolve_text / TOKEN_RE reused (no change)
source-tasks:
  - "SB1a -- Block-side binding core (todo_open.md, [type:feature], System Blocks build)"
parent-concept: docs/superpowers/specs/2026-09-29-system-blocks-concept-design.md
---

# SB1a -- Block-Side Binding Core -- Design Spec

> **Status: proposal.** Phase 1 of the System Blocks build (concept F1, F3, Q11;
> the concept's F4 System tier is SB1b and F6 annotative sizing is SB1c).
> Everything the concept ratified is linked, not restated (Rule A). This doc owns
> the SB1a rulings A1-A9 (Phase 2 grill, 2026-10-21) and the design sections
> S1-S4 approved on 2026-10-21. Promotion target: `docs/specs/system-blocks.md`
> at the SB3 checkpoint; until then `block-system.md` decisions 6 and 9 are
> amended in place at Account (concept F8).

## Goal

A block definition declares **attributes**; its text primitives reference them
with `@[key]` fields; a placed instance resolves those fields from its own typed
values, a per-instance override, or a host-value provider; the resolved text is
rendered through a per-instance bound layer that leaves the shared static ops
untouched (F1). Text primitives can be flagged `keep_upright`. The Block Editor
authors all of it and previews sample values.

## Motivation

Concept Q1 (the three payoffs). SB1a is the block-side half of the room-tag
vertical slice (SB3); SB2 supplies the host side (the `element_params`
registry). Nothing user-visible changes for blocks without attributes.

## Architecture & Constraints

### Phase 2 rulings (locked 2026-10-21, AskUserQuestion gates)

| # | Ruling |
|---|---|
| A1 | Nested bound text resolves against the **outermost placed instance's** values (one key namespace; outermost wins -- the WM2 override composition shape). Nested records carry no attributes dict. |
| A2 | Host values come through **one provider seam**, `BlockInstance.host_values() -> dict | None` (default `None` -> placeholder). Editor: `host_category` free combo, `host_key` free text, field picker lists the block's own keys. G1 runs with a stub provider; SB2 swaps in the registry and populates the pickers. |
| A3 | Instance values/overrides are edited in an **Edit Attributes dialog**, opened from the right-click menu ("Edit Attributes..." under "Edit Block", on both the entity menu and the plan-view selection menu) and by an "Edit attributes..." property-panel button; no attributes -> no menu item, button disabled. *Re-ruled at smoke 2026-10-21:* double-click on a placed instance keeps its pre-SB1a behaviour (no block action; the Block Editor's nested double-click, D10, unchanged) -- the original ruling opened the dialog on double-click. The Block Editor's Attributes editor is also reachable from the ribbon's Definition group **Edit Attributes** button (the pre-SB1a placeholder, wired at smoke; disabled on a schematic). |
| A4 | Dialog rows: label / source / value. Host rows show the resolved value read-only with an **Override** checkbox enabling an editor (uncheck = binding restored). OK = one undo step; Cancel discards. |
| A5 | `keep_upright`: net text angle in (90, 270] degrees -> 180-degree flip about the text's own box centre; a mirrored instance also un-mirrors the glyphs. Pose-only (view-independent), so model and paper agree. |
| A6 | `default` doubles as the preview sample (host attrs: sample only). Empty -> placeholder. A "show raw tokens" toggle. |
| A7 | Renaming a key rewrites every `@[old]` in the definition's text (one undo step); deleting a referenced key is refused ("used by N text fields"); unknown tokens render literally plus a Block Manager warning. |
| A8 | `type: number` renders as a plain decimal with `precision`, wrapped by prefix/suffix. Unit-aware (kind) formatting arrives with SB2 host values. |
| A9 | Explode bakes the resolved string and the keep_upright pose into a plain text primitive. |
| Assumed | `scale_mode: "annotative"` is authored and stored in SB1a but paints as real size until SB1c. |

### S1 -- Data model & schema (additive; no `schema` bump, absent => empty, CS1 precedent)

- **Definition `attributes`** (the reserved list, now read): records
  `{key, label, type: "text"|"number", source: "instance"|"host", host_key, default,
  prefix, suffix, precision, placeholder}`. `key` is the token name, unique per
  definition, case-sensitive. `host_category: str` ("" = none) and `scale_mode`
  ("real_size" | "annotative") become authored definition fields. `attributes` is
  still carried by clone (Manager "Create new based off").
- **Text primitive**: `keep_upright: true`, written only when true (the `mirrored`
  convention). Field text is the plain `text` string holding `@[key]` tokens.
- **Instance `attributes`** (`BlockInstance.attributes`): `{key: value}`. For
  `source: instance` the typed value (absent => `default`); for `source: host`
  **presence is the override** (A4). Nested records stop writing `attributes`; a
  legacy nested key is ignored on load (A1).
- **New pure module `firepro3d/block_attributes.py`** (no Qt): `normalise_attr`,
  `format_value(record, raw) -> str` (A8), `resolve_values(definition,
  instance_values, host_values) -> dict[str, str]`, `resolve_fields(text, values)`
  wrapping `titleblock_template.resolve_text`, `has_fields(text)` via `TOKEN_RE`,
  `rename_key_in_texts(prims, old, new)`, `references_of(prims, key)`.
- **Provider seam** (A2): `BlockInstance.host_values()`; a test stub subclass
  returns a dict. SB2/SB3 override it on host-aware subclasses.

### S2 -- Compile / render split, nested inherit, keep_upright

- **`BlockDefinition._compile`** skips a text prim that `has_fields` or is
  `keep_upright` and collects it into `bound_prims: list[BoundPrim(prim_dict,
  transform, override_args)]` (transform = the origin shift). `_nested_ops` also
  extends with the child's `bound_prims` mapped through the record pose and the
  WM2 override composition (outermost wins), the same walk the static ops take,
  so A1 falls out of the existing recursion. Invalidation is the existing version
  bump / `BlockRegistry.invalidate`; `bound_prims` is exposed per mirror/scale
  variant beside `render_ops_variant`.
- **`BlockInstance.render_ops()`** = today's result `+ _bound_ops()`. `_bound_ops()`
  memoises on `(variant list identity, definition.version, resolved_key)` with
  `resolved_key = tuple(resolved string per bound prim) + tuple(flip state per
  prim)` -- the `_ov_cache` idiom. A miss rebuilds only the bound ops:
  `TextItem.from_dict(prim)` with `text` replaced by the resolved string, glyph
  outline via `_local_path`, mapped through the prim transform, one text-kind fill
  `RenderOp` per prim (as `_compile` emits). `resolve_values` runs on every call
  (pull-on-paint, O(#fields)); the key compare limits rebuilds to real changes.
- **`keep_upright`** (A5): per prim, net angle = instance rotation + prim angle
  (mirror sign applied); in (90, 270] the glyph path is rotated 180 degrees about
  its bounding-rect centre; a mirrored instance additionally reflects the path
  about that centre's vertical axis. Flip state is in the cache key.
  `shape()`, `boundingRect()` and snap points consume `render_ops()`, so bound text
  takes part in hit-testing and bounds; `prepareGeometryChange` on a key change.
- **Block Editor canvas**: the live `TextItem`s show the authored string; the
  preview frame (the LT4 scratch-definition idiom) resolves with sample values.

### S3 -- Resolver, Edit Attributes dialog, undo, explode, serialization

- **Resolution**: per record -- host source: `instance.attributes[key]` if present
  (override), else `host_values()[host_key]` when the provider exists and knows
  the key, else `None`; instance source: `instance.attributes.get(key, default)`.
  `None` / `""` -> `placeholder`; numbers -> `format_value`; then `resolve_text`
  per bound prim; unknown tokens stay literal (title-block DD-13 contract, A7).
- **Edit Attributes dialog** (`block_attributes_dialog.py`, `QDialog`): rows per
  A4; number rows carry a numeric validator. Entry: `Model_Space.can_edit_attributes
  (inst)` gates an "Edit Attributes..." action in `_build_entity_context_menu`
  (via `entity_context_menu.build_entity_context_menu(on_edit_attributes=)`) and
  in `Model_View._build_plan_context_menu` (exactly one selected instance), both
  calling `Model_Space.open_edit_attributes`; the instance panel gets a
  `"button"` row "Edit attributes..." (the `Edit Roof...` / `Edit Revisions...`
  idiom), disabled when none. OK -> `instance.set_attributes(new)` inside
  `Model_Space.deferred_undo_push` (G9: one undo step) + repaint; Cancel -> nothing.
  Multi-select: the dialog acts on the one right-clicked (or sole selected) instance.
- **Serialization** (G2): definition `attributes` / `host_category` / `scale_mode`
  ride `to_dict` / `from_dict` (`.fpdb` schema 1 and bundled 2, `.fpd` embed, undo
  snapshot); prim `keep_upright` rides `TextItem.to_dict`; instance `attributes`
  already rides `.fpd`, undo snapshot and clipboard (copy/paste carries values);
  the nested record drops it (A1).
- **Explode** (A9): `block_explode.explode_instances` emits each bound prim as a
  plain text primitive holding the resolved string with the flip composed into
  the prim's angle/pos (the WM2 H6 override-bake step); nested bound prims bake
  with the outermost values.

### S4 -- Block Editor authoring

- **Block view** (`block_properties_info.get_properties`): header "Attributes",
  read-only `Count`, `"button"` row "Edit attributes..." opening the **Attributes
  editor dialog** (`block_attributes_editor.py`, sharing row widgets with S3's
  module): a table of records with the house `+` / minus / up / down glyph
  buttons (smoke 2026-10-21; the titleblock-editor and pattern-row idiom). The
  ribbon's Definition-group **Edit Attributes** button opens the same dialog
  (schematic: disabled, D-S14). `Host category`
  (free combo) and `Scale mode` (real size / annotative) are rows in the Block
  view. OK commits one editor edit (one editor undo step; version bump at Save,
  as capability edits do). Rename cascades (A7) in the same commit; Remove of a
  referenced key is refused via `references_of`.
- **Field picker**: the text primitive panel (Block Editor surface only) gains an
  "Insert field" choice row listing the definition's keys -- choosing one appends
  `@[key]` to `Content` -- and a `keep_upright` bool row (a plain TextAnnotation
  ignores it).
- **Sample preview**: the preview frame renders with `values = {k: default}`;
  "Show raw tokens" renders with `values = {}`.

### Reuse (link, don't reinvent)

`titleblock_template.resolve_text` + `TOKEN_RE` (the concept's `substitute` name is a
dead ref; this is the real symbol) · `_local_path` glyph outlines · the
`_ov_cache` memo idiom and `apply_overrides` · the LT4 scratch-definition preview ·
`deferred_undo_push` (G9) · the panel `"button"` row · WM2 H6 explode bake ·
`BlockRegistry.invalidate`.

## Design Decisions

| # | Fork | Chosen | Rejected | Why |
|---|---|---|---|---|
| D1 | Bound layer attachment | Second derived list appended by `render_ops()` | Placeholder `BoundTextOp` in the shared list; child `TextItem` per field | Every op consumer (shape, snaps, explode, ends, overrides) stays unchanged; the flyweight and F1's glyph-outline key hold. A placeholder op forces a new op-kind branch in each consumer; child items break the flyweight and selection chrome. |
| D2 | keep_upright in the static layer? | No -- a keep_upright prim is bound even without fields | Flip at paint over the static op | The flip depends on the instance pose, which the shared list cannot encode; routing it through the bound layer gives one cache key for both. |
| D3 | Resolver home | Pure `block_attributes.py` | Methods on `BlockDefinition` | `block_definition.py` is already large; a Qt-free module tests headless and serves the editor, the dialog, explode and the instance alike. |
| D4 | Override representation | Presence of the key in `instance.attributes` | A parallel `overrides` dict | One dict already rides four paths; A4's uncheck = delete maps onto it directly. |

## Edge Cases & Error Handling

- Unknown token in text -> literal + Block Manager warning row ("field @[x] has no attribute").
- Duplicate or empty key on Add -> refused inline.
- `type: number` with a non-numeric instance value -> placeholder.
- A nested definition declares a key the host redeclares -> outermost wins (A1).
- Attributes declared but no field text -> nothing bound; the dialog still opens.
- Annotative `scale_mode` saved; paints real size until SB1c.
- Explode of a nested bound prim bakes outermost values.
- Rotation crossing the 90/270 threshold rebuilds the bound ops; other rotations hit the cache.
- Legacy nested record with an `attributes` key -> ignored on load.

## Performance

Static ops stay shared (the flyweight gate, `block-system.md`). Per instance:
one `resolve_values` (O(#fields)) per `render_ops()` call and one glyph-outline
build per change in a resolved string or flip state. G6's cache-sharing half is
guarded here; the metric and threshold for the full G6 are confirmed before SB3.

## Acceptance Criteria

- [ ] AC1 A placed instance renders `@[key]` text from its typed values, an override, or the provider; the static ops of two instances of one definition are the same list object (F1).
- [ ] AC2 Definition `attributes`, `host_category`, `scale_mode`, prim `keep_upright` and instance `attributes` round-trip `.fpd`, `.fpdb` (schema 1 and bundled 2) and undo/redo (G2).
- [ ] AC3 A nested bound prim resolves the outermost instance's values (A1).
- [ ] AC4 `keep_upright` flips at 91 degrees, not at 89; a mirrored instance's glyphs read un-mirrored (A5).
- [ ] AC5 Edit Attributes dialog opens from the right-click "Edit Attributes..." item and the panel button, absent/disabled when no attributes, double-click opens nothing; OK = exactly one undo entry; Override uncheck restores the binding (A3/A4).
- [ ] AC6 Attributes editor: Add/Remove/reorder; rename cascades through text; Remove of a referenced key refused (A7); Insert field appends `@[key]`.
- [ ] AC7 Preview shows sample values; raw-token toggle shows tokens (A6).
- [ ] AC8 Explode yields a plain text primitive with the resolved string (A9).
- [ ] AC9 Unknown token -> literal text + Block Manager warning.

## Verification Checklist (VC3 guards, real paths)

| Guard | Scenario -> ground truth | RED mutation |
|---|---|---|
| G1 (stub host) | stub `host_values()` subclass; change the value; paint on a QImage via the real `paint`; glyph path differs; rebuild counter +1 | drop the key compare -> counter +2 |
| G2 | save/load `.fpd`, `.fpdb` (1 and 2), undo/redo snapshot; every S1 field equal | omit `keep_upright` from `to_dict` |
| G6-half | two instances: static prefix of `render_ops()` identical by identity, bound ops distinct | compile bound text into the static list |
| A1 | nested bound prim shows the outer instance's value | skip child bound_prims in `_nested_ops` |
| A5 | 91 deg flips, 89 does not; mirrored path == reflected un-mirrored box | remove the un-mirror |
| A7 | rename rewrites text; Remove of a referenced key refuses | skip `references_of` |
| A9 | explode -> text prim with the resolved string | bake the template string |
| A4 | dialog OK via QTest -> exactly one new undo entry | push per row |
| AC9 | unknown token -> literal + warning row present | -- |

## Code Style & Testing

Google docstrings; relative imports; ASCII-only in new files; tests under
`tests/test_sb1a_*.py` on `qapp` (no pytest-qt); pixel guards compare digests.
