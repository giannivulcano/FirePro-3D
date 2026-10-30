"""L283 -- per-item ``_display_overrides`` (Model Browser Hide = visible, Fill Type
section override = section_type, Graphic Override colours) round-trip to_dict /
from_dict on every DisplayableItemMixin holder: undo snapshot, .fpd and paste.
One helper pair on the mixin (display_overrides_to_dict / _from_dict)."""
import json

import pytest
from PyQt6.QtCore import QPointF

from firepro3d import fill_types as ft
from firepro3d.fill_layers import BackgroundLayer, FillLayers
from firepro3d.floor_slab import FloorSlab
from firepro3d.gridline import GridlineItem
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space

RED = FillLayers(BackgroundLayer("#ff0000", 1.0))
SQUARE = [QPointF(0.0, 0.0), QPointF(2000.0, 0.0), QPointF(2000.0, 2000.0), QPointF(0.0, 2000.0)]


def test_mixin_helpers_write_sparsely_and_read_missing_as_empty(qapp):
    slab = FloorSlab(points=list(SQUARE))
    assert "display_overrides" not in slab.to_dict()                  # untouched: no key
    slab._display_overrides["visible"] = False
    slab._display_overrides["color"] = "#112233"
    d = slab.to_dict()
    assert d["display_overrides"] == {"visible": False, "color": "#112233"}
    d["display_overrides"]["color"] = "#ffffff"                       # a copy, not the live dict
    assert slab._display_overrides["color"] == "#112233"
    back = FloorSlab.from_dict(d)
    assert back._display_overrides == {"visible": False, "color": "#ffffff"}
    assert back.isVisible() is False                                  # a carried Hide applies
    assert back._display_overrides is not d["display_overrides"]      # no aliasing of the record
    assert FloorSlab.from_dict({"points": [[0, 0], [1, 0], [1, 1]], "display_overrides": 7})._display_overrides == {}
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(5000.0, 0.0), label="A")
    gl._display_overrides["visible"] = False
    g = gl.to_dict()
    assert g["display_overrides"] == {"visible": False}
    gl2 = GridlineItem.from_dict(g)
    assert gl2._display_overrides == {"visible": False} and gl2.isVisible() is False
    assert gl2._display_overrides is not g["display_overrides"]


def test_mixin_from_dict_routes_section_type_through_canonical_id(qapp, monkeypatch):
    """The helper re-points section_type through fill_types.canonical_id (HF5 VC9 M2).
    The real alias (a name-duplicate type loaded from a file) is guarded end to end by
    tests/test_hf5_fill_types_persist.py; FillTypeTable.add refuses a duplicate name
    in memory (fill_types.py:87-94), so the alias cannot be built here without a file."""
    ft.reset_project_table()
    ft.project_table().add(ft.FillType("keep", "Red", RED))
    slab = FloorSlab(points=list(SQUARE))
    slab._display_overrides["section_type"] = "keep"
    rec = slab.to_dict()
    assert FloorSlab.from_dict(rec)._display_overrides["section_type"] == "keep"   # a kept id is itself
    assert FloorSlab.from_dict({"points": [[0, 0], [1, 0], [1, 1]],
                                "display_overrides": {"section_type": "nope"}}
                               )._display_overrides["section_type"] == "nope"      # unknown id unchanged
    seen = []
    monkeypatch.setattr(ft, "canonical_id", lambda tid, table=None: seen.append(tid) or f"kept-{tid}")
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(5000.0, 0.0), label="A")
    gl._display_overrides["section_type"] = "alias"
    assert GridlineItem.from_dict(gl.to_dict())._display_overrides["section_type"] == "kept-alias"
    assert seen == ["alias"]                     # exactly one re-point, through the module attribute
    ft.reset_project_table()


from firepro3d.geometry_2d import LineItem
from firepro3d.roof import RoofItem
from firepro3d.room import Room
from firepro3d.text_item import TextAnnotationData, TextItem
from firepro3d.wall import WallSegment
from firepro3d.wall_opening import WallOpening


