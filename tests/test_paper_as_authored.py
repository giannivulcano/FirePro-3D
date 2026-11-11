"""paper-as-authored guards (design 2026-11-11-paper-as-authored-design.md)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d import paper_display as pd
from firepro3d.constants import TOKEN_AUTO, TOKEN_BG
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.test_lt1_block_paper import (_HALF_LEN, _block_strokes, _crop, _export,
                                        _render_model)
from tests.wm3_support import (AUTHORED, BOXES, OVR, box_colours,
                               composite_scene, pdf_colours, rgb)

_TOGGLED = [k for k in pd._CATEGORY_KEYS if k not in pd._LW_ONLY]


# -- D2 / D3: rows and factory ------------------------------------------------

def test_underlay_row_in_drafting_and_hatch_has_no_toggle():
    assert pd._CATEGORY_KEYS[-3:] == ["Hatch", "Blocks", "Underlay"]
    f = pd.factory_paper_categories()
    assert "as_authored" not in f["Hatch"]
    assert f["Underlay"] == {"color": TOKEN_AUTO, "fill": None, "section_color": None,
                             "line_weight": None, "opacity": 100, "visible": True,
                             "as_authored": True}


def test_factory_rows_on_with_tokens():
    f = pd.factory_paper_categories()
    for k in _TOGGLED:
        assert f[k]["as_authored"] is True, k
        assert f[k]["color"] == TOKEN_AUTO, k
    assert f["Wall"]["fill"] == TOKEN_BG and f["Wall"]["section_color"] == TOKEN_AUTO
    assert f["Pipe"]["fill"] is None


def test_fresh_settings_load_every_row_on():
    cats = pd.load_paper_categories()
    assert all(cats[k]["as_authored"] is True for k in _TOGGLED)


# -- D4: legacy mapping ----------------------------------------------------------

@pytest.mark.parametrize("mode,rows,und", [
    ("full_color", True, True), ("custom", False, True), ("bw", False, False),
    (None, False, False), ("garbage", False, False)])
def test_legacy_as_authored_table(mode, rows, und):
    assert pd.legacy_as_authored(mode) == (rows, und)


@pytest.mark.parametrize("mode,rows,und", [
    ("full_color", True, True), ("custom", False, True), ("bw", False, False)])
def test_project_load_maps_legacy_mode(mode, rows, und):
    pd.apply_paper_display_from_project(
        {"color_mode": mode, "categories": {"Pipe": {"color": "#00aa00"}}})
    cats = pd.load_paper_categories()
    assert cats["Pipe"]["color"] == "#00aa00"          # stored colours kept
    assert all(cats[k]["as_authored"] is rows for k in _TOGGLED if k != "Underlay")
    assert cats["Underlay"]["as_authored"] is und
    assert cats["Underlay"]["color"] == TOKEN_AUTO      # backfilled (D4)


def test_project_without_paper_display_is_bw():
    pd.apply_paper_display_from_project(None)
    cats = pd.load_paper_categories()
    assert not any(cats[k]["as_authored"] for k in _TOGGLED)


def test_stored_per_row_value_beats_legacy_mode():
    pd.apply_paper_display_from_project(
        {"color_mode": "bw", "categories": {"Pipe": {"as_authored": True}}})
    cats = pd.load_paper_categories()
    assert cats["Pipe"]["as_authored"] is True and cats["Wall"]["as_authored"] is False


def test_save_never_writes_color_mode():
    out = pd.get_paper_display_for_save()
    assert "color_mode" not in out
    assert out["categories"]["Pipe"]["as_authored"] is True


# -- D5: QSettings migrates once --------------------------------------------------

@pytest.mark.parametrize("mode,rows,und", [
    ("full_color", True, True), ("custom", False, True), ("bw", False, False)])
def test_qsettings_legacy_key_migrates_once(mode, rows, und):
    s = QSettings("GV", "FirePro3D")
    s.setValue("paper/color_mode", mode)
    s.setValue("paper/categories/Pipe/color", "#123456")
    s.sync()
    cats = pd.load_paper_categories(s)
    assert cats["Pipe"]["color"] == "#123456"
    assert cats["Pipe"]["as_authored"] is rows and cats["Underlay"]["as_authored"] is und
    assert s.value("paper/color_mode") is None                       # removed
    assert pd._parse_bool(s.value("paper/categories/Pipe/as_authored")) is rows


def test_qsettings_string_booleans_parse():
    s = QSettings("GV", "FirePro3D")
    s.setValue("paper/categories/Wall/as_authored", "false")
    s.sync()
    assert pd.load_paper_categories(s)["Wall"]["as_authored"] is False


# =====================================================================
# Task 3: the per-row paper pass (D6, R6, ruling 6)
# =====================================================================

_ROW = "#00aa00"        # a paper row colour no authored component uses
_MODEL = "#00ff00"      # Model "Blocks" colour


def _set_row(key, *, on, colour=_ROW):
    cats = pd.load_paper_categories()
    cats[key]["as_authored"] = on
    cats[key]["color"] = colour
    pd.save_paper_categories(cats)


def _paper_render(ms, scale=0.02):
    """The model scene rendered inside a real paper pass: ``_render_model``
    pixels (400 x 400 on black, the wm3_support boxes) with the paper hooks
    live -- the WM3 S1 guard shape (78eeeac8)."""
    saved = pd.apply_paper_overrides(ms, _crop(scale), paper_scale=scale)
    try:
        return _render_model(ms)
    finally:
        pd.restore_model_display(saved)


@pytest.fixture(autouse=True)
def _reset_model_blocks():
    pd.set_model_blocks_colour(None)
    yield
    pd.set_model_blocks_colour(None)


# -- AC2: Blocks row ---------------------------------------------------------------

def test_ac2_blocks_on_plots_authored_and_placement_colours(qapp, shipped_hatches, tmp_path):
    _set_row("Blocks", on=True)
    ms, _ = composite_scene(shipped_hatches)
    img = _paper_render(ms)
    assert box_colours(img, BOXES["circle"]) == {AUTHORED["circle"]}
    assert box_colours(img, BOXES["deflector"]) == {AUTHORED["deflector"]}
    ov, _ = composite_scene(shipped_hatches, {"colour": OVR})
    assert box_colours(_paper_render(ov), BOXES["circle"]) == {OVR}
    strokes, _f = pdf_colours(_export(tmp_path, ms, 0.02, "on.pdf"))   # AC7 parity
    assert {rgb(AUTHORED["circle"]), rgb(AUTHORED["deflector"])} <= set(strokes)


def test_ac2_blocks_off_paints_row_colour(qapp, shipped_hatches, tmp_path):
    _set_row("Blocks", on=False)
    ms, _ = composite_scene(shipped_hatches, {"colour": OVR})
    img = _paper_render(ms)
    assert box_colours(img, BOXES["circle"]) == {_ROW}
    assert box_colours(img, BOXES["deflector"]) == {_ROW}
    strokes, _f = pdf_colours(_export(tmp_path, ms, 0.02, "off.pdf"))
    # Strokes / text in the row colour; the hatch pattern lines follow the
    # hatch rules (the placement override), exactly as B&W / Custom did.
    assert set(strokes) == {rgb(_ROW), rgb(OVR)}


@pytest.mark.parametrize("on,want", [(True, _MODEL), (False, _ROW)])
def test_ac2_by_category_follows_the_blocks_row(qapp, shipped_hatches, tmp_path, on, want):
    _set_row("Blocks", on=on)
    pd.set_model_blocks_colour(_MODEL)
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    assert box_colours(_paper_render(ms), BOXES["circle"]) == {want}
    assert set(pdf_colours(_export(tmp_path, ms, 0.02, "bc.pdf"))[0]) == {rgb(want)}


def test_ac2_by_category_factory_model_colour_is_black(qapp, shipped_hatches, tmp_path):
    _set_row("Blocks", on=True)                   # Model "Blocks" = factory Automatic
    ms, _ = composite_scene(shipped_hatches, {"colour": "by_category"})
    assert set(pdf_colours(_export(tmp_path, ms, 0.02, "f.pdf"))[0]) == {rgb("#000000")}


# -- AC2: Construction row (authored pen, token re-resolved on paper) -------------

@pytest.mark.parametrize("on,colour,want", [
    (True, "#ff00ff", (1.0, 0.0, 1.0)),
    (True, TOKEN_AUTO, (0.0, 0.0, 0.0)),          # canvas ink re-resolved on paper
    (False, "#ff00ff", (0.0, 2 / 3, 0.0)),        # the row colour #00aa00
])
def test_ac2_construction_row(qapp, tmp_path, on, colour, want):
    _set_row("Construction", on=on)
    ms = Model_Space()
    ms.addItem(LineItem(QPointF(-_HALF_LEN, 0), QPointF(_HALF_LEN, 0), colour))
    strokes = _block_strokes(_export(tmp_path, ms, 0.02, "c.pdf"), 0.02)
    assert strokes
    for _w, got in strokes:
        assert got == pytest.approx(want, abs=0.01), strokes


# -- AC4: Underlay row --------------------------------------------------------------

@pytest.mark.parametrize("on,want", [(True, "#ff0000"), (False, _ROW)])
def test_ac4_underlay_row(qapp, on, want):
    from tests.test_underlay_display import _paper_scene_setup
    _set_row("Underlay", on=on)
    # Both fixture layers draw the same line; colour both, or A-DOOR's
    # default #c0c0c0 paints over A-WALL's red.
    scene, _rec, group, rect = _paper_scene_setup(
        qapp, layer_overrides={"A-WALL": {"colour": "#ff0000"},
                               "A-DOOR": {"colour": "#ff0000"}})
    child = next(c for c in group.childItems() if c.data(1) == "A-WALL")
    before = child.pen().color().name()
    img = QImage(200, 200, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    saved = pd.apply_paper_overrides(scene, rect, paper_scale=0.02)
    try:
        assert child.pen().color().name() == want
        p = QPainter(img)                  # FX2: painted pixels, both branches
        scene.render(p, QRectF(0, 0, 200, 200), rect)
        p.end()
    finally:
        pd.restore_model_display(saved)
    assert child.pen().color().name() == before
    names = {QColor(img.pixel(x, y)).name() for x in range(200) for y in range(200)}
    assert want in names
    assert ({"#ff0000", _ROW} - {want}).isdisjoint(names)   # the other branch's colour is absent


# -- AC8: SVG symbols re-resolve token colour and fill on paper (R6) --------------

def _sprinkler_scene():
    ms = Model_Space()
    n = ms.add_node(0.0, 0.0)
    spr = ms.add_sprinkler(n)
    return ms, spr


@pytest.mark.parametrize("colour,fill,want", [
    ("#ff4444", TOKEN_BG, ("#ff4444", "#ffffff")),   # hex kept, token fill -> white
    (TOKEN_AUTO, "#123456", ("#000000", "#123456")), # token colour -> black, hex fill kept
    ("#ff4444", "#000000", None),                    # no token: no re-tint (canvas tint plots)
])
def test_ac8_svg_tokens_re_resolve_on_paper(qapp, monkeypatch, colour, fill, want):
    from firepro3d import display_manager as dm
    from firepro3d.colour_tokens import resolve_colour
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Sprinkler/color", colour)
    s.setValue("display/Sprinkler/fill", fill)
    s.sync()
    _set_row("Sprinkler", on=True)
    ms, spr = _sprinkler_scene()
    dm.apply_saved_display_settings(ms)              # the canvas tint, as at load
    seen = []
    real = dm._set_svg_tint

    def spy(it, c, f=None):
        if it is spr:
            # resolved now, inside the pass: the surface the tint is built for
            seen.append((resolve_colour(c).name() if c else c,
                         resolve_colour(f).name() if f else f))
        real(it, c, f)

    monkeypatch.setattr(dm, "_set_svg_tint", spy)
    saved = pd.apply_paper_overrides(ms, QRectF(-500, -500, 1000, 1000), paper_scale=0.02)
    try:
        assert seen == ([] if want is None else [want])
    finally:
        pd.restore_model_display(saved)


# =====================================================================
# Task 4: colour tokens (D7, R1)
# =====================================================================

from firepro3d import colour_tokens as ct          # noqa: E402
from firepro3d.constants import TOKEN_ACCENT       # noqa: E402
from firepro3d import theme as th                  # noqa: E402


def test_background_token_is_pickable_and_labelled():
    assert ct.picked_colour(TOKEN_BG) == TOKEN_BG
    assert ct.token_label(TOKEN_BG) == "Background"
    assert ct.colour_from_label("Background") == TOKEN_BG
    assert ct.picked_colour("token:blocks") is None      # still internal


def test_background_resolves_canvas_bg_on_screen_white_on_paper(qapp):
    from firepro3d.text_item import TextAnnotationData, TextItem
    assert ct.resolve_colour(TOKEN_BG).name() == QColor(th.detect().canvas_bg).name()
    paper = Model_Space()
    paper.paints_on_paper = True     # what PaperScene sets (tests/test_section_sheet_plot.py idiom)
    t = TextItem(TextAnnotationData(text="x", x=0, y=0, height_mm=3, color=TOKEN_BG))
    paper.addItem(t)
    assert ct.resolve_colour(TOKEN_BG, item=t).name() == "#ffffff"
    with_pass = Model_Space()
    t2 = TextItem(TextAnnotationData(text="y", x=0, y=0, height_mm=3, color=TOKEN_BG))
    with_pass.addItem(t2)
    saved = pd.apply_paper_overrides(with_pass, QRectF(-50, -50, 100, 100))
    try:
        assert ct.resolve_colour(TOKEN_BG, item=t2).name() == "#ffffff"
    finally:
        pd.restore_model_display(saved)


@pytest.mark.parametrize("rows_on", [True, False])
def test_ac9_accent_text_plots_the_accent_on_paper(qapp, tmp_path, rows_on):
    """R1: an unrowed item (TextItem) in Accent plots the light-theme accent
    whatever the rows' toggles; the Construction line beside it follows its row."""
    from tests.test_hf1_token_render import _scene_with_line_and_text
    from tests.test_lt1_block_paper import _text_fills
    _set_row("Construction", on=rows_on, colour="#000000")
    pdf = _export(tmp_path, _scene_with_line_and_text(TOKEN_ACCENT), 0.02, "a.pdf")
    acc = QColor(th.LIGHT.accent)
    want_acc = (acc.redF(), acc.greenF(), acc.blueF())
    fills = _text_fills(pdf)
    assert fills and all(f == pytest.approx(want_acc, abs=0.01) for f in fills)
    want_line = want_acc if rows_on else (0.0, 0.0, 0.0)
    for _w, got in _block_strokes(pdf, 0.02):
        assert got == pytest.approx(want_line, abs=0.01)


