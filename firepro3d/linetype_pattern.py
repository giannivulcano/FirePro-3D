"""Pure Dash / Gap / Dot rows <-> LT3-3 reading (linetypes.md LT4-1/LT4-2/LT4-9).

No Qt items: the live-scene half is ``linetype_authoring``.
"""
from __future__ import annotations

from .constants import LINETYPE_AXIS_TOL_MM

DASH, GAP, DOT = "dash", "gap", "dot"
SEED_ROWS = ((DASH, 6.0), (GAP, 3.0))      # LT4-6 starter unit
_TOL = LINETYPE_AXIS_TOL_MM


def rows_from_reading(dashes, dots, length: float):
    """Sequential rows for a reading, or None when unrepresentable (LT4-1).

    Args:
        dashes: ``((start, length), ...)`` as ``LinetypeDef.dashes``.
        dots: ``(x, ...)`` as ``LinetypeDef.dots``.
        length: The frame length (period).

    Returns:
        ``[(kind, mm), ...]`` with leading / between / trailing gaps, or None
        when dashes overlap or a dot sits strictly inside a dash.
    """
    # Middle field (0 = dot, 1 = dash): a dot at a dash's start sorts before it.
    events = sorted([(float(a), 1, float(n)) for a, n in dashes]
                    + [(float(x), 0, 0.0) for x in dots])
    rows, cur = [], 0.0
    for x, kind, n in events:
        if x < cur - _TOL:
            return None
        if x > cur + _TOL:
            rows.append((GAP, round(x - cur, 9)))
        if kind == 0:
            rows.append((DOT, 0.0))
            cur = max(cur, x)
        else:
            rows.append((DASH, round(n, 9)))
            cur = x + n
    if length > cur + _TOL:
        rows.append((GAP, round(length - cur, 9)))
    return rows


def spans(rows):
    """Axis spans of *rows* and their period (LT4-2: period = sum of rows).

    Args:
        rows: ``[(kind, mm), ...]`` as ``rows_from_reading`` returns.

    Returns:
        ``([(kind, x0, x1), ...], period)`` -- dashes and dots only (a dot
        has ``x0 == x1``), in x order.
    """
    x, out = 0.0, []
    for kind, n in rows:
        if kind == DASH:
            out.append((DASH, x, x + n))
            x += n
        elif kind == GAP:
            x += n
        else:
            out.append((DOT, x, x))
    return out, x


def content_end(prim_dicts) -> float:
    """Unclamped far end of the axis Lines (LT4-9 grow-to-fit); 0 when none.

    Args:
        prim_dicts: Block primitive dicts; only on-axis ``draw_line`` count.

    Returns:
        The largest axis-Line x (may exceed the frame length), or 0.0.
    """
    end = 0.0
    for p in prim_dicts:
        if p.get("type") != "draw_line":
            continue
        (x1, y1), (x2, y2) = p["pt1"], p["pt2"]
        if abs(y1) <= _TOL and abs(y2) <= _TOL:
            end = max(end, x1, x2)
    return float(end)


def validate_rows(rows) -> bool:
    """At least one dash or dot; every dash / gap length > tolerance (LT4-12).

    Args:
        rows: ``[(kind, mm), ...]``.

    Returns:
        True when the rows can be stored and read back by the renderer.
    """
    if not any(k in (DASH, DOT) for k, _ in rows):
        return False
    return all(n > _TOL for k, n in rows if k in (DASH, GAP))
