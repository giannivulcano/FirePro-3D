"""
PDF Import Worker
=================
Extracts vector geometry from PDF files using PyMuPDF (fitz).

Produces geometry dicts compatible with the DxfImportWorker output so the
same main-thread item-building helpers (``_append_geom_to_path`` /
``_build_pen_cache``) can render them.  Also generates page thumbnails for
the multi-page thumbnail strip in the import dialog.
"""

from __future__ import annotations

import math
from PyQt6.QtCore import QSettings, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    fitz = None
    _HAS_FITZ = False

from .constants import (PDF_BEZIER_FLATTEN_TOL, PDF_CURVE_JOIN_EPS,
                        PDF_CIRCLE_FIT_REL_TOL, PDF_CIRCLE_FIT_ABS_TOL)

# QSettings org/app — must match preferences_dialog._QSETTINGS_ORG/_APP.
_QSETTINGS_ORG = "GV"
_QSETTINGS_APP = "FirePro3D"

# How often (in drawing paths) extract_pdf_vectors_sync polls should_cancel.
# Small enough that Cancel feels immediate; large enough that the poll is
# negligible against the per-path extraction cost.
_CANCEL_POLL_EVERY = 100


def current_pdf_flatten_tol() -> float:
    """Return the user's PDF bézier flatten tolerance (PDF points).

    Reads the ``import/pdf_bezier_flatten_tol`` preference (Preferences →
    Import & Conversion), falling back to :data:`PDF_BEZIER_FLATTEN_TOL`.
    This value is BOTH an extraction parameter (fed to ``_flatten_bezier``)
    and part of the PDF cache key (``compute_cache_key(flatten_tol=…)``), so
    changing it re-extracts on the next load/refresh.
    """
    try:
        s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
        return float(s.value("import/pdf_bezier_flatten_tol",
                             PDF_BEZIER_FLATTEN_TOL, type=float))
    except Exception:
        return PDF_BEZIER_FLATTEN_TOL


# ─────────────────────────────────────────────────────────────────────────────
# Bezier flattening
# ─────────────────────────────────────────────────────────────────────────────

def _flatten_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    tol: float = PDF_BEZIER_FLATTEN_TOL,
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
# Curve preservation (Block Editor import — 2d-geometry §3.5.3)
# ─────────────────────────────────────────────────────────────────────────────
# A segment is ("l", p0, p1) or ("c", p0, p1, p2, p3) with (x, y) tuples in
# PDF page coords (Y-down == scene coords, no flip).

def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _bez_pt(seg, t: float):
    """Point at *t* on a cubic segment ("c", p0, p1, p2, p3)."""
    _, p0, p1, p2, p3 = seg
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def _fit_circle(pts):
    """Least-squares (Kasa) circle ``(cx, cy, r)`` through *pts*, or None.

    Solves x² + y² + D·x + E·y + F = 0 in the mean-centred frame (better
    conditioned). Returns None for a degenerate (collinear) point set.
    """
    import numpy as np
    a = np.asarray(pts, dtype=float)
    m = a.mean(axis=0)
    x, y = a[:, 0] - m[0], a[:, 1] - m[1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x * x + y * y)
    (d, e, f), *_ = np.linalg.lstsq(A, b, rcond=None)
    rr = (d * d + e * e) / 4.0 - f
    if not np.isfinite(rr) or rr <= 0:
        return None
    return float(m[0] - d / 2.0), float(m[1] - e / 2.0), float(np.sqrt(rr))


