"""SB1b G6 (UI) / G2 (manager) -- Block Manager System copies (D8, D11)."""
import os
import uuid

from PyQt6.QtCore import QPointF

from firepro3d import block_editor as be
from firepro3d import block_library as bl
from firepro3d.block_definition import BlockDefinition
from firepro3d.block_manager import _STATUS_TOKEN, BlockManagerDialog
from firepro3d.fill_layers import PatternLayer
from firepro3d.geometry_2d import RectangleItem

DIAG = "builtin-hatch-diagonal"


class _MW:
    settings = None


def _dialog(ms, root=None):
    return BlockManagerDialog(ms, _MW(), apply_stylesheet=False, root=root)


def _select_block(dlg, block_id):
    src_row = dlg.model.row_for_id(block_id)
    assert src_row >= 0
    proxy_idx = dlg.proxy.mapFromSource(dlg.model.index(src_row, 0))
    dlg.view.setCurrentIndex(proxy_idx)
    return proxy_idx


def _embed_diagonal(ms, root):
    path = os.path.join(root, "Hatches", "Diagonal.fpdb")
    ms.load_blocks_from_files([path])
    return ms._block_definitions[DIAG]


def _system_less_tag(ms):
    """A user-library block saved at v3 whose project copy is untouched v1."""
    d = BlockDefinition.new(name="Tag", library="Mine", series="Set",
                            primitives=[], origin=(0.0, 0.0))
    d.version = 3
    bl.save_to_library(d)
    proj = BlockDefinition.from_dict(d.to_dict())
    proj.version = proj.base_version = 1
    ms.register_block_definition(proj)
    return proj


def _item_with_fill(ms, ref):
    r = RectangleItem(QPointF(0, 0), QPointF(200, 100))
    ms.addItem(r)
    ms._draw_rects.append(r)
    r.set_property("Fill Pattern", PatternLayer(ref))
    return r


def _write_copy(src):
    """What run_duplicate_dialog does after OK, minus the dialog (covered by
    tests/test_system_library_duplicate.py)."""
    copy = BlockDefinition.from_dict(src.to_dict())
    copy.id, copy.version, copy.base_version = uuid.uuid4().hex, 1, None
    copy.name, copy.library, copy.series = f"{src.name} copy", "Mine", "Set"
    return bl.save_to_library(copy)


def _edited_system_copy(ms, root):
    proj = _embed_diagonal(ms, root)
    proj.set_primitives(list(proj.primitives))           # edited -> "modified"
    return proj


def test_g6_update_available_pill_token():
    assert _STATUS_TOKEN["update available"] == "accent"


def test_g6_reload_enabled_for_update_available(model_space, qapp):
    defn = _system_less_tag(model_space)
    dlg = _dialog(model_space)
    _select_block(dlg, defn.id)
    assert dlg.lbl_status.text() == "update available"
    assert dlg.btn_reload.isEnabled() and not dlg.btn_save.isEnabled()
    dlg.close()


def test_g2_manager_save_on_edited_system_copy_duplicates_and_switches(
        model_space, qapp, real_system_library, monkeypatch):
    proj = _edited_system_copy(model_space, real_system_library)
    item = _item_with_fill(model_space, DIAG)
    model_space.push_undo_state()
    seen = []

    def _dup(scene, src, parent, *, root=None, bundled=()):
        seen.append(src.id)
        return _write_copy(src)
    monkeypatch.setattr(be, "run_duplicate_dialog", _dup)
    dlg = _dialog(model_space)
    _select_block(dlg, proj.id)
    assert dlg.lbl_status.text() == "modified"
    dlg._save_to_library()
    assert seen == [DIAG]
    new_ref = item.fill_layers.pattern.ref
    assert new_ref != DIAG
    copy = model_space._block_definitions[new_ref]
    assert copy.name == "Diagonal copy" and copy.version == 1
    assert bl.source_status(copy) == "library"
    assert not bl.is_system_block(copy.id)
    with open(os.path.join(real_system_library, "Hatches", "Diagonal.fpdb"),
              "rb") as fh:
        assert b'"builtin-hatch-diagonal"' in fh.read()    # shipped untouched
    # the manager now shows the copy selected
    assert dlg._current_def().id == copy.id

    # one undo restores the holder; the copy stays registered (baseline)
    model_space.undo()
    assert model_space._draw_rects[0].fill_layers.pattern.ref == DIAG
    assert copy.id in model_space._block_definitions
    dlg.close()


def test_g2_manager_save_cancelled_changes_nothing(
        model_space, qapp, real_system_library, monkeypatch):
    proj = _edited_system_copy(model_space, real_system_library)
    item = _item_with_fill(model_space, DIAG)
    model_space.push_undo_state()
    before = set(model_space._block_definitions)
    steps = len(model_space._undo_stack)
    monkeypatch.setattr(be, "run_duplicate_dialog",
                        lambda scene, src, parent, *, root=None, bundled=(): None)
    dlg = _dialog(model_space)
    _select_block(dlg, proj.id)
    dlg._save_to_library()
    assert item.fill_layers.pattern.ref == DIAG
    assert set(model_space._block_definitions) == before
    assert len(model_space._undo_stack) == steps
    dlg.close()
