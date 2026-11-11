"""WM3 Task 1 -- placement Colour data + op-level resolution (design D1 / D2)."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainterPath, QPen, QTransform

from firepro3d import colour_tokens as ct
from firepro3d import stroke_style as ss
from firepro3d.constants import (TOKEN_ACCENT, TOKEN_AUTO, TOKEN_BG, TOKEN_BLOCKS,
                                 TOKEN_ELEMENT)
from firepro3d.render_op import FILL, PATTERN, STROKE, TEXT, RenderOp, apply_overrides


def _ops():
    p = QPainterPath(QPointF(0, 0)); p.lineTo(10, 0)
    return [RenderOp(STROKE, p, pen=QPen(), weight="Thin", linetype="continuous",
                     colour="#ff0000"),
            RenderOp(STROKE, p, pen=QPen()),                  # reference stroke (weight None)
            RenderOp(TEXT, p, colour="#ff00ff"),
            RenderOp(FILL, p, colour="#ffff00"),
            RenderOp(PATTERN, p, colour="#00ffff", tile_ref="x"),
            RenderOp(STROKE, p, pen=QPen(), fixed=True)]      # missing-nested placeholder


def test_normalize_overrides_colour_axis():
    assert ss.normalize_overrides(None) == {"weight": "as_authored",
                                            "linetype": "as_authored",
                                            "colour": "as_authored"}
    assert ss.normalize_overrides({"colour": " #00FF00 "})["colour"] == "#00ff00"
    assert ss.normalize_overrides({"colour": "#0f0"})["colour"] == "#00ff00"
    for keep in ("as_authored", "by_category", TOKEN_AUTO, TOKEN_ACCENT,
                 TOKEN_BG):                      # paper-as-authored D7: Background is pickable
        assert ss.normalize_overrides({"colour": keep})["colour"] == keep


@pytest.mark.parametrize("bad", [None, 3, "", "  ", "#zz", "red", "by_linetype",
                                 "by_block", "continuous", TOKEN_ELEMENT,
                                 TOKEN_BLOCKS, "token:nope", "As Authored"])
def test_normalize_overrides_invalid_colour_is_as_authored(bad):
    assert ss.normalize_overrides({"colour": bad})["colour"] == ss.AS_AUTHORED


def test_is_as_authored_tests_all_three_axes():
    assert ss.is_as_authored({}) and ss.is_as_authored({"colour": ""})
    assert not ss.is_as_authored({"colour": "#00ff00"})
    assert not ss.is_as_authored({"colour": "by_category"})


def test_override_args_is_a_three_tuple():
    assert ss.override_args(None) == (None, None, None)
    assert ss.override_args({"weight": "Thick", "colour": "#00ff00"}) == (
        "Thick", None, "#00ff00")
    assert ss.override_args({"colour": "by_category"}) == (None, None, "by_category")


def test_compose_and_refs_with_colour():
    assert ss.compose_overrides({"colour": "#00ff00"},
                                {"colour": "#ff0000", "weight": "Thick"}) == {
        "weight": "Thick", "linetype": "as_authored", "colour": "#00ff00"}
    assert ss.compose_overrides({}, {"colour": "#ff0000"})["colour"] == "#ff0000"
    assert ss.override_refs({"colour": "#00ff00"}) == (set(), set())


def test_apply_overrides_colour_reaches_every_kind_but_fixed():
    ops = _ops()
    out = apply_overrides(ops, colour="#00ff00")
    assert [o.colour for o in out[:5]] == ["#00ff00"] * 5
    assert out[5] is ops[5]                                   # D2: placeholder untouched
    assert [o.colour for o in ops[:5]] == ["#ff0000", None, "#ff00ff", "#ffff00",
                                           "#00ffff"]         # flyweights never mutated
    assert out[0].weight == "Thin" and out[1].weight is None


def test_apply_overrides_colour_skips_a_text_box_fill():
    """R3 (user ruling 2026-11-10): a text's box fill keeps its authored
    colour; a block-level fill / pattern takes the override."""
    p = QPainterPath(QPointF(0, 0)); p.lineTo(10, 0)
    box = RenderOp(FILL, p, colour="#406080", keep_colour=True)
    block_fill = RenderOp(FILL, p, colour="#ffff00")
    out = apply_overrides([box, block_fill], colour="#00ff00")
    assert out[0] is box and out[1].colour == "#00ff00"
    assert box.mapped(QTransform.fromTranslate(5, 5)).keep_colour


def test_text_box_ops_marks_only_its_fill(qapp):
    from firepro3d.block_definition import text_box_ops
    from firepro3d.text_item import TextAnnotationData, TextItem
    t = TextItem(TextAnnotationData(text="H", height_mm=60.0, color="#ff00ff",
                                    border=True, fill_color="#406080"))
    under, over = text_box_ops(t, QTransform())
    assert [(o.kind, o.keep_colour) for o in under] == [(FILL, True)]
    assert all(not o.keep_colour for o in over)          # border takes the override


def test_apply_overrides_by_category_writes_token_blocks():
    out = apply_overrides(_ops(), colour="by_category")
    assert {o.colour for o in out[:5]} == {TOKEN_BLOCKS}


def test_apply_overrides_weight_still_skips_reference_and_fixed():
    ops = _ops()
    out = apply_overrides(ops, weight="Thick", colour="#00ff00")
    assert out[0].weight == "Thick"
    assert out[1].weight is None and out[1].colour == "#00ff00"   # Q2
    assert out[5] is ops[5]
    assert apply_overrides(ops) is ops


def test_fixed_survives_mapped_and_marks_the_placeholder():
    from firepro3d.block_definition import _placeholder_op
    assert _ops()[5].mapped(QTransform.fromTranslate(5, 5)).fixed
    assert _placeholder_op(QTransform()).fixed


def test_colour_token_helpers():
    assert ct.token_label(TOKEN_BLOCKS) is None              # internal
    assert ct.picked_colour("#00FF00") == "#00ff00"
    assert ct.picked_colour(QColor("#123456")) == "#123456"
    assert ct.picked_colour(TOKEN_BG) == TOKEN_BG            # paper-as-authored D7: pickable
    for bad in ("", None, TOKEN_BLOCKS, TOKEN_ELEMENT, "#zz", "red"):
        assert ct.picked_colour(bad) is None, bad
    assert ct.swatch_label("") == "None"
    assert ct.swatch_label(TOKEN_AUTO) == "Automatic"
    assert ct.swatch_label("#00ff00") == "#00FF00"
    assert ct.colour_from_label("Automatic") == TOKEN_AUTO
    assert ct.colour_from_label("Accent") == TOKEN_ACCENT
    assert ct.colour_from_label("#00FF00") == "#00ff00"
    assert ct.colour_from_label("As Authored") is None


def test_bound_prim_and_instance_args_are_three(qapp):
    from firepro3d.block_attributes import BoundPrim
    from tests.wm2_support import scene_with, sprinkler_def
    assert BoundPrim({}, None).override_args == (None, None, None)
    d = sprinkler_def()
    ms, inst = scene_with([d], d.id)
    assert inst._ov_args is None
    inst.set_overrides({"colour": "#00ff00"})
    assert inst._ov_args == (None, None, "#00ff00")
    inst.set_overrides({})
    assert inst._ov_args is None
