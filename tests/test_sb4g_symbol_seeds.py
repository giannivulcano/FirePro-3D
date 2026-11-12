"""SB4g T4 -- the five shipped symbol seeds (design D9 / R1 / R14 / AC1).

Expected numbers come from the raw SVGs, never from the module under test:
every source has viewBox 0 0 20 20, and today's items map that box onto the
element's size -- heads and water supply 24 in = 609.6 mm (sprinkler.py /
water_supply.py TARGET_MM = 24.0 * 25.4), riser 150 mm
(constants.RISER_SYMBOL_SIZE_MM). K = size / 20, scene = (v - 10) * K after
the SVG's own transforms (no Y flip, DC1). R14: every stroke is By Linetype
and a thick SVG stroke becomes its centre line, so the extent is the
centre-line geometry extent."""
import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtSvg import QSvgRenderer

from firepro3d import block_library
from firepro3d.assets import asset_path, system_blocks_path
from firepro3d.block_definition import _PRIMITIVE_FACTORY, _local_path
from firepro3d.stroke_style import BY_LINETYPE

HEAD = 24.0 * 25.4
RISER = 150.0
KH, KR = HEAD / 20.0, RISER / 20.0
G = 0.22619051     # <g transform="translate(-G,-G)"> in sprinkler0 / sprinkler2 / water_supply.svg


def _h(v, shift=G):
    """Head / water-supply viewBox unit (before the group translate) -> scene mm."""
    return (v - shift - 10.0) * KH


# file, id, symbol_for, centre-line extent (raw SVG), primitive types, fill colours
SEEDS = [
    ("Sprinkler0.fpdb", "system-symbols-sprinkler0", "Sprinkler",
     2 * 9.51192 * KH,                                   # circle r (sprinkler0.svg)
     ["draw_circle", "draw_line", "draw_line"], ["#2e2e2e"]),
    ("Sprinkler1.fpdb", "system-symbols-sprinkler1", "Sprinkler",
     2 * 9.7560978 * KH,                                 # circle r (sprinkler1.svg)
     ["draw_circle"], ["#000000"]),
    ("Sprinkler2.fpdb", "system-symbols-sprinkler2", "Sprinkler",
     (20.226191 - 0.22619057) * KH,                      # the hairlines span the viewBox
     ["draw_circle"] + ["draw_line"] * 3 + ["draw_filled_region"] * 4,
     ["#000000", "#000000", "#ffffff", "#ffffff"]),      # path3..path6 fills
    ("Water Supply.fpdb", "system-symbols-watersupply", "Water Supply",
     2 * 9.51192 * KH,                                   # circle r (water_supply.svg)
     ["draw_circle", "draw_filled_region"], ["#2b2b2e"]),
    ("Riser.fpdb", "system-symbols-riser", "Riser",
     2 * 9.2852659 * KR,                                 # circle r (riser_passthrough.svg)
     ["draw_circle", "draw_spline"], []),
]
_IDS = [s[1] for s in SEEDS]

# Circles (cx, cy, r) and straight lines (pt1, pt2) in scene mm, from the raw SVG literals.
CIRCLES = {
    "Sprinkler0.fpdb": [(_h(10.226191), _h(10.226191), 9.51192 * KH)],
    "Sprinkler1.fpdb": [(_h(10.0, 0.0), _h(10.0, 0.0), 9.7560978 * KH)],
    "Sprinkler2.fpdb": [(_h(10.226191), _h(10.226191), 9.7442141 * KH)],
    "Water Supply.fpdb": [(_h(10.226191), _h(10.226191), 9.51192 * KH)],
    "Riser.fpdb": [((10.000001 - 10.0) * KR, (10.000001 - 10.0) * KR, 9.2852659 * KR)],
}
LINES = {
    # sprinkler0 path2: M 17.226191,17.226191 3.2261905,3.2261905 m 14.0000005,0 L 3.2261905,17.226191
    "Sprinkler0.fpdb": [((_h(17.226191), _h(17.226191)), (_h(3.2261905), _h(3.2261905))),
                        ((_h(17.226191), _h(3.2261905)), (_h(3.2261905), _h(17.226191)))],
    # sprinkler2 path2-8: m 10.231193,20.226191 -5e-6,-19.85507295 V 0.22619057
    # sprinkler2 path2:   M 0.22619057,10.231198 20.226191,10.231184
    "Sprinkler2.fpdb": [((_h(10.231193), _h(20.226191)), (_h(10.231188), _h(0.37111805))),
                        ((_h(10.231188), _h(0.37111805)), (_h(10.231188), _h(0.22619057))),
                        ((_h(0.22619057), _h(10.231198)), (_h(20.226191), _h(10.231184)))],
}


def _load(fname):
    return block_library.load_block_file(system_blocks_path("Symbols", fname))


def _prims(fname):
    return _load(fname).to_dict()["primitives"]


def _geom(p):
    """Centre-line geometry rect of one primitive record (block-local mm)."""
    it = _PRIMITIVE_FACTORY[p["type"]].from_dict(p)
    path = it.path() if p["type"] == "draw_filled_region" else it.mapToParent(_local_path(it))
    return path.boundingRect()


