"""SB3 G4 / AC5 -- the frozen System default: SYSTEM_DEFAULTS["Room"] is the id of the
shipped RoomTag (firepro3d/system_blocks/Tags/RoomTag.fpdb, promoted by the user at U2);
the file is an eligible Room tag binding only the Name (Q1); it cannot be written outside
the dev gate; a missing mapped id falls back to it with one notice (Q6, G5)."""
import hashlib
import os
import shutil

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from firepro3d import block_library
from firepro3d.assets import system_blocks_path
from firepro3d.bound_label import eligible_definition
from firepro3d.level_manager import LevelManager
from firepro3d.model_space import Model_Space
from firepro3d.room import Room
from firepro3d.settings.panes import AnnotationPane
from firepro3d.system_blocks import ANNOTATION_CATEGORIES, SYSTEM_DEFAULTS

SHIPPED = system_blocks_path("Tags", "RoomTag.fpdb")
FROZEN_ID = "system-tags-roomtag"          # U3's id (system_promote slug rule: system-<series>-<name>)
RECT = QRectF(-500.0, -500.0, 3000.0, 3000.0)


def _scene():
    ms = Model_Space()
    ms._level_manager = LevelManager()
    return ms


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


def test_every_annotation_category_has_a_frozen_default():
    assert set(SYSTEM_DEFAULTS) == set(ANNOTATION_CATEGORIES)
    assert SYSTEM_DEFAULTS["Room"] == FROZEN_ID


def test_system_default_is_the_shipped_roomtag(real_system_library):
    idx = block_library.shipped_index()
    assert os.path.normcase(idx[SYSTEM_DEFAULTS["Room"]]) == os.path.normcase(SHIPPED)
    d = block_library.load_block_file(SHIPPED)
    assert d is not None and d.id == FROZEN_ID
    assert d.library == block_library.SYSTEM_LIBRARY and d.series == "Tags"
    assert eligible_definition(d, "Room")
    texts = [p for p in d.primitives if p.get("type") == "text"]
    assert len(texts) == 1 and texts[0]["text"] == "@[Name]"                 # Q1: Name only
    assert {a["host_key"] for a in d.effective_attributes() if a["source"] == "host"} == {"Name"}


def test_shipped_roomtag_cannot_be_written_outside_the_dev_gate(real_system_library):
    with open(SHIPPED, "rb") as fh:
        before = fh.read()
    with pytest.raises(block_library.SystemLibraryReadOnly):
        block_library.write_shipped(SHIPPED, {"id": "x"})            # conftest: gate OFF
    with open(SHIPPED, "rb") as fh:
        assert fh.read() == before


def test_annotation_pane_default_row_reads_roomtag_system(qapp, real_system_library):
    ms = _scene()
    pane = AnnotationPane(scene=ms)
    pane.load()
    combo = pane._combos["Room"]
    assert combo.currentText() == "RoomTag (System)" and combo.currentData() == FROZEN_ID


def _temp_tier_with_roomtag(tmp_path):
    """The real shipped RoomTag copied into a temp System root (conftest hands
    every test an EMPTY tier; shipped_index() walks the root fresh)."""
    folder = tmp_path / "sys" / "Tags"
    folder.mkdir(parents=True)
    shutil.copy(SHIPPED, folder / "RoomTag.fpdb")
    block_library.set_system_root(str(tmp_path / "sys"))


def test_ac5_missing_mapped_id_falls_back_to_the_shipped_roomtag_with_one_notice(qapp, tmp_path):
    _temp_tier_with_roomtag(tmp_path)
    ms = _scene()
    room = _add_room(ms, "Office")
    ms.annotation_defaults["Room"] = "missing-block-id"
    notices = []
    ms._show_status = lambda msg, timeout=5000: notices.append(msg)
    n_undo = len(ms._undo_stack)
    d = ms.annotation_block("Room")
    assert d is not None and d.id == FROZEN_ID
    assert FROZEN_ID in ms._block_definitions and len(ms._undo_stack) == n_undo   # embedded outside undo
    assert ms.annotation_defaults["Room"] == "missing-block-id"                 # the mapping is kept (Q6)
    assert len(notices) == 1 and "missing-block-id" in notices[0] and "RoomTag" in notices[0]
    assert room._tag.paints()
    on = _digest(_render(ms, RECT, 300, 300))
    room._show_label = False
    room._update_label()
    assert _digest(_render(ms, RECT, 300, 300)) != on                           # the shipped tag inks the name
    ms.annotation_block("Room")
    assert len(notices) == 1                                                    # one notice
