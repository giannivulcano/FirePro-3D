"""Characterization safety-net for the sprinkler/design-area/hydraulic
decomposition slice (C0).

LOCKS the CURRENT behavior of concern #2 in
``firepro3d.model_space.Model_Space`` BEFORE it is relocated to
``firepro3d.sprinkler_workflow_controller``. Must pass on the CURRENT code.

CHARACTERIZATION testing: assertions encode observed behavior, not a desired
spec. If a relocation slice changes behavior these go red and flag the drift.
When a test itself encodes a wrong assumption, fix the TEST, never edit
production code from here.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.constants import DEFAULT_LEVEL


def _make_scene(qapp) -> Model_Space:
    s = Model_Space()
    s._level_manager = LevelManager()
    s.scale_manager = ScaleManager()
    return s


def _post_mouse(view, etype, scene_pt, button=Qt.MouseButton.NoButton,
                modifiers=Qt.KeyboardModifier.NoModifier):
    vp_pos = QPointF(view.mapFromScene(QPointF(scene_pt)))
    ev = QMouseEvent(etype, vp_pos, button, button, modifiers)
    QApplication.sendEvent(view.viewport(), ev)


def _add_sprinkler_at(scene, x, y, level=DEFAULT_LEVEL):
    """Create a bare node at (x,y) on *level* and attach a sprinkler; return it."""
    node = scene.add_node(x, y)
    node.level = level
    spr = scene.add_sprinkler(node)
    return spr


class TestBackCompat:
    PUBLIC_METHODS = (
        "add_sprinkler", "remove_sprinkler", "auto_populate_room",
        "run_hydraulics", "clear_hydraulics", "set_coverage_overlay",
    )

    def test_public_methods_present_and_callable(self, qapp):
        scene = _make_scene(qapp)
        for name in self.PUBLIC_METHODS:
            assert hasattr(scene, name), f"missing {name}"
            assert callable(getattr(scene, name)), f"{name} not callable"

    def test_design_area_sprinklers_property_present(self, qapp):
        scene = _make_scene(qapp)
        assert scene.design_area_sprinklers == []

    def test_add_sprinkler_registers(self, qapp):
        scene = _make_scene(qapp)
        spr = _add_sprinkler_at(scene, 0.0, 0.0)
        assert spr is not None
        assert spr in scene.sprinkler_system.sprinklers


class TestFileByteParity:
    def test_design_area_and_supply_byte_parity(self, qapp, tmp_path):
        scene1 = _make_scene(qapp)
        s1 = _add_sprinkler_at(scene1, 0.0, 0.0)
        s2 = _add_sprinkler_at(scene1, 1000.0, 0.0)
        da = scene1._ensure_editing_da()
        da.add_sprinkler(s1)
        da.add_sprinkler(s2)
        da.compute_area(scene1.scale_manager)

        proj1 = tmp_path / "proj.fpd"
        scene1.save_to_file(str(proj1))
        scene2 = _make_scene(qapp)
        scene2.load_from_file(str(proj1))
        proj2 = tmp_path / "proj2.fpd"
        scene2.save_to_file(str(proj2))

        assert proj1.read_bytes() == proj2.read_bytes(), \
            "design-area/supply save->load->save not byte-stable"


class TestUndoRedoParity:
    def test_design_area_membership_survives_undo_redo(self, qapp):
        scene = _make_scene(qapp)
        s1 = _add_sprinkler_at(scene, 0.0, 0.0)
        da = scene._ensure_editing_da()
        da.add_sprinkler(s1)
        scene.push_undo_state()
        s2 = _add_sprinkler_at(scene, 1000.0, 0.0)
        da.add_sprinkler(s2)
        scene.push_undo_state()

        def snap():
            return sorted(len(d.sprinklers) for d in scene.design_areas)

        before = snap()
        scene.undo()
        scene.redo()
        assert snap() == before, "undo/redo changed design-area membership"


class TestDesignAreaPickLive:
    def test_single_click_toggles_sprinkler_into_area(self, shown_model_view):
        view, scene = shown_model_view
        _add_sprinkler_at(scene, 0.0, 0.0)
        scene.set_mode("design_area")
        _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(0, 0),
                    button=Qt.MouseButton.LeftButton)
        _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(0, 0),
                    button=Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert scene.active_design_area is not None
        assert len(scene.active_design_area.sprinklers) == 1


class TestWaterSupplyLive:
    def test_click_node_places_supply(self, shown_model_view):
        view, scene = shown_model_view
        spr = _add_sprinkler_at(scene, 0.0, 0.0)
        node = spr.node
        scene.set_mode("water_supply")
        _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(0, 0),
                    button=Qt.MouseButton.LeftButton)
        _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(0, 0),
                    button=Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert scene.water_supply_node is not None
        assert scene.sprinkler_system.supply_node is scene.water_supply_node


class TestCoverageOverlay:
    def test_toggle_sets_class_flag(self, qapp):
        from firepro3d.node import Node
        scene = _make_scene(qapp)
        scene.set_coverage_overlay(True)
        assert Node._coverage_visible is True
        scene.set_coverage_overlay(False)
        assert Node._coverage_visible is False


class TestClearHookIsReal:
    def test_leaving_design_area_mode_tears_down_transient(self, shown_model_view):
        view, scene = shown_model_view
        _add_sprinkler_at(scene, 0.0, 0.0)
        _add_sprinkler_at(scene, 1000.0, 0.0)
        scene.set_mode("design_area")
        # Begin a Shift+rect selection (first corner) — leaves a live rect item
        _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(-200, -200),
                    button=Qt.MouseButton.LeftButton,
                    modifiers=Qt.KeyboardModifier.ShiftModifier)
        _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(-200, -200),
                    button=Qt.MouseButton.LeftButton,
                    modifiers=Qt.KeyboardModifier.ShiftModifier)
        QApplication.processEvents()
        assert scene._spr_ctl._design_area_rect_item is not None, \
            "precondition: an in-progress rubber-band rect should exist"
        scene.set_mode(None)
        assert scene._spr_ctl._design_area_rect_item is None, \
            "clear() did not remove the in-progress rect on mode change"
        assert scene._spr_ctl._da_editing is None
