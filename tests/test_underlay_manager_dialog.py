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
        self._visible = True

    def data(self, idx):
        return self._layers if idx == 2 else None

    def childItems(self):
        return []

    def setVisible(self, v):
        self._visible = bool(v)

    def isVisible(self):
        return self._visible


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
        self.layer_hidden_calls = []
        _outer = self

        class _LM:
            def apply_to_scene(_s, _scene, _active=None):
                # Mirror the real LevelManager.apply_to_scene underlay path:
                # the master ``record.visible`` gates the whole group.
                _outer.apply_calls += 1
                for data, group in list(_outer.underlays):
                    if group is None:
                        continue
                    group.setVisible(bool(getattr(data, "visible", True)))

        # Real Model_Space exposes the level manager as ``_level_manager``;
        # expose it there so the model's _apply_visibility fallback is exercised.
        self._level_manager = _LM()

    def set_underlay_layer_hidden(self, rec, group, layer, hidden):
        self.layer_hidden_calls.append((rec, layer, hidden))
        if hidden and layer not in rec.hidden_layers:
            rec.hidden_layers.append(layer)
        elif not hidden and layer in rec.hidden_layers:
            rec.hidden_layers.remove(layer)

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


def test_details_layers_row_shows_count(qapp):
    """Single-selection details panel Layers row shows the correct layer count."""
    dlg, scene, mw = _make_dialog(2)
    dlg.show()
    dlg._select_row(0)
    # Both records are backed by _FakeGroup(["GRID", "WALLS"]) → 2 layers.
    assert dlg.details._rows["Layers"].text() == "2 layers"


# --------------------------------------------------------------------------
# Bug 1 — master visibility toggle hides whole group + remembers per-layer
# --------------------------------------------------------------------------
def test_master_vis_toggle_hides_group_and_remembers_layers(qapp):
    from PyQt6.QtCore import Qt
    from firepro3d.underlay_manager_model import Col

    dlg, scene, mw = _make_dialog(1)
    dlg.show()
    record, group = scene.underlays[0]

    # User individually hides a layer first (remembered per-layer state).
    record.hidden_layers = ["WALLS"]

    vis_index = dlg.model.index(0, Col.VIS, QModelIndex())

    # Master OFF → group hidden on canvas, hidden_layers untouched.
    dlg.model.setData(vis_index, False, Qt.ItemDataRole.EditRole)
    assert record.visible is False
    assert group.isVisible() is False           # whole underlay hidden
    assert record.hidden_layers == ["WALLS"]     # per-layer state preserved
    assert scene.apply_calls >= 1                # routed through apply_to_scene

    # Master ON → group shown again, per-layer state still remembered.
    dlg.model.setData(vis_index, True, Qt.ItemDataRole.EditRole)
    assert record.visible is True
    assert group.isVisible() is True
    assert record.hidden_layers == ["WALLS"]     # NOT wiped by master toggle


# --------------------------------------------------------------------------
# Bug 2 / Bug 3 — collapsed by default, expansion preserved across resets
# --------------------------------------------------------------------------
def test_underlays_collapsed_by_default(qapp):
    dlg, scene, mw = _make_dialog(2)
    dlg.show()
    root = QModelIndex()
    for row in range(dlg.proxy.rowCount(root)):
        idx = dlg.proxy.index(row, 0, root)
        assert dlg.view.isExpanded(idx) is False


def test_expansion_preserved_across_model_reset(qapp):
    dlg, scene, mw = _make_dialog(2)
    dlg.show()
    root = QModelIndex()

    # Expand underlay 0 only.
    idx0 = dlg.proxy.index(0, 0, root)
    idx1 = dlg.proxy.index(1, 0, root)
    dlg.view.expand(idx0)
    assert dlg.view.isExpanded(idx0) is True
    assert dlg.view.isExpanded(idx1) is False

    # Trigger a model reset (mirrors the VIS-edit → underlaysChanged path).
    scene.underlaysChanged.emit()

    # Re-fetch indices (nodes rebuilt) and assert expansion state survived.
    idx0 = dlg.proxy.index(0, 0, root)
    idx1 = dlg.proxy.index(1, 0, root)
    assert dlg.view.isExpanded(idx0) is True     # still expanded
    assert dlg.view.isExpanded(idx1) is False    # still collapsed


def test_new_underlay_stays_collapsed_after_reset(qapp):
    dlg, scene, mw = _make_dialog(1)
    dlg.show()
    root = QModelIndex()
    dlg.view.expand(dlg.proxy.index(0, 0, root))

    # Add a second underlay and reset.
    new_rec = _dxf_record("/tmp/new.dxf")
    scene.underlays.append((new_rec, _FakeGroup(["A", "B"])))
    scene.underlaysChanged.emit()

    # The pre-existing (expanded) row stays expanded; the new one is collapsed.
    assert dlg.view.isExpanded(dlg.proxy.index(0, 0, root)) is True
    assert dlg.view.isExpanded(dlg.proxy.index(1, 0, root)) is False


# --------------------------------------------------------------------------
# Feature 2 — persist column widths across sessions (temp QSettings store)
# --------------------------------------------------------------------------
def _temp_settings(tmp_path):
    """A file-backed QSettings the test fully controls (never the real store)."""
    from PyQt6.QtCore import QSettings
    return QSettings(str(tmp_path / "uw.ini"), QSettings.Format.IniFormat)


def _make_dialog_with_settings(settings, n=2):
    records = [_dxf_record(f"/tmp/u{i}.dxf") for i in range(n)]
    underlays = [(r, _FakeGroup(["GRID", "WALLS"])) for r in records]
    scene = _FakeScene(underlays)
    mw = _FakeMainWindow()
    mw.settings = settings  # inject the store the dialog persists into
    dlg = UnderlayManagerDialog(scene, mw)
    return dlg, scene, mw


def test_header_state_round_trips_across_reopen(qapp, tmp_path):
    from firepro3d.underlay_manager_model import Col

    settings = _temp_settings(tmp_path)

    # First open: uses defaults, then user resizes a column.
    dlg1, _s1, _m1 = _make_dialog_with_settings(settings)
    dlg1.show()
    header1 = dlg1.view.header()
    header1.resizeSection(int(Col.NAME), 333)      # user drag -> sectionResized
    assert header1.sectionSize(int(Col.NAME)) == 333
    # sectionResized should have persisted the new layout.
    assert settings.value(UnderlayManagerDialog.HEADER_STATE_KEY)

    # Second open (new dialog, SAME store): restores the saved width.
    dlg2, _s2, _m2 = _make_dialog_with_settings(settings)
    dlg2.show()
    assert dlg2.view.header().sectionSize(int(Col.NAME)) == 333


def test_header_uses_injected_main_window_settings(qapp, tmp_path):
    settings = _temp_settings(tmp_path)
    dlg, _s, _m = _make_dialog_with_settings(settings)
    assert dlg._settings() is settings


def test_corrupt_header_blob_keeps_defaults(qapp, tmp_path):
    from firepro3d.underlay_manager_model import Col

    settings = _temp_settings(tmp_path)
    settings.setValue(UnderlayManagerDialog.HEADER_STATE_KEY, b"not-a-header-state")

    dlg, _s, _m = _make_dialog_with_settings(settings)
    dlg.show()
    # Defensive restore swallows the bad blob -> default NAME width intact.
    assert dlg.view.header().sectionSize(int(Col.NAME)) == 200
