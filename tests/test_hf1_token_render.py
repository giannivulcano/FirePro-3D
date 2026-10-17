"""HF1 render guards G8a/G8b/G8c (hatch-and-fill.md § HF1 verification)."""
import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsView

from firepro3d import theme
from firepro3d.block_definition import BlockDefinition
from firepro3d.constants import TOKEN_AUTO
from firepro3d.geometry_2d import LineItem
from firepro3d.model_space import Model_Space


@pytest.fixture
def force_theme(monkeypatch):
    def _set(name):
        monkeypatch.setattr(theme, "theme_preference", lambda: name)
    return _set


def _token_block(ms, colour, bid="tok"):
    ln = LineItem(QPointF(-500, 0), QPointF(500, 0), colour)
    d = BlockDefinition.new(name=bid, library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0, 0))
    ms.register_block_definition(d)
    return ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)


def _shown_pixels(ms):
    """Every opaque non-background colour on a shown view of *ms*."""
    v = QGraphicsView(ms)
    v.resize(400, 200)
    v.show()
    QTest.qWaitForWindowExposed(v)
    v.fitInView(QRectF(-600, -100, 1200, 200))
    v.viewport().repaint()
    img = v.viewport().grab().toImage()
    bg = img.pixelColor(2, 2).name()
    out = {img.pixelColor(x, y).name()
           for x in range(img.width()) for y in range(img.height())} - {bg}
    v.close()
    return out


@pytest.mark.parametrize("name,ink", [("dark", "#e6e9ec"), ("light", "#1c2024")])
def test_g8a_block_line_draws_theme_ink(qapp, force_theme, name, ink):
    force_theme(name)
    ms = Model_Space()
    _token_block(ms, TOKEN_AUTO)
    assert ink in _shown_pixels(ms)


def test_g8a_selected_block_uses_theme_accent(qapp, force_theme):
    force_theme("light")
    ms = Model_Space()
    inst = _token_block(ms, "#ff0000")
    inst.setSelected(True)
    px = _shown_pixels(ms)
    assert "#2f9e63" in px and "#63be8b" not in px


def test_g8a_theme_switch_repaints_without_recompile(qapp, force_theme):
    """The compiled op keeps the token; ink follows the theme at paint."""
    force_theme("dark")
    ms = Model_Space()
    inst = _token_block(ms, TOKEN_AUTO)
    assert "#e6e9ec" in _shown_pixels(ms)
    force_theme("light")
    inst.update()
    px = _shown_pixels(ms)
    assert "#1c2024" in px and "#e6e9ec" not in px


# ── Task 4: paper surface (G8b, AC2) ────────────────────────────────────────
from firepro3d.constants import TOKEN_ACCENT  # noqa: E402
from firepro3d.paper_display import PaperColorMode, save_paper_color_mode  # noqa: E402
from tests.test_lt1_block_paper import _HALF_LEN, _block_strokes, _export  # noqa: E402


@pytest.mark.parametrize("mode,colour,rgb", [
    (PaperColorMode.FULL_COLOR, TOKEN_AUTO, (0.0, 0.0, 0.0)),
    (PaperColorMode.FULL_COLOR, TOKEN_ACCENT, (0x2f / 255, 0x9e / 255, 0x63 / 255)),
    (PaperColorMode.BW, TOKEN_ACCENT, (0.0, 0.0, 0.0)),
])
def test_g8b_pdf_token_colour(qapp, tmp_path, force_theme, mode, colour, rgb):
    force_theme("dark")
    save_paper_color_mode(mode)         # conftest gives each test a fresh QSettings
    ms = Model_Space()
    ln = LineItem(QPointF(-_HALF_LEN, 0), QPointF(_HALF_LEN, 0), colour)
    d = BlockDefinition.new(name="P", library="L", series="S",
                            primitives=[ln.to_dict()], origin=(0, 0))
    ms.register_block_definition(d)
    ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level)
    strokes = _block_strokes(_export(tmp_path, ms, 0.01, "g8b.pdf"), 0.01)
    assert strokes
    for _w, got in strokes:
        assert got == pytest.approx(rgb, abs=0.01)