def _wall(ms, y=0.0):
    w = WallSegment(QPointF(0.0, y), QPointF(3000.0, y))
    ms.addItem(w)
    ms._walls.append(w)
    return w


def test_p2_hidden_before_add_item_stays_hidden(qapp):
    """P4 probe P-2: setVisible(False) applied before scene.addItem survives the add."""
    ms = Model_Space()
    w = WallSegment(QPointF(0.0, 0.0), QPointF(100.0, 0.0))
    w.setVisible(False)
    ms.addItem(w)
    assert w.isVisible() is False and w.scene() is ms


@pytest.mark.parametrize("with_levels", [False, True])
def test_g5_hidden_wall_stays_hidden_through_push_push_undo(qapp, with_levels):
    """L283 repro: Hide, push, push, undo -> the rebuilt wall keeps visible=False
    AND is not visible. with_levels=False is the bug's own parameter (no level pass
    re-hides anything); True is the app's path (apply_to_scene honours the override)."""
    ms = Model_Space()
    if with_levels:
        ms._level_manager = LevelManager()
    w = _wall(ms)
    uid = w._uid
    ms.push_undo_state()                       # before the Hide
    ms._hide_items([w])                        # Model Browser Hide (model_browser.py:569 -> _hide_items)
    ms.push_undo_state()
    ms.push_undo_state()
    ms.undo()                                  # the post-Hide snapshot, rebuilt from to_dict
    wall = next(x for x in ms._walls if x._uid == uid)
    assert wall is not w
    assert wall._display_overrides.get("visible") is False
    assert wall.isVisible() is False


def test_g4_2d_geometry_and_text_overrides_round_trip_undo_in_a_block_editor_scene(qapp):
    """scene-io.md section 5: loose geometry / text are never file-persisted in a plan
    scene; their overrides are guarded on the UNDO path of the Block Editor scratchpad."""
    ms = Model_Space(scene_role="block_editor")
    line = LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0))
    ms.addItem(line)
    ms._draw_lines.append(line)
    text = TextItem(TextAnnotationData(text="T", x=0.0, y=0.0, height_mm=20.0))
    ms.addItem(text)
    ms._texts.append(text)
    ms.push_undo_state()
    ms._hide_items([line, text])
    line._display_overrides["fill"] = "#ff0000"          # a Graphic Override (geometry_2d._fill_value)
    ms.push_undo_state()
    ms.push_undo_state()
    ms.undo()
    l2, t2 = ms._draw_lines[0], ms._texts[0]
    assert l2 is not line and t2 is not text
    assert l2._display_overrides == {"visible": False, "fill": "#ff0000"} and l2.isVisible() is False
    assert t2._display_overrides == {"visible": False} and t2.isVisible() is False


def test_every_holder_to_dict_from_dict_carries_overrides(qapp):
    """The four plan holders + opening: record shape and the carried Hide."""
    ms = Model_Space()
    wall = _wall(ms)
    op = WallOpening(wall=wall, feature_id="door_914", offset_along=600.0)
    wall.openings.append(op)
    ms.addItem(op)
    room = Room(boundary=list(SQUARE))
    room.name = "Office"
    roof = RoofItem(points=list(SQUARE))
    for it in (wall, op, room, roof):
        it._display_overrides["visible"] = False
    wall._display_overrides["section_type"] = "some-id"
    w2 = WallSegment.from_dict(wall.to_dict())
    o2 = WallOpening.from_dict(op.to_dict(), wall=w2)
    r2 = Room.from_dict(room.to_dict())
    rf2 = RoofItem.from_dict(roof.to_dict())
    assert w2._display_overrides == {"visible": False, "section_type": "some-id"}
    assert o2._display_overrides == {"visible": False}
    assert r2._display_overrides == {"visible": False}
    assert rf2._display_overrides == {"visible": False}
    assert all(it.isVisible() is False for it in (w2, o2, r2, rf2))
    assert "display_overrides" not in Room(boundary=list(SQUARE)).to_dict()