def _svg_ink(rel, el_id, k):
    """QSvgRenderer's ink rect of one SVG element (stroke included), in scene mm."""
    r = QSvgRenderer(asset_path(*rel))
    b = r.transformForElement(el_id).mapRect(r.boundsOnElement(el_id))
    return QRectF((b.x() - 10.0) * k, (b.y() - 10.0) * k, b.width() * k, b.height() * k)


@pytest.mark.parametrize("fname,bid,cat,extent,types,fills", SEEDS, ids=_IDS)
def test_seed_metadata(fname, bid, cat, extent, types, fills, qapp):
    d = _load(fname)
    assert d is not None, "does not load"
    assert (d.id, d.library, d.series, d.scale_mode, d.symbol_for, d.version) == \
        (bid, "System", "Symbols", "real_size", cat, 1)


@pytest.mark.parametrize("fname,bid,cat,extent,types,fills", SEEDS, ids=_IDS)
def test_seed_centre_line_extent_and_by_linetype(fname, bid, cat, extent, types, fills, qapp):
    """R14: centre-line extent from the raw SVG; every stroke By Linetype;
    primitive types in SVG order (empty paths dropped); literal fill colours."""
    prims = _prims(fname)
    assert [p["type"] for p in prims] == types
    assert all(p["style"]["weight"] == BY_LINETYPE for p in prims if p.get("style"))
    assert [p["fill"]["background"]["color"] for p in prims if p.get("fill")] == fills
    ext = QRectF()
    for op in _load(fname).render_ops_variant(False, 1.0):
        ext = ext.united(op.path.boundingRect())
    assert ext.width() == pytest.approx(extent, abs=0.01)
    assert ext.height() == pytest.approx(extent, abs=0.01)
    assert ext.center().x() == pytest.approx(0.0, abs=1e-3)
    assert ext.center().y() == pytest.approx(0.0, abs=1e-3)


@pytest.mark.parametrize("fname", [s[0] for s in SEEDS], ids=_IDS)
def test_seed_circles_and_lines_match_the_svg(fname, qapp):
    prims = _prims(fname)
    circles = [(p["cx"], p["cy"], p["radius"]) for p in prims if p["type"] == "draw_circle"]
    lines = [(tuple(p["pt1"]), tuple(p["pt2"])) for p in prims if p["type"] == "draw_line"]
    assert len(circles) == len(CIRCLES[fname])
    assert len(lines) == len(LINES.get(fname, []))
    for got, want in zip(circles, CIRCLES[fname]):
        assert got == pytest.approx(want, abs=0.01)
    for (g1, g2), (w1, w2) in zip(lines, LINES.get(fname, [])):
        assert g1 == pytest.approx(w1, abs=0.01) and g2 == pytest.approx(w2, abs=0.01)


def test_riser_s_curve_anchors_match_the_svg(qapp):
    """riser_passthrough.svg path3: m 10,1 c ... 0,9 ... 0,9 -> anchors (10, 1),
    (10, 10), (10, 19); centred x K 7.5 -> (0, -67.5), (0, 0), (0, 67.5)."""
    (sp,) = [p for p in _prims("Riser.fpdb") if p["type"] == "draw_spline"]
    cps = sp["control_points"]
    assert sp["degree"] == 3 and len(cps) == 7
    for got, want in zip((cps[0], cps[3], cps[6]),
                         ((0.0, -67.5), (0.0, 0.0), (0.0, 67.5))):
        assert tuple(got) == pytest.approx(want, abs=0.01)


def test_sprinkler2_quadrants_match_the_svg_ink_minus_half_stroke(qapp):
    """sprinkler2.svg path3..path6 (filled; no cap or miter reach past the
    stroke): the converted centre-line rect equals the SVG ink rect shrunk by
    half the stroke (stroke-width 0.22677165 x the path matrix 0.26458333 x K / 2
    = 0.9145 mm)."""
    half = 0.22677165 * 0.26458333 * KH / 2.0
    regions = [p for p in _prims("Sprinkler2.fpdb") if p["type"] == "draw_filled_region"]
    assert len(regions) == 4
    for p, el in zip(regions, ("path3", "path4", "path5", "path6")):
        want = _svg_ink(("sprinkler_graphics", "sprinkler2.svg"), el, KH).adjusted(
            half, half, -half, -half)
        got = _geom(p)
        for a, b in ((got.left(), want.left()), (got.top(), want.top()),
                     (got.right(), want.right()), (got.bottom(), want.bottom())):
            assert a == pytest.approx(b, abs=0.01), (el, got, want)


def test_water_supply_teardrop_starts_at_the_svg_anchor_and_stays_in_its_ink(qapp):
    """water_supply.svg path6: m 12.106859,13.3525 c ... (inside the group
    translate -G): the region's first control point is that anchor, and its
    centre-line rect lies inside the SVG's ink rect (the 4.5-unit stroke)."""
    (p,) = [q for q in _prims("Water Supply.fpdb") if q["type"] == "draw_filled_region"]
    first = p["loops"][0][0]
    start = first["control_points"][0] if first["type"] == "draw_spline" else first["pt1"]
    assert tuple(start) == pytest.approx((_h(12.106859), _h(13.3525)), abs=0.01)
    ink = _svg_ink(("sprinkler_graphics", "water_supply.svg"), "path6", KH)
    assert ink.contains(_geom(p))
