from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.model_space import Model_Space
from firepro3d.block_editor import BlockEditorManager, BlockEditorWidget
from firepro3d.construction_geometry import LineItem


def test_open_new_adds_isolated_level_less_editor_tab(qapp):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    assert isinstance(w, BlockEditorWidget)
    assert tabs.indexOf(w) != -1
    assert tabs.currentWidget() is w
    assert w.editor_scene is not project          # isolated scene
    assert isinstance(w.editor_scene, Model_Space)
    assert w.editor_scene._level_manager is None   # level-less
    assert w.editor_scene._plan_view_manager is None
    assert w._edit_block_id is None


def test_open_new_twice_makes_two_independent_tabs(qapp):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w1 = mgr.open_new()
    w2 = mgr.open_new()
    assert w1 is not w2
    assert tabs.count() == 2


def test_open_for_definition_focuses_existing(qapp):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    a = LineItem(QPointF(0, 0), QPointF(10, 0))
    defn = project.commit_block_definition(
        block_id=None, name="Corner", library="L", series="S",
        primitives=[a.to_dict()], origin=(0.0, 0.0), place_instance=False)
    w1 = mgr.open_for_definition(defn.id)
    assert w1._edit_block_id == defn.id
    n = tabs.count()
    w2 = mgr.open_for_definition(defn.id)   # same id -> focus, no new tab
    assert w2 is w1
    assert tabs.count() == n
    assert tabs.currentWidget() is w1


def test_close_removes_tab_and_untracks(qapp):
    project = Model_Space()
    tabs = QTabWidget()
    mgr = BlockEditorManager(tabs, project)
    w = mgr.open_new()
    mgr.close(w)
    assert tabs.indexOf(w) == -1
    # a fresh open still works after close
    w2 = mgr.open_new()
    assert tabs.indexOf(w2) != -1