def test_g8b_paper_text_annotation_is_black(qapp, force_theme):
    from unittest.mock import MagicMock
    from firepro3d.colour_tokens import resolve_colour
    from firepro3d.paper_space import PaperScene, Sheet, ViewResolver
    from firepro3d.text_item import TextAnnotationData, TextItem
    force_theme("dark")
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    sc = PaperScene(Sheet.create_default(), MagicMock(spec=ViewResolver))
    t = TextItem(TextAnnotationData(text="A"))
    sc.addItem(t)
    assert t._data.color == TOKEN_AUTO          # the real default (AC5)
    assert resolve_colour(t._data.color, item=t).name() == "#000000"
    assert t.defaultTextColor().name() == "#000000"


def test_g8b_titleblock_previews_resolve_tokens_as_paper(qapp, force_theme):
    """The real editor / arrange scenes are paper surfaces: token:auto is black
    even under the dark theme (white preview background)."""
    from firepro3d.colour_tokens import resolve_colour
    from firepro3d.titleblock_arrange import StripCanvas
    from firepro3d.titleblock_editor import TitleBlockEditorDialog
    from PyQt6.QtWidgets import QGraphicsRectItem
    force_theme("dark")
    save_paper_color_mode(PaperColorMode.FULL_COLOR)
    dlg = TitleBlockEditorDialog(project_template=None)
    canvas = StripCanvas()
    scenes = [dlg._preview_scene, dlg._field_preview_scene, canvas._scene]
    for sc in scenes:
        it = QGraphicsRectItem(0, 0, 1, 1)
        sc.addItem(it)
        assert resolve_colour(TOKEN_AUTO, item=it).name() == "#000000"
        assert resolve_colour(TOKEN_ACCENT, item=it).name() == "#2f9e63"


# ---------------------------------------------------------------------------
# T6: theme bus + live-scene refresh (AC3, G8c)
# ---------------------------------------------------------------------------

def test_g8c_live_switch_flips_pixel_and_text(qapp, force_theme):
    from firepro3d.text_item import TextAnnotationData, TextItem
    from firepro3d.view_3d import View3D  # noqa: F401 -- heavy import before MainWindow
    import main as _main_module
    _main_module.View3D = View3D
    from main import MainWindow
    from tests._mainwindow_helpers import dispose_main_window
    force_theme("dark")
    win = MainWindow()
    try:
        win.show()
        QTest.qWaitForWindowExposed(win)
        ms = win.scene
        t = TextItem(TextAnnotationData(text="A"))
        ms.addItem(t)
        _token_block(ms, TOKEN_AUTO)
        assert t.defaultTextColor().name() == "#e6e9ec"
        assert "#e6e9ec" in _shown_pixels(ms)
        force_theme("light")
        win._apply_theme()                       # the real switch entry point
        assert t.defaultTextColor().name() == "#1c2024"
        assert "#1c2024" in _shown_pixels(ms)
    finally:
        dispose_main_window(win)


def test_theme_bus_is_a_singleton_with_changed_signal(qapp):
    bus = theme.theme_bus()
    assert bus is theme.theme_bus()
    hits = []
    bus.changed.connect(lambda: hits.append(1))
    bus.changed.emit()
    assert hits == [1]


def test_disposed_main_window_does_not_leak_a_bus_slot(qapp, force_theme):
    from firepro3d.view_3d import View3D  # noqa: F401
    import main as _main_module
    _main_module.View3D = View3D
    from main import MainWindow
    from tests._mainwindow_helpers import dispose_main_window
    force_theme("dark")
    win = MainWindow()
    dispose_main_window(win)
    theme.theme_bus().changed.emit()      # must not touch the dead window


def test_font_swatch_follows_theme_switch_without_resync(qapp, force_theme):
    from firepro3d.font_group import FontGroupController
    force_theme("dark")
    fg = FontGroupController(get_targets=lambda: [])
    try:
        fg._set_swatch(TOKEN_AUTO)
        assert "#e6e9ec" in fg.color_btn.styleSheet()
        force_theme("light")
        theme.theme_bus().changed.emit()
        assert "#1c2024" in fg.color_btn.styleSheet()
        assert fg._swatch == TOKEN_AUTO
    finally:
        fg.container.deleteLater()
        fg.deleteLater()


def test_font_group_deleted_does_not_break_later_emits(qapp, force_theme):
    from PyQt6 import sip
    from firepro3d.font_group import FontGroupController
    force_theme("dark")
    fg = FontGroupController(get_targets=lambda: [])
    sip.delete(fg)
    theme.theme_bus().changed.emit()      # must not raise or crash
