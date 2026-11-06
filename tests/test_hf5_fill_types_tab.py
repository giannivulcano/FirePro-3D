"""HF5 Task 8 -- Fill Types tab (layout B) + restyle propagation + delete guard."""
import os
import shutil

import pytest
from PyQt6.QtCore import QPointF, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog

from firepro3d import colour_picker
from firepro3d import display_manager as dm
from firepro3d import fill_types as ft
from firepro3d import hatch_patterns as hp
from firepro3d import materials as mt
from firepro3d.block_definition import BlockDefinition
from firepro3d.constants import TOKEN_ACCENT, TOKEN_AUTO, TOKEN_ELEMENT
from firepro3d.fill_layers import BackgroundLayer, FillLayers, PatternLayer
from firepro3d.geometry_2d import LineItem
from firepro3d.hatch_patterns import LEGACY_ALIAS
from firepro3d.render_op import PATTERN


def _own_material(name="Own Mat", colour="#334455"):
    """A material on its own Fill Type (the shared tables carry whatever earlier
    tests left, so these tests never lean on a starter by name and the names
    carry a fresh suffix)."""
    name = f"{name} {ft.new_id()[:6]}"
    t = ft.project_table().add(ft.FillType(ft.new_id(), name + " Look",
                                           FillLayers(BackgroundLayer(colour, 1.0))))
    return mt.project_table().add(mt.Material(ft.new_id(), name, t.id))


def _open(model_space):
    d = dm.DisplayManager(model_space)
    tab = next(d._tabs.widget(i) for i in range(d._tabs.count())
               if d._tabs.tabText(i) == "Fill Types")
    return d, tab


def _names(sel):
    return [sel.itemText(i) for i in range(sel.count())]


def _wall(ms):
    from firepro3d.wall import WallSegment
    w = WallSegment(QPointF(0, 0), QPointF(2000, 0))
    ms._walls.append(w)
    ms.addItem(w)
    return w


def _tile(name="Zig"):
    return BlockDefinition.new(
        name=name, library="L", series="S", origin=(0.0, 0.0),
        primitives=[LineItem(QPointF(0, 0), QPointF(5, -5)).to_dict()],
        tile={"w": 5.0, "h": 5.0, "row_shift": 0.0, "size": "model"})


# -- layout / apply-on-OK ---------------------------------------------------

def test_tab_sits_after_line_weights(qapp, model_space):
    d, _tab = _open(model_space)
    try:
        names = [d._tabs.tabText(i) for i in range(d._tabs.count())]
        assert names.index("Fill Types") == names.index("Line Weights") + 1
    finally:
        d.close()


def test_add_rename_restyle_apply_on_ok_only(qapp, model_space):
    d, tab = _open(model_space)
    tab.add_type()
    assert tab.set_name("Concrete")
    tab.set_background(True, "#00ff00", 1.0)
    assert ft.project_table().by_name("Concrete") is None        # not before OK
    hits = []
    ft.fill_type_bus().changed.connect(lambda: hits.append(1))
    model_space._dirty = False
    d.accept()
    got = ft.project_table().by_name("Concrete")
    assert got.layers.background.color == "#00ff00" and hits
    assert model_space._dirty                                    # outside undo, dirties


def test_tab_ok_is_outside_undo(qapp, model_space):
    """VC9 M5 (AC1 undo half): OK on a tab edit pushes no undo state, and an Undo
    afterwards leaves the table (and the unrelated earlier state) alone."""
    model_space.push_undo_state()                    # something a later Undo could step back to
    model_space.push_undo_state()
    assert model_space.can_undo()
    pos, depth = model_space._undo_pos, len(model_space._undo_stack)
    d, tab = _open(model_space)
    tab.add_type()
    assert tab.set_name("Concrete")
    tab.set_background(True, "#00ff00", 1.0)
    d.accept()
    assert (model_space._undo_pos, len(model_space._undo_stack)) == (pos, depth)
    model_space.undo()
    got = ft.project_table().by_name("Concrete")
    assert got is not None and got.layers.background.color == "#00ff00"


