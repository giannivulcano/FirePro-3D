---
status: built            # ratified 2026-11-05 (Phase 2 criteria + design approval); N5 extended in review; N10, N13, AC5 changed at smoke 2026-11-06
last-verified: 2026-11-06
verified-commit: bfe51a30  # merge on main (v0.93.0)
applies-to:
  - firepro3d/text_item.py          # apply_grip clamp order, ink voff, printed paint in a pass
  - firepro3d/manip_handle.py       # GripHandle reach for text
  - firepro3d/sketch_adapters.py    # _TextBoxAdapter (only if the reach needs it)
  - firepro3d/paper_display.py      # new TextItem pass branch
  - firepro3d/paper_space.py        # schematic drop box
  - firepro3d/block_definition.py   # text_sizing, text_scale keys
  - firepro3d/block_properties_info.py # Text sizing + Drawing scale rows
  - firepro3d/block_editor.py       # seeding, new-schematic defaults
  - firepro3d/scene_io.py           # N13 call at the end of load
  - firepro3d/property_manager.py   # dimension rows commit real edits
  - firepro3d/dimension_edit.py     # set_mixed
  - firepro3d/schematic_scene.py    # render scene printed flag
  - firepro3d/model_space.py        # Note modes, previews, note_allowed
  - firepro3d/note_controller.py    # place with a preset leader
  - firepro3d/text_leader.py        # box + leader from three clicks
  - firepro3d/placement_input_coordinator.py # per-step anchor
  - main.py                         # Build Note button, status text
source-tasks:
  - "todo_open.md: Notes on schematics: text box polish, paper-correct text size, three-click Note placement"
---

# Notes on Schematics -- Design Spec

Consolidating contract for a change spanning `text-annotation-system.md`,
`2026-11-04-text-leader-annotations-design.md`, `schematics.md`,
`parametric-constraint-system.md` and `ribbon-bar.md`. Each gets a one-line pointer here at
Account; full rewrites are follow-ups (Rule A).

## Goal

Add notes to schematics that print at a set size, with a text box that behaves when tied,
looks centred, and places by three clicks: arrow tip, elbow, box.

## Motivation

The user's end goal is notes on schematics. A live recording on Blue Stair showed tied text
refusing resizes. Schematic text scales with the viewport, against D-S7. The Note tool is off on
schematics and places by two corners, which does not say where the arrow goes.

## Architecture & Constraints

- **C5 stands:** one Text item, one renderer. Printed size is a paint-time factor on the same item.
- **Primitives stay real size.** No field changes units, so the adapter, panel and grips keep
  working in scene mm. Printed height is derived.
- **No size depends on the viewport scale** except at paint, so the live crop cannot go circular.
- **Dual serialization:** both new definition keys travel `to_dict` / `from_dict`, so `.fpd`, `.fpdb`
  and the undo snapshot agree. Sparse: a schematic that never switches writes neither key.
- **`scene.items(source_rect)` selects items by bounds:** text scaled in a pass must report its
  scaled bounds during that pass (the SB1c D6 pattern).

## Design Decisions

Ratified by the user 2026-11-05 (Phase 2 questions, Phase 3 questions, design approval).

### Part 1: Tied text grips

| # | Decision |
|---|---|
| N1 | **The grip stays on the cursor** where constraints allow. A grip on an item pinned elsewhere reaches its target: a centre pin grows both sides, `rm +30` on a 120 box gives 180. Root cause of the lag: `pin_vars` pins all four text vars and `GripHandle._solve_frame` re-applies at the solved point, halving the gap per pass. |
| N2 | **Reach by re-aim.** After the first solve, each local axis with gain above a floor re-applies the grip at the point the measured gain predicts lands on target; an axis the constraints hold keeps today's slide. Scope: text. Rectangles share the lag; filed, not fixed here. |
| N3 | **Clamp before anchoring.** `TextItem.apply_grip` limits the dragged edge to the minimum before re-anchoring, so the opposite edge never moves. Root cause of the refusal: `_reanchor` ran before `_commit_box_size` clamped, the box slid off its tie and the solve did not converge. This also fixes the silent slide on an untied box. |
| N4 | **A tied box stops at its text, silently.** Past the minimum height the grip stops with no status. A width drag on a tied box stops at the narrowest width whose wrapped text fits the current box height. An untied box keeps growing in height as today. |
| N5 | **Real conflicts still report.** `CONFLICT_STATUS` stays for an edit the constraints truly forbid. A grip on the pinned point itself still does nothing, and moving a box its tie holds is still refused. A grip drag on a tied corner slides on the corner's free axis; a grip with no free axis stays put (user ruling, 2026-11-06). Text grips post no status, a box held by two corners included, so only a move reports. A rotated box's far corner holds. |

### Part 2: Centring

