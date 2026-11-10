"""linked_document.py
=====================
Sheet-linked document data + pure helpers
(docs/superpowers/specs/2026-11-09-sheet-linked-document-design.md).

A sheet may show one page of a linked Word or PDF file. ``LinkedDocData`` is the
persisted link: the path, the page, the scale setting and a one-page PDF snapshot
(base64) that is the render source for screen, print and export (D2). Everything
here is pure: PyMuPDF on PDF bytes, ``QRectF`` / ``QImage`` values, no widgets
and no scene.
"""
from __future__ import annotations

import base64
import binascii
import datetime
import functools
import os
from dataclasses import dataclass, field

import fitz
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage

from .constants import (
    LINKED_PAGE_DPI_STEP, LINKED_PAGE_MIN_DPI, LINKED_PAGE_PRINT_MAX_DPI,
    LINKED_PAGE_SCREEN_MAX_DPI, PDF_PT_PER_MM,
)
from .pdf_raster import pdf_page_to_qimage

SCALE_MODES = ("fit", "1", "2", "custom")
REFRESH_UPDATED = "updated"
REFRESH_PAGE_GONE = "page_gone"


class SnapshotError(ValueError):
    """A snapshot or source PDF could not be read, or lacks the page."""


@dataclass
class LinkedDocData:
    """One sheet's link to a page of a Word or PDF file (design Data model).

    ``path`` is absolute in memory; the project file stores it relative to the
    project folder when it sits in the same tree (``relativize_sheet_links``),
    like underlays (Q11). ``last_error`` is runtime only and never saved.
    """

    path: str
    page: int = 1
    scale_mode: str = "fit"
    scale_custom: float = 1.0
    snapshot_pdf: str = ""
    snapshot_at: str = ""
    source_mtime: float = 0.0
    source_size: int = 0
    source_pages: int = 0
    offered_pages: int = 0
    last_error: str = field(default="", compare=False, repr=False)

    def to_dict(self) -> dict:
        """The persisted fields (``last_error`` is left out)."""
        return {
            "path": self.path,
            "page": self.page,
            "scale_mode": self.scale_mode,
            "scale_custom": self.scale_custom,
            "snapshot_pdf": self.snapshot_pdf,
            "snapshot_at": self.snapshot_at,
            "source_mtime": self.source_mtime,
            "source_size": self.source_size,
            "source_pages": self.source_pages,
            "offered_pages": self.offered_pages,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LinkedDocData":
        """Read a saved link; every key is optional (old files, hand edits)."""
        mode = str(d.get("scale_mode", "fit"))
        return cls(
            path=str(d.get("path", "")),
            page=max(1, int(d.get("page", 1))),
            scale_mode=mode if mode in SCALE_MODES else "fit",
            scale_custom=float(d.get("scale_custom", 1.0)),
            snapshot_pdf=str(d.get("snapshot_pdf", "")),
            snapshot_at=str(d.get("snapshot_at", "")),
            source_mtime=float(d.get("source_mtime", 0.0)),
            source_size=int(d.get("source_size", 0)),
            source_pages=int(d.get("source_pages", 0)),
            offered_pages=int(d.get("offered_pages", 0)),
        )


# -- File kinds ----------------------------------------------------------------

def is_docx(path: str) -> bool:
    """True for a Word document (converted through Word, D3)."""
    return path.lower().endswith(".docx")


def is_pdf(path: str) -> bool:
    """True for a PDF (read directly, never needs Word)."""
    return path.lower().endswith(".pdf")


def open_source(path: str) -> bool:
    """Open *path* in its default app (Word for .docx, the PDF viewer for .pdf).

    Returns:
        False when the file does not exist (nothing is opened), else True.
    """
    if not os.path.isfile(path):
        return False
    os.startfile(path)  # noqa: S606 -- the user's own linked file (D12)
    return True


# -- PDF bytes and snapshots -----------------------------------------------------

def open_pdf_bytes(data: bytes) -> "fitz.Document":
    """Open PDF *data*; raise ``SnapshotError`` when it is not a readable PDF."""
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 -- PyMuPDF raises several types
        raise SnapshotError(f"not a readable PDF ({exc})") from exc
    if len(doc) < 1:
        doc.close()
        raise SnapshotError("the PDF has no pages")
    return doc


def open_snapshot(snapshot_b64: str) -> "fitz.Document":
    """Open a base64 one-page snapshot; raise ``SnapshotError`` if damaged."""
    if not snapshot_b64:
        raise SnapshotError("no saved copy")
    try:
        raw = base64.b64decode(snapshot_b64.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise SnapshotError(f"the saved copy is damaged ({exc})") from exc
    return open_pdf_bytes(raw)


def page_count(pdf_bytes: bytes) -> int:
    """Number of pages in PDF *pdf_bytes*."""
    doc = open_pdf_bytes(pdf_bytes)
    try:
        return len(doc)
    finally:
        doc.close()


def snapshot_page(doc: "fitz.Document", page: int) -> str:
    """Base64 of a one-page PDF holding 1-based *page* of *doc* (D2)."""
    out = fitz.open()
    try:
        out.insert_pdf(doc, from_page=page - 1, to_page=page - 1)
        return base64.b64encode(
            out.tobytes(garbage=3, deflate=True)).decode("ascii")
    finally:
        out.close()


def refresh_from_pdf(data: LinkedDocData, pdf_bytes: bytes, mtime: float,
                     size: int, now: "datetime.datetime | None" = None) -> str:
    """Take a new copy of ``data.page`` from *pdf_bytes* (design D5, D10).

    The source stat and page count always update. When the page no longer
    exists the old snapshot is kept (the badge names the page).

    Returns:
        ``REFRESH_UPDATED`` or ``REFRESH_PAGE_GONE``.

    Raises:
        SnapshotError: *pdf_bytes* is not a readable PDF.
    """
    doc = open_pdf_bytes(pdf_bytes)
    try:
        n = len(doc)
        data.source_mtime = float(mtime)
        data.source_size = int(size)
        data.source_pages = n
        data.last_error = ""
        if data.page > n:
            return REFRESH_PAGE_GONE
        data.snapshot_pdf = snapshot_page(doc, data.page)
        data.snapshot_at = (now or datetime.datetime.now()).isoformat(
            timespec="seconds")
        return REFRESH_UPDATED
    finally:
        doc.close()


def new_link(path: str, pdf_bytes: bytes, page: int, mtime: float, size: int,
             *, scale_mode: str = "fit", scale_custom: float = 1.0,
             now: "datetime.datetime | None" = None) -> LinkedDocData:
    """A fresh link to *page* of *path* with its snapshot taken (D11).

    ``offered_pages`` starts at the page count: linking already offered the
    other pages (the page picker), so only later growth prompts (D10).

    Raises:
        SnapshotError: unreadable bytes, or *page* is not in the file.
    """
    data = LinkedDocData(path=os.path.abspath(path), page=page,
                         scale_mode=scale_mode, scale_custom=scale_custom)
    if refresh_from_pdf(data, pdf_bytes, mtime, size, now) != REFRESH_UPDATED:
        raise SnapshotError(f"page {page} is not in {os.path.basename(path)}")
    data.offered_pages = data.source_pages
    return data


# -- Page geometry (D7, D8) --------------------------------------------------------

@dataclass(frozen=True)
class PageInfo:
    """Snapshot page size and content bounds, PDF points (top-left origin)."""

    width_pt: float
    height_pt: float
    bounds_pt: "tuple[float, float, float, float] | None"


@functools.lru_cache(maxsize=32)
def page_info(snapshot_b64: str) -> PageInfo:
    """Size + content bounds (text blocks and drawings, D8) of a snapshot."""
    doc = open_snapshot(snapshot_b64)
    try:
        page = doc[0]
        rects = [tuple(b[:4]) for b in page.get_text("blocks")]
        rects += [tuple(d["rect"]) for d in page.get_drawings()]
        bounds = None
        if rects:
            bounds = (min(r[0] for r in rects), min(r[1] for r in rects),
                      max(r[2] for r in rects), max(r[3] for r in rects))
        return PageInfo(page.rect.width, page.rect.height, bounds)
    finally:
        doc.close()


def page_size_mm(snapshot_b64: str) -> "tuple[float, float]":
    """Snapshot page size in mm (points -> mm, D7)."""
    info = page_info(snapshot_b64)
    return info.width_pt / PDF_PT_PER_MM, info.height_pt / PDF_PT_PER_MM


def effective_scale(data: LinkedDocData, sheet_w: float, sheet_h: float,
                    page_w: float, page_h: float) -> float:
    """The scale a mode means on this sheet (D7: fit = the tighter side)."""
    if data.scale_mode == "1":
        return 1.0
    if data.scale_mode == "2":
        return 2.0
    if data.scale_mode == "custom":
        return data.scale_custom if data.scale_custom > 0 else 1.0
    return min(sheet_w / page_w, sheet_h / page_h)


@dataclass(frozen=True, eq=False)
class Placement:
    """Where the page lands on the sheet (paper mm) and at what scale."""

    rect: QRectF
    scale: float


def placement(data: LinkedDocData, sheet_w: float, sheet_h: float) -> Placement:
    """Centred page rect at the mode's scale (D7)."""
    pw, ph = page_size_mm(data.snapshot_pdf)
    s = effective_scale(data, sheet_w, sheet_h, pw, ph)
    w, h = pw * s, ph * s
    return Placement(QRectF((sheet_w - w) / 2.0, (sheet_h - h) / 2.0, w, h), s)


def content_bounds_mm(data: LinkedDocData, sheet_w: float,
                      sheet_h: float) -> "QRectF | None":
    """The page's content bounds mapped onto the sheet (D8), or None if blank."""
    info = page_info(data.snapshot_pdf)
    if info.bounds_pt is None:
        return None
    geo = placement(data, sheet_w, sheet_h)
    k = geo.scale / PDF_PT_PER_MM
    x0, y0, x1, y1 = info.bounds_pt
    return QRectF(geo.rect.left() + x0 * k, geo.rect.top() + y0 * k,
                  (x1 - x0) * k, (y1 - y0) * k)


def overlap_mm(bounds: "QRectF | None", area: QRectF) -> float:
    """Largest overrun of *bounds* past *area* on any side, mm (0 if inside)."""
    if bounds is None:
        return 0.0
    return max(0.0, area.left() - bounds.left(), bounds.right() - area.right(),
               area.top() - bounds.top(), bounds.bottom() - area.bottom())


# -- Export (D1) -------------------------------------------------------------------

@dataclass(frozen=True)
class ExportGeometry:
    """One sheet's linked page for the export post-pass, PDF points."""

    snapshot_pdf: str
    dest_pt: "tuple[float, float, float, float]"   # on the sheet page
    clip_pt: "tuple[float, float, float, float]"   # on the snapshot page


def export_geometry(data: LinkedDocData, sheet_w: float, sheet_h: float,
                    area: QRectF) -> "ExportGeometry | None":
    """Destination (clipped to *area*) and the matching source clip (D1).

    Destination and clip are the same region in two spaces, so
    ``show_pdf_page`` maps it at exactly the placement scale.
    """
    if not data.snapshot_pdf:
        return None
    try:
        geo = placement(data, sheet_w, sheet_h)
    except SnapshotError:
        return None
    dest = geo.rect.intersected(area)
    if dest.isEmpty():
        return None
    k = PDF_PT_PER_MM / geo.scale
    clip = ((dest.left() - geo.rect.left()) * k,
            (dest.top() - geo.rect.top()) * k,
            (dest.right() - geo.rect.left()) * k,
            (dest.bottom() - geo.rect.top()) * k)
    p = PDF_PT_PER_MM
    return ExportGeometry(
        data.snapshot_pdf,
        (dest.left() * p, dest.top() * p, dest.right() * p, dest.bottom() * p),
        clip)


def place_pages_under(pdf_path: str, placements) -> None:
    """Put each linked page UNDER its sheet page in an exported PDF (D1).

    Args:
        pdf_path: The PDF ``export_pdf`` just wrote (painter already ended).
        placements: ``[(page_index, ExportGeometry), ...]``.

    Raises:
        OSError: the post-pass failed (the file is left as the plain export).
    """
    tmp = pdf_path + ".linked.tmp"
    try:
        doc = fitz.open(pdf_path)
        try:
            for index, geo in placements:
                src = open_snapshot(geo.snapshot_pdf)
                try:
                    doc[index].show_pdf_page(
                        fitz.Rect(*geo.dest_pt), src, 0,
                        clip=fitz.Rect(*geo.clip_pt), overlay=False)
                finally:
                    src.close()
            doc.save(tmp, garbage=3, deflate=True)
        finally:
            doc.close()
        os.replace(tmp, pdf_path)
    except (RuntimeError, ValueError) as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise OSError(f"Could not place the linked document page: {exc}") from exc


# -- Raster for screen and print (D1b) ---------------------------------------------

def raster_dpi(needed_dpi: float, *, screen: bool) -> float:
    """The raster dpi to use for a page that needs *needed_dpi*.

    Screen: a 1.5x ladder from ``LINKED_PAGE_MIN_DPI`` capped at
    ``LINKED_PAGE_SCREEN_MAX_DPI`` (re-render only past 1.5x growth).
    Print: the device's need, capped at ``LINKED_PAGE_PRINT_MAX_DPI``.
    """
    if screen:
        dpi = LINKED_PAGE_MIN_DPI
        while dpi < needed_dpi and dpi < LINKED_PAGE_SCREEN_MAX_DPI:
            dpi *= LINKED_PAGE_DPI_STEP
        return min(dpi, LINKED_PAGE_SCREEN_MAX_DPI)
    return max(LINKED_PAGE_MIN_DPI, min(needed_dpi, LINKED_PAGE_PRINT_MAX_DPI))


@functools.lru_cache(maxsize=8)
def render_snapshot(snapshot_b64: str, dpi: float) -> "QImage | None":
    """Raster of a snapshot at *dpi*, cached per (snapshot, dpi); None if damaged."""
    try:
        doc = open_snapshot(snapshot_b64)
    except SnapshotError:
        return None
    try:
        return pdf_page_to_qimage(doc[0], dpi)
    finally:
        doc.close()


# -- Badge (D9) ------------------------------------------------------------------------

def _when(iso: str) -> str:
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return "an earlier save"


def badge_text(data: LinkedDocData, *, sheet_w: float, sheet_h: float,
               area: QRectF, file_exists: bool, word_ok: bool) -> str:
    """The one screen-only badge line, by priority (D9, D3, D10, Edge Cases).

    Missing file > page gone > Word not available > conversion error >
    overlap > scale note. Empty when there is nothing to say.
    """
    name = os.path.basename(data.path)
    when = _when(data.snapshot_at)
    if not file_exists:
        return f"Linked file missing - showing copy from {when}"
    if data.source_pages and data.page > data.source_pages:
        return f"Page {data.page} is no longer in {name}"
    if is_docx(data.path) and not word_ok:
        return f"Word not available - showing copy from {when}"
    if data.last_error:
        return f"Could not update from {name}: {data.last_error}"
    try:
        over = overlap_mm(content_bounds_mm(data, sheet_w, sheet_h), area)
        scale = placement(data, sheet_w, sheet_h).scale
    except SnapshotError:
        return f"The saved copy of {name} cannot be read"
    if over >= 0.5:
        return f"Page content overlaps the title block by {over:.0f} mm"
    if abs(scale - 1.0) > 1e-6:
        return f"Page shown at {scale:g}x"
    return ""


# -- Paths (Q11: stored like underlays) ------------------------------------------

def stored_path(abs_path: str, project_dir: str) -> str:
    """The path as the project file stores it (``Underlay.relativize_path``)."""
    from .underlay import Underlay
    return Underlay.relativize_path(os.path.abspath(abs_path), project_dir)


def loaded_path(stored: str, project_dir: str) -> str:
    """The absolute in-memory path for a stored one, found or not."""
    from .underlay import Underlay
    resolved = Underlay.resolve_path(stored, project_dir)
    if resolved is not None:
        return os.path.abspath(resolved)
    if not os.path.isabs(stored):
        return os.path.normpath(os.path.join(project_dir, stored))
    return stored


def relativize_sheet_links(sheet_dicts: "list[dict]", project_dir: str) -> "list[dict]":
    """Rewrite each saved sheet's linked path for the project file (in place)."""
    for d in sheet_dicts:
        ld = d.get("linked_document")
        if ld and ld.get("path"):
            ld["path"] = stored_path(ld["path"], project_dir)
    return sheet_dicts


def resolve_sheet_links(sheets, project_dir: str) -> None:
    """Make every loaded sheet's linked path absolute again."""
    for s in sheets:
        ld = getattr(s, "linked_document", None)
        if ld is not None and ld.path:
            ld.path = loaded_path(ld.path, project_dir)
