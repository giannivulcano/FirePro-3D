"""
test_gridline_placement_template.py
=====================================
TDD tests for the gridline placement template in the properties panel.

When the user enters ``draw_gridline`` mode the right-side properties dock
should populate with a *template* GridlineItem so they can preset non-geometric
properties (Bubble Offsets, visibility, Locked) before placing.  Each placed
gridline adopts the template's values.

Scope
-----
- Entering ``draw_gridline`` mode emits ``requestPropertyUpdate`` with the template.
- Template ``get_properties()`` exposes only non-geometric rows.
- Placed gridline inherits template bubble-offsets, locked, bubble visibility.
- Editing the template does NOT push an undo state.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsView, QApplication

from firepro3d.gridline import GridlineItem
from firepro3d.model_space import Model_Space


# ---------------------------------------------------------------------------
# make_model_space fixture (local copy mirrors other gridline test modules)
# ---------------------------------------------------------------------------

@pytest.fixture
def make_model_space(qapp):
    """Factory: Model_Space with an attached 800×800 QGraphicsView."""
    created: list[tuple[Model_Space, QGraphicsView]] = []

    def _factory() -> Model_Space:
        ms = Model_Space()
        view = QGraphicsView(ms)
        view.resize(800, 800)
        view.resetTransform()
        view.centerOn(0.0, 0.0)
        QApplication.processEvents()
        created.append((ms, view))
        return ms

    yield _factory

    for ms, view in created:
        view.hide()


# ---------------------------------------------------------------------------
# Helper: place a gridline by driving _press_draw_line directly
# ---------------------------------------------------------------------------

def _place_gridline(ms: Model_Space, p1: QPointF, p2: QPointF) -> GridlineItem:
    """Drive the two-click placement flow for draw_gridline mode."""
    from types import SimpleNamespace
    from PyQt6.QtCore import Qt
    mods = Qt.KeyboardModifier.NoModifier
    ev = SimpleNamespace(modifiers=lambda: mods)
    ms.set_mode("draw_gridline")
    ms._press_draw_line(ev, p1, p1, None, None, None)  # first click: anchor
    ms._press_draw_line(ev, p2, p2, None, None, None)  # second click: commit
    return ms._gridlines[-1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEnteringPlacementModeEmitsTemplate:
    def test_entering_gridline_mode_emits_template(self, qapp, make_model_space):
        ms = make_model_space()
        captured = []
        ms.requestPropertyUpdate.connect(lambda obj: captured.append(obj))

        ms.set_mode("draw_gridline")

        assert captured, (
            "entering draw_gridline should populate the properties panel with a template"
        )
        tmpl = captured[-1]
        assert isinstance(tmpl, GridlineItem), (
            "emitted object should be a GridlineItem (the template)"
        )
        assert getattr(tmpl, "_is_template", False) is True, (
            "template should have _is_template == True"
        )

    def test_template_is_not_in_scene(self, qapp, make_model_space):
        ms = make_model_space()
        ms.set_mode("draw_gridline")
        tmpl = ms._get_gridline_template()
        assert tmpl.scene() is None, "template must NOT be added to the scene"
        assert tmpl not in ms._gridlines, "template must NOT be in _gridlines"


class TestTemplateGetProperties:
    def test_hides_geometric_rows(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        props = tmpl.get_properties()  # returns a dict keyed by name
        geometric = {"Origin X", "Origin Y", "Length", "Angle", "End X", "End Y", "Label"}
        overlap = geometric & set(props.keys())
        assert not overlap, (
            f"Template get_properties() should omit geometric rows; found: {overlap}"
        )

    def test_exposes_bubble_1_offset(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        props = tmpl.get_properties()
        assert "Bubble 1 Offset" in props, "Template should expose Bubble 1 Offset"

    def test_exposes_bubble_2_offset(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        props = tmpl.get_properties()
        assert "Bubble 2 Offset" in props, "Template should expose Bubble 2 Offset"

    def test_exposes_bubble_visibility_rows(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        props = tmpl.get_properties()
        assert "Bubble 1" in props, "Template should expose Bubble 1 (visibility)"
        assert "Bubble 2" in props, "Template should expose Bubble 2 (visibility)"

    def test_exposes_locked_row(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        props = tmpl.get_properties()
        assert "Locked" in props, "Template should expose Locked"

    def test_normal_gridline_get_properties_unchanged(self, qapp):
        """Non-template gridlines must still return the full property set."""
        gl = GridlineItem(QPointF(0, 0), QPointF(0, 1000))
        props = gl.get_properties()
        expected = {"Label", "Origin X", "Origin Y", "Length", "Angle",
                    "End X", "End Y",
                    "Bubble 1", "Bubble 1 Offset", "Bubble 2", "Bubble 2 Offset",
                    "Locked"}
        assert expected == set(props.keys()), (
            "Non-template get_properties() should be unchanged"
        )


class TestPlacedGridlineAdoptsTemplate:
    def test_placed_gridline_adopts_bubble1_offset(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        tmpl.set_bubble_offset(1, 1750.0)

        gl = _place_gridline(ms, QPointF(0, 0), QPointF(0, 4000))

        assert round(gl._bubble1_offset, 1) == 1750.0, (
            "Placed gridline should inherit bubble 1 offset from template"
        )

    def test_placed_gridline_adopts_bubble2_offset(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        tmpl.set_bubble_offset(2, 900.0)

        gl = _place_gridline(ms, QPointF(0, 0), QPointF(0, 4000))

        assert round(gl._bubble2_offset, 1) == 900.0, (
            "Placed gridline should inherit bubble 2 offset from template"
        )

    def test_placed_gridline_adopts_locked(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        tmpl._locked = True

        gl = _place_gridline(ms, QPointF(0, 0), QPointF(0, 4000))

        assert gl._locked is True, (
            "Placed gridline should inherit Locked state from template"
        )

    def test_placed_gridline_adopts_bubble1_visibility(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        tmpl.bubble1.setVisible(False)  # hide bubble 1

        gl = _place_gridline(ms, QPointF(0, 0), QPointF(0, 4000))

        assert not gl.bubble1.isVisible(), (
            "Placed gridline should inherit bubble 1 visibility from template"
        )

    def test_placed_gridline_adopts_bubble2_visibility(self, qapp, make_model_space):
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        tmpl.bubble2.setVisible(False)  # hide bubble 2

        gl = _place_gridline(ms, QPointF(0, 0), QPointF(0, 4000))

        assert not gl.bubble2.isVisible(), (
            "Placed gridline should inherit bubble 2 visibility from template"
        )

    def test_template_values_not_shared_between_placements(self, qapp, make_model_space):
        """Placed gridlines must not share state with the template object."""
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        tmpl.set_bubble_offset(1, 500.0)

        gl1 = _place_gridline(ms, QPointF(0, 0), QPointF(0, 4000))
        # Mutate template after first placement
        tmpl.set_bubble_offset(1, 999.0)
        gl2 = _place_gridline(ms, QPointF(1000, 0), QPointF(1000, 4000))

        assert round(gl1._bubble1_offset, 1) == 500.0, "gl1 should not be affected by later template change"
        assert round(gl2._bubble1_offset, 1) == 999.0, "gl2 should adopt the new template value"


class TestEditingTemplateDoesNotPushUndo:
    def test_set_bubble_offset_does_not_grow_undo_stack(self, qapp, make_model_space):
        """set_bubble_offset on an off-scene template must not push undo.

        GridlineItem.set_property guards the push with:
            sc = self.scene()
            if sc is not None and hasattr(sc, "push_undo_state"):
                sc.push_undo_state()
        The template is never added to the scene, so self.scene() is None
        and the push is skipped.  We verify via the undo stack length.
        """
        ms = make_model_space()
        tmpl = ms._get_gridline_template()

        # Capture depth before
        depth_before = len(ms._undo_stack)

        # Simulate the panel path: set_property routes Bubble 1 Offset to
        # set_bubble_offset internally.
        tmpl.set_property("Bubble 1 Offset", 1200.0)
        tmpl.set_property("Bubble 2 Offset", 800.0)
        tmpl.set_property("Locked", "True")

        depth_after = len(ms._undo_stack)
        assert depth_after == depth_before, (
            f"Editing the template should not push undo; "
            f"stack grew from {depth_before} to {depth_after}"
        )

    def test_template_not_in_gridlines_list(self, qapp, make_model_space):
        """Guard invariant: template is never registered in _gridlines."""
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        assert tmpl not in ms._gridlines, "template must never appear in _gridlines"

    def test_template_scene_is_none(self, qapp, make_model_space):
        """The template must never be added to the scene."""
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        assert tmpl.scene() is None, "template.scene() must be None (never added to scene)"

    def test_placing_after_template_edit_pushes_undo_once(self, qapp, make_model_space):
        """Placing a gridline should push undo exactly once (from _press_draw_line),
        not from template edits."""
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        tmpl.set_property("Bubble 1 Offset", 300.0)  # template edit — no undo

        depth_before = len(ms._undo_stack)
        _place_gridline(ms, QPointF(0, 0), QPointF(0, 4000))
        depth_after = len(ms._undo_stack)

        assert depth_after == depth_before + 1, (
            "Placing a gridline should push exactly one undo state"
        )


class TestTemplatePersistsAcrossPlacements:
    def test_template_cached_across_calls(self, qapp, make_model_space):
        """_get_gridline_template() must return the same object each time."""
        ms = make_model_space()
        t1 = ms._get_gridline_template()
        t2 = ms._get_gridline_template()
        assert t1 is t2, "_get_gridline_template() should return the same cached instance"

    def test_template_presets_survive_multiple_placements(self, qapp, make_model_space):
        """The template retains its preset values after placements."""
        ms = make_model_space()
        tmpl = ms._get_gridline_template()
        tmpl.set_bubble_offset(1, 2000.0)

        _place_gridline(ms, QPointF(0, 0), QPointF(0, 4000))
        _place_gridline(ms, QPointF(1000, 0), QPointF(1000, 4000))

        assert round(tmpl._bubble1_offset, 1) == 2000.0, (
            "Template bubble 1 offset should be unchanged after placements"
        )
        # Both placed gridlines should have inherited 2000 mm
        for gl in ms._gridlines:
            assert round(gl._bubble1_offset, 1) == 2000.0
