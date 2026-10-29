"""SB3 -- annotation_defaults: eligibility, the project-registry resolver (Task 3),
the .fpd / template round trip (AC3, Task 8), the fallback chain + notice,
the Annotation / Marks panes (AC9 pane level, Task 9)."""
import json

import pytest
from PyQt6.QtCore import QPointF

from firepro3d.block_attributes import normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.bound_label import eligible_definition
from firepro3d.end_render import SCREEN_FIXED
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.room import Room
from firepro3d.system_blocks import ANNOTATION_CATEGORIES, SYSTEM_DEFAULTS

TAG_MM = 3.0


@pytest.fixture(autouse=True)
def sys_defaults():
    """Empty ``SYSTEM_DEFAULTS`` for every test here (the dict is shared by every
    module-level binding); the returned setter installs a mapping. Restored after."""
    saved = dict(SYSTEM_DEFAULTS)
    SYSTEM_DEFAULTS.clear()

    def _set(mapping):
        SYSTEM_DEFAULTS.clear()
        SYSTEM_DEFAULTS.update(mapping)
    yield _set
    SYSTEM_DEFAULTS.clear()
    SYSTEM_DEFAULTS.update(saved)


def _tag_def(ms, name="TestTag", height=TAG_MM):
    d = BlockDefinition.new(name=name, library="", series="", origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "@[Name]", "x": 0.0,
                                         "y": 0.0, "height_mm": height}])
    d.scale_mode = "annotative"
    d.host_category = "Room"
    d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "Name"})]
    ms.register_block_definition(d)
    ms.annotation_defaults["Room"] = d.id
    return d


def _add_room(ms, name, x0=0.0, y0=0.0, w=2000.0, h=2000.0):
    r = Room(boundary=[QPointF(x0, y0), QPointF(x0 + w, y0),
                       QPointF(x0 + w, y0 + h), QPointF(x0, y0 + h)])
    r.name = name
    r.level = "Level 1"
    r._scale_manager_ref = ms.scale_manager
    ms.addItem(r)
    ms._rooms.append(r)
    r._update_label()
    return r


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


def test_categories_and_defaults_table_shape():
    assert ANNOTATION_CATEGORIES == ("Room",)
    assert isinstance(SYSTEM_DEFAULTS, dict)
    assert all(k in ANNOTATION_CATEGORIES for k in SYSTEM_DEFAULTS)


def test_eligible_definition_truth_table(qapp):
    ms = _scene()
    d = _tag_def(ms)
    assert eligible_definition(d, "Room")
    assert not eligible_definition(d, "Pipe")             # wrong host category
    assert not eligible_definition(None, "Room")
    real = BlockDefinition.new(name="R", library="", series="", origin=(0.0, 0.0), primitives=[])
    real.host_category = "Room"
    assert not eligible_definition(real, "Room")          # real size
    fixed = _tag_def(ms, name="Fixed")
    fixed.annotative_screen = SCREEN_FIXED
    assert not eligible_definition(fixed, "Room")         # Fixed size = treated as missing


def test_annotation_block_resolves_the_mapped_project_block(qapp):
    ms = _scene()
    d = _tag_def(ms)
    assert ms.annotation_defaults == {"Room": d.id}
    assert ms.annotation_block("Room") is ms.block_registry.get(d.id)
    assert ms.annotation_block("Pipe") is None            # no mapping, no default


def test_annotation_block_treats_an_ineligible_mapping_as_missing(qapp):
    ms = _scene()
    d = _tag_def(ms)
    d.annotative_screen = SCREEN_FIXED
    assert ms.annotation_block("Room") is None            # ineligible mapping + no default = miss


def test_ac3_annotation_defaults_round_trip_through_the_fpd(qapp, tmp_path):
    ms = _scene()
    d = _tag_def(ms)
    _add_room(ms, "Office")
    f = tmp_path / "a.fpd"
    assert ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["annotation_defaults"] == {"Room": d.id}
    rec["annotation_defaults"]["Pipe"] = 7                     # a non-str value is dropped on load
    f.write_text(json.dumps(rec), encoding="utf-8")
    ms2 = _scene()
    ms2.load_from_file(str(f))
    assert ms2.annotation_defaults == {"Room": d.id}
    assert ms2.annotation_block("Room").id == d.id
    assert ms2._rooms[0]._tag.paints()