def _wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def _circular_geom(segs: list, layer: str) -> dict | None:
    """Recognise a run of cubic Béziers as a circle / circular arc.

    Fits ONE least-squares circle to samples of every segment (a 3-point fit
    through a short, quantized first segment is too noisy — the 2026-09-23
    smoke miss) and accepts when every sample is within
    ``max(PDF_CIRCLE_FIT_ABS_TOL, PDF_CIRCLE_FIT_REL_TOL * r)``. Returns a
    ``circle`` or ``arc`` geom dict (the shared scene-space schemas), or None.
    Arc angles are Qt ``arcTo`` angles (0 = +x, positive = visually CCW, i.e.
    toward -y in these Y-down coords) — the convention ``ArcItem`` consumes.
    """
    samples = [_bez_pt(seg, t) for seg in segs
               for t in (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875)]
    samples.append(segs[-1][4])
    fit = _fit_circle(samples)
    if fit is None:
        return None
    cx, cy, r = fit
    tol = max(PDF_CIRCLE_FIT_ABS_TOL, PDF_CIRCLE_FIT_REL_TOL * r)
    if any(abs(_dist(q, (cx, cy)) - r) > tol for q in samples):
        return None
    # A (near-)straight run fits a huge circle within tolerance — it is a
    # line, not an arc: require real bulge off the chord.
    p0, p1 = samples[0], samples[-1]
    chord = _dist(p0, p1)
    if chord > tol:
        ux, uy = (p1[0] - p0[0]) / chord, (p1[1] - p0[1]) / chord
        bulge = max(abs((q[0] - p0[0]) * uy - (q[1] - p0[1]) * ux) for q in samples)
        if bulge <= tol:
            return None

    def ang(q):
        return math.degrees(math.atan2(-(q[1] - cy), q[0] - cx))

    total = 0.0
    for seg in segs:
        a0, am, a3 = ang(seg[1]), ang(_bez_pt(seg, 0.5)), ang(seg[4])
        sweep = _wrap180(am - a0) + _wrap180(a3 - am)
        if abs(sweep) < 1e-9 or (total and (sweep > 0) != (total > 0)):
            return None                     # degenerate or direction reversal
        total += sweep
    if abs(total) > 360.5:
        return None
    if abs(abs(total) - 360.0) <= 0.5 and _dist(segs[0][1], segs[-1][4]) <= tol:
        return {"kind": "circle", "layer": layer,
                "x": cx - r, "y": cy - r, "w": 2 * r, "h": 2 * r}
    return {"kind": "arc", "layer": layer,
            "rx": cx - r, "ry": cy - r, "rw": 2 * r, "rh": 2 * r,
            "start": ang(segs[0][1]), "span": total}


def _spline_geom(segs: list, closed: bool, layer: str) -> dict:
    """One EXACT cubic B-spline through a mixed line/Bézier subpath.

    Each segment contributes 3 control points (a line is degree-elevated to a
    collinear cubic, so it stays exactly straight); interior knots have
    multiplicity 3, making each span the source Bézier verbatim — no fitting.
    """
    segs = list(segs)
    start, end = segs[0][1], segs[-1][-1]
    if closed and _dist(start, end) > PDF_CURVE_JOIN_EPS:
        segs.append(("l", end, start))
    cps = [segs[0][1]]
    for seg in segs:
        if seg[0] == "l":
            (x0, y0), (x1, y1) = seg[1], seg[2]
            cps += [(x0 + (x1 - x0) / 3.0, y0 + (y1 - y0) / 3.0),
                    (x0 + 2.0 * (x1 - x0) / 3.0, y0 + 2.0 * (y1 - y0) / 3.0),
                    (x1, y1)]
        else:
            cps += [seg[2], seg[3], seg[4]]
    n = len(segs)
    knots = ([0.0] * 4 + [float(i) for i in range(1, n) for _ in range(3)]
             + [float(n)] * 4)
    return {"kind": "spline", "layer": layer, "control_points": cps,
            "degree": 3, "knots": knots, "weights": None,
            "closed": _dist(cps[0], cps[-1]) <= PDF_CURVE_JOIN_EPS}


def _piece_geom(segs: list, closed: bool, layer: str) -> dict:
    """A non-arc piece: ``path_points`` if all lines, else one exact spline."""
    if not any(sg[0] == "c" for sg in segs):
        return {"kind": "path_points", "layer": layer,
                "points": [segs[0][1]] + [sg[-1] for sg in segs],
                "closed": closed}
    return _spline_geom(segs, closed, layer)