def test_cancel_discards(qapp, model_space):
    d, tab = _open(model_space)
    tab.add_type()
    tab.set_name("Temp")
    d.reject()
    assert ft.project_table().by_name("Temp") is None


def test_ok_without_a_tab_edit_leaves_the_project_clean(qapp, model_space):
    d, tab = _open(model_space)
    assert not tab.dirty
    model_space._dirty = False
    d.accept()
    assert not model_space._dirty


def test_rename_to_existing_name_refused(qapp, model_space):
    d, tab = _open(model_space)
    try:
        tab.select_name("Solid Black")
        assert tab.set_name("Solid Grey 20%") is False
        assert tab.current_type().name == "Solid Black"
        assert tab._name.text() == "Solid Black"             # the field snaps back
        assert "already exists" in tab._status.text()
    finally:
        d.close()


@pytest.mark.parametrize("bad", [
    pytest.param("(Custom)", id="custom"), pytest.param("(custom)", id="custom-lower"),
    pytest.param("? 1234abcd", id="missing-label"), pytest.param("?  x", id="question-prefix"),
    pytest.param("  ", id="blank")])
def test_reserved_names_refused(qapp, model_space, bad):
    """The region panel would shadow "(Custom)" / mis-pick a "? " label (Group B carry-in)."""
    d, tab = _open(model_space)
    try:
        tab.select_name("Solid Black")
        assert tab.set_name(bad) is False
        assert tab.current_type().name == "Solid Black"
    finally:
        d.close()


def test_a_rename_keeps_the_id_and_the_users(qapp, model_space):
    d, tab = _open(model_space)
    tab.select_name("Solid Black")
    tid = tab.current_type().id
    assert tab.set_name("Black") and tab.current_type().id == tid
    d.accept()
    assert ft.project_table().get(tid).name == "Black"


# -- delete guard (AC8) -------------------------------------------------------

def test_delete_refused_while_used(qapp, model_space):
    ws = ft.project_table().add(ft.FillType("t-hf5-del", "Hf5 Used Type",
                                            FillLayers(BackgroundLayer("#123456", 1.0))))
    mt.project_table().add(mt.Material("m-hf5-del", "Hf5 Delete Guard", ws.id))
    try:
        d, tab = _open(model_space)
        tab.select_name("Hf5 Used Type")
        assert not tab.delete_button().isEnabled()
        assert "Used by 1" in tab.delete_button().toolTip()
        tab.select_name("Solid Black")
        assert tab.delete_button().isEnabled()
    finally:
        mt.reset_project_table()
    tab.delete_button().click()
    d.accept()
    assert ft.project_table().by_name("Solid Black") is None
    assert ft.project_table().by_name("Hf5 Used Type") is not None


def test_type_users_counts_regions_blocks_and_materials(qapp, model_space):
    from firepro3d.filled_region import FilledRegionItem
    t = ft.project_table().ensure_named("Concrete", FillLayers(BackgroundLayer("#00ff00", 1.0)))
    a, b, c, e = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    region = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, e), LineItem(e, a)]])
    region.set_fill_type(t.id)
    model_space.addItem(region)
    mt.project_table().add(mt.Material("m-hf5-users", "Hf5 Users Material", t.id))
    rec = region.to_dict()
    model_space.commit_block_definition(block_id=None, name="Host", library="L", series="S",
                                        primitives=[rec], origin=(0.0, 0.0), place_instance=False)
    try:
        users = ft.type_users(t.id, model_space)
        assert "block Host" in users and "1 region(s)" in users
        assert "material Hf5 Users Material" in users
        assert ft.type_users("nobody", model_space) == []
    finally:
        mt.reset_project_table()


def test_type_users_follows_a_duplicate_alias(qapp, model_space):
    """A record that kept a load-time duplicate's id counts for the kept type."""
    table = ft.FillTypeTable.from_payload([
        {"id": "keep", "name": "Concrete"}, {"id": "dupe", "name": "concrete"}])
    ft.set_project_table(table)
    rec = {"type": "filled_region", "fill_type": "dupe"}
    model_space.register_block_definition(BlockDefinition.new(
        name="H", library="L", series="S", origin=(0.0, 0.0), primitives=[rec]))
    assert ft.type_users("keep", model_space) == ["block H"]