def test_g4_fpd_round_trip_and_paste_carry_hide_and_section_type(qapp, tmp_path):
    ms = Model_Space()
    ms._level_manager = LevelManager()
    wall = _wall(ms)
    op = WallOpening(wall=wall, feature_id="door_914", offset_along=600.0)
    wall.openings.append(op)
    ms.addItem(op)
    room = Room(boundary=list(SQUARE))
    room.name = "Office"
    room.level = "Level 1"
    room._scale_manager_ref = ms.scale_manager
    ms.addItem(room)
    ms._rooms.append(room)
    roof = RoofItem(points=list(SQUARE))
    ms.addItem(roof)
    ms._roofs.append(roof)
    ms._hide_items([wall, op, room, roof])                       # Model Browser Hide
    wall._display_overrides["section_type"] = "some-id"          # Fill Type section override
    f = tmp_path / "ov.fpd"
    assert ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["walls"][0]["display_overrides"] == {"visible": False, "section_type": "some-id"}
    assert rec["walls"][0]["openings"][0]["display_overrides"] == {"visible": False}
    assert rec["rooms"][0]["display_overrides"] == {"visible": False}
    assert rec["roofs"][0]["display_overrides"] == {"visible": False}
    ms2 = Model_Space()
    ms2._level_manager = LevelManager()
    ms2.load_from_file(str(f))
    w2, r2, rf2 = ms2._walls[0], ms2._rooms[0], ms2._roofs[0]
    o2 = w2.openings[0]
    for it in (w2, o2, r2, rf2):
        assert it._display_overrides.get("visible") is False
        assert it.isVisible() is False                           # hidden on the canvas after open
    assert w2._display_overrides["section_type"] == "some-id"
    # Paste (Ctrl+V, Array, Duplicate Level all rebuild from to_dict records).
    new = ms2.paste_items(QPointF(10000.0, 0.0), data=ms2._clipboard_item_dicts([w2, r2, rf2]))
    pw = next(i for i in new if isinstance(i, WallSegment))
    pr = next(i for i in new if isinstance(i, Room))
    prf = next(i for i in new if isinstance(i, RoofItem))
    assert pw._display_overrides == {"visible": False, "section_type": "some-id"} and pw.isVisible() is False
    assert pw.openings[0]._display_overrides == {"visible": False} and pw.openings[0].isVisible() is False
    assert pr._display_overrides == {"visible": False} and pr.isVisible() is False
    assert prf._display_overrides == {"visible": False} and prf.isVisible() is False


def test_g4_folded_holders_gridline_and_slab_keep_hide_through_paste_and_array(qapp):
    """Review fix (Group A): the folded-in holders keep a carried Hide on paste;
    _register_gridline's category apply used to re-show a pasted / arrayed gridline."""
    ms = Model_Space()
    ms._level_manager = LevelManager()
    gl = GridlineItem(QPointF(0.0, 0.0), QPointF(5000.0, 0.0), label="A")
    ms._register_gridline(gl)
    slab = FloorSlab(points=list(SQUARE))
    slab.level = "Level 1"
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    ms._hide_items([gl, slab])
    new = ms.paste_items(QPointF(0.0, 10000.0), data=ms._clipboard_item_dicts([gl, slab]))
    pg = next(i for i in new if isinstance(i, GridlineItem))
    ps = next(i for i in new if isinstance(i, FloorSlab))
    assert pg._display_overrides == {"visible": False} and pg.isVisible() is False
    assert ps._display_overrides == {"visible": False} and ps.isVisible() is False
    cp = gl._clone_parallel(1000.0)
    ms._register_gridline(cp)                                        # the Array / Offset path
    assert cp._display_overrides == {"visible": False} and cp.isVisible() is False
