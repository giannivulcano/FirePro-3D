"""S3b guard — a 2-point polyline finish (Enter / double-click) commits a Line.

Block-Editor scene (polyline authoring is Block-Editor-only), real shown view,
posted mouse events and a real Return key. A single segment IS a line: the
finished item must be a ``LineItem`` in ``_draw_lines`` (selected, back in
Select), with no ``PolylineItem`` left behind. A 3-point finish still yields a
``PolylineItem`` (control).
"""
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem, PolylineItem
from tests._snap_polish_helpers import click, close_view, make_view, move, post


def _finish(view, how, last):
    if how == "enter":
        QTest.keyClick(view, Qt.Key.Key_Return)
        QApplication.processEvents()
    else:
        # Qt delivers Press → Release → DblClick → Release for a double click.
        post(view, QEvent.Type.MouseButtonPress, last)
        post(view, QEvent.Type.MouseButtonRelease, last)
        post(view, QEvent.Type.MouseButtonDblClick, last)
        post(view, QEvent.Type.MouseButtonRelease, last)


def _place(scene, view, pts, how, monkeypatch=None):
    scene.set_mode("polyline")
    QApplication.processEvents()
    for p in pts:
        move(view, p)
        click(view, p)
    assert scene._polyline_active is not None
    assert len(scene._polyline_active._points) == len(pts)
    calls = []
    if monkeypatch is not None:
        real = scene.push_undo_state
        monkeypatch.setattr(scene, "push_undo_state",
                            lambda *a, **k: (calls.append(1), real(*a, **k)))
    _finish(view, how, pts[-1])
    return calls


def _geo(scene):
    return [i for i in scene.items() if isinstance(i, (LineItem, PolylineItem))]


@pytest.mark.parametrize("how", ["enter", "dblclick"])
def test_two_point_finish_commits_a_line(qapp, how, monkeypatch):
    view, scene = make_view(role="block_editor")
    try:
        calls = _place(scene, view, [QPointF(0, 0), QPointF(1000, 0)], how,
                       monkeypatch)
        assert scene._polyline_active is None
        assert len(scene._polylines) == 0
        assert not any(isinstance(i, PolylineItem) for i in scene.items())
        lines = [i for i in scene._draw_lines if type(i) is LineItem]
        assert len(lines) == 1, scene._draw_lines
        ln = lines[0]
        assert ln.scene() is scene
        g = ln.grip_points()
        assert (g[0].x(), g[0].y()) == (0.0, 0.0)
        assert (g[2].x(), g[2].y()) == (1000.0, 0.0)
        assert ln.to_dict()["type"] == "draw_line"
        assert ln.get_properties()["Type"]["value"] == "Line"
        assert ln.isSelected()
        assert scene.selectedItems() == [ln]
        assert scene.mode == "select"
        assert calls == [1]                  # exactly one undo push
        # committed pen is solid (not the dashed placement ghost)
        assert ln.pen().style() == Qt.PenStyle.SolidLine
    finally:
        close_view(view, scene)


@pytest.mark.parametrize("how", ["enter", "dblclick"])
def test_three_point_finish_still_commits_a_polyline(qapp, how):
    view, scene = make_view(role="block_editor")
    try:
        _place(scene, view, [QPointF(0, 0), QPointF(1000, 0),
                             QPointF(1000, -1000)], how)
        assert scene._polyline_active is None
        assert len(scene._polylines) == 1
        pl = scene._polylines[0]
        assert len(pl._points) == 3
        assert pl.isSelected()
        assert scene.mode == "select"
        assert not any(type(i) is LineItem for i in _geo(scene))
    finally:
        close_view(view, scene)


def test_two_point_line_keeps_colour_and_lineweight(qapp):
    view, scene = make_view(role="block_editor")
    try:
        scene.set_mode("polyline")
        click(view, QPointF(0, 0))
        pl = scene._polyline_active
        # Placement ghost pen carries the template colour; finalize() restores
        # the committed width from _lineweight.
        exp_color = QColor(pl.pen().color())
        exp_lw = pl._lineweight
        click(view, QPointF(1000, 0))
        QTest.keyClick(view, Qt.Key.Key_Return)
        QApplication.processEvents()
        ln = scene._draw_lines[-1]
        assert type(ln) is LineItem
        assert ln.pen().color() == exp_color
        assert ln.pen().widthF() == pytest.approx(exp_lw)
    finally:
        close_view(view, scene)
