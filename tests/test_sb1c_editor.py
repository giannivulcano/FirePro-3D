"""SB1c G-editor -- the On screen row and the annotative meta (D2 / D8 / D9).
Helpers copied from tests/test_sb1a_editor.py (not imported)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QTabWidget

from firepro3d.block_definition import BlockDefinition
from firepro3d.block_editor import BlockEditorManager
from firepro3d.block_properties_info import BlockPropertiesInfo
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


def _editor(project=None):
    project = project or Model_Space()
    mgr = BlockEditorManager(QTabWidget(), project)
    return project, mgr.open_new()


def _line():
    return LineItem(QPointF(-3.0, 0.0), QPointF(3.0, 0.0)).to_dict()


def test_on_screen_row_only_for_annotative(qapp):
    project, w = _editor()
    w.seed_from_dicts([_line()])
    info = BlockPropertiesInfo(w.editor_scene, "B", editor=w)
    assert "On screen" not in info.get_properties()
    info.set_property("Scale mode", "Annotative")
    props = info.get_properties()
    keys = list(props)
    assert keys[keys.index("Scale mode") + 1] == "On screen"
    assert props["On screen"]["options"] == ["Fixed size", "Scale with zoom"]
    assert props["On screen"]["value"] == "Scale with zoom"        # D2 default
    info.set_property("On screen", "Fixed size")
    assert w.editor_scene.block_meta["annotative_screen"] == "fixed"
    defn = w.commit_block("B", "L", "S")
    assert defn.scale_mode == "annotative" and defn.annotative_screen == "fixed"
    back = BlockDefinition.from_dict(defn.to_dict())
    assert back.annotative_screen == "fixed"
    w2 = BlockEditorManager(QTabWidget(), project).open_for_definition(defn.id)
    w2.seed_from_definition(defn)
    assert w2.editor_scene.block_meta["annotative_screen"] == "fixed"
    info.set_property("Scale mode", "Real size")
    assert "On screen" not in info.get_properties()


def test_on_screen_meta_undoes(qapp):
    project, w = _editor()
    w.seed_from_dicts([_line()])
    sc = w.editor_scene
    sc.set_block_meta({**sc.block_meta, "scale_mode": "annotative"})
    sc.set_block_meta({**sc.block_meta, "annotative_screen": "fixed"})
    sc.undo()
    assert sc.block_meta["annotative_screen"] == "scale"


def test_g_editor_stores_authored_mm(qapp):
    """D9 / AC3 parity: an annotative definition stores what was drawn, 1:1."""
    project, w = _editor()
    w.seed_from_dicts([_line()])
    w.editor_scene.set_block_meta({**w.editor_scene.block_meta, "scale_mode": "annotative"})
    defn = w.commit_block("B", "L", "S")
    assert defn.render_ops()[0].path.boundingRect().width() == pytest.approx(6.0)


def test_panel_relists_on_screen_row_after_scale_mode_edit(qapp):
    """D13 / D8: a Scale mode edit through the real PropertyManager re-lists
    the rows (the 50 ms refresh timer) so the On screen row appears."""
    from PyQt6.QtTest import QTest
    from firepro3d.property_manager import PropertyManager
    project, w = _editor()
    w.seed_from_dicts([_line()])
    info = BlockPropertiesInfo(w.editor_scene, "B", editor=w)
    pm = PropertyManager()
    pm.show_properties(info)
    assert "On screen" not in pm._prop_widgets
    pm._apply_property("Scale mode", "Annotative")
    QTest.qWait(200)
    assert "On screen" in pm._prop_widgets
    pm._apply_property("Scale mode", "Real size")
    QTest.qWait(200)
    assert "On screen" not in pm._prop_widgets
