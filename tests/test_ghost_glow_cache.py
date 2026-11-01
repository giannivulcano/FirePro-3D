"""Cached ghost glow (L1068): GhostFrame paints like the live glow."""
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage, QPainter, QPainterPath, QTransform

from firepro3d import theme as th
from firepro3d import transform_ghost as tg


def _base():
    out = []
    for i in range(20):
        p = QPainterPath()
        p.moveTo(100 + i * 8, 100)
        p.lineTo(100 + i * 8, 300)
        out.append(p)
    return out


def _render(paths, world):
    img = QImage(600, 500, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    pt = QPainter(img)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pt.setWorldTransform(world)
    tg.paint_ghost(pt, paths, th.detect())
    pt.end()
    return img


def _stats(a, b):
    """Mean per-pixel gap over every channel of the raw premultiplied bytes."""
    tot = n = 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            pa, pb = a.pixel(x, y), b.pixel(x, y)
            tot += sum(abs(((pa >> s) & 255) - ((pb >> s) & 255))
                       for s in (0, 8, 16, 24))
            n += 1
    return tot / n


def _alpha_sum(img):
    return sum(img.pixelColor(x, y).alpha()
               for y in range(0, img.height(), 2) for x in range(0, img.width(), 2))


W = QTransform.fromScale(0.5, 0.5) * QTransform.fromTranslate(30, 20)


def test_translate_frame_matches_live(qapp):
    tg.release_glow_cache()
    base = _base()
    frame = tg.GhostFrame(base, QTransform.fromTranslate(40, 20))
    live = _render(list(frame), W)                  # plain list -> live glow
    got = _render(frame, W)
    assert tg._GLOW_CACHE.cached_base(got) is base  # the cache was used
    assert _alpha_sum(got) > 0
    assert _stats(live, got) < 1.0


def test_rotate_frame_matches_live(qapp):
    tg.release_glow_cache()
    base = _base()
    x = QTransform().translate(200, 200).rotate(30).translate(-200, -200)
    frame = tg.GhostFrame(base, x)
    live, got = _render(list(frame), W), _render(frame, W)
    assert tg._GLOW_CACHE.cached_base(got) is base
    assert _stats(live, got) < 3.0                  # soft glow resampled
    assert abs(_alpha_sum(got) - _alpha_sum(live)) / _alpha_sum(live) < 0.05


def test_zoom_change_rebuilds(qapp):
    tg.release_glow_cache()
    frame = tg.GhostFrame(_base(), QTransform.fromTranslate(40, 20))
    _render(frame, W)
    w2 = QTransform.fromScale(1.0, 1.0) * QTransform.fromTranslate(10, 5)
    assert _stats(_render(list(frame), w2), _render(frame, w2)) < 1.0


def test_non_rigid_uses_live_glow(qapp):
    tg.release_glow_cache()
    frame = tg.GhostFrame(_base(), QTransform.fromScale(2.0, 2.0))
    got = _render(frame, W)
    assert _stats(_render(list(frame), W), got) == 0
    assert tg._GLOW_CACHE.cached_base(got) is None


def _render_dpr(paths, world, dpr):
    img = QImage(round(600 * dpr), round(500 * dpr),
                 QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(0)
    pt = QPainter(img)
    pt.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pt.setWorldTransform(world)
    tg.paint_ghost(pt, paths, th.detect())
    pt.end()
    return img


_XFORMS = {
    "translate": QTransform.fromTranslate(40, 20),
    "rotate": QTransform().translate(200, 200).rotate(30).translate(-200, -200),
    "reflect": tg.reflect_transform(QPointF(150, 0), QPointF(250, 400)),
}


@pytest.mark.parametrize("dpr", [1.0, 1.25, 2.0])
@pytest.mark.parametrize("kind", list(_XFORMS))
def test_cached_glow_matches_live_across_dpr(qapp, kind, dpr):
    """Review I2: the cache math holds on HiDPI devices and under reflection."""
    tg.release_glow_cache()
    base = _base()
    frame = tg.GhostFrame(base, _XFORMS[kind])
    live, got = _render_dpr(list(frame), W, dpr), _render_dpr(frame, W, dpr)
    assert tg._GLOW_CACHE.cached_base(got) is base
    assert _stats(live, got) < 3.0
    assert abs(_alpha_sum(got) - _alpha_sum(live)) / _alpha_sum(live) < 0.05


def test_release_is_per_device(qapp):
    """Review I1: a view with no ghost releases only its own image."""
    tg.release_glow_cache()
    frame = tg.GhostFrame(_base(), QTransform.fromTranslate(40, 20))
    a = _render(frame, W)
    other = QImage(10, 10, QImage.Format.Format_ARGB32_Premultiplied)
    tg.release_glow_cache(other)
    assert tg._GLOW_CACHE.cached_base(a) is frame.base
    tg.release_glow_cache(a)
    assert tg._GLOW_CACHE.cached_base(a) is None


def test_two_devices_at_two_zooms_build_once_each(qapp, monkeypatch):
    """Review I1: two views of one gesture don't evict each other per paint."""
    tg.release_glow_cache()
    builds = []
    orig = tg._GlowCache._build
    monkeypatch.setattr(tg._GlowCache, "_build", staticmethod(
        lambda *a: builds.append(1) or orig(*a)))
    frame = tg.GhostFrame(_base(), QTransform.fromTranslate(40, 20))
    w2 = QTransform.fromTranslate(10, 5)
    imgs = [QImage(600, 500, QImage.Format.Format_ARGB32_Premultiplied) for _ in range(2)]
    for _ in range(3):
        for img, world in zip(imgs, (W, w2)):
            img.fill(0)
            pt = QPainter(img)
            pt.setWorldTransform(world)
            tg.paint_ghost(pt, frame, th.detect())
            pt.end()
    assert len(builds) == 2
    assert all(tg._GLOW_CACHE.cached_base(img) is frame.base for img in imgs)


def test_oversize_verdict_is_kept(qapp, monkeypatch):
    """Too big to cache: live glow, and the size check doesn't re-run per paint."""
    tg.release_glow_cache()
    monkeypatch.setattr(tg, "GHOST_GLOW_CACHE_MAX_PX", 1)
    builds = []
    orig = tg._GlowCache._build
    monkeypatch.setattr(tg._GlowCache, "_build", staticmethod(
        lambda *a: builds.append(1) or orig(*a)))
    frame = tg.GhostFrame(_base(), QTransform.fromTranslate(40, 20))
    img = QImage(600, 500, QImage.Format.Format_ARGB32_Premultiplied)
    for _ in range(3):
        img.fill(0)
        pt = QPainter(img)
        pt.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pt.setWorldTransform(W)
        tg.paint_ghost(pt, frame, th.detect())
        pt.end()
    assert len(builds) == 1
    assert tg._GLOW_CACHE.cached_base(img) is None
    assert _stats(_render(list(frame), W), img) == 0          # the live glow


def test_frame_is_the_mapped_list(qapp):
    base = _base()
    x = QTransform.fromTranslate(5, 7)
    frame = tg.GhostFrame(base, x)
    assert isinstance(frame, list) and len(frame) == len(base)
    assert frame[0].boundingRect() == x.map(base[0]).boundingRect()


def test_editor_rotate_cached_glow_matches_live(qapp, tmp_path):
    """Real Block Editor Rotate on the valve: cached-glow grab == live-glow grab."""
    import os

    import pytest
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    import main as _main_module
    from firepro3d.view_3d import View3D
    _main_module.View3D = View3D
    from main import MainWindow
    from firepro3d.block_library import load_block_file
    from tests._mainwindow_helpers import dispose_main_window

    d = load_block_file(os.path.join(os.path.dirname(__file__), "fixtures",
                                     "floor_control_valve.fpdb"))
    assert d is not None
    tg.release_glow_cache()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MainWindow, "_autosave_path",
                   staticmethod(lambda: str(tmp_path / "recovery.FPD")))
        win = MainWindow()
        win.resize(1600, 1000)
        win.show()
        QTest.qWaitForWindowExposed(win)
        try:
            win.scene.register_block_definition(d)
            w = win.block_editor_manager.edit_definition(d.id)
            QApplication.processEvents()
            view = w.view
            scene = view.scene()
            view.fitInView(scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            QApplication.processEvents()
            QTest.keyClick(view.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QApplication.processEvents()
            assert scene._modify_ctl.start("rotate")
            c = view.mapFromScene(scene.itemsBoundingRect().center())
            QTest.mouseMove(view.viewport(), c)
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=c)
            ray = c + QPoint(150, 0)                            # start ray (D8)
            QTest.mouseMove(view.viewport(), ray)
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=ray)
            QTest.mouseMove(view.viewport(), c + QPoint(90, 120))   # ~53 deg sweep
            QApplication.processEvents()
            ghost = scene._move_ghost
            assert isinstance(ghost, tg.GhostFrame) and len(ghost) > 100
            assert abs(ghost.xform.m12()) > 0.5                 # really rotated
            view.viewport().repaint()
            QApplication.processEvents()
            got = view.viewport().grab().toImage()
            assert tg._GLOW_CACHE.cached_base(view.viewport()) is ghost.base
            mp.setattr(tg._GLOW_CACHE, "paint", lambda *a: False)   # live glow
            view.viewport().repaint()
            QApplication.processEvents()
            live = view.viewport().grab().toImage()
            mp.setattr(tg._GLOW_CACHE, "paint", lambda *a: True)    # no glow at all
            view.viewport().repaint()
            QApplication.processEvents()
            bare = view.viewport().grab().toImage()
            assert got.size() == live.size() == bare.size()
            # A whole-viewport mean dilutes a misplaced glow, so judge the
            # cache's gap against the glow's own footprint (live vs bare).
            signal = _stats(live, bare)
            assert signal > 0.5, signal                         # the glow is visible
            assert _stats(live, got) < 0.25 * signal, (_stats(live, got), signal)
        finally:
            for ew in list(win.block_editor_manager.open_editors()):
                ew._modified = False
                win.block_editor_manager.close(ew)
            dispose_main_window(win)