# -- AC8 pixel backing: the spy above is a call-shape proxy -------------------------

def _sprinkler_paper_pixels(colour, fill):
    from firepro3d import display_manager as dm
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Sprinkler/color", colour)
    s.setValue("display/Sprinkler/fill", fill)
    s.sync()
    _set_row("Sprinkler", on=True)
    ms, spr = _sprinkler_scene()
    dm.apply_saved_display_settings(ms)
    rect = QRectF(-300, -300, 600, 600)
    img = QImage(200, 200, QImage.Format.Format_ARGB32)
    img.fill(QColor("#00cc00"))        # not white: a white fill must show against it
    saved = pd.apply_paper_overrides(ms, rect, paper_scale=0.02)
    try:
        p = QPainter(img)
        ms.render(p, QRectF(0, 0, 200, 200), rect)
        p.end()
    finally:
        pd.restore_model_display(saved)
    return {QColor(img.pixel(x, y)).name()
            for x in range(200) for y in range(200)}, ms


def test_ac8_pixels_token_fill_plots_white(qapp):
    names, _ms = _sprinkler_paper_pixels("#ff4444", TOKEN_BG)
    assert "#ffffff" in names          # Background fill -> white on paper
    assert "#ff4444" in names          # hex colour keeps its canvas value


def test_ac8_pixels_token_colour_plots_black(qapp):
    names, _ms = _sprinkler_paper_pixels(TOKEN_AUTO, "#123456")
    assert "#000000" in names          # Automatic stroke -> black on paper
    assert "#123456" in names          # hex fill keeps its canvas value
    assert "#ffffff" not in names


