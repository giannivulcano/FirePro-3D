"""AC2 E2E: an exactly axis-aligned committed segment records H / V (any
cause), on the finishing press's toggle XOR Shift; typed follows the toggle."""
from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtWidgets import QApplication

from firepro3d.constants import AUTO_CONSTRAIN_KEY
from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import click, close_view, make_view, move

SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier
NONE = Qt.KeyboardModifier.NoModifier


@pytest.fixture
def vs(qapp):
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, True)
    view, sc = make_view(role="block_editor", scale=1.0, mode=None)
    sc.set_align_enabled(False)
    yield view, sc
    QSettings("GV", "FirePro3D").remove(AUTO_CONSTRAIN_KEY)
    close_view(view, sc)


def _recs(sc):
    return [(c.type, [(r.get("uid"), r.get("h"), r.get("ref")) for r in c.refs])
            for c in sc.constraint_ctl.constraints]


def _line(sc, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b)); sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _draw(view, sc, a, b, ma=NONE, mb=NONE):
    sc.set_mode("draw_line")
    move(view, QPointF(*a), ma); click(view, QPointF(*a), ma)
    move(view, QPointF(*b), mb); click(view, QPointF(*b), mb)
    return sc._draw_lines[-1]


# ── line / reference line ────────────────────────────────────────────────

def test_coincident_clicks_horizontal_and_vertical(vs):
    view, sc = vs
    h = _draw(view, sc, (310, 120), (470, 120))          # same pixel row, no snaps
    v = _draw(view, sc, (-310, 40), (-310, 260))
    assert _recs(sc) == [("horizontal", [(h._uid, "edge", None)]),
                         ("vertical", [(v._uid, "edge", None)])]


def test_one_degree_off_records_nothing(vs):
    view, sc = vs
    # tip 1 deg above +x over 160 mm: (310 + 160cos1, 120 - 160sin1) -> dy 2.79 mm
    tip = (310 + 160 * math.cos(math.radians(1)), 120 - 160 * math.sin(math.radians(1)))
    _draw(view, sc, (310, 120), tip)
    assert _recs(sc) == []


def test_ctrl_lock_at_90(vs):
    view, sc = vs
    n = _draw(view, sc, (310, 120), (318, 300), mb=CTRL)  # ~87.5 deg -> locked 90
    assert abs(n._pt2.x() - 310) < 1e-6                  # precondition: lock applied
    assert _recs(sc) == [("vertical", [(n._uid, "edge", None)])]


def test_typed_tip_at_0_follows_the_toggle(vs):
    view, sc = vs
    sc.set_mode("draw_line")
    move(view, QPointF(310, 120)); click(view, QPointF(310, 120))
    assert sc._geom_ctl._commit_draw_line_at(QPointF(500, 120))   # HUD applier = typed
    n = sc._draw_lines[-1]
    assert _recs(sc) == [("horizontal", [(n._uid, "edge", None)])]


def test_typed_tip_with_toggle_off_records_nothing(vs):
    view, sc = vs
    QSettings("GV", "FirePro3D").setValue(AUTO_CONSTRAIN_KEY, False)
    sc.set_mode("draw_line")
    move(view, QPointF(310, 120)); click(view, QPointF(310, 120))
    assert sc._geom_ctl._commit_draw_line_at(QPointF(500, 120))
    assert _recs(sc) == []


def test_shift_on_the_finishing_click_suppresses(vs):
    view, sc = vs
    _draw(view, sc, (310, 120), (470, 120), mb=SHIFT)
    assert _recs(sc) == []
    n = _draw(view, sc, (310, 220), (470, 220), ma=SHIFT)  # Shift on click 1 only
    assert _recs(sc) == [("horizontal", [(n._uid, "edge", None)])]


def test_align_hv_ray(vs):
    view, sc = vs
    sc.set_align_enabled(True)
    sc.set_mode("draw_line")
    move(view, QPointF(310, 200)); click(view, QPointF(310, 200))   # anchor on y = 200
    # Acquire a point on y = 200 (dwell crossed; tests/test_align_seam.py's
    # controller call), then click 4 px off its H path.
    sc._align_controller.on_move(
        (0.0, 200.0), {"point": (0.0, 200.0), "snap_type": "endpoint",
                       "source_id": 1, "direction": None}, elapsed_ms=500)
    move(view, QPointF(480, 204)); click(view, QPointF(480, 204))
    n = sc._draw_lines[-1]
    assert abs(n._pt2.y() - 200) < 1e-9                 # precondition: ALIGN projected
    assert ("horizontal", [(n._uid, "edge", None)]) in _recs(sc)


def test_joins_win_a_redundant_hv(vs):
    """R3: both ends coincident with two Fixed lines' ends at one height ->
    the new line's H is implied, so the H (added last) is the one dropped."""
    view, sc = vs
    a = _line(sc, (0, 300), (100, 300))
    b = _line(sc, (400, 300), (500, 300))
    ctl = sc.constraint_ctl
    ctl.add("fix", [{"uid": a._uid, "h": "item"}]); ctl.add("fix", [{"uid": b._uid, "h": "item"}])
    n0 = len(ctl.constraints)
    n = _draw(view, sc, (100, 300), (400, 300))
    assert _recs(sc)[n0:] == [
        ("coincident", [(n._uid, "p1", None), (a._uid, "p2", None)]),
        ("coincident", [(n._uid, "p2", None), (b._uid, "p1", None)])]


def test_line_and_hv_are_one_undo_step(vs):
    view, sc = vs
    sc.push_undo_state()
    n_lines = len(sc._draw_lines)
    _draw(view, sc, (310, 120), (470, 120))
    assert len(sc.constraint_ctl.constraints) == 1
    sc.undo(); QApplication.processEvents()
    assert len(sc._draw_lines) == n_lines and sc.constraint_ctl.constraints == []


def test_gridline_gets_no_hv(vs):
    view, sc = vs
    sc.set_mode("draw_gridline")
    if sc.mode != "draw_gridline":
        pytest.skip("draw_gridline is refused in this scene role")
    move(view, QPointF(310, 120)); click(view, QPointF(310, 120))
    move(view, QPointF(470, 120)); click(view, QPointF(470, 120))
    assert _recs(sc) == []
