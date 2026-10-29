"""SB3b -- per-room tag style: Room.tag_block (None = project default) resolved ahead
of annotation_defaults (G1), a missing per-room id falls back with one notice (G2),
a project-default change moves only None rooms (AC5), tag_block round-trips file /
undo / paste (AC6), the panel Tag row is one undo step incl. a library embed
(G3 / G6), one shared choice list feeds the row and the Annotation pane (G6)."""
# -- shared helpers (copied per SB3 test-file convention) ----------------------
import hashlib
import json
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from firepro3d import block_library
from firepro3d.app_data import block_library_dir
from firepro3d.block_attributes import bound_text_ops, normalise_attr
from firepro3d.block_definition import BlockDefinition
from firepro3d.bound_label import PEN_MARGIN
from firepro3d.element_params import host_values
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.property_manager import PropertyManager
from firepro3d.room import Room
from firepro3d.settings.panes import AnnotationPane

TAG_MM = 3.0
RECT_A = QRectF(-500.0, -500.0, 3000.0, 3000.0)      # room A: 2000 x 2000 at the origin + margin
RECT_B = QRectF(4500.0, -500.0, 3000.0, 3000.0)      # room B: x0 = 5000


def _tag_def(ms, name="TestTag", height=TAG_MM):
    """An eligible Room tag registered in the project and mapped as the default."""
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


def _render(scene, rect, w, h, bg=0xFF101010):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(bg)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w, h), rect, Qt.AspectRatioMode.IgnoreAspectRatio)
    p.end()
    return img


