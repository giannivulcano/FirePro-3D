"""WM3 D4 / AC1 / AC8 -- the placement Colour row, its setter, the panel's
Pick colour action, mixed selections and the Q4 lock."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from firepro3d import paper_display as pd
from firepro3d.geometry_2d import LineItem
from tests.wm2_support import nested_record, scene_with, sprinkler_def
from tests.wm3_support import OVR

_PICK = "Pick colour\u2026"
_BY_CAT = "By Category (Automatic)"      # factory Model "Blocks" colour = Automatic (Q3)
_OVR_LABEL = OVR.upper()                 # the Swatch label of a hex colour


@pytest.fixture
def make_pm(qapp):
    """Real PropertyManagers for one test; teardown stops each one's pending
    refresh timer and deletes it, so a dropped manager's 50 ms timer cannot
    fire into a later test (memory: panel test timer crash, 0xC0000409)."""
    from PyQt6 import sip
    from firepro3d.property_manager import PropertyManager
    made = []

    def make(targets):
        pm = PropertyManager()
        made.append(pm)
        pm.show_properties(targets)
        QApplication.processEvents()
        return pm

    yield make
    for pm in made:
        if not sip.isdeleted(pm):
            pm._refresh_timer.stop()
            pm.deleteLater()
    QApplication.processEvents()


def test_colour_row_follows_weight_with_options(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    props = inst.get_properties()
    keys = list(props)
    assert keys.index("Colour") == keys.index("Weight") + 1
    row = props["Colour"]
    assert row["type"] == "enum" and row["value"] == "As Authored"
    assert row["options"] == ["As Authored", _BY_CAT, _PICK]
    assert row["action_options"] == {_PICK: "colour"}
    assert row["icons"] == {_BY_CAT: "token:auto"}
    assert row["tooltip"]


def test_colour_row_shows_the_picked_colour_and_by_category_value(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id, {"colour": OVR})
    row = inst.get_properties()["Colour"]
    assert row["value"] == _OVR_LABEL == row["options"][-1]
    assert row["icons"][_OVR_LABEL] == OVR
    pd.set_model_blocks_colour("#808000")
    inst.set_overrides({"colour": "by_category"})
    row = inst.get_properties()["Colour"]
    assert row["value"] == "By Category (#808000)" == row["options"][1]
    inst.set_overrides({"colour": "token:accent"})
    assert inst.get_properties()["Colour"]["value"] == "Accent"


def test_set_property_colour_labels_and_values(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    inst.set_property("Colour", _OVR_LABEL)
    assert inst.overrides["colour"] == OVR
    inst.set_property("Colour", _BY_CAT)
    assert inst.overrides["colour"] == "by_category"
    inst.set_property("Colour", "Automatic")
    assert inst.overrides["colour"] == "token:auto"
    for ignored in (_PICK, "", "No such colour", "token:bg"):
        inst.set_property("Colour", ignored)
        assert inst.overrides["colour"] == "token:auto", ignored
    inst.set_property("Colour", "As Authored")
    assert inst.overrides["colour"] == "as_authored"


def test_set_property_colour_one_undo_step_and_noop_none(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ms.push_undo_state()
    before = ms._undo_pos
    inst.set_property("Colour", OVR)
    assert ms._undo_pos == before + 1
    inst.set_property("Colour", _OVR_LABEL)                  # same colour: no step
    assert ms._undo_pos == before + 1


def test_mixed_selection_primitive_ignores_block_only_colour_labels(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["colour"] = "#ff0000"
    for label in ("As Authored", _BY_CAT, _PICK):
        ln.set_property("Colour", label)
        assert ln.style["colour"] == "#ff0000", label
    ln.set_property("Colour", "Accent")                      # a picked-colour label
    assert ln.style["colour"] == "token:accent"
    for t in (inst, ln):
        t.set_property("Colour", OVR)
    assert inst.overrides["colour"] == OVR and ln.style["colour"] == OVR


@pytest.mark.parametrize("cap", ["tile", "repeat"])
def test_q4_colour_row_locked_in_capability_editors(qapp, cap):
    from firepro3d.geometry_2d import _LOCKED_PLACEMENT_TIP
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    assert not inst.get_properties()["Colour"].get("disabled")
    if cap == "tile":
        ms.set_block_tile({"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"},
                          push_undo=False)
    else:
        ms.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}),
                                push_undo=False)
    row = inst.get_properties()["Colour"]
    assert row["disabled"] and row["tooltip"] == _LOCKED_PLACEMENT_TIP
    inst.set_property("Colour", OVR)
    assert inst.overrides["colour"] == "as_authored"


def test_q4_mixed_selection_primitive_first_cannot_bypass_lock(qapp, make_pm):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ms.set_block_tile({"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"},
                      push_undo=False)
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    pm = make_pm([ln, inst])
    pm._apply_property("Colour", OVR)
    QApplication.processEvents()
    assert ln.style["colour"] == OVR                         # the primitive took it
    assert inst.overrides["colour"] == "as_authored"


def test_nested_record_in_block_editor_has_the_row_and_saves_it(qapp):
    from firepro3d.block_editor import BlockEditorWidget
    from firepro3d.model_space import Model_Space
    s = sprinkler_def()
    project = Model_Space()
    project.register_block_definition(s)
    w = BlockEditorWidget(project)
    w.seed_from_dicts([nested_record(s.id)])
    (rec,) = w.editor_scene._block_instances
    assert rec.get_properties()["Colour"]["options"][:2] == ["As Authored", _BY_CAT]
    rec.set_property("Colour", OVR)
    assert rec.to_nested_dict()["overrides"]["colour"] == OVR


# -- the real PropertyManager: icons + the Pick colour action ------------------

def test_panel_row_paints_per_option_swatches(qapp, make_pm):
    pd.set_model_blocks_colour("#808000")
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id, {"colour": OVR})
    combo = make_pm([inst])._prop_widgets["Colour"]

    def chip(label):
        img = combo.itemIcon(combo.findText(label)).pixmap(16, 16).toImage()
        return QColor(img.pixel(8, 8)).name()

    assert chip("By Category (#808000)") == "#808000"
    assert chip(_OVR_LABEL) == OVR
    assert combo.itemIcon(combo.findText("As Authored")).isNull()


def test_panel_pick_colour_opens_the_picker_and_applies(qapp, monkeypatch, make_pm):
    from firepro3d import colour_picker
    calls = []
    monkeypatch.setattr(colour_picker, "pick_colour",
                        lambda initial, parent=None, context="":
                        calls.append(initial) or OVR)
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ms.push_undo_state()
    pos = ms._undo_pos
    pm = make_pm([inst])
    pm._prop_widgets["Colour"].setCurrentText(_PICK)          # the real combo
    QApplication.processEvents()
    assert calls == ["token:auto"]                 # opened by the panel, seeded Automatic
    assert inst.overrides["colour"] == OVR
    assert ms._undo_pos == pos + 1                 # one step per pick


@pytest.mark.parametrize("result", [None, ""])     # Cancel; No Fill is not a placement colour
def test_panel_pick_colour_cancel_restores_without_a_write(qapp, monkeypatch, make_pm, result):
    from firepro3d import colour_picker
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: result)
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id, {"colour": OVR})
    ms.push_undo_state()
    pos = ms._undo_pos
    combo = make_pm([inst])._prop_widgets["Colour"]
    combo.setCurrentText(_PICK)
    QApplication.processEvents()
    assert combo.currentText() == _OVR_LABEL
    assert inst.overrides["colour"] == OVR and ms._undo_pos == pos


def test_mixed_selection_block_first_by_category_skips_the_primitive(qapp, make_pm):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["colour"] = "#ff0000"
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    pm = make_pm([inst, ln])
    pm._prop_widgets["Colour"].setCurrentText(_BY_CAT)
    QApplication.processEvents()
    assert inst.overrides["colour"] == "by_category"
    assert ln.style["colour"] == "#ff0000"