def test_ac3_legacy_file_keeps_show_label_and_label_offset(qapp, tmp_path):
    ms = _scene()
    r = _add_room(ms, "Office")
    r._show_label = False
    r._label_offset = QPointF(120.0, -80.0)
    r._update_label()
    f = tmp_path / "legacy.fpd"
    assert ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))
    del rec["annotation_defaults"]                             # a pre-SB3 file has no key, same version
    f.write_text(json.dumps(rec), encoding="utf-8")
    ms2 = _scene()
    ms2.load_from_file(str(f))
    assert ms2.annotation_defaults == {}
    r2 = ms2._rooms[0]
    assert r2._show_label is False and r2._label_offset == QPointF(120.0, -80.0)
    assert r2._tag.pos() == QPointF(1000.0 + 120.0, 1000.0 - 80.0) and not r2._tag.isVisible()


def test_ac3_template_saves_and_overlays_annotation_defaults(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    from firepro3d.settings import template
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    ms = _scene()
    d = _tag_def(ms)
    path = template.save_current_as_default(ms)
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["annotation_defaults"] == {"Room": d.id}
    fresh = _scene()
    template.apply_template_settings(fresh)
    assert fresh.annotation_defaults == {"Room": d.id}


def test_pre_sb3_template_still_embeds_the_system_default_eagerly(qapp, tmp_path, monkeypatch,
                                                                   sys_defaults):
    """VC9 Minor 2: a template saved before SB3 has no ``annotation_defaults`` key;
    the System default must still be embedded by the template overlay itself, not
    lazily inside the first boundingRect()/paint()."""
    from firepro3d import app_data, block_library
    from firepro3d.settings import template
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    path = template.save_current_as_default(_scene())
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data.pop("annotation_defaults", None)                      # pre-SB3 shape
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    sysroot = tmp_path / "sys"
    _shipped(sysroot, "SysTag", "system-tags-systag")
    block_library.set_system_root(str(sysroot))                # conftest restores it
    sys_defaults({"Room": "system-tags-systag"})
    fresh = _scene()
    assert "system-tags-systag" not in fresh._block_definitions
    template.apply_template_settings(fresh)
    assert fresh.annotation_defaults == {}
    assert "system-tags-systag" in fresh._block_definitions   # embedded by the overlay (D-C)


from firepro3d import block_library
from firepro3d.settings.panes import AnnotationPane, MarksPane
from firepro3d.settings.project_settings_dialog import ProjectSettingsDialog


def _shipped(sysroot, name, block_id, series="Tags", category="Room"):
    """Write an eligible System-tier .fpdb (a .fpdb IS to_dict() JSON)."""
    d = BlockDefinition.new(name=name, library="System", series=series, origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "@[Name]", "x": 0.0,
                                         "y": 0.0, "height_mm": 3.0}])
    d.scale_mode = "annotative"
    d.host_category = category
    d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "Name"})]
    d.id = block_id
    folder = sysroot / series
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.fpdb"
    path.write_text(json.dumps(d.to_dict()), encoding="utf-8")
    return str(path)


def test_ac9_annotation_pane_lists_eligible_project_and_system_blocks(qapp, tmp_path):
    ms = _scene()
    d = _tag_def(ms)                                           # eligible project block
    real = BlockDefinition.new(name="Door", library="", series="", origin=(0.0, 0.0), primitives=[])
    real.host_category = "Room"
    ms.register_block_definition(real)                         # real size: not listed
    pipe = BlockDefinition.new(name="PipeTag", library="", series="", origin=(0.0, 0.0),
                               primitives=[{"type": "text", "text": "@[Mark]", "x": 0.0,
                                            "y": 0.0, "height_mm": 3.0}])
    pipe.scale_mode = "annotative"
    pipe.host_category = "Pipe"
    ms.register_block_definition(pipe)                         # other category: not listed
    sysroot = tmp_path / "sys"
    _shipped(sysroot, "SysTag", "system-tags-systag")
    _shipped(sysroot, "PipeSys", "system-tags-pipesys", category="Pipe")
    block_library.set_system_root(str(sysroot))                # conftest restores it
    pane = AnnotationPane(scene=ms)
    pane.load()
    combo = pane._combos["Room"]
    assert [combo.itemText(i) for i in range(combo.count())] == ["TestTag (Project)", "SysTag (System)"]
    assert [combo.itemData(i) for i in range(combo.count())] == [d.id, "system-tags-systag"]
    assert combo.currentData() == d.id


