---
status: built             # ratified 2026-11-09 (Phase 2 Q1-Q14 + D1/D2 AskUserQuestion); BUILT 2026-11-10 on feature/sheet-linked-doc (0.96.0); user smoke on the 26307 spec passed 2026-11-10
last-verified: 2026-11-10  # Account: as-built units, data model (last_error), drawing_area, D1/D1b/D6/D9/D10/D12 details, Lifecycle section, ACs ticked; prior 2026-11-09 design
verified-commit: f1dcede4  # feature/sheet-linked-doc close (0.96.0); prior e18cc00f design
applies-to:
  - firepro3d/linked_document.py      # LinkedDocData + pure helpers (placement, badge, export geometry, raster cache, paths)
  - firepro3d/doc_converter.py        # .docx -> PDF through Word (D3)
  - firepro3d/linked_doc_watcher.py   # folder watch (D4)
  - firepro3d/linked_doc_service.py   # LinkedDocService: refresh + link flows, one per window (D4, D5, D10, D11, Lifecycle)
  - firepro3d/pdf_raster.py           # shared PDF page -> QImage helper (D1b; also the underlay raster import)
  - firepro3d/paper_space.py          # Sheet.linked_document, SheetProperties link rows, LinkedPageItem, LinkedPageBadge, PaperScene.drawing_area / link seams only (rest: paper-space.md)
  - firepro3d/paper_export.py         # render_sheet export_pass + export_pdf post-pass only (rest: paper-space.md)
  - firepro3d/paper_commands.py       # SetLinkedDocumentCommand only (rest: paper-space.md)
  - firepro3d/scene_io.py             # sheets[].linked_document path relativize on save / resolve on load only (rest: scene-io.md)
  - firepro3d/underlay_controller.py  # import_pdf raster call into pdf_raster only (rest: underlay-workflow.md)
  - firepro3d/constants.py            # PDF_PT_PER_MM, Z_PAPER_LINKED_*, LINKED_DOC_*, LINKED_PAGE_*, LINKED_BADGE_* only
  - main.py                           # LinkedDocService wiring, rebind / reset / check_all_on_open / shutdown call sites only
source-tasks: ["todo_open.md: Link a Word document to a sheet so its pages show on the sheet and update with the file (project specification sheets) [P2]"]
---

# Sheet-Linked Document: Design Spec

Consolidating contract for a sheet that shows one page of a linked Word or PDF file. It extends
`paper-space.md`, `model-space-containment-contract.md`, `schematics.md` (D-S2), `scene-io.md`,
`underlay-workflow.md` and `titleblock-template-system.md`; each carries a one-line pointer here
(Account 2026-11-10; Rule A: facts live here, not restated there).

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
| `linked_document.py` | `LinkedDocData` dataclass + pure helpers: page snapshot extraction, page size, placement (scale + rect), content bounds, overlap, badge text (D9), export geometry + `place_pages_under` (D1), raster dpi + cached `render_snapshot` (D1b), stored/loaded path helpers (Q11), `path_key`. No Qt widgets. | PyMuPDF (`fitz`), `QRectF`, `QImage` only |
| `pdf_raster.py` | `pdf_page_to_qimage(page, dpi)`: one PDF page -> detached RGB888 `QImage`. Shared by `LinkedPageItem` and the PDF underlay raster import (`underlay_controller.import_pdf`, GENERALIZEd out of it). | PyMuPDF, `QImage` |
| `doc_converter.py` | `.docx` -> PDF through Microsoft Word, run in a `powershell.exe` subprocess on a temp copy; `word_available()`; a `QThread` worker (`ConvertWorker`) so the app stays usable (AC13). | `subprocess`, `tempfile` (the `dwg_converter.py` pattern) |
| `linked_doc_watcher.py` | One `QFileSystemWatcher` per project, watching each linked file's parent folder; debounces and compares (mtime, size) per file; emits `changed(abs_path)`. | Qt core |
| `linked_doc_service.py` | `LinkedDocService` (one per window, `MainWindow.linked_docs`): owns the watcher, runs one conversion per file at a time (one follow-up queued), applies refreshes to every sheet linking the file, the link / relink / page-change flows, the growth prompt and sheet creation (D4, D5, D10, D11, Lifecycle). Its Word check `word_ok()` is the one the badge uses. | the units above, paper commands |
| `LinkedPageItem` (in `paper_space.py`) | Paints the sheet's linked page on screen and in print. Not selectable, not movable, takes no mouse button. | `LinkedDocData` |
| `LinkedPageBadge` (in `paper_space.py`) | The screen-only one-line badge (D9). | `badge_text` |
| `SetLinkedDocumentCommand` (in `paper_commands.py`) | Undo for link / relink / unlink / page / scale changes (D6). | paper undo stack (`paper-space.md` §17) |

