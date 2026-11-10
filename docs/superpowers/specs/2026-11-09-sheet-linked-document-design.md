---
status: proposal
last-verified: 2026-11-09
verified-commit: e18cc00f
applies-to:
  - firepro3d/linked_document.py
  - firepro3d/doc_converter.py
  - firepro3d/linked_doc_watcher.py
  - firepro3d/paper_space.py
  - firepro3d/paper_export.py
  - firepro3d/paper_commands.py
  - main.py
source-tasks: ["todo_open.md: Link a Word document to a sheet so its pages show on the sheet and update with the file (project specification sheets) [P2]"]
---

# Sheet-Linked Document: Design Spec

Consolidating contract for a sheet that shows one page of a linked Word or PDF file. It extends
`paper-space.md`, `model-space-containment-contract.md`, `scene-io.md` and `underlay-workflow.md`;
each gets a one-line pointer here at Account (Rule A: facts live here, not restated there).

Phase 2 record: `.todo/sheet-linked-doc-phase2.md` (Q1-Q14, user-approved 2026-11-09).
Probe record: `.todo/sheet-linked-doc-phase3-probes.md`.

## Goal

Project specifications written in Word (laid out on 11x17 pages with a right margin left clear for
the title block) are linked to sheets, show on screen under the title block, update when the file is
saved, and issue in the exported PDF set as vector pages with selectable text.

## Motivation

Spec sheets are issued beside the drawings with the same title block. Retyping them as sheet text
loses Word's formatting and drifts from the source. A live link keeps one authoring home (Word) and
one issuing home (the sheet set).

## Architecture & Constraints

### New units

| Unit | Purpose | Depends on |
|---|---|---|
| `linked_document.py` | `LinkedDocData` dataclass + pure helpers: page snapshot extraction, page size, placement (scale + rect), content bounds, overlap. No Qt widgets. | PyMuPDF (`fitz`), `QRectF` only |
| `doc_converter.py` | `.docx` -> PDF through Microsoft Word, run in a `powershell.exe` subprocess on a temp copy; `word_available()`; a `QThread` worker so the app stays usable (AC13). | `subprocess`, `tempfile` (the `dwg_converter.py` pattern) |
| `linked_doc_watcher.py` | One `QFileSystemWatcher` per project, watching each linked file's parent folder; debounces and compares (mtime, size) per file; emits `changed(abs_path)`. | Qt core |
| `LinkedPageItem` (in `paper_space.py`) | Paints the sheet's linked page on screen and in print. Not selectable, not movable. | `LinkedDocData` |
| `SetLinkedDocumentCommand` (in `paper_commands.py`) | Undo for link / unlink / page / scale changes. | paper undo stack (`paper-space.md` §17) |

### Data model

`Sheet` gains `linked_document: LinkedDocData | None = None`; `to_dict` writes the key only when set;
`from_dict` reads it with `.get()` (old files load unchanged; `scene-io.md` needs no format bump).

```
LinkedDocData:
  path: str              # stored like underlays: Underlay.relativize_path / resolve_path (Q11)
  page: int              # 1-based page of the source file shown on this sheet (Q2)
  scale_mode: str        # "fit" (default) | "1" | "2" | "custom"   (Q3)
  scale_custom: float    # used only when scale_mode == "custom"
  snapshot_pdf: str      # base64 of a ONE-page PDF: the last good copy of that page (Q6, D2)
  snapshot_at: str       # ISO date-time the snapshot was taken (badge text)
  source_mtime: float    # source file mtime/size at the snapshot (change detection)
  source_size: int
  source_pages: int      # page count of the source at the snapshot (Q10)
  offered_pages: int     # highest page count already offered as new sheets (one-time prompt)
```

The snapshot is the render source for screen, print and export. The live file is read only to
refresh it. That makes the missing-file case the normal path with a badge, not a special renderer.

### Containment amendment

`model-space-containment-contract.md` (retired-paper-instance bullet, D-S2): a sheet holds viewports,
the title block, sheet text **and at most one linked document page** (a sheet property, not a placed
item). At Account the containment line gets that clause plus a pointer here.

### Z order and clip

`LinkedPageItem` sits above the paper background (z 0) and below the title block (z 1), so viewports,
sheet text and the title block all draw over it. It is clipped to the drawing area:
`solve_layout(...).area_rect` when a template is in use; otherwise the drawing-border rect that
`_setup` already draws from `MARGIN` / `INNER_MARGIN` / `TITLE_H` (one helper,
`sheet_drawing_area(scene)`, returns whichever applies, so screen, print and export clip alike).

## Design Decisions

- **D1 Export: vector page placed under the sheet (ratified 2026-11-09, AskUserQuestion).**
  `export_pdf` writes the sheet with `QPdfWriter` as today, with the linked page item and the paper
  background fill left out of that pass. Then PyMuPDF reopens the file and, for each page whose sheet
  has a link, calls `show_pdf_page(dest, snapshot, 1, clip=area, overlay=False)`, which places the
  original page *under* the sheet content. Probe: all 11,727 characters selectable, identical to the
  Word page, about 100 KB and 0.1 s per page. The paper background fill is dropped from the export
  pass because the PDF page is already white and the fill would cover the page placed underneath.
  Rejected: QtSvg (drops all text), SVG text-as-path (2.3 MB per page, not searchable), raster export.
