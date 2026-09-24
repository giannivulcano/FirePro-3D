"""Task 5b: grip-object limit (frame-only above N selected items) + O(1)
``SelectionManipulator.wraps()``.

Governing spec: docs/specs/selection-manipulator.md. Ground truth is the
VISIBLE grip hosts the manipulator actually shows (``manip._host_pool`` for
item-provided grips, ``manip._handles`` for the rigid box-native resize set)
— not internal handle-list lengths, per the house rule against asserting a
proxy instead of the observable effect.
"""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtTest import QTest

from firepro3d import selection_manipulator
from firepro3d.model_space import Model_Space
from firepro3d.level_manager import LevelManager
from firepro3d.scale_manager import ScaleManager
from firepro3d.model_view import Model_View
from firepro3d.selection_manipulator import SelectionManipulator
from firepro3d.geometry_2d import LineItem


@pytest.fixture
def scene_and_view(qapp):
    """A shown Model_View over a Model_Space, pinned to identity zoom (mirrors
    tests/test_selection_manipulator.py's fixture)."""
    scene = Model_Space()
    scene._level_manager = LevelManager()      # seeds Level 1 (elevation 0.0)
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


def _manip(scene):
    return next(i for i in scene.items()
                if isinstance(i, SelectionManipulator))


def _visible_hosts(manip):
    """Visible item-provided grip hosts (the ones a large selection's paint
    pass built one-per-selected-item — the O(n) cost this task caps)."""
    return sum(1 for h in manip._host_pool if h.isVisible())


def _visible_rigid(manip):
    """Visible rigid resize handles (box-native single-item path)."""
    return sum(1 for h in manip._handles.values() if h.isVisible())


def _lines(n, spacing=20.0):
    return [LineItem(QPointF(i * spacing, 0), QPointF(i * spacing + 10, 0))
            for i in range(n)]


# ── Grip-object limit: gates the per-item grip hosts, not the frame ─────────

def test_two_lines_show_grips_by_default(qapp, scene_and_view):
    scene, view = scene_and_view
    items = _lines(2)
    for it in items:
        scene.addItem(it)
    scene.select_items(items)
    qapp.processEvents()
    manip = _manip(scene)
    assert manip.isVisible()
    assert _visible_hosts(manip) > 0


def test_limit_1_hides_grips_keeps_frame(qapp, scene_and_view):
    scene, view = scene_and_view
    selection_manipulator.GRIP_OBJECT_LIMIT = 1
    items = _lines(2)
    for it in items:
        scene.addItem(it)
    scene.select_items(items)
    qapp.processEvents()
    manip = _manip(scene)
    assert manip.isVisible()                 # frame still shown
    assert _visible_hosts(manip) == 0         # no per-item grips


def test_default_limit_101_items_no_grips_100_items_has_grips(qapp, scene_and_view):
    scene, view = scene_and_view
    assert selection_manipulator.GRIP_OBJECT_LIMIT == 100

    items = _lines(101)
    for it in items:
        scene.addItem(it)
    scene.select_items(items)
    qapp.processEvents()
    manip = _manip(scene)
    assert manip.isVisible()
    assert _visible_hosts(manip) == 0

    scene.select_items(items[:100])
    qapp.processEvents()
    assert _visible_hosts(manip) > 0


def test_box_native_single_still_shows_rigid_handles_at_limit_1(qapp, scene_and_view):
    """Single-item box-native (scale-capable) branch precedes the limit check
    in _active_handles — 1 item is never "more than" limit=1 anyway."""
    from firepro3d.text_item import TextItem, TextAnnotationData
    scene, view = scene_and_view
    selection_manipulator.GRIP_OBJECT_LIMIT = 1
    t = TextItem(TextAnnotationData(text="Hi", x=0, y=0,
                                    wrap_width_mm=40, box_height_mm=20))
    t._force_device_independent = True
    t._apply_format()
    scene.addItem(t)
    t.setSelected(True)
    qapp.processEvents()
    manip = _manip(scene)
    assert manip._is_box_native_single(t)
    assert _visible_rigid(manip) > 0


# ── RED-check guard: prove the limit branch is what gates the hosts ────────

def test_limit_branch_is_reachable_in_active_handles(qapp, scene_and_view):
    """Directly exercises _active_handles() (bypassing paint) so a future
    refactor that removes the early-return can't silently regress; combined
    with test_default_limit_101_items_no_grips_100_items_has_grips this is
    the RED/GREEN pair called out in the task brief."""
    scene, view = scene_and_view
    items = _lines(101)
    for it in items:
        scene.addItem(it)
    scene.select_items(items)
    qapp.processEvents()
    manip = _manip(scene)
    assert manip._active_handles() == []


# ── wraps() correctness (now backed by a membership set, not a list scan) ──

def test_wraps_true_for_selected_false_for_unselected_across_changes(qapp, scene_and_view):
    scene, view = scene_and_view
    a, b, c = _lines(3)
    for it in (a, b, c):
        scene.addItem(it)
    scene.select_items([a, b])
    qapp.processEvents()
    manip = _manip(scene)
    assert manip.wraps(a) and manip.wraps(b)
    assert not manip.wraps(c)

    # add c
    scene.select_items([a, b, c])
    qapp.processEvents()
    assert manip.wraps(a) and manip.wraps(b) and manip.wraps(c)

    # remove a
    scene.select_items([b, c])
    qapp.processEvents()
    assert not manip.wraps(a)
    assert manip.wraps(b) and manip.wraps(c)


# ── Preferences pane wiring ──────────────────────────────────────────────────

def test_pane_apply_sets_global_and_qsettings_revert_restores(qapp):
    from PyQt6.QtCore import QSettings
    from firepro3d.settings.panes import UXPane, _QSETTINGS_ORG, _QSETTINGS_APP

    before = selection_manipulator.GRIP_OBJECT_LIMIT
    pane = UXPane()
    pane.load()
    assert pane._grip_limit_spin.value() == before

    pane._grip_limit_spin.setValue(7)
    pane.apply()
    assert selection_manipulator.GRIP_OBJECT_LIMIT == 7
    s = QSettings(_QSETTINGS_ORG, _QSETTINGS_APP)
    assert s.value("select/grip_object_limit", type=int) == 7

    pane.revert()
    assert selection_manipulator.GRIP_OBJECT_LIMIT == before
    assert pane._grip_limit_spin.value() == before
