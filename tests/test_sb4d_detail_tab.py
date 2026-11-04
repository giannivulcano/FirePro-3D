"""SB4d guard 8 (D6): in the detail tab the own callout -- bespoke leader +
the head block painted through its own paint under its scene transform --
draws bright ABOVE the crop mask; the head (outside the crop) is never
dimmed; the grip still drags it; another detail's marker stays hidden."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._sb4d_helpers import HEAD_R, dispose, head_def, ink, is_red, plan_scene


def _bright_red_near(view, scene_pt, half_px=40):
    img = view.viewport().grab().toImage()
    c = view.mapFromScene(scene_pt)
    pts = ink(img, is_red)
    return [p for p in pts if abs(p[0] - c.x()) <= half_px and abs(p[1] - c.y()) <= half_px]


def _any_red_tint_near(view, scene_pt, half_px=40):
    """Any reddish ink at all (bright OR mask-dimmed): the head leaves no trace."""
    img = view.viewport().grab().toImage()
    c = view.mapFromScene(scene_pt)
    return [p for p in ink(img, lambda q: q.red() - q.green() > 25 and q.red() - q.blue() > 25)
            if abs(p[0] - c.x()) <= half_px and abs(p[1] - c.y()) <= half_px]


def test_guard8_own_callout_paints_bright_above_the_mask_and_drags(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail", colour="#ff0000")
        m = det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
        tabs.resize(900, 700)
        tabs.show()
        QTest.qWaitForWindowExposed(tabs)
        v = det.open_detail("Detail 1")
        QTest.qWait(120)                                   # let the 50 ms fit timer run first
        v.resetTransform()
        v.scale(0.05, 0.05)                                # 20 mm per px: head radius 500 -> 25 px
        v.centerOn(m._bubble_pos)
        QApplication.processEvents()
        assert v._clip_rect is not None
        assert not m.crop_rect.contains(m._bubble_pos)     # the head sits under the mask
        near = _bright_red_near(v, m._bubble_pos)
        assert near, "own callout head not painted above the mask"
        # device-scale risk (T3 review): the head must measure its authored
        # size x drawing scale (HEAD_R * k mm) at this zoom, not a device-scaled one
        k = ms.scale_manager.drawing_scale
        expected_px = HEAD_R * k * 0.05
        xs = [p[0] for p in near]
        # the leader is vertical (head below the crop), so the x extent is the head's
        half_w = (max(xs) - min(xs)) / 2.0
        assert abs(half_w - expected_px) <= 3.0, (half_w, expected_px)
        old_pos = QPointF(m._bubble_pos)
        new_pos = QPointF(old_pos.x() + 2000.0, old_pos.y())
        m.apply_grip(8, new_pos)
        QApplication.processEvents()
        assert m._bubble_pos == new_pos                    # the grip moved the head
        assert m.bubble.pos() == new_pos
        v.centerOn(old_pos)                                # old and new spot both in view
        QApplication.processEvents()
        assert _bright_red_near(v, new_pos)                # repainted at the dragged spot
        assert not _bright_red_near(v, old_pos, half_px=20)   # and gone from the old one
        handles = m.manip_handles()
        assert len(handles) == 9                           # grip 8 = the round head grip (unchanged)
    finally:
        tabs.hide()
        dispose(ms, sec, tabs)


def test_guard8_other_details_marker_is_not_painted_in_this_tab(qapp):
    ms, sec, det, tabs = plan_scene()
    try:
        head_def(ms, "Detail", colour="#ff0000")
        m1 = det.create_detail("Detail 1", QRectF(0.0, 0.0, 4000.0, 3000.0))
        m2 = det.create_detail("Detail 2", QRectF(0.0, 9000.0, 4000.0, 3000.0))
        tabs.resize(900, 700)
        tabs.show()
        QTest.qWaitForWindowExposed(tabs)
        v = det.open_detail("Detail 1")
        QTest.qWait(120)
        v.resetTransform()
        v.scale(0.05, 0.05)
        # frame Detail 2's head (nothing of Detail 1's own callout is near it)
        v.centerOn(m2._bubble_pos)
        QApplication.processEvents()
        c = v.mapFromScene(m2._bubble_pos)
        assert v.viewport().rect().contains(c)
        assert not m1.bubble.sceneBoundingRect().intersects(
            v.mapToScene(v.viewport().rect()).boundingRect())
        assert not _any_red_tint_near(v, m2._bubble_pos), "another detail's marker painted in this tab"
        # control: its own tab does paint it
        v2 = det.open_detail("Detail 2")
        QTest.qWait(120)
        v2.resetTransform()
        v2.scale(0.05, 0.05)
        v2.centerOn(m2._bubble_pos)
        QApplication.processEvents()
        assert _bright_red_near(v2, m2._bubble_pos)
    finally:
        tabs.hide()
        dispose(ms, sec, tabs)
