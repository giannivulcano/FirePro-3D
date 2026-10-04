"""LT2-6 / H-e -- Model-tab Line Weight column with a weight-only Blocks row."""
import pytest

from firepro3d import paper_display as pd
from firepro3d.display_manager import (DisplayManager, _COL_LW,
                                       apply_project_display_settings,
                                       get_display_settings_for_save)
from firepro3d.model_space import Model_Space


@pytest.fixture(autouse=True)
def _blocks_weight():
    pd.set_model_blocks_weight(None)
    yield
    pd.set_model_blocks_weight(None)


def test_blocks_row_edits_model_weight_and_emits(qapp):
    d = DisplayManager(Model_Space())
    hits = []
    d.lineWeightsChanged.connect(lambda: hits.append(1))
    combo = d._model_blocks_combo
    assert d._tree.headerItem().text(_COL_LW) == "Line Weight"
    assert combo.currentText() == "Light"
    assert combo.toolTip()
    combo.setCurrentText("Heavy")
    assert pd.model_blocks_weight() == "Heavy" and hits
    d.reject()
    assert pd.model_blocks_weight() == "Light"


def test_blocks_weight_round_trips_through_project(qapp):
    pd.set_model_blocks_weight("Heavy")
    data = get_display_settings_for_save()
    assert data["Blocks"] == {"line_weight": "Heavy"}
    pd.set_model_blocks_weight(None)
    apply_project_display_settings(Model_Space(), data)
    assert pd.model_blocks_weight() == "Heavy"


def test_reset_and_set_as_default(qapp):
    from PyQt6.QtCore import QSettings
    from firepro3d.display_manager import apply_default_display_settings
    d = DisplayManager(Model_Space())
    d._model_blocks_combo.setCurrentText("Heavy")
    d._set_model_as_default()                      # default -> Heavy
    d._reset_model_tab()                           # live row -> factory
    assert pd.model_blocks_weight() == "Light"
    assert d._model_blocks_combo.currentText() == "Light"
    d.accept()
    apply_default_display_settings(Model_Space())  # New Project path
    assert pd.model_blocks_weight() == "Heavy"
    s = QSettings("GV", "FirePro3D")
    assert s.value("display/Blocks/line_weight") == "Heavy"
