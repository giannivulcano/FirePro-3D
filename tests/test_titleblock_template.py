"""Tests for the parametric title block template system (data + solver + I/O)."""
import copy
import os

import pytest
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtWidgets import QApplication

import firepro3d.titleblock_template as tbt
from firepro3d.constants import TB_CELL_PAD_MM
from firepro3d.titleblock_template import (
    BorderStyle, CellSpec, TemplateVariant, TitleBlockTemplate,
    _cell_font, solve_layout, validate,
)

_app = QApplication.instance() or QApplication([])


class TestSerialization:
    def _template(self):
        cell = CellSpec(kind="field", field_key="Title", label="Sheet Title",
                        min_height_mm=12.0, fill_color="#eef2f7")
        var = TemplateVariant(paper_size="ANSI D", cells=[cell])
        return TitleBlockTemplate(name="Test", uuid="u-1",
                                  modified="2026-07-21",
                                  variants={"ANSI D": var})

    def test_round_trip(self):
        t = self._template()
        t2 = TitleBlockTemplate.from_dict(t.to_dict())
        assert t2.to_dict() == t.to_dict()
        assert t2.variants["ANSI D"].cells[0].field_key == "Title"
        assert t2.variants["ANSI D"].cells[0].border.corner in ("sharp", "fillet")

    def test_unknown_keys_ignored(self):
        d = self._template().to_dict()
        d["future_field"] = 42
        d["variants"]["ANSI D"]["cells"][0]["mystery"] = "x"
        t2 = TitleBlockTemplate.from_dict(d)   # must not raise
        assert t2.name == "Test"

    def test_defaults(self):
        c = CellSpec(kind="stamp")
        assert c.pair_with_next is False
        assert c.border.visible is True
        b = BorderStyle()
        assert b.corner == "fillet" and b.fillet_radius_mm == 10.0
        v = TemplateVariant(paper_size="ANSI B")
        assert v.strip_edge == "right"

    def test_deep_copy_independent(self):
        t = self._template()
        t2 = t.copy()
        t2.variants["ANSI D"].cells[0].label = "changed"
        assert t.variants["ANSI D"].cells[0].label == "Sheet Title"
        assert t2.to_dict() != t.to_dict()


def _variant(cells, strip=90.0):
    return TemplateVariant(paper_size="ANSI D", strip_width_mm=strip,
                           cells=cells)


class TestSolver:
    PW, PH = 863.6, 558.8   # ANSI D landscape

    def test_area_and_strip_rects(self):
        v = _variant([CellSpec(kind="stamp", min_height_mm=20)])
        sl = solve_layout(v, self.PW, self.PH, {})
        # strip: right edge, inside 10mm margins
        assert sl.strip_rect.right() == self.PW - v.margin_edge_mm
        assert sl.strip_rect.width() == v.strip_width_mm
        # drawing area stops margin_strip before the strip
        assert sl.area_rect.right() == sl.strip_rect.left() - v.margin_strip_mm
        assert sl.area_rect.left() == v.margin_edge_mm

    def test_stack_positions_and_min_heights(self):
        cells = [CellSpec(kind="stamp", min_height_mm=30),
                 CellSpec(kind="stamp", min_height_mm=15)]
        sl = solve_layout(_variant(cells), self.PW, self.PH, {})
        r0, r1 = sl.cell_rects[0], sl.cell_rects[1]
        assert r0.top() == sl.strip_rect.top()
        assert r0.height() == 30
        assert r1.top() == r0.bottom()
        assert r1.height() == 15

    def test_pairing_half_width_row_height_max(self):
        cells = [CellSpec(kind="field", field_key="Scale", min_height_mm=10,
                          pair_with_next=True),
                 CellSpec(kind="field", field_key="Date", min_height_mm=14)]
        sl = solve_layout(_variant(cells), self.PW, self.PH,
                          {"Scale": "1:100", "Date": "2026-07-21"})
        r0, r1 = sl.cell_rects[0], sl.cell_rects[1]
        assert abs(r0.width() - sl.strip_rect.width() / 2) < 1e-6
        assert r0.top() == r1.top()
        assert r0.height() == r1.height() == 14   # max of pair

    def test_wrap_grows_and_pushes_down(self):
        long_val = "a very long project description " * 16
        cells = [CellSpec(kind="field", field_key="Project", min_height_mm=8),
                 CellSpec(kind="stamp", min_height_mm=20)]
        sl = solve_layout(_variant(cells), self.PW, self.PH,
                          {"Project": long_val})
        assert sl.cell_rects[0].height() > 8            # grew, text kept size
        assert sl.cell_rects[1].top() == sl.cell_rects[0].bottom()  # pushed

    def test_overflow_past_strip_bottom_warns(self):
        cells = [CellSpec(kind="stamp", min_height_mm=400),
                 CellSpec(kind="stamp", min_height_mm=400)]
        sl = solve_layout(_variant(cells), self.PW, self.PH, {})
        assert sl.warnings                                # clipped + warned

    def test_revision_table_rows(self):
        cells = [CellSpec(kind="revision_table", revision_rows=3,
                          min_height_mm=10)]
        revs = [{"no": str(i), "description": f"rev {i}", "date": "07-21"}
                for i in range(5)]
        sl = solve_layout(_variant(cells), self.PW, self.PH,
                          {"__revisions__": revs})
        assert sl.cell_revision_rows[0][0]["no"] == "4"   # newest first
        assert len(sl.cell_revision_rows[0]) == 3         # capped


