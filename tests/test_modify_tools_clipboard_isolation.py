"""scene-tools.md I1: internal copy paths never round-trip the OS clipboard,
and only the versioned payload is ever read from it."""
import json

import pytest
from PyQt6.QtCore import QObject, QPointF, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import close_view, make_view


class _DeadClip(QObject):
    """A clipboard whose writes never land (the machine-wide ACCESS_DENIED
    case); reads return a stale foreign value."""
    dataChanged = pyqtSignal()

    def __init__(self, stale):
        super().__init__()
        self._t = stale
        self.writes = 0

    def text(self, *a):
        return self._t

    def setText(self, t, *a):
        self.writes += 1


@pytest.fixture
def dead_clip(monkeypatch):
    stale = json.dumps([LineItem(QPointF(0, 0), QPointF(5, 0)).to_dict()] * 3)
    clip = _DeadClip(stale)
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: clip))
    monkeypatch.setattr(QGuiApplication, "clipboard", staticmethod(lambda: clip))
    return clip


def test_array_does_not_touch_the_clipboard(qapp, dead_clip):
    view, scene = make_view(scale=1.0)
    try:
        a = LineItem(QPointF(0, 0), QPointF(100, 0))
        scene.addItem(a); scene._draw_lines.append(a); a.setSelected(True)
        scene.array_items({"mode": "linear", "rows": 1, "cols": 3,
                           "x_spacing": 200, "y_spacing": 0})
        assert len(scene._draw_lines) == 3                              # [RED]
        xs = sorted(round(l.line().p1().x()) for l in scene._draw_lines)
        assert xs == [0, 200, 400]
        assert dead_clip.writes == 0
    finally:
        close_view(view, scene)


def test_copy_to_level_does_not_touch_the_clipboard(qapp, dead_clip):
    view, scene = make_view(role="plan", scale=1.0)
    try:
        node = scene.add_node(100.0, 100.0)
        n0 = len(scene.sprinkler_system.nodes)
        scene.copy_items_to_level([node], scene.active_level)
        assert len(scene.sprinkler_system.nodes) >= n0                  # node dedupes at 0 offset
        assert dead_clip.writes == 0                                    # [RED]
    finally:
        close_view(view, scene)


def test_clipboard_data_ignores_a_bare_list(qapp, dead_clip):
    view, scene = make_view(scale=1.0)
    try:
        assert scene.clipboard_data() is None                           # [RED]
        n0 = len(scene._draw_lines)
        scene.paste_items(QPointF(0, 0))                                # nothing to read
        assert len(scene._draw_lines) == n0
    finally:
        close_view(view, scene)


def test_cut_with_a_dead_clipboard_deletes_nothing(qapp, dead_clip):
    """Q2 / D4: a Cut whose clipboard write did not land must not delete."""
    from tests._modify_tools_helpers import add_primitive
    from tests._snap_polish_helpers import click
    view, scene = make_view(scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        item, attr = add_primitive(scene, "rect")
        p0 = scene._undo_pos
        scene._modify_ctl.start("cut")
        click(view, QPointF(400, 300))
        assert getattr(scene, attr) == [item]                           # [RED]
        assert item.scene() is scene
        assert scene._undo_pos == p0
        assert msgs[-1] == "Clipboard unavailable — nothing copied"
        assert scene.mode in (None, "select")
        assert item.isSelected()
    finally:
        close_view(view, scene)


def test_copy_with_a_dead_clipboard_reports_it(qapp, dead_clip):
    from tests._modify_tools_helpers import add_primitive
    from tests._snap_polish_helpers import click
    view, scene = make_view(scale=1.0)
    try:
        msgs = []
        scene._show_status = lambda m, timeout=5000: msgs.append(m)
        add_primitive(scene, "line")
        scene._modify_ctl.start("copy")
        click(view, QPointF(400, 300))
        assert msgs[-1] == "Clipboard unavailable — nothing copied"
    finally:
        close_view(view, scene)
