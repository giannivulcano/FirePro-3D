"""Old schematics at open, and the box rows, from the 2026-11-06 smoke on a real project.

A schematic saved before Printed text turns Printed when its project opens (N13). Its text
keeps the size its first viewport printed, then stops following the viewport.
Padding and Corner Radius read printed mm, like Height (N10).
"""
import json

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QLabel

from firepro3d.block_definition import BlockDefinition
from firepro3d.dimension_edit import DimensionEdit
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.paper_export import export_pdf
from firepro3d.paper_space import PaperScene, Sheet, SheetViewData, ViewResolver
from firepro3d.property_manager import PropertyManager
from firepro3d.schematic_scene import SchematicSceneManager
from firepro3d.text_item import TextAnnotationData, TextItem
from tests.test_note_three_click import THIRD, three_clicks
from tests.test_note_three_click import schematic  # noqa: F401
from tests.test_printed_text_pdf import (_VP_X, _VP_Y, _cap_mm, _DetailStub, _editor, _PlanStub,
                                         _sheet)

OLD_VERSION = 11
PROJECT_SCALE = 100.0
BOX = (180.0, 120.0)


def _old_project():
    proj = Model_Space()
    proj.scale_manager.drawing_scale = PROJECT_SCALE
    return proj


def _old_schematic(proj, height=40.0):
    """A schematic as the old build saved it: a drawing with one text, neither key."""
    w, _t = _editor(proj, None, height_mm=height)
    w._add_primitive(LineItem(QPointF(-200, -200), QPointF(4000, 2000)))
    return w.commit_block("Riser", "", "")


def _line_schematic(proj):
    d = BlockDefinition.new(name="Lines", library="", series="", origin=(0.0, 0.0),
                            primitives=[LineItem(QPointF(0, 0), QPointF(900, 400)).to_dict()],
                            kind="schematic")
    proj.register_block_definition(d)
    return d


def _save_as_version(proj, path, version=OLD_VERSION):
    """Save through the real writer, then stamp the file as an older build's."""
    proj.save_to_file(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = version
    path.write_text(json.dumps(payload), encoding="utf-8")


def _reopened(path):
    proj = Model_Space()
    assert proj.load_from_file(str(path))
    return proj


def _cap_of(tmp_path, proj, sheet, data, name):
    """The printed cap height of *sheet*'s viewport, through a real PDF export."""
    mgr = SchematicSceneManager(proj)
    res = ViewResolver(proj, _PlanStub(), _DetailStub(), None, schematic_scenes=mgr)
    PaperScene(sheet, res)
    path = tmp_path / name
    export_pdf([sheet], res, str(path))
    return _cap_mm(path, data)


@pytest.mark.parametrize("scale", [0.0, 0.05], ids=["NTS", "1:20"])
def test_g3_a_reopened_old_file_prints_its_text_at_todays_size(qapp, tmp_path, scale):
    proj = _old_project()
    defn = _old_schematic(proj)
    sheet, _res, _mgr, data = _sheet(proj, defn, scale, BOX)
    today = _cap_of(tmp_path, proj, sheet, data, "today.pdf")
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)

    again = _reopened(path)
    d2 = again.get_block_definition(defn.id)
    assert d2.text_sizing == "printed"
    s2 = again._sheets[0]
    assert _cap_of(tmp_path, again, s2, s2.sheet_views[0], "after.pdf") == pytest.approx(
        today, rel=0.01)


def test_g3_after_the_migration_the_text_ignores_the_viewport_size(qapp, tmp_path):
    proj = _old_project()
    defn = _old_schematic(proj)
    sheet, _res, _mgr, data = _sheet(proj, defn, 0.0, BOX)
    today = _cap_of(tmp_path, proj, sheet, data, "today.pdf")
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)

    again = _reopened(path)
    s2 = again._sheets[0]
    vp = s2.sheet_views[0]
    vp.w, vp.h = vp.w / 2.0, vp.h / 2.0
    assert _cap_of(tmp_path, again, s2, vp, "half.pdf") == pytest.approx(today, rel=0.01)


def test_a_true_scale_viewport_gives_its_own_scale(qapp, tmp_path):
    proj = _old_project()
    defn = _old_schematic(proj)
    _sheet(proj, defn, 0.05, BOX)
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)
    assert _reopened(path).get_block_definition(defn.id).text_scale == pytest.approx(20.0)


def test_the_first_viewport_wins_on_two_sheets(qapp, tmp_path):
    proj = _old_project()
    defn = _old_schematic(proj)
    first = Sheet.create_default()
    second = Sheet.create_default()
    for sheet, scale in ((first, 0.05), (second, 0.02)):
        sheet.sheet_views.append(SheetViewData("schematic", defn.id, "", scale, _VP_X, _VP_Y,
                                               BOX[0], BOX[1]))
    proj._sheets = [first, second]
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)
    assert _reopened(path).get_block_definition(defn.id).text_scale == pytest.approx(20.0)


