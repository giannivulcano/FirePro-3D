"""LT4 A6: the panel preview swatch draws exactly what the linetype renderer draws.

``linetype_authoring.preview_painter`` (LT4-7) is painted into an image and
compared pixel-coverage-wise against a direct ``expand`` + ``draw_expansion``
of the same pieces / factor / anchor / pen width (preview ≡ render).
"""
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPen

from firepro3d import linetype_authoring as la
from firepro3d import stroke_style as ss
from firepro3d.block_editor import BlockEditorWidget
from firepro3d.constants import PATTERN_PREVIEW_PERIODS
from firepro3d.linetype_render import LinetypeDef, draw_expansion, expand
from firepro3d.model_space import Model_Space
from firepro3d.path_walk import Seg

W, H, M = 226, 64, 8.0          # swatch rect + preview_painter's margin


def _img():
    img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))
    return img


def _cover(img, rows=(8, 56), cols=(8,)):
    """Coverage masks on the two straight rows and the L's vertical leg."""
    out = [[img.pixelColor(x, y).alpha() > 0 for x in range(W)] for y in rows]
    out += [[img.pixelColor(x, y).alpha() > 0 for y in range(H)] for x in cols]
    return out


def _swatch(sc):
    img = _img()
    p = QPainter(img)
    la.preview_painter(sc)(p, QRectF(0, 0, W, H))
    p.end()
    return img


def _direct(lt):
    x0, x1, y0, y1 = M, W - M, M, H - M
    s = (x1 - x0) / (PATTERN_PREVIEW_PERIODS * lt.period)
    pieces = (Seg(x0, y0, x1, y0), Seg(x0, y0 + 10.0, x0, y1), Seg(x0, y1, x1, y1))
    dash, dot = expand(pieces, lt, s, (0.0, 0.0))
    img = _img()
    p = QPainter(img)
    pen = QPen(QColor(255, 255, 255), ss.canvas_px(lt.dash_weight or ss.BY_LINETYPE))
    pen.setCosmetic(True)
    draw_expansion(p, dash, dot, pen)
    p.end()
    return img


def _editor(rows=None, weight=None):
    w = BlockEditorWidget(Model_Space())
    assert w.toggle_capability("repeat") is True
    sc = w.editor_scene
    if rows is not None:
        assert la.apply_pattern_rows(sc, rows) is True
    if weight is not None:
        la.set_pattern_weight(sc, weight)
    return w, sc


def _check(sc, expect_dashes, expect_dots, expect_weight):
    lt = LinetypeDef.from_block(sc.capability_frame_item().scratch_definition())
    # The scratch reads the live authored content (not a stale preview).
    assert (lt.dashes, lt.dots, lt.dash_weight) == (expect_dashes, expect_dots,
                                                    expect_weight)
    a, b = _cover(_swatch(sc)), _cover(_direct(lt))
    top = a[0][int(M):int(W - M)]
    assert any(top) and not all(top)        # a real broken line, not blank/solid
    assert a == b


def test_a6_seed_swatch_equals_direct_render(qapp):
    _w, sc = _editor()                                   # seed Dash 6 / Gap 3
    _check(sc, ((0.0, 6.0),), (), None)


def test_a6_authored_swatch_equals_direct_render(qapp):
    _w, sc = _editor([("dash", 6.0), ("gap", 2.0), ("dot", 0.0), ("gap", 2.0)],
                     "Heavy")
    _check(sc, ((0.0, 6.0),), (8.0,), "Heavy")
