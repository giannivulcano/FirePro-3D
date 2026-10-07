"""MW-12 / H-MW-g -- the D39 tint is the item drawn in its state colour (G8).

Each L523 guard is shown RED with the fix reverted (group report).
Probes sample off x = 0 / y = 0: the Block Editor paints its X/Y constraint
axes through the origin, over the strokes."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from firepro3d import theme as th
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from firepro3d.model_view import Model_View
from firepro3d.scale_manager import ScaleManager
from tests.mw_support import (blend_spread, boundary_x, boundary_y, column_profile,
                              dist, grab, row_profile, rows)

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


def _is_blend(c, bg, ink) -> bool:
    """True when *c* is a pure ``bg`` / *ink* blend (spread 0.0 included)."""
    sp = blend_spread(c, bg, ink)
    return sp is not None and sp <= 0.12


def _profile(v, img, dpr, x, y):
    dev = v.viewportTransform().map(QPointF(x, y))
    bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 60) * dpr))
    return column_profile(img, dpr, int(dev.x()), dev.y()), bg


def test_tint_color_reads_state_and_exclusions(be):
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
    assert t._uid in ctl.diagnostics().item_dof      # participates, yet ...
    assert ctl.tint_color(t) is None                 # ... text is never tinted (D39)
    ctl.show_status = False
    assert ctl.tint_color(ln) is None


@pytest.fixture(params=["dark", "light"])
def themed(request, monkeypatch):
    t = th.DARK if request.param == "dark" else th.LIGHT
    monkeypatch.setattr(th, "detect", lambda: t)
    return t


@pytest.mark.parametrize("half", [0.0, 0.5])
@pytest.mark.parametrize("weight,n", [("Thinnest", 1), ("Thinner", 2), ("Thick", 4)])
def test_g8_tint_width_equals_untinted_width(be, themed, half, weight, n):
    v, sc = be
    y = boundary_y(v, 40.0) + half
    _line(sc, (-150, y), (150, y), weight)
    img, dpr = grab(v)
    prof, bg = _profile(v, img, dpr, _X, y)
    assert rows(prof, themed.color("constraint_free"), bg) == (n, 0)


def test_g8_tint_width_vertical(be, themed):
    v, sc = be
    x = boundary_x(v, _X) + 0.5
    _line(sc, (x, -150), (x, 150), "Thinner")
    img, dpr = grab(v)
    dev = v.viewportTransform().map(QPointF(x, 40.0))   # clear of the X axis
    bg = img.pixelColor(int((dev.x() + 60) * dpr), int(dev.y() * dpr))
    prof = row_profile(img, dpr, dev.x(), int(dev.y()))
    assert rows(prof, themed.color("constraint_free"), bg) == (2, 0)


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
            assert _is_blend(c, bg, free), (sx, c.getRgb(), blend_spread(c, bg, free))
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
    # 250 px at 1 px / mm: most of one Fixed period (45 mm x 6 px/mm = 270 px,
    # 180 dash + 90 gap), so a dashed draw WOULD show a gap; LTS-7 paints it
    # solid -- and the tint must follow the solid fallback.
    ln = _line(sc, (20, 80), (270, 80))
    ln.style["linetype"] = d.id
    img, dpr = grab(v)
    a = v.mapFromScene(QPointF(22, 80)); b = v.mapFromScene(QPointF(268, 80))
    free = th.detect().color("constraint_free")
    unlit = [x for x in range(a.x(), b.x())
             if not any(dist(img.pixelColor(int(x * dpr), int((a.y() + dy) * dpr)), free) <= 60
                        for dy in (-1, 0, 1))]
    assert not unlit, (len(unlit), unlit[:5])


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
    assert lit and all(_is_blend(c, bg, free) for c in lit)
    # ... yet the item's own colour (its pen) is untouched.
    assert rl.to_dict()["color"] == before
    assert rl.pen().color() != free


@pytest.mark.parametrize("half", [0.0, 0.5])
def test_g8_block_ops_tint_per_op(be, half):
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


def test_g8_truly_nested_block_op_tints_at_its_own_width(be):
    """A block whose definition holds an instance of another block: the inner
    block's stroke op tints at its own width (MW-12 nested instances)."""
    from firepro3d.block_definition import BlockDefinition
    v, sc = be
    a = LineItem(QPointF(-100, 0), QPointF(100, 0)); a.style["weight"] = "Thick"
    inner = BlockDefinition.new(name="C", library="L", series="S",
                                primitives=[a.to_dict()], origin=(0.0, 0.0))
    outer = BlockDefinition.new(
        name="B", library="L", series="S", origin=(0.0, 0.0),
        primitives=[{"type": "block_instance", "block_id": inner.id,
                     "pos": [0.0, 0.0], "rotation": 0.0}])
    sc.register_block_definition(inner)
    sc.register_block_definition(outer)
    y = boundary_y(v, 40.0) + 0.5
    sc.place_block_instance(outer.id, (0.0, y))
    ops = sc._block_instances[-1].render_ops()      # inner line reached via nesting
    assert len(sc._block_instances) == 1 and ops
    img, dpr = grab(v)
    prof, bg = _profile(v, img, dpr, _X, y)
    assert rows(prof, th.detect().color("constraint_free"), bg) == (4, 0)