- **D1b Print and screen: picture of the page.** `print_sheets` uses a printer device, so it cannot
  be post-processed. `LinkedPageItem` paints a raster of the snapshot at the device's resolution
  (printer: its DPI; screen: re-rendered for the view's zoom, capped, cached per (page, dpi)).
  Probe: 150 dpi of a 17x11 page takes about 0.1 s.
- **D2 Saved copy inside the project file (ratified 2026-11-09, AskUserQuestion).** One-page PDF,
  base64 in `snapshot_pdf`, the same way title-block logos store `image_data`. About 100 KB per page;
  it travels with the .fpd.
- **D3 Word conversion: `powershell.exe` subprocess driving Word COM, no new Python dependency.**
  Copy the .docx to a temp folder first (works while the file is open in Word or locked by OneDrive),
  then `Documents.Open(ReadOnly)` + `ExportAsFixedFormat(PDF)` + `Quit`, with a hidden window and a
  120 s timeout. Probe: 18.5 s from a cold start. Runs in a `QThread`; the status bar says
  "Updating <file>..." and the sheet keeps its last copy until the new one is ready.
  `word_available()` checks the `Word.Application` COM registration; if it is absent, .docx links
  keep their copy with the badge "Word not available - showing copy from <date>". `.pdf` links never
  need Word.
- **D4 Change detection: watch the folder, not the file.** Word and OneDrive save by writing a temp
  file and renaming it, which drops a file-level watch. The watcher watches each linked file's
  parent folder, debounces 1.5 s, and fires only when (mtime, size) differ from the snapshot. The
  same comparison runs once for every linked sheet on project open (Q5). A manual **Refresh** in
  sheet properties forces the conversion.
- **D5 Refresh is not an undo step but dirties the project.** A refresh rewrites the snapshot fields
  directly (no command), emits `sheetModified` (the bytes `Sheet.to_dict()` writes changed,
  `paper-space.md` §17.7 rule), and shows a status message. A refresh that happens while the project
  loads also marks it modified, so the new copy gets saved.
- **D6 Link, page and scale edits are one undoable command.** `SetLinkedDocumentCommand` swaps the
  whole old/new `LinkedDocData` (or `None`) on the sheet and rebuilds the item. Link, Unlink, page
  change and scale change all go through it (Q12).
- **D7 Placement and scale.** Page size comes from the snapshot (points -> mm). `fit` scale =
  `min(sheet_w / page_w, sheet_h / page_h)`, centred on the sheet (11x17 on ANSI D = 2.0, on ANSI B =
  1.0). Fixed modes use their factor, centred. The scale used appears in the properties panel and
  in the screen-only note when it is not 1.0.
- **D8 Overlap warning.** Content bounds = union of the page's text-block and drawing rects
  (`get_text("blocks")` + `get_drawings()`), mapped through the placement. If they extend past the
  drawing area, the screen-only warning reads "Page content overlaps the title block by N mm"
  (largest overrun). The page is clipped either way (Q4).
- **D9 Badges are a separate screen-only item.** One `LinkedPageBadge` item (top-left of the drawing
  area, above everything) shows at most one line, by priority: missing file / page gone / Word not
  available / overlap / scale note. `render_sheet` hides it, so neither print nor export shows it (Q14).
- **D10 Page count changes (Q10).** Fewer pages: a sheet whose page no longer exists keeps its copy
  with the badge "Page N is no longer in <file>". More pages: once per growth
  (`source_pages > offered_pages`) one prompt lists the pages not on any sheet and offers to create
  a sheet for each, numbered by `SheetManager.suggest_number()`; either answer records `offered_pages`.
- **D11 Linking a multi-page file.** Link... in sheet properties opens a file dialog (.docx, .pdf),
  converts, then shows a page picker when the file has more than one page, with a "Create sheets
  for the other pages" check box (Q2 / AC3). The extra sheets are sheet-level operations (not undoable,
  `paper-space.md` §19.1); the link on the current sheet is the undoable command.
- **D12 Open in Word.** A button in sheet properties opens the resolved file with `os.startfile`
  (Word for .docx, the PDF viewer for .pdf). Disabled when the file is missing.

## Acceptance Criteria

From Phase 2 (AC1-AC13) plus the design rulings:

