"""WM3 G1 / G2 / G4 / G8 / G9 + R3 / R4 -- placement Colour on canvas pixels and parsed PDF.

Expected colours cite their raw source: ``wm3_support.AUTHORED`` (the authored
data), ``OVR`` (the picked colour), the theme ink (``token:auto`` on canvas),
the paper "Blocks" category colour, ``block_definition._PLACEHOLDER_COLOR``.
The "twin" is the same block AUTHORED in one colour: a recoloured placement
must render / plot exactly like it (Phase 3 ruling: fills and hatches follow
the hatch / paper rules as an authored fill of that colour)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from firepro3d import theme
from firepro3d.block_definition import _PLACEHOLDER_COLOR, BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.paper_display import load_paper_categories
from tests.paper_mode_shim import BW, CUSTOM, FULL_COLOR, set_paper_mode
from tests.test_lt1_block_paper import _export, _render_model
from tests.wm2_support import nested_record, scene_with
from tests.wm3_support import (AUTHORED, BOXES, OVR, box_colours, composite_defs,
                               composite_scene, lit_outside_origin, pdf_colours,
                               rgb)


_TEXTFILL = AUTHORED["textfill"]   # R3: the "H" box fill never takes the override
_MODES = [FULL_COLOR, BW, CUSTOM]


def _authored(comp):
    v = AUTHORED[comp]
    return QColor(theme.detect().ink).name() if v == "token:auto" else v


def _want(comp, colour=None):
    """Colours *comp*'s box shows: *colour* (the override) or the authored
    one; the "text" box also shows the box fill, always authored (R3)."""
    c = {colour or _authored(comp)}
    return c | {_TEXTFILL} if comp == "text" else c


def _count(img, box, name):
    x0, y0, x1, y1 = box
    return sum(1 for x in range(x0, x1) for y in range(y0, y1)
               if QColor(img.pixel(x, y)).name() == name)


# -- G1: canvas ----------------------------------------------------------------

def test_g1_as_authored_keeps_every_component(qapp, shipped_hatches):
    ms, _ = composite_scene(shipped_hatches)
    img = _render_model(ms)
    for comp, box in BOXES.items():
        assert box_colours(img, box) == _want(comp), comp


def test_g1_colour_replaces_every_component(qapp, shipped_hatches):
    ms, _ = composite_scene(shipped_hatches, {"colour": OVR})
    twin, _ = composite_scene(shipped_hatches, colour=OVR)
    img = _render_model(ms)
    for comp, box in BOXES.items():
        assert box_colours(img, box) == _want(comp, OVR), comp
    assert lit_outside_origin(img) == {OVR, _TEXTFILL}  # leader, end block, dots too
    assert img == _render_model(twin)                  # every pixel


def test_r3_text_box_fill_keeps_its_colour_on_canvas(qapp, shipped_hatches):
    """R3 (user ruling 2026-11-10): glyphs, border and leader take the
    override; the text's box fill keeps its authored colour, pixel for pixel."""
    plain, _ = composite_scene(shipped_hatches)
    ms, _ = composite_scene(shipped_hatches, {"colour": OVR})
    a, b = _render_model(plain), _render_model(ms)
    box = BOXES["text"]
    assert box_colours(a, box) == {AUTHORED["text"], _TEXTFILL}
    assert box_colours(b, box) == {OVR, _TEXTFILL}           # glyph + border grey
    assert _count(b, box, _TEXTFILL) == _count(a, box, _TEXTFILL) > 0


# -- G2: parsed PDF ------------------------------------------------------------