@pytest.mark.parametrize("screen", ["scale"])
def test_g8_linetyped_block_op_tints_dashes_and_keeps_gaps(be, screen):
    """The routed (linetyped) stroke-op loop of BlockInstance.paint."""
    from firepro3d.block_definition import BlockDefinition
    from tests.lt3_support import make_linetype
    v, sc = be
    d = make_linetype(dashes=((0.0, 30.0),), length=45.0, screen=screen)
    sc.register_block_definition(d)
    a = LineItem(QPointF(-150, 0), QPointF(150, 0)); a.style["linetype"] = d.id
    blk = BlockDefinition.new(name="B", library="L", series="S",
                              primitives=[a.to_dict()], origin=(0.0, 0.0))
    sc.register_block_definition(blk)
    sc.place_block_instance(blk.id, (0.0, 80.0))
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


def test_g8_memo_updates_items_whose_state_changed(be, monkeypatch):
    """Delta 5: a newly observed diagnostics result update()s exactly the
    items whose state changed (no full-viewport repaint needed)."""
    from firepro3d.geometry_2d import LineItem as _L
    v, sc = be
    held = _line(sc, (-200, 100), (-50, 140))
    other = _line(sc, (50, -100), (200, -100))
    ctl = sc.constraint_ctl
    grab(v)                                       # seed the memo (both free)
    assert ctl.tint_color(held) == th.detect().color("constraint_free")
    monkeypatch.setattr(ctl, "_repaint", lambda: None)
    ctl.add("horizontal", [{"uid": held._uid, "h": "edge"}])
    ctl.add("vertical", [{"uid": held._uid, "h": "edge"}])     # red -> conflict
    calls = []
    real = _L.update
    monkeypatch.setattr(_L, "update", lambda self, *a: (calls.append(self), real(self, *a)))
    assert ctl.tint_color(other) == th.detect().color("constraint_free")   # a paint read
    assert any(c is held for c in calls), calls
    assert not any(c is other for c in calls)
    assert ctl.tint_color(held) == th.detect().color("danger")


def test_ghost_polyline_is_never_tinted(be):
    """User ruling 2026-10-06: previews keep their own colour; only
    committed geometry shows constraint state."""
    from tests._snap_polish_helpers import click, move
    v, sc = be
    sc.set_mode("polyline"); QApplication.processEvents()
    for p in (QPointF(20, 80), QPointF(300, 80)):
        move(v, p); click(v, p)
    pl = sc._polyline_active
    assert pl is not None and pl._ghost_pen and pl in sc._polylines
    assert pl._uid in sc.constraint_ctl.diagnostics().item_dof   # would tint
    p0, p1 = pl._points[0], pl._points[1]
    move(v, QPointF(330, 250))     # rubber band + tracking overlays off the segment
    img, dpr = grab(v)
    ghost, free = pl.pen().color(), th.detect().color("constraint_free")
    a = v.mapFromScene(QPointF(p0.x() + 10, p0.y()))
    b = v.mapFromScene(QPointF(p1.x() - 10, p1.y()))
    bg = img.pixelColor(int(a.x() * dpr), int((a.y() + 40) * dpr))
    lit = [img.pixelColor(int(x * dpr), int((a.y() + dy) * dpr))
           for x in range(a.x(), b.x()) for dy in (-1, 0, 1)]
    lit = [c for c in lit if dist(c, bg) > 30]
    assert lit
    assert all(_is_blend(c, bg, ghost) for c in lit)
    # Never tinted: every lit pixel is measurably NOT a tint blend (a None
    # spread -- tint indistinguishable from bg -- must not pass silently).
    for c in lit:
        sp = blend_spread(c, bg, free)
        assert sp is not None and sp > 0.12, (c.getRgb(), sp)
    sc.set_mode("select"); QApplication.processEvents()


def test_block_placement_ghost_is_never_tinted(be):
    """The same ruling for BlockInstance placement ghosts (``_is_ghost``),
    made through the real placement-ghost path. The ghost is also listed as
    a participant so the exclusion -- not a missing uid -- is what holds."""
    from firepro3d.block_definition import BlockDefinition
    v, sc = be
    a = LineItem(QPointF(-100, 0), QPointF(100, 0))
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[a.to_dict()], origin=(0.0, 0.0))
    sc.register_block_definition(d)
    sc._place_block_id = d.id
    sc._place_block_make_ghost()
    g = sc._place_block_ghost
    assert g is not None and g._is_ghost
    sc._block_instances.append(g)
    try:
        ctl = sc.constraint_ctl
        assert g._uid in ctl.diagnostics().item_dof
        assert ctl.tint_color(g) is None
    finally:
        sc._block_instances.remove(g)
        sc._place_block_drop_ghost()
        sc._place_block_id = None


def test_tint_lookup_failure_paints_the_item_untinted(be, monkeypatch):
    """A failing tint lookup loses only the tint: the stroke still paints its
    full rows in the item's own colour."""
    v, sc = be
    ink = "#ff00ff"
    y = boundary_y(v, 40.0)
    ln = _line(sc, (-150, y), (150, y), "Thick")
    ln.style["colour"] = ink

    def boom():
        raise RuntimeError("diagnostics failed")
    monkeypatch.setattr(sc.constraint_ctl, "diagnostics", boom)
    img, dpr = grab(v)
    prof, bg = _profile(v, img, dpr, _X, y)
    assert rows(prof, QColor(ink), bg) == (4, 0)
