"""Gesture frame cache guards (scene-tools D11 amendment, todo item 21)."""
import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._mainwindow_helpers import dispose_main_window
from tests._snap_polish_helpers import click, move

RAY_PX = 150


def _small_block(n=40):
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import LineItem
    prims = [LineItem(QPointF(i * 5.0, 0.0), QPointF(i * 5.0, 200.0)).to_dict()
             for i in range(n)]
    return BlockDefinition.new(name="FC%d" % n, library="L", series="S",
                               origin=(0.0, 0.0), primitives=prims), n


@pytest.fixture
def gesture(qapp):
    """Open a block in the Block Editor, Ctrl+A, and return a starter."""
    import main as _main_module
    from firepro3d.view_3d import View3D
    _main_module.View3D = View3D
    from main import MainWindow
    win = MainWindow()
    win.resize(1600, 1000)
    win.show()
    QTest.qWaitForWindowExposed(win)
    state = {}

    def start(tool, n=40):
        d, count = _small_block(n)
        win.scene.register_block_definition(d)
        w = win.block_editor_manager.edit_definition(d.id)
        QApplication.processEvents()
        view = w.view
        scene = view.scene()
        view.fitInView(scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        QApplication.processEvents()
        QTest.keyClick(view.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        assert len(scene.selectedItems()) == count            # scene composition
        assert scene._modify_ctl.start(tool)
        c = view.mapFromScene(scene.itemsBoundingRect().center())
        at = view.mapToScene
        move(view, at(c)); click(view, at(c))
        if tool == "rotate":
            ray = c + QPoint(RAY_PX, 0)
            move(view, at(ray)); click(view, at(ray))
        QApplication.processEvents()
        state.update(view=view, scene=scene, c=c, at=at)
        return view, scene, c, at

    yield start
    for ew in list(win.block_editor_manager.open_editors()):
        ew._modified = False
        win.block_editor_manager.close(ew)
    dispose_main_window(win)


@pytest.mark.parametrize("tool", ["move", "rotate"])
def test_no_scene_change_per_gesture_move(gesture, tool):
    """The cache survives a move only if nothing in the scene repaints per move."""
    view, scene, c, at = gesture(tool)
    for i in range(2):                                        # settle the first ghost
        move(view, at(c + QPoint(30 + 5 * i, 20))); QApplication.processEvents()
    hits = []
    scene.changed.connect(lambda rects: hits.append(len(rects)))
    for i in range(5):
        move(view, at(c + QPoint(50 + 9 * i, 25 + 4 * i))); QApplication.processEvents()
    assert scene._move_ghost, "the ghost really moved"
    assert hits == [], f"scene.changed fired per move: {hits}"


def _grab(view) -> QImage:
    return view.viewport().grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _mask_child_widgets(view, img: QImage) -> None:
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QWidget
    p = QPainter(img)
    for w in view.viewport().findChildren(QWidget):
        if w.isVisible():
            r = w.geometry()
            p.fillRect(r.adjusted(-2, -2, 2, 2), QColor("#ff00ff"))
    p.end()


def test_render_reproduces_background_and_items(gesture):
    """P4: QGraphicsView.render(viewport rect) == the paintEvent item pass."""
    view, scene, c, at = gesture("move")
    move(view, at(c + QPoint(40, 30))); QApplication.processEvents()
    ghost = scene._move_ghost
    scene._move_ghost = []                                    # foreground: no ghost
    try:
        ref = _grab(view)                                     # normal paintEvent
        vp = view.viewport()
        dpr = vp.devicePixelRatioF()
        pm = QPixmap(round(vp.width() * dpr), round(vp.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(vp.palette().color(vp.backgroundRole()))
        p = QPainter(pm)
        p.setRenderHints(view.renderHints())          # render() takes the painter's hints
        view.render(p, QRectF(0, 0, vp.width(), vp.height()), vp.rect())
        p.end()
        got = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    finally:
        scene._move_ghost = ghost
    assert got.size() == ref.size()
    # Child widgets (the dX/dY HUD) paint themselves over the viewport: not part
    # of the item pass, so they are masked out of both frames.
    _mask_child_widgets(view, ref); _mask_child_widgets(view, got)
    assert got == ref


def _uncached(view) -> QImage:
    """The same frame through the normal paint path (cache disarmed)."""
    armed = view._fc_armed
    view._fc_armed = False
    try:
        return _grab(view)
    finally:
        view._fc_armed = armed


@pytest.mark.parametrize("tool", ["move", "rotate"])
def test_cached_frame_matches_uncached_paint(gesture, tool):
    """G2: mid-gesture, the cached frame + live foreground == a full repaint."""
    view, scene, c, at = gesture(tool)
    for i in range(3):
        move(view, at(c + QPoint(40 + 6 * i, 30 + 2 * i))); QApplication.processEvents()
    assert view._fc_armed
    got = _grab(view)
    assert view._fc_pixmap is not None, "the cache path really painted"
    assert got == _uncached(view)


def test_gesture_end_releases_every_view(gesture):
    """G3: Esc (set_mode(None) -> clear) disarms and frees every view's cache."""
    view, scene, c, at = gesture("move")
    move(view, at(c + QPoint(40, 30))); QApplication.processEvents()
    _grab(view)
    assert view._fc_pixmap is not None
    scene.set_mode(None)
    QApplication.processEvents()
    for v in scene.views():
        assert not v._fc_armed and v._fc_pixmap is None


def test_item_change_mid_gesture_repaints(gesture):
    """G3: an item changed mid-gesture shows at once (scene.changed drops the cache).

    Someone else (display manager, level switch) resets a dimmed original's
    opacity mid-transform — the restore_items rule's case (D11).
    """
    view, scene, c, at = gesture("move")
    move(view, at(c + QPoint(40, 30))); QApplication.processEvents()
    before = _grab(view)
    assert view._fc_pixmap is not None, "the cache path really painted"
    for it, _prior in scene._ghost_dimmed[:10]:
        it.setOpacity(1.0)
    QApplication.processEvents()
    got = _grab(view)
    assert got != before
    assert got == _uncached(view)


def test_zoom_mid_gesture_recaptures(gesture):
    """G3: a view-transform change re-captures (no stale frame at the old zoom)."""
    view, scene, c, at = gesture("move")
    move(view, at(c + QPoint(40, 30))); QApplication.processEvents()
    _grab(view)
    view.scale(1.7, 1.7)
    QApplication.processEvents()
    assert _grab(view) == _uncached(view)
