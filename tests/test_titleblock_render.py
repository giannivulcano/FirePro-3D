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
# build_field_values + TitleBlockTemplateItem renderer
# Pure QGraphicsItem tests — no MainWindow fixture needed.
# ─────────────────────────────────────────────────────────────────────────────

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter

from firepro3d.paper_space import (TitleBlockTemplateItem, build_field_values,
                                   PAPER_SIZES)
from firepro3d.titleblock_template import solve_layout


def _render(item, w, h, px=600):
    img = QImage(px, int(px * h / w), QImage.Format.Format_RGB32)
    img.fill(0xFFFFFF)
    p = QPainter(img)
    p.scale(px / w, px / w)
    item.paint(p, None, None)
    p.end()
    return img


class TestBuildFieldValues:
    def test_resolution_order_auto_sheet_project(self):
        s = Sheet.create_default()
        s.title_block_fields = {"Title": "L1 Plan"}
        s.revisions = [{"no": "1", "description": "x", "date": "d"}]
        info = {"name": "Plant 9",
                "custom": [{"key": "Company", "value": "ACME"}]}
        vals = build_field_values(s, info)
        assert vals["Title"] == "L1 Plan"          # sheet
        assert vals["Project"] == "Plant 9"        # project standard
        assert vals["Company"] == "ACME"           # project custom
        assert vals["Scale"] == ""                 # auto (no viewports)
        assert vals["__revisions__"] == s.revisions

    def test_sheet_overrides_project(self):
        s = Sheet.create_default()
        s.title_block_fields = {"Project": "Sheet-level"}
        vals = build_field_values(s, {"name": "Project-level"})
        assert vals["Project"] == "Sheet-level"

    def test_scale_auto_always_wins(self):
        s = Sheet.create_default()
        s.title_block_fields = {"Scale": "STALE MANUAL"}
        vals = build_field_values(s, {})
        assert vals["Scale"] == ""   # computed (no viewports), manual ignored


class TestRenderer:
    def _make(self, values=None, mutate=None):
        from firepro3d.titleblock_template import make_default_template
        t = make_default_template()
        v = t.variants["ANSI D"]
        if mutate:
            mutate(v)
        w, h = PAPER_SIZES["ANSI D"]
        values = values or {}
        sl = solve_layout(v, w, h, values)
        return TitleBlockTemplateItem(sl, v, values), w, h

    def test_strip_renders_nonwhite(self):
        item, w, h = self._make({"Title": "L1 PLAN"})
        img = _render(item, w, h)
        strip_x = int(img.width() * (w - 50) / w)     # mid-strip column
        col = [img.pixel(strip_x, y) for y in range(0, img.height(), 5)]
        assert any(c != 0xFFFFFFFF for c in col)      # borders/text drew

    def test_bounding_rect_covers_area_and_strip(self):
        item, w, h = self._make()
        br = item.boundingRect()
        assert br.width() >= w - 25    # spans area+strip inside margins
        assert br.height() >= h - 25

    def test_empty_logo_is_calm_missing_is_warned(self):
        item, w, h = self._make()
        assert item.warnings == []                    # empty logo: reserved box
        item2, _, _ = self._make(
            mutate=lambda v: setattr(v.cells[0], "logo_data", "!!!notbase64!!!"))
        assert item2.warnings                         # undecodable: warned

    def test_no_pointsize_in_renderer(self):
        import inspect
        from firepro3d import paper_space
        src = inspect.getsource(paper_space.TitleBlockTemplateItem)
        assert "setPointSizeF" not in src


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
