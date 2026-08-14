"""
test_gridline_array_offset.py
==============================
Unit tests for GridlineItem.offset_copy() and GridlineItem.array_copies()
(Task 6 — pure geometry factory), and on-canvas Array/Offset interaction
modes on Model_Space (Task 7 — TDD).
"""

import math
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsView
from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space


# ---------------------------------------------------------------------------
# Shared fixture for Task 7 interaction tests
# ---------------------------------------------------------------------------

@pytest.fixture
def make_model_space(qapp):
    """Factory that builds a Model_Space with an attached QGraphicsView."""
    created = []

    def _factory():
        ms = Model_Space()
        view = QGraphicsView(ms)
        view.resize(800, 800)
        view.resetTransform()
        view.centerOn(0.0, 0.0)
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        created.append((ms, view))
        return ms

    yield _factory

    for ms, view in created:
        view.hide()


def test_offset_copy_translates_perpendicular(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")  # vertical
    cp = src.offset_copy(1000.0)
    # vertical line dir (0,1); perpendicular normal (-dy,dx)=(-1,0) → origin x -= 1000
    assert round(cp.grip_points()[0].x(), 1) == -1000.0
    assert round(cp._length, 1) == 5000.0
    assert round(cp._angle_deg, 3) == round(src._angle_deg, 3)
    assert cp.locked is False


def test_array_copies_count_and_spacing(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    cps = src.array_copies(spacing=1000.0, count=3)
    assert len(cps) == 3
    xs = [round(c.grip_points()[0].x(), 1) for c in cps]
    assert xs == [-1000.0, -2000.0, -3000.0]


def test_array_copies_angled_source_is_perpendicular(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(3000.0, -3000.0), label="1")  # dir (1,-1)/√2
    cps = src.array_copies(spacing=1000.0, count=1)
    o = cps[0].grip_points()[0]
    # perpendicular normal of dir (1,-1)/√2 is (-(-1),1)/√2 = (1,1)/√2
    assert round(o.x(), 1) == round(1000.0 * (1 / math.sqrt(2)), 1)
    assert round(o.y(), 1) == round(1000.0 * (1 / math.sqrt(2)), 1)


def test_copies_inherit_bubble_offsets_and_visibility(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    src.set_bubble_offset(1, 1500.0)
    src.set_bubble_visible(2, False)
    cp = src.offset_copy(500.0)
    assert round(cp._bubble1_offset, 1) == 1500.0
    assert cp.bubble2.isVisible() is False


def test_copies_inherit_display_overrides_as_copy(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    src._display_overrides["color"] = "#ff0000"
    cp = src.offset_copy(500.0)
    assert cp._display_overrides == {"color": "#ff0000"}
    cp._display_overrides["color"] = "#00ff00"   # mutating copy must not affect src
    assert src._display_overrides["color"] == "#ff0000"


def test_array_copies_zero_count_is_empty(qapp):
    src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
    assert src.array_copies(1000.0, 0) == []


# ===========================================================================
# Task 7 — on-canvas Array/Offset interaction (TDD)
# ===========================================================================

class TestContextMenuActions:
    """entity_context_menu.build_entity_context_menu adds gridline actions."""

    def test_context_menu_has_gridline_actions(self, qapp):
        from firepro3d.entity_context_menu import build_entity_context_menu
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000), label="1")
        menu = build_entity_context_menu(
            [gl], gl,
            on_array_gridline=lambda: None,
            on_offset_gridline=lambda: None,
        )
        labels = [a.text() for a in menu.actions()]
        assert any("Array Gridlines" in l for l in labels)
        assert any("Offset Gridline" in l for l in labels)

    def test_no_gridline_actions_without_kwargs(self, qapp):
        """If the new callbacks are not passed, no gridline actions appear."""
        from firepro3d.entity_context_menu import build_entity_context_menu
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000), label="1")
        menu = build_entity_context_menu([gl], gl)
        labels = [a.text() for a in menu.actions()]
        assert not any("Array Gridlines" in l for l in labels)
        assert not any("Offset Gridline" in l for l in labels)

    def test_no_gridline_actions_for_non_gridline_target(self, qapp):
        """Callbacks given but target is not a GridlineItem: actions absent."""
        from firepro3d.entity_context_menu import build_entity_context_menu
        menu = build_entity_context_menu(
            [], None,
            on_array_gridline=lambda: None,
            on_offset_gridline=lambda: None,
        )
        labels = [a.text() for a in menu.actions()]
        assert not any("Array Gridlines" in l for l in labels)
        assert not any("Offset Gridline" in l for l in labels)


