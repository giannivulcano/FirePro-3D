"""MW-12 / H-MW-g -- the D39 tint is the item drawn in its state colour (G8).

Each L523 guard is shown RED with the fix reverted (group report).
Probes sample off x = 0 / y = 0: the Block Editor paints its X/Y constraint
axes through the origin, over the strokes."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from firepro3d import theme as th
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from tests.mw_support import blend_spread, boundary_y, column_profile, dist, grab, rows

_X = 60.0          # probe column, clear of the Y axis


@pytest.fixture
def be(qapp):
    sc = Model_Space(scene_role="block_editor")
    sc.scale_manager = ScaleManager()
    v = Model_View(sc)
    v.resize(800, 600); v.show(); QTest.qWaitForWindowExposed(v)
    v.resetTransform(); v.centerOn(0, 0)
    sc.set_mode("select"); QApplication.processEvents()
    yield v, sc
    sc.clearSelection(); sc.cleanup(); v.close(); v.deleteLater()
    QApplication.processEvents()


def _line(sc, a, b, weight="Thinnest"):
    ln = LineItem(QPointF(*a), QPointF(*b))
    ln.style["weight"] = weight
    sc.addItem(ln); sc._draw_lines.append(ln)
    return ln


def _profile(v, img, dpr, x, y):
    dev = v.viewportTransform().map(QPointF(x, y))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
    return column_profile(img, dpr, int(dev.x()), dev.y()), bg


def test_tint_color_reads_state_and_exclusions(be):
    from firepro3d.geometry_2d import SplineItem
    from firepro3d.text_item import TextAnnotationData, TextItem
    v, sc = be
    ln = _line(sc, (-100, 40), (100, 40))
    ctl = sc.constraint_ctl
    assert ctl.tint_color(ln) == th.detect().color("constraint_free")
    ln.setSelected(True)
    assert ctl.tint_color(ln) is None
    ln.setSelected(False)
    t = TextItem(TextAnnotationData(text="HI"))
    sc.addItem(t); sc._texts.append(t)
    sp = SplineItem([QPointF(0, 0), QPointF(50, -60), QPointF(100, 0)])
    sc.addItem(sp); sc._draw_splines.append(sp)
    assert ctl.tint_color(t) is None and ctl.tint_color(sp) is None   # D39 exclusions
    ctl.show_status = False
    assert ctl.tint_color(ln) is None


@pytest.mark.parametrize("half", [0.0, 0.5])
@pytest.mark.parametrize("weight,n", [("Thinnest", 1), ("Thinner", 2), ("Thick", 4)])
def test_g8_tint_width_equals_untinted_width(be, half, weight, n):
    v, sc = be
    y = boundary_y(v, 40.0) + half
    _line(sc, (-150, y), (150, y), weight)
    img, dpr = grab(v)
    prof, bg = _profile(v, img, dpr, _X, y)
    assert rows(prof, th.detect().color("constraint_free"), bg) == (n, 0)


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_g8_diagonal_fringe_is_pure_tint_hue(be, theme_name, monkeypatch):
    v, sc = be
    monkeypatch.setattr(th, "detect", lambda: th.DARK if theme_name == "dark" else th.LIGHT)
    _line(sc, (-100, -100), (100, 0), "Thinner")
    img, dpr = grab(v)
    free = th.detect().color("constraint_free")
    lit = 0
    for sx in (30.0, 41.0, 60.0, 73.0):
        dev = v.viewportTransform().map(QPointF(sx, -100.0 + (sx + 100.0) * 0.5))
        bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 80) * dpr))
        for _r, c in column_profile(img, dpr, int(dev.x()), dev.y()):
            if dist(c, bg) <= 30:
                continue
            lit += 1
            # every lit pixel is a blend of tint and background only:
            # c = bg + a (free - bg) with one a for all three channels
            sp = blend_spread(c, bg, free)
            assert sp is not None and sp <= 0.12, (sx, c.getRgb(), sp)
    assert lit > 0


@pytest.mark.parametrize("screen", ["scale", "fixed"])
def test_g8_linetyped_free_line_keeps_its_gaps(be, screen):
    from tests.lt3_support import make_linetype
    v, sc = be
    d = make_linetype(dashes=((0.0, 30.0),), length=45.0, screen=screen)
    sc.register_block_definition(d)
    ln = _line(sc, (-150, 80), (150, 80))
    ln.style["linetype"] = d.id
    img, dpr = grab(v)
    a = v.mapFromScene(QPointF(-140, 80)); b = v.mapFromScene(QPointF(140, 80))
    free = th.detect().color("constraint_free")
    bg = img.pixelColor(int(a.x() * dpr), int((a.y() + 40) * dpr))
    tinted = gap = 0
    for x in range(a.x(), b.x()):
        cols = [img.pixelColor(int(x * dpr), int((a.y() + dy) * dpr)) for dy in (-1, 0, 1)]
        if any(dist(c, free) <= 60 for c in cols):
            tinted += 1
        elif all(dist(c, bg) <= 30 for c in cols):
            gap += 1
    span = b.x() - a.x()
    assert tinted > 0.3 * span and gap > 0.15 * span, (tinted, gap, span)


def test_g8_short_fixed_stroke_tints_solid(be):
    from tests.lt3_support import make_linetype
    v, sc = be
    d = make_linetype(dashes=((0.0, 30.0),), length=45.0, screen="fixed")
    sc.register_block_definition(d)
    ln = _line(sc, (55, 80), (65, 80))          # shorter than one Fixed period
    ln.style["linetype"] = d.id
    img, dpr = grab(v)
    a = v.mapFromScene(QPointF(56, 80)); b = v.mapFromScene(QPointF(64, 80))
    free = th.detect().color("constraint_free")
    assert all(any(dist(img.pixelColor(int(x * dpr), int((a.y() + dy) * dpr)), free) <= 60
                   for dy in (-1, 0, 1)) for x in range(a.x(), b.x()))


def test_g8_missing_linetype_tints_continuous(be):
    v, sc = be
    ln = _line(sc, (-150, 80), (150, 80))
    ln.style["linetype"] = "no-such-linetype-id"
    img, dpr = grab(v)
    a = v.mapFromScene(QPointF(-140, 80)); b = v.mapFromScene(QPointF(140, 80))
    free = th.detect().color("constraint_free")
    lit = sum(1 for x in range(a.x(), b.x())
              if any(dist(img.pixelColor(int(x * dpr), int((a.y() + dy) * dpr)), free) <= 60
                     for dy in (-1, 0, 1)))
    assert lit >= 0.95 * (b.x() - a.x())


def test_g8_tint_never_leaks_into_the_item(be):
    from firepro3d.geometry_2d import ReferenceLineItem
    v, sc = be
    rl = ReferenceLineItem(QPointF(-300, -150), QPointF(0, -150))
    sc.addItem(rl); sc._reference_lines.append(rl)
    before = rl.to_dict()["color"]
    img, dpr = grab(v)
    # Painted tinted (the hook reached it: lit pixels are tint / bg blends;
    # an unsplit 1 px reference line straddles two rows at part intensity) ...
    a = v.mapFromScene(QPointF(-290, -150)); b = v.mapFromScene(QPointF(-10, -150))
    free = th.detect().color("constraint_free")
    bg = img.pixelColor(int(a.x() * dpr), int((a.y() + 40) * dpr))
    lit = [img.pixelColor(int(x * dpr), int((a.y() + dy) * dpr))
           for x in range(a.x(), b.x()) for dy in (-1, 0, 1)]
    lit = [c for c in lit if dist(c, bg) > 30]
    assert lit and all((blend_spread(c, bg, free) or 9) <= 0.12 for c in lit)
    # ... yet the item's own colour (its pen) is untouched.
    assert rl.to_dict()["color"] == before
    assert rl.pen().color() != free


@pytest.mark.parametrize("half", [0.0, 0.5])
def test_g8_nested_block_ops_tint_per_op(be, half):
    from firepro3d.block_definition import BlockDefinition
    v, sc = be
    a = LineItem(QPointF(-100, 0), QPointF(100, 0)); a.style["weight"] = "Thick"
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[a.to_dict()], origin=(0.0, 0.0))
    sc.register_block_definition(d)
    y = boundary_y(v, 40.0) + half
    sc.place_block_instance(d.id, (0.0, y))      # real placement path
    img, dpr = grab(v)
    prof, bg = _profile(v, img, dpr, _X, y)
    assert rows(prof, th.detect().color("constraint_free"), bg) == (4, 0)
