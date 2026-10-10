"""G-LTS1 / G-LTS2 / G-LTS4 -- Fixed dashes hold their screen size (LTS-3)."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from firepro3d.block_definition import BlockDefinition
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space
from tests.lt3_support import make_linetype


def _render(ms, rect, w=400, h=40):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, w, h), rect)
    p.end()
    return img


def _row(img, y):
    return [QColor(img.pixel(x, y)).lightness() > 128 for x in range(img.width())]


def runs(row):
    """[(lit?, length)] run-length encoding of a pixel row."""
    out, cur, n = [], row[0], 0
    for v in row:
        if v == cur:
            n += 1
        else:
            out.append((cur, n))
            cur, n = v, 1
    out.append((cur, n))
    return out


def _inner(row, lit=True):
    """Full runs of one kind: background beyond the line's ends dropped,
    then the first / last run (clipped by a line end or the crop edge)."""
    r = runs(row)
    if r and not r[0][0]:
        r = r[1:]
    if r and not r[-1][0]:
        r = r[:-1]
    return [n for v, n in r[1:-1] if v is lit]


def _editor(screen):
    ms = Model_Space(scene_role="block_editor")
    ms.scale_manager.drawing_scale = 1.0   # ET1 Q1: editors preview at the drawing scale; these cases read 1:1
    d = make_linetype(screen=screen)
    ms.register_block_definition(d)
    return ms, d.id


def _line(ms, lid, a, b):
    ln = LineItem(QPointF(*a), QPointF(*b))
    ln.style["linetype"] = lid
    ms.addItem(ln)
    return ln


def test_g_lts1_fixed_raw_dash_is_constant_px_across_zoom(qapp):
    ms, lid = _editor("fixed")
    _line(ms, lid, (0, 0), (200, 0))
    near = _row(_render(ms, QRectF(0, -1, 20, 2)), 20)     # 20 px/mm
    far = _row(_render(ms, QRectF(0, -2, 40, 4)), 20)      # 10 px/mm
    # Hidden 6 / 3 printed mm x 6 px/mm = 36 px dash, 18 px gap at any zoom.
    for row in (near, far):
        dashes, gaps = _inner(row, True), _inner(row, False)
        assert dashes and all(abs(n - 36) <= 2 for n in dashes), runs(row)
        assert gaps and all(abs(n - 18) <= 2 for n in gaps), runs(row)


def test_g_lts2_scale_raw_dash_doubles_with_zoom(qapp):
    ms, lid = _editor("scale")
    _line(ms, lid, (0, 0), (200, 0))
    far = _inner(_row(_render(ms, QRectF(0, -2, 40, 4)), 20))     # 10 px/mm
    near = _inner(_row(_render(ms, QRectF(0, -1, 20, 2)), 20))    # 20 px/mm
    assert far and all(abs(n - 60) <= 2 for n in far), far
    assert near and all(abs(n - 120) <= 2 for n in near), near


def test_g_lts4_fixed_collinear_pieces_match_one_line(qapp):
    ms1, l1 = _editor("fixed")
    _line(ms1, l1, (0, 0), (36, 0))
    ms2, l2 = _editor("fixed")
    _line(ms2, l2, (16, 0), (0, 0))              # reversed, off-grid split
    _line(ms2, l2, (16, 0), (36, 0))
    r1 = _row(_render(ms1, QRectF(0, -2, 40, 4)), 20)
    r2 = _row(_render(ms2, QRectF(0, -2, 40, 4)), 20)
    assert any(not v for v in r1[10:350])        # really dashed
    assert r1 == r2


def _plan_block(screen):
    """A plan scene with one placed block: a 3000 mm line at y = 1000 mm."""
    ms = Model_Space()
    lt = make_linetype(screen=screen)
    ms.register_block_definition(lt)
    ln = LineItem(QPointF(-1500, 0), QPointF(1500, 0))
    ln.style["linetype"] = lt.id
    d = BlockDefinition.new(name="B", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0.0, 0.0))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 1000.0), level=ms.active_level)
    return ms


def test_g_lts1_fixed_placed_block_dash_is_constant_px_across_zoom(qapp):
    ms = _plan_block("fixed")
    # 0.1 px/mm and 0.2 px/mm; the line's row is y = 1000 mm in both crops.
    far = _row(_render(ms, QRectF(-2000, -1000, 4000, 4000), 400, 400), 200)
    near = _row(_render(ms, QRectF(-1000, 0, 2000, 2000), 400, 400), 200)
    for row in (far, near):
        dashes = _inner(row, True)
        assert dashes and all(abs(n - 36) <= 2 for n in dashes), runs(row)


def test_scale_placed_block_still_follows_drawing_scale(qapp):
    ms = _plan_block("scale")                       # 6 mm x 100 = 600 mm
    far = _inner(_row(_render(ms, QRectF(-2000, -1000, 4000, 4000), 400, 400), 200))
    assert far and all(abs(n - 60) <= 2 for n in far), far      # 0.1 px/mm