### Data model

`Sheet` gains `linked_document: LinkedDocData | None = None`; `to_dict` writes the key only when set;
`from_dict` reads it with `.get()` (old files load unchanged; `scene-io.md` needs no format bump).
In memory `path` is always absolute: `save_to_file` rewrites the path on the saved `to_dict` copy
(`relativize_sheet_links`), and `load_from_file` makes it absolute again (`resolve_sheet_links`)
against the project file's folder. The project file and the autosave/recovery file use that same
save/load pair.

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
  last_error: str        # runtime only, never saved: the last conversion error (badge, Edge Cases)
```

`to_dict` writes the ten persisted fields above `last_error`.

The snapshot is the render source for screen, print and export. The live file is read only to
refresh it. That makes the missing-file case the normal path with a badge, not a special renderer.

### Containment amendment

`model-space-containment-contract.md` (retired-paper-instance bullet, D-S2): a sheet holds viewports,
the title block, sheet text **and at most one linked document page** (a sheet property, not a placed
item). The containment line and its owner `schematics.md` D-S2 carry that clause plus a pointer here
(Account 2026-11-10).

### Z order and clip

`LinkedPageItem` sits above the paper background (z 0) and below the title block (z 1)
(`Z_PAPER_LINKED_PAGE`), so viewports, sheet text and the title block all draw over it. The badge
sits above every sheet item and below `Z_PREVIEW` (`Z_PAPER_LINKED_BADGE`); `constants.py` owns both
values. The page is clipped to the drawing area returned by one method,
`PaperScene.drawing_area()`: the template's solved `area_rect` when a `TitleBlockTemplateItem` is
shown; otherwise the drawing-border rect that `_setup` draws from `MARGIN` on every side. Screen,
print and export all clip to it. `_setup` builds the page and badge after the title block, so the
area is known; `refresh_linked_page()` rebuilds only those two items.

## Design Decisions

- **D1 Export: vector page placed under the sheet (ratified 2026-11-09, AskUserQuestion).**
  `export_pdf` writes the sheet with `QPdfWriter` as today, with the linked page item and the paper
  background fill left out of that pass. Then PyMuPDF reopens the file and, for each page whose sheet
  has a link, calls `show_pdf_page(dest, snapshot, 0, clip=clip, overlay=False)`, which places the
  original page *under* the sheet content. As built: `render_sheet(..., export_pass=True)` calls
  `PaperScene.prepare_for_output(export_pass=True)` and returns the sheet's `ExportGeometry`
  (`linked_export_geometry()`): `dest` = placement rect clipped to the drawing area, in sheet PDF
  points, and `clip` = the same region in snapshot points, so the page lands at exactly the placement
  scale. `export_pdf` collects them and, after the painter ends, runs
  `linked_document.place_pages_under` (saved to a temp file, then replaced); a failed post-pass raises
  `OSError` and leaves the plain sheet export. Probe: all 11,727 characters selectable, identical to the
  Word page, about 100 KB and 0.1 s per page. The paper background fill is dropped from the export
  pass because the PDF page is already white and the fill would cover the page placed underneath.
  Rejected: QtSvg (drops all text), SVG text-as-path (2.3 MB per page, not searchable), raster export.
- **D1b Print and screen: picture of the page.** `print_sheets` uses a printer device, so it cannot
  be post-processed. `LinkedPageItem` paints a raster of the snapshot at the device's resolution
  (printer: its DPI; screen: re-rendered for the view's zoom, capped, cached per (page, dpi)).
  Probe: 150 dpi of a 17x11 page takes about 0.1 s. As built (`linked_document.raster_dpi`, values
  in `constants.py`): screen dpi climbs a `LINKED_PAGE_DPI_STEP` ladder from `LINKED_PAGE_MIN_DPI`,
  capped at `LINKED_PAGE_SCREEN_MAX_DPI`; print uses the device's need, capped at
  `LINKED_PAGE_PRINT_MAX_DPI` (a memory bound set at plan approval, so a printer above that cap gets
  the capped raster). `render_snapshot` caches per (snapshot, dpi), `LINKED_PAGE_RASTER_CACHE_SIZE`
  entries shared by every sheet. `print_sheets` goes through `render_sheet`, whose
  `prepare_for_output()` hides the badge.
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
  whole old/new `LinkedDocData` (or `None`) on the sheet and rebuilds the item. Link, Relink, Unlink,
  page change and scale change all go through it (Q12). Both states are deep copies, so unlink + undo
  brings the snapshot back with the link. Because a refresh is not an undo step (D5), when undo or a
  later redo restores a state that links the same file (`path_key`) and page as the live one, the
  live refresh fields (`snapshot_pdf`, `snapshot_at`, `source_mtime`, `source_size`, `source_pages`,
  `offered_pages`, `last_error`) carry over; the first redo (the push) does not carry over, so a
  same-file relink keeps the copy it brings.
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
  available / conversion error (Edge Cases) / overlap / scale note (`linked_document.badge_text`; a
  saved copy that cannot be read shows "The saved copy of <file> cannot be read" in place of the
  overlap and scale lines). `render_sheet` hides it through `PaperScene.prepare_for_output`, so
  neither print nor export shows it (Q14).
- **D10 Page count changes (Q10).** Fewer pages: a sheet whose page no longer exists keeps its copy
  with the badge "Page N is no longer in <file>". More pages: once per growth
  (`source_pages > offered_pages`) one prompt lists the pages not on any sheet and offers to create
  a sheet for each, numbered by `SheetManager.suggest_number()`; either answer records `offered_pages`.
  As built, every new sheet (here and in D11) comes from `SheetManager.create()`, is named
  "<file stem> - Page N" and takes the scale setting of the link it came from.
- **D11 Linking a multi-page file.** Link... in sheet properties opens a file dialog (.docx, .pdf),
  converts, then shows a page picker when the file has more than one page, with a "Create sheets
  for the other pages" check box (Q2 / AC3). The extra sheets are sheet-level operations (not undoable,
  `paper-space.md` §19.1); the link on the current sheet is the undoable command. Relink... runs the
  same dialog and conversion without the page picker: it keeps the old page (clamped to the new
  file's page count) and the old scale setting.
- **D12 Open in Word.** A button in sheet properties opens the resolved file with `os.startfile`
  (Word for .docx, the PDF viewer for .pdf; the button reads "Open in Word" or "Open PDF"). Disabled
  when the file is missing.
- **Sheet properties rows (as built, `SheetProperties._linked_rows`).** Unlinked: one **Linked
  Document** row with a "Link..." button (disabled without a service). Linked: **Linked Document**
  (label "<file>, page N", tooltip = full path), then buttons **Relink...**, **Unlink**, **Refresh**
  (disabled while the file is missing) and **Open in Word / Open PDF** (D12), the **Linked Page** enum
  (1..max(source pages, page)), the **Page Scale** enum (Fit / 1x / 2x / Custom..., plus the current
  "Custom (Nx)" value when set) and the read-only **Scale Used** label ("Nx", "-" when the copy cannot
  be read). Linked Page goes through `LinkedDocService.change_page`; Page Scale, Unlink and the link
  flows push `SetLinkedDocumentCommand`; Refresh calls `request_refresh`.

### Lifecycle (as built)

- `MainWindow` builds one `LinkedDocService` and sets it on the canonical `PaperScene`
  (`paper_scene.linked_docs`, the badge's Word check); the paper undo stack's `indexChanged` calls
  `rebind()` (re-point the watcher at the current sheets' files), as do sheet create / delete and
  sheets added by D10 / D11.
- `new_file` and every project load (`_apply_loaded_file`, shared by Open and crash recovery) call `reset()`: it drops
  queued link callbacks, then rebinds. A link or page change whose conversion finishes after its sheet
  is no longer the shown one is dropped with the status "Link of <file> cancelled: the sheet changed".
- Open (`_load_project`) and crash recovery (`_check_recovery`) call `check_all_on_open()` once, after
  the load has set the modified flag (cleared on Open, set on recovery), so a refresh on Open dirties
  the project (D5).
- `closeEvent` calls `shutdown()` (ratified 2026-11-09, "Close now, drop update"): running conversions
  are disconnected and cancelled, the sheet keeps the copy it had; the PowerShell child is not killed.
- Export files go through a transient `PaperScene` with no service; its badge falls back to
  `doc_converter.word_available()`.

## Acceptance Criteria

From Phase 2 (AC1-AC13) plus the design rulings. All delivered and guarded 2026-11-10 (each AC
mapped to its code and guard test at the VC9 seam review; AC14 is guarded on a `QImage` device, not
a real printer, per the harness rule against real-driver `QPrinter`s):

- [x] AC1 A sheet's properties panel has a Linked document row (Link... / Relink... / Unlink), Page and Scale rows; the page is fixed to the sheet (placed per D7) under viewports, text and title block; it cannot be selected or dragged.
- [x] AC2 .docx (through Word) and .pdf (direct) both link.
- [x] AC3 One page per sheet; linking a multi-page file offers sheets for the other pages.
- [x] AC4 Fit scale by default (11x17 on ANSI D = 2x, on ANSI B = 1x, centred), with Fit / 1x / 2x / custom in properties.
- [x] AC5 The page is clipped at the drawing area; an overlap shows the N mm warning.
- [x] AC6 Saving the file while the project is open refreshes the sheet automatically (the file can stay open in Word); a changed file is picked up on project open; Refresh forces it; a status message reports each refresh.
- [x] AC7 Missing file, no Word, or page gone: the saved copy shows and exports, with a badge naming the cause and date; Relink works.
- [x] AC8 A file that grew prompts once to create sheets for the new pages.
- [x] AC9 The path is stored like underlays (relative inside the project tree, absolute otherwise).
- [x] AC10 Exported PDF: the page is vector with selectable text, at the right size and position (D1).
- [x] AC11 Badges and warnings never print or export.
- [x] AC12 Open in Word; link / unlink / page / scale are undoable; a refresh is not an undo step.
- [x] AC13 The app stays usable during a conversion.
- [x] AC14 Printing draws the page as a picture at the printer's resolution (D1b).
- [x] AC15 The saved copy is inside the .fpd and survives save -> load with the source file deleted (D2).

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
- `underlay_controller.import_pdf`: the fitz -> `QImage` raster block (extract into a shared page-raster helper, GENERALIZE). Done: `pdf_raster.pdf_page_to_qimage`, which `import_pdf` now calls.
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

- Snapshot render is cached per (snapshot, dpi), which is per (sheet, page) in effect; zoom re-renders only when the needed dpi grows past the cache by more than 1.5x, capped at 300 dpi on screen (values and cache size: D1b, `constants.py`).
- Only the user's own files are opened; the PowerShell script is a fixed string with the file paths passed as arguments, never interpolated into script text.

## Follow-ups (filed at Phase 2)

- "New sheets from document..." in the sheet list.
- Export refreshes changed linked files before exporting.

Known gaps filed at the build (2026-11-10, `todo_open.md` "Paper-space sheet output"): a link restored
by undo/redo is not re-compared with the file, and `LinkedDocService.refreshed` has no consumer, so
the panel and badge can go stale after an auto-refresh or a file deleted while open; Word or temp
copies left behind on timeout / cancel; long badge text, the GUI-thread file check and the shared
raster cache; the per-task review Minors.
