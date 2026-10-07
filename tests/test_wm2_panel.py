"""WM2 Q4/Q5/Q12 panel rows + G11 mixed selection."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import paper_display as pd
from firepro3d.geometry_2d import LineItem
from tests.lt3_support import make_linetype
from tests.wm2_support import scene_with, sprinkler_def


def test_rows_and_options(qapp):
    lt = make_linetype()
    s = sprinkler_def()
    ms, inst = scene_with([lt, s], s.id)
    props = inst.get_properties()
    keys = list(props)
    assert keys.index("Linetype") == keys.index("Rotation") + 1
    assert keys.index("Weight") == keys.index("Linetype") + 1
    w = props["Weight"]
    assert w["value"] == "As Authored"
    assert w["options"][:2] == ["As Authored",
                                f"By Category ({pd.picker_weight_name(pd.model_blocks_weight())})"]
    assert not any(o.startswith("By Linetype") for o in w["options"])
    assert w["options"][2:] == pd.weight_names()
    lto = props["Linetype"]["options"]
    assert lto[0] == "As Authored" and "Continuous" in lto and "Hidden" in lto
    assert props["Linetype"]["value"] == "As Authored"
    assert props["Weight"]["tooltip"] and props["Linetype"]["tooltip"]


def test_rows_show_stored_override(qapp):
    lt = make_linetype()
    s = sprinkler_def()
    ms, inst = scene_with([lt, s], s.id, {"weight": "by_category",
                                          "linetype": lt.id})
    props = inst.get_properties()
    assert props["Weight"]["value"] == props["Weight"]["options"][1]
    assert props["Linetype"]["value"] == "Hidden"
    inst.set_overrides({"weight": "Thick"})
    assert inst.get_properties()["Weight"]["value"] == "Thick"


def test_set_property_applies_and_ignores_foreign_labels(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    inst.set_property("Weight", "Thick")
    assert inst.overrides["weight"] == "Thick"
    inst.set_property("Weight", "By Linetype (Thin)")       # primitive label
    assert inst.overrides["weight"] == "Thick"
    inst.set_property("Weight", "No Such Weight")
    assert inst.overrides["weight"] == "Thick"
    inst.set_property("Weight", inst.get_properties()["Weight"]["options"][1])
    assert inst.overrides["weight"] == "by_category"
    inst.set_property("Linetype", "Continuous")
    assert inst.overrides["linetype"] == "continuous"
    inst.set_property("Linetype", "Missing (abc)")
    assert inst.overrides["linetype"] == "continuous"
    inst.set_property("Linetype", "As Authored")
    assert inst.overrides["linetype"] == "as_authored"


def test_set_property_pushes_one_undo_step_and_noop_pushes_none(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ms.push_undo_state()
    before = ms._undo_pos
    inst.set_property("Weight", "Thick")
    assert ms._undo_pos == before + 1
    inst.set_property("Weight", "Thick")                     # no-op commit
    assert ms._undo_pos == before + 1


def test_g11_mixed_selection_primitive_ignores_block_labels(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["weight"] = "Thin"
    ln.set_property("Weight", "As Authored")
    ln.set_property("Weight", "By Category (Thinnest)")
    assert ln.style["weight"] == "Thin"
    for t in (inst, ln):
        t.set_property("Weight", "Thick")
    assert inst.overrides["weight"] == "Thick" and ln.style["weight"] == "Thick"


def test_q12_rows_locked_in_capability_editor(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    assert not inst.get_properties()["Weight"].get("disabled")
    ms.set_block_tile({"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"},
                     push_undo=False)
    props = inst.get_properties()
    assert props["Linetype"].get("disabled") and props["Weight"].get("disabled")
    assert props["Weight"]["tooltip"] == props["Linetype"]["tooltip"]
    assert "pattern" in props["Weight"]["tooltip"]


def test_q12_rows_locked_in_linetype_unit_editor(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id)
    ms.set_block_capability(("repeat", {"length": 9.0, "size": "drafting"}),
                            push_undo=False)
    props = inst.get_properties()
    assert props["Linetype"].get("disabled") and props["Weight"].get("disabled")


def test_q12_mixed_selection_primitive_first_cannot_bypass_lock(qapp):
    """The panel builds its rows from the primitive (enabled) -- a commit
    through the real PropertyManager path must still leave the nested block
    in a tile editor As Authored on both axes."""
    from PyQt6.QtWidgets import QApplication
    from firepro3d.property_manager import PropertyManager
    lt = make_linetype()
    s = sprinkler_def()
    ms, inst = scene_with([lt, s], s.id)
    ms.set_block_tile({"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"},
                      push_undo=False)
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    pm = PropertyManager()
    pm.show_properties([ln, inst])
    QApplication.processEvents()
    pm._apply_property("Weight", "Thick")
    pm._apply_property("Linetype", "Hidden")
    QApplication.processEvents()
    assert ln.style["weight"] == "Thick"                 # the primitive took it
    assert inst.overrides == {"weight": "as_authored",
                              "linetype": "as_authored"}


# --- linetype picks on a placed block in the PROJECT scene (LT3-12 parity) --

@pytest.fixture
def lt_dir(qapp, tmp_path):
    """A folder set as the Linetypes folder (QSettings isolated by conftest)."""
    from PyQt6.QtCore import QSettings
    from firepro3d import app_data
    root = tmp_path / "linetypes_root"
    root.mkdir()
    QSettings("GV", "FirePro3D").setValue(app_data.LINETYPE_DIR_KEY, str(root))
    return root


def _folder(lt_dir, name="Center"):
    from firepro3d import block_library
    lt = make_linetype(name=name)
    lt.series = "Linetypes"
    block_library.save_to_library(lt, root=str(lt_dir))
    return lt


def _placed(ms_defs=()):
    s = sprinkler_def()
    ms, inst = scene_with([*ms_defs, s], s.id)
    ms.push_undo_state()
    return ms, inst, s


def test_folder_linetype_pick_loads_it_in_one_undo_step(lt_dir):
    lt = _folder(lt_dir)
    ms, inst, s = _placed()
    pos0 = ms._undo_pos
    inst.set_property("Linetype", "Center")
    assert inst.overrides["linetype"] == lt.id
    assert ms.get_block_definition(lt.id) is not None    # loaded into project
    assert ms._undo_pos == pos0 + 1                      # exactly one step
    assert inst.get_properties()["Linetype"]["value"] == "Center"
    ms.undo()
    assert ms.get_block_definition(lt.id) is None
    (inst2,) = ms._block_instances                       # refs invalidated
    assert inst2.overrides["linetype"] == "as_authored"


def test_failed_folder_load_restores_old_override(lt_dir, monkeypatch):
    from firepro3d import themed_message
    shown = []
    monkeypatch.setattr(themed_message, "themed_info",
                        lambda *a, **k: shown.append(a))
    hid = make_linetype(name="Hidden")
    lt = _folder(lt_dir, name="Center")
    clash = make_linetype(name="Center")       # same lib/series/name, other id
    ms, inst, s = _placed([hid, clash])
    inst.set_property("Linetype", "Hidden")
    assert inst.overrides["linetype"] == hid.id
    pos0 = ms._undo_pos
    lib = next(o for o in inst.get_properties()["Linetype"]["options"]
               if o.startswith("Center ("))
    inst.set_property("Linetype", lib)
    assert ms.get_block_definition(lt.id) is None
    assert inst.overrides["linetype"] == hid.id          # restored
    assert ms._undo_pos == pos0                          # nothing pushed
    assert shown


def test_missing_override_linetype_never_rewrites(qapp):
    s = sprinkler_def()
    ms, inst = scene_with([s], s.id, {"linetype": "deadbeef"})
    ms.push_undo_state()
    pos0 = ms._undo_pos
    row = inst.get_properties()["Linetype"]
    assert row["value"] == "Missing (deadbeef)"
    assert "Missing (deadbeef)" in row["options"]
    inst.set_property("Linetype", "Missing (deadbeef)")
    inst.set_property("Linetype", "No such linetype")
    assert inst.overrides["linetype"] == "deadbeef"
    assert ms._undo_pos == pos0
