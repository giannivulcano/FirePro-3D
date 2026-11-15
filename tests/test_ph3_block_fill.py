"""PH3 DD4: a BlockInstance paints its fill ops in ``_paper_fill_colour`` when set
(the paint contract the paper pass drives; the render guard is
tests/test_ph3_sheet_render.py::test_ac9p_block_plots_status_colour_and_fill)."""
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter

from tests import _ph1_helpers as h
from tests._ph1_helpers import ph1_cleanup  # noqa: F401
from tests._ph3_helpers import fill_block


def _body(ms, inst):
    r = inst.sceneBoundingRect()
    inner = r.adjusted(r.width() * 0.3, r.height() * 0.3, -r.width() * 0.3, -r.height() * 0.3)
    img = QImage(40, 24, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    ms.render(p, QRectF(0, 0, 40, 24), inner)
    p.end()
    return {QColor(img.pixel(x, y)).name() for x in range(40) for y in range(24)}


def test_dd4_fill_ops_paint_in_the_paper_fill_slot(qapp):
    ms = h.scene()
    inst = fill_block(ms)
    assert inst._paper_fill_colour is None
    assert _body(ms, inst) == {"#ffff00"}                 # the authored fill (fill_block)
    inst._paper_fill_colour = QColor("#00ff00")
    inst.update()
    assert _body(ms, inst) == {"#00ff00"}
