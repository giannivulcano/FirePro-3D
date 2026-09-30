"""View3D lifecycle guards on a REAL Model_Space (view-3d.md §10).

Unlike tests/test_view_3d.py (fake scene), these drive the real scene so the
scene-side effects (lists, undo stack, signals) are ground truth.
"""
from __future__ import annotations

import sys

import pytest

pv = pytest.importorskip("pyvista")
pv.OFF_SCREEN = True
pytest.importorskip("pyvistaqt")

from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest


@pytest.fixture()
def real3d(qapp):
    """(Model_Space, View3D) with a real LevelManager; the view is never shown."""
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.view_3d import View3D
    ms = Model_Space()
    lm = LevelManager()
    ms._level_manager = lm
    v = View3D(ms, lm, ms.scale_manager)
    yield ms, v
    v.cleanup()
    v.deleteLater()


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
        applied = _Counter()
        v._show_heatmap_now = applied.wrap(v._show_heatmap_now)
        from types import SimpleNamespace
        result = SimpleNamespace(threshold=1.0, per_receiver_flux={},
                                 per_receiver_mesh={})
        v.show_radiation_heatmap(result)
        assert applied.n == 0
        assert v._pending_heatmap is result


class TestResetEscapeCleanup:

    def test_reset_for_project_takes_live_scale_manager_and_refits(self, real3d):
        from firepro3d.scale_manager import ScaleManager
        ms, v = real3d
        v._first_build = False
        v._3d_selected = [_wall(ms, 0, 0, 1000, 0)]
        fresh = ScaleManager()
        v.reset_for_project(fresh)
        assert v._sm is fresh
        assert v._first_build is True
        assert v.get_3d_selected() == []
        assert v._dirty is True

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
        v.cleanup()
        ms.selectionChanged.emit()
        ms.sceneModified.emit()
        QTest.qWait(150)
        assert errors == []
        assert rebuilds.n == 0, "a scene signal reached the closed view"
        assert not v._rebuild_timer.isActive()
