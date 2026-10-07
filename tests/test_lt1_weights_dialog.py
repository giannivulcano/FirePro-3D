"""LT1-3 -- Line Weights tab edits the PROJECT table; Set as Default -> template.

linetypes.md LT1-3 / H3: the Display Manager Line Weights tab edits the live
project weight table (never the QSettings template), emits
``DisplayManager.lineWeightsChanged`` which MainWindow turns into "project
dirty + re-pen underlays"; Cancel restores the snapshot into the project
table; "Set as Default" on the Line Weights tab writes the template.
QSettings is isolated per test by conftest (#312), and the project table is
reset per test (``_reset_project_line_weights``).
"""
import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QGraphicsPathItem

from firepro3d import paper_display as pd
from firepro3d.display_manager import DisplayManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef
from firepro3d.underlay import Underlay

_LW_TAB = 2   # Model=0, Paper Space=1 (insertTab), Line Weights=2 (addTab)


def _dlg(scene=None):
    return DisplayManager(scene if scene is not None else Model_Space(),
                          active_context="paper")


def _template_raw():
    return QSettings("GV", "FirePro3D").value("paper/line_weights")


def test_line_weights_tab_index(qapp):
    d = _dlg()
    assert d._tabs.tabText(_LW_TAB) == "Line Weights"
    d.reject()


def test_tab_loads_the_project_table(qapp):
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("Site", 0.40)])
    d = _dlg()
    assert "Site" in [x.name for x in d._lw_defs]
    assert all(lw.name != "Site" for lw in pd.load_line_weights())
    d.reject()


def test_add_edits_project_not_template(qapp):
    before = _template_raw()
    d = _dlg()
    fired = []
    d.lineWeightsChanged.connect(lambda: fired.append(1))
    d._on_lw_add()
    assert any(n.startswith("Custom") for n in pd.weight_names())
    assert _template_raw() == before
    assert fired
    d.reject()
    assert not any(n.startswith("Custom") for n in pd.weight_names())


def test_width_edit_and_remove_edit_project_not_template(qapp):
    before = _template_raw()
    d = _dlg()
    row = [x.name for x in d._lw_defs].index("Thick")
    d._lw_table.item(row, 1).setText("0.90")       # fires _on_lw_cell_changed
    assert pd.resolve_line_weight_mm("Thick") == pytest.approx(0.90)
    d._on_lw_add()
    row = [x.name for x in d._lw_defs].index(
        next(x.name for x in d._lw_defs if x.name.startswith("Custom")))
    d._lw_table.setCurrentCell(row, 0)
    d._on_lw_remove()
    assert not any(n.startswith("Custom") for n in pd.weight_names())
    assert _template_raw() == before
    d.reject()
    assert pd.resolve_line_weight_mm("Thick") == pytest.approx(0.50)


def test_set_as_default_writes_template(qapp):
    d = _dlg()
    d._on_lw_add()
    assert not any(lw.name.startswith("Custom") for lw in pd.load_line_weights())
    d._tabs.setCurrentIndex(_LW_TAB)
    d._set_as_default()
    assert any(lw.name.startswith("Custom") for lw in pd.load_line_weights())
    d.accept()


def test_reset_writes_factory_to_project_not_template(qapp):
    pd.save_line_weights([LineWeightDef("Tmpl", 0.33)])          # template
    pd.set_project_line_weights([LineWeightDef("Proj", 0.44)])
    before = _template_raw()
    d = _dlg()
    d._tabs.setCurrentIndex(_LW_TAB)
    d._reset_all()
    assert pd.weight_names() == [x.name for x in pd.FACTORY_LINE_WEIGHTS]
    assert _template_raw() == before
    d.reject()
    assert pd.weight_names() == ["Proj"]


def test_cancel_reverts_a_propagated_rename(qapp):
    scene = Model_Space()
    rec = Underlay(type="dxf", path="x.dxf", line_weight_name="Thin",
                   layer_overrides={"A-WALL": {"line_weight": "Thin"}})
    scene.underlays.append((rec, None))
    d = _dlg(scene)
    row = [x.name for x in d._lw_defs].index("Thin")
    d._lw_table.item(row, 0).setText("Bold")       # fires _on_lw_cell_changed
    assert pd.load_paper_categories()["Wall"]["line_weight"] == "Bold"
    assert "Bold" in pd.weight_names()
    assert rec.line_weight_name == "Bold"
    assert rec.layer_overrides["A-WALL"]["line_weight"] == "Bold"
    d.reject()
    assert "Thin" in pd.weight_names()
    assert "Bold" not in pd.weight_names()
    assert pd.load_paper_categories()["Wall"]["line_weight"] == "Thin"
    assert rec.line_weight_name == "Thin"
    assert rec.layer_overrides["A-WALL"]["line_weight"] == "Thin"


def _paper_combo_items(d):
    combo = d._paper_cat_data["Wall"]["lw_combo"]
    return [combo.itemText(i) for i in range(combo.count())]


def test_paper_tab_combos_list_the_project_table(qapp):
    pd.set_project_line_weights([*pd.FACTORY_LINE_WEIGHTS,
                                 LineWeightDef("Site", 0.40)])
    d = _dlg()
    assert "Site" in _paper_combo_items(d)           # built from the project
    d._on_lw_add()                                   # refresh path
    items = _paper_combo_items(d)
    assert "Site" in items
    assert any(n.startswith("Custom") for n in items)
    d.reject()


# ---------------------------------------------------------------------------
# MainWindow guard: dirty + underlay re-pen through the real connection
# ---------------------------------------------------------------------------

@pytest.fixture
def main_window(qapp):
    from firepro3d import snap_engine
    import main as _main_module
    from firepro3d.view_3d import View3D     # heavy import required before MainWindow
    _main_module.View3D = View3D
    from main import MainWindow
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    w = MainWindow()
    yield w
    w._modified = False
    w.close()
    w.deleteLater()
    qapp.processEvents()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def test_weight_edit_dirties_project_and_repens_underlay(main_window):
    w = main_window
    rec = Underlay(type="dxf", path="x.dxf", line_weight_name="Thin")
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100,
              "layer": "A-WALL"}]
    group, _ = w.scene._build_batched_underlay_group(geoms, rec)
    w.scene.addItem(group)
    w.scene.underlays.append((rec, group))
    child = next(c for c in group.childItems()
                 if isinstance(c, QGraphicsPathItem) and c.data(1) == "A-WALL")
    assert child.pen().widthF() == pytest.approx(pd.canvas_weight_px(0.35))
    w._modified = False

    d = w._make_display_manager("model")            # connected as MainWindow does
    row = [x.name for x in d._lw_defs].index("Thin")
    d._lw_table.item(row, 1).setText("0.70")        # real cell-edit path
    assert w._modified is True
    assert child.pen().widthF() == pytest.approx(pd.canvas_weight_px(0.70))
    assert pd.canvas_weight_px(0.70) != pytest.approx(pd.canvas_weight_px(0.35))

    d.reject()                                      # Cancel re-pens back
    assert child.pen().widthF() == pytest.approx(pd.canvas_weight_px(0.35))
    w.scene.underlays.remove((rec, group))
    w.scene.removeItem(group)