# -- picker guards (re-created from the retired DM section dialog) -----------

@pytest.fixture
def picker_spy(monkeypatch):
    """Stub the modal: record what the real dialog offers, then cancel."""
    seen = []

    def exec_(self):
        seen.append({"theme": [c.value for c in self._theme_row_chips],
                     "standard": [c.value for c in self._standard_row_chips]})
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(colour_picker.ColourPickerDialog, "exec", exec_)
    return seen


@pytest.mark.parametrize("which", ["_bg_swatch", "_pat_swatch"])
def test_tab_colour_pickers_show_theme_and_no_fill(qapp, model_space, picker_spy, which):
    d, tab = _open(model_space)
    try:
        tab.select_name("Solid Black")
        tab.set_pattern(True, hp.DEFAULT_TILE_REF, "#112233", 1.0, 1.0)
        getattr(tab, which)._pick()
    finally:
        d.close()
    assert len(picker_spy) == 1
    assert picker_spy[0]["theme"] == [TOKEN_AUTO, TOKEN_ACCENT]
    assert picker_spy[0]["standard"][-1] == "", "No Fill chip ends the Standard row"


def test_tab_background_theme_token_and_no_fill_apply(qapp, model_space, monkeypatch):
    d, tab = _open(model_space)
    try:
        tab.select_name("Solid Black")
        monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: TOKEN_ACCENT)
        tab._bg_swatch._pick()
        assert tab.current_type().layers.background.color == TOKEN_ACCENT
        monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "")
        tab._bg_swatch._pick()                                   # No Fill = background off
        assert tab.current_type().layers.background is None
        assert not tab._bg_on.isChecked()
    finally:
        d.close()


def test_tab_pattern_colour_refuses_no_fill(qapp, model_space, monkeypatch):
    d, tab = _open(model_space)
    try:
        tab.select_name("Solid Black")
        tab.set_pattern(True, hp.DEFAULT_TILE_REF, "#112233", 1.0, 1.0)
        monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "")
        tab._pat_swatch._pick()
        assert tab.current_type().layers.pattern.color == "#112233"   # never vanishes
        assert "needs a colour" in tab._status.text()
    finally:
        d.close()


def _put_shipped_into(folder):
    os.makedirs(str(folder), exist_ok=True)
    for _bid, src in hp.shipped_pattern_files():
        shutil.copyfile(src, os.path.join(str(folder), os.path.basename(src)))


def test_tab_pattern_list_offers_project_tiles_and_folder_patterns(qapp, model_space):
    from firepro3d import app_data
    _put_shipped_into(app_data.hatch_patterns_dir())
    z = _tile("Zig")
    model_space.register_block_definition(z)
    d, tab = _open(model_space)
    try:
        tab.select_name("Solid Black")
        tab.set_pattern(True, hp.DEFAULT_TILE_REF, "#112233", 1.0, 1.0)
        labels = _names(tab._pat_sel)
        assert "Zig" in labels                                   # a project tile
        assert tab._pat_sel.currentData() == LEGACY_ALIAS["diagonal"]   # legacy name -> id
        assert len(labels) > 1                                   # + the folder's patterns
        tab._pat_sel.setCurrentIndex(labels.index("Zig"))
        assert tab.current_type().layers.pattern.ref == z.id
    finally:
        d.close()


def test_tab_keeps_an_unresolvable_pattern_ref(qapp, model_space):
    """A stored ref that no longer resolves stays (D-A36): visible, kept through a
    colour edit and through OK; only an explicit pick replaces it."""
    from firepro3d import app_data
    _put_shipped_into(app_data.hatch_patterns_dir())
    ft.project_table().add(ft.FillType("gone", "Gone", FillLayers(
        None, PatternLayer("deleted-project-tile-uuid", "#112233", 1.0, 1.0))))
    d, tab = _open(model_space)
    tab.select_name("Gone")
    assert tab._pat_sel.currentText() == hp.MISSING_PATTERN_LABEL
    assert tab._pat_sel.currentData() == "deleted-project-tile-uuid"
    tab._pat_swatch.colorChanged.emit("#445566")                 # colour-only edit
    assert tab.current_type().layers.pattern.ref == "deleted-project-tile-uuid"
    d.accept()
    assert ft.project_table().by_name("Gone").layers.pattern.ref == "deleted-project-tile-uuid"


