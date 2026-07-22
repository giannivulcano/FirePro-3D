"""Tests for the parametric title block template system (data + solver + I/O)."""
import copy
import os

import pytest
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtWidgets import QApplication

import firepro3d.titleblock_template as tbt
from firepro3d.constants import TB_CELL_PAD_MM
from firepro3d.titleblock_template import (
    BorderStyle, FieldDef, Slot, TemplateLayout, TitleBlockTemplate,
    make_default_template, migrate_legacy_fields, native_orientation,
    new_field_id, resolve_text, solve_layout, validate,
    _cell_font,
)

_app = QApplication.instance() or QApplication([])


# ─────────────────────────────────────────────────────────────────────────────
# BROKEN MID-BRANCH — rewritten in Task 5 (rev-3 solver)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="rev-2 solver tests; rewritten in Task 5")
class TestDynamicSolverPass:
    """DD-8b: dynamic pass distributes leftover strip height."""

    PW, PH = 863.6, 558.8  # ANSI D landscape

    def _layout(self, cells, strip=90.0):
        return TemplateLayout(strip_width_mm=strip, cells=cells)

    def test_single_dynamic_stamp_fills_strip(self):
        """A single dynamic stamp → last rect bottom == strip bottom (±1e-6)."""
        cells = [
            CellSpec(kind="field", field_key="Title", min_height_mm=20.0),
            CellSpec(kind="stamp", min_height_mm=30.0, sizing="dynamic"),
        ]
        layout = self._layout(cells)
        sl = solve_layout(layout, self.PW, self.PH, {})
        last_bottom = sl.cell_rects[-1].bottom()
        assert abs(last_bottom - sl.strip_rect.bottom()) < 1e-6, (
            f"last bottom {last_bottom:.4f} != strip bottom "
            f"{sl.strip_rect.bottom():.4f}"
        )

    def test_two_dynamic_rows_proportional_distribution(self):
        """Two dynamic rows with min_heights 10 and 30 → extra distributed 1:3."""
        cells = [
            CellSpec(kind="stamp", min_height_mm=10.0, sizing="dynamic"),
            CellSpec(kind="stamp", min_height_mm=30.0, sizing="dynamic"),
        ]
        layout = self._layout(cells)
        sl = solve_layout(layout, self.PW, self.PH, {})
        assert abs(sl.cell_rects[-1].bottom() - sl.strip_rect.bottom()) < 1e-6
        h0 = sl.cell_rects[0].height()
        h1 = sl.cell_rects[1].height()
        assert abs(h0 / h1 - 10.0 / 30.0) < 1e-3, (
            f"Expected h0/h1 ≈ 1/3, got {h0:.3f}/{h1:.3f} = {h0/h1:.4f}"
        )

    def test_dynamic_field_wrap_does_not_bias_distribution(self):
        """Spec DD-8b: proportionality basis is min_height_mm, NOT wrap-grown height."""
        long_text = "word " * 60
        cells = [
            CellSpec(kind="field", field_key="Title", min_height_mm=10.0,
                     sizing="dynamic", cap_height_mm=3.0),
            CellSpec(kind="stamp", min_height_mm=30.0, sizing="dynamic"),
        ]
        layout = self._layout(cells)
        sl = solve_layout(layout, self.PW, self.PH, {"Title": long_text})
        h0 = sl.cell_rects[0].height()
        assert h0 > 10.0
        assert abs(sl.cell_rects[-1].bottom() - sl.strip_rect.bottom()) < 1e-6
        static_cells = [
            CellSpec(kind="field", field_key="Title", min_height_mm=10.0,
                     sizing="static", cap_height_mm=3.0),
            CellSpec(kind="stamp", min_height_mm=30.0, sizing="static"),
        ]
        sl_static = solve_layout(self._layout(static_cells),
                                 self.PW, self.PH, {"Title": long_text})
        static_h0 = sl_static.cell_rects[0].height()
        static_h1 = sl_static.cell_rects[1].height()
        extra0 = sl.cell_rects[0].height() - static_h0
        extra1 = sl.cell_rects[1].height() - static_h1
        assert extra0 > 0 and extra1 > 0
        ratio = extra0 / extra1
        expected_ratio = 10.0 / 30.0
        assert abs(ratio - expected_ratio) < 1e-3

    def test_zero_leftover_no_change(self):
        cells = [
            CellSpec(kind="stamp", min_height_mm=400.0),
            CellSpec(kind="stamp", min_height_mm=400.0, sizing="dynamic"),
        ]
        layout = self._layout(cells)
        sl = solve_layout(layout, self.PW, self.PH, {})
        h1 = sl.cell_rects[1].height()
        assert h1 == pytest.approx(400.0)

    def test_no_dynamic_cells_unchanged(self):
        cells = [
            CellSpec(kind="stamp", min_height_mm=30.0),
            CellSpec(kind="stamp", min_height_mm=15.0),
        ]
        layout = self._layout(cells)
        sl = solve_layout(layout, self.PW, self.PH, {})
        r0, r1 = sl.cell_rects[0], sl.cell_rects[1]
        assert r0.height() == pytest.approx(30.0)
        assert r1.height() == pytest.approx(15.0)
        assert sl.cell_rects[-1].bottom() < sl.strip_rect.bottom() - 1.0

    def test_dynamic_paired_row_grows_as_one(self):
        cells = [
            CellSpec(kind="field", field_key="Scale", min_height_mm=10.0,
                     pair_with_next=True),
            CellSpec(kind="field", field_key="Date", min_height_mm=10.0,
                     sizing="dynamic"),
            CellSpec(kind="stamp", min_height_mm=20.0),
        ]
        layout = self._layout(cells)
        sl = solve_layout(layout, self.PW, self.PH, {})
        assert sl.cell_rects[0].height() == sl.cell_rects[1].height()
        assert sl.cell_rects[2].height() == pytest.approx(20.0)
        assert abs(sl.cell_rects[-1].bottom() - sl.strip_rect.bottom()) < 1e-6


