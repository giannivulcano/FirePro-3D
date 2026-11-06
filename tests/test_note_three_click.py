"""Notes design N20 to N24: the Note tool places by tip, elbow, box edge."""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem

from firepro3d import text_leader as _tl
from firepro3d.constants import TEXT_LEADER_MIN_SHOULDER_MM
from firepro3d.system_blocks import NOTE_BLOCK_ID
from firepro3d.text_item import editing_text_item
from firepro3d.text_leader import attach_and_knee, box_from_clicks
from tests._note_helpers import click, key, mouse
from tests.test_note_instance import leader_op

W, H, MIN = 6000.0, 700.0, 200.0
K = QPointF(1000.0, 500.0)


@pytest.mark.parametrize("click, edge, want_attach", [
    (QPointF(1800.0, 700.0), "L", (1800.0, 500.0)),       # right of the elbow: the box's left edge
    (QPointF(200.0, 300.0), "R", (200.0, 500.0)),         # left of it: the right edge
    (QPointF(1100.0, 1400.0), "T", (1000.0, 1400.0)),     # below: the top edge
    (QPointF(900.0, -300.0), "B", (1000.0, -300.0)),      # above: the bottom edge
])
def test_the_click_names_the_edge_and_only_its_axis_counts(click, edge, want_attach):
    box, rec = box_from_clicks(K, click, W, H, MIN)
    assert rec["edge"] == edge
    a, k = attach_and_knee(box, rec)
    assert (a.x(), a.y()) == pytest.approx(want_attach)
    assert (k.x(), k.y()) == pytest.approx((K.x(), K.y()))       # the record lands on the elbow


def test_a_diagonal_tie_takes_a_side_edge():
    assert box_from_clicks(K, QPointF(1300.0, 800.0), W, H, MIN)[1]["edge"] == "L"
    assert box_from_clicks(K, QPointF(700.0, 200.0), W, H, MIN)[1]["edge"] == "R"


@pytest.mark.parametrize("click, edge, far", [
    (QPointF(1050.0, 510.0), "L", "left"),
    (QPointF(950.0, 490.0), "R", "right"),
    (QPointF(1010.0, 550.0), "T", "top"),
    (QPointF(990.0, 450.0), "B", "bottom"),
    (K, "L", "left"),                                     # a click on the elbow itself
])
def test_a_short_click_lands_at_the_minimum_shoulder(click, edge, far):
    box, rec = box_from_clicks(K, click, W, H, MIN)
    assert rec["edge"] == edge and rec["shoulder_mm"] == MIN
    a, k = attach_and_knee(box, rec)
    assert (k.x(), k.y()) == pytest.approx((K.x(), K.y()))
    assert abs(a.x() - k.x()) + abs(a.y() - k.y()) == pytest.approx(MIN)


@pytest.mark.parametrize("click", [QPointF(1800.0, 500.0), QPointF(200.0, 500.0),
                                   QPointF(1000.0, 1400.0), QPointF(1000.0, -300.0)])
def test_the_box_keeps_its_size_and_extends_away_from_the_elbow(click):
    box, _rec = box_from_clicks(K, click, W, H, MIN)
    assert (box.width(), box.height()) == (W, H)
    assert not box.contains(K)
