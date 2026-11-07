"""HF7 D6/D7 (G11): tiles against ezdxf's own pattern definitions."""
import math

import pytest
from ezdxf.tools import pattern as ezp

from firepro3d.hatch_tile import Tile, convert, key_of

PATTERNS = ezp.load()


def fams(name, *, rot=0.0, scale=1.0):
    """Scene-space families from ezdxf's table (Y negated like the reader)."""
    r = math.radians(rot)
    c, s = math.cos(r), math.sin(r)
    out = []
    for angle, base, offset, dashes in PATTERNS[name]:
        ox, oy = offset[0] * c - offset[1] * s, offset[0] * s + offset[1] * c
        bx, by = base[0] * c - base[1] * s, base[0] * s + base[1] * c
        out.append({"angle": -(angle + rot), "base": [bx * scale, -by * scale],
                    "offset": [ox * scale, -oy * scale],
                    "dashes": [d * scale for d in dashes]})
    return out


CONVERTIBLE = ["ANSI31", "ANSI32", "ANSI37", "ANGLE", "AR-B816", "NET3", "GRATE",
               "BRICK", "HEX", "AR-HBONE"]


@pytest.mark.parametrize("name", CONVERTIBLE)
def test_shipped_patterns_convert(name):
    t = convert(fams(name))
    assert isinstance(t, Tile) and t.w > 0 and t.h > 0 and t.segments


def test_rotated_ansi31_converts_and_rotated_grate_does_not():
    assert convert(fams("ANSI31", rot=28.28)) is not None
    assert convert(fams("GRATE", rot=151.72)) is None


def test_ar_conc_stays_unconvertible():
    assert convert(fams("AR-CONC")) is None


def _density(segments, area):
    """Stroke length per unit area, per direction (degrees, modulo 180)."""
    out: dict[int, float] = {}
    for x1, y1, x2, y2 in segments:
        a = round(math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180) % 180
        out[a] = out.get(a, 0.0) + math.hypot(x2 - x1, y2 - y1) / area
    return out


def _family_density(families):
    """The same density from raw family data, not the module under test."""
    out: dict[int, float] = {}
    for f in families:
        u = (math.cos(math.radians(f["angle"])), math.sin(math.radians(f["angle"])))
        spacing = abs(f["offset"][0] * u[1] - f["offset"][1] * u[0])
        dashes = f["dashes"]
        on = (sum(d for d in dashes if d > 0) / sum(abs(d) for d in dashes)) if dashes else 1.0
        a = round(f["angle"] % 180) % 180
        out[a] = out.get(a, 0.0) + on / spacing
    return out


@pytest.mark.parametrize("name", ["ANSI31", "ANSI37", "BRICK", "HEX", "NET3"])
def test_tile_density_matches_the_families(name):
    f = fams(name)
    t = convert(f)
    got = _density(t.segments, t.w * t.h)
    want = _family_density(f)
    assert set(got) == set(want)
    for a, v in want.items():
        assert got[a] == pytest.approx(v, rel=0.03)


# BRICK is out of this list on purpose: its dashed verticals END on the cell
# edge (stroke x=6.35 spans y -6.35..-12.7, then a gap), so an endpoint on the
# edge is a dash end, not a crossing. test_stamped_tile_matches_the_families
# covers BRICK against the raw data.
@pytest.mark.parametrize("name", ["ANSI31", "ANSI37", "HEX", "NET3"])
def test_tile_seams_close(name):
    """Every stroke leaving an edge re-enters on the opposite edge: a wrong
    W or H passes the density test but fails here."""
    _assert_seams_close(convert(fams(name)))


def _seams_match(leaving, entering, period, tol):
    """Each exit point re-enters at the same place along the seam; positions
    compare modulo the seam's length (a corner is both its ends)."""
    def near(a, b):
        d = abs(a - b) % period
        return min(d, period - d) < tol
    assert leaving and entering, "no stroke touches this seam: nothing was checked"
    assert all(any(near(a, b) for b in entering) for a in leaving)


def test_content_stays_in_the_cell_frame():
    t = convert(fams("BRICK"))
    for x1, y1, x2, y2 in t.segments:
        assert -1e-6 <= x1 <= t.w + 1e-6 and -t.h - 1e-6 <= y1 <= 1e-6
        assert -1e-6 <= x2 <= t.w + 1e-6 and -t.h - 1e-6 <= y2 <= 1e-6