class TestValidate:
    def test_valid_default(self):
        v = _variant([CellSpec(kind="field", field_key="Title")])
        assert validate(v, 863.6, 558.8) == []

    def test_floors(self):
        v = _variant([CellSpec(kind="field", field_key="Title")], strip=5.0)
        assert any("strip" in w.lower() for w in validate(v, 863.6, 558.8))
        v2 = _variant([CellSpec(kind="field", field_key="Title")])
        v2.margin_edge_mm = -1
        assert validate(v2, 863.6, 558.8)
        v3 = _variant([])
        assert any("cell" in w.lower() for w in validate(v3, 863.6, 558.8))
        v4 = _variant([CellSpec(kind="field", field_key="")])
        assert any("field key" in w.lower() for w in validate(v4, 863.6, 558.8))
        # drawing area floor: Letter portrait is 215.9 wide; 120mm strip leaves <100
        v5 = _variant([CellSpec(kind="field", field_key="Title")], strip=120.0)
        assert any("drawing area" in w.lower()
                   for w in validate(v5, 215.9, 279.4))

    def test_minimum_stack_must_fit(self):
        v = _variant([CellSpec(kind="stamp", min_height_mm=600)])
        assert any("fit" in w.lower() for w in validate(v, 863.6, 558.8))


class TestCapHeightCrashFix:
    """Finding #1: zero cap_height_mm must not crash solve_layout or _wrapped_height_mm."""

    PW, PH = 863.6, 558.8

    def test_solve_does_not_raise_with_zero_cap_height(self):
        # cap_height_mm=0.0 previously caused ZeroDivisionError in px_per_mm.
        cell = CellSpec(kind="field", field_key="Title", cap_height_mm=0.0)
        v = _variant([cell])
        sl = solve_layout(v, self.PW, self.PH, {"Title": "Fire Protection Plan"})
        # Must complete without raising; rect must be present.
        assert len(sl.cell_rects) == 1

    def test_validate_flags_zero_cap_height(self):
        cell = CellSpec(kind="field", field_key="Title", cap_height_mm=0.0)
        v = _variant([cell])
        errs = validate(v, self.PW, self.PH)
        assert any("cap height" in e.lower() for e in errs)

    def test_validate_flags_negative_cap_height(self):
        cell = CellSpec(kind="stamp", cap_height_mm=-1.0)
        v = _variant([cell])
        errs = validate(v, self.PW, self.PH)
        assert any("cap height" in e.lower() for e in errs)