def _subpath_geoms(segs: list, closed: bool, layer: str) -> list[dict]:
    """Emit geoms for a contiguous subpath (curve-preserving mode).

    Maximal runs of Béziers that fit a circle are carved out as
    ``circle``/``arc`` (how a DXF would arrive: separate entities); the
    stretches between them merge into ONE piece each — a spline when they
    contain a free-form curve, else a polyline. A line-only subpath is
    emitted exactly as the flattening path does.
    """
    if not any(sg[0] == "c" for sg in segs):
        return [_piece_geom(segs, closed, layer)]
    work = list(segs)
    if closed and _dist(work[0][1], work[-1][-1]) > PDF_CURVE_JOIN_EPS:
        work.append(("l", work[-1][-1], work[0][1]))
    # Maximal same-kind runs.
    runs: list[list] = []
    for sg in work:
        if runs and runs[-1][0][0] == sg[0]:
            runs[-1].append(sg)
        else:
            runs.append([sg])
    out: list[dict] = []
    pending: list = []
    for run in runs:
        circ = _circular_geom(run, layer) if run[0][0] == "c" else None
        if circ is None:
            pending.extend(run)
            continue
        if pending:
            out.append(_piece_geom(pending, False, layer))
            pending = []
        out.append(circ)
    if pending:
        whole = len(pending) == len(work)      # nothing carved out
        out.append(_piece_geom(pending, closed and whole, layer))
    return out


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
        self._flatten_tol = current_pdf_flatten_tol()

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

        try:
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

            # ── Extract text blocks ────────────────────────────────────
            try:
                text_geoms = self._extract_text(page_obj)
                geometries.extend(text_geoms)
            except Exception:
                pass

            if skipped:
                self.status.emit(f"Done — {len(geometries)} geometries, {skipped} skipped")
            else:
                self.status.emit(f"Done — {len(geometries)} geometries")

            self.finished_data.emit(geometries)
        finally:
            doc.close()

    # ─────────────────────────────────────────────────────────────────
    # Path → geometry dicts
    # ─────────────────────────────────────────────────────────────────

    def _extract_path(self, path: dict) -> list[dict]:
        """Convert a single PyMuPDF drawing path dict into geometry dicts.

        PyMuPDF coordinate system is top-left Y-down in PDF points (1/72 in),
        which matches Qt's scene coordinate system — no Y-flip needed.

        With ``_preserve_curves`` (Block Editor import) curves are kept exact
        instead of flattened — see :meth:`_extract_path_curves`.
        """
        if getattr(self, "_preserve_curves", False):
            return self._extract_path_curves(path)
        items = path.get("items", [])
        layer = path.get("layer", "") or "PDF Vectors"
        width = float(path.get("width") or 0.0)
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
                    tol=getattr(self, "_flatten_tol", None) or PDF_BEZIER_FLATTEN_TOL,
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

        # Carry the PDF stroke width (points) onto every geom from this path,
        # so the underlay builder can preserve the source line-width hierarchy.
        for r in results:
            r["width"] = width
        return results

    def _extract_path_curves(self, path: dict) -> list[dict]:
        """Curve-preserving variant of :meth:`_extract_path`.

        Splits the drawing into contiguous subpaths (a gap = PDF move-to);
        each subpath becomes a ``circle``/``arc`` (all-Bézier and circular), a
        single exact cubic ``spline`` (any other curved subpath) or the usual
        ``path_points`` (lines only). ``re``/``qu`` items emit closed
        ``path_points`` exactly as the flattening path does. ``closePath``
        applies to the drawing's final subpath.
        """
        layer = path.get("layer", "") or "PDF Vectors"
        width = float(path.get("width") or 0.0)
        results: list[dict] = []
        segs: list = []

        def xy(p):
            return (p.x, p.y)

        def flush(closed=False):
            if segs:
                results.extend(_subpath_geoms(segs, closed, layer))
                segs.clear()

        for item in path.get("items", []):
            kind = item[0]
            if kind == "l":
                seg = ("l", xy(item[1]), xy(item[2]))
            elif kind == "c":
                seg = ("c", xy(item[1]), xy(item[2]), xy(item[3]), xy(item[4]))
            elif kind == "re":
                flush()
                r = item[1]
                results.append({"kind": "path_points", "layer": layer,
                                "points": [(r.x0, r.y0), (r.x1, r.y0),
                                           (r.x1, r.y1), (r.x0, r.y1)],
                                "closed": True})
                continue
            elif kind == "qu":
                flush()
                q = item[1]
                results.append({"kind": "path_points", "layer": layer,
                                "points": [(q.ul.x, q.ul.y), (q.ur.x, q.ur.y),
                                           (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)],
                                "closed": True})
                continue
            else:
                continue
            if segs and _dist(segs[-1][-1], seg[1]) > PDF_CURVE_JOIN_EPS:
                flush()
            segs.append(seg)
        flush(bool(path.get("closePath", False)))

        for r in results:
            r["width"] = width
        return results

    # ─────────────────────────────────────────────────────────────────
    # Text extraction
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(page) -> list[dict]:
        """Extract text spans from a PDF page as geometry dicts.

        Uses ``get_text("dict")`` which returns text blocks containing
        lines and spans with position, size, and content.  Each span
        becomes a ``kind: "text"`` geometry dict.
        """
        results: list[dict] = []
        try:
            td = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except Exception:
            return results

        for block in td.get("blocks", []):
            if block.get("type") != 0:      # 0 = text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    origin = span.get("origin")   # (x, baseline_y) — exact baseline
                    bbox = span.get("bbox")       # ink bbox — for width fitting
                    size = span.get("size", 8.0)
                    if origin is None:
                        if bbox is None:
                            continue
                        origin = (bbox[0], bbox[3])
                    results.append({
                        "kind": "text",
                        "layer": "PDF Text",
                        "x": origin[0],
                        "y": origin[1],   # place the glyph baseline here
                        "text": text,
                        "size": size,
                        "halign": 0,      # left (span origin x)
                        "valign": 3,      # baseline: base_y = y (the span origin)
                        # on-paper text width -> substitute font is x-scaled to it
                        "twidth": (bbox[2] - bbox[0]) if bbox else None,
                    })
        return results


