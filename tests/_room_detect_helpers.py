"""Real-path helpers for the room-detection rework guards (design 2026-11-12).

Walls go through the wall tool's press-dispatch handler (``Model_Space._PRESS_DISPATCH
["wall"]`` -> ``WallPlacementController._press_wall``, auto-join included) at exact points
(event None: no OSNAP drift, as the 1b probe drove it). Rooms are placed by real posted
clicks on a shown Model_View in Room mode (the scene's own press dispatch).
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.wall import ALIGN_CENTER, WallSegment
from tests._snap_polish_helpers import click, make_view


def room_view(scale: float = 0.1):
    """``(view, scene)``: a shown plan-role Model_View (LevelManager, Level 1 active)."""
    return make_view(role="plan", scale=scale, mode=None)


def frame(view, center: QPointF, scale: float) -> None:
    """Pin the view's zoom to *scale* (px per mm) centred on *center*."""
    view.resetTransform()
    view.scale(scale, scale)
    view.centerOn(center)
    QApplication.processEvents()


def _arm_wall_tool(scene, primitive: str, align: str, th: float):
    scene.set_mode("wall")
    scene._wall_ctl._set_wall_primitive(primitive)
    tmpl = scene._get_wall_template()
    tmpl._thickness_mm = th
    tmpl._alignment = align
    scene._wall_alignment = align
    return getattr(scene, scene._PRESS_DISPATCH["wall"])


def wall_tool(scene, p1, p2, align: str = ALIGN_CENTER, th: float = 200.0):
    """One line wall through the wall tool: Wall mode, two presses at exact points."""
    press = _arm_wall_tool(scene, "line", align, th)
    for p in (p1, p2):
        q = QPointF(*p)
        press(None, q, q, None, None, None)
    return scene._walls[-1]


def rect_walls(scene, x0, y0, x1, y1, align: str = ALIGN_CENTER, th: float = 200.0,
               ccw: bool = True) -> list:
    """Four line walls (x0,y0)->(x1,y0)->(x1,y1)->(x0,y1) (ccw) or the reverse order (cw)."""
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if not ccw:
        pts = pts[::-1]
    return [wall_tool(scene, pts[i], pts[(i + 1) % 4], align, th) for i in range(4)]


def polyline_walls(scene, pts, align: str = ALIGN_CENTER, th: float = 200.0) -> list:
    """A polyline chain through the wall tool; Select mode ends the chain."""
    n0 = len(scene._walls)
    press = _arm_wall_tool(scene, "polyline", align, th)
    for p in pts:
        q = QPointF(*p)
        press(None, q, q, None, None, None)
    scene.set_mode("select")
    scene._wall_ctl._set_wall_primitive("line")
    return scene._walls[n0:]


def add_wall(scene, p1, p2, align: str = ALIGN_CENTER, th: float = 200.0):
    """A wall added directly (no auto-join) -- keeps a deliberate gap."""
    w = WallSegment(QPointF(*p1), QPointF(*p2), thickness_mm=th)
    w._alignment = align
    scene.addItem(w)
    scene._walls.append(w)
    return w


def settle(scene) -> None:
    """Rebuild every wall's joins after direct adds (the 1b probe idiom)."""
    for w in scene._walls:
        w.invalidate_geometry()


def click_room(view, pt: QPointF, scale: float = 2.0) -> None:
    """Zoom to *scale* centred on *pt* (OSNAP aperture << distance to any wall) and
    post a real left click there."""
    frame(view, pt, scale)
    click(view, pt)


def statuses(scene) -> list:
    """Record every status-bar message the scene shows from now on."""
    log: list = []
    orig = scene._show_status
    scene._show_status = lambda msg, timeout=5000: (log.append(msg), orig(msg, timeout))
    return log


def xy(pts) -> list:
    return [(p.x(), p.y()) for p in pts]


def area(pts) -> float:
    """Hand shoelace of (x, y) tuples -- the guards never read the module's area."""
    n = len(pts)
    s = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def _seg_x(a, b, c, d) -> bool:
    def o(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-6 else (1 if v > 0 else -1)
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def simple(pts) -> bool:
    """No two non-adjacent edges properly cross (the 1b bow-tie check)."""
    n = len(pts)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _seg_x(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n]):
                return False
    return True