| # | Decision |
|---|---|
| N6 | **V Align Middle centres the ink.** Gaps above and below the glyph outlines are equal, in fixed and auto boxes, with or without descenders. The baseline moves with the typed content (user ruling). `@[Field]` text keeps today's line box, in the editor and on placements, so tags share a baseline and the approved Room Tag is unchanged (user ruling, 2026-11-05: a descender would move a value 0.39 mm at 3 mm). A Note's words are typed text. Top and Bottom are unchanged. Empty text uses today's rule. |
| N7 | **One home.** `TextItem._layout_offsets` owns it, so glyphs, caret, selection, compile and `bound_text_ops` follow. Ink is measured from an outline with no vertical offset, cached until the layout changes. |
| N8 | **Sheet text is out of scope.** It has no V Align row, and its paint ignores the offset. |

### Part 3: Printed text in schematics

| # | Decision |
|---|---|
| N9 | **Two definition keys, schematics only.** `text_sizing: "printed"` (absent = real size) and `text_scale: float` (the drawing scale N of 1:N; absent = real size). |
| N10 | **Printed height = `height_mm / text_scale`.** Everything else in the box scales with it. The Height row shows and parses printed size through the `_printed_height` format. Padding and Corner Radius show and parse printed mm the same way, so the armed Note rows read the same before and after placement (smoke, 2026-11-06). |
| N11 | **Rows.** Schematic Block view gains **Text sizing** (Real size, Printed) and **Drawing scale** (shown when Printed). Drawing scale only sets how large text looks in the editor. |
| N12 | **New schematics start Printed**, at the project drawing scale, stored on the definition so a template carries it. A new text defaults to `DEFAULT_TEXT_HEIGHT_MM` printed. |
| N13 | **Old schematics turn Printed once, on opening a project saved below `SAVE_VERSION` 12** (user ruling at smoke, 2026-11-06, reversing "old schematics stay Real size"). A schematic takes N = 1 / S of its first viewport in sheet order, so its text starts at today's printed size and stops following the viewport, and a text added later matches the drawing in the editor as it does on the sheet (smoke, 2026-11-06: an empty schematic at the project's 1:100 drew a Note ten times too large against a 1:10 viewport). A schematic on no sheet takes the project drawing scale. Stored heights do not change, and the editor looks the same. Real size stays a row choice: chosen and saved at version 12 it stays. Switching by the row keeps the editor look unchanged; only the print changes. |
| N14 | **Changing Drawing scale** resizes the text on the canvas about each anchor (N16), one undo step; printed size stays. If a tie refuses, the row reverts with a status. |
| N15 | **Viewport paint.** A new `TextItem` branch in `apply_paper_overrides`, with restore, sets the pass factor. Text paints scaled `k = 1 / (text_scale * S)`, where S is the viewport's paper mm per model mm, so it prints at N10 at any scale and at NTS. Border weight plots true mm in this pass. A Real size schematic is untouched by the branch, border included. |
| N16 | **Anchor.** With no leader the box scales about its alignment point (`align` + `valign`), the rule bound text follows. With a leader, the tip and elbow stay put and box and shoulder scale about the elbow. |
| N17 | **Extent reads editor size**, so S never feeds it and NTS has no loop. It holds every text leader's elbow and tip, so a note past the drawing is not cropped (user ruling, 2026-11-05). A printed schematic drops at `extent / text_scale`, clamped to the sheet, so it opens matching the editor. |
| N18 | **Overrun.** Printed text larger than an NTS box allows is clipped at the viewport edge. The drawing does not shrink to fit. |
| N19 | **Nested blocks unchanged.** Annotative blocks already print at authored mm; real-size blocks scale with the view. |

### Part 4: Three-click Note

| # | Decision |
|---|---|
| N20 | **Clicks.** Tip, elbow, then the box edge where the elbow joins it. Replaces two-corner Note. |
| N21 | **Third click.** With K the elbow and C the click: `|dx| >= |dy|` picks edge L or R at `C.x`, the shoulder level with K; otherwise T or B at `C.y`, the box centred on `K.x`. A shorter click lands at `TEXT_LEADER_MIN_SHOULDER_MM`. The click's other coordinate is ignored so the shoulder stays perpendicular (D3). |
| N22 | **Box.** Starts 60 mm printed wide, one line tall, wrapped. It extends away from the elbow. New constant, no magic number. Printed mm convert by the canvas: a Printed schematic's own scale, else the project drawing scale, a Real size schematic included (user ruling, 2026-11-05). |
| N23 | **While typing.** The editor opens at once. The box grows downward and the shoulder stays on the first line; on an L or R edge the attach fraction `t` follows the height. On a B edge the box grows upward instead, so the elbow stays where it was clicked (user ruling, 2026-11-05). Commit keeps D13: empty text deletes the note. |
| N24 | **Preview and cancel.** Tip to elbow to cursor previews live, with the box after the elbow. Esc at any step leaves nothing. Snap applies at each click. The input HUD anchors on the current step. |
| N25 | **Where.** Plan and detail save a Note block (D8). A schematic saves a Text primitive with a leader, into the definition (D12). Block editors and sheets keep Text with Leader on. Section and elevation stay off. |
| N26 | **Button.** Plan and detail keep Architecture > Annotations. A Note button sits beside Text on the Build tab, live on Schematic tabs and disabled on Block tabs with a tooltip. Amends D11 and D12. |
| N27 | **Style.** The armed tool's rows stamp the note on every surface; Leader is on by construction. |

