from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from firepro3d.elevation_scene import ElevGridlineItem


def _grid():
    return ElevGridlineItem(100.0, -50.0, 50.0, "A", 20.0,
                            QColor("#888"), QColor("#fff"), 1.0)


def test_gridline_manip_handles_two_round_grips(qapp):
    g = _grid()
    handles = g.manip_handles()
    assert len(handles) == 2                       # both endpoints
    # both endpoints render round (circular={0,1}); real GripHandle
    # attribute is `.circular` (manip_handle.py:GripHandle.__init__).
    assert all(h.circular for h in handles)
    assert [h.index for h in handles] == [0, 1]


def test_gridline_has_no_manip_translate(qapp):
    # §3.1: no interior-move -> no manip_translate (would allow lateral H shift)
    assert not hasattr(_grid(), "manip_translate")


def test_gridline_manip_handle_apply_matches_apply_grip(qapp):
    g = _grid()
    g.manip_handles()[1]  # sanity
    g.apply_grip(1, QPointF(999.0, 80.0))          # x ignored, pinned to _h
    line = g.line()
    assert line.p2().x() == 100.0                  # H pinned
    assert line.p2().y() == 80.0                   # extent moved
