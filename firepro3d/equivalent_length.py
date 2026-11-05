"""
equivalent_length.py
====================
NFPA 13 Table 22.4.3.1.1 — Equivalent pipe lengths for fittings.

Provides a lookup function used by the hydraulic solver to add fitting
friction to each pipe's total length.
"""

# Nominal pipe diameters — internal keys used by Pipe._properties["Diameter"]
# Includes all 11 NFPA 13 table columns (3 sizes not yet in Pipe options).
_DIAMETERS = [
    '¾"Ø', '1"Ø', '1-¼"Ø', '1-½"Ø', '2"Ø',
    '2-½"Ø', '3"Ø', '4"Ø', '5"Ø', '6"Ø', '8"Ø',
]

# NFPA 13 Table 22.4.3.1.1 — equivalent lengths in feet
# Rows: fitting category, Columns: nominal pipe diameter (same order as _DIAMETERS)
_TABLE: dict[str, list[float]] = {
    "90_elbow":        [2, 2.5, 3, 4, 5, 6, 7, 10, 12, 14, 18],
    "45_elbow":        [1, 1.5, 2, 2, 3, 3, 4, 5, 6, 7, 9],
    "tee_flow_turn":   [4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 35],
    "cross_flow_turn": [4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 35],
    "cap":             [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
}

_DIA_INDEX = {d: i for i, d in enumerate(_DIAMETERS)}

# Map Fitting.type strings → table row keys
FITTING_TYPE_MAP: dict[str, str] = {
    "90elbow":    "90_elbow",
    "45elbow":    "45_elbow",
    "tee":        "tee_flow_turn",
    "tee_up":     "tee_flow_turn",
    "tee_down":   "tee_flow_turn",
    "wye":        "45_elbow",
    "cross":      "cross_flow_turn",
    "elbow_up":   "90_elbow",
    "elbow_down": "90_elbow",
    "cap":        "cap",
    "no fitting": "cap",
    "riser_through":  "cap",
    "tee_vertical":   "tee_flow_turn",
    "cross_vertical": "cross_flow_turn",
}


def equivalent_length_ft(fitting_type: str, nominal_diameter: str) -> float:
    """Return the equivalent pipe length in feet for a fitting.

    Args:
        fitting_type: Fitting.type string (e.g. "90elbow", "tee_up").
        nominal_diameter: Pipe internal diameter key (e.g. '2"Ø').

    Returns:
        Equivalent length in feet, or 0.0 if the fitting type or diameter
        is not in the NFPA table.
    """
    row_key = FITTING_TYPE_MAP.get(fitting_type)
    if row_key is None:
        return 0.0
    col_idx = _DIA_INDEX.get(nominal_diameter)
    if col_idx is None:
        return 0.0
    return _TABLE[row_key][col_idx]
