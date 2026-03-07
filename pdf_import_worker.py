"""
PDF Import Worker
=================
Extracts vector geometry from PDF files using PyMuPDF (fitz).

Produces geometry dicts compatible with the DxfImportWorker output so the
same ``_geom_to_item()`` pipeline can render them.  Also generates page
thumbnails for the multi-page thumbnail strip in the import dialog.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    fitz = None
    _HAS_FITZ = False


# ─────────────────────────────────────────────────────────────────────────────
# Bezier flattening
# ─────────────────────────────────────────────────────────────────────────────

def _flatten_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    tol: float = 1.0,
) -> list[tuple[float, float]]:
    """Flatten a cubic Bezier curve via De Casteljau subdivision.

    Returns a list of ``(x, y)`` points (including *p0* and *p3*).
    *tol* is the maximum chord deviation in PDF points before subdividing.
    """

    def _flatness(a, b, c, d):
        """Estimate max deviation of control points from the chord a→d."""
        ux = 3.0 * b[0] - 2.0 * a[0] - d[0]
        uy = 3.0 * b[1] - 2.0 * a[1] - d[1]
        vx = 3.0 * c[0] - 2.0 * d[0] - a[0]
        vy = 3.0 * c[1] - 2.0 * d[1] - a[1]
        return max(ux * ux, vx * vx) + max(uy * uy, vy * vy)

    tol_sq = tol * tol * 16.0  # matches the flatness formula scale

    result: list[tuple[float, float]] = [p0]
    stack = [(p0, p1, p2, p3)]

    while stack:
        a, b, c, d = stack.pop()
        if _flatness(a, b, c, d) < tol_sq:
            result.append(d)
        else:
            # De Casteljau split at t = 0.5
            ab = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            bc = ((b[0] + c[0]) * 0.5, (b[1] + c[1]) * 0.5)
            cd = ((c[0] + d[0]) * 0.5, (c[1] + d[1]) * 0.5)
            abc = ((ab[0] + bc[0]) * 0.5, (ab[1] + bc[1]) * 0.5)
            bcd = ((bc[0] + cd[0]) * 0.5, (bc[1] + cd[1]) * 0.5)
            abcd = ((abc[0] + bcd[0]) * 0.5, (abc[1] + bcd[1]) * 0.5)
            # Push right half first (stack is LIFO → left half processed first)
            stack.append((abcd, bcd, cd, d))
            stack.append((a, ab, abc, abcd))

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Worker
# ─────────────────────────────────────────────────────────────────────────────

class PdfImportWorker(QThread):
    """
    Extracts vector geometry from a PDF page using PyMuPDF.

    Signals
    -------
    progress(int, int)      — (current, total) drawing counts
    status(str)             — status message
    finished_data(list)     — list of geometry dicts (same schema as DxfImportWorker)
    error(str)              — error message
    thumbnails_ready(list)  — list of (page_index, QPixmap) tuples
    """
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished_data = pyqtSignal(list)
    error = pyqtSignal(str)
    thumbnails_ready = pyqtSignal(list)

    def __init__(self, file_path: str, page: int = 0,
                 extract_vectors: bool = True, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.page = page
        self.extract_vectors = extract_vectors
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if not _HAS_FITZ:
            self.error.emit("PyMuPDF (fitz) is not installed.\n"
                            "Install it with:  pip install PyMuPDF")
            return

        try:
            doc = fitz.open(self.file_path)
        except Exception as e:
            self.error.emit(f"Failed to open PDF: {e}")
            return

        # ── Generate thumbnails ───────────────────────────────────────
        self.status.emit("Generating page thumbnails…")
        thumbs = []
        for i in range(len(doc)):
            if self._cancelled:
                return
            try:
                pg = doc[i]
                # 128px wide thumbnail
                zoom = 128.0 / max(pg.rect.width, 1)
                mat = fitz.Matrix(zoom, zoom)
                pix = pg.get_pixmap(matrix=mat, alpha=False)
                qimg = QImage(pix.samples, pix.width, pix.height,
                              pix.stride, QImage.Format.Format_RGB888)
                thumbs.append((i, QPixmap.fromImage(qimg)))
            except Exception:
                pass
        if thumbs:
            self.thumbnails_ready.emit(thumbs)

        # ── Extract vectors from the selected page ────────────────────
        if not self.extract_vectors:
            self.finished_data.emit([])
            return

        if self.page < 0 or self.page >= len(doc):
            self.error.emit(f"Page {self.page} out of range (0–{len(doc)-1})")
            return

        page_obj = doc[self.page]
        self.status.emit(f"Extracting vectors from page {self.page + 1}…")

        try:
            drawings = page_obj.get_drawings()
        except Exception as e:
            self.error.emit(f"Failed to extract drawings: {e}")
            return

        total = len(drawings)
        self.status.emit(f"Processing {total} drawing paths…")

        geometries: list[dict] = []
        skipped = 0

        for i, path in enumerate(drawings):
            if self._cancelled:
                self.status.emit("Cancelled")
                return

            try:
                geoms = self._extract_path(path)
                geometries.extend(geoms)
            except Exception:
                skipped += 1

            if i % 200 == 0 or i == total - 1:
                self.progress.emit(i + 1, total)

        if skipped:
            self.status.emit(f"Done — {len(geometries)} geometries, {skipped} skipped")
        else:
            self.status.emit(f"Done — {len(geometries)} geometries")

        self.finished_data.emit(geometries)

    # ─────────────────────────────────────────────────────────────────
    # Path → geometry dicts
    # ─────────────────────────────────────────────────────────────────

    def _extract_path(self, path: dict) -> list[dict]:
        """Convert a single PyMuPDF drawing path dict into geometry dicts.

        PyMuPDF coordinate system is top-left Y-down in PDF points (1/72 in),
        which matches Qt's scene coordinate system — no Y-flip needed.
        """
        items = path.get("items", [])
        layer = path.get("layer", "") or "PDF Vectors"
        results: list[dict] = []

        # Track points for building a single path_points from connected segments
        current_points: list[tuple[float, float]] = []
        is_closed = bool(path.get("closePath", False))

        for item in items:
            kind = item[0]

            if kind == "l":
                # Line segment: ("l", Point(x0,y0), Point(x1,y1))
                p0, p1 = item[1], item[2]
                x0, y0 = p0.x, p0.y
                x1, y1 = p1.x, p1.y

                if not current_points:
                    current_points.append((x0, y0))
                current_points.append((x1, y1))

            elif kind == "re":
                # Rectangle: ("re", Rect(x0,y0,x1,y1), ...)
                # Flush any current path first
                if len(current_points) >= 2:
                    results.append({
                        "kind": "path_points", "layer": layer,
                        "points": list(current_points),
                        "closed": is_closed,
                    })
                    current_points = []

                rect = item[1]
                x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
                results.append({
                    "kind": "path_points", "layer": layer,
                    "points": [
                        (x0, y0), (x1, y0), (x1, y1), (x0, y1),
                    ],
                    "closed": True,
                })

            elif kind == "qu":
                # Quad: ("qu", Quad)
                if len(current_points) >= 2:
                    results.append({
                        "kind": "path_points", "layer": layer,
                        "points": list(current_points),
                        "closed": is_closed,
                    })
                    current_points = []

                quad = item[1]
                results.append({
                    "kind": "path_points", "layer": layer,
                    "points": [
                        (quad.ul.x, quad.ul.y),
                        (quad.ur.x, quad.ur.y),
                        (quad.lr.x, quad.lr.y),
                        (quad.ll.x, quad.ll.y),
                    ],
                    "closed": True,
                })

            elif kind == "c":
                # Cubic Bezier: ("c", Point0, Point1, Point2, Point3)
                p0, p1, p2, p3 = item[1], item[2], item[3], item[4]
                pts = _flatten_bezier(
                    (p0.x, p0.y), (p1.x, p1.y),
                    (p2.x, p2.y), (p3.x, p3.y),
                    tol=0.5,
                )
                if not current_points:
                    current_points.extend(pts)
                else:
                    # Skip first point (duplicate of last point in current_points)
                    current_points.extend(pts[1:])

        # Flush remaining points
        if len(current_points) >= 2:
            results.append({
                "kind": "path_points", "layer": layer,
                "points": list(current_points),
                "closed": is_closed,
            })

        return results


# ─────────────────────────────────────────────────────────────────────────────
# Synchronous helpers for the preview dialog
# ─────────────────────────────────────────────────────────────────────────────

def extract_pdf_vectors_sync(
    file_path: str,
    page: int = 0,
) -> tuple[list[dict], list[str]]:
    """Extract vector geometry from a PDF page synchronously.

    Returns (geometry_list, layer_names).
    """
    if not _HAS_FITZ:
        return [], []

    doc = fitz.open(file_path)
    if page < 0 or page >= len(doc):
        return [], []

    page_obj = doc[page]
    drawings = page_obj.get_drawings()

    worker = PdfImportWorker.__new__(PdfImportWorker)
    worker._cancelled = False

    geometries: list[dict] = []
    layers_set: set[str] = set()

    for path in drawings:
        try:
            geoms = worker._extract_path(path)
            for g in geoms:
                geometries.append(g)
                layers_set.add(g.get("layer", "PDF Vectors"))
        except Exception:
            pass

    return geometries, sorted(layers_set) if layers_set else ["PDF Vectors"]


def generate_pdf_thumbnails(file_path: str, width: int = 128) -> list[tuple[int, QPixmap]]:
    """Generate page thumbnails for a PDF file synchronously.

    Returns list of (page_index, QPixmap) tuples.
    """
    if not _HAS_FITZ:
        return []

    thumbs = []
    try:
        doc = fitz.open(file_path)
        for i in range(len(doc)):
            pg = doc[i]
            zoom = width / max(pg.rect.width, 1)
            mat = fitz.Matrix(zoom, zoom)
            pix = pg.get_pixmap(matrix=mat, alpha=False)
            qimg = QImage(pix.samples, pix.width, pix.height,
                          pix.stride, QImage.Format.Format_RGB888)
            thumbs.append((i, QPixmap.fromImage(qimg)))
    except Exception:
        pass

    return thumbs