@pytest.mark.parametrize("mode", _MODES)
def test_g2_pdf_colour_plots_as_the_authored_twin(qapp, shipped_hatches, tmp_path, mode):
    set_paper_mode(mode)
    ms, _ = composite_scene(shipped_hatches, {"colour": OVR})
    twin, _ = composite_scene(shipped_hatches, colour=OVR)
    plain, _ = composite_scene(shipped_hatches)
    got = pdf_colours(_export(tmp_path, ms, 0.02, "o.pdf"))
    authored = pdf_colours(_export(tmp_path, plain, 0.02, "p.pdf"))
    assert got == pdf_colours(_export(tmp_path, twin, 0.02, "t.pdf"))
    assert got != authored                                         # composition
    strokes, fills = got
    assert sum(strokes.values()) == sum(authored[0].values())      # nothing dropped
    assert sum(fills.values()) == sum(authored[1].values())
    if mode is FULL_COLOR:
        assert set(strokes) == {rgb(OVR)}
        assert set(fills) == {rgb(OVR), rgb(_TEXTFILL)}
    else:
        paper = rgb(load_paper_categories()["Blocks"]["color"])
        # B&W / Custom stay above: strokes / text / end fills in the paper
        # "Blocks" colour; the block fill and the hatch follow the hatch rules
        # (OVR); the text-box fill keeps its authored colour (R3).
        assert set(strokes) == {paper, rgb(OVR)}
        assert set(fills) == {paper, rgb(OVR), rgb(_TEXTFILL)}


@pytest.mark.parametrize("mode", _MODES)
def test_r3_text_box_fill_keeps_its_colour_in_pdf(qapp, shipped_hatches, tmp_path, mode):
    set_paper_mode(mode)
    plain, _ = composite_scene(shipped_hatches)
    ms, _ = composite_scene(shipped_hatches, {"colour": OVR})
    a = pdf_colours(_export(tmp_path, plain, 0.02, "a.pdf"))[1]
    b = pdf_colours(_export(tmp_path, ms, 0.02, "b.pdf"))[1]
    assert a[rgb(_TEXTFILL)] == b[rgb(_TEXTFILL)] == 1


# -- G4: nested outer wins -----------------------------------------------------

def test_g4_nested_record_alone_recolours_its_child(qapp, shipped_hatches):
    ms, _ = composite_scene(shipped_hatches, host_rec_ov={"colour": OVR})
    twin, _ = composite_scene(shipped_hatches, colour=OVR)
    assert _render_model(ms) == _render_model(twin)


def test_g4_as_authored_outer_shows_nested_record(qapp, shipped_hatches):
    ms, _ = composite_scene(shipped_hatches, host_rec_ov={"colour": "#808000"})
    twin, _ = composite_scene(shipped_hatches, colour="#808000")
    assert _render_model(ms) == _render_model(twin)


def test_g4_outer_placement_beats_nested_record(qapp, shipped_hatches):
    ms, _ = composite_scene(shipped_hatches, {"colour": OVR},
                            host_rec_ov={"colour": "#808000"})
    twin, _ = composite_scene(shipped_hatches, colour=OVR)
    assert _render_model(ms) == _render_model(twin)


def test_g4_outer_record_beats_inner_record(qapp, shipped_hatches):
    end, lt, d = composite_defs()
    mid = BlockDefinition.new(name="Mid", library="L", series="S",
                              primitives=[nested_record(d.id, {"colour": "#808000"})],
                              origin=(0.0, 0.0))
    top = BlockDefinition.new(name="Top", library="L", series="S",
                              primitives=[nested_record(mid.id, {"colour": OVR})],
                              origin=(0.0, 0.0))
    ms, inst = scene_with([end, lt, d, mid, top], top.id)
    shipped_hatches(ms)
    inst.update()
    twin, _ = composite_scene(shipped_hatches, colour=OVR)
    assert _render_model(ms) == _render_model(twin)


def test_g4_as_authored_record_keeps_inner_record(qapp, shipped_hatches):
    """R4 (user ruling 2026-11-10): an As Authored record ABOVE a coloured
    record keeps the inner colour on everything -- bound text included
    (before R4 the bound "@[Tag]" kept its authored colour here)."""
    end, lt, d = composite_defs()
    mid = BlockDefinition.new(name="Mid", library="L", series="S",
                              primitives=[nested_record(d.id, {"colour": OVR})],
                              origin=(0.0, 0.0))
    top = BlockDefinition.new(name="Top", library="L", series="S",
                              primitives=[nested_record(mid.id)], origin=(0.0, 0.0))
    ms, inst = scene_with([end, lt, d, mid, top], top.id)
    shipped_hatches(ms)
    inst.update()
    twin, _ = composite_scene(shipped_hatches, colour=OVR)
    img = _render_model(ms)
    assert box_colours(img, BOXES["bound"]) == {OVR}
    assert img == _render_model(twin)


