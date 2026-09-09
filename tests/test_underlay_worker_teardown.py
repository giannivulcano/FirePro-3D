"""Guard for bug #373: an async underlay DXF worker must not outlive its scene.

If a DxfImportWorker finishes after its owning scene/view (and the view-parented
QProgressDialog) are torn down, its queued ``finished_data`` delivers into dead
C++ objects during a LATER event loop → native access violation (non-determin
istic, passes in isolation, cross-test contamination). ``Model_Space.cleanup()``
must join AND disconnect the worker so a late delivery is a harmless no-op.

The native crash itself is timing-dependent and cannot be forced deterministic
ally in a unit test; these are the structural guards (worker joined + late
delivery neutralised after teardown). Full-suite run-completion is the
run-level acceptance (see the plan's Task 10).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QGraphicsView


def _tiny_dxf(tmp_path):
    import ezdxf
    path = tmp_path / "tiny.dxf"
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (100, 100))
    doc.saveas(str(path))
    return str(path)


def _scene_with_view(qapp):
    from firepro3d.model_space import Model_Space
    from firepro3d.level_manager import LevelManager
    from firepro3d.scale_manager import ScaleManager
    scene = Model_Space()
    scene._level_manager = LevelManager()
    scene.scale_manager = ScaleManager()
    # A view makes the progress dialog a child widget — the crash scenario, where
    # closing the view deletes the dialog's C++ object out from under the worker.
    view = QGraphicsView(scene)
    return scene, view


def test_cleanup_joins_and_dereferences_worker(qapp, tmp_path):
    scene, _view = _scene_with_view(qapp)
    scene.import_dxf(_tiny_dxf(tmp_path), x=0.0, y=0.0)
    worker = scene._underlay_ctl._dxf_worker
    assert worker is not None
    worker.wait(5000)   # run() done; finished_data now queued to the main thread

    scene.cleanup()     # teardown seam — must join + dereference the worker

    assert scene._underlay_ctl._dxf_worker is None
    assert not worker.isRunning()


def test_late_finished_data_after_cleanup_is_noop(qapp, tmp_path):
    scene, _view = _scene_with_view(qapp)
    scene.import_dxf(_tiny_dxf(tmp_path), x=0.0, y=0.0)
    worker = scene._underlay_ctl._dxf_worker
    worker.wait(5000)

    scene.cleanup()

    # After cleanup the worker's signals are disconnected and the slots are
    # guarded, so a late (re-)emitted finished_data must neither recreate an
    # underlay nor raise into the event loop.
    before = len(scene.underlays)
    worker.finished_data.emit([{"type": "line", "points": [(0.0, 0.0), (1.0, 1.0)]}])
    QApplication.processEvents()
    assert len(scene.underlays) == before