def test_ac9_pane_apply_writes_the_mapping_and_calls_on_changed_only_on_a_change(qapp):
    ms = _scene()
    d = _tag_def(ms)
    d2 = _tag_def(ms, name="Other")
    ms.annotation_defaults["Room"] = d.id
    room = _add_room(ms, "Office")
    fired = []
    pane = AnnotationPane(scene=ms, on_changed=lambda: fired.append(1))
    pane.load()
    pane.apply()
    assert fired == [] and ms.annotation_defaults == {"Room": d.id}
    combo = pane._combos["Room"]
    combo.setCurrentIndex(combo.findData(d2.id))
    pane.apply()
    assert ms.annotation_defaults == {"Room": d2.id} and fired == [1]
    assert ms.annotation_block("Room").id == d2.id and room._tag.definition().id == d2.id
    pane.revert()
    assert ms.annotation_defaults == {"Room": d.id}


def test_ac9_marks_pane_apply_calls_on_changed_only_on_a_change(qapp):
    ms = _scene()
    fired = []
    pane = MarksPane(scene=ms, on_changed=lambda: fired.append(1))
    pane.load()
    pane.apply()
    assert fired == []
    r = next(r for r in range(pane._table.rowCount()) if pane._table.item(r, 0).text() == "Door")
    pane._table.item(r, 1).setText("DR-{n:02}")
    pane.apply()
    assert ms.mark_patterns["Door"] == "DR-{n:02}" and fired == [1]


def test_dialog_rail_has_the_annotation_row_and_ok_applies_it(qapp):
    ms = _scene()
    d = _tag_def(ms)
    d2 = _tag_def(ms, name="Other")
    ms.annotation_defaults["Room"] = d.id
    fired = []
    dlg0 = ProjectSettingsDialog(scene=ms, get_info=lambda: {}, set_info=lambda x: None,
                                 on_changed=lambda: fired.append(1))
    dlg0._on_ok()                                              # baseline: UnitsPane always fires
    base = len(fired)
    assert ms.annotation_defaults == {"Room": d.id}
    fired.clear()
    dlg = ProjectSettingsDialog(scene=ms, get_info=lambda: {}, set_info=lambda x: None,
                                on_changed=lambda: fired.append(1))
    assert dlg.rail_keys() == ["project_info", "units", "marks", "annotation"]
    combo = dlg._panes["annotation"]._combos["Room"]
    combo.setCurrentIndex(combo.findData(d2.id))
    dlg._on_ok()
    assert ms.annotation_defaults == {"Room": d2.id} and len(fired) == base + 1


def _lib_file(root, name, block_id, library="Styles", series="Tags"):
    """An eligible user-library .fpdb (folder = library / series)."""
    d = BlockDefinition.new(name=name, library=library, series=series, origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "@[Name]", "x": 0.0,
                                         "y": 0.0, "height_mm": 3.0}])
    d.scale_mode = "annotative"
    d.host_category = "Room"
    d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "Name"})]
    d.id = block_id
    folder = root / library / series
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.fpdb").write_text(json.dumps(d.to_dict()), encoding="utf-8")


def _notices(ms):
    out = []
    ms._show_status = lambda msg, timeout=5000: out.append(msg)
    return out


def test_resolver_embeds_a_system_block_outside_undo_and_memoises(qapp, tmp_path):
    ms = _scene()
    _add_room(ms, "Office")
    sysroot = tmp_path / "sys"
    _shipped(sysroot, "SysTag", "system-tags-systag")
    block_library.set_system_root(str(sysroot))
    ms.annotation_defaults["Room"] = "system-tags-systag"
    notices = _notices(ms)
    n_undo = len(ms._undo_stack)
    d = ms.annotation_block("Room")
    assert d is not None and d.id == "system-tags-systag"
    assert "system-tags-systag" in ms._block_definitions                 # embedded (D-C)
    assert len(ms._undo_stack) == n_undo and notices == []               # outside undo; the mapped id drew
    assert ms._rooms[0]._tag.paints()
    assert ms.annotation_block("Room") is d                              # memo hit


