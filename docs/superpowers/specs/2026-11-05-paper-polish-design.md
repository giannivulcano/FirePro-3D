# Paper space polish (2026-11-05)

Ratified record for four small paper changes that touch `paper-space.md`, `system-blocks.md` and
`selection-manipulator.md`. Each spec keeps the fact it owns; this file holds the decisions and acceptance
criteria. Also closes the `3/4"=1'-0"` backlog bug (same table).

## Measured base (4d059779)

- `ViewTitleLabel._paper_pen_width` is None, so `render_op.paint_ops` takes the canvas branch: the block's stroke
  is cosmetic, 1.00 px at 1.5 to 48 px/mm. The composite line is a true 0.30 mm at every zoom. The hook is set only
  by `paper_display._apply_block` during a viewport pass, and a title is not in one.
- `PaperScene` builds its manipulator with `handle_units="mm"`: 4 mm grips, 6 px at fit, 192 px at 48 px/mm. The
  stated reason (they "plot true to scale") is wrong: the manipulator is `PAPER_EXCLUDED`. `SectionScene` already
  runs `handle_units="px"`.
- `SCALE_PRESETS`: 3/4" is 1:12, so 1" displays as 3/4". `float_to_scale_str` rounds 1:12.5 to 1:12.
  `scale_to_float` refuses `1"=10'`. A bad string raises `ValueError` in `ViewportProperties.set_property` and
  `SheetViewPropertiesDialog.get_scale`.

## Decisions (ratified at the Phase 2 FP1 gate)

- **D1 Grips:** paper grips are a constant 9 px on screen, as in model space (`MANIP_HANDLE_SIZE_PX`).
- **D2 Title ink:** the bubble is a true 0.30 mm (`VIEW_TITLE_LINE_PEN_MM`), the same as the line, on screen and in
  the PDF. A block stroke with a named weight keeps its own mm.
- **D3 Line grip:** a grip on the line's right end; dragged, the length is stored in mm and survives resize and
  rescale. An undragged title keeps today's rule (follows the box).
- **D4 Reset:** the Title Position button and the context-menu entry reset position and line together; the label
  becomes "Reset Title".
- **D5 Presets:** add 1:1000, 1:500, 1:250, 1:150; 1/32", 1/16", 3/32" = 1'-0"; 1"=10', 20', 30', 40', 50', 60',
  100'. Not added: 6"=1'-0", 1:2.
- **D6 Custom:** a `Custom...` item at the end of the panel's Scale list opens a small input accepting `1:125`,
  `1:12.5`, `3/4"=1'-0"`, `1"=15'`. Bad text shows a notice and keeps the old scale. A custom value is listed as
  its own entry.
- **D7 3/4" bug:** the table is fixed to 1:16. Saved 1:12 values are not migrated: they keep their size and read
  `1"=1'-0"`.
- **D8 Model scale:** shares the one preset table, so it gains the same entries.

Ratified at the plan gate: a custom value is stored as a ratio only, so `1"=15'` reads back as `1:180`
(no label is stored; `1:600` would be ambiguous otherwise).

## Acceptance criteria and guards

| AC | Criterion | Guard (ground truth) |
|----|-----------|----------------------|
| AC1 | Every preset round-trips; 3/4" is 1:16; 1" reads 1"; no two presets share a ratio | `float_to_scale_str(scale_to_float(l)) == l` over the raw list, with hand-written ratios |
| AC2 | `1"=10'` and `1:12.5` parse and read back; a saved 1:12 keeps w/h and reads 1" | parse + label; load a saved viewport and assert w/h |
| AC3 | Custom... sets a typed scale through the real panel row, one undo; bad text leaves scale, notice shown, no raise; Cancel changes nothing | drive the row's Selector; assert `data.scale`, undo stack count |
| AC4 | The bubble's stroke is 0.30 mm +/- 10% at 3, 12 and 48 px/mm and in a 300 dpi render; a named-weight stroke keeps its mm | pixel ink across the stroke, as the 1b probe measured |
| AC5 | Line grip sits at the line end; drag changes length only (x), one undo; Esc restores; stored length survives box resize, title move, save/load; an old file loads as auto; reset restores auto and position | real manipulator drag; rendered line end; `to_dict`/`from_dict` |
| AC6 | Paper grips measure 9 px at fit, 12 and 48 px/mm, viewport and text alike; a press on a grip hits at each zoom | real `PaperGraphicsView`, device-rect of the handle, `handles_at` |
| AC7 | A grip never appears in a PDF or sheet render | render with a selection; compare ink |
