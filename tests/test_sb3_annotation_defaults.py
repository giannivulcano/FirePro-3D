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
