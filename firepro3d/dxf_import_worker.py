"""
DXF Import Worker
=================
Runs the heavy DXF parsing on a background thread so the UI stays responsive.
Emits plain Python geometry dicts — NO Qt GUI objects are created here.
QGraphicsItems are built on the main thread after the signal is received.
"""

import math
import os
import tempfile

from PyQt6.QtCore import QThread, pyqtSignal

try:
    import ezdxf
    from ezdxf.colors import DXF_DEFAULT_COLORS
    from ezdxf.enums import TextEntityAlignment
    from ezdxf.upright import upright
except ImportError:
    ezdxf = None
    DXF_DEFAULT_COLORS = None
    TextEntityAlignment = None
    upright = None


# ── Text alignment mappings ─────────────────────────────────────────────────
# halign: 0=left, 1=center, 2=right
# valign: 0=top, 1=middle, 2=bottom, 3=baseline (default)

def _text_align_to_hv(align) -> tuple[int, int]:
    """Map ezdxf TextEntityAlignment → (halign, valign) for rendering."""
    if TextEntityAlignment is None:
        return (0, 3)
    _MAP = {
        TextEntityAlignment.LEFT:           (0, 3),
        TextEntityAlignment.CENTER:         (1, 3),
        TextEntityAlignment.RIGHT:          (2, 3),
        TextEntityAlignment.ALIGNED:        (1, 3),
        TextEntityAlignment.MIDDLE:         (1, 1),
        TextEntityAlignment.FIT:            (1, 3),
        TextEntityAlignment.BOTTOM_LEFT:    (0, 2),
        TextEntityAlignment.BOTTOM_CENTER:  (1, 2),
        TextEntityAlignment.BOTTOM_RIGHT:   (2, 2),
        TextEntityAlignment.MIDDLE_LEFT:    (0, 1),
        TextEntityAlignment.MIDDLE_CENTER:  (1, 1),
        TextEntityAlignment.MIDDLE_RIGHT:   (2, 1),
        TextEntityAlignment.TOP_LEFT:       (0, 0),
        TextEntityAlignment.TOP_CENTER:     (1, 0),
        TextEntityAlignment.TOP_RIGHT:      (2, 0),
    }
    return _MAP.get(align, (0, 3))


def _mtext_attach_to_hv(attachment_point: int) -> tuple[int, int]:
    """Map MTEXT attachment_point (1-9) → (halign, valign).

    Attachment points are arranged like a numpad:
    1=TL, 2=TC, 3=TR, 4=ML, 5=MC, 6=MR, 7=BL, 8=BC, 9=BR
    """
    _H = {1: 0, 2: 1, 3: 2, 4: 0, 5: 1, 6: 2, 7: 0, 8: 1, 9: 2}
    _V = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 1, 7: 2, 8: 2, 9: 2}
    return (_H.get(attachment_point, 0), _V.get(attachment_point, 0))


def _aci_to_hex(aci: int) -> str:
    """Convert an AutoCAD Color Index (1–255) to a ``#rrggbb`` hex string."""
    if DXF_DEFAULT_COLORS is not None and 0 < aci < len(DXF_DEFAULT_COLORS):
        val = DXF_DEFAULT_COLORS[aci]
        return f"#{(val >> 16) & 0xFF:02x}{(val >> 8) & 0xFF:02x}{val & 0xFF:02x}"
    return "#ffffff"


def _build_layer_colors(doc) -> dict[str, str]:
    """Return ``{layer_name: '#rrggbb'}`` from the DXF layer table."""
    layer_colors: dict[str, str] = {}
    try:
        for layer in doc.layers:
            name = layer.dxf.name
            # True-color on layer takes priority
            if layer.dxf.hasattr("true_color"):
                tc = layer.dxf.true_color
                layer_colors[name] = (
                    f"#{(tc >> 16) & 0xFF:02x}{(tc >> 8) & 0xFF:02x}"
                    f"{tc & 0xFF:02x}")
            else:
                aci = layer.dxf.get("color", 7)
                if 0 < aci < 256:
                    layer_colors[name] = _aci_to_hex(aci)
    except Exception:
        pass
    return layer_colors


