"""LT2-6 / WM3 D5 -- the Model "Blocks" row on the Line Weights tab: the weight
combo (LT2-6, smoke round 2) and, since WM3, the Colour swatch that By Category
placements paint in on the canvas (factory Automatic, Q3).

Contract-retired 2026-11-10 (WM3 design, "Contract-retired + rewritten"): the
row was weight-only; its saved record and its tooltip now carry the colour."""
import pytest
from PyQt6.QtCore import QEvent, QObject, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel

from firepro3d import colour_picker
from firepro3d import paper_display as pd
from firepro3d.display_manager import (DisplayManager,
                                       apply_default_display_settings,
                                       apply_project_display_settings,
                                       get_display_settings_for_save)
from firepro3d.model_space import Model_Space
from tests.test_constraint_pick_ribbon import mw  # noqa: F401

_G = "#00ff00"


@pytest.fixture(autouse=True)
def _blocks_row():
    pd.set_model_blocks_weight(None)
    pd.set_model_blocks_colour(None)
    yield
    pd.set_model_blocks_weight(None)
    pd.set_model_blocks_colour(None)


def _pick(monkeypatch, value):
    monkeypatch.setattr(colour_picker, "pick_colour", lambda *a, **k: value)


def test_blocks_row_edits_model_weight_and_emits(qapp):
    d = DisplayManager(Model_Space())
    hits = []
    d.lineWeightsChanged.connect(lambda: hits.append(1))
    combo = d._model_blocks_combo
    assert d._lw_tab.isAncestorOf(combo) and not d._tree.isAncestorOf(combo)
    assert combo.currentText() == "Thinnest"
    assert combo.toolTip()
    combo.setCurrentText("Thin")
    assert pd.model_blocks_weight() == "Thin" and hits
    d.reject()
    assert pd.model_blocks_weight() == "Thinnest"


def test_blocks_row_colour_swatch_edits_model_colour_and_emits(qapp, monkeypatch):
    d = DisplayManager(Model_Space())
    hits = []
    d.lineWeightsChanged.connect(lambda: hits.append(1))
    sw = d._model_blocks_swatch
    assert d._lw_tab.isAncestorOf(sw) and not d._tree.isAncestorOf(sw)
    assert sw.hex() == pd.model_blocks_colour() == "token:auto"   # Q3 factory
    _pick(monkeypatch, _G)
    sw._chip.clicked.emit()                                       # the real chip -> picker
    assert pd.model_blocks_colour() == _G and hits
    assert QSettings("GV", "FirePro3D").value("display/Blocks/color") == _G
    d.reject()                                                    # Cancel restores
    assert pd.model_blocks_colour() == "token:auto"
    assert QSettings("GV", "FirePro3D").value("display/Blocks/color") == "token:auto"


def test_blocks_row_colour_refuses_no_fill(qapp, monkeypatch):
    d = DisplayManager(Model_Space())
    hits = []
    d.lineWeightsChanged.connect(lambda: hits.append(1))
    _pick(monkeypatch, "")
    d._model_blocks_swatch._chip.clicked.emit()
    assert pd.model_blocks_colour() == "token:auto" and not hits
    assert d._model_blocks_swatch.hex() == "token:auto"
    d.reject()


def test_blocks_row_tooltip_names_colour(qapp):
    d = DisplayManager(Model_Space())
    (lbl,) = [l for l in d._lw_tab.findChildren(QLabel)
              if l.text().startswith("Model blocks weight")]
    tip = lbl.toolTip()
    assert "colour" in tip and "block colours" not in tip         # the deliverable is the text
    d.reject()