def _layout(cells, strip=90.0):
    return TemplateLayout(strip_width_mm=strip, cells=cells)


@pytest.mark.skip(reason="rev-2 solver tests; rewritten in Task 5")
class TestSolver:
    PW, PH = 863.6, 558.8   # ANSI D landscape

    def test_area_and_strip_rects(self):
        v = _layout([CellSpec(kind="stamp", min_height_mm=20)])
        sl = solve_layout(v, self.PW, self.PH, {})
        assert sl.strip_rect.right() == self.PW - v.margin_edge_mm
        assert sl.strip_rect.width() == v.strip_width_mm
        assert sl.area_rect.right() == sl.strip_rect.left() - v.margin_strip_mm
        assert sl.area_rect.left() == v.margin_edge_mm

    def test_stack_positions_and_min_heights(self):
        cells = [CellSpec(kind="stamp", min_height_mm=30),
                 CellSpec(kind="stamp", min_height_mm=15)]
        sl = solve_layout(_layout(cells), self.PW, self.PH, {})
        r0, r1 = sl.cell_rects[0], sl.cell_rects[1]
        assert r0.top() == sl.strip_rect.top()
        assert r0.height() == 30
        assert r1.top() == r0.bottom()
        assert r1.height() == 15

    def test_pairing_half_width_row_height_max(self):
        cells = [CellSpec(kind="field", field_key="Scale", min_height_mm=10,
                          pair_with_next=True),
                 CellSpec(kind="field", field_key="Date", min_height_mm=14)]
        sl = solve_layout(_layout(cells), self.PW, self.PH,
                          {"Scale": "1:100", "Date": "2026-07-21"})
        r0, r1 = sl.cell_rects[0], sl.cell_rects[1]
        assert abs(r0.width() - sl.strip_rect.width() / 2) < 1e-6
        assert r0.top() == r1.top()
        assert r0.height() == r1.height() == 14

    def test_wrap_grows_and_pushes_down(self):
        long_val = "a very long project description " * 16
        cells = [CellSpec(kind="field", field_key="Project", min_height_mm=8),
                 CellSpec(kind="stamp", min_height_mm=20)]
        sl = solve_layout(_layout(cells), self.PW, self.PH,
                          {"Project": long_val})
        assert sl.cell_rects[0].height() > 8
        assert sl.cell_rects[1].top() == sl.cell_rects[0].bottom()

    def test_overflow_past_strip_bottom_warns(self):
        cells = [CellSpec(kind="stamp", min_height_mm=400),
                 CellSpec(kind="stamp", min_height_mm=400)]
        sl = solve_layout(_layout(cells), self.PW, self.PH, {})
        assert sl.warnings

    def test_revision_table_rows(self):
        cells = [CellSpec(kind="revision_table", revision_rows=3,
                          min_height_mm=10)]
        revs = [{"no": str(i), "description": f"rev {i}", "date": "07-21"}
                for i in range(5)]
        sl = solve_layout(_layout(cells), self.PW, self.PH,
                          {"__revisions__": revs})
        assert sl.cell_revision_rows[0][0]["no"] == "4"
        assert len(sl.cell_revision_rows[0]) == 3


