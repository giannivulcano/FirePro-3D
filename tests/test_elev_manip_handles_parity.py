from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QFont

from firepro3d.elevation_scene import ElevGridlineItem, ElevDatumItem


def _grid():
    return ElevGridlineItem(100.0, -50.0, 50.0, "A", 20.0,
                            QColor("#888"), QColor("#fff"), 1.0)


def _datum():
    return ElevDatumItem(200.0, -50.0, 50.0, "Level 1", "0'-0\"", 20.0,
                         QColor("#48c"), QColor("#fff"), 1.0,
                         QFont("Consolas"), QFont("Consolas"))


def test_gridline_manip_handles_two_round_grips(qapp):
    g = _grid()
    handles = g.manip_handles()
    assert len(handles) == 2                       # both endpoints
    # both endpoints render round (circular={0,1}); real GripHandle
    # attribute is `.circular` (manip_handle.py:GripHandle.__init__).
    assert all(h.circular for h in handles)
    assert [h.index for h in handles] == [0, 1]


def test_gridline_interior_move_keeps_H_pinned(qapp):
    # §3.1: interior-move is axis-constrained — dx ignored (H stays pinned to
    # self._h), dy shifts the vertical extent. This grants the "translate"
    # capability so the manipulator wraps the item without allowing lateral H
    # authoring.
    g = _grid()   # H=100
    g.manip_translate(40.0, 20.0)          # dx ignored, dy shifts extent
    line = g.line()
    assert line.p1().x() == 100.0 and line.p2().x() == 100.0   # H pinned (§3.1)
    # both endpoints moved by dy
    assert line.p1().y() == -50.0 + 20.0 and line.p2().y() == 50.0 + 20.0


def test_datum_interior_move_keeps_V_pinned(qapp):
    # §3.1 twin: datum's V is pinned (self._v); dy ignored, dx shifts the
    # horizontal extent.
    d = _datum()   # V=200, extent h_min=-50 .. h_max=50
    line0 = d.line()
    x1_0, x2_0 = line0.p1().x(), line0.p2().x()
    d.manip_translate(40.0, 20.0)          # dy ignored, dx shifts extent
    line = d.line()
    assert line.p1().y() == 200.0 and line.p2().y() == 200.0   # V pinned (§3.1)
    assert line.p1().x() == x1_0 + 40.0 and line.p2().x() == x2_0 + 40.0


def test_gridline_manip_handle_apply_matches_apply_grip(qapp):
    g = _grid()
    g.manip_handles()[1]  # sanity
    g.apply_grip(1, QPointF(999.0, 80.0))          # x ignored, pinned to _h
    line = g.line()
    assert line.p2().x() == 100.0                  # H pinned
    assert line.p2().y() == 80.0                   # extent moved
