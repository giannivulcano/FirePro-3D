"""View3D lifecycle guards on a REAL Model_Space (view-3d.md §10).

Unlike tests/test_view_3d.py (fake scene), these drive the real scene so the
scene-side effects (lists, undo stack, signals) are ground truth.
"""
from __future__ import annotations

import sys

import numpy as np
import pytest

pv = pytest.importorskip("pyvista")
pv.OFF_SCREEN = True
pytest.importorskip("pyvistaqt")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest


@pytest.fixture()
def real3d(qapp):
    """(Model_Space, View3D) with a real LevelManager; hidden unless _show()n."""
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.view_3d import View3D
    ms = Model_Space()
    lm = LevelManager()
    ms._level_manager = lm
    v = View3D(ms, lm, ms.scale_manager)
    yield ms, v
    v.hide()
    v.cleanup()
    v.deleteLater()
    ms.deleteLater()          # release the scene too (never scene.clear())
    QTest.qWait(0)


_SETTLE_MS = 300              # > the 100 ms rebuild timer + the 0 ms show flush


def _show(v):
    """Show *v* through the real showEvent path without an on-screen window."""
    v.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    v.show()
    QTest.qWait(_SETTLE_MS)
    assert v.isVisible(), "precondition: WA_DontShowOnScreen view reports visible"


def _heatmap_for(ms, wall):
    """A real RadiationResult carrying *wall*'s own 3D mesh as one receiver."""
    from firepro3d.thermal_radiation_solver import RadiationResult
    md = wall.get_3d_mesh(level_manager=ms._level_manager)
    faces = np.asarray(md["faces"])
    return RadiationResult(
        per_receiver_mesh={wall: {"vertices": np.asarray(md["vertices"]),
                                  "faces": faces}},
        per_receiver_flux={wall: np.full(len(faces), 5.0)},
    )


def _wall(ms, x1, y1, x2, y2):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(x1, y1), QPointF(x2, y2))
    ms.addItem(w)
    ms._walls.append(w)
    return w


def _slab(ms):
    from firepro3d.floor_slab import FloorSlab
    s = FloorSlab(points=[QPointF(0, 0), QPointF(2000, 0),
                          QPointF(2000, 2000), QPointF(0, 2000)])
    ms.addItem(s)
    ms._floor_slabs.append(s)
    return s


def _roof(ms):
    from firepro3d.roof import RoofItem
    r = RoofItem(points=[QPointF(0, 0), QPointF(2000, 0), QPointF(2000, 2000)])
    ms.addItem(r)
    ms._roofs.append(r)
    return r


def _pipe(ms, x1=0, y1=0, x2=1000, y2=0):
    n1 = ms.add_node(x1, y1)
    n2 = ms.add_node(x2, y2)
    return ms.add_pipe(n1, n2)


class TestOneDeletePath:
    """I8 / D13: delete from 3D = the scene's delete path, ONE undo step."""

    def test_3d_delete_of_mixed_items_is_one_undo_step(self, real3d):
        ms, v = real3d
        wall, slab, roof, pipe = _wall(ms, 0, 0, 3000, 0), _slab(ms), _roof(ms), _pipe(ms)
        ms.push_undo_state()
        before = len(ms._undo_stack)
        v._3d_selected = [wall, slab, roof, pipe]
        v.delete_selected()
        assert wall not in ms._walls
        assert slab not in ms._floor_slabs
        assert roof not in ms._roofs
        assert pipe not in ms.sprinkler_system.pipes
        assert len(ms._undo_stack) == before + 1, "3D delete must push exactly one undo state"
        assert v.get_3d_selected() == []


class _Counter:
    def __init__(self):
        self.n = 0

    def wrap(self, fn):
        def _w(*a, **k):
            self.n += 1
            return fn(*a, **k)
        return _w


class TestIdleWhileHidden:
    """I6: nothing reaches VTK while the view is not visible."""

    def test_hidden_view_never_rebuilds_or_renders(self, real3d):
        ms, v = real3d
        _wall(ms, 0, 0, 3000, 0)
        rebuilds, renders = _Counter(), _Counter()
        v.rebuild = rebuilds.wrap(v.rebuild)
        v._plotter.render = renders.wrap(v._plotter.render)
        v.request_rebuild()
        ms.sceneModified.emit()
        ms.selectionChanged.emit()
        v.cancel_interaction()
        QTest.qWait(250)
        assert rebuilds.n == 0 and renders.n == 0
        assert v._dirty is True

    def test_hidden_heatmap_is_deferred_until_shown(self, real3d):
        ms, v = real3d
        w = _wall(ms, 0, 0, 3000, 0)
        v.show_radiation_heatmap(_heatmap_for(ms, w))
        assert v._radiation_meshes == [], "hidden: nothing reaches VTK yet"
        _show(v)
        assert len(v._radiation_meshes) == 1, "the heatmap appears on show (I10)"