def test_a_schematic_with_no_text_takes_its_viewport_scale_too(qapp, tmp_path):
    """Smoke: Standpipe, empty, took the project's 1:100 on a 1:10 viewport, so a Note drew
    ten times too large against the drawing in the editor."""
    proj = _old_project()
    defn = _line_schematic(proj)
    _sheet(proj, defn, 0.1, BOX)
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)
    d2 = _reopened(path).get_block_definition(defn.id)
    assert (d2.text_sizing, d2.text_scale) == ("printed", pytest.approx(10.0))


def test_a_schematic_with_no_text_takes_its_nts_fit(qapp, tmp_path):
    """Standpipe's own case. The 900 x 400 line pads 2% of 900 per side: 936 x 436 fits
    180 x 120 by width, so S = 180 / 936 and N = 5.2."""
    proj = _old_project()
    defn = _line_schematic(proj)
    _sheet(proj, defn, 0.0, BOX)
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)
    d2 = _reopened(path).get_block_definition(defn.id)
    assert (d2.text_sizing, d2.text_scale) == ("printed", pytest.approx(5.2, abs=0.01))


def test_a_textless_schematic_on_no_sheet_takes_the_project_scale(qapp, tmp_path):
    proj = _old_project()
    defn = _line_schematic(proj)
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)
    d2 = _reopened(path).get_block_definition(defn.id)
    assert (d2.text_sizing, d2.text_scale) == ("printed", PROJECT_SCALE)


def test_a_schematic_on_no_sheet_takes_the_project_scale(qapp, tmp_path):
    proj = _old_project()
    defn = _old_schematic(proj)
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)
    d2 = _reopened(path).get_block_definition(defn.id)
    assert (d2.text_sizing, d2.text_scale) == ("printed", PROJECT_SCALE)


def test_the_stored_text_does_not_change(qapp, tmp_path):
    """The editor looks the same: only the two definition keys are new."""
    proj = _old_project()
    defn = _old_schematic(proj)
    _sheet(proj, defn, 0.0, BOX)
    before = json.loads(json.dumps(defn.primitives))
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)
    assert _reopened(path).get_block_definition(defn.id).primitives == before


def test_real_size_chosen_and_saved_stays_real_size(qapp, tmp_path):
    """A file at the current version is never migrated: the row's choice holds."""
    proj = _old_project()
    defn = _old_schematic(proj)
    _sheet(proj, defn, 0.0, BOX)
    path = tmp_path / "now.fpd"
    proj.save_to_file(str(path))
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == Model_Space.SAVE_VERSION
    d2 = _reopened(path).get_block_definition(defn.id)
    assert d2.text_sizing is None and d2.text_scale is None


def test_a_migrated_schematic_saves_at_the_new_version_with_its_keys(qapp, tmp_path):
    proj = _old_project()
    defn = _old_schematic(proj)
    _sheet(proj, defn, 0.05, BOX)
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)
    out = tmp_path / "saved.fpd"
    _reopened(path).save_to_file(str(out))
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["version"] == Model_Space.SAVE_VERSION
    rec = payload["block_definitions"][defn.id]
    assert (rec["text_sizing"], rec["text_scale"]) == ("printed", pytest.approx(20.0))


def test_opening_leaves_no_listener_behind(qapp, tmp_path):
    """The migration's scenes are its own: nothing stays attached to the project."""
    proj = _old_project()
    defn = _old_schematic(proj)
    _sheet(proj, defn, 0.0, BOX)
    old, now = tmp_path / "old.fpd", tmp_path / "now.fpd"
    _save_as_version(proj, old)
    proj.save_to_file(str(now))
    migrated, plain = _reopened(old), _reopened(now)
    assert (migrated.receivers(migrated.blockDefinitionsChanged)
            == plain.receivers(plain.blockDefinitionsChanged))


# -- N10: the box rows read printed mm -----------------------------------------------------

def _rows_before_and_after(schematic_fixture):
    w, view, scene, _proj = schematic_fixture
    scene.set_mode("note")
    armed = scene._note_ctl.template.get_properties()
    three_clicks(view, scene, third=THIRD["L"])
    return armed, scene._texts[-1]


def _shown(row):
    return row["formatter"](row["value_mm"])


def _row(pm, label):
    form = pm._form
    for i in range(form.rowCount()):
        lbl = form.itemAt(i, form.ItemRole.LabelRole)
        fld = form.itemAt(i, form.ItemRole.FieldRole)
        if lbl and isinstance(lbl.widget(), QLabel) and lbl.widget().text() == label and fld:
            return fld.widget()
    raise AssertionError(label)


@pytest.mark.parametrize("key", ["Height", "Padding", "Corner Radius"])
def test_an_armed_note_row_reads_the_same_once_placed(schematic, key):
    """Smoke: 1 before placement became 20 after it, at this fixture's 1:20."""
    armed, item = _rows_before_and_after(schematic)
    assert _shown(armed[key]) == _shown(item.get_properties()[key])


