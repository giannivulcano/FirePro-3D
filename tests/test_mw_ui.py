"""MW-11 -- Line Weights Model column + System Settings factor (G3).

linetypes.md MW-11 / H-MW-h: the Display Manager Line Weights tab gains a
"Model (px)" column (Auto rows muted "Auto (n)", whole px 1-20 overrides,
empty / "auto" -> Auto, other input refused with the non-modal cell
tooltip); System Settings > UI gains "Model line weight scale" which applies
with a live re-pen / repaint of every canvas (MainWindow
``_refresh_weight_canvases``).
"""
import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QGraphicsPathItem

from firepro3d import paper_display as pd
from firepro3d import theme as th
from firepro3d.display_manager import DisplayManager
from firepro3d.model_space import Model_Space
from firepro3d.paper_display import LineWeightDef
from firepro3d.underlay import Underlay

# Saturated ink: never confusable with a light or dark theme background.
INK = "#ff00ff"
# Sample off x = 0: the Block Editor paints its Y axis through the origin.
_X = 60.0


def _dlg():
    return DisplayManager(Model_Space(), active_context="paper")


def _row(d, name):
    return [x.name for x in d._lw_defs].index(name)


def _px():
    return {x.name: x.model_px for x in pd.project_line_weights()}


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    import main as _main_module
    from firepro3d.view_3d import View3D  # heavy import required before MainWindow()
    _main_module.View3D = View3D
    from main import MainWindow
    recovery = str(tmp_path / "recovery.FPD")   # a real recovery file can't pop a modal
    monkeypatch.setattr(MainWindow, "_autosave_path", staticmethod(lambda: recovery))
    w = MainWindow()
    yield w
    w._modified = False
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _live_underlay(w, weight):
    rec = Underlay(type="dxf", path="x.dxf", line_weight_name=weight)
    geoms = [{"kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 100,
              "layer": "A-WALL"}]
    group, _ = w.scene._build_batched_underlay_group(geoms, rec)
    w.scene.addItem(group)
    w.scene.underlays.append((rec, group))
    child = next(c for c in group.childItems()
                 if isinstance(c, QGraphicsPathItem) and c.data(1) == "A-WALL")
    return rec, group, child


# ---------------------------------------------------------------- D1 column

def test_model_column_shows_auto_and_tooltips(qapp):
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35),
                                 LineWeightDef("Pinned", 0.50, 7)])
    d = _dlg()
    hdr = d._lw_table.horizontalHeaderItem(2)
    assert hdr.text() == "Model (px)" and hdr.toolTip()
    auto = d._lw_table.item(_row(d, "Thin"), 2)
    assert auto.text() == "Auto (3)" and auto.toolTip()
    muted = th.detect().color("muted")
    assert auto.foreground().color() == muted
    pinned = d._lw_table.item(_row(d, "Pinned"), 2)
    assert pinned.text() == "7" and pinned.toolTip()
    assert pinned.foreground().color() != muted
    d.reject()


def test_override_auto_and_refusal(qapp, monkeypatch):
    from PyQt6.QtWidgets import QToolTip
    calls = []
    monkeypatch.setattr(QToolTip, "showText", lambda *a: calls.append(a))
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35)])
    d = _dlg()
    emitted = []
    d.lineWeightsChanged.connect(lambda: emitted.append(1))
    d._lw_table.item(_row(d, "Thin"), 2).setText("5")
    assert _px()["Thin"] == 5 and emitted
    assert d._lw_table.item(_row(d, "Thin"), 2).text() == "5"
    for bad in ("2.5", "0", "21", "abc"):
        calls.clear()
        d._lw_table.item(_row(d, "Thin"), 2).setText(bad)
        assert calls and "1 to 20" in calls[-1][1], bad
        assert _px()["Thin"] == 5
        assert d._lw_table.item(_row(d, "Thin"), 2).text() == "5"
    d._lw_table.item(_row(d, "Thin"), 2).setText("")
    assert _px()["Thin"] is None
    assert d._lw_table.item(_row(d, "Thin"), 2).text() == "Auto (3)"
    d._lw_table.item(_row(d, "Thin"), 2).setText("20")
    assert _px()["Thin"] == 20
    d._lw_table.item(_row(d, "Thin"), 2).setText("AUTO")
    assert _px()["Thin"] is None
    d.accept()
    assert _px()["Thin"] is None


def test_mm_edit_refreshes_auto_text(qapp):
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35)])
    d = _dlg()
    d._lw_table.item(_row(d, "Thin"), 1).setText("0.70")
    assert d._lw_table.item(_row(d, "Thin"), 2).text() == "Auto (6)"
    d.reject()


def test_cancel_restores_overrides(qapp):
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35, 4)])
    d = _dlg()
    d._lw_table.item(_row(d, "Thin"), 2).setText("")
    assert _px()["Thin"] is None
    d.reject()
    assert _px()["Thin"] == 4


def test_reset_is_new_factory_all_auto(qapp):
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35, 4)])
    d = _dlg()
    d._reset_line_weights_tab()
    assert [(x.name, x.width_mm, x.model_px) for x in pd.project_line_weights()] \
        == [(x.name, x.width_mm, None) for x in pd.FACTORY_LINE_WEIGHTS]
    texts = [d._lw_table.item(r, 2).text() for r in range(d._lw_table.rowCount())]
    assert texts == ["Auto (1)", "Auto (2)", "Auto (3)", "Auto (4)", "Auto (6)"]
    d.reject()


