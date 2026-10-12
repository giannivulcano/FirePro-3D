"""Instance panel rows: Mirrored / Scale + one undo step per edit (G8/G9).

Every commit here goes through the REAL ``PropertyManager`` path
(``show_properties`` builds the rows, ``_apply_property`` commits), because
the G9 bug lived in that path: ``Model_Space.deferred_undo_push`` only pushes
a step when a setter asks for one.
"""
import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.property_manager import PropertyManager

IDENTITY = ("Level 1", 0.0, 0.0, False, 1.0)


def _scene(n=1):
    """A Model_Space with *n* identity-posed instances and a seed undo state."""
    ms = Model_Space()
    ms._level_manager = LevelManager()
    d = BlockDefinition.new(name="L", library="L", series="S", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(100, 0)).to_dict()])
    ms.register_block_definition(d)
    insts = [ms.place_block_instance(d.id, (200.0 * i, 0.0)) for i in range(n)]
    ms.push_undo_state()
    return ms, insts


def _state(inst):
    return (inst.level, inst._level_offset_mm, inst.block_rotation(),
            inst.block_mirrored(), inst.block_scale())


def _depth(ms):
    return len(ms._undo_stack)


def _panel(targets):
    """A PropertyManager showing *targets* through the real row builder."""
    pm = PropertyManager()
    pm.show_properties(targets if len(targets) > 1 else targets[0])
    QApplication.processEvents()
    return pm


def _panel_commit(targets, key, value):
    _panel(targets)._apply_property(key, value)


def test_rows_present(qapp):
    _ms, (inst,) = _scene()
    props = inst.get_properties()
    keys = list(props)
    assert props["Mirrored"]["type"] == "bool" and props["Mirrored"]["value"] is False
    sc = props["Scale"]
    assert sc["type"] == "dimension"
    assert sc["value"] == "1" and sc["value_mm"] == 1.0
    assert sc["parser"]("2x") == 2.0 and sc["parser"]("abc") is None
    assert sc["formatter"](0.5) == "0.5"
    assert sc["minimum"] == 0.0
    # Pose rows stay together: Rotation, Mirrored, Scale, then the overrides.
    assert keys.index("Mirrored") == keys.index("Rotation") + 1
    assert keys.index("Scale") == keys.index("Mirrored") + 1
    inst.set_block_mirrored(True)
    inst.set_block_scale(0.25)
    props = inst.get_properties()
    assert props["Mirrored"]["value"] is True
    assert props["Scale"]["value"] == "0.25" and props["Scale"]["value_mm"] == 0.25


# Values are what each real row hands _apply_property: level_ref combo -> str,
# dimension DimensionEdit -> value_mm() float, string QLineEdit -> text,
# bool checkbox -> isChecked() bool.
@pytest.mark.parametrize("key,value,check", [
    ("Rotation", "45", lambda i: i.block_rotation() == pytest.approx(45.0)),
    ("Level Offset", 300.0, lambda i: i._level_offset_mm == 300.0),
    ("Level", "Level 2", lambda i: i.level == "Level 2"),
    ("Mirrored", True, lambda i: i.block_mirrored() is True),
    ("Scale", 2.0, lambda i: i.block_scale() == pytest.approx(2.0)),
])
def test_each_row_edit_is_one_undo_step(qapp, key, value, check):
    ms, (inst,) = _scene()
    d0 = _depth(ms)
    _panel_commit([inst], key, value)
    assert check(inst)
    assert _depth(ms) == d0 + 1          # G9: one step per panel commit
    ms.undo()
    (now,) = ms._block_instances
    assert _state(now) == IDENTITY


@pytest.mark.parametrize("key,value", [
    ("Rotation", "0.0"),
    ("Level Offset", 0.0),
    ("Level", "Level 1"),
    ("Mirrored", False),
    ("Scale", 1.0),
])
def test_noop_commit_is_no_step(qapp, key, value):
    ms, (inst,) = _scene()
    d0 = _depth(ms)
    _panel_commit([inst], key, value)
    assert _state(inst) == IDENTITY
    assert _depth(ms) == d0


def test_multi_select_commit_is_one_step(qapp):
    ms, insts = _scene(n=2)
    d0 = _depth(ms)
    _panel_commit(insts, "Mirrored", True)
    assert all(i.block_mirrored() for i in insts)
    assert _depth(ms) == d0 + 1
    _panel_commit(insts, "Scale", 3.0)
    assert [i.block_scale() for i in insts] == [3.0, 3.0]
    assert _depth(ms) == d0 + 2
    ms.undo()
    assert sorted(_state(i) for i in ms._block_instances) == \
        [("Level 1", 0.0, 0.0, True, 1.0)] * 2
    ms.undo()
    assert [_state(i) for i in ms._block_instances] == [IDENTITY] * 2


@pytest.mark.parametrize("bad", ["0", "-2", "abc", "1e3", "", None,
                                 0.0, -1.0, math.nan, math.inf])
def test_bad_scale_is_refused_unchanged(qapp, bad):
    ms, (inst,) = _scene()
    d0 = _depth(ms)
    _panel_commit([inst], "Scale", bad)     # must not raise
    assert inst.block_scale() == 1.0
    assert _depth(ms) == d0


def test_scale_row_widget_commits_through_the_factor_grammar(qapp):
    """The real DimensionEdit built for the Scale row: FACTOR grammar in,
    format_factor text out, bad / zero input reverts without a commit."""
    ms, (inst,) = _scene()
    pm = _panel([inst])
    edit = pm._prop_widgets["Scale"]
    assert edit.text() == "1"
    d0 = _depth(ms)
    edit.setText("2x")
    edit.editingFinished.emit()
    assert inst.block_scale() == 2.0 and edit.text() == "2"
    assert _depth(ms) == d0 + 1
    for bad in ("0", "-3", "abc", "1e2"):
        edit.setText(bad)
        edit.editingFinished.emit()
        assert inst.block_scale() == 2.0 and edit.text() == "2"
    assert _depth(ms) == d0 + 1
    edit.setText("0.5")
    edit.editingFinished.emit()
    assert inst.block_scale() == 0.5 and edit.text() == "0.5"
    assert _depth(ms) == d0 + 2


def test_mirrored_checkbox_click_flips_and_is_one_step(qapp):
    """The real checkbox built for the Mirrored row toggles the pose."""
    ms, (inst,) = _scene()
    pm = _panel([inst])
    chk = pm._prop_widgets["Mirrored"]
    assert chk.isChecked() is False
    d0 = _depth(ms)
    chk.click()
    assert inst.block_mirrored() is True and _depth(ms) == d0 + 1
    chk.click()
    assert inst.block_mirrored() is False and _depth(ms) == d0 + 2
    ms.undo()
    (now,) = ms._block_instances
    assert now.block_mirrored() is True
