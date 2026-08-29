"""Tests for the Underlay Manager dialog (Task 11).

The dialog binds directly to a ``Model_Space``-like scene and a
``MainWindow``-like object. We build minimal QObject stubs (mirroring
tests/test_underlay_manager_model.py) sufficient to drive the dialog's core
actions: list / delete / add / modify / reload, plus Modify-button enablement.

Modal paths (the Delete confirm box, the import dialog, the file picker) are
NOT driven here — Task 18 smoke covers those. ``_delete(confirm=False)``
bypasses the confirm box to exercise the real remove path.
"""
from PyQt6.QtCore import QModelIndex, QObject, pyqtSignal

from firepro3d.underlay import Underlay
from firepro3d.underlay_manager import UnderlayManagerDialog


# --------------------------------------------------------------------------
# Fakes (mirror tests/test_underlay_manager_model.py)
# --------------------------------------------------------------------------
class _FakeGroup:
    def __init__(self, layers=None):
        self._layers = layers or []

    def data(self, idx):
        return self._layers if idx == 2 else None

    def childItems(self):
        return []


class _FakeScene(QObject):
    underlaysChanged = pyqtSignal()

    def __init__(self, underlays):
        super().__init__()
        self.underlays = underlays
        self.active_level = "L1"
        self.repen_calls = []
        self.apply_calls = 0
        self.refresh_calls = []
        self.refresh_all_calls = 0
        _outer = self

        class _LM:
            def apply_to_scene(_s, _scene, _active=None):
                _outer.apply_calls += 1

        self.level_mgr = _LM()

    def repen_underlay(self, rec):
        self.repen_calls.append(rec)

    def remove_underlay(self, rec, item):
        pair = (rec, item)
        if pair in self.underlays:
            self.underlays.remove(pair)
        self.underlaysChanged.emit()

    def refresh_underlay(self, rec, item, sync_from_item=True):
        self.refresh_calls.append((rec, item))

    def refresh_all_underlays(self):
        self.refresh_all_calls += 1


class _Level:
    def __init__(self, name):
        self.name = name


class _FakeMainWindow:
    def __init__(self):
        self.import_calls = 0
        self.modify_calls = []

        class _LM:
            levels = [_Level("L1"), _Level("L2")]

        self.level_mgr = _LM()

    def open_import_dialog(self):
        self.import_calls += 1

    def modify_underlay(self, record):
        self.modify_calls.append(record)


def _dxf_record(path="/tmp/a.dxf"):
    return Underlay(type="dxf", path=path, levels=["L1"], colour="#111111")


def _make_dialog(n=2, qapp=None):
    records = [_dxf_record(f"/tmp/u{i}.dxf") for i in range(n)]
    underlays = [(r, _FakeGroup(["GRID", "WALLS"])) for r in records]
    scene = _FakeScene(underlays)
    mw = _FakeMainWindow()
    dlg = UnderlayManagerDialog(scene, mw)
    return dlg, scene, mw


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
def test_dialog_lists_all_underlays(qapp):
    dlg, scene, mw = _make_dialog(2)
    dlg.show()
    root = QModelIndex()
    assert dlg.view.model().rowCount(root) == 2


def test_delete_removes_selected(qapp):
    dlg, scene, mw = _make_dialog(2)
    dlg.show()
    dlg._select_row(0)
    dlg._delete(confirm=False)
    assert len(scene.underlays) == 1


def test_add_invokes_import_dialog(qapp):
    dlg, scene, mw = _make_dialog(2)
    dlg.show()
    called = []
    mw.open_import_dialog = lambda: called.append(True)
    dlg._add()
    assert called == [True]


def test_modify_invokes_modify_underlay_with_record(qapp):
    dlg, scene, mw = _make_dialog(2)
    dlg.show()
    expected = scene.underlays[0][0]
    dlg._select_row(0)
    dlg._modify()
    assert mw.modify_calls == [expected]


def test_reload_all_when_none_selected(qapp):
    dlg, scene, mw = _make_dialog(2)
    dlg.show()
    dlg.view.selectionModel().clearSelection()
    dlg._reload()
    assert scene.refresh_all_calls == 1


def test_modify_disabled_with_no_or_multi_selection(qapp):
    dlg, scene, mw = _make_dialog(2)
    dlg.show()

    # No selection -> disabled.
    dlg.view.selectionModel().clearSelection()
    dlg._sync_ui()
    assert dlg.btn_modify.isEnabled() is False

    # Exactly one underlay row -> enabled.
    dlg._select_row(0)
    assert dlg.btn_modify.isEnabled() is True

    # Two rows selected -> disabled.
    sel = dlg.view.selectionModel()
    idx1 = dlg.proxy.mapFromSource(dlg.model.index(1, 0, QModelIndex()))
    sel.select(idx1, sel.SelectionFlag.Select | sel.SelectionFlag.Rows)
    dlg._sync_ui()
    assert dlg.btn_modify.isEnabled() is False