def test_key_ignores_scale_and_shift_but_not_angle():
    a, b = convert(fams("ANSI31")), convert(fams("ANSI31", scale=3.0))
    assert a.key == b.key and b.w == pytest.approx(a.w * 3)
    shifted = fams("ANSI31")
    shifted[0]["base"] = [shifted[0]["base"][0] + 7.3, shifted[0]["base"][1] - 2.1]
    assert convert(shifted).key == a.key
    assert convert(fams("ANSI31", rot=28.28)).key != a.key


def test_key_of_matches_a_stored_block():
    t = convert(fams("ANSI37"))
    assert key_of(t.segments, t.w, t.h) == t.key


def test_segment_cap_returns_none(monkeypatch):
    import firepro3d.hatch_tile as ht
    monkeypatch.setattr(ht, "HATCH_TILE_MAX_SEGMENTS", 1)
    assert convert(fams("HEX")) is None


def test_single_axis_family_uses_spacing_for_the_free_edge():
    t = convert([{"angle": 0.0, "base": [0.0, 0.0], "offset": [0.0, 5.0], "dashes": []}])
    assert t.h == pytest.approx(5.0) and t.w == pytest.approx(5.0)


def _assert_seams_close(t):
    tol = t.spacing * 2e-2
    pts = [p for s in t.segments for p in ((s[0], s[1]), (s[2], s[3]))]
    right = [y for x, y in pts if abs(x - t.w) < 1e-6]
    left = [y for x, y in pts if abs(x) < 1e-6]
    top = [x for x, y in pts if abs(y + t.h) < 1e-6]
    bottom = [x for x, y in pts if abs(y) < 1e-6]
    _seams_match(right, left, t.h, tol)
    _seams_match(top, bottom, t.w, tol)


@pytest.mark.parametrize("rot", [0.0, 45.0, 90.0])
def test_rotated_ansi37_converts_and_seams_close(rot):
    """ANSI37 carries no dashes (raw table), so this covers non-axis and
    rotated-to-axis undashed lines; the dashed case is the next test."""
    t = convert(fams("ANSI37", rot=rot))
    assert t is not None and t.segments
    _assert_seams_close(t)


def test_dashed_diagonal_family_seams_close():
    """A dashed 45 degree family: a wrong period leaves open seams."""
    d = 3.0
    f = [{"angle": -45.0, "base": [0.0, 0.0], "offset": [d, d],
          "dashes": [2.0 * d * math.sqrt(2), -d * math.sqrt(2)]}]
    f.append({"angle": 45.0, "base": [0.0, 0.0], "offset": [d, -d], "dashes": []})
    t = convert(f)
    assert t is not None and t.segments
    _assert_seams_close(t)


@pytest.mark.parametrize("name", CONVERTIBLE)
def test_convertible_segment_count_within_the_cap(name):
    from firepro3d.constants import HATCH_TILE_MAX_SEGMENTS
    n = len(convert(fams(name)).segments)
    assert n <= HATCH_TILE_MAX_SEGMENTS, f"{name}: {n} segments"


def _on_family(f, px, py, tol=1e-6):
    """Is (px, py) on a stroke of raw family *f* (infinite plane)?"""
    a = math.radians(f["angle"])
    u = (math.cos(a), math.sin(a))
    n = (-u[1], u[0])
    signed = f["offset"][0] * n[0] + f["offset"][1] * n[1]
    across = (px - f["base"][0]) * n[0] + (py - f["base"][1]) * n[1]
    m = round(across / signed)
    if abs(across - m * signed) > tol:
        return False
    if not f["dashes"]:
        return True
    ox = f["base"][0] + m * f["offset"][0]
    oy = f["base"][1] + m * f["offset"][1]
    t = (px - ox) * u[0] + (py - oy) * u[1]
    length = sum(abs(d) for d in f["dashes"])
    t %= length
    pos = 0.0
    for d in f["dashes"]:
        if d > 0 and pos - tol <= t <= pos + d + tol:
            return True
        pos += abs(d)
    return False


def _dist_to_segments(px, py, segments):
    best = math.inf
    for x1, y1, x2, y2 in segments:
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        s = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
        best = min(best, math.hypot(px - x1 - s * dx, py - y1 - s * dy))
    return best


STAMPED = [("ANSI31", 0.0), ("ANSI37", 0.0), ("BRICK", 0.0), ("HEX", 0.0),
           ("NET3", 0.0), ("ANSI31", 28.28), ("BRICK", 90.0), ("AR-B816", 45.0)]


