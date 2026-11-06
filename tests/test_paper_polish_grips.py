"""Paper polish AC6 / AC7: paper grips measure 9 px at any zoom, a press hits
them, and a sheet render never carries one."""
import pytest
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.constants import MANIP_HANDLE_SIZE_PX
from firepro3d.level_manager import PlanViewManager
from firepro3d.manip_math import HandleRole
from firepro3d.paper_export import render_sheet
from firepro3d.paper_space import ViewResolver, sheet_page_mm
from firepro3d.text_item import TextAnnotationData
from tests._sb4d_helpers import dispose, plan_scene
from tests._sb4f_helpers import place

ZOOMS = [1.5, 12.0, 48.0]       # px per mm: sheet fit, working, zoomed in (design Measured base)


@pytest.fixture
def rig(qapp, real_system_library):
    ms, sec, det, tabs = plan_scene()
    yield ms, sec, det
    dispose(ms, sec, tabs)


def _target(ps, vp, kind):
    if kind == "viewport":
        return vp
    return ps.add_annotation(TextAnnotationData(text="NOTE", x=150.0, y=40.0,
                                                height_mm=3.175, wrap_width_mm=60.0))


def _frame(view, ps, item, zoom):
    view.show()
    QTest.qWaitForWindowExposed(view)
    ps.clearSelection()
    item.setSelected(True)
    QApplication.processEvents()
    m = ps._manipulator
    host = m._handles[HandleRole.BOTTOM_RIGHT]
    assert host.isVisible()
    view.resetTransform()
    view.scale(zoom, zoom)
    view.centerOn(host.scenePos())
    QApplication.processEvents()
    return m, host


@pytest.mark.parametrize("zoom", ZOOMS)
@pytest.mark.parametrize("kind", ["viewport", "text"])
def test_grip_measures_nine_px_and_a_press_hits_it(rig, kind, zoom):
    view, ps, vp = place(*rig)
    item = _target(ps, vp, kind)
    if kind == "viewport":
        # The title line grip sits 4.5 mm under the corner handle and wins a
        # press where their hit areas overlap (sheet fit, accepted at T5); this
        # test measures the corner handle alone.
        ps.commit_viewport_edit(vp, show_title=False)
    m, host = _frame(view, ps, item, zoom)
    half = host._size() / 2.0
    dev = host.deviceTransform(view.viewportTransform())
    rect = dev.mapRect(QRectF(-half, -half, 2 * half, 2 * half))
    assert rect.width() == pytest.approx(MANIP_HANDLE_SIZE_PX)
    assert rect.height() == pytest.approx(MANIP_HANDLE_SIZE_PX)
    assert host.handle in m.handles_at(host.scenePos())
    pt = view.mapFromScene(host.scenePos())
    QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=pt)
    assert m._mode == "resize"
    m.cancel_drag()
    QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=pt)
    QApplication.processEvents()


def _image(paint, w, h):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    paint(p, QRectF(0, 0, w, h))
    p.end()
    return img


def test_a_sheet_render_never_carries_a_grip(rig):
    """render_sheet builds its own scene, so a live selection cannot reach it.
    The live scene is the positive control: the comparison can see a grip."""
    ms, sec, det = rig
    view, ps, vp = place(ms, sec, det)
    pvm = PlanViewManager()
    pvm.create("Level 1", ms._level_manager)
    resolver = ViewResolver(ms, pvm, det, sec, level_manager=ms._level_manager)
    page_w, page_h = sheet_page_mm(ps.sheet)
    w, h = int(page_w * 2), int(page_h * 2)

    def sheet(p, target):
        render_sheet(ps.sheet, resolver, p, target)

    def live(p, target):
        ps.render(p, target, QRectF(0, 0, page_w, page_h))
    clean_sheet, clean_live = _image(sheet, w, h), _image(live, w, h)
    _frame(view, ps, vp, 12.0)
    assert _image(live, w, h) != clean_live           # a grip is visible to this compare
    assert _image(sheet, w, h) == clean_sheet
