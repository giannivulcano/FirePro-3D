"""Task 7: a Note shows in its own view only, and in that view's sheet viewports (D9)."""
import os

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QTabWidget

from firepro3d.assets import system_blocks_path
from firepro3d.block_library import load_block_file
from firepro3d.detail_view import DetailViewManager
from firepro3d.level_manager import LevelManager, PlanViewManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_space import (PaperScene, Sheet, SheetViewData, ViewResolver,
                                   _same_view_context)
from firepro3d.system_blocks import NOTE_BLOCK_ID
from tests._paper_iso_helpers import make_wall


PLAN = "plan:Plan: Level 1"
DETAIL = "detail:D1"
CROP = QRectF(-100.0, -100.0, 1400.0, 900.0)


def view_fixture():
    """A real plan scene with a Level 1 plan view and a detail D1 on the same
    level, sharing the plan's range (so isolation must tell them apart by key)."""
    ms = Model_Space()
    ms.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    lm = LevelManager()
    ms._level_manager = lm
    pvm = PlanViewManager()
    pvm.create("Level 1", lm)
    tabs = QTabWidget()
    det = DetailViewManager(ms, lm, ms.scale_manager, tabs)
    det.create_detail("D1", QRectF(CROP), "Level 1")
    make_wall(ms, (0, -2000), (4000, -2000), "Level 1")      # outside the probe boxes
    resolver = ViewResolver(ms, pvm, det, None, level_manager=lm)
    return dict(ms=ms, lm=lm, pvm=pvm, det=det, tabs=tabs, resolver=resolver)


def place_note(ms, view, pos=(200.0, 200.0), text="MMMM"):
    inst = ms.place_block_instance(
        NOTE_BLOCK_ID, pos, level="Level 1",
        note={"view": view, "wrap_width_mm": 40.0, "box_height_mm": 8.0})
    inst.set_attributes({"Text": text})
    return inst


def show(fx, key):
    ms = fx["ms"]
    ms.active_view_key = key
    ms.active_level = "Level 1"
    fx["lm"].apply_to_scene(ms, "Level 1")


def test_note_shows_only_in_its_view(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    plan, det = place_note(ms, PLAN), place_note(ms, DETAIL)
    show(fx, PLAN)
    assert plan.isVisible() and not det.isVisible()
    show(fx, DETAIL)
    assert det.isVisible() and not plan.isVisible()


def test_a_plain_block_is_unaffected_by_the_view_key(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    plain = ms.place_block_instance(NOTE_BLOCK_ID, (0.0, 0.0), level="Level 1")
    for key in (PLAN, DETAIL, ""):
        show(fx, key)
        assert plain.isVisible()


def test_a_note_with_a_dangling_view_key_stays_hidden_and_in_the_file(qapp):
    fx = view_fixture()
    ms = fx["ms"]
    gone = place_note(ms, "detail:Gone")
    show(fx, PLAN)
    assert not gone.isVisible()
    assert gone.to_dict()["note"]["view"] == "detail:Gone"


def test_same_view_context_compares_the_key():
    ctx = ("Level 1", 3000.0, 0.0)
    assert not _same_view_context(PLAN, ctx, DETAIL, ctx)
    assert _same_view_context(DETAIL, ctx, DETAIL, ctx)
    assert not _same_view_context(DETAIL, None, DETAIL, None)


# -- the viewport: a real SheetViewport paint -------------------------------

SCALE = 0.1          # paper mm per model mm; the paper pass sizes the note at 1 / SCALE
PX = 4               # device px per paper mm, so a 3 mm glyph is ~12 px tall


def _viewport(fx, view_type, name):
    data = SheetViewData(view_type, name, "V", SCALE, 10, 10,
                         CROP.width() * SCALE, CROP.height() * SCALE)
    data.crop_rect = QRectF(CROP)
    paper = PaperScene(Sheet.create_default(), fx["resolver"])
    return paper, paper.add_viewport(data)


def _paint(vp):
    w, h = int(vp.data.w), int(vp.data.h)
    img = QImage((w + 8) * PX, (h + 8) * PX, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.scale(PX, PX)
    vp.paint(p, None, None)
    p.end()
    return img


def _ink_in_box(img, inst, vp):
    """Non-white pixels strictly inside *inst*'s box as the paper pass draws it:
    the box is printed mm (the pass sizes a note by 1 / SCALE), hung from its pos."""
    crop = vp._effective_crop()
    px, py = inst.block_pos()
    x0 = int((px - crop.left()) * SCALE * PX) + 3
    y0 = int((py - crop.top()) * SCALE * PX) + 3
    x1 = x0 - 3 + int(inst.note["wrap_width_mm"] * PX) - 3
    y1 = y0 - 3 + int(inst.note["box_height_mm"] * PX) - 3
    white = QColor("white").rgb()
    return sum(img.pixel(x, y) != white for x in range(x0, x1) for y in range(y0, y1))


@pytest.mark.parametrize("onscreen", [PLAN, DETAIL], ids=["onscreen-plan", "onscreen-detail"])
def test_each_viewport_paints_its_own_notes_and_not_the_others(qapp, onscreen):
    """Plan and detail share level and range, so the old no-op skip painted the
    on-screen view's notes into both. Pixels in each note's box tell which drew."""
    fx = view_fixture()
    ms = fx["ms"]
    plan = place_note(ms, PLAN, (200.0, 200.0))
    det = place_note(ms, DETAIL, (200.0, 500.0))
    show(fx, onscreen)
    paper_p, vp_plan = _viewport(fx, "plan", "Plan: Level 1")
    paper_d, vp_det = _viewport(fx, "detail", "D1")
    img = _paint(vp_plan)
    assert _ink_in_box(img, plan, vp_plan) > 40          # its own note drew
    assert _ink_in_box(img, det, vp_plan) == 0           # the detail's note did not
    img = _paint(vp_det)
    assert _ink_in_box(img, det, vp_det) > 40
    assert _ink_in_box(img, plan, vp_det) == 0
    # the on-screen scene is restored exactly
    assert ms.active_view_key == onscreen
    assert plan.isVisible() is (onscreen == PLAN)
    assert det.isVisible() is (onscreen == DETAIL)


# -- sections and 3D --------------------------------------------------------

def test_a_section_scene_never_copies_a_note(qapp, section_scene_for):
    from firepro3d.block_instance import BlockInstance
    from tests.test_section_classification import _placed_scene
    ms, sec = _placed_scene(section_scene_for, (0, 0), (10000, 0), 8000.0)
    ms.register_block_definition(load_block_file(
        os.path.join(system_blocks_path(), "Annotations", "Note.fpdb")))
    note = place_note(ms, PLAN, (1000.0, -1000.0))
    assert note.isVisible()
    sec.rebuild()
    assert [i for i in sec.items() if isinstance(i, BlockInstance)] == []