@pytest.mark.skip(reason="rev-2 solver tests; rewritten in Task 5")
class TestValidate:
    def test_valid_default(self):
        v = _layout([CellSpec(kind="field", field_key="Title")])
        assert validate(v, 863.6, 558.8) == []

    def test_floors(self):
        v = _layout([CellSpec(kind="field", field_key="Title")], strip=5.0)
        assert any("strip" in w.lower() for w in validate(v, 863.6, 558.8))
        v2 = _layout([CellSpec(kind="field", field_key="Title")])
        v2.margin_edge_mm = -1
        assert validate(v2, 863.6, 558.8)
        v3 = _layout([])
        assert any("cell" in w.lower() for w in validate(v3, 863.6, 558.8))
        v4 = _layout([CellSpec(kind="field", field_key="")])
        assert any("field key" in w.lower() for w in validate(v4, 863.6, 558.8))
        v5 = _layout([CellSpec(kind="field", field_key="Title")], strip=120.0)
        assert any("drawing area" in w.lower()
                   for w in validate(v5, 215.9, 279.4))

    def test_minimum_stack_must_fit(self):
        v = _layout([CellSpec(kind="stamp", min_height_mm=600)])
        assert any("fit" in w.lower() for w in validate(v, 863.6, 558.8))


@pytest.mark.skip(reason="rev-2 solver tests; rewritten in Task 5")
class TestCapHeightCrashFix:
    """Finding #1: zero cap_height_mm must not crash solve_layout or _wrapped_height_mm."""

    PW, PH = 863.6, 558.8

    def test_solve_does_not_raise_with_zero_cap_height(self):
        cell = CellSpec(kind="field", field_key="Title", cap_height_mm=0.0)
        v = _layout([cell])
        sl = solve_layout(v, self.PW, self.PH, {"Title": "Fire Protection Plan"})
        assert len(sl.cell_rects) == 1

    def test_validate_flags_zero_cap_height(self):
        cell = CellSpec(kind="field", field_key="Title", cap_height_mm=0.0)
        v = _layout([cell])
        errs = validate(v, self.PW, self.PH)
        assert any("cap height" in e.lower() for e in errs)

    def test_validate_flags_negative_cap_height(self):
        cell = CellSpec(kind="stamp", cap_height_mm=-1.0)
        v = _layout([cell])
        errs = validate(v, self.PW, self.PH)
        assert any("cap height" in e.lower() for e in errs)


@pytest.mark.skip(reason="rev-2 solver tests; rewritten in Task 5")
class TestMinHeightFloor:
    """Finding #2: negative min_height_mm fails validate and doesn't make negative rects."""

    PW, PH = 863.6, 558.8

    def test_validate_flags_negative_min_height(self):
        cell = CellSpec(kind="stamp", min_height_mm=-5.0)
        v = _layout([cell])
        errs = validate(v, self.PW, self.PH)
        assert any("minimum height" in e.lower() for e in errs)

    def test_solve_clamps_negative_min_height_to_zero(self):
        cell = CellSpec(kind="stamp", min_height_mm=-5.0)
        v = _layout([cell])
        sl = solve_layout(v, self.PW, self.PH, {})
        assert sl.cell_rects[0].height() >= 0.0

    def test_validate_passes_zero_min_height(self):
        cell = CellSpec(kind="field", field_key="Title", min_height_mm=0.0)
        v = _layout([cell])
        errs = validate(v, self.PW, self.PH)
        assert not any("minimum height" in e.lower() for e in errs)


