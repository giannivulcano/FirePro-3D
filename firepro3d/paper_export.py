"""
paper_export.py
===============
Vector PDF export and system-dialog printing for paper-space sheets.

Each :class:`~firepro3d.paper_space.Sheet` is rendered by building a transient
off-screen :class:`~firepro3d.paper_space.PaperScene` from the sheet data plus
the shared :class:`~firepro3d.paper_space.ViewResolver`, then rendering its
paper rectangle ``(0, 0, w_mm, h_mm)`` onto a ``QPainter`` attached to a
``QPdfWriter`` (PDF) or ``QPrinter`` (print). The transient scene is disposed
after each render so it never leaks ``changed`` connections into the live
model/elevation scenes.

Reusing ``PaperScene`` guarantees the on-screen composition (title block +
``SheetViewport`` B&W / line-weight overrides) is reproduced verbatim in
output — there is no second, drift-prone render path.

The public functions accept ``list[Sheet]`` so batch / multi-page export is a
thin extension once multi-sheet management ships; today the only reachable
callers pass a single sheet.
"""
from __future__ import annotations

import os
import re

from PyQt6.QtCore import QRectF, QSizeF, QMarginsF
from PyQt6.QtGui import QPainter, QPdfWriter, QPageSize, QPageLayout

from .paper_space import Sheet, PaperScene, PAPER_SIZES, ViewResolver

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def default_pdf_filename(sheet: Sheet) -> str:
    """Return a safe default PDF filename for *sheet* (``"{number} - {name}.pdf"``)."""
    base = f"{sheet.number} - {sheet.name}".strip(" -")
    safe = _INVALID_FILENAME_CHARS.sub("_", base).strip()
    if not safe:
        safe = "sheet"
    return f"{safe}.pdf"


def _set_page(device, sheet: Sheet) -> None:
    """Configure *device* (QPdfWriter/QPrinter) for *sheet*'s paper size, no margins."""
    w_mm, h_mm = PAPER_SIZES[sheet.paper_size]
    device.setPageSize(QPageSize(QSizeF(w_mm, h_mm), QPageSize.Unit.Millimeter))
    device.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)


def render_sheet(sheet: Sheet, resolver: ViewResolver,
                 painter: QPainter, target_rect: QRectF) -> None:
    """Render one *sheet* into *target_rect* (device px) of *painter*.

    Builds a transient PaperScene, renders the paper rectangle (0,0,w,h in mm)
    into ``target_rect``, then disposes the scene.
    """
    w_mm, h_mm = PAPER_SIZES[sheet.paper_size]
    scene = PaperScene(sheet, resolver)
    try:
        scene.render(painter, target_rect, QRectF(0, 0, w_mm, h_mm))
    finally:
        scene.dispose()


def export_pdf(sheets: "list[Sheet]", resolver: ViewResolver,
               path: str, dpi: int = 300) -> None:
    """Export *sheets* to a single multi-page vector PDF at *path*.

    Args:
        sheets: One or more sheets (one PDF page each). Must be non-empty.
        resolver: Shared ViewResolver bridging viewports to source scenes.
        path: Output PDF file path.
        dpi: Render resolution (affects raster title-block crispness + file size).

    Raises:
        ValueError: If *sheets* is empty.
        OSError: If *path* cannot be written (no partial file is produced).
    """
    if not sheets:
        raise ValueError("export_pdf requires at least one sheet")

    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        raise OSError(f"Output directory does not exist: {parent!r}")

    writer = QPdfWriter(path)
    writer.setResolution(dpi)

    painter: QPainter | None = None
    try:
        for sheet in sheets:
            _set_page(writer, sheet)
            if painter is None:
                painter = QPainter(writer)
                if not painter.isActive():
                    raise OSError(f"Cannot write PDF to {path!r}")
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            else:
                writer.newPage()
            render_sheet(sheet, resolver, painter, QRectF(painter.viewport()))
    finally:
        if painter is not None and painter.isActive():
            painter.end()


def print_sheets(sheets: "list[Sheet]", resolver: ViewResolver, printer) -> None:
    """Print *sheets* to *printer* (a configured ``QPrinter``), one page each.

    The caller owns the QPrinter (typically configured via ``QPrintDialog``).
    Mixed paper sizes are honoured per page via ``setPageSize``.

    Args:
        sheets: One or more sheets. Must be non-empty.
        resolver: Shared ViewResolver bridging viewports to source scenes.
        printer: A QPrinter the caller has already configured.

    Raises:
        ValueError: If *sheets* is empty.
        OSError: If the printer painter cannot be started.
    """
    if not sheets:
        raise ValueError("print_sheets requires at least one sheet")

    painter: QPainter | None = None
    try:
        for sheet in sheets:
            _set_page(printer, sheet)
            if painter is None:
                painter = QPainter(printer)
                if not painter.isActive():
                    raise OSError("Could not start printing (painter inactive)")
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            else:
                printer.newPage()
            render_sheet(sheet, resolver, painter, QRectF(painter.viewport()))
    finally:
        if painter is not None and painter.isActive():
            painter.end()
