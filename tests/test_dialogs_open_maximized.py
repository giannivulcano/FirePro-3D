"""Both underlay dialogs open maximized on first show (Task 5).

The first ``show()`` maximizes via a ``showEvent`` guard; a later user restore /
double-click is *not* re-maximized (the ``_did_initial_max`` flag). Here we only
assert the first-show behaviour; the restore-then-reshow path needs live smoke.
"""
from firepro3d.underlay_import_dialog import UnderlayImportDialog
from firepro3d.underlay_manager import UnderlayManagerDialog

# Reuse the scene/main_window stubs + factory from the manager dialog test.
from tests.test_underlay_manager_dialog import (
    _FakeScene,
    _FakeMainWindow,
    _dxf_record,
    _FakeGroup,
)


def test_import_dialog_opens_maximized(qapp):
    dlg = UnderlayImportDialog(None)
    dlg.show()
    qapp.processEvents()
    assert dlg.isMaximized()
    dlg.deleteLater()


def test_manager_dialog_opens_maximized(qapp):
    records = [_dxf_record("/tmp/u0.dxf")]
    underlays = [(r, _FakeGroup(["GRID", "WALLS"])) for r in records]
    scene = _FakeScene(underlays)
    mw = _FakeMainWindow()
    dlg = UnderlayManagerDialog(scene, mw)
    dlg.show()
    qapp.processEvents()
    assert dlg.isMaximized()
    dlg.deleteLater()
