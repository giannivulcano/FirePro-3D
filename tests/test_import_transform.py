"""Ground-truth tests for the shared underlay import-transform helper.

`apply_import_transform` bakes an underlay's stored import transform
(base-point shift + uniform scale) into geometry dicts. It replaces four
byte-identical inline copies that lived in ``model_space.py`` — one of which
(the text branch) forgot to scale ``twidth``, so PDF text rendered with the
wrong horizontal fit on the canvas while the raw-rendered import preview looked
correct (TODO 71).
"""
import math

from firepro3d.dwg_converter import apply_import_transform


def test_identity_when_scale_1_and_no_shift():
    geoms = [{"kind": "line", "x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0}]
    out = apply_import_transform(geoms, 1.0, 0.0, 0.0)
    assert out[0] == geoms[0]


def test_does_not_mutate_input():
    geoms = [{"kind": "line", "x1": 1.0, "y1": 2.0, "x2": 3.0, "y2": 4.0}]
    apply_import_transform(geoms, 2.0, 1.0, 1.0)
    assert geoms[0]["x1"] == 1.0  # original untouched


def test_line_shift_then_scale():
    g = {"kind": "line", "x1": 10.0, "y1": 20.0, "x2": 30.0, "y2": 40.0}
    out = apply_import_transform([g], 2.0, 5.0, 5.0)[0]
    assert out["x1"] == (10 - 5) * 2
    assert out["y1"] == (20 - 5) * 2
    assert out["x2"] == (30 - 5) * 2
    assert out["y2"] == (40 - 5) * 2


def test_circle_scales_extent():
    g = {"kind": "circle", "x": 10.0, "y": 20.0, "w": 4.0, "h": 6.0}
    out = apply_import_transform([g], 3.0, 0.0, 0.0)[0]
    assert out["x"] == 30.0 and out["y"] == 60.0
    assert out["w"] == 12.0 and out["h"] == 18.0


def test_arc_scales_extent():
    g = {"kind": "arc", "rx": 1.0, "ry": 2.0, "rw": 4.0, "rh": 8.0,
         "start": 0.0, "span": 90.0}
    out = apply_import_transform([g], 2.0, 0.0, 0.0)[0]
    assert out["rx"] == 2.0 and out["ry"] == 4.0
    assert out["rw"] == 8.0 and out["rh"] == 16.0
    # non-geometric angle fields untouched
    assert out["start"] == 0.0 and out["span"] == 90.0


def test_ellipse_full_scales():
    g = {"kind": "ellipse_full", "pos_cx": 10.0, "pos_cy": 20.0,
         "x": 1.0, "y": 2.0, "w": 3.0, "h": 4.0}
    out = apply_import_transform([g], 2.0, 5.0, 5.0)[0]
    assert out["pos_cx"] == (10 - 5) * 2 and out["pos_cy"] == (20 - 5) * 2
    assert out["x"] == 2.0 and out["y"] == 4.0
    assert out["w"] == 6.0 and out["h"] == 8.0


def test_path_points_shift_then_scale():
    g = {"kind": "path_points", "points": [(10.0, 20.0), (30.0, 40.0)],
         "closed": True}
    out = apply_import_transform([g], 2.0, 5.0, 5.0)[0]
    assert out["points"] == [((10 - 5) * 2, (20 - 5) * 2),
                             ((30 - 5) * 2, (40 - 5) * 2)]
    assert out["closed"] is True


def test_text_scales_position_size_AND_twidth():
    """The bug fix: twidth must scale with s, matching size/x/y."""
    g = {"kind": "text", "x": 10.0, "y": 20.0, "size": 8.0,
         "twidth": 30.0, "text": "HELLO", "halign": 0, "valign": 3}
    s = 33.87
    out = apply_import_transform([g], s, 5.0, 5.0)[0]
    assert math.isclose(out["x"], (10 - 5) * s)
    assert math.isclose(out["y"], (20 - 5) * s)
    assert math.isclose(out["size"], 8.0 * s)
    # the previously-dropped field — without this, sx = twidth/nat_w breaks
    assert math.isclose(out["twidth"], 30.0 * s)
    # the x-fit ratio (twidth : size) is preserved, so aspect matches preview
    assert math.isclose(out["twidth"] / out["size"], g["twidth"] / g["size"])
    # non-geometric fields preserved verbatim
    assert out["text"] == "HELLO"
    assert out["halign"] == 0 and out["valign"] == 3


def test_text_twidth_none_is_safe():
    g = {"kind": "text", "x": 10.0, "y": 20.0, "size": 8.0,
         "twidth": None, "text": "x"}
    out = apply_import_transform([g], 2.0, 0.0, 0.0)[0]
    assert out["twidth"] is None
    assert out["size"] == 16.0


def test_text_missing_size_key_is_safe():
    g = {"kind": "text", "x": 10.0, "y": 20.0, "text": "x"}
    out = apply_import_transform([g], 2.0, 0.0, 0.0)[0]
    assert "size" not in out
    assert out["x"] == 20.0


def test_unknown_kind_passed_through_untouched():
    g = {"kind": "mystery", "foo": 1}
    out = apply_import_transform([g], 2.0, 5.0, 5.0)[0]
    assert out == g


# ── Render-level guard: the full chain (transform -> _append_geom_to_path) ──
# The pure-function tests above prove twidth scales; this proves the scaled
# twidth actually flows through the batched text-path builder so on-canvas text
# scales in BOTH axes (aspect preserved) at architectural import scales. Before
# the fix, twidth stayed raw, so the text path width did NOT scale with s while
# its height did -> horizontally-distorted text (TODO 71). Red-verified: with
# the old inline loops this asserts ~1.0 for the width ratio and fails.
def _text_path_size(scene, s):
    from PyQt6.QtGui import QPainterPath
    g = {"kind": "text", "layer": "PDF Text", "x": 0.0, "y": 0.0,
         "size": 8.0, "twidth": 40.0, "text": "HELLO", "halign": 0,
         "valign": 3}
    tg = apply_import_transform([g], s, 0.0, 0.0)[0]
    path = QPainterPath()
    scene._append_geom_to_path(path, tg)
    br = path.boundingRect()
    return br.width(), br.height()


def test_placed_text_scales_isotropically_with_import_scale(qapp):
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    w1, h1 = _text_path_size(scene, 1.0)
    w10, h10 = _text_path_size(scene, 10.0)
    assert w1 > 0 and h1 > 0
    # both axes scale by ~10x -> aspect ratio preserved (isotropic)
    assert math.isclose(w10 / w1, 10.0, rel_tol=0.02)
    assert math.isclose(h10 / h1, 10.0, rel_tol=0.02)
