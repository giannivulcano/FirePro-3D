"""Two-click Section tool (spec s9, D5): click A, dashed preview with a look-side
hint, click B -> place_section(A, B); < 100 mm rejected; Esc cancels."""
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsLineItem

from firepro3d.section_marker import SectionMarker


class _PlaceMgr:
    def __init__(self):
        self.placed = []
    def place_section(self, a, b):
        m = SectionMarker(f"Section {len(self.placed) + 1}", a, b)
        self.placed.append(m)
        return m
    def open_section(self, name): pass
    def on_marker_geometry_changed(self, marker): pass


@pytest.fixture
def plan(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.model_view import Model_View
    ms = Model_Space()
    ms._section_manager = _PlaceMgr()
    view = Model_View(ms)
    view.resize(800, 600); view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform(); view.scale(0.5, 0.5)       # deterministic 2 mm / px
    view.centerOn(0, 0)
    yield ms, view
    view.close()


def _click(view, ms, x, y):
    vp = view.mapFromScene(QPointF(x, y))
    QTest.mouseMove(view.viewport(), vp)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, vp)


def _move(view, x, y):
    """A real MouseMove on the viewport (QTest.mouseMove posts none without a button)."""
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication
    pt = QPointF(view.mapFromScene(QPointF(x, y)))
    QApplication.sendEvent(view.viewport(), QMouseEvent(
        QEvent.Type.MouseMove, pt, view.viewport().mapToGlobal(pt), Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


def test_two_clicks_place_section_1_then_2(plan):
    ms, view = plan
    ms._snap_enabled = False
    ms.set_mode("section")
    _click(view, ms, -1000.0, 0.0)
    assert ms.mode == "section" and ms._section_anchor is not None
    assert isinstance(ms._section_preview, QGraphicsLineItem)
    _click(view, ms, 1000.0, 0.0)
    mgr = ms._section_manager
    assert [m.name for m in mgr.placed] == ["Section 1"]
    a, b = mgr.placed[0].cut_a, mgr.placed[0].cut_b
    assert abs(a.x() + 1000.0) < 3.0 and abs(b.x() - 1000.0) < 3.0     # view px rounding
    assert ms.mode == "select" and ms._section_preview is None
    assert len(ms._undo_stack) >= 1
    ms.set_mode("section")
    _click(view, ms, -1000.0, 500.0); _click(view, ms, 1000.0, 500.0)
    assert [m.name for m in mgr.placed] == ["Section 1", "Section 2"]


def test_sub_100mm_cut_is_rejected_with_status(plan):
    ms, view = plan
    ms._snap_enabled = False
    msgs = []
    ms._show_status = lambda message, timeout=5000: msgs.append(message)   # status bar seam (model_space.py:939)
    ms.set_mode("section")
    _click(view, ms, 0.0, 0.0)
    _click(view, ms, 0.5, 0.0)
    assert ms._section_manager.placed == []
    assert ms.mode == "section" and ms._section_anchor is not None      # still waiting for B
    assert any("100" in m for m in msgs)


def test_escape_cancels_and_removes_preview(plan):
    ms, view = plan
    ms.set_mode("section")
    _click(view, ms, 0.0, 0.0)
    assert ms._section_preview is not None
    QTest.keyClick(view.viewport(), Qt.Key.Key_Escape)
    assert ms.mode in (None, "select")            # Esc -> set_mode(None) (keyPressEvent tool-mode exit)
    assert ms._section_anchor is None and ms._section_preview is None
    assert ms._section_manager.placed == []


def test_look_side_hint_reads_left_for_any_drag_direction(plan):
    ms, view = plan
    ms._snap_enabled = False
    ms.set_mode("section")
    _click(view, ms, 0.0, 0.0)
    for x, y in ((-1000.0, 0.0), (0.0, 1000.0)):       # right-to-left, then straight below A
        _move(view, x, y)
        assert "left" in (ms._draw_dim_hint or "")


def test_first_click_arms_align_so_the_second_point_snaps_to_the_h_ray(qapp):
    """Smoke ruling 2026-10-21: section placement must ALIGN like draw_line. After the
    first click the anchor feeds ALIGN's H/V rays; a cursor a few px off the horizontal
    through A lands exactly on it (real Model_View move + click)."""
    from tests._snap_polish_helpers import click, close_view, make_view, move
    view, scene = make_view(mode="section", scale=0.5)
    try:
        scene._section_manager = _PlaceMgr()
        scene._snap_enabled = False                      # ALIGN only (no real snaps)
        click(view, QPointF(0.0, 0.0))
        assert scene._mode_placement_anchor() == QPointF(0.0, 0.0)
        cursor = QPointF(3000.0, 8.0)                    # 4 px above the H ray at 0.5 px/mm
        move(view, cursor)
        res = scene._align_result
        assert res is not None and res.snap_type in ("align_path", "align_intersection"), (
            res, scene._snap_result)
        assert scene._section_preview.line().p2() == QPointF(3000.0, 0.0)
        click(view, cursor)
        placed = scene._section_manager.placed
        assert len(placed) == 1 and placed[0].cut_b == QPointF(3000.0, 0.0)
    finally:
        close_view(view, scene)


def test_ctrl_second_click_constrains_the_cut_to_the_angle_increment(qapp):
    from tests._snap_polish_helpers import click, close_view, make_view, move
    view, scene = make_view(mode="section", scale=0.5)
    try:
        scene._section_manager = _PlaceMgr()
        scene._snap_enabled = False
        scene.set_align_enabled(False)                   # isolate the Ctrl constraint
        click(view, QPointF(0.0, 0.0))
        ctrl = Qt.KeyboardModifier.ControlModifier
        move(view, QPointF(4000.0, 500.0), ctrl)         # 7 deg off: rounds to 0 deg
        p2 = scene._section_preview.line().p2()
        assert p2.y() == pytest.approx(0.0, abs=1e-6) and p2.x() == pytest.approx(4031.129, abs=0.01)
        click(view, QPointF(4000.0, 500.0), ctrl)
        placed = scene._section_manager.placed
        assert len(placed) == 1
        assert placed[0].cut_b.y() == pytest.approx(0.0, abs=1e-6)
        assert placed[0].cut_b.x() == pytest.approx(4031.129, abs=0.01)
    finally:
        close_view(view, scene)
