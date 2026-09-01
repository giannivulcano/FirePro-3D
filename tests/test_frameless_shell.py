from PyQt6.QtWidgets import QDialog
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QEvent
from firepro3d.frameless_shell import FramelessShellMixin


class _Host(FramelessShellMixin, QDialog):
    def __init__(self):
        super().__init__()
        self.init_frameless_shell(title="Host", controls=("min", "max", "close"), resizable=True)


def test_shell_is_frameless_with_three_controls(qapp):
    h = _Host()
    assert h.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert {"min", "max", "close"} <= set(h._win_controls.keys())
    h.deleteLater()


def test_double_click_titlebar_toggles_maximize(qapp):
    h = _Host()
    h.show(); qapp.processEvents()
    assert not h.isMaximized()

    # Drive the REAL event handler (not _toggle_max directly): the mixin's
    # mouseDoubleClickEvent hit-tests event.position() against the titlebar.
    center = h._titlebar.geometry().center()
    ev = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(center),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(h, ev)
    qapp.processEvents()
    assert h.isMaximized()

    # Toggle back.
    center2 = h._titlebar.geometry().center()
    ev2 = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(center2),
                      Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                      Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(h, ev2)
    qapp.processEvents()
    assert not h.isMaximized()
    h.deleteLater()


def test_edge_at_detects_corners_and_sides(qapp):
    h = _Host()
    h.setGeometry(100, 100, 400, 300)
    m = h._RESIZE_MARGIN
    w, h_ = h.rect().width(), h.rect().height()

    # Corners.
    assert h._edge_at(QPoint(1, 1)) == "tl"
    assert h._edge_at(QPoint(w - 1, 1)) == "tr"
    assert h._edge_at(QPoint(1, h_ - 1)) == "bl"
    assert h._edge_at(QPoint(w - 1, h_ - 1)) == "br"

    # Sides (well away from the corners so only one axis is within the margin).
    assert h._edge_at(QPoint(1, h_ // 2)) == "l"
    assert h._edge_at(QPoint(w - 1, h_ // 2)) == "r"
    assert h._edge_at(QPoint(w // 2, 1)) == "t"
    assert h._edge_at(QPoint(w // 2, h_ - 1)) == "b"

    # Center → no edge.
    assert h._edge_at(QPoint(w // 2, h_ // 2)) is None

    # Just inside the margin still None (defensive: point past the margin band).
    assert h._edge_at(QPoint(m + 5, h_ // 2)) is None
    h.deleteLater()


def test_perform_resize_is_pixel_exact_and_respects_min_size(qapp):
    h = _Host()
    h.setMinimumSize(200, 150)
    h.setGeometry(100, 100, 400, 300)

    # Mirror the press-capture that mousePressEvent does on an edge grab.
    def _capture(edge):
        h._resize_edge = edge
        h._resize_origin = QPoint(0, 0)
        h._resize_geom = h.geometry()

    # Shrink from the right/bottom by an exact delta → width/height must be exact
    # (this is the regression guard for the QRect inclusive-edge off-by-one).
    _capture("br")
    h._perform_resize(QPoint(-40, -30))  # dx=-40, dy=-30
    assert h.geometry().width() == 360
    assert h.geometry().height() == 270

    # Drive well past the min size → must clamp to EXACTLY the minimum.
    h.setGeometry(100, 100, 400, 300)
    _capture("br")
    h._perform_resize(QPoint(-1000, -1000))
    assert h.geometry().width() == 200
    assert h.geometry().height() == 150

    # Left/top edge shrink is also pixel-exact.
    h.setGeometry(100, 100, 400, 300)
    _capture("tl")
    h._perform_resize(QPoint(40, 30))  # move left/top edges inward
    assert h.geometry().width() == 360
    assert h.geometry().height() == 270
    h.deleteLater()
