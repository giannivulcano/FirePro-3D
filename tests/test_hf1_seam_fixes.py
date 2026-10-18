"""HF1 VC9 seam-fix round guards (I1 elevation, I2/I4 latched DM consumers,
I3 per-instance overrides, M3 copy/paste/undo round-trip)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsView

from firepro3d import theme
from firepro3d.constants import TOKEN_AUTO


@pytest.fixture
def force_theme(monkeypatch):
    def _set(name):
        monkeypatch.setattr(theme, "theme_preference", lambda: name)
    return _set


def _view_pixels(scene, rect):
    """Every opaque non-background colour on a shown view of *scene*."""
    v = QGraphicsView(scene)
    v.resize(500, 300)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.fitInView(rect)
    v.viewport().repaint()
    img = v.viewport().grab().toImage()
    bg = img.pixelColor(2, 2).name()
    out = {img.pixelColor(x, y).name()
           for x in range(img.width()) for y in range(img.height())} - {bg}
    v.close()
    return out


def _floor_slab(ms):
    from firepro3d.floor_slab import FloorSlab
    slab = FloorSlab(points=[QPointF(0, 0), QPointF(4000, 0),
                             QPointF(4000, 4000), QPointF(0, 4000)])
    slab._top_mode = "absolute"
    slab._top_abs_z_mm = 3000.0
    slab._bottom_mode = "absolute"
    slab._bottom_abs_z_mm = 2000.0
    ms.addItem(slab)
    ms._floor_slabs.append(slab)
    return slab


def _token_floor_dm():
    s = QSettings("GV", "FirePro3D")        # conftest-isolated
    s.setValue("display/Floor/color", TOKEN_AUTO)
    s.setValue("display/Floor/fill", TOKEN_AUTO)
    s.setValue("display/Floor/opacity", 100)


# ── I1: elevation views resolve token DM colours ────────────────────────────

@pytest.mark.parametrize("name,ink", [("dark", "#e6e9ec"), ("light", "#1c2024")])
def test_i1_elevation_token_category_paints_theme_ink(
        qapp, force_theme, elevation_scene_for, name, ink):
    force_theme(name)
    _token_floor_dm()
    ms, elev = elevation_scene_for("north")
    _floor_slab(ms)
    elev.rebuild()
    px = _view_pixels(elev, QRectF(-500, -3500, 5000, 2000))
    assert ink in px, sorted(px)[:8]
    assert "#000000" not in px


def test_i1_elevation_flips_on_live_theme_switch(qapp, force_theme):
    from firepro3d.view_3d import View3D  # noqa: F401 -- heavy import before MainWindow
    import main as _main_module
    _main_module.View3D = View3D
    from main import MainWindow
    from tests._mainwindow_helpers import dispose_main_window
    force_theme("dark")
    prev_qss = qapp.styleSheet()
    _token_floor_dm()
    win = MainWindow()
    try:
        win.show()
        QTest.qWaitForWindowExposed(win)
        _floor_slab(win.scene)
        win.elevation_manager.open_elevation("north")
        elev = win.elevation_manager.get_scene("north")
        elev.rebuild()
        rect = QRectF(-500, -3500, 5000, 2000)
        assert "#e6e9ec" in _view_pixels(elev, rect)
        force_theme("light")
        win._apply_theme()
        px = _view_pixels(elev, rect)
        assert "#1c2024" in px and "#e6e9ec" not in px
    finally:
        dispose_main_window(win)
        qapp.setStyleSheet(prev_qss)
