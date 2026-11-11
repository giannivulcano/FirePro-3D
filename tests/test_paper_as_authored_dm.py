"""paper-as-authored Display Manager guards (AC1, AC5, AC6, AC7)."""
import re
from pathlib import Path

import pytest
from PyQt6.QtGui import QColor

from firepro3d import paper_display as pd
from firepro3d import theme as th
from firepro3d.constants import TOKEN_AUTO, TOKEN_BG
from firepro3d.display_manager import DisplayManager, _CATEGORY_MAP
from firepro3d.model_space import Model_Space
from firepro3d.ui_kit import AsAuthoredToggle, EyeToggle
from tests._mainwindow_helpers import dispose_main_window


def _grab_colours(w):
    img = w.grab().toImage()
    return {QColor(img.pixel(x, y)).name()
            for y in range(img.height()) for x in range(img.width())}


# The kit's EyeToggle tests (tests/test_ui_kit_dm_cells.py) apply no QSS either:
# the glyph paints from the live theme, not a stylesheet.
def test_glyph_is_the_eyes_twin_and_paints_accent_only_when_on(qapp):
    on, off = AsAuthoredToggle(checked=True), AsAuthoredToggle(checked=False)
    assert isinstance(on, EyeToggle) and on.size() == EyeToggle().size()
    on.show(); off.show(); qapp.processEvents()
    acc = th.detect().color("accent").name()
    assert acc in _grab_colours(on)
    assert acc not in _grab_colours(off)
    on.setChecked(False); qapp.processEvents()
    assert acc not in _grab_colours(on)


# -- Task 7: the Paper Space tab (AC1, AC6) ---------------------------------------

def _dm(qapp):
    return DisplayManager(Model_Space())


def test_ac1_every_row_but_hatch_has_the_glyph_left_of_colour(qapp):
    dlg = _dm(qapp)
    assert dlg._ps_tree.headerItem().text(dlg._PS_COL_AUTH) == "AS AUTH."
    assert dlg._PS_COL_AUTH == dlg._PS_COL_COLOR - 1
    # Loop the pass's registry, not the built rows: a category the pass
    # paints but the tab never shows has an unreachable toggle (VC9 FX1).
    for key in pd._CATEGORY_KEYS:
        assert key in dlg._paper_cat_data, f"{key}: no Paper Space row"
        w = dlg._paper_cat_data[key]
        if key in pd._LW_ONLY:
            assert w.get("auth") is None
            continue
        assert isinstance(w["auth"], AsAuthoredToggle), key
        host = dlg._ps_tree.itemWidget(w["tree_item"], dlg._PS_COL_AUTH)
        assert w["auth"] in host.findChildren(AsAuthoredToggle)
        assert w["auth"].toolTip() == (       # D8 tooltip text, verbatim (FX3)
            "As Authored: plot this row's items in their own colours "
            "(off = paint the row colours over them)"), key
    dlg.reject()


def test_construction_row_toggle_reaches_the_pass(qapp):
    """VC9 FX1: a legacy B&W load sets Construction OFF; the row's glyph is
    the only way back ON short of Reset All."""
    pd.apply_paper_display_from_project({"color_mode": "bw"})
    dlg = _dm(qapp)
    w = dlg._paper_cat_data["Construction"]
    assert not w["auth"].isChecked() and w["color_btn"].isEnabled()
    w["auth"].click()                                       # real input path
    assert not w["color_btn"].isEnabled()
    assert pd.load_paper_categories()["Construction"]["as_authored"] is True
    dlg.accept()


def test_ac1_on_greys_chips_off_makes_them_live_and_persists(qapp):
    dlg = _dm(qapp)
    w = dlg._paper_cat_data["Wall"]
    assert w["auth"].isChecked()
    assert not (w["color_btn"].isEnabled() or w["fill_btn"].isEnabled()
                or w["section_btn"].isEnabled())
    w["auth"].click()                                       # real input path
    assert w["color_btn"].isEnabled() and w["fill_btn"].isEnabled() and w["section_btn"].isEnabled()
    assert pd.load_paper_categories()["Wall"]["as_authored"] is False
    dlg.accept()


def test_ac1_underlay_row_toggle_and_colour_only(qapp):
    dlg = _dm(qapp)
    w = dlg._paper_cat_data["Underlay"]
    for k in ("vis", "fill_btn", "section_btn", "lw_combo", "opacity"):
        assert not w[k].isEnabled(), k
    assert w["auth"].isEnabled()
    w["auth"].click()
    assert w["color_btn"].isEnabled()
    assert "Underlay" in dlg._PS_GROUPS["Drafting"]
    dlg.reject()