def _resolve_entity_color(entity, layer_colors: dict[str, str]) -> str:
    """Resolve an entity's display colour to ``#rrggbb``.

    Priority: true_color → ACI (1-255) → BYLAYER (256) → fallback white.
    Never raises — returns ``#ffffff`` on any failure.
    """
    try:
        # 1) True-color RGB override
        if entity.dxf.hasattr("true_color"):
            tc = entity.dxf.true_color
            return (f"#{(tc >> 16) & 0xFF:02x}{(tc >> 8) & 0xFF:02x}"
                    f"{tc & 0xFF:02x}")

        aci = entity.dxf.get("color", 256)  # default = BYLAYER

        # 2) Explicit ACI colour
        if 0 < aci < 256:
            return _aci_to_hex(aci)

        # 3) BYLAYER (256) — look up from layer table
        layer_name = entity.dxf.get("layer", "0")
        return layer_colors.get(layer_name, "#ffffff")
    except Exception:
        return "#ffffff"


# ─────────────────────────────────────────────────────────────────────────────
# DXF sanitiser (moved here from the deleted dxf_import_dialog.py)
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_dxf(file_path: str) -> str:
    """
    Some DXF files have stray whitespace, BOM markers, or \\r\\r\\n line
    endings that confuse ezdxf's parser.  This reads the file, cleans up
    the line endings, strips trailing whitespace from every line, and
    writes a temp copy that ezdxf can parse.

    Returns the path to the cleaned temp file (caller should delete when done),
    or the original path if no cleaning was needed.
    """
    try:
        raw = open(file_path, "rb").read()
    except Exception:
        return file_path

    # Strip BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]

    # Normalise line endings to plain \\n
    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").decode("utf-8", errors="replace")

    # Strip trailing whitespace on each line (stray spaces/tabs after group codes)
    lines = [line.rstrip() for line in text.split("\n")]
    cleaned = "\n".join(lines)

    # Write to a temp file
    fd, tmp_path = tempfile.mkstemp(suffix=".dxf")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(cleaned)
    return tmp_path


def _entity_in_viewport(ent, bounds) -> bool:
    """Check if a DXF entity falls within viewport bounds.

    INSERT/HATCH/DIMENSION always pass since their explosion produces
    geometry at unpredictable locations.
    """
    etype = ent.dxftype()
    if etype in ("INSERT", "HATCH", "DIMENSION"):
        return True
    try:
        if etype == "LINE":
            pts = [(ent.dxf.start[0], -ent.dxf.start[1]),
                   (ent.dxf.end[0], -ent.dxf.end[1])]
        elif etype in ("CIRCLE", "ARC"):
            c = ent.dxf.center
            pts = [(c.x, -c.y)]
        elif etype == "ELLIPSE":
            c = ent.dxf.center
            pts = [(c.x, -c.y)]
        elif etype in ("LWPOLYLINE", "POLYLINE"):
            pts = [(p[0], -p[1]) for p in ent.get_points()]
        elif etype == "SPLINE":
            pts = [(cp[0], -cp[1]) for cp in ent.control_points]
        elif etype in ("TEXT", "MTEXT"):
            ins = ent.dxf.insert
            pts = [(ins[0], -ins[1])]
        else:
            return True
    except (AttributeError, IndexError, TypeError):
        return True
    if not pts:
        return True
    for bx0, by0, bx1, by1 in bounds:
        if by0 > by1:
            by0, by1 = by1, by0
        for px, py in pts:
            if bx0 <= px <= bx1 and by0 <= py <= by1:
                return True
    return False


