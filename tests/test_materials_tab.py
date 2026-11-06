"""Display Manager Materials tab (M12, M16, AC3, AC6)."""
import pytest
from PyQt6.QtCore import QPointF

from firepro3d import display_manager as dm
from firepro3d import fill_types as ft
from firepro3d import materials as mt
from firepro3d.constants import MATERIAL_NONE_ID
from firepro3d.materials_tab import NO_HATCH_LABEL, MaterialsTab
from firepro3d.wall import WallSegment


@pytest.fixture(autouse=True)
def _fresh_tables():
    ft.reset_project_table()
    mt.reset_project_table()
    yield
    ft.reset_project_table()
    mt.reset_project_table()


def _dialog(ms):
    return dm.DisplayManager(ms)


def _wall(ms, material=None):
    w = WallSegment(QPointF(0, 0), QPointF(4000, 0))
    if material is not None:
        w.material_id = material.id
    ms.addItem(w)
    ms._walls.append(w)
    return w


def test_list_starts_with_none_and_lists_every_material(qapp, model_space):
    tab = MaterialsTab(model_space)
    assert tab.names() == [m.name for m in mt.project_table().all()]
    assert tab.names()[0] == "None"


def test_selector_lists_no_hatch_plus_the_fill_types(qapp, model_space):
    tab = MaterialsTab(model_space)
    labels = [tab.section_selector().itemText(i) for i in range(tab.section_selector().count())]
    assert labels[0] == NO_HATCH_LABEL
    assert set(labels[1:]) == {t.name for t in ft.project_table().all()}


def test_edits_land_on_the_working_copy_only(qapp, model_space):
    tab = MaterialsTab(model_space)
    tab.select_name("Concrete")
    tab.set_fill_type(None)
    assert tab.table().by_name("Concrete").fill_type is None
    assert mt.project_table().by_name("Concrete").fill_type is not None
    assert tab.dirty


def test_rename_refuses_a_clash_and_a_blank(qapp, model_space):
    tab = MaterialsTab(model_space)
    tab.select_name("Concrete")
    assert not tab.set_name("Brick") and not tab.set_name("  ")
    assert tab.current().name == "Concrete"
    assert tab.set_name("Poured Concrete")


def test_none_cannot_be_renamed_or_deleted_with_the_reason_shown(qapp, model_space):
    tab = MaterialsTab(model_space)
    tab.select_name("None")
    assert not tab.delete_button().isEnabled()
    assert "None is permanent" in tab.delete_button().toolTip()
    assert not tab.name_field().isEnabled()
    tab.set_fill_type(ft.project_table().by_name("Diagonal").id)     # repoint is allowed
    assert tab.table().get(MATERIAL_NONE_ID).fill_type is not None


def test_in_use_delete_is_refused_with_used_by_n(qapp, model_space):
    brick = mt.project_table().by_name("Brick")
    _wall(model_space, brick)
    _wall(model_space, brick)
    tab = MaterialsTab(model_space)
    tab.select_name("Brick")
    assert not tab.delete_button().isEnabled()
    assert tab.delete_button().toolTip() == "Used by 1: 2 wall(s)"
    assert tab.used_label().text() == "Used by 1: 2 wall(s)"
    tab._on_delete()
    assert tab.table().by_name("Brick") is not None


def test_a_category_default_blocks_delete_and_an_unused_one_deletes(qapp, model_space):
    tab = MaterialsTab(model_space)
    tab.select_name("Brick")
    tab.set_default("Wall", tab.current().id)
    assert not tab.delete_button().isEnabled()
    tab.set_default("Wall", MATERIAL_NONE_ID)
    assert tab.delete_button().isEnabled()
    tab._on_delete()
    assert tab.table().by_name("Brick") is None


def test_add_and_duplicate_pick_free_names(qapp, model_space):
    tab = MaterialsTab(model_space)
    assert tab.add_material().name == "New Material"
    assert tab.add_material().name == "New Material 2"
    tab.select_name("Brick")
    dup = tab.duplicate_material()
    assert dup.name == "Brick Copy" and dup.fill_type == tab.table().by_name("Brick").fill_type


def test_ok_installs_and_cancel_drops(qapp, model_space):
    d = _dialog(model_space)
    d._mat_tab.select_name("Brick")
    d._mat_tab.set_name("Fired Brick")
    d.reject()
    assert mt.project_table().by_name("Fired Brick") is None
    d = _dialog(model_space)
    d._mat_tab.select_name("Brick")
    d._mat_tab.set_name("Fired Brick")
    d.accept()
    assert mt.project_table().by_name("Fired Brick") is not None


def test_ok_reaches_a_wall_through_the_table(qapp, model_space):
    brick = mt.project_table().by_name("Brick")
    w = _wall(model_space, brick)
    d = _dialog(model_space)
    d._mat_tab.select_name("Brick")
    d._mat_tab.set_fill_type(None)
    assert mt.fill_type_of(w) is not None           # nothing live until OK
    d.accept()
    assert mt.fill_type_of(w) is None
    assert model_space._dirty


def test_a_type_added_in_the_same_dialog_session_is_listed_and_survives_ok(qapp, model_space):
    d = _dialog(model_space)
    added = d._ft_tab.add_type()
    sel = d._mat_tab.section_selector()
    assert sel.findData(added.id) >= 0
    d._mat_tab.select_name("Brick")
    d._mat_tab.set_fill_type(added.id)
    d.accept()
    assert mt.project_table().by_name("Brick").fill_type == added.id
    assert ft.project_table().get(added.id) is not None