class TestMinHeightFloor:
    """Finding #2: negative min_height_mm fails validate and doesn't make negative rects."""

    PW, PH = 863.6, 558.8

    def test_validate_flags_negative_min_height(self):
        cell = CellSpec(kind="stamp", min_height_mm=-5.0)
        v = _variant([cell])
        errs = validate(v, self.PW, self.PH)
        assert any("minimum height" in e.lower() for e in errs)

    def test_solve_clamps_negative_min_height_to_zero(self):
        # Negative min_height should produce non-negative rect heights.
        cell = CellSpec(kind="stamp", min_height_mm=-5.0)
        v = _variant([cell])
        sl = solve_layout(v, self.PW, self.PH, {})
        assert sl.cell_rects[0].height() >= 0.0

    def test_validate_passes_zero_min_height(self):
        cell = CellSpec(kind="field", field_key="Title", min_height_mm=0.0)
        v = _variant([cell])
        errs = validate(v, self.PW, self.PH)
        assert not any("minimum height" in e.lower() for e in errs)


class TestFilletCheck:
    """Finding #3: fillet check uses the actual area/strip rect dims."""

    PW, PH = 863.6, 558.8   # ANSI D landscape
    # area_w ~ 748.6, area_h = 538.8, strip_w = 90, strip_h = 538.8

    def test_large_strip_fillet_fails(self):
        # strip min dim = min(90, 538.8) = 90 → max fillet = 45; 80mm > 45mm.
        cell = CellSpec(kind="field", field_key="Title")
        v = _variant([cell])
        v.strip_border = BorderStyle(corner="fillet", fillet_radius_mm=80.0)
        errs = validate(v, self.PW, self.PH)
        assert any("fillet radius" in e.lower() for e in errs)

    def test_default_fillet_passes(self):
        # Default 10mm fillet << 45mm half-min of strip → must pass.
        cell = CellSpec(kind="field", field_key="Title")
        v = _variant([cell])
        # area_border and strip_border default to 10mm fillet.
        assert validate(v, self.PW, self.PH) == []

    def test_sharp_corner_ignores_radius(self):
        # Sharp corner mode: any radius value should be ignored.
        cell = CellSpec(kind="field", field_key="Title")
        v = _variant([cell])
        v.strip_border = BorderStyle(corner="sharp", fillet_radius_mm=999.0)
        errs = validate(v, self.PW, self.PH)
        assert not any("fillet radius" in e.lower() for e in errs)


class TestCellLinesContract:
    """Finding #5: wrapped lines round-trip and fit within the available px width."""

    PW, PH = 863.6, 558.8

    def test_lines_join_equals_normalized_text(self):
        text = "  The quick brown fox jumps over  the lazy dog  "
        cell = CellSpec(kind="field", field_key="K", cap_height_mm=3.0)
        v = _variant([cell])
        sl = solve_layout(v, self.PW, self.PH, {"K": text})
        lines = sl.cell_lines[0]
        assert " ".join(lines) == " ".join(text.split())

    def test_lines_fit_available_width(self):
        text = "word " * 40
        cell = CellSpec(kind="field", field_key="K", cap_height_mm=3.0)
        v = _variant([cell])
        sl = solve_layout(v, self.PW, self.PH, {"K": text})
        lines = sl.cell_lines[0]
        # Compute the same px metrics the solver uses.
        f = _cell_font(cell)
        fm = QFontMetricsF(f)
        cap_px = fm.capHeight() or 1.0
        px_per_mm = cap_px / max(cell.cap_height_mm, 0.1)
        cw = sl.strip_rect.width()
        avail_px = max(1.0, (cw - 2 * TB_CELL_PAD_MM) * px_per_mm)
        # Every line must fit, unless it's a single unbreakable word.
        for line in lines:
            if " " in line:   # only multi-word lines must fit
                assert fm.horizontalAdvance(line) <= avail_px + 1e-3, (
                    f"Line too wide: {line!r}")

    def test_single_unbreakable_word_one_line(self):
        text = "A" * 200
        cell = CellSpec(kind="field", field_key="K", cap_height_mm=3.0)
        v = _variant([cell])
        sl = solve_layout(v, self.PW, self.PH, {"K": text})
        assert len(sl.cell_lines[0]) == 1


