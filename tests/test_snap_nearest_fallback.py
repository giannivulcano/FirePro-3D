"""Smoke item 1 guard — with no placement start point there is NO cursor-foot
``perpendicular``: the foot on a line/circle is ``nearest`` (⊥ exists only as
true PER-from-start)."""
import math

from PyQt6.QtCore import QEvent, QPointF

from firepro3d.geometry_2d import CircleItem, LineItem
from tests._snap_polish_helpers import close_view, make_view, move, post

R = 500.0


def test_grip_drag_without_start_point_snaps_nearest_not_perpendicular(qapp):
    view, scene = make_view(scale=0.25)            # block editor, select mode
    try:
        scene.addItem(CircleItem(QPointF(0, 0), R))
        scene.addItem(LineItem(QPointF(-1000, 800), QPointF(1000, 800)))
        ln = LineItem(QPointF(-1200, -900), QPointF(-800, -900))
        scene.addItem(ln)
        scene.clearSelection()
        ln.setSelected(True)
        a = math.radians(-45)
        on_circle = QPointF((R + 12) * math.cos(a), (R + 12) * math.sin(a))   # 3 px out
        on_line = QPointF(300, 812)                                            # 3 px off, clear of mid/ends
        seen = []
        post(view, QEvent.Type.MouseButtonPress, ln.grip_points()[2])
        view._snap_polish_pressed = True
        try:
            for spt in (QPointF(-400, -600), on_circle, QPointF(700, 300), on_line):
                move(view, spt)
                seen.append(scene._snap_result)
        finally:
            view._snap_polish_pressed = False
        circ_res, line_res = seen[1], seen[3]
        assert circ_res is not None and circ_res.snap_type == "nearest", circ_res
        assert abs(math.hypot(circ_res.point.x(), circ_res.point.y()) - R) < 0.01
        assert line_res is not None and line_res.snap_type == "nearest", line_res
        assert math.hypot(line_res.point.x() - 300, line_res.point.y() - 800) < 4.01
        assert not any(r is not None and r.snap_type == "perpendicular" for r in seen), seen
        post(view, QEvent.Type.MouseButtonRelease, on_line)
        ep = ln.grip_points()[2]
        assert abs(ep.y() - 800) < 0.01            # committed ON the line
    finally:
        close_view(view, scene)