def test_blocks_swatch_chip_hover_shows_by_category_tooltip(qapp):
    """WM3 Group E review Imp 1: hovering the swatch's chip (its only
    interactive part) shows the By Category text, not the generic
    'Pick model blocks colour'. Driven as Qt delivers a hover: a ToolTip
    help event to the chip, then the shown QToolTip text is read."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QHelpEvent
    from PyQt6.QtWidgets import QApplication, QToolTip
    d = DisplayManager(Model_Space())
    d.show()
    chip = d._model_blocks_swatch._chip
    QToolTip.hideText()
    QApplication.sendEvent(chip, QHelpEvent(
        QEvent.Type.ToolTip, QPoint(2, 2), chip.mapToGlobal(QPoint(2, 2))))
    shown = QToolTip.text()
    QToolTip.hideText()
    d.reject()
    assert "By Category" in shown and "Pick model blocks colour" not in shown


def test_blocks_weight_and_colour_round_trip_through_project(qapp):
    pd.set_model_blocks_weight("Heavy")
    pd.set_model_blocks_colour(_G)
    data = get_display_settings_for_save()
    assert data["Blocks"] == {"line_weight": "Heavy", "color": _G}
    pd.set_model_blocks_weight(None)
    pd.set_model_blocks_colour(None)
    apply_project_display_settings(Model_Space(), data)
    assert pd.model_blocks_weight() == "Heavy"
    assert pd.model_blocks_colour() == _G


def test_legacy_project_without_blocks_colour_reads_factory(qapp):
    apply_project_display_settings(Model_Space(), {"Blocks": {"line_weight": "Heavy"}})
    assert pd.model_blocks_colour() == "token:auto"


def test_reset_and_set_as_default(qapp, monkeypatch):
    d = DisplayManager(Model_Space())
    d._model_blocks_combo.setCurrentText("Thin")
    _pick(monkeypatch, _G)
    d._model_blocks_swatch._chip.clicked.emit()
    d._tabs.setCurrentWidget(d._lw_tab)
    d._set_as_default()                            # Line Weights tab: default -> Thin + _G
    d._reset_line_weights_tab()                    # live row -> factory
    assert pd.model_blocks_weight() == "Thinnest"
    assert pd.model_blocks_colour() == "token:auto"
    assert d._model_blocks_combo.currentText() == "Thinnest"
    assert d._model_blocks_swatch.hex() == "token:auto"
    d.accept()
    apply_default_display_settings(Model_Space())  # New Project path
    assert pd.model_blocks_weight() == "Thin"
    assert pd.model_blocks_colour() == _G
    s = QSettings("GV", "FirePro3D")
    assert s.value("display/Blocks/line_weight") == "Thin"
    assert s.value("display/Blocks/color") == _G


def test_model_undo_keeps_project_blocks_weight_and_colour(qapp, monkeypatch):
    """A user default must not flip the project's Blocks row on Ctrl+Z
    (apply_saved_display_settings runs at every model undo restore)."""
    s = QSettings("GV", "FirePro3D")
    s.setValue("display/Blocks/default_line_weight", "Thinnest")
    s.setValue("display/Blocks/default_color", "#808000")
    ms = Model_Space()
    apply_project_display_settings(ms, {"Blocks": {"line_weight": "Thinnest",
                                                   "color": "#808000"}})
    d = DisplayManager(ms)
    d._model_blocks_combo.setCurrentText("Thin")  # project edit, not default
    _pick(monkeypatch, _G)
    d._model_blocks_swatch._chip.clicked.emit()
    d.accept()
    ms.push_undo_state()
    ms.push_undo_state()
    pd.set_model_blocks_colour(None)               # live cache drifts; the restore must re-resolve it
    ms.undo()
    assert pd.model_blocks_weight() == "Thin"
    assert pd.model_blocks_colour() == _G


class _Paints(QObject):
    """Counts Paint events reaching a widget (the observable repaint)."""

    def __init__(self):
        super().__init__()
        self.n = 0

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Paint:
            self.n += 1
        return False


def test_g3_dm_colour_change_repaints_by_category_placements(mw, qapp, monkeypatch):
    """AC6 / G3 live read: the DM swatch (real MainWindow wiring) repaints the
    plan view and a By Category placement now paints the new colour."""
    from tests.test_constraint_pick_ribbon import _plan_index
    from tests.test_lt1_block_paper import _render_model
    from tests.wm2_support import ROWS, sprinkler_def
    from tests.wm3_support import box_colours
    mw.central_tabs.setCurrentIndex(_plan_index(mw))
    qapp.processEvents()
    ms = mw.scene
    d = sprinkler_def()
    ms.register_block_definition(d)
    inst = ms.place_block_instance(d.id, (0.0, 0.0), level=ms.active_level,
                                   overrides={"colour": "by_category"})
    dlg = mw._make_display_manager("model")
    vp = ms._snap_view().viewport()
    f = _Paints()
    vp.installEventFilter(f)
    try:
        QTest.qWait(300)
        f.n = 0
        QTest.qWait(250)
        assert f.n == 0                            # composition: an idle view does not paint
        mw._modified = False                       # so the dirty assert below is load-bearing
        _pick(monkeypatch, _G)
        dlg._model_blocks_swatch._chip.clicked.emit()
        QTest.qWait(200)
        assert f.n >= 1                            # the plan view repainted
        assert mw._modified                        # project data: dirty
        img = _render_model(ms)
        assert all(box_colours(img, (300, r - 3, 340, r + 4)) == {_G}
                   for r in ROWS.values())
    finally:
        vp.removeEventFilter(f)
        dlg.reject()
        dlg.deleteLater()
        ms.remove_block_instance(inst)
        mw._modified = False
        qapp.processEvents()