def test_a_fill_type_a_pending_material_uses_cannot_be_deleted(qapp, model_space):
    d = _dialog(model_space)
    added = d._ft_tab.add_type()
    d._mat_tab.select_name("Brick")
    d._mat_tab.set_fill_type(added.id)
    d._ft_tab._users.clear()
    d._ft_tab.select_name(ft.project_table().all()[0].name)   # leave, then come back:
    d._ft_tab.select_name(added.name)                          # a re-selected row reloads nothing
    assert not d._ft_tab.delete_button().isEnabled()


def test_reset_and_set_default_are_disabled_on_the_tab(qapp, model_space):
    d = _dialog(model_space)
    d._tabs.setCurrentWidget(d._mat_tab)
    assert not d._reset_btn.isEnabled() and not d._default_btn.isEnabled()
    assert "per-project" in d._reset_btn.toolTip()
    d._tabs.setCurrentIndex(0)
    assert d._reset_btn.isEnabled()


def test_the_tab_sits_right_after_fill_types(qapp, model_space):
    d = _dialog(model_space)
    stack = d._tabs._stack
    assert stack.indexOf(d._mat_tab) == stack.indexOf(d._ft_tab) + 1


def test_opening_the_dialog_and_pressing_ok_dirties_nothing_here(qapp, model_space):
    """The Selector rebuilds in the tab must not fire its own handlers."""
    before = (mt.project_table().to_payload(), model_space._dirty)
    d = _dialog(model_space)
    assert not d._mat_tab.dirty
    d._mat_tab.refresh_fill_types()
    d._mat_tab._fill_defaults()
    d._mat_tab.select_name("Brick")
    assert not d._mat_tab.dirty
    d.accept()
    assert not d._mat_tab.dirty
    assert (mt.project_table().to_payload(), model_space._dirty) == before


def test_a_category_default_picked_in_the_selector_is_installed_on_ok(qapp, model_space):
    d = _dialog(model_space)
    sel = d._mat_tab._default_sel["Wall"]
    sel.setCurrentIndex(sel.findData(d._mat_tab.table().by_name("Brick").id))
    assert d._mat_tab.dirty
    d.accept()
    assert mt.project_table().default_for("Wall") == mt.project_table().by_name("Brick").id


def test_a_material_edit_refreshes_the_fill_types_users_through_the_dialog(qapp, model_space):
    d = _dialog(model_space)
    added = d._ft_tab.add_type()
    d._mat_tab.select_name("Brick")
    d._mat_tab.set_fill_type(added.id)
    d._ft_tab._users.clear()
    d._ft_tab.select_name(ft.project_table().all()[0].name)   # leave, then come back:
    d._ft_tab.select_name(added.name)                          # a re-selected row reloads nothing
    assert d._ft_tab.delete_button().toolTip().startswith("Used by 1")
    d._mat_tab.set_fill_type(None)
    d._ft_tab._users.clear()
    d._ft_tab.select_name(ft.project_table().all()[0].name)   # leave, then come back:
    d._ft_tab.select_name(added.name)                          # a re-selected row reloads nothing
    assert d._ft_tab.delete_button().isEnabled()


def test_the_selector_follows_a_fill_type_edit_made_in_the_same_session(qapp, model_space):
    d = _dialog(model_space)
    added = d._ft_tab.add_type()
    d._ft_tab.set_name("Fancy Hatch")
    sel = d._mat_tab.section_selector()
    assert sel.findText("Fancy Hatch") >= 0 and sel.findData(added.id) >= 0


def test_a_selector_rebuild_keeps_a_hatched_materials_look(qapp, model_space):
    """clear() fires the selector with no data; that must not read as a pick of No hatch."""
    tab = MaterialsTab(model_space)
    tab.select_name("Brick")
    before = tab.current().fill_type
    assert before
    tab.refresh_fill_types()
    assert tab.current().fill_type == before
    assert not tab.dirty


def test_going_back_to_fill_types_shows_a_materials_new_claim(qapp, model_space):
    """A shown dialog, real tab switches: no cache cleared by hand, same row kept."""
    d = _dialog(model_space)
    d.show()
    try:
        d._tabs.setCurrentWidget(d._ft_tab)
        qapp.processEvents()
        added = d._ft_tab.add_type()
        assert d._ft_tab.delete_button().isEnabled()

        d._tabs.setCurrentWidget(d._mat_tab)
        qapp.processEvents()
        d._mat_tab.select_name("Brick")
        d._mat_tab.set_fill_type(added.id)
        d._tabs.setCurrentWidget(d._ft_tab)
        qapp.processEvents()
        assert d._ft_tab.current_type().id == added.id
        assert not d._ft_tab.delete_button().isEnabled()
        assert "material Brick" in d._ft_tab.delete_button().toolTip()

        d._tabs.setCurrentWidget(d._mat_tab)
        qapp.processEvents()
        d._mat_tab.set_fill_type(None)
        d._tabs.setCurrentWidget(d._ft_tab)
        qapp.processEvents()
        assert d._ft_tab.delete_button().isEnabled()
    finally:
        d.close()
