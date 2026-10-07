"""WM2 Task 1 -- override keywords + helpers (design H1 / H2)."""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath, QPen
import pytest

from firepro3d import paper_display as pd
from firepro3d import stroke_style as ss
from firepro3d.render_op import RenderOp, STROKE, TEXT, apply_overrides


def _stroke(weight="by_linetype", linetype="continuous"):
    p = QPainterPath(QPointF(0, 0)); p.lineTo(10, 0)
    return RenderOp(STROKE, p, pen=QPen(), weight=weight, linetype=linetype)


def test_keywords_are_not_names_or_refs():
    for kw in (ss.AS_AUTHORED, ss.BY_CATEGORY):
        assert not ss.is_named_weight(kw)
        assert not ss.is_linetype_ref(kw)


def test_normalize_overrides_defaults_and_canonical():
    assert ss.normalize_overrides(None) == {"weight": "as_authored",
                                            "linetype": "as_authored"}
    old = pd.weight_aliases()
    pd.set_weight_aliases({"Old": "Thick"})
    try:
        assert ss.normalize_overrides({"weight": "Old"})["weight"] == "Thick"
    finally:
        pd.set_weight_aliases(old)
    assert ss.normalize_overrides({"weight": "by_category",
                                   "linetype": "abc"}) == {
        "weight": "by_category", "linetype": "abc"}


def test_override_args_and_refs_and_compose():
    assert ss.override_args(ss.normalize_overrides(None)) == (None, None)
    ov = {"weight": "Thick", "linetype": "lt1"}
    assert ss.override_args(ov) == ("Thick", "lt1")
    assert ss.override_refs(ov) == ({"Thick"}, {"lt1"})
    assert ss.override_refs({"weight": "by_category",
                             "linetype": "continuous"}) == (set(), set())
    outer = {"weight": "Thinnest", "linetype": "as_authored"}
    inner = {"weight": "Thickest", "linetype": "lt1"}
    assert ss.compose_overrides(outer, inner) == {"weight": "Thinnest",
                                                  "linetype": "lt1"}


def test_canvas_weight_name_by_category_is_model_blocks():
    assert ss.canvas_weight_name(ss.BY_CATEGORY) == pd.model_blocks_weight()


def test_apply_overrides_replaces_strokes_only():
    p = QPainterPath(QPointF(0, 0)); p.lineTo(1, 1)
    ops = [_stroke(), RenderOp(TEXT, p, colour="#ffffff"),
           RenderOp(STROKE, p, pen=QPen())]          # placeholder: weight None
    assert apply_overrides(ops) is ops                 # no override -> same list
    out = apply_overrides(ops, weight="Thick", linetype="lt1")
    assert out is not ops and ops[0].weight == "by_linetype"   # never mutated
    assert (out[0].weight, out[0].linetype) == ("Thick", "lt1")
    assert out[1] is ops[1] and out[2] is ops[2]


@pytest.mark.parametrize("bad", [1.5, "  ", None, "by_linetype", "by_block",
                                 "continuous"])
def test_normalize_overrides_invalid_weight_is_as_authored(bad):
    assert ss.normalize_overrides({"weight": bad})["weight"] == ss.AS_AUTHORED


@pytest.mark.parametrize("bad", ["by_block", "by_category", 3, "", "  ",
                                 "by_linetype"])
def test_normalize_overrides_invalid_linetype_is_as_authored(bad):
    assert (ss.normalize_overrides({"linetype": bad})["linetype"]
            == ss.AS_AUTHORED)


def test_normalize_overrides_keeps_continuous_linetype_and_strips_weight():
    ov = ss.normalize_overrides({"weight": " Thick ", "linetype": "continuous"})
    assert ov == {"weight": "Thick", "linetype": "continuous"}


def test_is_as_authored_cases():
    assert ss.is_as_authored(None) and ss.is_as_authored({})
    assert not ss.is_as_authored({"weight": "Thick"})
    assert not ss.is_as_authored({"linetype": "lt1"})


def test_apply_overrides_one_axis_keeps_other():
    ops = [_stroke(weight="Thin", linetype="lt9")]
    w = apply_overrides(ops, weight="Thick")[0]
    assert (w.weight, w.linetype) == ("Thick", "lt9")
    lt = apply_overrides(ops, linetype="lt1")[0]
    assert (lt.weight, lt.linetype) == ("Thin", "lt1")


@pytest.mark.parametrize("name", ["As Authored", "by_category", "By Category",
                                  "as_authored"])
def test_keyword_names_are_reserved_weight_names(name):
    assert pd.validate_line_weight_name(name, []) is False
