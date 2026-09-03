"""Characterization safety-net for the pipe/node decomposition slice (C0).

LOCKS the CURRENT behavior of the pipe/node concern in
``firepro3d.model_space.Model_Space`` BEFORE it is relocated to
``firepro3d.pipe_network_controller``. Must pass on the CURRENT code.

CHARACTERIZATION testing: assertions encode observed behavior, not a desired
spec. If a relocation slice changes behavior these go red and flag the drift.
When a test itself encodes a wrong assumption, fix the TEST, never edit
production code from here.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.pipe import Pipe
from firepro3d.constants import DEFAULT_LEVEL, DEFAULT_CEILING_OFFSET_MM


def _make_scene(qapp) -> Model_Space:
    s = Model_Space()
    s._level_manager = LevelManager()
    s.scale_manager = ScaleManager()
    return s


def _pipe_template() -> Pipe:
    # A bare ``Pipe(None, None)`` leaves the per-node ceiling offsets as ``None``.
    # The live pipe workflow never uses such a template directly: ``set_mode
    # ("pipe", template)`` normalizes those Nones to ``DEFAULT_*`` before the
    # template ever reaches ``add_pipe`` (model_space.py set_mode, ~L1130).
    # Feeding a raw Pipe(None,None) into ``add_pipe`` crashes on current code
    # (get_properties -> _fmt(None) TypeError), so the realistic template — the
    # one whose behavior we are locking — carries the normalized defaults.
    t = Pipe(None, None)
    t.node1_ceiling_level = DEFAULT_LEVEL
    t.node1_ceiling_offset = DEFAULT_CEILING_OFFSET_MM
    t.node2_ceiling_level = DEFAULT_LEVEL
    t.node2_ceiling_offset = DEFAULT_CEILING_OFFSET_MM
    return t


def _post_mouse(view, etype, scene_pt, button=Qt.MouseButton.NoButton):
    vp_pos = QPointF(view.mapFromScene(QPointF(scene_pt)))
    ev = QMouseEvent(etype, vp_pos, button, button,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view.viewport(), ev)


class TestBackCompat:
    PUBLIC_METHODS = (
        "add_pipe", "delete_pipe", "split_pipe", "find_nearby_node",
        "find_or_create_node", "add_node", "remove_node",
        "find_nearby_candidates", "_apply_fitting_dm_colors",
    )

    def test_public_methods_present_and_callable(self, qapp):
        scene = _make_scene(qapp)
        for name in self.PUBLIC_METHODS:
            assert hasattr(scene, name), f"missing {name}"
            assert callable(getattr(scene, name)), f"{name} not callable"

    def test_add_pipe_registers_in_system(self, qapp):
        scene = _make_scene(qapp)
        n1 = scene.add_node(0.0, 0.0)
        n2 = scene.add_node(1000.0, 0.0)
        p = scene.add_pipe(n1, n2, _pipe_template())
        assert p in scene.sprinkler_system.pipes
        assert n1 in scene.sprinkler_system.nodes
        assert n2 in scene.sprinkler_system.nodes

    def test_delete_pipe_orphans_bare_nodes(self, qapp):
        scene = _make_scene(qapp)
        n1 = scene.add_node(0.0, 0.0)
        n2 = scene.add_node(1000.0, 0.0)
        p = scene.add_pipe(n1, n2, _pipe_template())
        scene.delete_pipe(p)
        assert p not in scene.sprinkler_system.pipes
        assert n1 not in scene.sprinkler_system.nodes
        assert n2 not in scene.sprinkler_system.nodes


class TestFileByteParity:
    def test_pipe_network_byte_parity(self, qapp, tmp_path):
        scene1 = _make_scene(qapp)
        n1 = scene1.add_node(0.0, 0.0)
        n2 = scene1.add_node(1000.0, 0.0)
        n3 = scene1.add_node(1000.0, 1000.0)
        scene1.add_pipe(n1, n2, _pipe_template())
        scene1.add_pipe(n2, n3, _pipe_template())

        proj1 = tmp_path / "proj.fpd"
        scene1.save_to_file(str(proj1))

        scene2 = _make_scene(qapp)
        scene2.load_from_file(str(proj1))
        proj2 = tmp_path / "proj2.fpd"
        scene2.save_to_file(str(proj2))

        assert proj1.read_bytes() == proj2.read_bytes(), \
            "pipe network save->load->save not byte-stable"


class TestUndoRedoParity:
    def test_network_identical_after_undo_redo(self, qapp):
        scene = _make_scene(qapp)
        n1 = scene.add_node(0.0, 0.0)
        n2 = scene.add_node(1000.0, 0.0)
        scene.add_pipe(n1, n2, _pipe_template())
        scene.push_undo_state()
        n3 = scene.add_node(1000.0, 1000.0)
        scene.add_pipe(n2, n3, _pipe_template())
        scene.push_undo_state()

        def snap():
            return (
                sorted((round(nd.x_pos, 3), round(nd.y_pos, 3),
                        round(nd.z_pos, 3)) for nd in scene.sprinkler_system.nodes),
                len(scene.sprinkler_system.pipes),
            )

        before = snap()
        scene.undo()
        scene.redo()
        assert snap() == before, "undo/redo changed the pipe network"


class TestPipePlacementLive:
    def test_two_click_creates_pipe(self, shown_model_view):
        view, scene = shown_model_view
        scene.set_mode("pipe", _pipe_template())
        n_pipes_0 = len(scene.sprinkler_system.pipes)

        _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(0, 0),
                    button=Qt.MouseButton.LeftButton)
        _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(0, 0),
                    button=Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert scene.node_start_pos is not None, "start node not set after click 1"

        _post_mouse(view, QEvent.Type.MouseMove, QPointF(1000, 0))
        QApplication.processEvents()

        _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(1000, 0),
                    button=Qt.MouseButton.LeftButton)
        _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(1000, 0),
                    button=Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        assert len(scene.sprinkler_system.pipes) == n_pipes_0 + 1, \
            "second click did not create a pipe"


class TestPipeCancel:
    def test_escape_removes_new_orphan_start_node(self, shown_model_view):
        view, scene = shown_model_view
        scene.set_mode("pipe", _pipe_template())
        _post_mouse(view, QEvent.Type.MouseButtonPress, QPointF(0, 0),
                    button=Qt.MouseButton.LeftButton)
        _post_mouse(view, QEvent.Type.MouseButtonRelease, QPointF(0, 0),
                    button=Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        start = scene.node_start_pos
        assert start is not None
        n_nodes = len(scene.sprinkler_system.nodes)

        scene.set_mode("select")
        assert scene.node_start_pos is None
        assert len(scene.sprinkler_system.nodes) == n_nodes - 1, \
            "orphan start node not cleaned on mode change"


class TestGeometryCorrections:
    def test_split_pipe_creates_junction(self, qapp):
        scene = _make_scene(qapp)
        n1 = scene.add_node(0.0, 0.0)
        n2 = scene.add_node(2000.0, 0.0)
        p = scene.add_pipe(n1, n2, _pipe_template())
        n_pipes = len(scene.sprinkler_system.pipes)
        mid = scene.split_pipe(p, QPointF(1000.0, 0.0))
        assert mid in scene.sprinkler_system.nodes
        assert len(scene.sprinkler_system.pipes) == n_pipes + 1

    def test_backtrack_blocks_duplicate(self, qapp):
        scene = _make_scene(qapp)
        n1 = scene.add_node(0.0, 0.0)
        n2 = scene.add_node(1000.0, 0.0)
        scene.add_pipe(n1, n2, _pipe_template())
        assert scene._would_backtrack_at(n1, QPointF(500.0, 0.0)) is True
