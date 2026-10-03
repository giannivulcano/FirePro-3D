# tests/test_hatch_render.py
"""paint_fill: lattice in scene axes, LOD, drafting factor, IntersectClip (HD4a)."""
import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from firepro3d import hatch_patterns as hp
from firepro3d import hatch_render as hr


class _PaperCtx:
    """Stand-in for a scene inside a paper-viewport render window."""
    def __init__(self, s):
        self._hatch_paper_scale = s


def _img(w=400, h=400):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    return img


def _rect(x, y, w, h):
    p = QPainterPath()
    p.addRect(QRectF(x, y, w, h))
    return p


def _red(img, x, y):
    c = QColor(img.pixel(x, y))
    return c.red() > 200 and c.green() < 90 and c.blue() < 90


def _row_runs(img, x):
    """y of the first pixel of each red run down column x."""
    ys, prev = [], False
    for y in range(img.height()):
        r = _red(img, x, y)
        if r and not prev:
            ys.append(y)
        prev = r
    return ys


def test_horizontal_spacing_tracks_scale(qapp):
    def spacing(scale):
        img = _img()
        p = QPainter(img)
        # scene=None → model canvas: Drafting 3 mm × 1:100 = 300 units × scale
        hr.paint_fill(p, _rect(10, 10, 380, 380), scene=None,
                      tile_ref="horizontal", colour=QColor("#ff0000"),
                      origin=QPointF(0, 0), scale=scale)
        p.end()
        ys = _row_runs(img, 200)
        return sorted({b - a for a, b in zip(ys, ys[1:])})[0]
    s1, s2 = spacing(0.1), spacing(0.2)          # 1 px per unit, cosmetic 1 px pen
    assert s1 == 30 and s2 == 60


def test_clip_is_intersected_not_replaced(qapp):
    img = _img()
    p = QPainter(img)
    p.setClipRect(QRectF(0, 0, 100, 400))                  # outer crop (paper viewport)
    hr.paint_fill(p, _rect(0, 0, 400, 400), scene=_PaperCtx(1.0),
                  background=QColor("#ff0000"))
    p.end()
    assert _red(img, 50, 50) and not _red(img, 300, 50)    # H5


def test_lod_tone_when_cells_are_sub_pixel(qapp):
    img = _img()
    p = QPainter(img)
    p.scale(0.05, 0.05)                                    # 3 mm cell → 0.15 px
    hr.paint_fill(p, _rect(0, 0, 8000, 8000), scene=_PaperCtx(1.0),
                  tile_ref="diagonal", colour=QColor("#ff0000"))
    p.end()
    c = QColor(img.pixel(200, 200))
    # 35 % red over white → (255, ~166, ~166); uniform = no lines stamped.
    assert c.red() == 255 and 150 < c.green() < 180
    assert QColor(img.pixel(207, 203)) == c


def test_unknown_tile_draws_tone_not_blank(qapp):
    img = _img()
    p = QPainter(img)
    hr.paint_fill(p, _rect(0, 0, 400, 400), scene=None,
                  tile_ref="no-such-tile", colour=QColor("#ff0000"))
    p.end()
    assert QColor(img.pixel(200, 200)) != QColor("white")


def test_drafting_factor_contexts(qapp):
    from firepro3d.constants import DRAFTING_CANVAS_SCALE
    assert hr.drafting_factor(None) == DRAFTING_CANVAS_SCALE
    assert hr.drafting_factor(_PaperCtx(0.01)) == 100.0
    assert hr.drafting_factor(_PaperCtx(0.02)) == 50.0


def test_pattern_never_rotates_with_the_painter_frame(qapp):
    """to_scene rotated 30°: lines stay at 45° on screen (G3 at renderer level)."""
    from PyQt6.QtGui import QTransform
    img = _img()
    p = QPainter(img)
    rot = QTransform().rotate(30)
    p.setTransform(rot)                                    # item frame = rotated
    inv, _ = rot.inverted()
    clip = inv.map(_rect(20, 20, 360, 360))                # same screen square
    hr.paint_fill(p, clip, scene=None, tile_ref="diagonal",
                  colour=QColor("#ff0000"), scale=0.1, to_scene=rot)   # ~42 px cells
    p.end()
    lit = [(x, y) for x in range(30, 370, 2) for y in range(30, 370, 2) if _red(img, x, y)]
    along = sum(_red(img, x + 3, y - 3) for x, y in lit) / len(lit)
    assert along > 0.8


# ── Fix round (review I1 / I2 / I3, M4, M5) ──────────────────────────────────