def _digest(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return hashlib.sha256(bytes(ptr)).hexdigest()


def _glyph_rect(d, room):
    """The tag's ops bbox at k = 1 for *room* drawn by *d* (the raw source of sizes)."""
    ops, _c = bound_text_ops(d, {}, host_values(room), False, 1.0, None, None)
    r = QRectF()
    for op in ops:
        r = r.united(op.path.boundingRect())
    return r


def _tag_height(room):
    return room._tag.boundingRect().adjusted(PEN_MARGIN, PEN_MARGIN, -PEN_MARGIN, -PEN_MARGIN).height()


def _notices(ms):
    out = []
    ms._show_status = lambda msg, timeout=5000: out.append(msg)
    return out


def _lib_file(root, name, block_id, *, eligible=True, library="Styles", series="Tags"):
    """A user-library .fpdb (folder = library / series); eligible = annotative Room tag,
    else a real-size block (treated as missing by bound_label.eligible_definition)."""
    d = BlockDefinition.new(name=name, library=library, series=series, origin=(0.0, 0.0),
                            primitives=[{"type": "text", "text": "@[Name]", "x": 0.0,
                                         "y": 0.0, "height_mm": 3.0}])
    if eligible:
        d.scale_mode = "annotative"
    d.host_category = "Room"
    d.attributes = [normalise_attr({"key": "Name", "source": "host", "host_key": "Name"})]
    d.id = block_id
    folder = Path(root) / library / series
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.fpdb"
    path.write_text(json.dumps(d.to_dict()), encoding="utf-8")
    return str(path)


# -- G1 / G2 / AC5 / AC6 -------------------------------------------------------

def test_g1_two_rooms_with_different_tag_blocks_draw_their_own_block(qapp):
    ms = _scene()
    small = _tag_def(ms, "Small", 3.0)
    big = _tag_def(ms, "Big", 6.0)
    ms.annotation_defaults["Room"] = small.id
    a = _add_room(ms, "Office")
    b = _add_room(ms, "Lobby", x0=5000.0)
    b._tag_block = big.id
    b._tag.refresh()
    k = ms.scale_manager.drawing_scale
    assert _tag_height(a) == pytest.approx(_glyph_rect(small, a).height() * k, rel=1e-6)
    assert _tag_height(b) == pytest.approx(_glyph_rect(big, b).height() * k, rel=1e-6)
    assert a._tag.definition() is ms.block_registry.get(small.id)
    assert b._tag.definition() is ms.block_registry.get(big.id)
    own = _digest(_render(ms, RECT_B, 300, 300))
    b._tag_block = None
    b._tag.refresh()
    assert _digest(_render(ms, RECT_B, 300, 300)) != own          # B's pixels came from its own block
    assert _tag_height(b) == pytest.approx(_glyph_rect(small, b).height() * k, rel=1e-6)


def test_g2_missing_per_room_id_falls_back_to_the_project_default_with_one_notice(qapp):
    ms = _scene()
    d = _tag_def(ms)
    room = _add_room(ms, "Office")
    notices = _notices(ms)
    with_default = _digest(_render(ms, RECT_A, 300, 300))
    room._tag_block = "nowhere"
    room._tag.refresh()
    assert _digest(_render(ms, RECT_A, 300, 300)) == with_default   # drew the project default
    assert room._tag.definition() is ms.block_registry.get(d.id)
    assert len(notices) == 1 and "nowhere" in notices[0] and "project default" in notices[0]
    ms._annot_memo.clear()                                          # a registry change clears the memo
    room._tag.refresh()
    _render(ms, RECT_A, 300, 300)
    assert len(notices) == 1                                        # once per (category, id)
    assert room.tag_block == "nowhere"                              # the room keeps its id
    assert room.to_dict()["tag_block"] == "nowhere"                 # and the file would too


def test_ac5_project_default_change_moves_only_rooms_on_the_default(qapp):
    ms = _scene()
    small = _tag_def(ms, "Small", 3.0)
    big = _tag_def(ms, "Big", 6.0)
    ms.annotation_defaults["Room"] = small.id
    a = _add_room(ms, "Office")                    # None: follows the default
    b = _add_room(ms, "Lobby", x0=5000.0)
    b._tag_block = small.id                        # pinned explicitly to the same block
    b._tag.refresh()
    k = ms.scale_manager.drawing_scale
    a1 = _digest(_render(ms, RECT_A, 300, 300))
    b1 = _digest(_render(ms, RECT_B, 300, 300))
    pane = AnnotationPane(scene=ms)                # the real project-default path (spec 7)
    pane.load()
    combo = pane._combos["Room"]
    combo.setCurrentIndex(combo.findData(big.id))
    pane.apply()
    assert ms.annotation_defaults["Room"] == big.id
    assert _digest(_render(ms, RECT_A, 300, 300)) != a1            # the None room moved
    assert _digest(_render(ms, RECT_B, 300, 300)) == b1            # the pinned room did not
    assert _tag_height(a) == pytest.approx(_glyph_rect(big, a).height() * k, rel=1e-6)
    assert _tag_height(b) == pytest.approx(_glyph_rect(small, b).height() * k, rel=1e-6)


def test_ac6_tag_block_round_trips_file_undo_and_paste(qapp, tmp_path):
    ms = _scene()
    small = _tag_def(ms, "Small", 3.0)
    big = _tag_def(ms, "Big", 6.0)
    ms.annotation_defaults["Room"] = small.id
    room = _add_room(ms, "Office")
    assert "tag_block" not in room.to_dict()                       # None is written sparsely
    room._tag_block = big.id
    f = tmp_path / "t.fpd"
    assert ms.save_to_file(str(f))
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["rooms"][0]["tag_block"] == big.id
    assert rec["version"] == Model_Space.SAVE_VERSION               # no bump
    ms2 = _scene()
    ms2.load_from_file(str(f))
    assert ms2._rooms[0].tag_block == big.id
    assert ms2._rooms[0]._tag.definition().id == big.id
    rec["rooms"][0]["tag_block"] = 7                                # non-str -> None
    f.write_text(json.dumps(rec), encoding="utf-8")
    ms3 = _scene()
    ms3.load_from_file(str(f))
    assert ms3._rooms[0].tag_block is None
    assert Room.from_dict({"boundary": [[0, 0], [1, 0], [1, 1]]}).tag_block is None   # missing -> None
    # undo snapshot (set -> push -> push -> undo keeps it)
    ms.push_undo_state()
    ms.push_undo_state()
    ms.undo()
    assert ms._rooms[0].tag_block == big.id
    # paste (Ctrl+V, Array and Duplicate Level all rebuild rooms from to_dict records)
    new = ms.paste_items(QPointF(10000.0, 0.0), data=ms._clipboard_item_dicts([ms._rooms[0]]))
    assert [r.tag_block for r in new if isinstance(r, Room)] == [big.id]
