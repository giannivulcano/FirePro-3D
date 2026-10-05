"""LT3-12 -- Linetype picker: project + folder, load on pick, Missing.

QSettings and the block library are isolated per test by the autouse
fixtures in tests/conftest.py (``_isolate_qsettings`` /
``_isolate_block_library``), so setting ``LINETYPE_DIR_KEY`` here never leaks.
"""
import pytest
from PyQt6.QtCore import QPointF, QSettings

from firepro3d import app_data, block_library
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import hidden, make_linetype


@pytest.fixture
def lt_dir(qapp, tmp_path):
    """A folder set as the Linetypes folder (isolated QSettings)."""
    root = tmp_path / "linetypes_root"
    root.mkdir()
    QSettings("GV", "FirePro3D").setValue(app_data.LINETYPE_DIR_KEY, str(root))
    return root


def _folder(lt_dir, name="Center", series="Linetypes"):
    lt = make_linetype(name=name)
    lt.series = series
    block_library.save_to_library(lt, root=str(lt_dir))
    return lt


def _line_in(ms):
    """A line in *ms*'s undo-snapshot draw list, with a baseline step."""
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    ms.push_undo_state()
    return ln


def test_options_order_project_then_folder(lt_dir):
    ms = Model_Space(scene_role="block_editor")
    hidden(ms)
    _folder(lt_dir)
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ms.addItem(ln)
    row = ln.get_properties()["Linetype"]
    assert row["options"] == ["Continuous", "By Block", "Hidden", "Center"]
    assert row["value"] == "Continuous"


def test_folder_linetype_already_in_project_is_listed_once(lt_dir):
    ms = Model_Space()
    lt = _folder(lt_dir, name="Hidden")
    ms.register_block_definition(lt)
    ln = _line_in(ms)
    assert ln.get_properties()["Linetype"]["options"] == [
        "Continuous", "By Block", "Hidden"]


def test_colliding_names_get_unique_labels(lt_dir):
    ms = Model_Space()
    proj = hidden(ms)                         # project "Hidden"
    # A different folder "Hidden" (another Series, so its load is no clash).
    lib = _folder(lt_dir, name="Hidden", series="Other")
    ln = _line_in(ms)
    assert ln.get_properties()["Linetype"]["options"] == [
        "Continuous", "By Block", "Hidden", "Hidden (library)"]
    ln.set_property("Linetype", "Hidden")
    assert ln.style["linetype"] == proj
    ln.set_property("Linetype", "Hidden (library)")
    assert ln.style["linetype"] == lib.id


def test_pick_folder_linetype_loads_it_in_one_undo_step(lt_dir):
    ms = Model_Space()
    lt = _folder(lt_dir)
    ln = _line_in(ms)
    pos0 = ms._undo_pos
    ln.set_property("Linetype", "Center")
    assert ln.style["linetype"] == lt.id
    assert ms.get_block_definition(lt.id) is not None
    assert ms._undo_pos == pos0 + 1                    # the load's one batch
    assert ln.get_properties()["Linetype"]["value"] == "Center"
    ms.undo()                                          # one step removes both
    assert ms.get_block_definition(lt.id) is None
    (ln2,) = ms._draw_lines                            # restored (refs invalidated)
    assert ln2.style["linetype"] == "continuous"
    ms.redo()
    (ln3,) = ms._draw_lines
    assert ln3.style["linetype"] == lt.id               # the step carried the ref
    assert ms.get_block_definition(lt.id) is not None


def test_failed_folder_load_keeps_the_old_ref(lt_dir, monkeypatch):
    from firepro3d import themed_message
    shown = []
    monkeypatch.setattr(themed_message, "themed_info",
                        lambda *a, **k: shown.append(a))
    ms = Model_Space()
    lid = hidden(ms)
    lt = _folder(lt_dir, name="Center")
    # A project block with the same (library, series, name) but another id:
    # the folder file is refused on load.
    clash = make_linetype(name="Center")
    ms.register_block_definition(clash)
    ln = _line_in(ms)
    ln.set_property("Linetype", "Hidden")
    pos0 = ms._undo_pos
    opts = ln.get_properties()["Linetype"]["options"]
    lib_label = next(o for o in opts if o.startswith("Center ("))
    ln.set_property("Linetype", lib_label)
    assert ms.get_block_definition(lt.id) is None
    assert ln.style["linetype"] == lid                  # restored
    assert ms._undo_pos == pos0                         # nothing pushed
    assert shown                                        # the failure was reported


def test_pick_project_linetype_is_one_undo_step(qapp):
    ms = Model_Space()
    lid = hidden(ms)
    ln = _line_in(ms)
    pos0 = ms._undo_pos
    ln.set_property("Linetype", "Hidden")
    assert ln.style["linetype"] == lid
    assert ms._undo_pos == pos0 + 1
    ms.undo()
    assert ms._draw_lines[0].style["linetype"] == "continuous"


def test_fixed_choices_still_resolve(qapp):
    ms = Model_Space()
    ln = _line_in(ms)
    ln.set_property("Linetype", "By Block")
    assert ln.style["linetype"] == "by_block"
    ln.set_property("Linetype", "Continuous")
    assert ln.style["linetype"] == "continuous"


def test_missing_label_and_choice_never_rewrites(qapp):
    ms = Model_Space()
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ln.style["linetype"] = "deadbeef"
    ms.addItem(ln)
    ms._draw_lines.append(ln)
    ms.push_undo_state()
    pos0 = ms._undo_pos
    row = ln.get_properties()["Linetype"]
    assert row["value"] == "Missing (deadbeef)"
    assert row["options"][0] == "Missing (deadbeef)"
    ln.set_property("Linetype", "Missing (deadbeef)")
    ln.set_property("Linetype", "No such linetype")
    assert ln.style["linetype"] == "deadbeef"
    assert ms._undo_pos == pos0


def test_block_editor_picker_excludes_the_edited_block(qapp):
    ms = Model_Space(scene_role="block_editor")
    lid = hidden(ms)
    hidden(ms, name="Center")
    ms._editing_block_id = lid
    ln = LineItem(QPointF(0, 0), QPointF(10, 0))
    ms.addItem(ln)
    assert ln.get_properties()["Linetype"]["options"] == [
        "Continuous", "By Block", "Center"]


def test_pick_through_the_property_panel_loads_it(lt_dir):
    """VC3 real path: the panel combo -> PropertyManager._apply_property ->
    set_property -> load + store, still one undo step."""
    from PyQt6.QtWidgets import QApplication
    from firepro3d.property_manager import PropertyManager
    ms = Model_Space()
    lt = _folder(lt_dir)
    ln = _line_in(ms)
    pm = PropertyManager()
    pm.show_properties([ln])
    QApplication.processEvents()
    combo = pm._prop_widgets["Linetype"]
    items = [combo.itemText(i) for i in range(combo.count())]
    assert items == ["Continuous", "By Block", "Center"]
    pos0 = ms._undo_pos
    combo.setCurrentText("Center")
    QApplication.processEvents()
    assert ln.style["linetype"] == lt.id
    assert ms.get_block_definition(lt.id) is not None
    assert ms._undo_pos == pos0 + 1
