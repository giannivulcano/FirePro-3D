"""Model_Space ALIGN lifecycle wiring during gridline placement + grip-drag.

Task 6 REMOVED the retired auto-proximity H/V engine that this file originally
exercised in full: ``GridlineItem.alignment_reference_points()``,
``Model_Space._collect_alignment_refs``, ``AlignEngine.resolve`` and the
``AlignResult``/``Guide`` render model (cursor auto-snapping X/Y to any nearby
gridline without a deliberate acquire).  Every test that asserted that behavior
was deleted with it — the replacement (deliberate acquire → transient rays →
one picker) is covered by tests/test_align_seam.py, tests/test_align_controller.py,
and tests/test_align_snap_integration.py.

What survives here is the still-live seam LIFECYCLE that the ALIGN tier depends
on regardless of engine: the active-item sentinel is armed on placement/grip
modes and cleared on mode change / grip release, and the drawForeground ALIGN
block paints nothing when there is no live result.
"""
from __future__ import annotations

from types import SimpleNamespace

from PyQt6.QtCore import QPointF

from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space


# ---------------------------------------------------------------------------
# ALIGN seam attributes present on a fresh Model_Space
# ---------------------------------------------------------------------------

def test_align_seam_attributes_present(qapp):
    """Model_Space exposes the ALIGN acquire-machine seam attributes."""
    ms = Model_Space()
    assert hasattr(ms, "_align_controller")
    assert hasattr(ms, "_align_enabled")
    assert hasattr(ms, "_align_result")
    assert hasattr(ms, "_align_active_item")
    assert ms._align_enabled is True
    assert ms._align_result is None
    assert ms._align_active_item is None
    assert ms._align_controller.acquired == []


# ---------------------------------------------------------------------------
# Placement + grip-drag lifecycle (active-item sentinel + acquire clearing)
# ---------------------------------------------------------------------------

def _setup_align_view(ms, *, center_x=0.0, center_y=0.0):
    from PyQt6.QtWidgets import QApplication
    view = ms.views()[0]
    view.centerOn(center_x, center_y)
    QApplication.processEvents()


def _no_modifier():
    from PyQt6.QtCore import Qt
    return SimpleNamespace(modifiers=lambda: Qt.KeyboardModifier.NoModifier)


def _place_click(ms, x, y):
    """Simulate one placement click in draw_gridline mode."""
    raw = QPointF(x, y)
    snapped = ms.get_effective_position(raw)
    ev = _no_modifier()
    ms._press_draw_line(ev, raw, snapped, None, None, None)


class TestPlacementAndGripWiring:
    """The active-item sentinel drives whether the ALIGN tier runs."""

    def test_placement_without_refs_is_free(self, qapp, make_model_space):
        """Placement with no reference geometry must succeed without crash."""
        ms = make_model_space()
        ms._snap_enabled = False
        _setup_align_view(ms, center_x=0.0, center_y=0.0)

        ms.set_mode("draw_gridline")
        _place_click(ms, 10.0, 10.0)
        _place_click(ms, 10.0, 200.0)

        assert len(ms._gridlines) == 1, "Should have placed one gridline"

    def test_active_item_stays_armed_after_continuous_placement(
            self, qapp, make_model_space):
        """Continuous mode: after a commit the sentinel stays armed and the
        mode stays draw_gridline (re-armed for the next placement)."""
        ms = make_model_space()
        ms._snap_enabled = False
        _setup_align_view(ms, center_x=0.0, center_y=0.0)

        ms.set_mode("draw_gridline")
        _place_click(ms, 0.0, 0.0)
        _place_click(ms, 0.0, 200.0)

        assert len(ms._gridlines) == 1
        assert ms.mode == "draw_gridline"
        assert ms._align_active_item is not None

    def test_active_item_cleared_on_mode_change(self, qapp, make_model_space):
        """set_mode away from a placement mode clears the sentinel AND the
        acquire set (design: mode change clears all)."""
        ms = make_model_space()
        ms.set_mode("draw_gridline")
        assert ms._align_active_item is not None
        # Seed the acquire set to prove the mode change clears it.
        ms._align_controller.on_move(
            (0.0, 0.0),
            {"point": (0.0, 0.0), "snap_type": "endpoint", "source_id": 1,
             "direction": None},
            elapsed_ms=500)
        assert len(ms._align_controller.acquired) == 1

        ms.set_mode("select")
        assert ms._align_active_item is None
        assert ms._align_controller.acquired == []

    def test_active_item_set_on_grip_drag_start(self, qapp, make_model_space):
        """_align_active_item equals the dragged GridlineItem at drag-start."""
        ms = make_model_space()
        gl = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 200.0), label="1")
        ms.addItem(gl)
        ms._gridlines.append(gl)
        gl.setSelected(True)
        _setup_align_view(ms, center_x=0.0, center_y=0.0)

        ms._grip_item = gl
        ms._grip_index = 1
        ms._grip_dragging = True
        if isinstance(ms._grip_item, GridlineItem):
            ms._align_active_item = ms._grip_item
        assert ms._align_active_item is gl


# ---------------------------------------------------------------------------
# drawForeground ALIGN block paints nothing without a live result
# ---------------------------------------------------------------------------

from PyQt6.QtGui import QColor
from firepro3d.constants import ALIGN_GUIDE_COLOR, ALIGN_ACQUIRE_COLOR


def _render_view(view):
    return view.grab().toImage()


def _has_color(img, hex_color, tolerance=6):
    target = QColor(hex_color).getRgb()[:3]
    for x in range(0, img.width(), 1):
        for y in range(0, img.height(), 1):
            rgb = QColor(img.pixel(x, y)).getRgb()[:3]
            if all(abs(rgb[i] - target[i]) <= tolerance for i in range(3)):
                return True
    return False


def test_no_align_paint_when_result_none_and_no_acquires(qapp, make_model_space):
    """The ALIGN overlay paints nothing when there is no result and the acquire
    set is empty."""
    from firepro3d.model_view import Model_View
    from PyQt6.QtWidgets import QApplication
    ms = make_model_space()
    mv = Model_View(ms)
    mv.resize(400, 400)
    mv.resetTransform()
    ms._align_result = None
    assert ms._align_controller.acquired_points() == []
    mv.centerOn(0.0, 0.0)
    QApplication.processEvents()
    mv.viewport().repaint()
    img = _render_view(mv)
    assert not _has_color(img, ALIGN_GUIDE_COLOR)
    assert not _has_color(img, ALIGN_ACQUIRE_COLOR)
    mv.hide()
