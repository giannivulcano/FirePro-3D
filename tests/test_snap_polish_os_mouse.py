"""Guard: the shared shown view (``_snap_polish_helpers.make_view``) is deaf to
the real OS mouse (test-harness Invariant 9).

Flake root cause (2026-10-15, block-snap parity): a real cursor over the
shown window delivered spontaneous MouseMoves between a test's posted move
and its read of ``_snap_result``, re-aiming the snap at the real cursor. A
window-system move (``QTest.mouseMove`` on the QWindow: spontaneous, the real
cursor stays put) reproduces it; the harness view must ignore it.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from firepro3d.geometry_2d import LineItem
from tests._snap_polish_helpers import close_view, make_view, move

# Far from the line: no snap there. Not the flip/mirror guard's (-300, 250):
# Qt drops a window-system move to the position it already holds, so a second
# guard in the same process aiming there would see no OS move at all.
_EMPTY = QPointF(-250.0, -220.0)


def test_os_mouse_input_cannot_reaim_the_snap(qapp):
    view, scene = make_view(scale=1.0, mode="draw_line")
    seen = []

    class _Spy(QObject):
        def eventFilter(self, obj, ev):  # noqa: N802 (Qt naming)
            if (obj is view.viewport() and ev.type() == QEvent.Type.MouseMove
                    and ev.spontaneous()):
                seen.append(ev.position().toPoint())
            return False
    spy = _Spy()
    QApplication.instance().installEventFilter(spy)
    try:
        scene.addItem(LineItem(QPointF(0.0, 0.0), QPointF(100.0, 0.0)))
        move(view, QPointF(101.0, 1.0))
        r = scene._snap_result
        assert r is not None and r.snap_type == "endpoint"      # precondition
        want = (round(r.point.x(), 2), round(r.point.y(), 2))
        win = view.window()
        at = view.viewport().mapTo(win, view.mapFromScene(_EMPTY))
        QTest.mouseMove(win.windowHandle(), at)
        QApplication.processEvents()
        assert seen                                       # the OS move arrived
        r = scene._snap_result
        assert r is not None and r.snap_type == "endpoint"                # [RED]
        assert (round(r.point.x(), 2), round(r.point.y(), 2)) == want
    finally:
        QApplication.instance().removeEventFilter(spy)
        close_view(view, scene)
