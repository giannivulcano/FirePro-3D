"""D11: ghost traces drawn geometry (halo_scene_path); originals dimmed 35% and restored."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from firepro3d.halo import halo_scene_path
from tests._modify_tools_helpers import add_primitive
from tests._snap_polish_helpers import click, close_view, make_view, move


def test_ghost_base_is_the_halo_trace_not_shape(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "rect_rotated")
        scene._modify_ctl.start("move"); click(view, QPointF(0, 0))
        base = scene._move_ghost_base
        assert len(base) == 1
        exp = halo_scene_path(item).boundingRect()
        got = base[0].boundingRect()
        assert abs(got.width() - exp.width()) < 0.01            # [RED]
        assert abs(got.height() - exp.height()) < 0.01
        assert abs(got.center().x() - exp.center().x()) < 0.01
        assert abs(got.center().y() - exp.center().y()) < 0.01
    finally:
        close_view(view, scene)


def test_paste_ghost_is_the_halo_trace_of_the_record(qapp):
    """Paste ghosts (built from clipboard records) trace drawn geometry too."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "rect_rotated")
        rec = scene._clipboard_item_dicts([item])
        paths = scene._modify_ctl._clipboard_ghost_paths(rec)
        assert len(paths) == 1
        exp = halo_scene_path(item).boundingRect()
        got = paths[0].boundingRect()
        assert abs(got.width() - exp.width()) < 0.01            # [RED]
        assert abs(got.height() - exp.height()) < 0.01
    finally:
        close_view(view, scene)


def test_original_dimmed_then_restored_on_esc(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        item.setOpacity(0.8)                               # a display-manager opacity
        scene._modify_ctl.start("move")
        assert item.opacity() == pytest.approx(0.8 * 0.35)  # [RED]
        scene.set_mode(None)
        assert item.opacity() == pytest.approx(0.8)
    finally:
        close_view(view, scene)


def test_duplicate_dims_original(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "circle")
        scene._modify_ctl.start("duplicate")
        assert item.opacity() == pytest.approx(0.35)        # [RED]
        scene.set_mode("select")
        assert item.opacity() == pytest.approx(1.0)
    finally:
        close_view(view, scene)


def test_original_restored_after_commit(qapp):
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "circle")
        scene._modify_ctl.start("move")
        click(view, QPointF(0, 0)); move(view, QPointF(10, 0)); click(view, QPointF(10, 0))
        assert scene.mode in (None, "select")
        assert item.opacity() == pytest.approx(1.0)
    finally:
        close_view(view, scene)


def _hue_deg(c: QColor) -> float:
    return c.hsvHueF() * 360.0


def test_move_ghost_paints_accent_trace(qapp):
    """The live ghost renders in the theme accent (HALO + 1 px solid trace)."""
    from firepro3d import theme as th
    from firepro3d.constants import HALO_TRACE_COLOR
    view, scene = make_view(scale=1.0)
    try:
        add_primitive(scene, "line")                       # (0,0)-(100,0)
        scene._modify_ctl.start("move")
        click(view, QPointF(0, 0)); move(view, QPointF(0, 150))
        assert scene._move_ghost
        br = scene._move_ghost[0].boundingRect()
        view.viewport().repaint(); QApplication.processEvents()
        img = view.viewport().grab().toImage()
        accent = QColor(th.detect().color(HALO_TRACE_COLOR))
        vp = view.viewportTransform().map(br.center())
        dpr = img.devicePixelRatio()           # grab() is in device pixels
        cx, cy = int(round(vp.x() * dpr)), int(round(vp.y() * dpr))
        # The line sits on a pixel edge, so AA blends the 1 px trace over two
        # rows: judge the most saturated pixel across the line by its hue.
        span = max(4, int(round(4 * dpr)))
        col = [QColor(img.pixel(cx, cy + dy)) for dy in range(-span, span + 1)]
        best = max(col, key=lambda c: c.hsvSaturationF())
        assert best.hsvSaturationF() > 0.3
        dh = abs(_hue_deg(best) - _hue_deg(accent)) % 360.0
        assert min(dh, 360.0 - dh) < 10.0                   # [RED] was cyan
    finally:
        close_view(view, scene)


def test_only_transformable_items_are_dimmed(qapp):
    """A selectable item Move cannot move (an underlay-style group: no
    translate / manip_translate) keeps its opacity — nothing leaks into what
    save persists (scene_io writes underlay opacity)."""
    from PyQt6.QtWidgets import QGraphicsItem, QGraphicsItemGroup
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        grp = QGraphicsItemGroup()
        grp.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        grp.setOpacity(0.7)
        scene.addItem(grp); grp.setSelected(True)
        assert grp in scene.selectedItems()
        scene._modify_ctl.start("move")
        assert item.opacity() == pytest.approx(0.35)
        assert grp.opacity() == pytest.approx(0.7)             # [RED]
        scene.set_mode(None)
        assert grp.opacity() == pytest.approx(0.7)
    finally:
        close_view(view, scene)


def test_begin_move_from_dims_and_restores(qapp):
    """Q-B: the Block Editor import Move (begin_move_from) dims too."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "circle")
        scene.begin_move_from(QPointF(0, 0))
        assert scene.mode == "move"
        assert item.opacity() == pytest.approx(0.35)            # [RED]
        scene.set_mode(None)
        assert item.opacity() == pytest.approx(1.0)
    finally:
        close_view(view, scene)


def test_restore_keeps_an_opacity_set_mid_transform(qapp):
    """Q-C: an opacity someone else set while dimmed is not overwritten."""
    view, scene = make_view(scale=1.0)
    try:
        item, _ = add_primitive(scene, "line")
        scene._modify_ctl.start("move")
        assert item.opacity() == pytest.approx(0.35)
        item.setOpacity(0.6)                                    # e.g. display manager
        scene.set_mode(None)
        assert item.opacity() == pytest.approx(0.6)              # [RED]
    finally:
        close_view(view, scene)
