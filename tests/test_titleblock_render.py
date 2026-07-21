"""Renderer/integration tests for the parametric title block system.

Covers:
- Sheet.revisions round-trip and absent-key default
- .fpd titleblock_template embed + load-time legacy migration
- skip_values guard (shipped default Company is not seeded to Project Info)
- no-template round-trip (loads as None)
"""
from __future__ import annotations

import json
import pytest

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from firepro3d.paper_space import DEFAULT_TITLE_BLOCK_FIELDS, Sheet
from firepro3d.titleblock_template import make_default_template

_app = QApplication.instance() or QApplication([])


# ─────────────────────────────────────────────────────────────────────────────
# Sheet.revisions — pure dataclass tests, no scene needed
# ─────────────────────────────────────────────────────────────────────────────

class TestSheetRevisions:
    def test_round_trip(self):
        s = Sheet.create_default()
        s.revisions = [{"no": "1", "description": "Issued", "date": "07-21"}]
        s2 = Sheet.from_dict(s.to_dict())
        assert s2.revisions == s.revisions

    def test_absent_defaults_empty(self):
        d = Sheet.create_default().to_dict()
        d.pop("revisions", None)
        assert Sheet.from_dict(d).revisions == []

    def test_multiple_revisions_preserve_order(self):
        s = Sheet.create_default()
        s.revisions = [
            {"no": "1", "description": "IFC", "date": "07-01"},
            {"no": "2", "description": "Rev A", "date": "07-21"},
        ]
        s2 = Sheet.from_dict(s.to_dict())
        assert s2.revisions[1]["no"] == "2"

    def test_empty_list_round_trips(self):
        s = Sheet.create_default()
        s.revisions = []
        s2 = Sheet.from_dict(s.to_dict())
        assert s2.revisions == []


# ─────────────────────────────────────────────────────────────────────────────
# scene_io embed — uses the MainWindow fixture (same pattern as test_paper_persistence.py)
# ─────────────────────────────────────────────────────────────────────────────

from firepro3d import snap_engine
import main as _main_module
from firepro3d.view_3d import View3D
_main_module.View3D = View3D
from main import MainWindow


@pytest.fixture(scope="module")
def _mw(qapp):
    """Module-scoped MainWindow singleton with safe teardown."""
    saved_tol = snap_engine.SNAP_TOLERANCE_PX
    win = MainWindow()
    win.show()
    QTest.qWaitForWindowExposed(win)
    yield win
    win._modified = False
    win.close()
    win.deleteLater()
    snap_engine.SNAP_TOLERANCE_PX = saved_tol


def _fresh(mw):
    """Reset to a clean default project without tripping the save prompt."""
    mw._modified = False
    mw.new_file()
    assert mw._modified is False


class TestSceneIOEmbed:
    def test_template_embeds_and_migration_runs(self, _mw, tmp_path):
        """Template is embedded in the .fpd; migration moves non-default fields to
        project_info on load.
        """
        _fresh(_mw)
        scene = _mw.scene
        tpl = make_default_template()
        scene._titleblock_template = tpl.to_dict()

        # Give the first sheet a non-default Company value.
        sheet = scene._sheets[0]
        sheet.title_block_fields["Company"] = "ACME"

        path = str(tmp_path / "t.fpd")
        _mw._current_file = path
        _mw.save_file()

        # Load into a fresh scene (reuse the same window — new_file clears state).
        _mw._modified = False
        _mw._load_project(path)

        scene2 = _mw.scene
        # Template is embedded and round-trips.
        assert scene2._titleblock_template is not None
        assert scene2._titleblock_template["name"] == "FirePro Default"

        # Migration ran: Company ("ACME") moved to project_info custom rows.
        custom = scene2._project_info.get("custom", [])
        assert any(
            c.get("key") == "Company" and c.get("value") == "ACME"
            for c in custom
        ), f"Expected Company=ACME in custom rows, got: {custom}"

        # Company must NOT remain in the sheet's title_block_fields.
        assert "Company" not in scene2._sheets[0].title_block_fields, (
            "migrate_legacy_fields must remove Company from sheet fields"
        )

    def test_default_company_not_seeded(self, _mw, tmp_path):
        """A sheet whose Company equals the shipped default must NOT create a
        custom Project Info row (skip_values guard).
        """
        _fresh(_mw)
        scene = _mw.scene
        scene._titleblock_template = make_default_template().to_dict()

        # Keep the default "Celerity Engineering Limited" value.
        sheet = scene._sheets[0]
        default_company = DEFAULT_TITLE_BLOCK_FIELDS["Company"]
        sheet.title_block_fields["Company"] = default_company

        path = str(tmp_path / "default_co.fpd")
        _mw._current_file = path
        _mw.save_file()

        _mw._modified = False
        _mw._load_project(path)
        scene2 = _mw.scene

        custom = scene2._project_info.get("custom", [])
        assert not any(c.get("key") == "Company" for c in custom), (
            "Shipped default Company value must NOT seed Project Info"
        )

    def test_no_template_loads_none(self, _mw, tmp_path):
        """A .fpd saved without _titleblock_template loads as None."""
        _fresh(_mw)
        scene = _mw.scene
        # Ensure no template is set (new_file sets it to None per model_space init).
        scene._titleblock_template = None

        path = str(tmp_path / "no_tpl.fpd")
        _mw._current_file = path
        _mw.save_file()

        # Verify the raw file has no / null titleblock_template key.
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        assert raw.get("titleblock_template") is None

        _mw._modified = False
        _mw._load_project(path)
        scene2 = _mw.scene
        assert scene2._titleblock_template is None

    def test_clear_scene_resets_template_and_project_info(self, _mw):
        """File->New must not leak the previous project's template/info
        (regression: _clear_scene resets both)."""
        _fresh(_mw)
        scene = _mw.scene
        scene._titleblock_template = make_default_template().to_dict()
        scene._project_info = {"name": "Leaky Project",
                               "custom": [{"key": "Company", "value": "X"}]}
        _fresh(_mw)   # File->New
        assert _mw.scene._titleblock_template is None
        assert _mw.scene._project_info.get("name", "") == ""
        assert not _mw.scene._project_info.get("custom")
