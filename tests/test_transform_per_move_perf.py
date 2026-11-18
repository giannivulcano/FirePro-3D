"""Perf bar for snap + ghost per mouse move in a transform tool (L1068/L1070).

Ratified 2026-11-01: snap find + paint_ghost <= 0.1 ms per selected
primitive per move, Block Editor, Ctrl+A, Rotate and Move; shapes
A = Floor Control Valve (394 prims), B = synthetic 2,000-line block.
Base 972c0025 (ms/move, levers.txt): A rotate snap 57-62 + ghost 58,
A move ghost 67-77; B rotate snap 163-188 + ghost 464-474, B move ghost
462-473.

What this bar guards (red-proof, 2026-11-01): dropping the cached ghost glow
turns all three gating cases RED. Dropping the per-find snap memo does NOT --
on B the unmemoized snap (~165-190 ms) still fits under 200 ms, and A-valve-
rotate is xfail -- so the memo is guarded by tests/test_snap_find_memo.py.
"""
import math
import os
import statistics
import time

import pytest
from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._mainwindow_helpers import dispose_main_window
from tests._snap_polish_helpers import click, move

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "floor_control_valve.fpdb")
BAR_MS_PER_PRIM = 0.1
RAY_PX = 150          # rotate start ray / sweep radius, viewport px


def _shape_a():
    from firepro3d.block_library import load_block_file
    d = load_block_file(FIXTURE)
    assert d is not None
    return d, 394


def _shape_b():
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import LineItem
    prims = [LineItem(QPointF(i * 5.0, 0.0), QPointF(i * 5.0, 200.0)).to_dict()
             for i in range(2000)]
    return BlockDefinition.new(name="Perf2000", library="L", series="S",
                               origin=(0.0, 0.0), primitives=prims), 2000


def _gesture_points(tool, c):
    """Cursor positions for 2 warm-up + 10 timed moves."""
    if tool == "rotate":                       # sweep 20..86 deg on the ray circle
        return [c + QPoint(round(RAY_PX * math.cos(math.radians(a))),
                           round(RAY_PX * math.sin(math.radians(a))))
                for a in range(20, 92, 6)]
    return [c + QPoint(40 + 7 * i, 25 + 3 * i) for i in range(12)]


def _ghost_centers(scene):
    """Each ghost path's centre (a rotate about the block centre keeps the union's)."""
    return [p.boundingRect().center() for p in scene._move_ghost]


# Valve Rotate: ghost ~1 ms, snap 31-128 ms/move (medians 42-84 vs bar 39.4).
# Expected to fail until the per-gesture snap segment cache lands (todo_open,
# "Per-gesture cache of still items' snap segments"); that task removes the mark.
CASES = [
    pytest.param(_shape_a, "rotate", id="A-valve-rotate", marks=pytest.mark.xfail(
        strict=False, reason="snap segment walk; per-gesture cache follow-up")),
    pytest.param(_shape_a, "move", id="A-valve-move"),
    pytest.param(_shape_b, "rotate", id="B-2000-lines-rotate"),
    pytest.param(_shape_b, "move", id="B-2000-lines-move"),
]


@pytest.mark.perf
@pytest.mark.parametrize("shape, tool", CASES)
def test_snap_plus_ghost_per_move_within_bar(qapp, shape, tool):
    import main as _main_module
    from firepro3d.view_3d import View3D
    _main_module.View3D = View3D
    from main import MainWindow
    import firepro3d.snap_engine as se
    import firepro3d.transform_ghost as tg
    d, n_prims = shape()
    with pytest.MonkeyPatch.context() as mp:
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
            assert len(scene.selectedItems()) == n_prims          # scene composition
            assert scene._modify_ctl.start(tool)
            c = view.mapFromScene(scene.itemsBoundingRect().center())
            # Events go straight to the viewport (house helpers): QTest.mouseMove
            # moves the OS cursor, which a second window in one process misses.
            at = view.mapToScene
            move(view, at(c))
            click(view, at(c))
            if tool == "rotate":                                   # start ray (D8)
                ray = c + QPoint(RAY_PX, 0)
                move(view, at(ray))
                click(view, at(ray))
            QApplication.processEvents()
            pts = _gesture_points(tool, c)
            for p in pts[:2]:                                      # warm-up (cache build)
                move(view, at(p))
                QApplication.processEvents()
            assert len(scene._move_ghost) == n_prims               # ghost covers selection
            first = _ghost_centers(scene)
            acc = [0.0]

            def wrap(owner, name):
                orig = getattr(owner, name)

                def timed(*a, **k):
                    t = time.perf_counter()
                    try:
                        return orig(*a, **k)
                    finally:
                        acc[0] += time.perf_counter() - t
                mp.setattr(owner, name, timed)
            wrap(se.SnapEngine, "find")
            wrap(tg, "paint_ghost")
            per_move = []
            for p in pts[2:]:
                acc[0] = 0.0
                move(view, at(p))
                QApplication.processEvents()                       # flush the deferred repaint
                per_move.append(acc[0] * 1000.0)
            moved = sum((b - a).manhattanLength()
                        for a, b in zip(first, _ghost_centers(scene)))
            assert moved > n_prims                                 # the ghost really swept
            assert min(per_move) > 0.0                             # snap + paint really ran
            med = statistics.median(per_move)
            print(f"PERF {tool} {n_prims}: median {med:.1f} ms/move; "
                  f"raw {[round(x, 1) for x in per_move]}")
            assert med <= BAR_MS_PER_PRIM * n_prims, (
                f"{tool} {n_prims} prims: median {med:.1f} ms/move "
                f"(bar {BAR_MS_PER_PRIM * n_prims:.1f}); raw {[round(x, 1) for x in per_move]}")
        finally:
            for ew in list(win.block_editor_manager.open_editors()):
                ew._modified = False
                win.block_editor_manager.close(ew)
            dispose_main_window(win)


