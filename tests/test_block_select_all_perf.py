"""Perf bar for Block Editor Select All + Rotate commit (2026-10-31, P1).

Ratified bar: each <= 1 ms per selected primitive, headless median of 3,
shapes A = the Floor Control Valve block and B = a synthetic 2,000-line
block. Was 7.5 s (Ctrl+A) and > 9 min (rotate) on A.
"""
import os
import statistics
import time

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from tests._mainwindow_helpers import dispose_main_window

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "floor_control_valve.fpdb")


def _shape_a():
    from firepro3d.block_library import load_block_file
    d = load_block_file(FIXTURE)
    assert d is not None
    return d, 394                                 # measured selectedItems() after Ctrl+A


def _shape_b():
    from firepro3d.block_definition import BlockDefinition
    from firepro3d.geometry_2d import LineItem
    prims = [LineItem(QPointF(i * 5.0, 0.0), QPointF(i * 5.0, 200.0)).to_dict()
             for i in range(2000)]
    return BlockDefinition.new(name="Perf2000", library="L", series="S",
                               origin=(0.0, 0.0), primitives=prims), 2000


def _timed(fn):
    t0 = time.perf_counter()
    fn()
    QApplication.processEvents()              # flush deferred repaints / timers
    return time.perf_counter() - t0


@pytest.mark.perf
@pytest.mark.parametrize("shape", [_shape_a, _shape_b], ids=["A-valve", "B-2000-lines"])
def test_select_all_and_rotate_commit_within_1ms_per_primitive(qapp, tmp_path, shape):
    import main as _main_module
    from firepro3d.view_3d import View3D
    _main_module.View3D = View3D
    from main import MainWindow
    d, min_prims = shape()
    recovery = str(tmp_path / "recovery.FPD")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
        win = MainWindow()
        win.show()
        QTest.qWaitForWindowExposed(win)
        try:
            win.scene.register_block_definition(d)
            w = win.block_editor_manager.edit_definition(d.id)
            QApplication.processEvents()
            view = w.view
            scene = view.scene()
            sel_t, rot_t = [], []
            for rep in range(3):
                scene.clearSelection()
                QApplication.processEvents()
                sel_t.append(_timed(lambda: QTest.keyClick(
                    view.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)))
                n = len(scene.selectedItems())
                assert n >= min_prims, f"scene composition: {n} selected"
                # The panel show is part of the timed cost: prove it ran.
                assert len(win.prop_manager._targets) >= min_prims, \
                    "property panel was not shown for the selection"
                assert scene._modify_ctl.start("rotate")
                c = view.mapFromScene(scene.itemsBoundingRect().center())
                QTest.mouseMove(view.viewport(), c)
                QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=c)
                QApplication.processEvents()

                def _commit():
                    assert scene.begin_dynamic_input() is True
                    scene.dynamic_input.editor("Angle").setText("15")
                    scene.dynamic_input._accept()
                rot_t.append(_timed(_commit))
                assert len(scene.selectedItems()) == n     # D3: rotated items reselected
            bar = 0.001 * n
            line = f"shape={shape.__name__} n={n} bar={bar:.3f} select={sel_t} rotate={rot_t}\n"
            with open(tmp_path / "bench.txt", "w") as fh:  # raw lines for the record
                fh.write(line)
            print(line, end="")
            assert statistics.median(sel_t) <= bar, f"Ctrl+A {sel_t} > {bar:.3f}s"
            assert statistics.median(rot_t) <= bar, f"rotate commit {rot_t} > {bar:.3f}s"
        finally:
            for ew in list(win.block_editor_manager.open_editors()):
                ew._modified = False
                win.block_editor_manager.close(ew)
            dispose_main_window(win)
