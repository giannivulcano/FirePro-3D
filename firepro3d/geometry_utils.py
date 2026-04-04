"""Shared geometry helpers used by roof, floor_slab, and other modules."""
from __future__ import annotations


def triangulate_polygon(pts: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Ear-clipping triangulation for a simple (possibly concave) polygon.

    Parameters
    ----------
    pts : list of (x, y) tuples
        Polygon vertices in order.

    Returns
    -------
    list of (i, j, k) index triples – one per triangle.
    """
    n = len(pts)
    if n < 3:
        return []

    indices = list(range(n))
    triangles: list[tuple[int, int, int]] = []

    def cross(o: int, a: int, b: int) -> float:
        return (pts[a][0] - pts[o][0]) * (pts[b][1] - pts[o][1]) - \
               (pts[a][1] - pts[o][1]) * (pts[b][0] - pts[o][0])

    def point_in_triangle(px: float, py: float,
                          ax: float, ay: float,
                          bx: float, by: float,
                          cx: float, cy: float) -> bool:
        d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
        d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
        d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)

    # Ensure CCW winding
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n))
    if area < 0:
        indices = indices[::-1]

    attempts = 0
    max_attempts = n * n
    while len(indices) > 2 and attempts < max_attempts:
        attempts += 1
        found_ear = False
        m = len(indices)
        for i in range(m):
            prev_idx = indices[(i - 1) % m]
            curr_idx = indices[i]
            next_idx = indices[(i + 1) % m]

            if cross(prev_idx, curr_idx, next_idx) <= 0:
                continue

            is_ear = True
            ax, ay = pts[prev_idx]
            bx, by = pts[curr_idx]
            cx, cy = pts[next_idx]
            for j in range(m):
                if j in (i, (i - 1) % m, (i + 1) % m):
                    continue
                px, py = pts[indices[j]]
                if point_in_triangle(px, py, ax, ay, bx, by, cx, cy):
                    is_ear = False
                    break

            if is_ear:
                triangles.append((prev_idx, curr_idx, next_idx))
                indices.pop(i)
                found_ear = True
                break

        if not found_ear:
            break

    return triangles