def test_resolver_falls_back_to_the_library_root_and_notices_a_total_miss(qapp, tmp_path):
    from pathlib import Path
    from firepro3d.app_data import block_library_dir
    ms = _scene()
    _add_room(ms, "Office")
    _lib_file(Path(block_library_dir()), "LibTag", "lib-tag-1")        # the isolated user root
    ms.annotation_defaults["Room"] = "lib-tag-1"
    notices = _notices(ms)
    assert ms.annotation_block("Room").id == "lib-tag-1" and notices == []
    ms.annotation_defaults["Room"] = "nowhere"
    assert ms.annotation_block("Room") is None                           # SYSTEM_DEFAULTS emptied by the autouse fixture
    assert len(notices) == 1 and "nowhere" in notices[0]
    ms.annotation_block("Room")
    assert len(notices) == 1                                             # memoised: one notice
    assert ms.annotation_defaults["Room"] == "nowhere"                   # the mapping is kept (Q6)
    assert ms._rooms[0]._tag.boundingRect().width() > 0                  # the orphan placeholder, never vanishes


def test_load_resolves_the_mapping_once_and_the_notice_outlives_loaded_from(qapp, tmp_path):
    ms = _scene()
    _add_room(ms, "Office")
    ms.annotation_defaults["Room"] = "nowhere"
    f = tmp_path / "n.fpd"
    assert ms.save_to_file(str(f))
    ms2 = _scene()
    notices = _notices(ms2)
    ms2.load_from_file(str(f))
    assert ms2.annotation_defaults == {"Room": "nowhere"}
    tag_notes = [n for n in notices if "nowhere" in n]
    assert len(tag_notes) == 1 and notices[-1] == tag_notes[0]          # last message on the bar
    ms2.annotation_block("Room")
    assert len([n for n in notices if "nowhere" in n]) == 1


def test_load_and_registry_change_refresh_the_cached_tag_rect(qapp, tmp_path):
    ms = _scene()
    d = _tag_def(ms)
    _add_room(ms, "Office")
    f = tmp_path / "r.fpd"
    assert ms.save_to_file(str(f))
    ms2 = _scene()
    ms2.load_from_file(str(f))
    tag = ms2._rooms[0]._tag
    assert tag.boundingRect().width() > 0
    # a registry change re-resolves: drop the block -> the cached rect follows (orphan box)
    ms2.annotation_defaults["Room"] = "nowhere"
    ms2.blockDefinitionsChanged.emit()
    assert tag.boundingRect() == tag._compute_rect()
    assert tag.boundingRect().width() > 0
    assert tag.definition() is None or tag.definition().id != d.id


# ---- G3 fix round 1 -------------------------------------------------------

def test_cancel_after_save_default_restores_mapping_and_tag_shape(qapp, tmp_path, monkeypatch):
    from firepro3d import app_data
    monkeypatch.setattr(app_data, "user_data_root", lambda: str(tmp_path))
    ms = _scene()
    d = _tag_def(ms)
    d2 = _tag_def(ms, name="Other-Longer-Name", height=9.0)
    ms.annotation_defaults["Room"] = d.id
    room = _add_room(ms, "Office")
    tag = room._tag
    opening = tag.boundingRect()
    dlg = ProjectSettingsDialog(scene=ms, get_info=lambda: {}, set_info=lambda x: None)
    combo = dlg._panes["annotation"]._combos["Room"]
    combo.setCurrentIndex(combo.findData(d2.id))
    dlg._on_save_default()
    assert tag.boundingRect() != opening                     # the new block drew
    dlg.reject()
    assert ms.annotation_defaults == {"Room": d.id}
    assert tag.boundingRect() == opening


def test_untouched_ok_neither_pins_the_mapping_nor_fires(qapp):
    ms = _scene()
    _tag_def(ms)
    ms.annotation_defaults.clear()                           # legacy file / new project
    fired = []
    pane = AnnotationPane(scene=ms, on_changed=lambda: fired.append(1))
    pane.load()
    assert pane._combos["Room"].currentIndex() == -1
    pane.apply()
    assert ms.annotation_defaults == {} and fired == []


