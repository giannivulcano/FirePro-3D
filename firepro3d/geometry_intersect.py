"""Geometry intersection utilities for trim/extend operations."""
import math
from PyQt6.QtCore import QPointF

EPS = 1e-9


def line_line_intersection(p1: QPointF, p2: QPointF,
                           p3: QPointF, p4: QPointF) -> QPointF | None:
    """Intersect segment (p1,p2) with segment (p3,p4).

    Returns the intersection point or None if no intersection exists
    within both segments.
    """
    dx1 = p2.x() - p1.x()
    dy1 = p2.y() - p1.y()
    dx2 = p4.x() - p3.x()
    dy2 = p4.y() - p3.y()

    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < EPS:
        return None  # parallel or coincident

    dx3 = p3.x() - p1.x()
    dy3 = p3.y() - p1.y()

    t = (dx3 * dy2 - dy3 * dx2) / denom
    u = (dx3 * dy1 - dy3 * dx1) / denom

    if -EPS <= t <= 1.0 + EPS and -EPS <= u <= 1.0 + EPS:
        return QPointF(p1.x() + t * dx1, p1.y() + t * dy1)
    return None


def line_line_intersection_unbounded(p1: QPointF, p2: QPointF,
                                     p3: QPointF, p4: QPointF) -> QPointF | None:
    """Intersect infinite lines through (p1,p2) and (p3,p4).

    Returns the intersection point or None if the lines are parallel.
    """
    dx1 = p2.x() - p1.x()
    dy1 = p2.y() - p1.y()
    dx2 = p4.x() - p3.x()
    dy2 = p4.y() - p3.y()

    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < EPS:
        return None  # parallel or coincident

    dx3 = p3.x() - p1.x()
    dy3 = p3.y() - p1.y()

    t = (dx3 * dy2 - dy3 * dx2) / denom
    return QPointF(p1.x() + t * dx1, p1.y() + t * dy1)


def line_circle_intersections(p1: QPointF, p2: QPointF,
                              center: QPointF, radius: float) -> list[QPointF]:
    """Return 0, 1, or 2 intersection points of line SEGMENT with circle.

    Uses the parametric approach: point on segment = p1 + t*(p2-p1),
    then solves the quadratic for |point - center|^2 = radius^2.
    Only returns points where 0 <= t <= 1.
    """
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    fx = p1.x() - center.x()
    fy = p1.y() - center.y()

    a = dx * dx + dy * dy
    if a < EPS:
        # Degenerate segment (p1 == p2)
        dist_sq = fx * fx + fy * fy
        if abs(dist_sq - radius * radius) < EPS:
            return [QPointF(p1.x(), p1.y())]
        return []

    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius

    discriminant = b * b - 4.0 * a * c

    if discriminant < -EPS:
        return []

    results = []
    if abs(discriminant) < EPS:
        # Tangent -- single intersection
        t = -b / (2.0 * a)
        if -EPS <= t <= 1.0 + EPS:
            t = max(0.0, min(1.0, t))
            results.append(QPointF(p1.x() + t * dx, p1.y() + t * dy))
    else:
        sqrt_disc = math.sqrt(max(0.0, discriminant))
        for sign in (-1.0, 1.0):
            t = (-b + sign * sqrt_disc) / (2.0 * a)
            if -EPS <= t <= 1.0 + EPS:
                t = max(0.0, min(1.0, t))
                results.append(QPointF(p1.x() + t * dx, p1.y() + t * dy))

    return results


def line_circle_intersections_unbounded(p1: QPointF, p2: QPointF,
                                        center: QPointF,
                                        radius: float) -> list[QPointF]:
    """Return 0, 1, or 2 intersection points of infinite line with circle.

    Same parametric approach as line_circle_intersections but without
    clamping t to [0, 1]. Used for Extend-to-circle-boundary.
    """
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    fx = p1.x() - center.x()
    fy = p1.y() - center.y()

    a = dx * dx + dy * dy
    if a < EPS:
        return []

    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius

    discriminant = b * b - 4.0 * a * c

    if discriminant < -EPS:
        return []

    results = []
    if abs(discriminant) < EPS:
        t = -b / (2.0 * a)
        results.append(QPointF(p1.x() + t * dx, p1.y() + t * dy))
    else:
        sqrt_disc = math.sqrt(max(0.0, discriminant))
        for sign in (-1.0, 1.0):
            t = (-b + sign * sqrt_disc) / (2.0 * a)
            results.append(QPointF(p1.x() + t * dx, p1.y() + t * dy))

    return results


