"""Stroke corner joins (design 2026-11-03-stroke-corner-joins-design.md).

Section A: P4 probes of the Qt facts the build rests on (pass at base).
Section B+: guards 1-8 (RED at base c20d2ec3).
"""
import math

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsLineItem, QGraphicsPathItem

from firepro3d.geometry_2d import LineItem, PolylineItem
from firepro3d.model_space import Model_Space


# ---------------------------------------------------------------- A. probes
def test_p4_python_setline_override_sees_every_setline_call(qapp):
    """Geometry2DMixin precedes QGraphicsLineItem in the MRO, so a Python
    `setLine` on the mixin intercepts every `self.setLine(...)` call made
    from Python (apply_grip, translate, rotate, set_length, __init__)."""
    seen = []

    class Probe(LineItem):
        def setLine(self, *a):
            seen.append(a)
            super().setLine(*a)

    ln = Probe(QPointF(0, 0), QPointF(10, 0))
    ln.apply_grip(2, QPointF(20, 0))
    ln.set_length(5.0)
    assert len(seen) == 3           # __init__, apply_grip, set_length


def test_p4_item_scene_has_changed_fires_without_geometry_flag(qapp):
    seen = []

    class Probe(LineItem):
        def itemChange(self, change, value):
            seen.append(change)
            return super().itemChange(change, value)

    sc = Model_Space(); ln = Probe(QPointF(0, 0), QPointF(10, 0))
    sc.addItem(ln); sc.removeItem(ln)
    gc = ln.GraphicsItemChange
    assert seen.count(gc.ItemSceneHasChanged) == 2
    sc.cleanup()


def test_p4_qt_miter_limit_2_equals_pdf_ratio_4(qapp):
    """A 20 deg corner (ratio 1/sin(10 deg) = 5.76 > 4) is bevelled under Qt
    limit 2 and mitered under Qt limit 4 -- Qt measures the tip's reach from
    the join point in pen widths, i.e. PDF ratio / 2 (design AC5)."""
    def tip_reach(limit):
        p = QPainterPath(QPointF(0, 100)); p.lineTo(QPointF(0, 0))
        a = math.radians(20.0); p.lineTo(QPointF(100 * math.sin(a), 100 * math.cos(a)))
        st = QPainterPathStroker(); st.setWidth(20.0)
        st.setJoinStyle(Qt.PenJoinStyle.MiterJoin); st.setMiterLimit(limit)
        st.setCapStyle(Qt.PenCapStyle.FlatCap)
        return -st.createStroke(p).boundingRect().top()      # reach above the apex
    # Measured at base: Qt does NOT bevel past the limit, it clips the miter
    # (reach grows ~linearly with the limit: 1 -> 22, 2 -> 41, 2.5 -> 50) and
    # reaches the full tip (half_w / sin(10 deg) ~ 56.7 after flat-cap box) from
    # limit 3 up, i.e. the full-miter threshold is ratio/2 = 2.88.
    full = tip_reach(8.0)
    assert full > 50.0
    assert tip_reach(2.0) < full - 5.0    # clipped below the full tip
    assert tip_reach(2.5) < full - 5.0    # still clipped just under ratio/2
    assert tip_reach(3.0) > full - 0.1    # full miter once limit >= ratio/2
    assert tip_reach(4.0) > full - 0.1


def test_p4_flat_cap_line_paints_exactly_between_its_endpoints(qapp):
    img = QImage(300, 100, QImage.Format.Format_ARGB32); img.fill(QColor("white"))
    p = QPainter(img); pen = QPen(QColor("black"), 6.0)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap); p.setPen(pen)
    p.drawLine(QPointF(50, 50), QPointF(250, 50)); p.end()
    dark = [x for x in range(300) if img.pixelColor(x, 50).red() < 128]
    assert (min(dark), max(dark)) == (50, 249)
