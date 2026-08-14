import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_no_grid_dialog_module():
    import importlib
    try:
        importlib.import_module("firepro3d.grid_lines_dialog")
        assert False, "grid_lines_dialog should be deleted"
    except ModuleNotFoundError:
        pass


def test_default_seed_places_gridlines(qapp):
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    specs = {"gridlines": [
        {"offset": 0.0, "length": 21945.6, "angle_deg": 90.0, "label": "1"},
        {"offset": 7315.2, "length": 21945.6, "angle_deg": 90.0, "label": "2"},
    ]}
    scene.place_grid_lines(specs)
    assert len(scene._gridlines) == 2


def test_undo_after_seed_baseline_keeps_gridlines(qapp):
    """Regression: seeding pushes an EMPTY-scene snapshot before adding the
    gridlines (place_grid_lines). Callers that seed a default grid must reset
    the undo stack and push a fresh baseline so the seeded gridlines survive a
    later edit+undo. Without the baseline reset, the first undo reverts to the
    empty pre-seed scene and wipes the whole default grid (reported bug)."""
    from firepro3d.model_space import Model_Space
    scene = Model_Space()
    specs = {"gridlines": [
        {"offset": 0.0, "length": 21945.6, "angle_deg": 90.0, "label": "1"},
        {"offset": 7315.2, "length": 21945.6, "angle_deg": 90.0, "label": "2"},
    ]}
    scene.place_grid_lines(specs)

    # Baseline reset (the fix mirrored from new_file()/startup).
    scene._undo_stack = []
    scene._undo_pos = -1
    scene.push_undo_state()

    # Edit a gridline, snapshot the edit, then undo it.
    scene._gridlines[0].set_length(30000.0)
    scene.push_undo_state()
    scene.undo()

    # Undo reverts the edit but MUST NOT delete the seeded gridlines.
    assert len(scene._gridlines) == 2


def test_array_digit_seeds_spacing_field(qapp):
    """A digit that opens the array _DynInput lands in the Spacing field."""
    import firepro3d.model_space as ms_mod
    from firepro3d.model_space import Model_Space
    from PyQt6.QtWidgets import QGraphicsView, QDialog
    from PyQt6.QtCore import QPointF
    from firepro3d.gridline import GridlineItem

    ms = Model_Space()
    view = QGraphicsView(ms); view.resize(400, 400); view.resetTransform()
    gl = GridlineItem(QPointF(0, 0), QPointF(0, 5000), label="1")
    ms.addItem(gl); ms._gridlines.append(gl)
    ms._replicate_source = gl
    ms._replicate_kind = "array"
    ms.set_mode("gridline_array")
    ms._pending_seed = "7"

    captured = {}
    orig_exec = QDialog.exec
    def fake_exec(self):
        first = self._order[0]
        captured["text"] = first.text()
        return QDialog.DialogCode.Rejected
    QDialog.exec = fake_exec
    try:
        ms._handle_tab_input()
    finally:
        QDialog.exec = orig_exec
    view.hide()
    assert captured["text"] == "7"