def test_cancel_restores_toggles_and_reset_is_factory(qapp):
    dlg = _dm(qapp)
    dlg._paper_cat_data["Pipe"]["auth"].click()
    dlg.reject()
    assert pd.load_paper_categories()["Pipe"]["as_authored"] is True
    dlg = _dm(qapp)
    dlg._paper_cat_data["Pipe"]["auth"].click()
    dlg._reset_paper_space_tab()
    assert dlg._paper_cat_data["Pipe"]["auth"].isChecked()
    assert pd.load_paper_categories()["Pipe"]["as_authored"] is True
    dlg.reject()


def test_colour_pick_flips_nothing(qapp, monkeypatch):
    from firepro3d import colour_picker
    dlg = _dm(qapp)
    dlg._paper_cat_data["Pipe"]["auth"].click()            # OFF: chip live
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: "#123456")
    dlg._on_paper_color_clicked("Pipe", "color")
    dlg._on_paper_color_clicked("Wall", "color")           # an ON row: must stay ON
    cats = pd.load_paper_categories()
    assert cats["Pipe"]["color"] == "#123456" and cats["Pipe"]["as_authored"] is False
    assert cats["Wall"]["color"] == "#123456"
    assert cats["Wall"]["as_authored"] is True               # no global switch
    dlg.accept()


def test_ac6_new_project_factory_on_both_tabs(qapp):
    cats = pd.load_paper_categories()
    assert all(cats[k]["as_authored"] for k in pd._CATEGORY_KEYS if k not in pd._LW_ONLY)
    assert cats["Wall"]["color"] == TOKEN_AUTO and cats["Wall"]["fill"] == TOKEN_BG
    assert _CATEGORY_MAP["Hydraulic Badge"]["color"] == TOKEN_AUTO
    assert {_CATEGORY_MAP[k]["fill"] for k in ("Sprinkler", "Water Supply", "Hydraulic Badge")} == {TOKEN_BG}
    assert _CATEGORY_MAP["Wall"]["color"] == "#666666"      # every other Model factory unchanged


@pytest.fixture()
def mw(qapp, tmp_path, monkeypatch):
    """Fresh MainWindow (mirrors tests/test_detail_new_project_leak.py)."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import main as main_mod
    from firepro3d.view_3d import View3D
    from firepro3d import snap_engine
    main_mod.View3D = View3D
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = main_mod.MainWindow()
    yield w
    dispose_main_window(w)
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def test_ac6_a_row_set_off_opens_a_new_project_off(mw):
    """The entry point: File > New, then the Display Manager on the new scene."""
    cats = pd.load_paper_categories()
    cats["Pipe"]["as_authored"] = False
    pd.save_paper_categories(cats)
    mw._modified = False                  # no unsaved-changes prompt
    mw.new_file()
    dlg = DisplayManager(mw.scene, mw)
    try:
        assert not dlg._paper_cat_data["Pipe"]["auth"].isChecked()
        assert dlg._paper_cat_data["Wall"]["auth"].isChecked()
    finally:
        dlg.reject()


# -- Task 8: Background in the picker (AC5) ---------------------------------------

def test_ac5_picker_offers_background(qapp):
    from firepro3d.colour_picker import ColourPickerDialog
    dlg = ColourPickerDialog(initial="#ff0000")
    values = [c.value for c in dlg._theme_row_chips]
    assert values == ["token:auto", "token:accent", TOKEN_BG]
    dlg._theme_row_chips[2].picked.emit(TOKEN_BG)
    dlg.accept()
    assert dlg.result_value() == TOKEN_BG


# -- Task 9: the retired API is gone (AC7) ------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]


def test_ac7_retired_colour_mode_api_is_gone():
    """The deliverable is the removal itself, so source text is the ground truth.

    Allow-list: a legacy-input READ of ``color_mode`` (``data.get("color_mode")``,
    the QSettings ``paper/color_mode`` key read/removed for migration) is not a
    write; only the retired API names and ``setValue(.. paper/color_mode)`` /
    a ``"color_mode":`` dict entry are forbidden."""
    pat = re.compile(r"PaperColorMode|load_paper_color_mode|save_paper_color_mode"
                     r"|paper_pass_color_mode|_PASS_COLOR_MODE|_color_mode_combo")
    hits = [f"{p.relative_to(_ROOT)}:{i}"
            for p in [*(_ROOT / "firepro3d").rglob("*.py"), _ROOT / "main.py"]
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if pat.search(line)]
    assert hits == []
    writes = [p for p in (_ROOT / "firepro3d").rglob("*.py")
              if re.search(r"setValue\([^)]*paper/color_mode", p.read_text(encoding="utf-8"))
              or re.search(r"[\"']color_mode[\"']\s*:", p.read_text(encoding="utf-8"))]
    assert writes == []