def test_set_as_default_writes_model_px(qapp):
    import json
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35, 4)])
    d = _dlg()
    d._tabs.setCurrentIndex(2)
    d._set_as_default()
    raw = json.loads(QSettings("GV", "FirePro3D").value("paper/line_weights"))
    assert {"name": "Thin", "width_mm": 0.35, "model_px": 4} in raw
    d.reject()


def test_override_cell_repens_live_underlay(main_window):
    """The real cell edit reaches MainWindow's re-pen (live repaint, MW-11)."""
    w = main_window
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35)])
    rec, group, child = _live_underlay(w, "Thin")
    try:
        assert child.pen().widthF() == pytest.approx(3.0)
        d = w._make_display_manager("model")
        d._lw_table.item(_row(d, "Thin"), 2).setText("9")
        assert child.pen().widthF() == pytest.approx(9.0)
        d.reject()                                  # Cancel re-pens back
        assert child.pen().widthF() == pytest.approx(3.0)
    finally:
        w.scene.underlays.remove((rec, group))
        w.scene.removeItem(group)


# ---------------------------------------------------------- D2 factor (G3)

def test_uipane_factor_persists_and_calls_back(qapp):
    from firepro3d.settings.panes import UIPane
    fired = []
    pane = UIPane(on_weight_factor_changed=fired.append)
    pane.load()
    spin = pane._weight_factor_spin
    assert spin.value() == 8.0 and spin.toolTip()
    assert (spin.minimum(), spin.maximum(), spin.singleStep()) == (1.0, 20.0, 0.5)
    assert spin.suffix() == " px / paper mm"
    pane.apply()
    assert fired == []                         # unchanged -> no callback
    spin.setValue(10.5)
    pane.apply()
    assert QSettings("GV", "FirePro3D").value(
        "view/model_weight_factor", type=float) == 10.5
    assert fired == [10.5]
    spin.setValue(4.0)
    pane.revert()
    assert spin.value() == 10.5


def test_system_settings_dialog_wires_the_factor_callback(qapp):
    from firepro3d.settings.system_settings_dialog import SystemSettingsDialog
    fired = []
    dlg = SystemSettingsDialog(on_weight_factor_changed=fired.append)
    try:
        dlg._panes["ui"]._weight_factor_spin.setValue(12.0)
        dlg._apply_all()
        assert fired == [12.0]
    finally:
        dlg.close()
        dlg.deleteLater()


def test_g3_factor_through_the_real_pane_repaints_auto_not_override(main_window):
    """G3: the factor set through the real UIPane wired to MainWindow re-pens
    a live underlay and repaints a Block Editor view: Auto rows follow the
    factor, overrides don't (pixel rows)."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from firepro3d.geometry_2d import LineItem
    from firepro3d.model_view import Model_View
    from firepro3d.scale_manager import ScaleManager
    from firepro3d.settings.panes import UIPane
    from tests.mw_support import boundary_y, column_profile, grab, rows
    w = main_window
    pd.set_project_line_weights([LineWeightDef("Thin", 0.35),
                                 LineWeightDef("Pinned", 0.35, 2)])
    rec, group, child = _live_underlay(w, "Thin")
    sc = Model_Space(scene_role="block_editor"); sc.scale_manager = ScaleManager()
    sc.constraint_ctl.show_status = False
    v = Model_View(sc); v.resize(800, 600); v.show(); QTest.qWaitForWindowExposed(v)
    v.resetTransform(); v.centerOn(0, 0); QApplication.processEvents()
    try:
        ya, yb = boundary_y(v, -40.0), boundary_y(v, 40.0)
        for y, name in ((ya, "Thin"), (yb, "Pinned")):
            ln = LineItem(QPointF(-150, y), QPointF(150, y))
            ln.style["weight"] = name; ln.style["colour"] = INK
            sc.addItem(ln); sc._draw_lines.append(ln)

        def count(y):
            img, dpr = grab(v)
            dev = v.viewportTransform().map(QPointF(_X, y))
            bg = img.pixelColor(int(dev.x() * dpr), int((dev.y() + 30) * dpr))
            return rows(column_profile(img, dpr, int(dev.x()), dev.y()),
                        QColor(INK), bg)

        assert (count(ya), count(yb)) == ((3, 0), (2, 0))
        assert child.pen().widthF() == pytest.approx(3.0)
        pane = UIPane(on_weight_factor_changed=w._apply_model_weight_factor)
        pane.load(); pane._weight_factor_spin.setValue(12.0); pane.apply()
        assert pd.model_weight_factor() == 12.0
        assert child.pen().widthF() == pytest.approx(4.0)   # baked pen re-penned
        assert (count(ya), count(yb)) == ((4, 0), (2, 0))   # 0.35 x 12 = 4.2 -> 4
    finally:
        w.scene.underlays.remove((rec, group))
        w.scene.removeItem(group)
        sc.cleanup(); v.close(); v.deleteLater(); QApplication.processEvents()


def test_open_system_settings_passes_the_factor_callback(main_window, monkeypatch):
    """MainWindow's real entry point wires the pane to _apply_model_weight_factor."""
    from firepro3d.settings import system_settings_dialog as ssd
    seen = {}

    def _fake_exec(self):
        self._panes["ui"]._weight_factor_spin.setValue(6.5)
        self._apply_all()
        seen["done"] = True
        return 0
    monkeypatch.setattr(ssd.SystemSettingsDialog, "exec", _fake_exec)
    main_window._open_system_settings()
    assert seen.get("done") and pd.model_weight_factor() == 6.5