# -- G8: imported reference linework (Q2) --------------------------------------

def _ref_host():
    ref = BlockDefinition.reference_from_geoms(
        [{"kind": "line", "layer": "A", "color": "#ff0000",
          "x1": -1500.0, "y1": -100.0, "x2": 1500.0, "y2": -100.0}], name="Ref")
    ln = LineItem(QPointF(-1500, 100), QPointF(1500, 100))
    ln.style["colour"] = "#ff8000"
    rec = ln.to_dict()
    rec["reference"] = True                     # printed reference (RG4)
    rec["printed"] = True
    host = BlockDefinition.new(name="Host", library="L", series="S",
                               primitives=[nested_record(ref.id), rec],
                               origin=(0.0, 0.0))
    return [ref, host], host.id


def _band(img, y0, y1):
    return {QColor(img.pixel(x, y)).name() for x in range(img.width())
            for y in range(y0, y1)} - {"#000000"}


def _thickness(img, x, y0, y1):
    return sum(1 for y in range(y0, y1) if QColor(img.pixel(x, y)).name() != "#000000")


def test_g8_imported_reference_linework_is_recoloured(qapp):
    defs, hid = _ref_host()
    plain, _ = scene_with(defs, hid)
    img = _render_model(plain)
    assert _band(img, 145, 156) == {"#ff0000"}      # the import's geom colour
    assert _band(img, 245, 256) == {"#ff8000"}      # the printed reference's style colour
    ms, _ = scene_with(defs, hid, {"colour": OVR, "weight": "Thickest"})
    img2 = _render_model(ms)
    assert _band(img2, 145, 156) == {OVR}
    assert _band(img2, 245, 256) == {OVR}
    # Q2: Weight still skips reference strokes -- same on-screen thickness.
    assert _thickness(img2, 320, 140, 161) == _thickness(img, 320, 140, 161)


def test_g8_imported_reference_linework_is_recoloured_in_pdf(qapp, tmp_path):
    """AC2 "(canvas + PDF)": probed As Authored Full Colour = one red stroke
    (the import) + one orange (the printed reference), no fills."""
    set_paper_mode("full_color")
    defs, hid = _ref_host()
    plain, _ = scene_with(defs, hid)
    a = pdf_colours(_export(tmp_path, plain, 0.02, "a.pdf"))
    assert set(a[0]) == {rgb("#ff0000"), rgb("#ff8000")}
    ms, _ = scene_with(defs, hid, {"colour": OVR})
    strokes, fills = pdf_colours(_export(tmp_path, ms, 0.02, "b.pdf"))
    assert set(strokes) == {rgb(OVR)} and sum(strokes.values()) == sum(a[0].values())


# -- G9: the missing-nested placeholder is never recoloured (AC9) --------------

def test_g9_missing_nested_placeholder_is_never_recoloured(qapp):
    missing = {"type": "block_instance", "block_id": "deadbeef",
               "pos": [250.0, 250.0], "rotation": 0.0}
    d = BlockDefinition.new(name="Host", library="L", series="S",
                            primitives=[missing], origin=(0.0, 0.0))
    top = BlockDefinition.new(name="Top", library="L", series="S",
                              primitives=[nested_record(d.id, {"colour": OVR})],
                              origin=(0.0, 0.0))
    box = (270, 270, 380, 380)                       # model (250,250) +- 100 mm
    for ov in (None, {"colour": OVR}, {"colour": "by_category"}):
        ms, _ = scene_with([d], d.id, ov)
        assert box_colours(_render_model(ms), box) == {_PLACEHOLDER_COLOR}, ov
    ms, _ = scene_with([d, top], top.id)             # a nested record's colour too
    assert box_colours(_render_model(ms), box) == {_PLACEHOLDER_COLOR}