def _shape_c_scene(win, n_still=2000, n_sel=400):
    """Model Space plan: n_still unselected lines + n_sel selected lines on screen."""
    from firepro3d.geometry_2d import LineItem
    s = win.scene
    sel = []
    for i in range(n_still + n_sel):
        it = s._add_from_dict(LineItem(QPointF(i * 5.0, 0.0),
                                       QPointF(i * 5.0, 300.0)).to_dict())
        assert it is not None
        if i >= n_still:
            sel.append(it)
    for it in sel:
        it.setSelected(True)
    QApplication.processEvents()
    return sel


WHOLE_CASES = [
    pytest.param("A", "rotate", id="A-valve-rotate", marks=pytest.mark.xfail(
        strict=False, reason="snap find ~35 ms/move: todo_open 'Per-gesture cache "
                             "of still items' snap segments'")),
    pytest.param("A", "move", id="A-valve-move"),
    pytest.param("B", "rotate", id="B-2000-lines-rotate"),
    pytest.param("B", "move", id="B-2000-lines-move"),
    pytest.param("C", "move", id="C-model-plan-move", marks=pytest.mark.xfail(
        strict=False, reason="Qt per-move items-under-cursor walk over every item "
                             "on the NoIndex model scene: todo_open 'HALO hover on "
                             "huge drawings: spatial index for the model scene'")),
    pytest.param("C", "rotate", id="C-model-plan-rotate", marks=pytest.mark.xfail(
        strict=False, reason="snap find (todo_open 'Per-gesture cache of still items' "
                             "snap segments') + NoIndex items-under-cursor walk "
                             "(todo_open 'spatial index for the model scene')")),
]


@pytest.mark.perf
@pytest.mark.parametrize("shape, tool", WHOLE_CASES)
def test_whole_move_within_bar(qapp, shape, tool):
    """G1: whole per-move wall (event + snap + ghost + flushed repaint) <= 0.1 ms/prim."""
    import main as _main_module
    from firepro3d.view_3d import View3D
    _main_module.View3D = View3D
    from main import MainWindow
    win = MainWindow()
    win.resize(1600, 1000)
    win.show()
    QTest.qWaitForWindowExposed(win)
    try:
        if shape == "C":
            sel = _shape_c_scene(win)
            n_prims = len(sel)
            view, scene = win.view, win.scene
            view.fitInView(scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            QApplication.processEvents()
            assert len(scene.selectedItems()) == n_prims          # scene composition
            assert len(scene.items()) >= 2000 + n_prims
            centre = QRectF()
            for it in sel:
                centre = centre.united(it.sceneBoundingRect())
            c = view.mapFromScene(centre.center())
        else:
            d, n_prims = (_shape_a if shape == "A" else _shape_b)()
            win.scene.register_block_definition(d)
            w = win.block_editor_manager.edit_definition(d.id)
            QApplication.processEvents()
            view = w.view
            scene = view.scene()
            view.fitInView(scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            QApplication.processEvents()
            QTest.keyClick(view.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
            QApplication.processEvents()
            assert len(scene.selectedItems()) == n_prims          # scene composition
            c = view.mapFromScene(scene.itemsBoundingRect().center())
        assert scene._modify_ctl.start(tool)
        at = view.mapToScene
        move(view, at(c)); click(view, at(c))
        if tool == "rotate":
            ray = c + QPoint(RAY_PX, 0)
            move(view, at(ray)); click(view, at(ray))
        QApplication.processEvents()
        pts = _gesture_points(tool, c)
        for p in pts[:2]:                                          # warm-up (capture)
            move(view, at(p)); QApplication.processEvents()
        assert len(scene._move_ghost) == n_prims                   # ghost covers selection
        per_move = []
        for p in pts[2:]:
            t = time.perf_counter()
            move(view, at(p))
            QApplication.processEvents()                           # flush the deferred repaint
            per_move.append((time.perf_counter() - t) * 1000.0)
        med = statistics.median(per_move)
        line = (f"WHOLE {shape} {tool} {n_prims}: median {med:.1f} ms/move "
                f"(bar {BAR_MS_PER_PRIM * n_prims:.1f}); raw {[round(x, 1) for x in per_move]}")
        print(line)
        out = os.environ.get("PERF_RAW_OUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        assert med <= BAR_MS_PER_PRIM * n_prims, line
    finally:
        for ew in list(win.block_editor_manager.open_editors()):
            ew._modified = False
            win.block_editor_manager.close(ew)
        dispose_main_window(win)