def test_untouched_ok_with_a_system_default_neither_pins_nor_fires(qapp, tmp_path, sys_defaults):
    ms = _scene()
    sysroot = tmp_path / "sys"
    _shipped(sysroot, "SysTag", "system-tags-systag")
    block_library.set_system_root(str(sysroot))
    sys_defaults({"Room": "system-tags-systag"})
    fired = []
    pane = AnnotationPane(scene=ms, on_changed=lambda: fired.append(1))
    pane.load()
    assert pane._combos["Room"].currentData() == "system-tags-systag"
    pane.apply()
    assert ms.annotation_defaults == {} and fired == []


def test_one_notice_per_mapping_survives_registry_changes(qapp):
    ms = _scene()
    _add_room(ms, "Office")
    ms.annotation_defaults["Room"] = "nowhere"
    notices = _notices(ms)
    assert ms.annotation_block("Room") is None and len(notices) == 1
    ms.blockDefinitionsChanged.emit()
    assert ms.annotation_block("Room") is None
    ms.register_block_definition(BlockDefinition.new(name="Unrelated", library="", series="",
                                                     origin=(0.0, 0.0), primitives=[]))
    assert ms.annotation_block("Room") is None
    assert len(notices) == 1


def test_pane_apply_embeds_eagerly_before_any_paint(qapp, tmp_path):
    ms = _scene()
    d = _tag_def(ms)
    room = _add_room(ms, "Office")
    sysroot = tmp_path / "sys"
    _shipped(sysroot, "SysTag", "system-tags-systag")
    block_library.set_system_root(str(sysroot))
    pane = AnnotationPane(scene=ms)
    pane.load()
    combo = pane._combos["Room"]
    combo.setCurrentIndex(combo.findData("system-tags-systag"))
    assert "system-tags-systag" not in ms._block_definitions
    pane.apply()
    assert "system-tags-systag" in ms._block_definitions      # embedded by apply, not by boundingRect
    assert room._tag.definition().id == "system-tags-systag"


def test_ineligible_library_file_is_never_embedded(qapp):
    from pathlib import Path
    from firepro3d.app_data import block_library_dir
    ms = _scene()
    _add_room(ms, "Office")
    _lib_file(Path(block_library_dir()), "RealTag", "lib-real-1")
    # rewrite the file as a real-size block (not annotative)
    for f in Path(block_library_dir()).rglob("RealTag.fpdb"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        rec["scale_mode"] = "real"
        f.write_text(json.dumps(rec), encoding="utf-8")
    ms.annotation_defaults["Room"] = "lib-real-1"
    notices = _notices(ms)
    assert ms.annotation_block("Room") is None
    assert "lib-real-1" not in ms._block_definitions
    assert len(notices) == 1


def test_choices_label_present_but_ineligible_block_not_eligible_not_missing(qapp):
    ms = _scene()
    real = BlockDefinition.new(name="Door", library="", series="", origin=(0.0, 0.0), primitives=[])
    real.host_category = "Room"
    ms.register_block_definition(real)
    ms.annotation_defaults["Room"] = real.id
    pane = AnnotationPane(scene=ms)
    pane.load()
    combo = pane._combos["Room"]
    assert combo.currentText() == "Door (not eligible)"
    ms.annotation_defaults["Room"] = "ghost-id"
    pane.load()
    assert pane._combos["Room"].currentText() == "ghost-id (missing)"


def test_shipped_tier_is_parsed_once_per_load(qapp, tmp_path, monkeypatch):
    ms = _scene()
    sysroot = tmp_path / "sys"
    _shipped(sysroot, "SysTag", "system-tags-systag")
    block_library.set_system_root(str(sysroot))
    calls = []
    real = block_library.load_block_file
    monkeypatch.setattr(block_library, "load_block_file", lambda p: calls.append(p) or real(p))
    monkeypatch.setattr("firepro3d.system_blocks.ANNOTATION_CATEGORIES", ("Room", "Pipe"))
    pane = AnnotationPane(scene=ms)
    assert set(pane._combos) == {"Room", "Pipe"}
    pane.load()
    assert len(calls) == 1