class DxfImportWorker(QThread):
    """
    Parses a DXF file and extracts geometry descriptors off the main thread.

    Signals
    -------
    progress(int, int)   — (current, total) entity counts
    status(str)          — status message for the dialog
    finished_data(list)  — list of geometry dicts ready for item creation
    error(str)           — error message if import fails
    """
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished_data = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, file_path: str, layers: list | None = None,
                 layout: str = "", parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.layers = layers
        self.layout = layout
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if ezdxf is None:
            self.error.emit("ezdxf is not installed")
            return

        # ── Sanitize and open ────────────────────────────────────────
        self.status.emit("Cleaning DXF file…")
        clean_path = _sanitize_dxf(self.file_path)

        try:
            self.status.emit("Reading DXF…")
            doc = ezdxf.readfile(clean_path)
            msp = doc.modelspace()
        except Exception as e:
            self.error.emit(f"Failed to load DXF: {e}")
            return
        finally:
            if clean_path != self.file_path and os.path.exists(clean_path):
                os.remove(clean_path)

        # ── Viewport bounds (paper layouts only) ────────────────────
        vp_bounds = None
        if self.layout and self.layout != "Model":
            from .dwg_converter import get_viewport_bounds
            vp_bounds = get_viewport_bounds(
                layout_name=self.layout, doc=doc)

        # ── Build layer colour map ──────────────────────────────────
        self._layer_colors = _build_layer_colors(doc)

        # ── Collect entities to process ──────────────────────────────
        self.status.emit("Counting entities…")
        all_entities = list(msp)
        total = len(all_entities)
        self.status.emit(f"Processing {total} entities…")

        geometries = []
        skipped = 0

        for i, entity in enumerate(all_entities):
            if self._cancelled:
                self.status.emit("Cancelled")
                return

            # Layer filter
            if self.layers is not None:
                entity_layer = entity.dxf.get("layer", "0") if hasattr(entity.dxf, "get") else "0"
                if entity_layer not in self.layers:
                    continue

            # Pre-filter by viewport bounds at entity level
            if vp_bounds and not _entity_in_viewport(entity, vp_bounds):
                continue

            try:
                result = self._extract_geometry(entity)
                if result is not None:
                    if isinstance(result, list):
                        geometries.extend(result)
                    else:
                        geometries.append(result)
            except Exception:
                skipped += 1

            # Emit progress every 500 entities (avoids signal spam)
            if i % 500 == 0 or i == total - 1:
                self.progress.emit(i + 1, total)

        # ── Post-extraction viewport filter ─────────────────────────
        if vp_bounds:
            from .dwg_converter import filter_geoms_by_bounds
            geometries = filter_geoms_by_bounds(geometries, vp_bounds)

        # ── Paper layout annotations ────────────────────────────────
        if self.layout and self.layout != "Model":
            from .dwg_converter import extract_layout_entities
            layout_geoms = extract_layout_entities(
                layout_name=self.layout, doc=doc)
            if layout_geoms:
                geometries.extend(layout_geoms)

        if skipped > 0:
            self.status.emit(f"Done — {len(geometries)} geometries, {skipped} skipped")
        else:
            self.status.emit(f"Done — {len(geometries)} geometries")

        self.finished_data.emit(geometries)

    # ─────────────────────────────────────────────────────────────────
    # Synchronous extraction (for cache population on save)
    # ─────────────────────────────────────────────────────────────────

    @classmethod
    def extract_file_sync(cls, file_path: str,
                          layers: list[str] | None = None,
                          layout: str = "") -> list[dict]:
        """Synchronous geometry extraction for cache population.

        Same logic as ``run()`` but without threading or progress signals.
        When *layout* names a paper layout, applies viewport filtering
        and merges paper-layout annotations.
        """
        clean_path = _sanitize_dxf(file_path)
        try:
            doc = ezdxf.readfile(clean_path)
            msp = doc.modelspace()
        finally:
            if clean_path != file_path and os.path.exists(clean_path):
                os.remove(clean_path)

        # Viewport bounds for paper layouts
        vp_bounds = None
        if layout and layout != "Model":
            from .dwg_converter import get_viewport_bounds
            vp_bounds = get_viewport_bounds(
                layout_name=layout, doc=doc)

        worker = cls(file_path, layers, layout=layout)
        worker._layer_colors = _build_layer_colors(doc)
        geoms = []
        for entity in msp:
            if layers is not None:
                entity_layer = (entity.dxf.get("layer", "0")
                                if hasattr(entity.dxf, "get") else "0")
                if entity_layer not in layers:
                    continue
            if vp_bounds and not _entity_in_viewport(entity, vp_bounds):
                continue
            try:
                result = worker._extract_geometry(entity)
                if result is not None:
                    if isinstance(result, list):
                        geoms.extend(result)
                    else:
                        geoms.append(result)
            except Exception:
                pass

        # Post-filter + paper annotations
        if vp_bounds:
            from .dwg_converter import filter_geoms_by_bounds
            geoms = filter_geoms_by_bounds(geoms, vp_bounds)
        if layout and layout != "Model":
            from .dwg_converter import extract_layout_entities
            layout_geoms = extract_layout_entities(
                layout_name=layout, doc=doc)
            if layout_geoms:
                geoms.extend(layout_geoms)

        return geoms

    # ─────────────────────────────────────────────────────────────────
    # Geometry extraction — returns plain dicts, no Qt objects
    # ─────────────────────────────────────────────────────────────────

    def _extract_geometry(self, entity) -> dict | None:
        etype = entity.dxftype()

        # Fix OCS (Object Coordinate System) → WCS before reading coords.
        # Only for simple entities — calling upright() on composite entities
        # (INSERT/DIMENSION/HATCH) corrupts their transform and breaks
        # virtual_entities().  Sub-entities get upright() via recursion.
        _COMPOSITE = ("INSERT", "DIMENSION", "HATCH",
                      "LEADER", "MULTILEADER", "MLEADER")
        if (upright is not None and etype not in _COMPOSITE):
            try:
                upright(entity)
            except Exception:
                pass
        layer = entity.dxf.get("layer", "0") if hasattr(entity.dxf, "get") else "0"
        lc = getattr(self, "_layer_colors", {})
        color = _resolve_entity_color(entity, lc)

        if etype == "LINE":
            return {
                "kind": "line", "layer": layer, "color": color,
                "x1": entity.dxf.start[0], "y1": -entity.dxf.start[1],
                "x2": entity.dxf.end[0],   "y2": -entity.dxf.end[1],
            }

        elif etype == "CIRCLE":
            r = entity.dxf.radius
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            return {"kind": "circle", "layer": layer, "color": color,
                    "x": cx - r, "y": -cy - r, "w": 2 * r, "h": 2 * r}

        elif etype == "ARC":
            # Convert arc to polyline points to avoid angle-convention
            # mismatches between DXF, QGraphicsEllipseItem, and
            # QPainterPath.arcTo (which disagree on Y-flip semantics).
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            start_deg = entity.dxf.start_angle
            end_deg = entity.dxf.end_angle
            # DXF arcs go CCW from start to end
            sweep = end_deg - start_deg
            if sweep <= 0:
                sweep += 360
            steps = max(16, int(sweep / 2))
            points = []
            for i in range(steps + 1):
                a = math.radians(start_deg + sweep * i / steps)
                points.append((cx + r * math.cos(a), -(cy + r * math.sin(a))))
            return {"kind": "path_points", "layer": layer, "color": color,
                    "points": points, "closed": False}

        elif etype == "ELLIPSE":
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            mx, my = entity.dxf.major_axis.x, entity.dxf.major_axis.y
            ratio = entity.dxf.ratio
            major_len = math.hypot(mx, my)
            minor_len = major_len * ratio
            rotation = math.degrees(math.atan2(my, mx))
            start_param = entity.dxf.get("start_param", 0.0)
            end_param = entity.dxf.get("end_param", math.tau)
            is_full = math.isclose(abs(end_param - start_param), math.tau, rel_tol=1e-3)

            if is_full:
                return {
                    "kind": "ellipse_full", "layer": layer, "color": color,
                    "x": -major_len, "y": -minor_len, "w": 2 * major_len, "h": 2 * minor_len,
                    "pos_cx": cx, "pos_cy": -cy, "rotation": -rotation,
                }
            else:
                param_range = end_param - start_param
                if param_range < 0:
                    param_range += math.tau
                rad = math.radians(rotation)
                cos_r, sin_r = math.cos(rad), math.sin(rad)
                points = []
                steps = 64
                for i in range(steps + 1):
                    t = start_param + param_range * (i / steps)
                    px = major_len * math.cos(t)
                    py = minor_len * math.sin(t)
                    rx = px * cos_r - py * sin_r + cx
                    ry = -(px * sin_r + py * cos_r + cy)
                    points.append((rx, ry))
                return {"kind": "path_points", "layer": layer, "color": color,
                        "points": points, "closed": False}

        elif etype in ("LWPOLYLINE", "POLYLINE"):
            if hasattr(entity, "get_points"):
                pts = list(entity.get_points())
            else:
                # POLYLINE (3D) uses .vertices instead of .get_points()
                pts = [(v.dxf.location.x, v.dxf.location.y)
                       for v in entity.vertices]
            if len(pts) < 2:
                return None
            closed = bool(hasattr(entity.dxf, "flags") and entity.dxf.flags & 1)
            return {
                "kind": "path_points", "layer": layer, "color": color,
                "points": [(pt[0], -pt[1]) for pt in pts],
                "closed": closed,
            }

        elif etype == "SPLINE":
            pts = list(entity.flattening(0.5))
            if not pts:
                return None
            return {
                "kind": "path_points", "layer": layer, "color": color,
                "points": [(pt.x, -pt.y) for pt in pts],
                "closed": False,
            }

        elif etype in ("TEXT", "ATTRIB", "ATTDEF"):
            text_str = entity.dxf.get("text", "")
            if not text_str or not text_str.strip():
                return None
            # get_placement() returns (align_enum, p1, p2) — p1 is the
            # correct reference position for any alignment.
            try:
                align, p1, _p2 = entity.get_placement()
                pos = p1
                ha, va = _text_align_to_hv(align)
            except Exception:
                pos = entity.dxf.insert
                ha, va = 0, 3  # left-baseline
            result = {"kind": "text", "layer": layer, "color": color,
                      "x": pos[0], "y": -pos[1], "text": text_str}
            height = entity.dxf.get("height", 0)
            if height > 0:
                result["size"] = height
            rotation = entity.dxf.get("rotation", 0)
            if rotation:
                result["rotation"] = -rotation  # DXF CCW → Qt CW
            if ha != 0 or va != 3:
                result["halign"] = ha
                result["valign"] = va
            return result

        elif etype == "MTEXT":
            plain = entity.plain_text() if hasattr(entity, "plain_text") else entity.text
            if not plain or not plain.strip():
                return None
            insert = entity.dxf.insert
            result = {"kind": "text", "layer": layer, "color": color,
                      "x": insert.x, "y": -insert.y, "text": plain}
            height = entity.dxf.get("char_height", 0)
            if height > 0:
                result["size"] = height
            rotation = entity.dxf.get("rotation", 0)
            if rotation:
                result["rotation"] = -rotation
            ap = entity.dxf.get("attachment_point", 1)
            ha, va = _mtext_attach_to_hv(ap)
            # Always set for MTEXT — its default (top-left) differs
            # from TEXT default (baseline-left), so the renderer
            # must know which convention applies.
            result["halign"] = ha
            result["valign"] = va
            return result

        elif etype in ("INSERT", "DIMENSION", "HATCH",
                       "LEADER", "MULTILEADER", "MLEADER"):
            # Explode block references, dimensions, hatches, and leaders
            # into constituent geometry via ezdxf's virtual_entities().
            results = []
            try:
                sub_entities = list(entity.virtual_entities())
            except Exception:
                sub_entities = []
            for sub_entity in sub_entities:
                try:
                    sub_geom = self._extract_geometry(sub_entity)
                    if sub_geom is not None:
                        if isinstance(sub_geom, list):
                            results.extend(sub_geom)
                        else:
                            results.append(sub_geom)
                except Exception:
                    pass
            # INSERT blocks have ATTRIB text not included in
            # virtual_entities() — extract separately.
            if etype == "INSERT" and hasattr(entity, "attribs"):
                try:
                    for attrib in entity.attribs:
                        if getattr(attrib, "is_invisible", False):
                            continue
                        attrib_geom = self._extract_geometry(attrib)
                        if attrib_geom is not None:
                            if isinstance(attrib_geom, list):
                                results.extend(attrib_geom)
                            else:
                                results.append(attrib_geom)
                except Exception:
                    pass
            return results if results else None

        elif etype == "SOLID":
            # SOLID is a filled triangle or quadrilateral.
            try:
                pts = [entity.dxf.vtx0, entity.dxf.vtx1,
                       entity.dxf.vtx2]
                # vtx3 may equal vtx2 for triangles
                v3 = entity.dxf.get("vtx3", None)
                if v3 is not None and (v3.x != pts[2].x or v3.y != pts[2].y):
                    pts.append(v3)
                return {
                    "kind": "path_points", "layer": layer, "color": color,
                    "points": [(p.x, -p.y) for p in pts],
                    "closed": True,
                }
            except Exception:
                return None

        elif etype == "POINT":
            # Render as a tiny cross marker.
            try:
                px, py = entity.dxf.location.x, -entity.dxf.location.y
                d = 0.5  # half-size in drawing units
                return [
                    {"kind": "line", "layer": layer, "color": color,
                     "x1": px - d, "y1": py, "x2": px + d, "y2": py},
                    {"kind": "line", "layer": layer, "color": color,
                     "x1": px, "y1": py - d, "x2": px, "y2": py + d},
                ]
            except Exception:
                return None

        return None
