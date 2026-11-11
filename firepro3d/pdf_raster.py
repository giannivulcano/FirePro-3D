"""pdf_raster.py
================
One PDF page -> ``QImage`` raster, shared by the PDF underlay raster import and
the sheet-linked document page (sheet-linked-document design D1b).
"""
from __future__ import annotations

import fitz
from PyQt6.QtGui import QImage


def pdf_page_to_qimage(page: "fitz.Page", dpi: float) -> QImage:
    """Render *page* at *dpi* to an RGB888 ``QImage`` detached from fitz.

    Args:
        page: An open PyMuPDF page.
        dpi: Raster resolution in dots per inch of the page.

    Returns:
        A ``QImage`` that owns its pixels (safe after the document closes).
    """
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                 QImage.Format.Format_RGB888)
    return img.copy()      # .copy() detaches from the fitz buffer