def _normalize_angle(deg: float) -> float:
    """Normalize an angle to the range [0, 360)."""
    deg = deg % 360.0
    if deg < 0.0:
        deg += 360.0
    return deg


def _angle_in_arc(angle_deg: float, start_deg: float, span_deg: float) -> bool:
    """Check whether angle_deg lies within the arc from start_deg over span_deg.

    span_deg may be positive (counter-clockwise) or negative (clockwise).
    All angles in degrees.
    """
    angle = _normalize_angle(angle_deg)
    start = _normalize_angle(start_deg)

    if abs(span_deg) >= 360.0 - EPS:
        return True  # full circle

    if span_deg > 0:
        # Counter-clockwise arc
        end = _normalize_angle(start + span_deg)
        if start < end:
            return start - EPS <= angle <= end + EPS
        else:
            # Arc wraps around 0 degrees
            return angle >= start - EPS or angle <= end + EPS
    else:
        # Clockwise arc: flip direction
        end = _normalize_angle(start + span_deg)
        if end < start:
            return end - EPS <= angle <= start + EPS
        else:
            # Arc wraps around 0 degrees
            return angle >= end - EPS or angle <= start + EPS


def line_arc_intersections(p1: QPointF, p2: QPointF,
                           center: QPointF, radius: float,
                           start_deg: float,
                           span_deg: float) -> list[QPointF]:
    """Intersect line segment with arc (subset of circle).

    The arc is defined by center, radius, start_deg, and span_deg
    (counter-clockwise positive, clockwise negative).
    Only returns points that lie both on the segment AND the arc's
    angular range.
    """
    # Get all segment-circle intersections first
    circle_hits = line_circle_intersections(p1, p2, center, radius)

    results = []
    for pt in circle_hits:
        # Compute the angle of this point relative to the arc centre
        angle = math.degrees(math.atan2(pt.y() - center.y(),
                                        pt.x() - center.x()))
        if _angle_in_arc(angle, start_deg, span_deg):
            results.append(pt)

    return results


def circle_circle_intersections(c1: QPointF, r1: float,
                                c2: QPointF, r2: float) -> list[QPointF]:
    """Compute intersection points of two circles.

    Returns 0, 1, or 2 intersection points.
    """
    dx = c2.x() - c1.x()
    dy = c2.y() - c1.y()
    d = math.hypot(dx, dy)

    # No intersection cases
    if d > r1 + r2 + EPS:
        return []  # circles too far apart
    if d < abs(r1 - r2) - EPS:
        return []  # one circle inside the other
    if d < EPS:
        return []  # concentric circles (infinite or zero intersections)

    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h_sq = r1 * r1 - a * a

    # Mid-point along the line connecting centres
    mx = c1.x() + a * dx / d
    my = c1.y() + a * dy / d

    if h_sq < -EPS:
        return []

    if h_sq < EPS:
        # Single tangent point
        return [QPointF(mx, my)]

    h = math.sqrt(max(0.0, h_sq))
    # Perpendicular offset
    ox = h * dy / d
    oy = h * dx / d

    return [
        QPointF(mx + ox, my - oy),
        QPointF(mx - ox, my + oy),
    ]


def point_on_segment_param(p: QPointF, p1: QPointF,
                           p2: QPointF) -> float:
    """Return parametric t for point p projected onto segment p1-p2.

    t = 0 at p1, t = 1 at p2.  The result is NOT clamped, so values
    outside [0, 1] indicate the projection falls beyond the segment.
    """
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    len_sq = dx * dx + dy * dy

    if len_sq < EPS:
        return 0.0  # degenerate segment

    t = ((p.x() - p1.x()) * dx + (p.y() - p1.y()) * dy) / len_sq
    return t


def nearest_intersection(click_pt: QPointF,
                          intersections: list[QPointF]) -> QPointF | None:
    """From a list of intersection points, return the one nearest to click_pt.

    Returns None if the list is empty.
    """
    if not intersections:
        return None

    best = None
    best_dist_sq = float('inf')

    for pt in intersections:
        dx = pt.x() - click_pt.x()
        dy = pt.y() - click_pt.y()
        dist_sq = dx * dx + dy * dy
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best = pt

    return best