# ─────────────────────────────────────────────────────────────────────────────
# Synchronous helpers for the preview dialog
# ─────────────────────────────────────────────────────────────────────────────

def extract_pdf_vectors_sync(
    file_path: str,
    page: int = 0,
    should_cancel=None,
    preserve_curves: bool = False,
) -> tuple[list[dict], list[str]] | None:
    """Extract vector geometry from a PDF page synchronously.

    Args:
        file_path: Path to the PDF file.
        page: 0-based page index to extract.
        should_cancel: Optional zero-arg callable polled during the drawing
            loop (every :data:`_CANCEL_POLL_EVERY` paths). When it returns
            truthy, extraction aborts early and this function returns ``None``.
            Defaults to ``None`` — no polling, i.e. the original behaviour, so
            callers that never cancel (e.g. ``model_space`` reloads) are
            unaffected.
        preserve_curves: Keep Béziers as exact circle/arc/spline geoms
            instead of flattening (Block Editor import). Default False keeps
            the underlay path byte-identical.

    Returns:
        ``(geometry_list, layer_names)`` on success, or ``None`` when the run
        was cancelled via *should_cancel*.
    """
    if not _HAS_FITZ:
        return [], []

    doc = fitz.open(file_path)
    try:
        if page < 0 or page >= len(doc):
            return [], []

        page_obj = doc[page]
        drawings = page_obj.get_drawings()

        worker = PdfImportWorker.__new__(PdfImportWorker)
        worker._cancelled = False
        worker._flatten_tol = current_pdf_flatten_tol()
        worker._preserve_curves = preserve_curves

        geometries: list[dict] = []
        layers_set: set[str] = set()

        for i, path in enumerate(drawings):
            # Poll for cancellation periodically so a Cancel during a large
            # page's extraction takes effect mid-run rather than only after
            # the whole page finishes.
            if (should_cancel is not None
                    and i % _CANCEL_POLL_EVERY == 0
                    and should_cancel()):
                return None
            try:
                geoms = worker._extract_path(path)
                for g in geoms:
                    geometries.append(g)
                    layers_set.add(g.get("layer", "PDF Vectors"))
            except Exception:
                pass

        if should_cancel is not None and should_cancel():
            return None

        # Also extract text
        try:
            text_geoms = PdfImportWorker._extract_text(page_obj)
            for g in text_geoms:
                geometries.append(g)
                layers_set.add(g.get("layer", "PDF Text"))
        except Exception:
            pass

        return geometries, sorted(layers_set) if layers_set else ["PDF Vectors"]
    finally:
        doc.close()


def generate_pdf_thumbnails(file_path: str, width: int = 128) -> list[tuple[int, QPixmap]]:
    """Generate page thumbnails for a PDF file synchronously.

    Returns list of (page_index, QPixmap) tuples.
    """
    if not _HAS_FITZ:
        return []

    thumbs = []
    doc = None
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
    finally:
        if doc is not None:
            doc.close()

    return thumbs


def pdf_page_names(file_path: str) -> list[str]:
    """Return a display name per page: PDF page label if present, else 'Page N'."""
    if not _HAS_FITZ:
        return []
    names: list[str] = []
    doc = fitz.open(file_path)
    try:
        for i in range(len(doc)):
            label = ""
            try:
                label = doc[i].get_label()      # PyMuPDF >= 1.18
            except Exception:
                label = ""
            names.append(label.strip() if label and label.strip()
                         else f"Page {i + 1}")
    finally:
        doc.close()
    return names
