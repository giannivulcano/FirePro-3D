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


def _grab_dyninput_field(captured):
    """Read the primary field of the live modal _DynInput and close it.

    Scheduled via QTimer.singleShot so it runs inside the dialog's modal
    exec() loop. We deliberately do NOT monkeypatch QDialog.exec — reassigning
    a sip method to the class corrupts its C++ slot binding for the rest of the
    process (identity restores but the call raises), which leaks into unrelated
    modal-dialog tests. Interacting with the live dialog avoids that entirely.
    """
    from PyQt6.QtWidgets import QApplication
    w = QApplication.activeModalWidget() or QApplication.activePopupWidget()
    if w is None:
        for tw in QApplication.topLevelWidgets():
            if hasattr(tw, "_order") and tw.isVisible():
                w = tw
                break
    if w is not None and hasattr(w, "_order"):
        captured["text"] = w._order[0].text()
    if w is not None:
        (w.reject if hasattr(w, "reject") else w.close)()


def test_array_digit_seeds_spacing_field(qapp):
    """A digit that opens the array _DynInput lands in the Spacing field."""
    from firepro3d.model_space import Model_Space
    from PyQt6.QtWidgets import QGraphicsView
    from PyQt6.QtCore import QPointF, QTimer
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
    QTimer.singleShot(0, lambda: _grab_dyninput_field(captured))
    ms._handle_tab_input()   # opens the modal _DynInput; the timer reads + closes it
    view.hide()
    assert captured.get("text") == "7"


def test_placement_digit_opens_and_seeds_length(qapp):
    """During gridline placement (anchor set), a digit opens the input
    seeded into the Length field."""
    from firepro3d.model_space import Model_Space
    from PyQt6.QtWidgets import QGraphicsView
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QPointF, Qt, QEvent, QTimer

    ms = Model_Space()
    view = QGraphicsView(ms); view.resize(400, 400); view.resetTransform()
    ms.set_mode("draw_gridline")
    ms._draw_line_anchor = QPointF(0, 0)

    captured = {}
    QTimer.singleShot(0, lambda: _grab_dyninput_field(captured))
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_5, Qt.KeyboardModifier.NoModifier, "5")
    ms.keyPressEvent(ev)   # opens the modal _DynInput; the timer reads + closes it
    view.hide()
    assert captured.get("text") == "5"