@pytest.mark.skip(reason="rev-2 solver tests; rewritten in Task 5")
class TestFilletCheck:
    """Finding #3: fillet check uses the actual area/strip rect dims."""

    PW, PH = 863.6, 558.8

    def test_large_strip_fillet_fails(self):
        cell = CellSpec(kind="field", field_key="Title")
        v = _layout([cell])
        v.strip_border = BorderStyle(corner="fillet", fillet_radius_mm=80.0)
        errs = validate(v, self.PW, self.PH)
        assert any("fillet radius" in e.lower() for e in errs)

    def test_default_fillet_passes(self):
        cell = CellSpec(kind="field", field_key="Title")
        v = _layout([cell])
        assert validate(v, self.PW, self.PH) == []

    def test_sharp_corner_ignores_radius(self):
        cell = CellSpec(kind="field", field_key="Title")
        v = _layout([cell])
        v.strip_border = BorderStyle(corner="sharp", fillet_radius_mm=999.0)
        errs = validate(v, self.PW, self.PH)
        assert not any("fillet radius" in e.lower() for e in errs)


@pytest.mark.skip(reason="rev-2 solver tests; rewritten in Task 5")
class TestCellLinesContract:
    """Finding #5: wrapped lines round-trip and fit within the available px width."""

    PW, PH = 863.6, 558.8

    def test_lines_join_equals_normalized_text(self):
        text = "  The quick brown fox jumps over  the lazy dog  "
        cell = CellSpec(kind="field", field_key="K", cap_height_mm=3.0)
        v = _layout([cell])
        sl = solve_layout(v, self.PW, self.PH, {"K": text})
        lines = sl.cell_lines[0]
        assert " ".join(lines) == " ".join(text.split())

    def test_lines_fit_available_width(self):
        text = "word " * 40
        cell = CellSpec(kind="field", field_key="K", cap_height_mm=3.0)
        v = _layout([cell])
        sl = solve_layout(v, self.PW, self.PH, {"K": text})
        lines = sl.cell_lines[0]
        f = _cell_font(cell)
        fm = QFontMetricsF(f)
        cap_px = fm.capHeight() or 1.0
        px_per_mm = cap_px / max(cell.cap_height_mm, 0.1)
        cw = sl.strip_rect.width()
        avail_px = max(1.0, (cw - 2 * TB_CELL_PAD_MM) * px_per_mm)
        for line in lines:
            if " " in line:
                assert fm.horizontalAdvance(line) <= avail_px + 1e-3

    def test_single_unbreakable_word_one_line(self):
        text = "A" * 200
        cell = CellSpec(kind="field", field_key="K", cap_height_mm=3.0)
        v = _layout([cell])
        sl = solve_layout(v, self.PW, self.PH, {"K": text})
        assert len(sl.cell_lines[0]) == 1


@pytest.mark.skip(reason="rev-2 solver tests; rewritten in Task 5")
class TestHardNewlines:
    """Finding #6: hard \\n splits into separate lines."""

    PW, PH = 863.6, 558.8

    def test_static_text_hard_newline_yields_two_lines(self):
        cell = CellSpec(kind="static_text",
                        static_text="Line one\nLine two",
                        min_height_mm=5.0)
        v = _layout([cell])
        sl = solve_layout(v, self.PW, self.PH, {})
        lines = sl.cell_lines[0]
        assert len(lines) >= 2
        assert lines[0].startswith("Line one")
        assert lines[1].startswith("Line two")

    def test_empty_paragraph_produces_empty_line(self):
        cell = CellSpec(kind="static_text",
                        static_text="a\n\nb",
                        min_height_mm=5.0)
        v = _layout([cell])
        sl = solve_layout(v, self.PW, self.PH, {})
        lines = sl.cell_lines[0]
        assert len(lines) == 3
        assert lines[1] == ""


