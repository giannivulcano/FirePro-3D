"""NFPA 13 density/area curve data and interpolation helpers.

Single home for Figure 11.2.3.1.1 curve data — imported by the
auto-populate dialog, Room protection criteria, DesignArea inheritance,
and the hydraulic report. No Qt imports (safe for any module).
"""

from __future__ import annotations

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

# Short abbreviations for each hazard class — used in legends, badges, labels.
HAZARD_ABBREV: dict[str, str] = {
    "Light Hazard":             "LH",
    "Ordinary Hazard Group 1":  "OH1",
    "Ordinary Hazard Group 2":  "OH2",
    "Extra Hazard Group 1":     "EH1",
    "Extra Hazard Group 2":     "EH2",
}

# Hazard classes with no density/area curve — protection criteria come from
# NFPA 13 storage chapters (Table 4.3.1.7.1 system is a planned follow-up).
STORAGE_HAZARDS: tuple[str, ...] = ("Miscellaneous Storage", "High Piled Storage")


def interpolate_density(hazard: str, area_sqft: float) -> float:
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


def interpolate_area(hazard: str, density: float) -> float:
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


def min_design_point(hazard: str) -> tuple[float, float] | None:
    """Smallest-area point on the hazard's curve — the default design point.

    Returns None for hazards with no curve (storage classes)."""
    pts = DENSITY_AREA_CURVES.get(hazard)
    if not pts:
        return None
    return min(pts, key=lambda p: p[0])
