"""SB1b G1 (dialog half) / G2 -- Duplicate to library (design D3, D9, D11)."""
import hashlib
import os

import pytest
from PyQt6.QtWidgets import QDialog, QTabWidget

from firepro3d import block_editor as be
from firepro3d import block_library as bl


def _system_diagonal(real_root):
    return os.path.join(real_root, "Hatches", "Diagonal.fpdb")


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def test_is_system_block(real_system_library):
    assert bl.is_system_block("builtin-hatch-diagonal")
    assert not bl.is_system_block("no-such-id")


def _accept_with(monkeypatch, name, library, series):
    """Stub the dialog's exec: fill the fields, then run the real _on_save."""
    def _exec(self):
        self.name_edit.setText(name)
        self._tree.setdefault(library, []).append(series)
        self.library_sel.set_items(sorted(self._tree), current=library)
        self.series_sel.set_items(self._tree[library], current=series)
        self._on_save()
        return self.result()
    monkeypatch.setattr(be.BlockSaveDialog, "exec", _exec)


def test_g2_duplicate_writes_a_new_id_into_the_picked_folder(
        model_space, qapp, real_system_library, monkeypatch):
    src = bl.load_block_file(_system_diagonal(real_system_library))
    _accept_with(monkeypatch, "Diagonal copy", "Mine", "Set")
    refused = []     # a same-id write is refused with a prompt: never block a run
    monkeypatch.setattr("firepro3d.themed_message.themed_info",
                        lambda *a, **k: refused.append(a))
    path = be.run_duplicate_dialog(model_space, src, None)
    assert refused == []
    assert path == os.path.join(bl.block_library_dir(), "Mine", "Set",
                                "Diagonal copy.fpdb")
    copy = bl.load_block_file(path)
    assert copy.id != src.id and copy.name == "Diagonal copy"
    assert copy.tile == src.tile                      # the capability travels
    assert not bl.is_system_block(copy.id)


def test_g2_duplicate_dialog_defaults(model_space, qapp, real_system_library,
                                      monkeypatch):
    seen = {}

    def _exec(self):
        seen["name"] = self.name_edit.text()
        seen["libs"] = [self.library_combo.itemText(i)
                        for i in range(self.library_combo.count())]
        seen["toggle"] = self.save_to_library_cb.isVisible()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(be.BlockSaveDialog, "exec", _exec)
    src = bl.load_block_file(_system_diagonal(real_system_library))
    assert be.run_duplicate_dialog(model_space, src, None) is None   # cancel
    assert seen["name"] == "Diagonal copy"
    assert "System" not in seen["libs"]
    assert seen["toggle"] is False                    # a duplicate always writes
    assert [p for d, _s, fs in os.walk(bl.block_library_dir())
            for p in fs if p.endswith(".fpdb")] == []  # cancel writes nothing


def test_g2_project_copy_duplicates_with_its_bundle(
        model_space, qapp, real_system_library, monkeypatch):
    """The dict bundle form (Block Manager path) writes through as well."""
    src = bl.load_block_file(_system_diagonal(real_system_library))
    _accept_with(monkeypatch, "Bundled", "Mine", "Set")
    path = be.run_duplicate_dialog(model_space, src, None, bundled={})
    assert path is not None and os.path.isfile(path)


@pytest.mark.parametrize("name", ["System", "system"])
def test_g1_dialog_refuses_reserved_library(qapp, name):
    dlg = be.BlockSaveDialog(None, library_tree={name: ["Hatches"]},
                             initial=("X", name, "Hatches"))
    assert "reserved" in (dlg.validation_error() or "")


def test_g1_new_library_plus_refuses_reserved(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr("firepro3d.themed_message.themed_info",
                        lambda *a, **k: shown.append(a[2]))
    dlg = be.BlockSaveDialog(None, library_tree={})
    dlg._create_library("System")
    assert shown and "reserved" in shown[0]
    assert not os.path.exists(os.path.join(bl.block_library_dir(), "System"))


def test_system_origin_edit_locks_library_and_toggle(qapp):
    dlg = be.BlockSaveDialog(None, library_tree={"System": ["Hatches"]},
                             context="edit", system_origin=True,
                             initial=("Diagonal", "System", "Hatches"))
    assert dlg.validation_error() is None             # project-only commit allowed
    v = dlg.values()
    assert v["save_to_library"] is False
    assert not dlg.save_to_library_cb.isEnabled()
    assert not dlg.library_sel.isEnabled()


def test_system_origin_silent_save_commits_project_copy_only(
        model_space, qapp, real_system_library, monkeypatch):
    """T2+T3 review I1: a System-origin copy open in the editor, Save (the
    silent path) must not touch the shipped tier, raise, or prompt."""
    path = _system_diagonal(real_system_library)
    before = _sha(path)
    model_space.load_blocks_from_files([path])
    assert "builtin-hatch-diagonal" in model_space._block_definitions
    shown = []
    monkeypatch.setattr("firepro3d.themed_message.themed_info",
                        lambda *a, **k: shown.append(a))
    tabs = QTabWidget()
    w = be.BlockEditorManager(tabs, model_space).edit_definition(
        "builtin-hatch-diagonal")
    version = model_space.get_block_definition("builtin-hatch-diagonal").version
    defn = w.save()                                   # silent: the block exists
    assert defn is not None and defn.id == "builtin-hatch-diagonal"
    assert shown == []                                # no refusal prompt either
    assert _sha(path) == before                       # shipped bytes unchanged
    assert model_space.get_block_definition(defn.id) is defn
    assert defn.version > version                     # the project copy committed
