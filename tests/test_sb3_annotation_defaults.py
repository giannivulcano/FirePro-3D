"""SB3 -- annotation_defaults: eligibility, the project-registry resolver (Task 3),
the .fpd / template round trip (AC3, Task 8), the fallback chain + notice (Task 10),
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
    assert ms.annotation_block("Room") is None            # Task 10 adds the fallback chain


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
