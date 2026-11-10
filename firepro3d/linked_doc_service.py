"""linked_doc_service.py
========================
Refresh service for sheet-linked documents
(docs/superpowers/specs/2026-11-09-sheet-linked-document-design.md D3-D5, D10, D11).

One ``LinkedDocService`` per main window. It watches every linked file's
folder (``LinkedDocWatcher``), converts .docx through Word on a worker thread
(``doc_converter.ConvertWorker``: one conversion per file at a time, one queued
follow-up), and writes each new copy into every sheet linking that file. A
refresh is not an undo step (D5): it rewrites the snapshot fields directly,
emits the live ``PaperScene.sheetModified`` (the project is dirtied) and
reports on the status bar.

The dialogs are module functions (``choose_linked_file``, ``pick_linked_page``,
``ask_create_pages``, ``ask_custom_scale``) so tests replace them with
``monkeypatch``; the service always calls them through module globals.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QObject, pyqtSignal

from . import doc_converter
from . import linked_document as ld_mod
from .constants import LINKED_DOC_DEBOUNCE_MS
from .linked_doc_watcher import LinkedDocWatcher
from .paper_commands import SetLinkedDocumentCommand


def _key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


# -- Dialogs (module functions: tests monkeypatch these) ----------------------

def choose_linked_file(parent=None, start_dir: str = "") -> str:
    """Ask for a .docx or .pdf to link; "" on cancel."""
    from PyQt6.QtWidgets import QFileDialog
    path, _ = QFileDialog.getOpenFileName(
        parent, "Link Document", start_dir,
        "Documents (*.docx *.pdf);;Word documents (*.docx);;PDF files (*.pdf)")
    return path


def pick_linked_page(parent, file_name: str, n_pages: int):
    """Page picker for a multi-page file (D11).

    Returns:
        ``(page, create_other_sheets)`` or None on cancel.
    """
    from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QPushButton
    from .themed_message import ThemedMessageDialog
    dlg = ThemedMessageDialog(
        "Link Document",
        f"{file_name} has {n_pages} pages. Which page goes on this sheet?",
        parent=parent)
    combo = QComboBox()
    combo.addItems([f"Page {i}" for i in range(1, n_pages + 1)])
    dlg._add_input_widget("Page", combo)
    others = QCheckBox("Create sheets for the other pages")
    dlg.body_layout().addWidget(others)
    dlg._clear_footer()
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(dlg.reject)
    dlg.set_footer_buttons(primary=("Link", dlg.accept), cancel=False,
                           extra_left=cancel)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    return combo.currentIndex() + 1, others.isChecked()


def ask_create_pages(file_name: str, n_pages: int, n_on_sheets: int,
                     missing) -> bool:
    """The one-time growth prompt (D10 / Q10 wording)."""
    from .themed_message import themed_confirm
    pages = ", ".join(str(p) for p in missing)
    what = (f"a sheet for page {pages}" if len(missing) == 1
            else f"sheets for pages {pages}")
    return themed_confirm(
        None, "Linked Document Has New Pages",
        f"{file_name} now has {n_pages} pages; {n_on_sheets} are on sheets.\n"
        f"Create {what}?",
        ok_label="Create", cancel_label="Not now")


def ask_custom_scale(parent, initial: float) -> "float | None":
    """Ask for a custom page scale factor; None on cancel."""
    from .themed_message import themed_input_number
    value, ok = themed_input_number(
        parent, "Custom Page Scale", "Scale factor (for example 1.5):",
        initial=float(initial), dimension=False, minimum=0.1, maximum=10.0)
    return value if ok else None


class LinkedDocService(QObject):
    """Refresh + link flows for every sheet-linked document of one project.

    Args:
        sheets_getter: Returns the project's live sheet list.
        scene_getter: Returns the live PaperScene (or None).
        manager_getter: Returns the SheetManager (for creating sheets).
        notify: ``notify(message, timeout_ms)`` status-bar callback.
        on_sheets_added: Called after sheets were created (browser refresh).
        convert_fn: .docx -> PDF bytes (default Word through PowerShell).
        word_available_fn: Word check (default ``doc_converter.word_available``).
        debounce_ms: Folder-watch debounce.
        parent: Owning QObject.
    """

    refreshed = pyqtSignal(str)

    def __init__(self, *, sheets_getter, scene_getter, manager_getter=None,
                 notify=None, on_sheets_added=None, convert_fn=None,
                 word_available_fn=None,
                 debounce_ms: int = LINKED_DOC_DEBOUNCE_MS, parent=None):
        super().__init__(parent)
        self._sheets_getter = sheets_getter
        self._scene_getter = scene_getter
        self._manager_getter = manager_getter or (lambda: None)
        self._notify_fn = notify or (lambda message, timeout_ms=6000: None)
        self._on_sheets_added = on_sheets_added or (lambda: None)
        self._convert_fn = convert_fn
        self._word_available_fn = word_available_fn
        self.watcher = LinkedDocWatcher(self, debounce_ms=debounce_ms)
        self.watcher.changed.connect(self._on_file_changed)
        self._closed = False            # set by shutdown(): drop late signals
        self._workers: dict = {}        # file key -> running ConvertWorker
        self._paths: dict = {}          # file key -> path as requested
        self._started_stat: dict = {}   # file key -> (mtime, size) at start
        self._queued: set = set()       # file keys with one follow-up queued
        self._pdf_cache: dict = {}      # file key -> (mtime, size, pdf bytes)
        self._pending: dict = {}        # file key -> [(on_ready, on_error)]

    # -- bookkeeping ---------------------------------------------------------

    def _notify(self, message: str, timeout_ms: int = 6000) -> None:
        try:
            self._notify_fn(message, timeout_ms)
        except RuntimeError:            # status bar deleted under teardown
            pass

    def _word_ok(self) -> bool:
        fn = self._word_available_fn or doc_converter.word_available
        return bool(fn())

    def linked_sheets(self, path: str) -> list:
        """Every sheet linking *path* (any page)."""
        k = _key(path)
        return [s for s in self._sheets_getter()
                if s.linked_document is not None
                and _key(s.linked_document.path) == k]

    def converting(self, path: str) -> bool:
        """True while a conversion of *path* runs."""
        return _key(path) in self._workers

    def rebind(self, *_args) -> None:
        """Re-point the watcher at the linked files of the current sheets."""
        baselines = {}
        for s in self._sheets_getter():
            ld = s.linked_document
            if ld is not None and ld.path:
                baselines.setdefault(ld.path, (ld.source_mtime, ld.source_size))
        self.watcher.set_files(baselines)

    def check_all_on_open(self) -> None:
        """The (mtime, size) compare for every linked file, once (D4, Q5)."""
        self.rebind()
        seen = set()
        for s in list(self._sheets_getter()):
            ld = s.linked_document
            if ld is None or _key(ld.path) in seen:
                continue
            seen.add(_key(ld.path))
            try:
                st = os.stat(ld.path)
            except OSError:
                continue                # missing: the badge says so
            if (st.st_mtime, st.st_size) != (ld.source_mtime, ld.source_size):
                self.request_refresh(ld.path)

    def shutdown(self) -> None:
        """Stop watching; drop running conversions (window close).

        Ratified 2026-11-09 ("Close now, drop update"): the sheet keeps the copy
        it had. Each worker is silenced (its signals disconnected, so a result
        or error that arrives late reaches nothing), cancelled (stops waiting
        within ~0.25 s) and joined, so no QThread is destroyed while running.
        The PowerShell child is NOT killed: it finishes or times out on its own
        and quits only the Word instance it started.
        """
        self._closed = True
        self._queued.clear()
        self._pending.clear()
        workers = list(self._workers.values())
        for worker in workers:
            for signal, slot in ((worker.converted, self._on_converted),
                                 (worker.failed, self._on_failed),
                                 (worker.finished, self._on_worker_finished)):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            worker.cancel()
        for worker in workers:
            worker.wait(2000)
        self._workers.clear()
        self.watcher.set_files({})

    # -- refresh -------------------------------------------------------------

    def _on_file_changed(self, path: str) -> None:
        self.request_refresh(path)

    def request_refresh(self, path: str) -> None:
        """Refresh every sheet linking *path* from the file now (D4, D5).

        A .pdf is read at once; a .docx converts on a worker thread and the
        sheets keep their copy until the new one is ready (D3).
        """
        if self._closed or not self.linked_sheets(path):
            return
        name = os.path.basename(path)
        if not os.path.isfile(path):
            self._redraw(path)
            self._notify(f"Cannot update {name}: the file was not found")
            return
        if ld_mod.is_pdf(path):
            st = os.stat(path)
            with open(path, "rb") as fh:
                data = fh.read()
            self._apply(path, data, st.st_mtime, st.st_size)
            return
        if not self._word_ok():
            self._redraw(path)
            self._notify(f"Word not available - cannot update {name}")
            return
        self._start_conversion(path)

    def _start_conversion(self, path: str) -> None:
        k = _key(path)
        if k in self._workers:
            self._queued.add(k)         # one follow-up, never two at once
            return
        try:
            st = os.stat(path)
        except OSError as exc:
            self._fail(path, str(exc))
            return
        self._paths[k] = path
        self._started_stat[k] = (st.st_mtime, st.st_size)
        worker = doc_converter.ConvertWorker(path, self._convert_fn, parent=self)
        worker.converted.connect(self._on_converted)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._workers[k] = worker
        self._notify(f"Updating {os.path.basename(path)}\u2026", 0)
        worker.start()

    def _on_converted(self, path: str, pdf_bytes) -> None:
        if self._closed:
            return
        k = _key(path)
        mtime, size = self._started_stat.get(k, (0.0, 0))
        self._pdf_cache[k] = (mtime, size, pdf_bytes)
        self._apply(path, pdf_bytes, mtime, size)
        for on_ready, _on_error in self._pending.pop(k, []):
            on_ready(pdf_bytes, mtime, size)

    def _on_failed(self, path: str, reason: str) -> None:
        if self._closed:
            return
        self._fail(path, reason)

    def _fail(self, path: str, reason: str) -> None:
        for s in self.linked_sheets(path):
            s.linked_document.last_error = reason
        self._redraw(path)
        self._notify(f"Could not update from {os.path.basename(path)}: {reason}")
        for _on_ready, on_error in self._pending.pop(_key(path), []):
            on_error(reason)

    def _on_worker_finished(self) -> None:
        if self._closed:
            return
        for k, worker in list(self._workers.items()):
            if not worker.isFinished():
                continue
            worker.wait()
            del self._workers[k]
            worker.deleteLater()
            if k in self._queued:
                self._queued.discard(k)
                self._start_conversion(self._paths[k])

    def _apply(self, path: str, pdf_bytes: bytes, mtime: float, size: int) -> None:
        sheets = self.linked_sheets(path)
        if not sheets:
            return
        gone = []
        try:
            for s in sheets:
                outcome = ld_mod.refresh_from_pdf(s.linked_document, pdf_bytes,
                                                  mtime, size)
                if outcome == ld_mod.REFRESH_PAGE_GONE:
                    gone.append(s.linked_document.page)
        except ld_mod.SnapshotError as exc:
            self._fail(path, str(exc))
            return
        self.watcher.set_baseline(path, mtime, size)
        self._redraw(path)
        scene = self._scene_getter()
        if scene is not None:
            scene.sheetModified.emit()          # D5: dirty, not an undo step
        name = os.path.basename(path)
        if gone:
            pages = ", ".join(str(p) for p in sorted(set(gone)))
            self._notify(f"Updated {name}; page {pages} is no longer in the "
                         "file - keeping the saved copy")
        else:
            self._notify(f"Updated {name} on {len(sheets)} sheet(s)")
        self.refreshed.emit(path)
        self._offer_new_pages(path, sheets, pdf_bytes, mtime, size)

    def _redraw(self, path: str) -> None:
        scene = self._scene_getter()
        if scene is None:
            return
        ld = scene.sheet.linked_document
        if ld is not None and _key(ld.path) == _key(path):
            scene.refresh_linked_page()

    def _offer_new_pages(self, path, sheets, pdf_bytes, mtime, size) -> None:
        """D10: once per growth, offer sheets for the pages on no sheet."""
        n = max(s.linked_document.source_pages for s in sheets)
        offered = max(s.linked_document.offered_pages for s in sheets)
        if n <= offered:
            return
        for s in sheets:
            s.linked_document.offered_pages = n      # either answer records it
        on_sheets = {s.linked_document.page for s in sheets} & set(range(1, n + 1))
        missing = [p for p in range(1, n + 1) if p not in on_sheets]
        if missing and ask_create_pages(os.path.basename(path), n,
                                        len(on_sheets), missing):
            self.create_sheets_for_pages(path, missing, pdf_bytes, mtime, size,
                                         like=sheets[0].linked_document)

    def create_sheets_for_pages(self, path, pages, pdf_bytes, mtime, size,
                                *, like=None) -> list:
        """New sheets (``SheetManager.create``) each linking one page.

        Sheet-level operation, not undoable (paper-space spec section 19.1).
        """
        mgr = self._manager_getter()
        if mgr is None or not pages:
            return []
        stem = os.path.splitext(os.path.basename(path))[0]
        made = []
        for p in pages:
            sheet = mgr.create()
            sheet.name = f"{stem} - Page {p}"
            sheet.linked_document = ld_mod.new_link(
                path, pdf_bytes, p, mtime, size,
                scale_mode=like.scale_mode if like else "fit",
                scale_custom=like.scale_custom if like else 1.0)
            made.append(sheet)
        self.rebind()
        self._on_sheets_added()
        self._notify(f"Created {len(made)} sheet(s) for {os.path.basename(path)}")
        return made

    # -- link flows (D11) ----------------------------------------------------

    def acquire(self, path: str, on_ready, on_error) -> None:
        """Deliver *path*'s PDF bytes to ``on_ready(pdf_bytes, mtime, size)``.

        A .pdf is read now; a .docx is converted (or taken from the last
        conversion of the same (mtime, size)) and delivered later.
        """
        if not os.path.isfile(path):
            on_error("the file was not found")
            return
        st = os.stat(path)
        if ld_mod.is_pdf(path):
            with open(path, "rb") as fh:
                data = fh.read()
            on_ready(data, st.st_mtime, st.st_size)
            return
        if not ld_mod.is_docx(path):
            on_error("only .docx and .pdf files can be linked")
            return
        k = _key(path)
        cached = self._pdf_cache.get(k)
        if cached is not None and cached[:2] == (st.st_mtime, st.st_size):
            on_ready(cached[2], cached[0], cached[1])
            return
        if not self._word_ok():
            on_error("Word is not available")
            return
        self._pending.setdefault(k, []).append((on_ready, on_error))
        self._start_conversion(path)

    def link_interactive(self, scene, sheet, *, relink: bool = False,
                         on_done=None, parent=None) -> None:
        """Link... / Relink...: file dialog, convert, page picker, command (D11)."""
        old = sheet.linked_document
        start = os.path.dirname(old.path) if old is not None else ""
        path = choose_linked_file(parent, start)
        if not path:
            return
        path = os.path.abspath(path)
        name = os.path.basename(path)

        def ready(pdf_bytes, mtime, size):
            try:
                n = ld_mod.page_count(pdf_bytes)
            except ld_mod.SnapshotError as exc:
                self._notify(f"Could not link {name}: {exc}")
                return
            create_others = False
            if relink and old is not None:
                page = min(old.page, n)
            elif n > 1:
                choice = pick_linked_page(parent, name, n)
                if choice is None:
                    return
                page, create_others = choice
            else:
                page = 1
            data = ld_mod.new_link(
                path, pdf_bytes, page, mtime, size,
                scale_mode=old.scale_mode if old is not None else "fit",
                scale_custom=old.scale_custom if old is not None else 1.0)
            scene.undo_stack.push(SetLinkedDocumentCommand(
                scene, sheet, data, "Relink Document" if relink else "Link Document"))
            if create_others:
                self.create_sheets_for_pages(
                    path, [p for p in range(1, n + 1) if p != page],
                    pdf_bytes, mtime, size, like=data)
            self.rebind()
            self._notify(f"Linked {name}, page {page}")
            if on_done is not None:
                on_done()

        self.acquire(path, ready,
                     lambda reason: self._notify(f"Could not link {name}: {reason}"))

    def change_page(self, scene, sheet, page: int, on_done=None) -> None:
        """Page row: take the new page's copy, then one undoable command (D6)."""
        ld = sheet.linked_document
        if ld is None:
            return
        name = os.path.basename(ld.path)

        def ready(pdf_bytes, mtime, size):
            try:
                new = ld_mod.new_link(ld.path, pdf_bytes, page, mtime, size,
                                      scale_mode=ld.scale_mode,
                                      scale_custom=ld.scale_custom)
            except ld_mod.SnapshotError:
                self._notify(f"Page {page} is not in {name}")
                return
            new.offered_pages = ld.offered_pages
            scene.undo_stack.push(SetLinkedDocumentCommand(
                scene, sheet, new, "Change Linked Page"))
            if on_done is not None:
                on_done()

        self.acquire(ld.path, ready,
                     lambda reason: self._notify(f"Cannot change the page: {reason}"))
