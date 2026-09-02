"""
dwg_converter.py
================
DWG to DXF conversion via ODA File Converter.

ODA File Converter is a free tool from Open Design Alliance that converts
between DWG and DXF formats.  This module handles finding the ODA executable,
running the conversion, and listing layouts from the resulting DXF.

ODA CLI usage::

    ODAFileConverter <input_dir> <output_dir> <version> <type> <recurse> <audit>

The converter operates on directories, not individual files, so we copy
the source DWG into a temp input directory and read the output DXF from
a temp output directory.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

_last_error: str = ""


def _set_last_error(msg: str) -> None:
    global _last_error
    _last_error = msg


def get_last_error() -> str:
    """Return diagnostic info from the last failed conversion."""
    return _last_error


_COMMON_ODA_DIRS: list[str] = [
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter 27.1.0"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter 26.3.0"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter 25.12.0"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter 25.6.0"),
    os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                 "ODA", "ODAFileConverter"),
]

_ODA_EXE = "ODAFileConverter.exe"

# Download page for error dialogs
ODA_DOWNLOAD_URL = "https://www.opendesign.com/guestfiles/oda_file_converter"


def _oda_path_from_settings() -> str | None:
    """Read the ODA converter path from QSettings, if set."""
    try:
        from PyQt6.QtCore import QSettings
        s = QSettings("GV", "FirePro3D")
        path = s.value("dwg/oda_converter_path", None)
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    return None


def find_oda_converter() -> str | None:
    """Locate the ODA File Converter executable.

    Search order:
    1. QSettings (user-configured path)
    2. System PATH (shutil.which)
    3. Common install directories

    Returns:
        Absolute path to ODAFileConverter.exe, or None if not found.
    """
    # 1. QSettings
    path = _oda_path_from_settings()
    if path:
        return path

    # 2. PATH
    which = shutil.which(_ODA_EXE)
    if which and os.path.isfile(which):
        return which

    # 3. Common install directories
    for d in _COMMON_ODA_DIRS:
        candidate = os.path.join(d, _ODA_EXE)
        if os.path.isfile(candidate):
            return candidate

    return None


def _ref_dir_for_project(project_dir: str | None) -> str | None:
    """Return the UNDERLAY_REF directory for a project, creating if needed.

    Args:
        project_dir: Directory containing the ``.fpd`` project file,
            or ``None`` if the project has not been saved yet.

    Returns:
        Absolute path to ``<project_dir>/UNDERLAY_REF/``, or ``None``
        if no project directory is available.
    """
    if not project_dir:
        return None
    ref_dir = os.path.join(project_dir, "UNDERLAY_REF")
    os.makedirs(ref_dir, exist_ok=True)
    return ref_dir


def convert_dwg_to_dxf(oda_path: str, dwg_path: str,
                        project_dir: str | None = None) -> str | None:
    """Convert a DWG file to DXF using ODA File Converter.

    When *project_dir* is given the converted DXF is saved to
    ``<project_dir>/UNDERLAY_REF/<stem>.dxf`` so it persists across
    sessions.  If the DXF already exists and is newer than the source
    DWG, the conversion is skipped entirely.

    When *project_dir* is ``None`` (project not saved yet), a temporary
    directory is used instead.

    Args:
        oda_path: Absolute path to ODAFileConverter.exe.
        dwg_path: Absolute path to the source ``.dwg`` file.
        project_dir: Directory containing the ``.fpd`` project file.

    Returns:
        Absolute path to the converted ``.dxf`` file, or ``None`` on
        failure (ODA crash, no output produced, source file missing).
    """
    if not os.path.isfile(dwg_path):
        return None

    basename = os.path.basename(dwg_path)
    stem = os.path.splitext(basename)[0]

    # Determine output directory
    ref_dir = _ref_dir_for_project(project_dir)
    if ref_dir:
        out_dir = ref_dir
        is_temp = False
        # Skip conversion if a fresh DXF already exists
        existing = os.path.join(out_dir, f"{stem}.dxf")
        if os.path.isfile(existing):
            if os.path.getmtime(existing) >= os.path.getmtime(dwg_path):
                return existing
    else:
        out_dir = tempfile.mkdtemp(prefix="fpro_dwg_out_")
        is_temp = True

    # ODA operates on directories — isolate the source file
    in_dir = tempfile.mkdtemp(prefix="fpro_dwg_in_")

    last_error = ""
    try:
        shutil.copy2(dwg_path, os.path.join(in_dir, basename))

        # ODA args: input_dir output_dir version output_type recurse audit
        cmd = [oda_path, in_dir, out_dir, "ACAD2018", "DXF", "0", "1"]

        # Suppress the ODA GUI window on Windows
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        result = subprocess.run(cmd, timeout=120, capture_output=True,
                                text=True, startupinfo=startupinfo)
        last_error = (f"ODA exit code {result.returncode}\n"
                      f"stdout: {(result.stdout or '')[:500]}\n"
                      f"stderr: {(result.stderr or '')[:500]}")
        if result.returncode != 0:
            _set_last_error(last_error)
            if is_temp:
                shutil.rmtree(out_dir, ignore_errors=True)
            return None
    except subprocess.TimeoutExpired:
        _set_last_error("ODA conversion timed out after 120 seconds")
        shutil.rmtree(in_dir, ignore_errors=True)
        if is_temp:
            shutil.rmtree(out_dir, ignore_errors=True)
        return None
    except OSError as e:
        _set_last_error(f"OSError launching ODA: {e}")
        shutil.rmtree(in_dir, ignore_errors=True)
        if is_temp:
            shutil.rmtree(out_dir, ignore_errors=True)
        return None
    finally:
        shutil.rmtree(in_dir, ignore_errors=True)

    # Find the output DXF
    expected = os.path.join(out_dir, f"{stem}.dxf")
    if os.path.isfile(expected):
        return expected

    # Fallback: pick the first .dxf in the output directory
    try:
        out_files = os.listdir(out_dir)
    except OSError:
        out_files = []
    for f in out_files:
        if f.lower().endswith(".dxf"):
            return os.path.join(out_dir, f)

    # No DXF produced — store diagnostics
    _set_last_error(
        last_error or
        f"No DXF produced. Output dir contents: {out_files}\n"
        f"cmd: {cmd}")
    if is_temp:
        shutil.rmtree(out_dir, ignore_errors=True)
    return None


def cleanup_converted_dxf(dxf_path: str) -> None:
    """Remove a converted DXF only if it lives in a temp directory.

    DXFs in ``UNDERLAY_REF/`` are kept for reuse across sessions.
    Only temp directories created when no project is saved are cleaned up.
    """
    if not dxf_path:
        return
    parent = os.path.dirname(dxf_path)
    if os.path.basename(parent).startswith("fpro_dwg_out_"):
        shutil.rmtree(parent, ignore_errors=True)


def read_dxf(dxf_path: str):
    """Read a DXF file and return the ezdxf document.

    Call once and pass the result to :func:`list_layouts`,
    :func:`get_viewport_bounds`, and :func:`extract_layout_entities`
    to avoid re-reading large files multiple times.

    Returns:
        An ezdxf document object, or ``None`` on read failure.
    """
    try:
        import ezdxf
        return ezdxf.readfile(dxf_path)
    except Exception:
        return None


def list_layouts(dxf_path: str = "", doc=None) -> list[str]:
    """Read layout names from a DXF file.

    Args:
        dxf_path: Path to a DXF file (ignored if *doc* is provided).
        doc: Pre-read ezdxf document from :func:`read_dxf`.

    Returns:
        List of layout names with ``"Model"`` always first.
        Returns ``["Model"]`` on any error.
    """
    if doc is None:
        doc = read_dxf(dxf_path)
    if doc is None:
        return ["Model"]

    try:
        names = list(doc.layouts.names())
    except Exception:
        return ["Model"]

    # Ensure "Model" is first
    if "Model" in names:
        names.remove("Model")
    return ["Model"] + sorted(names)


def get_viewport_bounds(
    dxf_path: str = "", layout_name: str = "", doc=None,
) -> list[tuple[float, float, float, float]] | None:
    """Extract model-space bounding boxes from viewports in a paper layout.

    Each viewport in a paper-space layout defines a window into model
    space.  This function reads those viewport definitions and returns
    the model-space regions they display — with Y negated to match the
    geometry dict coordinate convention (Y-down).

    Args:
        dxf_path: Path to the converted DXF file (ignored if *doc* given).
        layout_name: Name of the paper-space layout.
        doc: Pre-read ezdxf document from :func:`read_dxf`.

    Returns:
        List of ``(min_x, min_y, max_x, max_y)`` tuples in geometry-dict
        coordinates (Y negated), or ``None`` if *layout_name* is
        ``"Model"`` or no viewports are found.
    """
    if layout_name == "Model":
        return None

    if doc is None:
        doc = read_dxf(dxf_path)
    if doc is None:
        return None

    try:
        layout = doc.layouts.get(layout_name)
    except Exception:
        return None

    bounds: list[tuple[float, float, float, float]] = []
    for entity in layout:
        if entity.dxftype() != "VIEWPORT":
            continue
        # Viewport #1 is the paper-space background — skip it
        vp_id = entity.dxf.get("id", 0)
        if vp_id == 1:
            continue
        # Viewport might be off
        status = entity.dxf.get("status", 1)
        if status == 0:
            continue

        try:
            vc = entity.dxf.view_center_point  # model-space center (x, y)
            vh = entity.dxf.view_height         # model-space height
            vp_w = entity.dxf.width             # paper-space width
            vp_h = entity.dxf.height            # paper-space height
        except AttributeError:
            continue

        if vh <= 0 or vp_h <= 0:
            continue

        # Model-space width derived from aspect ratio
        vw = vh * (vp_w / vp_h)

        cx, cy = float(vc[0]), float(vc[1])

        # Negate Y to match geometry dict convention (DxfImportWorker
        # negates all Y coordinates during extraction).
        bounds.append((
            cx - vw / 2,          # min_x
            -cy - vh / 2,         # min_y (negated)
            cx + vw / 2,          # max_x
            -cy + vh / 2,         # max_y (negated)
        ))

    return bounds if bounds else None


def compute_geom_bounds(geoms: list[dict]) -> list[float] | None:
    """Compute the bounding box of geometry dicts' representative points.

    Uses the same point logic as :func:`_geom_in_any_bound` so the
    returned bounds can be fed back to :func:`filter_geoms_by_bounds`
    for consistent round-trip filtering.

    Returns ``[min_x, min_y, max_x, max_y]`` or ``None`` if *geoms*
    is empty or contains no locatable geometry.
    """
    if not geoms:
        return None
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for g in geoms:
        kind = g.get("kind")
        points: list[tuple[float, float]] = []
        if kind == "line":
            points = [(g["x1"], g["y1"]), (g["x2"], g["y2"])]
        elif kind == "circle":
            points = [(g["x"] + g["w"] / 2, g["y"] + g["h"] / 2)]
        elif kind == "arc":
            points = [(g["rx"] + g["rw"] / 2, g["ry"] + g["rh"] / 2)]
        elif kind == "ellipse_full":
            points = [(g["pos_cx"], g["pos_cy"])]
        elif kind == "path_points":
            points = [(p[0], p[1]) for p in g.get("points", [])]
        elif kind == "text":
            points = [(g["x"], g["y"])]
        for px, py in points:
            if px < min_x:
                min_x = px
            if px > max_x:
                max_x = px
            if py < min_y:
                min_y = py
            if py > max_y:
                max_y = py
    if min_x == float("inf"):
        return None
    return [min_x, min_y, max_x, max_y]


def apply_import_transform(
    geoms: list[dict],
    s: float,
    bx: float,
    by: float,
) -> list[dict]:
    """Bake an underlay's stored import transform into geometry dicts.

    Applies the base-point shift then the uniform import scale
    (``coord -> (coord - base) * s``) to every geometric field of each
    geometry dict, returning new dicts (the input is not mutated).

    This is the single home for a transform that was previously inlined —
    byte-identically — in four ``model_space`` sites
    (``_commit_place_import``, ``_on_dxf_finished``, ``_import_pdf_vectors``,
    ``_load_underlay_from_cache``). Extracting it fixed a text bug: the text
    branch scaled ``x``/``y``/``size`` but forgot ``twidth`` (the source span
    width the substitute font is x-scaled to), so PDF text rendered with the
    wrong horizontal fit on the canvas at architectural import scales while
    the raw-rendered import preview looked correct.

    Args:
        geoms: Geometry dicts from the DXF/PDF extraction pipeline (raw,
            pre-transform coordinates).
        s: Import scale (``real_mm / source_units``).
        bx: Base-point X (subtracted before scaling).
        by: Base-point Y (subtracted before scaling).

    Returns:
        A new list of transformed geometry dicts. When ``s == 1`` and the
        base point is the origin the returned dicts equal the inputs.
    """
    out: list[dict] = []
    for g in geoms:
        kind = g.get("kind")
        t = dict(g)
        if kind == "line":
            t["x1"] = (g["x1"] - bx) * s
            t["y1"] = (g["y1"] - by) * s
            t["x2"] = (g["x2"] - bx) * s
            t["y2"] = (g["y2"] - by) * s
        elif kind in ("circle", "arc"):
            xk = "x" if kind == "circle" else "rx"
            yk = "y" if kind == "circle" else "ry"
            wk = "w" if kind == "circle" else "rw"
            hk = "h" if kind == "circle" else "rh"
            t[xk] = (g[xk] - bx) * s
            t[yk] = (g[yk] - by) * s
            t[wk] = g[wk] * s
            t[hk] = g[hk] * s
        elif kind == "ellipse_full":
            t["pos_cx"] = (g["pos_cx"] - bx) * s
            t["pos_cy"] = (g["pos_cy"] - by) * s
            t["x"] = g["x"] * s
            t["y"] = g["y"] * s
            t["w"] = g["w"] * s
            t["h"] = g["h"] * s
        elif kind == "path_points":
            t["points"] = [((p[0] - bx) * s, (p[1] - by) * s)
                           for p in g["points"]]
        elif kind == "text":
            t["x"] = (g["x"] - bx) * s
            t["y"] = (g["y"] - by) * s
            if "size" in g:
                t["size"] = g["size"] * s
            # twidth is the on-paper source span width the substitute font is
            # x-scaled to; it lives in the same coordinate space as size, so it
            # MUST scale with s or the text's horizontal fit breaks.
            if g.get("twidth") is not None:
                t["twidth"] = g["twidth"] * s
        out.append(t)
    return out


def append_geom_to_path(path, g: dict) -> None:
    """Append a single geometry dict to a batched ``QPainterPath``.

    The single shared home for the geom->path builder that was previously
    duplicated (byte-equivalently) as ``_append_geom_to_path`` in
    ``model_space`` and ``underlay_import_dialog``. Batched underlay rendering
    uses one ``QPainterPath`` per DXF layer instead of one ``QGraphicsItem``
    per geometry (which freezes on large files).

    Handles the extraction-pipeline geom kinds ``line``, ``circle``, ``arc``,
    ``ellipse_full``, ``path_points`` and ``text``. Unknown kinds are ignored.

    Text is rendered DPI-independently and fractional-exact: a fixed pixel em
    (``_BASE``) is scaled by ``size/_BASE`` (point sizing would inflate by the
    screen-DPI/72 factor and rounding a pixel size would lose sub-point
    accuracy). When a source span width (``twidth``) is known for a single
    line, the substitute font is x-scaled to fit it so no substitute-font
    drift creeps in. ``valign`` follows the PDF span convention (3 == baseline,
    i.e. ``y`` is the span origin).

    Args:
        path: The ``QPainterPath`` to append to (mutated in place).
        g: A geometry dict from the DXF/PDF extraction pipeline.
    """
    # Imported lazily so this pure-geometry module stays Qt-free at import time
    # (it is also used from non-GUI conversion paths).
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QFont, QFontMetricsF, QPainterPath, QTransform

    from .theme import FONT_UI

    kind = g.get("kind")
    if kind == "line":
        path.moveTo(g["x1"], g["y1"])
        path.lineTo(g["x2"], g["y2"])
    elif kind == "circle":
        path.addEllipse(g["x"], g["y"], g["w"], g["h"])
    elif kind == "arc":
        rect = QRectF(g["rx"], g["ry"], g["rw"], g["rh"])
        path.arcMoveTo(rect, g["start"])
        path.arcTo(rect, g["start"], g["span"])
    elif kind == "ellipse_full":
        path.addEllipse(
            g["pos_cx"] + g["x"], g["pos_cy"] + g["y"],
            g["w"], g["h"])
    elif kind == "path_points":
        pts = g["points"]
        if len(pts) < 2:
            return
        path.moveTo(pts[0][0], pts[0][1])
        for p in pts[1:]:
            path.lineTo(p[0], p[1])
        if g.get("closed") and len(pts) >= 3:
            path.closeSubpath()
    elif kind == "text":
        txt = g.get("text", "")
        if txt:
            # DPI-independent + fractional-exact size: render at a fixed
            # pixel em, then scale by size/BASE. (Point size would inflate by
            # 96/72 + HiDPI; rounding a pixel size loses sub-point accuracy.)
            size = max(0.5, float(g.get("size", 6)))
            _BASE = 100.0
            f = QFont(FONT_UI)
            f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            f.setPixelSize(int(_BASE))
            sc = size / _BASE
            tx, ty = g["x"], g["y"]
            ha = g.get("halign", 0)
            va = g.get("valign", 3)
            twidth = g.get("twidth")
            lines = txt.split("\n")
            single = len(lines) == 1
            fm = QFontMetricsF(f)
            line_h = fm.height() * sc
            total_h = line_h * len(lines)
            # Vertical anchor for the text block
            if va == 0:       # top
                base_y = ty + fm.ascent() * sc
            elif va == 1:     # middle
                base_y = ty + fm.ascent() * sc - total_h / 2
            elif va == 2:     # bottom
                base_y = ty + fm.ascent() * sc - total_h
            else:             # baseline (PDF spans: y == span origin)
                base_y = ty
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                nat_w = fm.horizontalAdvance(line)   # at BASE px
                # fit x to the source span width when known, else scale = size
                sx = (twidth / nat_w) if (twidth and nat_w > 0 and single) else sc
                final_w = nat_w * sx
                lx = tx
                if ha == 1:   # center
                    lx -= final_w / 2
                elif ha == 2: # right
                    lx -= final_w
                tmp = QPainterPath()
                tmp.addText(0.0, 0.0, f, line)
                tr = QTransform()
                tr.translate(lx, base_y + i * line_h)
                tr.scale(sx, sc)
                path.addPath(tr.map(tmp))


def filter_geoms_by_bounds(
    geoms: list[dict],
    bounds: list[tuple[float, float, float, float]] | None,
) -> list[dict]:
    """Filter geometry dicts to those within any viewport bounds.

    Args:
        geoms: List of geometry dicts from the DXF extraction pipeline.
        bounds: Viewport bounds from :func:`get_viewport_bounds`, or
            ``None`` to return all geometry unchanged.

    Returns:
        Filtered list of geometry dicts.
    """
    if bounds is None:
        return geoms

    filtered = []
    for g in geoms:
        if _geom_in_any_bound(g, bounds):
            filtered.append(g)
    return filtered


def _geom_in_any_bound(
    g: dict,
    bounds: list[tuple[float, float, float, float]],
) -> bool:
    """Check if any representative point of a geometry dict falls
    within any of the bounding boxes."""
    kind = g.get("kind")
    points: list[tuple[float, float]] = []

    if kind == "line":
        points = [(g["x1"], g["y1"]), (g["x2"], g["y2"])]
    elif kind == "circle":
        # Center of the bounding rect
        points = [(g["x"] + g["w"] / 2, g["y"] + g["h"] / 2)]
    elif kind == "arc":
        points = [(g["rx"] + g["rw"] / 2, g["ry"] + g["rh"] / 2)]
    elif kind == "ellipse_full":
        points = [(g["pos_cx"], g["pos_cy"])]
    elif kind == "path_points":
        points = [(p[0], p[1]) for p in g.get("points", [])]
    elif kind == "text":
        points = [(g["x"], g["y"])]

    for bx0, by0, bx1, by1 in bounds:
        # Normalise in case min/max are swapped from Y negation
        if by0 > by1:
            by0, by1 = by1, by0
        for px, py in points:
            if bx0 <= px <= bx1 and by0 <= py <= by1:
                return True
    return False


def extract_layout_entities(
    dxf_path: str = "", layout_name: str = "", doc=None,
) -> list[dict]:
    """Extract paper-layout entities transformed to model-space coordinates.

    Paper-space layouts contain annotations (gridline bubbles, title
    block, notes) positioned at sheet scale.  This function reads them,
    runs them through the geometry extractor, and transforms the
    resulting coordinates into model space using the viewport mapping so
    they align with viewport-filtered model-space geometry.

    Args:
        dxf_path: Path to the converted DXF file (ignored if *doc* given).
        layout_name: Name of the paper-space layout.
        doc: Pre-read ezdxf document from :func:`read_dxf`.

    Returns:
        List of geometry dicts in model-space coordinates (Y negated),
        or an empty list on any error.
    """
    if layout_name == "Model":
        return []

    if doc is None:
        doc = read_dxf(dxf_path)
    if doc is None:
        return []

    try:
        layout = doc.layouts.get(layout_name)
    except Exception:
        return []

    # Find the main viewport (id != 1) to get the transform
    vp_paper_cx = vp_paper_cy = 0.0
    vp_model_cx = vp_model_cy = 0.0
    ps_to_ms = 1.0
    found_vp = False

    for ent in layout:
        if ent.dxftype() != "VIEWPORT":
            continue
        if ent.dxf.get("id", 0) == 1:
            continue
        try:
            pc = ent.dxf.center
            mc = ent.dxf.view_center_point
            vh = ent.dxf.view_height
            vhp = ent.dxf.height
            if vh <= 0 or vhp <= 0:
                continue
            vp_paper_cx, vp_paper_cy = float(pc[0]), float(pc[1])
            vp_model_cx, vp_model_cy = float(mc[0]), float(mc[1])
            ps_to_ms = vh / vhp
            found_vp = True
            break  # use first real viewport
        except AttributeError:
            continue

    if not found_vp:
        return []

    # Extract geometry from layout entities (exclude viewports)
    from .dxf_import_worker import DxfImportWorker, _build_layer_colors
    worker = DxfImportWorker.__new__(DxfImportWorker)
    worker._cancelled = False
    worker._layer_colors = _build_layer_colors(doc)

    raw_geoms = []
    for ent in layout:
        if ent.dxftype() in ("VIEWPORT", "OLE2FRAME"):
            continue
        try:
            g = worker._extract_geometry(ent)
            if g is not None:
                if isinstance(g, list):
                    raw_geoms.extend(g)
                else:
                    raw_geoms.append(g)
        except Exception:
            pass

    if not raw_geoms:
        return []

    # Transform paper-space coordinates to model-space coordinates.
    # The extractor already negated Y, so we work in negated-Y space.
    # Paper-space Y was also negated by the extractor, so:
    #   model_x = (paper_x - vp_paper_cx) * ps_to_ms + vp_model_cx
    #   model_y_neg = (paper_y_neg - (-vp_paper_cy)) * ps_to_ms + (-vp_model_cy)
    #              = (paper_y_neg + vp_paper_cy) * ps_to_ms - vp_model_cy
    def _tx(px: float) -> float:
        return (px - vp_paper_cx) * ps_to_ms + vp_model_cx

    def _ty(py_neg: float) -> float:
        return (py_neg + vp_paper_cy) * ps_to_ms - vp_model_cy

    transformed = []
    for g in raw_geoms:
        t = dict(g)
        kind = g.get("kind")
        if kind == "line":
            t["x1"] = _tx(g["x1"]); t["y1"] = _ty(g["y1"])
            t["x2"] = _tx(g["x2"]); t["y2"] = _ty(g["y2"])
        elif kind == "circle":
            cx_old = g["x"] + g["w"] / 2
            cy_old = g["y"] + g["h"] / 2
            new_cx = _tx(cx_old)
            new_cy = _ty(cy_old)
            new_w = g["w"] * ps_to_ms
            new_h = g["h"] * ps_to_ms
            t["x"] = new_cx - new_w / 2
            t["y"] = new_cy - new_h / 2
            t["w"] = new_w; t["h"] = new_h
        elif kind == "arc":
            cx_old = g["rx"] + g["rw"] / 2
            cy_old = g["ry"] + g["rh"] / 2
            new_cx = _tx(cx_old)
            new_cy = _ty(cy_old)
            new_w = g["rw"] * ps_to_ms
            new_h = g["rh"] * ps_to_ms
            t["rx"] = new_cx - new_w / 2
            t["ry"] = new_cy - new_h / 2
            t["rw"] = new_w; t["rh"] = new_h
        elif kind == "path_points":
            t["points"] = [(_tx(p[0]), _ty(p[1])) for p in g["points"]]
        elif kind == "text":
            t["x"] = _tx(g["x"]); t["y"] = _ty(g["y"])
            if "size" in g:
                t["size"] = g["size"] * ps_to_ms
        elif kind == "ellipse_full":
            t["pos_cx"] = _tx(g["pos_cx"])
            t["pos_cy"] = _ty(g["pos_cy"])
            t["w"] = g["w"] * ps_to_ms
            t["h"] = g["h"] * ps_to_ms
            t["x"] = g["x"] * ps_to_ms
            t["y"] = g["y"] * ps_to_ms
        else:
            continue
        transformed.append(t)

    return transformed