class TestDisplayName:
    """TitleBlockTemplate.display_name property."""

    def test_landscape_native_no_suffix(self):
        t = TitleBlockTemplate(name="FirePro Default", uuid="u", modified="",
                               paper_size="ANSI D", orientation="landscape",
                               layout=TemplateLayout())
        assert t.display_name == "FirePro Default (ANSI D)"

    def test_portrait_native_no_suffix(self):
        t = TitleBlockTemplate(name="My A4", uuid="u", modified="",
                               paper_size="A4", orientation="portrait",
                               layout=TemplateLayout())
        assert t.display_name == "My A4 (A4)"

    def test_portrait_nonnative_appends_label(self):
        t = TitleBlockTemplate(name="FirePro Default", uuid="u", modified="",
                               paper_size="ANSI D", orientation="portrait",
                               layout=TemplateLayout())
        name = t.display_name
        assert "ANSI D" in name
        assert "Portrait" in name

    def test_landscape_nonnative_appends_label(self):
        t = TitleBlockTemplate(name="My A4", uuid="u", modified="",
                               paper_size="A4", orientation="landscape",
                               layout=TemplateLayout())
        name = t.display_name
        assert "A4" in name
        assert "Landscape" in name


class TestNativeOrientation:
    """native_orientation() helper covers all PAPER_SIZES entries."""

    def test_ansi_landscape(self):
        assert native_orientation("ANSI B") == "landscape"
        assert native_orientation("ANSI D") == "landscape"

    def test_iso_portrait(self):
        for size in ("A4", "A3", "A2", "A1", "A0"):
            assert native_orientation(size) == "portrait", size

    def test_letter_portrait(self):
        assert native_orientation("Letter") == "portrait"

    def test_d_size_portrait(self):
        assert native_orientation("D-size") == "portrait"

    def test_unknown_defaults_landscape(self):
        assert native_orientation("Unknown-X9") == "landscape"