def test_a_folder_pattern_picked_in_the_tab_loads_on_ok(qapp, model_space):
    from firepro3d import app_data
    _put_shipped_into(app_data.hatch_patterns_dir())
    d, tab = _open(model_space)
    tab.select_name("Solid Black")
    ref = LEGACY_ALIAS["diagonal"]
    tab.set_pattern(True, ref, "#000000", 1.0, 1.0)
    assert ref not in model_space.block_registry.ids()
    d.accept()
    assert ref in model_space.block_registry.ids()


def test_by_element_toggle_stores_the_token_and_disables_the_swatch(qapp, model_space):
    d, tab = _open(model_space)
    try:
        tab.select_name("Solid Black")
        tab.set_pattern(True, hp.DEFAULT_TILE_REF, "#112233", 1.0, 1.0)
        tab._pat_elem.setChecked(True)
        assert tab.current_type().layers.pattern.color == TOKEN_ELEMENT
        assert not tab._pat_swatch.isEnabled()
        tab._pat_elem.setChecked(False)
        assert tab.current_type().layers.pattern.color == "#112233"
    finally:
        d.close()


def test_a_non_tab_edit_keeps_an_exact_scale_and_opacity(qapp, model_space):
    """The scale Stepper is whole percent: untouched, 1.337 must not be rounded."""
    d, tab = _open(model_space)
    try:
        tab.select_name("Solid Black")
        tab.set_pattern(True, hp.DEFAULT_TILE_REF, "#112233", 1.337, 0.333)
        tab._pat_swatch.colorChanged.emit("#445566")
        lay = tab.current_type().layers.pattern
        assert lay.scale == 1.337 and lay.opacity == 0.333 and lay.color == "#445566"
        tab._pat_elem.setChecked(True)                          # the widget path (_on_pat)
        lay = tab.current_type().layers.pattern
        assert lay.color == TOKEN_ELEMENT and lay.scale == 1.337 and lay.opacity == 0.333
        tab._pat_scale.setValue(250)
        assert tab.current_type().layers.pattern.scale == 2.5
    finally:
        d.close()


# -- a pending type reaches a wall through a material (M5, M16) ---------------------

def test_a_type_added_in_the_tab_is_pickable_before_ok_and_applies_on_ok(qapp, model_space):
    from firepro3d.wall import WallSegment
    mat = _own_material()
    wall = _wall(model_space)
    wall.material_id = mat.id
    d, tab = _open(model_space)
    tab.add_type()
    tab.set_name("Pending Look")
    tab.set_background(True, "#00ff00", 1.0)
    pending = tab.current_type().id
    assert d._mat_tab.section_selector().findData(pending) >= 0
    d._mat_tab.select_name(mat.name)
    d._mat_tab.set_fill_type(pending)
    d.accept()
    t = ft.project_table().by_name("Pending Look")
    assert t is not None and t.id == pending           # the tab's type, not a stray preview copy
    assert t.layers.background.color == "#00ff00"
    assert mt.fill_type_of(wall) == pending


def test_a_type_renamed_in_the_tab_follows_its_material(qapp, model_space):
    wall = _wall(model_space)
    wall.material_id = _own_material().id
    tid = mt.fill_type_of(wall)
    d, tab = _open(model_space)
    tab.select_name(ft.project_table().get(tid).name)
    tab.set_name("Brick Cut")
    d.accept()
    assert ft.project_table().get(tid).name == "Brick Cut"
    assert mt.fill_type_of(wall) == tid                           # by id: the rename follows


def test_cancel_drops_a_pending_type_and_leaves_the_cut_alone(qapp, model_space):
    mat = _own_material()
    wall = _wall(model_space)
    wall.material_id = mat.id
    before = mt.fill_type_of(wall)
    d, tab = _open(model_space)
    tab.add_type()
    tab.set_name("Pending Look")
    d._mat_tab.select_name(mat.name)
    d._mat_tab.set_fill_type(tab.current_type().id)
    d.reject()
    assert ft.project_table().by_name("Pending Look") is None
    assert mt.fill_type_of(wall) == before                        # nothing live moved, so nothing to restore


