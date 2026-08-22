from firepro3d import snap_engine
from firepro3d.preferences_dialog import PreferencesDialog, SettingsPane, SnappingPane


class _StubPane(SettingsPane):
    def __init__(self):
        super().__init__("Stub")
        self.log = []

    def load(self):    self.log.append("load")
    def apply(self):   self.log.append("apply")
    def revert(self):  self.log.append("revert")


def test_dialog_loads_all_panes_on_open(qapp):
    p = _StubPane()
    dlg = PreferencesDialog(panes=[p])
    assert p.log == ["load"]


def test_apply_commits_all_panes(qapp):
    p = _StubPane()
    dlg = PreferencesDialog(panes=[p])
    dlg._apply_all()
    assert "apply" in p.log


def test_reject_reverts_all_panes(qapp):
    p = _StubPane()
    dlg = PreferencesDialog(panes=[p])
    dlg.reject()
    assert "revert" in p.log


def test_snapping_pane_apply_writes_engine(qapp, monkeypatch):
    monkeypatch.setattr(snap_engine, "SNAP_TOLERANCE_PX", 40, raising=False)
    pane = SnappingPane()
    pane.load()
    pane._tol_spin.setValue(12)
    pane.apply()
    assert snap_engine.SNAP_TOLERANCE_PX == 12


def test_snapping_pane_revert_restores(qapp, monkeypatch):
    monkeypatch.setattr(snap_engine, "SNAP_TOLERANCE_PX", 40, raising=False)
    pane = SnappingPane()
    pane.load()
    pane._tol_spin.setValue(5)
    pane.revert()
    assert snap_engine.SNAP_TOLERANCE_PX == 40