class TestLibrary:
    def _tpl(self, uuid="u-lib", modified="2026-07-21"):
        f = FieldDef(id=new_field_id(), name="Title", text="@[Title]")
        layout = TemplateLayout(fields=[f], rows=[[Slot(f.id, 12.0)]])
        return TitleBlockTemplate(
            name="Lib", uuid=uuid, modified=modified,
            paper_size="ANSI D", orientation="landscape",
            layout=layout)

    def test_save_load_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        t = self._tpl()
        tbt.save_to_library(t)
        loaded = tbt.load_library()
        assert len(loaded) == 1 and loaded[0].uuid == "u-lib"

    def test_dir_created_on_first_use(self, tmp_path, monkeypatch):
        target = tmp_path / "sub" / "titleblocks"
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(target))
        tbt.save_to_library(self._tpl())
        assert target.exists()

    def test_corrupt_file_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        tbt.save_to_library(self._tpl())
        loaded = tbt.load_library()          # must not raise
        assert len(loaded) == 1

    def test_delete(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        tbt.save_to_library(self._tpl())
        tbt.delete_from_library("u-lib")
        assert tbt.load_library() == []

    def test_divergence(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        tbt.save_to_library(self._tpl(modified="2026-07-01"))
        embedded = self._tpl(modified="2026-07-21")
        assert tbt.library_diverges(embedded) is True
        tbt.save_to_library(embedded)
        assert tbt.library_diverges(embedded) is False
        assert tbt.library_diverges(self._tpl(uuid="unknown")) is False

    def test_corrupt_file_skipped_wrong_shape(self, tmp_path, monkeypatch):
        """Wrong-shape JSON (list not dict) must be skipped, not raise."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        (tmp_path / "wrongshape.json").write_text("[1, 2, 3]", encoding="utf-8")
        tbt.save_to_library(self._tpl())
        loaded = tbt.load_library()          # must not raise
        assert len(loaded) == 1

    def test_save_returns_path_and_file_exists(self, tmp_path, monkeypatch):
        """save_to_library returns the written path and the file must exist."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        returned = tbt.save_to_library(self._tpl())
        assert os.path.isfile(returned)

    def test_delete_absent_uuid_is_noop(self, tmp_path, monkeypatch):
        """Deleting a uuid that was never saved must not raise."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        tbt.delete_from_library("does-not-exist")  # must not raise

    def test_non_json_files_ignored(self, tmp_path, monkeypatch):
        """Non-.json files in the library dir are ignored by load_library."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        (tmp_path / "readme.txt").write_text("ignore me", encoding="utf-8")
        (tmp_path / "template.json.bak").write_text("{}", encoding="utf-8")
        tbt.save_to_library(self._tpl())
        loaded = tbt.load_library()
        assert len(loaded) == 1

    def test_save_evil_uuid_raises_value_error(self, tmp_path, monkeypatch):
        """A uuid with path separators must raise ValueError and write nothing."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        evil = self._tpl()
        evil.uuid = "..\\evil"
        with pytest.raises(ValueError):
            tbt.save_to_library(evil)
        assert list(tmp_path.iterdir()) == []

    def test_save_empty_uuid_raises_value_error(self, tmp_path, monkeypatch):
        """An empty uuid must raise ValueError."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        empty = self._tpl()
        empty.uuid = ""
        with pytest.raises(ValueError):
            tbt.save_to_library(empty)


class TestLegacyFieldsMigration:
    """migrate_legacy_fields — one-way project-field seeding (not cell migration)."""

    LEGACY = {"Company": "ACME Fire", "Project": "Plant 9",
              "Title": "L1 Plan", "Scale": "1:100", "Drawing No": "FP-1",
              "Rev": "A", "Date": "01 Jul 2026", "Drawn By": "GV",
              "Checked By": "JB"}

    def test_seeds_project_info_only_if_empty(self):
        info = {"name": ""}
        sheet_fields = dict(self.LEGACY)
        migrate_legacy_fields([sheet_fields], info)
        assert info["name"] == "Plant 9"
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert custom["Company"] == "ACME Fire"
        assert custom["Drawn By"] == "GV"
        assert custom["Checked By"] == "JB"
        # sheet-scoped keys stay; Scale dropped (auto)
        assert sheet_fields["Title"] == "L1 Plan"
        assert "Scale" not in sheet_fields

    def test_idempotent_and_no_overwrite(self):
        info = {"name": "Existing", "custom": [
            {"key": "Company", "value": "Keep Me"}]}
        sheet_fields = dict(self.LEGACY)
        migrate_legacy_fields([sheet_fields], info)
        before = (copy.deepcopy(info), copy.deepcopy(sheet_fields))
        migrate_legacy_fields([sheet_fields], info)
        assert (dict(info), dict(sheet_fields)) == before
        assert info["name"] == "Existing"
        custom = {c["key"]: c["value"] for c in info["custom"]}
        assert custom["Company"] == "Keep Me"

    def test_empty_sheets_no_crash(self):
        info = {}
        migrate_legacy_fields([], info)
        migrate_legacy_fields([{}], info)
        assert "custom" not in info or info["custom"] == []

    # ── Multi-sheet / odd-input hardening (findings 1–2) ─────────────────────

    def test_two_sheets_different_company_first_wins(self):
        """First non-empty Company across sheets seeds; both sheets lose the key."""
        info = {}
        sheet1 = {"Company": "Alpha Fire", "Title": "S1"}
        sheet2 = {"Company": "Beta Fire", "Title": "S2"}
        migrate_legacy_fields([sheet1, sheet2], info)
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert custom["Company"] == "Alpha Fire"     # first non-empty wins
        assert "Company" not in sheet1
        assert "Company" not in sheet2

    def test_first_sheet_empty_company_second_sheet_seeds(self):
        """Empty first-sheet Company is skipped; second sheet's value seeds."""
        info = {}
        sheet1 = {"Company": "", "Title": "S1"}
        sheet2 = {"Company": "Gamma Fire", "Title": "S2"}
        migrate_legacy_fields([sheet1, sheet2], info)
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert custom["Company"] == "Gamma Fire"

    def test_none_company_skipped_no_crash(self):
        """Company=None must be skipped without error and must not seed."""
        info = {}
        sheet = {"Company": None, "Title": "S1"}
        migrate_legacy_fields([sheet], info)
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert "Company" not in custom
        assert "Company" not in sheet          # still popped

    def test_int_company_seeds_as_str(self):
        """Company=123 (int) must be coerced to "123" and seed Project Info."""
        info = {}
        sheet = {"Company": 123, "Title": "S1"}
        migrate_legacy_fields([sheet], info)
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert custom["Company"] == "123"
        assert isinstance(custom["Company"], str)

    def test_skip_values_suppresses_shipped_default(self):
        """A Company matching skip_values is not treated as a donor; key still popped."""
        shipped_default = "Celerity Engineering Limited"
        info = {}
        sheet = {"Company": shipped_default, "Title": "S1"}
        migrate_legacy_fields(
            [sheet], info,
            skip_values={"Company": shipped_default},
        )
        custom = {c["key"]: c["value"] for c in info.get("custom", [])}
        assert "Company" not in custom          # not seeded
        assert "Company" not in sheet           # but key was still popped


class TestResolveText:
    VALUES = {"Company": "Acme Fire", "Rev": "", "Scale": "1:100"}

    def test_substitutes_known_key(self):
        out, unknown = resolve_text("By @[Company]", self.VALUES)
        assert out == "By Acme Fire"
        assert unknown == []

    def test_known_empty_renders_empty(self):
        out, unknown = resolve_text("Rev @[Rev].", self.VALUES)
        assert out == "Rev ."
        assert unknown == []

    def test_unknown_key_stays_literal_and_reported(self):
        out, unknown = resolve_text("@[Drawnig No]", self.VALUES)
        assert out == "@[Drawnig No]"
        assert unknown == ["Drawnig No"]

    def test_multiple_tokens_and_multiline(self):
        out, unknown = resolve_text("@[Company]\n@[Scale] @[Nope]", self.VALUES)
        assert out == "Acme Fire\n1:100 @[Nope]"
        assert unknown == ["Nope"]

    def test_malformed_tokens_pass_through(self):
        for text in ("@[Unclosed", "@[]", "@[a@[b]]"):
            out, unknown = resolve_text(text, self.VALUES)
            assert "@[" in out
        assert resolve_text("@[]", self.VALUES) == ("@[]", [])

    def test_no_tokens_no_change(self):
        assert resolve_text("plain text", self.VALUES) == ("plain text", [])


# ─────────────────────────────────────────────────────────────────────────────
# TestRev3Model — rev-3 data model: FieldDef + Slot + rows (Task 2)
# ─────────────────────────────────────────────────────────────────────────────


class TestRev3Model:
    def _layout(self):
        f1 = FieldDef(id="f1", name="Company", text="@[Company]")
        f2 = FieldDef(id="f2", name="Stamp")            # empty field = stamp
        f3 = FieldDef(id="f3", name="Spare", text="unplaced")
        return TemplateLayout(
            fields=[f1, f2, f3],
            rows=[[Slot("f1", 12.0)], [Slot("f2", 60.0, sizing="dynamic")]],
        )

    def test_round_trip(self):
        lay = self._layout()
        again = TemplateLayout.from_dict(lay.to_dict())
        assert again.to_dict() == lay.to_dict()

    def test_pool_and_placed(self):
        lay = self._layout()
        assert lay.placed_ids() == {"f1", "f2"}
        assert [f.id for f in lay.pool_fields()] == ["f3"]

    def test_field_map(self):
        lay = self._layout()
        assert lay.field_map()["f1"].name == "Company"

    def test_unknown_keys_ignored_on_load(self):
        d = self._layout().to_dict()
        d["future_thing"] = 1
        d["fields"][0]["future_prop"] = "x"
        d["rows"][0][0]["future_slot_prop"] = 2
        TemplateLayout.from_dict(d)      # must not raise

    def test_new_field_id_unique(self):
        assert new_field_id() != new_field_id()

    def test_image_position_reserved_default(self):
        assert FieldDef(id="x").image_position == "top"


# ─────────────────────────────────────────────────────────────────────────────
# TestMigration — rev-2 cells[] → rev-3 fields/rows migration (Task 3)
# ─────────────────────────────────────────────────────────────────────────────


class TestMigration:
    def _old(self, **kw):
        base = {"kind": "field", "field_key": "", "label": "", "static_text": "",
                "min_height_mm": 10.0, "sizing": "static",
                "pair_with_next": False, "font_family": "Arial",
                "cap_height_mm": 3.0, "bold": True, "italic": False,
                "alignment": "left", "fill_color": "",
                "border": {}, "logo_data": "", "logo_fit": "contain",
                "revision_rows": 3}
        base.update(kw)
        return base

    def test_field_key_becomes_token(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(field_key="Company", label="Company")]})
        f = lay.fields[0]
        assert f.text == "@[Company]"
        assert f.name == "Company"
        assert len(lay.rows) == 1 and lay.rows[0][0].field_id == f.id

    def test_static_text_becomes_text(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(kind="static_text", static_text="Hello\nWorld")]})
        assert lay.fields[0].text == "Hello\nWorld"

    def test_logo_becomes_image_field(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(kind="logo", logo_data="AAAA", min_height_mm=25.0)]})
        f = lay.fields[0]
        assert f.kind == "field" and f.image_data == "AAAA" and f.text == ""
        assert f.name == "Logo"
        assert lay.rows[0][0].min_height_mm == 25.0

    def test_stamp_becomes_empty_field(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(kind="stamp", sizing="dynamic", min_height_mm=60.0)]})
        f = lay.fields[0]
        assert (f.kind, f.text, f.image_data) == ("field", "", "")
        assert f.name == "Stamp"
        assert lay.rows[0][0].sizing == "dynamic"

    def test_pair_chain_becomes_two_slot_row(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(field_key="Scale", pair_with_next=True),
            self._old(field_key="Date"),
            self._old(field_key="Title")]})
        assert [len(r) for r in lay.rows] == [2, 1]

    def test_names_deduped(self):
        lay = TemplateLayout.from_dict({"cells": [
            self._old(kind="logo"), self._old(kind="logo")]})
        assert [f.name for f in lay.fields] == ["Logo", "Logo 2"]

    def test_idempotent_and_one_way(self):
        old = {"cells": [self._old(field_key="Company", label="Company",
                                   pair_with_next=True),
                         self._old(field_key="Project")]}
        lay = TemplateLayout.from_dict(old)
        d = lay.to_dict()
        assert "cells" not in d
        assert TemplateLayout.from_dict(d).to_dict() == d

    def test_default_template_is_rev3_native(self):
        t = make_default_template()
        assert t.layout.fields and t.layout.rows
        assert "cells" not in t.layout.to_dict()
        stamp_slot = t.layout.rows[-1][0]
        assert stamp_slot.sizing == "dynamic"
        assert any(f.kind == "revision_table" for f in t.layout.fields)
        from firepro3d.titleblock_template import DEFAULT_SEED_MODIFIED
        assert DEFAULT_SEED_MODIFIED > "2026-07-22"

    def test_variants_era_chains_through(self):
        old_rev1 = {"name": "Old", "uuid": "u1", "modified": "2026-07-21",
                    "variants": {"ANSI D": {
                        "strip_width_mm": 90.0,
                        "cells": [self._old(field_key="Title")]}}}
        t = TitleBlockTemplate.from_dict(old_rev1)
        assert t.layout.fields[0].text == "@[Title]"

    # Coercion coverage carried over from Task-2 review:
    def test_kind_fallback_on_load(self):
        f = FieldDef.from_dict({"id": "x", "kind": "banana"})
        assert f.kind == "field"

    def test_sizing_fallback_on_load(self):
        s = Slot.from_dict({"field_id": "x", "sizing": "banana"})
        assert s.sizing == "static"

    def test_missing_id_regenerated(self):
        f = FieldDef.from_dict({"name": "n"})
        assert f.id