def _raw_points_in(g, x0, x1, y0, y1, step):
    """Points on the ON strokes of raw families *g* inside the box, sampled
    along each line; line rows are chosen from the box, not from hatch_tile."""
    corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    for r in g:
        a = math.radians(r["angle"])
        u = (math.cos(a), math.sin(a))
        n = (-u[1], u[0])
        signed = r["offset"][0] * n[0] + r["offset"][1] * n[1]
        across = [(cx - r["base"][0]) * n[0] + (cy - r["base"][1]) * n[1] for cx, cy in corners]
        m_lo = math.floor(min(across) / abs(signed)) - 1
        m_hi = math.ceil(max(across) / abs(signed)) + 1
        for m in range(m_lo, m_hi + 1):
            ox = r["base"][0] + m * r["offset"][0]
            oy = r["base"][1] + m * r["offset"][1]
            along = [(cx - ox) * u[0] + (cy - oy) * u[1] for cx, cy in corners]
            for i in range(math.floor(min(along) / step), math.ceil(max(along) / step) + 1):
                px, py = ox + i * step * u[0], oy + i * step * u[1]
                if x0 <= px <= x1 and y0 <= py <= y1 and _on_family(r, px, py, tol=1e-9):
                    yield px, py


@pytest.mark.parametrize("name,rot", STAMPED)
def test_stamped_tile_matches_the_families(name, rot):
    """G11: stamp the tile over 3 x 3 cells and compare with the raw families
    (ezdxf's table, not hatch_tile) both ways. A wrong W or H opens or doubles
    a seam that a single cell cannot show."""
    f = fams(name, rot=rot)
    t = convert(f)
    assert t is not None
    origin = f[0]["base"]
    g = [dict(r, base=[r["base"][0] - origin[0], r["base"][1] - origin[1]]) for r in f]
    stamped = [(x1 + i * t.w, y1 - j * t.h, x2 + i * t.w, y2 - j * t.h)
               for i in (-1, 0, 1) for j in (-1, 0, 1)
               for x1, y1, x2, y2 in t.segments]
    tol = t.spacing * 1e-4
    # every stamped sample lies on a raw stroke
    for x1, y1, x2, y2 in stamped:
        for s in (0.1, 0.5, 0.9):
            px, py = x1 + s * (x2 - x1), y1 + s * (y2 - y1)
            assert any(_on_family(r, px, py, tol) for r in g), (name, px, py)
    # every raw on-point inside the stamped area lies on a stamped stroke; the
    # far right / bottom edge of the area is the next cell's, so keep clear of it
    m = t.spacing * 1e-2
    count = 0
    for px, py in _raw_points_in(g, -t.w + m, 2 * t.w - m, -2 * t.h + m, t.h - m,
                                 t.spacing * 0.0731):
        count += 1
        assert _dist_to_segments(px, py, stamped) < tol, (name, px, py)
    assert count > 50, "the raw side sampled too little to prove anything"


@pytest.mark.parametrize("name,rot", [("ANSI31", 0.0), ("HEX", 0.0), ("BRICK", 0.0),
                                      ("ANSI31", 28.28), ("ANGLE", 45.0),
                                      ("DOTS", 45.0), ("GROUT", 90.0)])
@pytest.mark.parametrize("scale", [25.4, 1 / 25.4, 1e-3, 1e3])
def test_key_survives_a_unit_change(name, rot, scale):
    """The same pattern in inches or mm (or any unit) is one block."""
    a, b = convert(fams(name, rot=rot)), convert(fams(name, rot=rot, scale=scale))
    assert a is not None and b is not None
    assert a.key == b.key and b.w == pytest.approx(a.w * scale)


def test_key_folds_signed_zero_for_a_rotated_pattern():
    """ANGLE rotated 45 degrees puts strokes on the edges; float noise there
    gives -0.0 or 0.0, which must not split the key."""
    keys = {convert(fams("ANGLE", rot=45.0, scale=s)).key for s in (1e-3, 1.0, 1e3)}
    assert len(keys) == 1


def test_key_of_folds_negative_zero():
    a = key_of([(0.0, 0.0, 1.0, -1.0)], 2.0, 2.0)
    assert key_of([(-0.0, -1e-12, 1.0, -1.0)], 2.0, 2.0) == a


