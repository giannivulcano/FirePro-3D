"""Manipulator translate adapters for the design-area badge and the model
annotations (NoteAnnotation, DimensionAnnotation), plus the drawForeground
selection-boundary de-duplication seam.

Governing spec: docs/specs/selection-manipulator.md.  These items are
translate-ONLY under the manipulator in v1 (no scale/rotate handles): a badge
carries a fixed table layout, annotations are parametric.  The manipulator
frame becomes the sole selection boundary — the view's
``_should_draw_selection_boundary`` predicate skips items the manipulator wraps
while grip squares keep rendering.
"""
import json

import pytest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.model_view import Model_View
from firepro3d.selection_manipulator import SelectionManipulator
from firepro3d.manip_math import HandleRole


@pytest.fixture
def scene_and_view(qapp):
    """A shown Model_View over a Model_Space, pinned to identity zoom
    (mirrors tests/test_selection_manipulator.py::scene_and_view)."""
    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    view = Model_View(scene)
    view.resize(800, 600)
    view.show()
    QTest.qWaitForWindowExposed(view)
    view.resetTransform()
    view.centerOn(150, 50)
    view.setFocus()
    qapp.processEvents()
    yield scene, view
    view.close()


def _post_mouse(view, etype, scene_pos, button=Qt.MouseButton.LeftButton,
                buttons=None, modifiers=Qt.KeyboardModifier.NoModifier):
    app = QApplication.instance()
    vp = view.viewport()
    p = view.mapFromScene(scene_pos)
    if buttons is None:
        buttons = (Qt.MouseButton.NoButton
                   if etype == QEvent.Type.MouseButtonRelease
                   else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(etype, p.toPointF(), vp.mapToGlobal(p).toPointF(),
                     button, buttons, modifiers)
    app.sendEvent(vp, ev)
    app.processEvents()


def _manip(scene) -> SelectionManipulator:
    return next(i for i in scene.items()
                if isinstance(i, SelectionManipulator))


def _visible_handles(manip):
    return [h for h in manip.childItems() if h.isVisible()]


# ── DesignArea badge ────────────────────────────────────────────────────────

def _confirmed_design_area(scene):
    """Build a confirmed DesignArea (with a visible badge) on a two-sprinkler
    branch, registered on the scene, in select mode so the badge shows."""
    n1 = scene.add_node(0.0, 0.0)
    n2 = scene.add_node(3000.0, 0.0)
    scene.add_pipe(n1, n2)
    s1 = scene.add_sprinkler(n1)
    s2 = scene.add_sprinkler(n2)
    from firepro3d.design_area import DesignArea
    da = DesignArea([s1, s2])
    scene.addItem(da)
    scene.design_areas.append(da)
    da.compute_area(scene.scale_manager)
    da.sync_z_for_mode(editing=False)   # confirmed → badge visible
    return da


def test_badge_moves_via_manipulator_one_undo(qapp, scene_and_view):
    scene, view = scene_and_view
    da = _confirmed_design_area(scene)
    assert da.badge.isVisible()
    da.setSelected(True)
    qapp.processEvents()

    manip = _manip(scene)
    assert manip.isVisible()
    assert da in manip.selection_items()          # wrapped (not excluded)
    # translate-only: no resize handles, no rotate knob
    assert _visible_handles(manip) == []

    scene.push_undo_state()                        # baseline
    depth0 = len(scene._undo_stack)
    x0, y0 = da.badge_offset()

    # Drive a manipulator move gesture (grip sits at the badge centre, so
    # exercise the manipulator API directly like the resize/rotate tests).
    manip._begin("move", QPointF(0, 0), QPointF(0, 0))
    manip._update(QPointF(120, 90), Qt.KeyboardModifier.NoModifier,
                  QPointF(120, 90))
    manip._finish(QPointF(120, 90), Qt.KeyboardModifier.NoModifier)
    qapp.processEvents()

    x1, y1 = da.badge_offset()
    assert abs((x1 - x0) - 120.0) < 2.0            # baked move applied
    assert abs((y1 - y0) - 90.0) < 2.0
    assert da.badge.transform().isIdentity()       # no held Qt transform
    assert len(scene._undo_stack) == depth0 + 1    # exactly one undo entry

    scene.undo()
    qapp.processEvents()
    da2 = scene.design_areas[0]
    xu, yu = da2.badge_offset()
    assert abs(xu - x0) < 1e-6 and abs(yu - y0) < 1e-6


def test_badge_manip_capabilities_translate_only(qapp, scene_and_view):
    scene, view = scene_and_view
    da = _confirmed_design_area(scene)
    from firepro3d.selection_manipulator import item_capabilities
    caps = item_capabilities(da)
    assert caps == {"translate"}                   # no scale/rotate phantom


def test_badge_manip_bounds_is_badge_box(qapp, scene_and_view):
    scene, view = scene_and_view
    da = _confirmed_design_area(scene)
    from firepro3d.selection_manipulator import manip_bounds
    b = manip_bounds(da)
    badge_box = da.badge.sceneBoundingRect()
    # Frame wraps the badge (the thing that moves), not the whole tile outline.
    assert abs(b.center().x() - badge_box.center().x()) < 1e-3
    assert abs(b.center().y() - badge_box.center().y()) < 1e-3


# ── NoteAnnotation ──────────────────────────────────────────────────────────

def test_note_annotation_moves_via_manipulator(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.annotations import NoteAnnotation
    from firepro3d.selection_manipulator import item_capabilities
    note = NoteAnnotation("Hello", x=100.0, y=100.0)
    scene.addItem(note)
    scene.annotations.add_note(note)
    assert item_capabilities(note) == {"translate"}   # translate-only

    note.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    assert note in manip.selection_items()
    assert _visible_handles(manip) == []              # no resize/rotate handles

    scene.push_undo_state()
    depth0 = len(scene._undo_stack)
    p0 = note.scenePos()

    manip._begin("move", QPointF(100, 100), QPointF(100, 100))
    manip._update(QPointF(160, 130), Qt.KeyboardModifier.NoModifier,
                  QPointF(160, 130))
    manip._finish(QPointF(160, 130), Qt.KeyboardModifier.NoModifier)
    qapp.processEvents()

    p1 = note.scenePos()
    assert abs((p1.x() - p0.x()) - 60.0) < 2.0
    assert abs((p1.y() - p0.y()) - 30.0) < 2.0
    assert note.transform().isIdentity()
    assert len(scene._undo_stack) == depth0 + 1


def test_dimension_annotation_moves_via_manipulator(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.annotations import DimensionAnnotation
    from firepro3d.selection_manipulator import item_capabilities
    dim = DimensionAnnotation(QPointF(0.0, 0.0), QPointF(1000.0, 0.0))
    scene.addItem(dim)
    scene.annotations.add_dimension(dim)
    assert item_capabilities(dim) == {"translate"}

    dim.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    assert dim in manip.selection_items()
    assert _visible_handles(manip) == []

    scene.push_undo_state()
    depth0 = len(scene._undo_stack)
    p1_0 = QPointF(dim._p1)
    p2_0 = QPointF(dim._p2)

    manip._begin("move", QPointF(500, 0), QPointF(500, 0))
    manip._update(QPointF(500, 200), Qt.KeyboardModifier.NoModifier,
                  QPointF(500, 200))
    manip._finish(QPointF(500, 200), Qt.KeyboardModifier.NoModifier)
    qapp.processEvents()

    # Endpoints translated by the same delta (internal-coord move, not moveBy).
    assert abs((dim._p1.y() - p1_0.y()) - 200.0) < 2.0
    assert abs((dim._p2.y() - p2_0.y()) - 200.0) < 2.0
    assert abs(dim._p1.x() - p1_0.x()) < 2.0
    assert abs(dim._p2.x() - p2_0.x()) < 2.0
    assert dim.transform().isIdentity()
    assert len(scene._undo_stack) == depth0 + 1


# ── drawForeground boundary dedup ───────────────────────────────────────────

def test_manipulator_frame_is_sole_boundary(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(item)
    item.setSelected(True)
    qapp.processEvents()

    manip = _manip(scene)
    assert manip.wraps(item)                          # manipulator owns the box
    # The view's boundary-draw predicate skips wrapped items: the manipulator
    # frame is the one boundary.  Grips are unaffected (drawn separately).
    assert view._should_draw_selection_boundary(item) is False


def test_boundary_predicate_true_for_unwrapped(qapp, scene_and_view):
    scene, view = scene_and_view
    from firepro3d.construction_geometry import LineItem
    item = LineItem(QPointF(0, 0), QPointF(100, 0))
    scene.addItem(item)          # NOT selected → not wrapped
    qapp.processEvents()
    manip = _manip(scene)
    assert not manip.wraps(item)
    assert view._should_draw_selection_boundary(item) is True
