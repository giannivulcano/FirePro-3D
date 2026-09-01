"""Chrome tests for the Underlay Manager (Task 4).

The Underlay Manager adopts the frameless house shell (``FramelessShellMixin``):
frameless flags, a themed titlebar with min/max/close control dots, drag-to-move,
and resizable edges. These tests verify the *chrome* is present and that the
existing CRUD widgets survive the change (guts unchanged).

Construction mirrors ``tests/test_underlay_manager_dialog.py`` exactly.
"""
from PyQt6.QtCore import Qt, QObject, pyqtSignal

from firepro3d.frameless_shell import FramelessShellMixin
from firepro3d.underlay import Underlay
from firepro3d.underlay_manager import UnderlayManagerDialog


# --------------------------------------------------------------------------
# Fakes (mirror tests/test_underlay_manager_dialog.py)
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
        _outer = self

        class _LM:
            def apply_to_scene(_s, _scene, _active=None):
                pass

        self.level_mgr = _LM()

    def repen_underlay(self, rec):
        pass

    def remove_underlay(self, rec, item):
        pass

    def refresh_underlay(self, rec, item, sync_from_item=True):
        pass

    def refresh_all_underlays(self):
        pass


class _Level:
    def __init__(self, name):
        self.name = name


class _FakeMainWindow:
    def __init__(self):
        class _LM:
            levels = [_Level("L1"), _Level("L2")]

        self.level_mgr = _LM()

    def open_import_dialog(self):
        pass

    def modify_underlay(self, record):
        pass


def _dxf_record(path="/tmp/a.dxf"):
    return Underlay(type="dxf", path=path, levels=["L1"], colour="#111111")


def _make_dialog():
    records = [_dxf_record(f"/tmp/u{i}.dxf") for i in range(2)]
    underlays = [(r, _FakeGroup(["GRID", "WALLS"])) for r in records]
    scene = _FakeScene(underlays)
    mw = _FakeMainWindow()
    return UnderlayManagerDialog(scene, mw)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
def test_manager_is_frameless_and_shell_based(qapp):
    dlg = _make_dialog()
    assert isinstance(dlg, FramelessShellMixin)
    assert dlg.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert {"min", "max", "close"} <= set(dlg._win_controls.keys())
    dlg.deleteLater()


def test_manager_still_has_crud_widgets(qapp):
    dlg = _make_dialog()
    for attr in ("btn_add", "btn_modify", "btn_reload", "btn_delete",
                 "view", "details", "filter_edit"):
        assert hasattr(dlg, attr)
    dlg.deleteLater()


def test_manager_resizable_respects_min_size(qapp):
    dlg = _make_dialog()
    assert dlg.minimumWidth() >= 1 and dlg.minimumHeight() >= 1
    # resizable path is enabled
    assert dlg._resizable is True
    dlg.deleteLater()