## Acceptance Criteria

- [x] AC1 A box tied by one point resizes from every other grip with no refusal and the grip at
      the cursor; a centre pin grows both sides; the tied point never moves. Moving is refused only
      when the tie really holds the box.
- [x] AC2 A tied box dragged past its text stops there with no status; width stops where wrapped text
      fits the current height.
- [x] AC3 At V Align Middle, typed text has equal ink gaps in the editor, on placements and in PDF;
      `@[Field]` text keeps today's look.
- [x] AC4 New schematics: text prints at its printed height in every viewport, NTS included; the
      Drawing scale row sets its editor size only.
- [x] AC5 An old schematic turns Printed when its project opens: its text prints at the size its first
      viewport gave at base, and no longer follows the viewport. Real size chosen by the row and saved
      stays Real size. A text leader past the drawing counts toward the extent (N17), so such a schematic's NTS fit can differ from base.
- [x] AC6 Note places by tip, elbow, box edge, then typing, on plan, detail and schematic; in a schematic
      it saves as a text with a leader. Esc at any step leaves nothing.
- [x] AC7 Save / reload and undo keep `text_sizing`, `text_scale`, and a schematic note.

## Verification Checklist

Guards drive the real path and are shown RED with the change reverted (VC3).

- [x] G1 Shown view, Blue Stair network rebuilt in a fixture with `bl` tied to a line: drag grips
      2, 3, 1, inward and out; no `CONFLICT_STATUS`, tied point unmoved, grip at cursor. Centre pin:
      `rm +30` gives width 180. Untied box past its text: far edge unmoved.
- [x] G2 `TextItem` paint and a Note's real `bound_text_ops` output: ink gaps equal at M, with and
      without a descender, in three fonts. Placed `@[Field]` text keeps a shared baseline.
- [x] G3 Exported PDF: 3 mm text in 1:10, 1:20 and NTS viewports measures 3 mm cap height; a version
      11 file reopened measures the same in its first viewport, and stays that size in a resized one.
- [x] G4 Posted clicks on plan, detail and schematic: tip, knee and box edge land at the clicks, the
      editor opens, shoulder perpendicular on all four edges; Esc at each step leaves nothing.
- [x] G5 Save / reload / undo round trip of both keys and a schematic note.
- [x] Keep-green by touched module (VC5). Rewrites sanctioned by this spec: two-corner Note in
      `test_note_placement.py` and `test_note_small_items.py`.
- [x] Smoke on Blue Stair, a new schematic on a sheet at 1:20 and NTS, and a plan note.
- [x] Perf: ink measure cached; no new per-paint work on a text outside a printed pass.

## Existing Code Context

- `manip_handle.GripHandle._solve_frame`, `sketch_adapters._TextBoxAdapter` (`pin_vars`, `collapses`).
- `text_item.apply_grip`, `_commit_box_size`, `_reanchor`, `_layout_offsets`, `_glyph_outline_local`,
  `_height_row`, `paint`.
- `paper_display.apply_paper_overrides`, `_apply_block` (the mutate + restore pattern),
  `annotative.paper_scene_size` (no caller yet; reuse it).
- `paper_space.SheetViewport.paint` (S), `schematic_scene.SchematicSceneManager.extent`.
- `note_controller.NoteController.place`, `NoteTemplate`; `text_leader.solve_knee`, `attach_and_knee`.

## Edge Cases & Error Handling

- **Rotated text:** N2 measures in the box's local axes.
- **Bound text:** keeps the line box at Middle (N6).
- **Note drag across an edge:** the third-click choice follows the click only; later knee drags stay D4.
- **Leader in a printed viewport:** the End keeps its existing paper sizing.
- **A tie at a different S:** ties hold at the drawing scale. A viewport at another scale draws the box
  about its anchor (N16), so a tied corner can sit off its line there. This is paint only.
- **Template:** both keys travel with Save as Template.

## Divergences

- Rectangles keep the grip lag (N2); filed as a follow-up.
- `schematics.md` D-S7 claimed paper-fixed text with no code behind it; true for Printed once built.
- An old `.fpdb` schematic or template loaded into a project stays Real size until switched: N13 runs
  on project open only. Filed as a follow-up.

## Follow-ups

Filed at Phase 6: rectangle grip reach; V Align on sheet text; slow redraw of a schematic with nested blocks (P1); old `.fpdb` schematics stay Real size. Verified by reduced keep-green, the panel set and user smoke: the full suite was waived by the user.