- [ ] AC1 A sheet's properties panel has a Linked document row (Link... / Relink... / Unlink), Page and Scale rows; the page is fixed to the sheet (placed per D7) under viewports, text and title block; it cannot be selected or dragged.
- [ ] AC2 .docx (through Word) and .pdf (direct) both link.
- [ ] AC3 One page per sheet; linking a multi-page file offers sheets for the other pages.
- [ ] AC4 Fit scale by default (11x17 on ANSI D = 2x, on ANSI B = 1x, centred), with Fit / 1x / 2x / custom in properties.
- [ ] AC5 The page is clipped at the drawing area; an overlap shows the N mm warning.
- [ ] AC6 Saving the file while the project is open refreshes the sheet automatically (the file can stay open in Word); a changed file is picked up on project open; Refresh forces it; a status message reports each refresh.
- [ ] AC7 Missing file, no Word, or page gone: the saved copy shows and exports, with a badge naming the cause and date; Relink works.
- [ ] AC8 A file that grew prompts once to create sheets for the new pages.
- [ ] AC9 The path is stored like underlays (relative inside the project tree, absolute otherwise).
- [ ] AC10 Exported PDF: the page is vector with selectable text, at the right size and position (D1).
- [ ] AC11 Badges and warnings never print or export.
- [ ] AC12 Open in Word; link / unlink / page / scale are undoable; a refresh is not an undo step.
- [ ] AC13 The app stays usable during a conversion.
- [ ] AC14 Printing draws the page as a picture at the printer's resolution (D1b).
- [ ] AC15 The saved copy is inside the .fpd and survives save -> load with the source file deleted (D2).

## Verification Checklist

Guards (VC3: real paths, real objects, PDF fixtures checked in under `tests/fixtures/linked_doc/`, a
two-page 17x11 PDF and a one-page variant; RED with the change reverted):

- [ ] Link a fixture PDF to an ANSI D sheet: `LinkedPageItem` exists between z 0 and z 1, placement rect = centred 2x page, not selectable.
- [ ] Export that sheet: the output PDF page is ANSI D, its text (via `fitz`) contains a fixture string, the text's bbox sits at 2x the fixture position, and the badge text is absent.
- [ ] Clip: fixture text placed past the drawing area is absent from the exported text inside the strip rect; the overlap warning reports the expected mm.
- [ ] Watch: rewrite the fixture file in a temp folder by temp-file + rename; the snapshot updates within the debounce (event loop pumped), `sheetModified` fires, the undo stack index does not move.
- [ ] On-open: save, change the file, load through the real load path; the snapshot is refreshed.
- [ ] Missing: save, delete the source, load; the sheet shows the copy, the badge says missing, export still contains the fixture text.
- [ ] Page gone: shrink the file to one page while page 2 is linked; the copy stays and the badge names page 2.
- [ ] Growth: grow the file to 3 pages; exactly one prompt (stubbed dialog), recorded in `offered_pages`; a second refresh does not prompt again.
- [ ] Round trip: save -> load -> save is byte-stable for `linked_document` (snapshot included); an old file without the key loads with `None`.
- [ ] Undo: link, change page, change scale, unlink, each undone and redone restores the data and the item.
- [ ] Converter: one live test converts a tiny .docx through Word and is skipped when `word_available()` is false.
- [ ] Print path: `render_sheet` onto a `QImage` device paints the page (non-white pixels inside the area) and no badge.
- [ ] User smoke: the real 26307 spec on an ANSI D sheet, edited and saved in Word while linked; exported set opened in a PDF viewer.

## Existing Code Context

- `paper_space.PaperScene._setup`: paper background `addRect` z 0 (white brush), `TitleBlockTemplateItem` z 1, drawing border z 2 (no template), `SheetViewport` z 5, `TextItem` z `Z_ANNOT_TEXT`.
- `paper_export.render_sheet` builds a transient `PaperScene` and calls `scene.render(painter, page_rect, QRectF(0, 0, w_mm, h_mm))`; `export_pdf` loops sheets on one `QPdfWriter`; `print_sheets` takes a printer.
- `titleblock_template.solve_layout(layout, w, h, values).area_rect / .strip_rect` (mm).
- `Underlay.relativize_path(abs, project_dir)` / `resolve_path(stored, project_dir)`; project dir = folder of `scene._project_path`.
- `underlay_controller.import_pdf`: the fitz -> `QImage` raster block (extract into a shared page-raster helper, GENERALIZE).
- `dwg_converter.convert_dwg_to_dxf`: subprocess with hidden window, timeout, temp dirs.
- `PaperScene.notify(message, timeout_ms)` for status messages; `SheetProperties` adapter for the panel rows (`paper-space.md` §19.4).

## Edge Cases & Error Handling

- Conversion timeout or Word error: keep the copy, badge "Could not update from <file>: <reason>", status message; no retry loop (the next save retries).
- A save while a conversion runs: queue one follow-up conversion per file, never run two at once for one file.
- Two sheets link the same file (different pages): one watch, one conversion, every linked sheet refreshed from that one PDF.
- Unlink removes the snapshot with the link (undo restores it).
- Paper size change: placement recomputes (fit follows the new sheet); no data change.
- Project not yet saved (no project dir): store the absolute path; it is relativized on first save, as underlays are.

## Performance & Security

- Snapshot render is cached per (sheet, page, dpi); zoom re-renders only when the needed dpi grows past the cache by more than 1.5x, capped at 300 dpi on screen.
- Only the user's own files are opened; the PowerShell script is a fixed string with the file paths passed as arguments, never interpolated into script text.

## Follow-ups (filed at Phase 2)

- "New sheets from document..." in the sheet list.
- Export refreshes changed linked files before exporting.
