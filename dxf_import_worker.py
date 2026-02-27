"""
DXF Import Worker
=================
Runs the heavy DXF parsing on a background thread so the UI stays responsive.
Emits plain Python geometry dicts — NO Qt GUI objects are created here.
QGraphicsItems are built on the main thread after the signal is received.
"""

import math
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import ezdxf
except ImportError:
    ezdxf = None

from dxf_import_dialog import _sanitize_dxf
import os


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

    def __init__(self, file_path: str, layers: list | None = None, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.layers = layers
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

            try:
                geom = self._extract_geometry(entity)
                if geom is not None:
                    geometries.append(geom)
            except Exception:
                skipped += 1

            # Emit progress every 500 entities (avoids signal spam)
            if i % 500 == 0 or i == total - 1:
                self.progress.emit(i + 1, total)

        if skipped > 0:
            self.status.emit(f"Done — {len(geometries)} geometries, {skipped} skipped")
        else:
            self.status.emit(f"Done — {len(geometries)} geometries")

        self.finished_data.emit(geometries)

    # ─────────────────────────────────────────────────────────────────
    # Geometry extraction — returns plain dicts, no Qt objects
    # ─────────────────────────────────────────────────────────────────

    def _extract_geometry(self, entity) -> dict | None:
        etype = entity.dxftype()
        layer = entity.dxf.get("layer", "0") if hasattr(entity.dxf, "get") else "0"

        if etype == "LINE":
            return {
                "kind": "line", "layer": layer,
                "x1": entity.dxf.start[0], "y1": -entity.dxf.start[1],
                "x2": entity.dxf.end[0],   "y2": -entity.dxf.end[1],
            }

        elif etype == "CIRCLE":
            r = entity.dxf.radius
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            return {"kind": "circle", "layer": layer, "x": cx - r, "y": -cy - r, "w": 2 * r, "h": 2 * r}

        elif etype == "ARC":
            cx, cy = entity.dxf.center.x, entity.dxf.center.y
            r = entity.dxf.radius
            start_angle = entity.dxf.start_angle
            end_angle = entity.dxf.end_angle
            qt_start = -start_angle
            qt_end = -end_angle
            span = qt_end - qt_start
            if span > 0:
                span -= 360
            return {
                "kind": "arc", "layer": layer,
                "rx": cx - r, "ry": -cy - r, "rw": 2 * r, "rh": 2 * r,
                "start": qt_start, "span": span,
            }

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
                    "kind": "ellipse_full", "layer": layer,
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
                return {"kind": "path_points", "layer": layer, "points": points, "closed": False}

        elif etype in ("LWPOLYLINE", "POLYLINE"):
            pts = list(entity.get_points())
            if len(pts) < 2:
                return None
            closed = bool(hasattr(entity.dxf, "flags") and entity.dxf.flags & 1)
            return {
                "kind": "path_points", "layer": layer,
                "points": [(pt[0], -pt[1]) for pt in pts],
                "closed": closed,
            }

        elif etype == "SPLINE":
            pts = list(entity.flattening(0.5))
            if not pts:
                return None
            return {
                "kind": "path_points", "layer": layer,
                "points": [(pt.x, -pt.y) for pt in pts],
                "closed": False,
            }

        elif etype == "TEXT":
            pos = entity.dxf.insert
            return {"kind": "text", "layer": layer, "x": pos[0], "y": -pos[1], "text": entity.dxf.text}

        elif etype == "MTEXT":
            plain = entity.plain_text() if hasattr(entity, "plain_text") else entity.text
            insert = entity.dxf.insert
            return {"kind": "text", "layer": layer, "x": insert.x, "y": -insert.y, "text": plain}

        return None