# Each case is one the sweep over all 172 ezdxf patterns showed splitting under
# an absolute coordinate tolerance (sliver drop, edge-stroke drop, parallel test).
UNIT_CASES = [("ANSI33", 0.0), ("ANSI35", 0.0), ("HEX", 0.0), ("AR-HBONE", 45.0),
              ("ANSI37", 45.0), ("ANGLE", 90.0), ("CORK", 90.0), ("ESCHER", 90.0),
              ("NET3", 0.0), ("BRICK", 0.0)]


@pytest.mark.parametrize("name,rot", UNIT_CASES)
def test_conversion_does_not_depend_on_the_drawing_unit(name, rot):
    """Coordinate tolerances follow the pattern, not the unit: the same pattern
    at in->mm, mm->in and 1e-3 .. 1e6 gives the same segment count (ANSI33 gave
    32 / 35 / 31) and the same key."""
    scales = (1.0, 25.4, 1 / 25.4, 1e-3, 1e3, 1e6)
    got = [convert(fams(name, rot=rot, scale=s)) for s in scales]
    assert len({t is None for t in got}) == 1
    if got[0] is not None:
        counts = [len(t.segments) for t in got]
        assert len(set(counts)) == 1, dict(zip(scales, counts))
        assert len({t.key for t in got}) == 1


@pytest.mark.parametrize("dashes", [[0.0], [0.0, 0.0], [0.0, -0.0]])
def test_zero_sum_dashes_return_none(dashes):
    """dxf_fills._pattern passes ln.dash_length_items unchanged, so a
    degenerate list reaches convert; it is not an undashed (solid) line."""
    f = [{"angle": 0.0, "base": [0.0, 0.0], "offset": [0.0, 5.0], "dashes": dashes}]
    assert convert(f) is None


def test_dots_only_family_still_converts():
    f = [{"angle": 0.0, "base": [0.0, 0.0], "offset": [0.0, 5.0], "dashes": [0.0, -5.0]}]
    assert convert(f) is not None


def test_negative_offset_gives_the_same_tile():
    up = [{"angle": 0.0, "base": [0.0, 0.0], "offset": [0.0, 5.0], "dashes": []}]
    down = [{"angle": 0.0, "base": [0.0, 0.0], "offset": [0.0, -5.0], "dashes": []}]
    a, b = convert(up), convert(down)
    assert (a.w, a.h, a.key) == (b.w, b.h, b.key)


@pytest.mark.parametrize("angle", [28.28 + 360.0, 28.28 - 360.0, 28.28 + 720.0])
def test_angle_outside_0_360_gives_the_same_tile(angle):
    ref = fams("ANSI31")
    ref[0]["angle"] = -28.28
    other = fams("ANSI31")
    other[0]["angle"] = -angle
    a, b = convert(ref), convert(other)
    assert a is not None and b is not None
    assert (a.key, len(a.segments)) == (b.key, len(b.segments))
    assert b.w == pytest.approx(a.w) and b.h == pytest.approx(a.h)


@pytest.mark.parametrize("name", ["ANSI31", "BRICK", "HEX", "ANSI33"])
@pytest.mark.parametrize("scale", [1e-12, 1e9])
def test_an_extreme_drawing_unit_still_converts(name, scale):
    """A pattern whose whole spacing is below (or far above) any absolute
    epsilon is the same pattern."""
    a, b = convert(fams(name)), convert(fams(name, scale=scale))
    assert a is not None and b is not None
    assert (len(a.segments), a.key) == (len(b.segments), b.key)


@pytest.mark.parametrize("dashes", [[1.0, -1.0, 1e-17], [1.0, -1.0, 1e-300], [1e-17, -1.0, 1.0]])
def test_a_sub_epsilon_dash_does_not_divide_by_zero(dashes):
    """A zero-length segment in the clip (dx = dy = 0) is parallel to every edge."""
    f = [{"angle": 0.0, "base": [0.0, 0.0], "offset": [0.0, 5.0], "dashes": dashes}]
    t = convert(f)
    assert t is None or (t.w > 0 and t.h > 0 and t.segments)


def test_clip_of_a_zero_length_segment_is_a_point_test():
    from firepro3d.hatch_tile import _clip
    assert _clip((1.0, -1.0), (1.0, -1.0), 5.0, 5.0, 1e-9) is not None   # inside the cell
    assert _clip((9.0, -1.0), (9.0, -1.0), 5.0, 5.0, 1e-9) is None       # outside it
