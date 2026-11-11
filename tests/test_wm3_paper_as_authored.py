"""WM3 smoke S1 -- the Paper Space "Blocks" Colour chip can be As Authored
(user ruling 2026-11-11, linetypes.md WM3).

As Authored (``stroke_style.AS_AUTHORED``) on that one chip means "no paper
colour override": under Custom a block plots its authored colours and any
placement Colour override; a By Category placement plots the Model "Blocks"
colour; B&W stays all black. Real composite block, real paper pass (pixels) and
real PDF export (parsed ops); expected colours cite ``wm3_support.AUTHORED`` /
``OVR`` and the colours the tests set."""
import json

import pytest
from PyQt6.QtWidgets import QDialog

from firepro3d import colour_picker
from firepro3d import paper_display as pd
from firepro3d.display_manager import DisplayManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode
from firepro3d.stroke_style import AS_AUTHORED
from tests.test_lt1_block_paper import _crop, _export, _render_model
from tests.wm3_support import (AUTHORED, BOXES, OVR, box_colours, composite_scene,
                               pdf_colours, rgb)

_CAT = "#00aa00"        # a real paper "Blocks" colour no authored component uses
_MODEL = "#00ff00"      # Model "Blocks" colour (reaches paper only through As Authored)
_TEXTFILL = AUTHORED["textfill"]
_BLACK = rgb("#000000")


@pytest.fixture(autouse=True)
def _reset_model_blocks():
    pd.set_model_blocks_colour(None)
    yield
    pd.set_model_blocks_colour(None)


def _paper_blocks(colour):
    cats = pd.load_paper_categories()
    cats["Blocks"]["color"] = colour
    pd.save_paper_categories(cats)


def _paper_render(ms, scale=0.02):
    """The model scene rendered INSIDE a paper pass (what a sheet viewport
    paints): ``_render_model`` pixels with the paper hooks live."""
    saved = pd.apply_paper_overrides(ms, _crop(scale), paper_scale=scale)
    try:
        return _render_model(ms)
    finally:
        pd.restore_model_display(saved)


def _pdf(tmp_path, ms, name):
    return pdf_colours(_export(tmp_path, ms, 0.02, name))


# -- G-S1a: Custom + As Authored keeps authored and placement colours -----------

def test_s1a_custom_as_authored_keeps_authored_colours(qapp, shipped_hatches, tmp_path):
    save_paper_color_mode(PaperColorMode.CUSTOM)
    _paper_blocks(AS_AUTHORED)
    ms, _ = composite_scene(shipped_hatches)
    img = _paper_render(ms)
    assert box_colours(img, BOXES["circle"]) == {AUTHORED["circle"]}      # red
    assert box_colours(img, BOXES["deflector"]) == {AUTHORED["deflector"]}  # blue
    strokes, _fills = _pdf(tmp_path, ms, "a.pdf")
    assert {rgb(AUTHORED["circle"]), rgb(AUTHORED["deflector"])} <= set(strokes)


def test_s1a_custom_as_authored_placement_colour_wins(qapp, shipped_hatches, tmp_path):
    save_paper_color_mode(PaperColorMode.CUSTOM)
    _paper_blocks(AS_AUTHORED)
    ms, _ = composite_scene(shipped_hatches, {"colour": OVR})
    twin, _ = composite_scene(shipped_hatches, colour=OVR)
    img = _paper_render(ms)
    assert box_colours(img, BOXES["circle"]) == {OVR}
    assert box_colours(img, BOXES["deflector"]) == {OVR}
    got = _pdf(tmp_path, ms, "o.pdf")
    assert got == _pdf(tmp_path, twin, "t.pdf")
    assert set(got[0]) == {rgb(OVR)}


# -- G-S1b: a real colour keeps today's behaviour -------------------------------

def test_s1b_custom_real_colour_still_forces_the_category_colour(qapp, shipped_hatches,
                                                                tmp_path):
    save_paper_color_mode(PaperColorMode.CUSTOM)
    _paper_blocks(_CAT)
    ms, _ = composite_scene(shipped_hatches)
    img = _paper_render(ms)
    assert box_colours(img, BOXES["circle"]) == {_CAT}
    assert box_colours(img, BOXES["deflector"]) == {_CAT}
    strokes, _ = _pdf(tmp_path, ms, "c.pdf")
    assert rgb(AUTHORED["circle"]) not in strokes and rgb(_CAT) in strokes


# -- G-S1c: B&W stays all black -------------------------------------------------

