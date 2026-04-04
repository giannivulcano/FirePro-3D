"""
auto_populate_dialog.py
=======================
Auto-populate a room with sprinklers based on NFPA 13 spacing rules.

Provides:
- NFPA 13 density/area curves and spacing limits
- Interactive density/area graph widget
- AutoPopulateDialog for configuration
- compute_sprinkler_grid() placement algorithm
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialogButtonBox, QLineEdit,
    QSizePolicy, QWidget, QSplitter,
)
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QPolygonF, QPainterPath,
    QFontMetrics,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal, QSettings, QByteArray

if TYPE_CHECKING:
    from .room import Room
    from .sprinkler_db import SprinklerDatabase, SprinklerRecord
    from .level_manager import LevelManager
    from .scale_manager import ScaleManager

# ─────────────────────────────────────────────────────────────────────────────
# NFPA 13 Data
# ─────────────────────────────────────────────────────────────────────────────

# Hazard classes (same order as room.py)
HAZARD_CLASSES = [
    "Light Hazard",
    "Ordinary Hazard Group 1",
    "Ordinary Hazard Group 2",
    "Extra Hazard Group 1",
    "Extra Hazard Group 2",
    "Miscellaneous Storage",
    "High Piled Storage",
]

# Max protection area per sprinkler (sq ft) — NFPA 13-2019
#
# Standard coverage pendent/upright (hydraulically calculated):
#   - Light Hazard:   Table 10.2.4.2.1(a) — max protection area varies
#                     between 12 m² and 20 m² (130–215 sq ft) depending on
#                     ceiling height and construction type.
#   - Ordinary Hazard: Table 10.2.4.2.1(b) — max protection area is 12 m²
#                     (130 sq ft).
#   - Extra Hazard:   max protection area 100 sq ft (9.3 m²).
#
# Note: These are for hydraulically calculated systems only.  Pipe-schedule
# systems have different (typically smaller) limits.
NFPA_MAX_COVERAGE: dict[str, float] = {
    "Light Hazard":             225.0,   # up to 20 m² per Table 10.2.4.2.1(a)
    "Ordinary Hazard Group 1":  130.0,   # 12 m² per Table 10.2.4.2.1(b)
    "Ordinary Hazard Group 2":  130.0,   # 12 m² per Table 10.2.4.2.1(b)
    "Extra Hazard Group 1":     100.0,
    "Extra Hazard Group 2":     100.0,
    "Miscellaneous Storage":    100.0,
    "High Piled Storage":       100.0,   # per NFPA 13 Ch. 16 / NFPA 230
}

# Max spacing — NFPA 13-2019
#
# Standard coverage pendent/upright (hydraulically calculated):
#   - Light Hazard:    4.6 m (15 ft) max spacing — Table 10.2.4.2.1(a)
#   - Ordinary Hazard: 4.6 m (15 ft) max spacing — Table 10.2.4.2.1(b)
#   - Extra Hazard:    4.6 m (15 ft) max spacing
#
# Obstructed ceilings reduce max spacing for Light Hazard to 12 ft (3.7 m).
# Spacing is generally 4.6 m across all hazard classes; the main variable
# between hazard classes is the max protection area, not the spacing itself.
NFPA_MAX_SPACING: dict[str, dict[str, float]] = {
    "Light Hazard":             {"Unobstructed": 15.0, "Obstructed": 12.0},
    "Ordinary Hazard Group 1":  {"Unobstructed": 15.0, "Obstructed": 15.0},
    "Ordinary Hazard Group 2":  {"Unobstructed": 15.0, "Obstructed": 15.0},
    "Extra Hazard Group 1":     {"Unobstructed": 15.0, "Obstructed": 15.0},
    "Extra Hazard Group 2":     {"Unobstructed": 15.0, "Obstructed": 15.0},
    "Miscellaneous Storage":    {"Unobstructed": 15.0, "Obstructed": 15.0},
    "High Piled Storage":       {"Unobstructed": 12.0, "Obstructed": 12.0},
}

# Sprinkler orientation compatibility per hazard class.
# Light/Ordinary: all types acceptable.
# Extra/Storage:  typically pendent or upright only (no sidewall/concealed).
HAZARD_SPRINKLER_TYPES: dict[str, list[str]] = {
    "Light Hazard":             ["Pendent", "Upright", "Sidewall", "Concealed"],
    "Ordinary Hazard Group 1":  ["Pendent", "Upright", "Sidewall", "Concealed"],
    "Ordinary Hazard Group 2":  ["Pendent", "Upright", "Sidewall"],
    "Extra Hazard Group 1":     ["Pendent", "Upright"],
    "Extra Hazard Group 2":     ["Pendent", "Upright"],
    "Miscellaneous Storage":    ["Pendent", "Upright"],
    "High Piled Storage":       ["Pendent", "Upright"],
}

# Min spacing (ft) — NFPA 13 Section 8.6.2.1
NFPA_MIN_SPACING_FT = 6.0

# Min distance from wall (inches) — NFPA 13 Section 8.6.2.5
NFPA_MIN_WALL_DIST_IN = 4.0

# Density / area curves — NFPA 13 Figure 11.2.3.1.1
# Each curve is a list of (area_sqft, density_gpm_per_sqft) points
DENSITY_AREA_CURVES: dict[str, list[tuple[float, float]]] = {
    # Each curve is a list of (area_sqft, density_gpm_per_sqft) endpoints.
    # NFPA 13 Figure 11.2.3.1.1 — standard occupancy curves only.
    "Light Hazard":             [(1500, 0.10), (3000, 0.07)],
    "Ordinary Hazard Group 1":  [(1500, 0.15), (4000, 0.10)],
    "Ordinary Hazard Group 2":  [(1500, 0.20), (4000, 0.15)],
    "Extra Hazard Group 1":     [(2500, 0.30), (5000, 0.20)],
    "Extra Hazard Group 2":     [(2500, 0.40), (5000, 0.30)],
}

# Curve display colors
_CURVE_COLORS: dict[str, str] = {
    "Light Hazard":             "#2196F3",
    "Ordinary Hazard Group 1":  "#4CAF50",
    "Ordinary Hazard Group 2":  "#FF9800",
    "Extra Hazard Group 1":     "#F44336",
    "Extra Hazard Group 2":     "#9C27B0",
}

# Short labels for legend
_CURVE_LABELS: dict[str, str] = {
    "Light Hazard":             "LH",
    "Ordinary Hazard Group 1":  "OH1",
    "Ordinary Hazard Group 2":  "OH2",
    "Extra Hazard Group 1":     "EH1",
    "Extra Hazard Group 2":     "EH2",
}

# Conversion constants
FT_TO_MM = 304.8
IN_TO_MM = 25.4
SQFT_TO_MM2 = FT_TO_MM ** 2


# ─────────────────────────────────────────────────────────────────────────────
# Helper: interpolate density from curve
# ─────────────────────────────────────────────────────────────────────────────

def _interpolate_density(hazard: str, area_sqft: float) -> float:
    """Return density (gpm/ft²) for a given area by linear interpolation."""
    pts = DENSITY_AREA_CURVES.get(hazard, [])
    if not pts:
        return 0.10
    if area_sqft <= pts[0][0]:
        return pts[0][1]
    if area_sqft >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        a0, d0 = pts[i]
        a1, d1 = pts[i + 1]
        if a0 <= area_sqft <= a1:
            t = (area_sqft - a0) / (a1 - a0)
            return d0 + t * (d1 - d0)
    return pts[-1][1]


def _interpolate_area(hazard: str, density: float) -> float:
    """Return area (sq ft) for a given density by linear interpolation along the curve."""
    pts = DENSITY_AREA_CURVES.get(hazard, [])
    if not pts:
        return 1500.0
    # Curves store (area, density).  Density decreases as area increases,
    # so sort by density ascending for lookup.
    sorted_pts = sorted(pts, key=lambda p: p[1])
    if density <= sorted_pts[0][1]:
        return sorted_pts[0][0]
    if density >= sorted_pts[-1][1]:
        return sorted_pts[-1][0]
    for i in range(len(sorted_pts) - 1):
        a0, d0 = sorted_pts[i]
        a1, d1 = sorted_pts[i + 1]
        if d0 <= density <= d1:
            t = (density - d0) / (d1 - d0) if d1 != d0 else 0.0
            return a0 + t * (a1 - a0)
    return sorted_pts[-1][0]


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Density / Area Graph Widget
# ─────────────────────────────────────────────────────────────────────────────

class DensityAreaGraph(QWidget):
    """Clickable NFPA 13 density/area curve graph."""

    pointSelected = pyqtSignal(float, float)  # density, area

    # Margins (px)
    ML, MR, MT, MB = 70, 20, 20, 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._active_hazard: str = "Light Hazard"
        self._selected_point: tuple[float, float] | None = None  # (area, density)
        self.setMouseTracking(True)
        self._hover_pos: QPointF | None = None
        # Dynamic ranges — recomputed per active hazard
        self.DENS_MIN = 0.05
        self.DENS_MAX = 0.15
        self.AREA_MIN = 1000.0
        self.AREA_MAX = 3500.0
        self._recompute_ranges()

    def set_active_hazard(self, hazard: str):
        self._active_hazard = hazard
        self._recompute_ranges()
        self.update()

    def _recompute_ranges(self):
        """Auto-scale axes to fit the active curve with padding."""
        pts = DENSITY_AREA_CURVES.get(self._active_hazard, [])
        if not pts:
            return
        areas = [p[0] for p in pts]
        densities = [p[1] for p in pts]
        # Pad: 0.05 on density axis, 500 on area axis
        self.DENS_MIN = max(0.0, min(densities) - 0.05)
        self.DENS_MAX = max(densities) + 0.05
        self.AREA_MIN = max(0.0, min(areas) - 500.0)
        self.AREA_MAX = max(areas) + 500.0

    def set_selected_point(self, area: float, density: float):
        self._selected_point = (area, density)
        self.update()

    def clear_selection(self):
        self._selected_point = None
        self.update()

    # ── Coordinate mapping ────────────────────────────────────────────────
    # X-axis = Density (gpm/ft²),  Y-axis = Area (sq ft)

    def _plot_rect(self) -> QRectF:
        w, h = self.width(), self.height()
        return QRectF(self.ML, self.MT, w - self.ML - self.MR, h - self.MT - self.MB)

    def _dens_to_x(self, dens: float) -> float:
        r = self._plot_rect()
        t = (dens - self.DENS_MIN) / (self.DENS_MAX - self.DENS_MIN)
        return r.left() + t * r.width()

    def _area_to_y(self, area: float) -> float:
        r = self._plot_rect()
        t = (area - self.AREA_MIN) / (self.AREA_MAX - self.AREA_MIN)
        return r.bottom() - t * r.height()

    def _x_to_dens(self, x: float) -> float:
        r = self._plot_rect()
        t = (x - r.left()) / r.width()
        return self.DENS_MIN + t * (self.DENS_MAX - self.DENS_MIN)

    def _y_to_area(self, y: float) -> float:
        r = self._plot_rect()
        t = (r.bottom() - y) / r.height()
        return self.AREA_MIN + t * (self.AREA_MAX - self.AREA_MIN)

    # ── Mouse interaction ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            r = self._plot_rect()
            pos = event.position()
            if r.contains(pos):
                density = self._x_to_dens(pos.x())
                # Clamp density to the active curve's valid range
                pts = DENSITY_AREA_CURVES.get(self._active_hazard, [])
                if pts:
                    densities = [p[1] for p in pts]
                    d_lo, d_hi = min(densities), max(densities)
                    density = max(d_lo, min(d_hi, density))
                # Snap to active curve — look up area for this density
                area = _interpolate_area(self._active_hazard, density)
                self._selected_point = (area, density)
                self.pointSelected.emit(density, area)
                self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._hover_pos = event.position()
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_pos = None
        self.update()
        super().leaveEvent(event)

    # ── Paint ─────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pr = self._plot_rect()

        # Background
        p.fillRect(self.rect(), QColor("#1e1e1e"))
        p.fillRect(pr.toRect(), QColor("#2a2a2a"))

        # Grid lines — dynamic ranges
        grid_pen = QPen(QColor("#3a3a3a"), 1, Qt.PenStyle.DotLine)
        p.setPen(grid_pen)
        # Vertical grid (density — X axis, step 0.05)
        d_start = math.ceil(self.DENS_MIN / 0.05) * 0.05
        d = d_start
        while d <= self.DENS_MAX + 1e-9:
            x = self._dens_to_x(d)
            p.drawLine(int(x), int(pr.top()), int(x), int(pr.bottom()))
            d += 0.05
        # Horizontal grid (area — Y axis, step 500)
        a_start = math.ceil(self.AREA_MIN / 500.0) * 500
        a = a_start
        while a <= self.AREA_MAX + 1:
            y = self._area_to_y(a)
            p.drawLine(int(pr.left()), int(y), int(pr.right()), int(y))
            a += 500

        # Axis labels
        label_font = QFont("Segoe UI", 7)
        p.setFont(label_font)
        p.setPen(QColor("#aaaaaa"))
        d = d_start
        while d <= self.DENS_MAX + 1e-9:
            x = self._dens_to_x(d)
            p.drawText(int(x) - 12, int(pr.bottom()) + 14, f"{d:.2f}")
            d += 0.05
        a = a_start
        while a <= self.AREA_MAX + 1:
            y = self._area_to_y(a)
            p.drawText(20, int(y) + 4, str(int(a)))
            a += 500

        # Axis titles
        title_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(QColor("#cccccc"))
        p.drawText(int(pr.center().x()) - 50, int(pr.bottom()) + 32, "Density (gpm/ft\u00b2)")
        p.save()
        p.translate(10, int(pr.center().y()) + 40)
        p.rotate(-90)
        p.drawText(0, 0, "Area (sq ft)")
        p.restore()

        # Draw only the active hazard curve
        active_pts = DENSITY_AREA_CURVES.get(self._active_hazard, [])
        if active_pts:
            color = QColor(_CURVE_COLORS.get(self._active_hazard, "#ffffff"))
            pen = QPen(color, 3)
            p.setPen(pen)
            for i in range(len(active_pts) - 1):
                # pts are (area, density) — X=density, Y=area
                x1 = self._dens_to_x(active_pts[i][1])
                y1 = self._area_to_y(active_pts[i][0])
                x2 = self._dens_to_x(active_pts[i + 1][1])
                y2 = self._area_to_y(active_pts[i + 1][0])
                p.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Legend — active hazard only
        legend_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(legend_font)
        label = _CURVE_LABELS.get(self._active_hazard, "")
        full_label = f"{label} \u2014 {self._active_hazard}"
        lx = int(pr.right()) - 180
        ly = int(pr.top()) + 12
        color = QColor(_CURVE_COLORS.get(self._active_hazard, "#ffffff"))
        p.setPen(QPen(color, 3))
        p.drawLine(lx, ly + 4, lx + 20, ly + 4)
        p.setPen(QColor("#cccccc"))
        p.drawText(lx + 24, ly + 8, full_label)

        # Hover crosshair
        if self._hover_pos and pr.contains(self._hover_pos):
            hp = self._hover_pos
            hover_pen = QPen(QColor("#ffffff44"), 1, Qt.PenStyle.DashLine)
            p.setPen(hover_pen)
            p.drawLine(int(hp.x()), int(pr.top()), int(hp.x()), int(pr.bottom()))
            p.drawLine(int(pr.left()), int(hp.y()), int(pr.right()), int(hp.y()))
            # Tooltip — X=density, snap area from curve
            dens = self._x_to_dens(hp.x())
            area = _interpolate_area(self._active_hazard, dens)
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(int(hp.x()) + 8, int(hp.y()) - 8,
                       f"{dens:.3f} gpm/ft\u00b2 @ {area:.0f} ft\u00b2")

        # Selected point marker
        if self._selected_point:
            sa, sd = self._selected_point
            sx = self._dens_to_x(sd)
            sy = self._area_to_y(sa)
            marker_color = QColor(_CURVE_COLORS.get(self._active_hazard, "#ffffff"))
            p.setPen(QPen(Qt.PenStyle.NoPen))
            p.setBrush(QBrush(marker_color))
            p.drawEllipse(QPointF(sx, sy), 6, 6)
            # White ring
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(sx, sy), 6, 6)
            # Label
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(int(sx) + 10, int(sy) - 4,
                       f"{sd:.3f} gpm/ft\u00b2 @ {sa:.0f} ft\u00b2")

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# Sprinkler Grid Computation
# ─────────────────────────────────────────────────────────────────────────────

def _decompose_into_rectangles(
    boundary: list[QPointF],
    path: QPainterPath,
    min_wall_mm: float,
) -> list[tuple[float, float, float, float]]:
    """Decompose a polygon into non-overlapping rectangles by scanline.

    Returns a list of (xmin, ymin, width, height) tuples in scene mm.
    For simple rectangular rooms this returns the single bounding rectangle.
    For L-shapes, T-shapes, etc. it returns multiple rectangles covering the
    interior.
    """
    xs = sorted({p.x() for p in boundary})
    ys = sorted({p.y() for p in boundary})

    rects: list[tuple[float, float, float, float]] = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[j], ys[j + 1]
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            if path.contains(QPointF(cx, cy)):
                rects.append((x0, y0, x1 - x0, y1 - y0))

    # Merge horizontally adjacent rectangles sharing same y-span
    merged = _merge_rectangles(rects)
    return merged


def _merge_rectangles(
    rects: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """Merge adjacent axis-aligned rectangles that share the same y-span
    into larger rectangles.  Then merge vertically."""
    if not rects:
        return rects

    # Round to avoid float precision issues
    def _key(r):
        return (round(r[1], 1), round(r[1] + r[3], 1))

    # Group by y-span
    from collections import defaultdict
    by_yspan: dict[tuple, list] = defaultdict(list)
    for r in rects:
        by_yspan[_key(r)].append(r)

    merged: list[tuple[float, float, float, float]] = []
    for yspan, group in by_yspan.items():
        group.sort(key=lambda r: r[0])  # sort by x
        cur = list(group[0])
        for r in group[1:]:
            # Adjacent if current right edge == next left edge
            if abs((cur[0] + cur[2]) - r[0]) < 1.0:
                cur[2] = (r[0] + r[2]) - cur[0]  # extend width
            else:
                merged.append(tuple(cur))
                cur = list(r)
        merged.append(tuple(cur))

    # Now merge vertically adjacent rects with same x-span
    from collections import defaultdict as dd
    by_xspan: dict[tuple, list] = dd(list)
    for r in merged:
        xkey = (round(r[0], 1), round(r[0] + r[2], 1))
        by_xspan[xkey].append(r)

    final: list[tuple[float, float, float, float]] = []
    for xspan, group in by_xspan.items():
        group.sort(key=lambda r: r[1])
        cur = list(group[0])
        for r in group[1:]:
            if abs((cur[1] + cur[3]) - r[1]) < 1.0:
                cur[3] = (r[1] + r[3]) - cur[1]
            else:
                final.append(tuple(cur))
                cur = list(r)
        final.append(tuple(cur))

    return final if final else rects


def _find_grid_dimensions(
    total_sprinklers: int,
    long_side_ft: float,
    short_side_ft: float,
) -> tuple[int, int]:
    """Find the best (n_long, n_short) grid dimensions for *total_sprinklers*.

    Prefers factorizations that keep the ratio close to room aspect ratio.
    Assigns the larger count to the longer side.
    If total is prime, bumps up to the next composite number.

    Returns (n_long, n_short) — count along longer side first.
    """
    def _is_prime(n: int) -> bool:
        if n < 2:
            return False
        if n < 4:
            return n > 1
        if n % 2 == 0 or n % 3 == 0:
            return False
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True

    aspect = long_side_ft / short_side_ft if short_side_ft > 0 else 1.0

    def _best_factor_pair(n: int) -> tuple[int, int]:
        """Return (a, b) with a >= b, a*b == n, closest to room aspect."""
        best = (n, 1)
        best_err = abs(n / 1.0 - aspect)
        for b in range(2, int(math.sqrt(n)) + 1):
            if n % b == 0:
                a = n // b
                err = abs(a / b - aspect)
                if err < best_err:
                    best = (a, b)
                    best_err = err
        return best

    n = total_sprinklers
    # If prime, try n+1 and n+2 (guaranteed to find a composite)
    candidates = [n]
    if _is_prime(n):
        candidates.extend([n + 1, n + 2, n + 3])

    best_pair = (n, 1)
    best_score = float("inf")
    for c in candidates:
        a, b = _best_factor_pair(c)
        # Score: penalise deviation from count and from aspect
        count_penalty = abs(c - total_sprinklers) * 2.0
        aspect_err = abs(a / b - aspect) if b > 0 else 999
        score = count_penalty + aspect_err
        if score < best_score:
            best_score = score
            best_pair = (a, b)

    return best_pair


def compute_sprinkler_grid(
    boundary: list[QPointF],
    max_coverage_sqft: float,
    max_spacing_ft: float,
    min_spacing_ft: float = NFPA_MIN_SPACING_FT,
    min_wall_dist_in: float = NFPA_MIN_WALL_DIST_IN,
) -> tuple[list[QPointF], float, float, str]:
    """Compute sprinkler positions inside a polygon.

    Algorithm:
      1.  Decompose room polygon into axis-aligned rectangles.
      2.  For each rectangle: area / max_coverage -> round up = starting count.
      3.  Find best grid dimensions (n_long x n_short), avoiding primes;
          assign larger count to longer side.
      4.  Spacing = side_length / count.  Half-spacing from each edge gives
          equal margins.
      5.  If any spacing exceeds max_spacing, bump count and recalculate.
      6.  Final pass checks min spacing between sprinklers in adjacent rects.

    Returns (positions, spacing_x_ft, spacing_y_ft, calc_log).
    """
    log_lines: list[str] = []
    log = log_lines.append

    if len(boundary) < 3:
        return [], 0.0, 0.0, ""

    # Build QPainterPath for containment testing
    path = QPainterPath()
    path.addPolygon(QPolygonF(boundary))
    path.closeSubpath()

    # Convert limits to mm
    max_coverage_mm2 = max_coverage_sqft * SQFT_TO_MM2
    max_spacing_mm = max_spacing_ft * FT_TO_MM
    min_spacing_mm = min_spacing_ft * FT_TO_MM
    min_wall_mm = min_wall_dist_in * IN_TO_MM

    log(f"Max coverage: {max_coverage_sqft:.1f} sq ft")
    log(f"Max spacing:  {max_spacing_ft:.1f} ft")
    log(f"Min spacing:  {min_spacing_ft:.1f} ft")

    # Decompose into rectangles
    rects = _decompose_into_rectangles(boundary, path, min_wall_mm)
    if not rects:
        xs = [p.x() for p in boundary]
        ys = [p.y() for p in boundary]
        rects = [(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))]
        log("Using bounding box (no rectangles found)")

    log(f"Decomposed into {len(rects)} rectangle(s)")
    log("")

    all_positions: list[QPointF] = []
    all_sx: list[float] = []
    all_sy: list[float] = []

    for rect_idx, (rx, ry, rw, rh) in enumerate(rects):
        w_ft = rw / FT_TO_MM
        h_ft = rh / FT_TO_MM
        area_sqft = w_ft * h_ft

        if area_sqft < 1.0:
            continue

        log(f"-- Rectangle {rect_idx + 1}: {w_ft:.2f} ft x {h_ft:.2f} ft --")
        log(f"  Area: {area_sqft:.2f} sq ft")

        # Step 2: starting sprinkler count
        raw_count = area_sqft / max_coverage_sqft
        n_total = max(1, math.ceil(raw_count))
        log(f"  {area_sqft:.2f} / {max_coverage_sqft:.0f} = {raw_count:.2f}"
            f"  -> ceil = {n_total}")

        # Step 3: determine long/short sides and grid dimensions
        if w_ft >= h_ft:
            long_ft, short_ft = w_ft, h_ft
            long_mm, short_mm = rw, rh
            is_x_long = True
        else:
            long_ft, short_ft = h_ft, w_ft
            long_mm, short_mm = rh, rw
            is_x_long = False

        n_long, n_short = _find_grid_dimensions(n_total, long_ft, short_ft)
        grid_total = n_long * n_short
        if grid_total != n_total:
            log(f"  {n_total} is prime -> adjusted to {grid_total}"
                f"  ({n_long}x{n_short})")
        else:
            log(f"  Grid: {n_long} x {n_short} = {grid_total}")

        # Step 4 helper
        def _calc_spacing_and_positions_1d(
            side_mm: float, count: int
        ) -> tuple[float, list[float]]:
            if count <= 0:
                return side_mm, []
            sp = side_mm / count
            return sp, [sp / 2.0 + i * sp for i in range(count)]

        # Step 5: check max spacing constraint, bump count if needed
        bumped = False
        for _attempt in range(20):
            sp_long = long_mm / n_long if n_long > 0 else long_mm
            sp_short = short_mm / n_short if n_short > 0 else short_mm
            exceeded = False
            if sp_long > max_spacing_mm:
                log(f"  Long spacing {sp_long / FT_TO_MM:.2f} ft"
                    f" > {max_spacing_ft:.1f} ft -> bump n_long"
                    f" {n_long}->{n_long + 1}")
                n_long += 1
                exceeded = True
                bumped = True
            if sp_short > max_spacing_mm:
                log(f"  Short spacing {sp_short / FT_TO_MM:.2f} ft"
                    f" > {max_spacing_ft:.1f} ft -> bump n_short"
                    f" {n_short}->{n_short + 1}")
                n_short += 1
                exceeded = True
                bumped = True
            if not exceeded:
                break

        # Also ensure min spacing
        for _attempt in range(20):
            sp_long = long_mm / n_long if n_long > 0 else long_mm
            sp_short = short_mm / n_short if n_short > 0 else short_mm
            shrunk = False
            if sp_long < min_spacing_mm and n_long > 1:
                log(f"  Long spacing {sp_long / FT_TO_MM:.2f} ft"
                    f" < {min_spacing_ft:.1f} ft -> reduce n_long"
                    f" {n_long}->{n_long - 1}")
                n_long -= 1
                shrunk = True
            if sp_short < min_spacing_mm and n_short > 1:
                log(f"  Short spacing {sp_short / FT_TO_MM:.2f} ft"
                    f" < {min_spacing_ft:.1f} ft -> reduce n_short"
                    f" {n_short}->{n_short - 1}")
                n_short -= 1
                shrunk = True
            if not shrunk:
                break

        if bumped:
            log(f"  Final grid: {n_long} x {n_short} = {n_long * n_short}")

        # Assign to x/y
        if is_x_long:
            nx, ny = n_long, n_short
        else:
            nx, ny = n_short, n_long

        sx_mm, x_offsets = _calc_spacing_and_positions_1d(rw, nx)
        sy_mm, y_offsets = _calc_spacing_and_positions_1d(rh, ny)

        sx_ft = sx_mm / FT_TO_MM
        sy_ft = sy_mm / FT_TO_MM
        log(f"  Spacing X: {w_ft:.2f}/{nx} = {sx_ft:.4f} ft"
            f"  (edge margin: {sx_ft / 2:.4f} ft)")
        log(f"  Spacing Y: {h_ft:.2f}/{ny} = {sy_ft:.4f} ft"
            f"  (edge margin: {sy_ft / 2:.4f} ft)")

        rect_pts = 0
        for xo in x_offsets:
            for yo in y_offsets:
                pt = QPointF(rx + xo, ry + yo)
                if path.contains(pt):
                    all_positions.append(pt)
                    rect_pts += 1

        log(f"  Placed: {rect_pts} sprinklers")
        if rect_pts < nx * ny:
            log(f"  ({nx * ny - rect_pts} clipped by polygon boundary)")
        log("")

        all_sx.append(sx_mm)
        all_sy.append(sy_mm)

    # Step 6: remove sprinklers from adjacent rectangles that are too close
    if len(all_positions) > 1:
        to_remove: set[int] = set()
        for i in range(len(all_positions)):
            if i in to_remove:
                continue
            for j in range(i + 1, len(all_positions)):
                if j in to_remove:
                    continue
                dist = math.hypot(
                    all_positions[i].x() - all_positions[j].x(),
                    all_positions[i].y() - all_positions[j].y(),
                )
                if dist < min_spacing_mm:
                    to_remove.add(j)
        if to_remove:
            log(f"Removed {len(to_remove)} sprinkler(s) too close"
                f" (< {min_spacing_ft:.1f} ft) between rectangles")
            all_positions = [
                p for i, p in enumerate(all_positions) if i not in to_remove
            ]

    # Summary
    final_sx = all_sx[0] / FT_TO_MM if all_sx else 0.0
    final_sy = all_sy[0] / FT_TO_MM if all_sy else 0.0
    log(f"=== TOTAL: {len(all_positions)} sprinklers ===")

    return all_positions, final_sx, final_sy, "\n".join(log_lines)


def _polygon_area_mm2(boundary: list[QPointF]) -> float:
    """Polygon area via shoelace formula (scene units = mm²)."""
    n = len(boundary)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += boundary[i].x() * boundary[j].y()
        area -= boundary[j].x() * boundary[i].y()
    return abs(area) / 2.0


def _min_dist_to_boundary(pt: QPointF, boundary: list[QPointF]) -> float:
    """Minimum distance from pt to any edge of the boundary polygon (mm)."""
    min_d = float("inf")
    n = len(boundary)
    px, py = pt.x(), pt.y()
    for i in range(n):
        j = (i + 1) % n
        ax, ay = boundary[i].x(), boundary[i].y()
        bx, by = boundary[j].x(), boundary[j].y()
        # Point-to-segment distance
        dx, dy = bx - ax, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-9:
            d = math.hypot(px - ax, py - ay)
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
            cx = ax + t * dx
            cy = ay + t * dy
            d = math.hypot(px - cx, py - cy)
        if d < min_d:
            min_d = d
    return min_d


# ─────────────────────────────────────────────────────────────────────────────
# Auto-Populate Dialog
# ─────────────────────────────────────────────────────────────────────────────

_SPR_COLUMNS = ("Manufacturer", "Model", "Type", "K-factor", "Coverage (ft\u00b2)", "Min P (psi)")


class AutoPopulateDialog(QDialog):
    """Dialog for configuring automatic sprinkler population of a room."""

    def __init__(
        self,
        room: Room,
        sprinkler_db: SprinklerDatabase,
        level_manager: LevelManager | None = None,
        scale_manager: ScaleManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Auto-Populate Sprinklers")
        self._room = room
        self._db = sprinkler_db
        self._lm = level_manager
        self._sm = scale_manager
        self._selected_record: SprinklerRecord | None = None
        self._computed_positions: list[QPointF] = []
        self._computed_sx: float = 0.0
        self._computed_sy: float = 0.0
        self._selected_density: float = 0.10
        self._selected_area: float = 1500.0

        self._build_ui()
        self._populate_sprinkler_table()
        self._on_config_changed()

        # Auto-size to fit content, capped to 90% of screen
        self.adjustSize()
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(self.sizeHint().width(), int(avail.width() * 0.9))
            h = min(self.sizeHint().height(), int(avail.height() * 0.9))
            self.resize(max(w, 900), max(h, 700))

        # Restore persisted geometry and splitter states
        self._settings = QSettings("FirePro3D", "AutoPopulateDialog")
        geo = self._settings.value("geometry")
        if isinstance(geo, QByteArray):
            self.restoreGeometry(geo)
        top_state = self._settings.value("topSplitter")
        if isinstance(top_state, QByteArray):
            self._top_splitter.restoreState(top_state)
        bot_state = self._settings.value("bottomSplitter")
        if isinstance(bot_state, QByteArray):
            self._bottom_splitter.restoreState(bot_state)

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)

        # ── Room info (inherited from room properties) ─────────────────────
        g_room = QGroupBox("Room Information")
        fl = QFormLayout(g_room)
        area_mm2 = self._room._compute_area_mm2()
        area_sqft = area_mm2 / SQFT_TO_MM2
        self._room_area_sqft = area_sqft
        fl.addRow("Room Name:", QLabel(self._room.name or "(unnamed)"))
        fl.addRow("Area:", QLabel(f"{area_sqft:.1f} sq ft"))
        fl.addRow("Hazard Class:", QLabel(self._room._hazard_class))
        fl.addRow("Ceiling Type:", QLabel(self._room._ceiling_type))
        fl.addRow("Compartment Type:", QLabel(self._room._compartment_type))
        fl.addRow("Floor Level:", QLabel(self._room.level))
        fl.addRow("Ceiling Level:", QLabel(self._room._ceiling_level))
        ceil_offset = getattr(self._room, "_ceiling_offset", 0.0)
        if ceil_offset:
            offset_str = self._sm.format_length(ceil_offset) if self._sm else f"{ceil_offset:.1f} mm"
            fl.addRow("Ceiling Offset:", QLabel(offset_str))
        ceil_h = self._room._ceiling_height_mm()
        self._ceiling_height_mm = ceil_h
        ceil_h_str = self._sm.format_length(ceil_h) if self._sm else f"{ceil_h:.1f} mm"
        fl.addRow("Ceiling Height:", QLabel(ceil_h_str))
        root.addWidget(g_room)

        # ── Side-by-side: Sprinkler Selection | Density/Area Graph ─────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left side — Sprinkler Selection
        g_spr = QGroupBox("Sprinkler Selection")
        spr_lay = QVBoxLayout(g_spr)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Search:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Manufacturer, model...")
        self._search_edit.textChanged.connect(self._filter_table)
        filter_row.addWidget(self._search_edit)
        filter_row.addWidget(QLabel("Type:"))
        self._type_filter = QComboBox()
        self._type_filter.addItems(["(All)", "Pendent", "Upright", "Sidewall", "Concealed"])
        self._type_filter.currentTextChanged.connect(self._filter_table)
        filter_row.addWidget(self._type_filter)
        spr_lay.addLayout(filter_row)

        self._spr_table = QTableWidget(0, len(_SPR_COLUMNS))
        self._spr_table.setHorizontalHeaderLabels(list(_SPR_COLUMNS))
        self._spr_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self._spr_table.horizontalHeader().setStretchLastSection(True)
        self._spr_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._spr_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._spr_table.setAlternatingRowColors(True)
        f = QFont()
        f.setPointSizeF(8.5)
        self._spr_table.setFont(f)
        self._spr_table.currentCellChanged.connect(self._on_sprinkler_selected)
        spr_lay.addWidget(self._spr_table)
        splitter.addWidget(g_spr)

        # Right side — Density/Area Graph
        g_graph = QGroupBox("Density / Area Curve (click to select operating point)")
        graph_lay = QVBoxLayout(g_graph)
        self._graph = DensityAreaGraph()
        self._graph.pointSelected.connect(self._on_graph_point_selected)
        graph_lay.addWidget(self._graph)
        self._lbl_selected_point = QLabel("Click the graph to select an operating point")
        self._lbl_selected_point.setStyleSheet("font-weight: bold;")
        graph_lay.addWidget(self._lbl_selected_point)
        splitter.addWidget(g_graph)

        # Give sprinkler table ~55% of the width, graph ~45%
        splitter.setStretchFactor(0, 55)
        splitter.setStretchFactor(1, 45)
        self._top_splitter = splitter
        root.addWidget(splitter, 1)  # stretch factor 1 so it fills vertical space

        # ── Side-by-side: NFPA Requirements | Results Preview ──────────────
        bottom_split = QSplitter(Qt.Orientation.Horizontal)
        bottom_split.setChildrenCollapsible(False)

        # Left — NFPA 13 Requirements & Spacing
        g_req = QGroupBox("NFPA 13 Requirements & Spacing")
        req_lay = QFormLayout(g_req)

        # Algorithm selection
        from PyQt6.QtWidgets import QComboBox
        self._algo_combo = QComboBox()
        self._algorithms = {
            "Grid (Uniform)": "grid_uniform",
        }
        for label in self._algorithms:
            self._algo_combo.addItem(label)
        self._algo_combo.currentTextChanged.connect(
            lambda _: self._on_config_changed())
        req_lay.addRow("Algorithm:", self._algo_combo)

        self._lbl_orientation = QLabel("---")
        self._lbl_density = QLabel("---")
        self._lbl_min_design_area = QLabel("---")
        self._lbl_max_coverage = QLabel("---")
        self._lbl_spr_coverage = QLabel("---")
        self._lbl_max_spacing = QLabel("---")
        self._lbl_min_spacing = QLabel(f"{NFPA_MIN_SPACING_FT:.0f} ft")

        # Ceiling offset — uses dimension parsing / display units
        self._offset_edit = QLineEdit()
        self._offset_mm: float = -50.8
        self._offset_edit.setText(self._format_offset(self._offset_mm))
        self._offset_edit.editingFinished.connect(self._on_offset_edited)

        req_lay.addRow("Sprinkler Orientation:", self._lbl_orientation)
        req_lay.addRow("Design Density:", self._lbl_density)
        req_lay.addRow("Minimum Design Area:", self._lbl_min_design_area)
        req_lay.addRow("NFPA Max Coverage:", self._lbl_max_coverage)
        req_lay.addRow("Sprinkler Listing Coverage:", self._lbl_spr_coverage)
        req_lay.addRow("Max Spacing:", self._lbl_max_spacing)
        req_lay.addRow("Min Spacing:", self._lbl_min_spacing)
        req_lay.addRow("Sprinkler Offset:", self._offset_edit)
        bottom_split.addWidget(g_req)

        # Right — Results Preview
        g_res = QGroupBox("Results Preview")
        res_vbox = QVBoxLayout(g_res)
        res_top = QFormLayout()
        self._lbl_spacing_xy = QLabel("---")
        self._lbl_count = QLabel("---")
        self._lbl_actual_cov = QLabel("---")
        self._lbl_spr_height = QLabel("---")
        self._lbl_status = QLabel("---")
        res_top.addRow("Computed Spacing:", self._lbl_spacing_xy)
        res_top.addRow("Sprinkler Count:", self._lbl_count)
        res_top.addRow("Actual Coverage/Sprinkler:", self._lbl_actual_cov)
        res_top.addRow("Sprinkler Height:", self._lbl_spr_height)
        res_top.addRow("Status:", self._lbl_status)
        res_vbox.addLayout(res_top)

        # Calculation log
        from PyQt6.QtWidgets import QTextEdit
        self._calc_log = QTextEdit()
        self._calc_log.setReadOnly(True)
        self._calc_log.setMaximumHeight(160)
        self._calc_log.setStyleSheet(
            "QTextEdit { font-family: Consolas, monospace; font-size: 11px; "
            "color: #000000; background: #f8f8f8; border: 1px solid #ccc; }"
        )
        res_vbox.addWidget(QLabel("Calculation Log:"))
        res_vbox.addWidget(self._calc_log)
        bottom_split.addWidget(g_res)

        bottom_split.setStretchFactor(0, 50)
        bottom_split.setStretchFactor(1, 50)
        self._bottom_splitter = bottom_split
        root.addWidget(bottom_split)

        # ── Buttons ───────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    # ── Ceiling offset helpers ─────────────────────────────────────────────

    def _format_offset(self, mm: float) -> str:
        """Format mm value using project display units."""
        if self._sm:
            return self._sm.format_length(mm)
        return f"{mm:.1f} mm"

    def _on_offset_edited(self):
        """Parse the ceiling offset text using scale_manager dimension parsing."""
        text = self._offset_edit.text().strip()
        if self._sm:
            parsed = self._sm.parse_dimension(text, self._sm.bare_number_unit())
        else:
            try:
                parsed = float(text)
            except (ValueError, TypeError):
                parsed = None
        if parsed is not None:
            self._offset_mm = parsed
        # Reformat to canonical display
        self._offset_edit.setText(self._format_offset(self._offset_mm))

    # ── Algorithm dispatch ─────────────────────────────────────────────────

    def _run_algorithm(self, algo_key: str, max_cov: float, max_spacing: float):
        """Run the selected placement algorithm and return
        (positions, spacing_x_ft, spacing_y_ft, calc_log)."""
        if algo_key == "grid_uniform":
            return compute_sprinkler_grid(
                self._room.boundary, max_cov, max_spacing)
        # Future algorithms go here:
        # elif algo_key == "offset_from_walls":
        #     return compute_wall_offset(...)
        # Fallback
        return compute_sprinkler_grid(
            self._room.boundary, max_cov, max_spacing)

    # ── Sprinkler table ───────────────────────────────────────────────────

    def _populate_sprinkler_table(self):
        self._all_records = self._db.library
        self._filter_table()

    def _filter_table(self):
        text = self._search_edit.text().lower()
        type_f = self._type_filter.currentText()
        # Filter by hazard-compatible sprinkler types (from room property)
        hazard = self._room._hazard_class
        allowed_types = HAZARD_SPRINKLER_TYPES.get(hazard, ["Pendent", "Upright", "Sidewall", "Concealed"])
        filtered = [
            r for r in self._all_records
            if (not text or text in r.manufacturer.lower() or text in r.model.lower())
            and (type_f == "(All)" or r.type == type_f)
            and r.type in allowed_types
        ]
        self._spr_table.setRowCount(len(filtered))
        for row, r in enumerate(filtered):
            cells = (
                r.manufacturer, r.model, r.type,
                f"{r.k_factor:.1f}", f"{r.coverage_area:.0f}", f"{r.min_pressure:.1f}",
            )
            for col, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                item.setData(Qt.ItemDataRole.UserRole, r)
                self._spr_table.setItem(row, col, item)
        # Select first row if available
        if filtered:
            self._spr_table.setCurrentCell(0, 0)

    def _on_sprinkler_selected(self, row, col, prev_row, prev_col):
        if row < 0:
            self._selected_record = None
        else:
            item = self._spr_table.item(row, 0)
            if item:
                self._selected_record = item.data(Qt.ItemDataRole.UserRole)
        self._on_config_changed()

    # ── Configuration change handler ──────────────────────────────────────

    def _on_config_changed(self):
        hazard = self._room._hazard_class
        # Derive obstruction from ceiling type — types containing "obstructed"
        # (but not "unobstructed") are obstructed
        ceiling_type = self._room._ceiling_type.lower()
        obstruction = "Obstructed" if "obstructed" in ceiling_type and "unobstructed" not in ceiling_type else "Unobstructed"
        self._graph.set_active_hazard(hazard)

        # Sprinkler orientation from selected record
        if self._selected_record:
            self._lbl_orientation.setText(self._selected_record.type)
        else:
            self._lbl_orientation.setText("---")

        # NFPA limits
        nfpa_max_cov = NFPA_MAX_COVERAGE.get(hazard, 130.0)
        max_spacing = NFPA_MAX_SPACING.get(hazard, {}).get(obstruction, 15.0)

        # Design density and minimum design area from graph selection
        self._lbl_density.setText(f"{self._selected_density:.3f} gpm/ft\u00b2")
        self._lbl_min_design_area.setText(f"{self._selected_area:.0f} sq ft")
        self._lbl_max_coverage.setText(f"{nfpa_max_cov:.0f} sq ft")
        self._lbl_max_spacing.setText(f"{max_spacing:.0f} ft ({obstruction.lower()})")

        # Sprinkler listing coverage
        spr_cov = nfpa_max_cov
        if self._selected_record:
            spr_cov = self._selected_record.coverage_area
            self._lbl_spr_coverage.setText(f"{spr_cov:.0f} sq ft")
        else:
            self._lbl_spr_coverage.setText("---")

        # Dispatch to selected algorithm
        algo_key = self._algorithms.get(
            self._algo_combo.currentText(), "grid_uniform")
        positions, sx, sy, calc_log = self._run_algorithm(
            algo_key, nfpa_max_cov, max_spacing)
        self._computed_positions = positions
        self._computed_sx = sx
        self._computed_sy = sy

        # Update calculation log
        self._calc_log.setPlainText(calc_log)

        # Update results
        count = len(positions)
        self._lbl_spacing_xy.setText(f"{sx:.1f} ft x {sy:.1f} ft")
        self._lbl_count.setText(str(count))

        # Sprinkler height = ceiling height + sprinkler offset
        spr_h = getattr(self, "_ceiling_height_mm", 0.0) + self._offset_mm
        spr_h_str = self._format_offset(spr_h)
        self._lbl_spr_height.setText(spr_h_str)

        if count > 0:
            actual_cov = self._room_area_sqft / count
            self._lbl_actual_cov.setText(f"{actual_cov:.1f} sq ft")
            ok = actual_cov <= nfpa_max_cov
            if ok:
                self._lbl_status.setText("PASS")
                self._lbl_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
            else:
                self._lbl_status.setText("FAIL - coverage exceeds limit")
                self._lbl_status.setStyleSheet("color: #F44336; font-weight: bold;")
        else:
            self._lbl_actual_cov.setText("---")
            self._lbl_status.setText("No sprinklers computed")
            self._lbl_status.setStyleSheet("color: #FF9800; font-weight: bold;")

    # ── Graph interaction ─────────────────────────────────────────────────

    def _on_graph_point_selected(self, density: float, area: float):
        self._selected_density = density
        self._selected_area = area
        self._lbl_selected_point.setText(
            f"Selected: {density:.3f} gpm/ft\u00b2 @ {area:.0f} sq ft"
        )
        # Refresh requirements display to reflect new graph selection
        self._lbl_density.setText(f"{density:.3f} gpm/ft\u00b2")
        self._lbl_min_design_area.setText(f"{area:.0f} sq ft")

    # ── Accept ────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Persist dialog geometry and splitter states."""
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("topSplitter", self._top_splitter.saveState())
        self._settings.setValue("bottomSplitter", self._bottom_splitter.saveState())
        super().closeEvent(event)

    def _on_accept(self):
        if not self._selected_record:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Sprinkler Selected",
                                "Please select a sprinkler from the table.")
            return
        if not self._computed_positions:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Positions",
                                "No sprinkler positions could be computed for this room.")
            return
        self.accept()

    # ── Public accessors ──────────────────────────────────────────────────

    def get_results(self) -> dict:
        """Return all parameters needed to place sprinklers."""
        algo_key = self._algorithms.get(
            self._algo_combo.currentText(), "grid_uniform")
        return {
            "positions": self._computed_positions,
            "record": self._selected_record,
            "level": self._room.level,
            "ceiling_level": self._room._ceiling_level,
            "ceiling_offset": self._offset_mm,
            "hazard_class": self._room._hazard_class,
            "design_density": f"{self._selected_density:.3f}",
            "design_area": self._selected_area,
            "spacing_x_ft": self._computed_sx,
            "spacing_y_ft": self._computed_sy,
            "algorithm": algo_key,
        }