# -- G1 review fixes (F1, F3, F4) ---------------------------------------------------

def test_underlay_off_token_layer_paints_row_colour_and_src_restored(qapp):
    """F1: a token layer colour would ignore the row colour at paint; the pass
    drops it while the Underlay row is OFF and restores it afterwards."""
    from tests.test_underlay_display import _paper_scene_setup
    _set_row("Underlay", on=False)
    scene, _rec, group, rect = _paper_scene_setup(
        qapp, layer_overrides={"A-WALL": {"colour": "token:accent"}})
    kids = [c for c in group.childItems() if hasattr(c, "set_colour_src")]
    assert kids
    for c in kids:
        c.set_colour_src("token:accent")
    img = QImage(200, 200, QImage.Format.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    saved = pd.apply_paper_overrides(scene, rect, paper_scale=0.02)
    try:
        p = QPainter(img)
        scene.render(p, QRectF(0, 0, 200, 200), rect)
        p.end()
    finally:
        pd.restore_model_display(saved)
    names = {QColor(img.pixel(x, y)).name()
             for x in range(200) for y in range(200)}
    assert _ROW in names
    assert all(c._colour_src == "token:accent" for c in kids)


def test_legacy_project_migration_leaves_no_color_mode_and_no_hatch_toggle():
    """F3 / F4: the project path never writes paper/color_mode, and Hatch
    (LW only) never gains as_authored."""
    pd.apply_paper_display_from_project({"color_mode": "custom"})
    assert QSettings("GV", "FirePro3D").value("paper/color_mode") is None
    assert "as_authored" not in pd.load_paper_categories()["Hatch"]


def test_legacy_qsettings_migration_has_no_hatch_toggle():
    """F4: the QSettings migration path leaves Hatch without as_authored."""
    s = QSettings("GV", "FirePro3D")
    s.setValue("paper/color_mode", "full_color")
    s.sync()
    assert "as_authored" not in pd.load_paper_categories(s)["Hatch"]