def test_s1c_bw_as_authored_is_black(qapp, shipped_hatches, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    _paper_blocks(AS_AUTHORED)
    ms, _ = composite_scene(shipped_hatches)
    got = _pdf(tmp_path, ms, "bw.pdf")
    assert rgb(AUTHORED["circle"]) not in got[0] and rgb(AUTHORED["deflector"]) not in got[0]
    assert _BLACK in got[0]
    _paper_blocks("#000000")             # today's B&W: the category colour is black
    ms2, _ = composite_scene(shipped_hatches)
    assert got == _pdf(tmp_path, ms2, "bw2.pdf")


# -- G-S1d: By Category + As Authored plots the Model "Blocks" colour -----------

@pytest.mark.parametrize("mode", [PaperColorMode.FULL_COLOR, PaperColorMode.CUSTOM])
def test_s1d_by_category_plots_the_model_blocks_colour(qapp, shipped_hatches, tmp_path,
                                                       mode):
    save_paper_color_mode(mode)
    _paper_blocks(AS_AUTHORED)
    pd.set_model_blocks_colour(_MODEL)
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    twin, _ = composite_scene(shipped_hatches, colour=_MODEL)
    img = _paper_render(ms)
    assert box_colours(img, BOXES["circle"]) == {_MODEL}
    assert box_colours(img, BOXES["deflector"]) == {_MODEL}
    got = _pdf(tmp_path, ms, "bc.pdf")
    assert got == _pdf(tmp_path, twin, "tw.pdf")
    assert set(got[0]) == {rgb(_MODEL)}
    assert set(got[1]) == {rgb(_MODEL), rgb(_TEXTFILL)}


def test_s1d_factory_model_blocks_colour_is_black_on_paper(qapp, shipped_hatches, tmp_path):
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    _paper_blocks(AS_AUTHORED)           # Model "Blocks" = factory token:auto
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    assert set(_pdf(tmp_path, ms, "f.pdf")[0]) == {_BLACK}


def test_s1d_bw_by_category_keeps_todays_black(qapp, shipped_hatches, tmp_path):
    save_paper_color_mode(PaperColorMode.BW)
    _paper_blocks(AS_AUTHORED)
    pd.set_model_blocks_colour(_MODEL)
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    assert set(_pdf(tmp_path, ms, "b.pdf")[0]) == {_BLACK}


def test_s1d_real_category_colour_by_category_is_unchanged(qapp, shipped_hatches, tmp_path):
    save_paper_color_mode(PaperColorMode.CUSTOM)
    _paper_blocks(_CAT)
    pd.set_model_blocks_colour(_MODEL)
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    assert set(_pdf(tmp_path, ms, "r.pdf")[0]) == {rgb(_CAT)}


# -- G-S1e: persistence round-trips the sentinel --------------------------------

def test_s1e_qsettings_and_project_file_round_trip(qapp):
    _paper_blocks(AS_AUTHORED)
    assert pd.load_paper_categories()["Blocks"]["color"] == AS_AUTHORED
    save_paper_color_mode(PaperColorMode.CUSTOM)
    data = json.loads(json.dumps(pd.get_paper_display_for_save()))   # the .fpd JSON path
    assert data["categories"]["Blocks"]["color"] == AS_AUTHORED
    pd.save_paper_categories(pd.factory_paper_categories())
    assert pd.load_paper_categories()["Blocks"]["color"] != AS_AUTHORED
    pd.apply_paper_display_from_project(data)
    assert pd.load_paper_categories()["Blocks"]["color"] == AS_AUTHORED
    assert pd.load_paper_color_mode() is PaperColorMode.CUSTOM


# -- G-S1f: the Display Manager chip + the picker flag --------------------------

def _dialog_offers(as_authored_kwarg):
    dlg = (colour_picker.ColourPickerDialog(None, initial="#112233", as_authored=True)
           if as_authored_kwarg else
           colour_picker.ColourPickerDialog(None, initial="#112233"))
    try:
        return [c for c in dlg._theme_row_chips if c.value == AS_AUTHORED]
    finally:
        dlg.deleteLater()


def test_s1f_dialog_offers_as_authored_only_when_asked(qapp):
    assert len(_dialog_offers(True)) == 1
    assert _dialog_offers(False) == []


def test_s1f_dialog_as_authored_chip_commits_the_sentinel(qapp):
    dlg = colour_picker.ColourPickerDialog(None, initial=AS_AUTHORED, as_authored=True)
    try:
        assert dlg.current_value() == AS_AUTHORED         # an As Authored start is kept
        dlg._on_chip("#ff0000")
        assert dlg.current_value() == "#FF0000"           # a colour leaves the sentinel
        chip = next(c for c in dlg._theme_row_chips if c.value == AS_AUTHORED)
        chip.committed.emit(chip.value)                    # double-click = commit
        assert dlg.result_value() == AS_AUTHORED
        assert colour_picker.load_recents() == []          # never remembered as a colour
    finally:
        dlg.deleteLater()


def _drive_dm(monkeypatch, key):
    """Click ``key``'s Colour chip with the REAL pick_colour; the dialog's exec
    is replaced by 'commit the As Authored chip if offered'. Returns the
    offered flag and the DM."""
    seen = []

    def exec_(self):
        chips = [c for c in self._theme_row_chips if c.value == AS_AUTHORED]
        seen.append(bool(chips))
        if not chips:
            return QDialog.DialogCode.Rejected
        chips[0].committed.emit(chips[0].value)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(colour_picker.ColourPickerDialog, "exec", exec_)
    dm = DisplayManager(Model_Space())
    save_paper_color_mode(PaperColorMode.BW)
    dm._paper_cat_data[key]["color_btn"]._chip.clicked.emit()
    return seen, dm


def test_s1f_blocks_chip_stores_and_shows_as_authored(qapp, monkeypatch):
    seen, dm = _drive_dm(monkeypatch, "Blocks")
    assert seen == [True]
    btn = dm._paper_cat_data["Blocks"]["color_btn"]
    assert btn.hex() == AS_AUTHORED
    assert btn._label.text() == "As Authored" and btn._chip.toolTip() == "As Authored"
    assert btn._chip.grab().toImage().pixelColor(btn._chip.width() // 2,
                                                 btn._chip.height() // 2).isValid()
    assert pd.load_paper_categories(dm._settings)["Blocks"]["color"] == AS_AUTHORED
    assert pd.load_paper_color_mode(dm._settings) is PaperColorMode.CUSTOM   # auto-switch kept
    assert dm._color_mode_combo.currentIndex() == 2


def test_s1f_other_rows_never_offer_as_authored(qapp, monkeypatch):
    seen, dm = _drive_dm(monkeypatch, "Wall")
    assert seen == [False]
    assert pd.load_paper_categories(dm._settings)["Wall"]["color"] != AS_AUTHORED