class TestShowFlush:
    """I6 second half: work deferred while hidden is applied on show."""

    def test_hidden_edits_rebuild_once_on_show(self, real3d):
        ms, v = real3d
        rebuilds = _Counter()
        v.rebuild = rebuilds.wrap(v.rebuild)
        _wall(ms, 0, 0, 3000, 0)
        _wall(ms, 0, 0, 0, 3000)
        for _ in range(3):
            ms.sceneModified.emit()
        QTest.qWait(150)
        assert rebuilds.n == 0
        _show(v)
        assert rebuilds.n == 1, "hidden edits coalesce into one rebuild on show"
        walls = [a for a in v._actors.get("walls", []) if a is not None]
        assert len(walls) == 2

    def test_selection_made_while_hidden_highlights_on_show(self, real3d):
        ms, v = real3d
        w = _wall(ms, 0, 0, 3000, 0)
        _show(v)                                  # built, clean
        v.hide()
        w.setSelected(True)
        assert w in ms.selectedItems(), "precondition: the wall is 2D-selected"
        assert not v._actors.get("sel_overlay"), "hidden: no overlay built yet"
        _show(v)
        assert v._actors.get("sel_overlay"), "the hidden selection highlights on show"

    def test_reset_for_project_refits_camera_on_show(self, real3d):
        from firepro3d.scale_manager import ScaleManager
        ms, v = real3d
        _wall(ms, 0, 0, 3000, 0)
        _show(v)
        far = (90000.0, 90000.0, 90000.0)
        v._plotter.camera.focal_point = far
        v._plotter.camera.position = (99000.0, 99000.0, 99000.0)
        v.hide()
        v.reset_for_project(ScaleManager())
        _show(v)
        centre = v._compute_scene_bounds()[0]
        fp = np.array(v._plotter.camera.focal_point)
        assert np.linalg.norm(fp - np.array(far)) > 1000.0, "camera re-fit on show"
        assert np.linalg.norm(fp - centre) < 1.0, "focal point sits on the model centre"

    def test_reset_for_project_drops_old_heatmap(self, real3d):    # M-2
        from firepro3d.scale_manager import ScaleManager
        ms, v = real3d
        w = _wall(ms, 0, 0, 3000, 0)
        _show(v)
        v.show_radiation_heatmap(_heatmap_for(ms, w))
        assert len(v._radiation_meshes) == 1, "precondition: heatmap displayed"
        v.hide()
        v.reset_for_project(ScaleManager())
        _show(v)
        assert v._radiation_meshes == [], "the previous project's heatmap is gone"


class TestResetEscapeCleanup:

    def test_reset_for_project_takes_live_scale_manager(self, real3d):
        from firepro3d.scale_manager import ScaleManager
        ms, v = real3d
        v._first_build = False
        v._3d_selected = [_wall(ms, 0, 0, 1000, 0)]
        fresh = ScaleManager()
        v.reset_for_project(fresh)
        assert v._sm is fresh
        assert v.get_3d_selected() == []

    def test_cancel_interaction_clears_pick_and_scene_selection(self, real3d):
        ms, v = real3d
        w = _wall(ms, 0, 0, 1000, 0)
        v._3d_selected = [w]
        w.setSelected(True)
        v.cancel_interaction()
        assert v.get_3d_selected() == []
        assert ms.selectedItems() == []

    def test_no_slot_runs_after_cleanup(self, real3d, monkeypatch):
        ms, v = real3d
        errors = []
        monkeypatch.setattr(sys, "excepthook", lambda *a: errors.append(a))
        # Treat the view as on-screen so a still-connected request_rebuild
        # would arm the rebuild timer (a hidden view idles by design, I6).
        monkeypatch.setattr(v, "isVisible", lambda: True)
        rebuilds = _Counter()
        v.rebuild = rebuilds.wrap(v.rebuild)
        v.request_rebuild()                       # arms the 100 ms timer
        assert v._rebuild_timer.isActive(), "precondition: timer armed"
        v.cleanup()
        ms.selectionChanged.emit()
        ms.sceneModified.emit()
        QTest.qWait(250)
        assert errors == []
        assert rebuilds.n == 0, "a scene signal reached the closed view"
        assert not v._rebuild_timer.isActive()


class TestRebuildFixes:

    def test_rebuild_keeps_the_users_camera(self, real3d):          # I13 / D7
        ms, v = real3d
        _wall(ms, 0, 0, 3000, 0)
        v.rebuild()                               # first build fits
        cam = v._plotter.camera
        cam.focal_point = (12345.0, -678.0, 90.0)
        cam.position = (22345.0, -678.0, 90.0)
        _wall(ms, 5000, 5000, 9000, 5000)          # geometry centroid moves
        v.rebuild()
        assert tuple(round(c, 3) for c in v._plotter.camera.focal_point) == (12345.0, -678.0, 90.0)

    def test_h_cut_survives_rebuild(self, real3d):                  # I15 / D10
        ms, v = real3d
        _wall(ms, 0, 0, 3000, 0)
        v.rebuild()
        v._section_h_btn.setChecked(True)
        v._toggle_horizontal_cut()                # enabling seeds the height from Level 2
        v._h_cut_height_mm = -100.0              # below everything → all cut away
        v.rebuild()
        walls = [a for a in v._actors.get("walls", []) if a is not None]
        assert walls and all(not a.GetVisibility() for a in walls)

    def test_hidden_wall_hides_its_openings(self, real3d):          # I14 / D9
        from firepro3d.wall_opening import DoorOpening
        ms, v = real3d
        w = _wall(ms, 0, 0, 3000, 0)
        door = DoorOpening(w, offset_along=500.0, width_mm=900.0)
        w.openings.append(door)
        v._extract_openings()
        assert v._actors.get("openings"), "precondition: a visible wall's door renders"
        ms._hide_items([w])                       # the 3D context menu's hide path
        v._extract_openings()
        assert not v._actors.get("openings")

    def test_pipe_pick_refs_align_with_midpoints(self, real3d):     # I16 / D11
        ms, v = real3d
        broken = _pipe(ms, 0, 0, 1000, 0)
        good = _pipe(ms, 0, 3000, 1000, 3000)
        broken.node1 = None                       # skipped by extraction
        v._extract_pipes()
        assert len(v._pipe_refs) == len(v._pipe_midpoints_3d)
        i = v._pipe_refs.index(good)
        expect = (v._node_to_3d(good.node1) + v._node_to_3d(good.node2)) / 2.0
        assert v._pipe_midpoints_3d[i] == pytest.approx(expect)
