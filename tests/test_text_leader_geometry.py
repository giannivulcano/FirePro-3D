"""Pure leader geometry (design D3, D4). No Qt scene needed."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from firepro3d import text_leader as tl

BOX = QRectF(0.0, 0.0, 100.0, 50.0)


def rec(edge="R", t=0.5, shoulder=20.0):
    return {"edge": edge, "t": t, "shoulder_mm": shoulder}


@pytest.mark.parametrize("edge,attach,knee", [
    ("R", (100, 25), (120, 25)), ("L", (0, 25), (-20, 25)),
    ("T", (50, 0), (50, -20)), ("B", (50, 50), (50, 70)),
])
def test_shoulder_leaves_each_edge_at_a_right_angle(edge, attach, knee):
    a, k = tl.attach_and_knee(BOX, rec(edge))
    assert (a.x(), a.y()) == attach and (k.x(), k.y()) == knee


def test_knee_drag_keeps_edge_and_slides_attach():
    out = tl.solve_knee(BOX, QPointF(130.0, 10.0), rec())
    assert out["edge"] == "R" and out["t"] == pytest.approx(0.2)
    assert out["shoulder_mm"] == pytest.approx(30.0)


def test_furthest_outside_axis_picks_the_edge():
    assert tl.solve_knee(BOX, QPointF(110.0, 90.0), rec())["edge"] == "B"


def test_past_a_corner_clamps_along_the_edge_and_stays_perpendicular():
    out = tl.solve_knee(BOX, QPointF(150.0, 60.0), rec())
    assert out["edge"] == "R" and out["t"] == 1.0
    a, k = tl.attach_and_knee(BOX, out)
    assert a.y() == k.y() == 50.0


def test_tie_keeps_the_current_edge():
    assert tl.solve_knee(BOX, QPointF(120.0, 70.0), rec("B"))["edge"] == "B"


def test_knee_inside_the_box_lands_on_the_nearest_edge_at_the_minimum():
    from firepro3d.constants import TEXT_LEADER_MIN_SHOULDER_MM as M
    out = tl.solve_knee(BOX, QPointF(95.0, 25.0), rec("L"))
    assert out["edge"] == "R" and out["shoulder_mm"] == M


def test_resize_keeps_edge_and_fraction():
    bigger = QRectF(0.0, 0.0, 200.0, 100.0)
    a, k = tl.attach_and_knee(bigger, rec("R", 0.2))
    assert (a.x(), a.y()) == (200.0, 20.0) and (k.x(), k.y()) == (220.0, 20.0)


def test_default_record_sits_right_of_the_box_with_the_arrow():
    d = tl.default_leader(BOX, QPointF(0.0, 0.0))
    assert d["edge"] == "R" and d["t"] == 0.5 and d["end"] == tl.DEFAULT_END_ID
    assert d["tip_x"] > 100.0 and d["tip_y"] > 25.0


def test_normalise_rejects_corrupt_records():
    assert tl.normalise(None) is None
    assert tl.normalise({"edge": "X"}) is None
    assert tl.normalise({"edge": "R", "t": 2.0, "shoulder_mm": 5.0,
                         "tip_x": 1, "tip_y": 2})["t"] == 1.0