def test_lattice_cache_follows_content_through_undo(qapp):
    """I1: undo restores an old version number; a later edit landing on a
    version that was cached with different content must render the NEW content."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.model_space import Model_Space
    s = Model_Space()
    line = hp._line
    d = BlockDefinition.new(name="T", library="Project", series="",
                            primitives=[line(0, 0, 40, 0)], origin=(0.0, 0.0))
    d.set_tile({"w": 40, "h": 40, "row_shift": 0, "size": "model"}, notify=False)
    d.set_primitives([line(0, 0, 40, 0)])                  # content A (horizontal)
    s.register_block_definition(d)
    s.push_undo_state()
    d.set_primitives([line(0, 0, 40, -40)])                # content B (rises →)
    s.push_undo_state()
    cached_version = d.version

    def render():
        img = _img()
        p = QPainter(img)
        hr.paint_fill(p, _rect(0, 0, 400, 400), scene=s, tile_ref=d.id,
                      colour=QColor("#ff0000"))
        p.end()
        return img

    def rising_fraction(img):
        lit = [(x, y) for x in range(10, 390, 2) for y in range(10, 390, 2)
               if _red(img, x, y)]
        return sum(_red(img, x + 3, y - 3) for x, y in lit) / len(lit)

    assert rising_fraction(render()) > 0.8                 # B rendered + cached
    s.undo()                                               # real restore → content A, old version
    r = s.block_registry.get(d.id)
    assert r is not d and r.version == cached_version - 1
    # Content C: same bbox as B (same lattice extents → same nx/ny) but falling.
    r.set_primitives([line(0, -40, 40, 0)])
    assert r.version == cached_version                     # same id + version as cached B
    assert rising_fraction(render()) < 0.2                 # C drawn, not stale B


def test_large_fill_stamps_visible_cells_not_tone(qapp):
    """I2: 200 m × 200 m diagonal fill, 2 m window on screen → real lines."""
    img = _img()
    p = QPainter(img)
    p.scale(0.2, 0.2)                                      # 2000 mm → 400 px
    hr.paint_fill(p, _rect(-100000, -100000, 200000, 200000), scene=None,
                  tile_ref="diagonal", colour=QColor("#ff0000"))
    p.end()
    reds = sum(_red(img, x, y) for x in range(0, 400, 2) for y in range(0, 400, 2))
    whites = sum(QColor(img.pixel(x, y)) == QColor("white")
                 for x in range(0, 400, 2) for y in range(0, 400, 2))
    assert reds > 100 and whites > 10000                   # lines, not a uniform tone


def test_lattice_cache_is_bounded_by_cells(qapp, monkeypatch):
    """I3: LRU eviction by Σ(nx·ny), oversize entries never cached."""
    monkeypatch.setattr(hr, "HATCH_LATTICE_CACHE_MAX_CELLS", 100)
    hr._LATTICE.clear()
    hr._LATTICE_CELLS[0] = 0
    tile = hp.resolve_tile("horizontal")
    t = tile.tile
    hr._lattice(tile, t, 1.0, 5, 8, 0)                     # A: 40
    hr._lattice(tile, t, 1.0, 8, 5, 0)                     # B: 40
    hr._lattice(tile, t, 1.0, 5, 8, 0)                     # touch A
    hr._lattice(tile, t, 1.0, 4, 10, 0)                    # C: 40 → evicts B (LRU)
    dims = [(k[-3], k[-2]) for k in hr._LATTICE]
    assert dims == [(5, 8), (4, 10)]
    assert hr._LATTICE_CELLS[0] == 80
    s, _ = hr._lattice(tile, t, 1.0, 11, 10, 0)            # 110 > budget
    assert not s.isEmpty() and len(hr._LATTICE) == 2 and hr._LATTICE_CELLS[0] == 80
    hr._LATTICE.clear()
    hr._LATTICE_CELLS[0] = 0


def test_non_finite_bounds_draw_nothing(qapp):
    """M5: an infinite bound never raises inside paint."""
    img = _img()
    p = QPainter(img)
    pen = QPen(QColor("#ff0000"))
    tile = hp.resolve_tile("horizontal")
    assert hr.stamp_lattice(p, QRectF(0, 0, math.inf, 100), tile, 100.0,
                            QPointF(0, 0), pen, QColor("#ff0000")) is False
    p.end()
    assert QColor(img.pixel(50, 50)) == QColor("white")


def test_tone_leaves_painter_state(qapp):
    """M4: the LOD-tone return path restores pen and brush."""
    from PyQt6.QtGui import QBrush
    img = _img()
    p = QPainter(img)
    p.setPen(QPen(QColor("#00ff00"), 3))
    p.setBrush(QBrush(QColor("#0000ff")))
    p.scale(0.01, 0.01)                                    # sub-pixel cells → tone
    tile = hp.resolve_tile("diagonal")
    assert hr.stamp_lattice(p, QRectF(0, 0, 1000, 1000), tile, 1.0, QPointF(0, 0),
                            QPen(QColor("#ff0000")), QColor("#ff0000")) is False
    assert p.pen().color() == QColor("#00ff00") and p.pen().width() == 3
    assert p.brush().color() == QColor("#0000ff")
    p.end()


def test_offset_viewport_stamps_its_bottom_right(qapp):
    """C1: a canvas viewport sitting far inside its window (below a ribbon,
    right of a dock) still gets hatch cells over its bottom-right quadrant.
    Real QGraphicsView + real BlockInstance pattern op + window grab."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QGraphicsView, QGridLayout, QWidget
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import RectangleItem
    from firepro3d.model_space import Model_Space

    scene = Model_Space()
    r = RectangleItem(QPointF(-100000, -100000), QPointF(100000, 100000))
    r.fill_type = "hatch"
    r.fill_pattern = "diagonal"                            # 424 mm cells at 1:100
    r._display_fill_color = "#ff0000"
    d = BlockDefinition.new(name="Slab", library="Project", series="",
                            primitives=[r.to_dict()], origin=(0.0, 0.0))
    scene.register_block_definition(d)
    scene.place_block_instance(d.id, (0.0, 0.0))

    win = QWidget()
    lay = QGridLayout(win)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    top, left = QWidget(), QWidget()
    top.setFixedHeight(350)                                # "ribbon"
    left.setFixedWidth(350)                                # "dock"
    view = QGraphicsView(scene)
    view.setFixedSize(500, 400)
    lay.addWidget(top, 0, 0, 1, 2)
    lay.addWidget(left, 1, 0)
    lay.addWidget(view, 1, 1)
    try:
        win.show()
        QTest.qWaitForWindowExposed(win)
        view.resetTransform()
        view.scale(0.05, 0.05)                             # cell ≈ 21 px
        view.centerOn(0.0, 0.0)
        qapp.processEvents()
        img = win.grab().toImage()
        vp = view.viewport()
        o = vp.mapTo(win, QPoint(0, 0))
        dpr = img.devicePixelRatio()
        assert o.x() >= 300 and o.y() >= 300               # scenario really offset
        w, h = vp.width(), vp.height()

        def red_in(x0, y0, x1, y1):
            n = 0
            for x in range(x0, x1, 2):
                for y in range(y0, y1, 2):
                    c = QColor(img.pixel(int((o.x() + x) * dpr), int((o.y() + y) * dpr)))
                    n += c.red() > 150 and c.green() < 100 and c.blue() < 100
            return n

        tl = red_in(0, 0, w // 2, h // 2)
        br = red_in(w // 2, h // 2, w - 2, h - 2)
        # Measured (step-2 sampling, strict red): fixed (tl 29, br 47); deviceTransform bug (12, 0).
        assert br > 15 and tl > 15, (tl, br)
    finally:
        win.close()
        win.deleteLater()
        scene.cleanup()


def _model_tile_scene():
    """Model_Space + a registered 100x100 Model tile holding one line (0,0)-(100,0)."""
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.model_space import Model_Space
    sc = Model_Space()
    d = BlockDefinition.new(name="T100", library="Project", series="",
                            primitives=[hp._line(0, 0, 100, 0)], origin=(0.0, 0.0))
    d.set_tile({"w": 100, "h": 100, "row_shift": 0, "size": "model"}, notify=False)
    d.set_primitives([hp._line(0, 0, 100, 0)])
    sc.register_block_definition(d)
    return sc, d


def _stamped(sc, d, clip, scale):
    img = _img()
    p = QPainter(img)
    p.scale(scale, scale)
    hr.STATS["stamped_cells"] = 0
    hr.paint_fill(p, clip, scene=sc, tile_ref=d.id, colour=QColor("#ff0000"))
    p.end()
    return hr.STATS["stamped_cells"]


def test_fully_visible_fill_stamps_exact_cells(qapp):
    """G12 ruling: a fill wholly on screen stamps exactly the cells covering
    bbox + content overhang (floor/ceil), no 4-cell snapping."""
    sc, d = _model_tile_scene()
    # bbox (0,0)-(1000,500), cell 100, content x∈[0,100], y=0, origin (0,0):
    #   j: floor((0+0-500)/100) = -5 .. ceil((0+0-0)/100) = 0   → 6 rows
    #   i: floor((0-100-0)/100) = -1 .. ceil((1000-0-0)/100) = 10 → 12 cols
    n = _stamped(sc, d, _rect(0, 0, 1000, 500), 0.4)      # 400x200 px of a 400x400 image
    assert n == 12 * 6


def test_partly_visible_fill_still_snaps_in_4_cell_steps(qapp):
    """A fill the visible area cuts keeps the outward 4-cell snap (pan-stable)."""
    sc, d = _model_tile_scene()
    m = 4
    for pan in (0.0, 30.0, 70.0):
        clip = _rect(-5000 - pan, -5000, 20000, 20000)     # far larger than the 1000x1000 view
        n = _stamped(sc, d, clip, 0.4)
        assert n > 0 and n % (m * m) == 0