@pytest.mark.parametrize("key, field", [("Padding", "cell_padding_mm"),
                                        ("Corner Radius", "border_corner_radius_mm")])
def test_a_box_row_shows_and_commits_printed_mm_through_the_panel(qapp, key, field):
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    _w, t = _editor(proj, "printed", height_mm=60.0, cell_padding_mm=40.0,
                    border_corner_radius_mm=40.0)
    pm = PropertyManager()
    pm.show_properties(t)
    edit = _row(pm, key)
    assert isinstance(edit, DimensionEdit)
    assert edit.text() == "2.00 mm"
    edit.setText("3mm")
    edit.editingFinished.emit()
    assert getattr(t.data, field) == pytest.approx(60.0)


@pytest.mark.parametrize("key, field", [("Padding", "cell_padding_mm"),
                                        ("Corner Radius", "border_corner_radius_mm")])
def test_a_box_row_goes_to_zero_and_refuses_a_negative(qapp, key, field):
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    _w, t = _editor(proj, "printed", height_mm=60.0, cell_padding_mm=40.0,
                    border_corner_radius_mm=40.0)
    pm = PropertyManager()
    pm.show_properties(t)
    edit = _row(pm, key)
    edit.setText("-1")
    edit.editingFinished.emit()
    assert getattr(t.data, field) == pytest.approx(40.0)
    edit.setText("0")
    edit.editingFinished.emit()
    assert getattr(t.data, field) == 0.0


def _two_texts(key_field):
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    w, a = _editor(proj, "printed", height_mm=60.0, **{key_field: 40.0})
    b = TextItem(TextAnnotationData(text="J", font_family="Arial", height_mm=60.0,
                                    **{key_field: 100.0}))
    w._add_primitive(b)
    return w, a, b


@pytest.mark.parametrize("key, field", [("Padding", "cell_padding_mm"),
                                        ("Corner Radius", "border_corner_radius_mm"),
                                        ("Height", "height_mm")])
def test_tabbing_through_a_mixed_row_writes_nothing(qapp, key, field):
    """Both differ on *field* (Height: the other two rows stay equal, so make it differ)."""
    _w, a, b = _two_texts("cell_padding_mm" if field == "height_mm" else field)
    if field == "height_mm":
        b.data.height_mm = 120.0
    want = getattr(a.data, field), getattr(b.data, field)
    pm = PropertyManager()
    pm.show_properties([a, b])
    edit = _row(pm, key)
    assert edit.text() == ""
    edit.editingFinished.emit()
    assert (getattr(a.data, field), getattr(b.data, field)) == want
    assert edit.text() == ""                            # still shows < mixed >


def test_typing_the_first_targets_value_into_a_mixed_row_commits_to_all(qapp):
    _w, a, b = _two_texts("cell_padding_mm")
    pm = PropertyManager()
    pm.show_properties([a, b])
    edit = _row(pm, "Padding")
    edit.setText("2.00 mm")                             # a's value: not an untouched field
    edit.editingFinished.emit()
    assert (a.data.cell_padding_mm, b.data.cell_padding_mm) == pytest.approx((40.0, 40.0))


def test_an_untouched_row_writes_nothing_on_a_single_target(qapp):
    proj = Model_Space()
    proj.scale_manager.drawing_scale = 20.0
    _w, t = _editor(proj, "printed", height_mm=60.0)
    seen = []
    pm = PropertyManager()
    pm.show_properties(t)
    t.set_property = lambda k, v: seen.append(k)        # instance shadow: the panel calls it by name
    _row(pm, "Height").editingFinished.emit()
    assert seen == []


def test_a_schematic_that_cannot_build_does_not_stop_the_open(qapp, tmp_path, monkeypatch):
    proj = _old_project()
    defn = _old_schematic(proj)
    _sheet(proj, defn, 0.0, BOX)
    path = tmp_path / "old.fpd"
    _save_as_version(proj, path)

    def boom(self, block_id):
        raise ValueError("bad primitive")

    monkeypatch.setattr(SchematicSceneManager, "scene_for", boom)
    again = _reopened(path)
    d2 = again.get_block_definition(defn.id)
    assert (d2.text_sizing, d2.text_scale) == ("printed", PROJECT_SCALE)


def test_a_bare_focus_out_keeps_a_small_padding(qapp):
    """A migrated label's padding can be under one printed mm: the row keeps its decimals, and
    leaving it unchanged writes nothing new."""
    proj = _old_project()
    w, t = _editor(proj, "printed", height_mm=60.0, cell_padding_mm=1.0)
    pm = PropertyManager()
    pm.show_properties(t)
    _row(pm, "Padding").editingFinished.emit()
    assert t.data.cell_padding_mm == pytest.approx(1.0)
