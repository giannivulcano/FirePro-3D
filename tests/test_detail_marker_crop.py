"""DetailMarker as a PARAMETRIC editable rectangle crop.

8 SQUARE crop grips (corners + midpoints; live apply_grip resize — no held-scale
warp) + a ROUND bubble grip. Caps = {translate} so the manipulator FRAME shows as
the visible bounding box (not box-native). Editable inside the detail view via a
bright drawForeground overlay (render_overlay)."""
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from firepro3d.detail_view import DetailMarker
from firepro3d.selection_manipulator import (
    item_capabilities, _item_uses_manip_handles, SelectionManipulator,
)
from firepro3d.manip_handle import GripHandle


def _make():
    return DetailMarker("Detail 1", QRectF(0, 0, 200, 100))


def test_parametric_caps_and_gate(qapp):
    dm = _make()
    assert item_capabilities(dm) == {"translate"}      # NOT scale (not box-native)
    assert _item_uses_manip_handles(dm) is True


def test_manip_handles_square_crop_grips_round_bubble(qapp):
    dm = _make()
    hs = dm.manip_handles()
    assert len(hs) == 9
    assert all(isinstance(h, GripHandle) for h in hs)
    assert all(h.circular is False for h in hs[:8])    # crop grips square
    assert hs[8].circular is True                      # bubble round


def test_apply_grip_resizes_crop_live(qapp):
    dm = _make()
    dm.apply_grip(2, QPointF(260, 160))                # bottom-right corner
    assert dm._crop_rect.bottomRight() == QPointF(260, 160)


def test_manip_translate_moves_crop_and_bubble(qapp):
    dm = _make()
    b0 = QPointF(dm._bubble_pos)
    dm.manip_translate(50, 30)
    assert dm._crop_rect.topLeft() == QPointF(50, 30)
    assert dm._bubble_pos == QPointF(b0.x() + 50, b0.y() + 30)


def test_frame_shows_as_bounding_box(qapp):
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(500, 500); view.show()
    qapp.processEvents()
    dm = _make(); scene.addItem(dm)
    m = SelectionManipulator(scene)
    dm.setSelected(True); qapp.processEvents()
    assert dm in m.selection_items()
    assert m.provides_handles_for(dm) is False         # parametric, not box-native
    assert m._frame_is_redundant() is False            # frame IS the visible box


def test_clip_view_gate(qapp):
    from firepro3d.selection_manipulator import _painting_into_clip_view
    assert _painting_into_clip_view(None) is False
    scene = QGraphicsScene(); view = QGraphicsView(scene)
    assert _painting_into_clip_view(view.viewport()) is False
    view._clip_rect = QRectF(0, 0, 100, 100)
    assert _painting_into_clip_view(view.viewport()) is True


def test_render_overlay_draws_in_detail_view(qapp):
    from PyQt6.QtGui import QImage, QPainter
    scene = QGraphicsScene()
    view = QGraphicsView(scene); view.resize(400, 400)
    view._clip_rect = QRectF(0, 0, 200, 100); view.show()
    qapp.processEvents()
    dm = _make(); scene.addItem(dm)
    m = SelectionManipulator(scene)
    dm.setSelected(True); qapp.processEvents()
    img = QImage(400, 400, QImage.Format.Format_ARGB32); img.fill(0)
    p = QPainter(img)
    m.render_overlay(view, p)
    p.end()
    drawn = [(x, y) for x in range(0, 400, 8) for y in range(0, 400, 8)
             if img.pixelColor(x, y).alpha() != 0]
    assert drawn != []                                 # frame + grips rendered