class TestArrayCommit:
    """_commit_gridline_replicate in array mode creates copies, single undo."""

    def test_array_commit_creates_copies(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "array")
        ms._replicate_spacing = 1000.0
        ms._replicate_count = 3
        before = len(ms._gridlines)
        ms._commit_gridline_replicate()
        assert len(ms._gridlines) == before + 3

    def test_array_commit_single_undo(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms.push_undo_state()      # establish "before" checkpoint
        ms._start_gridline_replicate(src, "array")
        ms._replicate_spacing = 1000.0
        ms._replicate_count = 3
        before = len(ms._gridlines)
        ms._commit_gridline_replicate()
        assert len(ms._gridlines) == before + 3
        ms.undo()
        assert len(ms._gridlines) == before

    def test_array_labels_fresh_sequential_no_dupes(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "array")
        ms._replicate_spacing = 1000.0
        ms._replicate_count = 3
        ms._commit_gridline_replicate()
        labels = [g.grid_label for g in ms._gridlines]
        assert len(set(labels)) == len(labels)  # no duplicates


class TestOffsetCommit:
    """_commit_gridline_replicate in offset mode creates exactly one copy."""

    def test_offset_commit_creates_one_copy(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "offset")
        ms._replicate_spacing = 800.0
        ms._commit_gridline_replicate()
        assert len(ms._gridlines) == 2

    def test_offset_commit_too_close_cancels(self, qapp, make_model_space):
        """Spacing below 0.5 mm threshold → no copy placed."""
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "offset")
        ms._replicate_spacing = 0.1
        ms._commit_gridline_replicate()
        assert len(ms._gridlines) == 1  # nothing added


class TestReplicateRoundtrip:
    """Copies serialize through to_dict/from_dict without schema change."""

    def test_replicate_roundtrip_parametric(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "array")
        ms._replicate_spacing = 1000.0
        ms._replicate_count = 2
        ms._commit_gridline_replicate()
        dicts = [g.to_dict() for g in ms._gridlines]
        assert all("origin" in d for d in dicts)  # parametric, no schema change
        restored = [GridlineItem.from_dict(d) for d in dicts]
        assert len(restored) == 3


class TestModeState:
    """_start_gridline_replicate enters correct mode; cancel clears state."""

    def test_start_array_enters_mode(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "array")
        assert ms.mode == "gridline_array"
        assert ms._replicate_source is src

    def test_start_offset_enters_mode(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "offset")
        assert ms.mode == "gridline_offset"
        assert ms._replicate_source is src

    def test_end_replicate_clears_source(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "offset")
        ms._end_gridline_replicate()
        assert ms._replicate_source is None
        assert ms._replicate_ghost == []
        assert ms.mode == "select"

    def test_set_mode_select_clears_replicate_state(self, qapp, make_model_space):
        """set_mode() when leaving replicate modes clears state."""
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "array")
        ms.set_mode("select")
        assert ms._replicate_source is None
        assert ms._replicate_ghost == []


class TestGhostMath:
    """_build_replicate_ghost produces correct preview lines."""

    def test_ghost_offset_single_line(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "offset")
        ms._replicate_spacing = 1000.0
        ghost = ms._build_replicate_ghost(1000.0)
        assert len(ghost) == 1
        o, f = ghost[0]
        # vertical src: perp vector = (-1, 0); offset should shift x by -1000
        assert round(o.x(), 1) == -1000.0
        assert round(o.y(), 1) == 0.0

    def test_ghost_array_three_lines(self, qapp, make_model_space):
        ms = make_model_space()
        src = GridlineItem(QPointF(0.0, 0.0), QPointF(0.0, 5000.0), label="1")
        ms.addItem(src)
        ms._gridlines.append(src)
        ms._start_gridline_replicate(src, "array")
        ms._replicate_count = 3
        ghost = ms._build_replicate_ghost(1000.0)
        assert len(ghost) == 3
        xs = [round(o.x(), 1) for o, f in ghost]
        assert xs == [-1000.0, -2000.0, -3000.0]