class TestHardNewlines:
    """Finding #6: hard \\n splits into separate lines."""

    PW, PH = 863.6, 558.8

    def test_static_text_hard_newline_yields_two_lines(self):
        cell = CellSpec(kind="static_text",
                        static_text="Line one\nLine two",
                        min_height_mm=5.0)
        v = _variant([cell])
        sl = solve_layout(v, self.PW, self.PH, {})
        lines = sl.cell_lines[0]
        assert len(lines) >= 2
        assert lines[0].startswith("Line one")
        assert lines[1].startswith("Line two")

    def test_empty_paragraph_produces_empty_line(self):
        # "a\n\nb" → ["a", "", "b"]
        cell = CellSpec(kind="static_text",
                        static_text="a\n\nb",
                        min_height_mm=5.0)
        v = _variant([cell])
        sl = solve_layout(v, self.PW, self.PH, {})
        lines = sl.cell_lines[0]
        assert len(lines) == 3
        assert lines[1] == ""


class TestIdenticalPairIndex:
    """Finding #7: two field-identical cells in a pair get distinct revision-row keys."""

    PW, PH = 863.6, 558.8

    def test_paired_revision_tables_get_distinct_keys(self):
        # Two identical revision_table cells paired together.
        rev_cell = CellSpec(kind="revision_table", revision_rows=2,
                            pair_with_next=True, min_height_mm=10.0)
        rev_cell2 = CellSpec(kind="revision_table", revision_rows=2,
                             min_height_mm=10.0)
        revs = [{"no": "1", "description": "Initial", "date": "07-21"}]
        v = _variant([rev_cell, rev_cell2])
        sl = solve_layout(v, self.PW, self.PH, {"__revisions__": revs})
        # Keys must be 0 and 1, not both 0.
        assert 0 in sl.cell_revision_rows
        assert 1 in sl.cell_revision_rows


class TestLibrary:
    def _tpl(self, uuid="u-lib", modified="2026-07-21"):
        return TitleBlockTemplate(
            name="Lib", uuid=uuid, modified=modified,
            variants={"ANSI D": TemplateVariant(
                paper_size="ANSI D",
                cells=[CellSpec(kind="field", field_key="Title")])})

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
        # Nothing must have been written outside (or inside) the tmp dir.
        assert list(tmp_path.iterdir()) == []

    def test_save_empty_uuid_raises_value_error(self, tmp_path, monkeypatch):
        """An empty uuid must raise ValueError."""
        monkeypatch.setattr(tbt, "_library_dir", lambda: str(tmp_path))
        empty = self._tpl()
        empty.uuid = ""
        with pytest.raises(ValueError):
            tbt.save_to_library(empty)


from firepro3d.titleblock_template import make_default_template, migrate_legacy_fields


class TestDefaultTemplate:
    def test_variants_present_and_valid(self):
        t = make_default_template()
        for size, (w, h) in (("ANSI B", (431.8, 279.4)),
                             ("ANSI D", (863.6, 558.8)),
                             ("Letter", (215.9, 279.4))):
            assert size in t.variants
            assert validate(t.variants[size], w, h) == []

    def test_arrangement_a(self):
        # mockup-gated 2026-07-21: logo top, stamp/revisions bottom, fillet frames
        v = make_default_template().variants["ANSI D"]
        kinds = [c.kind for c in v.cells]
        assert kinds[0] == "logo"
        assert kinds[-1] == "stamp"
        assert "revision_table" in kinds
        assert v.area_border.corner == "fillet"
        keys = [c.field_key for c in v.cells if c.kind == "field"]
        for k in ("Company", "Project", "Title", "Scale", "Date",
                  "Drawn By", "Checked By", "Drawing No", "Rev"):
            assert k in keys

    def test_unique_uuid_per_call(self):
        assert make_default_template().uuid != make_default_template().uuid


class TestMigration:
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
        before = (dict(info), dict(sheet_fields))
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
