"""Editor behavior: working copy, save/cancel, snapshot undo, library actions."""
from PyQt6.QtWidgets import QApplication

import firepro3d.titleblock_template as tbt
from firepro3d.titleblock_template import make_default_template
from firepro3d.titleblock_editor import TitleBlockEditorDialog

_app = QApplication.instance() or QApplication([])


class TestEditorSession:
    def _dlg(self, tmp_path, monkeypatch, template=None):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        if template:
            tbt.save_to_library(template)
        return TitleBlockEditorDialog(project_template=None)

    def test_cancel_discards(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.variants["ANSI D"].strip_width_mm = 123.0
        dlg.reject()
        assert tbt.load_library()[0].variants["ANSI D"].strip_width_mm != 123.0

    def test_save_commits_and_stamps_modified(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.variants["ANSI D"].strip_width_mm = 95.0
        dlg.save()
        lib = tbt.load_library()[0]
        assert lib.variants["ANSI D"].strip_width_mm == 95.0

    def test_snapshot_undo_redo(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        before = dlg.working.variants["ANSI D"].strip_width_mm
        dlg.push_snapshot()
        dlg.working.variants["ANSI D"].strip_width_mm = 99.0
        dlg.undo()
        assert dlg.working.variants["ANSI D"].strip_width_mm == before
        dlg.redo()
        assert dlg.working.variants["ANSI D"].strip_width_mm == 99.0

    def test_save_blocked_on_validation_failure(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.variants["ANSI D"].strip_width_mm = 5.0   # under floor
        dlg.refresh_preview()
        assert not dlg.save_button.isEnabled()

    def test_new_duplicate_save(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.new_template()
        assert len(tbt.load_library()) == 0        # library untouched until save
        dlg.save()
        assert len(tbt.load_library()) == 1
        dlg.duplicate_template()
        dlg.save()
        assert len(tbt.load_library()) == 2
        uuids = {t.uuid for t in tbt.load_library()}
        assert len(uuids) == 2

    def test_delete_template(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.delete_template()
        assert tbt.load_library() == []

    def test_use_for_project(self, tmp_path, monkeypatch):
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.use_for_project()
        assert dlg.project_template_result is not None
        assert dlg.project_template_result.uuid == t.uuid

    def test_save_stamps_modified_today(self, tmp_path, monkeypatch):
        import datetime
        t = make_default_template()
        dlg = self._dlg(tmp_path, monkeypatch, t)
        dlg.select_template(t.uuid)
        dlg.working.variants["ANSI D"].strip_width_mm = 95.0
        dlg.save()
        assert tbt.load_library()[0].modified == datetime.date.today().isoformat()


class TestEditorForm:
    def _dlg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = make_default_template()
        tbt.save_to_library(t)
        dlg = TitleBlockEditorDialog(project_template=None)
        dlg.select_template(t.uuid)
        return dlg

    def test_margin_slot_snapshots_and_undo(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_margin_edge(15.0)
        assert dlg.working.variants[dlg._active_size].margin_edge_mm == 15.0
        dlg.undo()
        assert dlg.working.variants[dlg._active_size].margin_edge_mm == 10.0

    def test_cell_reorder(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        first = dlg.working.variants[dlg._active_size].cells[0].kind
        dlg.move_cell(0, 1)
        assert dlg.working.variants[dlg._active_size].cells[1].kind == first

    def test_add_remove_cell(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        n = len(dlg.working.variants[dlg._active_size].cells)
        dlg.add_cell("static_text")
        assert len(dlg.working.variants[dlg._active_size].cells) == n + 1
        dlg.remove_cell(n)
        assert len(dlg.working.variants[dlg._active_size].cells) == n

    def test_add_variant_copies_cells_independently(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_active_size("ANSI D")
        dlg.add_variant("A3")
        assert "A3" in dlg.working.variants
        a3 = dlg.working.variants["A3"]
        d = dlg.working.variants["ANSI D"]
        assert len(a3.cells) == len(d.cells)
        a3.cells[0].label = "changed"
        assert d.cells[0].label != "changed"

    def test_set_cell_prop_and_border(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.set_cell_prop(1, "fill_color", "#ff0000")
        assert dlg.working.variants[dlg._active_size].cells[1].fill_color == "#ff0000"
        dlg.set_cell_border_prop(1, "width_mm", 0.7)
        assert dlg.working.variants[dlg._active_size].cells[1].border.width_mm == 0.7

    def test_preview_uses_renderer_item(self, tmp_path, monkeypatch):
        dlg = self._dlg(tmp_path, monkeypatch)
        dlg.refresh_preview()
        kinds = [type(i).__name__ for i in dlg._preview_scene.items()]
        assert "TitleBlockTemplateItem" in kinds