# -- MainWindow: restyle propagation (R5, AC2) -----------------------------------

@pytest.fixture
def mw_fn(qapp, tmp_path, monkeypatch):
    """A real MainWindow per test: the fill-type bus is reset per test (conftest),
    and MainWindow connects to the bus in its constructor."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d import theme as th
    from firepro3d.view_3d import View3D
    from tests._mainwindow_helpers import dispose_main_window
    main_mod.View3D = View3D
    prev_qss, prev_font = qapp.styleSheet(), qapp.font()
    th.apply_app_font(qapp)
    qapp.setStyleSheet(th.build_app_qss(th.detect()))
    w = main_mod.MainWindow()
    w.resize(1200, 800)
    w.show()
    QTest.qWaitForWindowExposed(w)
    QTest.qWait(100)
    yield w
    dispose_main_window(w)
    qapp.setStyleSheet(prev_qss)
    qapp.setFont(prev_font)


def _region_rec(type_id):
    from firepro3d.filled_region import FilledRegionItem
    a, b, c, e = QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)
    r = FilledRegionItem.from_pieces([[LineItem(a, b), LineItem(b, c), LineItem(c, e), LineItem(e, a)]])
    r.set_fill_type(type_id)
    return r.to_dict()


def test_retarget_recompiles_a_definition_that_inherits_the_pattern(qapp, mw_fn, shipped_hatches):
    """Group B carry-in: table-only retarget hits recompile typed definitions."""
    ms = mw_fn.scene
    shipped_hatches(ms)
    old = LEGACY_ALIAS["diagonal"]
    new = ms.duplicate_block_definition(old).id
    t = ft.project_table().ensure_named("Hatched", FillLayers(None, PatternLayer(old, "#000000", 1.0, 1.0)))
    d = ms.commit_block_definition(block_id=None, name="Host", library="L", series="S",
                                   primitives=[_region_rec(t.id)], origin=(0.0, 0.0),
                                   place_instance=False)
    tiles = lambda: {o.tile_ref for o in ms._block_definitions[d.id].render_ops() if o.kind == PATTERN}
    assert tiles() == {old}
    assert ms.retarget_block_refs(old, new) >= 1
    assert tiles() == {new}                       # no manual invalidate_cache()


def _count_paints(monkeypatch, item):
    from firepro3d.wall import WallSegment
    calls = []
    real = WallSegment.paint

    def paint(self, *a, **k):
        if self is item:
            calls.append(1)
        return real(self, *a, **k)
    monkeypatch.setattr(WallSegment, "paint", paint)
    return calls


def _show_wall(mw, wall):
    from tests.test_constraint_pick_ribbon import _plan_index
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    mw.view.centerOn(wall)
    QTest.qWait(150)


def test_retarget_repaints_open_cuts(qapp, mw_fn, shipped_hatches, monkeypatch):
    """Fix-round m1: 0091b114 dropped the display re-apply from the retarget; the
    bus handler repaints cut walls now."""
    ms = mw_fn.scene
    shipped_hatches(ms)
    old = LEGACY_ALIAS["diagonal"]
    new = ms.duplicate_block_definition(old).id
    t = ft.project_table().ensure_named("Hatched", FillLayers(None, PatternLayer(old, "#000000", 1.0, 1.0)))
    wall = _wall(ms)
    wall._is_section_cut = True
    wall.material_id = mt.project_table().add(mt.Material(ft.new_id(), "Hatched", t.id)).id
    _show_wall(mw_fn, wall)
    calls = _count_paints(monkeypatch, wall)
    QTest.qWait(100)
    calls.clear()
    assert ms.retarget_block_refs(old, new) >= 1
    QTest.qWait(200)
    assert calls, "the cut wall was not repainted after the retarget re-pointed its type"


def test_a_table_change_repaints_cut_walls(qapp, mw_fn, monkeypatch):
    ms = mw_fn.scene
    t = ft.project_table().ensure_named("Concrete", FillLayers(BackgroundLayer("#00ff00", 1.0)))
    wall = _wall(ms)
    wall._is_section_cut = True
    wall.material_id = mt.project_table().add(mt.Material(ft.new_id(), "Concrete Green", t.id)).id
    _show_wall(mw_fn, wall)
    calls = _count_paints(monkeypatch, wall)
    QTest.qWait(100)
    calls.clear()
    ft.project_table().replace(ft.FillType(t.id, t.name, FillLayers(BackgroundLayer("#0000ff", 1.0))))
    ft.notify_changed()
    QTest.qWait(200)
    assert calls


def test_the_handler_is_not_reentrant(qapp, mw_fn):
    """A recompile that itself notifies must not recurse."""
    depth = []
    real = mw_fn._live_scenes

    def spy():
        depth.append(1)
        if len(depth) == 1:
            ft.notify_changed()          # re-entry while the handler runs
        return real()
    mw_fn._live_scenes = spy
    ft.notify_changed()
    assert depth == [1]


# -- Group D review fixes ------------------------------------------------------

def _digest(ms, wall):
    import hashlib
    from tests.test_hf5_section_types import _render
    return hashlib.sha256(",".join(c.name() for c in _render(ms, wall)).encode()).hexdigest()


@pytest.mark.parametrize("pending", [False, True], ids=["existing-type", "pending-type"])
def test_cancel_after_a_material_edit_leaves_the_wall_cut(qapp, model_space, shipped_hatches, pending):
    """F1 (M5): a Cancel after a material points at another or a pending type
    renders the same cut; the material edit never reached the live table."""
    shipped_hatches(model_space)
    ft.project_table().ensure_named("Green", FillLayers(BackgroundLayer("#00aa00", 1.0)))
    mat = _own_material()
    wall = _wall(model_space)
    wall._is_section_cut = True
    wall.material_id = mat.id
    pre = _digest(model_space, wall)
    before = (mt.fill_type_of(wall), dict(wall._display_overrides))
    d, tab = _open(model_space)
    if pending:
        tab.add_type()
        tab.set_name("Pending Look")
        tab.set_background(True, "#ff0000", 1.0)
        target = tab.current_type().id
    else:
        target = ft.project_table().by_name("Green").id
    d._mat_tab.select_name(mat.name)
    d._mat_tab.set_fill_type(target)
    d.reject()
    assert (mt.fill_type_of(wall), dict(wall._display_overrides)) == before
    assert _digest(model_space, wall) == pre


def test_cancel_after_a_material_edit_leaves_a_floor_too(qapp, model_space):
    from firepro3d.floor_slab import FloorSlab
    ft.project_table().ensure_named("Green", FillLayers(BackgroundLayer("#00aa00", 1.0)))
    slab = FloorSlab([QPointF(0, 0), QPointF(1000, 0), QPointF(1000, 1000), QPointF(0, 1000)])
    model_space._floor_slabs.append(slab)
    model_space.addItem(slab)
    mat = _own_material()
    slab.material_id = mat.id
    before = (mt.fill_type_of(slab), dict(slab._display_overrides))
    d, _tab = _open(model_space)
    d._mat_tab.select_name(mat.name)
    d._mat_tab.set_fill_type(ft.project_table().by_name("Green").id)
    d.reject()
    assert (mt.fill_type_of(slab), dict(slab._display_overrides)) == before


def test_reset_all_and_set_as_default_are_disabled_on_the_fill_types_tab(qapp, model_space):
    """F3: the table is per project, so neither button applies there."""
    d, tab = _open(model_space)
    try:
        assert d._reset_btn.isEnabled() and d._default_btn.isEnabled()
        d._tabs.setCurrentWidget(tab)
        assert not d._reset_btn.isEnabled() and not d._default_btn.isEnabled()
        assert "per-project" in d._reset_btn.toolTip() and "per-project" in d._default_btn.toolTip()
        d._tabs.setCurrentIndex(0)
        assert d._reset_btn.isEnabled() and d._default_btn.isEnabled()
        assert "per-project" not in d._default_btn.toolTip()
    finally:
        d.close()
